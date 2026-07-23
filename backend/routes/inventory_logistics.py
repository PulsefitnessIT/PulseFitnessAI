"""
Inventory & Distribution — PHASE 2 · Logistics install-team portal + scoped logins.

A dedicated, VIEW-ONLY portal for the logistics/installation team. Owners/managers
provision separate logins (role='logistics') from the Inventory module Settings; those
users log in through the normal /api/auth/login and are routed to /logistics, where they
see their organisation's upcoming installs and the full Install pack (site survey, H&S,
drawings, docs). Logistics users are read-only everywhere else by construction —
_require_ops_role (owner/manager/admin only) already blocks every write endpoint.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body

from utils.auth import get_current_user, get_current_user_portal, hash_password
from utils.database import db
from routes.inventory_distribution import _of, _now, _uid, _audit, _require_ops_role
from routes.inventory_allocation import install_pack as _install_pack_impl, commission_install

router = APIRouter(prefix="/inventory/logistics", tags=["Inventory & Distribution · Logistics Portal"])
logger = logging.getLogger(__name__)

LOGISTICS_ROLE = "logistics"


def require_logistics_or_ops(user=Depends(get_current_user_portal)):
    """Allow the logistics role OR the operational roles (owner/manager/admin) so
    owners keep full Distribution access while logistics staff use the portal."""
    role = (user.get("role") or "").lower()
    if (user.get("is_master_admin") or user.get("is_inventory") or user.get("is_service_desk")
            or role in ("owner", "manager", "master_admin", "master", "admin", LOGISTICS_ROLE)):
        return user
    raise HTTPException(status_code=403, detail="Logistics portal access required")


# ──────────────────────────── Provisioning (owners/managers only) ────────────────────────────
def _clean_user(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "email": u.get("email"),
        "full_name": u.get("full_name"),
        "status": u.get("status", "active"),
        "created_at": u.get("created_at"),
        "last_login_at": u.get("last_login_at"),
    }


@router.get("/users")
async def list_logistics_users(user=Depends(get_current_user)):
    _require_ops_role(user)
    rows = await db.users.find(
        {"organization_id": user.get("organization_id"), "role": LOGISTICS_ROLE},
        {"_id": 0, "password": 0},
    ).sort("created_at", -1).to_list(200)
    return {"users": [_clean_user(u) for u in rows]}


@router.post("/users")
async def create_logistics_user(body: dict = Body(...), user=Depends(get_current_user)):
    _require_ops_role(user)
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    full_name = (body.get("full_name") or "").strip() or email.split("@")[0]
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "A valid email is required")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(409, "An account with this email already exists")
    uid = _uid()
    doc = {
        "id": uid,
        "email": email,
        "password": hash_password(password),
        "full_name": full_name,
        "role": LOGISTICS_ROLE,
        "organization_id": user.get("organization_id"),
        "status": "active",
        "created_by": user.get("email"),
        "created_at": _now(),
        "password_updated_at": _now(),
    }
    await db.users.insert_one({**doc})
    await _audit(user, "logistics_user_created", "user", uid, {"email": email})
    return {"ok": True, "user": _clean_user(doc)}


async def _get_logistics_user(user_id: str, user: dict) -> dict:
    u = await db.users.find_one(
        {"id": user_id, "organization_id": user.get("organization_id"), "role": LOGISTICS_ROLE})
    if not u:
        raise HTTPException(404, "Logistics user not found")
    return u


@router.post("/users/{user_id}/status")
async def set_logistics_user_status(user_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    _require_ops_role(user)
    await _get_logistics_user(user_id, user)
    status = (body.get("status") or "").strip()
    if status not in ("active", "disabled"):
        raise HTTPException(400, "status must be 'active' or 'disabled'")
    await db.users.update_one({"id": user_id}, {"$set": {"status": status, "updated_at": _now()}})
    await _audit(user, "logistics_user_status", "user", user_id, {"status": status})
    return {"ok": True, "status": status}


@router.post("/users/{user_id}/reset-password")
async def reset_logistics_password(user_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    _require_ops_role(user)
    await _get_logistics_user(user_id, user)
    password = (body.get("password") or "").strip()
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password": hash_password(password), "password_updated_at": _now(),
                  "must_change_password": False, "updated_at": _now()}})
    await _audit(user, "logistics_user_password_reset", "user", user_id, {})
    return {"ok": True}


# ──────────────────────────── Portal (logistics OR ops) — VIEW ONLY ────────────────────────────
@router.get("/installs")
async def logistics_installs(user=Depends(require_logistics_or_ops)):
    """Upcoming installs for the logistics team's organisation (view-only), plus
    installs completed in the last 7 days so the team can review the sign-off."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    flt = {**_of(user), "$or": [
        {"status": {"$in": ["awaiting_installation", "installation_in_progress"]}},
        {"status": "active", "installed_at": {"$gte": cutoff}},
    ]}
    rows = await db.dealer_customer_allocations.find(flt, {"_id": 0}).sort("planned_install_date", 1).limit(500).to_list(500)
    return {"installs": rows}


@router.get("/installs/{alloc_id}/pack")
async def logistics_install_pack(alloc_id: str, user=Depends(require_logistics_or_ops)):
    """Full install pack (survey + H&S + drawings + docs) for a scheduled install."""
    return await _install_pack_impl(alloc_id, user)


@router.post("/installs/{alloc_id}/start")
async def logistics_start_install(alloc_id: str, user=Depends(require_logistics_or_ops)):
    """Mark an install as in-progress when the team arrives on site."""
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id})
    if not a:
        raise HTTPException(404, "Install not found")
    if a.get("status") == "active":
        raise HTTPException(409, "This installation is already completed")
    await db.dealer_customer_allocations.update_one(
        {"id": alloc_id}, {"$set": {"status": "installation_in_progress", "installation_started_at": _now(), "updated_at": _now()}})
    await _audit(user, "installation_started", "allocation", alloc_id, {})
    return {"ok": True, "status": "installation_in_progress"}


@router.post("/installs/{alloc_id}/complete")
async def logistics_complete_install(alloc_id: str, body: dict = Body(...), user=Depends(require_logistics_or_ops)):
    """On-site completion + CUSTOMER SIGN-OFF. Records the signature and H&S
    acknowledgement, then commissions the asset and activates warranty."""
    customer_name = (body.get("customer_name") or "").strip()
    signature = (body.get("customer_signature") or "").strip()
    if not customer_name:
        raise HTTPException(400, "Customer name is required for sign-off")
    if not signature.startswith("data:image"):
        raise HTTPException(400, "A customer signature is required for sign-off")
    if not body.get("hs_acknowledged"):
        raise HTTPException(400, "The Health & Safety acknowledgement must be confirmed")
    if not body.get("customer_acceptance"):
        raise HTTPException(400, "Customer acceptance is required to complete the install")
    data = {
        "engineer_name": (body.get("installer_name") or user.get("full_name") or user.get("email")),
        "checklist": body.get("checklist") or {},
        "condition": body.get("condition") or "Good",
        "notes": body.get("notes"),
        "customer_acceptance": True,
        "customer_name": customer_name,
        "customer_signature": signature,
        "hs_acknowledged": True,
    }
    return await commission_install(alloc_id, data, user)
