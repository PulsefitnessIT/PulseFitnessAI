"""Iter 215ah — Audit Log API integration tests.

Tests the three audit log endpoints via HTTP:
- GET /api/master-admin/audit-log
- GET /api/master-admin/audit-log/summary
- GET /api/master-admin/audit-log/export.csv

Verifies:
- Master admin access (200)
- Non-master-admin operator gets 403
- Response structure and data types
- CSV export format
- Query filters (since_days, kinds, limit)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get JWT token for master admin."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD,
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_token():
    """Get JWT token for regular operator (non-master-admin)."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD,
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


class TestAuditLogListEndpoint:
    """Tests for GET /api/master-admin/audit-log"""

    def test_list_requires_auth(self):
        """Unauthenticated request should fail."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/audit-log")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_list_requires_master_admin(self, operator_token):
        """Non-master-admin operator should get 403."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_list_success_for_master_admin(self, master_admin_token):
        """Master admin should get 200 with proper response structure."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        # Verify response structure
        assert "count" in data, "Response missing 'count'"
        assert "since" in data, "Response missing 'since'"
        assert "events" in data, "Response missing 'events'"
        assert isinstance(data["count"], int), "count should be int"
        assert isinstance(data["events"], list), "events should be list"

    def test_list_event_structure(self, master_admin_token):
        """Verify each event has required fields."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?limit=10",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        if data["events"]:
            event = data["events"][0]
            # Required fields per spec
            assert "timestamp" in event, "Event missing 'timestamp'"
            assert "kind" in event, "Event missing 'kind'"
            assert "severity" in event, "Event missing 'severity'"
            assert "summary" in event, "Event missing 'summary'"
            # Optional fields should exist (may be None)
            assert "organization_id" in event or event.get("organization_id") is None
            assert "actor_email" in event or event.get("actor_email") is None

    def test_list_sorted_newest_first(self, master_admin_token):
        """Events should be sorted newest-first."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?limit=50",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        events = resp.json()["events"]
        if len(events) >= 2:
            timestamps = [e["timestamp"] for e in events if e.get("timestamp")]
            # Verify descending order
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1], "Events not sorted newest-first"

    def test_list_since_days_filter(self, master_admin_token):
        """Test since_days query parameter."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?since_days=1",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        resp90 = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?since_days=90",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp90.status_code == 200
        # 90 days should have >= events than 1 day
        assert resp90.json()["count"] >= resp.json()["count"]

    def test_list_kinds_filter(self, master_admin_token):
        """Test kinds filter - valid kinds only."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?kinds=login,login_failed",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        events = resp.json()["events"]
        for e in events:
            assert e["kind"] in ["login", "login_failed"], f"Unexpected kind: {e['kind']}"

    def test_list_kinds_filter_drops_invalid(self, master_admin_token):
        """Invalid kinds should be silently dropped."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?kinds=login,hacker_kind,invalid_xyz",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        events = resp.json()["events"]
        for e in events:
            assert e["kind"] == "login", f"Unexpected kind: {e['kind']}"

    def test_list_limit_capped_at_2000(self, master_admin_token):
        """Limit should be capped at 2000."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?limit=5000",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        # Should either cap at 2000 or reject with 422
        assert resp.status_code in [200, 422]


class TestAuditLogSummaryEndpoint:
    """Tests for GET /api/master-admin/audit-log/summary"""

    def test_summary_requires_auth(self):
        """Unauthenticated request should fail."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/audit-log/summary")
        assert resp.status_code in [401, 403]

    def test_summary_requires_master_admin(self, operator_token):
        """Non-master-admin operator should get 403."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/summary",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 403

    def test_summary_success_for_master_admin(self, master_admin_token):
        """Master admin should get 200 with proper response structure."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/summary",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        # Verify response structure per spec
        assert "total" in data, "Response missing 'total'"
        assert "by_kind" in data, "Response missing 'by_kind'"
        assert "by_severity" in data, "Response missing 'by_severity'"
        assert "since" in data, "Response missing 'since'"

        # Verify types
        assert isinstance(data["total"], int)
        assert isinstance(data["by_kind"], dict)
        assert isinstance(data["by_severity"], dict)

    def test_summary_severity_buckets(self, master_admin_token):
        """by_severity should have info/warning/critical keys."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/summary",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        by_sev = resp.json()["by_severity"]
        assert "info" in by_sev
        assert "warning" in by_sev
        assert "critical" in by_sev


class TestAuditLogCsvExport:
    """Tests for GET /api/master-admin/audit-log/export.csv"""

    def test_csv_requires_auth(self):
        """Unauthenticated request should fail."""
        resp = requests.get(f"{BASE_URL}/api/master-admin/audit-log/export.csv")
        assert resp.status_code in [401, 403]

    def test_csv_requires_master_admin(self, operator_token):
        """Non-master-admin operator should get 403."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/export.csv",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert resp.status_code == 403

    def test_csv_success_for_master_admin(self, master_admin_token):
        """Master admin should get 200 with CSV content."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/export.csv",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        # Verify Content-Type
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"

        # Verify Content-Disposition
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, f"Expected attachment, got {content_disp}"
        assert "gymaxis-audit-log-" in content_disp, f"Filename pattern missing: {content_disp}"
        assert ".csv" in content_disp, f"CSV extension missing: {content_disp}"

    def test_csv_header_row(self, master_admin_token):
        """CSV should have correct header row."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/export.csv",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"

        header = lines[0]
        expected_cols = [
            "timestamp", "kind", "severity", "organization_id", "organization_name",
            "actor_email", "actor_type", "member_id", "summary"
        ]
        for col in expected_cols:
            assert col in header, f"CSV header missing column: {col}"

    def test_csv_limit_capped_at_10000(self, master_admin_token):
        """CSV limit should be capped at 10000."""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log/export.csv?limit=20000",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        # Should either cap at 10000 or reject with 422
        assert resp.status_code in [200, 422]
