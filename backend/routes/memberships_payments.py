"""Stripe payments for GymAxis Memberships.

Two flows:
  • Recurring plans → mode='subscription' Checkout Session with a Stripe
    Price lazily provisioned per plan (cached on the plan doc as
    `stripe_product_id` / `stripe_price_id`).
  • Class-pack / PAYG / fixed-term → mode='payment' one-off Session.

Two entry points:
  • Member-initiated: member hits POST /memberships/checkout with a
    member-token.
  • Operator-initiated: operator with their CRM token hits
    POST /memberships/checkout, body additionally carries {member_id}.

Webhook (/memberships/webhook/stripe) does:
  • checkout.session.completed → flip member_memberships.status='active',
    record stripe IDs, credit balance for class_pack.
  • invoice.paid → billing_status='current', next_billing_at.
  • invoice.payment_failed → billing_status='past_due' + send the member a
    friendly update-your-card email.
  • customer.subscription.deleted → status='cancelled'.

All events are deduped through `stripe_event_id` in `payment_transactions`
so Stripe retries are safe. payment_transactions is the canonical
reconciliation ledger mandated by the playbook.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request

from routes.memberships import _require_current_member, _require_operator_org
from utils.auth import verify_token
from utils.database import db, STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-payments"])
stripe.api_key = STRIPE_API_KEY
# Pin API version so subscription/checkout/promotion features behave
# consistently regardless of the connected account's default version.
stripe.api_version = "2024-06-20"


# ═════════════════════ Helpers ═════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_or_create_stripe_price(plan: dict) -> str:
    """Resolve a Stripe Price id for this plan, creating one on the fly if
    we haven't before. Cache onto the plan doc."""
    # Iter 215u — smoothed (pro-rata) plans: bill the smoothed monthly
    # amount as the recurring Stripe price, not the headline price_pence
    # (which is often 0 on smoothed plans). Cached in a separate field
    # so toggling smoothing on/off doesn't mistakenly reuse the wrong
    # Stripe price.
    smoothed = bool(plan.get("smoothed"))
    cache_key = "stripe_price_smoothed_id" if smoothed else "stripe_price_id"
    cached = plan.get(cache_key)
    if cached:
        return cached
    if smoothed:
        annual = int(plan.get("smoothed_annual_pence") or 0)
        months = int(plan.get("smoothed_months") or 12) or 12
        unit_amount = round(annual / months) if annual > 0 else int(plan.get("price_pence") or 0)
    else:
        unit_amount = int(plan["price_pence"])
    product = stripe.Product.create(
        name=plan["name"],
        metadata={"plan_id": plan["id"], "gymaxis_kind": plan["kind"], "smoothed": str(smoothed).lower()},
    )
    price_kwargs = {
        "product": product.id,
        "unit_amount": unit_amount,
        "currency": "gbp",
    }
    # `recurring` and `bundle` (which is just a recurring sub with extra
    # bundled credits) bill on a Stripe subscription. Everything else
    # (class_pack, payg, course, fixed_term) is a one-off `payment` mode.
    if plan["kind"] in ("recurring", "bundle"):
        interval = "year" if plan.get("billing_cycle") == "annual" else "month"
        price_kwargs["recurring"] = {"interval": interval}
    price = stripe.Price.create(**price_kwargs)
    await db.membership_plans.update_one(
        {"id": plan["id"]},
        {"$set": {"stripe_product_id": product.id, cache_key: price.id}},
    )
    return price.id


async def _resolve_plan_and_member(
    plan_id: str, target_member_id: Optional[str], org_id: str
) -> tuple[dict, dict]:
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    member = await db.members.find_one(
        {"id": target_member_id, "organization_id": org_id},
        {"_id": 0, "password": 0},
    )
    if not member:
        raise HTTPException(404, "Member not found")
    return plan, member


# ═════════════════════ Checkout ═════════════════════

