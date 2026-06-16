"""
Pulse Fitness Service Operations — Parts catalogue + van stock.

Iter 215dq · annotations backfilled iter 215eb.

Phase 4 work brought forward to support intake-time parts allocation
(operators triage and reserve parts when logging the case so the
engineer arrives loaded).

For Pulse Fitness orgs the catalogue will be sourced from Sage / Sicon
(see `/imports/sicon` stub at the bottom). For everyone else operators
add SKUs ad-hoc.

Field mapping authoritative in /app/memory/SVC_FIELD_MAPPING.md.
"""

# Integration field manifest — see SVC_FIELD_MAPPING.md § 11-12.
__integration_fields__ = {
    # svc_parts (catalogue)
    "parts.id":                "gymaxis_only: local uuid",
    "parts.sku":               "sicon: PartCode · sage: StockCode · bidirectional",
    "parts.name":              "sicon: PartDescription · sage: StockDescription · bidirectional",
    "parts.cost":              "sage: AverageCost · Sage → Pulse Fitness",
    "parts.list_price":        "sage: SellingPrice · Sage → Pulse Fitness",
    "parts.lead_time_days":    "sage: ReorderLeadTimeDays · Sage → Pulse Fitness",
    "parts.reorder_threshold": "gymaxis_only: low-stock alert threshold",
    "parts.reorder_qty":       "gymaxis_only: PO suggestion quantity",
    "parts.preferred_supplier_id": "sage: SuppliersAccountID · Sage → Pulse Fitness",
    # svc_part_movements (allocate / deallocate / consume / transfer / return / receive)
    "movements.id":            "gymaxis_only: local uuid",
    "movements.movement_type": "sicon: MovementTypeID (PART_MOVEMENT_CROSSWALK) · Pulse Fitness → Sicon",
    "movements.case_id":       "sicon: ServiceCallID · Pulse Fitness → Sicon",
    "movements.case_reference":"sicon: ServiceCallReference · Pulse Fitness → Sicon",
    "movements.allocation_id": "sicon: AllocationID · Pulse Fitness → Sicon",
    "movements.part_sku":      "sicon: PartCode · Pulse Fitness → Sicon",
    "movements.qty":           "sicon: Quantity · Pulse Fitness → Sicon",
    "movements.source":        "sicon: FromLocation (warehouse|van_<engId>) · Pulse Fitness → Sicon",
    "movements.engineer_id":   "sicon: EngineerID · Pulse Fitness → Sicon",
    "movements.actor_id":      "sicon: MovedBySageUserID · Pulse Fitness → Sicon",
    "movements.actor_name":    "sicon: MovedByUserName · Pulse Fitness → Sicon",
    "movements.at":            "sicon: MovedAt · Pulse Fitness → Sicon",
    "movements.notes":         "sicon: Notes · Pulse Fitness → Sicon",
}

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex

from utils.database import db
from utils.auth import get_current_user
from utils.svc_state import append_event
from routes.svc.integrations import sicon_sync

