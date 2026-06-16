"""Pulse Fitness Memberships — Reporting & Analytics Engine.

All read-only aggregation endpoints powering the operator Analytics tab.
Scoped by `organization_id` via the operator JWT so multi-tenant isolation
is automatic. Heavy aggregations are cached in-process for 60s.

Covers:
  • Overview / Revenue / Member growth / Forecast (Phase 1)
  • Retention & churn, cohort matrix, engagement segmentation (Phase 2)
  • Class performance, instructor scorecards, heatmap, ops (Phase 3)
  • Multi-site comparison, alerts, AI brief, at-risk, CRM push,
    CSV/PDF export (Phase 4)
"""
from __future__ import annotations

import csv
import io
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.safe_paginate import safe_to_list, BULK_CAP
from utils.memberships_ai_insights import (
    generate_executive_brief,
    rank_at_risk_members,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-analytics"])

# ═════════════════════ helpers ═════════════════════

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_S = 60.0


def _ck(*parts: str) -> str:
    return "|".join(parts)


def _cache_get(key: str) -> Any | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, val = hit
    if time.time() - ts > _CACHE_TTL_S:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_set(key: str, val: Any) -> None:
    _CACHE[key] = (time.time(), val)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _daterange(from_: str | None, to: str | None, default_days: int = 90) -> tuple[datetime, datetime]:
    now = _now()
    end = _parse_iso(to) or now
    start = _parse_iso(from_) or (end - timedelta(days=default_days))
    return start, end


def _bucket_label(dt: datetime, period: str) -> str:
    if period == "daily":
        return dt.strftime("%Y-%m-%d")
    if period == "weekly":
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return dt.strftime("%Y-%m")


def _pct(num: float, den: float) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def _pence_to_gbp(p: int | float) -> float:
    return round((p or 0) / 100.0, 2)


# ═════════════════════ Overview + Revenue + Forecast (Phase 1) ═════════════════════


@router.get("/memberships/analytics/overview")
async def analytics_overview(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    site_id: str | None = None,
    period: Literal["daily", "weekly", "monthly"] = "monthly",
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to)
    cache_key = _ck("overview", org_id, site_id or "", period, start.isoformat(), end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    member_q: dict = {"organization_id": org_id}
    mm_q: dict = {"organization_id": org_id}
    booking_q: dict = {"organization_id": org_id}
    pay_q: dict = {"organization_id": org_id}
    if site_id:
        booking_q["site_id"] = site_id
        mm_q["site_id"] = site_id

    # -- KPI cards
    active_members = await db.members.count_documents({**member_q, "status": "active"})
    new_members = await db.members.count_documents({**member_q, "created_at": {"$gte": _iso(start), "$lte": _iso(end)}})
    cancellations = await db.member_memberships.count_documents(
        {**mm_q, "status": "cancelled", "cancel_effective_date": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    frozen = await db.member_memberships.count_documents({**mm_q, "status": "frozen"})
    net_growth = new_members - cancellations

    # -- Revenue rollup
    paid_rows = await safe_to_list(
        db.payment_transactions.find(
            {**pay_q, "payment_status": "paid", "created_at": {"$gte": _iso(start), "$lte": _iso(end)}},
            {"_id": 0, "amount_pence": 1, "created_at": 1, "plan_id": 1, "method": 1, "mode": 1},
        ),
        cap=BULK_CAP,
        name="memberships_analytics.paid_rows",
    )
    revenue_pence = sum(int(r.get("amount_pence") or 0) for r in paid_rows)
    revenue_gbp = _pence_to_gbp(revenue_pence)
    failed_rows = await db.payment_transactions.count_documents(
        {**pay_q, "payment_status": "failed", "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    recovered_rows = await db.payment_transactions.count_documents(
        {**pay_q, "payment_status": "paid", "recovered_from": {"$exists": True},
         "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )

    # -- MRR (active recurring memberships × monthly equivalent)
    active_mms = await safe_to_list(
        db.member_memberships.find(
            {**mm_q, "status": {"$in": ["active", "frozen"]}},
            {"_id": 0, "plan_id": 1},
        ),
        cap=BULK_CAP,
        name="memberships_analytics.active_mms",
    )
    plan_ids = list({m["plan_id"] for m in active_mms if m.get("plan_id")})
    plans = {p["id"]: p for p in await db.membership_plans.find(
        {"id": {"$in": plan_ids}}, {"_id": 0}).to_list(len(plan_ids) or 1)}
    mrr_pence = 0
    for m in active_mms:
        p = plans.get(m.get("plan_id"))
        if not p:
            continue
        price = int(p.get("price_pence") or 0)
        if p.get("billing_cycle") == "annual":
            mrr_pence += price // 12
        elif p.get("kind") == "recurring":
            mrr_pence += price
        # class_pack/fixed_term do not count toward MRR
    mrr_gbp = _pence_to_gbp(mrr_pence)
    arpu_gbp = round(mrr_gbp / active_members, 2) if active_members else 0.0

    # -- Trend buckets (new members vs cancellations vs revenue)
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"new": 0, "churn": 0, "revenue": 0.0})
    async for m in db.members.find(member_q, {"_id": 0, "created_at": 1}):
        dt = _parse_iso(m.get("created_at"))
        if dt and start <= dt <= end:
            buckets[_bucket_label(dt, period)]["new"] += 1
    async for mm in db.member_memberships.find({**mm_q, "status": "cancelled"}, {"_id": 0, "cancel_effective_date": 1}):
        dt = _parse_iso(mm.get("cancel_effective_date"))
        if dt and start <= dt <= end:
            buckets[_bucket_label(dt, period)]["churn"] += 1
    for r in paid_rows:
        dt = _parse_iso(r.get("created_at"))
        if dt:
            buckets[_bucket_label(dt, period)]["revenue"] += _pence_to_gbp(int(r.get("amount_pence") or 0))
    trend = [{"bucket": k, **v} for k, v in sorted(buckets.items())]

    # -- Revenue by product (plan kind)
    by_product: dict[str, float] = defaultdict(float)
    for r in paid_rows:
        p = plans.get(r.get("plan_id")) if r.get("plan_id") else None
        kind = (p.get("kind") if p else None) or "other"
        by_product[kind] += _pence_to_gbp(int(r.get("amount_pence") or 0))
    revenue_by_product = [{"product": k, "revenue_gbp": round(v, 2)} for k, v in sorted(by_product.items(), key=lambda x: -x[1])]

    # -- Membership mix (by plan name)
    mix_counter: Counter = Counter()
    for m in active_mms:
        p = plans.get(m.get("plan_id"))
        if p:
            mix_counter[p.get("name") or "Unknown"] += 1
    membership_mix = [{"plan": k, "count": v} for k, v in mix_counter.most_common()]

    # -- Churn %
    denom_churn = active_members + cancellations
    churn_pct = _pct(cancellations, denom_churn)

    # -- Occupancy (range)
    occ_rows = await db.class_occurrences.find(
        {"organization_id": org_id, "starts_at": {"$gte": _iso(start), "$lte": _iso(end)}},
        {"_id": 0, "capacity": 1, "bookings_count": 1, "attended_count": 1, "no_show_count": 1, "status": 1},
    ).to_list(5000)
    cap_sum = sum(int(o.get("capacity") or 0) for o in occ_rows) or 1
    book_sum = sum(int(o.get("bookings_count") or 0) for o in occ_rows)
    att_sum = sum(int(o.get("attended_count") or 0) for o in occ_rows)
    ns_sum = sum(int(o.get("no_show_count") or 0) for o in occ_rows)
    occ_pct = _pct(book_sum, cap_sum)
    no_show_pct = _pct(ns_sum, att_sum + ns_sum)

    # -- Revenue forecast (linear extrapolation + 7% seasonality + ±stdev bands)
    rev_series = [b["revenue"] for b in trend if b.get("revenue", 0)]
    forecast: list[dict[str, Any]] = []
    if len(rev_series) >= 2:
        last = rev_series[-1]
        avg_delta = (rev_series[-1] - rev_series[0]) / max(len(rev_series) - 1, 1)
        # Standard deviation of historical revenue for confidence bands
        mean_rev = sum(rev_series) / len(rev_series)
        variance = sum((x - mean_rev) ** 2 for x in rev_series) / len(rev_series)
        stdev = variance ** 0.5
        for i in range(1, 4):
            proj = max(0.0, (last + avg_delta * i) * 1.07)
            band = stdev * (1 + 0.2 * i)  # wider band further out
            forecast.append({
                "bucket": f"+{i}{period[0]}",
                "revenue_gbp": round(proj, 2),
                "lower_gbp": round(max(0.0, proj - band), 2),
                "upper_gbp": round(proj + band, 2),
            })

    payload = {
        "period": period,
        "range": {"from": _iso(start), "to": _iso(end)},
        "kpis": {
            "active_members": active_members,
            "new_members": new_members,
            "cancellations": cancellations,
            "net_growth": net_growth,
            "frozen": frozen,
            "churn_pct": churn_pct,
            "mrr_gbp": mrr_gbp,
            "arpu_gbp": arpu_gbp,
            "revenue_gbp": revenue_gbp,
            "failed_payments": failed_rows,
            "recovered_payments": recovered_rows,
            "occupancy_pct": occ_pct,
            "no_show_pct": no_show_pct,
            "total_bookings": book_sum,
            "attended": att_sum,
        },
        "trend": trend,
        "revenue_forecast": forecast,
        "revenue_by_product": revenue_by_product,
        "membership_mix": membership_mix,
    }
    _cache_set(cache_key, payload)
    return payload


# ═════════════════════ Retention, cohorts, segmentation (Phase 2) ═════════════════════


@router.get("/memberships/analytics/retention")
async def analytics_retention(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to, default_days=180)
    cache_key = _ck("retention", org_id, site_id or "", start.isoformat(), end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    member_q: dict = {"organization_id": org_id}
    if site_id:
        member_q["site_id"] = site_id

    members = await db.members.find(member_q, {"_id": 0, "password": 0}).to_list(20000)
    member_ids = [m["id"] for m in members]

    mms = await db.member_memberships.find(
        {"organization_id": org_id, "member_id": {"$in": member_ids}},
        {"_id": 0},
    ).to_list(20000)

    # -- Churn by plan + by site + early churn
    churn_by_plan: Counter = Counter()
    churn_by_site: Counter = Counter()
    lifespans: list[int] = []
    early_churn_30 = 0
    early_churn_60 = 0
    for mm in mms:
        if mm.get("status") != "cancelled":
            continue
        churn_by_plan[mm.get("plan_id") or "unknown"] += 1
        churn_by_site[mm.get("site_id") or "default"] += 1
        joined = _parse_iso(mm.get("joined_at"))
        cancelled = _parse_iso(mm.get("cancel_effective_date"))
        if joined and cancelled:
            days = (cancelled - joined).days
            lifespans.append(days)
            if days <= 30:
                early_churn_30 += 1
            if days <= 60:
                early_churn_60 += 1

    avg_lifespan = round(sum(lifespans) / len(lifespans), 1) if lifespans else 0.0

    # -- Resolve plan + site names for churn rollups
    plan_names = {p["id"]: p.get("name") or "Plan"
                  for p in await db.membership_plans.find(
                      {"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1}
                  ).to_list(500)}
    churn_by_plan_out = [{"plan": plan_names.get(k, k), "count": v} for k, v in churn_by_plan.most_common()]
    churn_by_site_out = [{"site": k, "count": v} for k, v in churn_by_site.most_common()]

    # -- Retention cohort matrix: join-month × months-since-join retained %
    cohort: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    cohort_size: Counter = Counter()
    for m in members:
        joined = _parse_iso(m.get("created_at"))
        if not joined:
            continue
        c_key = joined.strftime("%Y-%m")
        cohort_size[c_key] += 1
        # For each subsequent month, is the member still active?
        active_mm = next((x for x in mms if x.get("member_id") == m["id"] and x.get("status") in {"active", "frozen"}), None)
        cancelled_mm = next((x for x in mms if x.get("member_id") == m["id"] and x.get("status") == "cancelled"), None)
        # Cancelled date → defines retention drop
        drop_date = _parse_iso(cancelled_mm.get("cancel_effective_date")) if cancelled_mm and not active_mm else None
        for i in range(0, 7):  # months 0..6
            bucket_dt = (joined.replace(day=1) + timedelta(days=30 * i))
            if bucket_dt > _now():
                break
            still = True
            if drop_date and bucket_dt >= drop_date:
                still = False
            if still:
                cohort[c_key][i] += 1
    cohort_matrix = []
    for key in sorted(cohort.keys()):
        size = cohort_size[key] or 1
        cohort_matrix.append({
            "cohort": key,
            "size": cohort_size[key],
            "retention": [
                {"month": i, "pct": _pct(cohort[key].get(i, 0), size)}
                for i in range(0, 7)
            ],
        })

    # -- Engagement segmentation (RFM-style)
    # Count bookings/visits per member in last 60 days
    visit_floor = _now() - timedelta(days=60)
    visits_count: Counter = Counter()
    async for cin in db.member_checkins.find(
        {"organization_id": org_id, "at": {"$gte": _iso(visit_floor)}},
        {"_id": 0, "member_id": 1},
    ):
        visits_count[cin["member_id"]] += 1
    # Complement with bookings-attended so members w/o QR check-ins still count
    async for b in db.bookings.find(
        {"organization_id": org_id, "status": "attended", "booked_at": {"$gte": _iso(visit_floor)}},
        {"_id": 0, "member_id": 1},
    ):
        visits_count[b["member_id"]] = max(visits_count.get(b["member_id"], 0), 0) + 1

    segments = {"highly_engaged": 0, "regular": 0, "at_risk": 0, "inactive": 0}
    segment_members: dict[str, list[dict]] = {k: [] for k in segments}
    for m in members:
        if m.get("status") == "cancelled":
            continue
        v = visits_count.get(m["id"], 0)
        if v >= 12:
            bucket = "highly_engaged"
        elif v >= 4:
            bucket = "regular"
        elif v >= 1:
            bucket = "at_risk"
        else:
            bucket = "inactive"
        segments[bucket] += 1
        if len(segment_members[bucket]) < 50:
            segment_members[bucket].append({
                "id": m["id"],
                "name": f"{m.get('first_name','')} {m.get('last_name','')}".strip(),
                "email": m.get("email"),
                "visits_60d": v,
                "lifetime_value_gbp": _pence_to_gbp(int(m.get("lifetime_value_pence") or 0)),
            })

    payload = {
        "range": {"from": _iso(start), "to": _iso(end)},
        "kpis": {
            "churn_total": sum(churn_by_plan.values()),
            "avg_lifespan_days": avg_lifespan,
            "early_churn_30d": early_churn_30,
            "early_churn_60d": early_churn_60,
        },
        "churn_by_plan": churn_by_plan_out,
        "churn_by_site": churn_by_site_out,
        "cohort_matrix": cohort_matrix,
        "segments": segments,
        "segment_members": segment_members,
    }
    _cache_set(cache_key, payload)
    return payload


# ═════════════════════ Class + Instructor performance (Phase 3) ═════════════════════


@router.get("/memberships/analytics/classes")
async def analytics_classes(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to, default_days=60)
    cache_key = _ck("classes", org_id, site_id or "", start.isoformat(), end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    q: dict = {"organization_id": org_id, "starts_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    if site_id:
        q["site_id"] = site_id
    occs = await db.class_occurrences.find(q, {"_id": 0}).to_list(5000)

    # -- By template: fill speed, popularity, attendance, no-show
    tpl_stats: dict[str, dict] = defaultdict(lambda: {
        "name": "", "sessions": 0, "capacity": 0, "booked": 0,
        "attended": 0, "no_show": 0, "waitlist": 0, "cancelled_class": 0,
    })
    instr_stats: dict[str, dict] = defaultdict(lambda: {
        "name": "", "sessions": 0, "capacity": 0, "booked": 0,
        "attended": 0, "no_show": 0, "cancelled_class": 0, "unique_members": set(),
        "user_id": "",
    })
    heatmap: dict[str, int] = defaultdict(int)  # "DOW|HH" -> booked count

    for o in occs:
        tid = o.get("template_id") or "none"
        t = tpl_stats[tid]
        t["name"] = o.get("name") or t["name"]
        t["sessions"] += 1
        t["capacity"] += int(o.get("capacity") or 0)
        t["booked"] += int(o.get("bookings_count") or 0)
        t["attended"] += int(o.get("attended_count") or 0)
        t["no_show"] += int(o.get("no_show_count") or 0)
        t["waitlist"] += int(o.get("waitlist_count") or 0)
        if o.get("status") == "cancelled":
            t["cancelled_class"] += 1

        iid = o.get("instructor_user_id") or "unassigned"
        s = instr_stats[iid]
        s["name"] = o.get("instructor_name") or s["name"] or "Unassigned"
        s["user_id"] = iid
        s["sessions"] += 1
        s["capacity"] += int(o.get("capacity") or 0)
        s["booked"] += int(o.get("bookings_count") or 0)
        s["attended"] += int(o.get("attended_count") or 0)
        s["no_show"] += int(o.get("no_show_count") or 0)
        if o.get("status") == "cancelled":
            s["cancelled_class"] += 1

        dt = _parse_iso(o.get("starts_at"))
        if dt:
            heatmap[f"{dt.weekday()}|{dt.hour:02d}"] += int(o.get("bookings_count") or 0)

    # -- unique members per instructor (for retention signal)
    occ_ids_by_instr: dict[str, list[str]] = defaultdict(list)
    for o in occs:
        occ_ids_by_instr[o.get("instructor_user_id") or "unassigned"].append(o.get("id"))
    for iid, occ_ids in occ_ids_by_instr.items():
        if not occ_ids:
            continue
        uniq = await db.bookings.distinct("member_id", {"occurrence_id": {"$in": occ_ids}, "status": {"$in": ["attended", "booked"]}})
        instr_stats[iid]["unique_members"] = set(uniq)

    # -- Waitlist conversion (promoted → booked)
    promoted_count = await db.bookings.count_documents(
        {"organization_id": org_id, "promoted_from_waitlist_at": {"$exists": True},
         "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    waitlist_total = sum(t["waitlist"] for t in tpl_stats.values())
    waitlist_conv = _pct(promoted_count, waitlist_total)

    # Late-cancel + no-show rates
    late_cancels = await db.bookings.count_documents(
        {"organization_id": org_id, "status": "late_cancel",
         "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )

    def _tpl_row(tid: str, t: dict) -> dict:
        occ = t["sessions"] or 1
        return {
            "template_id": tid,
            "name": t["name"] or "Class",
            "sessions": t["sessions"],
            "capacity": t["capacity"],
            "booked": t["booked"],
            "attended": t["attended"],
            "no_show": t["no_show"],
            "waitlist": t["waitlist"],
            "cancelled": t["cancelled_class"],
            "occupancy_pct": _pct(t["booked"], t["capacity"]),
            "no_show_pct": _pct(t["no_show"], t["attended"] + t["no_show"]),
            "avg_bookings_per_session": round(t["booked"] / occ, 1),
        }

    classes = [_tpl_row(k, v) for k, v in tpl_stats.items()]
    classes.sort(key=lambda r: r["occupancy_pct"], reverse=True)

    # -- Rate pence + payout for instructors
    user_ids = [iid for iid in instr_stats if iid != "unassigned"]
    users_info = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": user_ids}}, {"_id": 0}).to_list(len(user_ids) or 1)}
    tpl_rates = {}
    async for tpl in db.class_templates.find(
        {"organization_id": org_id, "instructor_rate_pence": {"$exists": True}},
        {"_id": 0, "id": 1, "instructor_rate_pence": 1, "instructor_user_id": 1}):
        if tpl.get("instructor_user_id"):
            tpl_rates[tpl["instructor_user_id"]] = int(tpl.get("instructor_rate_pence") or 0)

    instructors = []
    for iid, s in instr_stats.items():
        u = users_info.get(iid) if iid != "unassigned" else None
        rate = tpl_rates.get(iid, int((u or {}).get("instructor_rate_pence") or 0))
        # Retention impact = unique attending members / sessions taught
        retention_impact = round(len(s["unique_members"]) / max(s["sessions"], 1), 2)
        instructors.append({
            "user_id": iid,
            "name": s["name"],
            "sessions": s["sessions"],
            "attended": s["attended"],
            "no_show": s["no_show"],
            "occupancy_pct": _pct(s["booked"], s["capacity"]),
            "no_show_pct": _pct(s["no_show"], s["attended"] + s["no_show"]),
            "cancelled": s["cancelled_class"],
            "unique_members": len(s["unique_members"]),
            "retention_impact": retention_impact,
            "payout_gbp": _pence_to_gbp(rate * s["attended"]) if rate else 0.0,
            "rate_gbp": _pence_to_gbp(rate) if rate else 0.0,
        })
    instructors.sort(key=lambda r: (-r["retention_impact"], -r["occupancy_pct"]))

    # Heatmap (7x24)
    heatmap_grid = [
        [heatmap.get(f"{d}|{h:02d}", 0) for h in range(24)]
        for d in range(7)
    ]

    payload = {
        "range": {"from": _iso(start), "to": _iso(end)},
        "kpis": {
            "total_sessions": sum(t["sessions"] for t in tpl_stats.values()),
            "avg_occupancy_pct": _pct(
                sum(t["booked"] for t in tpl_stats.values()),
                sum(t["capacity"] for t in tpl_stats.values()),
            ),
            "no_show_pct": _pct(
                sum(t["no_show"] for t in tpl_stats.values()),
                sum(t["attended"] for t in tpl_stats.values())
                + sum(t["no_show"] for t in tpl_stats.values()),
            ),
            "waitlist_conversion_pct": waitlist_conv,
            "late_cancels": late_cancels,
        },
        "classes_ranked": classes,
        "underperforming": [c for c in classes if c["occupancy_pct"] < 40.0][-10:],
        "top_performing": [c for c in classes if c["occupancy_pct"] >= 70.0][:10],
        "instructors": instructors,
        "heatmap": heatmap_grid,
    }
    _cache_set(cache_key, payload)
    return payload


# ═════════════════════ Operations + Site comparison + Alerts (Phase 4) ═════════════════════


@router.get("/memberships/analytics/operations")
async def analytics_operations(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to, default_days=30)
    cache_key = _ck("ops", org_id, start.isoformat(), end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    # -- Booking conversion (book attempts → booked not waitlisted)
    total_bookings = await db.bookings.count_documents(
        {"organization_id": org_id, "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    waitlisted = await db.bookings.count_documents(
        {"organization_id": org_id, "status": "waitlist",
         "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    booked_direct = await db.bookings.count_documents(
        {"organization_id": org_id, "status": {"$in": ["booked", "attended", "no_show", "late_cancel"]},
         "promoted_from_waitlist_at": {"$exists": False},
         "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )

    # -- Payment success & refund rate
    paid_count = await db.payment_transactions.count_documents(
        {"organization_id": org_id, "payment_status": "paid",
         "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    failed_count = await db.payment_transactions.count_documents(
        {"organization_id": org_id, "payment_status": "failed",
         "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    refund_count = await db.payment_transactions.count_documents(
        {"organization_id": org_id, "status": "refunded",
         "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    )
    pay_total = paid_count + failed_count + refund_count
    payment_success_pct = _pct(paid_count, pay_total)
    refund_pct = _pct(refund_count, paid_count + refund_count)

    # -- Fill speed (avg hours-to-full for classes that hit capacity)
    fill_samples = []
    async for o in db.class_occurrences.find(
        {"organization_id": org_id, "starts_at": {"$gte": _iso(start), "$lte": _iso(end)}},
        {"_id": 0, "id": 1, "capacity": 1, "bookings_count": 1, "starts_at": 1, "created_at": 1},
    ):
        cap = int(o.get("capacity") or 0)
        if cap <= 0 or int(o.get("bookings_count") or 0) < cap:
            continue
        starts = _parse_iso(o.get("starts_at"))
        # last booking that filled it
        last = await db.bookings.find_one(
            {"occurrence_id": o["id"], "status": {"$in": ["booked", "attended"]}},
            {"_id": 0, "booked_at": 1},
            sort=[("booked_at", -1)],
        )
        last_dt = _parse_iso((last or {}).get("booked_at"))
        if starts and last_dt:
            hours_to_full = max(0.0, (starts - last_dt).total_seconds() / 3600.0)
            fill_samples.append(hours_to_full)
    avg_fill_hours = round(sum(fill_samples) / len(fill_samples), 1) if fill_samples else 0.0

    # -- Site comparison (orgs may have multiple site_ids on bookings/members)
    sites_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "active_members": 0, "revenue_gbp": 0.0, "bookings": 0, "attended": 0,
        "no_show": 0, "churn": 0,
    })
    async for m in db.members.find({"organization_id": org_id}, {"_id": 0, "site_id": 1, "status": 1}):
        sid = m.get("site_id") or "default"
        if m.get("status") == "active":
            sites_agg[sid]["active_members"] += 1
    async for r in db.payment_transactions.find(
        {"organization_id": org_id, "payment_status": "paid",
         "created_at": {"$gte": _iso(start), "$lte": _iso(end)}},
        {"_id": 0, "amount_pence": 1, "member_id": 1}):
        mem = await db.members.find_one({"id": r.get("member_id")}, {"_id": 0, "site_id": 1})
        sid = (mem or {}).get("site_id") or "default"
        sites_agg[sid]["revenue_gbp"] += _pence_to_gbp(int(r.get("amount_pence") or 0))
    async for b in db.bookings.find(
        {"organization_id": org_id, "booked_at": {"$gte": _iso(start), "$lte": _iso(end)}},
        {"_id": 0, "site_id": 1, "status": 1}):
        sid = b.get("site_id") or "default"
        sites_agg[sid]["bookings"] += 1
        if b.get("status") == "attended":
            sites_agg[sid]["attended"] += 1
        if b.get("status") == "no_show":
            sites_agg[sid]["no_show"] += 1
    async for mm in db.member_memberships.find(
        {"organization_id": org_id, "status": "cancelled",
         "cancel_effective_date": {"$gte": _iso(start), "$lte": _iso(end)}},
        {"_id": 0, "site_id": 1}):
        sid = mm.get("site_id") or "default"
        sites_agg[sid]["churn"] += 1
    site_comparison = [
        {"site_id": k, "label": k if k != "default" else "All sites", **{sk: round(sv, 2) if isinstance(sv, float) else sv for sk, sv in v.items()}}
        for k, v in sites_agg.items()
    ]
    site_comparison.sort(key=lambda x: -x["revenue_gbp"])

    # -- Alerts
    alerts: list[dict[str, Any]] = []
    if failed_count >= 5:
        alerts.append({
            "severity": "high",
            "code": "failed_payments_spike",
            "title": f"{failed_count} failed payments this period",
            "detail": "Review the Dunning list in the Members tab and re-attempt.",
        })
    low_occ_sites = [s for s in site_comparison if s["bookings"] > 0 and _pct(s["attended"], s["bookings"]) < 50]
    for s in low_occ_sites:
        alerts.append({
            "severity": "medium",
            "code": "low_attendance",
            "title": f"Site '{s['label']}' attendance under 50%",
            "detail": f"{s['attended']}/{s['bookings']} attended — check class mix or instructor quality.",
        })
    if refund_pct >= 5:
        alerts.append({
            "severity": "medium",
            "code": "refund_spike",
            "title": f"Refund rate {refund_pct}%",
            "detail": "Look at the refunded transactions list and spot patterns (same plan? same site?).",
        })

    payload = {
        "range": {"from": _iso(start), "to": _iso(end)},
        "kpis": {
            "total_bookings": total_bookings,
            "waitlisted": waitlisted,
            "booking_conversion_pct": _pct(booked_direct, booked_direct + waitlisted),
            "payment_success_pct": payment_success_pct,
            "refund_pct": refund_pct,
            "avg_fill_hours": avg_fill_hours,
            "failed_payments": failed_count,
        },
        "site_comparison": site_comparison,
        "alerts": alerts,
    }
    _cache_set(cache_key, payload)
    return payload


# ═════════════════════ AI Insights + At-risk + CRM push (Phase 4) ═════════════════════


class BriefBody(BaseModel):
    period: Literal["weekly", "monthly"] = "weekly"


@router.post("/memberships/analytics/ai-brief")
async def ai_brief(body: BriefBody = Body(default=BriefBody()), user: dict = Depends(get_current_user)):
    await _require_operator_org(user)  # auth gate
    # Build context
    end = _now()
    start = end - timedelta(days=7 if body.period == "weekly" else 30)
    overview = await analytics_overview(  # type: ignore
        from_=_iso(start), to=_iso(end), site_id=None, period="weekly" if body.period == "weekly" else "monthly",
        user=user,
    )
    classes = await analytics_classes(from_=_iso(start), to=_iso(end), site_id=None, user=user)  # type: ignore
    ops = await analytics_operations(from_=_iso(start), to=_iso(end), user=user)  # type: ignore

    brief = await generate_executive_brief({
        "period": body.period,
        "kpis": overview["kpis"],
        "alerts": ops["alerts"],
        "top_classes": classes["top_performing"][:5],
        "underperforming_classes": classes["underperforming"][:5],
        "revenue_forecast": overview["revenue_forecast"],
    })
    return {"brief": brief, "generated_at": _iso(_now())}


@router.get("/memberships/analytics/at-risk")
async def at_risk_members(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    # Pull live members + activity
    members = await db.members.find(
        {"organization_id": org_id, "status": "active"},
        {"_id": 0, "password": 0},
    ).to_list(5000)
    visit_floor = _now() - timedelta(days=30)
    visits: Counter = Counter()
    async for cin in db.member_checkins.find(
        {"organization_id": org_id, "at": {"$gte": _iso(visit_floor)}},
        {"_id": 0, "member_id": 1},
    ):
        visits[cin["member_id"]] += 1
    async for b in db.bookings.find(
        {"organization_id": org_id, "status": "attended", "booked_at": {"$gte": _iso(visit_floor)}},
        {"_id": 0, "member_id": 1},
    ):
        visits[b["member_id"]] = visits.get(b["member_id"], 0) + 1
    failures: Counter = Counter()
    async for p in db.payment_transactions.find(
        {"organization_id": org_id, "payment_status": "failed"},
        {"_id": 0, "member_id": 1},
    ):
        failures[p["member_id"]] += 1

    # Rule-based feature vector, GPT-4o-mini does the ranking + reasoning
    enriched = []
    for m in members:
        v = visits.get(m["id"], 0)
        f = failures.get(m["id"], 0)
        joined = _parse_iso(m.get("created_at"))
        tenure_days = (_now() - joined).days if joined else 0
        enriched.append({
            "id": m["id"],
            "name": f"{m.get('first_name','')} {m.get('last_name','')}".strip(),
            "email": m.get("email"),
            "tenure_days": tenure_days,
            "visits_30d": v,
            "payment_failures": f,
            "no_show_count": int(m.get("no_show_count") or 0),
            "ltv_gbp": _pence_to_gbp(int(m.get("lifetime_value_pence") or 0)),
        })
    # Heuristic risk score (simple, fast — AI refines top-N)
    for e in enriched:
        score = 0
        if e["visits_30d"] == 0 and e["tenure_days"] > 30:
            score += 50
        elif e["visits_30d"] <= 1:
            score += 25
        if e["payment_failures"] >= 1:
            score += 30
        if e["no_show_count"] >= 3:
            score += 15
        if e["tenure_days"] < 45 and e["visits_30d"] < 3:
            score += 10  # early-tenure low engagement
        e["risk_score"] = min(score, 100)
    enriched.sort(key=lambda r: -r["risk_score"])
    top = enriched[:limit]

    # Ask GPT-4o-mini to add a single-sentence `reason` per top-10 (cap token use)
    try:
        top10 = await rank_at_risk_members(top[:10])
        reasons = {r["id"]: r.get("reason") for r in top10}
        for r in top:
            if r["id"] in reasons:
                r["reason"] = reasons[r["id"]]
    except Exception as e:
        logger.warning("AI reason enrichment skipped: %s", e)

    return {"members": top, "count": len(top)}


class CrmPushBody(BaseModel):
    member_ids: list[str]
    pipeline: Literal["retention", "accounts", "sales"] = "retention"
    note: str | None = None


@router.post("/memberships/analytics/crm-push")
async def push_to_crm(body: CrmPushBody, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if not body.member_ids:
        raise HTTPException(400, "member_ids required")
    members = await db.members.find(
        {"id": {"$in": body.member_ids}, "organization_id": org_id},
        {"_id": 0, "password": 0},
    ).to_list(len(body.member_ids))
    pushed = 0
    stage = {
        "retention": "at_risk",
        "accounts": "high_value",
        "sales": "upsell",
    }[body.pipeline]
    # Iter 215bx — write to v2 collections so the active CRM portal sees the push.
    from utils.crm_sync import upsert_crm_contact, log_crm_activity
    for m in members:
        contact_id = await upsert_crm_contact(
            org_id,
            email=m.get("email"),
            first_name=m.get("first_name"),
            last_name=m.get("last_name"),
            phone=m.get("phone"),
            source="memberships_analytics",
            lifecycle="Customer",
            tags=[body.pipeline, stage, "memberships"],
        )
        if not contact_id:
            continue
        await log_crm_activity(
            org_id,
            contact_id=contact_id,
            type="task",
            subject=f"Memberships: {stage.replace('_', ' ').title()} flag",
            body=body.note or f"Auto-flagged by Memberships analytics ({stage}).",
            created_by=user.get("id"),
        )
        pushed += 1
    return {"ok": True, "pushed": pushed, "pipeline": body.pipeline, "stage": stage}


# ═════════════════════ CSV / PDF export (Phase 4) ═════════════════════


@router.get("/memberships/analytics/export.csv")
async def export_csv(
    report: Literal["overview", "retention", "classes", "instructors", "operations", "at_risk"] = Query("overview"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    user: dict = Depends(get_current_user),
):
    await _require_operator_org(user)  # auth gate
    buf = io.StringIO()
    w = csv.writer(buf)

    if report == "overview":
        data = await analytics_overview(from_=from_, to=to, site_id=None, period="monthly", user=user)  # type: ignore
        w.writerow(["Metric", "Value"])
        for k, v in data["kpis"].items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["Bucket", "New members", "Churn", "Revenue GBP"])
        for t in data["trend"]:
            w.writerow([t["bucket"], t["new"], t["churn"], t["revenue"]])
    elif report == "retention":
        data = await analytics_retention(from_=from_, to=to, site_id=None, user=user)  # type: ignore
        w.writerow(["Cohort", "Size", "Month", "Retention %"])
        for c in data["cohort_matrix"]:
            for r in c["retention"]:
                w.writerow([c["cohort"], c["size"], r["month"], r["pct"]])
    elif report == "classes":
        data = await analytics_classes(from_=from_, to=to, site_id=None, user=user)  # type: ignore
        w.writerow(["Class", "Sessions", "Capacity", "Booked", "Attended", "No-show", "Occupancy %"])
        for c in data["classes_ranked"]:
            w.writerow([c["name"], c["sessions"], c["capacity"], c["booked"], c["attended"], c["no_show"], c["occupancy_pct"]])
    elif report == "instructors":
        data = await analytics_classes(from_=from_, to=to, site_id=None, user=user)  # type: ignore
        w.writerow(["Instructor", "Sessions", "Attended", "No-show %", "Occupancy %", "Unique members", "Retention impact", "Payout GBP"])
        for c in data["instructors"]:
            w.writerow([c["name"], c["sessions"], c["attended"], c["no_show_pct"], c["occupancy_pct"], c["unique_members"], c["retention_impact"], c["payout_gbp"]])
    elif report == "operations":
        data = await analytics_operations(from_=from_, to=to, user=user)  # type: ignore
        w.writerow(["Metric", "Value"])
        for k, v in data["kpis"].items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["Site", "Active members", "Revenue GBP", "Bookings", "Attended", "No-show", "Churn"])
        for s in data["site_comparison"]:
            w.writerow([s["label"], s["active_members"], s["revenue_gbp"], s["bookings"], s["attended"], s["no_show"], s["churn"]])
    else:  # at_risk
        data = await at_risk_members(limit=500, user=user)  # type: ignore
        w.writerow(["Name", "Email", "Risk score", "Visits 30d", "Payment failures", "No-shows", "Tenure days", "LTV GBP", "AI reason"])
        for m in data["members"]:
            w.writerow([m["name"], m["email"], m["risk_score"], m["visits_30d"],
                        m["payment_failures"], m["no_show_count"], m["tenure_days"],
                        m["ltv_gbp"], (m.get("reason") or "")])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="memberships-{report}.csv"'},
    )


@router.get("/memberships/analytics/export.pdf")
async def export_pdf(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Weekly executive PDF. Uses reportlab (already installed)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import mm

    ov = await analytics_overview(from_=from_, to=to, site_id=None, period="weekly", user=user)  # type: ignore
    ops = await analytics_operations(from_=from_, to=to, user=user)  # type: ignore
    try:
        brief = await generate_executive_brief({
            "period": "weekly",
            "kpis": ov["kpis"],
            "alerts": ops["alerts"],
            "top_classes": [], "underperforming_classes": [],
            "revenue_forecast": ov["revenue_forecast"],
        })
    except Exception:
        brief = {"headline": "Executive brief", "narrative": "GPT brief unavailable."}

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.setFillColorRGB(0.098, 0.804, 1)  # #19CDFF
    c.rect(0, H - 25 * mm, W, 25 * mm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, H - 16 * mm, "Pulse Fitness Memberships — Weekly Brief")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, H - 22 * mm, f"Generated {_iso(_now())[:10]}")

    y = H - 40 * mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, brief.get("headline") or "Executive brief")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    text = c.beginText(20 * mm, y)
    for line in (brief.get("narrative") or "").split("\n"):
        text.textLine(line[:110])
    c.drawText(text)
    y -= 40 * mm

    # KPI grid
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Key metrics")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for k, v in ov["kpis"].items():
        c.drawString(20 * mm, y, f"• {k.replace('_', ' ').title()}: {v}")
        y -= 5 * mm
        if y < 20 * mm:
            c.showPage()
            y = H - 20 * mm

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="memberships-weekly-brief.pdf"'},
    )


# ═════════════════════ Sites helper ═════════════════════


@router.get("/memberships/analytics/sites")
async def list_sites(user: dict = Depends(get_current_user)):
    """Return the site options operators can filter by."""
    org_id = await _require_operator_org(user)
    site_ids = await db.members.distinct("site_id", {"organization_id": org_id})
    site_ids = [s for s in site_ids if s]
    sites = [{"id": s, "name": s} for s in site_ids]  # enrich from db.sites if available
    async for s in db.sites.find({"id": {"$in": site_ids}}, {"_id": 0, "id": 1, "name": 1}):
        for row in sites:
            if row["id"] == s["id"] and s.get("name"):
                row["name"] = s["name"]
    return {"sites": sites}


# ═════════════════════ Member referrals leaderboard ═════════════════════


@router.get("/memberships/analytics/referrals")
async def analytics_referrals(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Member-to-member referral performance — totals, conversion rate,
    top 10 referrers, and month-on-month trend."""
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to, default_days=180)
    cache_key = _ck("referrals", org_id, start.isoformat(), end.isoformat())
    hit = _cache_get(cache_key)
    if hit is not None:
        return hit

    q: dict = {"organization_id": org_id,
               "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
    rows = await db.referrals.find(q, {"_id": 0}).to_list(5000)
    total = len(rows)
    earned = [r for r in rows if r.get("status") == "earned"]
    pending = [r for r in rows if r.get("status") == "pending"]
    total_credit_pence = sum(int(r.get("credit_pence") or 0) for r in earned)

    # Top referrers
    by_referrer: Counter = Counter()
    earned_by_referrer: Counter = Counter()
    for r in rows:
        rid = r.get("referrer_id")
        if not rid:
            continue
        by_referrer[rid] += 1
        if r.get("status") == "earned":
            earned_by_referrer[rid] += 1
    top_ids = [rid for rid, _ in by_referrer.most_common(10)]
    members_map = {
        m["id"]: m for m in await db.members.find(
            {"id": {"$in": top_ids}}, {"_id": 0, "password": 0}
        ).to_list(len(top_ids) or 1)
    }
    top_referrers = []
    for rid in top_ids:
        m = members_map.get(rid) or {}
        total_refs = by_referrer[rid]
        earned_refs = earned_by_referrer[rid]
        top_referrers.append({
            "member_id": rid,
            "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip() or "—",
            "email": m.get("email"),
            "referral_code": m.get("referral_code"),
            "total": total_refs,
            "earned": earned_refs,
            "conversion_pct": _pct(earned_refs, total_refs),
            "credit_earned_gbp": _pence_to_gbp(int(m.get("promo_credit_pence") or 0)),
        })

    # Month-on-month trend (created_at)
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"new": 0, "earned": 0})
    for r in rows:
        dt = _parse_iso(r.get("created_at"))
        if not dt:
            continue
        b = _bucket_label(dt, "monthly")
        buckets[b]["new"] += 1
        if r.get("status") == "earned":
            buckets[b]["earned"] += 1
    trend = [{"bucket": k, **v} for k, v in sorted(buckets.items())]

    payload = {
        "range": {"from": _iso(start), "to": _iso(end)},
        "kpis": {
            "total": total,
            "earned": len(earned),
            "pending": len(pending),
            "conversion_pct": _pct(len(earned), total),
            "credit_paid_gbp": _pence_to_gbp(total_credit_pence),
        },
        "top_referrers": top_referrers,
        "trend": trend,
    }
    _cache_set(cache_key, payload)
    return payload





# ═════════════════════ KPI drill-down (Phase 4) ═════════════════════


@router.get("/memberships/analytics/members-by-kpi")
async def members_by_kpi(
    kpi: Literal[
        "active_members", "new_members", "cancellations", "frozen",
        "failed_payments", "recovered_payments",
        "highly_engaged", "regular", "at_risk_segment", "inactive",
    ] = Query(..., description="Which KPI to drill into"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    """Return the underlying member list behind a KPI card. All filters are
    org-scoped via the operator JWT."""
    org_id = await _require_operator_org(user)
    start, end = _daterange(from_, to)
    rows: list[dict] = []

    if kpi == "active_members":
        async for m in db.members.find(
            {"organization_id": org_id, "status": "active"},
            {"_id": 0, "password": 0},
        ).limit(limit):
            rows.append(_member_brief(m))
    elif kpi == "new_members":
        async for m in db.members.find(
            {"organization_id": org_id,
             "created_at": {"$gte": _iso(start), "$lte": _iso(end)}},
            {"_id": 0, "password": 0},
        ).limit(limit):
            rows.append(_member_brief(m))
    elif kpi == "cancellations":
        async for mm in db.member_memberships.find(
            {"organization_id": org_id, "status": "cancelled",
             "cancel_effective_date": {"$gte": _iso(start), "$lte": _iso(end)}},
            {"_id": 0}).limit(limit):
            mem = await db.members.find_one(
                {"id": mm["member_id"]}, {"_id": 0, "password": 0})
            if mem:
                rows.append({**_member_brief(mem),
                             "cancel_reason": mm.get("cancel_reason"),
                             "cancel_effective_date": mm.get("cancel_effective_date")})
    elif kpi == "frozen":
        async for mm in db.member_memberships.find(
            {"organization_id": org_id, "status": "frozen"},
            {"_id": 0}).limit(limit):
            mem = await db.members.find_one(
                {"id": mm["member_id"]}, {"_id": 0, "password": 0})
            if mem:
                rows.append({**_member_brief(mem),
                             "frozen_until": mm.get("frozen_until")})
    elif kpi in ("failed_payments", "recovered_payments"):
        payment_status = "failed" if kpi == "failed_payments" else "paid"
        q: dict = {"organization_id": org_id, "payment_status": payment_status,
                   "created_at": {"$gte": _iso(start), "$lte": _iso(end)}}
        if kpi == "recovered_payments":
            q["recovered_from"] = {"$exists": True}
        seen: set = set()
        async for t in db.payment_transactions.find(q, {"_id": 0}).limit(limit):
            mid = t.get("member_id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            mem = await db.members.find_one({"id": mid}, {"_id": 0, "password": 0})
            if mem:
                rows.append({**_member_brief(mem),
                             "amount_gbp": _pence_to_gbp(int(t.get("amount_pence") or 0)),
                             "payment_method": t.get("method")})
    elif kpi in ("highly_engaged", "regular", "at_risk_segment", "inactive"):
        # Re-run the retention segmentation and pull the matching bucket.
        ret = await analytics_retention(from_=from_, to=to, site_id=None, user=user)  # type: ignore
        bucket_map = {
            "highly_engaged": "highly_engaged", "regular": "regular",
            "at_risk_segment": "at_risk", "inactive": "inactive",
        }
        rows = (ret.get("segment_members") or {}).get(bucket_map[kpi], [])[:limit]
    return {"kpi": kpi, "count": len(rows), "members": rows}


def _member_brief(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "name": f"{m.get('first_name','')} {m.get('last_name','')}".strip() or "—",
        "email": m.get("email"),
        "phone": m.get("phone"),
        "status": m.get("status"),
        "tags": m.get("tags") or [],
        "lifetime_value_gbp": _pence_to_gbp(int(m.get("lifetime_value_pence") or 0)),
        "created_at": m.get("created_at"),
    }


# ═════════════════════ Weekly digest — manual trigger ═════════════════════


@router.post("/memberships/analytics/send-weekly-digest")
async def send_weekly_digest_now(user: dict = Depends(get_current_user)):
    """Operator-initiated: force the weekly digest to build & send right now
    for this org (useful for testing + opt-in send-a-digest button)."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    from utils.memberships_digest import send_weekly_digest_for_org
    res = await send_weekly_digest_for_org(org, force=True)
    return res


@router.get("/memberships/analytics/winback-candidates")
async def winback_candidates(user: dict = Depends(get_current_user)):
    """Preview of lapsed members eligible for a win-back email — shown in
    the Analytics → AI Insights panel before a manager hits 'Send now'."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    from utils.memberships_winback import run_winback_dispatcher
    res = await run_winback_dispatcher(dry_run=True)
    # Dry-run returns totals; also build a small list of recent candidates
    # for the UI: <=5 lapsed members sorted by last-attended desc.
    cutoff = (_now() - timedelta(days=7)).isoformat()
    rows: list[dict] = []
    async for m in db.members.find(
        {"organization_id": org_id, "status": "active"},
        {"_id": 0, "password": 0},
    ).limit(200):
        last_checkin = await db.member_checkins.find_one(
            {"member_id": m["id"]}, {"_id": 0, "at": 1}, sort=[("at", -1)])
        last_booking = await db.bookings.find_one(
            {"member_id": m["id"], "status": "attended"},
            {"_id": 0, "checked_in_at": 1, "booked_at": 1},
            sort=[("checked_in_at", -1)])
        last_at = (last_checkin or {}).get("at") or \
                  (last_booking or {}).get("checked_in_at") or \
                  (last_booking or {}).get("booked_at")
        if not last_at or str(last_at) >= cutoff:
            continue
        rows.append({
            "id": m["id"],
            "name": f"{m.get('first_name','')} {m.get('last_name','')}".strip(),
            "email": m.get("email"),
            "last_attended_at": last_at,
            "winback_last_sent_at": m.get("winback_last_sent_at"),
        })
    rows.sort(key=lambda r: r["last_attended_at"], reverse=True)
    return {"totals": res, "preview": rows[:10]}


@router.post("/memberships/analytics/send-winback-now")
async def send_winback_now(user: dict = Depends(get_current_user)):
    """Operator-initiated immediate win-back run for this org only."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    from utils.memberships_winback import send_winback_for_member, _longest_streak
    cutoff = (_now() - timedelta(days=7)).isoformat()
    sent = 0
    skipped = 0
    async for m in db.members.find(
        {"organization_id": org_id, "status": "active"},
        {"_id": 0, "password": 0},
    ):
        last_checkin = await db.member_checkins.find_one(
            {"member_id": m["id"]}, {"_id": 0, "at": 1}, sort=[("at", -1)])
        last_booking = await db.bookings.find_one(
            {"member_id": m["id"], "status": "attended"},
            {"_id": 0, "checked_in_at": 1, "booked_at": 1},
            sort=[("checked_in_at", -1)])
        last_at = (last_checkin or {}).get("at") or \
                  (last_booking or {}).get("checked_in_at") or \
                  (last_booking or {}).get("booked_at")
        if not last_at or str(last_at) >= cutoff:
            continue
        streak = await _longest_streak(m["id"])
        if streak < 5:
            skipped += 1
            continue
        res = await send_winback_for_member(m, org)
        if res.get("sent"):
            sent += 1
        else:
            skipped += 1
    return {"ok": True, "sent": sent, "skipped": skipped}


# ═════════════════════ Public brag widget ═════════════════════


@router.get("/m/{slug}/brag")
async def public_brag(slug: str):
    """Shareable public stats for a gym. Safe to expose — no individual
    member PII, just high-level counts & top class."""
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Studio not found")
    org_id = org["id"]
    now = _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    active = await db.members.count_documents({"organization_id": org_id, "status": "active"})
    classes_this_month = await db.class_occurrences.count_documents({
        "organization_id": org_id,
        "starts_at": {"$gte": _iso(month_start), "$lte": _iso(now)},
        "status": {"$in": ["completed", "scheduled"]},
    })
    attended_this_month = 0
    async for o in db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": _iso(month_start), "$lte": _iso(now)}},
        {"_id": 0, "attended_count": 1},
    ):
        attended_this_month += int(o.get("attended_count") or 0)

    # Top class by total attended last 30 days
    since = now - timedelta(days=30)
    tpl_stats: dict[str, dict] = {}
    async for o in db.class_occurrences.find(
        {"organization_id": org_id, "starts_at": {"$gte": _iso(since), "$lte": _iso(now)}},
        {"_id": 0, "name": 1, "attended_count": 1, "template_id": 1, "colour": 1},
    ):
        key = o.get("template_id") or "none"
        if key not in tpl_stats:
            tpl_stats[key] = {"name": o.get("name"), "attended": 0, "colour": o.get("colour")}
        tpl_stats[key]["attended"] += int(o.get("attended_count") or 0)
    top = max(tpl_stats.values(), key=lambda x: x["attended"], default=None)

    return {
        "organization": {
            "name": org.get("name"),
            "slug": org.get("slug"),
            "logo_url": org.get("logo_url"),
            "primary_brand_colour": org.get("primary_brand_colour") or "#19CDFF",
        },
        "stats": {
            "active_members": active,
            "classes_this_month": classes_this_month,
            "attendance_this_month": attended_this_month,
            "top_class": top,
            "as_of": _iso(now),
        },
    }


# ═════════════════════ Reception QR poster (public) ═════════════════════


@router.get("/m/{slug}/poster.png")
async def public_poster(
    slug: str,
    variant: Literal["book", "brag"] = "book",
    fmt: Literal["a4", "square", "story"] = Query("a4", alias="format"),
):
    """Reception-ready poster PNG. Public, no auth — embed in print jobs.

    `variant=book` → QR to /m/{slug} booking app (default).
    `variant=brag` → QR to /m/{slug}/brag public stats card.
    `format=a4|square|story` → canvas size.
    """
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Studio not found")
    import os
    origin = (os.environ.get("PUBLIC_ORIGIN")
              or os.environ.get("FRONTEND_ORIGIN")
              or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
    target = f"{origin}/m/{slug}" + ("/brag" if variant == "brag" else "")

    from utils.memberships_poster import render_poster_png
    png = render_poster_png(
        studio_name=org.get("name") or "Your Studio",
        url=target,
        brand_hex=org.get("primary_brand_colour") or "#19CDFF",
        variant=variant,
        fmt=fmt,
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{slug}-{fmt}-{variant}.png"',
            "Cache-Control": "public, max-age=900",
        },
    )


@router.get("/m/{slug}/poster.pdf")
async def public_poster_pdf(slug: str, variant: Literal["book", "brag"] = "book"):
    """A4 poster wrapped in a print-shop-ready PDF."""
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Studio not found")
    import os
    origin = (os.environ.get("PUBLIC_ORIGIN")
              or os.environ.get("FRONTEND_ORIGIN")
              or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
    target = f"{origin}/m/{slug}" + ("/brag" if variant == "brag" else "")

    from utils.memberships_poster import render_poster_pdf
    pdf = render_poster_pdf(
        studio_name=org.get("name") or "Your Studio",
        url=target,
        brand_hex=org.get("primary_brand_colour") or "#19CDFF",
        variant=variant,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{slug}-poster.pdf"',
            "Cache-Control": "public, max-age=900",
        },
    )


@router.get("/m/{slug}/og.png")
async def public_og_image(slug: str):
    """1200×630 Open Graph preview for WhatsApp / LinkedIn / Twitter unfurls."""
    brag = await public_brag(slug)
    org = brag["organization"]
    stats = brag["stats"]
    from utils.memberships_poster import render_og_png
    png = render_og_png(
        studio_name=org.get("name"),
        brand_hex=org.get("primary_brand_colour") or "#19CDFF",
        stats=stats,
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{slug}-og.png"',
            "Cache-Control": "public, max-age=300",
        },
    )


@router.get("/m/{slug}/share")
async def public_share_page(slug: str):
    """Minimal HTML with OG tags so pasted links unfurl correctly on social
    platforms before they're reached. Clients (browsers, crawlers) get the
    meta tags; human visitors are redirected to /m/{slug}/brag by JS."""
    org = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Studio not found")
    import os
    origin = (os.environ.get("PUBLIC_ORIGIN")
              or os.environ.get("FRONTEND_ORIGIN")
              or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
    name = org.get("name") or "Your Studio"
    brand = org.get("primary_brand_colour") or "#19CDFF"
    og_img = f"{origin}/api/m/{slug}/og.png"
    target = f"{origin}/m/{slug}/brag"
    description = "Live class times, instant booking, and your member app — powered by Pulse Fitness."
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{name} · Pulse Fitness</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{name}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{target}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{name}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{og_img}">
<meta name="theme-color" content="{brand}">
<meta http-equiv="refresh" content="0; url={target}">
<style>body{{background:#05070A;color:#fff;font-family:-apple-system,sans-serif;display:grid;place-items:center;height:100vh;margin:0;text-align:center;}}a{{color:{brand};}}</style>
</head><body>
<div><h1 style="font-weight:800;">{name}</h1><p><a href="{target}">Open the member app →</a></p></div>
</body></html>"""
    return Response(content=html, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=300"})
