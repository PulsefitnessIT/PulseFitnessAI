from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from datetime import datetime, timezone
from typing import Optional
import json
import uuid
import logging

from utils.database import db, EMERGENT_LLM_KEY
from utils.auth import get_current_user, get_organization_filter
from utils.helpers import get_bulk_equipment_stats
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter()

# Default replacement costs (GBP) and lifespans (years) by equipment type
DEFAULT_EQUIPMENT_PROFILES = {
    "Treadmill":        {"cost": 3500, "lifespan": 8},
    "Cross Trainer":    {"cost": 2800, "lifespan": 8},
    "Elliptical":       {"cost": 2800, "lifespan": 8},
    "Exercise Bike":    {"cost": 1800, "lifespan": 7},
    "Spin Bike":        {"cost": 1200, "lifespan": 7},
    "Rowing Machine":   {"cost": 1800, "lifespan": 8},
    "Stairclimber":     {"cost": 3200, "lifespan": 8},
    "Cable Machine":    {"cost": 4500, "lifespan": 12},
    "Smith Machine":    {"cost": 3500, "lifespan": 15},
    "Leg Press":        {"cost": 3000, "lifespan": 12},
    "Chest Press":      {"cost": 2500, "lifespan": 12},
    "Shoulder Press":   {"cost": 2200, "lifespan": 12},
    "Lat Pulldown":     {"cost": 2200, "lifespan": 12},
    "Functional Trainer": {"cost": 4000, "lifespan": 10},
    "Power Rack":       {"cost": 2000, "lifespan": 15},
    "Bench":            {"cost": 600,  "lifespan": 15},
    "Dumbbells":        {"cost": 800,  "lifespan": 20},
    "Weight Plates":    {"cost": 500,  "lifespan": 20},
}
DEFAULT_PROFILE = {"cost": 2500, "lifespan": 10}

# Default scoring thresholds
DEFAULT_THRESHOLDS = {
    "age_weight": 25,
    "fault_count_weight": 25,
    "fault_frequency_weight": 20,
    "severity_weight": 15,
    "warranty_weight": 15,
    "replace_now_min": 80,
    "replace_soon_min": 60,
    "at_risk_min": 40,
    "monitor_min": 20,
}


def _require_owner_or_manager(user: dict) -> None:
    if user.get("role") not in ("owner", "manager", "master_admin"):
        raise HTTPException(status_code=403, detail="CAPEX data is restricted to Owner and Manager roles")


def _get_profile(equipment_type: str) -> dict[str, int]:
    for key, profile in DEFAULT_EQUIPMENT_PROFILES.items():
        if key.lower() in equipment_type.lower() or equipment_type.lower() in key.lower():
            return profile
    return DEFAULT_PROFILE


def _score_age(days_in_service, expected_lifespan: float) -> float:
    """Age score (0-100)."""
    if days_in_service and days_in_service > 0:
        return min(min(days_in_service / expected_lifespan, 2.0) * 60, 100)
    return 20


def _score_fault_count(total_faults: int) -> float:
    """Fault count score (0-100)."""
    if total_faults >= 10:
        return 100
    if total_faults >= 6:
        return 75
    if total_faults >= 3:
        return 50
    if total_faults >= 1:
        return 25
    return 0


def _score_fault_frequency(days_in_service: Optional[int], total_faults: int) -> float:
    """Fault frequency score (0-100) — faults per month."""
    if not days_in_service or days_in_service <= 30 or total_faults <= 0:
        return 0
    fpm = (total_faults / days_in_service) * 30
    if fpm >= 2:
        return 100
    if fpm >= 1:
        return 75
    if fpm >= 0.5:
        return 50
    return 25


def _score_warranty(warranty_days: Optional[int]) -> float:
    """Warranty score (0-100)."""
    if warranty_days is None:
        return 50
    if warranty_days <= 0:
        return 90
    if warranty_days <= 90:
        return 60
    if warranty_days <= 180:
        return 30
    return 0


def _determine_status(total_score: float, thresholds: dict) -> tuple[str, str, Optional[int]]:
    """Determine CAPEX status and suggested action from score."""
    if total_score >= thresholds["replace_now_min"]:
        status = "replace_now"
    elif total_score >= thresholds["replace_soon_min"]:
        status = "replace_soon"
    elif total_score >= thresholds["at_risk_min"]:
        status = "at_risk"
    elif total_score >= thresholds["monitor_min"]:
        status = "monitor"
    else:
        status = "healthy"

    actions = {
        "replace_now": "Immediate replacement required",
        "replace_soon": "Replace within 6-12 months",
        "at_risk": "Monitor closely — schedule replacement review",
        "monitor": "Continue using — monitor condition",
        "healthy": "Continue using — no action required",
    }
    months = {"replace_now": 3, "replace_soon": 9, "at_risk": 12}.get(status)
    return status, actions[status], months


