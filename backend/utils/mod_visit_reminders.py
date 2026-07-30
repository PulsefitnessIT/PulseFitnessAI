"""1-month pre-visit reminders for MOD Type A annual service visits.

Daily idempotent sweep (invoked from the poller). For every CONFIRMED
annual visit whose scheduled date is ~1 month away and which hasn't been
reminded yet, email BOTH the Pulse MOD Service team and the MOD site
contact (with the Engineer Appointment Booking form link) and stamp
``annual_visit.reminded_at`` so it only fires once.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, date

from utils.database import db

logger = logging.getLogger(__name__)

REMINDER_LEAD_DAYS = int(os.environ.get("MOD_VISIT_REMINDER_LEAD_DAYS", "30"))
# Fire when the visit is between (lead-2) and (lead+1) days away so a daily
# run never misses the window.
_WINDOW_LOW = REMINDER_LEAD_DAYS - 2
_WINDOW_HIGH = REMINDER_LEAD_DAYS + 1

# Nudge the site if their booking form is still unfilled this many days after
# it was first sent.
NUDGE_AFTER_DAYS = int(os.environ.get("MOD_BOOKING_NUDGE_DAYS", "7"))


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


def _parse_dt(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _resolve_site_email(site_id: str) -> str:
    def _valid(e):
        e = (e or "").strip().lower()
        return e if ("@" in e and not e.endswith("@site.mod.local")) else ""
    site = await db.organizations.find_one(
        {"id": site_id},
        {"_id": 0, "site_manager_email": 1, "primary_contact_email": 1, "contact_email": 1},
    ) or {}
    email = (_valid(site.get("site_manager_email")) or _valid(site.get("primary_contact_email"))
             or _valid(site.get("contact_email")))
    if not email:
        owner = await db.users.find_one({"organization_id": site_id, "role": "owner"}, {"_id": 0, "email": 1})
        email = _valid(owner.get("email")) if owner else ""
    return email


def _share_url(token: str) -> str:
    base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return f"{base}/mod-booking/{token}" if base else f"/mod-booking/{token}"


async def run_mod_visit_reminders() -> dict:
    """Email 1-month reminders for confirmed MOD annual visits. Idempotent."""
    today = datetime.now(timezone.utc).date()
    now_iso = datetime.now(timezone.utc).isoformat()
    team_email = os.environ.get("MOD_READINESS_HQ_EMAIL") or "modservice@pulsefitness.com"
    from utils.email import send_mod_visit_reminder_email, send_email

    contracts = await db.mod_service_contracts.find(
        {"status": "active", "annual_visit.status": "confirmed",
         "annual_visit.reminded_at": {"$in": [None, ""]}}, {"_id": 0},
    ).to_list(5000)

    sent = 0
    for c in contracts:
        av = c.get("annual_visit") or {}
        d = _parse_date(av.get("scheduled_date"))
        if not d:
            continue
        days_away = (d - today).days
        if not (_WINDOW_LOW <= days_away <= _WINDOW_HIGH):
            continue

        site_name = c.get("mod_site_name") or "your site"
        visit_date = av.get("scheduled_date")
        booking = av.get("booking") or {}
        token = booking.get("token")
        booking_url = _share_url(token) if token else ""
        site_email = await _resolve_site_email(c.get("mod_site_id"))

        # Site contact reminder (with booking form link).
        if site_email:
            try:
                await send_mod_visit_reminder_email(site_email, site_name, booking_url, visit_date)
            except Exception:
                logger.exception("[mod-visit-reminder] site email failed for %s", c.get("id"))

        # MOD Service team notice.
        try:
            html = (f"<p>Reminder: the annual MOD service visit for <b>{site_name}</b> is scheduled for "
                    f"<b>{visit_date}</b> (~1 month away).</p>"
                    f"<p>Engineer: {av.get('engineer') or '—'}</p>"
                    + (f'<p>Booking form: <a href="{booking_url}">{booking_url}</a></p>' if booking_url else
                       "<p>No booking form has been sent to the site yet.</p>"))
            await send_email(team_email, f"Upcoming MOD visit ({visit_date}) — {site_name}",
                             html, category="support")
        except Exception:
            logger.exception("[mod-visit-reminder] team email failed for %s", c.get("id"))

        av["reminded_at"] = now_iso
        await db.mod_service_contracts.update_one(
            {"id": c["id"]}, {"$set": {"annual_visit": av, "updated_at": now_iso}})
        sent += 1

    if sent:
        logger.info("[mod-visit-reminder] sent %d reminder(s)", sent)
    return {"sent": sent}



async def run_mod_booking_nudges() -> dict:
    """Gently nudge MOD sites whose booking form is still unfilled ~1 week
    after it was sent. Fires ONCE per booking (idempotent via booking.nudged_at)."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    from utils.email import send_mod_booking_nudge_email

    contracts = await db.mod_service_contracts.find(
        {"annual_visit.booking.status": {"$in": ["sent", "draft"]},
         "annual_visit.booking.nudged_at": {"$in": [None, ""]}}, {"_id": 0},
    ).to_list(5000)

    sent = 0
    for c in contracts:
        av = c.get("annual_visit") or {}
        booking = av.get("booking") or {}
        sent_at = _parse_dt(booking.get("sent_at"))
        if not sent_at:
            continue
        if (now - sent_at).days < NUDGE_AFTER_DAYS:
            continue

        site_name = c.get("mod_site_name") or "your site"
        visit_date = av.get("scheduled_date") or av.get("proposed_date")
        booking_url = _share_url(booking["token"]) if booking.get("token") else ""
        site_email = await _resolve_site_email(c.get("mod_site_id"))
        if site_email:
            try:
                await send_mod_booking_nudge_email(site_email, site_name, booking_url, visit_date)
            except Exception:
                logger.exception("[mod-booking-nudge] email failed for %s", c.get("id"))

        booking["nudged_at"] = now_iso
        av["booking"] = booking
        await db.mod_service_contracts.update_one(
            {"id": c["id"]}, {"$set": {"annual_visit": av, "updated_at": now_iso}})
        sent += 1

    if sent:
        logger.info("[mod-booking-nudge] sent %d nudge(s)", sent)
    return {"sent": sent}
