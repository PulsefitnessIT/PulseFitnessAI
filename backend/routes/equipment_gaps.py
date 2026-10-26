"""Missing Information — find and fill gaps against the Sicon essentials.

Messy imports often land assets without a Customer Ref, Location, Make,
Model or a real Serial Number. These endpoints list incomplete assets per
organisation / site and let staff fill the blanks in a grid (single cell or
"apply to all at this site").
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from utils.sicon_equipment import (
    EDITABLE_FIELDS, ESSENTIAL_FIELDS, clean_value, incomplete_query,
    missing_essentials, with_next_service,
)

router = APIRouter()

_BULK_FIELDS = {
    "sicon_customer_ref", "location", "sub_location", "manufacturer", "service_interval",
    "service_period", "equipment_group", "sla_name", "contract_number", "service_template",
    "last_service_date", "install_date",
}
_PROJECTION = {"_id": 0, **{f: 1 for f in (
    "id", "organization_id", "site_id", "equipment_type", "category", "status",
    *EDITABLE_FIELDS, "next_service_auto",
)}}
_ORG_REF_FIELDS = ("customer_account_number", "sage_customer_number", "sicon_customer_number")


def _is_staff(user: dict) -> bool:
    from routes.pulse_master_admin import _require_pulse_or_master
    try:
        _require_pulse_or_master(user)
        return True
    except HTTPException:
        return False


def _scope_org(user: dict, organization_id: Optional[str]) -> str:
    if _is_staff(user):
        if not organization_id:
            raise HTTPException(400, "organization_id is required")
        return organization_id
    own = user.get("organization_id")
    if not own:
        raise HTTPException(403, "No organisation context")
    if organization_id and organization_id != own:
        raise HTTPException(403, "Not allowed for this organisation")
    return own


def _org_ref(org: dict) -> str:
    return next((str(org.get(f)).strip() for f in _ORG_REF_FIELDS if org.get(f)), "")


async def backfill_customer_refs(org_id: str) -> int:
    """Copy the site / organisation account number onto assets missing a Customer Ref."""
    blank = {"$or": [{"sicon_customer_ref": {"$exists": False}}, {"sicon_customer_ref": None}, {"sicon_customer_ref": ""}]}
    n = 0
    async for s in db.sites.find({"organization_id": org_id}, {"_id": 0, "id": 1, "invoice_customer_ref": 1, "sicon_customer_ref": 1}):
        ref = (s.get("invoice_customer_ref") or s.get("sicon_customer_ref") or "").strip()
        if ref:
            r = await db.equipment.update_many({"organization_id": org_id, "site_id": s["id"], **blank}, {"$set": {"sicon_customer_ref": ref}})
            n += r.modified_count
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, **{f: 1 for f in _ORG_REF_FIELDS}}) or {}
    ref = _org_ref(org)
    if ref:
        r = await db.equipment.update_many({"organization_id": org_id, **blank}, {"$set": {"sicon_customer_ref": ref}})
        n += r.modified_count
    return n


def _summarise(items: list) -> dict:
    by_field = {f: 0 for f, _ in ESSENTIAL_FIELDS}
    for it in items:
        for f in it["missing"]:
            by_field[f] += 1
    complete = sum(1 for it in items if not it["missing"])
    total = len(items)
    return {"total": total, "complete": complete, "incomplete": total - complete,
            "percent_complete": round(100 * complete / total) if total else 100, "by_field": by_field}


@router.get("/equipment-gaps/fields")
async def gap_fields(user: dict = Depends(get_current_user)) -> dict:
    return {"essentials": [{"field": f, "label": lb} for f, lb in ESSENTIAL_FIELDS],
            "editable": list(EDITABLE_FIELDS), "bulk": sorted(_BULK_FIELDS)}


@router.get("/equipment-gaps/scopes")
async def gap_scopes(user: dict = Depends(get_current_user)) -> dict:
    """Organisations that still have incomplete assets (staff only)."""
    if not _is_staff(user):
        raise HTTPException(403, "Staff access required")
    pipeline = [{"$match": incomplete_query()}, {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}}, {"$limit": 300}]
    rows = await db.equipment.aggregate(pipeline).to_list(300)
    out = []
    for r in rows:
        oid = r["_id"]
        if not oid:
            continue
        if await backfill_customer_refs(oid):
            r["n"] = await db.equipment.count_documents({"organization_id": oid, **incomplete_query()})
        if not r["n"]:
            continue
        org = await db.organizations.find_one({"id": oid}, {"_id": 0, "name": 1, "account_type": 1, "is_mod": 1}) or {}
        total = await db.equipment.count_documents({"organization_id": oid})
        out.append({"organization_id": oid, "name": org.get("name") or oid, "account_type": org.get("account_type"),
                    "is_mod": bool(org.get("is_mod") or str(org.get("account_type") or "").startswith("mod")),
                    "incomplete": r["n"], "total": total})
    out.sort(key=lambda x: (-x["incomplete"], x["name"]))
    return {"scopes": out, "count": len(out)}


@router.get("/equipment-gaps")
async def list_gaps(
    organization_id: Optional[str] = None,
    site_id: Optional[str] = None,
    show: str = Query("incomplete", pattern="^(incomplete|all)$"),
    limit: int = Query(1000, ge=1, le=5000),
    user: dict = Depends(get_current_user),
) -> dict:
    org_id = _scope_org(user, organization_id)
    await backfill_customer_refs(org_id)
    q: dict = {"organization_id": org_id}
    if site_id:
        q["site_id"] = site_id
    docs = await db.equipment.find(q, _PROJECTION).sort([("location", 1), ("name", 1)]).to_list(limit)
    site_names = {s["id"]: s.get("name") async for s in db.sites.find({"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1})}
    items = []
    for d in docs:
        d["missing"] = missing_essentials(d)
        d["site_name"] = site_names.get(d.get("site_id"))
        items.append(d)
    summary = _summarise(items)
    if show == "incomplete":
        items = [it for it in items if it["missing"]]
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, **{f: 1 for f in _ORG_REF_FIELDS}}) or {}
    return {"organization_id": org_id, "organization_name": org.get("name"), "account_number": _org_ref(org) or None,
            "sites": [{"id": k, "name": v} for k, v in site_names.items()],
            "items": items, "summary": summary}


def _audit(user: dict, source: str) -> dict:
    return {"details_updated_at": datetime.now(timezone.utc).isoformat(),
            "details_updated_by": user.get("email") or user.get("id"), "details_source": source}


async def apply_detail_patch(eq: dict, body: dict, allowed, user: dict, source: str) -> dict:
    patch = {}
    for k, v in (body or {}).items():
        if k not in allowed:
            raise HTTPException(400, f"Field '{k}' cannot be edited here")
        patch[k] = clean_value(k, v)
    if not patch:
        raise HTTPException(400, "Nothing to update")
    if "name" in patch and not patch["name"]:
        raise HTTPException(400, "Description cannot be blank")
    with_next_service(eq, patch)
    patch.update(_audit(user, source))
    await db.equipment.update_one({"id": eq["id"]}, {"$set": patch})
    updated = {**eq, **patch}
    updated["missing"] = missing_essentials(updated)
    return updated


@router.patch("/equipment-gaps/{equipment_id}")
async def patch_gap(equipment_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    eq = await db.equipment.find_one({"id": equipment_id}, _PROJECTION)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    _scope_org(user, eq.get("organization_id"))
    return {"success": True, "item": await apply_detail_patch(eq, body, EDITABLE_FIELDS, user, "grid")}


@router.post("/equipment-gaps/bulk")
async def bulk_fill(body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    org_id = _scope_org(user, body.get("organization_id"))
    field = body.get("field")
    if field not in _BULK_FIELDS:
        raise HTTPException(400, f"Field '{field}' cannot be bulk-filled")
    value = clean_value(field, body.get("value"))
    if value in (None, ""):
        raise HTTPException(400, "A value is required")
    q: dict = {"organization_id": org_id}
    if body.get("site_id"):
        q["site_id"] = body["site_id"]
    if body.get("ids"):
        q["id"] = {"$in": list(body["ids"])}
    if body.get("only_blank", True):
        q["$or"] = [{field: {"$exists": False}}, {field: None}, {field: ""}]
    res = await db.equipment.update_many(q, {"$set": {field: value, **_audit(user, "grid_bulk")}})
    if field in ("last_service_date", "service_interval", "service_period"):
        async for d in db.equipment.find({k: v for k, v in q.items() if k != "$or"}, _PROJECTION):
            p = with_next_service(d, {})
            if p:
                await db.equipment.update_one({"id": d["id"]}, {"$set": p})
    if field == "sicon_customer_ref" and not body.get("site_id") and not body.get("ids"):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, **{f: 1 for f in _ORG_REF_FIELDS}}) or {}
        if not _org_ref(org):
            await db.organizations.update_one({"id": org_id}, {"$set": {"customer_account_number": value}})
    return {"success": True, "updated": res.modified_count}


@router.get("/equipment-gaps/export.xlsx")
async def export_gaps(organization_id: Optional[str] = None, site_id: Optional[str] = None,
                      user: dict = Depends(get_current_user)):
    """Current assets pre-filled into the Sicon template — fill blanks and re-import."""
    import io
    import openpyxl
    from fastapi.responses import Response
    from utils.sicon_equipment import SICON_EQUIPMENT_HEADERS, SICON_TO_CANONICAL
    org_id = _scope_org(user, organization_id)
    await backfill_customer_refs(org_id)
    q: dict = {"organization_id": org_id}
    if site_id:
        q["site_id"] = site_id
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(SICON_EQUIPMENT_HEADERS)
    async for d in db.equipment.find(q, {"_id": 0}).sort([("location", 1), ("name", 1)]):
        row = []
        for h in SICON_EQUIPMENT_HEADERS:
            f = SICON_TO_CANONICAL[h]
            v = d.get(f) or (d.get("purchase_date") if f == "install_date" else None)
            if f == "unit_price":
                v = d.get("purchase_cost") or d.get("purchase_price")
            row.append(v if v not in (None, "") else None)
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Equipment Import - Sicon Template.xlsx"'})
