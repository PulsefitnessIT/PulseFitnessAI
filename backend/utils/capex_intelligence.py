"""Iter 216h127 — CAPEX intelligence layer.

Extends the existing `routes/capex.py` scoring engine with the
data points Jack's "best-in-class CAPEX intelligence" brief asks
for. NEVER duplicates existing logic — these helpers consume the
records the legacy scoring already loaded and decorate them with
extra signals.

Each helper returns plain dicts and is pure-functional (no DB
calls) so the existing `_aggregate_capex_results` orchestrator
can stay in charge.

Public API:
  • compute_lifecycle_stage(age_years, expected_lifespan)
  • compute_condition_scores(equip_stats, severity_counts)
  • compute_fault_history_breakdown(faults_for_asset, now_dt)
  • compute_downtime_metrics(faults_for_asset, now_dt)
  • compute_ber_flag(estimated_repair_spend, replacement_cost)
  • compute_safety_risk(severity_counts, faults_for_asset)
  • compute_roi_estimate(repair_spend_12m, replacement_cost,
                        expected_lifespan_years, downtime_days)
  • build_recommendation_detail(asset_summary, lifecycle_stage,
                                safety_risk, ber_flag, condition_score)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ─────────────────────── Asset valuation / depreciation ─────────

# Commercial gym equipment retains a residual/salvage floor at the end
# of its expected life (parts, frame, resale). 10% is a conservative
# industry default; overridable per-org via capex_config later.
RESIDUAL_FLOOR_PCT = 0.10

# Referral target for sourcing replacements / trading in retired kit.
# We deliberately do NOT run our own marketplace — we hand off to Pulse
# Resale. No inventory, no listings held in-platform.
PULSE_RESALE_URL = "https://pulseresale.com/"


def compute_valuation(acquisition_cost: float | None, age_years: float | None,
                      expected_lifespan_years: float | None, replacement_cost: float | None,
                      residual_floor_pct: float = RESIDUAL_FLOOR_PCT) -> dict:
    """Straight-line depreciation → current book / residual value.

    Uses the asset's real `purchase_cost` when available; falls back to
    `replacement_cost` as an estimated acquisition basis (flagged via
    `basis`). Never duplicates the CAPEX replacement-cost logic — this
    is the *backward-looking* value of the asset you already own, the
    piece Orbit4 leads on that the scoring engine didn't cover.
    """
    basis = "actual"
    acq = acquisition_cost
    if not acq or acq <= 0:
        acq = replacement_cost or 0
        basis = "estimated"
    if not acq or acq <= 0:
        return {"available": False}
    life = expected_lifespan_years or 8
    age = max(0.0, age_years or 0)
    salvage = round(acq * residual_floor_pct, 2)
    annual_dep = round((acq - salvage) / life, 2) if life > 0 else 0.0
    accumulated = min(annual_dep * age, acq - salvage)
    book = round(max(salvage, acq - accumulated), 2)
    return {
        "available": True,
        "basis": basis,
        "acquisition_cost": round(acq, 2),
        "salvage_value": salvage,
        "annual_depreciation": annual_dep,
        "accumulated_depreciation": round(accumulated, 2),
        "current_book_value": book,
        "residual_value_pct": round(100 * book / acq, 1) if acq else None,
        "depreciation_method": "straight_line",
        "expected_lifespan_years": life,
    }


def compute_tco(acquisition_cost: float | None, replacement_cost: float | None,
                service_spend_12mo: float | None, age_years: float | None,
                valuation: dict | None = None) -> dict:
    """Total cost of ownership = acquisition + lifetime service/parts spend.

    Lifetime service is estimated from the live 12-month service spend
    (from `svc_capex_signals`) projected across the asset's age — our
    unfair advantage over a valuation-only competitor, since we hold the
    real service history.
    """
    acq = (valuation or {}).get("acquisition_cost") or acquisition_cost or replacement_cost or 0
    age = max(0.0, age_years or 0)
    annual_service = float(service_spend_12mo or 0)
    lifetime_service = round(annual_service * max(age, 1.0), 2)
    total = round(acq + lifetime_service, 2)
    tco_per_year = round(total / age, 2) if age >= 1 else total
    return {
        "acquisition_cost": round(acq, 2),
        "annual_service_spend": round(annual_service, 2),
        "estimated_lifetime_service_spend": lifetime_service,
        "total_cost_of_ownership": total,
        "tco_per_year": tco_per_year,
        "service_pct_of_tco": round(100 * lifetime_service / total, 1) if total else 0.0,
        "basis": "estimated",
    }


def build_resale_referral(equipment_type: str | None, manufacturer: str | None,
                          status: str, lifecycle_stage: str | None,
                          valuation: dict | None) -> dict | None:
    """For assets flagged for replacement, hand off to Pulse Resale for
    sourcing a replacement or trading in the retired unit. Returns None
    for healthy assets (no referral needed). No marketplace held here."""
    if status not in ("replace_now", "replace_soon", "at_risk"):
        return None
    from urllib.parse import urlencode
    params = {}
    if equipment_type:
        params["category"] = equipment_type
    if manufacturer:
        params["brand"] = manufacturer
    query = ("?" + urlencode(params)) if params else ""
    residual = (valuation or {}).get("current_book_value") if valuation and valuation.get("available") else None
    return {
        "url": PULSE_RESALE_URL + query,
        "label": "Source replacement or trade-in via Pulse Resale",
        "estimated_residual_value": residual,
        "sweet_spot": lifecycle_stage in ("Ageing", "End-of-life"),
    }


# ─────────────────────── Lifecycle stage ────────────────────────

def compute_lifecycle_stage(age_years: float | None, expected_lifespan: float | None) -> dict:
    """Return {stage, remaining_years, stage_color}.

    Stage bands:
      • New          (<= 25% of expected life)
      • Mid-life     (25%-65%)
      • Ageing       (65%-95%)
      • End-of-life  (95%-120%)
      • Unsupported  (>120%)
    """
    if age_years is None or expected_lifespan is None or expected_lifespan <= 0:
        return {"stage": "Unknown", "remaining_years": None, "ratio_pct": None, "color": "neutral"}
    ratio = age_years / expected_lifespan
    if ratio <= 0.25:
        stage, color = "New", "emerald"
    elif ratio <= 0.65:
        stage, color = "Mid-life", "cyan"
    elif ratio <= 0.95:
        stage, color = "Ageing", "amber"
    elif ratio <= 1.20:
        stage, color = "End-of-life", "orange"
    else:
        stage, color = "Unsupported", "red"
    return {
        "stage": stage,
        "remaining_years": round(max(0.0, expected_lifespan - age_years), 1),
        "ratio_pct": round(ratio * 100, 1),
        "color": color,
    }


# ─────────────────────── Condition scoring ──────────────────────

def compute_condition_scores(stats: dict, severity_counts: dict, age_years: float | None,
                             expected_lifespan: float | None) -> dict:
    """Derive 1-5 condition scores per facet from fault history.

    1 = Excellent · 2 = Good · 3 = Fair · 4 = Poor · 5 = Critical
    """
    critical = severity_counts.get("critical", 0)
    medium = severity_counts.get("medium", 0)
    open_faults = stats.get("open_issues", 0)
    total_faults = stats.get("total_issues", 0)
    age_ratio = (age_years / expected_lifespan) if (age_years and expected_lifespan) else 0

    def _band(value: int, thresholds=(0, 1, 3, 6)) -> int:
        # 1..5 from increasing fault counts.
        if value <= thresholds[0]:
            return 1
        if value <= thresholds[1]:
            return 2
        if value <= thresholds[2]:
            return 3
        if value <= thresholds[3]:
            return 4
        return 5

    # Mechanical: weighted by total faults + open faults.
    mechanical = min(5, max(_band(total_faults), _band(open_faults * 2, (0, 1, 2, 4))))
    # Electronics — proxy from critical-severity count
    electronics = _band(critical, (0, 0, 1, 3))
    # Frame/structural — age + critical
    if age_ratio >= 1.0:
        frame = 5 if critical else 4
    elif age_ratio >= 0.7:
        frame = 4 if critical else 3
    elif age_ratio >= 0.4:
        frame = 3 if critical else 2
    else:
        frame = 2 if critical else 1
    # Upholstery — age-driven only (no field data yet)
    upholstery = 5 if age_ratio >= 1.0 else 4 if age_ratio >= 0.75 else 3 if age_ratio >= 0.5 else 2 if age_ratio >= 0.25 else 1
    # Safety — any critical fault = 4-5, otherwise mostly 1-2
    safety = 5 if critical >= 2 else 4 if critical == 1 else 2 if medium >= 3 else 1
    overall = round((mechanical + electronics + frame + upholstery + safety) / 5)

    return {
        "mechanical": mechanical, "electronics": electronics,
        "frame": frame, "upholstery": upholstery, "safety": safety,
        "overall": overall,
    }


# ─────────────────────── Fault history breakdown ────────────────

def compute_fault_history_breakdown(faults: list[dict], now_dt: datetime) -> dict:
    """Counts of faults within rolling 12 / 24 / 36 month windows."""
    cutoff_12 = now_dt - timedelta(days=365)
    cutoff_24 = now_dt - timedelta(days=365 * 2)
    cutoff_36 = now_dt - timedelta(days=365 * 3)
    f12 = f24 = f36 = 0
    repeat_descs: dict[str, int] = {}
    safety_critical = 0
    unresolved = 0
    for f in faults:
        try:
            ca = datetime.fromisoformat(str(f.get("created_at", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ca >= cutoff_12:
            f12 += 1
        if ca >= cutoff_24:
            f24 += 1
        if ca >= cutoff_36:
            f36 += 1
        desc = (f.get("issue_description") or "").strip().lower()[:80]
        if desc:
            repeat_descs[desc] = repeat_descs.get(desc, 0) + 1
        sev = (f.get("severity") or "").lower()
        if sev in ("critical", "urgent"):
            safety_critical += 1
        if f.get("status") not in ("resolved", "closed"):
            unresolved += 1
    repeat_count = sum(1 for c in repeat_descs.values() if c >= 2)
    return {
        "last_12_months": f12, "last_24_months": f24, "last_36_months": f36,
        "repeat_faults": repeat_count,
        "safety_critical_faults": safety_critical,
        "unresolved_faults": unresolved,
    }


# ─────────────────────── Downtime ───────────────────────────────

def compute_downtime_metrics(faults: list[dict], now_dt: datetime) -> dict:
    """Aggregate downtime from each fault's open → resolved window.

    For unresolved faults we accumulate the time since `created_at`
    (still down today).
    """
    total_hours = 0.0
    fault_count = 0
    longest_outage_hours = 0.0
    last_incident_at: datetime | None = None
    for f in faults:
        try:
            ca = datetime.fromisoformat(str(f.get("created_at", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        last_incident_at = ca if not last_incident_at or ca > last_incident_at else last_incident_at
        resolved = None
        if f.get("status") in ("resolved", "closed"):
            try:
                resolved = datetime.fromisoformat(
                    str(f.get("resolved_at") or f.get("updated_at") or "").replace("Z", "+00:00"),
                )
            except (ValueError, TypeError):
                resolved = None
        end = resolved or now_dt
        hours = max(0.0, (end - ca).total_seconds() / 3600)
        total_hours += hours
        longest_outage_hours = max(longest_outage_hours, hours)
        fault_count += 1
    total_days_oos = total_hours / 24
    # Assume 24h/day availability for a 365-day window.
    availability_pct = max(0.0, min(100.0, 100 - (total_hours / (365 * 24)) * 100))
    return {
        "total_days_oos": round(total_days_oos, 1),
        "total_hours": round(total_hours, 1),
        "longest_outage_hours": round(longest_outage_hours, 1),
        "availability_pct": round(availability_pct, 2),
        "fault_count": fault_count,
        "days_since_last_incident": (
            (now_dt - last_incident_at).days if last_incident_at else None
        ),
    }


# ─────────────────────── Beyond Economic Repair ─────────────────

def compute_ber_flag(estimated_repair_spend: float, replacement_cost: float) -> dict:
    """Beyond-Economic-Repair classification.

    Returns ``{ratio, status, message}`` where status is:
      • ok                  (<25% of replacement)
      • monitor             (25-39%)
      • replacement_review  (40-59%)  → Jack's 40% threshold
      • recommend_replace   (>=60%)   → Jack's 60% threshold
    """
    if not replacement_cost or replacement_cost <= 0:
        return {"ratio_pct": None, "status": "unknown", "message": "Replacement cost not set"}
    ratio = (estimated_repair_spend or 0) / replacement_cost
    pct = round(ratio * 100, 1)
    if ratio >= 0.60:
        status, msg = "recommend_replace", "Repair spend ≥60% of replacement cost — replace"
    elif ratio >= 0.40:
        status, msg = "replacement_review", "Repair spend ≥40% of replacement cost — review"
    elif ratio >= 0.25:
        status, msg = "monitor", "Repair spend ≥25% — monitor closely"
    else:
        status, msg = "ok", "Repair spend within healthy band"
    return {"ratio_pct": pct, "status": status, "message": msg}


# ─────────────────────── Safety risk ────────────────────────────

def compute_safety_risk(severity_counts: dict, fault_breakdown: dict) -> dict:
    critical = severity_counts.get("critical", 0)
    safety_critical = fault_breakdown.get("safety_critical_faults", 0)
    if critical >= 2 or safety_critical >= 3:
        return {"level": "high", "score": 5, "immediate_action": True,
                "message": "Multiple safety-critical faults — withdraw from service"}
    if critical == 1 or safety_critical >= 1:
        return {"level": "elevated", "score": 4, "immediate_action": True,
                "message": "Safety-critical fault on record — inspect before next use"}
    if fault_breakdown.get("unresolved_faults", 0) >= 3:
        return {"level": "moderate", "score": 3, "immediate_action": False,
                "message": "Multiple open faults — schedule engineer visit"}
    return {"level": "low", "score": 1, "immediate_action": False,
            "message": "No safety concerns on record"}


# ─────────────────────── ROI / Business case ────────────────────

def compute_roi_estimate(repair_spend_12m: float, replacement_cost: float,
                         expected_lifespan_years: float, downtime_days: float) -> dict:
    """Crude ROI / payback estimate.

    Saving = projected repair spend over the remainder of expected
    life + estimated downtime revenue protection (£200/day downtime).
    Payback = replacement_cost / annual_saving (months).
    """
    if not replacement_cost or replacement_cost <= 0:
        return {"annual_saving": None, "payback_months": None, "lifetime_saving": None}
    annual_repair_avoid = max(0.0, repair_spend_12m * 0.7)   # 70% of current cost avoided
    annual_downtime_value = (downtime_days or 0) * 200
    annual_saving = round(annual_repair_avoid + annual_downtime_value, 2)
    payback_months = round((replacement_cost / annual_saving) * 12, 1) if annual_saving > 0 else None
    lifetime_saving = round(annual_saving * (expected_lifespan_years or 8), 2)
    return {
        "annual_saving": annual_saving,
        "annual_repair_avoid": round(annual_repair_avoid, 2),
        "annual_downtime_value": round(annual_downtime_value, 2),
        "payback_months": payback_months,
        "lifetime_saving": lifetime_saving,
    }


# ─────────────────────── Recommendation detail ──────────────────

def build_recommendation_detail(*, status: str, lifecycle_stage: dict, safety_risk: dict,
                                ber_flag: dict, condition: dict, age_years: float | None,
                                expected_lifespan_years: float | None) -> dict:
    reasons = []
    if status in ("replace_now", "replace_soon"):
        reasons.append("High CAPEX priority score")
    if lifecycle_stage.get("stage") in ("End-of-life", "Unsupported"):
        reasons.append(f"Lifecycle stage = {lifecycle_stage['stage']}")
    if safety_risk.get("level") in ("elevated", "high"):
        reasons.append(safety_risk["message"])
    if ber_flag.get("status") in ("recommend_replace", "replacement_review"):
        reasons.append(ber_flag["message"])
    if condition.get("overall", 0) >= 4:
        reasons.append(f"Overall condition score {condition['overall']}/5")
    if age_years and expected_lifespan_years and age_years > expected_lifespan_years:
        reasons.append(f"Age {age_years}yr > expected life {expected_lifespan_years}yr")

    action_map = {
        "replace_now":   ("Replace immediately",        "high"),
        "replace_soon":  ("Replace within 6-12 months", "elevated"),
        "at_risk":       ("Monitor weekly · book inspection", "moderate"),
        "monitor":       ("Monitor monthly",            "low"),
        "healthy":       ("Continue using — no action needed", "none"),
    }
    action, urgency = action_map.get(status, ("Review manually", "moderate"))
    if not reasons:
        reasons.append("No critical signals — continue using.")
    return {
        "action": action,
        "urgency": urgency,
        "reasons": reasons,
        "operational_impact": (
            "Plan downtime swap" if status in ("replace_now", "replace_soon")
            else "Minimal operational impact" if status == "healthy"
            else "Schedule inspection during quiet hours"
        ),
    }


# ─────────────────────── Fleet-level aggregator ──────────────────

LIFECYCLE_BUCKETS = ("New", "Mid-life", "Ageing", "End-of-life", "Unsupported", "Unknown")
SAFETY_BUCKETS = ("low", "moderate", "elevated", "high")
CONDITION_BUCKETS = ("1", "2", "3", "4", "5")
BER_BUCKETS = ("ok", "monitor", "replacement_review", "recommend_replace", "unknown")


def aggregate_fleet_intelligence(results: list[dict]) -> dict:
    """Roll up per-asset intelligence into board-level KPIs.

    Consumes the dicts produced by ``_build_capex_result_item``
    (each carries lifecycle_stage, condition_scores, fault_history,
    downtime, ber_flag, safety_risk, roi_estimate, recommendation).
    Returns:
      • lifecycle_distribution    {stage: count}
      • condition_distribution    {"1": n, ..., "5": n} + average
      • safety_distribution       {level: count}
      • ber_distribution          {status: count}
      • fleet_kpis (totals)       availability %, total OOS days,
                                  immediate_action assets, beyond-economic-
                                  repair count, est. lifetime saving.
      • priority_matrix           per-asset (safety_score, lifecycle_pct,
                                  replacement_cost, status) — for the
                                  bubble-chart on the front-end.
      • spend_forecast            cumulative spend in 3/6/12 month
                                  buckets broken down by priority.
    """
    if not results:
        return {
            "lifecycle_distribution": {b: 0 for b in LIFECYCLE_BUCKETS},
            "condition_distribution": {b: 0 for b in CONDITION_BUCKETS},
            "condition_average": None,
            "safety_distribution": {b: 0 for b in SAFETY_BUCKETS},
            "ber_distribution": {b: 0 for b in BER_BUCKETS},
            "fleet_kpis": {
                "total_assets": 0, "immediate_action_assets": 0,
                "beyond_economic_repair_count": 0,
                "fleet_availability_pct": None,
                "total_days_oos": 0, "total_downtime_hours": 0,
                "estimated_lifetime_saving": 0,
                "total_replacement_cost_full_fleet": 0,
                "average_age_years": None,
                "total_current_book_value": 0,
                "total_acquisition_cost": 0,
                "total_cost_of_ownership": 0,
            },
            "priority_matrix": [],
        }

    lifecycle = {b: 0 for b in LIFECYCLE_BUCKETS}
    condition = {b: 0 for b in CONDITION_BUCKETS}
    safety = {b: 0 for b in SAFETY_BUCKETS}
    ber = {b: 0 for b in BER_BUCKETS}

    immediate = 0
    ber_count = 0
    total_oos_days = 0.0
    total_hours = 0.0
    availability_weighted = 0.0  # sum of per-asset availability
    availability_n = 0
    lifetime_saving = 0.0
    total_replacement = 0
    condition_sum = 0
    age_sum = 0.0
    age_n = 0
    total_book_value = 0.0
    total_acquisition = 0.0
    total_tco = 0.0
    matrix: list[dict] = []

    for r in results:
        ls = (r.get("lifecycle_stage") or {}).get("stage", "Unknown")
        lifecycle[ls] = lifecycle.get(ls, 0) + 1

        cond = (r.get("condition_scores") or {}).get("overall")
        if cond:
            condition[str(cond)] = condition.get(str(cond), 0) + 1
            condition_sum += cond

        sl = (r.get("safety_risk") or {}).get("level", "low")
        safety[sl] = safety.get(sl, 0) + 1
        if (r.get("safety_risk") or {}).get("immediate_action"):
            immediate += 1

        bs = (r.get("ber_flag") or {}).get("status", "unknown")
        ber[bs] = ber.get(bs, 0) + 1
        if bs == "recommend_replace":
            ber_count += 1

        dt = r.get("downtime") or {}
        total_oos_days += dt.get("total_days_oos") or 0
        total_hours += dt.get("total_hours") or 0
        if dt.get("availability_pct") is not None:
            availability_weighted += dt["availability_pct"]
            availability_n += 1

        roi = r.get("roi_estimate") or {}
        lifetime_saving += roi.get("lifetime_saving") or 0

        capex = r.get("capex") or {}
        total_replacement += capex.get("replacement_cost") or 0

        if capex.get("age_years") is not None:
            age_sum += capex["age_years"]
            age_n += 1

        val = r.get("valuation") or {}
        if val.get("available"):
            total_book_value += val.get("current_book_value") or 0
            total_acquisition += val.get("acquisition_cost") or 0
        tco = r.get("tco") or {}
        total_tco += tco.get("total_cost_of_ownership") or 0

        # Priority-matrix datapoint:
        matrix.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "equipment_type": r.get("equipment_type"),
            "location": r.get("location"),
            "safety_score": (r.get("safety_risk") or {}).get("score", 1),
            "lifecycle_pct": (r.get("lifecycle_stage") or {}).get("ratio_pct") or 0,
            "condition_overall": cond,
            "capex_score": capex.get("score", 0),
            "replacement_cost": capex.get("replacement_cost", 0),
            "status": capex.get("status", "monitor"),
            "ber_status": bs,
        })

    fleet_availability = round(availability_weighted / availability_n, 2) if availability_n else None
    cond_avg = round(condition_sum / max(1, sum(condition.values())), 2) if any(condition.values()) else None

    return {
        "lifecycle_distribution": lifecycle,
        "condition_distribution": condition,
        "condition_average": cond_avg,
        "safety_distribution": safety,
        "ber_distribution": ber,
        "fleet_kpis": {
            "total_assets": len(results),
            "immediate_action_assets": immediate,
            "beyond_economic_repair_count": ber_count,
            "fleet_availability_pct": fleet_availability,
            "total_days_oos": round(total_oos_days, 1),
            "total_downtime_hours": round(total_hours, 1),
            "estimated_lifetime_saving": round(lifetime_saving, 2),
            "total_replacement_cost_full_fleet": total_replacement,
            "average_age_years": round(age_sum / age_n, 1) if age_n else None,
            "total_current_book_value": round(total_book_value, 2),
            "total_acquisition_cost": round(total_acquisition, 2),
            "total_cost_of_ownership": round(total_tco, 2),
        },
        "priority_matrix": matrix,
    }


def build_executive_summary(summary: dict, fleet: dict, forecast_12m: int) -> dict:
    """Return a structured exec-summary block for the board report."""
    total = summary.get("total", 0) or 1
    flagged = (summary.get("replace_now", 0) + summary.get("replace_soon", 0)
               + summary.get("at_risk", 0))
    headline = (
        f"{flagged} of {total} assets ({round(100 * flagged / total)}%) require attention. "
        f"Estimated 12-month replacement spend: £{forecast_12m:,}."
    )
    kpis = fleet.get("fleet_kpis", {})
    bullets = [
        f"Fleet availability: {kpis.get('fleet_availability_pct') or '—'}%",
        f"Assets needing immediate action: {kpis.get('immediate_action_assets', 0)}",
        f"Beyond Economic Repair: {kpis.get('beyond_economic_repair_count', 0)} machines",
        f"Avg condition score: {fleet.get('condition_average') or '—'}/5",
        f"Total downtime (12m): {kpis.get('total_days_oos', 0)} days",
    ]
    return {
        "headline": headline,
        "bullets": bullets,
        "recommended_action": _exec_action(flagged, kpis),
    }


def _exec_action(flagged: int, kpis: dict) -> str:
    if kpis.get("immediate_action_assets", 0) > 0:
        return "Authorise immediate withdrawal-from-service for safety-critical assets and approve emergency CAPEX release."
    if kpis.get("beyond_economic_repair_count", 0) >= 3:
        return "Approve replacement CAPEX for Beyond Economic Repair (BER) assets at next budget cycle."
    if flagged >= 5:
        return "Schedule replacement review for flagged machines within the next 6-12 month rolling budget."
    return "Maintain current PPM cadence; no immediate CAPEX release required."


__all__ = [
    "compute_lifecycle_stage",
    "compute_condition_scores",
    "compute_fault_history_breakdown",
    "compute_downtime_metrics",
    "compute_ber_flag",
    "compute_safety_risk",
    "compute_roi_estimate",
    "compute_valuation",
    "compute_tco",
    "build_resale_referral",
    "build_recommendation_detail",
    "aggregate_fleet_intelligence",
    "build_executive_summary",
    "LIFECYCLE_BUCKETS",
    "CONDITION_BUCKETS",
    "SAFETY_BUCKETS",
    "BER_BUCKETS",
]
