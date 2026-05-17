"""
GymAxis CAPEX ↔ Service Ops signal layer — Iter 216h154 (Feb 2026).

Aggregates the last 12 months of `svc_cases` and `svc_quotes` per
equipment asset so the CAPEX board report can recommend repair-vs-
replace with **live service spend**, not just self-service issue
counts. Closes the SVC → CAPEX feedback loop identified in the Feb
2026 process audit.

Design:
  * Pure read; no writes. Safe to call on every CAPEX render.
  * Lean projections; one-pass over Mongo. Targets fleets of <5k
    assets across <500 cases/yr — the common UK gym chain.
  * Asset matching is best-effort, in priority order:
      1) Exact `asset_id`
      2) Any `equipment_ids[]` membership
      3) Manufacturer + model match on the case (rarely used,
         intentionally non-strict — service desks frequently leave
         this blank)
  * `service_to_replacement_ratio` is the canonical BER metric: total
    service spend (net, ex-VAT) over the last 12 months ÷ replacement
    cost. >0.5 over a 12-month window is the industry red line.

The aggregator returns a per-asset dict that the CAPEX scoring path
can blend into its existing `stats` object — see `routes/capex.py`
for the integration point.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.database import db
from utils.safe_paginate import safe_to_list, BULK_CAP


def _iso_days_ago(days: int = 365) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# Backwards-compat alias kept for any external callers; new code should
# pass `window_days` to `aggregate_service_signals` directly.
def _iso_12mo_ago() -> str:
    return _iso_days_ago(365)


def _safe_minutes(case: dict) -> int:
    """Best-effort downtime estimate per case (minutes). Falls back
    to `estimated_minutes` then a 90-min industry default."""
    return int(case.get("on_site_minutes") or case.get("actual_minutes")
               or case.get("estimated_minutes") or 90)


async def aggregate_service_signals(
    org_filter: dict, *,
    asset_ids: Optional[list[str]] = None,
    window_days: int = 365,
) -> dict[str, dict]:
    """Build per-asset service signals over `window_days` (default 365).

    Iter 216h162 — window is now configurable so callers can compare
    6-month vs 12-month BER trends. Returns the same shape regardless
    of window: `{asset_id: {service_visits_Nmo, service_spend_Nmo,
    last_service_at, open_service_cases, downtime_hours_Nmo}}`. Keys
    keep the `_12mo` suffix for backwards compatibility — the CAPEX
    scorer and PDF exporter both read those exact keys.

    `asset_ids` is an optional prefilter for the equipment we're
    actually interested in — saves a full collection scan for orgs
    with thousands of legacy cases linked to retired equipment.
    """
    since = _iso_days_ago(window_days)
    case_query: dict = {
        **org_filter,
        # Either closed/invoiced last 12mo, or currently open (counts
        # toward "open_service_cases" but not spend).
        "$or": [
            {"updated_at": {"$gte": since}},
            {"created_at": {"$gte": since}},
        ],
    }
    if asset_ids:
        case_query["$and"] = [
            {"$or": [
                {"asset_id": {"$in": asset_ids}},
                {"equipment_ids": {"$elemMatch": {"$in": asset_ids}}},
            ]},
        ]

    # Iter 216h171 — wrapped with safe_to_list for truncation telemetry.
    cases = await safe_to_list(
        db.svc_cases.find(
            case_query,
            {"_id": 0, "id": 1, "organization_id": 1, "status": 1,
             "asset_id": 1, "equipment_ids": 1,
             "created_at": 1, "updated_at": 1,
             "closed_at": 1, "invoiced_at": 1,
             "on_site_minutes": 1, "actual_minutes": 1, "estimated_minutes": 1},
        ),
        cap=BULK_CAP * 2,  # 20k — fleet-wide BER analysis spans deep history
        name="svc_capex_signals.cases",
    )

    if not cases:
        return {}

    case_ids = [c["id"] for c in cases]
    # Pull all quotes that point at these cases. We don't trust the
    # status alone — `invoiced` is the strongest signal, but `approved`
    # quotes also indicate committed service spend.
    quotes = await safe_to_list(
        db.svc_quotes.find(
            {**org_filter, "case_id": {"$in": case_ids},
             "status": {"$in": ["invoiced", "approved"]}},
            {"_id": 0, "case_id": 1, "net": 1, "subtotal": 1, "status": 1},
        ),
        cap=BULK_CAP * 2,
        name="svc_capex_signals.quotes",
    )

    spend_by_case: dict[str, float] = {}
    for q in quotes:
        c = q.get("case_id")
        if not c:
            continue
        amt = float(q.get("net") or q.get("subtotal") or 0)
        if amt <= 0:
            continue
        # If a case has multiple quotes (rare — usually re-quotes),
        # take the highest committed value as authoritative spend.
        existing = spend_by_case.get(c)
        if existing is None or amt > existing:
            spend_by_case[c] = amt

    by_asset: dict[str, dict] = {}

    def _touch(aid: str, case: dict) -> dict:
        bucket = by_asset.setdefault(aid, {
            "service_visits_12mo": 0,
            "open_service_cases": 0,
            "service_spend_12mo": 0.0,
            "last_service_at": None,
            "downtime_hours_12mo": 0.0,
            "case_ids": [],
        })
        bucket["case_ids"].append(case["id"])
        return bucket

    for case in cases:
        # Each case can touch one primary `asset_id` plus any number
        # of `equipment_ids`. Treat the primary as the spend-bearing
        # asset (avoids double-counting); `equipment_ids` get a visit
        # tally only when no primary is set.
        primary = case.get("asset_id") or ""
        covered = list(case.get("equipment_ids") or [])
        if primary and primary not in covered:
            covered.insert(0, primary)
        if not covered:
            continue

        status = case.get("status") or ""
        is_open = status not in ("closed", "invoiced", "rejected")
        spend = spend_by_case.get(case["id"], 0.0)
        downtime_h = _safe_minutes(case) / 60.0
        when = case.get("closed_at") or case.get("invoiced_at") or case.get("updated_at")

        # Primary asset bears spend + downtime + recency.
        if primary:
            b = _touch(primary, case)
            b["service_visits_12mo"] += 1
            if is_open:
                b["open_service_cases"] += 1
            b["service_spend_12mo"] += spend
            b["downtime_hours_12mo"] += downtime_h
            if when and (b["last_service_at"] is None or when > b["last_service_at"]):
                b["last_service_at"] = when

        # Secondary `equipment_ids` get a visit count only — fixes
        # the "PPM-batch case touched 10 treadmills" inflation
        # problem without losing them from the visit tally.
        for aid in covered:
            if aid == primary:
                continue
            b = _touch(aid, case)
            b["service_visits_12mo"] += 1
            if is_open:
                b["open_service_cases"] += 1
            if when and (b["last_service_at"] is None or when > b["last_service_at"]):
                b["last_service_at"] = when

    # Round floats for the API.
    for sig in by_asset.values():
        sig["service_spend_12mo"] = round(sig["service_spend_12mo"], 2)
        sig["downtime_hours_12mo"] = round(sig["downtime_hours_12mo"], 1)
    return by_asset


def compute_repair_vs_replace(
    *, service_spend_12mo: float, replacement_cost: float,
) -> dict:
    """Industry-standard BER (Beyond Economic Repair) ratio + a
    plain-English recommendation suitable for the board report.

    Thresholds:
      • ratio ≥ 0.50 over 12 months → replace
      • 0.25–0.50                    → watch
      • < 0.25                       → keep
    """
    if not replacement_cost or replacement_cost <= 0:
        return {
            "service_to_replacement_ratio": None,
            "ber_recommendation": "insufficient_data",
            "ber_label": "Insufficient data",
        }
    ratio = round((service_spend_12mo or 0) / replacement_cost, 3)
    if ratio >= 0.50:
        rec, label = "replace", "Replace — BER threshold breached"
    elif ratio >= 0.25:
        rec, label = "watch", "Watch — approaching BER threshold"
    else:
        rec, label = "keep", "Keep — economic to repair"
    return {
        "service_to_replacement_ratio": ratio,
        "ber_recommendation": rec,
        "ber_label": label,
    }


__all__ = ["aggregate_service_signals", "compute_repair_vs_replace"]
