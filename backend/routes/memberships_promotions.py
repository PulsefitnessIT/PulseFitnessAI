"""GymAxis Memberships — Promo codes / discount engine.

Operator-managed promo codes that members can paste at Stripe Checkout to
discount a plan, pack, course, drop-in or bundle. Built on top of Stripe's
native Coupon + PromotionCode objects so the discount is enforced by Stripe
itself (no race conditions, no double-spend).

Code layout
───────────
  promo_codes               — operator-defined codes (collection)
    { id, organization_id, code, name, kind, percent_off, amount_off_pence,
      first_time_only, max_redemptions, redemptions_count, valid_until,
      applicable_plan_ids, applicable_kinds, stripe_coupon_id,
      stripe_promotion_code_id, archived, created_at, updated_at }

  promo_code_redemptions    — audit trail (one row per checkout that used a
                              promo). Lets us power 'first_time_only' rules
                              and a redemptions report later.

Endpoints
─────────
  GET    /api/memberships/promo-codes
  POST   /api/memberships/promo-codes
  PATCH  /api/memberships/promo-codes/{id}
  DELETE /api/memberships/promo-codes/{id}
  POST   /api/memberships/promo-codes/validate
  GET    /api/memberships/promo-codes/{id}/redemptions
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import STRIPE_API_KEY, db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-promotions"])
stripe.api_key = STRIPE_API_KEY
# Pin API version so Coupon/PromotionCode shape matches our usage. Some
# accounts default to a pre-2018 API where PromotionCode doesn't accept
# `coupon` — pinning here avoids that.
stripe.api_version = "2024-06-20"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "", (code or "").upper().strip())[:32]


# ───────────────────────── Models ─────────────────────────


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    """Member-facing token, e.g. 'SUMMER25'. Auto-uppercased & cleaned."""

    name: str
    """Internal label for the operator's reference (e.g. 'Summer launch — 25% off')."""

    percent_off: int | None = Field(default=None, ge=1, le=100)
    amount_off_pence: int | None = Field(default=None, ge=1)
    """Either percent_off OR amount_off_pence — exactly one required."""

    first_time_only: bool = False
    """If true, a member who already has a paid membership cannot use this code."""

    max_redemptions: int | None = Field(default=None, ge=1)
    """Optional global cap on uses across the org."""

    valid_until: str | None = None
    """Optional ISO8601 expiry; absent = never expires."""

    applicable_plan_ids: list[str] | None = None
    """When set, only these plan ids accept the code; null = all plans."""

    applicable_kinds: list[str] | None = None
    """When set, only plans whose kind ∈ this list accept the code; null = all kinds.
    Useful for 'first month free on subscriptions only' style codes."""

    duration: str = "once"
    """Stripe coupon duration semantics: 'once' (default — applies to first
    invoice only — the canonical 'first month free' pattern), 'forever'
    (every invoice forever), or 'repeating' (N months — set duration_in_months).
    Class-pack/course/drop-in (one-off) charges always behave as 'once' regardless."""

    duration_in_months: int | None = Field(default=None, ge=1, le=24)


# ───────────────────────── Helpers ─────────────────────────


async def _provision_stripe_objects(org_id: str, payload: dict) -> tuple[str, str]:
    """Create the Stripe Coupon + PromotionCode so the code is enforced by
    Stripe itself at checkout. Returns (coupon_id, promotion_code_id)."""
    coupon_kwargs: dict = {
        "duration": payload["duration"],
        "metadata": {"organization_id": org_id, "gymaxis_kind": "promo"},
    }
    if payload["duration"] == "repeating":
        if not payload.get("duration_in_months"):
            raise HTTPException(
                400, "duration='repeating' requires duration_in_months",
            )
        coupon_kwargs["duration_in_months"] = int(payload["duration_in_months"])
    if payload.get("percent_off"):
        coupon_kwargs["percent_off"] = float(payload["percent_off"])
    elif payload.get("amount_off_pence"):
        coupon_kwargs["amount_off"] = int(payload["amount_off_pence"])
        coupon_kwargs["currency"] = "gbp"
    else:
        raise HTTPException(400, "percent_off or amount_off_pence required")
    if payload.get("max_redemptions"):
        coupon_kwargs["max_redemptions"] = int(payload["max_redemptions"])
    if payload.get("valid_until"):
        try:
            ts = datetime.fromisoformat(
                str(payload["valid_until"]).replace("Z", "+00:00"),
            )
            coupon_kwargs["redeem_by"] = int(ts.timestamp())
        except Exception as exc:
            raise HTTPException(400, f"Invalid valid_until: {exc}") from exc
    coupon = stripe.Coupon.create(**coupon_kwargs)

    promo_kwargs: dict = {
        "coupon": coupon.id,
        "code": payload["code"],
        "metadata": {"organization_id": org_id, "gymaxis_kind": "promo"},
    }
    if payload.get("max_redemptions"):
        promo_kwargs["max_redemptions"] = int(payload["max_redemptions"])
    if payload.get("valid_until"):
        try:
            ts = datetime.fromisoformat(
                str(payload["valid_until"]).replace("Z", "+00:00"),
            )
            promo_kwargs["expires_at"] = int(ts.timestamp())
        except Exception:
            pass  # already validated above
    if payload.get("first_time_only"):
        promo_kwargs["restrictions"] = {"first_time_transaction": True}
    promotion_code = stripe.PromotionCode.create(**promo_kwargs)
    return coupon.id, promotion_code.id


