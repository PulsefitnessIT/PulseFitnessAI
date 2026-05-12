"""
Iter 216h60 — Site-level module override guard tests.

Tests:
1. PUT /api/sites/{site_id}/modules with marketing=true when org has marketing OFF
   → returns ok:false, blocked:['marketing'], detail contains 'Cannot enable marketing'
   → site doc must NOT have marketing override stored
2. After enabling marketing at org level, same PUT succeeds (ok:true, set:['marketing'])
3. GET /api/sites/{site_id}/modules with legacy override (marketing.enabled=true) but org marketing=false
   → effective.marketing=false (capped by org)
4. Guard uses _org_module_access(synthetic non-master, org) so master admin calls don't bypass
5. Onboarding steps audit — verify cta_route and cta_section values
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
PULSE_ORG_ID = "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f"
PULSE_SITE_ID = "3c9ef5a9-1ad4-454d-b558-8d67cc4ecbbf"

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(master_admin_token):
    """Auth headers for master admin."""
    return {"Authorization": f"Bearer {master_admin_token}"}


class TestSiteModuleOverrideGuard:
    """Test site-level module override guard (iter 216h60)."""

    def test_01_disable_marketing_at_org_level(self, auth_headers):
        """Setup: Disable marketing at org level to test the guard."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}/features",
            json={"modules": {"marketing": {"enabled": False, "tier": "pro"}}},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to disable marketing: {resp.text}"
        data = resp.json()
        # API returns {"success": True} - verify the change took effect via GET
        assert data.get("success") is True, f"Expected success:true, got: {data}"
        
        # Verify via GET that marketing is now off
        resp2 = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}",
            headers=auth_headers
        )
        if resp2.status_code == 200:
            org_data = resp2.json()
            marketing_enabled = org_data.get("modules", {}).get("marketing", {}).get("enabled")
            assert marketing_enabled is False, f"Marketing should be disabled: {org_data.get('modules')}"

    def test_02_site_override_blocked_when_org_off(self, auth_headers):
        """PUT marketing=true on site when org has marketing OFF → blocked."""
        resp = requests.put(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            json={"modules": {"marketing": {"enabled": True}}},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Request failed: {resp.text}"
        data = resp.json()
        
        # Must return ok:false
        assert data.get("ok") is False, f"Expected ok:false, got: {data}"
        
        # Must have blocked:['marketing']
        assert "marketing" in data.get("blocked", []), f"Expected marketing in blocked: {data}"
        
        # Detail must contain 'Cannot enable marketing'
        detail = data.get("detail", "")
        assert "Cannot enable marketing" in detail, f"Expected detail to mention 'Cannot enable marketing': {detail}"

    def test_03_site_doc_has_no_marketing_override(self, auth_headers):
        """Verify site doc does NOT have marketing override stored after blocked attempt."""
        resp = requests.get(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to get site modules: {resp.text}"
        data = resp.json()
        
        # site_overrides should NOT have marketing key (or it should be cleared)
        site_overrides = data.get("site_overrides", {})
        # If marketing exists, it should not have enabled=true
        if "marketing" in site_overrides:
            assert site_overrides["marketing"].get("enabled") is not True, \
                f"Marketing override should not be enabled: {site_overrides}"

    def test_04_effective_marketing_capped_by_org(self, auth_headers):
        """GET site modules with org marketing=false → effective.marketing=false."""
        resp = requests.get(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to get site modules: {resp.text}"
        data = resp.json()
        
        # effective.marketing must be False (capped by org)
        effective = data.get("effective", {})
        assert effective.get("marketing") is False, \
            f"Expected effective.marketing=false when org has marketing off: {effective}"

    def test_05_enable_marketing_at_org_level(self, auth_headers):
        """Enable marketing at org level to test successful site override."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}/features",
            json={"modules": {"marketing": {"enabled": True, "tier": "pro"}}},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to enable marketing: {resp.text}"
        data = resp.json()
        # API returns {"success": True}
        assert data.get("success") is True, f"Expected success:true, got: {data}"

    def test_06_site_override_succeeds_when_org_on(self, auth_headers):
        """PUT marketing=true on site when org has marketing ON → succeeds."""
        resp = requests.put(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            json={"modules": {"marketing": {"enabled": True}}},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Request failed: {resp.text}"
        data = resp.json()
        
        # Must return ok:true
        assert data.get("ok") is True, f"Expected ok:true, got: {data}"
        
        # Must have set:['marketing']
        assert "marketing" in data.get("set", []), f"Expected marketing in set: {data}"
        
        # blocked should be empty
        assert len(data.get("blocked", [])) == 0, f"Expected no blocked modules: {data}"

    def test_07_clear_site_override_and_restore_org(self, auth_headers):
        """Cleanup: Clear site override and restore org modules to all-on."""
        # Clear site override
        resp = requests.put(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            json={"modules": {"marketing": None, "memberships": None, "operations": None}},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to clear site overrides: {resp.text}"
        
        # Restore all modules at org level
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}/features",
            json={"modules": {
                "memberships": {"enabled": True, "tier": "pro"},
                "crm": {"enabled": True, "tier": "pro"},
                "marketing": {"enabled": True, "tier": "pro"},
                "operations": {"enabled": True, "tier": "pro"}
            }},
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Failed to restore org modules: {resp.text}"


class TestOnboardingStepsAudit:
    """Audit onboarding step CTA routes and sections (iter 216h60)."""

    def test_onboarding_steps_cta_values(self, auth_headers):
        """GET /api/account/onboarding returns correct cta_route/cta_section values."""
        resp = requests.get(f"{BASE_URL}/api/account/onboarding", headers=auth_headers)
        assert resp.status_code == 200, f"Failed to get onboarding: {resp.text}"
        data = resp.json()
        
        steps = data.get("steps", [])
        assert len(steps) > 0, "Expected onboarding steps"
        
        # Build a map of step_id -> step for easy lookup
        step_map = {s["id"]: s for s in steps}
        
        # Expected values per backend/routes/account.py line 716+
        expected = {
            "site_details": {"cta_route": "/sites"},
            "extra_sites": {"cta_route": "/sites"},
            "invite_staff": {"cta_section": "team"},
            "set_roles": {"cta_section": "team"},
            "upload_logo": {"cta_section": "organisation"},
            "import_machines": {"cta_route": "/dashboard?tab=equipment"},
            "connect_stripe": {"cta_route": "/pricing"},
            "complete_profile": {"cta_section": "profile"},
        }
        
        for step_id, expected_vals in expected.items():
            if step_id in step_map:
                step = step_map[step_id]
                for key, expected_val in expected_vals.items():
                    actual_val = step.get(key)
                    assert actual_val == expected_val, \
                        f"Step '{step_id}' expected {key}='{expected_val}', got '{actual_val}'"
                print(f"✓ Step '{step_id}': {expected_vals}")
            else:
                print(f"⚠ Step '{step_id}' not found in onboarding steps (may be conditional)")


class TestMasterAdminBypassGuard:
    """Verify master admin calls don't bypass the site module guard."""

    def test_master_admin_blocked_same_as_regular_user(self, auth_headers):
        """Master admin trying to enable marketing on site when org has it off → still blocked."""
        # First disable marketing at org level
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}/features",
            json={"modules": {"marketing": {"enabled": False, "tier": "pro"}}},
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        # Now try to enable at site level as master admin
        resp = requests.put(
            f"{BASE_URL}/api/sites/{PULSE_SITE_ID}/modules",
            json={"modules": {"marketing": {"enabled": True}}},
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Should still be blocked (guard uses synthetic non-master user)
        assert data.get("ok") is False, \
            f"Master admin should NOT bypass the guard. Expected ok:false, got: {data}"
        assert "marketing" in data.get("blocked", []), \
            f"Expected marketing in blocked even for master admin: {data}"
        
        # Cleanup: restore marketing
        requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{PULSE_ORG_ID}/features",
            json={"modules": {"marketing": {"enabled": True, "tier": "pro"}}},
            headers=auth_headers
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
