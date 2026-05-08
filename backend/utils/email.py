import asyncio
import logging
import os
from datetime import datetime, timezone

from utils.database import RESEND_API_KEY, SENDER_EMAIL, db

logger = logging.getLogger(__name__)

try:
    import resend
    if RESEND_API_KEY:
        resend.api_key = RESEND_API_KEY
except ImportError:
    resend = None


async def _record_email_event(*, to: str, subject: str, status: str, error: str | None) -> None:
    """Best-effort write to the ``email_send_events`` audit collection.

    Powers the Master Admin "email health" pill. Capped to recent
    history via a TTL index created in :mod:`server` startup.
    """
    try:
        await db.email_send_events.insert_one({
            "to": to,
            "subject": subject,
            "sender": SENDER_EMAIL or "",
            "status": status,            # "sent" | "failed" | "no_api_key" | "bad_sender"
            "error": (error or "")[:500],
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        # Telemetry failures must never block real email sends.
        pass


async def send_email(to: str, subject: str, html: str, attachments: list[dict] | None = None):
    if not RESEND_API_KEY:
        logger.warning(f"Email NOT sent (RESEND_API_KEY missing in env): to={to}, subject={subject!r}")
        await _record_email_event(to=to, subject=subject, status="no_api_key", error="RESEND_API_KEY missing")
        return False
    if not SENDER_EMAIL or "@" not in SENDER_EMAIL:
        logger.warning(f"Email NOT sent (SENDER_EMAIL invalid in env: {SENDER_EMAIL!r}): to={to}")
        await _record_email_event(to=to, subject=subject, status="bad_sender", error=f"SENDER_EMAIL={SENDER_EMAIL!r}")
        return False
    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html
        }
        if attachments:
            params["attachments"] = attachments
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to} (subject={subject!r}, resend_id={result.get('id') if isinstance(result, dict) else result})")
        await _record_email_event(to=to, subject=subject, status="sent", error=None)
        return True
    except Exception as e:
        logger.error(f"Email send FAILED via Resend: to={to}, subject={subject!r}, sender={SENDER_EMAIL!r}, error={e!r}")
        await _record_email_event(to=to, subject=subject, status="failed", error=repr(e))
        return False


async def send_welcome_email(email: str, name: str):
    html = f"""<div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
    <div style="background: #0055FF; padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0;">Welcome to GymAxis AI</h1>
    </div>
    <div style="padding: 30px; background: #f9f9f9;">
        <h2>Hi {name},</h2>
        <p>Welcome to GymAxis AI - the complete gym maintenance platform.</p>
        <p>Here's what you can do:</p>
        <ul>
            <li><strong>AI Fault Diagnosis</strong> - Get instant repair guidance</li>
            <li><strong>Risk Assessments</strong> - Generate professional reports</li>
            <li><strong>Issue Tracking</strong> - Log and manage equipment faults</li>
            <li><strong>Maintenance Checklists</strong> - Keep your gym safe and compliant</li>
        </ul>
        <p>Get started by logging into your dashboard.</p>
        <a href="#" style="display: inline-block; background: #0055FF; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Go to Dashboard</a>
    </div>
    </div>"""
    await send_email(email, "Welcome to GymAxis AI", html)


async def send_report_notification(email: str, name: str, report_type: str, report_id: str):
    html = f"""<div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
    <div style="background: #0055FF; padding: 20px; text-align: center;">
        <h2 style="color: white; margin: 0;">GymAxis AI - Report Ready</h2>
    </div>
    <div style="padding: 30px; background: #f9f9f9;">
        <p>Hi {name},</p>
        <p>Your <strong>{report_type}</strong> has been generated and is ready to view.</p>
        <p>Log into your dashboard to view, print, or download the report.</p>
    </div>
    </div>"""
    # Route through test recipient in test mode
    test_mode = 'resend.dev' in (os.environ.get('SENDER_EMAIL', '') or '')
    test_recipient = os.environ.get('TEST_RECIPIENT_EMAIL', '')
    recipient = (test_recipient or email) if test_mode else email
    await send_email(recipient, f"GymAxis AI - {report_type} Ready", html)


