"""Phase 6 — Dealer Service Desks endpoint tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def dealer(client):
    """Find or create a dealer CRM company via inventory dealer directory."""
    r = client.get(f"{BASE_URL}/api/inventory/dealers", timeout=30)
    assert r.status_code == 200, r.text
    dealers = r.json().get("dealers", [])
    if not dealers:
        pytest.skip("No dealers available")
    return dealers[0]


class TestPhase6Reachability:
    def test_summary_reachable(self, client):
        r = client.get(f"{BASE_URL}/api/inventory/svc/summary", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ["service_desks", "active_desks", "dealer_faults", "open_dealer_faults"]:
            assert k in j, f"Missing key {k} in summary: {j}"

    def test_desks_list_reachable(self, client):
        r = client.get(f"{BASE_URL}/api/inventory/svc/desks", timeout=30)
        assert r.status_code == 200, r.text
        assert "desks" in r.json()

    def test_route_default_pulse(self, client):
        r = client.get(f"{BASE_URL}/api/inventory/svc/route?serial=NO-SUCH-SERIAL-XYZ", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["responsible"] == "pulse"
        assert "reason" in j


class TestPhase6DeskLifecycle:
    desk_id = None
    dealer_id = None

    def test_create_desk(self, client, dealer):
        # First cleanup any existing desk for this dealer to avoid dupe conflict
        r = client.get(f"{BASE_URL}/api/inventory/svc/desks", timeout=30)
        existing = [d for d in r.json().get("desks", []) if d.get("dealer_id") == dealer["id"]]
        if existing:
            # can't delete via API, just use another dealer or accept
            TestPhase6DeskLifecycle.desk_id = existing[0]["id"]
            TestPhase6DeskLifecycle.dealer_id = dealer["id"]
            pytest.skip(f"Desk already exists for dealer {dealer['id']} — reusing for downstream tests")

        payload = {
            "dealer_id": dealer["id"],
            "dealer_name": dealer.get("name"),
            "country": "GB",
            "coverage": {"languages": ["en"]},
            "service_rules": {"sla": "next_business_day", "warranty_routing": "dealer"},
        }
        r = client.post(f"{BASE_URL}/api/inventory/svc/desks", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["dealer_id"] == dealer["id"]
        assert doc["status"] == "draft"
        assert doc["reference"].startswith("DSD-")
        TestPhase6DeskLifecycle.desk_id = doc["id"]
        TestPhase6DeskLifecycle.dealer_id = dealer["id"]

    def test_duplicate_desk_409(self, client):
        assert TestPhase6DeskLifecycle.dealer_id, "prereq missing"
        payload = {"dealer_id": TestPhase6DeskLifecycle.dealer_id, "country": "GB"}
        r = client.post(f"{BASE_URL}/api/inventory/svc/desks", json=payload, timeout=30)
        assert r.status_code == 409, f"expected 409 duplicate, got {r.status_code}: {r.text}"
        # error message must indicate duplicate
        body = r.json()
        detail = body.get("detail")
        assert (isinstance(detail, dict) and detail.get("error") == "duplicate_desk") or "duplicate" in str(body).lower()

    def test_activate_desk(self, client):
        assert TestPhase6DeskLifecycle.desk_id, "prereq missing"
        r = client.post(f"{BASE_URL}/api/inventory/svc/desks/{TestPhase6DeskLifecycle.desk_id}/activate", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "active"
        # Verify persistence
        r2 = client.get(f"{BASE_URL}/api/inventory/svc/desks/{TestPhase6DeskLifecycle.desk_id}", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["desk"]["status"] == "active"

    def test_get_desk_detail(self, client):
        assert TestPhase6DeskLifecycle.desk_id
        r = client.get(f"{BASE_URL}/api/inventory/svc/desks/{TestPhase6DeskLifecycle.desk_id}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ["desk", "customers", "assets", "faults", "stats"]:
            assert k in j

    def test_warranty_parts(self, client):
        assert TestPhase6DeskLifecycle.dealer_id
        r = client.get(f"{BASE_URL}/api/inventory/svc/warranty-parts?dealer_id={TestPhase6DeskLifecycle.dealer_id}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "recommendations" in j
        assert j["dealer_id"] == TestPhase6DeskLifecycle.dealer_id

    def test_log_fault_and_escalate(self, client):
        """Log a fault against an arbitrary serial (routes to Pulse by default when no alloc).
        Then escalate. Verify same record."""
        payload = {"serial_number": "PHASE6-TEST-SN-001", "title": "Phase6 test fault", "severity": "medium"}
        r = client.post(f"{BASE_URL}/api/inventory/svc/faults", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "fault" in j and "routing" in j
        fault_id = j["fault"]["id"]
        assert j["fault"]["serial_number"] == "PHASE6-TEST-SN-001"
        # Route without alloc → responsible=pulse
        assert j["routing"]["responsible"] == "pulse"

        # Escalate
        r2 = client.post(f"{BASE_URL}/api/inventory/svc/faults/{fault_id}/escalate", timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.json()["responsible"] == "pulse"

    def test_escalate_missing_fault_404(self, client):
        r = client.post(f"{BASE_URL}/api/inventory/svc/faults/nonexistent-id/escalate", timeout=30)
        assert r.status_code == 404


class TestPhase6Regression:
    def test_dashboard_summary(self, client):
        r = client.get(f"{BASE_URL}/api/inventory/svc/summary", timeout=30)
        assert r.status_code == 200

    def test_allocations_list(self, client):
        r = client.get(f"{BASE_URL}/api/inventory/allocations", timeout=30)
        assert r.status_code in (200, 404)
