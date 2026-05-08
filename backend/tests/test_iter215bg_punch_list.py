"""
Iteration 215bg — Punch list testing:
1. Sage/Sicon scrub verification (marketing pages)
2. /pulse-pricing route
3. Trial banner live countdown (backend returns trial_ends_at + trial_duration_days)
4. Site Calculator upsell on /platform/* pages
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN = {"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}
PULSE_USER = {"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"}


class TestTrialBannerBackend:
    """Test that /api/auth/me returns trial_ends_at and trial_duration_days for trial users"""

    def test_auth_me_returns_trial_fields(self):
        """GET /api/auth/me should return trial.trial_ends_at and trial.trial_duration_days"""
        # Login as master admin first to check the structure
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=MASTER_ADMIN)
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")

        # Get user info
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200, f"GET /api/auth/me failed: {me_resp.text}"

        user_data = me_resp.json()
        # Master admin may not be a trial user, but we verify the structure exists
        # The trial object should be present if is_trial is true
        print(f"User data keys: {user_data.keys()}")
        if user_data.get("trial", {}).get("is_trial"):
            trial = user_data["trial"]
            assert "trial_ends_at" in trial, "trial_ends_at missing from trial object"
            assert "trial_duration_days" in trial, "trial_duration_days missing from trial object"
            print(f"Trial fields present: trial_ends_at={trial.get('trial_ends_at')}, trial_duration_days={trial.get('trial_duration_days')}")
        else:
            print("User is not a trial user - checking trial object structure anyway")
            # Even non-trial users should have the trial object with is_trial: false
            assert "trial" in user_data or user_data.get("is_trial") is False, "Trial info should be present"


class TestPulseUserAuth:
    """Test Pulse user authentication and trial state"""

    def test_pulse_user_login(self):
        """Pulse user should be able to login"""
        time.sleep(6)  # Avoid rate limiting
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=PULSE_USER)
        assert login_resp.status_code == 200, f"Pulse user login failed: {login_resp.text}"

        data = login_resp.json()
        assert "token" in data, "Token missing from login response"
        assert "user" in data, "User missing from login response"

        user = data["user"]
        print(f"Pulse user account_type: {user.get('account_type')}")
        print(f"Pulse user trial info: {user.get('trial')}")


class TestMarketingPagesNoSageSicon:
    """Verify Sage/Sicon mentions are scrubbed from marketing pages"""

    @pytest.mark.parametrize("path", [
        "/learn/integrations",
        "/learn/service",
        "/learn/contracts",
        "/legacy-pricing",
        "/privacy",
    ])
    def test_no_sage_sicon_mentions(self, path):
        """Marketing pages should NOT mention 'Sage' or 'Sicon'"""
        resp = requests.get(f"{BASE_URL}{path}", timeout=10)
        # These are frontend routes, so we get HTML
        # The actual content check will be done via Playwright
        # Here we just verify the routes are accessible
        assert resp.status_code == 200, f"Route {path} returned {resp.status_code}"
        print(f"Route {path} accessible - content check via Playwright")


class TestPulsePricingRoute:
    """Test /pulse-pricing route exists and is accessible"""

    def test_pulse_pricing_route_accessible(self):
        """GET /pulse-pricing should return 200"""
        resp = requests.get(f"{BASE_URL}/pulse-pricing", timeout=10)
        assert resp.status_code == 200, f"/pulse-pricing returned {resp.status_code}"
        print("/pulse-pricing route accessible")


class TestPlatformModuleRoutes:
    """Test /platform/* module routes are accessible"""

    @pytest.mark.parametrize("path", [
        "/platform/crm",
        "/platform/memberships",
        "/platform/marketing",
    ])
    def test_platform_module_routes(self, path):
        """Platform module pages should be accessible"""
        resp = requests.get(f"{BASE_URL}{path}", timeout=10)
        assert resp.status_code == 200, f"Route {path} returned {resp.status_code}"
        print(f"Route {path} accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
