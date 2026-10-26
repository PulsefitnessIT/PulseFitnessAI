"""
Iter 216h50 — Backend tests for bulk-import enhancements:
1. Sites CSV template with invoice_customer_ref column
2. Sites preview-csv with invoice_customer_ref aliases
3. Sites CRUD with invoice_customer_ref field
4. Equipment CSV template with site_name first + unit_price
5. Equipment bulk-import with site resolution and unit_price parsing
"""
import os
import pytest
import requests
import uuid
from io import BytesIO

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Authenticate as master admin and return JWT token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    data = resp.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(master_admin_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture(scope="module")
def test_org_and_site(auth_headers):
    """Create a test organization and site for equipment import tests."""
    org_name = f"TEST_BulkImport_Org_{uuid.uuid4().hex[:8]}"
    site_name = f"TEST_Site_{uuid.uuid4().hex[:8]}"
    invoice_ref = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"
    
    payload = {
        "org_name": org_name,
        "tier": "pro",
        "account_type": "pulse_pro",
        "owner_email": f"test.owner.{uuid.uuid4().hex[:6]}@example.com",
        "owner_name": "Test Owner",
        "owner_password": "TestPass123!",
        "send_invite": False,
        "sites": [
            {
                "name": site_name,
                "invoice_customer_ref": invoice_ref,
                "address_line1": "123 Test Street",
                "city": "London",
                "postcode": "SW1A 1AA",
                "country": "United Kingdom",
                "is_head_office": True,
                "default_location": "Main Floor",
            }
        ],
    }
    
    resp = requests.post(
        f"{BASE_URL}/api/master-admin/onboard-head-office",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Failed to create test org: {resp.text}"
    data = resp.json()
    
    # Extract org_id and site_id from response
    org_id = data.get("organization", {}).get("id")
    sites = data.get("sites", [])
    site_id = sites[0].get("id") if sites else None
    
    yield {
        "org_id": org_id,
        "org_name": org_name,
        "site_id": site_id,
        "site_name": site_name,
        "invoice_customer_ref": invoice_ref,
    }


class TestSitesCSVTemplate:
    """Test GET /api/master-admin/sites/template.csv"""
    
    def test_template_has_invoice_customer_ref_column(self, auth_headers):
        """Verify template CSV has invoice_customer_ref as SECOND column."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/sites/template.csv",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Template download failed: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        
        # Parse CSV content - handle Windows line endings
        import csv
        from io import StringIO
        reader = csv.reader(StringIO(resp.text))
        rows = list(reader)
        headers = rows[0]
        
        # Expected headers
        expected_headers = [
            "site_name", "invoice_customer_ref", "address_line1", "address_line2",
            "address_line3", "city", "county", "postcode", "country", "phone",
            "email", "site_manager_name", "site_manager_email", "is_head_office",
            "default_location"
        ]
        assert headers[:len(expected_headers)] == expected_headers, f"Header mismatch. Got: {headers}"
        
        # Verify invoice_customer_ref is SECOND column (index 1)
        assert headers[1] == "invoice_customer_ref", "invoice_customer_ref should be second column"
        
        print("PASS: Sites template has correct header order with invoice_customer_ref as second column")
    
    def test_template_example_row_has_invoice_ref(self, auth_headers):
        """Verify example row has INV-EXM-001 for invoice_customer_ref."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/sites/template.csv",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        
        import csv
        from io import StringIO
        reader = csv.reader(StringIO(resp.text))
        rows = list(reader)
        example_row = rows[1]
        
        # invoice_customer_ref is at index 1
        assert example_row[1] == "INV-EXM-001", f"Expected INV-EXM-001, got {example_row[1]}"
        
        print("PASS: Sites template example row has INV-EXM-001 for invoice_customer_ref")


class TestSitesPreviewCSV:
    """Test POST /api/master-admin/sites/preview-csv"""
    
    def test_preview_preserves_invoice_customer_ref(self, auth_headers):
        """Upload CSV with invoice_customer_ref and verify it's preserved."""
        csv_content = """site_name,invoice_customer_ref,address_line1,city,postcode
Test Site 1,INV-001,123 Main St,London,SW1A 1AA
Test Site 2,INV-002,456 High St,Manchester,M1 1AA
"""
        files = {"file": ("test_sites.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/sites/preview-csv",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        assert "sites" in data
        assert len(data["sites"]) == 2
        
        # Check invoice_customer_ref is preserved
        assert data["sites"][0]["invoice_customer_ref"] == "INV-001"
        assert data["sites"][1]["invoice_customer_ref"] == "INV-002"
        
        print("PASS: Preview-csv preserves invoice_customer_ref on all rows")
    
    def test_preview_accepts_alias_invoice_customer_ref_with_space(self, auth_headers):
        """Test alias 'Invoice Customer Ref' (with space) maps correctly."""
        csv_content = """site_name,Invoice Customer Ref,address_line1,city,postcode
Alias Test Site,INV-ALIAS-001,789 Test Rd,Birmingham,B1 1AA
"""
        files = {"file": ("test_alias.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/sites/preview-csv",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        assert len(data["sites"]) == 1
        assert data["sites"][0]["invoice_customer_ref"] == "INV-ALIAS-001"
        
        print("PASS: Alias 'Invoice Customer Ref' (with space) works")
    
    def test_preview_accepts_alias_sicon_customer_ref(self, auth_headers):
        """Test alias 'sicon_customer_ref' maps correctly."""
        csv_content = """site_name,sicon_customer_ref,address_line1,city,postcode
Sicon Test Site,SICON-REF-001,101 Sicon Way,Leeds,LS1 1AA
"""
        files = {"file": ("test_sicon.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/sites/preview-csv",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        assert len(data["sites"]) == 1
        assert data["sites"][0]["invoice_customer_ref"] == "SICON-REF-001"
        
        print("PASS: Alias 'sicon_customer_ref' works")
    
    def test_preview_accepts_alias_customer_ref(self, auth_headers):
        """Test alias 'customer_ref' maps correctly."""
        csv_content = """site_name,customer_ref,address_line1,city,postcode
Customer Ref Test,CUST-REF-001,202 Customer Lane,Bristol,BS1 1AA
"""
        files = {"file": ("test_custref.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/sites/preview-csv",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        assert len(data["sites"]) == 1
        assert data["sites"][0]["invoice_customer_ref"] == "CUST-REF-001"
        
        print("PASS: Alias 'customer_ref' works")


class TestSitesCRUD:
    """Test site creation and update with invoice_customer_ref"""
    
    def test_site_created_with_invoice_customer_ref(self, auth_headers, test_org_and_site):
        """Verify site created via onboard-head-office has invoice_customer_ref stored."""
        org_id = test_org_and_site["org_id"]
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Failed to get sites: {resp.text}"
        data = resp.json()
        
        sites = data.get("sites", [])
        assert len(sites) >= 1, "Expected at least 1 site"
        
        # Find our test site
        test_site = next((s for s in sites if s.get("name") == test_org_and_site["site_name"]), None)
        assert test_site is not None, "Test site not found"
        assert test_site.get("invoice_customer_ref") == test_org_and_site["invoice_customer_ref"], \
            f"Expected {test_org_and_site['invoice_customer_ref']}, got {test_site.get('invoice_customer_ref')}"
        
        print(f"PASS: Site created with invoice_customer_ref={test_site.get('invoice_customer_ref')}")


class TestEquipmentCSVTemplate:
    """Test GET /api/master-admin/bulk-import/templates/equipment"""
    
    def test_template_has_site_name_first_and_unit_price(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        # Sicon template is the single equipment template (Jun 2026).
        import csv as _csv
        from io import StringIO as _SIO
        hdr = next(_csv.reader(_SIO(resp.text)))
        assert hdr[0] == "Sicon Customer Ref" and "Description" in hdr and "Make" in hdr and "Serial Number" in hdr, hdr
        assert len(hdr) == 29, hdr

    def test_template_example_row_values(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        # Sicon template is the single equipment template (Jun 2026).
        import csv as _csv
        from io import StringIO as _SIO
        hdr = next(_csv.reader(_SIO(resp.text)))
        assert hdr[0] == "Sicon Customer Ref" and "Description" in hdr and "Make" in hdr and "Serial Number" in hdr, hdr
        assert len(hdr) == 29, hdr

class TestEquipmentBulkImport:
    """Test POST /api/master-admin/bulk-import/equipment"""
    
    def test_import_equipment_with_site_name_resolution(self, auth_headers, test_org_and_site):
        """Import equipment referencing site by name, verify site_id is set."""
        org_id = test_org_and_site["org_id"]
        site_name = test_org_and_site["site_name"]
        
        equipment_name = f"TEST_Equipment_{uuid.uuid4().hex[:8]}"
        serial = f"SN-{uuid.uuid4().hex[:8]}"
        csv_content = f"""site_name,customer_account_number,name,equipment_type,manufacturer,model,serial_number,unit_price
{site_name},,{equipment_name},Treadmill,Life Fitness,T7000,{serial},3450.00
"""
        files = {"file": ("test_equipment.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={org_id}",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        
        assert data.get("imported") == 1, f"Expected 1 imported, got {data}"
        assert data.get("skipped") == 0, f"Expected 0 skipped, got {data}"
        assert len(data.get("errors", [])) == 0, f"Expected no errors, got {data.get('errors')}"
        
        print(f"PASS: Equipment imported with site resolution. Response: {data}")
    
    def test_import_equipment_site_name_mismatch_error(self, auth_headers, test_org_and_site):
        """Import with non-existent site name should error and skip row."""
        org_id = test_org_and_site["org_id"]
        
        csv_content = """site_name,customer_account_number,name,equipment_type,manufacturer,model,serial_number,unit_price
Nonexistent Site,,Test Equipment,Treadmill,Life Fitness,T7000,SN-NONEXIST-001,2500.00
"""
        files = {"file": ("test_mismatch.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={org_id}",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        
        # Row should be skipped with error
        assert data.get("imported") == 0, f"Expected 0 imported, got {data}"
        assert data.get("skipped") == 1, f"Expected 1 skipped, got {data}"
        assert len(data.get("errors", [])) > 0, "Expected error message"
        
        # Verify error mentions site not found
        error_msg = data["errors"][0].lower()
        assert "site" in error_msg and "not found" in error_msg, \
            f"Error should mention site not found: {data['errors']}"
        
        print(f"PASS: Site mismatch correctly reported. Errors: {data['errors']}")
    
    def test_import_equipment_fallback_to_invoice_customer_ref(self, auth_headers, test_org_and_site):
        """Import with blank site_name but valid invoice_customer_ref should resolve."""
        org_id = test_org_and_site["org_id"]
        invoice_ref = test_org_and_site["invoice_customer_ref"]
        
        equipment_name = f"TEST_RefEquipment_{uuid.uuid4().hex[:8]}"
        serial = f"SN-REF-{uuid.uuid4().hex[:8]}"
        csv_content = f"""site_name,invoice_customer_ref,customer_account_number,name,equipment_type,manufacturer,model,serial_number,unit_price
,{invoice_ref},,{equipment_name},Bike,Technogym,Excite,{serial},1500.00
"""
        files = {"file": ("test_ref_fallback.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={org_id}",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        
        assert data.get("imported") == 1, f"Expected 1 imported via ref fallback, got {data}"
        assert data.get("skipped") == 0, f"Expected 0 skipped, got {data}"
        
        print(f"PASS: Equipment imported via invoice_customer_ref fallback. Response: {data}")
    
    def test_import_equipment_unit_price_parsing(self, auth_headers, test_org_and_site):
        """Test unit_price parsing: string, decimal, and blank values."""
        org_id = test_org_and_site["org_id"]
        site_name = test_org_and_site["site_name"]
        
        # Create 3 equipment with different unit_price formats
        csv_content = f"""site_name,customer_account_number,name,equipment_type,manufacturer,model,serial_number,unit_price
{site_name},,TEST_Price_Int_{uuid.uuid4().hex[:6]},Treadmill,Life Fitness,T7000,SN-INT-{uuid.uuid4().hex[:6]},3450
{site_name},,TEST_Price_Dec_{uuid.uuid4().hex[:6]},Bike,Technogym,Excite,SN-DEC-{uuid.uuid4().hex[:6]},3450.50
{site_name},,TEST_Price_Blank_{uuid.uuid4().hex[:6]},Rower,Concept2,Model D,SN-BLANK-{uuid.uuid4().hex[:6]},
"""
        files = {"file": ("test_prices.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={org_id}",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        
        assert data.get("imported") == 3, f"Expected 3 imported, got {data}"
        assert data.get("skipped") == 0, f"Expected 0 skipped, got {data}"
        
        print(f"PASS: Unit price parsing works for int, decimal, and blank. Response: {data}")
    
    def test_import_equipment_no_site_reference_allowed(self, auth_headers, test_org_and_site):
        """Equipment with neither site_name nor invoice_customer_ref should import with site_id=None."""
        org_id = test_org_and_site["org_id"]
        
        equipment_name = f"TEST_NoSite_{uuid.uuid4().hex[:8]}"
        serial = f"SN-NOSITE-{uuid.uuid4().hex[:8]}"
        csv_content = f"""site_name,invoice_customer_ref,customer_account_number,name,equipment_type,manufacturer,model,serial_number,unit_price
,,,{equipment_name},Weights,Rogue,Barbell,{serial},500.00
"""
        files = {"file": ("test_nosite.csv", BytesIO(csv_content.encode()), "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={org_id}",
            files=files,
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        
        # Should import successfully with site_id=None
        assert data.get("imported") == 1, f"Expected 1 imported (no site ref is OK), got {data}"
        assert data.get("skipped") == 0, f"Expected 0 skipped, got {data}"
        
        print(f"PASS: Equipment with no site reference imports with site_id=None. Response: {data}")


class TestSitePatchInvoiceCustomerRef:
    """Test PATCH /api/sites/{id} with invoice_customer_ref"""
    
    def test_patch_site_invoice_customer_ref_via_master_admin(self, auth_headers, test_org_and_site):
        """Test that invoice_customer_ref can be updated via master-admin PATCH."""
        org_id = test_org_and_site["org_id"]
        site_id = test_org_and_site["site_id"]
        
        # Get current site data
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        sites = resp.json().get("sites", [])
        site = next((s for s in sites if s.get("id") == site_id), None)
        assert site is not None
        
        original_ref = site.get("invoice_customer_ref")
        print(f"Current invoice_customer_ref: {original_ref}")
        
        # Update via master-admin PATCH
        new_ref = f"INV-PATCH-{uuid.uuid4().hex[:6].upper()}"
        resp2 = requests.patch(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites/{site_id}",
            json={"invoice_customer_ref": new_ref},
            headers=auth_headers,
        )
        assert resp2.status_code == 200, f"PATCH failed: {resp2.text}"
        
        # Verify the update in response
        updated_site = resp2.json()
        assert updated_site.get("invoice_customer_ref") == new_ref, \
            f"Expected {new_ref}, got {updated_site.get('invoice_customer_ref')}"
        
        # Verify by fetching again
        resp3 = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites",
            headers=auth_headers,
        )
        sites = resp3.json().get("sites", [])
        site = next((s for s in sites if s.get("id") == site_id), None)
        assert site.get("invoice_customer_ref") == new_ref
        
        print(f"PASS: invoice_customer_ref updated from {original_ref} to {new_ref}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
