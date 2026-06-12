"""Iter 220ea·20 — Engineer App Phase 5 · Parts Catalogue (browse/edit).

Server-side paginated catalogue over the existing ``svc_parts``
collection (no duplicate records). Powers the desktop/admin catalogue
browser: search, facet filters (category / manufacturer / supplier /
status), sort, single-part edit and bulk status changes.

Bulk import lives in ``parts_import.py``. Van stock / usage lives in
``engineer_stock.py``. Allocation lives in ``parts.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/svc/parts/catalogue", tags=["Service Ops · Parts Catalogue"])

EDITABLE = {"name", "description", "manufacturer", "mfr_part_number", "supplier",
            "supplier_part_number", "category", "cost", "list_price",
            "reorder_threshold", "reorder_qty", "reorder_max", "bin_location", "notes",
            "compatible_models", "status", "active", "cover_category"}
NUMERIC = {"cost", "list_price"}
INT_FIELDS = {"reorder_threshold", "reorder_qty", "reorder_max"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _can_manage(user: dict) -> bool:
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("account_type") == "gymaxis_admin"
        or (user.get("role") or "") in {"owner", "owner_admin", "manager"}
    )


def _can_see_cost(user: dict) -> bool:
    return _can_manage(user)


@router.get("")
async def browse_catalogue(
    search: str = Query(""),
    category: str = Query(""),
    manufacturer: str = Query(""),
    supplier: str = Query(""),
    status: str = Query("active"),  # active|inactive|obsolete|all
    sort: str = Query("name"),      # name|sku|cost|price|updated
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Paginated catalogue with facets — never loads everything at once."""
    of = _of(user)
    q: dict = {**of}
    st = (status or "active").lower()
    if st == "active":
        q["active"] = {"$ne": False}
    elif st == "inactive":
        q["active"] = False
    elif st == "obsolete":
        q["status"] = "obsolete"
    if search:
        q["$or"] = [
            {"sku": safe_regex(search)},
            {"name": safe_regex(search)},
            {"manufacturer": safe_regex(search)},
            {"mfr_part_number": safe_regex(search)},
        ]
    if category:
        q["category"] = category
    if manufacturer:
        q["manufacturer"] = manufacturer
    if supplier:
        q["supplier"] = supplier

    sort_map = {"name": ("name", 1), "sku": ("sku", 1), "cost": ("cost", -1),
                "price": ("list_price", -1), "updated": ("updated_at", -1)}
    sf, sd = sort_map.get((sort or "name").lower(), ("name", 1))

    total = await db.svc_parts.count_documents(q)
    show_cost = _can_see_cost(user)
    proj = {"_id": 0}
    if not show_cost:
        proj["cost"] = 0
    items = await db.svc_parts.find(q, proj) \
        .sort([(sf, sd)]).skip((page - 1) * page_size).limit(page_size) \
        .to_list(page_size)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "show_cost": show_cost,
        "can_manage": _can_manage(user),
    }


@router.get("/facets")
async def catalogue_facets(user=Depends(get_current_user)):
    """Distinct categories / manufacturers / suppliers for filter chips."""
    of = _of(user)
    cats, mans, sups = await _distinct(of, "category"), await _distinct(of, "manufacturer"), await _distinct(of, "supplier")
    total = await db.svc_parts.count_documents(of)
    return {"categories": cats, "manufacturers": mans, "suppliers": sups, "total": total}


async def _distinct(of: dict, field: str) -> list[str]:
    vals = await db.svc_parts.distinct(field, of)
    return sorted([v for v in vals if v])[:200]


@router.get("/{part_id}")
async def get_part(part_id: str, user=Depends(get_current_user)):
    of = _of(user)
    proj = {"_id": 0}
    if not _can_see_cost(user):
        proj["cost"] = 0
    part = await db.svc_parts.find_one({**of, "id": part_id}, proj)
    if not part:
        raise HTTPException(404, "Part not found")
    return part


@router.patch("/{part_id}")
async def edit_part(part_id: str, body: dict, user=Depends(get_current_user)):
    """Edit a catalogue part (owner/admin/manager only)."""
    of = _of(user)
    if not _can_manage(user):
        raise HTTPException(403, "Editing the catalogue requires an owner/admin/manager role")
    updates: dict = {}
    for k, v in (body or {}).items():
        if k not in EDITABLE:
            continue
        if k in NUMERIC:
            updates[k] = float(v or 0)
        elif k in INT_FIELDS:
            updates[k] = int(v or 0)
        elif k == "compatible_models" and isinstance(v, str):
            updates[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            updates[k] = v
    if not updates:
        raise HTTPException(400, "No editable fields supplied")
    updates["updated_at"] = _now()
    res = await db.svc_parts.update_one({**of, "id": part_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Part not found")
    proj = {"_id": 0}
    if not _can_see_cost(user):
        proj["cost"] = 0
    return await db.svc_parts.find_one({**of, "id": part_id}, proj)


@router.post("/bulk-status")
async def bulk_status(body: dict, user=Depends(get_current_user)):
    """Activate / deactivate / mark obsolete a set of parts."""
    of = _of(user)
    if not _can_manage(user):
        raise HTTPException(403, "Bulk actions require an owner/admin/manager role")
    ids = body.get("ids") or []
    action = (body.get("action") or "").lower()
    if not ids:
        raise HTTPException(400, "No part ids supplied")
    if action == "activate":
        upd = {"active": True, "status": "active"}
    elif action == "deactivate":
        upd = {"active": False, "status": "inactive"}
    elif action == "obsolete":
        upd = {"active": False, "status": "obsolete"}
    else:
        raise HTTPException(422, "action must be activate|deactivate|obsolete")
    upd["updated_at"] = _now()
    res = await db.svc_parts.update_many(
        {**of, "id": {"$in": ids}}, {"$set": upd})
    return {"ok": True, "updated": res.modified_count}


__all__ = ["router"]
