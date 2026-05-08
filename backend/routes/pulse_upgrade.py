"""Pulse Pro upgrade-request funnel.

Public endpoint called from the Pulse landing page when a gym clicks
"Request Upgrade" on the Pro plan card. Captures contact + estate context,
persists to `pulse_upgrade_requests`, and emails both the Pulse Fitness
service team and the platform owner (Lee@gymaxisai.com).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.database import db
from utils.email import send_email
from utils.security_plus import rate_limit_async
from utils.security import sanitise_string
from utils.auth import get_current_user
from routes.master_admin import require_master_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class PulseUpgradeRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    gym_name: str = Field(..., min_length=2, max_length=200)
    site_count: int = Field(default=1, ge=1, le=500)
    equipment_count: Optional[int] = Field(default=None, ge=0, le=50000)
    contact_method: str = Field(default="email", pattern=r"^(email|phone|either)$")
    notes: Optional[str] = Field(default=None, max_length=2000)
    cf_turnstile_response: Optional[str] = None


def _pulse_fitness_email_html(r: dict) -> str:
    """Branded email for service.dept@pulsefitness.com — Pulse visual identity."""
    notes_block = ""
    if r.get("notes"):
        notes_block = (
            '<div style="margin-top:20px;padding:16px;background:#f8fafc;border-left:3px solid #19CDFF;border-radius:4px;">'
            '<div style="font-size:11px;font-weight:700;color:#6E7476;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:6px;">Notes from the gym</div>'
            f'<div style="color:#1B1D1D;font-size:14px;line-height:1.6;">{r["notes"]}</div>'
            "</div>"
        )
    first_name = r["full_name"].split(" ")[0]
    equip = r["equipment_count"] if r.get("equipment_count") is not None else "—"
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#f8fafc;color:#1B1D1D;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
  <div style="background:#1B1D1D;padding:28px 32px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">Pulse Pro · Upgrade Request</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{r['gym_name']} wants to upgrade</h1>
  </div>
  <div style="padding:28px 32px;background:#fff;">
    <table style="width:100%;border-collapse:collapse;color:#1B1D1D;font-size:14px;">
      <tr><td style="padding:8px 0;color:#6E7476;width:150px;">Contact name</td><td style="padding:8px 0;font-weight:600;">{r['full_name']}</td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Email</td><td style="padding:8px 0;"><a href="mailto:{r['email']}" style="color:#19CDFF;text-decoration:none;">{r['email']}</a></td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Phone</td><td style="padding:8px 0;">{r['phone'] or '—'}</td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Gym / Organisation</td><td style="padding:8px 0;font-weight:600;">{r['gym_name']}</td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Sites</td><td style="padding:8px 0;">{r['site_count']}</td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Equipment</td><td style="padding:8px 0;">{equip}</td></tr>
      <tr><td style="padding:8px 0;color:#6E7476;">Preferred contact</td><td style="padding:8px 0;text-transform:capitalize;">{r['contact_method']}</td></tr>
    </table>
    {notes_block}
    <div style="margin-top:24px;">
      <a href="mailto:{r['email']}" style="display:inline-block;background:#19CDFF;color:#05070A;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:700;font-size:13px;letter-spacing:0.05em;text-transform:uppercase;">Reply to {first_name}</a>
    </div>
  </div>
  <div style="background:#1B1D1D;padding:16px 32px;">
    <p style="color:#9ca3af;font-size:11px;margin:0;">Sent by the Pulse Fitness portal · upgrade-request funnel</p>
  </div>
</div>"""


def _platform_owner_email_html(r: dict) -> str:
    """Dark branded email for Lee@gymaxisai.com — matches trial-signup notifications."""
    notes_block = ""
    if r.get("notes"):
        notes_block = (
            '<div style="margin-top:20px;padding:16px;background:#05070A;border-left:3px solid #19CDFF;border-radius:4px;">'
            '<div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:6px;">Notes</div>'
            f'<div style="color:#e5e7eb;font-size:14px;line-height:1.6;">{r["notes"]}</div>'
            "</div>"
        )
    equip_suffix = ""
    if r.get("equipment_count") is not None:
        equip_suffix = f" · {r['equipment_count']} pieces"
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#05070A 0%,#0d1117 100%);padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.3);">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">Pulse Pro · Upgrade Request</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{r['gym_name']} requested Pro</h1>
  </div>
  <div style="padding:28px 32px;background:#0A0B10;">
    <table style="width:100%;border-collapse:collapse;color:#e5e7eb;font-size:14px;">
      <tr><td style="padding:8px 0;color:#9ca3af;width:150px;">Contact</td><td style="padding:8px 0;font-weight:600;">{r['full_name']}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Email</td><td style="padding:8px 0;"><a href="mailto:{r['email']}" style="color:#19CDFF;text-decoration:none;">{r['email']}</a></td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Phone</td><td style="padding:8px 0;">{r['phone'] or '—'}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Gym</td><td style="padding:8px 0;font-weight:600;">{r['gym_name']}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Sites · Equipment</td><td style="padding:8px 0;">{r['site_count']} site(s){equip_suffix}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Prefers</td><td style="padding:8px 0;text-transform:capitalize;">{r['contact_method']}</td></tr>
    </table>
    {notes_block}
  </div>
  <div style="background:#05070A;padding:16px 32px;border-top:1px solid rgba(255,255,255,0.05);">
    <p style="color:#6b7280;font-size:11px;margin:0;">Pulse upgrade intent · tracked in Master Admin funnel</p>
  </div>
