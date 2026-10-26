"""Shared spreadsheet importer helpers — iter 216h108.

Used by `routes/master_admin_bulk_import.py` and the new customer
`routes/equipment.py:/equipment/bulk-import` endpoint so both surfaces
parse uploads identically.

Two responsibilities:

1. **`iter_rows(file_bytes, filename)`** — yield `dict` rows from either
   a CSV or an .xlsx file. Detection is by file extension. The XLSX
   path uses openpyxl (already in requirements via reportlab adjacent
   tooling, see check below). Empty trailing rows are skipped.

2. **`parse_date_cell(value)`** — coerce a cell value to ``YYYY-MM-DD``
   regardless of how the source represented the date:
   - Excel serial number (int or float — 45979 → 2025-11-08)
   - ISO 8601 (``2024-01-15``)
   - dd/mm/yyyy or mm/dd/yyyy (UK preferred — assumed dd/mm/yyyy when
     ambiguous because we ship UK gym software)
   - dd-mm-yyyy, dd.mm.yyyy
   - long-form ``"15 Jan 2024"`` or ``"January 15 2024"``
   Returns ``""`` for blank / unparseable values so the caller can
   decide whether to surface the row as an error.

User regression (iter 216h108): Pulse Fitness uploaded an .xlsx with
warranty/contract dates stored as Excel serial numbers (45979) and our
importer was saving the strings verbatim, breaking every UI date pill
with "Invalid Date". This module is the single fix.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timedelta
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ── Date parsing ──────────────────────────────────────────────────────

# Excel anchor — Windows-Excel treats 1900 as a leap year, so the
# correct anchor for serial 1 = 1900-01-01 is the date 1899-12-30
# (this matches openpyxl's own conversion). We deliberately don't
# import openpyxl.utils.datetime to keep the helper usable when the
# upload is CSV (no openpyxl import on the hot path).
_EXCEL_ANCHOR = datetime(1899, 12, 30)

# Serial-number sanity window. Anything outside this would either
# pre-date the platform (we don't support warranties from 1970) or be
# centuries in the future. Keeps a stray "10" or "9999" from being
# mistaken for a date.
_SERIAL_MIN = 1   # 1900-01-01
_SERIAL_MAX = 80000  # 2119

# Slash-separated formats. Order matters — try dd/mm before mm/dd
# because we ship UK gym software.
_SLASH_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y")
_DASH_FORMATS = ("%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%m-%d-%Y")
_DOT_FORMATS = ("%d.%m.%Y", "%d.%m.%y")
_LONG_FORMATS = (
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y",
    "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
)


def parse_date_cell(value) -> str:
    """Coerce arbitrary cell input to an ISO ``YYYY-MM-DD`` date.

    Returns ``""`` for empty/None/unparseable values so the caller can
    decide whether that's a hard error or a tolerable omission.
    """
    if value is None:
        return ""
    # openpyxl hands us real datetime objects when the cell is a date.
    if isinstance(value, datetime):
        return value.date().isoformat()
    # Numeric — treat as Excel serial.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _from_excel_serial(value)
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null", "0", "0.0"):
        return ""
    # Numeric string?
    try:
        num = float(s)
        if num.is_integer() and _SERIAL_MIN <= num <= _SERIAL_MAX:
            return _from_excel_serial(int(num))
    except ValueError:
        pass
    # Try every known format.
    for fmt in _SLASH_FORMATS + _DASH_FORMATS + _DOT_FORMATS + _LONG_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # Last resort — strip out anything funky and retry ISO.
    s2 = re.sub(r"[^0-9\-/.: ]", "", s).strip()
    if s2 and s2 != s:
        return parse_date_cell(s2)
    return ""


def _from_excel_serial(serial: int | float) -> str:
    """Convert a Windows-Excel serial number to ISO date."""
    try:
        s = float(serial)
    except (TypeError, ValueError):
        return ""
    if not (_SERIAL_MIN <= s <= _SERIAL_MAX):
        return ""
    # Excel's 1900-leap-year bug: serials >= 60 are shifted by one day
    # because Excel pretends Feb 29 1900 exists. _EXCEL_ANCHOR is
    # 1899-12-30 which compensates for that — we get a correct
    # date for any modern serial without a special case.
    dt = _EXCEL_ANCHOR + timedelta(days=s)
    return dt.date().isoformat()


# ── Row iteration (CSV + XLSX) ────────────────────────────────────────

def _normalise_xlsx_value(v):
    """Convert openpyxl-returned values to strings the rest of the
    parser expects, but PRESERVE datetimes and numerics so
    ``parse_date_cell`` can handle them natively."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return str(v).strip()


