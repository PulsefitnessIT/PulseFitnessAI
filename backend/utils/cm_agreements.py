"""Customer agreements — approved terms, frozen agreement documents, customer
e-signature evidence, automatic activation and the welcome pack.

Extends the existing crm2_afs_agreements lifecycle (no second status engine).
Every figure in the document comes from the stored agreement record.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db, get_object, put_object

log = logging.getLogger(__name__)
LINK_DAYS = 14
CONSENT_TEXT = ("I confirm I have read this Maintenance Agreement and the attached Terms & Conditions, that I am "
                "authorised to sign on behalf of the customer, and I agree to sign electronically.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


async def _put(path: str, data: bytes, ctype: str = "application/pdf") -> None:
    await asyncio.to_thread(put_object, path, data, ctype)


async def load_object(path: str) -> bytes:
    data, _ = await asyncio.to_thread(get_object, path)
    return data


# ── Approved terms & conditions ──────────────────────────────────────────

async def approved_terms(org_id: str) -> dict | None:
    return await db.crm2_afs_terms.find_one({"organization_id": org_id, "status": "approved"}, {"_id": 0},
                                            sort=[("approved_at", -1)])


async def store_terms(org_id: str, version: str, filename: str, data: bytes, actor: str) -> dict:
    tid = str(uuid.uuid4())
    path = f"pulse/afs-terms/{org_id}/{tid}.pdf"
    source = None
    if filename.lower().endswith(".docx"):
        source = {"filename": filename, "sha256": sha256(data), "storage_path": f"pulse/afs-terms/{org_id}/{tid}.docx"}
        await _put(source["storage_path"], data,
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        data = docx_terms_to_pdf(data, version)
    await _put(path, data)
    doc = {"id": tid, "organization_id": org_id, "version": version.strip(), "filename": filename,
           "storage_path": path, "sha256": sha256(data), "size": len(data), "status": "pending_approval",
           "source_document": source, "uploaded_by": actor, "uploaded_at": _now()}
    await db.crm2_afs_terms.insert_one(dict(doc))
    return doc


def docx_terms_to_pdf(data: bytes, version: str) -> bytes:
    """Faithful text rendering of the Word T&Cs with clause numbering
    (Level 1 → 1, Level 2 → 1.1, Level 3 → (a), Level 4 → (i)).
    An administrator reviews the rendered PDF before approving it."""
    import docx
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    from utils.pulse_doc_template import make_pulse_doc, pulse_styles
    roman = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"]
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    s = pulse_styles()
    buf = io.BytesIO()
    pdf = make_pulse_doc(buf, f"Maintenance Terms & Conditions {version}")
    n = [0, 0, 0, 0]
    flow = []
    for p in docx.Document(io.BytesIO(data)).paragraphs:
        text = p.text.strip()
        if not text:
            continue
        st = p.style.name or ""
        lvl = next((i for i in (1, 2, 3, 4) if st.startswith(f"Level {i}")), 0)
        if lvl:
            n[lvl - 1] += 1
            for j in range(lvl, 4):
                n[j] = 0
            label = {1: f"{n[0]}.", 2: f"{n[0]}.{n[1]}", 3: f"({chr(96 + min(n[2], 26))})",
                     4: f"({roman[min(n[3], 15) - 1]})"}[lvl]
            if lvl == 1:
                flow += [Spacer(1, 2 * mm), Paragraph(f"<b>{label} {esc(text)}</b>", s["value"])]
            else:
                flow.append(Paragraph(f"{'&nbsp;' * 4 * (lvl - 1)}{label} {esc(text)}", s["body"]))
        elif len(flow) < 2:
            flow.append(Paragraph(f"<b>{esc(text)}</b>", s["title" if not flow else "value"]))
        else:
            flow.append(Paragraph(esc(text), s["body"]))
    pdf.build(flow)
    return buf.getvalue()


async def approve_terms(org_id: str, terms_id: str, actor: str) -> dict | None:
    t = await db.crm2_afs_terms.find_one({"id": terms_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        return None
    await db.crm2_afs_terms.update_many({"organization_id": org_id, "status": "approved", "id": {"$ne": terms_id}},
                                        {"$set": {"status": "superseded", "superseded_at": _now()}})
    await db.crm2_afs_terms.update_one({"id": terms_id}, {"$set": {"status": "approved", "approved_by": actor,
                                                                   "approved_at": _now()}})
    from utils.cm_actions import resolve_action
    await resolve_action(org_id, "cm:terms-missing", f"Terms {t['version']} approved.")
    return {**t, "status": "approved", "approved_by": actor}


async def raise_terms_missing(org_id: str) -> None:
    from utils.cm_actions import raise_action
    await raise_action(org_id, "cm:terms-missing", type_="terms_missing",
                       subject="Upload and approve the maintenance Terms & Conditions",
                       body="Agreements cannot be sent for customer signature until an administrator uploads and "
                            "approves the current Pulse Fitness maintenance Terms & Conditions.")


# ── Agreement document ───────────────────────────────────────────────────

def _gbp(v) -> str:
    return f"£{float(v or 0):,.2f}"


def build_agreement_pdf(ag: dict, terms: dict | None, version: int, signature: dict | None = None) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from utils.pulse_doc_template import (PULSE_BORDER, PULSE_LIGHT, make_pulse_doc, pulse_header,
                                          pulse_styles, pulse_title, section_label)
    esc = lambda t: "" if t is None else str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    s = pulse_styles()
    buf = io.BytesIO()
    doc = make_pulse_doc(buf, ag.get("agreement_number") or "Maintenance Agreement")
    sc = ag.get("schedules") or {}
    p1, p2 = sc.get("schedule1_parties") or {}, sc.get("schedule2_agreement") or {}
    sup, cust = p1.get("supplier") or {}, p1.get("customer") or {}
    flow = [pulse_header(s)]
    flow += pulse_title(s, p2.get("agreement_type") or "Maintenance Agreement",
                        subtitle=f"Agreement {esc(ag.get('agreement_number'))} · document version {version}")

    def kv(rows):
        t = Table([[Paragraph(esc(k), s["label"]), Paragraph(esc(v), s["value"])] for k, v in rows],
                  colWidths=[48 * mm, 122 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    vat = ag.get("vat_pct")
    vat_txt = f"{float(vat) * 100:.0f}% VAT charged in addition" if vat not in (None, "") else "VAT treatment per invoice"
    pay = {"monthly": "Monthly by Direct Debit", "annual": "Annually in advance", "lump_sum": "Lump sum in advance",
           "quarterly": "Quarterly in advance"}.get(ag.get("billing_frequency"), ag.get("billing_frequency") or "—")
    flow += [section_label(s, "Schedule 1 — Parties"), kv([
        ("Supplier", f"{sup.get('name', '')}, {sup.get('address', '')}"),
        ("Supplier company no.", sup.get("company_number") or "—"),
        ("Customer (legal entity)", cust.get("legal_name")),
        ("Customer address", cust.get("billing_address") or cust.get("address") or "—"),
        ("Site(s)", "; ".join(", ".join(x for x in (st.get("name"), st.get("address"), st.get("postcode")) if x)
                              for st in p1.get("sites") or []) or "—"),
    ]), Spacer(1, 3 * mm), section_label(s, "Schedule 2 — Agreement & payment"), kv([
        ("Agreement reference", ag.get("agreement_number")),
        ("Package", (ag.get("contract_type") or "").title()),
        ("Start date", ag.get("start_date")), ("Expiry date", ag.get("end_date")),
        ("Term", f"{ag.get('term_years', 1)} year(s)"),
        ("Annual value (ex VAT)", _gbp(ag.get("annual_value"))), ("VAT", vat_txt),
        ("Billing & payment", pay),
        ("Included service visits", f"{ag.get('visits_per_year', 0)} planned preventative maintenance visit(s) per year"),
    ]), Spacer(1, 3 * mm), section_label(s, "Schedule 3 — Equipment covered")]
    rows = [[Paragraph("Qty", s["thR"]), Paragraph("Machine", s["th"]), Paragraph("Serial numbers", s["th"]),
             Paragraph("Annual", s["thR"])]]
    for r in sc.get("schedule3_equipment") or []:
        serials = ", ".join(r.get("serial_numbers") or []) or "To be confirmed at first service"
        rows.append([Paragraph(str(r.get("quantity", "")), s["cellR"]), Paragraph(esc(r.get("machine")), s["cell"]),
                     Paragraph(esc(serials), s["cell"]), Paragraph(_gbp(r.get("annual_total")), s["cellR"])])
    t = Table(rows, colWidths=[12 * mm, 55 * mm, 75 * mm, 28 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PULSE_LIGHT), ("LINEBELOW", (0, 0), (-1, -1), 0.3, PULSE_BORDER)]))
    flow += [t, Spacer(1, 3 * mm)]
    for title, items in (("Services included", p2.get("services_included")), ("Exclusions & cover conditions", p2.get("exclusions")),
                         ("Schedule 5 — Customer obligations", sc.get("schedule5_customer_obligations")),
                         ("Schedule 6 — Exceptions", sc.get("schedule6_exceptions"))):
        if items:
            flow.append(section_label(s, title))
            flow += [Paragraph("• " + esc(i if isinstance(i, str) else (i.get("text") or i.get("title") or i)), s["body"]) for i in items]
            flow.append(Spacer(1, 2 * mm))
    fr = sc.get("schedule4_fault_reporting") or {}
    flow += [section_label(s, "Schedule 4 — Requesting service"), kv([
        ("Service email", fr.get("service_email")), ("Service phone", fr.get("service_phone")),
        ("Customer portal", fr.get("portal_url")), ("Office hours", fr.get("office_hours"))]), Spacer(1, 3 * mm)]
    if terms:
        flow += [section_label(s, "Terms & Conditions"), Paragraph(
            f"This agreement incorporates the Pulse Fitness Maintenance Terms &amp; Conditions version "
            f"<b>{esc(terms['version'])}</b> (SHA-256 {terms['sha256'][:16]}…), attached in full after this page.", s["body"])]
    if signature:
        flow += [Spacer(1, 4 * mm), section_label(s, "Electronic signature certificate"), kv([
            ("Signed by", signature.get("signatory_name")), ("Position", signature.get("position") or "—"),
            ("Email", signature.get("email")), ("Signed (UTC)", signature.get("signed_at")),
            ("Method", "Typed name and drawn signature via secure Pulse Fitness link"),
            ("Authority confirmed", "Yes"), ("Document version / SHA-256", f"v{version} · {signature.get('document_hash')}"),
            ("Consent", CONSENT_TEXT)])]
        img = signature.get("signature_data_url") or ""
        if img.startswith("data:image/png;base64,"):
            try:
                from reportlab.platypus import Image
                flow.append(Image(io.BytesIO(base64.b64decode(img.split(",", 1)[1])), width=60 * mm, height=22 * mm))
            except Exception:
                log.warning("signature image could not be embedded", exc_info=True)
    doc.build(flow)
    return buf.getvalue()


async def compose_pdf(ag: dict, terms: dict | None, version: int, signature: dict | None = None) -> bytes:
    body = build_agreement_pdf(ag, terms, version, signature)
    if not terms:
        return body
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for src in (body, await load_object(terms["storage_path"])):
        for page in PdfReader(io.BytesIO(src)).pages:
            w.add_page(page)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


async def freeze_document(org_id: str, ag: dict, terms: dict) -> dict:
    """Render + store the exact document the customer will sign."""
    version = int((ag.get("document") or {}).get("version") or 0) + 1
    pdf = await compose_pdf(ag, terms, version)
    path = f"pulse/afs-agreements/{org_id}/{ag['id']}/v{version}.pdf"
    await _put(path, pdf)
    return {"version": version, "sha256": sha256(pdf), "storage_path": path, "terms_id": terms["id"],
            "terms_version": terms["version"], "frozen_at": _now(), "size": len(pdf)}


# ── Customer signature request ───────────────────────────────────────────

def new_link(document: dict, email: str, name: str) -> tuple[str, dict]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    return token, {"token_hash": token_hash(token), "issued_at": now.isoformat(),
                   "expires_at": (now + timedelta(days=LINK_DAYS)).isoformat(), "revoked": False,
                   "document_version": document["version"], "document_hash": document["sha256"],
                   "email": email, "name": name, "delivery_status": "pending", "events": []}


def link_state(req: dict | None) -> str:
    if not req:
        return "none"
    if req.get("revoked"):
        return "revoked"
    if req.get("expires_at", "") < _now():
        return "expired"
    return "active"


async def deliver_signature_email(org_id: str, ag: dict, req: dict, url: str) -> dict:
    from utils.email import send_email
    html = (f"<p>Dear {req.get('name') or 'customer'},</p>"
            f"<p>Thank you for choosing Pulse Fitness. Your maintenance agreement <b>{ag.get('agreement_number')}</b> "
            f"for {ag.get('company_name')} is ready for review and electronic signature.</p>"
            f"<p><a href=\"{url}\">Review and sign your agreement</a></p>"
            f"<p>The secure link is personal to this agreement and expires in {LINK_DAYS} days. "
            f"You can download a full copy of the agreement before signing.</p><p>Pulse Fitness Aftersales</p>")
    out: dict = {}
    ok = await send_email(req["email"], f"Your Pulse Fitness maintenance agreement {ag.get('agreement_number')}",
                          html, organization_id=org_id, kind="afs_agreement_signature", result_out=out)
    return {"delivery_status": "accepted_by_provider" if ok else "failed", "message_id": out.get("message_id"),
            "attempted_at": _now()}


# ── Automatic activation + welcome pack ──────────────────────────────────

def auto_activation_blockers(ag: dict) -> list[str]:
    from routes.crm_aftersales import _agreement_health
    out = list(_agreement_health(ag)["reasons"])
    sig, docu = ag.get("signature") or {}, ag.get("document") or {}
    if sig.get("method") != "customer_esignature":
        out.append("Signature was not submitted by the customer")
    elif sig.get("document_hash") != docu.get("sha256"):
        out.append("Signed document version differs from the current agreement document")
    return out


async def try_auto_activate(org_id: str, agreement_id: str) -> dict:
    from fastapi import HTTPException
    from routes.crm_aftersales import ActivateIn, activate_agreement
    from utils.cm_actions import raise_action
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, "organization_id": org_id}, {"_id": 0})
    settings = await db.crm2_afs_settings.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    if settings.get("auto_activate_on_signature") is False:
        return {"activated": False, "reason": "policy_manual"}
    blockers = auto_activation_blockers(ag)
    if blockers:
        await raise_action(org_id, f"cm:agreement-activate:{agreement_id}", type_="agreement_step",
                           subject=f"Activate contract (review needed): {ag.get('agreement_number')}",
                           body=f"{ag.get('company_name')} — signed, but automatic activation stopped: {'; '.join(blockers[:4])}.",
                           contract={"id": agreement_id, "company_id": ag.get("company_id"),
                                     "contract_number": ag.get("agreement_number")},
                           extra={"agreement_id": agreement_id})
        return {"activated": False, "blockers": blockers}
    system = {"id": "system:auto-activation", "email": "auto-activation", "organization_id": org_id,
              "crm_permissions": ["agreements.process"]}
    try:
        res = await activate_agreement(agreement_id, ActivateIn(), user=system)
        return {"activated": True, **res}
    except HTTPException as e:
        return {"activated": False, "error": e.detail}


def _welcome_html(ag: dict, contract: dict, contacts: dict) -> str:
    sites = ", ".join(s.get("name", "") for s in (ag.get("schedules") or {}).get("schedule1_parties", {}).get("sites") or [])
    portal = f"<li>Customer portal: <a href=\"{contacts['portal_url']}\">{contacts['portal_url']}</a></li>" if contacts.get("portal_url") else ""
    return (f"<p>Thank you for selecting Pulse Fitness.</p>"
            f"<p>Your maintenance agreement is now active. Here is a summary for your records:</p><ul>"
            f"<li>Customer: {ag.get('company_name')}</li><li>Site(s): {sites or '—'}</li>"
            f"<li>Agreement reference: {contract.get('contract_number')}</li>"
            f"<li>Start date: {ag.get('start_date')} · Expiry date: {ag.get('end_date')}</li>"
            f"<li>Package: {(ag.get('contract_type') or '').title()}</li>"
            f"<li>Included maintenance visits: {ag.get('visits_per_year')} per year</li></ul>"
            f"<p><b>Requesting service support</b></p><ul>"
            f"<li>Email: {contacts.get('service_email')}</li><li>Phone: {contacts.get('service_phone')}</li>"
            f"<li>Office hours: {contacts.get('office_hours')}</li>{portal}</ul>"
            f"<p><b>What happens next</b><br/>Our service team will contact you to arrange your first planned "
            f"maintenance visit. Your signed agreement is attached.</p><p>Pulse Fitness Aftersales</p>")


async def send_welcome_pack(org_id: str, contract_id: str, *, actor: str, reissue: bool = False) -> dict:
    """Send once per contract + document version; reissue only when asked."""
    from routes.crm_aftersales import _service_contacts
    from utils.cm_actions import raise_action, resolve_action
    from utils.email import send_email
    c = await db.crm2_contracts.find_one({"id": contract_id, "organization_id": org_id}, {"_id": 0})
    if not c or c.get("status") != "active":
        return {"status": "skipped", "detail": "Contract is not active"}
    ag = await db.crm2_afs_agreements.find_one({"id": c.get("source_agreement_id"), "organization_id": org_id}, {"_id": 0}) or {}
    version = (ag.get("document") or {}).get("version") or 0
    key = f"{contract_id}:v{version}"
    retry_ok = {"failed", "queued"} | ({"accepted_by_provider"} if reissue else set())
    claim = await db.crm2_contracts.find_one_and_update(
        {"id": contract_id, "organization_id": org_id, "$or": [
            {"welcome_pack": {"$exists": False}}, {"welcome_pack.key": {"$ne": key}},
            {"welcome_pack.status": {"$in": list(retry_ok)}}]},
        {"$set": {"welcome_pack.status": "sending", "welcome_pack.key": key, "welcome_pack.updated_at": _now()}})
    if not claim:
        prev = {k: v for k, v in (c.get("welcome_pack") or {}).items() if k != "history"}
        return {**prev, "status": "duplicate_prevented", "previous_status": prev.get("status")}
    sig = ag.get("signature") or {}
    to = sig.get("email")
    if not to:
        co = await db.crm2_companies.find_one({"id": c.get("company_id")}, {"_id": 0, "email": 1}) or {}
        to = co.get("email")
    settings = await db.crm2_afs_settings.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    contacts = _service_contacts(settings)
    attach, path = None, (ag.get("signed_document") or ag.get("document") or {}).get("storage_path")
    try:
        pdf = await load_object(path) if path else build_agreement_pdf(ag, None, version)
        attach = [{"filename": f"{c.get('contract_number')}.pdf", "content": base64.b64encode(pdf).decode("ascii")}]
    except Exception:
        log.warning("welcome pack attachment unavailable for %s", contract_id, exc_info=True)
    out: dict = {}
    ok = bool(to) and await send_email(to, f"Welcome to Pulse Fitness maintenance — {c.get('contract_number')}",
                                       _welcome_html(ag, c, contacts), attachments=attach, organization_id=org_id,
                                       kind="afs_welcome_pack", result_out=out)
    status = "accepted_by_provider" if ok else "failed"
    detail = None if ok else ("No customer email on record" if not to else "Email provider did not accept the message")
    prev = (c.get("welcome_pack") or {}).get("history") or []
    wp = {"status": status, "key": key, "to": to, "message_id": out.get("message_id"), "detail": detail,
          "attachment": bool(attach), "updated_at": _now(), "sent_at": _now() if ok else None,
          "history": prev + [{"at": _now(), "status": status, "by": actor, "reissue": reissue}]}
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"welcome_pack": wp}})
    if ok:
        await resolve_action(org_id, f"cm:welcome-failed:{contract_id}", "Welcome pack accepted by the email provider.")
    else:
        await raise_action(org_id, f"cm:welcome-failed:{contract_id}", type_="welcome_pack_failed",
                           subject=f"Welcome pack not delivered: {c.get('contract_number')}",
                           body=f"{c.get('company_name')} — {detail}. Check the customer email and resend from the agreement.",
                           contract=c)
    return {k: v for k, v in wp.items() if k != "history"}
