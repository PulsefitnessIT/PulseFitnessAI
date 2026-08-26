"""Customer Handover Pack PDF (Equipment Sales).

A branded pack handed to the customer at handover: the equipment they've
received (with serials), the warranty sold against each unit, and clear
instructions on how to log a fault. Rendered on the shared Pulse document
shell so it matches quotes / invoices / service reports, but branded with the
selling org's identity (logo/colour/name) when set, falling back to Pulse.
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
from utils.warranty import get_tier


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fetch_logo_bytes(url: str | None) -> bytes | None:
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        import httpx
        r = httpx.get(url, timeout=4.0, follow_redirects=True)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def _company_identity(brand: dict) -> dict:
    """Build the header/footer company dict for the shared template from the
    resolved CRM brand. Pulse-branded packs use the default Pulse identity;
    tenant-branded packs carry the tenant name + best-effort logo."""
    name = (brand or {}).get("company_name") or "Pulse Fitness"
    is_pulse = name.strip().lower() in ("pulse fitness", "pulse fitness ltd", "pulse fitness limited")
    if is_pulse:
        return None  # None → shared template uses the full default Pulse identity
    logo_bytes = _fetch_logo_bytes((brand or {}).get("logo_url"))
    return {
        "name": name,
        "tagline": "",
        "logo_bytes": logo_bytes,
        "use_default_logo": False,
        "footer_brand_line": name,
    }


def build_handover_pack_pdf(
    *,
    brand: dict,
    quote: dict,
    company_name: str,
    equipment: list[dict],
    fault_instructions: dict,
    is_mod: bool = False,
) -> bytes:
    company = _company_identity(brand)
    primary = colors.HexColor((brand or {}).get("primary_color") or "#0B3D91")
    s = pulse_styles()
    buf = BytesIO()
    title = f"Equipment handover pack — {quote.get('quote_number') or ''}".strip()
    doc = make_pulse_doc(buf, title, is_mod=is_mod, company=company)

    story: list = [pulse_header(s, company=company), Spacer(1, 6 * mm)]

    # ── Title + meta ────────────────────────────────────────────────
    story.append(Paragraph("Equipment Handover Pack", s["title"]))
    story.append(Spacer(1, 2 * mm))
    meta_rows = [
        ["Customer", company_name or "—"],
        ["Reference", quote.get("quote_number") or "—"],
        ["Handover date", datetime.now().strftime("%d %B %Y")],
        ["Units handed over", str(len(equipment))],
    ]
    mt = Table(meta_rows, colWidths=[38 * mm, 120 * mm])
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
    story.append(Spacer(1, 7 * mm))

    # ── Equipment table ─────────────────────────────────────────────
    story.append(section_label(s, "Your equipment"))
    story.append(Spacer(1, 2 * mm))
    head = ["#", "Equipment", "Manufacturer / model", "Serial no.", "Warranty", "Cover until"]
    rows = [[Paragraph(f"<b>{_esc(h)}</b>", s["th"]) for h in head]]
    if not equipment:
        rows.append([Paragraph("—", s["cell"])] + [Paragraph("No equipment registered yet.", s["cell"])] + [Paragraph("", s["cell"])] * 4)
    for i, e in enumerate(equipment, start=1):
        tier = get_tier(e.get("warranty_tier"))
        mm_model = " / ".join([p for p in [e.get("manufacturer"), e.get("model")] if p]) or "—"
        rows.append([
            Paragraph(str(i), s["cell"]),
            Paragraph(_esc(e.get("name") or "Equipment"), s["cell"]),
            Paragraph(_esc(mm_model), s["cell"]),
            Paragraph(_esc(e.get("serial_number") or "—"), s["cell"]),
            Paragraph(_esc(tier["label"]), s["cell"]),
            Paragraph(_esc(e.get("warranty_expiry") or "—"), s["cell"]),
        ])
    tbl = Table(rows, colWidths=[8 * mm, 42 * mm, 40 * mm, 28 * mm, 26 * mm, 22 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 7 * mm))

    # ── Warranty summary (distinct tiers on this pack) ──────────────
    tier_codes = []
    for e in equipment:
        code = get_tier(e.get("warranty_tier"))["code"]
        if code not in tier_codes:
            tier_codes.append(code)
    if tier_codes:
        story.append(section_label(s, "What your warranty covers"))
        story.append(Spacer(1, 1.5 * mm))
        for code in tier_codes:
            t = get_tier(code)
            story.append(Paragraph(f"<b>{_esc(t['label'])}</b> — {_esc(t['summary'])}", s["body"]))
        story.append(Paragraph(
            "Warranty begins on the handover date shown above. Cover excludes "
            "consumables, accidental damage and misuse. Please keep this pack "
            "as proof of cover.", s["muted"]))
        story.append(Spacer(1, 7 * mm))

    # ── How to log a fault ──────────────────────────────────────────
    story.append(section_label(s, "How to log a fault"))
    story.append(Spacer(1, 1.5 * mm))
    if fault_instructions.get("portal_url"):
        story.append(Paragraph(
            f"Log any fault instantly through your Pulse portal at "
            f"<b>{_esc(fault_instructions['portal_url'])}</b> — sign in, open "
            f"<b>Report a fault</b>, pick the affected machine (already listed "
            f"on your account) and describe the issue. You'll get a reference "
            f"and live updates as our engineers respond.", s["body"]))
    else:
        story.append(Paragraph(
            "To log a fault, contact our service desk quoting the serial "
            "number of the affected machine (listed above):", s["body"]))
    contact_bits = []
    if fault_instructions.get("phone"):
        contact_bits.append(["Phone", fault_instructions["phone"]])
    if fault_instructions.get("email"):
        contact_bits.append(["Email", fault_instructions["email"]])
    if contact_bits:
        ct = Table(contact_bits, colWidths=[24 * mm, 134 * mm])
        ct.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (0, -1), PULSE_NAVY),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(Spacer(1, 1.5 * mm))
        story.append(ct)

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


__all__ = ["build_handover_pack_pdf"]
