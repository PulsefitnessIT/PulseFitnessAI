"""
Sicon → Pulse EQUIPMENT import engine (spec §8–§11, §18–§23).

Read-only FROM Sicon: we only ever write to Pulse `db.equipment` (never back to
Sicon). Idempotent via the immutable `siconEquipmentId` + the external-link
table, so re-running never duplicates. Ambiguous matches go to a conflict queue
instead of creating/merging. Null/empty Sicon values never erase populated
Pulse fields, and Sicon `make` never overwrites the Pulse manufacturer.

Everything here is DB-backed + client-injectable so it is fully testable
offline (the live Sicon server is only reachable on the customer network).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from utils.database import db
from utils import sicon_links as links

logger = logging.getLogger(__name__)

# §19 — fields we treat as sync-from-Sicon on an EXISTING Pulse asset. Anything
# not listed (manufacturer, photos, manuals, condition, CAPEX, portal flags…)
# stays Pulse-authoritative and is never touched by an import.
SICON_SYNCED_FIELDS = (
    "serial_number", "install_date", "warranty_expiry",
    "last_service_date", "next_service_date",
)
# External ids / raw source metadata — always stored, never treated as user data.
SICON_ID_FIELDS = (
    "sicon_equipment_id", "sage_item_id", "sicon_item_code",
    "sicon_sub_location_id", "sicon_make_raw", "sicon_customer_code",
    "sicon_customer_id",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v):
    return v.strip() if isinstance(v, str) else v


def normalise_equipment(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw Sicon Equipment record → normalised Pulse-shaped fields.

    §9 CRITICAL: Sicon `make` (e.g. "200E-AAA") is an item code, NOT a
    manufacturer — it is preserved as `sicon_make_raw` and NEVER mapped to the
    Pulse `manufacturer` field.
    """
    return {
        "sicon_equipment_id": rec.get("siconEquipmentId"),
        "sage_item_id": rec.get("itemId"),
        "sicon_item_code": _clean(rec.get("itemCode")),
        "serial_number": _clean(rec.get("serialNumber")) or "",
        "description": _clean(rec.get("description")),
        "model": _clean(rec.get("model")),
        "sicon_make_raw": _clean(rec.get("make")),         # never → manufacturer
        "warranty_expiry": rec.get("warrantyExpiry"),
        "install_date": rec.get("installDate"),
        "last_service_date": rec.get("lastServiceDate"),
        "next_service_date": rec.get("nextServiceDate"),
        "notes": _clean(rec.get("notes")),
        "sicon_customer_id": rec.get("customerId"),
        "sicon_customer_code": _clean(rec.get("customerCode")),
        "customer_name": _clean(rec.get("customerName")),
        "sicon_sub_location_id": rec.get("siconSubLocationDbKey"),
        "location_full": _clean(rec.get("locationFull")),
    }


async def classify_equipment(norm: Dict[str, Any], org_id: str) -> Dict[str, Any]:
    """Decide what to do with a Sicon record (spec §10 A–E):
      linked   — already linked to a Pulse asset → update/sync
      match    — one confident existing Pulse asset → suggest link + update
      conflict — ambiguous (multiple candidates) → review queue, never merge
      new      — no legitimate existing asset → create
    """
    seid = norm.get("sicon_equipment_id")

    # A) already linked (link table OR an asset already carrying the id)
    if seid is not None:
        link = await links.get_link(links.ENTITY_EQUIPMENT, seid, org_id)
        if link and link.get("pulse_entity_id"):
            return {"bucket": "linked", "pulse_asset_id": link["pulse_entity_id"],
                    "confidence": "high", "reasons": ["already linked by siconEquipmentId"]}
        existing = await db.equipment.find_one(
            {"organization_id": org_id, "sicon_equipment_id": seid}, {"_id": 0, "id": 1})
        if existing:
            return {"bucket": "linked", "pulse_asset_id": existing["id"],
                    "confidence": "high", "reasons": ["asset already carries siconEquipmentId"]}

    # B) confidence match — serial number is the only reliable unique key.
    serial = norm.get("serial_number") or ""
    candidates: List[Dict[str, Any]] = []
    if serial:
        rows = await db.equipment.find(
            {"organization_id": org_id, "serial_number": serial},
            {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "manufacturer": 1, "model": 1},
        ).to_list(20)
        candidates = [{"id": r["id"], "signal": "serial", "asset": r} for r in rows]

    ids = {c["id"] for c in candidates}
    if len(ids) == 1:
        return {"bucket": "match", "pulse_asset_id": next(iter(ids)),
                "confidence": "high", "reasons": ["exact serial-number match"],
                "candidates": candidates}
    if len(ids) > 1:
        return {"bucket": "conflict", "confidence": "ambiguous",
                "reasons": [f"{len(ids)} Pulse assets share serial '{serial}'"],
                "candidates": candidates}
    # (item code / customer / model are shared across many units, so they are
    #  NOT used as auto-link signals — left as a future extension point.)
    return {"bucket": "new", "confidence": "none",
            "reasons": ["no existing Pulse asset matched"], "candidates": []}


