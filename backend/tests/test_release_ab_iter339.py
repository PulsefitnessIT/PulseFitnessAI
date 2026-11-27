"""Iter 339 — retest of iteration_338 fixes with stronger assertions: cross-tenant link isolation (create/match/conflict
paths + upsert_link reassign), single-use approved preview (route 409 + engine consumed_by), noid held conflict,
decide_site failure rollback, Review Centre Sicon label, case->customer-owned asset attribution.
Synthetic TST data only; everything removed by id/tag. No Sicon/Sage network (fakes only)."""
import uuid

import pytest
import requests
from fastapi import HTTPException

from tests.shared_loop import run_async
from tests.test_release_ab_identity import FakeSicon
from tests.test_sage_sicon_customer_import import API, BASE, H, _db  # noqa: F401

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"


def _strip(d):
    return {k: v for k, v in (d or {}).items() if k != "_id"}


# --- Cross-tenant (create path): conflict recorded, no asset, no cross-link, other org's link byte-identical
def test_cross_tenant_new_record_is_conflict_and_other_link_untouched():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    c1, c2, seid = f"TST-x1-{tag}", f"TST-x2-{tag}", f"TSTY{tag}"

    async def go():
        L.SOURCE_CTX.set("shared.test#9")
        try:
            norm = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SY{tag}", "description": "TST Rower"})
            r1 = await IM.apply_equipment_record(c1, norm, {"bucket": "new", "reasons": []})
            before = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            r2 = await IM.apply_equipment_record(c2, norm, await IM.classify_equipment(norm, c2), run_id=f"TSTrun{tag}")
            after = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            nlinks = await adb.sicon_external_links.count_documents({"external_id": seid})
            n2 = await adb.equipment.count_documents({"organization_id": c2})
            conf = await adb.sicon_import_conflicts.find_one({"organization_id": c2, "external_id": seid}, {"_id": 0})
            # direct upsert_link without reassign must not mutate; with reassign it may
            u = await L.upsert_link("equipment", seid, "equipment", "TSTfake", organization_id=c2)
            after_u = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            return r1, before, r2, after, nlinks, n2, conf, u, after_u
        finally:
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.sicon_import_conflicts.delete_many({"external_id": seid})
            await adb.equipment.delete_many({"organization_id": {"$in": [c1, c2]}})
    r1, before, r2, after, nlinks, n2, conf, u, after_u = run_async(go())
    assert r2 == {"action": "conflict", "pulse_asset_id": None}, r2
    assert before == after and after["organization_id"] == c1 and after["pulse_entity_id"] == r1["pulse_asset_id"]
    assert nlinks == 1 and n2 == 0 and conf and conf["status"] == "open"
    assert u["sync_status"] == "conflict" and u["pulse_entity_id"] is None and after_u == before


# --- Cross-tenant (conflict bucket path): c2 has a same-serial asset with a different model -> set_status must not
# rewrite c1's link (organization_id / sync_status)
def test_cross_tenant_conflict_bucket_does_not_mutate_other_org_link():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    c1, c2, seid = f"TST-y1-{tag}", f"TST-y2-{tag}", f"TSTZ{tag}"

    async def go():
        L.SOURCE_CTX.set("shared.test#9")
        try:
            norm = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SZ{tag}", "description": "TST Bike",
                                           "model": "MODEL-A"})
            await IM.apply_equipment_record(c1, norm, {"bucket": "new", "reasons": []})
            before = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            await adb.equipment.insert_one({"id": f"TSTq-{tag}", "organization_id": c2, "serial_number": f"SZ{tag}", "model": "MODEL-B"})
            cls = await IM.classify_equipment(norm, c2)
            r2 = await IM.apply_equipment_record(c2, norm, cls, run_id=f"TSTrun{tag}")
            after = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            return cls, r2, before, after
        finally:
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.sicon_import_conflicts.delete_many({"external_id": seid})
            await adb.equipment.delete_many({"organization_id": {"$in": [c1, c2]}})
    cls, r2, before, after = run_async(go())
    assert cls["bucket"] == "conflict"
    assert after.get("organization_id") == c1, f"c1's link re-owned by c2: {after}"
    assert after.get("sync_status") == before.get("sync_status"), f"c1's link status changed: {before} -> {after}"


# --- Cross-tenant (match path): c2 has a same-serial asset -> c1's link untouched
def test_cross_tenant_match_bucket_does_not_mutate_other_org_link():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    c1, c2, seid = f"TST-z1-{tag}", f"TST-z2-{tag}", f"TSTW{tag}"

    async def go():
        L.SOURCE_CTX.set("shared.test#9")
        try:
            norm = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SW{tag}", "description": "TST Bike"})
            await IM.apply_equipment_record(c1, norm, {"bucket": "new", "reasons": []})
            before = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            await adb.equipment.insert_one({"id": f"TSTm-{tag}", "organization_id": c2, "serial_number": f"SW{tag}"})
            cls = await IM.classify_equipment(norm, c2)
            r2 = await IM.apply_equipment_record(c2, norm, cls, run_id=f"TSTrun{tag}")
            after = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            conf = await adb.sicon_import_conflicts.count_documents({"organization_id": c2, "external_id": seid})
            return cls, r2, before, after, conf
        finally:
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.sicon_import_conflicts.delete_many({"external_id": seid})
            await adb.equipment.delete_many({"organization_id": {"$in": [c1, c2]}})
    cls, r2, before, after, conf = run_async(go())
    print("match path:", cls["bucket"], r2, "conflicts:", conf)
    assert cls["bucket"] == "match"
    assert before == after


