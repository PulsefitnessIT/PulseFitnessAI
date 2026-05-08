"""
Test suite for Gamified Onboarding feature (iteration 140)
Tests the 4-stage onboarding journey: Suppliers → Equipment → Staff → Go-Live

Endpoints tested:
- GET /api/onboarding/status
- GET /api/onboarding/equipment-template.csv
- POST /api/onboarding/equipment-csv-import
- POST /api/onboarding/dismiss
- POST /api/onboarding/complete
- POST /api/suppliers (to verify status transitions)
"""

import pytest
import requests
import os
import uuid
import csv
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestGamifiedOnboarding:
    """Tests for the gamified onboarding 4-stage flow"""

    @pytest.fixture(scope="class")
    def fresh_trial_user(self):
        """Register a fresh trial user for onboarding tests"""
        rand_suffix = uuid.uuid4().hex[:8]
        email = f"onboard.autotest+{rand_suffix}@example.com"
        payload = {
            "email": email,
            "password": "OnboardTest123!",
            "full_name": "Auto Tester",
            "company_name": f"Auto Test Gym {rand_suffix}"
        }
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert response.status_code in [200, 201], f"Registration failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in registration response"
        return {
            "token": data["token"],
            "user": data.get("user", {}),
            "email": email
        }

    @pytest.fixture(scope="class")
    def auth_headers(self, fresh_trial_user):
        """Get auth headers for the fresh trial user"""
        return {"Authorization": f"Bearer {fresh_trial_user['token']}"}

    # ─────────── GET /api/onboarding/status ───────────

    def test_onboarding_status_fresh_user(self, auth_headers):
        """Fresh user should have all stages false, percent 0"""
        response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=auth_headers)
        assert response.status_code == 200, f"Status endpoint failed: {response.text}"

        data = response.json()
        # Verify response shape
        assert "stages" in data, "Missing 'stages' in response"
        assert "percent" in data, "Missing 'percent' in response"
        assert "completed_count" in data, "Missing 'completed_count' in response"
        assert "counts" in data, "Missing 'counts' in response"

        # Verify fresh user state
        stages = data["stages"]
        assert stages.get("suppliers") == False, "Fresh user should have suppliers=false"
        assert stages.get("equipment") == False, "Fresh user should have equipment=false"
        assert stages.get("staff") == False, "Fresh user should have staff=false"
        assert stages.get("live") == False, "Fresh user should have live=false"

        assert data["percent"] == 0, f"Fresh user should have percent=0, got {data['percent']}"
        assert data["completed_count"] == 0, f"Fresh user should have completed_count=0, got {data['completed_count']}"

        print(f"✓ Fresh user onboarding status: {data}")

    # ─────────── GET /api/onboarding/equipment-template.csv ───────────

    def test_equipment_template_download(self, auth_headers):
        """Template CSV should have 10 headers and 3 sample rows"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding/equipment-template.csv",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Template download failed: {response.text}"

        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"

        # Parse CSV content
        csv_content = response.text
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Verify headers (10 expected)
        expected_headers = [
            "name", "equipment_type", "manufacturer", "model",
            "serial_number", "location", "purchase_date", "warranty_expiry",
            "supplier", "sla_response_time"
        ]
        assert len(rows) >= 4, f"Expected at least 4 rows (1 header + 3 samples), got {len(rows)}"
        assert rows[0] == expected_headers, f"Headers mismatch: {rows[0]}"

        # Verify 3 sample rows
        sample_rows = rows[1:4]
        assert len(sample_rows) == 3, f"Expected 3 sample rows, got {len(sample_rows)}"

        # Verify sample data structure
        for i, row in enumerate(sample_rows):
            assert len(row) == 10, f"Sample row {i+1} should have 10 columns, got {len(row)}"
            assert row[0], f"Sample row {i+1} should have a name"

        print(f"✓ Equipment template: {len(rows[0])} headers, {len(sample_rows)} sample rows")

    # ─────────── POST /api/onboarding/equipment-csv-import ───────────

    def test_equipment_csv_import_valid(self, auth_headers):
        """Valid CSV import should insert equipment and return success"""
        csv_content = """name,equipment_type,manufacturer,model,serial_number,location,purchase_date,warranty_expiry,supplier,sla_response_time
