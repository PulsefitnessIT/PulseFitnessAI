"""
Gym Floor Iteration 185 Tests - Staff Email/Mobile + Fault Logging
Tests for the P0 feature: Staff must have email (required) + mobile (optional)
so suppliers can reach the right person when a fault is logged from gym floor.

Test coverage:
- POST /api/gym-floor/staff with no email returns 400
- POST /api/gym-floor/staff with valid name+email+mobile creates record
- PATCH /api/gym-floor/staff/{id} can update name, email, mobile
- DELETE /api/gym-floor/staff/{id} soft-deletes (active=false)
- GET /api/gym-floor/staff via X-Gym-Floor-Token strips email/mobile (privacy)
- GET /api/gym-floor/equipment with X-Gym-Floor-Token returns org's equipment
- POST /api/gym-floor/fault with valid staff_id creates issue with reporter contact
- POST /api/gym-floor/fault with staff_id of staff without email returns 400
- POST /api/gym-floor/fault without staff_id returns 422
- GET /api/issues/{id} returns created_by_name, created_by_email, created_by_mobile
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
PULSE_PRO_MANAGER = {"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"}
GYM_FLOOR_CRED = {"username": "tottenham-floor", "password": "FloorTest123!"}


def rate_limit_bypass_headers() -> dict:
    """Rate-limit bypass header for test runs."""
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if not secret:
        try:
            env_path = "/app/backend/.env"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                            secret = line.strip().split("=", 1)[1]
                            break
        except Exception:
            pass
    return {"X-RateLimit-Bypass": secret} if secret else {}


@pytest.fixture(scope="module")
def manager_token():
    """Get JWT token for Pulse Pro manager (lee.somers)"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=PULSE_PRO_MANAGER,
        headers=rate_limit_bypass_headers()
    )
    if resp.status_code != 200:
        pytest.skip(f"Could not login as Pulse Pro manager: {resp.status_code} {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def gym_floor_token():
    """Get gym floor session token"""
    resp = requests.post(f"{BASE_URL}/api/gym-floor/login", json=GYM_FLOOR_CRED)
    if resp.status_code != 200:
        pytest.skip(f"Could not login to gym floor: {resp.status_code} {resp.text}")
    return resp.json().get("token")


class TestStaffEmailRequirement:
    """Tests for staff email requirement (P0 feature)"""

    def test_add_staff_without_email_returns_400(self, manager_token):
        """POST /api/gym-floor/staff with no email returns 400"""
        headers = {"Authorization": f"Bearer {manager_token}"}
        payload = {"name": "TEST_NoEmail Staff"}
        resp = requests.post(f"{BASE_URL}/api/gym-floor/staff", json=payload, headers=headers)

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "email" in data.get("detail", "").lower(), f"Error should mention email: {data}"

    def test_add_staff_with_invalid_email_returns_400(self, manager_token):
        """POST /api/gym-floor/staff with invalid email returns 400"""
        headers = {"Authorization": f"Bearer {manager_token}"}
        payload = {"name": "TEST_InvalidEmail Staff", "email": "not-an-email"}
        resp = requests.post(f"{BASE_URL}/api/gym-floor/staff", json=payload, headers=headers)

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_add_staff_with_valid_email_and_mobile(self, manager_token):
        """POST /api/gym-floor/staff with valid name+email+mobile creates record"""
        headers = {"Authorization": f"Bearer {manager_token}"}
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Staff_{unique_id}",
            "email": f"test_{unique_id}@gymtest.com",
            "mobile": "+447700900123"
        }
        resp = requests.post(f"{BASE_URL}/api/gym-floor/staff", json=payload, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True

        # Verify via GET that staff was created with email/mobile
        list_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        assert list_resp.status_code == 200
        staff_list = list_resp.json().get("staff", [])
        created_staff = next((s for s in staff_list if s.get("name") == payload["name"]), None)
        assert created_staff is not None, f"Staff not found in list: {staff_list}"
        assert created_staff.get("email") == payload["email"].lower()
        assert created_staff.get("mobile") == "+447700900123"

    def test_add_staff_with_email_only_no_mobile(self, manager_token):
        """POST /api/gym-floor/staff with email but no mobile succeeds (mobile optional)"""
        headers = {"Authorization": f"Bearer {manager_token}"}
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_EmailOnly_{unique_id}",
            "email": f"emailonly_{unique_id}@gymtest.com"
        }
        resp = requests.post(f"{BASE_URL}/api/gym-floor/staff", json=payload, headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


class TestStaffUpdate:
    """Tests for PATCH /api/gym-floor/staff/{id}"""

    def test_update_staff_name_email_mobile(self, manager_token):
        """PATCH /api/gym-floor/staff/{id} can update name, email, and mobile"""
        headers = {"Authorization": f"Bearer {manager_token}"}

        # First create a staff member
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "name": f"TEST_ToUpdate_{unique_id}",
            "email": f"toupdate_{unique_id}@gymtest.com",
            "mobile": "+447700900001"
        }
        create_resp = requests.post(f"{BASE_URL}/api/gym-floor/staff", json=create_payload, headers=headers)
        assert create_resp.status_code == 200

        # Get the staff ID
        list_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        staff_list = list_resp.json().get("staff", [])
        staff = next((s for s in staff_list if s.get("name") == create_payload["name"]), None)
        assert staff is not None, "Created staff not found"
        staff_id = staff["id"]

        # Update the staff
        update_payload = {
            "name": f"TEST_Updated_{unique_id}",
            "email": f"updated_{unique_id}@gymtest.com",
            "mobile": "+447700900999"
        }
        update_resp = requests.patch(f"{BASE_URL}/api/gym-floor/staff/{staff_id}", json=update_payload, headers=headers)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.status_code} {update_resp.text}"

        # Verify update persisted
        verify_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        staff_list = verify_resp.json().get("staff", [])
        updated_staff = next((s for s in staff_list if s.get("id") == staff_id), None)
        assert updated_staff is not None
        assert updated_staff.get("name") == update_payload["name"]
        assert updated_staff.get("email") == update_payload["email"].lower()
        assert updated_staff.get("mobile") == update_payload["mobile"]

    def test_update_staff_invalid_email_returns_400(self, manager_token):
        """PATCH /api/gym-floor/staff/{id} with invalid email returns 400"""
        headers = {"Authorization": f"Bearer {manager_token}"}

        # Create a staff member first
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "name": f"TEST_InvalidUpdate_{unique_id}",
            "email": f"invalidupdate_{unique_id}@gymtest.com"
        }
        requests.post(f"{BASE_URL}/api/gym-floor/staff", json=create_payload, headers=headers)

        # Get staff ID
        list_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        staff_list = list_resp.json().get("staff", [])
        staff = next((s for s in staff_list if s.get("name") == create_payload["name"]), None)
        if not staff:
            pytest.skip("Could not find created staff")
        staff_id = staff["id"]

        # Try to update with invalid email
        update_resp = requests.patch(
            f"{BASE_URL}/api/gym-floor/staff/{staff_id}",
            json={"email": "not-valid-email"},
            headers=headers
        )
        assert update_resp.status_code == 400


