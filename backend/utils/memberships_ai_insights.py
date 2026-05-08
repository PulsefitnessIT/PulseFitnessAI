"""GymAxis Memberships — AI insight helpers.

Thin wrappers around GPT-4o-mini (Emergent LLM Key) for:
  • Executive weekly/monthly brief
  • Per-member at-risk reasoning
"""
from __future__ import annotations

import json as json_mod
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_MSG = (
    "You are a fitness SaaS BI analyst. Write concise, action-oriented "
    "insight suitable for busy gym operators. British English. No filler."
)


async def _chat_vision(prompt: str, image_urls: list[str], max_tokens: int = 200) -> str:
    """Send a vision prompt to GPT-4o (not mini) via Emergent LLM key.
    Attaches one or more image URLs; returns raw text. Degrades gracefully."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
        if not api_key:
            raise RuntimeError("EMERGENT_LLM_KEY missing")
        chat = LlmChat(
            api_key=api_key,
            session_id=str(uuid.uuid4()),
            system_message="You are a fitness-equipment verifier. British English, terse.",
        ).with_model("openai", "gpt-4o")
        image_contents = [ImageContent(image_url=u) for u in image_urls if u]
        resp = await chat.send_message(UserMessage(text=prompt, file_contents=image_contents))
        return resp or ""
    except Exception as exc:
        logger.info("Vision LLM call failed, degrading gracefully: %s", exc)
        return ""


async def _chat(prompt: str, max_tokens: int = 800) -> str:
    """Send a prompt to GPT-4o-mini via Emergent LLM key."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
        if not api_key:
            raise RuntimeError("EMERGENT_LLM_KEY missing")
        chat = LlmChat(
            api_key=api_key,
            session_id=str(uuid.uuid4()),
            system_message=_SYSTEM_MSG,
        ).with_model("openai", "gpt-4o-mini")
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp or ""
    except Exception as exc:
        logger.warning("LLM call failed, degrading gracefully: %s", exc)
        return ""


def _parse_json(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json_mod.loads(cleaned)
    except Exception:
        return fallback


async def generate_executive_brief(ctx: dict[str, Any]) -> dict[str, Any]:
    """Return {headline, narrative, actions[]}. Always returns a usable
    payload even when the LLM is unavailable — falls back to a
    deterministic summary so the UI never looks broken."""
    kpis = ctx.get("kpis") or {}
    alerts = ctx.get("alerts") or []
    period = ctx.get("period") or "weekly"
    top = ctx.get("top_classes") or []
    under = ctx.get("underperforming_classes") or []

    prompt = (
        f"Period: {period}\n"
        f"KPIs: {json_mod.dumps(kpis)}\n"
        f"Alerts: {json_mod.dumps(alerts)}\n"
        f"Top classes: {json_mod.dumps(top)}\n"
        f"Underperforming classes: {json_mod.dumps(under)}\n\n"
        "Produce JSON with keys: headline (max 80 chars), narrative "
        "(3–5 short sentences, plain text), actions (array of 3–5 "
        "imperative one-liners a manager should do this week). "
        "Return ONLY valid JSON."
    )
    raw = await _chat(prompt, max_tokens=700)
    parsed = _parse_json(raw, {})
    if not parsed.get("headline"):
        # Deterministic fallback
        growth = (kpis.get("new_members") or 0) - (kpis.get("cancellations") or 0)
        trend = "growing" if growth > 0 else ("flat" if growth == 0 else "shrinking")
        parsed = {
            "headline": f"Membership is {trend} — net {growth} this {period}.",
            "narrative": (
                f"MRR stands at £{kpis.get('mrr_gbp', 0)} with ARPU £{kpis.get('arpu_gbp', 0)}. "
                f"Occupancy is {kpis.get('occupancy_pct', 0)}% with no-show rate "
                f"{kpis.get('no_show_pct', 0)}%. "
                f"{kpis.get('failed_payments', 0)} failed payments remain to chase."
            ),
            "actions": [
                "Review the dunning list and re-attempt failed payments.",
                "Check underperforming class slots — consider moving to peak times.",
                "Reach out personally to at-risk members flagged this week.",
            ],
        }
    parsed.setdefault("actions", [])
    return parsed


async def rank_at_risk_members(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ask the LLM to rank the top-N at-risk members and give a one-line
    reason each. Returns [{id, reason}, ...]. Falls back to rule-based
    reasons on LLM failure."""
    if not rows:
        return []

    prompt = (
        "Below are gym members flagged by heuristic scoring. For each, "
        "return a concise (max 12 words) reason focused on what an operator "
        "should say or do. Output JSON array of {id, reason}. "
        "Members:\n" + json_mod.dumps(rows, default=str)
    )
    raw = await _chat(prompt, max_tokens=600)
    parsed = _parse_json(raw, {})
    arr = parsed if isinstance(parsed, list) else parsed.get("members") or []
    if not isinstance(arr, list) or not arr:
        # Deterministic fallback
        out = []
        for r in rows:
            reasons = []
            if r.get("visits_30d", 0) == 0:
                reasons.append("no visits in 30 days")
            if r.get("payment_failures", 0) >= 1:
                reasons.append("payment failed")
            if r.get("no_show_count", 0) >= 3:
                reasons.append("repeated no-shows")
            if r.get("tenure_days", 0) < 45 and r.get("visits_30d", 0) < 3:
                reasons.append("early-tenure disengagement")
            out.append({
                "id": r["id"],
                "reason": "; ".join(reasons) or "low recent activity",
            })
        return out
    return arr
