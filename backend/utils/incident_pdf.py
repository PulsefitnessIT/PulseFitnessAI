"""Iter 220t — Branded incident PDF exports.

Six PDF types share a common header / footer / theming module so the
output feels like one product, not a stack of unrelated reports.

* ``accident_report_pdf``         — single incident, full detail
* ``witness_statement_pdf``       — single signed statement
* ``investigation_report_pdf``    — findings + root causes + actions
* ``riddor_report_pdf``           — F2508-style cover sheet + audit
* ``corrective_action_log_pdf``   — all open + closed actions
* ``management_summary_pdf``      — period dashboard (counts + RIDDOR)
"""
from __future__ import annotations

import base64
import io
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)

PRIMARY = colors.HexColor("#1d4ed8")
ACCENT = colors.HexColor("#9D4CDD")
NAVY = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#F1F5F9")
BORDER = colors.HexColor("#E2E8F0")
AMBER = colors.HexColor("#D97706")
GREEN = colors.HexColor("#059669")
RED = colors.HexColor("#DC2626")

SEV_COLOR = {
    "minor": colors.HexColor("#94A3B8"),
    "moderate": colors.HexColor("#F59E0B"),
    "serious": colors.HexColor("#EA580C"),
    "major": RED,
    "fatal": colors.HexColor("#9F1239"),
}

RIDDOR_COLOR = {
    "not_assessed": MUTED,
    "non_riddor": GREEN,
    "potential": AMBER,
    "confirmed": RED,
    "submitted": PRIMARY,
    "closed": MUTED,
}


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Title"], fontSize=20, leading=24,
                             textColor=colors.white, alignment=TA_LEFT, spaceAfter=2),
        "kicker": ParagraphStyle("k", parent=base["Normal"], fontSize=8, leading=10,
                                 textColor=colors.white, alignment=TA_LEFT, spaceAfter=4,
                                 fontName="Helvetica-Bold"),
        "section": ParagraphStyle("s", parent=base["Heading2"], fontSize=11, leading=14,
                                  textColor=NAVY, spaceBefore=12, spaceAfter=6,
                                  fontName="Helvetica-Bold"),
        "label": ParagraphStyle("l", parent=base["Normal"], fontSize=8, leading=10,
                                textColor=MUTED, spaceAfter=1, fontName="Helvetica-Bold"),
        "value": ParagraphStyle("v", parent=base["Normal"], fontSize=10, leading=13,
                                textColor=NAVY, spaceAfter=2),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=10, leading=14,
                               textColor=NAVY, spaceAfter=4),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8.5, leading=11,
                                textColor=MUTED, spaceAfter=2),
        "pill_white": ParagraphStyle("pw", parent=base["Normal"], fontSize=8,
                                     textColor=colors.white, alignment=TA_CENTER,
                                     fontName="Helvetica-Bold"),
    }


def _header_factory(title: str, subtitle: str, brand: str = "GymAxis"):
    """Return a (canvas, doc) callback that paints the branded header
    band + footer on every page."""
    from utils.pdf_footer import draw_pdf_footer

    def _on_page(canv, doc):
        canv.saveState()
        # Top band — solid navy with a thin gradient-ish accent stripe.
        canv.setFillColor(NAVY)
        canv.rect(0, doc.pagesize[1] - 28 * mm, doc.pagesize[0], 28 * mm, fill=1, stroke=0)
        canv.setFillColor(ACCENT)
        canv.rect(0, doc.pagesize[1] - 28 * mm, 6 * mm, 28 * mm, fill=1, stroke=0)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 16)
        canv.drawString(14 * mm, doc.pagesize[1] - 14 * mm, title)
        canv.setFont("Helvetica", 9.5)
        canv.drawString(14 * mm, doc.pagesize[1] - 20 * mm, subtitle)
        canv.setFont("Helvetica-Bold", 8.5)
        canv.setFillColor(colors.HexColor("#A8B0BC"))
        canv.drawRightString(doc.pagesize[0] - 14 * mm, doc.pagesize[1] - 14 * mm, brand)
        canv.setFont("Helvetica", 7.5)
        canv.drawRightString(
            doc.pagesize[0] - 14 * mm, doc.pagesize[1] - 20 * mm,
            f"Generated {datetime.utcnow().strftime('%-d %b %Y · %H:%MZ')}",
        )
        canv.restoreState()
        try:
            draw_pdf_footer(canv, doc)
        except Exception:
            pass

    return _on_page


def _build_doc(buf: BytesIO, title: str, subtitle: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=34 * mm, bottomMargin=18 * mm,
        title=title,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_header_factory(title, subtitle))])
    return doc


def _kv_table(rows: list[tuple[str, str]], st) -> Table:
    data = []
    for label, value in rows:
        data.append([Paragraph(_esc(label), st["label"]),
                     Paragraph(_esc(value or "—"), st["value"])])
    t = Table(data, colWidths=[44 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER),
    ]))
    return t


