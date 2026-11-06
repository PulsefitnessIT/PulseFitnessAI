"""Offline tests for the Sicon onboarding sync (preview → apply, fill gaps only)."""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
from utils import sicon_onboarding as onb

COLLS = ("equipment", "issues", "crm2_companies", "crm2_sites", "crm2_contracts", "sicon_external_links",
         "sicon_import_conflicts", "sicon_import_differences", "sicon_sync_runs", "sicon_sync_locks")


class FakeClient:
    page_size = 50
    allow_writes = False

    def __init__(self, equipment, cases, contracts):
        self.data = {"equipment": equipment, "cases": cases}
        self.contracts = contracts

    async def svc_paginate(self, kind, page_size=None, max_pages=0):
        recs = self.data[kind]
        yield {"currentPage": 1, "nextPage": None, "pageSize": 50, "totalRecords": len(recs)}, recs

    async def svc_get_contracts(self):
        if self.contracts is None:
            raise RuntimeError("404")
        return {"data": self.contracts}

    async def _svc_get(self, path):
        raise RuntimeError("404")

    async def svc_get_case_equipment(self, scid):
        return {"data": [{"siconEquipmentId": 11}]}

    async def svc_get_case_tracking_notes(self, scid):
        return {"data": []}


EQUIP = [
    {"siconEquipmentId": 11, "serialNumber": "SN-NEW", "description": "Treadmill", "customerId": 501,
     "customerCode": "GYM01", "customerName": "Gym One", "siconSubLocationDbKey": 9001, "locationFull": "Gym One, Leeds"},
    {"siconEquipmentId": 12, "serialNumber": "SN-EXIST", "model": "X9", "installDate": "2021-05-05T00:00:00",
     "customerId": 501, "customerCode": "GYM01", "customerName": "Gym One", "siconSubLocationDbKey": 9001},
]
CASES = [{"siSMCaseId": 77, "caseNumber": "C77", "summary": "Belt slipping", "customerId": 501,
          "customerCode": "GYM01", "siconSubLocationDbKey": 9001}]
CONTRACTS = [{"siconContractId": 3, "contractNumber": "SC-3", "description": "Gold cover", "customerId": 501,
              "startDate": "2026-01-01", "endDate": "2026-12-31"}]


@pytest.fixture
def org():
    o = f"itest-onb-{uuid.uuid4().hex[:8]}"
    drive_async(db.equipment.insert_one({"id": f"{o}-eq", "organization_id": o, "serial_number": "SN-EXIST",
                                         "install_date": "2020-01-01", "name": "Existing bike"}))
    yield o

    async def clean():
        for c in COLLS:
            await db[c].delete_many({"organization_id": o})
    drive_async(clean())


def _run(org, apply, contracts=CONTRACTS):
    async def go():
        rid = str(uuid.uuid4())
        await db.sicon_sync_runs.insert_one({"id": rid, "organization_id": org, "entity": "onboarding"})
        await onb.run_onboarding(org, FakeClient(EQUIP, CASES, contracts), {}, rid, apply)
        return await db.sicon_sync_runs.find_one({"id": rid}, {"_id": 0})
    return drive_async(go())


def test_preview_writes_nothing_and_counts(org):
    run = _run(org, apply=False)
    c = run["counts"]
    assert run["status"] == "completed"
    assert c["customers"]["new"] == 1 and c["sites"]["new"] == 1
    assert c["equipment"]["new"] == 1 and c["equipment"]["matched"] == 1 and c["equipment"]["differences"] == 1
    assert c["contracts"]["new"] == 1 and c["cases"]["new"] == 1

    async def counts():
        return (await db.crm2_companies.count_documents({"organization_id": org}),
                await db.equipment.count_documents({"organization_id": org}),
                await db.issues.count_documents({"organization_id": org}))
    assert drive_async(counts()) == (0, 1, 0)


def test_apply_fills_gaps_and_flags_differences_idempotently(org):
    _run(org, apply=True)
    second = _run(org, apply=True)

    async def state():
        eq = await db.equipment.find_one({"id": f"{org}-eq"}, {"_id": 0})
        comp = await db.crm2_companies.find({"organization_id": org}, {"_id": 0}).to_list(5)
        site = await db.crm2_sites.find_one({"organization_id": org}, {"_id": 0})
        contract = await db.crm2_contracts.find_one({"organization_id": org}, {"_id": 0})
        issue = await db.issues.find_one({"organization_id": org}, {"_id": 0})
        diffs = await db.sicon_import_differences.find({"organization_id": org}, {"_id": 0}).to_list(10)
        assets = await db.equipment.count_documents({"organization_id": org})
        return eq, comp, site, contract, issue, diffs, assets
    eq, comp, site, contract, issue, diffs, assets = drive_async(state())
    assert eq["install_date"] == "2020-01-01"       # populated Pulse value kept
    assert eq["model"] == "X9"                      # empty field filled
    assert eq["company_id"] == comp[0]["id"] and eq["site_id"] == site["id"]
    assert [d["field"] for d in diffs] == ["install_date"]
    assert len(comp) == 1 and comp[0]["sage_customer_id"] == "GYM01"
    assert contract["company_id"] == comp[0]["id"] and contract["sicon_contract_id"] == 3
    assert issue["company_id"] == comp[0]["id"] and issue["asset_id"]
    assert assets == 2                              # idempotent: no duplicates on re-run
    assert second["counts"]["customers"]["matched"] == 1 and second["counts"]["equipment"]["new"] == 0


def test_name_only_customer_match_goes_to_review(org):
    drive_async(db.crm2_companies.insert_one({"id": f"{org}-c", "organization_id": org, "name": "gym one"}))
    run = _run(org, apply=True, contracts=None)
    assert run["counts"]["customers"]["conflicts"] == 1
    assert run["totals"]["contracts"] == "unavailable"
    n = drive_async(db.crm2_companies.count_documents({"organization_id": org}))
    assert n == 1
