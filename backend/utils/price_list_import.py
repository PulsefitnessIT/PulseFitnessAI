"""CRM · Master Price List — generalized spreadsheet migration parser.

Originally built for the Pulse Fitness master price-list workbook, this
engine now imports arbitrary, "complicated" supplier/price spreadsheets
from ANY company without losing data:

  • Header detection: keyword-hint first, then a score-based fallback so
    deep / unusual header rows are still found.
  • Identity column: works WITH a product-code column OR WITHOUT one —
    name-only catalogues are supported and a readable SKU is synthesised
    from the product name (so re-imports still match & update).
  • Multiple tables per sheet: repeated header rows are detected and
    skipped instead of being ingested as products.
  • Section bands / blank separators preserved and applied to following
    products.
  • Robust number parsing: currency symbols, thousands separators,
    percentages and accounting negatives "(123)".
  • Per-sheet confidence score so the wizard can flag sheets that need a
    manual check (or an AI re-analysis).

Zero-data-loss: the original file is stored verbatim by the route, and
every non-empty, non-mapped cell is preserved on each product as
``unmapped_fields`` with full provenance (sheet · row · column).
"""
from __future__ import annotations

import io
import re
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter


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

# Column-header text that identifies a product-code column.
_CODE_HINTS = ("product code", "system no", "item code", "sku", "part no",
               "stock code", "item no", "product no", "ref", "code")
_HEADER_HINTS = _CODE_HINTS  # back-compat alias

# Keyword → canonical field for heuristic auto-mapping (a fast first pass;
# the AI suggester refines this). Order matters (first match wins).
_AUTO_MAP_RULES: list[tuple[str, str]] = [
    ("sage", "sage_code"),
    ("product code", "sku"),
    ("stock code", "sku"),
    ("system no", "sku"),
    ("item code", "sku"),
    ("item no", "sku"),
    ("sku", "sku"),
    ("manufacturer part", "manufacturer_part_number"),
    ("supplier part", "supplier_part_number"),
    ("part no", "supplier_part_number"),
    ("description", "description"),
    ("product name", "name"),
    ("item name", "name"),
    ("product", "name"),
    ("model", "model"),
    ("sub category", "sub_category"),
    ("sub-category", "sub_category"),
    ("category", "category"),
    ("family", "product_family"),
    ("manufacturer", "manufacturer"),
    ("brand", "manufacturer"),
    ("supplier", "supplier_name"),
    ("vendor", "supplier_name"),
    ("cost", "cost_price"),
    ("buy price", "cost_price"),
    ("sell", "sell_price"),
    ("retail", "retail_price"),
    ("rrp", "retail_price"),
    ("trade", "trade_price"),
    ("list price", "list_price"),
    ("currency", "currency"),
    ("discount", "discount"),
    ("margin", "margin"),
    ("markup", "margin"),
    ("vat", "tax_rate"),
    ("tax", "tax_rate"),
    ("warranty", "warranty"),
    ("install", "installation_cost"),
    ("delivery", "delivery_cost"),
    ("carriage", "delivery_cost"),
    ("unit", "unit"),
    ("price", "sell_price"),
]

# Keywords that strongly indicate a header (label) cell.
_FIELD_KEYWORDS = tuple(sorted({kw for kw, _ in _AUTO_MAP_RULES} | set(_CODE_HINTS), key=len, reverse=True))


def load_workbook(file_bytes: bytes):
    return openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)


def _cell(ws, r: int, c: int) -> Any:
    return ws.cell(row=r, column=c).value


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _norm(v: Any) -> str:
    return v.strip().lower() if isinstance(v, str) else ""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or ""


# ── Header detection ───────────────────────────────────────────────

def _row_label_score(ws, r: int, max_col: int) -> tuple[float, int]:
    """Score how header-like a row is. Returns (score, non_blank_count)."""
    score = 0.0
    nonblank = 0
    for c in range(1, max_col + 1):
        v = _cell(ws, r, c)
        if _is_blank(v):
            continue
        nonblank += 1
        if isinstance(v, str):
            t = v.strip().lower()
            if any(kw in t for kw in _FIELD_KEYWORDS):
                score += 2.0
            elif 1 <= len(t) <= 40:
                score += 0.5  # short text — label-ish
        else:
            score -= 0.5  # numbers in a header row are a negative signal
    return score, nonblank


def _has_data_below(ws, header_row: int, max_col: int, max_row: int) -> bool:
    """True if rows just below look like data (contain numbers or varied text)."""
    nums = 0
    for r in range(header_row + 1, min(header_row + 8, max_row) + 1):
        for c in range(1, max_col + 1):
            v = _cell(ws, r, c)
            if isinstance(v, (int, float)):
                nums += 1
    return nums >= 1


