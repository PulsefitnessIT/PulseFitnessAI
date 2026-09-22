"""Branded PDF renderer for Aftersales maintenance quotes (crm2_afs_quotes).

Deterministic: every figure comes straight off the stored quote (grouped_lines +
summary). No prices are invented here — this only formats the authorised quote.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from utils.pulse_doc_template import (
    PULSE_BORDER, PULSE_LIGHT, PULSE_NAVY, make_pulse_doc, pulse_header,
    pulse_styles, pulse_title, section_label,
)


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _gbp(v) -> str:
    return f"£{float(v or 0):,.2f}"


def build_afs_quote_pdf(quote: dict, org: dict | None = None,
                        company: dict | None = None, coverage: dict | None = None,
                        site_annexe: list | None = None) -> bytes:
    s = pulse_styles()
    buf = io.BytesIO()
    doc = make_pulse_doc(buf, quote.get("quote_number") or "Maintenance Quote", company=company)
    flow = [pulse_header(s, company)]

    summary = quote.get("summary", {}) or {}
    tier = (quote.get("contract_type") or "gold").title()
    flow += pulse_title(s, "Maintenance Agreement Quotation",
                        subtitle=f"{tier} package · prepared by Pulse Fitness Aftersales")

    # Meta block (quote number / date / valid until / package)
    meta_rows = [
        ("Quote number", quote.get("quote_number") or "—"),
        ("Date", datetime.now().strftime("%d %b %Y")),
        ("Package", f"{tier} Maintenance"),
        ("Term", f"{summary.get('term_years', 1)} year(s)"),
    ]
    if quote.get("valid_until"):
        meta_rows.append(("Valid until", quote["valid_until"][:10]))
    meta = Table([[Paragraph(k, s["metalabel"]), Paragraph(_esc(v), s["metaval"])] for k, v in meta_rows],
                 colWidths=[35 * mm, 40 * mm], hAlign="RIGHT")
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    flow.append(meta)
    flow.append(Spacer(1, 4 * mm))

    # Customer
    flow.append(section_label(s, "Prepared for"))
    flow.append(Paragraph(f"<b>{_esc(quote.get('company_name') or 'Customer')}</b>", s["value"]))
    flow.append(Spacer(1, 4 * mm))

    # Equipment table (grouped lines)
    flow.append(section_label(s, "Equipment covered"))
    data = [[Paragraph("Qty", s["thR"]), Paragraph("Machine", s["th"]),
             Paragraph("Annual (each)", s["thR"]), Paragraph("Annual total", s["thR"])]]
    grouped = quote.get("grouped_lines") or []
    if not grouped:
        data.append([Paragraph("", s["cellR"]), Paragraph("No priced equipment on this quote.", s["cell"]),
                     Paragraph("", s["cellR"]), Paragraph("", s["cellR"])])
    for g in grouped:
        label = g.get("model") or g.get("type") or "—"
        if g.get("console_type"):
            label += f" · {g['console_type']}"
        annual_unit = g.get("annual_unit")
        if annual_unit is None:
            annual_unit = g.get("unit_price")
        annual_total = g.get("annual_total")
        if annual_total is None:
            annual_total = g.get("line_total")
        data.append([
            Paragraph(f"{int(g.get('qty', 0))}", s["cellR"]),
            Paragraph(_esc(label), s["cell"]),
            Paragraph(_gbp(annual_unit), s["cellR"]),
            Paragraph(_gbp(annual_total), s["cellR"]),
        ])
    t = Table(data, colWidths=[14 * mm, 92 * mm, 30 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 5 * mm))

    # Travel & visits (tender quotes charge travel per site, per visit)
    travel_lines = quote.get("travel_lines") or []
    if travel_lines:
        flow.append(section_label(s, "Travel & visits"))
        tdata = [[Paragraph("Site", s["th"]), Paragraph("Per visit", s["thR"]),
                  Paragraph("Visits/yr", s["thR"]), Paragraph("Annual", s["thR"])]]
        for tl in travel_lines:
            per_visit = tl.get("per_visit")
            if per_visit is None:
                per_visit = tl.get("price")
            visits = int(tl.get("visits") or 1)
            annual = tl.get("annual")
            if annual is None:
                annual = tl.get("price")
            tdata.append([
                Paragraph(_esc(tl.get("site_name") or tl.get("location") or "—"), s["cell"]),
                Paragraph(_gbp(per_visit), s["cellR"]),
                Paragraph(f"{visits}", s["cellR"]),
                Paragraph(_gbp(annual), s["cellR"]),
            ])
        tt = Table(tdata, colWidths=[92 * mm, 30 * mm, 22 * mm, 22 * mm], repeatRows=1)
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, PULSE_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        flow.append(tt)
        flow.append(Spacer(1, 5 * mm))

    # Totals (with defensive VAT / monthly fallbacks for older custom quotes)
    disc = summary.get("quote_discount_pct", 0) or 0
    final_annual = float(summary.get("final_annual") or 0)
    vat_pct = summary.get("vat_pct")
    if vat_pct is None:
        vat_pct = 0.20
    vat_amount = summary.get("vat_amount")
    if vat_amount is None:
        vat_amount = round(final_annual * float(vat_pct), 2)
    inc_vat = summary.get("final_annual_inc_vat")
    if inc_vat is None:
        inc_vat = round(final_annual + vat_amount, 2)
    monthly = summary.get("monthly")
    if monthly is None:
        monthly = round(final_annual / 12.0, 2)
    total_rows = []
    # Itemised charge breakdown for tender quotes (service / travel / repairs)
    if summary.get("service_annual") is not None or travel_lines:
        total_rows.append([Paragraph("Service (annual)", s["total_label"]),
                           Paragraph(_gbp(summary.get("service_annual")), s["total_value"])])
        if summary.get("travel_total"):
            total_rows.append([Paragraph("Travel &amp; visits (annual)", s["total_label"]),
                               Paragraph(_gbp(summary.get("travel_total")), s["total_value"])])
        if summary.get("repair_cost"):
            eh = summary.get("estimated_repair_hours") or 0
            total_rows.append([Paragraph(f"Repairs (est. {eh:g}h)", s["total_label"]),
                               Paragraph(_gbp(summary.get("repair_cost")), s["total_value"])])
    total_rows += [
        [Paragraph("Annual value", s["total_label"]), Paragraph(_gbp(final_annual), s["total_value"])],
        [Paragraph("Monthly (Direct Debit)", s["total_label"]), Paragraph(_gbp(monthly), s["total_value"])],
        [Paragraph(f"Term total ({summary.get('term_years', 1)} yr)", s["total_label"]),
         Paragraph(_gbp(summary.get("term_total")), s["total_value"])],
        [Paragraph(f"VAT ({float(vat_pct or 0) * 100:g}%)", s["total_label"]),
         Paragraph(_gbp(vat_amount), s["total_value"])],
        [Paragraph("Annual inc VAT", s["total_label"]), Paragraph(_gbp(inc_vat), s["grand_value"])],
    ]
    if disc:
        total_rows.insert(1, [Paragraph(f"Discount ({disc:g}%)", s["total_label"]),
                              Paragraph(f"applied", s["total_value"])])
    totals = Table(total_rows, colWidths=[45 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("BACKGROUND", (0, -1), (-1, -1), PULSE_LIGHT),
    ]))
    flow.append(totals)
    flow.append(Spacer(1, 6 * mm))

    # Coverage summary (from package — deterministic)
    cov = coverage or {}
    tail = []
    if cov.get("maintenance") or cov.get("technical_support"):
        tail.append(section_label(s, "What's included"))
        for item in (cov.get("maintenance") or [])[:8]:
            tail.append(Paragraph(f"• {_esc(item)}", s["body"]))
        for item in (cov.get("technical_support") or [])[:6]:
            tail.append(Paragraph(f"• {_esc(item)}", s["body"]))
    if cov.get("exclusions"):
        tail.append(Spacer(1, 2 * mm))
        tail.append(section_label(s, "Exclusions"))
        for item in (cov.get("exclusions") or [])[:6]:
            tail.append(Paragraph(f"• {_esc(item)}", s["muted"]))
    tail.append(Spacer(1, 4 * mm))
    tail.append(Paragraph(
        "<i>Figures are calculated from Pulse Fitness's authorised maintenance pricing rules. "
        "This quotation is subject to the standard Maintenance Agreement terms &amp; conditions.</i>", s["muted"]))
    flow.append(KeepTogether(tail))

    # Optional appendix: equipment listed per site (for large estates)
    if site_annexe:
        from reportlab.platypus import PageBreak
        flow.append(PageBreak())
        total_assets = sum(a.get("asset_count", 0) for a in site_annexe)
        flow += pulse_title(s, "Appendix A — Equipment by site")
        flow.append(Paragraph(
            f"{len(site_annexe)} site(s) · {total_assets} asset(s). Units marked "
            f"<i>(not covered)</i> are excluded from this agreement.", s["muted"]))
        flow.append(Spacer(1, 4 * mm))
        for a in site_annexe:
            block = []
            head = a["site_name"]
            if a.get("asset_count"):
                head += f"  ({a['asset_count']} asset{'s' if a['asset_count'] != 1 else ''})"
            block.append(section_label(s, head))
            if a.get("address"):
                block.append(Paragraph(_esc(a["address"]), s["muted"]))
            rows = [[Paragraph("Qty", s["thR"]), Paragraph("Equipment", s["th"]),
                     Paragraph("Serial(s)", s["th"])]]
            for it in a["items"]:
                label = it["label"] + ("" if it.get("covered", True) else "  (not covered)")
                serials = ", ".join(it.get("serials") or []) or "—"
                rows.append([
                    Paragraph(f"{int(it['qty'])}", s["cellR"]),
                    Paragraph(_esc(label), s["cell"]),
                    Paragraph(_esc(serials), s["cell"]),
                ])
            at = Table(rows, colWidths=[14 * mm, 78 * mm, 74 * mm], repeatRows=1)
            at.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, PULSE_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            block.append(at)
            block.append(Spacer(1, 4 * mm))
            flow.append(KeepTogether(block))

    doc.build(flow)
    return buf.getvalue()


async def render_afs_quote_pdf(quote: dict, organization_id: str | None = None) -> bytes:
    org: dict = {}
    company = None
    coverage = None
    site_annexe = None
    try:
        from utils.database import db as _db
        if organization_id:
            org = await _db.organizations.find_one({"id": organization_id}, {"_id": 0}) or {}
            try:
                from utils.document_branding import resolve_company_if_configured
                company = await resolve_company_if_configured(
                    _db, {"id": organization_id, "name": org.get("name")})
            except Exception:
                company = None
            pkg = await _db.crm2_afs_packages.find_one(
                {"organization_id": organization_id, "key": (quote.get("contract_type") or "gold").lower()},
                {"_id": 0})
            if pkg:
                coverage = {"maintenance": pkg.get("maintenance", []),
                            "technical_support": pkg.get("technical_support", []),
                            "exclusions": pkg.get("exclusions", [])}
        # Optional per-site equipment appendix (for large estates)
        if quote.get("include_site_annexe") and quote.get("linked_organization_id"):
            site_annexe = await _build_site_annexe(_db, quote)
    except Exception:
        pass
    return build_afs_quote_pdf(quote, org, company=company, coverage=coverage, site_annexe=site_annexe)


async def _build_site_annexe(_db, quote: dict) -> list:
    """Group the quoted estate's equipment by site for a customer-facing appendix.
    Identical model/console units at a site are collapsed into a quantity."""
    linked = quote.get("linked_organization_id")
    site_ids = quote.get("site_ids") or []
    excluded = set(quote.get("excluded_asset_ids") or [])
    eq_query = {"organization_id": linked}
    if site_ids:
        eq_query["site_id"] = {"$in": site_ids}
    equipment = await _db.equipment.find(
        eq_query, {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
                   "serial_number": 1, "site_id": 1}).to_list(20000)
    sites = await _db.sites.find(
        {"organization_id": linked, **({"id": {"$in": site_ids}} if site_ids else {})},
        {"_id": 0, "id": 1, "name": 1, "address": 1, "postcode": 1}).to_list(5000)
    site_name = {s["id"]: s for s in sites}
    by_site = {}
    for e in equipment:
        sid = e.get("site_id") or "__unassigned__"
        label = e.get("model") or e.get("model_code") or e.get("name") or "Equipment"
        if e.get("console_type"):
            label += f" · {e['console_type']}"
        covered = e.get("id") not in excluded
        bucket = by_site.setdefault(sid, {})
        key = (label, covered)
        row = bucket.setdefault(key, {"label": label, "covered": covered, "qty": 0, "serials": []})
        row["qty"] += 1
        if e.get("serial_number"):
            row["serials"].append(str(e["serial_number"]))
    annexe = []
    for sid, rows in by_site.items():
        meta = site_name.get(sid, {})
        addr = ", ".join(x for x in [meta.get("address"), meta.get("postcode")] if x)
        items = sorted(rows.values(), key=lambda r: r["label"].lower())
        annexe.append({
            "site_name": meta.get("name") or ("Unassigned" if sid == "__unassigned__" else "Site"),
            "address": addr,
            "asset_count": sum(r["qty"] for r in items),
            "items": items,
        })
    annexe.sort(key=lambda a: a["site_name"].lower())
    return annexe
