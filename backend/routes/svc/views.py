"""
GymAxis Service Operations — Saved Views.

Iter 216y (Phase 6+).

Per-org, per-page saved filter sets so operators can pin "Pulse — P1 only"
or "PPM this week" and reload them with one click. Stored in `svc_saved_views`.

Endpoints:
  GET    /api/svc/views?kind=desk|reports
  POST   /api/svc/views          {name, kind, filters, range_id?, route?}
  PUT    /api/svc/views/{id}     same body
  DELETE /api/svc/views/{id}
"""
__integration_fields__ = {
    "saved_views.id":              "gymaxis_only: local uuid",
    "saved_views.organization_id": "gymaxis_only: tenant scoping",
    "saved_views.kind":            "gymaxis_only: desk | reports",
    "saved_views.name":            "gymaxis_only: operator-facing label",
    "saved_views.filters":         "gymaxis_only: filter dict (status/priority/case_type/search/etc.)",
    "saved_views.range_id":        "gymaxis_only: 7|30|90 day window selector",
    "saved_views.created_by_id":   "gymaxis_only: who saved the view",
}

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user

router = APIRouter(prefix="/svc/views", tags=["Service Ops · Saved Views"])

_ALLOWED_KINDS = {"desk", "reports", "scheduler", "parts"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _validate(data: dict) -> dict:
    name = ((data or {}).get("name") or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(400, "name is required (≤80 chars)")
    kind = ((data or {}).get("kind") or "reports").lower()
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(_ALLOWED_KINDS)}")
    filters = (data or {}).get("filters") or {}
    if not isinstance(filters, dict):
        raise HTTPException(400, "filters must be an object")
    return {
        "name": name,
        "kind": kind,
        "filters": filters,
        "range_id": ((data or {}).get("range_id") or "").strip(),
        "route": ((data or {}).get("route") or "").strip(),
    }


@router.get("")
async def list_views(
    kind: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    q: dict = {**of}
    if kind:
        if kind not in _ALLOWED_KINDS:
            raise HTTPException(400, f"kind must be one of {sorted(_ALLOWED_KINDS)}")
        q["kind"] = kind
    rows = await db.svc_saved_views.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    return {"views": rows, "count": len(rows)}


@router.post("")
async def create_view(data: dict, user=Depends(get_current_user)):
    of = _of(user)
    valid = _validate(data)
    # Soft uniqueness guard — operators can override by editing.
    existing = await db.svc_saved_views.find_one(
        {**of, "kind": valid["kind"], "name": valid["name"]},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(409, "A saved view with that name already exists")
    row = {
        "id": str(uuid.uuid4()),
        **of,
        **valid,
        "created_by_id": user["id"],
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_saved_views.insert_one(row)
    row.pop("_id", None)
    return row


@router.put("/{view_id}")
async def update_view(view_id: str, data: dict, user=Depends(get_current_user)):
    of = _of(user)
    valid = _validate(data)
    res = await db.svc_saved_views.update_one(
        {**of, "id": view_id},
        {"$set": {**valid, "updated_at": _now(), "updated_by_id": user["id"]}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Saved view not found")
    row = await db.svc_saved_views.find_one({**of, "id": view_id}, {"_id": 0})
    return row


@router.delete("/{view_id}")
async def delete_view(view_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_saved_views.delete_one({**of, "id": view_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Saved view not found")
    return {"ok": True, "id": view_id}


__all__ = ["router"]
