"""
Owner Analytics — Iter 254.

Single aggregated endpoint behind the Service Desk "Analytics" tab.
Sales-hook dashboard for the self-serve Service Provider package (works
identically for the Pulse / platform desk since everything is org-scoped):

    GET /api/svc/analytics/owner?from=ISO&to=ISO

Returns, for the selected window:
- headline:  cases created/closed/open, avg time-to-respond & resolve (h),
             response + resolve SLA compliance rates
- sla:       per-priority response/resolve compliance
- engineers: per-engineer jobs completed, open workload, hours logged
             (svc_time_entries) and utilisation vs an 8h-weekday capacity
- revenue:   invoiced totals (svc_engineer_invoices, non-void) + invoiced
             quotes (deduped via linked_quote_id), revenue per job
- trend:     weekly buckets — created, closed, SLA on-time %

"Response" = first state_change event after creation (case left `new`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/svc/analytics", tags=["Service Ops · Analytics"])

_MAX_CASES = 5000


def _of(user: dict) -> dict:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _window(from_iso: Optional[str], to_iso: Optional[str]) -> tuple[datetime, datetime]:
    to_dt = datetime.fromisoformat(to_iso) if to_iso else datetime.now(timezone.utc)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=timezone.utc)
    from_dt = datetime.fromisoformat(from_iso) if from_iso else to_dt - timedelta(days=30)
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)
    if from_dt > to_dt:
        raise HTTPException(400, "from must be before to")
    if (to_dt - from_dt).days > 730:
        raise HTTPException(400, "Date range too large (max 2 years)")
    return from_dt, to_dt


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _weekdays(from_dt: datetime, to_dt: datetime) -> int:
    n, d = 0, from_dt.date()
    while d <= to_dt.date():
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return max(1, n)


def _week_start(d: datetime) -> str:
    monday = d.date() - timedelta(days=d.weekday())
    return monday.isoformat()


def _norm_priority(p: str | None) -> str:
    """Live data carries mixed forms ('P2', 'p2', 'medium'). Normalise to p1–p4."""
    v = (p or "").strip().lower()
    if v in ("p1", "p2", "p3", "p4"):
        return v
    return {"critical": "p1", "high": "p2", "medium": "p3", "low": "p4"}.get(v, "p3")


@router.get("/owner")
async def owner_analytics(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_dt, to_dt = _window(from_, to)
    from_iso, to_iso = from_dt.isoformat(), to_dt.isoformat()
    in_window = {"$gte": from_iso, "$lte": to_iso}

    # ── Case sets ────────────────────────────────────────────────
    created = await db.svc_cases.find(
        {**of, "created_at": in_window},
        {"_id": 0, "id": 1, "created_at": 1, "priority": 1, "sla_response_at": 1},
    ).to_list(_MAX_CASES)
    closed = await db.svc_cases.find(
        {**of, "status": {"$in": ["closed", "invoiced"]}, "closed_at": in_window},
        {"_id": 0, "id": 1, "created_at": 1, "closed_at": 1, "priority": 1,
         "sla_resolve_at": 1, "assigned_engineer_id": 1},
    ).to_list(_MAX_CASES)
    open_cases = await db.svc_cases.count_documents(
        {**of, "status": {"$nin": ["closed", "invoiced", "rejected"]}})

    # ── Response times: first state_change after creation ────────
    first_change: dict[str, str] = {}
    if created:
        pipeline = [
            {"$match": {**of, "type": "state_change",
                        "case_id": {"$in": [c["id"] for c in created]}}},
            {"$group": {"_id": "$case_id", "first_at": {"$min": "$at"}}},
        ]
        async for r in db.svc_case_events.aggregate(pipeline):
            first_change[r["_id"]] = r["first_at"]

    resp_hours: list[float] = []
    resp_on_time = resp_total = 0
    sla_by_priority: dict[str, dict] = {
        p: {"response_total": 0, "response_on_time": 0, "resolve_total": 0, "resolve_on_time": 0}
        for p in ("p1", "p2", "p3", "p4")
    }
    for c in created:
        responded_at = _parse(first_change.get(c["id"]))
        created_at = _parse(c.get("created_at"))
        target = _parse(c.get("sla_response_at"))
        if responded_at and created_at:
            resp_hours.append(max(0.0, (responded_at - created_at).total_seconds() / 3600))
        if responded_at and target:
            resp_total += 1
            ok = responded_at <= target
            resp_on_time += 1 if ok else 0
            b = sla_by_priority[_norm_priority(c.get("priority"))]
            b["response_total"] += 1
            b["response_on_time"] += 1 if ok else 0

    # ── Resolve times + resolve SLA ───────────────────────────────
    resolve_hours: list[float] = []
    resolve_on_time = resolve_total = 0
    for c in closed:
        closed_at, created_at = _parse(c.get("closed_at")), _parse(c.get("created_at"))
        target = _parse(c.get("sla_resolve_at"))
        if closed_at and created_at:
            resolve_hours.append(max(0.0, (closed_at - created_at).total_seconds() / 3600))
        if closed_at and target:
            resolve_total += 1
            ok = closed_at <= target
            resolve_on_time += 1 if ok else 0
            b = sla_by_priority[_norm_priority(c.get("priority"))]
            b["resolve_total"] += 1
            b["resolve_on_time"] += 1 if ok else 0

    # ── Engineer utilisation ──────────────────────────────────────
    engineers = await db.svc_engineers.find(
        {**of, "active": True}, {"_id": 0, "id": 1, "full_name": 1},
    ).to_list(200)
    jobs_done: dict[str, int] = {}
    for c in closed:
        eng = c.get("assigned_engineer_id")
        if eng:
            jobs_done[eng] = jobs_done.get(eng, 0) + 1
    workload: dict[str, int] = {}
    async for r in db.svc_cases.aggregate([
        {"$match": {**of, "status": {"$nin": ["closed", "invoiced", "rejected"]},
                    "assigned_engineer_id": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$assigned_engineer_id", "n": {"$sum": 1}}},
    ]):
        workload[r["_id"]] = r["n"]
    hours_logged: dict[str, float] = {}
    async for r in db.svc_time_entries.aggregate([
        {"$match": {**of, "start_at": in_window}},
        {"$group": {"_id": "$engineer_id", "mins": {"$sum": "$duration_minutes"}}},
    ]):
        hours_logged[r["_id"]] = round((r["mins"] or 0) / 60, 1)
    capacity_h = _weekdays(from_dt, to_dt) * 8
    eng_rows = sorted(
        ({
            "engineer_id": e["id"],
            "name": e.get("full_name") or "Engineer",
            "jobs_completed": jobs_done.get(e["id"], 0),
            "open_workload": workload.get(e["id"], 0),
            "hours_logged": hours_logged.get(e["id"], 0.0),
            "capacity_h": capacity_h,
            "utilisation_pct": round(min(1.0, hours_logged.get(e["id"], 0.0) / capacity_h), 3),
        } for e in engineers),
        key=lambda r: (-r["jobs_completed"], -r["hours_logged"]),
    )

    # ── Revenue ───────────────────────────────────────────────────
    inv_total = inv_paid = 0.0
    inv_count = 0
    inv_jobs: set[str] = set()
    linked_quotes: set[str] = set()
    async for inv in db.svc_engineer_invoices.find(
        {**of, "status": {"$ne": "void"}, "created_at": in_window},
        {"_id": 0, "total": 1, "status": 1, "case_id": 1, "linked_quote_id": 1},
    ):
        amt = float(inv.get("total") or 0)
        inv_total += amt
        inv_count += 1
        if inv.get("status") == "paid":
            inv_paid += amt
        if inv.get("case_id"):
            inv_jobs.add(inv["case_id"])
        if inv.get("linked_quote_id"):
            linked_quotes.add(inv["linked_quote_id"])
    quotes_total = 0.0
    async for q in db.svc_quotes.find(
        {**of, "status": "invoiced", "invoiced_at": in_window},
        {"_id": 0, "id": 1, "gross": 1, "total": 1, "case_id": 1},
    ):
        if q.get("id") in linked_quotes:
            continue  # already billed through an engineer invoice
        quotes_total += float(q.get("gross") or q.get("total") or 0)
        if q.get("case_id"):
            inv_jobs.add(q["case_id"])
    revenue_total = round(inv_total + quotes_total, 2)
    jobs_billed = len(inv_jobs)

    # ── Weekly trend ──────────────────────────────────────────────
    weeks: dict[str, dict] = {}
    wk = from_dt
    while wk <= to_dt:
        weeks[_week_start(wk)] = {"created": 0, "closed": 0, "sla_on_time": 0, "sla_total": 0}
        wk += timedelta(days=7)
    def _bucket(ts: str | None):
        d = _parse(ts)
        return weeks.get(_week_start(d)) if d else None
    for c in created:
        b = _bucket(c.get("created_at"))
        if b:
            b["created"] += 1
    for c in closed:
        b = _bucket(c.get("closed_at"))
        if b is None:
            continue
        b["closed"] += 1
        target = _parse(c.get("sla_resolve_at"))
        closed_at = _parse(c.get("closed_at"))
        if target and closed_at:
            b["sla_total"] += 1
            b["sla_on_time"] += 1 if closed_at <= target else 0
    trend = [
        {"week": w, "created": v["created"], "closed": v["closed"],
         "sla_pct": round(v["sla_on_time"] / v["sla_total"], 3) if v["sla_total"] else None}
        for w, v in sorted(weeks.items())
    ]

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    return {
        "from": from_iso,
        "to": to_iso,
        "headline": {
            "cases_created": len(created),
            "cases_closed": len(closed),
            "open_cases": open_cases,
            "avg_response_h": _avg(resp_hours),
            "avg_resolve_h": _avg(resolve_hours),
            "sla_response_rate": round(resp_on_time / resp_total, 3) if resp_total else None,
            "sla_resolve_rate": round(resolve_on_time / resolve_total, 3) if resolve_total else None,
        },
        "sla_by_priority": sla_by_priority,
        "engineers": eng_rows,
        "revenue": {
            "total": revenue_total,
            "invoices_raised": inv_count,
            "paid": round(inv_paid, 2),
            "outstanding": round(inv_total - inv_paid, 2),
            "jobs_billed": jobs_billed,
            "avg_per_job": round(revenue_total / jobs_billed, 2) if jobs_billed else 0.0,
        },
        "trend": trend,
    }


__all__ = ["router"]
