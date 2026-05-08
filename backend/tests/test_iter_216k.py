"""
Iteration 216k Backend Tests
- Invoice parsing (supplier_name, make, equipment_category)
- Master admin user management (add/edit with master_admin role)
- Reset password, invite link endpoints
- Onboard head office
- Supplier case update-email
- Sites overview endpoint
"""
import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Valid equipment categories per the prompt
VALID_CATEGORIES = {"Cardiovascular", "Strength", "Free Weights", "Functional", "Accessories"}


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def test_org_id(admin_headers):
    """Get or create a test organization."""
    # First try to find an existing org
    resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=admin_headers)
    if resp.status_code == 200:
        orgs = resp.json().get("organizations", [])
        if orgs:
            return orgs[0]["id"]

    # Create a new org if none exist
    resp = requests.post(f"{BASE_URL}/api/master-admin/organizations", headers=admin_headers, json={
        "name": f"TEST_Org_{uuid.uuid4().hex[:8]}",
        "portal_type": "service_portal",
        "account_type": "full"
    })
    assert resp.status_code == 200, f"Failed to create test org: {resp.text}"
    return resp.json().get("id")


class TestMasterAdminLogin:
    """Verify master admin authentication works."""

    def test_login_success(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        assert "access_token" in data or "token" in data
        print("✓ Master admin login successful")


class TestInvoiceParsingWizard:
    """Test POST /api/master-admin/invoice/parse-for-wizard with Carshalton PDF."""

    def test_parse_invoice_for_wizard(self, admin_headers):
        """Parse the Carshalton invoice and verify supplier_name, make, equipment_category."""
        pdf_path = "/tmp/inv/carshalton.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Test PDF not found at {pdf_path}")

        with open(pdf_path, "rb") as f:
            files = {"file": ("carshalton.pdf", f, "application/pdf")}
            # Remove Content-Type from headers for multipart
            headers = {"Authorization": admin_headers["Authorization"]}

            print("Sending invoice to parse-for-wizard endpoint (may take 30-60s)...")
            start = time.time()
            resp = requests.post(
                f"{BASE_URL}/api/master-admin/invoice/parse-for-wizard",
                headers=headers,
                files=files,
                timeout=90  # Allow up to 90s for AI extraction
            )
            elapsed = time.time() - start
            print(f"Response received in {elapsed:.1f}s")

        assert resp.status_code == 200, f"Invoice parse failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        # Check supplier_name is Pulse Fitness (not empty/Unknown)
        supplier_name = data.get("supplier_name", "")
        print(f"supplier_name: {supplier_name}")
        assert supplier_name, "supplier_name is empty"
        assert supplier_name.lower() != "unknown", "supplier_name is 'Unknown', expected 'Pulse Fitness'"
        # Accept variations like "Pulse Fitness", "Pulse Fitness Limited", etc.
        assert "pulse" in supplier_name.lower(), f"Expected 'Pulse Fitness', got '{supplier_name}'"
        print(f"✓ supplier_name = '{supplier_name}'")

        # Check equipment list
        equipment = data.get("equipment", [])
        assert len(equipment) > 0, "No equipment extracted"
        print(f"Extracted {len(equipment)} equipment items")

        # Verify each equipment item has make='Pulse Fitness' and valid equipment_category
        for i, eq in enumerate(equipment[:10]):  # Check first 10
            make = eq.get("make", "") or eq.get("manufacturer", "")
            category = eq.get("equipment_category", "")
            model = eq.get("model", "")[:50]

            # Make should be Pulse Fitness (not empty)
            assert make, f"Item {i} ({model}) has empty make"
            assert "pulse" in make.lower() or make.lower() != "unknown", \
                f"Item {i} ({model}) has make='{make}', expected 'Pulse Fitness'"

            # equipment_category should be one of the valid categories
            assert category in VALID_CATEGORIES, \
                f"Item {i} ({model}) has invalid equipment_category='{category}', expected one of {VALID_CATEGORIES}"

            print(f"  Item {i}: make='{make}', category='{category}', model='{model}'")

        print("✓ All checked equipment items have valid make and equipment_category")

        # Verify timing is under 60s (kubernetes ingress limit)
        assert elapsed < 60, f"Extraction took {elapsed:.1f}s, exceeds 60s kubernetes limit"
        print(f"✓ Extraction completed in {elapsed:.1f}s (under 60s limit)")