def _pill(label: str, color, st) -> Table:
    cell = Paragraph(_esc(label.upper()), st["pill_white"])
    t = Table([[cell]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0, color),
    ]))
    return t


def _signature_block(sig: dict, st) -> list:
    """Embed a captured signature (data URL or raw PNG bytes) plus the
    typed name / role / timestamp legal-line."""
    flow: list = []
    flow.append(Paragraph(_esc(f"{sig.get('role','').title() or 'Signed by'}: {sig.get('name','')}"),
                          st["value"]))
    img = sig.get("image_data_url") or sig.get("image_b64")
    if img:
        try:
            if isinstance(img, str) and img.startswith("data:"):
                img = img.split(",", 1)[1]
            raw = base64.b64decode(img) if isinstance(img, str) else img
            # Validate eagerly with PIL so ReportLab's deferred image
            # load doesn't blow up at doc.build() for truncated PNGs.
            from PIL import Image as PILImage  # type: ignore
            pim = PILImage.open(io.BytesIO(raw))
            pim.load()
            if pim.size[0] < 20 or pim.size[1] < 8:
                raise ValueError("signature image too small")
            flow.append(RLImage(io.BytesIO(raw), width=70 * mm, height=22 * mm))
        except Exception:
            flow.append(Paragraph("[Signature image unavailable]", st["small"]))
    when = sig.get("signed_at")
    if when:
        if isinstance(when, datetime):
            when = when.strftime("%-d %b %Y · %H:%M UTC")
        flow.append(Paragraph(_esc(f"Signed {when}"), st["small"]))
    return flow


def _date_str(dt) -> str:
    if not dt:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    return dt.strftime("%-d %b %Y · %H:%M UTC")


# ── Public generators ────────────────────────────────────────────


def accident_report_pdf(incident: dict, org_name: str = "", actions: list | None = None) -> bytes:
    """Single incident, full detail. Used as the legally defensible
    record of an accident."""
    buf = BytesIO()
    doc = _build_doc(
        buf,
        title=f"Accident Report · {incident.get('reference', '')}",
        subtitle=f"{org_name or 'GymAxis'} · {incident.get('kind', 'incident').replace('_',' ').title()}",
    )
    st = _styles()
    flow: list = []
    # Status pills row
    sev = incident.get("severity", "minor")
    rid = (incident.get("riddor") or {}).get("status", "not_assessed")
    pills = Table(
        [[_pill(sev, SEV_COLOR.get(sev, MUTED), st),
          _pill((incident.get("status") or "—").replace("_", " "), PRIMARY, st),
          _pill(rid.replace("_", " "), RIDDOR_COLOR.get(rid, MUTED), st)]],
        colWidths=[40 * mm, 50 * mm, 50 * mm],
    )
    pills.setStyle(TableStyle([("LEFTPADDING", (0,0), (-1,-1), 0)]))
    flow.append(pills)
    flow.append(Spacer(1, 8))
    flow.append(Paragraph("INCIDENT", st["section"]))
    flow.append(_kv_table([
        ("Reference", incident.get("reference")),
        ("Kind", (incident.get("kind") or "").replace("_", " ").title()),
        ("Category", (incident.get("category") or "").replace("_", " ").title()),
        ("Severity", sev.title()),
        ("Occurred", _date_str(incident.get("occurred_at"))),
        ("Reported", _date_str(incident.get("reported_at"))),
        ("Location", (incident.get("location") or {}).get("area") or "—"),
        ("Status", (incident.get("status") or "—").replace("_", " ").title()),
    ], st))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("DESCRIPTION", st["section"]))
    flow.append(Paragraph(_esc(incident.get("description", "")), st["body"]))
    if incident.get("immediate_action_taken"):
        flow.append(Paragraph("IMMEDIATE ACTION TAKEN", st["section"]))
        flow.append(Paragraph(_esc(incident["immediate_action_taken"]), st["body"]))
    ip = incident.get("injured_party") or {}
    if any(ip.get(k) for k in ("name", "role", "contact")):
        flow.append(Paragraph("INJURED PARTY", st["section"]))
        flow.append(_kv_table([
            ("Name", ip.get("name")),
            ("Role", (ip.get("role") or "").title()),
            ("Contact", ip.get("contact")),
            ("First aid given", "Yes" if incident.get("first_aid_given") else "No"),
            ("First aider", incident.get("first_aider_name")),
            ("Hospital treatment", "Yes" if incident.get("hospital_treatment") else "No"),
            ("Emergency services", "Yes" if incident.get("emergency_services_called") else "No"),
            ("Expected absence (days)", str(incident.get("work_absence_expected_days") or "—")),
        ], st))
    if incident.get("witnesses"):
        flow.append(Paragraph("WITNESSES", st["section"]))
        for w in incident["witnesses"]:
            flow.append(Paragraph(
                _esc(f"{w.get('name','')}{(' · ' + w.get('role')) if w.get('role') else ''}"
                     f"{(' · ' + w.get('contact')) if w.get('contact') else ''}"),
                st["value"]))
            if w.get("statement"):
                flow.append(Paragraph(_esc(w["statement"]), st["body"]))
    if actions:
        flow.append(Paragraph("CORRECTIVE ACTIONS", st["section"]))
        rows = [["Description", "Priority", "Status", "Due"]]
        for a in actions:
            rows.append([
                Paragraph(_esc(a.get("description", "")), st["value"]),
                (a.get("priority") or "—").title(),
                (a.get("status") or "—").replace("_", " ").title(),
                a.get("due_date").strftime("%-d %b %Y") if a.get("due_date") else "—",
            ])
        t = Table(rows, colWidths=[None, 22*mm, 26*mm, 26*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ]))
        flow.append(t)
    sigs = incident.get("signatures") or []
    if sigs:
        flow.append(Spacer(1, 10))
        flow.append(Paragraph("SIGNATURES", st["section"]))
        for s in sigs:
            for fl in _signature_block(s, st):
                flow.append(fl)
            flow.append(Spacer(1, 4))
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()


