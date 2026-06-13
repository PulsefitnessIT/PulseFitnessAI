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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from utils.security_plus import safe_regex_exact
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from utils.auth import get_current_user
from utils.database import db, put_object, APP_NAME
from utils.stripe_client_idempotency import stripe_idem_key as _stripe_idem_key

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── constants ─────────────────────────

PARTNER_PLAN_BASE_GBP = 30
RECURRING_GBP = 3
SIGNUP_REWARD_PCT = 0.5
OPERATIONS_PRICE_GBP = 69  # Iter 216h75 — bumped from £59
TERMS_VERSION = "2026-02-13"

# Iter 220ea·30 — Engineer tester recruitment programme. A limited cohort
# of fitness-equipment engineers is recruited (via the "WE NEED YOU!"
# social campaign) to test the Engineer App on a short free trial. The
# landing page shows a live "X of N spaces left" counter; applicants who
# arrive via the campaign are flagged `tester_cohort` and, on approval,
# get a `trial_ends_at` ENGINEER_TESTER_TRIAL_DAYS out + a trialing sub.
ENGINEER_TESTER_SPACES = max(1, int(os.environ.get("ENGINEER_TESTER_SPACES", "10") or 10))
ENGINEER_TESTER_TRIAL_DAYS = max(1, int(os.environ.get("ENGINEER_TESTER_TRIAL_DAYS", "10") or 10))
# Iter 220ea·31 — after the 10-day trial ends we email a feedback form and
# keep Engineer App access alive for a short grace window while the engineer
# decides (accept → Stripe, or decline). No decision by the end of grace =>
# auto-suspend (access revoked, in-flight jobs returned to dispatch).
ENGINEER_TRIAL_GRACE_DAYS = max(0, int(os.environ.get("ENGINEER_TRIAL_GRACE_DAYS", "3") or 3))


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
# Iter 265 — USA readiness. US engineers are billed in USD so they aren't hit
# with GBP FX fees. Create matching recurring USD prices in Stripe (e.g.
# $39 / $19) and set these env vars; if unset we fall back to the GBP price.
PARTNER_PLAN_PRICE_IDS_BY_TIER_USD = {
    30: "STRIPE_PRICE_PARTNER_PLAN_30_USD",
    15: "STRIPE_PRICE_PARTNER_PLAN_15_USD",
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


# ═════════════════════════════════════════════════════════════
# PUBLIC APPLICATION (iter 216h104)
#
# Allows independent engineers to apply WITHOUT first creating an
# account. CV / certification files are accepted. Master admin
# reviews via the existing partners admin surface — when approved
# they email the engineer a magic-link to claim the account.
#
# Stored separately in `partner_applications` (NOT partner_engineers)
# so a future spammy applicant can never accidentally collide with a
# real engineer profile.
# ═════════════════════════════════════════════════════════════

_CV_ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "rtf", "png", "jpg", "jpeg"}
_CV_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in str(value).split(",") if s and s.strip()][:25]


def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    """Iter 216h281 — accept ``YYYY-MM-DD`` (HTML <input type=date>) or full
    ISO datetimes and return an aware UTC datetime. Returns None on any
    failure so we never block the form on a bad date."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        # date-only input → midnight UTC
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        # full ISO datetime (with or without trailing 'Z')
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


async def _store_application_attachment(file: UploadFile, application_id: str) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > _CV_MAX_BYTES:
        raise HTTPException(400, "File too large — please keep CV/attachments under 10 MB")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin").lower()
    if ext not in _CV_ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type .{ext} — accepted: pdf, doc, docx, txt, rtf, png, jpg")
    path = f"{APP_NAME}/partner-applications/{application_id}/{uuid.uuid4()}.{ext}"
    stored = put_object(path, data, file.content_type or "application/octet-stream")
    return {
        "id": _new_id(),
        "original_filename": file.filename or f"attachment.{ext}",
        "content_type": file.content_type or "application/octet-stream",
        "size": len(data),
        "storage_path": stored.get("path", path),
        "download_url": stored.get("url", stored.get("path", path)),
        "uploaded_at": _now(),
    }


@router.post("/partners/track-source")
async def track_partner_attribution_source(payload: dict | None = None):
    """Iter 220o — Top-of-funnel attribution counter.

    Called by the public Partner Engineer landing page when a visitor
    arrives with UTM-tagged parameters (e.g. from the Instagram launch
    campaign). Increments a per-(source, medium, campaign) counter so
    master admin can see how many landings each channel produced —
    independent of whether they converted into an application.

    Storage layout (`db.partner_attribution_landings`):

        {
          "_id": auto,
          "key": "instagram|paid|partner-launch-may26",   # source|medium|campaign
          "utm_source": "instagram",
          "utm_medium": "paid",
          "utm_campaign": "partner-launch-may26",
          "landings": 1247,            # ← $inc'd each call
          "last_landing_at": "2026-05-26T18:11Z",
          "last_referrer_url": "https://www.instagram.com/...",
        }

    The endpoint is *deliberately* anonymous — no auth, no IP capture,
    no fingerprinting. We only count totals per channel-tag. Apply-form
    submissions carry their own attribution (`utm_source` on the
    `partner_applications` doc) for the conversion side.
    """
    payload = payload or {}
    utm_source = (payload.get("utm_source") or "").strip().lower()[:200]
    if not utm_source:
        # We only care about tagged landings — organic traffic is
        # tracked elsewhere (web analytics) and would otherwise drown
        # the per-channel counts.
        return {"ok": True, "skipped": "no-utm-source"}
    utm_medium = (payload.get("utm_medium") or "").strip().lower()[:200]
    utm_campaign = (payload.get("utm_campaign") or "").strip().lower()[:200]
    utm_content = (payload.get("utm_content") or "").strip().lower()[:200]
    referrer_url = (payload.get("referrer_url") or "").strip()[:500] or None
    landing_path = (payload.get("landing_path") or "").strip()[:200] or None
    key = f"{utm_source}|{utm_medium}|{utm_campaign}"
    now_iso = _now()
    try:
        await db.partner_attribution_landings.update_one(
            {"key": key},
            {
                "$inc": {"landings": 1},
                "$setOnInsert": {
                    "utm_source": utm_source,
                    "utm_medium": utm_medium or None,
                    "utm_campaign": utm_campaign or None,
                    "utm_content": utm_content or None,
                    "first_landing_at": now_iso,
                },
                "$set": {
                    "last_landing_at": now_iso,
                    "last_referrer_url": referrer_url,
                    "last_landing_path": landing_path,
                },
            },
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_partner_attribution_source upsert failed: %s", exc)
        return {"ok": False}
    return {"ok": True, "key": key}


@router.get("/partners/attribution-summary")
async def partner_attribution_summary(user: dict = Depends(get_current_user)):
    """Iter 220o — Master-admin only: top-of-funnel counts per
    (source, medium, campaign) plus the conversion count (applications
    received) for each tagged source. Lets the team see which
    Instagram post / channel drove the most applications.
    """
    _require_master_admin(user)
    # Landings: total visitors that landed with a UTM-tagged URL.
    landings = await db.partner_attribution_landings.find(
        {}, {"_id": 0},
    ).sort("landings", -1).to_list(500)
    # Conversions: count applications keyed by utm_source.
    pipeline = [
        {"$match": {"utm_source": {"$ne": None}}},
        {"$group": {"_id": "$utm_source", "applications": {"$sum": 1}}},
    ]
    conv_rows = await db.partner_applications.aggregate(pipeline).to_list(200)
    conversions_by_source = {r["_id"]: r["applications"] for r in conv_rows if r.get("_id")}
    # Decorate each landing row with its conversion count + rate.
    enriched = []
    for row in landings:
        src = row.get("utm_source")
        apps = conversions_by_source.get(src, 0)
        enriched.append({
            **row,
            "applications": apps,
            "conversion_rate_pct": (
                round(100.0 * apps / row["landings"], 2)
                if row.get("landings") else 0.0
            ),
        })
    return {
        "rows": enriched,
        "totals": {
            "landings": sum(r.get("landings", 0) for r in landings),
            "applications_attributed": sum(conversions_by_source.values()),
        },
    }


@router.post("/partners/public-apply")
async def public_apply_partner(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    company_name: str = Form(""),
    service_postcode: str = Form(""),
    # Iter 265 — USA readiness. The engineer's market (ISO-3166 alpha-2) chosen
    # at signup. Drives their currency (invoices/quotes), Stripe Connect account
    # country, compliance doc set (US→I-9/background check) and plan currency.
    country_code: str = Form("GB"),
    travel_radius_km: int = Form(25),
    brands_supported: str = Form(""),
    skills: str = Form(""),
    qualifications: str = Form(""),
    years_experience: str = Form(""),
    has_insurance: str = Form("false"),
    insurance_provider: str = Form(""),
    insurance_expires_at: str = Form(""),
    qualifications_expires_at: str = Form(""),
    referral_source: str = Form(""),
    referred_by_eref: str = Form(""),
    # Iter 220ea·30 — engineer tester recruitment cohort. The
    # "WE NEED YOU!" campaign landing sends cohort=tester so approved
    # applicants get the short free trial + count against the 10 spaces.
    cohort: str = Form(""),
    # Iter 220o — Instagram-attributed (and any other UTM-tagged)
    # landing. Stored on the application so master admin can see at
    # a glance which marketing channel converted this engineer.
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_content: str = Form(""),
    utm_term: str = Form(""),
    referrer_url: str = Form(""),
    cover_letter: str = Form(""),
    terms_accepted: str = Form("false"),
    cv_file: Optional[UploadFile] = File(None),
    cert_file: Optional[UploadFile] = File(None),
):
    """Public engineer application — no auth required. Stores into
    `partner_applications` for master admin review. Idempotent on
    `email` — a re-submission updates the pending application."""
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    if not full_name:
        raise HTTPException(400, "Full name is required")
    if not email or "@" not in email or len(email) > 200:
        raise HTTPException(400, "A valid email address is required")
    if (terms_accepted or "").lower() not in ("true", "1", "on", "yes"):
        raise HTTPException(400, "You must accept the Partner Engineer terms")
    from utils.localization import COUNTRY_CONFIG, DEFAULT_COUNTRY
    market = (country_code or "").strip().upper()
    if market not in COUNTRY_CONFIG:
        market = DEFAULT_COUNTRY
    # Postcode format is UK-specific; only validate it for GB applicants so a
    # US ZIP / other-market postal code isn't rejected.
    if market == "GB":
        postcode = _validate_postcode(service_postcode or "TBD") if (service_postcode or "").strip() else ""
    else:
        postcode = (service_postcode or "").strip()[:20] or ""

    application_id = _new_id()

    attachments: list[dict] = []
    if cv_file is not None and getattr(cv_file, "filename", ""):
        attachments.append({**(await _store_application_attachment(cv_file, application_id)), "kind": "cv"})
    if cert_file is not None and getattr(cert_file, "filename", ""):
        attachments.append({**(await _store_application_attachment(cert_file, application_id)), "kind": "certifications"})

    base_doc = {
        "full_name": full_name,
        "email": email,
        "phone": (phone or "").strip()[:40] or None,
        "company_name": (company_name or "").strip()[:200] or None,
        "country_code": market,
        "service_postcode": postcode or None,
        "travel_radius_km": max(1, min(int(travel_radius_km or 25), 500)),
        "brands_supported": _split_csv(brands_supported),
        "skills": _split_csv(skills),
        "qualifications": _split_csv(qualifications),
        "years_experience": (years_experience or "").strip()[:30] or None,
        "has_insurance": (has_insurance or "").lower() in ("true", "1", "on", "yes"),
        "insurance_provider": (insurance_provider or "").strip()[:200] or None,
        # Iter 216h281 — Gap 2 from BA audit: capture expiry dates so the
        # nightly job can warn engineers ahead of compliance gaps.
        "insurance_expires_at": _parse_iso_date(insurance_expires_at),
        "qualifications_expires_at": _parse_iso_date(qualifications_expires_at),
        "referral_source": (referral_source or "").strip()[:120] or None,
        # Iter 216h287 — Gap 9: engineer-of-engineer referrals. Stamp
        # the referring partner so master-admin sees the attribution
        # at-a-glance. The `engineer_referrals` ledger row is written
        # below once we know the applicant's email is valid.
        "referred_by_eref": (referred_by_eref or "").strip().upper()[:32] or None,
        # Iter 220o — UTM attribution (Instagram, etc.). Flattened onto
        # the application doc so the master-admin list view can filter
        # by source and master-admin analytics can count conversions
        # per channel without a join. All five UTM fields are lowercased
        # + capped at 200 chars.
        "utm_source": (utm_source or "").strip().lower()[:200] or None,
        "utm_medium": (utm_medium or "").strip().lower()[:200] or None,
        "utm_campaign": (utm_campaign or "").strip().lower()[:200] or None,
        "utm_content": (utm_content or "").strip().lower()[:200] or None,
        "utm_term": (utm_term or "").strip().lower()[:200] or None,
        "referrer_url": (referrer_url or "").strip()[:500] or None,
        "cover_letter": (cover_letter or "").strip()[:4000] or None,
        # Iter 220ea·30 — flag engineer-tester-cohort applicants (campaign
        # landing sends cohort=tester; also infer from the campaign UTM).
        "tester_cohort": (cohort or "").strip().lower() == "tester"
        or (utm_campaign or "").strip().lower() in {"engineer_recruit", "we_need_you"},
        "terms_accepted_at": _now(),
        "terms_version": TERMS_VERSION,
        "updated_at": _now(),
    }

    existing = await db.partner_applications.find_one({"email": email, "status": {"$in": ["pending", "in_review"]}}, {"_id": 0})
    if existing:
        # Idempotent resubmit — keep existing attachments, append new ones
        merged_attachments = (existing.get("attachments") or []) + attachments
        await db.partner_applications.update_one(
            {"id": existing["id"]},
            {"$set": {**base_doc, "attachments": merged_attachments[:20]}},
        )
        # Iter 216h287 — re-attempt eref attribution on resubmit, in
        # case the applicant lost the original link or applied raw
        # the first time.
        eref_re = base_doc.get("referred_by_eref")
        if eref_re:
            referrer = await _resolve_eref_partner(eref_re)
            if referrer:
                await _record_engineer_referral(
                    referrer_partner_id=referrer["id"],
                    referrer_code=referrer["referral_code"],
                    referred_email=email,
                    referred_application_id=existing["id"],
                )
        # Iter 216h281 — re-fire the receipt email on resubmit too so the
        # applicant has the most recent reference number in their inbox.
        try:
            from utils.partner_emails import send_application_received
            await send_application_received(email=email, full_name=full_name, application_id=existing["id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Partner application-received resubmit email failed: %s", exc)
        return {
            "ok": True,
            "application_id": existing["id"],
            "status": existing.get("status", "pending"),
            "message": "Application updated — our team will be in touch within 2 working days.",
            "resubmitted": True,
        }

    doc = {
        "id": application_id,
        "status": "pending",
        "submitted_at": _now(),
        "created_at": _now(),
        "attachments": attachments,
        "reviewer_notes": None,
        "user_id": None,  # linked once the engineer claims an account
        **base_doc,
    }
    await db.partner_applications.insert_one(doc)
    # Iter 216h287 — Gap 9: if the application came via an engineer's
    # eref link, log the attribution into `engineer_referrals` so the
    # tier credit can be awarded on approval. Self-referral, bad eref
    # and missing email are silently no-op'd by the helper.
    eref = base_doc.get("referred_by_eref")
    if eref:
        referrer = await _resolve_eref_partner(eref)
        if referrer:
            await _record_engineer_referral(
                referrer_partner_id=referrer["id"],
                referrer_code=referrer["referral_code"],
                referred_email=email,
                referred_application_id=application_id,
            )
    # Iter 216h281 — Gap 1 from the BA audit: fire the "application
    # received" email. Wrapped in a try so a mail failure never breaks
    # the form submission (the row is already persisted by this point).
    try:
        from utils.partner_emails import send_application_received
        await send_application_received(email=email, full_name=full_name, application_id=application_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner application-received email failed: %s", exc)
    return {
        "ok": True,
        "application_id": application_id,
        "status": "pending",
        "message": "Thanks — your application is in. We aim to respond within 2 working days.",
        "resubmitted": False,
    }


@router.get("/partners/recruitment/status")
async def recruitment_status():
    """Public — live tester-cohort capacity for the engineer recruitment
    ("WE NEED YOU!") campaign. Drives the "X of N spaces left" counter on
    the landing page. Counts applications flagged tester_cohort that are
    still pending/in-review/approved against ENGINEER_TESTER_SPACES."""
    taken = await db.partner_applications.count_documents({
        "tester_cohort": True,
        "status": {"$in": ["pending", "in_review", "approved"]},
    })
    remaining = max(0, ENGINEER_TESTER_SPACES - taken)
    return {
        "total_spaces": ENGINEER_TESTER_SPACES,
        "taken": min(taken, ENGINEER_TESTER_SPACES),
        "remaining": remaining,
        "open": remaining > 0,
        "trial_days": ENGINEER_TESTER_TRIAL_DAYS,
    }


@router.get("/partners/applications")
async def list_partner_applications(
    status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Master admin: list public partner applications."""
    _require_master_admin(user)
    q = {}
    if status:
        q["status"] = status
    items = await db.partner_applications.find(q, {"_id": 0}).sort("submitted_at", -1).to_list(500)
    return {"applications": items, "total": len(items)}


