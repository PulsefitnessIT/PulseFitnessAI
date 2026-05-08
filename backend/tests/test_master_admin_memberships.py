"""
Test Suite: Master Admin Memberships Control Layer (Iteration 179)

Tests all 18 endpoints under /api/master-admin/memberships/*:
- Overview, Organizations, Org Detail, Tier Toggle, Overrides Toggle
- Plan Templates CRUD + Apply
- Booking Rules (GET/PUT with enum validation)
- Tiers Matrix (GET/PUT)
- Revenue, Engagement, Instructors, AI Insights
- Feature Flags (GET/PUT)
- Audit Log

Auth: Master admin required (403 for non-master-admin users)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "test-bypass-secret-for-ci-runs-only-2026")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
NON_ADMIN_EMAIL = "craig.henshall@pulsefitness.com"
NON_ADMIN_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def non_admin_token():
    """Get non-master-admin JWT token for 403 tests.
    Uses Service Portal user (lee.somers) instead of CRM user since
    CRM tokens use a different auth system and return 401 instead of 403.
    """
    # Use Service Portal non-admin user
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    if resp.status_code != 200:
        pytest.skip(f"Non-admin login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def master_headers(master_admin_token):
    """Headers with master admin auth."""
    return {
        "Authorization": f"Bearer {master_admin_token}",
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


@pytest.fixture(scope="module")
def non_admin_headers(non_admin_token):
    """Headers with non-admin auth."""
    return {
        "Authorization": f"Bearer {non_admin_token}",
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS
    }


# ═══════════════════════════════════════════════════════════════════
# OVERVIEW ENDPOINT
# ═══════════════════════════════════════════════════════════════════

class TestOverview:
    """GET /api/master-admin/memberships/overview"""

    def test_overview_returns_kpis(self, master_headers):
        """Overview returns KPIs with expected structure."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/overview", headers=master_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Validate KPIs structure
        assert "kpis" in data, "Missing 'kpis' key"
        kpis = data["kpis"]
        required_kpi_keys = [
            "total_organizations", "active_members", "total_mrr_pence",
            "bookings_7d", "bookings_30d", "churn_pct_30d", "occupancy_pct_7d"
        ]
        for key in required_kpi_keys:
            assert key in kpis, f"Missing KPI key: {key}"

        # Validate tier_split
        assert "tier_split" in data, "Missing 'tier_split' key"
        assert "lite" in data["tier_split"]
        assert "pro" in data["tier_split"]

        # Validate high_risk_orgs is a list
        assert "high_risk_orgs" in data
        assert isinstance(data["high_risk_orgs"], list)

        # Validate trend is a list of 6 months
        assert "trend" in data
        assert isinstance(data["trend"], list)
        assert len(data["trend"]) == 6, f"Expected 6 trend entries, got {len(data['trend'])}"

        print(f"✓ Overview KPIs: total_orgs={kpis['total_organizations']}, active_members={kpis['active_members']}, MRR={kpis['total_mrr_pence']}p")


# ═══════════════════════════════════════════════════════════════════
# ORGANIZATIONS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

class TestOrganizations:
    """GET /api/master-admin/memberships/organizations"""

    def test_list_organizations(self, master_headers):
        """List organizations returns array with expected fields."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "organizations" in data
        assert isinstance(data["organizations"], list)

        if data["organizations"]:
            org = data["organizations"][0]
            required_fields = ["id", "name", "memberships_tier", "members", "plans", "classes", "mrr_pence"]
            for field in required_fields:
                assert field in org, f"Missing field: {field}"

        print(f"✓ Listed {len(data['organizations'])} organizations")

    def test_filter_by_tier_lite(self, master_headers):
        """Filter organizations by tier=lite."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations?tier=lite", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        for org in data["organizations"]:
            assert org["memberships_tier"] == "lite", f"Expected lite tier, got {org['memberships_tier']}"

        print(f"✓ Filtered {len(data['organizations'])} lite-tier organizations")

    def test_filter_by_tier_pro(self, master_headers):
        """Filter organizations by tier=pro."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations?tier=pro", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        for org in data["organizations"]:
            assert org["memberships_tier"] == "pro", f"Expected pro tier, got {org['memberships_tier']}"

        print(f"✓ Filtered {len(data['organizations'])} pro-tier organizations")

    def test_search_by_name(self, master_headers):
        """Search organizations by name query."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations?q=gym", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        # All returned orgs should have 'gym' in name (case-insensitive)
        for org in data["organizations"]:
            assert "gym" in org["name"].lower(), f"Name '{org['name']}' doesn't contain 'gym'"

        print(f"✓ Search returned {len(data['organizations'])} organizations matching 'gym'")


