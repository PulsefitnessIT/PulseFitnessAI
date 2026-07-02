"""Generic report exporters (Excel + branded PDF) for CRM reports.

Renders any ``{rows: [...], totals: {...}}`` report to XLSX or a Pulse-
branded PDF. Columns are derived from the row keys.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

CORE_BLUE = "19CDFF"
SOFT_BLACK = "1B1C1D"
_HIDE_TOTALS = {"from", "to", "top", "bottom", "leaking"}


def _label(k: str) -> str:
    return k.replace("_", " ").title()


def _cell(v):
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    if v in (None, ""):
        return ""
    return v


def build_report_xlsx(title: str, rows: list[dict], totals: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    blue = PatternFill("solid", fgColor=CORE_BLUE)
    dark = PatternFill("solid", fgColor=SOFT_BLACK)

    ws["A1"] = title
    ws["A1"].font = Font(size=14, bold=True)
    ws["A2"] = f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}"
    ws["A2"].font = Font(size=9, italic=True, color="6E7476")

    r = 4
    tvis = {k: v for k, v in (totals or {}).items() if k not in _HIDE_TOTALS}
    if tvis:
        ws.cell(r, 1, "Summary").font = Font(bold=True)
        r += 1
        for k, v in tvis.items():
            ws.cell(r, 1, _label(k)).font = Font(color="6E7476")
            ws.cell(r, 2, _cell(v))
            r += 1
        r += 1

    if rows:
        headers = list(rows[0].keys())
        for ci, h in enumerate(headers, 1):
            c = ws.cell(r, ci, _label(h))
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = dark
            c.alignment = Alignment(horizontal="left")
        r += 1
        for row in rows:
            for ci, h in enumerate(headers, 1):
                ws.cell(r, ci, _cell(row.get(h)))
            r += 1
        for ci, h in enumerate(headers, 1):
            width = max(len(_label(h)), *(len(str(_cell(rw.get(h)))) for rw in rows)) + 2
            ws.column_dimensions[ws.cell(1, ci).column_letter].width = min(width, 40)
    else:
        ws.cell(r, 1, "No data in this report yet.")

    _ = blue  # reserved accent
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_report_pdf(title: str, rows: list[dict], totals: dict) -> bytes:
    ss = getSampleStyleSheet()
    core = colors.HexColor(f"#{CORE_BLUE}")
    black = colors.HexColor(f"#{SOFT_BLACK}")
    slate = colors.HexColor("#6E7476")
    silver = colors.HexColor("#E0E0E0")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title=title)
    story = []
    story.append(Paragraph("Pulse Fitness", ParagraphStyle("b", textColor=core, fontSize=11)))
    story.append(Paragraph(title, ParagraphStyle("h", parent=ss["Title"], textColor=black, fontSize=18, spaceAfter=2)))
    story.append(Paragraph(f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
                           ParagraphStyle("s", textColor=slate, fontSize=9, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=2, color=black, spaceAfter=8))

    tvis = {k: v for k, v in (totals or {}).items() if k not in _HIDE_TOTALS}
    if tvis:
        tdata = [[Paragraph(_label(k), ParagraphStyle("l", textColor=slate, fontSize=8)),
                  Paragraph(str(_cell(v)), ParagraphStyle("v", textColor=black, fontSize=10))]
                 for k, v in tvis.items()]
        tt = Table(tdata, colWidths=[70 * mm, 60 * mm])
        tt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, silver),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(tt)
        story.append(Spacer(1, 8))

    if rows:
        headers = list(rows[0].keys())
        cell_style = ParagraphStyle("c", fontSize=8, textColor=black)
        head_style = ParagraphStyle("hd", fontSize=8, textColor=colors.white, fontName="Helvetica-Bold")
        data = [[Paragraph(_label(h), head_style) for h in headers]]
        for row in rows:
            data.append([Paragraph(str(_cell(row.get(h))), cell_style) for h in headers])
        avail = 269 * mm
        col_w = avail / len(headers)
        t = Table(data, colWidths=[col_w] * len(headers), repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), black),
            ("GRID", (0, 0), (-1, -1), 0.25, silver),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F7")]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No data in this report yet.", ParagraphStyle("nd", textColor=slate, fontSize=10)))

    doc.build(story)
    return buf.getvalue()
