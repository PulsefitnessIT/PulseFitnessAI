"""CRM · Master Price List — price-change & approval workflow (Iter 220 P1).

Bulk + single price changes with live preview, an optional per-org
approval gate (owners/admins approve; managers request), scheduled
effective dates (applied by a background sweep) and a full audit + per
product price history.

Settings (`crm_price_list_settings`, one doc per org):
  { organization_id, require_approval: bool, margin_threshold_pct }

Changes (`crm_price_changes`):
  { id, organization_id, kind, field, mode, amount, filter, product_id,
    reason, status, effective_date, affected_count, preview[],
    requested_by(_name), requested_at, approved_by(_name), approved_at,
    decision_comment, applied_at }

Status machine: pending → approved → applied | rejected | cancelled
                scheduled → applied (by the sweep) | cancelled
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body
from pymongo import UpdateOne

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit
from routes.crm_products import _is_admin, _calc_markup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/price-list", tags=["CRM Price Changes"])

PRICE_FIELDS = {"cost_price", "sell_price"}
MODES = {"pct", "fixed", "set", "margin"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _is_approver(user: dict) -> bool:
    return (
        bool(user.get("is_master_admin"))
        or bool(user.get("is_pulse_admin"))
        or (user.get("role") or "").lower() in ("admin", "owner")
    )


# ── Settings ───────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(user=Depends(get_crm_user)) -> dict:
    s = await db.crm_price_list_settings.find_one(_of(user), {"_id": 0}) or {}
    return {
        "require_approval": bool(s.get("require_approval", False)),
        "margin_threshold_pct": s.get("margin_threshold_pct", 10),
        "is_approver": _is_approver(user),
        "can_edit": _is_admin(user),
    }


@router.put("/settings")
async def update_settings(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can change approval settings")
    upd = {}
    if "require_approval" in body:
        upd["require_approval"] = bool(body["require_approval"])
    if "margin_threshold_pct" in body:
        try:
            upd["margin_threshold_pct"] = max(0, float(body["margin_threshold_pct"]))
        except (TypeError, ValueError):
            raise HTTPException(422, "margin_threshold_pct must be numeric")
    upd["updated_at"] = _now()
    upd["updated_by"] = user.get("id", "")
    await db.crm_price_list_settings.update_one(_of(user), {"$set": {**_of(user), **upd}}, upsert=True)
    await log_audit(user, "price_list_settings", user.get("organization_id"), "updated", upd)
    return await get_settings(user)


# ── Compute new prices ─────────────────────────────────────────────


def _new_value(old: float, cost: float, mode: str, amount: float, field: str) -> float | None:
    """Return the new value for a product, or None to skip it."""
    old = float(old or 0)
    if mode == "pct":
        return round(old * (1 + amount / 100.0), 2)
    if mode == "fixed":
        return round(old + amount, 2)
    if mode == "set":
        return round(amount, 2)
    if mode == "margin":
        # only meaningful for sell_price given a cost; margin on sell.
        if field != "sell_price" or not cost or cost <= 0 or amount >= 100:
            return None
        return round(cost / (1 - amount / 100.0), 2)
    return None


async def _query_for(filter_spec: dict, product_id: str | None, user: dict) -> dict:
    q = {**_of(user), "active": True}
    if product_id:
        q["id"] = product_id
        return q
    f = filter_spec or {}
    if f.get("category"):
        q["category"] = f["category"]
    if f.get("supplier"):
        q["supplier_name"] = f["supplier"]
    return q


async def _compute_preview(change: dict, user: dict, *, full: bool = False) -> dict:
    field = change["field"]
    mode = change["mode"]
    amount = float(change.get("amount") or 0)
    q = await _query_for(change.get("filter"), change.get("product_id"), user)
    cur = db.crm_products.find(q, {"_id": 0, "id": 1, "sku": 1, "name": 1, "cost_price": 1, "sell_price": 1})
    rows = []
    affected = 0
    below_margin = neg = cost_gt_sell = 0
    threshold = float((await get_settings(user)).get("margin_threshold_pct", 10))
    async for p in cur:
        old = float(p.get(field) or 0)
        cost = float(p.get("cost_price") or 0)
        nv = _new_value(old, cost, mode, amount, field)
        if nv is None or round(nv, 2) == round(old, 2):
            continue
        affected += 1
        new_cost = nv if field == "cost_price" else cost
        new_sell = nv if field == "sell_price" else float(p.get("sell_price") or 0)
        if nv < 0:
            neg += 1
        if new_cost and new_sell and new_cost > new_sell:
            cost_gt_sell += 1
        margin = _calc_markup(new_cost, new_sell)
        if new_sell and margin < threshold:
            below_margin += 1
        if full or len(rows) < 50:
            rows.append({"product_id": p["id"], "sku": p.get("sku"), "name": p.get("name"),
                         "old": round(old, 2), "new": nv})
    return {
        "affected_count": affected, "preview": rows,
        "warnings": {"below_margin": below_margin, "negative": neg, "cost_gt_sell": cost_gt_sell, "margin_threshold": threshold},
    }


@router.post("/price-changes/preview")
async def preview_change(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "Only price-list editors can change prices")
    _validate_change(body)
    res = await _compute_preview(body, user)
    return {"preview": res}


def _validate_change(body: dict) -> None:
    if body.get("field") not in PRICE_FIELDS:
        raise HTTPException(422, "field must be cost_price or sell_price")
    if body.get("mode") not in MODES:
        raise HTTPException(422, "mode must be pct, fixed, set or margin")
    try:
        float(body.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(422, "amount must be numeric")


# ── Apply ──────────────────────────────────────────────────────────


async def _apply_change(change: dict, actor_name: str) -> int:
    """Apply a price change to the catalogue; append per-product history."""
    user_org = {"organization_id": change["organization_id"]}
    field = change["field"]
    mode = change["mode"]
    amount = float(change.get("amount") or 0)
    q = {**user_org, "active": True}
    if change.get("product_id"):
        q["id"] = change["product_id"]
    else:
        f = change.get("filter") or {}
        if f.get("category"):
            q["category"] = f["category"]
        if f.get("supplier"):
            q["supplier_name"] = f["supplier"]
    cur = db.crm_products.find(q, {"_id": 0, "id": 1, "cost_price": 1, "sell_price": 1})
    ops: list[UpdateOne] = []
    applied = 0
    async for p in cur:
        old = float(p.get(field) or 0)
        cost = float(p.get("cost_price") or 0)
        nv = _new_value(old, cost, mode, amount, field)
        if nv is None or round(nv, 2) == round(old, 2):
            continue
        new_cost = nv if field == "cost_price" else cost
        new_sell = nv if field == "sell_price" else float(p.get("sell_price") or 0)
        ops.append(UpdateOne({"id": p["id"]}, {
            "$set": {field: nv, "markup_percent": _calc_markup(new_cost, new_sell), "updated_at": _now()},
            "$push": {"price_history": {"$each": [{
                "field": field, "old": round(old, 2), "new": nv,
                "reason": change.get("reason", ""), "change_id": change["id"],
                "by": actor_name, "at": _now(),
            }], "$slice": -50}},
        }))
        applied += 1
        if len(ops) >= 500:
            await db.crm_products.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await db.crm_products.bulk_write(ops, ordered=False)
    return applied


@router.post("/price-changes")
async def create_change(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "Only price-list editors can change prices")
    _validate_change(body)
    settings = await get_settings(user)
    eff = (body.get("effective_date") or "").strip()
    prev = await _compute_preview(body, user)
    change = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "kind": "single" if body.get("product_id") else "bulk",
        "field": body["field"], "mode": body["mode"], "amount": float(body["amount"]),
        "filter": body.get("filter") or {}, "product_id": body.get("product_id"),
        "reason": (body.get("reason") or "").strip(),
        "effective_date": eff or None,
        "affected_count": prev["affected_count"],
        "preview": prev["preview"][:50],
        "warnings": prev["warnings"],
        "requested_by": user.get("id", ""), "requested_by_name": user.get("full_name", ""),
        "requested_at": _now(),
        "approved_by": None, "approved_by_name": None, "approved_at": None,
        "decision_comment": None, "applied_at": None,
    }

    # Decide status.
    is_future = bool(eff and eff > _now())
    if is_future:
        change["status"] = "scheduled"
    elif settings["require_approval"] and not _is_approver(user):
        change["status"] = "pending"
    else:
        change["status"] = "applied"
        applied = await _apply_change(change, user.get("full_name", ""))
        change["affected_count"] = applied
        change["applied_at"] = _now()
        change["approved_by"] = user.get("id", "")
        change["approved_by_name"] = user.get("full_name", "")

    await db.crm_price_changes.insert_one(dict(change))
    await log_audit(user, "price_change", change["id"], change["status"],
                    {"field": change["field"], "mode": change["mode"], "amount": change["amount"], "affected": change["affected_count"]})
    change.pop("_id", None)
    return {"change": change}


@router.get("/price-changes")
async def list_changes(status: str = "", user=Depends(get_crm_user)) -> dict:
    q = {**_of(user)}
    if status:
        q["status"] = status
    cur = db.crm_price_changes.find(q, {"_id": 0}).sort("requested_at", -1).limit(100)
    changes = await cur.to_list(100)
    pending = await db.crm_price_changes.count_documents({**_of(user), "status": "pending"})
    return {"changes": changes, "pending_count": pending, "is_approver": _is_approver(user)}


@router.post("/price-changes/{change_id}/approve")
async def approve_change(change_id: str, body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can approve price changes")
    ch = await db.crm_price_changes.find_one({"id": change_id, **_of(user)}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Change not found")
    if ch["status"] != "pending":
        raise HTTPException(409, f"Change is {ch['status']}, not pending")
    eff = ch.get("effective_date")
    upd = {"approved_by": user.get("id", ""), "approved_by_name": user.get("full_name", ""),
           "approved_at": _now(), "decision_comment": (body.get("comment") or "").strip()}
    if eff and eff > _now():
        upd["status"] = "scheduled"
    else:
        applied = await _apply_change({**ch, **upd}, user.get("full_name", ""))
        upd["status"] = "applied"
        upd["applied_at"] = _now()
        upd["affected_count"] = applied
    await db.crm_price_changes.update_one({"id": change_id, **_of(user)}, {"$set": upd})
    await log_audit(user, "price_change", change_id, "approved", {"status": upd["status"]})
    return {"change": {**ch, **upd}}


@router.post("/price-changes/{change_id}/reject")
async def reject_change(change_id: str, body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can reject price changes")
    ch = await db.crm_price_changes.find_one({"id": change_id, **_of(user)}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Change not found")
    if ch["status"] not in ("pending", "scheduled"):
        raise HTTPException(409, f"Change is {ch['status']}")
    upd = {"status": "rejected", "approved_by": user.get("id", ""), "approved_by_name": user.get("full_name", ""),
           "approved_at": _now(), "decision_comment": (body.get("comment") or "").strip()}
    await db.crm_price_changes.update_one({"id": change_id, **_of(user)}, {"$set": upd})
    await log_audit(user, "price_change", change_id, "rejected")
    return {"change": {**ch, **upd}}


@router.post("/price-changes/{change_id}/cancel")
async def cancel_change(change_id: str, user=Depends(get_crm_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "Not allowed")
    ch = await db.crm_price_changes.find_one({"id": change_id, **_of(user)}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Change not found")
    if ch["status"] not in ("pending", "scheduled"):
        raise HTTPException(409, f"Cannot cancel a {ch['status']} change")
    # requesters can cancel their own; approvers can cancel any
    if ch["requested_by"] != user.get("id") and not _is_approver(user):
        raise HTTPException(403, "You can only cancel your own requests")
    await db.crm_price_changes.update_one({"id": change_id, **_of(user)}, {"$set": {"status": "cancelled", "cancelled_at": _now()}})
    await log_audit(user, "price_change", change_id, "cancelled")
    return {"cancelled": True}


# ── Scheduled sweep ────────────────────────────────────────────────


async def run_scheduled_price_changes_loop(interval_minutes: int = 30) -> None:
    import asyncio
    logger.info("[price-changes] scheduled sweep loop started (%dm)", interval_minutes)
    while True:
        try:
            await apply_due_scheduled_changes()
        except Exception:
            logger.exception("[price-changes] scheduled sweep error")
        await asyncio.sleep(interval_minutes * 60)


async def apply_due_scheduled_changes() -> dict:
    now = _now()
    due = await db.crm_price_changes.find({"status": "scheduled", "effective_date": {"$lte": now}}, {"_id": 0}).to_list(500)
    applied = 0
    for ch in due:
        try:
            n = await _apply_change(ch, ch.get("approved_by_name") or ch.get("requested_by_name") or "scheduler")
            await db.crm_price_changes.update_one({"id": ch["id"]}, {"$set": {"status": "applied", "applied_at": _now(), "affected_count": n}})
            applied += 1
        except Exception:
            logger.exception("[price-changes] failed applying scheduled change %s", ch.get("id"))
    if applied:
        logger.info("[price-changes] applied %d scheduled change(s)", applied)
    return {"applied": applied, "checked": len(due)}


async def ensure_price_change_indexes() -> None:
    try:
        await db.crm_price_changes.create_index([("organization_id", 1), ("status", 1), ("requested_at", -1)])
        await db.crm_price_changes.create_index([("status", 1), ("effective_date", 1)])
        await db.crm_price_list_settings.create_index([("organization_id", 1)], unique=True)
    except Exception:
        logger.exception("ensure_price_change_indexes failed (non-fatal)")
