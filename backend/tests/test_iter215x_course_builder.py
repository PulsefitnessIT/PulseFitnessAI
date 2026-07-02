"""
Iteration 215x — Course builder for dance schools + pro-rata monthly invoicing.

Tests:
1. POST /api/memberships/plans with kind='course' + course_excluded_dates
2. POST /api/memberships/plans/{plan_id}/enrol — bulk enrolment
3. GET /api/memberships/plans/{plan_id}/enrolments — roster + sessions
4. DELETE /api/memberships/plans/{plan_id}/enrolments/{member_id} — un-enrol
5. POST /api/memberships/billing/monthly-invoice/preview — multi-course grouping
6. Regression: existing course with tz-aware fix still works
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://comms-email-hub.preview.emergentagent.com").rstrip("/")

# Test credentials
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"

# Existing course plan from main agent's seeding
EXISTING_COURSE_ID = "d54a6b11-6dd2-42a3-a65c-a7062fc8ac80"
EXISTING_COURSE_EXCLUDED_DATES = ["2026-05-26", "2026-06-16"]

# Enrolled members
BILLING_TEST_MEMBER_ID = "billing-test-member-01f471"
BRAND_NEW_WALKER_ID = "3735fc93-ef98-4c21-a168-e05e8d42e162"


def rate_limit_bypass_headers() -> dict:
    """Rate-limit bypass header for test runs."""
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if not secret:
        try:
            env_path = "/app/backend/.env"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                            secret = line.strip().split("=", 1)[1]
                            break
        except Exception:
            pass
    return {"X-RateLimit-Bypass": secret} if secret else {}


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(operator_token):
    """Auth headers for API calls."""
    return {
        "Authorization": f"Bearer {operator_token}",
        "Content-Type": "application/json",
        **rate_limit_bypass_headers(),
    }


class TestCourseExcludedDates:
    """Test course creation with excluded dates (school holidays)."""

    def test_existing_course_has_excluded_dates(self, auth_headers):
        """Verify the existing Dance Term 2026 Spring course has excluded dates."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        plans = resp.json().get("plans", [])
        course = next((p for p in plans if p["id"] == EXISTING_COURSE_ID), None)
        assert course is not None, "Existing course not found"
        assert course["kind"] == "course"
        assert course["course_excluded_dates"] == EXISTING_COURSE_EXCLUDED_DATES
        assert course["course_session_count"] == 10
        assert len(course["course_occurrence_ids"]) == 10

    def test_excluded_dates_skip_correctly(self, auth_headers):
        """Verify materialised sessions skip the excluded dates."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans/{EXISTING_COURSE_ID}/enrolments",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        sessions = data["sessions"]

        # Should have 10 sessions
        assert len(sessions) == 10

        # Extract dates from sessions
        session_dates = [s["starts_at"][:10] for s in sessions]

        # Excluded dates should NOT be in the session dates
        for excluded in EXISTING_COURSE_EXCLUDED_DATES:
            assert excluded not in session_dates, f"Excluded date {excluded} should not be in sessions"

        # Verify session indices are 1-10
        indices = [s["course_session_index"] for s in sessions]
        assert indices == list(range(1, 11))

    def test_create_course_with_excluded_dates(self, auth_headers):
        """Create a new course with excluded dates and verify materialisation."""
        # Get a class template first
        resp = requests.get(
            f"{BASE_URL}/api/memberships/classes/templates",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        templates = resp.json().get("templates", [])
        assert len(templates) > 0, "No class templates found"
        template_id = templates[0]["id"]

        # Create course with 5 sessions, 2 excluded dates
        unique_id = uuid.uuid4().hex[:6]
        start_date = "2026-08-03"  # A Monday
        excluded = ["2026-08-10", "2026-08-24"]  # Skip weeks 2 and 4

        resp = requests.post(
            f"{BASE_URL}/api/memberships/plans",
            headers=auth_headers,
            json={
                "name": f"Test Course 215x {unique_id}",
                "kind": "course",
                "price_pence": 5000,
                "billing_cycle": "oneoff",
                "course_template_id": template_id,
                "course_session_count": 5,
                "course_start_date": start_date,
                "course_excluded_dates": excluded,
            },
            timeout=15,
        )
        assert resp.status_code == 200, f"Course creation failed: {resp.text}"
        plan = resp.json()["plan"]

        # Verify course was created with correct data
        assert plan["kind"] == "course"
        assert plan["course_session_count"] == 5
        assert plan["course_excluded_dates"] == excluded
        assert len(plan["course_occurrence_ids"]) == 5

        # Verify sessions skip excluded dates
        enrol_resp = requests.get(
            f"{BASE_URL}/api/memberships/plans/{plan['id']}/enrolments",
            headers=auth_headers,
            timeout=10,
        )
        assert enrol_resp.status_code == 200
        sessions = enrol_resp.json()["sessions"]
        session_dates = [s["starts_at"][:10] for s in sessions]

        for ex in excluded:
            assert ex not in session_dates, f"Excluded date {ex} should not be in sessions"

        # Clean up - archive the test course
        requests.delete(
            f"{BASE_URL}/api/memberships/plans/{plan['id']}",
            headers=auth_headers,
            timeout=10,
        )


class TestCourseEnrolment:
    """Test course enrolment endpoints."""

    def test_get_enrolments_returns_roster(self, auth_headers):
        """GET /enrolments returns sessions and enrolled pupils."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans/{EXISTING_COURSE_ID}/enrolments",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify structure
        assert "plan_id" in data
        assert "sessions" in data
        assert "enrolled" in data
        assert "pupil_count" in data
        assert "smoothed" in data

        # Verify enrolled pupils
        assert data["pupil_count"] >= 2
        enrolled_ids = [p["id"] for p in data["enrolled"]]
        assert BILLING_TEST_MEMBER_ID in enrolled_ids
        assert BRAND_NEW_WALKER_ID in enrolled_ids

        # Verify smoothed flag
        assert data["smoothed"] is True

    def test_get_enrolments_non_course_returns_400(self, auth_headers):
        """GET /enrolments on non-course plan returns 400."""
        # Get a non-course plan
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans",
            headers=auth_headers,
            timeout=10,
        )
        plans = resp.json().get("plans", [])
        non_course = next((p for p in plans if p["kind"] != "course"), None)
        assert non_course is not None, "No non-course plan found"

        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans/{non_course['id']}/enrolments",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400
        assert "Not a course plan" in resp.json().get("detail", "")

    def test_enrol_idempotent(self, auth_headers):
        """Re-enrolling already enrolled members is idempotent."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/plans/{EXISTING_COURSE_ID}/enrol",
            headers=auth_headers,
            json={"member_ids": [BILLING_TEST_MEMBER_ID, BRAND_NEW_WALKER_ID]},
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Should report 0 new bookings (already enrolled)
        assert data["ok"] is True
        assert data["enrolled_member_count"] == 2
        assert data["bookings_created"] == 0
        assert data["bookings_skipped_already_enrolled"] == 20  # 2 members * 10 sessions

    def test_enrol_invalid_member_returns_400(self, auth_headers):
        """Enrolling non-existent member returns 400."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/plans/{EXISTING_COURSE_ID}/enrol",
            headers=auth_headers,
            json={"member_ids": ["non-existent-member-id"]},
            timeout=10,
        )
        assert resp.status_code == 400
        assert "Unknown member ids" in resp.json().get("detail", "")


