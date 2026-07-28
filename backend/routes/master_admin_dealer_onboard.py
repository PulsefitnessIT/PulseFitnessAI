"""
Master Admin · Dealer & Engineer onboarding sub-router.

Provisions Pulse Fitness distribution **partners** — dealers and field
engineers — who (unlike standard leisure customers) get the Service Desk
and Inventory & Distribution modules.

    POST /master-admin/onboard-dealer

A single endpoint creates:
  • one `dealer` organisation (account_type='dealer', is_dealer=True) with
    Operations + Service Desk + Inventory & Distribution enabled, capturing
    as much company detail as possible (address, company/VAT no., coverage
    region, website, phone, notes);
  • an owner user with `is_service_desk` + `is_inventory` grants;
  • optional engineers, either INSIDE the dealer org (role=engineer) or as
    their own STANDALONE engineer-partner org.

Every new account is activated either via a self-serve 72 h invite link
(→ /reset-password) or an auto-generated temporary password — chosen
per-account by the operator.
"""
from datetime import datetime, timezone
import re
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user, hash_password
from utils.database import db
from routes.master_admin import (
    _derive_portal_type,
    _generate_initial_password,
    _mint_invite_link,
    log_activity,
    merge_address,
    require_master_admin,
)

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DEALER_MODULES = ["operations", "service_desk", "inventory"]
_ENGINEER_ORG_MODULES = ["operations", "service_desk"]


async def _email_taken(email: str) -> bool:
    return bool(
        await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        or await db.crm_users.find_one({"email": email}, {"_id": 0, "id": 1})
    )


async def _activate_account(user_id: str, email: str, send_invite: bool,
                            password: str, actor_email: str) -> dict:
    """Return an activation result for a freshly-created user.

    send_invite → mint a 72 h invite link (user stays password-pending).
    otherwise   → set the given/auto-generated temporary password.
    """
    if send_invite:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"password": None, "password_pending": True}},
        )
        invite = await _mint_invite_link(user_id, email, actor_email)
        return {"mode": "invite", "invite_url": invite["invite_url"],
                "invite_expires_at": invite["expires_at"]}
    temp = password or _generate_initial_password()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password": hash_password(temp), "password_pending": False}},
    )
    return {"mode": "password", "temporary_password": temp}


