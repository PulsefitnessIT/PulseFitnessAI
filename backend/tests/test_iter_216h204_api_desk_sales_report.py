"""Iter 216h204 — Desk-sales reconciliation report API integration tests.

Tests the actual HTTP endpoints via requests against the live preview.
Uses the creditpack.operator@example.com account which has existing desk sales
from iter h203 testing.

Run: pytest backend/tests/test_iter_216h204_api_desk_sales_report.py -v
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from iter h203
OPERATOR_EMAIL = "creditpack.operator@example.com"
OPERATOR_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def operator_token():
    """Login as the credit-pack-test operator and return JWT."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Could not login as operator: {resp.status_code} {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(operator_token):
    """Return auth headers for API calls."""
    return {"Authorization": f"Bearer {operator_token}"}


class TestDeskSalesReportEndpoint:
    """Tests for GET /api/memberships/reports/desk-sales"""

    def test_no_filters_returns_200_with_correct_shape(self, auth_headers):
        """Default call (no filters) returns 200 with rows[], summary{}, filters{}."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check top-level keys
        assert "rows" in data, "Missing 'rows' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "filters" in data, "Missing 'filters' key"
        
        # Check summary shape
        summary = data["summary"]
        assert "count" in summary, "Missing 'count' in summary"
        assert "total_pence" in summary, "Missing 'total_pence' in summary"
        assert "by_method" in summary, "Missing 'by_method' in summary"
        assert "top_operators" in summary, "Missing 'top_operators' in summary"
        
        print(f"✓ Response shape correct: {len(data['rows'])} rows, total_pence={summary['total_pence']}")

    def test_date_range_filter_returns_filters_in_response(self, auth_headers):
        """Date range filters are echoed back in response.filters."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-05-01", "to": "2026-05-18"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["filters"]["from"] == "2026-05-01"
        assert data["filters"]["to"] == "2026-05-18"
        print("✓ Date filters echoed in response")

    def test_from_after_to_returns_400(self, auth_headers):
        """from > to returns 400 with 'must be ≤' message."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-06-01", "to": "2026-01-01"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "≤" in resp.text or "<=" in resp.text or "must be" in resp.text.lower()
        print("✓ from > to correctly rejected with 400")

    def test_invalid_date_format_returns_400(self, auth_headers):
        """Invalid date format returns 400."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-13-99"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "invalid" in resp.text.lower() or "date" in resp.text.lower()
        print("✓ Invalid date format correctly rejected with 400")

    def test_invalid_method_returns_400(self, auth_headers):
        """method=bitcoin returns 400."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"method": "bitcoin"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ Invalid method 'bitcoin' correctly rejected with 400")

    def test_valid_method_filter_accepted(self, auth_headers):
        """Valid method filter (cash) is accepted."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"method": "cash"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data["filters"]["method"] == "cash"
        print("✓ Valid method filter 'cash' accepted")

    def test_operator_id_filter_accepted(self, auth_headers):
        """operator_id filter is accepted and echoed."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"operator_id": "some-user-id"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data["filters"]["operator_id"] == "some-user-id"
        print("✓ operator_id filter accepted")

    def test_hydration_fields_present_in_rows(self, auth_headers):
        """Rows include hydrated fields: member_name, member_email, plan_name, operator_name, credits_added."""
        # Use a wide date range to find any existing data
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        if len(data["rows"]) > 0:
            row = data["rows"][0]
            # Check hydration fields exist (may be empty string if deleted)
            assert "member_name" in row, "Missing 'member_name' hydration"
            assert "member_email" in row, "Missing 'member_email' hydration"
            assert "plan_name" in row, "Missing 'plan_name' hydration"
            assert "operator_name" in row, "Missing 'operator_name' hydration"
            assert "credits_added" in row, "Missing 'credits_added' hydration"
            print(f"✓ Hydration fields present. First row: member={row['member_name']}, plan={row['plan_name']}")
        else:
            print("⚠ No rows found to verify hydration (empty result)")

    def test_by_method_summary_structure(self, auth_headers):
        """by_method summary has correct structure per method."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        by_method = data["summary"]["by_method"]
        for method, bucket in by_method.items():
            assert "count" in bucket, f"Missing 'count' in by_method[{method}]"
            assert "total_pence" in bucket, f"Missing 'total_pence' in by_method[{method}]"
        print(f"✓ by_method structure correct: {list(by_method.keys())}")

    def test_top_operators_max_5_sorted_by_total(self, auth_headers):
        """top_operators returns max 5 entries sorted by total_pence desc."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales",
            headers=auth_headers,
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        top_ops = data["summary"]["top_operators"]
        assert len(top_ops) <= 5, f"top_operators should be max 5, got {len(top_ops)}"
        
        # Verify sorted by total_pence desc
        if len(top_ops) > 1:
            for i in range(len(top_ops) - 1):
                assert top_ops[i]["total_pence"] >= top_ops[i + 1]["total_pence"], \
                    "top_operators not sorted by total_pence desc"
        
        for op in top_ops:
            assert "operator_id" in op
            assert "operator_name" in op
            assert "count" in op
            assert "total_pence" in op
        
        print(f"✓ top_operators correct: {len(top_ops)} operators")


class TestDeskSalesCSVExport:
    """Tests for GET /api/memberships/reports/desk-sales/export.csv"""

    def test_csv_export_returns_200_with_correct_headers(self, auth_headers):
        """CSV export returns 200 with text/csv content-type and attachment disposition."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales/export.csv",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        # Check content-type
        content_type = resp.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        # Check Content-Disposition
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition.lower(), f"Expected attachment disposition, got {disposition}"
        assert "desk-sales" in disposition, f"Expected 'desk-sales' in filename, got {disposition}"
        
        print(f"✓ CSV headers correct: {content_type}, {disposition}")

    def test_csv_export_has_header_row(self, auth_headers):
        """CSV export starts with header row."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales/export.csv",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"
        
        header = lines[0]
        # Check expected columns
        assert "Date" in header
        assert "Member" in header
        assert "Plan" in header
        assert "Method" in header
        assert "Amount" in header or "GBP" in header
        
        print(f"✓ CSV header row present: {header[:80]}...")

    def test_csv_export_amount_formatted_as_pounds(self, auth_headers):
        """CSV amount column is formatted as £X.XX (2 decimal places)."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/reports/desk-sales/export.csv",
            headers=auth_headers,
            params={"from": "2026-01-01", "to": "2026-12-31"},
        )
        assert resp.status_code == 200
        
        lines = resp.text.strip().split("\n")
        if len(lines) > 1:
            # Parse header to find Amount column index
            import csv
            import io
            reader = csv.reader(io.StringIO(resp.text))
            header = next(reader)
            
            # Find the Amount column
            amount_idx = None
            for i, col in enumerate(header):
                if "amount" in col.lower() or "gbp" in col.lower():
                    amount_idx = i
                    break
            
            if amount_idx is not None:
                data_row = next(reader, None)
                if data_row:
                    amount_val = data_row[amount_idx]
                    # Should be formatted like "50.00" (2 decimal places)
                    assert "." in amount_val, f"Amount should have decimal: {amount_val}"
                    parts = amount_val.split(".")
                    assert len(parts[1]) == 2, f"Amount should have 2 decimal places: {amount_val}"
                    print(f"✓ Amount formatted correctly: {amount_val}")
                else:
                    print("⚠ No data rows to verify amount format")
            else:
                print("⚠ Could not find Amount column in header")
        else:
            print("⚠ No data rows in CSV")


class TestAuthRequirements:
    """Tests for authentication requirements."""

    def test_no_auth_returns_401(self):
        """Request without auth returns 401."""
        resp = requests.get(f"{BASE_URL}/api/memberships/reports/desk-sales")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ No auth correctly rejected")

    def test_csv_no_auth_returns_401(self):
        """CSV export without auth returns 401."""
        resp = requests.get(f"{BASE_URL}/api/memberships/reports/desk-sales/export.csv")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("✓ CSV no auth correctly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
