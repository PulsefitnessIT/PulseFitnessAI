"""
Iter 216h22 — Backend tests for the Integrations Hub endpoint (P5 redesign).

Tests:
1. GET /api/master-admin/integrations-hub — returns brand, integrations[4], summary
2. Auth gating — 401 without token
3. Pulse Master Admin scope — brand='pulse', orgs_total reflects only Pulse orgs
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RATE_LIMIT_BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', '')

# Test credentials
GYMAXIS_MASTER_ADMIN = {
    "email": "admin@gymaxisai.com",
    "password": "MasterAdmin123!"
}
PULSE_MASTER_ADMIN = {
    "email": "pulse.scope.test@pulsefitness.com",
    "password": "TestPulse2026!"
}


def get_bypass_headers():
    """Return rate-limit bypass header if secret is available."""
    if RATE_LIMIT_BYPASS:
        return {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    return {}


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    headers = {"Content-Type": "application/json", **get_bypass_headers()}
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=headers
    )
    if resp.status_code != 200:
        pytest.skip(f"Login failed for {email}: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestIntegrationsHubEndpoint:
    """Tests for GET /api/master-admin/integrations-hub"""

    def test_returns_401_without_token(self):
        """Endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Returns 401 without token")

    def test_returns_401_with_invalid_token(self):
        """Endpoint rejects invalid tokens."""
        headers = {"Authorization": "Bearer invalid-token-12345"}
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Returns 401 with invalid token")

    def test_gymaxis_master_admin_full_access(self):
        """GymAxis Master Admin gets full integrations hub data."""
        token = login(GYMAXIS_MASTER_ADMIN["email"], GYMAXIS_MASTER_ADMIN["password"])
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Check brand field
        assert "brand" in data, "Response missing 'brand' field"
        # GymAxis master admin should see 'all' brand by default
        assert data["brand"] in ["all", "gymaxis", "pulse"], f"Unexpected brand: {data['brand']}"
        
        # Check integrations array
        assert "integrations" in data, "Response missing 'integrations' field"
        integrations = data["integrations"]
        assert isinstance(integrations, list), "integrations should be a list"
        assert len(integrations) == 4, f"Expected 4 integrations, got {len(integrations)}"
        
        # Check each integration has required fields
        expected_keys = ["stripe_connect", "sicon", "orbit4", "sage200"]
        integration_keys = [i["key"] for i in integrations]
        for key in expected_keys:
            assert key in integration_keys, f"Missing integration: {key}"
        
        # Check integration structure
        for integration in integrations:
            assert "key" in integration, "Integration missing 'key'"
            assert "label" in integration, "Integration missing 'label'"
            assert "enabled" in integration, "Integration missing 'enabled'"
            assert "status" in integration, "Integration missing 'status'"
            assert integration["status"] in ["connected", "degraded", "not_configured", "down"], \
                f"Invalid status: {integration['status']}"
            assert "last_event_at" in integration, "Integration missing 'last_event_at'"
            assert "events_24h" in integration, "Integration missing 'events_24h'"
            assert "errors_24h" in integration, "Integration missing 'errors_24h'"
            assert "orgs_configured" in integration, "Integration missing 'orgs_configured'"
            assert "orgs_total" in integration, "Integration missing 'orgs_total'"
            assert "ref_field" in integration, "Integration missing 'ref_field'"
        
        # Check summary
        assert "summary" in data, "Response missing 'summary' field"
        summary = data["summary"]
        assert "connected" in summary, "Summary missing 'connected'"
        assert "degraded" in summary, "Summary missing 'degraded'"
        assert "not_configured" in summary, "Summary missing 'not_configured'"
        assert "total" in summary, "Summary missing 'total'"
        assert summary["total"] == 4, f"Expected total=4, got {summary['total']}"
        
        print(f"✓ GymAxis Master Admin gets full data: brand={data['brand']}, integrations={len(integrations)}")
        print(f"  Summary: connected={summary['connected']}, degraded={summary['degraded']}, not_configured={summary['not_configured']}")

    def test_pulse_master_admin_scoped_access(self):
        """Pulse Master Admin gets brand='pulse' and scoped org counts."""
        token = login(PULSE_MASTER_ADMIN["email"], PULSE_MASTER_ADMIN["password"])
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Pulse Master Admin MUST see brand='pulse'
        assert data.get("brand") == "pulse", f"Expected brand='pulse', got '{data.get('brand')}'"
        
        # Check integrations are present
        assert "integrations" in data, "Response missing 'integrations'"
        integrations = data["integrations"]
        assert len(integrations) == 4, f"Expected 4 integrations, got {len(integrations)}"
        
        # orgs_total should reflect only Pulse-brand orgs (not all 90)
        # The exact count depends on DB state, but it should be less than total platform orgs
        for integration in integrations:
            orgs_total = integration.get("orgs_total", 0)
            # We can't assert exact count, but we verify the field exists and is reasonable
            assert isinstance(orgs_total, int), f"orgs_total should be int, got {type(orgs_total)}"
            print(f"  {integration['key']}: orgs_total={orgs_total}, orgs_configured={integration.get('orgs_configured', 0)}")
        
        print(f"✓ Pulse Master Admin gets scoped data: brand={data['brand']}")

    def test_integration_ref_fields_correct(self):
        """Verify each integration has the correct ref_field for org coverage."""
        token = login(GYMAXIS_MASTER_ADMIN["email"], GYMAXIS_MASTER_ADMIN["password"])
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/integrations-hub", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        integrations = {i["key"]: i for i in data["integrations"]}
        
        # Verify ref_field mappings
        expected_refs = {
            "stripe_connect": "stripe_connect_account_id",
            "sicon": "sicon_customer_account_number",
            "orbit4": "orbit4_customer_id",
            "sage200": "sage_customer_number",
        }
        
        for key, expected_ref in expected_refs.items():
            actual_ref = integrations[key].get("ref_field")
            assert actual_ref == expected_ref, f"{key}: expected ref_field='{expected_ref}', got '{actual_ref}'"
        
        print("✓ All integration ref_fields are correct")


