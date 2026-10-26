"""Sicon equipment template — the single equipment import format.

Every equipment template download serves these exact Sicon Service columns,
and every equipment importer understands them (old Pulse formats still read).
Also owns the "asset completeness" rules (Sicon essentials) used by the
Missing Information grid and the MOD engineer app.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

SICON_EQUIPMENT_HEADERS = [
    "Sicon Customer Ref", "Location Description", "Sublocation Description",
    "Supplier Reference", "Supplier Name", "Contract Number", "Contract Line No",
    "SLA Name", "Stock Item Code", "Description", "Make", "Model", "Serial Number",
    "Install Date", "Manufacturer Warranty Expiry Date", "Last Service Date",
    "Service Interval", "Service Period", "Next Service Date", "ID Number",
    "Service Template", "Equipment Group", "service_provider", "unit_price",
    "replacement_cost", "length", "width", "height", "MOD-Force",
]

# Sicon header → Pulse canonical field.
SICON_TO_CANONICAL = {
    "Sicon Customer Ref": "sicon_customer_ref",
    "Location Description": "location",
    "Sublocation Description": "sub_location",
    "Supplier Reference": "supplier_reference",
    "Supplier Name": "supplier",
    "Contract Number": "contract_number",
    "Contract Line No": "contract_line_no",
    "SLA Name": "sla_name",
    "Stock Item Code": "stock_item_code",
    "Description": "name",
    "Make": "manufacturer",
    "Model": "model",
    "Serial Number": "serial_number",
    "Install Date": "install_date",
    "Manufacturer Warranty Expiry Date": "warranty_expiry",
    "Last Service Date": "last_service_date",
    "Service Interval": "service_interval",
    "Service Period": "service_period",
    "Next Service Date": "next_service_date",
    "ID Number": "id_number",
    "Service Template": "service_template",
    "Equipment Group": "equipment_group",
    "service_provider": "service_provider",
    "unit_price": "unit_price",
    "replacement_cost": "replacement_cost",
    "length": "length", "width": "width", "height": "height",
    "MOD-Force": "mod_force",
}

_GUIDE = {
    "Sicon Customer Ref": ("Essential", "Customer / site account number (matches the site's account number in Pulse)"),
    "Location Description": ("Essential", "Area of the site, e.g. Main Gym, Cardio Mezzanine"),
    "Sublocation Description": ("Optional", "Room / zone / bay within the location"),
    "Description": ("Essential", "Asset description, e.g. Treadmill — Bay 3"),
    "Make": ("Essential", "Manufacturer, e.g. Life Fitness"),
    "Model": ("Essential", "Model, e.g. 95T Discover SE3"),
    "Serial Number": ("Essential", "Unique serial — used to match existing assets on re-import"),
    "Install Date": ("Optional", "DD/MM/YYYY"),
    "Manufacturer Warranty Expiry Date": ("Optional", "DD/MM/YYYY"),
    "Last Service Date": ("Optional", "DD/MM/YYYY"),
    "Service Interval": ("Optional", "Whole number, e.g. 6"),
    "Service Period": ("Optional", "Days, Weeks, Months or Years"),
    "Next Service Date": ("Optional", "DD/MM/YYYY — worked out from Last Service + Interval if blank"),
    "MOD-Force": ("MOD only", "Army, RAF or Navy"),
}

# Extra Sicon-only fields stored on db.equipment.
SICON_EXTRA_FIELDS = (
    "sicon_customer_ref", "supplier_reference", "contract_line_no", "sla_name",
    "stock_item_code", "install_date", "last_service_date", "service_interval",
    "service_period", "next_service_date", "id_number", "service_template",
    "equipment_group",
)
_DATE_FIELDS = {"install_date", "last_service_date", "next_service_date", "warranty_expiry"}

ESSENTIAL_FIELDS = [
    ("sicon_customer_ref", "Customer Ref"),
    ("location", "Location"),
    ("name", "Description"),
    ("manufacturer", "Make"),
    ("model", "Model"),
    ("serial_number", "Serial Number"),
]

# Fields that can be filled in from the Missing Information grid.
EDITABLE_FIELDS = (
    "sicon_customer_ref", "location", "sub_location", "name", "manufacturer", "model",
    "serial_number", "install_date", "warranty_expiry", "last_service_date",
    "service_interval", "service_period", "next_service_date", "id_number",
    "equipment_group", "stock_item_code", "supplier_reference", "contract_number",
    "contract_line_no", "sla_name", "service_template",
)
# Subset the field engineer may capture on site.
ENGINEER_EDITABLE_FIELDS = (
    "location", "sub_location", "name", "manufacturer", "model", "serial_number",
    "install_date", "last_service_date", "id_number",
)

_PLACEHOLDER = {"", "UNKNOWN", "N/A", "NA", "TBC", "TBD", "NONE", "-", "0", "NULL"}
_PERIODS = {"day": "Days", "week": "Weeks", "month": "Months", "year": "Years"}


def _lower_map(row: dict) -> dict:
    return {(k or "").strip().lower(): v for k, v in row.items() if k}


def is_sicon_row(row: dict) -> bool:
    keys = set(_lower_map(row))
    hits = sum(1 for h in SICON_EQUIPMENT_HEADERS if h.lower() in keys)
    return hits >= 3 and ("make" in keys or "description" in keys or "serial number" in keys)


def sicon_values(row: dict) -> dict:
    """Canonical-keyed values from a Sicon-headed row (blank cells dropped)."""
    low = _lower_map(row)
    out = {}
    for hdr, canon in SICON_TO_CANONICAL.items():
        v = low.get(hdr.lower())
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        out[canon] = v.strip() if isinstance(v, str) else v
    return out


def adapt_row(row: dict, target: dict) -> dict:
    """Copy Sicon values into an importer's own header names
    (``target`` = canonical → importer header). No-op for non-Sicon rows."""
    if not is_sicon_row(row):
        return row
    vals = sicon_values(row)
    for canon, hdr in target.items():
        if canon in vals and not str(row.get(hdr) or "").strip():
            row[hdr] = vals[canon] if not hasattr(vals[canon], "isoformat") else vals[canon].isoformat()[:10]
    return row


def normalise_period(v) -> str:
    s = str(v or "").strip().lower().rstrip("s")
    for k, label in _PERIODS.items():
        if s.startswith(k[:3]) or s == k[0]:
            return label
    return ""


def _parse_int(v):
    try:
        n = int(float(str(v).strip()))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def compute_next_service(last_iso: str, interval, period: str) -> str:
    if not last_iso or not interval or not period:
        return ""
    try:
        from dateutil.relativedelta import relativedelta
        d = date.fromisoformat(str(last_iso)[:10])
    except Exception:
        return ""
    n = _parse_int(interval)
    if not n:
        return ""
    delta = {"Days": relativedelta(days=n), "Weeks": relativedelta(weeks=n),
             "Months": relativedelta(months=n), "Years": relativedelta(years=n)}.get(period)
    return (d + delta).isoformat() if delta else ""


def clean_value(field: str, value):
    """Normalise one user-entered value for storage."""
    from utils.spreadsheet_import import parse_date_cell
    if value is None:
        return None
    if field in _DATE_FIELDS:
        return parse_date_cell(value) or None
    if field == "service_interval":
        return _parse_int(value)
    if field == "service_period":
        return normalise_period(value) or None
    s = str(value).strip()
    return s or None


def sicon_extra_fields(row: dict) -> dict:
    """Extract the Sicon-only fields from ANY row (Sicon or alias headers)."""
    from utils.spreadsheet_import import get_pick
    out = {}
    for f in SICON_EXTRA_FIELDS:
        v = get_pick(row, f)
        if v is None and f == "sicon_customer_ref":
            v = get_pick(row, "invoice_customer_ref")
        out[f] = clean_value(f, v) if v not in (None, "") else None
    if not out.get("next_service_date"):
        out["next_service_date"] = compute_next_service(
            out.get("last_service_date"), out.get("service_interval"), out.get("service_period")) or None
        out["next_service_auto"] = bool(out["next_service_date"])
    return out


def with_next_service(doc: dict, patch: dict) -> dict:
    """Derive Next Service Date (Last Service + Interval) unless the user set one."""
    if patch.get("next_service_date"):
        patch["next_service_auto"] = False
        return patch
    merged = {**doc, **patch}
    if merged.get("next_service_date") and not doc.get("next_service_auto"):
        return patch
    nxt = compute_next_service(merged.get("last_service_date"), merged.get("service_interval"), merged.get("service_period"))
    if nxt:
        patch["next_service_date"] = nxt
        patch["next_service_auto"] = True
    return patch


# ── Completeness ────────────────────────────────────────────────────

def is_real_serial(v) -> bool:
    return str(v or "").strip().upper() not in _PLACEHOLDER


def missing_essentials(eq: dict, customer_ref: str | None = None) -> list[str]:
    miss = []
    for f, _label in ESSENTIAL_FIELDS:
        if f == "sicon_customer_ref":
            if not (eq.get(f) or customer_ref):
                miss.append(f)
        elif f in ("serial_number", "manufacturer", "model"):
            if not is_real_serial(eq.get(f)):
                miss.append(f)
        elif not str(eq.get(f) or "").strip():
            miss.append(f)
    return miss


def _blank(f: str) -> dict:
    return {"$or": [{f: {"$exists": False}}, {f: None}, {f: ""}]}


def incomplete_query() -> dict:
    """Mongo condition matching docs missing any essential (customer ref
    is checked on the stored field — callers backfill it first)."""
    placeholder_fields = ("serial_number", "manufacturer", "model")
    conds = [_blank(f) for f, _ in ESSENTIAL_FIELDS if f not in placeholder_fields]
    for f in placeholder_fields:
        conds.append({f: {"$regex": r"^\s*(unknown|n/?a|tbc|tbd|none|null|-|0)?\s*$", "$options": "i"}})
        conds.append({f: {"$exists": False}})
        conds.append({f: None})
    return {"$or": conds}


# ── Template builders ───────────────────────────────────────────────

def template_csv() -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerow(SICON_EQUIPMENT_HEADERS)
    return buf.getvalue().encode("utf-8")


def template_xlsx() -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(SICON_EQUIPMENT_HEADERS)
    essential = {h for h, (req, _) in _GUIDE.items() if req == "Essential"}
    for col, h in enumerate(SICON_EQUIPMENT_HEADERS, start=1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="B91C1C" if h in essential else "19398D")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = max(14, min(32, len(h) + 4))
    ws.freeze_panes = "A2"
    guide = wb.create_sheet("How to complete")
    guide.append(["Column", "Required?", "What to enter"])
    for cell in guide[1]:
        cell.font = Font(bold=True)
    for h in SICON_EQUIPMENT_HEADERS:
        req, desc = _GUIDE.get(h, ("Optional", ""))
        guide.append([h, req, desc])
    guide.append([])
    guide.append(["Red headers are the Sicon essentials. Re-importing a file with the same serial numbers fills in gaps on existing assets instead of creating duplicates."])
    for i, w in enumerate((34, 12, 80), start=1):
        guide.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


TEMPLATE_FILENAME = "Equipment Import - Sicon Template"


def template_response(fmt: str = "csv"):
    from fastapi.responses import Response
    if (fmt or "").lower() == "xlsx":
        return Response(
            content=template_xlsx(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}.xlsx"'},
        )
    return Response(content=template_csv(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}.csv"'})


def merge_extras(doc: dict, row: dict) -> dict:
    """Add Sicon-only fields (and sub-location) from ``row`` onto an equipment doc."""
    from utils.spreadsheet_import import get_pick
    for k, v in sicon_extra_fields(row).items():
        if v not in (None, "") and not doc.get(k):
            doc[k] = v
    sub = get_pick(row, "sub_location")
    if sub and not doc.get("sub_location"):
        doc["sub_location"] = str(sub).strip()
    return doc
