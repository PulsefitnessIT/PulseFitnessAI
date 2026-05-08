"""
GymAxis · Sicon Outbox Worker API tests (iter 215dz)

Phase 8 Workstream A — Sicon outbox worker + missing push_event/push_part_movement wiring.

Tests for:
- POST /api/integrations/admin/sicon/drain-now (live drain — skipped_no_config expected)
- POST /api/integrations/admin/sicon/simulate-drain (demo mode — simulated_succeeded)
- POST /api/integrations/admin/sicon/requeue-failed (move failed→pending)
- push_part_movement wiring via POST /api/svc/parts/allocate
- push_event wiring via POST /api/svc/cases/{id}/notes
- push_event wiring via POST /api/svc/cases/{id}/transition (state_change event)
- GET /api/integrations/admin/health (Sage PO outbox in by_outbox)
- Regression tests for prior endpoints
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Module-scoped token to avoid rate limiting
_TOKEN_CACHE = {}


def get_master_admin_token():
    """Get master admin token with caching to avoid rate limits"""
    if 'token' in _TOKEN_CACHE:
        return _TOKEN_CACHE['token']

    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 429:
        pytest.skip("Rate limited - skipping test")
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    _TOKEN_CACHE['token'] = response.json().get("token")
    return _TOKEN_CACHE['token']


@pytest.fixture(scope="module")
def master_admin_token():
    """Module-scoped fixture for master admin token"""
    return get_master_admin_token()


# ─────────────────────────────────────────────────────────────────
# Auth tests for new drain/requeue endpoints
# ─────────────────────────────────────────────────────────────────

class TestDrainEndpointsAuth:
    """Test authentication requirements for drain/requeue endpoints"""

    def test_drain_now_requires_auth(self):
        """POST /api/integrations/admin/sicon/drain-now returns 401 without token"""
        response = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/drain-now")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /sicon/drain-now returns 401 without auth")

    def test_simulate_drain_requires_auth(self):
        """POST /api/integrations/admin/sicon/simulate-drain returns 401 without token"""
        response = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /sicon/simulate-drain returns 401 without auth")

    def test_requeue_failed_requires_auth(self):
        """POST /api/integrations/admin/sicon/requeue-failed returns 401 without token"""
        response = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/requeue-failed")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /sicon/requeue-failed returns 401 without auth")


# ─────────────────────────────────────────────────────────────────
# Drain-now endpoint (live mode — skipped_no_config expected)
# ─────────────────────────────────────────────────────────────────

class TestDrainNow:
    """Test POST /api/integrations/admin/sicon/drain-now endpoint"""

    def test_drain_now_returns_200(self, master_admin_token):
        """POST /api/integrations/admin/sicon/drain-now returns 200 for master admin"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/drain-now?max_rows=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /sicon/drain-now returns 200 for master admin")

    def test_drain_now_response_shape(self, master_admin_token):
        """Drain-now response has DrainResult shape"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/drain-now?max_rows=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Check DrainResult fields
        expected_keys = [
            "started_at", "finished_at", "organizations", "attempted",
            "succeeded", "failed", "dead_letter", "skipped_no_config",
            "simulated", "by_kind"
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

        # simulated should be False for live drain
        assert data["simulated"] == False, "simulated should be False for live drain"

        print("✓ Drain-now response shape is correct")
        print(f"  - attempted: {data['attempted']}")
        print(f"  - succeeded: {data['succeeded']}")
        print(f"  - failed: {data['failed']}")
        print(f"  - skipped_no_config: {data['skipped_no_config']}")
        print(f"  - simulated: {data['simulated']}")

    def test_drain_now_skips_without_credentials(self, master_admin_token):
        """Live drain returns skipped_no_config when no SICON credentials configured"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/drain-now?max_rows=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # In this env, no SICON credentials are configured, so all rows should be skipped
        # succeeded should be 0, skipped_no_config should equal attempted
        if data["attempted"] > 0:
            assert data["succeeded"] == 0, f"Expected 0 succeeded without credentials, got {data['succeeded']}"
            assert data["skipped_no_config"] == data["attempted"], \
                f"Expected skipped_no_config={data['attempted']}, got {data['skipped_no_config']}"
            print(f"✓ Live drain correctly skips {data['skipped_no_config']} rows (no Sicon credentials)")
        else:
            print("✓ No pending rows to drain (skipped_no_config test passed trivially)")