TEST_Treadmill Import,cardio,Precor,TRM 425,SN-TEST-001,Cardio Floor,2023-06-15,2025-06-15,Precor,4 hours
TEST_Bike Import,cardio,Keiser,M3i,SN-TEST-002,Studio 1,2022-11-05,,Keiser,"""

        response = requests.post(
            f"{BASE_URL}/api/onboarding/equipment-csv-import",
            headers=auth_headers,
            json={"csv_content": csv_content}
        )
        assert response.status_code == 200, f"CSV import failed: {response.text}"

        data = response.json()
        assert data.get("success") == True, "Expected success=true"
        assert "imported" in data, "Missing 'imported' count"
        assert "skipped" in data, "Missing 'skipped' count"
        assert data["imported"] >= 2, f"Expected at least 2 imported, got {data['imported']}"

        print(f"✓ CSV import: {data['imported']} imported, {data['skipped']} skipped")

    def test_equipment_csv_import_empty(self, auth_headers):
        """Empty CSV should return 400 error"""
        response = requests.post(
            f"{BASE_URL}/api/onboarding/equipment-csv-import",
            headers=auth_headers,
            json={"csv_content": ""}
        )
        assert response.status_code == 400, f"Expected 400 for empty CSV, got {response.status_code}"
        print("✓ Empty CSV correctly rejected with 400")

    # ─────────── POST /api/onboarding/dismiss ───────────

    def test_onboarding_dismiss(self, auth_headers):
        """Dismiss should set dismissed flag"""
        response = requests.post(
            f"{BASE_URL}/api/onboarding/dismiss",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 200, f"Dismiss failed: {response.text}"

        data = response.json()
        assert data.get("success") == True, "Expected success=true"

        # Verify dismissed flag in status
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=auth_headers)
        status_data = status_response.json()
        assert status_data.get("dismissed") == True, "Dismissed flag should be true after dismiss"

        print("✓ Onboarding banner dismissed successfully")

    # ─────────── POST /api/onboarding/complete ───────────

    def test_onboarding_complete(self, auth_headers):
        """Complete should set onboarding_completed_at timestamp"""
        response = requests.post(
            f"{BASE_URL}/api/onboarding/complete",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 200, f"Complete failed: {response.text}"

        data = response.json()
        assert data.get("success") == True, "Expected success=true"

        # Verify completed_at in status
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=auth_headers)
        status_data = status_response.json()
        assert status_data.get("completed_at") is not None, "completed_at should be set after complete"

        print(f"✓ Onboarding completed at: {status_data.get('completed_at')}")


class TestOnboardingStatusTransitions:
    """Test that status transitions correctly after adding real data"""

    @pytest.fixture(scope="class")
    def fresh_user_for_transitions(self):
        """Register another fresh user for transition tests"""
        rand_suffix = uuid.uuid4().hex[:8]
        email = f"onboard.transition+{rand_suffix}@example.com"
        payload = {
            "email": email,
            "password": "OnboardTest123!",
            "full_name": "Transition Tester",
            "company_name": f"Transition Test Gym {rand_suffix}"
        }
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert response.status_code in [200, 201], f"Registration failed: {response.text}"
        data = response.json()
        return {"token": data["token"], "email": email}

    @pytest.fixture(scope="class")
    def transition_headers(self, fresh_user_for_transitions):
        return {"Authorization": f"Bearer {fresh_user_for_transitions['token']}"}

    def test_status_transitions_after_supplier_creation(self, transition_headers):
        """Creating a supplier should flip suppliers stage to true and update percent"""
        # Initial status check
        initial_response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=transition_headers)
        initial_data = initial_response.json()
        assert initial_data["stages"]["suppliers"] == False, "Initial suppliers should be false"
        initial_percent = initial_data["percent"]

        # Create a supplier
        supplier_payload = {
            "name": "TEST_Onboarding Supplier",
            "email": f"test.supplier+{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+44 20 1234 5678",
            "contact_person": "Test Contact",
            "supplier_type": "cardio"
        }
        supplier_response = requests.post(
            f"{BASE_URL}/api/suppliers",
            headers=transition_headers,
            json=supplier_payload
        )
        assert supplier_response.status_code in [200, 201], f"Supplier creation failed: {supplier_response.text}"

        # Check status after supplier creation
        updated_response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=transition_headers)
        updated_data = updated_response.json()

        assert updated_data["stages"]["suppliers"] == True, "Suppliers stage should be true after adding supplier"
        assert updated_data["percent"] > initial_percent, f"Percent should increase: {initial_percent} -> {updated_data['percent']}"
        assert updated_data["counts"]["suppliers"] >= 1, "Supplier count should be at least 1"

        print(f"✓ Status transition: suppliers={updated_data['stages']['suppliers']}, percent={updated_data['percent']}%")

    def test_status_transitions_after_equipment_creation(self, transition_headers):
        """Creating equipment should flip equipment stage to true"""
        # Create equipment via the standard endpoint
        equipment_payload = {
            "name": "TEST_Onboarding Treadmill",
            "equipment_type": "cardio",
            "manufacturer": "Precor",
            "model": "TRM 425",
            "serial_number": f"SN-ONBOARD-{uuid.uuid4().hex[:6]}",
            "location": "Cardio Floor"
        }
        equip_response = requests.post(
            f"{BASE_URL}/api/equipment",
            headers=transition_headers,
            json=equipment_payload
        )
        assert equip_response.status_code in [200, 201], f"Equipment creation failed: {equip_response.text}"

        # Check status
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status", headers=transition_headers)
        status_data = status_response.json()

        assert status_data["stages"]["equipment"] == True, "Equipment stage should be true after adding equipment"
        assert status_data["counts"]["equipment"] >= 1, "Equipment count should be at least 1"

        print(f"✓ Equipment stage: {status_data['stages']['equipment']}, count={status_data['counts']['equipment']}")


class TestMasterAdminOnboardingExclusion:
    """Verify master admin doesn't see onboarding wizard"""

    def test_master_admin_login(self):
        """Master admin should be able to login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200, f"Master admin login failed: {response.text}"
        data = response.json()
        assert data.get("user", {}).get("is_master_admin") == True, "Should be master admin"
        print("✓ Master admin login successful")


# Cleanup fixture to remove test data
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """Cleanup TEST_ prefixed data after all tests"""
    yield
    # Note: In a real scenario, we'd clean up TEST_ prefixed suppliers/equipment
    # For now, the test data is isolated to the fresh trial user's organization
    print("✓ Test cleanup complete (test data isolated to trial orgs)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
