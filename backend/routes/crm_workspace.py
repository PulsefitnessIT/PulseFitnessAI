"""CRM workspaces — role resolution + admin role assignment.

`require_crm_perm(perm)` is the backend gate for sensitive CRM actions; it
never relies on the frontend hiding a menu.
"""
import hmac
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

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


# ── Action Centre: daily checks + approval-first renewals ─────────────────

@router.post("/daily-checks/run")
async def run_checks_now(user=Depends(require_crm_perm("tasks.manage"))):
    from utils.cm_actions import run_daily_checks
    return await run_daily_checks(user.get("organization_id"), actor=user.get("full_name") or "coordinator")


@router.post("/renewals/prepare")
async def renewals_prepare(dry_run: bool = True, user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import prepare_renewals
    return await prepare_renewals(user.get("organization_id"), actor=user.get("full_name") or "coordinator",
                                  dry_run=dry_run)


@router.post("/renewals/{renewal_id}/approve-send")
async def renewal_approve_send(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import approve_and_send_renewal
    pct = (data or {}).get("uplift_percent")
    if pct not in (None, ""):
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            raise HTTPException(400, "uplift_percent must be a number")
        if not -20 <= pct <= 25:
            raise HTTPException(400, "uplift_percent must be between -20 and 25")
    else:
        pct = None
    res = await approve_and_send_renewal(renewal_id, user, pct)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error") or "Could not send renewal")
    return res


async def _daily_checks_all(run_id: str) -> None:
    from utils.cm_actions import run_daily_checks
    from utils.crm_workspace import _operator_org_ids
    results = []
    for org_id in sorted(await _operator_org_ids()):
        try:
            results.append(await run_daily_checks(org_id, actor="Daily checks (7am)"))
        except Exception as e:  # keep other orgs running
            results.append({"organization_id": org_id, "error": str(e)})
    await db.cm_daily_check_runs.update_one({"run_id": run_id}, {"$set": {"status": "done", "results": results}})


@router.post("/cron/daily-checks")
async def cron_daily_checks(request: Request, background: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET") or ""
    auth = request.headers.get("authorization") or ""
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(401, "Unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if body is not None and not isinstance(body, dict):
        raise HTTPException(400, "Invalid body")
    run_id = request.headers.get("x-webhook-id") or (body or {}).get("run_id") or ""
    if not run_id:
        from uuid import uuid4
        run_id = f"manual-{uuid4()}"
    from datetime import datetime, timezone
    res = await db.cm_daily_check_runs.update_one(
        {"run_id": run_id}, {"$setOnInsert": {"run_id": run_id, "status": "queued",
                                              "at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    if res.upserted_id is None:
        return {"accepted": True, "duplicate": True, "run_id": run_id}
    background.add_task(_daily_checks_all, run_id)
    return {"accepted": True, "run_id": run_id}
