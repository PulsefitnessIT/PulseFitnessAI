"""
Backend tests for iteration 134 - P3 refactor validation
Tests:
1. PATCH /api/issues/{id} - refactored update_issue with helper functions
2. GET /api/platform-docs/pdf - refactored _build_pdf with extracted helpers
3. Master Admin endpoints used by refactored frontend components
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials (loaded from env with local-dev fallbacks)
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


class TestAuth:
    """Authentication tests for both user types"""

    def test_master_admin_login(self):
        """Master admin can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("user", {}).get("is_master_admin") == True
        print("✓ Master admin login successful")

    def test_pulse_pro_login(self):
        """Pulse Pro user can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        print("✓ Pulse Pro login successful")


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Master admin login failed")
    return response.json()["token"]


@pytest.fixture(scope="module")
def pulse_token():
    """Get Pulse Pro auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Pulse Pro login failed")
    return response.json()["token"]


class TestUpdateIssueRefactor:
    """Tests for refactored PATCH /api/issues/{id} endpoint

    The update_issue function was decomposed from cyclomatic complexity 18 into:
    - _apply_status_change
    - _apply_resolution_fields
    - _apply_kpi_timestamps
    - _apply_engineer_fields
    """

    def test_status_change_only(self, admin_token):
        """Test status change updates timeline correctly"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # First get an existing issue
        issues_res = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        assert issues_res.status_code == 200
        issues = issues_res.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available for testing")

        issue_id = issues[0]["id"]
        original_status = issues[0].get("status", "open")
        new_status = "in_progress" if original_status != "in_progress" else "open"

        # Update status
        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": new_status},
            headers=headers
        )
        assert response.status_code == 200, f"Status update failed: {response.text}"
        assert response.json().get("success") == True

        # Verify the change persisted
        detail_res = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        assert detail_res.status_code == 200
        updated_issue = detail_res.json()
        assert updated_issue["status"] == new_status

        # Check timeline was updated
        timeline = updated_issue.get("timeline", [])
        assert len(timeline) > 0, "Timeline should have entries"
        last_event = timeline[-1]
        assert f"status_changed_to_{new_status}" in last_event.get("event", "")

        print(f"✓ Status change to '{new_status}' with timeline update")

        # Restore original status
        requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": original_status},
            headers=headers
        )

    def test_kpi_timestamp_update(self, admin_token):
        """Test KPI timestamp fields are properly applied"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        issues_res = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        issues = issues_res.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available for testing")

        issue_id = issues[0]["id"]

        # Update with KPI timestamp
        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"engineer_assigned_at": "2026-01-15T10:00:00Z"},
            headers=headers
        )
        assert response.status_code == 200

        # Verify
        detail_res = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        updated = detail_res.json()
        assert updated.get("engineer_assigned_at") == "2026-01-15T10:00:00Z"
        print("✓ KPI timestamp (engineer_assigned_at) updated correctly")

    def test_engineer_notes_update(self, admin_token):
        """Test engineer activity fields are properly applied"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        issues_res = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        issues = issues_res.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available for testing")

        issue_id = issues[0]["id"]
        test_notes = "TEST_Engineer notes from iteration 134 testing"

        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"engineer_notes": test_notes},
            headers=headers
        )
        assert response.status_code == 200

        detail_res = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        updated = detail_res.json()
        assert updated.get("engineer_notes") == test_notes
        print("✓ Engineer notes updated correctly")

    def test_resolution_fields_update(self, admin_token):
        """Test resolution fields are properly applied"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        issues_res = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        issues = issues_res.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available for testing")

        # Find an open issue to test resolution
        open_issues = [i for i in issues if i.get("status") == "open"]
        if not open_issues:
            pytest.skip("No open issues for resolution test")

        issue_id = open_issues[0]["id"]

        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={
                "status": "resolved",
                "resolution_type": "self_fix",
                "resolved_by": "test_user"
            },
            headers=headers
        )
        assert response.status_code == 200

        detail_res = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        updated = detail_res.json()
        assert updated.get("status") == "resolved"
        assert updated.get("resolution_type") == "self_fix"
        assert updated.get("resolved_at") is not None, "resolved_at should be auto-set"
        print("✓ Resolution fields updated with auto-set resolved_at")

        # Restore to open
        requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": "open"},
            headers=headers
        )


