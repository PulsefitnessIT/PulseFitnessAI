"""Master Admin → Service Desk customers.

Founder lens on the Service Desk *product's* own customers — the
``service_provider`` orgs that sign up, trial, set up and use the desk.
Surfaces the full lifecycle (signup → trial → setup → usage → conversion)
that Master Admin previously had no view of.

Endpoint: GET /api/master-admin/service-desk/customers
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(tags=["master-admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _health(*, converted: bool, trial_status: str | None, days_left: int | None,
            setup: bool, cases_7d: int, cases_total: int) -> tuple[str, str]:
    """(status_key, label) describing where the customer is in their journey."""
    if converted:
        return ("converted", "Paying" if cases_7d else "Paying · quiet")
    if trial_status in ("expired", "suspended") or (days_left is not None and days_left < 0):
        return ("churned_trial", "Trial lapsed")
    if cases_7d > 0:
        return ("active", "Active user")
    if not setup:
        return ("onboarding", "Setting up")
    if cases_total == 0:
        return ("at_risk", "Trial · no usage")
    return ("dormant", "Dormant")


@router.get("/master-admin/service-desk/customers")
async def service_desk_customers(user: dict = Depends(get_current_user)) -> dict:
    from routes.master_admin import require_master_admin
    require_master_admin(user)
    now = _now()
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()

    orgs = await db.organizations.find(
        {"account_type": "service_provider"}, {"_id": 0}).to_list(1000)
    org_ids = [o["id"] for o in orgs]

    # Usage rollup (one pass over svc_cases).
    case_rows = await db.svc_cases.aggregate([
        {"$match": {"organization_id": {"$in": org_ids}}},
        {"$group": {"_id": "$organization_id", "total": {"$sum": 1},
                    "last_at": {"$max": {"$ifNull": ["$updated_at", "$created_at"]}},
                    "recent7d": {"$sum": {"$cond": [{"$gte": ["$created_at", cutoff_7d]}, 1, 0]}}}},
    ]).to_list(2000)
    cases = {r["_id"]: r for r in case_rows}

    eng_rows = await db.org_chart_nodes.aggregate([
        {"$match": {"organization_id": {"$in": org_ids}, "is_engineer": True}},
        {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
    ]).to_list(2000)
    engineers = {r["_id"]: r["n"] for r in eng_rows}

    user_rows = await db.users.aggregate([
        {"$match": {"organization_id": {"$in": org_ids}}},
        {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
    ]).to_list(2000)
    users = {r["_id"]: r["n"] for r in user_rows}

    customers: list[dict] = []
    kpi = {"total": len(orgs), "new_30d": 0, "trials_active": 0, "trials_expiring_7d": 0,
           "trials_expired": 0, "converted": 0, "active_this_week": 0, "total_cases": 0}

    for o in orgs:
        oid = o["id"]
        c = cases.get(oid, {})
        cases_total = c.get("total", 0)
        cases_7d = c.get("recent7d", 0)
        ends = _parse(o.get("trial_ends_at"))
        days_left = (ends - now).days if ends else None
        converted = bool(o.get("subscription_active")) or o.get("trial_status") == "converted"
        trial_status = o.get("trial_status")
        setup = bool(o.get("service_ops_setup_complete"))
        status_key, status_label = _health(
            converted=converted, trial_status=trial_status, days_left=days_left,
            setup=setup, cases_7d=cases_7d, cases_total=cases_total)

        created = _parse(o.get("created_at"))
        if created and created.isoformat() >= cutoff_30d:
            kpi["new_30d"] += 1
        if converted:
            kpi["converted"] += 1
        elif trial_status == "active":
            kpi["trials_active"] += 1
            if days_left is not None and 0 <= days_left <= 7:
                kpi["trials_expiring_7d"] += 1
        elif trial_status in ("expired", "suspended"):
            kpi["trials_expired"] += 1
        if cases_7d > 0:
            kpi["active_this_week"] += 1
        kpi["total_cases"] += cases_total

        customers.append({
            "id": oid,
            "name": o.get("name"),
            "brand": o.get("service_desk_brand"),
            "created_at": o.get("created_at"),
            "trial_status": trial_status,
            "trial_ends_at": o.get("trial_ends_at"),
            "days_left": days_left,
            "subscription_active": converted,
            "subscription_tier": o.get("subscription_tier"),
            "setup_complete": setup,
            "engineers": engineers.get(oid, 0),
            "users": users.get(oid, 0),
            "cases_total": cases_total,
            "cases_7d": cases_7d,
            "last_activity": c.get("last_at"),
            "status": status_key,
            "status_label": status_label,
        })

    customers.sort(key=lambda r: (r.get("created_at") or ""), reverse=True)
    kpi["conversion_rate"] = round(100 * kpi["converted"] / kpi["total"], 1) if kpi["total"] else 0
    return {"summary": kpi, "customers": customers, "as_of": now.isoformat()}
