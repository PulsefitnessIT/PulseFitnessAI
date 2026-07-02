"""Branded Installation Handover PDF for Pre-Install Site Surveys.

Pulse Fitness brand (Core Blue #19CDFF / Soft Black #1B1C1D), Phase 1.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)

CORE_BLUE = colors.HexColor("#19CDFF")
SOFT_BLACK = colors.HexColor("#1B1C1D")
SLATE = colors.HexColor("#6E7476")
SILVER = colors.HexColor("#E0E0E0")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("PISHead", parent=ss["Title"], textColor=SOFT_BLACK, fontSize=20, spaceAfter=2))
    ss.add(ParagraphStyle("PISSub", parent=ss["Normal"], textColor=SLATE, fontSize=9, spaceAfter=8))
    ss.add(ParagraphStyle("PISSection", parent=ss["Heading2"], textColor=SOFT_BLACK, fontSize=12,
                          spaceBefore=12, spaceAfter=4))
    ss.add(ParagraphStyle("PISLabel", parent=ss["Normal"], textColor=SLATE, fontSize=8))
    ss.add(ParagraphStyle("PISVal", parent=ss["Normal"], textColor=SOFT_BLACK, fontSize=9))
    return ss


def _fmt(v):
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    if v in (None, ""):
        return "—"
    return str(v)


def _kv_table(rows, ss):
    data = [[Paragraph(str(k), ss["PISLabel"]), Paragraph(_fmt(v), ss["PISVal"])] for k, v in rows]
    if not data:
        data = [[Paragraph("—", ss["PISLabel"]), Paragraph("—", ss["PISVal"])]]
    t = Table(data, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, SILVER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _section(title, rows, ss, story):
    story.append(Paragraph(title, ss["PISSection"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=CORE_BLUE, spaceAfter=4))
    story.append(_kv_table(rows, ss))


def build_handover_pdf(h: dict) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title=f"Installation Handover {h.get('reference', '')}")
    story = []

    # Header band
    story.append(Paragraph("Pulse Fitness", ParagraphStyle(
        "brand", textColor=CORE_BLUE, fontSize=11, spaceAfter=0)))
    story.append(Paragraph("Installation Handover Report", ss["PISHead"]))
    story.append(Paragraph(
        f"Ref {h.get('reference', '—')} &nbsp;·&nbsp; {h.get('company_name', '—')} "
        f"&nbsp;·&nbsp; {h.get('site_name') or '—'} &nbsp;·&nbsp; "
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y')}", ss["PISSub"]))
    story.append(HRFlowable(width="100%", thickness=2, color=SOFT_BLACK, spaceAfter=6))

    readiness = h.get("readiness") or {}
    _section("Overview", [
        ("Survey type", h.get("survey_type")),
        ("Survey date", h.get("survey_date")),
        ("Target install date", h.get("target_install_date")),
        ("Completed by", h.get("completed_by")),
        ("Installation manager", h.get("installation_manager")),
        ("Status", h.get("status")),
        ("Readiness", readiness.get("status")),
    ], ss, story)

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
    ] + [(k.replace("_", " ").title(), v) for k, v in (h.get("access") or {}).items()][:10], ss, story)

    _section("Parking / Loading", [(k.replace("_", " ").title(), v)
                                    for k, v in (h.get("parking") or {}).items()][:10], ss, story)
    _section("Power / Electrical", [(k.replace("_", " ").title(), v)
                                     for k, v in (h.get("power") or {}).items()][:12], ss, story)
    _section("Network", [(k.replace("_", " ").title(), v)
                         for k, v in (h.get("network") or {}).items()][:8], ss, story)
    _section("Flooring / Walls / Ceiling", (
        [("Floor: " + k.replace("_", " "), v) for k, v in (h.get("flooring") or {}).items()][:5] +
        [("Wall: " + k.replace("_", " "), v) for k, v in (h.get("walls") or {}).items()][:5] +
        [("Ceiling: " + k.replace("_", " "), v) for k, v in (h.get("ceiling") or {}).items()][:5]), ss, story)

    # Rooms table
    rooms = h.get("rooms") or []
    if rooms:
        story.append(Paragraph("Rooms / Areas", ss["PISSection"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=CORE_BLUE, spaceAfter=4))
        head = ["Room", "Use", "L", "W", "H", "Ceiling"]
        data = [head] + [[
            _fmt(r.get("room_name")), _fmt(r.get("room_use")), _fmt(r.get("room_length")),
            _fmt(r.get("room_width")), _fmt(r.get("room_height")), _fmt(r.get("ceiling_height"))]
            for r in rooms]
        t = Table(data, colWidths=[45 * mm, 45 * mm, 18 * mm, 18 * mm, 18 * mm, 21 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SOFT_BLACK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, SILVER),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    # Equipment table
    equipment = h.get("equipment") or []
    if equipment:
        story.append(Paragraph("Proposed Equipment", ss["PISSection"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=CORE_BLUE, spaceAfter=4))
        head = ["Category", "Manufacturer", "Model", "Qty", "Area"]
        data = [head] + [[
            _fmt(e.get("category")), _fmt(e.get("manufacturer")), _fmt(e.get("model")),
            _fmt(e.get("quantity")), _fmt(e.get("proposed_area"))] for e in equipment]
        t = Table(data, colWidths=[38 * mm, 38 * mm, 40 * mm, 15 * mm, 34 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SOFT_BLACK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, SILVER),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    # Risks
    risks = h.get("risks") or []
    if risks:
        story.append(Paragraph("Risks", ss["PISSection"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=CORE_BLUE, spaceAfter=4))
        head = ["Category", "Level", "Description", "Mitigation"]
        data = [head] + [[
            _fmt(r.get("category")), _fmt(r.get("risk_level")),
            Paragraph(_fmt(r.get("description")), ss["PISVal"]),
            Paragraph(_fmt(r.get("mitigation")), ss["PISVal"])] for r in risks]
        t = Table(data, colWidths=[35 * mm, 20 * mm, 55 * mm, 55 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SOFT_BLACK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, SILVER),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    cr = h.get("customer_requirements") or {}
    if any(cr.values()):
        _section("Customer Requirements", [(k.replace("_", " ").title(), v)
                                           for k, v in cr.items()][:10], ss, story)

    if h.get("installation_notes"):
        story.append(Paragraph("Installation Notes", ss["PISSection"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=CORE_BLUE, spaceAfter=4))
        story.append(Paragraph(_fmt(h.get("installation_notes")), ss["PISVal"]))

    atts = h.get("attachments") or []
    if atts:
        _section("Attachments", [(a.get("category"), a.get("filename")) for a in atts][:30], ss, story)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=SILVER))
    story.append(Paragraph(
        "This handover was generated from the Pulse Fitness Pre-Install Site Survey. "
        "Installation must not proceed while critical actions remain outstanding "
        "unless a manager override has been recorded.", ss["PISSub"]))

    doc.build(story)
    return buf.getvalue()
