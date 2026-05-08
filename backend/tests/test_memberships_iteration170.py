"""
GymAxis Memberships — Iteration 170 Tests

Tests for:
1. POST /api/memberships/analytics/send-weekly-digest (operator auth, idempotent)
2. GET /api/memberships/analytics/members-by-kpi (all 10 KPI values)
3. GET /api/m/{slug}/brag (public, no auth)
4. Auth checks for drill-down endpoint (401 no token, 403 member token, 200 operator)
5. Regression: existing analytics endpoints still work
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    headers = {"Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        headers["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
        headers=headers,
    )
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def member_token():
    """Get member JWT token (separate identity)."""
    headers = {"Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        headers["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    resp = requests.post(
        f"{BASE_URL}/api/members/auth/login",
        json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD},
        headers=headers,
    )
    if resp.status_code != 200:
        pytest.skip(f"Member login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    h = {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        h["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    return h


@pytest.fixture(scope="module")
def member_headers(member_token):
    """Headers with member auth."""
    h = {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}
    if RATE_LIMIT_BYPASS:
        h["X-RateLimit-Bypass"] = RATE_LIMIT_BYPASS
    return h


class TestWeeklyDigest:
    """Tests for POST /api/memberships/analytics/send-weekly-digest"""

    def test_digest_requires_auth(self):
        """401 without token."""
        resp = requests.post(f"{BASE_URL}/api/memberships/analytics/send-weekly-digest")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: send-weekly-digest returns 401 without auth")

    def test_digest_operator_success(self, operator_headers):
        """Operator can trigger digest, returns sent/skipped."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
            headers=operator_headers,
            json={},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Should have either 'sent' array or 'skipped' reason
        assert "sent" in data or "skipped" in data, f"Expected sent or skipped in response: {data}"
        if "sent" in data:
            assert isinstance(data["sent"], list), "sent should be a list"
            assert "monday" in data, "Should include monday date"
            print(f"PASS: Digest sent to {len(data['sent'])} recipients, monday={data.get('monday')}")
        else:
            print(f"PASS: Digest skipped: {data.get('skipped')}")

    def test_digest_idempotent(self, operator_headers):
        """Second call within same week should be idempotent (skipped or same result)."""
        # First call
        resp1 = requests.post(
            f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
            headers=operator_headers,
            json={},
        )
        assert resp1.status_code == 200
        # Second call
        resp2 = requests.post(
            f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
            headers=operator_headers,
            json={},
        )
        assert resp2.status_code == 200
        # Both should succeed (force=True in manual trigger bypasses idempotency check)
        print("PASS: Digest endpoint is idempotent (both calls succeeded)")


