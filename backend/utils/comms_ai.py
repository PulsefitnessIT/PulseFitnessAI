"""Pulse Fitness AI — Comms AI assistant (Phase 2).

Writing + analysis helpers powered by the Emergent LLM key, mirroring the
existing ``incident_ai`` / ``risk_assessments`` integration pattern. The
assistant NEVER sends, approves, deletes or mutates consent — it only
returns suggestions for the user to accept.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger("comms_ai")

_MODEL = ("openai", "gpt-5.2")


def _chat(system: str, session_id: str):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(api_key=key, session_id=session_id, system_message=system).with_model(*_MODEL)
    except Exception as exc:  # pragma: no cover
        logger.warning("[comms-ai] LlmChat init failed: %s", exc)
        return None


def _extract_json(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        # try to locate first {...} or [...]
        for opener, closer in (("[", "]"), ("{", "}")):
            i, j = raw.find(opener), raw.rfind(closer)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(raw[i:j + 1])
                except Exception:
                    pass
    return None


async def _ask(system: str, prompt: str, tag: str):
    chat = _chat(system, f"{tag}_{datetime.now().timestamp()}")
    if not chat:
        return None
    try:
        from emergentintegrations.llm.chat import UserMessage
        return (await chat.send_message(UserMessage(text=prompt))).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[comms-ai] send failed: %s", exc)
        return None


_BRAND = (
    "You write for Pulse Fitness AI, a premium fitness + B2B communications platform. "
    "Tone: warm, professional, concise, UK English. Never mention you are an AI. "
    "Never invent prices, dates or facts. Keep merge tags like {{first_name}} intact."
)


async def generate_subjects(topic: str, audience: str, tone: str, n: int = 5):
    system = _BRAND + " Return ONLY a JSON array of subject-line strings."
    prompt = (
        f"Write {n} high-performing email subject lines.\n"
        f"Topic: {topic}\nAudience: {audience or 'general'}\nTone: {tone or 'friendly professional'}\n"
        "Keep each under 60 characters. Avoid spammy words and ALL CAPS. "
        "Vary the angle (benefit, curiosity, urgency, personal)."
    )
    raw = await _ask(system, prompt, "subj")
    data = _extract_json(raw) if raw else None
    if isinstance(data, list):
        return [str(s).strip() for s in data if str(s).strip()][:n]
    return None


async def write_email(brief: str, campaign_type: str, tone: str):
    system = (
        _BRAND + " Return ONLY JSON: {\"subject\": str, \"preview\": str, "
        "\"blocks\": [{\"type\": \"heading|text|button\", \"props\": {...}}]}. "
        "Use 'heading' (props.text), 'text' (props.text, may contain simple sentences), "
        "and at most one 'button' (props.text, props.url='{{booking_link}}'). "
        "3-5 blocks total. Personalise with {{first_name}} where natural."
    )
    prompt = (
        f"Draft a {campaign_type or 'marketing'} email.\nBrief: {brief}\n"
        f"Tone: {tone or 'friendly professional'}."
    )
    raw = await _ask(system, prompt, "write")
    data = _extract_json(raw) if raw else None
    if isinstance(data, dict) and isinstance(data.get("blocks"), list):
        return data
    return None


async def improve_text(text: str, goal: str):
    system = _BRAND + " Return ONLY the improved text, no preamble, no quotes."
    prompt = (
        f"Improve this email copy. Goal: {goal or 'clarity and engagement'}.\n"
        f"Keep merge tags intact. Keep it roughly the same length.\n\nCOPY:\n{text}"
    )
    raw = await _ask(system, prompt, "improve")
    return raw.strip().strip('"') if raw else None


async def analyse_campaign(context: dict):
    system = (
        _BRAND + " You are a marketing analyst. Return ONLY JSON: "
        "{\"summary\": str, \"what_worked\": [str], \"what_to_improve\": [str], "
        "\"recommendations\": [str]}. Be specific and reference the numbers."
    )
    prompt = (
        "Analyse this email campaign performance and explain plainly why it "
        "did well or under-performed, then give concrete next steps.\n\n"
        f"DATA:\n{json.dumps(context, default=str)}"
    )
    raw = await _ask(system, prompt, "analyse")
    data = _extract_json(raw) if raw else None
    if isinstance(data, dict) and data.get("summary"):
        return data
    return None