# --- Single-use preview (route): second apply -> 409
def test_onboarding_apply_route_single_use(monkeypatch):
    from routes import sicon as S
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    org, rid = f"TST-ap-{tag}", f"TSTpv-{tag}"
    started = []

    async def fake_start(user, apply, preview_run_id=None):
        started.append(preview_run_id)
        return {"success": True}
    monkeypatch.setattr(S, "_start_onboarding", fake_start)
    monkeypatch.setattr(S, "_require_owner_or_manager", lambda u: None)
    monkeypatch.setattr(S, "_require_org", lambda u: org)
    user = {"id": "t", "email": "tst@example.com"}

    async def go():
        await adb.sicon_sync_runs.insert_one({"id": rid, "organization_id": org, "entity": "onboarding", "mode": "preview",
                                              "status": "completed"})
        try:
            a = await S.onboarding_apply(rid, user)
            try:
                await S.onboarding_apply(rid, user)
                b = 200
            except HTTPException as e:
                b = e.status_code
            doc = await adb.sicon_sync_runs.find_one({"id": rid}, {"_id": 0})
            return a, b, doc
        finally:
            await adb.sicon_sync_runs.delete_many({"id": rid})
    a, b, doc = run_async(go())
    assert a["success"] and b == 409 and started == [rid] and doc.get("applied_at")


# --- Single-use preview (engine): second run_onboarding with the same preview ends 'failed'; noid held as conflict
def test_engine_consumed_preview_and_noid_held():
    run_async(_consumed())


async def _consumed():
    from utils import sicon_links as L, customer_identity as CI, sicon_onboarding as SO
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    co = await L.sage_company_for(OP)
    cref = f"CN{tag}"
    org, _ = await CI.provision_customer_org({"name": f"TST Cons {tag}"}, source="test", actor="t", ref=cref, company=co)
    runs = []

    async def sync(recs, prev=None):
        rid = f"TSTcn{len(runs)}-{tag}"
        runs.append(rid)
        await adb.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "preview_run_id": prev})
        await SO.run_onboarding(OP, FakeSicon([recs]), {}, rid, prev is not None)
        return rid
    try:
        recs = [{"customerCode": cref, "description": f"TST NoId Mat {tag}"},
                {"siconEquipmentId": f"7{tag}", "serialNumber": f"CN{tag}", "customerCode": cref, "description": "TST Bike"}]
        pv = await sync(recs)
        a1 = await sync(recs, pv)
        a2 = await sync(recs, pv)
        s1 = await adb.sicon_sync_runs.find_one({"id": a1}, {"_id": 0})
        s2 = await adb.sicon_sync_runs.find_one({"id": a2}, {"_id": 0})
        p = await adb.sicon_sync_runs.find_one({"id": pv}, {"_id": 0})
        n = await adb.equipment.count_documents({"organization_id": org})
        held = await adb.sicon_import_conflicts.count_documents({"run_id": a1, "external_id": {"$regex": "^noid:"}, "status": "open"})
        assert s1["status"] in ("completed", "partial"), s1
        assert s2["status"] == "failed" and "already" in (s2.get("error") or ""), s2
        assert p.get("consumed_by") == a1
        assert n == 1, f"expected only the Sicon-id asset, got {n}"
        assert held == 1, "noid record not held for review"
    finally:
        await adb.sicon_external_links.delete_many({"external_id": f"7{tag}"})
        await adb.sicon_import_conflicts.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await adb.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        await adb.equipment.delete_many({"organization_id": org})
        await adb.customer_account_refs.delete_many({"ref": cref})
        await adb.onboarding_projects.delete_many({"organization_id": org})
        await adb.crm2_companies.delete_many({"organization_id": OP, "sage_customer_id": {"$regex": tag}})
        await adb.organizations.delete_one({"id": org})


# --- decide_site: an unexpected failure returns the proposal to 'proposed'
def test_decide_failure_returns_to_proposed(monkeypatch):
    from routes import customer_account_import as R
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    pid = f"TSTdf-{tag}"

    async def ok(*a, **k):
        return None

    async def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(R, "_require_admin", ok)
    monkeypatch.setattr(R, "_apply_site_decision", boom)

    async def go():
        await adb.customer_proposed_sites.insert_one({"id": pid, "org_id": f"TST-df-{tag}", "status": "proposed", "name": "X",
                                                      "account_ref": ""})
        try:
            with pytest.raises(RuntimeError):
                await R.decide_site(pid, "confirm", "", False, {"id": "t", "email": "t@x"})
            return (await adb.customer_proposed_sites.find_one({"id": pid}))["status"]
        finally:
            await adb.customer_proposed_sites.delete_one({"id": pid})
    assert run_async(go()) == "proposed"