@router.get("/partners/applications/{application_id}")
async def get_partner_application(
    application_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 219 — Full application detail for the master admin drawer.

    Returns every field captured at submission (personal, coverage, skills,
    compliance, attachments metadata, terms acceptance) plus a denormalised
    referrer block when the applicant arrived via an existing engineer's
    eref code. Attachments are returned with a backend-relative
    `download_url` (`/api/partners/applications/{id}/attachments/{aid}`)
    that the FE can fetch with the admin's bearer token — we never expose
    the raw object-store URL.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")

    # Rewrite attachment URLs to our own auth-gated download endpoint so
    # the admin's browser doesn't try to hit the raw object-store path
    # (which 403s without the storage key).
    rewritten: list[dict] = []
    for att in app.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        att_id = att.get("id")
        rewritten.append({
            **att,
            "download_url": (
                f"/api/partners/applications/{application_id}/attachments/{att_id}"
                if att_id else att.get("download_url")
            ),
        })
    app["attachments"] = rewritten

    # Denormalise referrer info for the drawer header.
    referrer = None
    eref = (app.get("referred_by_eref") or "").strip().upper()
    if eref:
        ref_doc = await _resolve_eref_partner(eref)
        if ref_doc:
            referrer = {
                "id": ref_doc.get("id"),
                "full_name": ref_doc.get("full_name"),
                "email": ref_doc.get("email"),
                "referral_code": ref_doc.get("referral_code"),
            }

    return {"application": app, "referrer": referrer}


@router.patch("/partners/applications/{application_id}/notes")
async def update_partner_application_notes(
    application_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Iter 219 — persist reviewer notes on a pending application.

    Saved on every blur from the drawer so a reviewer's draft notes
    survive page reloads. Audited so we can prove what the reviewer
    saw at the moment of approve/reject.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    notes = (body.get("notes") or "").strip()[:4000] or None
    await db.partner_applications.update_one(
        {"id": application_id},
        {"$set": {"reviewer_notes": notes, "updated_at": _now()}},
    )
    return {"ok": True, "reviewer_notes": notes}


@router.get("/partners/applications/{application_id}/attachments/{attachment_id}")
async def download_partner_application_attachment(
    application_id: str,
    attachment_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 219 — auth-gated streaming download for an application's
    uploaded files (CV / certifications). Master admin only. We never
    surface the raw object-store URL because it requires an X-Storage-Key
    header that the browser doesn't have.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one(
        {"id": application_id}, {"_id": 0, "attachments": 1},
    )
    if not app:
        raise HTTPException(404, "Application not found")
    target = None
    for att in app.get("attachments") or []:
        if isinstance(att, dict) and att.get("id") == attachment_id:
            target = att
            break
    if not target:
        raise HTTPException(404, "Attachment not found")
    storage_path = target.get("storage_path")
    if not storage_path:
        raise HTTPException(410, "Attachment is missing its storage path")
    try:
        from utils.database import get_object
        body, content_type = get_object(storage_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch partner attachment %s: %s", storage_path, exc)
        raise HTTPException(502, "Attachment storage unavailable") from exc
    filename = target.get("original_filename") or "attachment"
    safe_name = filename.replace('"', "")
    return Response(
        content=body,
        media_type=target.get("content_type") or content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.post("/partners/applications/{application_id}/ai-suggest")
async def suggest_partner_application_decision(
    application_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 219b — AI decision helper. Returns a structured
    recommendation (approve / reject / needs_info), suggested level,
    confidence, headline, reasons, red flags and a coverage-value note
    so the master admin can decide faster.

    Advisory only — the human reviewer remains the source of truth.
    Falls back to a deterministic recommendation when the LLM is
    offline so the UI never breaks.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    # Pull a slim slice of active partners for coverage-gap reasoning.
    roster = await db.partner_engineers.find(
        {"status": "approved"},
        {"_id": 0, "brands_supported": 1, "service_postcode": 1},
    ).to_list(length=500)
    from utils.partner_application_ai import suggest_decision
    suggestion = await suggest_decision(app, roster)
    return {"application_id": application_id, "suggestion": suggestion}


@router.post("/partners/applications/{application_id}/approve")
async def approve_partner_application(
    application_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Iter 218 — promote a `partner_applications` row to a real
    `partner_engineers` row.

    First-customer bug: the master-admin UI was wiring its Partner
    Applications panel to `/api/master-admin/partners` which returns
    `partner_engineers`, so public-applied engineers (who land in
    `partner_applications`) were invisible. The application persisted
    fine — Dan Thomas's row is sitting in production. This endpoint
    is the missing piece to convert it.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    if app.get("status") in {"approved", "rejected"}:
        raise HTTPException(400, f"Application already {app['status']}")

    level = (body or {}).get("level") or "engineer_partner"
    if level not in {"engineer_partner", "verified_partner", "strategic_partner", "customer_added"}:
        raise HTTPException(400, "Invalid level")

    # Iter 220ea·30 — tester-cohort engineers get a short free trial on
    # approval. trial_ends_at drives the in-app countdown; the sub is
    # marked trialing with current_period_end == the trial end.
    is_tester = bool(app.get("tester_cohort"))
    trial_end_iso = (
        (datetime.now(timezone.utc) + timedelta(days=ENGINEER_TESTER_TRIAL_DAYS)).isoformat()
        if is_tester else None
    )

    # Idempotent — if a partner row already exists for this email
    # (e.g. they self-claimed via the authed flow earlier) just attach
    # the application to it rather than creating a duplicate.
    existing_partner = await db.partner_engineers.find_one({"email": app["email"]}, {"_id": 0})

    if existing_partner:
        existing_set = {
            "status": "approved",
            "level": level,
            "application_id": application_id,
            "updated_at": _now(),
        }
        if is_tester:
            existing_set["tester_cohort"] = True
            existing_set["trial_ends_at"] = trial_end_iso
            existing_set["subscription.status"] = "trialing"
            existing_set["subscription.current_period_end"] = trial_end_iso
        await db.partner_engineers.update_one(
            {"id": existing_partner["id"]},
            {"$set": existing_set},
        )
        partner_id = existing_partner["id"]
        referral_code = existing_partner.get("referral_code")
    else:
        partner_id = _new_id()
        referral_code = await _new_referral_code()        # Note: `partner_engineers` has a non-sparse unique index on
        # `user_id` — passing null (or omitting the field, treated as
        # null by the index) collides between unclaimed approvals.
        # We stamp a unique pending-claim placeholder; the magic-link
        # claim flow overwrites it with the real user_id on first
        # sign-in.
        doc = {
            "id": partner_id,
            "user_id": f"pending:{partner_id}",
            "email": app["email"],
            "owner_organization_id": None,
            "status": "approved",
            "level": level,
            "referral_code": referral_code,
            "active_referral_count": 0,
            "app_fee_tier": _app_fee_tier(0),
            "enhanced_review_required": False,
            "subscription": {
                "status": "trialing",
                "stripe_subscription_id": None,
                "current_period_end": trial_end_iso,
            },
            "tester_cohort": is_tester,
            "trial_ends_at": trial_end_iso,
            "payout": {"method": "manual_csv", "stripe_account_id": None, "bank_name": None,
                       "sort_code": None, "account_number_last4": None},
            "created_at": _now(),
            "updated_at": _now(),
            "application_id": application_id,
            # Carry profile fields across from the application.
            "full_name": app.get("full_name"),
            "company_name": app.get("company_name"),
            # Iter 265 — engineer's market (drives currency, Stripe Connect
            # account country, compliance doc set). Defaults GB for back-compat.
            "country_code": (app.get("country_code") or "GB"),
            "phone": app.get("phone"),
            "service_postcode": app.get("service_postcode"),
            "travel_radius_km": app.get("travel_radius_km") or 25,
            "brands_supported": app.get("brands_supported") or [],
            "skills": app.get("skills") or [],
            "qualifications": app.get("qualifications") or [],
            "years_experience": app.get("years_experience"),
            "has_insurance": bool(app.get("has_insurance")),
            "insurance_provider": app.get("insurance_provider"),
            "insurance_expires_at": app.get("insurance_expires_at"),
            "qualifications_expires_at": app.get("qualifications_expires_at"),
            "terms_accepted_at": app.get("terms_accepted_at"),
            "terms_version": app.get("terms_version") or TERMS_VERSION,
        }
        await db.partner_engineers.insert_one(doc)

    # Iter 219f — generate a single-use activation token so the email
    # CTA can take the engineer straight to a "set my password" page
    # (no scavenger hunt for /register). Stored on the application
    # row with a 14-day TTL so a stale link can't be replayed forever.
    import secrets
    activation_token = secrets.token_urlsafe(32)
    activation_expires_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    await db.partner_applications.update_one(
        {"id": application_id},
        {"$set": {
            "status": "approved",
            "approved_at": _now(),
            "approved_by": user.get("id"),
            "partner_id": partner_id,
            "level_assigned": level,
            "activation_token": activation_token,
            "activation_token_expires_at": activation_expires_at,
            "activation_completed_at": None,
            "updated_at": _now(),
        }},
    )
    await _audit(
        partner_id=partner_id, actor_id=user.get("id") or "", action="approve_application",
        before={"application_id": application_id, "status": app.get("status")},
        after={"status": "approved", "level": level},
    )

    # Approval email — wrapped so a mail outage never blocks the promotion.
    # Iter 219c — fix: previously called with `partner_id=` which is not a
    # parameter on `send_application_approved`, so the call raised TypeError
    # and was silently swallowed → engineers approved via the application
    # flow never received the welcome email. Now passes `referral_code`
    # correctly so the new partner gets their code in-inbox.
    # Iter 219f — additionally pass `activation_token` so the email CTA
    # is a single-use deep link to the activation page.
    try:
        from utils.partner_emails import send_application_approved
        await send_application_approved(
            email=app["email"],
            full_name=app.get("full_name") or "",
            referral_code=referral_code,
            activation_token=activation_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner application-approved email failed: %s", exc)

    # Iter 220ea·38 — EVERY approved engineer is auto-enrolled onto the
    # proper 10-day trial lifecycle (feedback form + Stripe at the end),
    # not just the campaign tester cohort. Previously non-tester engineers
    # were left with a bare `subscription.status='trialing'` and no end
    # date — the dashboard showed "Active · Billing in progress…" forever
    # with no countdown and no way forward (engineer stuck on the landing
    # page). Starting the trial here writes the real `trial` object +
    # `ends_at` + `current_period_end` so the 10-day timer runs and the
    # dashboard shows a proper countdown. Best-effort: a failure here must
    # never undo the approval.
    TRIAL_ELIGIBLE_LEVELS = {"engineer_partner", "verified_partner", "strategic_partner"}
    if level in TRIAL_ELIGIBLE_LEVELS:
        try:
            tp = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
            if tp and not tp.get("trial_used"):
                await _start_partner_trial(tp, user.get("id") or "")
        except Exception:
            logger.warning("[partners] auto-start trial on approve failed", exc_info=True)

    return {"ok": True, "partner_id": partner_id, "application_id": application_id, "level": level}


# ──────────────────────── Engineer 10-day trial lifecycle ────────────────────────
# Watertight rules:
#   • One trial per engineer, ever (`trial_used` guard — no repeat freebies).
#   • Explicit admin action (button) OR auto-start for campaign tester_cohort.
#   • Day 9 reminder → Day 10 feedback form → 3-day grace → accept(Stripe) /
#     decline / no-response(auto-suspend). All transitions audited.

import secrets as _secrets


async def _start_partner_trial(partner: dict, started_by: str, *, force: bool = False) -> dict:
    """Put an (approved) engineer onto the 10-day free trial. Idempotent-ish:
    refuses if the engineer has already used a trial unless `force`."""
    if partner.get("trial_used") and not force:
        raise HTTPException(400, "This engineer has already used their free trial.")
    now = datetime.now(timezone.utc)
    ends_at = (now + timedelta(days=ENGINEER_TESTER_TRIAL_DAYS)).isoformat()
    trial = {
        "status": "active",
        "started_at": now.isoformat(),
        "ends_at": ends_at,
        "started_by": started_by or "system",
        "reminder_sent_at": None,
        "feedback_sent_at": None,
        "feedback_token": None,
        "grace_until": None,
        "lastchance_sent_at": None,
        "feedback": None,
        "decision": None,
        "decided_at": None,
        "converted_at": None,
    }
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {
            "status": "approved",
            "trial": trial,
            "trial_used": True,
            "trial_ends_at": ends_at,
            "subscription.status": "trialing",
            "subscription.current_period_end": ends_at,
            "updated_at": _now(),
        }},
    )
    await _audit(partner_id=partner["id"], actor_id=started_by or "system",
                 action="trial_started", after={"ends_at": ends_at})
    try:
        from utils.partner_emails import send_trial_started
        await send_trial_started(
            email=partner.get("email") or "",
            full_name=partner.get("full_name") or "",
            ends_at=ends_at,
            trial_days=ENGINEER_TESTER_TRIAL_DAYS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] trial-started email failed: %s", exc)
    return trial


@router.post("/partners/{partner_id}/start-trial")
async def start_partner_trial_endpoint(
    partner_id: str, user: dict = Depends(get_current_user),
):
    """Master admin — put an already-approved engineer onto the 10-day
    free trial (button in the Partners list)."""
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Engineer not found")
    if partner.get("status") in {"rejected"}:
        raise HTTPException(400, "Cannot start a trial for a rejected engineer")
    trial = await _start_partner_trial(partner, user.get("id") or "")
    return {"ok": True, "partner_id": partner_id, "trial": trial}


@router.post("/partners/applications/{application_id}/approve-with-trial")
async def approve_application_with_trial(
    application_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Master admin — one-click 'Approve & start 10-day trial' from the
    application drawer. Promotes the application (if needed) then starts
    the trial. Safe to call on an already-approved application."""
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")

    if app.get("status") == "approved" and app.get("partner_id"):
        partner_id = app["partner_id"]
    else:
        result = await approve_partner_application(application_id, body, user)
        partner_id = result["partner_id"]

    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(500, "Partner row missing after approval")
    # If approval already auto-started a trial (campaign tester_cohort), keep it.
    if partner.get("trial_used") and (partner.get("trial") or {}).get("status"):
        return {"ok": True, "partner_id": partner_id, "trial": partner["trial"],
                "already_on_trial": True}
    trial = await _start_partner_trial(partner, user.get("id") or "")
    return {"ok": True, "partner_id": partner_id, "trial": trial}


@router.get("/partners/trial/feedback/{token}")
async def get_trial_feedback(token: str):
    """Public — resolve a trial-feedback token so the engineer's feedback
    page can render their name + state. No auth (token is the secret)."""
    partner = await db.partner_engineers.find_one(
        {"trial.feedback_token": token},
        {"_id": 0, "id": 1, "full_name": 1, "trial": 1},
    )
    if not partner:
        raise HTTPException(404, "This feedback link is invalid or has expired.")
    trial = partner.get("trial") or {}
    return {
        "engineer_name": partner.get("full_name") or "there",
        "status": trial.get("status"),
        "already_submitted": bool(trial.get("feedback")),
        "decision": trial.get("decision"),
        "trial_days": ENGINEER_TESTER_TRIAL_DAYS,
    }


@router.post("/partners/trial/feedback/{token}")
async def submit_trial_feedback(token: str, body: dict = Body(default_factory=dict)):
    """Public — engineer submits trial feedback + their continue decision.

    accept → create a Stripe checkout (returns url). decline → suspend.
    """
    partner = await db.partner_engineers.find_one({"trial.feedback_token": token}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "This feedback link is invalid or has expired.")
    trial = partner.get("trial") or {}
    if trial.get("status") not in {"feedback_pending", "accepted"}:
        raise HTTPException(400, "This trial is no longer awaiting feedback.")

    try:
        rating = int(body.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    rating = max(0, min(5, rating))
    feedback = {
        "rating": rating,
        "worked_well": (body.get("worked_well") or "").strip()[:4000],
        "missing": (body.get("missing") or "").strip()[:4000],
        "continue_paid": bool(body.get("continue_paid")),
        "submitted_at": _now(),
    }
    decision = "accept" if feedback["continue_paid"] else "decline"

    if decision == "accept":
        await db.partner_engineers.update_one(
            {"id": partner["id"]},
            {"$set": {"trial.feedback": feedback, "trial.status": "accepted",
                      "trial.decision": "accept", "trial.decided_at": _now(),
                      "updated_at": _now()}},
        )
        await _audit(partner_id=partner["id"], actor_id="engineer",
                     action="trial_feedback_accept", after={"rating": rating})
        try:
            checkout = await _create_partner_checkout_session(
                partner, body.get("origin_url") or "")
            return {"ok": True, "decision": "accept", "checkout_url": checkout["url"]}
        except HTTPException as exc:
            # Free-tier (no payment needed) → just keep them active.
            if exc.status_code == 400 and "free tier" in str(exc.detail).lower():
                await db.partner_engineers.update_one(
                    {"id": partner["id"]},
                    {"$set": {"trial.status": "converted_paid", "trial.converted_at": _now(),
                              "subscription.status": "active"}},
                )
                return {"ok": True, "decision": "accept", "checkout_url": None,
                        "free_tier": True}
            raise

    # Decline → mark, suspend access, return in-flight jobs to dispatch.
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"trial.feedback": feedback, "trial.status": "declined",
                  "trial.decision": "decline", "trial.decided_at": _now(),
                  "status": "suspended",
                  "subscription.status": "trial_declined", "updated_at": _now()}},
    )
    await _audit(partner_id=partner["id"], actor_id="engineer",
                 action="trial_feedback_decline", after={"rating": rating})
    try:
        await _handle_partner_loss_of_access(partner["id"], "trial_declined")
    except Exception:
        logger.exception("[partners] loss-of-access on trial decline failed")
    return {"ok": True, "decision": "decline", "checkout_url": None}


@router.post("/partners/applications/{application_id}/resend-approval-email")
async def resend_partner_application_approval_email(
    application_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 219d — Manually re-fire the welcome email for an already-
    approved application.

    Context: iter 219c fixed a TypeError that had been silently
    swallowing the approval email for every engineer approved via the
    application drawer. Existing approved engineers therefore never
    received their welcome / referral code. This endpoint lets the
    master admin retroactively send it.

    Returns 400 if the application isn't approved yet (use /approve
    instead) or if no partner row is attached (data integrity issue).
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    if app.get("status") != "approved":
        raise HTTPException(400, f"Application is not approved (status={app.get('status')})")
    partner_id = app.get("partner_id")
    if not partner_id:
        raise HTTPException(400, "Approved application has no partner record attached")
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(400, "Partner record missing — cannot resolve referral code")
    if not (partner.get("email") or app.get("email")):
        raise HTTPException(400, "No email address on file for this engineer")

    target_email = partner.get("email") or app["email"]
    full_name = partner.get("full_name") or app.get("full_name") or ""
    referral_code = partner.get("referral_code")

    # Iter 219f — Re-issue the activation token if expired or already
    # consumed, so the resend email always carries a working CTA. We
    # reuse the existing token when it's still valid and unused, so a
    # well-meaning admin clicking "resend" twice doesn't invalidate
    # the engineer's previous link.
    import secrets
    activation_token = app.get("activation_token")
    activation_expires_at = app.get("activation_token_expires_at")
    activation_completed_at = app.get("activation_completed_at")
    now = datetime.now(timezone.utc)
    expires_dt = activation_expires_at
    if isinstance(expires_dt, str):
        try:
            expires_dt = datetime.fromisoformat(expires_dt.replace("Z", "+00:00"))
        except ValueError:
            expires_dt = None
    needs_new = (
        not activation_token
        or activation_completed_at is not None
        or (isinstance(expires_dt, datetime) and expires_dt < now)
    )
    if needs_new:
        activation_token = secrets.token_urlsafe(32)
        activation_expires_at = (now + timedelta(days=14)).isoformat()
        await db.partner_applications.update_one(
            {"id": application_id},
            {"$set": {
                "activation_token": activation_token,
                "activation_token_expires_at": activation_expires_at,
                "activation_completed_at": None,
                "updated_at": _now(),
            }},
        )

    from utils.partner_emails import send_application_approved
    try:
        ok = await send_application_approved(
            email=target_email,
            full_name=full_name,
            referral_code=referral_code,
            activation_token=activation_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Manual resend of approval email failed: %s", exc)
        raise HTTPException(502, "Email send failed — please retry shortly") from exc

    await _audit(
        partner_id=partner_id,
        actor_id=user.get("id") or "",
        action="resend_approval_email",
        before=None,
        after={"to": target_email, "delivered": bool(ok), "token_reissued": needs_new},
    )
    return {
        "ok": bool(ok),
        "application_id": application_id,
        "partner_id": partner_id,
        "sent_to": target_email,
    }


async def _mint_and_send_password_reset(
    existing_user: dict, full_name: str, issued_by: str, partner_id: str,
) -> dict:
    """Shared password-reset minter — used by the application drawer AND
    the engineer-profile 'Send password link' button. 1-hour TTL token,
    same shape as /auth/forgot-password."""
    import secrets
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": existing_user["id"],
        "email": existing_user["email"],
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "issued_by": issued_by,
        "issued_via": "admin_partner",
    })
    from utils.brand_urls import app_url_for_org
    org = None
    if existing_user.get("organization_id"):
        org = await db.organizations.find_one(
            {"id": existing_user["organization_id"]}, {"_id": 0, "account_type": 1})
    reset_url = f"{app_url_for_org(org)}/reset-password?token={token}"
    try:
        from utils.email import send_password_reset_email
        ok = await send_password_reset_email(
            existing_user["email"], existing_user.get("full_name") or full_name, reset_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner password-reset email failed: %s", exc)
        raise HTTPException(502, "Email send failed — please retry shortly") from exc
    await _audit(partner_id=partner_id, actor_id=issued_by,
                 action="send_password_reset", after={"to": existing_user["email"], "delivered": bool(ok)})
    return {"ok": bool(ok), "kind": "password_reset", "sent_to": existing_user["email"]}


@router.post("/partners/{partner_id}/send-signin-link")
async def send_partner_signin_link_by_partner(
    partner_id: str, user: dict = Depends(get_current_user),
):
    """Iter 220ea·32 — send a sign-in / password link straight from an
    engineer's profile in the Partners list (not just the application
    drawer). Same smart behaviour: existing account → password reset;
    not yet activated → re-issue the activation welcome email."""
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Engineer not found")
    target_email = (partner.get("email") or "").strip()
    if not target_email:
        raise HTTPException(400, "This engineer has no email on file")

    existing_user = await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(target_email)}$", "$options": "i"}}, {"_id": 0})
    if existing_user:
        return await _mint_and_send_password_reset(
            existing_user, partner.get("full_name") or "", user.get("id") or "", partner_id)

    # No account yet → fall back to re-issuing the activation welcome email.
    if partner.get("application_id"):
        return await send_partner_signin_link(partner["application_id"], user)
    raise HTTPException(
        400, "This engineer hasn't created an account yet and has no application to "
             "activate from — they'll need to be (re)approved to receive an activation link.")


@router.post("/partners/applications/{application_id}/send-signin-link")
async def send_partner_signin_link(
    application_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 219g — One smart button that always lands the engineer
    back in a working sign-in state, whether they've activated yet or
    not.

      • Application not yet activated (no user account exists)
        → re-issue the activation token and send the welcome email
          with the "Set up your sign-in" CTA.

      • User account exists (engineer already activated)
        → mint a password-reset token (1-hour TTL, same shape as
          /auth/forgot-password) and send a password-reset email.

    Returns `{ok, kind, sent_to}` so the FE toast can say exactly
    what landed in the engineer's inbox.
    """
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    if app.get("status") != "approved":
        raise HTTPException(400, f"Application is not approved (status={app.get('status')})")
    target_email = (app.get("email") or "").strip()
    if not target_email:
        raise HTTPException(400, "Application has no email address on file")
    full_name = app.get("full_name") or ""

    # Does the engineer already have a GymAxis account? Case-insensitive.
    existing_user = await db.users.find_one(
        {"email": safe_regex_exact(target_email)},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "organization_id": 1},
    )

    if existing_user:
        # ── Password-reset path ────────────────────────────────
        result = await _mint_and_send_password_reset(
            existing_user, full_name, user.get("id") or "", app.get("partner_id") or "")
        result["application_id"] = application_id
        return result

    # ── Activation path ────────────────────────────────────────
    # Reuse existing token if still valid; otherwise mint a fresh one.
    import secrets
    activation_token = app.get("activation_token")
    expires_dt = app.get("activation_token_expires_at")
    if isinstance(expires_dt, str):
        try:
            expires_dt = datetime.fromisoformat(expires_dt.replace("Z", "+00:00"))
        except ValueError:
            expires_dt = None
    now = datetime.now(timezone.utc)
    needs_new = (
        not activation_token
        or app.get("activation_completed_at") is not None
        or (isinstance(expires_dt, datetime) and expires_dt < now)
    )
    if needs_new:
        activation_token = secrets.token_urlsafe(32)
        await db.partner_applications.update_one(
            {"id": application_id},
            {"$set": {
                "activation_token": activation_token,
                "activation_token_expires_at": (now + timedelta(days=14)).isoformat(),
                "activation_completed_at": None,
                "updated_at": _now(),
            }},
        )
    partner = await db.partner_engineers.find_one(
        {"id": app.get("partner_id")}, {"_id": 0, "referral_code": 1},
    ) if app.get("partner_id") else None
    referral_code = (partner or {}).get("referral_code")
    try:
        from utils.partner_emails import send_application_approved
        ok = await send_application_approved(
            email=target_email,
            full_name=full_name,
            referral_code=referral_code,
            activation_token=activation_token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner activation email failed: %s", exc)
        raise HTTPException(502, "Email send failed — please retry shortly") from exc
    await _audit(
        partner_id=app.get("partner_id") or "",
        actor_id=user.get("id") or "",
        action="send_activation_link",
        after={"to": target_email, "delivered": bool(ok), "token_reissued": needs_new},
    )
    return {
        "ok": bool(ok),
        "kind": "activation",
        "sent_to": target_email,
        "application_id": application_id,
    }


# ═══════════════════════════════════════════════════════════════
# Iter 219f — Activation flow.
# After approval, the welcome email points to /partner-engineer/activate
# ?token=<single-use>. The page hits these two endpoints to:
#   1. GET-style POST `/partners/activation/info` — validate the token and
#      return the applicant's name/email so the form can be pre-filled.
#   2. POST `/partners/activation/complete` — create the user account (or
#      mint a login token for an existing matching user) and consume the
#      token. The new user is auto-linked to the partner row via the
#      iter 219e claim helper so the dashboard works immediately.
# ═══════════════════════════════════════════════════════════════


async def _find_active_activation(token: str) -> Optional[dict]:
    """Token lookup with all the safety rails — returns None for any
    invalid/expired/consumed token. Public-facing so we deliberately
    keep the error messages generic."""
    if not token or not isinstance(token, str) or len(token) < 16:
        return None
    app = await db.partner_applications.find_one({"activation_token": token}, {"_id": 0})
    if not app:
        return None
    if app.get("activation_completed_at"):
        return None
    expires = app.get("activation_token_expires_at")
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            expires = None
    if isinstance(expires, datetime) and expires < datetime.now(timezone.utc):
        return None
    if app.get("status") != "approved":
        return None
    return app


@router.post("/partners/activation/info")
async def get_partner_activation_info(body: dict = Body(default_factory=dict)):
    """Public — token → {email, full_name, has_existing_account}.
    Used by the activation page to pre-fill the form and decide
    whether to show the password-set flow or a "sign in to claim"
    flow when the email already has a GymAxis account."""
    token = (body.get("token") or "").strip()
    app = await _find_active_activation(token)
    if not app:
        raise HTTPException(404, "This activation link is invalid or has expired. Ask the GymAxis team for a new one.")
    email = app.get("email") or ""
    has_account = bool(await db.users.find_one(
        {"email": safe_regex_exact(email)},
        {"_id": 0, "id": 1},
    )) if email else False
    return {
        "email": email,
        "full_name": app.get("full_name") or "",
        "has_existing_account": has_account,
    }


@router.post("/partners/activation/complete")
async def complete_partner_activation(
    body: dict = Body(default_factory=dict),
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
):
    """Public — consumes the token, creates the user account (or
    authenticates an existing one), runs the partner-claim hook so
    the user is linked to their `partner_engineers` row, then returns
    a fresh JWT + a `next_url` that points at Stripe Checkout for the
    £30/mo Partner Plan.

    Body shape:
      { token: <str>, password: <str> }
    """
    token = (body.get("token") or "").strip()
    password = (body.get("password") or "").strip()
    if not password or len(password) < 8:
        raise HTTPException(400, "Choose a password of at least 8 characters.")
    app = await _find_active_activation(token)
    if not app:
        raise HTTPException(404, "This activation link is invalid or has expired. Ask the GymAxis team for a new one.")

    email = (app.get("email") or "").strip()
    full_name = app.get("full_name") or ""
    if not email:
        raise HTTPException(400, "Application is missing an email address — contact support.")

    # Lazy import so circular deps don't bite cold-start.
    from utils.auth import hash_password, create_token, set_auth_cookie
    from utils.security import validate_password_strength
    validate_password_strength(password)

    existing_user = await db.users.find_one(
        {"email": safe_regex_exact(email)}, {"_id": 0},
    )
    if existing_user:
        # User already exists — refuse to silently overwrite their
        # password from a token. Send them to /login with email
        # pre-filled and a `?next` that resumes the subscribe flow.
        raise HTTPException(409, (
            "An account already exists for this email. Please sign in to claim your "
            "partner approval (we'll then take you to Stripe to set up your £30/mo plan)."
        ))

    # Fresh account creation — mirror the minimum path from /auth/register.
    user_id = _new_id()
    user_doc = {
        "id": user_id,
        "email": email,
        "password": hash_password(password),
        "full_name": (full_name or "").strip(),
        "organization_id": None,
        "role": "engineer_partner",
        "account_type": "partner_engineer",
        "is_partner_engineer": True,
        "created_at": _now(),
        "password_updated_at": _now(),
        "activated_via": "partner_application",
        "activated_from_application_id": app["id"],
    }
    await db.users.insert_one(user_doc)

    # Claim the pending partner row immediately (don't wait for next login).
    try:
        from utils.partner_claim import claim_pending_partner_for_user
        await claim_pending_partner_for_user(email, user_id)
    except Exception:  # noqa: BLE001
        logger.exception("[partners] post-activation claim failed")

    # Burn the token so the link can't be replayed.
    await db.partner_applications.update_one(
        {"id": app["id"]},
        {"$set": {
            "activation_completed_at": _now(),
            "activated_user_id": user_id,
            "updated_at": _now(),
        }},
    )

    # Audit trail.
    try:
        await _audit(
            partner_id=app.get("partner_id") or "",
            actor_id=user_id,
            action="activation_completed",
            after={"email": email, "application_id": app["id"]},
        )
    except Exception:  # noqa: BLE001
        logger.exception("[partners] activation audit failed")

    token_str = create_token(user_id)
    if response is not None:
        set_auth_cookie(response, token_str)

    # Frontend deep-link that auto-fires Stripe Checkout.
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    next_url = f"{base}/partner-engineer?action=subscribe" if base else "/partner-engineer?action=subscribe"
    return {
        "token": token_str,
        "user": {"id": user_id, "email": email, "full_name": full_name, "role": "engineer_partner"},
        "next_url": next_url,
    }


@router.post("/partners/applications/{application_id}/reject")
async def reject_partner_application(
    application_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Iter 218 — reject an application with an optional reason. No
    partner row is ever created on this path."""
    _require_master_admin(user)
    app = await db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(404, "Application not found")
    if app.get("status") in {"approved", "rejected"}:
        raise HTTPException(400, f"Application already {app['status']}")

    reason = ((body or {}).get("reason") or "").strip()[:1000]
    await db.partner_applications.update_one(
        {"id": application_id},
        {"$set": {
            "status": "rejected",
            "rejected_at": _now(),
            "rejected_by": user.get("id"),
            "reviewer_notes": reason or None,
            "updated_at": _now(),
        }},
    )
    await _audit(
        partner_id=application_id, actor_id=user.get("id") or "", action="reject_application",
        before={"status": app.get("status")}, after={"status": "rejected"},
        note=reason,
    )

    # Iter 219c — fix: rejection email was missing entirely on this path,
    # so engineers we declined never heard back. Now sends a polite
    # rejection with the optional reason. Wrapped so an SMTP outage
    # doesn't undo the rejection.
    try:
        from utils.partner_emails import send_application_rejected
        await send_application_rejected(
            email=app["email"],
            full_name=app.get("full_name") or "",
            reason=reason or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner application-rejected email failed: %s", exc)

    return {"ok": True, "application_id": application_id, "status": "rejected"}


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
    """Active **gym** referrals — orgs that signed up via the partner's
    referral code and are still on a paid plan."""
    return await db.partner_referrals.count_documents({
        "partner_id": partner_id,
        "status": "active",
    })


async def _approved_engineer_referral_count(partner_id: str) -> int:
    """Iter 216h287 — Gap 9: engineer-of-engineer referrals. Counts
    approved fellow-engineer recruits. Each one contributes to the
    same tier-credit ladder as a gym referral (the BA-audit decision).
    """
    return await db.engineer_referrals.count_documents({
        "referrer_partner_id": partner_id,
        "status": "approved",
    })


async def _combined_active_count(partner_id: str) -> int:
    """Sum of gym + engineer referrals used to drive the app-fee tier.
    Single source of truth — call this anywhere the tier matters."""
    gym = await _active_referral_count(partner_id)
    eng = await _approved_engineer_referral_count(partner_id)
    return gym + eng


async def _recompute_app_fee(partner_id: str) -> dict:
    """Recompute the partner's app-fee tier off the live active count.
    Persists `app_fee_tier` + `enhanced_review_required` and returns the
    tier. Also re-syncs the live Stripe subscription (if any) so that
    crossing a milestone (£30 → £15 → free) automatically transitions
    the partner's billing without a manual round-trip.

    Iter 216h287 — the count is now `gym + engineer` referrals so a
    partner who recruits 10 fellow engineers gets the same free-tier
    unlock as one who refers 10 gyms.
    """
    count = await _combined_active_count(partner_id)
    eng_count = await _approved_engineer_referral_count(partner_id)
    tier = _app_fee_tier(count)
    previous = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0, "app_fee_tier": 1, "subscription": 1})
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {
            "active_referral_count": count,
            "engineer_referral_count": eng_count,
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


def _partner_plan_price_id_for_tier(tier: dict, country_code: Optional[str] = None) -> Optional[str]:
    """Return the env-configured Stripe price ID matching this tier's
    `price_gbp` — or None when the tier is free (no subscription needed)
    or when the env var is unset (production must seed the price IDs).

    Iter 265 — US engineers (``country_code == 'US'``) get the USD price when
    its env var is set, falling back to the GBP price so nothing breaks when the
    USD prices haven't been seeded yet."""
    gbp_key = PARTNER_PLAN_PRICE_IDS_BY_TIER.get(tier.get("price_gbp"))
    if (country_code or "").strip().upper() == "US":
        usd_key = PARTNER_PLAN_PRICE_IDS_BY_TIER_USD.get(tier.get("price_gbp"))
        usd_price = os.environ.get(usd_key) if usd_key else None
        if usd_price:
            return usd_price
    if not gbp_key:
        return None
    return os.environ.get(gbp_key) or None


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

    target_price_id = _partner_plan_price_id_for_tier(tier, await _partner_country(partner))
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
            stripe.Subscription.modify(
                sub_id, cancel_at_period_end=True,
                idempotency_key=_stripe_idem_key("partner_auto_cancel", partner_id, sub_id),
            )
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
                stripe.Subscription.modify(
                    sub_id, cancel_at_period_end=False,
                    idempotency_key=_stripe_idem_key("partner_auto_uncancel", partner_id, sub_id),
                )
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
            idempotency_key=_stripe_idem_key("partner_price_swap", partner_id, target_price_id),
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


@router.put("/partners/me/compliance")
async def update_my_compliance(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Iter 216h281 — Gap 2: engineer self-service for insurance + cert
    expiry dates. Triggered from the dashboard when the nightly job
    flagged the partner as ``compliance_paused``.

    Body: ``{insurance_expires_at?: ISO, qualifications_expires_at?: ISO,
              insurance_provider?: str, has_insurance?: bool}``
    """
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    updates: dict = {"updated_at": _now()}
    if "insurance_expires_at" in body:
        updates["insurance_expires_at"] = _parse_iso_date(body.get("insurance_expires_at"))
    if "qualifications_expires_at" in body:
        updates["qualifications_expires_at"] = _parse_iso_date(body.get("qualifications_expires_at"))
    if "insurance_provider" in body:
        updates["insurance_provider"] = (body.get("insurance_provider") or "").strip()[:200] or None
    if "has_insurance" in body:
        updates["has_insurance"] = bool(body.get("has_insurance"))
    if len(updates) == 1:
        raise HTTPException(400, "Nothing to update")

    # Determine if the new dates clear the compliance pause.
    insurance_ok = _is_doc_valid(updates.get("insurance_expires_at") if "insurance_expires_at" in updates else partner.get("insurance_expires_at"))
    quals_ok = _is_doc_valid(updates.get("qualifications_expires_at") if "qualifications_expires_at" in updates else partner.get("qualifications_expires_at"))
    if partner.get("compliance_paused") and insurance_ok and quals_ok:
        # Auto-reactivate.
        updates["compliance_paused"] = False
        updates["compliance_pause_reason"] = None
    await db.partner_engineers.update_one({"id": partner["id"]}, {"$set": updates})
    await _audit(partner_id=partner["id"], actor_id=user["id"], action="compliance_updated",
                 after={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in updates.items() if k != "updated_at"})
    refreshed = _public(await db.partner_engineers.find_one({"id": partner["id"]}))
    return {"ok": True, "partner": refreshed}


# Iter 220l — Tax / VAT self-service. Engineers below the £85k VAT
# threshold (≈ 99% of sole-trader Partner Engineers) must NOT charge
# VAT. Letting them tick "Not VAT registered" once means every
# invoice PDF from this engineer hides the VAT line automatically —
# instead of them remembering to set rate=0 on every quote/invoice.
@router.put("/partners/me/tax-settings")
async def update_my_tax_settings(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Body: `{vat_registered: bool, vat_number?: str}`.

    `vat_registered` defaults to True for backward compatibility. When
    it flips to False, subsequent invoices/quotes generated by this
    engineer will set `vat_rate=0`, `vat_exempt=True`, and render
    "VAT not chargeable (engineer below £85k threshold)" in place
    of the VAT row on the PDF.
    """
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    updates: dict = {"updated_at": _now()}
    if "vat_registered" in body:
        updates["vat_registered"] = bool(body.get("vat_registered"))
    if "vat_number" in body:
        raw = (body.get("vat_number") or "").strip().upper().replace(" ", "")
        updates["vat_number"] = raw[:20] or None
    if len(updates) == 1:
        raise HTTPException(400, "Nothing to update")
    if updates.get("vat_registered") is False:
        updates["vat_number"] = None  # belt + braces — clear the number on un-tick
    await db.partner_engineers.update_one({"id": partner["id"]}, {"$set": updates})
    await _audit(partner_id=partner["id"], actor_id=user["id"], action="tax_settings_updated",
                 after={k: v for k, v in updates.items() if k != "updated_at"})
    refreshed = _public(await db.partner_engineers.find_one({"id": partner["id"]}))
    return {"ok": True, "partner": refreshed}


# Iter 220cr — Engineer pricing defaults.
# Lets the engineer set their callout fee + hourly labour rate +
# mileage rate + parts markup ONCE in account settings, so every
# new quote/invoice line auto-fills with the right number. These
# values already exist on `partner_engineers.rates` because the
# referral flow uses them — we just expose a setter.
@router.put("/partners/me/rates")
async def update_my_rates(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Body: `{callout_fee: float, labour_rate_per_hour: float,
    mileage_rate: float, parts_markup_pct: float}`. All optional —
    only supplied fields are updated. Values must be ≥ 0."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    rates = dict(partner.get("rates") or {})
    allowed = {
        "callout_fee", "labour_rate_per_hour",
        "mileage_rate", "parts_markup_pct",
    }
    touched = False
    for k in allowed:
        if k in body:
            try:
                v = float(body[k])
            except (TypeError, ValueError):
                raise HTTPException(422, f"{k} must be a number")
            if v < 0:
                raise HTTPException(422, f"{k} must be >= 0")
            rates[k] = round(v, 2)
            touched = True
    if not touched:
        raise HTTPException(400, "Nothing to update")
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"rates": rates, "updated_at": _now()}},
    )
    await _audit(
        partner_id=partner["id"], actor_id=user["id"],
        action="rates_updated", after=rates,
    )
    refreshed = _public(await db.partner_engineers.find_one({"id": partner["id"]}))
    return {"ok": True, "partner": refreshed, "rates": rates}


# Iter 220m — Master-admin trigger for the monthly reputation report.
# Operational hook for manual resends + a smoke target for tests.
@router.post("/partners/admin/{partner_id}/send-reputation-report")
async def admin_send_reputation_report(
    partner_id: str,
    body: dict | None = Body(default=None),
    user: dict = Depends(get_current_user),
):
    """Body (optional): `{period: "YYYY-MM"}`. Defaults to previous
    calendar month. Master-admin only."""
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    from utils.reputation_reports import (
        _previous_period as _rr_prev,
        send_monthly_report_to,
    )
    body = body or {}
    period = (body.get("period") or "").strip()
    if period:
        try:
            year_s, month_s = period.split("-")
            year, month = int(year_s), int(month_s)
        except ValueError:
            raise HTTPException(400, "period must be YYYY-MM")
    else:
        today = datetime.now(timezone.utc).date()
        year, month = _rr_prev(today.year, today.month)
    result = await send_monthly_report_to(partner, year, month)
    if result.get("sent"):
        await db.partner_engineers.update_one(
            {"id": partner_id},
            {"$set": {
                "reputation_reports.last_sent_period": f"{year:04d}-{month:02d}",
                "reputation_reports.last_sent_at": _now(),
            }},
        )
    return result


def _is_doc_valid(expires_at) -> bool:
    """A doc is "valid" if its expiry is unset (we haven't asked) or in
    the future. None means we never collected it — we treat that as
    allow-list during the rollout so existing approved partners aren't
    instantly paused. Future iter can flip this to False once the
    backfill is complete."""
    if expires_at is None:
        return True
    if not isinstance(expires_at, datetime):
        return True
    expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


# ── Iter 216h283 — Gap 4: DBS / RTW / Safeguarding / Public Liability ─


def _parse_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(str(value).strip()) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def _store_compliance_attachment(file: UploadFile, partner_id: str, kind: str) -> tuple[dict, bytes, str]:
    """Save a compliance doc file using the existing put_object pipeline.

    Returns ``(file_dict, raw_bytes, content_type)`` so the caller can
    immediately ship the bytes to the AI checker without re-reading
    from storage.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > _CV_MAX_BYTES:
        raise HTTPException(400, f"File too large — keep compliance docs under {_CV_MAX_BYTES // (1024 * 1024)} MB")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin").lower()
    if ext not in _CV_ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type .{ext}")
    path = f"{APP_NAME}/partner-compliance/{partner_id}/{kind}/{uuid.uuid4()}.{ext}"
    stored = put_object(path, data, file.content_type or "application/octet-stream")
    return ({
        "id": _new_id(),
        "original_filename": file.filename or f"{kind}.{ext}",
        "content_type": file.content_type or "application/octet-stream",
        "size": len(data),
        "storage_path": stored.get("path", path),
        "download_url": stored.get("url", stored.get("path", path)),
        "uploaded_at": _now(),
    }, data, file.content_type or "application/octet-stream")


async def _compliance_country(user: dict) -> str:
    """Iter 220p1 / 265 — the engineer's compliance market (drives which docs
    are required: UK→DBS/RTW, US→work authorization/background check). Resolved
    from the org country_code, then the independent engineer's market chosen at
    signup (``partner_engineers.country_code``); defaults to GB."""
    from utils.localization import engineer_localization
    return (await engineer_localization(user))["country_code"]



@router.put("/partners/me/compliance-docs/{kind}")
async def upload_my_compliance_doc(
    kind: str,
    user: dict = Depends(get_current_user),
    # File upload (optional — engineer can submit metadata first, file later)
    file: Optional[UploadFile] = File(None),
    # Common metadata
    expires_at: str = Form(""),
    # DBS-specific
    dbs_certificate_number: str = Form(""),
    dbs_update_service_number: str = Form(""),
    dbs_check_date: str = Form(""),
    dbs_check_level: str = Form(""),
    # RTW-specific
    rtw_document_type: str = Form(""),
    rtw_share_code: str = Form(""),
    # Safeguarding-specific
    safeguarding_issuer: str = Form(""),
    safeguarding_completed_at: str = Form(""),
    # Public liability-specific
    pl_provider: str = Form(""),
    pl_policy_number: str = Form(""),
    pl_cover_amount: str = Form(""),
    # Iter 220p1 — US work-authorization (I-9 / work eligibility)
    wa_document_type: str = Form(""),
    wa_reference: str = Form(""),
    # Iter 220p1 — US background check
    bg_provider: str = Form(""),
    bg_completed_at: str = Form(""),
    bg_reference: str = Form(""),
):
    """Engineer self-service compliance doc submission.

    Validates the kind, encrypts sensitive numbers, stores the file
    via the existing object-storage helper, runs the AI vision check
    immediately, and resets ``verified_at`` to None so the admin
    re-signs off on every new upload.
    """
    from utils.partner_compliance_docs import (
        DBS_LEVELS, DOC_KINDS, RTW_DOC_TYPES, WA_DOC_TYPES,
        ai_check_document, default_doc_shell, encrypt_field, last4, validate_kind,
    )
    validate_kind(kind)
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")

    blob: dict = (partner.get("compliance_docs") or {}).get(kind) or default_doc_shell()

    # ── Per-kind metadata ────────────────────────────────────────────
    if kind == "dbs":
        if dbs_certificate_number:
            blob["certificate_number_enc"] = encrypt_field(dbs_certificate_number)
            blob["certificate_last4"] = last4(dbs_certificate_number)
        if dbs_update_service_number:
            blob["update_service_number_enc"] = encrypt_field(dbs_update_service_number)
            blob["update_service_last4"] = last4(dbs_update_service_number)
        if dbs_check_date:
            blob["check_date"] = _parse_iso_date(dbs_check_date)
        if dbs_check_level:
            level = dbs_check_level.strip().lower()
            if level not in DBS_LEVELS:
                raise HTTPException(400, f"dbs_check_level must be one of {sorted(DBS_LEVELS)}")
            blob["check_level"] = level
    elif kind == "rtw":
        if rtw_document_type:
            doc_t = rtw_document_type.strip().lower()
            if doc_t not in RTW_DOC_TYPES:
                raise HTTPException(400, f"rtw_document_type must be one of {sorted(RTW_DOC_TYPES)}")
            blob["document_type"] = doc_t
        if rtw_share_code:
            blob["share_code_enc"] = encrypt_field(rtw_share_code)
            blob["share_code_last4"] = last4(rtw_share_code)
    elif kind == "safeguarding":
        if safeguarding_issuer:
            blob["issuer"] = safeguarding_issuer.strip()[:200]
        if safeguarding_completed_at:
            blob["completed_at"] = _parse_iso_date(safeguarding_completed_at)
    elif kind == "public_liability":
        if pl_provider:
            blob["provider"] = pl_provider.strip()[:200]
        if pl_policy_number:
            blob["policy_number_enc"] = encrypt_field(pl_policy_number)
            blob["policy_number_last4"] = last4(pl_policy_number)
        cover = _parse_int(pl_cover_amount)
        if cover is not None:
            blob["cover_amount"] = cover
    elif kind == "work_authorization":
        # Iter 220p1 — US I-9 / work-eligibility evidence.
        if wa_document_type:
            wa_t = wa_document_type.strip().lower()
            if wa_t not in WA_DOC_TYPES:
                raise HTTPException(400, f"wa_document_type must be one of {sorted(WA_DOC_TYPES)}")
            blob["document_type"] = wa_t
        if wa_reference:
            blob["reference_enc"] = encrypt_field(wa_reference)
            blob["reference_last4"] = last4(wa_reference)
    elif kind == "background_check":
        # Iter 220p1 — US criminal background check (e.g. Checkr).
        if bg_provider:
            blob["provider"] = bg_provider.strip()[:200]
        if bg_completed_at:
            blob["completed_at"] = _parse_iso_date(bg_completed_at)
        if bg_reference:
            blob["reference_enc"] = encrypt_field(bg_reference)
            blob["reference_last4"] = last4(bg_reference)

    if expires_at:
        blob["expires_at"] = _parse_iso_date(expires_at)

    # ── File + AI check ──────────────────────────────────────────────
    if file is not None:
        file_dict, raw_bytes, content_type = await _store_compliance_attachment(file, partner["id"], kind)
        blob["file"] = file_dict
        blob["uploaded_at"] = _now()
        # Reset verification on every new upload — the admin must
        # re-sign off after a doc replacement.
        blob["verified_at"] = None
        blob["verified_by"] = None
        # Fire-and-forget AI check (synchronous so the engineer sees
        # the result immediately, but wrapped to never break the
        # upload path).
        try:
            blob["ai_check"] = await ai_check_document(raw_bytes, content_type, expected_kind=kind)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI compliance check threw: %s", exc)
            blob["ai_check"] = {"status": "error", "notes": str(exc)[:200], "checked_at": _now()}

    # ── Persist & re-evaluate compliance pause ───────────────────────
    docs = dict(partner.get("compliance_docs") or {})
    docs[kind] = blob

    # Soft auto-unpause: if every uploaded doc with an expiry is still
    # in the future, drop the compliance_paused flag.
    from utils.partner_compliance_docs import required_doc_kinds
    _country = await _compliance_country(user)
    _req_kinds = required_doc_kinds(_country)
    paused = bool(partner.get("compliance_paused"))
    if paused:
        all_ok = all(_is_doc_valid((docs.get(k) or {}).get("expires_at")) for k in _req_kinds)
        if all_ok:
            paused = False

    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {
            "compliance_docs": docs,
            "compliance_paused": paused,
            "updated_at": _now(),
        }},
    )
    await _audit(partner_id=partner["id"], actor_id=user["id"], action=f"compliance_doc_{kind}_uploaded",
                 after={"has_file": blob.get("file") is not None, "ai_status": (blob.get("ai_check") or {}).get("status")})
    # Return only sanitised view so we never echo the ciphertext back.
    from utils.partner_compliance_docs import sanitise_docs_for_response, overall_status
    return {
        "ok": True,
        "compliance_docs": sanitise_docs_for_response(docs),
        "status": overall_status(docs, _country),
    }


@router.get("/partners/me/compliance-docs")
async def get_my_compliance_docs(user: dict = Depends(get_current_user)):
    """Sanitised compliance docs for the engineer dashboard."""
    from utils.partner_compliance_docs import (
        sanitise_docs_for_response, overall_status, required_doc_kinds, default_doc_shell,
    )
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    docs = partner.get("compliance_docs") or {}
    # Iter 220p1 — the required doc set follows the engineer's market
    # (UK: DBS/RTW/Safeguarding; US: work authorization/background check).
    country = await _compliance_country(user)
    kinds = required_doc_kinds(country)
    # Make sure the UI never has to handle missing keys.
    full = {k: docs.get(k) or default_doc_shell() for k in kinds}
    return {
        "compliance_docs": sanitise_docs_for_response(full),
        "status": overall_status(docs, country),
        "compliance_paused": bool(partner.get("compliance_paused")),
        "country_code": country,
        "required_kinds": list(kinds),
        # Iter 220ea·47 — trial grace window so the dashboard can show the
        # "upload within X days" countdown instead of an alarming 0/4.
        "grace": _compliance_grace_info(partner),
        "claim_doc_kinds": list(_claim_required_kinds(country)),
    }


@router.post("/master-admin/partners/{partner_id}/verify-doc")
async def admin_verify_compliance_doc(
    partner_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Master admin signs off on a compliance doc.

    Body: ``{kind: "dbs|rtw|safeguarding|public_liability", verified: bool, note?: str}``
    Setting ``verified=False`` clears any prior verification and adds
    the rejection note to the doc's audit trail.
    """
    from utils.partner_compliance_docs import sanitise_docs_for_response, validate_kind
    _require_master_admin(user)
    kind = validate_kind((body.get("kind") or "").strip().lower())
    verified = bool(body.get("verified", True))

    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    docs = dict(partner.get("compliance_docs") or {})
    blob = dict(docs.get(kind) or {})
    if not blob.get("file"):
        raise HTTPException(400, f"No {kind} doc to verify yet — engineer must upload first.")
    if verified:
        blob["verified_at"] = _now()
        blob["verified_by"] = user["id"]
        blob["rejection_note"] = None
    else:
        blob["verified_at"] = None
        blob["verified_by"] = None
        note = (body.get("note") or "").strip()[:400]
        if note:
            blob["rejection_note"] = note
    docs[kind] = blob
    await db.partner_engineers.update_one(
        {"id": partner_id},
        {"$set": {"compliance_docs": docs, "updated_at": _now()}},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action=f"compliance_doc_{kind}_verified",
                 after={"verified": verified})
    return {"ok": True, "compliance_docs": sanitise_docs_for_response(docs)}


async def _partner_country(partner: dict) -> str:
    """Iter 220p1 / 265 — resolve a partner engineer's compliance market.
    The market they chose at signup (``partner_engineers.country_code``) wins;
    else the org they operate under (their user's org); defaults to GB."""
    from utils.localization import org_localization
    if partner.get("country_code"):
        return org_localization({"country_code": partner["country_code"]})["country_code"]
    org_id = partner.get("owner_organization_id") or partner.get("organization_id")
    if not org_id:
        u = await db.users.find_one(
            {"id": partner.get("user_id")}, {"_id": 0, "organization_id": 1},
        )
        org_id = (u or {}).get("organization_id")
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "country_code": 1},
    ) if org_id else None
    return org_localization(org)["country_code"]


@router.get("/master-admin/partners/{partner_id}/compliance-docs")
async def admin_get_compliance_docs(partner_id: str, user: dict = Depends(get_current_user)):
    """Full compliance view for the admin verification panel."""
    from utils.partner_compliance_docs import (
        sanitise_docs_for_response, overall_status, required_doc_kinds, default_doc_shell,
    )
    _require_master_admin(user)
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partner not found")
    docs = partner.get("compliance_docs") or {}
    country = await _partner_country(partner)
    kinds = required_doc_kinds(country)
    full = {k: docs.get(k) or default_doc_shell() for k in kinds}
    return {
        "compliance_docs": sanitise_docs_for_response(full),
        "status": overall_status(docs, country),
        "country_code": country,
        "required_kinds": list(kinds),
    }


# ── End of iter 216h283 compliance-docs block ───────────────────────


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
        # Iter 216h287 — Gap 9: capture eref attribution on the authed
        # apply path too. The legacy form omits it; the engineer-side
        # invite link surfaces it via `eref` in the request body.
        eref_authed = (body.get("referred_by_eref") or "").strip().upper()
        if eref_authed and user.get("email"):
            referrer = await _resolve_eref_partner(eref_authed)
            if referrer:
                await _record_engineer_referral(
                    referrer_partner_id=referrer["id"],
                    referrer_code=referrer["referral_code"],
                    referred_email=user["email"],
                    referred_application_id=None,
                )

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


# ── Iter 216h284 — Gap 5: first-7-days activation checklist ──────────


@router.get("/partners/me/checklist")
async def get_my_checklist(user: dict = Depends(get_current_user)):
    """Pure-read endpoint — the dashboard hits this on mount + after
    any meaningful action (subscription, compliance upload). Computes
    the checklist from the latest partner record so we never serve
    stale completion state."""
    from utils.partner_checklist import build_checklist
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    referrals_count = await db.partner_referrals.count_documents({"partner_id": partner["id"]})
    return {"checklist": build_checklist(partner, referrals_count, await _compliance_country(user))}


@router.post("/partners/me/checklist/ack")
async def ack_my_checklist_step(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Mark one of the manually-ackable steps as done (currently only
    `referral_link_copied`). Idempotent — re-acking is a no-op."""
    from utils.partner_checklist import ack_field_name, build_checklist, is_ackable
    key = (body.get("key") or "").strip()
    if not is_ackable(key):
        raise HTTPException(400, "Step is not user-ackable — auto-resolved from your profile.")
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    # Only set the timestamp the first time so we preserve "completed on …".
    cl = partner.get("checklist") or {}
    if not cl.get(f"{key}_at"):
        await db.partner_engineers.update_one(
            {"id": partner["id"]},
            {"$set": {ack_field_name(key): _now(), "updated_at": _now()}},
        )
        await _audit(partner_id=partner["id"], actor_id=user["id"],
                     action="checklist_acked", after={"key": key})
        partner["checklist"] = {**cl, f"{key}_at": _now()}
    referrals_count = await db.partner_referrals.count_documents({"partner_id": partner["id"]})
    return {"ok": True, "checklist": build_checklist(partner, referrals_count, await _compliance_country(user))}


@router.get("/partners/me/collateral/{kind}")
async def get_my_collateral(kind: str, user: dict = Depends(get_current_user)):
    """Iter 216h285 — Gap 6: return a referral-collateral asset.

    Supported kinds:
      * ``qr-poster``   — A4 portrait PNG with a large QR code.
      * ``social-card`` — 1200×630 PNG sized for Instagram/LinkedIn/X.
      * ``pdf-pitch``   — single-page A4 PDF pitch deck.

    Generated in-memory from the partner's referral code + link. No
    files persisted; the browser caches for an hour so the engineer
    can hammer the dashboard download buttons without flooding the API.
    """
    from utils.partner_collateral import generate, COLLATERAL_KINDS
    if kind not in COLLATERAL_KINDS:
        raise HTTPException(400, f"Unknown collateral kind '{kind}' — expected one of {sorted(COLLATERAL_KINDS)}")
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    if partner.get("status") != "approved":
        raise HTTPException(403, "Approved partners only — your application is still in review.")
    referral_url = _public_referral_link(partner["referral_code"])
    try:
        data, mime, filename = generate(
            kind=kind,
            full_name=partner.get("full_name", ""),
            referral_code=partner["referral_code"],
            referral_url=referral_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Collateral generation failed (%s): %s", kind, exc)
        raise HTTPException(500, "Could not generate the collateral file — please retry.") from exc
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


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


async def _create_partner_checkout_session(partner: dict, origin_url: str) -> dict:
    """Shared Stripe Checkout creation for the Partner Engineer Plan.

    Used by both the authed subscription endpoint AND the public
    trial-feedback "accept & pay" flow (where the engineer may not be
    logged in). Price auto-selects from the partner's current app-fee tier.
    """
    tier = await _recompute_app_fee(partner["id"])
    if tier["price_gbp"] == 0:
        raise HTTPException(400, "You're on the free tier — no subscription needed")
    partner_market = await _partner_country(partner)
    price_id = _partner_plan_price_id_for_tier(tier, partner_market)
    if not price_id:
        raise HTTPException(
            501,
            "Partner Plan Stripe price IDs not configured — ask Master Admin to set "
            "STRIPE_PRICE_PARTNER_PLAN_30 and STRIPE_PRICE_PARTNER_PLAN_15 in the env.",
        )
    origin_url = (origin_url or "").rstrip("/") or (
        os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    ).rstrip("/")
    if not origin_url:
        raise HTTPException(400, "origin_url is required")
    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
    except ImportError:
        raise HTTPException(503, "Stripe SDK unavailable")

    email = partner.get("email") or ""
    success_url = f"{origin_url}/partner-engineer?subscription=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/partner-engineer?subscription=cancelled"
    metadata = {
        "partner_id": partner["id"],
        "user_id": partner.get("user_id") or "",
        "user_email": email,
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
            customer_email=email or None,
            metadata=metadata,
            subscription_data={"metadata": metadata},
            idempotency_key=_stripe_idem_key("partner_plan_checkout", partner["id"], price_id),
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
    return await _create_partner_checkout_session(partner, body.get("origin_url") or "")


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
        stripe.Subscription.modify(
            sub_id, cancel_at_period_end=True,
            idempotency_key=_stripe_idem_key("partner_sub_cancel", partner["id"], sub_id),
        )
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
        stripe.Subscription.modify(
            sub_id, cancel_at_period_end=False,
            idempotency_key=_stripe_idem_key("partner_sub_resume", partner["id"], sub_id),
        )
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
    # Iter 220ea·31 — a trial engineer who paid has converted. Close out
    # the trial lifecycle so the worker stops chasing them for feedback /
    # suspension, and re-open access if a lapse had suspended them.
    paid_partner = await db.partner_engineers.find_one(
        {"id": partner_id}, {"_id": 0, "trial": 1, "status": 1})
    if paid_partner and (paid_partner.get("trial") or {}).get("status") not in (None, "converted_paid"):
        trial_set = {"trial.status": "converted_paid", "trial.converted_at": _now()}
        if paid_partner.get("status") == "suspended":
            trial_set["status"] = "approved"  # paying lifts a trial-expiry suspension
        await db.partner_engineers.update_one({"id": partner_id}, {"$set": trial_set})
        await _audit(partner_id=partner_id, actor_id="system",
                     action="trial_converted_paid", after={"stripe_subscription_id": sub_id})
    await _audit(partner_id=partner_id, actor_id="system",
                 action="subscription_activated",
                 after={"stripe_subscription_id": sub_id, "stripe_customer_id": customer_id})
    return {"partner_id": partner_id, "subscription_id": sub_id}


async def _handle_partner_loss_of_access(partner_id: str, reason: str) -> dict:
    """Iter 220k — Mid-job recovery. When an engineer loses access
    (subscription cancelled, suspended), the in-flight cases they were
    assigned to must be flipped back to the dispatch queue so the
    case-owning org can reassign them — otherwise the customer is
    stranded.

    "In-flight" = any of the active engineering states. Closed,
    invoiced and rejected cases are left untouched (they're already
    historical).

    Returns ``{cases_reassigned: int, notified_orgs: int}`` for audit.
    """
    from utils.svc_state import (
        ASSIGNED, EN_ROUTE, ON_SITE, PAUSED_PARTS, PAUSED_CUSTOMER,
        REPAIRED, AWAITING_SIGN_OFF, NEW, append_event,
    )
    partner = await db.partner_engineers.find_one({"id": partner_id}, {"_id": 0, "user_id": 1, "full_name": 1})
    if not partner or not partner.get("user_id"):
        return {"cases_reassigned": 0, "notified_orgs": 0}
    user_id = partner["user_id"]
    in_flight_states = [ASSIGNED, EN_ROUTE, ON_SITE, PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED, AWAITING_SIGN_OFF]
    cursor = db.svc_cases.find(
        {"assigned_engineer_id": user_id, "status": {"$in": in_flight_states}},
        {"_id": 0, "id": 1, "organization_id": 1, "reference": 1, "title": 1, "status": 1},
    )
    cases = await cursor.to_list(500)
    if not cases:
        return {"cases_reassigned": 0, "notified_orgs": 0}
    eng_name = partner.get("full_name") or "the engineer"
    now_iso = _now()
    orgs_touched: set[str] = set()
    for c in cases:
        await db.svc_cases.update_one(
            {"id": c["id"]},
            {
                "$set": {
                    "status": NEW,
                    "assigned_engineer_id": None,
                    "assigned_engineer_name": None,
                    "needs_reassignment": True,
                    "needs_reassignment_reason": reason,
                    "updated_at": now_iso,
                },
            },
        )
        try:
            await append_event(
                case_id=c["id"],
                organization_id=c.get("organization_id"),
                event_type="system",
                actor=None,
                body=f"Engineer {eng_name} lost access ({reason}). Case unassigned and returned to dispatch queue.",
                extra={"kind": "partner_access_lost", "reason": reason, "previous_status": c.get("status")},
            )
        except Exception:
            logger.warning(f"[partners] could not append reassignment audit event for case {c['id']!r}")
        if c.get("organization_id"):
            orgs_touched.add(c["organization_id"])

    # Best-effort notify the dispatch admin of each affected org.
    try:
        from utils.email import send_email
        for org_id in orgs_touched:
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1, "support_email": 1})
            if not org:
                continue
            org_cases = [c for c in cases if c.get("organization_id") == org_id]
            to_addr = (org.get("support_email") or "").strip()
            if not to_addr:
                # Fall back to the org owner's email.
                owner = await db.users.find_one(
                    {"organization_id": org_id, "role": "owner"},
                    {"_id": 0, "email": 1},
                )
                to_addr = (owner or {}).get("email", "")
            if not to_addr:
                continue
            rows = "".join(
                f"<li><b>{c.get('reference') or c['id'][:8]}</b> — {c.get('title') or 'Untitled job'}</li>"
                for c in org_cases
            )
            html = (
                f"<p>{eng_name} has lost Partner Engineer access ({reason}) and the following in-flight "
                f"jobs have been returned to your dispatch queue. Please reassign them.</p>"
                f"<ul>{rows}</ul>"
            )
            await send_email(
                to=to_addr,
                subject=f"Action needed: {len(org_cases)} job(s) need reassignment",
                html=html,
                organization_id=org_id,
                category="service",
            )
    except Exception:
        logger.exception("[partners] reassignment notification email failed")

    return {"cases_reassigned": len(cases), "notified_orgs": len(orgs_touched)}


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
    # Iter 220k — Mid-job recovery. If the engineer has just lost
    # access, return their in-flight cases to the dispatch queue and
    # notify the affected orgs so the customer isn't stranded.
    if status in ("canceled", "unpaid", "incomplete_expired"):
        try:
            await _handle_partner_loss_of_access(partner_id, reason=f"subscription_{status}")
        except Exception:
            logger.exception("[partners] mid-job recovery failed for partner %s", partner_id)
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


# ── Iter 216h286 — Gap 8: customer review submission flow ──────────


def _hash_ip(ip: str) -> str:
    """Hash a client IP for soft-rate-limit + abuse audit without
    persisting the cleartext. Single-iteration SHA-256 is fine — this
    is anti-spam scaffolding, not PII protection."""
    import hashlib
    return hashlib.sha256((ip or "").encode()).hexdigest()[:24]


def _moderation_status(rating: int, body: str) -> str:
    """Light heuristic — anything ≤ 3 stars or with hot-button keywords
    lands in `pending` so a human moderator reviews it; everything
    else auto-approves so the engineer's wall stays alive. The admin
    moderation endpoint can flip either way."""
    blocked = ("fraud", "scam", "lawsuit", "thief", "incompetent")
    body_lower = (body or "").lower()
    if rating <= 3 or any(b in body_lower for b in blocked):
        return "pending"
    return "approved"


def _public_review(doc: dict) -> dict:
    """Shape-mapper used by the public list endpoint."""
    return {
        "id": doc["id"],
        "rating": doc["rating"],
        "title": doc.get("title", ""),
        "body": doc.get("body", ""),
        "reviewer_name": doc.get("reviewer_name", "Anonymous"),
        "gym_name": doc.get("gym_name") or None,
        "created_at": doc.get("created_at"),
        "engineer_response": doc.get("engineer_response") or None,
        "engineer_response_at": doc.get("engineer_response_at") or None,
    }


@router.post("/partners/{partner_id}/reviews")
async def submit_review(
    partner_id: str,
    body: dict = Body(...),
    request: Request = None,
):
    """Public endpoint — a gym contact submits a review on a partner.

    Soft-spam controls:
      * IP hash + 24 h cooldown on the (partner, reviewer_email) pair
      * Low-rating + keyword heuristic routes to `pending` moderation
      * Names + emails trimmed and length-capped
    """
    partner = await db.partner_engineers.find_one(
        {"id": partner_id, "status": "approved"}, {"_id": 0, "id": 1, "full_name": 1},
    )
    if not partner:
        raise HTTPException(404, "Engineer not found")

    try:
        rating = int(body.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        raise HTTPException(400, "Rating must be between 1 and 5 stars")

    reviewer_name = (body.get("reviewer_name") or "").strip()[:80]
    reviewer_email = (body.get("reviewer_email") or "").strip().lower()[:200]
    gym_name = (body.get("gym_name") or "").strip()[:120] or None
    title = (body.get("title") or "").strip()[:120]
    review_body = (body.get("body") or "").strip()[:2000]
    job_ref = (body.get("job_reference") or "").strip()[:80] or None
    if not reviewer_name:
        raise HTTPException(400, "reviewer_name is required")
    if not review_body:
        raise HTTPException(400, "Tell us what the engineer did — review body is required")

    # 24h cooldown on (partner, reviewer_email) so a single requester
    # can't flood the page.
    if reviewer_email:
        dup = await db.partner_reviews.find_one(
            {
                "partner_id": partner_id,
                "reviewer_email": reviewer_email,
                "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()},
            },
            {"_id": 0, "id": 1},
        )
        if dup:
            raise HTTPException(429, "You've already submitted a review for this engineer in the last 24 hours.")

    ip = request.client.host if request and request.client else ""
    doc = {
        "id": _new_id(),
        "partner_id": partner_id,
        "rating": rating,
        "title": title,
        "body": review_body,
        "reviewer_name": reviewer_name,
        "reviewer_email": reviewer_email or None,
        "gym_name": gym_name,
        "job_reference": job_ref,
        "ip_hash": _hash_ip(ip),
        "status": _moderation_status(rating, review_body),
        "engineer_response": None,
        "engineer_response_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.partner_reviews.insert_one(doc)
    await _audit(
        partner_id=partner_id, actor_id=None, action="review_submitted",
        after={"review_id": doc["id"], "rating": rating, "status": doc["status"]},
    )
    return {
        "ok": True,
        "review_id": doc["id"],
        "status": doc["status"],
        "message": (
            "Thanks — your review has been published."
            if doc["status"] == "approved"
            else "Thanks — your review will be public once our team has reviewed it."
        ),
    }


@router.get("/partners/{partner_id}/reviews")
async def list_partner_reviews(partner_id: str, limit: int = 50):
    """Public endpoint — returns approved reviews + summary stats so
    the engineer's public card can render trust signals."""
    partner = await db.partner_engineers.find_one(
        {"id": partner_id, "status": "approved"},
        {"_id": 0, "id": 1, "full_name": 1, "company_name": 1, "level": 1, "availability": 1},
    )
    if not partner:
        raise HTTPException(404, "Engineer not found")
    rows = await db.partner_reviews.find(
        {"partner_id": partner_id, "status": "approved"},
        {"_id": 0, "ip_hash": 0, "reviewer_email": 0},
    ).sort("created_at", -1).limit(min(max(int(limit), 1), 200)).to_list(length=200)
    average = (
        round(sum(r.get("rating") or 0 for r in rows) / len(rows), 2)
        if rows else None
    )
    return {
        "partner": {
            "id": partner["id"],
            "first_name": (partner.get("full_name") or "").split(" ")[0],
            "company_name": partner.get("company_name"),
            "level": partner.get("level"),
            # Iter 216h288 — Gap 10: pass availability to the public
            # review page so the visitor sees a yellow "Back on …"
            # badge rather than booking an engineer on leave.
            "availability": _effective_availability(partner),
        },
        "summary": {"average": average, "count": len(rows)},
        "reviews": [_public_review(r) for r in rows],
    }


@router.get("/partners/me/reviews")
async def list_my_reviews(user: dict = Depends(get_current_user)):
    """Engineer's own view — includes pending + rejected so they can
    see incoming reviews before moderation. Excludes the
    reviewer email + IP hash."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    rows = await db.partner_reviews.find(
        {"partner_id": partner["id"]},
        {"_id": 0, "ip_hash": 0, "reviewer_email": 0},
    ).sort("created_at", -1).limit(500).to_list(length=500)
    approved = [r for r in rows if r.get("status") == "approved"]
    avg = round(sum(r.get("rating") or 0 for r in approved) / len(approved), 2) if approved else None
    return {
        "reviews": rows,
        "summary": {
            "total": len(rows),
            "approved": len(approved),
            "pending": len([r for r in rows if r.get("status") == "pending"]),
            "rejected": len([r for r in rows if r.get("status") == "rejected"]),
            "average": avg,
        },
    }


@router.post("/partners/me/reviews/{review_id}/respond")
async def respond_to_review(review_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Engineer posts a single public response to a review on their
    own profile. Replacing an existing response is allowed (covers
    typo fixes) — every response is timestamped."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    review = await db.partner_reviews.find_one({"id": review_id, "partner_id": partner["id"]}, {"_id": 0})
    if not review:
        raise HTTPException(404, "Review not found")
    response = (body.get("response") or "").strip()[:1500]
    if not response:
        raise HTTPException(400, "Response text is required")
    await db.partner_reviews.update_one(
        {"id": review_id},
        {"$set": {"engineer_response": response, "engineer_response_at": _now(), "updated_at": _now()}},
    )
    await _audit(partner_id=partner["id"], actor_id=user["id"], action="review_responded",
                 after={"review_id": review_id})
    return {"ok": True}


@router.post("/master-admin/partners/{partner_id}/reviews/{review_id}/moderate")
async def admin_moderate_review(
    partner_id: str,
    review_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Master admin approves / rejects a review. Body:
    ``{decision: "approve" | "reject", note?: str}``."""
    _require_master_admin(user)
    decision = (body.get("decision") or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    review = await db.partner_reviews.find_one({"id": review_id, "partner_id": partner_id}, {"_id": 0})
    if not review:
        raise HTTPException(404, "Review not found")
    status = "approved" if decision == "approve" else "rejected"
    note = (body.get("note") or "").strip()[:400] or None
    await db.partner_reviews.update_one(
        {"id": review_id},
        {"$set": {
            "status": status, "moderation_note": note,
            "moderated_by": user["id"], "moderated_at": _now(),
            "updated_at": _now(),
        }},
    )
    await _audit(partner_id=partner_id, actor_id=user["id"], action=f"review_{decision}d",
                 after={"review_id": review_id, "note": note})
    return {"ok": True, "status": status}


# ── End iter 216h286 reviews block ──────────────────────────────────


# ── Iter 220y — Public Wall of Reviews at /engineers/{slug}/reviews ──
#
# The engineer's review submit form already lives at
# `/engineer/{partner_id}/review`. This adds a *read-only* public WALL
# of all approved reviews, addressed by a human-readable slug instead
# of an opaque UUID, so engineers can share a clean link in their
# email signature / business card.
#
# Slug strategy:
#   • Stored as ``public_slug`` on ``partner_engineers``. Auto-minted on
#     first read if the engineer doesn't have one yet. Idempotent.
#   • Derived from ``full_name`` with a 4-hex disambiguator to avoid
#     collisions on common names ("john-smith-a1b2"). Lowercased,
#     hyphen-delimited, max 64 chars.
#
# Endpoint:
#   GET /api/engineers/{slug}/reviews
#     → public — no auth
#     → returns: partner card + summary + rating distribution + reviews

def _slugify_partner_name(name: str) -> str:
    s = (name or "engineer").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "engineer")[:48]


async def _ensure_partner_public_slug(partner: dict) -> str:
    """Idempotent — returns the partner's ``public_slug``, minting one
    on first call. The disambiguator keeps slugs unique even when two
    partners share the same name."""
    existing = partner.get("public_slug")
    if existing:
        return existing
    base = _slugify_partner_name(partner.get("full_name"))
    for _ in range(8):
        candidate = f"{base}-{secrets.token_hex(2)}"
        clash = await db.partner_engineers.find_one(
            {"public_slug": candidate}, {"_id": 0, "id": 1},
        )
        if not clash:
            await db.partner_engineers.update_one(
                {"id": partner["id"]},
                {"$set": {"public_slug": candidate}},
            )
            return candidate
    fallback = f"{base}-{uuid.uuid4().hex[:6]}"
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"public_slug": fallback}},
    )
    return fallback


