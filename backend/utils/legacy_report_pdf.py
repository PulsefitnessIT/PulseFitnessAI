"""Iter 220ea·33 — Beautiful branded PDF for imported legacy reports.

A clean, modern service report: a brand colour band with the engineer's
logo, a customer/visit summary, then one elegant card per machine with a
status chip and a striped custom-field table. Collates multiple visits
(bulk-imported files, each with its own date + job number) into one doc.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone


def _hex(c: str | None, default: str) -> str:
    c = (c or "").strip()
    if c.startswith("#") and len(c) in (4, 7):
        return c
    return default


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(iso[:19] if "T" in iso else iso[:10], fmt).strftime("%-d %B %Y")
        except Exception:
            continue
    return iso[:10]


def build_legacy_pdf(report: dict, branding: dict, logo_bytes: bytes | None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
        TableStyle, Image, KeepTogether,
    )

    primary = colors.HexColor(_hex(branding.get("primary_color"), "#0055FF"))
    ink = colors.HexColor("#0F172A")
    muted = colors.HexColor("#64748B")
    line = colors.HexColor("#E2E8F0")
    soft = colors.HexColor("#F1F5F9")

    company = (branding.get("company_name") or "").strip()
    cust = report.get("customer") or {}
    visits = report.get("visits") or []

    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5,
                          textColor=ink, leading=14)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontName="Helvetica", fontSize=8,
                           textColor=muted, leading=11)
    label = ParagraphStyle("lb", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5,
                           textColor=muted, leading=10)
    val = ParagraphStyle("vl", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5,
                         textColor=ink, leading=13)
    sect = ParagraphStyle("se", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12,
                          textColor=primary, leading=15)
    mname = ParagraphStyle("mn", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11,
                           textColor=ink, leading=14)
    cf_lbl = ParagraphStyle("cl", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5,
                            textColor=muted, leading=12)
    cf_val = ParagraphStyle("cv", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5,
                            textColor=ink, leading=12)

    PW, PH = A4
    MARGIN = 16 * mm
    BAND_H = 34 * mm

    def header_footer(canvas, doc):
        canvas.saveState()
        # Brand band
        canvas.setFillColor(primary)
        canvas.rect(0, PH - BAND_H, PW, BAND_H, fill=1, stroke=0)
        canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.08))
        canvas.circle(PW - 20 * mm, PH - 6 * mm, 30 * mm, fill=1, stroke=0)
        # Logo (white chip) or company name
        x = MARGIN
        if logo_bytes:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(io.BytesIO(logo_bytes))
                iw, ih = img.getSize()
                disp_h = 14 * mm
                disp_w = min(48 * mm, disp_h * iw / ih)
                canvas.setFillColor(colors.white)
                canvas.roundRect(x - 2 * mm, PH - BAND_H + (BAND_H - disp_h) / 2 - 2 * mm,
                                 disp_w + 4 * mm, disp_h + 4 * mm, 2 * mm, fill=1, stroke=0)
                canvas.drawImage(img, x, PH - BAND_H + (BAND_H - disp_h) / 2,
                                 width=disp_w, height=disp_h, mask="auto", preserveAspectRatio=True)
            except Exception:
                canvas.setFillColor(colors.white)
                canvas.setFont("Helvetica-Bold", 15)
                canvas.drawString(x, PH - 16 * mm, company or "Service Report")
        elif company:
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 16)
            canvas.drawString(x, PH - 16 * mm, company)
        # Title right
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 19)
        canvas.drawRightString(PW - MARGIN, PH - 14 * mm, "SERVICE REPORT")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(PW - MARGIN, PH - 20 * mm, cust.get("name") or "")
        # Footer
        canvas.setStrokeColor(line)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 14 * mm, PW - MARGIN, 14 * mm)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7.5)
        foot = company or "GymAxis"
        canvas.drawString(MARGIN, 9 * mm, f"{foot} · Service report")
        canvas.drawRightString(PW - MARGIN, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    frame = Frame(MARGIN, 16 * mm, PW - 2 * MARGIN, PH - BAND_H - 28 * mm, id="main")
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=header_footer)])

    story: list = [Spacer(1, 4 * mm)]

    # Customer / site card
    addr = cust.get("address") or ""
    info_rows = [
        [Paragraph("CUSTOMER", label), Paragraph("SITE", label), Paragraph("CONTACT", label)],
        [Paragraph(cust.get("name") or "—", val),
         Paragraph(cust.get("site_name") or addr or "—", body),
         Paragraph("<br/>".join(filter(None, [cust.get("contact_name"), cust.get("email"), cust.get("phone")])) or "—", body)],
    ]
    info = Table(info_rows, colWidths=[(PW - 2 * MARGIN) / 3] * 3)
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), soft),
        ("BOX", (0, 0), (-1, -1), 0.5, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [info, Spacer(1, 6 * mm)]

    cw = PW - 2 * MARGIN

    for vi, visit in enumerate(visits):
        meta = []
        if visit.get("service_date"):
            meta.append(f"Visit date: {_fmt_date(visit['service_date'])}")
        if visit.get("job_number"):
            meta.append(f"Job #: {visit['job_number']}")
        title = " · ".join(meta) or f"Visit {vi + 1}"
        block = [Paragraph(title, sect)]
        if visit.get("summary"):
            block.append(Paragraph(visit["summary"], small))
        block.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(block))

        for m in (visit.get("machines") or []):
            card = []
            status = (m.get("status") or "").strip()
            status_cell = Paragraph(
                f'<font color="white"><b>&nbsp;{status}&nbsp;</b></font>', small) if status else Paragraph("", small)
            head = Table([[Paragraph(m.get("name") or "Machine", mname), status_cell]],
                         colWidths=[cw * 0.7, cw * 0.3])
            head_style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                          ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                          ("ALIGN", (1, 0), (1, 0), "RIGHT")]
            if status:
                head_style.append(("BACKGROUND", (1, 0), (1, 0), primary))
            head.setStyle(TableStyle(head_style))
            card.append(head)

            # standard chips
            chips = []
            for lbl, key in (("Model", "model"), ("Serial", "serial"), ("Location", "location")):
                if m.get(key):
                    chips.append([Paragraph(lbl.upper(), label), Paragraph(str(m[key]), val)])
            if chips:
                chip_tbl = Table([[c[0] for c in chips], [c[1] for c in chips]],
                                 colWidths=[cw / max(1, len(chips))] * len(chips))
                chip_tbl.setStyle(TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                card += [Spacer(1, 1.5 * mm), chip_tbl]

            if m.get("work_done"):
                card += [Spacer(1, 1.5 * mm),
                         Paragraph("WORK DONE / NOTES", label),
                         Paragraph(str(m["work_done"]).replace("\n", "<br/>"), body)]

            cfs = m.get("custom_fields") or []
            if cfs:
                rows = [[Paragraph(cf.get("label", ""), cf_lbl), Paragraph(cf.get("value", "") or "—", cf_val)]
                        for cf in cfs]
                cf_tbl = Table(rows, colWidths=[cw * 0.42, cw * 0.58])
                style = [
                    ("BOX", (0, 0), (-1, -1), 0.5, line),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, line),
                    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (0, -1), soft),
                ]
                for r in range(0, len(rows), 2):
                    style.append(("BACKGROUND", (1, r), (1, r), colors.HexColor("#FBFCFE")))
                cf_tbl.setStyle(TableStyle(style))
                card += [Spacer(1, 2 * mm), cf_tbl]

            wrapper = Table([[card]], colWidths=[cw])
            wrapper.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.75, line),
                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]))
            story += [Spacer(1, 3 * mm), wrapper]
        story.append(Spacer(1, 5 * mm))

    gen = datetime.now(timezone.utc).strftime("%-d %B %Y")
    story.append(Paragraph(f"This report was compiled from the engineer's historic records on {gen}.", small))

    doc.build(story)
    return buf.getvalue()