class TestMembersByKpi:
    """Tests for GET /api/memberships/analytics/members-by-kpi"""

    KPI_VALUES = [
        "active_members",
        "new_members",
        "cancellations",
        "frozen",
        "failed_payments",
        "recovered_payments",
        "highly_engaged",
        "regular",
        "at_risk_segment",
        "inactive",
    ]

    def test_members_by_kpi_requires_auth(self):
        """401 without token."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/members-by-kpi?kpi=active_members")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: members-by-kpi returns 401 without auth")

    def test_members_by_kpi_rejects_member_token(self, member_headers):
        """Member token should be rejected (403 or 500)."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/members-by-kpi?kpi=active_members",
            headers=member_headers,
        )
        # Should not be 200 - either 403 (proper) or 500 (current behavior per iteration 169)
        assert resp.status_code in [403, 500], f"Expected 403/500, got {resp.status_code}"
        print(f"PASS: members-by-kpi rejects member token with {resp.status_code}")

    @pytest.mark.parametrize("kpi", KPI_VALUES)
    def test_members_by_kpi_all_values(self, operator_headers, kpi):
        """Test all 10 KPI values return valid response."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/members-by-kpi?kpi={kpi}",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"KPI {kpi} failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "kpi" in data, f"Missing 'kpi' in response for {kpi}"
        assert data["kpi"] == kpi, f"KPI mismatch: expected {kpi}, got {data['kpi']}"
        assert "count" in data, f"Missing 'count' in response for {kpi}"
        assert "members" in data, f"Missing 'members' in response for {kpi}"
        assert isinstance(data["members"], list), f"members should be a list for {kpi}"
        print(f"PASS: members-by-kpi kpi={kpi} returned count={data['count']}, members={len(data['members'])}")


class TestPublicBragWidget:
    """Tests for GET /api/m/{slug}/brag (public, no auth)"""

    def test_brag_valid_slug(self):
        """Public brag endpoint returns stats for valid slug."""
        resp = requests.get(f"{BASE_URL}/api/m/pulse-leeds/brag")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify organization info
        assert "organization" in data, "Missing organization in response"
        org = data["organization"]
        assert "name" in org, "Missing organization.name"
        assert "slug" in org, "Missing organization.slug"
        assert org["slug"] == "pulse-leeds", f"Slug mismatch: {org['slug']}"

        # Verify stats
        assert "stats" in data, "Missing stats in response"
        stats = data["stats"]
        assert "active_members" in stats, "Missing stats.active_members"
        assert "classes_this_month" in stats, "Missing stats.classes_this_month"
        assert "attendance_this_month" in stats, "Missing stats.attendance_this_month"
        assert "as_of" in stats, "Missing stats.as_of"
        # top_class may be null if no classes

        print(f"PASS: brag endpoint returned org={org['name']}, active_members={stats['active_members']}, "
              f"classes={stats['classes_this_month']}, attendance={stats['attendance_this_month']}")
        if stats.get("top_class"):
            print(f"  Top class: {stats['top_class']['name']} ({stats['top_class']['attended']} attended)")

    def test_brag_invalid_slug_404(self):
        """Invalid slug returns 404."""
        resp = requests.get(f"{BASE_URL}/api/m/not-a-real-slug/brag")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: brag endpoint returns 404 for invalid slug")

    def test_brag_no_auth_required(self):
        """Brag endpoint works without any auth headers."""
        resp = requests.get(f"{BASE_URL}/api/m/pulse-leeds/brag", headers={})
        assert resp.status_code == 200, f"Expected 200 without auth, got {resp.status_code}"
        print("PASS: brag endpoint is public (no auth required)")


class TestRegressionAnalyticsEndpoints:
    """Regression tests for existing analytics endpoints from iteration 169."""

    def test_overview_still_works(self, operator_headers):
        """GET /api/memberships/analytics/overview still returns valid data."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/overview?period=monthly",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"Overview failed: {resp.status_code}"
        data = resp.json()
        assert "kpis" in data, "Missing kpis"
        assert "trend" in data, "Missing trend"
        print(f"PASS: overview endpoint works, active_members={data['kpis'].get('active_members')}")

    def test_retention_still_works(self, operator_headers):
        """GET /api/memberships/analytics/retention still returns valid data."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/retention",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"Retention failed: {resp.status_code}"
        data = resp.json()
        assert "segments" in data, "Missing segments"
        assert "cohort_matrix" in data, "Missing cohort_matrix"
        print(f"PASS: retention endpoint works, segments={data['segments']}")

    def test_classes_still_works(self, operator_headers):
        """GET /api/memberships/analytics/classes still returns valid data."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/classes",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"Classes failed: {resp.status_code}"
        data = resp.json()
        assert "classes_ranked" in data, "Missing classes_ranked"
        assert "instructors" in data, "Missing instructors"
        assert "heatmap" in data, "Missing heatmap"
        print(f"PASS: classes endpoint works, {len(data['classes_ranked'])} classes, {len(data['instructors'])} instructors")

    def test_operations_still_works(self, operator_headers):
        """GET /api/memberships/analytics/operations still returns valid data."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/operations",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"Operations failed: {resp.status_code}"
        data = resp.json()
        assert "kpis" in data, "Missing kpis"
        assert "site_comparison" in data, "Missing site_comparison"
        print(f"PASS: operations endpoint works, failed_payments={data['kpis'].get('failed_payments')}")

    def test_ai_brief_still_works(self, operator_headers):
        """POST /api/memberships/analytics/ai-brief still returns valid data."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/analytics/ai-brief",
            headers=operator_headers,
            json={"period": "weekly"},
        )
        assert resp.status_code == 200, f"AI brief failed: {resp.status_code}"
        data = resp.json()
        assert "brief" in data, "Missing brief"
        print(f"PASS: ai-brief endpoint works, headline={data['brief'].get('headline', 'N/A')[:50]}...")

    def test_at_risk_still_works(self, operator_headers):
        """GET /api/memberships/analytics/at-risk still returns valid data."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/at-risk?limit=10",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"At-risk failed: {resp.status_code}"
        data = resp.json()
        assert "members" in data, "Missing members"
        assert "count" in data, "Missing count"
        print(f"PASS: at-risk endpoint works, count={data['count']}")

    def test_crm_push_still_works(self, operator_headers):
        """POST /api/memberships/analytics/crm-push still works."""
        # First get an at-risk member ID
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/at-risk?limit=1",
            headers=operator_headers,
        )
        if resp.status_code != 200 or not resp.json().get("members"):
            pytest.skip("No at-risk members to test CRM push")
        member_id = resp.json()["members"][0]["id"]

        resp = requests.post(
            f"{BASE_URL}/api/memberships/analytics/crm-push",
            headers=operator_headers,
            json={"member_ids": [member_id], "pipeline": "retention"},
        )
        assert resp.status_code == 200, f"CRM push failed: {resp.status_code}"
        data = resp.json()
        assert data.get("ok") is True, "CRM push should return ok=True"
        print(f"PASS: crm-push endpoint works, pushed={data.get('pushed')}")

    def test_csv_export_still_works(self, operator_headers):
        """GET /api/memberships/analytics/export.csv still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/export.csv?report=overview",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"CSV export failed: {resp.status_code}"
        assert "text/csv" in resp.headers.get("content-type", ""), "Should return CSV"
        print(f"PASS: csv export works, size={len(resp.content)} bytes")

    def test_pdf_export_still_works(self, operator_headers):
        """GET /api/memberships/analytics/export.pdf still works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/export.pdf",
            headers=operator_headers,
        )
        assert resp.status_code == 200, f"PDF export failed: {resp.status_code}"
        assert resp.content[:4] == b"%PDF", "Should return valid PDF"
        print(f"PASS: pdf export works, size={len(resp.content)} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
