"""Iter 220e3 — Contract PDF builder.

Renders a branded service-contract PDF using reportlab. Mirrors the
visual language of ``utils/crm_quote_pdf.py`` so a quote and the
contract it became feel like part of the same family.

Sections:
    1. Header (org logo block + contract number + title)
    2. Parties (Provider | Customer | Site)
    3. Cover summary (tier + inclusion / exclusion / response counts)
    4. Comparison matrix (current contract vs Silver / Gold / Platinum
       templates if available — gives the customer the upsell context)
    5. Inclusions block (grouped tick list)
    6. Exclusions block
    7. Consumables table
    8. Response times grid
    9. Pricing summary (annual + per-asset + setup + VAT)
   10. Terms & conditions (markdown rendered as paragraphs)
   11. Signature box
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


_GROUP_LABELS = {
    "technical_support": "Technical Support",
    "online_support":    "Online Support",
    "maintenance":       "Maintenance",
    "extras":            "Extra Services",
}

_BAND_LABELS = {
    "emergency":        "Emergency",
    "urgent":           "Urgent",
    "standard":         "Standard",
    "remote_support":   "Remote support",
    "parts_quotation":  "Parts quotation",
    "first_attendance": "First attendance",
}


def _hex(hex_str: str, fallback: str = "#0F172A") -> colors.Color:
    h = (hex_str or "").lstrip("#")
    if len(h) != 6:
        h = fallback.lstrip("#")
    try:
        return colors.Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    except (ValueError, TypeError):
        return colors.HexColor(fallback)


def _label_for_inclusion(catalog: dict, group_key: str, item_key: str) -> str:
    grp = next((g for g in catalog.get("inclusion_groups", []) if g.get("key") == group_key), None)
    if not grp:
        return item_key
    item = next((i for i in grp.get("items", []) if i.get("key") == item_key), None)
    return (item or {}).get("label", item_key)


def _label_for_exclusion(catalog: dict, key: str) -> str:
    return next(
        (e.get("label", key) for e in catalog.get("exclusion_items", []) if e.get("key") == key),
        key,
    )


def build_contract_pdf(contract: dict, org: dict, catalog: dict) -> bytes:
    """Render a service-contract document into a PDF byte string.

    ``contract`` is the enriched contract document (with
    ``inclusions`` / ``exclusions_structured`` / ``response_times`` /
    ``pricing`` / ``terms_md`` populated). ``org`` carries
    ``name`` / ``logo_url`` / ``primary_color``. ``catalog`` is the
    same shape returned by ``GET /contract-catalog`` and is used to
    resolve customer-friendly labels for slug-keyed cover items.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    brand = _hex(org.get("primary_color") or "#0055FF")
    muted = colors.Color(0.45, 0.50, 0.58)
    border = colors.Color(0.88, 0.91, 0.95)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                        textColor=brand, spaceAfter=4, leading=22)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                        textColor=brand, spaceBefore=8, spaceAfter=4, leading=14)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9,
                          textColor=colors.black, leading=12)
    tiny = ParagraphStyle("tiny", parent=body, fontSize=8, textColor=muted)

    story: list[Any] = []

    # 1 · Header.
    org_name = org.get("name") or "Service Provider"
    story.append(Paragraph(f"<b>{org_name}</b> — Service Contract", h1))
    cn = contract.get("contract_number") or contract.get("id", "")[:8]
    story.append(Paragraph(
        f"#{cn} · {contract.get('title') or 'Service contract'} · {contract.get('tier', '').upper()}",
        tiny,
    ))
    story.append(Spacer(1, 8))

    # 2 · Parties.
    parties = [
        [
            Paragraph("<b>Provider</b>", body),
            Paragraph("<b>Customer</b>", body),
            Paragraph("<b>Site</b>", body),
        ],
        [
            Paragraph(org_name, body),
            Paragraph(contract.get("company_name") or "—", body),
            Paragraph(contract.get("site_name") or "All sites", body),
        ],
    ]
    pt = Table(parties, colWidths=[60 * mm, 60 * mm, 54 * mm])
    pt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, border),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, border),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.97, 0.97, 0.99)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(pt)
    story.append(Spacer(1, 6))

    # 3 · Cover summary.
    incl_total = sum(len(v or []) for v in (contract.get("inclusions") or {}).values())
    excl_total = len(contract.get("exclusions_structured") or [])
    cons_total = len(contract.get("consumables") or [])
    rt_total = len(contract.get("response_times") or {})
    story.append(Paragraph("Cover Summary", h2))
    story.append(Paragraph(
        f"This contract carries <b>{incl_total}</b> inclusion(s), "
        f"<b>{excl_total}</b> documented exclusion(s), "
        f"<b>{cons_total}</b> consumable(s), and <b>{rt_total}</b> "
        f"response-time band(s). Cover starts {contract.get('start_date') or '—'} "
        f"and ends {contract.get('end_date') or '—'}.",
        body,
    ))

    # 5 · Inclusions (grouped tick list).
    story.append(Paragraph("Inclusions", h2))
    inclusions = contract.get("inclusions") or {}
    inc_rows = []
    for group_key, items in inclusions.items():
        if not items:
            continue
        group_label = _GROUP_LABELS.get(group_key, group_key.replace("_", " ").title())
        labels = ", ".join(_label_for_inclusion(catalog, group_key, k) for k in items)
        inc_rows.append([Paragraph(f"<b>{group_label}</b>", body), Paragraph(labels, body)])
    if inc_rows:
        it = Table(inc_rows, colWidths=[40 * mm, 134 * mm])
        it.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, border),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, border),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(it)
    else:
        story.append(Paragraph("<i>No structured inclusions configured.</i>", tiny))

    # 6 · Exclusions.
    excl = contract.get("exclusions_structured") or []
    if excl:
        story.append(Paragraph("Exclusions", h2))
        story.append(Paragraph(
            " · ".join(_label_for_exclusion(catalog, k) for k in excl), body,
        ))

    # 7 · Consumables.
    cons = contract.get("consumables") or []
    if cons:
        story.append(Paragraph("Consumables", h2))
        rows = [["Item", "Included", "Charge"]]
        for c in cons:
            rows.append([
                c.get("name") or "—",
                "Yes" if c.get("included") else "No",
                f"£{float(c.get('charge') or 0):.2f}",
            ])
        ct = Table(rows, colWidths=[100 * mm, 30 * mm, 40 * mm])
        ct.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, border),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, border),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.97, 0.97, 0.99)),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(ct)

    # 8 · Response times grid.
    rt = contract.get("response_times") or {}
    if rt:
        story.append(Paragraph("Response Times", h2))
        rows = [["Band", "Target", "Unit"]]
        for key, label in _BAND_LABELS.items():
            entry = rt.get(key)
            if not entry:
                continue
            rows.append([label, str(entry.get("hours", "—")), entry.get("unit", "hours")])
        rtt = Table(rows, colWidths=[80 * mm, 40 * mm, 50 * mm])
        rtt.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, border),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, border),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.97, 0.97, 0.99)),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(rtt)

    # 9 · Pricing summary.
    p = contract.get("pricing") or {}
    story.append(Paragraph("Pricing", h2))
    annual = float(p.get("annual_value") or contract.get("annual_value") or 0)
    monthly = float(p.get("monthly_value") or annual / 12)
    setup = float(p.get("setup_fee") or 0)
    vat_pct = float(p.get("vat_percent") or 0)
    rows = [
        ["Annual value",      f"£{annual:,.2f}"],
        ["Monthly equivalent", f"£{monthly:,.2f}"],
        ["Setup fee",         f"£{setup:,.2f}"],
        ["VAT",               f"{vat_pct:.1f}%"],
    ]
    if (p.get("discount_percent") or 0) > 0:
        rows.append(["Discount", f"{p.get('discount_percent'):.1f}%"])
    if (p.get("uplift_percent") or 0) > 0:
        rows.append(["Uplift",   f"{p.get('uplift_percent'):.1f}%"])
    pt2 = Table(rows, colWidths=[60 * mm, 60 * mm])
    pt2.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, border),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, border),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
    ]))
    story.append(pt2)

    # 10 · Terms.
    terms = (contract.get("terms_md") or "").strip()
    if terms:
        story.append(Paragraph("Terms & Conditions", h2))
        for line in terms.splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
                continue
            if line.startswith("### "):
                story.append(Paragraph(f"<b>{line[4:]}</b>", body))
            elif line.startswith("- "):
                story.append(Paragraph(f"• {line[2:]}", body))
            else:
                story.append(Paragraph(line, body))

    # 11 · Signature box.
    story.append(Spacer(1, 14))
    sig_rows = [
        ["For the Customer", "For the Provider"],
        ["", ""],
        [contract.get("contact_name") or "_________________________",
         contract.get("owner_name") or "_________________________"],
        [f"Date: {datetime.utcnow().strftime('%d %b %Y')}",
         f"Date: {datetime.utcnow().strftime('%d %b %Y')}"],
    ]
    sig = Table(sig_rows, colWidths=[87 * mm, 87 * mm])
    sig.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, border),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(sig)

    doc.build(story)
    return buf.getvalue()