router = APIRouter(prefix="/svc/parts", tags=["Service Ops · Parts"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Catalogue
# ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_parts(
    search: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Catalogue search — type-ahead friendly."""
    of = _of(user)
    q: dict = {**of, "active": {"$ne": False}}
    if search:
        q["$or"] = [
            {"sku": safe_regex(search)},
            {"name": safe_regex(search)},
            {"manufacturer": safe_regex(search)},
        ]
    rows = (
        await db.svc_parts.find(q, {"_id": 0})
        .sort([("name", 1)])
        .limit(limit).to_list(limit)
    )
    return {"parts": rows, "count": len(rows)}


@router.post("")
async def create_part(data: dict, user=Depends(get_current_user)):
    of = _of(user)
    sku = (data.get("sku") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not sku or not name:
        raise HTTPException(400, "sku and name required")
    existing = await db.svc_parts.find_one({**of, "sku": sku})
    if existing:
        return _strip(existing)
    part = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "sku": sku,
        "name": name,
        "manufacturer": (data.get("manufacturer") or "").strip(),
        "supplier": (data.get("supplier") or "").strip(),
        "cost": float(data.get("cost") or 0),
        "lead_time_days": int(data.get("lead_time_days") or 0),
        "active": True,
        # Sicon/Sage fallthrough fields populated by /imports/sicon below.
        "sicon_part_id": data.get("sicon_part_id") or "",
        "sage_stock_code": data.get("sage_stock_code") or "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_parts.insert_one(part)
    part.pop("_id", None)
    return part


# ─────────────────────────────────────────────────────────────────
# Van stock — per engineer
# ─────────────────────────────────────────────────────────────────

@router.get("/van/{engineer_id}")
async def get_van_stock(engineer_id: str, user=Depends(get_current_user)):
    """Per-engineer van inventory — joined with the catalogue for display."""
    of = _of(user)
    rows = await db.svc_van_stock.find({**of, "engineer_id": engineer_id}, {"_id": 0}).to_list(500)
    if not rows:
        return {"van": [], "engineer_id": engineer_id}
    skus = {r["part_sku"] for r in rows}
    catalogue = await db.svc_parts.find(
        {**of, "sku": {"$in": list(skus)}}, {"_id": 0},
    ).to_list(len(skus))
    by_sku = {p["sku"]: p for p in catalogue}
    for r in rows:
        r["part"] = by_sku.get(r["part_sku"], {})
    return {"van": rows, "engineer_id": engineer_id}


# ─────────────────────────────────────────────────────────────────
# Allocation — case-bound parts (already triaged or from van)
# ─────────────────────────────────────────────────────────────────

@router.post("/allocate")
async def allocate_to_case(data: dict, user=Depends(get_current_user)):
    """Reserve a part for a case at intake time.

    Body: {case_id, part_sku, qty, source: 'warehouse'|'van', engineer_id?}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    part_sku = ((data or {}).get("part_sku") or "").strip().upper()
    qty = int((data or {}).get("qty") or 1)
    source = ((data or {}).get("source") or "warehouse").lower()
    if not case_id or not part_sku or qty <= 0:
        raise HTTPException(400, "case_id, part_sku and qty>0 required")
    if source not in ("warehouse", "van"):
        raise HTTPException(400, "source must be warehouse|van")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    part = await db.svc_parts.find_one({**of, "sku": part_sku}, {"_id": 0})
    if not part:
        raise HTTPException(404, f"Part {part_sku} not in catalogue — add it first")

    # Decrement van stock if sourcing from van.
    engineer_id = (data or {}).get("engineer_id") or case.get("assigned_engineer_id") or ""
    if source == "van":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required when source=van")
        van = await db.svc_van_stock.find_one({**of, "engineer_id": engineer_id, "part_sku": part_sku})
        if not van or (van.get("qty") or 0) < qty:
            raise HTTPException(409, f"Not enough {part_sku} in van stock")
        await db.svc_van_stock.update_one(
            {"_id": van["_id"]},
            {"$inc": {"qty": -qty}, "$set": {"updated_at": _now()}},
        )

    allocation = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "part_sku": part_sku,
        "part_name": part.get("name"),
        "qty": qty,
        "source": source,
        "engineer_id": engineer_id,
        "fulfilled": False,
        "allocated_by_id": user["id"],
        "allocated_by_name": user.get("full_name") or user.get("email") or "",
        "allocated_at": _now(),
    }
    await db.svc_part_movements.insert_one({
        **allocation,
        "movement_type": "allocate",
        "id": str(uuid.uuid4()),  # movement has its own id
        "allocation_id": allocation["id"],
    })
    # Embed the allocation onto the case for fast read.
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {
            "$push": {"allocated_parts": allocation},
            "$set": {"updated_at": _now()},
        },
    )
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Allocated {qty} × {part_sku} ({part.get('name','')}) from {source}",
        extra={"allocation_id": allocation["id"], "kind": "parts_allocation"},
    )
    # Mirror the stock movement to Sicon (Phase 8 A wiring).
    await sicon_sync.push_part_movement(
        {
            **allocation,
            "movement_type": "allocate",
            "from_location": source,
            "to_location": "case",
            "actor_id": user["id"],
            "actor_name": user.get("full_name") or user.get("email") or "",
            "at": allocation["allocated_at"],
        },
        case_reference=case.get("reference"),
    )
    return allocation


