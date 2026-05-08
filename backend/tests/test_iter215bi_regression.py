"""
Iter 215bi regression tests — targeted fixes verification.

Tests:
1. PATCH /api/master-admin/organizations/{org_id}/sites/{site_id} with is_head_office
2. GET /api/master-admin/organizations/{org_id}/sites returns at most one HQ
3. GET /api/crm/v2/companies?type=customer filters correctly
4. GET /api/crm/v2/companies?status=customer also works (legacy alias)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
CRM_USER_EMAIL = "craig.henshall@pulsefitness.com"
CRM_USER_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def crm_user_token():
    """Get CRM user JWT token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CRM_USER_EMAIL, "password": CRM_USER_PASSWORD}
    )
    assert response.status_code == 200, f"CRM user login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture(scope="module")
def crm_headers(crm_user_token):
    return {"Authorization": f"Bearer {crm_user_token}"}


class TestSitesHeadOffice:
    """Test PATCH /api/master-admin/organizations/{org_id}/sites/{site_id} with is_head_office."""

    def test_list_organizations(self, master_admin_headers):
        """Verify we can list organizations to get an org_id for testing."""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=master_admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "organizations" in data
        print(f"Found {len(data['organizations'])} organizations")

    def test_list_org_sites(self, master_admin_headers):
        """List sites for an organization."""
        # First get an org
        orgs_response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=master_admin_headers
        )
        assert orgs_response.status_code == 200
        orgs = orgs_response.json().get("organizations", [])

        if not orgs:
            pytest.skip("No organizations found to test sites")

        org_id = orgs[0]["id"]

        # List sites for this org
        response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers=master_admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "sites" in data
        print(f"Org {org_id} has {len(data['sites'])} sites")
        return data["sites"], org_id

    def test_patch_site_head_office(self, master_admin_headers):
        """Test PATCH /api/master-admin/organizations/{org_id}/sites/{site_id} with is_head_office."""
        # Get an org with sites
        orgs_response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=master_admin_headers
        )
        orgs = orgs_response.json().get("organizations", [])

        if not orgs:
            pytest.skip("No organizations found")

        # Find an org with real sites (not just default)
        test_org = None
        test_sites = []
        for org in orgs:
            sites_response = requests.get(
                f"{BASE_URL}/api/master-admin/organizations/{org['id']}/sites",
                headers=master_admin_headers
            )
            if sites_response.status_code == 200:
                sites = sites_response.json().get("sites", [])
                # Look for non-default sites
                real_sites = [s for s in sites if not s.get("is_default")]
                if real_sites:
                    test_org = org
                    test_sites = real_sites
                    break

        if not test_org or not test_sites:
            pytest.skip("No organization with real sites found for HQ test")

        site = test_sites[0]
        org_id = test_org["id"]
        site_id = site["id"]

        # Set is_head_office to true
        response = requests.patch(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{site_id}",
            json={"is_head_office": True},
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"PATCH failed: {response.text}"
        updated = response.json()
        assert updated.get("is_head_office") == True, "is_head_office should be True"
        print(f"Successfully set site {site_id} as head office")

        # Verify only one HQ exists
        sites_response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers=master_admin_headers
        )
        assert sites_response.status_code == 200
        sites = sites_response.json().get("sites", [])
        hq_count = sum(1 for s in sites if s.get("is_head_office"))
        assert hq_count <= 1, f"Expected at most 1 HQ, found {hq_count}"
        print(f"Verified: {hq_count} head office(s) in org")


class TestCRMCompaniesFilter:
    """Test GET /api/crm/v2/companies?type=customer filters correctly."""

    def test_companies_filter_by_type(self, crm_headers):
        """Test filtering companies by type=customer."""
        response = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?type=customer",
            headers=crm_headers
        )
        assert response.status_code == 200, f"Companies filter failed: {response.text}"
        data = response.json()
        assert "companies" in data

        # Verify all returned companies have type=customer
        companies = data["companies"]
        for company in companies:
            assert company.get("type") == "customer", f"Company {company.get('name')} has type {company.get('type')}, expected 'customer'"

        print(f"Found {len(companies)} companies with type=customer")

    def test_companies_filter_by_status_legacy(self, crm_headers):
        """Test filtering companies by status=customer (legacy alias)."""
        response = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?status=customer",
            headers=crm_headers
        )
        assert response.status_code == 200, f"Companies filter (status) failed: {response.text}"
        data = response.json()
        assert "companies" in data

        # Verify all returned companies have type=customer
        companies = data["companies"]
        for company in companies:
            assert company.get("type") == "customer", f"Company {company.get('name')} has type {company.get('type')}, expected 'customer'"

        print(f"Found {len(companies)} companies with status=customer (legacy)")

    def test_companies_filter_by_type_prospect(self, crm_headers):
        """Test filtering companies by type=prospect."""
        response = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?type=prospect",
            headers=crm_headers
        )
        assert response.status_code == 200
        data = response.json()
        companies = data.get("companies", [])

        for company in companies:
            assert company.get("type") == "prospect", f"Company {company.get('name')} has type {company.get('type')}, expected 'prospect'"

        print(f"Found {len(companies)} companies with type=prospect")

    def test_companies_no_filter(self, crm_headers):
        """Test listing all companies without filter."""
        response = requests.get(
            f"{BASE_URL}/api/crm/v2/companies",
            headers=crm_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "companies" in data
        print(f"Found {len(data['companies'])} total companies")


class TestMasterAdminResetPassword:
    """Test reset password returns temp_password."""

    def test_reset_password_endpoint_exists(self, master_admin_headers):
        """Verify the reset password endpoint structure."""
        # Get a user to test with
        orgs_response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers=master_admin_headers
        )
        orgs = orgs_response.json().get("organizations", [])

        if not orgs:
            pytest.skip("No organizations found")

        # Get users for first org
        users_response = requests.get(
            f"{BASE_URL}/api/master-admin/users",
            headers=master_admin_headers
        )
        assert users_response.status_code == 200
        users = users_response.json().get("users", [])

        # Find a non-master-admin user to test reset on
        test_user = None
        for u in users:
            if not u.get("is_master_admin") and u.get("email") != MASTER_ADMIN_EMAIL:
                test_user = u
                break

        if not test_user:
            pytest.skip("No suitable user found for password reset test")

        # Test reset password
        response = requests.put(
            f"{BASE_URL}/api/master-admin/users/{test_user['id']}/reset-password",
            json={},
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Reset password failed: {response.text}"
        data = response.json()

        # Verify response contains temp_password
        assert "temp_password" in data, "Response should contain temp_password"
        assert "user_email" in data or "email" in data, "Response should contain user email"
        print(f"Reset password successful, temp_password returned: {data.get('temp_password', '')[:4]}...")


class TestPulseBranding:
    """Test Pulse routes maintain data-brand='pulse'."""

    def test_pulse_pricing_page_loads(self):
        """Verify /pulse-pricing page loads."""
        response = requests.get(f"{BASE_URL}/pulse-pricing")
        assert response.status_code == 200, f"Pulse pricing page failed: {response.status_code}"
        print("Pulse pricing page loads successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
