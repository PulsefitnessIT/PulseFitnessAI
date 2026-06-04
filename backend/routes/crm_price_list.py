"""CRM · Master Price List — migration import wizard + version control (Phase 1).

Extends the existing `crm_products` Master Price List (routes/crm_products.py)
with an enterprise, ZERO-DATA-LOSS spreadsheet migration pipeline:

  upload → analyze → (AI) suggest mapping → preview/validate → commit

plus import history, price-list versions and a data-quality summary.

Collections:
  crm_price_imports        import batches (analysis, mappings, summary, status)
  crm_price_import_files    the original uploaded file, stored verbatim (base64)
  crm_price_list_versions   draft/live/archived versions created by a commit

Products land in the existing `crm_products` collection with provenance
(`import_batch_id`, `version_id`, `source_sheet`, `source_row`) and an
`unmapped_fields` array — so every cell on the sheet is preserved and
traceable. No duplicate product module is created.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
from pymongo import UpdateOne

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit
from routes.crm_products import _is_admin, _calc_markup
from utils.price_list_import import (
    CANONICAL_FIELDS, NUMERIC_FIELDS, analyze_workbook, analyze_sheet,
    extract_products, extract_products_from_wb, load_workbook,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/price-list", tags=["CRM Price List"])

_MAX_BYTES = 30 * 1024 * 1024  # 30 MB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _require_admin(user: dict) -> None:
    if not _is_admin(user):
        raise HTTPException(403, "Only Price List editors (admin / owner / manager) can manage the Master Price List")


# ── Upload + analyze ───────────────────────────────────────────────


@router.post("/import/upload")
async def upload_import(file: UploadFile = File(...), user=Depends(get_crm_user)) -> dict:
    """Upload an XLSX/CSV, parse its structure, store the original file
    verbatim, and return the per-sheet analysis for the mapping step."""
    _require_admin(user)
    name = (file.filename or "import").strip()
    lower = name.lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".xls") or lower.endswith(".csv")):
        raise HTTPException(415, "Upload an .xlsx or .csv file")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "The uploaded file is empty")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(413, "File too large (max 30 MB)")

    # CSV → wrap into a one-sheet workbook so the same engine handles both.
    if lower.endswith(".csv"):
        raw = _csv_to_xlsx_bytes(raw)

    try:
        analysis = analyze_workbook(raw)
    except Exception as exc:  # noqa: BLE001
        logger.exception("price-list analyze failed")
        raise HTTPException(400, f"Could not read this spreadsheet: {exc}") from exc

    import_id = str(uuid.uuid4())
    total_rows = sum(s["product_count"] for s in analysis["sheets"])
    doc = {
        "id": import_id,
        "organization_id": user.get("organization_id"),
        "filename": name,
        "size": len(raw),
        "status": "uploaded",
        "sheets": analysis["sheets"],
        "total_detected_rows": total_rows,
        "created_at": _now(),
        "created_by": user.get("id", ""),
        "created_by_name": user.get("full_name", ""),
        "summary": None,
    }
    await db.crm_price_imports.insert_one(dict(doc))
    await db.crm_price_import_files.insert_one({
        "import_id": import_id,
        "organization_id": user.get("organization_id"),
        "filename": name,
        "content_b64": base64.b64encode(raw).decode("ascii"),
        "size": len(raw),
        "created_at": _now(),
    })
    await log_audit(user, "price_list_import", import_id, "uploaded", {"filename": name, "rows": total_rows})
    doc.pop("_id", None)
    return {"import": doc, "canonical_fields": CANONICAL_FIELDS}


def _csv_to_xlsx_bytes(raw: bytes) -> bytes:
    import csv as _csv
    import io as _io
    import openpyxl
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in _csv.reader(_io.StringIO(text)):
        ws.append(row)
    out = _io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def _load_file_bytes(import_id: str, user: dict) -> bytes:
    f = await db.crm_price_import_files.find_one({"import_id": import_id, **_of(user)})
    if not f:
        raise HTTPException(404, "Import file not found")
    return base64.b64decode(f["content_b64"])


@router.get("/imports")
async def list_imports(user=Depends(get_crm_user)) -> dict:
    cur = db.crm_price_imports.find(_of(user), {"_id": 0, "sheets": 0}).sort("created_at", -1).limit(50)
    return {"imports": await cur.to_list(50)}


@router.get("/import/{import_id}")
async def get_import(import_id: str, user=Depends(get_crm_user)) -> dict:
    doc = await db.crm_price_imports.find_one({"id": import_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    return doc


# ── AI mapping suggestions ─────────────────────────────────────────


@router.post("/import/{import_id}/suggest-mapping")
async def suggest_mapping(import_id: str, body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """AI-assisted column → CRM field suggestions for one sheet. Advisory
    only — the user confirms the mapping before any data is written."""
    _require_admin(user)
    doc = await db.crm_price_imports.find_one({"id": import_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    sheet_name = body.get("sheet")
    sheet = next((s for s in doc["sheets"] if s["name"] == sheet_name), None)
    if not sheet:
        raise HTTPException(404, "Sheet not found in this import")
    try:
        mapping = await _ai_suggest(sheet)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI mapping suggestion failed: %s — falling back to heuristic", exc)
        mapping = {str(k): v for k, v in (sheet.get("auto_mapping") or {}).items()}
    return {"mapping": mapping, "source": "ai"}


async def _ai_suggest(sheet: dict) -> dict:
    import json
    import os
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    fields_desc = "\n".join(f"- {f['key']}: {f['label']}" for f in CANONICAL_FIELDS)
    cols = []
    sample = sheet.get("sample") or []
    for col in sheet["columns"]:
        examples = [r["cells"].get(col["label"]) for r in sample if r["cells"].get(col["label"])][:3]
        cols.append({"index": col["index"], "label": col["label"], "examples": examples})
    prompt = (
        "You map spreadsheet columns to a CRM product price-list schema. "
        "Return ONLY JSON: an object mapping column index (string) to the best "
        "CRM field key, or omit a column if none fits (it will be preserved as "
        "unmapped data — do NOT force a poor match).\n\n"
        f"CRM fields:\n{fields_desc}\n\n"
        f"Columns (index, label, example values):\n{json.dumps(cols, ensure_ascii=False)}\n\n"
        'Example output: {"1": "sku", "2": "name", "4": "cost_price"}'
    )
    chat = LlmChat(api_key=api_key, session_id=f"plmap-{uuid.uuid4()}",
                   system_message="You are a precise data-mapping assistant. Output JSON only.").with_model("anthropic", "claude-sonnet-4-6")
    resp = await chat.send_message(UserMessage(text=prompt))
    t = (resp or "").strip()
    if "```" in t:
        t = t.split("```")[1].replace("json", "", 1).strip()
    start, end = t.find("{"), t.rfind("}")
    raw = json.loads(t[start:end + 1]) if start != -1 else {}
    valid = {f["key"] for f in CANONICAL_FIELDS}
    return {str(k): v for k, v in raw.items() if v in valid}


@router.post("/import/{import_id}/ai-analyze")
async def ai_analyze_sheet(import_id: str, body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """Whole-sheet AI layout detection for messy spreadsheets.

    Sends a small sample of RAW rows to the LLM, which identifies the
    header row, the product-code / name columns and the field mapping.
    The sheet is then re-analyzed deterministically with those overrides
    and returned (same shape as upload analysis) so the wizard can swap it
    in. Advisory only — the user still confirms before any data is written.
    """
    _require_admin(user)
    doc = await db.crm_price_imports.find_one({"id": import_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    sheet_name = body.get("sheet")
    if not any(s["name"] == sheet_name for s in doc["sheets"]):
        raise HTTPException(404, "Sheet not found in this import")

    raw = await _load_file_bytes(import_id, user)
    wb = load_workbook(raw)
    try:
        suggestion = await _ai_detect_layout(wb, sheet_name)
        sheet = analyze_sheet(
            wb, sheet_name,
            header_row=suggestion["header_row"],
            code_col=suggestion.get("code_col", 0),
            name_col=suggestion.get("name_col"),
        )
        # merge AI field mappings (validated) over the heuristic ones
        valid = {f["key"] for f in CANONICAL_FIELDS}
        ai_map = {str(k): v for k, v in (suggestion.get("mappings") or {}).items() if v in valid}
        merged = {**sheet.get("auto_mapping", {}), **ai_map}
        sheet["auto_mapping"] = merged
        sheet["ai_note"] = suggestion.get("note", "")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI sheet analyze failed: %s", exc)
        raise HTTPException(503, "AI layout detection is unavailable — adjust the header row manually") from exc
    finally:
        wb.close()

    # persist the refreshed sheet structure back onto the import doc
    sheets = [sheet if s["name"] == sheet_name else s for s in doc["sheets"]]
    await db.crm_price_imports.update_one({"id": import_id, **_of(user)}, {"$set": {"sheets": sheets}})
    return {"sheet": sheet, "mapping": sheet["auto_mapping"], "source": "ai"}


async def _ai_detect_layout(wb, sheet_name: str) -> dict:
    """Ask the LLM to identify header row + identity columns + mapping from a
    raw sample. Returns {header_row, code_col, name_col, mappings, note}."""
    import json
    import os
    from openpyxl.utils import get_column_letter
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    ws = wb[sheet_name]
    max_col = min(ws.max_column or 1, 30)
    max_row = min(ws.max_row or 1, 25)
    grid = []
    for r in range(1, max_row + 1):
        cells = {}
        for c in range(1, max_col + 1):
            v = ws.cell(row=r, column=c).value
            if v is not None and str(v).strip():
                cells[c] = str(v).strip()[:60]
        if cells:
            grid.append({"row": r, "cells": cells})
    fields_desc = "\n".join(f"- {f['key']}: {f['label']}" for f in CANONICAL_FIELDS)
    prompt = (
        "You are analysing a raw product price-list spreadsheet to import it "
        "into a CRM. Columns are 1-based. From the sampled rows below, identify:\n"
        "- header_row: the row number containing the column titles\n"
        "- code_col: 1-based column number of the product code/SKU column, or 0 "
        "if there is none (some catalogues are keyed by product name only)\n"
        "- name_col: 1-based column number of the product NAME/description column\n"
        "- mappings: object of {column_number: crm_field_key} for columns you "
        "can confidently map (omit unknown columns — they're preserved as data)\n"
        "- note: one short sentence describing the layout.\n\n"
        f"CRM field keys:\n{fields_desc}\n\n"
        f"Sampled rows (row · {{column: value}}):\n{json.dumps(grid, ensure_ascii=False)}\n\n"
        'Return ONLY JSON, e.g. {"header_row":3,"code_col":1,"name_col":2,'
        '"mappings":{"1":"sku","2":"name","5":"cost_price"},"note":"..."}'
    )
    chat = LlmChat(api_key=api_key, session_id=f"pllayout-{uuid.uuid4()}",
                   system_message="You are a precise spreadsheet-structure analyst. Output JSON only.").with_model("anthropic", "claude-sonnet-4-6")
    resp = await chat.send_message(UserMessage(text=prompt))
    t = (resp or "").strip()
    if "```" in t:
        t = t.split("```")[1].replace("json", "", 1).strip()
    start, end = t.find("{"), t.rfind("}")
    raw = json.loads(t[start:end + 1]) if start != -1 else {}
    hr = int(raw.get("header_row") or 1)
    cc = int(raw.get("code_col") or 0)
    nc = raw.get("name_col")
    nc = int(nc) if nc else None
    return {"header_row": max(1, hr), "code_col": max(0, cc), "name_col": nc,
            "mappings": raw.get("mappings") or {}, "note": str(raw.get("note") or "")[:200]}



# ── Preview / validate ─────────────────────────────────────────────


def _validate_products(products: list[dict], existing_skus: set[str], seen: dict[str, int]) -> dict:
    ready = warnings = errors = dups_in_file = updates = new = 0
    missing_name = missing_price = missing_sage = neg_price = cost_gt_sell = unmapped_total = 0
    issues: list[dict] = []
    for p in products:
        sku = (p.get("sku") or "").strip()
        row_issues = []
        if not sku:
            errors += 1
            issues.append({"row": p.get("source_row"), "sheet": p.get("source_sheet"), "level": "error", "msg": "Missing product code"})
            continue
        if sku in seen:
            dups_in_file += 1
            row_issues.append("duplicate code in file")
        seen[sku] = seen.get(sku, 0) + 1
        if sku in existing_skus:
            updates += 1
        else:
            new += 1
        if not (p.get("name") or "").strip():
            missing_name += 1
            row_issues.append("missing name")
        cost = p.get("cost_price")
        sell = p.get("sell_price")
        if not cost and not sell:
            missing_price += 1
        if (isinstance(cost, (int, float)) and cost < 0) or (isinstance(sell, (int, float)) and sell < 0):
            neg_price += 1
            row_issues.append("negative price")
        if isinstance(cost, (int, float)) and isinstance(sell, (int, float)) and sell and cost > sell:
            cost_gt_sell += 1
            row_issues.append("cost > sell")
        if not (p.get("sage_code") or "").strip():
            missing_sage += 1
        unmapped_total += len(p.get("unmapped_fields") or [])
        if row_issues:
            warnings += 1
            if len(issues) < 50:
                issues.append({"row": p.get("source_row"), "sheet": p.get("source_sheet"), "code": sku, "level": "warning", "msg": ", ".join(row_issues)})
        else:
            ready += 1
    return {
        "total": len(products), "ready": ready, "warnings": warnings, "errors": errors,
        "new": new, "updates": updates, "duplicates_in_file": dups_in_file,
        "missing_name": missing_name, "missing_price": missing_price, "missing_sage": missing_sage,
        "negative_price": neg_price, "cost_gt_sell": cost_gt_sell,
        "unmapped_columns_total": unmapped_total, "issues": issues[:50],
    }


@router.post("/import/{import_id}/preview")
async def preview_import(import_id: str, body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """Dry-run: extract products per sheet cfg and report validation +
    new/update counts WITHOUT writing anything."""
    _require_admin(user)
    doc = await db.crm_price_imports.find_one({"id": import_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    sheets_cfg = body.get("sheets") or []
    raw = await _load_file_bytes(import_id, user)
    wb = load_workbook(raw)
    existing = await db.crm_products.distinct("sku", _of(user))
    existing_skus = {s for s in existing if s}
    all_products: list[dict] = []
    per_sheet = []
    for cfg in sheets_cfg:
        if not cfg.get("selected", True):
            continue
        prods = extract_products_from_wb(wb, cfg)
        all_products.extend(prods)
        per_sheet.append({"sheet": cfg["name"], "count": len(prods)})
    wb.close()
    seen: dict[str, int] = {}
    summary = _validate_products(all_products, existing_skus, seen)
    summary["per_sheet"] = per_sheet
    return {"preview": summary}


# ── Commit ─────────────────────────────────────────────────────────


_EXTENDED_STR = {
    "sage_code", "model", "sub_category", "product_family", "manufacturer",
    "supplier_part_number", "manufacturer_part_number", "warranty",
    "compatibility", "internal_notes", "customer_notes", "status",
    "effective_date", "currency",
}
_EXTENDED_NUM = {"retail_price", "trade_price", "list_price", "discount", "margin",
                 "installation_cost", "delivery_cost"}


def _build_product_doc(p: dict, user: dict, version_id: str, import_id: str) -> dict:
    cost = float(p.get("cost_price") or 0)
    sell = float(p.get("sell_price") or 0)
    doc: dict[str, Any] = {
        "organization_id": user.get("organization_id"),
        "name": (p.get("name") or p.get("sku") or "Unnamed").strip()[:300],
        "sku": (p.get("sku") or "").strip() or None,
        "description": (p.get("description") or "").strip(),
        "category": (p.get("category") or p.get("section") or "Equipment").strip() or "Equipment",
        "unit": (p.get("unit") or "each").strip()[:40],
        "cost_price": round(cost, 2),
        "sell_price": round(sell, 2),
        "currency": (p.get("currency") or "GBP").strip().upper()[:8] or "GBP",
        "markup_percent": _calc_markup(cost, sell),
        "tax_rate": float(p.get("tax_rate") or 20),
        "supplier_name": (p.get("supplier_name") or "").strip(),
        "active": True,
        "archived": False,
        "notes": "",
        # provenance — every product traceable back to the sheet
        "source_sheet": p.get("source_sheet"),
        "source_row": p.get("source_row"),
        "section": p.get("section") or "",
        "import_batch_id": import_id,
        "version_id": version_id,
        "unmapped_fields": p.get("unmapped_fields") or [],
        "is_bundle": False,
        "bundle_items": [],
    }
    for f in _EXTENDED_STR:
        if p.get(f) not in (None, ""):
            doc[f] = str(p[f]).strip()
    for f in _EXTENDED_NUM:
        if isinstance(p.get(f), (int, float)):
            doc[f] = round(float(p[f]), 2)
    return doc


@router.post("/import/{import_id}/commit")
async def commit_import(import_id: str, body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    """Write the mapped products into the Master Price List, creating a
    new price-list version. Idempotent on SKU within the org."""
    _require_admin(user)
    doc = await db.crm_price_imports.find_one({"id": import_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    if doc.get("status") == "committed":
        raise HTTPException(409, "This import has already been committed")

    sheets_cfg = body.get("sheets") or []
    opts = body.get("options") or {}
    mode = "live" if opts.get("mode") == "live" else "draft"
    do_create = opts.get("create", True)
    do_update = opts.get("update", True)
    version_label = (opts.get("version_label") or "").strip() or f"Import {datetime.now(timezone.utc):%d %b %Y %H:%M}"

    raw = await _load_file_bytes(import_id, user)
    wb = load_workbook(raw)
    version_id = str(uuid.uuid4())

    existing = await db.crm_products.find(_of(user), {"_id": 0, "id": 1, "sku": 1}).to_list(None)
    existing_by_sku = {p["sku"]: p["id"] for p in existing if p.get("sku")}

    created = updated = skipped = 0
    ops: list[UpdateOne] = []
    snaps: list[dict] = []
    seen_skus: set[str] = set()
    for cfg in sheets_cfg:
        if not cfg.get("selected", True):
            continue
        for p in extract_products_from_wb(wb, cfg):
            sku = (p.get("sku") or "").strip()
            if not sku:
                skipped += 1
                continue
            if sku in seen_skus:
                # first occurrence wins; duplicates within the same import skipped
                skipped += 1
                continue
            seen_skus.add(sku)
            pdoc = _build_product_doc(p, user, version_id, import_id)
            if sku in existing_by_sku:
                if not do_update:
                    skipped += 1
                    continue
                pid = existing_by_sku[sku]
                pdoc["updated_at"] = _now()
                pdoc["updated_by"] = user.get("id", "")
                ops.append(UpdateOne({"id": pid, **_of(user)}, {"$set": pdoc}))
                updated += 1
                snaps.append(_snapshot_entry(pid, pdoc, version_id, user))
            else:
                if not do_create:
                    skipped += 1
                    continue
                pdoc["id"] = str(uuid.uuid4())
                pdoc["created_at"] = _now()
                pdoc["created_by"] = user.get("id", "")
                pdoc["updated_at"] = _now()
                ops.append(UpdateOne({"id": pdoc["id"]}, {"$setOnInsert": pdoc}, upsert=True))
                created += 1
                snaps.append(_snapshot_entry(pdoc["id"], pdoc, version_id, user))
            if len(ops) >= 500:
                await db.crm_products.bulk_write(ops, ordered=False)
                ops = []
        if len(snaps) >= 1000:
            await db.crm_price_list_version_items.insert_many(snaps)
            snaps = []
    if ops:
        await db.crm_products.bulk_write(ops, ordered=False)
    if snaps:
        await db.crm_price_list_version_items.insert_many(snaps)
    wb.close()

    if mode == "live":
        await db.crm_price_list_versions.update_many(
            {**_of(user), "status": "live"}, {"$set": {"status": "archived", "archived_at": _now()}}
        )

    version_doc = {
        "id": version_id,
        "organization_id": user.get("organization_id"),
        "label": version_label,
        "status": mode,
        "import_batch_id": import_id,
        "product_count": created + updated,
        "created_at": _now(),
        "created_by": user.get("id", ""),
        "created_by_name": user.get("full_name", ""),
        "summary": {"created": created, "updated": updated, "skipped": skipped},
    }
    await db.crm_price_list_versions.insert_one(dict(version_doc))
    await db.crm_price_imports.update_one(
        {"id": import_id, **_of(user)},
        {"$set": {"status": "committed", "committed_at": _now(),
                  "version_id": version_id,
                  "summary": version_doc["summary"]}},
    )
    await log_audit(user, "price_list_import", import_id, "committed",
                    {"created": created, "updated": updated, "skipped": skipped, "mode": mode})
    version_doc.pop("_id", None)
    return {"version": version_doc, "summary": version_doc["summary"]}


# ── Versions + data quality ────────────────────────────────────────


def _snapshot_entry(product_id: str, pdoc: dict, version_id: str, user: dict) -> dict:
    """Compact price snapshot of a product at version-commit time — the
    basis for version compare + rollback."""
    return {
        "version_id": version_id,
        "organization_id": user.get("organization_id"),
        "product_id": product_id,
        "sku": pdoc.get("sku"),
        "name": pdoc.get("name"),
        "category": pdoc.get("category"),
        "cost_price": pdoc.get("cost_price", 0),
        "sell_price": pdoc.get("sell_price", 0),
        "markup_percent": pdoc.get("markup_percent", 0),
        "sage_code": pdoc.get("sage_code", ""),
        "archived": bool(pdoc.get("archived")),
    }


def _is_approver(user: dict) -> bool:
    return (
        bool(user.get("is_master_admin"))
        or bool(user.get("is_pulse_admin"))
        or (user.get("role") or "").lower() in ("admin", "owner")
    )


@router.get("/versions")
async def list_versions(user=Depends(get_crm_user)) -> dict:
    cur = db.crm_price_list_versions.find(_of(user), {"_id": 0}).sort("created_at", -1).limit(50)
    return {"versions": await cur.to_list(50)}


@router.post("/versions/snapshot-current")
async def snapshot_current(body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    """Capture a snapshot of the CURRENT live catalogue as a new version —
    a baseline so compare/rollback works for data imported before snapshots
    existed (or for ad-hoc checkpoints)."""
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can publish versions")
    label = (body.get("label") or "").strip() or f"Snapshot {datetime.now(timezone.utc):%d %b %Y %H:%M}"
    version_id = str(uuid.uuid4())
    cur = db.crm_products.find({**_of(user), "active": True}, {"_id": 0})
    snaps: list[dict] = []
    count = 0
    async for p in cur:
        snaps.append(_snapshot_entry(p["id"], p, version_id, user))
        count += 1
        if len(snaps) >= 1000:
            await db.crm_price_list_version_items.insert_many(snaps)
            snaps = []
    if snaps:
        await db.crm_price_list_version_items.insert_many(snaps)
    vdoc = {
        "id": version_id, "organization_id": user.get("organization_id"),
        "label": label, "status": "snapshot", "product_count": count,
        "created_at": _now(), "created_by": user.get("id", ""),
        "created_by_name": user.get("full_name", ""),
        "summary": {"snapshot": count},
    }
    await db.crm_price_list_versions.insert_one(dict(vdoc))
    await log_audit(user, "price_list_version", version_id, "snapshot", {"count": count})
    vdoc.pop("_id", None)
    return {"version": vdoc}


async def _version_items_map(version_id: str, user: dict) -> dict[str, dict]:
    cur = db.crm_price_list_version_items.find({"version_id": version_id, **_of(user)}, {"_id": 0})
    items = await cur.to_list(None)
    return {it["sku"]: it for it in items if it.get("sku")}


@router.get("/versions/{version_id}/compare")
async def compare_versions(version_id: str, to: str = "", user=Depends(get_crm_user)) -> dict:
    """Diff two versions by SKU: added / removed / changed (cost, sell,
    margin, Sage code). ``version_id`` is the base (older), ``to`` the
    target (newer). If ``to`` is omitted, compares against the current
    live catalogue snapshot-on-the-fly."""
    base = await db.crm_price_list_versions.find_one({"id": version_id, **_of(user)}, {"_id": 0})
    if not base:
        raise HTTPException(404, "Base version not found")
    base_map = await _version_items_map(version_id, user)
    if to:
        target = await db.crm_price_list_versions.find_one({"id": to, **_of(user)}, {"_id": 0})
        if not target:
            raise HTTPException(404, "Target version not found")
        target_map = await _version_items_map(to, user)
        target_label = target.get("label")
    else:
        # live catalogue as target
        cur = db.crm_products.find({**_of(user), "active": True}, {"_id": 0, "id": 1, "sku": 1, "name": 1, "cost_price": 1, "sell_price": 1, "markup_percent": 1, "sage_code": 1})
        target_map = {p["sku"]: p for p in await cur.to_list(None) if p.get("sku")}
        target_label = "Current live"

    added, removed, changed = [], [], []
    for sku, t in target_map.items():
        if sku not in base_map:
            added.append({"sku": sku, "name": t.get("name"), "sell_price": t.get("sell_price")})
    for sku, b in base_map.items():
        if sku not in target_map:
            removed.append({"sku": sku, "name": b.get("name"), "sell_price": b.get("sell_price")})
            continue
        t = target_map[sku]
        diffs = {}
        for f in ("cost_price", "sell_price", "markup_percent", "sage_code"):
            ov, nv = b.get(f), t.get(f)
            if f == "sage_code":
                same = (ov or "") == (nv or "")
            else:
                same = round(float(ov or 0), 2) == round(float(nv or 0), 2)
            if not same:
                diffs[f] = {"old": ov, "new": nv}
        if diffs:
            changed.append({"sku": sku, "name": t.get("name") or b.get("name"), "changes": diffs})
    return {
        "base": {"id": version_id, "label": base.get("label")},
        "target": {"id": to or None, "label": target_label},
        "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
        "added": added[:200], "removed": removed[:200], "changed": changed[:300],
    }


@router.post("/versions/{version_id}/rollback")
async def rollback_version(version_id: str, body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    """Restore prices (cost / sell / Sage code) from a version snapshot onto
    the live catalogue, creating a new live 'Rollback of …' version. Existing
    quotes keep their quoted prices (quotes store line prices at creation)."""
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can roll back versions")
    src = await db.crm_price_list_versions.find_one({"id": version_id, **_of(user)}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Version not found")
    items = await _version_items_map(version_id, user)
    if not items:
        raise HTTPException(400, "This version has no snapshot to restore")
    new_vid = str(uuid.uuid4())
    ops: list[UpdateOne] = []
    snaps: list[dict] = []
    restored = 0
    existing = await db.crm_products.find(_of(user), {"_id": 0, "id": 1, "sku": 1}).to_list(None)
    by_sku = {p["sku"]: p["id"] for p in existing if p.get("sku")}
    for sku, snap in items.items():
        pid = by_sku.get(sku)
        if not pid:
            continue
        upd = {
            "cost_price": snap.get("cost_price", 0),
            "sell_price": snap.get("sell_price", 0),
            "markup_percent": snap.get("markup_percent", 0),
            "sage_code": snap.get("sage_code", ""),
            "version_id": new_vid,
            "updated_at": _now(), "updated_by": user.get("id", ""),
        }
        ops.append(UpdateOne({"id": pid, **_of(user)}, {"$set": upd,
                    "$push": {"price_history": {"$each": [{
                        "field": "rollback", "old": None, "new": None,
                        "reason": f"Rolled back to {src.get('label')}",
                        "by": user.get("full_name", ""), "at": _now(),
                    }], "$slice": -50}}}))
        snaps.append({**snap, "version_id": new_vid, "product_id": pid})
        restored += 1
        if len(ops) >= 500:
            await db.crm_products.bulk_write(ops, ordered=False)
            ops = []
        if len(snaps) >= 1000:
            await db.crm_price_list_version_items.insert_many(snaps)
            snaps = []
    if ops:
        await db.crm_products.bulk_write(ops, ordered=False)
    if snaps:
        await db.crm_price_list_version_items.insert_many(snaps)
    await db.crm_price_list_versions.update_many({**_of(user), "status": "live"}, {"$set": {"status": "archived", "archived_at": _now()}})
    vdoc = {
        "id": new_vid, "organization_id": user.get("organization_id"),
        "label": f"Rollback of {src.get('label')}", "status": "live",
        "rolled_back_from": version_id, "product_count": restored,
        "created_at": _now(), "created_by": user.get("id", ""),
        "created_by_name": user.get("full_name", ""), "summary": {"restored": restored},
    }
    await db.crm_price_list_versions.insert_one(dict(vdoc))
    await log_audit(user, "price_list_version", new_vid, "rollback", {"from": version_id, "restored": restored})
    vdoc.pop("_id", None)
    return {"version": vdoc, "restored": restored}


@router.post("/versions/{version_id}/publish")
async def publish_version(version_id: str, user=Depends(get_crm_user)) -> dict:
    """Mark a draft/snapshot version as the live version (archives the
    previous live)."""
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can publish versions")
    v = await db.crm_price_list_versions.find_one({"id": version_id, **_of(user)}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Version not found")
    await db.crm_price_list_versions.update_many({**_of(user), "status": "live"}, {"$set": {"status": "archived", "archived_at": _now()}})
    await db.crm_price_list_versions.update_one({"id": version_id, **_of(user)}, {"$set": {"status": "live", "published_at": _now()}})
    await log_audit(user, "price_list_version", version_id, "published")
    return {"published": True, "id": version_id}


@router.get("/stats")
async def data_quality(user=Depends(get_crm_user)) -> dict:
    """Data-quality dashboard summary for the org's master price list."""
    of = _of(user)
    total = await db.crm_products.count_documents({**of, "active": True})
    archived = await db.crm_products.count_documents({**of, "active": False})
    missing_sage = await db.crm_products.count_documents({**of, "active": True, "$or": [{"sage_code": {"$exists": False}}, {"sage_code": ""}]})
    missing_price = await db.crm_products.count_documents({**of, "active": True, "sell_price": {"$lte": 0}, "cost_price": {"$lte": 0}})
    no_category = await db.crm_products.count_documents({**of, "active": True, "$or": [{"category": {"$exists": False}}, {"category": ""}]})
    with_unmapped = await db.crm_products.count_documents({**of, "active": True, "unmapped_fields.0": {"$exists": True}})
    suppliers = [s for s in await db.crm_products.distinct("supplier_name", {**of, "active": True}) if s]
    return {
        "total": total, "archived": archived,
        "missing_sage": missing_sage, "missing_price": missing_price,
        "no_category": no_category, "with_unmapped": with_unmapped,
        "suppliers": suppliers[:200],
    }


async def ensure_price_list_indexes() -> None:
    try:
        await db.crm_price_imports.create_index([("organization_id", 1), ("created_at", -1)])
        await db.crm_price_import_files.create_index([("import_id", 1)])
        await db.crm_price_list_versions.create_index([("organization_id", 1), ("created_at", -1)])
        await db.crm_products.create_index([("organization_id", 1), ("import_batch_id", 1)])
        await db.crm_price_list_version_items.create_index([("version_id", 1), ("organization_id", 1)])
        await db.crm_price_list_version_items.create_index([("version_id", 1), ("sku", 1)])
    except Exception:
        logger.exception("ensure_price_list_indexes failed (non-fatal)")
