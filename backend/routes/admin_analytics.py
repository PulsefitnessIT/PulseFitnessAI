from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import os
from pymongo import MongoClient
from utils.auth import get_current_user

router = APIRouter(prefix="/master-admin/analytics", tags=["Admin Analytics"])

client = MongoClient(os.environ.get("MONGO_URL"))
db = client[os.environ.get("DB_NAME", "gymfix")]


def require_admin(user):
    if not user or not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─── Shared Helpers ────────────────────────────────────────────────────────


def _parse_iso(value) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _month_ranges(months_back: int = 6):
    """Yield (label, start, end) for each of the last *months_back* months."""
    now = datetime.now(timezone.utc)
    for i in range(months_back - 1, -1, -1):
        month_start = (now - timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (now - timedelta(days=30 * (i - 1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0) if i > 0 else now
        yield month_start.strftime("%b %Y"), month_start, month_end


def _count_in_range(items, field, start, end):
    """Count items whose *field* falls within [start, end)."""
    count = 0
    for item in items:
        dt = _parse_iso(item.get(field))
        if dt and start <= dt < end:
            count += 1
    return count


def _compute_resolution_hours(issues):
    """Return list of resolution times in hours for resolved issues."""
    times = []
    for issue in issues:
        if issue.get("status") != "resolved":
            continue
        created = _parse_iso(issue.get("created_at"))
        resolved = _parse_iso(issue.get("resolved_at"))
        if created and resolved:
            times.append((resolved - created).total_seconds() / 3600)
    return times


def _compute_health_score(org_issues, org_equip_count, org_checks_count):
    """Composite health score (0-100) for a single gym."""
    total_faults = len(org_issues)
    open_faults = sum(1 for i in org_issues if i.get("status") == "open")
    resolved = sum(1 for i in org_issues if i.get("status") == "resolved")
    fault_ratio = (total_faults / org_equip_count) if org_equip_count > 0 else 0
    resolution_rate = (resolved / total_faults * 100) if total_faults > 0 else 100
    return max(0, min(100, round(
        100
        - (fault_ratio * 15)
        - (open_faults * 5)
        + (resolution_rate * 0.2)
        + min(org_checks_count * 2, 20)
    )))


def _recent_faults_in_window(issues: list, cutoff: datetime) -> int:
    """Count issues whose created_at is on or after the cutoff."""
    fallback = datetime.min.replace(tzinfo=timezone.utc)
    return sum(1 for i in issues if (_parse_iso(i.get("created_at")) or fallback) >= cutoff)


def _build_org_leaderboard_entry(org: dict, all_equipment: list, all_issues: list,
                                  all_checks: list, thirty_days_ago: datetime) -> dict:
    """Compute a single leaderboard row for one org."""
    oid = org.get("id")
    org_equip = [e for e in all_equipment if e.get("organization_id") == oid]
    org_issues = [i for i in all_issues if i.get("organization_id") == oid]
    org_checks = [c for c in all_checks if c.get("organization_id") == oid]
    status_counts = {s: sum(1 for i in org_issues if i.get("status") == s) for s in ("open", "resolved")}

    return {
        "org_id": oid,
        "org_name": org.get("name", "Unknown"),
        "equipment_count": len(org_equip),
        "total_faults": len(org_issues),
        "open_faults": status_counts["open"],
        "resolved_faults": status_counts["resolved"],
        "recent_faults_30d": _recent_faults_in_window(org_issues, thirty_days_ago),
        "check_sheets_completed": len(org_checks),
        "health_score": _compute_health_score(org_issues, len(org_equip), len(org_checks)),
        "account_type": org.get("account_type", "full"),
    }


def _build_org_leaderboard(orgs, all_equipment, all_issues, all_checks, thirty_days_ago):
    """Build per-org health leaderboard."""
    leaderboard = [
        _build_org_leaderboard_entry(org, all_equipment, all_issues, all_checks, thirty_days_ago)
        for org in orgs
    ]
    leaderboard.sort(key=lambda x: x["health_score"], reverse=True)
    return leaderboard


def _get_age_bucket(purchase_date_str: str | None, now) -> str:
    """Return the age bucket label for a purchase date."""
    purchase = _parse_iso(purchase_date_str)
    if not purchase:
        return "Unknown"
    if purchase.tzinfo is None:
        purchase = purchase.replace(tzinfo=timezone.utc)
    age = (now - purchase).days / 365.25
    if age < 1:
        return "< 1 year"
    if age < 3:
        return "1-3 years"
    if age < 5:
        return "3-5 years"
    if age < 10:
        return "5-10 years"
    return "10+ years"


def _equipment_age_distribution(all_equipment, now):
    """Bucket equipment by age."""
    buckets = {"< 1 year": 0, "1-3 years": 0, "3-5 years": 0, "5-10 years": 0, "10+ years": 0, "Unknown": 0}
    for e in all_equipment:
        buckets[_get_age_bucket(e.get("purchase_date"), now)] += 1
    return [{"range": k, "count": v} for k, v in buckets.items() if v > 0]


def _warranty_status(all_equipment, now):
    """Count active / expired warranties."""
    active, expired = 0, 0
    for e in all_equipment:
        exp = _parse_iso(e.get("warranty_expiry"))
        if not exp:
            continue
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            active += 1
        else:
            expired += 1
    unknown = len(all_equipment) - active - expired
    return {"active": active, "expired": expired, "unknown": unknown}


def _repeat_offenders(all_issues, orgs_map, min_faults=2, limit=20):
    """Equipment with *min_faults*+ faults."""
    counts = Counter()
    info = {}
    for i in all_issues:
        eid = i.get("equipment_id")
        if not eid:
            continue
        counts[eid] += 1
        if eid not in info:
            info[eid] = {
                "serial_number": i.get("serial_number", ""),
                "machine_type": i.get("machine_type", ""),
                "org_id": i.get("organization_id", ""),
            }
    result = []
    for eid, count in counts.most_common():
        if count < min_faults:
            break
        inf = info.get(eid, {})
        result.append({
            "equipment_id": eid,
            "serial_number": inf.get("serial_number", ""),
            "machine_type": inf.get("machine_type", ""),
            "gym": orgs_map.get(inf.get("org_id", ""), "Unknown"),
            "fault_count": count,
        })
        if len(result) >= limit:
            break
    return result


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def analytics_dashboard(user: dict = Depends(get_current_user)):
    """Global gym leaderboard and KPIs."""
    require_admin(user)

    orgs = list(db.organizations.find({}, {"_id": 0}))
    all_equipment = list(db.equipment.find({}, {"_id": 0}))
    all_issues = list(db.issues.find({}, {"_id": 0}))
    all_checks = list(db.check_sheets.find({}, {"_id": 0}))
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    resolution_times = _compute_resolution_hours(all_issues)
    avg_resolution_hrs = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0

    leaderboard = _build_org_leaderboard(orgs, all_equipment, all_issues, all_checks, thirty_days_ago)

    fault_trend = []
    for label, start, end in _month_ranges(6):
        fault_trend.append({"month": label, "faults": _count_in_range(all_issues, "created_at", start, end)})

    return {
        "global_kpis": {
            "total_gyms": len(orgs),
            "total_equipment": len(all_equipment),
            "total_faults": len(all_issues),
            "open_faults": sum(1 for i in all_issues if i.get("status") == "open"),
            "resolved_faults": sum(1 for i in all_issues if i.get("status") == "resolved"),
            "avg_resolution_hours": avg_resolution_hrs,
            "avg_health_score": round(sum(g["health_score"] for g in leaderboard) / len(leaderboard), 1) if leaderboard else 0,
        },
        "leaderboard": leaderboard,
        "fault_trend": fault_trend,
    }


def _count_top_field(items: list, key_fn, limit: int = 15) -> list[dict]:
    """Generic 'group by then take top N' helper that yields [{name, count}]."""
    return [{"name": k, "count": v} for k, v in Counter(key_fn(e) for e in items).most_common(limit)]


@router.get("/equipment")
async def analytics_equipment(user: dict = Depends(get_current_user)):
    """Equipment fleet intelligence across all gyms."""
    require_admin(user)

    all_equipment = list(db.equipment.find({}, {"_id": 0}))
    orgs = {o["id"]: o["name"] for o in db.organizations.find({}, {"_id": 0, "id": 1, "name": 1})}
    now = datetime.now(timezone.utc)

    by_manufacturer = _count_top_field(
        [e for e in all_equipment if e.get("manufacturer")],
        lambda e: e.get("manufacturer", "Unknown"),
    )
    by_type = _count_top_field(
        [e for e in all_equipment if e.get("equipment_type")],
        lambda e: e.get("equipment_type", "Unknown"),
    )
    by_model = _count_top_field(
        [e for e in all_equipment if e.get("model")],
        lambda e: f"{e.get('manufacturer', '?')} {e.get('model', '?')}",
    )

    org_equip = Counter(e.get("organization_id") for e in all_equipment)
    per_gym = [{"gym": orgs.get(oid, "Unknown"), "count": c} for oid, c in org_equip.most_common()]

    return {
        "total": len(all_equipment),
        "by_manufacturer": by_manufacturer,
        "by_type": by_type,
        "by_model": by_model,
        "age_distribution": _equipment_age_distribution(all_equipment, now),
        "per_gym": per_gym,
        "warranty": _warranty_status(all_equipment, now),
    }


def _monthly_severity_breakdown(all_issues: list) -> list[dict]:
    """Aggregate issues into monthly severity buckets."""
    breakdown: list[dict] = []
    for label, start, end in _month_ranges(6):
        month_data: dict = {"month": label.split()[0]}
        for issue in all_issues:
            dt = _parse_iso(issue.get("created_at"))
            if dt and start <= dt < end:
                sev = issue.get("severity", "unknown")
                month_data[sev] = month_data.get(sev, 0) + 1
        breakdown.append(month_data)
    return breakdown


def _compute_mom_fault_counters(all_issues: list) -> tuple:
    """Split issues into current 30-day and previous 30-day fault-code counters."""
    now = datetime.now(timezone.utc)
    curr_start = now - timedelta(days=30)
    prev_start = now - timedelta(days=60)
    current_counter: Counter = Counter()
    previous_counter: Counter = Counter()
    for issue in all_issues:
        code = issue.get("fault_code")
        if not code:
            continue
        dt = _parse_iso(issue.get("created_at")) or _parse_iso(issue.get("reported_at"))
        if not dt:
            continue
        if dt >= curr_start:
            current_counter[code] += 1
        elif dt >= prev_start:
            previous_counter[code] += 1
    return current_counter, previous_counter


def _code_trend(curr: int, prev: int) -> tuple:
    """Given current/previous counts, return (delta_pct, direction)."""
    if prev == 0:
        delta_pct = None if curr == 0 else 100
        direction = "new" if curr > 0 else "flat"
        return delta_pct, direction
    delta_pct = round(((curr - prev) / prev) * 100)
    if curr > prev:
        direction = "up"
    elif curr < prev:
        direction = "down"
    else:
        direction = "flat"
    return delta_pct, direction


def _build_code_entry(code: str, total: int, current_counter: Counter, previous_counter: Counter) -> dict:
    """Build a single by_fault_code entry with MoM trend fields."""
    from constants.fault_codes import FAULT_CODE_LABELS, fault_code_category
    curr = current_counter.get(code, 0)
    prev = previous_counter.get(code, 0)
    delta_pct, direction = _code_trend(curr, prev)
    return {
        "code": code,
        "label": FAULT_CODE_LABELS.get(code, code),
        "category": fault_code_category(code),
        "count": total,
        "count_current_30d": curr,
        "count_previous_30d": prev,
        "delta_pct": delta_pct,
        "trend": direction,
    }


def _build_fault_category_breakdown(code_counter: Counter) -> list:
    """Aggregate fault codes by category and return sorted list."""
    from constants.fault_codes import fault_code_category
    cat_counts = Counter(
        fault_code_category(c) for c in code_counter.elements() if fault_code_category(c)
    )
    return [{"category": cat, "count": cnt} for cat, cnt in cat_counts.most_common()]


def _build_fault_aggregate_breakdowns(all_issues: list, orgs_map: dict) -> tuple:
    """Return (problem_machines, by_severity, by_gym) breakdowns for analytics_faults."""
    problem_machines = [
        {"machine_type": k, "fault_count": v}
        for k, v in Counter(i.get("machine_type", "Unknown") for i in all_issues).most_common(15)
    ]
    by_severity = [
        {"severity": k, "count": v}
        for k, v in Counter(i.get("severity", "unknown") for i in all_issues).items()
    ]
    by_gym = [
        {"gym": orgs_map.get(oid, "Unknown"), "count": c, "org_id": oid}
        for oid, c in Counter(i.get("organization_id") for i in all_issues).most_common()
    ]
    return problem_machines, by_severity, by_gym


@router.get("/faults")
async def analytics_faults(user: dict = Depends(get_current_user)) -> dict:
    """Cross-gym fault breakdown analysis."""
    require_admin(user)

    all_issues = list(db.issues.find({}, {"_id": 0}))
    orgs_map = {o["id"]: o["name"] for o in db.organizations.find({}, {"_id": 0, "id": 1, "name": 1})}

    problem_machines, by_severity, by_gym = _build_fault_aggregate_breakdowns(all_issues, orgs_map)
    code_counter = Counter(i.get("fault_code") for i in all_issues if i.get("fault_code"))
    current_counter, previous_counter = _compute_mom_fault_counters(all_issues)
    by_fault_code = [
        _build_code_entry(code, total, current_counter, previous_counter)
        for code, total in code_counter.most_common(20)
    ]
    by_fault_category = _build_fault_category_breakdown(code_counter)

    return {
        "total_faults": len(all_issues),
        "status_breakdown": dict(Counter(i.get("status", "unknown") for i in all_issues)),
        "problem_machines": problem_machines,
        "by_severity": by_severity,
        "by_gym": by_gym,
        "by_fault_code": by_fault_code,
        "by_fault_category": by_fault_category,
        "coded_fault_count": sum(code_counter.values()),
        "repeat_offenders": _repeat_offenders(all_issues, orgs_map),
        "monthly_trend": _monthly_severity_breakdown(all_issues),
    }


def _build_checksheet_leaderboard(org_checks: dict, org_equip_count, orgs: dict, thirty_days_ago) -> list:
    """Build per-org compliance leaderboard from check sheet data."""
    leaderboard = []
    for org_id, checks in org_checks.items():
        equip_count = org_equip_count.get(org_id, 1)
        recent = sum(1 for c in checks if (_parse_iso(c.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= thirty_days_ago)
        compliance = min(100, round((len(checks) / max(equip_count, 1)) * 25))
        leaderboard.append({
            "org_id": org_id, "gym": orgs.get(org_id, "Unknown"),
            "total_checks": len(checks), "recent_checks_30d": recent,
            "equipment_count": equip_count, "compliance_score": compliance,
        })
    leaderboard.sort(key=lambda x: x["compliance_score"], reverse=True)
    return leaderboard


def _generate_check_suggestions(all_issues: list, all_checks: list) -> list:
    """Generate AI suggestions for missing check sheet coverage."""
    fault_types = Counter(i.get("machine_type", "") for i in all_issues if i.get("status") == "open")
    check_categories = set(c.get("equipment_category", "") for c in all_checks)
    return [
        f"Consider adding dedicated check sheets for '{mt}' — {cnt} open faults with no matching checks."
        for mt, cnt in fault_types.most_common(5)
        if mt and mt not in check_categories
    ] or ["Check sheet coverage looks good across current fault categories."]


@router.get("/checksheets")
async def analytics_checksheets(user: dict = Depends(get_current_user)):
    """Check sheet compliance leaderboard."""
    require_admin(user)

    all_checks = list(db.check_sheets.find({}, {"_id": 0}))
    all_issues = list(db.issues.find({}, {"_id": 0}))
    orgs = {o["id"]: o["name"] for o in db.organizations.find({}, {"_id": 0, "id": 1, "name": 1})}
    all_equipment = list(db.equipment.find({}, {"_id": 0}))
    org_equip_count = Counter(e.get("organization_id") for e in all_equipment)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    org_checks = defaultdict(list)
    for c in all_checks:
        org_checks[c.get("organization_id")].append(c)

    return {
        "total_checks": len(all_checks),
        "leaderboard": _build_checksheet_leaderboard(org_checks, org_equip_count, orgs, thirty_days_ago),
        "by_category": [{"category": k, "count": v} for k, v in Counter(c.get("equipment_category", "General") for c in all_checks).most_common()],
        "top_users": [{"user": k, "count": v} for k, v in Counter(c.get("completed_by", "Unknown") for c in all_checks).most_common(10)],
        "ai_suggestions": _generate_check_suggestions(all_issues, all_checks),
    }


SEVERITY_MAP = {"safety_critical": 5, "out_of_order": 4, "limited_use": 3, "operational_fault": 2, "operational_minor": 1}


def _build_check_improvements(all_issues: list) -> list:
    """Identify high-severity machine types needing increased inspection."""
    high_sev = Counter()
    for i in all_issues:
        if SEVERITY_MAP.get(i.get("severity", ""), 0) >= 3:
            high_sev[i.get("machine_type", "Unknown")] += 1
    return [
        {"machine_type": mt, "high_severity_faults": cnt,
         "suggestion": f"Increase inspection frequency for {mt} — {cnt} high-severity faults detected. Consider adding daily visual checks."}
        for mt, cnt in high_sev.most_common(5)
        if mt and mt != "Unknown"
    ]


@router.get("/ai")
async def analytics_ai(user: dict = Depends(get_current_user)):
    """AI learning and usage report."""
    require_admin(user)

    chats = list(db.chat_history.find({}, {"_id": 0}))
    audits = list(db.audits.find({}, {"_id": 0}))
    fixes = list(db.fix_history.find({}, {"_id": 0}))
    knowledge = list(db.equipment_knowledge.find({}, {"_id": 0}))
    all_issues = list(db.issues.find({}, {"_id": 0}))

    usage_trend = [
        {"month": label.split()[0],
         "diagnoses": _count_in_range(chats, "created_at", start, end),
         "audits": _count_in_range(audits, "created_at", start, end)}
        for label, start, end in _month_ranges(6)
    ]

    return {
        "summary": {
            "total_diagnoses": len(chats),
            "total_audits": len(audits),
            "total_fixes_logged": len(fixes),
            "knowledge_documents": len(knowledge),
            "unique_equipment_types_diagnosed": len(set(c.get("equipment_type", "") for c in chats if c.get("equipment_type"))),
            "unique_issue_patterns": len(set(i.get("issue_description", "")[:50] for i in all_issues)),
        },
        "top_diagnosed": [{"type": k, "count": v} for k, v in Counter(c.get("equipment_type", "Unknown") for c in chats if c.get("equipment_type")).most_common(10)],
        "top_fixed": [{"machine_type": k, "fixes": v} for k, v in Counter(f.get("machine_type", "Unknown") for f in fixes).most_common(10)],
        "usage_trend": usage_trend,
        "check_improvements": _build_check_improvements(all_issues),
    }
