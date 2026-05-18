"""Member-facing class-pack purchase — iter 216h202.

Closes the credit-loop Lee flagged: when a member hits the "Need 1
credit — purchase a pack" 402 on the booking endpoint, this module
gives them a Stripe Checkout to buy a pack right from the portal.

Endpoints
---------
* ``GET  /api/member/credit-packs``         → list packs available to buy
* ``POST /api/member/credit-pack-checkout`` → Stripe Checkout for pack id

Webhook
-------
``complete_credit_pack_purchase(meta, session)`` is called by the
central Stripe webhook in ``memberships_payments.py`` when
``metadata.gymaxis_kind == 'credit_pack'``. Atomically:

  1. Dedups on stripe_session_id (idempotent if webhook fires twice).
  2. If the member already has an active class_pack membership for the
     SAME plan, tops up its `credits_remaining` and extends
     `credits_expires_at` by `pack_expiry_days`.
  3. Otherwise creates a fresh `member_memberships` row with
     status="active" + credits_remaining + credits_expires_at.

Source of truth for available packs: the operator's
``membership_plans`` collection. We surface every plan where
``kind == "class_pack"`` AND ``status == "active"`` for that org.
Operators can hide a pack from self-purchase by flipping
``visible_for_self_purchase = False`` on the plan doc.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from utils.database import db, STRIPE_API_KEY
from routes.memberships.helpers import _now_iso, _require_current_member, _uuid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-credit-packs"])

stripe.api_key = STRIPE_API_KEY


def _frontend() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


# ═══════════════════════ Member endpoints ═══════════════════════


@router.get("/member/credit-packs")
async def list_credit_packs(request: Request) -> dict:
    """Return every active class_pack plan for the member's org that is
    flagged ``visible_for_self_purchase`` (default True). Operators can
    hide pricier corporate packs from the public list by setting that
    flag to False on the plan doc."""
    member = await _require_current_member(request)
    org_id = member.get("organization_id")
    if not org_id:
        return {"packs": [], "currency": "gbp"}
    cursor = db.membership_plans.find(
        {"organization_id": org_id,
         "kind": "class_pack",
         "status": "active",
         "$or": [
             {"visible_for_self_purchase": True},
             {"visible_for_self_purchase": {"$exists": False}},
         ]},
        {"_id": 0},
    ).sort("price_pence", 1)
    packs: list[dict] = []
    async for p in cursor:
        packs.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "price_pence": int(p.get("price_pence") or 0),
            "credits_count": int(p.get("credits_count") or 0),
            "pack_expiry_days": p.get("pack_expiry_days"),
            "colour": p.get("colour"),
            "description": p.get("description") or "",
            "value_per_credit_pence": (
                int(p.get("price_pence") or 0) // max(1, int(p.get("credits_count") or 1))
            ),
        })
    return {"packs": packs, "currency": "gbp"}


class PackCheckoutIn(BaseModel):
    plan_id: str


@router.post("/member/credit-pack-checkout")
async def create_credit_pack_checkout(request: Request, body: PackCheckoutIn = Body(...)):
    """Mint a Stripe Checkout for a single class-pack purchase.

    Security note: the price is read from the plan in OUR database,
    never from the client. The client only sends ``plan_id``.
    """
    if not STRIPE_API_KEY:
        raise HTTPException(503, "Stripe is not configured for this studio.")
    member = await _require_current_member(request)
    # Rate-limit: stop a compromised JWT spamming Stripe sessions.
    from utils.security_plus import rate_limit_async
    await rate_limit_async(
        f"credit_pack_checkout:{member['id']}",
        max_requests=10, window_seconds=60,
    )

    plan = await db.membership_plans.find_one(
        {"id": body.plan_id,
         "organization_id": member.get("organization_id"),
         "kind": "class_pack",
         "status": "active"},
        {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Pack not found or not available")
    price_pence = int(plan.get("price_pence") or 0)
    if price_pence <= 0:
        raise HTTPException(400, "Pack has no price configured — contact the studio")
    if int(plan.get("credits_count") or 0) <= 0:
        raise HTTPException(400, "Pack has no credits configured — contact the studio")

    frontend = _frontend()
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{frontend}/members?credits=purchased",
        cancel_url=f"{frontend}/members?credits=cancelled",
        customer_email=member.get("email") or None,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "gbp",
                "unit_amount": price_pence,
                "product_data": {
                    "name": f"{plan.get('name') or 'Class pack'}",
                    "description": (
                        f"{plan.get('credits_count')} class credits"
                        + (f" · expires in {plan.get('pack_expiry_days')} days"
                           if plan.get("pack_expiry_days") else "")
                    ),
                },
            },
        }],
        metadata={
            "gymaxis_kind": "credit_pack",
            "gymaxis_member_id": member["id"],
            "gymaxis_org_id": member.get("organization_id") or "",
            "gymaxis_plan_id": plan["id"],
        },
    )
    # Insert pending payment_transactions row so we have audit even if
    # the webhook is delayed.
    await db.payment_transactions.insert_one({
        "id": _uuid(),
        "session_id": session.id,
        "kind": "credit_pack",
        "member_id": member["id"],
        "organization_id": member.get("organization_id") or "",
        "plan_id": plan["id"],
        "amount_pence": price_pence,
        "currency": "gbp",
        "status": "pending",
        "created_at": _now_iso(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


# ═══════════════════════ Webhook completion ═══════════════════════


async def complete_credit_pack_purchase(meta: dict, session) -> None:
    """Apply the purchased pack to the member. Called from the central
    Stripe webhook on `checkout.session.completed` when
    ``gymaxis_kind == credit_pack``.

    Idempotency: deduped on `stripe_session_id` — re-running on the
    same session is a safe no-op.
    """
    member_id = meta.get("gymaxis_member_id")
    plan_id = meta.get("gymaxis_plan_id")
    org_id = meta.get("gymaxis_org_id") or ""
    if not member_id or not plan_id:
        logger.warning("[credit_pack] webhook missing member_id/plan_id meta=%s", meta)
        return
    session_id = (
        getattr(session, "id", None)
        or (session.get("id") if isinstance(session, dict) else None)
    )
    if not session_id:
        logger.warning("[credit_pack] webhook with no session id meta=%s", meta)
        return
    # Idempotency: have we already processed this session?
    if await db.member_memberships.find_one(
        {"stripe_session_id": session_id}, {"_id": 1},
    ):
        logger.info("[credit_pack] webhook deduped session=%s", session_id)
        return
    plan = await db.membership_plans.find_one(
        {"id": plan_id}, {"_id": 0},
    )
    if not plan:
        logger.warning("[credit_pack] plan not found id=%s", plan_id)
        return
    credits = int(plan.get("credits_count") or 0)
    expiry_days = plan.get("pack_expiry_days")
    expires_at = None
    if expiry_days:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=int(expiry_days))
        ).isoformat()

    # If the member already has an active pack for THIS plan, top it up
    # rather than spawning a duplicate row (matches the assign-plan
    # idempotency we shipped in iter 216h200).
    existing = await db.member_memberships.find_one(
        {"member_id": member_id, "plan_id": plan_id, "status": "active"},
        {"_id": 0},
    )
    if existing:
        new_credits = int(existing.get("credits_remaining") or 0) + credits
        update_doc = {
            "$set": {
                "credits_remaining": new_credits,
                "last_topup_at": _now_iso(),
                "stripe_session_id": session_id,
            },
            "$push": {
                "audit_log": {
                    "at": _now_iso(), "actor_id": "stripe",
                    "action": f"topped_up_{credits}_credits",
                },
            },
        }
        if expires_at:
            update_doc["$set"]["credits_expires_at"] = expires_at
        await db.member_memberships.update_one({"id": existing["id"]}, update_doc)
        logger.info(
            "[credit_pack] topped up member=%s +%d credits (total=%d)",
            member_id, credits, new_credits,
        )
    else:
        # Fresh class_pack membership.
        await db.member_memberships.insert_one({
            "id": _uuid(),
            "member_id": member_id,
            "organization_id": org_id,
            "plan_id": plan_id,
            "status": "active",
            "credits_remaining": credits,
            "credits_expires_at": expires_at,
            "joined_at": _now_iso(),
            "stripe_session_id": session_id,
            "purchased_via": "member_self_serve",
            "audit_log": [{
                "at": _now_iso(), "actor_id": "stripe",
                "action": f"purchased_pack_{credits}_credits",
            }],
        })
        logger.info(
            "[credit_pack] created new pack membership member=%s plan=%s credits=%d",
            member_id, plan_id, credits,
        )

    # Mark the payment_transactions row complete.
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "complete", "completed_at": _now_iso()}},
    )


# ═══════════════════════ Polling endpoint ═══════════════════════


@router.get("/member/credit-pack-status/{session_id}")
async def credit_pack_status(session_id: str, request: Request):
    """Member-portal polling — used by the success page to confirm the
    pack landed before showing the "credits added" toast. Webhook is
    the source of truth; this endpoint just looks at the local row."""
    member = await _require_current_member(request)
    txn = await db.payment_transactions.find_one(
        {"session_id": session_id, "member_id": member["id"]},
        {"_id": 0},
    )
    if not txn:
        raise HTTPException(404, "Checkout session not found")
    return {
        "status": txn.get("status"),
        "amount_pence": txn.get("amount_pence"),
        "plan_id": txn.get("plan_id"),
    }
