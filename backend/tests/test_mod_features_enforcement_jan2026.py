"""MOD-only module enforcement on PUT /api/master-admin/organizations/{id}/features.

Verifies:
 - For a MOD org, attempting to enable crm/memberships/marketing is silently
   forced to enabled=false and stripped from enabled_modules.
 - Operations can still be enabled on a MOD org.
 - Regression: NON-MOD (full) org can still enable crm/memberships/marketing.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def hdrs(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _create_org(hdrs, name, account_type, is_mod=False):
    # Try common create endpoint
    payload = {
        "name": name,
        "industry": "MOD" if is_mod else "commercial",
        "account_type": account_type,
        "is_mod": is_mod,
        "primary_contact_email": f"owner+{uuid.uuid4().hex[:6]}@example.com",
        "primary_contact_name": "Test Owner",
    }
    r = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                      json=payload, headers=hdrs, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"Cannot create org via master-admin API: {r.status_code} {r.text[:300]}")
    data = r.json()
    return data.get("id") or (data.get("organization") or {}).get("id") or data.get("org_id")


def _get_org(hdrs, org_id):
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations/{org_id}",
                     headers=hdrs, timeout=30)
    if r.status_code == 404:
        # Fallback to list
        r2 = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=hdrs, timeout=30)
        assert r2.status_code == 200
        rows = r2.json() if isinstance(r2.json(), list) else r2.json().get("organizations", [])
        for o in rows:
            if o.get("id") == org_id:
                return o
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find_existing_mod_org(hdrs):
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=hdrs, timeout=30)
    assert r.status_code == 200
    j = r.json()
    rows = j if isinstance(j, list) else j.get("organizations", [])
    for o in rows:
        if o.get("is_mod") or o.get("account_type") in {"mod_site", "mod_branch", "mod_org"}:
            return o.get("id")
    return None


def test_mod_org_features_endpoint_locks_out_bolt_ons(hdrs):
    org_id = _find_existing_mod_org(hdrs)
    created = False
    if not org_id:
        org_id = _create_org(hdrs, f"TEST_MOD_{uuid.uuid4().hex[:6]}", "mod_org", is_mod=True)
        created = True
    assert org_id, "No MOD org available"

    payload = {
        "modules": {
            "operations": {"enabled": True, "tier": "pro"},
            "crm": {"enabled": True, "tier": "pro"},
            "memberships": {"enabled": True, "tier": "pro"},
            "marketing": {"enabled": True, "tier": "pro"},
        }
    }
    r = requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
                     json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, f"PUT features failed: {r.status_code} {r.text[:400]}"

    org = _get_org(hdrs, org_id)
    mods = org.get("modules") or {}
    enabled = org.get("enabled_modules") or []

    for m in ("crm", "memberships", "marketing"):
        entry = mods.get(m) or {}
        assert entry.get("enabled") is False, f"MOD org must have {m}.enabled=False, got {entry}"
        assert m not in enabled, f"MOD org enabled_modules must exclude {m}, got {enabled}"

    # Operations should be enabled
    assert (mods.get("operations") or {}).get("enabled") is True
    assert "operations" in enabled

    # Cleanup if we created
    if created:
        try:
            requests.delete(f"{BASE_URL}/api/master-admin/organizations/{org_id}",
                            headers=hdrs, timeout=15)
        except Exception:
            pass


def test_non_mod_org_can_enable_bolt_ons(hdrs):
    # Use existing seeded iso-demo-org (non-MOD full)
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=hdrs, timeout=30)
    assert r.status_code == 200
    j = r.json()
    rows = j if isinstance(j, list) else j.get("organizations", [])
    target = None
    for o in rows:
        if o.get("id") == "iso-demo-org":
            target = o
            break
    if not target:
        # fallback: first full non-mod
        for o in rows:
            if o.get("account_type") == "full" and not o.get("is_mod"):
                target = o
                break
    assert target, "No non-MOD full org available for regression"
    org_id = target["id"]

    payload = {
        "modules": {
            "crm": {"enabled": True, "tier": "pro", "business_enabled": True, "leisure_enabled": True},
            "memberships": {"enabled": True, "tier": "pro"},
            "marketing": {"enabled": True, "tier": "pro"},
            "operations": {"enabled": True, "tier": "pro"},
        }
    }
    r = requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
                     json=payload, headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text[:400]

    org = _get_org(hdrs, org_id)
    mods = org.get("modules") or {}
    enabled = org.get("enabled_modules") or []
    for m in ("crm", "memberships", "marketing", "operations"):
        assert (mods.get(m) or {}).get("enabled") is True, f"{m} should be enabled on non-MOD org: {mods.get(m)}"
        assert m in enabled, f"{m} missing from enabled_modules: {enabled}"
