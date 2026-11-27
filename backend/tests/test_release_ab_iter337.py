"""Iter 337 — retest of iteration_336 fixes: link never reassigned after conflict/failed/ignored, Sage company identity
(Import Centre default -> uppercase -> Sicon onboarding resolves same customer), onboarding projects tenant 403,
'unscoped' read/write consistency, connection_company ignores disabled platform integration.
Synthetic TEST_/TST data only; everything created is removed by id/tag."""
import os
import uuid

import pytest
import requests

from tests.test_sage_sicon_customer_import import (API, BASE, H, _db, _token, _analyze, _rows, _decide, _run,  # noqa: F401
                                                    _rollback, _sage_csv, _sage_rows)
from tests.test_release_ab_identity import FakeSicon
from tests.shared_loop import run_async

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"


# --- sicon_links: syncs never reassign, whatever the status
@pytest.mark.parametrize("status", ["conflict", "failed", "ignored"])
def test_link_not_reassigned_after_status(status):
    from utils import sicon_links as L
    from utils.database import db as adb
    t = f"TSTRA{uuid.uuid4().hex[:6].upper()}"

    async def go():
        try:
            await L.upsert_link("equipment", t, "equipment", "pa", organization_id="o1", source_company="101")
            if status == "conflict":
                await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101")
            else:
                await adb.sicon_external_links.update_one({"external_id": t}, {"$set": {"sync_status": status}})
            r = await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101")
            r2 = await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101")
            pid = await L.get_pulse_id("equipment", t, "o1", "101")
            # explicit admin decision may reassign
            await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101", reassign=True)
            pid2 = await L.get_pulse_id("equipment", t, "o1", "101")
            n = await adb.sicon_external_links.count_documents({"external_id": t})
            return r, r2, pid, pid2, n
        finally:
            await adb.sicon_external_links.delete_many({"external_id": t})
    r, r2, pid, pid2, n = run_async(go())
    assert r["sync_status"] == "conflict" and r2["sync_status"] == "conflict"
    assert pid == "pa" and pid2 == "pz" and n == 1


def test_same_pulse_id_relinks_and_set_status_then_link():
    """Re-syncing the same id keeps linked; a set_status-only placeholder (no pulse id) can be linked by a sync."""
    from utils import sicon_links as L
    from utils.database import db as adb
    t = f"TSTSS{uuid.uuid4().hex[:6].upper()}"

    async def go():
        try:
            await L.upsert_link("equipment", t, "equipment", "pa", organization_id="o1", source_company="101")
            a = await L.upsert_link("equipment", t, "equipment", "pa", organization_id="o1", source_company="101")
            await adb.sicon_external_links.insert_one({"integration_source": "sicon", "external_entity_type": "case",
                                                       "external_id": t, "source_company": "101", "organization_id": "o1",
                                                       "sync_status": "failed"})
            b = await L.upsert_link("case", t, "svc_case", "c1", organization_id="o1", source_company="101")
            return a, b, await L.get_pulse_id("case", t, "o1", "101")
        finally:
            await adb.sicon_external_links.delete_many({"external_id": t})
    a, b, pid = run_async(go())
    assert a["sync_status"] == "linked" and b["sync_status"] == "linked" and pid == "c1"


def test_unscoped_written_and_read_consistently(monkeypatch):
    """Org with no Sicon config and no company: write stores 'unscoped' and the read finds it."""
    from utils import sicon_links as L

    async def _none(_org):
        return None
    monkeypatch.setattr(L, "connection_company", _none)
    from utils.database import db as adb
    t = f"TSTUN{uuid.uuid4().hex[:6].upper()}"
    org = f"TST-org-{t}"

    async def go():
        try:
            co = await L.connection_company(org)
            await L.upsert_link("equipment", t, "equipment", "pu", organization_id=org)
            d = await adb.sicon_external_links.find_one({"external_id": t}, {"_id": 0})
            await L.set_status("equipment", t, "failed", "x", organization_id=org)
            n = await adb.sicon_external_links.count_documents({"external_id": t})
            return co, d, await L.get_pulse_id("equipment", t, org), n
        finally:
            await adb.sicon_external_links.delete_many({"external_id": t})
    co, d, pid, n = run_async(go())
    if co:
        pytest.skip(f"A Sicon connection company is configured ({co}); unscoped path not reachable")
    assert d["source_company"] == "unscoped" and pid == "pu" and n == 1


def test_connection_company_ignores_disabled_platform_integration():
    from utils import sicon_links as L
    integ = _db().integrations.find_one({"integration_id": "sicon"}, {"_id": 0, "enabled": 1, "credentials": 1}) or {}
    org = f"TST-org-cc-{uuid.uuid4().hex[:6]}"
    co = run_async(L.connection_company(org))
    if integ.get("enabled"):
        pytest.skip("platform sicon integration is enabled in this env")
    env_co = (os.environ.get("SICON_COMPANY_ID") or "").strip()
    # identity is now "<sicon host>#<companyId>" so equal companyIds on different installations never collide
    assert (co is None and not env_co) or (co and co.endswith("#" + env_co)), co


