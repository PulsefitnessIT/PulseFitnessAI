"""
Master Admin · CRM Users + Sicon health sub-router.

Iter 216h177 — Extracted from `routes/master_admin.py`.

Routes:
    GET    /master-admin/crm-users
    POST   /master-admin/crm-users
    PATCH  /master-admin/crm-users/{id}
    DELETE /master-admin/crm-users/{id}

    GET    /master-admin/sicon/health
    POST   /master-admin/sicon/test-all
    POST   /master-admin/sicon/poll-all
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import require_master_admin


router = APIRouter()


# ─── CRM User Management (Master Admin) ───

@router.get("/master-admin/crm-users")
async def get_crm_users(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    users = await db.crm_users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(200)
    return {"users": users}


@router.post("/master-admin/crm-users")
async def create_crm_user(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    from routes.crm_auth import crm_hash_password
    email = (data.get("email") or "").strip().lower()
    if not email or not data.get("password"):
        raise HTTPException(status_code=400, detail="Email and password required")
    if await db.crm_users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail=f"CRM user {email} already exists")
    doc = {
        "id": str(uuid.uuid4()), "email": email,
        "full_name": (data.get("full_name") or "").strip(),
        "password": crm_hash_password(data["password"]),
        "role": data.get("role", "user"),
        "avatar_url": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password", None)
    return doc


@router.patch("/master-admin/crm-users/{crm_user_id}")
async def update_crm_user(crm_user_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    existing = await db.crm_users.find_one({"id": crm_user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="CRM user not found")
    updates = {}
    for field in ("full_name", "role"):
        if field in data:
            updates[field] = (data[field] or "").strip()
    if "password" in data and data["password"]:
        from routes.crm_auth import crm_hash_password
        updates["password"] = crm_hash_password(data["password"])
    if updates:
        await db.crm_users.update_one({"id": crm_user_id}, {"$set": updates})
    updated = await db.crm_users.find_one({"id": crm_user_id}, {"_id": 0, "password": 0})
    return updated or {}


@router.delete("/master-admin/crm-users/{crm_user_id}")
async def delete_crm_user(crm_user_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    result = await db.crm_users.delete_one({"id": crm_user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="CRM user not found")
    return {"success": True}


# ── Sicon Integration Health ──────────────────────────────────────

async def _sicon_health_counts(org_id: str) -> dict:
    """Fetch queue + issue counts for one org."""
    pending_q = await db.sicon_sync_queue.count_documents({
        "organization_id": org_id, "resolved_at": None, "retryable": True,
    })
    failed_q = await db.sicon_sync_queue.count_documents({
        "organization_id": org_id, "resolved_at": {"$ne": None},
        "resolution": "retries_exhausted",
    })
    synced = await db.issues.count_documents({
        "organization_id": org_id, "sicon_case_id": {"$exists": True, "$ne": None},
    })
    failed = await db.issues.count_documents({
        "organization_id": org_id, "sicon_sync_status": "failed",
    })
    return {"pending_queue": pending_q, "failed_queue": failed_q,
            "synced_issues": synced, "failed_issues": failed}


def _sicon_health_row(org_id: str, org_name: str, cfg: Optional[dict], counts: dict) -> dict:
    """Build one row of the per-org health response."""
    cfg = cfg or {}
    return {
        "organization_id": org_id, "organization_name": org_name,
        "configured": bool(cfg), "enabled": bool(cfg.get("enabled")),
        "base_url": cfg.get("base_url", ""),
        "connection_status": cfg.get("connection_status", "unknown"),
        "last_tested_at": cfg.get("last_tested_at"),
        "last_poll_at": cfg.get("last_poll_at"),
        "last_poll_counts": cfg.get("last_poll_counts", {}),
        "last_sync_at": cfg.get("last_sync_at"),
        "last_error": cfg.get("last_error", ""),
        **counts,
    }


def _sicon_row_sort_key(r: dict) -> tuple:
    name = r["organization_name"].lower()
    if r["enabled"] and r["connection_status"] == "connected":
        return (0, name)
    if r["enabled"]:
        return (1, name)
    if r["configured"]:
        return (2, name)
    return (3, name)


_SICON_HEALTH_SUMS = {
    "total_pending_queue": "pending_queue",
    "total_failed_queue": "failed_queue",
    "total_synced_issues": "synced_issues",
    "total_failed_issues": "failed_issues",
}


def _sicon_health_totals(rows: list) -> dict:
    totals = {
        "total_orgs": len(rows),
        "configured": sum(1 for r in rows if r["configured"]),
        "enabled": sum(1 for r in rows if r["enabled"]),
        "connected": sum(1 for r in rows if r["connection_status"] == "connected"),
    }
    for out_key, src_key in _SICON_HEALTH_SUMS.items():
        totals[out_key] = sum(r[src_key] for r in rows)
    return totals


@router.get("/master-admin/sicon/health")
async def sicon_health_overview(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate Sicon health across every organization."""
    require_master_admin(user)

    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    configs = await db.sicon_config.find({}, {"_id": 0}).to_list(1000)
    cfg_by_org = {c["organization_id"]: c for c in configs}

    rows = []
    for o in orgs:
        org_id = o["id"]
        cfg = cfg_by_org.get(org_id)
        counts = await _sicon_health_counts(org_id) if cfg else {
            "pending_queue": 0, "failed_queue": 0, "synced_issues": 0, "failed_issues": 0,
        }
        rows.append(_sicon_health_row(org_id, o.get("name", "Unnamed"), cfg, counts))

    rows.sort(key=_sicon_row_sort_key)
    return {"organizations": rows, "totals": _sicon_health_totals(rows)}


@router.post("/master-admin/sicon/test-all")
async def sicon_test_all_connections(user: dict = Depends(get_current_user)) -> dict:
    """Fire a connection test against every Sicon-enabled organization."""
    require_master_admin(user)
    from utils.sicon_common import get_sicon_client

    results = []
    cursor = db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1})
    async for cfg in cursor:
        org_id = cfg.get("organization_id")
        if not org_id:
            continue
        client = await get_sicon_client(org_id)
        if not client:
            continue
        try:
            is_up = await client.ping()
            status = "connected" if is_up else "unreachable"
            await db.sicon_config.update_one(
                {"organization_id": org_id},
                {"$set": {"connection_status": status,
                          "last_tested_at": datetime.now(timezone.utc).isoformat()}}
            )
            results.append({"organization_id": org_id, "connected": is_up, "status": status})
        except Exception as e:
            await db.sicon_config.update_one(
                {"organization_id": org_id},
                {"$set": {"connection_status": "error", "last_error": str(e)[:500]}}
            )
            results.append({"organization_id": org_id, "connected": False, "error": str(e)[:200]})

    return {"tested": len(results), "results": results}


@router.post("/master-admin/sicon/poll-all")
async def sicon_poll_all_orgs(user: dict = Depends(get_current_user)) -> dict:
    """Run an immediate inbound poll across every Sicon-enabled organization."""
    require_master_admin(user)
    from utils.sicon_sync import poll_sicon_updates_for_org, retry_queue_for_org

    results = []
    cursor = db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1})
    async for cfg in cursor:
        org_id = cfg.get("organization_id")
        if not org_id:
            continue
        try:
            poll = await poll_sicon_updates_for_org(org_id)
            retry = await retry_queue_for_org(org_id)
            results.append({"organization_id": org_id, "poll": poll, "retry": retry})
        except Exception as e:
            results.append({"organization_id": org_id, "error": str(e)[:200]})

    return {"polled": len(results), "results": results}
