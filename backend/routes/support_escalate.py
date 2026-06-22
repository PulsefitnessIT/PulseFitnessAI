"""
Ask Pulse Fitness / Pulse Fitness — Human-escalation pipeline (P1-D).

Flow:
- User clicks "Contact human support" in the Ask sheet.
- UI POSTs /api/support/escalate with the session_id + optional reason.
- We:
    1. Pull the last 10 conversation turns
    2. Create a `support_cases` row (status=open)
    3. Resend an email to the correct human inbox:
         * Pulse Lite / Pulse Pro   → SUPPORT_ESCALATION_EMAIL_PULSE
         * Everyone else (Pulse Fitness)  → SUPPORT_ESCALATION_EMAIL_GYMAXIS
    4. Write an audit row so SOC 2 has a breadcrumb
- User also rates every assistant turn via POST /api/support/feedback
  (👍 / 👎 + optional comment). CSAT feeds the Master Admin rollup.

Master Admin endpoints:
- GET  /api/master-admin/support/cases            — list + filter
- GET  /api/master-admin/support/cases/{id}       — full transcript
- PATCH /api/master-admin/support/cases/{id}      — status / assignee / resolution
- GET  /api/master-admin/support/analytics        — volume, deflection, CSAT, top topics
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db, RESEND_API_KEY, SENDER_EMAIL
from utils.support_audit import write_support_audit

try:
    import resend  # type: ignore
except ImportError:  # pragma: no cover
    resend = None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["support-escalate"])
admin_router = APIRouter(prefix="/master-admin/support", tags=["support-admin"])


PULSE_EMAIL = os.environ.get("SUPPORT_ESCALATION_EMAIL_PULSE", "service.dept@pulsefitness.com")
GYMAXIS_EMAIL = os.environ.get("SUPPORT_ESCALATION_EMAIL_GYMAXIS", "service.dept@pulsefitness.com")


# =============================== models ======================================

class EscalateReq(BaseModel):
    session_id: str
    reason: Optional[str] = Field(default=None, max_length=1000)
    last_message: Optional[str] = Field(default=None, max_length=2000)


class FeedbackReq(BaseModel):
    session_id: str
    turn_id: Optional[str] = None
    rating: str = Field(..., pattern="^(up|down)$")
    comment: Optional[str] = Field(default=None, max_length=800)


class CasePatchReq(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(open|in_progress|resolved|closed)$")
    assigned_to: Optional[str] = None
    resolution: Optional[str] = Field(default=None, max_length=2000)


# =============================== helpers =====================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_ref(case_id: str) -> str:
    return f"ASK-{case_id[:8].upper()}"


def _is_pulse(account_type: str) -> bool:
    return account_type in ("pulse_pro", "lite")


def _pick_recipient(account_type: str) -> str:
    return PULSE_EMAIL if _is_pulse(account_type) else GYMAXIS_EMAIL


async def _load_org(org_id: Optional[str]) -> dict:
    if not org_id:
        return {}
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "account_type": 1})
    return org or {}


async def _last_turns(session_id: str, limit: int = 10) -> list[dict]:
    turns = await db.support_conversations.find(
        {"session_id": session_id}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return list(reversed(turns))


def _transcript_rows(turns: list[dict]) -> list[dict]:
    return [
        {
            "role": t.get("role", ""),
            "text": (t.get("text") or "")[:2000],
            "created_at": t.get("created_at", ""),
        }
        for t in turns
    ]


def _transcript_html(turns: list[dict]) -> str:
    blocks = []
    for t in turns:
        role = t.get("role", "user").capitalize()
        colour = "#0055FF" if role.lower() == "assistant" else "#111827"
        when = (t.get("created_at") or "")[:19].replace("T", " ")
        text = (t.get("text") or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        blocks.append(
            f'<div style="margin-bottom:10px"><div style="font-size:11px;color:#6b7280;'
            f'text-transform:uppercase;letter-spacing:0.04em;">'
            f'<b style="color:{colour}">{role}</b> · {when}</div>'
            f'<div style="font-size:14px;color:#111827;line-height:1.45">{text}</div></div>'
        )
    return "".join(blocks) or '<div style="color:#6b7280">No transcript captured.</div>'


def _build_escalation_email(case_ref: str, user: dict, org: dict,
                            turns: list[dict], reason: str, platform_name: str) -> dict:
    transcript = _transcript_html(turns)
    reason_html = (reason or "").replace("<", "&lt;").replace(">", "&gt;") or "User clicked escalate."
    org_name = org.get("name", "Unknown organisation")
    subject = f"[{case_ref}] Human support requested — {org_name}"
    html = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;padding:20px">
      <h2 style="margin:0 0 6px 0;color:#0055FF">Ask {platform_name} — human escalation</h2>
      <p style="color:#6b7280;font-size:13px;margin:0 0 20px 0">Case reference: <b>{case_ref}</b></p>
      <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;padding:14px;margin-bottom:18px">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">Customer</div>
        <div style="font-size:14px;color:#111827"><b>{user.get('full_name') or user.get('email', '')}</b> · {user.get('email', '')}</div>
        <div style="font-size:13px;color:#6b7280;margin-top:2px">{org_name} ({org.get('account_type', 'unknown')})</div>
      </div>
      <div style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:8px;padding:14px;margin-bottom:18px">
        <div style="font-size:12px;color:#92400E;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">Why they escalated</div>
        <div style="font-size:14px;color:#78350F">{reason_html}</div>
      </div>
      <h3 style="margin:18px 0 10px 0;color:#111827;font-size:15px">Conversation transcript (last {len(turns)} turns)</h3>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:14px">{transcript}</div>
      <p style="color:#6b7280;font-size:11px;margin-top:20px">
        This email was sent automatically by {platform_name} when a user requested human support.
      </p>
    </div>
    """
    return {"subject": subject, "html": html}


