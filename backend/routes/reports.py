from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
import logging

from utils.database import db
from utils.auth import get_current_user
from utils.mod_scope import resolve_mod_query_filter
from utils.helpers import get_bulk_equipment_stats

logger = logging.getLogger(__name__)
router = APIRouter()


def _categorize_resolution(issue: dict) -> str:
    """Categorize an issue's resolution type."""
    rt = issue.get('resolution_type') or issue.get('resolved_by')
    if rt in ('self_fix', 'gymaxis_ai'):
        return 'self_fix'
    if rt == 'engineer':
        return 'engineer'
    return 'other'


def _build_monthly_breakdown(issues: list) -> dict:
    """Group issues by month and resolution type."""
    monthly: dict[str, dict] = {}
    for issue in issues:
        key = issue.get('created_at', '')[:7]
        if key not in monthly:
            monthly[key] = {"self_fix": 0, "engineer": 0, "other": 0}
        monthly[key][_categorize_resolution(issue)] += 1
    return dict(sorted(monthly.items()))


def _build_equipment_breakdown(issues: list) -> dict:
    """Group issues by equipment type and resolution."""
    by_eq: dict[str, dict] = {}
    for issue in issues:
        eq = issue.get('machine_type', 'Unknown')
        if eq not in by_eq:
            by_eq[eq] = {"total": 0, "self_fix": 0, "engineer": 0}
        by_eq[eq]['total'] += 1
        cat = _categorize_resolution(issue)
        if cat in by_eq[eq]:
            by_eq[eq][cat] += 1
    return by_eq


def _summarize_issue_item(i: dict, fields: tuple) -> dict:
    """Project a single issue down to a minimal dict of the given fields."""
    return {f: i.get(f) for f in fields}


