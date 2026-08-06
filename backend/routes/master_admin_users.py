"""
Master Admin · Users CRUD + impersonate sub-router.

Iter 216h179 — Extracted from `routes/master_admin.py` as phase 3 of
the 4,283 LoC → 5-6 focused routers decomposition.

Owns the platform-wide user lifecycle surface:
    POST   /master-admin/users/{user_id}/invite-link        — 72h signed link
    POST   /master-admin/organizations/{org_id}/users       — create
    GET    /master-admin/users                              — list (with portals, invites, role-mismatch flags)
    PUT    /master-admin/users/{user_id}/edit
    PUT    /master-admin/users/{user_id}/disable
    PUT    /master-admin/users/{user_id}/archive
    DELETE /master-admin/users/{user_id}                    — hard-delete + cascade
    PUT    /master-admin/users/{user_id}/reset-password
    POST   /master-admin/impersonate/{user_id}              — short-lived JWT

All shared helpers stay on the parent `routes.master_admin` module —
this file imports `require_master_admin`, `assert_user_in_pulse_scope`,
`assert_org_in_pulse_scope`, `is_pulse_only`, `_create_org_user`,
`log_activity`, `PULSE_VISIBLE_ACCOUNT_TYPES`.
"""
from datetime import datetime, timedelta, timezone
import logging
import os
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    PULSE_VISIBLE_ACCOUNT_TYPES,
    ALL_MODULE_IDS,
    _create_org_user,
    _derive_portal_type,
    assert_org_in_pulse_scope,
    assert_user_in_pulse_scope,
    is_desk_inventory_entitled,
    is_pulse_only,
    log_activity,
    require_master_admin,
)


logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────── invite-link issuer ─────────────

@router.post("/master-admin/users/{user_id}/invite-link")
async def issue_user_invite_link(user_id: str, user: dict = Depends(get_current_user)):
    """Iter 215ev — issue a signed set-password link for a user.

    Returns a URL the master admin can COPY and send manually (WhatsApp,
    their own email, Slack) while Resend DNS verification is pending —
    or use alongside automatic Resend delivery. 72h expiry. The user
    sets their own password on the linked page; master admin never
    sees the plaintext. Same mechanism is reused for "forgot password"
    resets (see /auth/forgot-password).
    """
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)

    target = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": target["id"],
        "email": target.get("email", ""),
        "expires_at": expires_at,
        "used": False,
        "kind": "invite",  # distinguishes "set initial password" from "forgot password"
        "issued_by": user.get("email", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    invite_url = f"{frontend_url}/reset-password?token={token}"
    await log_activity("user_invite_link_issued", f"Invite link issued for {target.get('email')}", user["email"], "user", target["id"])
    return {
        "invite_url": invite_url,
        "expires_at": expires_at,
        "email": target.get("email", ""),
        "full_name": target.get("full_name", ""),
    }


# ───────────── module-access diagnostics (Iter 278f) ─────────────
_MODULE_META = {
    "operations":  ("Operations", "Service desk, equipment, faults"),
    "memberships": ("Memberships", "Members, classes, billing"),
    "marketing":   ("Marketing", "Campaigns, segments, image library"),
    "crm":         ("CRM", "Leads, deals, business pipeline"),
}


@router.get("/master-admin/users/{user_id}/module-access")
async def get_user_module_access(user_id: str, user: dict = Depends(get_current_user)):
    """Diagnostics for the People drawer: per-module ORG-level vs USER-level
    access plus a plain-English reason, so a master admin can instantly see
    WHY someone can or can't reach a module (e.g. CRM lock-outs)."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)

    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    org = None
    org_id = target.get("organization_id")
    if org_id:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})

    return _module_access_payload(target, org)


def _module_access_payload(target: dict, org: Optional[dict]) -> dict:
    """Build the per-module access diagnostics for a user + their org."""
    from utils.module_access import (
        MODULE_KEYS, org_module_access, resolve_module_access,
    )
    org_lvl = org_module_access(org)
    effective = resolve_module_access(target, org)

    role = (target.get("role") or "").lower()
    is_master = bool(target.get("is_master_admin"))
    is_pulse = bool(target.get("is_pulse_admin")) or role == "pulse_master_admin"
    is_owner = role == "owner"
    privileged = is_master or is_pulse or is_owner
    priv_label = (
        "Platform Master Admin" if is_master
        else "Pulse Master Admin" if is_pulse
        else "Owner" if is_owner else ""
    )

    modules = []
    for key in MODULE_KEYS:
        label, blurb = _MODULE_META.get(key, (key.title(), ""))
        org_on = bool(org_lvl.get(key))
        user_on = bool(effective.get(key))
        if privileged:
            reason, action = f"Full access — {priv_label}", None
        elif not org_on:
            reason, action = "Not enabled for this organisation", "grant_org"
        elif user_on:
            reason, action = "Enabled", None
        else:
            reason, action = "Revoked for this user", "restore_user"
        modules.append({
            "key": key, "label": label, "blurb": blurb,
            "org_enabled": org_on or privileged,
            "user_access": user_on or privileged,
            "reason": reason,
            "fix_action": action,  # null | "grant_org" | "restore_user"
        })

    # Informational (non-org-module) access flags the People drawer should show:
    #   • Service Desk hub access   • Engineer app access
    role = (target.get("role") or "").lower()
    has_desk = bool(target.get("is_service_desk"))
    has_engineer = role == "engineer" or bool(target.get("is_engineer")) or bool(target.get("engineer_id"))
    if privileged:
        has_desk = True
    modules.append({
        "key": "service_desk", "label": "Service Desk", "blurb": "Service Desk hub (/service-desk)",
        "org_enabled": True, "user_access": has_desk or privileged,
        "reason": ("Full access — " + priv_label) if privileged else ("Service Desk member" if has_desk else "No Service Desk access"),
        "fix_action": None, "informational": True,
    })
    modules.append({
        "key": "engineer", "label": "Engineer app", "blurb": "Field engineer app (/engineer)",
        "org_enabled": True, "user_access": has_engineer or privileged,
        "reason": ("Full access — " + priv_label) if privileged else ("Engineer" if has_engineer else "Not an engineer"),
        "fix_action": None, "informational": True,
    })

    return {
        "organization_name": (org or {}).get("name") or "",
        "organization_id": (org or {}).get("id"),
        "is_privileged": privileged,
        "privilege_label": priv_label,
        "modules": modules,
    }


@router.post("/master-admin/users/{user_id}/module-access/{module}/grant")
async def grant_user_module_access(user_id: str, module: str, user: dict = Depends(get_current_user)):
    """One-click fix from the diagnostics row. Resolves whatever is blocking
    THIS module for THIS user:
      • org-level off  → enable the module for the organisation
      • user revoked   → clear the per-staff override that blocks it
    Returns the refreshed diagnostics so the drawer updates in place."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    if module not in {"operations", "memberships", "marketing", "crm"}:
        raise HTTPException(400, "Unknown module")

    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    is_crm_user = await db.crm_users.find_one({"id": user_id}, {"_id": 1}) is not None

    org_id = target.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None

    from utils.module_access import org_module_access, resolve_module_access
    org_on = bool(org_module_access(org).get(module))
    user_on = bool(resolve_module_access(target, org).get(module))

    label = _MODULE_META.get(module, (module.title(),))[0]
    actor = user.get("email") or "master_admin"
    org_name = (org or {}).get("name") or org_id or "organisation"
    target_name = target.get("full_name") or target.get("email") or user_id

    did = None
    # 1. Org-level off → enable the module for the org (merge + sync legacy fields).
    if org and not org_on:
        await _set_org_module_enabled(org_id, org, module, True)
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        did = "granted_org"
        await log_activity("module_access.grant_org",
                           f"Enabled {label} for {org_name}", actor, "organization", org_id)

    # 2. Per-staff override blocking → set it to allow (non-destructive merge).
    overrides = {**(target.get("module_overrides") or {})}
    if overrides.get(module) is False:
        overrides[module] = True
        coll = db.crm_users if is_crm_user else db.users
        await coll.update_one({"id": user_id}, {"$set": {"module_overrides": overrides}})
        target["module_overrides"] = overrides
        did = "restored_user" if did is None else "granted_org_and_restored_user"
        await log_activity("module_access.restore_user",
                           f"Restored {label} for {target_name}", actor, "user", user_id)

    if did is None and not (org_on and user_on):
        # Nothing to toggle (e.g. privileged user or no org). Still return state.
        did = "noop"

    payload = _module_access_payload(target, org)
    payload["result"] = did
    return payload


@router.post("/master-admin/users/{user_id}/module-access/{module}/revoke")
async def revoke_user_module_access(user_id: str, module: str,
                                    body: dict = Body(default={}),
                                    user: dict = Depends(get_current_user)):
    """Reverse a grant (the toast "Undo") or revoke access explicitly.
    ``scope`` selects what to undo: "org" disables the module for the org,
    "user" re-applies the per-staff block, "both" does both."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    if module not in {"operations", "memberships", "marketing", "crm"}:
        raise HTTPException(400, "Unknown module")
    scope = (body or {}).get("scope", "user")
    if scope not in {"org", "user", "both"}:
        raise HTTPException(400, "scope must be org | user | both")

    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    is_crm_user = await db.crm_users.find_one({"id": user_id}, {"_id": 1}) is not None

    org_id = target.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None
    label = _MODULE_META.get(module, (module.title(),))[0]
    actor = user.get("email") or "master_admin"
    org_name = (org or {}).get("name") or org_id or "organisation"
    target_name = target.get("full_name") or target.get("email") or user_id

    if scope in ("org", "both") and org:
        await _set_org_module_enabled(org_id, org, module, False)
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        await log_activity("module_access.revoke_org",
                           f"Disabled {label} for {org_name}", actor, "organization", org_id)

    if scope in ("user", "both"):
        overrides = {**(target.get("module_overrides") or {})}
        overrides[module] = False
        coll = db.crm_users if is_crm_user else db.users
        await coll.update_one({"id": user_id}, {"$set": {"module_overrides": overrides}})
        target["module_overrides"] = overrides
        await log_activity("module_access.revoke_user",
                           f"Revoked {label} for {target_name}", actor, "user", user_id)

    return _module_access_payload(target, org)


_ACCESS_ACTIONS = {
    "module_access.grant_org": ("granted", "org"),
    "module_access.revoke_org": ("revoked", "org"),
    "module_access.restore_user": ("restored", "user"),
    "module_access.revoke_user": ("revoked", "user"),
}


@router.get("/master-admin/users/{user_id}/module-access/audit")
async def get_user_module_access_audit(user_id: str, user: dict = Depends(get_current_user)):
    """Recent module-access changes for this user — both user-level changes
    (target_id == user_id) and org-level changes affecting their org."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)

    target = await db.users.find_one({"id": user_id}, {"_id": 0, "organization_id": 1})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "organization_id": 1})
    if not target:
        raise HTTPException(404, "User not found")
    org_id = target.get("organization_id")

    target_ids = [user_id] + ([org_id] if org_id else [])
    rows = await db.admin_activity_log.find(
        {"action": {"$in": list(_ACCESS_ACTIONS.keys())}, "target_id": {"$in": target_ids}},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(15)

    events = [{
        "action": r.get("action"),
        "verb": _ACCESS_ACTIONS.get(r.get("action"), ("changed", ""))[0],
        "level": _ACCESS_ACTIONS.get(r.get("action"), ("", "user"))[1],
        "details": r.get("details"),
        "admin_email": r.get("admin_email"),
        "timestamp": r.get("timestamp"),
    } for r in rows]
    return {"events": events}


async def _set_org_module_enabled(org_id: str, org: dict, module: str, enabled: bool) -> None:
    """Toggle a module's org-level entitlement, keeping the legacy
    ``enabled_modules`` array and ``portal_type`` in sync (single source of
    truth shared with the Feature Control panel)."""
    modules = {**(org.get("modules") or {})}
    existing = modules.get(module) or {}
    entry = {**existing, "enabled": enabled, "tier": existing.get("tier", "pro")}
    if module == "crm" and enabled and not (entry.get("business_enabled") or entry.get("leisure_enabled")):
        entry["leisure_enabled"] = True  # default to the gym/leisure CRM mode
    modules[module] = entry
    enabled_list = [k for k, v in modules.items() if isinstance(v, dict) and v.get("enabled")]
    derived = [m for m in ALL_MODULE_IDS if m in enabled_list] or ["operations"]
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"modules": modules, "enabled_modules": derived,
                  "portal_type": _derive_portal_type(derived)}},
    )




