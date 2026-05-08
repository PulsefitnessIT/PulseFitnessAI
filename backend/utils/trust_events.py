"""
Trust Backbone — event publisher & query helpers.

A single stream of `trust_events` that both the internal admin Trust Dashboard
and (eventually) the customer-facing AI Support platform read from.

Design rules:
- Publishing is fire-and-forget and MUST NEVER raise in caller code.
- Events default `visible_to=["master_admin"]`; scope to the org only when the
  customer should see a safe translation.
- De-duplication key: callers pass `dedupe_key` (e.g. "sicon.queue.backlog:<org>")
  and we upsert an existing `open` event for that key rather than spamming.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.database import db

logger = logging.getLogger(__name__)

SEVERITIES = ("info", "low", "med", "high", "critical")
STATES = ("open", "acknowledged", "resolved", "auto_resolved")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_trust_event(
    *,
    type: str,
    severity: str = "info",
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    payload: Optional[dict] = None,
    summary: Optional[str] = None,
    customer_safe_message: Optional[str] = None,
    visible_to: Optional[list[str]] = None,
    dedupe_key: Optional[str] = None,
    auto_actions: Optional[list[str]] = None,
) -> Optional[str]:
    """Publish a trust event. Returns the event id (or None on failure).

    If a `dedupe_key` is supplied and an open event with that key exists, the
    existing event is updated (payload merged, `last_seen_at` refreshed,
    `occurrences` incremented) and its id returned. Prevents storm amplification.
    """
    if severity not in SEVERITIES:
        severity = "info"
    try:
        if dedupe_key:
            existing_id = await _touch_existing_event(dedupe_key, severity, payload or {})
            if existing_id:
                return existing_id
        return await _insert_new_event(
            type, severity, org_id, user_id, payload, summary,
            customer_safe_message, visible_to, dedupe_key, auto_actions,
        )
    except Exception as exc:  # fire-and-forget — never break the caller
        logger.warning(f"trust_events publish failed ({type}): {exc}")
        return None


async def _touch_existing_event(dedupe_key: str, severity: str, payload: dict) -> Optional[str]:
    existing = await db.trust_events.find_one(
        {"dedupe_key": dedupe_key, "state": {"$in": ["open", "acknowledged"]}},
        {"_id": 0, "id": 1},
    )
    if not existing:
        return None
    await db.trust_events.update_one(
        {"id": existing["id"]},
        {
            "$set": {"last_seen_at": _now_iso(), "payload": payload, "severity": severity},
            "$inc": {"occurrences": 1},
        },
    )
    return existing["id"]


async def _insert_new_event(
    type_: str, severity: str, org_id: Optional[str], user_id: Optional[str],
    payload: Optional[dict], summary: Optional[str], customer_safe_message: Optional[str],
    visible_to: Optional[list[str]], dedupe_key: Optional[str], auto_actions: Optional[list[str]],
) -> str:
    ev_id = str(uuid.uuid4())
    doc = {
        "id": ev_id,
        "type": type_,
        "severity": severity,
        "org_id": org_id,
        "user_id": user_id,
        "payload": payload or {},
        "summary": summary or "",
        "customer_safe_message": customer_safe_message or "",
        "state": "open",
        "auto_actions": auto_actions or [],
        "visible_to": visible_to or ["master_admin"],
        "dedupe_key": dedupe_key,
        "occurrences": 1,
        "created_at": _now_iso(),
        "last_seen_at": _now_iso(),
        "resolved_at": None,
        "acknowledged_at": None,
        "acknowledged_by": None,
    }
    await db.trust_events.insert_one(doc)
    return ev_id


async def auto_resolve_trust_event(dedupe_key: str, note: str = "") -> None:
    """Mark any open event matching dedupe_key as auto_resolved. Used by
    self-healing playbooks to clear the condition once it clears."""
    try:
        await db.trust_events.update_many(
            {"dedupe_key": dedupe_key, "state": {"$in": ["open", "acknowledged"]}},
            {"$set": {
                "state": "auto_resolved",
                "resolved_at": _now_iso(),
                "resolution_note": note,
            }},
        )
    except Exception as exc:
        logger.warning(f"trust_events auto_resolve failed ({dedupe_key}): {exc}")


async def sweep_old_trust_events(retention_days: int = 365) -> int:
    """Delete trust_events older than retention_days. Returns count."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    try:
        res = await db.trust_events.delete_many({"created_at": {"$lt": cutoff}})
        return res.deleted_count or 0
    except Exception as exc:
        logger.warning(f"trust_events sweep failed: {exc}")
        return 0


async def ensure_trust_event_indexes() -> None:
    """Create indexes for the trust_events collection. Safe to re-run."""
    try:
        await db.trust_events.create_index([("state", 1), ("created_at", -1)])
        await db.trust_events.create_index([("severity", 1), ("state", 1)])
        await db.trust_events.create_index([("type", 1), ("created_at", -1)])
        await db.trust_events.create_index([("org_id", 1), ("state", 1), ("created_at", -1)])
        await db.trust_events.create_index([("dedupe_key", 1), ("state", 1)])
    except Exception as exc:
        logger.warning(f"trust_events index creation failed: {exc}")
