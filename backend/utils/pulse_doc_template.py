"""Shared Pulse Fitness document template — the single source of truth for the
branded header, footer and palette used across all generated PDFs (invoices,
quotes, fault/service reports, preventative-maintenance reports, …), modelled
on the standard Pulse Fitness invoice layout.

Usage:
    from utils.pulse_doc_template import (
        PULSE, pulse_styles, pulse_header, pulse_footer_factory, section_label,
    )
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Table, TableStyle

# ── Brand palette (dark Pulse blue, matching the standard invoice) ──────────
PULSE_NAVY = colors.HexColor("#0B3D91")     # headings / "Invoice" title / labels
PULSE_BLUE = colors.HexColor("#1763B5")     # wordmark accent / thin rules
PULSE_TEXT = colors.HexColor("#1A1A1A")
PULSE_MUTED = colors.HexColor("#5B6570")
PULSE_LIGHT = colors.HexColor("#EEF3FB")
PULSE_BORDER = colors.HexColor("#C9D4E5")

_LOGO_PATH = "/app/frontend/public/brand/pulse-logo-primary.jpg"

# ── Static company details (confirmed standard for all documents) ───────────
PULSE = {
    "name": "Pulse Fitness",
    "tagline": "Part of The Pulse Group",
    "phone": "+44 (0)1260 294600",
    "email": "info@pulsefitness.com",
    "web": "www.pulsefitness.com",
    "hashtag": "#pulsefitness",
    "payment_terms": "7 days from document date",
    "bank_name": "HSBC Bank Plc",
    "bank_account_name": "Pulse Fitness Ltd",
    "bank_account_number": "40023205",
    "bank_sort_code": "40-28-56",
    "vat_reg": "785413509",
    "company_reg": "4354059",
    "registered_office": "Pulse Fitness Limited, Radnor Park, Greenfield Road, "
                         "Congleton, Cheshire, CW12 4TW.",
    "footer_clauses": [
        "Title of Goods remains with Pulse Fitness until full payment is received.",
        "N.B. Extended Warranty Terms exclude all Accessories. One Year Manufacturers "
        "Warranty only. Products marked * indicate non-Pulse branded products subject to "
        "the relevant manufacturer's standard warranty terms and conditions.",
        "Refurbished electrical equipment has been tested in accordance with Electrical "
        "Equipment (Safety) Regulations 2016: Great Britain and is confirmed electrically "
        "safe at the point of despatch. Ongoing testing and compliance remain the "
        "responsibility of the end user.",
    ],
}


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pulse_styles() -> dict:
    base = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "esc": _esc,
        "wordmark": ps("wordmark", fontSize=17, leading=19, textColor=PULSE_NAVY,
                       fontName="Helvetica-Bold"),
        "tagline": ps("tagline", fontSize=8, leading=10, textColor=PULSE_BLUE,
                      fontName="Helvetica-Bold"),
        "co": ps("co", fontSize=8, leading=11, textColor=PULSE_MUTED, alignment=TA_RIGHT),
        "title": ps("title", fontSize=26, leading=28, textColor=PULSE_NAVY,
                    fontName="Helvetica-Bold", alignment=TA_LEFT),
        "metalabel": ps("metalabel", fontSize=8.5, leading=12, textColor=PULSE_MUTED,
                        fontName="Helvetica-Bold"),
        "metaval": ps("metaval", fontSize=8.5, leading=12, textColor=PULSE_TEXT,
                      alignment=TA_RIGHT),
        "sectlabel": ps("sectlabel", fontSize=10, leading=13, textColor=PULSE_NAVY,
                        fontName="Helvetica-Bold", spaceAfter=3),
        "label": ps("label", fontSize=8, leading=10, textColor=PULSE_MUTED, spaceAfter=2),
        "value": ps("value", fontSize=9.5, leading=13, textColor=PULSE_TEXT),
        "body": ps("body", fontSize=9.5, leading=13.5, textColor=PULSE_TEXT, spaceAfter=4),
        "muted": ps("muted", fontSize=8.5, leading=11.5, textColor=PULSE_MUTED, spaceAfter=3),
        "cell": ps("cell", fontSize=9, leading=12, textColor=PULSE_TEXT),
        "cellR": ps("cellR", fontSize=9, leading=12, textColor=PULSE_TEXT, alignment=TA_RIGHT),
        "th": ps("th", fontSize=9, leading=12, textColor=colors.white, fontName="Helvetica-Bold"),
        "thR": ps("thR", fontSize=9, leading=12, textColor=colors.white,
                  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "total_label": ps("total_label", fontSize=9.5, leading=13, textColor=PULSE_MUTED,
                          fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "total_value": ps("total_value", fontSize=9.5, leading=13, textColor=PULSE_TEXT,
                          fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "grand_value": ps("grand_value", fontSize=12, leading=15, textColor=PULSE_NAVY,
                          fontName="Helvetica-Bold", alignment=TA_RIGHT),
    }


def _logo_flowable(size_mm: float = 16):
    if os.path.exists(_LOGO_PATH):
        try:
            return Image(_LOGO_PATH, width=size_mm * mm, height=size_mm * mm)
        except Exception:
            return None
    return None


def pulse_header(s: dict) -> Table:
    """Branded header: logo + wordmark top-left, company contact block top-right."""
    logo = _logo_flowable()
    left_inner = [[logo, Paragraph(PULSE["name"], s["wordmark"])]] if logo else [[Paragraph(PULSE["name"], s["wordmark"])]]
    left = Table(left_inner, colWidths=([18 * mm, 60 * mm] if logo else [78 * mm]))
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    right = Paragraph(
        f"<b>{PULSE['tagline']}</b><br/>{PULSE['phone']}<br/>"
        f"{PULSE['email']}<br/>{PULSE['web']}<br/>"
        f"<font color='#1763B5'>{PULSE['hashtag']}</font>",
        s["co"])
    header = Table([[left, right]], colWidths=[95 * mm, 75 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, PULSE_NAVY),
    ]))
    return header


def section_label(s: dict, text: str) -> Paragraph:
    return Paragraph(_esc(text), s["sectlabel"])


def pulse_footer_factory(is_mod: bool = False, primary_line: str | None = None):
    """on_page callback drawing the standard Pulse registered-office / compliance
    footer at the bottom of every page."""
    def _footer(canvas, doc):
        canvas.saveState()
        width = doc.pagesize[0]
        x0 = doc.leftMargin
        x1 = width - doc.rightMargin
        y = 15 * mm
        canvas.setStrokeColor(PULSE_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(x0, y + 9 * mm, x1, y + 9 * mm)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.setFillColor(PULSE_NAVY)
        canvas.drawString(x0, y + 5.5 * mm, "A pulseglobal Company")
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(PULSE_MUTED)
        canvas.drawString(
            x0, y + 3 * mm,
            f"Registered Office: {PULSE['registered_office']}  Company Registration No "
            f"{PULSE['company_reg']}. VAT Registration No {PULSE['vat_reg']}.")
        canvas.drawString(
            x0, y + 0.5 * mm,
            "Refurbished electrical equipment tested per Electrical Equipment (Safety) "
            "Regulations 2016 (GB); ongoing testing/compliance is the end user's responsibility.")
        if is_mod:
            canvas.drawRightString(x1, y + 5.5 * mm, "© Crown Copyright")
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(PULSE_MUTED)
        canvas.drawCentredString((x0 + x1) / 2, y - 2 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return _footer


__all__ = [
    "PULSE", "PULSE_NAVY", "PULSE_BLUE", "PULSE_TEXT", "PULSE_MUTED",
    "PULSE_LIGHT", "PULSE_BORDER", "pulse_styles", "pulse_header",
    "section_label", "pulse_footer_factory",
]
