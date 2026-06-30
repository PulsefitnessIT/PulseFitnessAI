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


_IMPORT_SYSTEM = (
    _BRAND + " You are an email migration assistant. You are given the content of an "
    "existing email (as extracted text/HTML, and/or an image or PDF of the email). "
    "Rebuild it as a Pulse Fitness AI drag-and-drop template, faithfully preserving the "
    "content, copy, hierarchy and call-to-action order, but re-styled cleanly on-brand.\n"
    "Return ONLY JSON: {\"subject\": str, \"preview\": str, "
    "\"blocks\": [{\"type\": str, \"props\": {...}}], \"notes\": [str]}.\n"
    "Each block MUST be an object with exactly two keys: \"type\" (a string) and "
    "\"props\" (an object). Example block: {\"type\": \"heading\", \"props\": "
    "{\"text\": \"Welcome\", \"size\": 26, \"align\": \"left\"}}.\n"
    "Allowed block types and their props:\n"
    "- heading: {text, size (20-30), align, color}\n"
    "- text: {text, align}  (one paragraph each; split long copy into multiple text blocks)\n"
    "- button: {text, url}  (use the original link if present, else '{{booking_link}}')\n"
    "- image: {src, alt}\n"
    "- divider: {}\n"
    "- spacer: {height}\n"
    "Rules:\n"
    "1. Use the email's real subject line if present, otherwise infer a fitting one.\n"
    "2. For every image in the original: if a usable absolute URL appears in AVAILABLE_IMAGES, "
    "set props.src to that exact URL and write descriptive props.alt. If an image clearly existed "
    "but NO usable URL is available (inline/embedded/screenshot), still add an image block with "
    "src=\"\" and a descriptive props.alt, AND append a human-readable line to \"notes\" such as "
    "'The header image could not be pulled in automatically — add it manually.'\n"
    "3. Preserve merge tags like {{first_name}} if present. Do not invent prices, dates or facts.\n"
    "4. Do NOT add a logo or footer block — the builder adds those. 4-14 blocks total."
)


async def import_email_to_blocks(text_content: str, available_images: list,
                                 image_b64: Optional[str] = None,
                                 file_path: Optional[str] = None,
                                 file_mime: Optional[str] = None):
    """Reverse-engineer a dropped email into editable template blocks.

    ``text_content`` is the extracted text/HTML; ``available_images`` is a list
    of {url, alt} pulled from the source; ``image_b64`` / ``file_path`` feed the
    vision model for screenshots/PDFs. Returns the block JSON or None.
    """
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import (
            LlmChat, UserMessage, ImageContent, FileContentWithMimeType,
        )
        chat = LlmChat(
            api_key=key, session_id=f"import_{datetime.now().timestamp()}",
            system_message=_IMPORT_SYSTEM,
        ).with_model("openai", "gpt-4o")

        parts = []
        if text_content and text_content.strip():
            parts.append("EMAIL CONTENT (extracted):\n" + text_content.strip()[:18000])
        if available_images:
            parts.append("AVAILABLE_IMAGES (usable URLs you may place):\n"
                         + json.dumps(available_images[:20], default=str))
        if image_b64 or file_path:
            parts.append("An image/PDF of the email is attached — read its layout and copy.")
        if not parts:
            return None
        prompt = "\n\n".join(parts)

        file_contents = []
        if image_b64:
            file_contents.append(ImageContent(image_base64=image_b64))
        if file_path and file_mime:
            file_contents.append(FileContentWithMimeType(file_path=file_path, mime_type=file_mime))

        msg = UserMessage(text=prompt, file_contents=file_contents) if file_contents else UserMessage(text=prompt)
        raw = (await chat.send_message(msg)).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[comms-ai] import failed: %s", exc)
        return None

    data = _extract_json(raw)
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


async def suggest_segment(description: str, catalogue: dict):
    """Turn a plain-English audience description into a rule tree, strictly
    using the provided field catalogue. Returns {name, source, rules}."""
    system = (
        _BRAND + " You build audience segments. Return ONLY JSON: "
        "{\"name\": str, \"source\": \"contacts\"|\"members\", "
        "\"rules\": {\"op\": \"and\"|\"or\", \"conditions\": "
        "[{\"field\": str, \"op\": str, \"value\": any}]}}. "
        "You MUST only use fields, operators and (for select fields) option "
        "values from the provided CATALOGUE. Use date sentinels like "
        "'90d_ago' for date fields. Keep it to 1-4 conditions."
    )
    prompt = (
        f"Audience to build: {description}\n\nCATALOGUE:\n{json.dumps(catalogue, default=str)}"
    )
    raw = await _ask(system, prompt, "segsug")
    data = _extract_json(raw) if raw else None
    if isinstance(data, dict) and isinstance(data.get("rules"), dict):
        return data
    return None
