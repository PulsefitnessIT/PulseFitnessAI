"""Iter 220v — Incident AI helpers.

Three single-purpose AI helpers powered by the Emergent LLM key:

* ``summarise_incident``     — turns a long free-form description
  into a clean 2–3 sentence management summary.
* ``suggest_root_causes``    — proposes 1–3 likely root causes from
  the canonical ``ROOT_CAUSE_OPTIONS`` enum given the incident
  description + category. Returns enum keys (never free text) so
  the UI can pre-select chips in the Investigation pane.
* ``hint_riddor_qualification`` — best-effort triage hint that maps
  to the same wizard keys ``utils.riddor`` exposes. **Strictly
  advisory** — never sets the RIDDOR status on the incident; just
  pre-populates Yes/No/Don't-know on the wizard for the assessor
  to confirm.

All helpers:
* use ``LlmChat`` with Claude Sonnet 4.5 (recommended for structured
  reasoning and conservative output);
* return ``None`` on any failure (network, parse, rate-limit) so the
  caller can fall back gracefully — AI is a nice-to-have, never a
  hard dependency;
* are wrapped in a per-incident session id so message history can
  be persisted later if we ever want a "chat with this incident".
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

# emergentintegrations (litellm) imported lazily inside functions to keep it off the startup import path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from emergentintegrations.llm.chat import LlmChat  # noqa: F401

logger = logging.getLogger(__name__)

# Same enum the investigation pane uses (kept in lockstep with
# `routes.incidents.ROOT_CAUSE_OPTIONS`).
ROOT_CAUSE_KEYS = (
    "equipment_failure", "maintenance_issue", "user_error",
    "training_gap", "environmental", "process_failure",
    "contractor_issue", "communication", "inadequate_supervision",
    "other",
)

RIDDOR_WIZARD_KEYS = (
    "arose_from_work", "person_at_work", "fatality", "specified_injury",
    "over_7_day_incapacitation", "non_worker_to_hospital",
    "dangerous_occurrence", "occupational_disease", "gas_incident",
)


def _key() -> Optional[str]:
    k = os.environ.get("EMERGENT_LLM_KEY")
    return k or None


def _chat(system: str, session_id: str) -> Optional[LlmChat]:
    k = _key()
    if not k:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(
            api_key=k, session_id=session_id, system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incident-ai] LlmChat init failed: %s", exc)
        return None


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of the model's response. Models
    occasionally wrap JSON in fenced code blocks or prose; this
    handles both."""
    if not text:
        return None
    # Try a direct parse first
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    # Then look for a fenced ```json … ``` block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    # Fallback: first { … } in the body
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    return None


async def summarise_incident(incident: dict) -> Optional[str]:
    """Return a 2–3 sentence management summary. Pure prose; no
    structured output. Returns ``None`` on any failure."""
    chat = _chat(
        "You are an experienced H&S officer summarising workplace incidents for "
        "site managers. Write in plain UK English, no jargon, no speculation. "
        "Stick to what's in the source description. Avoid blame language. "
        "2–3 sentences, no headings, no bullets.",
        session_id=f"incident-summary:{incident.get('id','')}",
    )
    if not chat:
        return None
    desc = (incident.get("description") or "").strip()
    if len(desc) < 20:
        return None
    facts = []
    sev = incident.get("severity")
    if sev:
        facts.append(f"Severity: {sev}.")
    cat = incident.get("category")
    if cat:
        facts.append(f"Category: {cat.replace('_', ' ')}.")
    loc = (incident.get("location") or {}).get("area")
    if loc:
        facts.append(f"Location: {loc}.")
    ip = (incident.get("injured_party") or {})
    if ip.get("role"):
        facts.append(f"Affected: {ip['role']}.")
    prompt = (
        "Summarise the following incident in 2 to 3 sentences for the manager's morning briefing.\n\n"
        f"Description:\n{desc}\n\n"
        f"Context: {' '.join(facts) if facts else '(none provided)'}"
    )
    try:
        from emergentintegrations.llm.chat import UserMessage
        response = await chat.send_message(UserMessage(text=prompt))
        text = (response or "").strip()
        # Strip wrapping quotes / code fences if the model added them
        text = text.strip("`").strip('"').strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incident-ai] summarise failed: %s", exc)
        return None