@router.post("/master-admin/onboard-dealer")
async def onboard_dealer(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Create a distribution dealer partner org (Service Desk + Inventory)
    with its owner and optional engineers, in one pass."""
    require_master_admin(user)
    actor_email = user.get("email", "system")
    now = datetime.now(timezone.utc).isoformat()

    # ── Company ──────────────────────────────────────────────────────
    company_name = (data.get("company_name") or "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="Dealer company name is required")

    company_number = (data.get("company_number") or "").strip()
    allow_duplicate = bool(data.get("allow_duplicate"))
    if not allow_duplicate:
        if company_number and await db.organizations.find_one(
            {"company_number": company_number}, {"_id": 0, "name": 1}
        ):
            raise HTTPException(status_code=409,
                detail=f"An organisation with company number {company_number} already exists.")
        if await db.organizations.find_one(
            {"$expr": {"$eq": [{"$toLower": {"$trim": {"input": "$name"}}}, company_name.lower()]}},
            {"_id": 0, "id": 1},
        ):
            raise HTTPException(status_code=409,
                detail=f"An organisation named '{company_name}' already exists. Pass allow_duplicate=true to create anyway.")

    # ── Primary contact / owner ──────────────────────────────────────
    owner_name = (data.get("primary_contact_name") or "").strip()
    owner_email = (data.get("primary_contact_email") or "").strip().lower()
    if not owner_name or not owner_email:
        raise HTTPException(status_code=400, detail="Primary contact name and email are required")
    if not _EMAIL_RE.match(owner_email):
        raise HTTPException(status_code=400, detail=f"'{owner_email}' is not a valid email address")
    if await _email_taken(owner_email):
        raise HTTPException(status_code=400, detail=f"Email {owner_email} already in use")

    owner_send_invite = data.get("owner_send_invite")
    owner_send_invite = True if owner_send_invite is None else bool(owner_send_invite)
    owner_password = (data.get("owner_password") or "").strip()
    if not owner_send_invite and owner_password and len(owner_password) < 8:
        raise HTTPException(status_code=400, detail="Owner password must be at least 8 characters")

    # ── Validate engineers up-front (fail before any writes) ─────────
    engineers_in = data.get("engineers") or []
    if not isinstance(engineers_in, list):
        raise HTTPException(status_code=400, detail="engineers must be a list")
    seen_emails = {owner_email}
    cleaned_engineers = []
    for i, e in enumerate(engineers_in):
        if not isinstance(e, dict):
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1} is malformed")
        e_name = (e.get("full_name") or "").strip()
        e_email = (e.get("email") or "").strip().lower()
        if not e_name or not e_email:
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: name and email are required")
        if not _EMAIL_RE.match(e_email):
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: '{e_email}' is not a valid email")
        if e_email in seen_emails:
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: duplicate email {e_email}")
        if await _email_taken(e_email):
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: email {e_email} already in use")
        seen_emails.add(e_email)
        mode = (e.get("mode") or "in_dealer").strip()
        if mode not in ("in_dealer", "standalone"):
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: mode must be 'in_dealer' or 'standalone'")
        e_send_invite = e.get("send_invite")
        e_send_invite = True if e_send_invite is None else bool(e_send_invite)
        e_password = (e.get("password") or "").strip()
        if not e_send_invite and e_password and len(e_password) < 8:
            raise HTTPException(status_code=400, detail=f"Engineer #{i+1}: password must be at least 8 characters")
        cleaned_engineers.append({
            "full_name": e_name, "email": e_email,
            "phone": (e.get("phone") or "").strip(),
            "mode": mode,
            "region": (e.get("region") or "").strip(),
            "notes": (e.get("notes") or "").strip(),
            "date_of_birth": (e.get("date_of_birth") or "").strip(),
            "standalone_company_name": (e.get("standalone_company_name") or "").strip(),
            "send_invite": e_send_invite, "password": e_password,
        })

    # ── Create the dealer org ────────────────────────────────────────
    org_id = str(uuid.uuid4())
    addr = merge_address(data)
    org_doc = {
        "id": org_id,
        "name": company_name,
        "trading_name": (data.get("trading_name") or "").strip(),
        "company_code": str(uuid.uuid4())[:8].upper(),
        "account_type": "dealer",
        "is_dealer": True,
        "enabled_modules": list(_DEALER_MODULES),
        "portal_type": _derive_portal_type(_DEALER_MODULES),
        "subscription_tier": data.get("subscription_tier", "dealer"),
        "status": "active",
        "created_at": now,
        "created_via": "dealer_onboarding",
        "company_number": company_number,
        "vat_number": (data.get("vat_number") or "").strip(),
        "website": (data.get("website") or "").strip(),
        "phone": (data.get("phone") or "").strip(),
        "coverage_region": (data.get("coverage_region") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
        **addr,
        "primary_contact_name": owner_name,
        "primary_contact_email": owner_email,
        "primary_contact_phone": (data.get("primary_contact_phone") or "").strip(),
        "branding": {"primary_color": "#19CDFF", "company_name": company_name},
    }
    await db.organizations.insert_one(org_doc)

    # ── Owner user (Service Desk + Inventory grants) ────────────────
    owner_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": owner_id,
        "email": owner_email,
        "full_name": owner_name,
        "phone": (data.get("primary_contact_phone") or "").strip(),
        "organization_id": org_id,
        "role": "owner",
        "account_type": "dealer",
        "is_service_desk": True,
        "is_inventory": True,
        "service_org_id": org_id,
        "password": None,
        "password_pending": True,
        "created_at": now,
    })
    owner_activation = await _activate_account(
        owner_id, owner_email, owner_send_invite, owner_password, actor_email)

    # ── Engineers ────────────────────────────────────────────────────
    from routes.account import _sync_engineer_provisioning
    engineer_results = []
    for e in cleaned_engineers:
        eng_user_id = str(uuid.uuid4())
        if e["mode"] == "standalone":
            eng_org_id = str(uuid.uuid4())
            eng_org_name = e["standalone_company_name"] or f"{e['full_name']} (Engineer)"
            await db.organizations.insert_one({
                "id": eng_org_id,
                "name": eng_org_name,
                "company_code": str(uuid.uuid4())[:8].upper(),
                "account_type": "dealer",
                "is_dealer": True,
                "is_engineer_partner": True,
                "enabled_modules": list(_ENGINEER_ORG_MODULES),
                "portal_type": _derive_portal_type(_ENGINEER_ORG_MODULES),
                "subscription_tier": "engineer",
                "status": "active",
                "created_at": now,
                "created_via": "dealer_onboarding",
                "parent_dealer_org_id": org_id,
                "coverage_region": e["region"],
                "primary_contact_name": e["full_name"],
                "primary_contact_email": e["email"],
                "primary_contact_phone": e["phone"],
                "branding": {"primary_color": "#19CDFF", "company_name": eng_org_name},
            })
            target_org_id = eng_org_id
        else:
            target_org_id = org_id

        await db.users.insert_one({
            "id": eng_user_id,
            "email": e["email"],
            "full_name": e["full_name"],
            "phone": e["phone"],
            "date_of_birth": e["date_of_birth"] or None,
            "organization_id": target_org_id,
            "role": "engineer",
            "account_type": "dealer",
            "region": e["region"],
            "notes": e["notes"],
            "password": None,
            "password_pending": True,
            "created_at": now,
        })
        # Unlock the Engineer App (creates an active svc_engineers row).
        try:
            await _sync_engineer_provisioning({
                "id": eng_user_id, "organization_id": target_org_id, "role": "engineer",
                "full_name": e["full_name"], "email": e["email"],
            })
        except Exception:  # noqa: BLE001 — never fail onboarding on provisioning sync
            pass
        activation = await _activate_account(
            eng_user_id, e["email"], e["send_invite"], e["password"], actor_email)
        engineer_results.append({
            "id": eng_user_id, "email": e["email"], "full_name": e["full_name"],
            "mode": e["mode"], "organization_id": target_org_id, **activation,
        })

    await log_activity(
        "dealer_onboarded",
        f"Onboarded dealer '{company_name}' with {len(engineer_results)} engineer(s)",
        actor_email, "organization", org_id,
    )

    return {
        "success": True,
        "organization": {
            "id": org_id, "name": company_name, "account_type": "dealer",
            "company_code": org_doc["company_code"],
            "enabled_modules": list(_DEALER_MODULES),
        },
        "owner": {"id": owner_id, "email": owner_email, "full_name": owner_name,
                  **owner_activation},
        "engineers": engineer_results,
    }