# Iter 222 — assigning the "Master Admin" role is BRAND-AWARE. For a user
# in a Pulse-Fitness org it provisions a data-scoped *Pulse* Master Admin
# (role=pulse_master_admin, is_pulse_admin=True) — same Master Admin
# dashboard + org impersonation, but limited to Pulse-visible data. For a
# Pulse Fitness-internal org it stays a full platform admin (is_master_admin).
_PULSE_ACCOUNT_TYPES = ("pulse_pro", "pulse_lite", "pulse")
_PULSE_BRAND_VALUES = ("pulse", "pulse_fitness")


def _org_is_pulse(org: Optional[dict]) -> bool:
    if not org:
        return False
    return (
        org.get("account_type") in _PULSE_ACCOUNT_TYPES
        or (org.get("brand") or "").strip().lower() in _PULSE_BRAND_VALUES
    )



# ───────────── add user to organization ─────────────

@router.post("/master-admin/organizations/{org_id}/users")
async def add_user_to_organization(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Add a user to an existing organisation. Routes to correct collection based on portal_type."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    email = (body.get("email") or "").strip().lower()
    full_name = (body.get("full_name") or "").strip()
    password = body.get("password", "")
    role = body.get("role", "staff")
    # Iter 215ev — when no password is supplied we issue the user an
    # invite-link instead. They set their own password on first visit.
    # Master admin never handles the plaintext. See also
    # /master-admin/users/{user_id}/invite-link for re-issuing.
    invite_mode = not password
    if not email or not full_name:
        raise HTTPException(status_code=400, detail="email and full_name are required")

    # Iter 216h25 — return existing user_id + collection in the 409
    # payload so the frontend toast can render a "Jump to this user"
    # link directly into People → Directory drawer.
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1})
    collection = "users"
    if not existing:
        existing = await db.crm_users.find_one({"email": email}, {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1})
        collection = "crm_users"
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "user_exists",
                "message": f"User {email} already exists",
                "user_id": existing.get("id"),
                "full_name": existing.get("full_name"),
                "organization_id": existing.get("organization_id"),
                "collection": collection,
                "email": email,
            },
        )

    user_id = str(uuid.uuid4())
    # In invite mode we store a random high-entropy placeholder so the
    # row is valid; the user will overwrite it via the /auth/reset-password
    # endpoint when they follow the invite link.
    effective_password = password or secrets.token_urlsafe(32)
    # Iter 216k — `master_admin` role grants platform-wide access. The
    # user still belongs to the org doc (so they appear in its Users
    # tab and can switch context to it) but is_master_admin=True
    # elevates them in every guard. We persist the role as 'owner' on
    # the org-scoped fields so existing queries that look at role keep
    # working, and stamp is_master_admin separately.
    storage_role = "owner" if role == "master_admin" else role
    if role == "engineer":
        # Iter 236 — Engineers ALWAYS live in the service-portal `users`
        # collection (get_current_user / the Engineer App authenticate
        # against it) regardless of the org's portal_type — a CRM-only
        # org like Pulse Fitness would otherwise create them in
        # crm_users where they could never sign into the Engineer App.
        # The Iter-227 provisioning sync then creates an active
        # `svc_engineers` row, which is what unlocks the Engineer App
        # via the internal_engineer bypass (no £30/mo Partner plan for
        # direct employees).
        from utils.auth import hash_password
        now = datetime.now(timezone.utc).isoformat()
        await db.users.insert_one({
            "id": user_id, "email": email, "full_name": full_name,
            "password": hash_password(effective_password),
            "organization_id": org["id"], "role": "engineer",
            "account_type": org.get("account_type", "full"),
            "created_at": now,
        })
        collection = "Service Portal"
        from routes.account import _sync_engineer_provisioning
        await _sync_engineer_provisioning({
            "id": user_id, "organization_id": org["id"], "role": "engineer",
            "full_name": full_name, "email": email,
        })
    else:
        collection = await _create_org_user(org, email, full_name, effective_password, storage_role, user_id)
    if role == "master_admin":
        # _create_org_user returns "Service Portal" or "CRM", not collection names
        target_coll = db.users if collection == "Service Portal" else db.crm_users
        if _org_is_pulse(org):
            # Pulse-scoped delegated admin — NOT a full platform admin.
            await target_coll.update_one(
                {"id": user_id},
                {"$set": {"role": "pulse_master_admin", "is_pulse_admin": True,
                          "is_master_admin": False, "company_name": "Pulse Fitness"}},
            )
        else:
            await target_coll.update_one(
                {"id": user_id},
                {"$set": {"is_master_admin": True, "role": "owner"}},
            )

    # Iter 280 — module access chosen at creation time. The Add-User dialog
    # sends a `module_overrides` map ({operations:true, crm:false, ...}); we
    # persist it verbatim (validated against the known keys) so the created
    # user's effective access matches exactly what the admin ticked, and the
    # People-drawer "Module access" view agrees with the create form.
    raw_overrides = body.get("module_overrides")
    if isinstance(raw_overrides, dict) and role not in ("master_admin", "owner"):
        from utils.module_access import allowed_module_keys
        keys = allowed_module_keys(org)
        overrides = {k: bool(v) for k, v in raw_overrides.items() if k in keys}
        if overrides:
            await db.users.update_one({"id": user_id}, {"$set": {"module_overrides": overrides}})
            await db.crm_users.update_one({"id": user_id}, {"$set": {"module_overrides": overrides}})

    invite_url = None
    invite_expires_at = None
    if invite_mode:
        # Mint a 72h invite token so the UI can surface a copy-able link
        # straight back (for WhatsApp / manual email until Resend DNS
        # verification is done).
        token = secrets.token_urlsafe(32)
        invite_expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user_id, "email": email,
            "expires_at": invite_expires_at, "used": False, "kind": "invite",
            "issued_by": user.get("email", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
        invite_url = f"{frontend_url}/reset-password?token={token}"

    await log_activity("user_added_to_org", f"Added {email} to {org['name']} ({collection}){' [invite]' if invite_mode else ''}", user["email"], "user", user_id)
    return {
        "id": user_id, "email": email, "full_name": full_name,
        "role": role, "portal": collection,
        "invite_mode": invite_mode,
        "invite_url": invite_url,
        "invite_expires_at": invite_expires_at,
    }


# ───────────── users list with merge + enrichment ─────────────

async def _scope_user_filter(user: dict, brand: str) -> dict:
    """Build the org-scoped filter for the user list:
       Pulse-only admin → only Pulse-visible orgs;
       brand picker     → intersect with the selected brand."""
    pulse_org_ids: Optional[set] = None
    if is_pulse_only(user):
        pulse_org_docs = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
            {"_id": 0, "id": 1},
        ).to_list(length=None)
        pulse_org_ids = {o["id"] for o in pulse_org_docs}
        user_filter: dict = {"organization_id": {"$in": list(pulse_org_ids)}}
    else:
        user_filter = {}

    from utils.brand_filter import merge_brand_filter, normalise_brand
    canonical_brand = normalise_brand(brand)
    if canonical_brand != "all":
        org_brand_filter = merge_brand_filter({}, brand, collection="organizations")
        if org_brand_filter:
            brand_org_docs = await db.organizations.find(
                org_brand_filter, {"_id": 0, "id": 1},
            ).to_list(length=None)
            brand_org_ids = {o["id"] for o in brand_org_docs}
            if pulse_org_ids is not None:
                brand_org_ids &= pulse_org_ids
            user_filter["organization_id"] = {"$in": list(brand_org_ids) or [""]}
    return user_filter


