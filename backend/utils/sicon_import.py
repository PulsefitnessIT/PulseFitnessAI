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
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from utils.database import db
from utils import sicon_links as links
from utils.sicon_client import _extract_records

logger = logging.getLogger(__name__)

# ── Per-org sync concurrency lock ─────────────────────────────────
# A full estate can be 100k+ equipment lines, so a single sync run may take
# many minutes. The nightly cron and a manual "Sync" click could otherwise
# fire at the same time, doubling API load and racing on the same records.
# One lock per (organization_id, entity) guarantees only ONE sync of each kind
# runs per org at a time. A heartbeat keeps a long-running (but healthy) run
# from being considered dead; a stale lock (no heartbeat) is taken over so a
# crashed process can never wedge the integration permanently.
LOCK_STALE_MINUTES = 120

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


async def acquire_sync_lock(org_id: str, entity: str, run_id: str) -> bool:
    """Try to acquire the per-org sync lock for `entity` ('equipment'|'case').

    Returns True if acquired. Only acquires when no live lock is held (either
    unlocked, or the previous holder's heartbeat is older than
    LOCK_STALE_MINUTES → the holder crashed and we take over)."""
    key = {"organization_id": org_id, "entity": entity}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    stale_iso = (now - timedelta(minutes=LOCK_STALE_MINUTES)).isoformat()
    # Ensure the lock doc exists (idempotent). Unique index on (org, entity)
    # makes concurrent inserts collapse to one — swallow the dup-key race.
    try:
        await db.sicon_sync_locks.update_one(
            key, {"$setOnInsert": {**key, "locked": False}}, upsert=True)
    except Exception:
        pass
    res = await db.sicon_sync_locks.update_one(
        {**key, "$or": [{"locked": {"$ne": True}}, {"heartbeat_at": {"$lt": stale_iso}}]},
        {"$set": {"locked": True, "run_id": run_id,
                  "acquired_at": now_iso, "heartbeat_at": now_iso}},
    )
    return res.modified_count == 1


async def touch_sync_lock(org_id: str, entity: str, run_id: str) -> None:
    """Bump the heartbeat so a healthy long-running sync is never seen as stale."""
    await db.sicon_sync_locks.update_one(
        {"organization_id": org_id, "entity": entity, "run_id": run_id},
        {"$set": {"heartbeat_at": _now()}})


async def release_sync_lock(org_id: str, entity: str, run_id: str) -> None:
    """Release the lock (only if we still hold it, matched by run_id)."""
    await db.sicon_sync_locks.update_one(
        {"organization_id": org_id, "entity": entity, "run_id": run_id},
        {"$set": {"locked": False, "released_at": _now()}})


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
                                 run_id: str = "", user_id: str = "system",
                                 fill_gaps: bool = False) -> Dict[str, Any]:
    """Persist one classified record idempotently. Returns {action, pulse_asset_id}.
    fill_gaps=True (onboarding): never change a populated Pulse field; differences
    are queued for review instead."""
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
        setdoc = _sicon_update_set(existing, norm)
        if fill_gaps:
            from utils.sicon_onboarding import gap_fill
            for f in SICON_SYNCED_FIELDS:
                setdoc.pop(f, None)
            setdoc.update(await gap_fill(org_id, "equipment", seid, asset_id, existing,
                                         {f: norm.get(f) for f in (*SICON_SYNCED_FIELDS, "model")}, run_id))
        linkfields = await _resolve_equipment_links(org_id, norm, existing)
        setdoc.update(linkfields)
        await db.equipment.update_one({"id": asset_id}, {"$set": setdoc})
        if seid is not None:
            await links.upsert_link(links.ENTITY_EQUIPMENT, seid, "equipment", asset_id,
                                    organization_id=org_id, sync_status="linked")
        return {"action": "updated" if bucket == "linked" else "linked", "pulse_asset_id": asset_id}

    # new
    doc = _new_asset_doc(org_id, norm)
    doc.update(await _resolve_equipment_links(org_id, norm, {}))
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
    if not await acquire_sync_lock(org_id, "equipment", run_id):
        await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
            "id": run_id, "organization_id": org_id, "entity": "equipment",
            "status": "skipped_locked", "counts": counts, "finished_at": _now(),
            "skip_reason": "another equipment sync is already running for this organisation",
        }}, upsert=True)
        logger.info("equipment sync %s skipped — lock already held for org %s", run_id, org_id)
        return {"run_id": run_id, "status": "skipped_locked", "processed": 0, "counts": counts}
    await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
        "id": run_id, "organization_id": org_id, "entity": "equipment",
        "status": "running", "counts": counts, "started_at": _now(),
        "checkpoint_skip": 0, "user_id": user_id,
    }}, upsert=True)
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
            await touch_sync_lock(org_id, "equipment", run_id)
            if max_records and processed >= max_records:
                break
        status = "completed"
    except Exception as e:
        status = "failed"
        logger.error("equipment sync run %s aborted: %s", run_id, e)
    finally:
        await release_sync_lock(org_id, "equipment", run_id)
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


