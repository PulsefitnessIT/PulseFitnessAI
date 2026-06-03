"""GymAxis Memberships — Operator onboarding + Member-app branding + Ads.

Scope:
  • Setup wizard: /memberships/setup/*  (org-level state machine)
  • Record payment: operator-initiated manual payment logging (replaces
    the old Stripe-collect-from-member flow — GymAxis does NOT
    intermediate gym→member money).
  • Public white-label app: /m/{slug}  (member portal served with the
    gym's branding via GET /m/{slug}/branding).
  • Ads: per-gym ad placements surfaced in the member app's book feed.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-ops"])

_PAYMENT_METHODS = {"manual", "direct_debit", "stripe_connect"}
_RECORD_PAY_METHODS = {"cash", "card_terminal", "bank_transfer", "direct_debit", "invoice", "comp"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return base or f"gym-{uuid.uuid4().hex[:6]}"


# ═════════════════════ Setup wizard ═════════════════════

@router.get("/memberships/setup/status")
async def setup_status(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    plan_count = await db.membership_plans.count_documents(
        {"organization_id": org_id, "archived": {"$ne": True}})
    template_count = await db.class_templates.count_documents(
        {"organization_id": org_id, "archived": {"$ne": True}})
    instructor_count = await db.users.count_documents(
        {"organization_id": org_id, "is_instructor": True})
    return {
        "organization": {k: org.get(k) for k in (
            "id", "name", "slug", "logo_url", "primary_brand_colour",
            "currency", "timezone", "payment_method", "setup_completed",
            "setup_step",
            # Iter 216h252 — surface address + contact so the redesigned
            # Step 1 can pre-populate from data captured at trial-signup.
            "address_line1", "address_line2", "city", "postcode", "country",
            "contact_email", "contact_phone",
        )},
        "counts": {"plans": plan_count, "class_templates": template_count, "instructors": instructor_count},
    }


class BasicsBody(BaseModel):
    name: str
    timezone: str = "Europe/London"
    currency: str = "GBP"
    primary_brand_colour: str = "#19CDFF"
    logo_url: str | None = None
    slug: str | None = None  # operator can override auto-slug
    # Iter 216h252 — wizard now captures studio address + contact in
    # Step 1 so the operator doesn't have to hunt them down in the
    # admin console after onboarding.
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postcode: str | None = None
    country: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


@router.get("/memberships/setup/check-slug")
async def setup_check_slug(slug: str, user: dict = Depends(get_current_user)):
    """Iter 216h252 — live "is this app address taken?" check for the
    Step 1 input. Returns availability + a tweaked suggestion if the
    given slug clashes with another org. Empty/garbage input returns
    `available: False` so the UI can dim the Save button.
    """
    org_id = await _require_operator_org(user)
    cleaned = _slugify(slug or "")
    if not cleaned or len(cleaned) < 3:
        return {"available": False, "slug": cleaned, "reason": "too_short"}
    conflict = await db.organizations.find_one(
        {"slug": cleaned, "id": {"$ne": org_id}}, {"_id": 0, "id": 1},
    )
    if conflict:
        suggestion = f"{cleaned}-{uuid.uuid4().hex[:4]}"
        return {"available": False, "slug": cleaned, "suggestion": suggestion, "reason": "taken"}
    return {"available": True, "slug": cleaned}


@router.post("/memberships/setup/basics")
async def setup_basics(body: BasicsBody, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    slug = _slugify(body.slug or body.name)
    # Ensure slug uniqueness org-wide
    conflict = await db.organizations.find_one(
        {"slug": slug, "id": {"$ne": org_id}}, {"_id": 0, "id": 1})
    if conflict:
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"
    # Iter 216h252 — persist the optional address + contact captured in
    # the redesigned Step 1. Only $set fields the operator provided so
    # we never overwrite values already entered via other surfaces.
    update: dict = {
        "name": body.name, "slug": slug, "membership_app_slug": slug,
        "timezone": body.timezone,
        "currency": body.currency, "primary_brand_colour": body.primary_brand_colour,
        "logo_url": body.logo_url, "setup_step": "payment",
    }
    for key in (
        "address_line1", "address_line2", "city", "postcode", "country",
        "contact_email", "contact_phone",
    ):
        value = getattr(body, key, None)
        if value is not None:
            update[key] = (value or "").strip()
    await db.organizations.update_one({"id": org_id}, {"$set": update})
    return {"ok": True, "slug": slug}


class PaymentMethodBody(BaseModel):
    payment_method: Literal["manual", "direct_debit", "stripe_connect"]


@router.post("/memberships/setup/payment-method")
async def setup_payment_method(body: PaymentMethodBody, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if body.payment_method != "manual":
        # We don't have wires for DD/Connect yet — flag the choice so the
        # operator can come back to it, but fall through to manual for now.
        logger.info(f"[setup] {org_id} requested {body.payment_method} — deferred, using manual for now")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"payment_method": body.payment_method, "setup_step": "plans"}},
    )
    return {"ok": True, "payment_method": body.payment_method,
            "note": "DD / Stripe Connect coming soon — using manual for now" if body.payment_method != "manual" else None}


class StarterPlansBody(BaseModel):
    plans: list[dict] = Field(default_factory=list)  # [{name, kind, billing_cycle, price_pence, ...}]


@router.post("/memberships/setup/plans")
async def setup_plans(body: StarterPlansBody, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    created_ids: list[str] = []
    for p in body.plans:
        plan_id = str(uuid.uuid4())
        doc = {
            "id": plan_id, "organization_id": org_id,
            "name": p.get("name") or "Plan",
            "kind": p.get("kind") or "recurring",
            "billing_cycle": p.get("billing_cycle") or "monthly",
            "price_pence": int(p.get("price_pence") or 0),
            "upfront_fee_pence": int(p.get("upfront_fee_pence") or 0),
            "included_classes": p.get("included_classes") or "unlimited",
            "credits_count": p.get("credits_count"),
            "duration_days": p.get("duration_days"),
            "freeze_allowed": bool(p.get("freeze_allowed", True)),
            "freeze_max_days": int(p.get("freeze_max_days") or 90),
            "cancel_notice_days": int(p.get("cancel_notice_days") or 0),
            "colour": p.get("colour") or "#19CDFF",
            "description": p.get("description"),
            "display_order": int(p.get("display_order") or 0),
            "active": True, "archived": False, "created_at": _now_iso(),
        }
        await db.membership_plans.insert_one(doc)
        created_ids.append(plan_id)
    await db.organizations.update_one(
        {"id": org_id}, {"$set": {"setup_step": "class"}})
    return {"ok": True, "created": created_ids}


@router.post("/memberships/setup/complete")
async def setup_complete(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"setup_completed": True, "setup_step": "done",
                  "setup_completed_at": _now_iso()}},
    )
    # Auto-fire the launch kit email (best effort — never blocks the wizard)
    launch_kit_status: dict = {"skipped": "not_attempted"}
    try:
        from utils.memberships_launch_kit import send_launch_kit
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        if org:
            launch_kit_status = await send_launch_kit(org)
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger(__name__).warning("launch kit dispatch failed: %s", e)
    return {"ok": True, "launch_kit": launch_kit_status}



@router.post("/memberships/setup/resend-launch-kit")
async def resend_launch_kit(user: dict = Depends(get_current_user)):
    """Operator-initiated resend of the launch kit (useful if the owner
    wants to re-print posters or forward the assets)."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    from utils.memberships_launch_kit import send_launch_kit
    res = await send_launch_kit(org, force=True)
    return res



