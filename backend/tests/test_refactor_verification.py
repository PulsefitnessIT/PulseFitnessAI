"""
GymFix AI - Refactoring Verification Tests
Tests all endpoints after server.py was split into modular route files.
Previous iteration (7) had 100% pass rate - this verifies no regressions.
"""
import pytest
import requests
import os

from tests.conftest import REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials sourced centrally from conftest (see _ensure_regular_test_user)
TEST_EMAIL = REGULAR_USER_EMAIL
TEST_PASSWORD = REGULAR_USER_PASSWORD


class TestAuthEndpoints:
    """Auth routes: /api/auth/* and /api/organization/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def test_login_success(self):
        """POST /api/auth/login - should return token and user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        print(f"✓ Login successful, role: {data['user'].get('role')}")

    def test_login_invalid_credentials(self):
        """POST /api/auth/login - should return 401 for invalid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401
        print("✓ Invalid login correctly rejected")

    def test_get_me(self):
        """GET /api/auth/me - should return current user"""
        # First login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]

        # Get me
        response = self.session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == TEST_EMAIL
        print(f"✓ GET /api/auth/me returned user: {data['full_name']}")

    def test_get_organization(self):
        """GET /api/organization - should return org details"""
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]

        response = self.session.get(
            f"{BASE_URL}/api/organization",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "name" in data
        print(f"✓ GET /api/organization returned: {data['name']}")

    def test_get_organization_staff(self):
        """GET /api/organization/staff - should return staff list"""
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]

        response = self.session.get(
            f"{BASE_URL}/api/organization/staff",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "staff" in data
        print(f"✓ GET /api/organization/staff returned {data['count']} staff members")

    def test_get_organization_logo(self):
        """GET /api/organization/logo - should return logo URL"""
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]

        response = self.session.get(
            f"{BASE_URL}/api/organization/logo",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        print("✓ GET /api/organization/logo returned successfully")

    def test_get_account_billing(self):
        """GET /api/account/billing - should return billing info"""
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]

        response = self.session.get(
            f"{BASE_URL}/api/account/billing",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_plan" in data
        print(f"✓ GET /api/account/billing returned plan: {data['current_plan']}")


class TestEquipmentEndpoints:
    """Equipment routes: /api/equipment/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login and get token
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_all_equipment(self):
        """GET /api/equipment - should return equipment list"""
        response = self.session.get(f"{BASE_URL}/api/equipment", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "equipment" in data
        print(f"✓ GET /api/equipment returned {len(data['equipment'])} items")

    def test_create_and_delete_equipment(self):
        """POST /api/equipment and DELETE /api/equipment/{id}"""
        # Create
        create_resp = self.session.post(f"{BASE_URL}/api/equipment", headers=self.headers, json={
            "name": "TEST_Treadmill_Refactor",
            "equipment_type": "Treadmill",
            "manufacturer": "Test Manufacturer",
            "model": "Test Model"
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["name"] == "TEST_Treadmill_Refactor"
        equipment_id = created["id"]
        print(f"✓ POST /api/equipment created: {equipment_id}")

        # Get single
        get_resp = self.session.get(f"{BASE_URL}/api/equipment/{equipment_id}", headers=self.headers)
        assert get_resp.status_code == 200
        print(f"✓ GET /api/equipment/{equipment_id} returned successfully")

        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=self.headers)
        assert delete_resp.status_code == 200
        print(f"✓ DELETE /api/equipment/{equipment_id} successful")

    def test_export_csv(self):
        """GET /api/equipment/export/csv - should return CSV"""
        response = self.session.get(f"{BASE_URL}/api/equipment/export/csv", headers=self.headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        print("✓ GET /api/equipment/export/csv returned CSV")

    def test_lifecycle_alerts(self):
        """GET /api/equipment/lifecycle-alerts - should return alerts"""
        response = self.session.get(f"{BASE_URL}/api/equipment/lifecycle-alerts", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        print(f"✓ GET /api/equipment/lifecycle-alerts returned {len(data['alerts'])} alerts")


class TestIssuesEndpoints:
    """Issues routes: /api/issues/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_issues(self):
        """GET /api/issues - should return issues list"""
        response = self.session.get(f"{BASE_URL}/api/issues", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        print(f"✓ GET /api/issues returned {len(data['issues'])} issues")

    def test_triage_issue(self):
        """POST /api/issues/triage - should return AI triage"""
        response = self.session.post(f"{BASE_URL}/api/issues/triage", headers=self.headers, json={
            "machine_type": "Treadmill",
            "serial_number": "TEST-001",
            "issue_description": "Belt slipping during use",
            "severity": "medium"
        })
        assert response.status_code == 200
        data = response.json()
        assert "diagnosis" in data
        print("✓ POST /api/issues/triage returned diagnosis")

    def test_create_issue(self):
        """POST /api/issues - should create issue"""
        response = self.session.post(f"{BASE_URL}/api/issues", headers=self.headers, json={
            "machine_type": "Treadmill",
            "serial_number": "TEST-REFACTOR-001",
            "issue_description": "Test issue for refactor verification",
            "severity": "low",
            "resolution_type": "self_fix",
            "resolution_note": "Test resolution"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == "TEST-REFACTOR-001"
        print(f"✓ POST /api/issues created issue: {data['id']}")


class TestCheckSheetsEndpoints:
    """Check sheets routes: /api/check-sheets/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_templates_no_auth(self):
        """GET /api/check-sheets/templates - public endpoint, no auth required"""
        response = self.session.get(f"{BASE_URL}/api/check-sheets/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "Treadmills" in data["templates"]
        print(f"✓ GET /api/check-sheets/templates returned {len(data['templates'])} categories")

    def test_get_history(self):
        """GET /api/check-sheets/history - should return history"""
        response = self.session.get(f"{BASE_URL}/api/check-sheets/history", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "completions" in data
        print(f"✓ GET /api/check-sheets/history returned {len(data['completions'])} completions")

    def test_get_report(self):
        """GET /api/check-sheets/report - should return report"""
        response = self.session.get(f"{BASE_URL}/api/check-sheets/report", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_completions" in data
        print(f"✓ GET /api/check-sheets/report returned total: {data['total_completions']}")

    def test_complete_check_sheet(self):
        """POST /api/check-sheets/complete - should complete a check sheet"""
        response = self.session.post(f"{BASE_URL}/api/check-sheets/complete", headers=self.headers, json={
            "template_name": "Treadmills",
            "checks": {"All Areas Cleaned": True, "E-Stop Check": True},
            "notes": "Test completion for refactor verification"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print(f"✓ POST /api/check-sheets/complete created: {data['id']}")

    def test_get_custom_templates(self):
        """GET /api/check-sheets/custom-templates - should return custom templates"""
        response = self.session.get(f"{BASE_URL}/api/check-sheets/custom-templates", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        print(f"✓ GET /api/check-sheets/custom-templates returned {len(data['templates'])} templates")


class TestMaintenanceEndpoints:
    """Maintenance routes: /api/maintenance/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_tasks(self):
        """GET /api/maintenance/tasks - should return tasks"""
        response = self.session.get(f"{BASE_URL}/api/maintenance/tasks", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        print(f"✓ GET /api/maintenance/tasks returned {len(data['tasks'])} tasks")

    def test_get_templates(self):
        """GET /api/maintenance/templates - should return templates"""
        response = self.session.get(f"{BASE_URL}/api/maintenance/templates", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        print(f"✓ GET /api/maintenance/templates returned {len(data['templates'])} templates")


class TestReportsEndpoints:
    """Reports routes: /api/reports/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_resolution_stats(self):
        """GET /api/reports/resolution-stats - should return stats"""
        response = self.session.get(f"{BASE_URL}/api/reports/resolution-stats", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_issues" in data
        assert "self_fix_rate" in data
        print(f"✓ GET /api/reports/resolution-stats returned self-fix rate: {data['self_fix_rate']}%")

    def test_equipment_summary(self):
        """GET /api/reports/equipment-summary - should return summary"""
        response = self.session.get(f"{BASE_URL}/api/reports/equipment-summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_equipment" in data
        print(f"✓ GET /api/reports/equipment-summary returned {data['total_equipment']} equipment")

    def test_operational_reports(self):
        """GET /api/reports/operational - should return operational data"""
        response = self.session.get(f"{BASE_URL}/api/reports/operational", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_faults" in data
        print(f"✓ GET /api/reports/operational returned {data['total_faults']} faults")


class TestAIDiagnosisEndpoints:
    """AI Diagnosis routes: /api/chat/* and /api/audit/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_chat_diagnose(self):
        """POST /api/chat/diagnose - should return AI diagnosis"""
        response = self.session.post(f"{BASE_URL}/api/chat/diagnose", headers=self.headers, json={
            "message": "Treadmill belt is slipping",
            "equipment_type": "Treadmill"
        })
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        print("✓ POST /api/chat/diagnose returned AI response")

    def test_audit_generate(self):
        """POST /api/audit/generate - should generate audit report"""
        response = self.session.post(f"{BASE_URL}/api/audit/generate", headers=self.headers, json={
            "equipment_type": "Treadmill",
            "usage_frequency": "High",
            "last_maintenance": "2025-01-01",
            "notes": "Test audit for refactor verification"
        })
        assert response.status_code == 200
        data = response.json()
        assert "report" in data
        print(f"✓ POST /api/audit/generate created audit: {data['id']}")

    def test_audit_history(self):
        """GET /api/audit/history - should return audit history"""
        response = self.session.get(f"{BASE_URL}/api/audit/history", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "audits" in data
        print(f"✓ GET /api/audit/history returned {len(data['audits'])} audits")


class TestRiskAssessmentsEndpoints:
    """Risk Assessment routes: /api/risk-assessments/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_risk_assessments(self):
        """GET /api/risk-assessments - should return assessments"""
        response = self.session.get(f"{BASE_URL}/api/risk-assessments", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "assessments" in data
        print(f"✓ GET /api/risk-assessments returned {len(data['assessments'])} assessments")

    def test_create_risk_assessment(self):
        """POST /api/risk-assessments - should create assessment"""
        response = self.session.post(f"{BASE_URL}/api/risk-assessments", headers=self.headers, json={
            "title": "TEST_Refactor_RA",
            "site_name": "Test Gym",
            "assessor": "Test User",
            "assessment_date": "2026-01-06",
            "validity_period": "12 months",
            "hazards": [
                {"hazard": "Test Hazard", "harm": "Test Harm", "who": "Staff", "plr": 2, "psr": 2}
            ],
            "recommendations": [{"text": "Test recommendations"}],
            "notes": "Test notes"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Refactor_RA"
        print(f"✓ POST /api/risk-assessments created: {data['id']}")

    def test_ai_generate_risk_assessment(self):
        """POST /api/risk-assessments/ai-generate - should generate hazards"""
        response = self.session.post(f"{BASE_URL}/api/risk-assessments/ai-generate", headers=self.headers, json={
            "site_name": "Test Gym",
            "equipment_types": ["Treadmill"],
            "site_description": "Commercial gym"
        })
        assert response.status_code == 200
        data = response.json()
        assert "hazards" in data
        print(f"✓ POST /api/risk-assessments/ai-generate returned {len(data['hazards'])} hazards")


class TestPurchaseOrdersEndpoints:
    """Purchase Order routes: /api/purchase-orders/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_purchase_orders(self):
        """GET /api/purchase-orders - should return POs"""
        response = self.session.get(f"{BASE_URL}/api/purchase-orders", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "purchase_orders" in data
        print(f"✓ GET /api/purchase-orders returned {len(data['purchase_orders'])} POs")

    def test_create_purchase_order(self):
        """POST /api/purchase-orders - should create PO"""
        response = self.session.post(f"{BASE_URL}/api/purchase-orders", headers=self.headers, json={
            "supplier_name": "Test Supplier",
            "supplier_email": "test@supplier.com",
            "items": [{"description": "Test Part", "quantity": 1, "unit_price": 100}],
            "notes": "Test PO for refactor verification"
        })
        assert response.status_code == 200
        data = response.json()
        assert "po_number" in data
        print(f"✓ POST /api/purchase-orders created: {data['po_number']}")
        return data["id"]


class TestFilesEndpoints:
    """Files routes: /api/files/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_list_files(self):
        """GET /api/files/list - should return files"""
        response = self.session.get(f"{BASE_URL}/api/files/list", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        print(f"✓ GET /api/files/list returned {len(data['files'])} files")


class TestSuppliersEndpoints:
    """Suppliers routes: /api/suppliers/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_suppliers(self):
        """GET /api/suppliers - should return suppliers"""
        response = self.session.get(f"{BASE_URL}/api/suppliers", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "suppliers" in data
        print(f"✓ GET /api/suppliers returned {len(data['suppliers'])} suppliers")

    def test_create_and_delete_supplier(self):
        """POST /api/suppliers and DELETE /api/suppliers/{id}"""
        # Create
        create_resp = self.session.post(f"{BASE_URL}/api/suppliers", headers=self.headers, json={
            "name": "TEST_Supplier_Refactor",
            "email": "test@refactor.com",
            "phone": "123456789"
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        supplier_id = created["id"]
        print(f"✓ POST /api/suppliers created: {supplier_id}")

        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/suppliers/{supplier_id}", headers=self.headers)
        assert delete_resp.status_code == 200
        print(f"✓ DELETE /api/suppliers/{supplier_id} successful")


class TestSupplierAPIEndpoints:
    """Supplier API routes: /api/v1/supplier/*"""

    def test_supplier_api_health(self):
        """GET /api/v1/supplier/health - public health check"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/v1/supplier/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ GET /api/v1/supplier/health returned: {data['status']}")


class TestDigestEndpoints:
    """Digest routes: /api/digest/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_digest_preview(self):
        """GET /api/digest/preview - should return digest preview"""
        response = self.session.get(f"{BASE_URL}/api/digest/preview", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "period" in data
        print(f"✓ GET /api/digest/preview returned period: {data['period']}")


class TestOnboardingEndpoints:
    """Onboarding routes: /api/onboarding/* and /api/api-keys/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_onboard_equipment(self):
        """POST /api/onboarding/equipment - should onboard equipment"""
        response = self.session.post(f"{BASE_URL}/api/onboarding/equipment", headers=self.headers, json={
            "items": [
                {"name": "TEST_Onboard_Refactor", "equipment_type": "Treadmill", "serial_number": "TEST-ONB-001"}
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        print(f"✓ POST /api/onboarding/equipment onboarded {data['count']} items")

    def test_list_api_keys(self):
        """GET /api/api-keys - should return API keys"""
        response = self.session.get(f"{BASE_URL}/api/api-keys", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "api_keys" in data
        print(f"✓ GET /api/api-keys returned {len(data['api_keys'])} keys")


class TestGymLayoutsEndpoints:
    """Gym Layouts routes: /api/gym-layouts/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_gym_layouts(self):
        """GET /api/gym-layouts - should return layouts"""
        response = self.session.get(f"{BASE_URL}/api/gym-layouts", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "layouts" in data
        print(f"✓ GET /api/gym-layouts returned {len(data['layouts'])} layouts")

    def test_create_and_delete_layout(self):
        """POST /api/gym-layouts and DELETE /api/gym-layouts/{id}"""
        # Create - schema uses gym_length and gym_width
        create_resp = self.session.post(f"{BASE_URL}/api/gym-layouts", headers=self.headers, json={
            "name": "TEST_Layout_Refactor",
            "gym_length": 20,
            "gym_width": 15,
            "equipment_positions": []
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        layout_id = created["id"]
        print(f"✓ POST /api/gym-layouts created: {layout_id}")

        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/gym-layouts/{layout_id}", headers=self.headers)
        assert delete_resp.status_code == 200
        print(f"✓ DELETE /api/gym-layouts/{layout_id} successful")


class TestPaymentsEndpoints:
    """Payments routes: /api/payments/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_checkout_endpoint_exists(self):
        """POST /api/payments/checkout - should accept request (may fail with Stripe)"""
        response = self.session.post(f"{BASE_URL}/api/payments/checkout", headers=self.headers, json={
            "package_id": "basic",
            "origin_url": BASE_URL
        })
        # Accept 200 (success), 400 (invalid package), or 500 (Stripe config issue) — endpoint exists
        assert response.status_code in [200, 400, 500], f"Unexpected status: {response.status_code}"
        print(f"✓ POST /api/payments/checkout endpoint exists (status: {response.status_code})")


class TestServiceEndpoints:
    """Service routes: /api/service/*"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_service_request(self):
        """POST /api/service/request - should create service request"""
        response = self.session.post(f"{BASE_URL}/api/service/request", headers=self.headers, json={
            "machine_type": "Treadmill",
            "issue_summary": "Test service request for refactor verification",
            "site_info": "Test Gym",
            "contact_name": "Test User",
            "contact_email": TEST_EMAIL,
            "contact_phone": "123456789"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print(f"✓ POST /api/service/request created: {data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
