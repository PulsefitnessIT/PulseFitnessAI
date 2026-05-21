"""Branded CRM Quote → PDF builder (Iter 216h224).

Uses reportlab (already in requirements) to render a branded quote PDF
with header (org logo + address), customer block, line-item table
including subtotals, totals/tax/grand-total, payment terms + notes.

This is a CRM-CPQ-specific renderer — the engineer quote PDF
(`utils/engineer_quote_pdf.py`) has a different shape (visit-based,
labour bands) and isn't reusable here.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


def _hex_to_color(hex_str: str, fallback: str = "#0F172A"):
    """Forgiving #RRGGBB → reportlab Color. Falls back to slate-900."""
    h = (hex_str or "").lstrip("#")
    if len(h) != 6:
        h = fallback.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return colors.Color(r / 255, g / 255, b / 255)
    except Exception:
        return colors.HexColor(fallback)


def build_crm_quote_pdf(quote: dict, org: dict) -> bytes:
    """Render the quote into a PDF byte string."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    brand = _hex_to_color(org.get("primary_color") or "#1D4ED8")
    muted = colors.Color(0.45, 0.50, 0.58)
    border = colors.Color(0.88, 0.91, 0.95)

    base = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=base["Heading1"], fontSize=22, leading=26, textColor=brand, spaceAfter=2)
    H2 = ParagraphStyle("H2", parent=base["Heading2"], fontSize=11, leading=14, textColor=muted, spaceAfter=6, fontName="Helvetica-Bold")
    Body = ParagraphStyle("Body", parent=base["BodyText"], fontSize=9, leading=12)
    Right = ParagraphStyle("Right", parent=Body, alignment=TA_RIGHT)
    Bold = ParagraphStyle("Bold", parent=Body, fontName="Helvetica-Bold")
    BoldRight = ParagraphStyle("BoldRight", parent=Bold, alignment=TA_RIGHT)
    Small = ParagraphStyle("Small", parent=Body, fontSize=8, textColor=muted)

    story = []

    # ── Header (org name/address left, QUOTE meta right) ──────────
    org_name = org.get("name", "") or "GymAxis"
    org_addr = "<br/>".join(filter(None, [
        org.get("address_line1"), org.get("address_line2"),
        org.get("city"), org.get("postcode"), org.get("country"),
    ])) or "—"
    org_contact = "<br/>".join(filter(None, [
        org.get("phone"), org.get("primary_contact_email"), org.get("website"),
    ]))
    header_left = [
        Paragraph(org_name, H1),
        Paragraph(org_addr, Small),
    ]
    if org_contact:
        header_left.append(Spacer(0, 2 * mm))
        header_left.append(Paragraph(org_contact, Small))

    meta_rows = [
        ["Quote #", quote.get("quote_number", "—")],
        ["Date", datetime.now().strftime("%d %b %Y")],
    ]
    if quote.get("valid_until"):
        meta_rows.append(["Valid until", str(quote.get("valid_until"))])
    meta_rows.append(["Status", (quote.get("status") or "draft").replace("_", " ").title()])
    meta_table = Table(meta_rows, colWidths=[22 * mm, 38 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), muted),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    header_table = Table(
        [[header_left, meta_table]],
        colWidths=[110 * mm, 60 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, brand),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(0, 8 * mm))

    # ── Bill-to block ────────────────────────────────────────────
    story.append(Paragraph("QUOTE FOR", H2))
    bill_to_lines = []
    if quote.get("company_name"):
        bill_to_lines.append(Paragraph(f"<b>{quote['company_name']}</b>", Body))
    if quote.get("contact_name"):
        bill_to_lines.append(Paragraph(quote["contact_name"], Body))
    if not bill_to_lines:
        bill_to_lines.append(Paragraph("(No customer specified)", Small))
    for ln in bill_to_lines:
        story.append(ln)
    if quote.get("title"):
        story.append(Spacer(0, 3 * mm))
        story.append(Paragraph(f"<b>Subject:</b> {quote['title']}", Body))
    story.append(Spacer(0, 6 * mm))

    # ── Line items table ─────────────────────────────────────────
    head = [
        Paragraph("<b>Description</b>", Body),
        Paragraph("<b>Qty</b>", BoldRight),
        Paragraph("<b>Unit Price</b>", BoldRight),
        Paragraph("<b>Disc %</b>", BoldRight),
        Paragraph("<b>Subtotal</b>", BoldRight),
    ]
    currency_symbol = "£" if (quote.get("currency") or "GBP").upper() == "GBP" else (
        "$" if (quote.get("currency") or "GBP").upper() == "USD" else
        (quote.get("currency") or "GBP")
    )
    rows = [head]
    for item in quote.get("line_items", []):
        rows.append([
            Paragraph(item.get("description") or item.get("product_name", "—"), Body),
            Paragraph(f"{item.get('quantity', 0):g}", Right),
            Paragraph(f"{currency_symbol}{item.get('unit_price', 0):,.2f}", Right),
            Paragraph(f"{item.get('discount_percent', 0):g}%", Right),
            Paragraph(f"{currency_symbol}{item.get('subtotal', 0):,.2f}", Right),
        ])
    items_table = Table(rows, colWidths=[78 * mm, 18 * mm, 26 * mm, 22 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.98, 1.0)]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, border),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(0, 6 * mm))

    # ── Totals box (right-aligned) ───────────────────────────────
    totals_rows = [
        ["Subtotal", f"{currency_symbol}{quote.get('subtotal', 0):,.2f}"],
        [f"VAT ({quote.get('tax_rate', 20):g}%)", f"{currency_symbol}{quote.get('tax_amount', 0):,.2f}"],
        ["Total", f"{currency_symbol}{quote.get('total', 0):,.2f}"],
    ]
    totals_table = Table(totals_rows, colWidths=[40 * mm, 32 * mm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, 2), (-1, 2), 1, brand),
        ("TEXTCOLOR", (0, 2), (-1, 2), brand),
        ("TOPPADDING", (0, 2), (-1, 2), 6),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 4),
    ]))
    wrap_totals = Table([["", totals_table]], colWidths=[100 * mm, 72 * mm])
    wrap_totals.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(wrap_totals)

    # ── Notes / payment terms ────────────────────────────────────
    if quote.get("notes"):
        story.append(Spacer(0, 6 * mm))
        story.append(Paragraph("NOTES", H2))
        story.append(Paragraph(quote["notes"].replace("\n", "<br/>"), Body))

    # ── Footer ───────────────────────────────────────────────────
    story.append(Spacer(0, 10 * mm))
    story.append(Paragraph(
        f"<i>Prepared by {quote.get('created_by_name') or '—'} · "
        f"Generated {datetime.now().strftime('%d %b %Y')}</i>",
        Small,
    ))

    doc.build(story)
    return buf.getvalue()



async def render_quote_pdf(quote: dict, organization_id: str | None = None) -> bytes:
    """Async helper used by `crm_v2.quote_pdf` + `send_quote_email`.

    Resolves the organisation doc (for branding) then delegates to the
    synchronous `build_crm_quote_pdf`. Tolerant of a missing org row —
    falls back to a bare {} so an export still works on demo tenants.
    """
    org: dict = {}
    if organization_id:
        try:
            from utils.database import db as _db
            org_doc = await _db.organizations.find_one({"id": organization_id}, {"_id": 0})
            if org_doc:
                org = org_doc
        except Exception:
            org = {}
    return build_crm_quote_pdf(quote, org)
