"""
Test CRM Team Management Features - Iteration 113
Tests: invite, edit, delete team members with role-based permissions
- Manager can only manage sales_rep
- Admin/Owner can manage all non-owner roles
- Owner role is protected (cannot be changed/deleted)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials — loaded from shared test credentials file
MANAGER_EMAIL = os.environ.get('CRM_TEST_EMAIL', 'craig.henshall@pulsefitness.com')
MANAGER_PASSWORD = os.environ.get('CRM_TEST_PASSWORD', 'Test123!')


class TestCRMTeamManagement:
    """Test CRM team management endpoints with role-based permissions"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session and authenticate as manager"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.auth_token = None
        self.created_user_ids = []

        # Authenticate as manager (Craig)
        login_response = self.session.post(f"{BASE_URL}/api/crm/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        if login_response.status_code == 200:
            self.auth_token = login_response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})

        yield

        # Cleanup: delete test users created during tests
        for user_id in self.created_user_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/crm/users/{user_id}")
            except:
                pass

    def test_01_login_as_manager(self):
        """Test login as manager (Craig) works"""
        response = self.session.post(f"{BASE_URL}/api/crm/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data.get("user", {}).get("role") == "manager", "Craig should have manager role"
        print(f"✓ Login successful, user role: {data.get('user', {}).get('role')}")

    def test_02_list_crm_users(self):
        """Test GET /api/crm/users returns team members"""
        assert self.auth_token, "Auth token required"
        response = self.session.get(f"{BASE_URL}/api/crm/users")
        assert response.status_code == 200, f"Failed to list users: {response.text}"
        data = response.json()
        assert "users" in data
        print(f"✓ Listed {len(data['users'])} team members")

        # Check role colors are available (owner=orange, admin=red, manager=blue, sales_rep=green)
        for user in data['users']:
            assert 'role' in user, "User should have role field"
            assert user['role'] in ['owner', 'admin', 'manager', 'sales_rep'], f"Invalid role: {user['role']}"
        print("✓ All users have valid roles")

    def test_03_manager_invite_sales_rep_success(self):
        """Test manager can invite sales_rep (should succeed)"""
        assert self.auth_token, "Auth token required"

        test_email = f"test_salesrep_{uuid.uuid4().hex[:8]}@test.com"
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Sales Rep",
            "role": "sales_rep"
        })
        assert response.status_code == 200, f"Failed to invite sales_rep: {response.text}"
        data = response.json()
        assert data.get("role") == "sales_rep"
        assert "temp_password" in data
        assert data.get("email") == test_email

        # Track for cleanup
        if "id" in data:
            self.created_user_ids.append(data["id"])

        print(f"✓ Manager successfully invited sales_rep: {test_email}")
        return data.get("id")

    def test_04_manager_invite_manager_forbidden(self):
        """Test manager cannot invite another manager (should get 403)"""
        assert self.auth_token, "Auth token required"

        test_email = f"test_manager_{uuid.uuid4().hex[:8]}@test.com"
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Manager",
            "role": "manager"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Manager correctly forbidden from inviting manager role")

    def test_05_manager_invite_admin_forbidden(self):
        """Test manager cannot invite admin (should get 403)"""
        assert self.auth_token, "Auth token required"

        test_email = f"test_admin_{uuid.uuid4().hex[:8]}@test.com"
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Admin",
            "role": "admin"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Manager correctly forbidden from inviting admin role")

    def test_06_invite_owner_role_not_allowed(self):
        """Test owner role cannot be invited (should be rejected or converted to sales_rep)"""
        assert self.auth_token, "Auth token required"

        test_email = f"test_owner_{uuid.uuid4().hex[:8]}@test.com"
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Owner",
            "role": "owner"
        })

        # Owner role should either be rejected (403) or converted to sales_rep
        if response.status_code == 200:
            data = response.json()
            # If accepted, role should be converted to sales_rep (not owner)
            assert data.get("role") != "owner", "Owner role should not be allowed in invite"
            if "id" in data:
                self.created_user_ids.append(data["id"])
            print(f"✓ Owner role converted to: {data.get('role')}")
        else:
            # 403 is also acceptable
            assert response.status_code in [400, 403], f"Expected 400/403, got {response.status_code}"
            print("✓ Owner role correctly rejected in invite")

    def test_07_invite_duplicate_email_fails(self):
        """Test inviting duplicate email returns 409"""
        assert self.auth_token, "Auth token required"

        # Try to invite existing user (Craig)
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": MANAGER_EMAIL,
            "full_name": "Duplicate User",
            "role": "sales_rep"
        })
        assert response.status_code == 409, f"Expected 409 for duplicate, got {response.status_code}: {response.text}"
        print("✓ Duplicate email correctly rejected with 409")

    def test_08_manager_edit_sales_rep_success(self):
        """Test manager can edit sales_rep user"""
        assert self.auth_token, "Auth token required"

        # First create a sales_rep to edit
        test_email = f"test_edit_{uuid.uuid4().hex[:8]}@test.com"
        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Edit User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200, f"Failed to create test user: {create_response.text}"
        user_id = create_response.json().get("id")
        self.created_user_ids.append(user_id)

        # Now edit the user
        edit_response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "full_name": "TEST Edited Name",
            "status": "inactive"
        })
        assert edit_response.status_code == 200, f"Failed to edit user: {edit_response.text}"
        print("✓ Manager successfully edited sales_rep user")

        # Verify the edit persisted
        users_response = self.session.get(f"{BASE_URL}/api/crm/users")
        users = users_response.json().get("users", [])
        edited_user = next((u for u in users if u.get("id") == user_id), None)
        assert edited_user is not None, "Edited user not found"
        assert edited_user.get("full_name") == "TEST Edited Name", "Name not updated"
        assert edited_user.get("status") == "inactive", "Status not updated"
        print("✓ Edit changes persisted correctly")

    def test_09_status_active_inactive_toggle(self):
        """Test status field supports 'active' and 'inactive'"""
        assert self.auth_token, "Auth token required"

        # Create a user
        test_email = f"test_status_{uuid.uuid4().hex[:8]}@test.com"
        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Status User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200
        user_id = create_response.json().get("id")
        self.created_user_ids.append(user_id)

        # Set to inactive
        response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "status": "inactive"
        })
        assert response.status_code == 200

        # Verify inactive
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user.get("status") == "inactive", "Status should be inactive"
        print("✓ Status set to inactive")

        # Set back to active
        response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "status": "active"
        })
        assert response.status_code == 200

        # Verify active
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user.get("status") == "active", "Status should be active"
        print("✓ Status toggled back to active")

    def test_10_delete_sales_rep_success(self):
        """Test manager can delete sales_rep user"""
        assert self.auth_token, "Auth token required"

        # Create a user to delete
        test_email = f"test_delete_{uuid.uuid4().hex[:8]}@test.com"
        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Delete User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200
        user_id = create_response.json().get("id")

        # Delete the user
        delete_response = self.session.delete(f"{BASE_URL}/api/crm/users/{user_id}")
        assert delete_response.status_code == 200, f"Failed to delete: {delete_response.text}"
        print("✓ Manager successfully deleted sales_rep user")

        # Verify user is gone
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        deleted_user = next((u for u in users if u.get("id") == user_id), None)
        assert deleted_user is None, "Deleted user should not exist"
        print("✓ User deletion verified")

    def test_11_cannot_delete_self(self):
        """Test user cannot delete themselves"""
        assert self.auth_token, "Auth token required"

        # Get current user ID
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        current_user = next((u for u in users if u.get("email") == MANAGER_EMAIL), None)
        assert current_user, "Current user not found"

        # Try to delete self
        response = self.session.delete(f"{BASE_URL}/api/crm/users/{current_user['id']}")
        assert response.status_code == 400, f"Expected 400 for self-delete, got {response.status_code}"
        print("✓ Self-deletion correctly prevented")

    def test_12_cannot_delete_owner(self):
        """Test cannot delete owner account"""
        assert self.auth_token, "Auth token required"

        # Find owner user
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        owner_user = next((u for u in users if u.get("role") == "owner"), None)

        if owner_user:
            response = self.session.delete(f"{BASE_URL}/api/crm/users/{owner_user['id']}")
            assert response.status_code == 403, f"Expected 403 for owner delete, got {response.status_code}"
            print("✓ Owner deletion correctly prevented")
        else:
            print("⚠ No owner user found to test deletion protection")

    def test_13_manager_cannot_edit_non_sales_rep(self):
        """Test manager cannot edit users with non-sales_rep roles"""
        assert self.auth_token, "Auth token required"

        # Find a non-sales_rep user (admin, manager, or owner)
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        non_sales_rep = next((u for u in users if u.get("role") in ["admin", "owner"] and u.get("email") != MANAGER_EMAIL), None)

        if non_sales_rep:
            response = self.session.put(f"{BASE_URL}/api/crm/users/{non_sales_rep['id']}", json={
                "full_name": "Attempted Edit"
            })
            assert response.status_code == 403, f"Expected 403, got {response.status_code}"
            print(f"✓ Manager correctly forbidden from editing {non_sales_rep['role']} user")
        else:
            print("⚠ No admin/owner user found to test edit restriction")

    def test_14_cannot_change_owner_role(self):
        """Test owner role cannot be changed"""
        assert self.auth_token, "Auth token required"

        # Find owner user
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        owner_user = next((u for u in users if u.get("role") == "owner"), None)

        if owner_user:
            response = self.session.put(f"{BASE_URL}/api/crm/users/{owner_user['id']}", json={
                "role": "admin"
            })
            # Should be 403 (manager can't edit owner) or specific error about owner role
            assert response.status_code in [403, 400], f"Expected 403/400, got {response.status_code}"
            print("✓ Owner role change correctly prevented")
        else:
            print("⚠ No owner user found to test role protection")

    def test_15_cannot_promote_to_owner(self):
        """Test cannot promote any user to owner role"""
        assert self.auth_token, "Auth token required"

        # Create a sales_rep
        test_email = f"test_promote_{uuid.uuid4().hex[:8]}@test.com"
        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Promote User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200
        user_id = create_response.json().get("id")
        self.created_user_ids.append(user_id)

        # Try to promote to owner
        response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "role": "owner"
        })
        assert response.status_code == 403, f"Expected 403 for owner promotion, got {response.status_code}"
        print("✓ Promotion to owner correctly prevented")

    def test_16_edit_email_updates_correctly(self):
        """Test editing user email works"""
        assert self.auth_token, "Auth token required"

        # Create a user
        test_email = f"test_email_{uuid.uuid4().hex[:8]}@test.com"
        new_email = f"test_newemail_{uuid.uuid4().hex[:8]}@test.com"

        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Email User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200
        user_id = create_response.json().get("id")
        self.created_user_ids.append(user_id)

        # Edit email
        response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "email": new_email
        })
        assert response.status_code == 200

        # Verify email changed
        users = self.session.get(f"{BASE_URL}/api/crm/users").json().get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        assert user.get("email") == new_email, "Email not updated"
        print("✓ Email update successful")

    def test_17_edit_role_sales_rep_to_sales_rep(self):
        """Test manager can keep role as sales_rep"""
        assert self.auth_token, "Auth token required"

        # Create a user
        test_email = f"test_role_{uuid.uuid4().hex[:8]}@test.com"
        create_response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": test_email,
            "full_name": "TEST Role User",
            "role": "sales_rep"
        })
        assert create_response.status_code == 200
        user_id = create_response.json().get("id")
        self.created_user_ids.append(user_id)

        # Edit role (keep as sales_rep)
        response = self.session.put(f"{BASE_URL}/api/crm/users/{user_id}", json={
            "role": "sales_rep"
        })
        assert response.status_code == 200
        print("✓ Role update to sales_rep successful")

    def test_18_invite_missing_fields_fails(self):
        """Test invite with missing required fields fails"""
        assert self.auth_token, "Auth token required"

        # Missing email
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "full_name": "Test User",
            "role": "sales_rep"
        })
        assert response.status_code == 400, f"Expected 400 for missing email, got {response.status_code}"

        # Missing full_name
        response = self.session.post(f"{BASE_URL}/api/crm/users/invite", json={
            "email": "test@test.com",
            "role": "sales_rep"
        })
        assert response.status_code == 400, f"Expected 400 for missing name, got {response.status_code}"
        print("✓ Missing fields correctly rejected")

    def test_19_delete_nonexistent_user_404(self):
        """Test deleting non-existent user returns 404"""
        assert self.auth_token, "Auth token required"

        fake_id = str(uuid.uuid4())
        response = self.session.delete(f"{BASE_URL}/api/crm/users/{fake_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent user delete returns 404")

    def test_20_edit_nonexistent_user_404(self):
        """Test editing non-existent user returns 404"""
        assert self.auth_token, "Auth token required"

        fake_id = str(uuid.uuid4())
        response = self.session.put(f"{BASE_URL}/api/crm/users/{fake_id}", json={
            "full_name": "Test"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent user edit returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
