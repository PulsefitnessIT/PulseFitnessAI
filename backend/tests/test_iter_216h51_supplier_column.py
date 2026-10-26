"""
Iter 216h51 — Supplier column in equipment bulk import + orgs limit raised to 2000.

Tests:
1. GET /api/master-admin/bulk-import/templates/equipment — supplier column present
2. POST /api/master-admin/bulk-import/equipment — supplier resolution (exact, fuzzy, no match, blank)
3. GET /api/master-admin/organizations — limit raised from 500 to 2000
4. POST /api/auth/login — canonical E1 test user (e1.agent@gymaxisai.com)
"""
import os
import io
import csv
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
E1_AGENT_EMAIL = "e1.agent@gymaxisai.com"
E1_AGENT_PASSWORD = "E1Agent123!"
PULSE_FITNESS_ORG_ID = "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    data = resp.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def e1_agent_token():
    """Get E1 agent (owner) JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": E1_AGENT_EMAIL,
        "password": E1_AGENT_PASSWORD
    })
    assert resp.status_code == 200, f"E1 agent login failed: {resp.text}"
    data = resp.json()
    return data.get("access_token") or data.get("token")


class TestCanonicalE1User:
    """Test 7: Canonical E1 test user login verification."""
    
    def test_e1_agent_login_succeeds(self):
        """POST /api/auth/login with e1.agent@gymaxisai.com succeeds."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": E1_AGENT_EMAIL,
            "password": E1_AGENT_PASSWORD
        })
        assert resp.status_code == 200, f"E1 agent login failed: {resp.text}"
        data = resp.json()
        assert "access_token" in data or "token" in data, "No token in response"
        print("✓ E1 agent login succeeded")
    
    def test_e1_agent_has_owner_role(self):
        """E1 agent user has role='owner'."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": E1_AGENT_EMAIL,
            "password": E1_AGENT_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        user = data.get("user", {})
        assert user.get("role") == "owner", f"Expected role='owner', got '{user.get('role')}'"
        print("✓ E1 agent has role='owner'")
    
    def test_e1_agent_belongs_to_pulse_fitness_org(self):
        """E1 agent belongs to Pulse Fitness org (8cd02d8c-e5a2-4c13-bdb9-8b143b85455f)."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": E1_AGENT_EMAIL,
            "password": E1_AGENT_PASSWORD
        })
        assert resp.status_code == 200
        data = resp.json()
        user = data.get("user", {})
        assert user.get("organization_id") == PULSE_FITNESS_ORG_ID, \
            f"Expected org_id='{PULSE_FITNESS_ORG_ID}', got '{user.get('organization_id')}'"
        print("✓ E1 agent belongs to Pulse Fitness org")


class TestEquipmentTemplateSupplierColumn:
    """Test 1: Equipment CSV template includes supplier column."""
    
    def test_template_has_supplier_column(self, master_admin_token):
        resp = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers={"Authorization": f"Bearer {master_admin_token}"})
        assert resp.status_code == 200, resp.text
        # Sicon template is the single equipment template (Jun 2026).
        import csv as _csv
        from io import StringIO as _SIO
        hdr = next(_csv.reader(_SIO(resp.text)))
        assert hdr[0] == "Sicon Customer Ref" and "Description" in hdr and "Make" in hdr and "Serial Number" in hdr, hdr
        assert len(hdr) == 34 and hdr[29:] == ["MOD Code", "Asset Tag", "Condition", "Equipment Type", "Manufacture Date"], hdr
        assert "Supplier Name" in hdr

    def test_template_header_order(self, master_admin_token):
        resp = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers={"Authorization": f"Bearer {master_admin_token}"})
        assert resp.status_code == 200, resp.text
        # Sicon template is the single equipment template (Jun 2026).
        import csv as _csv
        from io import StringIO as _SIO
        hdr = next(_csv.reader(_SIO(resp.text)))
        assert hdr[0] == "Sicon Customer Ref" and "Description" in hdr and "Make" in hdr and "Serial Number" in hdr, hdr
        assert len(hdr) == 34 and hdr[29:] == ["MOD Code", "Asset Tag", "Condition", "Equipment Type", "Manufacture Date"], hdr
        assert "Supplier Name" in hdr

    def test_template_example_row_supplier_value(self, master_admin_token):
        resp = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers={"Authorization": f"Bearer {master_admin_token}"})
        assert resp.status_code == 200, resp.text
        # Sicon template is the single equipment template (Jun 2026).
        import csv as _csv
        from io import StringIO as _SIO
        hdr = next(_csv.reader(_SIO(resp.text)))
        assert hdr[0] == "Sicon Customer Ref" and "Description" in hdr and "Make" in hdr and "Serial Number" in hdr, hdr
        assert len(hdr) == 34 and hdr[29:] == ["MOD Code", "Asset Tag", "Condition", "Equipment Type", "Manufacture Date"], hdr
        assert "Supplier Name" in hdr