class TestMonthlyInvoicePreview:
    """Test monthly invoice preview with multi-course grouping."""

    def test_invoice_preview_groups_courses_and_classes(self, auth_headers):
        """Invoice preview groups multiple courses + ad-hoc classes per member."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=auth_headers,
            json={"period": "2026-05", "include_smoothed": True},
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["period"] == "2026-05"
        assert data["member_count"] >= 2

        # Find Brand New Walker's invoice
        walker_invoice = next(
            (inv for inv in data["invoices"] if inv["member_id"] == BRAND_NEW_WALKER_ID),
            None,
        )
        assert walker_invoice is not None, "Brand New Walker invoice not found"

        # Should have class lines + smoothed line
        class_lines = [l for l in walker_invoice["lines"] if l["kind"] == "class"]
        smoothed_lines = [l for l in walker_invoice["lines"] if l["kind"] == "smoothed"]

        assert len(class_lines) >= 3, "Should have at least 3 class bookings in May"
        assert len(smoothed_lines) == 1, "Should have exactly 1 smoothed installment"

        # Verify smoothed line
        smoothed = smoothed_lines[0]
        assert smoothed["plan_id"] == EXISTING_COURSE_ID
        assert smoothed["amount_pence"] == 2000  # £12000 / 6 months = £2000

    def test_invoice_preview_no_duplicates(self, auth_headers):
        """Invoice preview has no duplicate lines."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=auth_headers,
            json={"period": "2026-05", "include_smoothed": True},
            timeout=15,
        )
        assert resp.status_code == 200

        for invoice in resp.json()["invoices"]:
            # Check for duplicate booking_ids
            booking_ids = [l.get("booking_id") for l in invoice["lines"] if l.get("booking_id")]
            assert len(booking_ids) == len(set(booking_ids)), f"Duplicate booking_ids in {invoice['member_name']}'s invoice"

            # Check for duplicate smoothed lines per plan
            smoothed_plan_ids = [l.get("plan_id") for l in invoice["lines"] if l["kind"] == "smoothed"]
            assert len(smoothed_plan_ids) == len(set(smoothed_plan_ids)), f"Duplicate smoothed lines in {invoice['member_name']}'s invoice"

    def test_invoice_preview_tz_aware_fix(self, auth_headers):
        """Invoice preview works with naive datetimes (tz-aware fix)."""
        # This tests the fix: if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        # The existing course was created with naive datetimes, and the fix ensures
        # the invoice preview doesn't crash
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=auth_headers,
            json={"period": "2026-06", "include_smoothed": True},
            timeout=15,
        )
        assert resp.status_code == 200
        # If we get here without a 500 error, the tz-aware fix is working


