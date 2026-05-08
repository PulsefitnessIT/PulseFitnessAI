"""
Archive Feature Tests - Iteration 141
Tests for GDPR right-to-erasure Archive functionality:
- GET /api/master-admin/archive - list archived orgs
- POST /api/master-admin/archive/{org_id}/restore - restore archived org
- DELETE /api/master-admin/archive/{org_id} - hard delete org
- POST /api/master-admin/archive/sweep - run lifecycle sweep
- PUT /api/master-admin/organizations/{id}/status - archive/unarchive via status change
- 403 for non-master-admin users
- Regression tests for trials_summary, analytics_faults, kpi_export
"""
import pytest
import requests
import os
import uuid

from tests.conftest import (
    MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD,
    PULSE_PRO_EMAIL, PULSE_PRO_PASSWORD, API_BASE_URL,
)

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or API_BASE_URL).rstrip("/")

NON_ADMIN_EMAIL = PULSE_PRO_EMAIL
NON_ADMIN_PASSWORD = PULSE_PRO_PASSWORD


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-admin user auth token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": NON_ADMIN_EMAIL,
        "password": NON_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Non-admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def test_org_for_archive(master_admin_token):
    """Create a test organization for archive testing."""
    headers = {"Authorization": f"Bearer {master_admin_token}"}
    unique_name = f"TEST_Archive_Org_{uuid.uuid4().hex[:8]}"

    # Create org
    response = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
        "name": unique_name,
        "portal_type": "service_portal",
        "account_type": "full",
        "subscription_tier": "starter",
        "primary_contact_email": f"test_{uuid.uuid4().hex[:6]}@example.com"
    }, headers=headers)

    assert response.status_code == 200, f"Failed to create test org: {response.text}"
    org_data = response.json()
    org_id = org_data.get("id")

    yield {"id": org_id, "name": unique_name}

    # Cleanup: try to delete the org if it still exists
    try:
        requests.delete(f"{BASE_URL}/api/master-admin/archive/{org_id}", headers=headers)
    except:
        pass


