"""Booking reminder digest for GymAxis Memberships.

Runs every ~5 minutes via the existing `sicon_poller` loop. For every
booked class that starts in the next N hours (±2.5 min window so the
5-min poll cadence catches it exactly once) we send the member a nudge
email with the class details and a tap-to-cancel line.

Two reminder waves:
  • 24h-before  → "Tomorrow at 07:00 — HIIT Blast"
  • 2h-before   → "Heading in at 18:00 — see you at Rhythm Ride"

Dedupe via `reminders_sent: ['24h'|'2h', ...]` on the booking doc so
each member gets at most one 24h and one 2h email per booking.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

_POLL_WINDOW_MINUTES = 5
_REMINDER_WAVES = [
    ("24h", 24 * 60, "Tomorrow at"),
    ("2h",  2 * 60,  "See you at"),
]

_BRAND_BG = "#05070A"
_BRAND_ACCENT = "#19CDFF"


def _reminder_html(first: str, occ: dict, wave_label: str) -> str:
    when = ""
    try:
        when = datetime.fromisoformat(occ["starts_at"].replace("Z", "+00:00")).strftime("%A %-d %B · %H:%M")
    except Exception:
        when = occ.get("starts_at", "")
    name = occ.get("name") or "your class"
    room = occ.get("room_name") or ""
    instructor = occ.get("instructor_name") or ""
    sub = " · ".join([x for x in (instructor, room) if x])
    return f"""<div style="font-family:-apple-system,sans-serif;max-width:540px;margin:0 auto;background:{_BRAND_BG};color:#fff;border-radius:16px;overflow:hidden;">
  <div style="padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.25);">
    <div style="color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">Class reminder · {wave_label}</div>
    <h1 style="color:#fff;font-size:20px;margin:0;line-height:1.3;font-weight:800;">{wave_label} {when.split('·')[-1].strip() if '·' in when else when} — {name}</h1>
  </div>
  <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
    <p>Hi {first},</p>
    <p>Just a friendly nudge — you're booked in:</p>
    <div style="border-left:3px solid {occ.get('colour') or _BRAND_ACCENT};background:rgba(255,255,255,0.03);padding:14px 16px;border-radius:8px;margin:18px 0;">
      <div style="font-weight:800;font-size:15px;color:#fff;">{name}</div>
      <div style="color:#9ca3af;font-size:13px;margin-top:4px;">{when}</div>
      {f'<div style="color:#9ca3af;font-size:12px;margin-top:2px;">{sub}</div>' if sub else ''}
    </div>
    <p style="color:#9ca3af;font-size:13px;">Can't make it? Tap the class in your member app to cancel — earlier is kinder to the waitlist.</p>
  </div>
  <div style="background:{_BRAND_BG};padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
    <p style="color:#6b7280;font-size:11px;margin:0;">GymAxis Memberships · Reminder</p>
  </div>
</div>"""


async def _send_wave(wave_key: str, minutes_before: int, wave_label: str) -> int:
    """Email every booked member whose class starts in [T-min, T-min+window]."""
    now = datetime.now(timezone.utc)
    target_from = (now + timedelta(minutes=minutes_before)).isoformat()
    target_to = (now + timedelta(minutes=minutes_before + _POLL_WINDOW_MINUTES)).isoformat()

    occs = await db.class_occurrences.find(
        {"starts_at": {"$gte": target_from, "$lte": target_to}, "status": "scheduled"},
        {"_id": 0},
    ).to_list(500)
    if not occs:
        return 0

    sent = 0
    for occ in occs:
        bookings = await db.bookings.find(
            {"occurrence_id": occ["id"], "status": "booked",
             "reminders_sent": {"$ne": wave_key}},
            {"_id": 0},
        ).to_list(200)
        for b in bookings:
            mem = await db.members.find_one({"id": b["member_id"]}, {"_id": 0, "first_name": 1, "email": 1})
            if not mem:
                continue
            first = mem.get("first_name") or "there"
            subject = f"Reminder · {occ.get('name') or 'class'} · {wave_label}"
            ok = await send_email(mem["email"], subject, _reminder_html(first, occ, wave_label))
            if ok:
                await db.bookings.update_one(
                    {"id": b["id"]},
                    {"$addToSet": {"reminders_sent": wave_key},
                     "$set": {f"reminder_{wave_key}_sent_at": now.isoformat()}},
                )
                sent += 1
    return sent


async def run_booking_reminders() -> dict:
    """Invoked by the sicon_poller loop every ~5 min. Returns a count
    summary for observability."""
    summary = {"waves": {}, "started_at": datetime.now(timezone.utc).isoformat()}
    for wave_key, minutes_before, wave_label in _REMINDER_WAVES:
        try:
            n = await _send_wave(wave_key, minutes_before, wave_label)
            summary["waves"][wave_key] = n
        except Exception:
            logger.exception(f"[reminders] wave {wave_key} failed")
            summary["waves"][wave_key] = -1
    logger.info(f"[bookings-reminders] cycle complete {summary}")
    return summary
