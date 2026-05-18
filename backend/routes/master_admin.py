"""
Master Admin · shared helper module.

Iter 216h187 — After the 10-phase decomposition (216h177 → 216h186)
this module owns **zero routes**. It exists to provide the shared
helper surface that every `routes/master_admin_*.py` sub-router and
~6 other downstream modules (`routes/sites.py`, `routes/assistant.py`,
`routes/companies_house.py`, `routes/data_wipe.py`,
`routes/mod_portal.py`, `routes/pulse_sales.py`) import.

The `__all__` list below is the canonical public API. Pin-tests in
`tests/test_iter_216h186_master_admin_ops_split.py` assert that every
name here still exists; renaming or deleting any of them silently
breaks ~20 importers, so changes must be deliberate.

Routes used to live here (4,283 LoC, 40+ routes). They now live in 14
focused sub-routers — see `route_registry/admin.py` for the full list.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import asyncio
import logging
import os
import secrets
import uuid

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Public helper API (consumed by 14 sub-routers + ~6 other modules) ───
__all__ = [
    # FastAPI router — kept for backwards-compat with anything that imports
    # `from routes.master_admin import router`. Owns zero routes post-iter
    # 216h186; included so callers that include() it don't crash.
    "router",
    # role / scope guards
    "require_master_admin",
    "require_gymaxis_master_only",
    "assert_org_in_pulse_scope",
    "assert_user_in_pulse_scope",
    "is_pulse_only",
    "_resolve_pulse_scope_org_ids",
    # constants
    "PULSE_VISIBLE_ACCOUNT_TYPES",
    "MASTER_ADMIN_EMAIL",
    "ADDRESS_FIELDS",
    "ALL_MODULE_IDS",
    # audit + activity logging
    "log_activity",
    # address shape helpers
    "compose_legacy_address",
    "merge_address",
    # primary-contact / org bootstrap helpers
    "_normalize_modules",
    "_modules_from_portal_type",
    "_derive_portal_type",
    "_generate_initial_password",
    "_mint_invite_link",
    "_ensure_primary_contact_user",
    "_create_org_user",
    # misc parsers
    "_parse_onboard_date",
]


def _parse_onboard_date(date_str: str) -> str:
    """Convert dd/mm/yyyy to ISO format for storage."""
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return date_str


# ─────────────────────────────────────────────────────────────────
# Iter 215en — Structured address helpers (Address 1*, Address 2,
# Address 3, City, County, Post code, Country). Everything that
# accepts the legacy single-line `address` continues to work; when
# only the structured fields are supplied we compose the legacy
# field from them so downstream Sage / Sicon outbox payloads keep
# working unchanged.
# ─────────────────────────────────────────────────────────────────

ADDRESS_FIELDS = (
    "address_line1", "address_line2", "address_line3",
    "city", "county", "postcode", "country",
)


def compose_legacy_address(payload: dict) -> str:
    """Compose a single-line address from the structured shape.

    Used to populate the legacy `address` field on org / site rows so
    Sage / Sicon outbox payloads keep working without code changes.
    Returns the existing `address` if no structured fields are present.
    """
    parts = [str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    return str(payload.get("address") or "").strip()


def merge_address(payload: dict) -> dict:
    """Pluck the structured address fields from `payload`, ensure the
    legacy `address` is in sync, and return a dict ready to merge into
    a Mongo document. The caller is responsible for picking out the
    keys they actually want to persist."""
    out = {k: str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS}
    if not out["country"]:
        out["country"] = "United Kingdom"
    legacy_explicit = str(payload.get("address") or "").strip()
    composed = compose_legacy_address(payload)
    out["address"] = legacy_explicit or composed
    return out


MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")

# Account types a Pulse Master Admin is allowed to see.
# Mirrors `routes.pulse_master_admin.PULSE_VISIBLE_ACCOUNT_TYPES` — kept inline
# to avoid a circular import.
PULSE_VISIBLE_ACCOUNT_TYPES = ["pulse_pro", "lite", "mod", "full"]


def is_pulse_only(user: dict) -> bool:
    """True when the caller is a Pulse Master Admin (delegated) but NOT the
    GymAxis platform Master Admin. Used to decide whether to scope list /
    edit endpoints to Pulse-visible orgs."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return False
    return bool(user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin")


def require_master_admin(user: dict) -> None:
    """Either the GymAxis Master Admin OR a delegated Pulse Master Admin is
    allowed past this gate. Endpoints that need to lock out Pulse admins
    explicitly should call ``require_gymaxis_master_only(user)`` instead.
    """
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


def require_gymaxis_master_only(user: dict) -> None:
    """Strict gate — only the GymAxis platform Master Admin (not Pulse admins)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    raise HTTPException(status_code=403, detail="GymAxis master admin access required")


async def assert_org_in_pulse_scope(user: dict, org_id: str) -> dict:
    """If caller is Pulse-only, 404 unless the target org is Pulse-visible.

    Returns the org doc (sans `_id`) so callers can avoid a redundant fetch.
    GymAxis master admins skip the scope check.
    """
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if is_pulse_only(user) and org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def assert_user_in_pulse_scope(user: dict, target_user_id: str) -> None:
    """Pulse-only callers can only mutate users belonging to a Pulse-visible org."""
    if not is_pulse_only(user):
        return
    target = (
        await db.users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
        or await db.crm_users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
    )
    if not target or not target.get("organization_id"):
        raise HTTPException(status_code=404, detail="User not found")
    org = await db.organizations.find_one(
        {"id": target["organization_id"]}, {"_id": 0, "account_type": 1},
    )
    if not org or org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="User not found")


async def log_activity(action: str, details: str, admin_email: str, target_type: str = "", target_id: str = "") -> None:
    await db.admin_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "action": action,
        "details": details,
        "admin_email": admin_email,
        "target_type": target_type,
        "target_id": target_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })




async def _resolve_pulse_scope_org_ids(user: dict) -> Optional[list[str]]:
    """Return org-id list when caller is Pulse-only, else ``None``.

    ``None`` signals platform-wide queries.
    """
    if not is_pulse_only(user):
        return None
    pulse_orgs = await db.organizations.find(
        {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    return [o["id"] for o in pulse_orgs]


# Derivation tables for tier ↔ account_type. Used by the orgs sub-router
# when promoting a Pulse Lite site to Pro (or vice-versa). Kept here as
# constants so the mapping doesn't drift between modules.
_PULSE_TIER_TO_ACCOUNT_TYPE = {"lite": "lite", "pulse_pro": "pulse_pro"}
_GYMAXIS_TIERS = {"free", "pro", "premium", "enterprise", "starter", "professional"}


# ─── Iter 215ar — Modules + Primary-contact auto-provisioning ───
# Canonical module ids exposed to the master-admin UI (checkbox grid).
ALL_MODULE_IDS = ["operations", "crm", "memberships", "marketing", "staffing", "reporting"]


def _normalize_modules(raw, legacy_portal_type: Optional[str]) -> List[str]:
    """Coerce the inbound `enabled_modules` list to a clean, deduped subset
    of ALL_MODULE_IDS. Falls back to deriving from a legacy portal_type
    string so older callers keep working unchanged."""
    if isinstance(raw, list) and raw:
        cleaned = [m for m in raw if isinstance(m, str) and m in ALL_MODULE_IDS]
        if cleaned:
            # Stable order — match the UI grid for predictability.
            return [m for m in ALL_MODULE_IDS if m in cleaned]
    return _modules_from_portal_type(legacy_portal_type or "service_portal")


def _modules_from_portal_type(portal_type: str) -> List[str]:
    """Map a legacy portal_type string back onto the modules list."""
    if portal_type == "crm":
        return ["crm"]
    if portal_type == "both":
        return ["operations", "crm"]
    return ["operations"]  # service_portal default


def _derive_portal_type(modules: List[str]) -> str:
    """Reduce a modules list to the legacy portal_type for callers that
    still gate on it (collection routing, feature flags)."""
    has_crm = "crm" in modules
    has_ops = any(m in modules for m in ("operations", "memberships", "marketing", "staffing", "reporting"))
    if has_crm and has_ops:
        return "both"
    if has_crm:
        return "crm"
    return "service_portal"


def _generate_initial_password(length: int = 14) -> str:
    """Generate a friendly, copy-able initial password: 4 lowercase + 4 digits + 4 lowercase + 2 symbols.
    Avoids ambiguous characters (no l/1/O/0)."""
    alphabet = "abcdefghijkmnpqrstuvwxyz"
    digits   = "23456789"
    symbols  = "!@#%&*"

    def pick(src: str, n: int) -> str:
        return "".join(secrets.choice(src) for _ in range(n))

    return f"{pick(alphabet, 4)}{pick(digits, 3)}{pick(alphabet, 3)}{pick(symbols, 2)}"


async def _mint_invite_link(user_id: str, email: str, issued_by_email: str = "system") -> dict:
    """Iter 216h26 — Mint a 72 h reset-link invite for a user.

    Extracted from POST /master-admin/users/{user_id}/invite-link so
    that org create + customer onboarding can return a self-serve
    invite URL alongside (or instead of) the legacy reveal-password
    handover. Lets every Master Admin creation surface stay consistent
    with the iter-216h15 reset-link flow.
    """
    import secrets as _secrets
    from datetime import timedelta as _td
    token = _secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email,
        "expires_at": expires_at,
        "used": False,
        "kind": "invite",
        "issued_by": issued_by_email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return {
        "invite_url": f"{frontend_url}/reset-password?token={token}",
        "expires_at": expires_at,
    }


async def _ensure_primary_contact_user(org: dict, actor: dict) -> Optional[str]:
    """If `primary_contact_email` is set on `org` and no user exists for that
    email, auto-provision an admin user in the right collection(s) and
    persist the generated initial password on the org doc. Returns the
    generated password if a new user was created, else None.

    The plaintext is intentionally retained on the org until the user
    changes their password — so master-admin can hand it over during
    onboarding via the Reveal Password button. Cleared by the auth layer
    when the user changes password (see `password_reset.py`)."""
    email = (org.get("primary_contact_email") or "").strip().lower()
    if not email:
        return None
    # Skip if a user already exists in either collection — never overwrite.
    if await db.users.find_one({"email": email}) or await db.crm_users.find_one({"email": email}):
        return None

    full_name = (org.get("primary_contact_name") or email.split("@")[0]).strip() or email
    password  = _generate_initial_password()
    user_id   = str(uuid.uuid4())
    try:
        await _create_org_user(org, email, full_name, password, role="admin", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        # Don't blow up org creation if user creation fails — log + continue.
        logger.warning("Failed to auto-create primary contact user for org %s: %s", org.get("id"), exc)
        return None

    # Persist the plaintext password so master-admin can reveal it.
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "primary_contact_initial_password": password,
            "primary_contact_user_id": user_id,
            "primary_contact_password_changed": False,
            "primary_contact_provisioned_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_activity(
        "primary_contact_provisioned",
        f"Auto-created user {email} as primary contact for {org.get('name')}",
        actor.get("email", "system"), "user", user_id,
    )
    return password








async def _create_org_user(org: dict, email: str, full_name: str, password: str, role: str, user_id: str) -> str:
    """Create a user in the appropriate collection(s) based on org portal type.

    Iter 215ev — when portal_type == 'both' we write to both collections
    with the SAME `id` so downstream listings can dedupe into one row
    per person (with portal badges), instead of showing the same human
    as two separate user rows. Was a real pain-point (see user bug
    report "Rob Yates doubled up").
    """
    now = datetime.now(timezone.utc).isoformat()
    portal_type = org.get("portal_type", "service_portal")
    is_crm = portal_type in ("crm", "both")
    is_sp = portal_type in ("service_portal", "both")

    if is_crm:
        from routes.crm_auth import crm_hash_password
        await db.crm_users.insert_one({
            "id": user_id, "email": email, "full_name": full_name,
            "password": crm_hash_password(password),
            "organization_id": org["id"], "role": role,
            "avatar_url": None, "created_at": now,
        })

    if is_sp:
        from utils.auth import hash_password
        await db.users.insert_one({
            "id": user_id,  # Iter 215ev — SAME id across both collections so listings dedupe cleanly.
            "email": email, "full_name": full_name,
            "password": hash_password(password),
            "organization_id": org["id"], "role": role,
            "account_type": org.get("account_type", "full"),
            "created_at": now,
        })

    return "CRM" if is_crm else "Service Portal"


