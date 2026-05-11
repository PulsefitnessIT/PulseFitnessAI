"""Tour-calendar booking flow for public member signup.

Powers the slot picker on `/m/{slug}/join` and the operator-side
"Upcoming tour bookings" panel inside the Memberships module.

Endpoints:
  • GET    /api/public/signup/{slug}/tour-config        public — sensible defaults applied
  • GET    /api/public/signup/{slug}/tour-slots         public — next 14 days of bookable slots
  • POST   /api/public/signup/{slug}/draft/{id}/book-tour
  • POST   /api/public/signup/{slug}/draft/{id}/cancel-tour
  • GET    /api/memberships/tour-config                 operator — fetch / fall back to defaults
  • PUT    /api/memberships/tour-config                 operator — overwrite the weekly schedule
  • GET    /api/memberships/tour-bookings               operator — upcoming list
  • POST   /api/memberships/tour-bookings/{id}/cancel   operator — cancel on behalf of member
  • POST   /api/memberships/tour-bookings/{id}/attended

Schema notes:
  • tour_configs are PER-ORG (`organization_id` is the document id). Falling back to
    defaults means an org that never configured anything still has a working slot
    grid — Mon-Fri 10:00-16:00, 30-min slots, capacity 1, 4-hour lead time.
  • tour_bookings store a denormalised `member_email/name` so the operator panel can
    render without joining users — the user is created downstream by the signup
    flow after payment, so we can't rely on `member_id` being set at booking time.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from utils.auth import get_current_user
from utils.database import db

log = logging.getLogger("tour_bookings")
router = APIRouter(tags=["tour-bookings"])


# ── Defaults / helpers ───────────────────────────────────────────────────

DEFAULT_TOUR_CONFIG = {
    "weekly_schedule": [
        {"weekday": 1, "start": "10:00", "end": "16:00"},  # Monday
        {"weekday": 2, "start": "10:00", "end": "16:00"},
        {"weekday": 3, "start": "10:00", "end": "16:00"},
        {"weekday": 4, "start": "10:00", "end": "16:00"},
        {"weekday": 5, "start": "10:00", "end": "16:00"},  # Friday
    ],
    "slot_duration_minutes": 30,
    "capacity_per_slot": 1,
    "lead_time_hours": 4,
    "ahead_window_days": 14,
    "blackout_dates": [],
    "location": "Reception",
    "timezone": "Europe/London",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _resolve_gym_by_slug(slug: str) -> dict:
    """Match by slug OR org-id (same convention as public_signup)."""
    slug_clean = (slug or "").strip().lower()
    if not slug_clean:
        raise HTTPException(400, "slug required")
    gym = await db.organizations.find_one(
        {"$or": [{"slug": slug_clean}, {"id": slug_clean}]},
        {"_id": 0, "id": 1, "name": 1, "slug": 1},
    )
    if not gym:
        raise HTTPException(404, "Gym not found")
    return gym


async def _fetch_config(org_id: str) -> dict:
    doc = await db.tour_configs.find_one({"organization_id": org_id}, {"_id": 0})
    if not doc:
        return {**DEFAULT_TOUR_CONFIG, "organization_id": org_id, "_is_default": True}
    # Merge defaults so a partial config still resolves the missing keys.
    merged = {**DEFAULT_TOUR_CONFIG, **doc}
    merged["_is_default"] = False
    return merged


def _generate_slots(cfg: dict, start: datetime, end: datetime) -> list[dict]:
    """Build the cartesian product of (date, weekday-schedule-window, slot-step).

    Returns a list of `{slot_at: ISO, duration_minutes: int}` covering the
    window. Does NOT filter by capacity / lead-time — caller does that.
    """
    schedule_by_wd: dict[int, list[tuple[str, str]]] = {}
    for entry in cfg.get("weekly_schedule") or []:
        wd = int(entry.get("weekday", -1))
        if wd < 0 or wd > 6:
            continue
        schedule_by_wd.setdefault(wd, []).append(
            (entry.get("start", "10:00"), entry.get("end", "16:00")),
        )
    duration = int(cfg.get("slot_duration_minutes", 30))
    blackout = set(cfg.get("blackout_dates") or [])

    slots: list[dict] = []
    cursor = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while cursor.date() <= end.date():
        date_str = cursor.date().isoformat()
        if date_str in blackout:
            cursor += timedelta(days=1)
            continue
        # Python weekday: Mon=0 .. Sun=6 — bump to match our Mon=1..Sun=7 schema.
        wd = cursor.weekday() + 1
        if wd == 8:
            wd = 0  # never used but kept defensive
        for win_start, win_end in schedule_by_wd.get(wd, []):
            try:
                sh, sm = (int(x) for x in win_start.split(":"))
                eh, em = (int(x) for x in win_end.split(":"))
            except (ValueError, AttributeError):
                continue
            window_start = cursor.replace(hour=sh, minute=sm, second=0, microsecond=0)
            window_end = cursor.replace(hour=eh, minute=em, second=0, microsecond=0)
            step = window_start
            while step + timedelta(minutes=duration) <= window_end:
                slots.append({
                    "slot_at": _iso(step),
                    "duration_minutes": duration,
                })
                step += timedelta(minutes=duration)
        cursor += timedelta(days=1)
    return slots


# ── Public: config + slots ───────────────────────────────────────────────


@router.get("/public/signup/{slug}/tour-config")
async def public_tour_config(slug: str = Path(...)) -> dict:
    gym = await _resolve_gym_by_slug(slug)
    cfg = await _fetch_config(gym["id"])
    return {
        "location": cfg.get("location"),
        "slot_duration_minutes": cfg.get("slot_duration_minutes"),
        "lead_time_hours": cfg.get("lead_time_hours"),
        "ahead_window_days": cfg.get("ahead_window_days"),
        "timezone": cfg.get("timezone"),
    }


@router.get("/public/signup/{slug}/tour-slots")
async def public_tour_slots(slug: str = Path(...)) -> dict:
    """Return the next N days of bookable slots, grouped by date.

    Filters out: past slots (after lead-time), full slots (capacity exceeded),
    blackout dates. Each slot returns an opaque `slot_at` ISO that the booking
    endpoint accepts back unchanged — keeps the contract simple.
    """
    gym = await _resolve_gym_by_slug(slug)
    cfg = await _fetch_config(gym["id"])
    now = _now()
    lead_cutoff = now + timedelta(hours=int(cfg.get("lead_time_hours", 4)))
    window_end = now + timedelta(days=int(cfg.get("ahead_window_days", 14)))

    candidates = _generate_slots(cfg, lead_cutoff, window_end)
    if not candidates:
        return {"location": cfg.get("location"), "slots_by_date": {}, "total": 0}

    # Tally existing bookings within the window so we can apply capacity.
    bookings = await db.tour_bookings.find(
        {
            "organization_id": gym["id"],
            "status": "booked",
            "slot_at": {"$gte": _iso(lead_cutoff), "$lte": _iso(window_end)},
        },
        {"_id": 0, "slot_at": 1},
    ).to_list(length=2000)
    cap = max(1, int(cfg.get("capacity_per_slot", 1)))
    booked_count: dict[str, int] = {}
    for b in bookings:
        key = b.get("slot_at") or ""
        booked_count[key] = booked_count.get(key, 0) + 1

    available: list[dict] = []
    for s in candidates:
        if s["slot_at"] <= _iso(lead_cutoff):
            continue
        if booked_count.get(s["slot_at"], 0) >= cap:
            continue
        available.append(s)

    # Group by date for easy rendering — frontend renders one column per day.
    by_date: dict[str, list[dict]] = {}
    for s in available:
        date_key = s["slot_at"][:10]
        by_date.setdefault(date_key, []).append(s)
    return {
        "location": cfg.get("location"),
        "duration_minutes": cfg.get("slot_duration_minutes"),
        "lead_time_hours": cfg.get("lead_time_hours"),
        "slots_by_date": by_date,
        "total": len(available),
    }


@router.post("/public/signup/{slug}/draft/{draft_id}/book-tour")
async def public_book_tour(
    slug: str = Path(...),
    draft_id: str = Path(...),
    body: dict = Body(...),
) -> dict:
    """Reserve a slot. Idempotent on `(draft_id, slot_at)` — re-booking the same
    slot for the same draft is a no-op (returns the existing booking id)."""
    gym = await _resolve_gym_by_slug(slug)
    cfg = await _fetch_config(gym["id"])

    draft = await db.signup_drafts.find_one(
        {"id": draft_id, "organization_id": gym["id"]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "tour_booking_id": 1},
    )
    if not draft:
        raise HTTPException(404, "Draft not found for this gym")

    slot_at_raw = (body.get("slot_at") or "").strip()
    if not slot_at_raw:
        raise HTTPException(400, "slot_at is required")
    try:
        slot_dt = datetime.fromisoformat(slot_at_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, f"Invalid slot_at: {exc}") from exc

    now = _now()
    lead_cutoff = now + timedelta(hours=int(cfg.get("lead_time_hours", 4)))
    if slot_dt < lead_cutoff:
        raise HTTPException(400, "Slot is inside the lead-time window — pick a later slot.")
    window_end = now + timedelta(days=int(cfg.get("ahead_window_days", 14)))
    if slot_dt > window_end + timedelta(hours=1):
        raise HTTPException(400, "Slot is beyond the booking window.")

    # Capacity check (single read, race-tolerant — last booking wins).
    cap = max(1, int(cfg.get("capacity_per_slot", 1)))
    existing_count = await db.tour_bookings.count_documents({
        "organization_id": gym["id"],
        "status": "booked",
        "slot_at": _iso(slot_dt),
    })
    if existing_count >= cap:
        # If THIS draft already booked this slot, return the existing booking.
        own = await db.tour_bookings.find_one(
            {"organization_id": gym["id"], "draft_id": draft_id, "slot_at": _iso(slot_dt), "status": "booked"},
            {"_id": 0},
        )
        if own:
            return {"ok": True, "booking_id": own["id"], "idempotent": True}
        raise HTTPException(409, "That slot just filled up — please pick another.")

    # If draft already has a booking, move it (cancel old, create new).
    old_booking_id = draft.get("tour_booking_id")
    if old_booking_id:
        await db.tour_bookings.update_one(
            {"id": old_booking_id},
            {"$set": {"status": "cancelled", "cancelled_at": _iso(now), "cancelled_by": "rebook"}},
        )

    booking_id = str(uuid.uuid4())
    booking = {
        "id": booking_id,
        "organization_id": gym["id"],
        "draft_id": draft_id,
        "member_email": (body.get("email") or draft.get("email") or "").lower(),
        "member_name": body.get("full_name") or draft.get("full_name") or "",
        "slot_at": _iso(slot_dt),
        "duration_minutes": int(cfg.get("slot_duration_minutes", 30)),
        "location": cfg.get("location") or "Reception",
        "status": "booked",
        "created_at": _iso(now),
    }
    await db.tour_bookings.insert_one(booking.copy())
    await db.signup_drafts.update_one(
        {"id": draft_id},
        {"$set": {
            "tour_booking_id": booking_id,
            "tour_slot_at": _iso(slot_dt),
            "tour_requested": True,
            "updated_at": _iso(now),
        }},
    )
    return {"ok": True, "booking_id": booking_id, "idempotent": False}


@router.post("/public/signup/{slug}/draft/{draft_id}/cancel-tour")
async def public_cancel_tour(
    slug: str = Path(...),
    draft_id: str = Path(...),
) -> dict:
    gym = await _resolve_gym_by_slug(slug)
    draft = await db.signup_drafts.find_one(
        {"id": draft_id, "organization_id": gym["id"]},
        {"_id": 0, "tour_booking_id": 1},
    )
    if not draft:
        raise HTTPException(404, "Draft not found")
    booking_id = draft.get("tour_booking_id")
    if not booking_id:
        return {"ok": True, "noop": True}
    await db.tour_bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "cancelled", "cancelled_at": _iso(_now()), "cancelled_by": "member"}},
    )
    await db.signup_drafts.update_one(
        {"id": draft_id},
        {"$set": {"tour_booking_id": None, "tour_slot_at": None, "tour_requested": False}},
    )
    return {"ok": True}


# ── Operator: config + bookings list ─────────────────────────────────────


def _require_org_member(user: dict) -> str:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Org context required")
    role = (user.get("role") or "").lower()
    if role not in {"owner", "manager", "master_admin", "master"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Owner / manager access required")
    return org_id


@router.get("/memberships/tour-config")
async def operator_get_tour_config(user: dict = Depends(get_current_user)) -> dict:
    org_id = _require_org_member(user)
    cfg = await _fetch_config(org_id)
    return cfg


@router.put("/memberships/tour-config")
async def operator_update_tour_config(
    body: dict = Body(...), user: dict = Depends(get_current_user),
) -> dict:
    org_id = _require_org_member(user)
    update = {
        "organization_id": org_id,
        "weekly_schedule": body.get("weekly_schedule") or DEFAULT_TOUR_CONFIG["weekly_schedule"],
        "slot_duration_minutes": int(body.get("slot_duration_minutes") or DEFAULT_TOUR_CONFIG["slot_duration_minutes"]),
        "capacity_per_slot": max(1, int(body.get("capacity_per_slot") or 1)),
        "lead_time_hours": max(0, int(body.get("lead_time_hours") or DEFAULT_TOUR_CONFIG["lead_time_hours"])),
        "ahead_window_days": max(1, min(60, int(body.get("ahead_window_days") or DEFAULT_TOUR_CONFIG["ahead_window_days"]))),
        "blackout_dates": list(body.get("blackout_dates") or []),
        "location": (body.get("location") or DEFAULT_TOUR_CONFIG["location"]).strip()[:120],
        "timezone": body.get("timezone") or DEFAULT_TOUR_CONFIG["timezone"],
        "updated_at": _iso(_now()),
        "updated_by": user.get("email"),
    }
    await db.tour_configs.update_one(
        {"organization_id": org_id}, {"$set": update}, upsert=True,
    )
    return {"ok": True, "config": await _fetch_config(org_id)}


@router.get("/memberships/tour-bookings")
async def operator_list_tour_bookings(
    status: Optional[str] = None, user: dict = Depends(get_current_user),
) -> dict:
    org_id = _require_org_member(user)
    filt: dict = {"organization_id": org_id}
    if status:
        filt["status"] = status
    else:
        # Default: show upcoming (booked) + recent past (last 7 days).
        cutoff = _iso(_now() - timedelta(days=7))
        filt["$or"] = [
            {"status": "booked"},
            {"status": "attended", "slot_at": {"$gte": cutoff}},
            {"status": "cancelled", "slot_at": {"$gte": cutoff}},
        ]
    rows = await db.tour_bookings.find(filt, {"_id": 0}).sort("slot_at", 1).to_list(500)
    return {"bookings": rows, "total": len(rows)}


@router.post("/memberships/tour-bookings/{booking_id}/cancel")
async def operator_cancel_tour_booking(
    booking_id: str = Path(...), user: dict = Depends(get_current_user),
) -> dict:
    org_id = _require_org_member(user)
    target = await db.tour_bookings.find_one(
        {"id": booking_id, "organization_id": org_id}, {"_id": 0, "draft_id": 1},
    )
    if not target:
        raise HTTPException(404, "Booking not found")
    await db.tour_bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "cancelled", "cancelled_at": _iso(_now()), "cancelled_by": user.get("email")}},
    )
    if target.get("draft_id"):
        await db.signup_drafts.update_one(
            {"id": target["draft_id"]},
            {"$set": {"tour_booking_id": None, "tour_slot_at": None, "tour_requested": False}},
        )
    return {"ok": True}


@router.post("/memberships/tour-bookings/{booking_id}/attended")
async def operator_mark_attended(
    booking_id: str = Path(...), user: dict = Depends(get_current_user),
) -> dict:
    org_id = _require_org_member(user)
    res = await db.tour_bookings.update_one(
        {"id": booking_id, "organization_id": org_id},
        {"$set": {"status": "attended", "attended_at": _iso(_now()), "marked_by": user.get("email")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Booking not found")
    return {"ok": True}


@router.post("/memberships/tour-bookings/{booking_id}/no-show")
async def operator_mark_no_show(
    booking_id: str = Path(...), user: dict = Depends(get_current_user),
) -> dict:
    org_id = _require_org_member(user)
    res = await db.tour_bookings.update_one(
        {"id": booking_id, "organization_id": org_id},
        {"$set": {"status": "no_show", "no_show_at": _iso(_now()), "marked_by": user.get("email")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Booking not found")
    return {"ok": True}


# ── Conversion KPI ───────────────────────────────────────────────────────


@router.get("/memberships/tour-conversion")
async def operator_tour_conversion(
    days: int = 30, user: dict = Depends(get_current_user),
) -> dict:
    """Booked → attended → became-member funnel for the last N days.

    A booking "became_member" when the associated `signup_drafts.member_id`
    is non-null (i.e. payment completed and the draft was finalised),
    OR when a `members` row exists whose email matches the booking's
    `member_email` and whose `joined_at >= booking.created_at`.

    Conversion ratios are floats in [0, 1] — easier to render either as
    a percentage or as a 0-1 bar. Period defaults to last 30 days; cap
    at 365 to bound the aggregate.
    """
    org_id = _require_org_member(user)
    days = max(1, min(365, int(days)))
    cutoff = _iso(_now() - timedelta(days=days))

    rows = await db.tour_bookings.find(
        {"organization_id": org_id, "created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "draft_id": 1, "status": 1, "member_email": 1, "created_at": 1},
    ).to_list(length=5000)

    total = len(rows)
    by_status: dict[str, int] = {"booked": 0, "attended": 0, "no_show": 0, "cancelled": 0}
    for r in rows:
        by_status[r.get("status", "booked")] = by_status.get(r.get("status", "booked"), 0) + 1

    # Cross-reference: did any of these tour-bookers become members?
    became_member = 0
    if rows:
        # Path A: signup_drafts that completed (member_id present).
        draft_ids = [r["draft_id"] for r in rows if r.get("draft_id")]
        completed_drafts: set[str] = set()
        if draft_ids:
            async for d in db.signup_drafts.find(
                {"id": {"$in": draft_ids}, "member_id": {"$ne": None}},
                {"_id": 0, "id": 1},
            ):
                completed_drafts.add(d["id"])
        # Path B: members table rows by email (covers walk-ins / off-flow joins).
        emails = list({r["member_email"] for r in rows if r.get("member_email")})
        member_emails: set[str] = set()
        if emails:
            async for m in db.members.find(
                {"organization_id": org_id, "email": {"$in": emails}},
                {"_id": 0, "email": 1, "joined_at": 1},
            ):
                # Match the email even if joined_at is missing (legacy rows).
                if m.get("email"):
                    member_emails.add(m["email"].lower())
        for r in rows:
            if r.get("draft_id") in completed_drafts:
                became_member += 1
                continue
            email = (r.get("member_email") or "").lower()
            if email and email in member_emails:
                became_member += 1

    def _pct(num: int, denom: int) -> float:
        return round(num / denom, 4) if denom > 0 else 0.0

    return {
        "period_days": days,
        "total_booked": total,
        "by_status": by_status,
        "became_member": became_member,
        "conversion_rates": {
            "booked_to_attended": _pct(by_status["attended"], total),
            "attended_to_member": _pct(became_member, by_status["attended"]),
            "booked_to_member": _pct(became_member, total),
        },
        "generated_at": _iso(_now()),
    }


__all__ = ["router"]
