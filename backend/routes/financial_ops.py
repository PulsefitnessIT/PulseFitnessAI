from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime, timezone, timedelta

import uuid
import logging
import os

from utils.database import db
from utils.auth import get_current_user
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")

# Default configuration
DEFAULT_FINANCIAL_CONFIG = {
    "reserve_percentage": 15.0,
    "llm_top_up_amount": 50.00,
    "llm_low_threshold": 10.00,
    "llm_critical_threshold": 5.00,
    "infrastructure_monthly_estimate": 50.00,
    "min_reserve_months": 2,
    "critical_reserve_months": 1,
    "auto_top_up_enabled": True,
    "cost_centres": {
        "gymaxis": {
            "name": "GymAxis AI",
            "type": "direct",
            "stripe_connected_account_id": None,
            "platform_fee_percentage": 0,
        },
        "pulse": {
            "name": "Pulse Fitness",
            "type": "destination",
            "stripe_connected_account_id": None,
            "platform_fee_percentage": 0,
        },
    },
}


def _require_master_admin(user: dict):
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


async def _get_config() -> dict:
    config = await db.financial_config.find_one({}, {"_id": 0})
    if not config:
        config = {**DEFAULT_FINANCIAL_CONFIG, "id": str(uuid.uuid4())}
        await db.financial_config.insert_one(config)
        # Re-fetch to ensure _id is excluded (insert_one mutates the dict)
        config = await db.financial_config.find_one({}, {"_id": 0})
    return config


async def _get_reserve_balance() -> float:
    pipeline = [
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    result = await db.reserve_transactions.aggregate(pipeline).to_list(1)
    return result[0]["total"] if result else 0.0


async def _get_monthly_burn() -> dict:
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"},
        }},
    ]
    results = await db.operational_costs.aggregate(pipeline).to_list(20)
    burn = {}
    for r in results:
        burn[r["_id"]] = abs(r["total"])
    return burn


# ─── Configuration ───

