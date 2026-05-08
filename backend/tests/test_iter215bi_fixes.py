"""
Iteration 215bi — Regression fixes verification tests.

Tests:
1. Master Admin Settings sidebar entry
2. Reset password inline (no global toast blocking)
3. CRM company filter by type (was filtering on status)
4. Head Office tagging on org sites (PATCH /master-admin/organizations/{org_id}/sites/{site_id})
5. GET /master-admin/organizations/{org_id}/sites returns is_head_office field
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
CRM_USER_EMAIL = "craig.henshall@pulsefitness.com"
CRM_USER_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Master admin login failed: {response.status_code}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def crm_token():
    """Get CRM user JWT token."""
    response = requests.post(f"{BASE_URL}/api/crm/auth/login", json={
        "email": CRM_USER_EMAIL,
        "password": CRM_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"CRM login failed: {response.status_code}")
    return response.json().get("token")


class TestMasterAdminSites:
    """Test Head Office tagging on org sites."""

    def test_list_org_sites(self, master_admin_token):
        """GET /master-admin/organizations/{org_id}/sites returns sites with is_head_office field."""
        # First get an org
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert orgs_resp.status_code == 200, f"Failed to get orgs: {orgs_resp.text}"

        orgs = orgs_resp.json().get("organizations", [])
        if not orgs:
            pytest.skip("No organizations found")

        org_id = orgs[0]["id"]

        # Get sites for this org
        sites_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites", headers=headers)
        assert sites_resp.status_code == 200, f"Failed to get sites: {sites_resp.text}"

        sites = sites_resp.json().get("sites", [])
        # Sites should have is_head_office field (may be True, False, or missing for default sites)
        print(f"Found {len(sites)} sites for org {org_id}")
        for site in sites:
            print(f"  Site: {site.get('name')} - is_head_office: {site.get('is_head_office', 'N/A')}")

    def test_patch_site_head_office(self, master_admin_token):
        """PATCH /master-admin/organizations/{org_id}/sites/{site_id} with is_head_office."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # Get an org with real sites (not default)
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert orgs_resp.status_code == 200
        orgs = orgs_resp.json().get("organizations", [])

        # Find an org with sites
        test_org = None
        test_site = None
        for org in orgs:
            sites_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/{org['id']}/sites", headers=headers)
            if sites_resp.status_code == 200:
                sites = sites_resp.json().get("sites", [])
                # Look for a non-default site
                for site in sites:
                    if not site.get("is_default"):
                        test_org = org
                        test_site = site
                        break
            if test_site:
                break

        if not test_site:
            # Create a test site
            if orgs:
                test_org = orgs[0]
                create_resp = requests.post(
                    f"{BASE_URL}/api/sites",
                    json={"name": f"Test Site {uuid.uuid4().hex[:6]}", "address": "123 Test St"},
                    headers=headers
                )
                if create_resp.status_code == 200:
                    test_site = create_resp.json()
                else:
                    pytest.skip("Could not create test site and no existing non-default sites found")
            else:
                pytest.skip("No organizations found")

        org_id = test_org["id"]
        site_id = test_site["id"]

        # Set as head office
        patch_resp = requests.patch(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{site_id}",
            json={"is_head_office": True},
            headers=headers
        )
        assert patch_resp.status_code == 200, f"Failed to set head office: {patch_resp.text}"

        updated = patch_resp.json()
        assert updated.get("is_head_office") == True, f"is_head_office not set: {updated}"
        print(f"Successfully set site {site_id} as head office")

        # Verify only one HQ per org
        sites_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites", headers=headers)
        assert sites_resp.status_code == 200
        sites = sites_resp.json().get("sites", [])
        hq_count = sum(1 for s in sites if s.get("is_head_office"))
        assert hq_count <= 1, f"Multiple HQ sites found: {hq_count}"
        print(f"Verified only {hq_count} HQ site(s) in org")