def _compute_capex_score(equip: dict, stats: dict, thresholds: dict) -> dict:
    """Compute CAPEX replacement score (0-100) for a single equipment item."""
    profile = _get_profile(equip.get("equipment_type", ""))
    replacement_cost = equip.get("replacement_cost") or profile["cost"]
    expected_lifespan = (equip.get("expected_lifespan_years") or profile["lifespan"]) * 365
    days_in_service = stats.get("days_in_service")
    total_faults = stats.get("total_issues", 0)

    scores = {
        "age": _score_age(days_in_service, expected_lifespan),
        "fault_count": _score_fault_count(total_faults),
        "fault_frequency": _score_fault_frequency(days_in_service, total_faults),
        "severity": min(stats.get("critical_faults", 0) * 30 + stats.get("open_issues", 0) * 15, 100),
        "warranty": _score_warranty(stats.get("warranty_days_remaining")),
    }

    w = thresholds
    weight_sum = w["age_weight"] + w["fault_count_weight"] + w["fault_frequency_weight"] + w["severity_weight"] + w["warranty_weight"]
    total = round((
        scores["age"] * w["age_weight"] +
        scores["fault_count"] * w["fault_count_weight"] +
        scores["fault_frequency"] * w["fault_frequency_weight"] +
        scores["severity"] * w["severity_weight"] +
        scores["warranty"] * w["warranty_weight"]
    ) / weight_sum, 1)

    status, action, replace_months = _determine_status(total, thresholds)
    engineer_faults = max(0, total_faults - stats.get("self_fixes", 0))

    return {
        "score": total,
        "status": status,
        "status_label": status.replace("_", " ").title(),
        "suggested_action": action,
        "replacement_cost": replacement_cost,
        "estimated_repair_spend": engineer_faults * 150,
        "replace_within_months": replace_months,
        "score_breakdown": scores,
        "age_years": round(days_in_service / 365, 1) if days_in_service else None,
        "age_days": days_in_service,
        "in_service_date": stats.get("in_service_date"),
        "warranty_active": stats.get("warranty_active", False),
        "warranty_months_remaining": stats.get("warranty_months_remaining"),
        "warranty_days_remaining": stats.get("warranty_days_remaining"),
        "expected_lifespan_years": equip.get("expected_lifespan_years") or profile["lifespan"],
    }


async def _get_thresholds(org_id: Optional[str] = None) -> dict:
    """Get CAPEX thresholds, org-specific or global defaults."""
    if org_id:
        config = await db.capex_config.find_one({"organization_id": org_id}, {"_id": 0})
        if config and config.get("thresholds"):
            return {**DEFAULT_THRESHOLDS, **config["thresholds"]}
    return DEFAULT_THRESHOLDS


def _build_severity_lookup(all_issues: list[dict]) -> tuple[dict, dict]:
    """Build severity and self-fix lookup dicts from issue list."""
    severity_lookup = {}
    selffix_lookup = {}
    for issue in all_issues:
        sn = issue.get("serial_number", "")
        severity_lookup.setdefault(sn, {"critical": 0, "medium": 0, "low": 0})
        sev = issue.get("severity", "medium")
        severity_lookup[sn][sev] = severity_lookup[sn].get(sev, 0) + 1
        rt = issue.get("resolution_type") or issue.get("resolved_by")
        if rt in ("self_fix", "gymaxis_ai"):
            selffix_lookup[sn] = selffix_lookup.get(sn, 0) + 1
    return severity_lookup, selffix_lookup


def _accumulate_forecast(
    capex: dict, equip_type: str, location: str,
    forecast: dict, by_type: dict, by_location: dict, by_priority: dict,
) -> int:
    """Add replacement cost to forecast buckets. Returns cost if flagged, else 0."""
    months = capex["replace_within_months"]
    if not months:
        return 0
    cost = capex["replacement_cost"]
    if months <= 3:
        forecast["3m"] += cost
        forecast["6m"] += cost
        forecast["12m"] += cost
        by_priority["immediate"] += cost
    elif months <= 6:
        forecast["6m"] += cost
        forecast["12m"] += cost
        by_priority["short_term"] += cost
    else:
        forecast["12m"] += cost
        by_priority["medium_term"] += cost
    by_type[equip_type] = by_type.get(equip_type, 0) + cost
    by_location[location] = by_location.get(location, 0) + cost
    return cost


