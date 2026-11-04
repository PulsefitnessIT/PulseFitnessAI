"""External Service Provider (ESP) engineers — identity + job scope.

ESP engineers are provisioned from Master Admin → MOD estate → external
providers. They only ever use the engineer app (/svc/engineer) and see the
faults/jobs for the MOD sites their provider is allocated to.
"""
from __future__ import annotations

import re

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
        est = await db.mod_estate_suppliers.find_one({"id": sup_id}, {"_id": 0, "name": 1, "email": 1}) or {}
        match = [{"estate_supplier_id": sup_id}]
        if est.get("email"):
            match.append({"email": {"$regex": f"^{re.escape(est['email'].strip())}$", "$options": "i"}})
        if est.get("name"):
            match.append({"name": {"$regex": f"^{re.escape(est['name'].strip())}$", "$options": "i"}})
        rows = await db.suppliers.find({"$or": match}, {"_id": 0, "id": 1, "organization_id": 1}).to_list(2000)
        row_ids = [r["id"] for r in rows] + [sup_id]
        if row_ids:
            async for o in db.organizations.find({"service_supplier_id": {"$in": row_ids}}, {"_id": 0, "id": 1}):
                sites.add(o["id"])
            sites.update(await db.equipment.distinct("organization_id", {"supplier_id": {"$in": row_ids}}))
    return sorted(s for s in sites if s)


async def _case_provider_id(case: dict) -> str | None:
    """Estate provider servicing this fault: the machine's own supplier first,
    then the site's default provider. None for Pulse in-house."""
    row_id = None
    if case.get("asset_id"):
        eq = await db.equipment.find_one({"id": case["asset_id"]},
                                         {"_id": 0, "supplier_id": 1, "supplier_mode": 1}) or {}
        if eq.get("supplier_mode") == "pulse":
            return None
        row_id = eq.get("supplier_id")
    if not row_id:
        site = await db.organizations.find_one({"id": case.get("site_id")}, {"_id": 0, "service_supplier_id": 1}) or {}
        row_id = site.get("service_supplier_id")
    if not row_id:
        return None
    row = await db.suppliers.find_one({"id": row_id}, {"_id": 0, "estate_supplier_id": 1}) or {}
    est = row.get("estate_supplier_id")
    return est if est and est != INHOUSE_SUPPLIER_ID else None


async def auto_allocate_sole_engineer(case: dict) -> str | None:
    """New MOD fault → if its provider has exactly one active engineer, assign it to them."""
    if case.get("assigned_engineer_id"):
        return None
    est = await _case_provider_id(case)
    if not est:
        return None
    engs = await db.users.find(
        {"mod_estate_supplier_id": est, "is_active": {"$ne": False},
         "$or": [{"bfpo_role": "engineer"}, {"role": "engineer"}]},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1}).to_list(2)
    if len(engs) != 1:
        return None
    eng = engs[0]
    name = eng.get("full_name") or eng.get("email") or "Engineer"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = await db.svc_cases.update_one(
        {"id": case["id"], "assigned_engineer_id": {"$in": [None, ""]}},
        {"$set": {"assigned_engineer_id": eng["id"], "assigned_engineer_name": name, "status": "assigned",
                  "assigned_at": now, "auto_allocated": True, "updated_at": now}})
    if not res.modified_count:
        return None
    from utils.svc_state import append_event
    from routes.svc.notifications import create_notification
    await append_event(case_id=case["id"], organization_id=case["organization_id"], event_type="note",
                       actor={"id": "system", "full_name": "Auto-allocation"},
                       body=f"Auto-allocated to {name} (provider's only engineer)",
                       extra={"kind": "esp_auto_allocated", "engineer_id": eng["id"]})
    await create_notification(user_id=eng["id"], organization_id=case["organization_id"], kind="svc_job",
                              title=f"New fault allocated to you · {case.get('reference') or ''}",
                              body=f"{case.get('title') or 'Fault'} — {case.get('site_name') or 'MOD site'}",
                              link=f"/svc/engineer/jobs/{case['id']}", source_type="svc_case", source_id=case["id"])
    return eng["id"]


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
