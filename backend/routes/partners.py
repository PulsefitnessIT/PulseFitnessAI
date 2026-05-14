"""Partner Engineer Network — iter 216h75 (Phase 1).

Commercial layer ON TOP of the existing Engineer App (`routes/svc/*`) and
Service Desk (`routes/service_desk*`). DOES NOT duplicate jobs, cases,
engineers, customers, or billing. One source of truth.

Collections owned here (all keyed by `partner_id`, NEVER by org):
  • partner_engineers          — partner profile (status, level, terms, refcode)
  • partner_referrals          — one row per referred organisation
  • partner_commission_ledger  — append-only accruals (signup + recurring)
  • partner_payouts            — batched approved accruals → CSV / Connect
  • partner_audit_log          — every state transition

Joins (read-only):
  • users                      — auth + email
  • organizations              — the referred org (stores `referred_by_partner_id`)
  • svc_engineers              — the operational engineer profile (unrelated)
  • marketing_campaigns        — unused; referral attribution lives on org

Anti-abuse invariants (Phase 1):
  1. A partner's OWN organisation can NEVER count as a referral.
  2. `organizations.referred_by_partner_id` is write-once. Master admin can
     unlink with audit but never silently reassign.
  3. Commission is accrued automatically on Stripe `invoice.paid` for the
     Operations module, but each ledger row needs Master Admin approval
     before it can be moved into a payout batch.
  4. Refund/clawback path: ledger row flipped to `clawed_back` so the
     running totals still reconcile against accruals.
  5. `pre_existing_in_pipeline=true` on the referred org disqualifies it
     from commission at accrual time (master admin sets this when needed).
  6. Referral codes are short, unique, case-insensitive — and uppercase
     stored to defeat homoglyph confusion.

Commission model (locked at MVP):
  • Signup reward = 50% of the FIRST cleared Operations module charge.
  • Recurring     = £3 per active referred customer per month.
  • Operations module price increased to £69/mo (was £59) — this iter.

App fee tiers (computed from active referred customer count):
  • 0–4   → £30/mo
  • 5–9   → £15/mo
  • 10+   → free
  • 25+   → free + `enhanced_review_required=true` flag
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── constants ─────────────────────────

PARTNER_PLAN_BASE_GBP = 30
RECURRING_GBP = 3
SIGNUP_REWARD_PCT = 0.5
OPERATIONS_PRICE_GBP = 69  # Iter 216h75 — bumped from £59
TERMS_VERSION = "2026-02-13"

# Iter 216h80 — Pulse Fitness isolation. The Partner Engineer Network
# is a GymAxis-only commercial layer. Pulse customers/orgs must NEVER:
#   • see the "Find an engineer" widget
#   • have their first Operations invoice trigger a signup reward
#   • be allowed to attach a referral code on signup
#   • be issued customer-engineer grants
# We import lazily to avoid an import cycle.
PULSE_ACCOUNT_TYPES = {"pulse_pro", "pulse_lite", "pulse"}


def _is_pulse_user(user: dict) -> bool:
    at = (user or {}).get("account_type") or ""
    if at.lower() in PULSE_ACCOUNT_TYPES:
        return True
    if user.get("is_pulse_admin"):
        return True
    if (user.get("brand") or "").lower() in ("pulse", "pulse_fitness"):
        return True
    return False


async def _is_pulse_org(org_id: Optional[str]) -> bool:
    """True if the organisation is on the Pulse Fitness portal."""
    if not org_id:
        return False
    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "account_type": 1, "brand": 1},
    )
    if not org:
        return False
    at = (org.get("account_type") or "").lower()
    if at in PULSE_ACCOUNT_TYPES:
        return True
    if (org.get("brand") or "").lower() in ("pulse", "pulse_fitness"):
        return True
    return False


def _require_gymaxis_only(user: dict) -> None:
    """Raise 403 if the caller is a Pulse Fitness user. The Partner
    Engineer Network is exclusively a GymAxis programme."""
    if _is_pulse_user(user):
        raise HTTPException(
            status_code=403,
            detail="The Partner Engineer Network is exclusive to GymAxis — Pulse Fitness customers don't have access to this programme.",
        )


PARTNER_STATUSES = {"draft", "pending", "approved", "rejected", "suspended"}
PARTNER_LEVELS = {"customer_added", "engineer_partner", "verified_partner", "strategic_partner"}
LEDGER_KINDS = {"signup_reward", "recurring"}
LEDGER_STATES = {"accrued", "approved", "paid", "clawed_back", "rejected"}
PAYOUT_STATES = {"queued", "processing", "paid", "failed"}
PAYOUT_METHODS = {"manual_csv", "stripe_connect"}

# Iter 216h76 — Live Partner Plan Stripe subscription (Phase 2 of the
# Partner Engineer Network). Two env-driven Stripe prices map to the
# auto-computed `app_fee_tier`:
#   • STRIPE_PRICE_PARTNER_PLAN_30 → £30/mo (0-4 active referrals)
#   • STRIPE_PRICE_PARTNER_PLAN_15 → £15/mo (5-9 active referrals)
#   • free tier (10+) → subscription is cancelled at period end
PARTNER_PLAN_PRICE_IDS_BY_TIER = {
    30: "STRIPE_PRICE_PARTNER_PLAN_30",
    15: "STRIPE_PRICE_PARTNER_PLAN_15",
}


# ───────────────────────── helpers ─────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to dodge homoglyphs


async def _new_referral_code() -> str:
    """Short, uppercase, collision-checked."""
    for _ in range(20):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if not await db.partner_engineers.find_one({"referral_code": code}, {"_id": 1}):
            return code
    raise HTTPException(500, "Failed to mint a unique referral code — please retry")


def _validate_postcode(pc: str) -> str:
    cleaned = re.sub(r"\s+", " ", (pc or "").strip().upper())
    if not cleaned or len(cleaned) > 12:
        raise HTTPException(400, "Service-area postcode is required")
    return cleaned


def _require_master_admin(user: dict) -> None:
    """Local copy of routes.master_admin.require_master_admin to avoid an
    expensive cross-module import cycle. Behaviour identical."""
    if user.get("is_master_admin") or user.get("email") == os.environ.get("MASTER_ADMIN_EMAIL"):
        return
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


async def _audit(*, partner_id: str, actor_id: str, action: str, before=None, after=None, note: str = "") -> None:
    await db.partner_audit_log.insert_one({
        "id": _new_id(),
        "partner_id": partner_id,
        "actor_id": actor_id,
        "action": action,
        "before": before,
        "after": after,
        "note": note,
        "at": _now(),
    })


async def _get_partner_by_user(user_id: str) -> Optional[dict]:
    return _public(await db.partner_engineers.find_one({"user_id": user_id}))


def _public_referral_link(code: str) -> str:
    """Used in the Partner Dashboard. Frontend base URL drives the host."""
    base = (
        os.environ.get("PARTNER_REFERRAL_BASE_URL")
        or os.environ.get("EMAIL_PUBLIC_BASE_URL")
        or os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    return f"{base}/?ref={code}" if base else f"?ref={code}"


def _app_fee_tier(active_count: int) -> dict:
    """Pure function — also called from the dashboard so the operator and
    the billing engine never disagree."""
    if active_count >= 25:
        return {"price_gbp": 0, "label": "Free + enhanced review", "enhanced_review_required": True}
    if active_count >= 10:
        return {"price_gbp": 0, "label": "Free (10+ active referrals)", "enhanced_review_required": False}
    if active_count >= 5:
        return {"price_gbp": 15, "label": "£15/mo (5-9 active referrals)", "enhanced_review_required": False}
    return {"price_gbp": PARTNER_PLAN_BASE_GBP, "label": f"£{PARTNER_PLAN_BASE_GBP}/mo", "enhanced_review_required": False}


async def _active_referral_count(partner_id: str) -> int:
    return await db.partner_referrals.count_documents({
        "partner_id": partner_id,
        "status": "active",
    })


async def _recompute_app_fee(partner_id: str) -> dict:
    """Recompute the partner's app-fee tier off the live active count.
    Persists `app_fee_tier` + `enhanced_review_required` and returns the
    tier. Also re-syncs the live Stripe subscription (if any) so that
    crossing a milestone (£30 → £15 → free) automatically transitions
    the partner's billing without a manual round-trip."""
    count = await _active_referral_count(partner_id)
    tier = _app_fee_tier(count)
    previous = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0, "app_fee_tier": 1, "subscription": 1})
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {
            "active_referral_count": count,
            "app_fee_tier": tier,
            "enhanced_review_required": tier["enhanced_review_required"],
            "updated_at": _now(),
        }},
    )
    # Auto-sync Stripe subscription if the tier price changed.
    prev_tier = (previous or {}).get("app_fee_tier") or {}
    if prev_tier.get("price_gbp") != tier["price_gbp"]:
        try:
            await _sync_partner_subscription_to_tier(partner_id, tier)
        except Exception:
            logger.exception("[partners] subscription auto-sync failed for partner=%s", partner_id)
    return tier


