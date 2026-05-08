"""
Test Master Admin: Org Tier Upgrade/Downgrade and User Edit Features
Iteration 115 - Testing:
1. PUT /api/master-admin/organizations/{org_id}/subscription with tier=free/pro/premium/enterprise
2. PUT /api/master-admin/users/{user_id}/edit with role updates
3. PUT /api/master-admin/users/{user_id}/edit with full_name, email, job_title, phone updates
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level session to avoid rate limiting
_session = None
_token = None
_organizations = []
_users = []

def get_authenticated_session():
    """Get or create authenticated session (singleton to avoid rate limiting)"""
    global _session, _token, _organizations, _users

    if _session is not None and _token is not None:
        return _session, _token, _organizations, _users

    _session = requests.Session()
    _session.headers.update({"Content-Type": "application/json"})

    # Login as master admin
    login_resp = _session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@gymaxisai.com",
        "password": "MasterAdmin123!"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    _token = login_resp.json().get("token")
    _session.headers.update({"Authorization": f"Bearer {_token}"})

    # Get organizations list
    orgs_resp = _session.get(f"{BASE_URL}/api/master-admin/organizations")
    assert orgs_resp.status_code == 200, f"Failed to get orgs: {orgs_resp.text}"
    _organizations = orgs_resp.json().get("organizations", [])

    # Get users list
    users_resp = _session.get(f"{BASE_URL}/api/master-admin/users")
    assert users_resp.status_code == 200, f"Failed to get users: {users_resp.text}"
    _users = users_resp.json().get("users", [])

    return _session, _token, _organizations, _users


class TestMasterAdminTierAndUserEdit:
    """Test org tier changes and user edit functionality"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get authenticated session (reuses existing)"""
        self.session, self.token, self.organizations, self.users = get_authenticated_session()
        yield

    # ========== ORG TIER TESTS ==========

    def test_01_update_org_tier_to_free(self):
        """Test updating org subscription tier to 'free'"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "free"}
        )
        assert resp.status_code == 200, f"Failed to update tier to free: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert data.get("tier") == "free"
        print(f"✓ Updated org {org_id} tier to 'free'")

    def test_02_update_org_tier_to_pro(self):
        """Test updating org subscription tier to 'pro'"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "pro"}
        )
        assert resp.status_code == 200, f"Failed to update tier to pro: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert data.get("tier") == "pro"
        print(f"✓ Updated org {org_id} tier to 'pro'")

    def test_03_update_org_tier_to_premium(self):
        """Test updating org subscription tier to 'premium'"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "premium"}
        )
        assert resp.status_code == 200, f"Failed to update tier to premium: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert data.get("tier") == "premium"
        print(f"✓ Updated org {org_id} tier to 'premium'")

    def test_04_update_org_tier_to_enterprise(self):
        """Test updating org subscription tier to 'enterprise'"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "enterprise"}
        )
        assert resp.status_code == 200, f"Failed to update tier to enterprise: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert data.get("tier") == "enterprise"
        print(f"✓ Updated org {org_id} tier to 'enterprise'")

    def test_05_verify_tier_persists_after_update(self):
        """Test that tier change persists when fetching org list again"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        # Set to premium
        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "premium"}
        )
        assert resp.status_code == 200

        # Fetch orgs again and verify
        orgs_resp = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])

        updated_org = next((o for o in orgs if o["id"] == org_id), None)
        assert updated_org is not None, "Org not found after update"
        assert updated_org.get("subscription_tier") == "premium", f"Tier not persisted: {updated_org.get('subscription_tier')}"
        print(f"✓ Tier 'premium' persisted for org {org_id}")

    def test_06_invalid_tier_rejected(self):
        """Test that invalid tier values are rejected"""
        if not self.organizations:
            pytest.skip("No organizations available")

        org = self.organizations[0]
        org_id = org["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/subscription",
            json={"tier": "invalid_tier"}
        )
        assert resp.status_code == 400, f"Expected 400 for invalid tier, got {resp.status_code}"
        print("✓ Invalid tier 'invalid_tier' correctly rejected with 400")

    # ========== USER EDIT TESTS ==========

    def test_07_edit_user_role_to_manager(self):
        """Test updating user role to 'manager'"""
        if not self.users:
            pytest.skip("No users available")

        # Find a non-admin user to edit
        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"role": "manager"}
        )
        assert resp.status_code == 200, f"Failed to update role: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print(f"✓ Updated user {user_id} role to 'manager'")

    def test_08_edit_user_role_to_staff(self):
        """Test updating user role to 'staff'"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"role": "staff"}
        )
        assert resp.status_code == 200, f"Failed to update role: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print(f"✓ Updated user {user_id} role to 'staff'")

    def test_09_edit_user_role_to_owner(self):
        """Test updating user role to 'owner'"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"role": "owner"}
        )
        assert resp.status_code == 200, f"Failed to update role: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print(f"✓ Updated user {user_id} role to 'owner'")

    def test_10_edit_user_full_name(self):
        """Test updating user full_name"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]
        original_name = user.get("full_name", "")

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"full_name": "TEST_Updated Name"}
        )
        assert resp.status_code == 200, f"Failed to update full_name: {resp.text}"
        data = resp.json()
        assert data.get("success") == True

        # Verify persistence
        users_resp = self.session.get(f"{BASE_URL}/api/master-admin/users")
        assert users_resp.status_code == 200
        users = users_resp.json().get("users", [])
        updated_user = next((u for u in users if u["id"] == user_id), None)
        assert updated_user is not None
        assert updated_user.get("full_name") == "TEST_Updated Name"

        # Restore original name
        self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"full_name": original_name or "Test User"}
        )
        print(f"✓ Updated and verified user {user_id} full_name")

    def test_11_edit_user_email(self):
        """Test updating user email"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]
        original_email = user.get("email", "")

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"email": "test_updated@example.com"}
        )
        assert resp.status_code == 200, f"Failed to update email: {resp.text}"
        data = resp.json()
        assert data.get("success") == True

        # Restore original email
        self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"email": original_email}
        )
        print(f"✓ Updated user {user_id} email")

    def test_12_edit_user_job_title(self):
        """Test updating user job_title"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"job_title": "TEST_Senior Manager"}
        )
        assert resp.status_code == 200, f"Failed to update job_title: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print(f"✓ Updated user {user_id} job_title")

    def test_13_edit_user_phone(self):
        """Test updating user phone"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"phone": "+44 123 456 7890"}
        )
        assert resp.status_code == 200, f"Failed to update phone: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        print(f"✓ Updated user {user_id} phone")

    def test_14_edit_user_multiple_fields(self):
        """Test updating multiple user fields at once"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]
        original_name = user.get("full_name", "")
        original_role = user.get("role", "staff")

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={
                "full_name": "TEST_Multi Update",
                "role": "manager",
                "job_title": "TEST_Operations Lead",
                "phone": "+44 999 888 7777"
            }
        )
        assert resp.status_code == 200, f"Failed to update multiple fields: {resp.text}"
        data = resp.json()
        assert data.get("success") == True

        # Restore
        self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={"full_name": original_name or "Test User", "role": original_role}
        )
        print(f"✓ Updated user {user_id} with multiple fields")

    def test_15_edit_nonexistent_user_returns_404(self):
        """Test that editing a non-existent user returns 404"""
        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/nonexistent-user-id-12345/edit",
            json={"role": "staff"}
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent user, got {resp.status_code}"
        print("✓ Non-existent user correctly returns 404")

    def test_16_edit_user_empty_body_rejected(self):
        """Test that empty update body is rejected"""
        if not self.users:
            pytest.skip("No users available")

        user = next((u for u in self.users if u.get("email") != "admin@gymaxisai.com"), None)
        if not user:
            pytest.skip("No non-admin user available")

        user_id = user["id"]

        resp = self.session.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            json={}
        )
        assert resp.status_code == 400, f"Expected 400 for empty body, got {resp.status_code}"
        print("✓ Empty update body correctly rejected with 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
