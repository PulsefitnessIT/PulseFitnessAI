"""Iter 220ea·22 — Stock Phase 4 · Office/Admin stock overview.

Office-side stock management built entirely on the existing stock
collections (``svc_van_stock``, ``svc_warehouse_stock``, ``svc_parts``,
``svc_part_movements``) — no duplicate records. Gives owners / admins /
managers:

  • **Overview** — every engineer's van + the warehouse, with
    qty / value / low / zero rollups and org totals.
  • **By-location** — detailed line items for the warehouse or a chosen
    engineer's van.
  • **Transfer** — immediate stock moves (warehouse↔van, van↔van) with a
    paired movement audit trail (``transfer_out`` / ``transfer_in``).
  • **Stock-take** — post counted qty per part → variance vs expected →
    one-click ``adjust`` movements.
  • **Cross-org** (master / pulse admins) — stock value + low/zero per
    organization, drill into any org.

Engineer identity in van stock is the **user id** (the engineer app
keys ``svc_van_stock.engineer_id`` to ``user["id"]``), so all engineer
pickers/resolvers here use user ids.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/svc/admin/stock", tags=["Service Ops · Admin Stock"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _can_manage(user: dict) -> bool:
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("account_type") == "gymaxis_admin"
        or (user.get("role") or "") in {"owner", "owner_admin", "manager"}
    )


def _can_cross_org(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("is_pulse_admin"))


def _require_manage(user: dict) -> None:
    if not _can_manage(user):
        raise HTTPException(403, "Owners, managers and admins only")


async def _cat_map(of: dict, skus) -> dict:
    """sku → catalogue fields needed for valuation / low-stock flags."""
    skus = [s for s in skus if s]
    if not skus:
        return {}
    out: dict = {}
    async for p in db.svc_parts.find(
        {**of, "sku": {"$in": skus}},
        {"_id": 0, "sku": 1, "name": 1, "list_price": 1, "cost": 1,
         "reorder_threshold": 1, "manufacturer": 1, "category": 1},
    ):
        out[p["sku"]] = p
    return out


async def _resolve_engineer_names(ids) -> dict:
    ids = [i for i in set(ids) if i]
    out: dict = {}
    if not ids:
        return out
    async for u in db.users.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1},
    ):
        out[u["id"]] = u.get("full_name") or u.get("email") or ""
    missing = [i for i in ids if not out.get(i)]
    if missing:
        async for p in db.partner_engineers.find(
            {"user_id": {"$in": missing}},
            {"_id": 0, "user_id": 1, "full_name": 1, "trading_name": 1},
        ):
            out[p["user_id"]] = p.get("trading_name") or p.get("full_name") or out.get(p["user_id"]) or ""
    missing = [i for i in ids if not out.get(i)]
    if missing:
        async for e in db.svc_engineers.find(
            {"id": {"$in": missing}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1},
        ):
            out[e["id"]] = e.get("full_name") or e.get("email") or ""
    for i in ids:
        out.setdefault(i, f"Engineer {i[:6]}")
    return out


async def _org_engineer_ids(of: dict) -> set:
    ids = set(await db.svc_van_stock.distinct("engineer_id", of))
    ids |= set(await db.svc_cases.distinct("assigned_engineer_id", of))
    async for p in db.partner_engineers.find({**of}, {"_id": 0, "user_id": 1}):
        if p.get("user_id"):
            ids.add(p["user_id"])
    return {i for i in ids if i}


def _line_flags(qty: int, part: dict) -> tuple[bool, bool, int]:
    minq = int(part.get("reorder_threshold") or 0)
    zero = qty <= 0
    low = bool(minq > 0 and 0 < qty <= minq)
    return low, zero, minq


def _reorder_suggestion(qty: int, part: dict) -> int:
    """Suggested order qty when a line is at/below its minimum: top up to
    the max (target) level, else fall back to the reorder qty, else the
    shortfall to min."""
    minq = int(part.get("reorder_threshold") or 0)
    maxq = int(part.get("reorder_max") or 0)
    if minq <= 0 or qty > minq:
        return 0
    if maxq > qty:
        return maxq - qty
    roq = int(part.get("reorder_qty") or 0)
    return roq if roq > 0 else max(minq - qty, 0)


# ───────────────────────────── Overview ───────────────────────────

@router.get("/overview")
async def overview(user=Depends(get_current_user)):
    """Org-wide rollup: warehouse + every engineer's van, with value +
    low/zero counts. Cost values gated to managers (always true here)."""
    _require_manage(user)
    of = _of(user)
    show_cost = _can_manage(user)

    van_rows = await db.svc_van_stock.find(of, {"_id": 0}).to_list(50000)
    wh_rows = await db.svc_warehouse_stock.find(
        {**of, "location": "warehouse"}, {"_id": 0},
    ).to_list(50000)
    skus = {r.get("part_sku") for r in van_rows} | {r.get("part_sku") for r in wh_rows}
    cat = await _cat_map(of, skus)
    names = await _resolve_engineer_names([r.get("engineer_id") for r in van_rows])

    eng_summary: dict = {}
    for r in van_rows:
        eid = r.get("engineer_id") or ""
        s = eng_summary.setdefault(eid, {
            "engineer_id": eid, "name": names.get(eid, ""),
            "lines": 0, "units": 0, "value_sell": 0.0, "value_cost": 0.0,
            "low": 0, "zero": 0,
        })
        qty = int(r.get("qty") or 0)
        p = cat.get(r.get("part_sku"), {})
        low, zero, _ = _line_flags(qty, p)
        s["lines"] += 1
        s["units"] += qty
        s["value_sell"] += float(p.get("list_price") or 0) * qty
        s["value_cost"] += float(p.get("cost") or 0) * qty
        s["low"] += int(low)
        s["zero"] += int(zero)

    engineers = sorted(eng_summary.values(), key=lambda x: (x["name"] or "").lower())

    wh = {"lines": 0, "units": 0, "value_sell": 0.0, "value_cost": 0.0, "low": 0, "zero": 0}
    for r in wh_rows:
        qty = int(r.get("qty") or 0)
        p = cat.get(r.get("part_sku"), {})
        low, zero, _ = _line_flags(qty, p)
        wh["lines"] += 1
        wh["units"] += qty
        wh["value_sell"] += float(p.get("list_price") or 0) * qty
        wh["value_cost"] += float(p.get("cost") or 0) * qty
        wh["low"] += int(low)
        wh["zero"] += int(zero)

    totals = {
        "catalogue_parts": await db.svc_parts.count_documents(of),
        "value_sell": round(wh["value_sell"] + sum(e["value_sell"] for e in engineers), 2),
        "value_cost": round(wh["value_cost"] + sum(e["value_cost"] for e in engineers), 2),
        "low": wh["low"] + sum(e["low"] for e in engineers),
        "zero": wh["zero"] + sum(e["zero"] for e in engineers),
        "engineers": len(engineers),
    }
    for e in engineers:
        e["value_sell"] = round(e["value_sell"], 2)
        e["value_cost"] = round(e["value_cost"], 2)
    wh["value_sell"] = round(wh["value_sell"], 2)
    wh["value_cost"] = round(wh["value_cost"], 2)
    if not show_cost:
        for e in engineers:
            e.pop("value_cost", None)
        wh.pop("value_cost", None)
        totals.pop("value_cost", None)
    return {"warehouse": wh, "engineers": engineers, "totals": totals,
            "show_cost": show_cost, "can_cross_org": _can_cross_org(user)}


@router.get("/by-location")
async def by_location(
    location: str = Query("warehouse"),
    engineer_id: str = Query(""),
    search: str = Query(""),
    user=Depends(get_current_user),
):
    """Detailed line items at a location (warehouse or one engineer's van)."""
    _require_manage(user)
    of = _of(user)
    show_cost = _can_manage(user)
    if location == "van":
        if not engineer_id:
            raise HTTPException(400, "engineer_id required for van stock")
        rows = await db.svc_van_stock.find(
            {**of, "engineer_id": engineer_id}, {"_id": 0}).to_list(50000)
    else:
        location = "warehouse"
        rows = await db.svc_warehouse_stock.find(
            {**of, "location": "warehouse"}, {"_id": 0}).to_list(50000)
    cat = await _cat_map(of, {r.get("part_sku") for r in rows})
    q = (search or "").lower().strip()
    items = []
    for r in rows:
        p = cat.get(r.get("part_sku"), {})
        if q:
            hay = f"{r.get('part_sku', '')} {p.get('name', '')} {p.get('manufacturer', '')}".lower()
            if q not in hay:
                continue
        qty = int(r.get("qty") or 0)
        low, zero, minq = _line_flags(qty, p)
        maxq = int(p.get("reorder_max") or 0)
        item = {
            "part_sku": r.get("part_sku"), "name": p.get("name") or r.get("part_sku"),
            "manufacturer": p.get("manufacturer", ""), "category": p.get("category", ""),
            "qty": qty, "min_qty": minq, "max_qty": maxq, "low": low, "zero": zero,
            "below_min": bool(minq > 0 and qty <= minq),
            "suggested_order": _reorder_suggestion(qty, p),
            "sell_price": float(p.get("list_price") or 0),
            "value_sell": round(float(p.get("list_price") or 0) * qty, 2),
        }
        if show_cost:
            item["cost"] = float(p.get("cost") or 0)
            item["value_cost"] = round(float(p.get("cost") or 0) * qty, 2)
        items.append(item)
    items.sort(key=lambda x: (x["name"] or "").lower())
    return {"location": location, "engineer_id": engineer_id,
            "items": items, "count": len(items), "show_cost": show_cost}


@router.get("/locations")
async def locations(user=Depends(get_current_user)):
    """Warehouse + the org's engineers (user-id keyed) for transfer /
    stock-take pickers. Drops stale case-assignee ids that resolve to no
    real name and hold no van stock (avoids confusing UUID labels)."""
    _require_manage(user)
    of = _of(user)
    ids = await _org_engineer_ids(of)
    van_holders = set(await db.svc_van_stock.distinct("engineer_id", of))
    names = await _resolve_engineer_names(list(ids))
    engineers = []
    for i in ids:
        nm = names.get(i, "")
        resolved = bool(nm) and nm != f"Engineer {i[:6]}"
        if resolved or i in van_holders:
            # Iter 220ea·24 — never surface a raw UUID prefix as a label.
            # Unresolved van holders read "Unnamed engineer" instead of
            # the confusing "Engineer 663ec6" fallback.
            engineers.append({"engineer_id": i, "name": nm if resolved else "Unnamed engineer"})
    engineers.sort(key=lambda x: (x["name"] or "").lower())
    return {"warehouse": True, "engineers": engineers}


# ───────────────────────────── Transfer ───────────────────────────

async def _stock_doc(of, loc_type, engineer_id, sku):
    if loc_type == "van":
        return await db.svc_van_stock.find_one(
            {**of, "engineer_id": engineer_id, "part_sku": sku})
    return await db.svc_warehouse_stock.find_one(
        {**of, "location": "warehouse", "part_sku": sku})


async def _apply_delta(of, loc_type, engineer_id, sku, delta):
    if loc_type == "van":
        await db.svc_van_stock.update_one(
            {**of, "engineer_id": engineer_id, "part_sku": sku},
            {"$inc": {"qty": delta}, "$set": {"updated_at": _now()},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
            upsert=True)
    else:
        await db.svc_warehouse_stock.update_one(
            {**of, "location": "warehouse", "part_sku": sku},
            {"$inc": {"qty": delta}, "$set": {"updated_at": _now()},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
            upsert=True)


@router.post("/transfer")
async def transfer(
    body: dict,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Immediate stock move between two locations with a paired audit
    trail. Body: {part_sku, qty>0, from:{type,engineer_id?},
    to:{type,engineer_id?}, reason?}."""
    _require_manage(user)
    of = _of(user)
    sku = ((body or {}).get("part_sku") or "").strip().upper()
    qty = int((body or {}).get("qty") or 0)
    src = (body or {}).get("from") or {}
    dst = (body or {}).get("to") or {}
    reason = ((body or {}).get("reason") or "").strip()
    if not sku or qty <= 0:
        raise HTTPException(400, "part_sku and a positive qty are required")
    src_type = (src.get("type") or "").lower()
    dst_type = (dst.get("type") or "").lower()
    if src_type not in ("warehouse", "van") or dst_type not in ("warehouse", "van"):
        raise HTTPException(400, "from.type and to.type must be warehouse|van")
    src_eng = src.get("engineer_id") or ""
    dst_eng = dst.get("engineer_id") or ""
    if src_type == "van" and not src_eng:
        raise HTTPException(400, "from.engineer_id required for a van source")
    if dst_type == "van" and not dst_eng:
        raise HTTPException(400, "to.engineer_id required for a van destination")
    if src_type == dst_type and src_eng == dst_eng:
        raise HTTPException(400, "Source and destination are the same")
    part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
    if not part:
        raise HTTPException(404, f"Part {sku} not in catalogue")

    if idempotency_key:
        prev = await db.svc_part_movements.find_one(
            {**of, "idempotency_key": idempotency_key}, {"_id": 0})
        if prev:
            return {"ok": True, "already_done": True}

    s = await _stock_doc(of, src_type, src_eng, sku)
    on_hand = int((s or {}).get("qty") or 0)
    if on_hand < qty:
        raise HTTPException(409, f"Only {on_hand} in stock at source — cannot move {qty}")

    await _apply_delta(of, src_type, src_eng, sku, -qty)
    await _apply_delta(of, dst_type, dst_eng, sku, qty)

    src_label = f"van:{src_eng}" if src_type == "van" else "warehouse"
    dst_label = f"van:{dst_eng}" if dst_type == "van" else "warehouse"
    transfer_id = str(uuid.uuid4())
    base = {
        "organization_id": of["organization_id"], "part_sku": sku,
        "part_name": part.get("name") or sku,
        "actor_id": user["id"], "actor_name": user.get("full_name") or user.get("email") or "",
        "reason": reason or "Office transfer", "at": _now(),
        "transfer_id": transfer_id, "from_location": src_label, "to_location": dst_label,
    }
    if idempotency_key:
        base["idempotency_key"] = idempotency_key
    await db.svc_part_movements.insert_many([
        {**base, "id": str(uuid.uuid4()), "movement_type": "transfer_out",
         "qty": -qty, "location": src_type, "engineer_id": src_eng},
        {**base, "id": str(uuid.uuid4()), "movement_type": "transfer_in",
         "qty": qty, "location": dst_type, "engineer_id": dst_eng},
    ])
    return {"ok": True, "part_sku": sku, "qty": qty,
            "from": src_label, "to": dst_label, "transfer_id": transfer_id}


def _validate_locs(src: dict, dst: dict):
    """Shared from/to validation for transfers. Returns
    (src_type, src_eng, dst_type, dst_eng)."""
    src_type = (src.get("type") or "").lower()
    dst_type = (dst.get("type") or "").lower()
    if src_type not in ("warehouse", "van") or dst_type not in ("warehouse", "van"):
        raise HTTPException(400, "from.type and to.type must be warehouse|van")
    src_eng = src.get("engineer_id") or ""
    dst_eng = dst.get("engineer_id") or ""
    if src_type == "van" and not src_eng:
        raise HTTPException(400, "from.engineer_id required for a van source")
    if dst_type == "van" and not dst_eng:
        raise HTTPException(400, "to.engineer_id required for a van destination")
    if src_type == dst_type and src_eng == dst_eng:
        raise HTTPException(400, "Source and destination are the same")
    return src_type, src_eng, dst_type, dst_eng


@router.post("/availability")
async def availability(body: dict, user=Depends(get_current_user)):
    """Current on-hand qty for a set of SKUs at one location — used by the
    transfer cart to show 'X in stock at <source>' and stop over-transfers
    before they error. Body: {location, engineer_id?, part_skus:[...]}."""
    _require_manage(user)
    of = _of(user)
    location = ((body or {}).get("location") or "warehouse").lower()
    engineer_id = (body or {}).get("engineer_id") or ""
    skus = [str(s).strip().upper() for s in ((body or {}).get("part_skus") or []) if s]
    skus = list(dict.fromkeys(skus))[:500]
    if not skus:
        return {"location": location, "engineer_id": engineer_id, "availability": {}}
    if location == "van":
        cur = db.svc_van_stock.find(
            {**of, "engineer_id": engineer_id, "part_sku": {"$in": skus}},
            {"_id": 0, "part_sku": 1, "qty": 1})
    else:
        cur = db.svc_warehouse_stock.find(
            {**of, "location": "warehouse", "part_sku": {"$in": skus}},
            {"_id": 0, "part_sku": 1, "qty": 1})
    found: dict = {}
    async for r in cur:
        found[r["part_sku"]] = int(r.get("qty") or 0)
    return {"location": location, "engineer_id": engineer_id,
            "availability": {s: found.get(s, 0) for s in skus}}


@router.post("/transfer-batch")
async def transfer_batch(
    body: dict,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Move MULTIPLE parts between two locations in one go. Validates
    every line first (part exists + enough at source); if any line fails
    nothing is applied and a 409 lists the shortfalls. Body:
    {from, to, items:[{part_sku, qty}], reason?}."""
    _require_manage(user)
    of = _of(user)
    src = (body or {}).get("from") or {}
    dst = (body or {}).get("to") or {}
    reason = ((body or {}).get("reason") or "").strip()
    src_type, src_eng, dst_type, dst_eng = _validate_locs(src, dst)

    # Normalise + aggregate duplicate SKUs.
    agg: dict[str, int] = {}
    for it in (body or {}).get("items") or []:
        sku = ((it or {}).get("part_sku") or "").strip().upper()
        qty = int((it or {}).get("qty") or 0)
        if sku and qty > 0:
            agg[sku] = agg.get(sku, 0) + qty
    if not agg:
        raise HTTPException(400, "Add at least one part with a positive qty")

    if idempotency_key:
        prev = await db.svc_part_movements.find_one(
            {**of, "idempotency_key": idempotency_key}, {"_id": 0})
        if prev:
            return {"ok": True, "already_done": True}

    # Validate every line before touching stock (all-or-nothing).
    parts: dict[str, dict] = {}
    failures: list[dict] = []
    for sku, qty in agg.items():
        part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
        if not part:
            failures.append({"part_sku": sku, "reason": "not in catalogue"})
            continue
        parts[sku] = part
        s = await _stock_doc(of, src_type, src_eng, sku)
        on_hand = int((s or {}).get("qty") or 0)
        if on_hand < qty:
            failures.append({"part_sku": sku, "reason": f"only {on_hand} at source",
                             "available": on_hand, "requested": qty})
    if failures:
        raise HTTPException(409, {"message": "Some lines cannot be transferred",
                                  "failures": failures})

    src_label = f"van:{src_eng}" if src_type == "van" else "warehouse"
    dst_label = f"van:{dst_eng}" if dst_type == "van" else "warehouse"
    transfer_id = str(uuid.uuid4())
    actor_name = user.get("full_name") or user.get("email") or ""
    movements: list[dict] = []
    for sku, qty in agg.items():
        await _apply_delta(of, src_type, src_eng, sku, -qty)
        await _apply_delta(of, dst_type, dst_eng, sku, qty)
        base = {
            "organization_id": of["organization_id"], "part_sku": sku,
            "part_name": parts[sku].get("name") or sku,
            "actor_id": user["id"], "actor_name": actor_name,
            "reason": reason or "Office transfer", "at": _now(),
            "transfer_id": transfer_id, "from_location": src_label, "to_location": dst_label,
        }
        if idempotency_key:
            base["idempotency_key"] = idempotency_key
        movements.append({**base, "id": str(uuid.uuid4()), "movement_type": "transfer_out",
                          "qty": -qty, "location": src_type, "engineer_id": src_eng})
        movements.append({**base, "id": str(uuid.uuid4()), "movement_type": "transfer_in",
                          "qty": qty, "location": dst_type, "engineer_id": dst_eng})
    await db.svc_part_movements.insert_many(movements)
    return {"ok": True, "transferred": len(agg),
            "items": [{"part_sku": k, "qty": v} for k, v in agg.items()],
            "from": src_label, "to": dst_label, "transfer_id": transfer_id}


# ───────────────────────────── Stock-take ─────────────────────────

@router.post("/stock-take")
async def stock_take(
    body: dict,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Post a physical count. For each line we compute variance vs the
    expected qty and, where non-zero, set the stock to the counted value
    and write an ``adjust`` movement tagged as a stock-take.

    Body: {location: warehouse|van, engineer_id?,
           counts:[{part_sku, counted_qty}], reason?}."""
    _require_manage(user)
    of = _of(user)
    location = ((body or {}).get("location") or "warehouse").lower()
    engineer_id = (body or {}).get("engineer_id") or ""
    counts = (body or {}).get("counts") or []
    reason = ((body or {}).get("reason") or "Stock-take").strip()
    if location not in ("warehouse", "van"):
        raise HTTPException(400, "location must be warehouse|van")
    if location == "van" and not engineer_id:
        raise HTTPException(400, "engineer_id required for a van stock-take")
    if not counts:
        raise HTTPException(400, "counts required")

    # Iter 220ea·24 — dedupe duplicate submits on slow networks so a
    # stock-take is never double-posted (which would otherwise write a
    # second batch of ``adjust`` movements into the audit trail).
    if idempotency_key:
        prev = await db.svc_part_movements.find_one(
            {**of, "idempotency_key": idempotency_key}, {"_id": 0})
        if prev:
            return {"ok": True, "already_done": True, "checked": 0,
                    "adjusted": 0, "variance_units": 0, "lines": []}

    checked = adjusted = 0
    variance_units = 0
    movements: list[dict] = []
    lines: list[dict] = []
    for c in counts:
        sku = ((c or {}).get("part_sku") or "").strip().upper()
        if not sku:
            continue
        counted = int((c or {}).get("counted_qty") or 0)
        checked += 1
        s = await _stock_doc(of, location, engineer_id, sku)
        expected = int((s or {}).get("qty") or 0)
        delta = counted - expected
        lines.append({"part_sku": sku, "expected": expected,
                      "counted": counted, "variance": delta})
        if delta == 0:
            continue
        await _apply_delta(of, location, engineer_id, sku, 0)  # ensure row exists
        if location == "van":
            await db.svc_van_stock.update_one(
                {**of, "engineer_id": engineer_id, "part_sku": sku},
                {"$set": {"qty": counted, "updated_at": _now()}})
        else:
            await db.svc_warehouse_stock.update_one(
                {**of, "location": "warehouse", "part_sku": sku},
                {"$set": {"qty": counted, "updated_at": _now()}})
        movements.append({
            "id": str(uuid.uuid4()), "organization_id": of["organization_id"],
            "movement_type": "adjust", "part_sku": sku, "qty": delta,
            "location": location, "engineer_id": engineer_id,
            "reason": f"{reason} (variance {'+' if delta > 0 else ''}{delta})",
            "actor_id": user["id"], "actor_name": user.get("full_name") or "",
            "at": _now(), "stock_take": True,
            **({"idempotency_key": idempotency_key} if idempotency_key else {}),
        })
        adjusted += 1
        variance_units += delta
    if movements:
        await db.svc_part_movements.insert_many(movements)
    return {"ok": True, "checked": checked, "adjusted": adjusted,
            "variance_units": variance_units, "lines": lines}


# ───────────────────────────── Cross-org ──────────────────────────

async def _org_totals(org_id: str) -> dict:
    of = {"organization_id": org_id}
    van = await db.svc_van_stock.find(
        of, {"_id": 0, "part_sku": 1, "qty": 1, "engineer_id": 1}).to_list(100000)
    wh = await db.svc_warehouse_stock.find(
        {**of, "location": "warehouse"}, {"_id": 0, "part_sku": 1, "qty": 1}).to_list(100000)
    cat = await _cat_map(of, {r.get("part_sku") for r in van} | {r.get("part_sku") for r in wh})
    vs = vc = 0.0
    units = low = zero = 0
    for r in van + wh:
        qty = int(r.get("qty") or 0)
        p = cat.get(r.get("part_sku"), {})
        vs += float(p.get("list_price") or 0) * qty
        vc += float(p.get("cost") or 0) * qty
        units += qty
        lo, ze, _ = _line_flags(qty, p)
        low += int(lo)
        zero += int(ze)
    return {
        "lines": len(van) + len(wh), "units": units,
        "value_sell": round(vs, 2), "value_cost": round(vc, 2),
        "low": low, "zero": zero,
        "van_engineers": len({r.get("engineer_id") for r in van if r.get("engineer_id")}),
    }


@router.get("/cross-org")
async def cross_org(user=Depends(get_current_user)):
    """Master / Pulse admin rollup: stock value + low/zero per org."""
    if not _can_cross_org(user):
        raise HTTPException(403, "Master / Pulse admins only")
    org_ids = set(await db.svc_van_stock.distinct("organization_id")) \
        | set(await db.svc_warehouse_stock.distinct("organization_id"))
    org_ids = {o for o in org_ids if o}
    rows = []
    for oid in org_ids:
        t = await _org_totals(oid)
        org = await db.organizations.find_one({"id": oid}, {"_id": 0, "name": 1})
        rows.append({"organization_id": oid,
                     "name": (org or {}).get("name") or oid[:8], **t})
    rows.sort(key=lambda x: -x["value_sell"])
    totals = {
        "orgs": len(rows),
        "value_sell": round(sum(r["value_sell"] for r in rows), 2),
        "value_cost": round(sum(r["value_cost"] for r in rows), 2),
        "low": sum(r["low"] for r in rows),
        "zero": sum(r["zero"] for r in rows),
    }
    return {"organizations": rows, "totals": totals}


# ─────────────────── Reorder report (min/max levels) ──────────────

async def _location_stock_map(of: dict, location: str, engineer_id: str) -> dict:
    if location == "van":
        cur = db.svc_van_stock.find({**of, "engineer_id": engineer_id}, {"_id": 0, "part_sku": 1, "qty": 1})
    else:
        cur = db.svc_warehouse_stock.find({**of, "location": "warehouse"}, {"_id": 0, "part_sku": 1, "qty": 1})
    out: dict = {}
    async for r in cur:
        out[r["part_sku"]] = int(r.get("qty") or 0)
    return out


def _loc_label(location: str, engineer_id: str, names: dict) -> str:
    if location == "van":
        return f"{names.get(engineer_id, 'Van')} (van)"
    return "Warehouse"


async def _reorder_items(of: dict, location: str, engineer_id: str, show_cost: bool) -> tuple[list, dict]:
    """Catalogue parts with a minimum set whose on-hand at the location is
    at/below that minimum, with a suggested order qty (top-up to max)."""
    parts = await db.svc_parts.find(
        {**of, "reorder_threshold": {"$gt": 0}},
        {"_id": 0, "sku": 1, "name": 1, "manufacturer": 1, "supplier": 1,
         "category": 1, "reorder_threshold": 1, "reorder_max": 1, "reorder_qty": 1,
         "list_price": 1, "cost": 1},
    ).to_list(50000)
    stock = await _location_stock_map(of, location, engineer_id)
    items = []
    for p in parts:
        minq = int(p.get("reorder_threshold") or 0)
        qty = stock.get(p["sku"], 0)
        if qty > minq:
            continue
        suggested = _reorder_suggestion(qty, p)
        item = {
            "part_sku": p["sku"], "name": p.get("name") or p["sku"],
            "manufacturer": p.get("manufacturer", ""), "supplier": p.get("supplier", ""),
            "category": p.get("category", ""), "qty": qty, "min_qty": minq,
            "max_qty": int(p.get("reorder_max") or 0), "suggested_order": suggested,
            "zero": qty <= 0, "sell_price": float(p.get("list_price") or 0),
        }
        if show_cost:
            item["cost"] = float(p.get("cost") or 0)
            item["est_order_cost"] = round(float(p.get("cost") or 0) * suggested, 2)
        items.append(item)
    # Most urgent (deepest below min, then zero stock) first.
    items.sort(key=lambda x: (x["qty"] - x["min_qty"], x["qty"]))
    totals = {
        "parts": len(items),
        "suggested_units": sum(i["suggested_order"] for i in items),
        "est_order_cost": round(sum(i.get("est_order_cost", 0) for i in items), 2) if show_cost else None,
    }
    return items, totals


@router.get("/reorder-report")
async def reorder_report(
    location: str = Query("warehouse"), engineer_id: str = Query(""),
    user=Depends(get_current_user),
):
    _require_manage(user)
    of = _of(user)
    location = "van" if location == "van" else "warehouse"
    if location == "van" and not engineer_id:
        raise HTTPException(400, "engineer_id required for a van reorder report")
    show_cost = _can_manage(user)
    items, totals = await _reorder_items(of, location, engineer_id, show_cost)
    names = await _resolve_engineer_names([engineer_id]) if engineer_id else {}
    return {"location": location, "engineer_id": engineer_id,
            "location_label": _loc_label(location, engineer_id, names),
            "items": items, "totals": totals, "show_cost": show_cost}


@router.get("/reorder-report.csv")
async def reorder_report_csv(
    location: str = Query("warehouse"), engineer_id: str = Query(""),
    user=Depends(get_current_user),
):
    _require_manage(user)
    of = _of(user)
    location = "van" if location == "van" else "warehouse"
    show_cost = _can_manage(user)
    items, _ = await _reorder_items(of, location, engineer_id, show_cost)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["SKU", "Name", "Manufacturer", "Supplier", "On hand", "Min", "Max", "Suggested order"]
    if show_cost:
        head += ["Unit cost", "Est. order cost"]
    w.writerow(head)
    for it in items:
        row = [it["part_sku"], it["name"], it["manufacturer"], it["supplier"],
               it["qty"], it["min_qty"], it["max_qty"], it["suggested_order"]]
        if show_cost:
            row += [it.get("cost", 0), it.get("est_order_cost", 0)]
        w.writerow(row)
    buf.seek(0)
    fname = f"reorder-{location}-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


# ─────────────── Phase 5 — Weekly/Monthly stock report ────────────

async def _report_snapshot(of: dict, location: str, engineer_id: str, show_cost: bool) -> tuple[list, dict]:
    if location == "van":
        rows = await db.svc_van_stock.find({**of, "engineer_id": engineer_id}, {"_id": 0}).to_list(50000)
    else:
        rows = await db.svc_warehouse_stock.find({**of, "location": "warehouse"}, {"_id": 0}).to_list(50000)
    cat = await _cat_map(of, {r.get("part_sku") for r in rows})
    lines = []
    units = below = out = 0
    vs = vc = 0.0
    for r in rows:
        qty = int(r.get("qty") or 0)
        p = cat.get(r.get("part_sku"), {})
        minq = int(p.get("reorder_threshold") or 0)
        sell = float(p.get("list_price") or 0)
        cost = float(p.get("cost") or 0)
        units += qty
        vs += sell * qty
        vc += cost * qty
        if qty <= 0:
            out += 1
        if minq > 0 and qty <= minq:
            below += 1
        line = {"part_sku": r.get("part_sku"), "name": p.get("name") or r.get("part_sku"),
                "qty": qty, "min_qty": minq, "max_qty": int(p.get("reorder_max") or 0),
                "value_sell": round(sell * qty, 2)}
        if show_cost:
            line["value_cost"] = round(cost * qty, 2)
        lines.append(line)
    lines.sort(key=lambda x: (x["name"] or "").lower())
    snap = {"lines": len(rows), "units": units, "below_min": below, "out": out,
            "value_sell": round(vs, 2)}
    if show_cost:
        snap["value_cost"] = round(vc, 2)
    return lines, snap


async def _period_movements(of: dict, location: str, engineer_id: str, days: int) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = {**of, "at": {"$gte": since}, "location": location}
    if location == "van":
        q["engineer_id"] = engineer_id
    agg: dict = {}
    async for m in db.svc_part_movements.find(q, {"_id": 0, "movement_type": 1, "qty": 1}):
        mt = m.get("movement_type") or "other"
        a = agg.setdefault(mt, {"type": mt, "count": 0, "units": 0})
        a["count"] += 1
        a["units"] += abs(int(m.get("qty") or 0))
    return sorted(agg.values(), key=lambda x: -x["count"])


@router.get("/report")
async def stock_report(
    location: str = Query("warehouse"), engineer_id: str = Query(""),
    period: str = Query("month"), user=Depends(get_current_user),
):
    _require_manage(user)
    of = _of(user)
    location = "van" if location == "van" else "warehouse"
    if location == "van" and not engineer_id:
        raise HTTPException(400, "engineer_id required for a van report")
    show_cost = _can_manage(user)
    days = 7 if period == "week" else 30
    _, snap = await _report_snapshot(of, location, engineer_id, show_cost)
    movements = await _period_movements(of, location, engineer_id, days)
    names = await _resolve_engineer_names([engineer_id]) if engineer_id else {}
    return {"location": location, "engineer_id": engineer_id,
            "location_label": _loc_label(location, engineer_id, names),
            "period": "week" if period == "week" else "month",
            "snapshot": snap, "movements": movements, "show_cost": show_cost,
            "generated_at": _now()}


@router.get("/report.csv")
async def stock_report_csv(
    location: str = Query("warehouse"), engineer_id: str = Query(""),
    user=Depends(get_current_user),
):
    _require_manage(user)
    of = _of(user)
    location = "van" if location == "van" else "warehouse"
    show_cost = _can_manage(user)
    lines, _ = await _report_snapshot(of, location, engineer_id, show_cost)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["SKU", "Name", "On hand", "Min", "Max", "Stock value"]
    if show_cost:
        head.append("Cost value")
    w.writerow(head)
    for ln in lines:
        row = [ln["part_sku"], ln["name"], ln["qty"], ln["min_qty"], ln["max_qty"], ln["value_sell"]]
        if show_cost:
            row.append(ln.get("value_cost", 0))
        w.writerow(row)
    buf.seek(0)
    fname = f"stock-{location}-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/report.pdf")
async def stock_report_pdf(
    location: str = Query("warehouse"), engineer_id: str = Query(""),
    period: str = Query("month"), user=Depends(get_current_user),
):
    _require_manage(user)
    of = _of(user)
    location = "van" if location == "van" else "warehouse"
    show_cost = _can_manage(user)
    days = 7 if period == "week" else 30
    lines, snap = await _report_snapshot(of, location, engineer_id, show_cost)
    movements = await _period_movements(of, location, engineer_id, days)
    items, _ = await _reorder_items(of, location, engineer_id, show_cost)
    names = await _resolve_engineer_names([engineer_id]) if engineer_id else {}
    label = _loc_label(location, engineer_id, names)
    pdf = _build_report_pdf(label, "week" if period == "week" else "month",
                            snap, movements, items, lines, show_cost)
    fname = f"stock-report-{location}-{datetime.now(timezone.utc):%Y%m%d}.pdf"
    return StreamingResponse(iter([pdf]), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


def _build_report_pdf(label, period, snap, movements, reorder, lines, show_cost) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Stock report — {label}", styles["Title"]))
    story.append(Paragraph(
        f"Period: last {'7 days' if period == 'week' else '30 days'} · "
        f"Generated {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC", styles["Normal"]))
    story.append(Spacer(1, 8 * mm))

    sval = f"£{snap['value_sell']:,.2f}"
    summ = [["Stock lines", str(snap["lines"])], ["Total units", f"{snap['units']:,}"],
            ["Stock value", sval], ["Below minimum", str(snap["below_min"])],
            ["Out of stock", str(snap["out"])]]
    if show_cost:
        summ.insert(3, ["Cost value", f"£{snap.get('value_cost', 0):,.2f}"])
    t = Table(summ, colWidths=[60 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Activity this period", styles["Heading3"]))
    if movements:
        mt = [["Movement", "Count", "Units"]] + [
            [m["type"].replace("_", " ").title(), str(m["count"]), str(m["units"])] for m in movements]
    else:
        mt = [["Movement", "Count", "Units"], ["No activity", "0", "0"]]
    mtab = Table(mt, colWidths=[80 * mm, 40 * mm, 40 * mm])
    mtab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(mtab)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Reorder needed ({len(reorder)})", styles["Heading3"]))
    if reorder:
        rt = [["SKU", "Name", "On hand", "Min", "Max", "Order"]] + [
            [i["part_sku"], (i["name"] or "")[:38], str(i["qty"]), str(i["min_qty"]),
             str(i["max_qty"]), str(i["suggested_order"])] for i in reorder[:40]]
        rtab = Table(rt, colWidths=[28 * mm, 70 * mm, 20 * mm, 16 * mm, 16 * mm, 18 * mm])
        rtab.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fffbeb")]),
        ]))
        story.append(rtab)
        if len(reorder) > 40:
            story.append(Paragraph(f"…and {len(reorder) - 40} more (see CSV).", styles["Italic"]))
    else:
        story.append(Paragraph("Everything is at or above its minimum level.", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


__all__ = ["router"]
