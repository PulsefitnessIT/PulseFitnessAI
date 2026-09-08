"""Attendance Spine — the single source of truth for daily attendance.

This is the foundation of the unified Staff Portal / Attendance / Timesheet /
Payroll programme. The design principle is ENTER ONCE → USE EVERYWHERE: an
approved leave request, a clock punch, a training booking or a bank holiday all
resolve into ONE authoritative record per employee per day.

Everything else (timesheet, manager attendance board, payroll) reads these
records — nobody re-keys "HOL" in three places.

Collections (all NEW — nothing existing is duplicated)
------------------------------------------------------
- ``attendance_daily``          one row per (org, staff_id, date) — the truth
- ``attendance_patterns``       reusable working patterns (Mon-Fri, shift, etc.)
- ``attendance_work_profiles``  per-staff payroll/pattern extension of the
                                existing ``staff_members`` record (references it,
                                never copies identity)
- ``attendance_bank_holidays``  cached gov.uk bank-holiday calendar per division

Base employee identity, contracted hours, department and manager continue to
live on ``staff_members`` — this module only *extends* it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.staffing import (
    _clean,
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
    _role,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── Status vocabulary ─────────────────────────
# Canonical statuses, each mapped to the legacy spreadsheet code so the old
# Attendance Request / Timesheet worlds keep working during migration.
ATTENDANCE_STATUSES: dict[str, dict] = {
    "working":          {"legacy": "IN",   "label": "Working",              "paid": True,  "color": "#16a34a"},
    "holiday":          {"legacy": "HOL",  "label": "Holiday",              "paid": True,  "color": "#2563eb"},
    "bank_holiday":     {"legacy": "BH",   "label": "Bank Holiday",         "paid": True,  "color": "#7c3aed"},
    "sick":             {"legacy": "SICK", "label": "Sick",                 "paid": True,  "color": "#dc2626"},
    "comp":             {"legacy": "COMP", "label": "Comp / TOIL",          "paid": True,  "color": "#0891b2"},
    "off":              {"legacy": "OFF",  "label": "Scheduled Off",        "paid": False, "color": "#94a3b8"},
    "unpaid_leave":     {"legacy": "UNP",  "label": "Unpaid Leave",         "paid": False, "color": "#b45309"},
    "training":         {"legacy": "TRN",  "label": "Training",             "paid": True,  "color": "#9333ea"},
    "business_travel":  {"legacy": "TRV",  "label": "Business Travel",      "paid": True,  "color": "#0d9488"},
    "wfh":              {"legacy": "WFH",  "label": "Working From Home",    "paid": True,  "color": "#15803d"},
    "other_authorised": {"legacy": "OAL",  "label": "Other Authorised",     "paid": True,  "color": "#4f46e5"},
    "family_leave":     {"legacy": "FAM",  "label": "Family Leave",         "paid": True,  "color": "#db2777"},
    "not_confirmed":    {"legacy": "",     "label": "Not Confirmed",        "paid": False, "color": "#f59e0b"},
}

# Existing leave types (staffing.VALID_LEAVE_TYPE) → canonical attendance status.
LEAVE_TYPE_TO_STATUS = {
    "holiday": "holiday",
    "sick": "sick",
    "unpaid": "unpaid_leave",
    "training": "training",
    "other": "other_authorised",
}

# gov.uk divisions for bank holidays.
BANK_HOLIDAY_REGIONS = {"england-and-wales", "scotland", "northern-ireland"}
DEFAULT_REGION = "england-and-wales"

# Mon=0 … Sun=6
DEFAULT_WORKING_DAYS = [0, 1, 2, 3, 4]
DEFAULT_DAY_START = "09:00"
DEFAULT_DAY_FINISH = "17:00"
DEFAULT_BREAK_MIN = 30

_INDEXES_READY = False


# ───────────────────────── Small helpers ─────────────────────────

async def _ensure_indexes() -> None:
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    try:
        await db.attendance_daily.create_index(
            [("organization_id", 1), ("staff_id", 1), ("date", 1)], unique=True,
        )
        await db.attendance_daily.create_index([("organization_id", 1), ("date", 1)])
        await db.attendance_patterns.create_index([("organization_id", 1)])
        await db.attendance_work_profiles.create_index(
            [("organization_id", 1), ("staff_id", 1)], unique=True,
        )
        await db.attendance_bank_holidays.create_index(
            [("division", 1), ("year", 1)], unique=True,
        )
    except Exception as e:  # pragma: no cover — index race on boot
        logger.warning("attendance index setup: %s", e)
    _INDEXES_READY = True


def _today() -> str:
    return date.today().isoformat()


def _date_range(start: str, end: str) -> list[str]:
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except Exception:
        return []
    if e < s:
        return []
    out, cur = [], s
    while cur <= e:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _hm_to_minutes(hm: str | None) -> int | None:
    if not hm or ":" not in str(hm):
        return None
    try:
        h, m = str(hm).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _status_meta(status: str) -> dict:
    return ATTENDANCE_STATUSES.get(status, ATTENDANCE_STATUSES["not_confirmed"])


# ───────────────────────── Work profile ─────────────────────────

async def _resolve_profile(org_id: str, staff: dict) -> dict:
    """Merge the base staff_members record with its attendance extension.

    Base identity/hours/department/manager stay on staff_members; the
    attendance profile only adds payroll + working-pattern metadata.
    """
    extra = await db.attendance_work_profiles.find_one(
        {"organization_id": org_id, "staff_id": staff["id"]}, {"_id": 0},
    ) or {}
    weekly = staff.get("hours_per_week") or staff.get("weekly_hours")
    working_days = extra.get("working_days") or DEFAULT_WORKING_DAYS
    std_daily = extra.get("standard_daily_hours")
    if std_daily is None and weekly and working_days:
        std_daily = round(float(weekly) / max(1, len(working_days)), 2)
    return {
        "staff_id": staff["id"],
        "full_name": staff.get("full_name"),
        "department": staff.get("department"),
        "manager": staff.get("manager"),
        "contract_type": staff.get("contract_type"),
        "standard_weekly_hours": weekly,
        "standard_daily_hours": std_daily,
        "working_days": working_days,
        "working_pattern_id": extra.get("working_pattern_id"),
        "payroll_number": extra.get("payroll_number"),
        "job_title": extra.get("job_title") or staff.get("primary_role"),
        "payroll_frequency": extra.get("payroll_frequency") or "monthly",
        "overtime_eligibility": extra.get("overtime_eligibility", False),
        "overtime_rule": extra.get("overtime_rule") or "manager_approval",
        "break_rule_minutes": extra.get("break_rule_minutes", DEFAULT_BREAK_MIN),
        "bank_holiday_region": extra.get("bank_holiday_region") or DEFAULT_REGION,
        "time_entry_method": extra.get("time_entry_method") or "daily_timesheet",
        "employment_status": extra.get("employment_status") or "active",
        "start_date": extra.get("start_date"),
        "end_date": extra.get("end_date"),
        "normal_location": extra.get("normal_location"),
        "region": extra.get("region"),
        "atlas_ref": extra.get("atlas_ref"),
        "payroll_ref": extra.get("payroll_ref"),
    }


async def _pattern_for(org_id: str, profile: dict) -> dict:
    """Return an effective working pattern (explicit doc or implicit default)."""
    pid = profile.get("working_pattern_id")
    if pid:
        doc = await db.attendance_patterns.find_one(
            {"organization_id": org_id, "id": pid}, {"_id": 0},
        )
        if doc:
            return doc
    # Implicit pattern from working_days + standard daily hours.
    std_daily = profile.get("standard_daily_hours") or 7.5
    days = []
    for dow in range(7):
        working = dow in (profile.get("working_days") or DEFAULT_WORKING_DAYS)
        days.append({
            "dow": dow,
            "working": working,
            "start": DEFAULT_DAY_START if working else None,
            "finish": DEFAULT_DAY_FINISH if working else None,
            "break_minutes": profile.get("break_rule_minutes", DEFAULT_BREAK_MIN) if working else 0,
            "expected_hours": std_daily if working else 0,
        })
    return {"id": None, "name": "Default (from profile)", "type": "standard", "days": days}


def _expected_for_date(pattern: dict, date_iso: str) -> dict:
    dow = date.fromisoformat(date_iso).weekday()
    day = next((d for d in (pattern.get("days") or []) if int(d.get("dow", -1)) == dow), None)
    if not day or not day.get("working"):
        return {"expected_status": "off", "start": None, "finish": None,
                "break_minutes": 0, "expected_hours": 0}
    start = day.get("start") or DEFAULT_DAY_START
    finish = day.get("finish") or DEFAULT_DAY_FINISH
    brk = int(day.get("break_minutes") or 0)
    exp_h = day.get("expected_hours")
    if exp_h is None:
        sm, fm = _hm_to_minutes(start), _hm_to_minutes(finish)
        exp_h = round(((fm - sm) - brk) / 60.0, 2) if (sm is not None and fm is not None) else 7.5
    return {"expected_status": "working", "start": start, "finish": finish,
            "break_minutes": brk, "expected_hours": round(float(exp_h), 2)}


# ───────────────────────── Bank holidays (gov.uk) ─────────────────────────

async def _bank_holiday_dates(division: str, year: int) -> set[str]:
    division = division if division in BANK_HOLIDAY_REGIONS else DEFAULT_REGION
    cached = await db.attendance_bank_holidays.find_one(
        {"division": division, "year": year}, {"_id": 0},
    )
    if cached and cached.get("dates"):
        return set(cached["dates"])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://www.gov.uk/bank-holidays.json")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("bank-holiday fetch failed: %s", e)
        return set()
    # Cache every division/year we can see in one pass.
    for div, block in data.items():
        events = block.get("events", [])
        by_year: dict[int, list] = {}
        for ev in events:
            try:
                yr = int(str(ev.get("date", ""))[:4])
            except Exception:
                continue
            by_year.setdefault(yr, []).append({"date": ev.get("date"), "title": ev.get("title")})
        for yr, evs in by_year.items():
            await db.attendance_bank_holidays.update_one(
                {"division": div, "year": yr},
                {"$set": {"division": div, "year": yr, "dates": [e["date"] for e in evs],
                          "events": evs, "fetched_at": _now().isoformat()}},
                upsert=True,
            )
    again = await db.attendance_bank_holidays.find_one(
        {"division": division, "year": year}, {"_id": 0},
    )
    return set((again or {}).get("dates") or [])


# ───────────────────────── Clock actuals ─────────────────────────

async def _day_actuals_from_clock(org_id: str, staff_id: str, date_iso: str) -> dict | None:
    """Aggregate clock events on a calendar day into start/finish/break/worked."""
    win_start = f"{date_iso}T00:00:00"
    win_end = f"{date_iso}T23:59:59.999999"
    events = await db.staff_clock_events.find(
        {"organization_id": org_id, "staff_id": staff_id,
         "occurred_at": {"$gte": win_start, "$lte": win_end}},
        {"_id": 0},
    ).sort("occurred_at", 1).to_list(200)
    if not events:
        return None
    ins = [e for e in events if e.get("kind") == "clock_in"]
    outs = [e for e in events if e.get("kind") == "clock_out"]
    if not ins:
        return None
    start = ins[0]["occurred_at"]
    finish = outs[-1]["occurred_at"] if outs else None
    break_min = 0
    bs = None
    for e in events:
        if e.get("kind") == "break_start":
            bs = e.get("occurred_at")
        elif e.get("kind") == "break_end" and bs:
            try:
                break_min += int((datetime.fromisoformat(e["occurred_at"]) - datetime.fromisoformat(bs)).total_seconds() / 60)
            except Exception:
                pass
            bs = None
    worked = None
    if finish:
        try:
            worked = max(0.0, (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds() / 3600.0 - break_min / 60.0)
        except Exception:
            worked = None
    return {
        "start": start[11:16] if len(start) >= 16 else None,
        "finish": finish[11:16] if finish and len(finish) >= 16 else None,
        "break_minutes": break_min,
        "worked_hours": round(worked, 2) if worked is not None else None,
        "complete": finish is not None,
    }


async def _approved_leave_for(org_id: str, staff_id: str, date_iso: str) -> dict | None:
    rows = await db.staff_leave_requests.find(
        {"organization_id": org_id, "staff_id": staff_id, "status": "approved",
         "start_date": {"$lte": date_iso}},
        {"_id": 0},
    ).sort("start_date", -1).to_list(50)
    for r in rows:
        end = r.get("end_date") or ""
        if not end or end >= date_iso:  # open-ended (e.g. ongoing sick) covers forward
            return r
    return None


# ───────────────────────── The engine ─────────────────────────

async def recompute_day(org_id: str, staff_id: str, date_iso: str,
                        actor: str | None = None) -> dict:
    """Resolve ONE authoritative daily record for a staff member.

    Priority: manager correction > approved leave/absence > bank holiday >
    scheduled off > clock actuals (working) > not-confirmed.
    """
    await _ensure_indexes()
    staff = await db.staff_members.find_one(
        {"organization_id": org_id, "id": staff_id}, {"_id": 0},
    )
    if not staff:
        raise HTTPException(404, "staff not found")
    profile = await _resolve_profile(org_id, staff)
    pattern = await _pattern_for(org_id, profile)
    expected = _expected_for_date(pattern, date_iso)
    existing = await db.attendance_daily.find_one(
        {"organization_id": org_id, "staff_id": staff_id, "date": date_iso}, {"_id": 0},
    )

    actuals = await _day_actuals_from_clock(org_id, staff_id, date_iso)

    # Manager override wins for the *status*, but we still refresh derived data.
    if existing and existing.get("manual_override"):
        status = existing["actual_status"]
        source = "manager_correction"
        leave_id = existing.get("leave_event_id")
    else:
        leave = await _approved_leave_for(org_id, staff_id, date_iso)
        year = int(date_iso[:4])
        bh = await _bank_holiday_dates(profile["bank_holiday_region"], year)
        leave_id = None
        if leave:
            status = LEAVE_TYPE_TO_STATUS.get(leave.get("leave_type", ""), "other_authorised")
            source = "leave_approval"
            leave_id = leave.get("id")
        elif date_iso in bh and expected["expected_status"] == "working":
            status = "bank_holiday"
            source = "bank_holiday_calendar"
        elif expected["expected_status"] == "off":
            status = "off"
            source = "working_pattern"
        elif actuals:
            status = "working"
            source = "employee_time_entry"
        elif (existing or {}).get("employee_entry"):
            status = "working"
            source = "employee_time_entry"
        else:
            status = "not_confirmed"
            source = "working_pattern"

    meta = _status_meta(status)
    # Hours model.
    start = finish = None
    break_min = 0
    raw_worked = 0.0
    regular = 0.0
    overtime_raw = 0.0
    paid_leave_hours = 0.0
    if status == "working":
        # Prefer a COMPLETE clock day; otherwise the employee's typed entry;
        # otherwise a partial (mid-shift) clock punch.
        complete_clock = actuals if (actuals and actuals.get("complete")) else None
        ent = complete_clock or (existing or {}).get("employee_entry") or actuals
        if ent:
            start, finish, break_min = ent.get("start"), ent.get("finish"), ent.get("break_minutes") or 0
            raw_worked = ent.get("worked_hours")
            if raw_worked is None:
                sm, fm = _hm_to_minutes(start), _hm_to_minutes(finish)
                raw_worked = round(max(0.0, (fm - sm - break_min) / 60.0), 2) if (sm is not None and fm is not None) else 0.0
        else:
            start, finish, break_min = expected["start"], expected["finish"], expected["break_minutes"]
        raw_worked = raw_worked or 0.0
        exp_h = expected["expected_hours"] or 0.0
        regular = min(raw_worked, exp_h) if raw_worked else exp_h
        if raw_worked and raw_worked > exp_h:
            overtime_raw = round(raw_worked - exp_h, 2)
    elif status == "not_confirmed":
        pass
    elif status == "off":
        pass
    elif status == "unpaid_leave":
        pass
    elif meta["paid"]:
        paid_leave_hours = expected["expected_hours"] or profile.get("standard_daily_hours") or 0.0
        regular = paid_leave_hours

    doc = {
        "organization_id": org_id,
        "staff_id": staff_id,
        "date": date_iso,
        "expected_status": expected["expected_status"],
        "actual_status": status,
        "status_code": meta["legacy"],
        "source": source,
        "start_time": start,
        "finish_time": finish,
        "break_minutes": break_min,
        "expected_hours": expected["expected_hours"],
        "raw_worked_hours": round(raw_worked, 2),
        "regular_hours": round(regular, 2),
        "overtime_raw_hours": round(overtime_raw, 2),
        "approved_overtime_hours": (existing or {}).get("approved_overtime_hours", 0.0),
        "paid_leave_hours": round(paid_leave_hours, 2),
        "leave_event_id": leave_id,
        "employee_entry": (existing or {}).get("employee_entry"),
        "manual_override": (existing or {}).get("manual_override", False),
        "updated_at": _now().isoformat(),
    }
    if existing:
        doc["id"] = existing["id"]
        doc["created_at"] = existing.get("created_at")
        doc["history"] = existing.get("history", [])
        await db.attendance_daily.update_one(
            {"organization_id": org_id, "staff_id": staff_id, "date": date_iso},
            {"$set": doc},
        )
    else:
        doc["id"] = str(uuid4())
        doc["created_at"] = _now().isoformat()
        doc["history"] = []
        await db.attendance_daily.insert_one(doc.copy())
    return _clean(doc)


async def apply_leave_to_daily(org_id: str, leave_doc: dict) -> int:
    """Recompute every daily record a leave request touches (approve OR revoke)."""
    if not leave_doc:
        return 0
    start = leave_doc.get("start_date")
    end = leave_doc.get("end_date") or start
    staff_id = leave_doc.get("staff_id")
    if not (start and staff_id):
        return 0
    # Open-ended (no end): mark from start up to today so the board reflects it.
    if not leave_doc.get("end_date"):
        end = max(start, _today())
    n = 0
    for d in _date_range(start, end):
        try:
            await recompute_day(org_id, staff_id, d)
            n += 1
        except Exception as e:
            logger.warning("apply_leave_to_daily %s %s: %s", staff_id, d, e)
    return n


async def set_employee_entry(org_id: str, staff_id: str, date_iso: str,
                             start: str | None, finish: str | None,
                             break_min: int = 0) -> dict:
    """Employee-typed daily times (the 'Daily Timesheet' method — no live clock).

    Stored on the day's record as ``employee_entry`` so recompute_day treats it
    as the working actuals (leave / bank holiday still take precedence)."""
    await _ensure_indexes()
    entry = {"start": start, "finish": finish, "break_minutes": int(break_min or 0)}
    sm, fm = _hm_to_minutes(start), _hm_to_minutes(finish)
    entry["worked_hours"] = round(max(0.0, (fm - sm - int(break_min or 0)) / 60.0), 2) if (sm is not None and fm is not None) else None
    await db.attendance_daily.update_one(
        {"organization_id": org_id, "staff_id": staff_id, "date": date_iso},
        {"$set": {"employee_entry": entry, "organization_id": org_id,
                  "staff_id": staff_id, "date": date_iso},
         "$setOnInsert": {"id": str(uuid4()), "created_at": _now().isoformat(),
                          "history": [], "manual_override": False}},
        upsert=True,
    )
    return await recompute_day(org_id, staff_id, date_iso)



# ───────────────────────── Pattern endpoints ─────────────────────────
class PatternBody(BaseModel):
    name: str
    type: str = "standard"
    days: list[dict] = []


@router.get("/attendance/patterns")
async def list_patterns(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    rows = await db.attendance_patterns.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
    return {"patterns": rows}


@router.post("/attendance/patterns")
async def create_pattern(body: PatternBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    doc = {"id": str(uuid4()), "organization_id": org_id, "created_at": _now().isoformat(),
           "created_by": user.get("email"), **body.dict()}
    await db.attendance_patterns.insert_one(doc.copy())
    return _clean(doc)


@router.put("/attendance/patterns/{pattern_id}")
async def update_pattern(pattern_id: str, body: PatternBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.attendance_patterns.update_one(
        {"id": pattern_id, "organization_id": org_id},
        {"$set": {**body.dict(), "updated_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "pattern not found")
    return await db.attendance_patterns.find_one({"id": pattern_id}, {"_id": 0})


@router.delete("/attendance/patterns/{pattern_id}")
async def delete_pattern(pattern_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await db.attendance_patterns.delete_one({"id": pattern_id, "organization_id": org_id})
    await db.attendance_work_profiles.update_many(
        {"organization_id": org_id, "working_pattern_id": pattern_id},
        {"$set": {"working_pattern_id": None}},
    )
    return {"ok": True}


@router.post("/attendance/patterns/seed-defaults")
async def seed_default_patterns(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    existing = await db.attendance_patterns.count_documents({"organization_id": org_id})
    if existing:
        rows = await db.attendance_patterns.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
        return {"patterns": rows, "created": 0}

    def days(working_set, start, finish, brk, hrs):
        return [{"dow": d, "working": d in working_set,
                 "start": start if d in working_set else None,
                 "finish": finish if d in working_set else None,
                 "break_minutes": brk if d in working_set else 0,
                 "expected_hours": hrs if d in working_set else 0} for d in range(7)]

    presets = [
        {"name": "Standard Office (Mon–Fri 08:30–17:00)", "type": "standard",
         "days": days({0, 1, 2, 3, 4}, "08:30", "17:00", 30, 8.0)},
        {"name": "Part-time (Mon/Wed/Fri)", "type": "part_time",
         "days": days({0, 2, 4}, "09:00", "15:00", 30, 5.5)},
        {"name": "Field Engineer (variable)", "type": "engineer",
         "days": days({0, 1, 2, 3, 4}, "08:00", "16:30", 30, 8.0)},
        {"name": "Flexible (contracted weekly)", "type": "flexible",
         "days": days({0, 1, 2, 3, 4}, "09:00", "17:00", 60, 7.0)},
    ]
    made = []
    for p in presets:
        doc = {"id": str(uuid4()), "organization_id": org_id, "created_at": _now().isoformat(),
               "created_by": user.get("email"), **p}
        await db.attendance_patterns.insert_one(doc.copy())
        made.append(_clean(doc))
    return {"patterns": made, "created": len(made)}


# ───────────────────────── Work-profile endpoints ─────────────────────────

class WorkProfileBody(BaseModel):
    payroll_number: str | None = None
    job_title: str | None = None
    working_pattern_id: str | None = None
    working_days: list[int] | None = None
    standard_daily_hours: float | None = None
    payroll_frequency: str | None = None
    overtime_eligibility: bool | None = None
    overtime_rule: str | None = None
    break_rule_minutes: int | None = None
    bank_holiday_region: str | None = None
    time_entry_method: str | None = None
    employment_status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    normal_location: str | None = None
    region: str | None = None
    atlas_ref: str | None = None
    payroll_ref: str | None = None


@router.get("/attendance/work-profiles")
async def list_work_profiles(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).sort("full_name", 1).to_list(1000)
    out = [await _resolve_profile(org_id, s) for s in staff]
    patterns = await db.attendance_patterns.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
    return {"profiles": out, "patterns": patterns,
            "statuses": ATTENDANCE_STATUSES, "regions": sorted(BANK_HOLIDAY_REGIONS)}


@router.get("/attendance/work-profile/{staff_id}")
async def get_work_profile(staff_id: str, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    if not _is_manager(user):
        mine = await _my_staff_id_async(user, org_id)
        if mine != staff_id:
            raise HTTPException(403, "You can only view your own profile.")
    staff = await db.staff_members.find_one({"organization_id": org_id, "id": staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "staff not found")
    return await _resolve_profile(org_id, staff)


@router.put("/attendance/work-profile/{staff_id}")
async def upsert_work_profile(staff_id: str, body: WorkProfileBody,
                              user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    staff = await db.staff_members.find_one({"organization_id": org_id, "id": staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "staff not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if patch.get("bank_holiday_region") and patch["bank_holiday_region"] not in BANK_HOLIDAY_REGIONS:
        raise HTTPException(400, "invalid bank_holiday_region")
    patch.update({"organization_id": org_id, "staff_id": staff_id,
                  "updated_at": _now().isoformat(), "updated_by": user.get("email")})
    await db.attendance_work_profiles.update_one(
        {"organization_id": org_id, "staff_id": staff_id},
        {"$set": patch, "$setOnInsert": {"created_at": _now().isoformat()}},
        upsert=True,
    )
    return await _resolve_profile(org_id, staff)


# ───────────────────────── Daily record endpoints ─────────────────────────

class RecomputeBody(BaseModel):
    staff_id: str | None = None
    date_from: str
    date_to: str | None = None


@router.post("/attendance/recompute")
async def recompute(body: RecomputeBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    date_to = body.date_to or body.date_from
    dates = _date_range(body.date_from, date_to)
    if not dates:
        raise HTTPException(400, "invalid date range")
    if body.staff_id:
        staff_ids = [body.staff_id]
    else:
        rows = await db.staff_members.find(
            {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0, "id": 1},
        ).to_list(1000)
        staff_ids = [r["id"] for r in rows]
    n = 0
    for sid in staff_ids:
        for d in dates:
            try:
                await recompute_day(org_id, sid, d)
                n += 1
            except Exception:
                pass
    return {"ok": True, "records": n, "staff": len(staff_ids), "days": len(dates)}


@router.get("/attendance/daily")
async def list_daily(staff_id: str = Query(...), date_from: str = Query(...),
                     date_to: str | None = Query(None),
                     user: dict = Depends(get_current_user)):
    org_id = _org(user)
    if not _is_manager(user):
        mine = await _my_staff_id_async(user, org_id)
        if mine != staff_id:
            raise HTTPException(403, "You can only view your own attendance.")
    date_to = date_to or date_from
    rows = await db.attendance_daily.find(
        {"organization_id": org_id, "staff_id": staff_id,
         "date": {"$gte": date_from, "$lte": date_to}}, {"_id": 0},
    ).sort("date", 1).to_list(400)
    return {"records": rows, "statuses": ATTENDANCE_STATUSES}


@router.get("/attendance/me/daily")
async def my_daily(date_from: str = Query(...), date_to: str | None = Query(None),
                   user: dict = Depends(get_current_user)):
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account.")
    date_to = date_to or date_from
    for d in _date_range(date_from, date_to):
        try:
            await recompute_day(org_id, sid, d)
        except Exception:
            pass
    rows = await db.attendance_daily.find(
        {"organization_id": org_id, "staff_id": sid,
         "date": {"$gte": date_from, "$lte": date_to}}, {"_id": 0},
    ).sort("date", 1).to_list(400)
    return {"records": rows, "staff_id": sid, "statuses": ATTENDANCE_STATUSES}


class CorrectionBody(BaseModel):
    actual_status: str
    start_time: str | None = None
    finish_time: str | None = None
    break_minutes: int | None = None
    reason: str


@router.patch("/attendance/daily/{record_id}")
async def correct_daily(record_id: str, body: CorrectionBody,
                        user: dict = Depends(get_current_user)):
    """Manager exception correction — records old/new + who/when/why (§29)."""
    _require_manager(user)
    org_id = _org(user)
    if body.actual_status not in ATTENDANCE_STATUSES:
        raise HTTPException(400, "invalid status")
    if not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required for a correction.")
    rec = await db.attendance_daily.find_one({"id": record_id, "organization_id": org_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "record not found")
    meta = _status_meta(body.actual_status)
    hist = rec.get("history", [])
    hist.append({
        "at": _now().isoformat(), "by": user.get("email"),
        "from_status": rec.get("actual_status"), "to_status": body.actual_status,
        "reason": body.reason.strip(),
    })
    patch = {
        "actual_status": body.actual_status,
        "status_code": meta["legacy"],
        "manual_override": True,
        "source": "manager_correction",
        "history": hist,
        "corrected_by": user.get("email"),
        "corrected_at": _now().isoformat(),
        "correction_reason": body.reason.strip(),
        "updated_at": _now().isoformat(),
    }
    if body.start_time is not None:
        patch["start_time"] = body.start_time
    if body.finish_time is not None:
        patch["finish_time"] = body.finish_time
    if body.break_minutes is not None:
        patch["break_minutes"] = body.break_minutes
    await db.attendance_daily.update_one({"id": record_id, "organization_id": org_id}, {"$set": patch})
    return await db.attendance_daily.find_one({"id": record_id}, {"_id": 0})


@router.post("/attendance/daily/{record_id}/clear-override")
async def clear_override(record_id: str, user: dict = Depends(get_current_user)):
    """Undo a manual correction and let the engine re-derive the day."""
    _require_manager(user)
    org_id = _org(user)
    rec = await db.attendance_daily.find_one({"id": record_id, "organization_id": org_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "record not found")
    await db.attendance_daily.update_one(
        {"id": record_id, "organization_id": org_id}, {"$set": {"manual_override": False}},
    )
    return await recompute_day(org_id, rec["staff_id"], rec["date"])


class ReturnToWorkBody(BaseModel):
    return_date: str
    reason: str | None = None
    fit_to_return: str | None = None      # yes | phased | no
    fit_details: str | None = None
    agreed_actions: str | None = None


@router.post("/attendance/absence/{leave_id}/close")
async def close_absence(leave_id: str, body: ReturnToWorkBody,
                        user: dict = Depends(get_current_user)):
    """Return-to-work (§20/§21) — cap an open-ended sickness at the return date
    so forward SICK marking stops and the days from return onward re-derive."""
    _require_manager(user)
    org_id = _org(user)
    leave = await db.staff_leave_requests.find_one(
        {"organization_id": org_id, "id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "absence not found")
    start = date.fromisoformat(leave["start_date"])
    try:
        rd = date.fromisoformat(body.return_date)
    except Exception:
        raise HTTPException(400, "invalid return_date")
    if rd <= start:
        raise HTTPException(400, "return date must be after the first day of absence")
    new_end = (rd - timedelta(days=1)).isoformat()
    old_end = leave.get("end_date") or _today()
    rtw = {
        "reason": (body.reason or "").strip() or leave.get("reason"),
        "fit_to_return": body.fit_to_return,
        "fit_details": (body.fit_details or "").strip() or None,
        "agreed_actions": (body.agreed_actions or "").strip() or None,
        "interviewer": user.get("email"),
        "completed_at": _now().isoformat(),
    }
    await db.staff_leave_requests.update_one(
        {"organization_id": org_id, "id": leave_id},
        {"$set": {"end_date": new_end, "return_date": body.return_date, "status": "approved",
                  "closed_by": user.get("email"), "closed_at": _now().isoformat(),
                  "rtw_interview": rtw}},
    )
    last = max(date.fromisoformat(old_end), rd, date.today())
    cur = start
    n = 0
    while cur <= last:
        try:
            await recompute_day(org_id, leave["staff_id"], cur.isoformat())
            n += 1
        except Exception:
            pass
        cur += timedelta(days=1)
    return {"ok": True, "sick_through": new_end, "return_date": body.return_date, "recomputed": n}


# ───────────────────────── Attendance board (§26/§27) ─────────────────────────

@router.get("/attendance/board")
async def attendance_board(date_iso: str = Query(None, alias="date"),
                           user: dict = Depends(get_current_user)):
    """Exception-based 'Today's Attendance' — the Attendance Request replacement."""
    _require_manager(user)
    org_id = _org(user)
    day = date_iso or _today()
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).sort("full_name", 1).to_list(1000)
    rows = []
    counts: dict[str, int] = {}
    for s in staff:
        rec = await recompute_day(org_id, s["id"], day)
        counts[rec["actual_status"]] = counts.get(rec["actual_status"], 0) + 1
        meta = _status_meta(rec["actual_status"])
        rows.append({
            "staff_id": s["id"],
            "full_name": s.get("full_name"),
            "department": s.get("department"),
            "record_id": rec["id"],
            "status": rec["actual_status"],
            "status_label": meta["label"],
            "status_code": rec["status_code"],
            "color": meta["color"],
            "start_time": rec.get("start_time"),
            "finish_time": rec.get("finish_time"),
            "expected_hours": rec.get("expected_hours"),
            "regular_hours": rec.get("regular_hours"),
            "source": rec.get("source"),
            "manual_override": rec.get("manual_override", False),
            "leave_event_id": rec.get("leave_event_id"),
            "is_exception": rec["actual_status"] == "not_confirmed",
        })
    expected_working = sum(1 for r in rows if r["status"] in ("working", "not_confirmed"))
    confirmed = counts.get("working", 0)
    exceptions = counts.get("not_confirmed", 0)
    return {
        "date": day,
        "rows": rows,
        "counts": counts,
        "summary": {
            "total": len(rows),
            "expected_working": expected_working,
            "confirmed": confirmed,
            "holiday": counts.get("holiday", 0),
            "sick": counts.get("sick", 0),
            "off": counts.get("off", 0),
            "bank_holiday": counts.get("bank_holiday", 0),
            "exceptions": exceptions,
        },
        "statuses": ATTENDANCE_STATUSES,
    }