@router.post("/memberships/checkout")
async def create_checkout(request: Request, body: dict = Body(...)):
    """Create a Stripe Checkout Session for a plan purchase.

    Body:
      - plan_id (required)
      - origin_url (required — frontend's window.location.origin)
      - member_id (optional — operator flow; member flow derives from token)
      - promo_code (optional — Phase 1: validated server-side and the
                    matching Stripe promotion_code is attached to the
                    Checkout Session so Stripe enforces the discount)

    Accepts EITHER an operator JWT (POST from /memberships console) OR a
    member JWT (POST from /members portal).

    Returns: {url, session_id, promo?: {...validation preview}}
    """
    plan_id = body.get("plan_id")
    origin_url = body.get("origin_url") or str(request.base_url).rstrip("/")
    promo_code = (body.get("promo_code") or "").strip() or None
    if not plan_id:
        raise HTTPException(400, "plan_id required")

    # Resolve caller → member + org
    target_member_id: Optional[str] = None
    org_id: Optional[str] = None
    auth = request.headers.get("authorization", "")
    payload = verify_token(auth.split(" ", 1)[1]) if auth.lower().startswith("bearer ") else None
    if payload and payload.get("kind") != "member":
        # Operator flow — resolve their org
        user = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(401, "Operator user not found")
        org_id = await _require_operator_org(user)
        target_member_id = body.get("member_id")
        if not target_member_id:
            raise HTTPException(400, "member_id required when operator initiates")
    else:
        member = await _require_current_member(request)
        target_member_id = member["id"]
        org_id = member["organization_id"]

    plan, member = await _resolve_plan_and_member(plan_id, target_member_id, org_id)

    # ── Phase 1: validate promo code (if supplied) so we can attach the
    # matching Stripe PromotionCode to the session and Stripe enforces the
    # discount end-to-end. We also return the preview to the caller for UX.
    promo_preview: Optional[dict] = None
    if promo_code:
        from routes.memberships_promotions import _validate_for_checkout
        promo_preview = await _validate_for_checkout(
            org_id=org_id, code=promo_code, plan_id=plan_id,
            member_id=member["id"],
        )

    # Build price (subscription) OR amount (one-off)
    # Subscriptions: kind=recurring or kind=bundle (which is also recurring
    # but with bundled credits/PT credits per cycle).
    is_subscription_kind = plan["kind"] in ("recurring", "bundle")
    mode = "subscription" if is_subscription_kind else "payment"
    price_id = await _get_or_create_stripe_price(plan)

    # Pre-create or update pending membership row so the webhook can find it
    pending_membership_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    end_date: Optional[str] = None
    if plan["kind"] == "fixed_term" and plan.get("duration_days"):
        end_date = (now + timedelta(days=int(plan["duration_days"]))).isoformat()
    mm_doc = {
        "id": pending_membership_id,
        "member_id": member["id"],
        "plan_id": plan["id"],
        "organization_id": org_id,
        "status": "pending_payment",
        "start_date": now.isoformat(),
        "end_date": end_date,
        "billing_status": "pending",
        "credits_remaining": 0,  # Filled in after payment succeeds
        "credits_used": 0,
        "joined_at": now.isoformat(),
        "audit_log": [{"at": _now_iso(), "actor_id": (payload or {}).get("user_id") or "member", "action": "checkout_initiated"}],
    }
    await db.member_memberships.insert_one(mm_doc)

    success_url = f"{origin_url}/members?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/members?checkout=cancel"
    metadata = {
        "plan_id": plan["id"],
        "plan_kind": plan["kind"],
        "member_id": member["id"],
        "organization_id": org_id,
        "membership_id": pending_membership_id,
        "initiated_by": (payload or {}).get("user_id") or f"member:{member['id'] if 'member' in locals() else target_member_id}",
    }
    if promo_preview:
        metadata["promo_id"] = promo_preview["promo_id"]
        metadata["promo_code"] = promo_preview["code"]
        metadata["promo_savings_pence"] = str(promo_preview["savings_pence"])

    session_kwargs: dict = {
        "payment_method_types": ["card"],
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode": mode,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": member["email"],
        "client_reference_id": member["id"],
        "metadata": metadata,
    }

    # ── Phase 1: free trial — Stripe takes care of delaying the first
    # invoice; our existing webhook handles the eventual charge.
    if mode == "subscription" and int(plan.get("trial_days") or 0) > 0:
        session_kwargs["subscription_data"] = {
            "trial_period_days": int(plan["trial_days"]),
            "metadata": {"membership_id": pending_membership_id},
        }
        await db.member_memberships.update_one(
            {"id": pending_membership_id},
            {"$set": {"trial_days": int(plan["trial_days"]),
                      "trial_ends_at": (now + timedelta(days=int(plan["trial_days"]))).isoformat()}},
        )

    # ── Phase 1: promo code — attach Stripe's PromotionCode so the
    # discount is enforced at checkout time.
    if promo_preview and promo_preview.get("stripe_promotion_code_id"):
        session_kwargs["discounts"] = [
            {"promotion_code": promo_preview["stripe_promotion_code_id"]},
        ]

    # ── Stripe Connect routing — when the gym has finished Connect onboarding,
    # the member's payment is a destination charge into the gym's own account
    # (minus the platform fee). Falls back to the platform account otherwise.
    from utils.stripe_connect_routing import (
        resolve_org_connect_routing,
        payment_intent_connect_kwargs,
        subscription_connect_kwargs,
    )
    org_doc = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    routing = await resolve_org_connect_routing(org_doc)
    if routing:
        if mode == "subscription":
            sub_data = session_kwargs.get("subscription_data") or {}
            sub_data.update(subscription_connect_kwargs(routing))
            session_kwargs["subscription_data"] = sub_data
        else:
            net_pence = int(plan["price_pence"])
            if promo_preview:
                net_pence = max(0, net_pence - int(promo_preview.get("savings_pence") or 0))
            pi_data = payment_intent_connect_kwargs(routing, net_pence)
            if pi_data:
                session_kwargs["payment_intent_data"] = pi_data

    try:
        session = stripe.checkout.Session.create(**session_kwargs)
    except stripe.StripeError as e:
        logger.exception("Stripe session create failed")
        await db.member_memberships.delete_one({"id": pending_membership_id})
        raise HTTPException(400, f"Stripe error: {e}")

    # Record the pending txn (playbook-mandated `payment_transactions` collection)
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "member_id": member["id"],
        "membership_id": pending_membership_id,
        "plan_id": plan["id"],
        "organization_id": org_id,
        "amount_pence": int(plan["price_pence"]),
        "currency": "gbp",
        "mode": mode,
        "status": "pending",
        "payment_status": "pending",
        "metadata": metadata,
        "created_at": _now_iso(),
    })

    # Save the session id onto the membership so the webhook can find it
    await db.member_memberships.update_one(
        {"id": pending_membership_id},
        {"$set": {"stripe_checkout_session_id": session.id}},
    )

    return {
        "url": session.url, "session_id": session.id,
        "promo": promo_preview,
    }


