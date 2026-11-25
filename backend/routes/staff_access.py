"""System Access — one place to see and set who can use Contract Management and MOD Operations.

Uses the same identity as Staffing & HR (staff_members.user_id → users.id) and the same
permission sources as the Contracts workspace (crm_workspace_role) and MOD quotations (mod_quote_role).
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.crm_workspace import (ASSIGNABLE_ROLES, CM_ROLES, EXTRA_PERMISSIONS, NO_ROLE, ROLE_LABELS, _now,
                                 _operator_org_ids, is_platform_admin, permissions_for, resolve_workspace_role,
                                 set_explicit_role)
from utils.database import db
from utils.module_access import has_mod_operations

router = APIRouter(prefix="/staffing/system-access", tags=["staff-access"])

MOD_ROLES = {"": "MOD Sales (draft only)", "manager": "MOD Sales Manager (approve)",
             "pricing_admin": "Pricing Administrator", "pricing_admin_manager": "Sales Manager + Pricing Administrator"}
USER_PROJ = {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "organization_id": 1, "active": 1, "is_active": 1,
             "disabled": 1, "module_overrides": 1, "crm_workspace_role": 1, "crm_workspace_extra_permissions": 1,
             "mod_quote_role": 1, "is_master_admin": 1, "is_pulse_admin": 1, "department": 1, "last_login": 1}


def _owner_level(user: dict) -> bool:
    role = str(user.get("role") or "").lower()
    return is_platform_admin(user) or role in ("owner", "org_owner") or bool(user.get("is_org_owner"))


async def _admin(user=Depends(get_current_user)) -> dict:
    """Master Admin, an org owner, or a Contracts workspace Administrator (permissions.admin)."""
    role = str(user.get("role") or "").lower()
    if is_platform_admin(user) or role in ("owner", "org_owner") or user.get("is_org_owner"):
        return user
    if "permissions.admin" in permissions_for(await resolve_workspace_role(user), user):
        return user
    raise HTTPException(403, "System Access is restricted to administrators")


async def _org(user: dict) -> str:
    if user.get("organization_id") in await _operator_org_ids():
        return user["organization_id"]
    ops = sorted(await _operator_org_ids())
    if is_platform_admin(user) and ops:
        return ops[0]
    raise HTTPException(403, "System Access covers Pulse Fitness staff only")


def _login_active(u: dict | None) -> bool:
    return bool(u) and u.get("active", True) is not False and u.get("is_active", True) is not False and not u.get("disabled")


async def _row(st: dict | None, u: dict | None, op_ids: set, dupes: set) -> dict:
    issues: list[str] = []
    role = await resolve_workspace_role(u, op_ids) if u else NO_ROLE
    explicit = (u or {}).get("crm_workspace_role")
    mod_ops = has_mod_operations(u) if u else False
    if st and not u:
        email = (st.get("email") or "").strip()
        platform = email and await db.users.find_one(
            {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}, "$or": [{"is_master_admin": True}, {"is_pulse_admin": True}]}, {"_id": 1})
        if platform:
            u = None
            return {**(await _row(None, None, op_ids, dupes)), "staff_id": st.get("id"), "name": st.get("full_name"), "email": email,
                    "job_title": st.get("primary_role"), "department": st.get("department"), "status": "ok",
                    "login_active": True, "contracts_role": "admin", "contracts_role_label": "Administrator",
                    "contracts_role_source": "platform admin", "contracts_access": True, "mod_operations_access": True,
                    "issues": [], "note": "Signs in with the platform Master Admin account"}
        issues.append("No login account linked")
    if u and not st and not is_platform_admin(u):
        issues.append("Login has no Staffing & HR record")
    employed = ((st or {}).get("status", "active") not in ("archived", "terminated", "left", "inactive")
                and (st or {}).get("active", True) is not False and (st or {}).get("lifecycle_stage") != "leaver")
    if u and st and not employed and _login_active(u):
        issues.append("Employee has left but login is still active")
    if u and _login_active(u) and not explicit and role not in (NO_ROLE, "admin") and not is_platform_admin(u):
        issues.append("Contracts/CRM access comes from a default, not an explicit assignment")
    if (u or {}).get("mod_quote_role") and not mod_ops:
        issues.append("Has a MOD quotation role but no MOD Operations access")
    if st and str(st.get("primary_role") or "").endswith("contract_coordinator") and role not in CM_ROLES:
        issues.append("Job title is Contract Coordinator but no Contracts workspace role is assigned")
    if (u or {}).get("email", "").lower() in dupes or (st or {}).get("email", "").lower() in dupes:
        issues.append("Duplicate identity (same email on more than one record)")
    if u and not _login_active(u) and await db.crm2_companies.count_documents({"coordinator_id": u["id"]}):
        issues.append("Inactive login still owns customer portfolios")
    if not u:
        status = "no_login"
    elif not _login_active(u):
        status = "inactive"
    elif issues:
        status = "needs_review"
    elif role == NO_ROLE and not mod_ops:
        status = "not_authorised"
    else:
        status = "ok"
    return {
        "staff_id": (st or {}).get("id"), "user_id": (u or {}).get("id"),
        "name": (st or {}).get("full_name") or (u or {}).get("full_name") or (u or {}).get("email"),
        "email": (u or st or {}).get("email"), "job_title": (st or {}).get("primary_role"),
        "department": (st or {}).get("department") or (u or {}).get("department"),
        "employment_status": (st or {}).get("status") or ("active" if u else None),
        "login_active": _login_active(u), "platform_role": (u or {}).get("role"),
        "contracts_role": role, "contracts_role_label": ROLE_LABELS.get(role, "No workspace role"),
        "contracts_role_source": "explicit" if explicit else ("platform admin" if u and is_platform_admin(u) else "default"),
        "contracts_access": role in CM_ROLES, "crm_sales_access": role in ("sales_manager", "aftersales_manager", "admin"),
        "extra_permissions": [p for p in (u or {}).get("crm_workspace_extra_permissions") or [] if p in EXTRA_PERMISSIONS],
        "mod_operations_access": mod_ops, "mod_quote_role": (u or {}).get("mod_quote_role") or "",
        "issues": issues, "status": status,
    }


@router.get("/can")
async def can_administer(user=Depends(get_current_user)):
    try:
        await _admin(user)
        return {"allowed": True}
    except HTTPException:
        return {"allowed": False}


@router.get("")
async def system_access(department: str = Query(""), status: str = Query(""), user=Depends(_admin)):
    org_id = await _org(user)
    op_ids = await _operator_org_ids()
    staff = await db.staff_members.find({"organization_id": org_id}, {"_id": 0, "id": 1, "full_name": 1, "email": 1,
                                        "primary_role": 1, "department": 1, "status": 1, "user_id": 1}).to_list(2000)
    users = await db.users.find({"organization_id": org_id}, USER_PROJ).to_list(2000)
    by_id = {u["id"]: u for u in users}
    by_email = {}
    emails: dict[str, int] = {}
    for u in users:
        e = (u.get("email") or "").lower()
        by_email.setdefault(e, u)
        emails[e] = emails.get(e, 0) + 1
    for st in staff:
        e = (st.get("email") or "").lower()
        if e:
            emails[e] = emails.get(e, 0) + (0 if (st.get("user_id") in by_id or e in by_email) else 1)
    dupes = {e for e, n in emails.items() if e and n > 1}
    dupes |= {e for e in {(s.get("email") or "").lower() for s in staff}
              if e and sum(1 for s in staff if (s.get("email") or "").lower() == e) > 1}
    rows, seen = [], set()
    for st in staff:
        u = by_id.get(st.get("user_id")) or by_email.get((st.get("email") or "").lower())
        if u:
            seen.add(u["id"])
        rows.append(await _row(st, u, op_ids, dupes))
    for u in users:
        if u["id"] not in seen:
            rows.append(await _row(None, u, op_ids, dupes))
    summary = {k: sum(1 for r in rows if r["status"] == k) for k in ("ok", "needs_review", "no_login", "inactive", "not_authorised")}
    summary |= {"total": len(rows), "linked": sum(1 for r in rows if r["staff_id"] and r["user_id"]),
                "contracts_roles": sum(1 for r in rows if r["contracts_access"]),
                "mod_operations": sum(1 for r in rows if r["mod_operations_access"]),
                "duplicates": sum(1 for r in rows if any("Duplicate" in i for i in r["issues"]))}
    if department:
        rows = [r for r in rows if (r["department"] or "") == department]
    if status:
        rows = [r for r in rows if r["status"] == status]
    rows.sort(key=lambda r: (r["department"] or "~", r["name"] or ""))
    return {"rows": rows, "summary": summary,
            "contracts_roles": [{"id": k, "label": v} for k, v in ROLE_LABELS.items()],
            "mod_roles": [{"id": k, "label": v} for k, v in MOD_ROLES.items()],
            "extra_permissions": [{"id": k, "label": v} for k, v in EXTRA_PERMISSIONS.items()]}


@router.put("/{user_id}")
async def set_access(user_id: str, data: dict, user=Depends(_admin)):
    org_id = await _org(user)
    target = await db.users.find_one({"id": user_id, "organization_id": org_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Staff login not found")
    if is_platform_admin(target) and not is_platform_admin(user):
        raise HTTPException(403, "Master Admin access can only be changed by a Master Admin")
    actor = user.get("email") or user.get("id")
    changes = []
    if not _owner_level(user) and ({"mod_operations", "mod_quote_role"} & set(data) or data.get("contracts_role") == "admin"):
        raise HTTPException(403, "Only a Master Admin or company owner can grant MOD access or the Administrator role")
    if "extra_permissions" in data and not isinstance(data["extra_permissions"], list):
        raise HTTPException(400, "extra_permissions must be a list")
    if "contracts_role" in data:
        role = data["contracts_role"] or None
        if role not in (None, *ASSIGNABLE_ROLES):
            raise HTTPException(400, "Unknown Contracts workspace role")
        if role != target.get("crm_workspace_role"):
            await set_explicit_role(target, role, actor=actor)
            await db.crm_workspace_role_grants.update_one({"email": (target.get("email") or "").lower()}, {"$set": {"applied": True}})
            changes.append("contracts_role")
    if "extra_permissions" in data:
        extras = sorted({p for p in data["extra_permissions"] or [] if p in EXTRA_PERMISSIONS})
        if extras != sorted(target.get("crm_workspace_extra_permissions") or []):
            await db.users.update_one({"id": user_id}, {"$set": {"crm_workspace_extra_permissions": extras}})
            await db.crm_workspace_role_audit.insert_one({"user_id": user_id, "email": target.get("email"), "kind": "extra_permissions",
                                                         "from": target.get("crm_workspace_extra_permissions") or [], "to": extras,
                                                         "by": actor, "at": _now()})
            changes.append("extra_permissions")
    if "mod_quote_role" in data:
        mod = data["mod_quote_role"] or ""
        if mod not in MOD_ROLES:
            raise HTTPException(400, "Unknown MOD quotation role")
        if mod != (target.get("mod_quote_role") or ""):
            await db.users.update_one({"id": user_id}, {"$set": {"mod_quote_role": mod or None}})
            await db.crm_workspace_role_audit.insert_one({"user_id": user_id, "email": target.get("email"), "kind": "mod_quote_role",
                                                         "from": target.get("mod_quote_role"), "to": mod or None, "by": actor, "at": _now()})
            changes.append("mod_quote_role")
    if "mod_operations" in data:
        on = bool(data["mod_operations"])
        if on != has_mod_operations(target):
            upd = {"module_overrides.mod_operations": on} | ({} if on else {"mod_quote_role": None})
            await db.users.update_one({"id": user_id}, {"$set": upd})
            await db.crm_workspace_role_audit.insert_one({"user_id": user_id, "email": target.get("email"), "kind": "mod_operations",
                                                         "from": not on, "to": on, "by": actor, "at": _now()})
            changes.append("mod_operations")
    # Permissions are re-resolved on every request, so changes apply on the person's next page load.
    return {"ok": True, "changed": changes}


@router.get("/{user_id}/audit")
async def access_audit(user_id: str, user=Depends(_admin)):
    org_id = await _org(user)
    if not await db.users.find_one({"id": user_id, "organization_id": org_id}, {"_id": 1}):
        raise HTTPException(404, "Staff login not found")
    return {"history": await db.crm_workspace_role_audit.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).to_list(100)}