# ───────────────────────── Stripe subscription helpers (iter 216h76) ─────────────────────────


def _partner_plan_price_id_for_tier(tier: dict) -> Optional[str]:
    """Return the env-configured Stripe price ID matching this tier's
    `price_gbp` — or None when the tier is free (no subscription needed)
    or when the env var is unset (production must seed the price IDs)."""
    env_key = PARTNER_PLAN_PRICE_IDS_BY_TIER.get(tier.get("price_gbp"))
    if not env_key:
        return None
    return os.environ.get(env_key) or None


async def _sync_partner_subscription_to_tier(partner_id: str, tier: dict) -> None:
    """Live Stripe subscription transitions for a partner when their
    `app_fee_tier` changes (e.g. 4 → 5 active referrals = £30 → £15).

    Behaviour:
      • Free tier (10+ refs)  → cancel at period_end (engineer keeps
        access until the end of the paid month, then it lapses to free).
      • Paid tier change      → ``stripe.Subscription.modify`` to swap
        the price ID with proration, so the engineer is credited fairly
        for the lower price.
      • No active sub yet     → no-op (engineer hasn't checked out).
    """
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    sub_state = (partner or {}).get("subscription") or {}
    sub_id = sub_state.get("stripe_subscription_id")
    if not sub_id:
        return  # nothing to sync until checkout completes

    try:
        import stripe  # local import — keeps Stripe optional in unit tests
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
    except ImportError:
        logger.warning("[partners] stripe SDK unavailable — skipping subscription sync")
        return

    target_price_id = _partner_plan_price_id_for_tier(tier)
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] subscription retrieve failed: %s", exc)
        return

    if target_price_id is None:
        # Free tier — cancel at period end so we don't take another £30/£15.
        if sub.get("cancel_at_period_end"):
            return
        try:
            stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        except Exception:
            logger.exception("[partners] cancel-at-period-end failed")
            return
        await db.partner_engineers.update_one(
            {"id": partner_id},
            {"$set": {"subscription.cancel_at_period_end": True,
                      "subscription.synced_at": _now()}},
        )
        await _audit(partner_id=partner_id, actor_id="system",
                     action="subscription_cancel_at_period_end",
                     after={"reason": "free_tier_unlocked"})
        return

    # Paid tier — swap the price ID on the existing subscription item.
    items = (sub.get("items") or {}).get("data") or []
    if not items:
        return
    current_price_id = (items[0].get("price") or {}).get("id")
    if current_price_id == target_price_id:
        # Already correct; just clear any pending cancellation.
        if sub.get("cancel_at_period_end"):
            try:
                stripe.Subscription.modify(sub_id, cancel_at_period_end=False)
                await db.partner_engineers.update_one(
                    {"id": partner_id},
                    {"$set": {"subscription.cancel_at_period_end": False,
                              "subscription.synced_at": _now()}},
                )
            except Exception:
                logger.exception("[partners] re-instate failed")
        return
    try:
        stripe.Subscription.modify(
            sub_id,
            cancel_at_period_end=False,
            proration_behavior="create_prorations",
            items=[{"id": items[0]["id"], "price": target_price_id}],
        )
    except Exception:
        logger.exception("[partners] subscription price swap failed")
        return
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {
            "subscription.stripe_price_id": target_price_id,
            "subscription.cancel_at_period_end": False,
            "subscription.synced_at": _now(),
        }},
    )
    await _audit(partner_id=partner_id, actor_id="system",
                 action="subscription_price_swap",
                 after={"price_id": target_price_id, "tier_gbp": tier["price_gbp"]})


# ───────────────────────── PARTNER (self) endpoints ─────────────────────────


@router.get("/partners/me")
async def get_my_partner(user: dict = Depends(get_current_user)):
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        return {"partner": None}
    # Fresh counts
    await _recompute_app_fee(partner["id"])
    partner = _public(await db.partner_engineers.find_one({"id": partner["id"]}))
    return {"partner": partner, "referral_link": _public_referral_link(partner["referral_code"])}


@router.post("/partners/apply")
async def apply_partner(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Submit / refresh the partner application. Idempotent — calling
    again updates the draft profile until master admin approval lands."""
    _require_gymaxis_only(user)
    existing = await db.partner_engineers.find_one({"user_id": user["id"]}, {"_id": 0})
    if existing and existing.get("status") == "approved":
        # Once approved, only individual profile-edit endpoints can mutate.
        raise HTTPException(400, "Application is already approved — use /partners/me to edit your profile")

    full_name = (body.get("full_name") or user.get("full_name") or "").strip()
    company_name = (body.get("company_name") or "").strip()
    if not full_name:
        raise HTTPException(400, "Full name is required")

    accepted = bool(body.get("terms_accepted"))
    if not accepted:
        raise HTTPException(400, "You must accept the Partner Engineer terms")

    profile = {
        "full_name": full_name,
        "company_name": company_name or None,
        "phone": (body.get("phone") or "").strip() or None,
        "service_postcode": _validate_postcode(body.get("service_postcode") or ""),
        "travel_radius_km": int(body.get("travel_radius_km") or 25),
        "brands_supported": [s.strip() for s in (body.get("brands_supported") or []) if str(s).strip()][:25],
        "skills": [s.strip() for s in (body.get("skills") or []) if str(s).strip()][:25],
        "qualifications": [s.strip() for s in (body.get("qualifications") or []) if str(s).strip()][:25],
        "insurance_docs": (body.get("insurance_docs") or [])[:10],
        "terms_accepted_at": _now(),
        "terms_version": TERMS_VERSION,
        "updated_at": _now(),
    }

    if existing:
        # Resubmission after a rejection / draft polish.
        await db.partner_engineers.update_one(
            {"id": existing["id"]},
            {"$set": {**profile, "status": "pending", "rejected_reason": None}},
        )
        await _audit(
            partner_id=existing["id"], actor_id=user["id"], action="resubmit",
            before={"status": existing.get("status")}, after={"status": "pending"},
        )
        partner_id = existing["id"]
    else:
        partner_id = _new_id()
        referral_code = await _new_referral_code()
        doc = {
            "id": partner_id,
            "user_id": user["id"],
            "email": user.get("email"),
            "owner_organization_id": user.get("organization_id"),
            "status": "pending",
            "level": "engineer_partner",
            "referral_code": referral_code,
            "active_referral_count": 0,
            "app_fee_tier": _app_fee_tier(0),
            "enhanced_review_required": False,
            "subscription": {"status": "trialing", "stripe_subscription_id": None, "current_period_end": None},
            "payout": {"method": "manual_csv", "stripe_account_id": None, "bank_name": None, "sort_code": None,
                       "account_number_last4": None},
            "created_at": _now(),
            **profile,
        }
        await db.partner_engineers.insert_one(doc)
        await _audit(partner_id=partner_id, actor_id=user["id"], action="apply",
                     after={"status": "pending"})

    fresh = _public(await db.partner_engineers.find_one({"id": partner_id}))
    return {"partner": fresh, "referral_link": _public_referral_link(fresh["referral_code"])}


@router.get("/partners/me/referrals")
async def list_my_referrals(user: dict = Depends(get_current_user)):
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile")
    rows = await db.partner_referrals.find(
        {"partner_id": partner["id"]}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=500)
    return {"referrals": rows}


@router.get("/partners/me/commission")
async def my_commission(user: dict = Depends(get_current_user)):
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile")
    ledger = await db.partner_commission_ledger.find(
        {"partner_id": partner["id"]}, {"_id": 0},
    ).sort("created_at", -1).limit(500).to_list(length=500)

    def _sum(state: str) -> float:
        return round(sum(r["amount_gbp"] for r in ledger if r["status"] == state), 2)

    return {
        "ledger": ledger,
        "totals": {
            "accrued":     _sum("accrued"),
            "approved":    _sum("approved"),
            "paid":        _sum("paid"),
            "clawed_back": _sum("clawed_back"),
        },
    }


# ───────────────────────── PARTNER PLAN subscription (iter 216h76) ─────────────────────────


@router.post("/partners/me/subscription/checkout")
async def create_partner_subscription_checkout(
    body: dict = Body(default_factory=dict), user: dict = Depends(get_current_user),
):
    """Create a Stripe Checkout Session for the partner's app-fee plan.

    The price ID auto-selects from the partner's CURRENT `app_fee_tier` —
    so a brand-new partner lands on the £30 price, a partner with 5+
    active referrals lands on £15, and a partner at the free tier gets
    a friendly 400 ("you're already free, no checkout needed")."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile — apply first")
    if partner.get("status") != "approved":
        raise HTTPException(400, "Application must be approved before starting the subscription")
    tier = await _recompute_app_fee(partner["id"])
    if tier["price_gbp"] == 0:
        raise HTTPException(400, "You're on the free tier — no subscription needed")
    price_id = _partner_plan_price_id_for_tier(tier)
    if not price_id:
        raise HTTPException(
            501,
            "Partner Plan Stripe price IDs not configured — ask Master Admin to set "
            "STRIPE_PRICE_PARTNER_PLAN_30 and STRIPE_PRICE_PARTNER_PLAN_15 in the env.",
        )

    origin_url = (body.get("origin_url") or "").rstrip("/") or (
        os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    ).rstrip("/")
    if not origin_url:
        raise HTTPException(400, "origin_url is required")

    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
    except ImportError:
        raise HTTPException(503, "Stripe SDK unavailable")

    success_url = f"{origin_url}/partner-engineer?subscription=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/partner-engineer?subscription=cancelled"
    metadata = {
        "partner_id": partner["id"],
        "user_id": user["id"],
        "user_email": user.get("email") or "",
        "kind": "partner_engineer_plan",
        "tier_gbp": str(tier["price_gbp"]),
    }
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user.get("email"),
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )
    except Exception as exc:
        logger.exception("[partners] partner-plan checkout failed")
        raise HTTPException(400, f"Stripe checkout failed: {exc}")

    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {
            "subscription.checkout_session_id": session.id,
            "subscription.checkout_started_at": _now(),
            "subscription.target_price_id": price_id,
        }},
    )
    return {"url": session.url, "session_id": session.id}


