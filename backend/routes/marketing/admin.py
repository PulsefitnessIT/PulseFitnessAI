"""Master Admin: marketing plans, subscriptions, analytics.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

from routes.marketing.helpers import (
    _get_plan,
    _now_iso,
    _require_admin,
    _seed_default_plans_once,
)

router = APIRouter()


# ───────────────────────── Master Admin: Plans + Analytics ─────────────


@router.get("/master-admin/marketing/plans")
async def admin_list_plans(user: dict = Depends(get_current_user)):
    _require_admin(user)
    await _seed_default_plans_once()
    plans = await db.marketing_plans.find({}, {"_id": 0}).sort("sort_order", 1).to_list(length=20)
    return {"plans": plans}


@router.put("/master-admin/marketing/plans/{plan_id}")
async def admin_update_plan(plan_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    _require_admin(user)
    allowed = {"name", "monthly_price_gbp", "annual_price_gbp", "limits", "features", "active",
               "stripe_price_id_monthly", "stripe_price_id_annual"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No editable fields supplied")
    updates["updated_at"] = _now_iso()
    res = await db.marketing_plans.update_one({"id": plan_id}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(404, "Plan not found")
    plan = await _get_plan(plan_id)
    return {"plan": plan}


@router.get("/master-admin/marketing/analytics")
async def admin_marketing_analytics(brand: str = "all", user: dict = Depends(get_current_user)):
    """Platform-wide marketing KPIs. Pulse-scoped via the same helper used
    elsewhere in master_admin.

    Iter 216h25 — accepts a ``?brand=`` query param so Pulse Fitness Master
    Admins can focus the view on Pulse-only or Pulse Fitness-only orgs from
    the top-bar BrandPicker. Pulse Master Admins remain locked to
    ``pulse`` regardless of the query param.
    """
    _require_admin(user)
    from routes.master_admin import is_pulse_only, PULSE_VISIBLE_ACCOUNT_TYPES
    from utils.brand_filter import normalise_brand, brand_filter_clause

    canonical_brand = "pulse" if is_pulse_only(user) else normalise_brand(brand)

    org_filter: dict = {}
    if is_pulse_only(user):
        ps = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}}, {"_id": 0, "id": 1},
        ).to_list(length=None)
        ids = [o["id"] for o in ps]
        org_filter = {"organization_id": {"$in": ids}}
    elif canonical_brand != "all":
        clause = brand_filter_clause(canonical_brand, collection="organizations")
        if clause:
            brand_orgs = await db.organizations.find(clause, {"_id": 0, "id": 1}).to_list(length=None)
            ids = [o["id"] for o in brand_orgs]
            org_filter = {"organization_id": {"$in": ids}}

    total_subs = await db.marketing_subscriptions.count_documents({**org_filter, "status": {"$in": ["active", "trial"]}})
    by_plan: dict[str, int] = {}
    cursor = db.marketing_subscriptions.find({**org_filter}, {"_id": 0, "plan_id": 1, "status": 1})
    async for s in cursor:
        by_plan[s.get("plan_id", "unknown")] = by_plan.get(s.get("plan_id", "unknown"), 0) + 1

    plans = await db.marketing_plans.find({}, {"_id": 0}).to_list(length=20)
    plan_prices = {p["id"]: p.get("monthly_price_gbp", 0) for p in plans}
    mrr_gbp = sum(plan_prices.get(pid, 0) * count for pid, count in by_plan.items())

    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    emails_30d = await db.marketing_messages.count_documents(
        {**org_filter, "channel": "email", "sent_at": {"$gte": month_ago}},
    )
    ai_30d = await db.marketing_creative_assets.count_documents(
        {**org_filter, "created_at": {"$gte": month_ago}},
    )
    campaigns_30d = await db.marketing_campaigns.count_documents(
        {**org_filter, "sent_at": {"$gte": month_ago}},
    )
    journeys_active = await db.marketing_journeys.count_documents(
        {**org_filter, "status": "active"},
    )

    # Top-active orgs by emails sent
    pipeline: list[dict[str, Any]] = [
        {"$match": {"channel": "email", "sent_at": {"$gte": month_ago}, **org_filter}},
        {"$group": {"_id": "$organization_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top: list[dict] = []
    async for row in db.marketing_messages.aggregate(pipeline):
        org = await db.organizations.find_one({"id": row["_id"]}, {"_id": 0, "name": 1})
        top.append({"organization_id": row["_id"], "name": (org or {}).get("name", "—"), "emails_30d": row["count"]})

    return {
        "total_subscriptions": total_subs,
        "by_plan": by_plan,
        "mrr_gbp": mrr_gbp,
        "emails_30d": emails_30d,
        "ai_generations_30d": ai_30d,
        "campaigns_30d": campaigns_30d,
        "journeys_active": journeys_active,
        "top_orgs_by_email": top,
        "scoped": is_pulse_only(user),
        "brand": canonical_brand,
    }


@router.get("/master-admin/marketing/subscriptions")
async def admin_list_subscriptions(brand: str = "all", user: dict = Depends(get_current_user)):
    """Iter 216h25 — accepts ``?brand=`` so Pulse Fitness Master Admins can
    focus the view on Pulse-only or Pulse Fitness-only orgs. Pulse Master
    Admins remain locked to ``pulse`` regardless."""
    _require_admin(user)
    from routes.master_admin import is_pulse_only, PULSE_VISIBLE_ACCOUNT_TYPES
    from utils.brand_filter import normalise_brand, brand_filter_clause

    canonical_brand = "pulse" if is_pulse_only(user) else normalise_brand(brand)
    flt: dict = {}
    if is_pulse_only(user):
        ps = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}}, {"_id": 0, "id": 1},
        ).to_list(length=None)
        flt = {"organization_id": {"$in": [o["id"] for o in ps]}}
    elif canonical_brand != "all":
        clause = brand_filter_clause(canonical_brand, collection="organizations")
        if clause:
            brand_orgs = await db.organizations.find(clause, {"_id": 0, "id": 1}).to_list(length=None)
            flt = {"organization_id": {"$in": [o["id"] for o in brand_orgs]}}
    subs = await db.marketing_subscriptions.find(flt, {"_id": 0}).sort("created_at", -1).limit(500).to_list(length=500)
    # Decorate with org name + plan price.
    org_ids = list({s["organization_id"] for s in subs})
    orgs = {o["id"]: o for o in await db.organizations.find(
        {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    ).to_list(length=None)}
    plans = {p["id"]: p for p in await db.marketing_plans.find({}, {"_id": 0}).to_list(length=20)}
    for s in subs:
        s["organization_name"] = orgs.get(s["organization_id"], {}).get("name")
        s["account_type"] = orgs.get(s["organization_id"], {}).get("account_type")
        s["plan"] = plans.get(s.get("plan_id"), {})
    return {"subscriptions": subs}


@router.put("/master-admin/marketing/subscriptions/{organization_id}")
async def admin_set_subscription(organization_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    _require_admin(user)
    allowed = {"plan_id", "status", "comp_seats", "trial_ends_at", "current_period_end"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No editable fields supplied")
    updates["updated_at"] = _now_iso()
    await db.marketing_subscriptions.update_one(
        {"organization_id": organization_id}, {"$set": updates}, upsert=True,
    )
    sub = await db.marketing_subscriptions.find_one({"organization_id": organization_id}, {"_id": 0})
    return {"subscription": sub}


@router.delete("/master-admin/marketing/subscriptions/{organization_id}")
async def admin_delete_subscription(organization_id: str, user: dict = Depends(get_current_user)):
    """Hard-delete a marketing subscription. The org loses Marketing Suite
    access until a new subscription is provisioned."""
    _require_admin(user)
    res = await db.marketing_subscriptions.delete_one({"organization_id": organization_id})
    return {"deleted": res.deleted_count}


# ──────────── Iter 235: read-only cross-org Campaigns & Journeys ────────────


async def _admin_org_scope(user: dict, brand: str) -> dict:
    """organization_id filter implementing Pulse scoping + the top-bar
    BrandPicker, shared by the read-only cross-org browsers below."""
    from routes.master_admin import is_pulse_only, PULSE_VISIBLE_ACCOUNT_TYPES
    from utils.brand_filter import normalise_brand, brand_filter_clause

    if is_pulse_only(user):
        ps = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}}, {"_id": 0, "id": 1},
        ).to_list(length=None)
        return {"organization_id": {"$in": [o["id"] for o in ps]}}
    canonical = normalise_brand(brand)
    if canonical != "all":
        clause = brand_filter_clause(canonical, collection="organizations")
        if clause:
            brand_orgs = await db.organizations.find(clause, {"_id": 0, "id": 1}).to_list(length=None)
            return {"organization_id": {"$in": [o["id"] for o in brand_orgs]}}
    return {}


async def _decorate_org(rows: list[dict]) -> None:
    """Attach organization_name + account_type to each row in-place."""
    org_ids = list({r.get("organization_id") for r in rows if r.get("organization_id")})
    orgs = {o["id"]: o for o in await db.organizations.find(
        {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    ).to_list(length=None)}
    for r in rows:
        o = orgs.get(r.get("organization_id"), {})
        r["organization_name"] = o.get("name")
        r["account_type"] = o.get("account_type")


@router.get("/master-admin/marketing/campaigns")
async def admin_list_campaigns(brand: str = "all", status: str = "all",
                               user: dict = Depends(get_current_user)):
    """Read-only cross-org campaign browser for Master Admins. Lightweight
    projection only — never returns campaign body content."""
    _require_admin(user)
    flt = await _admin_org_scope(user, brand)
    if status != "all":
        flt["status"] = status
    projection = {
        "_id": 0, "id": 1, "organization_id": 1, "name": 1, "status": 1,
        "channel": 1, "metrics": 1, "created_at": 1, "updated_at": 1,
        "sent_at": 1, "ab_test.enabled": 1,
    }
    rows = await db.marketing_campaigns.find(flt, projection).sort(
        "updated_at", -1).limit(300).to_list(length=300)
    await _decorate_org(rows)
    total = await db.marketing_campaigns.count_documents(flt)
    return {"campaigns": rows, "total": total}


@router.get("/master-admin/marketing/journeys")
async def admin_list_journeys(brand: str = "all", status: str = "all",
                              user: dict = Depends(get_current_user)):
    """Read-only cross-org journey browser for Master Admins. Returns a
    node_count instead of the full node graph."""
    _require_admin(user)
    flt = await _admin_org_scope(user, brand)
    if status != "all":
        flt["status"] = status
    projection = {
        "_id": 0, "id": 1, "organization_id": 1, "name": 1, "status": 1,
        "trigger": 1, "metrics": 1, "nodes": 1, "created_at": 1,
        "updated_at": 1, "template_id": 1,
    }
    rows = await db.marketing_journeys.find(flt, projection).sort(
        "updated_at", -1).limit(300).to_list(length=300)
    for r in rows:
        r["node_count"] = len(r.pop("nodes", []) or [])
    await _decorate_org(rows)
    total = await db.marketing_journeys.count_documents(flt)
    return {"journeys": rows, "total": total}


__all__ = ["router"]
