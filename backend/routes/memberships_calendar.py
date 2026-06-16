"""Pulse Fitness Memberships — Phase 2 calendar sync.

Two ways for members and externals to subscribe to bookings:

1. Per-booking download — `GET /api/member/bookings/{id}/calendar.ics`
   returns a single VCALENDAR/VEVENT for one booking. Members tap
   "Add to calendar" on a confirmation screen and import.

2. Auto-syncing feed — `GET /m/{slug}/calendar/{token}.ics` returns all
   the member's upcoming bookings as a feed. They subscribe once
   (webcal://...) and Apple/Google/Outlook auto-pull updates from then on.

The feed token is a cryptographically random 32-char id stored on the
member doc (`calendar_feed_token`). Rotating it via PATCH on the member
auth-me endpoint invalidates the URL.

Standard iCal RFC 5545. We hand-roll the text because it's only ~25 lines
of formatting and avoids another runtime dep.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from routes.memberships import _require_current_member
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-calendar"])


def _ics_dt(iso: str) -> str:
    """Convert an ISO8601 timestamp to RFC5545 UTC format (YYYYMMDDTHHMMSSZ)."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return ""


def _esc(text: str) -> str:
    """Escape iCal special characters per RFC 5545."""
    if text is None:
        return ""
    return (str(text).replace("\\", "\\\\").replace(",", "\\,")
            .replace(";", "\\;").replace("\n", "\\n"))


def _build_vevent(occ: dict, tpl: dict, booking: dict, org_name: str) -> list[str]:
    """Single VEVENT block. Idempotent UID so re-imports update in-place."""
    site = tpl.get("room_name") or tpl.get("site_name") or ""
    instructor = tpl.get("instructor_name") or ""
    cls_name = tpl.get("name") or "Class"
    summary = f"{cls_name} · {org_name}" if org_name else cls_name
    description_parts: list[str] = []
    if instructor:
        description_parts.append(f"Instructor: {instructor}")
    if booking.get("attendee_name") and booking.get("attendee_kind") != "self":
        description_parts.append(f"Attendee: {booking['attendee_name']}")
    if booking.get("status") == "waitlist":
        description_parts.append("Status: WAITLIST — we'll notify you if a spot opens")
    description = " · ".join(description_parts)
    location_parts = [p for p in [site, tpl.get("address") or ""] if p]
    return [
        "BEGIN:VEVENT",
        f"UID:gymaxis-booking-{booking['id']}@gymaxis.app",
        f"DTSTAMP:{_ics_dt(booking.get('booked_at') or occ.get('starts_at'))}",
        f"DTSTART:{_ics_dt(occ['starts_at'])}",
        f"DTEND:{_ics_dt(occ.get('ends_at') or occ['starts_at'])}",
        f"SUMMARY:{_esc(summary)}",
        f"DESCRIPTION:{_esc(description)}",
        f"LOCATION:{_esc(', '.join(location_parts))}",
        "STATUS:CONFIRMED" if booking.get("status") == "booked" else "STATUS:TENTATIVE",
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]


def _wrap_calendar(events: list[list[str]], org_name: str) -> str:
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Pulse Fitness//Memberships//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(org_name + ' bookings')}",
        "X-WR-TIMEZONE:UTC",
        *[line for ev in events for line in ev],
        "END:VCALENDAR",
        "",
    ])


# ───────────────────────── Per-booking download ─────────────────────────


@router.get("/member/bookings/{booking_id}/calendar.ics")
async def booking_ics(
    booking_id: str, member: dict = Depends(_require_current_member),
):
    """Single-booking .ics download. Member taps the button on a booking
    confirmation card, the OS native calendar opens with the event ready
    to import."""
    booking = await db.bookings.find_one(
        {"id": booking_id, "member_id": member["id"]}, {"_id": 0},
    )
    if not booking:
        raise HTTPException(404, "Booking not found")
    occ = await db.class_occurrences.find_one(
        {"id": booking["occurrence_id"]}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    tpl = await db.class_templates.find_one(
        {"id": occ["template_id"]}, {"_id": 0},
    ) or {}
    org = await db.organizations.find_one(
        {"id": member["organization_id"]}, {"_id": 0, "name": 1},
    ) or {}
    body = _wrap_calendar(
        [_build_vevent(occ, tpl, booking, org.get("name") or "")],
        org.get("name") or "Pulse Fitness",
    )
    safe_name = (tpl.get("name") or "class").replace(" ", "-").lower()
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}-{booking_id[:8]}.ics"',
            "Cache-Control": "no-store",
        },
    )


