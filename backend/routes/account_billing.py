"""Self-serve subscription management (iter 215c1).

Operator-side endpoints to cancel, reactivate, or downgrade a subscription
without raising a support ticket. Required for UK consumer/business law
compliance — customers must have a clear self-service exit path.

Cancellation policy: we cancel the Stripe subscription at period end so
customers retain access for what they've already paid for. The org is
flagged `pending_cancellation=true` and a `cancellation_effective_at`
timestamp is recorded. Operators can `reactivate` at any time before the
effective date.

Downgrade policy: switching to a cheaper plan is queued for the next
billing period (Stripe proration disabled to avoid mid-cycle credits).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db, STRIPE_API_KEY

logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_API_KEY
router = APIRouter(prefix="/account/billing", tags=["account-billing"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_owner(user: dict) -> None:
    """Only org owners or master admins may change billing."""
    if user.get("is_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only the account owner can change billing")


async def _resolve_org(user: dict) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation linked to this account")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.get("/subscription")
async def get_subscription_status(user: dict = Depends(get_current_user)) -> dict:
    """Single endpoint that powers the self-serve billing UI.

    Returns the org's current plan, Stripe subscription state (if any),
    and any pending cancellation/downgrade scheduled for next renewal.
    """
    org = await _resolve_org(user)
    sub_id = org.get("stripe_subscription_id")

    stripe_state: dict = {}
    if sub_id and STRIPE_API_KEY:
        try:
            sub = stripe.Subscription.retrieve(sub_id)
            stripe_state = {
                "subscription_id": sub.id,
                "status": sub.status,
                "current_period_end": datetime.fromtimestamp(
                    sub.current_period_end, tz=timezone.utc
                ).isoformat() if sub.current_period_end else None,
                "cancel_at_period_end": bool(sub.cancel_at_period_end),
                "trial_end": datetime.fromtimestamp(sub.trial_end, tz=timezone.utc).isoformat()
                if sub.trial_end else None,
            }
        except Exception as exc:
            logger.warning("[billing] Stripe lookup failed for sub %s: %s", sub_id, exc)
            stripe_state = {"error": "stripe_lookup_failed"}

    return {
        "organization_id": org["id"],
        "organization_name": org.get("name"),
        "plan": org.get("subscription_tier") or "trial",
        "is_trial": bool(org.get("is_trial")),
        "trial_ends_at": org.get("trial_ends_at"),
        "billing_status": org.get("billing_status") or "active",
        "enabled_modules": org.get("enabled_modules") or [],
        "pending_cancellation": bool(org.get("pending_cancellation")),
        "cancellation_effective_at": org.get("cancellation_effective_at"),
        "pending_downgrade_to": org.get("pending_downgrade_to"),
        "stripe": stripe_state,
    }


@router.post("/cancel")
async def cancel_subscription(payload: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Cancel the org's subscription at the end of the current billing period.

    Body: `{"reason": "<text>", "feedback": "<optional>"}` — reason is required
    for the regretted-churn analytics dashboard.
    """
    _require_owner(user)
    org = await _resolve_org(user)

    if org.get("pending_cancellation"):
        raise HTTPException(status_code=409, detail="Cancellation already scheduled")

    reason = (payload.get("reason") or "").strip()[:500]
    feedback = (payload.get("feedback") or "").strip()[:2000]
    if not reason:
        raise HTTPException(status_code=400, detail="A cancellation reason is required")

    sub_id = org.get("stripe_subscription_id")
    effective_at = None
    stripe_result = "no_active_subscription"
    if sub_id and STRIPE_API_KEY:
        try:
            sub = stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
            stripe_result = "scheduled_at_period_end"
            if sub.current_period_end:
                effective_at = datetime.fromtimestamp(
                    sub.current_period_end, tz=timezone.utc
                ).isoformat()
        except Exception as exc:
            logger.exception("[billing] Stripe cancel failed for sub %s", sub_id)
            raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "pending_cancellation": True,
            "cancellation_effective_at": effective_at,
            "cancellation_requested_at": _now(),
            "cancellation_reason": reason,
            "cancellation_feedback": feedback,
            "cancellation_requested_by": user["id"],
        }},
    )
    await db.churn_events.insert_one({
        "organization_id": org["id"],
        "user_id": user["id"],
        "user_email": user.get("email"),
        "type": "cancellation_requested",
        "reason": reason,
        "feedback": feedback,
        "plan": org.get("subscription_tier"),
        "created_at": _now(),
    })
    ip = request.client.host if request.client else ""
    await audit_log(
        "billing_cancel_requested", user["id"], user.get("email", ""),
        "organization", org["id"], f"Cancellation requested: {reason}", ip,
    )
    return {
        "ok": True,
        "stripe_result": stripe_result,
        "effective_at": effective_at,
        "message": "Your subscription will end at the end of the current billing period. You can reactivate any time before then.",
    }


