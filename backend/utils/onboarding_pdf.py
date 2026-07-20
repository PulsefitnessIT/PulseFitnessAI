"""Branded PDF generation for Staff Onboarding offer letters & employment
contracts, built on the shared Pulse document shell (utils.pulse_doc_template).

Renders the already-merged ``rendered`` body plus an e-signature certificate
block (signer, method, timestamp, IP, document hash) so the downloaded PDF is a
faithful, tamper-evident record of what was signed.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utils.pulse_doc_template import (
    PULSE_NAVY, PULSE_BORDER, PULSE_LIGHT, pulse_styles, pulse_header,
    make_pulse_doc, pulse_title, section_label,
)


def _body_flow(styles: dict, text: str) -> list:
    """Turn the plain-text rendered body into platypus flowables, preserving
    blank-line spacing and simple bullet / numbered lines."""
    esc = styles["esc"]
    flow: list = []
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flow.append(Spacer(1, 4))
            continue
        stripped = line.strip()
        # A short ALL-CAPS heading line → section label
        if stripped == stripped.upper() and 3 < len(stripped) < 80 and any(ch.isalpha() for ch in stripped):
            flow.append(Spacer(1, 3))
            flow.append(section_label(styles, stripped))
            continue
        indent = len(line) - len(line.lstrip(" "))
        style = styles["body"]
        if indent >= 2:
            style = styles["value"]
        flow.append(Paragraph(esc(line).replace("  ", "&nbsp;&nbsp;"), style))
    return flow


def _cert_block(styles: dict, title: str, signatures: list) -> list:
    """Render the electronic-signature certificate table."""
    if not signatures:
        return []
    esc = styles["esc"]
    rows = [[Paragraph("Signatory", styles["th"]), Paragraph("Role", styles["th"]),
             Paragraph("Method", styles["th"]), Paragraph("Signed (UTC)", styles["th"]),
             Paragraph("IP address", styles["th"])]]
    for s in signatures:
        rows.append([
            Paragraph(esc(s.get("signer_name") or s.get("name")), styles["cell"]),
            Paragraph(esc(s.get("signer_role") or s.get("party") or "—"), styles["cell"]),
            Paragraph(esc(s.get("method") or "typed"), styles["cell"]),
            Paragraph(esc((s.get("signed_at") or "")[:19].replace("T", " ")), styles["cell"]),
            Paragraph(esc(s.get("ip") or "—"), styles["cell"]),
        ])
    tbl = Table(rows, colWidths=[42 * mm, 32 * mm, 24 * mm, 40 * mm, 36 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PULSE_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PULSE_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    out = [Spacer(1, 10), section_label(styles, title), tbl]
    doc_hash = None
    for s in signatures:
        doc_hash = s.get("document_hash") or doc_hash
    if doc_hash:
        out.append(Spacer(1, 3))
        out.append(Paragraph(f"Document integrity hash (SHA-256): {esc(doc_hash)}", styles["muted"]))
    return out


def _render_doc(title: str, subtitle: str, body_text: str,
                sig_title: str, signatures: list, status_note: str | None) -> bytes:
    buf = BytesIO()
    doc = make_pulse_doc(buf, title)
    styles = pulse_styles()
    story = [pulse_header(styles), Spacer(1, 8)]
    story += pulse_title(styles, title, subtitle)
    if status_note:
        story.append(Spacer(1, 2))
        story.append(Paragraph(status_note, styles["muted"]))
    story.append(Spacer(1, 10))
    story += _body_flow(styles, body_text)
    story += _cert_block(styles, sig_title, signatures)
    doc.build(story)
    return buf.getvalue()


def build_offer_pdf(case: dict, staff: dict, offer: dict) -> bytes:
    name = staff.get("full_name") or "Recruit"
    status = (offer.get("status") or "draft").replace("_", " ").title()
    sigs = []
    acc = (offer.get("acceptance") or {}).get("signature")
    if acc:
        sigs.append(acc)
    note = f"Status: {status}"
    if offer.get("issued_at"):
        note += f"  ·  Issued: {offer['issued_at'][:10]}"
    return _render_doc(
        "Offer of Employment", f"{name} — {(case.get('employment_proposal') or {}).get('job_title', '')}".strip(" —"),
        offer.get("rendered", ""), "Electronic acceptance certificate", sigs, note)


def build_contract_pdf(case: dict, staff: dict, contract: dict) -> bytes:
    name = staff.get("full_name") or "Employee"
    status = (contract.get("status") or "draft").replace("_", " ").title()
    sigs = list(contract.get("signatures") or [])
    note = f"Status: {status}"
    if contract.get("issued_at"):
        note += f"  ·  Issued: {contract['issued_at'][:10]}"
    if contract.get("fully_signed_at"):
        note += f"  ·  Fully signed: {contract['fully_signed_at'][:10]}"
    return _render_doc(
        "Contract of Employment", f"{name} — {(case.get('employment_proposal') or {}).get('job_title', '')}".strip(" —"),
        contract.get("rendered", ""), "Electronic signature certificate", sigs, note)