class TestStaffDelete:
    """Tests for DELETE /api/gym-floor/staff/{id}"""

    def test_delete_staff_soft_deletes(self, manager_token):
        """DELETE /api/gym-floor/staff/{id} soft-deletes (active=false)"""
        headers = {"Authorization": f"Bearer {manager_token}"}

        # Create a staff member
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "name": f"TEST_ToDelete_{unique_id}",
            "email": f"todelete_{unique_id}@gymtest.com"
        }
        requests.post(f"{BASE_URL}/api/gym-floor/staff", json=create_payload, headers=headers)

        # Get staff ID
        list_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        staff_list = list_resp.json().get("staff", [])
        staff = next((s for s in staff_list if s.get("name") == create_payload["name"]), None)
        if not staff:
            pytest.skip("Could not find created staff")
        staff_id = staff["id"]

        # Delete the staff
        del_resp = requests.delete(f"{BASE_URL}/api/gym-floor/staff/{staff_id}", headers=headers)
        assert del_resp.status_code == 200

        # Verify staff no longer appears in active list
        verify_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        staff_list = verify_resp.json().get("staff", [])
        deleted_staff = next((s for s in staff_list if s.get("id") == staff_id), None)
        assert deleted_staff is None, "Deleted staff should not appear in active list"


class TestGymFloorSessionPrivacy:
    """Tests for privacy - gym floor session should not see email/mobile"""

    def test_gym_floor_token_strips_email_mobile(self, manager_token, gym_floor_token):
        """GET /api/gym-floor/staff via X-Gym-Floor-Token strips email/mobile fields"""
        # First ensure there's staff with email/mobile (via manager)
        manager_headers = {"Authorization": f"Bearer {manager_token}"}
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "name": f"TEST_Privacy_{unique_id}",
            "email": f"privacy_{unique_id}@gymtest.com",
            "mobile": "+447700900555"
        }
        requests.post(f"{BASE_URL}/api/gym-floor/staff", json=create_payload, headers=manager_headers)

        # Now fetch via gym floor token
        gf_headers = {"X-Gym-Floor-Token": gym_floor_token}
        resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=gf_headers)
        assert resp.status_code == 200

        staff_list = resp.json().get("staff", [])
        # Check that no staff member has email or mobile exposed
        for staff in staff_list:
            assert "email" not in staff, f"Email should be stripped: {staff}"
            assert "mobile" not in staff, f"Mobile should be stripped: {staff}"
            # Should still have id and name
            assert "id" in staff
            assert "name" in staff

    def test_manager_sees_email_mobile(self, manager_token):
        """GET /api/gym-floor/staff via Bearer token shows email/mobile"""
        headers = {"Authorization": f"Bearer {manager_token}"}
        resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        assert resp.status_code == 200

        staff_list = resp.json().get("staff", [])
        # At least one staff should have email (we created several in tests)
        staff_with_email = [s for s in staff_list if s.get("email")]
        assert len(staff_with_email) > 0, "Manager should see staff with email"


