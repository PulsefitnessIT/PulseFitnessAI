"""Backend tests: Spreadsheet Migration (§74–§76)
Endpoints:
  POST /api/migration/attendance/preview
  POST /api/migration/attendance/commit
  POST /api/migration/timesheets/preview
  POST /api/migration/timesheets/commit
"""
import os
import uuid
import requests
import pytest

def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    return (v or "").rstrip("/")

BASE = _base()
API = f"{BASE}/api"

ATT_XLSX = "/app/backend/migration_samples/attendance_request.xlsx"
TS_XLSX = "/app/backend/migration_samples/timesheets_2026.xlsx"

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"
ORG_ID = "iso-demo-org"


@pytest.fixture(scope="session")
def auth_headers():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in login: {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def temp_staff(auth_headers):
    """Insert a temp staff row that matches an actual attendance name so commit tests can find a match.
    Cleans up staff + all its legacy_attendance / legacy_timesheet rows afterwards.
    """
    # Insert directly via mongo shell? Use backend admin insert. We'll use the staffing endpoint if present.
    # Fallback: direct pymongo since we're inside container.
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    client = MongoClient(mongo_url)
    db = client[db_name]

    staff_id = f"TEST-migr-{uuid.uuid4().hex[:8]}"
    # Use a name that WILL be in the attendance workbook (previous agent used Craig Fisher)
    full_name = "Craig Fisher"
    doc = {
        "id": staff_id,
        "organization_id": ORG_ID,
        "full_name": full_name,
        "active": True,
        "email": f"{staff_id}@test.local",
    }
    db.staff_members.insert_one(doc)
    yield {"id": staff_id, "full_name": full_name}
    # cleanup
    db.staff_members.delete_one({"id": staff_id})
    db.attendance_daily.delete_many({"organization_id": ORG_ID, "staff_id": staff_id})
    # also nuke any stray legacy rows for this org from our tests
    db.attendance_daily.delete_many({"organization_id": ORG_ID, "source": "legacy_attendance", "staff_id": staff_id})
    client.close()


# ─── attendance preview ─────────────────────────────────────
class TestAttendancePreview:
    def test_preview_returns_expected_shape(self, auth_headers):
        with open(ATT_XLSX, "rb") as f:
            r = requests.post(f"{API}/migration/attendance/preview",
                              files={"file": ("att.xlsx", f)},
                              data={"year": 2026},
                              headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "attendance"
        assert data["rows_parsed"] > 100, f"expected many rows, got {data['rows_parsed']}"
        assert isinstance(data["employees_matched"], list)
        assert isinstance(data["employees_unmatched"], list)
        assert isinstance(data["by_status"], dict)
        # status keys should be canonical, not codes
        for k in data["by_status"]:
            assert k in {"working", "holiday", "bank_holiday", "sick", "comp", "off",
                         "unpaid_leave", "training", "wfh"}, f"bad status: {k}"
        assert data["date_range"]["from"] and data["date_range"]["to"]
        assert isinstance(data["sample"], list) and len(data["sample"]) <= 25

    def test_preview_requires_auth(self):
        with open(ATT_XLSX, "rb") as f:
            r = requests.post(f"{API}/migration/attendance/preview",
                              files={"file": ("att.xlsx", f)})
        assert r.status_code in (401, 403)


# ─── attendance commit (with a temp matched staff) ───────────
class TestAttendanceCommit:
    def test_commit_writes_records_for_matched_staff(self, auth_headers, temp_staff):
        with open(ATT_XLSX, "rb") as f:
            r = requests.post(f"{API}/migration/attendance/commit",
                              files={"file": ("att.xlsx", f)},
                              data={"year": 2026},
                              headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["written"] > 0, f"no records written; result={data}"
        assert "skipped" in data
        assert isinstance(data["unmatched"], list)

        # Verify persistence: check attendance_daily has rows for our staff with legacy source
        from pymongo import MongoClient
        client = MongoClient(os.environ.get("MONGO_URL"))
        db = client[os.environ.get("DB_NAME")]
        rows = list(db.attendance_daily.find(
            {"organization_id": ORG_ID, "staff_id": temp_staff["id"], "source": "legacy_attendance"},
            {"_id": 0}))
        client.close()
        assert len(rows) > 0, "no legacy_attendance rows persisted for temp staff"
        # There should be at least some canonical statuses
        statuses = {r["actual_status"] for r in rows}
        assert statuses.issubset({"working", "holiday", "bank_holiday", "sick", "comp", "off",
                                  "unpaid_leave", "training", "wfh"})
        # manual_override True on all
        assert all(r.get("manual_override") is True for r in rows)


# ─── timesheet preview ──────────────────────────────────────
class TestTimesheetPreview:
    def test_preview_returns_expected_shape(self, auth_headers):
        with open(TS_XLSX, "rb") as f:
            r = requests.post(f"{API}/migration/timesheets/preview",
                              files={"file": ("ts.xlsx", f)},
                              headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "timesheet"
        assert "employee_name" in data
        assert "employee_matched" in data
        assert "days_parsed" in data
        assert "totals" in data and set(data["totals"].keys()) >= {"hours", "pt", "classes"}
        assert "conflicts" in data and isinstance(data["conflicts"], list)


# ─── timesheet commit (should reject when no match) ─────────
class TestTimesheetCommit:
    def test_commit_errors_when_no_employee_match(self, auth_headers):
        # Blank template → employee_name is None → 400
        with open(TS_XLSX, "rb") as f:
            r = requests.post(f"{API}/migration/timesheets/commit",
                              files={"file": ("ts.xlsx", f)},
                              headers=auth_headers)
        assert r.status_code == 400, f"expected 400 for unmatched employee, got {r.status_code}: {r.text}"
        assert "matching employee" in r.text.lower() or "no matching" in r.text.lower()
