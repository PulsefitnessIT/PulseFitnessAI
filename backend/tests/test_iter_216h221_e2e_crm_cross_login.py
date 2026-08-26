"""Iter 216h221 — E2E tests for CRM cross-login bug fix.

Tests the actual API endpoints to verify:
1. Pulse Pro user (jack.ottey@thirdspace.london) with CRM module enabled can cross-login
2. Master admin can always cross-login
3. MOD accounts are denied cross-login (defence-in-depth)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://photo-fix-verify.preview.emergentagent.com"


class TestCRMCrossLoginBugFix:
    """Bug #1: CRM cross-login gate now uses has_module() instead of enabled_modules array."""

    def test_pulse_pro_owner_can_cross_login(self):
        """Jack Ottey (Pulse Pro owner, modules.crm.enabled=true) should get HTTP 200 with CRM token.
        
        Pre-fix: returned 403 'CRM module not enabled for your organisation'
        Post-fix: returns 200 with valid CRM JWT
        """
        # Login as jack.ottey@thirdspace.london
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "jack.ottey@thirdspace.london", "password": "Test123!"},
            timeout=15
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        main_token = login_resp.json().get("token")
        assert main_token, "No token in login response"
        
        # Attempt CRM cross-login
        cross_login_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        
        # Post-fix: should be 200 with CRM token
        assert cross_login_resp.status_code == 200, f"Cross-login failed with {cross_login_resp.status_code}: {cross_login_resp.text}"
        
        data = cross_login_resp.json()
        assert "token" in data, "No CRM token in response"
        assert data["token"], "CRM token is empty"
        
        # Verify the CRM token works
        crm_me_resp = requests.get(
            f"{BASE_URL}/api/crm/auth/me",
            headers={"Authorization": f"Bearer {data['token']}"},
            timeout=10
        )
        assert crm_me_resp.status_code == 200, f"CRM /me failed: {crm_me_resp.text}"
        print(f"✓ Pulse Pro owner cross-login successful, CRM user: {crm_me_resp.json().get('email')}")

    def test_master_admin_can_always_cross_login(self):
        """Master admin (admin@gymaxisai.com) should always pass cross-login."""
        # Login as master admin
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            timeout=15
        )
        assert login_resp.status_code == 200, f"Master admin login failed: {login_resp.text}"
        main_token = login_resp.json().get("token")
        assert main_token, "No token in login response"
        
        # Attempt CRM cross-login
        cross_login_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        
        assert cross_login_resp.status_code == 200, f"Master admin cross-login failed: {cross_login_resp.text}"
        data = cross_login_resp.json()
        assert "token" in data, "No CRM token in response"
        print("✓ Master admin cross-login successful")

    def test_e1_agent_can_cross_login(self):
        """E1 agent (e1.agent@gymaxisai.com) should be able to cross-login."""
        # Login as e1 agent
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "e1.agent@gymaxisai.com", "password": "E1Agent123!"},
            timeout=15
        )
        assert login_resp.status_code == 200, f"E1 agent login failed: {login_resp.text}"
        main_token = login_resp.json().get("token")
        assert main_token, "No token in login response"
        
        # Attempt CRM cross-login
        cross_login_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        
        assert cross_login_resp.status_code == 200, f"E1 agent cross-login failed: {cross_login_resp.text}"
        data = cross_login_resp.json()
        assert "token" in data, "No CRM token in response"
        print("✓ E1 agent cross-login successful")


class TestCRMCrossLoginDenials:
    """Defence-in-depth: MOD accounts should be denied CRM cross-login."""

    def test_mod_site_account_denied_cross_login(self):
        """MOD site account (raf-demoairstation) should get 403 on cross-login."""
        # Login as MOD site user (username login)
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf-demoairstation", "password": "BrizeNorton2026!"},
            timeout=15
        )
        # MOD site login might use different endpoint or fail - skip if can't login
        if login_resp.status_code != 200:
            pytest.skip(f"MOD site login not available: {login_resp.status_code}")
        
        main_token = login_resp.json().get("token")
        if not main_token:
            pytest.skip("No token from MOD site login")
        
        # Attempt CRM cross-login - should be denied
        cross_login_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        
        assert cross_login_resp.status_code == 403, f"MOD site should be denied, got {cross_login_resp.status_code}"
        print("✓ MOD site account correctly denied CRM cross-login")

    def test_mod_branch_account_denied_cross_login(self):
        """MOD branch account should get 403 on cross-login."""
        # Login as MOD branch user
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf@demo.local", "password": "RafEstates2026!"},
            timeout=15
        )
        if login_resp.status_code != 200:
            pytest.skip(f"MOD branch login not available: {login_resp.status_code}")
        
        main_token = login_resp.json().get("token")
        if not main_token:
            pytest.skip("No token from MOD branch login")
        
        # Attempt CRM cross-login - should be denied
        cross_login_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        
        assert cross_login_resp.status_code == 403, f"MOD branch should be denied, got {cross_login_resp.status_code}"
        print("✓ MOD branch account correctly denied CRM cross-login")


class TestCRMCrossLoginEdgeCases:
    """Edge cases for cross-login."""

    def test_cross_login_without_token_returns_401(self):
        """Cross-login without auth token should return 401."""
        resp = requests.post(f"{BASE_URL}/api/crm/auth/cross-login", timeout=10)
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Cross-login without token correctly returns {resp.status_code}")

    def test_cross_login_with_invalid_token_returns_401(self):
        """Cross-login with invalid token should return 401."""
        resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": "Bearer invalid_token_here"},
            timeout=10
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Cross-login with invalid token correctly returns 401")

    def test_cross_login_with_crm_token_returns_400(self):
        """Cross-login with an already-CRM token should return 400."""
        # First get a CRM token via master admin
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            timeout=15
        )
        assert login_resp.status_code == 200
        main_token = login_resp.json().get("token")
        
        # Get CRM token
        cross_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {main_token}"},
            timeout=15
        )
        assert cross_resp.status_code == 200
        crm_token = cross_resp.json().get("token")
        
        # Try to cross-login again with the CRM token
        re_cross_resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {crm_token}"},
            timeout=15
        )
        assert re_cross_resp.status_code == 400, f"Expected 400 for re-exchange, got {re_cross_resp.status_code}"
        print("✓ Re-exchange of CRM token correctly returns 400")
