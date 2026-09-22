"""Equipment (treadmill) Calibration Certificate PDF — audit evidence.

Follows the shared Pulse document shell used by warranty_certificate_pdf.py:
a branded certificate listing each calibration reading with target / measured
/ tolerance and a pass/fail verdict, the overall result, engineer sign-off and
issue date. Retained by the customer as proof of calibration for audits.
"""
from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_BORDER, PULSE_LIGHT, PULSE_MUTED,
    pulse_styles, pulse_header, make_pulse_doc, section_label,
)

_PASS_HEX = "#0F9D58"
_FAIL_HEX = "#D93025"
_NA_HEX = "#6B7280"


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_calibration_certificate_pdf(*, case_ref, customer_name, site_name,
                                      service_type, readings, overall_result,
                                      engineer_name, issued_at, equipment_name="",
                                      notes="", signature_data_url=None) -> bytes:
    s = pulse_styles()
    buf = BytesIO()
    doc = make_pulse_doc(buf, f"Calibration Certificate — {case_ref}")
    story: list = [pulse_header(s), Spacer(1, 6 * mm)]

    story.append(Paragraph("Calibration Certificate", s["title"]))
    story.append(Spacer(1, 2 * mm))

    verdict = (overall_result or "").upper()
    vcol = colors.HexColor(_PASS_HEX if verdict == "PASS" else _FAIL_HEX)
    meta = [
        ["Case reference", case_ref or "—"],
        ["Customer", customer_name or "—"],
        ["Site", site_name or "—"],
        ["Equipment", equipment_name or "—"],
        ["Service", service_type or "Calibration"],
        ["Engineer", engineer_name or "—"],
        ["Issued on", issued_at or datetime.now().strftime("%d %B %Y %H:%M")],
    ]
    mt = Table(meta, colWidths=[38 * mm, 120 * mm])
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
    story.append(Spacer(1, 4 * mm))

    vb = Table([[Paragraph(f'<b>OVERALL RESULT: {verdict or "—"}</b>', s["th"])]], colWidths=[158 * mm])
    vb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), vcol),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(vb)
    story.append(Spacer(1, 5 * mm))

    story.append(section_label(s, "Calibration readings"))
    head = ["Parameter", "Target", "Measured", "Tolerance", "Result"]
    data = [[Paragraph(f"<b>{_esc(h)}</b>", s["th"]) for h in head]]
    for r in (readings or []):
        res = (r.get("result") or "").upper()
        rc = _PASS_HEX if res == "PASS" else (_FAIL_HEX if res == "FAIL" else _NA_HEX)
        unit = r.get("unit") or ""
        meas = r.get("measured") or "—"
        if unit and meas != "—":
            meas = f"{meas} {unit}"
        data.append([
            Paragraph(_esc(r.get("label")), s["cell"]),
            Paragraph(_esc(r.get("target") or "—"), s["cell"]),
            Paragraph(_esc(meas), s["cell"]),
            Paragraph(_esc(r.get("tolerance") or "—"), s["cell"]),
            Paragraph(f'<font color="{rc}"><b>{_esc(res or "—")}</b></font>', s["cell"]),
        ])
    tbl = Table(data, colWidths=[62 * mm, 26 * mm, 26 * mm, 26 * mm, 18 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 5 * mm))

    if notes:
        story.append(section_label(s, "Engineer notes"))
        story.append(Paragraph(_esc(notes), s["muted"]))
        story.append(Spacer(1, 4 * mm))

    if signature_data_url and "," in str(signature_data_url):
        try:
            raw = base64.b64decode(str(signature_data_url).split(",", 1)[1])
            img = Image(BytesIO(raw), width=50 * mm, height=20 * mm)
            story.append(section_label(s, "Engineer signature"))
            story.append(img)
            story.append(Spacer(1, 3 * mm))
        except Exception:
            pass

    story.append(Paragraph(
        "This certificate records the calibration checks performed on the equipment "
        "listed above at the visit date and is provided as audit evidence. Readings "
        "were taken using calibrated reference instruments where applicable.", s["muted"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


__all__ = ["build_calibration_certificate_pdf"]
