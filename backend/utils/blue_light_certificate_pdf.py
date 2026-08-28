"""Blue Light Service & Calibration Certificate PDF.

Rendered on the shared Pulse document shell (matches quotes / invoices /
handover packs) so branding is consistent. Carries a swappable per-contract
customer logo (e.g. a Fire & Rescue crest) and a treadmill calibration table
that flows naturally onto extra pages when a station has many treadmills.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_BORDER, PULSE_LIGHT, PULSE_MUTED,
    pulse_styles, pulse_header, make_pulse_doc,
)

TEMPLATE_VERSION = 1
_PASS = colors.HexColor("#16a34a")
_REVIEW = colors.HexColor("#d97706")
_FAIL = colors.HexColor("#dc2626")
_RESULT = {"pass": _PASS, "review": _REVIEW, "fail": _FAIL}


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fetch_logo_bytes(url):
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


def build_certificate_pdf(*, contract: dict, station: dict, visit: dict,
                          treadmills: list[dict], config: dict) -> bytes:
    """treadmills: [{serial_number, asset_name, speed:[{target,measured,result}],
    incline:[{target,measured,result}], overall}] using the FINAL measured values."""
    s = pulse_styles()
    buf = BytesIO()
    doc = make_pulse_doc(buf, "Service & Calibration Certificate")
    story = [pulse_header(s)]

    title = ParagraphStyle("cert_title", parent=s["title"], alignment=TA_CENTER, fontSize=22, leading=25)
    story.append(Spacer(1, 6 * mm))

    # Optional customer logo/crest (swappable per contract)
    logo_bytes = _fetch_logo_bytes((config or {}).get("customer_logo_url"))
    if logo_bytes:
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(BytesIO(logo_bytes))
            iw, ih = ir.getSize()
            h = 22 * mm
            w = h * (iw / ih) if ih else 30 * mm
            img = Image(BytesIO(logo_bytes), width=min(w, 60 * mm), height=h)
            img.hAlign = "CENTER"
            story += [img, Spacer(1, 4 * mm)]
        except Exception:
            pass

    story.append(Paragraph("CERTIFICATE OF SERVICE &amp; CALIBRATION", title))
    story.append(Spacer(1, 5 * mm))

    centre = ParagraphStyle("centre", parent=s["body"] if "body" in s else s["metalabel"],
                            alignment=TA_CENTER, fontSize=11, leading=16, textColor=PULSE_MUTED)
    station_style = ParagraphStyle("station", parent=centre, fontSize=15, leading=19,
                                   textColor=PULSE_NAVY, spaceBefore=2, spaceAfter=2)
    story.append(Paragraph("This is to certify that all Pulse Fitness equipment at", centre))
    story.append(Paragraph(f"<b>{_esc(station.get('site_name'))}</b>", station_style))
    story.append(Paragraph(
        "has been checked, serviced and calibrated to meet Pulse Fitness operational standards.", centre))
    story.append(Spacer(1, 6 * mm))

    # Certificate detail block
    def _row(label, value):
        return [Paragraph(_esc(label), s["metalabel"]),
                Paragraph(f"<b>{_esc(value)}</b>", s["metalabel"])]
    details = [
        _row("Customer", contract.get("company_name")),
        _row("Service Contract Number", contract.get("contract_number")),
        _row("Engineer", visit.get("engineer_name")),
        _row("Service & Calibration Date", (visit.get("completed_at") or "")[:10]),
        _row("Next Service Due", visit.get("next_service_due")),
    ]
    dt = Table(details, colWidths=[70 * mm, 104 * mm])
    dt.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(dt)
    story.append(Spacer(1, 8 * mm))

    # Treadmill calibration table (multi-page via repeatRows) — §26/§27
    speed_pts = (config or {}).get("speed_points_mph", [3, 6, 9, 12])
    incline_pts = (config or {}).get("incline_points_pct", [0, 5, 10, 15])
    story.append(Paragraph("Treadmill Calibration Results", s["sectlabel"]))
    story.append(Spacer(1, 2 * mm))
    if not treadmills:
        story.append(Paragraph(
            "No treadmills requiring calibration were recorded at this station.", centre))
    else:
        header = ["Serial Number"] + [f"{p} mph" for p in speed_pts] + [f"{p}%" for p in incline_pts]
        data = [header]
        cell_colors = []  # (row, col, color)
        for r_i, t in enumerate(treadmills, start=1):
            speed_map = {round(float(x["target"]), 3): x for x in (t.get("speed") or [])}
            incl_map = {round(float(x["target"]), 3): x for x in (t.get("incline") or [])}
            row = [_esc(t.get("serial_number") or t.get("asset_name") or "—")]
            for p in speed_pts:
                x = speed_map.get(round(float(p), 3), {})
                row.append(f"{x.get('measured', '—')}")
                cell_colors.append((r_i, len(row) - 1, _RESULT.get(x.get("result"))))
            for p in incline_pts:
                x = incl_map.get(round(float(p), 3), {})
                row.append(f"{x.get('measured', '—')}")
                cell_colors.append((r_i, len(row) - 1, _RESULT.get(x.get("result"))))
            data.append(row)
        ncols = len(header)
        first_w = 42 * mm
        rest_w = (174 * mm - first_w) / (ncols - 1)
        tbl = Table(data, colWidths=[first_w] + [rest_w] * (ncols - 1), repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for (ri, ci, col) in cell_colors:
            if col is not None:
                style.append(("TEXTCOLOR", (ci, ri), (ci, ri), col))
                style.append(("FONTNAME", (ci, ri), (ci, ri), "Helvetica-Bold"))
        tbl.setStyle(TableStyle(style))
        story.append(tbl)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"Speed measured in mph · Incline measured in %. Results within "
            f"{(config or {}).get('tolerance_pct', 5)}% of target are within Pulse Fitness "
            f"operational tolerance.", ParagraphStyle("note", parent=s["metalabel"], fontSize=7.5)))

    # Signatures
    story.append(Spacer(1, 12 * mm))
    sig_bytes = visit.get("_signature_image_bytes")
    eng_sig_cell = ""
    if sig_bytes:
        try:
            eng_sig_cell = Image(BytesIO(sig_bytes), width=45 * mm, height=16 * mm)
        except Exception:
            eng_sig_cell = ""
    sig_tbl = Table([
        [eng_sig_cell, ""],
        [Paragraph("_______________________________", s["metalabel"]),
         Paragraph("_______________________________", s["metalabel"])],
        [Paragraph(f"<b>{_esc(visit.get('engineer_name'))}</b><br/>Service Engineer, Pulse Fitness", s["metalabel"]),
         Paragraph("<b>Managing Director</b><br/>Pulse Fitness Ltd", s["metalabel"])],
    ], colWidths=[87 * mm, 87 * mm])
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    return buf.getvalue()


def certificate_filename(contract: dict, station: dict, service_date: str) -> str:
    import re
    def clean(x):
        return re.sub(r"[^A-Za-z0-9]+", "-", str(x or "")).strip("-")
    return (f"{clean(contract.get('company_name'))}_{clean(station.get('site_name'))}"
            f"_Service-and-Calibration_{(service_date or datetime.now().strftime('%Y-%m-%d'))[:10]}.pdf")
