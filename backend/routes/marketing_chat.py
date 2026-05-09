"""Marketing-side AI chat — Iter 216ba.

Public, unauthenticated endpoint that powers the on-site chat widget.
Lets prospects ask "do you support X?", "is there a free trial?", "how
does pricing work?" without leaving the marketing site.

Design choices:
  • Stateless — each request is a single Q→A. We pass the help corpus
    (titles + descriptions) as ground truth so Claude can't fabricate
    feature claims.
  • Rate-limited per IP (10 messages / 5 min) to stop abuse.
  • Anonymous — no PII captured. If the user wants to talk to sales
    Claude points them at sales@gymaxisai.com or the trial signup.
  • Logged to db.marketing_chat_logs for funnel analysis (no PII).
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Header, HTTPException, Request
from pydantic import BaseModel, Field

from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

CLAUDE_MODEL = ("anthropic", "claude-sonnet-4-5-20250929")

# Rate-limit window
_RL_WINDOW_S = 300
_RL_MAX = 10
_recent: dict[str, list[float]] = {}


def _check_rate(ip: str):
    now = time.time()
    bucket = [t for t in _recent.get(ip, []) if now - t < _RL_WINDOW_S]
    if len(bucket) >= _RL_MAX:
        raise HTTPException(429, "Too many messages. Please wait a few minutes.")
    bucket.append(now)
    _recent[ip] = bucket


# ───────────────── Help corpus snapshot for grounding ──────────────


def _build_corpus_text() -> str:
    """Pull a slim text representation of the help corpus so Claude has
    ground truth about every published feature. Imported lazily so this
    file can be imported even when help_data is being edited."""
    try:
        from routes.help_data import GUIDES
    except Exception:
        return ""
    rows = []
    for g in GUIDES:
        title = g.get("title") or g.get("id") or ""
        desc = g.get("description") or ""
        rows.append(f"- {title} :: {desc}")
    return "\n".join(rows[:120])  # cap so prompt stays <8k tokens


_CORPUS_CACHE: dict = {"text": None, "at": 0}


def _corpus_text() -> str:
    """Cache the corpus for 5 minutes."""
    now = time.time()
    if _CORPUS_CACHE["text"] and now - _CORPUS_CACHE["at"] < 300:
        return _CORPUS_CACHE["text"]
    text = _build_corpus_text()
    _CORPUS_CACHE["text"] = text
    _CORPUS_CACHE["at"] = now
    return text


# ───────────────── Pydantic schemas ──────────────────────────────


class ChatBody(BaseModel):
    message: str = Field(..., max_length=2000)
    session_id: str | None = None
    context_path: str | None = None      # marketing page the user is on (for analytics)


# ───────────────── Endpoint ──────────────────────────────────────


@router.post("/marketing/chat")
async def marketing_chat(
    body: ChatBody,
    request: Request,
    x_forwarded_for: str | None = Header(default=None),
):
    if not body.message.strip():
        raise HTTPException(400, "Message is required")
    ip = (x_forwarded_for or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    _check_rate(ip)

    session_id = body.session_id or str(uuid.uuid4())

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        # Graceful fallback so the widget still functions without the key.
        return {
            "session_id": session_id,
            "answer": (
                "Thanks for the question — our AI assistant is offline right now. "
                "Email sales@gymaxisai.com and we'll reply within 24 hours, "
                "or click 'Start Free Trial' to try the platform yourself."
            ),
            "engine": "fallback",
        }

    system = (
        "You are GymAxis Sales — a friendly, concise, accurate AI sales assistant for "
        "GymAxis AI, an all-in-one operations platform for fitness operators. "
        "Answer in 2-4 sentences max. Always be honest. If the buyer asks about a feature "
        "that ISN'T in the corpus below, say so plainly and offer to email sales@gymaxisai.com.\n\n"
        "Pricing facts (verbatim): "
        "GymAxis Pro is £150/mo (all 4 modules + AI + integrations + 1 site). "
        "Additional sites are £50/mo each. Individual modules: Memberships £29/mo, CRM £49/mo, "
        "Marketing £49/mo, Operations £59/mo. 3-day free trial, all modules unlocked, no credit card.\n\n"
        "When the buyer is ready to act, recommend they click 'Start Free Trial' in the page. "
        "For procurement / DPA / security: point them at security@gymaxisai.com. "
        "Do NOT invent customer names, logos, or specific revenue figures.\n\n"
        "Help corpus (the source of truth on what's shipped today):\n"
        + _corpus_text()
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: WPS433
        chat = LlmChat(
            api_key=key,
            session_id=f"marketing-chat-{session_id}",
            system_message=system,
        ).with_model(*CLAUDE_MODEL)
        t0 = time.time()
        answer = await chat.send_message(UserMessage(text=body.message.strip()))
        latency_ms = int((time.time() - t0) * 1000)
        await db.marketing_chat_logs.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "ip_hash": str(hash(ip)),                              # no plain IP stored
            "context_path": body.context_path or "",
            "message": body.message.strip()[:500],
            "answer": (answer or "")[:1000],
            "latency_ms": latency_ms,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        return {"session_id": session_id, "answer": answer or "Sorry — I didn't catch that. Could you rephrase?", "engine": "claude-sonnet-4-5"}
    except Exception as e:
        logger.warning("Marketing chat failed: %s", e)
        return {
            "session_id": session_id,
            "answer": (
                "I'm having trouble answering that right now. Email sales@gymaxisai.com "
                "and we'll come back to you within 24 hours."
            ),
            "engine": "fallback",
        }
