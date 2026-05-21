"""
Master Admin — Memberships & Group Fitness Commercial Control Engine.

Cross-organisation control plane for GymAxis Memberships. All endpoints
require master admin and are strictly scoped under /master-admin/memberships.

Surfaces:
  • Overview  — platform-wide KPIs, AI recommendations
  • Organisations — per-org drill-down: plans, classes, tier, standardised vs customised
  • Plan Templates — global monthly/annual/PAYG templates, apply to orgs, lock
  • Booking Rules — platform-wide defaults (windows, capacity, waitlist, no-show)
  • Subscription Tiers — Lite vs Pro feature matrix + per-org assignment
  • Revenue — MRR by org / plan, failed payments, upgrades, downgrades
  • Engagement & Retention — DAU/WAU, utilisation, peak times, churn segments
  • Instructors — cross-org leaderboard, utilisation, top/underperformers
  • AI Insights — GPT-4o-mini prioritised alerts + feature-flag recommendations
  • Feature Flags — global feature toggle matrix + beta rollout controls
  • Audit log — every master-admin write lands here
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.memberships_ai_insights import _chat, _parse_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["master-admin-memberships"])


# ═════════════════════ helpers ═════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def _audit(user: dict, action: str, target_type: str, target_id: str, diff: dict | None = None) -> None:
    await db.memberships_admin_audit.insert_one({
        "id": _uuid(),
        "at": _now_iso(),
        "by": user.get("email") or "?",
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "diff": diff or {},
    })


def _org_memberships_tier(org: dict) -> str:
    """Lite vs Pro distinction purely for the Memberships module.
    Defaults to 'lite' — Pro is opt-in and unlocks advanced reporting,
    AI insights, multi-site visibility, CRM-depth retention tooling."""
    return (org or {}).get("memberships_tier") or "lite"


def _month_key(iso_like: str | None) -> str | None:
    if not iso_like:
        return None
    return str(iso_like)[:7]  # YYYY-MM


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ═════════════════════ Overview ═════════════════════

@router.get("/master-admin/memberships/overview")
async def memberships_overview(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    non_test = {"is_test": {"$ne": True}}
    since_7 = _since(7)
    since_30 = _since(30)
    churn_cutoff = since_30

    # MRR pipeline (from active member_memberships × plan price)
    mrr_pipeline = [
        {"$match": {"status": "active"}},
        {"$lookup": {"from": "membership_plans", "localField": "plan_id", "foreignField": "id", "as": "p"}},
        {"$unwind": "$p"},
        {"$group": {
            "_id": "$organization_id",
            "mrr_pence": {"$sum": {
                "$cond": [
                    {"$eq": ["$p.billing_cycle", "annual"]},
                    {"$divide": [{"$ifNull": ["$p.price_pence", 0]}, 12]},
                    {"$ifNull": ["$p.price_pence", 0]},
                ],
            }},
            "members": {"$sum": 1},
        }},
    ]

    # Occupancy pipeline (last 7d)
    occ_pipe = [
        {"$match": {"starts_at": {"$gte": since_7, "$lte": _now_iso()}}},
        {"$group": {
            "_id": None,
            "capacity": {"$sum": {"$ifNull": ["$capacity", 0]}},
            "booked": {"$sum": {"$ifNull": ["$bookings_count", 0]}},
        }},
    ]

    # ── Run ALL 16 independent queries in parallel via asyncio.gather ──
    # Before: 16 sequential awaits (~600-800ms on warm cache). After: single
    # round-trip (~50-120ms). The non-test filter trims noise from CI data.
    (
        total_orgs, active_members, inactive_members,
        total_bookings, bookings_7d, bookings_30d,
        no_shows_30d, checkins_30d, total_classes, total_plans,
        cancelled_30d, lite, pro,
        per_org_rev, occ_row, orgs_raw,
    ) = await asyncio.gather(
        db.organizations.count_documents({**non_test, "account_type": {"$ne": "member"}}),
        db.members.count_documents({"status": {"$ne": "cancelled"}}),
        db.members.count_documents({"status": "cancelled"}),
        db.bookings.count_documents({}),
        db.bookings.count_documents({"booked_at": {"$gte": since_7}}),
        db.bookings.count_documents({"booked_at": {"$gte": since_30}}),
        db.bookings.count_documents({"status": "no_show", "booked_at": {"$gte": since_30}}),
        db.member_checkins.count_documents({"at": {"$gte": since_30}}),
        db.class_templates.count_documents({"archived": {"$ne": True}}),
        db.membership_plans.count_documents({"archived": {"$ne": True}}),
        db.members.count_documents({"status": "cancelled", "cancelled_at": {"$gte": churn_cutoff}}),
        db.organizations.count_documents({**non_test, "memberships_tier": {"$in": ["lite", None]}, "account_type": {"$ne": "member"}}),
        db.organizations.count_documents({**non_test, "memberships_tier": "pro"}),
        db.member_memberships.aggregate(mrr_pipeline).to_list(2000),
        db.class_occurrences.aggregate(occ_pipe).to_list(1),
        db.organizations.find(
            {**non_test, "account_type": {"$ne": "member"}},
            {"_id": 0, "id": 1, "name": 1, "memberships_tier": 1},
        ).to_list(500),
    )

    total_mrr_pence = int(sum(r["mrr_pence"] for r in per_org_rev))
    denom = max(1, active_members + cancelled_30d)
    churn_pct = round(100.0 * cancelled_30d / denom, 2)
    occupancy_pct = 0.0
    if occ_row and occ_row[0]["capacity"]:
        occupancy_pct = round(100.0 * occ_row[0]["booked"] / occ_row[0]["capacity"], 1)

    # ── Per-org alerts: run 2 counts per org in parallel too (was 2N sequential) ──
    async def _org_stats(org_id: str):
        ch, total = await asyncio.gather(
            db.members.count_documents({
                "organization_id": org_id,
                "status": "cancelled",
                "cancelled_at": {"$gte": churn_cutoff},
            }),
            db.members.count_documents({"organization_id": org_id}),
        )
        return ch, total

    org_stats = await asyncio.gather(*(_org_stats(o["id"]) for o in orgs_raw))
    per_org_alerts: list[dict] = []
    for o, (ch, total_members) in zip(orgs_raw, org_stats):
        churn_rate = round(100.0 * ch / max(1, total_members), 1) if total_members else 0.0
        if churn_rate >= 5.0:
            per_org_alerts.append({
                "organization_id": o.get("id"),
                "name": o.get("name") or "—",
                "churn_rate": churn_rate,
                "cancelled_30d": ch,
                "members": total_members,
                "memberships_tier": _org_memberships_tier(o),
            })
    per_org_alerts.sort(key=lambda r: r["churn_rate"], reverse=True)

    # ── 6-month trend: 12 counts in parallel (was 12 sequential) ──
    months: list[tuple[str, str, str]] = []  # (label, start_iso, end_iso)
    now_utc = datetime.now(timezone.utc)
    for i in range(5, -1, -1):
        d = now_utc - timedelta(days=30 * i)
        month_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = (month_start + timedelta(days=32)).replace(day=1) if i > 0 else now_utc
        months.append((month_start.strftime("%b %y"), month_start.isoformat(), cutoff.isoformat()))

    trend_counts = await asyncio.gather(*[
        asyncio.gather(
            db.bookings.count_documents({"booked_at": {"$gte": s, "$lt": c}}),
            db.members.count_documents({"created_at": {"$gte": s, "$lt": c}}),
        )
        for _, s, c in months
    ])
    trend = [
        {"month": label, "bookings": b, "new_members": m}
        for (label, _, _), (b, m) in zip(months, trend_counts)
    ]

    return {
        "kpis": {
            "total_organizations": total_orgs,
            "active_members": active_members,
            "inactive_members": inactive_members,
            "total_mrr_pence": total_mrr_pence,
            "total_bookings": total_bookings,
            "bookings_7d": bookings_7d,
            "bookings_30d": bookings_30d,
            "checkins_30d": checkins_30d,
            "no_shows_30d": no_shows_30d,
            "total_classes": total_classes,
            "total_plans": total_plans,
            "churn_pct_30d": churn_pct,
            "cancelled_30d": cancelled_30d,
            "occupancy_pct_7d": occupancy_pct,
        },
        "tier_split": {"lite": lite, "pro": pro},
        "high_risk_orgs": per_org_alerts[:10],
        "trend": trend,
    }


# ═════════════════════ Organisations ═════════════════════

@router.get("/master-admin/memberships/organizations")
async def memberships_organizations(
    q: str = Query("", description="Fuzzy name search"),
    tier: str = Query("all", description="lite|pro|all"),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    query: dict = {"is_test": {"$ne": True}, "account_type": {"$ne": "member"}}
    if tier in ("lite", "pro"):
        if tier == "lite":
            query["$or"] = [{"memberships_tier": "lite"}, {"memberships_tier": {"$exists": False}}, {"memberships_tier": None}]
        else:
            query["memberships_tier"] = "pro"
    if q:
        query["name"] = {"$regex": q, "$options": "i"}

    orgs = await db.organizations.find(query, {
        "_id": 0, "id": 1, "name": 1, "slug": 1, "subscription_tier": 1,
        "memberships_tier": 1, "memberships_overrides_enabled": 1, "memberships_locked": 1,
        "created_at": 1, "status": 1, "setup_completed": 1,
    }).sort("name", 1).to_list(500)

    out: list[dict] = []
    for o in orgs:
        org_id = o["id"]
        members = await db.members.count_documents({"organization_id": org_id})
        active = await db.members.count_documents({"organization_id": org_id, "status": {"$ne": "cancelled"}})
        cancelled = await db.members.count_documents({
            "organization_id": org_id, "status": "cancelled",
            "cancelled_at": {"$gte": _since(30)},
        })
        plans = await db.membership_plans.count_documents({"organization_id": org_id, "archived": {"$ne": True}})
        classes = await db.class_templates.count_documents({"organization_id": org_id, "archived": {"$ne": True}})
        bookings_30d = await db.bookings.count_documents({"organization_id": org_id, "booked_at": {"$gte": _since(30)}})
        # MRR
        p = await db.member_memberships.aggregate([
            {"$match": {"organization_id": org_id, "status": "active"}},
            {"$lookup": {"from": "membership_plans", "localField": "plan_id", "foreignField": "id", "as": "p"}},
            {"$unwind": "$p"},
            {"$group": {"_id": None, "mrr_pence": {"$sum": {
                "$cond": [{"$eq": ["$p.billing_cycle", "annual"]},
                          {"$divide": [{"$ifNull": ["$p.price_pence", 0]}, 12]},
                          {"$ifNull": ["$p.price_pence", 0]}]
            }}}},
        ]).to_list(1)
        mrr = int(p[0]["mrr_pence"]) if p else 0

        # Standardised indicator: no overrides present → "standard"
        customised = bool(o.get("memberships_overrides_enabled")) or bool(
            await db.membership_plans.count_documents({"organization_id": org_id, "customised_from_template": True})
        )

        churn_rate = round(100.0 * cancelled / max(1, members), 1) if members else 0.0

        out.append({
            "id": org_id,
            "name": o.get("name"),
            "slug": o.get("slug"),
            "memberships_tier": _org_memberships_tier(o),
            "platform_tier": o.get("subscription_tier") or "free",
            "locked": bool(o.get("memberships_locked")),
            "members": members,
            "active_members": active,
            "cancelled_30d": cancelled,
            "churn_rate_30d": churn_rate,
            "plans": plans,
            "classes": classes,
            "bookings_30d": bookings_30d,
            "mrr_pence": mrr,
            "standardisation": "customised" if customised else "standard",
            "status": o.get("status") or "active",
            "created_at": o.get("created_at"),
            "setup_completed": bool(o.get("setup_completed")),
        })

    return {"organizations": out}


@router.get("/master-admin/memberships/organizations/{org_id}")
async def memberships_org_detail(org_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found")

    plans = await db.membership_plans.find({"organization_id": org_id}, {"_id": 0}).to_list(500)
    classes = await db.class_templates.find({"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0}).to_list(500)
    members_total = await db.members.count_documents({"organization_id": org_id})
    bookings_30d = await db.bookings.count_documents({"organization_id": org_id, "booked_at": {"$gte": _since(30)}})
    audit = await db.memberships_admin_audit.find(
        {"target_type": "organization", "target_id": org_id}, {"_id": 0},
    ).sort("at", -1).limit(20).to_list(20)

    return {
        "organization": {
            "id": org_id,
            "name": org.get("name"),
            "slug": org.get("slug"),
            "memberships_tier": _org_memberships_tier(org),
            "platform_tier": org.get("subscription_tier") or "free",
            "locked": bool(org.get("memberships_locked")),
            "overrides_enabled": bool(org.get("memberships_overrides_enabled")),
            "features": org.get("features") or {},
            "branding": org.get("branding") or {},
        },
        "plans": plans,
        "classes": classes,
        "stats": {"members": members_total, "bookings_30d": bookings_30d},
        "audit": audit,
    }


class OrgTierBody(BaseModel):
    memberships_tier: str = Field(..., pattern="^(lite|pro)$")


@router.put("/master-admin/memberships/organizations/{org_id}/tier")
async def set_org_tier(org_id: str, body: OrgTierBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "memberships_tier": 1})
    if org is None:
        raise HTTPException(404, "Organization not found")
    old = _org_memberships_tier(org)
    await db.organizations.update_one(
        {"id": org_id}, {"$set": {"memberships_tier": body.memberships_tier}},
    )
    await _audit(user, "set_tier", "organization", org_id, {"from": old, "to": body.memberships_tier})
    return {"ok": True, "memberships_tier": body.memberships_tier}


class OrgOverrideBody(BaseModel):
    overrides_enabled: Optional[bool] = None
    locked: Optional[bool] = None


class OrgEditBody(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


@router.put("/master-admin/memberships/organizations/{org_id}")
async def edit_org_basics(org_id: str, body: OrgEditBody, user: dict = Depends(get_current_user)):
    """Edit core organisation fields (name/slug/contact_email/notes)."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(404, "Organization not found")
    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    if "name" in updates and not updates["name"].strip():
        raise HTTPException(400, "Name cannot be blank")
    if "slug" in updates:
        s = updates["slug"].strip().lower().replace(" ", "-")
        if not s:
            raise HTTPException(400, "Slug cannot be blank")
        existing = await db.organizations.find_one({"slug": s, "id": {"$ne": org_id}}, {"_id": 0, "id": 1})
        if existing:
            raise HTTPException(409, f"Slug '{s}' is already in use by another organisation")
        updates["slug"] = s
    await db.organizations.update_one({"id": org_id}, {"$set": updates})
    await _audit(user, "edit_org", "organization", org_id, updates)
    return {"ok": True, **updates}


