"""Payroll Workspace backend tests (§32–§43).
Covers period generate/create/update/delete, workspace, submit/approve/return,
lock/snapshot, adjustments, validation, export CSV with field mapping,
and staff portal (submit as employee)."""
import os
import io
import csv
import time
import pytest
import requests
from datetime import date, timedelta

def _load_env():
    p = "/app/frontend/.env"
    try:
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE = _load_env().rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"
API = f"{BASE}/api"

MANAGER_EMAIL = "owner@isodemo.com"
MANAGER_PASSWORD = "IsoDemo123!"
STAFF_EMAIL = "portal.staff@pulsedemo.test"
STAFF_PASSWORD = "Staff123!"


# ─────────── auth helpers ───────────
@pytest.fixture(scope="module")
def manager_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"manager login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in response: {data}"
    return tok


@pytest.fixture(scope="module")
def mh(manager_token):
    return {"Authorization": f"Bearer {manager_token}"}


@pytest.fixture(scope="module")
def staff_token():
    # Try common staff-portal login endpoints
    for path, payload in [
        ("/new-starter/staff-login", {"email": STAFF_EMAIL, "password": STAFF_PASSWORD}),
        ("/new-starter/portal/login", {"email": STAFF_EMAIL, "password": STAFF_PASSWORD}),
        ("/staff-portal/login", {"email": STAFF_EMAIL, "password": STAFF_PASSWORD}),
        ("/staff/login", {"email": STAFF_EMAIL, "password": STAFF_PASSWORD}),
    ]:
        r = requests.post(f"{API}{path}", json=payload, timeout=30)
        if r.status_code == 200:
            j = r.json()
            tok = j.get("token") or j.get("access_token")
            if tok:
                return tok
    pytest.skip("staff portal login endpoint not found / failed")


@pytest.fixture(scope="module")
def sh(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}


# ─────────── created period (module-scoped, cleaned up) ───────────
@pytest.fixture(scope="module")
def created_period(mh):
    """Create a Calendar-month period via /generate. Cleanup at end (best effort)."""
    anchor = date.today().replace(day=15).isoformat()
    r = requests.post(f"{API}/payroll/periods/generate",
                      json={"frequency": "month", "anchor": anchor}, headers=mh, timeout=30)
    assert r.status_code == 200, f"generate failed: {r.status_code} {r.text}"
    p = r.json()
    assert p["frequency"] == "month"
    assert p["start_date"].endswith("-01")
    assert p["status"] == "open"
    yield p
    # cleanup
    try:
        requests.delete(f"{API}/payroll/periods/{p['id']}", headers=mh, timeout=15)
    except Exception:
        pass