async def send_password_reset_email(email: str, name: str, reset_url: str):
    html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: #0055FF; padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 22px;">GymAxis AI</h1>
    </div>
    <div style="padding: 40px 30px;">
        <h2 style="color: #1a1a1a; margin: 0 0 12px;">Password Reset Request</h2>
        <p style="color: #555; line-height: 1.6;">Hi {name},</p>
        <p style="color: #555; line-height: 1.6;">We received a request to reset your password. Click the button below to set a new password:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="display: inline-block; background: #0055FF; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 15px;">Reset Password</a>
        </div>
        <p style="color: #888; font-size: 13px; line-height: 1.6;">This link will expire in 1 hour. If you didn't request this, you can safely ignore this email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #aaa; font-size: 12px;">If the button doesn't work, copy and paste this URL into your browser:<br/><a href="{reset_url}" style="color: #0055FF; word-break: break-all;">{reset_url}</a></p>
    </div>
    <div style="background: #f5f5f5; padding: 16px 30px; text-align: center;">
        <p style="color: #aaa; font-size: 11px; margin: 0;">GymAxis AI · Gym Equipment Maintenance Platform</p>
    </div>
    </div>"""
    return await send_email(email, "Reset Your Password — GymAxis AI", html)



async def send_onboarding_invite_email(email: str, recipient_name: str, customer_name: str,
                                        share_url: str, sender_name: str, deadline_days: int = 14) -> bool:
    """Send a branded onboarding invite to a prospective customer's primary contact."""
    greeting = f"Hi {recipient_name}," if recipient_name else "Hello,"
    html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: linear-gradient(135deg, #0055FF 0%, #0033AA 100%); padding: 36px 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px; letter-spacing: -0.5px;">Welcome to GymAxis AI</h1>
        <p style="color: #cfe0ff; margin: 8px 0 0; font-size: 13px;">Your equipment management platform is ready</p>
    </div>
    <div style="padding: 40px 32px;">
        <h2 style="color: #1a1a1a; margin: 0 0 16px; font-size: 20px;">Let's get {customer_name or 'you'} set up</h2>
        <p style="color: #444; line-height: 1.7; margin: 0 0 16px;">{greeting}</p>
        <p style="color: #444; line-height: 1.7; margin: 0 0 20px;">
            {sender_name} has prepared a secure onboarding form so we can configure GymAxis for your sites, staff,
            and equipment in one go. It takes around <strong>10–15 minutes</strong> and auto-saves as you go —
            you can complete it in multiple sessions.
        </p>
        <div style="background: #f0f7ff; border-left: 4px solid #0055FF; padding: 18px 20px; margin: 24px 0; border-radius: 4px;">
            <p style="margin: 0 0 6px; color: #0033AA; font-weight: 600; font-size: 13px;">What you'll need</p>
            <ul style="margin: 0; padding-left: 18px; color: #444; line-height: 1.7; font-size: 14px;">
                <li>Your legal entity name and billing address</li>
                <li>Details of each site you operate</li>
                <li>Staff members who need access (we'll email them to set passwords)</li>
                <li>Your equipment list — you can paste rows from Excel</li>
            </ul>
        </div>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{share_url}" style="display: inline-block; background: #0055FF; color: white; padding: 16px 36px;
               text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px; letter-spacing: 0.3px;">
               Open Onboarding Form →
            </a>
        </div>
        <p style="color: #888; font-size: 13px; line-height: 1.6; text-align: center;">
            This secure link expires in {deadline_days} days. Please complete it before then.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 28px 0;" />
        <p style="color: #aaa; font-size: 12px; line-height: 1.6;">
            If the button doesn't work, copy and paste this URL into your browser:<br/>
            <a href="{share_url}" style="color: #0055FF; word-break: break-all;">{share_url}</a>
        </p>
    </div>
    <div style="background: #f5f5f5; padding: 18px 30px; text-align: center;">
        <p style="color: #888; font-size: 12px; margin: 0;">GymAxis AI · Gym Equipment Maintenance Platform</p>
        <p style="color: #aaa; font-size: 11px; margin: 4px 0 0;">Sent by {sender_name}</p>
    </div>
    </div>"""
    return await send_email(email, f"Onboarding invitation for {customer_name or 'your organisation'}", html)



async def send_trial_signup_notification(trial: dict):
    """Notify the platform owner(s) that a new trial user has signed up.

    Recipient(s) controlled by env var TRIAL_SIGNUP_NOTIFY_EMAIL
    (defaults to Lee@gymaxisai.com). Comma-separated list supported.
    """
    recipients_raw = os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        return False

    name = trial.get("full_name") or "New user"
    email = trial.get("email") or ""
    company = trial.get("company_name") or ""
    phone = trial.get("phone") or "—"
    days = trial.get("trial_duration_days") or 14
    org_id = trial.get("organization_id") or ""
    frontend = os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    admin_link = f"{frontend}/master-admin" if frontend else "/master-admin"

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#05070A 0%,#0d1117 100%);padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.3);">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;">New Trial Signup</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{name} just started a {days}-day free trial</h1>
  </div>
  <div style="padding:28px 32px;background:#0A0B10;">
    <table style="width:100%;border-collapse:collapse;color:#e5e7eb;font-size:14px;">
      <tr><td style="padding:8px 0;color:#9ca3af;width:130px;">Full name</td><td style="padding:8px 0;font-weight:600;">{name}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Work email</td><td style="padding:8px 0;"><a href="mailto:{email}" style="color:#19CDFF;text-decoration:none;">{email}</a></td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Company / Gym</td><td style="padding:8px 0;font-weight:600;">{company}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Phone</td><td style="padding:8px 0;">{phone}</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Trial length</td><td style="padding:8px 0;">{days} days</td></tr>
      <tr><td style="padding:8px 0;color:#9ca3af;">Org ID</td><td style="padding:8px 0;font-family:monospace;font-size:12px;color:#9ca3af;">{org_id}</td></tr>
    </table>
    <div style="margin-top:24px;">
      <a href="{admin_link}" style="display:inline-block;background:#19CDFF;color:#05070A;padding:12px 24px;text-decoration:none;border-radius:999px;font-weight:700;font-size:13px;letter-spacing:0.05em;text-transform:uppercase;">Open Master Admin →</a>
    </div>
  </div>
  <div style="background:#05070A;padding:16px 32px;border-top:1px solid rgba(255,255,255,0.05);">
    <p style="color:#6b7280;font-size:11px;margin:0;">Sent by the GymAxis trial funnel · landing-page signup</p>
  </div>
</div>"""

    subject = f"[Trial] {name} — {company or email}"
    ok = True
    for rcpt in recipients:
        if not await send_email(rcpt, subject, html):
            ok = False
    return ok
