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
import string
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

PARTNER_STATUSES = {"draft", "pending", "approved", "rejected", "suspended"}
PARTNER_LEVELS = {"customer_added", "engineer_partner", "verified_partner", "strategic_partner"}
LEDGER_KINDS = {"signup_reward", "recurring"}
LEDGER_STATES = {"accrued", "approved", "paid", "clawed_back", "rejected"}
PAYOUT_STATES = {"queued", "processing", "paid", "failed"}
PAYOUT_METHODS = {"manual_csv", "stripe_connect"}


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
    Persists `app_fee_tier` + `enhanced_review_required` and returns the tier."""
    count = await _active_referral_count(partner_id)
    tier = _app_fee_tier(count)
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {
            "active_referral_count": count,
            "app_fee_tier": tier,
            "enhanced_review_required": tier["enhanced_review_required"],
            "updated_at": _now(),
        }},
    )
    return tier


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
        {"_id": 0, "id": 1, "referred_by_partner_id": 1},
    )
    if not (org and org.get("referred_by_partner_id")):
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