@router.get("/engineers/{slug}/reviews")
async def public_engineer_reviews_wall(slug: str, limit: int = 100):
    """Public Wall of Reviews — read-only, no auth.

    Resolves *slug* to an approved partner engineer and returns a
    bundle the frontend can render into a beautiful trust-signal wall:

        {
          "partner":  { id, first_name, company_name, level,
                         availability, public_slug, member_since },
          "summary":  { average, count },
          "distribution": { "1": n, "2": n, ..., "5": n },
          "reviews":  [ ...same shape as /partners/{id}/reviews... ]
        }
    """
    slug_norm = (slug or "").strip().lower()
    if not slug_norm:
        raise HTTPException(404, "Engineer not found")
    partner = await db.partner_engineers.find_one(
        {"public_slug": slug_norm, "status": "approved"},
        {"_id": 0},
    )
    if not partner:
        # Fall-back path #1 — UUID-shaped slug (legacy share links).
        partner = await db.partner_engineers.find_one(
            {"id": slug_norm, "status": "approved"},
            {"_id": 0},
        )
        # Fall-back path #2 — name-based slug match (engineer never
        # opened the wall, so we haven't minted a slug yet). Limit
        # this to exactly one match to avoid leaking across namesakes.
        if not partner:
            base_match = re.sub(r"-[0-9a-f]{4}$", "", slug_norm)
            candidates = await db.partner_engineers.find(
                {"status": "approved", "full_name": {"$exists": True}},
                {"_id": 0, "id": 1, "full_name": 1, "public_slug": 1},
            ).to_list(500)
            matches = [
                p for p in candidates
                if _slugify_partner_name(p.get("full_name")) == base_match
            ]
            if len(matches) == 1:
                partner = await db.partner_engineers.find_one(
                    {"id": matches[0]["id"], "status": "approved"},
                    {"_id": 0},
                )
        if not partner:
            raise HTTPException(404, "Engineer not found")

    public_slug = await _ensure_partner_public_slug(partner)

    rows = await db.partner_reviews.find(
        {"partner_id": partner["id"], "status": "approved"},
        {"_id": 0, "ip_hash": 0, "reviewer_email": 0},
    ).sort("created_at", -1).limit(min(max(int(limit), 1), 200)).to_list(length=200)

    distribution = {str(n): 0 for n in range(1, 6)}
    for r in rows:
        key = str(int(r.get("rating") or 0))
        if key in distribution:
            distribution[key] += 1
    average = (
        round(sum(r.get("rating") or 0 for r in rows) / len(rows), 2)
        if rows else None
    )

    return {
        "partner": {
            "id": partner["id"],
            "public_slug": public_slug,
            "first_name": (partner.get("full_name") or "").split(" ")[0],
            "full_name": partner.get("full_name"),
            "company_name": partner.get("company_name"),
            "level": partner.get("level"),
            "availability": _effective_availability(partner),
            "member_since": partner.get("approved_at") or partner.get("created_at"),
        },
        "summary": {"average": average, "count": len(rows)},
        "distribution": distribution,
        "reviews": [_public_review(r) for r in rows],
    }


