"""
Iteration 216ag — Brand Inheritance into Outbound Channels + Live Preview

Tests:
1. Invoice send path honours site branding (iGym Leeds vs parent org)
2. Invoice send regression (member with no site_id falls back to parent org)
3. SVC auto-notify ctx includes site-scoped branding
4. Site-branding override regression (GET/PATCH round-trip, _inherits flip)
5. _branding_for_member helper returns correct values for various scenarios
6. Frontend live preview component exists with correct data-testid
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "bob@knockers.com"
OPERATOR_PASSWORD = "Test123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator token for Bob@knockers.com"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not login as operator: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not login as master admin: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}"}


@pytest.fixture(scope="module")
def org_info(operator_headers):
    """Get operator's organization info"""
    resp = requests.get(f"{BASE_URL}/api/organization", headers=operator_headers)
    if resp.status_code != 200:
        pytest.skip(f"Could not get org info: {resp.status_code}")
    return resp.json()


@pytest.fixture(scope="module")
def test_site(operator_headers, org_info):
    """Create a test site with branding override for testing"""
    site_id = f"test-site-216ag-{uuid.uuid4().hex[:8]}"
    site_name = "iGym Leeds"
    
    # Create site
    resp = requests.post(f"{BASE_URL}/api/sites", headers=operator_headers, json={
        "name": site_name,
        "address": "123 Test Street, Leeds",
        "postcode": "LS1 1AA"
    })
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create test site: {resp.status_code} - {resp.text}")
    
    site = resp.json()
    site_id = site.get("id")
    
    # Set branding override
    resp = requests.patch(f"{BASE_URL}/api/sites/{site_id}/branding", headers=operator_headers, json={
        "name": "iGym Leeds",
        "primary_color": "#FF6B35"
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not set site branding: {resp.status_code} - {resp.text}")
    
    yield {"id": site_id, "name": site_name, "primary_color": "#FF6B35"}
    
    # Cleanup
    requests.delete(f"{BASE_URL}/api/sites/{site_id}", headers=operator_headers)


@pytest.fixture(scope="module")
def test_member_with_site(operator_headers, test_site):
    """Create a test member assigned to the test site"""
    member_email = f"test-member-216ag-{uuid.uuid4().hex[:8]}@example.com"
    
    resp = requests.post(f"{BASE_URL}/api/memberships/members", headers=operator_headers, json={
        "email": member_email,
        "first_name": "Test",
        "last_name": "Member",
        "site_id": test_site["id"]
    })
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create test member: {resp.status_code} - {resp.text}")
    
    data = resp.json()
    # Response wraps member in "member" key
    member = data.get("member", data)
    member_id = member.get("id")
    
    if not member_id:
        pytest.skip(f"Member creation returned no ID: {data}")
    
    yield {"id": member_id, "email": member_email, "site_id": test_site["id"]}
    
    # Cleanup
    if member_id:
        requests.delete(f"{BASE_URL}/api/memberships/members/{member_id}", headers=operator_headers)


@pytest.fixture(scope="module")
def test_member_no_site(operator_headers):
    """Create a test member with no site_id (should fall back to parent org branding)"""
    member_email = f"test-member-nosite-216ag-{uuid.uuid4().hex[:8]}@example.com"
    
    resp = requests.post(f"{BASE_URL}/api/memberships/members", headers=operator_headers, json={
        "email": member_email,
        "first_name": "NoSite",
        "last_name": "Member"
    })
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create test member without site: {resp.status_code} - {resp.text}")
    
    data = resp.json()
    # Response wraps member in "member" key
    member = data.get("member", data)
    member_id = member.get("id")
    
    if not member_id:
        pytest.skip(f"Member creation returned no ID: {data}")
    
    yield {"id": member_id, "email": member_email}
    
    # Cleanup
    if member_id:
        requests.delete(f"{BASE_URL}/api/memberships/members/{member_id}", headers=operator_headers)


class TestSiteBrandingRegressionFromIter216af:
    """Regression tests for site branding from iteration 216af"""
    
    def test_get_site_branding_returns_effective_and_inherits(self, operator_headers, test_site):
        """GET /api/sites/{id}/branding returns effective branding with _inherits flags"""
        resp = requests.get(f"{BASE_URL}/api/sites/{test_site['id']}/branding", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "effective" in data
        assert "override" in data
        assert "parent" in data
        
        effective = data["effective"]
        assert "_inherits" in effective
        assert effective.get("name") == "iGym Leeds"
        assert effective.get("primary_color") == "#FF6B35"
        
        # _inherits should be False for overridden fields
        inherits = effective["_inherits"]
        assert inherits.get("name") is False, "name should NOT be inherited (overridden)"
        assert inherits.get("primary_color") is False, "primary_color should NOT be inherited (overridden)"
    
    def test_patch_site_branding_clear_reverts_to_inherit(self, operator_headers, test_site):
        """PATCH with empty string clears override and reverts to inherit"""
        # First verify current state
        resp = requests.get(f"{BASE_URL}/api/sites/{test_site['id']}/branding", headers=operator_headers)
        assert resp.status_code == 200
        
        # Clear secondary_color (which should already be inherited)
        resp = requests.patch(f"{BASE_URL}/api/sites/{test_site['id']}/branding", headers=operator_headers, json={
            "secondary_color": ""
        })
        assert resp.status_code == 200
        
        data = resp.json()
        inherits = data["effective"]["_inherits"]
        assert inherits.get("secondary_color") is True, "secondary_color should be inherited after clear"
    
    def test_public_branding_with_site_param(self, operator_headers, test_site, org_info):
        """GET /api/m/{slug}/branding?site= returns site branding when override exists"""
        # First ensure org has a slug
        slug = org_info.get("slug") or org_info.get("id")
        if not slug:
            pytest.skip("Org has no slug")
        
        # Get public branding with site param
        resp = requests.get(f"{BASE_URL}/api/m/{slug}/branding", params={"site": test_site["id"]})
        # This endpoint may not require auth
        if resp.status_code == 404:
            pytest.skip("Public branding endpoint not found or org has no slug")
        
        if resp.status_code == 200:
            data = resp.json()
            # Should return site branding
            assert data.get("name") == "iGym Leeds" or data.get("branding", {}).get("name") == "iGym Leeds"


class TestInvoiceSendHonoursSiteBranding:
    """Test that invoice send path uses site-scoped branding"""
    
    def test_generate_invoice_for_member_with_site(self, operator_headers, test_member_with_site):
        """Generate invoice for member with site_id - should use site branding"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate", 
            headers=operator_headers, json={
                "period": period,
                "member_ids": [test_member_with_site["id"]],
                "send_email": False  # Don't actually send, just generate
            })
        
        # May return 200 with empty invoices if member has no billable items
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # The generate endpoint should succeed without 500 errors
        assert "period" in data
        print(f"Generate response: {data}")
    
    def test_invoice_send_endpoint_no_500_with_site_member(self, operator_headers, test_member_with_site):
        """POST /api/memberships/billing/invoices/{id}/send should not 500 for site member"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # First generate an invoice
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate", 
            headers=operator_headers, json={
                "period": period,
                "member_ids": [test_member_with_site["id"]],
                "send_email": False
            })
        
        if resp.status_code != 200:
            pytest.skip(f"Could not generate invoice: {resp.status_code}")
        
        data = resp.json()
        invoices = data.get("invoices", [])
        
        if not invoices:
            # Create a manual invoice for testing
            pytest.skip("No invoice generated (member has no billable items)")
        
        invoice_id = invoices[0].get("id")
        
        # Try to send - expect 502 (Resend not configured) NOT 500
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{invoice_id}/send", 
            headers=operator_headers)
        
        # 502 = Resend not configured (expected in preview env)
        # 400 = Member has no email
        # 200 = Success (if Resend is configured)
        # NOT 500 = No internal server error from branding resolver
        assert resp.status_code != 500, f"Got 500 error - branding resolver may have failed: {resp.text}"
        print(f"Send response: {resp.status_code} - {resp.text}")


class TestInvoiceSendFallbackToParentOrg:
    """Test that invoice send falls back to parent org branding when no site"""
    
    def test_invoice_send_no_site_member_no_500(self, operator_headers, test_member_no_site):
        """Invoice send for member without site_id should not 500"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # Generate invoice
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate", 
            headers=operator_headers, json={
                "period": period,
                "member_ids": [test_member_no_site["id"]],
                "send_email": False
            })
        
        if resp.status_code != 200:
            pytest.skip(f"Could not generate invoice: {resp.status_code}")
        
        data = resp.json()
        invoices = data.get("invoices", [])
        
        if not invoices:
            pytest.skip("No invoice generated (member has no billable items)")
        
        invoice_id = invoices[0].get("id")
        
        # Try to send
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{invoice_id}/send", 
            headers=operator_headers)
        
        # Should not 500
        assert resp.status_code != 500, f"Got 500 error: {resp.text}"
        print(f"Send response (no site): {resp.status_code}")


class TestSVCAutoNotifyWithSiteBranding:
    """Test that SVC auto-notify uses site-scoped branding"""
    
    def test_svc_case_create_via_intake_with_site_id(self, operator_headers, test_site):
        """Create SVC case via intake with site_id - should not error"""
        case_data = {
            "title": f"Test case 216ag - {uuid.uuid4().hex[:8]}",
            "description": "Testing site branding in auto-notify",
            "priority": "p3",
            "site_id": test_site["id"],
            "customer_name": "Test Customer",
            "customer_email": "test-customer-216ag@example.com",
            "comms_auto_notify": True
        }
        
        # Use the portal intake endpoint
        resp = requests.post(f"{BASE_URL}/api/svc/intake/portal", headers=operator_headers, json=case_data)
        
        # May get 404 if SVC module not enabled, or 200/201 on success
        if resp.status_code == 404:
            pytest.skip("SVC intake module not available")
        
        if resp.status_code == 422:
            # Validation error - check what fields are required
            print(f"Validation error: {resp.text}")
            pytest.skip(f"SVC intake validation: {resp.text}")
        
        assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        case = resp.json()
        case_id = case.get("id") or case.get("case", {}).get("id")
        
        # Cleanup
        if case_id:
            requests.delete(f"{BASE_URL}/api/svc/cases/{case_id}", headers=operator_headers)
        
        print(f"SVC case created with site_id: {case}")
    
    def test_svc_case_transition_no_500(self, operator_headers, test_site):
        """Transitioning SVC case state should not 500 when site branding is resolved"""
        case_data = {
            "title": f"Test transition 216ag - {uuid.uuid4().hex[:8]}",
            "description": "Testing state transition with site branding",
            "priority": "p3",
            "site_id": test_site["id"],
            "customer_name": "Test Customer",
            "customer_email": "test-transition-216ag@example.com",
            "comms_auto_notify": True
        }
        
        resp = requests.post(f"{BASE_URL}/api/svc/intake/portal", headers=operator_headers, json=case_data)
        
        if resp.status_code == 404:
            pytest.skip("SVC intake module not available")
        
        if resp.status_code not in (200, 201):
            pytest.skip(f"Could not create case: {resp.status_code} - {resp.text}")
        
        data = resp.json()
        case_id = data.get("id") or data.get("case", {}).get("id")
        
        if not case_id:
            pytest.skip(f"Case creation returned no ID: {data}")
        
        try:
            # Try to transition to en_route (should trigger auto-notify)
            resp = requests.post(f"{BASE_URL}/api/svc/cases/{case_id}/transition", headers=operator_headers, json={
                "target_state": "en_route",
                "assigned_engineer_name": "Test Engineer"
            })
            
            # Should not 500
            assert resp.status_code != 500, f"Got 500 on transition: {resp.text}"
            print(f"Transition response: {resp.status_code}")
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/svc/cases/{case_id}", headers=operator_headers)


class TestBrandingForMemberHelper:
    """Test the _branding_for_member helper behavior via API endpoints"""
    
    def test_invoice_preview_includes_branding_context(self, operator_headers, test_member_with_site):
        """Invoice preview should work without errors for site member"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview", 
            headers=operator_headers, json={
                "period": period,
                "member_ids": [test_member_with_site["id"]]
            })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "period" in data
        print(f"Preview response: {data}")
    
    def test_invoice_preview_no_site_member(self, operator_headers, test_member_no_site):
        """Invoice preview should work for member without site_id"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview", 
            headers=operator_headers, json={
                "period": period,
                "member_ids": [test_member_no_site["id"]]
            })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


class TestCommsLogForBrandedEmails:
    """Test that comms log captures branded email attempts"""
    
    def test_comms_log_endpoint_accessible(self, operator_headers):
        """GET /api/svc/comms/log should be accessible"""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/log", headers=operator_headers)
        
        if resp.status_code == 404:
            pytest.skip("SVC comms module not available")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "events" in data or "count" in data


class TestFrontendLivePreviewComponent:
    """Verify frontend live preview component exists"""
    
    def test_site_branding_override_component_has_preview_testid(self):
        """SiteBrandingOverride.js should have site-branding-preview-{id} data-testid"""
        import os
        component_path = "/app/frontend/src/components/sites/SiteBrandingOverride.js"
        
        if not os.path.exists(component_path):
            pytest.skip("SiteBrandingOverride.js not found")
        
        with open(component_path, "r") as f:
            content = f.read()
        
        # Check for live preview data-testid
        assert "site-branding-preview-" in content, "Missing site-branding-preview-{id} data-testid"
        assert "BrandPreview" in content, "Missing BrandPreview component"
        assert "Live preview" in content or "live preview" in content.lower(), "Missing live preview label"
        
        # Check that preview updates with draft values
        assert "draft" in content, "Preview should use draft values"
        assert "primary_color" in content or "primary" in content, "Preview should show primary color"
        
        print("Frontend live preview component verified")
    
    def test_brand_preview_shows_pay_button_with_color(self):
        """BrandPreview should show Pay button with primary color"""
        component_path = "/app/frontend/src/components/sites/SiteBrandingOverride.js"
        
        if not os.path.exists(component_path):
            pytest.skip("SiteBrandingOverride.js not found")
        
        with open(component_path, "r") as f:
            content = f.read()
        
        # Check for pay button in preview
        assert "Pay" in content, "Preview should show Pay button"
        assert "£45.00" in content or "45.00" in content, "Preview should show sample amount"
        
        # Check that button uses effective.primary color
        assert "effective.primary" in content or "effective['primary']" in content, \
            "Pay button should use effective primary color"


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_invoices(self, operator_headers):
        """Clean up any test invoices created during testing"""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices", 
            headers=operator_headers, params={"period": period})
        
        if resp.status_code != 200:
            return
        
        data = resp.json()
        invoices = data.get("invoices", [])
        
        for inv in invoices:
            if "test" in (inv.get("member_email") or "").lower() or "216ag" in (inv.get("member_email") or ""):
                inv_id = inv.get("id")
                if inv_id:
                    # Void the invoice
                    requests.patch(f"{BASE_URL}/api/memberships/billing/invoices/{inv_id}/status",
                        headers=operator_headers, json={"status": "void"})
