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
async def download_equipment_csv_template(format: str = "csv", user: dict = Depends(get_current_user)):
    """Sicon equipment template (same as every other equipment import)."""
    require_master_admin(user)
    from utils.sicon_equipment import template_response
    return template_response(format)


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
    from utils.sicon_equipment import is_sicon_row, sicon_values
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
        _sv = sicon_values(raw_row) if is_sicon_row(raw_row) else {}
        for _src, _dst in (("name", "name"), ("serial_number", "serial_number"), ("install_date", "install_date"),
                           ("warranty_expiry", "warranty_expiry"), ("location", "location"), ("equipment_group", "equipment_type")):
            if _sv.get(_src) and not row.get(_dst):
                row[_dst] = str(_sv[_src])
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
    from routes.equipment_import import extract_invoice_smart, match_supplier

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
    # Iter 216h13 — use the same short-name + short-model helpers the
    # equipment doc builder uses so the wizard preview matches the row
    # that will actually be created on confirm.
    from routes.equipment_import import _short_equipment_name, _short_model_code
    for item in (extracted.get("equipment") or []):
        make = (item.get("make") or item.get("manufacturer") or "").strip()
        if not make and supplier and supplier.lower() != "unknown":
            make = supplier
        short_name = _short_equipment_name(item)
        short_model = _short_model_code(item)
        full_desc = (item.get("description") or item.get("model") or "").strip()
        equipment.append({
            # Display fields — what the wizard table shows
            "name": short_name,
            "model": short_model,
            "description": full_desc,
            # Backing fields — preserved for the confirm step + Sicon export
            "make": make,
            "manufacturer": make,
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
        "supplier_vat_number": extracted.get("supplier_vat_number", ""),
        "supplier_company_number": extracted.get("supplier_company_number", ""),
        "customer_name": extracted.get("customer_name", ""),
        "customer_reference": extracted.get("customer_reference", ""),
        "due_date": extracted.get("due_date", ""),
        "payment_terms": extracted.get("payment_terms", ""),
        "bank_details": extracted.get("bank_details") or {},
        "totals": extracted.get("totals") or {},
        "invoice_number": extracted.get("invoice_number", ""),
        "matched_supplier": await match_supplier(
            user.get("organization_id"),
            extracted.get("supplier_name", ""),
            extracted.get("supplier_vat_number", "") or "",
        ),
    }



# ── Iter 216h13 — Backfill helper for legacy invoice-imported equipment ──
#
# Equipment imported BEFORE iter 216h13 stored the 200-char Pulse Fitness
# marketing line as both `name` and `model`, which blew the equipment-row
# layout out of the page. This endpoint walks every equipment doc that
# was imported from an invoice and re-splits the long name/model into
# short `name` (subtype noun), short `model` (stock code), and a
# preserved `description` (full marketing line).
#
# Defaults to dry-run so the operator can eyeball the changes before
# applying them. Master-Admin gated.

def _looks_like_legacy_long_row(eq: dict) -> bool:
    """True when the equipment doc still has the pre-iter-216h13 shape —
    i.e. either `name` or `model` contains a long marketing line
    (> 24 chars and > 2 spaces). New imports never produce this shape
    because `_build_equipment_doc` short-circuits it."""
    name = (eq.get("name") or "").strip()
    model = (eq.get("model") or "").strip()
    name_long = len(name) > 30 and name.count(" ") >= 3
    model_long = len(model) > 24 and model.count(" ") >= 2
    return name_long or model_long


@router.post("/master-admin/equipment/backfill-short-display")
async def backfill_equipment_short_display(
    body: dict | None = None,
    dry_run: bool = True,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h13 — Rewrite legacy invoice-imported equipment rows so
    `name` is the short subtype noun and `model` is the short stock
    code (matching the iter-216h13 import behaviour). The full
    marketing line is preserved in the `description` field.

    Accepts `dry_run` either as a query param (matches existing
    BackfillsPanel convention) OR inside the JSON body.

    Body (all optional):
      - `organization_id`: limit to one org. If omitted, the backfill
                           runs across **every** org (master-admin only).
      - `site_name`: limit to one location (matches `location` field
                     stamped from the invoice delivery address).
      - `supplier_name`: limit to rows matching this supplier (case-
                         insensitive).
      - `dry_run`: bool, overrides query param.

    Returns:
      {
        "dry_run": bool,
        "total_candidates": int,           # legacy rows matched by filter
        "equipment_to_update": int,        # rows whose name/model actually changes
        "equipment_updated": int,          # 0 when dry_run; otherwise == equipment_to_update
        "orgs": int,                       # distinct org count touched
        "preview": [ {id, before, after}, ... ]  # first 200
      }
    """
    require_master_admin(user)
    from utils.database import db
    from routes.equipment_import import _short_equipment_name, _short_model_code

    body = body or {}
    if "dry_run" in body:
        dry_run = bool(body["dry_run"])
    org_id = (body.get("organization_id") or "").strip()
    site_name = (body.get("site_name") or "").strip()
    supplier_name = (body.get("supplier_name") or "").strip()

    query: dict = {}
    if org_id:
        query["organization_id"] = org_id
    # Only touch rows that were imported from an invoice. Either they
    # have a non-empty `import_id` OR their notes start with the
    # canonical stub "Imported from invoice".
    query["$or"] = [
        {"import_id": {"$exists": True, "$ne": ""}},
        {"notes": {"$regex": "^Imported from invoice"}},
    ]
    if site_name:
        import re as _re
        query["location"] = {"$regex": f"^{_re.escape(site_name)}$", "$options": "i"}
    if supplier_name:
        import re as _re
        query["supplier"] = {"$regex": f"^{_re.escape(supplier_name)}$", "$options": "i"}

    cursor = db.equipment.find(query, {"_id": 0})
    candidates: list[dict] = []
    async for doc in cursor:
        candidates.append(doc)

    preview: list[dict] = []
    to_update: list[dict] = []
    touched_orgs: set[str] = set()
    for eq in candidates:
        if not _looks_like_legacy_long_row(eq):
            continue
        # Synthesize the source the short helpers expect.
        long_text = (eq.get("name") or eq.get("model") or "")
        synth = {
            "equipment_name": "",  # force heuristic
            "description": long_text,
            "model": eq.get("model") or "",
            "stock_item_code": eq.get("stock_item_code") or "",
            "equipment_category": eq.get("equipment_category") or eq.get("equipment_type") or "",
        }
        new_name = _short_equipment_name(synth)
        new_model = _short_model_code(synth)
        old_name = (eq.get("name") or "").strip()
        old_model = (eq.get("model") or "").strip()
        if new_name == old_name and new_model == old_model:
            continue
        update = {
            "name": new_name,
            "model": new_model,
            "description": (eq.get("description") or long_text).strip(),
        }
        to_update.append({"id": eq["id"], "update": update})
        touched_orgs.add(eq.get("organization_id") or "")
        if len(preview) < 200:
            preview.append({
                "id": eq["id"],
                "before": {"name": old_name, "model": old_model},
                "after": update,
            })

    updated_count = 0
    if not dry_run and to_update:
        for item in to_update:
            await db.equipment.update_one({"id": item["id"]}, {"$set": item["update"]})
        updated_count = len(to_update)

    return {
        "dry_run": dry_run,
        "total_candidates": len(candidates),
        "equipment_to_update": len(to_update),
        "equipment_updated": updated_count,
        "orgs": len([o for o in touched_orgs if o]),
        "preview": preview,
    }
