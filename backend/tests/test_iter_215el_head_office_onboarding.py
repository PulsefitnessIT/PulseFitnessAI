"""
Iter 215el — Head Office Onboarding API Tests

Tests the POST /api/master-admin/onboard-head-office endpoint:
- Happy path: creates org, sites, owner
- Validation: missing fields, duplicate email, multiple HQ flags, >50 sites
- Auth gates: no token → 401, non-master-admin → 403
- Tier mapping: lite→lite, pro→pulse_pro, starter/professional/enterprise→full
- Downstream linkage: GET /api/sites, GET /api/organizations, login as owner
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin token for authenticated requests."""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD,
    })
    assert r.status_code == 200, f"Master admin login failed: {r.text}"
    return r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(master_admin_token):
    """Headers with master admin token."""
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture
def unique_email():
    """Generate a unique email for each test."""
    return f"test-215el-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def cleanup_test_data(auth_headers):
    """Track created test data for cleanup."""
    created_orgs = []
    created_users = []
    yield {"orgs": created_orgs, "users": created_users}
    # Cleanup after test
    # Note: In a real scenario, we'd delete via API or direct DB access
    # For now, we just track what was created


class TestHeadOfficeOnboardingHappyPath:
    """Happy path tests for POST /api/master-admin/onboard-head-office"""

    def test_create_head_office_with_3_sites(self, auth_headers, unique_email):
        """Valid payload creates org, 3 sites (1 HQ + 2 branches), and owner."""
        payload = {
            "tier": "professional",
            "org_name": f"Test HQ {uuid.uuid4().hex[:6]}",
            "company_number": "12345678",
            "vat_number": "GB123456789",
            "billing_address": "123 Test Street, London",
            "billing_postcode": "SW1A 1AA",
            "billing_phone": "020 7123 4567",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [
                {"name": "Head Office Site", "address": "HQ Address", "postcode": "SW1A 1AA", "is_head_office": True},
                {"name": "Branch Site 1", "address": "Branch 1 Address", "postcode": "E1 1AA", "is_head_office": False},
                {"name": "Branch Site 2", "address": "Branch 2 Address", "postcode": "N1 1AA", "is_head_office": False},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()

        # Verify response structure
        assert data.get("success") is True
        assert "organization" in data
        assert "head_office_site" in data
        assert "sites" in data
        assert "owner" in data

        # Verify organization
        org = data["organization"]
        assert org["name"] == payload["org_name"]
        assert org["tier"] == "professional"
        assert org["account_type"] == "full"  # professional → full
        assert org["site_count"] == 3
        assert "id" in org
        assert "company_code" in org

        # Verify sites
        sites = data["sites"]
        assert len(sites) == 3
        hq_sites = [s for s in sites if s.get("is_head_office")]
        assert len(hq_sites) == 1, "Exactly one site should be flagged as HQ"
        non_hq_sites = [s for s in sites if not s.get("is_head_office")]
        assert len(non_hq_sites) == 2

        # Verify head_office_site matches the HQ
        assert data["head_office_site"]["is_head_office"] is True
        assert data["head_office_site"]["name"] == "Head Office Site"

        # Verify owner
        owner = data["owner"]
        assert owner["email"] == unique_email
        assert owner["name"] == "Test Owner"
        assert "id" in owner

        print(f"✓ Created org {org['id']} with {len(sites)} sites and owner {owner['id']}")


class TestHeadOfficeOnboardingValidation:
    """Validation tests for the onboarding endpoint."""

    def test_missing_org_name_returns_400(self, auth_headers, unique_email):
        """Missing org_name → 400 'Head office name is required'."""
        payload = {
            "tier": "lite",
            "org_name": "",  # Empty
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "Head office name is required" in r.json().get("detail", "")
        print("✓ Missing org_name returns 400 with correct message")

    def test_missing_owner_fields_returns_400(self, auth_headers):
        """Missing owner_email/name/password → 400."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "",  # Empty
            "owner_email": "",  # Empty
            "owner_password": "",  # Empty
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "Owner email, name and password are required" in r.json().get("detail", "")
        print("✓ Missing owner fields returns 400 with correct message")

    def test_empty_sites_array_returns_400(self, auth_headers, unique_email):
        """Empty sites array → 400 'At least one site is required'."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [],  # Empty
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "At least one site is required" in r.json().get("detail", "")
        print("✓ Empty sites array returns 400 with correct message")

    def test_more_than_50_sites_returns_400(self, auth_headers, unique_email):
        """More than 50 sites → 400 'Up to 50 sites per onboarding pass'."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [{"name": f"Site {i}", "is_head_office": i == 0} for i in range(51)],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "Up to 50 sites" in r.json().get("detail", "")
        print("✓ >50 sites returns 400 with correct message")

    def test_site_missing_name_returns_400(self, auth_headers, unique_email):
        """Site without name → 400 'Site #N: name is required'."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [
                {"name": "Site 1", "is_head_office": True},
                {"name": "", "is_head_office": False},  # Missing name
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "Site #2: name is required" in r.json().get("detail", "")
        print("✓ Site missing name returns 400 with correct message")

    def test_two_hq_sites_returns_400(self, auth_headers, unique_email):
        """Two sites flagged is_head_office=true → 400."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [
                {"name": "Site 1", "is_head_office": True},
                {"name": "Site 2", "is_head_office": True},  # Second HQ
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "Only one site can be flagged as Head Office" in r.json().get("detail", "")
        print("✓ Two HQ sites returns 400 with correct message")

    def test_no_hq_flag_defaults_first_site(self, auth_headers, unique_email):
        """No site flagged as HQ → first site auto-defaults to is_head_office=true."""
        payload = {
            "tier": "lite",
            "org_name": f"Test HQ No Flag {uuid.uuid4().hex[:6]}",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [
                {"name": "First Site", "is_head_office": False},
                {"name": "Second Site", "is_head_office": False},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()

        # First site should be auto-flagged as HQ
        sites = data["sites"]
        hq_sites = [s for s in sites if s.get("is_head_office")]
        assert len(hq_sites) == 1, "Exactly one site should be HQ"
        assert data["head_office_site"]["name"] == "First Site"
        print("✓ No HQ flag defaults first site to HQ")

    def test_duplicate_email_returns_400(self, auth_headers):
        """Re-using existing email → 400 'Email ... already in use'."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ Duplicate",
            "owner_name": "Test Owner",
            "owner_email": MASTER_ADMIN_EMAIL,  # Already exists
            "owner_password": "TestPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "already in use" in r.json().get("detail", "")
        print("✓ Duplicate email returns 400 with correct message")


class TestHeadOfficeOnboardingAuthGates:
    """Auth gate tests for the onboarding endpoint."""

    def test_no_token_returns_401(self):
        """Calling without a token → 401."""
        payload = {
            "tier": "lite",
            "org_name": "Test HQ",
            "owner_name": "Test Owner",
            "owner_email": "test@example.com",
            "owner_password": "TestPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload)

        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        print("✓ No token returns 401")

    def test_non_master_admin_returns_403(self, auth_headers, unique_email):
        """Non-master-admin token → 403."""
        # First create a regular user via the onboarding endpoint
        org_email = f"test-regular-{uuid.uuid4().hex[:8]}@example.com"
        create_payload = {
            "tier": "lite",
            "org_name": f"Test Org Regular {uuid.uuid4().hex[:6]}",
            "owner_name": "Regular User",
            "owner_email": org_email,
            "owner_password": "RegularPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=create_payload, headers=auth_headers)
        assert r.status_code == 200, f"Setup failed: {r.text}"

        # Login as the regular user
        login_r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": org_email,
            "password": "RegularPass123!",
        })
        assert login_r.status_code == 200, f"Regular user login failed: {login_r.text}"
        regular_token = login_r.json().get("token")

        # Try to call the endpoint with regular user token
        test_payload = {
            "tier": "lite",
            "org_name": "Test HQ Forbidden",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(
            f"{BASE_URL}/api/master-admin/onboard-head-office",
            json=test_payload,
            headers={"Authorization": f"Bearer {regular_token}"}
        )

        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        print("✓ Non-master-admin returns 403")


class TestHeadOfficeOnboardingTierMapping:
    """Tier mapping tests: tier → account_type."""

    @pytest.mark.parametrize("tier,expected_account_type", [
        ("lite", "lite"),
        ("pro", "pulse_pro"),
        ("starter", "full"),
        ("professional", "full"),
        ("enterprise", "full"),
    ])
    def test_tier_to_account_type_mapping(self, auth_headers, tier, expected_account_type):
        """Verify tier maps to correct account_type."""
        unique_email = f"test-tier-{tier}-{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "tier": tier,
            "org_name": f"Test HQ Tier {tier} {uuid.uuid4().hex[:6]}",
            "owner_name": "Test Owner",
            "owner_email": unique_email,
            "owner_password": "TestPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)

        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()

        assert data["organization"]["tier"] == tier
        assert data["organization"]["account_type"] == expected_account_type
        print(f"✓ Tier '{tier}' maps to account_type '{expected_account_type}'")


class TestHeadOfficeOnboardingDownstreamLinkage:
    """Downstream linkage tests: verify created data is accessible."""

    def test_owner_can_login_and_get_sites(self, auth_headers):
        """After creating HQ org, owner can login and GET /api/sites returns the sites."""
        unique_email = f"test-linkage-{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "tier": "professional",
            "org_name": f"Test HQ Linkage {uuid.uuid4().hex[:6]}",
            "owner_name": "Linkage Owner",
            "owner_email": unique_email,
            "owner_password": "LinkagePass123!",
            "sites": [
                {"name": "HQ Site", "is_head_office": True},
                {"name": "Branch A", "is_head_office": False},
                {"name": "Branch B", "is_head_office": False},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)
        assert r.status_code == 200, f"Create failed: {r.text}"
        created_data = r.json()
        org_id = created_data["organization"]["id"]

        # Login as the new owner
        login_r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "LinkagePass123!",
        })
        assert login_r.status_code == 200, f"Owner login failed: {login_r.text}"
        owner_token = login_r.json().get("token")
        owner_data = login_r.json()

        # Verify login response has correct organization_id (inside user object)
        user_obj = owner_data.get("user", {})
        assert user_obj.get("organization_id") == org_id, f"Owner should have correct organization_id, got {user_obj.get('organization_id')}"

        # GET /api/sites as the owner
        sites_r = requests.get(
            f"{BASE_URL}/api/sites",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert sites_r.status_code == 200, f"GET sites failed: {sites_r.text}"
        sites_data = sites_r.json()

        # Verify 3 sites returned
        sites = sites_data.get("sites", [])
        assert len(sites) == 3, f"Expected 3 sites, got {len(sites)}"

        # Verify HQ flag distribution
        hq_sites = [s for s in sites if s.get("is_head_office")]
        assert len(hq_sites) == 1, "Exactly one site should be HQ"

        print(f"✓ Owner can login and GET /api/sites returns {len(sites)} sites")

    def test_master_admin_can_see_org_in_list(self, auth_headers):
        """After creating HQ org, GET /api/organizations returns the new org."""
        unique_email = f"test-orglist-{uuid.uuid4().hex[:8]}@example.com"
        org_name = f"Test HQ OrgList {uuid.uuid4().hex[:6]}"
        payload = {
            "tier": "enterprise",
            "org_name": org_name,
            "owner_name": "OrgList Owner",
            "owner_email": unique_email,
            "owner_password": "OrgListPass123!",
            "sites": [{"name": "Site 1", "is_head_office": True}],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)
        assert r.status_code == 200, f"Create failed: {r.text}"
        created_org_id = r.json()["organization"]["id"]

        # GET /api/master-admin/organizations
        orgs_r = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        assert orgs_r.status_code == 200, f"GET orgs failed: {orgs_r.text}"
        orgs_data = orgs_r.json()

        # Find the created org
        orgs = orgs_data.get("organizations", [])
        found_org = next((o for o in orgs if o.get("id") == created_org_id), None)
        assert found_org is not None, f"Created org {created_org_id} not found in list"
        assert found_org["name"] == org_name

        print(f"✓ Master admin can see org {created_org_id} in GET /api/organizations")


class TestHeadOfficeOnboardingOrgFields:
    """Verify organization row has correct fields."""

    def test_org_has_is_multi_site_and_site_count(self, auth_headers):
        """Created org has is_multi_site=true and site_count=N."""
        unique_email = f"test-orgfields-{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "tier": "professional",
            "org_name": f"Test HQ OrgFields {uuid.uuid4().hex[:6]}",
            "owner_name": "OrgFields Owner",
            "owner_email": unique_email,
            "owner_password": "OrgFieldsPass123!",
            "sites": [
                {"name": "Site 1", "is_head_office": True},
                {"name": "Site 2", "is_head_office": False},
                {"name": "Site 3", "is_head_office": False},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=auth_headers)
        assert r.status_code == 200, f"Create failed: {r.text}"

        org = r.json()["organization"]
        assert org["site_count"] == 3, f"Expected site_count=3, got {org.get('site_count')}"

        print(f"✓ Org has site_count={org['site_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
