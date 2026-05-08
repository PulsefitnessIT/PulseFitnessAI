"""
Test Trial Funnel Analytics Widget - Iteration 127
Tests the enhanced /api/master-admin/trials/summary endpoint with new fields:
- ended_30d, conversion_rate_30d, avg_days_to_convert, expiring_this_week, by_source
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level token cache to avoid rate limiting
_token_cache = {}

def get_admin_token():
    """Get admin token with caching to avoid rate limiting"""
    if 'admin' not in _token_cache:
        time.sleep(1)  # Small delay to avoid rate limiting
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        if login_resp.status_code == 200:
            _token_cache['admin'] = login_resp.json()["token"]
        else:
            pytest.skip(f"Admin login failed: {login_resp.text}")
    return _token_cache['admin']

def get_non_admin_token():
    """Get non-admin token with caching"""
    if 'non_admin' not in _token_cache:
        time.sleep(1)
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "lee.somers@pulsefitness.com",
            "password": "TempPass123!"
        })
        if login_resp.status_code == 200:
            _token_cache['non_admin'] = login_resp.json()["token"]
        else:
            _token_cache['non_admin'] = None
    return _token_cache['non_admin']


class TestTrialFunnelAnalytics:
    """Tests for the enhanced trials/summary endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get tokens for authenticated requests"""
        self.admin_token = get_admin_token()
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        self.non_admin_token = get_non_admin_token()
        if self.non_admin_token:
            self.non_admin_headers = {"Authorization": f"Bearer {self.non_admin_token}"}
        else:
            self.non_admin_headers = {}

    def test_trials_summary_returns_new_fields(self):
        """Test that /api/master-admin/trials/summary returns all new fields"""
        resp = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=self.admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()

        # Check existing fields still present
        assert "total" in data, "Missing 'total' field"
        assert "by_status" in data, "Missing 'by_status' field"
        assert "converted_30d" in data, "Missing 'converted_30d' field"

        # Check new fields added in this iteration
        assert "ended_30d" in data, "Missing 'ended_30d' field (new)"
        assert "conversion_rate_30d" in data, "Missing 'conversion_rate_30d' field (new)"
        assert "avg_days_to_convert" in data, "Missing 'avg_days_to_convert' field (new)"
        assert "expiring_this_week" in data, "Missing 'expiring_this_week' field (new)"
        assert "by_source" in data, "Missing 'by_source' field (new)"

        # Validate data types
        assert isinstance(data["ended_30d"], int), "ended_30d should be int"
        assert isinstance(data["conversion_rate_30d"], (int, float)), "conversion_rate_30d should be numeric"
        assert isinstance(data["avg_days_to_convert"], (int, float)), "avg_days_to_convert should be numeric"
        assert isinstance(data["expiring_this_week"], int), "expiring_this_week should be int"
        assert isinstance(data["by_source"], dict), "by_source should be dict"

        # Validate by_source structure
        assert "crm_linked" in data["by_source"], "by_source missing 'crm_linked'"
        assert "direct" in data["by_source"], "by_source missing 'direct'"

        print(f"✓ trials/summary returns all new fields: ended_30d={data['ended_30d']}, "
              f"conversion_rate_30d={data['conversion_rate_30d']}, avg_days_to_convert={data['avg_days_to_convert']}, "
              f"expiring_this_week={data['expiring_this_week']}, by_source={data['by_source']}")

    def test_trials_summary_by_status_structure(self):
        """Test that by_status contains all expected status keys"""
        resp = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=self.admin_headers)
        assert resp.status_code == 200

        data = resp.json()
        by_status = data["by_status"]

        expected_statuses = ["active", "expiring_soon", "expired", "suspended", "converted"]
        for status in expected_statuses:
            assert status in by_status, f"Missing status '{status}' in by_status"
            assert isinstance(by_status[status], int), f"by_status['{status}'] should be int"

        print(f"✓ by_status contains all expected keys: {by_status}")

    def test_trials_list_endpoint_regression(self):
        """Test that existing /api/master-admin/trials endpoint still works"""
        resp = requests.get(f"{BASE_URL}/api/master-admin/trials", headers=self.admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "trials" in data, "Missing 'trials' field"
        assert "count" in data, "Missing 'count' field"
        assert isinstance(data["trials"], list), "trials should be a list"
        assert isinstance(data["count"], int), "count should be int"

        print(f"✓ /api/master-admin/trials regression passed: count={data['count']}")

    def test_non_admin_gets_403_on_trials_summary(self):
        """Test that non-master-admin users get 403 on /api/master-admin/trials/summary"""
        if not self.non_admin_token:
            pytest.skip("Non-admin user login failed, skipping test")

        resp = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=self.non_admin_headers)
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "detail" in data, "Expected error detail in response"

        print(f"✓ Non-admin correctly gets 403: {data['detail']}")

    def test_non_admin_gets_403_on_trials_list(self):
        """Test that non-master-admin users get 403 on /api/master-admin/trials"""
        if not self.non_admin_token:
            pytest.skip("Non-admin user login failed, skipping test")

        resp = requests.get(f"{BASE_URL}/api/master-admin/trials", headers=self.non_admin_headers)
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}: {resp.text}"

        print("✓ Non-admin correctly gets 403 on /api/master-admin/trials")

    def test_conversion_rate_calculation(self):
        """Test that conversion_rate_30d is calculated correctly"""
        resp = requests.get(f"{BASE_URL}/api/master-admin/trials/summary", headers=self.admin_headers)
        assert resp.status_code == 200

        data = resp.json()
        converted_30d = data["converted_30d"]
        ended_30d = data["ended_30d"]
        conversion_rate = data["conversion_rate_30d"]

        # If ended_30d > 0, rate should be (converted_30d / ended_30d) * 100
        if ended_30d > 0:
            expected_rate = round((converted_30d / ended_30d) * 100, 1)
            assert abs(conversion_rate - expected_rate) < 0.2, \
                f"Conversion rate mismatch: expected ~{expected_rate}, got {conversion_rate}"
        else:
            assert conversion_rate == 0, "Conversion rate should be 0 when no trials ended"

        print(f"✓ Conversion rate calculation correct: {converted_30d}/{ended_30d} = {conversion_rate}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