def _sicon_update_set(existing: Dict[str, Any], norm: Dict[str, Any]) -> Dict[str, Any]:
    """Build the $set for an EXISTING asset: Sicon-synced fields only, and never
    overwrite a populated Pulse value with a null/empty Sicon value (§20)."""
    setdoc: Dict[str, Any] = {}
    for f in SICON_SYNCED_FIELDS:
        val = norm.get(f)
        if val in (None, "", 0):
            continue  # §20 — don't erase populated Pulse data with empty Sicon
        setdoc[f] = val
    for f in SICON_ID_FIELDS:
        val = norm.get(f)
        if val not in (None, ""):
            setdoc[f] = val
    setdoc["sicon_last_synced_at"] = _now()
    setdoc["updated_at"] = _now()
    return setdoc


def _new_asset_doc(org_id: str, norm: Dict[str, Any]) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": norm.get("description") or f"Sicon Equipment {norm.get('sicon_equipment_id')}",
        "description": norm.get("description") or "",
        "serial_number": norm.get("serial_number") or "",
        "model": norm.get("model") or "",
        "notes": norm.get("notes") or "",
        "status": "active",
        "source": "sicon_import",
        "imported_via": "sicon",
        "created_at": _now(),
        "updated_at": _now(),
        "sicon_last_synced_at": _now(),
    }
    for f in SICON_SYNCED_FIELDS:
        if norm.get(f) not in (None, "", 0):
            doc[f] = norm[f]
    for f in SICON_ID_FIELDS:
        if norm.get(f) not in (None, ""):
            doc[f] = norm[f]
    return doc


async def apply_equipment_record(org_id: str, norm: Dict[str, Any],
                                 classification: Dict[str, Any],
                                 run_id: str = "", user_id: str = "system") -> Dict[str, Any]:
    """Persist one classified record idempotently. Returns {action, pulse_asset_id}."""
    seid = norm.get("sicon_equipment_id")
    bucket = classification["bucket"]

    if bucket == "conflict":
        await _record_conflict(org_id, norm, classification, run_id)
        if seid is not None:
            await links.set_status(links.ENTITY_EQUIPMENT, seid, "conflict",
                                   reason=classification["reasons"][0], organization_id=org_id)
        return {"action": "conflict", "pulse_asset_id": None}

    if bucket in ("linked", "match"):
        asset_id = classification["pulse_asset_id"]
        existing = await db.equipment.find_one({"id": asset_id}, {"_id": 0}) or {}
        await db.equipment.update_one({"id": asset_id}, {"$set": _sicon_update_set(existing, norm)})
        if seid is not None:
            await links.upsert_link(links.ENTITY_EQUIPMENT, seid, "equipment", asset_id,
                                    organization_id=org_id, sync_status="linked")
        return {"action": "updated" if bucket == "linked" else "linked", "pulse_asset_id": asset_id}

    # new
    doc = _new_asset_doc(org_id, norm)
    await db.equipment.insert_one(doc)
    if seid is not None:
        await links.upsert_link(links.ENTITY_EQUIPMENT, seid, "equipment", doc["id"],
                                organization_id=org_id, sync_status="linked")
    return {"action": "created", "pulse_asset_id": doc["id"]}


async def _record_conflict(org_id: str, norm: Dict[str, Any],
                           classification: Dict[str, Any], run_id: str) -> None:
    seid = norm.get("sicon_equipment_id")
    key = {"organization_id": org_id, "external_entity_type": links.ENTITY_EQUIPMENT,
           "external_id": str(seid)}
    await db.sicon_import_conflicts.update_one(key, {"$set": {
        **key,
        "sicon_record": norm,
        "candidates": classification.get("candidates", []),
        "reasons": classification.get("reasons", []),
        "status": "open",
        "run_id": run_id,
        "updated_at": _now(),
    }, "$setOnInsert": {"created_at": _now()}}, upsert=True)


