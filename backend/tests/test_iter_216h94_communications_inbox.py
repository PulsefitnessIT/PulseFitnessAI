"""Regression tests for iter 216h94 + iter 216h95.

Covers:
  * Iter 216h94 — Public contact form with the extended payload, and
    the Master Admin Communications Inbox CRUD endpoints.
  * Iter 216h95 — Theme settings audit + per-tenant overrides.

These are smoke-level guards: they prove the endpoints exist, validate
the happy path and reject the obvious bad inputs. Deep email-dispatch
tests live under the email_health suite.
"""
from __future__ import annotations

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


# ── 216h94 — Contact form + Communications inbox ──────────────────────


def test_contact_form_accepts_extended_payload():
    """The public form keeps backwards compat AND captures new fields."""
    payload = {
        "name": "Regression Bot",
        "email": "regress+216h94@example.com",
        "company": "QA Gyms",
        "message": "Hello from the regression suite — pricing question.",
        "phone": "+44 7700 900000",
        "gym_size": "3-10",
        "interest": "memberships",
        "preferred_contact_time": "morning",
        "heard_from": "linkedin",
    }
    r = requests.post(f"{API}/contact", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("id")


def test_communications_inbox_summary_requires_auth():
    """Unauthenticated calls must 401, not 200 with public data."""
    r = requests.get(f"{API}/master-admin/communications/summary", timeout=10)
    assert r.status_code == 401


def test_communications_inbox_full_crud_happy_path():
    """List → fetch → patch → reply (best-effort email)."""
    token = _master_token()
    # Seed an enquiry first so the test never relies on demo data state.
    seed = requests.post(
        f"{API}/contact",
        json={
            "name": "Inbox CRUD Tester",
            "email": "regress+inbox@example.com",
            "company": "Inbox QA",
            "message": "Please ignore — regression seed.",
            "interest": "engineers",
        },
        timeout=15,
    )
    assert seed.status_code == 200, seed.text
    enquiry_id = seed.json()["id"]

    # Summary
    s = requests.get(
        f"{API}/master-admin/communications/summary",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert s.status_code == 200, s.text
    assert "by_status" in s.json()

    # List
    lst = requests.get(
        f"{API}/master-admin/communications?status=new",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert lst.status_code == 200, lst.text
    assert isinstance(lst.json().get("items"), list)

    # Detail (should also promote new → read)
    d = requests.get(
        f"{API}/master-admin/communications/{enquiry_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert d.status_code == 200, d.text
    detail = d.json()
    assert detail["id"] == enquiry_id
    assert detail["status"] == "read"

    # Patch — close it + add internal notes
    p = requests.patch(
        f"{API}/master-admin/communications/{enquiry_id}",
        headers=_h(token),
        json={"status": "closed", "internal_notes": "Closed by regression suite."},
        timeout=10,
    )
    assert p.status_code == 200, p.text


def test_communications_patch_rejects_unknown_status():
    token = _master_token()
    # Seed
    seed = requests.post(
        f"{API}/contact",
        json={"name": "Status Reject", "email": "reject@example.com", "message": "test ignore"},
        timeout=15,
    )
    eid = seed.json()["id"]
    r = requests.patch(
        f"{API}/master-admin/communications/{eid}",
        headers=_h(token),
        json={"status": "purgatory"},
        timeout=10,
    )
    assert r.status_code == 400


# ── 216h95 — Theme settings ───────────────────────────────────────────


def test_theme_audit_reports_isolation_ok():
    token = _master_token()
    r = requests.get(
        f"{API}/master-admin/theme/audit",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["overlap"] == []
    namespaces = body["namespaces"]
    assert {ns["id"] for ns in namespaces} == {"gymaxis", "pulse"}
    # Every namespace must declare at least 5 tokens — guards against
    # accidental data loss in the contract.
    for ns in namespaces:
        assert len(ns["tokens"]) >= 5


def test_theme_per_tenant_override_round_trip():
    token = _master_token()
    # Pick any org from the master-admin listing.
    listing = requests.get(
        f"{API}/master-admin/organizations",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    orgs = listing if isinstance(listing, list) else listing.get("organizations") or listing.get("items") or []
    assert orgs, "Expected at least one organisation in master-admin listing"
    org_id = orgs[0]["id"]

    # Save overrides
    save = requests.put(
        f"{API}/master-admin/theme/orgs/{org_id}",
        headers=_h(token),
        json={"primary": "#19CDFF", "accent": "#10B981"},
        timeout=10,
    )
    assert save.status_code == 200, save.text
    overrides = save.json()["theme_overrides"]
    assert overrides["primary"] == "#19CDFF"
    assert overrides["accent"] == "#10B981"

    # GET should return the same overrides
    g = requests.get(
        f"{API}/master-admin/theme/orgs/{org_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert g.status_code == 200, g.text
    assert g.json()["theme_overrides"]["primary"] == "#19CDFF"

    # Clear by passing empty strings
    clr = requests.put(
        f"{API}/master-admin/theme/orgs/{org_id}",
        headers=_h(token),
        json={"primary": "", "accent": ""},
        timeout=10,
    )
    assert clr.status_code == 200, clr.text
    assert clr.json()["theme_overrides"].get("primary") is None


def test_theme_override_rejects_non_hex():
    token = _master_token()
    listing = requests.get(
        f"{API}/master-admin/organizations",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    orgs = listing if isinstance(listing, list) else listing.get("organizations") or listing.get("items") or []
    org_id = orgs[0]["id"]
    r = requests.put(
        f"{API}/master-admin/theme/orgs/{org_id}",
        headers=_h(token),
        json={"primary": "not-a-colour"},
        timeout=10,
    )
    assert r.status_code == 400


def test_theme_routes_require_auth():
    r1 = requests.get(f"{API}/master-admin/theme/audit", timeout=10)
    assert r1.status_code == 401
    r2 = requests.get(f"{API}/master-admin/theme/orgs/00000000-0000-0000-0000-000000000000", timeout=10)
    assert r2.status_code == 401
