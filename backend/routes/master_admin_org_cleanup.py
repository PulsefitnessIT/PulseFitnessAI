"""Master Admin · Organisation cleanup tool.

Safe, auditable consolidation of duplicate / stray organisations:

  * `set-operator`  — pin ONE org as the operator company. The Pulse portal
                      quick button (pulse_portal_login) prefers this pin, so
                      the "wrong org" class of bug can never recur.
  * `merge-delete`  — reassign every org-scoped record from the stray orgs to
                      the keep org, then HARD-DELETE the stray org docs.
                      Guards: never delete the keep org, the pinned operator
                      org, or a SYSTEM org (one that owns a master-admin user).
                      Supports `dry_run` to preview the reassignment counts.

Every destructive call writes a full snapshot to `org_cleanup_audit` (so the
deleted org record itself is recoverable) plus an `admin_activity_log` entry.
"""
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import log_activity, require_master_admin

router = APIRouter()

# Collections we never touch when reassigning org-scoped data.
_SKIP_COLLECTIONS = {
    "organizations", "admin_activity_log", "org_cleanup_audit",
    "system.indexes", "system.views",
}
_ORG_KEYS = ("organization_id", "org_id")
# Child collections surfaced as counts on the cleanup screen.
_COUNT_COLLECTIONS = [
    "users", "sites", "equipment", "members", "crm2_companies",
    "crm2_contracts", "issues", "staff", "suppliers", "purchase_orders",
]


async def _is_system_org(org_id: str) -> bool:
    """A system org owns at least one master-admin user — never deletable."""
    return bool(await db.users.find_one(
        {"organization_id": org_id, "is_master_admin": True}, {"_id": 1}
    ))


async def _org_counts(org_id: str) -> dict:
    out = {}
    for c in _COUNT_COLLECTIONS:
        try:
            n = await db[c].count_documents({"organization_id": org_id})
        except Exception:
            n = 0
        if n:
            out[c] = n
    return out


@router.get("/master-admin/org-cleanup/candidates")
async def cleanup_candidates(q: str = "", user: dict = Depends(get_current_user)) -> dict:
    """List orgs (optionally name-filtered) annotated for the cleanup screen."""
    require_master_admin(user)
    flt: dict = {}
    qs = (q or "").strip()
    if qs:
        import re
        flt["name"] = {"$regex": re.escape(qs), "$options": "i"}
    orgs = await db.organizations.find(flt, {"_id": 0}).sort("created_at", -1).to_list(200)
    items = []
    for o in orgs:
        oid = o.get("id")
        is_sys = await _is_system_org(oid)
        owner = await db.users.find_one(
            {"organization_id": oid, "role": "owner"}, {"_id": 0, "email": 1}
        )
        items.append({
            "id": oid,
            "name": o.get("name"),
            "account_type": o.get("account_type"),
            "owner_email": (owner or {}).get("email"),
            "counts": await _org_counts(oid),
            "is_system_org": is_sys,
            "is_operator_company": bool(o.get("is_operator_company")),
            "protected": is_sys,
        })
    return {"organizations": items, "total": len(items)}


@router.post("/master-admin/org-cleanup/set-operator/{org_id}")
async def set_operator_company(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Pin a single org as THE operator company (the Pulse portal button target)."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await db.organizations.update_many(
        {"is_operator_company": True}, {"$set": {"is_operator_company": False}}
    )
    await db.organizations.update_one({"id": org_id}, {"$set": {"is_operator_company": True}})
    await log_activity(
        "org_set_operator", f"Pinned '{org.get('name')}' as the operator company",
        user.get("email", ""), "organization", org_id,
    )
    return {"ok": True, "operator_org_id": org_id, "operator_org_name": org.get("name")}


@router.post("/master-admin/org-cleanup/merge-delete")
async def merge_delete(body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Reassign org-scoped data to keep_org, then hard-delete the stray orgs.

    Body: { keep_org_id: str, delete_org_ids: [str], dry_run: bool=False }
    """
    require_master_admin(user)
    keep_id = (body.get("keep_org_id") or "").strip()
    delete_ids = [d for d in (body.get("delete_org_ids") or []) if d]
    dry_run = bool(body.get("dry_run"))

    if not keep_id or not delete_ids:
        raise HTTPException(status_code=400, detail="keep_org_id and delete_org_ids are required")
    keep = await db.organizations.find_one({"id": keep_id}, {"_id": 0})
    if not keep:
        raise HTTPException(status_code=404, detail="Keep organisation not found")
    if keep_id in delete_ids:
        raise HTTPException(status_code=400, detail="Cannot delete the org you are keeping")

    # Validate every target BEFORE mutating anything.
    targets = []
    for did in delete_ids:
        org = await db.organizations.find_one({"id": did}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail=f"Organisation {did} not found")
        if await _is_system_org(did):
            raise HTTPException(
                status_code=400,
                detail=f"'{org.get('name')}' is a system org (owns a master-admin user) and cannot be deleted",
            )
        if org.get("is_operator_company"):
            raise HTTPException(
                status_code=400,
                detail=f"'{org.get('name')}' is the pinned operator company — unpin it first",
            )
        targets.append(org)

    collection_names = [c for c in await db.list_collection_names() if c not in _SKIP_COLLECTIONS]

    results = []
    for org in targets:
        did = org["id"]
        reassigned: dict = {}
        for c in collection_names:
            for key in _ORG_KEYS:
                try:
                    match = {key: did}
                    if dry_run:
                        n = await db[c].count_documents(match)
                    else:
                        res = await db[c].update_many(match, {"$set": {key: keep_id}})
                        n = res.modified_count
                except Exception:
                    n = 0
                if n:
                    reassigned[f"{c}.{key}"] = reassigned.get(f"{c}.{key}", 0) + n

        entry = {"org_id": did, "org_name": org.get("name"), "reassigned": reassigned}
        if not dry_run:
            await db.org_cleanup_audit.insert_one({
                "id": str(uuid.uuid4()),
                "action": "merge_delete",
                "keep_org_id": keep_id,
                "keep_org_name": keep.get("name"),
                "deleted_org_snapshot": org,
                "reassigned": reassigned,
                "admin_email": user.get("email", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await db.organizations.delete_one({"id": did})
            await log_activity(
                "org_merge_delete",
                f"Merged '{org.get('name')}' into '{keep.get('name')}' and deleted it "
                f"({sum(reassigned.values())} records reassigned)",
                user.get("email", ""), "organization", did,
            )
        results.append(entry)

    return {
        "dry_run": dry_run,
        "keep_org_id": keep_id,
        "keep_org_name": keep.get("name"),
        "deleted": [] if dry_run else [r["org_id"] for r in results],
        "results": results,
    }