def _merge_users_by_email(sp_users: list, crm_list: list) -> list:
    """Iter 215ev — dedupe by email so a single human that exists in both
    `users` (Service Portal) and `crm_users` (CRM) renders as ONE row.
    Service Portal row is the primary (owns disabled/archived state)."""
    merged_by_email: dict = {}
    for u in sp_users:
        k = (u.get("email") or "").lower()
        u = dict(u)
        u["portals"] = ["service_portal"]
        u["user_type"] = "service_portal"
        merged_by_email[k] = u
    for u in crm_list:
        k = (u.get("email") or "").lower()
        if k in merged_by_email:
            existing = merged_by_email[k]
            if "crm" not in existing.get("portals", []):
                existing["portals"].append("crm")
            if not existing.get("avatar_url") and u.get("avatar_url"):
                existing["avatar_url"] = u["avatar_url"]
            # Iter 281 — if the Service Portal row has no org (e.g. a Service
            # Desk agent provisioned from a CRM contact before the org-preserve
            # fix), adopt the CRM row's org so the person still shows under
            # their organisation instead of vanishing to "N/A".
            if not existing.get("organization_id") and u.get("organization_id"):
                existing["organization_id"] = u["organization_id"]
        else:
            u = dict(u)
            u["portals"] = ["crm"]
            u["user_type"] = "crm"
            merged_by_email[k] = u
    return list(merged_by_email.values())


async def _fan_pulse_platform_admins(all_users: list) -> list:
    """Iter 216g — Pulse Platform Admins can be ATTACHED to one or more orgs
    via `organization_memberships`. Fan a virtual row per (admin × org) so
    the existing UI filter `users.filter(u => u.organization_id === orgId)`
    works without changes."""
    pulse_with_membership = await db.users.find(
        {"role": "pulse_master_admin", "organization_memberships": {"$exists": True, "$ne": []}},
        {"_id": 0, "password": 0, "password_hash": 0},
    ).to_list(500)
    seen_keys = {
        ((u.get("email") or "").lower(), u.get("organization_id") or "")
        for u in all_users
    }
    for admin in pulse_with_membership:
        email = (admin.get("email") or "").lower()
        for oid in admin.get("organization_memberships") or []:
            if (email, oid) in seen_keys:
                continue
            row = dict(admin)
            row["organization_id"] = oid
            row["portals"] = list(set((row.get("portals") or []) + ["service_portal", "crm"]))
            row["user_type"] = "pulse_master_admin"
            row["is_pulse_master_admin"] = True
            row["display_role"] = "Pulse Platform Admin"
            all_users.append(row)
            seen_keys.add((email, oid))
    return all_users


