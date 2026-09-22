"""Pulse Fitness Service Operations — PPM-due notification sweeper (Iter 220dm).

`ppm_due` was declared in ``PUSH_NOTIFICATION_KINDS`` but nothing
actually fired it. This module closes the loop by adding a sweep
endpoint that:

  * Finds open PPM cases (``case_type='ppm'``, status ∈ open) that are
    scheduled within the next ``hours_ahead`` window (default 24h).
  * For each, creates a ``ppm_due`` notification for the assigned
    engineer (which fans out to Web Push via the existing pipeline).
  * Deduplicates: same case → at most one notification per
    ``DEDUPE_WINDOW_HOURS`` (default 18h) to avoid spamming the
    engineer when a daily cron + a manual trigger both hit.

Operator hits this from the master-admin dashboard or wires it to
an external cron once per shift. Idempotent + safe to run multiple
times in the same window.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


DEDUPE_WINDOW_HOURS = 18
DEFAULT_HOURS_AHEAD = 24
OPEN_STATES = {"new", "scheduled", "assigned"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    if (user.get("role") or "").lower() in ("owner", "manager"):
        return
    raise HTTPException(403, "Owner / Manager / Master Admin required")


async def _ppm_due_was_recently_sent(case_id: str, user_id: str) -> bool:
    """Dedupe guard: returns True when a ``ppm_due`` notification was
    already created for this case+engineer within the last
    ``DEDUPE_WINDOW_HOURS``."""
    cutoff = (_now() - timedelta(hours=DEDUPE_WINDOW_HOURS)).isoformat()
    existing = await db.svc_notifications.find_one(
        {
            "kind": "ppm_due",
            "source_type": "case",
            "source_id": case_id,
            "user_id": user_id,
            "created_at": {"$gte": cutoff},
        },
        {"_id": 0, "id": 1},
    )
    return existing is not None


@router.post("/svc/admin/ppm/fire-due-reminders")
async def fire_ppm_due_reminders(
    hours_ahead: int = Query(
        DEFAULT_HOURS_AHEAD, ge=1, le=168,
        description="Look forward window for PPM jobs (1–168 h).",
    ),
    organization_id: Optional[str] = Query(
        None,
        description="Master-Admin only — sweep one tenant explicitly.",
    ),
    user=Depends(get_current_user),
):
    """Sweep open PPM jobs and emit a ``ppm_due`` notification for
    each assigned engineer. Returns counts so the operator can see
    what fired."""
    _require_admin(user)
    now = _now()
    cutoff = (now + timedelta(hours=hours_ahead)).isoformat()
    earliest = now.isoformat()

    # Master-admin can target a specific org; others always scoped to their own.
    flt: dict = {
        "case_type": "ppm",
        "status": {"$in": list(OPEN_STATES)},
        "assigned_engineer_id": {"$exists": True, "$ne": None},
        "scheduled_at": {"$gte": earliest, "$lte": cutoff},
    }
    if user.get("is_master_admin") and organization_id:
        flt["organization_id"] = organization_id
    elif not user.get("is_master_admin"):
        flt["organization_id"] = (user.get("organization_id") or user.get("service_org_id"))

    cases = await db.svc_cases.find(
        flt,
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1,
            "scheduled_at": 1, "assigned_engineer_id": 1,
            "organization_id": 1,
        },
    ).sort("scheduled_at", 1).limit(500).to_list(500)

    fired = 0
    skipped_dupe = 0
    skipped_self_assigned_only = 0

    from routes.svc.notifications import create_notification

    for c in cases:
        eng = c.get("assigned_engineer_id")
        if not eng:
            skipped_self_assigned_only += 1
            continue
        if await _ppm_due_was_recently_sent(c["id"], eng):
            skipped_dupe += 1
            continue
        try:
            when_str = datetime.fromisoformat(
                c["scheduled_at"].replace("Z", "+00:00"),
            ).strftime("%a %d %b · %H:%M")
        except Exception:
            when_str = "soon"
        ref = c.get("reference") or c["id"][:8]
        site = c.get("site_name") or "Site"
        try:
            await create_notification(
                user_id=eng,
                organization_id=c["organization_id"],
                kind="ppm_due",
                title=f"PPM due: {ref}",
                body=f"{site} — scheduled {when_str}",
                link=f"/svc/engineer/jobs/{c['id']}",
                source_type="case",
                source_id=c["id"],
            )
            fired += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("ppm_due notify failed for case=%s: %s", c["id"], exc)

    return {
        "ok": True,
        "scanned": len(cases),
        "fired": fired,
        "skipped_dupe": skipped_dupe,
        "skipped_unassigned": skipped_self_assigned_only,
        "window_hours_ahead": hours_ahead,
    }


__all__ = ["router", "DEDUPE_WINDOW_HOURS", "run_ppm_email_reminders"]


# ── Commercial PPM pre-visit EMAIL reminder (~2 weeks ahead) ───────────────
# Mirrors the MOD annual-visit reminder (utils/mod_visit_reminders.py) but for
# commercial ppm_schedules. Reads the canonical `ppm_schedules.next_pm`, emails
# the site/customer contact, and is idempotent per due-date via `reminded_for`.
import os  # noqa: E402
from datetime import date  # noqa: E402

PPM_REMINDER_LEAD_DAYS = int(os.environ.get("PPM_REMINDER_LEAD_DAYS", "14"))
_PPM_WIN_LOW = PPM_REMINDER_LEAD_DAYS - 2
_PPM_WIN_HIGH = PPM_REMINDER_LEAD_DAYS + 2


def _ppm_parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


async def _resolve_ppm_site_email(schedule: dict) -> str:
    """Site/customer contact email for a commercial PPM. Site manager →
    imported site-manager CRM contact for that site → customer org contact."""
    def _valid(e):
        e = (e or "").strip().lower()
        return e if ("@" in e and "@site." not in e) else ""

    site_id = schedule.get("site_id")
    org_id = schedule.get("organization_id")
    if site_id:
        site = await db.sites.find_one(
            {"id": site_id},
            {"_id": 0, "site_manager_email": 1, "email": 1, "invoice_customer_ref": 1},
        ) or {}
        email = _valid(site.get("site_manager_email")) or _valid(site.get("email"))
        if email:
            return email
        contact = await db.crm2_contacts.find_one(
            {"customer_site_id": site_id, "email": {"$nin": [None, ""]}}, {"_id": 0, "email": 1},
        )
        if contact and _valid(contact.get("email")):
            return _valid(contact["email"])
    if org_id:
        org = await db.organizations.find_one(
            {"id": org_id},
            {"_id": 0, "site_manager_email": 1, "primary_contact_email": 1, "contact_email": 1},
        ) or {}
        return (_valid(org.get("site_manager_email")) or _valid(org.get("primary_contact_email"))
                or _valid(org.get("contact_email")))
    return ""


def _ppm_reminder_html(customer, site, equipment, service, due_date) -> str:
    what = equipment or "your equipment"
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:560px;margin:0 auto;background:#fff;color:#1B1D1D;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
  <div style="background:#1B1D1D;padding:18px 26px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · Preventative Maintenance</div>
    <h1 style="color:#fff;margin:6px 0 0 0;font-size:19px;">Upcoming service reminder</h1>
  </div>
  <div style="padding:22px 26px;">
    <p>This is a reminder that a <strong>{service}</strong> for <strong>{what}</strong>{f' at <strong>{site}</strong>' if site else ''} is due on <strong>{due_date}</strong> (about two weeks away).</p>
    <p>Our service team will be in touch to arrange an engineer visit. If you have a preferred date or access requirements, just reply to this email.</p>
    <p style="color:#6E7476;font-size:12px;">{customer or ''} · You're receiving this because a preventative-maintenance service is scheduled for your equipment.</p>
  </div>
</div>"""


