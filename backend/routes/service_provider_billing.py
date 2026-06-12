"""
Service Provider self-serve upgrade — Iter 258.

Converts a Service Provider org from its 14-day trial onto a paid monthly
subscription via Stripe Checkout. Mirrors the established pattern in
`routes/crm_modes.py` (raw stripe SDK, payment_transactions ledger,
outbound idempotency, polling status endpoint).

    GET  /api/service-provider/plan                       — plan + trial state
    POST /api/service-provider/upgrade/checkout           — create session
    GET  /api/service-provider/upgrade/status/{session}   — poll + convert

On `paid`, the org is flipped trial → converted (`trial_status=converted`,
`subscription_active=True`) which `trial_lifecycle.compute_trial_state`
reads to drop the banner / lock.
"""
from datetime import datetime, timezone
import logging
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/service-provider", tags=["Service Provider · Billing"])

# Monthly price (GBP). A real recurring Price ID is used when configured;
# otherwise we fall back to an inline subscription price so the upgrade
# works in dev/test without a pre-created Stripe product.
PLAN = {
    "id": "service_desk_pro",
    "name": "Service Desk — Pro",
    "amount_pennies": 9900,          # £99 / month
    "currency": "gbp",
    "interval": "month",
    "blurb": "Unlimited engineers, cases, customers, SLA analytics and the migration import wizard.",
}


async def _provider_org(user: dict) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or org.get("account_type") != "service_provider":
        raise HTTPException(status_code=403, detail="Service Provider account required")
    return org


@router.get("/plan")
async def get_plan(user: dict = Depends(get_current_user)) -> dict:
    """Return the upgrade plan + current subscription/trial state."""
    org = await _provider_org(user)
    converted = bool(org.get("subscription_active")) or org.get("trial_status") == "converted"
    return {
        "plan": {k: PLAN[k] for k in ("id", "name", "amount_pennies", "currency", "interval", "blurb")},
        "price_display": f"£{PLAN['amount_pennies'] // 100}/{PLAN['interval']}",
        "is_converted": converted,
        "trial_ends_at": org.get("trial_ends_at"),
    }


@router.post("/upgrade/checkout")
async def create_upgrade_checkout(
    request: Request,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Owner → Stripe Checkout Session for the Service Desk subscription."""
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    org = await _provider_org(user)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the account owner can upgrade")
    if org.get("subscription_active") or org.get("trial_status") == "converted":
        raise HTTPException(status_code=400, detail="Already subscribed")

    origin_url = (body.get("origin_url") or os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    import stripe
    stripe.api_key = STRIPE_API_KEY

    metadata = {
        "purpose": "service_desk_upgrade",
        "organization_id": org["id"],
        "user_id": user["id"],
        "plan_id": PLAN["id"],
    }
    session_kwargs = {
        "payment_method_types": ["card"],
        "success_url": f"{origin_url}/service-desk/upgrade?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origin_url}/service-desk/upgrade?status=cancelled",
        "customer_email": user.get("email") or None,
        "metadata": metadata,
        "mode": "subscription",
    }
    price_id = os.environ.get("STRIPE_PRICE_SERVICE_DESK")
    if price_id:
        session_kwargs["line_items"] = [{"price": price_id, "quantity": 1}]
    else:
        # Inline recurring price — keeps self-serve working without a
        # pre-created Stripe product (dev/test + first-run prod).
        session_kwargs["line_items"] = [{
            "price_data": {
                "currency": PLAN["currency"],
                "product_data": {"name": PLAN["name"], "description": PLAN["blurb"]},
                "unit_amount": PLAN["amount_pennies"],
                "recurring": {"interval": PLAN["interval"]},
            },
            "quantity": 1,
        }]

    try:
        from utils.stripe_client_idempotency import stripe_idem_key
        session = stripe.checkout.Session.create(
            **session_kwargs,
            idempotency_key=stripe_idem_key("service_desk_upgrade", org["id"], user["id"]),
        )
    except Exception as e:
        logger.exception("Stripe session creation failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "organization_id": org["id"],
        "user_id": user["id"],
        "purpose": "service_desk_upgrade",
        "amount": PLAN["amount_pennies"],
        "currency": PLAN["currency"],
        "payment_status": "pending",
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"url": session.url, "session_id": session.id}


@router.get("/upgrade/status/{session_id}")
async def check_upgrade_status(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Poll Stripe; on `paid`, convert the org trial → active. Idempotent."""
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    import stripe
    stripe.api_key = STRIPE_API_KEY

    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Scope: a user may only poll their own org's transaction.
    if txn.get("organization_id") != user.get("organization_id"):
        raise HTTPException(status_code=403, detail="Not your transaction")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    payment_status = session.get("payment_status", "")
    if payment_status == "paid" and txn.get("payment_status") != "paid":
        now = datetime.now(timezone.utc).isoformat()
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "completed_at": now}},
        )
        await db.organizations.update_one(
            {"id": txn["organization_id"]},
            {"$set": {
                "is_trial": False,
                "trial_status": "converted",
                "subscription_active": True,
                "subscription_plan": PLAN["id"],
                "subscription_started_at": now,
                "subscription_stripe_session": session_id,
                # Iter 258b — kept for the billing portal + renewal lookups.
                "stripe_customer_id": session.get("customer"),
                "stripe_subscription_id": session.get("subscription"),
            }},
        )
        logger.info("Service Desk org %s converted to paid (session %s)", txn["organization_id"], session_id)

    return {
        "status": session.get("status"),
        "payment_status": payment_status,
        "amount_total": session.get("amount_total"),
        "currency": session.get("currency"),
    }


