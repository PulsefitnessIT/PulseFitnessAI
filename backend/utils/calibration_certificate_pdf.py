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
                                      machines=None, notes="", signature_data_url=None,
                                      customer_signoff=None) -> bytes:
    s = pulse_styles()
    buf = BytesIO()
    doc = make_pulse_doc(buf, f"Calibration Certificate — {case_ref}")
    story: list = [pulse_header(s), Spacer(1, 6 * mm)]

    story.append(Paragraph("Calibration Certificate", s["title"]))
    story.append(Spacer(1, 2 * mm))

    verdict = (overall_result or "").upper()
    vcol = colors.HexColor(_PASS_HEX if verdict == "PASS" else _FAIL_HEX)
    equip_meta = equipment_name or "—"
    if machines:
        equip_meta = f"{len(machines)} treadmill(s)"
    meta = [
        ["Case reference", case_ref or "—"],
        ["Customer", customer_name or "—"],
        ["Site", site_name or "—"],
        ["Equipment", equip_meta],
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

    if machines:
        _append_treadmill_matrix(story, s, machines)
    else:
        _append_flat_readings(story, s, readings)
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

    from utils.customer_signoff import signoff_flowables
    story.append(section_label(s, "Customer sign-off"))
    story.extend(signoff_flowables(customer_signoff, s))

    story.append(Paragraph(
        "This certificate records the calibration checks performed on the equipment "
        "listed above at the visit date and is provided as audit evidence. Readings "
        "were taken using calibrated reference instruments where applicable.", s["muted"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


# Speed / incline columns for the multi-treadmill certificate matrix — matches
# the customer's Certificate of Service (3/6/9/12 mph, 0/5/10/15%).
_MATRIX_COLS = [
    ("Speed — 3 mph", "3 mph"), ("Speed — 6 mph", "6 mph"),
    ("Speed — 9 mph", "9 mph"), ("Speed — 12 mph", "12 mph"),
    ("Incline — 0%", "0%"), ("Incline — 5%", "5%"),
    ("Incline — 10%", "10%"), ("Incline — 15%", "15%"),
]


def _append_treadmill_matrix(story, s, machines) -> None:
    story.append(section_label(s, "Treadmill calibration readings"))
    head = ["Serial / Asset"] + [c[1] for c in _MATRIX_COLS] + ["Result"]
    data = [[Paragraph(f"<b>{_esc(h)}</b>", s["th"]) for h in head]]
    for m in machines:
        by_label = {str(r.get("label") or ""): r for r in (m.get("readings") or [])}
        ident = m.get("serial") or m.get("equipment_name") or "—"
        row = [Paragraph(_esc(ident), s["cell"])]
        for label, _short in _MATRIX_COLS:
            r = by_label.get(label) or {}
            val = r.get("measured") or "—"
            res = (r.get("result") or "").upper()
            col = _FAIL_HEX if res == "FAIL" else "#1A1A1A"
            row.append(Paragraph(f'<font color="{col}">{_esc(val)}</font>', s["cell"]))
        mres = (m.get("overall_result") or "").upper()
        rc = _PASS_HEX if mres == "PASS" else (_FAIL_HEX if mres == "FAIL" else _NA_HEX)
        row.append(Paragraph(f'<font color="{rc}"><b>{_esc(mres or "—")}</b></font>', s["cell"]))
        data.append(row)
    col_w = [30 * mm] + [14 * mm] * len(_MATRIX_COLS) + [16 * mm]
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl)


def _append_flat_readings(story, s, readings) -> None:
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


__all__ = ["build_calibration_certificate_pdf"]
