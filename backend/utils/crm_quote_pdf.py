"""Branded CRM Quote → PDF builder.

Rebuilt onto the shared Pulse document shell (``utils/pulse_doc_template``)
so CRM quotes share the exact header / footer / palette as Pulse invoices,
engineer quotes, contracts, tenders, incident reports and site-survey
handovers.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, Paragraph, Spacer, Table, TableStyle,
)

from utils.pulse_doc_template import (
    PULSE, PULSE_NAVY, PULSE_LIGHT, PULSE_BORDER,
    pulse_styles, pulse_header, section_label, pulse_title, make_pulse_doc,
)


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_crm_quote_pdf(quote: dict, org: dict, company: dict | None = None) -> bytes:
    """Render the quote into a PDF byte string on the Pulse shell. Pass
    ``company`` (from the tenant's document-branding profile) to brand the
    header/footer/bank block with the tenant's own details; when omitted the
    document keeps the default Pulse branding."""
    s = pulse_styles()
    buf = io.BytesIO()
    doc = make_pulse_doc(buf, f"Quote {quote.get('quote_number') or ''}", company=company)
    c = company or PULSE

    from utils.localization import org_localization, currency_symbol as _cur_sym
    _loc = org_localization(org)
    sym = _cur_sym(quote.get("currency") or _loc["currency"])
    tax_label = quote.get("tax_label") or _loc["tax_label"]

    flow: list = [pulse_header(s, company=company), Spacer(1, 6 * mm)]

    # ── Title + meta panel ───────────────────────────────────────
    meta_rows = [
        ("Quote No.", quote.get("quote_number") or "—"),
        ("Date", datetime.now().strftime("%d %b %Y")),
    ]
    if quote.get("valid_until"):
        meta_rows.append(("Valid Until", str(quote.get("valid_until"))))
    meta_rows.append(("Status", (quote.get("status") or "draft").replace("_", " ").title()))
    meta = Table(
        [[Paragraph(k, s["metalabel"]), Paragraph(_esc(v), s["metaval"])] for k, v in meta_rows],
        colWidths=[28 * mm, 42 * mm])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    title_row = Table([[Paragraph("Quotation", s["title"]), meta]], colWidths=[100 * mm, 70 * mm])
    title_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    flow.append(title_row)
    flow.append(Spacer(1, 8 * mm))

    # ── Quote-for block ──────────────────────────────────────────
    flow.append(section_label(s, "Quote For"))
    if quote.get("company_name"):
        flow.append(Paragraph(f"<b>{_esc(quote['company_name'])}</b>", s["value"]))
    if quote.get("contact_name"):
        flow.append(Paragraph(_esc(quote["contact_name"]), s["value"]))
    if not quote.get("company_name") and not quote.get("contact_name"):
        flow.append(Paragraph("(No customer specified)", s["muted"]))
    if quote.get("title"):
        flow.append(Spacer(1, 2 * mm))
        flow.append(Paragraph(f"<b>Subject:</b> {_esc(quote['title'])}", s["value"]))
    flow.append(Spacer(1, 6 * mm))

    # ── Line items table ─────────────────────────────────────────
    data = [[Paragraph("Description", s["th"]), Paragraph("Qty", s["thR"]),
             Paragraph("Unit Price", s["thR"]), Paragraph("Disc %", s["thR"]),
             Paragraph("Net", s["thR"])]]
    items = quote.get("line_items", [])
    if not items:
        data.append([Paragraph("No line items.", s["cell"]), Paragraph("", s["cellR"]),
                     Paragraph("", s["cellR"]), Paragraph("", s["cellR"]), Paragraph("", s["cellR"])])
    for item in items:
        data.append([
            Paragraph(_esc(item.get("description") or item.get("product_name", "—")), s["cell"]),
            Paragraph(f"{item.get('quantity', 0):g}", s["cellR"]),
            Paragraph(f"{sym}{item.get('unit_price', 0):,.2f}", s["cellR"]),
            Paragraph(f"{item.get('discount_percent', 0):g}%", s["cellR"]),
            Paragraph(f"{sym}{item.get('subtotal', 0):,.2f}", s["cellR"]),
        ])
    t = Table(data, colWidths=[80 * mm, 18 * mm, 26 * mm, 20 * mm, 26 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1, PULSE_NAVY),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 6 * mm))

    # ── Totals + payment (kept together on the final page) ───────
    tax_rate = quote.get("tax_rate", quote.get("vat_rate", 20))
    total_rows = [
        [Paragraph("NET", s["total_label"]),
         Paragraph(f"{sym}{quote.get('subtotal', 0):,.2f}", s["total_value"])],
        [Paragraph(f"{tax_label} ({tax_rate:g}%)", s["total_label"]),
         Paragraph(f"{sym}{quote.get('tax_amount', 0):,.2f}", s["total_value"])],
        [Paragraph("TOTAL", s["total_label"]),
         Paragraph(f"{sym}{quote.get('total', 0):,.2f}", s["grand_value"])],
    ]
    totals = Table(total_rows, colWidths=[30 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("LINEBELOW", (0, 0), (-1, 1), 0.5, PULSE_BORDER),
        ("BACKGROUND", (0, 2), (-1, 2), PULSE_LIGHT),
    ]))
    tail = [totals, Spacer(1, 6 * mm)]
    if quote.get("notes"):
        tail.append(section_label(s, "Notes"))
        tail.append(Paragraph(_esc(quote["notes"]).replace("\n", "<br/>"), s["body"]))
        tail.append(Spacer(1, 3 * mm))
    tail.append(Paragraph(
        f"<b>Payment terms:</b> {c.get('payment_terms') or PULSE['payment_terms']}. "
        + (f"{c['bank_name']} · Account {c.get('bank_account_number', '')} · "
           f"Sort {c.get('bank_sort_code', '')}. " if c.get("bank_name") else "")
        + (f"VAT Reg No. {c['vat_reg']}." if c.get("vat_reg") else ""), s["muted"]))
    tail.append(Paragraph(
        f"<i>Prepared by {_esc(quote.get('created_by_name') or '—')} · "
        f"Generated {datetime.now().strftime('%d %b %Y')}</i>", s["muted"]))
    flow.append(KeepTogether(tail))

    doc.build(flow)
    return buf.getvalue()


async def render_quote_pdf(quote: dict, organization_id: str | None = None) -> bytes:
    """Async helper used by ``crm_v2.quote_pdf`` + ``send_quote_email``."""
    org: dict = {}
    company = None
    if organization_id:
        try:
            from utils.database import db as _db
            org_doc = await _db.organizations.find_one({"id": organization_id}, {"_id": 0})
            if org_doc:
                org = org_doc
            from utils.document_branding import resolve_company_if_configured
            company = await resolve_company_if_configured(_db, {"id": organization_id, "name": org.get("name")})
        except Exception:
            org = org or {}
    return build_crm_quote_pdf(quote, org, company=company)
