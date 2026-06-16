"""
Trial lifecycle management.
Handles trial expiry, reminder emails, auto-suspend, and status transitions.
Invoked by the shared background poller (utils/sicon_poller.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

# Trial-ending CTA destination — login-gated paid checkout page (iter 221).
# Deliberately the in-app /choose-plan page (no free-trial re-offer), not the
# public marketing pricing page.
CHOOSE_PLAN_URL = "https://www.pulsefitness.ai/choose-plan"
# Iter 259 — Service Providers convert on their dedicated Stripe page.
PROVIDER_UPGRADE_URL = "https://www.pulsefitness.ai/service-desk/upgrade"

# Trial status transitions
STATUS_ACTIVE = "active"
STATUS_EXPIRING_SOON = "expiring_soon"  # ≤ 4 days remaining
STATUS_EXPIRED = "expired"              # hard lock, 30-day grace window
STATUS_SUSPENDED = "suspended"          # after grace window, data hidden
STATUS_CONVERTED = "converted"          # customer upgraded to paid

REMINDER_DAYS = [10, 13]  # Day offsets from trial_start when to nudge
GRACE_PERIOD_DAYS = 30    # Days between expiry → suspension
TRIAL_BANNER_THRESHOLD_DAYS = 4  # Show "expiring soon" banner when ≤ this many days left


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    if not value:
        return _now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return _now()


def compute_trial_state(org: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given an org document, return the current trial state without mutating DB.
    Callers use this for the trial banner + locked screen decision.
    """
    if not org.get("is_trial"):
        return {"is_trial": False}

    if org.get("trial_status") == STATUS_CONVERTED:
        return {"is_trial": False, "converted": True}

    trial_ends = _parse_iso(org.get("trial_ends_at", ""))
    suspends_at = _parse_iso(org.get("trial_suspends_at", "")) if org.get("trial_suspends_at") else (trial_ends + timedelta(days=GRACE_PERIOD_DAYS))
    now = _now()

    seconds_left = (trial_ends - now).total_seconds()
    days_left = int(seconds_left // 86400)

    if now >= suspends_at:
        status = STATUS_SUSPENDED
    elif now >= trial_ends:
        status = STATUS_EXPIRED
    elif days_left <= TRIAL_BANNER_THRESHOLD_DAYS:
        status = STATUS_EXPIRING_SOON
    else:
        status = STATUS_ACTIVE

    return {
        "is_trial": True,
        "status": status,
        "days_left": max(0, days_left),
        "hours_left": max(0, int(seconds_left // 3600)),
        "trial_ends_at": org.get("trial_ends_at"),
        "trial_starts_at": org.get("trial_starts_at"),
        "trial_duration_days": org.get("trial_duration_days"),
        "trial_suspends_at": suspends_at.isoformat(),
        "can_use_platform": status in (STATUS_ACTIVE, STATUS_EXPIRING_SOON),
        "read_only": status == STATUS_EXPIRED,
        "locked_out": status == STATUS_SUSPENDED,
        "extended_by_days": org.get("trial_extended_by_days", 0),
    }


def _trial_reminder_html(org_name: str, days_left: int, upgrade_url: str) -> str:
    urgency = "Final day" if days_left <= 1 else f"{days_left} days left"
    hero_bg = "#EF4444" if days_left <= 1 else "#F59E0B" if days_left <= 4 else "#0055FF"
    return f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: {hero_bg}; padding: 36px 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">{urgency} of your Pulse Fitness trial</h1>
    </div>
    <div style="padding: 40px 32px;">
        <h2 style="color: #1a1a1a; margin: 0 0 16px;">Hi {org_name},</h2>
        <p style="color: #444; line-height: 1.7;">Your 2-week trial of Pulse Fitness ends in <strong>{days_left} day{'s' if days_left != 1 else ''}</strong>. To keep your equipment data, PPM schedules, and site history, upgrade now and we'll switch you over seamlessly — no re-import required.</p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{upgrade_url}" style="display: inline-block; background: #0055FF; color: white; padding: 16px 36px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px;">Upgrade to Pro</a>
        </div>
        <p style="color: #888; font-size: 13px;">If you'd prefer to chat first, just reply to this email.</p>
    </div>
    <div style="background: #f5f5f5; padding: 18px; text-align: center;">
        <p style="color: #888; font-size: 12px; margin: 0;">Pulse Fitness AI · Gym Equipment Maintenance Platform</p>
    </div>
    </div>"""


def _provider_trial_reminder_html(org_name: str, days_left: int, upgrade_url: str) -> str:
    """Iter 259 — Service Provider variant: desk copy + orange brand + the
    dedicated /service-desk/upgrade CTA (£99/month self-serve)."""
    urgency = "Final day" if days_left <= 1 else f"{days_left} days left"
    hero_bg = "#EF4444" if days_left <= 1 else "#F97316"
    return f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff;">
    <div style="background: {hero_bg}; padding: 36px 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">{urgency} of your Service Desk trial</h1>
    </div>
    <div style="padding: 40px 32px;">
        <h2 style="color: #1a1a1a; margin: 0 0 16px;">Hi {org_name},</h2>
        <p style="color: #444; line-height: 1.7;">Your 14-day Service Desk trial ends in <strong>{days_left} day{'s' if days_left != 1 else ''}</strong>. Upgrade to Pro (&pound;99/month) to keep your cases, customers, engineers and SLA history exactly as they are — nothing to re-import, no interruption for your team in the field.</p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{upgrade_url}" style="display: inline-block; background: #F97316; color: white; padding: 16px 36px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px;">Upgrade to Pro &mdash; &pound;99/month</a>
        </div>
        <p style="color: #888; font-size: 13px;">Unlimited engineers, cases and customers &middot; cancel anytime. Questions? Just reply to this email.</p>
    </div>
    <div style="background: #f5f5f5; padding: 18px; text-align: center;">
        <p style="color: #888; font-size: 12px; margin: 0;">Pulse Fitness Service Desk &middot; Field service operations for fitness suppliers</p>
    </div>
    </div>"""


async def _find_primary_contact(org_id: str) -> str:
    """Find a primary contact email for trial emails — owner role preferred."""
    primary = (await db.organizations.find_one({"id": org_id}, {"_id": 0, "primary_contact": 1}) or {}).get("primary_contact") or {}
    if primary.get("email"):
        return primary["email"]
    owner = await db.users.find_one(
        {"organization_id": org_id, "role": "owner"},
        {"_id": 0, "email": 1}
    )
    return (owner or {}).get("email", "")


def _pick_due_reminder(days_elapsed: int, days_left: int, sent: set[str]) -> str | None:
    """Determine which reminder marker, if any, should be sent now."""
    if days_elapsed >= 13 and days_left <= 1 and "day13" not in sent:
        return "day13"
    if days_elapsed >= 10 and days_left <= 4 and "day10" not in sent:
        return "day10"
    return None


async def _send_reminder_if_due(org: Dict[str, Any], frontend_url: str) -> bool:
    """Send the appropriate trial reminder email at days 10 and 13 (if not already sent)."""
    org_id = org["id"]
    trial_start = _parse_iso(org.get("trial_started_at") or org.get("created_at", ""))
    trial_ends = _parse_iso(org.get("trial_ends_at", ""))
    now = _now()
    days_elapsed = int((now - trial_start).total_seconds() // 86400)
    days_left = max(0, int((trial_ends - now).total_seconds() // 86400))

    due_marker = _pick_due_reminder(days_elapsed, days_left,
                                    set(org.get("trial_reminders_sent", []) or []))
    if not due_marker:
        return False

    recipient = await _find_primary_contact(org_id)
    if not recipient:
        logger.info(f"[Trial] No recipient for org {org_id} — skipping reminder")
        return False

    # Iter 259 — Service Providers get desk-specific copy + upgrade URL.
    if org.get("account_type") == "service_provider":
        upgrade_url = PROVIDER_UPGRADE_URL
        html = _provider_trial_reminder_html(org.get("name", "there"), days_left or 1, upgrade_url)
        subject = ("Final day of your Service Desk trial" if due_marker == "day13"
                   else f"{days_left} days left of your Service Desk trial")
    else:
        upgrade_url = CHOOSE_PLAN_URL
        html = _trial_reminder_html(org.get("name", "there"), days_left or 1, upgrade_url)
        subject = ("Final day of your Pulse Fitness trial" if due_marker == "day13"
                   else f"{days_left} days left of your Pulse Fitness trial")
    sent_ok = await send_email(recipient, subject, html, organization_id=org_id)
    if sent_ok:
        await db.organizations.update_one(
            {"id": org_id},
            {"$addToSet": {"trial_reminders_sent": due_marker},
             "$set": {"last_trial_reminder_at": now.isoformat()}}
        )
        logger.info(f"[Trial] Sent {due_marker} reminder for org {org_id} to {recipient}")
    return sent_ok


async def _apply_status_transition(org: Dict[str, Any]) -> str | None:
    """
    Apply an expiry/suspension state change if warranted.
    Returns the new status if one was set, else None.
    """
    state = compute_trial_state(org)
    if not state.get("is_trial"):
        return None

    current = org.get("trial_status", STATUS_ACTIVE)
    target = state["status"]

    if current == target:
        return None

    # Don't demote out of "converted"
    if current == STATUS_CONVERTED:
        return None

    update: Dict[str, Any] = {"trial_status": target, "trial_status_updated_at": _now().isoformat()}
    if target == STATUS_EXPIRED:
        update["status"] = "trial_expired"
    elif target == STATUS_SUSPENDED:
        update["status"] = "suspended"

    await db.organizations.update_one({"id": org["id"]}, {"$set": update})
    logger.info(f"[Trial] Org {org['id']} transitioned {current} → {target}")
    return target


async def run_trial_lifecycle_once(frontend_url: str = "") -> Dict[str, int]:
    """
    Scan all trial orgs once: send reminders, apply status transitions.
    Safe to call every 5 minutes — reminder dedup uses trial_reminders_sent array.
    """
    counts = {"scanned": 0, "reminders_sent": 0, "expired": 0, "suspended": 0, "expiring_soon": 0}

    cursor = db.organizations.find(
        {"is_trial": True, "trial_status": {"$ne": STATUS_CONVERTED}},
        {"_id": 0}
    )
    async for org in cursor:
        counts["scanned"] += 1
        try:
            if await _send_reminder_if_due(org, frontend_url):
                counts["reminders_sent"] += 1
            new_status = await _apply_status_transition(org)
            if new_status == STATUS_EXPIRED:
                counts["expired"] += 1
            elif new_status == STATUS_SUSPENDED:
                counts["suspended"] += 1
            elif new_status == STATUS_EXPIRING_SOON:
                counts["expiring_soon"] += 1
        except Exception as e:
            logger.warning(f"[Trial] Error processing org {org.get('id')}: {e}")

    return counts
