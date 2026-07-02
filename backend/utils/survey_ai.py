"""Pre-Install Site Survey — AI assistant (Phase 2).

Advisory only. Powered by the Emergent LLM key (OpenAI GPT), mirroring
the verified ``utils.comms_ai`` integration. The assistant NEVER approves
a site for installation and NEVER mutates survey data — it only returns
suggestions for a human to review and accept.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger("survey_ai")

_MODEL = ("openai", "gpt-5.2")

_SYSTEM = (
    "You are an installation-readiness assistant for Pulse Fitness, a premium "
    "gym-equipment installer. You review PRE-INSTALL SITE SURVEYS completed by "
    "sales/account managers before a gym equipment installation. UK English, "
    "concise, practical. You focus on delivery/access, power/electrical, "
    "network/IPTV, room measurements, flooring/walls/ceiling clearance and "
    "health & safety risks. You NEVER approve a site for installation and you "
    "NEVER invent facts — if something is not in the survey, treat it as MISSING. "
    "Always respond with STRICT JSON only, no prose, no markdown fences."
)


def _chat(session_id: str):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(api_key=key, session_id=session_id, system_message=_SYSTEM).with_model(*_MODEL)
    except Exception as exc:  # pragma: no cover
        logger.warning("[survey-ai] init failed: %s", exc)
        return None


def _extract_json(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        for opener, closer in (("{", "}"), ("[", "]")):
            i, j = raw.find(opener), raw.rfind(closer)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(raw[i:j + 1])
                except Exception:
                    pass
    return None


async def _ask(prompt: str, tag: str) -> str | None:
    chat = _chat(f"{tag}_{datetime.now().timestamp()}")
    if not chat:
        return None
    try:
        from emergentintegrations.llm.chat import UserMessage
        return (await chat.send_message(UserMessage(text=prompt))).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[survey-ai] send failed: %s", exc)
        return None


def _flatten(doc: dict) -> str:
    """Compact, readable text view of the survey for the model."""
    data = doc.get("data") or {}
    lines = [
        f"Reference: {doc.get('reference')}",
        f"Company: {doc.get('company_name')}",
        f"Site: {doc.get('site_name')}",
        f"Survey type: {doc.get('survey_type')}",
        f"Target install date: {doc.get('target_install_date')}",
        f"Status: {doc.get('status')}",
        f"Linked quote/opportunity: {bool(doc.get('quote_id') or doc.get('opportunity_id'))}",
        f"Attachments on file: {doc.get('attachment_count', 0)} (floor plan: {doc.get('has_floor_plan')})",
    ]
    for sec in ("site_details", "access", "parking", "power", "network",
                "flooring", "walls", "ceiling", "ventilation", "site_rules",
                "customer_requirements", "installation_notes"):
        d = data.get(sec) or {}
        if d:
            kv = "; ".join(f"{k}={v}" for k, v in d.items() if v not in (None, "", []))
            if kv:
                lines.append(f"[{sec}] {kv}")
    rooms = data.get("rooms") or []
    for i, r in enumerate(rooms, 1):
        lines.append(f"[room {i}] " + "; ".join(f"{k}={v}" for k, v in r.items() if v not in (None, "", [])))
    equip = data.get("equipment") or []
    for i, e in enumerate(equip, 1):
        lines.append(f"[equipment {i}] " + "; ".join(f"{k}={v}" for k, v in e.items() if v not in (None, "", [])))
    risks = data.get("risks") or []
    for i, rk in enumerate(risks, 1):
        lines.append(f"[risk {i}] " + "; ".join(f"{k}={v}" for k, v in rk.items() if v not in (None, "", [])))
    return "\n".join(lines)


async def analyse_survey(doc: dict, readiness: dict) -> dict:
    """Return a structured advisory analysis (summary, missing info, risks,
    suggested questions, concerns, and a readiness RECOMMENDATION)."""
    survey_text = _flatten(doc)
    critical_missing = readiness.get("critical_missing") or []
    prompt = (
        "Analyse this pre-install site survey and return STRICT JSON with keys:\n"
        '{\n'
        '  "summary": "3-4 sentence plain-English summary of the site & job",\n'
        '  "missing_information": ["specific fields/answers still needed before install"],\n'
        '  "risks": [{"area":"access|electrical|network|manual_handling|ceiling|flooring|customer_readiness|other","description":"","severity":"low|medium|high|critical"}],\n'
        '  "suggested_questions": ["questions the sales manager should ask the customer/site"],\n'
        '  "concerns": {"electrical":"", "network":"", "access":""},\n'
        '  "readiness_recommendation": {"recommendation":"not_ready|ready_for_quote|ready_for_design|needs_review", "reasoning":"one line"}\n'
        '}\n'
        "Base everything ONLY on the survey below. Do not approve installation. "
        f"The system already computed these CRITICAL missing items: {critical_missing}.\n\n"
        f"SURVEY:\n{survey_text}"
    )
    raw = await _ask(prompt, "survey_analyse")
    if raw is None:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    parsed["advisory_only"] = True
    return parsed


async def draft_follow_up_email(doc: dict, missing: list[str]) -> dict:
    survey_text = _flatten(doc)
    prompt = (
        "Draft a short, friendly UK-English follow-up email FROM the Pulse Fitness "
        "account manager TO the customer/site contact, requesting the missing "
        "information needed to progress their gym installation. Return STRICT JSON: "
        '{"subject":"", "body":"plain text with line breaks, no markdown"}. '
        "Be specific about what is needed and why it matters for a smooth install. "
        "Do not invent dates or prices.\n"
        f"Known missing items (from the system): {missing}\n\n"
        f"SURVEY:\n{survey_text}"
    )
    raw = await _ask(prompt, "survey_email")
    if raw is None:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    return parsed


async def draft_briefing(doc: dict) -> dict:
    survey_text = _flatten(doc)
    prompt = (
        "Write a concise installation-team briefing (UK English) for the engineers/"
        "installers attending this site. Cover: access & delivery route, parking/"
        "loading, power/electrical, network needs, room/clearance constraints, and "
        "the top risks with mitigations. Use short headed sections in plain text. "
        'Return STRICT JSON: {"briefing":"plain text with line breaks"}. '
        "Only use facts from the survey; flag anything unknown as 'to confirm on site'.\n\n"
        f"SURVEY:\n{survey_text}"
    )
    raw = await _ask(prompt, "survey_briefing")
    if raw is None:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    return parsed


__all__ = ["analyse_survey", "draft_follow_up_email", "draft_briefing"]
