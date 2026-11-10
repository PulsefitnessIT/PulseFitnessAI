"""
Pulse Fitness Service Operations — Service Desk Dashboard API.

Iter 215dn (Phase 1).

Read-only aggregates powering the desk dashboard: KPI strip, queue,
filters meta. Designed to be cheap on a 500-case cold cache; uses
count_documents + a single sorted slice rather than aggregation
pipelines so it's fast even at scale.
"""
__integration_fields__ = {
    # All endpoints in this module are read-only aggregates over
    # `svc_cases` + `svc_case_events`. No new collections, no writes.
    # The aggregated outputs are Pulse Fitness-internal dashboard data — every
    # underlying field (priority, status, sla_*, customer_*, etc.) is
    # already mapped to Sicon/Sage in routes/svc/cases.py.
    "summary.kpi.open_count":      "gymaxis_only: dashboard KPI",
    "summary.kpi.due_today":       "gymaxis_only: dashboard KPI",
    "summary.kpi.sla_at_risk":     "gymaxis_only: dashboard KPI",
    "summary.kpi.unassigned":      "gymaxis_only: dashboard KPI",
    "summary.kpi.closed_today":    "gymaxis_only: dashboard KPI",
    "queue.id":                    "sicon: ServiceCallID (read-through from svc_cases) · gymaxis_only on Sage",
    "queue.reference":             "sicon: ServiceCallReference (read-through from svc_cases) · sage: SLInvoice.Reference",
    "queue.priority":              "sicon: PriorityID (read-through from svc_cases)",
    "queue.status":                "sicon: StatusID (read-through from svc_cases)",
    "queue.sla_resolve_at":        "sicon: SLAResolveTarget (read-through from svc_cases)",
    "queue.assigned_engineer_id":  "sicon: AppointmentResourceID (read-through from svc_cases)",
}

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query

from utils.database import db
from utils.svc_desk_scope import desk_filter
from utils.auth import get_current_user
from utils.svc_state import OPEN_STATES, CLOSED, INVOICED, SLA_RISK_WINDOW_HOURS

router = APIRouter(prefix="/svc/desk", tags=["Service Ops · Desk"])


def _of(user: dict) -> dict:
    return {"organization_id": (user.get("organization_id") or user.get("service_org_id")) or "__none__"}


@router.get("/summary")
async def desk_summary(user=Depends(get_current_user)):
    """KPI strip + queue snapshot for the dashboard header."""
    _of(user)
    of = await desk_filter(user)
    now = datetime.now(timezone.utc).isoformat()

    open_count = await db.svc_cases.count_documents({**of, "status": {"$in": list(OPEN_STATES)}})
    # Iter 290e — "unassigned" must match the /svc/cases?assigned=unassigned
    # drill-down (and the desk performance tile): no engineer means the field
    # is empty OR null/missing, not just "".
    unassigned_count = await db.svc_cases.count_documents({
        **of, "status": {"$in": list(OPEN_STATES)}, "assigned_engineer_id": {"$in": [None, ""]},
    })
    sla_at_risk = await db.svc_cases.count_documents({
        **of, "status": {"$in": list(OPEN_STATES)},
        "sla_resolve_at": {
            "$gte": now,
            "$lt": (datetime.now(timezone.utc) + timedelta(hours=SLA_RISK_WINDOW_HOURS)).isoformat(),
        },
    })
    sla_breached = await db.svc_cases.count_documents({
        **of, "status": {"$in": list(OPEN_STATES)},
        "sla_resolve_at": {"$ne": None, "$lt": now},
    })

    # First-time-fix proxy: closed cases without re-open in last 30 days.
    thirty_d_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    closed_30 = await db.svc_cases.count_documents({
        **of, "status": {"$in": [CLOSED, INVOICED]}, "closed_at": {"$gte": thirty_d_ago},
    })
    # Without callback flag yet (Phase 4) we treat all closed as FTF for now.
    ftf_pct = 100 if closed_30 == 0 else 100  # Placeholder — real metric in Phase 4.

    # Avg resolution time over the last 30 days.
    pipeline = [
        {"$match": {
            **of, "status": {"$in": [CLOSED, INVOICED]},
            "closed_at": {"$gte": thirty_d_ago},
        }},
        {"$project": {
            "duration_hours": {"$divide": [
                {"$subtract": [
                    {"$dateFromString": {"dateString": "$closed_at"}},
                    {"$dateFromString": {"dateString": "$created_at"}},
                ]},
                3600 * 1000,
            ]},
        }},
        {"$group": {"_id": None, "avg": {"$avg": "$duration_hours"}}},
    ]
    cursor = db.svc_cases.aggregate(pipeline)
    avg_resolve_h = None
    async for d in cursor:
        avg_resolve_h = round(float(d.get("avg") or 0), 1)

    # Skill gap: how many open cases have a recommended engineer but no
    # exact skill match (heuristic — recommended_engineer_score ≤ 50 implies
    # AI couldn't find a great match, often skill-mismatch driven).
    skill_gap_count = await db.svc_cases.count_documents({
        **of, "status": {"$in": list(OPEN_STATES)},
        "assigned_engineer_id": {"$in": [None, ""]},
        "recommended_engineer_score": {"$lte": 50, "$gt": 0},
    })

    return {
        "kpis": {
            "open": open_count,
            "unassigned": unassigned_count,
            "sla_at_risk": sla_at_risk,
            "sla_breached": sla_breached,
            "first_time_fix_pct": ftf_pct,
            "closed_last_30d": closed_30,
            "avg_resolve_hours": avg_resolve_h,
            "skill_gap": skill_gap_count,
        },
        "as_of": now,
    }


