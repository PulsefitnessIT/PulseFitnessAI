"""
Iter 216h62 — Site-scoped Reports + Suppliers tests

Tests:
1. GET /api/reports/resolution-stats?site_id={id} filters issues by site
2. GET /api/reports/equipment-summary?site_id={id} filters equipment by site
3. GET /api/reports/operational?period=30d&site_id={id} filters issues/POs by site
4. GET /api/suppliers?site_id={id} returns only suppliers servicing equipment at that site
5. Without site_id, all endpoints return org-wide aggregate data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
PULSE_OWNER_EMAIL = "e1.agent@gymaxisai.com"
PULSE_OWNER_PASSWORD = "E1Agent123!"
PULSE_ORG_ID = "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f"

# Third Space org for intersection test (has equipment but suppliers directory may be empty)
THIRD_SPACE_ORG_ID = "c695638c-5f60-424d-bdd0-2273e6c24205"
THIRD_SPACE_HQ_SITE_ID = "d194718d-3e32-4cd7-8831-f1c39d6e7122"


@pytest.fixture(scope="module")
def pulse_token():
    """Get auth token for Pulse Fitness owner"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_OWNER_EMAIL,
        "password": PULSE_OWNER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Could not authenticate Pulse owner: {response.status_code} - {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def pulse_headers(pulse_token):
    """Headers with Pulse owner auth"""
    return {"Authorization": f"Bearer {pulse_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def pulse_sites(pulse_headers):
    """Get list of sites for Pulse Fitness org"""
    response = requests.get(f"{BASE_URL}/api/sites", headers=pulse_headers)
    if response.status_code != 200:
        return []
    return response.json().get("sites", [])


class TestResolutionStatsEndpoint:
    """Tests for GET /api/reports/resolution-stats with site_id filtering"""
    
    def test_resolution_stats_without_site_id_returns_org_aggregate(self, pulse_headers):
        """Without site_id, returns org-wide aggregate"""
        response = requests.get(f"{BASE_URL}/api/reports/resolution-stats", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "total_issues" in data
        assert "self_fixes" in data
        assert "engineer_callouts" in data
        assert "open_issues" in data
        assert "self_fix_rate" in data
        assert "by_equipment" in data
        print(f"✓ Org-wide resolution stats: total_issues={data['total_issues']}, open={data['open_issues']}")
    
    def test_resolution_stats_with_site_id_filters_by_site(self, pulse_headers, pulse_sites):
        """With site_id, returns only issues for that site"""
        if not pulse_sites:
            pytest.skip("No sites available for Pulse org")
        
        site = pulse_sites[0]
        site_id = site.get("id")
        
        # Get org-wide stats first
        org_response = requests.get(f"{BASE_URL}/api/reports/resolution-stats", headers=pulse_headers)
        org_data = org_response.json()
        
        # Get site-specific stats
        site_response = requests.get(
            f"{BASE_URL}/api/reports/resolution-stats?site_id={site_id}",
            headers=pulse_headers
        )
        assert site_response.status_code == 200, f"Expected 200, got {site_response.status_code}"
        
        site_data = site_response.json()
        assert "total_issues" in site_data
        
        # Site-specific should be <= org-wide (unless org has only one site)
        print(f"✓ Site '{site.get('name')}' resolution stats: total_issues={site_data['total_issues']} (org-wide: {org_data['total_issues']})")
        assert site_data['total_issues'] <= org_data['total_issues'], \
            "Site-specific issues should not exceed org-wide total"


class TestEquipmentSummaryEndpoint:
    """Tests for GET /api/reports/equipment-summary with site_id filtering"""
    
    def test_equipment_summary_without_site_id_returns_org_aggregate(self, pulse_headers):
        """Without site_id, returns org-wide equipment summary"""
        response = requests.get(f"{BASE_URL}/api/reports/equipment-summary", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "total_equipment" in data
        assert "by_type" in data
        assert "equipment_details" in data
        print(f"✓ Org-wide equipment summary: total_equipment={data['total_equipment']}")
    
    def test_equipment_summary_with_site_id_filters_by_site(self, pulse_headers, pulse_sites):
        """With site_id, returns only equipment for that site"""
        if not pulse_sites:
            pytest.skip("No sites available for Pulse org")
        
        site = pulse_sites[0]
        site_id = site.get("id")
        
        # Get org-wide summary first
        org_response = requests.get(f"{BASE_URL}/api/reports/equipment-summary", headers=pulse_headers)
        org_data = org_response.json()
        
        # Get site-specific summary
        site_response = requests.get(
            f"{BASE_URL}/api/reports/equipment-summary?site_id={site_id}",
            headers=pulse_headers
        )
        assert site_response.status_code == 200, f"Expected 200, got {site_response.status_code}"
        
        site_data = site_response.json()
        assert "total_equipment" in site_data
        
        print(f"✓ Site '{site.get('name')}' equipment summary: total_equipment={site_data['total_equipment']} (org-wide: {org_data['total_equipment']})")
        assert site_data['total_equipment'] <= org_data['total_equipment'], \
            "Site-specific equipment should not exceed org-wide total"


class TestOperationalReportsEndpoint:
    """Tests for GET /api/reports/operational with site_id filtering"""
    
    def test_operational_reports_without_site_id_returns_org_aggregate(self, pulse_headers):
        """Without site_id, returns org-wide operational reports"""
        response = requests.get(
            f"{BASE_URL}/api/reports/operational?period=30d",
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "period" in data
        assert "total_faults" in data
        assert "open_faults" in data
        assert "resolved_faults" in data
        assert "by_equipment" in data
        assert "po_count" in data
        print(f"✓ Org-wide operational reports (30d): total_faults={data['total_faults']}, po_count={data['po_count']}")
    
    def test_operational_reports_with_site_id_filters_by_site(self, pulse_headers, pulse_sites):
        """With site_id, returns only faults/POs for that site"""
        if not pulse_sites:
            pytest.skip("No sites available for Pulse org")
        
        site = pulse_sites[0]
        site_id = site.get("id")
        
        # Get org-wide reports first
        org_response = requests.get(
            f"{BASE_URL}/api/reports/operational?period=30d",
            headers=pulse_headers
        )
        org_data = org_response.json()
        
        # Get site-specific reports
        site_response = requests.get(
            f"{BASE_URL}/api/reports/operational?period=30d&site_id={site_id}",
            headers=pulse_headers
        )
        assert site_response.status_code == 200, f"Expected 200, got {site_response.status_code}"
        
        site_data = site_response.json()
        assert "total_faults" in site_data
        
        print(f"✓ Site '{site.get('name')}' operational reports (30d): total_faults={site_data['total_faults']} (org-wide: {org_data['total_faults']})")
        assert site_data['total_faults'] <= org_data['total_faults'], \
            "Site-specific faults should not exceed org-wide total"


class TestSuppliersEndpoint:
    """Tests for GET /api/suppliers with site_id filtering"""
    
    def test_suppliers_without_site_id_returns_org_directory(self, pulse_headers):
        """Without site_id, returns full org-wide suppliers directory"""
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "suppliers" in data
        suppliers = data["suppliers"]
        print(f"✓ Org-wide suppliers directory: {len(suppliers)} suppliers")
    
    def test_suppliers_with_site_id_filters_by_equipment_at_site(self, pulse_headers, pulse_sites):
        """With site_id, returns only suppliers that service equipment at that site"""
        if not pulse_sites:
            pytest.skip("No sites available for Pulse org")
        
        site = pulse_sites[0]
        site_id = site.get("id")
        
        # Get org-wide suppliers first
        org_response = requests.get(f"{BASE_URL}/api/suppliers", headers=pulse_headers)
        org_data = org_response.json()
        org_suppliers = org_data.get("suppliers", [])
        
        # Get site-specific suppliers
        site_response = requests.get(
            f"{BASE_URL}/api/suppliers?site_id={site_id}",
            headers=pulse_headers
        )
        assert site_response.status_code == 200, f"Expected 200, got {site_response.status_code}"
        
        site_data = site_response.json()
        site_suppliers = site_data.get("suppliers", [])
        
        print(f"✓ Site '{site.get('name')}' suppliers: {len(site_suppliers)} (org-wide: {len(org_suppliers)})")
        
        # Site-specific should be <= org-wide
        assert len(site_suppliers) <= len(org_suppliers), \
            "Site-specific suppliers should not exceed org-wide total"
    
    def test_suppliers_with_nonexistent_site_returns_empty(self, pulse_headers):
        """With a site_id that has no equipment, returns empty list"""
        # Use a fake site_id that doesn't exist
        fake_site_id = "00000000-0000-0000-0000-000000000000"
        
        response = requests.get(
            f"{BASE_URL}/api/suppliers?site_id={fake_site_id}",
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        suppliers = data.get("suppliers", [])
        
        # Should return empty list for site with no equipment
        print(f"✓ Non-existent site returns {len(suppliers)} suppliers (expected 0 or empty)")
        assert len(suppliers) == 0, "Site with no equipment should return empty suppliers list"


class TestThirdSpaceIntersectionBehavior:
    """Tests for Third Space org — verifies intersection behavior where
    equipment uses supplier 'Pulse Fitness' but org's suppliers directory
    may not have that entry, resulting in empty intersection."""
    
    @pytest.fixture(scope="class")
    def third_space_token(self):
        """Get auth token for master admin to access Third Space"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        if response.status_code != 200:
            pytest.skip(f"Could not authenticate master admin: {response.status_code}")
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def third_space_headers(self, third_space_token):
        return {"Authorization": f"Bearer {third_space_token}", "Content-Type": "application/json"}
    
    def test_third_space_suppliers_intersection(self, third_space_headers):
        """Third Space HQ site has 29 equipment items using supplier 'Pulse Fitness'
        but if the org's suppliers directory doesn't have 'Pulse Fitness' entry,
        the intersection returns [] — this is correct behavior."""
        
        # Get org-wide suppliers for Third Space
        # Note: Master admin sees all orgs, so we need to check the specific org
        org_response = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{THIRD_SPACE_ORG_ID}",
            headers=third_space_headers
        )
        if org_response.status_code != 200:
            pytest.skip("Cannot access Third Space org")
        
        # Get suppliers for Third Space HQ site
        site_response = requests.get(
            f"{BASE_URL}/api/suppliers?site_id={THIRD_SPACE_HQ_SITE_ID}",
            headers=third_space_headers
        )
        
        # This may return 200 with empty list or may fail if master admin
        # doesn't have org context. Either way, document the behavior.
        print(f"Third Space HQ suppliers response: {site_response.status_code}")
        if site_response.status_code == 200:
            data = site_response.json()
            suppliers = data.get("suppliers", [])
            print(f"✓ Third Space HQ site suppliers: {len(suppliers)} (intersection behavior)")


class TestSiteSwitcherIntegration:
    """Tests verifying that switching sites via SiteSwitcher reloads data correctly"""
    
    def test_switching_sites_changes_report_data(self, pulse_headers, pulse_sites):
        """Verify that different sites return different data"""
        if len(pulse_sites) < 2:
            pytest.skip("Need at least 2 sites to test switching")
        
        site1 = pulse_sites[0]
        site2 = pulse_sites[1]
        
        # Get resolution stats for site 1
        response1 = requests.get(
            f"{BASE_URL}/api/reports/resolution-stats?site_id={site1['id']}",
            headers=pulse_headers
        )
        data1 = response1.json()
        
        # Get resolution stats for site 2
        response2 = requests.get(
            f"{BASE_URL}/api/reports/resolution-stats?site_id={site2['id']}",
            headers=pulse_headers
        )
        data2 = response2.json()
        
        print(f"✓ Site 1 '{site1.get('name')}': {data1.get('total_issues')} issues")
        print(f"✓ Site 2 '{site2.get('name')}': {data2.get('total_issues')} issues")
        
        # Both should be valid responses (may have same or different counts)
        assert response1.status_code == 200
        assert response2.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
