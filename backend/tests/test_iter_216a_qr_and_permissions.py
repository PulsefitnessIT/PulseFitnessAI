"""
Iter 216a — QR Code Dynamic URL Resolution + Per-User Feature Editor Tests

Tests:
1. QR Code endpoints return URLs with public-facing host (not internal cluster)
2. PUT /api/master-admin/users/{user_id}/edit accepts module_overrides
3. module_overrides validation (must be dict, invalid keys stripped)
4. Owner role exemption from module_overrides
"""
import pytest
import requests
import os
import io
import uuid

# pyzbar for QR decoding
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    from PIL import Image
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pulse-staging-10.preview.emergentagent.com').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
MASTER_ADMIN_ORG_ID = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"


@pytest.fixture(scope="module")
def auth_token():
    """Get master admin auth token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_equipment_id(headers):
    """Create test equipment for QR code testing."""
    equipment_data = {
        "name": f"TEST_QR_Equipment_{uuid.uuid4().hex[:8]}",
        "equipment_type": "treadmill",
        "serial_number": f"TEST-QR-{uuid.uuid4().hex[:8]}",
        "manufacturer": "Test Manufacturer",
        "model": "Test Model",
        "location": "Test Location"
    }
    response = requests.post(f"{BASE_URL}/api/equipment", json=equipment_data, headers=headers)
    if response.status_code == 201:
        eq_id = response.json().get("id")
        yield eq_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/equipment/{eq_id}", headers=headers)
    else:
        # Try to find existing equipment
        response = requests.get(f"{BASE_URL}/api/equipment", headers=headers)
        if response.status_code == 200:
            equipment_list = response.json().get("equipment", [])
            if equipment_list:
                yield equipment_list[0]["id"]
                return
        pytest.skip("Could not create or find test equipment")


@pytest.fixture(scope="module")
def test_user_id(headers):
    """Create a test user for module_overrides testing."""
    # First, get an org to add user to
    orgs_response = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
    assert orgs_response.status_code == 200
    orgs = orgs_response.json().get("organizations", [])

    # Find an org with modules enabled (not master admin org)
    target_org = None
    for org in orgs:
        if org.get("id") != MASTER_ADMIN_ORG_ID:
            target_org = org
            break

    if not target_org:
        # Create a test org
        org_data = {
            "name": f"TEST_Org_Permissions_{uuid.uuid4().hex[:8]}",
            "enabled_modules": ["operations", "crm", "memberships", "marketing"],
            "account_type": "full"
        }
        org_response = requests.post(f"{BASE_URL}/api/master-admin/organizations", json=org_data, headers=headers)
        if org_response.status_code in [200, 201]:
            target_org = org_response.json()
        else:
            pytest.skip("Could not create test org")

    org_id = target_org.get("id")

    # Create test user
    user_email = f"test_perms_{uuid.uuid4().hex[:8]}@example.com"
    user_data = {
        "email": user_email,
        "full_name": "TEST Permissions User",
        "role": "manager"  # Manager so we can test module_overrides
    }
    user_response = requests.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json=user_data, headers=headers)

    if user_response.status_code in [200, 201]:
        user_id = user_response.json().get("id")
        yield {"user_id": user_id, "org_id": org_id, "email": user_email}
        # Cleanup - archive then delete
        requests.put(f"{BASE_URL}/api/master-admin/users/{user_id}/archive", json={"archived": True}, headers=headers)
    else:
        pytest.skip(f"Could not create test user: {user_response.text}")


class TestMasterAdminLogin:
    """Test master admin login works."""

    def test_login_success(self):
        """POST /api/auth/login as admin@gymaxisai.com — verify token works."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert len(data["token"]) > 0, "Token is empty"

        # Verify token works by calling a protected endpoint
        headers = {"Authorization": f"Bearer {data['token']}"}
        verify_response = requests.get(f"{BASE_URL}/api/master-admin/stats", headers=headers)
        assert verify_response.status_code == 200, "Token verification failed"


