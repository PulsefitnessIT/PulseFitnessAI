"""Iter 216h130 — Branded engineer invoice PDF (light-mode GymAxis)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

GX_PRIMARY = colors.HexColor("#1d4ed8")
GX_ACCENT = colors.HexColor("#6366f1")
GX_NAVY = colors.HexColor("#0F172A")
GX_MUTED = colors.HexColor("#64748B")
GX_LIGHT = colors.HexColor("#F1F5F9")
GX_BORDER = colors.HexColor("#E2E8F0")
GX_AMBER = colors.HexColor("#D97706")


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Title"], fontSize=22, leading=28,
                              textColor=colors.white, alignment=TA_LEFT, spaceAfter=2),
        "kicker": ParagraphStyle("kicker", parent=base["Normal"], fontSize=8.5, leading=10,
                                   textColor=colors.white, alignment=TA_LEFT, spaceAfter=4),
        "label": ParagraphStyle("label", parent=base["Normal"], fontSize=8, leading=10,
                                  textColor=GX_MUTED, spaceAfter=2, alignment=TA_LEFT),
        "value": ParagraphStyle("value", parent=base["Normal"], fontSize=10, leading=13,
                                  textColor=GX_NAVY, spaceAfter=2, alignment=TA_LEFT),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14,
                                 textColor=GX_NAVY, alignment=TA_LEFT, spaceAfter=4),
        "muted": ParagraphStyle("muted", parent=base["Normal"], fontSize=9, leading=12,
                                  textColor=GX_MUTED, spaceAfter=3),
        "total_label": ParagraphStyle("total_label", parent=base["Normal"], fontSize=10,
                                        leading=14, textColor=GX_MUTED, alignment=TA_RIGHT),
        "total_value": ParagraphStyle("total_value", parent=base["Normal"], fontSize=12,
                                        leading=16, textColor=GX_NAVY,
                                        alignment=TA_RIGHT, fontName="Helvetica-Bold"),
        "grand_value": ParagraphStyle("grand_value", parent=base["Normal"], fontSize=16,
                                        leading=20, textColor=GX_PRIMARY,
                                        alignment=TA_RIGHT, fontName="Helvetica-Bold"),
    }


def _footer_factory(is_mod: bool):
    """Iter 216h166 — close over `is_mod` so MOD tenants get the
    Crown copyright bar without changing the call site of `_footer`."""
    from utils.pdf_footer import draw_pdf_footer

    def _footer(canvas, doc):
        draw_pdf_footer(
            canvas, doc,
            primary_line="GymAxis · Field Service for Fitness Equipment",
            is_mod=is_mod,
            muted_colour=GX_MUTED, line_colour=GX_BORDER,
        )
    return _footer


def _header_block(s, inv: dict) -> Table:
    ino = inv.get("invoice_number") or "INVOICE"
    issue_date = inv.get("issue_date") or datetime.utcnow().date().isoformat()
    due_date = inv.get("due_date") or "—"
    header = Table(
        [[Paragraph("INVOICE · GymAxis", s["kicker"])],
         [Paragraph(_esc(ino), s["h1"])],
         [Paragraph(f"Issued {_esc(issue_date)} · Due {_esc(due_date)}", s["kicker"])]],
        colWidths=[170 * mm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GX_PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return header


def _two_col(s, left_label, left_lines, right_label, right_lines):
    def stack(label, lines):
        rows = [[Paragraph(label, s["label"])]]
        for ln in lines:
            rows.append([Paragraph(_esc(ln or ""), s["value"])])
        t = Table(rows, colWidths=[80 * mm])
        t.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t
    return Table([[stack(left_label, left_lines), stack(right_label, right_lines)]],
                 colWidths=[85 * mm, 85 * mm])


def _lines_table(s, inv):
    data = [["Description", "Qty", "Unit £", "Total £"]]
    lines = inv.get("lines") or []
    if not lines:
        data.append(["No line items.", "", "", ""])
    for ln in lines:
        kind = (ln.get("kind") or "").title()
        prefix = f"<font color='#64748B' size='8'>{_esc(kind)} · </font>" if kind else ""
        desc_html = prefix + _esc(ln.get("description") or "—")
        if ln.get("notes"):
            desc_html += f"<br/><font color='#64748B' size='8'>{_esc(ln['notes'])}</font>"
        data.append([
            Paragraph(desc_html, s["body"]),
            Paragraph(f"{float(ln.get('quantity', 0)):g}", s["body"]),
            Paragraph(f"{float(ln.get('unit_price', 0)):,.2f}", s["body"]),
            Paragraph(f"{float(ln.get('line_total', 0)):,.2f}", s["body"]),
        ])
    t = Table(data, colWidths=[100 * mm, 18 * mm, 22 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GX_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GX_LIGHT]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, GX_PRIMARY),
        ("GRID", (0, 1), (-1, -1), 0.25, GX_BORDER),
    ]))
    return t


def _totals_block(s, inv):
    rows = [[Paragraph("Subtotal", s["total_label"]),
             Paragraph(f"£{float(inv.get('subtotal', 0)):,.2f}", s["total_value"])]]
    if inv.get("discount_amount"):
        rows.append([Paragraph(f"Discount ({inv.get('discount_pct', 0):g}%)", s["total_label"]),
                     Paragraph(f"-£{float(inv['discount_amount']):,.2f}", s["total_value"])])
    # Iter 220l — if the engineer is VAT-exempt (below £85k threshold),
    # show a clarifying row instead of "VAT (0%): £0.00".
    if inv.get("vat_exempt"):
        rows.append([Paragraph("VAT", s["total_label"]),
                     Paragraph("Not chargeable", s["total_value"])])
    else:
        rows.append([Paragraph(f"VAT ({inv.get('vat_rate', 0):g}%)", s["total_label"]),
                     Paragraph(f"£{float(inv.get('vat_amount', 0)):,.2f}", s["total_value"])])
    rows.append([Paragraph("<b>TOTAL DUE</b>", s["total_label"]),
                 Paragraph(f"£{float(inv.get('total', 0)):,.2f}", s["grand_value"])])
    t = Table(rows, colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, -2), (-1, -2), 0.5, GX_BORDER),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, GX_PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _payment_block(s, inv):
    """Highlighted box with bank/BACS instructions."""
    body = []
    if inv.get("payment_method"):
        body.append(f"<b>Method:</b> {_esc(inv['payment_method'])}")
    bank_lines = []
    if inv.get("bank_name"):
        bank_lines.append(f"Bank: {inv['bank_name']}")
    if inv.get("bank_account_name"):
        bank_lines.append(f"Account name: {inv['bank_account_name']}")
    if inv.get("bank_sort_code"):
        bank_lines.append(f"Sort code: {inv['bank_sort_code']}")
    if inv.get("bank_account_number"):
        bank_lines.append(f"Account number: {inv['bank_account_number']}")
    if bank_lines:
        body.append("<br/>".join(_esc(b) for b in bank_lines))
    if inv.get("payment_instructions"):
        body.append(_esc(inv["payment_instructions"]))
    if not body:
        return None
    para = Paragraph("<br/><br/>".join(body), s["body"])
    box = Table([[para]], colWidths=[170 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GX_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (0, 0), (0, -1), 3, GX_PRIMARY),
    ]))
    return box


def build_engineer_invoice_pdf(inv: dict, *, is_mod: bool = False) -> bytes:
    s = _styles()
    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=f"Invoice {inv.get('invoice_number') or ''}",
        author="GymAxis",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="normal", showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame], onPage=_footer_factory(is_mod))])
    flow = [_header_block(s, inv), Spacer(1, 8 * mm)]
    customer_lines = [inv.get("customer_name"), inv.get("site_name"),
                      inv.get("site_address"), inv.get("customer_email"),
                      inv.get("customer_phone")]
    engineer_lines = [inv.get("engineer_name"), inv.get("engineer_email"),
                      inv.get("engineer_mobile"),
                      f"Case ref: {inv.get('case_reference') or '—'}"]
    if inv.get("linked_quote_number"):
        engineer_lines.append(f"Linked quote: {inv['linked_quote_number']}")
    flow.append(_two_col(s, "BILL TO", customer_lines, "FROM", engineer_lines))
    flow.append(Spacer(1, 6 * mm))

    if inv.get("asset_name") or inv.get("asset_serial"):
        flow.append(Paragraph("ASSET", s["label"]))
        flow.append(Paragraph(
            f"{_esc(inv.get('asset_name') or '—')} · Serial {_esc(inv.get('asset_serial') or '—')}",
            s["value"]))
        flow.append(Spacer(1, 4 * mm))

    if inv.get("description_of_work"):
        flow.append(Paragraph("DESCRIPTION OF WORK", s["label"]))
        flow.append(Paragraph(_esc(inv["description_of_work"]).replace("\n", "<br/>"),
                              s["body"]))
        flow.append(Spacer(1, 4 * mm))

    flow.append(Paragraph("LINE ITEMS", s["label"]))
    flow.append(_lines_table(s, inv))
    flow.append(Spacer(1, 6 * mm))
    flow.append(_totals_block(s, inv))
    flow.append(Spacer(1, 8 * mm))

    pay = _payment_block(s, inv)
    if pay:
        flow.append(Paragraph("PAYMENT INSTRUCTIONS", s["label"]))
        flow.append(pay)
        flow.append(Spacer(1, 6 * mm))

    if inv.get("notes"):
        flow.append(Paragraph("NOTES", s["label"]))
        flow.append(Paragraph(_esc(inv["notes"]).replace("\n", "<br/>"), s["body"]))
        flow.append(Spacer(1, 4 * mm))

    if inv.get("terms"):
        flow.append(Paragraph("TERMS &amp; CONDITIONS", s["label"]))
        flow.append(Paragraph(_esc(inv["terms"]).replace("\n", "<br/>"), s["muted"]))

    doc.build(flow)
    return buf.getvalue()


__all__ = ["build_engineer_invoice_pdf"]
