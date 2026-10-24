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
        "title": ps("title", fontSize=26, leading=32, textColor=PULSE_NAVY,
                    fontName="Helvetica-Bold", alignment=TA_LEFT, spaceAfter=2),
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


_WIDE_LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pulse-logo-wide.jpg")


def _wide_logo_flowable(width_mm: float = 55):
    if not os.path.exists(_WIDE_LOGO_PATH):
        return None
    try:
        from PIL import Image as _PIL
        w, h = _PIL.open(_WIDE_LOGO_PATH).size
        return Image(_WIDE_LOGO_PATH, width=width_mm * mm, height=width_mm * mm * h / w)
    except Exception:
        return None


def _logo_flowable(size_mm: float = 16, logo_bytes: bytes | None = None):
    if logo_bytes:
        try:
            from io import BytesIO
            return Image(BytesIO(logo_bytes), width=size_mm * mm, height=size_mm * mm)
        except Exception:
            return None
    if os.path.exists(_LOGO_PATH):
        try:
            return Image(_LOGO_PATH, width=size_mm * mm, height=size_mm * mm)
        except Exception:
            return None
    return None


def pulse_header(s: dict, company: dict | None = None) -> Table:
    """Branded header: logo + wordmark top-left, company contact block top-right.

    ``company`` overrides the default Pulse identity (used by tenant-branded
    documents). It may carry ``logo_bytes`` (raw image), ``use_default_logo``
    (fall back to the Pulse logo file), ``name``/``tagline``/``phone``/
    ``email``/``web``/``hashtag`` — empty fields are simply skipped.
    """
    c = company or PULSE
    if company is None or company is PULSE:
        hdr = invoice_header_flowable()
        if hdr is not None:
            return hdr
    logo_bytes = c.get("logo_bytes")
    pulse_logo = False
    if logo_bytes:
        logo = _logo_flowable(logo_bytes=logo_bytes)
    elif c.get("use_default_logo", company is None):
        logo = _wide_logo_flowable() or _logo_flowable(size_mm=22)
        pulse_logo = logo is not None
    else:
        logo = None
    name = c.get("name") or PULSE["name"]
    if pulse_logo:  # Pulse logo already carries the wordmark
        left_inner, widths = [[logo]], [78 * mm]
    elif logo:
        left_inner, widths = [[logo, Paragraph(_esc(name), s["wordmark"])]], [18 * mm, 60 * mm]
    else:
        left_inner, widths = [[Paragraph(_esc(name), s["wordmark"])]], [78 * mm]
    left = Table(left_inner, colWidths=widths)
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    contact_lines = []
    if c.get("tagline"):
        contact_lines.append(f"<b>{_esc(c['tagline'])}</b>")
    for key in ("phone", "email", "web"):
        if c.get(key):
            contact_lines.append(_esc(c[key]))
    if c.get("hashtag"):
        contact_lines.append(f"<font color='#1763B5'>{_esc(c['hashtag'])}</font>")
    right = Paragraph("<br/>".join(contact_lines), s["co"])
    header = Table([[left, right]], colWidths=[95 * mm, 75 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, PULSE_NAVY),
    ]))
    return header


_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_INV_HEADER = os.path.join(_ASSETS, "pulse-invoice-header.png")
_INV_FOOTER = os.path.join(_ASSETS, "pulse-invoice-footer.png")
# Placement copied from the Pulse invoice template (A4, points).
_INV_X, _INV_W = 36.0, 523.0
_INV_FOOTER_X, _INV_FOOTER_W = 39.0, 520.0
INVOICE_FOOTER_H = _INV_FOOTER_W * 570 / 3307  # ≈ 90pt
INVOICE_BOTTOM_MARGIN = INVOICE_FOOTER_H + 22  # body clearance above the footer art


def invoice_header_flowable(width: float | None = None):
    """The exact header artwork used on Pulse invoices (logo + contact block)."""
    if not os.path.exists(_INV_HEADER):
        return None
    from reportlab.platypus import Flowable

    class _InvoiceHeader(Flowable):
        """Drawn at the invoice's absolute x so it lines up exactly, whatever the margins."""
        def wrap(self, aw, ah):
            self._w = width or _INV_W
            self._h = self._w * 326 / 2729
            return aw, self._h + 4

        def draw(self):
            frame_x = self.canv.absolutePosition(0, 0)[0]
            self.canv.drawImage(_INV_HEADER, _INV_X - frame_x, 4, width=self._w, height=self._h, mask="auto")

    return _InvoiceHeader()


def invoice_art_available() -> bool:
    return os.path.exists(_INV_HEADER) and os.path.exists(_INV_FOOTER)


def draw_invoice_header(canvas, page_h: float) -> float:
    """Draw the invoice header artwork on a raw canvas; returns its bottom y."""
    if not os.path.exists(_INV_HEADER):
        return page_h - 20
    hh = _INV_W * 326 / 2729
    top = page_h - 20
    canvas.drawImage(_INV_HEADER, _INV_X, top - hh, width=_INV_W, height=hh, mask="auto")
    return top - hh


