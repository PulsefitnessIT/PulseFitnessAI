"""
Iteration 216af — Brand Inheritance (iGym vs Pulse parent/child override on site doc)

Tests:
1. GET /api/sites/{site_id}/branding — returns effective branding with _inherits flags
2. PATCH /api/sites/{site_id}/branding — override fields, clear with empty string
3. 403 for staff role, 404 for site not in org
4. GET /api/m/{slug}/branding — public endpoint with optional ?site= param
5. PATCH /api/organization/branding — regression test (parent org branding)
6. Audit row for site.branding.updated
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "bob@knockers.com"
OPERATOR_PASSWORD = "Test123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def operator_token(api_client):
    """Get operator (Bob) auth token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Operator login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth"""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_site(api_client, operator_headers):
    """Create a test site for branding tests, clean up after"""
    # Create site
    site_name = f"TEST_BrandInherit_{uuid.uuid4().hex[:6]}"
    create_resp = api_client.post(f"{BASE_URL}/api/sites", json={
        "name": site_name,
        "address": "123 Test Street",
        "postcode": "TE1 1ST"
    }, headers=operator_headers)
    
    if create_resp.status_code != 200:
        pytest.skip(f"Failed to create test site: {create_resp.status_code} - {create_resp.text}")
    
    site = create_resp.json()
    site_id = site.get("id")
    
    yield {"id": site_id, "name": site_name}
    
    # Cleanup
    api_client.delete(f"{BASE_URL}/api/sites/{site_id}", headers=operator_headers)


class TestSiteBrandingGet:
    """GET /api/sites/{site_id}/branding tests"""
    
    def test_get_site_branding_default_inherit(self, api_client, operator_headers, test_site):
        """Brand-new site should inherit all fields from parent org"""
        response = api_client.get(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "site_id" in data, "Response should contain site_id"
        assert "site_name" in data, "Response should contain site_name"
        assert "effective" in data, "Response should contain effective branding"
        assert "override" in data, "Response should contain override dict"
        assert "parent" in data, "Response should contain parent branding"
        
        # Verify effective branding structure
        effective = data["effective"]
        assert "name" in effective, "effective should contain name"
        assert "logo_url" in effective, "effective should contain logo_url"
        assert "primary_color" in effective, "effective should contain primary_color"
        assert "secondary_color" in effective, "effective should contain secondary_color"
        assert "_inherits" in effective, "effective should contain _inherits flags"
        assert "_parent" in effective, "effective should contain _parent values"
        
        # On a brand-new site, all _inherits flags should be True
        inherits = effective["_inherits"]
        assert inherits.get("name") is True, "name should be inherited"
        assert inherits.get("logo_url") is True, "logo_url should be inherited"
        assert inherits.get("primary_color") is True, "primary_color should be inherited"
        assert inherits.get("secondary_color") is True, "secondary_color should be inherited"
        
        # Effective values should equal parent values
        parent = effective["_parent"]
        assert effective["name"] == parent["name"], "effective name should equal parent name"
        assert effective["logo_url"] == parent["logo_url"], "effective logo_url should equal parent"
        assert effective["primary_color"] == parent["primary_color"], "effective primary_color should equal parent"
        
        # Primary color should default to #19CDFF if org has none
        assert effective["primary_color"], "primary_color should have a value"
        
        print(f"✓ GET site branding returns correct structure with all fields inherited")
    
    def test_get_site_branding_404_not_found(self, api_client, operator_headers):
        """Non-existent site should return 404"""
        fake_site_id = str(uuid.uuid4())
        response = api_client.get(
            f"{BASE_URL}/api/sites/{fake_site_id}/branding",
            headers=operator_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✓ GET site branding returns 404 for non-existent site")


class TestSiteBrandingPatch:
    """PATCH /api/sites/{site_id}/branding tests"""
    
    def test_patch_site_branding_override_single_field(self, api_client, operator_headers, test_site):
        """Patching a single field should override it, others remain inherited"""
        override_color = "#FF6B35"
        response = api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"primary_color": override_color},
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify override was applied
        assert data["override"].get("primary_color") == override_color, "Override should contain primary_color"
        assert data["effective"]["primary_color"] == override_color, "Effective should reflect override"
        
        # _inherits flag should flip to False for overridden field
        assert data["effective"]["_inherits"]["primary_color"] is False, "primary_color should NOT be inherited"
        
        # Other fields should still be inherited
        assert data["effective"]["_inherits"]["name"] is True, "name should still be inherited"
        assert data["effective"]["_inherits"]["logo_url"] is True, "logo_url should still be inherited"
        
        print(f"✓ PATCH single field overrides correctly, others remain inherited")
    
    def test_patch_site_branding_override_multiple_fields(self, api_client, operator_headers, test_site):
        """Patching multiple fields should override all of them"""
        overrides = {
            "name": "iGym Leeds Override",
            "primary_color": "#1A1A2E",
            "secondary_color": "#E94560"
        }
        response = api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json=overrides,
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify all overrides applied
        for key, value in overrides.items():
            assert data["override"].get(key) == value, f"Override should contain {key}={value}"
            assert data["effective"][key] == value, f"Effective {key} should be {value}"
            assert data["effective"]["_inherits"][key] is False, f"{key} should NOT be inherited"
        
        print(f"✓ PATCH multiple fields overrides all correctly")
    
    def test_patch_site_branding_clear_with_empty_string(self, api_client, operator_headers, test_site):
        """Passing empty string should clear override and revert to inherit"""
        # First set an override
        api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"name": "Temporary Override"},
            headers=operator_headers
        )
        
        # Now clear it with empty string
        response = api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"name": ""},
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # name should no longer be in override
        assert "name" not in data["override"] or data["override"].get("name") == "", \
            "name should be cleared from override"
        
        # _inherits flag should flip back to True
        assert data["effective"]["_inherits"]["name"] is True, "name should be inherited again"
        
        # Effective value should equal parent
        assert data["effective"]["name"] == data["effective"]["_parent"]["name"], \
            "effective name should equal parent after clear"
        
        print(f"✓ PATCH with empty string clears override and reverts to inherit")
    
    def test_patch_site_branding_403_staff_role(self, api_client, operator_headers, test_site):
        """Staff role should get 403 Forbidden"""
        # We need to create a staff user or use a different approach
        # For now, we'll test that the endpoint exists and returns proper error for unauthorized
        # This test would require a staff user token which we don't have readily available
        # Skip for now and document
        pytest.skip("Staff role test requires a staff user token - documented for manual verification")
    
    def test_patch_site_branding_404_wrong_org(self, api_client, operator_headers):
        """Site not belonging to caller's org should return 404"""
        fake_site_id = str(uuid.uuid4())
        response = api_client.patch(
            f"{BASE_URL}/api/sites/{fake_site_id}/branding",
            json={"name": "Should Fail"},
            headers=operator_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✓ PATCH returns 404 for site not in caller's org")


class TestPublicBrandingEndpoint:
    """GET /api/m/{slug}/branding tests"""
    
    def test_public_branding_no_site_param(self, api_client, operator_headers):
        """Public branding without ?site= should return org-level branding"""
        # First get the org's slug
        org_resp = api_client.get(f"{BASE_URL}/api/organization", headers=operator_headers)
        if org_resp.status_code != 200:
            pytest.skip("Could not get organization info")
        
        org = org_resp.json()
        slug = org.get("slug")
        
        if not slug:
            pytest.skip("Organization has no slug set")
        
        # Call public branding endpoint
        response = api_client.get(f"{BASE_URL}/api/m/{slug}/branding")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "organization_id" in data, "Response should contain organization_id"
        assert "name" in data, "Response should contain name"
        assert "primary_brand_colour" in data, "Response should contain primary_brand_colour"
        assert "branding_source" in data, "Response should contain branding_source"
        
        # Without ?site=, branding_source should be 'organization'
        assert data["branding_source"] == "organization", \
            f"branding_source should be 'organization', got {data['branding_source']}"
        
        print(f"✓ Public branding without ?site= returns org-level branding")
    
    def test_public_branding_with_site_override(self, api_client, operator_headers, test_site):
        """Public branding with ?site= and override should return site branding"""
        # First get the org's slug
        org_resp = api_client.get(f"{BASE_URL}/api/organization", headers=operator_headers)
        if org_resp.status_code != 200:
            pytest.skip("Could not get organization info")
        
        org = org_resp.json()
        slug = org.get("slug")
        
        if not slug:
            pytest.skip("Organization has no slug set")
        
        # Set a site override
        override_color = "#AABBCC"
        override_name = "iGym Test Override"
        api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"primary_color": override_color, "name": override_name},
            headers=operator_headers
        )
        
        # Call public branding endpoint with ?site=
        response = api_client.get(f"{BASE_URL}/api/m/{slug}/branding?site={test_site['id']}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # With site override, branding_source should be 'site'
        assert data["branding_source"] == "site", \
            f"branding_source should be 'site', got {data['branding_source']}"
        
        # Values should reflect the override
        assert data["primary_brand_colour"] == override_color, \
            f"primary_brand_colour should be {override_color}, got {data['primary_brand_colour']}"
        assert data["name"] == override_name, \
            f"name should be {override_name}, got {data['name']}"
        
        # site_id and site_name should be present
        assert data.get("site_id") == test_site['id'], "site_id should match"
        
        print(f"✓ Public branding with ?site= and override returns site branding")
    
    def test_public_branding_with_site_no_override(self, api_client, operator_headers, test_site):
        """Public branding with ?site= but NO override should return org branding"""
        # First get the org's slug
        org_resp = api_client.get(f"{BASE_URL}/api/organization", headers=operator_headers)
        if org_resp.status_code != 200:
            pytest.skip("Could not get organization info")
        
        org = org_resp.json()
        slug = org.get("slug")
        
        if not slug:
            pytest.skip("Organization has no slug set")
        
        # Clear all site overrides
        api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"name": "", "primary_color": "", "secondary_color": "", "logo_url": ""},
            headers=operator_headers
        )
        
        # Call public branding endpoint with ?site=
        response = api_client.get(f"{BASE_URL}/api/m/{slug}/branding?site={test_site['id']}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # With no site override, branding_source should be 'organization'
        assert data["branding_source"] == "organization", \
            f"branding_source should be 'organization' when no override, got {data['branding_source']}"
        
        print(f"✓ Public branding with ?site= but no override returns org branding")
    
    def test_public_branding_404_invalid_slug(self, api_client):
        """Invalid slug should return 404"""
        response = api_client.get(f"{BASE_URL}/api/m/nonexistent-slug-12345/branding")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✓ Public branding returns 404 for invalid slug")


class TestOrgBrandingRegression:
    """PATCH /api/organization/branding regression tests"""
    
    def test_org_branding_update(self, api_client, operator_headers):
        """Parent org branding update should still work"""
        # Get current branding first
        org_resp = api_client.get(f"{BASE_URL}/api/organization", headers=operator_headers)
        if org_resp.status_code != 200:
            pytest.skip("Could not get organization info")
        
        org = org_resp.json()
        original_branding = org.get("branding", {})
        
        # Update branding
        new_color = "#DDEEFF"
        response = api_client.patch(
            f"{BASE_URL}/api/organization/branding",
            json={"primary_color": new_color, "company_name": "Test Org Name"},
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success") is True, "Response should indicate success"
        assert "branding" in data, "Response should contain branding"
        assert data["branding"]["primary_color"] == new_color, "primary_color should be updated"
        
        # Restore original if possible (best effort)
        if original_branding:
            api_client.patch(
                f"{BASE_URL}/api/organization/branding",
                json=original_branding,
                headers=operator_headers
            )
        
        print(f"✓ PATCH /api/organization/branding still works (regression)")


class TestAuditLog:
    """Audit logging tests for site branding updates"""
    
    def test_site_branding_audit_row(self, api_client, operator_headers, test_site):
        """Site branding update should write audit row (best-effort check)"""
        # Update site branding
        response = api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"name": "Audit Test Override"},
            headers=operator_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # The audit is best-effort (doesn't fail the response if audit fails)
        # We can only verify the response succeeded - actual audit verification
        # would require DB access or an audit log endpoint
        print(f"✓ Site branding update succeeded (audit is best-effort, not verified)")


class TestInheritanceLogic:
    """Test the inheritance resolution logic"""
    
    def test_effective_values_match_parent_when_inherited(self, api_client, operator_headers, test_site):
        """When a field is inherited, effective value should match parent"""
        # Clear all overrides
        api_client.patch(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            json={"name": "", "primary_color": "", "secondary_color": "", "logo_url": ""},
            headers=operator_headers
        )
        
        # Get branding
        response = api_client.get(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            headers=operator_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        effective = data["effective"]
        parent = effective["_parent"]
        inherits = effective["_inherits"]
        
        # For each inherited field, effective should equal parent
        for field in ["name", "logo_url", "primary_color", "secondary_color"]:
            if inherits.get(field):
                assert effective[field] == parent[field], \
                    f"Inherited {field}: effective ({effective[field]}) should equal parent ({parent[field]})"
        
        print(f"✓ Inherited fields have effective values matching parent")
    
    def test_default_primary_color(self, api_client, operator_headers, test_site):
        """Primary color should default to #19CDFF if org has none"""
        response = api_client.get(
            f"{BASE_URL}/api/sites/{test_site['id']}/branding",
            headers=operator_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Primary color should always have a value
        primary = data["effective"]["primary_color"]
        assert primary, "primary_color should have a value"
        
        # If parent has no primary color, it should default to #19CDFF
        parent_primary = data["effective"]["_parent"]["primary_color"]
        assert parent_primary, "parent primary_color should have a value (default #19CDFF)"
        
        print(f"✓ Primary color has default value: {primary}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