class TestOrganizationDetail:
    """GET /api/master-admin/memberships/organizations/{org_id}"""

    @pytest.fixture(scope="class")
    def test_org_id(self, master_headers):
        """Get a valid org_id for testing."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations", headers=master_headers)
        if resp.status_code != 200 or not resp.json().get("organizations"):
            pytest.skip("No organizations available for testing")
        return resp.json()["organizations"][0]["id"]

    def test_org_detail_success(self, master_headers, test_org_id):
        """Get organization detail returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "organization" in data
        assert "plans" in data
        assert "classes" in data
        assert "stats" in data
        assert "audit" in data

        org = data["organization"]
        assert org["id"] == test_org_id
        assert "memberships_tier" in org
        assert "locked" in org
        assert "overrides_enabled" in org

        print(f"✓ Org detail: {org['name']} (tier={org['memberships_tier']}, plans={len(data['plans'])}, classes={len(data['classes'])})")

    def test_org_detail_404_for_bogus_id(self, master_headers):
        """404 for non-existent organization."""
        bogus_id = "bogus-org-id-does-not-exist-12345"
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations/{bogus_id}", headers=master_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ 404 returned for bogus org_id")


# ═══════════════════════════════════════════════════════════════════
# TIER TOGGLE
# ═══════════════════════════════════════════════════════════════════

class TestTierToggle:
    """PUT /api/master-admin/memberships/organizations/{org_id}/tier"""

    @pytest.fixture(scope="class")
    def test_org_id(self, master_headers):
        """Get a valid org_id for tier toggle testing."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations", headers=master_headers)
        if resp.status_code != 200 or not resp.json().get("organizations"):
            pytest.skip("No organizations available for testing")
        return resp.json()["organizations"][0]["id"]

    def test_set_tier_to_pro(self, master_headers, test_org_id):
        """Set organization tier to pro."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/tier",
            json={"memberships_tier": "pro"},
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        assert data["memberships_tier"] == "pro"
        print(f"✓ Set org {test_org_id} tier to pro")

    def test_set_tier_to_lite(self, master_headers, test_org_id):
        """Set organization tier back to lite."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/tier",
            json={"memberships_tier": "lite"},
            headers=master_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["memberships_tier"] == "lite"
        print(f"✓ Set org {test_org_id} tier back to lite")

    def test_tier_404_for_bogus_org(self, master_headers):
        """404 for tier change on non-existent org."""
        bogus_id = "bogus-org-tier-test-12345"
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{bogus_id}/tier",
            json={"memberships_tier": "pro"},
            headers=master_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ 404 returned for tier change on bogus org_id")

    def test_tier_invalid_value_rejected(self, master_headers, test_org_id):
        """Invalid tier value rejected with 422."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/tier",
            json={"memberships_tier": "invalid_tier"},
            headers=master_headers
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
        print("✓ Invalid tier value rejected with 422")


# ═══════════════════════════════════════════════════════════════════
# OVERRIDES TOGGLE
# ═══════════════════════════════════════════════════════════════════