@router.get("/subscription")
async def get_subscription(user: dict = Depends(get_current_user)) -> dict:
    """Subscription status card for the provider dashboard (Iter 258b).

    Trial orgs answer without touching Stripe; converted orgs best-effort
    fetch the renewal date from the live subscription."""
    org = await _provider_org(user)
    converted = bool(org.get("subscription_active")) or org.get("trial_status") == "converted"
    if not converted:
        days_left = None
        ends = org.get("trial_ends_at")
        if ends:
            try:
                end_dt = datetime.fromisoformat(ends)
                days_left = max(0, (end_dt - datetime.now(timezone.utc)).days)
            except ValueError:
                pass
        return {
            "status": "trial",
            "plan_name": "Free trial",
            "price_display": f"£{PLAN['amount_pennies'] // 100}/{PLAN['interval']} after trial",
            "trial_ends_at": ends,
            "days_left": days_left,
        }

    renewal_at = None
    from utils.database import STRIPE_API_KEY
    sub_id = org.get("stripe_subscription_id")
    if STRIPE_API_KEY and sub_id:
        try:
            import stripe
            stripe.api_key = STRIPE_API_KEY
            sub = stripe.Subscription.retrieve(sub_id)
            period_end = sub.get("current_period_end")
            if period_end:
                renewal_at = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
        except Exception as e:  # renewal date is cosmetic — never fail the card
            logger.warning("Stripe subscription lookup failed for %s: %s", org["id"], e)
    return {
        "status": "active",
        "plan_name": PLAN["name"],
        "price_display": f"£{PLAN['amount_pennies'] // 100}/{PLAN['interval']}",
        "started_at": org.get("subscription_started_at"),
        "renewal_at": renewal_at,
        "can_manage": bool(org.get("stripe_customer_id")),
    }


@router.post("/billing-portal")
async def create_billing_portal(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Owner → Stripe customer Billing Portal (manage card / cancel)."""
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    org = await _provider_org(user)
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the account owner can manage billing")
    customer_id = org.get("stripe_customer_id")
    if not (org.get("subscription_active") and customer_id):
        raise HTTPException(status_code=400, detail="No active subscription to manage")

    origin_url = (body.get("origin_url") or os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    import stripe
    stripe.api_key = STRIPE_API_KEY
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{origin_url}/service-desk",
        )
    except Exception as e:
        logger.exception("Stripe billing portal failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"url": portal.url}


__all__ = ["router"]
