"""Dealer Parts — AI helpers (Emergent LLM key, advisory only).

Text-only GPT usage:
  • parse_invoice_text  — extract machine lines + order value from pasted
    invoice/order text so an order can be created and the allowance calculated.
  • dealer_summary      — draft a concise monthly stock/usage summary + a
    short dealer-facing note.

Never approves anything, never invents part numbers or machine models with
confidence — always advisory, human reviews before use.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger("dealer_parts_ai")

_MODEL = ("openai", "gpt-5.2")


def _chat(session_id: str, system: str):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(api_key=key, session_id=session_id, system_message=system).with_model(*_MODEL)
    except Exception as exc:  # pragma: no cover
        logger.warning("[dealer-parts-ai] init failed: %s", exc)
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


_INVOICE_SYSTEM = (
    "You extract structured order data from gym-equipment dealer invoices/orders "
    "for Pulse Fitness. UK English. You ONLY extract what is present in the text — "
    "never invent machine models, quantities or values. Respond with STRICT JSON "
    "only, no prose, no markdown fences."
)


async def parse_invoice_text(text: str) -> dict:
    """Return {available, order_reference, currency, order_value, lines:[{machine_model,
    quantity, unit_value}], note}. Advisory only."""
    chat = _chat(f"dp_invoice_{datetime.now().timestamp()}", _INVOICE_SYSTEM)
    if not chat:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    prompt = (
        "From the dealer invoice/order text below, extract the equipment lines and totals. "
        "Return STRICT JSON:\n"
        '{\n'
        '  "order_reference": "PO/invoice ref if present else empty",\n'
        '  "currency": "ISO code if determinable else empty",\n'
        '  "order_value": 0,\n'
        '  "lines": [ {"machine_model":"", "quantity":0, "unit_value":0} ],\n'
        '  "note": "one short caveat if anything is ambiguous, else empty"\n'
        '}\n'
        "Only include equipment/machine lines (ignore shipping, tax, discounts as lines but "
        "include them in order_value if that is the grand total). If a unit price is not shown, "
        "set unit_value to 0. Never guess a machine model that is not written.\n\n"
        f"INVOICE TEXT:\n{text[:8000]}"
    )
    try:
        from emergentintegrations.llm.chat import UserMessage
        raw = (await chat.send_message(UserMessage(text=prompt))).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[dealer-parts-ai] invoice send failed: %s", exc)
        return {"available": False, "error": "AI request failed."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    parsed["advisory_only"] = True
    parsed.setdefault("lines", [])
    return parsed


_SUMMARY_SYSTEM = (
    "You are a Pulse Fitness dealer-parts analyst. UK English, concise and factual. "
    "You summarise a dealer's warranty-parts position for internal managers and draft "
    "a short, friendly dealer-facing note. Base everything strictly on the data given. "
    "Respond with STRICT JSON only, no prose, no markdown fences."
)


async def dealer_summary(context: dict) -> dict:
    """Return {available, summary, dealer_note, highlights:[...]}. Advisory only."""
    chat = _chat(f"dp_summary_{datetime.now().timestamp()}", _SUMMARY_SYSTEM)
    if not chat:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    prompt = (
        "Given this dealer's parts data (JSON), produce STRICT JSON:\n"
        '{\n'
        '  "summary": "3-4 sentence internal summary of stock, usage, allowance and any risks",\n'
        '  "highlights": ["short bullet", "short bullet", "short bullet"],\n'
        '  "dealer_note": "a short, friendly 2-3 sentence note to the dealer about their parts position"\n'
        '}\n\n'
        f"DEALER DATA:\n{json.dumps(context)[:8000]}"
    )
    try:
        from emergentintegrations.llm.chat import UserMessage
        raw = (await chat.send_message(UserMessage(text=prompt))).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[dealer-parts-ai] summary send failed: %s", exc)
        return {"available": False, "error": "AI request failed."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed["available"] = True
    parsed["advisory_only"] = True
    parsed.setdefault("highlights", [])
    return parsed


__all__ = ["parse_invoice_text", "parse_invoice_file", "dealer_summary"]


def _text_from_file(content: bytes, filename: str) -> str:
    """Best-effort text extraction from an invoice file (pdf/xlsx/csv/txt)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as exc:  # pragma: no cover
            logger.warning("[dealer-parts-ai] pdf extract failed: %s", exc)
            return ""
    if name.endswith((".xlsx", ".xls")):
        try:
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            out = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        out.append("\t".join(cells))
            wb.close()
            return "\n".join(out)
        except Exception as exc:  # pragma: no cover
            logger.warning("[dealer-parts-ai] xlsx extract failed: %s", exc)
            return ""
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""


async def _parse_invoice_image(content: bytes, mime: str) -> dict:
    """Parse an invoice image via the multimodal model."""
    chat = _chat(f"dp_invoice_img_{datetime.now().timestamp()}", _INVOICE_SYSTEM)
    if not chat:
        return {"available": False, "error": "AI is not configured or is unavailable."}
    import base64
    b64 = base64.b64encode(content).decode()
    prompt = (
        "This is a dealer equipment invoice/order image. Extract equipment lines and totals as STRICT JSON:\n"
        '{"order_reference":"","currency":"","order_value":0,'
        '"lines":[{"machine_model":"","quantity":0,"unit_value":0}],"note":""}\n'
        "Only include equipment/machine lines. Never invent a machine model that is not shown."
    )
    try:
        from emergentintegrations.llm.chat import UserMessage, ImageContent
        raw = (await chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=b64)]))).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("[dealer-parts-ai] invoice image failed: %s", exc)
        return {"available": False, "error": "AI could not read the image. Try a PDF or paste the text."}
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return {"available": False, "error": "AI returned an unreadable response."}
    parsed.update({"available": True, "advisory_only": True})
    parsed.setdefault("lines", [])
    return parsed


async def parse_invoice_file(content: bytes, filename: str, content_type: str = "") -> dict:
    """Parse an uploaded invoice file (pdf/xlsx/csv/txt/image) into structured lines."""
    name = (filename or "").lower()
    is_image = name.endswith((".png", ".jpg", ".jpeg", ".webp")) or (content_type or "").startswith("image/")
    if is_image:
        return await _parse_invoice_image(content, content_type or "image/png")
    text = _text_from_file(content, filename)
    if not text.strip():
        return {"available": False, "error": "Could not read text from this file. Try a PDF/Excel or paste the text."}
    return await parse_invoice_text(text)