def _detect_header(ws) -> tuple[int, int, bool]:
    """Return (header_row, code_col, via_hint).

    1. Keyword-hint pass (strong, backward-compatible with Pulse sheets).
    2. Score-based fallback: the most header-like row in the first 40.
    code_col is 0 when no product-code column can be identified.
    """
    max_row = ws.max_row or 1
    max_col = ws.max_column or 1
    limit = min(max_row, 40)

    # 1. hint-based
    for r in range(1, limit + 1):
        for c in range(1, min(max_col, 12) + 1):
            if _norm(_cell(ws, r, c)) in _CODE_HINTS:
                return r, c, True

    # 2. score-based fallback
    best_r, best_score = 1, -1e9
    for r in range(1, limit + 1):
        score, nonblank = _row_label_score(ws, r, max_col)
        if nonblank < 2:
            continue
        if _has_data_below(ws, r, max_col, max_row):
            score += 1.0
        if score > best_score:
            best_score, best_r = score, r
    # try to find a code column in the chosen header row
    code_col = 0
    for c in range(1, max_col + 1):
        if any(h in _norm(_cell(ws, best_r, c)) for h in _CODE_HINTS):
            code_col = c
            break
    return best_r, code_col, False


def detect_header_row(ws) -> tuple[int, int]:
    """Back-compat: (header_row, code_col). code_col may be 0 (no code)."""
    hr, cc, _ = _detect_header(ws)
    return hr, cc


def _detect_band(ws, header_row: int) -> int:
    band = 0
    max_col = ws.max_column or 1
    for up in range(1, 7):
        r = header_row - up
        if r < 1:
            break
        n = sum(1 for c in range(1, max_col + 1)
                if isinstance(_cell(ws, r, c), str) and _cell(ws, r, c).strip() not in ("", "."))
        if n >= 3:
            band = up
        else:
            break
    return band


def column_label(ws, header_row: int, band: int, col: int) -> str:
    parts: list[str] = []
    for r in range(max(1, header_row - band), header_row + 1):
        v = _cell(ws, r, col)
        if isinstance(v, str):
            s = v.strip()
            if s and s != "." and s not in parts:
                parts.append(s)
    return " · ".join(parts)


def _detect_name_col(ws, header_row: int, code_col: int, max_col: int, max_row: int) -> int | None:
    """Pick the most name-like text column (most non-blank longish text in a
    sample), excluding the code column."""
    best_col, best_count = None, 0
    sample_end = min(header_row + 25, max_row)
    for c in range(1, max_col + 1):
        if c == code_col:
            continue
        text_hits = 0
        for r in range(header_row + 1, sample_end + 1):
            v = _cell(ws, r, c)
            if isinstance(v, str) and len(v.strip()) > 3:
                text_hits += 1
        if text_hits > best_count:
            best_count, best_col = text_hits, c
    return best_col


def _is_section_heading(ws, r: int, code_col: int, max_col: int) -> str | None:
    """A row whose code column is blank but which has descriptive text in
    another column is treated as a section heading."""
    if code_col and not _is_blank(_cell(ws, r, code_col)):
        return None
    for c in range(1, min(max_col, 6) + 1):
        v = _cell(ws, r, c)
        if isinstance(v, str) and len(v.strip()) > 2:
            return v.strip()
    return None


def _header_norms(ws, header_row: int, band: int, max_col: int) -> set[str]:
    out: set[str] = set()
    for r in range(max(1, header_row - band), header_row + 1):
        for c in range(1, max_col + 1):
            v = _cell(ws, r, c)
            if isinstance(v, str) and v.strip():
                out.add(v.strip().lower())
    return out


def _row_has_substance(ws, r: int, code_col: int, name_col: int | None, max_col: int) -> bool:
    """True if the row carries product-like content (a name or any number)
    even without a product code — so we don't silently drop it."""
    for c in range(1, max_col + 1):
        if c == code_col:
            continue
        v = _cell(ws, r, c)
        if isinstance(v, (int, float)):
            return True
        if c == name_col and isinstance(v, str) and v.strip():
            return True
    return False


