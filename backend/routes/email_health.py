"""Master Admin — email pipeline health.

Powers the tiny green/amber/red "Email" pill in the top bar so we
catch issues like "Resend domain not verified" in 30 seconds, not
half a meeting day.

Reads ``email_send_events`` (populated by :func:`utils.email.send_email`)
and returns a short summary plus the last few attempts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db, RESEND_API_KEY, SENDER_EMAIL


router = APIRouter()
logger = logging.getLogger(__name__)

# Window for the rolling health summary.
WINDOW_HOURS = 24
SAMPLE_SIZE = 5


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


@router.get("/master-admin/email-health")
async def email_health(user: dict = Depends(get_current_user)) -> dict:
    """Return a tiny health summary for the email pipeline.

    Shape::

        {
            "status": "green" | "amber" | "red" | "unconfigured",
            "label":  human-readable summary,
            "sent":   int,            # last 24h
            "failed": int,            # last 24h
            "last_sent_at":   iso | null,
            "last_failed_at": iso | null,
            "last_error":     str | null,
            "sender":         SENDER_EMAIL,
            "domain_verified": bool | null,   # heuristic
            "recent": [
                {"to", "subject", "status", "error", "created_at"},
                ... (last 5)
            ]
        }
    """
    _require_master(user)

    if not RESEND_API_KEY:
        return {
            "status": "unconfigured",
            "label": "RESEND_API_KEY is not set in the environment",
            "sent": 0,
            "failed": 0,
            "last_sent_at": None,
            "last_failed_at": None,
            "last_error": None,
            "sender": SENDER_EMAIL or "",
            "domain_verified": None,
            "recent": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)

    # Aggregate counts in the rolling window.
    sent = await db.email_send_events.count_documents({
        "status": "sent", "created_at": {"$gte": cutoff},
    })
    failed = await db.email_send_events.count_documents({
        "status": {"$ne": "sent"}, "created_at": {"$gte": cutoff},
    })

    last_sent = await db.email_send_events.find_one(
        {"status": "sent"}, {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    last_failed = await db.email_send_events.find_one(
        {"status": {"$ne": "sent"}}, {"_id": 0, "created_at": 1, "error": 1},
        sort=[("created_at", -1)],
    )
    last_sent_at = _iso(last_sent.get("created_at")) if last_sent else None
    last_failed_at = _iso(last_failed.get("created_at")) if last_failed else None
    last_error = (last_failed or {}).get("error") or None

    # Recent feed for the dialog.
    recent_rows = await db.email_send_events.find(
        {}, {"_id": 0, "to": 1, "subject": 1, "status": 1, "error": 1, "created_at": 1},
        sort=[("created_at", -1)],
    ).to_list(SAMPLE_SIZE)
    for r in recent_rows:
        r["created_at"] = _iso(r.get("created_at"))

    # Heuristic on the most common failure: Resend's "domain not verified".
    domain_verified: bool | None
    if last_error and "domain is not verified" in last_error.lower():
        domain_verified = False
    elif sent > 0:
        domain_verified = True
    else:
        domain_verified = None

    status, label = _classify(sent, failed, last_error)

    return {
        "status": status,
        "label": label,
        "sent": sent,
        "failed": failed,
        "last_sent_at": last_sent_at,
        "last_failed_at": last_failed_at,
        "last_error": last_error,
        "sender": SENDER_EMAIL or "",
        "domain_verified": domain_verified,
        "recent": recent_rows,
    }


@router.get("/master-admin/emails")
async def list_outbound_emails(
    user: dict = Depends(get_current_user),
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
):
    """Iter 216h99 — full paginated feed for the Outbound emails panel.

    Filters:
      * ``status``: ``sent`` | ``failed`` (or unset for both)
      * ``search``: case-insensitive substring over ``to`` / ``subject``
                   / ``sender`` / ``error``
      * ``limit``: 1-500 (default 100)
    """
    _require_master(user)
    limit = max(1, min(int(limit or 100), 500))

    q: dict = {}
    if status == "sent":
        q["status"] = "sent"
    elif status == "failed":
        q["status"] = {"$ne": "sent"}

    if search:
        s = search.strip()
        q["$or"] = [
            {"to":      {"$regex": s, "$options": "i"}},
            {"subject": {"$regex": s, "$options": "i"}},
            {"sender":  {"$regex": s, "$options": "i"}},
            {"error":   {"$regex": s, "$options": "i"}},
        ]

    cursor = (
        db.email_send_events.find(
            q,
            {"_id": 0, "id": 1, "to": 1, "subject": 1, "sender": 1, "status": 1, "error": 1, "created_at": 1, "payload": 1, "retried_at": 1, "retry_event_id": 1},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    rows: list[dict] = []
    async for r in cursor:
        r["created_at"] = _iso(r.get("created_at"))
        # Iter 216h222 — front-end flag so the "Retry" button only
        # appears on rows we can actually replay (failed + payload
        # persisted + not already retried). Strip the payload from
        # the response so the UI list stays light.
        r["retryable"] = bool(
            r.get("status") and r.get("status") != "sent"
            and r.get("payload")
            and not r.get("retried_at")
            and r.get("id")
        )
        r.pop("payload", None)
        rows.append(r)

    # Cheap rolling counts (24h) so the panel header shows the same
    # values as the global health pill.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    sent_24h = await db.email_send_events.count_documents({
        "status": "sent", "created_at": {"$gte": cutoff},
    })
    failed_24h = await db.email_send_events.count_documents({
        "status": {"$ne": "sent"}, "created_at": {"$gte": cutoff},
    })
    total_all_time = await db.email_send_events.count_documents({})

    return {
        "sender": SENDER_EMAIL or "",
        "window_hours": WINDOW_HOURS,
        "sent_24h": sent_24h,
        "failed_24h": failed_24h,
        "total_all_time": total_all_time,
        "count": len(rows),
        "items": rows,
    }




@router.post("/master-admin/email-events/{event_id}/retry")
async def retry_failed_email(
    event_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h222 — replay a failed outbound email.

    Looks up the failed ``email_send_events`` row by id, re-sends the
    persisted Resend payload, and (on success) marks the row as
    ``retried_at`` so it can't be replayed in a loop. Returns the new
    event row + Resend message id.

    Errors:
      • 404 — event not found
      • 409 — event already retried, or already in ``sent`` state, or
              no payload was persisted (pre-h222 failures cannot be
              retried — surface that clearly so the operator knows to
              trigger the original flow again).
      • 502 — Resend rejected the retry; the new error is captured.
    """
    _require_master(user)

    if not RESEND_API_KEY:
        raise HTTPException(503, "RESEND_API_KEY missing — cannot send")

    event = await db.email_send_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Email event not found")
    if event.get("status") == "sent":
        raise HTTPException(409, "This email already delivered — nothing to retry")
    if event.get("retried_at"):
        raise HTTPException(409, "This email has already been retried")
    payload = event.get("payload") or {}
    if not payload.get("to") or not payload.get("html"):
        raise HTTPException(
            409,
            "No retry payload stored for this email (pre-216h222 failure). "
            "Trigger the original flow again instead.",
        )

    # Re-build the Resend params from the persisted payload. Note:
    # `html` is already wrapped with operator branding so we DON'T
    # call ``send_email()`` here (that would double-wrap).
    try:
        import resend as _resend
        _resend.api_key = RESEND_API_KEY
        params = {
            "from": payload.get("from"),
            "to": payload["to"] if isinstance(payload["to"], list) else [payload["to"]],
            "subject": payload.get("subject") or event.get("subject") or "(no subject)",
            "html": payload["html"],
        }
        if payload.get("reply_to"):
            params["reply_to"] = payload["reply_to"]
        if payload.get("attachments"):
            params["attachments"] = payload["attachments"]

        import asyncio as _asyncio
        from utils.email_rate_limiter import acquire as _rl_acquire
        await _rl_acquire()
        result = await _asyncio.to_thread(_resend.Emails.send, params)
        resend_id = result.get("id") if isinstance(result, dict) else None
    except Exception as exc:
        # Persist the new failure as its own event so the operator
        # sees the retry attempt in the panel.
        new_err = repr(exc)
        import uuid as _uuid
        new_event_id = str(_uuid.uuid4())
        try:
            await db.email_send_events.insert_one({
                "id": new_event_id,
                "to": (payload.get("to") or [event.get("to")])[0] if isinstance(payload.get("to"), list) else event.get("to"),
                "subject": params.get("subject"),
                "sender": payload.get("from") or SENDER_EMAIL or "",
                "status": "failed",
                "error": (new_err or "")[:500],
                "created_at": datetime.now(timezone.utc),
                "payload": payload,
                "retry_of": event_id,
            })
        except Exception:
            pass
        raise HTTPException(502, f"Retry rejected by Resend: {new_err[:200]}")

    # Mark the original event as retried + log the success.
    now = datetime.now(timezone.utc)
    import uuid as _uuid
    success_event_id = str(_uuid.uuid4())
    try:
        await db.email_send_events.insert_one({
            "id": success_event_id,
            "to": (payload.get("to") or [event.get("to")])[0] if isinstance(payload.get("to"), list) else event.get("to"),
            "subject": params.get("subject"),
            "sender": payload.get("from") or SENDER_EMAIL or "",
            "status": "sent",
            "error": "",
            "created_at": now,
            "retry_of": event_id,
            "resend_id": resend_id,
        })
        await db.email_send_events.update_one(
            {"id": event_id},
            {"$set": {"retried_at": now, "retry_event_id": success_event_id}},
        )
    except Exception:
        logger.exception("retry: failed to write success row (Resend already accepted, non-fatal)")

    return {
        "ok": True,
        "retry_event_id": success_event_id,
        "resend_id": resend_id,
        "original_event_id": event_id,
    }



