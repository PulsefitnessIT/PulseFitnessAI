"""
Master Admin · Org-create + primary-contact sub-router.

Iter 216h183 — Extracted from `routes/master_admin.py` as phase 7 of
the 4,283 LoC → focused-routers decomposition.

Owns the org-bootstrap surface — the 3 endpoints used when a Master
Admin spins up a new tenant and hands the credentials over:

    POST /master-admin/organizations
    GET  /master-admin/organizations/{org_id}/primary-contact-credentials
    POST /master-admin/organizations/{org_id}/send-primary-contact-credentials

The 6 module-helpers (`_normalize_modules`, `_modules_from_portal_type`,
`_derive_portal_type`, `_generate_initial_password`, `_mint_invite_link`,
`_ensure_primary_contact_user`) STAY on `routes.master_admin` because
`routes/master_admin_orgs.py` already imports 4 of them directly —
moving them now would break the iter-216h178 split. We re-import them
here as regular dependencies.

`PULSE_VISIBLE_ACCOUNT_TYPES`, `assert_org_in_pulse_scope`,
`is_pulse_only`, `log_activity`, `merge_address`, `require_master_admin`
similarly stay on the parent because they're shared across ~12 modules.
"""
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    PULSE_VISIBLE_ACCOUNT_TYPES,
    _derive_portal_type,
    _ensure_primary_contact_user,
    _mint_invite_link,
    _normalize_modules,
    assert_org_in_pulse_scope,
    is_pulse_only,
    log_activity,
    merge_address,
    require_master_admin,
)


router = APIRouter()


def _localization_fields(body: dict) -> dict:
    """Iter 220p1 — resolve country/currency/timezone for a new org.

    A ``country_code`` derives the currency + timezone defaults; explicit
    ``currency`` / ``timezone`` in the body override. Only emits keys that
    were resolved (defaults to GB when nothing supplied)."""
    from utils.localization import country_config, COUNTRY_CONFIG, CURRENCY_SYMBOLS
    code = (body.get("country_code") or "").strip().upper()
    if not code or code not in COUNTRY_CONFIG:
        code = "GB"
    cfg = country_config(code)
    currency = (body.get("currency") or cfg["currency"]).strip().upper()
    if currency not in CURRENCY_SYMBOLS:
        currency = cfg["currency"]
    timezone_ = (body.get("timezone") or cfg["timezone"]).strip()
    return {"country_code": code, "currency": currency, "timezone": timezone_}



