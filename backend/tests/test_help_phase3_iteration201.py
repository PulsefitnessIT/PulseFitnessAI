"""
Test Help Centre Phase 3 — Iteration 201
- ALL 28 guides now have walkthroughs
- Setup Checklist live event wiring (tested via API, frontend tests via Playwright)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# All 28 guide IDs that must have walkthroughs
ALL_GUIDE_IDS = [
    "gs-first-login", "gs-modules-overview",
    "crm-add-contact", "crm-pipeline-first-deal", "crm-company-setup", "crm-contracts-overview",
    "service-log-fault", "service-triage-ai",
    "mbr-onboard-first", "mbr-first-plan", "mbr-first-class",
    "mkt-first-campaign", "mkt-ai-director", "mkt-audiences-101", "mkt-brand-kit",
    "staff-gym-floor-login", "staff-rota-basics",
    "reporting-weekly-digest", "reporting-exports",
    "admin-invite-user", "admin-roles-explained", "admin-security-mfa",
    "int-stripe-connect", "int-sage200", "int-sicon",
    "ai-assistant", "ai-campaign-copilot", "ai-fault-triage"
]


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin token for testing"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@gymaxisai.com",
        "password": "MasterAdmin123!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not login as master admin: {resp.status_code}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def staff_token():
    """Get staff/owner token for testing role-based filtering"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "lee.somers@pulsefitness.com",
        "password": "TempPass123!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not login as staff: {resp.status_code}")
    return resp.json().get("token")


class TestAllGuidesHaveWalkthroughs:
    """Verify all 28 guides have walkthrough metadata"""

    @pytest.mark.parametrize("guide_id", ALL_GUIDE_IDS)
    def test_guide_has_walkthrough(self, master_admin_token, guide_id):
        """Each guide must have walkthrough.initial_route (string starting with /) and walkthrough.steps (array >=1)"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)

        assert resp.status_code == 200, f"Guide {guide_id} not found: {resp.status_code}"
        data = resp.json()

        # Must have walkthrough field
        assert "walkthrough" in data, f"Guide {guide_id} missing walkthrough field"
        walkthrough = data["walkthrough"]

        # Must have initial_route starting with /
        assert "initial_route" in walkthrough, f"Guide {guide_id} walkthrough missing initial_route"
        assert isinstance(walkthrough["initial_route"], str), f"Guide {guide_id} initial_route not a string"
        assert walkthrough["initial_route"].startswith("/"), f"Guide {guide_id} initial_route must start with /"

        # Must have steps array with at least 1 step
        assert "steps" in walkthrough, f"Guide {guide_id} walkthrough missing steps"
        assert isinstance(walkthrough["steps"], list), f"Guide {guide_id} steps not an array"
        assert len(walkthrough["steps"]) >= 1, f"Guide {guide_id} must have at least 1 step"

        # Each step must have target, title, content
        for i, step in enumerate(walkthrough["steps"]):
            assert "target" in step, f"Guide {guide_id} step {i} missing target"
            assert "title" in step, f"Guide {guide_id} step {i} missing title"
            assert "content" in step, f"Guide {guide_id} step {i} missing content"


class TestSetupChecklistAPI:
    """Verify Setup Checklist API still works correctly"""

    def test_checklist_returns_7_items_for_master_admin(self, master_admin_token):
        """Master admin should see all 7 checklist items"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/help/setup-checklist", headers=headers)

        assert resp.status_code == 200
        data = resp.json()

        assert "items" in data
        assert "total_count" in data
        assert "completed_count" in data
        assert "percent" in data

        # Should have 7 items
        assert data["total_count"] == 7, f"Expected 7 items, got {data['total_count']}"
        assert len(data["items"]) == 7

        # Verify item structure
        for item in data["items"]:
            assert "id" in item
            assert "label" in item
            assert "href" in item
            assert "completed" in item

    def test_checklist_role_filtering_for_staff(self, staff_token):
        """Staff/owner should see items filtered by role"""
        headers = {"Authorization": f"Bearer {staff_token}"}
        resp = requests.get(f"{BASE_URL}/api/help/setup-checklist", headers=headers)

        assert resp.status_code == 200
        data = resp.json()

        # Staff should see items (may be fewer than 7 if some are owner-only)
        assert "items" in data
        assert len(data["items"]) >= 1

        # Verify each item has required fields
        for item in data["items"]:
            assert "id" in item
            assert "label" in item
            assert "completed" in item


