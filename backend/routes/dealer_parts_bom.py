"""Dealer Warranty Parts — Phase 2.

BOM Management, Most-Used Parts, and the Recommendation Engine.

Reuses Phase 1 helpers/collections from `routes.dealer_parts` (single source
of truth — no duplicate dealers/orders/stock). BOMs are versioned per machine
model (old versions kept as `superseded`, never overwritten). The recommendation
engine reads the machines on an order, pulls the active BOM + most-used parts,
then NETS the recommendation against what the dealer already holds and has been
allocated before — preventing unnecessary repetition.
"""
from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.security_plus import safe_regex

from routes.dealer_parts import (
    _of, _now, _audit, _can_manage, _strip, _dealer_or_404, require_staff,
    ORDERS, ALLOCATIONS, STORE_STOCK,
)
from routes.dealer_parts_intel import failure_bump

router = APIRouter(prefix="/dealer-parts", tags=["Dealer Warranty Parts"], dependencies=[Depends(require_staff)])

BOMS = "dealer_bom"
MOST_USED = "dealer_most_used_parts"

PRIORITY_DEFAULT_QTY = {"critical": 3, "high": 2, "medium": 1, "low": 1, "optional": 0}
PRIORITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "optional": 1}


# ─────────────────────────────────────────────────────────────────
# BOM Management (versioned per machine model)
# ─────────────────────────────────────────────────────────────────

def _norm_bom_item(it: dict) -> dict:
    return {
        "id": it.get("id") or str(uuid.uuid4()),
        "part_number": (it.get("part_number") or it.get("part_sku") or "").strip().upper(),
        "part_description": (it.get("part_description") or it.get("part_name") or "").strip(),
        "quantity_per_machine": float(it.get("quantity_per_machine") or 1),
        "part_category": (it.get("part_category") or "").strip(),
        "criticality": (it.get("criticality") or "medium").strip().lower(),
        "warranty_relevance": bool(it.get("warranty_relevance", False)),
        "recommended_spare": bool(it.get("recommended_spare", False)),
        "service_part": bool(it.get("service_part", False)),
        "consumable": bool(it.get("consumable", False)),
        "wear_item": bool(it.get("wear_item", False)),
        "supplier": (it.get("supplier") or "").strip(),
        "cost": float(it.get("cost") or 0),
        "notes": (it.get("notes") or "").strip(),
    }


