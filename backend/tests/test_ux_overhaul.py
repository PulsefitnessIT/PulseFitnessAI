"""
Backend API tests for GymFix AI UX Overhaul
Tests issue status update endpoint and other critical APIs
"""
import pytest
import requests
import os

from tests.conftest import REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aftersales-engine.preview.emergentagent.com')

# Test credentials sourced centrally from conftest (see _ensure_regular_test_user)
TEST_EMAIL = REGULAR_USER_EMAIL
TEST_PASSWORD = REGULAR_USER_PASSWORD

class TestAuth:
    """Authentication tests"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")

    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"Login successful, user: {data['user']['email']}")


class TestIssueStatusUpdate:
    """Test issue status update endpoint - PATCH /api/issues/{id}?status="""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}

    def test_get_issues(self, headers):
        """Test getting issues list"""
        response = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        print(f"Found {len(data['issues'])} issues")
        return data['issues']

    def test_update_issue_status_to_in_progress(self, headers):
        """Test updating issue status to in_progress"""
        # First get issues
        response = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        issues = response.json().get('issues', [])

        # Find an open issue
        open_issues = [i for i in issues if i.get('status') == 'open']
        if not open_issues:
            pytest.skip("No open issues to test status update")

        issue_id = open_issues[0]['id']

        # Update status to in_progress (body-based payload)
        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": "in_progress"},
            headers=headers
        )
        assert response.status_code == 200, f"Status update failed: {response.text}"
        data = response.json()
        assert data.get('success') == True
        print(f"Successfully updated issue {issue_id} to in_progress")

    def test_update_issue_status_to_resolved(self, headers):
        """Test updating issue status to resolved"""
        # First get issues
        response = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        issues = response.json().get('issues', [])

        # Find an in_progress issue
        in_progress_issues = [i for i in issues if i.get('status') == 'in_progress']
        if not in_progress_issues:
            pytest.skip("No in_progress issues to test status update")

        issue_id = in_progress_issues[0]['id']

        # Update status to resolved (body-based payload)
        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": "resolved"},
            headers=headers
        )
        assert response.status_code == 200, f"Status update failed: {response.text}"
        data = response.json()
        assert data.get('success') == True
        print(f"Successfully updated issue {issue_id} to resolved")


class TestReportsEndpoints:
    """Test Reports-related endpoints"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}

    def test_resolution_stats(self, headers):
        """Test resolution stats endpoint for Operational Reports"""
        response = requests.get(f"{BASE_URL}/api/reports/resolution-stats", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Check expected fields
        assert "total_issues" in data
        assert "self_fixes" in data
        assert "engineer_callouts" in data
        assert "estimated_savings" in data
        assert "self_fix_rate" in data

        print(f"Resolution stats: {data['self_fixes']} self-fixes, {data['engineer_callouts']} engineer callouts")
        print(f"Estimated savings: £{data['estimated_savings']}")

    def test_audit_history(self, headers):
        """Test audit history endpoint"""
        response = requests.get(f"{BASE_URL}/api/audit/history", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "audits" in data
        print(f"Found {len(data['audits'])} audits")

    def test_risk_assessments(self, headers):
        """Test risk assessments endpoint"""
        response = requests.get(f"{BASE_URL}/api/risk-assessments", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "assessments" in data
        print(f"Found {len(data['assessments'])} risk assessments")


class TestMaintenanceEndpoints:
    """Test Maintenance-related endpoints"""

    def test_maintenance_tasks(self):
        """Test maintenance tasks endpoint (no auth required)"""
        response = requests.get(f"{BASE_URL}/api/maintenance/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data['tasks']) > 0
        print(f"Found {len(data['tasks'])} maintenance tasks")

    def test_check_sheet_templates(self):
        """Test check sheet templates endpoint"""
        response = requests.get(f"{BASE_URL}/api/check-sheets/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data

        # Check for expected categories
        expected_categories = ["Treadmills", "Cross Trainers", "Free Weights & Benches"]
        for cat in expected_categories:
            assert cat in data['templates'], f"Missing category: {cat}"

        print(f"Found {len(data['templates'])} check sheet categories")


class TestEquipmentEndpoints:
    """Test Equipment-related endpoints"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        return response.json().get("token")

    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}

    def test_get_equipment(self, headers):
        """Test getting equipment list"""
        response = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "equipment" in data
        print(f"Found {len(data['equipment'])} equipment items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
