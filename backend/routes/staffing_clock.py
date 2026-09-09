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

    # Attendance Spine — keep the day's single source of truth in step with
    # the punch (best-effort; punches stand even if the recompute fails).
    try:
        from routes.attendance import recompute_day
        await recompute_day(org_id, sid, now.date().isoformat())
    except Exception:
        pass

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
    try:
        from routes.attendance import recompute_day
        await recompute_day(org_id, staff_id, occurred_at[:10])
    except Exception:
        pass
    return {"ok": True, "event": {k: v for k, v in event.items() if k != "_id"}}


# ─────────────────────── Timesheets ──────────────────────────────

def _self_day_hours(entry: dict) -> float:
    """Hours for a staff-entered day: (finish − start) − break + PT classes.
    Handles overnight (finish < start) and treats PT-class hours as additive."""
    try:
        s, f = entry.get("start"), entry.get("finish")
        base = 0.0
        if s and f:
            sh, sm = (int(x) for x in s.split(":")[:2])
            fh, fm = (int(x) for x in f.split(":")[:2])
            mins = (fh * 60 + fm) - (sh * 60 + sm)
            if mins < 0:
                mins += 24 * 60
            base = mins / 60.0
        base -= float(entry.get("break_minutes") or 0) / 60.0
        base += float(entry.get("pt_classes") or 0)
        return round(max(0.0, base), 2)
    except Exception:
        return 0.0


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
            "notes": sh.get("notes"),
            "missing_punch": (in_ev is None) or (out_ev is None),
        })

    # Merge staff-entered days (remote / no-rota staff, or extra worked time on
    # top of a shift). Stored on the persisted timesheet as `self_entries`.
    saved = await db.staff_timesheets.find_one(
        {"organization_id": org_id, "staff_id": staff_id, "week_start": week_start},
        {"_id": 0, "self_entries": 1},
    )
    self_entries = (saved or {}).get("self_entries") or {}
    self_hours = 0.0
    for d in sorted(self_entries):
        e = self_entries[d] or {}
        h = _self_day_hours(e)
        if h <= 0 and not (e.get("start") or e.get("finish")):
            continue
        self_hours += h
        total_actual += h
        line_items.append({
            "source": "self",
            "date": d,
            "scheduled_start": None, "scheduled_end": None,
            "self_start": e.get("start"), "self_finish": e.get("finish"),
            "break_minutes": int(e.get("break_minutes") or 0),
            "pt_classes": float(e.get("pt_classes") or 0),
            "scheduled_hours": 0.0,
            "actual_hours": h,
            "late_minutes": 0,
            "notes": e.get("notes"),
            "missing_punch": False,
        })
    line_items.sort(key=lambda li: (li.get("date") or ""))

    # Overtime — only meaningful against a scheduled roster; self-entry-only
    # weeks (no shifts) have no "scheduled" baseline, so they're not overtime.
    overtime_h = max(0.0, total_actual - total_scheduled) if total_scheduled > 0 else 0.0
    return {
        "staff_id": staff_id,
        "week_start": week_start,
        "week_end": week_end,
        "scheduled_hours": round(total_scheduled, 2),
        "actual_hours": round(total_actual, 2),
        "self_hours": round(self_hours, 2),
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
    st = await db.staff_members.find_one({"id": staff_id}, {"_id": 0, "weekly_hours": 1, "hours_per_week": 1})
    standard_hours = float((st or {}).get("weekly_hours") or (st or {}).get("hours_per_week") or 0)
    saved = await db.staff_timesheets.find_one(
        {"organization_id": org_id, "staff_id": staff_id, "week_start": week_start},
        {"_id": 0},
    )
    if saved:
        status = saved.get("approval_status", "pending")
        return {**saved, **live, "id": saved["id"], "approval_status": status,
                "standard_hours": standard_hours,
                "locked": status in ("submitted", "approved"),
                "employee_signature": saved.get("employee_signature"),
                "submitted_at": saved.get("submitted_at"),
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
    return {**new_doc, **live, "standard_hours": standard_hours, "locked": False}


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


@router.post("/staffing/timesheets/{ts_id}/return")
async def return_timesheet(
    ts_id: str, body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Manager sends a submitted timesheet back to the employee for edits —
    unlocks it so they can correct and re-submit."""
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_timesheets.update_one(
        {"id": ts_id, "organization_id": org_id},
        {"$set": {
            "approval_status": "returned",
            "returned_by": user.get("email"),
            "returned_at": _now().isoformat(),
            "return_reason": (body.get("reason") or "").strip() or "Please review and re-submit.",
        }},
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


# ─────────────────────── Timesheet exports (Excel / PDF) ─────────

_DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hhmm(iso: str | None) -> str:
    """ISO datetime → HH:MM (local naive), or '' if unparseable/empty."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except Exception:
        return str(iso)[11:16] if len(str(iso)) >= 16 else ""


def _paper_rows(ts: dict) -> list[dict]:
    """Collapse a timesheet's line items into a Monday→Sunday paper grid —
    one row per weekday with start/finish, break, PT classes, hours, notes."""
    from datetime import date as _date

    mon = _date.fromisoformat(ts["week_start"])
    days: dict[str, dict] = {}
    order: list[str] = []
    for i in range(7):
        d = (mon + timedelta(days=i)).isoformat()
        order.append(d)
        days[d] = {
            "day": _DOW[i], "date": d, "start": "", "finish": "",
            "break_min": 0, "pt": 0.0, "hours": 0.0, "notes": [],
        }
    for li in ts.get("line_items", []):
        d = li.get("date")
        if d not in days:
            continue
        row = days[d]
        if li.get("source") == "self":
            s, f = li.get("self_start"), li.get("self_finish")
        else:
            s = _hhmm(li.get("actual_start")) or li.get("scheduled_start") or ""
            f = _hhmm(li.get("actual_end")) or li.get("scheduled_end") or ""
        if s and not row["start"]:
            row["start"] = s
        if f:
            row["finish"] = f
        row["break_min"] += int(li.get("break_minutes") or 0)
        row["pt"] += float(li.get("pt_classes") or 0)
        row["hours"] += float(li.get("actual_hours") or 0)
        if li.get("missing_punch"):
            row["notes"].append("Missing punch")
        if li.get("notes"):
            row["notes"].append(str(li["notes"]))
    return [{**days[d], "notes": ", ".join(days[d]["notes"])} for d in order]


_TS_COLS = ["Day", "Date", "Start", "Finish", "Break (mins)", "PT classes", "Hours", "Notes"]


def _safe_sheet_title(name: str, used: set[str]) -> str:
    base = "".join(c for c in (name or "Staff") if c not in "[]:*?/\\")[:28] or "Staff"
    title = base
    n = 2
    while title in used:
        title = f"{base[:26]}_{n}"
        n += 1
    used.add(title)
    return title


def _ts_xlsx(sheets: list[dict]) -> bytes:
    """sheets: list of {name, ts}. One worksheet per timesheet."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="D0D5DD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="0B0C10")
    head_font = Font(bold=True, color="FFFFFF")
    title_font = Font(bold=True, size=14)
    label_font = Font(bold=True, color="475467")
    tot_fill = PatternFill("solid", fgColor="EEF2F6")
    used: set[str] = set()

    for sh in sheets:
        ts = sh["ts"]
        ws = wb.create_sheet(_safe_sheet_title(sh.get("sheet_title") or sh["name"], used))
        ws["A1"] = "Weekly Timesheet"
        ws["A1"].font = title_font
        ws["A2"] = "Employee:"; ws["A2"].font = label_font; ws["B2"] = sh["name"]
        ws["A3"] = "Role:"; ws["A3"].font = label_font; ws["B3"] = ts.get("primary_role") or ""
        ws["A4"] = "Week:"; ws["A4"].font = label_font
        ws["B4"] = f"{ts.get('week_start')} → {ts.get('week_end')}"
        ws["D2"] = "Status:"; ws["D2"].font = label_font; ws["E2"] = (ts.get("approval_status") or "").title()
        ws["D3"] = "Approved by:"; ws["D3"].font = label_font; ws["E3"] = ts.get("approved_by") or ""
        ws["D4"] = "Approved at:"; ws["D4"].font = label_font; ws["E4"] = (ts.get("approved_at") or "")[:16].replace("T", " ")

        hrow = 6
        for c, col in enumerate(_TS_COLS, start=1):
            cell = ws.cell(row=hrow, column=c, value=col)
            cell.fill = head_fill; cell.font = head_font; cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")
        r = hrow + 1
        for row in _paper_rows(ts):
            vals = [row["day"], row["date"], row["start"], row["finish"],
                    row["break_min"], round(row["pt"], 2), round(row["hours"], 2), row["notes"]]
            for c, v in enumerate(vals, start=1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.border = border
                if c in (3, 4, 5, 6, 7):
                    cell.alignment = Alignment(horizontal="center")
            r += 1
        # Totals row
        tot = ws.cell(row=r, column=1, value="TOTAL")
        tot.font = Font(bold=True)
        for c in range(1, 9):
            ws.cell(row=r, column=c).fill = tot_fill
            ws.cell(row=r, column=c).border = border
        ws.cell(row=r, column=5, value=round(ts.get("break_hours", 0) * 60)).alignment = Alignment(horizontal="center")
        ws.cell(row=r, column=7, value=round(ts.get("actual_hours", 0), 2)).alignment = Alignment(horizontal="center")
        ws.cell(row=r, column=7).font = Font(bold=True)

        # Summary block
        s = r + 2
        summary = [
            ("Standard hours", round(ts.get("standard_hours", 0), 2)),
            ("Scheduled hours", round(ts.get("scheduled_hours", 0), 2)),
            ("Actual hours", round(ts.get("actual_hours", 0), 2)),
            ("Overtime hours", round(ts.get("overtime_hours", 0), 2)),
            ("Pay", ts.get("payable_amount", 0)),
        ]
        for i, (lab, val) in enumerate(summary):
            ws.cell(row=s + i, column=1, value=lab).font = label_font
            ws.cell(row=s + i, column=2, value=val)

        widths = [12, 12, 9, 9, 12, 11, 9, 40]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ts_pdf(sheets: list[dict]) -> bytes:
    """sheets: list of {name, ts}. One page per timesheet."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Title"], fontSize=16, spaceAfter=4)
    meta = ParagraphStyle("m", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475467"))
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=8, leading=10)
    story: list = []

    for idx, sh in enumerate(sheets):
        ts = sh["ts"]
        if idx > 0:
            story.append(PageBreak())
        story.append(Paragraph("Weekly Timesheet", h_style))
        story.append(Paragraph(
            f"<b>{sh['name']}</b> &nbsp;·&nbsp; {ts.get('primary_role') or ''} &nbsp;·&nbsp; "
            f"Week {ts.get('week_start')} → {ts.get('week_end')} &nbsp;·&nbsp; "
            f"Status: {(ts.get('approval_status') or '').title()}"
            + (f" &nbsp;·&nbsp; Approved by {ts.get('approved_by')}" if ts.get("approved_by") else ""),
            meta,
        ))
        story.append(Spacer(1, 6))

        data = [_TS_COLS]
        for row in _paper_rows(ts):
            data.append([
                row["day"], row["date"], row["start"] or "—", row["finish"] or "—",
                str(row["break_min"]), f"{row['pt']:g}", f"{row['hours']:.2f}",
                Paragraph(row["notes"] or "", cell),
            ])
        data.append(["TOTAL", "", "", "", str(round(ts.get("break_hours", 0) * 60)), "",
                     f"{ts.get('actual_hours', 0):.2f}", ""])
        col_w = [24 * mm, 24 * mm, 18 * mm, 18 * mm, 22 * mm, 20 * mm, 18 * mm, 105 * mm]
        tbl = Table(data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B0C10")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
            ("ALIGN", (2, 0), (6, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2F6")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#FAFBFC")]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"Standard: <b>{ts.get('standard_hours', 0):g}h</b> &nbsp;|&nbsp; "
            f"Scheduled: <b>{ts.get('scheduled_hours', 0):g}h</b> &nbsp;|&nbsp; "
            f"Actual: <b>{ts.get('actual_hours', 0):g}h</b> &nbsp;|&nbsp; "
            f"Overtime: <b>{ts.get('overtime_hours', 0):g}h</b>",
            meta,
        ))

    doc.build(story)
    return buf.getvalue()


