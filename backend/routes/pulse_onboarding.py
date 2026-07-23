"""
Automated customer portal onboarding.

When a confirmed CRM quote is pushed to Distribution, provision the customer's own
Pulse Lite tenant (organisation + pending owner) and email them a branded
"Set up your Pulse portal access" link (reusing the password_reset_tokens flow).
Auto-links the CRM company to the new org so their in-dashboard Deliveries tab works.
Idempotent, best-effort, and never blocks the order flow.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from utils.database import db
from utils.auth import hash_password
from utils.email import send_email, wrap_branded

logger = logging.getLogger(__name__)

SETUP_TOKEN_TTL_HOURS = 72  # generous window for a first-time set-up link


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_contact(company: dict) -> tuple[str, str]:
    """Return (email, name) for the company's main contact."""
    email = (company.get("primary_contact_email") or "").strip().lower()
    name = company.get("primary_contact_name") or company.get("name") or ""
    if not email:
        contact = await db.crm2_contacts.find_one(
            {"company_id": company.get("id"), "email": {"$nin": [None, ""]}, "gdpr_erased": {"$ne": True}},
            {"_id": 0, "email": 1, "first_name": 1, "last_name": 1, "name": 1}, sort=[("created_at", 1)])
        if contact:
            email = (contact.get("email") or "").strip().lower()
            name = name or contact.get("name") or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    return email, (name or email)


async def _notify(owner_email: str | None, subject: str, html: str, org_id: str | None = None):
    if not owner_email:
        return
    try:
        await send_email(to=owner_email, subject=subject, html=await wrap_branded(html, org_id), kind="ops_notification")
    except Exception:
        pass


async def _send_setup_email(*, to_email: str, name: str, org: dict, order_ref: str, owner_email: str | None):
    from utils.brand_urls import app_url_for_org
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": org["owner_id"],
        "email": to_email,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=SETUP_TOKEN_TTL_HOURS)).isoformat(),
        "used": False,
        "purpose": "portal_setup",
        "created_at": _now(),
    })
    link = f"{app_url_for_org(org).rstrip('/')}/reset-password?token={token}"
    html = await wrap_branded(f"""
      <p>Hi {name.split(' ')[0] if name else 'there'},</p>
      <p>Your Pulse Fitness portal is ready. Set your password to access your dashboard,
      where you can track your upcoming installation, warranty and equipment.</p>
      <p style="margin:24px 0"><a href="{link}"
        style="background:#0BB0DD;color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:700">
        Set up your Pulse portal access</a></p>
      <p style="color:#64748b;font-size:13px">Order reference: {order_ref or '—'}. This link is single-use and expires in {SETUP_TOKEN_TTL_HOURS // 24} days.</p>
    """, org.get("id"))
    try:
        await send_email(to=to_email, subject="Set up your Pulse Fitness portal access", html=html, kind="portal_setup")
        await db.crm2_companies.update_one({"id": org["_crm_company_id"]}, {"$set": {"pulse_onboarding_state": "sent_pending_password", "pulse_onboarding_sent_at": _now()}})
        await _notify(owner_email, "Customer portal invite sent",
                      f"<p>A Pulse portal set-up email was sent to <b>{to_email}</b> for <b>{org.get('name')}</b>.</p>", org.get("id"))
    except Exception as exc:
        logger.exception("[pulse-onboarding] setup email failed")
        await db.crm2_companies.update_one({"id": org["_crm_company_id"]}, {"$set": {"pulse_onboarding_state": "email_failed", "pulse_onboarding_email_error": str(exc)}})
        await _notify(owner_email, "Customer portal invite FAILED to send",
                      f"<p>The account for <b>{org.get('name')}</b> was created but the invite email to <b>{to_email}</b> failed. Please resend from the customer record.</p>", org.get("id"))