def _build_capex_result_item(equip: dict, stats: dict, capex: dict, faults_by_eq: dict | None = None,
                             severity_counts: dict | None = None) -> dict:
    """Build a single result dict for the CAPEX response.

    Iter 216h127 — extended with the intelligence layer:
    lifecycle_stage, condition_scores, fault_history, downtime,
    ber_flag, safety_risk, roi_estimate, recommendation_detail.
    """
    from datetime import datetime, timezone
    from utils.capex_intelligence import (
        compute_lifecycle_stage, compute_condition_scores,
        compute_fault_history_breakdown, compute_downtime_metrics,
        compute_ber_flag, compute_safety_risk, compute_roi_estimate,
        build_recommendation_detail,
    )
    now_dt = datetime.now(timezone.utc)
    asset_faults = (faults_by_eq or {}).get(equip["id"], [])
    severity_counts = severity_counts or {}

    lifecycle = compute_lifecycle_stage(capex.get("age_years"), capex.get("expected_lifespan_years"))
    fault_history = compute_fault_history_breakdown(asset_faults, now_dt)
    downtime = compute_downtime_metrics(asset_faults, now_dt)
    condition = compute_condition_scores(stats, severity_counts, capex.get("age_years"),
                                          capex.get("expected_lifespan_years"))
    ber = compute_ber_flag(capex.get("estimated_repair_spend", 0), capex.get("replacement_cost", 0))
    safety = compute_safety_risk(severity_counts, fault_history)
    roi = compute_roi_estimate(
        capex.get("estimated_repair_spend", 0) or 0,
        capex.get("replacement_cost", 0) or 0,
        capex.get("expected_lifespan_years") or 8,
        downtime.get("total_days_oos") or 0,
    )
    recommendation = build_recommendation_detail(
        status=capex.get("status", "monitor"),
        lifecycle_stage=lifecycle, safety_risk=safety,
        ber_flag=ber, condition=condition,
        age_years=capex.get("age_years"),
        expected_lifespan_years=capex.get("expected_lifespan_years"),
    )

    return {
        "id": equip["id"], "name": equip.get("name", "Unknown"),
        "equipment_type": equip.get("equipment_type", "Unknown"),
        "manufacturer": equip.get("manufacturer", ""), "model": equip.get("model", ""),
        "serial_number": equip.get("serial_number", ""),
        "location": equip.get("location", "Unassigned") or "Unassigned",
        "site_id": equip.get("site_id"),
        "organization_id": equip.get("organization_id"),
        "purchase_date": equip.get("purchase_date"), "warranty_expiry": equip.get("warranty_expiry"),
        "service_contract_end": equip.get("service_contract_end"),
        "total_faults": stats.get("total_issues", 0), "open_faults": stats.get("open_issues", 0),
        "days_in_service": stats.get("days_in_service"),
        "warranty_active": stats.get("warranty_active", False),
        "capex": capex,
        # ── New intelligence layer ──
        "lifecycle_stage": lifecycle,
        "condition_scores": condition,
        "fault_history": fault_history,
        "downtime": downtime,
        "ber_flag": ber,
        "safety_risk": safety,
        "roi_estimate": roi,
        "recommendation": recommendation,
    }


def _aggregate_capex_results(
    equipment_list: list[dict],
    bulk_stats: dict,
    severity_lookup: dict,
    selffix_lookup: dict,
    thresholds: dict,
    faults_by_eq: dict | None = None,
) -> tuple[list, dict, int, dict, dict, dict, dict]:
    """Score all equipment and aggregate summary, forecasts, and breakdowns."""
    results: list[dict] = []
    summary = {"total": len(equipment_list), "healthy": 0, "monitor": 0, "at_risk": 0, "replace_soon": 0, "replace_now": 0}
    total_replacement_cost = 0
    forecast: dict[str, int] = {"3m": 0, "6m": 0, "12m": 0}
    by_type: dict[str, int] = {}
    by_location: dict[str, int] = {}
    by_priority: dict[str, int] = {"immediate": 0, "short_term": 0, "medium_term": 0}

    for equip in equipment_list:
        stats = bulk_stats.get(equip["id"], {})
        sn = equip.get("serial_number", "") or equip.get("name", "")
        sev_data = severity_lookup.get(sn, {"critical": 0, "medium": 0, "low": 0})
        stats["critical_faults"] = sev_data.get("critical", 0)
        stats["self_fixes"] = selffix_lookup.get(sn, 0)

        capex = _compute_capex_score(equip, stats, thresholds)
        summary[capex["status"]] += 1
        location = equip.get("location", "Unassigned") or "Unassigned"
        total_replacement_cost += _accumulate_forecast(
            capex, equip.get("equipment_type", "Unknown"), location,
            forecast, by_type, by_location, by_priority,
        )
        results.append(_build_capex_result_item(equip, stats, capex,
                                                faults_by_eq=faults_by_eq,
                                                severity_counts=sev_data))

    results.sort(key=lambda x: x["capex"]["score"], reverse=True)
    return results, summary, total_replacement_cost, forecast, by_type, by_location, by_priority