# ── End iter 220y reviews wall block ────────────────────────────────


# ── Iter 220z — Engineer "Share your wall" endpoint ───────────────
#
# Logged-in engineer's dashboard needs to know its own public wall URL
# (mint on first call). Returns the slug + a ready-to-share URL +
# summary stats so the dashboard card can show "37 reviews · 4.8★"
# alongside a copy-to-clipboard / QR / LinkedIn share UI.

@router.get("/partners/me/public-wall")
async def my_public_wall(user: dict = Depends(get_current_user)):
    """Return the calling engineer's public wall URL + summary stats.

    Mints ``public_slug`` on first call. 403 if the caller is not an
    approved partner engineer (pending / rejected applicants don't get
    a public wall yet)."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    if partner.get("status") != "approved":
        raise HTTPException(403, "Wall is published once your application is approved.")

    slug = await _ensure_partner_public_slug(partner)

    rows = await db.partner_reviews.find(
        {"partner_id": partner["id"], "status": "approved"},
        {"_id": 0, "rating": 1},
    ).to_list(length=500)
    average = (
        round(sum(r.get("rating") or 0 for r in rows) / len(rows), 2)
        if rows else None
    )

    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/") \
        or "https://app.gymaxis.ai"
    public_url = f"{base}/engineers/{slug}/reviews"

    first_name = (partner.get("full_name") or "").split(" ")[0] or "your engineer"
    if average is not None and len(rows) >= 3:
        share_text = (
            f"{first_name} has {len(rows)} ★ reviews on GymAxis — "
            f"averaging {average:.1f}/5. Find a trusted gym engineer here:"
        )
    else:
        share_text = (
            f"{first_name} is a verified GymAxis Partner Engineer — "
            f"see the full profile and book here:"
        )

    return {
        "public_slug": slug,
        "public_url": public_url,
        "summary": {"average": average, "count": len(rows)},
        "share_text": share_text,
    }


# ── End iter 220z share-wall block ────────────────────────────────


# ── Iter 216h287 — Gap 9: engineer-of-engineer referrals ────────────
#
# An approved Partner Engineer can share their referral_code under a
# new `eref` URL (`/engineer/r/{code}`). Anyone who applies through
# that link is attributed back to the referring engineer; once master
# admin approves the new applicant, the referrer earns +1 tier credit
# (same ladder as gym referrals: 5 → £15/mo, 10 → free).
#
# Storage: collection `engineer_referrals` — append-only, one row per
# attempted referral. The `status` field walks pending → approved /
# rejected as the application moves through master-admin review.
# Status fields used:
#   pending   — applicant submitted, no decision yet
#   approved  — applicant was approved as a partner; credit awarded
#   rejected  — applicant was rejected (no credit)
#   superseded — applicant resubmitted later under the same email
#                (we keep the original row for the audit trail)


def _public_eref_link(code: str) -> str:
    """Engineer-of-engineer share URL. Lands on the branded recruit
    page, which then forwards into the public apply form with the
    `eref` query param preserved."""
    base = (
        os.environ.get("PARTNER_REFERRAL_BASE_URL")
        or os.environ.get("EMAIL_PUBLIC_BASE_URL")
        or os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    return f"{base}/engineer/r/{code}" if base else f"/engineer/r/{code}"


async def _resolve_eref_partner(code: str) -> Optional[dict]:
    """Look up the referring engineer by their referral_code. Only
    returns approved partners so an unverified engineer can't drive
    a branded recruit page."""
    code_up = (code or "").strip().upper()
    if not code_up:
        return None
    return await db.partner_engineers.find_one(
        {"referral_code": code_up, "status": "approved"},
        {"_id": 0, "id": 1, "full_name": 1, "company_name": 1, "referral_code": 1,
         "service_postcode": 1, "level": 1, "active_referral_count": 1},
    )


async def _record_engineer_referral(
    *,
    referrer_partner_id: str,
    referrer_code: str,
    referred_email: str,
    referred_application_id: Optional[str] = None,
) -> Optional[dict]:
    """Idempotent — re-applying with the same email re-uses the row
    (and bumps `updated_at`). Returns the stored doc or ``None`` if
    the inputs are unusable (self-referral / bad email)."""
    email = (referred_email or "").strip().lower()
    if not email or "@" not in email:
        return None
    # Self-referral guard: the referrer's own email never attributes.
    referrer = await db.partner_engineers.find_one(
        {"id": referrer_partner_id}, {"_id": 0, "email": 1},
    )
    if referrer and (referrer.get("email") or "").lower() == email:
        return None
    now = _now()
    existing = await db.engineer_referrals.find_one(
        {"referrer_partner_id": referrer_partner_id, "referred_email": email,
         "status": {"$in": ["pending", "approved"]}},
        {"_id": 0},
    )
    if existing:
        await db.engineer_referrals.update_one(
            {"id": existing["id"]},
            {"$set": {
                "referred_application_id": referred_application_id or existing.get("referred_application_id"),
                "updated_at": now,
            }},
        )
        return {**existing, "updated_at": now,
                "referred_application_id": referred_application_id or existing.get("referred_application_id")}
    doc = {
        "id": _new_id(),
        "referrer_partner_id": referrer_partner_id,
        "referrer_referral_code": referrer_code,
        "referred_email": email,
        "referred_application_id": referred_application_id,
        "referred_partner_id": None,
        "status": "pending",
        "credit_awarded_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.engineer_referrals.insert_one(doc)
    return doc


async def _credit_engineer_referral_on_approval(partner: dict, actor_id: str) -> Optional[dict]:
    """Called from `admin_approve_partner` once a partner_engineers
    row is flipped to approved. Idempotent — if the matching engineer
    referral row was already credited, returns ``None`` without
    side-effects. Otherwise marks the row approved, recomputes the
    referrer's app-fee tier, and audit-logs against the referrer.
    """
    email = (partner.get("email") or "").lower()
    if not email:
        return None
    ref = await db.engineer_referrals.find_one(
        {"referred_email": email, "status": "pending"},
        {"_id": 0},
    )
    if not ref:
        return None
    now = _now()
    await db.engineer_referrals.update_one(
        {"id": ref["id"]},
        {"$set": {
            "status": "approved",
            "referred_partner_id": partner["id"],
            "credit_awarded_at": now,
            "updated_at": now,
        }},
    )
    # Re-tier the referrer — may trigger a Stripe subscription downshift.
    try:
        await _recompute_app_fee(ref["referrer_partner_id"])
    except Exception:
        logger.exception("[partners] eref re-tier failed for partner=%s", ref["referrer_partner_id"])
    await _audit(
        partner_id=ref["referrer_partner_id"], actor_id=actor_id,
        action="engineer_referral_credit",
        after={"referred_partner_id": partner["id"], "referred_email": email,
               "engineer_referral_id": ref["id"]},
    )
    return {**ref, "status": "approved", "referred_partner_id": partner["id"]}


@router.get("/partners/public/by-eref/{code}")
async def public_eref_lookup(code: str):
    """Public — drives the branded recruit landing page. Returns the
    referring engineer's first name + company so the visitor sees
    "Jane recommends GymAxis". Never leaks PII (no email, no phone,
    no full name, no postcode beyond outward code)."""
    partner = await _resolve_eref_partner(code)
    if not partner:
        raise HTTPException(404, "Referral link not found")
    first = (partner.get("full_name") or "").split(" ")[0] or "An engineer"
    postcode = (partner.get("service_postcode") or "").upper().strip()
    outward = postcode.split(" ")[0] if " " in postcode else (postcode[:4] if postcode else None)
    return {
        "first_name": first,
        "company_name": partner.get("company_name"),
        "level": partner.get("level"),
        "service_area": outward or None,
        "referral_code": partner["referral_code"],
        "active_referrals": int(partner.get("active_referral_count") or 0),
        "apply_url": f"/partners/engineers/apply?eref={partner['referral_code']}",
    }


@router.get("/partners/me/engineer-referrals")
async def list_my_engineer_referrals(user: dict = Depends(get_current_user)):
    """Engineer dashboard — list the partner's recruit pipeline +
    summary stats. Sensitive applicant data is held back; the engineer
    sees an obfuscated email (`j***@gym.io`) and the current status."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "No partner profile")
    rows = await db.engineer_referrals.find(
        {"referrer_partner_id": partner["id"]}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=500)
    sanitised = [
        {
            "id": r["id"],
            "status": r.get("status", "pending"),
            "referred_email_masked": _mask_email(r.get("referred_email", "")),
            "created_at": r.get("created_at"),
            "credit_awarded_at": r.get("credit_awarded_at"),
        }
        for r in rows
    ]
    approved = sum(1 for r in rows if r.get("status") == "approved")
    pending = sum(1 for r in rows if r.get("status") == "pending")
    rejected = sum(1 for r in rows if r.get("status") == "rejected")
    return {
        "referrals": sanitised,
        "summary": {"total": len(rows), "approved": approved, "pending": pending, "rejected": rejected},
        "share_link": _public_eref_link(partner["referral_code"]),
        "referral_code": partner["referral_code"],
        "tier_credit_each": 1,
    }


