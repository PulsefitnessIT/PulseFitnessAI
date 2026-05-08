"""Saved searches / smart segments (iter 215c0).

A saved search is a named filter set the user can re-apply later.
Smart segments are saved searches with `auto_refresh=true` — they are
re-evaluated each time they're loaded (vs static lists which are
snapshotted; static lists already exist for Marketing). Frontend
consumers: CRM Contacts, CRM Pipeline, Memberships Members.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/saved-searches", tags=["saved searches"])

ALLOWED_MODULES = {"crm_contacts", "crm_pipeline", "crm_companies",
                   "memberships_members", "memberships_bookings",
                   "marketing_audiences"}


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("")
async def list_searches(module: str | None = None, user: dict = Depends(get_current_user)) -> dict:
    """List the current user's saved searches plus org-shared ones."""
    org_id = user.get("organization_id")
    q: dict = {
        "$or": [
            {"user_id": user["id"]},
            {"organization_id": org_id, "shared": True},
        ]
    }
    if module:
        if module not in ALLOWED_MODULES:
            raise HTTPException(status_code=400, detail="Unknown module")
        q["module"] = module
    cursor = db.saved_searches.find(q, {"_id": 0}).sort("name", 1)
    return {"items": await cursor.to_list(200)}


@router.post("")
async def create_search(payload: dict, user: dict = Depends(get_current_user)) -> dict:
    name = (payload.get("name") or "").strip()
    module = payload.get("module")
    if not name or len(name) > 80:
        raise HTTPException(status_code=400, detail="Name is required (1–80 chars)")
    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=400, detail=f"module must be one of: {sorted(ALLOWED_MODULES)}")
    filters = payload.get("filters") or {}
    if not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "module": module,
        "filters": filters,
        "shared": bool(payload.get("shared", False)),
        "auto_refresh": bool(payload.get("auto_refresh", True)),
        "user_id": user["id"],
        "user_email": user.get("email"),
        "organization_id": user.get("organization_id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.saved_searches.insert_one(doc)
    return _strip(doc)


@router.put("/{search_id}")
async def update_search(search_id: str, payload: dict, user: dict = Depends(get_current_user)) -> dict:
    existing = await db.saved_searches.find_one(
        {"id": search_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Saved search not found")
    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name or len(new_name) > 80:
            raise HTTPException(status_code=400, detail="Name must be 1–80 chars")
        update["name"] = new_name
    if "filters" in payload:
        if not isinstance(payload["filters"], dict):
            raise HTTPException(status_code=400, detail="filters must be an object")
        update["filters"] = payload["filters"]
    if "shared" in payload:
        update["shared"] = bool(payload["shared"])
    if "auto_refresh" in payload:
        update["auto_refresh"] = bool(payload["auto_refresh"])
    await db.saved_searches.update_one({"id": search_id}, {"$set": update})
    return await db.saved_searches.find_one({"id": search_id}, {"_id": 0})


@router.delete("/{search_id}")
async def delete_search(search_id: str, user: dict = Depends(get_current_user)) -> dict:
    res = await db.saved_searches.delete_one({"id": search_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"ok": True}
