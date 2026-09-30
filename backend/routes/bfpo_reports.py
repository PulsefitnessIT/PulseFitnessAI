"""
MOD / BFPO — MOD Operations reporting.

Filterable operational reports (jobs/faults, planned servicing, SLA) for
Pulse Fitness MOD Operations staff, with PDF and Excel (xlsx) export.
Staff-only (reuses _require_staff → mod_operations module gate from routes.bfpo).
"""
from datetime import datetime, timezone
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from utils.database import db
from utils.svc_state import OPEN_STATES, PAUSED_PARTS
from routes.bfpo import BFPO_ORG_ID, _require_staff

router = APIRouter(prefix="/bfpo/staff/reports", tags=["MOD · BFPO Reports"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _base_filters(territory: str, site: str, frm: str, to: str) -> dict:
    q = {"organization_id": BFPO_ORG_ID}
    if territory:
        q["territory_id"] = territory
    if site:
        q["site_id"] = site
    return q


def _in_range(iso: str, frm: str, to: str) -> bool:
    if not iso:
        return not frm and not to
    d = iso[:10]
    if frm and d < frm:
        return False
    if to and d > to:
        return False
    return True


async def _jobs_report(territory, site, frm, to):
    q = {**_base_filters(territory, site, frm, to), "bfpo": True}
    rows_raw = await db.svc_cases.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    rows_raw = [c for c in rows_raw if _in_range(c.get("created_at"), frm, to)]
    now = _now()
    rows, by_prio, open_n, closed_n, safety_n = [], {"p1": 0, "p2": 0, "p3": 0, "p4": 0}, 0, 0, 0
    for c in rows_raw:
        is_open = c.get("status") in OPEN_STATES
        open_n += 1 if is_open else 0
        closed_n += 0 if is_open else 1
        by_prio[c.get("priority", "p3")] = by_prio.get(c.get("priority", "p3"), 0) + 1
        if c.get("safety_critical"):
            safety_n += 1
        rows.append({
            "Reference": c.get("reference"), "Title": c.get("title"),
            "Territory": c.get("territory_name"), "Site": c.get("site_name"),
            "Priority": (c.get("priority") or "").upper(), "Status": c.get("status"),
            "Safety Critical": "Yes" if c.get("safety_critical") else "No",
            "Engineer": c.get("assigned_engineer_name") or "Unallocated",
            "Logged": (c.get("created_at") or "")[:10], "Closed": (c.get("closed_at") or "")[:10],
        })
    summary = [
        {"label": "Total jobs", "value": len(rows_raw)},
        {"label": "Open", "value": open_n}, {"label": "Completed", "value": closed_n},
        {"label": "Safety-critical", "value": safety_n},
        {"label": "P1", "value": by_prio["p1"]}, {"label": "P2", "value": by_prio["p2"]},
        {"label": "P3", "value": by_prio["p3"]}, {"label": "P4", "value": by_prio["p4"]},
    ]
    return {"title": "Jobs & Faults Report", "summary": summary,
            "columns": ["Reference", "Title", "Territory", "Site", "Priority", "Status", "Safety Critical", "Engineer", "Logged", "Closed"],
            "rows": rows}


async def _services_report(territory, site, frm, to):
    q = _base_filters(territory, site, frm, to)
    svcs = await db.bfpo_ppm_services.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    svcs = [s for s in svcs if _in_range(s.get("created_at"), frm, to)]
    rows, completed, assets, faults = [], 0, 0, 0
    for s in svcs:
        insp = await db.bfpo_ppm_inspections.find(
            {"service_id": s["id"], "organization_id": BFPO_ORG_ID}, {"_id": 0, "status": 1}).to_list(1000)
        f = sum(1 for i in insp if i.get("status") == "failed")
        faults += f
        assets += len(insp)
        if s.get("status") == "completed":
            completed += 1
        rows.append({
            "Reference": s.get("reference"), "Territory": s.get("territory_name"),
            "Site": s.get("site_name"), "Status": s.get("status"),
            "Assets": len(insp), "Faults Raised": f,
            "Engineer": s.get("assigned_engineer_name") or "Unallocated",
            "Due": s.get("due_date") or "", "Completed": (s.get("completed_at") or "")[:10],
        })
    summary = [
        {"label": "Services", "value": len(svcs)}, {"label": "Completed", "value": completed},
        {"label": "In progress/due", "value": len(svcs) - completed},
        {"label": "Assets inspected", "value": assets}, {"label": "Faults raised", "value": faults},
    ]
    return {"title": "Planned Servicing Report", "summary": summary,
            "columns": ["Reference", "Territory", "Site", "Status", "Assets", "Faults Raised", "Engineer", "Due", "Completed"],
            "rows": rows}


async def _sla_report(territory, site, frm, to):
    q = {**_base_filters(territory, site, frm, to), "bfpo": True}
    cases = await db.svc_cases.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    cases = [c for c in cases if _in_range(c.get("created_at"), frm, to)]
    now = _now()
    rows, on_time, late, open_breach, open_ok = [], 0, 0, 0, 0
    for c in cases:
        target = c.get("sla_resolve_at")
        is_open = c.get("status") in OPEN_STATES
        if is_open:
            breached = bool(target and target < now)
            status = "Open — breached" if breached else "Open — on track"
            open_breach += 1 if breached else 0
            open_ok += 0 if breached else 1
        else:
            closed = c.get("closed_at") or c.get("completed_at")
            breached = bool(target and closed and closed > target)
            status = "Resolved late" if breached else "Resolved on time"
            late += 1 if breached else 0
            on_time += 0 if breached else 1
        rows.append({
            "Reference": c.get("reference"), "Site": c.get("site_name"),
            "Priority": (c.get("priority") or "").upper(),
            "SLA Target": (target or "")[:16].replace("T", " "),
            "Resolved": ((c.get("closed_at") or c.get("completed_at") or "")[:16]).replace("T", " "),
            "Outcome": status,
        })
    total_resolved = on_time + late
    compliance = round((on_time / total_resolved) * 100) if total_resolved else 100
    summary = [
        {"label": "SLA compliance", "value": f"{compliance}%"},
        {"label": "Resolved on time", "value": on_time}, {"label": "Resolved late", "value": late},
        {"label": "Open — breached", "value": open_breach}, {"label": "Open — on track", "value": open_ok},
    ]
    return {"title": "SLA Report", "summary": summary,
            "columns": ["Reference", "Site", "Priority", "SLA Target", "Resolved", "Outcome"],
            "rows": rows}


async def _build(report: str, territory, site, frm, to):
    if report == "services":
        return await _services_report(territory, site, frm, to)
    if report == "sla":
        return await _sla_report(territory, site, frm, to)
    return await _jobs_report(territory, site, frm, to)


@router.get("")
async def get_report(
    report: str = Query("jobs"), territory: str = Query(""), site: str = Query(""),
    frm: str = Query("", alias="from"), to: str = Query(""), user=Depends(_require_staff),
):
    data = await _build(report, territory, site, frm, to)
    data["generated_at"] = _now()
    data["count"] = len(data["rows"])
    return data


@router.get("/export")
async def export_report(
    report: str = Query("jobs"), fmt: str = Query("pdf"), territory: str = Query(""),
    site: str = Query(""), frm: str = Query("", alias="from"), to: str = Query(""),
    user=Depends(_require_staff),
):
    data = await _build(report, territory, site, frm, to)
    fname = f"{data['title'].replace(' ', '_')}_{_now()[:10]}"
    if fmt == "xlsx":
        content = _to_xlsx(data)
        return Response(content=content,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    content = _to_pdf(data, {"territory": territory, "site": site, "from": frm, "to": to})
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}.pdf"'})


def _to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    head_fill = PatternFill("solid", fgColor="0F172A")
    ws.append([data["title"]])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Generated {_now()[:16].replace('T', ' ')}"])
    ws.append([])
    ws.append(["Summary"])
    ws["A4"].font = Font(bold=True)
    for s in data["summary"]:
        ws.append([s["label"], s["value"]])
    ws.append([])
    hdr_row = ws.max_row + 1
    ws.append(data["columns"])
    for cell in ws[hdr_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
    for r in data["rows"]:
        ws.append([r.get(c, "") for c in data["columns"]])
    for i, col in enumerate(data["columns"], 1):
        width = max(len(str(col)), *(len(str(r.get(col, ""))) for r in data["rows"])) if data["rows"] else len(str(col))
        ws.column_dimensions[ws.cell(row=hdr_row, column=i).column_letter].width = min(width + 2, 40)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_pdf(data: dict, filters: dict) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    w, h = landscape(A4)
    ink = colors.HexColor("#0f172a")
    cyan = colors.HexColor("#0891b2")
    c.setFillColor(ink)
    c.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, h - 14 * mm, "PULSE FITNESS — MOD Operations")
    c.setFillColor(cyan)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(w - 15 * mm, h - 14 * mm, data["title"])
    y = h - 30 * mm
    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 8)
    fstr = " · ".join(f"{k}: {v}" for k, v in filters.items() if v) or "All records"
    c.drawString(15 * mm, y, f"Generated {_now()[:16].replace('T', ' ')}   |   Filters: {fstr}")
    y -= 8 * mm
    # summary chips
    c.setFont("Helvetica-Bold", 9)
    x = 15 * mm
    for s in data["summary"]:
        txt = f"{s['label']}: {s['value']}"
        c.setFillColor(colors.HexColor("#f1f5f9"))
        cw = c.stringWidth(txt, "Helvetica-Bold", 9) + 8 * mm
        c.roundRect(x, y - 2 * mm, cw, 7 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(ink)
        c.drawString(x + 4 * mm, y, txt)
        x += cw + 3 * mm
        if x > w - 40 * mm:
            x = 15 * mm; y -= 10 * mm
    y -= 12 * mm
    cols = data["columns"]
    n = len(cols)
    avail = w - 30 * mm
    cwid = avail / n
    c.setFillColor(cyan)
    c.setFont("Helvetica-Bold", 7)
    for i, col in enumerate(cols):
        c.drawString(15 * mm + i * cwid, y, str(col)[:int(cwid / 4.4)])
    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(15 * mm, y, w - 15 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.setFillColor(ink)
    for r in data["rows"]:
        if y < 15 * mm:
            c.showPage(); y = h - 20 * mm
            c.setFont("Helvetica", 7); c.setFillColor(ink)
        for i, col in enumerate(cols):
            c.drawString(15 * mm + i * cwid, y, str(r.get(col, ""))[:int(cwid / 4.4)])
        y -= 5 * mm
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = ["router"]