async def _enrich_with_orgs(all_users: list) -> None:
    """Tier-3.5 N+1 fix: batch fetch all referenced orgs in one query."""
    org_ids = {u.get("organization_id") for u in all_users if u.get("organization_id")}
    orgs = await db.organizations.find(
        {"id": {"$in": list(org_ids)}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "enabled_modules": 1, "account_type": 1},
    ).to_list(length=None)
    org_map = {o["id"]: o for o in orgs}
    for u in all_users:
        org = org_map.get(u.get("organization_id"))
        u["organization_name"] = org.get("name", "") if org else "N/A"
        u["org_status"] = org.get("status", "active") if org else "N/A"
        # Iter 216h197 — Portal pills used to be derived from the existence
        # of a `crm_users` row, which only exists after the user has first
        # cross-logged-in. That broke Lee's pills the moment we purged test
        # data: the OWNER showed only "Service Portal" even though his org
        # has CRM enabled. Recompute pills from actual module access:
        #   • service_portal  → everyone who has a `users` row
        #   • crm             → org has `crm` in enabled_modules OR
        #                        legacy account_type='full' OR
        #                        user is master_admin / pulse_master_admin
        #   • pulse_platform  → user is pulse_master_admin
        enabled_modules = (org or {}).get("enabled_modules") or []
        account_type = (org or {}).get("account_type") or u.get("account_type") or ""
        is_master = bool(u.get("is_master_admin")) or u.get("role") == "pulse_master_admin"
        portals = list(u.get("portals") or [])
        if "service_portal" not in portals and u.get("user_type") != "crm":
            portals.append("service_portal")
        crm_enabled = (
            "crm" in enabled_modules
            or account_type == "full"
            or account_type == "pulse_pro"
            or account_type == "lite"
            or is_master
        )
        if crm_enabled and "crm" not in portals:
            portals.append("crm")
        if is_master and "pulse_platform" not in portals:
            portals.append("pulse_platform")
        u["portals"] = portals


async def _enrich_with_module_access(all_users: list) -> None:
    """Resolve each person's effective module entitlement (operations,
    memberships, marketing, crm) for the Master Admin "Org People" directory,
    plus surface a single job_title field. Batch-fetches the referenced orgs
    once (full docs so trial/modules config resolves accurately)."""
    if not all_users:
        return
    from utils.module_access import MODULE_KEYS, resolve_module_access
    org_ids = {u.get("organization_id") for u in all_users if u.get("organization_id")}
    orgs = await db.organizations.find({"id": {"$in": list(org_ids)}}, {"_id": 0}).to_list(length=None)
    org_map = {o["id"]: o for o in orgs}
    for u in all_users:
        org = org_map.get(u.get("organization_id"))
        try:
            eff = resolve_module_access(u, org)
        except Exception:  # never let a single bad record break the list
            eff = {}
        u["module_access"] = {k: bool(eff.get(k)) for k in MODULE_KEYS}
        u["job_title"] = (u.get("job_title") or u.get("primary_role") or "").strip()


async def _enrich_job_titles(all_users: list) -> None:
    """Backfill an empty `job_title` from the org's staffing records
    (`staff_members.primary_role`), matched by user_id then email, so the
    Org People directory is populated automatically instead of showing '—'."""
    if not all_users:
        return
    need = [u for u in all_users if not (u.get("job_title") or "").strip()]
    if not need:
        return
    org_ids = {u.get("organization_id") for u in all_users if u.get("organization_id")}
    staff = await db.staff_members.find(
        {"organization_id": {"$in": list(org_ids)}},
        {"_id": 0, "email": 1, "user_id": 1, "primary_role": 1},
    ).to_list(length=None)
    by_uid = {s["user_id"]: s for s in staff if s.get("user_id")}
    by_email = {(s.get("email") or "").lower(): s for s in staff if s.get("email")}
    for u in need:
        s = by_uid.get(u.get("id")) or by_email.get((u.get("email") or "").lower())
        if s:
            u["job_title"] = (s.get("primary_role") or "").strip()


async def _enrich_partner_engineers(all_users: list) -> None:
    """Iter 220p — flag Partner Engineers so the People Directory shows
    them as 'Partner Engineer' on the Engineer App rather than as generic
    'Staff' on the Operations / Service Portal.

    A user is a Partner Engineer if their `users` row carries the
    `is_partner_engineer` flag / `engineer_partner` role / `partner_engineer`
    account_type, OR they're linked to a row in the `partner_engineers`
    collection (matched by user_id or email). The collection cross-check
    catches engineers whose `users` row predates the flag (e.g. existing
    production accounts that haven't re-logged-in since the flag shipped).
    """
    if not all_users:
        return
    pe_docs = await db.partner_engineers.find(
        {"status": {"$nin": ["pending", "rejected", "declined", "withdrawn"]}},
        {"_id": 0, "email": 1, "user_id": 1},
    ).to_list(length=None)
    pe_emails = {(d.get("email") or "").lower() for d in pe_docs if d.get("email")}
    pe_user_ids = {d.get("user_id") for d in pe_docs if d.get("user_id")}
    for u in all_users:
        email = (u.get("email") or "").lower()
        is_pe = (
            bool(u.get("is_partner_engineer"))
            or u.get("role") == "engineer_partner"
            or u.get("account_type") == "partner_engineer"
            or (email and email in pe_emails)
            or (u.get("id") and u.get("id") in pe_user_ids)
        )
        if not is_pe:
            continue
        u["is_partner_engineer"] = True
        u["display_role"] = "Partner Engineer"
        # Engineers operate in the Engineer App, not the Operations /
        # Service Portal — swap the portal chip so the directory is honest.
        portals = [p for p in (u.get("portals") or []) if p != "service_portal"]
        if "engineer_app" not in portals:
            portals.append("engineer_app")
        u["portals"] = portals


async def _enrich_with_invited_role(all_users: list) -> None:
    """Iter 216h3 — flag users whose accepted invite role differs from
    their current role so the People Directory shows a warning badge."""
    pairs = [(u.get("email"), u.get("organization_id")) for u in all_users if u.get("email") and u.get("organization_id")]
    if not pairs:
        return
    emails = list({p[0] for p in pairs})
    org_ids_for_invites = list({p[1] for p in pairs})
    invites = await db.invites.find(
        {
            "email": {"$in": emails},
            "organization_id": {"$in": org_ids_for_invites},
            "status": "accepted",
        },
        {"_id": 0, "email": 1, "organization_id": 1, "role": 1, "accepted_at": 1, "created_at": 1},
    ).to_list(length=None)
    invite_lookup: dict = {}
    for inv in invites:
        key = ((inv.get("email") or "").lower(), inv.get("organization_id") or "")
        existing = invite_lookup.get(key)
        ts = inv.get("accepted_at") or inv.get("created_at") or ""
        existing_ts = (existing or {}).get("_ts", "")
        if not existing or ts > existing_ts:
            invite_lookup[key] = {**inv, "_ts": ts}
    for u in all_users:
        key = ((u.get("email") or "").lower(), u.get("organization_id") or "")
        inv = invite_lookup.get(key)
        if inv and inv.get("role") and inv["role"] != u.get("role"):
            u["invited_role"] = inv["role"]