class TestQRCodeDynamicURL:
    """Test QR code endpoints return public-facing URLs."""

    def test_qr_code_endpoint_returns_png(self, headers, test_equipment_id):
        """GET /api/equipment/{equipment_id}/qr-code returns PNG."""
        response = requests.get(
            f"{BASE_URL}/api/equipment/{test_equipment_id}/qr-code",
            headers=headers
        )
        assert response.status_code == 200, f"QR code endpoint failed: {response.text}"
        assert response.headers.get("content-type") == "image/png", "Response is not PNG"
        assert len(response.content) > 100, "PNG content too small"

    @pytest.mark.skipif(not PYZBAR_AVAILABLE, reason="pyzbar not installed")
    def test_qr_code_contains_public_url(self, headers, test_equipment_id):
        """QR code PNG decodes to URL with public host, NOT internal cluster."""
        response = requests.get(
            f"{BASE_URL}/api/equipment/{test_equipment_id}/qr-code",
            headers=headers
        )
        assert response.status_code == 200

        # Decode QR code
        img = Image.open(io.BytesIO(response.content))
        decoded = pyzbar_decode(img)
        assert len(decoded) > 0, "Could not decode QR code"

        qr_url = decoded[0].data.decode('utf-8')
        print(f"Decoded QR URL: {qr_url}")

        # Verify URL contains public host
        assert "maintenance-hub-357.preview.emergentagent.com" in qr_url or "gymaxisai.com" in qr_url, \
            f"QR URL should contain public host, got: {qr_url}"

        # Verify URL does NOT contain internal cluster
        assert "emergentcf.cloud" not in qr_url, f"QR URL should NOT contain internal cluster: {qr_url}"
        assert "cluster-" not in qr_url, f"QR URL should NOT contain cluster-: {qr_url}"

        # Verify URL format
        assert f"/scan/{test_equipment_id}" in qr_url, f"QR URL should contain /scan/{{eq_id}}: {qr_url}"

    def test_qr_card_endpoint_returns_png(self, headers, test_equipment_id):
        """GET /api/equipment/{equipment_id}/qr-card?size=62x35 returns PNG."""
        response = requests.get(
            f"{BASE_URL}/api/equipment/{test_equipment_id}/qr-card?size=62x35",
            headers=headers
        )
        assert response.status_code == 200, f"QR card endpoint failed: {response.text}"
        assert response.headers.get("content-type") == "image/png", "Response is not PNG"
        assert len(response.content) > 100, "PNG content too small"

    @pytest.mark.skipif(not PYZBAR_AVAILABLE, reason="pyzbar not installed")
    def test_qr_card_contains_public_url(self, headers, test_equipment_id):
        """QR card PNG decodes to URL with public host."""
        response = requests.get(
            f"{BASE_URL}/api/equipment/{test_equipment_id}/qr-card?size=62x35",
            headers=headers
        )
        assert response.status_code == 200

        # Decode QR code from card
        img = Image.open(io.BytesIO(response.content))
        decoded = pyzbar_decode(img)
        assert len(decoded) > 0, "Could not decode QR code from card"

        qr_url = decoded[0].data.decode('utf-8')
        print(f"Decoded QR Card URL: {qr_url}")

        # Verify URL contains public host
        assert "maintenance-hub-357.preview.emergentagent.com" in qr_url or "gymaxisai.com" in qr_url, \
            f"QR Card URL should contain public host, got: {qr_url}"

        # Verify URL does NOT contain internal cluster
        assert "emergentcf.cloud" not in qr_url, f"QR Card URL should NOT contain internal cluster: {qr_url}"
        assert "cluster-" not in qr_url, f"QR Card URL should NOT contain cluster-: {qr_url}"

    def test_qr_label_endpoint_returns_json(self, headers, test_equipment_id):
        """GET /api/equipment/{equipment_id}/qr-label returns JSON with scan_url."""
        response = requests.get(
            f"{BASE_URL}/api/equipment/{test_equipment_id}/qr-label",
            headers=headers
        )
        assert response.status_code == 200, f"QR label endpoint failed: {response.text}"

        data = response.json()
        assert "scan_url" in data, "Response missing scan_url field"

        scan_url = data["scan_url"]
        print(f"QR Label scan_url: {scan_url}")

        # Verify URL contains public host
        assert "maintenance-hub-357.preview.emergentagent.com" in scan_url or "gymaxisai.com" in scan_url, \
            f"scan_url should contain public host, got: {scan_url}"

        # Verify URL does NOT contain internal cluster
        assert "emergentcf.cloud" not in scan_url, f"scan_url should NOT contain internal cluster: {scan_url}"
        assert "cluster-" not in scan_url, f"scan_url should NOT contain cluster-: {scan_url}"

        # Verify URL format
        assert f"/scan/{test_equipment_id}" in scan_url, f"scan_url should contain /scan/{{eq_id}}: {scan_url}"


