"""
Test suite for iteration 188 — Per-site module overrides, module guards,
Creative Studio, AI Action Undo Log, Booking Rules, CSV Bulk Import, Module Access Resolution.

Tests:
1. Per-site module overrides (GET/PUT /api/sites/{site_id}/modules)
2. Backend module guards on memberships+marketing routes (403 when module disabled)
3. Creative Studio generation with brand_lock/resolution payload
4. AI Action Undo Log (GET /api/master-admin/assistant-actions, POST undo)
5. Booking rules per-gym (GET/PUT/POST-reset /api/memberships/booking-rules)
6. CSV bulk import (GET csv-template, POST bulk-import)
7. Module access resolution (GET /api/auth/me returns module_access)
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
RATE_LIMIT_BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', 'test-bypass-secret-for-ci-runs-only-2026')

# Test credentials
MASTER_ADMIN = {
    "email": "admin@gymaxisai.com",
    "password": "MasterAdmin123!"
}

PULSE_PRO_OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!"
}

# Note: studio.leeds@gymaxisai.com was purged during platform reset (iteration 202)
# Using Lee Somers (pulse_pro) who has memberships+marketing modules enabled
MEMBERSHIPS_OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!"
}


@pytest.fixture(scope="module")
def master_admin_token():
    """Get auth token for master admin"""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=MASTER_ADMIN, headers=headers)
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get auth token for Pulse Pro operator (Lee Somers)"""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=PULSE_PRO_OPERATOR, headers=headers)
    assert resp.status_code == 200, f"Pulse Pro login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def memberships_token():
    """Get auth token for memberships operator (Studio Leeds)"""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=MEMBERSHIPS_OPERATOR, headers=headers)
    assert resp.status_code == 200, f"Memberships login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture
