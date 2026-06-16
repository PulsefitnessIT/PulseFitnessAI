"""Performance Management & KPI Engine.

Provides automatic KPI calculation from real system data:
1. PPM Compliance (scheduled vs completed maintenance)
2. Equipment Downtime (fault→resolution time per asset)
3. Reactive Response Time (fault→engineer attendance)
4. Safety Critical Response (separate tracking + SLA breach)
5. Safety Compliance Rate (first-time inspection pass %)
6. Machine Out of Service Ratio (% unavailable by site/contract)
7. Post-Installation Verification (commissioning pass/fail)

All KPIs are drillable to case, asset, engineer, and site level.
"""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────

def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _hours_between(start: str | None, end: str | None) -> float | None:
    s, e = _parse_dt(start), _parse_dt(end)
    if not s or not e:
        return None
    return round((e - s).total_seconds() / 3600, 2)


def _safe_pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _period_cutoff(period: str) -> str:
    days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365, "all": 99999}.get(period, 30)
    if days >= 99999:
        return "2000-01-01"
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ── 1. PPM Compliance ────────────────────────────────────────────

def _ppm_task_on_time(task: dict) -> bool:
    """A completed PPM task is on-time if completed_date ≤ scheduled_date."""
    return task.get("status") == "completed" and task.get("completed_date", "") <= task.get("scheduled_date", "9999")


def _ppm_task_overdue(task: dict, now_iso: str) -> bool:
    """Non-completed task whose scheduled_date is already in the past."""
    return task.get("status") != "completed" and task.get("scheduled_date", "9999") < now_iso


def _update_site_bucket(site_bucket: dict, task: dict, now_iso: str) -> None:
    site_bucket["total"] += 1
    site_bucket["site_name"] = task.get("site_name", "Unknown")
    if task.get("status") == "completed":
        site_bucket["completed"] += 1
        if _ppm_task_on_time(task):
            site_bucket["on_time"] += 1
    if _ppm_task_overdue(task, now_iso):
        site_bucket["overdue"] += 1


