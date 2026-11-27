"""Release E — per-product billing self-service for owners, and commercial reporting for Pulse."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db, STRIPE_API_KEY
from utils import commercial_lifecycle as CL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["commercial-lifecycle"])
NAMES = {"operations": "Pulse Fitness PRO (Operations)", "memberships": "Memberships", "marketing": "Marketing", "crm": "CRM"}


def _prices() -> dict:
    from routes.payments import PRICING_CATALOG
    return {m["id"]: m for m in PRICING_CATALOG["modules"]}


async def _owner_org(user: dict) -> dict:
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the account owner can change paid products")
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


def _check(module: str) -> None:
    if module not in CL.PAID_MODULES:
        raise HTTPException(404, "Unknown product")


@router.get("/account/billing/modules")
async def list_products(user: dict = Depends(get_current_user)):
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    p = _prices()
    return {"account_type": org.get("account_type"), "is_owner": user.get("role") == "owner",
            "products": [{**CL.module_state(org, m), "name": NAMES[m], "monthly_price": p.get(m, {}).get("monthly"),
                          "annual_price": p.get(m, {}).get("annual")} for m in CL.PAID_MODULES]}


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


@router.post("/account/billing/modules/{module}/cancel")
async def cancel_product(module: str, body: CancelIn, user: dict = Depends(get_current_user)):
    _check(module)
    org = await _owner_org(user)
    st = CL.module_state(org, module)
    if st["status"] == "cancelling":
        raise HTTPException(409, "Cancellation is already scheduled")
    if st["status"] != "active":
        raise HTTPException(409, "This product isn't an active paid subscription")
    sub_id = ((org.get("module_subscriptions") or {}).get(module) or {}).get("stripe_subscription_id")
    if not sub_id or not STRIPE_API_KEY:
        raise HTTPException(409, "This product is billed by invoice. Contact Pulse Fitness to cancel it.")
    try:
        sub = stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
    except Exception as exc:
        logger.warning("[commercial] Stripe cancel failed for %s: %s", sub_id, exc)
        raise HTTPException(502, "Stripe couldn't schedule the cancellation. Nothing was changed; try again.") from exc
    end = getattr(sub, "current_period_end", None)
    end_iso = datetime.fromtimestamp(int(end), tz=timezone.utc).isoformat() if end else None
    await db.organizations.update_one({"id": org["id"]}, {"$set": {
        f"module_subscriptions.{module}.cancel_at_period_end": True,
        f"module_subscriptions.{module}.current_period_end": end_iso,
        f"module_subscriptions.{module}.cancel_reason": body.reason.strip()}})
    await CL.record_event(org["id"], "cancellation_scheduled", module, actor_id=user["id"], reason=body.reason.strip(),
                          effective_at=end_iso)
    return {"ok": True, "effective_at": end_iso,
            "message": f"{NAMES[module]} stays on until the end of the billing period. Your data is kept."}


@router.post("/account/billing/modules/{module}/reactivate")
async def reactivate_product(module: str, user: dict = Depends(get_current_user)):
    _check(module)
    org = await _owner_org(user)
    st = CL.module_state(org, module)
    if st["status"] == "ended":
        raise HTTPException(409, "This subscription has ended. Subscribe again to switch it back on; your data is still here.")
    if st["status"] != "cancelling":
        raise HTTPException(409, "There is no scheduled cancellation to undo")
    sub_id = org["module_subscriptions"][module]["stripe_subscription_id"]
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=False)
    except Exception as exc:
        raise HTTPException(502, "Stripe couldn't undo the cancellation. Nothing was changed; try again.") from exc
    await db.organizations.update_one({"id": org["id"]}, {"$set": {f"module_subscriptions.{module}.cancel_at_period_end": False},
                                                         "$unset": {f"module_subscriptions.{module}.cancel_reason": ""}})
    await CL.record_event(org["id"], "cancellation_withdrawn", module, actor_id=user["id"])
    return {"ok": True, "message": f"{NAMES[module]} will continue."}


# ---------------------------------------------------------------- Pulse commercial reporting
async def _require_pulse(user: dict) -> None:
    from routes.customer_account_import import _is_full_admin
    if not _is_full_admin(user):
        raise HTTPException(403, "Pulse Fitness administrator access required")


@router.get("/master-admin/commercial/summary")
async def commercial_summary(user: dict = Depends(get_current_user)):
    await _require_pulse(user)
    prices = _prices()
    base = {"is_operator_company": {"$ne": True}}
    products = []
    mrr_total = 0.0
    for m in CL.PAID_MODULES:
        paid = {**base, f"modules.{m}.source": "paid", f"modules.{m}.enabled": True}
        active = await db.organizations.count_documents(paid)
        annual = await db.organizations.count_documents({**paid, f"module_subscriptions.{m}.billing_cycle": "annual"})
        cancelling = await db.organizations.count_documents({**paid, f"module_subscriptions.{m}.cancel_at_period_end": True})
        pr = prices.get(m, {})
        mrr = (active - annual) * (pr.get("monthly") or 0) + annual * (pr.get("annual") or 0) / 12
        mrr_total += mrr
        products.append({"module": m, "name": NAMES[m], "paying": active, "annual": annual, "cancelling": cancelling,
                         "trials": await db.organizations.count_documents({**base, f"modules.{m}.source": "trial",
                                                                           f"module_trials.{m}.expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}),
                         "included_by_pulse": await db.organizations.count_documents({**base, f"modules.{m}.source": "admin",
                                                                                     f"modules.{m}.enabled": True}),
                         "ended": await db.organizations.count_documents({**base, f"module_subscriptions.{m}.status": "ended"}),
                         "mrr": round(mrr, 2)})
    since30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    ev = {r["_id"]: r["n"] async for r in db.commercial_events.aggregate([
        {"$match": {"at": {"$gte": since30}}}, {"$group": {"_id": "$event", "n": {"$sum": 1}}}])}
    recent = await db.commercial_events.find({}, {"_id": 0}).sort("at", -1).limit(30).to_list(30)
    names = {o["id"]: o.get("name") async for o in db.organizations.find(
        {"id": {"$in": list({r["organization_id"] for r in recent})}}, {"_id": 0, "id": 1, "name": 1})}
    for r in recent:
        r["organization_name"] = names.get(r["organization_id"])
    accounts = {
        "lite": await db.organizations.count_documents({**base, "account_type": "lite"}),
        "pro": await db.organizations.count_documents({**base, "account_type": "pulse_pro"}),
        "awaiting_activation": await db.organizations.count_documents({**base, "onboarding_status": "pending_activation"}),
        "owner_invited": len(await db.secure_invitations.distinct("organization_id", {"kind": "owner_activation", "status": "pending"})),
        "activated_by_invitation": await db.organizations.count_documents({**base, "activated_via_invitation": {"$exists": True}}),
    }
    return {"currency": "GBP", "mrr": round(mrr_total, 2), "products": products, "accounts": accounts,
            "last_30_days": {"upgrades_lite_to_pro": ev.get("upgraded_lite_to_pro", 0), "purchases": ev.get("purchased", 0),
                             "reactivations": ev.get("reactivated", 0), "cancellations_scheduled": ev.get("cancellation_scheduled", 0),
                             "cancellations_withdrawn": ev.get("cancellation_withdrawn", 0), "ended": ev.get("ended", 0)},
            "recent_events": recent,
            "note": "MRR uses list prices for paid products bought through Stripe. Products included by Pulse and invoiced accounts are counted separately, not in MRR."}