@router.delete("/allocate/{allocation_id}")
async def deallocate(allocation_id: str, user=Depends(get_current_user)):
    """Release a previously-reserved allocation back to stock."""
    of = _of(user)
    case = await db.svc_cases.find_one(
        {**of, "allocated_parts.id": allocation_id}, {"_id": 0},
    )
    if not case:
        raise HTTPException(404, "Allocation not found")
    alloc = next((a for a in (case.get("allocated_parts") or []) if a.get("id") == allocation_id), None)
    if not alloc:
        raise HTTPException(404, "Allocation not found")
    if alloc.get("source") == "van" and alloc.get("engineer_id"):
        await db.svc_van_stock.update_one(
            {**of, "engineer_id": alloc["engineer_id"], "part_sku": alloc["part_sku"]},
            {"$inc": {"qty": alloc.get("qty") or 0}, "$set": {"updated_at": _now()}},
            upsert=True,
        )
    await db.svc_cases.update_one(
        {"id": case["id"], **of},
        {"$pull": {"allocated_parts": {"id": allocation_id}}, "$set": {"updated_at": _now()}},
    )
    await db.svc_part_movements.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case["id"],
        "case_reference": case.get("reference"),
        "movement_type": "deallocate",
        "allocation_id": allocation_id,
        "part_sku": alloc.get("part_sku"),
        "qty": alloc.get("qty"),
        "source": alloc.get("source"),
        "engineer_id": alloc.get("engineer_id"),
        "actor_id": user["id"],
        "at": _now(),
    })
    # Mirror the deallocation to Sicon (Phase 8 A wiring).
    await sicon_sync.push_part_movement(
        {
            "id": str(uuid.uuid4()),
            "organization_id": of["organization_id"],
            "case_id": case["id"],
            "case_reference": case.get("reference"),
            "movement_type": "deallocate",
            "allocation_id": allocation_id,
            "part_sku": alloc.get("part_sku"),
            "qty": alloc.get("qty"),
            "from_location": "case",
            "to_location": alloc.get("source") or "warehouse",
            "engineer_id": alloc.get("engineer_id"),
            "actor_id": user["id"],
            "actor_name": user.get("full_name") or user.get("email") or "",
            "at": _now(),
        },
        case_reference=case.get("reference"),
    )
    return {"ok": True, "deallocated": allocation_id}


# ─────────────────────────────────────────────────────────────────
# Sicon / Sage import (Pulse Fitness flow)
# ─────────────────────────────────────────────────────────────────

@router.post("/imports/sicon")
async def import_from_sicon(data: dict, user=Depends(get_current_user)):
    """Mirror parts from Sicon/Sage into the local catalogue.

    Body: {parts: [{sku, name, manufacturer?, supplier?, cost?, lead_time_days?,
                    sicon_part_id?, sage_stock_code?}]}

    Currently a manual-feed endpoint — when the live Sicon worker lands
    in Phase 8 it will pull the catalogue automatically. Pulse Fitness
    operators can paste a Sicon export here in the meantime.
    """
    of = _of(user)
    parts = (data or {}).get("parts") or []
    if not isinstance(parts, list) or not parts:
        raise HTTPException(400, "parts array required")
    inserted = 0
    updated = 0
    for raw in parts:
        sku = (raw.get("sku") or "").strip().upper()
        name = (raw.get("name") or "").strip()
        if not sku or not name:
            continue
        res = await db.svc_parts.update_one(
            {**of, "sku": sku},
            {
                "$set": {
                    "organization_id": of["organization_id"],
                    "sku": sku,
                    "name": name,
                    "manufacturer": (raw.get("manufacturer") or "").strip(),
                    "supplier": (raw.get("supplier") or "").strip(),
                    "cost": float(raw.get("cost") or 0),
                    "lead_time_days": int(raw.get("lead_time_days") or 0),
                    "sicon_part_id": raw.get("sicon_part_id") or "",
                    "sage_stock_code": raw.get("sage_stock_code") or "",
                    "active": True,
                    "updated_at": _now(),
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "created_at": _now(),
                },
            },
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}
