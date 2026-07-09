"""Contract PDF builder — rebuilt onto the shared Pulse document shell
(``utils/pulse_doc_template``) so a quote and the contract it became feel
like part of the same Pulse-branded family.

Sections: header · parties · cover summary · inclusions · exclusions ·
consumables · response times · pricing · terms · signature box.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_LIGHT, PULSE_BORDER, PULSE_MUTED,
    pulse_styles, pulse_header, section_label, make_pulse_doc,
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


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def _grid_style(header_row: bool = False) -> TableStyle:
    cmds = [
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header_row:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    return TableStyle(cmds)


def build_contract_pdf(contract: dict, org: dict, catalog: dict) -> bytes:
    """Render a service-contract document into a PDF byte string."""
    s = pulse_styles()
    h2 = ParagraphStyle("ct_h2", parent=s["sectlabel"], fontSize=12, leading=15,
                        spaceBefore=8, spaceAfter=4, textColor=PULSE_NAVY)
    body = s["body"]
    tiny = s["muted"]

    from utils.localization import org_localization, currency_symbol as _cur_sym
    _loc = org_localization(org)
    _sym = _cur_sym(contract.get("currency") or _loc["currency"])
    _tax_label = contract.get("tax_label") or _loc["tax_label"]

    buf = io.BytesIO()
    doc = make_pulse_doc(buf, f"Contract {contract.get('contract_number') or ''}")
    story: list[Any] = [pulse_header(s), Spacer(1, 6 * mm)]

    # 1 · Title.
    story.append(Paragraph("Service Contract", s["title"]))
    cn = contract.get("contract_number") or contract.get("id", "")[:8]
    story.append(Paragraph(
        f"#{_esc(cn)} · {_esc(contract.get('title') or 'Service contract')} · "
        f"{_esc((contract.get('tier') or '').upper())}", tiny))
    story.append(Spacer(1, 4 * mm))

    # 2 · Parties.
    org_name = org.get("name") or "Pulse Fitness"
    parties = [
        [Paragraph("<b>Provider</b>", body), Paragraph("<b>Customer</b>", body),
         Paragraph("<b>Site</b>", body)],
        [Paragraph(_esc(org_name), body), Paragraph(_esc(contract.get("company_name") or "—"), body),
         Paragraph(_esc(contract.get("site_name") or "All sites"), body)],
    ]
    pt = Table(parties, colWidths=[58 * mm, 58 * mm, 58 * mm])
    pt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_LIGHT),
    ]))
    story.append(pt)
    story.append(Spacer(1, 4 * mm))

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
        f"response-time band(s). Cover starts {_esc(contract.get('start_date') or '—')} "
        f"and ends {_esc(contract.get('end_date') or '—')}.", body))

    # 5 · Inclusions.
    story.append(Paragraph("Inclusions", h2))
    inclusions = contract.get("inclusions") or {}
    inc_rows = []
    for group_key, items in inclusions.items():
        if not items:
            continue
        group_label = _GROUP_LABELS.get(group_key, group_key.replace("_", " ").title())
        labels = ", ".join(_label_for_inclusion(catalog, group_key, k) for k in items)
        inc_rows.append([Paragraph(f"<b>{_esc(group_label)}</b>", body), Paragraph(_esc(labels), body)])
    if inc_rows:
        it = Table(inc_rows, colWidths=[40 * mm, 134 * mm])
        it.setStyle(_grid_style())
        story.append(it)
    else:
        story.append(Paragraph("<i>No structured inclusions configured.</i>", tiny))

    # 6 · Exclusions.
    excl = contract.get("exclusions_structured") or []
    if excl:
        story.append(Paragraph("Exclusions", h2))
        story.append(Paragraph(
            " · ".join(_esc(_label_for_exclusion(catalog, k)) for k in excl), body))

    # 7 · Consumables.
    cons = contract.get("consumables") or []
    if cons:
        story.append(Paragraph("Consumables", h2))
        rows = [["Item", "Included", "Charge"]]
        for c in cons:
            rows.append([c.get("name") or "—", "Yes" if c.get("included") else "No",
                         f"{_sym}{float(c.get('charge') or 0):.2f}"])
        ct = Table(rows, colWidths=[100 * mm, 30 * mm, 40 * mm])
        ct.setStyle(_grid_style(header_row=True))
        story.append(ct)

    # 8 · Response times.
    rt = contract.get("response_times") or {}
    if rt:
        story.append(Paragraph("Response Times", h2))
        rows = [["Band", "Target", "Unit"]]
        for key, label in _BAND_LABELS.items():
            entry = rt.get(key)
            if not entry:
                continue
            rows.append([label, str(entry.get("hours", "—")), entry.get("unit", "hours")])
        rtt = Table(rows, colWidths=[84 * mm, 40 * mm, 50 * mm])
        rtt.setStyle(_grid_style(header_row=True))
        story.append(rtt)

    # 9 · Pricing.
    p = contract.get("pricing") or {}
    story.append(Paragraph("Pricing", h2))
    annual = float(p.get("annual_value") or contract.get("annual_value") or 0)
    monthly = float(p.get("monthly_value") or annual / 12)
    setup = float(p.get("setup_fee") or 0)
    vat_pct = float(p.get("vat_percent") or 0)
    rows = [
        ["Annual value",       f"{_sym}{annual:,.2f}"],
        ["Monthly equivalent", f"{_sym}{monthly:,.2f}"],
        ["Setup fee",          f"{_sym}{setup:,.2f}"],
        [_tax_label,           f"{vat_pct:.1f}%"],
    ]
    if (p.get("discount_percent") or 0) > 0:
        rows.append(["Discount", f"{p.get('discount_percent'):.1f}%"])
    if (p.get("uplift_percent") or 0) > 0:
        rows.append(["Uplift", f"{p.get('uplift_percent'):.1f}%"])
    pt2 = Table(rows, colWidths=[60 * mm, 60 * mm])
    pt2.setStyle(_grid_style())
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
                story.append(Paragraph(f"<b>{_esc(line[4:])}</b>", body))
            elif line.startswith("- "):
                story.append(Paragraph(f"• {_esc(line[2:])}", body))
            else:
                story.append(Paragraph(_esc(line), body))

    # 11 · Signature box.
    story.append(Spacer(1, 8 * mm))
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
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), PULSE_MUTED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(sig)

    doc.build(story)
    return buf.getvalue()