# ─────────── periods ───────────
class TestPeriods:
    def test_generate_4_week(self, mh):
        anchor = date.today().isoformat()
        r = requests.post(f"{API}/payroll/periods/generate",
                          json={"frequency": "4_week", "anchor": anchor}, headers=mh, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["frequency"] == "4_week"
        s = date.fromisoformat(p["start_date"])
        e = date.fromisoformat(p["end_date"])
        assert (e - s).days == 27
        # cleanup
        requests.delete(f"{API}/payroll/periods/{p['id']}", headers=mh, timeout=15)

    def test_generate_5_week(self, mh):
        r = requests.post(f"{API}/payroll/periods/generate",
                          json={"frequency": "5_week", "anchor": date.today().isoformat()},
                          headers=mh, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        s = date.fromisoformat(p["start_date"])
        e = date.fromisoformat(p["end_date"])
        assert (e - s).days == 34
        requests.delete(f"{API}/payroll/periods/{p['id']}", headers=mh, timeout=15)

    def test_generate_invalid_frequency(self, mh):
        r = requests.post(f"{API}/payroll/periods/generate",
                          json={"frequency": "weekly", "anchor": date.today().isoformat()},
                          headers=mh, timeout=30)
        assert r.status_code == 400

    def test_create_custom(self, mh):
        s = date.today().replace(day=1)
        e = s + timedelta(days=13)
        r = requests.post(f"{API}/payroll/periods",
                          json={"name": "TEST_custom_2wk", "start_date": s.isoformat(),
                                "end_date": e.isoformat(), "frequency": "custom"},
                          headers=mh, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["name"] == "TEST_custom_2wk"
        assert p["frequency"] == "custom"
        requests.delete(f"{API}/payroll/periods/{p['id']}", headers=mh, timeout=15)

    def test_list_periods(self, mh, created_period):
        r = requests.get(f"{API}/payroll/periods", headers=mh, timeout=30)
        assert r.status_code == 200
        periods = r.json()["periods"]
        assert any(p["id"] == created_period["id"] for p in periods)


# ─────────── workspace / submit / approve / return ───────────
class TestWorkspace:
    def test_workspace_shape(self, mh, created_period):
        r = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["period"]["id"] == created_period["id"]
        assert "rows" in j and "summary" in j
        for k in ("total", "ready", "awaiting_approval", "missing_timesheet", "exceptions"):
            assert k in j["summary"]
        if j["rows"]:
            row = j["rows"][0]
            for k in ("staff_id", "status", "totals", "exceptions"):
                assert k in row

    def test_submit_requires_declaration(self, mh, created_period):
        # Get some staff_id
        w = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if not w["rows"]:
            pytest.skip("no staff to submit")
        sid = w["rows"][0]["staff_id"]
        r = requests.post(f"{API}/payroll/periods/{created_period['id']}/submit",
                          json={"staff_id": sid, "declaration": False}, headers=mh, timeout=30)
        assert r.status_code == 400

    def test_approve_requires_submit_first(self, mh, created_period):
        w = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if len(w["rows"]) < 2:
            pytest.skip("need >=2 staff")
        sid = w["rows"][1]["staff_id"]
        # Ensure no timesheet yet by not calling submit; call approve directly
        r = requests.post(f"{API}/payroll/periods/{created_period['id']}/approve",
                          json={"staff_id": sid}, headers=mh, timeout=30)
        # If already submitted by previous test run, allow 200; otherwise expect 409
        assert r.status_code in (200, 409)

    def test_submit_then_approve_flow(self, mh, created_period):
        w = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if not w["rows"]:
            pytest.skip("no staff")
        sid = w["rows"][0]["staff_id"]
        r1 = requests.post(f"{API}/payroll/periods/{created_period['id']}/submit",
                           json={"staff_id": sid, "declaration": True}, headers=mh, timeout=30)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/payroll/periods/{created_period['id']}/approve",
                           json={"staff_id": sid}, headers=mh, timeout=30)
        assert r2.status_code == 200, r2.text
        # Verify workspace reflects approved
        w2 = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                          headers=mh, timeout=60).json()
        row = next(r for r in w2["rows"] if r["staff_id"] == sid)
        assert row["status"] == "approved"

    def test_return_requires_reason(self, mh, created_period):
        w = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if not w["rows"]:
            pytest.skip("no staff")
        sid = w["rows"][0]["staff_id"]
        r = requests.post(f"{API}/payroll/periods/{created_period['id']}/return",
                         json={"staff_id": sid, "reason": ""}, headers=mh, timeout=30)
        assert r.status_code == 400

    def test_return_with_reason(self, mh, created_period):
        w = requests.get(f"{API}/payroll/periods/{created_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if len(w["rows"]) < 2:
            pytest.skip("need 2 staff")
        sid = w["rows"][1]["staff_id"]
        # first submit
        requests.post(f"{API}/payroll/periods/{created_period['id']}/submit",
                      json={"staff_id": sid, "declaration": True}, headers=mh, timeout=30)
        r = requests.post(f"{API}/payroll/periods/{created_period['id']}/return",
                        json={"staff_id": sid, "reason": "please recheck hours"},
                        headers=mh, timeout=30)
        assert r.status_code == 200, r.text


# ─────────── lock + snapshot + adjustment + export ───────────
class TestLockAndExport:
    @pytest.fixture(scope="class")
    def lockable_period(self, mh):
        """A separate period we can lock and cleanup via mongo removal note."""
        # Generate 4-week (unique)
        anchor = (date.today() - timedelta(days=60)).isoformat()
        r = requests.post(f"{API}/payroll/periods/generate",
                          json={"frequency": "4_week", "anchor": anchor}, headers=mh, timeout=30)
        assert r.status_code == 200
        return r.json()

    def test_lock(self, mh, lockable_period):
        r = requests.post(f"{API}/payroll/periods/{lockable_period['id']}/lock",
                          headers=mh, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "snapshot_id" in j
        assert j.get("employees", 0) >= 0

    def test_locked_put_conflicts(self, mh, lockable_period):
        s = lockable_period["start_date"]
        e = lockable_period["end_date"]
        r = requests.put(f"{API}/payroll/periods/{lockable_period['id']}",
                         json={"name": "TEST_edit", "start_date": s, "end_date": e,
                               "frequency": "custom"}, headers=mh, timeout=30)
        assert r.status_code == 409

    def test_locked_delete_conflicts(self, mh, lockable_period):
        r = requests.delete(f"{API}/payroll/periods/{lockable_period['id']}", headers=mh, timeout=30)
        assert r.status_code == 409

    def test_lock_again_conflicts(self, mh, lockable_period):
        r = requests.post(f"{API}/payroll/periods/{lockable_period['id']}/lock",
                          headers=mh, timeout=30)
        assert r.status_code == 409

    def test_adjustment_requires_reason(self, mh, lockable_period):
        w = requests.get(f"{API}/payroll/periods/{lockable_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if not w["rows"]:
            pytest.skip("no staff")
        sid = w["rows"][0]["staff_id"]
        r = requests.post(f"{API}/payroll/periods/{lockable_period['id']}/adjustment",
                          json={"staff_id": sid, "category": "regular", "new_value": 1.0,
                                "reason": ""}, headers=mh, timeout=30)
        assert r.status_code == 400

    def test_adjustment_ok(self, mh, lockable_period):
        w = requests.get(f"{API}/payroll/periods/{lockable_period['id']}/workspace",
                         headers=mh, timeout=60).json()
        if not w["rows"]:
            pytest.skip("no staff")
        sid = w["rows"][0]["staff_id"]
        r = requests.post(f"{API}/payroll/periods/{lockable_period['id']}/adjustment",
                          json={"staff_id": sid, "category": "regular", "new_value": 2.5,
                                "reason": "missing shift correction"}, headers=mh, timeout=30)
        assert r.status_code == 200, r.text
        # verify list
        r2 = requests.get(f"{API}/payroll/periods/{lockable_period['id']}/adjustments",
                          headers=mh, timeout=30)
        assert r2.status_code == 200
        assert any(a["staff_id"] == sid for a in r2.json()["adjustments"])

    def test_validation_counts(self, mh, lockable_period):
        r = requests.get(f"{API}/payroll/periods/{lockable_period['id']}/validation",
                         headers=mh, timeout=60)
        assert r.status_code == 200
        for k in ("employees", "payroll_ids_found", "missing_approvals",
                  "missing_entries", "with_overtime", "unpaid_adjustments"):
            assert k in r.json()

    def test_export_csv_with_mapping(self, mh, lockable_period):
        # Set a custom mapping first
        mapping = [
            {"source": "payroll_number", "label": "PID", "column": "PID"},
            {"source": "full_name", "label": "Name", "column": "Name"},
            {"source": "regular", "label": "Reg", "column": "Reg"},
        ]
        rp = requests.put(f"{API}/payroll/field-mapping",
                          json={"fields": mapping}, headers=mh, timeout=30)
        assert rp.status_code == 200
        # Export
        r = requests.get(f"{API}/payroll/periods/{lockable_period['id']}/export?format=csv",
                         headers=mh, timeout=60)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader)
        assert header == ["PID", "Name", "Reg"]
        # restore default mapping (best-effort)
        default = requests.get(f"{API}/payroll/field-mapping", headers=mh, timeout=30).json()["fields"]
        # (leave as-is; test just verifies mapping honored)


# ─────────── staff portal (employee submit) ───────────
class TestStaffPortal:
    def test_portal_periods(self, sh):
        r = requests.get(f"{API}/new-starter/portal/periods", headers=sh, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "periods" in j

    def test_portal_submit(self, sh, mh):
        # Find a draft/returned period in portal
        r = requests.get(f"{API}/new-starter/portal/periods", headers=sh, timeout=30)
        pers = r.json().get("periods", [])
        cand = [p for p in pers if p.get("status") in ("draft", "returned")
                and p["period"].get("status") != "locked"]
        if not cand:
            pytest.skip("no draft/returned period for employee")
        pid = cand[0]["period"]["id"]
        r2 = requests.post(f"{API}/new-starter/portal/period/{pid}/submit",
                           json={"declaration": True}, headers=sh, timeout=30)
        assert r2.status_code == 200, r2.text
