"""CRM · Master Price List — spreadsheet migration parser (Phase 1).

Reads the Pulse Fitness master price-list workbook (a hand-built
cost-engineering spreadsheet: multi-row headers, exchange-rate metadata,
section-heading blocks, blank separators, USD component-cost columns) and
turns it into structured product rows WITHOUT losing any data.

Zero-data-loss strategy:
  1. The original uploaded file is stored verbatim (see route) for
     bulletproof recovery.
  2. Each detected product row captures EVERY non-empty cell, keyed by a
     composite column label built from the multi-row header band. Cells
     that aren't mapped to a canonical CRM field are preserved on the
     product as ``unmapped_fields`` (label · value · sheet · row · column).
  3. Rows above the header (exchange rates, notes) and section headings
     are preserved on the import record so nothing on the sheet is dropped.

Nothing here writes to the database — it only parses. The route owns
persistence, versioning and audit.
"""
from __future__ import annotations

import io
import re
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter


# Canonical CRM fields a spreadsheet column can be mapped to. ``None``
# (or absence) means the column is preserved as unmapped imported data.
CANONICAL_FIELDS: list[dict[str, str]] = [
    {"key": "sku", "label": "Product code / SKU"},
    {"key": "sage_code", "label": "Sage item code"},
    {"key": "name", "label": "Product name"},
    {"key": "description", "label": "Description"},
    {"key": "model", "label": "Model"},
    {"key": "category", "label": "Category"},
    {"key": "sub_category", "label": "Sub-category"},
    {"key": "product_family", "label": "Product family"},
    {"key": "supplier_name", "label": "Supplier"},
    {"key": "manufacturer", "label": "Manufacturer"},
    {"key": "supplier_part_number", "label": "Supplier part no."},
    {"key": "manufacturer_part_number", "label": "Manufacturer part no."},
    {"key": "cost_price", "label": "Cost price"},
    {"key": "sell_price", "label": "Sell price"},
    {"key": "retail_price", "label": "Retail price"},
    {"key": "trade_price", "label": "Trade price"},
    {"key": "list_price", "label": "List price"},
    {"key": "currency", "label": "Currency"},
    {"key": "discount", "label": "Discount"},
    {"key": "margin", "label": "Margin %"},
    {"key": "tax_rate", "label": "VAT / tax rate"},
    {"key": "unit", "label": "Unit"},
    {"key": "warranty", "label": "Warranty"},
    {"key": "installation_cost", "label": "Installation cost"},
    {"key": "delivery_cost", "label": "Delivery cost"},
    {"key": "compatibility", "label": "Compatibility"},
    {"key": "internal_notes", "label": "Internal notes"},
    {"key": "customer_notes", "label": "Customer-facing notes"},
    {"key": "status", "label": "Status"},
    {"key": "effective_date", "label": "Effective date"},
]

NUMERIC_FIELDS = {
    "cost_price", "sell_price", "retail_price", "trade_price", "list_price",
    "discount", "margin", "tax_rate", "installation_cost", "delivery_cost",
}

_HEADER_HINTS = ("product code", "system no", "item code", "sku", "code", "part no")

# Keyword → canonical field for heuristic auto-mapping (used as a fast
# first pass; the AI suggester refines this).
_AUTO_MAP_RULES: list[tuple[str, str]] = [
    ("sage", "sage_code"),
    ("product code", "sku"),
    ("system no", "sku"),
    ("sku", "sku"),
    ("part no", "supplier_part_number"),
    ("description", "description"),
    ("product name", "name"),
    ("model", "model"),
    ("sub category", "sub_category"),
    ("sub-category", "sub_category"),
    ("category", "category"),
    ("family", "product_family"),
    ("manufacturer", "manufacturer"),
    ("supplier", "supplier_name"),
    ("cost", "cost_price"),
    ("sell", "sell_price"),
    ("retail", "retail_price"),
    ("trade", "trade_price"),
    ("list price", "list_price"),
    ("rrp", "retail_price"),
    ("currency", "currency"),
    ("discount", "discount"),
    ("margin", "margin"),
    ("vat", "tax_rate"),
    ("tax", "tax_rate"),
    ("warranty", "warranty"),
    ("install", "installation_cost"),
    ("delivery", "delivery_cost"),
    ("unit", "unit"),
]


