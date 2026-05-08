"""
Iter 215be — Backend tests for new flexible pricing model + checkout endpoints.

Tests:
1. GET /api/payments/pricing - returns correct pricing catalog
2. POST /api/payments/checkout/flex - bundle checkout (returns 501 without Stripe Price IDs)
3. POST /api/payments/checkout/flex - module checkout (returns 501 without Stripe Price IDs)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPricingEndpoint:
    """Tests for GET /api/payments/pricing"""

    def test_pricing_endpoint_returns_200(self):
        """Pricing endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/payments/pricing")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/payments/pricing returns 200")

    def test_pricing_bundle_structure(self):
        """Bundle should have correct structure and values"""
        response = requests.get(f"{BASE_URL}/api/payments/pricing")
        data = response.json()

        assert "bundle" in data, "Response should have 'bundle' key"
        bundle = data["bundle"]

        # Check bundle fields
        assert bundle["id"] == "gymaxis_pro", f"Bundle id should be 'gymaxis_pro', got {bundle['id']}"
        assert bundle["name"] == "GymAxis Pro", f"Bundle name should be 'GymAxis Pro', got {bundle['name']}"
        assert bundle["monthly"] == 150, f"Bundle monthly should be 150, got {bundle['monthly']}"
        assert bundle["per_site"] == 50, f"Bundle per_site should be 50, got {bundle['per_site']}"
        assert set(bundle["modules"]) == {"operations", "memberships", "marketing", "crm"}, \
            f"Bundle modules incorrect: {bundle['modules']}"

        # Stripe price IDs should NOT be in public response
        assert "stripe_price_id" not in bundle, "stripe_price_id should not be in public response"
        assert "site_addon_stripe_price_id" not in bundle, "site_addon_stripe_price_id should not be in public response"

        print("✓ Bundle structure and values correct")

    def test_pricing_modules_structure(self):
        """Modules should have correct structure and values"""
        response = requests.get(f"{BASE_URL}/api/payments/pricing")
        data = response.json()

        assert "modules" in data, "Response should have 'modules' key"
        modules = data["modules"]

        assert len(modules) == 4, f"Should have 4 modules, got {len(modules)}"

        # Expected module prices
        expected = {
            "memberships": 29,
            "crm": 49,
            "marketing": 49,
            "operations": 59
        }

        for mod in modules:
            assert mod["id"] in expected, f"Unknown module: {mod['id']}"
            assert mod["monthly"] == expected[mod["id"]], \
                f"Module {mod['id']} should be £{expected[mod['id']]}/mo, got £{mod['monthly']}"
            # Stripe price IDs should NOT be in public response
            assert "stripe_price_id" not in mod, f"stripe_price_id should not be in {mod['id']} response"

        print("✓ Modules structure and values correct")

    def test_pricing_trial_days(self):
        """Trial days should be 3"""
        response = requests.get(f"{BASE_URL}/api/payments/pricing")
        data = response.json()

        assert "trial_days" in data, "Response should have 'trial_days' key"
        assert data["trial_days"] == 3, f"Trial days should be 3, got {data['trial_days']}"
        print("✓ Trial days is 3")

    def test_pricing_stripe_configured_flag(self):
        """stripe_configured should be false (no Price IDs in test env)"""
        response = requests.get(f"{BASE_URL}/api/payments/pricing")
        data = response.json()

        assert "stripe_configured" in data, "Response should have 'stripe_configured' key"
        # In test env, Stripe Price IDs are not configured
        assert data["stripe_configured"] == False, \
            f"stripe_configured should be false in test env, got {data['stripe_configured']}"
        print("✓ stripe_configured is false (expected in test env)")


class TestFlexCheckoutEndpoint:
    """Tests for POST /api/payments/checkout/flex"""

    @pytest.fixture
    def auth_token(self):
        """Get auth token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")

    def test_flex_checkout_bundle_returns_501_without_price_ids(self, auth_token):
        """Bundle checkout should return 501 when Stripe Price IDs not configured"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={
                "plan": "bundle",
                "site_count": 1,
                "origin_url": "https://example.com"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # Expected: 501 because STRIPE_PRICE_GYMAXIS_PRO is not set
        assert response.status_code == 501, \
            f"Expected 501 (Price IDs not configured), got {response.status_code}"
        assert "not configured" in response.json().get("detail", "").lower(), \
            f"Error should mention 'not configured': {response.json()}"
        print("✓ Bundle checkout returns 501 (Stripe Price IDs not configured - expected)")

    def test_flex_checkout_module_returns_501_without_price_ids(self, auth_token):
        """Module checkout should return 501 when Stripe Price IDs not configured"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={
                "plan": "module",
                "module_id": "memberships",
                "origin_url": "https://example.com"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # Expected: 501 because STRIPE_PRICE_MEMBERSHIPS is not set
        assert response.status_code == 501, \
            f"Expected 501 (Price IDs not configured), got {response.status_code}"
        assert "not configured" in response.json().get("detail", "").lower(), \
            f"Error should mention 'not configured': {response.json()}"
        print("✓ Module checkout returns 501 (Stripe Price IDs not configured - expected)")

    def test_flex_checkout_requires_origin_url(self, auth_token):
        """Checkout should require origin_url"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={"plan": "bundle", "site_count": 1},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "origin_url" in response.json().get("detail", "").lower()
        print("✓ Checkout requires origin_url")

    def test_flex_checkout_invalid_plan(self, auth_token):
        """Checkout should reject invalid plan type"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={"plan": "invalid", "origin_url": "https://example.com"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Checkout rejects invalid plan type")

    def test_flex_checkout_invalid_module_id(self, auth_token):
        """Checkout should reject unknown module_id"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={
                "plan": "module",
                "module_id": "unknown_module",
                "origin_url": "https://example.com"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "unknown" in response.json().get("detail", "").lower()
        print("✓ Checkout rejects unknown module_id")

    def test_flex_checkout_requires_auth(self):
        """Checkout should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/payments/checkout/flex",
            json={"plan": "bundle", "site_count": 1, "origin_url": "https://example.com"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Checkout requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
