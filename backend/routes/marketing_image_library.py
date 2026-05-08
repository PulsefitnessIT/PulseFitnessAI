"""Master-admin marketing image library (Iter 238f).

Pulse Fitness operators who add the Marketing bolt-on get a curated,
brand-aligned image library out of the box — sourced from the master
admin so every Marketing Suite tenant draws from the same pool when
building campaigns.

Endpoints
---------
* ``GET    /api/master-admin/marketing-image-library``
    List all images (master admin view).
* ``POST   /api/master-admin/marketing-image-library``
    Add an image entry: ``{url, label, tags?, category?}``.
* ``DELETE /api/master-admin/marketing-image-library/{id}``
    Remove an entry.

* ``GET    /api/marketing/image-library``
    Tenant-facing view — returns all enabled entries for any user
    whose org has ``marketing`` module access (Pulse Pro or active
    Marketing trial). Pulled by the Marketing Creative Studio's
    "Brand library" picker.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db
from utils.module_access import has_module

router = APIRouter(tags=["marketing-image-library"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_url(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        raise HTTPException(400, "url required")
    if not u.startswith(("http://", "https://", "data:")):
        raise HTTPException(400, "url must be http(s)://… or data:image/…")
    return u


# ── Master admin (CRUD) ───────────────────────────────────────────────


@router.get("/master-admin/marketing-image-library")
async def list_images_admin(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    rows = await db.marketing_image_library.find(
        {}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=2000)
    return {"rows": rows, "count": len(rows)}


@router.post("/master-admin/marketing-image-library")
async def add_image_admin(body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    url = _normalise_url(body.get("url", ""))
    label = (body.get("label") or "").strip()[:120] or "Untitled"
    raw_tags = body.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",")]
    tags = [t.strip().lower() for t in raw_tags if t and t.strip()][:20]
    category = (body.get("category") or "general").strip().lower()[:40]

    row = {
        "id": str(uuid.uuid4()),
        "url": url,
        "label": label,
        "tags": tags,
        "category": category,
        "enabled": bool(body.get("enabled", True)),
        "created_at": _now(),
        "created_by": user.get("email") or user.get("id"),
    }
    await db.marketing_image_library.insert_one(row.copy())
    row.pop("_id", None)
    return {"ok": True, "row": row}


@router.delete("/master-admin/marketing-image-library/{img_id}")
async def delete_image_admin(
    img_id: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    res = await db.marketing_image_library.delete_one({"id": img_id})
    if not res.deleted_count:
        raise HTTPException(404, "Image not found")
    return {"ok": True}


# ── Tenant-facing read ────────────────────────────────────────────────


@router.get("/marketing/image-library")
async def list_images_tenant(user: dict = Depends(get_current_user)):
    """Read-only feed for any operator whose org has Marketing access."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "Missing organization context")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found")
    if not has_module(user, org, "marketing"):
        raise HTTPException(403, "Marketing module not active for this organisation")
    rows = await db.marketing_image_library.find(
        {"enabled": True}, {"_id": 0, "created_by": 0},
    ).sort("created_at", -1).to_list(length=2000)
    return {"rows": rows, "count": len(rows)}


__all__ = ["router"]
