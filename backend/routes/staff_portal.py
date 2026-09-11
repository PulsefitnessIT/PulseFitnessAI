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
import io
import base64
from datetime import datetime, timezone, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Body, Query, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from utils.database import db, put_object, get_object, APP_NAME
from utils.auth import get_current_user, get_current_user_portal
from utils.module_access import org_module_access, resolve_module_access

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
    """Resolve the staff_members doc for a logged-in staff-portal user.

    Matches by user_id, falling back to email (case-insensitive, org-scoped) so
    employees whose record was linked by email still get in; self-heals the
    user_id link when resolved by email.
    """
    staff = await db.staff_members.find_one({"user_id": user.get("id")})
    if not staff:
        email = (user.get("email") or "").strip()
        if email:
            q = {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
            if user.get("organization_id"):
                q["organization_id"] = user["organization_id"]
            staff = await db.staff_members.find_one(q)
            if staff and staff.get("user_id") != user.get("id"):
                await db.staff_members.update_one({"id": staff["id"]}, {"$set": {"user_id": user.get("id")}})
    if not staff:
        raise HTTPException(404, "No staff record for this account.")
    return staff


async def notify_staff(*, org: str, recipient_kind: str, type: str, title: str,
                       body: str, link: str = "", recipient_staff_id: str | None = None,
                       recipient_user_id: str | None = None,
                       dedupe_key: str | None = None) -> None:
    """Write a persistent in-app staffing notification (bell feed).

    recipient_kind='employee' → keyed by recipient_staff_id (Staff Portal bell).
    recipient_kind='manager'  → keyed by recipient_user_id (line manager) or
    left null for any owner/manager in the org to pick up (Staffing bell)."""
    if dedupe_key:
        exists = await db.staff_notifications.find_one(
            {"organization_id": org, "dedupe_key": dedupe_key}, {"_id": 1})
        if exists:
            return
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org,
        "recipient_kind": recipient_kind,
        "recipient_staff_id": recipient_staff_id,
        "recipient_user_id": recipient_user_id,
        "type": type, "title": title, "body": body, "link": link,
        "read": False, "created_at": _now(),
    }
    if dedupe_key:
        doc["dedupe_key"] = dedupe_key
    await db.staff_notifications.insert_one(doc.copy())


async def _line_manager_user_id(org: str, staff: dict) -> str | None:
    lm_sid = staff.get("line_manager_staff_id")
    if not lm_sid:
        return None
    lm = await db.staff_members.find_one(
        {"organization_id": org, "id": lm_sid}, {"_id": 0, "user_id": 1})
    return (lm or {}).get("user_id")


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


_EDITABLE_TS = {"pending", "returned", "disputed", "draft", None}


class SelfDay(BaseModel):
    date: str
    start: str | None = None
    finish: str | None = None
    break_minutes: float | None = 0
    pt_classes: float | None = 0
    van_check: bool | None = False
    notes: str | None = None


class SelfSave(BaseModel):
    week_start: str
    days: list[SelfDay] = []


@router.post("/new-starter/portal/timesheet/self-save")
async def portal_timesheet_self_save(body: SelfSave, user: dict = Depends(get_current_user_portal)):
    """Employee fills in their own hours for the week (remote / no-rota staff, or
    extra time on top of a shift). Writes `self_entries` keyed by date. Blocked
    once the week is submitted/approved (locked)."""
    staff = await _portal_staff(user)
    from routes.staffing_clock import _ensure_timesheet_doc, _week_bounds
    ws, we = _week_bounds(body.week_start)
    ts = await _ensure_timesheet_doc(staff["organization_id"], staff["id"], ws, we)
    if ts.get("approval_status") not in _EDITABLE_TS:
        raise HTTPException(409, "This week is locked for approval. Ask your manager to return it if you need changes.")
    entries: dict = {}
    for d in body.days:
        note = (d.notes or "").strip()
        if not (d.start or d.finish or d.break_minutes or d.pt_classes or d.van_check or note):
            continue
        entries[d.date] = {
            "start": (d.start or "").strip() or None,
            "finish": (d.finish or "").strip() or None,
            "break_minutes": float(d.break_minutes or 0),
            "pt_classes": float(d.pt_classes or 0),
            "van_check": bool(d.van_check),
            "notes": note or None,
        }
    await db.staff_timesheets.update_one(
        {"id": ts["id"]},
        {"$set": {"self_entries": entries, "self_updated_at": _now()}},
    )
    fresh = await _ensure_timesheet_doc(staff["organization_id"], staff["id"], ws, we)
    return _clean(fresh)


class SelfSubmit(BaseModel):
    week_start: str
    signature: str


