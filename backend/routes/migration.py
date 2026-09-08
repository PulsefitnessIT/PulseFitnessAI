"""Spreadsheet Migration — import the legacy TIME SHEETS 2026 and Attendance
Request workbooks into the Attendance Spine (§74–§76).

- Matches existing employees (never creates duplicate staff).
- Converts legacy status codes (IN/HOL/BH/SICK/COMP/OFF) to canonical statuses.
- Dry-run PREVIEW returns a reconciliation report (matched / conflict / new)
  before anything is written; nothing is decided silently (§75).
- COMMIT writes daily records tagged with their legacy source (§73/§76).
"""
from __future__ import annotations

import io
import logging
from datetime import date
from uuid import uuid4

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from utils.auth import get_current_user
from utils.database import db
from routes.staffing import _now, _org, _require_manager
from routes.attendance import ATTENDANCE_STATUSES, set_employee_entry, recompute_day

logger = logging.getLogger(__name__)
router = APIRouter()

CODE_TO_STATUS = {
    "IN": "working", "HOL": "holiday", "BH": "bank_holiday",
    "SICK": "sick", "COMP": "comp", "OFF": "off",
    "UNP": "unpaid_leave", "TRN": "training", "WFH": "wfh",
}
MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def _norm(name: str | None) -> str:
    return " ".join(str(name or "").strip().lower().split())


async def _staff_index(org_id: str) -> dict:
    rows = await db.staff_members.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "full_name": 1, "active": 1},
    ).to_list(2000)
    return {_norm(r.get("full_name")): r for r in rows if r.get("full_name")}


