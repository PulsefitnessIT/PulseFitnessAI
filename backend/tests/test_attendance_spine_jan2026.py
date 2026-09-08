"""Attendance Spine — Phase 1 backend test (Jan 2026).

Covers:
- Working pattern seed-defaults idempotency
- Work profiles listing + PUT persistence + invalid region 400
- Bank holiday cache endpoint (best-effort; env may block gov.uk)
- ENTER-ONCE spine: leave approval fans out to attendance_daily (HOL) and cancel reverts
- Manager correction: manual_override + history, missing reason -> 400, override survives leave revocation
- Attendance board summary + not_confirmed rows
"""
import os
import time
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PW = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PW}, timeout=30)
    assert r.status_code == 200, r.text
    tk = r.json().get("token") or r.json().get("access_token")
    assert tk, r.text
    return tk


@pytest.fixture(scope="module")
def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def owner_staff_id(hdrs):
    r = requests.get(f"{BASE}/api/staffing/staff", headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("staff") or r.json().get("rows") or r.json()
    if isinstance(rows, dict):
        rows = rows.get("staff") or []
    for s in rows:
        if (s.get("email") or "").lower() == OWNER_EMAIL:
            return s["id"]
    raise AssertionError("owner staff record not found")


# ─── Patterns ─────────────────────────────────────────────────────────
def test_seed_default_patterns_idempotent(hdrs):
    r1 = requests.post(f"{BASE}/api/attendance/patterns/seed-defaults", headers=hdrs, timeout=30)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    # Idempotent second call
    r2 = requests.post(f"{BASE}/api/attendance/patterns/seed-defaults", headers=hdrs, timeout=30)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("created", 1) == 0, f"expected created:0 on 2nd call, got {j2}"
    # 4 patterns total
    lr = requests.get(f"{BASE}/api/attendance/patterns", headers=hdrs, timeout=30)
    assert lr.status_code == 200
    pats = lr.json().get("patterns", [])
    assert len(pats) >= 4, f"expected >=4 patterns, got {len(pats)}"


# ─── Work profiles ─────────────────────────────────────────────────────
def test_work_profiles_shape(hdrs):
    r = requests.get(f"{BASE}/api/attendance/work-profiles", headers=hdrs, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "profiles" in j and "patterns" in j and "statuses" in j and "regions" in j
    assert len(j["profiles"]) >= 1
    p0 = j["profiles"][0]
    # Resolved defaults present
    assert "working_days" in p0
    assert "standard_daily_hours" in p0
    assert "bank_holiday_region" in p0


def test_upsert_work_profile_and_invalid_region(hdrs, owner_staff_id):
    payload = {
        "payroll_number": "TEST_PAY_001",
        "bank_holiday_region": "england-and-wales",
        "time_entry_method": "clock",
        "overtime_eligible": True,
    }
    r = requests.put(f"{BASE}/api/attendance/work-profile/{owner_staff_id}",
                     headers=hdrs, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got.get("payroll_number") == "TEST_PAY_001"
    assert got.get("bank_holiday_region") == "england-and-wales"

    # Invalid region -> 400
    r2 = requests.put(f"{BASE}/api/attendance/work-profile/{owner_staff_id}",
                      headers=hdrs, json={"bank_holiday_region": "narnia"}, timeout=30)
    assert r2.status_code == 400, r2.text


# ─── Bank holidays ─────────────────────────────────────────────────────
def test_bank_holidays_best_effort(hdrs):
    r = requests.get(f"{BASE}/api/attendance/bank-holidays",
                     params={"region": "england-and-wales", "year": 2026},
                     headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    dates = j.get("dates") or j.get("events") or j.get("holidays") or []
    if not dates:
        pytest.skip(f"gov.uk network likely blocked; empty dates (env issue not code): {j}")
    assert isinstance(dates, list) and len(dates) > 0


# ─── ENTER-ONCE spine (leave -> attendance_daily) ─────────────────────
def _future_range(days_ahead=14, span=3):
    s = date.today() + timedelta(days=days_ahead)
    e = s + timedelta(days=span - 1)
    return s.isoformat(), e.isoformat()


@pytest.fixture(scope="module")
def leave_dates():
    return _future_range(14, 3)


@pytest.fixture(scope="module")
def created_leave(hdrs, leave_dates):
    start, end = leave_dates
    body = {"leave_type": "holiday", "start_date": start, "end_date": end,
            "reason": "TEST_attendance_spine"}
    r = requests.post(f"{BASE}/api/staffing/leave", headers=hdrs, json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_leave_approval_fans_out_to_daily(hdrs, owner_staff_id, created_leave, leave_dates):
    lid = created_leave["id"]
    r = requests.patch(f"{BASE}/api/staffing/leave/{lid}",
                       headers=hdrs, json={"status": "approved"}, timeout=30)
    assert r.status_code == 200, r.text
    time.sleep(0.5)
    start, end = leave_dates
    dr = requests.get(f"{BASE}/api/attendance/daily",
                      params={"staff_id": owner_staff_id, "date_from": start, "date_to": end},
                      headers=hdrs, timeout=30)
    assert dr.status_code == 200, dr.text
    recs = dr.json()["records"]
    hol_days = [r for r in recs if r.get("actual_status") == "holiday"]
    assert len(hol_days) >= 1, f"expected holiday days, got {recs}"
    for rec in hol_days:
        assert rec.get("status_code") == "HOL"
        assert rec.get("source") == "leave_approval"


def test_manager_correction_missing_reason_400(hdrs, owner_staff_id, leave_dates):
    start, _ = leave_dates
    dr = requests.get(f"{BASE}/api/attendance/daily",
                      params={"staff_id": owner_staff_id, "date_from": start, "date_to": start},
                      headers=hdrs, timeout=30)
    recs = dr.json()["records"]
    assert recs, "no daily record for start date"
    rid = recs[0]["id"]
    r = requests.patch(f"{BASE}/api/attendance/daily/{rid}",
                       headers=hdrs, json={"actual_status": "sick", "reason": "  "}, timeout=30)
    assert r.status_code == 400, r.text


def test_manager_correction_and_persistence_through_cancel(hdrs, owner_staff_id, created_leave, leave_dates):
    start, _ = leave_dates
    dr = requests.get(f"{BASE}/api/attendance/daily",
                      params={"staff_id": owner_staff_id, "date_from": start, "date_to": start},
                      headers=hdrs, timeout=30)
    recs = dr.json()["records"]
    rid = recs[0]["id"]
    prev_status = recs[0].get("actual_status")
    # Apply correction with reason
    r = requests.patch(f"{BASE}/api/attendance/daily/{rid}",
                       headers=hdrs,
                       json={"actual_status": "sick", "reason": "TEST override"}, timeout=30)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got.get("manual_override") is True
    assert got.get("actual_status") == "sick"
    hist = got.get("history") or []
    assert any(h.get("to_status") == "sick" and h.get("from_status") == prev_status for h in hist), hist

    # Cancel leave — override should survive
    lid = created_leave["id"]
    rc = requests.patch(f"{BASE}/api/staffing/leave/{lid}",
                        headers=hdrs, json={"status": "cancelled"}, timeout=30)
    assert rc.status_code == 200
    time.sleep(0.5)
    dr2 = requests.get(f"{BASE}/api/attendance/daily",
                       params={"staff_id": owner_staff_id, "date_from": start, "date_to": start},
                       headers=hdrs, timeout=30)
    rec = dr2.json()["records"][0]
    assert rec.get("actual_status") == "sick", f"override lost: {rec}"
    assert rec.get("manual_override") is True

    # Non-overridden days in the range should revert to not_confirmed
    _, end = leave_dates
    dr3 = requests.get(f"{BASE}/api/attendance/daily",
                       params={"staff_id": owner_staff_id, "date_from": start, "date_to": end},
                       headers=hdrs, timeout=30)
    non_over = [r for r in dr3.json()["records"] if not r.get("manual_override")]
    for r in non_over:
        assert r.get("actual_status") != "holiday", f"expected reverted, got {r}"


# ─── Board ─────────────────────────────────────────────────────────────
def test_attendance_board(hdrs):
    today = date.today().isoformat()
    r = requests.get(f"{BASE}/api/attendance/board", params={"date": today},
                     headers=hdrs, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "rows" in j and "summary" in j
    s = j["summary"]
    for k in ("total", "expected_working", "confirmed", "holiday", "sick", "off", "exceptions"):
        assert k in s, f"summary missing {k}: {s}"
    assert j["rows"], "expected at least 1 row"
    # not_confirmed rows should be flagged is_exception when expected to work
    nc = [r for r in j["rows"] if r.get("status") == "not_confirmed"]
    if nc:
        assert any(r.get("is_exception") for r in nc)


# ─── Cleanup ───────────────────────────────────────────────────────────
def test_cleanup(hdrs, created_leave, owner_staff_id, leave_dates):
    """Best-effort cleanup: remove test leave + payroll number + created daily rows."""
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa

    async def _cleanup():
        org = "iso-demo-org"
        await db.staff_leave_requests.delete_many(
            {"organization_id": org, "reason": "TEST_attendance_spine"})
        start, end = leave_dates
        await db.attendance_daily.delete_many(
            {"organization_id": org, "staff_id": owner_staff_id,
             "date": {"$gte": start, "$lte": end}})
        await db.attendance_work_profiles.update_one(
            {"organization_id": org, "staff_id": owner_staff_id},
            {"$unset": {"payroll_number": ""}})
    asyncio.get_event_loop().run_until_complete(_cleanup())