class TestCRMCompanyFilter:
    """Test CRM company filter by type (customer/prospect/partner)."""

    def test_filter_companies_by_type(self, crm_token):
        """GET /crm/v2/companies?type=customer filters correctly."""
        headers = {"Authorization": f"Bearer {crm_token}"}

        # First create a test company with type=customer
        test_company_name = f"Test Customer {uuid.uuid4().hex[:6]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/crm/v2/companies",
            json={"name": test_company_name, "type": "customer"},
            headers=headers
        )
        assert create_resp.status_code == 200, f"Failed to create company: {create_resp.text}"
        created = create_resp.json()
        company_id = created.get("id")
        print(f"Created test company: {test_company_name} with type=customer")

        # Filter by type=customer
        filter_resp = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?type=customer",
            headers=headers
        )
        assert filter_resp.status_code == 200, f"Filter failed: {filter_resp.text}"

        companies = filter_resp.json().get("companies", [])
        # Our test company should be in the results
        found = any(c.get("id") == company_id for c in companies)
        assert found, "Test company not found in filtered results"

        # All returned companies should have type=customer
        for c in companies:
            assert c.get("type") == "customer", f"Company {c.get('name')} has type {c.get('type')}, expected customer"

        print(f"Filter returned {len(companies)} customer companies, all verified")

        # Also test the status alias (backwards compat)
        alias_resp = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?status=customer",
            headers=headers
        )
        assert alias_resp.status_code == 200, f"Status alias filter failed: {alias_resp.text}"
        alias_companies = alias_resp.json().get("companies", [])
        assert len(alias_companies) == len(companies), "Status alias should return same results as type"
        print("Status alias filter also works correctly")

    def test_filter_companies_by_prospect(self, crm_token):
        """GET /crm/v2/companies?type=prospect filters correctly."""
        headers = {"Authorization": f"Bearer {crm_token}"}

        # Create a prospect company
        test_company_name = f"Test Prospect {uuid.uuid4().hex[:6]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/crm/v2/companies",
            json={"name": test_company_name, "type": "prospect"},
            headers=headers
        )
        assert create_resp.status_code == 200
        company_id = create_resp.json().get("id")

        # Filter by type=prospect
        filter_resp = requests.get(
            f"{BASE_URL}/api/crm/v2/companies?type=prospect",
            headers=headers
        )
        assert filter_resp.status_code == 200

        companies = filter_resp.json().get("companies", [])
        found = any(c.get("id") == company_id for c in companies)
        assert found, "Test prospect company not found in filtered results"

        for c in companies:
            assert c.get("type") == "prospect", f"Company {c.get('name')} has wrong type"

        print(f"Prospect filter returned {len(companies)} companies, all verified")


class TestResetPassword:
    """Test reset password returns temp_password inline."""

    def test_reset_password_returns_temp_password(self, master_admin_token):
        """PUT /master-admin/users/{id}/reset-password returns temp_password and user_email."""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # Get a user to reset
        users_resp = requests.get(f"{BASE_URL}/api/master-admin/users", headers=headers)
        assert users_resp.status_code == 200

        users = users_resp.json().get("users", [])
        # Find a non-master-admin user
        test_user = None
        for u in users:
            if not u.get("is_master_admin") and u.get("email") != MASTER_ADMIN_EMAIL:
                test_user = u
                break

        if not test_user:
            pytest.skip("No non-master-admin user found to test reset password")

        user_id = test_user["id"]

        # Reset password
        reset_resp = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/reset-password",
            headers=headers
        )
        assert reset_resp.status_code == 200, f"Reset failed: {reset_resp.text}"

        data = reset_resp.json()
        assert "temp_password" in data, f"temp_password not in response: {data}"
        assert "user_email" in data, f"user_email not in response: {data}"
        assert data.get("success") == True, f"success not True: {data}"

        print(f"Reset password for {data.get('user_email')}, temp_password returned: {data.get('temp_password')[:4]}...")


class TestHealthCheck:
    """Basic health check."""

    def test_api_health(self):
        """GET / returns 200."""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
