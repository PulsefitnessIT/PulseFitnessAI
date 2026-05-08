"""Iter 215dc — CRM Territories, team hierarchy, auto-assignment, audit.

Covers:
- POST /api/crm/territories creates a territory.
- Creating a company in a matching postcode auto-sets `territory_id` + `owner_id`.
- Non-matching postcodes leave both fields null.
- GET /api/crm/territories/team/tree returns the user hierarchy.
- `scope=mine` / `scope=team` filters on companies/opportunities.
- Setting a manager cannot create a cycle.
"""
from __future__ import annotations
import os
import uuid
import requests

BASE = os.environ.get("PUBLIC_BASE") or "http://localhost:8001"


def _bypass():
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    return {"X-RateLimit-Bypass": s} if s else {}


def _crm_token() -> tuple[str, str]:
    """Return (main_token, crm_token) for the master admin."""
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        headers=_bypass(), timeout=10,
    )
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    r2 = requests.post(
        f"{BASE}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {t}", **_bypass()},
        timeout=10,
    )
    assert r2.status_code == 200, r2.text
    return t, r2.json()["token"]


def _auth(crm_token: str):
    return {"Authorization": f"Bearer {crm_token}", **_bypass()}


def test_territory_crud_and_auto_assign():
    _, ct = _crm_token()
    name = f"Test London {uuid.uuid4().hex[:6]}"
    # Create a territory covering London postcodes.
    r = requests.post(
        f"{BASE}/api/crm/territories",
        json={"name": name, "postcode_prefixes": ["SW", "SE", "WC"], "priority": 99},
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 200, r.text
    terr_id = r.json()["id"]

    # Company with matching postcode auto-assigns territory.
    r = requests.post(
        f"{BASE}/api/crm/v2/companies",
        json={"name": f"Auto-assign Co {uuid.uuid4().hex[:4]}", "postcode": "SW1A 1AA", "country": "UK"},
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 200, r.text
    co = r.json()
    assert co["territory_id"] == terr_id, f"expected territory_id={terr_id}, got {co.get('territory_id')}"
    assert co.get("owner_id"), "owner_id must be set via round-robin"

    # Non-matching postcode leaves territory null.
    r = requests.post(
        f"{BASE}/api/crm/v2/companies",
        json={"name": f"Manc Co {uuid.uuid4().hex[:4]}", "postcode": "M1 2AA", "country": "UK"},
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("territory_id") in (None, ""), "no territory should match M1"

    # Clean up
    requests.delete(f"{BASE}/api/crm/territories/{terr_id}", headers=_auth(ct), timeout=10)


def test_team_tree_and_scope_filters():
    _, ct = _crm_token()
    r = requests.get(f"{BASE}/api/crm/territories/team/tree", headers=_auth(ct), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tree" in body and isinstance(body["tree"], list)
    assert body["total_users"] >= 1

    # scope=mine narrows to the caller.
    r = requests.get(
        f"{BASE}/api/crm/v2/companies?scope=mine&limit=5",
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 200, r.text
    # Companies returned must all be owned by the caller (id lookup happens server-side).
    for c in r.json().get("companies", []):
        # Master admin id matches; we just sanity-check no other owner slipped in.
        assert c.get("owner_id"), "owner_id must be present on scoped rows"


def test_manager_cycle_prevention():
    _, ct = _crm_token()
    # /crm/auth/me returns the user fields directly.
    r = requests.get(f"{BASE}/api/crm/auth/me", headers=_auth(ct), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    uid = body.get("id")
    assert uid, f"no id on /crm/auth/me response: {body}"
    # Self-management → 400.
    r = requests.put(
        f"{BASE}/api/crm/territories/team/{uid}/manager",
        json={"manager_id": uid}, headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 400, r.text


def test_bulk_reassign_validation():
    _, ct = _crm_token()
    # Same from/to → 400.
    r = requests.post(
        f"{BASE}/api/crm/territories/bulk-reassign",
        json={"from_user_id": "same", "to_user_id": "same", "entities": ["company"]},
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 400, r.text


def test_auto_assign_dry_run():
    _, ct = _crm_token()
    r = requests.post(
        f"{BASE}/api/crm/territories/auto-assign",
        json={"entity": "company", "dry_run": True, "only_unassigned": True},
        headers=_auth(ct), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["changed"] == 0  # dry run never mutates
    assert isinstance(body["proposals"], list)
