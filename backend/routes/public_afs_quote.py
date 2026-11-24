"""Public (no-login) Aftersales maintenance-quote acceptance.

Commercial customers click a link → land on /aq/:shortcode in the React app,
review the maintenance quote + PDF, then accept (with signature) or decline.
Acceptance auto-prepares a DRAFT agreement for the coordinator (feeds straight
into agreement prep). MOD keeps its existing SOR portal flow — not this one.

Single-use: once accepted/declined, future POSTs return 410.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils.database import db

router = APIRouter(prefix="/public/afs", tags=["Public · Aftersales Quote"])

MAX_SIGNATURE_LEN = 250_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(q: dict) -> bool:
    vu = q.get("valid_until")
    if not vu:
        return False
    try:
        return datetime.fromisoformat(vu.replace("Z", "+00:00")) < datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        return False


def _public_view(q: dict) -> dict:
    summary = q.get("summary", {}) or {}
    return {
        "quote_number": q.get("quote_number"),
        "company_name": q.get("company_name"),
        "contract_type": q.get("contract_type"),
        "term_years": summary.get("term_years", q.get("term_years", 1)),
        "grouped_lines": [
            {k: g.get(k) for k in ("model", "console_type", "description", "qty",
                                    "annual_unit", "annual_total")}
            for g in (q.get("grouped_lines") or [])
        ],
        "summary": {k: summary.get(k) for k in (
            "final_annual", "monthly", "term_total", "term_years",
            "vat_pct", "vat_amount", "final_annual_inc_vat", "quote_discount_pct")},
        "valid_until": q.get("valid_until"),
        "expired": _is_expired(q),
        "portal_status": q.get("portal_status"),
        "accepted_at": q.get("accepted_at"),
        "accepted_by_name": q.get("accepted_by_name"),
        "declined_at": q.get("declined_at"),
    }


async def _find(shortcode: str) -> dict:
    q = await db.crm2_afs_quotes.find_one({"public_shortcode": shortcode}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Quote not found or no longer available")
    return q


class AcceptBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    signature_data_url: str | None = Field(default=None, max_length=MAX_SIGNATURE_LEN)
    note: str | None = Field(default=None, max_length=500)


class DeclineBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


@router.get("/quote/{shortcode}")
async def get_public_afs_quote(shortcode: str):
    return _public_view(await _find(shortcode))


@router.get("/quote/{shortcode}/pdf")
async def public_afs_quote_pdf(shortcode: str):
    q = await _find(shortcode)
    from utils.afs_quote_pdf import render_afs_quote_pdf
    pdf = await render_afs_quote_pdf(q, organization_id=q.get("organization_id"))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{q.get("quote_number", "quote")}.pdf"'})


@router.post("/quote/{shortcode}/accept")
async def accept_public_afs_quote(shortcode: str, body: AcceptBody):
    q = await _find(shortcode)
    if q.get("portal_status") == "accepted":
        raise HTTPException(410, "This quote has already been accepted.")
    if q.get("portal_status") == "declined":
        raise HTTPException(410, "This quote has already been declined.")
    if _is_expired(q):
        raise HTTPException(410, "This quote has expired. Please contact Pulse Fitness for a fresh quote.")
    set_payload = {
        "portal_status": "accepted", "status": "accepted", "accepted_at": _now(),
        "accepted_by_name": body.name.strip(),
        "accepted_by_note": (body.note or "").strip(),
        "accepted_via": "public_link", "updated_at": _now(),
    }
    if body.signature_data_url:
        set_payload["customer_signature_data_url"] = body.signature_data_url
    await db.crm2_afs_quotes.update_one({"id": q["id"]}, {"$set": set_payload})

    # Feed straight into agreement prep — auto-create a DRAFT agreement.
    agreement_number = None
    try:
        from routes.crm_aftersales import _insert_agreement_from_quote
        q2 = await db.crm2_afs_quotes.find_one({"id": q["id"]}, {"_id": 0})
        ag = await _insert_agreement_from_quote(
            q["organization_id"], q2, f"portal:{body.name.strip()}",
            timeline_note=f"Customer {body.name.strip()} accepted quote {q.get('quote_number')} via portal")
        agreement_number = ag.get("agreement_number")
    except Exception:
        agreement_number = None
    return {"ok": True, "quote_number": q.get("quote_number"), "agreement_number": agreement_number}


@router.post("/quote/{shortcode}/decline")
async def decline_public_afs_quote(shortcode: str, body: DeclineBody):
    q = await _find(shortcode)
    if q.get("portal_status") == "accepted":
        raise HTTPException(410, "This quote has already been accepted.")
    if q.get("portal_status") == "declined":
        raise HTTPException(410, "This quote has already been declined.")
    await db.crm2_afs_quotes.update_one({"id": q["id"]}, {"$set": {
        "portal_status": "declined", "declined_at": _now(),
        "declined_by_name": body.name.strip(),
        "declined_reason": (body.reason or "").strip(),
        "declined_via": "public_link", "updated_at": _now()}})
    return {"ok": True, "quote_number": q.get("quote_number")}


__all__ = ["router"]


# ── Customer agreement review + e-signature (link from the coordinator) ──

class AgreementSignBody(BaseModel):
    signatory_name: str = Field(..., min_length=2, max_length=120)
    position: str = Field("", max_length=120)
    email: str = Field(..., min_length=5, max_length=200)
    authority_confirmed: bool = False
    consent_confirmed: bool = False
    signature_data_url: str = Field(..., min_length=50, max_length=400_000)
    document_hash: str = Field(..., min_length=64, max_length=64)


class AgreementDeclineBody(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    reason: str | None = Field(None, max_length=2000)


async def _agreement_for(token: str, *, allow_closed: bool = False) -> dict:
    from utils.cm_agreements import link_state, token_hash
    if not token or len(token) < 20:
        raise HTTPException(404, "This agreement link is not valid.")
    ag = await db.crm2_afs_agreements.find_one({"signature_request.token_hash": token_hash(token)}, {"_id": 0})
    if not ag:
        raise HTTPException(404, "This agreement link is not valid or has been replaced by a newer link.")
    state = link_state(ag.get("signature_request"))
    if ag.get("status") in ("signed", "active", "activating", "activation_attention", "declined"):
        if allow_closed:
            return ag
    if state == "revoked":
        raise HTTPException(410, "This link has been withdrawn. Please contact Pulse Fitness for a new link.")
    if state == "expired":
        from utils.cm_actions import raise_action
        await raise_action(ag["organization_id"], f"cm:agreement-link-expired:{ag['id']}", type_="agreement_step",
                           subject=f"Signature link expired: {ag.get('agreement_number')}",
                           body=f"{ag.get('company_name')} — the customer's signature link expired. Re-send for signature.",
                           contract={"id": ag["id"], "company_id": ag.get("company_id"),
                                     "contract_number": ag.get("agreement_number")})
        raise HTTPException(410, "This link has expired. Please contact Pulse Fitness and we will send a new one.")
    return ag


def _public_agreement(ag: dict) -> dict:
    sc = ag.get("schedules") or {}
    p1, p2 = sc.get("schedule1_parties") or {}, sc.get("schedule2_agreement") or {}
    req, doc = ag.get("signature_request") or {}, ag.get("document") or {}
    signed = ag.get("status") in ("signed", "activating", "activation_attention", "active")
    return {
        "agreement_number": ag.get("agreement_number"), "status": "signed" if signed else ag.get("status"),
        "supplier": (p1.get("supplier") or {}).get("name"),
        "customer": (p1.get("customer") or {}).get("legal_name"),
        "sites": [s.get("name") for s in p1.get("sites") or []],
        "agreement_type": p2.get("agreement_type"), "package": ag.get("contract_type"),
        "start_date": ag.get("start_date"), "end_date": ag.get("end_date"), "term_years": ag.get("term_years"),
        "annual_value": ag.get("annual_value"), "vat_pct": ag.get("vat_pct"),
        "billing_frequency": ag.get("billing_frequency"), "visits_per_year": ag.get("visits_per_year"),
        "equipment": [{"machine": r.get("machine"), "quantity": r.get("quantity"),
                       "serial_numbers": r.get("serial_numbers") or []} for r in sc.get("schedule3_equipment") or []],
        "exclusions": p2.get("exclusions") or [],
        "terms_version": doc.get("terms_version"), "document_version": doc.get("version"),
        "document_hash": req.get("document_hash"), "expires_at": req.get("expires_at"),
        "signatory_name": req.get("name"), "signed_at": (ag.get("signature") or {}).get("signed_at") if signed else None,
    }


@router.get("/agreement/{token}")
async def get_public_agreement(token: str):
    ag = await _agreement_for(token, allow_closed=True)
    if ag.get("status") == "sent":
        await db.crm2_afs_agreements.update_one(
            {"id": ag["id"], "status": "sent"},
            {"$set": {"status": "viewed", "viewed_at": _now(), "updated_at": _now()},
             "$push": {"signature_request.events": {"at": _now(), "event": "viewed"},
                       "timeline": {"at": _now(), "event": "Customer opened the agreement", "by": "customer"}}})
        from routes.crm_aftersales import _agreement_step_action
        await _agreement_step_action(ag["organization_id"], {**ag, "status": "viewed"})
        ag["status"] = "viewed"
    return _public_agreement(ag)


@router.get("/agreement/{token}/pdf")
async def public_agreement_pdf(token: str):
    from utils.cm_agreements import load_object
    ag = await _agreement_for(token, allow_closed=True)
    d = ag.get("signed_document") or ag.get("document")
    if not d:
        raise HTTPException(404, "Document unavailable")
    pdf = await load_object(d["storage_path"])
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{ag.get("agreement_number")}.pdf"'})


@router.post("/agreement/{token}/sign")
async def sign_public_agreement(token: str, body: AgreementSignBody, request: Request):
    from utils import cm_agreements as cma
    ag = await _agreement_for(token, allow_closed=True)
    if ag.get("status") not in ("sent", "viewed"):
        if ag.get("status") == "declined":
            raise HTTPException(409, "This agreement was declined.")
        return {"ok": True, "already_signed": True, **_public_agreement(ag)}
    req, doc = ag["signature_request"], ag.get("document") or {}
    if not (body.authority_confirmed and body.consent_confirmed):
        raise HTTPException(400, "Please confirm your authority to sign and your consent to sign electronically.")
    if body.document_hash != req["document_hash"] or req["document_hash"] != doc.get("sha256"):
        raise HTTPException(409, "The agreement has changed since this page was opened. Please reload and review it again.")
    if not body.signature_data_url.startswith("data:image/png;base64,"):
        raise HTTPException(400, "Please draw your signature.")
    sig = {"method": "customer_esignature", "signatory_name": body.signatory_name.strip(),
           "position": body.position.strip(), "email": body.email.strip(), "authority_confirmed": True,
           "consent_text": cma.CONSENT_TEXT, "signature_data_url": body.signature_data_url,
           "signed_at": _now(), "document_version": doc.get("version"), "document_hash": doc.get("sha256"),
           "terms_version": doc.get("terms_version"), "link_issued_to": req.get("email"),
           "ip": request.headers.get("x-forwarded-for", request.client.host if request.client else ""),
           "user_agent": request.headers.get("user-agent", "")[:300]}
    who = f"{sig['signatory_name']} ({sig['position']})" if sig["position"] else sig["signatory_name"]
    claimed = await db.crm2_afs_agreements.find_one_and_update(
        {"id": ag["id"], "status": {"$in": ["sent", "viewed"]}, "signature_request.token_hash": req["token_hash"],
         "signature_request.revoked": False},
        {"$set": {"status": "signed", "signature": sig, "signed_at": sig["signed_at"], "updated_at": _now()},
         "$push": {"signature_request.events": {"at": _now(), "event": "signed"},
                   "timeline": {"at": _now(), "event": f"Signed electronically by {who}", "by": sig["email"]}}})
    if not claimed:
        return {"ok": True, "already_signed": True}
    org_id = ag["organization_id"]
    stored = await cma.store_signed_copy(org_id, ag["id"])
    from routes.crm_aftersales import _agreement_step_action
    from utils.crm_audit import record_audit
    await _agreement_step_action(org_id, {**ag, "status": "signed"})
    await record_audit(entity_type="afs_agreement", entity_id=ag["id"], action="customer_esign",
                       user={"id": "customer", "email": sig["email"], "organization_id": org_id},
                       extra={"document_hash": sig["document_hash"], "version": sig["document_version"]})
    activation = await cma.try_auto_activate(org_id, ag["id"]) if stored else {"activated": False}
    return {"ok": True, "signed_at": sig["signed_at"], "activated": bool(activation.get("activated"))}


@router.post("/agreement/{token}/decline")
async def decline_public_agreement(token: str, body: AgreementDeclineBody):
    ag = await _agreement_for(token)
    if ag.get("status") not in ("sent", "viewed"):
        raise HTTPException(409, "This agreement can no longer be declined.")
    reason = (body.reason or "").strip()
    await db.crm2_afs_agreements.update_one({"id": ag["id"], "status": {"$in": ["sent", "viewed"]}}, {
        "$set": {"status": "declined", "declined_at": _now(), "declined_by": body.name.strip(),
                 "declined_reason": reason, "signature_request.revoked": True, "updated_at": _now()},
        "$push": {"timeline": {"at": _now(), "event": f"Declined by {body.name.strip()}", "by": "customer"}}})
    from routes.crm_aftersales import _agreement_step_action
    await _agreement_step_action(ag["organization_id"], {**ag, "status": "declined", "declined_reason": reason})
    return {"ok": True}