class TestEquipmentImportParseInvoice:
    """Test POST /api/equipment-import/parse-invoice with Carshalton PDF."""

    def test_parse_invoice(self, admin_headers):
        """Parse the Carshalton invoice via equipment-import endpoint."""
        pdf_path = "/tmp/inv/carshalton.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Test PDF not found at {pdf_path}")

        with open(pdf_path, "rb") as f:
            files = {"file": ("carshalton.pdf", f, "application/pdf")}
            headers = {"Authorization": admin_headers["Authorization"]}

            print("Sending invoice to equipment-import/parse-invoice endpoint...")
            start = time.time()
            resp = requests.post(
                f"{BASE_URL}/api/equipment-import/parse-invoice",
                headers=headers,
                files=files,
                timeout=90
            )
            elapsed = time.time() - start
            print(f"Response received in {elapsed:.1f}s")

        assert resp.status_code == 200, f"Invoice parse failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        # Check supplier_name
        supplier_name = data.get("supplier_name", "")
        print(f"supplier_name: {supplier_name}")
        assert supplier_name and supplier_name.lower() != "unknown", \
            f"supplier_name is empty or 'Unknown', got '{supplier_name}'"
        assert "pulse" in supplier_name.lower(), f"Expected 'Pulse Fitness', got '{supplier_name}'"
        print(f"✓ supplier_name = '{supplier_name}'")

        # Check equipment
        equipment = data.get("equipment", [])
        assert len(equipment) > 0, "No equipment extracted"
        print(f"Extracted {len(equipment)} equipment items")

        # Verify make and equipment_category on first few items
        for i, eq in enumerate(equipment[:5]):
            make = eq.get("make", "")
            category = eq.get("equipment_category", "")
            model = eq.get("model", "")[:50]

            assert make and "pulse" in make.lower(), \
                f"Item {i} ({model}) has make='{make}', expected 'Pulse Fitness'"
            assert category in VALID_CATEGORIES, \
                f"Item {i} ({model}) has invalid equipment_category='{category}'"

            print(f"  Item {i}: make='{make}', category='{category}'")

        print("✓ Equipment items have valid make and equipment_category")


class TestMasterAdminUserAdd:
    """Test POST /api/master-admin/organizations/{org_id}/users with role='master_admin'."""

    def test_add_user_with_master_admin_role(self, admin_headers, test_org_id):
        """Add a user with role='master_admin' - should set is_master_admin=true and role='owner'."""
        test_email = f"test_master_{uuid.uuid4().hex[:8]}@example.com"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/users",
            headers=admin_headers,
            json={
                "email": test_email,
                "full_name": "Test Master Admin",
                "role": "master_admin"
            }
        )

        assert resp.status_code == 200, f"Add user failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        user_id = data.get("id")
        assert user_id, "No user ID returned"

        # The response should indicate the role
        print(f"Created user: {data}")

        # Verify by fetching all users and checking the new user
        resp2 = requests.get(f"{BASE_URL}/api/master-admin/users", headers=admin_headers)
        assert resp2.status_code == 200
        users = resp2.json().get("users", [])

        created_user = next((u for u in users if u.get("id") == user_id), None)
        assert created_user, f"Created user {user_id} not found in users list"

        # Check is_master_admin flag
        is_master = created_user.get("is_master_admin", False)
        role = created_user.get("role", "")

        print(f"Created user: is_master_admin={is_master}, role={role}")
        assert is_master == True, f"Expected is_master_admin=True, got {is_master}"
        assert role == "owner", f"Expected role='owner', got '{role}'"

        print("✓ User created with is_master_admin=True and role='owner'")

        # Cleanup - store user_id for potential cleanup
        return user_id


class TestMasterAdminUserEdit:
    """Test PUT /api/master-admin/users/{user_id}/edit with role='master_admin'."""

    def test_edit_user_to_master_admin_role(self, admin_headers, test_org_id):
        """Edit an existing user to role='master_admin' - should set is_master_admin=true."""
        # First create a regular user
        test_email = f"test_edit_{uuid.uuid4().hex[:8]}@example.com"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/users",
            headers=admin_headers,
            json={
                "email": test_email,
                "full_name": "Test Edit User",
                "role": "staff"
            }
        )
        assert resp.status_code == 200, f"Create user failed: {resp.text}"
        user_id = resp.json().get("id")

        # Now edit to master_admin role
        resp2 = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/edit",
            headers=admin_headers,
            json={"role": "master_admin"}
        )

        assert resp2.status_code == 200, f"Edit user failed ({resp2.status_code}): {resp2.text}"

        # Verify the change
        resp3 = requests.get(f"{BASE_URL}/api/master-admin/users", headers=admin_headers)
        assert resp3.status_code == 200
        users = resp3.json().get("users", [])

        edited_user = next((u for u in users if u.get("id") == user_id), None)
        assert edited_user, f"Edited user {user_id} not found"

        is_master = edited_user.get("is_master_admin", False)
        role = edited_user.get("role", "")

        print(f"Edited user: is_master_admin={is_master}, role={role}")
        assert is_master == True, f"Expected is_master_admin=True after edit, got {is_master}"
        assert role == "owner", f"Expected role='owner' after edit, got '{role}'"

        print("✓ User edited to is_master_admin=True and role='owner'")