async def _enrich_with_pending_invite(all_users: list) -> None:
    """Iter 216h29 — surface `invite_pending` block on users whose most
    recent password_reset_tokens entry is still unused AND unexpired."""
    user_ids = [u.get("id") for u in all_users if u.get("id")]
    if not user_ids:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    pending_cursor = db.password_reset_tokens.find(
        {
            "user_id": {"$in": user_ids},
            "used": False,
            "expires_at": {"$gt": now_iso},
        },
        {"_id": 0, "user_id": 1, "token": 1, "expires_at": 1, "created_at": 1, "issued_by": 1, "kind": 1},
    ).sort("created_at", -1)
    latest_per_user: dict = {}
    async for tok in pending_cursor:
        uid = tok.get("user_id")
        if uid and uid not in latest_per_user:
            latest_per_user[uid] = tok
    if not latest_per_user:
        return
    now_dt = datetime.now(timezone.utc)
    for u in all_users:
        tok = latest_per_user.get(u.get("id"))
        if not tok:
            continue
        try:
            exp_dt = datetime.fromisoformat(tok["expires_at"])
        except Exception:  # noqa: BLE001
            continue
        delta = exp_dt - now_dt
        hours_left = max(0, int(delta.total_seconds() // 3600))
        u["invite_pending"] = {
            "expires_at": tok["expires_at"],
            "issued_at":  tok.get("created_at"),
            "issued_by":  tok.get("issued_by"),
            "hours_left": hours_left,
            "kind":       tok.get("kind", "invite"),
        }


async def _append_no_login_staff(all_users: list) -> list:
    """Surface Staffing staff who have no platform/CRM login yet, so Master
    Admin shows the WHOLE team with a 'No login' status + invite affordance.
    Also tags every existing row with login_status='active'."""
    for u in all_users:
        u.setdefault("login_status", "active")
        u.setdefault("is_staff_record", False)
    known_emails = {(u.get("email") or "").lower() for u in all_users if u.get("email")}
    known_ids = {u.get("id") for u in all_users}
    org_ids = {u.get("organization_id") for u in all_users if u.get("organization_id")}
    if not org_ids:
        return all_users
    try:
        from routes.staffing import _platform_role_from_staff_role
    except Exception:
        def _platform_role_from_staff_role(_r):
            return "staff"
    staff = await db.staff_members.find(
        {"organization_id": {"$in": list(org_ids)}, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "organization_id": 1,
         "primary_role": 1, "job_title": 1, "user_id": 1},
    ).to_list(3000)
    for s in staff:
        em = (s.get("email") or "").lower()
        if (em and em in known_emails) or (s.get("user_id") and s.get("user_id") in known_ids):
            continue
        all_users.append({
            "id": f"staff:{s['id']}",
            "staff_id": s["id"],
            "full_name": s.get("full_name") or em or "Unnamed",
            "email": s.get("email") or "",
            "organization_id": s.get("organization_id"),
            "role": _platform_role_from_staff_role(s.get("primary_role")),
            "job_title": s.get("job_title") or s.get("primary_role") or "",
            "login_status": "none",
            "is_staff_record": True,
            "disabled": False,
        })
    return all_users



@router.get("/master-admin/users")
async def get_all_users(user: dict = Depends(get_current_user), brand: str = "all"):
    require_master_admin(user)
    user_filter = await _scope_user_filter(user, brand)

    sp_users = await db.users.find(user_filter, {"_id": 0, "password": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    crm_list = await db.crm_users.find(user_filter, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(1000)

    all_users = _merge_users_by_email(sp_users, crm_list)
    all_users = await _fan_pulse_platform_admins(all_users)
    all_users = await _append_no_login_staff(all_users)
    await _enrich_with_orgs(all_users)
    await _enrich_with_module_access(all_users)
    await _enrich_job_titles(all_users)
    await _enrich_partner_engineers(all_users)
    await _enrich_with_invited_role(all_users)
    await _enrich_with_pending_invite(all_users)
    return {"users": all_users}


# ───────────── edit, disable, archive ─────────────

@router.put("/master-admin/users/{user_id}/edit")
async def admin_edit_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Master admin edits user details: name, email, role, job_title, module_overrides."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    allowed = {"full_name", "email", "role", "job_title", "phone", "module_overrides", "allowed_site_ids"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "email" in updates:
        updates["email"] = updates["email"].lower().strip()

    if "allowed_site_ids" in updates:
        raw = updates["allowed_site_ids"] or []
        if not isinstance(raw, list):
            raise HTTPException(400, "allowed_site_ids must be an array")
        updates["allowed_site_ids"] = [str(x) for x in raw if x]
        updates["permissions_updated_at"] = datetime.now(timezone.utc).isoformat()

    if "module_overrides" in updates:
        from utils.module_access import allowed_module_keys
        raw = updates["module_overrides"] or {}
        if not isinstance(raw, dict):
            raise HTTPException(400, "module_overrides must be an object")
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "organization_id": 1})
        target_org = await db.organizations.find_one(
            {"id": (target_user or {}).get("organization_id")}, {"_id": 0, "account_type": 1, "is_mod": 1},
        )
        keys = allowed_module_keys(target_org)
        updates["module_overrides"] = {k: bool(v) for k, v in raw.items() if k in keys}

    if not updates:
        raise HTTPException(400, "No valid fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if updates.get("role") == "master_admin":
        # Iter 222 — brand-aware elevation + remember the previous role so
        # a later demotion can restore it. Promotes EXISTING staff in place
        # (keeps their password). Pulse-org users become a Pulse Master
        # Admin (data-scoped); Pulse Fitness-org users become a full admin.
        target_u = (
            await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1, "organization_id": 1})
            or await db.crm_users.find_one({"id": user_id}, {"_id": 0, "role": 1, "organization_id": 1})
        ) or {}
        target_org = None
        if target_u.get("organization_id"):
            target_org = await db.organizations.find_one(
                {"id": target_u["organization_id"]},
                {"_id": 0, "account_type": 1, "brand": 1},
            )
        prev_role = target_u.get("role")
        if prev_role and prev_role not in ("master_admin", "pulse_master_admin"):
            updates["pulse_admin_previous_role"] = prev_role
        if _org_is_pulse(target_org):
            updates["role"] = "pulse_master_admin"
            updates["is_pulse_admin"] = True
            updates["is_master_admin"] = False
        else:
            updates["role"] = "owner"
            updates["is_master_admin"] = True
    elif updates.get("role") in ("owner", "manager", "staff", "engineer"):
        # Demotion away from any master-admin role — strip elevated flags so
        # access is fully revoked (active sessions are killed below).
        updates["is_pulse_admin"] = False
        updates["is_master_admin"] = False

    result = await db.users.update_one({"id": user_id}, {"$set": updates})
    if result.modified_count == 0:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": updates})
    if result.modified_count == 0:
        raise HTTPException(404, "User not found")
    # Iter 220au · F-19 — kill every active session for the edited user
    # whenever a field that affects authorisation has been mutated.
    # Without this, a user whose role was just demoted could keep
    # using their existing access token for the rest of its TTL.
    _rbac_keys = {"role", "is_master_admin", "is_pulse_admin", "allowed_site_ids",
                  "module_overrides", "permissions", "disabled", "archived"}
    if _rbac_keys & set(updates.keys()):
        from utils.auth_guards import revoke_user_sessions
        await revoke_user_sessions(user_id, reason="role_or_permissions_changed")
    if "role" in updates:
        # Iter 236 — keep `svc_engineers` in lock-step with role changes
        # made from the master-admin dialog (same Iter-227 sync the
        # org-level team manager uses): role→engineer provisions an
        # active engineer record (unlocks the Engineer App); any other
        # role deactivates it.
        target = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "id": 1, "organization_id": 1, "role": 1,
             "full_name": 1, "email": 1, "phone": 1},
        )
        if target:
            from routes.account import _sync_engineer_provisioning
            await _sync_engineer_provisioning(target)
    await log_activity("user_edited", f"Edited user {user_id}: {list(updates.keys())}", user["email"], "user", user_id)
    return {"success": True}


@router.put("/master-admin/users/{user_id}/disable")
async def disable_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    disabled = body.get("disabled", True)
    result = await db.users.update_one({"id": user_id}, {"$set": {"disabled": disabled}})
    if result.modified_count == 0:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"disabled": disabled}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    if disabled:
        from utils.auth_guards import revoke_user_sessions
        await revoke_user_sessions(user_id, reason="user_disabled")
    await log_activity("user_disable" if disabled else "user_enable", f"{'Disabled' if disabled else 'Enabled'} user {user_id}", user["email"], "user", user_id)
    return {"success": True}