@router.post("/new-starter/portal/timesheet/submit")
async def portal_timesheet_submit(body: SelfSubmit, user: dict = Depends(get_current_user_portal)):
    """Employee signs and submits the week — locks it and flags for the manager
    to approve in Time Clock ▸ Timesheets."""
    staff = await _portal_staff(user)
    sig = (body.signature or "").strip()
    if not sig:
        raise HTTPException(400, "Please type your name to sign the timesheet.")
    from routes.staffing_clock import _ensure_timesheet_doc, _week_bounds
    ws, we = _week_bounds(body.week_start)
    ts = await _ensure_timesheet_doc(staff["organization_id"], staff["id"], ws, we)
    if ts.get("approval_status") in ("submitted", "approved"):
        raise HTTPException(409, "This week has already been submitted.")
    await db.staff_timesheets.update_one(
        {"id": ts["id"]},
        {"$set": {
            "approval_status": "submitted",
            "employee_signature": sig,
            "submitted_at": _now(),
        }, "$unset": {"return_reason": "", "dispute_reason": ""}},
    )
    return {"ok": True, "status": "submitted"}


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
    # Route to the employee's line manager (or any owner/manager if unassigned).
    mgr_uid = await _line_manager_user_id(staff["organization_id"], staff)
    await notify_staff(
        org=staff["organization_id"], recipient_kind="manager", recipient_user_id=mgr_uid,
        type="holiday_request",
        title="New holiday request",
        body=f"{staff.get('full_name') or 'An employee'} requested {wd['working_days']} "
             f"working day{'' if wd['working_days'] == 1 else 's'}: {body.start_date} → {body.end_date}.",
        link="leave",
    )
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


HANDBOOK_SECTIONS = [
    ("Signing in", [
        "Open the Staff Portal link in your welcome email and sign in with the details provided.",
        "On a phone the portal works like an app — add it to your home screen for one-tap access.",
        "After login, choose the Staff Portal or another module from the launcher."]),
    ("Getting around (mobile)", [
        "A fixed bottom bar gives you the main areas: Home, My Time, Holidays, Vehicle and More.",
        "'More' holds My Rota, Timesheets, Documents, System Access, My Details and Help & Tutorials.",
        "The bell (top right) shows reminders and updates — tap an item to jump straight to it."]),
    ("My Day (Home)", [
        "Record your day in seconds: start/finish, breaks, working from home, sick and more.",
        "If you've been off sick, confirm the agreed return-to-work actions here."]),
    ("My Time (timesheets)", [
        "Review your week or month of daily records in one place.",
        "Type your hours for each day — start, finish, break minutes and any PT classes; the daily "
        "and weekly totals work themselves out automatically.",
        "When the week looks right, sign it off by typing your full name in the signature box "
        "('Type name to sign here') and submit it to your manager.",
        "A reminder appears if any days are missing confirmed hours. Once you submit (or it's "
        "approved) the week is locked."]),
    ("Van check & daily notes (field engineers)", [
        "If you're a field engineer, your timesheet shows two extra fields on each day.",
        "Tick 'Van check' on every day you completed your vehicle check.",
        "Use the day's 'Notes' box for a short line about the day (e.g. 'Site A callout, M62 delay').",
        "Your van checks and notes are shown to your manager when they review the week and appear "
        "on the timesheet PDF/Excel."]),
    ("Holidays", [
        "Request holiday by picking your dates — the portal auto-calculates the working days "
        "(excluding weekends and bank holidays) and shows what's left of your allowance.",
        "Requests go to your line manager to approve; you're notified of the decision."]),
    ("Vehicle checks (drivers)", [
        "If a vehicle is assigned to you, complete its weekly check in the Vehicle tab.",
        "Your name, registration and vehicle details are pre-filled. Mark each item OK / Defect / N/A.",
        "The checklist matches your vehicle type (car, electric car, van or lorry).",
        "For any defect (or if it's not safe to drive), describe it, add a photo and submit — "
        "your manager is alerted automatically.",
        "Tick the declaration and Submit. Checks are due weekly (by Friday); you'll be reminded "
        "if one is outstanding."]),
    ("My Details", [
        "See the personal and payroll information we hold for you — contact details, emergency "
        "contact and bank details.",
        "Need something changed? Request an update (for example a new address, bank details or "
        "emergency contact) and it's sent to HR to approve — you'll see a 'pending' note until "
        "it's actioned.",
        "Add a profile photo so managers can put a face to the name — tap your photo to upload a headshot."]),
    ("Documents & System Access", [
        "View your documents and the platform modules you have access to."]),
    ("Help & Tutorials", [
        "This section holds these quick guides and lets you download the full Staff Portal "
        "Handbook (PDF) any time."]),
    ("Need help?", [
        "Contact your line manager or the Pulse HR team."]),
]


def _build_handbook_pdf(full_name: str | None) -> bytes:
    import io as _io
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
    from utils.pulse_doc_template import (
        pulse_styles, pulse_header, pulse_title, section_label, make_pulse_doc,
    )
    s = pulse_styles()
    buf = _io.BytesIO()
    doc = make_pulse_doc(buf, "Staff Portal Handbook")
    story = [pulse_header(s, None)]
    story += pulse_title(s, "Staff Portal Handbook",
                         f"Welcome{(' ' + full_name) if full_name else ''} — your quick guide to the Pulse Fitness Staff Portal")
    story.append(Spacer(1, 5 * mm))
    esc = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for i, (title, points) in enumerate(HANDBOOK_SECTIONS, start=1):
        story.append(section_label(s, f"{i}. {title}"))
        story.append(ListFlowable(
            [ListItem(Paragraph(esc(p), s["body"]), leftIndent=10) for p in points],
            bulletType="bullet", start="•"))
        story.append(Spacer(1, 3 * mm))
    doc.build(story)
    return buf.getvalue()