# ── Preview (classify without writing) ────────────────────────────
async def preview_equipment(org_id: str, client, max_records: int = 500) -> Dict[str, Any]:
    """Pull up to max_records from Sicon, classify each, return bucket counts +
    a sample. Writes NOTHING (spec §17)."""
    buckets = {"linked": 0, "match": 0, "conflict": 0, "new": 0, "failed": 0}
    sample: List[Dict[str, Any]] = []
    total_records = None
    processed = 0
    async for meta, records in client.svc_paginate("equipment"):
        if total_records is None:
            total_records = meta.get("totalRecords")
        for rec in records:
            try:
                norm = normalise_equipment(rec)
                cls = await classify_equipment(norm, org_id)
                buckets[cls["bucket"]] += 1
                if len(sample) < 50:
                    sample.append({"sicon_equipment_id": norm["sicon_equipment_id"],
                                   "serial_number": norm["serial_number"],
                                   "description": norm["description"],
                                   "customer_name": norm["customer_name"],
                                   "bucket": cls["bucket"], "confidence": cls["confidence"],
                                   "reasons": cls["reasons"]})
            except Exception as e:  # §23 — one bad record must not kill preview
                buckets["failed"] += 1
                logger.warning("preview classify failed: %s", e)
            processed += 1
            if processed >= max_records:
                break
        if processed >= max_records:
            break
    return {"total_in_sicon": total_records, "previewed": processed,
            "counts": buckets, "sample": sample}


# ── Sync (apply) ──────────────────────────────────────────────────
async def run_equipment_sync(org_id: str, client, max_records: int = 0,
                             run_id: Optional[str] = None, user_id: str = "system") -> Dict[str, Any]:
    """Idempotent, per-record-isolated equipment sync. max_records=0 → whole
    estate. Records a sync-run doc with counts + last checkpoint (spec §22/§23)."""
    run_id = run_id or str(uuid.uuid4())
    counts = {"created": 0, "linked": 0, "updated": 0, "conflict": 0, "failed": 0}
    await db.sicon_sync_runs.insert_one({
        "id": run_id, "organization_id": org_id, "entity": "equipment",
        "status": "running", "counts": counts, "started_at": _now(),
        "checkpoint_skip": 0, "user_id": user_id,
    })
    processed = 0
    last_skip = 0
    try:
        async for meta, records in client.svc_paginate("equipment"):
            for rec in records:
                try:
                    norm = normalise_equipment(rec)
                    cls = await classify_equipment(norm, org_id)
                    res = await apply_equipment_record(org_id, norm, cls, run_id, user_id)
                    counts[res["action"]] = counts.get(res["action"], 0) + 1
                except Exception as e:  # §23 failure isolation
                    counts["failed"] += 1
                    logger.warning("sync record failed (run %s): %s", run_id, e)
                processed += 1
                if max_records and processed >= max_records:
                    break
            last_skip = (meta.get("currentPage") or 1) * (meta.get("pageSize") or client.page_size)
            await db.sicon_sync_runs.update_one(
                {"id": run_id}, {"$set": {"counts": counts, "checkpoint_skip": last_skip}})
            if max_records and processed >= max_records:
                break
        status = "completed"
    except Exception as e:
        status = "failed"
        logger.error("equipment sync run %s aborted: %s", run_id, e)
    await db.sicon_sync_runs.update_one(
        {"id": run_id}, {"$set": {"status": status, "counts": counts,
                                  "processed": processed, "finished_at": _now()}})
    return {"run_id": run_id, "status": status, "processed": processed, "counts": counts}


# ── Dashboard stats ───────────────────────────────────────────────
async def dashboard_stats(org_id: str) -> Dict[str, Any]:
    equip = await links.counts_by_status(links.ENTITY_EQUIPMENT, org_id)
    cases = await links.counts_by_status(links.ENTITY_CASE, org_id)
    conflicts = await db.sicon_import_conflicts.count_documents(
        {"organization_id": org_id, "external_entity_type": links.ENTITY_EQUIPMENT, "status": "open"})
    last_run = await db.sicon_sync_runs.find_one(
        {"organization_id": org_id, "entity": "equipment"}, {"_id": 0}, sort=[("started_at", -1)])
    return {
        "equipment": {
            "linked": equip.get("linked", 0),
            "conflict": equip.get("conflict", 0),
            "open_conflicts": conflicts,
            "total_linked": equip.get("total", 0),
        },
        "cases": {"linked": cases.get("linked", 0), "total_linked": cases.get("total", 0)},
        "last_equipment_sync": last_run,
    }
