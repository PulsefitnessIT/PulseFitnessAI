"""Master Admin — Login event timeline.

Surfaces the audit-log + trust-events stream as a clean chronological feed
so the security team can answer "is this account compromised?" in seconds.

The data already exists — the `audit_logs` collection captures successful
logins (action ``login``), failed logins (action ``login_failed`` if
emitted) and lockout events. This endpoint just joins + paginates.

Endpoints
---------
``GET /api/master-admin/login-events``
    Returns the most-recent login events. Filters: ``user_id``, ``email``,
    ``since`` (iso datetime), ``limit``.

The response intentionally omits passwords / token bodies. Each row
contains: ``at``, ``action``, ``email``, ``user_id``, ``ip``, ``details``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


@router.get("/master-admin/login-events")
async def list_login_events(
    user_id: str | None = None,
    email: str | None = None,
    since: str | None = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the most-recent login-related audit-log rows.

    Master-admin only. The query is bounded by `limit` (max 500) so it's
    safe to call from an unauthenticated dashboard widget.
    """
    _require_master(user)
    limit_i = max(1, min(int(limit or 100), 500))

    # Login-shaped audit actions. We deliberately keep this narrow so the
    # security view stays signal-rich.
    actions = ["login", "login_failed", "logout", "mfa_verify", "mfa_failed", "password_reset"]
    query: dict[str, Any] = {"action": {"$in": actions}}
    if user_id:
        query["user_id"] = user_id
    if email:
        query["user_email"] = email.lower().strip()
    if since:
        query["timestamp"] = {"$gte": since}

    cursor = db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit_i)
    rows = await cursor.to_list(length=limit_i)

    # Iter 216h210 — surface the structured failure reason on each row.
    # Details is stored as e.g. ``reason=wrong_password; ua=...``. The
    # frontend renders a colour-coded badge per reason.
    import re as _re
    _REASON_RE = _re.compile(r"reason=([a-z_]+)")
    for r in rows:
        d = r.get("details") or ""
        m = _REASON_RE.search(d) if isinstance(d, str) else None
        r["failure_reason"] = m.group(1) if m else None

    # Also pull recent brute-force trust events so the timeline reflects
    # high-severity attempts even if the audit action varies by version.
    trust_query: dict[str, Any] = {"type": {"$in": ["security.brute_force"]}}
    if since:
        trust_query["created_at"] = {"$gte": since}
    trust_cursor = db.trust_events.find(trust_query, {"_id": 0}).sort("created_at", -1).limit(limit_i)
    trust_rows = await trust_cursor.to_list(length=limit_i)

    successes = sum(1 for r in rows if r.get("action") == "login")
    failures = sum(1 for r in rows if r.get("action") in ("login_failed", "mfa_failed"))
    unique_users = len({r.get("user_email") for r in rows if r.get("user_email")})

    return {
        "events": rows,
        "trust_events": trust_rows,
        "stats": {
            "total": len(rows),
            "success": successes,
            "failure": failures,
            "unique_users": unique_users,
            "as_of": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/master-admin/login-events/summary")
async def login_events_summary(user: dict = Depends(get_current_user)) -> dict:
    """Return a compact 24h summary suitable for a dashboard tile."""
    _require_master(user)
    since = (datetime.now(timezone.utc).timestamp() - 86400)
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()

    success = await db.audit_logs.count_documents({
        "action": "login",
        "timestamp": {"$gte": since_iso},
    })
    failure = await db.audit_logs.count_documents({
        "action": {"$in": ["login_failed", "mfa_failed"]},
        "timestamp": {"$gte": since_iso},
    })
    brute_force = await db.trust_events.count_documents({
        "type": "security.brute_force",
        "created_at": {"$gte": since_iso},
    })
    return {
        "window_hours": 24,
        "success": success,
        "failure": failure,
        "brute_force_signals": brute_force,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
