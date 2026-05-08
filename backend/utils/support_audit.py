"""
Support audit log — one row per /api/support/ask request.

Each row captures everything a SOC 2 / ISO 27001 auditor wants to see:
- Who (user_id, org_id)
- When (created_at)
- What shape of input (prompt_hash — SHA-256 of user_message, NOT the raw text)
- What shape of output (response_hash, token counts, latency)
- What tool calls (names only, not args — args can contain customer data)
- Whether any safety layers fired (classifier_label, pii_redactions, blocked)

We hash the prompt/response instead of storing them because:
- Raw conversations already live in `support_conversations` with 180-day TTL
- Audit needs to live 7 years (SOC 2) but should NOT duplicate PII
- Hashes let us prove a given transcript was / was not present without storing it
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from utils.database import db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_payload(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


async def write_support_audit(
    *,
    session_id: str,
    user_id: str,
    org_id: Optional[str],
    prompt_text: str,
    response_text: str,
    model: str,
    latency_ms: int,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    classifier_label: Optional[str] = None,
    classifier_confidence: Optional[str] = None,
    pii_redactions: Optional[dict] = None,
    blocked: bool = False,
    block_reason: Optional[str] = None,
    tool_calls_proposed: Optional[list[str]] = None,
    tool_calls_executed: Optional[list[str]] = None,
    needs_human: Optional[bool] = None,
    response_confidence: Optional[str] = None,
) -> None:
    """Fire-and-forget — never raise in the caller path."""
    try:
        await db.support_audit.insert_one({
            "session_id": session_id,
            "user_id": user_id,
            "org_id": org_id,
            "created_at": _now_iso(),
            "model": model,
            "latency_ms": int(latency_ms or 0),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "prompt_hash": hash_payload(prompt_text),
            "response_hash": hash_payload(response_text),
            "prompt_len": len(prompt_text or ""),
            "response_len": len(response_text or ""),
            "classifier_label": classifier_label or "safe",
            "classifier_confidence": classifier_confidence,
            "pii_redactions": pii_redactions or {},
            "blocked": bool(blocked),
            "block_reason": block_reason,
            "tool_calls_proposed": tool_calls_proposed or [],
            "tool_calls_executed": tool_calls_executed or [],
            "needs_human": needs_human,
            "response_confidence": response_confidence,
        })
    except Exception as exc:
        logger.warning(f"support_audit write failed: {exc}")


async def ensure_support_audit_indexes() -> None:
    try:
        await db.support_audit.create_index([("org_id", 1), ("created_at", -1)])
        await db.support_audit.create_index([("user_id", 1), ("created_at", -1)])
        await db.support_audit.create_index([("classifier_label", 1), ("created_at", -1)])
        await db.support_audit.create_index([("blocked", 1)])
    except Exception as exc:
        logger.warning(f"support_audit index creation failed: {exc}")
