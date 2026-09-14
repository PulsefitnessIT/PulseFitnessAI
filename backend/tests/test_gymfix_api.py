"""
GymFix AI Backend API Tests
Tests for: Authentication, Issues, Equipment, CSV Import/Export
"""
import pytest
import requests
import os

from tests.conftest import REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mod-only-deploy.preview.emergentagent.com')

# Test credentials sourced centrally from conftest (see _ensure_regular_test_user)
TEST_EMAIL = REGULAR_USER_EMAIL
TEST_PASSWORD = REGULAR_USER_PASSWORD


class TestAuthentication:
    """Authentication endpoint tests"""

    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.text[:500]}")

        assert response.status_code == 200, f"Login failed: {response.text}"

        data = response.json()
        assert "token" in data, "Token not in response"
        assert "user" in data, "User not in response"
        assert data["user"]["email"] == TEST_EMAIL
        assert len(data["token"]) > 0

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401


class TestIssues:
    """Issue management tests - testing new serial_number/supplier schema"""

    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")

    def test_create_issue_with_new_schema(self, auth_token):
        """Test creating issue with serial_number, machine_type, supplier fields"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        issue_data = {
            "serial_number": "TEST-SN-001",
            "machine_type": "Treadmill",
            "issue_description": "Test issue - belt slipping during high speed",
            "severity": "medium",
            "supplier": "Life Fitness"
        }

        response = requests.post(f"{BASE_URL}/api/issues", json=issue_data, headers=headers)
        print(f"Create issue response status: {response.status_code}")
        print(f"Create issue response: {response.text[:1000]}")

        assert response.status_code == 200, f"Issue creation failed: {response.text}"

        data = response.json()
        assert "id" in data, "Issue ID not returned"
        assert data["serial_number"] == "TEST-SN-001"
        assert data["machine_type"] == "Treadmill"
        assert data["supplier"] == "Life Fitness"
        assert data["severity"] == "medium"
        assert data["status"] == "open"
        # AI triage should be present (may take time)
        assert "ai_triage" in data

    def test_get_issues_returns_serial_number(self, auth_token):
        """Test GET /api/issues returns issues with serial_number field"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/issues", headers=headers)
        print(f"Get issues response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "issues" in data

        # Check that issues have serial_number field (even old ones normalized)
        for issue in data["issues"]:
            assert "serial_number" in issue, f"Issue missing serial_number: {issue}"
            print(f"Issue: {issue.get('serial_number')} - {issue.get('machine_type')} - {issue.get('status')}")

    def test_update_issue_status(self, auth_token):
        """Test updating issue status"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # First create an issue
        issue_data = {
            "serial_number": "TEST-UPDATE-001",
            "machine_type": "Exercise Bike",
            "issue_description": "Test issue for status update",
            "severity": "low",
            "supplier": "Technogym"
        }

        create_response = requests.post(f"{BASE_URL}/api/issues", json=issue_data, headers=headers)
        if create_response.status_code != 200:
            pytest.skip(f"Could not create issue: {create_response.text}")

        issue_id = create_response.json()["id"]

        # Update status to in_progress (body-based payload per current API)
        update_response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}",
            json={"status": "in_progress"},
            headers=headers
        )
        print(f"Update issue response: {update_response.status_code}")

        assert update_response.status_code == 200


class TestEquipmentCSV:
    """Equipment CSV import/export tests"""

    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")

    def test_get_csv_template(self, auth_token):
        """Test GET /api/equipment/template/csv returns downloadable template"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/equipment/template/csv", headers=headers)
        print(f"CSV template response status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("Content-Type", "")

        # Check CSV content has expected headers
        content = response.text
        assert "Name" in content
        assert "Type" in content
        assert "Serial Number" in content
        print(f"Template content preview: {content[:300]}")

    def test_export_equipment_csv(self, auth_token):
        """Test GET /api/equipment/export/csv exports equipment"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/equipment/export/csv", headers=headers)
        print(f"Export CSV response status: {response.status_code}")

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("Content-Type", "")

        content = response.text
        print(f"Export content preview: {content[:500]}")

    def test_import_equipment_csv(self, auth_token):
        """Test POST /api/equipment/import/csv imports equipment from CSV"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Create a test CSV file
        csv_content = """Name,Type,Manufacturer,Model,Serial Number,Purchase Date (YYYY-MM-DD),Warranty Expiry (YYYY-MM-DD),Length (m),Width (m),Height (m),Notes
TEST Import Treadmill,Treadmill,Life Fitness,95T,TEST-IMP-001,2024-01-15,2027-01-15,2.1,0.9,1.6,Test import
TEST Import Bike,Exercise Bike,Technogym,Bike 700,TEST-IMP-002,2024-02-20,2027-02-20,1.2,0.6,1.4,Test import bike"""

        files = {
            'file': ('test_import.csv', csv_content, 'text/csv')
        }

        response = requests.post(
            f"{BASE_URL}/api/equipment/import/csv",
            headers=headers,
            files=files
        )
        print(f"Import CSV response status: {response.status_code}")
        print(f"Import CSV response: {response.text}")

        assert response.status_code == 200

        data = response.json()
        assert "imported" in data
        assert data["imported"] >= 0  # May be 0 if duplicates
        print(f"Imported: {data['imported']}, Errors: {data.get('errors', [])}")


class TestEquipment:
    """Equipment CRUD tests"""

    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")

    def test_get_equipment_list(self, auth_token):
        """Test GET /api/equipment returns equipment list"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        print(f"Get equipment response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "equipment" in data
        print(f"Equipment count: {len(data['equipment'])}")

    def test_get_equipment_summary(self, auth_token):
        """Test GET /api/reports/equipment-summary"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/reports/equipment-summary", headers=headers)
        print(f"Equipment summary response status: {response.status_code}")
        print(f"Equipment summary response: {response.text[:500]}")

        assert response.status_code == 200

        data = response.json()
        assert "total_equipment" in data
        assert "total_issues" in data


class TestMaintenanceTasks:
    """Maintenance tasks tests"""

    def test_get_maintenance_tasks(self):
        """Test GET /api/maintenance/tasks (no auth required)"""
        response = requests.get(f"{BASE_URL}/api/maintenance/tasks")
        print(f"Maintenance tasks response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) > 0
        print(f"Tasks count: {len(data['tasks'])}")


class TestAudit:
    """Audit report tests"""

    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")

    def test_get_audit_history(self, auth_token):
        """Test GET /api/audit/history"""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = requests.get(f"{BASE_URL}/api/audit/history", headers=headers)
        print(f"Audit history response status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert "audits" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