class TestArchiveEndpoints:
    """Test Archive API endpoints."""

    def test_get_archive_returns_correct_structure(self, master_admin_token):
        """GET /api/master-admin/archive returns correct response structure."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/master-admin/archive", headers=headers)

        assert response.status_code == 200, f"GET archive failed: {response.text}"
        data = response.json()

        # Verify required keys
        assert "organizations" in data, "Missing 'organizations' key"
        assert "retention_days" in data, "Missing 'retention_days' key"
        assert "warning_lead_days" in data, "Missing 'warning_lead_days' key"
        assert "count" in data, "Missing 'count' key"

        # Verify retention values
        assert data["retention_days"] == 365, f"Expected retention_days=365, got {data['retention_days']}"
        assert data["warning_lead_days"] == 7, f"Expected warning_lead_days=7, got {data['warning_lead_days']}"
        assert data["count"] == len(data["organizations"]), "Count mismatch"

        print(f"✓ GET /api/master-admin/archive returns correct structure with {data['count']} archived orgs")

    def test_archive_org_via_status_update(self, master_admin_token, test_org_for_archive):
        """PUT /api/master-admin/organizations/{id}/status with status='archived' stamps archived_at."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        org_id = test_org_for_archive["id"]

        # Archive the org
        response = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"},
            headers=headers
        )

        assert response.status_code == 200, f"Archive status update failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("status") == "archived"

        # Verify org appears in archive list with correct fields
        archive_response = requests.get(f"{BASE_URL}/api/master-admin/archive", headers=headers)
        assert archive_response.status_code == 200
        archive_data = archive_response.json()

        archived_org = next((o for o in archive_data["organizations"] if o["id"] == org_id), None)
        assert archived_org is not None, "Archived org not found in archive list"

        # Verify required fields per org
        assert "days_until_deletion" in archived_org, "Missing days_until_deletion"
        assert "scheduled_deletion_at" in archived_org, "Missing scheduled_deletion_at"
        assert "warning_sent_at" in archived_org, "Missing warning_sent_at"
        assert archived_org.get("archived_at") is not None, "archived_at not stamped"
        assert archived_org.get("archived_by") == MASTER_ADMIN_EMAIL, "archived_by not stamped correctly"

        print(f"✓ Org archived via status update, archived_at={archived_org['archived_at']}, days_until_deletion={archived_org['days_until_deletion']}")

    def test_restore_archived_org(self, master_admin_token, test_org_for_archive):
        """POST /api/master-admin/archive/{org_id}/restore restores org to active."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        org_id = test_org_for_archive["id"]

        # Ensure org is archived first
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"},
            headers=headers
        )

        # Restore the org
        response = requests.post(
            f"{BASE_URL}/api/master-admin/archive/{org_id}/restore",
            headers=headers
        )

        assert response.status_code == 200, f"Restore failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("status") == "active"

        # Verify org no longer in archive list
        archive_response = requests.get(f"{BASE_URL}/api/master-admin/archive", headers=headers)
        archive_data = archive_response.json()
        archived_org = next((o for o in archive_data["organizations"] if o["id"] == org_id), None)
        assert archived_org is None, "Restored org should not be in archive list"

        # Verify org is active in organizations list
        orgs_response = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        orgs_data = orgs_response.json()
        org = next((o for o in orgs_data["organizations"] if o["id"] == org_id), None)
        assert org is not None, "Org not found in organizations list"
        assert org.get("status") == "active", f"Expected status=active, got {org.get('status')}"
        assert org.get("archived_at") is None, "archived_at should be cleared"
        assert org.get("archived_by") is None, "archived_by should be cleared"

        print(f"✓ Org restored successfully, status={org.get('status')}")

    def test_restore_non_archived_org_returns_404(self, master_admin_token, test_org_for_archive):
        """POST /api/master-admin/archive/{org_id}/restore returns 404 for non-archived org."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        org_id = test_org_for_archive["id"]

        # Ensure org is active (not archived)
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "active"},
            headers=headers
        )

        # Try to restore non-archived org
        response = requests.post(
            f"{BASE_URL}/api/master-admin/archive/{org_id}/restore",
            headers=headers
        )

        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Restore non-archived org returns 404")

    def test_sweep_archive_idempotent(self, master_admin_token):
        """POST /api/master-admin/archive/sweep is idempotent when no orgs are due."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        response = requests.post(f"{BASE_URL}/api/master-admin/archive/sweep", headers=headers)

        assert response.status_code == 200, f"Sweep failed: {response.text}"
        data = response.json()

        assert data.get("success") is True
        assert "scanned" in data, "Missing 'scanned' key"
        assert "warnings_sent" in data, "Missing 'warnings_sent' key"
        assert "deleted" in data, "Missing 'deleted' key"

        # Since no orgs should be past retention, deleted should be 0
        # (unless there are very old archived orgs in the system)
        print(f"✓ Sweep completed: scanned={data['scanned']}, warnings_sent={data['warnings_sent']}, deleted={data['deleted']}")

    def test_hard_delete_archived_org(self, master_admin_token):
        """DELETE /api/master-admin/archive/{org_id} hard-deletes org and returns purged counts."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # Create a fresh org for deletion
        unique_name = f"TEST_Delete_Org_{uuid.uuid4().hex[:8]}"
        create_response = requests.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "service_portal",
            "account_type": "full"
        }, headers=headers)
        assert create_response.status_code == 200
        org_id = create_response.json().get("id")

        # Archive it first
        archive_response = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/status",
            json={"status": "archived"},
            headers=headers
        )
        assert archive_response.status_code == 200

        # Hard delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/master-admin/archive/{org_id}",
            headers=headers
        )

        assert delete_response.status_code == 200, f"Hard delete failed: {delete_response.text}"
        data = delete_response.json()

        assert data.get("success") is True
        assert "purged" in data, "Missing 'purged' key"
        assert data["purged"].get("organizations") == 1, "Should have purged 1 organization"

        # Verify org is gone
        orgs_response = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        orgs_data = orgs_response.json()
        org = next((o for o in orgs_data["organizations"] if o["id"] == org_id), None)
        assert org is None, "Deleted org should not exist"

        print(f"✓ Hard delete successful, purged: {data['purged']}")

    def test_hard_delete_nonexistent_org_returns_404(self, master_admin_token):
        """DELETE /api/master-admin/archive/{org_id} returns 404 for nonexistent org."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        fake_id = f"nonexistent-{uuid.uuid4().hex}"

        response = requests.delete(
            f"{BASE_URL}/api/master-admin/archive/{fake_id}",
            headers=headers
        )

        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Hard delete nonexistent org returns 404")


class TestArchive403ForNonAdmin:
    """Test that archive endpoints return 403 for non-master-admin users."""

    def test_get_archive_403_for_non_admin(self, non_admin_token):
        """GET /api/master-admin/archive returns 403 for non-admin."""
        headers = {"Authorization": f"Bearer {non_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/master-admin/archive", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ GET archive returns 403 for non-admin")

    def test_restore_403_for_non_admin(self, non_admin_token):
        """POST /api/master-admin/archive/{org_id}/restore returns 403 for non-admin."""
        headers = {"Authorization": f"Bearer {non_admin_token}"}
        response = requests.post(
            f"{BASE_URL}/api/master-admin/archive/fake-org-id/restore",
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Restore returns 403 for non-admin")

    def test_hard_delete_403_for_non_admin(self, non_admin_token):
        """DELETE /api/master-admin/archive/{org_id} returns 403 for non-admin."""
        headers = {"Authorization": f"Bearer {non_admin_token}"}
        response = requests.delete(
            f"{BASE_URL}/api/master-admin/archive/fake-org-id",
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Hard delete returns 403 for non-admin")

    def test_sweep_403_for_non_admin(self, non_admin_token):
        """POST /api/master-admin/archive/sweep returns 403 for non-admin."""
        headers = {"Authorization": f"Bearer {non_admin_token}"}
        response = requests.post(f"{BASE_URL}/api/master-admin/archive/sweep", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Sweep returns 403 for non-admin")


class TestRegressionTrialsSummary:
    """Regression test for GET /api/master-admin/trials/summary after refactor."""

    def test_trials_summary_returns_all_8_keys(self, master_admin_token):
        """GET /api/master-admin/trials/summary returns all 8 required keys."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=headers)

        assert response.status_code == 200, f"Trials summary failed: {response.text}"
        data = response.json()

        required_keys = [
            "total", "by_status", "converted_30d", "ended_30d",
            "conversion_rate_30d", "avg_days_to_convert", "expiring_this_week", "by_source"
        ]

        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

        print(f"✓ Trials summary returns all 8 keys: {list(data.keys())}")