def classify_rows(ws, header_row: int, band: int, code_col: int,
                  name_col: int | None, max_col: int, max_row: int):
    """Yield (kind, row, heading) for every row below the header.

    kind ∈ {"product", "section", "header", "blank"}. Shared by analyze
    (counting) and extract (building) so both agree on what is a product.
    """
    header_norms = _header_norms(ws, header_row, band, max_col)
    header_size = len(header_norms)
    for r in range(header_row + 1, max_row + 1):
        nonblank = [(c, _cell(ws, r, c)) for c in range(1, max_col + 1) if not _is_blank(_cell(ws, r, c))]
        if not nonblank:
            yield ("blank", r, None)
            continue
        # repeated header row (a second stacked table) → skip as data
        norm_set = {str(v).strip().lower() for _, v in nonblank if isinstance(v, str)}
        if header_size >= 3 and norm_set and len(norm_set & header_norms) >= max(2, header_size // 2):
            yield ("header", r, None)
            continue
        if code_col:
            if not _is_blank(_cell(ws, r, code_col)):
                # A lone textual value in the code column (nothing else on the
                # row) is almost always a section banner, not a product.
                if len(nonblank) == 1 and nonblank[0][0] == code_col and isinstance(nonblank[0][1], str):
                    yield ("section", r, str(nonblank[0][1]).strip())
                    continue
                yield ("product", r, None)
                continue
            heading = _is_section_heading(ws, r, code_col, max_col)
            if heading and len(nonblank) <= 2:
                yield ("section", r, heading)
                continue
            if _row_has_substance(ws, r, code_col, name_col, max_col):
                yield ("product", r, None)  # name/price-only row, no code
                continue
            yield ("blank", r, None)
        else:
            # No code column → identity is the name column.
            if len(nonblank) == 1 and isinstance(nonblank[0][1], str):
                yield ("section", r, nonblank[0][1].strip())
                continue
            yield ("product", r, None)


def auto_map(columns: list[dict]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for col in columns:
        label = (col.get("label") or "").lower()
        if not label:
            continue
        for kw, field in _AUTO_MAP_RULES:
            if kw in label and field not in used:
                mapping[col["index"]] = field
                used.add(field)
                break
    return mapping


def _confidence(via_hint: bool, code_col: int, name_col: int | None,
                product_count: int, mapped_count: int) -> int:
    score = 40 if via_hint else 18
    if code_col:
        score += 25
    elif name_col:
        score += 18
    if product_count > 0:
        score += 25
    else:
        score -= 12
    score += min(12, mapped_count * 3)
    return max(0, min(100, score))


def _analyze_one(ws, header_row: int, band: int, code_col: int,
                 name_col: int | None, via_hint: bool) -> dict:
    """Build the per-sheet analysis dict (shared by full analyze + AI re-analyze)."""
    max_col = ws.max_column or 1
    max_row = ws.max_row or 1

    columns = [{
        "index": c,
        "letter": get_column_letter(c),
        "label": column_label(ws, header_row, band, c) or f"Column {get_column_letter(c)}",
    } for c in range(1, max_col + 1)]

    if name_col is None:
        name_col = _detect_name_col(ws, header_row, code_col, max_col, max_row)

    preamble = []
    for r in range(1, max(1, header_row - band)):
        cells = {get_column_letter(c): str(_cell(ws, r, c))
                 for c in range(1, max_col + 1) if not _is_blank(_cell(ws, r, c))}
        if cells:
            preamble.append({"row": r, "cells": cells})

    product_count = 0
    sample = []
    sections: list[dict] = []
    for kind, r, heading in classify_rows(ws, header_row, band, code_col, name_col, max_col, max_row):
        if kind == "section":
            sections.append({"row": r, "heading": heading})
        elif kind == "product":
            product_count += 1
            if len(sample) < 6:
                row_cells = {}
                for col in columns:
                    v = _cell(ws, r, col["index"])
                    if not _is_blank(v):
                        row_cells[col["label"]] = str(v)
                code_val = _cell(ws, r, code_col) if code_col else None
                name_val = _cell(ws, r, name_col) if name_col else None
                sample.append({
                    "row": r,
                    "code": str(code_val) if not _is_blank(code_val) else "",
                    "name": str(name_val) if not _is_blank(name_val) else "",
                    "cells": row_cells,
                })

    mapping = auto_map(columns)
    warnings: list[str] = []
    if not code_col:
        warnings.append("No product-code column detected — a SKU will be generated from each product name.")
    if product_count == 0:
        warnings.append("No product rows detected — check the header row, or use AI auto-detect.")

    return {
        "name": ws.title,
        "max_row": max_row,
        "max_col": max_col,
        "header_row": header_row,
        "header_band": band,
        "code_col": code_col,
        "name_col": name_col,
        "id_col": code_col or name_col or 0,
        "has_code": bool(code_col),
        "columns": columns,
        "auto_mapping": {str(k): v for k, v in mapping.items()},
        "preamble": preamble[:60],
        "section_headings": sections[:200],
        "product_count": product_count,
        "sample": sample,
        "confidence": _confidence(via_hint, code_col, name_col, product_count, len(mapping)),
        "warnings": warnings,
    }


def analyze_workbook(file_bytes: bytes) -> dict:
    """Parse structure of every worksheet for the import wizard."""
    wb = load_workbook(file_bytes)
    sheets = []
    for ws in wb.worksheets:
        if (ws.max_row or 0) < 1 or (ws.max_column or 0) < 1:
            continue
        header_row, code_col, via_hint = _detect_header(ws)
        band = _detect_band(ws, header_row)
        sheets.append(_analyze_one(ws, header_row, band, code_col, None, via_hint))
    wb.close()
    return {"sheets": sheets}


def analyze_sheet(wb, sheet_name: str, *, header_row: int, header_band: int | None = None,
                  code_col: int = 0, name_col: int | None = None) -> dict:
    """Re-analyze ONE sheet with explicit structure overrides (used by the
    AI auto-detect fallback). Returns the same per-sheet shape as analyze."""
    ws = wb[sheet_name]
    band = _detect_band(ws, header_row) if header_band is None else int(header_band)
    return _analyze_one(ws, int(header_row), band, int(code_col or 0),
                        int(name_col) if name_col else None, via_hint=False)


# ── Number coercion ────────────────────────────────────────────────

def _coerce_number(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")  # accounting negative
    if neg:
        s = s[1:-1]
    s = s.replace(",", "")  # thousands separators
    s2 = re.sub(r"[^0-9.\-]", "", s)
    if s2 in ("", "-", ".", "--"):
        return None
    try:
        n = float(s2)
    except ValueError:
        return None
    if neg:
        n = -abs(n)
    return n


# ── Extraction ─────────────────────────────────────────────────────

def extract_products(file_bytes: bytes, sheet_cfg: dict) -> list[dict]:
    """Thin wrapper: load workbook then extract one sheet (used by tests)."""
    return extract_products_from_wb(load_workbook(file_bytes), sheet_cfg)


def extract_products_from_wb(wb, sheet_cfg: dict) -> list[dict]:
    """Extract structured product rows for ONE sheet from a loaded workbook.

    sheet_cfg = {
      name, header_row, header_band, code_col (0 if none), name_col,
      mappings: { "<col_index>": "<canonical_field>" }
    }
    Returns product dicts with mapped fields + ``unmapped_fields`` (every
    non-empty, non-mapped cell) + ``source_*`` provenance + ``section``.
    SKUs are synthesised from the product name when there is no code column.
    """
    ws = wb[sheet_cfg["name"]]
    header_row = int(sheet_cfg["header_row"])
    band = int(sheet_cfg.get("header_band", 0))
    code_col = int(sheet_cfg.get("code_col") or 0)
    name_col = sheet_cfg.get("name_col")
    name_col = int(name_col) if name_col else None
    max_col = ws.max_column or 1
    max_row = ws.max_row or 1
    mappings = {int(k): v for k, v in (sheet_cfg.get("mappings") or {}).items() if v}

    labels = {c: column_label(ws, header_row, band, c) or f"Column {get_column_letter(c)}"
              for c in range(1, max_col + 1)}

    products: list[dict] = []
    current_section = ""
    synth_seen: dict[str, int] = {}
    for kind, r, heading in classify_rows(ws, header_row, band, code_col, name_col, max_col, max_row):
        if kind == "section":
            current_section = heading or current_section
            continue
        if kind != "product":
            continue

        prod: dict[str, Any] = {
            "source_sheet": ws.title,
            "source_row": r,
            "section": current_section,
            "unmapped_fields": [],
        }
        # resolve name early (used for SKU synthesis)
        name_val = _cell(ws, r, name_col) if name_col else None
        if name_val is not None and not _is_blank(name_val):
            prod["name"] = str(name_val).strip()

        code = _cell(ws, r, code_col) if code_col else None
        if code_col and not _is_blank(code):
            prod["sku"] = str(code).strip()

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

        # Default human-readable name.
        if not prod.get("name"):
            prod["name"] = prod.get("description") or (current_section and f"{current_section} — {prod.get('sku', '')}".strip(" —")) or prod.get("sku", "")

        # Synthesise a stable, readable SKU when the sheet has no code.
        if not prod.get("sku"):
            base = _slug(prod.get("name", "")) or f"row-{r}"
            # disambiguate repeated names within the sheet so distinct
            # products don't silently merge on commit.
            n = synth_seen.get(base, 0)
            synth_seen[base] = n + 1
            prod["sku"] = base if n == 0 else f"{base}-{n + 1}"
            prod["sku_synthesized"] = True

        prod["unmapped_fields"] = prod["unmapped_fields"][:120]
        products.append(prod)
    return products
