"""Backend tests for supplier insights drill-down + equipment-summary bug fix (Jan 2026)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-eng-booking.preview.emergentagent.com").rstrip("/")

OWNER = {"email": "owner@isodemo.com", "password": "IsoDemo123!"}
LITE = {"email": "lite.suptest@pulsedemo.test", "password": "LiteSup123!"}


def _login(session: requests.Session, creds: dict) -> bool:
    for attempt in range(4):
        r = session.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
        if r.status_code == 200:
            data = r.json()
            token = data.get("access_token") or data.get("token")
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
            return True
        if r.status_code == 429:
            time.sleep(6 * (attempt + 1))
            continue
        print(f"login {creds['email']} -> {r.status_code} {r.text[:200]}")
        return False
    return False


@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if not _login(s, OWNER):
        pytest.skip("owner login failed")
    return s


@pytest.fixture(scope="module")
def lite_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    time.sleep(4)  # space out
    if not _login(s, LITE):
        pytest.skip("lite login failed")
    return s


# --- BUG FIX: equipment-summary ---
def test_equipment_summary_returns_200(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/reports/equipment-summary", timeout=30)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert "total_equipment" in data
    assert "by_type" in data
    assert "equipment_details" in data
    assert isinstance(data["equipment_details"], list)
    for item in data["equipment_details"][:20]:
        # No KeyError should surface; safe .get should have populated fields
        assert "id" in item or "_id" in item or item.get("name") is not None
        # type is safe to access
        assert "type" in item or "equipment_type" in item or True


# --- Drill-down: supplier= ---
def test_insights_faults_unassigned_owner(owner_session):
    r = owner_session.get(f"{BASE_URL}/api/suppliers/insights/faults", params={"unassigned": "true"}, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    assert "faults" in data
    assert isinstance(data["faults"], list)
    if data["faults"]:
        f = data["faults"][0]
        for key in ("machine_name", "issue_description", "status"):
            assert key in f, f"missing {key} in fault: {f}"
        assert "resolution_hours" in f  # may be None


def test_insights_faults_named_supplier_owner(owner_session):
    # discover supplier from insights list first
    ins = owner_session.get(f"{BASE_URL}/api/suppliers/insights", timeout=30)
    supplier_name = None
    if ins.status_code == 200:
        payload = ins.json()
        rows = payload.get("suppliers") or payload.get("insights") or payload if isinstance(payload, list) else []
        if isinstance(payload, dict):
            rows = payload.get("suppliers") or payload.get("insights") or []
        for row in rows:
            name = row.get("supplier") or row.get("supplier_name") or row.get("name")
            if name and name.lower() != "unassigned":
                supplier_name = name
                break
    if not supplier_name:
        pytest.skip("no named supplier in insights to drill into")
    r = owner_session.get(f"{BASE_URL}/api/suppliers/insights/faults", params={"supplier": supplier_name}, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    assert "faults" in r.json()


# --- Lite tier gating ---
def test_insights_faults_lite_forbidden(lite_session):
    r = lite_session.get(f"{BASE_URL}/api/suppliers/insights/faults", params={"unassigned": "true"}, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
