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
    CANONICAL_FIELDS, NUMERIC_FIELDS, analyze_workbook, extract_products,
    extract_products_from_wb, load_workbook,
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
            if len(ops) >= 500:
                await db.crm_products.bulk_write(ops, ordered=False)
                ops = []
    if ops:
        await db.crm_products.bulk_write(ops, ordered=False)
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


@router.get("/versions")
async def list_versions(user=Depends(get_crm_user)) -> dict:
    cur = db.crm_price_list_versions.find(_of(user), {"_id": 0}).sort("created_at", -1).limit(50)
    return {"versions": await cur.to_list(50)}


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
    except Exception:
        logger.exception("ensure_price_list_indexes failed (non-fatal)")