class TestOverridesToggle:
    """PUT /api/master-admin/memberships/organizations/{org_id}/overrides"""

    @pytest.fixture(scope="class")
    def test_org_id(self, master_headers):
        """Get a valid org_id for overrides testing."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations", headers=master_headers)
        if resp.status_code != 200 or not resp.json().get("organizations"):
            pytest.skip("No organizations available for testing")
        return resp.json()["organizations"][0]["id"]

    def test_set_overrides_enabled(self, master_headers, test_org_id):
        """Enable overrides for organization."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/overrides",
            json={"overrides_enabled": True, "locked": False},
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        assert data["memberships_overrides_enabled"] is True
        assert data["memberships_locked"] is False
        print(f"✓ Set overrides_enabled=True, locked=False for org {test_org_id}")

    def test_set_locked_true(self, master_headers, test_org_id):
        """Lock organization memberships."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/overrides",
            json={"locked": True},
            headers=master_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["memberships_locked"] is True
        print(f"✓ Set locked=True for org {test_org_id}")

    def test_reset_overrides(self, master_headers, test_org_id):
        """Reset overrides to default state."""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/organizations/{test_org_id}/overrides",
            json={"overrides_enabled": False, "locked": False},
            headers=master_headers
        )
        assert resp.status_code == 200
        print(f"✓ Reset overrides for org {test_org_id}")


# ═══════════════════════════════════════════════════════════════════
# PLAN TEMPLATES CRUD
# ═══════════════════════════════════════════════════════════════════

class TestPlanTemplates:
    """CRUD for /api/master-admin/memberships/templates/plans"""

    created_template_id = None

    def test_list_templates(self, master_headers):
        """List plan templates."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/templates/plans", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)
        print(f"✓ Listed {len(data['templates'])} plan templates")

    def test_create_template(self, master_headers):
        """Create a new plan template."""
        template_data = {
            "name": f"TEST_Template_{uuid.uuid4().hex[:8]}",
            "kind": "recurring",
            "billing_cycle": "monthly",
            "price_pence": 2999,
            "upfront_fee_pence": 0,
            "included_classes": "unlimited",
            "freeze_allowed": True,
            "freeze_max_days": 30,
            "cancel_notice_days": 7,
            "grace_period_days": 3,
            "vat_pct": 20.0,
            "description": "Test template for iteration 179",
            "colour": "#FF5733"
        }
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/memberships/templates/plans",
            json=template_data,
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "template" in data
        assert data["template"]["name"] == template_data["name"]
        assert data["template"]["price_pence"] == 2999
        assert "id" in data["template"]

        TestPlanTemplates.created_template_id = data["template"]["id"]
        print(f"✓ Created template: {data['template']['name']} (id={data['template']['id']})")

    def test_update_template(self, master_headers):
        """Update the created template."""
        if not TestPlanTemplates.created_template_id:
            pytest.skip("No template created to update")

        resp = requests.patch(
            f"{BASE_URL}/api/master-admin/memberships/templates/plans/{TestPlanTemplates.created_template_id}",
            json={"price_pence": 3499, "description": "Updated description"},
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        print(f"✓ Updated template {TestPlanTemplates.created_template_id}")

    def test_apply_template_to_org(self, master_headers):
        """Apply template to an organization."""
        if not TestPlanTemplates.created_template_id:
            pytest.skip("No template created to apply")

        # Get an org to apply to
        orgs_resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/organizations", headers=master_headers)
        if orgs_resp.status_code != 200 or not orgs_resp.json().get("organizations"):
            pytest.skip("No organizations available")

        org_id = orgs_resp.json()["organizations"][0]["id"]

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/memberships/templates/plans/{TestPlanTemplates.created_template_id}/apply",
            json={"organization_ids": [org_id], "lock": False},
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        assert data["created"] >= 1
        print(f"✓ Applied template to org {org_id}, created {data['created']} plan(s)")

    def test_delete_template(self, master_headers):
        """Delete the created template."""
        if not TestPlanTemplates.created_template_id:
            pytest.skip("No template created to delete")

        resp = requests.delete(
            f"{BASE_URL}/api/master-admin/memberships/templates/plans/{TestPlanTemplates.created_template_id}",
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        print(f"✓ Deleted template {TestPlanTemplates.created_template_id}")
        TestPlanTemplates.created_template_id = None


# ═══════════════════════════════════════════════════════════════════
# BOOKING RULES
# ═══════════════════════════════════════════════════════════════════

class TestBookingRules:
    """GET/PUT /api/master-admin/memberships/booking-rules"""

    def test_get_booking_rules(self, master_headers):
        """Get global booking rules."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/booking-rules", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "rules" in data
        rules = data["rules"]
        required_fields = [
            "booking_window_hours", "cancellation_cutoff_hours", "waitlist_enabled",
            "max_waitlist", "default_capacity", "no_show_penalty",
            "no_show_strikes_before_block", "checkin_window_min",
            "instructor_assignment", "allow_site_overrides"
        ]
        for field in required_fields:
            assert field in rules, f"Missing field: {field}"

        print(f"✓ Booking rules: window={rules['booking_window_hours']}h, no_show_penalty={rules['no_show_penalty']}")

    def test_update_booking_rules_valid(self, master_headers):
        """Update booking rules with valid values."""
        valid_rules = {
            "booking_window_hours": 168,
            "cancellation_cutoff_hours": 12,
            "waitlist_enabled": True,
            "max_waitlist": 10,
            "default_capacity": 20,
            "no_show_penalty": "warning",
            "no_show_strikes_before_block": 3,
            "checkin_window_min": 15,
            "instructor_assignment": "manual",
            "allow_site_overrides": True
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/booking-rules",
            json=valid_rules,
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        print("✓ Updated booking rules with valid values")

    def test_update_booking_rules_invalid_no_show_penalty(self, master_headers):
        """422 for invalid no_show_penalty enum value."""
        invalid_rules = {
            "booking_window_hours": 168,
            "cancellation_cutoff_hours": 12,
            "waitlist_enabled": True,
            "max_waitlist": 10,
            "default_capacity": 20,
            "no_show_penalty": "invalid_penalty",  # Invalid enum
            "no_show_strikes_before_block": 3,
            "checkin_window_min": 15,
            "instructor_assignment": "manual",
            "allow_site_overrides": True
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/booking-rules",
            json=invalid_rules,
            headers=master_headers
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
        print("✓ 422 returned for invalid no_show_penalty enum")

    def test_update_booking_rules_invalid_instructor_assignment(self, master_headers):
        """422 for invalid instructor_assignment enum value."""
        invalid_rules = {
            "booking_window_hours": 168,
            "cancellation_cutoff_hours": 12,
            "waitlist_enabled": True,
            "max_waitlist": 10,
            "default_capacity": 20,
            "no_show_penalty": "warning",
            "no_show_strikes_before_block": 3,
            "checkin_window_min": 15,
            "instructor_assignment": "invalid_assignment",  # Invalid enum
            "allow_site_overrides": True
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/booking-rules",
            json=invalid_rules,
            headers=master_headers
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
        print("✓ 422 returned for invalid instructor_assignment enum")


# ═══════════════════════════════════════════════════════════════════
# TIERS MATRIX
# ═══════════════════════════════════════════════════════════════════

class TestTiersMatrix:
    """GET/PUT /api/master-admin/memberships/tiers"""

    def test_get_tiers(self, master_headers):
        """Get tier matrix with counts."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/tiers", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "matrix" in data
        assert "counts" in data
        assert "pro_orgs" in data

        assert "lite" in data["matrix"]
        assert "pro" in data["matrix"]
        assert "lite" in data["counts"]
        assert "pro" in data["counts"]

        print(f"✓ Tiers: lite={data['counts']['lite']}, pro={data['counts']['pro']}, pro_orgs={len(data['pro_orgs'])}")

    def test_update_tiers_matrix(self, master_headers):
        """Update tier feature matrix."""
        new_matrix = {
            "matrix": {
                "lite": {
                    "basic_memberships": True,
                    "class_booking": True,
                    "limited_reporting": True,
                    "advanced_reporting": False,
                    "ai_insights": False
                },
                "pro": {
                    "basic_memberships": True,
                    "class_booking": True,
                    "limited_reporting": True,
                    "advanced_reporting": True,
                    "ai_insights": True
                }
            }
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/tiers",
            json=new_matrix,
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        print("✓ Updated tier matrix")


# ═══════════════════════════════════════════════════════════════════
# REVENUE
# ═══════════════════════════════════════════════════════════════════

class TestRevenue:
    """GET /api/master-admin/memberships/revenue"""

    def test_revenue_structure(self, master_headers):
        """Revenue endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/revenue", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "by_org" in data
        assert "by_kind" in data
        assert "payments" in data
        assert "trend" in data
        assert "total_mrr_pence" in data

        # Validate payments structure
        payments = data["payments"]
        assert "failed_90d" in payments
        assert "refunds_90d" in payments
        assert "total_90d" in payments

        # Validate trend is 6 months
        assert len(data["trend"]) == 6

        print(f"✓ Revenue: total_mrr={data['total_mrr_pence']}p, by_org={len(data['by_org'])}, by_kind={len(data['by_kind'])}")


# ═══════════════════════════════════════════════════════════════════
# ENGAGEMENT
# ═══════════════════════════════════════════════════════════════════

class TestEngagement:
    """GET /api/master-admin/memberships/engagement"""

    def test_engagement_structure(self, master_headers):
        """Engagement endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/engagement", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "daily" in data
        assert "peak_hours" in data
        assert "utilisation" in data
        assert "no_show" in data
        assert "churn" in data

        # Validate daily is 30 days
        assert len(data["daily"]) == 30, f"Expected 30 daily entries, got {len(data['daily'])}"

        # Validate peak_hours is 24 hours
        assert len(data["peak_hours"]) == 24, f"Expected 24 peak_hours entries, got {len(data['peak_hours'])}"

        # Validate no_show structure
        no_show = data["no_show"]
        assert "total_30d" in no_show
        assert "no_shows_30d" in no_show
        assert "pct" in no_show

        print(f"✓ Engagement: no_show_pct={no_show['pct']}%, utilisation_orgs={len(data['utilisation'])}, churn_orgs={len(data['churn'])}")


# ═══════════════════════════════════════════════════════════════════
# INSTRUCTORS
# ═══════════════════════════════════════════════════════════════════

class TestInstructors:
    """GET /api/master-admin/memberships/instructors"""

    def test_instructors_structure(self, master_headers):
        """Instructors endpoint returns leaderboard structure."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/instructors", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "leaderboard" in data
        assert "top" in data
        assert "underperformers" in data

        assert isinstance(data["leaderboard"], list)
        assert isinstance(data["top"], list)
        assert isinstance(data["underperformers"], list)

        print(f"✓ Instructors: leaderboard={len(data['leaderboard'])}, top={len(data['top'])}, underperformers={len(data['underperformers'])}")


# ═══════════════════════════════════════════════════════════════════
# AI INSIGHTS
# ═══════════════════════════════════════════════════════════════════

class TestAIInsights:
    """GET /api/master-admin/memberships/ai-insights"""

    def test_ai_insights_structure(self, master_headers):
        """AI insights returns insights array with expected fields."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/ai-insights", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "insights" in data
        assert "generated_at" in data
        assert isinstance(data["insights"], list)
        assert len(data["insights"]) <= 8, f"Expected max 8 insights, got {len(data['insights'])}"

        # Validate insight structure if any exist
        if data["insights"]:
            insight = data["insights"][0]
            required_fields = ["severity", "title", "detail", "action"]
            for field in required_fields:
                assert field in insight, f"Missing insight field: {field}"
            assert insight["severity"] in ["high", "medium", "low"], f"Invalid severity: {insight['severity']}"

        print(f"✓ AI Insights: {len(data['insights'])} insights generated at {data['generated_at']}")


# ═══════════════════════════════════════════════════════════════════
# FEATURE FLAGS
# ═══════════════════════════════════════════════════════════════════

class TestFeatureFlags:
    """GET/PUT /api/master-admin/memberships/feature-flags"""

    def test_get_feature_flags(self, master_headers):
        """Get global feature flags."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/feature-flags", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "flags" in data
        flags = data["flags"]

        # Check some expected flags exist
        expected_flags = ["memberships_enabled", "bookings_enabled", "ai_features_enabled"]
        for flag in expected_flags:
            assert flag in flags, f"Missing flag: {flag}"

        print(f"✓ Feature flags: {len(flags)} flags, memberships_enabled={flags.get('memberships_enabled')}")

    def test_update_feature_flags(self, master_headers):
        """Update feature flags."""
        new_flags = {
            "flags": {
                "memberships_enabled": True,
                "bookings_enabled": True,
                "reporting_enabled": True,
                "ai_features_enabled": True,
                "beta_smart_pricing": False
            }
        }
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/memberships/feature-flags",
            json=new_flags,
            headers=master_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        print("✓ Updated feature flags")


# ═══════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════

class TestAuditLog:
    """GET /api/master-admin/memberships/audit"""

    def test_audit_log_structure(self, master_headers):
        """Audit log returns entries ordered by 'at' desc."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/audit", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "audit" in data
        assert isinstance(data["audit"], list)

        # Validate ordering (most recent first)
        if len(data["audit"]) >= 2:
            for i in range(len(data["audit"]) - 1):
                assert data["audit"][i]["at"] >= data["audit"][i + 1]["at"], "Audit log not ordered by 'at' desc"

        # Validate entry structure if any exist
        if data["audit"]:
            entry = data["audit"][0]
            required_fields = ["id", "at", "by", "action", "target_type", "target_id"]
            for field in required_fields:
                assert field in entry, f"Missing audit field: {field}"

        print(f"✓ Audit log: {len(data['audit'])} entries, ordered by 'at' desc")

    def test_audit_log_limit(self, master_headers):
        """Audit log respects limit parameter."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/audit?limit=5", headers=master_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["audit"]) <= 5
        print(f"✓ Audit log with limit=5 returned {len(data['audit'])} entries")


# ═══════════════════════════════════════════════════════════════════
# AUTH: 403 FOR NON-MASTER-ADMIN
# ═══════════════════════════════════════════════════════════════════

class TestAuthGate:
    """All endpoints must return 403 for non-master-admin users."""

    endpoints = [
        ("GET", "/api/master-admin/memberships/overview"),
        ("GET", "/api/master-admin/memberships/organizations"),
        ("GET", "/api/master-admin/memberships/templates/plans"),
        ("GET", "/api/master-admin/memberships/booking-rules"),
        ("GET", "/api/master-admin/memberships/tiers"),
        ("GET", "/api/master-admin/memberships/revenue"),
        ("GET", "/api/master-admin/memberships/engagement"),
        ("GET", "/api/master-admin/memberships/instructors"),
        ("GET", "/api/master-admin/memberships/ai-insights"),
        ("GET", "/api/master-admin/memberships/feature-flags"),
        ("GET", "/api/master-admin/memberships/audit"),
    ]

    @pytest.mark.parametrize("method,endpoint", endpoints)
    def test_403_for_non_admin(self, non_admin_headers, method, endpoint):
        """Non-master-admin users get 403."""
        if method == "GET":
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=non_admin_headers)
        else:
            resp = requests.post(f"{BASE_URL}{endpoint}", json={}, headers=non_admin_headers)

        assert resp.status_code == 403, f"Expected 403 for {endpoint}, got {resp.status_code}"
        print(f"✓ 403 returned for non-admin on {method} {endpoint}")


# ═══════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════

class TestCleanup:
    """Cleanup any test data created during tests."""

    def test_cleanup_test_templates(self, master_headers):
        """Delete any TEST_ prefixed templates."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/memberships/templates/plans", headers=master_headers)
        if resp.status_code != 200:
            return

        templates = resp.json().get("templates", [])
        deleted = 0
        for tpl in templates:
            if tpl.get("name", "").startswith("TEST_"):
                del_resp = requests.delete(
                    f"{BASE_URL}/api/master-admin/memberships/templates/plans/{tpl['id']}",
                    headers=master_headers
                )
                if del_resp.status_code == 200:
                    deleted += 1

        print(f"✓ Cleanup: deleted {deleted} TEST_ prefixed templates")
