"""
GymAxis Service Operations — Reports & Audit dashboards.

Iter 215du (Phase 7).

Five aggregation endpoints for the operations console:

  GET /api/svc/reports/summary              high-level KPIs
  GET /api/svc/reports/revenue-by-engineer  invoiced revenue attributed to engineers via quote labour lines
  GET /api/svc/reports/ftfr                 first-time-fix rate (closed without paused_parts state)
  GET /api/svc/reports/sla                  SLA compliance % + breach buckets
  GET /api/svc/reports/ai                   svc_ai_calls observability (calls / ok-rate / p50 / p95 by kind)
  GET /api/svc/reports/audit                paginated timeline events filtered by user/date/type

All endpoints accept `from` / `to` ISO dates and respect `organization_id`.
Numbers are computed via Mongo aggregation pipelines so they scale.
"""
__integration_fields__ = {
    # All endpoints in this module are read-only aggregates over
    # svc_cases / svc_quotes / svc_time_entries / svc_part_movements /
    # svc_ai_calls / svc_case_events. No new collections, no writes —
    # every underlying field is mapped in cases.py / billing.py /
    # engineer.py / parts.py / ai.py manifests already.
    "summary.cases.opened":       "gymaxis_only: aggregate count over svc_cases",
    "summary.cases.closed":       "gymaxis_only: aggregate count over svc_cases",
    "summary.cases.in_progress":  "gymaxis_only: aggregate count over svc_cases",
    "summary.revenue.invoiced":   "sage: SLInvoice rollup (read-through) · GymAxis dashboard",
    "revenue_by_engineer.engineer_id":   "sage: Employee.Reference (read-through) · gymaxis_only attribution math",
    "revenue_by_engineer.invoiced":      "sage: SLInvoiceLine.LineTotalNetAmount filtered to labour lines · GymAxis dashboard",
    "ftfr.first_time_fix_pct":    "gymaxis_only: closed-without-paused_parts metric",
    "sla.compliance_pct":         "sicon: SLAComplianceRate (computed locally; not pushed) · gymaxis_only",
    "sla.breach_buckets":         "gymaxis_only: dashboard breakdown",
    "ai.calls":                   "gymaxis_only: svc_ai_calls rollup",
    "ai.ok_rate":                 "gymaxis_only: svc_ai_calls success rate",
    "ai.p50_ms":                  "gymaxis_only: svc_ai_calls latency p50",
    "ai.p95_ms":                  "gymaxis_only: svc_ai_calls latency p95",
    "audit.events":               "gymaxis_only: paginated svc_case_events (each event is mapped in cases.py)",
}

from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/reports", tags=["Service Ops · Reports"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _window(from_iso: str | None, to_iso: str | None, default_days: int = 30) -> tuple[str, str]:
    """Return ISO timestamp window. Defaults to last N days."""
    if not to_iso:
        to_dt = datetime.now(timezone.utc)
    else:
        to_dt = datetime.fromisoformat(to_iso)
    if not from_iso:
        from_dt = to_dt - timedelta(days=default_days)
    else:
        from_dt = datetime.fromisoformat(from_iso)
    if from_dt > to_dt:
        raise HTTPException(400, "from must be before to")
    return from_dt.isoformat(), to_dt.isoformat()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return float(s[k])


# ─────────────────────────────────────────────────────────────────
# Summary KPIs
# ─────────────────────────────────────────────────────────────────

