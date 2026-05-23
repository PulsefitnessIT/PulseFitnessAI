from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
import logging

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

_RATING_THRESHOLDS: list[tuple[int, str, str]] = [
    (80, "Excellent", "#22c55e"),
    (60, "Good", "#84cc16"),
    (40, "Fair", "#eab308"),
    (20, "Needs Attention", "#f97316"),
    (0, "Critical", "#ef4444"),
]


# ─── Iter 217 — re-weighted to fit two new metrics ────────────────
# Old totals (5 metrics → 100):  30 + 20 + 20 + 15 + 15
# New totals (7 metrics → 100):  20 + 10 + 15 + 15 + 10 + 15 + 15
#   fault_management (20)   fault_freshness (10, NEW)   self_fix (15)
#   audit_coverage (15)     warranty_health (10)
#   sla_adherence (15, NEW) ai_knowledge (15)


def _score_fault_management(total_issues: int, open_issues: int) -> float:
    """Open/total ratio — measures backlog. Max 20."""
    if total_issues > 0:
        return max(0.0, 20 * (1 - open_issues / total_issues))
    return 20.0


async def _score_fault_freshness(org_filter: dict) -> tuple[float, str]:
    """Iter 217 — median age of currently-open faults. Captures
    "how stale is the backlog" which the simple open/total ratio
    can't see. Max 10. 0 days → 10, ≥30 days → 0.
    """
    cur = db.issues.find({**org_filter, "status": {"$nin": ["closed", "resolved"]}},
                          {"created_at": 1, "_id": 0})
    now = datetime.now(timezone.utc)
    ages: list[float] = []
    async for d in cur:
        created = d.get("created_at")
        if not created:
            continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        ages.append((now - created).total_seconds() / 86400.0)
    if not ages:
        return 10.0, "no open faults"
    ages.sort()
    mid = len(ages) // 2
    median = ages[mid] if len(ages) % 2 else (ages[mid - 1] + ages[mid]) / 2
    score = max(0.0, 10 * (1 - median / 30.0))
    return score, f"{len(ages)} open · median {round(median, 1)}d"


def _score_self_fix(self_fixes: int, resolved_issues: int) -> float:
    """Self-fix rate score (max 15)."""
    if resolved_issues > 0:
        return 15 * (self_fixes / resolved_issues)
    return 7.5


async def _score_audit_coverage(total_equipment: int, org_filter: dict) -> float:
    """Audit coverage score (max 15)."""
    if total_equipment <= 0:
        return 7.5
    audited = len(await db.audits.distinct("equipment_id", org_filter))
    return 15 * min(1.0, audited / total_equipment)


def _score_warranty_health(total_equipment: int, expired_warranty: int) -> float:
    """Warranty health score (max 10)."""
    if total_equipment <= 0:
        return 10.0
    return 10 * (1 - expired_warranty / total_equipment)


async def _score_sla_adherence(org_filter: dict) -> tuple[float, str]:
    """Iter 217 — % of issues created in the last 30 days that were
    acknowledged within 24h. Max 15."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    cur = db.issues.find({**org_filter, "created_at": {"$gte": since}},
                          {"created_at": 1, "acknowledged_at": 1, "_id": 0})
    total = 0
    on_time = 0
    async for d in cur:
        total += 1
        ack = d.get("acknowledged_at")
        created = d.get("created_at")
        if not ack or not created:
            continue
        if isinstance(ack, str):
            try:
                ack = datetime.fromisoformat(ack.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
        if (ack - created).total_seconds() <= 86400:
            on_time += 1
    if total == 0:
        return 12.0, "no faults in last 30 days"
    pct = on_time / total
    return 15 * pct, f"{round(pct * 100, 1)}% of {total} faults"


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
    SiteSwitcher = All Operations Sites).

    Iter 216h122 — MOD HQ users had `not_ready=true` even when the
    chosen child gym had 10 machines + 48 open faults, because the
    legacy `get_organization_filter` only returned the HQ's own org
    id (which has no equipment of its own). Now uses
    `utils.mod_scope.resolve_mod_query_filter`.

    Iter 217 — merged the previously-duplicate "Pulse Score" into
    this endpoint. The breakdown now exposes two extra metrics
    (`fault_freshness` + `sla_adherence`) and the weights were
    re-balanced so the total still sums to 100.
    """
    from utils.mod_scope import resolve_mod_query_filter
    org_filter = await resolve_mod_query_filter(user, site_id)
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
    freshness_score, freshness_detail = await _score_fault_freshness(org_filter)
    selffix_score = _score_self_fix(c["self_fixes"], c["resolved_issues"])
    audit_score = await _score_audit_coverage(c["total_equipment"], org_filter)
    warranty_score = _score_warranty_health(c["total_equipment"], c["expired_warranty"])
    sla_score, sla_detail = await _score_sla_adherence(org_filter)
    knowledge_score = min(15.0, c["fix_history_count"] * 3)

    total_score = max(0, min(100, round(
        fault_score + freshness_score + selffix_score + audit_score
        + warranty_score + sla_score + knowledge_score,
    )))
    rating, color = _determine_health_rating(total_score)

    return {
        "score": total_score, "rating": rating, "color": color,
        "breakdown": {
            "fault_management": {"score": round(fault_score), "max": 20, "detail": f"{c['open_issues']} open / {c['total_issues']} total faults"},
            "fault_freshness": {"score": round(freshness_score), "max": 10, "detail": freshness_detail},
            "self_fix_rate": {"score": round(selffix_score), "max": 15, "detail": f"{c['self_fixes']} self-fixed / {c['resolved_issues']} resolved"},
            "audit_coverage": {"score": round(audit_score), "max": 15, "detail": f"{c['total_audits']} audits across {c['total_equipment']} equipment"},
            "warranty_health": {"score": round(warranty_score), "max": 10, "detail": f"{c['expired_warranty']} expired warranties"},
            "sla_adherence": {"score": round(sla_score), "max": 15, "detail": sla_detail},
            "ai_knowledge": {"score": round(knowledge_score), "max": 15, "detail": f"{c['fix_history_count']} proven fixes in knowledge base"},
        },
        "stats": {
            "total_equipment": c["total_equipment"], "open_issues": c["open_issues"],
            "resolved_issues": c["resolved_issues"], "self_fixes": c["self_fixes"],
            "total_audits": c["total_audits"], "fix_history_count": c["fix_history_count"],
        },
    }
