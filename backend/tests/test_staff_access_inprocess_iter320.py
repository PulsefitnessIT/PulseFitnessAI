"""Iter 320 — in-process checks: job title never grants Contracts/CRM privilege (derive/resolve role),
and offboarding release_departing_staff on SYNTHETIC docs only (cleaned up)."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import asyncio
import uuid

import pytest

from utils.database import db
from utils.crm_workspace import release_departing_staff, resolve_workspace_role, permissions_for, set_explicit_role
from routes.staffing import _platform_role_from_staff_role

LOOP = asyncio.new_event_loop()
OP_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"


def run(c):
    return LOOP.run_until_complete(c)


async def _mk(title):
    uid = f"TEST_synth_{uuid.uuid4().hex[:8]}"
    u = {"id": uid, "email": f"{uid.lower()}@example.test", "full_name": f"TEST Synth {title}", "organization_id": OP_ORG,
         "role": _platform_role_from_staff_role(title), "module_overrides": {"crm": False}}
    await db.users.insert_one(dict(u))
    await db.staff_members.insert_one({"id": f"{uid}_st", "user_id": uid, "organization_id": OP_ORG, "email": u["email"],
                                       "primary_role": title, "status": "active", "full_name": u["full_name"]})
    return u


async def _rm(uid):
    await db.users.delete_one({"id": uid})
    await db.staff_members.delete_one({"id": f"{uid}_st"})
    await db.crm_workspace_role_audit.delete_many({"user_id": uid})


# Job titles that must NOT confer a privileged Contracts/CRM role by themselves
@pytest.mark.parametrize("title", ["contract_coordinator", "senior_contract_coordinator", "service_aftersales_manager",
                                   "service_administrator", "service_desk_coordinator", "field_service_engineer",
                                   "finance_manager", "operations_manager", "department_manager", "manager", "director"])
def test_job_title_grants_nothing(title):
    async def go():
        u = await _mk(title)
        try:
            fresh = await db.users.find_one({"id": u["id"]}, {"_id": 0})
            role = await resolve_workspace_role(fresh)
            return role, permissions_for(role, fresh)
        finally:
            await _rm(u["id"])
    role, perms = run(go())
    assert role == "none", f"{title} -> {role}"
    assert perms == set()


# Known/expected design: a sales job title keeps default sales CRM access (reported, not a failure gate)
def test_sales_manager_title_default():
    async def go():
        u = await _mk("sales_manager")
        try:
            return await resolve_workspace_role(await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        finally:
            await _rm(u["id"])
    print("sales_manager job title resolves to:", run(go()))


# Offboarding releases work + roles (synthetic user/company/activities)
def test_release_departing_staff():
    async def go():
        u = await _mk("contract_coordinator")
        uid = u["id"]
        cid, a_open, a_done = f"TEST_co_{uid}", f"TEST_act_open_{uid}", f"TEST_act_done_{uid}"
        try:
            await set_explicit_role(await db.users.find_one({"id": uid}, {"_id": 0}), "contract_coordinator", actor="test")
            await db.users.update_one({"id": uid}, {"$set": {"mod_quote_role": "manager"}})
            await db.crm2_companies.insert_one({"id": cid, "organization_id": OP_ORG, "name": "TEST_Synth Co",
                                                "coordinator_id": uid, "coordinator_name": u["full_name"]})
            await db.crm2_activities.insert_many([
                {"id": a_open, "organization_id": OP_ORG, "owner_id": uid, "status": "open", "subject": "TEST open"},
                {"id": a_done, "organization_id": OP_ORG, "owner_id": uid, "status": "completed", "subject": "TEST done"}])
            leaver = await db.users.find_one({"id": uid}, {"_id": 0})
            res = await release_departing_staff(leaver, "qa@example.test")
            after = await db.users.find_one({"id": uid}, {"_id": 0})
            co = await db.crm2_companies.find_one({"id": cid}, {"_id": 0})
            ao = await db.crm2_activities.find_one({"id": a_open}, {"_id": 0})
            ad = await db.crm2_activities.find_one({"id": a_done}, {"_id": 0})
            aud = await db.crm_workspace_role_audit.find({"user_id": uid}, {"_id": 0}).to_list(20)
            return res, after, co, ao, ad, aud
        finally:
            await _rm(uid)
            await db.crm2_companies.delete_one({"id": cid})
            await db.crm2_activities.delete_many({"id": {"$in": [a_open, a_done]}})
    res, after, co, ao, ad, aud = run(go())
    assert res == {"tasks_to_shared_queue": 1, "portfolios_unassigned": 1}
    assert after["crm_workspace_role"] is None and after.get("mod_quote_role") is None
    assert after["module_overrides"]["crm"] is False  # CRM grant that came from the CM role is undone
    assert ao["owner_id"] == "system" and ao["owner_history"][0]["from_id"] == after["id"]
    assert ad["owner_id"] == after["id"]  # completed history untouched
    assert co["coordinator_id"] is None and co["coordinator_history"][0]["from_id"] == after["id"]
    assert any(a.get("to_role") is None and str(a.get("actor", "")).startswith("offboarding:") for a in aud)
    assert any(a.get("kind") == "mod_quote_role" and a.get("to") is None for a in aud)