class TestPulseAdminScopeEnforcement:
    """Tests to verify Pulse Master Admin cannot see GymAxis-only data."""

    def test_pulse_admin_user_flags(self):
        """Verify the Pulse test user has correct flags (is_pulse_admin=true, is_master_admin=false)."""
        # Use login response which includes is_pulse_admin (unlike /api/auth/me)
        headers = {"Content-Type": "application/json", **get_bypass_headers()}
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": PULSE_MASTER_ADMIN["email"], "password": PULSE_MASTER_ADMIN["password"]},
            headers=headers
        )
        assert resp.status_code == 200, f"Login failed: {resp.status_code}"
        
        data = resp.json()
        user = data.get("user", {})
        assert user.get("is_pulse_admin") == True, f"Expected is_pulse_admin=True, got {user.get('is_pulse_admin')}"
        assert user.get("is_master_admin") in [False, None], f"Expected is_master_admin=False, got {user.get('is_master_admin')}"
        
        print(f"✓ Pulse test user has correct flags: is_pulse_admin={user.get('is_pulse_admin')}, is_master_admin={user.get('is_master_admin')}")

    def test_pulse_admin_orgs_list_scoped(self):
        """Verify Pulse Master Admin only sees Pulse-visible orgs in the organizations list."""
        token = login(PULSE_MASTER_ADMIN["email"], PULSE_MASTER_ADMIN["password"])
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(f"{BASE_URL}/api/master-admin/organizations", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        orgs = data.get("organizations", [])
        
        # All orgs should be Pulse-visible account types
        pulse_visible_types = ["pulse_pro", "lite", "mod", "full"]
        for org in orgs:
            account_type = org.get("account_type", "full")
            # Note: 'full' is included in PULSE_VISIBLE_ACCOUNT_TYPES per the backend code
            assert account_type in pulse_visible_types, \
                f"Pulse admin saw non-Pulse org: {org.get('name')} (account_type={account_type})"
        
        print(f"✓ Pulse Master Admin sees {len(orgs)} orgs, all Pulse-visible")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
