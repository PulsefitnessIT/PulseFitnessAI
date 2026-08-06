"""AI-assisted MOD kit-list importer.

Reads ANY equipment spreadsheet (all tabs), figures out which columns hold the
type/model/manufacturer/serial/asset/quantity, derives a clean grammatical
equipment NAME (there is rarely a Name column), title-cases the usually
ALL-CAPS text, treats each worksheet tab as a sub-location/room by default,
and skips obvious summary / pivot tabs.

The LLM only cleans the small set of DISTINCT (type, model, manufacturer)
tuples — it never re-emits row data, so it can't hallucinate serials/quantities.
Falls back to a deterministic title-caser if the LLM is unavailable.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import asyncio

logger = logging.getLogger("kit_list_ai")

_MODEL = ("openai", "gpt-5.2")
_LLM_TIMEOUT = 90

# Known gym brands → correct casing (extend as needed).
_BRANDS = {
    "WATTBIKE": "Wattbike", "TECHNOGYM": "Technogym", "CONCEPT 2": "Concept 2",
    "CONCEPT2": "Concept 2", "MARPO": "Marpo", "BULLDOG": "Bulldog",
    "BULLDOG GEAR": "Bulldog Gear", "PURE STRENGTH": "Pure Strength",
    "LEISURELINES": "Leisurelines", "LIFE FITNESS": "Life Fitness",
    "MATRIX": "Matrix", "PRECOR": "Precor", "HAMMER STRENGTH": "Hammer Strength",
    "STAR TRAC": "Star Trac", "CYBEX": "Cybex", "ROGUE": "Rogue",
    "ESCAPE": "Escape", "JORDAN": "Jordan", "NAUTILUS": "Nautilus",
}

_HEADER_HINTS = {
    "type": ["type", "equipment type", "equipment", "description", "item", "asset type"],
    "model": ["model", "model number", "model no"],
    "manufacturer": ["manufacturer", "make", "brand", "supplier"],
    "serial_number": ["frame - serial number", "frame serial number", "serial number",
                      "serial", "serial no", "frame serial", "s/n", "sn"],
    "serial_secondary": ["console - serial number", "console serial number", "console serial"],
    "asset_number": ["servicesport asset number", "asset number", "asset no", "asset id",
                     "asset tag", "nsn", "mod asset number"],
    "quantity": ["qty", "quantity", "count", "no.", "number"],
    "category": ["category", "class", "group"],
    "mod_code": ["mod-code", "mod code"],
}

_SUMMARY_NAMES = ("total", "totals", "summary", "pivot", "overview", "grand total", "sum")
_SUMMARY_CELL_HINTS = ("row labels", "sum of", "grand total", "count of")


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("none", "nan", "na", "n/a", "-") else s


def _title_case(s: str, preserve_acronyms: bool = True) -> str:
    s = _clean(s)
    if not s:
        return ""
    up = s.upper()
    if up in _BRANDS:
        return _BRANDS[up]
    words = []
    for w in re.split(r"(\s+)", s):
        if w.isspace() or w == "":
            words.append(w)
            continue
        # keep short alphanumeric codes (letters+digits) uppercase, e.g. D91, DAC73L
        if re.search(r"\d", w) and re.search(r"[A-Za-z]", w) and len(w) <= 8:
            words.append(w.upper())
        # preserve all-caps acronyms (all letters, 2-5 chars) e.g. FMB, PCRF, RAF
        elif preserve_acronyms and w.isupper() and w.isalpha() and 2 <= len(w) <= 5:
            words.append(w)
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return "".join(words)


def _match_header(cell: str) -> str | None:
    c = _clean(cell).lower()
    if not c:
        return None
    for field, hints in _HEADER_HINTS.items():
        if any(c == h or c.startswith(h) for h in hints):
            return field
    return None


def _looks_like_zip(content: bytes) -> bool:
    # xlsx/xlsm are OOXML zip archives — they start with the local file header 'PK'.
    return len(content) >= 2 and content[:2] == b"PK"


def _csv_to_workbook(content: bytes, filename: str = ""):
    """Build an in-memory workbook from a CSV/TSV so the rest of the pipeline
    (which expects openpyxl worksheets) works unchanged."""
    import csv
    import openpyxl
    text = content.decode("utf-8-sig", errors="replace")
    name = (filename or "").lower()
    if name.endswith(".tsv"):
        delim = "\t"
    else:
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except Exception:
            delim = ","
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in csv.reader(io.StringIO(text), delimiter=delim):
        ws.append(list(row))
    return wb


def _read_workbook(content: bytes, filename: str = ""):
    """Read an uploaded kit list. Handles .xlsx/.xlsm (zip-based) AND plain
    .csv/.tsv (which are NOT zip files, so openpyxl can't open them directly)."""
    import openpyxl
    name = (filename or "").lower()
    if name.endswith((".csv", ".tsv", ".txt")) or not _looks_like_zip(content):
        return _csv_to_workbook(content, name)
    try:
        return openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        # Mislabeled or odd file — last-ditch attempt to read it as delimited text.
        return _csv_to_workbook(content, name)


def _analyse_sheet(ws):
    """Locate the header row + column map; collect raw rows. Returns dict."""
    rows = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 3000), values_only=True))
    header_idx, colmap = None, {}
    for i, r in enumerate(rows[:8]):
        m = {}
        for ci, cell in enumerate(r or []):
            f = _match_header(cell)
            if f and f not in m:
                m[f] = ci
        if ("type" in m or "model" in m) and ("manufacturer" in m or "serial_number" in m or "asset_number" in m):
            header_idx, colmap = i, m
            break
    is_summary = ((ws.title or "").strip().lower() in _SUMMARY_NAMES)
    data_rows = []
    if header_idx is not None:
        for r in rows[header_idx + 1:]:
            if not r:
                continue
            cells = list(r)
            joined = " ".join(_clean(x) for x in cells).lower()
            if not joined.strip():
                continue
            if any(h in joined for h in _SUMMARY_CELL_HINTS):
                is_summary = True
                continue

            def g(field):
                ci = colmap.get(field)
                return _clean(cells[ci]) if ci is not None and ci < len(cells) else ""
            typ, model = g("type"), g("model")
            serial = g("serial_number") or g("serial_secondary")
            asset = g("asset_number")
            if not (typ or model or serial or asset):
                continue
            try:
                qty = int(float(g("quantity"))) if g("quantity") else 1
            except Exception:
                qty = 1
            data_rows.append({
                "type": typ, "model": model, "manufacturer": g("manufacturer"),
                "category": g("category"), "mod_code": g("mod_code"),
                "serial_number": serial,
                "asset_number": asset, "quantity": max(1, qty),
            })
    return {
        "tab": ws.title, "is_summary": is_summary,
        "has_header": header_idx is not None, "rows": data_rows,
    }


