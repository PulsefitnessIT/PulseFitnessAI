"""
CRM Enterprise Record-Level Permissions + Field-Level Security
================================================================
Iter 215de.

Two layered authorisation primitives applied on top of the existing
`organization_id` tenant boundary:

1. **Sharing rules** (`crm_sharing_rules`) — a list of role -> access
   mappings per entity type (contact / company / opportunity). Access
   levels are: `all`, `team`, `owner`, `none`. Enforced at the query
   level for list/detail endpoints.

2. **Field-level security** (`crm_field_perms`) — per-role redaction
   list. Fields listed here are stripped from the response payload
   before being returned to the user. Wraps any dict / list-of-dicts.

Master admins, org owners, and admin-role CRM users always bypass
both layers (you can't lock the admin out of their own org).

The module exposes:
  - `compute_visibility(user, entity_type)`  → MongoDB query fragment
  - `redact(user, entity_type, payload)`     → field-stripped payload
  - `is_unrestricted(user)`                  → admin/owner gate
  - REST endpoints under `/api/crm/permissions`.
"""
from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user, _is_master_admin_user

router = APIRouter(prefix="/crm/permissions", tags=["CRM Permissions"])

ENTITY_TYPES = {"contact", "company", "opportunity", "contract"}
ACCESS_LEVELS = {"all", "team", "owner", "none"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_unrestricted(user: dict) -> bool:
    """Master admins and org owners/admins bypass record + field perms."""
    if _is_master_admin_user(user):
        return True
    role = (user.get("role") or "").lower()
    return role in ("admin", "owner")


async def _get_team_ids(user: dict) -> list[str]:
    """Collect ids of every direct + indirect report of `user`."""
    try:
        from routes.crm_territories import collect_team_ids
        return await collect_team_ids(user.get("id"), user.get("organization_id"))
    except Exception:
        return [user.get("id", "")]


async def _resolve_access(user: dict, entity_type: str) -> str:
    """Highest-priority sharing rule wins; default = `team`."""
    if is_unrestricted(user):
        return "all"
    role = (user.get("role") or "user").lower()
    rule = await db.crm_sharing_rules.find_one(
        {"organization_id": user.get("organization_id"), "entity_type": entity_type, "role": role},
        {"_id": 0},
    )
    if rule and rule.get("access") in ACCESS_LEVELS:
        return rule["access"]
    return "team"


async def compute_visibility(user: dict, entity_type: str) -> dict:
    """Return a MongoDB query fragment enforcing this user's record visibility.

    Always merges the per-request site filter (multi-site isolation) so a
    restricted manager only ever reads their assigned site(s) — this is the
    single choke-point for every CRM v2 list endpoint, so it can't be missed.
    """
    from utils.site_scope import effective_site_filter
    site_f = effective_site_filter()
    base: dict = {"organization_id": user.get("organization_id") or "__none__", **site_f}
    if entity_type not in ENTITY_TYPES:
        return base
    access = await _resolve_access(user, entity_type)
    if access == "all":
        return base
    if access == "owner":
        return {**base, "owner_id": user.get("id")}
    if access == "none":
        return {**base, "owner_id": "__BLOCKED__"}  # impossible match
    # team (default)
    ids = await _get_team_ids(user)
    return {**base, "owner_id": {"$in": ids or [user.get("id", "")]}}


async def _field_blocklist(user: dict, entity_type: str) -> set[str]:
    if is_unrestricted(user) or entity_type not in ENTITY_TYPES:
        return set()
    role = (user.get("role") or "user").lower()
    rows = await db.crm_field_perms.find(
        {
            "organization_id": user.get("organization_id"),
            "entity_type": entity_type,
            "role": role,
            "access": "hidden",
        },
        {"_id": 0, "field": 1},
    ).to_list(200)
    return {r["field"] for r in rows if r.get("field")}


def _strip_fields(doc: dict, fields: set[str]) -> dict:
    if not fields:
        return doc
    return {k: v for k, v in doc.items() if k not in fields}


async def redact(user: dict, entity_type: str, payload: Any) -> Any:
    """Strip restricted fields from a dict / list-of-dicts response."""
    fields = await _field_blocklist(user, entity_type)
    if not fields:
        return payload
    if isinstance(payload, list):
        return [_strip_fields(d, fields) if isinstance(d, dict) else d for d in payload]
    if isinstance(payload, dict):
        return _strip_fields(payload, fields)
    return payload


# ─────────────────────────────────────────────────────────────────────
# REST API — admin only
# ─────────────────────────────────────────────────────────────────────

def _require_admin(user: dict) -> None:
    if not is_unrestricted(user):
        raise HTTPException(403, "Master admin / owner access required")


@router.get("/sharing-rules")
async def list_sharing_rules(user=Depends(get_crm_user)):
    _require_admin(user)
    rows = await db.crm_sharing_rules.find(
        {"organization_id": user.get("organization_id")}, {"_id": 0}
    ).sort("entity_type", 1).to_list(200)
    return {"rules": rows, "entity_types": sorted(ENTITY_TYPES), "access_levels": sorted(ACCESS_LEVELS)}


@router.put("/sharing-rules")
async def upsert_sharing_rule(data: dict, user=Depends(get_crm_user)):
    _require_admin(user)
    entity_type = (data.get("entity_type") or "").lower()
    role = (data.get("role") or "").lower()
    access = (data.get("access") or "").lower()
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(400, f"entity_type must be one of {sorted(ENTITY_TYPES)}")
    if access not in ACCESS_LEVELS:
        raise HTTPException(400, f"access must be one of {sorted(ACCESS_LEVELS)}")
    if not role:
        raise HTTPException(400, "role required")
    org_id = user.get("organization_id")
    await db.crm_sharing_rules.update_one(
        {"organization_id": org_id, "entity_type": entity_type, "role": role},
        {"$set": {"access": access, "updated_at": _now(), "updated_by": user.get("full_name", "")},
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
        upsert=True,
    )
    return {"success": True}


@router.delete("/sharing-rules")
async def delete_sharing_rule(entity_type: str, role: str, user=Depends(get_crm_user)):
    _require_admin(user)
    await db.crm_sharing_rules.delete_one(
        {"organization_id": user.get("organization_id"),
         "entity_type": entity_type.lower(), "role": role.lower()}
    )
    return {"success": True}


@router.get("/field-perms")
async def list_field_perms(user=Depends(get_crm_user)):
    _require_admin(user)
    rows = await db.crm_field_perms.find(
        {"organization_id": user.get("organization_id")}, {"_id": 0}
    ).sort("entity_type", 1).to_list(500)
    return {"perms": rows, "entity_types": sorted(ENTITY_TYPES)}


@router.put("/field-perms")
async def upsert_field_perm(data: dict, user=Depends(get_crm_user)):
    _require_admin(user)
    entity_type = (data.get("entity_type") or "").lower()
    role = (data.get("role") or "").lower()
    field = (data.get("field") or "").strip()
    access = (data.get("access") or "hidden").lower()
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(400, "invalid entity_type")
    if access not in ("hidden", "visible"):
        raise HTTPException(400, "access must be hidden|visible")
    if not field or not role:
        raise HTTPException(400, "field and role required")
    org_id = user.get("organization_id")
    if access == "visible":
        await db.crm_field_perms.delete_one(
            {"organization_id": org_id, "entity_type": entity_type, "role": role, "field": field}
        )
    else:
        await db.crm_field_perms.update_one(
            {"organization_id": org_id, "entity_type": entity_type, "role": role, "field": field},
            {"$set": {"access": access, "updated_at": _now()},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
            upsert=True,
        )
    return {"success": True}


@router.delete("/field-perms")
async def delete_field_perm(entity_type: str, role: str, field: str, user=Depends(get_crm_user)):
    _require_admin(user)
    await db.crm_field_perms.delete_one(
        {"organization_id": user.get("organization_id"),
         "entity_type": entity_type.lower(), "role": role.lower(), "field": field}
    )
    return {"success": True}


@router.get("/effective")
async def effective_for_me(user=Depends(get_crm_user)):
    """Return the active access rules for the calling user — useful for UI gating."""
    out = {"is_unrestricted": is_unrestricted(user), "rules": {}, "hidden_fields": {}}
    for et in ENTITY_TYPES:
        out["rules"][et] = await _resolve_access(user, et)
        out["hidden_fields"][et] = sorted(await _field_blocklist(user, et))
    return out
