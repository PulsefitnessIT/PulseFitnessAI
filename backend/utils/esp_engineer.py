"""External Service Provider (ESP) engineers — identity + job scope.

ESP engineers are provisioned from Master Admin → MOD estate → external
providers. They only ever use the engineer app (/svc/engineer) and see the
faults/jobs for the MOD sites their provider is allocated to.
"""
from __future__ import annotations

from utils.database import db

BFPO_ORG_ID = "bfpo-mod-org"
INHOUSE_SUPPLIER_ID = "pulse-inhouse-mod"


def is_external_engineer(user: dict | None) -> bool:
    u = user or {}
    if u.get("mod_estate_supplier_id") == INHOUSE_SUPPLIER_ID:
        return False  # Pulse's own MOD engineers keep the BFPO portal
    return bool(u.get("mod_estate_supplier_id") or u.get("is_external_engineer")
                or u.get("created_via") == "external_provider_onboarding")


async def esp_site_ids(user: dict) -> list[str]:
    """Sites the engineer's provider services: explicit picks + every site
    whose default provider (or any machine) points at that provider."""
    sites = set(user.get("bfpo_site_ids") or [])
    sup_id = user.get("mod_estate_supplier_id")
    if sup_id:
        rows = await db.suppliers.find({"estate_supplier_id": sup_id},
                                       {"_id": 0, "id": 1, "organization_id": 1}).to_list(2000)
        row_ids = [r["id"] for r in rows]
        if row_ids:
            async for o in db.organizations.find({"service_supplier_id": {"$in": row_ids}}, {"_id": 0, "id": 1}):
                sites.add(o["id"])
            sites.update(await db.equipment.distinct("organization_id", {"supplier_id": {"$in": row_ids}}))
    return sorted(s for s in sites if s)


async def engineer_job_scope(user: dict, of: dict) -> dict:
    """Mongo filter for 'my jobs'. Internal engineers: assigned to me in my
    org. ESP engineers: assigned to me, or unassigned on my provider's sites."""
    if not is_external_engineer(user):
        return {**of, "assigned_engineer_id": user["id"]}
    sites = await esp_site_ids(user)
    return {"$and": [{"$or": [
        {"assigned_engineer_id": user["id"]},
        {"organization_id": {"$in": [BFPO_ORG_ID, *sites]},
         "assigned_engineer_id": {"$in": [None, ""]},
         "$or": [{"site_id": {"$in": sites}}, {"organization_id": {"$in": sites}}]},
    ]}]}
