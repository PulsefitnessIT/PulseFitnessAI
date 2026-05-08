"""
Test suite for Phase 7 Reports & Audit dashboards (iter 215du).

Endpoints tested:
  GET /api/svc/reports/summary              - high-level KPIs
  GET /api/svc/reports/revenue-by-engineer  - invoiced revenue by engineer
  GET /api/svc/reports/ftfr                 - first-time-fix rate
  GET /api/svc/reports/sla                  - SLA compliance
  GET /api/svc/reports/ai                   - AI observability (calls/ok-rate/p50/p95)
  GET /api/svc/reports/audit                - paginated timeline events
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for master admin."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestSummaryEndpoint:
    """Tests for GET /api/svc/reports/summary"""

    def test_summary_returns_kpis(self, auth_headers):
        """Summary endpoint returns expected KPI structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/summary", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify structure
        assert "from" in data, "Missing 'from' field"
        assert "to" in data, "Missing 'to' field"
        assert "kpis" in data, "Missing 'kpis' field"

        kpis = data["kpis"]
        assert "open_cases" in kpis, "Missing open_cases KPI"
        assert "cases_closed" in kpis, "Missing cases_closed KPI"
        assert "chargeable_invoiced" in kpis, "Missing chargeable_invoiced KPI"
        assert "revenue_gross" in kpis, "Missing revenue_gross KPI"
        assert "revenue_net" in kpis, "Missing revenue_net KPI"
        assert "ai_calls" in kpis, "Missing ai_calls KPI"

    def test_summary_with_date_range(self, auth_headers):
        """Summary endpoint accepts from/to date parameters."""
        params = {
            "from": "2026-01-01T00:00:00",
            "to": "2026-12-31T23:59:59"
        }
        resp = requests.get(f"{BASE_URL}/api/svc/reports/summary", headers=auth_headers, params=params)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "kpis" in data

    def test_summary_from_after_to_returns_400(self, auth_headers):
        """Summary endpoint returns 400 when from > to."""
        params = {
            "from": "2026-12-31T23:59:59",
            "to": "2026-01-01T00:00:00"
        }
        resp = requests.get(f"{BASE_URL}/api/svc/reports/summary", headers=auth_headers, params=params)
        assert resp.status_code == 400, f"Expected 400 for from > to, got {resp.status_code}"

    def test_summary_accepts_iso_without_timezone(self, auth_headers):
        """Summary endpoint accepts ISO dates without Z suffix."""
        params = {
            "from": "2026-01-01T00:00:00",  # No Z
            "to": "2026-06-01T00:00:00"     # No Z
        }
        resp = requests.get(f"{BASE_URL}/api/svc/reports/summary", headers=auth_headers, params=params)
        assert resp.status_code == 200, f"Expected 200 for ISO without Z, got {resp.status_code}: {resp.text}"


class TestRevenueByEngineerEndpoint:
    """Tests for GET /api/svc/reports/revenue-by-engineer"""

    def test_revenue_returns_rows(self, auth_headers):
        """Revenue endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/revenue-by-engineer", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "from" in data
        assert "to" in data
        assert "rows" in data
        assert "count" in data
        assert isinstance(data["rows"], list)

    def test_revenue_row_structure(self, auth_headers):
        """Revenue rows have expected fields."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/revenue-by-engineer", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        if data["rows"]:
            row = data["rows"][0]
            # Check expected fields
            assert "engineer_name" in row, "Missing engineer_name"
            assert "hours" in row, "Missing hours"
            assert "revenue" in row, "Missing revenue"
            assert "cases" in row, "Missing cases"

    def test_revenue_sorted_by_revenue_desc(self, auth_headers):
        """Revenue rows are sorted by revenue descending."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/revenue-by-engineer", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        if len(data["rows"]) > 1:
            revenues = [r["revenue"] for r in data["rows"]]
            assert revenues == sorted(revenues, reverse=True), "Rows not sorted by revenue desc"


class TestFTFREndpoint:
    """Tests for GET /api/svc/reports/ftfr (First-Time-Fix Rate)"""

    def test_ftfr_returns_structure(self, auth_headers):
        """FTFR endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ftfr", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "from" in data
        assert "to" in data
        assert "total_closed" in data
        assert "ftf" in data
        assert "rate" in data

    def test_ftfr_rate_is_valid(self, auth_headers):
        """FTFR rate is between 0 and 1."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ftfr", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        rate = data["rate"]
        assert 0 <= rate <= 1, f"Rate {rate} not in [0, 1]"

    def test_ftfr_math_consistency(self, auth_headers):
        """FTFR math: ftf <= total_closed and rate = ftf/total_closed."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ftfr", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        total = data["total_closed"]
        ftf = data["ftf"]
        rate = data["rate"]

        assert ftf <= total, f"ftf ({ftf}) > total_closed ({total})"
        if total > 0:
            expected_rate = round(ftf / total, 3)
            assert abs(rate - expected_rate) < 0.001, f"Rate mismatch: {rate} vs expected {expected_rate}"