@router.get("/memberships/checkout/status/{session_id}")
async def checkout_status(session_id: str):
    """Polled by the frontend after Stripe redirect. Reconciles the
    session on demand so even if the webhook has not yet landed, the
    user still sees their success state."""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e}")

    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if txn and txn["status"] != "complete" and session.payment_status == "paid":
        # Webhook may not have fired yet — promote the membership lazily.
        await _mark_membership_paid(session.metadata or {}, session)
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "complete", "payment_status": "paid", "completed_at": _now_iso()}},
        )

    return {
        "status": session.status,
        "payment_status": session.payment_status,
        "amount_total": session.amount_total,
        "currency": session.currency,
        "metadata": dict(session.metadata or {}),
    }


@router.post("/member/billing-portal")
async def member_billing_portal(request: Request, body: dict = Body(default={})):
    """Return a short-lived Stripe Customer Portal URL so the member can
    update their card / cancel without leaving the app."""
    member = await _require_current_member(request)
    origin_url = body.get("origin_url") or "https://app.gymaxis.ai"
    mm = await db.member_memberships.find_one(
        {"member_id": member["id"], "stripe_customer_id": {"$ne": None}},
        {"_id": 0, "stripe_customer_id": 1},
        sort=[("joined_at", -1)],
    )
    if not mm or not mm.get("stripe_customer_id"):
        raise HTTPException(400, "No Stripe billing profile yet — subscribe to a plan first")
    try:
        portal = stripe.billing_portal.Session.create(
            customer=mm["stripe_customer_id"],
            return_url=f"{origin_url}/members?tab=plan",
        )
    except stripe.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e}")
    return {"url": portal.url}


# ═════════════════════ Abandoned checkout sweep ═════════════════════

