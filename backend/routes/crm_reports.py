"""CRM · Reports suite (Iter 216h226).

Aggregated read-only analytics endpoints for the new CRM Reports panel.
Every report returns plain JSON with a compact `{rows: [...], totals: {...}, generated_at}`
shape so a single client component can render them as either a table
or a chart.

Reports shipped:
  GET /crm/reports/pipeline-by-stage       count + value by opp stage
  GET /crm/reports/pipeline-by-territory   count + value by territory
  GET /crm/reports/quote-conversion        win-rate, accepted/created/lost
  GET /crm/reports/margin                  margin distribution + outliers
  GET /crm/reports/lost-reasons            why we lose deals
  GET /crm/reports/salesperson             per-owner deal/quote/value totals
  GET /crm/reports/consent-overview        GDPR comm consent breakdown

All endpoints are org-scoped via `get_crm_user`. Date filters use
`from_iso` + `to_iso` query params (default = last 90 days for time-
series reports).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from utils.database import db
from routes.crm_auth import get_crm_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/reports", tags=["CRM Reports"])


# ── Helpers ────────────────────────────────────────────────────────


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_range(from_iso: str | None, to_iso: str | None, days_default: int = 90) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_default)
    if from_iso:
        try:
            start = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
        except Exception:
            pass
    if to_iso:
        try:
            end = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
        except Exception:
            pass
    return start.isoformat(), end.isoformat()


def _envelope(rows: list[dict], totals: dict | None = None, **extra) -> dict:
    return {
        "rows": rows,
        "totals": totals or {},
        "generated_at": _now_iso(),
        **extra,
    }


# ── 1. Pipeline by stage ───────────────────────────────────────────


@router.get("/pipeline-by-stage")
async def pipeline_by_stage(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """Count + total value of open opportunities grouped by stage.
    Excludes closed_won / closed_lost so the view focuses on what's
    actually still in play.

    Honours `from_iso` / `to_iso` against `created_at` so admins can
    inspect pipeline composition at a specific point in time.
    """
    start, end = _date_range(from_iso, to_iso)
    match: dict[str, Any] = {**_of(user), "stage": {"$nin": ["closed_won", "closed_lost"]}}
    if from_iso or to_iso:
        match["created_at"] = {"$gte": start, "$lte": end}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$stage",
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$value", 0]}},
        }},
        {"$project": {"_id": 0, "stage": "$_id", "count": 1, "value": 1}},
        {"$sort": {"stage": 1}},
    ]
    rows = await db.crm2_opportunities.aggregate(pipeline).to_list(50)
    totals = {
        "count": sum(r.get("count", 0) for r in rows),
        "value": round(sum(r.get("value", 0) for r in rows), 2),
        "from": start, "to": end,
    }
    return _envelope(rows, totals)


# ── 2. Pipeline by territory ───────────────────────────────────────


@router.get("/pipeline-by-territory")
async def pipeline_by_territory(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """Open opportunity count + value broken down by `territory_id`.
    Joined to the territory directory so the row carries the human
    name (or "Unassigned" when null).
    """
    start, end = _date_range(from_iso, to_iso)
    match: dict[str, Any] = {**_of(user), "stage": {"$nin": ["closed_won", "closed_lost"]}}
    if from_iso or to_iso:
        match["created_at"] = {"$gte": start, "$lte": end}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$ifNull": ["$territory_id", "__unassigned__"]},
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$value", 0]}},
        }},
        {"$project": {"_id": 0, "territory_id": "$_id", "count": 1, "value": 1}},
        {"$sort": {"value": -1}},
    ]
    rows = await db.crm2_opportunities.aggregate(pipeline).to_list(100)

    # Hydrate territory names.
    terr_ids = [r["territory_id"] for r in rows if r["territory_id"] != "__unassigned__"]
    names = {
        t["id"]: t["name"]
        for t in await db.crm_territories.find(
            {"id": {"$in": terr_ids}, **_of(user)}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(200)
    }
    for r in rows:
        r["territory_name"] = (
            "Unassigned" if r["territory_id"] == "__unassigned__"
            else names.get(r["territory_id"], "Unknown")
        )
    totals = {
        "count": sum(r.get("count", 0) for r in rows),
        "value": round(sum(r.get("value", 0) for r in rows), 2),
        "territories": len([r for r in rows if r["territory_id"] != "__unassigned__"]),
        "from": start, "to": end,
    }
    return _envelope(rows, totals)


# ── 3. Quote conversion ────────────────────────────────────────────


@router.get("/quote-conversion")
async def quote_conversion(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """How many quotes did we send, accept, and lose in the period?
    Pre-216h222 quotes used various status spellings; we normalise to
    sent / accepted / lost / draft / expired / cancelled.
    """
    start, end = _date_range(from_iso, to_iso)
    base_q = {
        "$or": [
            {"organization_id": user.get("organization_id")},
            {"organization_id": {"$exists": False}},
        ],
        "created_at": {"$gte": start, "$lte": end},
    }
    by_status_pipeline = [
        {"$match": base_q},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$total", 0]}},
        }},
        {"$project": {"_id": 0, "status": "$_id", "count": 1, "value": 1}},
    ]
    rows = await db.crm_quotes.aggregate(by_status_pipeline).to_list(50)
    by_status: dict[str, dict] = {r["status"]: r for r in rows}

    created = sum(r.get("count", 0) for r in rows)
    accepted = by_status.get("accepted", {}).get("count", 0)
    sent = by_status.get("sent", {}).get("count", 0)
    lost = by_status.get("lost", {}).get("count", 0)
    accepted_value = by_status.get("accepted", {}).get("value", 0)
    total_value = sum(r.get("value", 0) for r in rows)
    win_rate = round((accepted / created) * 100, 1) if created > 0 else 0.0

    totals = {
        "created": created,
        "sent": sent,
        "accepted": accepted,
        "lost": lost,
        "win_rate_percent": win_rate,
        "accepted_value": round(accepted_value, 2),
        "total_value": round(total_value, 2),
        "from": start,
        "to": end,
    }
    return _envelope(rows, totals)


# ── 4. Margin analysis ─────────────────────────────────────────────


@router.get("/margin")
async def margin_analysis(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """Distribution + outliers of gross margin % across the org's
    quotes. Includes a "leaking margin" list — quotes pending approval
    older than 48h.

    `from_iso` / `to_iso` filter on the quote's `created_at`.
    """
    start, end = _date_range(from_iso, to_iso)
    org_q = {
        "$or": [
            {"organization_id": user.get("organization_id")},
            {"organization_id": {"$exists": False}},
        ],
    }
    quote_match: dict[str, Any] = {**org_q, "gross_margin_percent": {"$exists": True}}
    if from_iso or to_iso:
        quote_match["created_at"] = {"$gte": start, "$lte": end}
    cursor = db.crm_quotes.find(
        quote_match,
        {"_id": 0, "id": 1, "quote_number": 1, "title": 1, "gross_margin_percent": 1, "total": 1, "status": 1, "company_name": 1, "created_by_name": 1, "updated_at": 1, "approval_status": 1, "created_at": 1},
    ).sort("gross_margin_percent", -1).limit(500)
    rows = await cursor.to_list(500)
    if not rows:
        return _envelope([], {"avg_margin_percent": 0, "median_margin_percent": 0, "count": 0, "leaking": [], "from": start, "to": end})

    margins = sorted([r.get("gross_margin_percent", 0) or 0 for r in rows])
    avg = round(sum(margins) / len(margins), 2)
    median = margins[len(margins) // 2]
    # Distribution buckets (0-10, 11-20, 21-30, 31-50, 51+).
    buckets = {"0-10": 0, "11-20": 0, "21-30": 0, "31-50": 0, "51+": 0}
    for m in margins:
        if m <= 10:
            buckets["0-10"] += 1
        elif m <= 20:
            buckets["11-20"] += 1
        elif m <= 30:
            buckets["21-30"] += 1
        elif m <= 50:
            buckets["31-50"] += 1
        else:
            buckets["51+"] += 1
    distribution = [{"bucket": k, "count": v} for k, v in buckets.items()]

    # Top 5 / bottom 5 by margin.
    sorted_rows = sorted(rows, key=lambda r: r.get("gross_margin_percent", 0), reverse=True)
    top = sorted_rows[:5]
    bottom = sorted([r for r in rows if r.get("gross_margin_percent", 0) > 0], key=lambda r: r["gross_margin_percent"])[:5]

    # Leaking — pending_approval > 48h.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    leaking = [
        r for r in rows
        if r.get("approval_status") == "pending"
        and (r.get("created_at") or "") < cutoff
    ]

    return _envelope(distribution, {
        "avg_margin_percent": avg,
        "median_margin_percent": round(median, 2),
        "count": len(rows),
        "top": top,
        "bottom": bottom,
        "leaking": leaking[:10],
        "from": start, "to": end,
    })


# ── 5. Lost reasons ────────────────────────────────────────────────


@router.get("/lost-reasons")
async def lost_reasons(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """Top reasons we lose deals + dollar value lost per reason."""
    start, end = _date_range(from_iso, to_iso)
    match: dict[str, Any] = {**_of(user), "stage": "closed_lost"}
    if from_iso or to_iso:
        match["closed_at"] = {"$gte": start, "$lte": end}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$ifNull": ["$lost_reason", "(no reason)"]},
            "count": {"$sum": 1},
            "value": {"$sum": {"$ifNull": ["$value", 0]}},
        }},
        {"$project": {"_id": 0, "reason": "$_id", "count": 1, "value": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    rows = await db.crm2_opportunities.aggregate(pipeline).to_list(50)
    totals = {
        "deals_lost": sum(r["count"] for r in rows),
        "value_lost": round(sum(r["value"] for r in rows), 2),
        "from": start, "to": end,
    }
    return _envelope(rows, totals)


# ── 6. Salesperson performance ─────────────────────────────────────


@router.get("/salesperson")
async def salesperson_performance(
    from_iso: str | None = None,
    to_iso: str | None = None,
    user=Depends(get_crm_user),
) -> dict:
    """Per-owner deal + quote performance for the period. Computes
    open / won / lost / total-value / avg-margin-% per sales person.
    """
    start, end = _date_range(from_iso, to_iso)

    opp_pipeline = [
        {"$match": {**_of(user), "created_at": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": {"$ifNull": ["$owner_id", "__unassigned__"]},
            "owner_name": {"$first": "$owner_name"},
            "total_opps": {"$sum": 1},
            "won_opps": {"$sum": {"$cond": [{"$eq": ["$stage", "closed_won"]}, 1, 0]}},
            "lost_opps": {"$sum": {"$cond": [{"$eq": ["$stage", "closed_lost"]}, 1, 0]}},
            "open_value": {
                "$sum": {
                    "$cond": [
                        {"$not": {"$in": ["$stage", ["closed_won", "closed_lost"]]}},
                        {"$ifNull": ["$value", 0]}, 0,
                    ]
                }
            },
            "won_value": {
                "$sum": {
                    "$cond": [
                        {"$eq": ["$stage", "closed_won"]},
                        {"$ifNull": ["$value", 0]}, 0,
                    ]
                }
            },
        }},
        {"$project": {
            "_id": 0,
            "owner_id": "$_id",
            "owner_name": 1,
            "total_opps": 1,
            "won_opps": 1,
            "lost_opps": 1,
            "open_value": 1,
            "won_value": 1,
        }},
        {"$sort": {"won_value": -1}},
    ]
    rows = await db.crm2_opportunities.aggregate(opp_pipeline).to_list(100)

    # Compute win-rate per row.
    for r in rows:
        closed = r.get("won_opps", 0) + r.get("lost_opps", 0)
        r["win_rate"] = round((r["won_opps"] / closed) * 100, 1) if closed else 0.0
        r["owner_name"] = r.get("owner_name") or ("Unassigned" if r["owner_id"] == "__unassigned__" else r["owner_id"])

    totals = {
        "total_opps": sum(r["total_opps"] for r in rows),
        "total_won": sum(r["won_opps"] for r in rows),
        "total_lost": sum(r["lost_opps"] for r in rows),
        "open_value": round(sum(r["open_value"] for r in rows), 2),
        "won_value": round(sum(r["won_value"] for r in rows), 2),
        "from": start,
        "to": end,
    }
    return _envelope(rows, totals)


# ── 7. Consent overview ────────────────────────────────────────────


@router.get("/consent-overview")
async def consent_overview(user=Depends(get_crm_user)) -> dict:
    """GDPR communication consent breakdown across all contacts in
    the org. One row per channel showing opted-in / opted-out counts.
    """
    base = {**_of(user)}
    channels = ["email", "sms", "phone", "post", "marketing"]
    rows = []
    for ch in channels:
        field = f"opt_out_{ch}"
        opted_out = await db.crm2_contacts.count_documents({**base, field: True})
        total = await db.crm2_contacts.count_documents(base)
        opted_in = total - opted_out
        rows.append({
            "channel": ch,
            "opted_in": opted_in,
            "opted_out": opted_out,
            "opt_in_rate": round((opted_in / total) * 100, 1) if total else 0.0,
        })

    consenting_total = await db.crm2_contacts.count_documents({**base, "gdpr_consent": True})
    total_contacts = await db.crm2_contacts.count_documents(base)
    return _envelope(rows, {
        "total_contacts": total_contacts,
        "with_recorded_consent": consenting_total,
        "consent_rate_percent": round((consenting_total / total_contacts) * 100, 1) if total_contacts else 0.0,
    })


# ── Catalogue (drives the FE sidebar) ──────────────────────────────


@router.get("")
async def list_reports(user=Depends(get_crm_user)) -> dict:
    return {
        "reports": [
            {"id": "pipeline-by-stage",     "label": "Pipeline by Stage",     "category": "Pipeline"},
            {"id": "pipeline-by-territory", "label": "Pipeline by Territory", "category": "Pipeline"},
            {"id": "quote-conversion",      "label": "Quote Conversion",      "category": "Sales"},
            {"id": "margin",                "label": "Margin Analysis",       "category": "Sales"},
            {"id": "lost-reasons",          "label": "Lost Reasons",          "category": "Sales"},
            {"id": "salesperson",           "label": "Salesperson Performance","category": "Team"},
            {"id": "consent-overview",      "label": "GDPR Consent",          "category": "Compliance"},
        ],
    }



# ── Pre-Install Site Survey reports (Iter 2026-07) ──────────────────
from utils.site_scope import effective_site_filter  # noqa: E402
from routes.crm_site_surveys_schema import SURVEY_STATUSES, READINESS_STATUSES  # noqa: E402

_SURVEYS = "pre_install_site_surveys"
_STATUS_LABEL = {s["key"]: s["label"] for s in SURVEY_STATUSES}
_READY_LABEL = {s["key"]: s["label"] for s in READINESS_STATUSES}
_INSTALLED_STATUSES = {"approved_for_installation", "completed"}


def _survey_of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id"), **effective_site_filter()}


def _survey_high_risk(doc: dict):
    """Return the worst risk severity ('critical'/'high') or None."""
    worst = None
    for r in ((doc.get("data") or {}).get("risks") or []):
        lvl = (r.get("risk_level") or r.get("severity") or "").lower()
        if lvl == "critical":
            return "critical"
        if lvl == "high":
            worst = "high"
    return worst


async def _load_surveys(user, from_iso, to_iso, dated=True):
    q = {**_survey_of(user), "is_current": True}
    if dated:
        start, end = _date_range(from_iso, to_iso, 365)
        q["created_at"] = {"$gte": start, "$lte": end}
        rng = {"from": start, "to": end}
    else:
        rng = {}
    docs = await db[_SURVEYS].find(q, {"_id": 0}).to_list(5000)
    return docs, rng


@router.get("/site-surveys-status")
async def rpt_surveys_status(from_iso: str = None, to_iso: str = None, user=Depends(get_crm_user)):
    docs, rng = await _load_surveys(user, from_iso, to_iso)
    counts = {}
    for d in docs:
        counts[d.get("status")] = counts.get(d.get("status"), 0) + 1
    rows = [{"status": _STATUS_LABEL.get(k, k), "count": v}
            for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    open_count = sum(v for k, v in counts.items() if k not in {"completed", "archived", "superseded"})
    return {"rows": rows,
            "totals": {"total_surveys": len(docs), "open": open_count,
                       "awaiting_customer_info": counts.get("awaiting_customer_information", 0),
                       **rng},
            "generated_at": _now_iso()}


@router.get("/site-surveys-manager")
async def rpt_surveys_manager(from_iso: str = None, to_iso: str = None, user=Depends(get_crm_user)):
    docs, rng = await _load_surveys(user, from_iso, to_iso)
    by = {}
    for d in docs:
        m = d.get("completed_by_name") or "Unassigned"
        row = by.setdefault(m, {"manager": m, "surveys": 0, "ready_for_install": 0, "installed": 0, "high_risk": 0})
        row["surveys"] += 1
        if d.get("readiness_status") in ("ready_for_installation", "installation_approved"):
            row["ready_for_install"] += 1
        if d.get("status") in _INSTALLED_STATUSES:
            row["installed"] += 1
        if _survey_high_risk(d):
            row["high_risk"] += 1
    rows = sorted(by.values(), key=lambda r: -r["surveys"])
    return {"rows": rows, "totals": {"managers": len(rows), "total_surveys": len(docs), **rng},
            "generated_at": _now_iso()}


@router.get("/site-surveys-high-risk")
async def rpt_surveys_high_risk(from_iso: str = None, to_iso: str = None, user=Depends(get_crm_user)):
    docs, rng = await _load_surveys(user, from_iso, to_iso)
    rows = []
    crit = 0
    for d in docs:
        sev = _survey_high_risk(d)
        if not sev:
            continue
        if sev == "critical":
            crit += 1
        risks = (d.get("data") or {}).get("risks") or []
        rows.append({
            "reference": d.get("reference"),
            "company": d.get("company_name"),
            "site": d.get("site_name") or "—",
            "top_severity": sev.capitalize(),
            "open_risks": len(risks),
            "status": _STATUS_LABEL.get(d.get("status"), d.get("status")),
            "target_install_date": (d.get("target_install_date") or "—"),
        })
    rows.sort(key=lambda r: (r["top_severity"] != "Critical", r["reference"]))
    return {"rows": rows, "totals": {"high_risk_surveys": len(rows), "critical": crit, **rng},
            "generated_at": _now_iso()}


@router.get("/site-surveys-conversion")
async def rpt_surveys_conversion(from_iso: str = None, to_iso: str = None, user=Depends(get_crm_user)):
    docs, rng = await _load_surveys(user, from_iso, to_iso)
    total = len(docs)
    approved_quote = sum(1 for d in docs if d.get("status") in
                         {"approved_for_quote", "approved_for_installation", "completed"})
    approved_install = sum(1 for d in docs if d.get("status") in _INSTALLED_STATUSES)
    completed = sum(1 for d in docs if d.get("status") == "completed")
    pct = lambda n: (round(n / total * 100, 1) if total else 0.0)  # noqa: E731
    rows = [
        {"stage": "Surveys created", "count": total, "conversion_%": 100.0 if total else 0.0},
        {"stage": "Approved for quote+", "count": approved_quote, "conversion_%": pct(approved_quote)},
        {"stage": "Approved for installation", "count": approved_install, "conversion_%": pct(approved_install)},
        {"stage": "Completed", "count": completed, "conversion_%": pct(completed)},
    ]
    return {"rows": rows,
            "totals": {"total_surveys": total, "converted_to_install": approved_install,
                       "survey_to_install_rate_%": pct(approved_install), **rng},
            "generated_at": _now_iso()}


# ── Excel / PDF export for ALL CRM reports ──────────────────────────
import inspect  # noqa: E402

_EXPORTABLE_REPORTS = {
    "pipeline-by-stage": ("Pipeline by Stage", pipeline_by_stage),
    "pipeline-by-territory": ("Pipeline by Territory", pipeline_by_territory),
    "quote-conversion": ("Quote Conversion", quote_conversion),
    "margin": ("Margin Analysis", margin_analysis),
    "lost-reasons": ("Lost Reasons", lost_reasons),
    "salesperson": ("Salesperson Performance", salesperson_performance),
    "consent-overview": ("GDPR Consent Overview", consent_overview),
    "site-surveys-status": ("Surveys by Status", rpt_surveys_status),
    "site-surveys-manager": ("Surveys by Manager", rpt_surveys_manager),
    "site-surveys-high-risk": ("High-Risk Installations", rpt_surveys_high_risk),
    "site-surveys-conversion": ("Survey → Install Conversion", rpt_surveys_conversion),
}


@router.get("/{report_id}/export")
async def export_report(report_id: str, fmt: str = "xlsx", from_iso: str = None,
                        to_iso: str = None, user=Depends(get_crm_user)):
    entry = _EXPORTABLE_REPORTS.get(report_id)
    if not entry:
        raise HTTPException(404, "This report does not support Excel/PDF export")
    title, fn = entry
    # Only pass date params the target report actually accepts.
    params = inspect.signature(fn).parameters
    kwargs = {"user": user}
    if "from_iso" in params:
        kwargs["from_iso"] = from_iso
    if "to_iso" in params:
        kwargs["to_iso"] = to_iso
    result = await fn(**kwargs)
    rows = result.get("rows") or []
    totals = result.get("totals") or {}
    if fmt == "pdf":
        from utils.report_export import build_report_pdf
        data = build_report_pdf(title, rows, totals)
        mt, ext = "application/pdf", "pdf"
    else:
        from utils.report_export import build_report_xlsx
        data = build_report_xlsx(title, rows, totals)
        mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    fname = f"{report_id}.{ext}"
    return Response(content=data, media_type=mt,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
