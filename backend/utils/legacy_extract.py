"""Iter 220ea·33 — Legacy report AI extraction.

Engineers who lived on spreadsheets/PDFs upload their historic service
reports; Gemini 3 Flash reads each file and returns a structured set of
machines with their fields. The columns we already use (model, serial,
etc.) map to standard fields; everything else (Drag Factor, Firmware,
Battery %, Shock Cord …) is preserved as ordered CUSTOM FIELDS against
each machine.

File attachments are a Gemini-only capability in emergentintegrations, so
we always run on Gemini. XLSX is converted to CSV first (openpyxl).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = ("gemini", "gemini-3-flash-preview")

SYSTEM = (
    "You are a meticulous data-extraction engine for a field-service company "
    "that maintains gym / fitness equipment. You convert messy legacy service "
    "reports (PDF, CSV, spreadsheets) into clean structured JSON. You never "
    "invent data — if a value isn't present, omit it."
)

PROMPT = """Extract this legacy equipment service report into STRICT JSON.

Return ONLY a JSON object (no markdown, no commentary) of this exact shape:
{
  "customer": {            // only if clearly present in the document
    "name": string|null,
    "site_name": string|null,
    "address": string|null,
    "contact_name": string|null,
    "email": string|null,
    "phone": string|null
  },
  "service_date": string|null,   // ISO YYYY-MM-DD if a date is present
  "summary": string|null,        // 1-2 sentence overview of the visit
  "machines": [
    {
      "name": string,            // best human label e.g. "RowErg" / "Treadmill 4"
      "model": string|null,
      "serial": string|null,
      "location": string|null,
      "status": string|null,     // e.g. "Serviced", "Pass", "Needs repair"
      "work_done": string|null,  // notes / recommendations for this machine
      "custom_fields": [         // EVERYTHING else, in original column order
        { "label": string, "value": string }
      ]
    }
  ]
}

Rules:
- Each ROW of the equipment table is one machine object.
- Map obvious columns to name/model/serial/location/status/work_done.
- Put every other column (Drag Factor, Firmware, Battery %, Shock Cord,
  PM dates, 6/12-month service ticks, colour, etc.) into custom_fields as
  {label, value}, preserving the left-to-right column order. Keep tick/✓/Y
  values as "Yes" and blanks/✗ as "No" where they're clearly checkboxes.
- Keep values exactly as written (don't reformat numbers).
- If the file has multiple equipment tables, include all machines.
Output JSON only."""


def _xlsx_to_csv(file_bytes: bytes, out_dir: str) -> str:
    import csv
    import openpyxl
    src = os.path.join(out_dir, "in.xlsx")
    with open(src, "wb") as f:
        f.write(file_bytes)
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    csv_path = os.path.join(out_dir, "in.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf)
        for ws in wb.worksheets:
            writer.writerow([f"# Sheet: {ws.title}"])
            for row in ws.iter_rows(values_only=True):
                writer.writerow(["" if c is None else str(c) for c in row])
    wb.close()
    return csv_path


def _coerce_json(text: str) -> dict:
    """Pull the first JSON object out of the model response."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t
        t = t.replace("json", "", 1).strip() if t.lower().startswith("json") else t
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


def _normalise(data: dict) -> dict:
    machines = []
    for m in (data.get("machines") or []):
        if not isinstance(m, dict):
            continue
        cfs = []
        for cf in (m.get("custom_fields") or []):
            if isinstance(cf, dict) and (cf.get("label") or "").strip():
                cfs.append({
                    "label": str(cf["label"]).strip()[:120],
                    "value": ("" if cf.get("value") is None else str(cf["value"]).strip())[:500],
                })
        machines.append({
            "name": (str(m.get("name") or "").strip() or "Unnamed machine")[:160],
            "model": (str(m.get("model") or "").strip() or None),
            "serial": (str(m.get("serial") or "").strip() or None),
            "location": (str(m.get("location") or "").strip() or None),
            "status": (str(m.get("status") or "").strip() or None),
            "work_done": (str(m.get("work_done") or "").strip() or None),
            "custom_fields": cfs,
        })
    cust = data.get("customer") or {}
    return {
        "customer": {
            "name": (str(cust.get("name") or "").strip() or None),
            "site_name": (str(cust.get("site_name") or "").strip() or None),
            "address": (str(cust.get("address") or "").strip() or None),
            "contact_name": (str(cust.get("contact_name") or "").strip() or None),
            "email": (str(cust.get("email") or "").strip() or None),
            "phone": (str(cust.get("phone") or "").strip() or None),
        },
        "service_date": (str(data.get("service_date") or "").strip() or None),
        "summary": (str(data.get("summary") or "").strip() or None),
        "machines": machines,
    }


async def extract_legacy_report(file_bytes: bytes, filename: str) -> dict:
    """Run Gemini extraction. Returns the normalised structure or raises."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    tmp = tempfile.mkdtemp(prefix="legacy_")
    if ext in ("xlsx", "xls"):
        path, mime = _xlsx_to_csv(file_bytes, tmp), "text/csv"
    elif ext == "csv":
        path = os.path.join(tmp, "in.csv")
        open(path, "wb").write(file_bytes)
        mime = "text/csv"
    elif ext == "pdf":
        path = os.path.join(tmp, "in.pdf")
        open(path, "wb").write(file_bytes)
        mime = "application/pdf"
    else:
        raise ValueError(f"Unsupported file type '.{ext}' — upload PDF, CSV or XLSX")

    chat = LlmChat(api_key=api_key, session_id=f"legacy-{uuid.uuid4()}",
                   system_message=SYSTEM).with_model(*MODEL)
    msg = UserMessage(text=PROMPT, file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)])
    resp = await chat.send_message(msg)
    try:
        return _normalise(_coerce_json(resp))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[legacy] JSON parse failed: %s | head=%s", exc, (resp or "")[:200])
        raise ValueError("Could not read this file — the report format wasn't recognised. Try a clearer PDF or a CSV.")
