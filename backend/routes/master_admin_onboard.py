"""
Master Admin · Head-Office onboarding sub-router.

Iter 216h181 — Extracted from `routes/master_admin.py` as phase 5a of
the 4,283 LoC → focused-routers decomposition.

Owns the multi-site Head-Office onboarding surface:
    POST /master-admin/onboard-head-office

The single route handles "Head Office customer with N sites in one pass"
(see route docstring for the data model). A single private helper —
`_validate_head_office_payload` — owns all the validation rules
(duplicate org guards, tier whitelist, owner-credential / invite-mode
fork, ≤50-sites cap, single-HQ invariant).

Shared helpers (`merge_address`, `log_activity`, `require_master_admin`)
are imported FROM `routes.master_admin` because they're used by ~12
other modules and must stay there.
"""
from datetime import datetime, timedelta, timezone
import os
import secrets
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user, hash_password as _hash_password
from utils.database import db
from routes.master_admin import (
    log_activity,
    merge_address,
    require_master_admin,
)


router = APIRouter()


async def _validate_head_office_payload(data: dict) -> dict:
    """Validate the head-office onboarding payload.

    Returns a normalised dict ready for the create flow. Raises
    HTTPException on the first failure so the wizard surfaces a clear
    field-specific error.
    """
    org_name = (data.get("org_name") or "").strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="Head office name is required")

    # Iter 216d — duplicate-org guard. A common onboarding mistake is to
    # create the same Head Office twice (once via the wizard, once via
    # an "Add organisation" shortcut). Block early with a clear message
    # so the operator can re-use the existing record. Two checks:
    #   • Exact match on company_number (canonical, unambiguous).
    #   • Case-insensitive match on org name (catches typos / casing
    #     drift like "PULSE FITNESS LIMITED" vs "Pulse Fitness Limited").
    # Caller can pass `allow_duplicate: true` to override (e.g. franchise
    # subsidiaries that share a name across regions).
    company_number = (data.get("company_number") or "").strip()
    allow_duplicate = bool(data.get("allow_duplicate"))
    if not allow_duplicate:
        if company_number:
            existing = await db.organizations.find_one(
                {"company_number": company_number}, {"_id": 0, "id": 1, "name": 1}
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"An organisation with company number {company_number} already exists ({existing.get('name')}). Open it from the org list, or pass allow_duplicate=true to create anyway.",
                )
        # Case-insensitive name match. We intentionally compare on the
        # trimmed lowercase form so "Pulse Fitness Limited" == "PULSE
        # FITNESS LIMITED" == "  pulse fitness limited  ".
        existing_by_name = await db.organizations.find_one(
            {"$expr": {"$eq": [{"$toLower": {"$trim": {"input": "$name"}}}, org_name.lower()]}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if existing_by_name:
            raise HTTPException(
                status_code=409,
                detail=f"An organisation named '{existing_by_name.get('name')}' already exists. Open it from the org list, or pass allow_duplicate=true to create anyway.",
            )

    tier = data.get("tier") or "lite"
    if tier not in ("lite", "pro", "starter", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Tier must be one of lite/pro/starter/professional/enterprise")
    # Account type is derived from tier for backwards compatibility with
    # existing role-gating logic.
    account_type = (
        "lite" if tier == "lite"
        else "pulse_pro" if tier == "pro"
        else "full"
    )

    owner_email = (data.get("owner_email") or "").strip().lower()
    owner_name = (data.get("owner_name") or "").strip()
    owner_password = (data.get("owner_password") or "").strip()
    # Iter 216f — password is now optional. If `send_invite=true` (or the
    # password is blank) we create the user with NO password and generate
    # a one-time invite token instead. Caller surfaces the URL on success.
    send_invite = bool(data.get("send_invite")) or not owner_password
    if not owner_email or not owner_name:
        raise HTTPException(status_code=400, detail="Owner email and name are required")
    if not send_invite and len(owner_password) < 8:
        raise HTTPException(status_code=400, detail="Owner password must be at least 8 characters")
    if await db.users.find_one({"email": owner_email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {owner_email} already in use")

    sites = data.get("sites") or []
    if not isinstance(sites, list) or len(sites) < 1:
        raise HTTPException(status_code=400, detail="At least one site is required")
    if len(sites) > 50:
        raise HTTPException(status_code=400, detail="Up to 50 sites per onboarding pass; split into batches if needed")

    cleaned_sites: list[dict] = []
    head_office_count = 0
    for i, s in enumerate(sites):
        if not isinstance(s, dict):
            raise HTTPException(status_code=400, detail=f"Site #{i+1} is malformed")
        s_name = (s.get("name") or "").strip()
        if not s_name:
            raise HTTPException(status_code=400, detail=f"Site #{i+1}: name is required")
        is_hq = bool(s.get("is_head_office"))
        if is_hq:
            head_office_count += 1
        # Iter 215en — accept either the structured 8-field address or the
        # legacy single-line `address` (for backwards-compat with the
        # original wizard payload). `merge_address` returns both shapes
        # auto-composed and ready to persist.
        addr = merge_address(s)
        cleaned_sites.append({
            "name": s_name,
            **addr,
            "phone": (s.get("phone") or "").strip(),
            "email": (s.get("email") or "").strip().lower(),
            # Iter 216h50 — Sicon "Invoice Customer Ref" per-site reference.
            "invoice_customer_ref": (s.get("invoice_customer_ref") or "").strip(),
            "default_location": (s.get("default_location") or "Main Floor").strip(),
            "is_head_office": is_hq,
            # Iter 216e — optional per-site equipment list captured inline
            # in the wizard or via AI invoice import. We persist each
            # machine as an Equipment doc linked to this site at onboard
            # time so the tenant can start scanning QRs immediately.
            "equipment": s.get("equipment") or [],
        })
    # Iter 216e — respect operator's choice: zero HQ is fine (registered
    # office from step 1 is the "head office"; no physical gym is the HQ).
    # We still reject multiple HQs (invariant: ≤1 HQ per org).
    if head_office_count > 1:
        raise HTTPException(status_code=400, detail="Only one site can be flagged as Head Office")

    return {
        "org_name": org_name,
        "tier": tier,
        "account_type": account_type,
        "owner_email": owner_email,
        "owner_name": owner_name,
        "owner_password": owner_password,
        "send_invite": send_invite,
        "sites": cleaned_sites,
        # Iter 215en — accept structured billing address. We pass the
        # whole `data` dict through merge_address so callers can supply
        # either the legacy `billing_address` string or the new
        # structured fields prefixed `billing_*`.
        "billing": merge_address({
            "address": data.get("billing_address", ""),
            "address_line1": data.get("billing_address_line1", ""),
            "address_line2": data.get("billing_address_line2", ""),
            "address_line3": data.get("billing_address_line3", ""),
            "city": data.get("billing_city", ""),
            "county": data.get("billing_county", ""),
            "postcode": data.get("billing_postcode", ""),
            "country": data.get("billing_country", ""),
        }),
        "billing_phone": (data.get("billing_phone") or "").strip(),
        "company_number": (data.get("company_number") or "").strip(),
        "vat_number": (data.get("vat_number") or "").strip(),
    }


@router.post("/master-admin/onboard-head-office")
async def onboard_head_office(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Iter 215el — Create a Head Office customer with N sites in one pass.

    Architecture (Option A — confirmed by user):
      • One `organizations` row = the customer (Head Office)
      • N `sites` rows = the locations under that HQ
      • Exactly one site flagged `is_head_office=true` (corporate HQ
        location); others are operational branches.
      • All downstream collections (members, equipment, contracts,
        svc_cases, crm2_*) are scoped by `organization_id` (the HQ org)
        and optionally by `site_id` for site-level operations.

    Sage / Sicon mapping:
      • Org → SLCustomerAccount / Sicon Customer
      • Each site → SLDeliveryAddress / Sicon SubLocation
    """
    require_master_admin(user)
    payload = await _validate_head_office_payload(data)
    now = datetime.now(timezone.utc).isoformat()

    org_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    company_code = str(uuid.uuid4())[:8].upper()

    # Org row — represents the customer (the Head Office).
    is_pulse = payload["account_type"] in ("lite", "pulse_pro")
    branding = (
        {"primary_color": "#66ccff", "company_name": "Pulse Fitness"}
        if is_pulse else {"primary_color": "#5b8cff", "company_name": payload["org_name"]}
    )
    await db.organizations.insert_one({
        "id": org_id,
        "name": payload["org_name"],
        "company_code": company_code,
        "owner_id": owner_id,
        "created_at": now,
        "subscription_tier": payload["tier"],
        "account_type": payload["account_type"],
        # Iter 215en — structured billing address persisted alongside the
        # legacy single-line `address`. Sage / Sicon outboxes consume the
        # legacy field; reports / UI can pull the structured shape.
        "address": payload["billing"]["address"],
        "address_line1": payload["billing"]["address_line1"],
        "address_line2": payload["billing"]["address_line2"],
        "address_line3": payload["billing"]["address_line3"],
        "city": payload["billing"]["city"],
        "county": payload["billing"]["county"],
        "postcode": payload["billing"]["postcode"],
        "country": payload["billing"]["country"],
        "contact_person": payload["owner_name"],
        "email": payload["owner_email"],
        "phone": payload["billing_phone"],
        "company_number": payload["company_number"],
        "vat_number": payload["vat_number"],
        "branding": branding,
        # Iter 215el — explicit org-level marker so the master-admin org
        # list can render the "X sites" affordance and dashboards know
        # to roll up across children.
        "is_multi_site": True,
        "site_count": len(payload["sites"]),
    })

    # Sites rows — one per location.
    site_ids: list[dict] = []
    total_equipment_created = 0
    for s in payload["sites"]:
        site_id = str(uuid.uuid4())
        await db.sites.insert_one({
            "id": site_id,
            "organization_id": org_id,
            "name": s["name"],
            "address": s["address"],
            "postcode": s["postcode"],
            "phone": s["phone"],
            "email": s["email"],
            # Iter 216h50 — Sicon "Invoice Customer Ref" per-site reference.
            # Plumbed through the multi-site onboarding wizard so equipment
            # imports later can resolve site by this code as well as by name.
            "invoice_customer_ref": (s.get("invoice_customer_ref") or "").strip(),
            "default_location": s["default_location"],
            "is_head_office": s["is_head_office"],
            "created_at": now,
            "updated_at": now,
        })
        # Iter 216e — persist per-site equipment captured in the wizard.
        # Each machine becomes an Equipment doc scoped to this org and
        # site. We silently skip rows missing a minimum viable set of
        # fields (need at least a name or make/model); UI surfaces the
        # ones that were created.
        for eq in (s.get("equipment") or []):
            name = (eq.get("name") or eq.get("model") or eq.get("make") or "").strip()
            if not name:
                continue
            await db.equipment.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "site_id": site_id,
                "name": name,
                "make": (eq.get("make") or eq.get("manufacturer") or "").strip(),
                "manufacturer": (eq.get("manufacturer") or eq.get("make") or "").strip(),
                "model": (eq.get("model") or "").strip(),
                "serial_number": (eq.get("serial_number") or eq.get("serial") or "").strip(),
                "equipment_type": (eq.get("equipment_type") or eq.get("type") or "").strip(),
                "location": (eq.get("location") or s["default_location"] or "Main Floor").strip(),
                "warranty_code": (eq.get("warranty_code") or "").strip(),
                "warranty_expiry": eq.get("warranty_expiry") or None,
                "install_date": eq.get("install_date") or None,
                "purchase_date": eq.get("purchase_date") or eq.get("install_date") or None,
                "status": "active",
                "condition": (eq.get("condition") or "good").strip(),
                "created_at": now,
                "updated_at": now,
            })
            total_equipment_created += 1
        site_ids.append({
            "id": site_id, "name": s["name"], "is_head_office": s["is_head_office"],
            "equipment_count": len(s.get("equipment") or []),
        })

    # Owner user — scoped to the HQ org.
    # Iter 216f — when send_invite=True, persist with NO password and
    # mint a password_reset_token; the wizard surfaces the URL.
    owner_doc = {
        "id": owner_id,
        "email": payload["owner_email"],
        "full_name": payload["owner_name"],
        "organization_id": org_id,
        "role": "owner",
        "account_type": payload["account_type"],
        "created_at": now,
    }
    invite_url: str | None = None
    if payload.get("send_invite"):
        # Persist user with no password — sign-in is blocked until they
        # complete the invite flow.
        owner_doc["password"] = None
        owner_doc["password_pending"] = True
        await db.users.insert_one(owner_doc)
        # Mint invite token (72h) — same shape used by the user-edit
        # invite-link endpoint so the existing /reset-password route can
        # consume it without modification.
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": owner_id, "email": payload["owner_email"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
            "used": False, "kind": "invite",
            "issued_by": user.get("email", ""),
            "created_at": now,
        })
        # Resolve the public-facing host the same way QR codes do.
        try:
            from routes.qr_codes import resolve_frontend_url
            base = resolve_frontend_url(None)
        except Exception:
            base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
        invite_url = f"{base}/reset-password?token={token}"
    else:
        owner_doc["password"] = _hash_password(payload["owner_password"])
        await db.users.insert_one(owner_doc)

    await log_activity(
        "head_office_onboarded",
        f"Onboarded Head Office '{payload['org_name']}' with {len(site_ids)} site(s)",
        user.get("email", ""), "organization", org_id,
    )

    hq = next((s for s in site_ids if s["is_head_office"]), site_ids[0])
    return {
        "success": True,
        "organization": {
            "id": org_id,
            "name": payload["org_name"],
            "company_code": company_code,
            "tier": payload["tier"],
            "account_type": payload["account_type"],
            "site_count": len(site_ids),
        },
        "head_office_site": hq,
        "sites": site_ids,
        "owner": {"id": owner_id, "email": payload["owner_email"], "name": payload["owner_name"]},
        "invite_url": invite_url,
        "equipment_created": total_equipment_created,
    }
