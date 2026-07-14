"""Dealer Warranty Parts — Phase 1 Data & Intelligence engine.

Turns the two historical Pulse Fitness spreadsheets into a reusable, intelligent
dealer-parts engine:

  • Parts Used.xlsx  (sheet SageReportData1) → usage records + Most-Used analysis.
  • Pulse_Fitness_BOM.xlsx (sheet BOMData)  → versioned BOM machines + components.

Everything is import-batch traceable, reversible and audited. Matching between
historical usage and the BOM is multi-stage (exact code → normalised code →
description exact/normalised/fuzzy → alias → manual). Unmatched high-usage parts
land in a review queue; low-confidence matches require human review before they
feed dealer recommendations.

Reuses Phase 1 helpers/collections from `routes.dealer_parts` — no duplication of
dealers / orders / stock / parts. New collections owned here:

  • dealer_parts_import_batches     — one row per import (parts_used | bom)
  • dealer_parts_usage_records      — raw usage rows (SageReportData1)
  • dealer_most_used_analysis       — computed most-used master (per component code)
  • dealer_bom_machines             — one row per top-level BOM ref (versioned)
  • dealer_bom_components           — BOM component rows (BOMData)
  • dealer_component_matches        — audit record per resolved match
  • dealer_component_aliases        — old/superseded → current code aliases
  • dealer_parts_data_settings      — matching thresholds / import config
"""
from __future__ import annotations

import io
import re
import uuid
import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from utils.database import db
from utils.auth import get_current_user
from utils.security_plus import safe_regex

from routes.dealer_parts import _of, _now, _audit, require_staff

router = APIRouter(prefix="/dealer-parts/data", tags=["Dealer Parts — Data & Intelligence"],
                   dependencies=[Depends(require_staff)])

BATCHES = "dealer_parts_import_batches"
USAGE = "dealer_parts_usage_records"
ANALYSIS = "dealer_most_used_analysis"
BOM_MACHINES = "dealer_bom_machines"
BOM_COMPONENTS = "dealer_bom_components"
MATCHES = "dealer_component_matches"
ALIASES = "dealer_component_aliases"
DATA_SETTINGS = "dealer_parts_data_settings"

DEFAULT_DATA_SETTINGS = {
    "fuzzy_threshold": 0.82,
    "high_usage_threshold": 20,       # total qty since 2022 to flag "high usage"
    "recent_window_days": 90,
    "auto_match_exact_code": True,
    "auto_match_normalised_code": True,
    "auto_match_fuzzy_description": False,   # fuzzy always needs review
    "require_alias_approval": True,
    "require_human_review_before_recommend": True,
}

CONF_RANK = {
    "exact_code": 100, "normalised_code": 92, "exact_description": 80,
    "normalised_description": 72, "fuzzy_description": 60, "alias": 88,
    "manual": 100, "none": 0,
}


# ─────────────────────────────────────────────────────────────────
# Normalisation + helpers
# ─────────────────────────────────────────────────────────────────

def norm_code(s) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[\u200b-\u200f\ufeff]", "", s)
    s = s.strip().upper()
    s = s.replace("\\", "/").replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def norm_desc(s) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).upper().strip()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _data_settings(org: str) -> dict:
    s = await db[DATA_SETTINGS].find_one({"organization_id": org}, {"_id": 0})
    if not s:
        s = {"organization_id": org, **DEFAULT_DATA_SETTINGS, "updated_at": _now()}
        await db[DATA_SETTINGS].insert_one(dict(s))
        s.pop("_id", None)
    else:
        for k, v in DEFAULT_DATA_SETTINGS.items():
            s.setdefault(k, v)
    return s


def _to_iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(str(dt)).isoformat()
    except Exception:
        return None


def _parse_dt(dt):
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(dt))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _find_sheet(wb, preferred: str):
    for name in wb.sheetnames:
        if name.strip().lower() == preferred.strip().lower():
            return wb[name]
    return None


def _header_map(ws):
    """Return {normalised_header: column_index} from the first row."""
    hdr = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None) or ()
    return {norm_desc(h): i for i, h in enumerate(hdr) if h is not None}


def _col(hmap, *candidates):
    for c in candidates:
        idx = hmap.get(norm_desc(c))
        if idx is not None:
            return idx
    return None


# ─────────────────────────────────────────────────────────────────
# Parts Used import
# ─────────────────────────────────────────────────────────────────

