"""Release 1: supervised Sicon acceptance can restrict an approved apply to sample customers only."""
import uuid

from tests.shared_loop import run_async
from tests.test_release_ab_identity import FakeSicon
from tests.test_release_ab_iter339 import OP


def test_apply_restricted_to_sample_customers():
    run_async(_sample())


async def _sample():
    from utils import sicon_links as L, customer_identity as CI, sicon_onboarding as SO
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    co = await L.sage_company_for(OP)
    ra, rb = f"SA{tag}", f"SB{tag}"
    a, _ = await CI.provision_customer_org({"name": f"TST Sample A {tag}"}, source="test", actor="t", ref=ra, company=co)
    b, _ = await CI.provision_customer_org({"name": f"TST Sample B {tag}"}, source="test", actor="t", ref=rb, company=co)
    recs = [{"siconEquipmentId": f"81{tag}", "serialNumber": f"SA{tag}1", "customerCode": ra, "description": "TST Bike A"},
            {"siconEquipmentId": f"82{tag}", "serialNumber": f"SB{tag}1", "customerCode": rb, "description": "TST Bike B"}]
    runs = []
    try:
        for prev, cfg in ((None, {}), ("PV", {"sample_org_ids": [a]})):
            rid = f"TSTsm{len(runs)}-{tag}"
            pv = runs[0] if prev else None
            runs.append(rid)
            await adb.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "preview_run_id": pv})
            await SO.run_onboarding(OP, FakeSicon([recs]), cfg, rid, prev is not None)
        assert await adb.equipment.count_documents({"organization_id": a}) == 1
        assert await adb.equipment.count_documents({"organization_id": b}) == 0  # outside sample: untouched
        assert await adb.sicon_import_conflicts.count_documents({"run_id": runs[1], "external_id": f"82{tag}"}) == 0
        # Nothing at all is written for the customer outside the sample: sites, cases, proposed sites, review items, links.
        for coll in ("sites", "issues", "service_cases", "customer_proposed_sites", "sicon_import_conflicts", "review_items"):
            n = await adb[coll].count_documents({"$or": [{"organization_id": b}, {"org_id": b}, {"customer_org_id": b}]})
            assert n == 0, (coll, n)
        assert await adb.sicon_external_links.count_documents({"external_id": f"82{tag}"}) == 0
        assert await adb.crm2_companies.count_documents({"sage_customer_id": {"$regex": rb}}) == 0
        run = await adb.sicon_sync_runs.find_one({"id": runs[1]}, {"_id": 0})
        assert ((run.get("counts") or {}).get("outside_sample") or {}).get("skipped") == 1, run.get("counts")
    finally:
        await adb.sicon_external_links.delete_many({"external_id": {"$in": [f"81{tag}", f"82{tag}"]}})
        await adb.sicon_import_conflicts.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await adb.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        for o, r in ((a, ra), (b, rb)):
            await adb.equipment.delete_many({"organization_id": o})
            await adb.customer_account_refs.delete_many({"ref": r})
            await adb.onboarding_projects.delete_many({"organization_id": o})
            await adb.organizations.delete_one({"id": o})
        await adb.crm2_companies.delete_many({"organization_id": OP, "sage_customer_id": {"$regex": tag}})