async def sweep_abandoned_checkouts(older_than_hours: int = 24) -> dict:
    """Mark any pending_payment memberships older than N hours as abandoned
    (so they don't clog the DB or confuse future reports). Called from the
    sicon_poller loop."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
    result = await db.member_memberships.update_many(
        {"status": "pending_payment", "joined_at": {"$lt": cutoff}},
        {"$set": {"status": "abandoned", "abandoned_at": _now_iso()},
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": "system", "action": "abandoned_checkout"}}},
    )
    # Mirror onto the txn ledger
    txn_result = await db.payment_transactions.update_many(
        {"status": "pending", "created_at": {"$lt": cutoff}},
        {"$set": {"status": "abandoned"}},
    )
    logger.info(f"[abandoned-sweep] memberships={result.modified_count} txns={txn_result.modified_count}")
    return {"memberships_swept": result.modified_count, "txns_swept": txn_result.modified_count}

async def _mark_membership_paid(meta: dict, session) -> Optional[dict]:
    """Transition the pre-created member_memberships doc to 'active'."""
    mm_id = meta.get("membership_id")
    if not mm_id:
        return None
    mm = await db.member_memberships.find_one({"id": mm_id}, {"_id": 0})
    if not mm:
        return None
    if mm["status"] == "active":
        return mm  # already promoted — idempotent
    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0})
    updates: dict = {
        "status": "active",
        "billing_status": "current",
        "last_billed_at": _now_iso(),
    }
    now = datetime.now(timezone.utc)
    # ── Class packs: grant credits + optional expiry ─────────────────
    if plan and plan["kind"] == "class_pack":
        updates["credits_remaining"] = int(plan.get("credits_count") or 0)
        if plan.get("pack_expiry_days"):
            updates["credits_expires_at"] = (
                now + timedelta(days=int(plan["pack_expiry_days"]))
            ).isoformat()
    # ── Recurring + Bundle subscriptions ────────────────────────────
    if plan and plan["kind"] in ("recurring", "bundle"):
        days = 365 if plan.get("billing_cycle") == "annual" else 30
        updates["next_billing_at"] = (now + timedelta(days=days)).isoformat()
        sub_id = getattr(session, "subscription", None)
        if sub_id:
            updates["stripe_subscription_id"] = sub_id
        # Bundles: also grant the bundled class credits + PT credits per cycle
        if plan["kind"] == "bundle":
            if plan.get("credits_count"):
                updates["credits_remaining"] = int(plan["credits_count"])
            if plan.get("pt_credits_count"):
                updates["pt_credits_remaining"] = int(plan["pt_credits_count"])
    # ── Course: auto-enrol member into all course occurrences ───────
    if plan and plan["kind"] == "course":
        await _enrol_member_in_course(plan, mm["member_id"], mm["organization_id"])
    cust_id = getattr(session, "customer", None)
    if cust_id:
        updates["stripe_customer_id"] = cust_id
    await db.member_memberships.update_one(
        {"id": mm_id},
        {"$set": updates,
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": "stripe", "action": "payment_succeeded"}}},
    )
    await db.members.update_one(
        {"id": mm["member_id"]},
        {"$set": {"status": "active"},
         "$inc": {"lifetime_value_pence": int(plan.get("price_pence") or 0) if plan else 0}},
    )
    # Referral conversion — first paid checkout flips any pending referral to earned
    await _convert_pending_referral(mm["member_id"])

    # ── Phase 1: promo redemption tracking ──────────────────────────
    promo_id = (meta or {}).get("promo_id")
    if promo_id:
        try:
            from routes.memberships_promotions import record_promo_redemption
            await record_promo_redemption(
                promo_id=promo_id,
                organization_id=mm["organization_id"],
                member_id=mm["member_id"],
                plan_id=mm["plan_id"],
                session_id=getattr(session, "id", "") or "",
                savings_pence=int(meta.get("promo_savings_pence") or 0),
            )
        except Exception as exc:  # pragma: no cover
            logger.info("[checkout] promo redemption record failed: %s", exc)

    return {**mm, **updates}


async def _enrol_member_in_course(
    plan: dict, member_id: str, organization_id: str,
) -> int:
    """Auto-create bookings for every course occurrence on the plan once
    the course has been paid for. Idempotent — a member can't double-book
    the same occurrence."""
    occ_ids = plan.get("course_occurrence_ids") or []
    if not occ_ids:
        return 0
    n = 0
    for occ_id in occ_ids:
        existing = await db.bookings.find_one(
            {"member_id": member_id, "occurrence_id": occ_id,
             "status": {"$in": ["booked", "waitlist", "attended"]}},
            {"_id": 0, "id": 1},
        )
        if existing:
            continue
        occ = await db.class_occurrences.find_one(
            {"id": occ_id}, {"_id": 0},
        )
        if not occ:
            continue
        await db.bookings.insert_one({
            "id": str(uuid.uuid4()),
            "occurrence_id": occ_id,
            "member_id": member_id,
            "organization_id": organization_id,
            "site_id": occ.get("site_id"),
            "status": "booked",
            "credits_charged": 0,
            "from_course_plan_id": plan["id"],
            "booked_at": _now_iso(),
            "channel": "course_enrolment",
        })
        await db.class_occurrences.update_one(
            {"id": occ_id}, {"$inc": {"bookings_count": 1}},
        )
        n += 1
    return n


async def _convert_pending_referral(member_id: str) -> None:
    """If this member was referred and has a pending referral, award credit
    to the referrer and flip the referral row to 'earned'. Idempotent — only
    the oldest pending referral per referee converts."""
    pending = await db.referrals.find_one(
        {"referee_id": member_id, "status": "pending"},
        {"_id": 0}, sort=[("created_at", 1)])
    if not pending:
        return
    await db.referrals.update_one(
        {"id": pending["id"]},
        {"$set": {"status": "earned", "earned_at": _now_iso()}},
    )
    await db.members.update_one(
        {"id": pending["referrer_id"]},
        {"$inc": {"promo_credit_pence": int(pending.get("credit_pence") or 0)}},
    )


async def _mark_payment_failed(sub_id: str | None, cust_id: str | None, background: BackgroundTasks | None) -> None:
    q: dict = {}
    if sub_id:
        q["stripe_subscription_id"] = sub_id
    elif cust_id:
        q["stripe_customer_id"] = cust_id
    else:
        return
    mm = await db.member_memberships.find_one(q, {"_id": 0})
    if not mm:
        return
    await db.member_memberships.update_one(
        {"id": mm["id"]},
        {"$set": {"billing_status": "past_due"},
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": "stripe", "action": "payment_failed"}}},
    )
    member = await db.members.find_one({"id": mm["member_id"]}, {"_id": 0, "password": 0})
    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0})
    if background is not None and member and plan:
        background.add_task(_send_payment_failed_email, member, plan)


async def _mark_subscription_cancelled(sub_id: str) -> None:
    mm = await db.member_memberships.find_one({"stripe_subscription_id": sub_id}, {"_id": 0})
    if not mm:
        return
    await db.member_memberships.update_one(
        {"id": mm["id"]},
        {"$set": {"status": "cancelled", "cancel_effective_date": _now_iso(),
                  "cancel_reason": "stripe_subscription_deleted"},
         "$push": {"audit_log": {"at": _now_iso(), "actor_id": "stripe", "action": "subscription_cancelled"}}},
    )


async def _send_payment_failed_email(member: dict, plan: dict) -> None:
    first = member.get("first_name") or "there"
    amount = f"£{plan['price_pence']/100:.2f}"
    html = f"""<div style="font-family:-apple-system,sans-serif;max-width:540px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="padding:28px 32px;border-bottom:1px solid rgba(239,68,68,0.3);">
    <div style="color:#EF4444;font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">Payment failed</div>
    <h1 style="color:#fff;font-size:20px;margin:0;line-height:1.3;font-weight:800;">We couldn't take your {amount} payment</h1>
  </div>
  <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
    <p>Hi {first},</p>
    <p>Your {plan.get('name') or 'membership'} renewal payment of <strong>{amount}</strong> didn't go through — usually this is an expired card or insufficient funds, nothing more serious.</p>
    <p style="color:#9ca3af;font-size:13px;">Your membership is marked <strong style="color:#F59E0B;">past due</strong> — please update your card to keep access. Reply to this email or pop into reception and we'll sort it in a minute.</p>
  </div>
  <div style="background:#05070A;padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
    <p style="color:#6b7280;font-size:11px;margin:0;">GymAxis Memberships · Billing</p>
  </div>
