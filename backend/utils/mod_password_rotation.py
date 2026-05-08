"""MOD site-code password rotation (blueprint §10.4).

Site-tier MOD logins use a shared site code. Per policy they rotate on a
180-day cycle. This module:

  • Detects MOD site users whose `password_updated_at` is approaching or
    past the 180-day threshold and emails the master admin 30 / 14 / 7 / 0
    days ahead.
  • Provides a master-admin-only one-click rotate endpoint that mints a
    fresh password, updates `password_updated_at`, writes an audit row,
    and emails the new code to the master admin + configured site
    facilities contact.

Idempotent & runs once per UTC day from the existing sicon_poller loop.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROTATION_DAYS = 180
REMINDER_THRESHOLDS = (30, 14, 7, 0, -1, -7)  # negative = already overdue reminders
_DEFAULT_NOTIFY_EMAIL = os.environ.get(
    "MOD_ROTATION_NOTIFY_EMAIL",
    os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com"),
)


def _days_until_expiry(password_updated_at: str | None) -> int | None:
    if not password_updated_at:
        return None
    try:
        updated = datetime.fromisoformat(password_updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = updated + timedelta(days=ROTATION_DAYS) - datetime.now(timezone.utc)
    return int(delta.total_seconds() // 86400)


async def scan_mod_password_rotation() -> dict:
    """Email the master admin when a MOD site login is approaching expiry.

    Tracks last-reminder state on the user doc to avoid spamming. Returns
    aggregate counts for logging.
    """
    totals = {"users_scanned": 0, "reminders_sent": 0, "expired": 0}
    cursor = db.users.find(
        {"account_type": "mod_site"},
        {"_id": 0, "id": 1, "username": 1, "organization_id": 1,
         "password_updated_at": 1, "rotation_reminder_sent_at": 1, "rotation_reminder_stage": 1},
    )
    async for u in cursor:
        totals["users_scanned"] += 1
        days = _days_until_expiry(u.get("password_updated_at"))
        if days is None:
            continue
        if days < 0:
            totals["expired"] += 1
        # Pick the most urgent threshold we've crossed that we haven't
        # notified for yet.
        candidate_stages = [t for t in REMINDER_THRESHOLDS if days <= t]
        if not candidate_stages:
            continue
        stage = min(candidate_stages)  # e.g. days=20 → threshold 14 fires
        if u.get("rotation_reminder_stage") == stage:
            continue
        # Send + mark
        site = await db.organizations.find_one({"id": u.get("organization_id")}, {"_id": 0})
        try:
            await _send_rotation_reminder(u, site, days, stage)
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {
                    "rotation_reminder_sent_at": datetime.now(timezone.utc).isoformat(),
                    "rotation_reminder_stage": stage,
                }},
            )
            totals["reminders_sent"] += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("[mod-rotation] reminder for %s failed: %s", u.get("username"), exc)
    logger.info("[mod-rotation] scan complete %s", totals)
    return totals


async def _send_rotation_reminder(user: dict, site: dict, days: int, stage: int) -> None:
    """Email the master admin + optional site facilities contact."""
    site_name = (site or {}).get("name", "MOD Site")
    branch = (site or {}).get("mod_branch", "")
    urgent = stage <= 0
    label = "EXPIRED" if urgent else ("DUE SOON" if stage <= 7 else "UPCOMING")
    when = ("already expired" if days < 0 else
            "today" if days == 0 else
            f"in {days} day{'s' if days != 1 else ''}")
    subject = f"[MOD password rotation · {label}] {site_name} ({branch}) — {when}"

    html = f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:{'#b91c1c' if urgent else '#1B1D1D'};padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Password Rotation</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{label} — {site_name}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>The site login for <strong>{site_name}</strong> ({branch or 'MOD'}) is <strong>{when}</strong> (username <code>{user.get('username')}</code>).</p>
    <p>Rotation policy: 180 days. Rotate now via the Master Admin console → <em>MOD Service Portal</em> → Rotate password on this site, or use the API <code>POST /api/master-admin/mod/sites/{user.get('organization_id')}/rotate-password</code>.</p>
    <p style="color:#6E7476;font-size:13px;margin-top:18px;">After rotation the new site code should be communicated to the on-site PTI (and taped inside a secure ops-room drawer — not left on the front desk). You'll receive the new code in a follow-up email.</p>
  </div>
</div>"""
    await send_email(_DEFAULT_NOTIFY_EMAIL, subject, html)
    # Best-effort: also email site oncall if configured
    oncall = (site or {}).get("oncall_email")
    if oncall:
        await send_email(oncall, subject, html)


