"""Master Admin → Pulse data explorer (Iter 226).

A *curated, brand-scoped* read-only data browser for Pulse Master Admins.

Unlike the raw db-viewer (master_admin_db_viewer.py — every collection,
GymAxis-only), this surface exposes a hand-picked whitelist of business
collections, each HARD-filtered to the requesting brand's Pulse Fitness
organisations. A Pulse admin can therefore inspect their own
orgs / users / equipment / faults / members / social posts without ever
seeing GymAxis or other-tenant data.

Scoping:
  pulse_org_ids = organisation `id`s whose account_type/brand is Pulse
  (utils.brand_filter). Every whitelisted collection is filtered by its
  org-link field against that set (or by brand=pulse for the social
  library). Search is AND-ed *inside* the scope so it can never escape it.

Reuses redaction + search-field logic from the raw db-viewer.

Endpoints (under /api/master-admin/pulse-explorer, require_master_admin —
which permits both GymAxis and Pulse Master Admins; the data is identical
either way because it is always brand-scoped):
  GET /collections
  GET /collections/{name}?page&page_size&q
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from routes.master_admin import require_master_admin
from routes.master_admin_db_viewer import _redact, _build_search_filter
from utils.auth import get_current_user
from utils.brand_filter import brand_filter_clause, PULSE_BRAND_VALUES
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# Curated whitelist. `scope`:
#   "organization_id" → {organization_id: {$in: pulse_org_ids}}
#   "org_self"        → {id: {$in: pulse_org_ids}}   (the organisations coll.)
#   "brand_pulse"     → {brand: {$in: PULSE_BRAND_VALUES}}
PULSE_COLLECTIONS = [
    {"name": "organizations",          "label": "Organisations",          "scope": "org_self"},
    {"name": "users",                  "label": "Users",                  "scope": "organization_id"},
    {"name": "crm_users",              "label": "CRM users",              "scope": "organization_id"},
    {"name": "sites",                  "label": "Sites",                  "scope": "organization_id"},
    {"name": "equipment",              "label": "Equipment",              "scope": "organization_id"},
    {"name": "issues",                 "label": "Faults",                 "scope": "organization_id"},
    {"name": "members",                "label": "Members",                "scope": "organization_id"},
    {"name": "member_memberships",     "label": "Memberships",            "scope": "organization_id"},
    {"name": "membership_plans",       "label": "Membership plans",       "scope": "organization_id"},
    {"name": "marketing_subscriptions","label": "Billing / subscriptions","scope": "organization_id"},
    {"name": "social_media_library",   "label": "Social posts",           "scope": "brand_pulse"},
]
_BY_NAME = {c["name"]: c for c in PULSE_COLLECTIONS}


async def _pulse_org_ids() -> list[str]:
    """Organisation `id`s that belong to the Pulse Fitness brand."""
    clause = brand_filter_clause("pulse", "organizations")
    ids: list[str] = []
    async for o in db.organizations.find(clause, {"id": 1, "_id": 0}):
        if o.get("id"):
            ids.append(o["id"])
    return ids


def _scope_clause(scope: str, org_ids: list[str]) -> dict:
    if scope == "org_self":
        return {"id": {"$in": org_ids}}
    if scope == "brand_pulse":
        return {"brand": {"$in": PULSE_BRAND_VALUES}}
    return {"organization_id": {"$in": org_ids}}


def _merge_scoped(scope_clause: dict, search_clause: dict) -> dict:
    # AND the search INSIDE the scope so a query can never widen it.
    if scope_clause and search_clause:
        return {"$and": [scope_clause, search_clause]}
    return scope_clause or search_clause or {}


@router.get("/master-admin/pulse-explorer/collections")
async def pulse_list_collections(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    org_ids = await _pulse_org_ids()
    out = []
    for c in PULSE_COLLECTIONS:
        clause = _scope_clause(c["scope"], org_ids)
        try:
            count = await db[c["name"]].count_documents(clause)
        except Exception:
            count = -1
        out.append({"name": c["name"], "label": c["label"], "count": count})
    return {"collections": out, "count": len(out), "pulse_org_count": len(org_ids)}


@router.get("/master-admin/pulse-explorer/collections/{name}")
async def pulse_browse_collection(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    conf = _BY_NAME.get(name)
    if not conf:
        raise HTTPException(status_code=404, detail="Collection not available in the Pulse explorer")

    org_ids = await _pulse_org_ids()
    query = _merge_scoped(_scope_clause(conf["scope"], org_ids), _build_search_filter(q))

    total = await db[name].count_documents(query)
    pages = max(1, (total + page_size - 1) // page_size)
    cursor = db[name].find(query).sort("_id", -1).skip((page - 1) * page_size).limit(page_size)
    docs = [_redact(d) async for d in cursor]

    # Iter 247 — readability: resolve raw organization_id values to the
    # organisation's display name. The frontend shows the name in the
    # "organisation" column (raw id stays available in the tooltip).
    org_id_set = {d.get("organization_id") for d in docs if d.get("organization_id")}
    if org_id_set:
        names = {
            o["id"]: o.get("name", "")
            async for o in db.organizations.find(
                {"id": {"$in": list(org_id_set)}}, {"_id": 0, "id": 1, "name": 1},
            )
        }
        for d in docs:
            oid = d.get("organization_id")
            if oid:
                d["organization_name"] = names.get(oid, "")

    return {
        "docs": docs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "label": conf["label"],
    }