async def suggest_root_causes(incident: dict) -> Optional[list[str]]:
    """Return up to 3 root-cause keys from ``ROOT_CAUSE_KEYS``. Keys
    are validated server-side before returning so a hallucinated
    cause never leaks to the UI."""
    chat = _chat(
        "You are an H&S investigator. Given an incident description, "
        "return STRICT JSON with one key 'root_causes', whose value is "
        "an array of 1 to 3 strings drawn ONLY from this exact list:\n"
        f"{', '.join(ROOT_CAUSE_KEYS)}\n"
        "Do NOT invent new categories. Order from most to least likely.",
        session_id=f"incident-causes:{incident.get('id','')}",
    )
    if not chat:
        return None
    desc = (incident.get("description") or "").strip()
    if len(desc) < 20:
        return None
    prompt = (
        f"Incident category: {incident.get('category') or 'unknown'}\n"
        f"Severity: {incident.get('severity') or 'unknown'}\n"
        f"Description: {desc}\n\n"
        'Reply with JSON like: {"root_causes": ["equipment_failure", "maintenance_issue"]}'
    )
    try:
        from emergentintegrations.llm.chat import UserMessage
        raw = await chat.send_message(UserMessage(text=prompt))
        data = _extract_json(raw or "") or {}
        causes = data.get("root_causes") or []
        cleaned = [c for c in causes if isinstance(c, str) and c in ROOT_CAUSE_KEYS]
        return cleaned[:3] or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incident-ai] root-causes failed: %s", exc)
        return None


async def hint_riddor_qualification(incident: dict) -> Optional[dict]:
    """Returns a draft answer map for the RIDDOR wizard
    (``{key: bool|None}``). Conservative — when the description is
    ambiguous the model SHOULD return ``null`` so the human still
    has to pick. Returns ``None`` on any failure."""
    chat = _chat(
        "You are an H&S officer pre-screening incidents for RIDDOR reportability "
        "under the UK Reporting of Injuries, Diseases and Dangerous Occurrences "
        "Regulations 2013. Be conservative: when the description doesn't make "
        "the answer crystal clear, return null (don't-know) for that question — "
        "never guess.\n\n"
        "Return STRICT JSON with EXACTLY these keys (each value must be true, "
        "false, or null):\n"
        f"{', '.join(RIDDOR_WIZARD_KEYS)}\n\n"
        "Also include 'reasoning' (1 sentence per qualifying yes) so the "
        "manager can sanity-check.",
        session_id=f"incident-riddor:{incident.get('id','')}",
    )
    if not chat:
        return None
    desc = (incident.get("description") or "").strip()
    if len(desc) < 20:
        return None
    ip = incident.get("injured_party") or {}
    prompt = (
        f"Incident description: {desc}\n"
        f"Severity: {incident.get('severity') or 'unknown'}\n"
        f"Category: {incident.get('category') or 'unknown'}\n"
        f"Injured party role: {ip.get('role') or 'unknown'}\n"
        f"Hospital treatment: {incident.get('hospital_treatment')}\n"
        f"Fatality flag: {incident.get('fatality')}\n\n"
        "Return JSON only. Example:\n"
        '{"arose_from_work": true, "person_at_work": true, "fatality": false, '
        '"specified_injury": null, "over_7_day_incapacitation": null, '
        '"non_worker_to_hospital": false, "dangerous_occurrence": false, '
        '"occupational_disease": false, "gas_incident": false, '
        '"reasoning": "Slip on wet floor; person not transported to hospital."}'
    )
    try:
        from emergentintegrations.llm.chat import UserMessage
        raw = await chat.send_message(UserMessage(text=prompt))
        data = _extract_json(raw or "") or {}
        answers: dict[str, Optional[bool]] = {}
        for k in RIDDOR_WIZARD_KEYS:
            v = data.get(k)
            if v is True or v is False or v is None:
                answers[k] = v
            else:
                answers[k] = None
        reasoning = data.get("reasoning") or ""
        if isinstance(reasoning, list):
            reasoning = " ".join(str(r) for r in reasoning)
        return {"answers": answers, "reasoning": str(reasoning)[:600]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incident-ai] RIDDOR hint failed: %s", exc)
        return None


async def transcribe_audio(file_obj, *, language: str = "en") -> Optional[str]:
    """Whisper transcription wrapper. ``file_obj`` is a file-like
    object opened in binary mode. Returns plain text or ``None``."""
    from emergentintegrations.llm.openai import OpenAISpeechToText

    k = _key()
    if not k:
        return None
    try:
        stt = OpenAISpeechToText(api_key=k)
        response = await stt.transcribe(
            file=file_obj,
            model="whisper-1",
            response_format="text",
            language=language,
        )
        # Library returns either a plain string for response_format='text'
        # or an object with a `.text` attribute. Be defensive.
        if isinstance(response, str):
            return response.strip() or None
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text.strip() or None
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incident-ai] transcription failed: %s", exc)
        return None