</div>"""


@router.post("/pulse/upgrade-request")
async def submit_upgrade_request(payload: PulseUpgradeRequest, request: Request):
    """Accept an upgrade-intent form from the Pulse landing page."""
    ip = request.client.host if request.client else "unknown"
    # IP-scoped abuse limit — 5 requests / 10 min / IP.
    await rate_limit_async(f"pulse_upgrade_ip:{ip}", max_requests=5, window_seconds=600)

    # Turnstile captcha — public write endpoint, must be bot-protected.
    from utils.captcha import verify_captcha
    await verify_captcha(payload.cf_turnstile_response, action="pulse_upgrade")

    record_id = str(uuid.uuid4())
    record = {
        "id": record_id,
        "full_name": sanitise_string(payload.full_name),
        "email": payload.email.lower().strip(),
        "phone": sanitise_string(payload.phone) if payload.phone else None,
        "gym_name": sanitise_string(payload.gym_name),
        "site_count": payload.site_count,
        "equipment_count": payload.equipment_count,
        "contact_method": payload.contact_method,
        "notes": sanitise_string(payload.notes) if payload.notes else None,
        "status": "new",
        "source": "pulse_landing",
        "ip": ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.pulse_upgrade_requests.insert_one(record)

    # Fan out emails (non-blocking)
    pulse_recipient = os.environ.get("PULSE_UPGRADE_NOTIFY_EMAIL", "service.dept@pulsefitness.com")
    platform_recipient = os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com")

    subject_pulse = f"[Pulse Pro] Upgrade request — {record['gym_name']}"
    subject_owner = f"[Pulse Upgrade] {record['gym_name']} ({record['site_count']} site{'s' if record['site_count'] > 1 else ''})"

    try:
        asyncio.create_task(send_email(pulse_recipient, subject_pulse, _pulse_fitness_email_html(record)))
        asyncio.create_task(send_email(platform_recipient, subject_owner, _platform_owner_email_html(record)))
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning(f"pulse upgrade notification dispatch failed: {e}")

    return {"ok": True, "id": record_id}


@router.get("/master-admin/pulse-upgrade-requests")
async def list_pulse_upgrade_requests(user: dict = Depends(get_current_user)):
    """Paginated list of upgrade requests for the Master Admin funnel view."""
    require_master_admin(user)

    try:
        total = await db.pulse_upgrade_requests.count_documents({})
    except Exception:
        total = 0
    cursor = db.pulse_upgrade_requests.find({}, {"_id": 0}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(200)

    # Status counts for the summary strip
    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    try:
        new_last_7d = await db.pulse_upgrade_requests.count_documents({
            "created_at": {"$gte": seven_days_ago},
        })
    except Exception:
        new_last_7d = 0

    by_status_raw = {
        "new": 0, "contacted": 0, "quoted": 0, "converted": 0, "lost": 0,
    }
    for it in items:
        s = (it.get("status") or "new").lower()
        by_status_raw[s] = by_status_raw.get(s, 0) + 1

    return {
        "total": total,
        "new_last_7d": new_last_7d,
        "by_status": by_status_raw,
        "items": items,
    }


@router.patch("/master-admin/pulse-upgrade-requests/{req_id}")
async def update_pulse_upgrade_status(
    req_id: str, body: dict, user: dict = Depends(get_current_user),
):
    """Move an upgrade request through the funnel (new → contacted → quoted → converted/lost)."""
    require_master_admin(user)

    status = (body.get("status") or "").lower()
    if status not in ("new", "contacted", "quoted", "converted", "lost"):
        raise HTTPException(400, "Invalid status")
    updated = await db.pulse_upgrade_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": status,
            "status_updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if updated.matched_count == 0:
        raise HTTPException(404, "Upgrade request not found")
    return {"ok": True}