@router.get("/reports/resolution-stats")
async def get_resolution_stats(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Iter 216h62 — `site_id` query param scopes the report to a
    single site. Omitted = aggregate across the whole org (used when
    the SiteSwitcher is on "All Operations Sites"). Owners/managers
    bypass the site_id constraint via the same allowed_site_ids logic
    that protects the equipment listing."""
    org_filter = await resolve_mod_query_filter(user, site_id)
    all_issues = await db.issues.find(
        org_filter,
        {"_id": 0, "status": 1, "resolution_type": 1, "resolved_by": 1, "created_at": 1,
         "machine_type": 1, "serial_number": 1, "severity": 1, "supplier": 1, "resolution_note": 1}
    ).to_list(5000)

    total = len(all_issues)
    self_fixes = [i for i in all_issues if _categorize_resolution(i) == 'self_fix']
    engineer_fixes = [i for i in all_issues if _categorize_resolution(i) == 'engineer']
    status_counts = {s: sum(1 for i in all_issues if i.get('status') == s) for s in ('open', 'in_progress', 'resolved')}
    self_fix_fields = ('serial_number', 'machine_type', 'resolution_note', 'created_at')
    engineer_fields = ('serial_number', 'machine_type', 'supplier', 'severity', 'created_at')

    return {
        "total_issues": total, "self_fixes": len(self_fixes), "engineer_callouts": len(engineer_fixes),
        "open_issues": status_counts['open'],
        "in_progress": status_counts['in_progress'],
        "resolved": status_counts['resolved'],
        "self_fix_rate": round((len(self_fixes) / max(total, 1)) * 100, 1),
        "estimated_savings": len(self_fixes) * 150, "avg_callout_cost": 150,
        "monthly_breakdown": _build_monthly_breakdown(all_issues),
        "by_equipment": _build_equipment_breakdown(all_issues),
        "recent_self_fixes": [_summarize_issue_item(i, self_fix_fields) for i in self_fixes[:10]],
        "recent_engineer_callouts": [_summarize_issue_item(i, engineer_fields) for i in engineer_fixes[:10]],
    }


@router.get("/reports/equipment-summary")
async def get_equipment_summary_report(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    org_filter = await resolve_mod_query_filter(user, site_id)
    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(200)

    summary = {
        "total_equipment": len(equipment_list),
        "by_type": {},
        "total_issues": 0,
        "open_issues": 0,
        "total_audits": 0,
        "warranty_expiring_soon": 0,
        "equipment_details": []
    }

    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)

    for equip in equipment_list:
        equip_type = equip.get('equipment_type', 'Unknown')
        summary['by_type'][equip_type] = summary['by_type'].get(equip_type, 0) + 1
        stats = bulk_stats.get(equip['id'], {})
        summary['total_issues'] += stats.get('total_issues', 0)
        summary['open_issues'] += stats.get('open_issues', 0)
        summary['total_audits'] += stats.get('total_audits', 0)
        if stats.get('warranty_days_remaining') and stats['warranty_days_remaining'] < 30:
            summary['warranty_expiring_soon'] += 1
        summary['equipment_details'].append({
            "id": equip['id'],
            "name": equip['name'],
            "type": equip['equipment_type'],
            "manufacturer": equip.get('manufacturer'),
            "stats": stats
        })
    return summary


def _count_by_field(issues: list[dict], field: str, default: str = "Unknown") -> dict[str, int]:
    """Group-count issues by a given field."""
    counts: dict[str, int] = {}
    for issue in issues:
        key = issue.get(field, default) or default
        counts[key] = counts.get(key, 0) + 1
    return counts


def _calculate_resolution_times(issues: list[dict]) -> list[dict]:
    """Extract resolution time data from resolved issues."""
    times: list[dict] = []
    for issue in issues:
        if issue.get('status') != 'resolved':
            continue
        created_at = issue.get('created_at')
        updated_at = issue.get('updated_at')
        if not created_at or not updated_at:
            continue
        try:
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            resolved = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            hours = (resolved - created).total_seconds() / 3600
            times.append({
                "issue": issue.get('serial_number'),
                "hours": round(hours, 1),
                "type": issue.get('resolution_type', 'unknown'),
            })
        except (ValueError, TypeError):
            continue
    return times


def _compute_weekly_trend(issues: list[dict]) -> dict[str, dict]:
    """Aggregate weekly fault totals and self-fix counts."""
    trend: dict[str, dict] = {}
    for issue in issues:
        try:
            dt = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            week_key = dt.strftime('%Y-W%U')
        except (ValueError, TypeError, KeyError):
            continue
        if week_key not in trend:
            trend[week_key] = {"total": 0, "self_fix": 0}
        trend[week_key]['total'] += 1
        rt = issue.get('resolution_type') or issue.get('resolved_by')
        if rt in ('self_fix', 'gymaxis_ai'):
            trend[week_key]['self_fix'] += 1
    return trend


def _build_severity_counts(issues: list) -> dict:
    """Count issues by severity."""
    counts = {"critical": 0, "medium": 0, "low": 0}
    for issue in issues:
        sev = issue.get('severity', 'medium')
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _build_daily_faults(issues: list) -> dict:
    """Count faults by day."""
    by_day: dict[str, int] = {}
    for issue in issues:
        day = issue.get('created_at', '')[:10]
        by_day[day] = by_day.get(day, 0) + 1
    return dict(sorted(by_day.items()))


_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365, "all": 99999}


def _period_cutoff_iso(period: str) -> str:
    """Return an ISO-string cutoff for a period like '30d'."""
    days = _PERIOD_DAYS.get(period, 30)
    if days >= 99999:
        return "2000-01-01"
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@router.get("/reports/operational")
async def get_operational_reports(
    period: str = "30d",
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    org_filter = await resolve_mod_query_filter(user, site_id)
    cutoff = _period_cutoff_iso(period)

    all_issues = await db.issues.find(org_filter, {"_id": 0}).to_list(5000)
    period_issues = [i for i in all_issues if i.get('created_at', '') >= cutoff]

    resolution_times = _calculate_resolution_times(period_issues)
    all_pos = await db.purchase_orders.find(org_filter, {"_id": 0}).to_list(500)
    period_pos = [p for p in all_pos if p.get('created_at', '') >= cutoff]
    status_counts = {s: sum(1 for i in period_issues if i.get('status') == s) for s in ('open', 'resolved')}

    return {
        "period": period, "total_faults": len(period_issues),
        "faults_by_day": _build_daily_faults(period_issues),
        "severity_counts": _build_severity_counts(period_issues),
        "by_equipment": dict(sorted(_count_by_field(period_issues, 'machine_type', 'Unknown').items(), key=lambda x: -x[1])),
        "by_supplier": dict(sorted(_count_by_field(period_issues, 'supplier', 'Unassigned').items(), key=lambda x: -x[1])),
        "avg_resolution_hours": round(sum(r['hours'] for r in resolution_times) / max(len(resolution_times), 1), 1),
        "resolution_times": resolution_times[:20],
        "total_po_value": round(sum(p.get('total', 0) for p in period_pos), 2),
        "po_count": len(period_pos),
        "po_by_status": _count_by_field(period_pos, 'status', 'draft'),
        "weekly_trend": dict(sorted(_compute_weekly_trend(period_issues).items())),
        "open_faults": status_counts['open'],
        "resolved_faults": status_counts['resolved'],
    }