# ───────────────────────── Endpoints ─────────────────────────


@router.get(
    "/memberships/promo-codes",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_list(
    include_archived: bool = False,
    user: dict = Depends(get_current_user),
):
    """All promo codes for this org. Newest first."""
    org_id = await _require_operator_org(user)
    q: dict = {"organization_id": org_id}
    if not include_archived:
        q["archived"] = {"$ne": True}
    rows = await db.promo_codes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"promo_codes": rows, "count": len(rows)}


@router.post(
    "/memberships/promo-codes",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_create(body: PromoIn, user: dict = Depends(get_current_user)):
    """Create a promo code. Provisions the Stripe Coupon + PromotionCode
    so the discount is enforced server-side at checkout."""
    org_id = await _require_operator_org(user)
    if not (body.percent_off or body.amount_off_pence):
        raise HTTPException(400, "percent_off or amount_off_pence required")
    if body.percent_off and body.amount_off_pence:
        raise HTTPException(
            400, "Specify either percent_off OR amount_off_pence, not both",
        )

    code = _normalise_code(body.code)
    if not code:
        raise HTTPException(400, "Code must contain at least 3 alphanumerics")

    # Per-org uniqueness — Stripe also enforces global uniqueness on
    # promotion code names so we prefix our org id when collision detected.
    existing = await db.promo_codes.find_one(
        {"organization_id": org_id, "code": code, "archived": {"$ne": True}},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(409, f"Promo code '{code}' already exists")

    payload = body.model_dump()
    payload["code"] = code

    if not STRIPE_API_KEY:
        raise HTTPException(
            503, "Stripe is not configured — cannot provision the promo code",
        )
    try:
        coupon_id, promo_id = await _provision_stripe_objects(org_id, payload)
    except stripe.StripeError as exc:
        # Stripe global uniqueness conflict — suffix with the org id and retry once
        if getattr(exc, "code", "") == "code_already_exists":
            payload["code"] = f"{code}-{org_id[:6].upper()}"
            try:
                coupon_id, promo_id = await _provision_stripe_objects(org_id, payload)
            except stripe.StripeError as exc2:
                raise HTTPException(400, f"Stripe error: {exc2}") from exc2
        else:
            raise HTTPException(400, f"Stripe error: {exc}") from exc

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "created_by": user.get("id"),
        "created_at": _now_iso(),
        "redemptions_count": 0,
        "stripe_coupon_id": coupon_id,
        "stripe_promotion_code_id": promo_id,
        "archived": False,
        **payload,
    }
    await db.promo_codes.insert_one(doc)
    return {"promo_code": {k: v for k, v in doc.items() if k != "_id"}}


@router.patch(
    "/memberships/promo-codes/{promo_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_update(
    promo_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Update editable, non-Stripe-locked fields. The Stripe coupon is
    immutable in core terms — to change discount amount, archive and
    create a new code."""
    org_id = await _require_operator_org(user)
    allowed = {"name", "applicable_plan_ids", "applicable_kinds",
               "first_time_only", "active"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No allowed fields supplied")
    update["updated_at"] = _now_iso()
    res = await db.promo_codes.update_one(
        {"id": promo_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Promo code not found")
    return {"ok": True, "updated": list(update.keys())}


@router.delete(
    "/memberships/promo-codes/{promo_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_archive(
    promo_id: str, user: dict = Depends(get_current_user),
):
    """Archive a promo. Existing redemptions remain; future checkouts
    cannot use the code. Stripe-side we deactivate the PromotionCode so
    the code stops working everywhere."""
    org_id = await _require_operator_org(user)
    promo = await db.promo_codes.find_one(
        {"id": promo_id, "organization_id": org_id}, {"_id": 0},
    )
    if not promo:
        raise HTTPException(404, "Promo code not found")
    if promo.get("stripe_promotion_code_id"):
        try:
            stripe.PromotionCode.modify(
                promo["stripe_promotion_code_id"], active=False,
            )
        except Exception as exc:  # pragma: no cover
            logger.info("[promo] stripe deactivate failed: %s", exc)
    await db.promo_codes.update_one(
        {"id": promo_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now_iso()}},
    )
    return {"ok": True}


@router.post(
    "/memberships/promo-codes/validate",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_validate(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Validate a member-supplied code against an org + plan BEFORE we
    initiate the Stripe Checkout. Returns the discount preview so the
    member can see the new total in the UI before paying."""
    org_id = await _require_operator_org(user)
    code = _normalise_code(body.get("code") or "")
    plan_id = body.get("plan_id")
    member_id = body.get("member_id")
    if not code:
        raise HTTPException(400, "code is required")
    if not plan_id:
        raise HTTPException(400, "plan_id is required")

    return await _validate_for_checkout(
        org_id=org_id, code=code, plan_id=plan_id, member_id=member_id,
    )


@router.get(
    "/memberships/promo-codes/{promo_id}/redemptions",
    dependencies=[Depends(require_module("memberships"))],
)
async def promo_redemptions(
    promo_id: str, user: dict = Depends(get_current_user),
):
    """All redemptions for one promo. Powers the operator analytics."""
    org_id = await _require_operator_org(user)
    promo = await db.promo_codes.find_one(
        {"id": promo_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if not promo:
        raise HTTPException(404, "Promo code not found")
    rows = await db.promo_code_redemptions.find(
        {"promo_id": promo_id, "organization_id": org_id}, {"_id": 0},
    ).sort("redeemed_at", -1).to_list(500)
    return {"redemptions": rows, "count": len(rows)}


# ───────────────────────── Checkout integration helpers ─────────────────────────


async def _validate_for_checkout(
    *, org_id: str, code: str, plan_id: str, member_id: Optional[str],
) -> dict:
    """Shared validator used both by `promo_validate` (manual UI check)
    and the checkout endpoint when applying a code at purchase time.

    Returns: { promo_id, code, percent_off?, amount_off_pence?,
               original_pence, discounted_pence, savings_pence,
               stripe_promotion_code_id }
    Raises HTTPException(400) with a member-friendly reason on any failure.
    """
    code_norm = _normalise_code(code)
    promo = await db.promo_codes.find_one(
        {"organization_id": org_id, "code": code_norm, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not promo:
        raise HTTPException(400, "Invalid promo code")

    # Validity window
    if promo.get("valid_until"):
        try:
            ts = datetime.fromisoformat(
                str(promo["valid_until"]).replace("Z", "+00:00"),
            )
            if ts < datetime.now(timezone.utc):
                raise HTTPException(400, "This promo code has expired")
        except HTTPException:
            raise
        except Exception:
            pass

    # Global cap
    if promo.get("max_redemptions") is not None and \
            int(promo.get("redemptions_count") or 0) >= int(promo["max_redemptions"]):
        raise HTTPException(400, "This promo code has reached its redemption limit")

    # Plan + kind eligibility
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    applicable = promo.get("applicable_plan_ids") or []
    if applicable and plan_id not in applicable:
        raise HTTPException(400, "This promo code does not apply to this plan")
    kinds = promo.get("applicable_kinds") or []
    if kinds and plan.get("kind") not in kinds:
        raise HTTPException(400, "This promo code does not apply to this plan type")

    # First-time-only
    if promo.get("first_time_only") and member_id:
        prior_paid = await db.member_memberships.find_one(
            {"member_id": member_id, "organization_id": org_id,
             "billing_status": {"$in": ["current", "past_due", "cancelled_future"]}},
            {"_id": 0, "id": 1},
        )
        if prior_paid:
            raise HTTPException(
                400, "This code is for first-time members only — your account already has a paid membership history",
            )

    # Compute preview
    price = int(plan.get("price_pence") or 0)
    if promo.get("percent_off"):
        savings = int(round(price * (int(promo["percent_off"]) / 100.0)))
    else:
        savings = min(int(promo.get("amount_off_pence") or 0), price)
    discounted = max(price - savings, 0)

    return {
        "promo_id": promo["id"],
        "code": promo["code"],
        "name": promo.get("name"),
        "percent_off": promo.get("percent_off"),
        "amount_off_pence": promo.get("amount_off_pence"),
        "original_pence": price,
        "discounted_pence": discounted,
        "savings_pence": savings,
        "stripe_promotion_code_id": promo.get("stripe_promotion_code_id"),
        "duration": promo.get("duration", "once"),
    }


async def record_promo_redemption(
    *, promo_id: str, organization_id: str, member_id: str,
    plan_id: str, session_id: str, savings_pence: int,
) -> None:
    """Insert a redemption row + bump the parent promo's redemptions_count.
    Called from the Stripe webhook on successful checkout."""
    await db.promo_code_redemptions.insert_one({
        "id": str(uuid.uuid4()),
        "promo_id": promo_id,
        "organization_id": organization_id,
        "member_id": member_id,
        "plan_id": plan_id,
        "stripe_session_id": session_id,
        "savings_pence": savings_pence,
        "redeemed_at": _now_iso(),
    })
    await db.promo_codes.update_one(
        {"id": promo_id}, {"$inc": {"redemptions_count": 1}},
    )


__all__ = ["router", "_validate_for_checkout", "record_promo_redemption"]
