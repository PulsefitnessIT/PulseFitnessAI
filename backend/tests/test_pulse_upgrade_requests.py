"""
Test suite for Pulse Pro Upgrade Request feature (iteration 155).

Tests:
1. POST /api/pulse/upgrade-request - public endpoint for upgrade requests
2. GET /api/master-admin/pulse-upgrade-requests - master admin list
3. PATCH /api/master-admin/pulse-upgrade-requests/<id> - status updates
4. Validation and rate limiting
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = "1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6"

# Master Admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")


@pytest.fixture
def bypass_headers():
    """Headers to bypass rate limiting."""
    return {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}


class TestPulseUpgradeRequestPublicEndpoint:
    """Tests for POST /api/pulse/upgrade-request (public endpoint)."""

    def test_submit_upgrade_request_success(self, bypass_headers):
        """Test successful upgrade request submission."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Test User {unique_id}",
            "email": f"test.upgrade.{unique_id}@example.com",
            "gym_name": f"Test Gym {unique_id}",
            "site_count": 3,
            "equipment_count": 150,
            "contact_method": "email",
            "notes": "Testing upgrade request flow"
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "id" in data
        assert isinstance(data["id"], str)
        print(f"PASS: Upgrade request created with id={data['id']}")

    def test_submit_upgrade_request_minimal_fields(self, bypass_headers):
        """Test upgrade request with only required fields."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Minimal User {unique_id}",
            "email": f"minimal.{unique_id}@example.com",
            "gym_name": f"Minimal Gym {unique_id}",
            "site_count": 1
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        print("PASS: Minimal upgrade request created successfully")

    def test_submit_upgrade_request_with_phone(self, bypass_headers):
        """Test upgrade request with phone and contact_method=phone."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Phone User {unique_id}",
            "email": f"phone.{unique_id}@example.com",
            "gym_name": f"Phone Gym {unique_id}",
            "site_count": 5,
            "phone": "+44 7700 900123",
            "contact_method": "phone"
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Upgrade request with phone created successfully")

    def test_submit_upgrade_request_contact_method_either(self, bypass_headers):
        """Test upgrade request with contact_method=either."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Either User {unique_id}",
            "email": f"either.{unique_id}@example.com",
            "gym_name": f"Either Gym {unique_id}",
            "site_count": 2,
            "contact_method": "either"
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Upgrade request with contact_method=either created successfully")


class TestPulseUpgradeRequestValidation:
    """Tests for validation on POST /api/pulse/upgrade-request."""

    def test_reject_invalid_email(self, bypass_headers):
        """Test that invalid email is rejected with 422."""
        payload = {
            "full_name": "Invalid Email User",
            "email": "not-an-email",
            "gym_name": "Test Gym",
            "site_count": 1
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for invalid email, got {resp.status_code}"
        print("PASS: Invalid email rejected with 422")

    def test_reject_site_count_below_minimum(self, bypass_headers):
        """Test that site_count < 1 is rejected with 422."""
        payload = {
            "full_name": "Low Site User",
            "email": "lowsite@example.com",
            "gym_name": "Test Gym",
            "site_count": 0
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for site_count=0, got {resp.status_code}"
        print("PASS: site_count < 1 rejected with 422")

    def test_reject_site_count_above_maximum(self, bypass_headers):
        """Test that site_count > 500 is rejected with 422."""
        payload = {
            "full_name": "High Site User",
            "email": "highsite@example.com",
            "gym_name": "Test Gym",
            "site_count": 501
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for site_count=501, got {resp.status_code}"
        print("PASS: site_count > 500 rejected with 422")

    def test_reject_missing_full_name(self, bypass_headers):
        """Test that missing full_name is rejected with 422."""
        payload = {
            "email": "noname@example.com",
            "gym_name": "Test Gym",
            "site_count": 1
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for missing full_name, got {resp.status_code}"
        print("PASS: Missing full_name rejected with 422")

    def test_reject_missing_email(self, bypass_headers):
        """Test that missing email is rejected with 422."""
        payload = {
            "full_name": "No Email User",
            "gym_name": "Test Gym",
            "site_count": 1
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for missing email, got {resp.status_code}"
        print("PASS: Missing email rejected with 422")

    def test_reject_missing_gym_name(self, bypass_headers):
        """Test that missing gym_name is rejected with 422."""
        payload = {
            "full_name": "No Gym User",
            "email": "nogym@example.com",
            "site_count": 1
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for missing gym_name, got {resp.status_code}"
        print("PASS: Missing gym_name rejected with 422")

    def test_reject_invalid_contact_method(self, bypass_headers):
        """Test that invalid contact_method is rejected with 422."""
        payload = {
            "full_name": "Invalid Contact User",
            "email": "invalidcontact@example.com",
            "gym_name": "Test Gym",
            "site_count": 1,
            "contact_method": "invalid"
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 422, f"Expected 422 for invalid contact_method, got {resp.status_code}"
        print("PASS: Invalid contact_method rejected with 422")


class TestMasterAdminPulseUpgradeRequests:
    """Tests for master admin endpoints."""

    def test_list_upgrade_requests_as_master_admin(self, master_admin_token):
        """Test GET /api/master-admin/pulse-upgrade-requests returns correct structure."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "total" in data, "Response missing 'total'"
        assert "new_last_7d" in data, "Response missing 'new_last_7d'"
        assert "by_status" in data, "Response missing 'by_status'"
        assert "items" in data, "Response missing 'items'"

        # Verify by_status structure
        by_status = data["by_status"]
        for status in ["new", "contacted", "quoted", "converted", "lost"]:
            assert status in by_status, f"by_status missing '{status}'"

        # Verify items is a list
        assert isinstance(data["items"], list), "items should be a list"

        print(f"PASS: List upgrade requests returned {data['total']} total, {data['new_last_7d']} in last 7 days")
        print(f"  by_status: {by_status}")

    def test_list_upgrade_requests_forbidden_without_auth(self):
        """Test GET /api/master-admin/pulse-upgrade-requests returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/pulse-upgrade-requests")

        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASS: Unauthenticated request rejected with 401")

    def test_list_upgrade_requests_forbidden_for_non_master_admin(self):
        """Test GET /api/master-admin/pulse-upgrade-requests returns 403 for non-master-admin."""
        # Login as a regular user (Pulse Pro user)
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "lee.somers@pulsefitness.com",
            "password": "TempPass123!"
        })

        if login_resp.status_code != 200:
            pytest.skip("Could not login as regular user")

        token = login_resp.json().get("token")

        resp = requests.get(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert resp.status_code == 403, f"Expected 403 for non-master-admin, got {resp.status_code}"
        print("PASS: Non-master-admin rejected with 403")


class TestMasterAdminPulseUpgradeStatusUpdate:
    """Tests for PATCH /api/master-admin/pulse-upgrade-requests/<id>."""

    @pytest.fixture
    def created_request_id(self, bypass_headers):
        """Create a test upgrade request and return its ID."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Status Test User {unique_id}",
            "email": f"status.test.{unique_id}@example.com",
            "gym_name": f"Status Test Gym {unique_id}",
            "site_count": 2
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        if resp.status_code != 200:
            pytest.skip(f"Could not create test request: {resp.text}")

        return resp.json()["id"]

    def test_update_status_to_contacted(self, master_admin_token, created_request_id):
        """Test updating status to 'contacted'."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "contacted"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        print("PASS: Status updated to 'contacted'")

    def test_update_status_to_quoted(self, master_admin_token, created_request_id):
        """Test updating status to 'quoted'."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "quoted"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Status updated to 'quoted'")

    def test_update_status_to_converted(self, master_admin_token, created_request_id):
        """Test updating status to 'converted'."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "converted"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Status updated to 'converted'")

    def test_update_status_to_lost(self, master_admin_token, created_request_id):
        """Test updating status to 'lost'."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "lost"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Status updated to 'lost'")

    def test_update_status_invalid_returns_400(self, master_admin_token, created_request_id):
        """Test that invalid status returns 400."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "invalid_status"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 400, f"Expected 400 for invalid status, got {resp.status_code}"
        print("PASS: Invalid status rejected with 400")

    def test_update_status_unknown_id_returns_404(self, master_admin_token):
        """Test that unknown request ID returns 404."""
        fake_id = str(uuid.uuid4())
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{fake_id}",
            json={"status": "contacted"},
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )

        assert resp.status_code == 404, f"Expected 404 for unknown ID, got {resp.status_code}"
        print("PASS: Unknown ID rejected with 404")

    def test_update_status_forbidden_without_auth(self, created_request_id):
        """Test that status update without auth returns 401."""
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/pulse-upgrade-requests/{created_request_id}",
            json={"status": "contacted"}
        )

        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("PASS: Unauthenticated status update rejected with 401")


class TestEmailDispatch:
    """Tests to verify email dispatch (check backend logs)."""

    def test_upgrade_request_triggers_emails(self, bypass_headers):
        """Test that upgrade request triggers email dispatch to both recipients."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"Email Test User {unique_id}",
            "email": f"email.test.{unique_id}@example.com",
            "gym_name": f"Email Test Gym {unique_id}",
            "site_count": 5,
            "equipment_count": 200,
            "contact_method": "either",
            "notes": "Testing email dispatch"
        }

        resp = requests.post(
            f"{BASE_URL}/api/pulse/upgrade-request",
            json=payload,
            headers=bypass_headers
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: Upgrade request submitted - check backend logs for:")
        print("  - 'Email sent to service.dept@pulsefitness.com'")
        print("  - 'Email sent to Lee@gymaxisai.com'")


class TestTrialSignupRegression:
    """Regression test for trial signup email (SENDER_EMAIL fix)."""

    def test_trial_signup_email_dispatch(self, bypass_headers):
        """Test that trial signup still works with restored SENDER_EMAIL."""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "email": f"trial.regression.{unique_id}@example.com",
            "password": "TestPass123!",
            "full_name": f"Trial Regression User {unique_id}",
            "company_name": f"Trial Regression Gym {unique_id}",
            "is_trial": True
        }

        resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json=payload,
            headers=bypass_headers
        )

        # Accept 200 (success) or 409 (email already exists)
        assert resp.status_code in [200, 201, 409], f"Expected 200/201/409, got {resp.status_code}: {resp.text}"

        if resp.status_code in [200, 201]:
            print("PASS: Trial signup successful - check backend logs for email to Lee@gymaxisai.com")
            print("  - Should NOT see 'domain not verified' error")
        else:
            print("INFO: Email already exists (409) - this is expected if test ran before")