async def _import_parts_used(org: str, user: dict, content: bytes, filename: str) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = _find_sheet(wb, "SageReportData1")
    if ws is None:
        raise HTTPException(400, "Sheet 'SageReportData1' not found in workbook")
    hmap = _header_map(ws)
    c_sla = _col(hmap, "SiSMSLAs.Name", "SLA", "SiSMSLAs Name")
    c_dt = _col(hmap, "SiconAppointments.ActualStartTime", "ActualStartTime", "Date")
    c_code = _col(hmap, "Component/Sub-assembly Code", "Component Code", "Part Code")
    c_desc = _col(hmap, "Component/Sub-assembly Description", "Description")
    c_qty = _col(hmap, "Quantity", "Qty")
    c_cost = _col(hmap, "Cost")
    if c_code is None or c_qty is None:
        raise HTTPException(400, "Required columns missing (need Component Code + Quantity)")

    batch_id = str(uuid.uuid4())
    docs = []
    warnings = {"missing_code": 0, "missing_qty": 0, "invalid_qty": 0, "missing_date": 0, "missing_cost": 0}
    imported = skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        code = row[c_code] if c_code is not None else None
        if not code or not str(code).strip():
            warnings["missing_code"] += 1
            skipped += 1
            continue
        raw_qty = row[c_qty] if c_qty is not None else None
        try:
            qty = float(raw_qty) if raw_qty not in (None, "") else 1.0
        except (TypeError, ValueError):
            warnings["invalid_qty"] += 1
            qty = 1.0
        dt = _parse_dt(row[c_dt]) if c_dt is not None else None
        if dt is None:
            warnings["missing_date"] += 1
        cost = None
        if c_cost is not None and row[c_cost] not in (None, ""):
            try:
                cost = float(row[c_cost])
            except (TypeError, ValueError):
                cost = None
        if cost is None:
            warnings["missing_cost"] += 1
        docs.append({
            "id": str(uuid.uuid4()),
            "organization_id": org,
            "batch_id": batch_id,
            "sla_name": (str(row[c_sla]).strip() if c_sla is not None and row[c_sla] else ""),
            "used_at": dt.isoformat() if dt else None,
            "year": dt.year if dt else None,
            "month": dt.strftime("%Y-%m") if dt else None,
            "code": str(code).strip(),
            "code_norm": norm_code(code),
            "description": (str(row[c_desc]).strip() if c_desc is not None and row[c_desc] else ""),
            "quantity": qty,
            "cost": cost,
        })
        imported += 1
    wb.close()

    if docs:
        for i in range(0, len(docs), 2000):
            await db[USAGE].insert_many([dict(d) for d in docs[i:i + 2000]])

    batch = {
        "id": batch_id, "organization_id": org, "kind": "parts_used",
        "filename": filename, "status": "imported",
        "rows_imported": imported, "rows_skipped": skipped,
        "unique_parts": len({d["code_norm"] for d in docs}),
        "warnings": warnings,
        "created_by": user.get("full_name") or user.get("email"),
        "created_at": _now(),
    }
    await db[BATCHES].insert_one(dict(batch))
    await _audit(org, user, "parts_used_imported", batch_id=batch_id, rows=imported, skipped=skipped)

    summary = await _rebuild_analysis(org)
    batch["analysis"] = summary
    batch.pop("_id", None)
    return batch


async def _rebuild_analysis(org: str) -> dict:
    """Recompute the Most-Used analysis master from all live usage records."""
    await db[ANALYSIS].delete_many({"organization_id": org})
    agg: dict = {}
    ref_date = datetime.now(timezone.utc)
    async for r in db[USAGE].find({"organization_id": org}, {"_id": 0}):
        key = r["code_norm"]
        a = agg.get(key)
        if not a:
            a = agg[key] = {
                "code": r["code"], "code_norm": key, "description": r.get("description") or "",
                "total_qty": 0.0, "usage_count": 0, "total_cost": 0.0, "cost_rows": 0,
                "first_used": None, "last_used": None, "by_year": {}, "by_month": {},
                "months": set(), "descs": {},
            }
        qty = r.get("quantity") or 0
        a["total_qty"] += qty
        a["usage_count"] += 1
        if r.get("cost") is not None:
            a["total_cost"] += r["cost"]
            a["cost_rows"] += 1
        if r.get("description"):
            a["descs"][r["description"]] = a["descs"].get(r["description"], 0) + 1
        dt = _parse_dt(r.get("used_at")) if r.get("used_at") else None
        if dt:
            if dt > ref_date:
                ref_date = dt
            if not a["first_used"] or dt < a["first_used"]:
                a["first_used"] = dt
            if not a["last_used"] or dt > a["last_used"]:
                a["last_used"] = dt
            y = str(dt.year)
            a["by_year"][y] = a["by_year"].get(y, 0) + qty
            m = dt.strftime("%Y-%m")
            a["by_month"][m] = a["by_month"].get(m, 0) + qty
            a["months"].add(m)

    settings = await _data_settings(org)
    hi = settings["high_usage_threshold"]
    win = settings["recent_window_days"]
    cut_recent = ref_date - timedelta(days=win)
    cut_12m = ref_date - timedelta(days=365)

    ranked = sorted(agg.values(), key=lambda x: x["total_qty"], reverse=True)
    docs = []
    for rank, a in enumerate(ranked, start=1):
        first = a["first_used"]
        last = a["last_used"]
        months_active = max(1, len(a["months"]))
        avg_monthly = round(a["total_qty"] / months_active, 2)
        recent_90d = sum(q for m, q in a["by_month"].items() if _month_dt(m) and _month_dt(m) >= cut_recent)
        recent_12m = sum(q for m, q in a["by_month"].items() if _month_dt(m) and _month_dt(m) >= cut_12m)
        # dominant description
        desc = a["description"]
        if a["descs"]:
            desc = max(a["descs"].items(), key=lambda kv: kv[1])[0]
        trend = _classify_trend(a, last, first, recent_12m, ref_date)
        docs.append({
            "id": str(uuid.uuid4()), "organization_id": org,
            "code": a["code"], "code_norm": a["code_norm"], "description": desc,
            "alt_descriptions": sorted(a["descs"], key=lambda d: -a["descs"][d])[:5],
            "total_qty": round(a["total_qty"], 2), "usage_count": a["usage_count"],
            "total_cost": round(a["total_cost"], 2),
            "avg_cost": round(a["total_cost"] / a["cost_rows"], 2) if a["cost_rows"] else None,
            "first_used": first.isoformat() if first else None,
            "last_used": last.isoformat() if last else None,
            "by_year": {k: round(v, 2) for k, v in sorted(a["by_year"].items())},
            "by_month": {k: round(v, 2) for k, v in sorted(a["by_month"].items())},
            "avg_monthly": avg_monthly,
            "recent_90d": round(recent_90d, 2), "recent_12m": round(recent_12m, 2),
            "trend": trend, "rank": rank,
            "high_usage": a["total_qty"] >= hi,
            "warranty_relevant": True,
            "matched": False, "match_method": "none", "match_confidence": "none",
            "match_score": 0, "matched_bom_code": None, "matched_bom_description": None,
            "matched_models": [], "review_status": "pending",
        })
    if docs:
        for i in range(0, len(docs), 2000):
            await db[ANALYSIS].insert_many([dict(d) for d in docs[i:i + 2000]])
    return {"unique_parts": len(docs), "total_qty": round(sum(d["total_qty"] for d in docs), 2),
            "high_usage_parts": sum(1 for d in docs if d["high_usage"])}


