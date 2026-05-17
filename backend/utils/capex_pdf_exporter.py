"""Board-ready CAPEX PDF (Iter 216h127).

Generates a multi-page A4 portrait PDF intended for board / DIO /
finance review. Self-contained — receives the full board-report
payload from ``routes/capex.py::get_capex_board_report`` and renders
to bytes via reportlab.

Brand is tenant-aware via the existing ``branding`` dict shape used by
``utils.tender_pdf_exporter`` — accepts ``{company_name, primary_color,
logo_url}``. Defaults to Pulse Fitness branding because CAPEX is a
Pulse Fitness Pro feature.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

PULSE_PRIMARY = colors.HexColor("#19CDFF")
PULSE_BLACK = colors.HexColor("#0F172A")
PULSE_MUTED = colors.HexColor("#64748B")
PULSE_LIGHT = colors.HexColor("#F1F5F9")
PULSE_DANGER = colors.HexColor("#DC2626")
PULSE_WARN = colors.HexColor("#F59E0B")
PULSE_OK = colors.HexColor("#22C55E")

STATUS_COLOR = {
    "replace_now": PULSE_DANGER,
    "replace_soon": colors.HexColor("#EA580C"),
    "at_risk": PULSE_WARN,
    "monitor": colors.HexColor("#CA8A04"),
    "healthy": PULSE_OK,
}
SAFETY_COLOR = {
    "high": PULSE_DANGER, "elevated": colors.HexColor("#EA580C"),
    "moderate": PULSE_WARN, "low": PULSE_OK,
}


def _esc(text: str) -> str:
    if text is None:
        return ""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _styles(brand: dict) -> dict:
    primary = colors.HexColor(brand.get("primary_color") or "#19CDFF")
    base = getSampleStyleSheet()
    return {
        "primary": primary,
        "company": (brand or {}).get("company_name") or "Pulse Fitness",
        "cover_title": ParagraphStyle("cover_title", parent=base["Title"], fontSize=34, leading=40,
                                      textColor=PULSE_BLACK, alignment=TA_LEFT, spaceAfter=8),
        "cover_sub": ParagraphStyle("cover_sub", parent=base["Normal"], fontSize=13, leading=18,
                                    textColor=primary, alignment=TA_LEFT, spaceAfter=20),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, leading=26,
                             textColor=primary, alignment=TA_LEFT, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, leading=18,
                             textColor=PULSE_BLACK, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14,
                               textColor=PULSE_BLACK, alignment=TA_LEFT, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=10, leading=14,
                                 textColor=PULSE_BLACK, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "muted": ParagraphStyle("muted", parent=base["Normal"], fontSize=9, leading=12,
                                textColor=PULSE_MUTED, spaceAfter=4),
        "kpi_label": ParagraphStyle("kpi_label", parent=base["Normal"], fontSize=8, leading=10,
                                    textColor=PULSE_MUTED, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("kpi_value", parent=base["Normal"], fontSize=18, leading=22,
                                    textColor=PULSE_BLACK, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    }


def _footer_factory(brand_name: str):
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(PULSE_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(20 * mm, 12 * mm, f"{brand_name} — Board CAPEX Report · CONFIDENTIAL")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(PULSE_LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
        canvas.restoreState()
    return _footer


def _kpi_row(s, items: list[tuple[str, str]]) -> Table:
    col_count = max(1, len(items))
    col_w = 170 / col_count * mm
    inner_cells = []
    for label, value in items:
        inner = Table(
            [[Paragraph(_esc(value), s["kpi_value"])],
             [Paragraph(_esc(label), s["kpi_label"])]],
            colWidths=[col_w],
        )
        inner.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        inner_cells.append(inner)
    table = Table([inner_cells], colWidths=[col_w] * col_count)
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, PULSE_LIGHT),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def _distribution_table(s, title: str, dist: dict, color: colors.Color | None = None) -> Table:
    rows = [["", title]]
    rows[0] = [Paragraph(f"<b>{_esc(title)}</b>", s["body"]), Paragraph("Count", s["body"])]
    body = [
        [Paragraph(_esc(str(k)), s["body"]), Paragraph(str(v), s["body"])]
        for k, v in dist.items()
    ]
    table = Table(rows + body, colWidths=[60 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color or PULSE_LIGHT),
        ("LINEBELOW", (0, 0), (-1, 0), 1, PULSE_MUTED),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _equipment_table(s, equipment: list[dict], limit: int = 25) -> Table:
    header = ["Machine", "Type", "Location", "Status", "Score", "Replacement"]
    data = [header]
    for r in equipment[:limit]:
        capex = r.get("capex") or {}
        status_label = (capex.get("status") or "").replace("_", " ").title()
        data.append([
            Paragraph(_esc(r.get("name", "")), s["body"]),
            Paragraph(_esc(r.get("equipment_type", "")), s["body"]),
            Paragraph(_esc(r.get("location") or "-"), s["body"]),
            Paragraph(_esc(status_label), s["body"]),
            Paragraph(str(capex.get("score", 0)), s["body"]),
            Paragraph(f"£{capex.get('replacement_cost', 0):,}", s["body"]),
        ])
    t = Table(data, colWidths=[42 * mm, 27 * mm, 30 * mm, 25 * mm, 16 * mm, 30 * mm],
              repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), s["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, PULSE_LIGHT),
    ]
    # Per-row status colour
    for i, r in enumerate(equipment[:limit], start=1):
        status = (r.get("capex") or {}).get("status", "monitor")
        c = STATUS_COLOR.get(status, PULSE_MUTED)
        style.append(("TEXTCOLOR", (3, i), (3, i), c))
        style.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def _recommendations_table(s, items: list[dict]) -> Table:
    header = ["Machine", "Action", "Urgency", "Why"]
    data = [header]
    for r in items[:20]:
        rec = r.get("recommendation") or {}
        reasons = rec.get("reasons") or []
        data.append([
            Paragraph(_esc(r.get("name", "")), s["body"]),
            Paragraph(_esc(rec.get("action", "—")), s["body"]),
            Paragraph(_esc((rec.get("urgency") or "").title()), s["body"]),
            Paragraph(_esc("; ".join(reasons[:2])), s["body"]),
        ])
    t = Table(data, colWidths=[40 * mm, 45 * mm, 25 * mm, 60 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), s["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, PULSE_LIGHT),
    ]
    t.setStyle(TableStyle(style))
    return t


def _service_signals_section(s, equipment: list[dict]) -> list:
    """Iter 216h160 — Live Service Spend & BER summary.

    Aggregates the per-asset `service_signals` block (added in iter
    216h154) into a fleet-level rollup + a top-10 BER offenders
    table. Renders nothing when no asset has service_signals (e.g.
    cold-start orgs) so the rest of the report degrades gracefully.
    """
    flow: list = []
    with_signals = [
        e for e in (equipment or [])
        if isinstance(e.get("service_signals"), dict)
    ]
    if not with_signals:
        return flow

    total_visits = 0
    total_spend = 0.0
    total_downtime = 0.0
    open_cases = 0
    replace = watch = keep = 0
    for e in with_signals:
        sig = e["service_signals"]
        total_visits += int(sig.get("service_visits_12mo") or 0)
        total_spend += float(sig.get("service_spend_12mo") or 0)
        total_downtime += float(sig.get("downtime_hours_12mo") or 0)
        open_cases += int(sig.get("open_service_cases") or 0)
        rec = sig.get("ber_recommendation")
        if rec == "replace":
            replace += 1
        elif rec == "watch":
            watch += 1
        elif rec == "keep":
            keep += 1

    flow.append(Paragraph("5. Live Service Spend &amp; Repair-vs-Replace", s["h1"]))
    flow.append(Paragraph(
        "Twelve-month engineer service spend and the BER (Beyond "
        "Economic Repair) ratio for every asset. Replace = spend ≥ "
        "50% of replacement cost; Watch = 25–50%; Keep = below 25%. "
        "Sourced from the live Engineer App job + invoice history.",
        s["muted"],
    ))
    flow.append(Spacer(1, 3 * mm))
    flow.append(_kpi_row(s, [
        ("Service visits", str(total_visits)),
        ("Spend (12m)", f"£{total_spend:,.0f}"),
        ("Open cases", str(open_cases)),
        ("Downtime (hrs)", f"{total_downtime:,.0f}"),
    ]))
    flow.append(Spacer(1, 3 * mm))
    flow.append(_kpi_row(s, [
        ("BER Replace", str(replace)),
        ("BER Watch",   str(watch)),
        ("BER Keep",    str(keep)),
        ("Avg spend / asset", f"£{(total_spend / max(len(with_signals), 1)):,.0f}"),
    ]))
    flow.append(Spacer(1, 4 * mm))

    # Top 10 BER offenders by ratio (only those above keep threshold).
    flagged = []
    for e in with_signals:
        sig = e["service_signals"]
        ratio = sig.get("service_to_replacement_ratio")
        if ratio is None or ratio < 0.25:
            continue
        flagged.append({
            "name": e.get("name") or "(unnamed)",
            "location": e.get("location") or "—",
            "type": e.get("equipment_type") or "—",
            "spend": sig.get("service_spend_12mo") or 0.0,
            "replacement_cost": (e.get("capex") or {}).get("replacement_cost") or 0,
            "ratio": ratio,
            "rec": sig.get("ber_recommendation") or "—",
        })
    flagged.sort(key=lambda r: r["ratio"], reverse=True)
    flagged = flagged[:10]

    if flagged:
        rows = [[
            Paragraph("<b>Asset</b>", s["body"]),
            Paragraph("<b>Location</b>", s["body"]),
            Paragraph("<b>12m spend</b>", s["body"]),
            Paragraph("<b>Replacement</b>", s["body"]),
            Paragraph("<b>BER %</b>", s["body"]),
            Paragraph("<b>Action</b>", s["body"]),
        ]]
        for r in flagged:
            rows.append([
                Paragraph(_esc(r["name"]), s["body"]),
                Paragraph(_esc(r["location"]), s["body"]),
                f"£{r['spend']:,.0f}",
                f"£{r['replacement_cost']:,.0f}",
                f"{int(r['ratio'] * 100)}%",
                r["rec"].title(),
            ])
        tbl = Table(rows, colWidths=[50 * mm, 35 * mm, 22 * mm,
                                       25 * mm, 18 * mm, 20 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PULSE_LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
            ("LINEBELOW", (0, 0), (-1, 0), 1, PULSE_MUTED),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        flow.append(Paragraph("<b>Top BER offenders (12-month basis)</b>", s["body"]))
        flow.append(Spacer(1, 2 * mm))
        flow.append(tbl)
    else:
        flow.append(Paragraph(
            "No asset has crossed the 25% BER watch threshold in the "
            "last 12 months. Fleet is economic to repair.", s["muted"]))
    flow.append(Spacer(1, 6 * mm))
    return flow


def build_capex_board_pdf(report: dict, brand: dict | None = None) -> bytes:
    """Render the full Board CAPEX PDF and return raw bytes.

    Expects the payload shape produced by ``GET /capex/board-report``.
    """
    s = _styles(brand or {})
    brand_name = s["company"]
    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"{brand_name} — Board CAPEX Report",
        author=brand_name,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="normal", showBoundary=0)
    doc.addPageTemplates([
        PageTemplate(id="default", frames=[frame], onPage=_footer_factory(brand_name))
    ])

    flow = []
    now = datetime.utcnow().strftime("%d %B %Y")

    # ─── Cover ───────────────────────────────────────────────
    flow.append(Spacer(1, 18 * mm))
    flow.append(Paragraph(f"<b>{_esc(brand_name)}</b>", s["body"]))
    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph("Board CAPEX Report", s["cover_title"]))
    flow.append(Paragraph("Equipment Replacement Strategy &amp; Investment Decision",
                          s["cover_sub"]))
    flow.append(Spacer(1, 8 * mm))

    summary = report.get("summary") or {}
    forecast = report.get("forecast") or {}
    fleet_kpis = (report.get("fleet_intelligence") or {}).get("fleet_kpis", {})
    flow.append(_kpi_row(s, [
        ("Assets", str(summary.get("total", 0))),
        ("Flagged", str((summary.get("replace_now", 0) + summary.get("replace_soon", 0)
                         + summary.get("at_risk", 0)))),
        ("12m £", f"£{forecast.get('next_12_months', 0):,}"),
        ("Availability", f"{fleet_kpis.get('fleet_availability_pct') or '—'}%"),
    ]))
    flow.append(Spacer(1, 14 * mm))
    flow.append(Paragraph(f"<b>Generated:</b> {now}", s["muted"]))
    flow.append(Paragraph(f"<b>Scope:</b> {_esc(report.get('scope_label', 'Full estate'))}",
                          s["muted"]))
    flow.append(Paragraph("This report contains commercially sensitive equipment data. "
                          "Distribute internally only.", s["muted"]))
    flow.append(PageBreak())

    # ─── 1. Executive Summary ───────────────────────────────
    exec_block = report.get("executive_summary") or {}
    flow.append(Paragraph("1. Executive Summary", s["h1"]))
    flow.append(Paragraph(_esc(exec_block.get("headline", "")), s["body"]))
    flow.append(Spacer(1, 4 * mm))
    for b in exec_block.get("bullets") or []:
        flow.append(Paragraph(f"• {_esc(b)}", s["bullet"]))
    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph(f"<b>Recommended Action:</b> {_esc(exec_block.get('recommended_action', ''))}",
                          s["body"]))
    flow.append(Spacer(1, 6 * mm))

    # ─── 2. Fleet KPIs ──────────────────────────────────────
    flow.append(Paragraph("2. Fleet Intelligence — Headline KPIs", s["h1"]))
    flow.append(_kpi_row(s, [
        ("Immediate Action", str(fleet_kpis.get("immediate_action_assets", 0))),
        ("BER Assets", str(fleet_kpis.get("beyond_economic_repair_count", 0))),
        ("Days OOS", str(fleet_kpis.get("total_days_oos", 0))),
        ("Avg Age (yr)", str(fleet_kpis.get("average_age_years") or "—")),
    ]))
    flow.append(Spacer(1, 4 * mm))
    flow.append(_kpi_row(s, [
        ("Avg Condition", f"{(report.get('fleet_intelligence') or {}).get('condition_average') or '—'}/5"),
        ("Lifetime Saving", f"£{fleet_kpis.get('estimated_lifetime_saving', 0):,.0f}"),
        ("Replacement (full fleet)", f"£{fleet_kpis.get('total_replacement_cost_full_fleet', 0):,}"),
        ("Downtime (hrs)", str(fleet_kpis.get("total_downtime_hours", 0))),
    ]))
    flow.append(Spacer(1, 8 * mm))

    # ─── 3. Distributions ───────────────────────────────────
    fi = report.get("fleet_intelligence") or {}
    flow.append(Paragraph("3. Lifecycle &amp; Condition Distribution", s["h1"]))
    dist_row = Table([[
        _distribution_table(s, "Lifecycle Stage", fi.get("lifecycle_distribution", {})),
        _distribution_table(s, "Condition Score (1-5)", fi.get("condition_distribution", {})),
    ]], colWidths=[90 * mm, 80 * mm])
    dist_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(dist_row)
    flow.append(Spacer(1, 8 * mm))

    flow.append(Paragraph("4. Safety Risk &amp; BER Status", s["h1"]))
    dist_row2 = Table([[
        _distribution_table(s, "Safety Risk", fi.get("safety_distribution", {})),
        _distribution_table(s, "Beyond Economic Repair", fi.get("ber_distribution", {})),
    ]], colWidths=[90 * mm, 80 * mm])
    dist_row2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(dist_row2)
    flow.append(PageBreak())

    # ─── 5. Live Service Spend & BER (iter 216h160) ─────────
    flow.extend(_service_signals_section(s, report.get("equipment") or []))

    # ─── 6. CAPEX Forecast ──────────────────────────────────
    flow.append(Paragraph("6. CAPEX Spend Forecast", s["h1"]))
    forecast_table = Table(
        [
            [Paragraph("<b>Window</b>", s["body"]), Paragraph("<b>£</b>", s["body"])],
            ["Next 3 months",  f"£{forecast.get('next_3_months', 0):,}"],
            ["Next 6 months",  f"£{forecast.get('next_6_months', 0):,}"],
            ["Next 12 months", f"£{forecast.get('next_12_months', 0):,}"],
        ],
        colWidths=[60 * mm, 30 * mm],
    )
    forecast_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("LINEBELOW", (0, 0), (-1, 0), 1, PULSE_MUTED),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    flow.append(forecast_table)
    flow.append(Spacer(1, 6 * mm))

    by_priority = report.get("by_priority") or {}
    flow.append(Paragraph(
        f"<b>Priority breakdown:</b> Immediate £{by_priority.get('immediate', 0):,} · "
        f"Short term £{by_priority.get('short_term', 0):,} · "
        f"Medium term £{by_priority.get('medium_term', 0):,}",
        s["body"],
    ))
    flow.append(Spacer(1, 6 * mm))

    # ─── 7. Recommendations ─────────────────────────────────
    flow.append(Paragraph("7. Replacement Recommendations (Top 20)", s["h1"]))
    flagged = [
        e for e in (report.get("equipment") or [])
        if (e.get("capex") or {}).get("status") in ("replace_now", "replace_soon", "at_risk")
    ]
    if flagged:
        flow.append(_recommendations_table(s, flagged))
    else:
        flow.append(Paragraph("No assets flagged for replacement.", s["muted"]))
    flow.append(PageBreak())

    # ─── 8. Asset Register ──────────────────────────────────
    flow.append(Paragraph("8. Asset Register — Detailed", s["h1"]))
    flow.append(Paragraph(
        f"Top {min(25, len(report.get('equipment') or []))} assets by CAPEX urgency. "
        "Full register available in the platform.", s["muted"]))
    flow.append(Spacer(1, 3 * mm))
    flow.append(_equipment_table(s, report.get("equipment") or [], limit=25))
    flow.append(Spacer(1, 8 * mm))

    # ─── 9. Sign-off footer ────────────────────────────────
    flow.append(Paragraph("9. Sign-off", s["h1"]))
    sign_table = Table(
        [
            [Paragraph("<b>Prepared by</b>", s["body"]), Paragraph(_esc(report.get("prepared_by", brand_name)), s["body"])],
            [Paragraph("<b>Approved by</b>", s["body"]), ""],
            [Paragraph("<b>Date</b>", s["body"]), Paragraph(now, s["body"])],
        ],
        colWidths=[40 * mm, 130 * mm],
    )
    sign_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, PULSE_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    flow.append(sign_table)

    doc.build(flow)
    return buf.getvalue()


__all__ = ["build_capex_board_pdf"]
