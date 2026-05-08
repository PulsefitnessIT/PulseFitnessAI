from datetime import datetime, timezone
from collections import defaultdict
from typing import Union
from utils.database import db
from utils.auth import get_organization_filter


async def get_equipment_stats(equipment_id: str, user: Union[str, dict]) -> dict:
    """Single-equipment stats (used for single-item views). For lists, use get_bulk_equipment_stats."""
    if isinstance(user, str):
        user_doc = await db.users.find_one({"id": user}, {"_id": 0})
        org_filter = get_organization_filter(user_doc) if user_doc else {"user_id": user}
    else:
        org_filter = get_organization_filter(user)

    equipment = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not equipment:
        return {}

    bulk = await get_bulk_equipment_stats([equipment], org_filter)
    return bulk.get(equipment_id, {})


async def get_bulk_equipment_stats(equipment_list: list[dict], org_filter: dict) -> dict[str, dict]:
    """Batch-compute stats for many equipment items using 3 bulk DB queries instead of N*6."""
    if not equipment_list:
        return {}

    # Build lookup keys: each equipment can match issues by serial_number OR name
    equip_lookup = {}  # maps match_key -> equipment_id
    all_match_keys = set()
    equip_ids = []
    equip_map = {}  # id -> equipment doc

    for equip in equipment_list:
        eid = equip['id']
        equip_ids.append(eid)
        equip_map[eid] = equip
        sn = equip.get('serial_number', '')
        name = equip.get('name', '')
        keys = set()
        if sn:
            keys.add(sn)
            equip_lookup.setdefault(sn, []).append(eid)
        if name:
            keys.add(name)
            equip_lookup.setdefault(name, []).append(eid)
        all_match_keys.update(keys)

    # --- Bulk query 1: all issues matching any of these serial_numbers ---
    all_issues = await db.issues.find(
        {**org_filter, "serial_number": {"$in": list(all_match_keys)}},
        {"_id": 0, "serial_number": 1, "status": 1, "created_at": 1}
    ).to_list(length=10000)

    # Group issues by equipment_id
    issues_by_equip = defaultdict(list)
    for issue in all_issues:
        sn = issue.get("serial_number", "")
        for eid in equip_lookup.get(sn, []):
            issues_by_equip[eid].append(issue)

    # --- Bulk query 2: all audits for these equipment IDs ---
    all_audits = await db.audits.find(
        {"equipment_id": {"$in": equip_ids}},
        {"_id": 0, "equipment_id": 1, "created_at": 1}
    ).to_list(length=10000)

    audits_by_equip = defaultdict(list)
    for audit in all_audits:
        audits_by_equip[audit["equipment_id"]].append(audit)

    # --- Compute stats per equipment in memory ---
    now = datetime.now(timezone.utc)
    results = {}

    for equip in equipment_list:
        eid = equip['id']
        issues = issues_by_equip.get(eid, [])
        audits = audits_by_equip.get(eid, [])
        results[eid] = _compute_single_stats(equip, issues, audits, now)

    return results


def _compute_single_stats(equip: dict, issues: list, audits: list, now: datetime) -> dict:
    """Compute stats dict for one equipment item from pre-fetched issues/audits."""
    total_issues = len(issues)
    open_issues = sum(1 for i in issues if i.get('status') == 'open')
    resolved_issues = sum(1 for i in issues if i.get('status') == 'resolved')
    last_issue = max(issues, key=lambda i: i.get('created_at', ''), default=None) if issues else None

    total_audits = len(audits)
    last_audit = max(audits, key=lambda a: a.get('created_at', ''), default=None) if audits else None

    # Prefer install_date (in-service) > purchase_date (invoice) > invoice_date
    in_service_date = (
        equip.get('install_date')
        or equip.get('purchase_date')
        or equip.get('invoice_date')
    )
    days_in_service = _safe_days_since(in_service_date, now)
    warranty_active, warranty_days = _safe_days_until(equip.get('warranty_expiry'), now)
    warranty_months = None
    if warranty_days is not None:
        warranty_months = round(warranty_days / 30.44, 1)

    return {
        "total_issues": total_issues,
        "open_issues": open_issues,
        "resolved_issues": resolved_issues,
        "last_issue_date": last_issue['created_at'] if last_issue else None,
        "total_audits": total_audits,
        "last_audit_date": last_audit['created_at'] if last_audit else None,
        "days_in_service": days_in_service,
        "in_service_date": in_service_date,
        "warranty_active": warranty_active,
        "warranty_days_remaining": warranty_days,
        "warranty_months_remaining": warranty_months,
        "manuals_count": len(equip.get('manuals', [])),
    }


def _safe_days_since(date_str: str | None, now: datetime) -> int | None:
    """Return days between *date_str* and *now*, or None on failure."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except (ValueError, TypeError):
        return None


def _safe_days_until(date_str: str | None, now: datetime) -> tuple[bool, int | None]:
    """Return (is_active, days_remaining) for a future date."""
    if not date_str:
        return False, None
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (dt - now).days
        return days > 0, days
    except (ValueError, TypeError):
        return False, None