# --- Review Centre: Sicon proposed site labelled 'Sicon sub-location' with 'Sicon location <id>' ref
def test_review_labels_sicon_proposed_site(H):
    db = _db()
    tag = uuid.uuid4().hex[:6].upper()
    org = f"TST-rl-{tag}"
    db.customer_proposed_sites.insert_one({"id": f"TSTrl-{tag}", "org_id": org, "status": "proposed", "name": f"TSTRL {tag}",
                                           "account_ref": "", "sicon_sub_location_id": f"RL{tag}", "sicon_source": "h#1"})
    try:
        r = requests.get(f"{API}/review", headers=H, params={"search": f"TSTRL {tag}"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("items", body if isinstance(body, list) else [])
        hit = [i for i in items if i.get("site_id") == f"TSTrl-{tag}"]
        assert len(hit) == 1 and hit[0]["source"] == "Sicon sub-location" and hit[0]["ref"] == f"Sicon location RL{tag}", hit
    finally:
        db.customer_proposed_sites.delete_one({"id": f"TSTrl-{tag}"})


# --- Case in the Pulse workspace linked to a customer-owned asset gets customer_org_id/customer_site_id
def test_case_attach_sets_customer_org_and_site():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    cust, seid, aid, iid = f"TST-ca-{tag}", f"TSTCA{tag}", f"TSTa-{tag}", f"TSTi-{tag}"

    class C:
        async def svc_get_case_equipment(self, scid):
            return {"data": [{"siconEquipmentId": seid}]}

    async def go():
        L.SOURCE_CTX.set(await L.connection_company(OP))
        await adb.equipment.insert_one({"id": aid, "organization_id": cust, "site_id": f"TSTsite-{tag}", "name": "TST Bike",
                                        "sicon_equipment_id": seid, "serial_number": f"CA{tag}"})
        await L.upsert_link("equipment", seid, "equipment", aid, organization_id=cust)
        await adb.issues.insert_one({"id": iid, "organization_id": OP, "title": "TST case"})
        try:
            out = await IM._attach_case_equipment(OP, C(), "1", iid, f"TSTr{tag}")
            return out, await adb.issues.find_one({"id": iid}, {"_id": 0})
        finally:
            await adb.issues.delete_one({"id": iid})
            await adb.equipment.delete_one({"id": aid})
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.sicon_unmapped_equipment.delete_many({"sicon_equipment_id": seid}) if hasattr(adb, "x") else None
    out, issue = run_async(go())
    assert out["equipment_linked"] == 1, out
    assert issue["asset_id"] == aid and issue.get("customer_org_id") == cust and issue.get("customer_site_id") == f"TSTsite-{tag}", issue


# --- Follow-on of the conflict-bucket re-own: c2's next sync resolves c1's asset as 'linked' and writes onto it
def test_cross_tenant_conflict_then_resync_no_write_to_other_org_asset():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    c1, c2, seid = f"TST-v1-{tag}", f"TST-v2-{tag}", f"TSTV{tag}"

    async def go():
        L.SOURCE_CTX.set("shared.test#9")
        try:
            norm = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SV{tag}", "description": "TST Bike",
                                           "model": "MODEL-A"})
            r1 = await IM.apply_equipment_record(c1, norm, {"bucket": "new", "reasons": []})
            await adb.equipment.insert_one({"id": f"TSTv-{tag}", "organization_id": c2, "serial_number": f"SV{tag}", "model": "MODEL-B"})
            await IM.apply_equipment_record(c2, norm, await IM.classify_equipment(norm, c2), run_id=f"TSTrun{tag}")
            norm2 = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SV{tag}", "description": "TST C2 WROTE THIS",
                                            "model": "MODEL-A"})
            cls = await IM.classify_equipment(norm2, c2)
            r2 = await IM.apply_equipment_record(c2, norm2, cls, run_id=f"TSTrun{tag}")
            a1 = await adb.equipment.find_one({"id": r1["pulse_asset_id"]}, {"_id": 0})
            return cls, r2, r1, a1
        finally:
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.sicon_import_conflicts.delete_many({"external_id": seid})
            await adb.equipment.delete_many({"organization_id": {"$in": [c1, c2]}})
    cls, r2, r1, a1 = run_async(go())
    print("resync:", cls.get("bucket"), r2, "c1 asset desc:", a1.get("description"), a1.get("name"))
    assert r2.get("pulse_asset_id") != r1["pulse_asset_id"], f"c2 resolved c1's asset: {r2}"
    assert "C2 WROTE" not in str(a1), f"c2's sync wrote onto c1's asset: {a1}"
