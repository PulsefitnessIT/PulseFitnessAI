"""Real-time security alerting (security §32/§34).

When a CRITICAL or abuse security event lands, notify the Master Admin
immediately — an in-app toast (via the short-poll alerts feed) and a
best-effort email. Email is throttled per event-type so an enumeration burst
can't cause an inbox storm.

Fail-open: alerting must never break the request that triggered it.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from utils.database import db

logger = logging.getLogger("security")

# In-app alert feed collection (short-poll surface for the Master Admin UI).
_FEED = "security_alert_feed"
FEED_RETENTION_SECONDS = int(os.environ.get("SECURITY_ALERT_FEED_TTL", str(7 * 24 * 3600)))

# Event types that always page the Master Admin, regardless of severity.
ALERT_EVENT_TYPES = {
    "abuse_detected", "abuse_action_blocked",
    "bola_cross_tenant_denied", "cross_site_denied",
    "contract_send_blocked_unapproved", "step_up_failed",
}
EMAIL_THROTTLE_SECONDS = int(os.environ.get("SECURITY_ALERT_EMAIL_THROTTLE", "600"))
SECURITY_ALERT_EMAIL = os.environ.get("SECURITY_ALERT_EMAIL", "true").lower() in ("1", "true", "yes")


def is_alertable(event_type: str, severity: str) -> bool:
    return severity == "critical" or event_type in ALERT_EVENT_TYPES


async def _throttled(event_type: str) -> bool:
    """True if we already emailed for this event_type inside the window."""
    now = datetime.now(timezone.utc)
    key = f"secalert:{event_type}"
    doc = await db.security_alert_throttle.find_one({"id": key}, {"_id": 0, "ts": 1})
    if doc and doc.get("ts"):
        ts = doc["ts"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        if age < EMAIL_THROTTLE_SECONDS:
            return True
    await db.security_alert_throttle.update_one(
        {"id": key}, {"$set": {"id": key, "ts": now}}, upsert=True)
    return False


async def _queue_toast(event: dict) -> None:
    """Write a compact in-app alert row the Master Admin UI short-polls."""
    now = datetime.now(timezone.utc)
    etype = event.get("event_type") or ""
    sev = event.get("severity") or "warning"
    actor = event.get("actor_email") or event.get("actor_id") or "unknown actor"
    row = {
        "id": str(uuid.uuid4()),
        "event_id": event.get("id"),
        "event_type": etype,
        "severity": sev,
        "title": etype.replace("_", " ").title(),
        "actor": actor,
        "tenant_id": event.get("tenant_id"),
        "resource_type": event.get("resource_type"),
        "resource_id": event.get("resource_id"),
        "detail": event.get("detail"),
        "ip": event.get("ip"),
        "created_at": event.get("created_at") or now.isoformat(),
        "ts": now,
        "acknowledged": False,
    }
    await db[_FEED].insert_one(row)


async def dispatch_alert(event: dict) -> None:
    """Best-effort real-time alert for a critical/abuse security event."""
    try:
        etype = event.get("event_type") or ""
        sev = event.get("severity") or ""
        if not is_alertable(etype, sev):
            return

        # 1) In-app toast queue (primary channel — always, un-throttled).
        try:
            await _queue_toast(event)
        except Exception:
            logger.exception("security alert toast queue failed for %s", etype)

        # 2) Email the Master Admin (throttled, best-effort).
        if SECURITY_ALERT_EMAIL and not await _throttled(etype):
            try:
                from routes.master_admin import MASTER_ADMIN_EMAIL
                from utils.email import send_email
                actor = event.get("actor_email") or event.get("actor_id") or "unknown"
                subject = f"⚠️ PulseFitness security alert: {etype.replace('_', ' ')}"
                html = (
                    f"<h2>Security alert — {sev.upper()}</h2>"
                    f"<p><b>Event:</b> {etype}<br/>"
                    f"<b>Actor:</b> {actor}<br/>"
                    f"<b>Tenant:</b> {event.get('tenant_id') or '—'}<br/>"
                    f"<b>Resource:</b> {event.get('resource_type') or '—'} "
                    f"{event.get('resource_id') or ''}<br/>"
                    f"<b>Detail:</b> {event.get('detail') or '—'}<br/>"
                    f"<b>IP:</b> {event.get('ip') or '—'}<br/>"
                    f"<b>When:</b> {event.get('created_at') or ''}</p>"
                    f"<p>Open the Security Alert Centre in the Master Admin console for the full timeline.</p>"
                )
                await send_email(
                    to=MASTER_ADMIN_EMAIL, subject=subject, html=html,
                    kind="system_alert", category="security",
                )
            except Exception:
                logger.exception("security alert email failed for %s", etype)
    except Exception:
        logger.exception("dispatch_alert failed")


async def ensure_indexes() -> None:
    """Create feed indexes (TTL + poll query). Idempotent."""
    try:
        await db[_FEED].create_index([("ts", -1)])
        await db[_FEED].create_index("ts", expireAfterSeconds=FEED_RETENTION_SECONDS)
    except Exception:
        logger.exception("security_alert_feed index setup failed")


__all__ = ["dispatch_alert", "is_alertable", "ALERT_EVENT_TYPES", "ensure_indexes"]