class TestPDFExportRefactor:
    """Tests for refactored GET /api/platform-docs/pdf endpoint

    The _build_pdf function was decomposed from complexity 16 to 10 with:
    - _is_header_title_skip helper
    - _parse_table_cells helper
    """

    def test_pdf_endpoint_returns_valid_pdf(self, admin_token):
        """PDF endpoint returns a valid PDF file > 50KB"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/platform-docs/pdf", headers=headers)
        assert response.status_code == 200, f"PDF endpoint failed: {response.status_code}"

        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Wrong content type: {content_type}"

        # Check file size > 50KB
        content_length = len(response.content)
        assert content_length > 50000, f"PDF too small: {content_length} bytes (expected >50KB)"

        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF', "Invalid PDF header"

        print(f"✓ PDF generated successfully: {content_length / 1024:.1f}KB")

    def test_pdf_has_content_disposition(self, admin_token):
        """PDF response has proper Content-Disposition header"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/platform-docs/pdf", headers=headers)
        assert response.status_code == 200

        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "GymAxis" in disposition or "filename" in disposition
        print(f"✓ Content-Disposition header correct: {disposition[:60]}...")


class TestMasterAdminEndpoints:
    """Tests for Master Admin endpoints used by refactored frontend components"""

    def test_stats_endpoint(self, admin_token):
        """GET /api/master-admin/stats returns dashboard stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Verify expected fields exist
        assert "total_organizations" in data or "organizations" in data
        print("✓ Master admin stats endpoint working")

    def test_organizations_endpoint(self, admin_token):
        """GET /api/master-admin/organizations returns org list"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert response.status_code == 200
        data = response.json()

        orgs = data.get("organizations", [])
        assert isinstance(orgs, list)
        assert len(orgs) >= 3, f"Expected at least 3 orgs, got {len(orgs)}"

        # Check for expected orgs
        org_names = [o.get("name", "") for o in orgs]
        print(f"✓ Organizations endpoint returned {len(orgs)} orgs: {org_names[:3]}...")

    def test_users_endpoint(self, admin_token):
        """GET /api/master-admin/users returns user list"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert response.status_code == 200
        data = response.json()

        users = data.get("users", [])
        assert isinstance(users, list)
        print(f"✓ Users endpoint returned {len(users)} users")

    def test_ai_usage_endpoint(self, admin_token):
        """GET /api/master-admin/ai-usage returns AI usage stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/ai-usage", headers=headers)
        assert response.status_code == 200
        print("✓ AI usage endpoint working")

    def test_activity_log_endpoint(self, admin_token):
        """GET /api/master-admin/activity-log returns activity logs"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/activity-log", headers=headers)
        assert response.status_code == 200
        data = response.json()

        logs = data.get("logs", [])
        assert isinstance(logs, list)
        print(f"✓ Activity log endpoint returned {len(logs)} entries")

    def test_pulse_stats_endpoint(self, admin_token):
        """GET /api/master-admin/pulse-stats returns Pulse stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/pulse-stats", headers=headers)
        assert response.status_code == 200
        print("✓ Pulse stats endpoint working")

    def test_analytics_dashboard_endpoint(self, admin_token):
        """GET /api/master-admin/analytics/dashboard returns analytics"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/analytics/dashboard", headers=headers)
        assert response.status_code == 200
        print("✓ Analytics dashboard endpoint working")

    def test_trials_endpoint(self, admin_token):
        """GET /api/master-admin/trials returns trial data"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/master-admin/trials", headers=headers)
        assert response.status_code == 200
        print("✓ Trials endpoint working")


