"""Phase 2 Staff Portal 'My Day' / 'My Time' — backend tests.

Covers /api/new-starter/portal/{my-day, day/timesheet, day/punch,
my-time, report-absence} against the Attendance Spine.
"""
import os
from datetime import date, timedelta

import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

STAFF_EMAIL = "portal.staff@pulsedemo.test"
STAFF_PASSWORD = "Staff123!"


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{API}/new-starter/staff-login",
                      json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"staff-login {r.status_code}: {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def h(staff_token):
    return {"Authorization": f"Bearer {staff_token}",
            "Content-Type": "application/json"}


# ── /my-day ──
def test_my_day_shape(h):
    r = requests.get(f"{API}/new-starter/portal/my-day", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("first_name", "time_entry_method", "record",
              "clock_state", "month", "upcoming_leave", "statuses"):
        assert k in d, f"missing {k}"
    for k in ("recorded", "expected", "overtime", "missing"):
        assert k in d["month"], f"month missing {k}"
    assert d["record"]["date"] == date.today().isoformat()


# ── /day/timesheet ──
def test_day_timesheet_hours_math(h):
    body = {"start": "08:30", "finish": "17:00", "break_minutes": 30}
    r = requests.post(f"{API}/new-starter/portal/day/timesheet",
                      headers=h, json=body, timeout=30)
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["actual_status"] == "working", rec
    # 08:30-17:00 = 8.5h, minus 30m break = 8.0 worked
    assert abs((rec.get("raw_worked_hours") or 0) - 8.0) < 0.01, rec
    reg = rec.get("regular_hours") or 0
    ot = rec.get("overtime_raw_hours") or 0
    assert abs((reg + ot) - 8.0) < 0.05, f"reg+ot != 8.0: {rec}"
    # Expected 7.5h profile → regular capped at 7.5, OT 0.5 (per spec).
    # But allow either 8.0/0.0 (if expected=8) as long as sum matches.
    exp = rec.get("expected_hours") or 0
    if abs(exp - 7.5) < 0.01:
        assert abs(reg - 7.5) < 0.05, rec
        assert abs(ot - 0.5) < 0.05, rec


# ── /my-time ──
def test_my_time_week(h):
    r = requests.get(f"{API}/new-starter/portal/my-time?scope=week",
                     headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scope"] == "week"
    assert "records" in d and isinstance(d["records"], list)
    for k in ("worked", "expected", "overtime", "holiday", "sick", "missing"):
        assert k in d["totals"]


def test_my_time_month(h):
    r = requests.get(f"{API}/new-starter/portal/my-time?scope=month",
                     headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scope"] == "month"


# ── /day/punch ──
def test_punch_invalid_transition(h):
    # Ensure "clock_out while off" -> 409. Use fresh clock_out attempt.
    # First check state; if currently working, clock_out first to reach off.
    md = requests.get(f"{API}/new-starter/portal/my-day", headers=h, timeout=30).json()
    if md.get("clock_state") == "working":
        requests.post(f"{API}/new-starter/portal/day/punch",
                      headers=h, json={"kind": "clock_out"}, timeout=30)
    # Now off, clock_out should 409
    r = requests.post(f"{API}/new-starter/portal/day/punch",
                      headers=h, json={"kind": "clock_out"}, timeout=30)
    assert r.status_code == 409, r.text


# ── /report-absence (sick, closed) ──
def test_report_absence_sick_marks_today(h):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = requests.post(f"{API}/new-starter/portal/report-absence",
                      headers=h,
                      json={"absence_type": "sick", "first_day": today,
                            "expected_return": tomorrow,
                            "note": "TEST_ automated"},
                      timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("days_marked", 0) >= 1

    # verify my-day now reflects sick
    md = requests.get(f"{API}/new-starter/portal/my-day", headers=h, timeout=30).json()
    assert md["record"]["actual_status"] == "sick", md["record"]

    # verify my-time week sick totals >0
    mt = requests.get(f"{API}/new-starter/portal/my-time?scope=week",
                      headers=h, timeout=30).json()
    assert mt["totals"]["sick"] > 0, mt["totals"]