# --- Sage company identity: Import Centre default == Sicon onboarding company
def test_import_config_default_company(H):
    r = requests.get(f"{API}/config", headers=H, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["default_sage_company"] == "Pulse Fitness"
    t = {"Authorization": f"Bearer {_token('owner@isodemo.com')}"}
    assert requests.get(f"{API}/config", headers=t, timeout=30).status_code == 403


def test_file_import_then_sicon_onboarding_resolves_same_customer(H):
    db = _db()
    tag = uuid.uuid4().hex[:6].upper()
    company = requests.get(f"{API}/config", headers=H, timeout=30).json()["default_sage_company"]
    ref = f"T{tag}"
    base = _sage_rows()[0]
    row = {**base, "AccountNumber": ref, "AccountName": f"TEST_ Identity Gym {tag}", "ShortName": f"T{tag}", "PostCode": "ZZ9 9ZZ"}
    j = _analyze(H, _sage_csv([row]), "identity.csv", "sage_accounts", company)
    jid = j["id"]
    runs = []
    try:
        assert j["source_company"] == "PULSE FITNESS", j.get("source_company")
        rows = _rows(H, jid)
        _decide(H, jid, [{"row": x["row"], "include": True, "relationship": "separate"} for x in rows])
        done = _run(H, jid)
        assert done["status"] == "completed", done
        org = db.organizations.find_one({"created_via_job_id": jid}, {"_id": 0, "id": 1, "sage_company": 1,
                                                                      "customer_account_number": 1})
        assert org and org["sage_company"] == "PULSE FITNESS" and org["customer_account_number"] == ref, org

        from utils import sicon_onboarding as SO
        from utils import customer_identity as CI
        from utils.database import db as adb
        recs = [{"siconEquipmentId": f"7{tag}1", "serialNumber": f"SNID{tag}", "model": "T5", "customerCode": ref,
                 "description": "Treadmill"}]
        pv, ap = f"run-pv-{tag}", f"run-ap-{tag}"
        runs += [pv, ap]

        async def go():
            hits = await CI.find_orgs_by_ref(ref, "PULSE FITNESS")
            await adb.sicon_sync_runs.insert_one({"id": pv, "organization_id": OP, "entity": "onboarding", "mode": "preview"})
            await SO.run_onboarding(OP, FakeSicon([recs]), {}, pv, False)
            await adb.sicon_sync_runs.insert_one({"id": ap, "organization_id": OP, "entity": "onboarding", "mode": "apply",
                                                  "preview_run_id": pv})
            r = await SO.run_onboarding(OP, FakeSicon([recs]), {}, ap, True)
            return hits, r
        hits, r = run_async(go())
        assert hits == [org["id"]], hits
        assert r["status"] != "skipped_locked", r
        eq = db.equipment.find_one({"sicon_equipment_id": f"7{tag}1"},
                                   {"_id": 0, "organization_id": 1})
        assert eq and eq["organization_id"] == org["id"], eq
        assert not db.sicon_import_conflicts.find_one({"external_id": f"7{tag}1"})
    finally:
        db.equipment.delete_many({"sicon_equipment_id": f"7{tag}1"})
        db.equipment.delete_many({"serial_number": f"SNID{tag}"})
        db.sicon_external_links.delete_many({"external_id": {"$regex": tag}})
        db.sicon_import_conflicts.delete_many({"external_id": {"$regex": tag}})
        db.sicon_preview_fingerprints.delete_many({"run_id": {"$in": runs}})
        db.sicon_sync_runs.delete_many({"id": {"$in": runs}})
        db.sicon_sync_locks.delete_many({"run_id": {"$in": runs}})
        _rollback(H, jid)
        db.customer_import_rows.delete_many({"job_id": jid})
        db.customer_import_jobs.delete_many({"id": jid})


# --- Onboarding projects: tenant service desk 403, Pulse admin / Pulse staff allowed
@pytest.fixture(scope="module")
def pulse_desk_staff():
    db = _db()
    uid = f"TEST_desk_{uuid.uuid4().hex[:6]}"
    email = f"{uid.lower()}@test.pulse.local"
    db.users.insert_one({"id": uid, "email": email, "full_name": "TEST Desk", "organization_id": OP, "role": "staff",
                         "is_active": True, "is_service_desk": True, "is_pulse_staff": True})
    yield {"id": uid, "email": email}
    db.users.delete_one({"id": uid})


def _any_project_id():
    p = _db().onboarding_projects.find_one({}, {"_id": 0, "id": 1})
    return p["id"] if p else None


def test_tenant_service_desk_blocked_everywhere():
    h = {"Authorization": f"Bearer {_token('owner@isodemo.com')}"}
    assert requests.get(f"{BASE}/api/onboarding/projects", headers=h, timeout=30).status_code == 403
    assert requests.get(f"{BASE}/api/onboarding/customer-types", headers=h, timeout=30).status_code == 403
    pid = _any_project_id()
    if pid:
        assert requests.get(f"{BASE}/api/onboarding/projects/{pid}/estate-progress", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{BASE}/api/onboarding/projects/{pid}", headers=h, timeout=30).status_code in (403, 405)


def test_pulse_admin_and_pulse_staff_allowed(H, pulse_desk_staff):
    assert requests.get(f"{BASE}/api/onboarding/projects", headers=H, timeout=30).status_code == 200
    sh = {"Authorization": f"Bearer {_token(pulse_desk_staff['email'])}"}
    r = requests.get(f"{BASE}/api/onboarding/projects", headers=sh, timeout=30)
    assert r.status_code == 200, r.text
    pid = _any_project_id()
    if pid:
        assert requests.get(f"{BASE}/api/onboarding/projects/{pid}/estate-progress", headers=sh, timeout=30).status_code == 200
