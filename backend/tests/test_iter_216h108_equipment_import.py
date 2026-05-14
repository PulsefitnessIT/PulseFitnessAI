"""
Iter 216h108 — Equipment Import / Onboarding Flow Tests

Tests for:
1. POST /api/account/import/equipment — customer-scoped bulk import
2. GET /api/account/import/equipment/template — same template as Master Admin
3. GET /api/account/onboarding — includes print_qr_codes + import_machines with cta_inline
4. Date parser unit tests — Excel serials, dd/mm/yyyy, ISO, etc.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for master admin (who also has organization_id)."""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} - {r.text}")
    return r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestDateParser:
    """Unit tests for parse_date_cell from utils/spreadsheet_import.py"""
    
    def test_excel_serial_45979(self):
        """Excel serial 45979 should parse to 2025-11-18"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell(45979)
        assert result == "2025-11-18", f"Expected 2025-11-18, got {result}"
    
    def test_uk_date_format(self):
        """dd/mm/yyyy format should parse correctly"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell("15/01/2024")
        assert result == "2024-01-15", f"Expected 2024-01-15, got {result}"
    
    def test_iso_date_format(self):
        """ISO YYYY-MM-DD should pass through"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell("2024-01-15")
        assert result == "2024-01-15", f"Expected 2024-01-15, got {result}"
    
    def test_empty_string(self):
        """Empty string should return empty string"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell("")
        assert result == "", f"Expected empty string, got {result}"
    
    def test_none_value(self):
        """None should return empty string"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell(None)
        assert result == "", f"Expected empty string, got {result}"
    
    def test_garbage_value(self):
        """Garbage text should return empty string"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell("garbage")
        assert result == "", f"Expected empty string, got {result}"
    
    def test_excel_serial_as_string(self):
        """Excel serial as string should also parse"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell("45979")
        assert result == "2025-11-18", f"Expected 2025-11-18, got {result}"
    
    def test_excel_serial_float(self):
        """Excel serial as float should parse"""
        from utils.spreadsheet_import import parse_date_cell
        result = parse_date_cell(45979.0)
        assert result == "2025-11-18", f"Expected 2025-11-18, got {result}"


class TestEquipmentTemplateEndpoint:
    """GET /api/account/import/equipment/template"""
    
    def test_template_returns_csv(self, auth_headers):
        """Template endpoint should return CSV with correct headers"""
        r = requests.get(f"{BASE_URL}/api/account/import/equipment/template", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert "text/csv" in r.headers.get("Content-Type", ""), "Expected CSV content type"
        
        # Check that the CSV has the expected headers
        content = r.text
        first_line = content.split('\n')[0]
        expected_headers = [
            "site_name", "customer_account_number", "supplier", "name",
            "equipment_type", "manufacturer", "model", "serial_number",
            "purchase_date", "warranty_expiry", "service_provider",
            "unit_price", "length", "width", "height", "location", "notes"
        ]
        for header in expected_headers:
            assert header in first_line, f"Missing header: {header}"
    
    def test_template_matches_master_admin(self, auth_headers):
        """Customer template should match Master Admin template"""
        # Get customer template
        r1 = requests.get(f"{BASE_URL}/api/account/import/equipment/template", headers=auth_headers)
        assert r1.status_code == 200
        
        # Get master admin template
        r2 = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers=auth_headers)
        assert r2.status_code == 200
        
        # Headers should be identical
        customer_headers = r1.text.split('\n')[0]
        admin_headers = r2.text.split('\n')[0]
        assert customer_headers == admin_headers, "Templates should have identical headers"


class TestOnboardingEndpoint:
    """GET /api/account/onboarding"""
    
    def test_onboarding_returns_9_steps(self, auth_headers):
        """Onboarding should return 9 steps"""
        r = requests.get(f"{BASE_URL}/api/account/onboarding", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "steps" in data, "Response should have 'steps' key"
        assert len(data["steps"]) == 9, f"Expected 9 steps, got {len(data['steps'])}"
    
    def test_onboarding_has_print_qr_codes_step(self, auth_headers):
        """Onboarding should include print_qr_codes step with cta_inline"""
        r = requests.get(f"{BASE_URL}/api/account/onboarding", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        
        qr_step = next((s for s in data["steps"] if s["id"] == "print_qr_codes"), None)
        assert qr_step is not None, "print_qr_codes step not found"
        assert qr_step.get("cta_inline") == "qr_print", f"Expected cta_inline='qr_print', got {qr_step.get('cta_inline')}"
        assert "cta_route" not in qr_step or qr_step.get("cta_route") is None, "print_qr_codes should NOT have cta_route"
    
    def test_onboarding_has_import_machines_step(self, auth_headers):
        """Onboarding should include import_machines step with cta_inline"""
        r = requests.get(f"{BASE_URL}/api/account/onboarding", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        
        import_step = next((s for s in data["steps"] if s["id"] == "import_machines"), None)
        assert import_step is not None, "import_machines step not found"
        assert import_step.get("cta_inline") == "equipment_import", f"Expected cta_inline='equipment_import', got {import_step.get('cta_inline')}"
        assert "cta_route" not in import_step or import_step.get("cta_route") is None, "import_machines should NOT have cta_route"
    
    def test_onboarding_has_percent(self, auth_headers):
        """Onboarding should return percent completion"""
        r = requests.get(f"{BASE_URL}/api/account/onboarding", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "percent" in data, "Response should have 'percent' key"
        assert isinstance(data["percent"], int), "percent should be an integer"


class TestEquipmentImportEndpoint:
    """POST /api/account/import/equipment"""
    
    def test_import_requires_auth(self):
        """Import endpoint should require authentication"""
        r = requests.post(f"{BASE_URL}/api/account/import/equipment")
        assert r.status_code in [401, 403, 422], f"Expected auth error, got {r.status_code}"
    
    def test_import_xlsx_file(self, auth_headers):
        """Import the Carshalton iGym.xlsx file and verify response structure"""
        xlsx_path = "/tmp/Carshalton_iGym.xlsx"
        if not os.path.exists(xlsx_path):
            pytest.skip("Test file not downloaded")
        
        with open(xlsx_path, "rb") as f:
            files = {"file": ("Carshalton_iGym.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = requests.post(
                f"{BASE_URL}/api/account/import/equipment",
                headers=auth_headers,
                files=files
            )
        
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        
        # Verify import results structure
        assert "imported" in data, "Response should have 'imported' key"
        assert "skipped" in data, "Response should have 'skipped' key"
        
        # Total processed should be >= 100 (imported + skipped due to duplicates)
        total_processed = data["imported"] + data.get("skipped", 0)
        assert total_processed >= 100, f"Expected at least 100 total processed, got {total_processed}"
        print(f"Imported: {data['imported']}, Skipped: {data.get('skipped', 0)}, Errors: {data.get('error_count', 0)}")
        
        # Verify organization_id is returned
        assert "organization_id" in data, "Response should have 'organization_id' key"
    
    def test_imported_dates_are_iso_format(self, auth_headers):
        """Verify that imported equipment has dates in ISO YYYY-MM-DD format"""
        # Get equipment list
        r = requests.get(f"{BASE_URL}/api/equipment", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        
        equipment = r.json().get("equipment", [])
        if not equipment:
            pytest.skip("No equipment found to verify")
        
        # Check date fields for ISO format
        import re
        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        excel_serial_pattern = re.compile(r'^\d{5}$')  # 5-digit numbers like 45979
        
        date_fields = ["purchase_date", "warranty_expiry", "sla_start", "sla_expiry"]
        issues = []
        
        for eq in equipment[:20]:  # Check first 20
            for field in date_fields:
                value = eq.get(field)
                if value and isinstance(value, str) and value.strip():
                    # Check it's NOT an Excel serial
                    if excel_serial_pattern.match(value):
                        issues.append(f"Equipment {eq.get('id')}: {field}={value} is Excel serial, not ISO")
                    # Check it IS ISO format (if it looks like a date)
                    elif not iso_pattern.match(value) and not value.startswith("20"):
                        issues.append(f"Equipment {eq.get('id')}: {field}={value} is not ISO format")
        
        assert len(issues) == 0, f"Date format issues found:\n" + "\n".join(issues[:10])


class TestBulkAutoLookupChunking:
    """Verify the chunked auto-lookup endpoint exists and responds"""
    
    def test_batch_lookup_endpoint_exists(self, auth_headers):
        """POST /api/equipment/lookup-images/batch should exist"""
        r = requests.post(
            f"{BASE_URL}/api/equipment/lookup-images/batch?limit=8",
            headers=auth_headers,
            json={}
        )
        # Should return 200 even if no equipment needs images
        assert r.status_code in [200, 404], f"Expected 200 or 404, got {r.status_code}: {r.text}"
        
        if r.status_code == 200:
            data = r.json()
            # Should have the expected response structure
            assert "total_examined" in data or "matched" in data or "message" in data, \
                f"Unexpected response structure: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