@router.post("/master-admin/organizations")
async def create_organization(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create a new organisation (Service Portal, CRM, or both)."""
    require_master_admin(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organisation name is required")

    # Iter 215ar — `enabled_modules` is the new source of truth for
    # which modules an org has access to. The legacy `portal_type`
    # ("service_portal" | "crm" | "both") is derived from it for
    # backwards-compatibility with existing callers / DB queries.
    raw_modules = body.get("enabled_modules") or body.get("modules")
    enabled_modules = _normalize_modules(raw_modules, body.get("portal_type"))
    portal_type = _derive_portal_type(enabled_modules)

    # Pulse-only admins can only create Pulse-visible orgs.
    requested_account_type = body.get("account_type", "full")
    if is_pulse_only(user) and requested_account_type not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Pulse admins can only create Pulse-visible account types: {PULSE_VISIBLE_ACCOUNT_TYPES}",
        )

    org_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Iter 216h109 — MOD portal fields. `is_mod` flags the org for the
    # MOD module-gating rules (no Memberships/CRM/Marketing/Staffing/
    # Gym Layout). `mod_force` (army|raf|navy) groups sites under the
    # right Command-Centre HQ. `parent_organization_id` chains a site
    # under its service HQ.
    is_mod = bool(body.get("is_mod") or False)
    mod_force = (body.get("mod_force") or "").strip().lower() or None
    if mod_force and mod_force not in {"army", "raf", "navy"}:
        raise HTTPException(status_code=400, detail="mod_force must be army, raf, or navy")
    parent_organization_id = body.get("parent_organization_id") or None
    org_doc = {
        "id": org_id, "name": name,
        "portal_type": portal_type,
        "enabled_modules": enabled_modules,
        "subscription_tier": body.get("subscription_tier", "free"),
        "account_type": requested_account_type,
        "status": "active", "created_at": now,
        "company_code": str(uuid.uuid4())[:8].upper(),
        "industry": body.get("industry", ""),
        "employee_count": body.get("employee_count", ""),
        "website": body.get("website", ""),
        "phone": body.get("phone", ""),
        # MOD portal hierarchy + flagging.
        "is_mod": is_mod,
        "mod_force": mod_force,
        "parent_organization_id": parent_organization_id,
        # Iter 215en — accept structured 8-field address. Legacy `address`
        # is retained for downstream Sage / Sicon outboxes; we auto-compose
        # it from the structured shape when only the structured fields are
        # supplied.
        **merge_address(body),
        "primary_contact_name": body.get("primary_contact_name", ""),
        "primary_contact_email": body.get("primary_contact_email", ""),
        "primary_contact_phone": body.get("primary_contact_phone", ""),
        # Iter 220p1 — localization market. Defaults to UK when unset;
        # picking a country auto-derives currency + timezone defaults.
        **_localization_fields(body),
        "notes": body.get("notes", ""),
        "features": body.get("features", {}),
    }
    await db.organizations.insert_one(org_doc)

    # Iter 215ar — auto-provision a user account for the primary contact
    # so the org owner can sign in immediately. Master admin can reveal the
    # initial password from the org panel until the user changes it.
    await _ensure_primary_contact_user(org_doc, user)

    # Iter 216h26 — also mint a 72 h invite link so the operator can
    # send a self-serve "set your own password" URL instead of relying
    # on the credentials-reveal handover. Both paths remain valid;
    # operators can pick whichever fits the customer.
    invite_payload = None
    try:
        org_after = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        owner_id = (org_after or {}).get("primary_contact_user_id")
        owner_email = (org_after or {}).get("primary_contact_email")
        if owner_id and owner_email:
            invite_payload = await _mint_invite_link(owner_id, owner_email, user.get("email", "system"))
    except Exception:  # noqa: BLE001 — never fail org creation on invite mint
        invite_payload = None

    await log_activity("org_created", f"Created organisation: {name} ({portal_type})", user["email"], "organization", org_id)
    fresh = await db.organizations.find_one({"id": org_id}, {"_id": 0, "primary_contact_initial_password": 0})
    response: dict = {**(fresh or org_doc), "user_count": 0}
    if invite_payload:
        response["owner"] = {
            "email": fresh.get("primary_contact_email"),
            "user_id": fresh.get("primary_contact_user_id"),
            "invite_url": invite_payload["invite_url"],
            "invite_expires_at": invite_payload["expires_at"],
        }
        # Convenience top-level keys so older callers keep working.
        response["invite_url"] = invite_payload["invite_url"]
        response["invite_expires_at"] = invite_payload["expires_at"]
    return response


@router.get("/master-admin/organizations/{org_id}/primary-contact-credentials")
async def get_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Reveal the auto-generated initial password for the org's primary
    contact user. Audited every time it is accessed. Cleared once the
    contact changes their own password (see password reset flow)."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        return {"email": None, "initial_password": None, "password_changed": False, "available": False}
    await log_activity(
        "primary_contact_password_revealed",
        f"Revealed initial password for {email}",
        user["email"], "organization", org_id,
    )
    return {
        "email": email,
        "initial_password": initial if (initial and not changed) else None,
        "password_changed": changed,
        "available": bool(initial and not changed),
    }


@router.post("/master-admin/organizations/{org_id}/send-primary-contact-credentials")
async def send_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 215at — email the auto-generated initial credentials to the
    primary contact via Resend, then clear the plaintext from the org doc
    so it can no longer be revealed in the panel.

    Audited. Returns 400 if no credentials are available to send."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email   = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        raise HTTPException(400, "No primary contact email set on this organisation")
    if not initial or changed:
        raise HTTPException(400, "No initial password is available to send (already used or rotated)")

    # Late import — avoid the helper module loading at startup if email
    # is misconfigured. send_email is best-effort and audited internally.
    from utils.email import send_email

    org_name  = org.get("name", "your GymAxis account")
    contact   = org.get("primary_contact_name") or email.split("@")[0]
    subject   = f"Welcome to {org_name} on GymAxis"

    # Plain HTML — no inline images, no tracking pixels, deliverability-friendly.
    html = f"""
    <div style="font-family:Inter,system-ui,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a">
      <h1 style="font-size:20px;font-weight:800;letter-spacing:-0.4px;margin:0 0 8px">Welcome to GymAxis, {contact}.</h1>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Your account for <strong>{org_name}</strong> is ready. Use the credentials below to sign in for the first time.
      </p>
      <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;background:#f8fafc;margin-bottom:20px">
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Email</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0 0 14px;color:#0f172a">{email}</p>
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Temporary password</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0;color:#0f172a">{initial}</p>
      </div>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Please change your password the first time you sign in — go to your profile menu and select
        <em>Change password</em>. The temporary password above will stop working once you do.
      </p>
      <a href="https://gymaxisai.com/login" style="display:inline-block;background:linear-gradient(135deg,#2563EB,#9D4CDD);color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:999px;font-size:14px">Sign in to GymAxis</a>
      <p style="font-size:11px;color:#94a3b8;margin-top:32px">
        If you weren't expecting this email, please contact us at security@gymaxisai.com.
      </p>
    </div>
    """

    ok = await send_email(email, subject, html)
    if not ok:
        raise HTTPException(502, "Email could not be delivered. Please try again or copy the password manually.")

    # Clear the plaintext from the org doc immediately on successful send —
    # we no longer need to keep it; if the user loses the email they can
    # reset via the standard /auth/forgot-password flow.
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"primary_contact_credentials_sent_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"primary_contact_initial_password": ""}},
    )
    await log_activity(
        "primary_contact_credentials_emailed",
        f"Emailed initial credentials to {email}",
        user["email"], "organization", org_id,
    )
    return {"sent": True, "email": email}
