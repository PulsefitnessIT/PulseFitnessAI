"""Iter 338 — Release A/B final P0 corrections: nightly sync gate + SOURCE_CTX per run, shared 'estate' lock,
cross-tenant link isolation, Sage read-only + config-derived pull company, site reconciliation (Sicon + Sage
proposals via HTTP), delegated-staff history, preview fingerprint 'noid:' key, Review Centre held grouping.
Synthetic TST data only; everything created is removed by id/tag. No Sicon/Sage network calls (fakes only)."""
import uuid

import pytest
import requests
from fastapi import HTTPException

from tests.shared_loop import run_async
from tests.test_release_ab_identity import FakeSicon
from tests.test_sage_sicon_customer_import import API, BASE, H, _db  # noqa: F401

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
ADMIN = {"email": "admin@pulsefitness.com", "is_master_admin": True}


# --- Nightly sync gate
def test_nightly_does_nothing_unless_enabled(monkeypatch):
    from routes import sicon as S
    calls = []
    monkeypatch.delenv("SICON_NIGHTLY_SYNC_ENABLED", raising=False)

    async def rec(*a, **k):
        calls.append(a)
    monkeypatch.setattr(S._imp, "run_equipment_sync", rec)
    monkeypatch.setattr(S._imp, "run_case_sync", rec)
    monkeypatch.setattr(S, "get_sicon_client", rec)
    run_async(S._run_all_org_sicon_sync())
    assert calls == []
    monkeypatch.setenv("SICON_NIGHTLY_SYNC_ENABLED", "false")
    run_async(S._run_all_org_sicon_sync())
    assert calls == []


# --- Nightly with flag ON: each org's equipment links must be scoped by THAT org's connection (no SOURCE_CTX leak)
def test_nightly_source_ctx_not_leaked_between_orgs(monkeypatch):
    from routes import sicon as S
    from utils import sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    oa, ob = f"TST-nA-{tag}", f"TST-nB-{tag}"
    seen = {}
    real_eq = S._imp.run_equipment_sync

    async def eq_wrap(org_id, client, **kw):
        seen[org_id] = L.SOURCE_CTX.get()
        return await real_eq(org_id, client, **kw)

    async def client_for(org_id):
        if org_id == ob:
            return FakeSicon([[{"siconEquipmentId": f"TSTNB{tag}", "serialNumber": f"NB{tag}", "description": "TST Bike"}]])
        if org_id == oa:
            return FakeSicon([[]])
        return None

    async def cfg(_o):
        return {}

    async def noop(*a, **k):
        return None
    monkeypatch.setenv("SICON_NIGHTLY_SYNC_ENABLED", "true")
    monkeypatch.setattr(S._imp, "run_equipment_sync", eq_wrap)
    monkeypatch.setattr(S, "get_sicon_client", client_for)
    monkeypatch.setattr(S, "get_sicon_config", cfg)
    monkeypatch.setattr(S, "log_sicon_event", noop)

    async def go():
        await adb.sicon_config.insert_many([
            {"organization_id": oa, "enabled": True, "company_id": "11", "base_url": "https://sicon-a.test", "tst": tag},
            {"organization_id": ob, "enabled": True, "company_id": "22", "base_url": "https://sicon-b.test", "tst": tag}])
        try:
            L._COMPANY_CACHE.pop(oa, None)
            L._COMPANY_CACHE.pop(ob, None)
            await S._run_all_org_sicon_sync()
            return await adb.sicon_external_links.find_one({"external_id": f"TSTNB{tag}"}, {"_id": 0})
        finally:
            await adb.sicon_config.delete_many({"tst": tag})
            await adb.sicon_external_links.delete_many({"external_id": f"TSTNB{tag}"})
            await adb.equipment.delete_many({"organization_id": {"$in": [oa, ob]}})
            await adb.sicon_sync_runs.delete_many({"organization_id": {"$in": [oa, ob]}})
            await adb.sicon_sync_locks.delete_many({"organization_id": {"$in": [oa, ob]}})
    lk = run_async(go())
    assert lk, "org B equipment was not synced"
    assert lk["source_company"] == "sicon-b.test#22", f"leaked connection: {lk['source_company']} (ctx at entry {seen.get(ob)})"


