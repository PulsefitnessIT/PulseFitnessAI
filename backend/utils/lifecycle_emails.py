"""Trial / lifecycle email templates (iter 215c2).

5 nurture sends that drive trial→paid conversion. Plain HTML so they
render correctly across Gmail, Outlook, and Apple Mail without external
CSS. Each template is idempotent — backed by a dedupe key per
(organization_id, template) so the cron can re-run safely.

Templates (timed off the trial start):
    welcome      — sent immediately after registration
    day2_check   — 36h post-signup, "have you set up your first member?"
    mid_trial    — day 2 of a 3-day trial: feature highlight + book demo
    expiry_warn  — 12h before trial expires: convert or extend
    winback      — 7d after cancellation: come back, here's a discount

Dispatch is handled by `send_lifecycle_emails()` — call it on a 30-min
interval cron (we hook it into the existing scheduler in server.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from utils.database import db, SENDER_EMAIL
from utils.email import send_email
from utils.notification_prefs_helper import can_send_lifecycle_email

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.gymaxisai.com/login"
DEMO_URL = "https://www.gymaxisai.com/contact"
PRICING_URL = "https://www.gymaxisai.com/pricing"


def _shell(title: str, body_html: str, cta_text: str, cta_url: str) -> str:
    """Branded HTML shell used by every lifecycle send."""
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
<div style="max-width:560px;margin:0 auto;padding:24px;">
  <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#ffffff;border-radius:16px;border:1px solid #e2e8f0;overflow:hidden;">
    <tr>
      <td style="padding:24px 28px;background:linear-gradient(135deg,#2563EB,#9D4CDD);color:#fff;">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;opacity:0.85;">GymAxis AI</div>
        <h1 style="margin:6px 0 0 0;font-size:22px;line-height:1.3;font-weight:800;">{title}</h1>
      </td>
    </tr>
    <tr>
      <td style="padding:28px;font-size:14px;line-height:1.6;color:#0f172a;">
        {body_html}
        <div style="margin-top:24px;text-align:center;">
          <a href="{cta_url}" style="display:inline-block;padding:12px 28px;background:#2563EB;color:#fff;text-decoration:none;border-radius:9999px;font-weight:600;font-size:14px;">{cta_text}</a>
        </div>
      </td>
    </tr>
    <tr>
      <td style="padding:18px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;text-align:center;">
        <p style="margin:0;">Sent by GymAxis AI · <a href="{LOGIN_URL}" style="color:#2563EB;text-decoration:none;">Sign in</a> · <a href="https://www.gymaxisai.com/legal/dpa" style="color:#2563EB;text-decoration:none;">Privacy</a></p>
        <p style="margin:6px 0 0 0;font-size:11px;color:#94a3b8;">You can manage email preferences inside your account.</p>
      </td>
    </tr>
  </table>
</div></body></html>"""


def _welcome(name: str) -> tuple[str, str]:
    body = f"""
        <p>Hi {name or 'there'},</p>
        <p>Welcome to GymAxis AI — your free 3-day trial is live, with every module unlocked. No credit card required.</p>
        <p><strong>What you can do in your first session:</strong></p>
        <ul style="padding-left:18px;">
            <li>Add your first member or upload a CSV</li>
            <li>Create a class template and publish a timetable</li>
            <li>Connect Stripe for instant payments</li>
            <li>Capture leads with an embeddable signup form</li>
        </ul>
        <p>Need help finding your way around? Hit "Take the Tour" inside the dashboard, or reply to this email.</p>
    """
    return ("Welcome to GymAxis AI · Your trial is live", _shell("Welcome aboard", body, "Open my dashboard", LOGIN_URL))


def _day2_check(name: str) -> tuple[str, str]:
    body = f"""
        <p>Hi {name or 'there'},</p>
        <p>You're a day into your GymAxis trial — how's it going?</p>
        <p>Operators who add at least one member and one plan in the first 48 hours are <strong>3x more likely</strong> to keep using the platform after their trial. Two quick wins:</p>
        <ol style="padding-left:18px;">
            <li><strong>Members tab</strong> → "Add member" or "Bulk import CSV"</li>
            <li><strong>Plans tab</strong> → "New plan" — even one recurring plan gets your members onto auto-pay</li>
        </ol>
        <p>Stuck? Reply to this email and a real person will help.</p>
    """
    return ("Day 2 of your trial — quick wins inside", _shell("How's it going?", body, "Continue setup", LOGIN_URL))


def _mid_trial(name: str) -> tuple[str, str]:
    body = f"""
        <p>Hi {name or 'there'},</p>
        <p>You're halfway through your trial. Want a 15-minute walkthrough with the team? We'll show you the AI features your competitors charge double for:</p>
        <ul style="padding-left:18px;">
            <li><strong>AI Triage</strong> — auto-suggest fault diagnoses from member-reported issues</li>
            <li><strong>AI Director</strong> — drafts marketing campaigns on demand</li>
            <li><strong>Auto-Bill</strong> — Stripe + family wallet integration that just works</li>
        </ul>
        <p>Or browse pricing first to see how the £150/mo bundle compares to per-module.</p>
    """
    return ("Want a personal walkthrough?", _shell("See what's possible", body, "Book a 15-min call", DEMO_URL))


