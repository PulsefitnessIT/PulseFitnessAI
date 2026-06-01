"""Iter 220ea·19 — Engineer App Phase 5: Stock Control hub (read layer).

The write paths already exist and are reused as-is:
  • Parts used on a job (van auto-decrement + consume movement + machine
    tag + offline idempotency) → ``routes/svc/engineer_phase3.py``
    (``POST /api/svc/engineer/jobs/{case_id}/parts/use``).
  • Replenishment requests → ``routes/svc/engineer_parts_requests.py``.
  • Manual stock adjust / PO receive → ``routes/svc/inventory.py``.

This module ADDS the engineer-scoped READ endpoints the new mobile
"Stock" hub needs, aggregating over the *existing* collections
(``svc_van_stock``, ``svc_parts``, ``svc_part_movements``). No new
collections are introduced — we link to existing records, never
duplicate them.

Endpoints (all scoped to the calling engineer + org, gated by
``require_engineer_app_access``):
  • GET /api/svc/engineer/stock/van      — my van stock (enriched + filters)
  • GET /api/svc/engineer/stock/low      — my low/zero van lines + reorder qty
  • GET /api/svc/engineer/stock/history  — my stock movements (paged)
  • GET /api/svc/engineer/stock/asset    — parts used against a machine/asset

Field mapping authoritative in /app/memory/SVC_FIELD_MAPPING.md (§12-13).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db
import uuid

URGENCIES = {"normal", "urgent", "critical"}

router = APIRouter(
    prefix="/svc/engineer/stock",
    tags=["Service Ops · Engineer Stock"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _can_see_cost(user: dict) -> bool:
    """Cost price is owner/admin-only (desktop). Field engineers see the
    sell value only. Solo engineers are ``owner`` → they see their own
    cost; partner/enterprise engineers (``engineer``) do not."""
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("account_type") == "gymaxis_admin"
        or (user.get("role") or "") in {"owner", "owner_admin", "manager"}
    )


async def _usage_by_sku(of: dict, engineer_id: str) -> dict:
    """Aggregate consume movements → {sku: {used_count, last_used_at}}."""
    pipeline = [
        {"$match": {**of, "engineer_id": engineer_id,
                    "movement_type": "consume"}},
        {"$group": {
            "_id": "$part_sku",
            "used_count": {"$sum": {"$ifNull": ["$qty", 0]}},
            "last_used_at": {"$max": "$at"},
        }},
    ]
    out: dict = {}
    async for row in db.svc_part_movements.aggregate(pipeline):
        out[row["_id"]] = {
            "used_count": row.get("used_count") or 0,
            "last_used_at": row.get("last_used_at"),
        }
    return out


async def _replenished_by_sku(of: dict, engineer_id: str) -> dict:
    """Last inbound movement per sku → {sku: last_replenished_at}."""
    pipeline = [
        {"$match": {**of, "engineer_id": engineer_id,
                    "movement_type": {"$in": ["receive", "transfer_in",
                                              "deallocate", "adjust"]}}},
        {"$group": {"_id": "$part_sku", "last_at": {"$max": "$at"}}},
    ]
    out: dict = {}
    async for row in db.svc_part_movements.aggregate(pipeline):
        out[row["_id"]] = row.get("last_at")
    return out


def _min_qty(part: dict, van: dict) -> int:
    """Van min level — explicit van override beats catalogue threshold."""
    if van.get("min_qty") is not None:
        return int(van.get("min_qty") or 0)
    return int(part.get("reorder_threshold") or 0)


@router.get("/van")
async def my_van_stock(
    search: str = Query(""),
    category: str = Query(""),
    manufacturer: str = Query(""),
    stock_filter: str = Query("all", alias="filter"),
    sort: str = Query("name"),
    user=Depends(get_current_user),
):
    """My van stock — joined with the catalogue + usage signals.

    ``filter`` in all|low|zero|most_used|recent.
    ``sort``   in name|qty|most_used|recent.
    Sell price is always returned; cost only for owner/admin roles.
    """
    of = _of(user)
    eng = user["id"]
    show_cost = _can_see_cost(user)

    van_rows = await db.svc_van_stock.find(
        {**of, "engineer_id": eng}, {"_id": 0},
    ).to_list(2000)
    if not van_rows:
        return {"items": [], "summary": {
            "lines": 0, "low": 0, "zero": 0, "value_sell": 0.0,
        }, "show_cost": show_cost}

    skus = list({r["part_sku"] for r in van_rows})
    catalogue = await db.svc_parts.find(
        {**of, "sku": {"$in": skus}}, {"_id": 0},
    ).to_list(len(skus))
    by_sku = {p["sku"]: p for p in catalogue}

    usage = await _usage_by_sku(of, eng)
    replen = await _replenished_by_sku(of, eng)

    items = []
    total_low = total_zero = 0
    value_sell = 0.0
    for v in van_rows:
        sku = v["part_sku"]
        part = by_sku.get(sku, {})
        qty = int(v.get("qty") or 0)
        minq = _min_qty(part, v)
        u = usage.get(sku, {})
        sell = float(part.get("list_price") or 0)
        is_zero = qty <= 0
        is_low = (not is_zero) and minq > 0 and qty <= minq
        if is_zero:
            total_zero += 1
        if is_low:
            total_low += 1
        value_sell += sell * max(qty, 0)
        item = {
            "part_sku": sku,
            "name": part.get("name") or sku,
            "category": part.get("category") or "",
            "manufacturer": part.get("manufacturer") or "",
            "supplier": part.get("supplier") or "",
            "qty": qty,
            "min_qty": minq,
            "reorder_qty": int(part.get("reorder_qty") or 0),
            "bin_location": v.get("bin_location") or "",
            "sell_price": round(sell, 2),
            "used_count": u.get("used_count") or 0,
            "last_used_at": u.get("last_used_at"),
            "last_replenished_at": replen.get(sku) or v.get("last_replenished_at"),
            "in_catalogue": bool(part),
            "low": is_low,
            "zero": is_zero,
        }
        if show_cost:
            item["cost"] = round(float(part.get("cost") or 0), 2)
        items.append(item)

    # Server-side filtering
    f = (stock_filter or "all").lower()
    if f == "low":
        items = [i for i in items if i["low"] or i["zero"]]
    elif f == "zero":
        items = [i for i in items if i["zero"]]
    elif f == "most_used":
        items = [i for i in items if i["used_count"] > 0]
    elif f == "recent":
        items = [i for i in items if i["last_used_at"]]

    if search:
        s = search.lower()
        items = [i for i in items
                 if s in i["name"].lower() or s in i["part_sku"].lower()
                 or s in (i["manufacturer"] or "").lower()]
    if category:
        items = [i for i in items
                 if (i["category"] or "").lower() == category.lower()]
    if manufacturer:
        items = [i for i in items
                 if (i["manufacturer"] or "").lower() == manufacturer.lower()]

    # Server-side sort
    s = (sort or "name").lower()
    if s == "qty":
        items.sort(key=lambda i: i["qty"])
    elif s == "most_used":
        items.sort(key=lambda i: i["used_count"], reverse=True)
    elif s == "recent":
        items.sort(key=lambda i: i["last_used_at"] or "", reverse=True)
    else:
        items.sort(key=lambda i: i["name"].lower())

    return {
        "items": items,
        "summary": {
            "lines": len(van_rows),
            "low": total_low,
            "zero": total_zero,
            "value_sell": round(value_sell, 2),
        },
        "show_cost": show_cost,
    }


@router.get("/low")
async def my_low_stock(user=Depends(get_current_user)):
    """My van lines at/below their minimum level, with suggested reorder."""
    of = _of(user)
    eng = user["id"]
    van_rows = await db.svc_van_stock.find(
        {**of, "engineer_id": eng}, {"_id": 0},
    ).to_list(2000)
    if not van_rows:
        return {"rows": [], "count": 0}
    skus = list({r["part_sku"] for r in van_rows})
    catalogue = await db.svc_parts.find(
        {**of, "sku": {"$in": skus}}, {"_id": 0},
    ).to_list(len(skus))
    by_sku = {p["sku"]: p for p in catalogue}
    rows = []
    for v in van_rows:
        part = by_sku.get(v["part_sku"], {})
        qty = int(v.get("qty") or 0)
        minq = _min_qty(part, v)
        if minq <= 0 or qty > minq:
            continue
        reorder_to = int(part.get("reorder_qty") or 0) or max(minq * 2, minq + 1)
        rows.append({
            "part_sku": v["part_sku"],
            "name": part.get("name") or v["part_sku"],
            "manufacturer": part.get("manufacturer") or "",
            "qty": qty,
            "min_qty": minq,
            "suggested_qty": max(reorder_to - qty, 1),
            "zero": qty <= 0,
            "in_catalogue": bool(part),
        })
    rows.sort(key=lambda r: (not r["zero"], r["qty"]))
    return {"rows": rows, "count": len(rows)}


@router.get("/history")
async def my_stock_history(
    part_sku: Optional[str] = Query(None),
    movement_type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None, description="ISO cursor on `at`"),
    user=Depends(get_current_user),
):
    """My stock movement timeline (paged via `before` cursor on `at`)."""
    of = _of(user)
    q: dict = {**of, "engineer_id": user["id"]}
    if part_sku:
        q["part_sku"] = part_sku.strip().upper()
    if movement_type:
        q["movement_type"] = movement_type
    if before:
        q["at"] = {"$lt": before}
    rows = await db.svc_part_movements.find(q, {"_id": 0}) \
        .sort("at", -1).limit(limit).to_list(limit)
    next_cursor = rows[-1]["at"] if len(rows) == limit and rows else None
    return {"items": rows, "next_cursor": next_cursor}


@router.get("/asset")
async def parts_used_on_asset(
    machine_id: Optional[str] = Query(None),
    machine_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=300),
    user=Depends(get_current_user),
):
    """Parts-used history tagged to a specific machine/asset.

    Powers the per-asset 'parts fitted' timeline (repeat-failure / CAPEX
    signal). Matches the machine tag carried on consume movements.
    """
    of = _of(user)
    if not machine_id and not machine_name:
        return {"items": [], "count": 0, "total_qty": 0}
    q: dict = {**of, "movement_type": "consume"}
    if machine_id:
        q["machine_id"] = machine_id
    elif machine_name:
        q["machine_name"] = {"$regex": f"^{machine_name}$", "$options": "i"}
    rows = await db.svc_part_movements.find(q, {"_id": 0}) \
        .sort("at", -1).limit(limit).to_list(limit)
    total_qty = sum(int(r.get("qty") or 0) for r in rows)
    return {"items": rows, "count": len(rows), "total_qty": total_qty}


# ─────────────────────────────────────────────────────────────────
# Van-level replenishment (no job context)
# ─────────────────────────────────────────────────────────────────


class VanReplenishIn(BaseModel):
    part_sku: str = Field(..., min_length=1)
    part_name: Optional[str] = None
    qty: int = Field(..., gt=0, le=999)
    urgency: str = Field(default="normal")
    notes: Optional[str] = ""


@router.post("/replenish", status_code=201)
async def request_van_replenishment(body: VanReplenishIn,
                                    user=Depends(get_current_user)):
    """Engineer asks the office to top up their van — NOT tied to a job.

    Writes to the existing ``svc_parts_requests`` collection (case_id
    null, kind=``van_replenish``) so it lands in the same admin inbox.
    On approve the office tops up the van directly (see
    ``engineer_parts_requests.admin_approve`` case-less branch).
    """
    of = _of(user)
    urgency = body.urgency.lower()
    if urgency not in URGENCIES:
        raise HTTPException(422, f"urgency must be one of {sorted(URGENCIES)}")
    sku = body.part_sku.strip().upper()
    catalogue = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
    name = (body.part_name or "").strip() or (catalogue or {}).get("name") or sku
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": None,
        "case_reference": None,
        "kind": "van_replenish",
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "part_sku": sku,
        "part_name": name,
        "qty": body.qty,
        "list_price_gbp": float((catalogue or {}).get("list_price") or 0),
        "urgency": urgency,
        "notes": (body.notes or "").strip(),
        "status": "pending",
        "in_catalogue": bool(catalogue),
        "machine_id": None,
        "machine_name": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_parts_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


__all__ = ["router"]