@router.put("/master-admin/memberships/organizations/{org_id}/overrides")
async def set_org_overrides(org_id: str, body: OrgOverrideBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    updates: dict = {}
    if body.overrides_enabled is not None:
        updates["memberships_overrides_enabled"] = body.overrides_enabled
    if body.locked is not None:
        updates["memberships_locked"] = body.locked
    if not updates:
        raise HTTPException(400, "Nothing to update")
    await db.organizations.update_one({"id": org_id}, {"$set": updates})
    await _audit(user, "set_overrides", "organization", org_id, updates)
    return {"ok": True, **updates}


# ═════════════════════ Plan Templates ═════════════════════

class PlanTemplateIn(BaseModel):
    name: str
    kind: str = "recurring"  # recurring | paygo | pack
    billing_cycle: str = "monthly"  # monthly | annual | oneoff
    price_pence: int = 0
    upfront_fee_pence: int = 0
    included_classes: str = "unlimited"  # unlimited | credits | duration
    credits_count: int | None = None
    duration_days: int | None = None
    freeze_allowed: bool = True
    freeze_max_days: int = 90
    cancel_notice_days: int = 0
    grace_period_days: int = 3
    vat_pct: float = 20.0
    default_contract_rules: str | None = None
    description: str | None = None
    colour: str = "#19CDFF"


@router.get("/master-admin/memberships/templates/plans")
async def list_plan_templates(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    rows = await db.membership_plan_templates.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"templates": rows}


@router.post("/master-admin/memberships/templates/plans")
async def create_plan_template(body: PlanTemplateIn, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    doc = {"id": _uuid(), "created_at": _now_iso(), "created_by": user.get("email"), **body.model_dump()}
    await db.membership_plan_templates.insert_one(doc)
    await _audit(user, "template_create", "plan_template", doc["id"], body.model_dump())
    return {"template": {k: v for k, v in doc.items() if k != "_id"}}


@router.patch("/master-admin/memberships/templates/plans/{tpl_id}")
async def update_plan_template(tpl_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    allowed = set(PlanTemplateIn.model_fields.keys())
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = _now_iso()
    await db.membership_plan_templates.update_one({"id": tpl_id}, {"$set": update})
    await _audit(user, "template_update", "plan_template", tpl_id, update)
    return {"ok": True}


@router.delete("/master-admin/memberships/templates/plans/{tpl_id}")
async def delete_plan_template(tpl_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await db.membership_plan_templates.delete_one({"id": tpl_id})
    await _audit(user, "template_delete", "plan_template", tpl_id, {})
    return {"ok": True}


class ApplyTemplateBody(BaseModel):
    organization_ids: list[str]
    lock: bool = False


@router.post("/master-admin/memberships/templates/plans/{tpl_id}/apply")
async def apply_plan_template(tpl_id: str, body: ApplyTemplateBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    tpl = await db.membership_plan_templates.find_one({"id": tpl_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template not found")
    created = 0
    for org_id in body.organization_ids:
        plan_id = _uuid()
        plan_doc = {
            "id": plan_id,
            "organization_id": org_id,
            "name": tpl.get("name") or "Plan",
            "kind": tpl.get("kind") or "recurring",
            "billing_cycle": tpl.get("billing_cycle") or "monthly",
            "price_pence": int(tpl.get("price_pence") or 0),
            "upfront_fee_pence": int(tpl.get("upfront_fee_pence") or 0),
            "included_classes": tpl.get("included_classes") or "unlimited",
            "credits_count": tpl.get("credits_count"),
            "duration_days": tpl.get("duration_days"),
            "freeze_allowed": bool(tpl.get("freeze_allowed", True)),
            "freeze_max_days": int(tpl.get("freeze_max_days") or 90),
            "cancel_notice_days": int(tpl.get("cancel_notice_days") or 0),
            "grace_period_days": int(tpl.get("grace_period_days") or 3),
            "vat_pct": float(tpl.get("vat_pct") or 20.0),
            "colour": tpl.get("colour") or "#19CDFF",
            "description": tpl.get("description"),
            "from_template_id": tpl_id,
            "customised_from_template": False,
            "template_locked": body.lock,
            "active": True,
            "archived": False,
            "created_at": _now_iso(),
        }
        await db.membership_plans.insert_one(plan_doc)
        if body.lock:
            await db.organizations.update_one(
                {"id": org_id}, {"$set": {"memberships_locked": True}},
            )
        created += 1
    await _audit(user, "template_apply", "plan_template", tpl_id, {
        "organization_ids": body.organization_ids, "lock": body.lock, "created": created,
    })
    return {"ok": True, "created": created}


# ═════════════════════ Booking Rules (global) ═════════════════════

_DEFAULT_BOOKING_RULES: dict = {
    "booking_window_hours": 168,
    "cancellation_cutoff_hours": 12,
    "waitlist_enabled": True,
    "max_waitlist": 10,
    "default_capacity": 20,
    "no_show_penalty": "warning",  # warning | credit_forfeit | suspension
    "no_show_strikes_before_block": 3,
    "checkin_window_min": 15,
    "instructor_assignment": "manual",  # manual | auto | balanced
    "allow_site_overrides": True,
}


@router.get("/master-admin/memberships/booking-rules")
async def get_booking_rules(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    doc = await db.memberships_global_rules.find_one({"id": "booking"}, {"_id": 0})
    if not doc:
        doc = {"id": "booking", **_DEFAULT_BOOKING_RULES, "updated_at": None, "updated_by": None}
    return {"rules": doc}


class BookingRulesBody(BaseModel):
    booking_window_hours: int = Field(ge=1, le=4320)
    cancellation_cutoff_hours: int = Field(ge=0, le=720)
    waitlist_enabled: bool
    max_waitlist: int = Field(ge=0, le=500)
    default_capacity: int = Field(ge=1, le=500)
    no_show_penalty: str = Field(pattern="^(warning|credit_forfeit|suspension)$")
    no_show_strikes_before_block: int = Field(ge=1, le=20)
    checkin_window_min: int = Field(ge=0, le=120)
    instructor_assignment: str = Field(pattern="^(manual|auto|balanced)$")
    allow_site_overrides: bool


@router.put("/master-admin/memberships/booking-rules")
async def update_booking_rules(body: BookingRulesBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    old = await db.memberships_global_rules.find_one({"id": "booking"}, {"_id": 0}) or {}
    payload = body.model_dump()
    await db.memberships_global_rules.update_one(
        {"id": "booking"},
        {"$set": {**payload, "updated_at": _now_iso(), "updated_by": user.get("email")}},
        upsert=True,
    )
    await _audit(user, "booking_rules_update", "global", "booking", {"from": old, "to": payload})
    return {"ok": True}


# ═════════════════════ Subscription Tier Control (Lite vs Pro) ═════════════════════

_TIER_FEATURE_MATRIX: dict = {
    "lite": {
        "basic_memberships": True,
        "class_booking": True,
        "limited_reporting": True,
        "advanced_reporting": False,
        "ai_insights": False,
        "multi_site_visibility": False,
        "retention_tools": False,
        "crm_integration_depth": False,
    },
    "pro": {
        "basic_memberships": True,
        "class_booking": True,
        "limited_reporting": True,
        "advanced_reporting": True,
        "ai_insights": True,
        "multi_site_visibility": True,
        "retention_tools": True,
        "crm_integration_depth": True,
    },
}


@router.get("/master-admin/memberships/tiers")
async def get_tier_matrix(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    # Allow admin overrides stored per key
    override = await db.memberships_global_rules.find_one({"id": "tier_matrix"}, {"_id": 0})
    matrix = (override or {}).get("matrix") or _TIER_FEATURE_MATRIX

    # Count orgs by tier
    non_test = {"is_test": {"$ne": True}, "account_type": {"$ne": "member"}}
    lite = await db.organizations.count_documents({**non_test, "$or": [
        {"memberships_tier": "lite"}, {"memberships_tier": {"$exists": False}}, {"memberships_tier": None},
    ]})
    pro = await db.organizations.count_documents({**non_test, "memberships_tier": "pro"})

    pro_orgs = await db.organizations.find(
        {**non_test, "memberships_tier": "pro"},
        {"_id": 0, "id": 1, "name": 1, "slug": 1},
    ).sort("name", 1).to_list(500)

    return {"matrix": matrix, "counts": {"lite": lite, "pro": pro}, "pro_orgs": pro_orgs}


class TierMatrixBody(BaseModel):
    matrix: dict


@router.put("/master-admin/memberships/tiers")
async def update_tier_matrix(body: TierMatrixBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    old = await db.memberships_global_rules.find_one({"id": "tier_matrix"}, {"_id": 0}) or {}
    await db.memberships_global_rules.update_one(
        {"id": "tier_matrix"},
        {"$set": {"matrix": body.matrix, "updated_at": _now_iso(), "updated_by": user.get("email")}},
        upsert=True,
    )
    await _audit(user, "tier_matrix_update", "global", "tier_matrix", {"from": old.get("matrix"), "to": body.matrix})
    return {"ok": True}


# ═════════════════════ Revenue & Billing Oversight ═════════════════════

@router.get("/master-admin/memberships/revenue")
async def revenue_oversight(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    # MRR by org
    by_org = await db.member_memberships.aggregate([
        {"$match": {"status": "active"}},
        {"$lookup": {"from": "membership_plans", "localField": "plan_id", "foreignField": "id", "as": "p"}},
        {"$unwind": "$p"},
        {"$group": {
            "_id": "$organization_id",
            "mrr_pence": {"$sum": {"$cond": [
                {"$eq": ["$p.billing_cycle", "annual"]},
                {"$divide": [{"$ifNull": ["$p.price_pence", 0]}, 12]},
                {"$ifNull": ["$p.price_pence", 0]},
            ]}},
            "members": {"$sum": 1},
        }},
        {"$sort": {"mrr_pence": -1}},
    ]).to_list(500)
    # Iter 216h271 — guard against orphan org docs missing `name` or
    # `id` (a fixture / partial migration can leave these unset). The
    # previous strict dict-access blew up the whole revenue endpoint
    # with KeyError → 500 → frontend Promise.all rejected → the
    # entire Master Admin Memberships page stayed in loading state.
    org_names = {
        o["id"]: o.get("name") or "—"
        for o in await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
        if o.get("id")
    }
    by_org = [{
        "organization_id": r["_id"], "name": org_names.get(r["_id"]) or "—",
        "mrr_pence": int(r["mrr_pence"]), "members": r["members"],
    } for r in by_org]

    # MRR by plan type (kind)
    by_kind = await db.member_memberships.aggregate([
        {"$match": {"status": "active"}},
        {"$lookup": {"from": "membership_plans", "localField": "plan_id", "foreignField": "id", "as": "p"}},
        {"$unwind": "$p"},
        {"$group": {
            "_id": "$p.kind",
            "mrr_pence": {"$sum": {"$cond": [
                {"$eq": ["$p.billing_cycle", "annual"]},
                {"$divide": [{"$ifNull": ["$p.price_pence", 0]}, 12]},
                {"$ifNull": ["$p.price_pence", 0]},
            ]}},
            "members": {"$sum": 1},
        }},
    ]).to_list(20)
    by_kind = [{"kind": r["_id"] or "—", "mrr_pence": int(r["mrr_pence"]), "members": r["members"]} for r in by_kind]

    # Failed payments & refunds (last 90d)
    failed = await db.payment_transactions.count_documents({"status": "failed", "created_at": {"$gte": _since(90)}})
    refunds = await db.payment_transactions.count_documents({"status": "refunded", "created_at": {"$gte": _since(90)}})
    total_txn = await db.payment_transactions.count_documents({"created_at": {"$gte": _since(90)}})

    # 6-month MRR trend (snapshot via active members × plan at point-in-time is too heavy;
    # use revenue_booked from payment_transactions instead)
    trend: list[dict] = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=30 * i)
        month_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = (month_start + timedelta(days=32)).replace(day=1) if i > 0 else datetime.now(timezone.utc)
        pipe = [
            {"$match": {
                "created_at": {"$gte": month_start.isoformat(), "$lt": cutoff.isoformat()},
                "status": {"$in": ["succeeded", "paid"]},
            }},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount_pence", 0]}}}},
        ]
        row = await db.payment_transactions.aggregate(pipe).to_list(1)
        trend.append({
            "month": month_start.strftime("%b %y"),
            "revenue_pence": int(row[0]["total"]) if row else 0,
        })

    return {
        "by_org": by_org[:50],
        "by_kind": by_kind,
        "payments": {
            "failed_90d": failed, "refunds_90d": refunds, "total_90d": total_txn,
            "failed_pct": round(100.0 * failed / max(1, total_txn), 1) if total_txn else 0.0,
        },
        "trend": trend,
        "total_mrr_pence": int(sum(r["mrr_pence"] for r in by_org)),
    }


# ═════════════════════ Engagement & Retention ═════════════════════

@router.get("/master-admin/memberships/engagement")
async def engagement_retention(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    # Cross-platform bookings per day for last 30 days
    today = datetime.now(timezone.utc).date()
    daily: list[dict] = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        iso_s = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        iso_e = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
        b = await db.bookings.count_documents({"booked_at": {"$gte": iso_s, "$lt": iso_e}})
        c = await db.member_checkins.count_documents({"at": {"$gte": iso_s, "$lt": iso_e}})
        daily.append({"date": d.isoformat(), "bookings": b, "checkins": c})

    # Peak hours across all class occurrences in last 30d
    from collections import Counter as _Counter
    hours = _Counter()
    cursor = db.class_occurrences.find(
        {"starts_at": {"$gte": _since(30)}},
        {"_id": 0, "starts_at": 1, "bookings_count": 1},
    )
    async for occ in cursor:
        try:
            h = int(str(occ["starts_at"])[11:13])
            hours[h] += int(occ.get("bookings_count") or 0)
        except Exception:
            continue
    peak = [{"hour": f"{h:02d}:00", "bookings": hours.get(h, 0)} for h in range(24)]

    # Utilisation by org (last 30d)
    orgs = await db.organizations.find(
        {"is_test": {"$ne": True}, "account_type": {"$ne": "member"}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(500)
    util_rows: list[dict] = []
    for o in orgs:
        if not o.get("id"):
            continue
        row = await db.class_occurrences.aggregate([
            {"$match": {"organization_id": o["id"], "starts_at": {"$gte": _since(30)}}},
            {"$group": {"_id": None,
                        "capacity": {"$sum": {"$ifNull": ["$capacity", 0]}},
                        "booked": {"$sum": {"$ifNull": ["$bookings_count", 0]}}}}
        ]).to_list(1)
        if row and row[0]["capacity"]:
            util = round(100.0 * row[0]["booked"] / row[0]["capacity"], 1)
            util_rows.append({
                "organization_id": o["id"], "name": o.get("name") or "—",
                "capacity_30d": int(row[0]["capacity"]),
                "booked_30d": int(row[0]["booked"]),
                "utilisation_pct": util,
            })
    util_rows.sort(key=lambda r: r["utilisation_pct"], reverse=True)

    # No-show rate
    total_30d = await db.bookings.count_documents({"booked_at": {"$gte": _since(30)}})
    no_shows = await db.bookings.count_documents({"status": "no_show", "booked_at": {"$gte": _since(30)}})
    no_show_pct = round(100.0 * no_shows / max(1, total_30d), 1) if total_30d else 0.0

    # Churn by org
    churn_rows: list[dict] = []
    for o in orgs:
        if not o.get("id"):
            continue
        total = await db.members.count_documents({"organization_id": o["id"]})
        can30 = await db.members.count_documents({
            "organization_id": o["id"], "status": "cancelled",
            "cancelled_at": {"$gte": _since(30)},
        })
        if total:
            churn_rows.append({
                "organization_id": o["id"], "name": o.get("name") or "—",
                "members": total, "cancelled_30d": can30,
                "churn_rate_30d": round(100.0 * can30 / total, 1),
            })
    churn_rows.sort(key=lambda r: r["churn_rate_30d"], reverse=True)

    return {
        "daily": daily,
        "peak_hours": peak,
        "utilisation": util_rows[:20],
        "no_show": {"total_30d": total_30d, "no_shows_30d": no_shows, "pct": no_show_pct},
        "churn": churn_rows[:20],
    }


# ═════════════════════ Instructors ═════════════════════

@router.get("/master-admin/memberships/instructors")
async def instructor_leaderboard(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    # Group bookings by instructor via class_occurrences → class_templates
    pipe = [
        {"$match": {"starts_at": {"$gte": _since(30)}}},
        {"$lookup": {"from": "class_templates", "localField": "template_id", "foreignField": "id", "as": "t"}},
        {"$unwind": {"path": "$t", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {
                "organization_id": "$organization_id",
                "instructor_name": {"$ifNull": ["$t.instructor_name", "$instructor_name"]},
            },
            "classes_delivered": {"$sum": 1},
            "bookings": {"$sum": {"$ifNull": ["$bookings_count", 0]}},
            "capacity": {"$sum": {"$ifNull": ["$capacity", 0]}},
        }},
    ]
    rows = await db.class_occurrences.aggregate(pipe).to_list(2000)
    # Iter 216h271 — same orphan-org guard as revenue_oversight (above).
    org_names = {
        o["id"]: o.get("name") or "—"
        for o in await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
        if o.get("id")
    }
    out: list[dict] = []
    for r in rows:
        name = r["_id"].get("instructor_name") or "—"
        if name == "—":
            continue
        cap = int(r.get("capacity") or 0)
        booked = int(r.get("bookings") or 0)
        out.append({
            "organization_id": r["_id"]["organization_id"],
            "org_name": org_names.get(r["_id"]["organization_id"]) or "—",
            "instructor_name": name,
            "classes_delivered_30d": int(r["classes_delivered"]),
            "bookings_30d": booked,
            "capacity_30d": cap,
            "utilisation_pct": round(100.0 * booked / cap, 1) if cap else 0.0,
        })
    out.sort(key=lambda r: r["utilisation_pct"], reverse=True)
    top = out[:10]
    under = [r for r in out if r["utilisation_pct"] < 40.0][:10]
    return {"leaderboard": out, "top": top, "underperformers": under}


# ═════════════════════ AI Insights ═════════════════════

@router.get("/master-admin/memberships/ai-insights")
async def ai_insights(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    # Build cross-platform context
    ov = await memberships_overview(user=user)  # reuse the aggregation
    eng = await engagement_retention(user=user)

    ctx = {
        "kpis": ov["kpis"],
        "tier_split": ov["tier_split"],
        "high_risk_orgs": ov["high_risk_orgs"][:5],
        "no_show_pct": eng["no_show"]["pct"],
        "top_churn": eng["churn"][:5],
        "low_util": [u for u in eng["utilisation"] if u["utilisation_pct"] < 40][:5],
    }

    prompt = (
        "You are analysing a multi-tenant gym SaaS platform. Below are "
        "cross-organisation KPIs. Return STRICT JSON of the form: "
        '{"insights": [{"severity":"high|medium|low","title":"...","detail":"...","action":"...","org_id":"..."}]}'
        " — max 6 insights, ranked by severity. Prioritise churn, utilisation, "
        "revenue opportunity (Lite → Pro upgrade), and no-show risk. "
        "Be specific — reference organisation names when helpful.\n\n"
        f"CONTEXT: {ctx}"
    )
    raw = await _chat(prompt, max_tokens=900)
    parsed = _parse_json(raw, fallback={"insights": []})
    insights = parsed.get("insights") or []

    # Always add a deterministic safety-net alert set so UI never empty
    if not insights:
        fallback: list[dict] = []
        for hr in (ctx.get("high_risk_orgs") or [])[:3]:
            fallback.append({
                "severity": "high",
                "title": f"{hr['name']} — high churn",
                "detail": f"Churn rate {hr['churn_rate']}% over 30d with {hr['cancelled_30d']} cancellations.",
                "action": "Open organisation and review retention programs; enable win-back campaign.",
                "org_id": hr["organization_id"],
            })
        for lu in (ctx.get("low_util") or [])[:2]:
            fallback.append({
                "severity": "medium",
                "title": f"Low utilisation at {lu['name']}",
                "detail": f"Only {lu['utilisation_pct']}% of capacity filled in last 30 days.",
                "action": "Review scheduling and instructor rotation; consider canceling low-fill classes.",
                "org_id": lu["organization_id"],
            })
        if ctx["tier_split"]["lite"] > 0:
            fallback.append({
                "severity": "low",
                "title": "Upgrade opportunity — Lite → Pro",
                "detail": f"{ctx['tier_split']['lite']} organisations on Lite tier. Pro unlocks AI insights and retention tools.",
                "action": "Trigger Pro upgrade outreach for top-performing Lite orgs.",
                "org_id": None,
            })
        insights = fallback

    return {"insights": insights[:8], "generated_at": _now_iso()}


# ═════════════════════ Feature Flags ═════════════════════

_DEFAULT_FEATURE_FLAGS: dict = {
    "memberships_enabled": True,
    "bookings_enabled": True,
    "reporting_enabled": True,
    "ai_features_enabled": True,
    "public_brag_page": True,
    "winback_emails": True,
    "qr_posters": True,
    "referral_rewards": True,
    "attendance_streaks": True,
    "social_pulse": True,
    "beta_class_waitlist_auto_promote": False,
    "beta_ai_forecasting": False,
    "beta_smart_pricing": False,
}


@router.get("/master-admin/memberships/feature-flags")
async def get_feature_flags(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    doc = await db.memberships_global_rules.find_one({"id": "feature_flags"}, {"_id": 0})
    flags = (doc or {}).get("flags") or _DEFAULT_FEATURE_FLAGS
    return {"flags": flags, "updated_at": (doc or {}).get("updated_at"), "updated_by": (doc or {}).get("updated_by")}


class FeatureFlagsBody(BaseModel):
    flags: dict


@router.put("/master-admin/memberships/feature-flags")
async def update_feature_flags(body: FeatureFlagsBody, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    old = await db.memberships_global_rules.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
    await db.memberships_global_rules.update_one(
        {"id": "feature_flags"},
        {"$set": {"flags": body.flags, "updated_at": _now_iso(), "updated_by": user.get("email")}},
        upsert=True,
    )
    await _audit(user, "feature_flags_update", "global", "feature_flags",
                 {"from": old.get("flags"), "to": body.flags})
    return {"ok": True}


# ═════════════════════ Audit Log ═════════════════════

@router.get("/master-admin/memberships/audit")
async def get_audit_log(limit: int = 50, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    limit = max(1, min(limit, 500))
    rows = await db.memberships_admin_audit.find(
        {}, {"_id": 0},
    ).sort("at", -1).limit(limit).to_list(limit)
    return {"audit": rows}