async def register_customer_equipment(alloc: dict, warranty: dict | None = None) -> dict:
    """When an install is commissioned, register the machine in the customer's own
    Pulse org (if linked) so it appears in their Lite/Pro Equipment list and they can
    log faults on it. Idempotent by (organization_id, serial_number). Best-effort."""
    company_id = alloc.get("customer_company_id")
    if not company_id:
        return {"status": "skipped", "reason": "no_company"}
    company = await db.crm2_companies.find_one({"id": company_id}, {"_id": 0, "linked_operator_org_id": 1})
    org_id = (company or {}).get("linked_operator_org_id")
    if not org_id:
        return {"status": "skipped", "reason": "not_linked"}
    serial = alloc.get("serial_number")
    existing = await db.equipment.find_one(
        {"organization_id": org_id, "serial_number": serial}, {"_id": 0, "id": 1}) if serial else None
    if existing:
        return {"status": "exists", "equipment_id": existing["id"]}
    now = _now()
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": alloc.get("model") or alloc.get("product_code") or "Pulse Fitness equipment",
        "manufacturer": "Pulse Fitness",
        "model": alloc.get("model") or alloc.get("product_code"),
        "serial_number": serial,
        "status": "operational",
        "supplier": "Pulse Fitness",
        "supplier_email": "service.dept@pulsefitness.com",
        "warranty_expiry": (warranty or {}).get("warranty_end"),
        "source": "distribution_install",
        "source_allocation_id": alloc.get("id"),
        "manuals": [],
        "created_at": now, "updated_at": now,
    }
    await db.equipment.insert_one({**doc})
    return {"status": "created", "equipment_id": doc["id"], "organization_id": org_id}

    """Idempotently create a Pulse Lite tenant for a CRM customer and email a
    set-up link. Safe to call best-effort from the order flow."""
    now = _now()
    # Atomic claim: only proceed if not already linked and not mid-processing.
    claimed = await db.crm2_companies.find_one_and_update(
        {"id": company_id,
         "$or": [{"linked_operator_org_id": {"$exists": False}}, {"linked_operator_org_id": None}],
         "pulse_onboarding_state": {"$ne": "processing"}},
        {"$set": {"pulse_onboarding_state": "processing", "pulse_onboarding_claimed_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        return {"status": "skipped", "reason": "already_linked_or_processing"}

    email, name = await _resolve_contact(claimed)
    if not email:
        await db.crm2_companies.update_one({"id": company_id}, {"$set": {"pulse_onboarding_state": "skipped_missing_email"}})
        await _notify(owner_email, "Customer portal onboarding needs a contact email",
                      f"<p>Couldn't send the Pulse portal invite for <b>{claimed.get('name')}</b> — no contact email on the customer record. Please add one and resend.</p>",
                      claimed.get("organization_id"))
        return {"status": "skipped", "reason": "missing_contact_email"}

    # Guard: a Pulse account may already exist for this email — link to it instead of creating a duplicate.
    existing_user = await db.users.find_one({"email": email}, {"_id": 0, "organization_id": 1})
    if existing_user and existing_user.get("organization_id"):
        await db.crm2_companies.update_one({"id": company_id}, {"$set": {
            "linked_operator_org_id": existing_user["organization_id"],
            "pulse_onboarding_state": "linked_existing_account", "updated_at": now}})
        await _notify(owner_email, "Customer linked to existing Pulse account",
                      f"<p><b>{claimed.get('name')}</b> already has a Pulse account ({email}); linked it so they see their deliveries. No invite sent.</p>",
                      claimed.get("organization_id"))
        return {"status": "linked_existing", "org_id": existing_user["organization_id"]}

    # Create the Lite org + pending owner (unusable password until they set one).
    org_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    org_doc = {
        "id": org_id, "name": claimed.get("name") or email,
        "company_code": str(uuid.uuid4())[:8].upper(),
        "owner_id": owner_id, "created_at": now,
        "account_type": "lite", "subscription_tier": "none",
        "created_via": "distribution_onboarding",
    }
    try:
        from utils.localization import resolve_org_fields
        org_doc.update(resolve_org_fields(claimed.get("country")))
    except Exception:
        pass
    await db.organizations.insert_one({**org_doc})
    await db.users.insert_one({
        "id": owner_id, "email": email, "password": hash_password(secrets.token_urlsafe(24)),
        "full_name": name, "organization_id": org_id, "role": "owner",
        "status": "active", "account_type": "lite",
        "created_via": "distribution_onboarding", "created_at": now, "password_updated_at": now,
    })
    await db.crm2_companies.update_one({"id": company_id}, {"$set": {
        "linked_operator_org_id": org_id, "pulse_onboarding_owner_user_id": owner_id, "updated_at": now}})

    org_doc["_crm_company_id"] = company_id
    asyncio.create_task(_send_setup_email(to_email=email, name=name, org=org_doc, order_ref=order_ref, owner_email=owner_email))
    return {"status": "provisioned", "org_id": org_id, "email": email}