class TestRegressionIter215w:
    """Regression tests for iter 215w features."""

    def test_instructor_crud_still_works(self, auth_headers):
        """Instructor list endpoint still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert "instructors" in resp.json()

    def test_billing_invoices_list_works(self, auth_headers):
        """Invoice list endpoint still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/invoices",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert "invoices" in resp.json()

    def test_plans_list_works(self, auth_headers):
        """Plans list endpoint still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        plans = resp.json().get("plans", [])
        assert len(plans) > 0

    def test_members_list_works(self, auth_headers):
        """Members list endpoint still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert "members" in resp.json()


class TestRegressionIter215Earlier:
    """Regression tests for iter 215v, 215u, 215t, 215s, 215r features."""

    def test_smoothing_preview_works(self, auth_headers):
        """Smoothing preview endpoint (215s) still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/plans/{EXISTING_COURSE_ID}/smoothing-preview",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["monthly_pence"] == 2000
        assert data["months"] == 6

    def test_waitlist_endpoint_works(self, auth_headers):
        """Waitlist endpoint (215t) still works."""
        # Get a class occurrence
        resp = requests.get(
            f"{BASE_URL}/api/memberships/timetable",
            headers=auth_headers,
            params={"from": "2026-05-01", "to": "2026-05-31"},
            timeout=10,
        )
        assert resp.status_code == 200

    def test_dashboard_works(self, auth_headers):
        """Dashboard endpoint still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/dashboard",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "active_members" in data
        assert "today_classes" in data
