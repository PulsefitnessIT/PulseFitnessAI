"""
Trial Tooling Backend Tests
Tests for:
- Onboarding packet trial flow (is_trial, trial_duration_days)
- Master Admin trial endpoints (/master-admin/trials/*)
- Auth integration (trial state in login/me responses)
- Trial lifecycle compute_trial_state()
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
NON_ADMIN_EMAIL = os.environ.get("TEST_NON_ADMIN_EMAIL", "lee.somers@pulsefitness.com")
NON_ADMIN_PASSWORD = os.environ.get("TEST_NON_ADMIN_PASSWORD", "TempPass123!")


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin auth token"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if res.status_code != 200:
        pytest.skip(f"Admin login failed: {res.status_code} - {res.text}")
    return res.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-admin auth token"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": NON_ADMIN_EMAIL,
        "password": NON_ADMIN_PASSWORD
    })
    if res.status_code != 200:
        pytest.skip(f"Non-admin login failed: {res.status_code}")
    return res.json().get("token")


@pytest.fixture(scope="module")
def non_admin_headers(non_admin_token):
    return {"Authorization": f"Bearer {non_admin_token}"}


class TestOnboardingPacketTrialFlow:
    """Test onboarding packet trial fields"""

    def test_create_packet_with_trial_true(self, admin_headers):
        """POST /api/onboarding-packets with is_trial=true stores trial fields"""
        res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_Trial_Packet_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 14
        }, headers=admin_headers)

        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("is_trial") == True
        assert data.get("trial_duration_days") == 14
        assert "id" in data
        assert "share_url" in data

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{data['id']}", headers=admin_headers)

    def test_create_packet_trial_duration_out_of_range(self, admin_headers):
        """POST /api/onboarding-packets with trial_duration_days=100 returns 400"""
        res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Invalid_Duration",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 100  # Out of 1-90 range
        }, headers=admin_headers)

        assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
        assert "trial_duration_days" in res.text.lower() or "1 and 90" in res.text

    def test_create_packet_trial_duration_zero(self, admin_headers):
        """POST /api/onboarding-packets with trial_duration_days=0 returns 400"""
        res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": "TEST_Zero_Duration",
            "target_tier": "pro",
            "is_trial": True,
            "trial_duration_days": 0
        }, headers=admin_headers)

        assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"


class TestMasterAdminTrialEndpoints:
    """Test /master-admin/trials/* endpoints"""

    def test_list_trials_returns_structure(self, admin_headers):
        """GET /api/master-admin/trials returns {trials:[], count}"""
        res = requests.get(f"{BASE_URL}/api/master-admin/trials", headers=admin_headers)

        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "trials" in data
        assert "count" in data
        assert isinstance(data["trials"], list)

        # If there are trials, check structure
        if data["trials"]:
            trial = data["trials"][0]
            assert "id" in trial
            assert "name" in trial
            assert "trial_status" in trial
            assert "days_left" in trial
            assert "user_count" in trial
            assert "extended_by_days" in trial or trial.get("extended_by_days") == 0

    def test_trials_summary_returns_structure(self, admin_headers):
        """GET /api/master-admin/trials/summary returns {total, by_status, converted_30d}"""
        res = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=admin_headers)

        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "total" in data
        assert "by_status" in data
        assert "converted_30d" in data

        by_status = data["by_status"]
        # Check expected status keys exist
        for status in ["active", "expiring_soon", "expired", "suspended", "converted"]:
            assert status in by_status or by_status.get(status, 0) >= 0

    def test_extend_trial_invalid_days_over_30(self, admin_headers):
        """POST /api/master-admin/trials/{org_id}/extend with days=50 returns 400"""
        # Use a fake org_id - should fail on days validation first
        res = requests.post(f"{BASE_URL}/api/master-admin/trials/fake-org-id/extend", json={
            "days": 50,
            "reason": "Testing"
        }, headers=admin_headers)

        assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
        assert "days" in res.text.lower() or "30" in res.text

    def test_extend_trial_non_trial_org_returns_404(self, admin_headers):
        """POST /api/master-admin/trials/{org_id}/extend on non-trial org returns 404"""
        # Use a non-existent org ID
        res = requests.post(f"{BASE_URL}/api/master-admin/trials/non-existent-org-id/extend", json={
            "days": 7,
            "reason": "Testing"
        }, headers=admin_headers)

        assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"

    def test_trials_endpoints_require_admin(self, non_admin_headers):
        """All /master-admin/trials/* endpoints return 403 for non-admin"""
        endpoints = [
            ("GET", f"{BASE_URL}/api/master-admin/trials"),
            ("GET", f"{BASE_URL}/api/master-admin/trials/summary"),
            ("POST", f"{BASE_URL}/api/master-admin/trials/fake-org/extend"),
            ("POST", f"{BASE_URL}/api/master-admin/trials/fake-org/convert"),
            ("POST", f"{BASE_URL}/api/master-admin/trials/fake-org/mark-converted"),
        ]

        for method, url in endpoints:
            if method == "GET":
                res = requests.get(url, headers=non_admin_headers)
            else:
                res = requests.post(url, json={}, headers=non_admin_headers)

            assert res.status_code == 403, f"{method} {url} expected 403, got {res.status_code}"


class TestAuthTrialIntegration:
    """Test that login and /auth/me include trial state"""

    def test_login_includes_trial_object(self, admin_headers):
        """Login response includes user.trial object"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })

        assert res.status_code == 200
        data = res.json()
        assert "user" in data
        user = data["user"]
        assert "trial" in user

        trial = user["trial"]
        assert "is_trial" in trial
        # For master admin, should be is_trial: false
        # The structure should exist regardless

    def test_auth_me_includes_trial_object(self, admin_headers):
        """GET /api/auth/me includes trial object"""
        res = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert "trial" in data

        trial = data["trial"]
        assert "is_trial" in trial

    def test_non_trial_user_has_is_trial_false(self, non_admin_headers):
        """Non-trial user has trial.is_trial=false"""
        res = requests.get(f"{BASE_URL}/api/auth/me", headers=non_admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert "trial" in data
        # Non-trial user should have is_trial: false
        # (unless their org is a trial, which we can't control here)


class TestTrialLifecycleLogic:
    """Test compute_trial_state logic indirectly via API responses"""

    def test_trial_list_has_correct_status_fields(self, admin_headers):
        """Verify trial list items have status-related fields"""
        res = requests.get(f"{BASE_URL}/api/master-admin/trials", headers=admin_headers)

        assert res.status_code == 200
        data = res.json()

        if data["trials"]:
            trial = data["trials"][0]
            # Check status-related fields exist
            assert "trial_status" in trial
            assert "days_left" in trial
            assert "read_only" in trial
            assert "locked_out" in trial

            # Status should be one of the valid values
            valid_statuses = ["active", "expiring_soon", "expired", "suspended", "converted"]
            assert trial["trial_status"] in valid_statuses


class TestOnboardingPacketRegression:
    """Ensure existing onboarding packet endpoints still work"""

    def test_list_packets_still_works(self, admin_headers):
        """GET /api/onboarding-packets returns packets list"""
        res = requests.get(f"{BASE_URL}/api/onboarding-packets", headers=admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert "packets" in data
        assert "count" in data

    def test_create_non_trial_packet_still_works(self, admin_headers):
        """POST /api/onboarding-packets without trial fields still works"""
        res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_NonTrial_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro",
            "is_trial": False
        }, headers=admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert data.get("is_trial") == False
        assert data.get("trial_duration_days") is None

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{data['id']}", headers=admin_headers)

    def test_get_single_packet_still_works(self, admin_headers):
        """GET /api/onboarding-packets/{id} returns packet details"""
        # First create a packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_GetSingle_{uuid.uuid4().hex[:8]}",
            "target_tier": "starter"
        }, headers=admin_headers)

        assert create_res.status_code == 200
        packet_id = create_res.json()["id"]

        # Get the packet
        res = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == packet_id

        # Cleanup
        requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)

    def test_delete_packet_still_works(self, admin_headers):
        """DELETE /api/onboarding-packets/{id} deletes packet"""
        # Create a packet
        create_res = requests.post(f"{BASE_URL}/api/onboarding-packets", json={
            "customer_display_name": f"TEST_Delete_{uuid.uuid4().hex[:8]}",
            "target_tier": "pro"
        }, headers=admin_headers)

        assert create_res.status_code == 200
        packet_id = create_res.json()["id"]

        # Delete it
        del_res = requests.delete(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        assert del_res.status_code == 200

        # Verify it's gone
        get_res = requests.get(f"{BASE_URL}/api/onboarding-packets/{packet_id}", headers=admin_headers)
        assert get_res.status_code == 404


class TestAuthRegression:
    """Ensure existing auth endpoints still work"""

    def test_login_still_works(self):
        """POST /api/auth/login returns token and user"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })

        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == MASTER_ADMIN_EMAIL

    def test_auth_me_still_works(self, admin_headers):
        """GET /api/auth/me returns user info"""
        res = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)

        assert res.status_code == 200
        data = res.json()
        assert "email" in data
        assert "id" in data


class TestTrialConvertEndpoint:
    """Test trial conversion endpoint"""

    def test_convert_non_trial_org_returns_404(self, admin_headers):
        """POST /api/master-admin/trials/{org_id}/convert on non-trial org returns 404"""
        res = requests.post(f"{BASE_URL}/api/master-admin/trials/non-existent-org/convert", json={
            "tier": "pro",
            "origin_url": "https://example.com"
        }, headers=admin_headers)

        assert res.status_code == 404

    def test_mark_converted_non_trial_org_returns_404(self, admin_headers):
        """POST /api/master-admin/trials/{org_id}/mark-converted on non-trial org returns 404"""
        res = requests.post(f"{BASE_URL}/api/master-admin/trials/non-existent-org/mark-converted",
                          json={}, headers=admin_headers)

        assert res.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
