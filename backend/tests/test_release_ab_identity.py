"""Release A/B: scoped Sicon links, reference reservation concurrency, Sage API → Import Centre job,
Sicon equipment destination/site resolution, partial-run status and preview→apply revalidation."""
import asyncio
import os
import uuid

import httpx

from utils.database import db

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"  # Pulse operator company (multi-customer workspace)


def test_release_ab_identity():
    from tests.shared_loop import run_async
    run_async(_run())


class FakeSicon:
    def __init__(self, pages):
        self.pages = pages

    async def svc_paginate(self, entity):
        if entity == "equipment":
            total = sum(len(p) for p in self.pages)
            for p in self.pages:
                yield {"totalRecords": total}, p

    async def svc_get_contracts(self):
        raise RuntimeError("404 no contract read route")

    async def _svc_get(self, path):
        raise RuntimeError("404")


async def _run():
    from utils import sicon_links as L
    from utils import customer_identity as CI
    from utils import sicon_onboarding as SO
    from routes import crm_sage200 as SG
    from routes import customer_account_import as CAI

    tag = uuid.uuid4().hex[:6].upper()
    orgs, jobs, runs = [], [], []
    ext = f"9{tag}"
    try:
        # 1) Links are scoped by connection company; identical numeric ids in two companies never collide.
        a = await L.upsert_link("equipment", ext, "equipment", "pa", organization_id="o1", source_company="101")
        b = await L.upsert_link("equipment", ext, "equipment", "pb", organization_id="o2", source_company="202")
        assert a["source_company"] == "101" and b["source_company"] == "202"
        assert await L.get_pulse_id("equipment", ext, "o1", "101") == "pa"
        assert await L.get_pulse_id("equipment", ext, "o2", "202") == "pb"
        # sync never reassigns an established link; explicit admin decisions may
        c = await L.upsert_link("equipment", ext, "equipment", "pz", organization_id="o1", source_company="101")
        assert c["sync_status"] == "conflict" and await L.get_pulse_id("equipment", ext, "o1", "101") == "pa"
        await L.upsert_link("equipment", ext, "equipment", "pz", organization_id="o1", source_company="101", reassign=True)
        assert await L.get_pulse_id("equipment", ext, "o1", "101") == "pz"
        # legacy unscoped link is reused (no duplicate) and only the audited migration scopes it
        await db.sicon_external_links.insert_one({"integration_source": "sicon", "external_entity_type": "site",
                                                  "external_id": ext, "organization_id": "o3", "pulse_entity_type": "crm2_site",
                                                  "pulse_entity_id": "legacy", "sync_status": "linked"})
        assert await L.get_pulse_id("site", ext, "o3", "303") == "legacy"
        await L.upsert_link("site", ext, "crm2_site", "legacy", organization_id="o3", source_company="303")
        assert await db.sicon_external_links.count_documents({"external_entity_type": "site", "external_id": ext}) == 1
        plan = await CAI._link_migration_plan()
        co3 = await L.connection_company("o3")
        if co3:  # falls back to the platform Sicon connection's company
            assert any(x["external_id"] == ext and x["source_company"] == co3 for x in plan["to_scope"])
        else:
            assert any(x["external_id"] == ext for x in plan["needs_review"])

        # 2) Reference reservation: an active job's reservation is never stolen; a dead one is.
        ref, company = f"R{tag}", f"TSTCO{tag}"
        job_id = f"tstjob-{tag}"
        await db.customer_import_jobs.insert_one({"id": job_id, "status": "committing", "heartbeat_at": CI._now()})
        jobs.append(job_id)
        await db.customer_account_refs.insert_one({"system": "sage", "company": company, "ref": ref, "org_id": "not-yet",
                                                   "job_id": job_id, "created_at": CI._now()})
        CI.RESERVATION_WAIT_STEPS = 2
        try:
            await CI.claim_ref(ref, company, "other", None, "test")
            raise AssertionError("active reservation was taken over")
        except CI.RefReserved:
            pass
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "rolled_back"}})
        assert await CI.claim_ref(ref, company, "other", None, "test") == "other"
        CI.RESERVATION_WAIT_STEPS = 10
        # concurrent provisioning of one new account -> exactly one organisation
        ref2 = f"C{tag}"
        res = await asyncio.gather(*[CI.provision_customer_org({"name": f"Conc {tag}"}, source="test", actor="t", ref=ref2,
                                                               company=company) for _ in range(5)], return_exceptions=True)
        ids = {r[0] for r in res if isinstance(r, tuple)}
        orgs += list(ids)
        assert len(ids) == 1, res
        assert await db.organizations.count_documents({"customer_account_number": ref2, "sage_company": company}) == 1

        # 3) Sage 200 API: every page retrieved, staged as an Import Centre job; nothing provisioned before approval.
        n_pages = []

        def handler(request):
            skip = int(request.url.params.get("$skip", "0"))
            n_pages.append(skip)
            size = 500 if skip < 1000 else 7
            return httpx.Response(200, json=[{"reference": f"S{tag}{skip + i}", "name": f"Sage Api {tag} {skip + i}",
                                              "address_1": "1 High St", "address_4": "Line Four", "postcode": "AB1 2CD"}
                                             for i in range(size)])
        real = httpx.AsyncClient
        SG.httpx.AsyncClient = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
        try:
            got = await SG.fetch_all_sage_customers("http://sage.test", {})
        finally:
            SG.httpx.AsyncClient = real
        assert len(got) == 1007 and n_pages == [0, 500, 1000]
        vals = SG.sage_api_customer_values(got[0])
        assert vals["AccountNumber"] == f"S{tag}0" and vals["AddressLine4"] == "Line Four"
        n_orgs = await db.organizations.count_documents({})
        job = await CAI.create_job("sage_accounts", [{"row": i + 1, "role": "record", "values": SG.sage_api_customer_values(c)}
                                                     for i, c in enumerate(got[:20])], {"email": "t@test"},
                                   source_company=company, filename="api", file_type="api", checksum=f"api-{tag}", size=20,
                                   detection={}, source="sage_200_api")
        jobs.append(job["id"])
        assert await db.customer_import_rows.count_documents({"job_id": job["id"]}) == 20
        assert await db.organizations.count_documents({}) == n_orgs

        # 4) Sicon equipment from the operator workspace lands in the right customer, matches the spreadsheet asset,
        #    never matches placeholder serials, holds unknown customers, and the run is 'partial' (no contract API).
        sage_co = await L.sage_company_for(OP)
        assert sage_co == (os.environ.get("SICON_SAGE_COMPANY") or "").strip().upper()
        cref = f"E{tag}"
        cust, _ = await CI.provision_customer_org({"name": f"Estate {tag}"}, source="test", actor="t", ref=cref, company=sage_co)
        orgs.append(cust)
        await db.sites.insert_one({"id": f"site-{tag}", "organization_id": cust, "name": f"Main Gym {tag}"})
        await db.equipment.insert_one({"id": f"eq-{tag}", "organization_id": cust, "name": "Treadmill",
                                       "serial_number": f"SN{tag}", "model": "T5"})
        await db.equipment.insert_one({"id": f"eq2-{tag}", "organization_id": cust, "name": "Bike", "serial_number": "N/A"})
        recs = [{"siconEquipmentId": f"7{tag}1", "serialNumber": f"sn{tag}", "model": "T5", "customerCode": cref,
                 "siconSubLocationDbKey": f"88{tag}", "locationFull": f"Main Gym {tag}", "description": "Treadmill"},
                {"siconEquipmentId": f"7{tag}2", "serialNumber": "N/A", "customerCode": cref, "description": "Bike"},
                {"siconEquipmentId": f"7{tag}3", "serialNumber": f"X{tag}", "customerCode": f"NOPE{tag}", "description": "Rower"}]
        client = FakeSicon([recs[:2], recs[2:]])
        pv = f"run-pv-{tag}"
        runs.append(pv)
        await db.sicon_sync_runs.insert_one({"id": pv, "organization_id": OP, "entity": "onboarding", "mode": "preview"})
        r = await SO.run_onboarding(OP, client, {}, pv, False)
        assert r["status"] == "partial" and any(m["resource"] == "contracts" for m in r["missing_resources"])
        # change one record after the preview -> it goes back to review instead of being applied
        recs[1]["description"] = "Bike (changed)"
        ap = f"run-ap-{tag}"
        runs.append(ap)
        await db.sicon_sync_runs.insert_one({"id": ap, "organization_id": OP, "entity": "onboarding", "mode": "apply",
                                             "preview_run_id": pv})
        r2 = await SO.run_onboarding(OP, client, {}, ap, True)
        assert r2["status"] == "partial"
        eq = await db.equipment.find_one({"id": f"eq-{tag}"}, {"_id": 0})
        assert eq.get("sicon_equipment_id") in (f"7{tag}1", int(f"7{tag}1") if f"7{tag}1".isdigit() else None)
        assert eq.get("site_id") == f"site-{tag}"
        assert await db.sites.find_one({"id": f"site-{tag}", "sicon_sub_location_id": f"88{tag}"})
        assert await db.equipment.count_documents({"organization_id": cust, "serial_number": {"$regex": f"^SN{tag}$", "$options": "i"}}) == 1
        assert await db.equipment.count_documents({"organization_id": OP, "description": {"$in": ["Treadmill", "Rower"]},
                                                   "sicon_customer_code": {"$in": [cref, f"NOPE{tag}"]}}) == 0
        assert await db.sicon_import_conflicts.find_one({"external_id": f"7{tag}2", "run_id": ap})  # changed since preview
        assert await db.sicon_import_conflicts.find_one({"external_id": f"7{tag}3"})  # unknown customer held
        assert not await db.equipment.find_one({"organization_id": cust, "sicon_equipment_id": {"$in": [f"7{tag}2", f"7{tag}3"]}})
    finally:
        await db.sicon_external_links.delete_many({"external_id": {"$regex": f"{tag}"}})
        await db.sicon_import_conflicts.delete_many({"external_id": {"$regex": f"{tag}"}})
        await db.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await db.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await db.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        await db.customer_account_refs.delete_many({"ref": {"$regex": f"{tag}"}})
        await db.customer_import_rows.delete_many({"job_id": {"$in": jobs}})
        await db.customer_import_jobs.delete_many({"id": {"$in": jobs}})
        await db.equipment.delete_many({"$or": [{"organization_id": {"$in": orgs}}, {"sicon_equipment_id": {"$regex": f"{tag}"}}]})
        await db.sites.delete_many({"organization_id": {"$in": orgs}})
        await db.customer_proposed_sites.delete_many({"org_id": {"$in": orgs}})
        await db.crm2_companies.delete_many({"organization_id": OP, "sage_customer_id": {"$regex": f"{tag}"}})
        await db.organizations.delete_many({"id": {"$in": orgs}})


