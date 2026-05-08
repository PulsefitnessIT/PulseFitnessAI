"""Iter 216e — Master-admin invoice parse helper for the Head Office
onboarding wizard.

Reuses the equipment_import AI pipeline (text-from-PDF → Emergent LLM →
structured JSON) but returns the result in the shape the wizard expects:
a single { site: {...}, equipment: [...] } blob the operator reviews on
screen before committing.

Iter 216f — also exposes equipment CSV preview + template download so
operators can bulk-add machines per site without invoices.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
import csv as _csv
import io as _io
import logging
import json as _json

from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def require_master_admin(user: dict):
    from fastapi import HTTPException as _H
    if not (user.get("is_master_admin") or user.get("role") in ("master_admin", "master")):
        raise _H(status_code=403, detail="Master admin access required")


_EQUIPMENT_CSV_HEADERS = [
    "make", "model", "serial_number", "equipment_type",
    "warranty_code", "warranty_expiry", "install_date", "location",
]
_EQUIPMENT_CSV_EXAMPLE_ROWS = [
    ["Pulse Fitness", "Club Line Treadmill", "SN1234", "treadmill", "WTY-001", "2027-01-31", "2025-04-12", "Main Floor"],
]


@router.get("/master-admin/equipment/template.csv")
async def download_equipment_csv_template(user: dict = Depends(get_current_user)):
    """Download a starter CSV for bulk-adding equipment to a site."""
    require_master_admin(user)
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(_EQUIPMENT_CSV_HEADERS)
    for row in _EQUIPMENT_CSV_EXAMPLE_ROWS:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="gymaxis-equipment-template.csv"'},
    )


@router.post("/master-admin/equipment/preview-csv")
async def preview_equipment_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Parse a per-site equipment CSV and return normalised rows. The
    wizard merges these into the active site's `equipment` list so they
    persist atomically with the rest of the onboarding payload."""
    require_master_admin(user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = _csv.DictReader(_io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is empty or missing a header row")
    headers_lower = [(h or "").strip().lower() for h in reader.fieldnames]
    has_any = any(k in headers_lower for k in ("make", "model", "serial_number", "name"))
    if not has_any:
        raise HTTPException(
            status_code=400,
            detail="CSV must include at least one of: make, model, serial_number, name",
        )

    rows: list[dict] = []
    errors: list[dict] = []
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        name = row.get("name") or row.get("model") or row.get("make")
        if not name:
            errors.append({"line": i, "error": "No name/model/make"})
            continue
        rows.append({
            "name": name,
            "make": row.get("make") or row.get("manufacturer") or "",
            "manufacturer": row.get("manufacturer") or row.get("make") or "",
            "model": row.get("model") or "",
            "serial_number": row.get("serial_number") or row.get("serial") or "",
            "equipment_type": row.get("equipment_type") or row.get("type") or "",
            "warranty_code": row.get("warranty_code") or "",
            "warranty_expiry": row.get("warranty_expiry") or "",
            "install_date": row.get("install_date") or row.get("purchase_date") or "",
            "location": row.get("location") or "Main Floor",
        })

    if not rows:
        raise HTTPException(status_code=400, detail="No valid equipment rows found in CSV")
    return {"equipment": rows, "count": len(rows), "errors": errors}


@router.post("/master-admin/invoice/parse-for-wizard")
async def parse_invoice_for_wizard(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Parse a supplier invoice (PDF or image — JPG/PNG/WEBP) and return
    {site, equipment} for the Head Office onboarding wizard. No
    persistence — caller submits the full wizard payload via
    /onboard-head-office to commit.

    Iter 216g — feature parity with the single-site onboarding flow:
    accepts scanned invoices via the smart extractor (text → vision
    fallback) and image uploads directly."""
    require_master_admin(user)
    from utils.file_validation import validate_upload
    from routes.equipment_import import extract_invoice_smart

    data = await file.read()
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    try:
        validate_upload(
            file_bytes=data, filename=file.filename,
            allowed=allowed, max_size=30 * 1024 * 1024,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Upload rejected: {exc}")

    try:
        extracted = await extract_invoice_smart(data, file.content_type)
    except HTTPException:
        raise
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {e}")

    # Normalise into the wizard's site schema. The AI currently gives us
    # a flat `site_name` + delivery-address string in `extracted`; split
    # into the 8-field address shape the wizard uses.
    site_name = (extracted.get("site_name") or "").strip()
    raw_addr = extracted.get("delivery_address") or extracted.get("ship_to") or ""
    # Try a very light split: first line → address_line1, last line → postcode.
    lines = [ln.strip() for ln in (raw_addr or "").splitlines() if ln.strip()]
    postcode = ""
    city = ""
    if lines:
        # Postcode often on the last line (UK style). Heuristic only.
        import re
        pc_match = re.search(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", lines[-1].upper())
        if pc_match:
            postcode = pc_match.group().strip()
            city = lines[-1].replace(pc_match.group(), "").replace(",", "").strip() or (lines[-2] if len(lines) > 1 else "")
    addr_line1 = lines[0] if lines else ""
    addr_line2 = lines[1] if len(lines) > 1 and lines[1] != city else ""

    equipment = []
    supplier = (extracted.get("supplier_name") or "").strip()
    for item in (extracted.get("equipment") or []):
        # Iter 216k — multi-site parity with single-site flow:
        #   • include unit_price + stock_item_code (was being dropped)
        #   • include AI-detected equipment_category (new this iter)
        #   • fall back to supplier_name when the AI couldn't pin a
        #     manufacturer to a particular line — that's why operators
        #     were seeing "Unknown" for every Pulse Fitness item.
        make = (item.get("make") or item.get("manufacturer") or "").strip()
        if not make and supplier and supplier.lower() != "unknown":
            make = supplier
        equipment.append({
            "name": (item.get("name") or item.get("model") or "").strip(),
            "make": make,
            "manufacturer": make,
            "model": (item.get("model") or "").strip(),
            "serial_number": (item.get("serial_number") or item.get("serial") or "").strip(),
            "equipment_type": (item.get("equipment_type") or item.get("type") or "").strip(),
            "equipment_category": (item.get("equipment_category") or "").strip(),
            "warranty_code": (item.get("warranty_code") or extracted.get("warranty_code") or "").strip(),
            "warranty_expiry": item.get("warranty_expiry") or None,
            "install_date": extracted.get("install_date") or "",
            "unit_price": item.get("unit_price") or 0,
            "stock_item_code": (item.get("stock_item_code") or "").strip(),
        })

    return {
        "site": {
            "name": site_name or (lines[0] if lines else ""),
            "address_line1": addr_line1,
            "address_line2": addr_line2,
            "city": city,
            "county": "",
            "postcode": postcode,
            "country": "United Kingdom",
            "phone": "",
            "email": "",
            "is_head_office": False,
            "default_location": "Main Floor",
        },
        "equipment": equipment,
        "equipment_count": len(equipment),
        "supplier_name": extracted.get("supplier_name", ""),
        "invoice_number": extracted.get("invoice_number", ""),
    }
