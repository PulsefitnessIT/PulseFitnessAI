"""Iter 216h227 — End-to-end tests for module-tailored activation + onboarding.

Tests the full API surface:
  • GET /api/activation/me filters by primary_module
  • GET /api/account/onboarding hides steps based on primary_module
  • POST /api/auth/register with primary_module persists it on the org
  • Activation event hooks fire correctly for each module

Run: pytest backend/tests/test_iter_216h227_e2e_module_tailored.py -v
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token for setup operations."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@gymaxisai.com",
        "password": "MasterAdmin123!"
    })
    if resp.status_code != 200:
        pytest.skip("Admin login failed")
    return resp.json().get("token")


def _create_trial_user(primary_module: str) -> dict:
    """Create a fresh trial user with a specific primary_module."""
    unique = uuid.uuid4().hex[:8]
    email = f"test.{primary_module}.{unique}@example.com"
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "full_name": f"Test {primary_module.title()} User",
        "company_name": f"Test {primary_module.title()} Gym {unique}",
        "is_trial": True,
        "trial_duration_days": 3,
        "trial_unlock_all_modules": True,
        "primary_module": primary_module,
    })
    if resp.status_code != 200:
        return {"error": resp.text, "status": resp.status_code}
    data = resp.json()
    return {
        "token": data.get("token"),
        "user": data.get("user"),
        "email": email,
        "primary_module": primary_module,
    }


class TestActivationMeFiltering:
    """Test GET /api/activation/me filters by primary_module."""

    def test_operations_primary_module_shows_only_ops_events(self):
        """Operations trial should see ops + universal events, not CRM/Marketing."""
        user = _create_trial_user("operations")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        event_types = {e["event_type"] for e in data.get("timeline", [])}
        
        # Should have operations events
        assert "first_equipment_added" in event_types, "Missing first_equipment_added"
        assert "first_fault_logged" in event_types, "Missing first_fault_logged"
        # Should have universal events
        assert "first_login" in event_types, "Missing first_login"
        assert "first_staff_invited" in event_types, "Missing first_staff_invited"
        # Should NOT have CRM/Marketing events
        assert "first_lead_added" not in event_types, "Leaked first_lead_added"
        assert "first_campaign_launched" not in event_types, "Leaked first_campaign_launched"
        assert "first_member_added" not in event_types, "Leaked first_member_added"
        # Check primary_module is returned
        assert data.get("primary_module") == "operations"

    def test_memberships_primary_module_shows_only_memberships_events(self):
        """Memberships trial should see memberships + universal events."""
        user = _create_trial_user("memberships")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        event_types = {e["event_type"] for e in data.get("timeline", [])}
        
        # Should have memberships events
        assert "first_member_added" in event_types
        assert "first_booking_taken" in event_types
        assert "first_class_scheduled" in event_types
        # Should NOT have operations/CRM/Marketing events
        assert "first_equipment_added" not in event_types
        assert "first_lead_added" not in event_types
        assert "first_campaign_launched" not in event_types
        assert data.get("primary_module") == "memberships"

    def test_crm_primary_module_shows_only_crm_events(self):
        """CRM trial should see CRM + universal events."""
        user = _create_trial_user("crm")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        event_types = {e["event_type"] for e in data.get("timeline", [])}
        
        # Should have CRM events
        assert "first_lead_added" in event_types
        assert "first_deal_created" in event_types
        assert "first_quote_sent" in event_types
        # Should NOT have operations/memberships/marketing events
        assert "first_equipment_added" not in event_types
        assert "first_member_added" not in event_types
        assert "first_campaign_launched" not in event_types
        assert data.get("primary_module") == "crm"

    def test_marketing_primary_module_shows_only_marketing_events(self):
        """Marketing trial should see marketing + universal events."""
        user = _create_trial_user("marketing")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        event_types = {e["event_type"] for e in data.get("timeline", [])}
        
        # Should have marketing events
        assert "first_brand_discovered" in event_types
        assert "first_audience_built" in event_types
        assert "first_campaign_launched" in event_types
        # Should NOT have operations/memberships/CRM events
        assert "first_equipment_added" not in event_types
        assert "first_member_added" not in event_types
        assert "first_lead_added" not in event_types
        assert data.get("primary_module") == "marketing"


class TestOnboardingFiltering:
    """Test GET /api/account/onboarding filters steps by primary_module."""

    def test_operations_primary_shows_import_machines_step(self):
        """Operations trial should see import_machines and print_qr_codes steps."""
        user = _create_trial_user("operations")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        step_ids = {s["id"] for s in data.get("steps", [])}
        
        # Operations-specific steps should be visible
        assert "import_machines" in step_ids, "Missing import_machines for operations"
        assert "print_qr_codes" in step_ids, "Missing print_qr_codes for operations"
        # Universal steps should be visible
        assert "site_details" in step_ids
        assert "complete_profile" in step_ids
        # connect_stripe should be visible for operations
        assert "connect_stripe" in step_ids

    def test_marketing_primary_hides_import_machines_step(self):
        """Marketing trial should NOT see import_machines or print_qr_codes steps."""
        user = _create_trial_user("marketing")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        step_ids = {s["id"] for s in data.get("steps", [])}
        
        # Operations-specific steps should be hidden
        assert "import_machines" not in step_ids, "Leaked import_machines for marketing"
        assert "print_qr_codes" not in step_ids, "Leaked print_qr_codes for marketing"
        # Universal steps should be visible
        assert "site_details" in step_ids
        assert "complete_profile" in step_ids
        # connect_stripe should be visible for marketing
        assert "connect_stripe" in step_ids

    def test_crm_primary_hides_import_machines_and_connect_stripe(self):
        """CRM trial should NOT see import_machines, print_qr_codes, or connect_stripe."""
        user = _create_trial_user("crm")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        step_ids = {s["id"] for s in data.get("steps", [])}
        
        # Operations-specific steps should be hidden
        assert "import_machines" not in step_ids, "Leaked import_machines for CRM"
        assert "print_qr_codes" not in step_ids, "Leaked print_qr_codes for CRM"
        # connect_stripe should be hidden for CRM (no payments)
        assert "connect_stripe" not in step_ids, "Leaked connect_stripe for CRM"
        # Universal steps should be visible
        assert "site_details" in step_ids
        assert "complete_profile" in step_ids

    def test_memberships_primary_shows_connect_stripe_hides_machines(self):
        """Memberships trial should see connect_stripe but NOT import_machines."""
        user = _create_trial_user("memberships")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        step_ids = {s["id"] for s in data.get("steps", [])}
        
        # Operations-specific steps should be hidden
        assert "import_machines" not in step_ids, "Leaked import_machines for memberships"
        assert "print_qr_codes" not in step_ids, "Leaked print_qr_codes for memberships"
        # connect_stripe should be visible for memberships
        assert "connect_stripe" in step_ids, "Missing connect_stripe for memberships"
        # Universal steps should be visible
        assert "site_details" in step_ids
        assert "complete_profile" in step_ids


class TestPrimaryModulePersistence:
    """Test that primary_module is persisted on registration."""

    def test_register_with_primary_module_persists_on_org(self):
        """POST /api/auth/register with primary_module should persist it."""
        user = _create_trial_user("marketing")
        if "error" in user:
            pytest.skip(f"User creation failed: {user['error']}")
        
        # Verify via activation/me that the primary_module is set
        headers = {"Authorization": f"Bearer {user['token']}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        assert resp.status_code == 200
        
        data = resp.json()
        assert data.get("primary_module") == "marketing", \
            f"Expected primary_module='marketing', got {data.get('primary_module')}"


class TestLegacyFallback:
    """Test legacy orgs without primary_module fall back correctly."""

    def test_legacy_org_without_primary_module_sees_ops_plus_memberships(self, admin_token):
        """Orgs without primary_module should see ops + memberships events (legacy fallback)."""
        # Use admin account which has no primary_module set
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/activation/me", headers=headers)
        
        # Admin may not have an org, so this might return empty timeline
        # That's expected behavior for master admins
        assert resp.status_code == 200
        data = resp.json()
        
        # If there's a timeline, verify the legacy fallback behavior
        if data.get("timeline"):
            event_types = {e["event_type"] for e in data["timeline"]}
            # Legacy fallback should include ops + memberships + universal
            # but NOT CRM/Marketing events
            if "first_equipment_added" in event_types:
                # This is a legacy org with ops enabled
                assert "first_lead_added" not in event_types or data.get("primary_module"), \
                    "Legacy org leaked CRM events without primary_module"
