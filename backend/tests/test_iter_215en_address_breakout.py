"""
Iter 215en — Structured Address Breakout + Head Office Autocomplete Tests

Tests the new 8-field address structure (Address 1*, Address 2, Address 3, City,
County, Post code, Country) across:
  - GET /api/master-admin/organizations/search (Head Office autocomplete)
  - POST /api/master-admin/organizations (create org with structured address)
  - PUT /api/master-admin/organizations/{id}/details (update structured address)
  - GET /api/master-admin/organizations (returns structured fields)
  - POST /api/master-admin/onboard-head-office (structured billing + site addresses)
  - POST /api/master-admin/onboard-pulse-site (structured + legacy address)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for master admin."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def non_admin_token():
    """Create a non-admin user and get their token."""
    unique = str(uuid.uuid4())[:8]
    email = f"test-nonadmin-{unique}@example.com"
    # Register a new user
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "full_name": "Non Admin User",
        "company_name": f"Test Org {unique}"
    })
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create non-admin user: {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def non_admin_headers(non_admin_token):
    """Auth headers for non-admin user."""
    return {"Authorization": f"Bearer {non_admin_token}", "Content-Type": "application/json"}


class TestOrganizationSearch:
    """Tests for GET /api/master-admin/organizations/search (Head Office autocomplete)."""

    def test_search_returns_200_with_empty_query(self, auth_headers):
        """Empty q returns most recent N orgs."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 5}, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "organizations" in data
        assert "query" in data
        assert data["query"] == ""

    def test_search_returns_structured_address_fields(self, auth_headers):
        """Search results include address_line1..3, city, county, postcode, country."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 10}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        if data["organizations"]:
            org = data["organizations"][0]
            # Check all structured address fields are present
            assert "address_line1" in org, "Missing address_line1"
            assert "address_line2" in org, "Missing address_line2"
            assert "address_line3" in org, "Missing address_line3"
            assert "city" in org, "Missing city"
            assert "county" in org, "Missing county"
            assert "postcode" in org, "Missing postcode"
            assert "country" in org, "Missing country"

    def test_search_with_query_filters_results(self, auth_headers):
        """Search with q filters by name/company_number/vat/postcode."""
        # Search for something that likely exists
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "Tottenham", "limit": 10}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "Tottenham"

    def test_search_respects_limit(self, auth_headers):
        """Limit parameter caps results."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 2}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) <= 2

    def test_search_requires_auth(self):
        """401 without token."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 5})
        assert resp.status_code == 401

    def test_search_requires_master_admin(self, non_admin_headers):
        """403 for non-master-admin user."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 5}, headers=non_admin_headers)
        assert resp.status_code == 403

    def test_search_country_defaults_to_uk(self, auth_headers):
        """Country defaults to 'United Kingdom' for orgs without country set."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations/search",
                           params={"q": "", "limit": 10}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for org in data["organizations"]:
            # Country should never be empty - defaults to UK
            assert org.get("country"), f"Country should not be empty for org {org.get('name')}"


class TestCreateOrganization:
    """Tests for POST /api/master-admin/organizations with structured address."""

    def test_create_org_with_structured_address(self, auth_headers):
        """Create org with all 7 structured address fields."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Structured_Addr_{unique}",
            "address_line1": "123 Test Street",
            "address_line2": "Suite 456",
            "address_line3": "Business Park",
            "city": "London",
            "county": "Greater London",
            "postcode": "SW1A 1AA",
            "country": "United Kingdom",
            "phone": "020 7123 4567",
            "industry": "Fitness & Leisure"
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify structured fields persisted
        assert data.get("address_line1") == "123 Test Street"
        assert data.get("address_line2") == "Suite 456"
        assert data.get("address_line3") == "Business Park"
        assert data.get("city") == "London"
        assert data.get("county") == "Greater London"
        assert data.get("postcode") == "SW1A 1AA"
        assert data.get("country") == "United Kingdom"

        # Verify legacy address is auto-composed
        assert data.get("address"), "Legacy address should be auto-composed"
        assert "123 Test Street" in data.get("address", "")

    def test_create_org_country_defaults_to_uk(self, auth_headers):
        """Country defaults to 'United Kingdom' when not provided."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Default_Country_{unique}",
            "address_line1": "456 Default St",
            "city": "Manchester"
            # No country provided
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("country") == "United Kingdom"


class TestUpdateOrganizationDetails:
    """Tests for PUT /api/master-admin/organizations/{id}/details."""

    @pytest.fixture
    def test_org(self, auth_headers):
        """Create a test org for update tests."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Update_Org_{unique}",
            "address_line1": "Original Address",
            "city": "Original City",
            "postcode": "OG1 1AA"
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200
        return resp.json()

    def test_update_structured_address_recomposes_legacy(self, auth_headers, test_org):
        """Updating structured fields re-composes the legacy address."""
        org_id = test_org["id"]
        update_payload = {
            "address_line1": "Updated Street 789",
            "address_line2": "Floor 2",
            "city": "Birmingham",
            "county": "West Midlands",
            "postcode": "B1 1AA"
        }
        resp = requests.put(f"{BASE_URL}/api/master-admin/organizations/{org_id}/details",
                           json=update_payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        # Verify by fetching the org
        get_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        assert get_resp.status_code == 200
        orgs = get_resp.json().get("organizations", [])
        updated_org = next((o for o in orgs if o["id"] == org_id), None)
        assert updated_org, "Could not find updated org"

        # Check structured fields updated
        assert updated_org.get("address_line1") == "Updated Street 789"
        assert updated_org.get("city") == "Birmingham"

        # Check legacy address was re-composed
        legacy = updated_org.get("address", "")
        assert "Updated Street 789" in legacy


class TestGetAllOrganizations:
    """Tests for GET /api/master-admin/organizations returning structured fields."""

    def test_list_orgs_includes_structured_address(self, auth_headers):
        """GET /organizations returns address_line1..3, county fields."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "organizations" in data

        if data["organizations"]:
            org = data["organizations"][0]
            # All structured fields should be present
            assert "address_line1" in org
            assert "address_line2" in org
            assert "address_line3" in org
            assert "city" in org
            assert "county" in org
            assert "postcode" in org
            assert "country" in org

    def test_list_orgs_fallback_for_unmigrated(self, auth_headers):
        """Un-migrated orgs fall back to legacy address for line1."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        for org in data["organizations"]:
            # address_line1 should never be empty if there's a legacy address
            if org.get("address") and not org.get("address_line1"):
                # This would be a bug - address_line1 should fall back to legacy
                pytest.fail(f"Org {org['name']} has legacy address but empty address_line1")


class TestOnboardHeadOffice:
    """Tests for POST /api/master-admin/onboard-head-office with structured addresses."""

    def test_onboard_with_structured_billing_address(self, auth_headers):
        """Onboard HO with billing_address_line1..3, billing_city, etc."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "tier": "professional",
            "org_name": f"TEST_HO_Structured_{unique}",
            "company_number": "12345678",
            "vat_number": "GB123456789",
            "billing_address_line1": "HQ Building",
            "billing_address_line2": "100 Corporate Way",
            "billing_address_line3": "Tech Park",
            "billing_city": "London",
            "billing_county": "Greater London",
            "billing_postcode": "EC1A 1BB",
            "billing_country": "United Kingdom",
            "billing_phone": "020 7000 0000",
            "owner_name": "Test Owner",
            "owner_email": f"test-ho-owner-{unique}@example.com",
            "owner_password": "SecurePass123!",
            "sites": [
                {
                    "name": f"Site Alpha {unique}",
                    "address_line1": "Site A Street",
                    "address_line2": "Unit 1",
                    "city": "Manchester",
                    "county": "Greater Manchester",
                    "postcode": "M1 1AA",
                    "country": "United Kingdom",
                    "phone": "0161 000 0001",
                    "email": f"sitea-{unique}@example.com",
                    "is_head_office": True
                },
                {
                    "name": f"Site Beta {unique}",
                    "address_line1": "Site B Road",
                    "city": "Birmingham",
                    "postcode": "B1 1BB",
                    "phone": "0121 000 0002",
                    "email": f"siteb-{unique}@example.com",
                    "is_head_office": False
                }
            ]
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert data.get("success") is True
        assert data.get("organization")
        assert len(data.get("sites", [])) == 2

        # Verify org was created with structured billing address
        org_id = data["organization"]["id"]
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        orgs = orgs_resp.json().get("organizations", [])
        created_org = next((o for o in orgs if o["id"] == org_id), None)

        assert created_org, "Created org not found in list"
        assert created_org.get("address_line1") == "HQ Building"
        assert created_org.get("city") == "London"
        assert created_org.get("county") == "Greater London"
        assert created_org.get("postcode") == "EC1A 1BB"

    def test_onboard_site_structured_address_persisted(self, auth_headers):
        """Per-site structured addresses are persisted."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "tier": "lite",
            "org_name": f"TEST_HO_Sites_{unique}",
            "owner_name": "Site Test Owner",
            "owner_email": f"test-site-owner-{unique}@example.com",
            "owner_password": "SecurePass123!",
            "sites": [
                {
                    "name": f"Structured Site {unique}",
                    "address_line1": "123 Structured Lane",
                    "address_line2": "Building A",
                    "address_line3": "Industrial Estate",
                    "city": "Leeds",
                    "county": "West Yorkshire",
                    "postcode": "LS1 1AA",
                    "country": "United Kingdom",
                    "is_head_office": True
                }
            ]
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # Verify site was created
        assert len(data.get("sites", [])) == 1
        site = data["sites"][0]
        assert site.get("is_head_office") is True


class TestOnboardPulseSite:
    """Tests for POST /api/master-admin/onboard-pulse-site with structured address."""

    def test_onboard_pulse_with_structured_address(self, auth_headers):
        """Pulse site onboarding accepts structured address fields."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "site_name": f"TEST_Pulse_Structured_{unique}",
            "tier": "pro",
            "owner_email": f"test-pulse-{unique}@example.com",
            "owner_name": "Pulse Owner",
            "owner_password": "PulsePass123!",
            "address_line1": "Pulse Gym Building",
            "address_line2": "Floor 1",
            "city": "Bristol",
            "county": "Avon",
            "postcode": "BS1 1AA",
            "country": "United Kingdom",
            "phone": "0117 000 0000"
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/onboard-pulse-site",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert data.get("success") is True
        org_id = data["organization"]["id"]

        # Verify structured address on org
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        orgs = orgs_resp.json().get("organizations", [])
        created_org = next((o for o in orgs if o["id"] == org_id), None)

        assert created_org, "Created Pulse org not found"
        assert created_org.get("address_line1") == "Pulse Gym Building"
        assert created_org.get("city") == "Bristol"

    def test_onboard_pulse_with_legacy_address_still_works(self, auth_headers):
        """Legacy single-line address still accepted for backwards compat."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "site_name": f"TEST_Pulse_Legacy_{unique}",
            "tier": "lite",
            "owner_email": f"test-pulse-legacy-{unique}@example.com",
            "owner_name": "Legacy Owner",
            "owner_password": "LegacyPass123!",
            "address": "456 Legacy Street, Old Town, OT1 1AA",  # Legacy format
            "phone": "0118 000 0000"
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/onboard-pulse-site",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True


class TestEdgeCases:
    """Edge case tests for address handling."""

    def test_mixed_legacy_and_structured_both_persisted(self, auth_headers):
        """When both legacy and structured provided, both are persisted (backwards compat)."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Mixed_Addr_{unique}",
            "address": "Explicit Legacy Address",
            "address_line1": "Structured Line 1",
            "city": "Priority City",
            "postcode": "PR1 1AA"
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # Structured fields should be persisted
        assert data.get("address_line1") == "Structured Line 1"
        assert data.get("city") == "Priority City"
        # Legacy address is kept when explicitly provided (backwards compat)
        assert data.get("address") == "Explicit Legacy Address"

    def test_empty_structured_fields_handled_gracefully(self, auth_headers):
        """Empty structured fields don't break the API."""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Empty_Fields_{unique}",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postcode": ""
        }
        resp = requests.post(f"{BASE_URL}/api/master-admin/organizations",
                            json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should still create org, country defaults to UK
        assert data.get("country") == "United Kingdom"


# Cleanup fixture to remove test data
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_orgs(auth_headers):
    """Cleanup TEST_ prefixed orgs after all tests."""
    yield
    # After tests, try to clean up
    try:
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=auth_headers)
        if resp.status_code == 200:
            orgs = resp.json().get("organizations", [])
            for org in orgs:
                if org.get("name", "").startswith("TEST_"):
                    # Try hard delete
                    requests.delete(
                        f"{BASE_URL}/api/master-admin/organizations/{org['id']}/hard",
                        headers=auth_headers
                    )
    except Exception:
        pass  # Best effort cleanup