async def run_ppm_email_reminders() -> dict:
    """Daily idempotent sweep — email the site contact ~2 weeks before a
    commercial PPM is due. Idempotent per due-date via `reminded_for`."""
    from utils.email import send_email
    today = date.today()
    now_iso = _now().isoformat()
    schedules = await db.ppm_schedules.find(
        {"source": "service_desk", "active": True, "next_pm": {"$nin": [None, ""]}}, {"_id": 0},
    ).to_list(20000)

    sent = 0
    for s in schedules:
        npm = _ppm_parse_date(s.get("next_pm"))
        if not npm:
            continue
        if not (_PPM_WIN_LOW <= (npm - today).days <= _PPM_WIN_HIGH):
            continue
        if s.get("reminded_for") == s.get("next_pm"):
            continue  # already reminded for this occurrence
        email = await _resolve_ppm_site_email(s)
        if email:
            try:
                await send_email(
                    email,
                    f"Reminder: {s.get('service_type') or 'Preventative maintenance'} due {s.get('next_pm')}"
                    + (f" — {s.get('site_name')}" if s.get("site_name") else ""),
                    _ppm_reminder_html(s.get("customer_name"), s.get("site_name"),
                                       s.get("equipment_name"),
                                       s.get("service_type") or "Preventative Maintenance Service",
                                       s.get("next_pm")),
                    category="support",
                )
            except Exception:
                logger.exception("[ppm-email-reminder] send failed for schedule %s", s.get("id"))
        # Stamp regardless so we don't rescan a contactless schedule each cycle.
        await db.ppm_schedules.update_one(
            {"id": s["id"], "organization_id": s.get("organization_id")},
            {"$set": {"reminded_for": s.get("next_pm"), "reminded_at": now_iso}},
        )
        if email:
            sent += 1

    if sent:
        logger.info("[ppm-email-reminder] sent %d reminder(s)", sent)
    return {"sent": sent, "scanned": len(schedules)}


@router.post("/svc/admin/ppm/fire-email-reminders")
async def fire_ppm_email_reminders(user=Depends(get_current_user)):
    """Manually run the ~2-week PPM email reminder sweep."""
    _require_admin(user)
    return await run_ppm_email_reminders()