@router.get("/attendance/bank-holidays")
async def get_bank_holidays(region: str = Query(DEFAULT_REGION),
                            year: int = Query(None),
                            user: dict = Depends(get_current_user)):
    yr = year or date.today().year
    dates = await _bank_holiday_dates(region, yr)
    doc = await db.attendance_bank_holidays.find_one(
        {"division": region if region in BANK_HOLIDAY_REGIONS else DEFAULT_REGION, "year": yr},
        {"_id": 0},
    )
    return {"region": region, "year": yr, "dates": sorted(dates),
            "events": (doc or {}).get("events", [])}


# ───────────────────────── Pay-period aggregation ─────────────────────────
# Categories credited as paid leave, grouped for payroll.
async def period_summary(org_id: str, staff_id: str, start: str, end: str,
                         recompute: bool = True) -> dict:
    """Aggregate the spine daily records for one employee across a pay period.

    This is the payroll read model — every figure traces back to daily records
    (the single source of truth), never re-keyed."""
    if recompute:
        cur = date.fromisoformat(start)
        stop = min(date.fromisoformat(end), date.today())
        while cur <= stop:
            try:
                await recompute_day(org_id, staff_id, cur.isoformat())
            except Exception:
                pass
            cur += timedelta(days=1)
    rows = await db.attendance_daily.find(
        {"organization_id": org_id, "staff_id": staff_id,
         "date": {"$gte": start, "$lte": end}}, {"_id": 0},
    ).to_list(60)
    today = _today()

    def paid(status):
        return round(sum(r.get("paid_leave_hours") or 0 for r in rows if r.get("actual_status") == status), 2)

    worked = round(sum(r.get("raw_worked_hours") or 0 for r in rows if r.get("actual_status") == "working"), 2)
    regular = round(sum(r.get("regular_hours") or 0 for r in rows if r.get("actual_status") == "working"), 2)
    ot_raw = round(sum(r.get("overtime_raw_hours") or 0 for r in rows), 2)
    ot_appr = round(sum(r.get("approved_overtime_hours") or 0 for r in rows), 2)
    expected = round(sum(r.get("expected_hours") or 0 for r in rows if r.get("expected_status") == "working"), 2)
    pt = round(sum(((r.get("categories") or {}).get("pt") or 0) for r in rows), 2)
    classes = round(sum(((r.get("categories") or {}).get("classes") or 0) for r in rows), 2)
    return {
        "worked": worked, "regular": regular, "expected": expected,
        "overtime_raw": ot_raw, "overtime_approved": ot_appr,
        "holiday": paid("holiday"), "sick": paid("sick"),
        "bank_holiday": paid("bank_holiday"), "comp": paid("comp"),
        "training": paid("training"),
        "other_leave": round(paid("other_authorised") + paid("family_leave")
                             + paid("business_travel") + paid("wfh"), 2),
        "unpaid_days": sum(1 for r in rows if r.get("actual_status") == "unpaid_leave"),
        "missing": sum(1 for r in rows if r.get("actual_status") == "not_confirmed" and r["date"] < today),
        "expected_days": sum(1 for r in rows if r.get("expected_status") == "working"),
        "present_days": sum(1 for r in rows if r.get("actual_status") == "working"),
        "pt": pt, "classes": classes, "days": len(rows),
    }
