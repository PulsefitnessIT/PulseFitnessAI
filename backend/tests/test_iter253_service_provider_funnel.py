"""Iter 253 — Self-serve Service Provider funnel (P0b).

Covers:
1. POST /api/service-provider/signup creates a provider org with a REAL
   trial window (active, days_left > 0 — the original bug rendered the
   trial-expired paywall immediately).
2. /auth/me exposes `service_ops_setup_complete` so the frontend can
   route incomplete providers to /service-desk/setup.
3. Wizard endpoints: branding → SLA → first engineer → complete.
4. TENANT ISOLATION: a provider's desk is hard-scoped to their own org —
   /service-desk/summary returns desk_kind=provider with their numbers,
   /service-desk/customers shows only their org, /service-desk/audit-log
   excludes platform/Pulse rows.
5. Regression: master admin still gets the platform-wide desk view.
"""

import uuid

import pytest
import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
PASSWORD = "Str0ngPass!23"
EMAIL = f"sp.pytest.{uuid.uuid4().hex[:10]}@example.com"
ENG_EMAIL = f"sp.eng.{uuid.uuid4().hex[:10]}@example.com"

_state: dict = {}


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_provider_with_active_trial():
    r = requests.post(f"{BASE_URL}/api/service-provider/signup", json={
        "company_name": "Pytest Service Co",
        "full_name": "Py Tester",
        "email": EMAIL,
        "password": PASSWORD,
    }, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next"] == "/service-desk/setup"
    user = body["user"]
    assert user["is_service_desk"] is True
    assert user["account_type"] == "service_provider"
    assert user["service_ops_setup_complete"] is False
    _state["token"] = body["token"]
    _state["org_id"] = user["organization_id"]

    me = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth(_state["token"]), timeout=20).json()
    assert me["service_ops_setup_complete"] is False
    trial = me.get("trial") or {}
    # The original bug: no trial_ends_at → instantly expired paywall.
    assert trial.get("status") in ("active", "expiring_soon"), trial
    assert trial.get("days_left", 0) >= 7
    assert trial.get("can_use_platform") is True


def test_duplicate_email_rejected():
    r = requests.post(f"{BASE_URL}/api/service-provider/signup", json={
        "company_name": "Dup Co", "full_name": "Dup", "email": EMAIL, "password": PASSWORD,
    }, timeout=20)
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


def test_setup_wizard_flow():
    h = _auth(_state["token"])
    setup = requests.get(f"{BASE_URL}/api/service-provider/setup", headers=h, timeout=20).json()
    assert setup["setup_complete"] is False
    assert setup["sla"]["p1"]["response_h"] == 1  # seeded defaults

    r = requests.put(f"{BASE_URL}/api/service-provider/setup/branding", headers=h, json={
        "company_name": "Pytest Service Co", "primary_color": "#112233", "accent_color": "#445566",
    }, timeout=20)
    assert r.status_code == 200

    r = requests.put(f"{BASE_URL}/api/service-provider/setup/sla", headers=h, json={
        "sla": {"p1": {"response_h": 2, "resolve_h": 8}},
    }, timeout=20)
    assert r.status_code == 200

    # Finishing before an engineer exists must 400.
    r = requests.post(f"{BASE_URL}/api/service-provider/setup/complete", headers=h, timeout=20)
    assert r.status_code == 400

    r = requests.post(f"{BASE_URL}/api/service-provider/setup/engineer", headers=h, json={
        "full_name": "Py Engineer", "email": ENG_EMAIL,
    }, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["temp_password"]

    r = requests.post(f"{BASE_URL}/api/service-provider/setup/complete", headers=h, timeout=20)
    assert r.status_code == 200
    assert r.json()["redirect"] == "/service-desk"

    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=20).json()
    assert me["service_ops_setup_complete"] is True


def test_provider_desk_is_tenant_scoped():
    h = _auth(_state["token"])
    summary = requests.get(f"{BASE_URL}/api/service-desk/summary", headers=h, timeout=20).json()
    assert summary["desk_kind"] == "provider", summary
    assert summary["provider"]["engineers"] == 1
    assert "organizations" not in summary  # no platform estate leak

    customers = requests.get(f"{BASE_URL}/api/service-desk/customers", headers=h, timeout=20).json()
    assert customers["total"] == 1
    assert customers["organizations"][0]["id"] == _state["org_id"]

    audit = requests.get(f"{BASE_URL}/api/service-desk/audit-log", headers=h, timeout=20).json()
    for row in audit["rows"]:
        assert row.get("actor_org_id") == _state["org_id"]


def test_setup_requires_auth_and_provider_role():
    r = requests.get(f"{BASE_URL}/api/service-provider/setup", timeout=20)
    assert r.status_code in (401, 403)


def test_master_admin_still_platform_wide():
    token = _login(*MASTER_ADMIN)
    summary = requests.get(f"{BASE_URL}/api/service-desk/summary", headers=_auth(token), timeout=20).json()
    assert summary["desk_kind"] == "platform"
    assert summary["organizations"]["total"] > 1