@router.get("/queue")
async def desk_queue(
    sort: str = Query("sla", description="sla | newest | priority"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Pre-sorted open queue, default = SLA at risk first."""
    _of(user)
    of = await desk_filter(user)
    sort_spec = [("sla_resolve_at", 1), ("created_at", -1)]
    if sort == "newest":
        sort_spec = [("created_at", -1)]
    elif sort == "priority":
        sort_spec = [("priority", 1), ("sla_resolve_at", 1)]
    rows = (
        await db.svc_cases
        .find({**of, "status": {"$in": list(OPEN_STATES)}}, {"_id": 0})
        .sort(sort_spec)
        .limit(limit)
        .to_list(limit)
    )
    return {"cases": rows, "count": len(rows)}


async def _operator_org(user: dict) -> str:
    return (user.get("organization_id") or user.get("service_org_id")) or "__none__"


async def _authorized_customer_org(user: dict, org_id: str) -> bool:
    """A customer org is reachable from the operator's Service Desk if it's
    the operator's own org OR a CRM-linked customer of the operator."""
    operator = await _operator_org(user)
    if not org_id or org_id == operator:
        return True
    link = await db.crm2_companies.find_one(
        {"organization_id": operator, "linked_organization_id": org_id}, {"_id": 0, "id": 1},
    )
    return bool(link)


@router.get("/customers")
async def desk_customers(user=Depends(get_current_user)):
    """Customers selectable when logging a case: the operator's own org
    plus every CRM-linked customer estate (imported via Master Admin)."""
    operator = await _operator_org(user)
    out = []
    seen = set()
    op_org = await db.organizations.find_one({"id": operator}, {"_id": 0, "id": 1, "name": 1})
    if op_org:
        sc = await db.sites.count_documents({"organization_id": operator, "archived": {"$ne": True}})
        out.append({"organization_id": operator, "name": op_org.get("name") or "My organisation",
                    "is_operator": True, "site_count": sc})
        seen.add(operator)
    cursor = db.crm2_companies.find(
        {"organization_id": operator, "linked_organization_id": {"$nin": [None, ""]}},
        {"_id": 0, "name": 1, "linked_organization_id": 1, "account_number": 1},
    ).sort("name", 1)
    async for c in cursor:
        oid = c.get("linked_organization_id")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        sc = await db.sites.count_documents({"organization_id": oid, "archived": {"$ne": True}})
        out.append({"organization_id": oid, "name": c.get("name") or "Customer",
                    "account_number": c.get("account_number") or "", "is_operator": False,
                    "site_count": sc})
    return {"customers": out, "count": len(out)}


@router.get("/customer-sites")
async def desk_customer_sites(organization_id: str = Query(...), user=Depends(get_current_user)):
    """Sites (with equipment counts) for a chosen customer org."""
    if not await _authorized_customer_org(user, organization_id):
        return {"sites": [], "count": 0}
    sites = await db.sites.find(
        {"organization_id": organization_id, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("name", 1).to_list(1000)
    counts: dict[str, int] = {}
    async for d in db.equipment.aggregate([
        {"$match": {"organization_id": organization_id}},
        {"$group": {"_id": "$site_id", "n": {"$sum": 1}}},
    ]):
        if d.get("_id"):
            counts[d["_id"]] = d["n"]
    for s in sites:
        s["equipment_count"] = counts.get(s.get("id"), 0)
    return {"sites": sites, "count": len(sites)}


@router.get("/customer-equipment")
async def desk_customer_equipment(
    organization_id: str = Query(...), site_id: str = Query(...), user=Depends(get_current_user),
):
    """Equipment for a chosen customer site (org-scoped, authorized)."""
    if not await _authorized_customer_org(user, organization_id):
        return {"equipment": [], "count": 0}
    rows = await db.equipment.find(
        {"organization_id": organization_id,
         "$or": [{"site_id": site_id}, {"site_id": {"$exists": False}}, {"site_id": None}]},
        {"_id": 0},
    ).sort("name", 1).to_list(2000)
    return {"equipment": rows, "count": len(rows)}


@router.get("/equipment-coverage")
async def desk_equipment_coverage(
    organization_id: str = Query(...), equipment_id: str = Query(...), user=Depends(get_current_user),
):
    """Contract/warranty coverage for a customer's own equipment, so the
    intake form auto-fills cover type even for imported customer estates."""
    if not await _authorized_customer_org(user, organization_id):
        return {"covered": False, "type": "none", "label": "", "crm_coverage": {"has_coverage": False}}
    equipment = await db.equipment.find_one(
        {"id": equipment_id, "organization_id": organization_id}, {"_id": 0},
    )
    if not equipment:
        return {"covered": False, "type": "none", "label": "Equipment not found",
                "crm_coverage": {"has_coverage": False}}
    from routes.equipment import _parse_date_remaining, _determine_coverage
    from utils.coverage import resolve_equipment_coverage
    warranty_active, warranty_days = _parse_date_remaining(equipment.get("warranty_expiry"))
    contract_active, contract_days = _parse_date_remaining(equipment.get("sla_expiry"))
    covered, coverage_type, coverage_label = _determine_coverage(
        warranty_active, warranty_days, contract_active, contract_days,
    )
    cov = await resolve_equipment_coverage(equipment, db)
    return {
        "equipment_id": equipment_id, "equipment_name": equipment.get("name", ""),
        "covered": covered or cov["has_crm_contract"],
        "type": coverage_type, "label": coverage_label,
        "warranty_active": warranty_active, "warranty_days_remaining": warranty_days,
        "warranty_expiry": equipment.get("warranty_expiry"),
        "contract_active": contract_active, "contract_days_remaining": contract_days,
        "sla_contract_ref": equipment.get("sla_contract_ref"), "sla_expiry": equipment.get("sla_expiry"),
        "crm_coverage": {"has_coverage": cov["has_crm_contract"], "best": cov["best"],
                         "all_contracts": cov["all_contracts"]},
    }


@router.get("/engineers")
async def desk_engineers(user=Depends(get_current_user)):
    """Engineer roster with current load (open case count)."""
    of = _of(user)
    # Iter — self-heal duplicate engineer rows (manual + staffing mirror)
    # so "Live engineers" never shows the same person twice.
    try:
        from routes.svc.engineers_admin import dedupe_svc_engineers
        await dedupe_svc_engineers(of["organization_id"])
    except Exception:
        pass
    engineers = await db.svc_engineers.find(of, {"_id": 0}).sort("full_name", 1).to_list(500)

    # Count open cases per engineer in one round-trip.
    pipeline = [
        {"$match": {**of, "status": {"$in": list(OPEN_STATES)}, "assigned_engineer_id": {"$ne": ""}}},
        {"$group": {"_id": "$assigned_engineer_id", "count": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    cursor = db.svc_cases.aggregate(pipeline)
    async for d in cursor:
        counts[d["_id"]] = d["count"]

    # Live status — derived from clock events on each engineer's most-recent
    # open case. travel|on_site → "en route"|"on site". No clock yet =
    # "available" if active, "off duty" if not.
    live_pipeline = [
        {"$match": {
            **of, "status": {"$in": list(OPEN_STATES)},
            "assigned_engineer_id": {"$ne": ""},
        }},
        {"$sort": {"updated_at": -1}},
        {"$group": {
            "_id": "$assigned_engineer_id",
            "case_id": {"$first": "$id"},
            "case_reference": {"$first": "$reference"},
            "case_title": {"$first": "$title"},
            "site_name": {"$first": "$site_name"},
            "clock_state": {"$first": "$clock_state"},
        }},
    ]
    live: dict[str, dict] = {}
    async for d in db.svc_cases.aggregate(live_pipeline):
        live[d["_id"]] = d
    for e in engineers:
        e.pop("_id", None)
        e["open_cases"] = counts.get(e.get("id"), 0)
        ld = live.get(e.get("id"))
        if ld:
            cs = (ld.get("clock_state") or "").lower()
            if cs == "on_site":
                e["live_status"] = "on_site"
            elif cs in ("travel", "en_route"):
                e["live_status"] = "en_route"
            else:
                e["live_status"] = "assigned"
            e["live_case"] = {
                "id": ld.get("case_id"),
                "reference": ld.get("case_reference"),
                "title": ld.get("case_title"),
                "site_name": ld.get("site_name"),
            }
        else:
            e["live_status"] = "available" if e.get("active") is not False else "off_duty"
            e["live_case"] = None
    return {"engineers": engineers, "count": len(engineers)}
