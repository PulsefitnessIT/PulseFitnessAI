"""Parts Request — AI part identification (Emergent LLM key).

Advisory only. Given a photo of a broken/required part plus the machine
context (manufacturer/model/type), the assistant suggests the likely
part name + part number so the operator can raise an accurate request.
Never fabricates a definite part number — always returns a confidence.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger("parts_ai")

_MODEL = ("openai", "gpt-5.2")

_SYSTEM = (
    "You are a gym-equipment spare-parts identification assistant for Pulse "
    "Fitness. Given a photo of a part (or the area needing a part) and the "
    "machine make/model, you identify the most likely spare part. UK English, "
    "concise, practical. You NEVER invent an exact manufacturer part number "
    "unless it is clearly legible in the image — instead describe the part and "
    "give your confidence. Always respond with STRICT JSON only, no prose, no "
    "markdown fences."
)


def _chat(session_id: str):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(api_key=key, session_id=session_id, system_message=_SYSTEM).with_model(*_MODEL)
    except Exception as exc:  # pragma: no cover
        logger.warning("[parts-ai] init failed: %s", exc)
        return None


def _extract_json(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                pass
    return None


async def identify_part(image_b64: str, *, machine_type: str = "", manufacturer: str = "",
                        model: str = "", notes: str = "") -> dict:
    """Return {available, suggestions:[{part_name, part_number, category,
    confidence, reasoning}], observed_text, note}. Advisory only."""
    chat = _chat(f"parts_identify_{datetime.now().timestamp()}")
    if not chat:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    context = "; ".join(
        f"{k}={v}" for k, v in (
            ("machine_type", machine_type), ("manufacturer", manufacturer),
            ("model", model), ("operator_notes", notes),
        ) if v
    ) or "(no machine context provided)"
    prompt = (
        "Identify the spare part(s) required from this photo. Return STRICT JSON:\n"
        '{\n'
        '  "suggestions": [\n'
        '    {"part_name":"", "part_number":"", "category":"consumable|wear_tear|major|electrical|upholstery|other",\n'
        '     "confidence":"low|medium|high", "reasoning":"one short line"}\n'
        '  ],\n'
        '  "observed_text": "any legible part numbers / labels seen in the image, else empty",\n'
        '  "note": "one short caveat if the image is unclear, else empty"\n'
        '}\n'
        "Only set part_number when it is clearly legible in the image; otherwise leave it empty. "
        "Give 1-3 suggestions, most likely first.\n\n"
        f"MACHINE CONTEXT: {context}"
    )
    try:
        from emergentintegrations.llm.chat import UserMessage, ImageContent
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
        raw = (await chat.send_message(msg)).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[parts-ai] send failed: %s", exc)
        return {"available": False, "error": "AI request failed."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    parsed["advisory_only"] = True
    parsed.setdefault("suggestions", [])
    return parsed


__all__ = ["identify_part"]
