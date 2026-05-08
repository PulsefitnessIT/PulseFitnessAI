"""
Test Account Settings Enhancements (iteration 216q)
- GET /api/account/onboarding — returns 8 steps with completion status
- GET /api/account/organisation — returns org address + contact details
- PATCH /api/account/organisation — owner-only update
- GET /api/account/billing/{payment_id}/invoice.pdf — PDF download
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


class TestAccountOnboarding:
    """Test GET /api/account/onboarding endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            self.token = resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    
    def test_onboarding_returns_8_steps(self):
        """Verify onboarding endpoint returns 8 steps with required fields"""
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "steps" in data, "Response should contain 'steps'"
        assert "percent" in data, "Response should contain 'percent'"
        assert "completed_count" in data, "Response should contain 'completed_count'"
        assert "total" in data, "Response should contain 'total'"
        
        steps = data["steps"]
        assert len(steps) == 8, f"Expected 8 steps, got {len(steps)}"
        
        # Verify each step has required fields
        expected_step_ids = [
            "site_details", "extra_sites", "invite_staff", "set_roles",
            "upload_logo", "import_machines", "connect_stripe", "complete_profile"
        ]
        actual_step_ids = [s["id"] for s in steps]
        assert actual_step_ids == expected_step_ids, f"Step IDs mismatch: {actual_step_ids}"
        
        for step in steps:
            assert "id" in step, "Step should have 'id'"
            assert "label" in step, "Step should have 'label'"
            assert "description" in step, "Step should have 'description'"
            assert "completed" in step, "Step should have 'completed'"
            assert "cta_label" in step, "Step should have 'cta_label'"
            # Either cta_route or cta_section should be present
            assert "cta_route" in step or "cta_section" in step, "Step should have cta_route or cta_section"
    
    def test_onboarding_percent_calculation(self):
        """Verify percent is calculated correctly"""
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        completed_count = data["completed_count"]
        total = data["total"]
        percent = data["percent"]
        
        expected_percent = int(round((completed_count / total) * 100)) if total > 0 else 0
        assert percent == expected_percent, f"Percent mismatch: expected {expected_percent}, got {percent}"


class TestAccountOrganisation:
    """Test GET/PATCH /api/account/organisation endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            self.token = resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    
    def test_get_organisation_returns_expected_fields(self):
        """Verify GET /api/account/organisation returns expected fields"""
        resp = requests.get(f"{BASE_URL}/api/account/organisation", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        expected_fields = [
            "name", "address_line1", "address_line2", "address_line3", "city",
            "postcode", "country", "phone", "primary_contact_email",
            "primary_contact_phone", "website", "company_code", "logo_url"
        ]
        for field in expected_fields:
            assert field in data, f"Response should contain '{field}'"
    
    def test_patch_organisation_updates_fields(self):
        """Verify PATCH /api/account/organisation updates allowed fields"""
        # First get current values
        get_resp = requests.get(f"{BASE_URL}/api/account/organisation", headers=self.headers)
        assert get_resp.status_code == 200
        original = get_resp.json()
        
        # Update with test values
        test_update = {
            "address_line1": "TEST_123 Test Street",
            "city": "TEST_London",
            "postcode": "TEST_SW1A 1AA",
            "website": "https://test.example.com"
        }
        
        patch_resp = requests.patch(
            f"{BASE_URL}/api/account/organisation",
            json=test_update,
            headers=self.headers
        )
        assert patch_resp.status_code == 200, f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"
        
        updated = patch_resp.json()
        assert updated["address_line1"] == test_update["address_line1"]
        assert updated["city"] == test_update["city"]
        assert updated["postcode"] == test_update["postcode"]
        assert updated["website"] == test_update["website"]
        
        # Verify persistence with GET
        verify_resp = requests.get(f"{BASE_URL}/api/account/organisation", headers=self.headers)
        assert verify_resp.status_code == 200
        verified = verify_resp.json()
        assert verified["address_line1"] == test_update["address_line1"]
        
        # Restore original values
        restore_update = {
            "address_line1": original.get("address_line1", ""),
            "city": original.get("city", ""),
            "postcode": original.get("postcode", ""),
            "website": original.get("website", "")
        }
        requests.patch(f"{BASE_URL}/api/account/organisation", json=restore_update, headers=self.headers)
    
    def test_patch_organisation_ignores_disallowed_fields(self):
        """Verify PATCH ignores fields not in ORG_ALLOWED_FIELDS"""
        # Try to update 'name' which should be ignored
        patch_resp = requests.patch(
            f"{BASE_URL}/api/account/organisation",
            json={"name": "HACKED_NAME", "address_line1": "Valid Update"},
            headers=self.headers
        )
        assert patch_resp.status_code == 200
        
        # Verify name was NOT changed
        get_resp = requests.get(f"{BASE_URL}/api/account/organisation", headers=self.headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["name"] != "HACKED_NAME", "Name should not be updatable via PATCH"


class TestInvoicePDF:
    """Test GET /api/account/billing/{payment_id}/invoice.pdf endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            self.token = resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    
    def test_invoice_pdf_nonexistent_returns_404(self):
        """Verify non-existent payment_id returns 404"""
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/nonexistent-payment-id/invoice.pdf",
            headers=self.headers,
            allow_redirects=False
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    
    def test_invoice_pdf_with_valid_payment(self):
        """Test invoice PDF endpoint with a real payment if available"""
        # First get billing info to find a payment
        billing_resp = requests.get(f"{BASE_URL}/api/account/billing", headers=self.headers)
        if billing_resp.status_code != 200:
            pytest.skip("Could not fetch billing info")
        
        billing = billing_resp.json()
        payments = billing.get("payment_history", [])
        
        if not payments:
            pytest.skip("No payments available to test PDF download")
        
        # Try the first payment
        payment = payments[0]
        payment_id = payment.get("id") or payment.get("session_id")
        
        if not payment_id:
            pytest.skip("Payment has no id or session_id")
        
        resp = requests.get(
            f"{BASE_URL}/api/account/billing/{payment_id}/invoice.pdf",
            headers=self.headers,
            allow_redirects=False
        )
        
        # Should be either 302 (Stripe redirect) or 200 (local PDF)
        assert resp.status_code in [200, 302], f"Expected 200 or 302, got {resp.status_code}: {resp.text}"
        
        if resp.status_code == 200:
            assert resp.headers.get("content-type") == "application/pdf", "Should return PDF content type"
        elif resp.status_code == 302:
            location = resp.headers.get("location", "")
            assert "stripe" in location.lower() or "invoice" in location.lower(), "Redirect should be to Stripe"


class TestAccountBilling:
    """Test GET /api/account/billing endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            self.token = resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip(f"Login failed: {resp.status_code} - {resp.text}")
    
    def test_billing_returns_payment_history(self):
        """Verify billing endpoint returns payment_history array"""
        resp = requests.get(f"{BASE_URL}/api/account/billing", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "payment_history" in data, "Response should contain 'payment_history'"
        assert isinstance(data["payment_history"], list), "payment_history should be a list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