@router.put("/master-admin/users/{user_id}/archive")
async def archive_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    archived = body.get("archived", True)
    result = await db.users.update_one({"id": user_id}, {"$set": {"archived": archived}})
    if result.modified_count == 0:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"archived": archived}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    if archived:
        from utils.auth_guards import revoke_user_sessions
        await revoke_user_sessions(user_id, reason="user_archived")
    action = "user_archived" if archived else "user_unarchived"
    await log_activity(action, f"{'Archived' if archived else 'Unarchived'} user {user_id}", user["email"], "user", user_id)
    return {"success": True}


@router.post("/master-admin/users/{user_id}/unlock")
async def unlock_user(user_id: str, user: dict = Depends(get_current_user)):
    """Manually clear a login lockout / rate-limit for a user so they can sign
    in immediately (instead of waiting for the 15-minute auto-unlock)."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    from utils.security import clear_failed_logins, clear_login_rate_limits

    target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    email = (target.get("email") or "").strip()
    if email:
        clear_failed_logins(email)        # in-memory account lockout + counter
    clear_login_rate_limits()             # in-memory per-IP login rate limits
    # Clear any persisted lockout flags on the user doc(s).
    unset = {"$unset": {"lockout_until": "", "failed_login_attempts": "", "locked_until": ""}}
    await db.users.update_one({"id": user_id}, unset)
    await db.crm_users.update_one({"id": user_id}, unset)
    await log_activity("user_unlock", f"Unlocked login for {email or user_id}", user["email"], "user", user_id)
    return {"success": True, "email": email}


# ───────────── hard-delete with cascade ─────────────

_DELETE_CASCADE_SPECS = [
    ("issues",                "user_or_raised_by"),
    ("notes",                 "user_or_created_by"),
    ("files",                 "uploaded_by"),
    ("audit_logs",            "user_or_target_id"),
    ("activity_log",          "user_or_target_id"),
    ("notifications",         "user_id"),
    ("invites",               "email"),
    ("password_reset_tokens", "user_id"),
    ("ui_error_events",       "user_id"),
    ("security_audit_log",    "actor_or_target_id"),
    ("crm_audits",            "user_id"),
    ("member_documents",      "uploaded_by"),
    ("trust_events",          "user_id"),
    ("api_keys",              "user_id"),
    ("mfa_secrets",           "user_id"),
    ("refresh_tokens",        "user_id"),
    ("user_sessions",         "user_id"),
    # Iter 236 — internal-engineer provisioning row (id == user_id).
    # Without this, hard-deleting an engineer leaves an orphaned ACTIVE
    # svc_engineers row behind.
    ("svc_engineers",         "id"),
]


def _build_cascade_query(shape: str, user_id: str, target_email: str) -> dict:
    if shape == "user_or_raised_by":
        return {"$or": [{"user_id": user_id}, {"raised_by": user_id}]}
    if shape == "user_or_created_by":
        return {"$or": [{"user_id": user_id}, {"created_by": user_id}]}
    if shape == "user_or_target_id":
        return {"$or": [{"user_id": user_id}, {"target_id": user_id}]}
    if shape == "actor_or_target_id":
        return {"$or": [{"actor_id": user_id}, {"target_id": user_id}]}
    if shape == "email":
        return {"email": target_email}
    return {shape: user_id}


@router.delete("/master-admin/users/{user_id}")
async def hard_delete_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Permanently delete an archived user and cascade their personal data.

    Strict rules:
      • Caller must be master admin OR an owner/manager of the user's org.
      • Target must already be `archived=True` (force a soft-delete first).
      • Master admins cannot be hard-deleted (avoids platform lockout).
      • The sole owner of an org cannot be hard-deleted (avoids orphan org).
      • The dedicated `admin@pulsefitness.ai` is never deletable.
      • Caller must echo back the target's email in `confirm_email`.

    Cascade scope (best-effort, never blocks the delete on a single failure):
      issues, audit_logs, files, activity_log, notifications, invites,
      password_reset_tokens, ui_error_events, security_audit_log,
      crm_audits, notes, member_documents, trust_events,
      api_keys, mfa_secrets, refresh_tokens, user_sessions.
    """
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    is_crm = False
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        is_crm = True

    # Authorization
    is_admin = bool(user.get("is_master_admin"))
    if not is_admin:
        same_org = (
            user.get("organization_id")
            and user.get("organization_id") == target.get("organization_id")
        )
        if not same_org or user.get("role") not in ("owner", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Only master admin, or an owner/manager in the same organisation, can hard-delete users.",
            )

    # Hard guards
    if not target.get("archived"):
        raise HTTPException(status_code=400, detail="User must be archived first. Archive then delete.")
    if target.get("is_master_admin"):
        raise HTTPException(status_code=400, detail="Master admin accounts cannot be hard-deleted.")
    if (target.get("email") or "").lower() == "admin@pulsefitness.ai":
        raise HTTPException(status_code=400, detail="The default platform admin account cannot be deleted.")

    if not is_crm and target.get("role") == "owner" and target.get("organization_id"):
        siblings = await db.users.count_documents({
            "organization_id": target["organization_id"],
            "role": "owner",
            "id": {"$ne": user_id},
            "archived": {"$ne": True},
        })
        if siblings == 0:
            raise HTTPException(
                status_code=400,
                detail="This is the only owner of the organisation. Promote another user before deleting.",
            )

    confirm_email = (body.get("confirm_email") or "").strip().lower()
    if confirm_email != (target.get("email") or "").lower():
        raise HTTPException(status_code=400, detail="Confirmation email does not match the target user's email.")

    # Cascade
    cascade_summary: dict = {}
    target_email = (target.get("email") or "").lower()

    async def _safe_delete(coll_name: str, query: dict):
        try:
            res = await getattr(db, coll_name).delete_many(query)
            if res.deleted_count:
                cascade_summary[coll_name] = cascade_summary.get(coll_name, 0) + res.deleted_count
        except Exception as exc:
            logger.warning("Cascade delete on %s failed: %s", coll_name, exc)

    for coll, shape in _DELETE_CASCADE_SPECS:
        await _safe_delete(coll, _build_cascade_query(shape, user_id, target_email))

    coll = db.crm_users if is_crm else db.users
    res = await coll.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User no longer exists")

    try:
        await log_activity(
            "user_hard_deleted",
            f"Permanently deleted user {target_email} ({user_id}). Cascade: {cascade_summary}",
            user["email"], "user", user_id,
        )
    except Exception:  # noqa: BLE001
        pass
    logger.warning(
        "[hard-delete] user_id=%s email=%s by=%s cascade=%s",
        user_id, target_email, user.get("email"), cascade_summary,
    )
    return {
        "success": True,
        "deleted_user_id": user_id,
        "email": target_email,
        "cascade": cascade_summary,
    }


# ───────────── reset-password + impersonate ─────────────

@router.put("/master-admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    import bcrypt
    # P0.5 — generate a one-time cryptographic password for every reset.
    # Never reuse a shared default; the admin must communicate this via a
    # secure channel and the user is forced to change it at next login.
    temp_password = secrets.token_urlsafe(16)
    hashed = bcrypt.hashpw(temp_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    result = await db.users.update_one({"id": user_id}, {"$set": {"password": hashed, "password_reset_required": True}})
    target_email = None
    if result.modified_count > 0:
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1})
        target_email = (target or {}).get("email")
    else:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"password": hashed, "password_reset_required": True}})
        if result.modified_count > 0:
            target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "email": 1})
            target_email = (target or {}).get("email")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Iter 215bh — keep the org's "Primary contact login" reveal panel in
    # sync. If the user we just reset is the org's primary contact, write
    # the fresh temp_password back into the org doc so the Master Admin can
    # see (and copy) it from the reveal panel after the toast is gone.
    if target_email:
        await db.organizations.update_many(
            {"primary_contact_email": target_email.strip().lower()},
            {"$set": {
                "primary_contact_initial_password": temp_password,
                "primary_contact_password_changed": False,
            }},
        )

    await log_activity("password_reset", f"Reset password for user {user_id}", user["email"], "user", user_id)
    return {"success": True, "temp_password": temp_password, "user_email": target_email}