def witness_statement_pdf(incident: dict, witness: dict, org_name: str = "") -> bytes:
    buf = BytesIO()
    doc = _build_doc(buf, title=f"Witness Statement · {incident.get('reference','')}",
                     subtitle=f"{org_name or 'GymAxis'} · {witness.get('name','')}")
    st = _styles()
    flow: list = []
    flow.append(Paragraph("WITNESS", st["section"]))
    flow.append(_kv_table([
        ("Name", witness.get("name")),
        ("Role", witness.get("role")),
        ("Contact", witness.get("contact")),
        ("Statement date", _date_str(witness.get("statement_at"))),
    ], st))
    flow.append(Paragraph("INCIDENT", st["section"]))
    flow.append(_kv_table([
        ("Reference", incident.get("reference")),
        ("Occurred", _date_str(incident.get("occurred_at"))),
        ("Location", (incident.get("location") or {}).get("area") or "—"),
        ("Severity", (incident.get("severity") or "").title()),
    ], st))
    flow.append(Paragraph("STATEMENT", st["section"]))
    flow.append(Paragraph(_esc(witness.get("statement") or "—"), st["body"]))
    if witness.get("signature"):
        flow.append(Spacer(1, 12))
        flow.append(Paragraph("SIGNED", st["section"]))
        for fl in _signature_block(witness["signature"], st):
            flow.append(fl)
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()


def investigation_report_pdf(incident: dict, actions: list | None = None, org_name: str = "") -> bytes:
    buf = BytesIO()
    doc = _build_doc(buf, title=f"Investigation Report · {incident.get('reference','')}",
                     subtitle=f"{org_name or 'GymAxis'}")
    st = _styles()
    inv = incident.get("investigation") or {}
    flow: list = []
    flow.append(Paragraph("INVESTIGATION", st["section"]))
    flow.append(_kv_table([
        ("Investigator", inv.get("investigator_name")),
        ("Started", _date_str(inv.get("started_at"))),
        ("Completed", _date_str(inv.get("completed_at"))),
        ("Review at", _date_str(inv.get("review_at"))),
        ("Incident reference", incident.get("reference")),
        ("Severity", (incident.get("severity") or "").title()),
    ], st))
    flow.append(Paragraph("FINDINGS", st["section"]))
    flow.append(Paragraph(_esc(inv.get("findings") or "—"), st["body"]))
    if inv.get("root_causes"):
        flow.append(Paragraph("ROOT CAUSES", st["section"]))
        for rc in inv["root_causes"]:
            flow.append(Paragraph("• " + _esc(rc.replace("_", " ").title()), st["body"]))
    if actions:
        flow.append(Paragraph("CORRECTIVE ACTIONS", st["section"]))
        for a in actions:
            flow.append(Paragraph(
                _esc(f"[{(a.get('priority') or '—').title()}] {a.get('description','')}"
                     f" — {(a.get('status') or '—').replace('_', ' ').title()}"),
                st["body"]))
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()


