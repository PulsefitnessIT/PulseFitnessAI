"""
Help Centre Brand Separation & Factual Fixes Tests — Iteration 202

Tests:
1. SPACING FIX: Verified via frontend Playwright (pt-24 on hero)
2. BRAND SEPARATION: Pulse users see "Pulse Fitness", no "GymAxis"
3. GYMAXIS BRAND INTACT: Admin users see "GymAxis"
4. ROTA GUIDE REMOVED: staff-rota-basics returns 404
5. CATEGORY RELABELED: Staff category is now "Staff Access"
6. FACTUAL CONTENT FIXES: crm-company-setup and mkt-brand-kit updated
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
PULSE_USER = {"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"}
ADMIN_USER = {"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}


@pytest.fixture(scope="module")
def pulse_token():
    """Get auth token for Pulse operator (lee.somers)"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=PULSE_USER)
    if resp.status_code != 200:
        pytest.skip(f"Pulse login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for Master Admin"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestBrandSeparationPulseUser:
    """Test that Pulse users see 'Pulse Fitness' branding, NOT 'GymAxis'"""

    def test_categories_returns_pulse_brand(self, pulse_token):
        """GET /api/help/categories should return brand.name='Pulse Fitness' for Pulse user"""
        resp = requests.get(
            f"{BASE_URL}/api/help/categories",
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "brand" in data
        assert data["brand"]["id"] == "pulse"
        assert data["brand"]["name"] == "Pulse Fitness"
        assert data["brand"]["assistant_name"] == "Ask Pulse Fitness"

    def test_guides_list_returns_pulse_brand(self, pulse_token):
        """GET /api/help/guides should return brand.name='Pulse Fitness' for Pulse user"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides",
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["brand"]["name"] == "Pulse Fitness"

    def test_guide_detail_whitelabeled_for_pulse(self, pulse_token):
        """GET /api/help/guides/service-log-fault should have 'Pulse Fitness' in content, NOT 'GymAxis'"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/service-log-fault",
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # Brand should be Pulse
        assert data["brand"]["name"] == "Pulse Fitness"

        # Content should NOT contain 'GymAxis'
        content_blob = str(data)
        gymaxis_count = content_blob.lower().count("gymaxis")
        pulse_count = content_blob.lower().count("pulse fitness")

        assert gymaxis_count == 0, f"Found {gymaxis_count} 'GymAxis' mentions in guide content for Pulse user"
        assert pulse_count > 0, "Expected 'Pulse Fitness' mentions in guide content"

    def test_search_results_whitelabeled_for_pulse(self, pulse_token):
        """GET /api/help/search?q=fault should return results with 'Pulse Fitness', NOT 'GymAxis'"""
        resp = requests.get(
            f"{BASE_URL}/api/help/search",
            params={"q": "fault"},
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["brand"]["name"] == "Pulse Fitness"

        # Check results don't contain GymAxis
        results_blob = str(data.get("results", []))
        assert "gymaxis" not in results_blob.lower(), "Search results should not contain 'GymAxis' for Pulse user"

    def test_ai_assistant_whitelabeled_for_pulse(self, pulse_token):
        """POST /api/help/ask should return answer with 'Pulse Fitness', NOT 'GymAxis'"""
        resp = requests.post(
            f"{BASE_URL}/api/help/ask",
            json={"question": "How do I log a fault?", "current_module": "operations"},
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # Brand should be Pulse
        assert data["brand"]["name"] == "Pulse Fitness"

        # Answer should NOT contain 'GymAxis'
        answer = data.get("answer", "")
        assert "gymaxis" not in answer.lower(), f"AI answer should not contain 'GymAxis' for Pulse user. Got: {answer}"


class TestBrandIntactForAdmin:
    """Test that Admin users still see 'GymAxis' branding"""

    def test_categories_returns_gymaxis_brand(self, admin_token):
        """GET /api/help/categories should return brand.name='GymAxis' for admin"""
        resp = requests.get(
            f"{BASE_URL}/api/help/categories",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["brand"]["id"] == "gymaxis"
        assert data["brand"]["name"] == "GymAxis"
        assert data["brand"]["assistant_name"] == "Ask GymAxis"

    def test_guides_list_returns_gymaxis_brand(self, admin_token):
        """GET /api/help/guides should return brand.name='GymAxis' for admin"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["brand"]["name"] == "GymAxis"

    def test_guide_detail_has_gymaxis_for_admin(self, admin_token):
        """GET /api/help/guides/service-log-fault should have 'GymAxis' in content for admin"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/service-log-fault",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # Brand should be GymAxis
        assert data["brand"]["name"] == "GymAxis"

        # Content should contain 'GymAxis' (original branding)
        content_blob = str(data)
        gymaxis_count = content_blob.lower().count("gymaxis")
        assert gymaxis_count > 0, "Expected 'GymAxis' mentions in guide content for admin"


class TestRotaGuideRemoved:
    """Test that staff-rota-basics guide is removed"""

    def test_rota_guide_returns_404(self, admin_token):
        """GET /api/help/guides/staff-rota-basics should return 404"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/staff-rota-basics",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404 for staff-rota-basics, got {resp.status_code}"

    def test_staff_category_has_only_one_guide(self, admin_token):
        """GET /api/help/guides?category=staff should return only 1 guide (staff-gym-floor-login)"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides",
            params={"category": "staff"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        guides = data.get("guides", [])

        # Should have exactly 1 guide
        assert len(guides) == 1, f"Expected 1 guide in staff category, got {len(guides)}: {[g['id'] for g in guides]}"
        assert guides[0]["id"] == "staff-gym-floor-login"

    def test_search_rota_returns_zero_matches(self, admin_token):
        """GET /api/help/search?q=rota should return zero matches"""
        resp = requests.get(
            f"{BASE_URL}/api/help/search",
            params={"q": "rota"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", [])
        assert len(results) == 0, f"Expected 0 results for 'rota' search, got {len(results)}: {[r['id'] for r in results]}"


class TestCategoryRelabeled:
    """Test that staff category is now 'Staff Access' (not 'Staff & Rota')"""

    def test_staff_category_label(self, admin_token):
        """GET /api/help/categories should have staff category with label='Staff Access'"""
        resp = requests.get(
            f"{BASE_URL}/api/help/categories",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        categories = data.get("categories", [])

        staff_cat = next((c for c in categories if c["id"] == "staff"), None)
        assert staff_cat is not None, "Staff category not found"
        assert staff_cat["label"] == "Staff Access", f"Expected 'Staff Access', got '{staff_cat['label']}'"
        assert staff_cat["blurb"] == "Gym Floor kiosk and staff roles.", f"Unexpected blurb: {staff_cat['blurb']}"


class TestFactualContentFixes:
    """Test that guide content has been updated to be factual"""

    def test_crm_company_setup_no_ai_auto_recognition(self, admin_token):
        """GET /api/help/guides/crm-company-setup should NOT mention 'AI auto-recognition'"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/crm-company-setup",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # Check steps don't mention AI auto-recognition
        steps = data.get("steps", [])
        steps_blob = str(steps).lower()
        assert "ai auto-recognition" not in steps_blob, "crm-company-setup should not mention 'AI auto-recognition'"
        assert "ai-recognised" not in steps_blob, "crm-company-setup should not mention 'AI-recognised'"

    def test_mkt_brand_kit_no_preset_list(self, admin_token):
        """GET /api/help/guides/mkt-brand-kit should say 'Describe your brand voice' not preset list"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/mkt-brand-kit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # Check steps for brand voice description
        steps = data.get("steps", [])
        steps_blob = str(steps)

        # Should have "Describe your brand voice" or similar
        assert "describe" in steps_blob.lower() or "brand voice" in steps_blob.lower(), \
            "mkt-brand-kit should mention describing brand voice"

        # Should NOT have the old preset list (Warm/Bold/Expert/Playful)
        assert "warm/bold/expert/playful" not in steps_blob.lower(), \
            "mkt-brand-kit should not have old preset list"


class TestSetupChecklistNoBranding:
    """Test that Setup Checklist doesn't expose brand names inappropriately"""

    def test_setup_checklist_items_no_gymaxis_for_pulse(self, pulse_token):
        """GET /api/help/setup-checklist should not have 'GymAxis' in item labels for Pulse user"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {pulse_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()

        items = data.get("items", [])
        items_blob = str(items).lower()

        # Item labels should not contain 'GymAxis' for Pulse users
        # Note: The checklist items are generic (e.g., "Add your first piece of equipment")
        # so they shouldn't have brand names anyway
        assert "gymaxis" not in items_blob, "Setup checklist items should not contain 'GymAxis' for Pulse user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