@router.post("/reactivate")
async def reactivate_subscription(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Cancel a pending cancellation."""
    _require_owner(user)
    org = await _resolve_org(user)

    if not org.get("pending_cancellation"):
        raise HTTPException(status_code=409, detail="No pending cancellation to reactivate")

    sub_id = org.get("stripe_subscription_id")
    if sub_id and STRIPE_API_KEY:
        try:
            stripe.Subscription.modify(sub_id, cancel_at_period_end=False)
        except Exception as exc:
            logger.exception("[billing] Stripe reactivate failed")
            raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {"pending_cancellation": False},
         "$unset": {"cancellation_effective_at": "", "cancellation_requested_at": "",
                    "cancellation_reason": "", "cancellation_feedback": "",
                    "cancellation_requested_by": ""}},
    )
    ip = request.client.host if request.client else ""
    await audit_log(
        "billing_reactivated", user["id"], user.get("email", ""),
        "organization", org["id"], "Cancellation reverted; subscription continues", ip,
    )
    return {"ok": True, "message": "Your subscription will continue."}


@router.post("/downgrade")
async def schedule_downgrade(payload: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Queue a plan downgrade for the next billing cycle.

    Body: `{"target_tier": "starter|memberships|crm|marketing|operations"}`
    We don't immediately swap the Stripe subscription — that would prorate
    a credit and complicate accounting. Instead we mark it pending; the
    `customer.subscription.updated` webhook will pick it up at renewal.
    """
    _require_owner(user)
    org = await _resolve_org(user)
    target = (payload.get("target_tier") or "").strip().lower()
    allowed = {"starter", "memberships", "crm", "marketing", "operations"}
    if target not in allowed:
        raise HTTPException(status_code=400, detail=f"target_tier must be one of {sorted(allowed)}")

    if org.get("subscription_tier") == target:
        raise HTTPException(status_code=409, detail="You are already on this plan")

    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "pending_downgrade_to": target,
            "pending_downgrade_requested_at": _now(),
            "pending_downgrade_requested_by": user["id"],
        }},
    )
    ip = request.client.host if request.client else ""
    await audit_log(
        "billing_downgrade_scheduled", user["id"], user.get("email", ""),
        "organization", org["id"], f"Downgrade scheduled to '{target}'", ip,
    )
    return {
        "ok": True,
        "target_tier": target,
        "message": f"Your plan will switch to {target} at the next billing cycle.",
    }


@router.post("/downgrade/cancel")
async def cancel_pending_downgrade(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Withdraw a pending downgrade before it takes effect."""
    _require_owner(user)
    org = await _resolve_org(user)
    if not org.get("pending_downgrade_to"):
        raise HTTPException(status_code=409, detail="No pending downgrade to cancel")
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$unset": {"pending_downgrade_to": "", "pending_downgrade_requested_at": "",
                    "pending_downgrade_requested_by": ""}},
    )
    ip = request.client.host if request.client else ""
    await audit_log(
        "billing_downgrade_cancelled", user["id"], user.get("email", ""),
        "organization", org["id"], "Pending downgrade withdrawn", ip,
    )
    return {"ok": True, "message": "Downgrade cancelled. Your plan stays as-is."}