# ═════════════════════ Record manual payment ═════════════════════

class RecordPaymentBody(BaseModel):
    plan_id: str
    method: Literal["cash", "card_terminal", "bank_transfer",
                    "direct_debit", "invoice", "comp"] = "cash"
    reference: str | None = None
    note: str | None = None


@router.post("/memberships/members/{member_id}/record-payment")
async def record_payment(
    member_id: str,
    body: RecordPaymentBody,
    user: dict = Depends(get_current_user),
):
    """Operator records that this member paid via their chosen method.
    Activates a membership + creates a manual payment_transactions row."""
    org_id = await _require_operator_org(user)
    plan = await db.membership_plans.find_one(
        {"id": body.plan_id, "organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Plan not found")
    member = await db.members.find_one(
        {"id": member_id, "organization_id": org_id}, {"_id": 0, "password": 0})
    if not member:
        raise HTTPException(404, "Member not found")

    # Retire any existing open membership (Iter 216h200 — previously
    # only retired `active`, leaving `pending_payment` rows orphaned
    # in the audit feed).
    await db.member_memberships.update_many(
        {"member_id": member_id,
         "status": {"$in": ["active", "frozen", "pending_payment"]}},
        {"$set": {"status": "replaced", "replaced_at": _now_iso()}},
    )

    now = datetime.now(timezone.utc)
    mm_id = str(uuid.uuid4())
    mm: dict = {
        "id": mm_id, "member_id": member_id, "plan_id": plan["id"],
        "organization_id": org_id, "status": "active",
        "start_date": now.isoformat(), "end_date": None,
        "billing_status": "current",
        "credits_remaining": int(plan.get("credits_count") or 0) if plan.get("kind") == "class_pack" else 0,
        "credits_used": 0,
        "joined_at": now.isoformat(),
        "payment_method": body.method,
        "payment_reference": body.reference,
        "audit_log": [{"at": _now_iso(), "actor_id": user["id"], "action": f"payment_recorded:{body.method}",
                       "note": body.note}],
    }
    if plan.get("kind") == "recurring":
        days = 365 if plan.get("billing_cycle") == "annual" else 30
        mm["next_billing_at"] = (now + timedelta(days=days)).isoformat()
    if plan.get("kind") == "fixed_term" and plan.get("duration_days"):
        mm["end_date"] = (now + timedelta(days=int(plan["duration_days"]))).isoformat()
    await db.member_memberships.insert_one(mm)

    # Ledger row
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "member_id": member_id, "membership_id": mm_id,
        "plan_id": plan["id"], "organization_id": org_id,
        "amount_pence": int(plan["price_pence"]) + int(plan.get("upfront_fee_pence") or 0),
        "currency": (await db.organizations.find_one({"id": org_id}, {"_id": 0, "currency": 1}) or {}).get("currency") or "GBP",
        "mode": "manual", "method": body.method,
        "status": "complete", "payment_status": "paid",
        "reference": body.reference, "note": body.note,
        "recorded_by": user["id"], "created_at": _now_iso(),
    })
    # Flip the member to active and bump LTV
    await db.members.update_one(
        {"id": member_id},
        {"$set": {"status": "active"},
         "$inc": {"lifetime_value_pence": int(plan["price_pence"]) + int(plan.get("upfront_fee_pence") or 0)}},
    )
    return {"ok": True, "membership_id": mm_id}


