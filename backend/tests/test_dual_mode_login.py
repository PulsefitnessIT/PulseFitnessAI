"""
Test dual-mode login (username vs email) and MOD account type routing.

Tests:
1. MOD site login via username (no @) - raf-demoairstation
2. MOD branch PRO login via email - raf@demo.local
3. MOD org PRO login via email - modestates@demo.local
4. Wrong password returns 401
5. Regression: civilian email login still works
6. /auth/me returns correct account_type for each user type
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Bypass headers for rate limiting and captcha
BYPASS_HEADERS = {
    "Content-Type": "application/json",
    "X-RateLimit-Bypass": "1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6",
    "X-Captcha-Token": "bypass:1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6",
}


class TestDualModeLogin:
    """Test dual-mode login: username (MOD site) vs email (PRO/civilian)"""

    def test_mod_site_username_login_raf(self):
        """MOD site login via kebab-case username (no @)"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf-demoairstation", "password": "BrizeNorton2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "user" in data, "Response should contain user"
        assert data["user"]["account_type"] == "mod_site", f"Expected mod_site, got {data['user'].get('account_type')}"
        print(f"✓ MOD site username login (raf-demoairstation): account_type={data['user']['account_type']}")

    def test_mod_site_username_login_army(self):
        """MOD site login via kebab-case username - army-catterick"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "army-catterick", "password": "Demo Garrison2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["user"]["account_type"] == "mod_site"
        print(f"✓ MOD site username login (army-catterick): account_type={data['user']['account_type']}")

    def test_mod_site_username_login_navy(self):
        """MOD site login via kebab-case username - navy-raleigh"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "navy-raleigh", "password": "Raleigh2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["user"]["account_type"] == "mod_site"
        print(f"✓ MOD site username login (navy-raleigh): account_type={data['user']['account_type']}")

    def test_mod_branch_pro_login_raf(self):
        """MOD branch PRO login via email - raf@demo.local"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf@demo.local", "password": "RafEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["account_type"] == "mod_branch", f"Expected mod_branch, got {data['user'].get('account_type')}"
        print(f"✓ MOD branch PRO login (raf@demo.local): account_type={data['user']['account_type']}")

    def test_mod_branch_pro_login_army(self):
        """MOD branch PRO login via email - army@demo.local"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "army@demo.local", "password": "ArmyEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["user"]["account_type"] == "mod_branch"
        print(f"✓ MOD branch PRO login (army@demo.local): account_type={data['user']['account_type']}")

    def test_mod_branch_pro_login_navy(self):
        """MOD branch PRO login via email - navy@demo.local"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "navy@demo.local", "password": "NavyEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["user"]["account_type"] == "mod_branch"
        print(f"✓ MOD branch PRO login (navy@demo.local): account_type={data['user']['account_type']}")

    def test_mod_org_pro_login(self):
        """MOD org PRO login via email - modestates@demo.local"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "modestates@demo.local", "password": "ModEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["account_type"] == "mod_org", f"Expected mod_org, got {data['user'].get('account_type')}"
        print(f"✓ MOD org PRO login (modestates@demo.local): account_type={data['user']['account_type']}")

    def test_wrong_password_mod_site(self):
        """Wrong password for MOD site returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf-demoairstation", "password": "WrongPassword123!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Wrong password for MOD site returns 401")

    def test_wrong_password_mod_branch(self):
        """Wrong password for MOD branch PRO returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf@demo.local", "password": "WrongPassword123!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Wrong password for MOD branch PRO returns 401")

    def test_wrong_password_mod_org(self):
        """Wrong password for MOD org PRO returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "modestates@demo.local", "password": "WrongPassword123!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Wrong password for MOD org PRO returns 401")


class TestRegressionCivilianLogin:
    """Regression tests: civilian email logins still work"""

    def test_pulse_pro_login(self):
        """Pulse Pro user login - lee.somers@pulsefitness.com"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        # Pulse Pro users should NOT have mod_site/mod_branch/mod_org account_type
        account_type = data["user"].get("account_type", "full")
        assert account_type not in ("mod_site", "mod_branch", "mod_org"), f"Unexpected MOD account_type: {account_type}"
        print(f"✓ Pulse Pro login (lee.somers@pulsefitness.com): account_type={account_type}")

    def test_master_admin_login(self):
        """Master admin login - admin@gymaxisai.com"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            headers=BYPASS_HEADERS,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"].get("is_master_admin") is True, "Expected is_master_admin=True"
        print(f"✓ Master admin login: is_master_admin={data['user'].get('is_master_admin')}")


class TestAuthMeEndpoint:
    """Test /auth/me returns correct account_type for each user type"""

    def test_auth_me_mod_site(self):
        """GET /auth/me for MOD site user returns mod_site account_type"""
        # Login first
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf-demoairstation", "password": "BrizeNorton2026!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        # Call /auth/me
        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200, f"Expected 200, got {me_resp.status_code}: {me_resp.text}"
        data = me_resp.json()
        assert data.get("account_type") == "mod_site", f"Expected mod_site, got {data.get('account_type')}"
        # Verify synthetic email is stored but user logged in with username
        assert "@site.mod.local" in data.get("email", ""), f"Expected synthetic email, got {data.get('email')}"
        print(f"✓ /auth/me for MOD site: account_type={data.get('account_type')}, email={data.get('email')}")

    def test_auth_me_mod_branch(self):
        """GET /auth/me for MOD branch PRO user returns mod_branch account_type"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf@demo.local", "password": "RafEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data.get("account_type") == "mod_branch"
        print(f"✓ /auth/me for MOD branch PRO: account_type={data.get('account_type')}")

    def test_auth_me_mod_org(self):
        """GET /auth/me for MOD org PRO user returns mod_org account_type"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "modestates@demo.local", "password": "ModEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data.get("account_type") == "mod_org"
        print(f"✓ /auth/me for MOD org PRO: account_type={data.get('account_type')}")


class TestMODProDashboard:
    """Test MOD PRO dashboard scoping"""

    def test_branch_pro_sees_only_branch_sites(self):
        """RAF branch PRO should see only RAF sites (1 site)"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "raf@demo.local", "password": "RafEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        dashboard_resp = requests.get(
            f"{BASE_URL}/api/mod/pro/dashboard",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert dashboard_resp.status_code == 200, f"Expected 200, got {dashboard_resp.status_code}: {dashboard_resp.text}"
        data = dashboard_resp.json()

        assert data.get("scope") == "mod_branch"
        assert data.get("branch") == "RAF"
        assert data["totals"]["sites"] == 1, f"Expected 1 site, got {data['totals']['sites']}"
        assert data["totals"]["equipment"] == 12, f"Expected 12 machines, got {data['totals']['equipment']}"

        # Verify only RAF site is in the list
        site_names = [s.get("name", "") for s in data.get("sites", [])]
        assert any("RAF" in name or "Brize" in name for name in site_names), f"Expected RAF site, got {site_names}"
        print(f"✓ RAF branch PRO dashboard: {data['totals']['sites']} site(s), {data['totals']['equipment']} machines")

    def test_org_pro_sees_all_sites(self):
        """MOD org PRO should see all 3 sites (RAF + Army + Navy)"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "modestates@demo.local", "password": "ModEstates2026!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        dashboard_resp = requests.get(
            f"{BASE_URL}/api/mod/pro/dashboard",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert dashboard_resp.status_code == 200
        data = dashboard_resp.json()

        assert data.get("scope") == "mod_org"
        assert data["totals"]["sites"] == 3, f"Expected 3 sites, got {data['totals']['sites']}"
        assert data["totals"]["equipment"] == 36, f"Expected 36 machines (12*3), got {data['totals']['equipment']}"

        # Verify all 3 branches are represented
        site_names = [s.get("name", "") for s in data.get("sites", [])]
        assert len(site_names) == 3, f"Expected 3 sites, got {len(site_names)}"
        print(f"✓ MOD org PRO dashboard: {data['totals']['sites']} sites, {data['totals']['equipment']} machines")


class TestMasterAdminMODConsole:
    """Test Master Admin MOD Console shows exactly 3 seeded sites"""

    def test_mod_console_shows_3_sites(self):
        """Master admin MOD console should show exactly 3 MOD sites (no duplicates)"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            headers=BYPASS_HEADERS,
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["token"]

        sites_resp = requests.get(
            f"{BASE_URL}/api/master-admin/mod/sites",
            headers={**BYPASS_HEADERS, "Authorization": f"Bearer {token}"},
        )
        assert sites_resp.status_code == 200, f"Expected 200, got {sites_resp.status_code}: {sites_resp.text}"
        data = sites_resp.json()

        sites = data.get("sites", [])
        assert len(sites) == 3, f"Expected exactly 3 MOD sites, got {len(sites)}"

        site_names = [s.get("name", "") for s in sites]
        expected_names = ["Demo Air Station Gym", "Demo Garrison Gym", "Demo Naval Base Gym"]
        for expected in expected_names:
            assert any(expected in name for name in site_names), f"Missing site: {expected}"

        print(f"✓ Master admin MOD console: {len(sites)} sites - {site_names}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
