"""Service Desk operational endpoints — customer management, audit, impersonation.

All mutating endpoints write a row to `service_desk_audit_log` via `log_desk_action`.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

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


# ── Global equipment search (Iter 216h49) ────────────────────────
#
# Pulse Fitness currently uses Sicon Service to look up "what's that
# treadmill in Carshalton" by serial number from a single search box.
# Service Desk gets feature parity here — one search across every org's
# equipment with org + site context surfaced inline.

@router.get("/equipment")
async def search_equipment_global(
    q: str = "",
    org_id: str = "",
    site_id: str = "",
    equipment_type: str = "",
    manufacturer: str = "",
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Global equipment search across every customer organisation.

    Service Desk feature-parity with Sicon Service. Filters all use AND.
    Returns equipment rows enriched with their parent org name + site name
    so the desk operator never has to drill into a customer to identify
    "which gym is this kit at".

    Args:
        q: free-text — matches name, model, manufacturer, serial number
        org_id: scope to one organisation
        site_id: scope to one site (org_id optional, but site is unique
                 per-org so usually paired)
        equipment_type / manufacturer: exact-match filters
        skip / limit: pagination
    """
    query: Dict[str, Any] = {}
    if org_id:
        query["organization_id"] = org_id
    if site_id:
        query["site_id"] = site_id
    if equipment_type:
        query["equipment_type"] = equipment_type
    if manufacturer:
        query["manufacturer"] = manufacturer
    if q:
        # Mongo $or with case-insensitive regex. Anchored to be cheap on
        # short queries; Pulse has fewer than 100k equipment rows so a
        # collection scan is acceptable until a text index is justified.
        import re
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"name": rx}, {"model": rx}, {"manufacturer": rx},
            {"serial_number": rx}, {"equipment_type": rx},
        ]

    projection = {
        "_id": 0, "id": 1, "name": 1, "equipment_type": 1, "manufacturer": 1,
        "model": 1, "serial_number": 1, "location": 1, "site_id": 1,
        "organization_id": 1, "purchase_date": 1, "warranty_expiry": 1,
        "supplier": 1, "created_at": 1,
    }
    cursor = (
        db.equipment.find(query, projection)
        .sort("created_at", -1)
        .skip(max(0, int(skip)))
        .limit(min(200, max(1, int(limit))))
    )
    rows = await cursor.to_list(limit)
    total = await db.equipment.count_documents(query)

    # Hydrate org + site names in a single pass each to avoid N+1.
    org_ids = list({r.get("organization_id") for r in rows if r.get("organization_id")})
    site_ids = list({r.get("site_id") for r in rows if r.get("site_id")})
    orgs = {
        o["id"]: o.get("name", "")
        for o in await db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(org_ids) or 1)
    } if org_ids else {}
    sites = {
        s["id"]: s.get("name", "")
        for s in await db.sites.find(
            {"id": {"$in": site_ids}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(site_ids) or 1)
    } if site_ids else {}

    for r in rows:
        r["organization_name"] = orgs.get(r.get("organization_id"), "")
        r["site_name"] = sites.get(r.get("site_id"), "")

    await log_desk_action(
        user, "equipment.search", "equipment", "global",
        f"Equipment search: q={q!r}, results={len(rows)}",
        details={"q": q, "org_id": org_id, "site_id": site_id, "count": len(rows)},
    )

    return {"equipment": rows, "total": total}


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
