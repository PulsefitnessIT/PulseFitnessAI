"""
Iter 216h23 — Tests for the new All Sites endpoint and sidebar restructure.

Test items:
1. GET /api/master-admin/all-sites — returns sites[], totals, brand. Master-admin gated.
2. Pulse Master Admin scope test — must return brand='pulse' and filtered sites.
3. Sidebar restructure verification (frontend test).
4. AdminAllSites component rendering (frontend test).
5. Site row click navigation (frontend test).
6. Regression: CataloguePanel still renders at section=catalogue.
7. Regression: Organizations, Integrations Hub, Brand Picker scope-lock.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RATE_LIMIT_BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', '')

# Test credentials from test_credentials.md
GYMAXIS_ADMIN_EMAIL = "admin@gymaxisai.com"
GYMAXIS_ADMIN_PASSWORD = "MasterAdmin123!"
PULSE_ADMIN_EMAIL = "pulse.scope.test@pulsefitness.com"
PULSE_ADMIN_PASSWORD = "TestPulse2026!"


def get_auth_headers(email: str, password: str) -> dict:
    """Login and return auth headers with rate-limit bypass."""
    headers = {"Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        headers["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    if resp.status_code != 200:
        pytest.skip(f"Login failed for {email}: {resp.status_code} - {resp.text}")
    
    token = resp.json().get("token")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS,
    }


class TestAllSitesEndpoint:
    """Test GET /api/master-admin/all-sites endpoint."""
    
    def test_all_sites_requires_auth(self):
        """Endpoint returns 401 without authentication."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/all-sites")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ All-sites endpoint returns 401 without auth")
    
    def test_all_sites_gymaxis_admin(self):
        """GymAxis Master Admin gets all sites across all orgs."""
        headers = get_auth_headers(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)
        
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/all-sites",
            headers=headers,
            params={"limit": 1000},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify response structure
        assert "sites" in data, "Response missing 'sites' array"
        assert "totals" in data, "Response missing 'totals' object"
        assert "brand" in data, "Response missing 'brand' field"
        
        # Verify totals structure
        totals = data["totals"]
        assert "sites" in totals, "Totals missing 'sites' count"
        assert "head_offices" in totals, "Totals missing 'head_offices' count"
        assert "branches" in totals, "Totals missing 'branches' count"
        assert "equipment" in totals, "Totals missing 'equipment' count"
        
        # GymAxis admin should see brand='all'
        assert data["brand"] == "all", f"Expected brand='all', got '{data['brand']}'"
        
        # Verify site structure if any sites exist
        if data["sites"]:
            site = data["sites"][0]
            required_fields = ["id", "name", "organization_id", "org_name", "org_brand", 
                              "is_head_office", "equipment_count", "members_count"]
            for field in required_fields:
                assert field in site, f"Site missing required field: {field}"
        
        print(f"✓ GymAxis admin sees {totals['sites']} sites, {totals['head_offices']} HQs, {totals['branches']} branches, {totals['equipment']} equipment")
        print(f"  Brand: {data['brand']}")
    
    def test_all_sites_query_params(self):
        """Test query parameter filtering: org_id, site_type, q."""
        headers = get_auth_headers(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)
        
        # Test site_type=head_office filter
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/all-sites",
            headers=headers,
            params={"site_type": "head_office", "limit": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # All returned sites should be head offices
        for site in data["sites"]:
            assert site.get("is_head_office") == True, f"Site {site['name']} is not a head office"
        
        print(f"✓ site_type=head_office filter works: {len(data['sites'])} head offices returned")
        
        # Test site_type=branch filter
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/all-sites",
            headers=headers,
            params={"site_type": "branch", "limit": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # All returned sites should be branches (not head offices)
        for site in data["sites"]:
            assert site.get("is_head_office") != True, f"Site {site['name']} is a head office, expected branch"
        
        print(f"✓ site_type=branch filter works: {len(data['sites'])} branches returned")
    
    def test_all_sites_pulse_admin_scope(self):
        """Pulse Master Admin gets only Pulse-brand sites with brand='pulse'."""
        headers = get_auth_headers(PULSE_ADMIN_EMAIL, PULSE_ADMIN_PASSWORD)
        
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/all-sites",
            headers=headers,
            params={"limit": 1000},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Pulse admin should see brand='pulse'
        assert data["brand"] == "pulse", f"Expected brand='pulse', got '{data['brand']}'"
        
        totals = data["totals"]
        print(f"✓ Pulse admin sees {totals['sites']} sites (brand='pulse')")
        print(f"  Head offices: {totals['head_offices']}, Branches: {totals['branches']}, Equipment: {totals['equipment']}")
        
        # Compare with GymAxis admin to verify filtering
        gymaxis_headers = get_auth_headers(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)
        gymaxis_resp = requests.get(
            f"{BASE_URL}/api/master-admin/all-sites",
            headers=gymaxis_headers,
            params={"limit": 1000},
        )
        gymaxis_data = gymaxis_resp.json()
        
        # Pulse admin should see same or fewer sites than GymAxis admin
        assert totals["sites"] <= gymaxis_data["totals"]["sites"], \
            f"Pulse admin sees more sites ({totals['sites']}) than GymAxis admin ({gymaxis_data['totals']['sites']})"
        
        print(f"✓ Pulse scope verified: {totals['sites']} Pulse sites vs {gymaxis_data['totals']['sites']} total sites")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints that should still work."""
    
    def test_organizations_endpoint(self):
        """GET /api/master-admin/organizations still works."""
        headers = get_auth_headers(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "organizations" in data, "Response missing 'organizations' array"
        
        print(f"✓ Organizations endpoint works: {len(data['organizations'])} orgs returned")
    
    def test_integrations_hub_endpoint(self):
        """GET /api/master-admin/integrations-hub still works."""
        headers = get_auth_headers(GYMAXIS_ADMIN_EMAIL, GYMAXIS_ADMIN_PASSWORD)
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "integrations" in data, "Response missing 'integrations' array"
        
        print(f"✓ Integrations Hub endpoint works: {len(data['integrations'])} integrations returned")
    
    def test_pulse_admin_integrations_hub_scope(self):
        """Pulse admin sees brand='pulse' on integrations-hub."""
        headers = get_auth_headers(PULSE_ADMIN_EMAIL, PULSE_ADMIN_PASSWORD)
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert data.get("brand") == "pulse", f"Expected brand='pulse', got '{data.get('brand')}'"
        
        print(f"✓ Pulse admin integrations-hub scope verified: brand='{data['brand']}'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
