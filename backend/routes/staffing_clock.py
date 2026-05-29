"""Staffing Phase S2 — Time clock + attendance.

Focused subsystem so the existing 1429-line `staffing.py` stays
reviewable. Provides the punch-clock surface, geofence validation,
auto-built timesheets with manager approvals, and a kiosk PIN flow
for shared front-desk devices.

Endpoints
---------
Staff (anyone with a linked staff record):
    POST  /staffing/clock/punch          — clock in/out + break start/end
    GET   /staffing/clock/status         — am I clocked in? on a break?
    GET   /staffing/clock/history        — recent punches (last 30 days)
    GET   /staffing/clock/my-timesheet   — my own timesheet for a week

Manager (owner/manager/master_admin):
    GET   /staffing/clock/board          — live punch board (across staff)
    GET   /staffing/clock/events         — punch audit log
    POST  /staffing/clock/manual-edit    — operator-corrects a missed punch
    GET   /staffing/timesheets           — all timesheets for a week
    POST  /staffing/timesheets/{id}/approve
    POST  /staffing/timesheets/{id}/dispute

Kiosks (shared device):
    GET   /staffing/kiosks               — list kiosks (managers)
    POST  /staffing/kiosks               — create
    PATCH /staffing/kiosks/{id}
    DELETE /staffing/kiosks/{id}
    POST  /staffing/kiosk/punch          — staff_id + 4-digit PIN + kind

Data model
----------
- `staff_clock_events`  immutable punch log (one row per kind)
- `staff_kiosks`        shared front-desk devices (PIN-gated)
- `staff_timesheets`    derived weekly timesheet (one per staff per week)

Geofence
--------
Sites have optional `latitude`, `longitude`, `geofence_radius_m`. On
mobile clock-in, GPS coords are checked against the site's centre;
within radius → ok, outside → soft warning (operators can still
approve), >5km → hard reject (likely wrong site or spoof).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

# Re-use the helpers defined in staffing.py to keep behaviour identical.
from routes.staffing import (
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
    _shift_hours,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────── Constants / models ──────────────────────

VALID_PUNCH_KINDS = {"clock_in", "clock_out", "break_start", "break_end"}
HARD_REJECT_DISTANCE_KM = 5.0    # >5km from site → punch rejected
APPROVAL_STATES = {"pending", "approved", "disputed"}


class PunchBody(BaseModel):
    kind: str
    shift_id: str | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    accuracy_m: float | None = None
    site_id: str | None = None
    notes: str | None = None


class KioskCreate(BaseModel):
    name: str
    site_id: str | None = None
    pin: str = Field(min_length=4, max_length=6)


class KioskUpdate(BaseModel):
    name: str | None = None
    site_id: str | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=6)
    active: bool | None = None


class KioskPunchBody(BaseModel):
    kiosk_id: str
    pin: str
    staff_id: str
    kind: str


# ─────────────────────── Helpers ─────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = (math.sin(dp / 2) ** 2) + math.cos(p1) * math.cos(p2) * (math.sin(dl / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _resolve_site(org_id: str, site_id: str | None) -> dict | None:
    if not site_id:
        return None
    return await db.sites.find_one(
        {"id": site_id, "organization_id": org_id},
        {"_id": 0, "id": 1, "name": 1, "latitude": 1, "longitude": 1, "geofence_radius_m": 1},
    )


async def _last_clock_event(staff_id: str, org_id: str) -> dict | None:
    return await db.staff_clock_events.find_one(
        {"staff_id": staff_id, "organization_id": org_id},
        {"_id": 0},
        sort=[("occurred_at", -1)],
    )


def _state_from_event(ev: dict | None) -> str:
    """Walk the punch FSM. clock_in → on_shift; break_start → on_break;
    break_end → on_shift; clock_out → off."""
    if not ev:
        return "off"
    k = ev.get("kind")
    if k == "clock_in" or k == "break_end":
        return "on_shift"
    if k == "break_start":
        return "on_break"
    return "off"


def _validate_transition(state: str, new_kind: str) -> str | None:
    """Return error string or None if the transition is valid."""
    legal = {
        "off":      {"clock_in"},
        "on_shift": {"clock_out", "break_start"},
        "on_break": {"break_end", "clock_out"},
    }.get(state, set())
    if new_kind not in legal:
        nice = {
            "off":      "You're not clocked in.",
            "on_shift": "You're already clocked in.",
            "on_break": "You're on a break — end it first.",
        }.get(state, "Punch not allowed in current state.")
        return nice
    return None


def _week_bounds(any_day_iso: str) -> tuple[str, str]:
    """Monday → Sunday window for the week containing the given date."""
    d = datetime.fromisoformat(any_day_iso).date()
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon.isoformat(), sun.isoformat()


# ─────────────────────── Punch endpoints ────────────────────────

@router.post("/staffing/clock/punch")
async def clock_punch(body: PunchBody, user: dict = Depends(get_current_user)):
    """Record a clock event for the calling staff member.

    Validates the FSM transition, geofences against the site (if the
    site has lat/lng configured), and stamps the event in the
    immutable `staff_clock_events` log. Also stamps the linked shift
    (`clocked_in_at`, `clocked_out_at`) so the rota reflects reality.
    """
    org_id = _org(user)
    if body.kind not in VALID_PUNCH_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(VALID_PUNCH_KINDS)}")
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(403, "No staff record linked to your account — ask a manager to add you.")

    last = await _last_clock_event(sid, org_id)
    state = _state_from_event(last)
    err = _validate_transition(state, body.kind)
    if err:
        raise HTTPException(409, err)

    # Geofence + distance audit
    distance_km: float | None = None
    geo_warning: str | None = None
    site_doc = await _resolve_site(org_id, body.site_id)
    if site_doc and body.gps_lat is not None and body.gps_lng is not None:
        s_lat = site_doc.get("latitude")
        s_lng = site_doc.get("longitude")
        if isinstance(s_lat, (int, float)) and isinstance(s_lng, (int, float)):
            distance_km = round(
                _haversine_km(float(s_lat), float(s_lng), body.gps_lat, body.gps_lng),
                3,
            )
            radius_m = float(site_doc.get("geofence_radius_m") or 0)
            if distance_km * 1000 > HARD_REJECT_DISTANCE_KM * 1000:
                raise HTTPException(
                    400,
                    f"You appear to be {distance_km:.1f}km from {site_doc.get('name') or 'the site'}. "
                    "Punch rejected — wrong site, or contact your manager.",
                )
            if radius_m and (distance_km * 1000) > radius_m:
                geo_warning = (
                    f"Outside the {int(radius_m)}m geofence "
                    f"({int(distance_km*1000)}m from site)."
                )

    event_id = str(uuid4())
    now = _now()
    event = {
        "id": event_id,
        "organization_id": org_id,
        "staff_id": sid,
        "shift_id": body.shift_id,
        "kind": body.kind,
        "occurred_at": now.isoformat(),
        "gps_lat": body.gps_lat,
        "gps_lng": body.gps_lng,
        "accuracy_m": body.accuracy_m,
        "distance_from_site_m": int(distance_km * 1000) if distance_km is not None else None,
        "site_id": body.site_id,
        "source": "mobile",
        "geo_warning": geo_warning,
        "notes": body.notes,
        "created_by_user_id": user.get("id"),
    }
    await db.staff_clock_events.insert_one(event.copy())

    # Update the linked shift if any (best-effort — punches stand even if no shift)
    if body.shift_id:
        if body.kind == "clock_in":
            await db.staff_shifts.update_one(
                {"id": body.shift_id, "organization_id": org_id},
                {"$set": {"clocked_in_at": now.isoformat()}},
            )
        elif body.kind == "clock_out":
            await db.staff_shifts.update_one(
                {"id": body.shift_id, "organization_id": org_id},
                {"$set": {"clocked_out_at": now.isoformat(), "status": "completed"}},
            )

    return {
        "ok": True,
        "event": {k: v for k, v in event.items() if k != "_id"},
        "state": _state_from_event(event),
        "geo_warning": geo_warning,
    }


@router.get("/staffing/clock/status")
async def clock_status(user: dict = Depends(get_current_user)):
    """Current punch state for the calling staff member."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        return {"state": "off", "linked": False}
    last = await _last_clock_event(sid, org_id)
    state = _state_from_event(last)
    # Find today's scheduled shift for context
    today = _now().date().isoformat()
    todays_shift = await db.staff_shifts.find_one(
        {
            "organization_id": org_id,
            "staff_id": sid,
            "date": today,
            "status": {"$nin": ["cancelled", "completed"]},
        },
        {"_id": 0},
    )
    return {
        "state": state,
        "linked": True,
        "staff_id": sid,
        "last_event": last,
        "todays_shift": todays_shift,
    }


