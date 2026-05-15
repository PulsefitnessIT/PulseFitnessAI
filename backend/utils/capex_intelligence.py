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
        if value <= thresholds[0]: return 1
        if value <= thresholds[1]: return 2
        if value <= thresholds[2]: return 3
        if value <= thresholds[3]: return 4
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
        if ca >= cutoff_12: f12 += 1
        if ca >= cutoff_24: f24 += 1
        if ca >= cutoff_36: f36 += 1
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


__all__ = [
    "compute_lifecycle_stage",
    "compute_condition_scores",
    "compute_fault_history_breakdown",
    "compute_downtime_metrics",
    "compute_ber_flag",
    "compute_safety_risk",
    "compute_roi_estimate",
    "build_recommendation_detail",
]
