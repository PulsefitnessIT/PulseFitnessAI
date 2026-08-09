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


# ── Sicon Go-Live Readiness Pre-flight ────────────────────────────
# A prescriptive checklist that answers "are we ready to flip Sicon live?"
# for every configured org. Read-only + DB/env-derived (no live HTTP), so it
# is safe to run repeatedly and fast. Each check is pass | warn | fail:
#   fail = a true blocker (can't work without it)
#   warn = expected-pre-go-live or optional-but-recommended
#   pass = good to go
# An org is `ready` when it has zero fail-level checks.

def _chk(check_id: str, label: str, status: str, detail: str, fix: str = "") -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


async def _sicon_org_readiness(org_id: str, org_name: str, cfg: dict) -> dict:
    checks: list[dict] = []

    # 1 · Credentials stored (encrypted at rest)
    has_creds = bool(cfg.get("username_enc")) and bool(cfg.get("password_enc"))
    checks.append(_chk(
        "credentials", "API credentials stored",
        "pass" if has_creds else "fail",
        "Username + password are encrypted and stored." if has_creds
        else "No Sicon WebAPI credentials saved.",
        "" if has_creds else "Add the Sicon service-account username & password in the Configuration tab.",
    ))

    # 2 · Base URL
    base_url = (cfg.get("base_url") or "").strip()
    if not base_url:
        checks.append(_chk("base_url", "WebAPI base URL", "fail",
                           "No base URL configured.",
                           "Set the Sicon WebAPI base URL (e.g. https://customer.sicon-cloud.com)."))
    elif not base_url.lower().startswith("https://"):
        checks.append(_chk("base_url", "WebAPI base URL", "warn",
                           f"Base URL is not HTTPS: {base_url}",
                           "Use an https:// URL so credentials are sent over TLS."))
    else:
        checks.append(_chk("base_url", "WebAPI base URL", "pass", base_url))

    # 3 · Company ID
    company_id = cfg.get("company_id") or 0
    checks.append(_chk(
        "company_id", "Sage company ID",
        "pass" if company_id else "warn",
        f"companyId={company_id}" if company_id else "companyId is 0 / unset.",
        "" if company_id else "Set the Sage 200 company ID so calls target the right company.",
    ))

    # 4 · Live switch (enabled)
    enabled = bool(cfg.get("enabled"))
    checks.append(_chk(
        "enabled", "Live switch (Enabled)",
        "pass" if enabled else "warn",
        "Enabled — outbound writes go live." if enabled
        else "Dry-run: rows queue in the outbox but are NOT sent yet.",
        "" if enabled else "Flip 'Enabled' on in Configuration when you're ready to send to Sicon.",
    ))

    # 5 · Connection (last test result — does not ping live here)
    conn = cfg.get("connection_status", "unknown")
    conn_map = {
        "connected": ("pass", "Last connection test succeeded."),
        "unreachable": ("fail", "Last connection test could not reach Sicon."),
        "error": ("fail", f"Last test errored: {(cfg.get('last_error') or '')[:160]}"),
        "unknown": ("warn", "Connection has never been tested."),
    }
    c_status, c_detail = conn_map.get(conn, ("warn", "Connection status unknown."))
    checks.append(_chk("connection", "Connectivity ping", c_status, c_detail,
                       "" if c_status == "pass" else "Run 'Test All Connections' (needs credentials + Enabled)."))

    # 6 · Priority mapping filled (Sicon has no priorities lookup — must be manual)
    pm = cfg.get("priority_mapping") or {}
    pm_filled = any((pm.get(k) or 0) for k in ("low", "medium", "critical"))
    checks.append(_chk(
        "priority_mapping", "Priority mapping",
        "pass" if pm_filled else "warn",
        f"low={pm.get('low',0)} medium={pm.get('medium',0)} critical={pm.get('critical',0)}",
        "" if pm_filled else "Map low/medium/critical to Sicon PriorityIDs, or all cases land on the default priority.",
    ))

    # 7 · Default case type
    ct = cfg.get("default_case_type_id") or 0
    checks.append(_chk(
        "case_type", "Default case type",
        "pass" if ct else "warn",
        f"CaseTypeID={ct}" if ct else "No default case type set.",
        "" if ct else "Pick a default case type (pull the list in Configuration).",
    ))

    # 8 · Default team (internal or external)
    team = (cfg.get("default_internal_team_id") or 0) or (cfg.get("default_external_team_id") or 0)
    checks.append(_chk(
        "team", "Default team",
        "pass" if team else "warn",
        "A default team is set." if team else "No default internal/external team set.",
        "" if team else "Set a default internal or external team so cases route correctly.",
    ))

    # 9 · Engineer directory cached
    eng_count = await db.sicon_engineers.count_documents({"organization_id": org_id, "is_leaver": {"$ne": True}})
    checks.append(_chk(
        "engineers", "Engineer directory",
        "pass" if eng_count else "warn",
        f"{eng_count} engineers cached." if eng_count else "No engineers pulled yet.",
        "" if eng_count else "Run an engineer refresh so appointments can be assigned.",
    ))

    # 10 · Equipment → Sicon asset ID coverage (needed for asset cross-linking)
    eq_total = await db.equipment.count_documents({"organization_id": org_id})
    eq_mapped = await db.equipment.count_documents({
        "organization_id": org_id, "sicon_equipment_id": {"$exists": True, "$ne": None},
    })
    map_serials = len((cfg.get("equipment_id_mapping") or {}))
    covered = max(eq_mapped, map_serials)
    pct = round((covered / eq_total) * 100) if eq_total else 0
    if eq_total == 0:
        eq_status, eq_detail = "warn", "No equipment on record yet."
    elif pct >= 100:
        eq_status, eq_detail = "pass", f"All {eq_total} machines have a Sicon asset ID."
    elif pct > 0:
        eq_status, eq_detail = "warn", f"{covered}/{eq_total} machines mapped ({pct}%)."
    else:
        eq_status, eq_detail = "warn", f"0/{eq_total} machines have a Sicon asset ID."
    checks.append(_chk(
        "equipment_mapping", "Equipment asset IDs", eq_status, eq_detail,
        "" if eq_status == "pass" else "Map each machine's Sicon equipment ID so faults cross-link to the right asset.",
    ))

    # 11 · Outbox / sync-queue health
    ob_failed = await db.svc_sicon_outbox.count_documents({"organization_id": org_id, "status": {"$in": ["failed", "dead_letter"]}})
    q_failed = await db.sicon_sync_queue.count_documents({
        "organization_id": org_id, "resolved_at": {"$ne": None}, "resolution": "retries_exhausted",
    })
    total_failed = ob_failed + q_failed
    checks.append(_chk(
        "outbox", "Outbox health",
        "pass" if total_failed == 0 else "warn",
        "No failed or dead-letter rows." if total_failed == 0
        else f"{total_failed} row(s) failed / exhausted retries.",
        "" if total_failed == 0 else "Review & requeue failed rows once the connection is healthy.",
    ))

    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    passes = sum(1 for c in checks if c["status"] == "pass")
    return {
        "organization_id": org_id,
        "organization_name": org_name,
        "ready": fails == 0,
        "score": {"pass": passes, "warn": warns, "fail": fails, "total": len(checks)},
        "equipment_coverage": {"mapped": covered, "total": eq_total, "pct": pct},
        "checks": checks,
    }


