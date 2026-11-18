"""Engineer report fields shared by every engineer close-out (service desk, MOD jobs, MOD PPM)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

_UK = ZoneInfo("Europe/London")


def _iso(v) -> str:
    if not v:
        return ""
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(400, f"Invalid time: {v}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def clean_report(data: dict | None, *, summary: str = "") -> dict:
    r = (data or {}).get("report") or {}
    parts = []
    for p in r.get("further_parts_required") or []:
        name = str((p or {}).get("name") or "").strip()[:200]
        if not name:
            continue
        try:
            qty = max(1, int(p.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        parts.append({"name": name, "qty": qty, "sku": str(p.get("sku") or "")[:60], "part_id": p.get("part_id") or None})
    start, end = _iso(r.get("start_time")), _iso(r.get("end_time"))
    if start and end and end < start:
        raise HTTPException(400, "End time must be after the start time")
    return {
        "work_completed": (r.get("work_completed") or summary or "").strip()[:5000],
        "further_work_required": (r.get("further_work_required") or "").strip()[:5000],
        "further_parts_required": parts,
        "start_time": start,
        "end_time": end,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone(_UK).strftime("%d %b %Y %H:%M")
    except ValueError:
        return iso


def duration(report: dict) -> str:
    try:
        mins = int((datetime.fromisoformat(report["end_time"]) - datetime.fromisoformat(report["start_time"])).total_seconds() // 60)
    except (KeyError, ValueError, TypeError):
        return ""
    return f"{mins // 60}h {mins % 60:02d}m"


def report_rows(report: dict) -> list[tuple[str, str]]:
    parts = report.get("further_parts_required") or []
    return [
        ("Start time", fmt_time(report.get("start_time"))),
        ("End time", fmt_time(report.get("end_time")) + (f"  ({duration(report)})" if duration(report) else "")),
        ("Description of Work Completed", report.get("work_completed") or "—"),
        ("Further Work Required", report.get("further_work_required") or "None"),
        ("Further Parts Required", "\n".join(f"{p['qty']} × {p['name']}" + (f" ({p['sku']})" if p.get("sku") else "") for p in parts) or "None"),
    ]


def report_flowables(report: dict, h_section, body):
    """Reportlab flowables for the platypus-based service report."""
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    rows = [[Paragraph(f"<b>{k}</b>", body), Paragraph(escape(v).replace("\n", "<br/>"), body)] for k, v in report_rows(report)]
    t = Table(rows, colWidths=[55 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0E0E0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph("ENGINEER REPORT", h_section), t, Spacer(1, 4 * mm)]


def draw_report_canvas(c, x: float, y: float, width: float, report: dict) -> float:
    """Draw the report rows on a raw reportlab canvas; returns the new y."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.lib import colors
    c.setFillColor(colors.HexColor("#1B1C1D"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "ENGINEER REPORT")
    y -= 6 * mm
    for label, val in report_rows(report):
        lines = [ln for chunk in val.split("\n") for ln in (simpleSplit(chunk, "Helvetica", 9, width - 55 * mm) or [""])]
        if y - len(lines) * 4.5 * mm < 20 * mm:
            c.showPage()
            y = 280 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, label)
        c.setFont("Helvetica", 9)
        for ln in lines:
            c.drawString(x + 55 * mm, y, ln)
            y -= 4.5 * mm
        y -= 1.5 * mm
    return y