def _mask_email(addr: str) -> str:
    """j.smith@gym.io → j***@gym.io. Stable, length-preserving-ish,
    no PII leakage beyond the first character of the local-part."""
    if not addr or "@" not in addr:
        return "anonymous"
    local, _, domain = addr.partition("@")
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"


# ── End iter 216h287 engineer-referrals block ──────────────────────


# ── Iter 216h288 — Gap 10: master availability toggle ───────────────
#
# An approved Partner Engineer can flip themselves to "unavailable"
# (annual leave, parental leave, full diary) with an optional
# "back on" date. Per the user's BA-audit decision (2C), an
# unavailable engineer is **still surfaced** on discovery surfaces
# but with a yellow "Back on 5 Mar" badge so existing relationships
# aren't broken and the visitor knows there's a partner in the area.
#
# Schema lives under `partner_engineers.availability`:
#   { status: "available" | "unavailable",
#     resumes_on: ISO date | None,
#     note: short str | None,
#     updated_at: ISO datetime }
#
# Read paths automatically "auto-resume" a partner whose `resumes_on`
# is in the past — so a returning engineer doesn't need to remember
# to toggle back on.


def _today_utc():
    """Date-only helper, UTC. Pulled out so tests can patch it."""
    return datetime.now(timezone.utc).date()