@router.get("/staffing/clock/history")
async def clock_history(
    days: int = Query(30, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    """Recent punches for the calling staff member."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        return {"events": []}
    since = (_now() - timedelta(days=days)).isoformat()
    rows = await db.staff_clock_events.find(
        {"organization_id": org_id, "staff_id": sid, "occurred_at": {"$gte": since}},
        {"_id": 0},
    ).sort("occurred_at", -1).to_list(500)
    return {"events": rows}


# ─────────────────────── Manager — clock board / audit ───────────

@router.get("/staffing/clock/board")
async def clock_board(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Live snapshot — every staff member's current punch state.

    Returns one row per active staff member with: their last event,
    derived state, today's scheduled shift (if any), and a `late`
    flag (scheduled to be in but no clock_in yet).

    Iter 216h63 (h) — `site_id` filters the board to staff allocated
    to the requested site. Staff with empty `allowed_site_ids` (i.e.
    org-wide access — owners + managers) always appear.
    """
    _require_manager(user)
    org_id = _org(user)
    now = _now()
    today = now.date().isoformat()
    now_hm = now.strftime("%H:%M")

    # Iter 216h63 — when site_id is provided we need to intersect
    # `staff_members` against `users.allowed_site_ids`. staff_members
    # rows carry a `user_id` for clocked employees; legacy rows without
    # a user_id (manually-added engineers, kiosk-only staff) are treated
    # as org-wide for now.
    staff_filter: dict = {"organization_id": org_id, "active": True}
    if site_id:
        # Find every user that's allocated to this site OR has no site
        # restriction at all.
        scoped_users = await db.users.find(
            {
                "organization_id": org_id,
                "$or": [
                    {"allowed_site_ids": site_id},
                    {"allowed_site_ids": {"$exists": False}},
                    {"allowed_site_ids": {"$size": 0}},
                    {"role": {"$in": ["owner", "manager"]}},
                ],
            },
            {"_id": 0, "id": 1},
        ).to_list(2000)
        allowed_user_ids = {u["id"] for u in scoped_users}
        # Accept staff rows where user_id matches OR there's no user_id
        # link (legacy/kiosk-only members are org-wide).
        staff_filter = {
            "organization_id": org_id,
            "active": True,
            "$or": [
                {"user_id": {"$in": list(allowed_user_ids)}},
                {"user_id": {"$exists": False}},
                {"user_id": None},
            ],
        }

    staff = await db.staff_members.find(
        staff_filter,
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "user_id": 1},
    ).to_list(1000)
    if not staff:
        return {"as_of": now.isoformat(), "rows": [], "summary": {"on_shift": 0, "on_break": 0, "off": 0, "late": 0}}

    # Pull most recent event per staff in one batch
    staff_ids = [s["id"] for s in staff]
    pipeline = [
        {"$match": {"organization_id": org_id, "staff_id": {"$in": staff_ids}}},
        {"$sort": {"occurred_at": -1}},
        {"$group": {"_id": "$staff_id", "last": {"$first": "$$ROOT"}}},
    ]
    last_by_staff: dict[str, dict] = {}
    async for grp in db.staff_clock_events.aggregate(pipeline):
        last = grp.get("last") or {}
        last.pop("_id", None)
        last_by_staff[grp["_id"]] = last

    # Today's shifts in one go
    todays = await db.staff_shifts.find(
        {"organization_id": org_id, "date": today, "status": {"$ne": "cancelled"}},
        {"_id": 0},
    ).to_list(1000)
    shift_by_staff: dict[str, dict] = {}
    for sh in todays:
        if sh.get("staff_id"):
            shift_by_staff[sh["staff_id"]] = sh

    rows = []
    summary = {"on_shift": 0, "on_break": 0, "off": 0, "late": 0}
    for s in staff:
        last = last_by_staff.get(s["id"])
        state = _state_from_event(last)
        sh = shift_by_staff.get(s["id"])
        late = False
        if sh and state == "off":
            try:
                if sh.get("start_time") and sh["start_time"] <= now_hm <= sh.get("end_time", "23:59"):
                    late = True
            except Exception:  # defensive
                pass
        if late:
            summary["late"] += 1
        summary[state] += 1
        rows.append({
            "staff_id": s["id"],
            "staff_name": s.get("full_name"),
            "primary_role": s.get("primary_role"),
            "state": state,
            "last_event": last,
            "todays_shift": sh,
            "late": late,
        })
    rows.sort(key=lambda r: (
        # on shift first, then on break, then late, then everyone else
        {"on_shift": 0, "on_break": 1}.get(r["state"], 9 if not r["late"] else 2),
        r.get("staff_name") or "",
    ))
    return {"as_of": now.isoformat(), "rows": rows, "summary": summary}


@router.get("/staffing/clock/events")
async def clock_events(
    staff_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if staff_id:
        q["staff_id"] = staff_id
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = (datetime.fromisoformat(date_to) + timedelta(days=1)).isoformat()
        q["occurred_at"] = rng
    rows = await db.staff_clock_events.find(q, {"_id": 0}).sort("occurred_at", -1).limit(2000).to_list(2000)
    return {"events": rows, "count": len(rows)}


@router.post("/staffing/clock/manual-edit")
async def manual_edit(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Manager fixes a missed punch — creates a `source: manual` event
    with an audit pointer to the operator. Required: staff_id + kind +
    occurred_at (ISO). Optional: shift_id, notes."""
    _require_manager(user)
    org_id = _org(user)
    kind = (body.get("kind") or "").lower()
    if kind not in VALID_PUNCH_KINDS:
        raise HTTPException(400, "invalid kind")
    staff_id = body.get("staff_id")
    occurred_at = body.get("occurred_at")
    if not staff_id or not occurred_at:
        raise HTTPException(400, "staff_id and occurred_at are required")
    try:
        datetime.fromisoformat(occurred_at)
    except ValueError as err:
        raise HTTPException(400, "occurred_at must be ISO-8601") from err
    event = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": staff_id,
        "shift_id": body.get("shift_id"),
        "kind": kind,
        "occurred_at": occurred_at,
        "source": "manual",
        "edited_by": user.get("email"),
        "edited_by_user_id": user.get("id"),
        "notes": body.get("notes"),
        "created_at": _now().isoformat(),
    }
    await db.staff_clock_events.insert_one(event.copy())
    return {"ok": True, "event": {k: v for k, v in event.items() if k != "_id"}}


# ─────────────────────── Timesheets ──────────────────────────────

async def _build_weekly_timesheet(
    org_id: str, staff_id: str, week_start: str, week_end: str,
) -> dict:
    """Reconstruct a timesheet from clock events + scheduled shifts.

    For each shift in the week, pair up the clock_in / clock_out events
    that fall closest to the shift window. Compute scheduled vs actual
    hours, late minutes, break minutes, overtime hours.
    """
    shifts = await db.staff_shifts.find(
        {
            "organization_id": org_id,
            "staff_id": staff_id,
            "date": {"$gte": week_start, "$lte": week_end},
            "status": {"$nin": ["cancelled"]},
        },
        {"_id": 0},
    ).sort([("date", 1), ("start_time", 1)]).to_list(200)

    # Pull all events for the week (slight buffer for early/late punches)
    win_start = (datetime.fromisoformat(week_start) - timedelta(hours=12)).isoformat()
    win_end = (datetime.fromisoformat(week_end) + timedelta(days=1, hours=12)).isoformat()
    events = await db.staff_clock_events.find(
        {
            "organization_id": org_id,
            "staff_id": staff_id,
            "occurred_at": {"$gte": win_start, "$lte": win_end},
        },
        {"_id": 0},
    ).sort("occurred_at", 1).to_list(2000)

    line_items: list[dict] = []
    total_scheduled = 0.0
    total_actual = 0.0
    total_break = 0.0
    total_late_min = 0
    for sh in shifts:
        sched_h = _shift_hours(sh)
        # Find the clock-in nearest the scheduled start (±2h)
        try:
            sch_start_dt = datetime.fromisoformat(f"{sh['date']}T{sh['start_time']}:00+00:00")
            sch_end_dt = datetime.fromisoformat(f"{sh['date']}T{sh['end_time']}:00+00:00")
        except Exception:
            sch_start_dt = sch_end_dt = None
        in_ev = next(
            (e for e in events if e["kind"] == "clock_in" and sch_start_dt
             and abs((datetime.fromisoformat(e["occurred_at"]) - sch_start_dt).total_seconds()) < 7200),
            None,
        )
        out_ev = None
        if in_ev and sch_end_dt:
            out_ev = next(
                (e for e in events if e["kind"] == "clock_out"
                 and datetime.fromisoformat(e["occurred_at"]) >= datetime.fromisoformat(in_ev["occurred_at"])
                 and (datetime.fromisoformat(e["occurred_at"]) - sch_end_dt).total_seconds() < 7200 * 2),
                None,
            )
        # Break events between in_ev and out_ev
        break_minutes = 0
        if in_ev and out_ev:
            in_t = datetime.fromisoformat(in_ev["occurred_at"])
            out_t = datetime.fromisoformat(out_ev["occurred_at"])
            bs: datetime | None = None
            for e in events:
                if e.get("occurred_at"):
                    et = datetime.fromisoformat(e["occurred_at"])
                else:
                    continue
                if not (in_t <= et <= out_t):
                    continue
                if e["kind"] == "break_start":
                    bs = et
                elif e["kind"] == "break_end" and bs:
                    break_minutes += int((et - bs).total_seconds() / 60)
                    bs = None
        actual_h = 0.0
        late_min = 0
        if in_ev and out_ev:
            in_t = datetime.fromisoformat(in_ev["occurred_at"])
            out_t = datetime.fromisoformat(out_ev["occurred_at"])
            actual_h = max(0.0, ((out_t - in_t).total_seconds() / 3600.0) - (break_minutes / 60.0))
            if sch_start_dt:
                late_min = max(0, int((in_t - sch_start_dt).total_seconds() / 60))
        total_scheduled += sched_h
        total_actual += actual_h
        total_break += break_minutes / 60.0
        total_late_min += late_min
        line_items.append({
            "shift_id": sh.get("id"),
            "date": sh.get("date"),
            "scheduled_start": sh.get("start_time"),
            "scheduled_end": sh.get("end_time"),
            "actual_start": in_ev["occurred_at"] if in_ev else None,
            "actual_end": out_ev["occurred_at"] if out_ev else None,
            "scheduled_hours": round(sched_h, 2),
            "actual_hours": round(actual_h, 2),
            "break_minutes": break_minutes,
            "late_minutes": late_min,
            "missing_punch": (in_ev is None) or (out_ev is None),
        })

    # Overtime — if more than scheduled, count the diff (simple model)
    overtime_h = max(0.0, total_actual - total_scheduled)
    return {
        "staff_id": staff_id,
        "week_start": week_start,
        "week_end": week_end,
        "scheduled_hours": round(total_scheduled, 2),
        "actual_hours": round(total_actual, 2),
        "break_hours": round(total_break, 2),
        "overtime_hours": round(overtime_h, 2),
        "late_total_minutes": total_late_min,
        "line_items": line_items,
    }


async def _ensure_timesheet_doc(
    org_id: str, staff_id: str, week_start: str, week_end: str,
) -> dict:
    """Build the live timesheet and merge with the persisted approval state."""
    live = await _build_weekly_timesheet(org_id, staff_id, week_start, week_end)
    saved = await db.staff_timesheets.find_one(
        {"organization_id": org_id, "staff_id": staff_id, "week_start": week_start},
        {"_id": 0},
    )
    if saved:
        return {**saved, **live, "id": saved["id"], "approval_status": saved.get("approval_status", "pending"),
                "approved_by": saved.get("approved_by"),
                "approved_at": saved.get("approved_at"),
                "dispute_reason": saved.get("dispute_reason")}
    # Create a pending row so managers can approve.
    new_doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": staff_id,
        "week_start": week_start,
        "week_end": week_end,
        "approval_status": "pending",
        "created_at": _now().isoformat(),
    }
    await db.staff_timesheets.insert_one(new_doc.copy())
    return {**new_doc, **live}


@router.get("/staffing/clock/my-timesheet")
async def my_timesheet(
    week_start: str = Query(...),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(403, "No staff record linked to your account.")
    ws, we = _week_bounds(week_start)
    return await _ensure_timesheet_doc(org_id, sid, ws, we)


@router.get("/staffing/timesheets")
async def list_timesheets(
    week_start: str = Query(...),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Manager view — every active staff member gets a timesheet row."""
    _require_manager(user)
    org_id = _org(user)
    ws, we = _week_bounds(week_start)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "hourly_cost": 1},
    ).to_list(1000)
    out = []
    for s in staff:
        ts = await _ensure_timesheet_doc(org_id, s["id"], ws, we)
        rate = float(s.get("hourly_cost") or 0)
        ts["staff_name"] = s.get("full_name")
        ts["primary_role"] = s.get("primary_role")
        ts["hourly_cost"] = rate
        ts["payable_amount"] = round(ts.get("actual_hours", 0) * rate, 2)
        if status and ts.get("approval_status") != status:
            continue
        out.append(ts)
    out.sort(key=lambda t: t.get("staff_name") or "")
    return {"week_start": ws, "week_end": we, "timesheets": out, "count": len(out)}


@router.post("/staffing/timesheets/{ts_id}/approve")
async def approve_timesheet(
    ts_id: str, body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_timesheets.update_one(
        {"id": ts_id, "organization_id": org_id},
        {"$set": {
            "approval_status": "approved",
            "approved_by": user.get("email"),
            "approved_at": _now().isoformat(),
            "approval_notes": body.get("notes"),
        }, "$unset": {"dispute_reason": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Timesheet not found")
    return {"ok": True}


@router.post("/staffing/timesheets/{ts_id}/dispute")
async def dispute_timesheet(
    ts_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Either staff (about their own) or managers can flag a dispute."""
    org_id = _org(user)
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "reason is required")
    ts = await db.staff_timesheets.find_one(
        {"id": ts_id, "organization_id": org_id},
        {"_id": 0},
    )
    if not ts:
        raise HTTPException(404, "Timesheet not found")
    if not _is_manager(user):
        # Staff can only dispute their own
        sid = await _my_staff_id_async(user, org_id)
        if ts.get("staff_id") != sid:
            raise HTTPException(403, "Not your timesheet")
    await db.staff_timesheets.update_one(
        {"id": ts_id, "organization_id": org_id},
        {"$set": {
            "approval_status": "disputed",
            "dispute_reason": reason,
            "disputed_by": user.get("email"),
            "disputed_at": _now().isoformat(),
        }},
    )
    return {"ok": True}


# ─────────────────────── Kiosks ──────────────────────────────────

# Kiosks store the PIN as a plain 4-6 digit because they're shared
# devices physically secured by the front desk; we still keep them
# scoped per-kiosk so a kiosk can be revoked individually.

@router.get("/staffing/kiosks")
async def list_kiosks(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    rows = await db.staff_kiosks.find(
        {"organization_id": org_id, "active": {"$ne": False}},
        {"_id": 0, "pin": 0},
    ).sort("name", 1).to_list(100)
    return {"kiosks": rows}


@router.post("/staffing/kiosks")
async def create_kiosk(body: KioskCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    if not body.pin.isdigit():
        raise HTTPException(400, "PIN must be all digits")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "name": body.name.strip(),
        "site_id": body.site_id,
        "pin": body.pin,
        "active": True,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    }
    await db.staff_kiosks.insert_one(doc.copy())
    return {k: v for k, v in doc.items() if k not in {"_id", "pin"}}


@router.patch("/staffing/kiosks/{kiosk_id}")
async def update_kiosk(
    kiosk_id: str, body: KioskUpdate, user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "pin" in patch and not patch["pin"].isdigit():
        raise HTTPException(400, "PIN must be all digits")
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_kiosks.update_one(
        {"id": kiosk_id, "organization_id": org_id},
        {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "kiosk not found")
    doc = await db.staff_kiosks.find_one({"id": kiosk_id, "organization_id": org_id}, {"_id": 0, "pin": 0})
    return doc


@router.delete("/staffing/kiosks/{kiosk_id}")
async def delete_kiosk(kiosk_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_kiosks.update_one(
        {"id": kiosk_id, "organization_id": org_id},
        {"$set": {"active": False, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "kiosk not found")
    return {"ok": True}


@router.post("/staffing/kiosk/punch")
async def kiosk_punch(body: KioskPunchBody):
    """Public-ish endpoint: kiosk_id + pin + staff_id + kind. No auth
    token required because kiosks are shared devices — the PIN gates
    access. We still scope every write by org_id from the kiosk doc."""
    if body.kind not in VALID_PUNCH_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(VALID_PUNCH_KINDS)}")
    kiosk = await db.staff_kiosks.find_one(
        {"id": body.kiosk_id, "active": {"$ne": False}}, {"_id": 0},
    )
    if not kiosk or kiosk.get("pin") != body.pin:
        raise HTTPException(401, "Invalid kiosk or PIN")
    org_id = kiosk["organization_id"]
    staff = await db.staff_members.find_one(
        {"id": body.staff_id, "organization_id": org_id, "active": True},
        {"_id": 0, "id": 1, "full_name": 1},
    )
    if not staff:
        raise HTTPException(404, "Staff not found")

    # Re-use the FSM
    last = await _last_clock_event(staff["id"], org_id)
    state = _state_from_event(last)
    err = _validate_transition(state, body.kind)
    if err:
        raise HTTPException(409, err)

    now = _now()
    event = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": staff["id"],
        "shift_id": None,
        "kind": body.kind,
        "occurred_at": now.isoformat(),
        "source": "kiosk",
        "kiosk_id": kiosk["id"],
        "site_id": kiosk.get("site_id"),
    }
    await db.staff_clock_events.insert_one(event.copy())
    await db.staff_kiosks.update_one(
        {"id": kiosk["id"]}, {"$set": {"last_seen_at": now.isoformat()}},
    )
    return {
        "ok": True,
        "staff_name": staff.get("full_name"),
        "state": _state_from_event(event),
        "kind": body.kind,
        "at": now.isoformat(),
    }


@router.get("/staffing/kiosk/{kiosk_id}/staff")
async def kiosk_staff_directory(kiosk_id: str, pin: str = Query(...)):
    """Staff list for a single kiosk so the device can render the
    selection grid without an operator JWT. PIN-gated."""
    kiosk = await db.staff_kiosks.find_one(
        {"id": kiosk_id, "active": {"$ne": False}}, {"_id": 0},
    )
    if not kiosk or kiosk.get("pin") != pin:
        raise HTTPException(401, "Invalid kiosk or PIN")
    org_id = kiosk["organization_id"]
    rows = await db.staff_members.find(
        {"organization_id": org_id, "active": True},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1},
    ).sort("full_name", 1).to_list(500)
    # Decorate with each staff member's current state.
    out = []
    for s in rows:
        last = await _last_clock_event(s["id"], org_id)
        out.append({**s, "state": _state_from_event(last)})
    return {"kiosk_name": kiosk.get("name"), "site_id": kiosk.get("site_id"), "staff": out}
