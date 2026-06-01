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

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query

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
        item = {
            "part_sku": r.get("part_sku"), "name": p.get("name") or r.get("part_sku"),
            "manufacturer": p.get("manufacturer", ""), "category": p.get("category", ""),
            "qty": qty, "min_qty": minq, "low": low, "zero": zero,
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
            engineers.append({"engineer_id": i, "name": nm or "Unnamed engineer"})
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


# ───────────────────────────── Stock-take ─────────────────────────

@router.post("/stock-take")
async def stock_take(body: dict, user=Depends(get_current_user)):
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


__all__ = ["router"]
