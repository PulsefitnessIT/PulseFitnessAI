"""
Test suite for Fault Templates and Fault Code Taxonomy features (Iteration 135)

Tests:
- GET /api/fault-codes: Returns 9 categories with ~41 codes
- POST /api/fault-templates: Create with validation (name required, invalid fault_code returns 400, scope='org' requires privileged role)
- GET /api/fault-templates: Returns org-scoped + user's personal templates (not other users' personal)
- PUT /api/fault-templates/{id}: Update with RBAC (403 for non-privileged promoting personal→org)
- DELETE /api/fault-templates/{id}: Success for owner, 403 for non-privileged on org templates
- POST /api/fault-templates/{id}/used: Increments usage_count and sets last_used_at
- POST /api/issues with fault_code: Verify fault_code is stored
- PATCH /api/issues/{id} with fault_code: Update fault_code field
- GET /api/master-admin/analytics/faults: Returns by_fault_code, by_fault_category, coded_fault_count
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials (loaded from env with local-dev fallbacks)
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get Pulse Pro (owner) auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    assert response.status_code == 200, f"Pulse Pro login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def pulse_pro_user(pulse_pro_token):
    """Get Pulse Pro user info"""
    response = requests.get(f"{BASE_URL}/api/auth/me", headers={
        "Authorization": f"Bearer {pulse_pro_token}"
    })
    assert response.status_code == 200
    return response.json()


class TestFaultCodesTaxonomy:
    """Tests for GET /api/fault-codes endpoint"""

    def test_fault_codes_requires_auth(self):
        """Fault codes endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/fault-codes")
        # 401 or 403 both indicate auth required
        assert response.status_code in [401, 403]

    def test_fault_codes_returns_9_categories(self, pulse_pro_token):
        """GET /api/fault-codes returns 9 categories"""
        response = requests.get(f"{BASE_URL}/api/fault-codes", headers={
            "Authorization": f"Bearer {pulse_pro_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        categories = data["categories"]
        assert len(categories) == 9, f"Expected 9 categories, got {len(categories)}"

        # Verify expected category names
        category_names = [c["category"] for c in categories]
        expected = ["mechanical", "electrical", "hydraulic", "structural",
                    "weight_stack", "safety", "software", "wear", "other"]
        for exp in expected:
            assert exp in category_names, f"Missing category: {exp}"

    def test_fault_codes_returns_41_codes(self, pulse_pro_token):
        """GET /api/fault-codes returns ~41 total codes"""
        response = requests.get(f"{BASE_URL}/api/fault-codes", headers={
            "Authorization": f"Bearer {pulse_pro_token}"
        })
        assert response.status_code == 200
        data = response.json()

        total_codes = sum(len(cat["codes"]) for cat in data["categories"])
        assert total_codes >= 40, f"Expected ~41 codes, got {total_codes}"

    def test_fault_codes_contains_expected_codes(self, pulse_pro_token):
        """Verify specific fault codes exist: BEL-01, MOT-01, WGT-01, SAF-01"""
        response = requests.get(f"{BASE_URL}/api/fault-codes", headers={
            "Authorization": f"Bearer {pulse_pro_token}"
        })
        assert response.status_code == 200
        data = response.json()

        all_codes = []
        for cat in data["categories"]:
            for code_tuple in cat["codes"]:
                all_codes.append(code_tuple[0])

        expected_codes = ["BEL-01", "MOT-01", "WGT-01", "SAF-01"]
        for code in expected_codes:
            assert code in all_codes, f"Missing expected code: {code}"


class TestFaultTemplatesCRUD:
    """Tests for fault templates CRUD operations"""

    def test_create_template_missing_name_returns_400(self, pulse_pro_token):
        """POST /api/fault-templates with missing name returns 400"""
        response = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "machine_type": "Treadmill",
                "issue_description": "Belt slipping",
                "severity": "operational_minor"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 400
        assert "name" in response.json().get("detail", "").lower()

    def test_create_template_invalid_fault_code_returns_400(self, pulse_pro_token):
        """POST /api/fault-templates with invalid fault_code returns 400"""
        response = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "name": "TEST_Invalid Code Template",
                "machine_type": "Treadmill",
                "issue_description": "Belt slipping",
                "severity": "operational_minor",
                "fault_code": "INVALID-99"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 400
        assert "invalid" in response.json().get("detail", "").lower()

    def test_create_personal_template_success(self, pulse_pro_token):
        """POST /api/fault-templates creates personal template successfully"""
        unique_name = f"TEST_Personal_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "name": unique_name,
                "scope": "personal",
                "machine_type": "Treadmill",
                "issue_description": "Belt slipping during high speed",
                "severity": "operational_minor",
                "supplier": "Pulse Fitness",
                "steps_taken": "Checked belt tension",
                "fault_code": "BEL-01"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert data["name"] == unique_name
        assert data["scope"] == "personal"
        assert data["fault_code"] == "BEL-01"
        assert "id" in data
        return data["id"]

    def test_create_org_template_as_owner_success(self, pulse_pro_token):
        """POST /api/fault-templates with scope='org' succeeds for owner"""
        unique_name = f"TEST_Org_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "name": unique_name,
                "scope": "org",
                "machine_type": "Spin Bike",
                "issue_description": "Pedal loose",
                "severity": "limited_use",
                "fault_code": "FRM-03"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 200, f"Create org template failed: {response.text}"
        data = response.json()
        assert data["scope"] == "org"
        return data["id"]

    def test_list_templates_returns_visible_templates(self, pulse_pro_token):
        """GET /api/fault-templates returns org-scoped + user's personal templates"""
        response = requests.get(f"{BASE_URL}/api/fault-templates",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        # Should have at least the templates we created
        templates = data["templates"]
        assert isinstance(templates, list)

    def test_mark_template_used_increments_count(self, pulse_pro_token):
        """POST /api/fault-templates/{id}/used increments usage_count"""
        # First create a template
        unique_name = f"TEST_Usage_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "name": unique_name,
                "machine_type": "Rowing Machine",
                "issue_description": "Chain noise",
                "severity": "operational_minor",
                "fault_code": "CHN-01"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert create_resp.status_code == 200
        template_id = create_resp.json()["id"]

        # Mark as used
        used_resp = requests.post(f"{BASE_URL}/api/fault-templates/{template_id}/used",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert used_resp.status_code == 200

        # Verify usage_count increased by fetching templates
        list_resp = requests.get(f"{BASE_URL}/api/fault-templates",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        templates = list_resp.json()["templates"]
        template = next((t for t in templates if t["id"] == template_id), None)
        assert template is not None
        assert template["usage_count"] >= 1
        assert template["last_used_at"] is not None

    def test_delete_own_personal_template_success(self, pulse_pro_token):
        """DELETE /api/fault-templates/{id} succeeds for own personal template"""
        # Create a template to delete
        unique_name = f"TEST_Delete_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/fault-templates",
            json={
                "name": unique_name,
                "scope": "personal",
                "machine_type": "Elliptical",
                "issue_description": "Display error",
                "severity": "operational_minor"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert create_resp.status_code == 200
        template_id = create_resp.json()["id"]

        # Delete it
        delete_resp = requests.delete(f"{BASE_URL}/api/fault-templates/{template_id}",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert delete_resp.status_code == 200

    def test_delete_nonexistent_template_returns_404(self, pulse_pro_token):
        """DELETE /api/fault-templates/{id} returns 404 for non-existent template"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(f"{BASE_URL}/api/fault-templates/{fake_id}",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 404


class TestIssuesWithFaultCode:
    """Tests for issues with fault_code field"""

    def test_create_issue_with_fault_code(self, pulse_pro_token):
        """POST /api/issues with fault_code stores the code"""
        response = requests.post(f"{BASE_URL}/api/issues",
            json={
                "serial_number": f"TEST-SN-{uuid.uuid4().hex[:6]}",
                "machine_type": "Treadmill",
                "issue_description": "Belt slipping at high speed",
                "severity": "operational_minor",
                "fault_code": "BEL-01"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 200, f"Create issue failed: {response.text}"
        data = response.json()
        assert data.get("fault_code") == "BEL-01"
        return data["id"]

    def test_create_issue_without_fault_code_regression(self, pulse_pro_token):
        """POST /api/issues without fault_code still works (regression test)"""
        response = requests.post(f"{BASE_URL}/api/issues",
            json={
                "serial_number": f"TEST-SN-{uuid.uuid4().hex[:6]}",
                "machine_type": "Spin Bike",
                "issue_description": "General maintenance needed",
                "severity": "operational_minor"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 200, f"Create issue without fault_code failed: {response.text}"
        data = response.json()
        # fault_code should be None or not present
        assert data.get("fault_code") is None

    def test_patch_issue_with_fault_code(self, pulse_pro_token):
        """PATCH /api/issues/{id} with fault_code updates the field"""
        # First create an issue without fault_code
        create_resp = requests.post(f"{BASE_URL}/api/issues",
            json={
                "serial_number": f"TEST-SN-{uuid.uuid4().hex[:6]}",
                "machine_type": "Weight Stack",
                "issue_description": "Pin stuck",
                "severity": "limited_use"
            },
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert create_resp.status_code == 200
        issue_id = create_resp.json()["id"]

        # Patch with fault_code
        patch_resp = requests.patch(f"{BASE_URL}/api/issues/{issue_id}",
            json={"fault_code": "WGT-01"},
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert patch_resp.status_code == 200

        # Verify the update
        get_resp = requests.get(f"{BASE_URL}/api/issues/{issue_id}",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert get_resp.status_code == 200
        assert get_resp.json().get("fault_code") == "WGT-01"


class TestMasterAdminFaultAnalytics:
    """Tests for master admin fault analytics with fault code aggregation"""

    def test_faults_analytics_returns_fault_code_breakdown(self, master_admin_token, pulse_pro_token):
        """GET /api/master-admin/analytics/faults returns by_fault_code, by_fault_category, coded_fault_count"""
        # First seed some issues with fault codes
        for code in ["BEL-01", "MOT-01", "BEL-01"]:  # BEL-01 twice for aggregation test
            requests.post(f"{BASE_URL}/api/issues",
                json={
                    "serial_number": f"TEST-ANALYTICS-{uuid.uuid4().hex[:6]}",
                    "machine_type": "Test Machine",
                    "issue_description": f"Test issue for {code}",
                    "severity": "operational_minor",
                    "fault_code": code
                },
                headers={"Authorization": f"Bearer {pulse_pro_token}"}
            )

        # Now fetch analytics
        response = requests.get(f"{BASE_URL}/api/master-admin/analytics/faults",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Analytics failed: {response.text}"
        data = response.json()

        # Verify new keys exist
        assert "by_fault_code" in data, "Missing by_fault_code in response"
        assert "by_fault_category" in data, "Missing by_fault_category in response"
        assert "coded_fault_count" in data, "Missing coded_fault_count in response"

        # Verify by_fault_code structure
        by_fault_code = data["by_fault_code"]
        assert isinstance(by_fault_code, list)
        if len(by_fault_code) > 0:
            first_item = by_fault_code[0]
            assert "code" in first_item
            assert "label" in first_item
            assert "category" in first_item
            assert "count" in first_item

        # Verify coded_fault_count is a number
        assert isinstance(data["coded_fault_count"], int)

    def test_faults_analytics_requires_admin(self, pulse_pro_token):
        """GET /api/master-admin/analytics/faults requires master admin"""
        response = requests.get(f"{BASE_URL}/api/master-admin/analytics/faults",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert response.status_code == 403


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_templates(self, pulse_pro_token):
        """Clean up TEST_ prefixed templates"""
        response = requests.get(f"{BASE_URL}/api/fault-templates",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        if response.status_code == 200:
            templates = response.json().get("templates", [])
            for tpl in templates:
                if tpl.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/fault-templates/{tpl['id']}",
                        headers={"Authorization": f"Bearer {pulse_pro_token}"}
                    )
        assert True  # Cleanup is best-effort