# ══════════════════════════════════════════════════════════════════
# CASESEARCH → SERVICE DESK (db.issues) — Increment C
# Idempotent by siSMCaseId (permanent key, §12). Reference data (case type /
# priority / tracking status) resolved through per-org CONFIGURABLE maps stored
# on sicon_config; customer/site resolved via the external-link table.
# ══════════════════════════════════════════════════════════════════

# Sensible fallbacks when no explicit mapping is configured yet.
_DEFAULT_STATUS = "open"
_DEFAULT_SEVERITY = "operational_fault"


def _id_name(v):
    if isinstance(v, dict):
        return (v.get("siSMPriorityId") or v.get("siSMTrackingStatusId")
                or v.get("siSMCaseTypeId") or v.get("id")), v.get("name")
    return None, v


def normalise_case(rec: Dict[str, Any]) -> Dict[str, Any]:
    pr_id, pr_name = _id_name(rec.get("priority"))
    ts_id, ts_name = _id_name(rec.get("trackingStatus"))
    ct_id, ct_name = _id_name(rec.get("caseType"))
    proj = rec.get("project") or {}
    return {
        "si_sm_case_id": rec.get("siSMCaseId"),
        "case_number": rec.get("caseNumber"),
        "summary": _clean(rec.get("summary")),
        "customer_name": _clean(rec.get("customerName")),
        "contact_name": _clean(rec.get("contactName")),
        "tracking_status_id": ts_id, "tracking_status_name": ts_name,
        "priority_id": pr_id, "priority_name": pr_name,
        "case_type_id": ct_id, "case_type_name": ct_name,
        "logged_date": rec.get("loggedDate"),
        "last_tracking_date": rec.get("lastTrackingDate"),
        "next_appointment_date": rec.get("nextAppointmentDate"),
        "customer_order_number": _clean(rec.get("customerOrderNumber")),
        "sicon_customer_id": rec.get("customerId"),
        "sicon_customer_code": _clean(rec.get("customerCode")),
        "sicon_sub_location_id": rec.get("siconSubLocationDbKey"),
        "sicon_project_job_id": proj.get("siJcJobId"),
        "project_number": proj.get("jobNumber"),
    }


def _map_lookup(mapping: Dict[str, Any], key_id, key_name, default):
    """Explicit-mapping resolution (§13 — no hardcoded business logic).
    Try the Sicon id (as str) first, then the name; else the default."""
    if not isinstance(mapping, dict):
        return default
    if key_id is not None and str(key_id) in mapping:
        return mapping[str(key_id)]
    if key_name and key_name in mapping:
        return mapping[key_name]
    return default