class TestMasterAdminMutations:
    """Tests for Master Admin mutation endpoints used by useMasterAdminActions hook"""

    def test_toggle_test_flag(self, admin_token):
        """PUT /api/master-admin/organizations/{id}/test-flag toggles test flag"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Get an org to test with
        orgs_res = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        orgs = orgs_res.json().get("organizations", [])

        # Find Tottenham Green (test org from previous iterations)
        test_org = next((o for o in orgs if "Tottenham" in o.get("name", "")), None)
        if not test_org:
            test_org = orgs[0] if orgs else None

        if not test_org:
            pytest.skip("No org available for test flag toggle")

        org_id = test_org["id"]
        original_is_test = test_org.get("is_test", False)

        # Toggle test flag
        response = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/test-flag",
            json={"is_test": not original_is_test},
            headers=headers
        )
        assert response.status_code == 200, f"Toggle failed: {response.text}"

        # Verify change
        orgs_res = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        updated_org = next((o for o in orgs_res.json().get("organizations", []) if o["id"] == org_id), None)
        assert updated_org.get("is_test") == (not original_is_test)

        print(f"✓ Test flag toggled from {original_is_test} to {not original_is_test}")

        # Restore original
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/test-flag",
            json={"is_test": original_is_test},
            headers=headers
        )

    def test_update_tier(self, admin_token):
        """PUT /api/master-admin/organizations/{id}/subscription updates tier"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        orgs_res = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        orgs = orgs_res.json().get("organizations", [])

        if not orgs:
            pytest.skip("No orgs available")

        test_org = orgs[0]
        org_id = test_org["id"]
        original_tier = test_org.get("subscription_tier", "free")
        new_tier = "pro" if original_tier != "pro" else "premium"

        response = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": new_tier},
            headers=headers
        )
        assert response.status_code == 200
        print("✓ Subscription tier update endpoint working")

        # Restore
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": original_tier},
            headers=headers
        )

    def test_reset_user_password(self, admin_token):
        """PUT /api/master-admin/users/{id}/reset-password resets password"""
        headers = {"Authorization": f"Bearer {admin_token}"}

        users_res = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        users = users_res.json().get("users", [])

        # Find a non-admin user to test with
        test_user = next((u for u in users if not u.get("is_master_admin") and "test" not in u.get("email", "").lower()), None)

        if not test_user:
            pytest.skip("No suitable user for password reset test")

        user_id = test_user["id"]

        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/reset-password",
            json={},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "temp_password" in data, "Should return temp password"
        print("✓ Password reset endpoint working, temp password returned")


class TestPulseProDashboard:
    """Tests for Pulse Pro user dashboard functionality"""

    def test_issues_endpoint(self, pulse_token):
        """GET /api/issues returns issues for Pulse Pro user"""
        headers = {"Authorization": f"Bearer {pulse_token}"}

        response = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        assert response.status_code == 200
        data = response.json()

        issues = data.get("issues", [])
        assert isinstance(issues, list)
        print(f"✓ Issues endpoint returned {len(issues)} issues for Pulse Pro")

    def test_equipment_endpoint(self, pulse_token):
        """GET /api/equipment returns equipment for Pulse Pro user"""
        headers = {"Authorization": f"Bearer {pulse_token}"}

        response = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        assert response.status_code == 200
        data = response.json()

        equipment = data.get("equipment", [])
        assert isinstance(equipment, list)
        print(f"✓ Equipment endpoint returned {len(equipment)} items for Pulse Pro")

    def test_maintenance_tasks_endpoint(self, pulse_token):
        """GET /api/maintenance/tasks returns tasks"""
        headers = {"Authorization": f"Bearer {pulse_token}"}

        response = requests.get(f"{BASE_URL}/api/maintenance/tasks", headers=headers)
        assert response.status_code == 200
        print("✓ Maintenance tasks endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