def draw_invoice_footer(canvas, doc, *, left_lines: list[str] | None = None,
                        note: str | None = None, is_mod: bool = False) -> bool:
    """Draw the invoice footer artwork (pulseglobal / registered office / dark bar)
    plus the page number where the invoice prints it. Returns False if missing."""
    if not os.path.exists(_INV_FOOTER):
        return False
    canvas.saveState()
    canvas.drawImage(_INV_FOOTER, _INV_FOOTER_X, 0, width=_INV_FOOTER_W,
                     height=INVOICE_FOOTER_H, mask="auto")
    canvas.setFillColor(PULSE_TEXT)
    canvas.setFont("Helvetica", 8)
    y = INVOICE_FOOTER_H - 22
    for line in [str(doc.page)] + list(left_lines or []):
        canvas.drawString(_INV_FOOTER_X + 12, y, line)
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(PULSE_MUTED)
        y -= 8
    if is_mod:
        canvas.setFont("Helvetica", 6)
        canvas.drawRightString(_INV_FOOTER_X + _INV_FOOTER_W, INVOICE_FOOTER_H + 4, "© Crown Copyright")
    if note:
        canvas.setFont("Helvetica", 5.6)
        canvas.setFillColor(PULSE_MUTED)
        canvas.drawString(_INV_FOOTER_X + 12, INVOICE_FOOTER_H + 4, note[:200])
    canvas.restoreState()
    return True


def section_label(s: dict, text: str) -> Paragraph:
    return Paragraph(_esc(text), s["sectlabel"])


def make_pulse_doc(buf, title: str, *, is_mod: bool = False,
                   left_mm: float = 18, right_mm: float = 18,
                   top_mm: float = 16, bottom_mm: float = 28,
                   company: dict | None = None):
    """Return a BaseDocTemplate wired with a single full-width frame and the
    standard Pulse footer (registered office / Co Reg / VAT / page number) on
    every page. Callers prepend ``pulse_header(pulse_styles())`` to the story.
    Pass ``company`` to brand the footer for a specific tenant."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

    is_pulse = company is None or company is PULSE
    bottom = max(bottom_mm * mm, INVOICE_BOTTOM_MARGIN) if is_pulse and os.path.exists(_INV_FOOTER) else bottom_mm * mm
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=left_mm * mm, rightMargin=right_mm * mm,
        topMargin=top_mm * mm, bottomMargin=bottom,
        title=title, author=(company or PULSE).get("name") or "Pulse Fitness",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="pulse-body", showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame],
                                       onPage=pulse_footer_factory(is_mod, company=company))])
    return doc


def pulse_title(s: dict, title: str, subtitle: str | None = None) -> list:
    """Standard document title (navy) + optional muted subtitle line."""
    from reportlab.platypus import Spacer
    from reportlab.lib.units import mm
    flow = [Paragraph(_esc(title), s["title"])]
    if subtitle:
        # Small gap so the subtitle never rides up into the title's descenders.
        flow.append(Spacer(1, 2 * mm))
        flow.append(Paragraph(subtitle, s["muted"]))
    return flow


def pulse_footer_factory(is_mod: bool = False, primary_line: str | None = None,
                         company: dict | None = None):
    """on_page callback drawing the standard registered-office / compliance
    footer at the bottom of every page. ``company`` overrides the default
    Pulse identity for tenant-branded documents; empty fields are skipped."""
    c = company or PULSE
    is_tenant = company is not None and company is not PULSE

    def _footer(canvas, doc):
        if not is_tenant and not primary_line and draw_invoice_footer(
                canvas, doc, is_mod=is_mod, note=c.get("footer_note") or (
                    "Refurbished electrical equipment tested per Electrical Equipment (Safety) "
                    "Regulations 2016 (GB); ongoing testing/compliance is the end user's responsibility.")):
            return
        canvas.saveState()
        width = doc.pagesize[0]
        x0 = doc.leftMargin
        x1 = width - doc.rightMargin
        y = 15 * mm
        canvas.setStrokeColor(PULSE_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(x0, y + 9 * mm, x1, y + 9 * mm)
        brand_line = c.get("footer_brand_line") or ("" if is_tenant else "A pulseglobal Company")
        if brand_line:
            canvas.setFont("Helvetica-Bold", 6.5)
            canvas.setFillColor(PULSE_NAVY)
            canvas.drawString(x0, y + 5.5 * mm, brand_line)
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(PULSE_MUTED)
        reg = c.get("registered_office")
        reg_bits = []
        if reg:
            reg_bits.append(f"Registered Office: {reg}")
        if c.get("company_reg"):
            reg_bits.append(f"Company Registration No {c['company_reg']}.")
        if c.get("vat_reg"):
            reg_bits.append(f"VAT Registration No {c['vat_reg']}.")
        if reg_bits:
            canvas.drawString(x0, y + 3 * mm, "  ".join(reg_bits))
        note = c.get("footer_note")
        if note:
            canvas.drawString(x0, y + 0.5 * mm, note[:180])
        elif not is_tenant:
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
    "section_label", "pulse_footer_factory", "make_pulse_doc", "pulse_title",
    "invoice_header_flowable", "draw_invoice_footer", "INVOICE_BOTTOM_MARGIN",
]
