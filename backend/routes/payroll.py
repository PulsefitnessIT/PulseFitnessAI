"""Payroll Workspace — configurable pay periods, exception-based approval,
immutable lock/snapshot and export-with-field-mapping (spec §32–§43).

Everything reads the Attendance Spine (attendance_daily) via
attendance.period_summary, so payroll never rebuilds hours from spreadsheets.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.staffing import _clean, _now, _org, _require_manager
from routes.attendance import period_summary, _resolve_profile

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_FIELD_MAPPING = [
    {"source": "payroll_number", "label": "Payroll ID", "column": "Payroll ID"},
    {"source": "full_name", "label": "Employee", "column": "Employee"},
    {"source": "regular", "label": "Regular Hours", "column": "Regular Hours"},
    {"source": "overtime_approved", "label": "Overtime", "column": "Overtime"},
    {"source": "holiday", "label": "Holiday", "column": "Holiday"},
    {"source": "sick", "label": "Sick", "column": "Sick"},
    {"source": "bank_holiday", "label": "Bank Holiday", "column": "Bank Holiday"},
    {"source": "comp", "label": "Comp / TOIL", "column": "Comp"},
    {"source": "unpaid_days", "label": "Unpaid Days", "column": "Unpaid Days"},
    {"source": "pt", "label": "PT", "column": "PT"},
    {"source": "classes", "label": "Classes", "column": "Classes"},
]


# ───────────────────────── helpers ─────────────────────────
async def _period(org_id: str, period_id: str) -> dict:
    p = await db.pay_periods.find_one({"organization_id": org_id, "id": period_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "pay period not found")
    return p


async def _timesheet(org_id: str, period_id: str, staff_id: str) -> dict | None:
    return await db.pay_period_timesheets.find_one(
        {"organization_id": org_id, "period_id": period_id, "staff_id": staff_id}, {"_id": 0},
    )


def _exceptions(totals: dict, profile: dict, ts_status: str) -> list[str]:
    ex = []
    if totals["missing"] > 0:
        ex.append("missing_entry")
    if totals["overtime_raw"] > 0 and profile.get("overtime_eligibility") and \
            profile.get("overtime_rule") == "manager_approval" and totals["overtime_approved"] <= 0:
        ex.append("unapproved_overtime")
    if totals["unpaid_days"] > 0:
        ex.append("unpaid_leave")
    if not profile.get("payroll_number"):
        ex.append("no_payroll_id")
    if totals["expected"] and totals["worked"]:
        ratio = totals["worked"] / totals["expected"]
        if ratio > 1.15:
            ex.append("above_contract")
        elif ratio < 0.85:
            ex.append("below_contract")
    if ts_status != "approved":
        ex.append("missing_approval")
    return ex


async def _build_row(org_id: str, staff: dict, period: dict, recompute=True) -> dict:
    profile = await _resolve_profile(org_id, staff)
    ts = await _timesheet(org_id, period["id"], staff["id"])
    # Locked periods read the immutable snapshot totals; otherwise compute live.
    if period["status"] == "locked" and ts and ts.get("snapshot_totals"):
        totals = ts["snapshot_totals"]
    elif ts and ts.get("status") in ("submitted", "approved") and ts.get("totals"):
        totals = ts["totals"]
    else:
        totals = await period_summary(org_id, staff["id"], period["start_date"], period["end_date"], recompute)
    status = (ts or {}).get("status", "draft")
    return {
        "staff_id": staff["id"], "full_name": staff.get("full_name"),
        "payroll_number": profile.get("payroll_number"),
        "department": staff.get("department"),
        "status": status, "totals": totals,
        "exceptions": _exceptions(totals, profile, status),
        "declaration": (ts or {}).get("declaration"),
        "submitted_at": (ts or {}).get("submitted_at"),
        "approved_by": (ts or {}).get("approved_by"),
        "returned_reason": (ts or {}).get("returned_reason"),
    }


# ───────────────────────── field mapping ─────────────────────────
@router.get("/payroll/field-mapping")
async def get_mapping(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    doc = await db.payroll_field_mappings.find_one({"organization_id": org_id}, {"_id": 0})
    return {"fields": (doc or {}).get("fields") or DEFAULT_FIELD_MAPPING}


@router.put("/payroll/field-mapping")
async def put_mapping(fields: list[dict] = Body(..., embed=True), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await db.payroll_field_mappings.update_one(
        {"organization_id": org_id},
        {"$set": {"organization_id": org_id, "fields": fields, "updated_at": _now().isoformat()}},
        upsert=True,
    )
    return {"fields": fields}


# ───────────────────────── periods ─────────────────────────
class PeriodBody(BaseModel):
    name: str
    start_date: str
    end_date: str
    frequency: str = "custom"
    employee_deadline: str | None = None
    manager_deadline: str | None = None
    payroll_date: str | None = None


class GenerateBody(BaseModel):
    frequency: str  # 4_week | 5_week | month
    anchor: str     # start date (or any date in the month for 'month')


@router.get("/payroll/periods")
async def list_periods(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    rows = await db.pay_periods.find({"organization_id": org_id}, {"_id": 0}).sort("start_date", -1).to_list(200)
    return {"periods": rows}


@router.post("/payroll/periods")
async def create_period(body: PeriodBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    doc = {"id": str(uuid4()), "organization_id": org_id, "status": "open",
           "created_at": _now().isoformat(), "created_by": user.get("email"), **body.dict()}
    await db.pay_periods.insert_one(doc.copy())
    return _clean(doc)


@router.post("/payroll/periods/generate")
async def generate_period(body: GenerateBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    a = date.fromisoformat(body.anchor)
    if body.frequency == "month":
        start = a.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        name = start.strftime("%B %Y")
    elif body.frequency in ("4_week", "5_week"):
        weeks = 4 if body.frequency == "4_week" else 5
        start = a
        end = a + timedelta(days=weeks * 7 - 1)
        name = f"{weeks}-week · {start.isoformat()} to {end.isoformat()}"
    else:
        raise HTTPException(400, "frequency must be 4_week, 5_week or month")
    doc = {"id": str(uuid4()), "organization_id": org_id, "status": "open",
           "name": name, "start_date": start.isoformat(), "end_date": end.isoformat(),
           "frequency": body.frequency, "payroll_date": (end + timedelta(days=5)).isoformat(),
           "employee_deadline": (end + timedelta(days=2)).isoformat(),
           "manager_deadline": (end + timedelta(days=3)).isoformat(),
           "created_at": _now().isoformat(), "created_by": user.get("email")}
    await db.pay_periods.insert_one(doc.copy())
    return _clean(doc)


@router.put("/payroll/periods/{period_id}")
async def update_period(period_id: str, body: PeriodBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    p = await _period(org_id, period_id)
    if p["status"] == "locked":
        raise HTTPException(409, "period is locked")
    await db.pay_periods.update_one({"organization_id": org_id, "id": period_id},
                                    {"$set": {**body.dict(), "updated_at": _now().isoformat()}})
    return await _period(org_id, period_id)


@router.delete("/payroll/periods/{period_id}")
async def delete_period(period_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    p = await _period(org_id, period_id)
    if p["status"] == "locked":
        raise HTTPException(409, "cannot delete a locked period")
    await db.pay_periods.delete_one({"organization_id": org_id, "id": period_id})
    await db.pay_period_timesheets.delete_many({"organization_id": org_id, "period_id": period_id})
    return {"ok": True}


# ───────────────────────── workspace ─────────────────────────
@router.get("/payroll/periods/{period_id}/workspace")
async def workspace(period_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).sort("full_name", 1).to_list(1000)
    rows = [await _build_row(org_id, s, period) for s in staff]
    ready = sum(1 for r in rows if r["status"] == "approved" and not r["exceptions"])
    awaiting = sum(1 for r in rows if r["status"] == "submitted")
    missing = sum(1 for r in rows if r["status"] in ("draft", "returned") or "missing_entry" in r["exceptions"])
    exceptions = sum(1 for r in rows if r["exceptions"])
    return {
        "period": period, "rows": rows,
        "summary": {"total": len(rows), "ready": ready, "awaiting_approval": awaiting,
                    "missing_timesheet": missing, "exceptions": exceptions},
    }


@router.get("/payroll/periods/{period_id}/employee/{staff_id}")
async def employee_detail(period_id: str, staff_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    staff = await db.staff_members.find_one({"organization_id": org_id, "id": staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "staff not found")
    row = await _build_row(org_id, staff, period)
    days = await db.attendance_daily.find(
        {"organization_id": org_id, "staff_id": staff_id,
         "date": {"$gte": period["start_date"], "$lte": period["end_date"]}}, {"_id": 0},
    ).sort("date", 1).to_list(60)
    row["days"] = days
    return row


# ───────────────────────── submit / approve / return ─────────────────────────
async def _do_submit(org_id: str, period: dict, staff_id: str, declaration: bool, by: str):
    if not declaration:
        raise HTTPException(400, "declaration is required")
    if period["status"] == "locked":
        raise HTTPException(409, "period is locked")
    totals = await period_summary(org_id, staff_id, period["start_date"], period["end_date"])
    await db.pay_period_timesheets.update_one(
        {"organization_id": org_id, "period_id": period["id"], "staff_id": staff_id},
        {"$set": {"organization_id": org_id, "period_id": period["id"], "staff_id": staff_id,
                  "status": "submitted", "declaration": True, "totals": totals,
                  "submitted_at": _now().isoformat(), "submitted_by": by, "returned_reason": None},
         "$setOnInsert": {"id": str(uuid4()), "created_at": _now().isoformat()}},
        upsert=True,
    )
    return totals


class SubmitBody(BaseModel):
    staff_id: str
    declaration: bool = True


@router.post("/payroll/periods/{period_id}/submit")
async def submit(period_id: str, body: SubmitBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    totals = await _do_submit(org_id, period, body.staff_id, body.declaration, user.get("email"))
    return {"ok": True, "totals": totals}


@router.post("/payroll/periods/{period_id}/approve")
async def approve(period_id: str, staff_id: str = Body(..., embed=True), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    if period["status"] == "locked":
        raise HTTPException(409, "period is locked")
    ts = await _timesheet(org_id, period_id, staff_id)
    if not ts or ts.get("status") not in ("submitted", "returned"):
        raise HTTPException(409, "employee has not submitted this period")
    await db.pay_period_timesheets.update_one(
        {"organization_id": org_id, "period_id": period_id, "staff_id": staff_id},
        {"$set": {"status": "approved", "approved_by": user.get("email"),
                  "approved_at": _now().isoformat(), "returned_reason": None}},
    )
    return {"ok": True}


@router.post("/payroll/periods/{period_id}/return")
async def return_for_correction(period_id: str, staff_id: str = Body(...), reason: str = Body(...),
                                user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    if period["status"] == "locked":
        raise HTTPException(409, "period is locked")
    if not (reason or "").strip():
        raise HTTPException(400, "reason is required")
    ts = await _timesheet(org_id, period_id, staff_id)
    if not ts:
        raise HTTPException(409, "no submission to return")
    await db.pay_period_timesheets.update_one(
        {"organization_id": org_id, "period_id": period_id, "staff_id": staff_id},
        {"$set": {"status": "returned", "returned_reason": reason.strip(),
                  "returned_by": user.get("email"), "returned_at": _now().isoformat()}},
    )
    return {"ok": True}


@router.post("/payroll/periods/{period_id}/approve-ready")
async def approve_ready(period_id: str, user: dict = Depends(get_current_user)):
    """Bulk-approve every employee who has submitted and carries no blocking
    exception, leaving payroll only the genuine exceptions to review."""
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    if period["status"] == "locked":
        raise HTTPException(409, "period is locked")
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).to_list(1000)
    approved, skipped = 0, []
    for s in staff:
        row = await _build_row(org_id, s, period, recompute=False)
        if row["status"] not in ("submitted", "returned"):
            continue
        blocking = [e for e in row["exceptions"] if e != "missing_approval"]
        if blocking:
            skipped.append({"staff_id": s["id"], "full_name": s.get("full_name"), "reasons": blocking})
            continue
        await db.pay_period_timesheets.update_one(
            {"organization_id": org_id, "period_id": period_id, "staff_id": s["id"]},
            {"$set": {"status": "approved", "approved_by": user.get("email"),
                      "approved_at": _now().isoformat(), "returned_reason": None}},
        )
        approved += 1
    return {"approved": approved, "skipped": skipped, "skipped_count": len(skipped)}
@router.post("/payroll/periods/{period_id}/lock")
async def lock_period(period_id: str, user: dict = Depends(get_current_user)):
    """Freeze an immutable payroll snapshot (§39/§42). Later attendance edits
    can never silently alter these historical figures."""
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    if period["status"] == "locked":
        raise HTTPException(409, "already locked")
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).to_list(1000)
    snap_rows = []
    for s in staff:
        profile = await _resolve_profile(org_id, s)
        totals = await period_summary(org_id, s["id"], period["start_date"], period["end_date"])
        snap_rows.append({"staff_id": s["id"], "full_name": s.get("full_name"),
                          "payroll_number": profile.get("payroll_number"), "totals": totals})
        await db.pay_period_timesheets.update_one(
            {"organization_id": org_id, "period_id": period_id, "staff_id": s["id"]},
            {"$set": {"organization_id": org_id, "period_id": period_id, "staff_id": s["id"],
                      "status": "locked", "snapshot_totals": totals},
             "$setOnInsert": {"id": str(uuid4()), "created_at": _now().isoformat()}},
            upsert=True,
        )
    snap = {"id": str(uuid4()), "organization_id": org_id, "period_id": period_id,
            "locked_by": user.get("email"), "locked_at": _now().isoformat(),
            "rows": snap_rows, "period_name": period.get("name")}
    await db.payroll_snapshots.insert_one(snap.copy())
    await db.pay_periods.update_one({"organization_id": org_id, "id": period_id},
                                    {"$set": {"status": "locked", "locked_at": snap["locked_at"],
                                              "locked_by": user.get("email"), "snapshot_id": snap["id"]}})
    return {"ok": True, "snapshot_id": snap["id"], "employees": len(snap_rows)}


class AdjustmentBody(BaseModel):
    staff_id: str
    category: str
    old_value: float | str | None = None
    new_value: float | str
    reason: str


@router.post("/payroll/periods/{period_id}/adjustment")
async def add_adjustment(period_id: str, body: AdjustmentBody, user: dict = Depends(get_current_user)):
    """Post-lock correction (§39/§84) — recorded against the locked period,
    never mutates the immutable snapshot."""
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    if period["status"] != "locked":
        raise HTTPException(409, "adjustments only apply to locked periods")
    if not (body.reason or "").strip():
        raise HTTPException(400, "reason is required")
    doc = {"id": str(uuid4()), "organization_id": org_id, "period_id": period_id,
           "authoriser": user.get("email"), "created_at": _now().isoformat(), **body.dict()}
    await db.payroll_adjustments.insert_one(doc.copy())
    return _clean(doc)


@router.get("/payroll/periods/{period_id}/adjustments")
async def list_adjustments(period_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    rows = await db.payroll_adjustments.find(
        {"organization_id": org_id, "period_id": period_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return {"adjustments": rows}


# ───────────────────────── validation + export ─────────────────────────
@router.get("/payroll/periods/{period_id}/validation")
async def validation(period_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    staff = await db.staff_members.find({"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0}).to_list(1000)
    rows = [await _build_row(org_id, s, period) for s in staff]
    with_ot = sum(1 for r in rows if r["totals"]["overtime_raw"] > 0)
    return {
        "employees": len(rows),
        "payroll_ids_found": sum(1 for r in rows if r["payroll_number"]),
        "missing_approvals": sum(1 for r in rows if r["status"] != "approved" and period["status"] != "locked"),
        "missing_entries": sum(1 for r in rows if r["totals"]["missing"] > 0),
        "with_overtime": with_ot,
        "unpaid_adjustments": sum(1 for r in rows if r["totals"]["unpaid_days"] > 0),
    }


@router.get("/payroll/periods/{period_id}/export")
async def export_period(period_id: str, format: str = Query("csv"), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    period = await _period(org_id, period_id)
    mp = await db.payroll_field_mappings.find_one({"organization_id": org_id}, {"_id": 0})
    fields = (mp or {}).get("fields") or DEFAULT_FIELD_MAPPING
    staff = await db.staff_members.find({"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0}).sort("full_name", 1).to_list(1000)
    rows = [await _build_row(org_id, s, period) for s in staff]

    def cell(row, source):
        if source in ("payroll_number", "full_name"):
            return row.get(source) or ""
        return row["totals"].get(source, "")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f["column"] for f in fields])
    for r in rows:
        w.writerow([cell(r, f["source"]) for f in fields])
    fname = f"payroll-{period.get('name', period_id)}.csv".replace(" ", "_").replace("/", "-")
    return Response(content=buf.getvalue().encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


# ───────────────────────── reports (§43) ─────────────────────────
@router.get("/payroll/reports")
async def payroll_reports(date_from: str = Query(...), date_to: str = Query(...),
                          user: dict = Depends(get_current_user)):
    """Aggregated payroll reporting over any date range — hours/overtime/absence
    by employee and department, attendance rate, and submission performance.
    Reads the spine; no separate reporting engine."""
    _require_manager(user)
    org_id = _org(user)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).sort("full_name", 1).to_list(1000)

    by_emp = []
    dept: dict[str, dict] = {}
    tot = {"worked": 0.0, "regular": 0.0, "overtime": 0.0, "holiday": 0.0, "sick": 0.0,
           "unpaid_days": 0, "expected": 0.0, "expected_days": 0, "present_days": 0}
    for s in staff:
        profile = await _resolve_profile(org_id, s)
        t = await period_summary(org_id, s["id"], date_from, date_to)
        ot = t["overtime_approved"] or t["overtime_raw"]
        rate = round(100 * t["present_days"] / t["expected_days"], 1) if t["expected_days"] else 100.0
        d = s.get("department") or "Unassigned"
        by_emp.append({"staff_id": s["id"], "full_name": s.get("full_name"), "department": d,
                       "payroll_number": profile.get("payroll_number"),
                       "worked": t["worked"], "regular": t["regular"], "overtime": ot,
                       "holiday": t["holiday"], "sick": t["sick"], "unpaid_days": t["unpaid_days"],
                       "expected": t["expected"], "missing": t["missing"], "attendance_rate": rate})
        g = dept.setdefault(d, {"department": d, "headcount": 0, "worked": 0.0, "overtime": 0.0,
                                "holiday": 0.0, "sick": 0.0, "expected_days": 0, "present_days": 0})
        g["headcount"] += 1
        g["worked"] += t["worked"]; g["overtime"] += ot
        g["holiday"] += t["holiday"]; g["sick"] += t["sick"]
        g["expected_days"] += t["expected_days"]; g["present_days"] += t["present_days"]
        tot["worked"] += t["worked"]; tot["regular"] += t["regular"]; tot["overtime"] += ot
        tot["holiday"] += t["holiday"]; tot["sick"] += t["sick"]; tot["unpaid_days"] += t["unpaid_days"]
        tot["expected"] += t["expected"]; tot["expected_days"] += t["expected_days"]; tot["present_days"] += t["present_days"]

    by_dept = []
    for g in dept.values():
        g["worked"] = round(g["worked"], 1); g["overtime"] = round(g["overtime"], 1)
        g["holiday"] = round(g["holiday"], 1); g["sick"] = round(g["sick"], 1)
        g["attendance_rate"] = round(100 * g["present_days"] / g["expected_days"], 1) if g["expected_days"] else 100.0
        by_dept.append(g)
    for k in ("worked", "regular", "overtime", "holiday", "sick", "expected"):
        tot[k] = round(tot[k], 1)
    tot["attendance_rate"] = round(100 * tot["present_days"] / tot["expected_days"], 1) if tot["expected_days"] else 100.0

    # Submission + approval performance across periods overlapping the range.
    periods = await db.pay_periods.find(
        {"organization_id": org_id, "start_date": {"$lte": date_to}, "end_date": {"$gte": date_from}},
        {"_id": 0},
    ).to_list(50)
    on_time = late = missing_sub = appr_on = appr_late = 0
    for p in periods:
        ts_rows = await db.pay_period_timesheets.find(
            {"organization_id": org_id, "period_id": p["id"]}, {"_id": 0},
        ).to_list(1000)
        submitted_ids = set()
        for ts in ts_rows:
            if ts.get("submitted_at"):
                submitted_ids.add(ts["staff_id"])
                dl = p.get("employee_deadline")
                if dl and ts["submitted_at"][:10] > dl:
                    late += 1
                else:
                    on_time += 1
            if ts.get("approved_at"):
                mdl = p.get("manager_deadline")
                if mdl and ts["approved_at"][:10] > mdl:
                    appr_late += 1
                else:
                    appr_on += 1
        missing_sub += max(0, len(staff) - len(submitted_ids))

    adjustments = await db.payroll_adjustments.count_documents({"organization_id": org_id})
    return {
        "range": {"from": date_from, "to": date_to},
        "totals": tot,
        "by_employee": sorted(by_emp, key=lambda x: -x["worked"]),
        "by_department": sorted(by_dept, key=lambda x: -x["worked"]),
        "submissions": {"on_time": on_time, "late": late, "missing": missing_sub,
                        "approvals_on_time": appr_on, "approvals_late": appr_late,
                        "periods": len(periods)},
        "adjustments": adjustments,
    }
