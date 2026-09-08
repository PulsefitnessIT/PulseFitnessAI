"""Staff Portal (activated employees) + module-access provisioning.

Two audiences share these endpoints:

  • The activated employee, logged into `/staff-portal` with the scoped
    staff JWT (a real `users` row, role `staff`/`recruit`, linked to a
    `staff_members` doc). They reach `/api/new-starter/portal/*` for their
    rota, timesheet, holidays, documents and system-access status.

  • HR + Line Managers, logged into the main app with a platform token,
    reach the provisioning endpoints:
      - HR assigns a Line Manager to an employee
        (`/api/staff-onboarding/managers`, `.../line-manager`).
      - The Line Manager grants that report the org's modules
        (`/api/staffing/access/my-reports`, `.../modules`).

All data reuses the EXISTING collections (`staff_shifts`,
`staff_clock_events`, `staff_timesheets`, `staff_leave_requests`,
`staff_members`, `staff_onboarding_*`). Only `staff_access_provisions`
is new (one doc per provisioned employee).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel

from utils.database import db
from utils.auth import get_current_user, get_current_user_portal
from utils.module_access import org_module_access

router = APIRouter()

HR_ROLES = {"owner", "manager", "master_admin"}
MODULE_LABELS = {
    "operations": "Operations",
    "memberships": "Memberships",
    "marketing": "Marketing",
    "crm": "CRM",
    "service_desk": "Service Desk",
    "inventory": "Inventory & Distribution",
}
BOLT_ON = ("memberships", "marketing", "crm")
# Per-user capability grants — NOT org module_access keys. These are additive
# rights stamped straight onto the user record (users.is_service_desk /
# users.is_inventory) and are assignable to any staff account regardless of the
# org's plan, so a line manager can put a team member on the Service Desk /
# Inventory app from Operations → Staffing → Team access.
USER_GRANTS = ("service_desk", "inventory")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _clean(d: dict | None) -> dict | None:
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if k != "_id"}


def _is_manager(user: dict) -> bool:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    return (user.get("role") or "").lower() in {"owner", "manager", "master_admin"}


def _require_hr(user: dict) -> None:
    if not _is_manager(user):
        raise HTTPException(403, "HR / managers only")


def _org(user: dict) -> str:
    oid = user.get("organization_id")
    if not oid:
        raise HTTPException(400, "No organization context")
    return oid


async def _portal_staff(user: dict) -> dict:
    """Resolve the staff_members doc for a logged-in staff-portal user."""
    staff = await db.staff_members.find_one({"user_id": user.get("id")})
    if not staff:
        raise HTTPException(404, "No staff record for this account.")
    return staff


async def _case_for(staff_id: str) -> dict | None:
    return await db.staff_onboarding_cases.find_one({"staff_id": staff_id})


async def _department(staff: dict) -> str:
    dept = (staff.get("department") or "").strip()
    if dept:
        return dept
    case = await _case_for(staff["id"])
    if case:
        return ((case.get("employment_proposal") or {}).get("department") or "").strip()
    return ""


async def _org_available_modules(org_id: str) -> list[str]:
    org = await db.organizations.find_one({"id": org_id})
    access = org_module_access(org)
    org_mods = [k for k in MODULE_LABELS if k not in USER_GRANTS and access.get(k)]
    # Service Desk + Inventory are per-user capability grants, not org plan
    # modules — always offer them so managers can assign them to staff.
    return org_mods + list(USER_GRANTS)


# ══════════════════════════ EMPLOYEE PORTAL ══════════════════════════

@router.get("/new-starter/portal/rota")
async def portal_rota(days: int = Query(21, ge=1, le=90), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    end = (date.today() + timedelta(days=days)).isoformat()
    rows = await db.staff_shifts.find(
        {"organization_id": org, "staff_id": staff["id"],
         "date": {"$gte": _today(), "$lte": end},
         "status": {"$nin": ["cancelled"]}},
        {"_id": 0},
    ).sort([("date", 1), ("start_time", 1)]).to_list(300)
    return {"shifts": rows, "staff_id": staff["id"]}


@router.get("/new-starter/portal/timesheet")
async def portal_timesheet(week_start: str = Query(...), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    from routes.staffing_clock import _ensure_timesheet_doc, _week_bounds  # lazy — avoid import cycle
    ws, we = _week_bounds(week_start)
    ts = await _ensure_timesheet_doc(staff["organization_id"], staff["id"], ws, we)
    return _clean(ts)


class TimesheetEdit(BaseModel):
    week_start: str
    note: str | None = None
    edits: list[dict] = []


@router.post("/new-starter/portal/timesheet/edit")
async def portal_timesheet_edit(body: TimesheetEdit, user: dict = Depends(get_current_user_portal)):
    """Employee submits corrections to their week — flags the timesheet as
    disputed so a manager reviews and approves in Time Clock ▸ Timesheets."""
    staff = await _portal_staff(user)
    from routes.staffing_clock import _ensure_timesheet_doc, _week_bounds
    ws, we = _week_bounds(body.week_start)
    ts = await _ensure_timesheet_doc(staff["organization_id"], staff["id"], ws, we)
    reason = (body.note or "").strip() or "Employee requested corrections to their hours."
    await db.staff_timesheets.update_one(
        {"id": ts["id"]},
        {"$set": {
            "approval_status": "disputed",
            "dispute_reason": reason,
            "staff_requested_edits": body.edits,
            "disputed_by": staff.get("full_name") or user.get("email"),
            "disputed_at": _now(),
        }},
    )
    return {"ok": True, "status": "disputed"}


def _days_between(start: str, end: str) -> int:
    try:
        s = datetime.fromisoformat(start).date()
        e = datetime.fromisoformat(end).date()
        return max(1, (e - s).days + 1)
    except Exception:
        return 1


@router.get("/new-starter/portal/holidays")
async def portal_holidays(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    mine = await db.staff_leave_requests.find(
        {"organization_id": org, "staff_id": staff["id"]},
        {"_id": 0},
    ).sort("start_date", -1).to_list(200)

    # Allowance — parsed from the employment proposal (best-effort).
    case = await _case_for(staff["id"])
    ent = ((case or {}).get("employment_proposal") or {}).get("holiday_entitlement") or ""
    m = re.search(r"\d+", str(ent))
    total = int(m.group()) if m else 28
    yr = date.today().year
    from routes.attendance import count_working_days
    used = 0
    for r in mine:
        if (r.get("leave_type") == "holiday" and r.get("status") == "approved"
                and str(r.get("start_date", "")).startswith(str(yr))):
            wd = r.get("working_days")
            if wd is None:
                wd = (await count_working_days(org, staff, r["start_date"], r["end_date"]))["working_days"]
            used += wd

    # Team calendar — APPROVED holidays of same-department colleagues only.
    dept = await _department(staff)
    team: list[dict] = []
    if dept:
        colleagues = await db.staff_members.find(
            {"organization_id": org, "active": True, "department": dept,
             "id": {"$ne": staff["id"]}},
            {"_id": 0, "id": 1, "full_name": 1},
        ).to_list(500)
        by_id = {c["id"]: c.get("full_name") for c in colleagues}
        if by_id:
            rows = await db.staff_leave_requests.find(
                {"organization_id": org, "staff_id": {"$in": list(by_id)},
                 "leave_type": "holiday", "status": "approved"},
                {"_id": 0, "staff_id": 1, "start_date": 1, "end_date": 1},
            ).sort("start_date", 1).to_list(500)
            team = [{"full_name": by_id.get(r["staff_id"]), "start_date": r["start_date"],
                     "end_date": r["end_date"]} for r in rows]

    return {
        "mine": mine,
        "department": dept,
        "allowance": {"total": total, "used": used, "remaining": max(0, total - used)},
        "team": team,
    }


class HolidayRequest(BaseModel):
    start_date: str
    end_date: str
    note: str | None = None


@router.post("/new-starter/portal/holidays")
async def portal_request_holiday(body: HolidayRequest, user: dict = Depends(get_current_user_portal)):
    from routes.attendance import count_working_days
    staff = await _portal_staff(user)
    if not body.start_date or not body.end_date:
        raise HTTPException(400, "Start and end dates are required.")
    if body.end_date < body.start_date:
        raise HTTPException(400, "End date can't be before the start date.")
    wd = await count_working_days(staff["organization_id"], staff, body.start_date, body.end_date)
    if wd["working_days"] < 1:
        raise HTTPException(400, "That range has no working days (weekend / bank holiday only).")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": staff["organization_id"],
        "staff_id": staff["id"],
        "status": "pending",
        "leave_type": "holiday",
        "start_date": body.start_date,
        "end_date": body.end_date,
        "working_days": wd["working_days"],
        "bank_holidays_in_range": wd["bank_holidays"],
        "reason": body.note,
        "created_at": _now(),
        "requested_via": "staff_portal",
    }
    await db.staff_leave_requests.insert_one(doc.copy())
    return _clean(doc)


@router.get("/new-starter/portal/holidays/preview")
async def portal_holiday_preview(start: str = Query(...), end: str = Query(...),
                                 user: dict = Depends(get_current_user_portal)):
    """Live working-days count for the request form (excludes rest days + bank holidays)."""
    from routes.attendance import count_working_days
    staff = await _portal_staff(user)
    if end < start:
        return {"working_days": 0, "bank_holidays": 0}
    wd = await count_working_days(staff["organization_id"], staff, start, end)
    return {"working_days": wd["working_days"], "bank_holidays": wd["bank_holidays"]}


@router.delete("/new-starter/portal/holidays/{leave_id}")
async def portal_cancel_holiday(leave_id: str, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    rec = await db.staff_leave_requests.find_one({"id": leave_id, "staff_id": staff["id"]})
    if not rec:
        raise HTTPException(404, "Request not found.")
    if rec.get("status") not in ("pending", None):
        raise HTTPException(400, "Only pending requests can be cancelled.")
    await db.staff_leave_requests.delete_one({"id": leave_id})
    return {"ok": True}


# ══════════════════ MY DAY + MY TIME (Attendance Spine) ══════════════════
# Mobile-first employee surface. Reads/writes the ONE daily record via the
# attendance engine so a clock-in / typed hours / self-reported sickness all
# resolve into the single source of truth (ENTER ONCE → USE EVERYWHERE).

def _month_bounds(anchor: str) -> tuple[str, str]:
    d = datetime.fromisoformat(anchor).date() if anchor else date.today()
    first = d.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    last = nxt - timedelta(days=1)
    return first.isoformat(), last.isoformat()


async def _day_state(org_id: str, staff_id: str) -> dict:
    from routes.staffing_clock import _last_clock_event, _state_from_event
    ev = await _last_clock_event(staff_id, org_id)
    return {"clock_state": _state_from_event(ev),
            "last_punch_at": (ev or {}).get("occurred_at")}


@router.get("/new-starter/portal/my-day")
async def portal_my_day(user: dict = Depends(get_current_user_portal)):
    from routes.attendance import (
        recompute_day, _resolve_profile, ATTENDANCE_STATUSES,
    )
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    today = _today()
    profile = await _resolve_profile(org, staff)
    record = await recompute_day(org, staff["id"], today)
    state = await _day_state(org, staff["id"])

    # This-month totals — recompute past+today (one employee, ≤31 days).
    m_start, m_end = _month_bounds(today)
    cur = datetime.fromisoformat(m_start).date()
    stop = date.today()
    while cur <= stop:
        try:
            await recompute_day(org, staff["id"], cur.isoformat())
        except Exception:
            pass
        cur += timedelta(days=1)
    rows = await db.attendance_daily.find(
        {"organization_id": org, "staff_id": staff["id"],
         "date": {"$gte": m_start, "$lte": m_end}}, {"_id": 0},
    ).to_list(40)
    recorded = round(sum(r.get("regular_hours") or 0 for r in rows), 2)
    expected = round(sum(r.get("expected_hours") or 0 for r in rows
                         if r.get("expected_status") == "working"), 2)
    overtime = round(sum((r.get("approved_overtime_hours") or 0) or (r.get("overtime_raw_hours") or 0) for r in rows), 2)
    missing = sum(1 for r in rows if r.get("actual_status") == "not_confirmed" and r["date"] < today)

    # Upcoming approved leave (next 60 days).
    horizon = (date.today() + timedelta(days=60)).isoformat()
    upcoming = await db.staff_leave_requests.find(
        {"organization_id": org, "staff_id": staff["id"], "status": "approved",
         "start_date": {"$gte": today, "$lte": horizon}}, {"_id": 0},
    ).sort("start_date", 1).to_list(10)

    method = profile.get("time_entry_method") or "daily_timesheet"
    meta = ATTENDANCE_STATUSES.get(record["actual_status"], {})
    return {
        "date": today,
        "first_name": (staff.get("full_name") or "").split(" ")[0] or "there",
        "time_entry_method": method,
        "record": record,
        "status_label": meta.get("label"),
        "status_color": meta.get("color"),
        "clock_state": state["clock_state"],
        "expected_hours_today": record.get("expected_hours"),
        "month": {"recorded": recorded, "expected": expected,
                  "overtime": overtime, "missing": missing},
        "upcoming_leave": upcoming,
        "statuses": ATTENDANCE_STATUSES,
    }


class PunchBody(BaseModel):
    kind: str  # clock_in | clock_out | break_start | break_end


@router.post("/new-starter/portal/day/punch")
async def portal_punch(body: PunchBody, user: dict = Depends(get_current_user_portal)):
    from routes.staffing_clock import (
        _last_clock_event, _state_from_event, _validate_transition, VALID_PUNCH_KINDS,
    )
    from routes.attendance import recompute_day
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    if body.kind not in VALID_PUNCH_KINDS:
        raise HTTPException(400, "invalid punch kind")
    last = await _last_clock_event(staff["id"], org)
    err = _validate_transition(_state_from_event(last), body.kind)
    if err:
        raise HTTPException(409, err)
    now = datetime.now(timezone.utc)
    event = {"id": str(uuid.uuid4()), "organization_id": org, "staff_id": staff["id"],
             "kind": body.kind, "occurred_at": now.isoformat(), "source": "staff_portal",
             "created_by_user_id": user.get("id"), "created_at": _now()}
    await db.staff_clock_events.insert_one(event.copy())
    record = await recompute_day(org, staff["id"], now.date().isoformat())
    return {"ok": True, "clock_state": _state_from_event(event), "record": record}


class DayEntryBody(BaseModel):
    date: str | None = None
    start: str
    finish: str
    break_minutes: int = 0


@router.post("/new-starter/portal/day/timesheet")
async def portal_day_timesheet(body: DayEntryBody, user: dict = Depends(get_current_user_portal)):
    from routes.attendance import set_employee_entry
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    day = body.date or _today()
    record = await set_employee_entry(org, staff["id"], day, body.start, body.finish, body.break_minutes)
    return {"ok": True, "record": record}


@router.get("/new-starter/portal/my-time")
async def portal_my_time(scope: str = Query("week"), anchor: str | None = Query(None),
                         user: dict = Depends(get_current_user_portal)):
    from routes.attendance import recompute_day, ATTENDANCE_STATUSES
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    a = anchor or _today()
    if scope == "month":
        start, end = _month_bounds(a)
    else:  # week (Mon–Sun)
        from routes.staffing_clock import _week_bounds
        start, end = _week_bounds(a)
    cur = datetime.fromisoformat(start).date()
    stop_end = datetime.fromisoformat(end).date()
    today = date.today()
    while cur <= min(stop_end, today):
        try:
            await recompute_day(org, staff["id"], cur.isoformat())
        except Exception:
            pass
        cur += timedelta(days=1)
    rows = await db.attendance_daily.find(
        {"organization_id": org, "staff_id": staff["id"],
         "date": {"$gte": start, "$lte": end}}, {"_id": 0},
    ).sort("date", 1).to_list(40)
    totals = {
        "worked": round(sum(r.get("regular_hours") or 0 for r in rows), 2),
        "expected": round(sum(r.get("expected_hours") or 0 for r in rows if r.get("expected_status") == "working"), 2),
        "overtime": round(sum((r.get("approved_overtime_hours") or 0) or (r.get("overtime_raw_hours") or 0) for r in rows), 2),
        "holiday": round(sum(r.get("paid_leave_hours") or 0 for r in rows if r.get("actual_status") == "holiday"), 2),
        "sick": round(sum(r.get("paid_leave_hours") or 0 for r in rows if r.get("actual_status") == "sick"), 2),
        "missing": sum(1 for r in rows if r.get("actual_status") == "not_confirmed" and r["date"] < _today()),
    }
    return {"scope": scope, "start": start, "end": end, "records": rows,
            "totals": totals, "statuses": ATTENDANCE_STATUSES}


class AbsenceBody(BaseModel):
    absence_type: str = "sick"          # sick | family_leave | other
    first_day: str
    expected_return: str | None = None
    note: str | None = None


@router.post("/new-starter/portal/report-absence")
async def portal_report_absence(body: AbsenceBody, user: dict = Depends(get_current_user_portal)):
    """Self-reported absence (§19/§20). Sickness reflects immediately: the day
    becomes SICK and open-ended sick keeps marking forward until closed."""
    from routes.attendance import apply_leave_to_daily
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    lt_map = {"sick": "sick", "family_leave": "other", "other": "other"}
    leave_type = lt_map.get(body.absence_type, "sick")
    # end_date: expected_return - 1 day (return day itself is worked); open if unknown.
    end_date = None
    if body.expected_return:
        try:
            end_date = (datetime.fromisoformat(body.expected_return).date() - timedelta(days=1)).isoformat()
            if end_date < body.first_day:
                end_date = body.first_day
        except Exception:
            end_date = None
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org, "staff_id": staff["id"],
        "status": "approved", "self_reported": True, "leave_type": leave_type,
        "absence_type": body.absence_type, "start_date": body.first_day,
        "end_date": end_date, "reason": body.note, "created_at": _now(),
        "requested_via": "staff_portal",
    }
    await db.staff_leave_requests.insert_one(doc.copy())
    days = await apply_leave_to_daily(org, doc)
    return {"ok": True, "absence_id": doc["id"], "days_marked": days,
            "open_ended": end_date is None}


class RtwAckBody(BaseModel):
    agreed: bool = False
    comment: str | None = None


@router.get("/new-starter/portal/rtw-pending")
async def portal_rtw_pending(user: dict = Depends(get_current_user_portal)):
    """Closed sicknesses awaiting the employee's electronic sign-off (§20/§21) —
    the second signature that matches Pulse's two-signature return-to-work form."""
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    rows = await db.staff_leave_requests.find(
        {"organization_id": org, "staff_id": staff["id"],
         "rtw_interview": {"$exists": True},
         "employee_ack": {"$exists": False}}, {"_id": 0},
    ).sort("closed_at", -1).to_list(20)
    out = []
    for r in rows:
        rtw = r.get("rtw_interview") or {}
        out.append({
            "leave_id": r["id"],
            "start_date": r.get("start_date"),
            "return_date": r.get("return_date") or r.get("end_date"),
            "reason": rtw.get("reason"),
            "fit_to_return": rtw.get("fit_to_return"),
            "fit_details": rtw.get("fit_details"),
            "agreed_actions": rtw.get("agreed_actions"),
            "interviewer": rtw.get("interviewer"),
            "completed_at": rtw.get("completed_at"),
        })
    return {"pending": out}


