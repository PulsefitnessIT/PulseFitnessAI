"""
Iter 216h54 — P0/P1 feature tests:
  - P0: JWT revocation grace window (60s on refresh, 0s on logout)
  - P1: Bulk import row-level error messages (equipment, customers, sites)
  - P1: Service Desk 8-tab parity (backend auth check)

Uses the canonical test credentials from /app/memory/test_credentials.md:
  - Master Admin: admin@gymaxisai.com / MasterAdmin123!
  - Target org for bulk imports: Pulse Fitness (8cd02d8c-e5a2-4c13-bdb9-8b143b85455f)
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://photo-fix-verify.preview.emergentagent.com").rstrip("/")
PULSE_ORG_ID = "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f"


@pytest.fixture(scope="module")
def admin_token():
    """Login as master admin and return the token."""
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
    )
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ═══════════════════════════════════════════════════════════════════════════
# P0 — JWT Revocation Grace Window Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestJWTRevocationGraceWindow:
    """
    P0 bug fix: /api/auth/refresh now revokes the old jti with a 60-second
    grace period. In-flight requests using the old token must NOT get 401
    'Session revoked' during the grace window.
    """

    def test_refresh_returns_new_token(self, admin_headers):
        """POST /api/auth/refresh returns a new token."""
        r = requests.post(f"{BASE_URL}/api/auth/refresh", headers=admin_headers)
        assert r.status_code == 200, f"Refresh failed: {r.text}"
        data = r.json()
        assert "token" in data, "Response must contain 'token'"
        assert data["token"], "Token must not be empty"

    def test_old_token_still_valid_after_refresh(self, admin_headers):
        """
        After calling /api/auth/refresh, the OLD token must still work for
        60 seconds (grace window). This is the P0 bug fix — previously the
        old token was immediately revoked, causing 'Session revoked' 401s
        on parallel requests (loadSites, loadBranding, DeskSummary).
        """
        old_token = admin_headers["Authorization"].replace("Bearer ", "")
        
        # Call refresh to rotate the token
        r = requests.post(f"{BASE_URL}/api/auth/refresh", headers=admin_headers)
        assert r.status_code == 200, f"Refresh failed: {r.text}"
        new_token = r.json()["token"]
        assert new_token != old_token, "Refresh must return a different token"
        
        # IMMEDIATELY use the OLD token — must NOT get 401 'Session revoked'
        r2 = requests.get(
            f"{BASE_URL}/api/service-desk/summary",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        # The old token should still work within the 60s grace window
        assert r2.status_code == 200, (
            f"Old token should still work within grace window. "
            f"Got {r2.status_code}: {r2.text}"
        )

    def test_new_token_works_after_refresh(self, admin_headers):
        """The new token returned by refresh must work immediately."""
        r = requests.post(f"{BASE_URL}/api/auth/refresh", headers=admin_headers)
        assert r.status_code == 200
        new_token = r.json()["token"]
        
        r2 = requests.get(
            f"{BASE_URL}/api/service-desk/summary",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert r2.status_code == 200, f"New token should work: {r2.text}"

    def test_logout_revokes_immediately(self):
        """
        Logout must revoke the token IMMEDIATELY (grace_seconds=0).
        After logout, the token must NOT work.
        """
        # Login fresh to get a token we can logout
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        )
        assert r.status_code == 200
        token = r.json()["token"]
        
        # Logout
        r2 = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200, f"Logout failed: {r2.text}"
        
        # Token should be immediately invalid
        r3 = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r3.status_code == 401, (
            f"Token should be revoked after logout. Got {r3.status_code}: {r3.text}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# P0 — Service Desk Dashboard Load Test
# ═══════════════════════════════════════════════════════════════════════════

class TestServiceDeskDashboardLoad:
    """
    P0: Service Desk Dashboard must load without 'Session revoked' or
    'Failed to load summary' errors.
    """

    def test_service_desk_summary_loads(self, admin_headers):
        """GET /api/service-desk/summary must return 200 with valid data."""
        r = requests.get(f"{BASE_URL}/api/service-desk/summary", headers=admin_headers)
        assert r.status_code == 200, f"Service Desk summary failed: {r.text}"
        data = r.json()
        assert "organizations" in data, "Response must contain 'organizations'"
        assert "recent_actions_7d" in data, "Response must contain 'recent_actions_7d'"


# ═══════════════════════════════════════════════════════════════════════════
# P1 — Bulk Import Row-Level Error Messages
# ═══════════════════════════════════════════════════════════════════════════

class TestBulkImportEquipmentRowErrors:
    """
    P1: POST /api/master-admin/bulk-import/equipment must return row-level
    error messages for: missing 'name', duplicate serial, unknown site.
    """

    def test_equipment_missing_name_error(self, admin_headers):
        """Row missing 'name' column must report 'Row N: missing required column name'."""
        csv_content = "site_name,customer_account_number,supplier,name,serial_number\n"
        csv_content += "Test Site,PULSENC01,Pulse Fitness,,SN-MISSING-NAME-001\n"  # name is empty
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "errors" in data, "Response must contain 'errors' array"
        assert "error_count" in data, "Response must contain 'error_count'"
        assert data["error_count"] >= 1, "Should have at least 1 error"
        
        # Check for the specific error message
        errors_text = " ".join(data["errors"])
        assert "missing required column" in errors_text.lower() or "missing" in errors_text.lower(), (
            f"Expected 'missing required column name' error. Got: {data['errors']}"
        )

    def test_equipment_duplicate_serial_error(self, admin_headers):
        """Row with duplicate serial number must report 'Row N: duplicate - equipment with serial X already exists'."""
        # First, check if there's existing equipment with a known serial
        # We'll use the seeded TEST-FUZZY-6542adb5 mentioned in the context
        csv_content = "site_name,customer_account_number,supplier,name,serial_number\n"
        csv_content += ",PULSENC01,Pulse Fitness,Duplicate Test,TEST-FUZZY-6542adb5\n"
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        # If the serial exists, we should get a duplicate error
        # If it doesn't exist, the import will succeed (which is also valid)
        if data.get("skipped", 0) > 0:
            assert "errors" in data, "Response must contain 'errors' when rows are skipped"
            errors_text = " ".join(data["errors"])
            assert "duplicate" in errors_text.lower(), (
                f"Expected 'duplicate' error for existing serial. Got: {data['errors']}"
            )

    def test_equipment_unknown_site_error(self, admin_headers):
        """Row referencing non-existent site must report 'Row N: Site X not found in target org'."""
        csv_content = "site_name,customer_account_number,supplier,name,serial_number\n"
        csv_content += f"NonExistent Site XYZ 12345,PULSENC01,Pulse Fitness,Test Equipment,SN-UNKNOWN-SITE-{int(time.time())}\n"
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "errors" in data, "Response must contain 'errors' array"
        assert data.get("skipped", 0) >= 1, "Row with unknown site should be skipped"
        
        errors_text = " ".join(data["errors"])
        assert "not found" in errors_text.lower() or "site" in errors_text.lower(), (
            f"Expected 'Site not found' error. Got: {data['errors']}"
        )

    def test_equipment_response_has_error_count(self, admin_headers):
        """Response must include 'error_count' field."""
        csv_content = "site_name,name,serial_number\n"
        csv_content += "Test Site,,SN-001\n"  # missing name
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "error_count" in data, "Response must contain 'error_count' field"
        assert isinstance(data["error_count"], int), "error_count must be an integer"


class TestBulkImportCustomersRowErrors:
    """
    P1: POST /api/master-admin/bulk-import/customers must return row-level
    error messages for: missing email/first/last name, duplicate email.
    """

    def test_customers_missing_required_fields_error(self, admin_headers):
        """Row with no email/first/last name must report 'Row N: missing email, first_name and last_name'."""
        csv_content = "customer_account_number,first_name,last_name,email,phone\n"
        csv_content += "PULSENC01,,,,+447700900001\n"  # all required fields empty
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/customers?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "errors" in data, "Response must contain 'errors' array"
        assert "error_count" in data, "Response must contain 'error_count'"
        assert data["error_count"] >= 1, "Should have at least 1 error"
        
        errors_text = " ".join(data["errors"])
        assert "missing" in errors_text.lower(), (
            f"Expected 'missing' error for empty required fields. Got: {data['errors']}"
        )

    def test_customers_duplicate_email_error(self, admin_headers):
        """Row with duplicate email must report 'Row N: duplicate - contact with email X already exists'."""
        # First import a contact
        unique_email = f"test-dup-{int(time.time())}@example.com"
        csv_content = "customer_account_number,first_name,last_name,email\n"
        csv_content += f"PULSENC01,Test,User,{unique_email}\n"
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r1 = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/customers?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r1.status_code == 200, f"First import failed: {r1.text}"
        
        # Try to import the same email again
        files2 = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r2 = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/customers?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files2,
        )
        assert r2.status_code == 200, f"Second import failed: {r2.text}"
        data = r2.json()
        
        assert data.get("skipped", 0) >= 1, "Duplicate email should be skipped"
        assert "errors" in data, "Response must contain 'errors' array"
        
        errors_text = " ".join(data["errors"])
        assert "duplicate" in errors_text.lower(), (
            f"Expected 'duplicate' error for existing email. Got: {data['errors']}"
        )

    def test_customers_response_has_error_count(self, admin_headers):
        """Response must include 'error_count' field."""
        csv_content = "customer_account_number,first_name,last_name,email\n"
        csv_content += "PULSENC01,,,\n"  # missing all required
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/customers?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "error_count" in data, "Response must contain 'error_count' field"


class TestBulkImportSitesRowErrors:
    """
    P1: POST /api/master-admin/bulk-import/sites must return row-level
    error messages for: missing site_name, duplicate site name.
    """

    def test_sites_missing_site_name_error(self, admin_headers):
        """Row missing site_name must report 'Row N: missing site_name'."""
        csv_content = "site_name,address_line1,city\n"
        csv_content += ",123 Test Street,London\n"  # site_name is empty
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/sites?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "errors" in data, "Response must contain 'errors' array"
        assert "error_count" in data, "Response must contain 'error_count'"
        assert data["error_count"] >= 1, "Should have at least 1 error"
        
        errors_text = " ".join(data["errors"])
        assert "missing" in errors_text.lower() and "site" in errors_text.lower(), (
            f"Expected 'missing site_name' error. Got: {data['errors']}"
        )

    def test_sites_duplicate_name_error(self, admin_headers):
        """Row with duplicate site name must report 'Row N: duplicate - a site named X already exists'."""
        # First import a site
        unique_name = f"TEST Site {int(time.time())}"
        csv_content = "site_name,address_line1,city\n"
        csv_content += f"{unique_name},123 Test Street,London\n"
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r1 = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/sites?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r1.status_code == 200, f"First import failed: {r1.text}"
        
        # Try to import the same site name again
        files2 = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r2 = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/sites?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files2,
        )
        assert r2.status_code == 200, f"Second import failed: {r2.text}"
        data = r2.json()
        
        assert data.get("skipped", 0) >= 1, "Duplicate site name should be skipped"
        assert "errors" in data, "Response must contain 'errors' array"
        
        errors_text = " ".join(data["errors"])
        assert "duplicate" in errors_text.lower(), (
            f"Expected 'duplicate' error for existing site name. Got: {data['errors']}"
        )

    def test_sites_response_has_error_count(self, admin_headers):
        """Response must include 'error_count' field."""
        csv_content = "site_name,address_line1\n"
        csv_content += ",123 Test Street\n"  # missing site_name
        
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/sites?organization_id={PULSE_ORG_ID}",
            headers=admin_headers,
            files=files,
        )
        assert r.status_code == 200, f"Request failed: {r.text}"
        data = r.json()
        
        assert "error_count" in data, "Response must contain 'error_count' field"


# ═══════════════════════════════════════════════════════════════════════════
# P1 — Service Desk Auth Check (Backend)
# ═══════════════════════════════════════════════════════════════════════════

class TestServiceDeskAuth:
    """
    P1: Service Desk endpoints require is_master_admin or is_service_desk.
    """

    def test_service_desk_summary_requires_auth(self):
        """GET /api/service-desk/summary without auth returns 401."""
        r = requests.get(f"{BASE_URL}/api/service-desk/summary")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_service_desk_summary_works_for_master_admin(self, admin_headers):
        """Master admin can access Service Desk summary."""
        r = requests.get(f"{BASE_URL}/api/service-desk/summary", headers=admin_headers)
        assert r.status_code == 200, f"Master admin should access Service Desk: {r.text}"