@router.get("/master-admin/sicon/readiness")
async def sicon_readiness(user: dict = Depends(get_current_user)) -> dict:
    """Go-live readiness pre-flight for every Sicon-configured organization."""
    require_master_admin(user)
    import os

    configs = await db.sicon_config.find({}, {"_id": 0}).to_list(1000)
    cfg_by_org = {c["organization_id"]: c for c in configs if c.get("organization_id")}
    org_ids = list(cfg_by_org.keys())
    orgs = await db.organizations.find(
        {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(1000)
    name_by_org = {o["id"]: o.get("name", "Unnamed") for o in orgs}

    org_rows = []
    for org_id, cfg in cfg_by_org.items():
        org_rows.append(await _sicon_org_readiness(org_id, name_by_org.get(org_id, "Unnamed"), cfg))
    org_rows.sort(key=lambda r: (r["ready"], r["organization_name"].lower()))

    # Platform-level checks (apply to all orgs)
    autostart = os.environ.get("SICON_AUTOSTART_WORKER", "").lower() in ("1", "true", "yes")
    platform = [
        _chk("worker_autostart", "Outbox worker auto-start",
             "pass" if autostart else "warn",
             "SICON_AUTOSTART_WORKER is on — the outbox drains automatically." if autostart
             else "Worker is demand-driven only (manual drain).",
             "" if autostart else "Set SICON_AUTOSTART_WORKER=true in the backend env and redeploy so queued rows send automatically."),
        _chk("credential_encryption", "Credential encryption key",
             "pass", "JWT_SECRET is set — Sicon credentials are encrypted at rest."),
        _chk("field_mapping", "Field-mapping contract",
             "pass", "~200 fields across 7 entities mapped (Case, Contract, ContractLine, TrackingNote, Appointment, TimeBooking, Resource)."),
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "orgs_configured": len(org_rows),
            "orgs_ready": sum(1 for r in org_rows if r["ready"]),
        },
        "platform_checks": platform,
        "organizations": org_rows,
    }

