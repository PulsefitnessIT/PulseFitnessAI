"""
Test Master Admin CRM Organization Creation and User Assignment
Tests for iteration 91 - CRM org creation with portal_type and user assignment
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get('MASTER_ADMIN_EMAIL', 'admin@gymaxisai.com')
MASTER_ADMIN_PASSWORD = os.environ.get('MASTER_ADMIN_PASSWORD', 'MasterAdmin123!')


class TestMasterAdminCRMOrganizations:
    """Test CRM organization creation and user assignment via Master Admin"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token for master admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Login as master admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })

        if login_response.status_code != 200:
            pytest.skip(f"Master admin login failed: {login_response.status_code}")

        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.created_org_ids = []
        self.created_user_emails = []
        yield

        # Cleanup - Note: No delete endpoint exists, so we just track what we created

    def test_01_get_organizations_returns_portal_type(self):
        """GET /api/master-admin/organizations should return portal_type field"""
        response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "organizations" in data, "Response should have 'organizations' key"

        # Check that organizations have portal_type field
        if len(data["organizations"]) > 0:
            org = data["organizations"][0]
            assert "portal_type" in org, "Organization should have portal_type field"
            assert org["portal_type"] in ["service_portal", "crm", "both"], f"Invalid portal_type: {org['portal_type']}"
            print(f"PASSED: Organizations endpoint returns portal_type field. First org portal_type: {org['portal_type']}")
        else:
            print("PASSED: Organizations endpoint works (no orgs to verify portal_type)")

    def test_02_create_organization_with_service_portal_type(self):
        """POST /api/master-admin/organizations creates org with service_portal type"""
        unique_name = f"TEST_ServicePortal_{uuid.uuid4().hex[:8]}"

        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "service_portal",
            "subscription_tier": "free"
        })

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "id" in data, "Response should have 'id'"
        assert data["name"] == unique_name, f"Name mismatch: {data['name']}"
        assert data["portal_type"] == "service_portal", f"portal_type should be service_portal, got {data.get('portal_type')}"

        self.created_org_ids.append(data["id"])
        print(f"PASSED: Created service_portal org: {unique_name} (ID: {data['id']})")

    def test_03_create_organization_with_crm_type(self):
        """POST /api/master-admin/organizations creates org with CRM type"""
        unique_name = f"TEST_CRM_{uuid.uuid4().hex[:8]}"

        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm",
            "subscription_tier": "pro"
        })

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "id" in data, "Response should have 'id'"
        assert data["name"] == unique_name, f"Name mismatch: {data['name']}"
        assert data["portal_type"] == "crm", f"portal_type should be crm, got {data.get('portal_type')}"

        self.created_org_ids.append(data["id"])
        print(f"PASSED: Created CRM org: {unique_name} (ID: {data['id']})")

    def test_04_create_organization_with_both_type(self):
        """POST /api/master-admin/organizations creates org with 'both' portal type"""
        unique_name = f"TEST_Both_{uuid.uuid4().hex[:8]}"

        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "both",
            "subscription_tier": "premium"
        })

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "id" in data, "Response should have 'id'"
        assert data["portal_type"] == "both", f"portal_type should be both, got {data.get('portal_type')}"

        self.created_org_ids.append(data["id"])
        print(f"PASSED: Created 'both' portal type org: {unique_name} (ID: {data['id']})")

    def test_05_create_organization_invalid_portal_type(self):
        """POST /api/master-admin/organizations rejects invalid portal_type"""
        unique_name = f"TEST_Invalid_{uuid.uuid4().hex[:8]}"

        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "invalid_type",
            "subscription_tier": "free"
        })

        assert response.status_code == 400, f"Expected 400 for invalid portal_type, got {response.status_code}"
        print("PASSED: Invalid portal_type correctly rejected with 400")

    def test_06_create_organization_missing_name(self):
        """POST /api/master-admin/organizations rejects missing name"""
        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": "",
            "portal_type": "crm"
        })

        assert response.status_code == 400, f"Expected 400 for missing name, got {response.status_code}"
        print("PASSED: Missing name correctly rejected with 400")

    def test_07_add_user_to_organization(self):
        """POST /api/master-admin/organizations/{org_id}/users adds user to org"""
        # First create an org
        unique_name = f"TEST_UserOrg_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm",
            "subscription_tier": "free"
        })

        assert create_response.status_code == 200, f"Failed to create org: {create_response.text}"
        org_id = create_response.json()["id"]
        self.created_org_ids.append(org_id)

        # Now add a user
        unique_email = f"test.user.{uuid.uuid4().hex[:8]}@example.com"
        user_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json={
            "email": unique_email,
            "full_name": "Test User",
            "password": "TestPass123!",
            "role": "staff"
        })

        assert user_response.status_code == 200, f"Expected 200, got {user_response.status_code}: {user_response.text}"
        user_data = user_response.json()

        assert "id" in user_data, "Response should have user 'id'"
        assert user_data["email"] == unique_email, f"Email mismatch: {user_data['email']}"
        assert user_data["full_name"] == "Test User", f"Name mismatch: {user_data['full_name']}"
        assert user_data["role"] == "staff", f"Role mismatch: {user_data['role']}"

        self.created_user_emails.append(unique_email)
        print(f"PASSED: Added user {unique_email} to org {org_id}")

    def test_08_add_user_with_owner_role(self):
        """POST /api/master-admin/organizations/{org_id}/users adds owner role user"""
        # First create an org
        unique_name = f"TEST_OwnerOrg_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm"
        })

        assert create_response.status_code == 200
        org_id = create_response.json()["id"]
        self.created_org_ids.append(org_id)

        # Add owner user
        unique_email = f"test.owner.{uuid.uuid4().hex[:8]}@example.com"
        user_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json={
            "email": unique_email,
            "full_name": "Test Owner",
            "password": "OwnerPass123!",
            "role": "owner"
        })

        assert user_response.status_code == 200, f"Expected 200, got {user_response.status_code}: {user_response.text}"
        user_data = user_response.json()
        assert user_data["role"] == "owner", f"Role should be owner, got {user_data['role']}"

        self.created_user_emails.append(unique_email)
        print(f"PASSED: Added owner user {unique_email} to org {org_id}")

    def test_09_add_user_missing_required_fields(self):
        """POST /api/master-admin/organizations/{org_id}/users rejects missing fields"""
        # First create an org
        unique_name = f"TEST_MissingFields_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm"
        })

        assert create_response.status_code == 200
        org_id = create_response.json()["id"]
        self.created_org_ids.append(org_id)

        # Try to add user without email
        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json={
            "full_name": "Test User",
            "password": "TestPass123!"
        })

        assert response.status_code == 400, f"Expected 400 for missing email, got {response.status_code}"
        print("PASSED: Missing email correctly rejected with 400")

    def test_10_add_user_to_nonexistent_org(self):
        """POST /api/master-admin/organizations/{org_id}/users returns 404 for invalid org"""
        fake_org_id = str(uuid.uuid4())

        response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{fake_org_id}/users", json={
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "TestPass123!",
            "role": "staff"
        })

        assert response.status_code == 404, f"Expected 404 for nonexistent org, got {response.status_code}"
        print("PASSED: Nonexistent org correctly returns 404")

    def test_11_add_duplicate_user_email(self):
        """POST /api/master-admin/organizations/{org_id}/users rejects duplicate email"""
        # First create an org
        unique_name = f"TEST_DupeEmail_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm"
        })

        assert create_response.status_code == 200
        org_id = create_response.json()["id"]
        self.created_org_ids.append(org_id)

        # Add first user
        unique_email = f"test.dupe.{uuid.uuid4().hex[:8]}@example.com"
        first_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json={
            "email": unique_email,
            "full_name": "First User",
            "password": "TestPass123!",
            "role": "staff"
        })

        assert first_response.status_code == 200
        self.created_user_emails.append(unique_email)

        # Try to add same email again
        dupe_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/users", json={
            "email": unique_email,
            "full_name": "Duplicate User",
            "password": "TestPass123!",
            "role": "staff"
        })

        assert dupe_response.status_code == 409, f"Expected 409 for duplicate email, got {dupe_response.status_code}"
        print("PASSED: Duplicate email correctly rejected with 409")

    def test_12_verify_created_org_in_list(self):
        """Verify created CRM org appears in organizations list with correct portal_type"""
        # Create a CRM org
        unique_name = f"TEST_VerifyList_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/master-admin/organizations", json={
            "name": unique_name,
            "portal_type": "crm",
            "subscription_tier": "pro"
        })

        assert create_response.status_code == 200
        org_id = create_response.json()["id"]
        self.created_org_ids.append(org_id)

        # Fetch all orgs and verify
        list_response = self.session.get(f"{BASE_URL}/api/master-admin/organizations")
        assert list_response.status_code == 200

        orgs = list_response.json()["organizations"]
        found_org = next((o for o in orgs if o["id"] == org_id), None)

        assert found_org is not None, f"Created org {org_id} not found in list"
        assert found_org["name"] == unique_name, "Name mismatch in list"
        assert found_org["portal_type"] == "crm", f"portal_type should be crm, got {found_org['portal_type']}"

        print(f"PASSED: Created CRM org {unique_name} verified in organizations list")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
