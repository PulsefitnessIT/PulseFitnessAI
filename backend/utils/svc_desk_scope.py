"""Pulse Service Desk visibility of MOD jobs.

MOD faults are bridged into ``svc_cases`` under the BFPO tenant
(``bfpo-mod-org``). The Pulse operator company (``is_operator_company``)
runs the desk, so its users see those cases alongside their own. Per-case
endpoints swap the caller's org for the case's org (``as_case_org``) so all
existing org-scoped reads/writes work unchanged. Jobs with an outside
provider are read-only on the desk until Pulse takes them over.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import HTTPException

from utils.database import db
from utils.esp_engineer import BFPO_ORG_ID

_OP_CACHE: dict = {}
_TTL = 60
PROVIDER_INACTIVE = ("cancelled", "taken_over", "declined")
DESK_COMPLETE_STATES = ("repaired", "awaiting_sign_off", "closed")


def _home_org(user: dict) -> Optional[str]:
    return user.get("_desk_home_org") or user.get("organization_id") or user.get("service_org_id")


async def is_operator_org(org_id: Optional[str]) -> bool:
    if not org_id:
        return False
    hit = _OP_CACHE.get(org_id)
    if hit and hit[1] > time.time():
        return hit[0]
    doc = await db.organizations.find_one({"id": org_id}, {"_id": 0, "is_operator_company": 1})
    val = bool((doc or {}).get("is_operator_company"))
    _OP_CACHE[org_id] = (val, time.time() + _TTL)
    return val


async def desk_org_ids(user: dict) -> list:
    org = _home_org(user)
    return [org, BFPO_ORG_ID] if await is_operator_org(org) else [org]


async def desk_filter(user: dict) -> dict:
    ids = await desk_org_ids(user)
    return {"organization_id": ids[0] if len(ids) == 1 else {"$in": ids}}


async def as_case_org(user: dict, case_id: str) -> dict:
    """Caller re-scoped to a MOD case's org when the desk may see it."""
    org = _home_org(user)
    if not await is_operator_org(org):
        return user
    case = await db.svc_cases.find_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0, "id": 1})
    if not case:
        return user
    return {**user, "organization_id": BFPO_ORG_ID, "service_org_id": BFPO_ORG_ID, "_desk_home_org": org}


async def external_provider(case: dict) -> Optional[dict]:
    """Active outside-provider routing for a MOD case, else None."""
    issue_id = case.get("mod_issue_id")
    if not issue_id or case.get("provider_taken_over_at"):
        return None
    sc = await db.supplier_cases.find_one(
        {"issue_id": issue_id, "current_status": {"$nin": list(PROVIDER_INACTIVE)}},
        {"_id": 0, "id": 1, "supplier_name": 1, "supplier_email": 1, "current_status": 1, "updated_at": 1},
        sort=[("created_at", -1)])
    return sc


async def guard_desk_write(user: dict, case_id: str, target_state: Optional[str] = None) -> None:
    """Desk edits are blocked while an outside provider owns the MOD job;
    marking it complete/closed stays allowed."""
    if not user.get("_desk_home_org") or target_state in DESK_COMPLETE_STATES:
        return
    case = await db.svc_cases.find_one({"id": case_id}, {"_id": 0, "mod_issue_id": 1, "provider_taken_over_at": 1})
    prov = await external_provider(case or {})
    if prov:
        raise HTTPException(409, f"This MOD job is with {prov.get('supplier_name') or 'an outside provider'} — "
                                 "take it over to make changes.")


async def mirror_provider_update(issue_id: str, supplier_name: str, body: str,
                                 status: Optional[str] = None, extra: Optional[dict] = None) -> None:
    """Copy an outside provider's update onto the MOD svc_case timeline."""
    from utils.svc_state import append_event
    case = await db.svc_cases.find_one({"mod_issue_id": issue_id}, {"_id": 0, "id": 1, "organization_id": 1})
    if not case:
        return
    if status:
        await db.svc_cases.update_one({"id": case["id"]}, {"$set": {
            "provider_status": status, "provider_name": supplier_name}})
    await append_event(case_id=case["id"], organization_id=case["organization_id"],
                       event_type="provider_update", actor={"id": "provider", "full_name": supplier_name},
                       body=body, extra={**(extra or {}), **({"provider_status": status} if status else {})})
