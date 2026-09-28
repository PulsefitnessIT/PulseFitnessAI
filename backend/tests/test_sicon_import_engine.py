"""
Offline tests for the Sicon→Pulse equipment import engine (spec §29 §10 §20 §23).
DB-backed (real Motor) with a fake paginating client; fully isolated to a
throwaway org id and cleaned up after each test.
"""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
from utils import sicon_import as imp
from utils import sicon_links as links


class FakeClient:
    page_size = 50
    allow_writes = False

    def __init__(self, pages):
        self._pages = pages

    async def svc_paginate(self, kind, page_size=None, max_pages=0):
        for meta, records in self._pages:
            yield meta, records


def _rec(seid, serial="", **kw):
    d = {"siconEquipmentId": seid, "serialNumber": serial}
    d.update(kw)
    return d


async def _cleanup(org):
    await db.equipment.delete_many({"organization_id": org})
    await db.sicon_external_links.delete_many({"organization_id": org})
    await db.sicon_import_conflicts.delete_many({"organization_id": org})
    await db.sicon_sync_runs.delete_many({"organization_id": org})


@pytest.fixture
def org():
    o = f"itest-sicon-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(_cleanup(o))


def test_new_then_idempotent_no_duplicate(org):
    async def run():
        norm = imp.normalise_equipment(_rec(1001, "SNX-1", description="Treadmill"))
        c1 = await imp.classify_equipment(norm, org)
        r1 = await imp.apply_equipment_record(org, norm, c1)
        # run again — must NOT create a second asset
        c2 = await imp.classify_equipment(norm, org)
        r2 = await imp.apply_equipment_record(org, norm, c2)
        n = await db.equipment.count_documents({"organization_id": org, "sicon_equipment_id": 1001})
        return r1, c2["bucket"], r2["action"], n
    r1, bucket2, action2, n = drive_async(run())
    assert r1["action"] == "created"
    assert bucket2 == "linked" and action2 == "updated"
    assert n == 1  # idempotent


def test_null_sicon_does_not_erase_and_make_not_manufacturer(org):
    async def run():
        # Seed a rich Pulse asset (manufacturer + install date populated).
        aid = str(uuid.uuid4())
        await db.equipment.insert_one({
            "id": aid, "organization_id": org, "serial_number": "SN-KEEP",
            "manufacturer": "StairMaster", "install_date": "2020-01-01",
            "name": "Existing"})
        # Sicon rec: same serial, empty install date, make is an item code.
        norm = imp.normalise_equipment(_rec(2002, "SN-KEEP", make="200E-AAA", installDate=""))
        cls = await imp.classify_equipment(norm, org)
        await imp.apply_equipment_record(org, norm, cls)
        doc = await db.equipment.find_one({"id": aid}, {"_id": 0})
        return cls["bucket"], doc
    bucket, doc = drive_async(run())
    assert bucket == "match"
    assert doc["manufacturer"] == "StairMaster"          # §9 never overwritten
    assert doc["install_date"] == "2020-01-01"           # §20 empty didn't erase
    assert doc["sicon_make_raw"] == "200E-AAA"           # preserved as raw metadata
    assert doc["sicon_equipment_id"] == 2002             # id linked


def test_ambiguous_serial_creates_conflict_not_duplicate(org):
    async def run():
        for _ in range(2):
            await db.equipment.insert_one({
                "id": str(uuid.uuid4()), "organization_id": org,
                "serial_number": "DUP-SN", "name": "dup"})
        norm = imp.normalise_equipment(_rec(3003, "DUP-SN"))
        cls = await imp.classify_equipment(norm, org)
        res = await imp.apply_equipment_record(org, norm, cls)
        conflicts = await db.sicon_import_conflicts.count_documents(
            {"organization_id": org, "external_id": "3003", "status": "open"})
        assets = await db.equipment.count_documents({"organization_id": org})
        return cls["bucket"], res["action"], conflicts, assets
    bucket, action, conflicts, assets = drive_async(run())
    assert bucket == "conflict" and action == "conflict"
    assert conflicts == 1
    assert assets == 2  # no new asset created, none merged


def test_existing_sicon_id_updates_same_record(org):
    async def run():
        aid = str(uuid.uuid4())
        await db.equipment.insert_one({
            "id": aid, "organization_id": org, "sicon_equipment_id": 4004,
            "serial_number": "OLD", "name": "linked"})
        norm = imp.normalise_equipment(_rec(4004, "NEW-SERIAL"))
        cls = await imp.classify_equipment(norm, org)
        await imp.apply_equipment_record(org, norm, cls)
        doc = await db.equipment.find_one({"id": aid}, {"_id": 0})
        cnt = await db.equipment.count_documents({"organization_id": org, "sicon_equipment_id": 4004})
        return cls["bucket"], doc["serial_number"], cnt
    bucket, serial, cnt = drive_async(run())
    assert bucket == "linked"
    assert serial == "NEW-SERIAL"  # Sicon-owned field synced
    assert cnt == 1


def test_failed_record_does_not_kill_run(org):
    async def run():
        pages = [({"currentPage": 1, "nextPage": None, "pageSize": 50, "totalRecords": 3},
                  [_rec(5005, "A"), "GARBAGE-NOT-A-DICT", _rec(5006, "B")])]
        result = await imp.run_equipment_sync(org, FakeClient(pages), run_id="itest-run")
        created = await db.equipment.count_documents({"organization_id": org})
        return result, created
    result, created = drive_async(run())
    assert result["status"] == "completed"
    assert result["counts"]["failed"] == 1     # the garbage record
    assert result["counts"]["created"] == 2    # the two good records still imported
    assert created == 2


def test_preview_writes_nothing(org):
    async def run():
        pages = [({"currentPage": 1, "nextPage": None, "pageSize": 50, "totalRecords": 2},
                  [_rec(6006, "P1"), _rec(6007, "P2")])]
        result = await imp.preview_equipment(org, FakeClient(pages), max_records=500)
        assets = await db.equipment.count_documents({"organization_id": org})
        return result, assets
    result, assets = drive_async(run())
    assert result["counts"]["new"] == 2
    assert result["total_in_sicon"] == 2
    assert assets == 0  # preview must not write