@router.get("/summary")
async def summary(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_iso, to_iso = _window(from_, to)
    closed_q = {**of, "closed_at": {"$gte": from_iso, "$lte": to_iso}}
    open_q = {**of, "status": {"$nin": ["closed", "invoiced", "rejected"]}}
    cases_closed = await db.svc_cases.count_documents(closed_q)
    open_cases = await db.svc_cases.count_documents(open_q)
    chargeable_invoiced = await db.svc_cases.count_documents({
        **of, "cover_type": "chargeable", "status": "invoiced",
        "closed_at": {"$gte": from_iso, "$lte": to_iso},
    })
    # Revenue from invoiced quotes whose case closed in window.
    pipeline = [
        {"$match": {**of, "status": "invoiced",
                    "invoiced_at": {"$gte": from_iso, "$lte": to_iso}}},
        {"$group": {"_id": None, "gross": {"$sum": {"$ifNull": ["$gross", "$total"]}},
                    "net": {"$sum": "$net"}}},
    ]
    rev = 0.0
    net = 0.0
    async for r in db.svc_quotes.aggregate(pipeline):
        rev = float(r.get("gross") or 0)
        net = float(r.get("net") or 0)
    # AI spend proxy — count of AI calls in window (cost mapped client-side).
    ai_calls = await db.svc_ai_calls.count_documents({**of, "at": {"$gte": from_iso, "$lte": to_iso}})
    return {
        "from": from_iso,
        "to": to_iso,
        "kpis": {
            "open_cases": open_cases,
            "cases_closed": cases_closed,
            "chargeable_invoiced": chargeable_invoiced,
            "revenue_gross": round(rev, 2),
            "revenue_net": round(net, 2),
            "ai_calls": ai_calls,
        },
    }


# ─────────────────────────────────────────────────────────────────
# Revenue by engineer — labour lines on invoiced quotes
# ─────────────────────────────────────────────────────────────────

@router.get("/revenue-by-engineer")
async def revenue_by_engineer(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_iso, to_iso = _window(from_, to, default_days=90)
    pipeline = [
        {"$match": {**of, "status": "invoiced",
                    "invoiced_at": {"$gte": from_iso, "$lte": to_iso}}},
        {"$unwind": "$lines"},
        {"$match": {"lines.kind": "labour"}},
        {"$group": {
            "_id": {"engineer_id": "$lines.engineer_id", "engineer_name": "$lines.engineer_name"},
            "hours": {"$sum": "$lines.qty"},
            "revenue": {"$sum": {"$multiply": ["$lines.qty", "$lines.unit_amount"]}},
            "cases": {"$addToSet": "$case_id"},
        }},
        {"$project": {
            "_id": 0,
            "engineer_id": "$_id.engineer_id",
            "engineer_name": "$_id.engineer_name",
            "hours": {"$round": ["$hours", 2]},
            "revenue": {"$round": ["$revenue", 2]},
            "cases": {"$size": "$cases"},
        }},
        {"$sort": {"revenue": -1}},
    ]
    rows = []
    async for r in db.svc_quotes.aggregate(pipeline):
        if not r.get("engineer_id") and not r.get("engineer_name"):
            r["engineer_name"] = "Unattributed"
        rows.append(r)
    return {"from": from_iso, "to": to_iso, "rows": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# First-time-fix rate
# ─────────────────────────────────────────────────────────────────

@router.get("/ftfr")
async def first_time_fix(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    """A case is a first-time fix if it transitioned to closed without
    ever entering paused_parts.
    """
    of = _of(user)
    from_iso, to_iso = _window(from_, to)
    closed = await db.svc_cases.find(
        {**of, "status": {"$in": ["closed", "invoiced"]},
         "closed_at": {"$gte": from_iso, "$lte": to_iso}},
        {"_id": 0, "id": 1},
    ).to_list(5000)
    if not closed:
        return {"from": from_iso, "to": to_iso, "total_closed": 0, "ftf": 0, "rate": 0.0}
    case_ids = [c["id"] for c in closed]
    paused_pipeline = [
        {"$match": {**of, "case_id": {"$in": case_ids}, "type": "state_change",
                    "to_state": "paused_parts"}},
        {"$group": {"_id": "$case_id"}},
    ]
    paused: set[str] = set()
    async for d in db.svc_case_events.aggregate(paused_pipeline):
        paused.add(d["_id"])
    ftf = len(case_ids) - len(paused)
    return {
        "from": from_iso, "to": to_iso,
        "total_closed": len(case_ids),
        "ftf": ftf,
        "rate": round(ftf / len(case_ids), 3),
    }


# ─────────────────────────────────────────────────────────────────
# SLA compliance
# ─────────────────────────────────────────────────────────────────

@router.get("/sla")
async def sla(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_iso, to_iso = _window(from_, to)
    closed = await db.svc_cases.find(
        {**of, "status": {"$in": ["closed", "invoiced"]},
         "closed_at": {"$gte": from_iso, "$lte": to_iso}},
        {"_id": 0, "closed_at": 1, "sla_resolve_at": 1, "priority": 1},
    ).to_list(5000)
    by_priority: dict[str, dict] = {}
    on_time = 0
    breached = 0
    for c in closed:
        if not c.get("sla_resolve_at"):
            continue
        try:
            ok = c["closed_at"] <= c["sla_resolve_at"]
        except Exception:
            continue
        on_time += 1 if ok else 0
        breached += 0 if ok else 1
        bucket = by_priority.setdefault(c.get("priority") or "p3", {"total": 0, "on_time": 0, "breached": 0})
        bucket["total"] += 1
        bucket["on_time"] += 1 if ok else 0
        bucket["breached"] += 0 if ok else 1
    total = on_time + breached
    return {
        "from": from_iso, "to": to_iso,
        "total": total,
        "on_time": on_time,
        "breached": breached,
        "rate": round(on_time / total, 3) if total else 0.0,
        "by_priority": by_priority,
    }


# ─────────────────────────────────────────────────────────────────
# AI observability
# ─────────────────────────────────────────────────────────────────

@router.get("/ai")
async def ai_observability(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_iso, to_iso = _window(from_, to)
    rows = await db.svc_ai_calls.find(
        {**of, "at": {"$gte": from_iso, "$lte": to_iso}},
        {"_id": 0, "kind": 1, "ok": 1, "latency_ms": 1, "prompt_chars": 1, "response_chars": 1},
    ).to_list(10000)
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = r.get("kind") or "unknown"
        b = by_kind.setdefault(k, {"calls": 0, "ok": 0, "latencies": [],
                                    "prompt_chars": 0, "response_chars": 0})
        b["calls"] += 1
        b["ok"] += 1 if r.get("ok") else 0
        if r.get("latency_ms") is not None:
            b["latencies"].append(r["latency_ms"])
        b["prompt_chars"] += int(r.get("prompt_chars") or 0)
        b["response_chars"] += int(r.get("response_chars") or 0)
    out = []
    for kind, b in by_kind.items():
        out.append({
            "kind": kind,
            "calls": b["calls"],
            "ok": b["ok"],
            "ok_rate": round(b["ok"] / b["calls"], 3) if b["calls"] else 0.0,
            "p50_latency_ms": int(_percentile(b["latencies"], 50)),
            "p95_latency_ms": int(_percentile(b["latencies"], 95)),
            "prompt_chars": b["prompt_chars"],
            "response_chars": b["response_chars"],
        })
    out.sort(key=lambda r: -r["calls"])
    total_calls = sum(r["calls"] for r in out)
    total_ok = sum(r["ok"] for r in out)
    return {
        "from": from_iso, "to": to_iso,
        "by_kind": out,
        "totals": {
            "calls": total_calls,
            "ok": total_ok,
            "ok_rate": round(total_ok / total_calls, 3) if total_calls else 0.0,
        },
    }


# ─────────────────────────────────────────────────────────────────
# Audit feed
# ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    types: Optional[str] = Query(None, description="comma-separated event types"),
    case_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    of = _of(user)
    from_iso, to_iso = _window(from_, to, default_days=14)
    q: dict = {**of, "at": {"$gte": from_iso, "$lte": to_iso}}
    if actor_id:
        q["actor_id"] = actor_id
    if case_id:
        q["case_id"] = case_id
    if types:
        wanted = [t.strip() for t in types.split(",") if t.strip()]
        if wanted:
            q["type"] = {"$in": wanted}
    rows = (
        await db.svc_case_events.find(q, {"_id": 0})
        .sort("at", -1).limit(limit).to_list(limit)
    )
    return {"from": from_iso, "to": to_iso, "events": rows, "count": len(rows)}


__all__ = ["router"]
