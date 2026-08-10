"""Iter 220e3 — Contract PDF download + email send + public accept.

Phase D of the Contracts evolution. Adds three endpoints alongside the
existing ``routes/crm_contracts.py`` CRUD so the wizard's "Save &
Send" path can produce a branded PDF, email it via Resend, and let
the customer accept it through a tokenised public URL without
needing a CRM seat.

Endpoints (all under ``/api/crm/v2``):

* ``GET  /contracts/{id}/pdf``            — authenticated, streams PDF
* ``POST /contracts/{id}/send``           — emails the customer
* ``GET  /public/contracts/{token}``      — customer-facing snapshot
* ``POST /public/contracts/{token}/sign`` — customer accepts & signs
"""
from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from routes.crm_auth import get_crm_user
from routes.crm_contract_templates import (
    INCLUSION_GROUPS, EXCLUSION_ITEMS, CONSUMABLE_PRESETS, RESPONSE_TIME_BANDS,
)
from utils.crm_audit import record_audit
from utils.crm_contract_pdf import build_contract_pdf
from utils.database import db


router = APIRouter(prefix="/crm/v2", tags=["Contracts · Send & Sign"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org if org else "__none__"}


def _build_catalog() -> dict:
    """Mirror of the public ``/contract-catalog`` shape, used server-
    side when rendering the PDF so labels resolve without an extra
    fetch hop."""
    return {
        "inclusion_groups": INCLUSION_GROUPS,
        "exclusion_items":  EXCLUSION_ITEMS,
        "consumable_presets": CONSUMABLE_PRESETS,
        "response_time_bands": RESPONSE_TIME_BANDS,
    }


async def _load_contract_with_org(contract_id: str, user_of: dict):
    contract = await db.crm2_contracts.find_one({"id": contract_id, **user_of}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    org = {}
    if contract.get("organization_id"):
        org = await db.organizations.find_one(
            {"id": contract["organization_id"]},
            {"_id": 0, "name": 1, "primary_color": 1, "brand_primary_color": 1,
             "logo_url": 1, "brand_kit": 1},
        ) or {}
    return contract, org


@router.get("/contracts/{contract_id}/pdf")
async def download_contract_pdf(contract_id: str, user: dict = Depends(get_crm_user)):
    """Build the branded contract PDF and stream it back to the
    operator. Uses the SAME builder as the email send path so the
    customer sees an identical artifact."""
    contract, org = await _load_contract_with_org(contract_id, _of(user))
    from utils.document_branding import resolve_company_if_configured
    company = await resolve_company_if_configured(db, {"id": contract.get("organization_id"), "name": org.get("name")})
    pdf_bytes = build_contract_pdf(contract, org, _build_catalog(), company=company)
    fn = f"contract_{contract.get('contract_number') or contract_id[:8]}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{fn}\""},
    )


async def _ensure_accept_token(contract_id: str, of: dict) -> str:
    contract = await db.crm2_contracts.find_one(
        {"id": contract_id, **of}, {"_id": 0, "accept_token": 1, "id": 1},
    )
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.get("accept_token"):
        return contract["accept_token"]
    token = secrets.token_urlsafe(22)
    await db.crm2_contracts.update_one(
        {"id": contract_id},
        {"$set": {"accept_token": token, "updated_at": _now()}},
    )
    return token


@router.post("/contracts/{contract_id}/send")
async def send_contract_to_customer(contract_id: str, data: dict,
                                    user: dict = Depends(get_crm_user)):
    """Email the contract PDF to the customer's primary or billing
    contact. Returns the public accept-link so the operator can also
    copy/paste it manually if email is unreliable.

    Body:
        {
          "to":      "alice@gym.com" (optional — defaults to billing/primary contact email),
          "subject": "Your service contract is ready" (optional override),
          "message": "Please review and sign…" (optional override)
        }
    """
    of = _of(user)
    contract, org = await _load_contract_with_org(contract_id, of)

    # Workflow lock: a contract must be APPROVED before it can be sent to the
    # customer (blocks the draft → sent → public-sign → active skip path).
    if (contract.get("status") or "").lower() in ("draft", "negotiation", "amended", "pending_approval", "rejected"):
        from utils.security_events import log_security_event, SEV_WARNING
        await log_security_event(
            "contract_send_blocked_unapproved", user=user, severity=SEV_WARNING,
            resource_type="contract", resource_id=contract_id, action="send",
            result="denied", detail=f"status={contract.get('status')}",
        )
        raise HTTPException(403, "This contract must be approved before it can be sent to the customer.")

    # Resolve recipient.
    to_email = (data.get("to") or "").strip().lower()
    if not to_email:
        for cid in (contract.get("billing_contact_id"), contract.get("contact_id")):
            if not cid:
                continue
            ct = await db.crm2_contacts.find_one({"id": cid}, {"_id": 0, "email": 1})
            if ct and ct.get("email"):
                to_email = ct["email"]
                break
    if not to_email:
        raise HTTPException(400, "No recipient email — pass `to` or set a contact email")

    # Build PDF + accept link.
    from utils.document_branding import resolve_company_if_configured
    company = await resolve_company_if_configured(db, {"id": contract.get("organization_id"), "name": org.get("name")})
    pdf_bytes = build_contract_pdf(contract, org, _build_catalog(), company=company)
    token = await _ensure_accept_token(contract_id, of)
    # Public URL is deliberately relative — the FE renders it under the
    # current host (same trick the public tracking link uses).
    accept_path = f"/contracts/accept/{token}"

    subject = data.get("subject") or (
        f"Your {contract.get('tier', 'service').title()} service contract — "
        f"{contract.get('contract_number') or ''}"
    ).strip()
    intro = data.get("message") or (
        f"Hi,\n\nPlease find your service contract attached. You can review "
        f"and accept it online at {accept_path}.\n\nKind regards,\n"
        f"{org.get('name', 'Your service team')}"
    )
    html = (
        f"<p>Hi,</p>"
        f"<p>Please find your service contract attached. "
        f"You can also review and accept it online here: "
        f"<a href=\"{accept_path}\">{accept_path}</a>.</p>"
        f"<p>Kind regards,<br/>{org.get('name', 'Your service team')}</p>"
    )

    # Attempt email send — gracefully degrade if Resend isn't configured.
    sent_ok = False
    try:
        from utils.email import send_email
        sent_ok = await send_email(
            to=to_email, subject=subject, html=html, text=intro,
            attachments=[{
                "filename": f"contract_{contract.get('contract_number') or contract_id[:8]}.pdf",
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            }],
        )
    except Exception:
        sent_ok = False

    await db.crm2_contracts.update_one(
        {"id": contract_id},
        {"$set": {"last_sent_at": _now(), "last_sent_to": to_email,
                  "status": "sent" if contract.get("status") in ("draft", "approved") else contract.get("status"),
                  "updated_at": _now()}},
    )
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": contract.get("organization_id"),
        "type": "system", "contract_id": contract_id,
        "subject": f"Contract sent: {contract.get('contract_number')}",
        "body": f"Sent to {to_email}" + ("" if sent_ok else " (email delivery deferred)"),
        "company_id": contract.get("company_id", ""),
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(),
    })
    await record_audit(
        entity_type="contract", entity_id=contract_id, action="send",
        user=user, before=contract,
        after={**contract, "last_sent_to": to_email, "last_sent_at": _now()},
        summary=f"Contract sent to {to_email}",
    )
    return {
        "success": True, "to": to_email,
        "email_dispatched": sent_ok,
        "accept_path": accept_path,
    }


