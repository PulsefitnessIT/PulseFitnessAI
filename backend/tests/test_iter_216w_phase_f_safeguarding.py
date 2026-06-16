"""Phase F — Staff & Safeguarding (DBS / First Aid / Safeguarding expiry tracking,
hourly-rate payroll export, substitute pool).

Tests:
- GET /api/memberships/instructors/substitutes (with ?specialty= / ?discipline= filters)
- GET /api/memberships/instructors/compliance (summary + per-instructor compliance)
- GET /api/memberships/instructors/payroll.csv (date range, CSV format, TOTAL row)
- POST /api/memberships/instructors (new safeguarding/payroll fields round-trip)
- PATCH /api/memberships/instructors/{id} (update safeguarding fields, toggle substitute_available)
- Regression: GET /api/memberships/instructors/performance still returns expected shape
- Regression: GET /api/memberships/instructors/{id} still works (static routes don't shadow dynamic)
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

# Use the operator account with memberships module enabled
OPERATOR_EMAIL = "bob@knockers.com"
OPERATOR_PASSWORD = "Test123!"

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fitness-ai-migrate.preview.emergentagent.com").rstrip("/")


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
                            secret = line.strip().split("=", 1)[1].strip('"').strip("'")
                            break
        except Exception:
            pass
    return {"X-RateLimit-Bypass": secret} if secret else {}


@pytest.fixture(scope="module")
def operator_token():
    """Login as operator (Bob@knockers.com) who has memberships module."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(f"Could not login as operator: {resp.status_code} {resp.text[:200]}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(operator_token):
    """Authorization headers for operator."""
    return {
        "Authorization": f"Bearer {operator_token}",
        "Content-Type": "application/json",
        **rate_limit_bypass_headers(),
    }


