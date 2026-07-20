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


# ───────────────────────── completed forms + full onboarding pack ─────────────────────────
FORM_FIELD_LABELS = {
    "home_address": "Home address", "dob": "Date of birth",
    "ni_number": "National Insurance number", "emergency_contact_name": "Emergency contact name",
    "emergency_contact_phone": "Emergency contact phone", "bank_account": "Bank account",
    "sort_code": "Sort code", "account_number": "Account number",
}


def _kv_table(styles: dict, rows: list, col1_mm: float = 55) -> Table:
    esc = styles["esc"]
    data = [[Paragraph(esc(k), styles["metalabel"]), Paragraph(esc("" if v is None else str(v)), styles["value"])]
            for k, v in rows]
    if not data:
        data = [[Paragraph("—", styles["muted"]), Paragraph("", styles["value"])]]
    tbl = Table(data, colWidths=[col1_mm * mm, (174 - col1_mm) * mm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, PULSE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _forms_sections(styles: dict, forms: dict) -> list:
    """Render the New Starter form data as titled key/value tables."""
    ns = (forms.get("new_starter") or {}).get("data") or {}
    flow: list = []
    personal = [(FORM_FIELD_LABELS.get(k, k.replace("_", " ").title()), ns.get(k))
                for k in ("home_address", "dob", "ni_number") if ns.get(k)]
    emergency = [(FORM_FIELD_LABELS.get(k, k.replace("_", " ").title()), ns.get(k))
                 for k in ("emergency_contact_name", "emergency_contact_phone") if ns.get(k)]
    payroll = [(FORM_FIELD_LABELS.get(k, k.replace("_", " ").title()), ns.get(k))
               for k in ("bank_account", "sort_code", "account_number") if ns.get(k)]
    # any extra fields not covered above
    known = {"home_address", "dob", "ni_number", "emergency_contact_name",
             "emergency_contact_phone", "bank_account", "sort_code", "account_number"}
    extra = [(k.replace("_", " ").title(), v) for k, v in ns.items() if k not in known and v]
    for title, rows in [("Personal details", personal), ("Emergency contact", emergency),
                        ("Payroll & bank details", payroll), ("Additional information", extra)]:
        if rows:
            flow.append(Spacer(1, 6))
            flow.append(section_label(styles, title))
            flow.append(_kv_table(styles, rows))
    if not flow:
        flow.append(Paragraph("No form data has been submitted yet.", styles["muted"]))
    return flow


def build_forms_pdf(case: dict, staff: dict, forms: dict) -> bytes:
    buf = BytesIO()
    doc = make_pulse_doc(buf, "New Starter Form")
    styles = pulse_styles()
    name = staff.get("full_name") or "Recruit"
    story = [pulse_header(styles), Spacer(1, 8)]
    story += pulse_title(styles, "Completed New Starter Form", name)
    story += _forms_sections(styles, forms)
    doc.build(story)
    return buf.getvalue()


def _status_table(styles: dict, title: str, rows: list) -> list:
    if not rows:
        return []
    return [Spacer(1, 6), section_label(styles, title), _kv_table(styles, rows)]


def build_pack_pdf(case: dict, staff: dict, data: dict) -> bytes:
    """Audit-ready Onboarding Pack: cover + employment summary + completed forms +
    ID / RTW / DBS + policy acknowledgements + signed agreements + offer + contract."""
    buf = BytesIO()
    doc = make_pulse_doc(buf, "Onboarding Pack")
    styles = pulse_styles()
    esc = styles["esc"]
    name = staff.get("full_name") or "Recruit"
    ep = case.get("employment_proposal") or {}
    forms = data.get("forms") or {}
    docs = data.get("documents") or []
    acks = data.get("policy_acknowledgements") or []
    agreements = data.get("agreements") or []
    rtw = data.get("right_to_work") or {}
    dbs = data.get("dbs") or {}
    offer = case.get("offer") or {}
    contract = case.get("contract") or {}

    story = [pulse_header(styles), Spacer(1, 8)]
    story += pulse_title(styles, "Employee Onboarding Pack", name)
    story.append(Paragraph(f"Case status: {esc((case.get('status') or '').replace('_', ' ').title())}"
                           f"  ·  Generated: {esc((case.get('updated_at') or '')[:10])}", styles["muted"]))

    # Employment summary
    story += _status_table(styles, "Employment summary", [
        ("Job title", ep.get("job_title") or ep.get("position")),
        ("Company / site", f"{ep.get('employing_company') or '—'} · {ep.get('site') or '—'}"),
        ("Line manager", ep.get("line_manager")),
        ("Start date", ep.get("proposed_start_date")),
        ("Salary", ep.get("salary")), ("Employment type", ep.get("employment_type")),
    ])

    # Completed forms
    story.append(Spacer(1, 6))
    story.append(section_label(styles, "Completed new starter form"))
    story += _forms_sections(styles, forms)[1:] if _forms_sections(styles, forms) else []

    # Identity documents
    if docs:
        story += _status_table(styles, "Identity & evidence documents",
                               [(d.get("document_type", "document").replace("_", " ").title(),
                                 f"{d.get('original_filename', '—')} ({(d.get('verification_status') or 'pending')})")
                                for d in docs])

    # RTW / DBS
    rtw_rows = []
    if rtw:
        rtw_rows = [("Method", rtw.get("check_method")), ("Result", rtw.get("result")),
                    ("Share code", rtw.get("share_code")), ("Expiry", rtw.get("expiry")),
                    ("Checked by", rtw.get("checker")), ("Provider", rtw.get("provider") or "manual")]
    story += _status_table(styles, "Right to Work", [(k, v) for k, v in rtw_rows if v])
    dbs_rows = []
    if dbs:
        dbs_rows = [("Level", dbs.get("level")), ("Status", dbs.get("status")),
                    ("Certificate no.", dbs.get("certificate_number")), ("Issue date", dbs.get("issue_date")),
                    ("Checked by", dbs.get("checker")), ("Provider", dbs.get("provider") or "manual")]
    story += _status_table(styles, "DBS (Disclosure & Barring)", [(k, v) for k, v in dbs_rows if v])

    # Policy acknowledgements
    if acks:
        story += _status_table(styles, "Policy acknowledgements",
                               [(a.get("policy_key", "policy").replace("_", " ").title(),
                                 f"Acknowledged {(a.get('acknowledged_at') or '')[:10]} by {a.get('signature_name') or name}")
                                for a in acks])
    # Signed agreements
    signed_agr = [a for a in agreements if a.get("status") == "signed"]
    if signed_agr:
        story += _status_table(styles, "Signed agreements",
                               [(a.get("agreement_key", "agreement").replace("_", " ").title(),
                                 f"Signed {(a.get('signed_at') or '')[:10]}")
                                for a in signed_agr])

    # Offer letter (full)
    if offer.get("rendered"):
        story.append(Spacer(1, 8))
        story.append(section_label(styles, "Offer letter"))
        story += _body_flow(styles, offer["rendered"])
        acc = (offer.get("acceptance") or {}).get("signature")
        story += _cert_block(styles, "Offer acceptance certificate", [acc] if acc else [])

    # Contract (full)
    if contract.get("rendered"):
        story.append(Spacer(1, 8))
        story.append(section_label(styles, "Contract of employment"))
        story += _body_flow(styles, contract["rendered"])
        story += _cert_block(styles, "Contract signature certificate", list(contract.get("signatures") or []))

    doc.build(story)
    return buf.getvalue()
