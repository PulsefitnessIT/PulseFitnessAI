"""Payroll monthly timesheet workbook — a 1:1 replica of the customer's
"TIME SHEETS 2026.xlsx" template (layout, [h]:mm formats and every formula),
pre-filled per staff member and with the yellow hand-in (deadline) Friday.

Public API:
  default_year_schedule(year)        -> list[12] month dicts (auto 5-4-4 calendar)
  build_month_timesheet_xlsx(...)    -> bytes (single staff, single month sheet)
"""
from __future__ import annotations

import io
from datetime import date, time, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# 5-4-4 quarterly payroll calendar (weeks per month, Jan→5).
WEEKS_PATTERN = [5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4]

_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_INPUT_FILL = PatternFill("solid", fgColor="F2F2F2")
_YELLOW = PatternFill("solid", fgColor="FFFF00")
_HEAD = PatternFill("solid", fgColor="1F3864")


def _label(year: int, month_idx0: int) -> str:
    return f"{MONTH_ABBR[month_idx0]}{str(year)[2:]}"


def default_year_schedule(year: int) -> list[dict]:
    """Auto-generate the 12 monthly payroll periods for a year using a
    contiguous, Monday-start 5-4-4 calendar. January ends on the 2nd Sunday
    of January; each subsequent period follows on immediately. The hand-in
    (yellow) date is the Friday of each period's final week. Payroll can
    override any field afterwards."""
    # 2nd Sunday of January = January period end.
    d = date(year, 1, 1)
    sundays = [d + timedelta(days=i) for i in range(31) if (d + timedelta(days=i)).weekday() == 6]
    jan_end = sundays[1]
    start = jan_end - timedelta(days=WEEKS_PATTERN[0] * 7 - 1)  # Monday
    out = []
    for i in range(12):
        weeks = WEEKS_PATTERN[i]
        end = start + timedelta(days=weeks * 7 - 1)  # Sunday
        hand_in = end - timedelta(days=2)            # Friday of final week
        out.append({
            "month": i + 1,
            "label": _label(year, i),
            "period_start": start.isoformat(),
            "weeks": weeks,
            "hand_in": hand_in.isoformat(),
        })
        start = end + timedelta(days=1)
    return out


def _time_from_hhmm(v) -> time:
    try:
        h, m = (int(x) for x in str(v).split(":")[:2])
        return time(h % 24, m % 60)
    except Exception:
        return time(0, 0)