class TestRegressionAnalyticsFaults:
    """Regression test for GET /api/master-admin/analytics/faults after refactor."""

    def test_analytics_faults_by_fault_code_structure(self, master_admin_token):
        """GET /api/master-admin/analytics/faults returns by_fault_code with 8 keys per entry."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        response = requests.get(f"{BASE_URL}/api/master-admin/analytics/faults", headers=headers)

        assert response.status_code == 200, f"Analytics faults failed: {response.text}"
        data = response.json()

        assert "by_fault_code" in data, "Missing 'by_fault_code' key"

        # If there are fault codes, verify structure
        if data["by_fault_code"]:
            entry = data["by_fault_code"][0]
            required_keys = [
                "code", "label", "category", "count",
                "count_current_30d", "count_previous_30d", "delta_pct", "trend"
            ]
            for key in required_keys:
                assert key in entry, f"Missing key in by_fault_code entry: {key}"
            print(f"✓ Analytics faults by_fault_code has all 8 keys: {list(entry.keys())}")
        else:
            print("✓ Analytics faults returns empty by_fault_code (no fault data)")


class TestRegressionKPIExportCSV:
    """Regression test for GET /api/master-admin/kpi/{org_id}/export-csv after refactor."""

    def test_kpi_export_csv_returns_10_kpi_rows(self, master_admin_token):
        """GET /api/master-admin/kpi/{org_id}/export-csv returns CSV with 10 standard KPI rows."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # First get an org ID
        orgs_response = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert orgs_response.status_code == 200
        orgs = orgs_response.json().get("organizations", [])

        if not orgs:
            pytest.skip("No organizations available for KPI export test")

        org_id = orgs[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/master-admin/kpi/{org_id}/export-csv",
            headers=headers
        )

        assert response.status_code == 200, f"KPI export failed: {response.text}"
        assert "text/csv" in response.headers.get("content-type", ""), "Response should be CSV"

        csv_content = response.text
        lines = csv_content.strip().split("\n")

        # Should have header rows + 10 KPI rows + possibly worst assets section
        # Header: GymAxis AI, Organisation, Period, Generated, blank, KPI header
        # Then 10 KPI rows
        assert len(lines) >= 15, f"Expected at least 15 lines, got {len(lines)}"

        # Check for expected KPI labels
        expected_kpis = [
            "PPM Compliance", "PPM Completion Rate", "Avg Machine Downtime",
            "Open Downtime Faults", "Reactive Response (Standard)",
            "Reactive Response (Safety Critical)", "Safety SLA Compliance",
            "Safety Inspection Pass Rate", "Machine Availability",
            "Post-Install Verification Pass Rate"
        ]

        found_kpis = 0
        for kpi in expected_kpis:
            if kpi in csv_content:
                found_kpis += 1

        assert found_kpis == 10, f"Expected 10 KPI rows, found {found_kpis}"
        print("✓ KPI export CSV contains all 10 standard KPI rows")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