# ───────────────────────── parsers ─────────────────────────
def parse_attendance(data: bytes, year_filter: int | None = None) -> list[dict]:
    """→ [{name, date, code, status}] from the grid workbook."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    out = []
    for sheet in wb.sheetnames:
        try:
            year = int(str(sheet).strip())
        except Exception:
            continue
        if year_filter and year != year_filter:
            continue
        ws = wb[sheet]
        # Build column → date map from row1 (month) + row2 (day-of-month).
        col_date, cur_month = {}, None
        for c in range(2, ws.max_column + 1):
            mlabel = ws.cell(1, c).value
            if mlabel and str(mlabel).strip().lower() in MONTHS:
                cur_month = MONTHS[str(mlabel).strip().lower()]
            day = ws.cell(2, c).value
            if cur_month and isinstance(day, (int, float)):
                try:
                    col_date[c] = date(year, cur_month, int(day)).isoformat()
                except Exception:
                    pass
        for r in range(4, ws.max_row + 1):
            name = ws.cell(r, 1).value
            if not name or not str(name).strip():
                continue
            for c, diso in col_date.items():
                code = ws.cell(r, c).value
                if not code:
                    continue
                code = str(code).strip().upper()
                if code not in CODE_TO_STATUS:
                    continue
                out.append({"name": str(name).strip(), "date": diso, "code": code,
                            "status": CODE_TO_STATUS[code]})
    return out


def _cell_hours(v) -> float:
    import datetime as _dt
    if v is None:
        return 0.0
    if isinstance(v, _dt.timedelta):
        return round(v.total_seconds() / 3600.0, 2)
    if isinstance(v, _dt.time):
        return round(v.hour + v.minute / 60.0, 2)
    try:
        return float(v)
    except Exception:
        return 0.0


def _cell_hm(v) -> str | None:
    import datetime as _dt
    if isinstance(v, _dt.time):
        return f"{v.hour:02d}:{v.minute:02d}"
    return None


def _parse_ddmmyy(s) -> str | None:
    try:
        parts = str(s).strip().split(".")
        if len(parts) != 3:
            return None
        d, m, y = (int(p) for p in parts)
        if y < 100:
            y += 2000
        return date(y, m, d).isoformat()
    except Exception:
        return None


def parse_timesheet(data: bytes) -> dict:
    """→ {employee_name, department, days:[{date,start,finish,break_minutes,pt,classes,total}]}"""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    name = dept = None
    days = []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        if name is None:
            # Name / Department live to the right of their labels on row 1.
            for c in range(1, ws.max_column + 1):
                lbl = str(ws.cell(1, c).value or "").strip().lower()
                if lbl.startswith("name") and not name:
                    for cc in range(c + 1, ws.max_column + 1):
                        v = ws.cell(1, cc).value
                        if not v:
                            continue
                        sv = str(v).strip()
                        if ":" in sv or sv.lower().startswith("department"):
                            break  # hit the next label, no name entered
                        name = sv; break
                if lbl.startswith("department") and not dept:
                    for cc in range(c + 1, ws.max_column + 1):
                        v = ws.cell(1, cc).value
                        if v and ":" not in str(v):
                            dept = str(v).strip(); break
        for r in range(8, ws.max_row + 1):
            diso = _parse_ddmmyy(ws.cell(r, 1).value)
            if not diso:
                continue
            start = _cell_hm(ws.cell(r, 3).value)
            finish = _cell_hm(ws.cell(r, 4).value)
            brk = _cell_hours(ws.cell(r, 5).value)
            pt = _cell_hours(ws.cell(r, 6).value)
            classes = _cell_hours(ws.cell(r, 7).value)
            total = _cell_hours(ws.cell(r, 8).value)
            if total <= 0:
                continue  # no hours recorded → nothing to import for this day
            days.append({"date": diso, "start": start, "finish": finish,
                         "break_minutes": int(brk * 60), "pt": pt, "classes": classes,
                         "total": total})
    return {"employee_name": name, "department": dept, "days": days}


# ───────────────────────── attendance import ─────────────────────────
@router.post("/migration/attendance/preview")
async def preview_attendance(file: UploadFile = File(...), year: int | None = Form(None),
                             user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    records = parse_attendance(await file.read(), year)
    idx = await _staff_index(org_id)
    names = sorted({r["name"] for r in records})
    matched = [n for n in names if _norm(n) in idx]
    unmatched = [n for n in names if _norm(n) not in idx]
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "type": "attendance", "rows_parsed": len(records),
        "employees_matched": matched, "employees_unmatched": unmatched,
        "by_status": by_status,
        "sample": [{**r, "matched": _norm(r["name"]) in idx} for r in records[:25]],
        "date_range": {"from": min((r["date"] for r in records), default=None),
                       "to": max((r["date"] for r in records), default=None)},
    }


@router.post("/migration/attendance/commit")
async def commit_attendance(file: UploadFile = File(...), year: int | None = Form(None),
                            user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    records = parse_attendance(await file.read(), year)
    idx = await _staff_index(org_id)
    written, skipped, unmatched = 0, 0, set()
    for r in records:
        staff = idx.get(_norm(r["name"]))
        if not staff:
            unmatched.add(r["name"]); skipped += 1; continue
        meta = ATTENDANCE_STATUSES.get(r["status"], {})
        await db.attendance_daily.update_one(
            {"organization_id": org_id, "staff_id": staff["id"], "date": r["date"]},
            {"$set": {"organization_id": org_id, "staff_id": staff["id"], "date": r["date"],
                      "actual_status": r["status"], "status_code": meta.get("legacy", r["code"]),
                      "source": "legacy_attendance", "manual_override": True,
                      "imported_from": "Legacy Attendance Spreadsheet",
                      "imported_at": _now().isoformat()},
             "$setOnInsert": {"id": str(uuid4()), "created_at": _now().isoformat(),
                              "expected_status": "working", "history": []}},
            upsert=True,
        )
        written += 1
    return {"written": written, "skipped": skipped, "unmatched": sorted(unmatched)}


# ───────────────────────── timesheet import ─────────────────────────
@router.post("/migration/timesheets/preview")
async def preview_timesheets(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    parsed = parse_timesheet(await file.read())
    idx = await _staff_index(org_id)
    staff = idx.get(_norm(parsed["employee_name"]))
    conflicts, matched = [], 0
    if staff:
        for d in parsed["days"]:
            existing = await db.attendance_daily.find_one(
                {"organization_id": org_id, "staff_id": staff["id"], "date": d["date"]}, {"_id": 0})
            # Reconcile against any leave/attendance already on the spine (§75).
            if existing and existing.get("actual_status") in ("holiday", "sick", "bank_holiday", "off") and d["total"] > 0:
                conflicts.append({"date": d["date"], "attendance": existing["actual_status"],
                                  "timesheet_hours": d["total"], "result": "CONFLICT"})
            else:
                matched += 1
    return {
        "type": "timesheet", "employee_name": parsed["employee_name"],
        "department": parsed["department"], "employee_matched": bool(staff),
        "days_parsed": len(parsed["days"]), "matched_days": matched,
        "conflicts": conflicts,
        "sample": parsed["days"][:25],
        "totals": {"hours": round(sum(d["total"] for d in parsed["days"]), 2),
                   "pt": round(sum(d["pt"] for d in parsed["days"]), 2),
                   "classes": round(sum(d["classes"] for d in parsed["days"]), 2)},
    }


@router.post("/migration/timesheets/commit")
async def commit_timesheets(file: UploadFile = File(...), overwrite_conflicts: bool = Form(False),
                            user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    parsed = parse_timesheet(await file.read())
    idx = await _staff_index(org_id)
    staff = idx.get(_norm(parsed["employee_name"]))
    if not staff:
        raise HTTPException(400, f"No matching employee for '{parsed['employee_name']}'. Add them first.")
    written, skipped_conflicts = 0, 0
    for d in parsed["days"]:
        existing = await db.attendance_daily.find_one(
            {"organization_id": org_id, "staff_id": staff["id"], "date": d["date"]}, {"_id": 0})
        if existing and existing.get("actual_status") in ("holiday", "sick", "bank_holiday", "off") \
                and d["total"] > 0 and not overwrite_conflicts:
            skipped_conflicts += 1
            continue
        if d["start"] and d["finish"]:
            await set_employee_entry(org_id, staff["id"], d["date"], d["start"], d["finish"], d["break_minutes"])
        # Store PT / Classes categories on the record (kept per §10).
        await db.attendance_daily.update_one(
            {"organization_id": org_id, "staff_id": staff["id"], "date": d["date"]},
            {"$set": {"organization_id": org_id, "staff_id": staff["id"], "date": d["date"],
                      "categories": {"pt": d["pt"], "classes": d["classes"]},
                      "imported_from": "Legacy Timesheet", "imported_at": _now().isoformat()},
             "$setOnInsert": {"id": str(uuid4()), "created_at": _now().isoformat(), "history": []}},
            upsert=True,
        )
        written += 1
    return {"written": written, "skipped_conflicts": skipped_conflicts,
            "employee": staff.get("full_name")}