async def _enriched_ts(org_id: str, staff: dict, ws: str, we: str) -> dict:
    ts = await _ensure_timesheet_doc(org_id, staff["id"], ws, we)
    rate = float(staff.get("hourly_cost") or 0)
    ts["staff_name"] = staff.get("full_name")
    ts["primary_role"] = staff.get("primary_role")
    ts["payable_amount"] = round(ts.get("actual_hours", 0) * rate, 2)
    return ts


def _export_response(fmt: str, sheets: list[dict], filename: str):
    from fastapi.responses import Response

    fmt = (fmt or "xlsx").lower()
    if fmt == "pdf":
        return Response(
            content=_ts_pdf(sheets),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    return Response(
        content=_ts_xlsx(sheets),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )


@router.get("/staffing/timesheets/{ts_id}/export")
async def export_timesheet(
    ts_id: str,
    format: str = Query("xlsx"),
    user: dict = Depends(get_current_user),
):
    """Download ONE approved timesheet as Excel or PDF, laid out like the
    paper Mon→Sun sheet (managers only, approved only)."""
    _require_manager(user)
    org_id = _org(user)
    saved = await db.staff_timesheets.find_one(
        {"id": ts_id, "organization_id": org_id}, {"_id": 0, "staff_id": 1, "week_start": 1, "approval_status": 1},
    )
    if not saved:
        raise HTTPException(404, "Timesheet not found")
    if saved.get("approval_status") != "approved":
        raise HTTPException(400, "Only approved timesheets can be downloaded.")
    staff = await db.staff_members.find_one(
        {"id": saved["staff_id"], "organization_id": org_id},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "hourly_cost": 1},
    )
    if not staff:
        raise HTTPException(404, "Staff not found")
    ws, we = _week_bounds(saved["week_start"])
    ts = await _enriched_ts(org_id, staff, ws, we)
    name = (staff.get("full_name") or "staff").replace(" ", "_")
    return _export_response(format, [{"name": staff.get("full_name") or "Staff", "ts": ts}],
                            f"timesheet-{name}-{ws}")


