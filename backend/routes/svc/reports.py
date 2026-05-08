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
import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response

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


@router.get("/downtime")
async def downtime(
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Asset/site downtime hours: for every closed (or invoiced) case in the
    window, sum (closed_at − created_at) per asset and per site. Active
    (open) cases get their open-time-so-far included so the chart reflects
    real-world impact, not just billed completions.
    """
    of = _of(user)
    horizon_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    pipeline = [
        {"$match": {**of, "created_at": {"$gte": horizon_iso}}},
        {"$project": {
            "asset_name": 1,
            "asset_id": 1,
            "site_name": 1,
            "site_id": 1,
            "status": 1,
            "case_type": 1,
            "duration_hours": {
                "$divide": [
                    {"$subtract": [
                        {"$dateFromString": {"dateString": {"$ifNull": ["$closed_at", now_iso]}}},
                        {"$dateFromString": {"dateString": "$created_at"}},
                    ]},
                    3600 * 1000,
                ],
            },
        }},
    ]
    rows = []
    async for d in db.svc_cases.aggregate(pipeline):
        d.pop("_id", None)
        rows.append(d)

    by_asset: dict[str, dict] = {}
    by_site: dict[str, dict] = {}
    total_hours = 0.0
    for r in rows:
        h = max(0.0, float(r.get("duration_hours") or 0))
        total_hours += h
        akey = (r.get("asset_id") or r.get("asset_name") or "Unknown asset")
        a = by_asset.setdefault(akey, {
            "asset_id": r.get("asset_id", ""),
            "asset_name": r.get("asset_name") or "Unknown asset",
            "case_count": 0, "downtime_hours": 0.0,
        })
        a["case_count"] += 1
        a["downtime_hours"] = round(a["downtime_hours"] + h, 1)
        skey = (r.get("site_id") or r.get("site_name") or "Unknown site")
        s = by_site.setdefault(skey, {
            "site_id": r.get("site_id", ""),
            "site_name": r.get("site_name") or "Unknown site",
            "case_count": 0, "downtime_hours": 0.0,
        })
        s["case_count"] += 1
        s["downtime_hours"] = round(s["downtime_hours"] + h, 1)

    top_assets = sorted(by_asset.values(), key=lambda r: r["downtime_hours"], reverse=True)[:10]
    top_sites = sorted(by_site.values(), key=lambda r: r["downtime_hours"], reverse=True)[:10]
    return {
        "window_days": days,
        "total_hours": round(total_hours, 1),
        "case_count": len(rows),
        "top_assets": top_assets,
        "top_sites": top_sites,
    }


__all__ = ["router"]


# ─────────────────────────────────────────────────────────────────
# Phase 6+ — CSV / PDF exports & helpers
# ─────────────────────────────────────────────────────────────────

_EXPORTABLE_TYPES = {"revenue", "ftfr", "sla", "ai", "downtime", "summary"}


def _csv_response(filename: str, rows: list[list], headers: list[str]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.csv")
async def export_csv(
    type: str = Query("revenue"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """One-click CSV export for any report section."""
    kind = (type or "").lower()
    if kind not in _EXPORTABLE_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(_EXPORTABLE_TYPES)}")
    # Org guard — exports are gated on tenant scope just like the underlying reports.
    _of(user)

    if kind == "revenue":
        data = await revenue_by_engineer(from_, to, user)
        rows = [[r.get("engineer_name", ""), r.get("engineer_id", ""),
                 r.get("hours", 0), r.get("revenue", 0), r.get("cases", 0)]
                for r in data["rows"]]
        return _csv_response(f"revenue-by-engineer_{kind}.csv", rows,
                             ["Engineer", "Engineer ID", "Hours", "Revenue (gross)", "Cases"])

    if kind == "ftfr":
        data = await first_time_fix(from_, to, user)
        return _csv_response("ftfr.csv",
                             [[data["from"], data["to"], data["total_closed"], data["ftf"], data["rate"]]],
                             ["From", "To", "Total closed", "First-time fix", "Rate"])

    if kind == "sla":
        data = await sla(from_, to, user)
        rows = [["__overall__", data["total"], data["on_time"], data["breached"], data["rate"]]]
        for prio, b in (data.get("by_priority") or {}).items():
            rate = round(b["on_time"] / b["total"], 3) if b.get("total") else 0.0
            rows.append([prio, b["total"], b["on_time"], b["breached"], rate])
        return _csv_response("sla-compliance.csv", rows,
                             ["Priority", "Total", "On time", "Breached", "Rate"])

    if kind == "ai":
        data = await ai_observability(from_, to, user)
        rows = [[r["kind"], r["calls"], r["ok"], r["ok_rate"], r["p50_latency_ms"], r["p95_latency_ms"],
                 r["prompt_chars"], r["response_chars"]] for r in data["by_kind"]]
        return _csv_response("ai-observability.csv", rows,
                             ["Kind", "Calls", "OK", "OK rate", "p50 ms", "p95 ms",
                              "Prompt chars", "Response chars"])

    if kind == "downtime":
        data = await downtime(days, user)
        rows = [["asset", r.get("asset_name", ""), r.get("asset_id", ""),
                 r.get("case_count", 0), r.get("downtime_hours", 0)] for r in data["top_assets"]]
        rows += [["site", r.get("site_name", ""), r.get("site_id", ""),
                  r.get("case_count", 0), r.get("downtime_hours", 0)] for r in data["top_sites"]]
        return _csv_response("downtime.csv", rows,
                             ["Scope", "Name", "ID", "Cases", "Downtime hours"])

    # Summary
    data = await summary(from_, to, user)
    k = data["kpis"]
    rows = [[data["from"], data["to"], k.get("open_cases"), k.get("cases_closed"),
             k.get("chargeable_invoiced"), k.get("revenue_gross"), k.get("revenue_net"),
             k.get("ai_calls")]]
    return _csv_response("summary.csv", rows,
                         ["From", "To", "Open cases", "Closed", "Chargeable invoiced",
                          "Revenue gross", "Revenue net", "AI calls"])


@router.get("/export.pdf")
async def export_pdf(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Branded multi-section PDF — the same view operations sees on screen,
    rendered for sharing with execs / customers.
    """
    of = _of(user)
    summary_d = await summary(from_, to, user)
    revenue_d = await revenue_by_engineer(from_, to, user)
    ftfr_d = await first_time_fix(from_, to, user)
    sla_d = await sla(from_, to, user)
    downtime_d = await downtime(days, user)
    org = await db.organizations.find_one({"id": of["organization_id"]}, {"_id": 0, "name": 1})
    org_name = (org or {}).get("name") or "GymAxis"

    # Render with reportlab — already used elsewhere in the codebase.
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Service ops report — {org_name}",
    )
    styles = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#1d4ed8"), spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], textColor=colors.HexColor("#1e293b"))
    eyebrow = ParagraphStyle("eyebrow", parent=body, textColor=colors.HexColor("#64748b"),
                              fontSize=9, leading=11, spaceAfter=2)

    flow = []
    flow.append(Paragraph(f"{org_name} — Service Operations report", H1))
    flow.append(Paragraph(
        f"Window: {summary_d['from'][:10]} → {summary_d['to'][:10]} · Generated {datetime.now(timezone.utc).isoformat(timespec='minutes')}",
        eyebrow,
    ))
    flow.append(Spacer(1, 6))

    # KPIs
    k = summary_d["kpis"]
    kpi_table = Table([
        ["Open cases", "Closed", "Chargeable invoiced", "Revenue (gross)", "AI calls", "Downtime"],
        [str(k.get("open_cases", 0)), str(k.get("cases_closed", 0)),
         str(k.get("chargeable_invoiced", 0)),
         f"£{float(k.get('revenue_gross') or 0):,.0f}",
         str(k.get("ai_calls", 0)),
         f"{downtime_d.get('total_hours', 0):,}h"],
    ], colWidths=[28 * mm] * 6)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(kpi_table)

    # FTFR + SLA gauges
    flow.append(Paragraph("Quality & SLA", H2))
    flow.append(Paragraph(
        f"<b>First-time-fix:</b> {round((ftfr_d.get('rate') or 0) * 100)}% "
        f"({ftfr_d.get('ftf', 0)} of {ftfr_d.get('total_closed', 0)} closed) &nbsp; "
        f"<b>SLA compliance:</b> {round((sla_d.get('rate') or 0) * 100)}% "
        f"({sla_d.get('on_time', 0)} on-time / {sla_d.get('breached', 0)} breached)",
        body,
    ))
    if sla_d.get("by_priority"):
        sla_rows = [["Priority", "Total", "On time", "Breached", "Rate"]]
        for prio, b in sla_d["by_priority"].items():
            rate = round((b["on_time"] / b["total"]) * 100) if b.get("total") else 0
            sla_rows.append([prio.upper(), b["total"], b["on_time"], b["breached"], f"{rate}%"])
        sla_table = Table(sla_rows, colWidths=[24 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm])
        sla_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        flow.append(Spacer(1, 4))
        flow.append(sla_table)

    # Revenue per engineer
    flow.append(Paragraph("Revenue per engineer", H2))
    if not revenue_d.get("rows"):
        flow.append(Paragraph("<i>No invoiced labour in this window.</i>", body))
    else:
        rev_rows = [["Engineer", "Hours", "Cases", "Revenue (gross)"]]
        for r in revenue_d["rows"][:25]:
            rev_rows.append([r.get("engineer_name", "—"),
                             f"{r.get('hours', 0):.1f}",
                             str(r.get("cases", 0)),
                             f"£{float(r.get('revenue') or 0):,.2f}"])
        rev_table = Table(rev_rows, colWidths=[60 * mm, 24 * mm, 24 * mm, 32 * mm])
        rev_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        flow.append(rev_table)

    # Downtime
    flow.append(PageBreak())
    flow.append(Paragraph("Downtime — top assets", H2))
    flow.append(Paragraph(
        f"<b>Total fleet downtime:</b> {downtime_d.get('total_hours', 0):,}h "
        f"across {downtime_d.get('case_count', 0)} cases ({downtime_d.get('window_days', 30)}-day window).",
        body,
    ))
    if downtime_d.get("top_assets"):
        rows = [["Asset", "Cases", "Downtime (h)"]]
        for r in downtime_d["top_assets"][:15]:
            rows.append([r.get("asset_name", "—"), str(r.get("case_count", 0)),
                         f"{r.get('downtime_hours', 0):,.1f}"])
        t = Table(rows, colWidths=[100 * mm, 24 * mm, 32 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        flow.append(Spacer(1, 4))
        flow.append(t)

    flow.append(Paragraph("Downtime — top sites", H2))
    if downtime_d.get("top_sites"):
        rows = [["Site", "Cases", "Downtime (h)"]]
        for r in downtime_d["top_sites"][:15]:
            rows.append([r.get("site_name", "—"), str(r.get("case_count", 0)),
                         f"{r.get('downtime_hours', 0):,.1f}"])
        t = Table(rows, colWidths=[100 * mm, 24 * mm, 32 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        flow.append(Spacer(1, 4))
        flow.append(t)

    flow.append(Spacer(1, 12))
    flow.append(Paragraph(
        "<i>Generated by GymAxis Service Operations · figures are live from the operational database.</i>",
        eyebrow,
    ))

    doc.build(flow)
    pdf_bytes = buf.getvalue()
    buf.close()
    safe_org = "".join(c for c in org_name if c.isalnum() or c in "_-").lower() or "report"
    filename = f"svc-ops-report-{safe_org}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────
# Phase 6+ — Email digest settings (per-org)
# ─────────────────────────────────────────────────────────────────

@router.get("/digest/settings")
async def digest_settings_get(user=Depends(get_current_user)):
    """Read the org's digest cadence + recipient list."""
    of = _of(user)
    org = await db.organizations.find_one(
        {"id": of["organization_id"]},
        {"_id": 0, "svc_digest_enabled": 1, "svc_digest_cadence": 1,
         "svc_digest_recipients": 1, "svc_digest_last_sent_at": 1},
    ) or {}
    return {
        "enabled": bool(org.get("svc_digest_enabled", False)),
        "cadence": org.get("svc_digest_cadence", "weekly"),
        "recipients": org.get("svc_digest_recipients") or [],
        "last_sent_at": org.get("svc_digest_last_sent_at"),
    }


@router.put("/digest/settings")
async def digest_settings_put(data: dict, user=Depends(get_current_user)):
    of = _of(user)
    cadence = ((data or {}).get("cadence") or "weekly").lower()
    if cadence not in ("daily", "weekly"):
        raise HTTPException(400, "cadence must be daily | weekly")
    raw_recipients = (data or {}).get("recipients") or []
    if isinstance(raw_recipients, str):
        raw_recipients = [r.strip() for r in raw_recipients.split(",")]
    recipients = sorted({r.strip().lower() for r in raw_recipients
                         if r and "@" in r})[:20]
    enabled = bool((data or {}).get("enabled"))
    if enabled and not recipients:
        raise HTTPException(400, "At least one recipient is required when enabling the digest")
    await db.organizations.update_one(
        {"id": of["organization_id"]},
        {"$set": {
            "svc_digest_enabled": enabled,
            "svc_digest_cadence": cadence,
            "svc_digest_recipients": recipients,
            "svc_digest_updated_at": _now_iso(),
            "svc_digest_updated_by_id": user["id"],
        }},
    )
    return await digest_settings_get(user)


@router.post("/digest/send-test")
async def digest_send_test(user=Depends(get_current_user)):
    """Render and send the digest immediately to whatever recipient list is
    configured. Useful for the `Send test` button on the settings UI.
    """
    of = _of(user)
    from utils.svc_digest import send_digest_for_org  # local import — avoids cycle
    sent = await send_digest_for_org(of["organization_id"], force=True)
    return {"ok": True, "sent": sent}