def _month_dt(m: str):
    try:
        y, mm = m.split("-")
        return datetime(int(y), int(mm), 1, tzinfo=timezone.utc)
    except Exception:
        return None


def _classify_trend(a: dict, last, first, recent_12m: float, ref_date: datetime) -> str:
    if a["usage_count"] <= 1:
        return "one_off"
    if last and (ref_date - last).days > 365:
        return "dormant"
    if first and (ref_date - first).days <= 180 and a["usage_count"] >= 3:
        return "new_failure_trend"
    months_active = max(1, len(a["months"]))
    overall_monthly = a["total_qty"] / months_active
    recent_monthly = recent_12m / 12.0
    if overall_monthly <= 0:
        return "stable"
    ratio = recent_monthly / overall_monthly
    if ratio >= 1.3:
        return "increasing"
    if ratio <= 0.6:
        return "decreasing"
    return "stable"


# ─────────────────────────────────────────────────────────────────
# BOM import (versioned per top-level reference)
# ─────────────────────────────────────────────────────────────────

async def _import_bom(org: str, user: dict, content: bytes, filename: str) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = _find_sheet(wb, "BOMData")
    if ws is None:
        raise HTTPException(400, "Sheet 'BOMData' not found in workbook")
    hmap = _header_map(ws)
    c_tlr = _col(hmap, "Top Level BOM Reference")
    c_tsc = _col(hmap, "Top Level Stock Code")
    c_lvl = _col(hmap, "Level")
    c_bref = _col(hmap, "BOM Reference")
    c_bdesc = _col(hmap, "BOM Description")
    c_ltype = _col(hmap, "Line Type")
    c_code = _col(hmap, "Component/Sub-assembly Code", "Component Code")
    c_cdesc = _col(hmap, "Component/Sub-assembly Description", "Component Description")
    c_qty = _col(hmap, "Quantity", "Qty")
    if c_tlr is None or c_code is None:
        raise HTTPException(400, "Required columns missing (need Top Level BOM Reference + Component Code)")

    batch_id = str(uuid.uuid4())
    machines: dict = {}   # top_level_ref_norm -> machine doc
    components = []
    warnings = {"missing_code": 0, "missing_qty": 0, "missing_ref": 0, "duplicate_rows": 0}
    seen_rows = set()
    imported = skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        tlr = row[c_tlr] if c_tlr is not None else None
        code = row[c_code] if c_code is not None else None
        if not tlr or not str(tlr).strip():
            warnings["missing_ref"] += 1
            skipped += 1
            continue
        if not code or not str(code).strip():
            warnings["missing_code"] += 1
            skipped += 1
            continue
        tlr_norm = norm_code(tlr)
        code_norm = norm_code(code)
        bref = str(row[c_bref]).strip() if c_bref is not None and row[c_bref] else ""
        dup_key = (tlr_norm, norm_code(bref), code_norm)
        if dup_key in seen_rows:
            warnings["duplicate_rows"] += 1
        seen_rows.add(dup_key)
        try:
            qty = float(row[c_qty]) if c_qty is not None and row[c_qty] not in (None, "") else 1.0
        except (TypeError, ValueError):
            warnings["missing_qty"] += 1
            qty = 1.0
        m = machines.get(tlr_norm)
        if not m:
            m = machines[tlr_norm] = {
                "id": str(uuid.uuid4()), "organization_id": org, "batch_id": batch_id,
                "top_level_ref": str(tlr).strip(), "top_level_ref_norm": tlr_norm,
                "top_level_stock_code": str(row[c_tsc]).strip() if c_tsc is not None and row[c_tsc] else "",
                "description": str(row[c_bdesc]).strip() if c_bdesc is not None and row[c_bdesc] else "",
                "component_count": 0, "status": "active", "version": 1, "created_at": _now(),
            }
        m["component_count"] += 1
        if not m["description"] and c_bdesc is not None and row[c_bdesc]:
            m["description"] = str(row[c_bdesc]).strip()
        components.append({
            "id": str(uuid.uuid4()), "organization_id": org, "batch_id": batch_id,
            "machine_id": m["id"], "top_level_ref": str(tlr).strip(), "top_level_ref_norm": tlr_norm,
            "level": row[c_lvl] if c_lvl is not None else None,
            "bom_reference": bref, "bom_description": str(row[c_bdesc]).strip() if c_bdesc is not None and row[c_bdesc] else "",
            "line_type": str(row[c_ltype]).strip() if c_ltype is not None and row[c_ltype] else "",
            "code": str(code).strip(), "code_norm": code_norm,
            "description": str(row[c_cdesc]).strip() if c_cdesc is not None and row[c_cdesc] else "",
            "quantity": qty, "status": "active",
        })
        imported += 1
    wb.close()

    # Versioning: supersede existing active machines/components for refs in this file.
    refs = list(machines.keys())
    if refs:
        prev = {}
        async for doc in db[BOM_MACHINES].aggregate([
            {"$match": {"organization_id": org, "top_level_ref_norm": {"$in": refs}}},
            {"$group": {"_id": "$top_level_ref_norm", "maxv": {"$max": "$version"}}},
        ]):
            prev[doc["_id"]] = doc["maxv"]
        for ref, m in machines.items():
            m["version"] = prev.get(ref, 0) + 1
        await db[BOM_MACHINES].update_many(
            {"organization_id": org, "top_level_ref_norm": {"$in": refs}, "status": "active"},
            {"$set": {"status": "superseded", "updated_at": _now()}},
        )
        await db[BOM_COMPONENTS].update_many(
            {"organization_id": org, "top_level_ref_norm": {"$in": refs}, "status": "active"},
            {"$set": {"status": "superseded"}},
        )
        # re-point components to their machine version
        for c in components:
            c["version"] = machines[c["top_level_ref_norm"]]["version"]

    if machines:
        await db[BOM_MACHINES].insert_many([dict(m) for m in machines.values()])
    if components:
        for i in range(0, len(components), 3000):
            await db[BOM_COMPONENTS].insert_many([dict(c) for c in components[i:i + 3000]])

    batch = {
        "id": batch_id, "organization_id": org, "kind": "bom",
        "filename": filename, "status": "imported",
        "rows_imported": imported, "rows_skipped": skipped,
        "machines": len(machines), "unique_components": len({c["code_norm"] for c in components}),
        "warnings": warnings,
        "created_by": user.get("full_name") or user.get("email"), "created_at": _now(),
    }
    await db[BATCHES].insert_one(dict(batch))
    await _audit(org, user, "bom_imported", batch_id=batch_id, machines=len(machines), rows=imported)
    batch.pop("_id", None)
    return batch


