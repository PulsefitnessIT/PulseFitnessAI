from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter, apply_site_lock

logger = logging.getLogger(__name__)
router = APIRouter()

_RATING_THRESHOLDS: list[tuple[int, str, str]] = [
    (80, "Excellent", "#22c55e"),
    (60, "Good", "#84cc16"),
    (40, "Fair", "#eab308"),
    (20, "Needs Attention", "#f97316"),
    (0, "Critical", "#ef4444"),
]


def _score_fault_management(total_issues: int, open_issues: int) -> float:
    """Fault ratio score (max 30). Fewer open faults = higher."""
    if total_issues > 0:
        return max(0.0, 30 * (1 - open_issues / total_issues))
    return 30.0


def _score_self_fix(self_fixes: int, resolved_issues: int) -> float:
    """Self-fix rate score (max 20)."""
    if resolved_issues > 0:
        return 20 * (self_fixes / resolved_issues)
    return 10.0


async def _score_audit_coverage(total_equipment: int, org_filter: dict) -> float:
    """Audit coverage score (max 20)."""
    if total_equipment <= 0:
        return 10.0
    audited = len(await db.audits.distinct("equipment_id", org_filter))
    return 20 * min(1.0, audited / total_equipment)


def _score_warranty_health(total_equipment: int, expired_warranty: int) -> float:
    """Warranty health score (max 15)."""
    if total_equipment <= 0:
        return 15.0
    return 15 * (1 - expired_warranty / total_equipment)


def _determine_health_rating(score: int) -> tuple[str, str]:
    """Return (rating_label, hex_color) for a 0-100 score."""
    for threshold, label, color in _RATING_THRESHOLDS:
        if score >= threshold:
            return label, color
    return "Critical", "#ef4444"


async def _fetch_health_counts(org_filter: dict) -> dict:
    """Fetch all count-based metrics for health score."""
    total_equipment = await db.equipment.count_documents(org_filter)
    total_issues = await db.issues.count_documents(org_filter)
    open_issues = await db.issues.count_documents({**org_filter, "status": "open"})
    resolved_issues = await db.issues.count_documents({**org_filter, "status": "resolved"})
    self_fixes = await db.issues.count_documents({**org_filter, "resolution_type": "self_fix"})
    total_audits = await db.audits.count_documents(org_filter)
    fix_history_count = await db.fix_history.count_documents(org_filter)
    now_iso = datetime.now(timezone.utc).isoformat()[:10]
    equipment_list = await db.equipment.find(org_filter, {"_id": 0, "warranty_expiry": 1}).to_list(500)
    expired_warranty = sum(1 for eq in equipment_list if (eq.get("warranty_expiry") or "") < now_iso and eq.get("warranty_expiry"))
    return {
        "total_equipment": total_equipment, "total_issues": total_issues,
        "open_issues": open_issues, "resolved_issues": resolved_issues,
        "self_fixes": self_fixes, "total_audits": total_audits,
        "fix_history_count": fix_history_count, "expired_warranty": expired_warranty,
    }


@router.get("/gym-health-score")
async def get_gym_health_score(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h65 — `site_id` query param scopes the score to a
    single site. Omitting it = aggregate across the org (used when
    SiteSwitcher = All Operations Sites)."""
    org_filter = get_organization_filter(user)
    org_filter = apply_site_lock(user, site_id, org_filter)
    c = await _fetch_health_counts(org_filter)

    # Not-ready state: no equipment onboarded AND no faults logged.
    # A Gym Health Score is only meaningful once the user has started onboarding
    # (added equipment) or used the system (logged faults/audits). Returning a
    # default score based on empty data misleads customers with a "65 / Good"
    # score on day one.
    if c["total_equipment"] == 0 and c["total_issues"] == 0 and c["total_audits"] == 0:
        return {
            "not_ready": True,
            "reason": "onboarding_incomplete",
            "message": "Your Gym Health Score will be calculated once you've added equipment and started logging activity.",
            "stats": {
                "total_equipment": 0, "open_issues": 0, "resolved_issues": 0,
                "self_fixes": 0, "total_audits": 0, "fix_history_count": 0,
            },
        }

    fault_score = _score_fault_management(c["total_issues"], c["open_issues"])
    selffix_score = _score_self_fix(c["self_fixes"], c["resolved_issues"])
    audit_score = await _score_audit_coverage(c["total_equipment"], org_filter)
    warranty_score = _score_warranty_health(c["total_equipment"], c["expired_warranty"])
    knowledge_score = min(15.0, c["fix_history_count"] * 3)

    total_score = max(0, min(100, round(fault_score + selffix_score + audit_score + warranty_score + knowledge_score)))
    rating, color = _determine_health_rating(total_score)

    return {
        "score": total_score, "rating": rating, "color": color,
        "breakdown": {
            "fault_management": {"score": round(fault_score), "max": 30, "detail": f"{c['open_issues']} open / {c['total_issues']} total faults"},
            "self_fix_rate": {"score": round(selffix_score), "max": 20, "detail": f"{c['self_fixes']} self-fixed / {c['resolved_issues']} resolved"},
            "audit_coverage": {"score": round(audit_score), "max": 20, "detail": f"{c['total_audits']} audits across {c['total_equipment']} equipment"},
            "warranty_health": {"score": round(warranty_score), "max": 15, "detail": f"{c['expired_warranty']} expired warranties"},
            "ai_knowledge": {"score": round(knowledge_score), "max": 15, "detail": f"{c['fix_history_count']} proven fixes in knowledge base"},
        },
        "stats": {
            "total_equipment": c["total_equipment"], "open_issues": c["open_issues"],
            "resolved_issues": c["resolved_issues"], "self_fixes": c["self_fixes"],
            "total_audits": c["total_audits"], "fix_history_count": c["fix_history_count"],
        },
    }