@router.get("/financial-ops/config")
async def get_financial_config(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    return await _get_config()


@router.put("/financial-ops/config")
async def update_financial_config(data: dict, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    allowed = {
        "reserve_percentage", "llm_top_up_amount", "llm_low_threshold",
        "llm_critical_threshold", "infrastructure_monthly_estimate",
        "min_reserve_months", "critical_reserve_months", "auto_top_up_enabled",
    }
    clean = {k: v for k, v in data.items() if k in allowed}
    if not clean:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    clean["updated_by"] = user["id"]
    await db.financial_config.update_one({}, {"$set": clean}, upsert=True)
    return await _get_config()


# ─── Cost Centres ───

@router.put("/financial-ops/cost-centres/{portal_id}")
async def update_cost_centre(portal_id: str, data: dict, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    if portal_id not in ("gymaxis", "pulse"):
        raise HTTPException(status_code=400, detail="Invalid portal ID")

    allowed = {"stripe_connected_account_id", "platform_fee_percentage", "name"}
    clean = {k: v for k, v in data.items() if k in allowed}
    update_fields = {f"cost_centres.{portal_id}.{k}": v for k, v in clean.items()}
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.financial_config.update_one({}, {"$set": update_fields}, upsert=True)
    return await _get_config()


@router.post("/financial-ops/stripe-connect/onboarding-link")
async def create_stripe_onboarding_link(data: dict, user: dict = Depends(get_current_user)):
    """Generate a Stripe Connect onboarding link for Pulse Fitness."""
    _require_master_admin(user)
    # Scaffold: In production, this would call Stripe's Account Links API
    # stripe.AccountLink.create(account=acct_id, type='account_onboarding', ...)
    return {
        "message": "Stripe Connect onboarding link generation",
        "status": "scaffolded",
        "note": "Activate with live Stripe keys. Will generate an onboarding link for the Pulse Fitness connected account.",
        "required": {
            "stripe_live_key": "Required for production",
            "pulse_account_id": "Will be created automatically during onboarding",
        },
    }


# ─── Reserve Fund ───

@router.get("/financial-ops/reserve")
async def get_reserve_status(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    config = await _get_config()
    balance = await _get_reserve_balance()
    burn = await _get_monthly_burn()
    total_monthly_burn = sum(burn.values()) or config.get("infrastructure_monthly_estimate", 50)

    runway_months = round(balance / total_monthly_burn, 1) if total_monthly_burn > 0 else 99

    # Determine health status
    if runway_months >= config.get("min_reserve_months", 2):
        health = "healthy"
    elif runway_months >= config.get("critical_reserve_months", 1):
        health = "warning"
    else:
        health = "critical"

    # Recent transactions
    recent = await db.reserve_transactions.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    return {
        "balance": round(balance, 2),
        "monthly_burn": round(total_monthly_burn, 2),
        "burn_breakdown": burn,
        "runway_months": runway_months,
        "health": health,
        "reserve_percentage": config.get("reserve_percentage", 15),
        "recent_transactions": recent,
    }


@router.post("/financial-ops/reserve/manual-deposit")
async def manual_reserve_deposit(data: dict, user: dict = Depends(get_current_user)):
    """Manually add funds to the operations reserve."""
    _require_master_admin(user)
    amount = data.get("amount", 0)
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    txn = {
        "id": str(uuid.uuid4()),
        "type": "manual_deposit",
        "amount": float(amount),
        "description": data.get("description", "Manual deposit"),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reserve_transactions.insert_one(txn)
    balance = await _get_reserve_balance()
    return {"success": True, "new_balance": round(balance, 2), "transaction_id": txn["id"]}


# ─── Revenue Processing (called when subscription payment succeeds) ───

async def process_payment_revenue(payment_amount: float, portal: str, metadata: dict = None):
    """Process incoming revenue: split between reserve and cost centre."""
    config = await _get_config()
    reserve_pct = config.get("reserve_percentage", 15) / 100
    reserve_amount = round(payment_amount * reserve_pct, 2)
    distributed_amount = round(payment_amount - reserve_amount, 2)

    # Reserve transaction
    await db.reserve_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "type": "revenue_reserve",
        "amount": reserve_amount,
        "description": f"Reserve from {portal} payment (£{payment_amount})",
        "portal": portal,
        "source_amount": payment_amount,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Revenue distribution record
    cost_centre = config.get("cost_centres", {}).get(portal, {})
    await db.revenue_distributions.insert_one({
        "id": str(uuid.uuid4()),
        "portal": portal,
        "cost_centre": cost_centre.get("name", portal),
        "payment_amount": payment_amount,
        "reserve_held": reserve_amount,
        "distributed_amount": distributed_amount,
        "stripe_connected_account": cost_centre.get("stripe_connected_account_id"),
        "platform_fee_pct": cost_centre.get("platform_fee_percentage", 0),
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[FINANCIAL] Payment £{payment_amount} from {portal}: "
                f"Reserve £{reserve_amount} ({reserve_pct*100}%), "
                f"Distributed £{distributed_amount}")

    # Check if auto-top-up needed after reserve update
    if config.get("auto_top_up_enabled"):
        await _check_auto_top_up(config)

    return {
        "reserve_amount": reserve_amount,
        "distributed_amount": distributed_amount,
    }


# ─── LLM Auto-Top-Up ───

async def _check_auto_top_up(config: dict):
    """Check LLM balance and trigger auto-top-up if needed."""
    reserve_balance = await _get_reserve_balance()
    top_up_amount = config.get("llm_top_up_amount", 50)

    if reserve_balance < top_up_amount:
        logger.warning("[FINANCIAL] Reserve insufficient for LLM auto-top-up")
        await _create_alert("warning", "Reserve balance too low for automatic LLM top-up",
                          f"Reserve: £{reserve_balance:.2f}, Top-up amount: £{top_up_amount}")
        return

    # Log the auto-top-up intent
    await db.llm_top_up_log.insert_one({
        "id": str(uuid.uuid4()),
        "amount": top_up_amount,
        "reserve_balance_before": reserve_balance,
        "status": "pending",
        "triggered_by": "auto",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[FINANCIAL] LLM auto-top-up triggered: £{top_up_amount}")


@router.post("/financial-ops/llm-top-up")
async def trigger_llm_top_up(data: dict, user: dict = Depends(get_current_user)):
    """Manually trigger LLM credit top-up via Stripe."""
    _require_master_admin(user)
    config = await _get_config()
    amount = data.get("amount", config.get("llm_top_up_amount", 50))
    reserve_balance = await _get_reserve_balance()

    if reserve_balance < amount:
        raise HTTPException(status_code=400,
                          detail=f"Insufficient reserve balance (£{reserve_balance:.2f}) for £{amount} top-up")

    # Debit reserve
    await db.reserve_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "type": "llm_top_up",
        "amount": -float(amount),
        "description": f"LLM credit top-up (£{amount})",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Record in top-up log
    top_up_id = str(uuid.uuid4())
    await db.llm_top_up_log.insert_one({
        "id": top_up_id,
        "amount": amount,
        "reserve_balance_before": reserve_balance,
        "reserve_balance_after": reserve_balance - amount,
        "status": "completed",
        "triggered_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Record operational cost
    await db.operational_costs.insert_one({
        "id": str(uuid.uuid4()),
        "category": "llm_credits",
        "amount": -float(amount),
        "description": "LLM credit top-up",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    new_balance = await _get_reserve_balance()
    return {
        "success": True,
        "top_up_amount": amount,
        "new_reserve_balance": round(new_balance, 2),
        "top_up_id": top_up_id,
    }


# ─── Alerts ───

async def _create_alert(severity: str, title: str, message: str):
    await db.financial_alerts.insert_one({
        "id": str(uuid.uuid4()),
        "severity": severity,
        "title": title,
        "message": message,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/financial-ops/alerts")
async def get_financial_alerts(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    alerts = await db.financial_alerts.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"alerts": alerts}


@router.put("/financial-ops/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    await db.financial_alerts.update_one({"id": alert_id}, {"$set": {"read": True}})
    return {"success": True}


# ─── Revenue Analytics ───

@router.get("/financial-ops/revenue")
async def get_revenue_analytics(user: dict = Depends(get_current_user)):
    _require_master_admin(user)

    # Revenue distributions
    distributions = await db.revenue_distributions.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    # Aggregate by portal
    by_portal = {}
    total_revenue = 0
    total_reserved = 0
    for d in distributions:
        portal = d.get("portal", "unknown")
        by_portal.setdefault(portal, {"revenue": 0, "reserved": 0, "distributed": 0, "count": 0})
        by_portal[portal]["revenue"] += d.get("payment_amount", 0)
        by_portal[portal]["reserved"] += d.get("reserve_held", 0)
        by_portal[portal]["distributed"] += d.get("distributed_amount", 0)
        by_portal[portal]["count"] += 1
        total_revenue += d.get("payment_amount", 0)
        total_reserved += d.get("reserve_held", 0)

    # LLM top-up history
    top_ups = await db.llm_top_up_log.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    # Payment transactions
    payments = await db.payment_transactions.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    return {
        "total_revenue": round(total_revenue, 2),
        "total_reserved": round(total_reserved, 2),
        "total_distributed": round(total_revenue - total_reserved, 2),
        "by_portal": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in by_portal.items()},
        "recent_distributions": distributions[:20],
        "llm_top_ups": top_ups,
        "recent_payments": payments,
    }


CHECKOUT_PACKAGES = {
    "lite_monthly": {"amount": 49.00, "currency": "gbp", "name": "Lite Monthly"},
    "pro_monthly": {"amount": 99.00, "currency": "gbp", "name": "Pro Monthly"},
    "pro_annual": {"amount": 990.00, "currency": "gbp", "name": "Pro Annual"},
    "enterprise_monthly": {"amount": 199.00, "currency": "gbp", "name": "Enterprise Monthly"},
    "llm_top_up_50": {"amount": 50.00, "currency": "gbp", "name": "LLM Credit Top-Up (£50)"},
    "llm_top_up_100": {"amount": 100.00, "currency": "gbp", "name": "LLM Credit Top-Up (£100)"},
}


async def _record_payment_transaction(session, user: dict, package: dict, package_id: str, portal: str) -> None:
    """Record a pending payment transaction in the database."""
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.session_id,
        "user_id": user["id"],
        "email": user.get("email", ""),
        "portal": portal,
        "package_id": package_id,
        "package_name": package["name"],
        "amount": package["amount"],
        "currency": package["currency"],
        "payment_status": "pending",
        "metadata": {"user_id": user["id"], "portal": portal, "package_id": package_id, "organization_id": user.get("organization_id", "")},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/financial-ops/checkout")
async def create_checkout_session(request: Request, data: dict, user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for subscription or top-up payment."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    origin_url = data.get("origin_url", "")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    portal = data.get("portal", "gymaxis")
    package_id = data.get("package_id", "standard")

    package = CHECKOUT_PACKAGES.get(package_id)
    if not package:
        raise HTTPException(status_code=400, detail=f"Invalid package: {package_id}")

    host_url = str(request.base_url).rstrip("/")
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=f"{host_url}/api/webhook/stripe")

    checkout_request = CheckoutSessionRequest(
        amount=package["amount"],
        currency=package["currency"],
        success_url=f"{origin_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin_url}/payment-cancelled",
        metadata={"user_id": user["id"], "portal": portal, "package_id": package_id, "organization_id": user.get("organization_id", "")},
    )

    session = await stripe_checkout.create_checkout_session(checkout_request)
    await _record_payment_transaction(session, user, package, package_id, portal)

    return {"url": session.url, "session_id": session.session_id}


@router.get("/financial-ops/checkout/status/{session_id}")
async def get_checkout_status(session_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Check payment status and process if successful."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    status = await stripe_checkout.get_checkout_status(session_id)

    # Update transaction
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if txn and txn.get("payment_status") != "paid" and status.payment_status == "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "payment_status": "paid",
                "status": status.status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        # Process revenue split
        portal = txn.get("portal", "gymaxis")
        await process_payment_revenue(txn["amount"], portal, txn.get("metadata"))

        # If LLM top-up, process it
        if txn.get("package_id", "").startswith("llm_top_up"):
            await db.reserve_transactions.insert_one({
                "id": str(uuid.uuid4()),
                "type": "llm_stripe_top_up",
                "amount": txn["amount"],
                "description": "LLM credit purchase via Stripe",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    elif txn and status.status == "expired":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "expired", "status": "expired"}}
        )

    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency,
    }


# ─── Stripe Webhook ───

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    try:
        host_url = str(request.base_url).rstrip("/")
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
        event = await stripe_checkout.handle_webhook(body, signature)

        if event.payment_status == "paid":
            txn = await db.payment_transactions.find_one(
                {"session_id": event.session_id}, {"_id": 0}
            )
            if txn and txn.get("payment_status") != "paid":
                await db.payment_transactions.update_one(
                    {"session_id": event.session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "status": "complete",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                portal = txn.get("portal", "gymaxis")
                await process_payment_revenue(txn["amount"], portal, txn.get("metadata"))

        logger.info(f"[WEBHOOK] Stripe event: {event.event_type} for session {event.session_id}")
        return {"received": True}
    except Exception as e:
        logger.error(f"[WEBHOOK] Stripe webhook error: {e}")
        return {"received": True}


# ─── Dashboard Summary ───

@router.get("/financial-ops/dashboard")
async def get_financial_dashboard(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    config = await _get_config()
    reserve_balance = await _get_reserve_balance()
    burn = await _get_monthly_burn()
    total_burn = sum(burn.values()) or config.get("infrastructure_monthly_estimate", 50)
    runway = round(reserve_balance / total_burn, 1) if total_burn > 0 else 99

    # Unread alerts count
    unread_alerts = await db.financial_alerts.count_documents({"read": False})

    # Total revenue this month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0).isoformat()
    monthly_pipeline = [
        {"$match": {"created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$payment_amount"}}},
    ]
    monthly_rev = await db.revenue_distributions.aggregate(monthly_pipeline).to_list(1)
    monthly_revenue = monthly_rev[0]["total"] if monthly_rev else 0

    # Recent top-ups
    recent_top_ups = await db.llm_top_up_log.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(5)

    return {
        "reserve_balance": round(reserve_balance, 2),
        "monthly_burn": round(total_burn, 2),
        "burn_breakdown": burn,
        "runway_months": runway,
        "health": "healthy" if runway >= config.get("min_reserve_months", 2) else ("warning" if runway >= config.get("critical_reserve_months", 1) else "critical"),
        "config": config,
        "monthly_revenue": round(monthly_revenue, 2),
        "unread_alerts": unread_alerts,
        "recent_top_ups": recent_top_ups,
    }
