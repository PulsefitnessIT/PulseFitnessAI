"""CRM mode entitlements (Iter 215c).

Two modes:
  • leisure  — bundled with Memberships; auto-enabled when memberships
               module is on. Targets gyms / leisure centres selling
               memberships.
  • business — paid add-on for B2B sales (corporate wellness, schools,
               supplier ops). Granted by Master Admin or via Stripe
               self-serve upgrade.
"""
from datetime import datetime, timezone
import os
import logging

from fastapi import APIRouter, HTTPException, Depends, Body, Request

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import crm_modes, has_crm_access

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


async def _get_org(user: dict):
    org_id = user.get("organization_id")
    if not org_id:
        return None
    return await db.organizations.find_one({"id": org_id}, {"_id": 0})


@router.get("/me/crm-modes")
async def get_my_crm_modes(user: dict = Depends(get_current_user)):
    """Return the CRM modes currently available to the signed-in user."""
    org = await _get_org(user)
    modes = crm_modes(user, org)
    return {
        "modes": modes,
        "any_enabled": any(modes.values()),
        "memberships_enabled": bool(((org or {}).get("modules") or {}).get("memberships", {}).get("enabled")),
        "account_type": (org or {}).get("account_type") or user.get("account_type"),
    }


@router.put("/master-admin/organizations/{org_id}/crm-business")
async def set_business_crm(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Master Admin: grant or revoke Business CRM for an organization."""
    _require_master_admin(user)
    enabled = bool(body.get("enabled", False))
    note = (body.get("note") or "").strip()[:200]

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "modules": 1, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    modules = dict(org.get("modules") or {})
    crm = dict(modules.get("crm") or {})
    crm["business_enabled"] = enabled
    # If business is being granted and CRM module isn't enabled at all,
    # turn it on (leisure may also be on via memberships, but business
    # should always work even if memberships isn't).
    if enabled and not crm.get("enabled"):
        crm["enabled"] = True
        crm.setdefault("tier", "pro")
    crm["business_granted_by"] = user.get("email") if enabled else None
    crm["business_granted_at"] = datetime.now(timezone.utc).isoformat() if enabled else None
    crm["business_grant_note"] = note or None
    modules["crm"] = crm

    await db.organizations.update_one({"id": org_id}, {"$set": {"modules": modules}})
    return {"success": True, "business_enabled": enabled}


# ─── Self-serve Stripe upgrade ──────────────────────────────────

@router.post("/me/crm-business/checkout")
async def create_business_crm_checkout(
    request: Request,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Operator → Stripe Checkout Session for the Business CRM upgrade.

    Currency: GBP. Recurring monthly subscription. Price comes from
    `STRIPE_PRICE_CRM_BUSINESS` env var; if not set, falls back to a
    one-time £49 charge so the upgrade still works in dev/test.
    """
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    org = await _get_org(user)
    if not org:
        raise HTTPException(status_code=400, detail="No organization")

    origin_url = (body.get("origin_url") or os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    import stripe
    stripe.api_key = STRIPE_API_KEY

    price_id = os.environ.get("STRIPE_PRICE_CRM_BUSINESS")

    metadata = {
        "purpose": "crm_business_upgrade",
        "organization_id": org["id"],
        "user_id": user["id"],
    }

    session_kwargs = {
        "payment_method_types": ["card"],
        "success_url": f"{origin_url}/crm?upgrade=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origin_url}/crm?upgrade=cancelled",
        "customer_email": user.get("email") or None,
        "metadata": metadata,
    }
    if price_id:
        session_kwargs.update({
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
        })
    else:
        # Dev/test fallback — fixed-price one-shot charge.
        session_kwargs.update({
            "mode": "payment",
            "line_items": [{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": "GymAxis Business CRM",
                        "description": "B2B sales pipeline, contracts and supplier ops.",
                    },
                    "unit_amount": 4900,
                },
                "quantity": 1,
            }],
        })

    try:
        session = stripe.checkout.Session.create(**session_kwargs)
    except Exception as e:
        logger.exception("Stripe session creation failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    # Record the transaction so the webhook can flip the flag.
    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "organization_id": org["id"],
        "user_id": user["id"],
        "purpose": "crm_business_upgrade",
        "amount": 4900,
        "currency": "gbp",
        "payment_status": "pending",
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"url": session.url, "session_id": session.id}


@router.get("/me/crm-business/checkout/{session_id}/status")
async def check_business_crm_checkout(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Poll Stripe for the upgrade status. On `paid`, flip
    `modules.crm.business_enabled = True` for the org and record the
    grant. Idempotent."""
    from utils.database import STRIPE_API_KEY
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    import stripe
    stripe.api_key = STRIPE_API_KEY

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    payment_status = session.get("payment_status", "")
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if payment_status == "paid" and txn.get("payment_status") != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "completed_at": datetime.now(timezone.utc).isoformat()}},
        )
        # Flip the entitlement.
        org_id = txn.get("organization_id")
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "modules": 1})
        modules = dict((org or {}).get("modules") or {})
        crm = dict(modules.get("crm") or {})
        crm["business_enabled"] = True
        crm.setdefault("enabled", True)
        crm.setdefault("tier", "pro")
        crm["business_granted_by"] = "stripe_self_serve"
        crm["business_granted_at"] = datetime.now(timezone.utc).isoformat()
        crm["business_stripe_session"] = session_id
        modules["crm"] = crm
        await db.organizations.update_one({"id": org_id}, {"$set": {"modules": modules}})

    return {
        "status": session.get("status"),
        "payment_status": payment_status,
        "amount_total": session.get("amount_total"),
        "currency": session.get("currency"),
    }