async def _send_escalation_email(recipient: str, subject: str, html: str, reply_to: Optional[str]) -> bool:
    if not RESEND_API_KEY or not resend:
        logger.warning("Resend not configured — skipping escalation email")
        return False
    resend.api_key = RESEND_API_KEY
    payload = {
        "from": f"Ask Support <{SENDER_EMAIL or 'faults@service.pulsefitness.ai'}>",
        "to": [recipient],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        await asyncio.to_thread(resend.Emails.send, payload)
        return True
    except Exception as exc:  # pragma: no cover - resend network failures
        logger.warning(f"Escalation email dispatch failed: {exc}")
        return False


async def _persist_case(user: dict, org: dict, session_id: str, reason: str,
                        recipient: str, email_sent: bool, turns: list[dict]) -> dict:
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "ref": _case_ref(case_id),
        "session_id": session_id,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "user_name": user.get("full_name") or user.get("email"),
        "org_id": user.get("organization_id"),
        "org_name": org.get("name") or "",
        "account_type": org.get("account_type") or "",
        "reason": reason or "",
        "transcript": _transcript_rows(turns),
        "recipient_email": recipient,
        "email_sent": email_sent,
        "status": "open",
        "assigned_to": None,
        "resolution": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "closed_at": None,
    }
    await db.support_cases.insert_one(doc)
    doc.pop("_id", None)
    return doc


# =============================== endpoints ===================================

@router.post("/support/escalate")
async def escalate_to_human(req: EscalateReq, user: dict = Depends(get_current_user)) -> dict:
    """Create a support case + email the human ops inbox."""
    org = await _load_org(user.get("organization_id"))
    account_type = org.get("account_type") or ""
    platform_name = "Pulse Fitness" if _is_pulse(account_type) else "Pulse Fitness"
    recipient = _pick_recipient(account_type)
    turns = await _last_turns(req.session_id)
    reason = (req.reason or req.last_message or "").strip()
    email_payload = _build_escalation_email(
        case_ref=_case_ref(req.session_id),  # preview ref; real one applied below
        user=user, org=org, turns=turns,
        reason=reason, platform_name=platform_name,
    )
    email_sent = await _send_escalation_email(
        recipient, email_payload["subject"], email_payload["html"], user.get("email"),
    )
    case = await _persist_case(user, org, req.session_id, reason, recipient, email_sent, turns)

    await write_support_audit(
        session_id=req.session_id, user_id=user["id"], org_id=user.get("organization_id"),
        prompt_text=f"escalate:{reason[:200]}", response_text=f"case:{case['ref']}",
        model="escalation", latency_ms=0,
        tool_calls_executed=["escalate_human"], classifier_label="safe",
        response_confidence="high", needs_human=True,
    )

    return {
        "success": True,
        "case_id": case["id"],
        "case_ref": case["ref"],
        "email_sent": email_sent,
        "recipient": recipient,
        "platform_name": platform_name,
    }


@router.post("/support/feedback")
async def submit_feedback(req: FeedbackReq, user: dict = Depends(get_current_user)) -> dict:
    """Record a CSAT rating for an assistant turn."""
    doc = {
        "id": str(uuid.uuid4()),
        "session_id": req.session_id,
        "turn_id": req.turn_id,
        "user_id": user.get("id"),
        "org_id": user.get("organization_id"),
        "rating": req.rating,
        "comment": (req.comment or "").strip() or None,
        "created_at": _now_iso(),
    }
    await db.support_feedback.insert_one(doc)
    return {"success": True, "id": doc["id"]}


# =============================== admin =======================================