@router.get("/new-starter/portal/handbook.pdf")
async def portal_handbook(user: dict = Depends(get_current_user_portal)):
    """Pulse-branded employee handbook PDF for the Staff Portal."""
    staff = await _portal_staff(user)
    try:
        pdf = _build_handbook_pdf(staff.get("full_name"))
    except Exception as e:
        raise HTTPException(500, f"Could not generate handbook: {e}")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=pulse-staff-portal-handbook.pdf"})


@router.get("/new-starter/portal/handbook-guide")
async def portal_handbook_guide(user: dict = Depends(get_current_user_portal)):
    """Handbook content as JSON — powers the in-app Help & Tutorials tab so it
    always matches the downloadable PDF (single source of truth)."""
    await _portal_staff(user)
    return {"sections": [{"title": t, "points": list(p)} for t, p in HANDBOOK_SECTIONS]}



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


# ══════════════════════════ NOTIFICATIONS / NUDGES ══════════════════════════

@router.get("/new-starter/portal/notifications")
async def portal_notifications(user: dict = Depends(get_current_user_portal)):
    """Staff Portal bell — event pings (leave decisions) + live nudges
    (missing time entries, unsigned return-to-work forms)."""
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    stored = await db.staff_notifications.find(
        {"organization_id": org, "recipient_kind": "employee", "recipient_staff_id": staff["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)

    nudges: list[dict] = []
    today = _today()
    win_start = (date.today() - timedelta(days=30)).isoformat()
    missing = await db.attendance_daily.count_documents(
        {"organization_id": org, "staff_id": staff["id"],
         "actual_status": "not_confirmed", "date": {"$gte": win_start, "$lt": today}})
    if missing:
        nudges.append({
            "type": "missing_time", "title": "Missing time entries",
            "body": f"{missing} day{'' if missing == 1 else 's'} in the last 30 days have no confirmed hours.",
            "link": "mytime"})
    rtw_pending = await db.staff_leave_requests.count_documents(
        {"organization_id": org, "staff_id": staff["id"],
         "rtw_interview": {"$exists": True}, "employee_ack": {"$exists": False}})
    if rtw_pending:
        nudges.append({
            "type": "rtw_unsigned", "title": "Return-to-work sign-off needed",
            "body": f"{rtw_pending} return-to-work form{'' if rtw_pending == 1 else 's'} awaiting your confirmation.",
            "link": "home"})

    # Weekly vehicle checks assigned to me but not yet submitted this week.
    from routes.vehicle_checks import run_vehicle_chase, _is_chase_time
    await run_vehicle_chase(org)
    week = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    my_vehicle_ids = await db.vehicles.distinct(
        "id", {"organization_id": org, "active": {"$ne": False}, "driver_staff_ids": staff["id"]})
    if my_vehicle_ids:
        done_ids = await db.vehicle_checks.distinct(
            "vehicle_id", {"organization_id": org, "week_commencing": week,
                           "vehicle_id": {"$in": my_vehicle_ids},
                           "status": {"$in": ["submitted", "reviewed"]}})
        due = len(set(my_vehicle_ids) - set(done_ids))
        if due > 0:
            overdue = _is_chase_time()
            nudges.append({
                "type": "vehicle_check_overdue" if overdue else "vehicle_check_due",
                "title": "Vehicle check overdue" if overdue else "Weekly vehicle check due",
                "body": (f"{due} vehicle check{'' if due == 1 else 's'} still outstanding — please complete "
                         f"{'it' if due == 1 else 'them'} now." if overdue
                         else f"{due} vehicle check{'' if due == 1 else 's'} to complete this week."),
                "link": "vehicle"})

    unread = sum(1 for n in stored if not n.get("read")) + len(nudges)
    return {"notifications": stored, "nudges": nudges, "unread": unread}


@router.post("/new-starter/portal/notifications/read")
async def portal_notifications_read(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    await db.staff_notifications.update_many(
        {"organization_id": staff["organization_id"], "recipient_kind": "employee",
         "recipient_staff_id": staff["id"], "read": False},
        {"$set": {"read": True}})
    return {"ok": True}


# ─────────────── My Details change requests (staff → HR) ───────────────
# Fields a staff member may request to change from the Staff Portal "My Details"
# tab. Value → (human label, staff_members field to also update, or None).
DETAIL_FIELDS = {
    "home_address": ("Home address", "address"),
    "dob": ("Date of birth", None),
    "ni_number": ("National Insurance number", None),
    "emergency_contact_name": ("Emergency contact name", None),
    "emergency_contact_phone": ("Emergency contact phone", None),
    "bank_name": ("Bank name", None),
    "sort_code": ("Sort code", None),
    "bank_account": ("Bank account", None),
}


class DetailChangeReq(BaseModel):
    changes: dict = {}
    note: str | None = None


class DetailRejectReq(BaseModel):
    reason: str | None = None


async def _new_starter_form(staff_id: str):
    return await db.staff_form_submissions.find_one(
        {"staff_id": staff_id, "form_key": "new_starter"})


@router.post("/new-starter/portal/detail-change-request")
async def portal_request_detail_change(body: DetailChangeReq,
                                       user: dict = Depends(get_current_user_portal)):
    """Staff submit requested changes to their own details; HR is notified to
    review and update the record. Nothing changes until HR approves."""
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    form = await _new_starter_form(staff["id"])
    cur = (form or {}).get("data") or {}
    changes: dict = {}
    for k, v in (body.changes or {}).items():
        if k not in DETAIL_FIELDS:
            continue
        newv = ("" if v is None else str(v)).strip()
        oldv = str(cur.get(k) or "")
        if newv and newv != oldv:
            changes[k] = {"old": oldv, "new": newv, "label": DETAIL_FIELDS[k][0]}
    if not changes:
        raise HTTPException(400, "No changes to submit — update at least one field.")
    req = {
        "id": str(uuid.uuid4()), "organization_id": org, "staff_id": staff["id"],
        "onboarding_case_id": (form or {}).get("onboarding_case_id"),
        "requested_by_name": staff.get("full_name"), "changes": changes,
        "note": (body.note or "").strip(), "status": "pending", "created_at": _now(),
    }
    await db.staff_detail_change_requests.insert_one(req.copy())
    fields_txt = ", ".join(c["label"] for c in changes.values())
    await notify_staff(
        org=org, recipient_kind="manager", type="detail_change_request",
        title="Staff detail change request",
        body=f"{staff.get('full_name')} requested changes to: {fields_txt}.",
        link="hr")
    # Best-effort email to owners/managers.
    try:
        from utils.email import send_email
        recips = await db.users.distinct(
            "email", {"organization_id": org, "role": {"$in": ["owner", "manager", "master_admin"]}})
        for em in [e for e in recips if e and "@" in e][:10]:
            await send_email(
                to=em, subject="Staff detail change request — action needed",
                html=(f"<p>{staff.get('full_name')} has requested changes to their details "
                      f"({fields_txt}).</p><p>Please review and update the record in "
                      f"Operations → Staffing → People.</p>"),
                organization_id=org, kind="staff_detail_change")
    except Exception:
        pass
    return {"ok": True, "request_id": req["id"], "fields": list(changes.keys())}


@router.get("/new-starter/portal/detail-change-requests")
async def portal_my_detail_requests(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    items = await db.staff_detail_change_requests.find(
        {"staff_id": staff["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"requests": items, "pending": sum(1 for r in items if r.get("status") == "pending")}


@router.get("/staffing/detail-change-requests")
async def hr_list_detail_requests(status: str = Query("pending"),
                                  user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    q: dict = {"organization_id": org}
    if status and status != "all":
        q["status"] = status
    items = await db.staff_detail_change_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in items:
        s = await db.staff_members.find_one({"id": r.get("staff_id")}, {"_id": 0, "full_name": 1, "email": 1}) or {}
        r["person"] = {"full_name": s.get("full_name"), "email": s.get("email")}
    pending = await db.staff_detail_change_requests.count_documents({"organization_id": org, "status": "pending"})
    return {"requests": items, "pending": pending}


@router.post("/staffing/detail-change-requests/{req_id}/approve")
async def hr_approve_detail_request(req_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    r = await db.staff_detail_change_requests.find_one({"id": req_id, "organization_id": org})
    if not r:
        raise HTTPException(404, "Request not found")
    if r.get("status") != "pending":
        raise HTTPException(400, "This request has already been reviewed.")
    form = await _new_starter_form(r["staff_id"])
    data = dict((form or {}).get("data") or {})
    for k, c in (r.get("changes") or {}).items():
        data[k] = c.get("new")
    if form:
        await db.staff_form_submissions.update_one(
            {"id": form["id"]}, {"$set": {"data": data, "updated_at": _now()}})
    else:
        await db.staff_form_submissions.insert_one({
            "id": str(uuid.uuid4()), "staff_id": r["staff_id"], "organization_id": org,
            "onboarding_case_id": r.get("onboarding_case_id"), "form_key": "new_starter",
            "data": data, "created_at": _now(), "updated_at": _now()})
    # Unify: write the approved values into the canonical staff_members record
    # (single source of truth) so the HR profile reflects them too.
    from utils.personal_sync import form_to_staff_patch
    changed = {k: c.get("new") for k, c in (r.get("changes") or {}).items()}
    staff_patch = form_to_staff_patch(changed)
    if staff_patch:
        staff_patch["updated_at"] = _now()
        await db.staff_members.update_one({"id": r["staff_id"]}, {"$set": staff_patch})
    await db.staff_detail_change_requests.update_one(
        {"id": req_id}, {"$set": {"status": "approved", "reviewed_by": user.get("full_name"),
                                  "reviewed_at": _now()}})
    fields_txt = ", ".join(c.get("label") for c in (r.get("changes") or {}).values())
    await notify_staff(
        org=org, recipient_kind="employee", recipient_staff_id=r["staff_id"],
        type="detail_change_approved", title="Detail change approved",
        body=f"Your requested changes ({fields_txt}) were approved and updated.", link="details")
    return {"ok": True}


@router.post("/staffing/detail-change-requests/{req_id}/reject")
async def hr_reject_detail_request(req_id: str, body: DetailRejectReq,
                                   user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    r = await db.staff_detail_change_requests.find_one({"id": req_id, "organization_id": org})
    if not r:
        raise HTTPException(404, "Request not found")
    if r.get("status") != "pending":
        raise HTTPException(400, "This request has already been reviewed.")
    reason = (body.reason or "").strip()
    await db.staff_detail_change_requests.update_one(
        {"id": req_id}, {"$set": {"status": "rejected", "reviewed_by": user.get("full_name"),
                                  "reviewed_at": _now(), "reject_reason": reason}})
    await notify_staff(
        org=org, recipient_kind="employee", recipient_staff_id=r["staff_id"],
        type="detail_change_rejected", title="Detail change not approved",
        body="Your requested detail changes were not approved."
             + (f" Reason: {reason}" if reason else " Please contact HR."), link="details")
    return {"ok": True}


def _process_headshot(raw: bytes) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(raw)); img.load(); img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((384, 384), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


async def _save_staff_photo(staff: dict, raw: bytes) -> str:
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(413, "Photo must be 12 MB or smaller")
    try:
        compressed = _process_headshot(raw)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read that image — please upload a JPG or PNG.")
    sid = staff["id"]
    path = f"{APP_NAME}/staff-photos/{sid}/{uuid.uuid4()}.jpg"
    photo_path = None
    try:
        put_object(path, compressed, "image/jpeg")
        photo_path = path
        photo_url = f"/api/staffing/staff/{sid}/photo?v={uuid.uuid4().hex[:8]}"
    except Exception:
        # Object-store outage → inline data URI so the headshot still round-trips.
        photo_url = "data:image/jpeg;base64," + base64.b64encode(compressed).decode("ascii")
    await db.staff_members.update_one(
        {"id": sid}, {"$set": {"photo_url": photo_url, "photo_path": photo_path, "updated_at": _now()}})
    return photo_url


@router.post("/new-starter/portal/photo")
async def portal_upload_photo(file: UploadFile = File(...),
                              user: dict = Depends(get_current_user_portal)):
    """Staff (and recruits during sign-up) upload/replace their own headshot."""
    staff = await _portal_staff(user)
    url = await _save_staff_photo(staff, await file.read())
    return {"photo_url": url}


@router.delete("/new-starter/portal/photo")
async def portal_delete_photo(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    await db.staff_members.update_one(
        {"id": staff["id"]}, {"$set": {"photo_url": None, "photo_path": None}})
    return {"ok": True}


@router.get("/staffing/staff/{staff_id}/photo")
async def serve_staff_photo(staff_id: str) -> Response:
    """Public streaming proxy for a staff headshot (non-sensitive; embedded in
    <img> tags in the Staff Portal and Staffing → People)."""
    rec = await db.staff_members.find_one({"id": staff_id}, {"_id": 0, "photo_path": 1})
    path = (rec or {}).get("photo_path")
    if not path:
        raise HTTPException(404, "No photo")
    try:
        data, ct = get_object(path)
    except Exception:
        raise HTTPException(404, "Photo not available")
    return Response(content=data, media_type=ct or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=600"})


def _is_owner(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("is_pulse_admin")
                or (user.get("role") or "").lower() == "owner")


@router.get("/staffing/notifications")
async def staffing_notifications(user: dict = Depends(get_current_user)):
    """Staffing console bell (managers) — new leave requests + live nudge for
    pending approvals. Line managers see items routed to them or unassigned;
    owners see the whole org."""
    _require_hr(user)
    org = _org(user)
    from routes.vehicle_checks import run_vehicle_chase
    await run_vehicle_chase(org)
    me = await db.staff_members.find_one(
        {"organization_id": org, "user_id": user.get("id")}, {"_id": 0, "id": 1})
    owner = _is_owner(user)
    if owner:
        q = {"organization_id": org, "recipient_kind": "manager"}
    else:
        q = {"organization_id": org, "recipient_kind": "manager",
             "$or": [{"recipient_user_id": user.get("id")}, {"recipient_user_id": None}]}
    stored = await db.staff_notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)

    leave_q: dict = {"organization_id": org, "status": "pending"}
    if not owner and me:
        report_ids = await db.staff_members.distinct(
            "id", {"organization_id": org, "line_manager_staff_id": me["id"]})
        leave_q["staff_id"] = {"$in": report_ids or ["__none__"]}
    pending = await db.staff_leave_requests.count_documents(leave_q)
    nudges: list[dict] = []
    if pending:
        nudges.append({
            "type": "pending_approvals", "title": "Holiday approvals waiting",
            "body": f"{pending} leave request{'' if pending == 1 else 's'} need your review.",
            "link": "leave"})

    unread = sum(1 for n in stored if not n.get("read")) + len(nudges)
    return {"notifications": stored, "nudges": nudges, "unread": unread}


@router.post("/staffing/notifications/read")
async def staffing_notifications_read(user: dict = Depends(get_current_user)):
    _require_hr(user)
    org = _org(user)
    owner = _is_owner(user)
    if owner:
        q = {"organization_id": org, "recipient_kind": "manager", "read": False}
    else:
        q = {"organization_id": org, "recipient_kind": "manager", "read": False,
             "$or": [{"recipient_user_id": user.get("id")}, {"recipient_user_id": None}]}
    await db.staff_notifications.update_many(q, {"$set": {"read": True}})
    return {"ok": True}





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
    provisioned = set(prov.get("granted_modules") or [])
    avail = await _org_available_modules(org)
    lm_name = staff.get("line_manager_name")
    if not lm_name and staff.get("line_manager_staff_id"):
        lm = await db.staff_members.find_one({"id": staff["line_manager_staff_id"]}, {"_id": 0, "full_name": 1})
        lm_name = (lm or {}).get("full_name")
    # Reflect the user's ACTUAL live access, not just the onboarding
    # provisioning record: the 4 gym modules resolve per-user via the module
    # matrix, and Service Desk / Inventory are per-user capability flags.
    org_doc = await db.organizations.find_one({"id": org})
    real = resolve_module_access(user, org_doc)

    def _granted(k: str) -> bool:
        if k in provisioned:
            return True
        if k == "service_desk":
            return bool(user.get("is_service_desk"))
        if k == "inventory":
            return bool(user.get("is_inventory"))
        return bool(real.get(k))

    modules = [{"key": k, "label": MODULE_LABELS[k], "granted": _granted(k)} for k in avail]
    any_granted = any(m["granted"] for m in modules)
    status = prov.get("status") or ("granted" if any_granted
                                    else ("awaiting_manager" if lm_name else "not_started"))
    return {
        "line_manager": lm_name,
        "status": status,
        "modules": modules,
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


# ══════════════════════════════════════════════════════════════════════════
# STAFF PORTAL — EXPENSES (monthly claim, modelled on the Pulse Fitness
# template). Guided, dummy-proof: prefilled name/department, pick a mileage
# rate + enter miles (£ auto-calcs), itemised lines with a nominal code and
# Net/VAT/Total (+ "no VAT on receipt" toggle), receipt photos with AI autofill,
# then submit → line manager approves → finance marks reimbursed.
# ══════════════════════════════════════════════════════════════════════════
EXP_MILEAGE_RATES = [
    {"key": "rate1", "label": "Personal car — first miles", "rate": 0.55},
    {"key": "rate2", "label": "Personal car — reduced rate", "rate": 0.25},
    {"key": "rate3", "label": "Company car — without fuel card", "rate": 0.17},
    {"key": "rate4", "label": "Company car — with fuel card", "rate": -0.17},
    {"key": "rate5", "label": "Tesla / electric vehicle", "rate": 0.075},
]
EXP_NOMINALS = [
    "Miscellaneous Expenses", "Airfare", "Train fares", "Hotel", "Entertaining Clients",
    "Entertaining Staff", "Meals/Drinks", "Parking, tolls and other vehicle costs", "Taxi's",
    "Stationery", "Computer consumables", "Postage", "Telecoms", "Rent", "Fuel", "Vehicle Servicing",
]
EXP_DEPARTMENTS = [
    "Accounts", "Assembly", "D&B", "Product Design", "Directors", "Install", "IT", "Marketing",
    "Production", "Quality", "Refurbishment", "Rock", "Sales", "Sales Admin", "Service",
    "Service Admin", "Stores", "Technical", "Warehouse",
]
_EXP_RATE_BY_KEY = {r["key"]: r for r in EXP_MILEAGE_RATES}


def _exp_num(v):
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return 0.0


def _exp_recalc(claim: dict) -> dict:
    mileage = []
    m_total = 0.0
    for m in (claim.get("mileage") or []):
        base = _EXP_RATE_BY_KEY.get(m.get("key"))
        if not base:
            continue
        miles = _exp_num(m.get("miles"))
        amount = round(miles * base["rate"], 2)
        m_total += amount
        mileage.append({"key": base["key"], "label": base["label"], "rate": base["rate"],
                        "miles": miles, "amount": amount})
    claim["mileage"] = mileage
    claim["mileage_total"] = round(m_total, 2)

    lines, e_total = [], 0.0
    for ln in (claim.get("lines") or []):
        net = _exp_num(ln.get("net"))
        no_vat = bool(ln.get("no_vat"))
        vat = 0.0 if no_vat else _exp_num(ln.get("vat"))
        total = round(net + vat, 2)
        e_total += total
        lines.append({"date": (ln.get("date") or "")[:10], "description": (ln.get("description") or "").strip(),
                      "nominal": ln.get("nominal") or "", "net": net, "vat": vat, "no_vat": no_vat,
                      "total": total, "receipt_id": ln.get("receipt_id")})
    claim["lines"] = lines
    claim["expenses_total"] = round(e_total, 2)
    claim["grand_total"] = round(m_total + e_total, 2)
    return claim


def _exp_public(claim: dict) -> dict:
    return {k: v for k, v in claim.items() if k not in ("_id", "receipts")}


@router.get("/new-starter/portal/expenses/config")
async def portal_expenses_config(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    return {"mileage_rates": EXP_MILEAGE_RATES, "nominals": EXP_NOMINALS, "departments": EXP_DEPARTMENTS,
            "staff": {"name": staff.get("full_name") or staff.get("name") or "",
                      "department": await _department(staff)}}


@router.get("/new-starter/portal/expenses")
async def portal_expenses_list(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    rows = await db.staff_expense_claims.find(
        {"organization_id": staff["organization_id"], "staff_person_id": staff["id"]},
        {"_id": 0, "receipts": 0, "mileage": 0, "lines": 0}).sort("created_at", -1).to_list(200)
    return {"claims": rows}


class ExpClaimCreate(BaseModel):
    claim_month: str
    car_registration: str = ""


@router.post("/new-starter/portal/expenses")
async def portal_expenses_create(body: ExpClaimCreate, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = {
        "id": str(uuid.uuid4()), "organization_id": staff["organization_id"],
        "staff_person_id": staff["id"], "staff_name": staff.get("full_name") or staff.get("name") or "",
        "department": await _department(staff), "car_registration": (body.car_registration or "").strip(),
        "claim_month": body.claim_month, "status": "draft",
        "mileage": [], "lines": [], "receipts": {},
        "mileage_total": 0.0, "expenses_total": 0.0, "grand_total": 0.0,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.staff_expense_claims.insert_one(claim.copy())
    return _exp_public(claim)


@router.get("/new-starter/portal/expenses/{claim_id}")
async def portal_expenses_get(claim_id: str, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"], "staff_person_id": staff["id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    return _exp_public(claim)


class ExpClaimUpdate(BaseModel):
    car_registration: Optional[str] = None
    claim_month: Optional[str] = None
    department: Optional[str] = None
    mileage: Optional[list] = None
    lines: Optional[list] = None


@router.put("/new-starter/portal/expenses/{claim_id}")
async def portal_expenses_update(claim_id: str, body: ExpClaimUpdate,
                                 user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"], "staff_person_id": staff["id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") not in ("draft", "rejected"):
        raise HTTPException(409, "This claim has been submitted and can't be edited.")
    if body.car_registration is not None:
        claim["car_registration"] = body.car_registration.strip()
    if body.claim_month is not None:
        claim["claim_month"] = body.claim_month
    if body.department is not None:
        claim["department"] = body.department
    if body.mileage is not None:
        claim["mileage"] = body.mileage
    if body.lines is not None:
        claim["lines"] = body.lines
    _exp_recalc(claim)
    claim["updated_at"] = _now()
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {
        "car_registration": claim["car_registration"], "claim_month": claim["claim_month"],
        "department": claim["department"], "mileage": claim["mileage"], "lines": claim["lines"],
        "mileage_total": claim["mileage_total"], "expenses_total": claim["expenses_total"],
        "grand_total": claim["grand_total"], "updated_at": claim["updated_at"]}})
    return _exp_public(claim)


@router.post("/new-starter/portal/expenses/{claim_id}/receipt")
async def portal_expenses_receipt(claim_id: str, file: UploadFile = File(...),
                                  user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"], "staff_person_id": staff["id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Receipt too large (max 15MB).")
    rid = str(uuid.uuid4())
    ext = (file.filename or "jpg").rsplit(".", 1)[-1][:5] or "jpg"
    path = f"{APP_NAME}/staff-expense-receipts/{staff['organization_id']}/{rid}.{ext}"
    put_object(path, data, file.content_type or "image/jpeg")
    receipts = claim.get("receipts") or {}
    receipts[rid] = {"path": path, "content_type": file.content_type or "image/jpeg", "filename": file.filename}
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {"receipts": receipts, "updated_at": _now()}})

    # Optional AI autofill (best-effort — never blocks the upload).
    ocr = None
    try:
        import base64 as _b64
        from routes.expenses.common import ocr_receipt
        ocr = await ocr_receipt(_b64.b64encode(data).decode("ascii"))
    except Exception:
        ocr = None
    suggestion = None
    if isinstance(ocr, dict) and ocr.get("is_receipt"):
        gross = _exp_num(ocr.get("total_amount") or 0)
        tax = _exp_num(ocr.get("tax_amount") or 0)
        suggestion = {"date": (ocr.get("date") or "")[:10],
                      "description": (ocr.get("merchant_name") or "").strip(),
                      "net": round(gross - tax, 2) if gross else 0.0, "vat": tax, "no_vat": tax == 0}
    return {"receipt_id": rid, "suggestion": suggestion}


@router.get("/new-starter/portal/expenses/{claim_id}/receipt/{receipt_id}")
async def portal_expenses_receipt_get(claim_id: str, receipt_id: str,
                                      user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    meta = (claim.get("receipts") or {}).get(receipt_id)
    if not meta:
        raise HTTPException(404, "Receipt not found")
    data = get_object(meta["path"])
    return Response(content=data, media_type=meta.get("content_type") or "image/jpeg")


@router.post("/new-starter/portal/expenses/{claim_id}/submit")
async def portal_expenses_submit(claim_id: str, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"], "staff_person_id": staff["id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") not in ("draft", "rejected"):
        raise HTTPException(409, "This claim has already been submitted.")
    if not claim.get("mileage") and not claim.get("lines"):
        raise HTTPException(400, "Add at least one mileage entry or expense line before submitting.")
    org = staff["organization_id"]
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {
        "status": "submitted", "submitted_at": _now(), "updated_at": _now(), "review_note": ""}})
    mgr_uid = await _line_manager_user_id(org, staff)
    await notify_staff(org=org, recipient_kind="manager", recipient_user_id=mgr_uid,
                       type="expense_claim", title="Expense claim to review",
                       body=f"{claim.get('staff_name')} submitted a {claim.get('claim_month')} expense claim "
                            f"for £{claim.get('grand_total', 0):.2f}.",
                       link="/staffing?tab=expenses")
    return {"status": "submitted"}


@router.delete("/new-starter/portal/expenses/{claim_id}")
async def portal_expenses_delete(claim_id: str, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    claim = await db.staff_expense_claims.find_one(
        {"id": claim_id, "organization_id": staff["organization_id"], "staff_person_id": staff["id"]})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") not in ("draft", "rejected"):
        raise HTTPException(409, "Only draft claims can be deleted.")
    await db.staff_expense_claims.delete_one({"id": claim_id})
    return {"deleted": True}


# ── Manager / finance review (platform session) ─────────────────────────────
@router.get("/new-starter/expenses/review/pending")
async def expenses_review_pending(user: dict = Depends(get_current_user)):
    if (user.get("role") not in HR_ROLES) and not user.get("is_master_admin"):
        raise HTTPException(403, "Not authorised")
    org = user.get("organization_id")
    rows = await db.staff_expense_claims.find(
        {"organization_id": org, "status": {"$in": ["submitted", "approved"]}},
        {"_id": 0, "receipts": 0}).sort("submitted_at", 1).to_list(500)
    return {"claims": rows}


class ExpReview(BaseModel):
    note: Optional[str] = ""


async def _exp_notify_owner(org: str, claim: dict, title: str, body: str):
    await notify_staff(org=org, recipient_kind="employee", recipient_staff_id=claim.get("staff_person_id"),
                       type="expense_claim", title=title, body=body, link="?tab=expenses")


@router.post("/new-starter/expenses/review/{claim_id}/approve")
async def expenses_review_approve(claim_id: str, user: dict = Depends(get_current_user)):
    if (user.get("role") not in HR_ROLES) and not user.get("is_master_admin"):
        raise HTTPException(403, "Not authorised")
    org = user.get("organization_id")
    claim = await db.staff_expense_claims.find_one({"id": claim_id, "organization_id": org})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") != "submitted":
        raise HTTPException(409, "Only submitted claims can be approved.")
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {
        "status": "approved", "approved_by": user.get("id"), "approved_at": _now(), "updated_at": _now()}})
    await _exp_notify_owner(org, claim, "Expense claim approved",
                            f"Your {claim.get('claim_month')} claim (£{claim.get('grand_total', 0):.2f}) was approved and is awaiting reimbursement.")
    return {"status": "approved"}


@router.post("/new-starter/expenses/review/{claim_id}/reject")
async def expenses_review_reject(claim_id: str, body: ExpReview, user: dict = Depends(get_current_user)):
    if (user.get("role") not in HR_ROLES) and not user.get("is_master_admin"):
        raise HTTPException(403, "Not authorised")
    org = user.get("organization_id")
    claim = await db.staff_expense_claims.find_one({"id": claim_id, "organization_id": org})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") not in ("submitted", "approved"):
        raise HTTPException(409, "This claim can't be rejected in its current state.")
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {
        "status": "rejected", "review_note": (body.note or "").strip(),
        "reviewed_by": user.get("id"), "reviewed_at": _now(), "updated_at": _now()}})
    await _exp_notify_owner(org, claim, "Expense claim returned",
                            f"Your {claim.get('claim_month')} claim was returned: {(body.note or 'please review and resubmit').strip()}")
    return {"status": "rejected"}


@router.post("/new-starter/expenses/review/{claim_id}/reimburse")
async def expenses_review_reimburse(claim_id: str, user: dict = Depends(get_current_user)):
    if (user.get("role") not in HR_ROLES) and not user.get("is_master_admin"):
        raise HTTPException(403, "Not authorised")
    org = user.get("organization_id")
    claim = await db.staff_expense_claims.find_one({"id": claim_id, "organization_id": org})
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.get("status") != "approved":
        raise HTTPException(409, "Only approved claims can be marked reimbursed.")
    await db.staff_expense_claims.update_one({"id": claim_id}, {"$set": {
        "status": "reimbursed", "reimbursed_by": user.get("id"), "reimbursed_at": _now(), "updated_at": _now()}})
    await _exp_notify_owner(org, claim, "Expense claim reimbursed",
                            f"Your {claim.get('claim_month')} claim (£{claim.get('grand_total', 0):.2f}) has been marked as paid.")
    return {"status": "reimbursed"}