@router.post("/partners/me/subscription/cancel")
async def cancel_partner_subscription(user: dict = Depends(get_current_user)):
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile")
    sub_id = ((partner.get("subscription") or {}).get("stripe_subscription_id"))
    if not sub_id:
        raise HTTPException(400, "No active subscription to cancel")
    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
    except Exception as exc:
        raise HTTPException(400, f"Stripe cancellation failed: {exc}")
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"subscription.cancel_at_period_end": True, "subscription.synced_at": _now()}},
    )
    await _audit(partner_id=partner["id"], actor_id=user["id"],
                 action="subscription_cancel", after={"cancel_at_period_end": True})
    return {"ok": True}


@router.post("/partners/me/subscription/resume")
async def resume_partner_subscription(user: dict = Depends(get_current_user)):
    """Reverse a pending-cancellation. Useful if the engineer dropped
    below the free threshold and wants to keep paying for the moment."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile")
    sub_id = ((partner.get("subscription") or {}).get("stripe_subscription_id"))
    if not sub_id:
        raise HTTPException(400, "No subscription to resume")
    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
        stripe.Subscription.modify(sub_id, cancel_at_period_end=False)
    except Exception as exc:
        raise HTTPException(400, f"Stripe resume failed: {exc}")
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"subscription.cancel_at_period_end": False, "subscription.synced_at": _now()}},
    )
    await _audit(partner_id=partner["id"], actor_id=user["id"],
                 action="subscription_resume", after={"cancel_at_period_end": False})
    return {"ok": True}


# ──── Stripe webhook entrypoints (called from routes/payments.py) ────


async def handle_partner_checkout_completed(session_data: dict) -> Optional[dict]:
    """Hook from `_handle_checkout_completed`. Wires a fresh Stripe
    subscription to the partner profile."""
    metadata = session_data.get("metadata") or {}
    if metadata.get("kind") != "partner_engineer_plan":
        return None
    partner_id = metadata.get("partner_id")
    sub_id = session_data.get("subscription")
    customer_id = session_data.get("customer")
    if not (partner_id and sub_id):
        return None
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {
            "subscription.stripe_subscription_id": sub_id,
            "subscription.stripe_customer_id": customer_id,
            "subscription.status": "active",
            "subscription.activated_at": _now(),
            "subscription.cancel_at_period_end": False,
            "subscription.synced_at": _now(),
        }},
    )
    await _audit(partner_id=partner_id, actor_id="system",
                 action="subscription_activated",
                 after={"stripe_subscription_id": sub_id, "stripe_customer_id": customer_id})
    return {"partner_id": partner_id, "subscription_id": sub_id}


async def handle_partner_subscription_event(sub_data: dict) -> Optional[dict]:
    """Hook from `customer.subscription.{updated,deleted}` webhooks. Keeps
    the partner profile in sync with Stripe (status, period end, cancel flag)."""
    metadata = sub_data.get("metadata") or {}
    if metadata.get("kind") != "partner_engineer_plan":
        return None
    partner_id = metadata.get("partner_id")
    sub_id = sub_data.get("id")
    if not (partner_id and sub_id):
        return None
    status = sub_data.get("status") or "unknown"
    items = (sub_data.get("items") or {}).get("data") or []
    current_price = (items[0].get("price") or {}).get("id") if items else None
    period_end_epoch = sub_data.get("current_period_end") or 0
    period_end_iso = (
        datetime.fromtimestamp(int(period_end_epoch), tz=timezone.utc).isoformat()
        if period_end_epoch else None
    )
    update: dict = {
        "subscription.status": status,
        "subscription.current_period_end": period_end_iso,
        "subscription.cancel_at_period_end": bool(sub_data.get("cancel_at_period_end")),
        "subscription.stripe_price_id": current_price,
        "subscription.synced_at": _now(),
    }
    if status in ("canceled", "unpaid", "incomplete_expired"):
        update["subscription.cancelled_at"] = _now()
    await db.partner_engineers.update_one({"id": partner_id}, {"$set": update})
    await _audit(partner_id=partner_id, actor_id="system",
                 action="subscription_event",
                 after={"status": status, "price_id": current_price,
                        "cancel_at_period_end": update["subscription.cancel_at_period_end"]})
    return {"partner_id": partner_id, "status": status}


# ───────────────────────── PUBLIC referral attribution ─────────────────────────


@router.get("/partners/public/lookup")
async def public_referral_lookup(code: str = Query(...)):
    """Light-weight public endpoint hit by the signup pages to verify a
    referral code BEFORE binding it to the new organisation. Returns the
    partner's first name + level only (no PII / no commercials)."""
    code_up = (code or "").strip().upper()
    if not code_up:
        raise HTTPException(400, "Missing code")
    partner = await db.partner_engineers.find_one(
        {"referral_code": code_up, "status": "approved"},
        {"_id": 0, "full_name": 1, "company_name": 1, "level": 1, "referral_code": 1, "id": 1},
    )
    if not partner:
        return {"valid": False}
    first = (partner.get("full_name") or "Your engineer").split(" ")[0]
    return {
        "valid": True,
        "first_name": first,
        "company_name": partner.get("company_name"),
        "level": partner.get("level"),
        "code": partner["referral_code"],
    }