class TestEquipmentBulkImportSupplierResolution:
    """Tests 2-5: Equipment bulk import with supplier resolution."""
    
    @pytest.fixture(scope="class")
    def seeded_supplier(self, e1_agent_token):
        """Seed a supplier in Pulse Fitness org for testing."""
        supplier_name = f"TEST_Pulse Fitness Supplier {uuid.uuid4().hex[:6]}"
        supplier_email = f"test.service.{uuid.uuid4().hex[:6]}@pulsefitness.com"
        
        resp = requests.post(
            f"{BASE_URL}/api/suppliers",
            headers={"Authorization": f"Bearer {e1_agent_token}"},
            json={
                "name": "Pulse Fitness",  # Exact name for matching
                "service_email": "service@pulsefitness.com",
                "email": "contact@pulsefitness.com",
                "phone": "+44 1onal 234567"
            }
        )
        
        if resp.status_code == 201:
            data = resp.json()
            supplier_id = data.get("id")
            print(f"✓ Seeded supplier: id={supplier_id}, name='Pulse Fitness', service_email='service@pulsefitness.com'")
            yield {
                "id": supplier_id,
                "name": "Pulse Fitness",
                "service_email": "service@pulsefitness.com"
            }
            # Cleanup
            requests.delete(
                f"{BASE_URL}/api/suppliers/{supplier_id}",
                headers={"Authorization": f"Bearer {e1_agent_token}"}
            )
        else:
            # Supplier might already exist - try to find it
            resp = requests.get(
                f"{BASE_URL}/api/suppliers",
                headers={"Authorization": f"Bearer {e1_agent_token}"}
            )
            if resp.status_code == 200:
                suppliers = resp.json().get("suppliers", [])
                for s in suppliers:
                    if s.get("name") == "Pulse Fitness":
                        print(f"✓ Found existing supplier: id={s.get('id')}, name='Pulse Fitness'")
                        yield {
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "service_email": s.get("service_email")
                        }
                        return
            # Create with unique name if exact match exists
            resp = requests.post(
                f"{BASE_URL}/api/suppliers",
                headers={"Authorization": f"Bearer {e1_agent_token}"},
                json={
                    "name": supplier_name,
                    "service_email": supplier_email,
                    "email": f"contact.{uuid.uuid4().hex[:6]}@pulsefitness.com"
                }
            )
            assert resp.status_code == 201, f"Failed to seed supplier: {resp.text}"
            data = resp.json()
            yield {
                "id": data.get("id"),
                "name": supplier_name,
                "service_email": supplier_email
            }
            # Cleanup
            requests.delete(
                f"{BASE_URL}/api/suppliers/{data.get('id')}",
                headers={"Authorization": f"Bearer {e1_agent_token}"}
            )
    
    def _create_equipment_csv(self, rows):
        """Create a CSV file content from rows."""
        output = io.StringIO()
        writer = csv.writer(output)
        # Headers
        writer.writerow([
            "site_name", "customer_account_number", "supplier",
            "name", "equipment_type", "manufacturer", "model", "serial_number",
            "purchase_date", "warranty_expiry", "service_provider",
            "unit_price", "length", "width", "height", "location", "notes"
        ])
        for row in rows:
            writer.writerow(row)
        return output.getvalue()
    
    def test_supplier_exact_match_resolution(self, master_admin_token, e1_agent_token):
        """Test 2: Supplier='Pulse Fitness' resolves to seeded supplier."""
        # First, ensure we have a supplier named "Pulse Fitness" in the org
        # Check existing suppliers
        resp = requests.get(
            f"{BASE_URL}/api/suppliers",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        suppliers = resp.json().get("suppliers", []) if resp.status_code == 200 else []
        pulse_supplier = next((s for s in suppliers if s.get("name") == "Pulse Fitness"), None)
        
        if not pulse_supplier:
            # Create the supplier
            resp = requests.post(
                f"{BASE_URL}/api/suppliers",
                headers={"Authorization": f"Bearer {e1_agent_token}"},
                json={
                    "name": "Pulse Fitness",
                    "service_email": "service@pulsefitness.com",
                    "email": "contact@pulsefitness.com"
                }
            )
            if resp.status_code == 201:
                pulse_supplier = resp.json()
                print(f"✓ Created supplier 'Pulse Fitness' with id={pulse_supplier.get('id')}")
            else:
                pytest.skip(f"Could not create test supplier: {resp.text}")
        
        # Create CSV with exact supplier name match
        serial = f"TEST-EXACT-{uuid.uuid4().hex[:8]}"
        csv_content = self._create_equipment_csv([
            ["", "", "Pulse Fitness",  # supplier column
             f"Test Treadmill {serial}", "Treadmill", "Life Fitness", "T7000", serial,
             "2024-01-15", "2027-01-15", "Pulse Service",
             "3450.00", "2.20", "0.95", "1.55", "Gym Floor", "Test equipment"]
        ])
        
        # Import equipment
        files = {"file": ("equipment.csv", csv_content, "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_FITNESS_ORG_ID}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            files=files
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        assert data.get("imported") >= 1, f"Expected at least 1 imported, got {data}"
        print(f"✓ Equipment imported: {data}")
        
        # Verify the equipment doc has supplier_id and supplier_email set
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        assert resp.status_code == 200
        equipment_list = resp.json().get("equipment", [])
        test_equip = next((e for e in equipment_list if e.get("serial_number") == serial), None)
        
        assert test_equip is not None, f"Could not find equipment with serial={serial}"
        assert test_equip.get("supplier") == "Pulse Fitness", \
            f"Expected supplier='Pulse Fitness', got '{test_equip.get('supplier')}'"
        assert test_equip.get("supplier_id") == pulse_supplier.get("id"), \
            f"Expected supplier_id='{pulse_supplier.get('id')}', got '{test_equip.get('supplier_id')}'"
        # supplier_email should be service_email or fallback to email
        expected_email = pulse_supplier.get("service_email") or pulse_supplier.get("email")
        assert test_equip.get("supplier_email") == expected_email, \
            f"Expected supplier_email='{expected_email}', got '{test_equip.get('supplier_email')}'"
        
        print(f"✓ Exact match: supplier_id={test_equip.get('supplier_id')}, supplier_email={test_equip.get('supplier_email')}")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/equipment/{test_equip.get('id')}",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
    
    def test_supplier_fuzzy_match_resolution(self, master_admin_token, e1_agent_token):
        """Test 3: Supplier='Pulse Fitness Limited' fuzzy-matches to 'Pulse Fitness'."""
        # Ensure supplier exists
        resp = requests.get(
            f"{BASE_URL}/api/suppliers",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        suppliers = resp.json().get("suppliers", []) if resp.status_code == 200 else []
        pulse_supplier = next((s for s in suppliers if s.get("name") == "Pulse Fitness"), None)
        
        if not pulse_supplier:
            resp = requests.post(
                f"{BASE_URL}/api/suppliers",
                headers={"Authorization": f"Bearer {e1_agent_token}"},
                json={
                    "name": "Pulse Fitness",
                    "service_email": "service@pulsefitness.com"
                }
            )
            if resp.status_code == 201:
                pulse_supplier = resp.json()
        
        if not pulse_supplier:
            pytest.skip("Could not find or create 'Pulse Fitness' supplier")
        
        # Create CSV with fuzzy supplier name (includes 'Limited' suffix)
        serial = f"TEST-FUZZY-{uuid.uuid4().hex[:8]}"
        csv_content = self._create_equipment_csv([
            ["", "", "Pulse Fitness Limited",  # fuzzy match - should strip 'Limited'
             f"Test Bike {serial}", "Exercise Bike", "Pulse", "PB500", serial,
             "2024-02-01", "2027-02-01", "Pulse Service",
             "2500.00", "1.50", "0.60", "1.20", "Cardio Area", "Fuzzy match test"]
        ])
        
        files = {"file": ("equipment.csv", csv_content, "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_FITNESS_ORG_ID}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            files=files
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        assert data.get("imported") >= 1, f"Expected at least 1 imported, got {data}"
        
        # Verify fuzzy match worked
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        equipment_list = resp.json().get("equipment", [])
        test_equip = next((e for e in equipment_list if e.get("serial_number") == serial), None)
        
        assert test_equip is not None, f"Could not find equipment with serial={serial}"
        # Fuzzy match should resolve to the seeded supplier
        assert test_equip.get("supplier_id") == pulse_supplier.get("id"), \
            f"Fuzzy match failed: expected supplier_id='{pulse_supplier.get('id')}', got '{test_equip.get('supplier_id')}'"
        # supplier_email should be service_email or fallback to email
        expected_email = pulse_supplier.get("service_email") or pulse_supplier.get("email")
        assert test_equip.get("supplier_email") == expected_email, \
            f"Expected supplier_email='{expected_email}', got '{test_equip.get('supplier_email')}'"
        
        print(f"✓ Fuzzy match 'Pulse Fitness Limited' -> supplier_id={test_equip.get('supplier_id')}")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/equipment/{test_equip.get('id')}",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
    
    def test_supplier_no_match(self, master_admin_token, e1_agent_token):
        """Test 4: Supplier='Some Unknown Supplier' - row inserts but supplier_id=None."""
        serial = f"TEST-NOMATCH-{uuid.uuid4().hex[:8]}"
        csv_content = self._create_equipment_csv([
            ["", "", "Some Unknown Supplier",  # no match expected
             f"Test Rower {serial}", "Rowing Machine", "Concept2", "Model D", serial,
             "2024-03-01", "2027-03-01", "Unknown Service",
             "1200.00", "2.40", "0.60", "0.90", "Cardio Area", "No match test"]
        ])
        
        files = {"file": ("equipment.csv", csv_content, "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_FITNESS_ORG_ID}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            files=files
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        assert data.get("imported") >= 1, f"Row should still import even with no supplier match: {data}"
        
        # Verify equipment was inserted with supplier string but no supplier_id
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        equipment_list = resp.json().get("equipment", [])
        test_equip = next((e for e in equipment_list if e.get("serial_number") == serial), None)
        
        assert test_equip is not None, f"Could not find equipment with serial={serial}"
        assert test_equip.get("supplier") == "Some Unknown Supplier", \
            f"Expected supplier='Some Unknown Supplier', got '{test_equip.get('supplier')}'"
        assert test_equip.get("supplier_id") is None, \
            f"Expected supplier_id=None for unmatched supplier, got '{test_equip.get('supplier_id')}'"
        assert test_equip.get("supplier_email") is None, \
            f"Expected supplier_email=None for unmatched supplier, got '{test_equip.get('supplier_email')}'"
        
        print("✓ No match: supplier='Some Unknown Supplier', supplier_id=None, supplier_email=None")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/equipment/{test_equip.get('id')}",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
    
    def test_supplier_blank_falls_back_to_manufacturer(self, master_admin_token, e1_agent_token):
        """Test 5: Blank supplier column falls back to manufacturer (existing behaviour)."""
        serial = f"TEST-BLANK-{uuid.uuid4().hex[:8]}"
        csv_content = self._create_equipment_csv([
            ["", "", "",  # blank supplier - should fall back to manufacturer
             f"Test Elliptical {serial}", "Elliptical", "Life Fitness", "E5", serial,
             "2024-04-01", "2027-04-01", "Life Fitness Service",
             "4500.00", "2.00", "0.80", "1.70", "Cardio Area", "Blank supplier test"]
        ])
        
        files = {"file": ("equipment.csv", csv_content, "text/csv")}
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/bulk-import/equipment?organization_id={PULSE_FITNESS_ORG_ID}",
            headers={"Authorization": f"Bearer {master_admin_token}"},
            files=files
        )
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        assert data.get("imported") >= 1, f"Expected at least 1 imported: {data}"
        
        # Verify equipment - supplier should be manufacturer value, but no supplier_id
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )
        equipment_list = resp.json().get("equipment", [])
        test_equip = next((e for e in equipment_list if e.get("serial_number") == serial), None)
        
        assert test_equip is not None, f"Could not find equipment with serial={serial}"
        # Blank supplier falls back to manufacturer for the supplier field
        assert test_equip.get("supplier") == "Life Fitness", \
            f"Expected supplier='Life Fitness' (from manufacturer), got '{test_equip.get('supplier')}'"
        # But supplier_id/email should be None since 'Life Fitness' isn't in suppliers collection
        assert test_equip.get("supplier_id") is None, \
            f"Expected supplier_id=None, got '{test_equip.get('supplier_id')}'"
        assert test_equip.get("supplier_email") is None, \
            f"Expected supplier_email=None, got '{test_equip.get('supplier_email')}'"
        
        print("✓ Blank supplier: falls back to manufacturer='Life Fitness', supplier_id=None")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/equipment/{test_equip.get('id')}",
            headers={"Authorization": f"Bearer {e1_agent_token}"}
        )


class TestOrganizationsEndpointLimit:
    """Test 6: GET /api/master-admin/organizations limit raised to 2000."""
    
    def test_organizations_endpoint_works(self, master_admin_token):
        """GET /api/master-admin/organizations returns org list (5-6 orgs after purge)."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Organizations fetch failed: {resp.text}"
        data = resp.json()
        
        orgs = data.get("organizations", [])
        assert len(orgs) >= 1, "Expected at least 1 organization"
        print(f"✓ Organizations endpoint returned {len(orgs)} orgs")
        
        # Verify structure - should have enrichment fields
        first_org = orgs[0]
        assert "id" in first_org, "Org missing 'id' field"
        assert "name" in first_org, "Org missing 'name' field"
        assert "user_count" in first_org, "Org missing 'user_count' enrichment"
        assert "owner_email" in first_org, "Org missing 'owner_email' enrichment"
        
        print("✓ Org structure verified: id, name, user_count, owner_email present")
    
    def test_organizations_no_truncation(self, master_admin_token):
        """Verify orgs aren't silently truncated (should be 5-6 after purge)."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        orgs = data.get("organizations", [])
        # After purge, should have 5-6 orgs per test_credentials.md
        # The limit is now 2000, so we shouldn't see truncation
        print(f"✓ Returned {len(orgs)} organizations (limit is 2000, no truncation)")
        
        # List org names for verification
        org_names = [o.get("name", "?") for o in orgs]
        print(f"  Orgs: {org_names}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