async def _calc_ppm_compliance(org_filter: dict, cutoff: str) -> dict:
    """PPM Compliance: scheduled vs completed maintenance tasks."""
    tasks = await db.ppm_tasks.find(
        {**org_filter, "scheduled_date": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(5000)

    now_iso = datetime.now(timezone.utc).isoformat()
    total = len(tasks)
    completed = [t for t in tasks if t.get("status") == "completed"]
    completed_on_time = [t for t in completed if _ppm_task_on_time(t)]
    overdue = [t for t in tasks if _ppm_task_overdue(t, now_iso)]

    by_site: dict[str, dict] = defaultdict(lambda: {"total": 0, "completed": 0, "on_time": 0, "overdue": 0})
    for t in tasks:
        _update_site_bucket(by_site[t.get("site_id", "unassigned")], t, now_iso)
    for s in by_site.values():
        s["compliance_pct"] = _safe_pct(s["on_time"], s["total"])

    return {
        "total_scheduled": total,
        "total_completed": len(completed),
        "completed_on_time": len(completed_on_time),
        "overdue": len(overdue),
        "compliance_pct": _safe_pct(len(completed_on_time), total),
        "completion_pct": _safe_pct(len(completed), total),
        "by_site": dict(by_site),
    }


# ── 2. Equipment Downtime ────────────────────────────────────────

def _issue_resolution_end(issue: dict) -> str | None:
    """Return the best resolved-at timestamp for an issue, else None if open."""
    if issue.get("resolved_at"):
        return issue["resolved_at"]
    if issue.get("status") == "resolved":
        return issue.get("updated_at")
    return None


async def _calc_equipment_downtime(org_filter: dict, cutoff: str) -> dict:
    """Track fault→resolution time per asset."""
    issues = await db.issues.find(
        {**org_filter, "created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "serial_number": 1, "machine_type": 1, "status": 1,
         "severity": 1, "created_at": 1, "resolved_at": 1, "updated_at": 1, "site_id": 1}
    ).to_list(5000)

    downtimes = []
    by_asset: dict[str, dict] = defaultdict(lambda: {"total_hours": 0, "fault_count": 0, "asset_name": ""})

    for issue in issues:
        hours = _hours_between(issue.get("created_at"), _issue_resolution_end(issue))
        downtimes.append({
            "issue_id": issue["id"], "asset": issue.get("serial_number", ""),
            "machine_type": issue.get("machine_type", ""), "hours": hours,
            "status": issue.get("status"), "severity": issue.get("severity"),
        })
        if hours is not None:
            a = by_asset[issue.get("serial_number", "unknown")]
            a["total_hours"] += hours
            a["fault_count"] += 1
            a["asset_name"] = issue.get("machine_type", "")

    resolved_hours = [d["hours"] for d in downtimes if d["hours"] is not None]
    avg = round(sum(resolved_hours) / len(resolved_hours), 2) if resolved_hours else 0

    worst = sorted(by_asset.items(), key=lambda x: -x[1]["total_hours"])[:10]
    worst_list = [{"asset_id": k, "asset_name": v["asset_name"],
                   "total_hours": round(v["total_hours"], 1), "fault_count": v["fault_count"]}
                  for k, v in worst]

    return {
        "total_faults": len(issues),
        "avg_downtime_hours": avg,
        "worst_performing_assets": worst_list,
        "open_downtime_count": sum(1 for d in downtimes if d["status"] != "resolved"),
    }


# ── 3. Reactive Response Time ────────────────────────────────────

async def _calc_response_times(org_filter: dict, cutoff: str) -> dict:
    """Time from fault logged → engineer attendance/first action."""
    issues = await db.issues.find(
        {**org_filter, "created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "serial_number": 1, "machine_type": 1,
         "severity": 1, "fault_type": 1, "created_at": 1,
         "engineer_assigned_at": 1, "engineer_arrived_at": 1,
         "first_response_at": 1, "site_id": 1}
    ).to_list(5000)

    standard, safety = [], []
    for issue in issues:
        is_safety = issue.get("fault_type") == "safety_critical" or issue.get("severity") in ("safety_critical",)
        response_time = _hours_between(
            issue.get("created_at"),
            issue.get("engineer_arrived_at") or issue.get("first_response_at") or issue.get("engineer_assigned_at")
        )
        entry = {"issue_id": issue["id"], "asset": issue.get("serial_number", ""),
                 "response_hours": response_time, "severity": issue.get("severity")}
        if is_safety:
            safety.append(entry)
        else:
            standard.append(entry)

    def _avg(items):
        vals = [i["response_hours"] for i in items if i["response_hours"] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "standard": {"count": len(standard), "avg_response_hours": _avg(standard)},
        "safety_critical": {"count": len(safety), "avg_response_hours": _avg(safety)},
        "total_tracked": len(issues),
    }


# ── 4. Safety Critical Response ──────────────────────────────────

async def _calc_safety_critical(org_filter: dict, cutoff: str, sla_hours: float = 4.0) -> dict:
    """Safety critical issue tracking with SLA breach detection."""
    issues = await db.issues.find(
        {**org_filter, "created_at": {"$gte": cutoff},
         "$or": [{"fault_type": "safety_critical"}, {"severity": "safety_critical"}]},
        {"_id": 0, "id": 1, "serial_number": 1, "machine_type": 1,
         "created_at": 1, "engineer_arrived_at": 1, "first_response_at": 1,
         "resolved_at": 1, "status": 1, "site_id": 1}
    ).to_list(1000)

    breaches = []
    for issue in issues:
        response = _hours_between(
            issue.get("created_at"),
            issue.get("engineer_arrived_at") or issue.get("first_response_at")
        )
        if response is not None and response > sla_hours:
            breaches.append({
                "issue_id": issue["id"], "asset": issue.get("serial_number", ""),
                "response_hours": response, "breach_by_hours": round(response - sla_hours, 2),
            })

    return {
        "total_safety_issues": len(issues),
        "sla_target_hours": sla_hours,
        "sla_breaches": len(breaches),
        "breach_details": breaches[:20],
        "compliance_pct": _safe_pct(len(issues) - len(breaches), len(issues)),
    }


# ── 5. Safety Compliance Rate ────────────────────────────────────

async def _calc_safety_compliance(org_filter: dict, cutoff: str) -> dict:
    """% of equipment passing inspection/check sheets first time."""
    completions = await db.check_sheet_completions.find(
        {**org_filter, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(5000)

    total = len(completions)
    first_pass = sum(1 for c in completions if c.get("result") != "fail" and not c.get("has_failures"))
    failed = total - first_pass

    return {
        "total_inspections": total,
        "first_time_pass": first_pass,
        "failed": failed,
        "first_time_pass_pct": _safe_pct(first_pass, total),
    }


# ── 6. Machine Out of Service Ratio ─────────────────────────────

async def _calc_oos_ratio(org_filter: dict) -> dict:
    """% of total equipment currently unavailable."""
    total_equip = await db.equipment.count_documents(org_filter)
    open_faults = await db.issues.find(
        {**org_filter, "status": {"$in": ["open", "in_progress"]}},
        {"_id": 0, "serial_number": 1, "site_id": 1}
    ).to_list(5000)

    # Count unique assets with open faults
    oos_assets = set()
    by_site: dict[str, dict] = defaultdict(lambda: {"oos": 0, "total": 0})
    for f in open_faults:
        sn = f.get("serial_number", "")
        if sn:
            oos_assets.add(sn)

    # Site breakdown
    equipment = await db.equipment.find(org_filter, {"_id": 0, "id": 1, "serial_number": 1, "site_id": 1}).to_list(5000)
    for eq in equipment:
        sid = eq.get("site_id", "unassigned")
        by_site[sid]["total"] += 1
    for f in open_faults:
        sid = f.get("site_id", "unassigned")
        by_site[sid]["oos"] += 1

    for s in by_site.values():
        s["oos_pct"] = _safe_pct(s["oos"], s["total"])

    return {
        "total_equipment": total_equip,
        "out_of_service": len(oos_assets),
        "oos_pct": _safe_pct(len(oos_assets), total_equip),
        "by_site": dict(by_site),
    }


# ── 7. Post-Installation Verification ────────────────────────────

async def _calc_commissioning(org_filter: dict, cutoff: str) -> dict:
    """Commissioning/installation verification pass/fail rate."""
    records = await db.commissioning_records.find(
        {**org_filter, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(1000)

    total = len(records)
    passed = sum(1 for r in records if r.get("result") == "pass")
    failed = sum(1 for r in records if r.get("result") == "fail")

    return {
        "total_verifications": total,
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": _safe_pct(passed, total),
        "recent": records[:10],
    }


# ── Aggregate KPI Dashboard ─────────────────────────────────────

@router.get("/reports/kpi-dashboard")
async def get_kpi_dashboard(
    period: str = Query("30d", description="7d, 30d, 90d, 365d, all"),
    user: dict = Depends(get_current_user),
):
    """Full KPI dashboard — all 7 KPIs calculated from real data."""
    org_filter = get_organization_filter(user)
    cutoff = _period_cutoff(period)

    return {
        "period": period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ppm_compliance": await _calc_ppm_compliance(org_filter, cutoff),
        "equipment_downtime": await _calc_equipment_downtime(org_filter, cutoff),
        "reactive_response": await _calc_response_times(org_filter, cutoff),
        "safety_critical": await _calc_safety_critical(org_filter, cutoff),
        "safety_compliance": await _calc_safety_compliance(org_filter, cutoff),
        "oos_ratio": await _calc_oos_ratio(org_filter),
        "commissioning": await _calc_commissioning(org_filter, cutoff),
    }


# ── Individual KPI Endpoints (for drilldown) ─────────────────────

@router.get("/reports/kpi/ppm")
async def get_ppm_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_ppm_compliance(get_organization_filter(user), _period_cutoff(period))


@router.get("/reports/kpi/downtime")
async def get_downtime_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_equipment_downtime(get_organization_filter(user), _period_cutoff(period))


@router.get("/reports/kpi/response-time")
async def get_response_time_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_response_times(get_organization_filter(user), _period_cutoff(period))


@router.get("/reports/kpi/safety")
async def get_safety_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_safety_critical(get_organization_filter(user), _period_cutoff(period))


@router.get("/reports/kpi/compliance")
async def get_compliance_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_safety_compliance(get_organization_filter(user), _period_cutoff(period))


@router.get("/reports/kpi/oos")
async def get_oos_kpi(user: dict = Depends(get_current_user)):
    return await _calc_oos_ratio(get_organization_filter(user))


@router.get("/reports/kpi/commissioning")
async def get_commissioning_kpi(period: str = "30d", user: dict = Depends(get_current_user)):
    return await _calc_commissioning(get_organization_filter(user), _period_cutoff(period))


# ── Master Admin: KPI for any org (tender export) ────────────────

@router.get("/master-admin/kpi/{org_id}")
async def get_org_kpi(org_id: str, period: str = "365d", user: dict = Depends(get_current_user)):
    """Master Admin: get KPI dashboard for a specific organisation (for tender packs)."""
    if not user.get("is_master_admin"):
        from fastapi import HTTPException
        raise HTTPException(403, "Master admin access required")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    if not org:
        from fastapi import HTTPException
        raise HTTPException(404, "Organisation not found")

    org_filter = {"organization_id": org_id}
    cutoff = _period_cutoff(period)
    sites = await db.sites.find({"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1}).to_list(50)

    kpis = {
        "organization_id": org_id,
        "organization_name": org.get("name", ""),
        "sites": [s.get("name", "") for s in sites],
        "period": period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ppm_compliance": await _calc_ppm_compliance(org_filter, cutoff),
        "equipment_downtime": await _calc_equipment_downtime(org_filter, cutoff),
        "reactive_response": await _calc_response_times(org_filter, cutoff),
        "safety_critical": await _calc_safety_critical(org_filter, cutoff),
        "safety_compliance": await _calc_safety_compliance(org_filter, cutoff),
        "oos_ratio": await _calc_oos_ratio(org_filter),
        "commissioning": await _calc_commissioning(org_filter, cutoff),
    }
    return kpis


def _write_kpi_summary_rows(w, k: dict) -> None:
    """Write the standard KPI metrics block (10 rows) to the CSV writer.

    `k` is the dict returned by `_collect_kpis()` — keys: ppm, dt, rr, sc, si, oos, comm.
    """
    ppm, dt, rr, sc, si, oos, comm = k["ppm"], k["dt"], k["rr"], k["sc"], k["si"], k["oos"], k["comm"]
    w.writerow(["KPI", "Value", "Unit", "Detail"])
    w.writerow(["PPM Compliance", ppm["compliance_pct"], "%", f"{ppm['total_completed']}/{ppm['total_scheduled']} completed"])
    w.writerow(["PPM Completion Rate", ppm["completion_pct"], "%", f"{ppm['completed_on_time']} on time, {ppm['overdue']} overdue"])
    w.writerow(["Avg Machine Downtime", dt["avg_downtime_hours"], "hours", f"{dt['total_faults']} faults tracked"])
    w.writerow(["Open Downtime Faults", dt["open_downtime_count"], "count", "Currently unresolved"])
    w.writerow(["Reactive Response (Standard)", rr["standard"]["avg_response_hours"] or "N/A", "hours", f"{rr['standard']['count']} faults"])
    w.writerow(["Reactive Response (Safety Critical)", rr["safety_critical"]["avg_response_hours"] or "N/A", "hours", f"{rr['safety_critical']['count']} faults"])
    w.writerow(["Safety SLA Compliance", sc["compliance_pct"], "%", f"{sc['sla_breaches']} breaches / {sc['total_safety_issues']} safety issues"])
    w.writerow(["Safety Inspection Pass Rate", si["first_time_pass_pct"], "%", f"{si['first_time_pass']}/{si['total_inspections']} first-time pass"])
    w.writerow(["Machine Availability", round(100 - oos["oos_pct"], 1), "%", f"{oos['out_of_service']}/{oos['total_equipment']} machines OOS"])
    w.writerow(["Post-Install Verification Pass Rate", comm["pass_rate_pct"], "%", f"{comm['passed']}/{comm['total_verifications']}"])


def _write_kpi_worst_assets_rows(w, dt: dict) -> None:
    """Append the 'Worst Performing Machines' table if present."""
    assets = dt.get("worst_performing_assets") or []
    if not assets:
        return
    w.writerow([])
    w.writerow(["Worst Performing Machines"])
    w.writerow(["Machine", "Total Downtime (hrs)", "Fault Count"])
    for asset in assets:
        w.writerow([asset.get("asset_name", asset.get("asset_id", "")), asset["total_hours"], asset["fault_count"]])


async def _collect_kpis(org_filter: dict, cutoff) -> dict:
    """Run all 7 KPI calculators in sequence and return them keyed by short name."""
    return {
        "ppm": await _calc_ppm_compliance(org_filter, cutoff),
        "dt": await _calc_equipment_downtime(org_filter, cutoff),
        "rr": await _calc_response_times(org_filter, cutoff),
        "sc": await _calc_safety_critical(org_filter, cutoff),
        "si": await _calc_safety_compliance(org_filter, cutoff),
        "oos": await _calc_oos_ratio(org_filter),
        "comm": await _calc_commissioning(org_filter, cutoff),
    }


@router.get("/master-admin/kpi/{org_id}/export-csv")
async def export_kpi_csv(org_id: str, period: str = "365d", user: dict = Depends(get_current_user)):
    """Export KPI data as CSV for tender submission."""
    if not user.get("is_master_admin"):
        from fastapi import HTTPException
        raise HTTPException(403, "Master admin access required")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    org_name = (org or {}).get("name", "Unknown")
    k = await _collect_kpis({"organization_id": org_id}, _period_cutoff(period))

    import csv
    from io import StringIO
    from fastapi.responses import Response as FastResponse

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Pulse Fitness AI - KPI Performance Report"])
    w.writerow(["Organisation", org_name])
    w.writerow(["Period", period])
    w.writerow(["Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")])
    w.writerow([])
    _write_kpi_summary_rows(w, k)
    _write_kpi_worst_assets_rows(w, k["dt"])

    return FastResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=KPI_Report_{org_name.replace(' ', '_')}_{period}.csv"}
    )
