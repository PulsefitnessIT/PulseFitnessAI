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
from utils.security_plus import safe_regex

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
        "status": {"$ne": "sent"}, "created_at": {"$gte": cutoff}, "retry_of": {"$exists": False},
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
        {}, {"_id": 0, "id": 1, "to": 1, "subject": 1, "status": 1, "error": 1, "created_at": 1, "payload": 1, "retried_at": 1},
        sort=[("created_at", -1)],
    ).to_list(SAMPLE_SIZE)
    for r in recent_rows:
        r["created_at"] = _iso(r.get("created_at"))
        # Iter 216h222 — surface a retry button only on rows we can
        # actually replay (post-h222 failure + payload stored + not
        # yet retried). Strip the payload itself before returning.
        r["retryable"] = bool(
            r.get("status") and r.get("status") != "sent"
            and (r.get("payload") or {}).get("html")
            and not r.get("retried_at")
            and r.get("id")
        )
        r.pop("payload", None)
        r.pop("retried_at", None)

    # Heuristic on the most common failure: Resend's "domain not verified".
    domain_verified: bool | None
    if last_error and "domain is not verified" in last_error.lower():
        domain_verified = False
    elif sent > 0:
        domain_verified = True
    else:
        domain_verified = None

    status, label = _classify(sent, failed, last_error)

    # Iter 216h258 — aggregate distinct senders seen in the rolling
    # window so the modal can show ALL outgoing addresses (support /
    # billing / service / etc.), not just the configured default. The
    # default `SENDER_EMAIL` is always included even if it hasn't sent
    # anything yet so the operator can confirm it's wired up.
    sender_pipeline = [
        {"$match": {
            "created_at": {"$gte": cutoff},
            "sender": {"$exists": True, "$nin": [None, ""]},
        }},
        {"$group": {
            "_id": "$sender",
            "sent":   {"$sum": {"$cond": [{"$eq": ["$status", "sent"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "sent"]}, 0, 1]}},
            "last_at": {"$max": "$created_at"},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": 25},
    ]
    sender_rows = await db.email_send_events.aggregate(sender_pipeline).to_list(25)
    senders: list[dict] = []
    seen_default = False
    for r in sender_rows:
        addr = (r.get("_id") or "").strip()
        if not addr:
            continue
        if SENDER_EMAIL and addr.lower() == SENDER_EMAIL.lower():
            seen_default = True
        senders.append({
            "address": addr,
            "sent":   int(r.get("sent")   or 0),
            "failed": int(r.get("failed") or 0),
            "last_at": _iso(r.get("last_at")),
            "is_default": bool(SENDER_EMAIL and addr.lower() == SENDER_EMAIL.lower()),
        })
    if SENDER_EMAIL and not seen_default:
        senders.insert(0, {
            "address": SENDER_EMAIL,
            "sent": 0, "failed": 0, "last_at": None, "is_default": True,
        })

    return {
        "status": status,
        "label": label,
        "sent": sent,
        "failed": failed,
        "last_sent_at": last_sent_at,
        "last_failed_at": last_failed_at,
        "last_error": last_error,
        "sender": SENDER_EMAIL or "",
        # Iter 216h258 — `senders` is the new full list. `sender`
        # remains for backward compatibility (older FE bundles still
        # display only the default).
        "senders": senders,
        "domain_verified": domain_verified,
        "recent": recent_rows,
        "retryable_count": await db.email_send_events.count_documents(
            _retryable_query(datetime.now(timezone.utc) - timedelta(days=RETRY_WINDOW_DAYS))),
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
            {"to":      safe_regex(s)},
            {"subject": safe_regex(s)},
            {"sender":  safe_regex(s)},
            {"error":   safe_regex(s)},
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
            and (r.get("payload") or {}).get("html")
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
        "status": {"$ne": "sent"}, "created_at": {"$gte": cutoff}, "retry_of": {"$exists": False},
    })
    total_all_time = await db.email_send_events.count_documents({})

    return {
        "sender": SENDER_EMAIL or "",
        "window_hours": WINDOW_HOURS,
        "sent_24h": sent_24h,
        "retryable_count": await db.email_send_events.count_documents(_retryable_query(datetime.now(timezone.utc) - timedelta(days=RETRY_WINDOW_DAYS))),
        "failed_24h": failed_24h,
        "total_all_time": total_all_time,
        "count": len(rows),
        "items": rows,
    }




RETRY_WINDOW_DAYS = 7


def _retryable_query(since: datetime) -> dict:
    return {"status": {"$ne": "sent"}, "payload.html": {"$exists": True},
            "retried_at": {"$exists": False}, "created_at": {"$gte": since}}


def _repair_from(sender: str) -> str:
    """Swap an unverified bare pulsefitness.com sender for the verified MOD subdomain."""
    from utils.email import _bare_addr
    bare = _bare_addr(sender or "")
    local, _, domain = bare.partition("@")
    if domain.lower() == "pulsefitness.com":
        return (sender or "").replace(bare, f"{local}@modservice.pulsefitness.com")
    return sender or SENDER_EMAIL


async def _replay_event(event: dict) -> dict:
    """Re-send a failed event's stored payload. Marks the original as retried
    (success or not) so only the newest attempt stays retryable."""
    import asyncio as _asyncio
    import uuid as _uuid
    import resend as _resend
    from utils.email import _bare_addr, _CATEGORY_SENDER_DEFAULT
    from utils.email_rate_limiter import acquire as _rl_acquire

    payload = dict(event.get("payload") or {})
    payload["from"] = _repair_from(payload.get("from"))
    to = payload["to"] if isinstance(payload["to"], list) else [payload["to"]]
    params = {"from": payload["from"], "to": to,
              "subject": payload.get("subject") or event.get("subject") or "(no subject)",
              "html": payload["html"]}
    if payload.get("reply_to"):
        params["reply_to"] = payload["reply_to"]
    if payload.get("attachments"):
        params["attachments"] = payload["attachments"]
    _resend.api_key = RESEND_API_KEY
    now = datetime.now(timezone.utc)
    new_id = str(_uuid.uuid4())
    row = {"id": new_id, "to": to[0], "subject": params["subject"], "sender": params["from"],
           "created_at": now, "retry_of": event["id"]}
    try:
        await _rl_acquire()
        try:
            result = await _asyncio.to_thread(_resend.Emails.send, params)
        except Exception as first:
            fallback = _bare_addr(_CATEGORY_SENDER_DEFAULT["service"])
            if "not verified" not in str(first).lower() or _bare_addr(params["from"]) == fallback:
                raise
            display = params["from"].split("<")[0].strip() or "Pulse Fitness"
            params["reply_to"] = params.get("reply_to") or _bare_addr(params["from"])
            params["from"] = row["sender"] = f"{display} <{fallback}>"
            result = await _asyncio.to_thread(_resend.Emails.send, params)
        resend_id = result.get("id") if isinstance(result, dict) else None
        await db.email_send_events.insert_one({**row, "status": "sent", "error": "", "resend_id": resend_id})
        ok, err = True, None
    except Exception as exc:
        err = repr(exc)[:500]
        await db.email_send_events.insert_one({**row, "status": "failed", "error": err, "payload": payload})
        ok, resend_id = False, None
    await db.email_send_events.update_one(
        {"id": event["id"]}, {"$set": {"retried_at": now, "retry_event_id": new_id}})
    return {"ok": ok, "error": err, "resend_id": resend_id, "retry_event_id": new_id}


@router.post("/master-admin/email-events/retry-failed")
async def retry_all_failed_emails(user: dict = Depends(get_current_user)) -> dict:
    """One-tap resend of every failed email from the last RETRY_WINDOW_DAYS."""
    _require_master(user)
    if not RESEND_API_KEY:
        raise HTTPException(503, "RESEND_API_KEY missing — cannot send")
    since = datetime.now(timezone.utc) - timedelta(days=RETRY_WINDOW_DAYS)
    events = await db.email_send_events.find(_retryable_query(since), {"_id": 0}).sort("created_at", -1).to_list(60)
    sent, failed, errors = 0, 0, []
    for ev in events:
        r = await _replay_event(ev)
        if r["ok"]:
            sent += 1
        else:
            failed += 1
            errors.append({"to": ev.get("to"), "subject": ev.get("subject"), "error": r["error"]})
    return {"ok": failed == 0, "attempted": len(events), "sent": sent, "failed": failed, "errors": errors[:10]}


@router.post("/master-admin/email-events/{event_id}/retry")
async def retry_failed_email(event_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Replay a single failed outbound email (404 / 409 / 422 on error)."""
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
        raise HTTPException(409, "No retry payload stored for this email. Trigger the original flow again instead.")
    r = await _replay_event(event)
    if not r["ok"]:
        raise HTTPException(422, f"Resend rejected it again: {(r['error'] or '')[:200]}")
    return {"ok": True, "retry_event_id": r["retry_event_id"], "resend_id": r["resend_id"],
            "original_event_id": event_id}



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
    from utils.mongo_indexes import ensure_ttl_index
    await ensure_ttl_index(db.email_send_events, "created_at", "email_send_events_ttl", 30 * 86400)
    try:
        await db.email_send_events.create_index("id", unique=False, sparse=True)
    except Exception:
        logger.warning("email_send_events id index setup failed (non-fatal)")