class TestPhaseF_Substitutes:
    """GET /api/memberships/instructors/substitutes endpoint tests."""

    def test_substitutes_returns_200(self, auth_headers):
        """Substitutes endpoint returns 200 with expected structure."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/substitutes",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "substitutes" in data, "Response should have 'substitutes' key"
        assert "count" in data, "Response should have 'count' key"
        assert isinstance(data["substitutes"], list), "substitutes should be a list"

    def test_substitutes_have_compliance_object(self, auth_headers):
        """Each substitute row should include a compliance object."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/substitutes",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        # If there are substitutes, check compliance structure
        for sub in data.get("substitutes", []):
            assert "compliance" in sub, f"Substitute {sub.get('id')} missing compliance object"
            comp = sub["compliance"]
            assert "status" in comp, "compliance should have 'status'"
            assert comp["status"] in ("green", "amber", "red", "missing"), f"Invalid status: {comp['status']}"

    def test_substitutes_filter_by_specialty(self, auth_headers):
        """Filter substitutes by ?specialty= parameter."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/substitutes",
            params={"specialty": "yoga"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        # Filter should work even if no matches (returns empty list)
        data = resp.json()
        assert "substitutes" in data

    def test_substitutes_filter_by_discipline(self, auth_headers):
        """Filter substitutes by ?discipline= parameter."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/substitutes",
            params={"discipline": "pilates"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "substitutes" in data


class TestPhaseF_Compliance:
    """GET /api/memberships/instructors/compliance endpoint tests."""

    def test_compliance_returns_200(self, auth_headers):
        """Compliance endpoint returns 200 with expected structure."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/compliance",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "compliance" in data, "Response should have 'compliance' key"
        assert "summary" in data, "Response should have 'summary' key"

    def test_compliance_summary_structure(self, auth_headers):
        """Summary should have green, amber, red, missing, total counts."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/compliance",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        summary = resp.json().get("summary", {})
        for key in ("green", "amber", "red", "missing", "total"):
            assert key in summary, f"Summary missing '{key}' key"
            assert isinstance(summary[key], int), f"summary.{key} should be int"

    def test_compliance_items_have_status(self, auth_headers):
        """Each compliance item should have id, name, compliance object."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/compliance",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        items = resp.json().get("compliance", [])
        for item in items:
            assert "id" in item, "compliance item missing 'id'"
            assert "compliance" in item, "compliance item missing 'compliance' object"
            comp = item["compliance"]
            assert "status" in comp
            assert comp["status"] in ("green", "amber", "red", "missing")


class TestPhaseF_PayrollCSV:
    """GET /api/memberships/instructors/payroll.csv endpoint tests."""

    def test_payroll_csv_returns_200_with_valid_dates(self, auth_headers):
        """Payroll CSV returns 200 with valid date range."""
        today = datetime.now().strftime("%Y-%m-%d")
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/payroll.csv",
            params={"date_from": month_ago, "date_to": today},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        assert "text/csv" in resp.headers.get("Content-Type", ""), "Should return text/csv"

    def test_payroll_csv_has_correct_headers(self, auth_headers):
        """CSV should have expected header row."""
        today = datetime.now().strftime("%Y-%m-%d")
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/payroll.csv",
            params={"date_from": month_ago, "date_to": today},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"
        header = lines[0]
        expected_cols = ["Instructor", "Email", "Classes completed", "Minutes taught", "Hourly rate (GBP)", "Pay (GBP)"]
        for col in expected_cols:
            assert col in header, f"Header missing column: {col}"

    def test_payroll_csv_has_total_row(self, auth_headers):
        """CSV should end with a TOTAL row."""
        today = datetime.now().strftime("%Y-%m-%d")
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/payroll.csv",
            params={"date_from": month_ago, "date_to": today},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        # Last row should start with TOTAL
        last_row = lines[-1]
        assert last_row.startswith("TOTAL"), f"Last row should be TOTAL row, got: {last_row[:50]}"

    def test_payroll_csv_returns_400_for_malformed_dates(self, auth_headers):
        """Payroll CSV returns 400 for malformed date parameters."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/payroll.csv",
            params={"date_from": "invalid-date", "date_to": "also-invalid"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 400, f"Expected 400 for malformed dates, got {resp.status_code}"

    def test_payroll_csv_has_content_disposition(self, auth_headers):
        """CSV response should have Content-Disposition attachment header."""
        today = datetime.now().strftime("%Y-%m-%d")
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/payroll.csv",
            params={"date_from": month_ago, "date_to": today},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        cd = resp.headers.get("Content-Disposition", "")
        assert "attachment" in cd, f"Content-Disposition should be attachment, got: {cd}"
        assert ".csv" in cd, f"Filename should end with .csv, got: {cd}"


class TestPhaseF_InstructorCRUD:
    """POST/PATCH instructor with new safeguarding/payroll fields."""

    @pytest.fixture(scope="class")
    def created_instructor_id(self, auth_headers):
        """Create a test instructor and return its ID. Clean up after tests."""
        # Create instructor with safeguarding fields
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        payload = {
            "name": "TEST_PhaseF_Instructor",
            "email": "test.phasef@example.com",
            "phone": "+447700900123",
            "specialties": ["yoga", "pilates"],
            "dbs_reference": "DBS123456789",
            "dbs_issued_on": today,
            "dbs_expires_on": future,
            "safeguarding_completed_on": today,
            "safeguarding_expires_on": future,
            "first_aid_completed_on": today,
            "first_aid_expires_on": future,
            "hourly_rate_pence": 3500,  # £35.00
            "substitute_available": True,
        }
        resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors",
            json=payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Failed to create instructor: {resp.status_code} {resp.text[:300]}"
        instructor_id = resp.json().get("instructor", {}).get("id")
        assert instructor_id, "Created instructor should have an ID"
        yield instructor_id
        # Cleanup: delete the instructor
        requests.delete(
            f"{BASE_URL}/api/memberships/instructors/{instructor_id}",
            headers=auth_headers,
            timeout=10,
        )

    def test_create_instructor_with_safeguarding_fields(self, auth_headers, created_instructor_id):
        """POST instructor accepts new safeguarding/payroll fields."""
        # Verify the instructor was created (fixture already asserts this)
        assert created_instructor_id is not None

    def test_get_instructor_returns_safeguarding_fields(self, auth_headers, created_instructor_id):
        """GET instructor/{id} returns the safeguarding fields."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/{created_instructor_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        inst = resp.json().get("instructor", {})
        # Check safeguarding fields round-tripped
        assert inst.get("dbs_reference") == "DBS123456789"
        assert inst.get("hourly_rate_pence") == 3500
        assert inst.get("substitute_available") is True
        assert inst.get("dbs_expires_on") is not None
        assert inst.get("safeguarding_expires_on") is not None
        assert inst.get("first_aid_expires_on") is not None

    def test_patch_instructor_safeguarding_fields(self, auth_headers, created_instructor_id):
        """PATCH instructor/{id} updates safeguarding fields."""
        new_future = (datetime.now() + timedelta(days=730)).strftime("%Y-%m-%d")
        patch_payload = {
            "dbs_reference": "DBS987654321",
            "dbs_expires_on": new_future,
            "hourly_rate_pence": 4000,  # £40.00
            "substitute_available": False,
        }
        resp = requests.patch(
            f"{BASE_URL}/api/memberships/instructors/{created_instructor_id}",
            json=patch_payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        inst = resp.json().get("instructor", {})
        assert inst.get("dbs_reference") == "DBS987654321"
        assert inst.get("hourly_rate_pence") == 4000
        assert inst.get("substitute_available") is False

    def test_substitute_available_false_hides_from_substitutes(self, auth_headers, created_instructor_id):
        """Instructor with substitute_available=false should not appear in /substitutes."""
        # First ensure substitute_available is false
        requests.patch(
            f"{BASE_URL}/api/memberships/instructors/{created_instructor_id}",
            json={"substitute_available": False},
            headers=auth_headers,
            timeout=10,
        )
        # Now check substitutes list
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/substitutes",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        subs = resp.json().get("substitutes", [])
        sub_ids = [s.get("id") for s in subs]
        assert created_instructor_id not in sub_ids, "Instructor with substitute_available=false should not be in substitutes"


class TestPhaseF_Regression:
    """Regression tests: existing endpoints still work after Phase F changes."""

    def test_performance_endpoint_still_works(self, auth_headers):
        """GET /api/memberships/instructors/performance returns expected shape."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors/performance",
            params={"days": 30},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        # Performance endpoint should have rows and pay_due_pence in each row
        assert "rows" in data, "Performance response should have 'rows' key"
        assert isinstance(data["rows"], list), "rows should be a list"

    def test_dynamic_instructor_id_route_not_shadowed(self, auth_headers):
        """Static routes (/substitutes, /compliance, /payroll.csv) don't shadow /{instructor_id}."""
        # First create an instructor
        payload = {
            "name": "TEST_RouteShadow_Instructor",
            "email": "test.routeshadow@example.com",
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/instructors",
            json=payload,
            headers=auth_headers,
            timeout=10,
        )
        assert create_resp.status_code == 200, f"Failed to create: {create_resp.status_code}"
        inst_id = create_resp.json().get("instructor", {}).get("id")
        assert inst_id, "Should have instructor ID"

        try:
            # Now GET the instructor by ID - this should NOT 404
            get_resp = requests.get(
                f"{BASE_URL}/api/memberships/instructors/{inst_id}",
                headers=auth_headers,
                timeout=10,
            )
            assert get_resp.status_code == 200, f"GET /{inst_id} should return 200, got {get_resp.status_code}"
            inst = get_resp.json().get("instructor", {})
            assert inst.get("id") == inst_id, "Returned instructor should match requested ID"
            assert inst.get("name") == "TEST_RouteShadow_Instructor"
        finally:
            # Cleanup
            requests.delete(
                f"{BASE_URL}/api/memberships/instructors/{inst_id}",
                headers=auth_headers,
                timeout=10,
            )

    def test_list_instructors_still_works(self, auth_headers):
        """GET /api/memberships/instructors (list) still returns expected structure."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/instructors",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "instructors" in data, "Response should have 'instructors' key"
        assert isinstance(data["instructors"], list), "instructors should be a list"