@router.get("/capex/analysis")
async def get_capex_analysis(
    user: dict = Depends(get_current_user),
    site_id: str | None = None,
):
    _require_owner_or_manager(user)
    # Iter 216h120 — MOD HQ rebind. CAPEX is a flagship report for
    # Lee's MOD pitch; the HQ tier needs to see the whole estate's
    # equipment in "All Operations Sites" mode AND drill into a single
    # garrison gym to justify base-specific replacement spend.
    from utils.mod_scope import resolve_mod_query_filter
    from utils.capex_intelligence import aggregate_fleet_intelligence
    from utils.svc_capex_signals import (
        aggregate_service_signals, compute_repair_vs_replace,
    )
    org_filter = await resolve_mod_query_filter(user, site_id)
    thresholds = await _get_thresholds(user.get("organization_id"))

    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(5000)
    if not equipment_list:
        return {
            "equipment": [], "summary": {"total": 0}, "forecast": {},
            "fleet_intelligence": aggregate_fleet_intelligence([]),
        }

    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)
    all_issues = await db.issues.find(
        org_filter,
        {"_id": 0, "id": 1, "serial_number": 1, "severity": 1, "resolution_type": 1,
         "resolved_by": 1, "organization_id": 1, "equipment_id": 1,
         "issue_description": 1, "status": 1, "created_at": 1, "resolved_at": 1,
         "updated_at": 1},
    ).to_list(20000)

    severity_lookup, selffix_lookup = _build_severity_lookup(all_issues)
    # Iter 216h127 — also group full fault dicts by equipment_id so
    # the intelligence layer (downtime + fault history breakdown) can
    # compute time-based metrics per asset.
    faults_by_eq: dict[str, list] = {}
    for iss in all_issues:
        eid = iss.get("equipment_id")
        if eid:
            faults_by_eq.setdefault(eid, []).append(iss)

    # Iter 216h154 — SVC → CAPEX signal layer. Aggregate the last 12
    # months of service cases per asset and blend the visit count into
    # `total_issues` so the existing scorer recognises engineer
    # callouts (not just self-service issues). Spend + BER ratio are
    # exposed under `service_signals` on each result item.
    asset_ids = [e["id"] for e in equipment_list]
    svc_signals = await aggregate_service_signals(org_filter, asset_ids=asset_ids)
    for eid, sig in svc_signals.items():
        bs = bulk_stats.setdefault(eid, {})
        bs["total_issues"] = (bs.get("total_issues") or 0) + sig["service_visits_12mo"]
        bs["open_issues"] = (bs.get("open_issues") or 0) + sig["open_service_cases"]

    results, summary, total_cost, forecast, by_type, by_location, by_priority = _aggregate_capex_results(
        equipment_list, bulk_stats, severity_lookup, selffix_lookup, thresholds, faults_by_eq
    )

    # Attach the SVC signal payload (+ BER computation) to each
    # equipment item. Done post-aggregation so we have the resolved
    # replacement_cost from `_compute_capex_score`.
    for item in results:
        sig = svc_signals.get(item["id"])
        if not sig:
            item["service_signals"] = {
                "service_visits_12mo": 0,
                "open_service_cases": 0,
                "service_spend_12mo": 0.0,
                "downtime_hours_12mo": 0.0,
                "last_service_at": None,
                **compute_repair_vs_replace(
                    service_spend_12mo=0.0,
                    replacement_cost=item.get("capex", {}).get("replacement_cost", 0),
                ),
            }
        else:
            item["service_signals"] = {
                "service_visits_12mo": sig["service_visits_12mo"],
                "open_service_cases": sig["open_service_cases"],
                "service_spend_12mo": sig["service_spend_12mo"],
                "downtime_hours_12mo": sig["downtime_hours_12mo"],
                "last_service_at": sig["last_service_at"],
                **compute_repair_vs_replace(
                    service_spend_12mo=sig["service_spend_12mo"],
                    replacement_cost=item.get("capex", {}).get("replacement_cost", 0),
                ),
            }

    priority_top5 = [r for r in results if r["capex"]["status"] in ("replace_now", "replace_soon", "at_risk")][:5]
    fleet = aggregate_fleet_intelligence(results)

    return {
        "equipment": results,
        "summary": summary,
        "total_replacement_cost_12m": total_cost,
        "forecast": {"next_3_months": forecast["3m"], "next_6_months": forecast["6m"], "next_12_months": forecast["12m"]},
        "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
        "by_location": dict(sorted(by_location.items(), key=lambda x: -x[1])),
        "by_priority": by_priority,
        "priority_replacements": [{
            "name": r["name"], "type": r["equipment_type"], "location": r["location"],
            "score": r["capex"]["score"], "status": r["capex"]["status_label"],
            "cost": r["capex"]["replacement_cost"], "action": r["capex"]["suggested_action"],
        } for r in priority_top5],
        "thresholds": thresholds,
        # Iter 216h127 — fleet-level board KPIs (lifecycle, condition,
        # safety, BER, ROI, priority matrix).
        "fleet_intelligence": fleet,
    }


