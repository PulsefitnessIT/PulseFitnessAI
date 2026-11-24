"""CRM workspaces — role resolution + admin role assignment.

`require_crm_perm(perm)` is the backend gate for sensitive CRM actions; it
never relies on the frontend hiding a menu.
"""
from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from utils.crm_workspace import (
    ROLE_LABELS, ASSIGNABLE_ROLES, ROLE_PERMISSIONS, CM_ROLES,
    resolve_workspace_role, set_explicit_role, derive_role, _operator_org_ids,
)
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/workspace", tags=["CRM Workspaces"])


def assert_crm_perm(user: dict, perm: str) -> None:
    if perm not in (user.get("crm_permissions") or []):
        label = user.get("crm_workspace_role_label") or "your role"
        raise HTTPException(403, f"{label} is not permitted to perform this action ({perm}).")


def require_crm_perm(perm: str):
    async def _dep(user=Depends(get_crm_user)):
        assert_crm_perm(user, perm)
        return user
    return _dep


@router.get("/me")
async def workspace_me(user=Depends(get_crm_user)):
    return {
        "role": user.get("crm_workspace_role"),
        "role_label": user.get("crm_workspace_role_label"),
        "permissions": user.get("crm_permissions") or [],
        "workspaces": user.get("crm_workspaces") or {},
    }


async def _staff_org_id(user: dict) -> str:
    ops = await _operator_org_ids()
    if user.get("organization_id") in ops:
        return user["organization_id"]
    if ops:
        return sorted(ops)[0]
    raise HTTPException(400, "No operator company configured")


@router.get("/roles")
async def list_roles(user=Depends(require_crm_perm("permissions.admin"))):
    org_id = await _staff_org_id(user)
    ops = await _operator_org_ids()
    rows = await db.users.find(
        {"organization_id": org_id, "role": {"$nin": ["engineer", "engineer_partner", "site_staff"]}},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "crm_workspace_role": 1,
         "is_master_admin": 1, "is_pulse_admin": 1, "is_org_owner": 1, "organization_id": 1},
    ).sort("full_name", 1).to_list(1000)
    out = []
    for r in rows:
        eff = await resolve_workspace_role(r, ops)
        out.append({
            "id": r["id"], "email": r.get("email"), "full_name": r.get("full_name") or r.get("email"),
            "platform_role": r.get("role"),
            "explicit_role": r.get("crm_workspace_role") if r.get("crm_workspace_role") in ASSIGNABLE_ROLES else None,
            "derived_role": derive_role(r),
            "effective_role": eff,
            "effective_role_label": ROLE_LABELS.get(eff, eff),
        })
    return {
        "users": out,
        "roles": [{"id": k, "label": v, "permissions": sorted(ROLE_PERMISSIONS[k]),
                   "contract_management": k in CM_ROLES} for k, v in ROLE_LABELS.items()],
    }


@router.put("/roles/{user_id}")
async def assign_role(user_id: str, data: dict, user=Depends(require_crm_perm("permissions.admin"))):
    role = data.get("role") or None
    if role not in (None, *ASSIGNABLE_ROLES):
        raise HTTPException(400, f"role must be one of {list(ASSIGNABLE_ROLES)} or null (match platform role)")
    org_id = await _staff_org_id(user)
    target = await db.users.find_one({"id": user_id, "organization_id": org_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Staff member not found")
    await set_explicit_role(target, role, actor=user.get("email") or user.get("id"))
    # An admin decision supersedes any pending initial grant for this email.
    await db.crm_workspace_role_grants.update_one(
        {"email": (target.get("email") or "").lower()}, {"$set": {"applied": True}})
    eff = await resolve_workspace_role(target)
    return {"success": True, "user_id": user_id, "effective_role": eff, "effective_role_label": ROLE_LABELS.get(eff, eff)}


@router.get("/roles/{user_id}/audit")
async def role_audit(user_id: str, user=Depends(require_crm_perm("permissions.admin"))):
    rows = await db.crm_workspace_role_audit.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).to_list(50)
    return {"history": rows}
