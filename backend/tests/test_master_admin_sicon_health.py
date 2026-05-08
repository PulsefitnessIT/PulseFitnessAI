"""
Test Master Admin Sicon Health Endpoints (iteration 122)
Tests the new /master-admin/sicon/health, /sicon/test-all, /sicon/poll-all endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
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
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Master admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-admin user token for 403 tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Non-admin login failed: {response.status_code}")


class TestSiconHealthEndpoint:
    """Tests for GET /api/master-admin/sicon/health"""

    # ── Expected field sets (module-level constants — easy to extend) ────
    _REQUIRED_TOP_KEYS = ("organizations", "totals")
    _REQUIRED_TOTAL_KEYS = (
        "total_orgs", "configured", "enabled", "connected",
        "total_pending_queue", "total_failed_queue", "total_synced_issues",
    )
    _REQUIRED_ORG_KEYS = (
        "organization_id", "organization_name", "configured", "enabled",
        "connection_status", "pending_queue", "failed_queue", "synced_issues",
    )
    _OPTIONAL_ORG_KEYS = ("last_poll_at", "last_tested_at", "base_url", "last_error")

    def _fetch_health(self, master_admin_token):
        response = requests.get(
            f"{BASE_URL}/api/master-admin/sicon/health",
            headers={"Authorization": f"Bearer {master_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        return response.json()

    def test_sicon_health_with_master_admin(self, master_admin_token):
        """Master admin can access sicon health endpoint (smoke test + top-level shape)."""
        data = self._fetch_health(master_admin_token)
        for key in self._REQUIRED_TOP_KEYS:
            assert key in data, f"Response missing key '{key}'"
        assert isinstance(data["organizations"], list)

    def test_sicon_health_totals_shape(self, master_admin_token):
        """Totals block has every required counter."""
        totals = self._fetch_health(master_admin_token)["totals"]
        missing = [k for k in self._REQUIRED_TOTAL_KEYS if k not in totals]
        assert not missing, f"Totals missing keys: {missing}"

    def test_sicon_health_first_org_shape(self, master_admin_token):
        """Per-org records carry the full required field set (when any orgs exist)."""
        orgs = self._fetch_health(master_admin_token)["organizations"]
        if not orgs:
            pytest.skip("No Sicon-configured orgs — nothing to verify")
        org = orgs[0]
        missing = [k for k in self._REQUIRED_ORG_KEYS if k not in org]
        assert not missing, f"Org missing keys: {missing}"
        # Optional keys are allowed to be absent or null — no assertion needed here.

    def test_sicon_health_without_auth(self):
        """Sicon health endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/master-admin/sicon/health")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✓ Sicon health returns {response.status_code} without auth")

    def test_sicon_health_with_non_admin(self, non_admin_token):
        """Non-admin users get 403 on sicon health endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/sicon/health",
            headers={"Authorization": f"Bearer {non_admin_token}"}
        )
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("✓ Sicon health returns 403 for non-admin user")


class TestSiconTestAllEndpoint:
    """Tests for POST /api/master-admin/sicon/test-all"""

    def test_sicon_test_all_with_master_admin(self, master_admin_token):
        """Master admin can trigger test-all connections"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/sicon/test-all",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "tested" in data, "Response should have 'tested' count"
        assert "results" in data, "Response should have 'results' list"
        assert isinstance(data["results"], list)

        # Even with 0 enabled orgs, should return successfully
        print(f"✓ Test-all completed: tested {data['tested']} orgs")

    def test_sicon_test_all_without_auth(self):
        """Test-all requires authentication"""
        response = requests.post(f"{BASE_URL}/api/master-admin/sicon/test-all", json={})
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Test-all returns {response.status_code} without auth")

    def test_sicon_test_all_with_non_admin(self, non_admin_token):
        """Non-admin users get 403 on test-all"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/sicon/test-all",
            headers={"Authorization": f"Bearer {non_admin_token}"},
            json={}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Test-all returns 403 for non-admin")


class TestSiconPollAllEndpoint:
    """Tests for POST /api/master-admin/sicon/poll-all"""

    def test_sicon_poll_all_with_master_admin(self, master_admin_token):
        """Master admin can trigger poll-all"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/sicon/poll-all",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "polled" in data, "Response should have 'polled' count"
        assert "results" in data, "Response should have 'results' list"
        assert isinstance(data["results"], list)

        # Even with 0 enabled orgs, should return successfully
        print(f"✓ Poll-all completed: polled {data['polled']} orgs")

    def test_sicon_poll_all_without_auth(self):
        """Poll-all requires authentication"""
        response = requests.post(f"{BASE_URL}/api/master-admin/sicon/poll-all", json={})
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Poll-all returns {response.status_code} without auth")

    def test_sicon_poll_all_with_non_admin(self, non_admin_token):
        """Non-admin users get 403 on poll-all"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/sicon/poll-all",
            headers={"Authorization": f"Bearer {non_admin_token}"},
            json={}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Poll-all returns 403 for non-admin")


class TestRegressionSiconEndpoints:
    """Regression tests for existing Sicon endpoints from iteration 121"""

    def test_sicon_config_get(self, master_admin_token):
        """GET /api/sicon/config still works"""
        response = requests.get(
            f"{BASE_URL}/api/sicon/config",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/sicon/config works")

    def test_sicon_sync_queue(self, master_admin_token):
        """GET /api/sicon/sync-queue still works"""
        response = requests.get(
            f"{BASE_URL}/api/sicon/sync-queue",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/sicon/sync-queue works")

    def test_sicon_poll_updates(self, master_admin_token):
        """POST /api/sicon/poll-updates still works"""
        response = requests.post(
            f"{BASE_URL}/api/sicon/poll-updates",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            json={}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ POST /api/sicon/poll-updates works")


class TestRegressionMasterAdminEndpoints:
    """Regression tests for other Master Admin endpoints"""

    def test_master_admin_organizations(self, master_admin_token):
        """GET /api/master-admin/organizations still works"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "organizations" in data
        print(f"✓ Master admin organizations: {len(data['organizations'])} orgs")

    def test_master_admin_stats(self, master_admin_token):
        """GET /api/master-admin/stats still works"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/stats",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Master admin stats works")

    def test_master_admin_payments(self, master_admin_token):
        """Master admin can view payment-related stats"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/stats",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "payments" in data or "mrr" in data
        print("✓ Master admin payments/stats accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