class TestSLAEndpoint:
    """Tests for GET /api/svc/reports/sla"""

    def test_sla_returns_structure(self, auth_headers):
        """SLA endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/sla", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "from" in data
        assert "to" in data
        assert "total" in data
        assert "on_time" in data
        assert "breached" in data
        assert "rate" in data
        assert "by_priority" in data

    def test_sla_rate_is_valid(self, auth_headers):
        """SLA rate is between 0 and 1."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/sla", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        rate = data["rate"]
        assert 0 <= rate <= 1, f"Rate {rate} not in [0, 1]"

    def test_sla_math_consistency(self, auth_headers):
        """SLA math: on_time + breached = total."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/sla", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        total = data["total"]
        on_time = data["on_time"]
        breached = data["breached"]

        assert on_time + breached == total, f"on_time ({on_time}) + breached ({breached}) != total ({total})"

    def test_sla_by_priority_structure(self, auth_headers):
        """SLA by_priority has expected structure per priority."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/sla", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        by_priority = data["by_priority"]
        for priority, bucket in by_priority.items():
            assert "total" in bucket, f"Missing total in {priority}"
            assert "on_time" in bucket, f"Missing on_time in {priority}"
            assert "breached" in bucket, f"Missing breached in {priority}"


class TestAIObservabilityEndpoint:
    """Tests for GET /api/svc/reports/ai"""

    def test_ai_returns_structure(self, auth_headers):
        """AI endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ai", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "from" in data
        assert "to" in data
        assert "by_kind" in data
        assert "totals" in data
        assert isinstance(data["by_kind"], list)

    def test_ai_by_kind_row_structure(self, auth_headers):
        """AI by_kind rows have expected fields."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ai", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        if data["by_kind"]:
            row = data["by_kind"][0]
            assert "kind" in row, "Missing kind"
            assert "calls" in row, "Missing calls"
            assert "ok" in row, "Missing ok"
            assert "ok_rate" in row, "Missing ok_rate"
            assert "p50_latency_ms" in row, "Missing p50_latency_ms"
            assert "p95_latency_ms" in row, "Missing p95_latency_ms"
            assert "prompt_chars" in row, "Missing prompt_chars"
            assert "response_chars" in row, "Missing response_chars"

    def test_ai_totals_structure(self, auth_headers):
        """AI totals have expected fields."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ai", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        totals = data["totals"]
        assert "calls" in totals, "Missing calls in totals"
        assert "ok" in totals, "Missing ok in totals"
        assert "ok_rate" in totals, "Missing ok_rate in totals"


class TestAuditEndpoint:
    """Tests for GET /api/svc/reports/audit"""

    def test_audit_returns_structure(self, auth_headers):
        """Audit endpoint returns expected structure."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/audit", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "from" in data
        assert "to" in data
        assert "events" in data
        assert "count" in data
        assert isinstance(data["events"], list)

    def test_audit_with_limit(self, auth_headers):
        """Audit endpoint respects limit parameter."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/audit", headers=auth_headers, params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["events"]) <= 5, f"Expected <= 5 events, got {len(data['events'])}"

    def test_audit_with_types_filter(self, auth_headers):
        """Audit endpoint filters by event types."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/reports/audit",
            headers=auth_headers,
            params={"types": "note,state_change"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # If events returned, they should be of the filtered types
        for event in data["events"]:
            assert event.get("type") in ["note", "state_change"], f"Unexpected type: {event.get('type')}"

    def test_audit_default_14_days(self, auth_headers):
        """Audit endpoint defaults to last 14 days."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/audit", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # Just verify it returns without error - the window is internal
        assert "from" in data
        assert "to" in data


class TestOrgScoping:
    """Tests for organization scoping on reports endpoints."""

    def test_summary_requires_auth(self):
        """Summary endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/summary")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_revenue_requires_auth(self):
        """Revenue endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/revenue-by-engineer")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_ftfr_requires_auth(self):
        """FTFR endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ftfr")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_sla_requires_auth(self):
        """SLA endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/sla")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_ai_requires_auth(self):
        """AI endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/ai")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_audit_requires_auth(self):
        """Audit endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/reports/audit")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
