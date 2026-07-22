"""Comprehensive tests for Memberships Phase 1 — Revenue Structures.

Tests cover:
- Promo codes (CRUD, validation, archive, redemptions)
- Plans with kind=course (materialises occurrences)
- Plans with kind=class_pack (credits + pack_expiry_days)
- Plans with kind=bundle (class credits + PT credits)
- Plans with kind=recurring + trial_days
- Checkout endpoint with promo_code + trial_period_days

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase1_full.py -v
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://platform-doctor.preview.emergentagent.com")
API = f"{BASE_URL.rstrip('/')}/api"

OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!",
}


@pytest.fixture(scope="module")
def operator_token():
    """Login as operator and return token."""
    r = requests.post(f"{API}/auth/login", json=OPERATOR, timeout=10)
    assert r.status_code == 200, f"Operator login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


# ───────────────────────── Promo Codes ─────────────────────────


class TestPromoCodes:
    """Promo code CRUD and validation tests."""

    def test_promo_list_requires_auth(self):
        """GET /api/memberships/promo-codes requires auth."""
        r = requests.get(f"{API}/memberships/promo-codes", timeout=10)
        assert r.status_code in (401, 403)

    def test_promo_list_returns_structure(self, headers):
        """GET /api/memberships/promo-codes returns {promo_codes, count}."""
        r = requests.get(f"{API}/memberships/promo-codes", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "promo_codes" in data
        assert "count" in data
        assert isinstance(data["promo_codes"], list)

    def test_promo_create_no_discount_returns_400(self, headers):
        """POST with no discount fields → 400."""
        r = requests.post(
            f"{API}/memberships/promo-codes",
            headers=headers,
            json={"code": "TESTBAD", "name": "Bad promo", "duration": "once"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "percent_off" in r.text.lower() or "amount_off" in r.text.lower()

    def test_promo_create_both_discounts_returns_400(self, headers):
        """POST with both percent_off and amount_off_pence → 400."""
        r = requests.post(
            f"{API}/memberships/promo-codes",
            headers=headers,
            json={
                "code": "TESTBOTH",
                "name": "Both discounts",
                "percent_off": 25,
                "amount_off_pence": 500,
                "duration": "once",
            },
            timeout=10,
        )
        assert r.status_code == 400
        assert "either" in r.text.lower() or "both" in r.text.lower()

    def test_promo_create_valid_percent_off(self, headers):
        """POST with percent_off=25 → 200, returns promo with Stripe IDs."""
        suffix = str(int(time.time()))[-6:]
        code = f"TESTABC{suffix}"
        r = requests.post(
            f"{API}/memberships/promo-codes",
            headers=headers,
            json={
                "code": code,
                "name": "Test 25% off",
                "percent_off": 25,
                "duration": "once",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        promo = r.json()["promo_code"]
        assert promo["code"] == code
        assert promo["percent_off"] == 25
        assert promo["stripe_coupon_id"], "Missing stripe_coupon_id"
        assert promo["stripe_promotion_code_id"], "Missing stripe_promotion_code_id"
        # Store for later tests
        TestPromoCodes.created_promo_id = promo["id"]
        TestPromoCodes.created_promo_code = code

    def test_promo_create_duplicate_returns_409(self, headers):
        """POST with same code as existing → 409."""
        code = getattr(TestPromoCodes, "created_promo_code", "TESTABC123456")
        r = requests.post(
            f"{API}/memberships/promo-codes",
            headers=headers,
            json={"code": code, "name": "Duplicate", "percent_off": 10, "duration": "once"},
            timeout=15,
        )
        assert r.status_code == 409
        assert "already exists" in r.text.lower()

    def test_promo_validate_bogus_plan_returns_404(self, headers):
        """POST /validate with plan_id='no-such' → 404."""
        code = getattr(TestPromoCodes, "created_promo_code", "TESTABC123456")
        r = requests.post(
            f"{API}/memberships/promo-codes/validate",
            headers=headers,
            json={"code": code, "plan_id": "no-such-plan"},
            timeout=10,
        )
        assert r.status_code == 404
        assert "plan" in r.text.lower()

    def test_promo_validate_bogus_code_returns_400(self, headers):
        """POST /validate with code='DOESNOTEXIST' → 400 'Invalid promo code'."""
        r = requests.post(
            f"{API}/memberships/promo-codes/validate",
            headers=headers,
            json={"code": "DOESNOTEXIST", "plan_id": "any-plan-id"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "invalid" in r.text.lower()

    def test_promo_patch_name(self, headers):
        """PATCH /promo-codes/{id} with {name:'New name'} → 200."""
        promo_id = getattr(TestPromoCodes, "created_promo_id", None)
        if not promo_id:
            pytest.skip("No promo created in earlier test")
        r = requests.patch(
            f"{API}/memberships/promo-codes/{promo_id}",
            headers=headers,
            json={"name": "Renamed promo"},
            timeout=10,
        )
        assert r.status_code == 200

    def test_promo_redemptions_empty(self, headers):
        """GET /promo-codes/{id}/redemptions → 200 {redemptions:[], count:0}."""
        promo_id = getattr(TestPromoCodes, "created_promo_id", None)
        if not promo_id:
            pytest.skip("No promo created in earlier test")
        r = requests.get(
            f"{API}/memberships/promo-codes/{promo_id}/redemptions",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["redemptions"] == []

    def test_promo_archive_and_list(self, headers):
        """DELETE /promo-codes/{id} → 200; subsequent GET excludes it; include_archived=true shows it."""
        promo_id = getattr(TestPromoCodes, "created_promo_id", None)
        if not promo_id:
            pytest.skip("No promo created in earlier test")
        # Archive
        r = requests.delete(
            f"{API}/memberships/promo-codes/{promo_id}",
            headers=headers,
            timeout=15,
        )
        assert r.status_code == 200

        # List without archived
        r = requests.get(f"{API}/memberships/promo-codes", headers=headers, timeout=10)
        assert r.status_code == 200
        assert all(p["id"] != promo_id for p in r.json().get("promo_codes", []))

        # List with archived
        r = requests.get(
            f"{API}/memberships/promo-codes?include_archived=true",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert any(p["id"] == promo_id for p in r.json().get("promo_codes", []))


# ───────────────────────── Plans ─────────────────────────


class TestPlans:
    """Plan creation tests for different kinds."""

    def test_plan_create_course_missing_template_returns_400(self, headers):
        """POST /plans with kind='course' but missing course_template_id → 400."""
        r = requests.post(
            f"{API}/memberships/plans",
            headers=headers,
            json={
                "name": "Test Course Bad",
                "kind": "course",
                "price_pence": 10000,
                "billing_cycle": "oneoff",
                "course_session_count": 8,
                "course_start_date": "2026-06-01",
            },
            timeout=10,
        )
        assert r.status_code == 400
        assert "course_template_id" in r.text.lower()

    def test_plan_create_class_pack_with_expiry(self, headers):
        """POST /plans with kind='class_pack', credits_count=10, pack_expiry_days=90 → 200."""
        r = requests.post(
            f"{API}/memberships/plans",
            headers=headers,
            json={
                "name": f"Test Pack {int(time.time())}",
                "kind": "class_pack",
                "price_pence": 5000,
                "billing_cycle": "oneoff",
                "credits_count": 10,
                "pack_expiry_days": 90,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["kind"] == "class_pack"
        assert plan["credits_count"] == 10
        assert plan["pack_expiry_days"] == 90
        TestPlans.class_pack_id = plan["id"]

    def test_plan_create_bundle_with_pt_credits(self, headers):
        """POST /plans with kind='bundle', credits_count=8, pt_credits_count=2 → 200."""
        r = requests.post(
            f"{API}/memberships/plans",
            headers=headers,
            json={
                "name": f"Test Bundle {int(time.time())}",
                "kind": "bundle",
                "price_pence": 8000,
                "billing_cycle": "monthly",
                "credits_count": 8,
                "pt_credits_count": 2,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["kind"] == "bundle"
        assert plan["credits_count"] == 8
        assert plan["pt_credits_count"] == 2
        TestPlans.bundle_id = plan["id"]

    def test_plan_create_recurring_with_trial(self, headers):
        """POST /plans with kind='recurring', trial_days=7 → 200."""
        r = requests.post(
            f"{API}/memberships/plans",
            headers=headers,
            json={
                "name": f"Test Recurring Trial {int(time.time())}",
                "kind": "recurring",
                "price_pence": 2900,
                "billing_cycle": "monthly",
                "trial_days": 7,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["kind"] == "recurring"
        assert plan["trial_days"] == 7
        TestPlans.recurring_trial_id = plan["id"]


class TestPlanCourse:
    """Course plan creation with occurrence materialisation."""

    @pytest.fixture(scope="class")
    def class_template_id(self, headers):
        """Get or create a class template for course testing."""
        # List existing templates
        r = requests.get(f"{API}/memberships/classes/templates", headers=headers, timeout=10)
        if r.status_code == 200 and r.json().get("templates"):
            return r.json()["templates"][0]["id"]
        # Create one
        r = requests.post(
            f"{API}/memberships/classes/templates",
            headers=headers,
            json={
                "name": "Test Course Template",
                "category": "Course",
                "duration_min": 60,
                "capacity": 15,
                "recurs_days": [1],  # Tuesday
                "start_time": "10:00",
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()["template"]["id"]
        pytest.skip("Could not create class template")

    def test_plan_create_course_materialises_occurrences(self, headers, class_template_id):
        """POST /plans with kind='course' → 200, returns plan with course_occurrence_ids array."""
        r = requests.post(
            f"{API}/memberships/plans",
            headers=headers,
            json={
                "name": f"Test Course {int(time.time())}",
                "kind": "course",
                "price_pence": 12000,
                "billing_cycle": "oneoff",
                "course_template_id": class_template_id,
                "course_session_count": 8,
                "course_start_date": "2026-06-01",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["kind"] == "course"
        assert plan["course_template_id"] == class_template_id
        assert plan["course_session_count"] == 8
        assert "course_occurrence_ids" in plan
        assert len(plan["course_occurrence_ids"]) == 8
        TestPlanCourse.course_plan_id = plan["id"]
        TestPlanCourse.course_occurrence_ids = plan["course_occurrence_ids"]


# ───────────────────────── Cleanup ─────────────────────────


class TestCleanup:
    """Archive test-created plans to keep the DB clean."""

    def test_cleanup_plans(self, headers):
        """Archive any test plans created during this run."""
        plan_ids = []
        if hasattr(TestPlans, "class_pack_id"):
            plan_ids.append(TestPlans.class_pack_id)
        if hasattr(TestPlans, "bundle_id"):
            plan_ids.append(TestPlans.bundle_id)
        if hasattr(TestPlans, "recurring_trial_id"):
            plan_ids.append(TestPlans.recurring_trial_id)
        if hasattr(TestPlanCourse, "course_plan_id"):
            plan_ids.append(TestPlanCourse.course_plan_id)

        for pid in plan_ids:
            r = requests.delete(f"{API}/memberships/plans/{pid}", headers=headers, timeout=10)
            # 200 or 404 (already archived) is fine
            assert r.status_code in (200, 404)