def test_site_reconciliation_reservation_and_preview_destination():
    from tests.shared_loop import run_async
    run_async(_run2())


async def _run2():
    from utils import sicon_links as L, customer_identity as CI, sicon_onboarding as SO, sicon_import as IM
    from routes import customer_account_import as CAI
    tag = uuid.uuid4().hex[:6].upper()
    sage_co = await L.sage_company_for(OP)
    cref = f"G{tag}"
    cust, _ = await CI.provision_customer_org({"name": f"Sites {tag}"}, source="test", actor="t", ref=cref, company=sage_co)
    admin = {"email": "admin@pulsefitness.com", "is_master_admin": True}
    runs, n, blocked_id = [], [0], [""]
    recs = [{"siconEquipmentId": f"6{tag}1", "serialNumber": f"A{tag}1", "customerCode": cref, "siconSubLocationDbKey": f"S{tag}1",
             "locationFull": "Brand New Gym", "description": "Bike"},
            {"siconEquipmentId": f"6{tag}2", "serialNumber": f"A{tag}2", "customerCode": cref, "siconSubLocationDbKey": f"S{tag}2",
             "locationFull": "Upstairs Studio", "description": "Rower"}]

    async def sync(prev=None):
        n[0] += 1
        rid = f"r{n[0]}-{tag}"
        runs.append(rid)
        await db.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "preview_run_id": prev})
        await SO.run_onboarding(OP, FakeSicon([recs]), {}, rid, prev is not None)
        return rid
    try:
        await db.sites.insert_one({"id": f"old-{tag}", "organization_id": cust, "name": "Old Annex"})
        pv = await sync()
        await sync(pv)  # apply: unknown sub-locations become proposals (no sites created)
        props = [p async for p in db.customer_proposed_sites.find({"org_id": cust}, {"_id": 0})]
        assert len(props) == 2 and all(p["account_ref"] == "" and p["sicon_sub_location_id"] and p["sicon_source"] for p in props)
        assert await db.sites.count_documents({"organization_id": cust}) == 1
        p1 = next(p for p in props if p["sicon_sub_location_id"] == f"S{tag}1")
        p2 = next(p for p in props if p["sicon_sub_location_id"] == f"S{tag}2")
        r = await CAI.decide_site(p1["id"], "confirm", user=admin)
        r2 = await CAI.decide_site(p2["id"], "link", link_site_id=f"old-{tag}", user=admin)
        s1 = await db.sites.find_one({"id": r["site_id"]}, {"_id": 0})
        assert s1["sicon_sub_location_id"] == f"S{tag}1" and not s1.get("invoice_customer_ref", "").startswith("SICON")
        assert (await db.sites.find_one({"id": f"old-{tag}"}))["sicon_sub_location_id"] == f"S{tag}2"
        # equipment already synced joined its site
        assert (await db.equipment.find_one({"sicon_equipment_id": f"6{tag}1"}))["site_id"] == r["site_id"]
        assert (await db.equipment.find_one({"sicon_equipment_id": f"6{tag}2"}))["site_id"] == r2["site_id"]
        # sync again: same sites recognised, no duplicates, no new proposals
        pv2 = await sync()
        await sync(pv2)
        assert await db.sites.count_documents({"organization_id": cust}) == 2
        assert await db.customer_proposed_sites.count_documents({"org_id": cust}) == 2
        assert await db.equipment.count_documents({"organization_id": cust}) == 2
        # destination changed after approval -> back to review
        pv3 = await sync()
        await db.equipment.update_one({"sicon_equipment_id": f"6{tag}1"}, {"$set": {"model": "edited", "updated_at": "x"}})
        ap3 = await sync(pv3)
        assert await db.sicon_import_conflicts.find_one({"external_id": f"6{tag}1", "run_id": ap3})
        # link carries the actual source connection
        lk = await db.sicon_external_links.find_one({"external_id": f"6{tag}2"}, {"_id": 0})
        assert lk["source_company"] == (await L.connection_company(OP) or "unscoped")
        # concurrent creation of the same Sicon id -> exactly one asset
        norm = IM.normalise_equipment({"siconEquipmentId": f"6{tag}9", "serialNumber": f"Z{tag}", "description": "Dup"})
        L.SOURCE_CTX.set(await L.connection_company(OP))
        res = await asyncio.gather(*[IM.apply_equipment_record(cust, norm, {"bucket": "new", "reasons": []}) for _ in range(4)])
        assert len({x["pulse_asset_id"] for x in res}) == 1
        assert await db.equipment.count_documents({"sicon_equipment_id": f"6{tag}9"}) == 1
        # the old per-entity sync cannot bypass the customer-aware engine in the Pulse workspace
        blocked = await IM.run_equipment_sync(OP, FakeSicon([recs]))
        blocked_id[0] = blocked["run_id"]
        assert blocked["status"] == "blocked"
    finally:
        await db.sicon_external_links.delete_many({"external_id": {"$regex": tag}})
        await db.sicon_import_conflicts.delete_many({"external_id": {"$regex": tag}})
        await db.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await db.sicon_sync_runs.delete_many({"id": {"$in": runs + [blocked_id[0]]}})
        await db.equipment.delete_many({"$or": [{"organization_id": cust}, {"sicon_equipment_id": {"$regex": tag}}]})
        await db.sites.delete_many({"organization_id": cust})
        await db.customer_proposed_sites.delete_many({"org_id": cust})
        await db.customer_account_refs.delete_many({"ref": cref})
        await db.onboarding_projects.delete_many({"organization_id": cust})
        await db.organizations.delete_one({"id": cust})