@router.post("/new-starter/portal/rtw/{leave_id}/acknowledge")
async def portal_rtw_acknowledge(leave_id: str, body: RtwAckBody,
                                 user: dict = Depends(get_current_user_portal)):
    """Employee electronically confirms the agreed return-to-work actions,
    capturing the second signature (name, email, timestamp) so both sign-offs
    are recorded per Pulse procedure."""
    if not body.agreed:
        raise HTTPException(400, "Please confirm the agreed actions to sign off.")
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    leave = await db.staff_leave_requests.find_one(
        {"organization_id": org, "staff_id": staff["id"], "id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "return-to-work record not found")
    if not leave.get("rtw_interview"):
        raise HTTPException(400, "no return-to-work interview to acknowledge")
    if leave.get("employee_ack"):
        raise HTTPException(409, "already acknowledged")
    ack = {
        "confirmed": True,
        "comment": (body.comment or "").strip() or None,
        "employee_name": staff.get("full_name"),
        "employee_email": user.get("email") or staff.get("email"),
        "acknowledged_at": _now(),
    }
    await db.staff_leave_requests.update_one(
        {"organization_id": org, "id": leave_id},
        {"$set": {"employee_ack": ack}},
    )
    return {"ok": True, "acknowledged_at": ack["acknowledged_at"]}


@router.get("/new-starter/portal/periods")
async def portal_current_periods(user: dict = Depends(get_current_user_portal)):
    """Open pay periods relevant to the employee + their own submission status."""
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    from routes.attendance import period_summary
    periods = await db.pay_periods.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("start_date", -1).to_list(12)
    out = []
    for p in periods[:6]:
        ts = await db.pay_period_timesheets.find_one(
            {"organization_id": org, "period_id": p["id"], "staff_id": staff["id"]}, {"_id": 0},
        )
        totals = (ts or {}).get("snapshot_totals") or (ts or {}).get("totals")
        if not totals:
            totals = await period_summary(org, staff["id"], p["start_date"], p["end_date"])
        out.append({"period": p, "status": (ts or {}).get("status", "draft"),
                    "returned_reason": (ts or {}).get("returned_reason"), "totals": totals})
    return {"periods": out}


class PortalSubmitBody(BaseModel):
    declaration: bool = True


@router.post("/new-starter/portal/period/{period_id}/submit")
async def portal_submit_period(period_id: str, body: PortalSubmitBody,
                               user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    period = await db.pay_periods.find_one({"organization_id": org, "id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "pay period not found")
    from routes.payroll import _do_submit
    totals = await _do_submit(org, period, staff["id"], body.declaration, user.get("email") or staff.get("full_name"))
    return {"ok": True, "totals": totals}


@router.get("/staffing/me/portal-access")
async def my_portal_access(user: dict = Depends(get_current_user)):
    """Post-login launcher probe — does the signed-in platform user also have
    an employee Staff Portal? True when a staff_members record is linked to
    their user id (or email) in their org."""
    org = user.get("organization_id")
    q = {"$or": [{"user_id": user.get("id")}]}
    if user.get("email"):
        q["$or"].append({"email": user.get("email")})
    if org:
        q["organization_id"] = org
    staff = await db.staff_members.find_one(q, {"_id": 0, "full_name": 1, "active": 1})
    return {"has_staff_portal": bool(staff and staff.get("active", True)),
            "full_name": (staff or {}).get("full_name")}





@router.get("/new-starter/portal/documents")
async def portal_documents(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    case = await _case_for(staff["id"])
    docs: list[dict] = []
    offer_available = contract_available = False
    if case:
        rows = await db.staff_onboarding_documents.find(
            {"onboarding_case_id": case["id"], "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "original_filename": 1, "document_type": 1, "upload_date": 1},
        ).to_list(200)
        docs = rows
        offer_available = (case.get("offer") or {}).get("status") in ("issued", "accepted")
        contract_available = (case.get("contract") or {}).get("status") in (
            "issued", "employee_signed", "fully_signed")
    return {"documents": docs, "offer_available": offer_available,
            "contract_available": contract_available}


@router.get("/new-starter/portal/access")
async def portal_access(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    prov = await db.staff_access_provisions.find_one({"staff_id": staff["id"]}) or {}
    granted = set(prov.get("granted_modules") or [])
    avail = await _org_available_modules(org)
    lm_name = staff.get("line_manager_name")
    if not lm_name and staff.get("line_manager_staff_id"):
        lm = await db.staff_members.find_one({"id": staff["line_manager_staff_id"]}, {"_id": 0, "full_name": 1})
        lm_name = (lm or {}).get("full_name")
    return {
        "line_manager": lm_name,
        "status": prov.get("status") or ("awaiting_manager" if lm_name else "not_started"),
        "modules": [{"key": k, "label": MODULE_LABELS[k], "granted": k in granted} for k in avail],
        "updated_at": prov.get("updated_at"),
    }


# ══════════════════════════ HR — LINE MANAGER ══════════════════════════

@router.get("/staff-onboarding/managers")
async def list_managers(user: dict = Depends(get_current_user)):
    """Active staff with a real login — eligible to be a Line Manager."""
    _require_hr(user)
    org = _org(user)
    rows = await db.staff_members.find(
        {"organization_id": org, "active": True, "user_id": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1},
    ).sort("full_name", 1).to_list(1000)
    return {"managers": [{"staff_id": r["id"], "full_name": r.get("full_name"),
                          "role": r.get("primary_role")} for r in rows]}


class LineManagerAssign(BaseModel):
    line_manager_staff_id: str


@router.get("/staff-onboarding/cases/{case_id}/line-manager")
async def get_line_manager(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user)
    org = _org(user)
    case = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not case:
        raise HTTPException(404, "Case not found")
    staff = await db.staff_members.find_one({"id": case["staff_id"]}) or {}
    return {"line_manager_staff_id": staff.get("line_manager_staff_id"),
            "line_manager_name": staff.get("line_manager_name")}


@router.post("/staff-onboarding/cases/{case_id}/line-manager")
async def assign_line_manager(case_id: str, body: LineManagerAssign,
                              user: dict = Depends(get_current_user)):
    _require_hr(user)
    org = _org(user)
    case = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not case:
        raise HTTPException(404, "Case not found")
    mgr = await db.staff_members.find_one(
        {"id": body.line_manager_staff_id, "organization_id": org})
    if not mgr:
        raise HTTPException(404, "Line manager not found")
    await db.staff_members.update_one(
        {"id": case["staff_id"]},
        {"$set": {"line_manager_staff_id": mgr["id"], "line_manager_name": mgr.get("full_name")}},
    )
    ep = {**(case.get("employment_proposal") or {}), "line_manager": mgr.get("full_name")}
    await db.staff_onboarding_cases.update_one(
        {"id": case_id}, {"$set": {"employment_proposal": ep, "updated_at": _now()}})
    await db.staff_access_provisions.update_one(
        {"staff_id": case["staff_id"]},
        {"$set": {"organization_id": org, "staff_id": case["staff_id"],
                  "line_manager_staff_id": mgr["id"], "status": "awaiting_manager",
                  "updated_at": _now()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "granted_modules": []}},
        upsert=True,
    )
    return {"ok": True, "line_manager_name": mgr.get("full_name")}


# ══════════════════════════ LINE MANAGER — ACCESS GRANTS ══════════════════════════

@router.get("/staffing/access/my-reports")
async def my_reports(user: dict = Depends(get_current_user)):
    org = _org(user)
    me = await db.staff_members.find_one({"organization_id": org, "user_id": user.get("id")},
                                         {"_id": 0, "id": 1})
    q = {"organization_id": org, "active": True}
    see_all = _is_manager(user)
    if me:
        q_reports = {**q, "line_manager_staff_id": me["id"]}
    else:
        q_reports = {**q, "line_manager_staff_id": "__none__"}
    # Owners/master admins can review every provisioned employee; a plain
    # line manager sees only their own direct reports.
    if see_all and (user.get("is_master_admin") or user.get("is_pulse_admin")
                    or (user.get("role") or "").lower() == "owner"):
        q_reports = {**q, "line_manager_staff_id": {"$nin": [None, ""]}}
    reports = await db.staff_members.find(
        q_reports, {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1,
                    "department": 1, "line_manager_name": 1, "user_id": 1},
    ).sort("full_name", 1).to_list(1000)
    avail = await _org_available_modules(org)
    out = []
    for r in reports:
        prov = await db.staff_access_provisions.find_one({"staff_id": r["id"]}) or {}
        granted = set(prov.get("granted_modules") or [])
        # Service Desk / Inventory live on the user record (and can be set from
        # other surfaces too), so reflect the authoritative flags into the
        # toggles rather than trusting only the provision doc.
        if r.get("user_id"):
            u = await db.users.find_one(
                {"id": r["user_id"]}, {"_id": 0, "is_service_desk": 1, "is_inventory": 1})
            if u:
                granted.discard("service_desk"); granted.discard("inventory")
                if u.get("is_service_desk"):
                    granted.add("service_desk")
                if u.get("is_inventory"):
                    granted.add("inventory")
        out.append({
            "staff_id": r["id"], "full_name": r.get("full_name"),
            "role": r.get("primary_role"), "department": r.get("department"),
            "line_manager_name": r.get("line_manager_name"),
            "granted_modules": sorted(granted),
            "status": prov.get("status") or "awaiting_manager",
        })
    return {"reports": out,
            "available_modules": [{"key": k, "label": MODULE_LABELS[k]} for k in avail]}


class ModuleGrant(BaseModel):
    modules: list[str] = []


@router.post("/staffing/access/reports/{staff_id}/modules")
async def grant_report_modules(staff_id: str, body: ModuleGrant,
                               user: dict = Depends(get_current_user)):
    org = _org(user)
    report = await db.staff_members.find_one({"id": staff_id, "organization_id": org})
    if not report:
        raise HTTPException(404, "Team member not found")
    me = await db.staff_members.find_one({"organization_id": org, "user_id": user.get("id")},
                                         {"_id": 0, "id": 1})
    owner_level = (user.get("is_master_admin") or user.get("is_pulse_admin")
                   or (user.get("role") or "").lower() == "owner")
    if not owner_level and (not me or report.get("line_manager_staff_id") != me["id"]):
        raise HTTPException(403, "You can only manage access for your own direct reports.")
    avail = await _org_available_modules(org)
    granted = [m for m in body.modules if m in avail]
    await db.staff_access_provisions.update_one(
        {"staff_id": staff_id},
        {"$set": {"organization_id": org, "staff_id": staff_id, "granted_modules": granted,
                  "status": "granted", "updated_by": user.get("email"), "updated_at": _now()},
         "$setOnInsert": {"id": str(uuid.uuid4()),
                          "line_manager_staff_id": report.get("line_manager_staff_id")}},
        upsert=True,
    )
    # Reflect on the user's module_overrides (overrides can only REVOKE, so we
    # switch OFF any bolt-on the manager did not grant; granted bolt-ons fall
    # back to the org-level entitlement).
    if report.get("user_id"):
        overrides = {m: (m in granted) for m in BOLT_ON if m in avail}
        user_set: dict = {"module_overrides": overrides}
        now = _now()
        # Per-user capability grants — stamp Service Desk / Inventory straight
        # onto the user record so they can reach those apps (or lose access).
        if "service_desk" in avail:
            desk_on = "service_desk" in granted
            user_set["is_service_desk"] = desk_on
            if desk_on:
                existing = await db.users.find_one(
                    {"id": report["user_id"]},
                    {"_id": 0, "service_desk_brand": 1, "service_org_id": 1})
                if not (existing or {}).get("service_desk_brand"):
                    user_set["service_desk_brand"] = "pulse"
                if not (existing or {}).get("service_org_id"):
                    user_set["service_org_id"] = org
                user_set["service_desk_granted_at"] = now
                user_set["service_desk_granted_by_email"] = user.get("email")
        if "inventory" in avail:
            user_set["is_inventory"] = "inventory" in granted
        await db.users.update_one({"id": report["user_id"]}, {"$set": user_set})
    return {"ok": True, "granted_modules": granted}