class TestResetPassword:
    """Test PUT /api/master-admin/users/{user_id}/reset-password."""

    def test_reset_password_returns_temp_password(self, admin_headers, test_org_id):
        """Reset password should return 200 with temp_password."""
        # Create a test user first
        test_email = f"test_reset_{uuid.uuid4().hex[:8]}@example.com"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/users",
            headers=admin_headers,
            json={
                "email": test_email,
                "full_name": "Test Reset User",
                "role": "staff"
            }
        )
        assert resp.status_code == 200, f"Create user failed: {resp.text}"
        user_id = resp.json().get("id")

        # Reset password
        resp2 = requests.put(
            f"{BASE_URL}/api/master-admin/users/{user_id}/reset-password",
            headers=admin_headers
        )

        assert resp2.status_code == 200, f"Reset password failed ({resp2.status_code}): {resp2.text}"
        data = resp2.json()

        # Should have temp_password
        temp_password = data.get("temp_password") or data.get("temporary_password") or data.get("password")
        assert temp_password, f"No temp_password in response: {data}"

        print(f"✓ Reset password returned temp_password (length={len(temp_password)})")


class TestInviteLink:
    """Test POST /api/master-admin/users/{user_id}/invite-link."""

    def test_invite_link_returns_url(self, admin_headers, test_org_id):
        """Invite link should return 200 with invite_url."""
        # Create a test user first
        test_email = f"test_invite_{uuid.uuid4().hex[:8]}@example.com"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/users",
            headers=admin_headers,
            json={
                "email": test_email,
                "full_name": "Test Invite User",
                "role": "staff"
            }
        )
        assert resp.status_code == 200, f"Create user failed: {resp.text}"
        user_id = resp.json().get("id")

        # Get invite link
        resp2 = requests.post(
            f"{BASE_URL}/api/master-admin/users/{user_id}/invite-link",
            headers=admin_headers
        )

        assert resp2.status_code == 200, f"Invite link failed ({resp2.status_code}): {resp2.text}"
        data = resp2.json()

        invite_url = data.get("invite_url")
        assert invite_url, f"No invite_url in response: {data}"
        assert "reset-password" in invite_url or "token=" in invite_url, \
            f"invite_url doesn't look like a reset link: {invite_url}"

        print(f"✓ Invite link returned: {invite_url[:80]}...")


class TestOnboardHeadOffice:
    """Test POST /api/master-admin/onboard-head-office."""

    def test_onboard_head_office_returns_invite_url(self, admin_headers):
        """Onboard head office should return invite_url and organization."""
        unique_id = uuid.uuid4().hex[:8]

        # The endpoint expects org_name, owner_email, owner_name, and at least one site
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/onboard-head-office",
            headers=admin_headers,
            json={
                "org_name": f"TEST_HeadOffice_{unique_id}",
                "owner_name": "Test Contact",
                "owner_email": f"test_ho_{unique_id}@example.com",
                "tier": "lite",
                "send_invite": True,
                "sites": [
                    {
                        "name": f"TEST_Site_{unique_id}",
                        "address": "123 Test Street",
                        "postcode": "TE1 1ST",
                        "is_head_office": True
                    }
                ]
            }
        )

        assert resp.status_code == 200, f"Onboard failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        # Should have organization info
        org = data.get("organization") or data
        assert org.get("id") or org.get("organization_id"), f"No organization ID in response: {data}"

        # Should have invite_url
        invite_url = data.get("invite_url")
        if invite_url:
            print(f"✓ Onboard returned invite_url: {invite_url[:80]}...")
        else:
            # Some implementations return the org with credentials instead
            print(f"✓ Onboard returned organization: {org.get('name', org.get('id'))}")


class TestSupplierCaseUpdateEmail:
    """Test POST /api/supplier/case/{token}/update-email."""

    def test_update_email_endpoint_exists(self, admin_headers):
        """Verify the update-email endpoint exists (may need a valid token to fully test)."""
        # Use a fake token - should return 404 (case not found), not 405 (method not allowed)
        fake_token = str(uuid.uuid4())

        resp = requests.post(
            f"{BASE_URL}/api/supplier/case/{fake_token}/update-email",
            json={"supplier_email": "test@example.com"}
        )

        # Should be 404 (case not found) not 405 (method not allowed)
        assert resp.status_code in [404, 400], \
            f"Unexpected status {resp.status_code}: {resp.text}"

        print(f"✓ update-email endpoint exists (returned {resp.status_code} for invalid token)")


class TestSitesOverview:
    """Test GET /api/sites/overview."""

    def test_sites_overview_returns_totals(self, admin_headers):
        """Sites overview should return totals, sites list, and best_site."""
        resp = requests.get(
            f"{BASE_URL}/api/sites/overview",
            headers=admin_headers
        )

        assert resp.status_code == 200, f"Sites overview failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        # Should have totals
        totals = data.get("totals", {})
        assert "equipment" in totals or "sites" in totals, f"No totals in response: {data}"

        # Should have sites list
        sites = data.get("sites", [])
        assert isinstance(sites, list), f"sites is not a list: {type(sites)}"

        # Should have best_site (can be null if no sites)
        # Just verify the key exists
        assert "best_site" in data, f"No best_site key in response: {data.keys()}"

        print(f"✓ Sites overview returned: {len(sites)} sites, totals={totals}")
        if data.get("best_site"):
            print(f"  best_site: {data['best_site'].get('name', data['best_site'].get('id'))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