@router.get("/capex/service-signals/{asset_id}")
async def get_asset_service_signals(
    asset_id: str,
    user: dict = Depends(get_current_user),
):
    """Iter 216h154 — drill-down for a single asset.

    Returns the 12-month service signals (visits, spend, downtime,
    BER ratio) plus a list of contributing case IDs so the asset
    detail drawer / board PDF can link straight to the source jobs.
    """
    _require_owner_or_manager(user)
    from utils.mod_scope import resolve_mod_query_filter
    from utils.svc_capex_signals import (
        aggregate_service_signals, compute_repair_vs_replace,
    )
    org_filter = await resolve_mod_query_filter(user, None)
    equip = await db.equipment.find_one(
        {**org_filter, "id": asset_id},
        {"_id": 0, "id": 1, "name": 1, "equipment_type": 1,
         "manufacturer": 1, "model": 1, "serial_number": 1,
         "replacement_cost": 1, "expected_lifespan_years": 1,
         "location": 1, "site_id": 1, "organization_id": 1},
    )
    if not equip:
        raise HTTPException(404, "Asset not found")
    profile = _get_profile(equip.get("equipment_type", ""))
    replacement_cost = equip.get("replacement_cost") or profile["cost"]
    signals_map = await aggregate_service_signals(
        org_filter, asset_ids=[asset_id],
    )
    sig = signals_map.get(asset_id, {
        "service_visits_12mo": 0,
        "open_service_cases": 0,
        "service_spend_12mo": 0.0,
        "downtime_hours_12mo": 0.0,
        "last_service_at": None,
        "case_ids": [],
    })
    ber = compute_repair_vs_replace(
        service_spend_12mo=sig["service_spend_12mo"],
        replacement_cost=replacement_cost,
    )
    return {
        "asset": equip,
        "replacement_cost": replacement_cost,
        "service_signals": {
            "service_visits_12mo": sig["service_visits_12mo"],
            "open_service_cases": sig["open_service_cases"],
            "service_spend_12mo": sig["service_spend_12mo"],
            "downtime_hours_12mo": sig["downtime_hours_12mo"],
            "last_service_at": sig["last_service_at"],
            **ber,
        },
        "case_ids": sig.get("case_ids", []),
    }


@router.get("/capex/ber-trend")
async def capex_ber_trend(
    user: dict = Depends(get_current_user),
    site_id: str = "",
):
    """Iter 216h162 — 6-month vs 12-month BER comparison.

    Returns fleet-level BER bucket distribution at both window
    horizons + a list of assets whose BER bucket has **moved**
    (improved or worsened) between the two windows. Used by the
    CAPEX dashboard to show longitudinal trend.

    Both windows share the same denominator (replacement cost), so
    the 6-month ratio is annualised (×2) to make them directly
    comparable — otherwise a 6-month sample would always look
    healthier just by virtue of having half the time to accumulate
    spend.
    """
    _require_owner_or_manager(user)
    from utils.mod_scope import resolve_mod_query_filter
    from utils.svc_capex_signals import (
        aggregate_service_signals, compute_repair_vs_replace,
    )
    org_filter = await resolve_mod_query_filter(user, site_id or None)
    equipment_list = await db.equipment.find(
        org_filter,
        {"_id": 0, "id": 1, "name": 1, "equipment_type": 1,
         "replacement_cost": 1, "location": 1},
    ).to_list(5000)
    if not equipment_list:
        return {
            "windows": {"6mo": {}, "12mo": {}},
            "movers": [], "totals": {"6mo": 0, "12mo": 0},
        }

    asset_ids = [e["id"] for e in equipment_list]
    # Parallel? not worth the orchestration cost — these are two short
    # Mongo finds against the same indexes.
    sigs_12 = await aggregate_service_signals(
        org_filter, asset_ids=asset_ids, window_days=365,
    )
    sigs_06 = await aggregate_service_signals(
        org_filter, asset_ids=asset_ids, window_days=180,
    )

    def _bucket_for(eid: str, sig_map: dict, *, annualise: bool) -> dict:
        equip = next((e for e in equipment_list if e["id"] == eid), {})
        replacement_cost = equip.get("replacement_cost") or 0
        sig = sig_map.get(eid) or {}
        spend = float(sig.get("service_spend_12mo") or 0)
        # Annualise 6-month spend so the BER ratio is comparable.
        eff_spend = spend * 2 if annualise else spend
        ber = compute_repair_vs_replace(
            service_spend_12mo=eff_spend,
            replacement_cost=replacement_cost,
        )
        return {
            "spend": spend, "annualised_spend": eff_spend,
            "ratio": ber["service_to_replacement_ratio"],
            "recommendation": ber["ber_recommendation"],
            "label": ber["ber_label"],
            "name": equip.get("name") or "(unnamed)",
            "location": equip.get("location") or "—",
            "equipment_type": equip.get("equipment_type") or "—",
            "replacement_cost": replacement_cost,
        }

    fleet = {"6mo": {"replace": 0, "watch": 0, "keep": 0, "insufficient_data": 0},
             "12mo": {"replace": 0, "watch": 0, "keep": 0, "insufficient_data": 0}}
    movers: list[dict] = []
    for eid in asset_ids:
        b12 = _bucket_for(eid, sigs_12, annualise=False)
        b06 = _bucket_for(eid, sigs_06, annualise=True)
        fleet["12mo"][b12["recommendation"]] = fleet["12mo"].get(b12["recommendation"], 0) + 1
        fleet["6mo"][b06["recommendation"]] = fleet["6mo"].get(b06["recommendation"], 0) + 1
        # A "mover" is an asset that has changed bucket OR that has
        # increased its BER ratio by at least 10 percentage points in
        # the 6m window (early warning signal).
        rank = {"keep": 0, "watch": 1, "replace": 2, "insufficient_data": -1}
        bucket_changed = rank[b06["recommendation"]] != rank[b12["recommendation"]]
        ratio_delta = (b06["ratio"] or 0) - (b12["ratio"] or 0)
        if bucket_changed or ratio_delta >= 0.10:
            movers.append({
                "id": eid,
                "name": b12["name"],
                "location": b12["location"],
                "equipment_type": b12["equipment_type"],
                "replacement_cost": b12["replacement_cost"],
                "from_recommendation": b12["recommendation"],
                "to_recommendation": b06["recommendation"],
                "ratio_12mo": b12["ratio"],
                "ratio_6mo": b06["ratio"],
                "ratio_delta": round(ratio_delta, 3),
                "spend_12mo": b12["spend"],
                "spend_6mo": b06["spend"],
                "direction": (
                    "worsening" if rank[b06["recommendation"]] > rank[b12["recommendation"]]
                    or ratio_delta > 0
                    else "improving"
                ),
            })

    # Sort movers — worst first.
    movers.sort(key=lambda m: (
        -(1 if m["direction"] == "worsening" else 0),
        -(m["ratio_delta"] or 0),
    ))
    return {
        "windows": fleet,
        "movers": movers[:30],
        "totals": {"6mo": len(asset_ids), "12mo": len(asset_ids)},
    }


