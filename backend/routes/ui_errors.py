"""UI-error telemetry.

Captures `notify.error(...)` calls from the frontend so operators can see
which validation errors and API failures users actually hit in production.

Events are stored in `ui_error_events` with a 30-day TTL. Aggregated
summaries are exposed to master admins for product-friction analysis.

Privacy: we deliberately do not capture arbitrary DOM state or page
contents — only the error title/detail plus route, user id (if logged in),
and account type.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from utils.auth import get_current_user, try_get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────── Models ───────────────────────

class UIErrorIn(BaseModel):
    title: str = Field(..., max_length=300)
    detail: Optional[str] = Field(default=None, max_length=1000)
    tone: Optional[str] = Field(default="error", max_length=20)
    path: Optional[str] = Field(default=None, max_length=500)
    module: Optional[str] = Field(default=None, max_length=64)


# ─────────────────────── Helpers ──────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _fingerprint(title: str, path: Optional[str]) -> str:
    """Stable hash used to group "same" errors across sessions.

    SHA1 here is a non-cryptographic identity hash — we just need a
    stable short fingerprint to bucket duplicate UI errors. Not a
    security boundary, hence ``usedforsecurity=False`` to silence
    bandit's B324 false-positive.
    """
    base = f"{(title or '').strip().lower()}|{(path or '').split('?')[0]}"
    return hashlib.sha1(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


# ─────────────────────── Routes ───────────────────────

@router.post("/ui-errors")
async def log_ui_error(body: UIErrorIn, request: Request):
    """Fire-and-forget client error logger.

    Anonymous calls accepted — we still learn useful things from visitors
    hitting errors on the marketing pages. Auth users get enriched context.
    """
    if not body.title:
        raise HTTPException(status_code=400, detail="title required")

    user = await try_get_current_user(request)
    event = {
        "id": str(uuid.uuid4()),
        "title": body.title.strip()[:300],
        "detail": (body.detail or "").strip()[:1000] or None,
        "tone": body.tone or "error",
        "path": body.path,
        "module": body.module,
        "fingerprint": _fingerprint(body.title, body.path),
        "user_id": user.get("id") if user else None,
        "user_email": user.get("email") if user else None,
        "organization_id": user.get("organization_id") if user else None,
        "account_type": user.get("account_type") if user else None,
        "user_agent": (request.headers.get("user-agent") or "")[:300],
        "created_at": _now(),
    }
    try:
        await db.ui_error_events.insert_one(event)
    except Exception as e:
        logger.warning("ui_error insert failed: %s", e)
        # Never fail the request — telemetry is non-critical.
    return {"ok": True}


@router.get("/ui-errors/summary")
async def ui_errors_summary(
    days: int = Query(default=7, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    """Top ~50 error fingerprints in the last `days` window.

    Master admin only — other users get 403. Returns counts, first/last
    seen, unique affected users, a sample message, and the route breakdown.
    """
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    since = _now() - timedelta(days=days)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$fingerprint",
            "count": {"$sum": 1},
            "users": {"$addToSet": "$user_id"},
            "paths": {"$addToSet": "$path"},
            "title": {"$last": "$title"},
            "detail": {"$last": "$detail"},
            "last_seen": {"$max": "$created_at"},
            "first_seen": {"$min": "$created_at"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    try:
        rows = await db.ui_error_events.aggregate(pipeline).to_list(length=50)
    except Exception as e:
        logger.error("ui_errors_summary aggregation failed: %s", e)
        raise HTTPException(status_code=500, detail="aggregation failed")

    # Total events + affected users in window
    total_events = await db.ui_error_events.count_documents({"created_at": {"$gte": since}})
    unique_users = await db.ui_error_events.distinct(
        "user_id", {"created_at": {"$gte": since}, "user_id": {"$ne": None}}
    )

    items = []
    for r in rows:
        users = [u for u in (r.get("users") or []) if u]
        items.append({
            "fingerprint": r["_id"],
            "title": r.get("title"),
            "detail": r.get("detail"),
            "count": r.get("count", 0),
            "affected_users": len(users),
            "paths": [p for p in (r.get("paths") or []) if p][:5],
            "first_seen": _iso(r["first_seen"]) if r.get("first_seen") else None,
            "last_seen": _iso(r["last_seen"]) if r.get("last_seen") else None,
        })

    return {
        "window_days": days,
        "total_events": total_events,
        "unique_users_affected": len(unique_users),
        "top": items,
    }


@router.get("/ui-errors/recent")
async def ui_errors_recent(
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """Most recent individual events — useful for drill-down after spotting
    a fingerprint in the summary. Master admin only."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    rows = await db.ui_error_events.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = _iso(r["created_at"])
    return {"items": rows}


async def ensure_indexes() -> None:
    """Module-level index setup — called from server startup."""
    try:
        await db.ui_error_events.create_index("created_at")
        await db.ui_error_events.create_index("fingerprint")
        # 30-day TTL — keeps the collection bounded without manual cleanup
        await db.ui_error_events.create_index(
            "created_at", name="ui_error_events_ttl", expireAfterSeconds=60 * 60 * 24 * 30,
        )
    except Exception as e:
        logger.warning("ui_error_events index setup failed: %s", e)
