"""Offline tests for Sicon case-relationship wiring (spec §12/§13):
equipment attach + UNMAPPED_EQUIPMENT flagging, and tracking-notes → timeline
folding, all idempotent. No live Sicon server — a FakeClient serves canned
relationship payloads.
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

    def __init__(self, cases, equipment_by_case, notes_by_case):
        self._cases = cases
        self._equipment = equipment_by_case
        self._notes = notes_by_case

    async def svc_paginate(self, kind, page_size=None, max_pages=0):
        yield {"totalRecords": len(self._cases), "nextPage": None}, self._cases

    async def svc_get_case_equipment(self, scid):
        return {"records": self._equipment.get(scid, [])}

    async def svc_get_case_tracking_notes(self, scid):
        return {"records": self._notes.get(scid, [])}


async def _cleanup(org):
    await db.issues.delete_many({"organization_id": org})
    await db.equipment.delete_many({"organization_id": org})
    await db.sicon_external_links.delete_many({"organization_id": org})
    await db.sicon_import_conflicts.delete_many({"organization_id": org})
    await db.sicon_sync_runs.delete_many({"organization_id": org})
    await db.sicon_sync_locks.delete_many({"organization_id": org})


@pytest.fixture
def org():
    o = f"itest-siconrel-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(_cleanup(o))


async def _seed_asset(org, seid, serial):
    aid = str(uuid.uuid4())
    await db.equipment.insert_one({
        "id": aid, "organization_id": org, "name": f"Asset {seid}",
        "serial_number": serial, "sicon_equipment_id": seid})
    await links.upsert_link(links.ENTITY_EQUIPMENT, seid, "equipment", aid,
                            organization_id=org, sync_status="linked")
    return aid


def test_equipment_attach_and_unmapped_flag(org):
    async def run():
        mapped_asset = await _seed_asset(org, 5001, "SER-AAA")
        cases = [{"siSMCaseId": 8001, "caseNumber": "CN8001", "summary": "Belt"}]
        equipment = {8001: [{"siconEquipmentId": 5001}, {"siconEquipmentId": 5999}]}  # 5999 unmapped
        client = FakeClient(cases, equipment, {})
        r = await imp.run_case_sync(org, client, {})
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 8001}, {"_id": 0})
        conflict = await db.sicon_import_conflicts.find_one(
            {"organization_id": org, "external_entity_type": imp.CASE_EQUIPMENT_ENTITY,
             "external_id": "8001:5999"}, {"_id": 0})
        return r, issue, conflict, mapped_asset
    r, issue, conflict, mapped_asset = drive_async(run())
    assert r["counts"]["equipment_linked"] == 1
    assert r["counts"]["equipment_unmapped"] == 1
    assert issue["asset_id"] == mapped_asset
    assert issue["equipment_ids"] == [mapped_asset]
    assert issue["equipment_serials"] == ["SER-AAA"]
    assert conflict is not None and conflict["reasons"] == ["UNMAPPED_EQUIPMENT"]
    assert conflict["status"] == "open"


def test_tracking_notes_fold_and_dedupe(org):
    async def run():
        cases = [{"siSMCaseId": 8002, "caseNumber": "CN8002", "summary": "Motor"}]
        notes = {8002: [
            {"siconTrackingNoteId": 11, "note": "Engineer called", "userName": "Bob",
             "trackingDate": "2026-01-02"},
            {"siconTrackingNoteId": 12, "note": "Part ordered", "userName": "Sue",
             "trackingDate": "2026-01-03"},
        ]}
        client = FakeClient(cases, {}, notes)
        r1 = await imp.run_case_sync(org, client, {}, run_id=str(uuid.uuid4()))
        # Second run with the SAME notes must not duplicate (dedupe by note id).
        r2 = await imp.run_case_sync(org, client, {}, run_id=str(uuid.uuid4()))
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 8002}, {"_id": 0})
        return r1, r2, issue
    r1, r2, issue = drive_async(run())
    assert r1["counts"]["notes_added"] == 2
    assert r2["counts"]["notes_added"] == 0          # idempotent
    tl = [e for e in issue.get("timeline", []) if e.get("event") == "sicon_tracking_note"]
    assert len(tl) == 2                               # not duplicated
    assert {e["sicon_tracking_note_id"] for e in tl} == {"11", "12"}
    assert all(e["source"] == "SICON" for e in tl)


def test_relationships_skipped_when_flag_false(org):
    async def run():
        await _seed_asset(org, 5003, "SER-CCC")
        cases = [{"siSMCaseId": 8003, "caseNumber": "CN8003", "summary": "X"}]
        client = FakeClient(cases, {8003: [{"siconEquipmentId": 5003}]},
                            {8003: [{"siconTrackingNoteId": 1, "note": "n"}]})
        r = await imp.run_case_sync(org, client, {}, pull_relationships=False)
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 8003}, {"_id": 0})
        return r, issue
    r, issue = drive_async(run())
    assert r["counts"]["equipment_linked"] == 0
    assert r["counts"]["notes_added"] == 0
    assert "asset_id" not in issue                    # relationship pull skipped
    assert not issue.get("timeline")


def test_null_protection_no_asset_does_not_erase(org):
    """If a re-pull returns no resolvable equipment, existing links are kept (§22)."""
    async def run():
        asset = await _seed_asset(org, 5004, "SER-DDD")
        cases = [{"siSMCaseId": 8004, "caseNumber": "CN8004", "summary": "Y"}]
        # First pull attaches the asset.
        c1 = FakeClient(cases, {8004: [{"siconEquipmentId": 5004}]}, {})
        await imp.run_case_sync(org, c1, {})
        # Second pull returns NO equipment — must not wipe the attached asset.
        c2 = FakeClient(cases, {8004: []}, {})
        await imp.run_case_sync(org, c2, {})
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 8004}, {"_id": 0})
        return issue, asset
    issue, asset = drive_async(run())
    assert issue["equipment_ids"] == [asset]          # preserved, not erased