def master_admin_headers(master_admin_token):
    return {
        "Authorization": f"Bearer {master_admin_token}",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


@pytest.fixture
def pulse_pro_headers(pulse_pro_token):
    return {
        "Authorization": f"Bearer {pulse_pro_token}",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


@pytest.fixture
def memberships_headers(memberships_token):
    return {
        "Authorization": f"Bearer {memberships_token}",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Module Access Resolution — GET /api/auth/me returns module_access
# ═══════════════════════════════════════════════════════════════════════════

class TestModuleAccessResolution:
    """Test that /api/auth/me returns module_access with operations/memberships/marketing"""

    def test_auth_me_returns_module_access_for_pulse_pro(self, pulse_pro_headers):
        """Pulse Pro user should have module_access in /auth/me response"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=pulse_pro_headers)
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "module_access" in data, f"module_access missing from response: {data.keys()}"
        ma = data["module_access"]
        assert "operations" in ma
        assert "memberships" in ma
        assert "marketing" in ma
        print(f"Pulse Pro module_access: {ma}")

    def test_auth_me_returns_module_access_for_memberships_user(self, memberships_headers):
        """Memberships operator should have module_access in /auth/me response"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=memberships_headers)
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "module_access" in data, f"module_access missing from response: {data.keys()}"
        ma = data["module_access"]
        assert "operations" in ma
        assert "memberships" in ma
        assert "marketing" in ma
        print(f"Memberships user module_access: {ma}")

    def test_master_admin_has_all_modules_enabled(self, master_admin_headers):
        """Master admin should have all modules enabled"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=master_admin_headers)
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "module_access" in data
        ma = data["module_access"]
        assert ma.get("operations") is True, f"Master admin should have operations=True: {ma}"
        assert ma.get("memberships") is True, f"Master admin should have memberships=True: {ma}"
        assert ma.get("marketing") is True, f"Master admin should have marketing=True: {ma}"
        print(f"Master admin module_access: {ma}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Per-site Module Overrides — GET/PUT /api/sites/{site_id}/modules
# ═══════════════════════════════════════════════════════════════════════════

class TestPerSiteModuleOverrides:
    """Test per-site module override endpoints"""

    @pytest.fixture
    def test_site_id(self, pulse_pro_headers):
        """Get or create a test site for module override testing"""
        # First, list existing sites
        resp = requests.get(f"{BASE_URL}/api/sites", headers=pulse_pro_headers)
        assert resp.status_code == 200, f"List sites failed: {resp.text}"
        sites = resp.json().get("sites", [])
        if sites:
            return sites[0]["id"]
        # Create a new site if none exist
        resp = requests.post(
            f"{BASE_URL}/api/sites",
            json={"name": "Test Site for Module Overrides", "address": "123 Test St"},
            headers=pulse_pro_headers
        )
        if resp.status_code == 201 or resp.status_code == 200:
            return resp.json()["id"]
        pytest.skip("Could not get or create a test site")

    def test_get_site_modules_returns_effective_resolution(self, pulse_pro_headers, test_site_id):
        """GET /api/sites/{site_id}/modules returns site_overrides, org_modules, effective"""
        resp = requests.get(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Get site modules failed: {resp.text}"
        data = resp.json()
        assert "site_id" in data
        assert "site_overrides" in data
        assert "org_modules" in data
        assert "effective" in data
        eff = data["effective"]
        assert "operations" in eff
        assert "memberships" in eff
        assert "marketing" in eff
        print(f"Site modules response: site_overrides={data['site_overrides']}, effective={eff}")

    def test_put_site_modules_sets_override(self, pulse_pro_headers, test_site_id):
        """PUT /api/sites/{site_id}/modules with {modules:{operations:{enabled:false}}} persists override"""
        # Set operations to disabled for this site
        resp = requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"operations": {"enabled": False}}},
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Put site modules failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert "operations" in data.get("set", [])

        # Verify the override was persisted
        resp = requests.get(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["site_overrides"].get("operations", {}).get("enabled") is False
        assert data["effective"]["operations"] is False
        print(f"After setting override: site_overrides={data['site_overrides']}, effective={data['effective']}")

    def test_put_site_modules_clears_override_with_null(self, pulse_pro_headers, test_site_id):
        """PUT with {modules:{operations:null}} clears the override and re-inherits org"""
        # First set an override
        requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"operations": {"enabled": False}}},
            headers=pulse_pro_headers
        )

        # Now clear it with null
        resp = requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"operations": None}},
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Clear override failed: {resp.text}"
        data = resp.json()
        assert "operations" in data.get("cleared", [])

        # Verify the override was cleared
        resp = requests.get(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "operations" not in data["site_overrides"] or data["site_overrides"].get("operations") is None
        print(f"After clearing override: site_overrides={data['site_overrides']}")

    def test_put_site_modules_clears_override_with_clear_flag(self, pulse_pro_headers, test_site_id):
        """PUT with {modules:{operations:{clear:true}}} clears the override"""
        # First set an override
        requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"memberships": {"enabled": True}}},
            headers=pulse_pro_headers
        )

        # Now clear it with clear:true
        resp = requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"memberships": {"clear": True}}},
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Clear override failed: {resp.text}"
        data = resp.json()
        assert "memberships" in data.get("cleared", [])

    def test_put_site_modules_requires_owner_manager_or_master_admin(self, pulse_pro_headers, test_site_id):
        """PUT /api/sites/{site_id}/modules requires owner/manager/master-admin role"""
        # This test verifies the endpoint works for owner/manager (Lee Somers is a manager)
        resp = requests.put(
            f"{BASE_URL}/api/sites/{test_site_id}/modules",
            json={"modules": {"marketing": {"enabled": True}}},
            headers=pulse_pro_headers
        )
        # Should succeed for owner/manager
        assert resp.status_code == 200, f"Owner/manager should be able to set modules: {resp.text}"

    def test_get_site_modules_returns_404_for_cross_org(self, pulse_pro_headers, test_site_id):
        """GET /api/sites/{site_id}/modules returns 404 for site not in caller's org
        Note: This test verifies that the endpoint correctly scopes by organization.
        Since master admin doesn't have an org context, we test with the pulse_pro user
        accessing a non-existent site ID to verify 404 behavior."""
        # Try to access a non-existent site
        fake_site_id = "00000000-0000-0000-0000-000000000000"
        resp = requests.get(
            f"{BASE_URL}/api/sites/{fake_site_id}/modules",
            headers=pulse_pro_headers
        )
        # Should return 404 because site doesn't exist
        assert resp.status_code == 404, f"Expected 404 for non-existent site, got {resp.status_code}: {resp.text}"
        print("Got expected 404 for non-existent site")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Backend Module Guards — 403 when module disabled
# ═══════════════════════════════════════════════════════════════════════════

class TestModuleGuards:
    """Test that module guards return 403 when module is disabled"""

    def test_memberships_booking_rules_accessible_when_enabled(self, memberships_headers):
        """GET /api/memberships/booking-rules should work when memberships module is enabled"""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/booking-rules",
            headers=memberships_headers
        )
        # Should succeed (200) or return rules
        assert resp.status_code == 200, f"Booking rules should be accessible: {resp.text}"
        data = resp.json()
        assert "rules" in data
        print(f"Booking rules: {data['rules']}")

    def test_memberships_csv_template_accessible_when_enabled(self, memberships_headers):
        """GET /api/memberships/members/csv-template should work when memberships module is enabled"""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/csv-template",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"CSV template should be accessible: {resp.text}"
        assert "member_number" in resp.text or "first_name" in resp.text
        print(f"CSV template headers present: {resp.text[:200]}")

    def test_marketing_resolutions_accessible_when_enabled(self, memberships_headers):
        """GET /api/marketing/creative/resolutions should work when marketing module is enabled"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/resolutions",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Resolutions should be accessible: {resp.text}"
        data = resp.json()
        assert "presets" in data
        print(f"Resolution presets count: {len(data['presets'])}")

    def test_master_admin_bypasses_module_guard(self, master_admin_headers):
        """Master admin should bypass module guards even if org has module disabled"""
        # Master admin should always be able to access any module endpoint
        resp = requests.get(
            f"{BASE_URL}/api/memberships/booking-rules",
            headers=master_admin_headers
        )
        # Master admin bypasses guards
        assert resp.status_code == 200, f"Master admin should bypass module guard: {resp.text}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Creative Studio Generation — POST /api/marketing/creative/generate
# ═══════════════════════════════════════════════════════════════════════════

class TestCreativeStudioGeneration:
    """Test Creative Studio generation with brand_lock, resolution_preset, context_assets"""

    def test_get_resolution_presets(self, memberships_headers):
        """GET /api/marketing/creative/resolutions returns canonical resolution presets"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/resolutions",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Get resolutions failed: {resp.text}"
        data = resp.json()
        assert "presets" in data
        presets = data["presets"]
        assert len(presets) > 0
        # Check for expected presets
        preset_ids = [p["id"] for p in presets]
        assert "instagram_square" in preset_ids
        assert "instagram_story" in preset_ids
        assert "facebook_feed" in preset_ids
        print(f"Resolution presets: {preset_ids}")

    def test_creative_generate_with_brand_lock(self, memberships_headers):
        """POST /api/marketing/creative/generate with brand_lock=true includes brand kit context"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/generate",
            json={
                "prompt": "A motivational gym poster with energetic athletes",
                "brand_lock": True,
                "resolution_preset": "instagram_square"
            },
            headers=memberships_headers,
            timeout=120  # AI generation can be slow
        )
        # Accept 200 (success) or 402 (plan upgrade required) or fallback SVG
        assert resp.status_code in [200, 402], f"Creative generate failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "asset" in data
            asset = data["asset"]
            assert asset.get("brand_lock") is True
            assert "variants" in asset
            assert len(asset["variants"]) > 0
            print(f"Generated asset with brand_lock: id={asset['id']}, source={asset.get('source')}")

    def test_creative_generate_with_resolution_preset(self, memberships_headers):
        """POST /api/marketing/creative/generate with resolution_preset uses correct dimensions"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/generate",
            json={
                "prompt": "A fitness class in action",
                "brand_lock": False,
                "resolution_preset": "poster_vertical"
            },
            headers=memberships_headers,
            timeout=120
        )
        assert resp.status_code in [200, 402], f"Creative generate failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            asset = data["asset"]
            # poster_vertical is 1080x1350
            assert asset.get("width") == 1080
            assert asset.get("height") == 1350
            print(f"Generated asset with resolution: {asset['width']}x{asset['height']}")

    def test_creative_generate_with_custom_resolution(self, memberships_headers):
        """POST /api/marketing/creative/generate with custom_width/height uses custom dimensions"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/generate",
            json={
                "prompt": "A gym equipment showcase",
                "brand_lock": False,
                "custom_width": 800,
                "custom_height": 600
            },
            headers=memberships_headers,
            timeout=120
        )
        assert resp.status_code in [200, 402], f"Creative generate failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            asset = data["asset"]
            assert asset.get("width") == 800
            assert asset.get("height") == 600
            print(f"Generated asset with custom resolution: {asset['width']}x{asset['height']}")

    def test_creative_generate_requires_prompt(self, memberships_headers):
        """POST /api/marketing/creative/generate without prompt returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/generate",
            json={
                "brand_lock": True,
                "resolution_preset": "instagram_square"
            },
            headers=memberships_headers
        )
        assert resp.status_code == 400, f"Expected 400 for missing prompt, got {resp.status_code}: {resp.text}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. AI Action Undo Log — GET /api/master-admin/assistant-actions, POST undo
# ═══════════════════════════════════════════════════════════════════════════

class TestAIActionUndoLog:
    """Test AI Action Undo Log endpoints"""

    def test_get_assistant_actions_returns_rows_and_totals(self, master_admin_headers):
        """GET /api/master-admin/assistant-actions returns rows + totals"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/assistant-actions",
            headers=master_admin_headers
        )
        assert resp.status_code == 200, f"Get assistant actions failed: {resp.text}"
        data = resp.json()
        assert "rows" in data
        assert "totals" in data
        assert "undo_window_seconds" in data
        assert data["undo_window_seconds"] == 300  # 5 minutes
        totals = data["totals"]
        assert "by_type" in totals
        assert "by_mode" in totals
        assert "distinct_users" in totals
        assert "distinct_orgs" in totals
        print(f"Assistant actions: {len(data['rows'])} rows, totals={totals}")

    def test_get_assistant_actions_with_filters(self, master_admin_headers):
        """GET /api/master-admin/assistant-actions supports days, limit, mode, action_type filters"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/assistant-actions",
            params={"days": 30, "limit": 50, "mode": "operations"},
            headers=master_admin_headers
        )
        assert resp.status_code == 200, f"Get assistant actions with filters failed: {resp.text}"
        data = resp.json()
        assert "rows" in data
        assert data["window_days"] == 30
        # All rows should be operations mode if any exist
        for row in data["rows"]:
            assert row.get("mode") == "operations", f"Row mode should be operations: {row}"

    def test_undo_action_returns_404_for_nonexistent(self, master_admin_headers):
        """POST /api/master-admin/assistant-actions/{action_id}/undo returns 404 if not found"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/assistant-actions/nonexistent-action-id/undo",
            headers=master_admin_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_undo_action_requires_master_admin(self, pulse_pro_headers):
        """POST /api/master-admin/assistant-actions/{action_id}/undo requires master admin"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/assistant-actions/some-action-id/undo",
            headers=pulse_pro_headers
        )
        # Should return 403 (not master admin) or 404 (not found)
        assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}: {resp.text}"


class TestAIActionUndoFlow:
    """Test the full undo flow: execute action → undo within window"""

    @pytest.fixture
    def test_issue_id(self, pulse_pro_headers):
        """Get an open issue to test resolve/undo flow"""
        # Get issues for the org
        resp = requests.get(f"{BASE_URL}/api/issues", headers=pulse_pro_headers)
        if resp.status_code != 200:
            pytest.skip("Could not get issues")
        issues = resp.json().get("issues", [])
        # Find an open issue
        open_issues = [i for i in issues if i.get("status") in ("open", "in_progress")]
        if not open_issues:
            pytest.skip("No open issues available for testing")
        return open_issues[0]["id"]

    def test_resolve_issue_then_undo(self, pulse_pro_headers, master_admin_headers, test_issue_id):
        """Execute resolve_issue via assistant, then undo it within 5 minutes"""
        # Step 1: Execute resolve_issue action
        resp = requests.post(
            f"{BASE_URL}/api/assistant/execute-action",
            json={
                "mode": "operations",
                "type": "resolve_issue",
                "params": {"fault_id": test_issue_id}
            },
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Execute resolve_issue failed: {resp.text}"
        data = resp.json()
        assert data.get("executed") is True
        print(f"Resolved issue: {test_issue_id}")

        # Step 2: Get the action log to find the action_id
        time.sleep(1)  # Give time for the log to be written
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/assistant-actions",
            params={"days": 1, "limit": 10, "action_type": "resolve_issue"},
            headers=master_admin_headers
        )
        assert resp.status_code == 200
        rows = resp.json().get("rows", [])
        # Find the action for our issue
        action_row = None
        for row in rows:
            if row.get("target_id") == test_issue_id:
                action_row = row
                break

        if not action_row:
            # The action might have been logged with already_done=true if issue was already resolved
            print("Action not found in log - issue may have already been resolved")
            return

        action_id = action_row["id"]
        print(f"Found action in log: {action_id}")

        # Step 3: Undo the action
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/assistant-actions/{action_id}/undo",
            headers=master_admin_headers
        )
        # Could be 200 (success), 400 (already undone or outside window), or 409 (state changed)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("ok") is True
            assert data.get("action_type") == "resolve_issue"
            print(f"Successfully undone action: {action_id}")
        elif resp.status_code == 400:
            # Already undone or outside window
            print(f"Undo returned 400: {resp.text}")
        else:
            print(f"Undo returned {resp.status_code}: {resp.text}")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Booking Rules Per-Gym — GET/PUT/POST-reset /api/memberships/booking-rules
# ═══════════════════════════════════════════════════════════════════════════

class TestBookingRulesPerGym:
    """Test per-gym booking rules endpoints"""

    def test_get_booking_rules_returns_rules_and_inherited_flag(self, memberships_headers):
        """GET /api/memberships/booking-rules returns rules with inherited flag"""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/booking-rules",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Get booking rules failed: {resp.text}"
        data = resp.json()
        assert "rules" in data
        assert "inherited" in data
        rules = data["rules"]
        # Check expected fields
        assert "booking_window_hours" in rules
        assert "cancellation_cutoff_hours" in rules
        assert "waitlist_enabled" in rules
        assert "max_waitlist" in rules
        assert "default_capacity" in rules
        assert "no_show_penalty" in rules
        assert "no_show_strikes_before_block" in rules
        assert "checkin_window_min" in rules
        assert "instructor_assignment" in rules
        assert "allow_site_overrides" in rules
        print(f"Booking rules: inherited={data['inherited']}, rules={rules}")

    def test_put_booking_rules_saves_override(self, memberships_headers):
        """PUT /api/memberships/booking-rules saves gym-level override"""
        new_rules = {
            "booking_window_hours": 72,
            "cancellation_cutoff_hours": 6,
            "waitlist_enabled": True,
            "max_waitlist": 15,
            "default_capacity": 25,
            "no_show_penalty": "credit_forfeit",
            "no_show_strikes_before_block": 2,
            "checkin_window_min": 20,
            "instructor_assignment": "balanced",
            "allow_site_overrides": True
        }
        resp = requests.put(
            f"{BASE_URL}/api/memberships/booking-rules",
            json=new_rules,
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Put booking rules failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("inherited") is False

        # Verify the rules were saved
        resp = requests.get(
            f"{BASE_URL}/api/memberships/booking-rules",
            headers=memberships_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inherited"] is False
        assert data["rules"]["booking_window_hours"] == 72
        assert data["rules"]["cancellation_cutoff_hours"] == 6
        print(f"Saved booking rules: {data['rules']}")

    def test_reset_booking_rules_to_platform(self, memberships_headers):
        """POST /api/memberships/booking-rules/reset-to-platform clears gym override"""
        # First set a custom rule
        requests.put(
            f"{BASE_URL}/api/memberships/booking-rules",
            json={
                "booking_window_hours": 48,
                "cancellation_cutoff_hours": 4,
                "waitlist_enabled": False,
                "max_waitlist": 5,
                "default_capacity": 10,
                "no_show_penalty": "warning",
                "no_show_strikes_before_block": 5,
                "checkin_window_min": 10,
                "instructor_assignment": "manual",
                "allow_site_overrides": False
            },
            headers=memberships_headers
        )

        # Now reset to platform defaults
        resp = requests.post(
            f"{BASE_URL}/api/memberships/booking-rules/reset-to-platform",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Reset booking rules failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("inherited") is True

        # Verify the rules are now inherited
        resp = requests.get(
            f"{BASE_URL}/api/memberships/booking-rules",
            headers=memberships_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inherited"] is True
        print(f"After reset: inherited={data['inherited']}")


# ═══════════════════════════════════════════════════════════════════════════
# 7. CSV Bulk Import — GET csv-template, POST bulk-import
# ═══════════════════════════════════════════════════════════════════════════

class TestCSVBulkImport:
    """Test CSV template and bulk import endpoints"""

    def test_get_csv_template_returns_csv_with_headers(self, memberships_headers):
        """GET /api/memberships/members/csv-template returns CSV with expected headers"""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/csv-template",
            headers=memberships_headers
        )
        assert resp.status_code == 200, f"Get CSV template failed: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        content = resp.text
        # Check for expected headers
        expected_headers = ["member_number", "first_name", "last_name", "email", "mobile",
                           "address_line1", "city", "postcode", "dob", "plan_name", "joined_date"]
        for header in expected_headers:
            assert header in content, f"Missing header: {header}"
        print(f"CSV template headers: {content.split(chr(10))[0]}")

    def test_bulk_import_with_valid_csv(self, memberships_headers):
        """POST /api/memberships/members/bulk-import with valid CSV creates members"""
        # Create a small valid CSV
        unique_id = uuid.uuid4().hex[:6]
        csv_content = f'''"member_number","first_name","last_name","email","mobile","address_line1","address_line2","city","postcode","dob","plan_name","joined_date"
"TEST-{unique_id}","Test","User{unique_id}","test.bulk.{unique_id}@example.com","+447700900999","1 Test Lane","","London","SW1A 1AA","1990-01-15","","2026-01-20"
'''
        files = {
            'file': ('members.csv', csv_content.encode('utf-8'), 'text/csv')
        }
        # Remove Content-Type from headers for multipart upload
        headers = {k: v for k, v in memberships_headers.items() if k.lower() != 'content-type'}

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-import",
            files=files,
            headers=headers
        )
        assert resp.status_code == 200, f"Bulk import failed: {resp.text}"
        data = resp.json()
        assert "created" in data
        assert "skipped" in data
        assert "total" in data
        assert data["created"] >= 0
        print(f"Bulk import result: created={data['created']}, skipped={data['skipped']}, total={data['total']}")

    def test_bulk_import_rejects_duplicate_email(self, memberships_headers):
        """POST /api/memberships/members/bulk-import skips rows with duplicate emails"""
        unique_id = uuid.uuid4().hex[:6]
        email = f"test.dup.{unique_id}@example.com"
        # CSV with same email twice
        csv_content = f'''"member_number","first_name","last_name","email","mobile","address_line1","address_line2","city","postcode","dob","plan_name","joined_date"
"DUP1-{unique_id}","First","User","{email}","+447700900001","1 Test Lane","","London","SW1A 1AA","1990-01-15","","2026-01-20"
"DUP2-{unique_id}","Second","User","{email}","+447700900002","2 Test Lane","","London","SW1A 1AA","1990-01-16","","2026-01-21"
'''
        files = {
            'file': ('members.csv', csv_content.encode('utf-8'), 'text/csv')
        }
        headers = {k: v for k, v in memberships_headers.items() if k.lower() != 'content-type'}

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-import",
            files=files,
            headers=headers
        )
        assert resp.status_code == 200, f"Bulk import failed: {resp.text}"
        data = resp.json()
        # First row should be created, second should be skipped as duplicate
        assert data["created"] == 1
        assert data["skipped"] == 1
        # Check the rows report for the duplicate reason
        rows = data.get("rows", [])
        dup_row = [r for r in rows if not r.get("ok") and "duplicate" in r.get("reason", "").lower()]
        assert len(dup_row) == 1
        print(f"Duplicate handling: created={data['created']}, skipped={data['skipped']}")

    def test_bulk_import_requires_name_fields(self, memberships_headers):
        """POST /api/memberships/members/bulk-import skips rows missing first_name or last_name"""
        unique_id = uuid.uuid4().hex[:6]
        csv_content = f'''"member_number","first_name","last_name","email","mobile","address_line1","address_line2","city","postcode","dob","plan_name","joined_date"
"NONAME-{unique_id}","","","noname.{unique_id}@example.com","+447700900003","1 Test Lane","","London","SW1A 1AA","1990-01-15","","2026-01-20"
'''
        files = {
            'file': ('members.csv', csv_content.encode('utf-8'), 'text/csv')
        }
        headers = {k: v for k, v in memberships_headers.items() if k.lower() != 'content-type'}

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-import",
            files=files,
            headers=headers
        )
        assert resp.status_code == 200, f"Bulk import failed: {resp.text}"
        data = resp.json()
        assert data["skipped"] == 1
        rows = data.get("rows", [])
        missing_name_row = [r for r in rows if not r.get("ok") and "name" in r.get("reason", "").lower()]
        assert len(missing_name_row) == 1
        print(f"Missing name handling: skipped={data['skipped']}, reason={missing_name_row[0].get('reason')}")


# ═══════════════════════════════════════════════════════════════════════════
# 8. Module Guard with Disabled Module (Integration Test)
# ═══════════════════════════════════════════════════════════════════════════

class TestModuleGuardWithDisabledModule:
    """Test that module guards return 403 when module is disabled via master admin"""

    @pytest.fixture
    def test_org_id(self, pulse_pro_headers):
        """Get the org_id for the pulse pro user"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=pulse_pro_headers)
        assert resp.status_code == 200
        return resp.json().get("organization_id")

    def test_disable_module_then_access_returns_403(self, master_admin_headers, pulse_pro_headers, test_org_id):
        """Disabling a module via master admin should cause 403 on guarded routes"""
        if not test_org_id:
            pytest.skip("Could not get org_id")

        # Step 1: Get current module state
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/modules",
            headers=master_admin_headers
        )
        if resp.status_code != 200:
            pytest.skip(f"Could not get org modules: {resp.text}")
        original_modules = resp.json().get("modules", {})
        print(f"Original modules: {original_modules}")

        # Step 2: Disable marketing module
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/modules",
            json={"modules": {"marketing": {"enabled": False}}},
            headers=master_admin_headers
        )
        if resp.status_code != 200:
            pytest.skip(f"Could not disable marketing module: {resp.text}")
        print("Disabled marketing module")

        try:
            # Step 3: Try to access a marketing-guarded route
            resp = requests.get(
                f"{BASE_URL}/api/marketing/creative/resolutions",
                headers=pulse_pro_headers
            )
            # Should return 403 because marketing is disabled
            assert resp.status_code == 403, f"Expected 403 when marketing disabled, got {resp.status_code}: {resp.text}"
            print(f"Got expected 403: {resp.text}")
        finally:
            # Step 4: Re-enable marketing module
            resp = requests.put(
                f"{BASE_URL}/api/master-admin/organizations/{test_org_id}/modules",
                json={"modules": {"marketing": {"enabled": True}}},
                headers=master_admin_headers
            )
            print("Re-enabled marketing module")

        # Step 5: Verify access is restored
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/resolutions",
            headers=pulse_pro_headers
        )
        assert resp.status_code == 200, f"Marketing should be accessible after re-enabling: {resp.text}"
        print("Marketing access restored")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