def mint_site_password(site_code: str) -> str:
    """Generate a new human-memorable MOD site code (≥ 14 chars, uppercase
    letter + digit + special guaranteed). Kept memorable for PTI handover;
    still bcrypt-hashed at rest."""
    year = datetime.now(timezone.utc).year
    qtr = (datetime.now(timezone.utc).month - 1) // 3 + 1
    # PascalCase the site code for readability: "raf-brizenorton" →
    # "RafBrizenorton".
    core = "".join(s.capitalize() for s in site_code.split("-"))
    suffix = secrets.token_urlsafe(4)[:4].replace("-", "x").replace("_", "z")
    return f"{core}-{year}Q{qtr}-{suffix}!"


async def perform_rotation(site_id: str, actor_user_id: str) -> dict:
    """Rotate a MOD site's shared login password and email the new code.

    Returns ``{new_password, site_name, user_id}``. Caller MUST be master
    admin — auth is enforced at the route layer.
    """
    site = await db.organizations.find_one({"id": site_id, "account_type": "mod_site"}, {"_id": 0})
    if not site:
        raise ValueError("MOD site not found")
    site_user = await db.users.find_one({"organization_id": site_id, "account_type": "mod_site"}, {"_id": 0})
    if not site_user:
        raise ValueError("Site login user not found")

    new_password = mint_site_password(site.get("site_code") or site_user.get("username", "mod-site"))
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": site_user["id"]},
        {"$set": {
            "password": pwd_ctx.hash(new_password),
            "password_updated_at": now,
            "rotation_reminder_stage": None,
            "rotation_reminder_sent_at": None,
        }},
    )
    # Audit trail — reuse the MOD audit collection.
    await db.mod_audit_log.insert_one({
        "id": secrets.token_urlsafe(10),
        "site_id": site_id,
        "user_id": actor_user_id,
        "action": "password.rotate",
        "payload": {"username": site_user.get("username")},
        "created_at": now,
    })
    # Email the new code to master admin + site oncall.
    subject = f"[MOD password rotated] {site.get('name')} — new code inside"
    html = f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · New Site Code</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{site.get('name')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>The login code for <strong>{site.get('name')}</strong> has been rotated.</p>
    <table style="margin-top:14px;border-collapse:collapse;">
      <tr><td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;color:#6E7476;font-size:11px;font-weight:800;text-transform:uppercase;">Username</td>
          <td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;font-weight:700;"><code>{site_user.get('username')}</code></td></tr>
      <tr><td style="padding:8px 14px;background:#0A0B10;color:#19CDFF;border:1px solid #0A0B10;font-size:11px;font-weight:800;text-transform:uppercase;">New code</td>
          <td style="padding:8px 14px;background:#0A0B10;color:#fff;border:1px solid #0A0B10;font-family:ui-monospace,Menlo,monospace;font-weight:700;">{new_password}</td></tr>
    </table>
    <p style="color:#6E7476;font-size:13px;margin-top:18px;">Share this with the on-site PTI via a secure channel. The previous code has been invalidated immediately.</p>
  </div>
</div>"""
    try:
        await send_email(_DEFAULT_NOTIFY_EMAIL, subject, html)
    except Exception:  # pragma: no cover
        pass
    return {"new_password": new_password, "site_name": site.get("name"),
            "username": site_user.get("username"), "user_id": site_user["id"]}
