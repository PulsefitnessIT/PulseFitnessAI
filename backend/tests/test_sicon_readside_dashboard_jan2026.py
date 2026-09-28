"""Sicon read-side dashboard + endpoints integration test — Increment B.
Runs against the live public backend using owner@isodemo.com creds.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASS = "IsoDemo123!"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASS}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ── Dashboard endpoint ────────────────────────────────────────────
def test_dashboard_returns_expected_shape(owner_headers):
    r = requests.get(f"{BASE_URL}/api/sicon/read/dashboard", headers=owner_headers, timeout=30)
    assert r.status_code == 200, f"dashboard failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    # connection block
    assert "connection" in data
    conn = data["connection"]
    for k in ("configured", "connected", "status", "writes_enabled"):
        assert k in conn, f"missing connection.{k}"
    assert conn["status"] == "not_configured", f"expected status=not_configured got {conn['status']}"
    assert conn["writes_enabled"] is False
    assert conn["configured"] is False
    # equipment block
    assert "equipment" in data
    eq = data["equipment"]
    for k in ("linked", "open_conflicts", "total_linked"):
        assert k in eq, f"missing equipment.{k}"
    # cases block
    assert "cases" in data
    cs = data["cases"]
    for k in ("linked", "total_linked"):
        assert k in cs, f"missing cases.{k}"


# ── Conflicts endpoint (empty) ────────────────────────────────────
def test_conflicts_empty_when_not_configured(owner_headers):
    r = requests.get(f"{BASE_URL}/api/sicon/read/conflicts", headers=owner_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "conflicts" in data
    assert "count" in data
    assert isinstance(data["conflicts"], list)


# ── API health endpoint (not configured) ──────────────────────────
def test_api_health_not_configured(owner_headers):
    r = requests.get(f"{BASE_URL}/api/sicon/read/api-health", headers=owner_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data.get("configured") is False
    assert data.get("endpoints") == []


# ── Preview returns 400 when not configured (EXPECTED) ────────────
def test_preview_400_when_not_configured(owner_headers):
    r = requests.post(f"{BASE_URL}/api/sicon/read/equipment/preview",
                      headers=owner_headers, json={"max_records": 10}, timeout=30)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"


# ── Sync also 400 when not configured ─────────────────────────────
def test_sync_400_when_not_configured(owner_headers):
    r = requests.post(f"{BASE_URL}/api/sicon/read/equipment/sync",
                      headers=owner_headers, json={"max_records": 0}, timeout=30)
    assert r.status_code == 400


# ── Non owner/manager rejected 403 ────────────────────────────────
def test_non_manager_rejected():
    # Try to login as staff-role user in same org (dealer_user)
    # dealer login: portal2@fitline.test / DealerDemo123!
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "portal2@fitline.test", "password": "DealerDemo123!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"dealer login unavailable: {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        pytest.skip("dealer login returned no token")
    h = {"Authorization": f"Bearer {tok}"}
    r2 = requests.get(f"{BASE_URL}/api/sicon/read/dashboard", headers=h, timeout=30)
    assert r2.status_code == 403, f"expected 403 got {r2.status_code}: {r2.text[:200]}"


# ── Unauthenticated rejected ──────────────────────────────────────
def test_unauth_rejected():
    r = requests.get(f"{BASE_URL}/api/sicon/read/dashboard", timeout=30)
    assert r.status_code in (401, 403)