def load_workbook(file_bytes: bytes):
    return openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)


def _cell(ws, r: int, c: int) -> Any:
    return ws.cell(row=r, column=c).value


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def detect_header_row(ws) -> tuple[int, int]:
    """Return (header_row, code_col). Scans the first 40 rows for a cell
    matching a known code-column hint; falls back to the row with the
    most distinct text labels."""
    limit = min(ws.max_row, 40)
    for r in range(1, limit + 1):
        for c in range(1, min(ws.max_column, 10) + 1):
            v = _cell(ws, r, c)
            if isinstance(v, str) and v.strip().lower() in _HEADER_HINTS:
                return r, c
    best = (1, 0)
    for r in range(1, min(ws.max_row, 30) + 1):
        n = sum(1 for c in range(1, ws.max_column + 1) if isinstance(_cell(ws, r, c), str) and _cell(ws, r, c).strip())
        if n > best[1]:
            best = (r, n)
    return best[0], 1


def _detect_band(ws, header_row: int) -> int:
    """How many rows above the header carry column labels (multi-row
    header band). Looks for a contiguous run of rows above header_row
    that have >=3 text cells. Capped at 6."""
    band = 0
    for up in range(1, 7):
        r = header_row - up
        if r < 1:
            break
        n = sum(1 for c in range(1, ws.max_column + 1) if isinstance(_cell(ws, r, c), str) and _cell(ws, r, c).strip() not in ("", "."))
        if n >= 3:
            band = up
        else:
            break
    return band


def column_label(ws, header_row: int, band: int, col: int) -> str:
    """Composite label from the header band + header row for one column."""
    parts: list[str] = []
    for r in range(max(1, header_row - band), header_row + 1):
        v = _cell(ws, r, col)
        if isinstance(v, str):
            s = v.strip()
            if s and s != "." and s not in parts:
                parts.append(s)
    return " · ".join(parts)


def _is_section_heading(ws, r: int, code_col: int, max_col: int) -> str | None:
    """A row whose code column is blank but which has descriptive text in
    another column is treated as a section heading (preserved + applied
    to the products that follow)."""
    if not _is_blank(_cell(ws, r, code_col)):
        return None
    for c in range(1, min(max_col, 6) + 1):
        v = _cell(ws, r, c)
        if isinstance(v, str) and len(v.strip()) > 2:
            return v.strip()
    return None


def auto_map(columns: list[dict]) -> dict[int, str]:
    """Heuristic column→field guess by keyword. Returns {col_index: field_key}."""
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for col in columns:
        label = (col.get("label") or "").lower()
        if not label:
            continue
        for kw, field in _AUTO_MAP_RULES:
            if kw in label and field not in used:
                # name vs description: prefer the code column to sku
                mapping[col["index"]] = field
                used.add(field)
                break
    return mapping


