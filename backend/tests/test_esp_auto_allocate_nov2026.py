"""Nov 2026 — auto-allocate new MOD faults to a provider's sole engineer."""
import asyncio
import os
import uuid

import pytest

LOOP = asyncio.new_event_loop()
T = uuid.uuid4().hex[:6]
EST, ROW, SITE = f"pytest-est-{T}", f"pytest-row-{T}", f"pytest-site-{T}"
ENG1, ENG2, EQ = f"pytest-eng1-{T}", f"pytest-eng2-{T}", f"pytest-eq-{T}"


def run(c):
    return LOOP.run_until_complete(c)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module", autouse=True)
def seed():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    asyncio.set_event_loop(LOOP)
    import utils.esp_engineer as esp
    import utils.svc_state as st
    import routes.svc.notifications as nt
    fresh = _db()
    for m in (esp, st, nt):
        m.db = fresh

    async def setup():
        db = _db()
        await db.mod_estate_suppliers.insert_one({"id": EST, "name": "Pytest Provider", "email": "p@example.com"})
        await db.suppliers.insert_one({"id": ROW, "organization_id": SITE, "estate_supplier_id": EST, "name": "Pytest Provider"})
        await db.organizations.insert_one({"id": SITE, "name": "Pytest MOD Site", "service_supplier_id": ROW})
        await db.equipment.insert_one({"id": EQ, "organization_id": SITE, "supplier_mode": "pulse"})
        await db.users.insert_one({"id": ENG1, "full_name": "Solo Engineer", "email": f"solo-{T}@example.com", "bfpo_role": "engineer",
                                   "mod_estate_supplier_id": EST, "is_active": True})

    async def teardown():
        db = _db()
        await db.mod_estate_suppliers.delete_many({"id": EST})
        await db.suppliers.delete_many({"id": ROW})
        await db.organizations.delete_many({"id": SITE})
        await db.equipment.delete_many({"id": EQ})
        await db.users.delete_many({"id": {"$in": [ENG1, ENG2]}})
        await db.svc_cases.delete_many({"site_id": SITE})
        await db.svc_case_events.delete_many({"organization_id": "bfpo-mod-org", "extra.engineer_id": {"$in": [ENG1, ENG2]}})
        await db.svc_notifications.delete_many({"user_id": {"$in": [ENG1, ENG2]}})
    run(setup())
    yield
    run(teardown())


def _case(**extra):
    cid = f"pytest-case-{uuid.uuid4().hex[:6]}"
    doc = {"id": cid, "organization_id": "bfpo-mod-org", "site_id": SITE, "site_name": "Pytest MOD Site",
           "status": "new", "assigned_engineer_id": None, "reference": cid, "title": "Fault", **extra}
    run(_db().svc_cases.insert_one({**doc}))
    return doc


def test_sole_engineer_gets_the_fault():
    from utils.esp_engineer import auto_allocate_sole_engineer
    c = _case()
    assert run(auto_allocate_sole_engineer(c)) == ENG1
    saved = run(_db().svc_cases.find_one({"id": c["id"]}))
    assert saved["assigned_engineer_id"] == ENG1 and saved["status"] == "assigned" and saved["auto_allocated"]
    assert run(_db().svc_notifications.count_documents({"user_id": ENG1, "source_id": c["id"]})) == 1


def test_pulse_inhouse_machine_is_skipped():
    from utils.esp_engineer import auto_allocate_sole_engineer
    assert run(auto_allocate_sole_engineer(_case(asset_id=EQ))) is None


def test_two_engineers_leaves_fault_unassigned():
    from utils.esp_engineer import auto_allocate_sole_engineer
    run(_db().users.insert_one({"id": ENG2, "full_name": "Second", "email": f"second-{T}@example.com", "bfpo_role": "engineer",
                                "mod_estate_supplier_id": EST, "is_active": True}))
    c = _case()
    assert run(auto_allocate_sole_engineer(c)) is None
    assert run(_db().svc_cases.find_one({"id": c["id"]}))["assigned_engineer_id"] is None


def test_inactive_engineer_not_counted():
    from utils.esp_engineer import auto_allocate_sole_engineer
    run(_db().users.update_one({"id": ENG2}, {"$set": {"is_active": False}}))
    assert run(auto_allocate_sole_engineer(_case())) == ENG1
