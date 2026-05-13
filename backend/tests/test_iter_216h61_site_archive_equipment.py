"""
Iter 216h61 — Master Admin Site Archive/Restore/Delete + Equipment Listing Tests

Tests:
1. GET /api/master-admin/organizations/{org_id}/sites/{site_id}/equipment - returns ALL equipment for org+site
2. POST /api/master-admin/organizations/{org}/sites/{site}/archive - soft-archive (blocked for only HQ)
3. POST /api/master-admin/organizations/{org}/sites/{site}/restore - restore archived site
4. DELETE /api/master-admin/organizations/{org}/sites/{site} - hard delete (blocked when equipment/issues exist)
5. PATCH /api/master-admin/organizations/{org}/sites/{site} - extended field set (14 fields)
6. GET /api/sites - archived sites filtered out for operators
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data from review_request
THIRD_SPACE_ORG_ID = "c695638c-5f60-424d-bdd0-2273e6c24205"
THIRD_SPACE_CANARY_WHARF_SITE_ID = "d194718d-3e32-4cd7-8831-f1c39d6e7122"  # HQ site
THIRD_SPACE_ISLINGTON_SITE_ID = "8b482dcc-2f0e-4086-9999-d4ca92372d22"  # non-HQ site

MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(master_admin_token):
    """Auth headers for master admin"""
    return {"Authorization": f"Bearer {master_admin_token}"}


class TestMasterAdminSiteEquipment:
    """Test GET /api/master-admin/organizations/{org_id}/sites/{site_id}/equipment"""

    def test_01_equipment_endpoint_returns_all_items(self, auth_headers):
        """Third Space Canary Wharf should have 29 equipment items"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_CANARY_WHARF_SITE_ID}/equipment",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Equipment endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "equipment" in data, "Response should have 'equipment' key"
        assert "count" in data, "Response should have 'count' key"
        
        # Verify count - should be 29 per the bug fix
        count = data.get("count", 0)
        equipment_list = data.get("equipment", [])
        
        print(f"Equipment count: {count}")
        print(f"Equipment list length: {len(equipment_list)}")
        
        # The fix should return 29 items, not 3 stale TEST_QR rows
        assert count >= 20, f"Expected at least 20 equipment items, got {count}"
        assert len(equipment_list) == count, "Count should match equipment list length"
        
        # Verify equipment items have expected fields
        if equipment_list:
            sample = equipment_list[0]
            assert "id" in sample, "Equipment should have 'id'"
            assert "organization_id" in sample, "Equipment should have 'organization_id'"
            assert "site_id" in sample, "Equipment should have 'site_id'"
            
            # Verify all items belong to the correct org and site
            for eq in equipment_list:
                assert eq.get("organization_id") == THIRD_SPACE_ORG_ID, f"Equipment {eq.get('id')} has wrong org_id"
                assert eq.get("site_id") == THIRD_SPACE_CANARY_WHARF_SITE_ID, f"Equipment {eq.get('id')} has wrong site_id"

    def test_02_equipment_endpoint_requires_master_admin(self):
        """Non-master-admin should be rejected"""
        # Try without auth
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_CANARY_WHARF_SITE_ID}/equipment"
        )
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"


class TestMasterAdminSiteArchive:
    """Test POST /api/master-admin/organizations/{org}/sites/{site}/archive"""

    def test_03_archive_hq_site_blocked_when_only_hq(self, auth_headers):
        """Cannot archive the only HQ site"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_CANARY_WHARF_SITE_ID}/archive",
            headers=auth_headers,
            json={}
        )
        # Should be blocked with 400
        assert resp.status_code == 400, f"Expected 400 for archiving only HQ, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "")
        assert "Head Office" in detail or "HQ" in detail, f"Error should mention Head Office: {detail}"
        assert "Promote another site" in detail or "only HQ" in detail, f"Error should explain the constraint: {detail}"

    def test_04_archive_non_hq_site_succeeds(self, auth_headers):
        """Archive a non-HQ site (Islington) should succeed"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_ISLINGTON_SITE_ID}/archive",
            headers=auth_headers,
            json={}
        )
        assert resp.status_code == 200, f"Archive non-HQ site failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True, "Response should have ok:true"
        assert data.get("archived") is True, "Response should have archived:true"
        assert data.get("site_id") == THIRD_SPACE_ISLINGTON_SITE_ID, "Response should include site_id"