def _build_flagged_equipment(
    equipment_list: list[dict],
    bulk_stats: dict,
    severity_lookup: dict,
    selffix_lookup: dict,
    thresholds: dict,
) -> list[dict]:
    """Identify equipment that needs CAPEX attention."""
    flagged = []
    for equip in equipment_list:
        eid = equip["id"]
        stats = bulk_stats.get(eid, {})
        sn = equip.get("serial_number", "") or equip.get("name", "")
        sev_data = severity_lookup.get(sn, {"critical": 0, "medium": 0, "low": 0})
        stats["critical_faults"] = sev_data.get("critical", 0)
        stats["self_fixes"] = selffix_lookup.get(sn, 0)
        capex = _compute_capex_score(equip, stats, thresholds)
        if capex["status"] in ("at_risk", "replace_soon", "replace_now"):
            flagged.append({"equip": equip, "stats": stats, "capex": capex})
    return flagged


def _format_equipment_summary(item: dict) -> str:
    """Format a single flagged equipment item for AI prompt."""
    e, c, s = item["equip"], item["capex"], item["stats"]
    return (
        f"- {e.get('name','Unknown')} ({e.get('equipment_type','')}, {e.get('manufacturer','')}) | "
        f"Age: {c.get('age_years','unknown')} yrs | Faults: {s.get('total_issues',0)} (open: {s.get('open_issues',0)}) | "
        f"Score: {c['score']}/100 ({c['status_label']}) | "
        f"Est. repair spend: £{c['estimated_repair_spend']} | Replacement: £{c['replacement_cost']} | "
        f"Warranty: {'Active' if s.get('warranty_active') else 'Expired'}"
    )


def _fallback_justifications(flagged: list[dict]) -> dict[str, str]:
    """Generate template justifications when AI fails."""
    justifications = {}
    for item in flagged:
        name = item["equip"].get("name", "Unknown")
        c, s = item["capex"], item["stats"]
        justifications[name] = (
            f"This equipment has a CAPEX score of {c['score']}/100 ({c['status_label']}). "
            f"With {s.get('total_issues', 0)} recorded faults and an estimated repair spend of £{c['estimated_repair_spend']}, "
            f"maintenance costs are approaching the replacement threshold of £{c['replacement_cost']}. "
            f"{c['suggested_action']}."
        )
    return justifications


