"""Iter 220ea·31 — Engineer 10-day trial lifecycle worker.

Watertight, idempotent state machine driven on a timer:

    active ──(day 9)──► send "ends tomorrow" (reminder_sent_at)
    active ──(day 10, ends_at)──► feedback_pending  (+ feedback form email,
                                  feedback_token, grace_until = +3 days)
    feedback_pending ──(+2 days, no feedback)──► send last-chance nudge
    feedback_pending/accepted ──(grace_until passed, not paid)──► expired
                                  → partner suspended, in-flight jobs returned

The accept→Stripe→converted_paid and decline→suspend transitions happen
synchronously in the feedback endpoint / webhook; this worker only handles
the time-based nudges and the no-response auto-suspend.

Every transition is guarded by a per-step timestamp so a re-run never
double-sends or double-suspends. Started from server.py via run_forever().
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


async def run_once() -> dict:
    import os
    grace_days = max(0, int(os.environ.get("ENGINEER_TRIAL_GRACE_DAYS", "3") or 3))
    now = _now()
    stats = {"reminders": 0, "feedback_requests": 0, "lastchance": 0, "expired": 0}

    from utils.partner_emails import (
        send_trial_ending_tomorrow, send_trial_feedback_request, send_trial_lastchance,
    )

    # ── 1. Active trials: day-9 reminder + day-10 feedback transition ──
    actives = await db.partner_engineers.find(
        {"trial.status": "active"},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "trial": 1},
    ).to_list(500)
    for p in actives:
        trial = p.get("trial") or {}
        ends_at = _parse(trial.get("ends_at"))
        if not ends_at:
            continue
        if now >= ends_at:
            token = secrets.token_urlsafe(32)
            grace_until = (now + timedelta(days=grace_days)).isoformat()
            await db.partner_engineers.update_one(
                {"id": p["id"], "trial.status": "active"},
                {"$set": {
                    "trial.status": "feedback_pending",
                    "trial.feedback_token": token,
                    "trial.feedback_sent_at": now.isoformat(),
                    "trial.grace_until": grace_until,
                    "updated_at": now.isoformat(),
                }},
            )
            try:
                await send_trial_feedback_request(p.get("email") or "", p.get("full_name") or "", token)
            except Exception:
                logger.warning("[trial] feedback email failed for %s", p["id"], exc_info=True)
            await _audit(p["id"], "trial_feedback_requested")
            stats["feedback_requests"] += 1
        elif now >= ends_at - timedelta(days=1) and not trial.get("reminder_sent_at"):
            await db.partner_engineers.update_one(
                {"id": p["id"], "trial.reminder_sent_at": None},
                {"$set": {"trial.reminder_sent_at": now.isoformat()}},
            )
            try:
                await send_trial_ending_tomorrow(p.get("email") or "", p.get("full_name") or "", trial.get("ends_at"))
            except Exception:
                logger.warning("[trial] reminder email failed for %s", p["id"], exc_info=True)
            stats["reminders"] += 1

    # ── 2. feedback_pending / accepted: last-chance + auto-suspend ──
    pendings = await db.partner_engineers.find(
        {"trial.status": {"$in": ["feedback_pending", "accepted"]}},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "trial": 1},
    ).to_list(500)
    for p in pendings:
        trial = p.get("trial") or {}
        fb_sent = _parse(trial.get("feedback_sent_at"))
        # Last-chance nudge: +2 days after the feedback email, only if they
        # haven't submitted and we haven't nudged yet.
        if (
            trial.get("status") == "feedback_pending"
            and not trial.get("feedback")
            and not trial.get("lastchance_sent_at")
            and fb_sent
            and now >= fb_sent + timedelta(days=2)
            and trial.get("feedback_token")
        ):
            await db.partner_engineers.update_one(
                {"id": p["id"], "trial.lastchance_sent_at": None},
                {"$set": {"trial.lastchance_sent_at": now.isoformat()}},
            )
            try:
                await send_trial_lastchance(p.get("email") or "", p.get("full_name") or "", trial["feedback_token"])
            except Exception:
                logger.warning("[trial] last-chance email failed for %s", p["id"], exc_info=True)
            stats["lastchance"] += 1

        # Auto-suspend once the grace window passes with no payment.
        grace_until = _parse(trial.get("grace_until"))
        if grace_until and now >= grace_until and trial.get("status") != "converted_paid":
            res = await db.partner_engineers.update_one(
                {"id": p["id"], "trial.status": {"$in": ["feedback_pending", "accepted"]}},
                {"$set": {
                    "trial.status": "expired",
                    "status": "suspended",
                    "subscription.status": "trial_expired",
                    "updated_at": now.isoformat(),
                }},
            )
            if res.modified_count:
                try:
                    from routes.partners import _handle_partner_loss_of_access
                    await _handle_partner_loss_of_access(p["id"], "trial_expired")
                except Exception:
                    logger.warning("[trial] loss-of-access failed for %s", p["id"], exc_info=True)
                await _audit(p["id"], "trial_expired_suspended")
                stats["expired"] += 1

    if any(stats.values()):
        logger.info("[trial] lifecycle run: %s", stats)
    return stats


async def _audit(partner_id: str, action: str) -> None:
    try:
        await db.partner_audit_log.insert_one({
            "partner_id": partner_id,
            "actor_id": "system",
            "action": action,
            "at": _now().isoformat(),
        })
    except Exception:
        pass


async def run_forever(hours: float = 6) -> None:
    import asyncio
    interval = max(60, int(hours * 3600))
    while True:
        try:
            await run_once()
        except Exception:
            logger.exception("[trial] lifecycle sweep failed")
        await asyncio.sleep(interval)