def _expiry_warn(name: str, hours_left: int) -> tuple[str, str]:
    body = f"""
        <p>Hi {name or 'there'},</p>
        <p>Heads up — your free trial ends in <strong>about {hours_left} hour{'s' if hours_left != 1 else ''}</strong>.</p>
        <p>To keep your data and continue using GymAxis without interruption, choose a plan now. The bundle starts at £150/mo, or pick a single module from £29/mo.</p>
        <p>Need more time? Reply to this email — we'll happily extend your trial.</p>
    """
    return (f"Your trial ends in {hours_left}h", _shell("Don't lose your setup", body, "See plans", PRICING_URL))


def _winback(name: str) -> tuple[str, str]:
    body = f"""
        <p>Hi {name or 'there'},</p>
        <p>It's been a week since you cancelled GymAxis — we'd love to know what we could have done better.</p>
        <p>If you'd like a second look, here's <strong>20% off your first 3 months</strong> when you reactivate. Just reply with the word "reactivate" and we'll set it up for you.</p>
        <p>Either way, your data is still safe with us for the next 30 days.</p>
    """
    return ("Come back? Here's 20% off", _shell("We'd love to have you back", body, "Reactivate my account", LOGIN_URL))


async def _already_sent(org_id: str, template: str) -> bool:
    return bool(await db.lifecycle_email_sends.find_one({"organization_id": org_id, "template": template}, {"_id": 1}))


async def _mark_sent(org_id: str, user_id: str, template: str, email: str) -> None:
    await db.lifecycle_email_sends.insert_one({
        "organization_id": org_id, "user_id": user_id, "template": template,
        "email": email, "sent_at": datetime.now(timezone.utc).isoformat(),
    })


async def _dispatch(template: str, org: dict, user: dict, subject: str, html: str) -> bool:
    org_id = org.get("id")
    user_id = user.get("id") or org.get("primary_contact_user_id") or ""
    email = user.get("email") or org.get("primary_contact_email")
    if not email:
        return False
    if await _already_sent(org_id, template):
        return False
    if not await can_send_lifecycle_email(user_id, template):
        await _mark_sent(org_id, user_id, template, email)  # mark anyway so we don't retry
        return False
    try:
        await send_email(email, subject, html)
        await _mark_sent(org_id, user_id, template, email)
        return True
    except Exception:
        logger.exception("[lifecycle-email] %s send failed for %s", template, email)
        return False


async def send_welcome_now(org: dict, user: dict) -> bool:
    """Fire welcome email immediately on registration (called from auth.py)."""
    subj, html = _welcome(user.get("full_name") or "")
    return await _dispatch("welcome", org, user, subj, html)


async def send_lifecycle_emails() -> dict:
    """Cron entrypoint — scans trial orgs and dispatches the right send."""
    now = datetime.now(timezone.utc)
    sent = {"welcome": 0, "day2_check": 0, "mid_trial": 0, "expiry_warn": 0, "winback": 0, "skipped": 0}

    # Trial nurture — find any active trial that hasn't expired yet.
    trial_orgs = await db.organizations.find(
        {"is_trial": True, "trial_ends_at": {"$exists": True}},
        {"_id": 0, "id": 1, "name": 1, "trial_starts_at": 1, "trial_ends_at": 1,
         "primary_contact_email": 1, "primary_contact_user_id": 1, "is_trial": 1},
    ).to_list(2_000)

    for org in trial_orgs:
        try:
            ends_at = datetime.fromisoformat(str(org.get("trial_ends_at")).replace("Z", "+00:00"))
            starts_at = datetime.fromisoformat(str(org.get("trial_starts_at") or org.get("created_at")).replace("Z", "+00:00")) if org.get("trial_starts_at") else (ends_at - timedelta(days=3))
        except Exception:
            sent["skipped"] += 1
            continue
        hours_in = (now - starts_at).total_seconds() / 3600
        hours_left = (ends_at - now).total_seconds() / 3600
        user = await db.users.find_one(
            {"id": org.get("primary_contact_user_id")} if org.get("primary_contact_user_id") else {"organization_id": org["id"], "role": {"$in": ["owner", "admin"]}},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1},
        ) or {}

        if hours_in >= 36 and hours_left > 12:
            subj, html = _day2_check(user.get("full_name") or "")
            if await _dispatch("day2_check", org, user, subj, html):
                sent["day2_check"] += 1
        if hours_in >= 48 and hours_left > 12:
            subj, html = _mid_trial(user.get("full_name") or "")
            if await _dispatch("mid_trial", org, user, subj, html):
                sent["mid_trial"] += 1
        if 0 < hours_left <= 12:
            subj, html = _expiry_warn(user.get("full_name") or "", max(1, int(hours_left)))
            if await _dispatch("expiry_warn", org, user, subj, html):
                sent["expiry_warn"] += 1

    # Winback — orgs cancelled 7+ days ago but not yet emailed
    seven_d_ago = (now - timedelta(days=7)).isoformat()
    cancelled = await db.organizations.find(
        {"pending_cancellation": True, "cancellation_requested_at": {"$lte": seven_d_ago}},
        {"_id": 0, "id": 1, "name": 1, "primary_contact_email": 1, "primary_contact_user_id": 1},
    ).to_list(2_000)
    for org in cancelled:
        user = await db.users.find_one(
            {"id": org.get("primary_contact_user_id")} if org.get("primary_contact_user_id") else {"organization_id": org["id"]},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1},
        ) or {}
        subj, html = _winback(user.get("full_name") or "")
        if await _dispatch("winback", org, user, subj, html):
            sent["winback"] += 1

    logger.info("[lifecycle-email] cycle complete %s", sent)
    return sent