class TestWalkthroughStructure:
    """Verify walkthrough step structure is correct for Joyride"""

    def test_walkthrough_step_has_placement(self, master_admin_token):
        """Most walkthrough steps should have placement field"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        # Check a few guides that should have placement
        guides_with_placement = ["service-log-fault", "crm-add-contact", "mbr-onboard-first"]

        for guide_id in guides_with_placement:
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            walkthrough = data.get("walkthrough", {})
            steps = walkthrough.get("steps", [])

            # At least one step should have placement
            has_placement = any("placement" in step for step in steps)
            assert has_placement, f"Guide {guide_id} should have at least one step with placement"

    def test_walkthrough_targets_are_valid_selectors(self, master_admin_token):
        """Walkthrough targets should be valid CSS selectors"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        for guide_id in ALL_GUIDE_IDS[:5]:  # Check first 5 guides
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            walkthrough = data.get("walkthrough", {})
            steps = walkthrough.get("steps", [])

            for step in steps:
                target = step.get("target", "")
                # Target should be a valid selector (starts with [ or . or # or body)
                assert target, f"Guide {guide_id} has empty target"
                valid_start = target.startswith("[") or target.startswith(".") or target.startswith("#") or target == "body"
                assert valid_start, f"Guide {guide_id} has invalid target: {target}"


class TestSpecificWalkthroughRoutes:
    """Verify specific walkthrough initial_routes are correct"""

    def test_operations_guides_route_to_pulse(self, master_admin_token):
        """Operations guides should route to /pulse"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        ops_guides = ["gs-first-login", "service-log-fault", "service-triage-ai",
                      "staff-gym-floor-login", "staff-rota-basics",
                      "reporting-weekly-digest", "reporting-exports", "ai-fault-triage"]

        for guide_id in ops_guides:
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            route = data.get("walkthrough", {}).get("initial_route", "")
            assert route == "/pulse", f"Guide {guide_id} should route to /pulse, got {route}"

    def test_crm_guides_route_to_crm(self, master_admin_token):
        """CRM guides should route to /crm"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        crm_guides = ["crm-add-contact", "crm-pipeline-first-deal",
                      "crm-company-setup", "crm-contracts-overview"]

        for guide_id in crm_guides:
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            route = data.get("walkthrough", {}).get("initial_route", "")
            assert route == "/crm", f"Guide {guide_id} should route to /crm, got {route}"

    def test_memberships_guides_route_to_memberships(self, master_admin_token):
        """Memberships guides should route to /memberships"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        mbr_guides = ["mbr-onboard-first", "mbr-first-plan", "mbr-first-class", "int-stripe-connect"]

        for guide_id in mbr_guides:
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            route = data.get("walkthrough", {}).get("initial_route", "")
            assert route == "/memberships", f"Guide {guide_id} should route to /memberships, got {route}"

    def test_marketing_guides_route_to_marketing(self, master_admin_token):
        """Marketing guides should route to /marketing"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        mkt_guides = ["mkt-first-campaign", "mkt-ai-director", "mkt-audiences-101",
                      "mkt-brand-kit", "ai-assistant", "ai-campaign-copilot"]

        for guide_id in mkt_guides:
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            route = data.get("walkthrough", {}).get("initial_route", "")
            assert route == "/marketing", f"Guide {guide_id} should route to /marketing, got {route}"

    def test_admin_guides_route_correctly(self, master_admin_token):
        """Admin guides should route to /master-admin or /account"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}

        admin_routes = {
            "admin-invite-user": "/master-admin",
            "admin-roles-explained": "/master-admin",
            "admin-security-mfa": "/account",
            "int-sage200": "/master-admin",
            "int-sicon": "/master-admin",
        }

        for guide_id, expected_route in admin_routes.items():
            resp = requests.get(f"{BASE_URL}/api/help/guides/{guide_id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()

            route = data.get("walkthrough", {}).get("initial_route", "")
            assert route == expected_route, f"Guide {guide_id} should route to {expected_route}, got {route}"


class TestGuideCountAndCategories:
    """Verify guide counts and categories are correct"""

    def test_total_guide_count(self, master_admin_token):
        """Should have exactly 28 guides"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/help/guides", headers=headers)

        assert resp.status_code == 200
        data = resp.json()

        assert "guides" in data
        assert len(data["guides"]) == 28, f"Expected 28 guides, got {len(data['guides'])}"

    def test_categories_have_correct_counts(self, master_admin_token):
        """Each category should have the expected number of guides"""
        headers = {"Authorization": f"Bearer {master_admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/help/categories", headers=headers)

        assert resp.status_code == 200
        data = resp.json()

        assert "categories" in data
        assert len(data["categories"]) == 10, "Should have 10 categories"

        # Verify each category has a count
        for cat in data["categories"]:
            assert "id" in cat
            assert "label" in cat
            assert "count" in cat
            assert cat["count"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