# ═════════════════════ White-label member-app branding ═════════════════════

@router.get("/m/{slug}/branding")
async def public_branding(slug: str, site: str | None = None):
    """Public endpoint used by the member-facing app shell to render with
    the right gym's logo and colour BEFORE the member logs in.

    Iter 216af — an optional ``?site=<site_id|site_code>`` lets a multi-site
    operator return branding scoped to a specific venue (e.g. iGym vs
    Pulse under the same parent org). Falls back to org-level when the
    site has no override or the param isn't supplied.
    """
    org = await db.organizations.find_one(
        {"$or": [{"membership_app_slug": slug.lower()}, {"slug": slug}]},
        {"_id": 0},
    )
    if not org:
        raise HTTPException(404, "Studio not found")

    site_doc: dict | None = None
    if site:
        site_doc = await db.sites.find_one(
            {"organization_id": org["id"],
             "$or": [{"id": site}, {"site_code": site}, {"slug": site}]},
            {"_id": 0},
        )
    # Resolve via the parent-child inheritance helper so there's ONE source
    # of truth for how branding cascades between org and site docs.
    from routes.sites import _effective_site_branding
    eff = _effective_site_branding(org, site_doc)
    return {
        "organization_id": org["id"],
        "name": eff["name"] or org.get("name"),
        "slug": org.get("slug"),
        "logo_url": eff["logo_url"] or org.get("logo_url"),
        "primary_brand_colour": eff["primary_color"] or "#19CDFF",
        "secondary_color": eff["secondary_color"] or "",
        "hero_image_url": org.get("member_app_hero_url") or None,
        "font": org.get("member_app_font") or "inter",
        "button_style": org.get("member_app_button_style") or "soft",
        "currency": org.get("currency") or "GBP",
        "site_id": (site_doc or {}).get("id"),
        "site_name": (site_doc or {}).get("name"),
        "branding_source": "site" if site_doc and site_doc.get("branding") else "organization",
    }


