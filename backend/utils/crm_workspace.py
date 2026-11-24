"""CRM workspace roles + action permissions (CRM vs Contract Management).

One CRM data layer, two workspaces. A user's workspace role decides which
workspace(s) they reach and which sensitive CRM actions the backend allows.
Applies to the operator company (Pulse Fitness Ltd) only; every other tenant
keeps its historical unrestricted CRM behaviour (role ``crm_user``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from utils.database import db

ROLE_LABELS = {
    "contract_coordinator": "Contract Coordinator",
    "sales_manager": "Sales Manager",
    "aftersales_manager": "Service & Aftersales Manager",
    "finance": "Finance",
    "admin": "Administrator",
}
ASSIGNABLE_ROLES = tuple(ROLE_LABELS.keys())
LEGACY_ROLE = "crm_user"

ALL_PERMISSIONS = {
    "workspace.crm", "workspace.contract_management",
    "contracts.read", "contracts.manage",
    "quotes.commercial", "quotes.mod", "quotes.maintenance",
    "renewals.review", "renewals.approve", "agreements.process",
    "service.read", "billing.prepare", "billing.reconcile",
    "finance.sync", "finance.post", "tasks.manage",
    "exceptions.approve", "reports.management",
    "pricing.commercial", "pricing.manage",
    "integrations.admin", "permissions.admin",
}

ROLE_PERMISSIONS = {
    "admin": set(ALL_PERMISSIONS),
    "aftersales_manager": {
        "workspace.crm", "workspace.contract_management",
        "contracts.read", "contracts.manage", "quotes.commercial", "quotes.mod",
        "quotes.maintenance", "renewals.review", "renewals.approve",
        "agreements.process", "service.read", "billing.prepare", "finance.sync",
        "tasks.manage", "exceptions.approve", "reports.management",
        "pricing.commercial",
    },
    "contract_coordinator": {
        "workspace.contract_management", "contracts.read", "contracts.manage",
        "quotes.maintenance", "renewals.review", "agreements.process",
        "service.read", "billing.prepare", "tasks.manage",
    },
    "sales_manager": {
        "workspace.crm", "contracts.read", "quotes.commercial", "quotes.mod",
        "service.read", "pricing.commercial", "renewals.review", "renewals.approve",
    },
    "finance": {
        "workspace.contract_management", "contracts.read", "service.read",
        "billing.prepare", "billing.reconcile", "finance.sync", "finance.post",
    },
    # Non-operator tenants: unchanged historical CRM behaviour.
    LEGACY_ROLE: set(ALL_PERMISSIONS) - {"workspace.contract_management"},
}

CM_ROLES = {"contract_coordinator", "aftersales_manager", "finance", "admin"}

# Initial coordinator list supplied by Pulse Fitness (applied once per email).
INITIAL_COORDINATORS = (
    "claire.johnson@pulsefitness.com",
    "becky.hassell@pulsefitness.com",
    "mandy.gosnell@pulsefitness.com",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_platform_admin(u: Optional[dict]) -> bool:
    u = u or {}
    return bool(u.get("is_master_admin") or u.get("is_pulse_admin")
                or (u.get("role") or "").lower() in ("pulse_master_admin", "master_admin"))


def derive_role(platform_user: dict) -> str:
    """Map the real platform role when no explicit workspace role is set."""
    if is_platform_admin(platform_user):
        return "admin"
    role = (platform_user.get("role") or "").lower()
    if role in ("owner", "org_owner", "admin") or platform_user.get("is_org_owner"):
        return "admin"
    if role in ("finance", "accounts", "accountant"):
        return "finance"
    return "sales_manager"


async def _operator_org_ids() -> set:
    rows = await db.organizations.find({"is_operator_company": True}, {"_id": 0, "id": 1}).to_list(20)
    return {r["id"] for r in rows if r.get("id")}


async def _apply_grant(platform_user: dict) -> Optional[str]:
    email = (platform_user.get("email") or "").lower().strip()
    if not email:
        return None
    grant = await db.crm_workspace_role_grants.find_one({"email": email, "applied": {"$ne": True}}, {"_id": 0})
    if not grant or grant.get("role") not in ASSIGNABLE_ROLES:
        return None
    await set_explicit_role(platform_user, grant["role"], actor="initial-coordinator-list")
    await db.crm_workspace_role_grants.update_one({"email": email}, {"$set": {"applied": True, "applied_at": _now()}})
    return grant["role"]


async def set_explicit_role(platform_user: dict, role: Optional[str], actor: str) -> None:
    """Persist (or clear) an explicit workspace role, with an audit row.

    A Contract-Management role also switches the CRM module on for that
    operator-company staffer, because CM lives inside CRM's entitlement.
    """
    updates: dict = {"crm_workspace_role": role, "crm_workspace_role_updated_at": _now()}
    overrides = platform_user.get("module_overrides") if isinstance(platform_user.get("module_overrides"), dict) else {}
    granted_by_ws = bool(platform_user.get("crm_override_from_workspace"))
    if role in CM_ROLES and overrides.get("crm") is not True:
        updates["module_overrides.crm"] = True
        updates["crm_override_from_workspace"] = True
        granted_by_ws = True
    elif role not in CM_ROLES and granted_by_ws:
        # Undo a CRM grant that only existed because of a CM role.
        updates["module_overrides.crm"] = False
        updates["crm_override_from_workspace"] = False
        granted_by_ws = False
    await db.users.update_one({"id": platform_user["id"]}, {"$set": updates})
    await db.crm_workspace_role_audit.insert_one({
        "user_id": platform_user["id"], "email": platform_user.get("email"),
        "from_role": platform_user.get("crm_workspace_role"), "to_role": role,
        "actor": actor, "at": _now(),
    })
    platform_user["crm_workspace_role"] = role
    platform_user["crm_override_from_workspace"] = granted_by_ws
    if "module_overrides.crm" in updates:
        platform_user["module_overrides"] = {**overrides, "crm": updates["module_overrides.crm"]}


async def resolve_workspace_role(platform_user: Optional[dict], op_ids: Optional[set] = None) -> str:
    if not platform_user:
        return LEGACY_ROLE
    if is_platform_admin(platform_user):
        return "admin"
    op_ids = op_ids if op_ids is not None else await _operator_org_ids()
    if platform_user.get("organization_id") not in op_ids:
        return LEGACY_ROLE
    explicit = platform_user.get("crm_workspace_role")
    if explicit in ASSIGNABLE_ROLES:
        return explicit
    granted = await _apply_grant(platform_user)
    return granted or derive_role(platform_user)


def permissions_for(role: str) -> set:
    return set(ROLE_PERMISSIONS.get(role, set()))


async def workspace_context(platform_user: dict, org: Optional[dict]) -> dict:
    """Fields stamped on /auth/login + /auth/me so the launcher / Switch area
    menu and route guards share one backend-resolved access decision."""
    from utils.module_access import has_module
    role = await resolve_workspace_role(platform_user)
    perms = permissions_for(role)
    crm_on = is_platform_admin(platform_user) or (
        not str((org or {}).get("account_type") or "").startswith("mod_")
        and has_module(platform_user, org, "crm"))
    return {
        "crm_workspace_role": role,
        "crm_workspace_role_label": ROLE_LABELS.get(role, "CRM user"),
        "crm_permissions": sorted(perms),
        "crm_workspaces": {
            "crm": bool(crm_on and "workspace.crm" in perms),
            "contract_management": bool(crm_on and "workspace.contract_management" in perms),
        },
    }


async def run_workspace_boot() -> dict:
    """Idempotent boot step: seed the initial coordinator grants and
    reconcile cross-login CRM rows that were blanket-provisioned 'manager'."""
    for email in INITIAL_COORDINATORS:
        await db.crm_workspace_role_grants.update_one(
            {"email": email},
            {"$setOnInsert": {"email": email, "role": "contract_coordinator",
                              "source": "initial_coordinator_list", "created_at": _now()}},
            upsert=True,
        )
    applied = 0
    async for g in db.crm_workspace_role_grants.find({"applied": {"$ne": True}}, {"_id": 0}):
        u = await db.users.find_one({"email": g["email"]}, {"_id": 0})
        if u and not u.get("crm_workspace_role"):
            if await _apply_grant(u):
                applied += 1
    reconciled = 0
    async for cu in db.crm_users.find({"cross_login_provisioned": True, "role": "manager"}, {"_id": 0, "id": 1, "email": 1}):
        pu = await db.users.find_one({"email": (cu.get("email") or "").lower()}, {"_id": 0, "role": 1, "is_master_admin": 1, "is_pulse_admin": 1})
        if not pu:
            continue
        new_role = "admin" if is_platform_admin(pu) else (pu.get("role") or "staff")
        if new_role != "manager":
            await db.crm_users.update_one({"id": cu["id"]}, {"$set": {"role": new_role, "role_reconciled_at": _now()}})
            reconciled += 1
    return {"grants_applied": applied, "crm_roles_reconciled": reconciled}


async def run_integrity_boot() -> dict:
    """Idempotent: remove fabricated Sicon/Sage references and classify MOD
    rate-card prices that were never verified."""
    import re as _re
    from utils.mod_sor_data import build_seed_rate_card
    fixed_sicon = fixed_sage = 0
    async for c in db.crm2_contracts.find({"$or": [{"sicon_contract_id": {"$regex": "^SICON-"}},
                                                   {"sage_reference": {"$regex": "^SAGE-"}}]},
                                          {"_id": 0, "id": 1, "sicon_contract_id": 1, "sage_reference": 1}):
        upd = {}
        if c.get("sicon_contract_id") == f"SICON-{c['id'][:8].upper()}":
            upd.update({"sicon_contract_id": None, "sicon_sync_status": "pending",
                        "sicon_sync_detail": "Earlier simulated Sicon reference removed — not confirmed by Sicon."})
            fixed_sicon += 1
        if c.get("sage_reference") == f"SAGE-{c['id'][:8].upper()}":
            upd.update({"sage_reference": None, "sage_sync_status": "pending",
                        "sage_sync_detail": "Earlier simulated Sage reference removed — not confirmed by Sage."})
            fixed_sage += 1
        if upd:
            await db.crm2_contracts.update_one({"id": c["id"]}, {"$set": upd})
    seed = {d["id"]: d for d in build_seed_rate_card()}
    classified = 0
    async for rc in db.mod_sor_rate_card.find({"price_status": {"$exists": False}}, {"_id": 0}):
        sd = seed.get(rc["id"]) or {}
        same = all(rc.get(f) == sd.get(f) for f in ("type_a_price", "type_b_price"))
        status = "verified" if (rc.get("updated_by") or not same) else "placeholder"
        await db.mod_sor_rate_card.update_one({"id": rc["id"]}, {"$set": {"price_status": status}})
        classified += 1
    # Prices previously inferred as "verified" only because they differ from the
    # built-in examples are NOT commercially confirmed → "historical".
    hist = await db.mod_sor_rate_card.update_many(
        {"price_status": "verified", "verified_by": {"$in": [None, ""]}, "price_source": {"$in": [None, ""]}},
        {"$set": {"price_status": "historical"}})
    _ = _re
    from utils.cm_actions import ensure_indexes
    await ensure_indexes()
    from utils.cm_quote_import import ensure_indexes as _qi_indexes
    await _qi_indexes()
    return {"fabricated_sicon_refs_removed": fixed_sicon, "fabricated_sage_refs_removed": fixed_sage,
            "mod_rates_classified": classified, "mod_rates_marked_historical": hist.modified_count}
