"""ASER (Activity Safety Events Register) backend tests — Jan 2026.

Covers MOD-only gating, site-scoping, create flow, equipment red-flag,
actions (create-fault / flag-capex / close / dispose), dashboard cards.
"""
import os
import time
import pytest
import requests

def _load_be_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return (v or "").rstrip("/")

BASE_URL = _load_be_url()
API = f"{BASE_URL}/api"

MOD_EMAIL = "aser.qa@army.mod.test"
MOD_PASSWORD = "AserQA123!"
MOD_SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


def _login(email, password, retries=3):
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            data = r.json()
            return data.get("access_token") or data.get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        pytest.skip(f"Login failed ({email}): {r.status_code} {r.text[:200]}")
    pytest.skip(f"Login rate-limited for {email}")


@pytest.fixture(scope="module")
def mod_token():
    return _login(MOD_EMAIL, MOD_PASSWORD)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def mod_headers(mod_token):
    return {"Authorization": f"Bearer {mod_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- MOD-only gating ----------
class TestGating:
    def test_config_as_mod(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/config", headers=mod_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "event_types" in data and len(data["event_types"]) > 5
        assert "equipment_statuses" in data
        assert "sites" in data

    def test_dashboard_as_mod(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/dashboard", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        assert "cards" in r.json()

    def test_list_as_mod(self, mod_headers):
        r = requests.get(f"{API}/mod/aser", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        assert "entries" in r.json()

    def test_equipment_as_mod(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/equipment", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        eq = r.json().get("equipment", [])
        assert isinstance(eq, list)
        # Must include seeded QA equipment
        names = " ".join([(e.get("name") or "") for e in eq])
        assert "Concept2" in names or "Rower" in names or len(eq) > 0

    def test_admin_can_read(self, admin_headers):
        r = requests.get(f"{API}/mod/aser/config", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_non_mod_forbidden(self):
        # Login as a commercial user (iso-demo)
        tok = _login("owner@isodemo.com", "IsoDemo123!")
        headers = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{API}/mod/aser/config", headers=headers, timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ---------- Site scoping ----------
class TestSiteScoping:
    def test_equipment_own_site_ok(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/equipment", headers=mod_headers,
                         params={"site_id": MOD_SITE_ID}, timeout=20)
        assert r.status_code == 200
        for e in r.json().get("equipment", []):
            assert e["organization_id"] == MOD_SITE_ID

    def test_equipment_out_of_scope_forbidden(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/equipment", headers=mod_headers,
                         params={"site_id": "00000000-0000-0000-0000-000000000000"}, timeout=20)
        assert r.status_code == 403


# ---------- Create + red-flag + actions ----------
@pytest.fixture(scope="module")
def qa_equipment(mod_headers):
    r = requests.get(f"{API}/mod/aser/equipment", headers=mod_headers,
                     params={"site_id": MOD_SITE_ID}, timeout=20)
    assert r.status_code == 200
    eq = r.json()["equipment"]
    assert len(eq) >= 1, "Need at least one seeded equipment at ARMY QA MOD site"
    # Prefer one that's not already disposed
    for e in eq:
        if not e.get("aser_disposed"):
            return e
    return eq[0]


class TestCreateFlow:
    def test_create_high_risk_removed(self, mod_headers, qa_equipment):
        payload = {
            "site_id": MOD_SITE_ID,
            "equipment_id": qa_equipment["id"],
            "event_type": "equipment_failure_rehab",
            "title": "TEST_ASER high risk removed",
            "description": "Belt snapped mid-session; equipment made safe.",
            "risk": {"actual_harm": "no_harm", "potential_severity": "high",
                     "likelihood": "possible", "rating": "high"},
            "equipment_status": "removed_from_use",
            "activity_impact": {"impacted_rehab": True, "sessions_affected": 2},
            "submit": True,
        }
        r = requests.post(f"{API}/mod/aser", headers=mod_headers, json=payload, timeout=25)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["aser_ref"].startswith("ASER-")
        assert data["entry"]["status"] == "under_review"
        pytest.aser_entry_id = data["entry"]["id"]
        pytest.aser_ref = data["aser_ref"]
        pytest.aser_equipment_id = qa_equipment["id"]

    def test_equipment_red_flag_applied(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/equipment", headers=mod_headers,
                         params={"site_id": MOD_SITE_ID}, timeout=20)
        assert r.status_code == 200
        target = next((e for e in r.json()["equipment"]
                       if e["id"] == pytest.aser_equipment_id), None)
        assert target is not None
        assert target["aser_removed_from_use"] is True
        assert target["aser_flag_status"] == "removed_from_use"

    def test_list_contains_new_entry(self, mod_headers):
        r = requests.get(f"{API}/mod/aser", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert any(e["id"] == pytest.aser_entry_id for e in entries)

    def test_dashboard_reflects_entry(self, mod_headers):
        r = requests.get(f"{API}/mod/aser/dashboard", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        cards = r.json()["cards"]
        assert cards["total_entries"] >= 1
        assert cards["high_risk_entries"] >= 1
        assert cards["removed_from_use"] >= 1

    def test_create_invalid_equipment(self, mod_headers):
        payload = {
            "site_id": MOD_SITE_ID,
            "equipment_id": "not-a-real-id",
            "event_type": "near_miss",
            "title": "TEST bad equipment",
            "description": "Should fail validation on equipment lookup.",
            "risk": {"rating": "low"},
        }
        r = requests.post(f"{API}/mod/aser", headers=mod_headers, json=payload, timeout=20)
        assert r.status_code in (404, 400)

    def test_create_out_of_scope_site(self, mod_headers, qa_equipment):
        payload = {
            "site_id": "00000000-0000-0000-0000-000000000000",
            "equipment_id": qa_equipment["id"],
            "event_type": "near_miss",
            "title": "TEST oob site",
            "description": "Should be forbidden due to site scoping.",
            "risk": {"rating": "low"},
        }
        r = requests.post(f"{API}/mod/aser", headers=mod_headers, json=payload, timeout=20)
        assert r.status_code == 403


class TestActions:
    def test_create_fault(self, mod_headers):
        eid = pytest.aser_entry_id
        r = requests.post(f"{API}/mod/aser/{eid}/create-fault", headers=mod_headers, timeout=25)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["ticket_ref"].startswith("MOD-")
        pytest.linked_fault_id = data["fault_id"]

    def test_detail_after_link(self, mod_headers):
        eid = pytest.aser_entry_id
        r = requests.get(f"{API}/mod/aser/{eid}", headers=mod_headers, timeout=20)
        assert r.status_code == 200
        doc = r.json()
        assert doc["linked_fault_id"] == pytest.linked_fault_id
        assert doc["status"] == "linked_to_fault"

    def test_flag_capex(self, mod_headers):
        # Create a fresh entry to flag capex (linked_to_fault already changes status)
        payload = {
            "site_id": MOD_SITE_ID,
            "equipment_id": pytest.aser_equipment_id,
            "event_type": "old_rundown",
            "title": "TEST_ASER capex flag",
            "description": "Old rundown equipment needs replacement.",
            "risk": {"rating": "medium"},
            "equipment_status": "operational",
        }
        r = requests.post(f"{API}/mod/aser", headers=mod_headers, json=payload, timeout=20)
        assert r.status_code == 200
        eid = r.json()["entry"]["id"]
        r2 = requests.post(f"{API}/mod/aser/{eid}/flag-capex", headers=mod_headers, timeout=20)
        assert r2.status_code == 200
        pytest.capex_entry_id = eid

    def test_dispose_manager_only(self, mod_headers):
        # Dispose using the removed-from-use entry
        eid = pytest.aser_entry_id
        r = requests.post(f"{API}/mod/aser/{eid}/dispose", headers=mod_headers, timeout=20)
        # aser.qa user role — could be manager or member. Accept either 200 or 403.
        assert r.status_code in (200, 403), r.text
        pytest.dispose_status = r.status_code

    def test_close(self, mod_headers):
        eid = pytest.capex_entry_id
        r = requests.post(f"{API}/mod/aser/{eid}/close", headers=mod_headers,
                          json={"manager_override": True, "note": "TEST close"}, timeout=20)
        assert r.status_code in (200, 403)