def resolve_case_fields(norm: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    status = _map_lookup(config.get("tracking_status_mapping"),
                         norm.get("tracking_status_id"), norm.get("tracking_status_name"),
                         _DEFAULT_STATUS)
    severity = _map_lookup(config.get("priority_mapping"),
                           norm.get("priority_id"), norm.get("priority_name"),
                           config.get("default_severity") or _DEFAULT_SEVERITY)
    return {"status": status, "severity": severity}


async def _resolve_case_links(org_id: str, norm: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    company_id = await resolve_company(org_id, norm.get("sicon_customer_id"), norm.get("sicon_customer_code"))
    if company_id:
        out["company_id"] = company_id
    site_id = await resolve_site(org_id, norm.get("sicon_sub_location_id"))
    if site_id:
        out["site_id"] = site_id
    return out


async def resolve_company(org_id: str, sicon_customer_id, sicon_customer_code) -> Optional[str]:
    """Auto-resolve a Sicon customer → Pulse CRM company, hands-off (§11):
      1) an existing stored link (manual or previously auto-created);
      2) a DEFINITIVE code match: crm2_companies.sage_customer_id == the Sicon
         customerCode (or customerId). A unique hit is auto-linked and
         remembered so it's instant next time.
    Never matches on name alone. Returns None when not definitive."""
    if sicon_customer_id is not None:
        cid = await links.get_pulse_id(links.ENTITY_CUSTOMER, sicon_customer_id, org_id)
        if cid:
            return cid
    code = sicon_customer_code or (str(sicon_customer_id) if sicon_customer_id is not None else None)
    if code:
        matches = await db.crm2_companies.find(
            {"organization_id": org_id, "sage_customer_id": code}, {"_id": 0, "id": 1}).to_list(3)
        if len(matches) == 1:
            cid = matches[0]["id"]
            if sicon_customer_id is not None:
                await links.upsert_link(links.ENTITY_CUSTOMER, sicon_customer_id, "crm2_company", cid,
                                        organization_id=org_id, sync_status="auto")
            return cid
    return None


async def _resolve_equipment_links(org_id: str, norm: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    """Auto customer/site link for an asset. Never overwrites a company/site a
    Pulse user has already set (§20) — only fills when empty."""
    out: Dict[str, Any] = {}
    if not existing.get("company_id"):
        cid = await resolve_company(org_id, norm.get("sicon_customer_id"), norm.get("sicon_customer_code"))
        if cid:
            out["company_id"] = cid
    if not existing.get("site_id"):
        sid = await resolve_site(org_id, norm.get("sicon_sub_location_id"))
        if sid:
            out["site_id"] = sid
    return out


async def resolve_site(org_id: str, sicon_sub_location_id) -> Optional[str]:
    """Auto-resolve a Sicon sub-location → Pulse site (§11): stored link first,
    else a unique crm2_sites.sicon_sub_location_id match (auto-linked). No
    name-guessing; None when not definitive."""
    if sicon_sub_location_id is None:
        return None
    sid = await links.get_pulse_id(links.ENTITY_SITE, sicon_sub_location_id, org_id)
    if sid:
        return sid
    matches = await db.crm2_sites.find(
        {"organization_id": org_id, "sicon_sub_location_id": sicon_sub_location_id},
        {"_id": 0, "id": 1}).to_list(3)
    if len(matches) == 1:
        sid = matches[0]["id"]
        await links.upsert_link(links.ENTITY_SITE, sicon_sub_location_id, "crm2_site", sid,
                                organization_id=org_id, sync_status="auto")
        return sid
    return None


async def classify_case(norm: Dict[str, Any], org_id: str) -> Dict[str, Any]:
    scid = norm.get("si_sm_case_id")
    if scid is not None:
        link = await links.get_link(links.ENTITY_CASE, scid, org_id)
        if link and link.get("pulse_entity_id"):
            return {"bucket": "linked", "issue_id": link["pulse_entity_id"]}
        existing = await db.issues.find_one(
            {"organization_id": org_id, "sicon_case_id": scid}, {"_id": 0, "id": 1})
        if existing:
            return {"bucket": "linked", "issue_id": existing["id"]}
    return {"bucket": "new", "issue_id": None}


def _case_sicon_set(norm: Dict[str, Any], resolved: Dict[str, Any], linkfields: Dict[str, Any]) -> Dict[str, Any]:
    setdoc = {
        "sicon_case_id": norm.get("si_sm_case_id"),
        "sicon_case_number": norm.get("case_number"),
        "sicon_tracking_status_id": norm.get("tracking_status_id"),
        "sicon_tracking_status": norm.get("tracking_status_name"),
        "sicon_customer_order_number": norm.get("customer_order_number"),
        "sicon_project_job_id": norm.get("sicon_project_job_id"),
        "sicon_project_number": norm.get("project_number"),
        "sicon_next_appointment_date": norm.get("next_appointment_date"),
        "sicon_last_tracking_date": norm.get("last_tracking_date"),
        "sicon_last_synced_at": _now(),
        "updated_at": _now(),
    }
    setdoc.update(linkfields)  # company_id / site_id if resolved
    return {k: v for k, v in setdoc.items() if v not in (None, "")}


async def apply_case_record(org_id: str, norm: Dict[str, Any], classification: Dict[str, Any],
                            config: Dict[str, Any], run_id: str = "",
                            fill_gaps: bool = False) -> Dict[str, Any]:
    scid = norm.get("si_sm_case_id")
    resolved = resolve_case_fields(norm, config)
    linkfields = await _resolve_case_links(org_id, norm)

    if classification["bucket"] == "linked":
        issue_id = classification["issue_id"]
        if fill_gaps:
            from utils.sicon_onboarding import gap_fill
            existing = await db.issues.find_one({"id": issue_id}, {"_id": 0}) or {}
            setdoc = _case_sicon_set(norm, resolved, {})
            setdoc.update(await gap_fill(org_id, "case", scid, issue_id, existing,
                                         {**linkfields, "status": resolved.get("status")}, run_id))
            await db.issues.update_one({"id": issue_id}, {"$set": setdoc})
            if scid is not None:
                await links.upsert_link(links.ENTITY_CASE, scid, "issue", issue_id,
                                        organization_id=org_id, sync_status="linked")
            return {"action": "updated", "issue_id": issue_id}
        setdoc = _case_sicon_set(norm, resolved, linkfields)
        # Status/severity are Sicon-tracked for imported cases; keep the mapped
        # values in sync but never blank them.
        if resolved.get("status"):
            setdoc["status"] = resolved["status"]
        await db.issues.update_one({"id": issue_id}, {"$set": setdoc})
        if scid is not None:
            await links.upsert_link(links.ENTITY_CASE, scid, "issue", issue_id,
                                    organization_id=org_id, sync_status="linked")
        return {"action": "updated", "issue_id": issue_id}

    # new
    issue_id = str(uuid.uuid4())
    doc = {
        "id": issue_id,
        "organization_id": org_id,
        "machine_type": norm.get("customer_name") or "Sicon Case",
        "serial_number": "",
        "issue_description": norm.get("summary") or f"Sicon case {norm.get('case_number') or scid}",
        "status": resolved.get("status") or _DEFAULT_STATUS,
        "severity": resolved.get("severity") or _DEFAULT_SEVERITY,
        "source": "sicon_import",
        "imported_via": "sicon",
        "reported_date": norm.get("logged_date") or _now(),
        "created_at": _now(),
    }
    doc.update(_case_sicon_set(norm, resolved, linkfields))
    await db.issues.insert_one(doc)
    if scid is not None:
        await links.upsert_link(links.ENTITY_CASE, scid, "issue", issue_id,
                                organization_id=org_id, sync_status="linked")
    return {"action": "created", "issue_id": issue_id}


# ── Case relationships (proven v1 chain, §12-13) ──────────────────
# When a case imports, attach its Sicon-linked EQUIPMENT to the EXISTING Pulse
# asset (resolved via the immutable siconEquipmentId link) and fold its
# TRACKING NOTES into the case's EXISTING timeline. We never invent an asset
# link — equipment that isn't yet a linked Pulse asset is flagged
# UNMAPPED_EQUIPMENT in the conflict queue (§12) for manual review. All fully
# idempotent: re-running never duplicates a note or double-attaches an asset.

CASE_EQUIPMENT_ENTITY = "case_equipment"  # conflict-queue entity for §12 flags


def _first(rec: Dict[str, Any], keys) -> Any:
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return v
    return None


def _note_identity(rec: Dict[str, Any]):
    return _first(rec, ("siconTrackingNoteId", "siSMTrackingNoteId", "trackingNoteId", "id"))


def _note_timeline_entry(rec: Dict[str, Any]) -> Dict[str, Any]:
    note_id = _note_identity(rec)
    return {
        "event": "sicon_tracking_note",
        "text": _first(rec, ("note", "noteText", "body", "description", "text")) or "",
        "by": _first(rec, ("userName", "createdBy", "author", "resourceName")) or "Sicon",
        "timestamp": _first(rec, ("trackingDate", "createdDate", "date", "loggedDate")) or _now(),
        "source": "SICON",
        "sicon_tracking_note_id": str(note_id) if note_id is not None else None,
    }


async def _record_unmapped_equipment(org_id: str, scid, seid, sicon_eq: Dict[str, Any],
                                     run_id: str) -> None:
    """§12 — a case references Sicon equipment that isn't a linked Pulse asset."""
    key = {"organization_id": org_id, "external_entity_type": CASE_EQUIPMENT_ENTITY,
           "external_id": f"{scid}:{seid}"}
    await db.sicon_import_conflicts.update_one(key, {"$set": {
        **key,
        "sicon_record": {"si_sm_case_id": scid, "sicon_equipment_id": seid, "raw": sicon_eq},
        "candidates": [],
        "reasons": ["UNMAPPED_EQUIPMENT"],
        "status": "open",
        "run_id": run_id,
        "updated_at": _now(),
    }, "$setOnInsert": {"created_at": _now()}}, upsert=True)


async def _resolve_asset_for_sicon_equipment(org_id: str, seid) -> Optional[str]:
    if seid is None:
        return None
    pid = await links.get_pulse_id(links.ENTITY_EQUIPMENT, seid, org_id)
    if pid:
        return pid
    existing = await db.equipment.find_one(
        {"organization_id": org_id, "sicon_equipment_id": seid}, {"_id": 0, "id": 1})
    return existing["id"] if existing else None


async def _attach_case_equipment(org_id: str, client, scid, issue_id: str,
                                 run_id: str) -> Dict[str, int]:
    """Pull the case's Sicon equipment and attach resolved Pulse assets to the
    issue. Unresolved equipment is flagged UNMAPPED_EQUIPMENT (never invented)."""
    out = {"equipment_linked": 0, "equipment_unmapped": 0}
    body = await client.svc_get_case_equipment(scid)
    asset_ids: List[str] = []
    for rec in _extract_records(body):
        seid = _first(rec, ("siconEquipmentId", "SiconEquipmentId", "equipmentId"))
        asset_id = await _resolve_asset_for_sicon_equipment(org_id, seid)
        if asset_id:
            if asset_id not in asset_ids:
                asset_ids.append(asset_id)
            out["equipment_linked"] += 1
        else:
            out["equipment_unmapped"] += 1
            await _record_unmapped_equipment(org_id, scid, seid, rec, run_id)
    # §22 — only set when we resolved at least one asset; never erase existing.
    if asset_ids:
        assets = await db.equipment.find(
            {"id": {"$in": asset_ids}}, {"_id": 0, "id": 1, "name": 1, "serial_number": 1}
        ).to_list(len(asset_ids))
        by_id = {a["id"]: a for a in assets}
        first = by_id.get(asset_ids[0], {})
        serials = [by_id[i].get("serial_number") for i in asset_ids
                   if by_id.get(i, {}).get("serial_number")]
        await db.issues.update_one({"id": issue_id}, {"$set": {
            "asset_id": asset_ids[0],
            "asset_name": first.get("name") or "",
            "equipment_ids": asset_ids,
            "equipment_serials": serials,
            "updated_at": _now(),
        }})
    return out


async def _fold_tracking_notes(org_id: str, client, scid, issue_id: str) -> Dict[str, int]:
    """Fold a case's Sicon tracking notes into the EXISTING issue timeline,
    deduped by sicon_tracking_note_id so re-runs never duplicate (§13/§21)."""
    body = await client.svc_get_case_tracking_notes(scid)
    records = _extract_records(body)
    if not records:
        return {"notes_added": 0}
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0, "timeline": 1}) or {}
    seen = {str(e.get("sicon_tracking_note_id")) for e in (issue.get("timeline") or [])
            if e.get("sicon_tracking_note_id") is not None}
    fresh = []
    for rec in records:
        entry = _note_timeline_entry(rec)
        nid = entry.get("sicon_tracking_note_id")
        if nid is not None and nid in seen:
            continue
        if nid is not None:
            seen.add(nid)
        fresh.append(entry)
    if fresh:
        await db.issues.update_one({"id": issue_id},
                                   {"$push": {"timeline": {"$each": fresh}},
                                    "$set": {"updated_at": _now()}})
    return {"notes_added": len(fresh)}


async def sync_case_relationships(org_id: str, client, scid, issue_id: str,
                                  run_id: str = "") -> Dict[str, int]:
    """Attach a case's equipment + tracking notes to the existing Pulse issue.
    Each sub-pull is isolated so one failing relationship never fails the case.
    Appointments/resources/time-bookings are intentionally NOT wired here yet —
    they need the engineer-mapping layer + a canonical scheduling target."""
    totals = {"equipment_linked": 0, "equipment_unmapped": 0, "notes_added": 0}
    if client is None or scid is None or not issue_id:
        return totals
    try:
        for k, v in (await _attach_case_equipment(org_id, client, scid, issue_id, run_id)).items():
            totals[k] += v
    except Exception as e:
        logger.warning("case %s equipment attach failed: %s", scid, e)
    try:
        for k, v in (await _fold_tracking_notes(org_id, client, scid, issue_id)).items():
            totals[k] += v
    except Exception as e:
        logger.warning("case %s tracking-note fold failed: %s", scid, e)
    return totals



async def preview_cases(org_id: str, client, config: Dict[str, Any], max_records: int = 500) -> Dict[str, Any]:
    buckets = {"linked": 0, "new": 0, "failed": 0}
    sample: List[Dict[str, Any]] = []
    total = None
    processed = 0
    async for meta, records in client.svc_paginate("cases"):
        if total is None:
            total = meta.get("totalRecords")
        for rec in records:
            try:
                norm = normalise_case(rec)
                cls = await classify_case(norm, org_id)
                buckets[cls["bucket"]] += 1
                res = resolve_case_fields(norm, config)
                if len(sample) < 50:
                    sample.append({"si_sm_case_id": norm["si_sm_case_id"],
                                   "case_number": norm["case_number"],
                                   "summary": norm["summary"],
                                   "customer_name": norm["customer_name"],
                                   "sicon_status": norm["tracking_status_name"],
                                   "mapped_status": res["status"],
                                   "mapped_severity": res["severity"],
                                   "bucket": cls["bucket"]})
            except Exception as e:
                buckets["failed"] += 1
                logger.warning("case preview failed: %s", e)
            processed += 1
            if processed >= max_records:
                break
        if processed >= max_records:
            break
    return {"total_in_sicon": total, "previewed": processed, "counts": buckets, "sample": sample}


async def run_case_sync(org_id: str, client, config: Dict[str, Any], max_records: int = 0,
                        run_id: Optional[str] = None, user_id: str = "system",
                        pull_relationships: bool = True) -> Dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    counts = {"created": 0, "updated": 0, "failed": 0,
              "equipment_linked": 0, "equipment_unmapped": 0, "notes_added": 0}
    if not await acquire_sync_lock(org_id, "case", run_id):
        await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
            "id": run_id, "organization_id": org_id, "entity": "case",
            "status": "skipped_locked", "counts": counts, "finished_at": _now(),
            "skip_reason": "another case sync is already running for this organisation",
        }}, upsert=True)
        logger.info("case sync %s skipped — lock already held for org %s", run_id, org_id)
        return {"run_id": run_id, "status": "skipped_locked", "processed": 0, "counts": counts}
    await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
        "id": run_id, "organization_id": org_id, "entity": "case",
        "status": "running", "counts": counts, "started_at": _now(), "user_id": user_id}},
        upsert=True)
    processed = 0
    try:
        async for meta, records in client.svc_paginate("cases"):
            for rec in records:
                try:
                    norm = normalise_case(rec)
                    cls = await classify_case(norm, org_id)
                    res = await apply_case_record(org_id, norm, cls, config, run_id)
                    counts[res["action"]] = counts.get(res["action"], 0) + 1
                    if pull_relationships and res.get("issue_id"):
                        rel = await sync_case_relationships(
                            org_id, client, norm.get("si_sm_case_id"), res["issue_id"], run_id)
                        for rk, rv in rel.items():
                            counts[rk] = counts.get(rk, 0) + rv
                except Exception as e:
                    counts["failed"] += 1
                    logger.warning("case sync record failed (run %s): %s", run_id, e)
                processed += 1
                if max_records and processed >= max_records:
                    break
            await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {"counts": counts}})
            await touch_sync_lock(org_id, "case", run_id)
            if max_records and processed >= max_records:
                break
        status = "completed"
    except Exception as e:
        status = "failed"
        logger.error("case sync run %s aborted: %s", run_id, e)
    finally:
        await release_sync_lock(org_id, "case", run_id)
    await db.sicon_sync_runs.update_one(
        {"id": run_id}, {"$set": {"status": status, "counts": counts,
                                  "processed": processed, "finished_at": _now()}})
    return {"run_id": run_id, "status": status, "processed": processed, "counts": counts}
