"""Dealer Warranty Parts — Phase 3.

Engineer/Dealer parts-usage flow, Stores Department views, and Returns/RMA.

Reuses Phase 1 helpers/collections (single source of truth). Logging a part
used:
  1. writes a usage log,
  2. decrements the dealer remote-store stock (with a stock-movement ledger row),
  3. posts a timeline event on the linked Service Desk case (`svc_cases`),
  4. (Phase 4 will read these usage logs for failure monitoring).

No stock ever changes without a `dealer_stock_movements` row.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.security_plus import safe_regex
from utils.svc_state import append_event

from routes.dealer_parts import (
    _of, _now, _audit, _strip, _dealer_or_404, _movement, require_staff,
    STORES, STORE_STOCK, ALLOCATIONS,
)

router = APIRouter(prefix="/dealer-parts", tags=["Dealer Warranty Parts"], dependencies=[Depends(require_staff)])

USAGE = "dealer_parts_usage_logs"
RMA = "dealer_parts_rma"

FAILURE_REASONS = [
    "mechanical_failure", "electrical_failure", "wear_and_tear", "accidental_damage",
    "misuse", "corrosion_environmental", "transit_damage", "installation_issue",
    "manufacturing_defect_suspected", "unknown", "other",
]
RMA_STATUSES = [
    "not_required", "return_requested", "awaiting_return", "in_transit",
    "received_by_pulse", "under_inspection", "quality_review", "closed",
]


# ─────────────────────────────────────────────────────────────────
# Store resolution + consumption
# ─────────────────────────────────────────────────────────────────

async def _ensure_usage_store(org: str, dealer: dict, store_id: str | None, sku: str) -> dict:
    if store_id:
        s = await db[STORES].find_one({"organization_id": org, "id": store_id}, {"_id": 0})
        if s:
            return s
    ss = await db[STORE_STOCK].find_one(
        {"organization_id": org, "dealer_id": dealer["id"], "part_sku": sku, "qty_on_hand": {"$gt": 0}}, {"_id": 0}
    )
    if ss:
        s = await db[STORES].find_one({"organization_id": org, "id": ss["store_id"]}, {"_id": 0})
        if s:
            return s
    s = await db[STORES].find_one({"organization_id": org, "dealer_id": dealer["id"]}, {"_id": 0})
    if s:
        return s
    store = {
        "id": str(uuid.uuid4()), "organization_id": org, "dealer_id": dealer["id"],
        "dealer_name": dealer["name"], "name": "Main Dealer Store", "store_type": "main",
        "active": True, "created_at": _now(), "updated_at": _now(),
    }
    await db[STORES].insert_one(dict(store))
    return store


# ─────────────────────────────────────────────────────────────────
# Parts usage (engineer app + dealer portal)
# ─────────────────────────────────────────────────────────────────

@router.get("/usage")
async def list_usage(
    dealer_id: str = Query(""),
    case_id: str = Query(""),
    part_sku: str = Query(""),
    failures_only: bool = Query(False),
    limit: int = Query(300, ge=1, le=1000),
    user=Depends(get_current_user),
):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    if case_id:
        q["case_id"] = case_id
    if part_sku:
        q["part_sku"] = part_sku.strip().upper()
    if failures_only:
        q["warranty"] = True
    rows = await db[USAGE].find(q, {"_id": 0}).sort([("at", -1)]).limit(limit).to_list(limit)
    return {"usage": rows, "count": len(rows)}


@router.post("/usage")
async def log_usage(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer_id = data.get("dealer_id")
    sku = (data.get("part_sku") or "").strip().upper()
    qty = float(data.get("quantity") or 0)
    if not dealer_id or not sku or qty <= 0:
        raise HTTPException(400, "dealer_id, part_sku and quantity required")
    dealer = await _dealer_or_404(org, dealer_id)
    store = await _ensure_usage_store(org, dealer, data.get("store_id"), sku)
    part_name = (data.get("part_name") or "").strip()

    # Decrement store stock (only if held) — movement recorded regardless.
    key = {"organization_id": org, "store_id": store["id"], "part_sku": sku}
    existing = await db[STORE_STOCK].find_one(key)
    if existing:
        if not part_name:
            part_name = existing.get("part_name") or sku
        await db[STORE_STOCK].update_one(
            key, {"$inc": {"qty_on_hand": -qty}, "$set": {"last_used": _now(), "updated_at": _now()}}
        )

    usage = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "store_id": store["id"],
        "store_name": store["name"],
        "part_sku": sku,
        "part_name": part_name or sku,
        "quantity": qty,
        "machine_model": (data.get("machine_model") or "").strip(),
        "serial_number": (data.get("serial_number") or "").strip(),
        "case_id": data.get("case_id") or "",
        "customer_site": (data.get("customer_site") or "").strip(),
        "country": dealer.get("country") or "",
        "region": dealer.get("region") or "",
        "reason": (data.get("reason") or "").strip(),
        "warranty": bool(data.get("warranty", True)),
        "chargeable": bool(data.get("chargeable", False)),
        "failure_reason": (data.get("failure_reason") or "unknown").strip(),
        "failed_part_returned": bool(data.get("failed_part_returned", False)),
        "photo_url": data.get("photo_url") or "",
        "notes": (data.get("notes") or "").strip(),
        "engineer_name": (data.get("engineer_name") or user.get("full_name") or user.get("email") or "").strip(),
        "source": data.get("source") or "engineer_app",
        "at": _now(),
    }
    await db[USAGE].insert_one(dict(usage))

    await _movement(
        org, user, dealer_id=dealer_id, store_id=store["id"], store_name=store["name"],
        mtype="part_used", part_sku=sku, part_name=usage["part_name"], qty=qty,
        from_loc=store["name"], to_loc="consumed", reason=usage["failure_reason"],
        ref=f"USE-{usage['id'][:8].upper()}",
    )

    # Service Desk case timeline (best-effort; only if the case exists).
    if usage["case_id"]:
        case = await db.svc_cases.find_one({"id": usage["case_id"], "organization_id": org})
        if case:
            await append_event(
                case_id=usage["case_id"], organization_id=org, event_type="dealer_part_used",
                actor=user,
                body=f"{qty} × {usage['part_name']} ({sku}) fitted by {usage['engineer_name']} — {usage['failure_reason'].replace('_', ' ')}",
                extra={"part_sku": sku, "quantity": qty, "dealer_id": dealer_id,
                       "warranty": usage["warranty"], "usage_id": usage["id"]},
            )

    await _audit(org, user, "part_usage_logged", dealer_id=dealer_id, part_sku=sku,
                 quantity=qty, case_id=usage["case_id"])
    return _strip(usage)


# ─────────────────────────────────────────────────────────────────
# Stores Department dashboard
# ─────────────────────────────────────────────────────────────────

@router.get("/stores-dashboard")
async def stores_dashboard(user=Depends(get_current_user)):
    org = _of(user)
    to_pick = await db[ALLOCATIONS].find({"organization_id": org, "status": "approved"}, {"_id": 0}).sort([("approved_at", 1)]).to_list(200)
    awaiting_receipt = await db[ALLOCATIONS].find(
        {"organization_id": org, "status": {"$in": ["dispatched", "partially_received"]}}, {"_id": 0}
    ).sort([("dispatched_at", 1)]).to_list(200)
    recent_usage = await db[USAGE].find({"organization_id": org}, {"_id": 0}).sort([("at", -1)]).limit(12).to_list(12)
    stock = await db[STORE_STOCK].find({"organization_id": org}, {"_id": 0}).to_list(5000)
    low_stock = [s for s in stock if (s.get("min_stock") or 0) and (s.get("qty_on_hand") or 0) <= (s.get("min_stock") or 0)]
    open_rma = await db[RMA].count_documents({"organization_id": org, "status": {"$ne": "closed"}})
    return {
        "cards": {
            "to_pick": len(to_pick),
            "awaiting_receipt": len(awaiting_receipt),
            "low_stock": len(low_stock),
            "open_rma": open_rma,
        },
        "to_pick": to_pick,
        "awaiting_receipt": awaiting_receipt,
        "recent_usage": recent_usage,
        "low_stock": low_stock[:50],
    }


# ─────────────────────────────────────────────────────────────────
# Returns / RMA
# ─────────────────────────────────────────────────────────────────

@router.get("/rma")
async def list_rma(dealer_id: str = Query(""), status: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q: dict = {"organization_id": org}
    if dealer_id:
        q["dealer_id"] = dealer_id
    if status:
        q["status"] = status
    rows = await db[RMA].find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    return {"rma": rows, "count": len(rows)}


@router.post("/rma")
async def create_rma(data: dict, user=Depends(get_current_user)):
    org = _of(user)
    dealer_id = data.get("dealer_id")
    sku = (data.get("part_sku") or "").strip().upper()
    if not dealer_id or not sku:
        raise HTTPException(400, "dealer_id and part_sku required")
    dealer = await _dealer_or_404(org, dealer_id)
    status = (data.get("status") or "return_requested").strip()
    if status not in RMA_STATUSES:
        raise HTTPException(400, "Invalid status")
    rma = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "rma_reference": (data.get("rma_reference") or f"RMA-{uuid.uuid4().hex[:8].upper()}"),
        "dealer_id": dealer_id,
        "dealer_name": dealer["name"],
        "part_sku": sku,
        "part_name": (data.get("part_name") or sku).strip(),
        "quantity": float(data.get("quantity") or 1),
        "machine_model": (data.get("machine_model") or "").strip(),
        "serial_number": (data.get("serial_number") or "").strip(),
        "reason": (data.get("reason") or "").strip(),
        "failure_reason": (data.get("failure_reason") or "unknown").strip(),
        "usage_log_id": data.get("usage_log_id") or "",
        "case_id": data.get("case_id") or "",
        "failed_part_returned": bool(data.get("failed_part_returned", False)),
        "status": status,
        "inspection_status": "",
        "quality_finding": "",
        "warranty_outcome": "",
        "credit_status": "",
        "notes": (data.get("notes") or "").strip(),
        "created_by": user.get("full_name") or user.get("email"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[RMA].insert_one(dict(rma))
    await _audit(org, user, "rma_created", dealer_id=dealer_id, rma_id=rma["id"], part_sku=sku)
    return _strip(rma)


@router.patch("/rma/{rma_id}")
async def update_rma(rma_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    existing = await db[RMA].find_one({"organization_id": org, "id": rma_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "RMA not found")
    allowed = {"status", "inspection_status", "quality_finding", "warranty_outcome",
               "credit_status", "notes", "failed_part_returned"}
    patch = {k: v for k, v in data.items() if k in allowed}
    if "status" in patch and patch["status"] not in RMA_STATUSES:
        raise HTTPException(400, "Invalid status")
    patch["updated_at"] = _now()
    await db[RMA].update_one({"organization_id": org, "id": rma_id}, {"$set": patch})
    await _audit(org, user, "rma_updated", rma_id=rma_id, changes=list(patch.keys()))
    return await db[RMA].find_one({"organization_id": org, "id": rma_id}, {"_id": 0})