@router.get("/m/{slug}/plans")
async def public_plans(slug: str):
    """Public plan catalogue for the signup screen."""
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(404, "Studio not found")
    plans = await db.membership_plans.find(
        {"organization_id": org["id"], "archived": {"$ne": True}, "active": True},
        {"_id": 0},
    ).sort("display_order", 1).to_list(100)
    return {"plans": plans}


# ═════════════════════ Ads ═════════════════════

class AdBody(BaseModel):
    headline: str
    body: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    image_url: str | None = None
    placement: Literal["book_top", "bookings_top", "profile_bottom"] = "book_top"
    active: bool = True
    starts_at: str | None = None
    ends_at: str | None = None
    background_colour: str | None = None


@router.get("/memberships/ads")
async def list_ads(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    ads = await db.ad_placements.find(
        {"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"ads": ads}


@router.post("/memberships/ads")
async def create_ad(body: AdBody, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    ad = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        **body.model_dump(), "created_at": _now_iso(),
        "impressions": 0, "clicks": 0,
    }
    await db.ad_placements.insert_one(ad)
    ad.pop("_id", None)
    return {"ad": ad}


@router.patch("/memberships/ads/{ad_id}")
async def update_ad(ad_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    allowed = {"headline", "body", "cta_label", "cta_url", "image_url",
               "placement", "active", "starts_at", "ends_at", "background_colour"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No allowed fields in update")
    r = await db.ad_placements.update_one(
        {"id": ad_id, "organization_id": org_id}, {"$set": updates})
    if not r.matched_count:
        raise HTTPException(404, "Ad not found")
    return {"ok": True}


@router.delete("/memberships/ads/{ad_id}")
async def delete_ad(ad_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    r = await db.ad_placements.delete_one({"id": ad_id, "organization_id": org_id})
    if not r.deleted_count:
        raise HTTPException(404, "Ad not found")
    return {"ok": True}


@router.get("/m/{slug}/ads")
async def public_ads(slug: str, placement: str | None = None):
    """Member-facing ad fetch for a specific placement slot."""
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(404, "Studio not found")
    now_iso = _now_iso()
    q: dict = {"organization_id": org["id"], "active": True}
    if placement:
        q["placement"] = placement
    ads = await db.ad_placements.find(q, {"_id": 0}).to_list(50)
    # Filter by active window if set
    def _in_window(ad: dict) -> bool:
        s = ad.get("starts_at")
        e = ad.get("ends_at")
        if s and now_iso < s:
            return False
        if e and now_iso > e:
            return False
        return True
    ads = [a for a in ads if _in_window(a)]
    # Track impressions (bulk inc, fire-and-forget)
    if ads:
        await db.ad_placements.update_many(
            {"id": {"$in": [a["id"] for a in ads]}},
            {"$inc": {"impressions": 1}},
        )
    return {"ads": ads}


@router.post("/m/{slug}/ads/{ad_id}/click")
async def track_ad_click(slug: str, ad_id: str):
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(404, "Studio not found")
    await db.ad_placements.update_one(
        {"id": ad_id, "organization_id": org["id"]}, {"$inc": {"clicks": 1}})
    return {"ok": True}
