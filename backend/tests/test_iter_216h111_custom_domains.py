"""Regression tests for iter 216h111 — custom-domain routing.

Covers:
  * Master-admin CRUD on the per-org custom-domain list
  * Hostname validation (FQDN + platform-host block)
  * Force-verify path (GymAxis master only)
  * Public host-config resolver — matches verified, ignores unverified,
    follows primary_route updates
  * Auth gates — endpoints reject unauthenticated callers
"""
from __future__ import annotations

import uuid

import requests

from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    _test_backend_url,
)

API = _test_backend_url() + "/api"


def _master_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("token")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _pick_org_id(token: str) -> str:
    listing = requests.get(
        f"{API}/master-admin/organizations",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    orgs = listing if isinstance(listing, list) else listing.get("organizations") or listing.get("items") or []
    assert orgs, "Expected at least one organisation"
    # Prefer a pulse_pro org (most realistic), fall back to any non-MOD.
    eligible = [o for o in orgs if (o.get("account_type") or "").lower() == "pulse_pro"]
    if not eligible:
        eligible = [o for o in orgs if not (o.get("account_type") or "").lower().startswith("mod")]
    assert eligible, "Expected at least one non-MOD org"
    return eligible[0]["id"]


def _unique_host(label: str = "test") -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}.regress-host.example"


# ── 1. List endpoint ─────────────────────────────────────────────────


def test_custom_domains_list_empty_starts_clean():
    token = _master_token()
    org_id = _pick_org_id(token)
    r = requests.get(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["org_id"] == org_id
    assert isinstance(body.get("domains"), list)
    assert isinstance(body.get("allowed_routes"), list)
    route_values = [r["value"] for r in body["allowed_routes"]]
    assert {"join", "app", "brag", "timetable"} <= set(route_values)


# ── 2. Validation ────────────────────────────────────────────────────


def test_create_rejects_invalid_hostname():
    token = _master_token()
    org_id = _pick_org_id(token)
    r = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        json={"hostname": "not a domain", "primary_route": "join"},
        timeout=10,
    )
    assert r.status_code == 400


def test_create_rejects_platform_subdomain():
    token = _master_token()
    org_id = _pick_org_id(token)
    r = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        json={"hostname": "join.gymaxisai.com", "primary_route": "join"},
        timeout=10,
    )
    assert r.status_code == 400
    assert "platform" in r.json()["detail"].lower()


def test_create_rejects_invalid_route():
    token = _master_token()
    org_id = _pick_org_id(token)
    r = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        json={"hostname": _unique_host(), "primary_route": "bogus"},
        timeout=10,
    )
    assert r.status_code == 400


# ── 3. CRUD round-trip ───────────────────────────────────────────────


def test_create_force_verify_resolve_update_delete_round_trip():
    token = _master_token()
    org_id = _pick_org_id(token)
    host = _unique_host("crud")

    # CREATE
    cr = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        json={"hostname": host, "primary_route": "join"},
        timeout=10,
    )
    assert cr.status_code == 200, cr.text
    domain = cr.json()["domain"]
    assert domain["hostname"] == host
    assert domain["verified"] is False
    assert domain["dns_record"]["txt"]["value"] == domain["dns_token"]
    assert domain["dns_record"]["txt"]["host"] == f"_gymaxis-verify.{host}"
    domain_id = domain["id"]

    try:
        # Pre-verify public resolver should NOT match (unverified)
        hc = requests.get(f"{API}/public/host-config", params={"host": host}, timeout=10)
        assert hc.status_code == 200
        assert hc.json()["matched"] is False

        # FORCE-VERIFY (master-admin only path)
        fv = requests.post(
            f"{API}/master-admin/custom-domains/orgs/{org_id}/{domain_id}/force-verify",
            headers=_h(token),
            timeout=10,
        )
        assert fv.status_code == 200, fv.text
        assert fv.json()["verified"] is True

        # PUBLIC HOST-CONFIG should now match
        hc2 = requests.get(f"{API}/public/host-config", params={"host": host}, timeout=10)
        assert hc2.status_code == 200, hc2.text
        cfg = hc2.json()
        assert cfg["matched"] is True
        assert cfg["org_id"] == org_id
        assert cfg["primary_route"] == "join"
        assert cfg["redirect_path"].endswith("/join")
        # PII guard — never leak the verification token.
        assert "dns_token" not in cfg
        assert "dns_record" not in cfg

        # PATCH primary_route → "app"
        pa = requests.patch(
            f"{API}/master-admin/custom-domains/orgs/{org_id}/{domain_id}",
            headers=_h(token),
            json={"primary_route": "app"},
            timeout=10,
        )
        assert pa.status_code == 200, pa.text
        assert pa.json()["domain"]["primary_route"] == "app"

        # Public resolver should follow the new route
        hc3 = requests.get(f"{API}/public/host-config", params={"host": host}, timeout=10)
        assert hc3.status_code == 200
        cfg3 = hc3.json()
        assert cfg3["matched"] is True
        assert cfg3["primary_route"] == "app"
        # When route=app the path is /m/{slug} (no /join suffix).
        assert not cfg3["redirect_path"].endswith("/join")

    finally:
        # DELETE — always run, even if assertion above failed
        dl = requests.delete(
            f"{API}/master-admin/custom-domains/orgs/{org_id}/{domain_id}",
            headers=_h(token),
            timeout=10,
        )
        assert dl.status_code == 200, dl.text

    # Post-delete public resolver should fail to match
    hc4 = requests.get(f"{API}/public/host-config", params={"host": host}, timeout=10)
    assert hc4.status_code == 200
    assert hc4.json()["matched"] is False


# ── 4. Duplicate-hostname guard ─────────────────────────────────────


def test_create_rejects_duplicate_hostname_within_same_org():
    token = _master_token()
    org_id = _pick_org_id(token)
    host = _unique_host("dup")

    cr = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id}",
        headers=_h(token),
        json={"hostname": host, "primary_route": "join"},
        timeout=10,
    )
    assert cr.status_code == 200
    domain_id = cr.json()["domain"]["id"]
    try:
        dup = requests.post(
            f"{API}/master-admin/custom-domains/orgs/{org_id}",
            headers=_h(token),
            json={"hostname": host, "primary_route": "app"},
            timeout=10,
        )
        assert dup.status_code == 409
    finally:
        requests.delete(
            f"{API}/master-admin/custom-domains/orgs/{org_id}/{domain_id}",
            headers=_h(token),
            timeout=10,
        )


# ── 5. Auth gates ───────────────────────────────────────────────────


def test_management_endpoints_require_auth():
    org_id_fake = "00000000-0000-0000-0000-000000000000"
    r1 = requests.get(
        f"{API}/master-admin/custom-domains/orgs/{org_id_fake}",
        timeout=10,
    )
    assert r1.status_code in (401, 403)
    r2 = requests.post(
        f"{API}/master-admin/custom-domains/orgs/{org_id_fake}",
        json={"hostname": "test.example.com", "primary_route": "join"},
        timeout=10,
    )
    assert r2.status_code in (401, 403)


def test_public_host_config_is_public():
    """The host-config resolver MUST work without auth — the visitor
    has no token yet at this stage of the flow."""
    r = requests.get(
        f"{API}/public/host-config",
        params={"host": "nope-never-registered.example.com"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is False


def test_public_host_config_handles_bogus_host_gracefully():
    """Invalid host strings (with spaces / schemes) should not 500."""
    r = requests.get(
        f"{API}/public/host-config",
        params={"host": "not a real host"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is False