# --- Shared estate lock
def test_estate_lock_shared_by_onboarding_equipment_case():
    from utils import sicon_import as IM
    from utils.database import db as adb
    org = f"TST-lock-{uuid.uuid4().hex[:6]}"

    async def go():
        try:
            a = await IM.acquire_sync_lock(org, "onboarding", "r1")
            b = await IM.acquire_sync_lock(org, "equipment", "r2")
            c = await IM.acquire_sync_lock(org, "case", "r3")
            await IM.release_sync_lock(org, "onboarding", "r1")
            d = await IM.acquire_sync_lock(org, "case", "r4")
            n = await adb.sicon_sync_locks.count_documents({"organization_id": org})
            return a, b, c, d, n
        finally:
            await adb.sicon_sync_locks.delete_many({"organization_id": org})
    a, b, c, d, n = run_async(go())
    assert (a, b, c, d, n) == (True, False, False, True, 1)


# --- Pulse workspace: equipment sync blocked and writes nothing
def test_workspace_equipment_sync_blocked_writes_nothing():
    from utils import sicon_import as IM
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()

    async def go():
        rid = f"TST-blk-{tag}"
        try:
            n0 = await adb.equipment.count_documents({"organization_id": OP})
            r = await IM.run_equipment_sync(OP, FakeSicon([[{"siconEquipmentId": f"TSTW{tag}", "description": "x"}]]), run_id=rid)
            n1 = await adb.equipment.count_documents({"organization_id": OP})
            lk = await adb.sicon_external_links.count_documents({"external_id": f"TSTW{tag}"})
            return r, n0, n1, lk
        finally:
            await adb.sicon_sync_runs.delete_one({"id": rid})
    r, n0, n1, lk = run_async(go())
    assert r["status"] == "blocked" and n0 == n1 and lk == 0


# --- Cross-tenant: a customer org must never resolve/receive/mutate another customer's link
def test_customer_org_cannot_claim_other_customers_link():
    from utils import sicon_import as IM, sicon_links as L
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    c1, c2 = f"TST-c1-{tag}", f"TST-c2-{tag}"
    seid = f"TSTX{tag}"

    async def go():
        L.SOURCE_CTX.set("shared.test#9")
        try:
            norm = IM.normalise_equipment({"siconEquipmentId": seid, "serialNumber": f"SX{tag}", "description": "TST Rower"})
            r1 = await IM.apply_equipment_record(c1, norm, {"bucket": "new", "reasons": []})
            vis = await L.get_link("equipment", seid, c2)
            cls2 = await IM.classify_equipment(norm, c2)
            r2 = await IM.apply_equipment_record(c2, norm, cls2)
            a1 = await adb.equipment.find_one({"id": r1["pulse_asset_id"]}, {"_id": 0, "organization_id": 1})
            lk = await adb.sicon_external_links.find_one({"external_id": seid}, {"_id": 0})
            return r1, vis, cls2, r2, a1, lk
        finally:
            await adb.sicon_external_links.delete_many({"external_id": seid})
            await adb.equipment.delete_many({"organization_id": {"$in": [c1, c2]}})
    r1, vis, cls2, r2, a1, lk = run_async(go())
    assert vis is None and cls2["bucket"] == "new"
    assert a1["organization_id"] == c1 and lk["organization_id"] == c1 and lk["pulse_entity_id"] == r1["pulse_asset_id"]
    # c2 must not be handed c1's asset id as its own 'linked' asset
    assert r2["pulse_asset_id"] != r1["pulse_asset_id"], f"c2 got c1's asset: {r2}"


# --- Sage: pull company from config (400 none / 409 mismatch), writes 403 unless SAGE_ALLOW_WRITES
def test_sage_pull_company_from_config_and_write_guard(monkeypatch):
    from routes import crm_sage200 as SG
    cfg = {"v": None}

    async def gc():
        return cfg["v"]
    monkeypatch.setattr(SG, "get_sage_config", gc)
    u = {"id": "t", "is_master_admin": True}

    def call(coro):
        try:
            run_async(coro)
            return 200, ""
        except HTTPException as e:
            return e.status_code, str(e.detail)
    assert call(SG.sync_customers_to_crm("", u))[0] == 400
    cfg["v"] = {"company_name": "", "company_id": ""}
    assert call(SG.sync_customers_to_crm("", u))[0] == 400
    cfg["v"] = {"company_name": "Pulse Fitness"}
    assert call(SG.sync_customers_to_crm("Other Co", u))[0] == 409
    assert call(SG.sync_customers_to_crm("PULSE fitness", u))[0] == 503  # passes identity, no token -> no network
    cfg["v"] = {"company_id": "77"}
    assert call(SG.sync_customers_to_crm("77", u))[0] == 503
    assert call(SG.sync_customers_to_crm("", {"id": "x", "role": "admin"}))[0] == 403
    monkeypatch.delenv("SAGE_ALLOW_WRITES", raising=False)
    s, d = call(SG.push_contacts_to_sage(u))
    assert s == 403 and "read-only" in d
    monkeypatch.setenv("SAGE_ALLOW_WRITES", "true")
    cfg["v"] = {}
    assert call(SG.push_contacts_to_sage(u))[0] == 503  # guard passed; nothing configured, nothing pushed