# ───────────────────────── Auto-syncing feed ─────────────────────────


async def _ensure_feed_token(member_id: str) -> str:
    m = await db.members.find_one(
        {"id": member_id}, {"_id": 0, "calendar_feed_token": 1},
    )
    token = (m or {}).get("calendar_feed_token")
    if not token:
        token = secrets.token_urlsafe(24)
        await db.members.update_one(
            {"id": member_id},
            {"$set": {"calendar_feed_token": token,
                      "calendar_feed_created_at": datetime.now(timezone.utc).isoformat()}},
        )
    return token


@router.get("/member/calendar-feed")
async def my_calendar_feed_url(
    request: Request, member: dict = Depends(_require_current_member),
):
    """Return the member's personal feed URL (in webcal:// + https://
    forms — they paste either into Apple/Google/Outlook). Generates the
    token on first call."""
    token = await _ensure_feed_token(member["id"])
    # Prefer the request's host so we serve a feed URL that's valid in
    # the same environment the member is using (preview vs prod).
    base = str(request.base_url).rstrip("/")
    org = await db.organizations.find_one(
        {"id": member["organization_id"]},
        {"_id": 0, "membership_app_slug": 1, "name": 1},
    ) or {}
    slug = org.get("membership_app_slug") or "app"
    https_url = f"{base}/api/m/{slug}/calendar/{token}.ics"
    webcal_url = https_url.replace("https://", "webcal://").replace("http://", "webcal://")
    return {
        "https_url": https_url,
        "webcal_url": webcal_url,
        "token": token,
        "instructions": (
            "Tap webcal_url on iPhone/macOS, or paste https_url into "
            "Google Calendar → 'From URL'. Updates auto-sync every few hours."
        ),
    }


@router.post("/member/calendar-feed/rotate")
async def rotate_calendar_feed(
    member: dict = Depends(_require_current_member),
):
    """Issue a new token. The old URL stops working immediately — useful
    if the member shared the old URL by accident."""
    new_token = secrets.token_urlsafe(24)
    await db.members.update_one(
        {"id": member["id"]},
        {"$set": {"calendar_feed_token": new_token,
                  "calendar_feed_rotated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"token": new_token}


@router.get("/m/{slug}/calendar/{token}.ics")
async def calendar_feed(slug: str, token: str):
    """Public endpoint Apple/Google/Outlook hits to refresh the feed.
    Auth is the token itself — leak-tolerant because rotating issues a
    fresh one. Returns all the member's upcoming bookings (next 90 days)."""
    member = await db.members.find_one(
        {"calendar_feed_token": token}, {"_id": 0},
    )
    if not member:
        raise HTTPException(404, "Feed not found")
    org = await db.organizations.find_one(
        {"id": member["organization_id"]},
        {"_id": 0, "name": 1, "membership_app_slug": 1},
    ) or {}
    # Slug isn't validated against — it's just there for prettier URLs.
    now_iso = datetime.now(timezone.utc).isoformat()
    bookings = await db.bookings.find(
        {"member_id": member["id"],
         "status": {"$in": ["booked", "waitlist", "attended"]}},
        {"_id": 0},
    ).to_list(500)
    if not bookings:
        return Response(
            content=_wrap_calendar([], org.get("name") or "Pulse Fitness"),
            media_type="text/calendar; charset=utf-8",
        )
    occ_ids = [b["occurrence_id"] for b in bookings]
    occs = {o["id"]: o for o in await db.class_occurrences.find(
        {"id": {"$in": occ_ids}, "starts_at": {"$gte": now_iso}}, {"_id": 0},
    ).to_list(1000)}
    tpl_ids = list({o["template_id"] for o in occs.values()})
    tpls = {t["id"]: t for t in await db.class_templates.find(
        {"id": {"$in": tpl_ids}}, {"_id": 0},
    ).to_list(500)} if tpl_ids else {}
    events: list[list[str]] = []
    for b in bookings:
        occ = occs.get(b["occurrence_id"])
        if not occ:
            continue
        tpl = tpls.get(occ["template_id"]) or {}
        events.append(_build_vevent(occ, tpl, b, org.get("name") or ""))
    body = _wrap_calendar(events, org.get("name") or "Pulse Fitness")
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "public, max-age=600"},
    )


__all__ = ["router"]