# ─────────────────────────────────────────────────────────────────
# Import endpoints + batch management
# ─────────────────────────────────────────────────────────────────

@router.post("/import/parts-used")
async def import_parts_used(file: UploadFile = File(...), user=Depends(get_current_user)):
    org = _of(user)
    content = await file.read()
    return await _import_parts_used(org, user, content, file.filename or "parts_used.xlsx")


@router.post("/import/bom")
async def import_bom(file: UploadFile = File(...), user=Depends(get_current_user)):
    org = _of(user)
    content = await file.read()
    return await _import_bom(org, user, content, file.filename or "bom.xlsx")


# ── Chunked upload (bypasses the 2 MB ingress body limit) ─────────
import os as _os
import tempfile as _tempfile

_UPLOAD_DIR = _os.path.join(_tempfile.gettempdir(), "dp_uploads")
_os.makedirs(_UPLOAD_DIR, exist_ok=True)


def _upload_path(upload_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", upload_id)
    return _os.path.join(_UPLOAD_DIR, f"{safe}.part")


@router.post("/upload/init")
async def upload_init(user=Depends(get_current_user)):
    _of(user)
    upload_id = str(uuid.uuid4())
    open(_upload_path(upload_id), "wb").close()
    return {"upload_id": upload_id}


@router.post("/upload/{upload_id}/chunk")
async def upload_chunk(upload_id: str, chunk: UploadFile = File(...), user=Depends(get_current_user)):
    _of(user)
    path = _upload_path(upload_id)
    if not _os.path.exists(path):
        raise HTTPException(404, "Upload session not found")
    data = await chunk.read()
    with open(path, "ab") as fh:
        fh.write(data)
    return {"ok": True, "received": len(data), "total": _os.path.getsize(path)}


@router.post("/upload/{upload_id}/finish")
async def upload_finish(upload_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    path = _upload_path(upload_id)
    if not _os.path.exists(path):
        raise HTTPException(404, "Upload session not found")
    kind = (data.get("kind") or "").lower()
    filename = data.get("filename") or f"{kind}.xlsx"
    with open(path, "rb") as fh:
        content = fh.read()
    try:
        if kind == "parts_used":
            result = await _import_parts_used(org, user, content, filename)
        elif kind == "bom":
            result = await _import_bom(org, user, content, filename)
        else:
            raise HTTPException(400, "kind must be parts_used or bom")
    finally:
        try:
            _os.remove(path)
        except OSError:
            pass
    return result


@router.get("/imports")
async def list_imports(kind: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q = {"organization_id": org}
    if kind:
        q["kind"] = kind
    rows = await db[BATCHES].find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(200)
    return {"batches": rows, "count": len(rows)}


@router.post("/imports/{batch_id}/reverse")
async def reverse_import(batch_id: str, user=Depends(get_current_user)):
    org = _of(user)
    b = await db[BATCHES].find_one({"organization_id": org, "id": batch_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Import batch not found")
    if b.get("status") == "reversed":
        raise HTTPException(400, "Batch already reversed")
    if b["kind"] == "parts_used":
        await db[USAGE].delete_many({"organization_id": org, "batch_id": batch_id})
        await _rebuild_analysis(org)
    else:
        # reactivate the version this batch superseded
        machines = await db[BOM_MACHINES].find({"organization_id": org, "batch_id": batch_id}, {"_id": 0}).to_list(10000)
        refs = list({m["top_level_ref_norm"] for m in machines})
        await db[BOM_MACHINES].delete_many({"organization_id": org, "batch_id": batch_id})
        await db[BOM_COMPONENTS].delete_many({"organization_id": org, "batch_id": batch_id})
        for ref in refs:
            latest = await db[BOM_MACHINES].find_one(
                {"organization_id": org, "top_level_ref_norm": ref},
                sort=[("version", -1)])
            if latest:
                await db[BOM_MACHINES].update_one({"_id": latest["_id"]}, {"$set": {"status": "active"}})
                await db[BOM_COMPONENTS].update_many(
                    {"organization_id": org, "top_level_ref_norm": ref, "batch_id": latest["batch_id"]},
                    {"$set": {"status": "active"}})
    await db[BATCHES].update_one({"organization_id": org, "id": batch_id},
                                 {"$set": {"status": "reversed", "reversed_at": _now()}})
    await _audit(org, user, "import_reversed", batch_id=batch_id, kind=b["kind"])
    return {"ok": True, "batch_id": batch_id}


# ─────────────────────────────────────────────────────────────────
# Most-Used analysis + unmatched
# ─────────────────────────────────────────────────────────────────

@router.get("/most-used-analysis")
async def most_used_analysis(
    q: str = Query(""), trend: str = Query(""), matched: str = Query(""),
    review_status: str = Query(""), high_usage: str = Query(""),
    sort: str = Query("rank"), limit: int = Query(200),
    user=Depends(get_current_user),
):
    org = _of(user)
    query = {"organization_id": org}
    if q:
        rx = safe_regex(q)
        query["$or"] = [{"code": rx}, {"description": rx}]
    if trend:
        query["trend"] = trend
    if matched in ("true", "false"):
        query["matched"] = matched == "true"
    if review_status:
        query["review_status"] = review_status
    if high_usage == "true":
        query["high_usage"] = True
    sort_field = {"rank": ("rank", 1), "qty": ("total_qty", -1), "cost": ("total_cost", -1),
                  "recent": ("recent_12m", -1)}.get(sort, ("rank", 1))
    rows = await db[ANALYSIS].find(query, {"_id": 0}).sort([sort_field]).to_list(min(limit, 2000))
    total = await db[ANALYSIS].count_documents({"organization_id": org})
    matched_n = await db[ANALYSIS].count_documents({"organization_id": org, "matched": True})
    return {"parts": rows, "count": len(rows), "total": total, "matched": matched_n,
            "unmatched": total - matched_n}


@router.get("/unmatched")
async def unmatched_parts(limit: int = Query(200), user=Depends(get_current_user)):
    """High-usage unmatched parts, prioritised by total quantity used."""
    org = _of(user)
    rows = await db[ANALYSIS].find(
        {"organization_id": org, "matched": False},
        {"_id": 0},
    ).sort([("total_qty", -1)]).to_list(min(limit, 2000))
    return {"parts": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# Multi-stage matching engine
# ─────────────────────────────────────────────────────────────────

@router.post("/match/run")
async def run_matching(user=Depends(get_current_user)):
    org = _of(user)
    settings = await _data_settings(org)
    fuzzy_threshold = settings["fuzzy_threshold"]
    fuzzy_cutoff = int(fuzzy_threshold * 100)

    # Build BOM indexes from ACTIVE components.
    by_code_exact: dict = {}
    by_code_norm: dict = {}
    by_desc_norm: dict = {}
    comp_meta: dict = {}          # code_norm -> {code, description, refs:set}
    async for c in db[BOM_COMPONENTS].find(
        {"organization_id": org, "status": "active"},
        {"_id": 0, "code": 1, "code_norm": 1, "description": 1, "top_level_ref": 1},
    ):
        cn = c["code_norm"]
        meta = comp_meta.get(cn)
        if not meta:
            meta = comp_meta[cn] = {"code": c["code"], "description": c.get("description") or "", "refs": set()}
        if c.get("top_level_ref"):
            meta["refs"].add(c["top_level_ref"])
        by_code_norm.setdefault(cn, meta)
        by_code_exact.setdefault(c["code"], meta)
        dn = norm_desc(c.get("description"))
        if dn:
            by_desc_norm.setdefault(dn, meta)

    # Fuzzy candidate pool (deduped normalised descriptions → meta).
    fuzz_choices = {}   # desc_norm -> meta (first wins)
    for cn, meta in comp_meta.items():
        dn = norm_desc(meta["description"])
        if dn and dn not in fuzz_choices:
            fuzz_choices[dn] = meta
    fuzz_keys = list(fuzz_choices.keys())

    # Approved aliases: used code_norm -> bom code_norm
    alias_map: dict = {}
    async for a in db[ALIASES].find({"organization_id": org, "status": "approved"}, {"_id": 0}):
        alias_map[norm_code(a["from_code"])] = norm_code(a["to_code"])

    stats = {"exact_code": 0, "normalised_code": 0, "exact_description": 0,
             "normalised_description": 0, "fuzzy_description": 0, "alias": 0, "none": 0}
    await db[MATCHES].delete_many({"organization_id": org, "method": {"$ne": "manual"}})

    from rapidfuzz import process, fuzz as _rf

    analysis = await db[ANALYSIS].find({"organization_id": org}, {"_id": 0}).to_list(5000)
    analysis_updates = []
    match_docs = []
    for a in analysis:
        if a.get("match_method") == "manual" and a.get("matched"):
            continue  # preserve manual matches
        method = "none"
        meta = None
        if a["code"] in by_code_exact:
            meta, method = by_code_exact[a["code"]], "exact_code"
        elif a["code_norm"] in by_code_norm:
            meta, method = by_code_norm[a["code_norm"]], "normalised_code"
        elif a["code_norm"] in alias_map and alias_map[a["code_norm"]] in by_code_norm:
            meta, method = by_code_norm[alias_map[a["code_norm"]]], "alias"
        else:
            dn = norm_desc(a.get("description"))
            if dn and dn in by_desc_norm:
                meta, method = by_desc_norm[dn], "normalised_description"
            elif dn and fuzz_keys:
                hit = process.extractOne(dn, fuzz_keys, scorer=_rf.ratio, score_cutoff=fuzzy_cutoff)
                if hit:
                    meta, method = fuzz_choices[hit[0]], "fuzzy_description"

        auto_ok = (
            (method == "exact_code" and settings["auto_match_exact_code"]) or
            (method == "normalised_code" and settings["auto_match_normalised_code"]) or
            (method == "alias")
        )
        if meta and method != "none":
            refs = sorted(meta["refs"])[:50]
            review = "approved" if auto_ok else "pending"
            analysis_updates.append(({"organization_id": org, "id": a["id"]}, {"$set": {
                "matched": True, "match_method": method, "match_confidence": method,
                "match_score": CONF_RANK[method], "matched_bom_code": meta["code"],
                "matched_bom_description": meta["description"], "matched_models": refs,
                "review_status": review,
            }}))
            match_docs.append({
                "id": str(uuid.uuid4()), "organization_id": org,
                "used_code": a["code"], "used_code_norm": a["code_norm"],
                "used_description": a.get("description"),
                "bom_code": meta["code"], "bom_description": meta["description"],
                "top_level_refs": refs, "models": refs,
                "confidence": method, "score": CONF_RANK[method], "method": method,
                "review_status": review, "approved": review == "approved",
                "reviewed_by": None, "review_date": None, "created_at": _now(),
            })
            stats[method] += 1
        else:
            analysis_updates.append(({"organization_id": org, "id": a["id"]}, {"$set": {
                "matched": False, "match_method": "none", "match_confidence": "none",
                "match_score": 0, "matched_bom_code": None, "matched_models": [],
                "review_status": "unmatched"}}))
            stats["none"] += 1

    # Bulk apply.
    from pymongo import UpdateOne
    if analysis_updates:
        ops = [UpdateOne(f, u) for f, u in analysis_updates]
        for i in range(0, len(ops), 1000):
            await db[ANALYSIS].bulk_write(ops[i:i + 1000], ordered=False)
    if match_docs:
        for i in range(0, len(match_docs), 1000):
            await db[MATCHES].insert_many([dict(d) for d in match_docs[i:i + 1000]])

    await _audit(org, user, "match_run", **stats)
    total = sum(stats.values())
    return {"stats": stats, "total": total,
            "matched": total - stats["none"], "unmatched": stats["none"]}


@router.get("/matches")
async def list_matches(review_status: str = Query(""), method: str = Query(""),
                       limit: int = Query(300), user=Depends(get_current_user)):
    org = _of(user)
    q = {"organization_id": org}
    if review_status:
        q["review_status"] = review_status
    if method:
        q["method"] = method
    rows = await db[MATCHES].find(q, {"_id": 0}).sort([("score", -1)]).to_list(min(limit, 2000))
    return {"matches": rows, "count": len(rows)}


@router.post("/matches/{match_id}/review")
async def review_match(match_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    m = await db[MATCHES].find_one({"organization_id": org, "id": match_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Match not found")
    action = (data.get("action") or "").lower()
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    review = "approved" if action == "approve" else "rejected"
    await db[MATCHES].update_one({"organization_id": org, "id": match_id}, {"$set": {
        "review_status": review, "approved": action == "approve",
        "reviewed_by": user.get("full_name") or user.get("email"), "review_date": _now(),
    }})
    upd = {"review_status": review}
    if action == "reject":
        upd.update({"matched": False, "match_method": "none", "matched_bom_code": None, "matched_models": []})
    await db[ANALYSIS].update_one({"organization_id": org, "code_norm": m["used_code_norm"]}, {"$set": upd})
    await _audit(org, user, "match_reviewed", match_id=match_id, review_action=action, used_code=m["used_code"])
    return {"ok": True, "review_status": review}


# ─────────────────────────────────────────────────────────────────
# Aliases + unmatched actions
# ─────────────────────────────────────────────────────────────────

@router.get("/aliases")
async def list_aliases(status: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q = {"organization_id": org}
    if status:
        q["status"] = status
    rows = await db[ALIASES].find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    return {"aliases": rows, "count": len(rows)}


@router.post("/aliases")
async def create_alias(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    settings = await _data_settings(org)
    from_code = (data.get("from_code") or "").strip()
    to_code = (data.get("to_code") or "").strip()
    if not from_code or not to_code:
        raise HTTPException(400, "from_code and to_code required")
    status = "pending" if settings["require_alias_approval"] else "approved"
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org,
        "from_code": from_code, "from_code_norm": norm_code(from_code),
        "to_code": to_code, "to_code_norm": norm_code(to_code),
        "note": (data.get("note") or "").strip(),
        "status": status, "created_by": user.get("full_name") or user.get("email"), "created_at": _now(),
    }
    await db[ALIASES].insert_one(dict(doc))
    await _audit(org, user, "alias_created", from_code=from_code, to_code=to_code, status=status)
    doc.pop("_id", None)
    return doc


@router.post("/aliases/{alias_id}/review")
async def review_alias(alias_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    action = (data.get("action") or "").lower()
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    status = "approved" if action == "approve" else "rejected"
    r = await db[ALIASES].update_one({"organization_id": org, "id": alias_id},
                                     {"$set": {"status": status, "reviewed_by": user.get("full_name") or user.get("email"),
                                               "review_date": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Alias not found")
    await _audit(org, user, "alias_reviewed", alias_id=alias_id, review_action=action)
    return {"ok": True, "status": status}


@router.post("/unmatched/{code_norm}/action")
async def unmatched_action(code_norm: str, data: dict, user=Depends(get_current_user)):
    """Human-approved dispositions for an unmatched high-usage part."""
    org = _of(user)
    a = await db[ANALYSIS].find_one({"organization_id": org, "code_norm": code_norm}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Part not found in analysis")
    action = (data.get("action") or "").lower()
    valid = {"map_to_bom", "create_alias", "mark_obsolete", "not_dealer_relevant",
             "exclude_from_recommendations", "send_for_review"}
    if action not in valid:
        raise HTTPException(400, f"action must be one of {sorted(valid)}")
    upd = {}
    if action == "map_to_bom":
        bom_code = (data.get("bom_code") or "").strip()
        comp = await db[BOM_COMPONENTS].find_one(
            {"organization_id": org, "status": "active", "code_norm": norm_code(bom_code)}, {"_id": 0})
        if not comp:
            raise HTTPException(400, "bom_code not found in active BOM components")
        refs = await db[BOM_COMPONENTS].distinct(
            "top_level_ref", {"organization_id": org, "status": "active", "code_norm": norm_code(bom_code)})
        upd = {"matched": True, "match_method": "manual", "match_confidence": "manual", "match_score": 100,
               "matched_bom_code": comp["code"], "matched_bom_description": comp.get("description"),
               "matched_models": sorted(refs)[:50], "review_status": "approved"}
        await db[MATCHES].insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "used_code": a["code"], "used_code_norm": code_norm,
            "used_description": a.get("description"), "bom_code": comp["code"], "bom_description": comp.get("description"),
            "top_level_refs": sorted(refs)[:50], "models": sorted(refs)[:50], "confidence": "manual",
            "score": 100, "method": "manual", "review_status": "approved", "approved": True,
            "reviewed_by": user.get("full_name") or user.get("email"), "review_date": _now(), "created_at": _now()})
    elif action == "create_alias":
        await create_alias({"from_code": a["code"], "to_code": data.get("bom_code", ""),
                            "note": data.get("note", "Created from unmatched review")}, user)
        upd = {"review_status": "alias_pending"}
    elif action == "mark_obsolete":
        upd = {"review_status": "obsolete", "warranty_relevant": False}
    elif action == "not_dealer_relevant":
        upd = {"review_status": "not_relevant", "warranty_relevant": False}
    elif action == "exclude_from_recommendations":
        upd = {"review_status": "excluded", "warranty_relevant": False}
    elif action == "send_for_review":
        upd = {"review_status": "parts_team_review"}
    await db[ANALYSIS].update_one({"organization_id": org, "code_norm": code_norm}, {"$set": upd})
    await _audit(org, user, "unmatched_action", code=a["code"], review_action=action)
    return {"ok": True, "action": action, **upd}


# ─────────────────────────────────────────────────────────────────
# Machine → parts intelligence (Most-Used by machine)
# ─────────────────────────────────────────────────────────────────

@router.get("/machines")
async def list_machines(q: str = Query(""), limit: int = Query(100), user=Depends(get_current_user)):
    org = _of(user)
    query = {"organization_id": org, "status": "active"}
    if q:
        rx = safe_regex(q)
        query["$or"] = [{"top_level_ref": rx}, {"top_level_stock_code": rx}, {"description": rx}]
    rows = await db[BOM_MACHINES].find(query, {"_id": 0}).sort([("component_count", -1)]).to_list(min(limit, 500))
    total = await db[BOM_MACHINES].count_documents({"organization_id": org, "status": "active"})
    return {"machines": rows, "count": len(rows), "total": total}


PRIORITY_BY_TREND = {"increasing": 5, "new_failure_trend": 5, "stable": 3, "decreasing": 2,
                     "dormant": 1, "one_off": 1}


def _machine_priority(usage) -> str:
    if not usage:
        return "no_usage"
    qty = usage.get("total_qty", 0)
    trend = usage.get("trend", "stable")
    if qty >= 100 or trend in ("increasing", "new_failure_trend"):
        return "critical" if qty >= 200 else "recommended"
    if qty >= 20:
        return "recommended"
    if qty >= 5:
        return "optional"
    return "low"


@router.get("/machine-parts")
async def machine_parts(top_level_ref: str = Query(...), user=Depends(get_current_user)):
    """BOM components for a machine, ranked by historical usage → dealer-stock priority."""
    org = _of(user)
    ref_norm = norm_code(top_level_ref)
    machine = await db[BOM_MACHINES].find_one(
        {"organization_id": org, "top_level_ref_norm": ref_norm, "status": "active"}, {"_id": 0})
    if not machine:
        raise HTTPException(404, "Machine/BOM reference not found")
    comps = await db[BOM_COMPONENTS].find(
        {"organization_id": org, "top_level_ref_norm": ref_norm, "status": "active"}, {"_id": 0}).to_list(5000)
    # dedupe components by code (a BOM can list a code at multiple levels)
    comp_by_code: dict = {}
    for c in comps:
        cur = comp_by_code.get(c["code_norm"])
        if cur:
            cur["quantity"] += c.get("quantity") or 0
        else:
            comp_by_code[c["code_norm"]] = {"code": c["code"], "code_norm": c["code_norm"],
                                            "description": c.get("description"), "quantity": c.get("quantity") or 0,
                                            "line_type": c.get("line_type")}
    # join usage analysis
    usage_codes = list(comp_by_code.keys())
    usage_map = {}
    async for u in db[ANALYSIS].find({"organization_id": org, "code_norm": {"$in": usage_codes}}, {"_id": 0}):
        usage_map[u["code_norm"]] = u
    items = []
    for cn, c in comp_by_code.items():
        u = usage_map.get(cn)
        items.append({
            **c,
            "used_historically": bool(u),
            "total_qty_used": u.get("total_qty") if u else 0,
            "usage_count": u.get("usage_count") if u else 0,
            "recent_12m": u.get("recent_12m") if u else 0,
            "trend": u.get("trend") if u else None,
            "unit_cost": u.get("avg_cost") if u else None,
            "priority": _machine_priority(u),
        })
    items.sort(key=lambda x: (-(x["total_qty_used"] or 0), x["code"]))
    return {
        "machine": machine, "components": items, "component_count": len(items),
        "used_components": sum(1 for i in items if i["used_historically"]),
        "unused_components": sum(1 for i in items if not i["used_historically"]),
    }


@router.get("/settings")
async def get_data_settings(user=Depends(get_current_user)):
    return await _data_settings(_of(user))


@router.put("/settings")
async def update_data_settings(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    allowed = set(DEFAULT_DATA_SETTINGS.keys())
    upd = {k: v for k, v in data.items() if k in allowed}
    upd["updated_at"] = _now()
    await db[DATA_SETTINGS].update_one({"organization_id": org}, {"$set": upd}, upsert=True)
    await _audit(org, user, "data_settings_updated", **{k: str(v) for k, v in upd.items()})
    return await _data_settings(org)