async def attach_referral_to_org(*, organization_id: str, ref_code: Optional[str]) -> Optional[dict]:
    """Called from auth.register() — write-once link from the new org back
    to the partner. Returns the partner_referrals row, or None when no
    code / unknown code / org is the partner's own org."""
    if not ref_code:
        return None
    code_up = ref_code.strip().upper()
    partner = await db.partner_engineers.find_one(
        {"referral_code": code_up, "status": "approved"}, {"_id": 0},
    )
    if not partner:
        return None
    # Iter 216h80 — Pulse Fitness isolation. Block referral attachment
    # if the org is a Pulse customer (programme is GymAxis-only).
    if await _is_pulse_org(organization_id):
        return None
    # Anti-abuse: partner can't refer their own org.
    if partner.get("owner_organization_id") == organization_id:
        return None
    # Already-attributed orgs are immutable.
    org = await db.organizations.find_one({"id": organization_id}, {"_id": 0, "referred_by_partner_id": 1})
    if org and org.get("referred_by_partner_id"):
        return None

    ref_id = _new_id()
    ref_doc = {
        "id": ref_id,
        "partner_id": partner["id"],
        "referral_code": code_up,
        "referred_organization_id": organization_id,
        "status": "pending",  # promoted to active on first cleared invoice
        "pre_existing_in_pipeline": False,
        "created_at": _now(),
        "first_paid_at": None,
        "last_recurring_at": None,
        "recurring_total_paid_gbp": 0.0,
        "signup_reward_amount_gbp": None,
    }
    await db.partner_referrals.insert_one(ref_doc)
    await db.organizations.update_one(
        {"id": organization_id},
        {"$set": {"referred_by_partner_id": partner["id"], "referred_by_code": code_up,
                  "referred_at": _now()}},
    )
    await _audit(partner_id=partner["id"], actor_id="system", action="referral_attributed",
                 after={"organization_id": organization_id, "code": code_up})
    return ref_doc


# ───────────────────────── COMMISSION accrual (webhook entrypoint) ─────────────────────────


def _is_operations_charge(invoice_data: dict) -> bool:
    """Best-effort module sniffer. We treat any line containing the word
    'operations' in the description OR the env-defined Operations Stripe
    price id as the Operations module."""
    target_price_ids = {
        os.environ.get("STRIPE_PRICE_OPERATIONS"),
        os.environ.get("STRIPE_PRICE_OPERATIONS_ANNUAL"),
    }
    target_price_ids.discard(None)
    lines = (invoice_data.get("lines") or {}).get("data") or []
    for line in lines:
        price = line.get("price") or {}
        if target_price_ids and price.get("id") in target_price_ids:
            return True
        desc = (line.get("description") or "").lower()
        if "operations" in desc:
            return True
    return False


def _invoice_amount_paid_gbp(invoice_data: dict) -> float:
    """Stripe amounts are in pence. We use `amount_paid` (post tax/discount)
    so the commission tracks the *actual* paid revenue, not headline."""
    pence = invoice_data.get("amount_paid") or invoice_data.get("amount_due") or 0
    return round(float(pence) / 100.0, 2)


async def accrue_commission_on_invoice_paid(invoice_data: dict) -> Optional[dict]:
    """Hook called from `routes.payments._handle_invoice_paid`. Idempotent
    by Stripe invoice id — second webhook delivery is a no-op.

    Accrues:
      • signup_reward (once per referral) on the first cleared Operations
        invoice for that org;
      • recurring £3 per subsequent month's cleared Operations invoice.

    Returns the ledger row created, or None when the invoice is irrelevant
    (no referral, not Operations, or already-processed)."""
    customer_id = invoice_data.get("customer") or ""
    if not customer_id:
        return None
    invoice_id = invoice_data.get("id") or ""

    org = await db.organizations.find_one(
        {"stripe_customer_id": customer_id},
        {"_id": 0, "id": 1, "referred_by_partner_id": 1, "account_type": 1, "brand": 1},
    )
    if not (org and org.get("referred_by_partner_id")):
        return None
    # Iter 216h80 — defensive Pulse check. Even if a Pulse org somehow
    # ended up with a referred_by_partner_id (legacy data), block accrual.
    if (org.get("account_type") or "").lower() in PULSE_ACCOUNT_TYPES \
            or (org.get("brand") or "").lower() in ("pulse", "pulse_fitness"):
        return None
    if not _is_operations_charge(invoice_data):
        return None

    # Idempotency — same invoice can fire twice on Stripe retries
    if invoice_id and await db.partner_commission_ledger.find_one(
        {"source_invoice_id": invoice_id}, {"_id": 1},
    ):
        return None

    partner_id = org["referred_by_partner_id"]
    ref = await db.partner_referrals.find_one(
        {"partner_id": partner_id, "referred_organization_id": org["id"]}, {"_id": 0},
    )
    if not ref:
        return None
    if ref.get("pre_existing_in_pipeline"):
        # Master admin has blocked this referral from commission.
        return None

    amount_paid = _invoice_amount_paid_gbp(invoice_data)
    is_first = ref.get("first_paid_at") is None
    kind = "signup_reward" if is_first else "recurring"
    if kind == "signup_reward":
        commission = round(amount_paid * SIGNUP_REWARD_PCT, 2)
        await db.partner_referrals.update_one(
            {"id": ref["id"]},
            {"$set": {
                "first_paid_at": _now(),
                "status": "active",
                "signup_reward_amount_gbp": commission,
            }},
        )
    else:
        commission = float(RECURRING_GBP)
        await db.partner_referrals.update_one(
            {"id": ref["id"]},
            {"$set": {"last_recurring_at": _now(), "status": "active"},
             "$inc": {"recurring_total_paid_gbp": commission}},
        )

    ledger_doc = {
        "id": _new_id(),
        "partner_id": partner_id,
        "referral_id": ref["id"],
        "referred_organization_id": org["id"],
        "kind": kind,
        "amount_gbp": commission,
        "status": "accrued",  # awaits master-admin approval
        "source_invoice_id": invoice_id,
        "source_invoice_amount_paid_gbp": amount_paid,
        "created_at": _now(),
        "approved_by": None,
        "approved_at": None,
        "paid_at": None,
        "payout_id": None,
    }
    await db.partner_commission_ledger.insert_one(ledger_doc)
    await _recompute_app_fee(partner_id)
    await _audit(partner_id=partner_id, actor_id="system", action=f"accrue_{kind}",
                 after={"ledger_id": ledger_doc["id"], "amount_gbp": commission})
    return ledger_doc


# ───────────────────────── MASTER ADMIN endpoints ─────────────────────────


