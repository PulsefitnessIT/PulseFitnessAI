"""Public contact form submission.

Backs the /contact page. Captures the marketing enquiry form payload,
persists to ``public_contact_submissions``, notifies the platform owner
and returns a generic 200 regardless of downstream email status to avoid
enumeration. Protected by Turnstile.

Iter 216h94 — extended payload + admin-facing Communications Inbox.
The form now captures phone, gym size, interest area, preferred contact
time and the "how did you hear about us" source. Older clients posting
the minimal ``{name,email,company,message}`` payload remain compatible
because every new field is optional.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field

from utils.captcha import verify_captcha
from utils.database import db
from utils.email import send_email
from utils.security import sanitise_string
from utils.security_plus import rate_limit_async

logger = logging.getLogger(__name__)
router = APIRouter()


# Whitelist of interest categories the marketing form is allowed to send.
# Anything outside the list is dropped to "other" so the inbox filter
# never gets polluted with arbitrary free-form values.
_INTEREST_OPTIONS = {
    "memberships", "service_desk", "engineers", "marketing",
    "crm", "pricing", "other",
}
_CONTACT_TIME_OPTIONS = {"morning", "afternoon", "evening", "anytime"}
_HEARD_FROM_OPTIONS = {
    "search", "referral", "linkedin", "industry_event",
    "press", "partner", "other",
}


class ContactSubmission(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(..., min_length=5, max_length=4000)
    # Iter 216h94 — new optional fields
    phone: Optional[str] = Field(default=None, max_length=40)
    gym_size: Optional[str] = Field(default=None, max_length=40)
    interest: Optional[str] = Field(default=None, max_length=40)
    preferred_contact_time: Optional[str] = Field(default=None, max_length=20)
    heard_from: Optional[str] = Field(default=None, max_length=40)
    cf_turnstile_response: Optional[str] = None


def _normalise(value: Optional[str], whitelist: set[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower().strip().replace(" ", "_")
    return v if v in whitelist else "other"


def _notification_html(r: dict) -> str:
    message_html = (r.get("message") or "").replace("\n", "<br/>")

    def _row(label: str, value: Optional[str]) -> str:
        if not value:
            return ""
        return (
            f'<tr><td style="padding:8px 0;color:#9ca3af;width:160px;">{label}</td>'
            f'<td style="padding:8px 0;">{value}</td></tr>'
        )

    rows = "".join([
        _row("Name", r.get("name")),
        _row("Email", f'<a href="mailto:{r["email"]}" style="color:#19CDFF;text-decoration:none;">{r["email"]}</a>'),
        _row("Phone", r.get("phone")),
        _row("Company", r.get("company")),
        _row("Gym size", r.get("gym_size")),
        _row("Interest", (r.get("interest") or "").replace("_", " ").title() or None),
        _row("Preferred time", (r.get("preferred_contact_time") or "").title() or None),
        _row("Heard from", (r.get("heard_from") or "").replace("_", " ").title() or None),
    ])
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#05070A 0%,#0d1117 100%);padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.3);">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">New Sales Enquiry</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{r['name']} — {r.get('company') or 'no company provided'}</h1>
  </div>
  <div style="padding:28px 32px;background:#0A0B10;">
    <table style="width:100%;border-collapse:collapse;color:#e5e7eb;font-size:14px;margin-bottom:20px;">
      {rows}
    </table>
    <div style="padding:16px;background:#05070A;border-left:3px solid #19CDFF;border-radius:4px;">
      <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px;">Message</div>
      <div style="color:#e5e7eb;font-size:14px;line-height:1.6;">{message_html}</div>
    </div>
    <div style="margin-top:20px;">
      <a href="mailto:{r['email']}" style="display:inline-block;background:#19CDFF;color:#05070A;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:700;font-size:13px;letter-spacing:0.05em;text-transform:uppercase;">Reply to {r['name'].split(' ')[0]}</a>
    </div>
  </div>
  <div style="background:#05070A;padding:16px 32px;border-top:1px solid rgba(255,255,255,0.05);">
    <p style="color:#6b7280;font-size:11px;margin:0;">Sent by the GymAxis public contact form · Turnstile-verified · Visible in Master Admin → Growth → Communications inbox</p>
  </div>
</div>"""


@router.post("/contact")
async def submit_contact(payload: ContactSubmission, request: Request):
    """Accept a public contact submission from the /contact page."""
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"contact_ip:{ip}", max_requests=5, window_seconds=600)
    await verify_captcha(payload.cf_turnstile_response, action="contact")

    record_id = str(uuid.uuid4())
    record = {
        "id": record_id,
        "name": sanitise_string(payload.name),
        "email": payload.email.lower().strip(),
        "company": sanitise_string(payload.company) if payload.company else None,
        "phone": sanitise_string(payload.phone) if payload.phone else None,
        "gym_size": sanitise_string(payload.gym_size) if payload.gym_size else None,
        "interest": _normalise(payload.interest, _INTEREST_OPTIONS),
        "preferred_contact_time": _normalise(payload.preferred_contact_time, _CONTACT_TIME_OPTIONS),
        "heard_from": _normalise(payload.heard_from, _HEARD_FROM_OPTIONS),
        "message": sanitise_string(payload.message),
        "source": "public_contact_form",
        "status": "new",  # new | read | replied | closed
        "replies": [],     # appended via Communications Inbox reply endpoint
        "ip": ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_contact_submissions.insert_one(record)

    recipient = os.environ.get("CONTACT_NOTIFY_EMAIL") or os.environ.get(
        "TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com",
    )
    subject = f"[Enquiry] {record['name']} — {record.get('company') or record['email']}"
    try:
        asyncio.create_task(send_email(recipient, subject, _notification_html(record)))
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning(f"contact notification dispatch failed: {e}")

    return {"ok": True, "id": record_id}