def _require_master(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin access required")


@admin_router.get("/cases")
async def list_cases(
    status: Optional[str] = Query(None),
    org_id: Optional[str] = Query(None),
    limit: int = Query(200, le=2000),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master(user)
    query: dict = {}
    if status:
        query["status"] = status
    if org_id:
        query["org_id"] = org_id
    rows = await db.support_cases.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"cases": rows, "total": len(rows)}


@admin_router.get("/cases/{case_id}")
async def get_case(case_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_master(user)
    case = await db.support_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@admin_router.patch("/cases/{case_id}")
async def patch_case(case_id: str, req: CasePatchReq, user: dict = Depends(get_current_user)) -> dict:
    _require_master(user)
    updates: dict = {"updated_at": _now_iso()}
    if req.status is not None:
        updates["status"] = req.status
        if req.status in ("resolved", "closed"):
            updates["closed_at"] = _now_iso()
    if req.assigned_to is not None:
        updates["assigned_to"] = req.assigned_to
    if req.resolution is not None:
        updates["resolution"] = req.resolution
    result = await db.support_cases.update_one({"id": case_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = await db.support_cases.find_one({"id": case_id}, {"_id": 0})
    return doc or {}


# -------- analytics rollup --------

def _bucket_cutoffs(days: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    return since, now.isoformat()


async def _count_volume(since: str) -> dict:
    total = await db.support_audit.count_documents({"created_at": {"$gte": since}})
    blocked = await db.support_audit.count_documents({"created_at": {"$gte": since}, "blocked": True})
    escalated = await db.support_cases.count_documents({"created_at": {"$gte": since}})
    return {"asks": total, "blocked": blocked, "escalated": escalated}


async def _avg_latency(since: str) -> int:
    cursor = db.support_audit.find(
        {"created_at": {"$gte": since}, "blocked": {"$ne": True}},
        {"_id": 0, "latency_ms": 1},
    ).limit(5000)
    total = 0
    count = 0
    async for row in cursor:
        latency = int(row.get("latency_ms") or 0)
        if latency > 0:
            total += latency
            count += 1
    return int(total / count) if count else 0


async def _csat_summary(since: str) -> dict:
    up = await db.support_feedback.count_documents({"created_at": {"$gte": since}, "rating": "up"})
    down = await db.support_feedback.count_documents({"created_at": {"$gte": since}, "rating": "down"})
    total = up + down
    return {
        "thumbs_up": up,
        "thumbs_down": down,
        "total": total,
        "score_pct": round(up * 100 / total, 1) if total else None,
    }


async def _top_classifier_labels(since: str) -> list[dict]:
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$classifier_label", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6},
    ]
    out = []
    async for row in db.support_audit.aggregate(pipeline):
        out.append({"label": row["_id"] or "safe", "count": row["count"]})
    return out


async def _cases_by_status() -> dict:
    buckets = {"open": 0, "in_progress": 0, "resolved": 0, "closed": 0}
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    async for row in db.support_cases.aggregate(pipeline):
        status = row["_id"] or "open"
        if status in buckets:
            buckets[status] = row["count"]
    return buckets


def _compute_deflection(volume: dict) -> float:
    asks = volume.get("asks") or 0
    escalated = volume.get("escalated") or 0
    if not asks:
        return 0.0
    return round((asks - escalated) * 100 / asks, 1)


@admin_router.get("/analytics")
async def analytics_summary(days: int = Query(30, ge=1, le=180), user: dict = Depends(get_current_user)) -> dict:
    _require_master(user)
    since, until = _bucket_cutoffs(days)
    volume = await _count_volume(since)
    avg_ms = await _avg_latency(since)
    csat = await _csat_summary(since)
    labels = await _top_classifier_labels(since)
    cases = await _cases_by_status()
    return {
        "window_days": days,
        "since": since,
        "until": until,
        "volume": volume,
        "deflection_pct": _compute_deflection(volume),
        "avg_latency_ms": avg_ms,
        "csat": csat,
        "classifier_breakdown": labels,
        "cases_by_status": cases,
    }


# -------- nightly rollup --------

async def rollup_daily_support_analytics() -> dict:
    """Run once per day by the sicon_poller loop. Stores a dated snapshot
    in `support_analytics_daily` so we can render trend charts."""
    since, _ = _bucket_cutoffs(1)
    volume = await _count_volume(since)
    csat = await _csat_summary(since)
    avg_ms = await _avg_latency(since)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot = {
        "date": today,
        "asks": volume["asks"],
        "blocked": volume["blocked"],
        "escalated": volume["escalated"],
        "deflection_pct": _compute_deflection(volume),
        "avg_latency_ms": avg_ms,
        "csat_up": csat["thumbs_up"],
        "csat_down": csat["thumbs_down"],
        "csat_score_pct": csat["score_pct"],
        "created_at": _now_iso(),
    }
    await db.support_analytics_daily.update_one(
        {"date": today}, {"$set": snapshot}, upsert=True,
    )
    return snapshot


async def ensure_support_escalate_indexes() -> None:
    try:
        await db.support_cases.create_index([("org_id", 1), ("created_at", -1)])
        await db.support_cases.create_index([("status", 1)])
        await db.support_feedback.create_index([("session_id", 1), ("created_at", -1)])
        await db.support_feedback.create_index([("org_id", 1), ("rating", 1)])
        await db.support_analytics_daily.create_index([("date", 1)], unique=True)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"support escalate index creation failed: {exc}")
