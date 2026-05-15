from fastapi import APIRouter, Depends, HTTPException
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


def _build_capex_result_item(equip: dict, stats: dict, capex: dict) -> dict:
    """Build a single result dict for the CAPEX response."""
    return {
        "id": equip["id"], "name": equip.get("name", "Unknown"),
        "equipment_type": equip.get("equipment_type", "Unknown"),
        "manufacturer": equip.get("manufacturer", ""), "model": equip.get("model", ""),
        "serial_number": equip.get("serial_number", ""),
        "location": equip.get("location", "Unassigned") or "Unassigned",
        "purchase_date": equip.get("purchase_date"), "warranty_expiry": equip.get("warranty_expiry"),
        "total_faults": stats.get("total_issues", 0), "open_faults": stats.get("open_issues", 0),
        "days_in_service": stats.get("days_in_service"),
        "warranty_active": stats.get("warranty_active", False),
        "capex": capex,
    }


def _aggregate_capex_results(
    equipment_list: list[dict],
    bulk_stats: dict,
    severity_lookup: dict,
    selffix_lookup: dict,
    thresholds: dict,
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
        results.append(_build_capex_result_item(equip, stats, capex))

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
    org_filter = await resolve_mod_query_filter(user, site_id)
    thresholds = await _get_thresholds(user.get("organization_id"))

    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(5000)
    if not equipment_list:
        return {"equipment": [], "summary": {"total": 0}, "forecast": {}}

    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)
    all_issues = await db.issues.find(org_filter, {"_id": 0, "serial_number": 1, "severity": 1, "resolution_type": 1, "resolved_by": 1, "organization_id": 1}).to_list(20000)

    severity_lookup, selffix_lookup = _build_severity_lookup(all_issues)
    results, summary, total_cost, forecast, by_type, by_location, by_priority = _aggregate_capex_results(
        equipment_list, bulk_stats, severity_lookup, selffix_lookup, thresholds
    )

    priority_top5 = [r for r in results if r["capex"]["status"] in ("replace_now", "replace_soon", "at_risk")][:5]

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