class TestGymFloorEquipment:
    """Tests for GET /api/gym-floor/equipment"""

    def test_equipment_list_with_gym_floor_token(self, gym_floor_token):
        """GET /api/gym-floor/equipment with X-Gym-Floor-Token returns org's equipment"""
        headers = {"X-Gym-Floor-Token": gym_floor_token}
        resp = requests.get(f"{BASE_URL}/api/gym-floor/equipment", headers=headers)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "equipment" in data
        assert isinstance(data["equipment"], list)
        # Tottenham org should have equipment
        if len(data["equipment"]) > 0:
            eq = data["equipment"][0]
            assert "id" in eq
            assert "name" in eq


class TestGymFloorFaultLogging:
    """Tests for POST /api/gym-floor/fault - fault logging with staff contact"""

    def test_fault_with_valid_staff_creates_issue(self, manager_token, gym_floor_token):
        """POST /api/gym-floor/fault with valid staff_id creates issue with reporter contact"""
        manager_headers = {"Authorization": f"Bearer {manager_token}"}
        gf_headers = {"X-Gym-Floor-Token": gym_floor_token}

        # Create a staff member with email
        unique_id = str(uuid.uuid4())[:8]
        staff_payload = {
            "name": f"TEST_FaultReporter_{unique_id}",
            "email": f"faultreporter_{unique_id}@gymtest.com",
            "mobile": "+447700900777"
        }
        requests.post(f"{BASE_URL}/api/gym-floor/staff", json=staff_payload, headers=manager_headers)

        # Get staff ID
        staff_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=manager_headers)
        staff_list = staff_resp.json().get("staff", [])
        staff = next((s for s in staff_list if s.get("name") == staff_payload["name"]), None)
        assert staff is not None, "Created staff not found"
        staff_id = staff["id"]

        # Get equipment
        eq_resp = requests.get(f"{BASE_URL}/api/gym-floor/equipment", headers=gf_headers)
        equipment = eq_resp.json().get("equipment", [])
        if not equipment:
            pytest.skip("No equipment available for fault logging")
        equipment_id = equipment[0]["id"]

        # Log a fault
        fault_payload = {
            "staff_id": staff_id,
            "equipment_id": equipment_id,
            "issue_description": f"TEST_Fault_{unique_id}: Machine making strange noise",
            "severity": "operational_minor"
        }
        fault_resp = requests.post(f"{BASE_URL}/api/gym-floor/fault", json=fault_payload, headers=gf_headers)

        assert fault_resp.status_code == 200, f"Fault creation failed: {fault_resp.status_code} {fault_resp.text}"
        data = fault_resp.json()
        assert data.get("ok") is True
        assert "id" in data
        assert "ref" in data
        assert data["ref"].startswith("FLT-"), f"Ref should start with FLT-: {data['ref']}"

        # Verify reporter contact info in response
        assert "reporter" in data
        assert data["reporter"]["name"] == staff_payload["name"]
        assert data["reporter"]["email"] == staff_payload["email"].lower()
        assert data["reporter"]["mobile"] == staff_payload["mobile"]

        # Verify issue was created with contact details via manager API
        issue_id = data["id"]
        issue_resp = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=manager_headers)
        if issue_resp.status_code == 200:
            issue = issue_resp.json()
            assert issue.get("created_by_name") == staff_payload["name"]
            assert issue.get("created_by_email") == staff_payload["email"].lower()
            assert issue.get("created_by_mobile") == staff_payload["mobile"]
            assert issue.get("created_via") == "gym_floor"
            # Check timeline
            timeline = issue.get("timeline", [])
            if timeline:
                assert "(Gym Floor)" in timeline[0].get("by", "")

    def test_fault_with_staff_without_email_returns_400(self, manager_token, gym_floor_token):
        """POST /api/gym-floor/fault with staff_id of staff without email returns 400"""
        manager_headers = {"Authorization": f"Bearer {manager_token}"}
        gf_headers = {"X-Gym-Floor-Token": gym_floor_token}

        # We need to find or create a staff member without email
        # Since email is now required for new staff, we need to check if there's
        # an existing staff member without email (legacy data)
        staff_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=manager_headers)
        staff_list = staff_resp.json().get("staff", [])
        staff_without_email = next((s for s in staff_list if not s.get("email")), None)

        if not staff_without_email:
            # Skip if no staff without email exists (all have been updated)
            pytest.skip("No staff without email found - all staff have email")

        staff_id = staff_without_email["id"]

        # Get equipment
        eq_resp = requests.get(f"{BASE_URL}/api/gym-floor/equipment", headers=gf_headers)
        equipment = eq_resp.json().get("equipment", [])
        if not equipment:
            pytest.skip("No equipment available")
        equipment_id = equipment[0]["id"]

        # Try to log fault with staff without email
        fault_payload = {
            "staff_id": staff_id,
            "equipment_id": equipment_id,
            "issue_description": "TEST_Fault: Should fail due to missing email"
        }
        fault_resp = requests.post(f"{BASE_URL}/api/gym-floor/fault", json=fault_payload, headers=gf_headers)

        assert fault_resp.status_code == 400, f"Expected 400, got {fault_resp.status_code}: {fault_resp.text}"
        data = fault_resp.json()
        assert "contact details" in data.get("detail", "").lower() or "email" in data.get("detail", "").lower()

    def test_fault_without_staff_id_returns_422(self, gym_floor_token):
        """POST /api/gym-floor/fault without staff_id returns 422 (Pydantic validation)"""
        headers = {"X-Gym-Floor-Token": gym_floor_token}

        # Get equipment
        eq_resp = requests.get(f"{BASE_URL}/api/gym-floor/equipment", headers=headers)
        equipment = eq_resp.json().get("equipment", [])
        if not equipment:
            pytest.skip("No equipment available")
        equipment_id = equipment[0]["id"]

        # Try to log fault without staff_id
        fault_payload = {
            "equipment_id": equipment_id,
            "issue_description": "TEST_Fault: Missing staff_id"
        }
        fault_resp = requests.post(f"{BASE_URL}/api/gym-floor/fault", json=fault_payload, headers=headers)

        assert fault_resp.status_code == 422, f"Expected 422, got {fault_resp.status_code}: {fault_resp.text}"

    def test_fault_with_invalid_staff_id_returns_400(self, gym_floor_token):
        """POST /api/gym-floor/fault with non-existent staff_id returns 400"""
        headers = {"X-Gym-Floor-Token": gym_floor_token}

        # Get equipment
        eq_resp = requests.get(f"{BASE_URL}/api/gym-floor/equipment", headers=headers)
        equipment = eq_resp.json().get("equipment", [])
        if not equipment:
            pytest.skip("No equipment available")
        equipment_id = equipment[0]["id"]

        # Try to log fault with fake staff_id
        fault_payload = {
            "staff_id": "non-existent-staff-id-12345",
            "equipment_id": equipment_id,
            "issue_description": "TEST_Fault: Invalid staff_id"
        }
        fault_resp = requests.post(f"{BASE_URL}/api/gym-floor/fault", json=fault_payload, headers=headers)

        assert fault_resp.status_code == 400, f"Expected 400, got {fault_resp.status_code}: {fault_resp.text}"


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_staff(self, manager_token):
        """Clean up TEST_ prefixed staff"""
        headers = {"Authorization": f"Bearer {manager_token}"}

        staff_resp = requests.get(f"{BASE_URL}/api/gym-floor/staff", headers=headers)
        if staff_resp.status_code == 200:
            staff_list = staff_resp.json().get("staff", [])
            for s in staff_list:
                if s.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/gym-floor/staff/{s['id']}", headers=headers)

        assert True  # Cleanup always passes
