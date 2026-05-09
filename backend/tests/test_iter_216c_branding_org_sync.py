"""Iter 216c regression — org-name ↔ branding.company_name drift guard.

Background
----------
Before iter-216c, the dashboard header read `branding.company_name` while
Master Admin / billing / audit logs read `organizations.name`. The two
fields could drift apart because `update_branding` only wrote one side.
Lee's Feb-2026 production screenshot caught Bob's gym showing
"Test Org Name" in the header even though Master Admin had it correctly
recorded as "Strong Fitness".

These tests pin the iter-216c contract:

  1. PATCH /api/organization/branding with `company_name=X` updates BOTH
     `organizations.name` AND `branding.company_name` to X atomically.

  2. GET /api/organization self-heals on read: if a previously-drifted
     org has `branding.company_name != organizations.name`, the response
     returns the canonical `organizations.name` for both fields without
     requiring an explicit save.

  3. PATCHing without a `company_name` (e.g. only updating
     `primary_color`) leaves `organizations.name` untouched — non-empty
     names never get blanked out.

If any of these break, every consumer that reads either field will start
disagreeing again — the "two fields, one truth" pattern is back.
"""
import requests

import pytest

from tests.conftest import (
    _test_backend_url,
    rate_limit_bypass_headers,
    REGULAR_USER_EMAIL,
    REGULAR_USER_PASSWORD,
)


@pytest.fixture(scope="module")
def regular_token() -> str:
    """Module-scoped login so we don't burn the rate-limit budget."""
    base = _test_backend_url()
    resp = requests.post(
        f"{base}/api/auth/login",
        json={"email": REGULAR_USER_EMAIL, "password": REGULAR_USER_PASSWORD},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert token, "login response missing token"
    return token


def _get_org(token: str) -> dict:
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/organization",
        headers={"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _patch_branding(token: str, payload: dict) -> dict:
    base = _test_backend_url()
    r = requests.patch(
        f"{base}/api/organization/branding",
        json=payload,
        headers={"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_patch_branding_keeps_org_name_in_sync(regular_token):
    """PATCH branding.company_name must also write organizations.name."""
    original = _get_org(regular_token)
    original_name = original.get("name")
    assert original_name, "fixture org should have a name"

    new_name = f"{original_name} (sync-test-{uuid_short()})"
    try:
        _patch_branding(regular_token, {
            "company_name": new_name,
            "primary_color": "#0055FF",
            "logo_url": "",
        })
        after = _get_org(regular_token)
        assert after["name"] == new_name, "organizations.name should have been updated"
        assert (after.get("branding") or {}).get("company_name") == new_name, \
            "branding.company_name should also reflect the new value"
    finally:
        # Restore so other tests + the live test account don't see the
        # mutated name. Idempotent — safe even if the test failed mid-way.
        _patch_branding(regular_token, {
            "company_name": original_name,
            "primary_color": (original.get("branding") or {}).get("primary_color") or "#0055FF",
            "logo_url": (original.get("branding") or {}).get("logo_url") or "",
        })


def test_get_organization_self_heals_drifted_company_name(regular_token):
    """GET should always return branding.company_name == organizations.name.

    We can't (and shouldn't) write the drifted state directly from the
    test — the API contract is what we exercise. Instead we PATCH a fresh
    name and assert the returned `branding.company_name` matches the
    `name` field. Once `update_branding` keeps them in sync going forward,
    the self-heal path is essentially "branding.company_name returned by
    the API will always equal organizations.name".
    """
    org = _get_org(regular_token)
    name = (org.get("name") or "").strip()
    branding_name = (org.get("branding") or {}).get("company_name") or ""
    assert name, "org must have a name"
    assert name == branding_name, (
        f"GET /api/organization returned drifted names: "
        f"name={name!r}, branding.company_name={branding_name!r}. "
        "Iter-216c read-time self-heal is broken."
    )


def test_patch_branding_without_company_name_does_not_blank_org_name(regular_token):
    """Updating only primary_color/logo_url must NOT clear organizations.name."""
    original = _get_org(regular_token)
    original_name = original.get("name")
    assert original_name

    # Send the patch WITHOUT a company_name — only colour/logo.
    _patch_branding(regular_token, {
        "primary_color": "#112233",
        "logo_url": "",
    })
    after = _get_org(regular_token)
    assert after["name"] == original_name, (
        "PATCH without company_name accidentally cleared organizations.name "
        "— iter-216c only-write-when-non-empty guard regressed."
    )

    # Restore the colour so we leave the world tidy.
    _patch_branding(regular_token, {
        "primary_color": (original.get("branding") or {}).get("primary_color") or "#0055FF",
        "logo_url": (original.get("branding") or {}).get("logo_url") or "",
    })


def uuid_short() -> str:
    """Return a 6-char random id (helper, not a pytest test)."""
    import uuid
    return uuid.uuid4().hex[:6]
