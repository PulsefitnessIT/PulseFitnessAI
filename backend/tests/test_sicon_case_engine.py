"""Offline tests for the Sicon CaseSearch → Service Desk import (spec §12/§13)."""
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


def _case(scid, **kw):
    d = {"siSMCaseId": scid, "caseNumber": f"CN{scid}", "summary": "Broken belt"}
    d.update(kw)
    return d


async def _cleanup(org):
    await db.issues.delete_many({"organization_id": org})
    await db.sicon_external_links.delete_many({"organization_id": org})
    await db.sicon_sync_runs.delete_many({"organization_id": org})


@pytest.fixture
def org():
    o = f"itest-siconc-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(_cleanup(o))


def test_case_new_then_idempotent(org):
    async def run():
        norm = imp.normalise_case(_case(7001))
        c1 = await imp.classify_case(norm, org)
        r1 = await imp.apply_case_record(org, norm, c1, {})
        c2 = await imp.classify_case(norm, org)
        r2 = await imp.apply_case_record(org, norm, c2, {})
        n = await db.issues.count_documents({"organization_id": org, "sicon_case_id": 7001})
        return r1["action"], c2["bucket"], r2["action"], n
    a1, b2, a2, n = drive_async(run())
    assert a1 == "created" and b2 == "linked" and a2 == "updated"
    assert n == 1


def test_reference_mapping_applied(org):
    async def run():
        cfg = {"tracking_status_mapping": {"5": "resolved", "In Progress": "in_progress"},
               "priority_mapping": {"3": "safety_critical"}}
        norm = imp.normalise_case(_case(7002,
                                        trackingStatus={"siSMTrackingStatusId": 5, "name": "Closed"},
                                        priority={"siSMPriorityId": 3, "name": "Urgent"}))
        cls = await imp.classify_case(norm, org)
        await imp.apply_case_record(org, norm, cls, cfg)
        doc = await db.issues.find_one({"organization_id": org, "sicon_case_id": 7002}, {"_id": 0})
        return doc
    doc = drive_async(run())
    assert doc["status"] == "resolved"          # mapped by tracking-status id 5
    assert doc["severity"] == "safety_critical"  # mapped by priority id 3
    assert doc["sicon_case_number"] == "CN7002"


def test_unmapped_falls_back_to_defaults(org):
    async def run():
        norm = imp.normalise_case(_case(7003, trackingStatus="Weird", priority="Nope"))
        cls = await imp.classify_case(norm, org)
        await imp.apply_case_record(org, norm, cls, {})
        return await db.issues.find_one({"organization_id": org, "sicon_case_id": 7003}, {"_id": 0})
    doc = drive_async(run())
    assert doc["status"] == "open"
    assert doc["severity"] == "operational_fault"


def test_customer_and_site_link_resolved_from_map(org):
    async def run():
        await links.upsert_link("customer", 2541439, "crm2_company", "pulse-co-1", organization_id=org)
        await links.upsert_link("site", 88, "crm2_site", "pulse-site-1", organization_id=org)
        norm = imp.normalise_case(_case(7004, customerId=2541439, siconSubLocationDbKey=88))
        cls = await imp.classify_case(norm, org)
        await imp.apply_case_record(org, norm, cls, {})
        return await db.issues.find_one({"organization_id": org, "sicon_case_id": 7004}, {"_id": 0})
    doc = drive_async(run())
    assert doc["company_id"] == "pulse-co-1"
    assert doc["site_id"] == "pulse-site-1"


def test_case_sync_failure_isolation(org):
    async def run():
        pages = [({"currentPage": 1, "nextPage": None, "pageSize": 50, "totalRecords": 3},
                  [_case(7005), "GARBAGE", _case(7006)])]
        result = await imp.run_case_sync(org, FakeClient(pages), {}, run_id="itest-crun")
        created = await db.issues.count_documents({"organization_id": org})
        return result, created
    result, created = drive_async(run())
    assert result["status"] == "completed"
    assert result["counts"]["failed"] == 1
    assert result["counts"]["created"] == 2
    assert created == 2


def test_customer_auto_matched_by_sage_code(org):
    """Hands-off: no manual mapping — a unique sage_customer_id == Sicon
    customerCode is auto-linked and remembered (sync_status 'auto')."""
    async def run():
        await db.crm2_companies.insert_one({
            "id": "pulse-co-auto", "organization_id": org,
            "name": "Get Active @ Jesmond", "sage_customer_id": "00001026"})
        norm = imp.normalise_case(_case(7100, customerId=2541439, customerCode="00001026"))
        cls = await imp.classify_case(norm, org)
        await imp.apply_case_record(org, norm, cls, {})
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 7100}, {"_id": 0})
        link = await links.get_link("customer", 2541439, org)
        await db.crm2_companies.delete_many({"organization_id": org})
        return issue, link
    issue, link = drive_async(run())
    assert issue["company_id"] == "pulse-co-auto"        # auto-resolved, no manual map
    assert link and link["pulse_entity_id"] == "pulse-co-auto"
    assert link["sync_status"] == "auto"                 # remembered for next time


def test_customer_not_guessed_by_name(org):
    """Ambiguous / no code match must NOT link by name alone (§11)."""
    async def run():
        await db.crm2_companies.insert_one({
            "id": "pulse-co-x", "organization_id": org, "name": "Get Active @ Jesmond"})
        norm = imp.normalise_case(_case(7101, customerId=999, customerCode="NOPE",
                                        customerName="Get Active @ Jesmond"))
        cls = await imp.classify_case(norm, org)
        await imp.apply_case_record(org, norm, cls, {})
        issue = await db.issues.find_one({"organization_id": org, "sicon_case_id": 7101}, {"_id": 0})
        await db.crm2_companies.delete_many({"organization_id": org})
        return issue
    issue = drive_async(run())
    assert "company_id" not in issue  # name match is never definitive
