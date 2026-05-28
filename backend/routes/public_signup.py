"""Public member sign-up flow for individual gyms.

This is what powers https://app.gymaxisai.com/m/{gym_slug}/join — the
operator-side Marketing campaigns funnel members here. The flow:

  1. GET  /api/public/signup/{slug}/branding   — gym name, logo, colours
  2. GET  /api/public/signup/{slug}/plans      — published membership plans
  3. POST /api/public/signup/{slug}/draft      — save partial signup
                                                  (email captured ⇒ we can
                                                  recover via magic link)
  4. POST /api/public/signup/{slug}/parq       — submit PARQ answers
  5. POST /api/public/signup/{slug}/checkout   — create Stripe Checkout
                                                  session on the gym's
                                                  connected account, with
                                                  application_fee_amount
                                                  = 1% of the total
  6. GET  /api/public/signup/status/{session}  — front-end polls for the
                                                  payment outcome
  7. POST /api/webhooks/stripe-checkout        — webhook handler that
                                                  flips the draft into a
                                                  real member record

PARQ rules:
  * Default 7-question PARQ-Q template
  * If ANY answer is "yes", we set ``parq_clearance_required = True`` on
    the member record AND we still let the payment go through (option B
    from the user's spec). The gym is notified to chase a GP-clearance
    letter within 14 days.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Body, HTTPException, Path, Request

from routes.stripe_connect import PLATFORM_FEE_PERCENT
from utils.database import db

load_dotenv()
log = logging.getLogger("public_signup")
stripe.api_key = os.getenv("STRIPE_API_KEY")

router = APIRouter(tags=["public-signup"])


PARQ_DEFAULT = [
    {"id": "heart", "q": "Has your doctor ever said you have a heart condition or that you should only do physical activity recommended by a doctor?"},
    {"id": "chest_pain", "q": "Do you feel pain in your chest when you do physical activity?"},
    {"id": "dizzy", "q": "In the past month, have you had chest pain when not doing physical activity, or have you lost your balance because of dizziness?"},
    {"id": "bone_joint", "q": "Do you have a bone or joint problem that could be made worse by a change in your physical activity?"},
    {"id": "medication", "q": "Is your doctor currently prescribing drugs (for example, water pills) for your blood pressure or heart condition?"},
    {"id": "other", "q": "Do you know of any other reason why you should not do physical activity?"},
    {"id": "pregnancy", "q": "Are you pregnant, or have you given birth in the last 6 weeks?"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _resolve_gym(slug: str) -> dict:
    slug_clean = (slug or "").strip().lower()
    if not slug_clean:
        raise HTTPException(400, "slug required")
    gym = await db.organizations.find_one(
        {"$or": [{"slug": slug_clean}, {"id": slug_clean}]},
        {"_id": 0},
    )
    if not gym:
        raise HTTPException(404, "Gym not found")
    return gym


def _public_branding(gym: dict) -> dict:
    branding = gym.get("branding") or {}
    return {
        "id": gym["id"],
        "slug": gym.get("slug") or gym["id"],
        "name": gym.get("name") or branding.get("company_name") or "Your gym",
        "logo_url": branding.get("logo_url"),
        "primary_colour": branding.get("primary_colour") or "#2563EB",
        "accent_colour": branding.get("accent_colour") or "#19CDFF",
        "tagline": branding.get("tagline") or "Train. Belong. Grow.",
        "hero_image_url": branding.get("hero_image_url"),
        "address": gym.get("address") or "",
        "phone": gym.get("contact_phone") or "",
        "email": gym.get("contact_email") or "",
        "stripe_ready": bool(gym.get("stripe_account_id")),
    }


def _format_plan(plan: dict) -> dict:
    return {
        "id": plan["id"],
        "name": plan.get("name") or "Membership",
        "description": plan.get("description") or "",
        "monthly_price_pence": int(plan.get("monthly_price_pence") or plan.get("price_pence") or 0),
        "joining_fee_pence": int(plan.get("joining_fee_pence") or 0),
        "contract_months": int(plan.get("contract_months") or 0),
        "early_termination_fee_pence": int(plan.get("early_termination_fee_pence") or 0),
        "accept_card": plan.get("accept_card", True),
        "accept_bacs": plan.get("accept_bacs", False),
        "accept_wallet": plan.get("accept_wallet", True),
        "currency": (plan.get("currency") or "GBP").upper(),
        "perks": plan.get("perks") or [],
        "best_for": plan.get("best_for") or "",
    }


# ── Public reads ──────────────────────────────────────────────────────


@router.get("/public/signup/{slug}/branding")
async def get_branding(slug: str = Path(...)):
    gym = await _resolve_gym(slug)
    return {"gym": _public_branding(gym), "parq_questions": gym.get("parq_template") or PARQ_DEFAULT}


@router.get("/public/signup/{slug}/plans")
async def get_plans(slug: str = Path(...)):
    gym = await _resolve_gym(slug)
    rows = await db.membership_plans.find(
        {
            "organization_id": gym["id"],
            "$or": [{"published": True}, {"public": True}],
            "archived": {"$ne": True},
        },
        {"_id": 0},
    ).sort("monthly_price_pence", 1).to_list(length=50)
    if not rows:
        # fallback: surface ALL active plans so a gym that hasn't ticked
        # "published" still has something visible during early adoption
        rows = await db.membership_plans.find(
            {"organization_id": gym["id"], "archived": {"$ne": True}},
            {"_id": 0},
        ).sort("monthly_price_pence", 1).to_list(length=50)
    return {"plans": [_format_plan(p) for p in rows], "count": len(rows)}


# ── Draft signup (saves email + meta to recover via magic link) ───────


@router.post("/public/signup/{slug}/draft")
async def save_draft(slug: str = Path(...), body: dict = Body(...)):
    gym = await _resolve_gym(slug)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "valid email required")
    draft_id = body.get("draft_id") or str(uuid.uuid4())
    doc = {
        "id": draft_id,
        "organization_id": gym["id"],
        "gym_slug": gym.get("slug") or gym["id"],
        "step": (body.get("step") or "details")[:32],
        "plan_id": body.get("plan_id"),
        "details": {
            "first_name": (body.get("first_name") or "").strip()[:80],
            "last_name": (body.get("last_name") or "").strip()[:80],
            "email": email,
            "phone": (body.get("phone") or "").strip()[:32],
            "dob": body.get("dob"),
            "address": (body.get("address") or "").strip()[:240],
            "emergency_contact_name": (body.get("emergency_contact_name") or "").strip()[:80],
            "emergency_contact_phone": (body.get("emergency_contact_phone") or "").strip()[:32],
            "marketing_consent": bool(body.get("marketing_consent")),
        },
        "updated_at": _now(),
    }
    existing = await db.signup_drafts.find_one({"id": draft_id}, {"_id": 0})
    if existing:
        await db.signup_drafts.update_one({"id": draft_id}, {"$set": doc})
    else:
        doc["created_at"] = _now()
        await db.signup_drafts.insert_one(doc.copy())
    return {"ok": True, "draft_id": draft_id}


@router.get("/public/signup/{slug}/draft/{draft_id}")
async def get_draft(slug: str = Path(...), draft_id: str = Path(...)):
    """Read-only draft fetch for magic-link pre-fill."""
    gym = await _resolve_gym(slug)
    draft = await db.signup_drafts.find_one(
        {"id": draft_id, "organization_id": gym["id"]},
        {"_id": 0},
    )
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.get("member_id"):
        raise HTTPException(410, "This sign-up has already been completed")
    return {"draft": {
        "id": draft["id"],
        "plan_id": draft.get("plan_id"),
        "details": draft.get("details") or {},
        "parq": draft.get("parq") or {},
        "step": draft.get("step", "details"),
    }}


@router.post("/public/signup/{slug}/parq")
async def save_parq(slug: str = Path(...), body: dict = Body(...)):
    await _resolve_gym(slug)
    draft_id = body.get("draft_id")
    if not draft_id:
        raise HTTPException(400, "draft_id required")
    answers = body.get("answers") or {}
    flagged = any(bool(v) for v in answers.values())
    await db.signup_drafts.update_one(
        {"id": draft_id},
        {"$set": {
            "parq": {"answers": answers, "flagged": flagged, "submitted_at": _now()},
            "updated_at": _now(),
        }},
    )
    return {"ok": True, "clearance_required": flagged}


# ── Checkout creation (destination charge + 1% application fee) ───────


def _origin_or(default: str, request: Request) -> str:
    return (request.headers.get("origin") or default).rstrip("/")


def _payment_method_types(plan: dict) -> list[str]:
    methods = []
    if plan.get("accept_card", True):
        methods.append("card")
    if plan.get("accept_bacs", False):
        methods.append("bacs_debit")
    # Apple/Google Pay are auto-enabled on card; PayPal opt-in only if the
    # connected account has it active. We deliberately omit "paypal" from
    # default flows to avoid Stripe rejecting the session.
    return methods or ["card"]


@router.post("/public/signup/{slug}/checkout")
async def create_checkout(
    request: Request,
    slug: str = Path(...),
    body: dict = Body(...),
):
    gym = await _resolve_gym(slug)
    if not gym.get("stripe_account_id"):
        raise HTTPException(400, "This gym has not connected payments yet. Please contact them directly.")
    draft_id = body.get("draft_id")
    plan_id = body.get("plan_id")
    if not draft_id or not plan_id:
        raise HTTPException(400, "draft_id and plan_id required")
    draft = await db.signup_drafts.find_one({"id": draft_id, "organization_id": gym["id"]}, {"_id": 0})
    if not draft:
        raise HTTPException(404, "Draft not found")
    plan = await db.membership_plans.find_one({"id": plan_id, "organization_id": gym["id"]}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Plan not found")
    plan_fmt = _format_plan(plan)

    origin = _origin_or("https://gymaxisai.com", request)
    success_url = f"{origin}/m/{gym.get('slug') or gym['id']}/join/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/m/{gym.get('slug') or gym['id']}/join?cancelled=1&draft={draft_id}"
    currency = plan_fmt["currency"].lower()

    line_items: list[dict[str, Any]] = []
    # Recurring monthly subscription
    line_items.append({
        "price_data": {
            "currency": currency,
            "unit_amount": plan_fmt["monthly_price_pence"],
            "recurring": {"interval": "month"},
            "product_data": {"name": plan_fmt["name"]},
        },
        "quantity": 1,
    })
    # One-off joining fee (if any)
    if plan_fmt["joining_fee_pence"] > 0:
        line_items.append({
            "price_data": {
                "currency": currency,
                "unit_amount": plan_fmt["joining_fee_pence"],
                "product_data": {"name": "Joining fee"},
            },
            "quantity": 1,
        })

    # Application fee: 1% of the recurring price (floored, never below 50p)
    application_fee_amount = max(50, int(plan_fmt["monthly_price_pence"] * (PLATFORM_FEE_PERCENT / 100.0)))

    metadata = {
        "draft_id": draft_id,
        "plan_id": plan_id,
        "organization_id": gym["id"],
        "platform_fee_percent": str(PLATFORM_FEE_PERCENT),
    }

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=_payment_method_types(plan_fmt),
            line_items=line_items,
            customer_email=(draft.get("details") or {}).get("email"),
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            subscription_data={
                "application_fee_percent": PLATFORM_FEE_PERCENT,
                "metadata": metadata,
            },
            stripe_account=gym["stripe_account_id"],
        )
    except stripe.error.StripeError as exc:
        log.error("Checkout session create failed: %s", exc, exc_info=True)
        raise HTTPException(400, f"Stripe error: {exc.user_message or str(exc)}")

    txn = {
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "draft_id": draft_id,
        "organization_id": gym["id"],
        "plan_id": plan_id,
        "amount_total_pence": plan_fmt["monthly_price_pence"] + plan_fmt["joining_fee_pence"],
        "currency": currency,
        "stripe_account_id": gym["stripe_account_id"],
        "application_fee_amount_pence": application_fee_amount,
        "status": "initiated",
        "payment_status": "unpaid",
        "metadata": metadata,
        "created_at": _now(),
    }
    await db.payment_transactions.insert_one(txn.copy())

    await db.signup_drafts.update_one(
        {"id": draft_id},
        {"$set": {"checkout_session_id": session.id, "step": "payment", "updated_at": _now()}},
    )

    return {"url": session.url, "session_id": session.id}


@router.get("/public/signup/status/{session_id}")
async def checkout_status(session_id: str = Path(...)):
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.get("payment_status") == "paid" and txn.get("member_id"):
        # already finalised — return cached state
        return {"status": "complete", "payment_status": "paid", "member_id": txn["member_id"], "draft_id": txn.get("draft_id")}
    # Live poll
    try:
        gym = await db.organizations.find_one({"id": txn["organization_id"]}, {"_id": 0})
        session = stripe.checkout.Session.retrieve(session_id, stripe_account=gym.get("stripe_account_id"))
    except stripe.error.StripeError as exc:
        log.warning("status retrieve failed: %s", exc)
        return {"status": txn.get("status"), "payment_status": txn.get("payment_status")}
    payment_status = session.get("payment_status")
    new_status = "complete" if session.get("status") == "complete" else "open"
    update = {"status": new_status, "payment_status": payment_status, "updated_at": _now()}
    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": update})
    if payment_status == "paid":
        member_id = await _finalise_signup(session_id)
        return {"status": "complete", "payment_status": "paid", "member_id": member_id, "draft_id": txn.get("draft_id")}
    return {"status": new_status, "payment_status": payment_status}


# ── Webhook + finalise ────────────────────────────────────────────────


WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


async def _finalise_signup(session_id: str) -> str | None:
    """Create the real member record. Idempotent on session_id."""
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        return None
    if txn.get("member_id"):
        return txn["member_id"]
    draft = await db.signup_drafts.find_one({"id": txn["draft_id"]}, {"_id": 0})
    if not draft:
        log.warning("Draft missing for session %s", session_id)
        return None
    details = draft.get("details") or {}
    parq = draft.get("parq") or {"flagged": False, "answers": {}}
    member_id = str(uuid.uuid4())
    member_doc = {
        "id": member_id,
        "organization_id": txn["organization_id"],
        "first_name": details.get("first_name") or "",
        "last_name": details.get("last_name") or "",
        "email": (details.get("email") or "").strip().lower(),
        "phone": details.get("phone") or "",
        "dob": details.get("dob"),
        "address": details.get("address") or "",
        "emergency_contact_name": details.get("emergency_contact_name") or "",
        "emergency_contact_phone": details.get("emergency_contact_phone") or "",
        "marketing_consent": bool(details.get("marketing_consent")),
        "plan_id": txn["plan_id"],
        "status": "active",
        "joined_at": _now(),
        "joined_via": "online_signup",
        "parq_clearance_required": bool(parq.get("flagged")),
        "parq_answers": parq.get("answers") or {},
        "stripe_session_id": session_id,
    }
    await db.members.insert_one(member_doc.copy())
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"member_id": member_id, "payment_status": "paid", "status": "complete", "finalised_at": _now()}},
    )
    await db.signup_drafts.update_one(
        {"id": draft["id"]},
        {"$set": {"member_id": member_id, "step": "complete", "completed_at": _now()}},
    )
    # Emit a marketing/CRM signal — listeners hook in later.
    evt = {
        "id": str(uuid.uuid4()),
        "organization_id": txn["organization_id"],
        "type": "online_signup_completed",
        "member_id": member_id,
        "plan_id": txn["plan_id"],
        "amount_total_pence": txn.get("amount_total_pence", 0),
        "parq_flagged": bool(parq.get("flagged")),
        "tour_requested": bool(draft.get("tour_requested")),
        "first_class_id": draft.get("first_class_id"),
        "created_at": _now(),
    }
    await db.signup_events.insert_one(evt.copy())
    # Phase-2: kick off the welcome-journey email schedule.
    try:
        from routes.signup_journeys import schedule_welcome_journey
        await schedule_welcome_journey(evt)
    except Exception as exc:  # noqa: BLE001
        log.warning("schedule_welcome_journey skipped for %s: %s", member_id, exc)
    return member_id


@router.post("/webhooks/stripe-checkout")
async def webhook_checkout(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
        else:
            import json as _json
            event = _json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid signature: {exc}")
    etype = event["type"] if isinstance(event, dict) is False else event.get("type")
    # Iter 220as — Stripe webhook idempotency. Without dedupe a retry
    # of ``checkout.session.completed`` would call _finalise_signup
    # twice and could double-bill / double-grant a new tenant.
    from utils.stripe_idempotency import mark_event_processed
    event_id = event["id"] if isinstance(event, dict) is False else event.get("id")
    if not await mark_event_processed(event_id, handler="public_signup"):
        return {"received": True, "duplicate": True}
    if etype == "checkout.session.completed":
        obj = event["data"]["object"] if isinstance(event, dict) is False else event.get("data", {}).get("object", {})
        sid = (obj or {}).get("id") if isinstance(obj, dict) else obj.id
        await _finalise_signup(sid)
    return {"received": True}


__all__ = ["router"]
