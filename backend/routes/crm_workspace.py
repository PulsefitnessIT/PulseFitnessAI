"""CRM workspaces — role resolution + admin role assignment.

`require_crm_perm(perm)` is the backend gate for sensitive CRM actions; it
never relies on the frontend hiding a menu.
"""
from datetime import datetime, timezone
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


def _pct(v):
    if v in (None, ""):
        return None
    try:
        p = float(v)
    except (TypeError, ValueError):
        raise HTTPException(400, "uplift_percent must be a number")
    if not -20 <= p <= 25:
        raise HTTPException(400, "uplift_percent must be between -20 and 25")
    return p


@router.post("/renewals/{renewal_id}/approve-send")
async def renewal_approve_send(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.review"))):
    """Standard renewals (0% / approved RPI) can be issued by a coordinator;
    any other increase needs renewals.approve (checked inside)."""
    from utils.cm_renewals import approve_and_send_renewal
    res = await approve_and_send_renewal(renewal_id, user, _pct((data or {}).get("uplift_percent")))
    if not res.get("ok"):
        raise HTTPException(403 if res.get("code") == "approval_required" else 409, res.get("error") or "Could not send renewal")
    return res


@router.post("/renewals/{renewal_id}/request-approval")
async def renewal_request_approval(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import request_price_approval
    pct = _pct((data or {}).get("uplift_percent"))
    if pct is None:
        raise HTTPException(400, "Enter the proposed increase (%)")
    res = await request_price_approval(renewal_id, user, pct, (data or {}).get("reason") or "")
    if not res.get("ok"):
        raise HTTPException(409, res.get("error"))
    return res


@router.get("/renewals")
async def renewals_list(user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import list_renewals
    return {"renewals": await list_renewals(user.get("organization_id"))}


@router.post("/renewals/{renewal_id}/resend")
async def renewal_resend(renewal_id: str, user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import resend_renewal
    res = await resend_renewal(renewal_id, user)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error"))
    return res


@router.post("/renewals/{renewal_id}/cancel-email")
async def renewal_cancel_email(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.approve"))):
    from utils.cm_renewals import cancel_queued_renewal_email
    reason = ((data or {}).get("reason") or "").strip()
    if not reason:
        raise HTTPException(422, "Give a reason for cancelling the customer email")
    res = await cancel_queued_renewal_email(renewal_id, user, reason)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error"))
    return res


@router.post("/renewals/{renewal_id}/mark-issued")
async def renewal_mark_issued(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.approve"))):
    from utils.cm_renewals import mark_renewal_issued_manually
    evidence = ((data or {}).get("evidence") or "").strip()
    if len(evidence) < 5:
        raise HTTPException(422, "Record how the renewal reached the customer (e.g. 'handed to site manager 26/11')")
    res = await mark_renewal_issued_manually(renewal_id, user, evidence)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error"))
    return res


@router.post("/renewals/{renewal_id}/declined")
async def renewal_declined(renewal_id: str, data: dict = None, user=Depends(require_crm_perm("renewals.review"))):
    from utils.cm_renewals import record_outcome
    res = await record_outcome(renewal_id, user, "declined", (data or {}).get("note") or "")
    if not res.get("ok"):
        raise HTTPException(409, res.get("error"))
    return res


@router.put("/customers/{company_id}/coordinator")
async def set_customer_coordinator(company_id: str, data: dict, user=Depends(require_crm_perm("contracts.manage"))):
    """Assign the customer's Contract Coordinator (receives their tasks)."""
    org_id = user.get("organization_id")
    co = await db.crm2_companies.find_one({"id": company_id, "organization_id": org_id}, {"_id": 0, "id": 1})
    if not co:
        raise HTTPException(404, "Customer not found")
    uid = (data or {}).get("user_id") or None
    name = None
    if uid:
        u = await db.users.find_one({"id": uid, "organization_id": org_id}, {"_id": 0, "full_name": 1, "email": 1})
        if not u:
            raise HTTPException(404, "Coordinator not found")
        name = u.get("full_name") or u.get("email")
    prev = await db.crm2_companies.find_one({"id": company_id}, {"_id": 0, "coordinator_id": 1, "coordinator_name": 1}) or {}
    await db.crm2_companies.update_one({"id": company_id}, {
        "$set": {"coordinator_id": uid, "coordinator_name": name},
        "$push": {"coordinator_history": {"at": datetime.now(timezone.utc).isoformat(), "by": user.get("email"),
                                          "from_id": prev.get("coordinator_id"), "from_name": prev.get("coordinator_name"),
                                          "to_id": uid, "to_name": name}}})
    # Hand over open contract-admin work (shared queue + the previous coordinator's items).
    owners = ["system"] + ([prev["coordinator_id"]] if prev.get("coordinator_id") else [])
    new_owner = {"owner_id": uid or "system", "owner_name": name or "Shared coordinator queue"}
    moved = 0
    async for a in db.crm2_activities.find(
            {"organization_id": org_id, "company_id": company_id, "status": "open", "owner_id": {"$in": owners},
             "category": "contract_admin", "type": {"$ne": "renewal_price_approval"}},
            {"_id": 0, "id": 1, "owner_id": 1, "owner_name": 1}):
        if a["owner_id"] == new_owner["owner_id"]:
            continue
        await db.crm2_activities.update_one({"id": a["id"]}, {
            "$set": new_owner, "$push": {"owner_history": {"at": datetime.now(timezone.utc).isoformat(),
                                                           "from_id": a["owner_id"], "from_name": a.get("owner_name"),
                                                           "by": user.get("email")}}})
        moved += 1
    return {"company_id": company_id, "coordinator_id": uid, "coordinator_name": name, "tasks_reassigned": moved}


@router.get("/coordinators")
async def list_coordinators(user=Depends(require_crm_perm("contracts.read"))):
    rows = await db.users.find({"organization_id": user.get("organization_id"),
                                "crm_workspace_role": {"$in": ["contract_coordinator", "aftersales_manager"]}},
                               {"_id": 0, "id": 1, "full_name": 1, "email": 1}).to_list(200)
    return {"coordinators": rows}


@router.post("/sales-handover/{sales_quote_id}")
async def raise_handover_now(sales_quote_id: str, user=Depends(require_crm_perm("contracts.read"))):
    from utils.cm_handover import raise_sales_handover
    q = await db.crm_quotes.find_one({"id": sales_quote_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Sales quote not found")
    return await raise_sales_handover(user.get("organization_id"), q)


async def _daily_checks_all(run_id: str) -> None:
    from utils.cm_actions import run_daily_checks
    from utils.crm_workspace import _operator_org_ids
    results = []
    for org_id in sorted(await _operator_org_ids()):
        try:
            results.append(await run_daily_checks(org_id, actor="Daily checks (7am)"))
        except Exception as e:  # keep other orgs running
            results.append({"organization_id": org_id, "error": str(e)})
    try:
        from utils.cm_renewals import dispatch_queued_renewals
        results.append({"renewal_emails": await dispatch_queued_renewals()})
    except Exception as e:  # never block the other checks
        results.append({"renewal_emails_error": str(e)})
    try:
        from utils.mod_quote_chase import run_chases
        results.append({"mod_quote_chases": await run_chases()})
    except Exception as e:  # MOD chases must never block Contract Management checks
        results.append({"mod_quote_chases_error": str(e)})
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


@router.get("/mod-commitments")
async def mod_commitments(user=Depends(require_crm_perm("contracts.read"))):
    """Read-only view of accepted MOD quotations handed to MOD Service Operations.
    MOD Operations stays the authoritative register — nothing here is editable."""
    proj = {"_id": 0, "id": 1, "mod_site_name": 1, "quote_type": 1, "source_quote_number": 1, "annual_type_a_value": 1,
            "one_off_type_b_value": 1, "start_date": 1, "status": 1, "service_records": 1, "group_id": 1, "created_at": 1,
            "outstanding": 1}
    items = await db.mod_quote_handovers.find({}, proj).sort("created_at", -1).to_list(500)
    return {"items": items}