def _iter_xlsx(content: bytes) -> Iterable[dict]:
    """Stream rows from an .xlsx file as dicts keyed by header row."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover — should always be installed
        raise RuntimeError("openpyxl is not available — install it to import .xlsx files") from exc
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return
    headers = [str(h).strip() if h is not None else "" for h in header]
    if not any(headers):
        return
    for raw in rows_iter:
        cells = list(raw) + [None] * (len(headers) - len(raw))
        row = {headers[i]: _normalise_xlsx_value(cells[i]) for i in range(len(headers)) if headers[i]}
        if any(str(v).strip() for v in row.values() if v not in (None, "")):
            yield row


def _iter_csv(content: bytes) -> Iterable[dict]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    yield from reader


def iter_rows(content: bytes, filename: str) -> Iterable[dict]:
    """Yield row-dicts from either a CSV or .xlsx file.

    Branching is by extension — the upload validator already restricts
    to MIME_SPREADSHEETS so we know the content is one of the two.
    """
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        yield from _iter_xlsx(content)
    else:
        yield from _iter_csv(content)


# ── Header alias normaliser ───────────────────────────────────────────

# Many real-world templates use different column names for the same
# field. Map common aliases to the canonical key the importer expects.
# Match is case-insensitive.
HEADER_ALIASES: dict[str, list[str]] = {
    # equipment
    "name":              ["name", "machine name", "equipment name", "asset name", "description"],
    "equipment_type":    ["equipment_type", "type", "category", "equipment type", "asset type"],
    "manufacturer":      ["manufacturer", "make", "brand", "oem"],
    "model":             ["model", "model number", "model_no"],
    "serial_number":     ["serial_number", "serial", "serial number", "sn", "asset tag", "asset_tag"],
    "purchase_date":     ["purchase_date", "purchase date", "purchase", "install date", "install_date", "installation date", "installation_date"],
    "warranty_expiry":   ["warranty_expiry", "warranty expiry", "warranty expiry date", "manufacturer warranty expiry date", "warranty end", "warranty_end", "warranty"],
    "service_provider":  ["service_provider", "service provider"],
    "supplier":          ["supplier", "supplier name"],
    "site_name":         ["site_name", "site name", "site", "location name"],
    "location":          ["location", "location description", "room", "zone", "bay"],
    "sub_location":      ["sub_location", "sublocation description", "sub location", "sublocation", "sub location description"],
    "unit_price":        ["unit_price", "unit price", "price", "cost", "purchase price", "purchase_price"],
    "length":            ["length", "length (m)", "length_m"],
    "width":             ["width",  "width (m)", "width_m"],
    "height":            ["height", "height (m)", "height_m"],
    "notes":             ["notes", "comments", "remark", "description (notes)"],
    "customer_account_number": [
        "customer_account_number", "customer account number", "account number",
        "account code", "customer code", "sage customer number", "sicon customer number",
    ],
    "invoice_customer_ref": [
        "invoice_customer_ref", "invoice customer ref", "sicon customer ref",
        "customer ref", "customer reference",
    ],
    "contract_start":    ["contract_start", "contract start", "contract start date"],
    "contract_end":      ["contract_end", "contract end", "contract end date"],
    "contract_number":   ["contract_number", "contract number", "contract code"],
    # Sicon Service template-only columns
    "install_date":      ["install_date", "install date", "installation date", "installation_date"],
    "last_service_date": ["last_service_date", "last service date", "last service", "last serviced"],
    "service_interval":  ["service_interval", "service interval"],
    "service_period":    ["service_period", "service period"],
    "next_service_date": ["next_service_date", "next service date", "next service", "next service due"],
    "supplier_reference": ["supplier_reference", "supplier reference", "supplier ref"],
    "contract_line_no":  ["contract_line_no", "contract line no", "contract line", "contract line number"],
    "sla_name":          ["sla_name", "sla name"],
    "stock_item_code":   ["stock_item_code", "stock item code", "stock code", "item code"],
    "id_number":         ["id_number", "id number", "id no"],
    "service_template":  ["service_template", "service template"],
    "equipment_group":   ["equipment_group", "equipment group"],
    "sicon_customer_ref": ["sicon_customer_ref", "sicon customer ref"],
    # Iter 216h111 — MOD Force tag (Army / RAF / Navy)
    "mod_force":         ["mod_force", "mod-force", "mod force", "force", "service", "mod service", "mod_service", "command", "service branch", "branch of service"],
}


_FORCE_ALIASES = {
    "army":   {"army", "british army", "land forces", "ba", "a"},
    "raf":    {"raf", "royal air force", "air force", "r.a.f"},
    "navy":   {"navy", "royal navy", "rn", "r.n", "sea"},
}


def parse_force(value) -> str:
    """Coerce a free-text Force/Service value to one of
    ``army`` / ``raf`` / ``navy`` (or ``""`` if blank/unknown)."""
    if value is None:
        return ""
    v = str(value).strip().lower()
    if not v:
        return ""
    for canonical, aliases in _FORCE_ALIASES.items():
        if v in aliases:
            return canonical
    return ""


def normalise_row(row: dict) -> dict:
    """Lower-cases header aliases and returns a dict keyed by canonical names.

    Unknown columns are kept under their original lower-cased key so
    downstream code can still inspect them if needed.
    """
    by_lower = {(k or "").strip().lower(): v for k, v in row.items() if k is not None}
    out: dict = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for a in aliases:
            v = by_lower.get(a.lower())
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
            if v == "":
                continue
            out[canonical] = v
            break
    # Preserve unknown columns (lower-cased) for inspection.
    for k, v in by_lower.items():
        if k not in out and k:
            out.setdefault(k, v)
    return out


def get_pick(row: dict, canonical: str, default=None):
    """Return the value for a canonical column from an already-normalised row.

    Convenience wrapper for callers that don't want to call
    ``normalise_row`` (e.g. the master-admin importer that still uses
    the raw row dict). Tries canonical, then every alias.
    """
    if canonical in row:
        return row[canonical]
    for a in HEADER_ALIASES.get(canonical, []):
        for k in row:
            if (k or "").strip().lower() == a.lower():
                return row[k]
    return default