def _build_justification_prompt(flagged: list[dict]) -> str:
    """Build the AI prompt for CAPEX justification generation."""
    summaries = [_format_equipment_summary(item) for item in flagged[:15]]
    return (
        "You are a professional gym equipment consultant writing CAPEX justifications "
        "for a facilities management report.\n\n"
        "For each of these flagged machines, write a professional 2-3 sentence justification "
        "explaining why it needs attention.\n"
        "The language should be suitable for board meetings, council submissions, and budget approvals.\n"
        "Be factual, reference the data provided, and recommend a clear action.\n\n"
        f"Flagged Equipment:\n{chr(10).join(summaries)}\n\n"
        "Return your response as a JSON object where keys are the equipment names "
        "and values are the justification text.\n"
        'Example: {"Treadmill 1": "This machine has shown...", "Rower 3": "With 8 faults..."}\n'
        "Return ONLY the JSON object, no markdown or other text."
    )


async def _call_ai_justifications(prompt: str, org_id: str | None, flagged: list[dict]) -> dict:
    """Send prompt to LLM and parse JSON response, falling back to templates on failure."""
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"capex-{org_id or 'default'}",
            system_message="You are a professional gym equipment CAPEX consultant.",
        ).with_model("openai", "gpt-5.2")
        response: str = await chat.send_message(UserMessage(text=prompt))

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as exc:
        logger.error("AI justification generation failed: %s", exc)
        return _fallback_justifications(flagged)


async def _save_justification_report(user: dict, justifications: dict) -> str:
    """Persist justifications to DB and return the report ID."""
    report_id = str(uuid.uuid4())
    await db.capex_justifications.update_one(
        {"organization_id": user.get("organization_id")},
        {"$set": {
            "organization_id": user.get("organization_id"),
            "justifications": justifications,
            "generated_by": user["id"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_id": report_id,
        }},
        upsert=True,
    )
    return report_id


@router.post("/capex/generate-justifications")
async def generate_capex_justifications(user: dict = Depends(get_current_user)) -> dict:
    """Generate AI justifications for all at-risk/replace equipment."""
    _require_owner_or_manager(user)
    org_filter = get_organization_filter(user)
    thresholds = await _get_thresholds(user.get("organization_id"))

    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(500)
    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)
    all_issues = await db.issues.find(
        org_filter,
        {"_id": 0, "serial_number": 1, "severity": 1, "resolution_type": 1, "resolved_by": 1},
    ).to_list(5000)

    severity_lookup, selffix_lookup = _build_severity_lookup(all_issues)
    flagged = _build_flagged_equipment(equipment_list, bulk_stats, severity_lookup, selffix_lookup, thresholds)
    if not flagged:
        return {"justifications": {}, "count": 0}

    prompt = _build_justification_prompt(flagged)
    justifications = await _call_ai_justifications(prompt, user.get("organization_id"), flagged)
    report_id = await _save_justification_report(user, justifications)
    return {"justifications": justifications, "count": len(justifications), "report_id": report_id}


@router.get("/capex/justifications")
async def get_saved_justifications(user: dict = Depends(get_current_user)) -> dict:
    _require_owner_or_manager(user)
    doc = await db.capex_justifications.find_one(
        {"organization_id": user.get("organization_id")}, {"_id": 0}
    )
    if not doc:
        return {"justifications": {}, "generated_at": None}
    return doc


@router.get("/capex/defaults")
async def get_capex_defaults(user: dict = Depends(get_current_user)) -> dict:
    """Get default equipment profiles and current thresholds."""
    _require_owner_or_manager(user)
    thresholds = await _get_thresholds(user.get("organization_id"))
    return {
        "equipment_profiles": DEFAULT_EQUIPMENT_PROFILES,
        "default_profile": DEFAULT_PROFILE,
        "thresholds": thresholds,
    }