# ── Public accept endpoints ───────────────────────────────────


@router.get("/public/contracts/{token}")
async def public_contract_snapshot(token: str):
    """Customer-safe contract snapshot for the accept page. No auth —
    the token is the gate. Drops everything we don't want bleeding into
    the public URL (cost estimates, margin, internal owner ids, etc.)."""
    if not token or len(token) < 16:
        raise HTTPException(404, "Contract not found")
    c = await db.crm2_contracts.find_one(
        {"accept_token": token},
        {"_id": 0, "id": 1, "contract_number": 1, "title": 1, "tier": 1,
         "company_name": 1, "site_name": 1, "site_id": 1, "contact_name": 1,
         "start_date": 1, "end_date": 1, "renewal_date": 1,
         "billing_frequency": 1, "annual_value": 1,
         "inclusions": 1, "exclusions_structured": 1, "consumables": 1,
         "response_times": 1, "terms_md": 1, "signed_at": 1, "signed_by": 1,
         "status": 1, "organization_id": 1,
         "pricing": 1},
    )
    if not c:
        raise HTTPException(404, "Contract not found")
    # Strip internal cost / margin from the pricing payload before returning.
    pricing = {k: v for k, v in (c.get("pricing") or {}).items()
               if k not in {"cost_estimate", "margin_percent"}}
    c["pricing"] = pricing
    org = await db.organizations.find_one(
        {"id": c.get("organization_id")},
        {"_id": 0, "name": 1, "logo_url": 1},
    ) or {}
    return {
        **{k: v for k, v in c.items() if k != "organization_id"},
        "organization": {"name": org.get("name") or "Your service team",
                         "logo_url": org.get("logo_url") or ""},
    }


@router.post("/public/contracts/{token}/sign")
async def public_contract_sign(token: str, data: dict):
    """Customer accepts and signs via the public URL. Body:

        {"signer_name": "Alice Customer", "signature": "data:image/png;base64,…"}

    On success the contract status is moved to ``active`` and a
    contract_activated integration event is fired (same path as the
    in-CRM signature canvas)."""
    if not token or len(token) < 16:
        raise HTTPException(404, "Contract not found")
    signer = (data.get("signer_name") or "").strip()
    sig = (data.get("signature") or "").strip()
    if not signer or not sig:
        raise HTTPException(400, "signer_name and signature are required")
    contract = await db.crm2_contracts.find_one({"accept_token": token}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.get("status") in ("active", "signed", "cancelled"):
        # Idempotent — re-signing an already-signed contract just confirms.
        return {"success": True, "status": contract["status"], "already_signed": True}
    # Defensive workflow lock: the public link can only activate a contract
    # that reached the customer via the approved→sent path.
    from utils.authz import assert_transition
    await assert_transition("contract", contract.get("status"), "active", {},
                            resource_id=contract["id"])
    updates = {
        "signed_by": signer, "signed_at": _now(),
        "signature": sig, "status": "active",
        "updated_at": _now(),
    }
    await db.crm2_contracts.update_one({"id": contract["id"]}, {"$set": updates})
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": contract.get("organization_id"),
        "type": "system", "contract_id": contract["id"],
        "subject": f"Contract signed: {contract.get('contract_number')}",
        "body": f"Accepted by {signer} via public link",
        "company_id": contract.get("company_id", ""),
        "owner_id": None, "owner_name": signer,
        "created_at": _now(),
    })
    # Fire the same integration event the in-CRM signature path does.
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="contract_activated", source_system="crm",
            target_system="service_portal",
            entity_type="contract", entity_id=contract["id"],
            payload={"contract_id": contract["id"],
                     "company_id": contract.get("company_id", ""),
                     "sla_tier": contract.get("tier", "standard"),
                     "start_date": contract.get("start_date", ""),
                     "end_date": contract.get("end_date", "")},
            organization_id=contract.get("organization_id", ""),
            triggered_by=signer,
        )
    except Exception:
        pass
    return {"success": True, "status": "active"}