def analyze_workbook(file_bytes: bytes) -> dict:
    """Parse structure of every worksheet for the import wizard."""
    wb = load_workbook(file_bytes)
    sheets = []
    for ws in wb.worksheets:
        max_col = ws.max_column or 1
        max_row = ws.max_row or 1
        header_row, code_col = detect_header_row(ws)
        band = _detect_band(ws, header_row)
        columns = []
        for c in range(1, max_col + 1):
            columns.append({
                "index": c,
                "letter": get_column_letter(c),
                "label": column_label(ws, header_row, band, c) or f"Column {get_column_letter(c)}",
            })
        # name col: first text column that isn't the code col (usually col 2)
        name_col = None
        for c in range(1, max_col + 1):
            if c == code_col:
                continue
            # sample a few product rows for text
            vals = [_cell(ws, r, c) for r in range(header_row + 1, min(header_row + 12, max_row) + 1)]
            if any(isinstance(v, str) and len(v.strip()) > 3 for v in vals):
                name_col = c
                break
        # preamble rows (above header band) — preserved verbatim
        preamble = []
        for r in range(1, max(1, header_row - band)):
            cells = {get_column_letter(c): str(_cell(ws, r, c)) for c in range(1, max_col + 1) if not _is_blank(_cell(ws, r, c))}
            if cells:
                preamble.append({"row": r, "cells": cells})
        # product count + sample + section headings
        product_count = 0
        sample = []
        sections: list[dict] = []
        for r in range(header_row + 1, max_row + 1):
            code = _cell(ws, r, code_col)
            if _is_blank(code):
                heading = _is_section_heading(ws, r, code_col, max_col)
                if heading:
                    sections.append({"row": r, "heading": heading})
                continue
            product_count += 1
            if len(sample) < 6:
                row_cells = {}
                for col in columns:
                    v = _cell(ws, r, col["index"])
                    if not _is_blank(v):
                        row_cells[col["label"]] = str(v)
                sample.append({
                    "row": r,
                    "code": str(code),
                    "name": str(_cell(ws, r, name_col)) if name_col and not _is_blank(_cell(ws, r, name_col)) else "",
                    "cells": row_cells,
                })
        sheets.append({
            "name": ws.title,
            "max_row": max_row,
            "max_col": max_col,
            "header_row": header_row,
            "header_band": band,
            "code_col": code_col,
            "name_col": name_col,
            "columns": columns,
            "auto_mapping": {str(k): v for k, v in auto_map(columns).items()},
            "preamble": preamble[:60],
            "section_headings": sections[:200],
            "product_count": product_count,
            "sample": sample,
        })
    wb.close()
    return {"sheets": sheets}


def _coerce_number(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_products(file_bytes: bytes, sheet_cfg: dict) -> list[dict]:
    """Extract structured product rows for ONE sheet given a mapping cfg.

    sheet_cfg = {
      name, header_row, header_band, code_col, name_col,
      mappings: { "<col_index>": "<canonical_field>" }
    }
    Returns a list of product dicts with mapped fields + ``unmapped_fields``
    (every non-empty, non-mapped cell) + ``source_*`` provenance + ``section``.
    """
    wb = load_workbook(file_bytes)
    ws = wb[sheet_cfg["name"]]
    header_row = int(sheet_cfg["header_row"])
    band = int(sheet_cfg.get("header_band", 0))
    code_col = int(sheet_cfg["code_col"])
    name_col = sheet_cfg.get("name_col")
    name_col = int(name_col) if name_col else None
    max_col = ws.max_column or 1
    max_row = ws.max_row or 1
    mappings = {int(k): v for k, v in (sheet_cfg.get("mappings") or {}).items() if v}

    # Pre-compute labels per column.
    labels = {c: column_label(ws, header_row, band, c) or f"Column {get_column_letter(c)}" for c in range(1, max_col + 1)}

    products: list[dict] = []
    current_section = ""
    for r in range(header_row + 1, max_row + 1):
        code = _cell(ws, r, code_col)
        if _is_blank(code):
            heading = _is_section_heading(ws, r, code_col, max_col)
            if heading:
                current_section = heading
            continue
        prod: dict[str, Any] = {
            "source_sheet": ws.title,
            "source_row": r,
            "section": current_section,
            "unmapped_fields": [],
        }
        # code col always becomes sku (+ keep its mapping if provided)
        prod["sku"] = str(code).strip()
        if name_col and not _is_blank(_cell(ws, r, name_col)):
            prod.setdefault("name", str(_cell(ws, r, name_col)).strip())
        for c in range(1, max_col + 1):
            v = _cell(ws, r, c)
            if _is_blank(v):
                continue
            field = mappings.get(c)
            if c == code_col and not field:
                field = "sku"
            if c == name_col and not field:
                field = "name"
            if field:
                if field in NUMERIC_FIELDS:
                    num = _coerce_number(v)
                    if num is not None:
                        prod[field] = num
                else:
                    prod[field] = str(v).strip()
            else:
                prod["unmapped_fields"].append({
                    "column": labels.get(c, get_column_letter(c)),
                    "letter": get_column_letter(c),
                    "value": str(v).strip(),
                })
        # default human name when no name column mapped
        if not prod.get("name"):
            prod["name"] = prod.get("description") or (current_section and f"{current_section} — {prod['sku']}") or prod["sku"]
        prod["unmapped_fields"] = prod["unmapped_fields"][:120]
        products.append(prod)
    wb.close()
    return products