# ───────────── Iter 279 — login-access diagnostics + one-click repair ─────────────
# A user created in a CRM-capable org can end up ONLY in `crm_users`, so the
# standard portal login reports "unknown user" (the class of bug that locked
# out Robert Buckley). These endpoints let a master admin SEE which portal a
# person can actually sign into and REPAIR a CRM-only account in one click by
# mirroring a `users` row (bcrypt hash copied verbatim — identical algorithm —
# so the person keeps their existing password).

async def _login_access_payload(user_id: str) -> dict:
    sp = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email": 1, "active": 1, "disabled": 1, "archived": 1,
         "password": 1, "no_password_login": 1},
    )
    crm = await db.crm_users.find_one(
        {"id": user_id},
        {"_id": 0, "email": 1, "password": 1, "cross_login_provisioned": 1},
    )
    email = (sp or crm or {}).get("email", "")
    in_sp = sp is not None
    in_crm = crm is not None
    sp_blocked = bool(sp and (
        sp.get("active") is False or sp.get("disabled") or sp.get("archived")
        or sp.get("no_password_login")
    ))
    can_standard = in_sp and not sp_blocked and bool(sp.get("password"))
    needs_repair = in_crm and not in_sp
    placeholder = bool(crm and crm.get("cross_login_provisioned"))

    if not (in_sp or in_crm):
        reason = "No account row found for this user."
    elif needs_repair:
        reason = ("This account exists only in the CRM portal, so standard "
                  "sign-in (pulsefitness.ai/login) reports \u201cunknown user\u201d. "
                  "Repair to enable standard-portal login.")
    elif can_standard:
        reason = "Can sign in on the standard portal."
    elif sp_blocked:
        reason = "Standard-portal account exists but sign-in is blocked (disabled / archived / no-password)."
    else:
        reason = "Account present."

    return {
        "user_id": user_id,
        "email": email,
        "in_service_portal": in_sp,
        "in_crm": in_crm,
        "can_standard_login": can_standard,
        "can_crm_login": in_crm,
        "needs_repair": needs_repair,
        "password_placeholder": placeholder,
        "reason": reason,
    }


@router.get("/master-admin/users/{user_id}/login-access")
async def get_user_login_access(user_id: str, user: dict = Depends(get_current_user)):
    """Diagnostics for the People drawer: which portal(s) this person can
    actually sign into, and whether a CRM-only account needs repair."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    return await _login_access_payload(user_id)


@router.post("/master-admin/users/{user_id}/repair-login")
async def repair_user_login(user_id: str, user: dict = Depends(get_current_user)):
    """One-click fix for the "unknown user" login class: if the account
    lives only in `crm_users`, mirror a `users` row (copying the bcrypt hash
    verbatim) so standard-portal login works with the SAME password. Returns
    refreshed diagnostics so the drawer updates in place. Idempotent."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)

    sp = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1})
    crm = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
    did = "noop"
    if not sp and crm:
        org = None
        if crm.get("organization_id"):
            org = await db.organizations.find_one(
                {"id": crm["organization_id"]}, {"_id": 0, "account_type": 1},
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        mirrored = {
            "id": user_id,
            "email": (crm.get("email") or "").lower(),
            "full_name": crm.get("full_name") or crm.get("name") or "",
            "password": crm.get("password", ""),
            "organization_id": crm.get("organization_id"),
            "role": crm.get("role") or "staff",
            "account_type": (org or {}).get("account_type", "full"),
            "avatar_url": crm.get("avatar_url"),
            "created_at": crm.get("created_at") or now_iso,
            "cross_login_provisioned": True,
            "mirrored_from_crm_at": now_iso,
            "login_repaired_by": user.get("email", ""),
        }
        await db.users.insert_one(dict(mirrored))
        did = "mirrored_crm_to_service_portal"
        await log_activity(
            "login_access_repaired",
            f"Repaired standard-portal login for {mirrored['email']} (mirrored crm_users \u2192 users)",
            user.get("email", ""), "user", user_id,
        )
    elif not sp and not crm:
        raise HTTPException(status_code=404, detail="User not found")

    payload = await _login_access_payload(user_id)
    payload["result"] = did
    return payload


@router.get("/master-admin/engineers")
async def list_provisioned_engineers(user: dict = Depends(get_current_user)) -> dict:
    """Iter 227 — engineers a master / Pulse admin can "view as" for
    training & support. Lists active ``svc_engineers`` mappings joined
    with their organisation. Pulse Master Admins only see engineers
    within Pulse-visible orgs (their existing data scope); the Pulse Fitness
    master admin sees every engineer.
    """
    require_master_admin(user)
    query: dict = {"active": {"$ne": False}}
    if is_pulse_only(user):
        pulse_orgs = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
            {"_id": 0, "id": 1},
        ).to_list(length=None)
        scope_ids = [o["id"] for o in pulse_orgs]
        if not scope_ids:
            return {"engineers": []}
        query["organization_id"] = {"$in": scope_ids}

    rows = await db.svc_engineers.find(query, {"_id": 0}).sort("full_name", 1).to_list(length=500)
    org_ids = list({r.get("organization_id") for r in rows if r.get("organization_id")})
    org_names: dict[str, str] = {}
    if org_ids:
        async for o in db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1},
        ):
            org_names[o["id"]] = o.get("name") or ""
    engineers = [{
        "id": r.get("id"),
        "full_name": r.get("full_name") or "",
        "email": r.get("email") or "",
        "organization_id": r.get("organization_id") or "",
        "organization_name": org_names.get(r.get("organization_id"), ""),
        "verified": bool(r.get("verified")),
        "auto_provisioned": bool(r.get("auto_provisioned")),
    } for r in rows]
    return {"engineers": engineers}


