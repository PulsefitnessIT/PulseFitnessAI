"""Estate-scale: Sicon equipment sync of N records (default 20,000) through the operator workspace into one customer
organisation, then a repeat sync. Measures time and peak memory; checks no duplicates. Run: ESTATE_N=20000 pytest -k large"""
import asyncio
import os
import resource
import time
import uuid

from utils.database import db

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
N = int(os.environ.get("ESTATE_N", "20000"))


class Pager:
    def __init__(self, tag, cref):
        self.tag, self.cref = tag, cref

    async def svc_paginate(self, entity):
        if entity != "equipment":
            return
        for start in range(0, N, 200):
            yield {"totalRecords": N}, [{"siconEquipmentId": f"8{self.tag}{i}", "serialNumber": f"SER{self.tag}{i}",
                                         "customerCode": self.cref, "model": "T5", "description": f"Machine {i}",
                                         "siconSubLocationDbKey": f"L{self.tag}{i % 30}", "locationFull": f"Site {i % 30}"}
                                        for i in range(start, min(start + 200, N))]

    async def svc_get_contracts(self):
        raise RuntimeError("unavailable")

    async def _svc_get(self, path):
        raise RuntimeError("unavailable")


def test_large_estate_sync():
    from tests.shared_loop import run_async
    run_async(_run())


async def _run():
    from utils import customer_identity as CI, sicon_links as L, sicon_onboarding as SO
    tag = uuid.uuid4().hex[:5].upper()
    cref = f"BIG{tag}"
    cust, _ = await CI.provision_customer_org({"name": f"TST Big Estate {tag}"}, source="test", actor="t", ref=cref,
                                              company=await L.sage_company_for(OP))
    runs = []
    try:
        for k in range(2):
            rid = f"big-{tag}-{k}"
            runs.append(rid)
            await db.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "mode": "apply"})
            t0 = time.time()
            r = await SO.run_onboarding(OP, Pager(tag, cref), {}, rid, True)
            print(f"pass {k + 1}: {N} records in {time.time() - t0:.1f}s, peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024} MB,"
                  f" counts={r['counts']['equipment']}")
            assert await db.equipment.count_documents({"organization_id": cust}) == N
        assert await db.sicon_external_links.count_documents({"external_entity_type": "equipment", "external_id": {"$regex": f"^8{tag}"}}) == N
    finally:
        await db.equipment.delete_many({"organization_id": cust})
        await db.sicon_external_links.delete_many({"external_id": {"$regex": f"^8{tag}"}})
        await db.customer_proposed_sites.delete_many({"org_id": cust})
        await db.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await db.sicon_import_differences.delete_many({"external_id": {"$regex": f"^8{tag}"}})
        await db.customer_account_refs.delete_many({"ref": cref})
        await db.onboarding_projects.delete_many({"organization_id": cust})
        await db.organizations.delete_one({"id": cust})
