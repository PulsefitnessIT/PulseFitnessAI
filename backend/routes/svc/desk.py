"""
GymAxis Service Operations — Service Desk Dashboard API.

Iter 215dn (Phase 1).

Read-only aggregates powering the desk dashboard: KPI strip, queue,
filters meta. Designed to be cheap on a 500-case cold cache; uses
count_documents + a single sorted slice rather than aggregation
pipelines so it's fast even at scale.
"""
__integration_fields__ = {
    # All endpoints in this module are read-only aggregates over
    # `svc_cases` + `svc_case_events`. No new collections, no writes.
    # The aggregated outputs are GymAxis-internal dashboard data — every
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
from utils.auth import get_current_user
from utils.svc_state import OPEN_STATES, CLOSED, INVOICED, SLA_RISK_WINDOW_HOURS

router = APIRouter(prefix="/svc/desk", tags=["Service Ops · Desk"])


def _of(user: dict) -> dict:
    return {"organization_id": (user.get("organization_id") or user.get("service_org_id")) or "__none__"}


@router.get("/summary")
async def desk_summary(user=Depends(get_current_user)):
    """KPI strip + queue snapshot for the dashboard header."""
    of = _of(user)
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
    of = _of(user)
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


@router.get("/engineers")
async def desk_engineers(user=Depends(get_current_user)):
    """Engineer roster with current load (open case count)."""
    of = _of(user)
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
