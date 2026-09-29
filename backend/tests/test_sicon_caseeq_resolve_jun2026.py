"""Offline tests for UNMAPPED_EQUIPMENT (case_equipment) conflict resolution
(§12): link an existing Pulse asset, create a new asset, or ignore — and, on
link/create, attach the asset to the case's issue.
"""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
from utils import sicon_links as links
from utils import sicon_import as imp
from routes.sicon import read_resolve_conflict


def _user(org):
    return {"id": "u-test", "organization_id": org, "role": "owner"}


async def _cleanup(org):
    for c in ("issues", "equipment", "sicon_external_links", "sicon_import_conflicts"):
        await db[c].delete_many({"organization_id": org})


@pytest.fixture
def org():
    o = f"itest-caseeq-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(_cleanup(o))


async def _seed_case_with_unmapped(org, scid, seid, raw):
    issue_id = str(uuid.uuid4())
    await db.issues.insert_one({"id": issue_id, "organization_id": org,
                                "sicon_case_id": scid, "issue_description": "x"})
    await links.upsert_link(links.ENTITY_CASE, scid, "issue", issue_id, organization_id=org)
    await imp._record_unmapped_equipment(org, scid, seid, raw, "run1")
    return issue_id


def test_resolve_link_attaches_asset_to_case(org):
    async def run():
        issue_id = await _seed_case_with_unmapped(org, 9001, 7001,
                                                  {"siconEquipmentId": 7001, "serialNumber": "S-1"})
        asset_id = str(uuid.uuid4())
        await db.equipment.insert_one({"id": asset_id, "organization_id": org,
                                       "name": "Rower 12", "serial_number": "S-1"})
        res = await read_resolve_conflict("9001:7001",
                                          {"entity": "case_equipment", "action": "link",
                                           "pulse_asset_id": asset_id}, _user(org))
        issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
        conflict = await db.sicon_import_conflicts.find_one(
            {"organization_id": org, "external_id": "9001:7001"}, {"_id": 0})
        eqlink = await links.get_pulse_id(links.ENTITY_EQUIPMENT, 7001, org)
        return res, issue, conflict, asset_id, eqlink
    res, issue, conflict, asset_id, eqlink = drive_async(run())
    assert res["success"] and "linked" in res["resolution"]
    assert issue["equipment_ids"] == [asset_id]
    assert issue["asset_id"] == asset_id
    assert conflict["status"] == "resolved"
    assert eqlink == asset_id                        # equipment now linked by siconEquipmentId


def test_resolve_create_new_makes_and_attaches_asset(org):
    async def run():
        issue_id = await _seed_case_with_unmapped(org, 9002, 7002,
                                                  {"siconEquipmentId": 7002, "serialNumber": "S-2",
                                                   "description": "Treadmill 9"})
        res = await read_resolve_conflict("9002:7002",
                                          {"entity": "case_equipment", "action": "create_new"},
                                          _user(org))
        issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
        new_asset = await db.equipment.find_one(
            {"organization_id": org, "sicon_equipment_id": 7002}, {"_id": 0})
        return res, issue, new_asset
    res, issue, new_asset = drive_async(run())
    assert "created new asset" in res["resolution"]
    assert new_asset is not None and new_asset["serial_number"] == "S-2"
    assert issue["equipment_ids"] == [new_asset["id"]]
    assert issue["asset_id"] == new_asset["id"]


def test_resolve_ignore_leaves_issue_untouched(org):
    async def run():
        issue_id = await _seed_case_with_unmapped(org, 9003, 7003, {"siconEquipmentId": 7003})
        res = await read_resolve_conflict("9003:7003",
                                          {"entity": "case_equipment", "action": "ignore"},
                                          _user(org))
        issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
        conflict = await db.sicon_import_conflicts.find_one(
            {"organization_id": org, "external_id": "9003:7003"}, {"_id": 0})
        return res, issue, conflict
    res, issue, conflict = drive_async(run())
    assert res["resolution"] == "ignored"
    assert "equipment_ids" not in issue              # nothing attached
    assert conflict["status"] == "resolved"
