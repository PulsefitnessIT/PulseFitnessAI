"""Offline tests for the Sicon engineer-mapping layer (§15). Pulse-side only —
maps cached Sicon resources (db.sicon_engineers) to Pulse engineers
(db.svc_engineers) via the ENTITY_RESOURCE external link. No live Sicon needed.
"""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
from utils import sicon_links as links
from routes.sicon import read_engineer_mapping, save_engineer_mapping


def _user(org):
    return {"id": "u-test", "organization_id": org, "role": "owner"}


async def _cleanup(org):
    await db.sicon_engineers.delete_many({"organization_id": org})
    await db.svc_engineers.delete_many({"organization_id": org})
    await db.sicon_external_links.delete_many({"organization_id": org})


@pytest.fixture
def org():
    o = f"itest-siconeng-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(_cleanup(o))


async def _seed(org):
    await db.sicon_engineers.insert_many([
        {"id": f"{org}:R1", "organization_id": org, "sicon_employee_id": "R1",
         "full_name": "Alan Grant", "email": "alan@pulse.test", "team_name": "North"},
        {"id": f"{org}:R2", "organization_id": org, "sicon_employee_id": "R2",
         "full_name": "Ellie Sattler", "email": "ellie@pulse.test", "team_name": "South"},
        {"id": f"{org}:R3", "organization_id": org, "sicon_employee_id": "R3",
         "full_name": "Ian Malcolm", "email": "", "is_leaver": True},  # excluded
    ])
    await db.svc_engineers.insert_many([
        {"id": "eng-alan", "organization_id": org, "full_name": "Alan Grant",
         "email": "alan@pulse.test", "active": True},
        {"id": "eng-someone", "organization_id": org, "full_name": "Someone Else",
         "email": "x@pulse.test", "active": True},
    ])


def test_lists_resources_with_email_suggestion_excludes_leavers(org):
    async def run():
        await _seed(org)
        return await read_engineer_mapping(_user(org))
    res = drive_async(run())
    ids = {r["sicon_employee_id"] for r in res["resources"]}
    assert ids == {"R1", "R2"}                       # leaver R3 excluded
    r1 = next(r for r in res["resources"] if r["sicon_employee_id"] == "R1")
    assert r1["suggested_engineer_id"] == "eng-alan"  # matched by email
    assert r1["status"] == "suggested"
    r2 = next(r for r in res["resources"] if r["sicon_employee_id"] == "R2")
    assert r2["suggested_engineer_id"] is None         # no email/name match
    assert res["counts"] == {"total": 2, "mapped": 0, "unmapped": 2}


def test_save_and_clear_mapping_idempotent(org):
    async def run():
        await _seed(org)
        s1 = await save_engineer_mapping(
            {"sicon_employee_id": "R1", "pulse_engineer_id": "eng-alan"}, _user(org))
        after = await read_engineer_mapping(_user(org))
        r1 = next(r for r in after["resources"] if r["sicon_employee_id"] == "R1")
        # clear it
        s2 = await save_engineer_mapping(
            {"sicon_employee_id": "R1", "pulse_engineer_id": ""}, _user(org))
        after2 = await read_engineer_mapping(_user(org))
        r1b = next(r for r in after2["resources"] if r["sicon_employee_id"] == "R1")
        return s1, r1, s2, r1b
    s1, r1, s2, r1b = drive_async(run())
    assert s1["mapped_engineer_id"] == "eng-alan"
    assert r1["mapped_engineer_id"] == "eng-alan" and r1["status"] == "mapped"
    assert s2["mapped_engineer_id"] is None
    assert r1b["mapped_engineer_id"] is None and r1b["status"] in ("suggested", "unmapped")


def test_save_rejects_unknown_engineer(org):
    async def run():
        await _seed(org)
        try:
            await save_engineer_mapping(
                {"sicon_employee_id": "R1", "pulse_engineer_id": "nope"}, _user(org))
            return "no-error"
        except Exception as e:
            return getattr(e, "status_code", None)
    assert drive_async(run()) == 404


def test_link_uses_entity_resource(org):
    async def run():
        await _seed(org)
        await save_engineer_mapping(
            {"sicon_employee_id": "R1", "pulse_engineer_id": "eng-alan"}, _user(org))
        return await links.get_link(links.ENTITY_RESOURCE, "R1", org)
    link = drive_async(run())
    assert link and link["pulse_entity_id"] == "eng-alan"
    assert link["pulse_entity_type"] == "svc_engineer"