def _fallback_clean(typ, model, manufacturer):
    t = _title_case(typ)
    m = _title_case(model)
    name = (f"{t} — {m}".strip(" —")) if (t or m) else "Equipment"
    return {"name": name or "Equipment", "equipment_type": t or "Other",
            "manufacturer": _title_case(manufacturer)}


async def _ai_clean_tuples(tuples: list[dict]) -> dict:
    """Ask the LLM to produce clean {name, equipment_type, manufacturer} per
    distinct tuple. Returns {index: {...}}; falls back deterministically."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    result = {}
    if key and tuples:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            system = (
                "You clean gym/fitness equipment descriptions for a UK MOD asset register. "
                "Input is a JSON list of raw items (often ALL CAPS, terse, sometimes reversed like "
                "'BIKE - (UPRIGHT)'). For EACH item return a grammatically correct, human-readable "
                "record. Rules: 'name' = a natural product name combining the type and model, e.g. "
                "'BIKE - (UPRIGHT)' + 'PRO' -> 'Upright Bike — Pro'; 'SPINNER' + 'D91 GROUP CYCLE' -> "
                "'Spinner — D91 Group Cycle'. 'equipment_type' = a short clean category noun "
                "(e.g. 'Bike', 'Treadmill', 'Rower', 'Cross Trainer', 'Strength'). 'manufacturer' = "
                "correctly cased brand (WATTBIKE->Wattbike, TECHNOGYM->Technogym, CONCEPT 2->Concept 2). "
                "Keep short alphanumeric model codes (D91, DAC73L) uppercase. NEVER invent data; if a "
                "field is blank leave it blank. Respond with STRICT JSON only: "
                '{"items":[{"i":0,"name":"","equipment_type":"","manufacturer":""}]}'
            )
            chat = LlmChat(api_key=key, session_id="kit-clean", system_message=system).with_model(*_MODEL)
            payload = [{"i": i, "type": t["type"], "model": t["model"], "manufacturer": t["manufacturer"]}
                       for i, t in enumerate(tuples)]
            prompt = "Clean these items:\n" + json.dumps(payload)[:12000]
            raw = (await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=_LLM_TIMEOUT)).strip()
            m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()
            i, j = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[i:j + 1]) if i != -1 else {}
            for it in data.get("items", []):
                idx = it.get("i")
                if isinstance(idx, int):
                    result[idx] = {
                        "name": _clean(it.get("name")) or None,
                        "equipment_type": _clean(it.get("equipment_type")) or None,
                        "manufacturer": _clean(it.get("manufacturer")) or None,
                    }
        except Exception as exc:
            logger.warning("[kit-list-ai] LLM clean failed, using fallback: %s", exc)
    # fill any gaps deterministically
    out = {}
    for i, t in enumerate(tuples):
        fb = _fallback_clean(t["type"], t["model"], t["manufacturer"])
        ai = result.get(i) or {}
        out[i] = {
            "name": ai.get("name") or fb["name"],
            "equipment_type": ai.get("equipment_type") or fb["equipment_type"],
            "manufacturer": ai.get("manufacturer") or fb["manufacturer"],
        }
    return out


async def analyse_kit_workbook(content: bytes, filename: str) -> dict:
    """Parse a kit-list workbook into clean, review-ready rows grouped by tab."""
    wb = _read_workbook(content, filename)
    sheets = [_analyse_sheet(ws) for ws in wb.worksheets]

    # distinct (type, model, manufacturer) across DATA sheets → AI clean once
    tuples, tkey = [], {}
    for sh in sheets:
        if sh["is_summary"]:
            continue
        for r in sh["rows"]:
            k = (r["type"].upper(), r["model"].upper(), r["manufacturer"].upper())
            if k not in tkey:
                tkey[k] = len(tuples)
                tuples.append({"type": r["type"], "model": r["model"], "manufacturer": r["manufacturer"]})
    cleaned = await _ai_clean_tuples(tuples)

    out_sheets = []
    for sh in sheets:
        rows = []
        for r in sh["rows"]:
            k = (r["type"].upper(), r["model"].upper(), r["manufacturer"].upper())
            c = cleaned.get(tkey.get(k), {})
            rows.append({
                "name": c.get("name") or _fallback_clean(r["type"], r["model"], r["manufacturer"])["name"],
                "equipment_type": c.get("equipment_type") or "Other",
                "manufacturer": c.get("manufacturer") or "",
                "model": r["model"],
                "serial_number": r["serial_number"],
                "asset_number": r["asset_number"],
                "quantity": r["quantity"],
                "category": _title_case(r["category"], preserve_acronyms=False),
                "mod_code": r.get("mod_code", ""),
                "sub_location": _title_case(sh["tab"]),
            })
        out_sheets.append({
            "tab": sh["tab"],
            "is_summary": sh["is_summary"] or not sh["has_header"],
            "suggested_sub_location": _title_case(sh["tab"]),
            "row_count": len(rows),
            "rows": rows,
        })

    total = sum(len(s["rows"]) for s in out_sheets if not s["is_summary"])
    return {
        "filename": filename,
        "sheet_count": len(out_sheets),
        "importable_rows": total,
        "distinct_items": len(tuples),
        "sheets": out_sheets,
    }