@router.get("/boms")
async def list_boms(
    machine_model: str = Query(""),
    include_superseded: bool = Query(False),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if machine_model:
        q["machine_model"] = safe_regex(machine_model)
    if not include_superseded:
        q["status"] = {"$ne": "superseded"}
    rows = await db[BOMS].find(q, {"_id": 0}).sort([("machine_model", 1), ("version", -1)]).to_list(500)
    return {"boms": rows, "count": len(rows)}


@router.post("/boms")
async def create_bom(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    model = (data.get("machine_model") or "").strip()
    if not model:
        raise HTTPException(400, "machine_model required")
    items = [_norm_bom_item(i) for i in (data.get("items") or []) if (i.get("part_number") or i.get("part_sku"))]
    # Version control: supersede current active BOM(s) for this model.
    prev = await db[BOMS].find({"organization_id": org, "machine_model": model}, {"_id": 0, "version": 1}).to_list(500)
    next_version = (max([p.get("version", 0) for p in prev]) + 1) if prev else 1
    status = (data.get("status") or "active").strip().lower()
    if status == "active":
        await db[BOMS].update_many(
            {"organization_id": org, "machine_model": model, "status": "active"},
            {"$set": {"status": "superseded", "updated_at": _now()}},
        )
    bom = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "machine_model": model,
        "machine_category": (data.get("machine_category") or "").strip(),
        "version": next_version,
        "status": status,
        "items": items,
        "notes": (data.get("notes") or "").strip(),
        "created_by": user.get("full_name") or user.get("email"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[BOMS].insert_one(dict(bom))
    await _audit(org, user, "bom_imported", machine_model=model, bom_id=bom["id"],
                 version=next_version, item_count=len(items))
    return _strip(bom)


@router.get("/boms/{bom_id}")
async def get_bom(bom_id: str, user=Depends(get_current_user)):
    org = _of(user)
    b = await db[BOMS].find_one({"organization_id": org, "id": bom_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "BOM not found")
    return b


@router.patch("/boms/{bom_id}")
async def update_bom_status(bom_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    b = await db[BOMS].find_one({"organization_id": org, "id": bom_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "BOM not found")
    status = (data.get("status") or "").strip().lower()
    if status not in ("draft", "active", "superseded", "archived"):
        raise HTTPException(400, "Invalid status")
    if status == "active":
        await db[BOMS].update_many(
            {"organization_id": org, "machine_model": b["machine_model"], "status": "active", "id": {"$ne": bom_id}},
            {"$set": {"status": "superseded", "updated_at": _now()}},
        )
    await db[BOMS].update_one({"organization_id": org, "id": bom_id}, {"$set": {"status": status, "updated_at": _now()}})
    await _audit(org, user, "bom_status_changed", bom_id=bom_id, status=status)
    return await get_bom(bom_id, user)


# ─────────────────────────────────────────────────────────────────
# Most-Used Parts
# ─────────────────────────────────────────────────────────────────

@router.get("/most-used")
async def list_most_used(machine_model: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q: dict = {"organization_id": org}
    if machine_model:
        q["machine_model"] = safe_regex(machine_model)
    rows = await db[MOST_USED].find(q, {"_id": 0}).sort([("machine_model", 1), ("priority_rank", -1)]).to_list(1000)
    return {"most_used": rows, "count": len(rows)}


@router.post("/most-used")
async def upsert_most_used(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    model = (data.get("machine_model") or "").strip()
    sku = (data.get("part_number") or data.get("part_sku") or "").strip().upper()
    if not model or not sku:
        raise HTTPException(400, "machine_model and part_number required")
    priority = (data.get("priority") or "medium").strip().lower()
    doc = {
        "organization_id": org,
        "machine_model": model,
        "part_number": sku,
        "part_description": (data.get("part_description") or data.get("part_name") or "").strip(),
        "usage_frequency": float(data.get("usage_frequency") or 0),
        "failure_frequency": float(data.get("failure_frequency") or 0),
        "avg_usage_per_year": float(data.get("avg_usage_per_year") or 0),
        "recommended_dealer_stock_quantity": data.get("recommended_dealer_stock_quantity"),
        "priority": priority,
        "priority_rank": PRIORITY_RANK.get(priority, 3),
        "warranty_relevance": bool(data.get("warranty_relevance", True)),
        "lead_time_days": int(data.get("lead_time_days") or 0),
        "cost": float(data.get("cost") or 0),
        "updated_at": _now(),
    }
    existing = await db[MOST_USED].find_one({"organization_id": org, "machine_model": model, "part_number": sku})
    if existing:
        await db[MOST_USED].update_one({"_id": existing["_id"]}, {"$set": doc})
        doc["id"] = existing.get("id")
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = _now()
        await db[MOST_USED].insert_one(dict(doc))
    await _audit(org, user, "most_used_upserted", machine_model=model, part_number=sku)
    return _strip(doc)


@router.delete("/most-used/{mu_id}")
async def delete_most_used(mu_id: str, user=Depends(get_current_user)):
    org = _of(user)
    await db[MOST_USED].delete_one({"organization_id": org, "id": mu_id})
    await _audit(org, user, "most_used_deleted", mu_id=mu_id)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Recommendation Engine (with duplicate / repetition prevention)
# ─────────────────────────────────────────────────────────────────

async def _dealer_held(org: str, dealer_id: str) -> dict:
    """SKU → qty currently held (on hand + in transit) across dealer stores."""
    held: dict = {}
    async for s in db[STORE_STOCK].find({"organization_id": org, "dealer_id": dealer_id}, {"_id": 0}):
        sku = s.get("part_sku")
        held[sku] = held.get(sku, 0) + (s.get("qty_on_hand") or 0) + (s.get("qty_in_transit") or 0)
    return held


async def _dealer_allocated(org: str, dealer_id: str) -> dict:
    """SKU → qty already allocated in non-cancelled allocations (committed)."""
    alloc: dict = {}
    async for a in db[ALLOCATIONS].find(
        {"organization_id": org, "dealer_id": dealer_id, "status": {"$nin": ["cancelled", "draft"]}}, {"_id": 0}
    ):
        for it in a.get("items", []):
            if it.get("status") == "removed":
                continue
            sku = it.get("part_sku")
            alloc[sku] = alloc.get(sku, 0) + (it.get("quantity") or 0)
    return alloc


@router.post("/recommend")
async def recommend(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    order_id = data.get("order_id")
    if not order_id:
        raise HTTPException(400, "order_id required")
    order = await db[ORDERS].find_one({"organization_id": org, "id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    dealer_id = order["dealer_id"]
    dealer = await _dealer_or_404(org, dealer_id)
    d_region = dealer.get("region") or ""
    d_country = dealer.get("country") or ""

    held = await _dealer_held(org, dealer_id)
    allocated = await _dealer_allocated(org, dealer_id)

    # candidate[sku] = merged record across all machine lines
    candidates: dict = {}
    missing_bom_models: list = []

    for line in order.get("lines", []):
        model = (line.get("machine_model") or "").strip()
        if not model:
            continue
        machine_qty = float(line.get("quantity") or 1)
        fleet_factor = max(1, round(machine_qty / 10.0))

        bom = await db[BOMS].find_one(
            {"organization_id": org, "machine_model": safe_regex(f"^{model}$"), "status": "active"}, {"_id": 0}
        ) or await db[BOMS].find_one(
            {"organization_id": org, "machine_model": model, "status": "active"}, {"_id": 0}
        )
        if not bom:
            missing_bom_models.append(model)
        mu_rows = await db[MOST_USED].find({"organization_id": org, "machine_model": model}, {"_id": 0}).to_list(500)
        mu_by_sku = {m["part_number"]: m for m in mu_rows}

        # Seed from BOM's warranty/spare/wear/service/consumable items.
        bom_items = {}
        for bi in (bom.get("items", []) if bom else []):
            if not (bi.get("recommended_spare") or bi.get("warranty_relevance") or bi.get("wear_item")
                    or bi.get("consumable") or bi.get("service_part")):
                continue
            bom_items[bi["part_number"]] = bi

        skus = set(bom_items) | set(mu_by_sku)
        for sku in skus:
            bi = bom_items.get(sku)
            mu = mu_by_sku.get(sku)
            priority = (mu.get("priority") if mu else (bi.get("criticality") if bi else "medium")) or "medium"
            base = None
            if mu and mu.get("recommended_dealer_stock_quantity") is not None:
                base = float(mu["recommended_dealer_stock_quantity"])
            if base is None:
                base = float(PRIORITY_DEFAULT_QTY.get(priority, 1))
            qty = int(math.ceil(base * fleet_factor)) if base else 0
            if qty <= 0:
                continue
            cost = 0.0
            if mu and mu.get("cost"):
                cost = float(mu["cost"])
            elif bi and bi.get("cost"):
                cost = float(bi["cost"])
            desc = (mu.get("part_description") if mu else "") or (bi.get("part_description") if bi else "") or sku
            source = "BOM + most-used" if (bi and mu) else ("most-used" if mu else "BOM")
            c = candidates.get(sku)
            if c:
                c["qty"] += qty
                if PRIORITY_RANK.get(priority, 3) > PRIORITY_RANK.get(c["priority"], 3):
                    c["priority"] = priority
                if model not in c["models"]:
                    c["models"].append(model)
            else:
                candidates[sku] = {
                    "part_sku": sku, "part_name": desc, "priority": priority,
                    "unit_value": cost, "qty": qty, "models": [model], "source": source,
                }

    items = []
    duplicates_avoided = 0
    total_value = 0.0
    quality_flags = []
    for sku, c in candidates.items():
        raw = c["qty"]
        have = held.get(sku, 0) + allocated.get(sku, 0)
        rec = max(0, int(raw - have))
        unit = c["unit_value"]
        model_txt = ", ".join(c["models"])
        base_reason = f"Appears in {c['source']} for {model_txt} (priority: {c['priority']})."
        dup_warning = ""
        if have > 0 and rec < raw:
            duplicates_avoided += 1
            if rec == 0:
                dup_warning = f"Dealer already holds/allocated {int(have)} unit(s) — no repeat needed."
            else:
                dup_warning = f"Reduced from {raw} to {rec}: dealer already holds/allocated {int(have)}."
        # Closed loop — bump for regional failure signals + quality watch.
        bump_note = ""
        extra, note, qflag = await failure_bump(org, d_region, d_country, sku)
        if extra and rec >= 0:
            rec += extra
            bump_note = note
        elif note:
            bump_note = note
        if qflag:
            quality_flags.append(sku)
        items.append({
            "part_sku": sku,
            "part_name": c["part_name"],
            "machine_model": model_txt,
            "priority": c["priority"],
            "recommended_qty": rec,
            "original_qty": raw,
            "already_held": int(have),
            "unit_value": unit,
            "value": round(rec * unit, 2),
            "reason": (base_reason + (" " + dup_warning if dup_warning else "") + bump_note).strip(),
            "duplicate_warning": dup_warning,
            "failure_bumped": bool(extra),
            "quality_flag": qflag,
            "source": c["source"],
        })
        total_value += rec * unit

    items.sort(key=lambda x: (-PRIORITY_RANK.get(x["priority"], 3), -x["value"]))
    allowance = float(order.get("allowance") or 0)
    total_value = round(total_value, 2)
    return {
        "order_id": order_id,
        "dealer_id": dealer_id,
        "dealer_name": order.get("dealer_name"),
        "items": items,
        "recommended_items": [i for i in items if i["recommended_qty"] > 0],
        "total_value": total_value,
        "allowance": allowance,
        "allowance_remaining": round(allowance - total_value, 2),
        "over_allowance": total_value > allowance if allowance else False,
        "duplicates_avoided": duplicates_avoided,
        "quality_flags": sorted(set(quality_flags)),
        "missing_bom_models": sorted(set(missing_bom_models)),
    }