def _iso(dt) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None


def _classify(sent: int, failed: int, last_error: str | None) -> tuple[str, str]:
    """Translate the rolling counts into status + plain-English label."""
    total = sent + failed
    if total == 0:
        return "amber", "No email activity in the last 24h"
    if failed == 0:
        return "green", f"All {sent} emails delivered in the last 24h"
    if sent == 0:
        # Total breakage — surface the actual reason.
        if last_error and "domain is not verified" in last_error.lower():
            return "red", "Resend domain not verified — verify it at resend.com/domains"
        return "red", f"All {failed} email attempts failed in the last 24h"
    # Mixed — degrade to amber.
    fail_pct = (failed / total) * 100
    return "amber", f"{sent} delivered, {failed} failed in the last 24h ({fail_pct:.0f}% failure)"


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_email_send_events_indexes() -> None:
    """30-day TTL on `email_send_events` so the collection stays small."""
    try:
        await db.email_send_events.create_index("created_at")
        await db.email_send_events.create_index("id", unique=False, sparse=True)
        await db.email_send_events.create_index(
            [("created_at", 1)],
            name="email_send_events_ttl",
            expireAfterSeconds=30 * 86400,
        )
    except Exception:
        logger.exception("ensure_email_send_events_indexes failed (non-fatal)")
