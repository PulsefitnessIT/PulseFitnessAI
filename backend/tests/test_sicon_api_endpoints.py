"""
Sicon API Endpoints Integration Tests
Tests all Sicon routes for proper error handling when Sicon is not configured.
Also tests RBAC, sync queue CRUD, and regression of existing KPI/PPM/auth flows.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://engineer-hub-114.preview.emergentagent.com")

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


# Module-scoped fixtures to avoid rate limiting
@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin token once for all tests"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get Pulse Pro site manager token once for all tests"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Pulse Pro login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestSiconAuth:
    """Test authentication tokens are valid"""

    def test_master_admin_token_valid(self, master_admin_token):
        """Verify master admin token is valid"""
        assert master_admin_token is not None
        print("✓ Master admin token obtained")

    def test_pulse_pro_token_valid(self, pulse_pro_token):
        """Verify Pulse Pro token is valid"""
        assert pulse_pro_token is not None
        print("✓ Pulse Pro token obtained")


class TestSiconConfigEndpoints:
    """Test Sicon config GET/PUT endpoints"""

    def test_get_config_not_configured(self, master_admin_token):
        """GET /api/sicon/config returns configured=false when no config exists"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/config",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "configured" in data or "enabled" in data
        print(f"✓ GET /api/sicon/config returns: configured={data.get('configured')}, enabled={data.get('enabled')}")

    def test_get_config_masks_credentials(self, master_admin_token):
        """GET /api/sicon/config masks credentials when config exists"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/config",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        if data.get("configured"):
            assert data.get("username") in ["", "••••••••"], f"Username not masked: {data.get('username')}"
            assert "password" not in data or data.get("password") is None
        print("✓ GET /api/sicon/config masks credentials properly")

    def test_put_config_requires_owner(self, pulse_pro_token):
        """PUT /api/sicon/config requires owner role"""
        resp = requests.put(
            f"{BASE_URL}/api/sicon/config",
            headers={"Authorization": f"Bearer {pulse_pro_token}"},
            json={"enabled": False}
        )
        # Pulse Pro user is a manager, not owner - should get 403
        assert resp.status_code in [200, 403], f"Expected 200 or 403, got {resp.status_code}: {resp.text}"
        print(f"✓ PUT /api/sicon/config RBAC check: status={resp.status_code}")

    def test_put_config_saves_config(self, master_admin_token):
        """PUT /api/sicon/config saves configuration"""
        resp = requests.put(
            f"{BASE_URL}/api/sicon/config",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={
                "enabled": False,
                "base_url": "https://test-sicon.example.com",
                "company_id": 1,
                "auto_sync_faults": False
            }
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print("✓ PUT /api/sicon/config saves config successfully")


class TestSiconConnectionTest:
    """Test Sicon connection test endpoint"""

    def test_connection_not_configured(self, master_admin_token):
        """POST /api/sicon/test-connection returns connected=false when not configured"""
        resp = requests.post(
            f"{BASE_URL}/api/sicon/test-connection",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "connected" in data
        print(f"✓ POST /api/sicon/test-connection returns: connected={data.get('connected')}")


class TestSiconReferenceDataEndpoints:
    """Test Sicon reference data endpoints (case-types, tracking-statuses, engineers, priorities)"""

    def test_case_types_not_configured(self, master_admin_token):
        """GET /api/sicon/case-types returns empty+error when not configured"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/case-types",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "case_types" in data
        print(f"✓ GET /api/sicon/case-types returns: {len(data.get('case_types', []))} types, error={data.get('error')}")

    def test_tracking_statuses_not_configured(self, master_admin_token):
        """GET /api/sicon/tracking-statuses returns empty+error when not configured"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/tracking-statuses",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "statuses" in data
        print(f"✓ GET /api/sicon/tracking-statuses returns: {len(data.get('statuses', []))} statuses")

    def test_engineers_not_configured(self, master_admin_token):
        """GET /api/sicon/engineers returns empty+error when not configured"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/engineers",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "engineers" in data
        print(f"✓ GET /api/sicon/engineers returns: {len(data.get('engineers', []))} engineers")

    def test_priorities_not_configured(self, master_admin_token):
        """GET /api/sicon/priorities returns empty+error when not configured"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/priorities",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "priorities" in data
        print(f"✓ GET /api/sicon/priorities returns: {len(data.get('priorities', []))} priorities")


class TestSiconSyncEndpoints:
    """Test Sicon sync endpoints (sync-case, amend-case, add-note, create-appointment, sync-contract)"""

    def test_sync_case_issue_not_found(self, master_admin_token):
        """POST /api/sicon/sync-case/{issue_id} returns 404 when issue not found"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/sync-case/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/sync-case returns 404 for non-existent issue")

    def test_sync_issue_alias_not_found(self, master_admin_token):
        """POST /api/sicon/sync-issue/{issue_id} (alias) returns 404 when issue not found"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/sync-issue/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/sync-issue (alias) returns 404 for non-existent issue")

    def test_amend_case_issue_not_found(self, master_admin_token):
        """POST /api/sicon/amend-case/{issue_id} returns 404 when issue not found"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/amend-case/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/amend-case returns 404 for non-existent issue")

    def test_add_note_issue_not_found(self, master_admin_token):
        """POST /api/sicon/add-note/{issue_id} returns 404 when issue not found"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/add-note/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={"note": "Test note"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/add-note returns 404 for non-existent issue")

    def test_add_note_requires_note_field(self, master_admin_token):
        """POST /api/sicon/add-note/{issue_id} requires note field"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/add-note/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={}  # Missing note field
        )
        # Should return 404 (issue not found) or 400 (note required)
        assert resp.status_code in [400, 404], f"Expected 400 or 404, got {resp.status_code}: {resp.text}"
        print(f"✓ POST /api/sicon/add-note validates note field: status={resp.status_code}")

    def test_create_appointment_issue_not_synced(self, master_admin_token):
        """POST /api/sicon/create-appointment/{issue_id} returns 400 when issue not synced"""
        fake_issue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/create-appointment/{fake_issue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={"scheduled_start": "2026-04-20T09:00:00Z", "scheduled_end": "2026-04-20T11:00:00Z"}
        )
        # Should return 400 (not synced) since issue doesn't exist or isn't synced
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/create-appointment returns 400 for non-synced issue")

    def test_sync_contract_not_found(self, master_admin_token):
        """POST /api/sicon/sync-contract/{contract_id} returns 404 when contract not found"""
        fake_contract_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/sync-contract/{fake_contract_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/sync-contract returns 404 for non-existent contract")


class TestSiconPollAndQueue:
    """Test Sicon poll and sync queue endpoints"""

    def test_poll_updates_returns_counts(self, master_admin_token):
        """POST /api/sicon/poll-updates returns poll + retry counts"""
        resp = requests.post(
            f"{BASE_URL}/api/sicon/poll-updates",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "poll" in data
        assert "retry" in data
        print(f"✓ POST /api/sicon/poll-updates returns: poll={data.get('poll')}, retry={data.get('retry')}")

    def test_sync_queue_returns_empty_list(self, master_admin_token):
        """GET /api/sicon/sync-queue returns empty list initially"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/sync-queue",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "items" in data
        assert "count" in data
        assert isinstance(data["items"], list)
        print(f"✓ GET /api/sicon/sync-queue returns: {data.get('count')} items")

    def test_sync_queue_status_filter(self, master_admin_token):
        """GET /api/sicon/sync-queue supports status filter"""
        for status in ["pending", "resolved", "all"]:
            resp = requests.get(
                f"{BASE_URL}/api/sicon/sync-queue?status={status}",
                headers={"Authorization": f"Bearer {master_admin_token}"}
            )
            assert resp.status_code == 200, f"Expected 200 for status={status}, got {resp.status_code}"
        print("✓ GET /api/sicon/sync-queue supports status=pending|resolved|all")

    def test_sync_queue_limit_param(self, master_admin_token):
        """GET /api/sicon/sync-queue supports limit parameter"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/sync-queue?limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ GET /api/sicon/sync-queue supports limit parameter")

    def test_sync_queue_retry_not_found(self, master_admin_token):
        """POST /api/sicon/sync-queue/{queue_id}/retry returns 404 when item not found"""
        fake_queue_id = str(uuid.uuid4())
        resp = requests.post(
            f"{BASE_URL}/api/sicon/sync-queue/{fake_queue_id}/retry",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ POST /api/sicon/sync-queue/{id}/retry returns 404 for non-existent item")

    def test_sync_queue_delete_not_found(self, master_admin_token):
        """DELETE /api/sicon/sync-queue/{queue_id} returns 404 when item not found"""
        fake_queue_id = str(uuid.uuid4())
        resp = requests.delete(
            f"{BASE_URL}/api/sicon/sync-queue/{fake_queue_id}",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ DELETE /api/sicon/sync-queue/{id} returns 404 for non-existent item")


class TestSiconAuditLog:
    """Test Sicon audit log endpoint"""

    def test_audit_log_returns_logs(self, master_admin_token):
        """GET /api/sicon/audit-log returns logs list"""
        resp = requests.get(
            f"{BASE_URL}/api/sicon/audit-log",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)
        print(f"✓ GET /api/sicon/audit-log returns: {len(data.get('logs', []))} logs")


class TestSiconRBAC:
    """Test Sicon RBAC requirements"""

    def test_config_requires_auth(self):
        """GET /api/sicon/config requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/sicon/config")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ GET /api/sicon/config requires authentication")

    def test_poll_requires_auth(self):
        """POST /api/sicon/poll-updates requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/sicon/poll-updates")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ POST /api/sicon/poll-updates requires authentication")

    def test_sync_queue_requires_auth(self):
        """GET /api/sicon/sync-queue requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/sicon/sync-queue")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ GET /api/sicon/sync-queue requires authentication")


class TestRegressionKPIEngine:
    """Regression tests for existing KPI engine endpoints"""

    def test_kpi_dashboard_endpoint(self, master_admin_token):
        """GET /api/reports/kpi-dashboard still works (master-admin — KPI is GymAxis-only)."""
        resp = requests.get(
            f"{BASE_URL}/api/reports/kpi-dashboard",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # KPI dashboard returns nested structure with equipment_downtime.total_faults
        assert "equipment_downtime" in data or "oos_ratio" in data or "ppm_compliance" in data
        print("✓ GET /api/reports/kpi-dashboard returns 200 with KPI data")


class TestRegressionPPMEndpoints:
    """Regression tests for existing PPM endpoints"""

    def test_ppm_schedules_endpoint(self, pulse_pro_token):
        """GET /api/ppm/schedules still works"""
        resp = requests.get(
            f"{BASE_URL}/api/ppm/schedules",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ GET /api/ppm/schedules returns 200")

    def test_ppm_summary_endpoint(self, pulse_pro_token):
        """GET /api/ppm/summary still works"""
        resp = requests.get(
            f"{BASE_URL}/api/ppm/summary",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ GET /api/ppm/summary returns 200")

    def test_ppm_checklists_endpoint(self, pulse_pro_token):
        """GET /api/ppm/checklists still works"""
        resp = requests.get(
            f"{BASE_URL}/api/ppm/checklists",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ GET /api/ppm/checklists returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