def _time_from_minutes(mins) -> time:
    try:
        mins = int(round(float(mins or 0)))
    except Exception:
        mins = 0
    return time((mins // 60) % 24, mins % 60)


def _time_from_hours(hrs) -> time:
    try:
        total = int(round(float(hrs or 0) * 60))
    except Exception:
        total = 0
    return time((total // 60) % 24, total % 60)


def build_month_timesheet_xlsx(
    *, staff_name: str, department: str, weekly_hours: float,
    period_start: date, weeks: int, hand_in: date | None,
    year: int, month: int, entries_by_date: dict, columns: list | None = None,
) -> bytes:
    """Build one month's timesheet exactly like the template, pre-filled.

    entries_by_date: {iso_date: {start,finish,break_minutes,pt_classes}}."""
    wb = Workbook()
    ws = wb.active
    ws.title = _label(year, month - 1)

    widths = {"A": 10.6, "B": 12.4, "C": 10.4, "D": 13.4, "E": 10.4,
              "F": 10.4, "G": 9.0, "H": 12.6, "I": 19.6, "J": 22.6}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Header block
    ws["A1"] = "Name:"
    ws["B1"] = staff_name or ""
    ws["D1"] = "Department:"
    ws["E1"] = department or ""
    for a in ("B1", "E1"):
        ws[a].fill = _INPUT_FILL
        ws[a].border = _BORDER
    ws["A3"] = "Standard Hours"
    ws["C3"] = round(float(weekly_hours or 0), 2)
    ws["C3"].fill = _INPUT_FILL
    ws["C3"].border = _BORDER
    ws["D3"] = "=C3/24"
    ws["D3"].number_format = "[h]:mm"
    ws["A4"] = "No of Weeks"
    ws["D4"] = int(weeks)

    # Activity columns (role-tailored). Fall back to PT+Classes if unspecified.
    if columns is None:
        columns = [{"key": "pt", "label": "PT", "unit": "hours"},
                   {"key": "classes", "label": "Classes", "unit": "hours"}]
    n_act = len(columns)
    act_first = 6                        # first activity column index (F)
    total_col = act_first + n_act        # TOTAL (hours) column index
    emp_col = total_col + 1
    duty_col = total_col + 2
    TL = get_column_letter(total_col)

    # widen activity/signature columns
    for i in range(n_act):
        ws.column_dimensions[get_column_letter(act_first + i)].width = 12.5
    ws.column_dimensions[TL].width = 12.6
    ws.column_dimensions[get_column_letter(emp_col)].width = 19.6
    ws.column_dimensions[get_column_letter(duty_col)].width = 22.6

    # Column headers (row 6)
    heads = ["DATE", "DAY", "START", "FINISH", "Break"] \
        + [c["label"] for c in columns] + ["TOTAL", "EMPLOYEE ", "DUTY OFFICER"]
    for ci, txt in enumerate(heads, start=1):
        cell = ws.cell(6, ci, txt)
        cell.font = Font(bold=True)
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    ws.cell(7, total_col, "HOURS").font = Font(bold=True)
    ws.cell(7, emp_col, "SIGNATURE").font = Font(bold=True)
    ws.cell(7, duty_col, "SIGNATURE").font = Font(bold=True)
    for ci in range(1, duty_col + 1):
        ws.cell(7, ci).border = _BORDER

    hand_in_iso = hand_in.isoformat() if hand_in else None
    total_rows: list[int] = []
    day_blocks: list[tuple[int, int]] = []   # (first_day_row, last_day_row) per week
    r = 8
    cur = period_start
    for _wk in range(int(weeks)):
        block_first = r
        for _d in range(7):
            ws.cell(r, 1, f"{cur.day}.{cur.month}.{str(cur.year)[2:]}")
            ws.cell(r, 2, cur.strftime("%A").upper())
            ent = entries_by_date.get(cur.isoformat(), {})
            ws.cell(r, 3, _time_from_hhmm(ent.get("start")))
            ws.cell(r, 4, _time_from_hhmm(ent.get("finish")))
            ws.cell(r, 5, _time_from_minutes(ent.get("break_minutes")))
            acts = ent.get("acts") if isinstance(ent.get("acts"), dict) else {}
            for i, col in enumerate(columns):
                ci = act_first + i
                k = col["key"]
                a = acts.get(k) if isinstance(acts.get(k), dict) else None
                if a is not None:
                    mins, done = float(a.get("mins") or 0), bool(a.get("done"))
                elif k == "pt":  # legacy combined value
                    mins, done = float(ent.get("pt_classes") or 0) * 60, bool(ent.get("pt_classes"))
                elif k == "van_check":
                    mins, done = 0.0, bool(ent.get("van_check"))
                else:
                    mins, done = 0.0, False
                cell = ws.cell(r, ci)
                if mins > 0:
                    cell.value = _time_from_minutes(mins)
                    cell.number_format = "h:mm"
                elif done:
                    cell.value = "Y"
                    cell.alignment = Alignment(horizontal="center")
                else:
                    cell.value = time(0, 0)
                    cell.number_format = "h:mm"
            hc = ws.cell(r, total_col, f"=(+D{r}-C{r})-E{r}")
            hc.number_format = "[h]:mm"
            for ci in range(1, total_col + 1):
                ws.cell(r, ci).border = _BORDER
            for ci in (3, 4, 5):
                ws.cell(r, ci).number_format = "h:mm"
            if hand_in_iso and cur.isoformat() == hand_in_iso:
                ws.cell(r, 1).fill = _YELLOW
                ws.cell(r, 2).fill = _YELLOW
            cur += timedelta(days=1)
            r += 1
        # weekly TOTAL row — sum each activity column + the hours total
        day_blocks.append((block_first, r - 1))
        tc = ws.cell(r, 4, "TOTAL")
        tc.alignment = Alignment(horizontal="right")
        for ci in list(range(act_first, act_first + n_act)) + [total_col]:
            col = get_column_letter(ci)
            fc = ws.cell(r, ci, f"=SUM({col}{block_first}:{col}{r - 1})")
            fc.number_format = "[h]:mm"
            fc.border = _BORDER
        total_rows.append(r)
        r += 1

    # Footer
    fr = r

    # Per-activity monthly totals, aligned under each activity column. Hour-based
    # columns sum to [h]:mm; tick columns show a count of "Y" (worked) days.
    mt = ws.cell(fr, 4, "MONTHLY TOTAL")
    mt.font = Font(bold=True)
    mt.alignment = Alignment(horizontal="right")
    mt.border = _BORDER
    for i, col in enumerate(columns):
        ci = act_first + i
        cl = get_column_letter(ci)
        cell = ws.cell(fr, ci)
        if str(col.get("unit")) == "tick_hours":
            parts = "+".join(f'COUNTIF({cl}{a}:{cl}{b},"Y")' for a, b in day_blocks)
            cell.value = f"={parts}" if parts else 0
            cell.number_format = '0" days"'
        else:
            parts = "+".join(f"SUM({cl}{a}:{cl}{b})" for a, b in day_blocks)
            cell.value = f"={parts}" if parts else 0
            cell.number_format = "[h]:mm"
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.border = _BORDER
    fr += 2

    lab_col, val_col = emp_col, duty_col   # labels under EMPLOYEE col, values under DUTY
    LV = get_column_letter(val_col)
    gt = "+".join(f"{TL}{tr}" for tr in total_rows)
    ws.cell(fr, lab_col, "Grand Total Number of hours").alignment = Alignment(horizontal="right")
    ws.cell(fr, val_col, f"={gt}").number_format = "[h]:mm"
    ws.cell(fr + 2, lab_col, "Total Standard Hours ").alignment = Alignment(horizontal="right")
    ws.cell(fr + 2, val_col, "=D3*D4").number_format = "[h]:mm"
    ws.cell(fr + 4, lab_col, "Overtime").alignment = Alignment(horizontal="right")
    ws.cell(fr + 4, val_col, f'=IF({LV}{fr}>{LV}{fr + 2},{LV}{fr}-{LV}{fr + 2},"")').number_format = "[h]:mm"
    ws.cell(fr + 6, lab_col, "Unpaid Leave").alignment = Alignment(horizontal="right")
    ws.cell(fr + 6, val_col, f'=IF({LV}{fr + 2}>{LV}{fr},{LV}{fr + 2}-{LV}{fr},"")').number_format = "[h]:mm"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def safe_filename(staff_name: str, label: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in (staff_name or "Staff")).strip()
    return f"Timesheet {label} - {clean or 'Staff'}.xlsx"