def test_sage_http_tenant_forbidden_admin_readonly():
    def tok(email, pw):
        r = requests.post(f"{BASE}/api/crm/auth/login", json={"email": email, "password": pw}, timeout=30)
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}
    from tests.test_release_ab_onboarding import requests as _r  # noqa: F401
    t = tok("owner@isodemo.com", "IsoDemo123!")
    for m, p in (("get", "/config"), ("post", "/config"), ("get", "/customers"), ("post", "/sync/customers"),
                 ("post", "/sync/customers-to-sage")):
        assert getattr(requests, m)(f"{BASE}/api/crm/sage200{p}", headers=t, json={}, timeout=30).status_code == 403, p
    a = tok("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
    g = requests.get(f"{BASE}/api/crm/sage200/config", headers=a, timeout=30)
    assert g.status_code == 200
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers-to-sage", headers=a, timeout=30)
    assert r.status_code == 403 and "read-only" in r.text
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers", params={"source_company": "TST NOT THE COMPANY"},
                      headers=a, timeout=30)
    assert r.status_code in (400, 409), r.text


# --- Site reconciliation via HTTP: Sage proposals (confirm/force/link/reject) and Sicon link 409
def test_proposed_sites_http_sage_and_sicon(H):
    db = _db()
    tag = uuid.uuid4().hex[:6].upper()
    org = f"TST-ps-{tag}"
    db.organizations.insert_one({"id": org, "name": f"TST PS {tag}", "account_type": "lite"})
    db.sites.insert_many([{"id": f"TSTs1-{tag}", "organization_id": org, "name": "Main", "postcode": "AB1 2CD"},
                          {"id": f"TSTs2-{tag}", "organization_id": org, "name": "Annex", "sicon_sub_location_id": f"OTHER{tag}"}])
    def mk(i, **kw):
        return {"id": f"TSTp{i}-{tag}", "org_id": org, "status": "proposed", "name": f"P{i}", "address_line1": "",
                "city": "", "postcode": kw.pop("postcode", ""), "account_ref": kw.pop("account_ref", ""), **kw}
    db.customer_proposed_sites.insert_many([
        mk(1, account_ref=f"SA{tag}1", postcode="AB12CD"),   # Sage twin postcode -> 409, then force
        mk(2, account_ref=f"SA{tag}2"),                      # Sage link
        mk(3, account_ref=f"SA{tag}3"),                      # Sage reject
        mk(4, sicon_sub_location_id=f"SUB{tag}", sicon_source="h#1")])  # Sicon link to site with other sub -> 409
    db.equipment.insert_one({"id": f"TSTe-{tag}", "organization_id": org, "sicon_sub_location_id": f"SUB{tag}", "site_id": ""})
    U = f"{API}/proposed-sites"
    try:
        r = requests.post(f"{U}/TSTp1-{tag}/confirm", headers=H, timeout=30)
        assert r.status_code == 409 and "existing_sites" in r.text
        r = requests.post(f"{U}/TSTp1-{tag}/confirm", params={"force": "true"}, headers=H, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "confirmed"
        s = db.sites.find_one({"id": r.json()["site_id"]})
        assert s["invoice_customer_ref"] == f"SA{tag}1" and "sicon_sub_location_id" not in s
        r = requests.post(f"{U}/TSTp2-{tag}/link", params={"link_site_id": f"TSTs1-{tag}"}, headers=H, timeout=30)
        assert r.status_code == 200 and db.sites.find_one({"id": f"TSTs1-{tag}"})["invoice_customer_ref"] == f"SA{tag}2"
        assert requests.post(f"{U}/TSTp3-{tag}/reject", headers=H, timeout=30).json()["status"] == "rejected"
        assert requests.post(f"{U}/TSTp3-{tag}/reject", headers=H, timeout=30).status_code == 409  # already decided
        r = requests.post(f"{U}/TSTp4-{tag}/link", params={"link_site_id": f"TSTs2-{tag}"}, headers=H, timeout=30)
        assert r.status_code == 409
        assert db.customer_proposed_sites.find_one({"id": f"TSTp4-{tag}"})["status"] == "proposed"  # released
        r = requests.post(f"{U}/TSTp4-{tag}/confirm", headers=H, timeout=30)
        assert r.status_code == 200
        sid = r.json()["site_id"]
        s = db.sites.find_one({"id": sid})
        assert s["sicon_sub_location_id"] == f"SUB{tag}" and s["sicon_source"] == "h#1" and s["invoice_customer_ref"] == ""
        assert db.equipment.find_one({"id": f"TSTe-{tag}"})["site_id"] == sid
        # tenant cannot decide
        ct = requests.post(f"{BASE}/api/auth/login", json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}, timeout=30)
        if ct.status_code == 200 and ct.json().get("token"):
            assert requests.post(f"{U}/x/confirm", headers={"Authorization": f"Bearer {ct.json()['token']}"},
                                 timeout=30).status_code == 403
    finally:
        db.customer_proposed_sites.delete_many({"org_id": org})
        db.sites.delete_many({"organization_id": org})
        db.equipment.delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})


