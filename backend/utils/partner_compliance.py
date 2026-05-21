"""Iter 216h281 — Nightly compliance sweep for Partner Engineers.

Closes Gap 2 from the BA audit: partners' insurance and certifications
can lapse silently. This job runs once a day, sends T-30 / T-7 / T-0
reminder emails, and flips ``compliance_paused = True`` on the partner
record once anything has expired.

The pause is a soft signal — the existing routing / job-acceptance
endpoints will check ``compliance_paused`` before offering jobs.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.partner_emails import send_compliance_reminder

logger = logging.getLogger(__name__)

# Days-before-expiry at which we fire reminders. The job marks the
# reminder as fired on the partner so we never spam the same window
# twice.
REMINDER_WINDOWS = [30, 7, 0]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_until(expires_at: datetime, now: datetime) -> int:
    return (_aware(expires_at).date() - now.date()).days


def _bucket_for(days: int) -> int | None:
    """Return the tightest reminder-window bucket a given days-until
    value falls into. Iterating ascending picks the SMALLEST window
    that still fits — so a 5-day-out partner picks T-7, not T-30."""
    for w in sorted(REMINDER_WINDOWS):
        if days <= w:
            return w
    return None


async def _process_doc(partner: dict, kind: str, expires_at: datetime, now: datetime) -> dict:
    """Returns a dict patch to apply to the partner record, or {} if nothing
    changes."""
    days = _days_until(expires_at, now)
    bucket = _bucket_for(days)
    if bucket is None:
        return {}

    fired_field = f"{kind}_reminder_fired_window"
    last_fired = partner.get(fired_field)
    if last_fired == bucket:
        return {}  # already fired this window

    # Send the email.
    email = (partner.get("email") or "").strip()
    if not email:
        logger.warning("Partner %s has no email — skipping %s reminder", partner.get("id"), kind)
        return {fired_field: bucket}

    try:
        await send_compliance_reminder(
            email=email,
            full_name=partner.get("full_name", ""),
            kind=kind,
            expires_at=expires_at,
            days_remaining=max(days, 0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Compliance reminder send failed for %s/%s: %s", partner.get("id"), kind, exc)

    patch = {fired_field: bucket, f"{kind}_reminder_last_sent_at": now}
    # Bucket 0 means expired — flip the pause flag.
    if bucket == 0:
        patch["compliance_paused"] = True
        patch["compliance_pause_reason"] = f"{kind} expired"
    return patch


async def sweep_once() -> dict:
    """Single sweep. Returns a summary so the scheduler can log
    something useful.

    Iter 216h283 — extended to include the 4 gym-entry compliance
    docs (DBS, Right to Work, Safeguarding, Public Liability). Each
    is checked against its own ``expires_at`` field nested under
    ``compliance_docs[kind]``.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max(REMINDER_WINDOWS) + 1)
    query = {
        "status": "approved",
        "$or": [
            {"insurance_expires_at": {"$lte": cutoff}},
            {"qualifications_expires_at": {"$lte": cutoff}},
            {"compliance_docs.dbs.expires_at": {"$lte": cutoff}},
            {"compliance_docs.rtw.expires_at": {"$lte": cutoff}},
            {"compliance_docs.safeguarding.expires_at": {"$lte": cutoff}},
            {"compliance_docs.public_liability.expires_at": {"$lte": cutoff}},
        ],
    }
    partners = await db.partner_engineers.find(query, {"_id": 0}).to_list(2000)
    summary = {"checked": len(partners), "reminders_sent": 0, "paused": 0}
    DOC_KINDS_NESTED = ("dbs", "rtw", "safeguarding", "public_liability")
    for partner in partners:
        patch: dict = {}
        # Legacy top-level fields (insurance + qualifications).
        for kind in ("insurance", "qualifications"):
            exp = partner.get(f"{kind}_expires_at")
            if not exp or not isinstance(exp, datetime):
                continue
            update = await _process_doc(partner, kind, exp, now)
            if update:
                patch.update(update)
                if update.get(f"{kind}_reminder_last_sent_at"):
                    summary["reminders_sent"] += 1
                if update.get("compliance_paused"):
                    summary["paused"] += 1
        # Nested compliance_docs (iter 216h283).
        docs = partner.get("compliance_docs") or {}
        for kind in DOC_KINDS_NESTED:
            blob = docs.get(kind) or {}
            exp = blob.get("expires_at")
            if not exp or not isinstance(exp, datetime):
                continue
            # Synthesise a "merged" partner for the reminder window
            # tracker so we don't collide with the top-level field
            # names. We persist progress under
            # `compliance_docs[kind].reminder_fired_window`.
            partner_view = {
                **partner,
                f"{kind}_reminder_fired_window": blob.get("reminder_fired_window"),
            }
            update = await _process_doc(partner_view, kind, exp, now)
            if not update:
                continue
            # Translate the flat update back into the nested doc.
            nested_patch = {}
            if f"{kind}_reminder_fired_window" in update:
                nested_patch["reminder_fired_window"] = update[f"{kind}_reminder_fired_window"]
            if f"{kind}_reminder_last_sent_at" in update:
                nested_patch["reminder_last_sent_at"] = update[f"{kind}_reminder_last_sent_at"]
                summary["reminders_sent"] += 1
            if update.get("compliance_paused"):
                patch["compliance_paused"] = True
                patch["compliance_pause_reason"] = update.get("compliance_pause_reason", f"{kind} expired")
                summary["paused"] += 1
            # Merge nested patch into the blob.
            blob = {**blob, **nested_patch}
            patch[f"compliance_docs.{kind}"] = blob
        if patch:
            patch["compliance_swept_at"] = now
            await db.partner_engineers.update_one({"id": partner["id"]}, {"$set": patch})
    return summary


async def run_forever(interval_hours: int = 24) -> None:
    """Long-running task — invoked from main.py at startup."""
    while True:
        try:
            summary = await sweep_once()
            logger.info("Partner compliance sweep: %s", summary)
        except Exception as exc:  # noqa: BLE001
            logger.error("Partner compliance sweep crashed: %s", exc)
        await asyncio.sleep(interval_hours * 3600)