def _parse_resumes_on(raw: Optional[str]) -> Optional[str]:
    """Accept an ISO-ish date string and emit a normalised 'YYYY-MM-DD'.
    Empty / None / unparseable → None (which means 'no end date set')."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        # Accept full ISO datetimes too — strip the time component.
        if "T" in s:
            s = s.split("T", 1)[0]
        from datetime import date as _date
        parsed = _date.fromisoformat(s)
        return parsed.isoformat()
    except Exception:  # noqa: BLE001
        return None


def _effective_availability(partner: dict) -> dict:
    """Return the live availability sub-doc for a partner. Auto-flips
    back to 'available' if `resumes_on` is in the past. Defaults to
    'available' for legacy rows that never set the field.

    This is **read-only** — it does NOT persist the auto-flip; the
    next write (engineer toggle, admin update) will reconcile state.
    """
    av = (partner or {}).get("availability") or {}
    status = av.get("status") or "available"
    resumes_on = av.get("resumes_on")
    note = av.get("note") or None
    if status == "unavailable" and resumes_on:
        try:
            from datetime import date as _date
            if _date.fromisoformat(resumes_on) <= _today_utc():
                status = "available"
                # Keep resumes_on + note around for the audit trail; the
                # caller can render "Back on Mar 5 (last leave ended)".
        except Exception:  # noqa: BLE001
            pass
    return {
        "status": status,
        "resumes_on": resumes_on,
        "note": note,
        "updated_at": av.get("updated_at"),
    }


@router.get("/partners/me/availability")
async def get_my_availability(user: dict = Depends(get_current_user)):
    """Engineer reads their own toggle state. Pure read — useful for
    a settings page that doesn't already hit `/partners/me`."""
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    return {"availability": _effective_availability(partner)}


