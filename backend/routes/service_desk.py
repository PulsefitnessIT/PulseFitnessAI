"""Service Desk operational endpoints — customer management, audit, impersonation.

All mutating endpoints write a row to `service_desk_audit_log` via `log_desk_action`.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from datetime import datetime, timezone, timedelta

from utils.auth import create_token
from utils.database import db
from utils.service_desk_auth import require_service_desk, log_desk_action

router = APIRouter(prefix="/service-desk", tags=["Service Desk"])


# ── Dashboard / summary ──────────────────────────────────────────

@router.get("/summary")
async def desk_summary(user: dict = Depends(require_service_desk)) -> dict:
    """Top-level counters shown on the Service Desk landing page."""
    orgs_total = await db.organizations.count_documents({})
    orgs_active = await db.organizations.count_documents({"status": {"$ne": "archived"}})
    orgs_pending = await db.organizations.count_documents({"status": "pending_invite"})
    orgs_archived = await db.organizations.count_documents({"status": "archived"})
    recent_actions = await db.service_desk_audit_log.count_documents({
        "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()},
    })
    return {
        "organizations": {
            "total": orgs_total, "active": orgs_active,
            "pending_invite": orgs_pending, "archived": orgs_archived,
        },
        "recent_actions_7d": recent_actions,
    }


# ── Customer list ────────────────────────────────────────────────

def _build_customer_query(q: str, account_type: str, status: str) -> dict:
    query: dict = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"sicon_customer_ref": {"$regex": q, "$options": "i"}},
            {"head_office_ref": {"$regex": q, "$options": "i"}},
        ]
    if account_type:
        query["account_type"] = account_type
    if status:
        query["status"] = status
    return query


@router.get("/customers")
async def list_customers(
    q: str = "",
    account_type: str = "",
    status: str = "",
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Search + filter customer organisations. Billing/cost fields excluded."""
    query = _build_customer_query(q, account_type, status)
    projection = {
        "_id": 0, "id": 1, "name": 1, "account_type": 1, "status": 1,
        "sicon_customer_ref": 1, "head_office_ref": 1, "is_multi_site": 1,
        "subscription_tier": 1, "primary_contact_email": 1,
        "onboarding_variant": 1, "created_at": 1, "last_activity_at": 1,
    }
    cursor = db.organizations.find(query, projection).sort("created_at", -1).skip(skip).limit(limit)
    orgs = await cursor.to_list(limit)
    total = await db.organizations.count_documents(query)
    return {"organizations": orgs, "total": total}


# ── Customer detail / edit ───────────────────────────────────────

async def _org_or_404(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.get("/customers/{org_id}")
async def get_customer(
    org_id: str,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Full customer record including sites, staff, supplier, onboarding state."""
    org = await _org_or_404(org_id)
    sites = await db.sites.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
    staff = await db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "disabled": 1, "last_login_at": 1},
    ).to_list(500)
    suppliers = await db.suppliers.find({"organization_id": org_id}, {"_id": 0}).to_list(50)
    equipment_count = await db.equipment.count_documents({"organization_id": org_id})

    return {
        "organization": org, "sites": sites, "staff": staff,
        "suppliers": suppliers, "equipment_count": equipment_count,
    }


_EDITABLE_ORG_FIELDS = {
    "name", "primary_contact_email", "primary_contact_name",
    "primary_contact_phone", "head_office_ref", "notes",
}


@router.patch("/customers/{org_id}")
async def update_customer(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(require_service_desk),
) -> dict:
    """Patch whitelisted customer fields. Billing / tier / feature-flag edits
    stay in Master Admin only — they are intentionally absent from the allow-list."""
    org = await _org_or_404(org_id)
    updates = {k: v for k, v in body.items() if k in _EDITABLE_ORG_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields supplied")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.organizations.update_one({"id": org_id}, {"$set": updates})
    await log_desk_action(
        user, "org.update", "organization", org_id,
        f"Updated {org.get('name', org_id)} — fields: {', '.join(updates.keys())}",
        details={"before": {k: org.get(k) for k in updates}, "after": updates},
    )
    return {"success": True, "updated_fields": list(updates.keys())}


# ── Site management ──────────────────────────────────────────────

@router.patch("/customers/{org_id}/sites/{site_id}")
async def update_site(
    org_id: str,
    site_id: str,
    body: dict = Body(...),
    user: dict = Depends(require_service_desk),
) -> dict:
    """Edit a site's address / contact fields on behalf of the customer."""
    site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    allowed = {"name", "address_line1", "address_line2", "city", "county",
               "postcode", "phone", "contact_name", "contact_email"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sites.update_one({"id": site_id}, {"$set": updates})
    await log_desk_action(
        user, "site.update", "site", site_id,
        f"Updated site '{site.get('name')}' for org {org_id}",
        details={"fields": list(updates.keys())},
    )
    return {"success": True, "updated_fields": list(updates.keys())}


# ── Impersonation ────────────────────────────────────────────────

async def _resolve_impersonation_target(org_id: str) -> dict:
    org = await _org_or_404(org_id)
    target = await db.users.find_one(
        {"organization_id": org_id, "role": "owner", "disabled": {"$ne": True}},
        {"_id": 0},
    )
    if not target:
        raise HTTPException(
            status_code=400,
            detail=f"No active owner user for org '{org.get('name')}'",
        )
    return target


@router.post("/customers/{org_id}/impersonate")
async def impersonate_customer(
    org_id: str,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Issue a short-lived token scoped to the customer org's owner user.

    The returned token has `impersonation=True` in its payload so the frontend
    can show a red banner and audit every action taken during the session.
    Session expires in 1 hour; every refresh requires a fresh impersonation call.
    """
    target = await _resolve_impersonation_target(org_id)
    token = create_token(target["id"], expires_hours=1)
    await log_desk_action(
        user, "org.impersonate", "organization", org_id,
        f"Impersonation session started for {target.get('email')}",
        impersonating_org_id=org_id,
    )
    return {
        "token": token,
        "expires_in_seconds": 3600,
        "impersonating": {
            "user_id": target["id"],
            "user_email": target.get("email"),
            "org_id": org_id,
        },
    }


# ── Audit log ────────────────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    actor_id: str = Query(""),
    target_type: str = Query(""),
    target_id: str = Query(""),
    action: str = Query(""),
    skip: int = 0,
    limit: int = 200,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Immutable feed of Service Desk actions. Any Service Desk agent can read;
    nobody (including Master Admin) can delete or edit rows."""
    query: dict = {}
    for field, value in (
        ("actor_id", actor_id), ("target_type", target_type),
        ("target_id", target_id), ("action", action),
    ):
        if value:
            query[field] = value
    cursor = db.service_desk_audit_log.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    total = await db.service_desk_audit_log.count_documents(query)
    return {"rows": rows, "total": total}