@router.get("/master-admin/partners")
async def admin_list_partners(
    status: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    q: dict = {}
    if status:
        q["status"] = status
    if level:
        q["level"] = level
    rows = await db.partner_engineers.find(q, {"_id": 0}).sort("created_at", -1).to_list(length=500)
    return {"partners": rows}


@router.get("/master-admin/partners/{partner_id}")
async def admin_get_partner(partner_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    partner = _public(await db.partner_engineers.find_one({"id": partner_id}))
    if not partner:
        raise HTTPException(404, "Partner not found")
    referrals = await db.partner_referrals.find(
        {"partner_id": partner_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=500)
    audit = await db.partner_audit_log.find(
        {"partner_id": partner_id}, {"_id": 0},
    ).sort("at", -1).limit(50).to_list(length=50)
    return {"partner": partner, "referrals": referrals, "audit": audit}


@router.post("/master-admin/partners/{partner_id}/approve")
async def admin_approve_partner(
    partner_id: str, body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    level = (body.get("level") or partner.get("level") or "engineer_partner").lower()
    if level not in PARTNER_LEVELS:
        raise HTTPException(400, f"level must be one of {sorted(PARTNER_LEVELS)}")
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {"status": "approved", "level": level, "approved_at": _now(),
                  "approved_by": user["id"], "rejected_reason": None, "updated_at": _now()}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action="approve",
                 before={"status": partner.get("status")}, after={"status": "approved", "level": level})
    return {"ok": True}


@router.post("/master-admin/partners/{partner_id}/reject")
async def admin_reject_partner(
    partner_id: str, body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    reason = (body.get("reason") or "").strip()[:500] or "Not approved"
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {"status": "rejected", "rejected_reason": reason,
                  "approved_at": None, "approved_by": None, "updated_at": _now()}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action="reject",
                 before={"status": partner.get("status")}, after={"status": "rejected", "reason": reason})
    return {"ok": True}


@router.post("/master-admin/partners/{partner_id}/suspend")
async def admin_suspend_partner(partner_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {"status": "suspended", "updated_at": _now()}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action="suspend",
                 before={"status": partner.get("status")}, after={"status": "suspended"})
    return {"ok": True}


@router.post("/master-admin/partners/{partner_id}/level")
async def admin_set_level(
    partner_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    level = (body.get("level") or "").lower()
    if level not in PARTNER_LEVELS:
        raise HTTPException(400, f"level must be one of {sorted(PARTNER_LEVELS)}")
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    await db.partner_engineers.update_one(
        {"id": partner_id}, {"$set": {"level": level, "updated_at": _now()}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action="set_level",
                 before={"level": partner.get("level")}, after={"level": level})
    return {"ok": True}


@router.post("/master-admin/partners/referrals/{referral_id}/flag-pre-existing")
async def admin_flag_referral_pre_existing(
    referral_id: str, body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Anti-abuse: master admin marks a referral as 'org was already in
    pipeline' → commission is suppressed going forward and any existing
    accrued (un-approved) rows are clawed back."""
    _require_master_admin(user)
    ref = await db.partner_referrals.find_one({"id": referral_id}, {"_id": 0})
    if not ref:
        raise HTTPException(404, "Referral not found")
    new_value = bool(body.get("pre_existing", True))
    await db.partner_referrals.update_one(
        {"id": referral_id}, {"$set": {"pre_existing_in_pipeline": new_value}},
    )
    if new_value:
        # Claw back any non-paid ledger rows for this referral.
        upd = await db.partner_commission_ledger.update_many(
            {"referral_id": referral_id, "status": {"$in": ["accrued", "approved"]}},
            {"$set": {"status": "clawed_back", "clawed_back_at": _now(),
                      "clawed_back_by": user["id"],
                      "clawed_back_reason": "Org already in GymAxis pipeline"}},
        )
        clawed = upd.modified_count
    else:
        clawed = 0
    await _audit(partner_id=ref["partner_id"], actor_id=user["id"], action="flag_pre_existing",
                 after={"referral_id": referral_id, "pre_existing": new_value, "clawed_back": clawed})
    return {"ok": True, "clawed_back": clawed}


@router.get("/master-admin/partners/commission/queue")
async def admin_commission_queue(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    rows = await db.partner_commission_ledger.find(
        {"status": "accrued"}, {"_id": 0},
    ).sort("created_at", 1).to_list(length=1000)
    # Enrich with partner name for the UI.
    partner_ids = list({r["partner_id"] for r in rows})
    partners = {p["id"]: p async for p in db.partner_engineers.find(
        {"id": {"$in": partner_ids}}, {"_id": 0, "id": 1, "full_name": 1, "company_name": 1, "email": 1},
    )}
    for r in rows:
        p = partners.get(r["partner_id"]) or {}
        r["partner_name"] = p.get("full_name")
        r["partner_email"] = p.get("email")
    total = round(sum(r["amount_gbp"] for r in rows), 2)
    return {"queue": rows, "total_gbp": total}


@router.post("/master-admin/partners/commission/{ledger_id}/approve")
async def admin_approve_commission(ledger_id: str, user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    row = await db.partner_commission_ledger.find_one({"id": ledger_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Ledger row not found")
    if row["status"] != "accrued":
        raise HTTPException(400, f"Cannot approve — current status is '{row['status']}'")
    await db.partner_commission_ledger.update_one(
        {"id": ledger_id},
        {"$set": {"status": "approved", "approved_at": _now(), "approved_by": user["id"]}},
    )
    await _audit(partner_id=row["partner_id"], actor_id=user["id"], action="approve_commission",
                 before={"status": "accrued"}, after={"status": "approved", "ledger_id": ledger_id})
    return {"ok": True}


@router.post("/master-admin/partners/commission/{ledger_id}/reject")
async def admin_reject_commission(
    ledger_id: str, body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    row = await db.partner_commission_ledger.find_one({"id": ledger_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Ledger row not found")
    if row["status"] not in ("accrued", "approved"):
        raise HTTPException(400, f"Cannot reject — current status is '{row['status']}'")
    reason = (body.get("reason") or "").strip()[:500] or "Not approved"
    await db.partner_commission_ledger.update_one(
        {"id": ledger_id},
        {"$set": {"status": "rejected", "rejected_reason": reason,
                  "rejected_at": _now(), "rejected_by": user["id"]}},
    )
    await _audit(partner_id=row["partner_id"], actor_id=user["id"], action="reject_commission",
                 after={"ledger_id": ledger_id, "reason": reason})
    return {"ok": True}


@router.post("/master-admin/partners/payouts/queue")
async def admin_queue_payout(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Bundle approved ledger rows for one partner into a payout batch.
    Body: {partner_id, method?: 'manual_csv'|'stripe_connect'}.
    Defaults to manual_csv (Phase 1). Stripe Connect is wired in Phase 2."""
    _require_master_admin(user)
    partner_id = body.get("partner_id")
    if not partner_id:
        raise HTTPException(400, "partner_id is required")
    method = (body.get("method") or "manual_csv").lower()
    if method not in PAYOUT_METHODS:
        raise HTTPException(400, f"method must be one of {sorted(PAYOUT_METHODS)}")

    approved = await db.partner_commission_ledger.find(
        {"partner_id": partner_id, "status": "approved"}, {"_id": 0},
    ).to_list(length=10_000)
    if not approved:
        raise HTTPException(400, "No approved commission rows for this partner")

    payout_id = _new_id()
    total = round(sum(r["amount_gbp"] for r in approved), 2)
    await db.partner_payouts.insert_one({
        "id": payout_id,
        "partner_id": partner_id,
        "method": method,
        "status": "queued",
        "total_gbp": total,
        "ledger_ids": [r["id"] for r in approved],
        "created_at": _now(),
        "created_by": user["id"],
        "csv_exported_at": None,
        "paid_at": None,
        "stripe_transfer_id": None,
    })
    await db.partner_commission_ledger.update_many(
        {"id": {"$in": [r["id"] for r in approved]}},
        {"$set": {"payout_id": payout_id}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action="queue_payout",
                 after={"payout_id": payout_id, "total_gbp": total, "method": method,
                        "ledger_count": len(approved)})
    return {"ok": True, "payout_id": payout_id, "total_gbp": total, "ledger_count": len(approved)}


@router.post("/master-admin/partners/payouts/{payout_id}/mark-paid")
async def admin_mark_payout_paid(
    payout_id: str, body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    payout = await db.partner_payouts.find_one({"id": payout_id}, {"_id": 0})
    if not payout:
        raise HTTPException(404, "Payout not found")
    if payout["status"] == "paid":
        return {"ok": True, "already_paid": True}
    reference = (body.get("reference") or "").strip()[:120]
    await db.partner_payouts.update_one(
        {"id": payout_id},
        {"$set": {"status": "paid", "paid_at": _now(), "payment_reference": reference}},
    )
    await db.partner_commission_ledger.update_many(
        {"payout_id": payout_id},
        {"$set": {"status": "paid", "paid_at": _now()}},
    )
    await _audit(partner_id=payout["partner_id"], actor_id=user["id"], action="mark_payout_paid",
                 after={"payout_id": payout_id, "reference": reference})
    return {"ok": True}


@router.get("/master-admin/partners/payouts/{payout_id}/csv")
async def admin_payout_csv(payout_id: str, user: dict = Depends(get_current_user)):
    """CSV export for the manual BACS batch — single payout."""
    _require_master_admin(user)
    payout = await db.partner_payouts.find_one({"id": payout_id}, {"_id": 0})
    if not payout:
        raise HTTPException(404, "Payout not found")
    partner = await db.partner_engineers.find_one({"id": payout["partner_id"]}, {"_id": 0}) or {}
    ledger = await db.partner_commission_ledger.find(
        {"payout_id": payout_id}, {"_id": 0},
    ).to_list(length=10_000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["payout_id", "partner_id", "partner_name", "partner_email",
                     "ledger_id", "kind", "amount_gbp", "referral_id",
                     "referred_organization_id", "source_invoice_id", "accrued_at"])
    for row in ledger:
        writer.writerow([
            payout_id,
            payout["partner_id"],
            partner.get("full_name") or "",
            partner.get("email") or "",
            row["id"], row["kind"], f"{row['amount_gbp']:.2f}",
            row.get("referral_id") or "", row.get("referred_organization_id") or "",
            row.get("source_invoice_id") or "", row.get("created_at") or "",
        ])
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", "", "", "",
                     f"{payout['total_gbp']:.2f}", "", "", "", ""])
    buf.seek(0)
    await db.partner_payouts.update_one(
        {"id": payout_id}, {"$set": {"csv_exported_at": _now()}},
    )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="partner-payout-{payout_id}.csv"'},
    )


@router.get("/master-admin/partners/reports/summary")
async def admin_reports_summary(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    total_partners = await db.partner_engineers.count_documents({})
    by_status = {}
    async for row in db.partner_engineers.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]):
        by_status[row["_id"] or "unknown"] = row["n"]
    by_level = {}
    async for row in db.partner_engineers.aggregate([
        {"$group": {"_id": "$level", "n": {"$sum": 1}}},
    ]):
        by_level[row["_id"] or "unknown"] = row["n"]
    referrals_total = await db.partner_referrals.count_documents({})
    referrals_active = await db.partner_referrals.count_documents({"status": "active"})
    commission_accrued = 0.0
    commission_approved = 0.0
    commission_paid = 0.0
    async for row in db.partner_commission_ledger.aggregate([
        {"$group": {"_id": "$status", "sum": {"$sum": "$amount_gbp"}}},
    ]):
        if row["_id"] == "accrued":
            commission_accrued = round(row["sum"], 2)
        elif row["_id"] == "approved":
            commission_approved = round(row["sum"], 2)
        elif row["_id"] == "paid":
            commission_paid = round(row["sum"], 2)
    return {
        "partners": {"total": total_partners, "by_status": by_status, "by_level": by_level},
        "referrals": {"total": referrals_total, "active": referrals_active},
        "commission": {
            "accrued_gbp": commission_accrued,
            "approved_gbp": commission_approved,
            "paid_gbp": commission_paid,
        },
    }


# ───────────────────────── ENGINEER APP ACCESS GUARD (iter 216h77) ─────────────────────────


ACTIVE_SUB_STATES = {"active", "trialing", "past_due"}  # past_due still has access; dunning fixes it


def _has_access_via_subscription(partner: dict) -> bool:
    sub = (partner or {}).get("subscription") or {}
    return sub.get("status") in ACTIVE_SUB_STATES


def _has_access_via_free_tier(partner: dict) -> bool:
    tier = (partner or {}).get("app_fee_tier") or {}
    return (tier.get("price_gbp") or 0) == 0


async def _has_access_via_grant(user_id: str) -> bool:
    grant = await db.partner_job_grants.find_one(
        {"engineer_user_id": user_id, "active": True}, {"_id": 1},
    )
    return grant is not None


async def evaluate_engineer_app_access(user: dict) -> dict:
    """Pure, side-effect-free reason resolver. Used by the frontend access
    landing page and the request-time guard. Returns:

        {
          allowed: bool,
          reason:  str,   # one of: active_subscription | free_tier |
                          # customer_grant | master_admin |
                          # internal_engineer |  # h86 — direct tenant employee
                          # needs_subscription | needs_application |
                          # application_pending | application_rejected |
                          # suspended
          partner: dict | None,
          subscription: dict,
          app_fee_tier: dict,
          active_grant_count: int,
        }
    """
    # Master admin always passes — they support engineers & need to test.
    if user.get("is_master_admin") or user.get("is_pulse_admin") or \
       user.get("role") == "pulse_master_admin":
        return {"allowed": True, "reason": "master_admin", "partner": None,
                "subscription": {}, "app_fee_tier": {}, "active_grant_count": 0}

    partner = await db.partner_engineers.find_one({"user_id": user["id"]}, {"_id": 0})
    grant_count = await db.partner_job_grants.count_documents(
        {"engineer_user_id": user["id"], "active": True},
    )

    # Iter 216h86 — Internal engineer bypass. Direct employees of a tenant
    # (Pulse Fitness, GymAxis customer orgs, etc.) get a `svc_engineers`
    # row created by their owner/manager. They are NOT independent
    # contractors and shouldn't be funnelled into the £30/mo Partner Plan.
    #
    # The bypass only applies when the user has NOT enrolled as a partner.
    # Enrolling as a partner is an opt-in choice — the rules of that
    # contract apply once you've signed up.
    if partner is None:
        internal_engineer = await db.svc_engineers.find_one(
            {"id": user["id"], "organization_id": user.get("organization_id"), "active": {"$ne": False}},
            {"_id": 0, "id": 1},
        )
        if internal_engineer is not None:
            return {"allowed": True, "reason": "internal_engineer", "partner": None,
                    "subscription": {}, "app_fee_tier": {}, "active_grant_count": grant_count}

    base = {
        "partner": partner,
        "subscription": (partner or {}).get("subscription") or {},
        "app_fee_tier": (partner or {}).get("app_fee_tier") or {},
        "active_grant_count": grant_count,
    }

    if grant_count > 0:
        # Customer-added engineers without a partner profile still get
        # job-specific access. This honours the h75 brief: "If a customer
        # adds an engineer only to complete jobs for that customer,
        # ensure the engineer can receive and complete assigned jobs."
        return {"allowed": True, "reason": "customer_grant", **base}

    if not partner:
        return {"allowed": False, "reason": "needs_application", **base}
    if partner["status"] == "pending":
        return {"allowed": False, "reason": "application_pending", **base}
    if partner["status"] == "rejected":
        return {"allowed": False, "reason": "application_rejected", **base}
    if partner["status"] == "suspended":
        return {"allowed": False, "reason": "suspended", **base}

    if _has_access_via_free_tier(partner):
        return {"allowed": True, "reason": "free_tier", **base}
    if _has_access_via_subscription(partner):
        return {"allowed": True, "reason": "active_subscription", **base}

    return {"allowed": False, "reason": "needs_subscription", **base}


async def require_engineer_app_access(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency wrapping `evaluate_engineer_app_access`. Raises
    a structured 402 (Payment Required) when access is denied so the
    frontend can route the engineer to the subscription page rather than
    silently bounce them to /login."""
    decision = await evaluate_engineer_app_access(user)
    if decision["allowed"]:
        return user
    raise HTTPException(
        status_code=402,
        detail={
            "code": "engineer_app_blocked",
            "reason": decision["reason"],
            "subscription_status": decision["subscription"].get("status"),
            "app_fee_tier_gbp": decision["app_fee_tier"].get("price_gbp"),
            "message": _BLOCK_MESSAGES.get(decision["reason"], "Engineer App access is restricted."),
        },
    )


_BLOCK_MESSAGES = {
    "needs_application":      "Apply to the Partner Engineer Network to start accepting jobs.",
    "application_pending":    "Your Partner Engineer application is under review. We'll email you within 2 working days.",
    "application_rejected":   "Your Partner Engineer application was not approved. Update your details and resubmit.",
    "suspended":              "Your Partner Engineer access has been suspended. Contact GymAxis support.",
    "needs_subscription":     "Start the £30/mo Partner Engineer Plan to unlock the Engineer App. Discounts kick in automatically at 5 active referrals.",
}


@router.get("/partners/me/engineer-access")
async def get_my_engineer_access(user: dict = Depends(get_current_user)):
    """Public-facing access status — used by the frontend gate landing page
    to render the correct CTA without 402'ing first."""
    decision = await evaluate_engineer_app_access(user)
    decision["partner"] = _public(decision["partner"])
    return decision


# ───────────────────────── CUSTOMER-ADDED ENGINEER GRANTS ─────────────────────────


@router.get("/customer-engineer-grants")
async def list_customer_grants(user: dict = Depends(get_current_user)):
    """List all engineer grants this customer has issued."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organization context required")
    rows = await db.partner_job_grants.find(
        {"granted_by_organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=500)
    return {"grants": rows}


@router.post("/customer-engineer-grants")
async def create_customer_grant(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Customer grants an engineer access to specific jobs/cases without
    forcing them to subscribe. This is the "customer-added engineer"
    onboarding path."""
    _require_gymaxis_only(user)
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organization context required")
    engineer_email = (body.get("engineer_email") or "").strip().lower()
    if not engineer_email:
        raise HTTPException(400, "engineer_email is required")
    case_ids = body.get("case_ids") or []
    if not isinstance(case_ids, list):
        raise HTTPException(400, "case_ids must be a list")

    # Look up the engineer user (must already have a GymAxis account).
    eng_user = await db.users.find_one({"email": engineer_email}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if not eng_user:
        raise HTTPException(404, f"No GymAxis user with email '{engineer_email}'. Ask them to sign up first.")

    grant_id = _new_id()
    doc = {
        "id": grant_id,
        "engineer_user_id": eng_user["id"],
        "engineer_email": engineer_email,
        "engineer_name": eng_user.get("full_name"),
        "granted_by_organization_id": org_id,
        "granted_by_user_id": user["id"],
        "case_ids": [str(c) for c in case_ids][:200],
        "scope": (body.get("scope") or "per_case").lower(),  # per_case | org_wide
        "note": (body.get("note") or "").strip()[:500],
        "active": True,
        "created_at": _now(),
        "revoked_at": None,
        "revoked_by": None,
    }
    await db.partner_job_grants.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "grant": doc}


@router.delete("/customer-engineer-grants/{grant_id}")
async def revoke_customer_grant(grant_id: str, user: dict = Depends(get_current_user)):
    org_id = user.get("organization_id")
    grant = await db.partner_job_grants.find_one(
        {"id": grant_id, "granted_by_organization_id": org_id}, {"_id": 0},
    )
    if not grant:
        raise HTTPException(404, "Grant not found")
    await db.partner_job_grants.update_one(
        {"id": grant_id},
        {"$set": {"active": False, "revoked_at": _now(), "revoked_by": user["id"]}},
    )
    return {"ok": True}


# ─── End of iter 216h77 additions ───


# ───────────────────────── PARTNER PERFORMANCE SCORING (iter 216h79) ─────────────────────────


SCORE_WEIGHTS = {
    "sla":        0.40,
    "completion": 0.30,
    "volume":     0.20,
    "csat":       0.10,
}
# Volume normalisation — 50 closed jobs in the window = full marks. This
# is intentionally generous: partners who close 50+ jobs/quarter are at
# the top of the volume curve.
VOLUME_FULL_MARK = 50
# Minimum closed jobs before we'll publish a score — avoids over-weighting
# a partner who has done one perfect job.
MIN_CLOSED_FOR_SCORE = 5
# Score → reliability tier (these inform level-up RECOMMENDATIONS only;
# Master Admin still has to manually approve the level change).
SCORE_TIERS = [
    (90, "top_tier",          "Top-tier",          "strategic_partner"),
    (75, "strong",            "Strong",            "verified_partner"),
    (60, "solid",             "Solid",             "engineer_partner"),
    (0,  "needs_improvement", "Needs improvement", None),
]


def _classify_score(score: float, closed_count: int) -> dict:
    if closed_count < MIN_CLOSED_FOR_SCORE:
        return {
            "tier": "insufficient_data",
            "tier_label": "Insufficient data",
            "recommended_level": None,
            "rationale": f"Need {MIN_CLOSED_FOR_SCORE - closed_count} more closed jobs in the window before we can publish a score.",
        }
    for threshold, tier, label, level in SCORE_TIERS:
        if score >= threshold:
            return {"tier": tier, "tier_label": label, "recommended_level": level,
                    "rationale": None}
    return {"tier": "needs_improvement", "tier_label": "Needs improvement",
            "recommended_level": None, "rationale": None}


async def compute_partner_performance(partner_id: str, window_days: int = 90) -> dict:
    """Pure read-only scoring over the partner's `user_id`'s closed cases
    in the last `window_days`. Returns a dict the Master Admin UI can
    render directly.

    Components:
      • sla_compliance — closed_within_sla / closed_total
      • completion_rate — closed / (closed + cancelled + rejected) in window
      • volume         — closed_total / VOLUME_FULL_MARK (capped 1.0)
      • csat           — avg customer_rating / 5.0 (neutral 0.8 if no ratings)

    Each is normalised to [0, 1], weighted, and summed → 0-100.
    """
    from datetime import timedelta  # local import — keeps cold-path clean
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0, "user_id": 1, "level": 1})
    if not partner:
        raise HTTPException(404, "Partner not found")
    user_id = partner["user_id"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()

    closed_cur = db.svc_cases.find(
        {
            "assigned_engineer_id": user_id,
            "status": {"$in": ["closed", "invoiced"]},
            "closed_at": {"$gte": cutoff},
        },
        {"_id": 0, "closed_at": 1, "sla_resolve_at": 1, "customer_rating": 1, "priority": 1},
    )
    closed = await closed_cur.to_list(length=10_000)
    cancelled_count = await db.svc_cases.count_documents({
        "assigned_engineer_id": user_id,
        "status": {"$in": ["cancelled", "rejected"]},
        "updated_at": {"$gte": cutoff},
    })

    closed_total = len(closed)
    if closed_total == 0:
        # Fully empty window — return zeros so the UI knows.
        return {
            "partner_id": partner_id,
            "window_days": window_days,
            "score": 0,
            "components": {"sla_compliance": 0, "completion_rate": 0, "volume": 0, "csat": 0},
            "counts": {"closed": 0, "closed_within_sla": 0, "cancelled": cancelled_count,
                       "rated": 0, "avg_rating": None},
            **_classify_score(0, 0),
        }

    closed_within_sla = sum(
        1 for c in closed
        if c.get("closed_at") and c.get("sla_resolve_at")
        and c["closed_at"] <= c["sla_resolve_at"]
    )
    sla_compliance = closed_within_sla / closed_total

    total_attempted = closed_total + cancelled_count
    completion_rate = (closed_total / total_attempted) if total_attempted else 1.0

    volume = min(1.0, closed_total / VOLUME_FULL_MARK)

    rated = [c for c in closed if isinstance(c.get("customer_rating"), (int, float))]
    if rated:
        avg_rating = sum(c["customer_rating"] for c in rated) / len(rated)
        csat = max(0.0, min(1.0, avg_rating / 5.0))
    else:
        avg_rating = None
        # Neutral default — don't penalise partners who have closed jobs
        # in a system where rating capture isn't widespread yet.
        csat = 0.8

    score_raw = (
        SCORE_WEIGHTS["sla"]        * sla_compliance
        + SCORE_WEIGHTS["completion"] * completion_rate
        + SCORE_WEIGHTS["volume"]     * volume
        + SCORE_WEIGHTS["csat"]       * csat
    )
    score = round(score_raw * 100, 1)

    return {
        "partner_id": partner_id,
        "window_days": window_days,
        "score": score,
        "components": {
            "sla_compliance":   round(sla_compliance, 3),
            "completion_rate":  round(completion_rate, 3),
            "volume":           round(volume, 3),
            "csat":             round(csat, 3),
        },
        "counts": {
            "closed":            closed_total,
            "closed_within_sla": closed_within_sla,
            "cancelled":         cancelled_count,
            "rated":             len(rated),
            "avg_rating":        round(avg_rating, 2) if avg_rating is not None else None,
        },
        **_classify_score(score, closed_total),
    }


@router.get("/master-admin/partners/{partner_id}/performance")
async def admin_partner_performance(
    partner_id: str,
    window_days: int = Query(90, ge=7, le=365),
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    return await compute_partner_performance(partner_id, window_days=window_days)


@router.get("/master-admin/partners/performance/leaderboard")
async def admin_partners_leaderboard(
    window_days: int = Query(90, ge=7, le=365),
    user: dict = Depends(get_current_user),
):
    """Returns every approved partner scored over the same window — used
    by the Master Admin Partner Engineers panel to surface the score
    column without N round-trips. Top-tier partners appear first."""
    _require_master_admin(user)
    partners = await db.partner_engineers.find(
        {"status": "approved"}, {"_id": 0, "id": 1, "full_name": 1, "company_name": 1,
                                  "level": 1, "email": 1, "active_referral_count": 1},
    ).to_list(length=1000)
    rows = []
    for p in partners:
        perf = await compute_partner_performance(p["id"], window_days=window_days)
        rows.append({**p, "performance": perf})
    # Sort: insufficient_data at the bottom, then by score desc.
    rows.sort(key=lambda r: (r["performance"]["tier"] == "insufficient_data",
                              -r["performance"]["score"]))
    return {"window_days": window_days, "partners": rows}


# ─── End of iter 216h79 additions ───


# ───────────────────────── PUBLIC "FIND AN ENGINEER" WIDGET (iter 216h80) ─────────────────────────


# Quick & deterministic postcode prefix matcher. Live geocoding can
# come in a later iter — for MVP we match on the first 2-4 chars of
# the UK outcode (e.g. "SW1A" matches "SW1A", "SW1", "SW") which is
# good enough for "engineers within the same broad area".


def _outcode(postcode: str) -> str:
    """Return the UK outcode (chars before the space, e.g. 'SW1A' from
    'SW1A 1AA'). Uppercased & whitespace-stripped."""
    if not postcode:
        return ""
    pc = re.sub(r"\s+", " ", postcode.strip().upper())
    return pc.split(" ", 1)[0] if " " in pc else pc[:4]


def _postcode_match(engineer_pc: str, customer_pc: str) -> bool:
    """Loose match on the outcode prefix — engineer covers customer if
    they share any leading character sequence of >=2 chars, OR the
    engineer's `travel_radius_km` is generous (≥75km counts as
    nationwide for MVP)."""
    a = _outcode(engineer_pc)
    b = _outcode(customer_pc)
    if not a or not b:
        return False
    # Same outcode prefix (≥2 chars) → match
    for n in (4, 3, 2):
        if a[:n] == b[:n]:
            return True
    return False


@router.get("/partners/find-engineers")
async def find_engineers(
    postcode: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Return verified / strategic Partner Engineers within reach of the
    customer's postcode. GymAxis-only — Pulse users get 403.

    Surface limited fields only (NO email, phone, commercial data).
    """
    _require_gymaxis_only(user)
    # Also block if the user's own org is Pulse — guards customer-by-org.
    if user.get("organization_id"):
        if await _is_pulse_org(user["organization_id"]):
            raise HTTPException(403, "The Partner Engineer Network is exclusive to GymAxis customers.")

    customer_pc = _validate_postcode(postcode)
    cur = db.partner_engineers.find(
        {"status": "approved", "level": {"$in": ["verified_partner", "strategic_partner"]}},
        {"_id": 0, "id": 1, "full_name": 1, "company_name": 1, "level": 1,
         "service_postcode": 1, "travel_radius_km": 1, "brands_supported": 1,
         "skills": 1, "qualifications": 1, "active_referral_count": 1},
    )
    rows = await cur.to_list(length=500)

    # Score by postcode match + travel-radius generosity.
    matched = []
    nationwide = []
    for r in rows:
        eng_pc = r.get("service_postcode") or ""
        radius = r.get("travel_radius_km") or 25
        if _postcode_match(eng_pc, customer_pc):
            matched.append(r)
        elif radius >= 75:
            nationwide.append(r)

    # Pull in live performance scores so customers see the strongest first.
    scored = []
    for r in matched + nationwide:
        try:
            perf = await compute_partner_performance(r["id"], window_days=90)
        except Exception:
            perf = {"score": 0, "tier": "insufficient_data"}
        scored.append({
            "id": r["id"],
            "full_name": r["full_name"],
            "company_name": r.get("company_name"),
            "level": r["level"],
            "service_postcode_area": _outcode(r.get("service_postcode") or ""),
            "travel_radius_km": r.get("travel_radius_km"),
            "brands_supported": r.get("brands_supported") or [],
            "skills": r.get("skills") or [],
            "qualifications": r.get("qualifications") or [],
            "score":  perf.get("score", 0),
            "tier":   perf.get("tier"),
            "rating": (perf.get("counts") or {}).get("avg_rating"),
            "jobs_completed_90d": (perf.get("counts") or {}).get("closed", 0),
            "in_area":  r in matched,
        })
    # Top-tier + strategic always rank above verified; within tier, score desc.
    scored.sort(key=lambda x: (
        not x["in_area"],                            # in-area first
        x["level"] != "strategic_partner",           # strategic ranks above verified
        -(x["score"] or 0),
    ))
    return {"postcode": customer_pc, "engineers": scored, "in_area_count": len(matched)}


@router.post("/partners/find-engineers/{partner_id}/request-contact")
async def request_engineer_contact(
    partner_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """A customer expresses interest in an engineer. We DON'T leak the
    engineer's email; instead we create a `partner_contact_requests` row
    and (P2) notify the engineer via Resend. The engineer can then
    accept the lead from their dashboard."""
    _require_gymaxis_only(user)
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organization context required")
    if await _is_pulse_org(org_id):
        raise HTTPException(403, "GymAxis-only programme")
    partner = await db.partner_engineers.find_one(
        {"id": partner_id, "status": "approved",
         "level": {"$in": ["verified_partner", "strategic_partner"]}},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1},
    )
    if not partner:
        raise HTTPException(404, "Engineer is not available")
    req = {
        "id": _new_id(),
        "partner_id": partner_id,
        "requested_by_organization_id": org_id,
        "requested_by_user_id": user["id"],
        "requested_by_user_email": user.get("email"),
        "note": (body.get("note") or "").strip()[:1000],
        "status": "new",
        "created_at": _now(),
    }
    await db.partner_contact_requests.insert_one(req)
    req.pop("_id", None)
    return {"ok": True, "request": req}


# ─── End of iter 216h80 additions ───


# ───────────────────────── indexes (called from server startup) ─────────────────────────


async def ensure_partner_indexes() -> None:
    await db.partner_engineers.create_index([("user_id", 1)], unique=True)
    await db.partner_engineers.create_index([("referral_code", 1)], unique=True)
    await db.partner_engineers.create_index([("status", 1)])
    await db.partner_referrals.create_index([("partner_id", 1), ("created_at", -1)])
    await db.partner_referrals.create_index([("referred_organization_id", 1)], unique=True)
    await db.partner_commission_ledger.create_index([("partner_id", 1), ("status", 1)])
    await db.partner_commission_ledger.create_index(
        [("source_invoice_id", 1)],
        unique=True,
        partialFilterExpression={"source_invoice_id": {"$type": "string"}},
    )
    await db.partner_payouts.create_index([("partner_id", 1), ("status", 1)])
    await db.partner_audit_log.create_index([("partner_id", 1), ("at", -1)])
    # Iter 216h77 — customer-added engineer grants
    await db.partner_job_grants.create_index([("engineer_user_id", 1), ("active", 1)])
    await db.partner_job_grants.create_index([("granted_by_organization_id", 1), ("created_at", -1)])
    # Iter 216h80 — find-engineers widget
    await db.partner_contact_requests.create_index([("partner_id", 1), ("created_at", -1)])
    await db.partner_contact_requests.create_index([("requested_by_organization_id", 1), ("created_at", -1)])
