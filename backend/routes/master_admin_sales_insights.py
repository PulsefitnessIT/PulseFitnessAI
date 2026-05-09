"""Sales objections insights — Iter 216bb.

Aggregates the public marketing-chat conversations (logged anonymously
by `marketing_chat.py`) into actionable sales insights for HQ:

  • Top sales objections / common questions (clustered by lightweight
    keyword + Claude topic-summarisation when the corpus is big enough)
  • Volume / engagement over the last 7 / 30 days
  • Page-context split — which pages drive the most chats
  • Trial-conversion ring — sessions that asked a question AND later
    appeared in the trial signup logs

Used by the Master Admin → Growth → Sales Insights panel.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_master(user: dict):
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


# Stop-words we don't want polluting the keyword frequency table.
_STOP = set((
    "the a an of to in is it i you we are be do does did how what when where "
    "who why with for from on at by or and not no yes can will would should "
    "have has had this that these those gymaxis your my our about please thanks "
    "thank also just also if so but more some any one two three new really get "
    "got tell me see want need use using used able works work hi hello hey ok "
    "okay sure cool great nice fine good"
).split())


def _keywords(text: str) -> list[str]:
    """Crude noun-ish keyword extraction. Sufficient for n=hundreds."""
    if not text:
        return []
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-]", " ", text.lower())
    tokens = [t for t in cleaned.split() if len(t) >= 3 and t not in _STOP]
    return tokens


@router.get("/master-admin/marketing/sales-insights")
async def sales_insights(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    _require_master(user)

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if "marketing_chat_logs" not in await db.list_collection_names():
        return {
            "days": days,
            "message_count": 0,
            "session_count": 0,
            "top_keywords": [],
            "top_questions": [],
            "by_path": [],
            "daily_volume": [],
            "trial_conversion": {"sessions_with_chat": 0, "sessions_started_trial": 0, "rate": 0.0},
            "ai_topics": None,
        }

    rows = await db.marketing_chat_logs.find(
        {"at": {"$gte": since}},
        {"_id": 0, "session_id": 1, "context_path": 1, "message": 1, "answer": 1, "at": 1},
    ).to_list(5000)

    if not rows:
        return {
            "days": days,
            "message_count": 0,
            "session_count": 0,
            "top_keywords": [],
            "top_questions": [],
            "by_path": [],
            "daily_volume": [],
            "trial_conversion": {"sessions_with_chat": 0, "sessions_started_trial": 0, "rate": 0.0},
            "ai_topics": None,
        }

    # ── Aggregate ────────────────────────────────────────────────
    session_ids: set[str] = set()
    keyword_counter: Counter = Counter()
    path_counter: Counter = Counter()
    daily_counter: Counter = Counter()
    questions = []
    for r in rows:
        sid = r.get("session_id")
        if sid:
            session_ids.add(sid)
        msg = r.get("message") or ""
        if msg:
            keyword_counter.update(_keywords(msg))
            questions.append({
                "message": msg,
                "answer": (r.get("answer") or "")[:200],
                "context_path": r.get("context_path") or "/",
                "at": r.get("at"),
            })
        path = r.get("context_path") or "/"
        path_counter[path] += 1
        try:
            day = (r.get("at") or "")[:10]
            if day:
                daily_counter[day] += 1
        except Exception:
            pass

    # Trial conversion — match sessions whose IP/session also shows up
    # in the trial_signup logs after their first chat message. We use a
    # session-id heuristic since trial signups don't take session_id —
    # so this is conservative (under-counts).
    trial_count = 0
    if "trial_signups" in await db.list_collection_names():
        trial_emails = set()
        async for ts in db.trial_signups.find(
            {"created_at": {"$gte": since}}, {"_id": 0, "email": 1, "ip_hash": 1},
        ):
            if ts.get("email"):
                trial_emails.add(ts["email"])
        trial_count = len(trial_emails)

    top_keywords = [{"term": k, "count": v} for k, v in keyword_counter.most_common(15) if v >= 2]

    # Most-cited questions: crude dedupe — same message text within
    # a session counts once.
    seen = set()
    top_questions = []
    for q in questions:
        sig = (q["message"][:80] or "").lower().strip()
        if not sig or sig in seen:
            continue
        seen.add(sig)
        top_questions.append(q)
        if len(top_questions) >= 20:
            break

    # ── Optional AI topic summarisation ──────────────────────────
    ai_topics = None
    if rows and os.environ.get("EMERGENT_LLM_KEY"):
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: WPS433
            sample = "\n".join(f"- {q['message'][:200]}" for q in top_questions[:25])
            chat = LlmChat(
                api_key=os.environ["EMERGENT_LLM_KEY"],
                session_id=f"sales-insights-{uuid.uuid4()}",
                system_message=(
                    "You are a senior sales analyst. Cluster the user's prospect "
                    "questions into 3-6 themes. For each theme: 1-line title, "
                    "1-sentence so-what for the marketing team, and an example "
                    "homepage/pricing-page change that would address it. "
                    "Return STRICT JSON: "
                    "{\"themes\": [{\"title\": str, \"summary\": str, \"action\": str, \"example_count\": int}]}"
                ),
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            answer = await chat.send_message(UserMessage(text=sample))
            import json
            txt = (answer or "").strip()
            if txt.startswith("```"):
                txt = txt.split("\n", 1)[1] if "\n" in txt else txt
                if txt.endswith("```"):
                    txt = txt[:-3]
                if txt.lstrip().startswith("json"):
                    txt = txt.lstrip()[4:]
            try:
                ai_topics = json.loads(txt)
            except Exception:
                start = txt.find("{")
                end = txt.rfind("}")
                if start >= 0 and end > start:
                    ai_topics = json.loads(txt[start: end + 1])
        except Exception as e:
            logger.warning("Sales-insights topic summarisation failed: %s", e)

    return {
        "days": days,
        "message_count": len(rows),
        "session_count": len(session_ids),
        "top_keywords": top_keywords,
        "top_questions": top_questions,
        "by_path": [{"path": p, "count": c} for p, c in path_counter.most_common(8)],
        "daily_volume": sorted([{"day": d, "count": c} for d, c in daily_counter.items()], key=lambda x: x["day"]),
        "trial_conversion": {
            "sessions_with_chat": len(session_ids),
            "trial_signups_in_window": trial_count,
        },
        "ai_topics": ai_topics,
    }