# --- Delegated staff: revoke recorded in history; transfer revokes review/onboarding project detail
def test_delegate_history_records_every_change(H):
    db = _db()
    op = db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1})
    uid, email = str(uuid.uuid4()), f"tst.hist.{uuid.uuid4().hex[:6]}@pulsefitness.com"
    db.users.insert_one({"id": uid, "email": email, "organization_id": op["id"], "role": "manager", "is_active": True})
    try:
        for perms in (["imports.review"], ["imports.review", "activation.view"], []):
            assert requests.post(f"{API}/delegates", headers=H, timeout=30,
                                 json={"email": email, "permissions": perms}).status_code == 200
        hist = list(db.onboarding_permission_history.find({"email": email}, {"_id": 0}).sort("at", 1))
        assert len(hist) == 3 and hist[-1]["revoked"] == ["activation.view", "imports.review"] and hist[-1]["after"] == []
        u = db.users.find_one({"id": uid})
        assert u["onboarding_permissions"] == [] and u["is_pulse_staff"] is False
        from utils.auth import create_token
        D = {"Authorization": f"Bearer {create_token(uid)}"}
        assert requests.get(f"{API}/review", headers=D, timeout=30).status_code == 403
        assert requests.post(f"{API}/delegates", headers=H, timeout=30,
                             json={"email": email, "permissions": ["bogus.perm"]}).status_code == 400
    finally:
        db.users.delete_one({"id": uid})
        db.onboarding_permission_history.delete_many({"email": email})