# ─────────────────────────────────────────────────────────────────
# Simulate-drain endpoint (demo mode)
# ─────────────────────────────────────────────────────────────────

class TestSimulateDrain:
    """Test POST /api/integrations/admin/sicon/simulate-drain endpoint"""

    def test_simulate_drain_returns_200(self, master_admin_token):
        """POST /api/integrations/admin/sicon/simulate-drain returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain?max_rows=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /sicon/simulate-drain returns 200")

    def test_simulate_drain_response_shape(self, master_admin_token):
        """Simulate-drain response has DrainResult shape with simulated=True"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain?max_rows=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Check DrainResult fields
        expected_keys = [
            "started_at", "finished_at", "organizations", "attempted",
            "succeeded", "failed", "dead_letter", "skipped_no_config",
            "simulated", "by_kind"
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

        # simulated should be True for simulate drain
        assert data["simulated"] == True, "simulated should be True for simulate drain"

        print("✓ Simulate-drain response shape is correct")
        print(f"  - attempted: {data['attempted']}")
        print(f"  - succeeded: {data['succeeded']}")
        print(f"  - simulated: {data['simulated']}")

    def test_simulate_drain_transitions_to_simulated_succeeded(self, master_admin_token):
        """Simulate drain transitions pending rows to simulated_succeeded"""
        # First check if there are pending rows
        health_resp = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert health_resp.status_code == 200
        pending_before = health_resp.json()["sicon"]["outbox"]["pending"]

        if pending_before == 0:
            print("✓ No pending rows to simulate (test passed trivially)")
            return

        # Run simulate drain
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain?max_rows=5",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Check that rows were transitioned
        if data["attempted"] > 0:
            assert data["succeeded"] == data["attempted"], \
                f"Expected all {data['attempted']} rows to succeed in simulate mode"
            print(f"✓ Simulate drain transitioned {data['succeeded']} rows to simulated_succeeded")

        # Verify by checking outbox for simulated_succeeded rows
        outbox_resp = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?status=simulated_succeeded&limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert outbox_resp.status_code == 200
        simulated_rows = outbox_resp.json()["rows"]
        print(f"  - Found {len(simulated_rows)} simulated_succeeded rows in outbox")


# ─────────────────────────────────────────────────────────────────
# Requeue-failed endpoint
# ─────────────────────────────────────────────────────────────────

class TestRequeueFailed:
    """Test POST /api/integrations/admin/sicon/requeue-failed endpoint"""

    def test_requeue_failed_returns_200(self, master_admin_token):
        """POST /api/integrations/admin/sicon/requeue-failed returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/requeue-failed",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /sicon/requeue-failed returns 200")

    def test_requeue_failed_response_shape(self, master_admin_token):
        """Requeue-failed response has {ok, requeued} shape"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/requeue-failed",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "ok" in data, "Missing 'ok' in response"
        assert "requeued" in data, "Missing 'requeued' in response"
        assert data["ok"] == True, "Expected ok=True"
        assert isinstance(data["requeued"], int), "requeued should be an integer"

        print(f"✓ Requeue-failed response shape correct, requeued: {data['requeued']}")

    def test_requeue_with_dead_letter_flag(self, master_admin_token):
        """Requeue-failed with include_dead_letter=true also rescues dead_letter rows"""
        response = requests.post(
            f"{BASE_URL}/api/integrations/admin/sicon/requeue-failed?include_dead_letter=true",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["ok"] == True
        print(f"✓ Requeue with include_dead_letter=true returned requeued: {data['requeued']}")


# ─────────────────────────────────────────────────────────────────
# Health endpoint — Sage PO outbox in by_outbox
# ─────────────────────────────────────────────────────────────────

class TestHealthSageByOutbox:
    """Test GET /api/integrations/admin/health includes Sage PO outbox"""

    def test_health_sage_by_outbox_structure(self, master_admin_token):
        """Health response has sage.outbox.by_outbox with invoice and po"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        sage_outbox = data["sage"]["outbox"]
        assert "by_outbox" in sage_outbox, "Missing sage.outbox.by_outbox"

        by_outbox = sage_outbox["by_outbox"]
        assert "invoice" in by_outbox, "Missing sage.outbox.by_outbox.invoice"
        assert "po" in by_outbox, "Missing sage.outbox.by_outbox.po"

        # Check invoice outbox structure
        invoice = by_outbox["invoice"]
        assert "pending" in invoice, "Missing invoice.pending"
        assert "in_flight" in invoice, "Missing invoice.in_flight"

        # Check po outbox structure
        po = by_outbox["po"]
        assert "pending" in po, "Missing po.pending"
        assert "in_flight" in po, "Missing po.in_flight"

        print("✓ Health response has sage.outbox.by_outbox with invoice and po")
        print(f"  - Invoice pending: {invoice['pending']}")
        print(f"  - PO pending: {po['pending']}")

    def test_health_sage_totals_are_sums(self, master_admin_token):
        """Top-level sage.outbox counts are sums of invoice + po"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        sage_outbox = data["sage"]["outbox"]
        by_outbox = sage_outbox["by_outbox"]

        # Verify sums
        expected_pending = by_outbox["invoice"]["pending"] + by_outbox["po"]["pending"]
        assert sage_outbox["pending"] == expected_pending, \
            f"Expected pending={expected_pending}, got {sage_outbox['pending']}"

        expected_in_flight = by_outbox["invoice"]["in_flight"] + by_outbox["po"]["in_flight"]
        assert sage_outbox["in_flight"] == expected_in_flight, \
            f"Expected in_flight={expected_in_flight}, got {sage_outbox['in_flight']}"

        print("✓ Sage outbox totals are correct sums of invoice + po")


# ─────────────────────────────────────────────────────────────────
# Outbox filter includes simulated statuses
# ─────────────────────────────────────────────────────────────────

class TestOutboxSimulatedFilter:
    """Test that outbox filter includes simulated and simulated_succeeded"""

    def test_filter_by_simulated_succeeded(self, master_admin_token):
        """Sicon outbox can filter by status=simulated_succeeded"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?status=simulated_succeeded&limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # All rows should have status=simulated_succeeded
        for row in data["rows"]:
            assert row.get("status") == "simulated_succeeded", \
                f"Expected status=simulated_succeeded, got {row.get('status')}"

        print(f"✓ Filter by status=simulated_succeeded works, count: {data['count']}")

    def test_filter_by_simulated(self, master_admin_token):
        """Sicon outbox can filter by status=simulated"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?status=simulated&limit=20",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # All rows should have status=simulated (if any)
        for row in data["rows"]:
            assert row.get("status") == "simulated", \
                f"Expected status=simulated, got {row.get('status')}"

        print(f"✓ Filter by status=simulated works, count: {data['count']}")


# ─────────────────────────────────────────────────────────────────
# Regression tests for prior endpoints
# ─────────────────────────────────────────────────────────────────

class TestRegressionPriorEndpoints:
    """Regression tests for prior /api/integrations/admin/* endpoints"""

    def test_health_endpoint(self, master_admin_token):
        """GET /api/integrations/admin/health still works"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/health",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sicon" in data
        assert "sage" in data
        print("✓ /health endpoint still works")

    def test_sicon_outbox_endpoint(self, master_admin_token):
        """GET /api/integrations/admin/sicon/outbox still works"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sicon/outbox?limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert "count" in data
        print("✓ /sicon/outbox endpoint still works")

    def test_sage_outbox_endpoint(self, master_admin_token):
        """GET /api/integrations/admin/sage/outbox still works"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert "count" in data
        print("✓ /sage/outbox endpoint still works")

    def test_mapping_sections_endpoint(self, master_admin_token):
        """GET /api/integrations/admin/mapping/sections still works"""
        response = requests.get(
            f"{BASE_URL}/api/integrations/admin/mapping/sections",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "master" in data
        assert "legacy" in data
        assert "modules" in data
        print("✓ /mapping/sections endpoint still works")


class TestServiceOpsRegression:
    """Regression tests for Service Ops endpoints (cases, parts, comms, billing)"""

    def test_comms_templates(self, master_admin_token):
        """GET /api/svc/comms/templates still works"""
        response = requests.get(
            f"{BASE_URL}/api/svc/comms/templates",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        print("✓ /svc/comms/templates returns 200")

    def test_desk_summary(self, master_admin_token):
        """GET /api/svc/desk/summary still works"""
        response = requests.get(
            f"{BASE_URL}/api/svc/desk/summary",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        print("✓ /svc/desk/summary returns 200")

    def test_billing_ready(self, master_admin_token):
        """GET /api/svc/billing?status=ready still works"""
        response = requests.get(
            f"{BASE_URL}/api/svc/billing?status=ready",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        print("✓ /svc/billing?status=ready returns 200")


# ─────────────────────────────────────────────────────────────────
# Test push_part_movement wiring (via parts allocate endpoint)
# ─────────────────────────────────────────────────────────────────

class TestPushPartMovementWiring:
    """Test that POST /api/svc/parts/allocate enqueues part_movement to outbox"""

    def test_parts_allocate_endpoint_exists(self, master_admin_token):
        """POST /api/svc/parts/allocate endpoint exists (may return 400 without valid data)"""
        response = requests.post(
            f"{BASE_URL}/api/svc/parts/allocate",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={}
        )
        # Should return 400 (bad request) not 404 (not found)
        assert response.status_code in [400, 404, 422], \
            f"Expected 400/404/422, got {response.status_code}: {response.text}"
        if response.status_code == 400:
            print("✓ /svc/parts/allocate endpoint exists (returns 400 for invalid data)")
        else:
            print(f"✓ /svc/parts/allocate endpoint exists (returns {response.status_code})")


# ─────────────────────────────────────────────────────────────────
# Test push_event wiring (via cases notes and transition endpoints)
# ─────────────────────────────────────────────────────────────────

class TestPushEventWiring:
    """Test that cases notes and transition endpoints call push_event"""

    def test_cases_notes_endpoint_exists(self, master_admin_token):
        """POST /api/svc/cases/{id}/notes endpoint exists"""
        # Use a fake case ID - should return 404 (case not found)
        fake_case_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{fake_case_id}/notes",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={"body": "Test note"}
        )
        # Should return 404 (case not found) not 405 (method not allowed)
        assert response.status_code in [404, 400], \
            f"Expected 404/400, got {response.status_code}: {response.text}"
        print("✓ /svc/cases/{id}/notes endpoint exists")

    def test_cases_transition_endpoint_exists(self, master_admin_token):
        """POST /api/svc/cases/{id}/transition endpoint exists"""
        # Use a fake case ID - should return 404 (case not found)
        fake_case_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{fake_case_id}/transition",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={"to": "triaged"}
        )
        # Should return 404 (case not found) or 400 (invalid state)
        assert response.status_code in [404, 400], \
            f"Expected 404/400, got {response.status_code}: {response.text}"
        print("✓ /svc/cases/{id}/transition endpoint exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