@router.post("/master-admin/impersonate/{user_id}")
async def impersonate_user(user_id: str, request: Request, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    import jwt
    from utils.database import JWT_SECRET as _JWT_SECRET, JWT_ALGORITHM as _JWT_ALGO
    from utils.security_plus import new_jti
    jti = new_jti()
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    token = jwt.encode({
        "user_id": target["id"],
        "email": target["email"],
        "organization_id": target.get("organization_id", ""),
        "role": target.get("role", "member"),
        "impersonated_by": user["email"],
        "jti": jti,
        "exp": exp,
    }, _JWT_SECRET, algorithm=_JWT_ALGO)

    await log_activity("impersonate", f"Impersonated user {target['email']}", user["email"], "user", user_id)
    # Iter 220ax · F-28 — dedicated impersonation audit collection.
    # Captures actor + target + IP + UA + token jti so the session
    # can be killed later if needed.
    from utils.audit_log import record_impersonation_event
    await record_impersonation_event(
        actor=user, target_user_id=target["id"],
        target_email=target.get("email"),
        target_organization_id=target.get("organization_id"),
        token_jti=jti, expires_at=exp, request=request,
        reason="master_admin_impersonate",
    )
    return {"token": token, "user": target}


async def _issue_org_portal_token(org: dict, actor: dict, request: Request, grants: list | None = None) -> str:
    """Provision (idempotently) an impersonation-only owner in `org` and mint a
    short-lived, audited impersonation JWT for it. Shared by the dedicated
    Pulse Fitness button and the generic any-org portal switch."""
    org_id = org["id"]
    target = await db.users.find_one(
        {"organization_id": org_id, "role": "owner"}, {"_id": 0, "password": 0, "password_hash": 0})
    if not target:
        import uuid
        slug = (org.get("name") or "org").lower().replace(" ", "-")[:32]
        target = {
            "id": str(uuid.uuid4()),
            "email": f"portal+{org_id[:8]}@{slug}.portal",
            "full_name": org.get("name") or "Portal Owner",
            "name": org.get("name") or "Portal Owner",
            "organization_id": org_id,
            "role": "owner",
            "account_type": org.get("account_type") or "pulse_pro",
            "is_master_admin": False,
            "auto_provisioned": True,
            "no_password_login": True,  # impersonation-only; cannot sign in with a password
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(dict(target))

    import jwt
    from utils.database import JWT_SECRET as _JWT_SECRET, JWT_ALGORITHM as _JWT_ALGO
    from utils.security_plus import new_jti
    jti = new_jti()
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    token = jwt.encode({
        "user_id": target["id"],
        "email": target["email"],
        "organization_id": org_id,
        "role": target.get("role", "owner"),
        "impersonated_by": actor["email"],
        "imp_grants": grants or [],
        "jti": jti,
        "exp": exp,
    }, _JWT_SECRET, algorithm=_JWT_ALGO)

    await log_activity("portal_switch", f"Switched into {org.get('name')} portal", actor["email"], "organization", org_id)
    from utils.audit_log import record_impersonation_event
    await record_impersonation_event(
        actor=actor, target_user_id=target["id"],
        target_email=target.get("email"),
        target_organization_id=org_id,
        token_jti=jti, expires_at=exp, request=request,
        reason="org_portal_switch",
    )
    return token


@router.post("/master-admin/pulse-portal-login")
async def pulse_portal_login(request: Request, user: dict = Depends(get_current_user)):
    """Log a Pulse master admin straight into the Pulse Fitness (LTD) portal.

    Resolves the operator's REAL company robustly. Several near-duplicate orgs
    can exist ("Pulse Fitness", "Pulse Fitness Ltd", "Pulse Fitness AI", ...);
    a naive name=="Pulse Fitness" lookup landed the admin in a near-empty org
    that only showed Operations. We now prefer the genuine operator company
    (Ltd/Limited), then the pulse-fitness org with the MOST modules already
    enabled, excluding the internal "...AI" / "...Admin" orgs.
    """
    require_master_admin(user)
    # 1) An explicit pin always wins — set via the Org Cleanup tool. This makes
    #    the operator company deterministic and kills the "wrong org" bug class.
    org = await db.organizations.find_one({"is_operator_company": True}, {"_id": 0})
    if not org:
        # 2) Fall back to a heuristic across all "Pulse Fitness…" orgs.
        candidates = await db.organizations.find(
            {"name": {"$regex": "pulse\\s*fitness", "$options": "i"}}, {"_id": 0},
        ).to_list(50)
        if not candidates:
            raise HTTPException(status_code=404, detail="Pulse Fitness organisation not found")

        def _enabled_count_h(o: dict) -> int:
            mods = o.get("modules") or {}
            return sum(1 for v in mods.values() if isinstance(v, dict) and v.get("enabled"))

        def _rank(o: dict):
            name = (o.get("name") or "").strip().lower()
            is_internal = ("ai" in name.split()) or ("admin" in name)
            is_ltd = name.endswith("ltd") or name.endswith("limited") or " ltd" in name or " limited" in name
            return (
                0 if is_internal else 1,
                1 if is_ltd else 0,
                _enabled_count_h(o),
                o.get("user_count", 0) or 0,
            )

        org = sorted(candidates, key=_rank, reverse=True)[0]

    def _enabled_count(o: dict) -> int:
        mods = o.get("modules") or {}
        return sum(1 for v in mods.values() if isinstance(v, dict) and v.get("enabled"))

    # Self-heal: the chosen operator company must be a FULL platform with every
    # module enabled so the admin always lands on the complete operator
    # dashboard (idempotent — only writes when something is missing).
    full_modules = {
        k: {"enabled": True, "tier": "pro", "source": "admin"}
        for k in ("operations", "memberships", "marketing", "crm")
    }
    full_modules["crm"]["business_enabled"] = True
    if org.get("account_type") != "full" or _enabled_count(org) < 4:
        merged = {**(org.get("modules") or {})}
        for k, v in full_modules.items():
            merged[k] = {**(merged.get(k) or {}), **v}
        await db.organizations.update_one(
            {"id": org["id"]},
            {"$set": {"account_type": "full", "modules": merged}},
        )
        org = await db.organizations.find_one({"id": org["id"]}, {"_id": 0})
    token = await _issue_org_portal_token(org, user, request)
    return {"token": token, "organization_id": org["id"], "organization_name": org.get("name")}


@router.post("/master-admin/org-portal-login/{org_id}")
async def org_portal_login(org_id: str, request: Request, area: str = "operator", user: dict = Depends(get_current_user)):
    """Log a Pulse master admin into ANY organisation's operator portal as its
    owner (one-click client portal switch from the admin console).

    `area` picks which shell to grant for the impersonated session:
      operator (default) → main app; service_desk → Service Desk hub;
      inventory → Inventory & Distribution (also grants service_desk so the
      shared desk/asset data resolves). Grants are session-only JWT claims."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    grants = None
    if area == "service_desk":
        grants = ["service_desk"]
    elif area == "inventory":
        grants = ["service_desk", "inventory"]
    # Service Desk / Inventory are restricted to Pulse Fitness + dealer
    # partners + entitled orgs. Block impersonating a general leisure
    # customer into those shells (defence-in-depth behind the gated picker).
    if area in ("service_desk", "inventory") and not is_desk_inventory_entitled(org):
        raise HTTPException(
            status_code=403,
            detail="This organisation is not entitled to the Service Desk / Inventory modules.",
        )
    token = await _issue_org_portal_token(org, user, request, grants=grants)
    return {"token": token, "organization_id": org["id"], "organization_name": org.get("name"), "area": area}


@router.post("/master-admin/operator-portal-login")
async def operator_portal_login(request: Request, user: dict = Depends(get_current_user)):
    """Log a Pulse master admin into the Pulse Fitness OPERATOR COMPANY's portal
    (the org flagged is_operator_company — 'Pulse Fitness Ltd'), NOT the admin's
    own platform org. Backs the sidebar 'Pulse Fitness Portal' switch."""
    require_master_admin(user)
    org = await db.organizations.find_one({"is_operator_company": True}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="No Pulse Fitness operator company is configured.")
    token = await _issue_org_portal_token(org, user, request, grants=None)
    return {"token": token, "organization_id": org["id"], "organization_name": org.get("name"), "area": "operator"}


@router.post("/master-admin/inventory-access/grant")
async def grant_inventory_access(body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Grant the additive Inventory & Distribution right to an existing user."""
    require_master_admin(user)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    target = await db.users.find_one({"email": email}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {
        "is_inventory": True,
        "inventory_granted_at": now,
        "inventory_granted_by_email": user["email"],
    }
    if not target.get("organization_id") and not target.get("service_org_id"):
        svc_org = user.get("organization_id") or user.get("service_org_id")
        if svc_org:
            set_fields["service_org_id"] = svc_org
    await db.users.update_one({"id": target["id"]}, {"$set": set_fields})
    await log_activity("inventory_access_grant", f"Granted Inventory & Distribution to {email}", user["email"], "user", target["id"])
    return {"success": True, "email": email}


@router.post("/master-admin/inventory-access/revoke")
async def revoke_inventory_access(body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Revoke the Inventory & Distribution right from a user."""
    require_master_admin(user)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    target = await db.users.find_one({"email": email}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    await db.users.update_one({"id": target["id"]}, {"$set": {"is_inventory": False}})
    await log_activity("inventory_access_revoke", f"Revoked Inventory & Distribution from {email}", user["email"], "user", target["id"])
    return {"success": True, "email": email}
