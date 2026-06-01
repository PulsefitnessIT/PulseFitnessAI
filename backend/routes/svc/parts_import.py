"""Iter 220ea·20 — Engineer App Phase 5 · Parts Catalogue + Bulk Import.

Phase 2 of the Stock Control system. Builds on the existing ``svc_parts``
catalogue and ``svc_van_stock`` — no duplicate business records. Adds:

  • A server-side paginated catalogue browser with facets + edit/bulk
    (``parts_catalogue.py``).
  • A 6-step CSV/Excel bulk import wizard (this file):
      parse  → upload + AI-suggested column mapping
      validate → dupes / missing / invalid + AI near-duplicate detection
      commit → upsert parts (+ optional van stock) + audit

The parsed file is staged server-side in ``svc_parts_import_sessions``
(transient working table) so thousands of rows aren't shuttled through
the browser on every step.

AI (column mapping + near-duplicate detection) reuses the established
Emergent LLM pattern (Claude via ``emergentintegrations``); it is
strictly advisory and never mutates data without explicit confirmation.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/parts/import", tags=["Service Ops · Parts Import"])

MAX_ROWS = 10000  # per import; larger catalogues (e.g. Pulse 8k+) fit in one file

# Canonical target fields → synonyms (normalised) for heuristic mapping.
CANONICAL_FIELDS: dict[str, list[str]] = {
    "sku": ["partnumber", "part", "partno", "sku", "code", "stockcode", "itemcode", "partcode"],
    "name": ["name", "partname", "description", "itemname", "title", "product"],
    "description": ["longdescription", "fulldescription", "details", "desc", "notes2"],
    "manufacturer": ["manufacturer", "make", "brand", "oem"],
    "mfr_part_number": ["manufacturerpartnumber", "mfrpartnumber", "mpn", "oempartnumber"],
    "supplier": ["supplier", "vendor", "supplyname"],
    "supplier_part_number": ["supplierpartnumber", "vendorpartnumber", "spn", "suppliercode"],
    "category": ["category", "group", "type", "parttype", "productgroup"],
    "cost": ["cost", "costprice", "buyprice", "purchaseprice", "unitcost", "nett"],
    "list_price": ["sellprice", "sellingprice", "saleprice", "listprice", "rrp", "retail", "price"],
    "van_qty": ["quantity", "qty", "stock", "onhand", "vanqty", "stockqty", "instock"],
    "reorder_threshold": ["minstock", "minimumstock", "minstocklevel", "minlevel", "min", "reorderpoint"],
    "reorder_max": ["maxstock", "maximumstock", "maxstocklevel", "maxlevel", "max", "targetstock", "targetlevel"],
    "reorder_qty": ["reorderlevel", "reorderquantity", "reorderqty", "orderqty", "ordermultiple"],
    "bin_location": ["binlocation", "location", "bin", "vanlocation", "shelf", "position"],
    "compatible_models": ["compatiblemodel", "compatiblemodels", "model", "models", "fitsmodel"],
    "notes": ["notes", "comment", "comments", "remarks", "memo"],
}
REQUIRED_FIELDS = {"sku", "name"}
NUMERIC_FIELDS = {"cost", "list_price", "van_qty", "reorder_threshold", "reorder_max", "reorder_qty"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _can_manage(user: dict) -> bool:
    """Bulk import is an owner/admin/manager action (solo engineers are
    ``owner`` → allowed; enterprise field engineers are not)."""
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("account_type") == "gymaxis_admin"
        or (user.get("role") or "") in {"owner", "owner_admin", "manager"}
    )


def _require_manage(user: dict):
    if not _can_manage(user):
        raise HTTPException(403, "Bulk import requires an owner/admin/manager role")


def _norm(h: str) -> str:
    return "".join(c for c in (h or "").lower() if c.isalnum())


def _heuristic_mapping(headers: list[str]) -> dict[str, Optional[str]]:
    """Best-guess {header → canonical field} by normalised synonym match."""
    out: dict[str, Optional[str]] = {}
    used: set[str] = set()
    for h in headers:
        n = _norm(h)
        match = None
        # exact synonym first, then substring
        for field, syns in CANONICAL_FIELDS.items():
            if field in used:
                continue
            if n in syns:
                match = field
                break
        if not match:
            for field, syns in CANONICAL_FIELDS.items():
                if field in used:
                    continue
                if any(n == s or (len(n) > 3 and (n in s or s in n)) for s in syns):
                    match = field
                    break
        if match:
            used.add(match)
        out[h] = match
    return out


# ─── AI column-mapping + near-duplicate detection (advisory) ──────────


def _emergent_key() -> Optional[str]:
    return os.environ.get("EMERGENT_LLM_KEY") or None


def _extract_json(text: str):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        t = t.lstrip("json").strip()
    try:
        return json.loads(t)
    except Exception:
        start = t.find("{")
        end = t.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(t[start:end + 1])
            except Exception:
                return None
    return None


async def _llm_json(system: str, prompt: str, *, session_id: str):
    key = _emergent_key()
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(api_key=key, session_id=session_id,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        return _extract_json(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[parts-import] llm failed: %s", exc)
        return None


async def _ai_mapping(headers: list[str], sample: list[dict]) -> dict:
    """Ask Claude to map headers → canonical fields. Advisory only."""
    fields = ", ".join(CANONICAL_FIELDS.keys())
    prompt = (
        "Map each spreadsheet column header to ONE of these canonical "
        f"part fields (or null if none fit): {fields}.\n"
        f"Headers: {json.dumps(headers)}\n"
        f"Sample rows: {json.dumps(sample[:3])}\n"
        'Return ONLY JSON: {"header name": "canonical_field_or_null", ...}.'
    )
    data = await _llm_json(
        "You map messy supplier spreadsheet columns to a fixed schema. "
        "Output strict JSON only.", prompt, session_id=f"map-{uuid.uuid4()}")
    if not isinstance(data, dict):
        return {}
    valid = set(CANONICAL_FIELDS.keys())
    return {h: (v if v in valid else None) for h, v in data.items() if h in headers}


# ─── File parsing ─────────────────────────────────────────────────────


def _parse_csv(raw: bytes) -> tuple[list[str], list[dict]]:
    text = raw.decode("utf-8-sig", errors="replace")
    sniff = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sniff, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        return [], []
    headers = [str(h).strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any((c or "").strip() for c in r):
            continue
        out.append({headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))})
    return headers, out


def _parse_xlsx(raw: bytes) -> tuple[list[str], list[dict]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], []
    headers = [str(h).strip() if h is not None else f"col{i}"
               for i, h in enumerate(header_row)]
    out = []
    for r in rows_iter:
        if r is None or not any(c is not None and str(c).strip() for c in r):
            continue
        out.append({headers[i]: ("" if i >= len(r) or r[i] is None else str(r[i]))
                    for i in range(len(headers))})
    wb.close()
    return headers, out


@router.post("/parse")
async def parse_import(
    file: UploadFile = File(...),
    use_ai: str = Form("true"),
    user=Depends(get_current_user),
):
    """Step 1-2: upload a CSV/Excel file → headers, sample, AI mapping."""
    _require_manage(user)
    of = _of(user)
    name = (file.filename or "").lower()
    raw = await file.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 12MB) — split it and retry")
    try:
        if name.endswith((".xlsx", ".xlsm")):
            headers, rows = _parse_xlsx(raw)
        elif name.endswith(".csv") or name.endswith(".txt"):
            headers, rows = _parse_csv(raw)
        else:
            raise HTTPException(415, "Unsupported file — upload .csv or .xlsx")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("[parts-import] parse failed: %s", exc)
        raise HTTPException(400, f"Could not read file: {exc}") from exc

    if not headers:
        raise HTTPException(400, "No columns found in the file")
    if len(rows) == 0:
        raise HTTPException(400, "No data rows found in the file")
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            413, f"{len(rows)} rows exceeds the {MAX_ROWS}-row limit — split the file")

    mapping = _heuristic_mapping(headers)
    if (use_ai or "").lower() == "true":
        ai = await _ai_mapping(headers, rows[:3])
        # AI fills gaps + overrides nulls; heuristic wins on conflict only
        # when AI returned null.
        for h, field in ai.items():
            if field and not mapping.get(h):
                mapping[h] = field

    session = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "created_by": user["id"],
        "filename": file.filename,
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "status": "parsed",
        "created_at": _now(),
    }
    await db.svc_parts_import_sessions.insert_one(session)
    return {
        "session_id": session["id"],
        "filename": file.filename,
        "headers": headers,
        "row_count": len(rows),
        "sample": rows[:5],
        "suggested_mapping": mapping,
        "canonical_fields": list(CANONICAL_FIELDS.keys()),
        "required_fields": sorted(REQUIRED_FIELDS),
    }


def _mapped_row(raw_row: dict, inv_map: dict) -> dict:
    """raw header→value + {canonical→header} → canonical dict."""
    out: dict = {}
    for field, header in inv_map.items():
        out[field] = (raw_row.get(header) or "").strip() if header else ""
    return out


def _to_num(v: str):
    if v is None or str(v).strip() == "":
        return None
    s = str(v).replace("£", "").replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


async def _load_session(session_id: str, of: dict) -> dict:
    s = await db.svc_parts_import_sessions.find_one(
        {"id": session_id, **of}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Import session not found or expired")
    return s


@router.post("/validate")
async def validate_import(body: dict, user=Depends(get_current_user)):
    """Step 3-4: validate the mapped rows + flag duplicates."""
    _require_manage(user)
    of = _of(user)
    session_id = body.get("session_id")
    mapping = body.get("mapping") or {}  # {header: canonical|null}
    use_ai = bool(body.get("use_ai", False))
    s = await _load_session(session_id, of)

    inv_map = {field: h for h, field in mapping.items() if field}
    missing_required = [f for f in REQUIRED_FIELDS if f not in inv_map]
    if missing_required:
        raise HTTPException(
            422, f"Map required field(s): {', '.join(missing_required)}")

    rows = s["rows"]
    mapped = [_mapped_row(r, inv_map) for r in rows]

    # Existing catalogue SKUs (for create-vs-update + dupe detection)
    existing = await db.svc_parts.find(
        of, {"_id": 0, "sku": 1, "name": 1}).to_list(20000)
    existing_skus = {p["sku"] for p in existing}

    issues: list[dict] = []
    seen: dict[str, int] = {}
    valid = 0
    new_count = update_count = 0
    for idx, m in enumerate(mapped):
        sku = (m.get("sku") or "").strip().upper()
        row_issues = []
        if not sku:
            row_issues.append(("sku", "error", "Missing part number"))
        if not (m.get("name") or "").strip():
            row_issues.append(("name", "error", "Missing part name"))
        for nf in NUMERIC_FIELDS:
            raw = m.get(nf)
            if raw:
                num = _to_num(raw)
                if num is None:
                    row_issues.append((nf, "error", f"'{raw}' is not a valid number"))
                elif num < 0:
                    row_issues.append((nf, "error", f"{nf} cannot be negative"))
        if sku:
            if sku in seen:
                row_issues.append(("sku", "warning",
                                   f"Duplicate of row {seen[sku] + 1} in this file"))
            else:
                seen[sku] = idx
            if sku in existing_skus:
                update_count += 1
            else:
                new_count += 1
        if not any(sev == "error" for _, sev, _ in row_issues):
            valid += 1
        for field, sev, msg in row_issues:
            issues.append({"row": idx, "field": field, "severity": sev, "message": msg})

    # AI near-duplicate detection (advisory) — distinct SKUs, similar names.
    ai_duplicates = []
    if use_ai:
        names = [{"row": i, "sku": (m.get("sku") or "").upper(), "name": m.get("name") or ""}
                 for i, m in enumerate(mapped) if (m.get("name") or "").strip()][:120]
        data = await _llm_json(
            "You find likely DUPLICATE parts (same physical item, different "
            "SKU or spelling) in a list. Output strict JSON only.",
            "From this list, return groups that are likely the SAME part.\n"
            f"{json.dumps(names)}\n"
            'Return ONLY JSON: {"groups": [{"rows": [int,int], "reason": "..."}]}.'
            " Only include high-confidence groups; empty if none.",
            session_id=f"dedupe-{uuid.uuid4()}")
        if isinstance(data, dict) and isinstance(data.get("groups"), list):
            ai_duplicates = data["groups"][:50]

    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    await db.svc_parts_import_sessions.update_one(
        {"id": session_id, **of},
        {"$set": {"mapping": mapping, "status": "validated", "validated_at": _now()}})
    return {
        "session_id": session_id,
        "summary": {
            "total": len(mapped), "valid": valid,
            "errors": error_count, "warnings": warning_count,
            "new": new_count, "update": update_count,
        },
        "issues": issues[:500],
        "preview": [{**_mapped_row(rows[i], inv_map), "_row": i} for i in range(min(len(rows), 20))],
        "ai_duplicates": ai_duplicates,
    }


@router.post("/commit")
async def commit_import(body: dict, user=Depends(get_current_user)):
    """Step 5-6: apply the import + write an audit record."""
    _require_manage(user)
    of = _of(user)
    session_id = body.get("session_id")
    mapping = body.get("mapping") or {}
    options = body.get("options") or {}
    mode = (options.get("mode") or "upsert").lower()          # add_new|update_existing|upsert
    # Iter 220ea·22 — stock destination: where mapped quantities land.
    #   catalogue → don't touch stock · warehouse → svc_warehouse_stock
    #   van → svc_van_stock for target_engineer_id
    van_mode = (options.get("van_qty_mode") or "set").lower()  # set|adjust|ignore (legacy)
    stock_location = (options.get("stock_location") or "").lower()
    if stock_location not in ("catalogue", "warehouse", "van"):
        # Back-compat: derive from the legacy van_qty_mode.
        stock_location = "catalogue" if van_mode == "ignore" else "van"
    qty_mode = (options.get("qty_mode") or van_mode or "set").lower()  # set|adjust
    if qty_mode not in ("set", "adjust"):
        qty_mode = "set"
    skip_dupes = bool(options.get("skip_duplicates", True))
    target_eng = options.get("target_engineer_id") or user["id"]

    s = await _load_session(session_id, of)
    inv_map = {field: h for h, field in mapping.items() if field}
    if "sku" not in inv_map or "name" not in inv_map:
        raise HTTPException(422, "Part number and name must be mapped")

    rows = s["rows"]
    existing = await db.svc_parts.find(of, {"_id": 0, "sku": 1}).to_list(20000)
    existing_skus = {p["sku"] for p in existing}

    created = updated = skipped = van_adjusted = 0
    seen: set[str] = set()
    errors = 0
    for r in rows:
        m = _mapped_row(r, inv_map)
        sku = (m.get("sku") or "").strip().upper()
        name = (m.get("name") or "").strip()
        if not sku or not name:
            errors += 1
            continue
        if sku in seen and skip_dupes:
            skipped += 1
            continue
        seen.add(sku)
        is_update = sku in existing_skus
        if mode == "add_new" and is_update:
            skipped += 1
            continue
        if mode == "update_existing" and not is_update:
            skipped += 1
            continue

        fields = {"name": name, "updated_at": _now()}
        for f in ("description", "manufacturer", "mfr_part_number", "supplier",
                  "supplier_part_number", "category", "bin_location", "notes"):
            if m.get(f):
                fields[f] = m[f]
        if m.get("compatible_models"):
            fields["compatible_models"] = [x.strip() for x in m["compatible_models"].split(",") if x.strip()]
        for f in ("cost", "list_price", "reorder_threshold", "reorder_max", "reorder_qty"):
            num = _to_num(m.get(f))
            if num is not None:
                fields[f] = num if f in {"cost", "list_price"} else int(num)

        res = await db.svc_parts.update_one(
            {**of, "sku": sku},
            {"$set": fields,
             "$setOnInsert": {"id": str(uuid.uuid4()), "sku": sku,
                              "organization_id": of["organization_id"],
                              "active": True, "created_at": _now()}},
            upsert=True)
        if res.upserted_id is not None:
            created += 1
            existing_skus.add(sku)
        else:
            updated += 1

        # Stock quantity (optional) → warehouse or a chosen engineer's van.
        if stock_location != "catalogue":
            qnum = _to_num(m.get("van_qty"))
            if qnum is not None:
                qty = int(qnum)
                sset = {"updated_at": _now()}
                if m.get("bin_location"):
                    sset["bin_location"] = m["bin_location"]
                if qty_mode == "adjust":
                    set_part = {"$inc": {"qty": qty}, "$set": sset}
                else:  # set
                    sset["qty"] = qty
                    set_part = {"$set": sset}
                if stock_location == "warehouse":
                    on_insert = {"id": str(uuid.uuid4()), "created_at": _now(),
                                 "location": "warehouse"}
                    await db.svc_warehouse_stock.update_one(
                        {**of, "location": "warehouse", "part_sku": sku},
                        {**set_part, "$setOnInsert": on_insert}, upsert=True)
                    to_loc, eng_for_move = "warehouse", ""
                else:  # van
                    on_insert = {"id": str(uuid.uuid4()), "created_at": _now()}
                    await db.svc_van_stock.update_one(
                        {**of, "engineer_id": target_eng, "part_sku": sku},
                        {**set_part, "$setOnInsert": on_insert}, upsert=True)
                    to_loc, eng_for_move = "van", target_eng
                await db.svc_part_movements.insert_one({
                    "id": str(uuid.uuid4()), "organization_id": of["organization_id"],
                    "movement_type": "import", "part_sku": sku, "part_name": name,
                    "qty": qty, "from_location": "import", "to_location": to_loc,
                    "engineer_id": eng_for_move, "actor_id": user["id"],
                    "actor_name": user.get("full_name") or user.get("email") or "",
                    "at": _now(), "import_session_id": session_id})
                van_adjusted += 1

    summary = {"created": created, "updated": updated, "skipped": skipped,
               "errors": errors, "stock_lines": van_adjusted, "van_adjusted": van_adjusted,
               "stock_location": stock_location, "rows": len(rows)}
    audit = {
        "id": str(uuid.uuid4()), "organization_id": of["organization_id"],
        "import_session_id": session_id, "filename": s.get("filename"),
        "actor_id": user["id"],
        "actor_name": user.get("full_name") or user.get("email") or "",
        "mode": mode, "van_qty_mode": van_mode, "stock_location": stock_location,
        "qty_mode": qty_mode,
        "target_engineer_id": (target_eng if stock_location == "van" else None),
        "summary": summary, "at": _now(),
    }
    await db.svc_parts_import_audit.insert_one(audit)
    await db.svc_parts_import_sessions.update_one(
        {"id": session_id, **of},
        {"$set": {"status": "committed", "committed_at": _now(), "summary": summary}})
    audit.pop("_id", None)
    return {"ok": True, "summary": summary, "import_id": audit["id"]}


@router.get("/audit")
async def import_audit(limit: int = 20, user=Depends(get_current_user)):
    """Recent import runs (audit trail)."""
    _require_manage(user)
    of = _of(user)
    rows = await db.svc_parts_import_audit.find(of, {"_id": 0}) \
        .sort("at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
    return {"items": rows}


__all__ = ["router"]
