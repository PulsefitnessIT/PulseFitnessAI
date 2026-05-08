"""Master-admin CRUD for the manufacturer-domain override list.

Iter 238f — surfaced on the Equipment Image Catalogue panel so operators
can plug in a new supplier domain without a release.

Endpoints
---------
* ``GET    /api/master-admin/manufacturer-domains`` — merged list
  (seed + overrides) for display.
* ``POST   /api/master-admin/manufacturer-domains`` — upsert override.
* ``DELETE /api/master-admin/manufacturer-domains/{key}`` — drop an
  override (the seed entry, if any, becomes effective again).
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils import manufacturer_domains_store as store

router = APIRouter(tags=["master-admin"])


@router.get("/master-admin/manufacturer-domains")
async def list_manufacturer_domains(user: dict = Depends(get_current_user)):
    """Merged seed + overrides. Sorted alphabetically by label so the
    admin UI renders a stable list."""
    require_master_admin(user)
    merged = await store.merged_domains()
    rows = list(merged.values())
    rows.sort(key=lambda r: (r.get("label") or r["key"]).lower())
    return {"rows": rows, "seed_count": sum(1 for r in rows if r["source"] == "seed"),
            "override_count": sum(1 for r in rows if r["source"] == "override")}


@router.post("/master-admin/manufacturer-domains")
async def upsert_manufacturer_domain(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    try:
        row = await store.upsert_override(
            key=body.get("key", ""),
            domain=body.get("domain", ""),
            label=body.get("label"),
            enabled=bool(body.get("enabled", True)),
            actor=user.get("email") or user.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "row": row}


@router.delete("/master-admin/manufacturer-domains/{key}")
async def delete_manufacturer_domain(
    key: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    deleted = await store.delete_override(key)
    return {"ok": True, "deleted": deleted}


__all__ = ["router"]
