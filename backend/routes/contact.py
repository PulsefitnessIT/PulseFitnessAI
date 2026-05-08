"""Public contact form submission.

Backs the /contact page. Captures name/email/company/message, persists to
`public_contact_submissions`, notifies the platform owner and returns a
generic 200 regardless of downstream email status to avoid enumeration.
Protected by Turnstile.
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


class ContactSubmission(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(..., min_length=5, max_length=4000)
    cf_turnstile_response: Optional[str] = None


def _notification_html(r: dict) -> str:
    message_html = (r.get("message") or "").replace("\n", "<br/>")
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#05070A 0%,#0d1117 100%);padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.3);">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">New Contact Form Submission</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{r['name']} — {r.get('company') or 'no company provided'}</h1>
  </div>
  <div style="padding:28px 32px;background:#0A0B10;">
    <table style="width:100%;border-collapse:collapse;color:#e5e7eb;font-size:14px;margin-bottom:20px;">
      <tr><td style="padding:8px 0;color:#9ca3af;width:130px;">Name</td><td style="padding:8px 0;font-weight:600;">{r['name']}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Email</td><td style="padding:8px 0;"><a href="mailto:{r['email']}" style="color:#19CDFF;text-decoration:none;">{r['email']}</a></td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Company</td><td style="padding:8px 0;">{r.get('company') or '—'}</td></tr>
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
    <p style="color:#6b7280;font-size:11px;margin:0;">Sent by the GymAxis public contact form · Turnstile-verified</p>
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
        "message": sanitise_string(payload.message),
        "source": "public_contact_form",
        "status": "new",
        "ip": ip,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_contact_submissions.insert_one(record)

    recipient = os.environ.get("CONTACT_NOTIFY_EMAIL") or os.environ.get(
        "TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com",
    )
    subject = f"[Contact] {record['name']} — {record.get('company') or record['email']}"
    try:
        asyncio.create_task(send_email(recipient, subject, _notification_html(record)))
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning(f"contact notification dispatch failed: {e}")

    return {"ok": True, "id": record_id}
