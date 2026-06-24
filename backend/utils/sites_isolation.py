"""DB-backed helpers for multi-site isolation (Memberships/CRM/Marketing).

Pairs with the pure ``utils.site_scope`` engine: this module knows about
the ``sites`` collection and is responsible for resolving an org's
primary/Head-Office site and for the idempotent backfill that stamps
existing siteless records onto that primary site.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from utils.database import db

log = logging.getLogger(__name__)

# Collections that participate in site isolation, grouped by module.
ISOLATED_COLLECTIONS: dict[str, list[str]] = {
    "memberships": [
        "members", "member_memberships", "checkins", "bookings",
        "class_templates", "occurrences", "membership_plans", "ad_placements",
    ],
    "crm": [
        # v1 layer
        "crm_companies", "crm_contacts", "crm_opportunities", "crm_deals",
        "crm_activities", "crm_cases", "crm_assets", "crm_quotes",
        # v2 (active) layer
        "crm2_companies", "crm2_contacts", "crm2_opportunities",
        "crm2_activities", "crm2_cases", "crm2_assets", "crm2_quotes",
    ],
    "marketing": [
        "marketing_campaigns", "marketing_audiences", "journeys", "forms", "pages",
    ],
}


async def get_primary_site_id(org_id: str) -> str | None:
    """Return the org's primary site id (Head Office, else oldest site).

    Idempotently creates a Head-Office site when the org has none, so new
    records always have somewhere to land. Returns None only when the org
    id is missing.
    """
    if not org_id:
        return None
    hq = await db.sites.find_one(
        {"organization_id": org_id, "is_head_office": True, "archived": {"$ne": True}},
        {"_id": 0, "id": 1},
    )
    if hq:
        return hq["id"]
    oldest = await db.sites.find_one(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0, "id": 1},
        sort=[("created_at", 1)],
    )
    if oldest:
        return oldest["id"]
    # No sites at all — create a Head Office so isolation has an anchor.
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "address": 1})
    if not org:
        return None
    hq_id = str(uuid.uuid4())
    await db.sites.insert_one({
        "id": hq_id,
        "organization_id": org_id,
        "name": f"{org.get('name', 'Head Office')} Head Office",
        "address": org.get("address", ""),
        "is_head_office": True,
        "default_location": "Head Office",
        "auto_created": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return hq_id


async def backfill_org_site_ids(org_id: str, *, modules: list[str] | None = None) -> dict:
    """Stamp every siteless record in the org's isolated collections onto
    its primary site. Idempotent — only touches docs whose ``site_id`` is
    missing/null/empty. Returns a per-collection count of updated docs.
    """
    primary = await get_primary_site_id(org_id)
    if not primary:
        return {}
    keys = modules or list(ISOLATED_COLLECTIONS.keys())
    siteless = {"$or": [
        {"site_id": {"$exists": False}},
        {"site_id": None},
        {"site_id": ""},
    ]}
    result: dict[str, int] = {}
    for mod in keys:
        for coll in ISOLATED_COLLECTIONS.get(mod, []):
            try:
                res = await db[coll].update_many(
                    {"organization_id": org_id, **siteless},
                    {"$set": {"site_id": primary}},
                )
                if res.modified_count:
                    result[coll] = res.modified_count
            except Exception:
                log.exception("backfill_org_site_ids failed for %s/%s", org_id, coll)
    return result


async def backfill_all_orgs(*, modules: list[str] | None = None) -> dict:
    """Run :func:`backfill_org_site_ids` across every organisation. Safe to
    re-run; returns a summary keyed by org id."""
    summary: dict[str, dict] = {}
    async for org in db.organizations.find({}, {"_id": 0, "id": 1}):
        oid = org.get("id")
        if not oid:
            continue
        changed = await backfill_org_site_ids(oid, modules=modules)
        if changed:
            summary[oid] = changed
    return summary


__all__ = [
    "ISOLATED_COLLECTIONS",
    "get_primary_site_id",
    "backfill_org_site_ids",
    "backfill_all_orgs",
]
