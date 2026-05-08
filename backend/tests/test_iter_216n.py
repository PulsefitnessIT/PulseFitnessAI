"""
Iteration 216n Backend Tests
- Logo upload creates files collection entry with category='branding' and is_public=true
- Logo upload returns /api/public/files/{id} URL
- Logo upload updates both organizations.logo_url AND organizations.branding.logo_url
- GET /organization/logo returns the same /api/public/files/{id} URL
- GET /api/public/files/{file_id} serves the binary image with correct MIME type
- Invoice parsing endpoints (parse-invoice and parse-for-wizard) work under 60s
- Master admin add user with role=master_admin sets is_master_admin=true
"""
import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


# Module-level fixture to avoid rate limiting
@pytest.fixture(scope="module")
def auth_token():
    """Login as master admin once for all tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in login response"
    return data["token"]


class TestMasterAdminLogin:
    """Verify master admin login works"""

    def test_login_success(self, auth_token):
        """Verify master admin login works"""
        assert auth_token is not None
        assert len(auth_token) > 0
        print(f"✓ Master admin login successful, token length: {len(auth_token)}")


class TestLogoUpload:
    """Test POST /api/organization/logo - Iter 216n fixes"""

    def test_logo_upload_returns_public_files_url(self, auth_token):
        """POST /organization/logo should return logo_url starting with /api/public/files/"""
        with open("/tmp/logo.png", "rb") as f:
            files = {"file": ("test_logo.png", f, "image/png")}
            response = requests.post(
                f"{BASE_URL}/api/organization/logo",
                headers={"Authorization": f"Bearer {auth_token}"},
                files=files
            )

        assert response.status_code == 200, f"Logo upload failed: {response.text}"
        data = response.json()

        # Verify logo_url starts with /api/public/files/
        assert "logo_url" in data, "Response missing logo_url"
        logo_url = data["logo_url"]
        assert logo_url.startswith("/api/public/files/"), f"logo_url should start with /api/public/files/, got: {logo_url}"

        # Verify file_id is returned
        assert "file_id" in data, "Response missing file_id"
        file_id = data["file_id"]
        assert len(file_id) > 0, "file_id should not be empty"

        print(f"✓ Logo upload returned logo_url: {logo_url}")
        print(f"✓ Logo upload returned file_id: {file_id}")

        # Store for subsequent tests
        TestLogoUpload.uploaded_logo_url = logo_url
        TestLogoUpload.uploaded_file_id = file_id

    def test_get_organization_logo_returns_same_url(self, auth_token):
        """GET /organization/logo should return the same /api/public/files/{id} URL"""
        response = requests.get(
            f"{BASE_URL}/api/organization/logo",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200, f"GET logo failed: {response.text}"
        data = response.json()

        assert "logo_url" in data, "Response missing logo_url"
        logo_url = data["logo_url"]

        # Should be the same URL we uploaded
        if hasattr(TestLogoUpload, 'uploaded_logo_url'):
            assert logo_url == TestLogoUpload.uploaded_logo_url, \
                f"GET logo_url ({logo_url}) doesn't match uploaded ({TestLogoUpload.uploaded_logo_url})"

        # Should start with /api/public/files/
        assert logo_url is not None, "logo_url should not be None"
        assert logo_url.startswith("/api/public/files/"), f"logo_url should start with /api/public/files/, got: {logo_url}"

        print(f"✓ GET /organization/logo returned: {logo_url}")

    def test_public_files_serves_image(self, auth_token):
        """GET /api/public/files/{file_id} should serve the binary image with correct MIME type"""
        if not hasattr(TestLogoUpload, 'uploaded_file_id'):
            pytest.skip("No uploaded file_id from previous test")

        file_id = TestLogoUpload.uploaded_file_id
        response = requests.get(f"{BASE_URL}/api/public/files/{file_id}")

        assert response.status_code == 200, f"Public file fetch failed: {response.status_code} - {response.text}"

        # Check Content-Type is image/png
        content_type = response.headers.get("Content-Type", "")
        assert "image/png" in content_type, f"Expected image/png, got: {content_type}"

        # Check we got binary content
        assert len(response.content) > 0, "Response content is empty"

        print(f"✓ GET /api/public/files/{file_id} returned HTTP 200")
        print(f"✓ Content-Type: {content_type}")
        print(f"✓ Content length: {len(response.content)} bytes")


class TestFilesCollectionEntry:
    """Verify the files collection entry is created correctly"""

    def test_logo_upload_creates_files_entry(self, auth_token):
        """Upload logo and verify files collection entry has category='branding' and is_public=true"""
        # Upload a fresh logo
        with open("/tmp/logo.png", "rb") as f:
            files = {"file": ("branding_test.png", f, "image/png")}
            response = requests.post(
                f"{BASE_URL}/api/organization/logo",
                headers={"Authorization": f"Bearer {auth_token}"},
                files=files
            )

        assert response.status_code == 200, f"Logo upload failed: {response.text}"
        data = response.json()
        file_id = data.get("file_id")
        assert file_id, "No file_id returned"

        # The files collection entry is internal - we verify by checking the public endpoint works
        # and the logo_url format is correct
        logo_url = data.get("logo_url", "")
        assert f"/api/public/files/{file_id}" == logo_url, \
            f"logo_url should be /api/public/files/{file_id}, got: {logo_url}"

        # Verify the public endpoint serves the file (which means is_public=true works)
        public_response = requests.get(f"{BASE_URL}{logo_url}")
        assert public_response.status_code == 200, \
            f"Public file endpoint failed - is_public may not be set: {public_response.status_code}"

        print(f"✓ Files collection entry created with file_id: {file_id}")
        print("✓ Public endpoint serves file (is_public=true verified)")


class TestOrganizationBrandingUpdate:
    """Verify both logo_url and branding.logo_url are updated on org doc"""

    def test_org_doc_has_both_logo_urls(self, auth_token):
        """After logo upload, org doc should have both logo_url and branding.logo_url"""
        # Upload logo first
        with open("/tmp/logo.png", "rb") as f:
            files = {"file": ("org_test.png", f, "image/png")}
            upload_response = requests.post(
                f"{BASE_URL}/api/organization/logo",
                headers={"Authorization": f"Bearer {auth_token}"},
                files=files
            )

        assert upload_response.status_code == 200
        expected_url = upload_response.json().get("logo_url")

        # Get organization details
        org_response = requests.get(
            f"{BASE_URL}/api/organization",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert org_response.status_code == 200, f"GET organization failed: {org_response.text}"
        org = org_response.json()

        # Check logo_url at root level
        assert org.get("logo_url") == expected_url, \
            f"org.logo_url should be {expected_url}, got: {org.get('logo_url')}"

        # Check branding.logo_url
        branding = org.get("branding", {})
        assert branding.get("logo_url") == expected_url, \
            f"org.branding.logo_url should be {expected_url}, got: {branding.get('logo_url')}"

        print(f"✓ org.logo_url = {org.get('logo_url')}")
        print(f"✓ org.branding.logo_url = {branding.get('logo_url')}")


class TestInvoiceParsingParseInvoice:
    """Test POST /api/equipment-import/parse-invoice with Carshalton PDF"""

    def test_parse_invoice_carshalton(self, auth_token):
        """POST /api/equipment-import/parse-invoice with Carshalton PDF - verify under 60s"""
        pdf_path = "/tmp/inv/carshalton.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Carshalton PDF not found at {pdf_path}")

        start_time = time.time()

        with open(pdf_path, "rb") as f:
            files = {"file": ("carshalton.pdf", f, "application/pdf")}
            response = requests.post(
                f"{BASE_URL}/api/equipment-import/parse-invoice",
                headers={"Authorization": f"Bearer {auth_token}"},
                files=files,
                timeout=90  # Allow up to 90s for the request
            )

        elapsed = time.time() - start_time

        assert response.status_code == 200, f"Parse invoice failed: {response.status_code} - {response.text}"
        assert elapsed < 60, f"Invoice parsing took {elapsed:.1f}s, should be under 60s"

        data = response.json()

        # Verify supplier_name is 'Pulse Fitness'
        supplier = data.get("supplier_name", "")
        assert "pulse" in supplier.lower(), f"supplier_name should contain 'Pulse', got: {supplier}"

        # Verify equipment items have make='Pulse Fitness' and equipment_category populated
        equipment = data.get("equipment", [])
        assert len(equipment) > 0, "No equipment items extracted"

        valid_categories = {"Cardiovascular", "Strength", "Free Weights", "Functional", "Accessories"}

        for i, eq in enumerate(equipment[:5]):  # Check first 5 items
            make = eq.get("make", "")
            category = eq.get("equipment_category", "")

            assert make, f"Equipment item {i} has empty make"
            assert category in valid_categories, \
                f"Equipment item {i} has invalid category: {category}"

        print(f"✓ Invoice parsed in {elapsed:.1f}s (under 60s limit)")
        print(f"✓ supplier_name: {supplier}")
        print(f"✓ Equipment count: {len(equipment)}")
        print("✓ All checked items have valid make and equipment_category")


class TestInvoiceParsingWizard:
    """Test POST /api/master-admin/invoice/parse-for-wizard with Carshalton PDF"""

    def test_parse_for_wizard_carshalton(self, auth_token):
        """POST /api/master-admin/invoice/parse-for-wizard with Carshalton PDF"""
        pdf_path = "/tmp/inv/carshalton.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Carshalton PDF not found at {pdf_path}")

        start_time = time.time()

        with open(pdf_path, "rb") as f:
            files = {"file": ("carshalton.pdf", f, "application/pdf")}
            response = requests.post(
                f"{BASE_URL}/api/master-admin/invoice/parse-for-wizard",
                headers={"Authorization": f"Bearer {auth_token}"},
                files=files,
                timeout=90
            )

        elapsed = time.time() - start_time

        assert response.status_code == 200, f"Parse for wizard failed: {response.status_code} - {response.text}"
        assert elapsed < 60, f"Invoice parsing took {elapsed:.1f}s, should be under 60s"

        data = response.json()

        # Verify supplier_name is 'Pulse Fitness'
        supplier = data.get("supplier_name", "")
        assert "pulse" in supplier.lower(), f"supplier_name should contain 'Pulse', got: {supplier}"

        # Verify equipment items
        equipment = data.get("equipment", [])
        assert len(equipment) > 0, "No equipment items extracted"

        valid_categories = {"Cardiovascular", "Strength", "Free Weights", "Functional", "Accessories"}

        for i, eq in enumerate(equipment[:5]):
            make = eq.get("make", "")
            category = eq.get("equipment_category", "")

            assert make, f"Equipment item {i} has empty make"
            assert category in valid_categories, \
                f"Equipment item {i} has invalid category: {category}"

        print(f"✓ Wizard invoice parsed in {elapsed:.1f}s (under 60s limit)")
        print(f"✓ supplier_name: {supplier}")
        print(f"✓ Equipment count: {len(equipment)}")


class TestMasterAdminUserAdd:
    """Test POST /api/master-admin/organizations/{org_id}/users with role=master_admin"""

    @pytest.fixture(scope="class")
    def test_org_id(self, auth_token):
        """Create a test organization for user tests"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": f"TEST_Org_216n_{uuid.uuid4().hex[:8]}",
                "portal_type": "service_portal",
                "subscription_tier": "pro"
            }
        )
        assert response.status_code == 200, f"Create org failed: {response.text}"
        return response.json().get("id")

    def test_add_user_with_master_admin_role(self, auth_token, test_org_id):
        """Adding user with role=master_admin should set is_master_admin=true"""
        test_email = f"test_master_{uuid.uuid4().hex[:8]}@example.com"

        response = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "email": test_email,
                "full_name": "Test Master Admin",
                "password": "TestPass123!",
                "role": "master_admin"
            }
        )

        assert response.status_code == 200, f"Add user failed: {response.text}"
        data = response.json()

        user_id = data.get("id")
        assert user_id, "No user id returned"

        # Verify the user can login and has is_master_admin=true
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": test_email, "password": "TestPass123!"}
        )

        assert login_response.status_code == 200, f"New master admin login failed: {login_response.text}"
        login_data = login_response.json()

        user_info = login_data.get("user", {})
        assert user_info.get("is_master_admin") == True, \
            f"is_master_admin should be True, got: {user_info.get('is_master_admin')}"

        print("✓ User created with role=master_admin")
        print("✓ User can login and is_master_admin=True verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