@router.get("/staffing/timesheets/export-week")
async def export_week_timesheets(
    week_start: str = Query(...),
    format: str = Query("xlsx"),
    user: dict = Depends(get_current_user),
):
    """Download the whole team's APPROVED timesheets for a week as one
    Excel workbook (a sheet each) or PDF (a page each). Managers only."""
    _require_manager(user)
    org_id = _org(user)
    ws, we = _week_bounds(week_start)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "hourly_cost": 1},
    ).to_list(1000)
    sheets: list[dict] = []
    for s in sorted(staff, key=lambda x: x.get("full_name") or ""):
        ts = await _enriched_ts(org_id, s, ws, we)
        if ts.get("approval_status") == "approved":
            sheets.append({"name": s.get("full_name") or "Staff", "ts": ts})
    if not sheets:
        raise HTTPException(400, "No approved timesheets for this week yet.")
    return _export_response(format, sheets, f"timesheets-week-{ws}")


@router.get("/staffing/timesheets/payroll-pack")
async def payroll_pack(
    date_from: str = Query(..., alias="from"),
    date_to: str = Query(..., alias="to"),
    user: dict = Depends(get_current_user),
):
    """Payroll handover pack — a ZIP with ONE Excel workbook per employee,
    each containing a worksheet per APPROVED week that falls in the chosen
    date range (defaults to a calendar month on the client). Managers only."""
    import io
    import zipfile
    from datetime import date as _date

    _require_manager(user)
    org_id = _org(user)
    try:
        d_to = _date.fromisoformat(date_to)
        mon0 = _date.fromisoformat(_week_bounds(date_from)[0])
    except Exception:
        raise HTTPException(400, "Invalid date range.")
    if mon0 > d_to:
        raise HTTPException(400, "'From' date must be on or before 'To' date.")

    # Every Monday whose week overlaps the range.
    weeks: list[str] = []
    m = mon0
    while m <= d_to:
        weeks.append(m.isoformat())
        m = m + timedelta(days=7)
    if not weeks:
        raise HTTPException(400, "Empty date range.")

    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True},
        {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "hourly_cost": 1},
    ).to_list(1000)

    buf = io.BytesIO()
    used_names: set[str] = set()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in sorted(staff, key=lambda x: x.get("full_name") or ""):
            sheets: list[dict] = []
            for wk in weeks:
                ws, we = _week_bounds(wk)
                ts = await _enriched_ts(org_id, s, ws, we)
                if ts.get("approval_status") == "approved":
                    sheets.append({"name": s.get("full_name") or "Staff", "sheet_title": ws, "ts": ts})
            if not sheets:
                continue
            base = (s.get("full_name") or "staff").replace(" ", "_")
            fname = f"{base}"
            n = 2
            while fname in used_names:
                fname = f"{base}_{n}"; n += 1
            used_names.add(fname)
            zf.writestr(f"{fname}-{mon0.isoformat()}_to_{date_to}.xlsx", _ts_xlsx(sheets))
            added += 1

    if added == 0:
        raise HTTPException(400, "No approved timesheets in this date range yet.")

    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="payroll-pack-{mon0.isoformat()}_to_{date_to}.zip"'},
    )


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
