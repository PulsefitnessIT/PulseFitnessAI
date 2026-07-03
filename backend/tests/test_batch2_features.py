"""
Test Batch 2 Features for GymFix AI
- Suppliers API
- Purchase Orders API
- Operational Reports API
- Issue Details Update (supplier_ref)
- File Uploads
"""
import pytest
import requests
import os
import uuid

from tests.conftest import REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://rbac-modules.preview.emergentagent.com')

# Test credentials sourced centrally from conftest (see _ensure_regular_test_user)
TEST_EMAIL = REGULAR_USER_EMAIL
TEST_PASSWORD = REGULAR_USER_PASSWORD


class TestBatch2Features:
    """Test Batch 2 features: Suppliers, POs, Operational Reports"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user = data["user"]

    # ==================
    # Suppliers API Tests
    # ==================

    def test_get_suppliers(self):
        """GET /api/suppliers returns supplier list"""
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "suppliers" in data
        assert isinstance(data["suppliers"], list)
        print(f"✓ GET /api/suppliers - Found {len(data['suppliers'])} suppliers")

    def test_create_supplier(self):
        """POST /api/suppliers creates a new supplier"""
        supplier_data = {
            "name": f"TEST_Supplier_{uuid.uuid4().hex[:6]}",
            "email": "testsupplier@example.com",
            "phone": "+44 123 456 7890",
            "contact_person": "Test Contact"
        }
        response = requests.post(f"{BASE_URL}/api/suppliers", json=supplier_data, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == supplier_data["name"]
        assert data["email"] == supplier_data["email"]
        assert "id" in data
        print(f"✓ POST /api/suppliers - Created supplier: {data['name']}")

        # Cleanup - delete the test supplier
        delete_response = requests.delete(f"{BASE_URL}/api/suppliers/{data['id']}", headers=self.headers)
        assert delete_response.status_code == 200
        print(f"✓ DELETE /api/suppliers/{data['id']} - Cleaned up test supplier")

    # ==================
    # Purchase Orders API Tests
    # ==================

    def test_get_purchase_orders(self):
        """GET /api/purchase-orders returns PO list"""
        response = requests.get(f"{BASE_URL}/api/purchase-orders", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "purchase_orders" in data
        assert isinstance(data["purchase_orders"], list)
        print(f"✓ GET /api/purchase-orders - Found {len(data['purchase_orders'])} POs")

    def test_create_purchase_order(self):
        """POST /api/purchase-orders creates a new PO"""
        # First get an issue to link the PO to
        issues_response = requests.get(f"{BASE_URL}/api/issues", headers=self.headers)
        assert issues_response.status_code == 200
        issues = issues_response.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available to create PO for")

        issue_id = issues[0]["id"]

        po_data = {
            "issue_id": issue_id,
            "supplier_name": "Test PO Supplier",
            "supplier_email": "po@supplier.com",
            "delivery_address": "123 Test Street",
            "notes": "Test PO from pytest",
            "items": [
                {"description": "Test Part", "quantity": 2, "unit_price": 25.00}
            ]
        }

        response = requests.post(f"{BASE_URL}/api/purchase-orders", json=po_data, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "po_number" in data
        assert data["supplier_name"] == po_data["supplier_name"]
        assert data["status"] == "draft"
        assert data["subtotal"] == 50.0  # 2 * 25
        assert data["total"] == 60.0  # 50 + 20% VAT
        print(f"✓ POST /api/purchase-orders - Created PO: {data['po_number']}")

    def test_get_purchase_orders_by_issue(self):
        """GET /api/purchase-orders?issue_id=xxx filters by issue"""
        # Get an issue first
        issues_response = requests.get(f"{BASE_URL}/api/issues", headers=self.headers)
        issues = issues_response.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available")

        issue_id = issues[0]["id"]
        response = requests.get(f"{BASE_URL}/api/purchase-orders?issue_id={issue_id}", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "purchase_orders" in data
        print(f"✓ GET /api/purchase-orders?issue_id - Found {len(data['purchase_orders'])} POs for issue")

    # ==================
    # Operational Reports API Tests
    # ==================

    def test_operational_reports_30d(self):
        """GET /api/reports/operational?period=30d returns operational data"""
        response = requests.get(f"{BASE_URL}/api/reports/operational?period=30d", headers=self.headers)
        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "period" in data
        assert data["period"] == "30d"
        assert "total_faults" in data
        assert "severity_counts" in data
        assert "by_equipment" in data
        assert "by_supplier" in data
        assert "avg_resolution_hours" in data
        assert "total_po_value" in data
        assert "po_count" in data
        assert "open_faults" in data
        assert "resolved_faults" in data

        print("✓ GET /api/reports/operational?period=30d")
        print(f"  - Total faults: {data['total_faults']}")
        print(f"  - Open: {data['open_faults']}, Resolved: {data['resolved_faults']}")
        print(f"  - Avg resolution: {data['avg_resolution_hours']}h")

    def test_operational_reports_7d(self):
        """GET /api/reports/operational?period=7d returns 7-day data"""
        response = requests.get(f"{BASE_URL}/api/reports/operational?period=7d", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "7d"
        print(f"✓ GET /api/reports/operational?period=7d - {data['total_faults']} faults")

    def test_operational_reports_90d(self):
        """GET /api/reports/operational?period=90d returns 90-day data"""
        response = requests.get(f"{BASE_URL}/api/reports/operational?period=90d", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "90d"
        print(f"✓ GET /api/reports/operational?period=90d - {data['total_faults']} faults")

    def test_operational_reports_all(self):
        """GET /api/reports/operational?period=all returns all-time data"""
        response = requests.get(f"{BASE_URL}/api/reports/operational?period=all", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "all"
        print(f"✓ GET /api/reports/operational?period=all - {data['total_faults']} faults")

    # ==================
    # Issue Details Update Tests
    # ==================

    def test_update_issue_supplier_ref(self):
        """PATCH /api/issues/{id}/details updates supplier_ref"""
        # Get an issue first
        issues_response = requests.get(f"{BASE_URL}/api/issues", headers=self.headers)
        issues = issues_response.json().get("issues", [])

        if not issues:
            pytest.skip("No issues available")

        issue_id = issues[0]["id"]
        test_ref = f"TEST-REF-{uuid.uuid4().hex[:6]}"

        response = requests.patch(
            f"{BASE_URL}/api/issues/{issue_id}/details",
            json={"supplier_ref": test_ref},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print(f"✓ PATCH /api/issues/{issue_id}/details - Updated supplier_ref to {test_ref}")

    # ==================
    # File Upload Tests
    # ==================

    def test_file_upload_endpoint(self):
        """POST /api/files/upload accepts file uploads"""
        # Create a simple test file
        files = {
            'file': ('test.txt', b'Test file content', 'text/plain')
        }

        response = requests.post(
            f"{BASE_URL}/api/files/upload?category=test",
            files=files,
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "download_url" in data
        print(f"✓ POST /api/files/upload - Uploaded file, ID: {data['id']}")

    # ==================
    # Gym Layouts Tests
    # ==================

    def test_get_gym_layouts(self):
        """GET /api/gym-layouts returns layout list"""
        response = requests.get(f"{BASE_URL}/api/gym-layouts", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "layouts" in data
        print(f"✓ GET /api/gym-layouts - Found {len(data['layouts'])} layouts")

    # ==================
    # Audit History Tests
    # ==================

    def test_get_audit_history(self):
        """GET /api/audit/history returns audit list"""
        response = requests.get(f"{BASE_URL}/api/audit/history", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "audits" in data
        print(f"✓ GET /api/audit/history - Found {len(data['audits'])} audits")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
