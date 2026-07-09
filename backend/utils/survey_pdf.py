"""Branded Installation Handover PDF for Pre-Install Site Surveys.

Rebuilt onto the shared Pulse document shell (``utils/pulse_doc_template``)
so the handover carries the same Pulse header / footer / palette as every
other generated document.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_MUTED, PULSE_BORDER,
    pulse_styles, pulse_header, make_pulse_doc,
)


def _fmt(v):
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    if v in (None, ""):
        return "—"
    return str(v)


def _kv_table(rows, s):
    data = [[Paragraph(str(k), s["label"]), Paragraph(_fmt(v), s["value"])] for k, v in rows]
    if not data:
        data = [[Paragraph("—", s["label"]), Paragraph("—", s["value"])]]
    t = Table(data, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, PULSE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _section(title, rows, s, story):
    story.append(Paragraph(title, s["sectlabel"]))
    story.append(HRFlowable(width="100%", thickness=1.2, color=PULSE_NAVY, spaceAfter=4))
    story.append(_kv_table(rows, s))


def _tbl_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


def build_handover_pdf(h: dict) -> bytes:
    s = pulse_styles()
    buf = io.BytesIO()
    doc = make_pulse_doc(buf, f"Installation Handover {h.get('reference', '')}")
    story = [pulse_header(s), Spacer(1, 6 * mm)]

    story.append(Paragraph("Installation Handover Report", s["title"]))
    story.append(Paragraph(
        f"Ref {h.get('reference', '—')} &nbsp;·&nbsp; {h.get('company_name', '—')} "
        f"&nbsp;·&nbsp; {h.get('site_name') or '—'} &nbsp;·&nbsp; "
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y')}", s["muted"]))
    story.append(Spacer(1, 4 * mm))

    readiness = h.get("readiness") or {}
    _section("Overview", [
        ("Survey type", h.get("survey_type")),
        ("Survey date", h.get("survey_date")),
        ("Target install date", h.get("target_install_date")),
        ("Completed by", h.get("completed_by")),
        ("Installation manager", h.get("installation_manager")),
        ("Status", h.get("status")),
        ("Readiness", readiness.get("status")),
    ], s, story)

    crit = readiness.get("critical_missing") or []
    if crit:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "<b>Actions required before install:</b> " + ", ".join(crit),
            ParagraphStyle("warn", textColor=colors.HexColor("#B00020"), fontSize=9)))

    sd = h.get("site_details") or {}
    _section("Site & Access", [
        ("Site address", sd.get("site_address")),
        ("Access hours", sd.get("access_hours")),
        ("Room location", sd.get("room_location")),
    ] + [(k.replace("_", " ").title(), v) for k, v in (h.get("access") or {}).items()][:10], s, story)

    _section("Parking / Loading", [(k.replace("_", " ").title(), v)
                                    for k, v in (h.get("parking") or {}).items()][:10], s, story)
    _section("Power / Electrical", [(k.replace("_", " ").title(), v)
                                     for k, v in (h.get("power") or {}).items()][:12], s, story)
    _section("Network", [(k.replace("_", " ").title(), v)
                         for k, v in (h.get("network") or {}).items()][:8], s, story)
    _section("Flooring / Walls / Ceiling", (
        [("Floor: " + k.replace("_", " "), v) for k, v in (h.get("flooring") or {}).items()][:5] +
        [("Wall: " + k.replace("_", " "), v) for k, v in (h.get("walls") or {}).items()][:5] +
        [("Ceiling: " + k.replace("_", " "), v) for k, v in (h.get("ceiling") or {}).items()][:5]), s, story)

    rooms = h.get("rooms") or []
    if rooms:
        story.append(Paragraph("Rooms / Areas", s["sectlabel"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=PULSE_NAVY, spaceAfter=4))
        head = ["Room", "Use", "L", "W", "H", "Ceiling"]
        data = [head] + [[
            _fmt(r.get("room_name")), _fmt(r.get("room_use")), _fmt(r.get("room_length")),
            _fmt(r.get("room_width")), _fmt(r.get("room_height")), _fmt(r.get("ceiling_height"))]
            for r in rooms]
        t = Table(data, colWidths=[45 * mm, 45 * mm, 18 * mm, 18 * mm, 18 * mm, 21 * mm])
        t.setStyle(_tbl_style())
        story.append(t)

    equipment = h.get("equipment") or []
    if equipment:
        story.append(Paragraph("Proposed Equipment", s["sectlabel"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=PULSE_NAVY, spaceAfter=4))
        head = ["Category", "Manufacturer", "Model", "Qty", "Area"]
        data = [head] + [[
            _fmt(e.get("category")), _fmt(e.get("manufacturer")), _fmt(e.get("model")),
            _fmt(e.get("quantity")), _fmt(e.get("proposed_area"))] for e in equipment]
        t = Table(data, colWidths=[38 * mm, 38 * mm, 40 * mm, 15 * mm, 34 * mm])
        t.setStyle(_tbl_style())
        story.append(t)

    risks = h.get("risks") or []
    if risks:
        story.append(Paragraph("Risks", s["sectlabel"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=PULSE_NAVY, spaceAfter=4))
        head = ["Category", "Level", "Description", "Mitigation"]
        data = [head] + [[
            _fmt(r.get("category")), _fmt(r.get("risk_level")),
            Paragraph(_fmt(r.get("description")), s["value"]),
            Paragraph(_fmt(r.get("mitigation")), s["value"])] for r in risks]
        t = Table(data, colWidths=[35 * mm, 20 * mm, 55 * mm, 55 * mm])
        t.setStyle(_tbl_style())
        story.append(t)

    cr = h.get("customer_requirements") or {}
    if any(cr.values()):
        _section("Customer Requirements", [(k.replace("_", " ").title(), v)
                                           for k, v in cr.items()][:10], s, story)

    if h.get("installation_notes"):
        story.append(Paragraph("Installation Notes", s["sectlabel"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=PULSE_NAVY, spaceAfter=4))
        story.append(Paragraph(_fmt(h.get("installation_notes")), s["value"]))

    atts = h.get("attachments") or []
    if atts:
        _section("Attachments", [(a.get("category"), a.get("filename")) for a in atts][:30], s, story)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=PULSE_BORDER))
    story.append(Paragraph(
        "This handover was generated from the Pulse Fitness Pre-Install Site Survey. "
        "Installation must not proceed while critical actions remain outstanding "
        "unless a manager override has been recorded.", s["muted"]))

    doc.build(story)
    return buf.getvalue()