@router.put("/capex/thresholds")
async def update_capex_thresholds(data: dict, user: dict = Depends(get_current_user)) -> dict:
    """Master admin or org owner can update CAPEX scoring thresholds."""
    if user.get("role") not in ("owner", "master_admin"):
        raise HTTPException(status_code=403, detail="Only owners and master admins can update thresholds")

    allowed_keys = set(DEFAULT_THRESHOLDS.keys())
    clean = {k: v for k, v in data.items() if k in allowed_keys and isinstance(v, (int, float))}
    if not clean:
        raise HTTPException(status_code=400, detail="No valid threshold keys provided")

    await db.capex_config.update_one(
        {"organization_id": user.get("organization_id")},
        {"$set": {
            "organization_id": user.get("organization_id"),
            "thresholds": clean,
            "updated_by": user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"success": True, "thresholds": {**DEFAULT_THRESHOLDS, **clean}}


@router.get("/capex/master-admin/overview")
async def master_admin_capex_overview(user: dict = Depends(get_current_user)) -> dict:
    """Master admin cross-org CAPEX view."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    overview = []
    for org in orgs:
        org_filter = {"organization_id": org["id"]}
        equip_count = await db.equipment.count_documents(org_filter)
        issue_count = await db.issues.count_documents(org_filter)
        overview.append({
            "org_id": org["id"],
            "org_name": org.get("name", "Unknown"),
            "equipment_count": equip_count,
            "total_faults": issue_count,
        })
    return {"organizations": overview}


# ─────────────────────────── Board CAPEX Report ──────────────────

_PLATFORM_ORG_NAMES = {"gymaxis ai", "gymaxis", "gymaxis ltd", "gymaxis limited"}


async def _resolve_capex_brand(user: dict) -> dict:
    """Resolve tenant brand for the CAPEX board PDF.

    Priority for company name:
      1. theme_overrides.tender_company_name (operator override)
      2. branding.company_name (legacy override)
      3. org.name (if not a platform org name)
      4. "Pulse Fitness" (CAPEX is Pulse-only feature)

    MOD HQ tenants (account_type mod_org/mod_branch/mod_site) get
    "Ministry of Defence" + neutral navy palette so the report is
    presentation-ready for DIO / Army review.
    """
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "name": 1, "branding": 1, "theme_overrides": 1, "account_type": 1,
         "is_mod": 1, "mod_force": 1},
    ) or {}
    overrides = org.get("theme_overrides") or {}
    branding = org.get("branding") or {}
    is_mod = (
        org.get("is_mod") is True
        or (user.get("account_type") in ("mod_site", "mod_branch", "mod_org"))
    )

    if is_mod:
        company = "Ministry of Defence"
        primary = "#0F2D52"  # Defence navy
    else:
        tender_company = (overrides.get("tender_company_name") or "").strip()
        legacy_company = (branding.get("company_name") or "").strip()
        raw_name = (org.get("name") or "").strip()
        if tender_company:
            company = tender_company
        elif legacy_company:
            company = legacy_company
        elif raw_name and raw_name.lower() not in _PLATFORM_ORG_NAMES:
            company = raw_name
        else:
            company = "Pulse Fitness"
        primary = (
            (overrides.get("tender_primary_color") or "").strip()
            or branding.get("primary_color")
            or "#19CDFF"
        )
    return {
        "company_name": company,
        "primary_color": primary,
        "logo_url": (
            (overrides.get("tender_logo_url") or "").strip()
            or branding.get("logo_url") or None
        ),
        "is_mod": is_mod,
    }


async def _build_board_report(user: dict, site_id: str | None) -> dict:
    """Run the CAPEX analysis and decorate with exec summary + scope label."""
    from utils.capex_intelligence import build_executive_summary
    base = await get_capex_analysis(user=user, site_id=site_id)
    fleet = base.get("fleet_intelligence") or {}
    exec_block = build_executive_summary(
        base.get("summary", {}), fleet,
        base.get("forecast", {}).get("next_12_months", 0),
    )
    # Scope label — site name when drilled in, else "All sites"
    scope_label = "All operations sites"
    if site_id:
        org = await db.organizations.find_one({"id": site_id}, {"_id": 0, "name": 1})
        site = await db.sites.find_one({"id": site_id}, {"_id": 0, "name": 1})
        scope_label = (org or site or {}).get("name") or "Selected site"
    return {
        **base,
        "executive_summary": exec_block,
        "scope_label": scope_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prepared_by": user.get("full_name") or user.get("email") or "Platform",
    }


@router.get("/capex/board-report")
async def get_capex_board_report(
    user: dict = Depends(get_current_user),
    site_id: str | None = None,
) -> dict:
    """Single endpoint returning the full board-ready CAPEX payload.

    Includes the per-asset intelligence layer, fleet-wide rollups, the
    priority matrix, exec summary + recommendations — all of which the
    PDF endpoint + the front-end dashboard consume.
    """
    _require_owner_or_manager(user)
    return await _build_board_report(user, site_id)


@router.get("/capex/board-report.pdf")
async def export_capex_board_pdf(
    user: dict = Depends(get_current_user),
    site_id: str | None = None,
):
    """Render the board CAPEX report as a tenant-branded PDF.

    Brand-aware: Pulse Fitness defaults; switches to a Ministry of
    Defence palette for MOD tenants; honours per-tenant
    `theme_overrides` for everyone else.
    """
    _require_owner_or_manager(user)
    from utils.capex_pdf_exporter import build_capex_board_pdf
    from utils.pdf_footer import is_mod_account_type
    report = await _build_board_report(user, site_id)
    brand = await _resolve_capex_brand(user)
    is_mod = is_mod_account_type(user.get("account_type"))
    pdf_bytes = build_capex_board_pdf(report, brand=brand, is_mod=is_mod)
    filename = f"capex-board-report-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

