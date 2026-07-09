"""Standard Pulse Fitness invoice PDF — laid out to match the company's
standard invoice template (see utils/pulse_doc_template for the shared shell)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from utils.pulse_doc_template import (
    PULSE, PULSE_NAVY, PULSE_LIGHT, PULSE_BORDER, PULSE_MUTED,
    pulse_styles, pulse_header, section_label, pulse_footer_factory,
)


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _title_and_meta(s, inv):
    account_ref = inv.get("account_ref") or inv.get("customer_account_ref") or "—"
    meta_rows = [
        ("Invoice", inv.get("invoice_number") or "—"),
        ("Customer Ref", inv.get("customer_po_number") or "—"),
        ("Account Ref", account_ref),
        ("Invoice Date", inv.get("issue_date") or datetime.utcnow().date().isoformat()),
        ("Sales Order Ref", inv.get("sales_order_ref") or inv.get("case_reference") or "—"),
        ("Contract Ref", inv.get("contract_ref") or "—"),
    ]
    meta = Table(
        [[Paragraph(k, s["metalabel"]), Paragraph(_esc(v), s["metaval"])] for k, v in meta_rows],
        colWidths=[28 * mm, 42 * mm])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    row = Table([[Paragraph("Invoice", s["title"]), meta]], colWidths=[100 * mm, 70 * mm])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


def _address_blocks(s, inv):
    def block(label, lines):
        rows = [[Paragraph(label, s["sectlabel"])]]
        for ln in lines:
            if ln:
                rows.append([Paragraph(_esc(ln), s["value"])])
        t = Table(rows, colWidths=[82 * mm])
        t.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t
    inv_addr = [inv.get("customer_name"), inv.get("customer_company"),
                inv.get("site_address") or inv.get("billing_address"),
                inv.get("customer_email"), inv.get("customer_phone")]
    del_addr = [inv.get("customer_name"), inv.get("site_name"),
                inv.get("site_address"), inv.get("asset_name") and f"Asset: {inv.get('asset_name')}"]
    grid = Table([[block("Invoice Address", inv_addr), block("Delivery Address", del_addr)]],
                 colWidths=[85 * mm, 85 * mm])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return grid


def _lines_table(s, inv):
    sym = inv.get("currency_symbol") or "£"
    data = [[Paragraph("Line Item Code", s["th"]), Paragraph("Description", s["th"]),
             Paragraph("Quantity", s["thR"]), Paragraph("Unit Price", s["thR"]),
             Paragraph("Net", s["thR"])]]
    lines = inv.get("lines") or []
    if not lines:
        data.append([Paragraph("", s["cell"]), Paragraph("No line items.", s["cell"]),
                     Paragraph("", s["cellR"]), Paragraph("", s["cellR"]), Paragraph("", s["cellR"])])
    for ln in lines:
        code = ln.get("code") or (ln.get("kind") or "").upper()[:8] or "—"
        desc = _esc(ln.get("description") or "—")
        if ln.get("notes"):
            desc += f"<br/><font color='#5B6570' size='7.5'>{_esc(ln['notes'])}</font>"
        data.append([
            Paragraph(_esc(code), s["cell"]),
            Paragraph(desc, s["cell"]),
            Paragraph(f"{float(ln.get('quantity', 0)):g}", s["cellR"]),
            Paragraph(f"{sym} {float(ln.get('unit_price', 0)):,.2f}", s["cellR"]),
            Paragraph(f"{sym} {float(ln.get('line_total', 0)):,.2f}", s["cellR"]),
        ])
    t = Table(data, colWidths=[26 * mm, 74 * mm, 20 * mm, 25 * mm, 25 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1, PULSE_NAVY),
    ]))
    return t


def _totals_block(s, inv):
    sym = inv.get("currency_symbol") or "£"
    net = float(inv.get("subtotal", 0))
    vat = float(inv.get("vat_amount", 0))
    gross = float(inv.get("total", 0))
    rows = [
        [Paragraph("NET", s["total_label"]), Paragraph(f"{sym} {net:,.2f}", s["total_value"])],
        [Paragraph("VAT", s["total_label"]), Paragraph(f"{sym} {vat:,.2f}", s["total_value"])],
        [Paragraph("GROSS", s["total_label"]), Paragraph(f"{sym} {gross:,.2f}", s["grand_value"])],
    ]
    t = Table(rows, colWidths=[30 * mm, 40 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("LINEBELOW", (0, 0), (-1, 1), 0.5, PULSE_BORDER),
        ("BACKGROUND", (0, 2), (-1, 2), PULSE_LIGHT),
    ]))
    return t


def _payment_and_vat(s, inv, c):
    pay_lines = [f"<b>Payment Details</b>  <font color='#5B6570'>{c.get('payment_terms', '')}</font>"]
    if c.get("bank_name"):
        pay_lines.append(f"<b>{c['bank_name']}</b>")
    if c.get("bank_account_name"):
        pay_lines.append(f"Account Name: {c['bank_account_name']}")
    if c.get("bank_account_number"):
        pay_lines.append(f"Account Number: {c['bank_account_number']}")
    if c.get("bank_sort_code"):
        pay_lines.append(f"Sort Code: {c['bank_sort_code']}")
    pay = Paragraph("<br/>".join(pay_lines), s["value"])
    vat = Paragraph(f"<b>VAT Reg. No.</b> {c['vat_reg']}" if c.get("vat_reg") else "", s["value"])
    t = Table([[pay, vat]], colWidths=[110 * mm, 60 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def build_engineer_invoice_pdf(inv: dict, *, is_mod: bool = False, company: dict | None = None) -> bytes:
    from utils.pulse_doc_template import make_pulse_doc
    s = pulse_styles()
    c = company or PULSE
    buf = BytesIO()
    doc = make_pulse_doc(buf, f"Invoice {inv.get('invoice_number') or ''}", is_mod=is_mod, company=company)

    flow = [pulse_header(s, company=company), Spacer(1, 6 * mm), _title_and_meta(s, inv), Spacer(1, 8 * mm),
            _address_blocks(s, inv), Spacer(1, 8 * mm)]

    if inv.get("description_of_work"):
        flow.append(section_label(s, "Description of Work"))
        flow.append(Paragraph(_esc(inv["description_of_work"]).replace("\n", "<br/>"), s["body"]))
        flow.append(Spacer(1, 4 * mm))

    flow.append(_lines_table(s, inv))
    flow.append(Spacer(1, 6 * mm))
    # Keep the totals + payment details + references together so a page break
    # never orphans the GROSS line or splits the bank details. On multi-page
    # invoices the line-item table (repeatRows=1) carries its header to each
    # page; this block then lands intact on the final page.
    tail = [
        _totals_block(s, inv),
        Spacer(1, 8 * mm),
        _payment_and_vat(s, inv, c),
        Spacer(1, 6 * mm),
    ]
    ref = inv.get("account_ref") or inv.get("customer_account_ref") or inv.get("invoice_number") or ""
    tail.append(Paragraph(
        f"Please quote the following reference on payment: <b>{_esc(ref)}</b>", s["muted"]))
    if company is None:
        for clause in PULSE["footer_clauses"][:2]:
            tail.append(Paragraph(_esc(clause), s["muted"]))
    elif c.get("footer_note"):
        tail.append(Paragraph(_esc(c["footer_note"]), s["muted"]))
    flow.append(KeepTogether(tail))

    if inv.get("notes"):
        flow.append(Spacer(1, 3 * mm))
        flow.append(section_label(s, "Notes"))
        flow.append(Paragraph(_esc(inv["notes"]).replace("\n", "<br/>"), s["muted"]))

    doc.build(flow)
    return buf.getvalue()


__all__ = ["build_engineer_invoice_pdf"]