</div>"""
    await send_email(member["email"], f"Payment failed · {plan.get('name') or 'membership'}", html, category="billing")


@router.post("/memberships/webhook/stripe")
async def stripe_webhook(request: Request, background: BackgroundTasks):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        # Iter 215ae — in production this is a hard failure. Dev keeps the
        # old unsigned-payload path so local testing with Stripe CLI works.
        if (os.environ.get("APP_ENV") or "").lower() == "production":
            logger.critical("[stripe-webhook] STRIPE_WEBHOOK_SECRET is not set in production")
            raise HTTPException(503, "Webhook signing not configured")
        logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check (DEV ONLY)")
        try:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
        except Exception as e:
            raise HTTPException(400, f"Invalid payload: {e}")
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.SignatureVerificationError:
            raise HTTPException(400, "Bad signature")
        except Exception as e:
            raise HTTPException(400, f"Invalid payload: {e}")

    # Idempotency gate — dedupe via stripe_event_id
    if await db.payment_transactions.find_one({"stripe_event_id": event["id"]}, {"_id": 1}):
        return {"ok": True, "deduped": True}
    await db.payment_transactions.update_one(
        {"session_id": (event["data"]["object"] or {}).get("id", "")},
        {"$setOnInsert": {"stripe_event_id": event["id"], "created_at": _now_iso()}},
        upsert=False,
    )

    etype = event["type"]
    obj = event["data"]["object"]
    try:
        if etype == "checkout.session.completed":
            session = stripe.checkout.Session.retrieve(obj["id"])
            meta = dict(session.metadata or {})
            # Iter 215u — route class-invoice payments to the studio_billing
            # handler. Subscription/one-off plan flows continue through
            # _mark_membership_paid as before.
            if meta.get("gymaxis_kind") == "class_invoice":
                from routes.memberships.studio_billing import (
                    mark_class_invoice_paid_from_session,
                )
                await mark_class_invoice_paid_from_session(meta, session)
            elif meta.get("gymaxis_kind") == "class_invoice_bundle":
                from routes.memberships.studio_billing import (
                    mark_class_invoice_bundle_paid,
                )
                await mark_class_invoice_bundle_paid(meta, session)
            elif meta.get("gymaxis_kind") == "autopay_setup":
                from routes.memberships.family_autopay import (
                    complete_autopay_setup,
                )
                await complete_autopay_setup(meta, session)
            elif meta.get("gymaxis_kind") == "wallet_topup":
                from routes.memberships.wallet import (
                    complete_wallet_topup,
                )
                await complete_wallet_topup(meta, session)
            elif meta.get("gymaxis_kind") == "credit_pack":
                # Iter 216h202 — member self-serve class-pack purchase.
                # See routes/memberships/credit_packs.py.
                from routes.memberships.credit_packs import (
                    complete_credit_pack_purchase,
                )
                await complete_credit_pack_purchase(meta, session)
            else:
                await _mark_membership_paid(meta, session)
            await db.payment_transactions.update_one(
                {"session_id": session.id},
                {"$set": {"status": "complete", "payment_status": session.payment_status,
                          "stripe_event_id": event["id"], "completed_at": _now_iso()}},
            )
        elif etype == "invoice.paid":
            sub_id = obj.get("subscription")
            if sub_id:
                mm = await db.member_memberships.find_one({"stripe_subscription_id": sub_id}, {"_id": 0})
                if mm:
                    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0})
                    days = 365 if (plan or {}).get("billing_cycle") == "annual" else 30
                    await db.member_memberships.update_one(
                        {"id": mm["id"]},
                        {"$set": {"billing_status": "current", "last_billed_at": _now_iso(),
                                  "next_billing_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()},
                         "$push": {"audit_log": {"at": _now_iso(), "actor_id": "stripe", "action": "invoice_paid"}}},
                    )
        elif etype == "invoice.payment_failed":
            await _mark_payment_failed(obj.get("subscription"), obj.get("customer"), background)
        elif etype == "customer.subscription.deleted":
            await _mark_subscription_cancelled(obj["id"])
    except Exception:
        logger.exception(f"Webhook handler failed for {etype}")
        # Still 200 so Stripe doesn't hammer us — we have the event id logged.

    return {"ok": True, "event": etype}