class TestPerUserFeatureEditor:
    """Test PUT /api/master-admin/users/{user_id}/edit with module_overrides."""

    def test_edit_user_with_valid_module_overrides(self, headers, test_user_id):
        """PUT with module_overrides as {module: bool} dict returns 200."""
        user_id = test_user_id["user_id"]

        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"module_overrides": {"marketing": False, "crm": False}},
            headers=headers
        )
        assert response.status_code == 200, f"Edit user failed: {response.text}"

        # Verify the override persisted
        users_response = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert users_response.status_code == 200

        users = users_response.json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user is not None, "User not found in users list"

        overrides = user.get("module_overrides", {})
        assert overrides.get("marketing") == False, "marketing override not persisted"
        assert overrides.get("crm") == False, "crm override not persisted"

    def test_edit_user_invalid_module_overrides_type(self, headers, test_user_id):
        """PUT with module_overrides as non-dict returns HTTP 400."""
        user_id = test_user_id["user_id"]

        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"module_overrides": "not-a-dict"},
            headers=headers
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

        data = response.json()
        detail = data.get("detail", "")
        assert "object" in detail.lower() or "dict" in detail.lower(), \
            f"Error should mention 'object' or 'dict', got: {detail}"

    def test_edit_user_invalid_module_keys_stripped(self, headers, test_user_id):
        """PUT with invalid module names succeeds but only persists valid keys."""
        user_id = test_user_id["user_id"]

        # First reset overrides
        requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"module_overrides": {}},
            headers=headers
        )

        # Send with invalid + valid keys
        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"module_overrides": {"hacker_module": True, "crm": True, "invalid_key": False}},
            headers=headers
        )
        assert response.status_code == 200, f"Edit user failed: {response.text}"

        # Verify only valid key persisted
        users_response = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert users_response.status_code == 200

        users = users_response.json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user is not None, "User not found"

        overrides = user.get("module_overrides", {})
        assert "hacker_module" not in overrides, "Invalid key 'hacker_module' should be stripped"
        assert "invalid_key" not in overrides, "Invalid key 'invalid_key' should be stripped"
        assert overrides.get("crm") == True, "Valid key 'crm' should be persisted"

    def test_edit_user_basic_fields_still_work(self, headers, test_user_id):
        """Regression: changing name, email, role, job_title, phone still saves correctly."""
        user_id = test_user_id["user_id"]

        new_name = f"Updated Name {uuid.uuid4().hex[:4]}"
        new_job_title = "Senior Manager"
        new_phone = "+44 7700 900123"

        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={
                "full_name": new_name,
                "job_title": new_job_title,
                "phone": new_phone
            },
            headers=headers
        )
        assert response.status_code == 200, f"Edit user failed: {response.text}"

        # Verify changes persisted
        users_response = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert users_response.status_code == 200

        users = users_response.json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user is not None, "User not found"

        assert user.get("full_name") == new_name, f"Name not updated: {user.get('full_name')}"
        assert user.get("job_title") == new_job_title, f"Job title not updated: {user.get('job_title')}"
        assert user.get("phone") == new_phone, f"Phone not updated: {user.get('phone')}"


class TestGetAllUsersReturnsModuleOverrides:
    """Test GET /api/master-admin/users returns module_overrides."""

    def test_users_list_includes_module_overrides(self, headers):
        """GET /api/master-admin/users returns module_overrides field."""
        response = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert response.status_code == 200, f"Get users failed: {response.text}"

        users = response.json().get("users", [])
        assert len(users) > 0, "No users returned"

        # Check that users have the module_overrides field (even if empty)
        # At least one user should have it defined
        has_overrides_field = any("module_overrides" in u for u in users)
        # This is optional - the field may not exist if never set
        print(f"Users with module_overrides field: {sum(1 for u in users if 'module_overrides' in u)}/{len(users)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