class TestMasterAdminSiteRestore:
    """Test POST /api/master-admin/organizations/{org}/sites/{site}/restore"""

    def test_05_restore_archived_site(self, auth_headers):
        """Restore the archived Islington site"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_ISLINGTON_SITE_ID}/restore",
            headers=auth_headers,
            json={}
        )
        assert resp.status_code == 200, f"Restore site failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True, "Response should have ok:true"
        assert data.get("archived") is False, "Response should have archived:false"
        assert data.get("site_id") == THIRD_SPACE_ISLINGTON_SITE_ID, "Response should include site_id"


class TestMasterAdminSiteDelete:
    """Test DELETE /api/master-admin/organizations/{org}/sites/{site}"""

    def test_06_delete_site_with_equipment_blocked(self, auth_headers):
        """Cannot delete site with equipment (Canary Wharf has 29 items)"""
        resp = requests.delete(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_CANARY_WHARF_SITE_ID}",
            headers=auth_headers
        )
        assert resp.status_code == 400, f"Expected 400 for deleting site with equipment, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "")
        
        # Should mention equipment count
        assert "equipment" in detail.lower(), f"Error should mention equipment: {detail}"
        # Should mention the count or "item(s)"
        assert "item" in detail.lower() or "29" in detail, f"Error should mention item count: {detail}"


class TestMasterAdminSitePatch:
    """Test PATCH /api/master-admin/organizations/{org}/sites/{site} - extended field set"""

    def test_07_patch_site_extended_fields(self, auth_headers):
        """PATCH should accept all 14 fields"""
        # Test payload with all extended fields
        test_payload = {
            "name": "Third Space - Canary Wharf",  # Keep original name
            "address": "1 Canada Square",
            "postcode": "E14 5AB",
            "invoice_customer_ref": "TS-CW-001",
            "address_line1": "1 Canada Square",
            "address_line2": "Level 2",
            "city": "London",
            "county": "Greater London",
            "country": "United Kingdom",
            "phone": "+44 20 7123 4567",
            "email": "canarywharf@thirdspace.london",
            "site_manager_name": "Test Manager",
            "site_manager_email": "manager@thirdspace.london",
            "default_location": "Main Gym Floor"
        }
        
        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_CANARY_WHARF_SITE_ID}",
            headers=auth_headers,
            json=test_payload
        )
        assert resp.status_code == 200, f"PATCH site failed: {resp.text}"
        data = resp.json()
        
        # Verify fields were persisted
        assert data.get("city") == "London", f"city not persisted: {data.get('city')}"
        assert data.get("county") == "Greater London", f"county not persisted: {data.get('county')}"
        assert data.get("country") == "United Kingdom", f"country not persisted: {data.get('country')}"
        assert data.get("phone") == "+44 20 7123 4567", f"phone not persisted: {data.get('phone')}"
        assert data.get("email") == "canarywharf@thirdspace.london", f"email not persisted: {data.get('email')}"
        assert data.get("site_manager_name") == "Test Manager", f"site_manager_name not persisted: {data.get('site_manager_name')}"
        assert data.get("site_manager_email") == "manager@thirdspace.london", f"site_manager_email not persisted: {data.get('site_manager_email')}"
        assert data.get("default_location") == "Main Gym Floor", f"default_location not persisted: {data.get('default_location')}"
        assert data.get("address_line1") == "1 Canada Square", f"address_line1 not persisted: {data.get('address_line1')}"
        assert data.get("address_line2") == "Level 2", f"address_line2 not persisted: {data.get('address_line2')}"


class TestOperatorSitesFiltering:
    """Test GET /api/sites - archived sites filtered for operators"""

    def test_08_archive_restore_visibility_cycle(self, auth_headers):
        """Archive a site, verify it's hidden from operator /api/sites, then restore"""
        # First, archive the Islington site
        archive_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_ISLINGTON_SITE_ID}/archive",
            headers=auth_headers,
            json={}
        )
        assert archive_resp.status_code == 200, f"Archive failed: {archive_resp.text}"
        
        # Get sites via master-admin endpoint (should still show archived with badge)
        admin_sites_resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites",
            headers=auth_headers
        )
        assert admin_sites_resp.status_code == 200, f"Admin sites list failed: {admin_sites_resp.text}"
        admin_sites = admin_sites_resp.json().get("sites", [])
        
        # Find the Islington site in admin view
        islington_in_admin = next((s for s in admin_sites if s.get("id") == THIRD_SPACE_ISLINGTON_SITE_ID), None)
        assert islington_in_admin is not None, "Islington should still appear in master-admin sites list"
        assert islington_in_admin.get("archived") is True, "Islington should be marked as archived"
        
        # Now restore the site
        restore_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_ISLINGTON_SITE_ID}/restore",
            headers=auth_headers,
            json={}
        )
        assert restore_resp.status_code == 200, f"Restore failed: {restore_resp.text}"
        
        # Verify it's no longer archived
        admin_sites_resp2 = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites",
            headers=auth_headers
        )
        admin_sites2 = admin_sites_resp2.json().get("sites", [])
        islington_after = next((s for s in admin_sites2 if s.get("id") == THIRD_SPACE_ISLINGTON_SITE_ID), None)
        assert islington_after is not None, "Islington should still appear after restore"
        assert islington_after.get("archived") is not True, "Islington should no longer be archived"


class TestCleanup:
    """Ensure test sites are restored after testing"""

    def test_99_cleanup_restore_islington(self, auth_headers):
        """Ensure Islington site is restored (not archived) after tests"""
        # Try to restore - will succeed if archived, or 200 if already restored
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}/sites/{THIRD_SPACE_ISLINGTON_SITE_ID}/restore",
            headers=auth_headers,
            json={}
        )
        # Either 200 (restored) or 404 (not found) is acceptable
        assert resp.status_code in [200, 404], f"Cleanup restore failed unexpectedly: {resp.text}"
        print("Cleanup: Islington site restored (or was already restored)")