def riddor_report_pdf(incident: dict, org_name: str = "") -> bytes:
    """F2508 cover sheet — captures the assessment + reasoning + audit
    so the manager has a defensible record alongside the HSE submission."""
    buf = BytesIO()
    rid = incident.get("riddor") or {}
    doc = _build_doc(buf,
                     title=f"RIDDOR Report · {incident.get('reference','')}",
                     subtitle=f"{rid.get('form') or 'F2508'} · {org_name or 'GymAxis'}")
    st = _styles()
    flow: list = []
    flow.append(_pill(rid.get("status", "not_assessed").replace("_", " "),
                      RIDDOR_COLOR.get(rid.get("status", "not_assessed"), MUTED), st))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("ASSESSMENT", st["section"]))
    flow.append(_kv_table([
        ("Form", rid.get("form") or "—"),
        ("Status", (rid.get("status") or "").replace("_", " ").title()),
        ("Statutory deadline", _date_str(rid.get("deadline_at"))),
        ("Assessed by", (rid.get("assessment") or {}).get("assessed_by_name")),
        ("Assessed at", _date_str((rid.get("assessment") or {}).get("assessed_at"))),
        ("HSE submission ref", rid.get("submission_ref")),
        ("Submitted at", _date_str(rid.get("submitted_at"))),
        ("Submitted by", rid.get("submitted_by")),
    ], st))
    reasons = (rid.get("assessment") or {}).get("reasons") or []
    if reasons:
        flow.append(Paragraph("REASONING", st["section"]))
        for r in reasons:
            flow.append(Paragraph("• " + _esc(r), st["body"]))
    flow.append(Paragraph("INCIDENT SUMMARY", st["section"]))
    flow.append(_kv_table([
        ("Reference", incident.get("reference")),
        ("Kind", (incident.get("kind") or "").replace("_", " ").title()),
        ("Severity", (incident.get("severity") or "").title()),
        ("Occurred", _date_str(incident.get("occurred_at"))),
        ("Location", (incident.get("location") or {}).get("area") or "—"),
    ], st))
    flow.append(Paragraph("DESCRIPTION", st["section"]))
    flow.append(Paragraph(_esc(incident.get("description", "")), st["body"]))
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()


def corrective_action_log_pdf(actions: list[dict], org_name: str = "", period_label: str = "All time") -> bytes:
    buf = BytesIO()
    doc = _build_doc(buf, title="Corrective Action Log", subtitle=f"{org_name} · {period_label}")
    st = _styles()
    flow: list = []
    rows = [["Ref", "Action", "Priority", "Status", "Due", "Assigned to"]]
    for a in actions:
        rows.append([
            a.get("incident_reference") or "—",
            Paragraph(_esc(a.get("description", "")), st["value"]),
            (a.get("priority") or "—").title(),
            (a.get("status") or "—").replace("_", " ").title(),
            a.get("due_date").strftime("%-d %b %Y") if a.get("due_date") else "—",
            a.get("assigned_to_name") or "—",
        ])
    t = Table(rows, colWidths=[20*mm, None, 22*mm, 26*mm, 22*mm, 36*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
    ]))
    flow.append(t)
    if not actions:
        flow.append(Paragraph("No corrective actions on file for this period.", st["small"]))
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()


def management_summary_pdf(stats: dict, org_name: str = "", period_label: str = "Last 30 days") -> bytes:
    """Period dashboard — what's been happening, what needs attention."""
    buf = BytesIO()
    doc = _build_doc(buf, title="H&S Management Summary",
                     subtitle=f"{org_name} · {period_label}")
    st = _styles()
    flow: list = []
    flow.append(Paragraph("HEADLINE", st["section"]))
    headline_rows = [[
        Paragraph("<b>Total incidents</b>", st["value"]),
        Paragraph(str(stats.get("total", 0)), st["value"]),
        Paragraph("<b>Confirmed RIDDOR</b>", st["value"]),
        Paragraph(str(stats.get("riddor_confirmed", 0)), st["value"]),
    ]]
    t = Table(headline_rows, colWidths=[40*mm, 22*mm, 50*mm, 22*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("ALIGN", (3, 0), (3, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(t)
    for title_, key in (("BY KIND", "by_kind"), ("BY SEVERITY", "by_severity"),
                       ("BY STATUS", "by_status"), ("BY CATEGORY", "by_category")):
        block = stats.get(key) or {}
        if not block:
            continue
        flow.append(Paragraph(title_, st["section"]))
        rows = [["", "Count"]]
        for k, v in sorted(block.items(), key=lambda x: -x[1]):
            rows.append([k.replace("_", " ").title(), str(v)])
        tt = Table(rows, colWidths=[None, 22*mm])
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        flow.append(tt)
    if stats.get("top_assets"):
        flow.append(Paragraph("EQUIPMENT WITH MOST INCIDENTS", st["section"]))
        rows = [["Asset", "Incidents"]]
        for r in stats["top_assets"]:
            rows.append([r.get("asset_name") or r.get("asset_id") or "—", str(r.get("count", 0))])
        tt = Table(rows, colWidths=[None, 26*mm])
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        flow.append(tt)
    doc.build(flow)
    buf.seek(0)
    return buf.getvalue()
