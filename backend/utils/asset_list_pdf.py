"""Branded asset list PDF for the Service Desk (equipment + last service visit)."""
import io
import os
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from utils.engineer_report import fmt_time

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
INK, SILVER, LIGHT, SLATE, BLUE = "#1B1C1D", "#E0E0E0", "#F0F0F0", "#6E7476", "#0091CA"


def _d(iso: str | None) -> str:
    return " ".join(fmt_time(str(iso)).split(" ")[:3]) if iso else "—"


def build_asset_list_pdf(*, customer: str, site_label: str, groups: list[tuple[str, list[dict]]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page = landscape(A4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
                            title=f"Asset list — {customer}")
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor(INK))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(INK), spaceBefore=6)
    cell = ParagraphStyle("c", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=colors.HexColor(INK))
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    meta = ParagraphStyle("m", parent=cell, fontSize=8.5, leading=11, textColor=colors.HexColor(SLATE))

    story = []
    logo = os.path.join(_ASSETS, "pulse-header-logo.png")
    addr = os.path.join(_ASSETS, "pulse-header-address.png")
    hdr = [[Image(logo, width=54 * mm, height=10 * mm) if os.path.exists(logo) else "",
            Image(addr, width=60 * mm, height=11.8 * mm) if os.path.exists(addr) else ""]]
    ht = Table(hdr, colWidths=[(page[0] - 24 * mm) / 2] * 2)
    ht.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor(BLUE)), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [ht, Spacer(1, 5 * mm), Paragraph("Asset List", h1)]
    total = sum(len(rows) for _, rows in groups)
    story.append(Paragraph(f"{escape(customer)} · {escape(site_label)} · {total} machine(s) · Issued {datetime.now(timezone.utc).strftime('%d %b %Y')}", meta))
    story.append(Spacer(1, 4 * mm))

    cols = ["Machine", "Make / model", "Serial", "Type", "Status", "Installed", "Last service", "Job / engineer", "Work completed"]
    widths = [38, 38, 26, 22, 18, 20, 22, 32, 57]
    for site_name, rows in groups:
        story.append(Paragraph(f"{escape(site_name)} ({len(rows)})", h2))
        data = [[Paragraph(c, head) for c in cols]]
        for e in rows:
            last = e.get("_last_service") or {}
            work = (last.get("work") or "")[:400]
            data.append([Paragraph(escape(str(v or "—")), cell) for v in (
                e.get("name") or "Unnamed",
                " ".join(x for x in (e.get("manufacturer"), e.get("model")) if x),
                e.get("serial_number"), e.get("equipment_type") or e.get("category"),
                (e.get("status") or "").replace("_", " ").title(),
                _d(e.get("installation_date") or e.get("install_date")),
                _d(last.get("date") or e.get("last_service_date")),
                " · ".join(x for x in (last.get("reference"), last.get("engineer")) if x),
                work,
            )])
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(SILVER)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [t, Spacer(1, 4 * mm)]
    if not groups:
        story.append(Paragraph("No equipment found.", meta))

    def _footer(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.HexColor(SLATE))
        canv.drawString(12 * mm, 8 * mm, "Pulse Fitness Ltd · Radnor Park, Greenfield Road, Congleton, Cheshire CW12 4TW · www.pulsefitness.com")
        canv.drawRightString(page[0] - 12 * mm, 8 * mm, f"Page {canv.getPageNumber()}")
        canv.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