@router.put("/partners/me/availability")
async def set_my_availability(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Engineer flips their own availability toggle.

    Body:
      * `available` (bool, required) — true = accepting work, false = on leave
      * `resumes_on` (ISO date, optional) — only meaningful when
        `available=false`. Cleared when switching back on.
      * `note` (str, optional, max 200 chars) — surfaces on the public
        badge (e.g. "Back from paternity leave 4 Mar"). Stripped when
        switching back on.
    """
    partner = await _get_partner_by_user(user["id"])
    if not partner:
        raise HTTPException(404, "Not a partner — apply first.")
    if "available" not in body:
        raise HTTPException(400, "`available` (bool) is required")
    is_available = bool(body.get("available"))
    note = (body.get("note") or "").strip()[:200] or None
    resumes_on = _parse_resumes_on(body.get("resumes_on")) if not is_available else None
    if not is_available and resumes_on:
        # Optional sanity: if the date is in the past, drop it — the engineer
        # almost certainly meant to leave it open-ended.
        from datetime import date as _date
        try:
            if _date.fromisoformat(resumes_on) <= _today_utc():
                resumes_on = None
        except Exception:  # noqa: BLE001
            resumes_on = None
    new_av = {
        "status": "available" if is_available else "unavailable",
        "resumes_on": resumes_on,
        "note": note if not is_available else None,
        "updated_at": _now(),
    }
    before = (partner.get("availability") or {}).get("status") or "available"
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {"availability": new_av, "updated_at": _now()}},
    )
    await _audit(
        partner_id=partner["id"], actor_id=user["id"], action="availability_set",
        before={"status": before},
        after={"status": new_av["status"], "resumes_on": resumes_on, "note": note},
    )
    return {"ok": True, "availability": new_av}


# ── End iter 216h288 availability block ────────────────────────────


# ── Iter 220r-2 — Welcome-back "Send thanks" one-click flow ────────
#
# Sweep ``utils.partner_return_digest`` pre-mints one short-lived
# token per referred gym that had activity during the leave. The
# digest email surfaces a "Send thanks → " button per gym; the
# button hits this GET endpoint, which validates the token, fires
# a thank-you email to the gym's primary contact (with the
# engineer's name on it), marks the token used, and renders a
# tiny confirmation page.
#
# Token storage lives in ``db.partner_welcome_thanks_tokens``.
# Fields: ``token, partner_id, organization_id, gym_name,
# engineer_name, engineer_email, created_at, expires_at, used_at``.
#
# Why GET and not POST? The link sits in an email body — most
# email clients only follow GET. We tolerate the slightly weaker
# semantics because (a) the token is single-use, (b) it carries
# no input from the user, and (c) the audit row + the
# ``used_at`` flip make replay a no-op.


@router.get("/partners/welcome-back/thanks/{token}", response_class=HTMLResponse)
async def welcome_back_send_thanks(token: str) -> HTMLResponse:
    """One-click thanks. Email link → fires a thanks email to the
    gym's primary contact, then returns a small HTML confirmation."""
    token = (token or "").strip()
    if not token or len(token) > 200:
        return HTMLResponse(_thanks_page_html("Invalid link", "This thanks link looks malformed."), status_code=400)
    row = await db.partner_welcome_thanks_tokens.find_one({"token": token}, {"_id": 0})
    if not row:
        return HTMLResponse(_thanks_page_html("Link not recognised", "This thanks link was never issued, or has been retired."), status_code=404)
    # Expiry — 60-day window so an engineer who reads the digest
    # late still has a chance to click. Past that the data drift
    # makes the recap stale.
    expires_at = row.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
        return HTMLResponse(_thanks_page_html("This link has expired", "Welcome-back thanks links expire after 60 days."), status_code=410)
    if row.get("used_at"):
        return HTMLResponse(_thanks_page_html("Already sent", f"You've already sent thanks to {row.get('gym_name') or 'this gym'}."))
    # Resolve the gym's primary contact lazily — the org could have
    # rotated owners since the token was minted.
    org = await db.organizations.find_one({"id": row["organization_id"]}, {"_id": 0})
    if not org:
        await db.partner_welcome_thanks_tokens.update_one(
            {"token": token},
            {"$set": {"used_at": _now(), "outcome": "org-missing"}},
        )
        return HTMLResponse(_thanks_page_html("Gym not found", "We couldn't find this gym anymore — it may have been archived."), status_code=410)
    recipient = (
        org.get("primary_contact_email") or org.get("admin_email") or org.get("owner_email") or ""
    ).strip()
    sent = False
    if recipient:
        try:
            from utils.email import send_email
            engineer_name = row.get("engineer_name") or "Your service engineer"
            gym_name = row.get("gym_name") or org.get("name") or "your team"
            html = (
                f'<div style="font-family:Arial,sans-serif;color:#0F172A;line-height:1.55;max-width:560px;margin:0 auto;">'
                f'<h2 style="margin:0 0 12px;font-size:22px;font-weight:800;">A quick thank you from {engineer_name}.</h2>'
                f"<p>Hi team,</p>"
                f"<p><strong>{engineer_name}</strong> was off the tools recently and wanted to say thanks "
                f"to <strong>{gym_name}</strong> for keeping things running — and for your patience while they were away.</p>"
                f"<p>{engineer_name} is back on GymAxis and picking up any open faults now. "
                f"You shouldn't notice any change in service.</p>"
                f'<p style="margin-top:18px;font-size:13px;color:#475569;">'
                f"This is a one-tap thanks sent directly from {engineer_name}'s welcome-back digest. "
                f"No reply needed — just a courtesy note."
                f"</p>"
                f"</div>"
            )
            sent = bool(await send_email(
                to=recipient,
                subject=f"{row.get('engineer_name') or 'Your engineer'} says thanks",
                html=html,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[welcome-thanks] send failed token=%s err=%s", token, exc)
    await db.partner_welcome_thanks_tokens.update_one(
        {"token": token},
        {"$set": {
            "used_at": _now(),
            "outcome": "sent" if sent else ("no-recipient" if not recipient else "send-failed"),
            "recipient": recipient or None,
        }},
    )
    if sent:
        return HTMLResponse(_thanks_page_html(
            "Thanks sent",
            f"We just emailed your thanks to {row.get('gym_name') or 'the gym'}. Nice touch.",
        ))
    if not recipient:
        return HTMLResponse(_thanks_page_html(
            "No contact on file",
            "This gym doesn't have a primary contact email on file yet — we couldn't deliver the thanks. "
            "Mention it to them next time you're on site.",
        ), status_code=200)
    return HTMLResponse(_thanks_page_html(
        "We couldn't send right now",
        "Our email provider had a hiccup. Your link is still valid — try again in a minute.",
    ), status_code=200)


def _thanks_page_html(headline: str, sub: str) -> str:
    """Tiny inline confirmation page — keeps the user in their email
    client without bouncing them through the SPA. Brand-light so it
    survives any future palette refresh."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
        f"<title>{headline} · GymAxis</title>"
        '<style>body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        "background:linear-gradient(135deg,#F8FAFC 0%,#EEF2FF 100%);min-height:100vh;"
        "display:flex;align-items:center;justify-content:center;color:#0F172A;}"
        ".card{background:#fff;border-radius:18px;padding:32px 28px;max-width:440px;"
        "box-shadow:0 12px 30px rgba(15,23,42,0.08);text-align:center;}"
        "h1{margin:0 0 10px;font-size:22px;font-weight:800;letter-spacing:-0.01em;}"
        "p{margin:0;color:#475569;font-size:14px;line-height:1.55;}"
        ".dot{width:54px;height:54px;border-radius:50%;margin:0 auto 18px;"
        "background:linear-gradient(135deg,#2563EB 0%,#9D4CDD 100%);display:flex;"
        "align-items:center;justify-content:center;color:#fff;font-size:24px;font-weight:800;}"
        "</style></head><body>"
        '<div class="card">'
        '<div class="dot">✓</div>'
        f"<h1>{headline}</h1><p>{sub}</p>"
        "</div></body></html>"
    )


# ── End iter 220r-2 ───────────────────────────────────────────────


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

    # Iter 220n — Auto-add the referring engineer as a service supplier for
    # the new gym. The whole point of the Partner Plan economics is that
    # every gym you bring in is recurring revenue AND recurring work —
    # we deliver both halves here. The gym keeps full agency (can disable
    # auto_dispatch, swap primary, add more suppliers) via the existing
    # Supplier Dashboard. Idempotent: skip if a supplier row already
    # links to this partner engineer for this org.
    try:
        existing_supplier = await db.suppliers.find_one(
            {"organization_id": organization_id, "partner_engineer_id": partner["id"]},
            {"_id": 0, "id": 1},
        )
        if not existing_supplier:
            supplier_id = _new_id()
            await db.suppliers.insert_one({
                "id": supplier_id,
                "organization_id": organization_id,
                "partner_engineer_id": partner["id"],
                "name": partner.get("full_name") or partner.get("trading_name") or "Service Engineer",
                "email": partner.get("email", ""),
                "phone": partner.get("phone", ""),
                "contact_person": partner.get("full_name", ""),
                "address": partner.get("address", ""),
                "notes": "Auto-added — your referring engineer. Faults logged "
                         "here route to them by default. Edit anytime.",
                "supplier_types": ["service_engineer"],
                "supplier_type": "service_engineer",
                "callout_fee": float((partner.get("rates") or {}).get("callout_fee", 0) or 0),
                "labour_rate_per_hour": float((partner.get("rates") or {}).get("labour_rate_per_hour", 0) or 0),
                "mileage_rate": float((partner.get("rates") or {}).get("mileage_rate", 0) or 0),
                "parts_markup_pct": float((partner.get("rates") or {}).get("parts_markup_pct", 0) or 0),
                "custom_items": [],
                "auto_dispatch": True,        # faults route here by default
                "is_primary_supplier": True,  # first one ⇒ default supplier
                "auto_created_from_referral": True,
                "created_at": _now(),
            })
            await _audit(
                partner_id=partner["id"], actor_id="system",
                action="supplier_auto_attached",
                after={"organization_id": organization_id, "supplier_id": supplier_id},
            )
    except Exception as supplier_exc:
        # Best-effort — never block a successful referral on a supplier
        # auto-attach failure. The referral itself is what matters
        # commercially; the gym can always add the engineer manually.
        logger.warning(
            "Auto-supplier attach failed for partner=%s org=%s: %s",
            partner.get("id"), organization_id, supplier_exc,
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

    Iter 216h194 — Policy: engineers receive TWO commissions per referred
    gym: (a) a one-off signup reward of 50% of the first cleared
    Operations invoice, and (b) £3/site/mo recurring for every
    subsequent cleared Operations invoice. Both are accrued here; the
    qualifying-period gate (3 months on platform) is enforced at
    APPROVAL time in `admin_approve_commission`, not at accrual time —
    so finance can see the running total even before it's payable.

    Iter 216h193 removed the £100–£400 premium-plan bonus tier.

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
    # Iter 216h287 — Gap 9: if this partner was attributed to a
    # referring engineer, mark the engineer_referrals row approved and
    # award the tier credit. Idempotent — re-approving has no effect.
    try:
        credited = await _credit_engineer_referral_on_approval(
            {**partner, "status": "approved"}, actor_id=user["id"],
        )
        if credited:
            logger.info(
                "[partners] engineer-referral credit awarded: referrer=%s referred=%s",
                credited.get("referrer_partner_id"), partner_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Engineer-referral credit failed for partner=%s: %s", partner_id, exc)
    # Iter 216h281 — Gap 1: notify the engineer they're approved + send
    # them their referral code straight into the inbox.
    try:
        from utils.partner_emails import send_application_approved
        if partner.get("email"):
            await send_application_approved(
                email=partner["email"],
                full_name=partner.get("full_name", ""),
                referral_code=partner.get("referral_code"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner approval email failed: %s", exc)
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
    # Iter 216h281 — Gap 1: notify the engineer their app was rejected
    # and let them know they can re-apply.
    try:
        from utils.partner_emails import send_application_rejected
        if partner.get("email"):
            await send_application_rejected(
                email=partner["email"],
                full_name=partner.get("full_name", ""),
                reason=reason if reason != "Not approved" else None,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner rejection email failed: %s", exc)
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
async def admin_approve_commission(
    ledger_id: str,
    user: dict = Depends(get_current_user),
    body: dict = Body(default_factory=dict),
):
    _require_master_admin(user)
    row = await db.partner_commission_ledger.find_one({"id": ledger_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Ledger row not found")
    if row["status"] != "accrued":
        raise HTTPException(400, f"Cannot approve — current status is '{row['status']}'")
    # Iter 216h193 — 3-month qualifying-period guard. A signup reward
    # is only released once the referred gym has been active on the
    # platform for >= 3 months. Master admin can override by passing
    # `force=true` (e.g. for legacy / exception cases) — the override
    # is audited.
    qualifying_ok = True
    days_on_platform: Optional[int] = None
    referred_org = await db.organizations.find_one(
        {"id": row["referred_organization_id"]},
        {"_id": 0, "created_at": 1, "status": 1},
    )
    if referred_org:
        try:
            created_at = referred_org.get("created_at") or ""
            if created_at:
                # `created_at` is an ISO string in this codebase.
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                days_on_platform = (datetime.now(timezone.utc) - dt).days
                qualifying_ok = days_on_platform >= 90
        except Exception:
            qualifying_ok = True  # parse failure → don't block (audited)
    if not qualifying_ok and not bool(body.get("force")):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Referred gym has only been on the platform for "
                f"{days_on_platform} day(s). The 3-month qualifying period "
                "has not elapsed. Pass force=true to override (audited)."
            ),
        )
    await db.partner_commission_ledger.update_one(
        {"id": ledger_id},
        {"$set": {"status": "approved", "approved_at": _now(), "approved_by": user["id"]}},
    )
    await _audit(
        partner_id=row["partner_id"], actor_id=user["id"], action="approve_commission",
        before={"status": "accrued"},
        after={
            "status": "approved",
            "ledger_id": ledger_id,
            "days_on_platform": days_on_platform,
            "forced": bool(body.get("force")) and not qualifying_ok,
        },
    )
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
    """Iter 220l — grants now have a 30-day max-age so an old grant
    can't be reused forever. A grant counts only if active AND not
    yet expired."""
    now_iso = _now()
    grant = await db.partner_job_grants.find_one(
        {
            "engineer_user_id": user_id,
            "active": True,
            "$or": [{"expires_at": None}, {"expires_at": {"$gt": now_iso}}],
        },
        {"_id": 1},
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
    # Iter 220k — claim-time gates (read-only access still works so the
    # engineer can see what's blocking them).
    "compliance_paused":      "Your compliance status is paused — re-upload your expired documents to take new jobs.",
    "compliance_required":    "Upload your DBS (or Right-to-Work) document before claiming jobs. This protects you, the gym, and their members.",
}


# Iter 220k — claim-time compliance gate. Layered on top of the existing
# access guard so the engineer can still SEE the dashboard, settings,
# and compliance uploader — they just can't claim or self-create paid
# work until their KYC is on file and unpaused.
#
# Exempt cohorts (return immediately without compliance checks):
#   • internal_engineer  (employed directly by an organisation)
#   • customer_grant     (granted access for a single case by a gym)
#
# Required for partner-track engineers:
#   • partner.compliance_paused == False, AND
#   • at least one of {dbs, rtw} has a file uploaded with no expiry,
#     or an expiry strictly in the future.
# Required for partner-track engineers (market-specific):
#   • partner.compliance_paused == False, AND
#   • at least one of the market's identity/eligibility docs has a file
#     uploaded with no expiry, or an expiry strictly in the future.
#   UK: {dbs, rtw} ; US: {work_authorization, background_check}.
_CLAIM_REQUIRED_KINDS = ("dbs", "rtw")  # legacy default (UK)
_CLAIM_KINDS_BY_COUNTRY = {
    "GB": ("dbs", "rtw"),
    "US": ("work_authorization", "background_check"),
}


def _claim_required_kinds(country_code: str | None) -> tuple:
    return _CLAIM_KINDS_BY_COUNTRY.get((country_code or "GB").strip().upper(), _CLAIM_REQUIRED_KINDS)


def _has_valid_claim_doc(partner: dict, kinds: tuple = _CLAIM_REQUIRED_KINDS) -> bool:
    docs = (partner or {}).get("compliance_docs") or {}
    now = datetime.now(timezone.utc)
    for kind in kinds:
        blob = docs.get(kind) or {}
        if not isinstance(blob, dict) or not blob.get("file"):
            continue
        expires_at_raw = blob.get("expires_at")
        if not expires_at_raw:
            return True  # no expiry = treated as currently valid
        try:
            s = str(expires_at_raw)
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            exp = datetime.fromisoformat(s)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now:
                return True
        except Exception:
            continue
    return False


# Iter 220ea·47 — trial compliance grace. A newly-approved partner engineer
# can claim jobs WITHOUT any compliance docs for the first N days after
# approval, so they can actually trial the Engineer App. A visible in-app
# deadline nudges them to upload DBS / Right-to-Work before the grace lapses;
# once it does, the standard claim gate re-applies.
_COMPLIANCE_GRACE_DAYS = max(1, int(os.environ.get("ENGINEER_COMPLIANCE_GRACE_DAYS", "14") or 14))


def _compliance_grace_info(partner: dict) -> dict:
    """Returns {active, until, days_left, grace_days} for the post-approval
    compliance grace window (anchored on approval, falling back to signup)."""
    anchor = (partner or {}).get("approved_at") or (partner or {}).get("created_at")
    out = {"active": False, "until": None, "days_left": 0, "grace_days": _COMPLIANCE_GRACE_DAYS}
    if not anchor:
        return out
    try:
        s = str(anchor)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        start = datetime.fromisoformat(s)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    except Exception:
        return out
    until = start + timedelta(days=_COMPLIANCE_GRACE_DAYS)
    secs_left = (until - datetime.now(timezone.utc)).total_seconds()
    out["until"] = until.isoformat()
    if secs_left > 0:
        out["active"] = True
        out["days_left"] = int((secs_left + 86399) // 86400)  # ceil to whole days
    return out


async def require_engineer_compliance_to_claim(user: dict = Depends(get_current_user)) -> dict:
    """Stricter gate applied to *claim-time* endpoints (queue claim,
    self-create-job).

    Engineers can still hit the dashboard / settings / compliance
    uploader under the looser `require_engineer_app_access` — they're
    only blocked from picking up NEW paid work until they're
    compliant. In-flight jobs are NOT affected (those have their own
    routes that don't carry this dependency).
    """
    decision = await evaluate_engineer_app_access(user)
    if not decision["allowed"]:
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
    # Internal employees / customer-granted engineers / master admins
    # are exempt — they are not signed onto the Partner Engineer
    # contract. (Master admins still get a useful 200 so they can
    # support / test claim flows.)
    if decision["reason"] in ("master_admin", "internal_engineer", "customer_grant"):
        return user
    partner = decision.get("partner") or {}
    # Iter 220ea·47 — trial grace: during the first N days after approval the
    # engineer can claim jobs without compliance docs on file. The dashboard
    # shows the countdown so they know the deadline to upload DBS / RTW.
    if _compliance_grace_info(partner).get("active"):
        return user
    if partner.get("compliance_paused"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "engineer_app_blocked",
                "reason": "compliance_paused",
                "message": _BLOCK_MESSAGES["compliance_paused"],
            },
        )
    _claim_country = await _compliance_country(user)
    _claim_kinds = _claim_required_kinds(_claim_country)
    if not _has_valid_claim_doc(partner, _claim_kinds):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "engineer_app_blocked",
                "reason": "compliance_required",
                "message": _BLOCK_MESSAGES["compliance_required"],
                "required_one_of": list(_claim_kinds),
            },
        )
    return user


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
    # Iter 220l — grants now auto-expire after 30 days (configurable via
    # body.expires_in_days, capped at 365). This stops a stale per-case
    # grant being silently reused months later.
    raw_days = int(body.get("expires_in_days") or 30)
    expires_in_days = max(1, min(raw_days, 365))
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()
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
        "expires_at": expires_at,
        "expires_in_days": expires_in_days,
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
    return any(a[:n] == b[:n] for n in (4, 3, 2))


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
         "skills": 1, "qualifications": 1, "active_referral_count": 1,
         "availability": 1},
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
            # Iter 216h288 — Gap 10: include availability so the
            # customer-facing card can render a yellow "Back on …"
            # badge instead of hiding the engineer outright.
            "availability": _effective_availability(r),
        })
    # Top-tier + strategic always rank above verified; within tier, score desc.
    # Iter 216h288 — additionally sink unavailable engineers below available
    # ones so the visitor sees who can actually take work first.
    scored.sort(key=lambda x: (
        (x.get("availability") or {}).get("status") == "unavailable",
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
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "company_name": 1,
         "service_postcode": 1, "availability": 1},
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
    # Iter 216h290 — Gap 10 follow-up: if the engineer is currently on
    # leave, fire a polite autoreply to the customer with up to 3
    # in-area alternatives. Wrapped in try/except so a Resend hiccup
    # never breaks the contact-request flow — the row is already
    # persisted by this point.
    try:
        await _maybe_send_unavailable_autoreply(partner=partner, requester=user, request_id=req["id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Engineer-unavailable autoreply failed for partner=%s: %s", partner_id, exc)
    return {"ok": True, "request": req}


async def _alternative_engineers_for(partner_id: str, postcode: str, limit: int = 3) -> list[dict]:
    """Iter 216h290 — find up to ``limit`` AVAILABLE in-area engineers
    to suggest as alternatives to a leave-stricken partner. Reuses the
    same outcode-prefix matcher as the public widget so the suggestions
    line up with what the customer would see if they searched the
    network themselves.
    """
    if not postcode:
        return []
    cur = db.partner_engineers.find(
        {"status": "approved",
         "level": {"$in": ["verified_partner", "strategic_partner"]},
         "id": {"$ne": partner_id}},
        {"_id": 0, "id": 1, "full_name": 1, "company_name": 1,
         "service_postcode": 1, "availability": 1},
    )
    rows = await cur.to_list(length=200)
    out: list[dict] = []
    for r in rows:
        # Defensive: never recommend the engineer back to themselves,
        # even if the mongo $ne filter is somehow bypassed.
        if r.get("id") == partner_id:
            continue
        # Skip other unavailable engineers — never recommend someone
        # else who's also on leave.
        if _effective_availability(r).get("status") != "available":
            continue
        if not _postcode_match(r.get("service_postcode") or "", postcode):
            continue
        out.append({
            "id": r["id"],
            "full_name": r["full_name"],
            "company_name": r.get("company_name"),
            "service_postcode_area": _outcode(r.get("service_postcode") or ""),
        })
        if len(out) >= limit:
            break
    return out


async def _maybe_send_unavailable_autoreply(*, partner: dict, requester: dict, request_id: str) -> None:
    """Iter 216h290 — fire the autoreply only when the engineer is in
    fact on leave. Stamps the partner_contact_requests row with
    ``auto_reply_sent_at`` so a future polling worker knows it's
    already been handled.
    """
    av = _effective_availability(partner)
    if av.get("status") != "unavailable":
        return
    to_email = requester.get("email")
    if not to_email:
        return
    alternatives = await _alternative_engineers_for(
        partner_id=partner["id"], postcode=partner.get("service_postcode") or "",
    )
    eng_first = (partner.get("full_name") or "").strip().split(" ")[0] or "Your engineer"
    requester_first = (requester.get("full_name") or "").strip().split(" ")[0] or None
    from utils.partner_emails import send_engineer_unavailable_autoreply
    sent = await send_engineer_unavailable_autoreply(
        to_email=to_email,
        requester_first_name=requester_first,
        engineer_first_name=eng_first,
        engineer_company=partner.get("company_name"),
        resumes_on=av.get("resumes_on"),
        leave_note=av.get("note"),
        alternatives=alternatives,
    )
    if sent:
        await db.partner_contact_requests.update_one(
            {"id": request_id},
            {"$set": {"auto_reply_sent_at": _now()}},
        )


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
    # Iter 216h287 — Gap 9: engineer-of-engineer referrals.
    await db.engineer_referrals.create_index([("referrer_partner_id", 1), ("created_at", -1)])
    await db.engineer_referrals.create_index(
        [("referred_email", 1), ("status", 1)],
    )