# --- Review Centre groups held Sicon equipment per unresolved customer code
def test_review_groups_held_equipment(H):
    db = _db()
    tag = uuid.uuid4().hex[:6].upper()
    code = f"TSTHELD{tag}"
    reason = f"Customer '{code}' is not a single Pulse customer under the configured Sage company — import first"
    db.sicon_import_conflicts.insert_many([{"organization_id": OP, "external_entity_type": "equipment", "external_id": f"TSTH{tag}{i}",
                                            "status": "open", "reasons": [reason], "sicon_record": {"sicon_customer_code": code}}
                                           for i in range(3)])
    try:
        r = requests.get(f"{API}/review", headers=H, params={"search": code}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("items", body if isinstance(body, list) else [])
        held = [i for i in items if i.get("ref") == code]
        assert len(held) == 1 and held[0]["type"] == "Held Sicon equipment (customer not imported)" and "3" in held[0]["name"]
    finally:
        db.sicon_import_conflicts.delete_many({"external_id": {"$regex": f"^TSTH{tag}"}})


# --- Onboarding: a Sicon id that moves to another customer must not write customer B's site onto customer A's asset
def test_onboarding_moved_equipment_no_cross_tenant_write():
    run_async(_moved())


async def _moved():
    from utils import sicon_links as L, customer_identity as CI, sicon_onboarding as SO
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    co = await L.sage_company_for(OP)
    ca, cb = f"MA{tag}", f"MB{tag}"
    oa, _ = await CI.provision_customer_org({"name": f"TST MoveA {tag}"}, source="test", actor="t", ref=ca, company=co)
    ob, _ = await CI.provision_customer_org({"name": f"TST MoveB {tag}"}, source="test", actor="t", ref=cb, company=co)
    await adb.sites.insert_one({"id": f"TSTsb-{tag}", "organization_id": ob, "name": "B Gym", "sicon_sub_location_id": f"SB{tag}",
                                "sicon_source": await L.connection_company(OP)})
    seid = f"5{tag}"
    runs = []

    async def sync(recs, prev=None):
        rid = f"TSTmv{len(runs)}-{tag}"
        runs.append(rid)
        await adb.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "preview_run_id": prev})
        await SO.run_onboarding(OP, FakeSicon([recs]), {}, rid, prev is not None)
        return rid
    try:
        r1 = [{"siconEquipmentId": seid, "serialNumber": f"MV{tag}", "customerCode": ca, "description": "TST Bike"}]
        await sync(r1, await sync(r1))
        a = await adb.equipment.find_one({"organization_id": oa, "sicon_equipment_id": seid}, {"_id": 0})
        assert a and not a.get("site_id")
        r2 = [{**r1[0], "customerCode": cb, "siconSubLocationDbKey": f"SB{tag}", "locationFull": "B Gym"}]
        await sync(r2, await sync(r2))
        a2 = await adb.equipment.find_one({"id": a["id"]}, {"_id": 0})
        assert a2.get("site_id") != f"TSTsb-{tag}", "customer B's site written onto customer A's asset"
    finally:
        await adb.sicon_external_links.delete_many({"external_id": seid})
        await adb.sicon_import_conflicts.delete_many({"external_id": seid})
        await adb.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await adb.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        await adb.equipment.delete_many({"organization_id": {"$in": [oa, ob]}})
        await adb.sites.delete_many({"organization_id": {"$in": [oa, ob]}})
        await adb.customer_proposed_sites.delete_many({"org_id": {"$in": [oa, ob]}})
        await adb.customer_account_refs.delete_many({"ref": {"$in": [ca, cb]}})
        await adb.onboarding_projects.delete_many({"organization_id": {"$in": [oa, ob]}})
        await adb.crm2_companies.delete_many({"organization_id": OP, "sage_customer_id": {"$regex": tag}})
        await adb.organizations.delete_many({"id": {"$in": [oa, ob]}})


# --- Records without a Sicon id: 'noid:' content key cannot bypass the preview; re-apply must not duplicate
def test_noid_records_respect_preview():
    run_async(_noid())


async def _noid():
    from utils import sicon_links as L, customer_identity as CI, sicon_onboarding as SO
    from utils.database import db as adb
    tag = uuid.uuid4().hex[:6].upper()
    co = await L.sage_company_for(OP)
    cref = f"NI{tag}"
    org, _ = await CI.provision_customer_org({"name": f"TST NoId {tag}"}, source="test", actor="t", ref=cref, company=co)
    runs = []

    async def sync(recs, prev=None):
        rid = f"TSTni{len(runs)}-{tag}"
        runs.append(rid)
        await adb.sicon_sync_runs.insert_one({"id": rid, "organization_id": OP, "entity": "onboarding", "preview_run_id": prev})
        await SO.run_onboarding(OP, FakeSicon([recs]), {}, rid, prev is not None)
        return rid
    try:
        recs = [{"customerCode": cref, "description": f"TST NoId Mat {tag}"}]
        pv = await sync(recs)
        fps = await adb.sicon_preview_fingerprints.count_documents({"run_id": pv, "external_id": {"$regex": "^noid:"}})
        changed = [{**recs[0], "description": f"TST NoId Mat {tag} v2"}]
        await sync(changed, pv)  # not in the approved preview -> review, nothing created
        n_changed = await adb.equipment.count_documents({"organization_id": org})
        await sync(recs, pv)
        await sync(recs, pv)  # same approved preview applied twice
        n_after = await adb.equipment.count_documents({"organization_id": org})
        assert fps == 1 and n_changed == 0, (fps, n_changed)
        # records without a Sicon id are never auto-created (they would duplicate on every sync): held for review
        assert n_after == 0, f"no-id record created: {n_after}"
    finally:
        await adb.sicon_import_conflicts.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        await adb.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        await adb.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        await adb.equipment.delete_many({"organization_id": org})
        await adb.customer_account_refs.delete_many({"ref": cref})
        await adb.onboarding_projects.delete_many({"organization_id": org})
        await adb.crm2_companies.delete_many({"organization_id": OP, "sage_customer_id": {"$regex": tag}})
        await adb.organizations.delete_one({"id": org})
