"""Consolidated customer Warranty Certificate PDF.

One branded certificate the customer can print from their Warranty Register:
their whole kit list grouped by warranty level, with serials and cover-until
dates. Rendered on the shared Pulse document shell (Pulse-issued warranty).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_BORDER, PULSE_LIGHT, PULSE_MUTED,
    pulse_styles, pulse_header, make_pulse_doc, section_label,
)
from utils.warranty import get_tier, WARRANTY_TIERS


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Group order: known tiers first (least→most cover), then a "Manufacturer" bucket.
_TIER_ORDER = [t["code"] for t in WARRANTY_TIERS] + ["_manufacturer"]


def build_warranty_certificate_pdf(*, customer_name: str, equipment: list[dict]) -> bytes:
    s = pulse_styles()
    buf = BytesIO()
    doc = make_pulse_doc(buf, f"Warranty Certificate — {customer_name}")
    story: list = [pulse_header(s), Spacer(1, 6 * mm)]

    story.append(Paragraph("Warranty Certificate", s["title"]))
    story.append(Spacer(1, 2 * mm))
    meta = [
        ["Issued to", customer_name or "—"],
        ["Issued on", datetime.now().strftime("%d %B %Y")],
        ["Units covered", str(len(equipment))],
    ]
    mt = Table(meta, colWidths=[34 * mm, 124 * mm])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), PULSE_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1A1A1A")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, PULSE_LIGHT),
    ]))
    story.append(mt)
    story.append(Spacer(1, 6 * mm))

    # Group equipment by warranty tier.
    groups: dict[str, list[dict]] = {}
    for e in equipment:
        code = e.get("warranty_tier") or "_manufacturer"
        groups.setdefault(code, []).append(e)

    for code in _TIER_ORDER:
        rows = groups.get(code)
        if not rows:
            continue
        tier = get_tier(code) if code != "_manufacturer" else None
        label = tier["label"] if tier else "Manufacturer warranty"
        summary = tier["summary"] if tier else ""
        story.append(section_label(s, label))
        if summary:
            story.append(Paragraph(_esc(summary), s["muted"]))
        story.append(Spacer(1, 1.5 * mm))
        head = ["Equipment", "Manufacturer / model", "Serial no.", "Cover until"]
        data = [[Paragraph(f"<b>{_esc(h)}</b>", s["th"]) for h in head]]
        for e in rows:
            mm_model = " / ".join([p for p in [e.get("manufacturer"), e.get("model")] if p]) or "—"
            data.append([
                Paragraph(_esc(e.get("name") or "Equipment"), s["cell"]),
                Paragraph(_esc(mm_model), s["cell"]),
                Paragraph(_esc(e.get("serial_number") or "—"), s["cell"]),
                Paragraph(_esc(e.get("warranty_expiry") or "—"), s["cell"]),
            ])
        tbl = Table(data, colWidths=[52 * mm, 52 * mm, 30 * mm, 24 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(
        "This certificate confirms the warranty cover held against the equipment "
        "listed above as at the issue date. Cover begins on each unit's handover "
        "date and excludes consumables, accidental damage and misuse. Please retain "
        "this certificate as proof of cover.", s["muted"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


__all__ = ["build_warranty_certificate_pdf"]
