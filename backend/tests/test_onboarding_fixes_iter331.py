"""Iteration 331 — retest of the iteration 330 fixes: stale-job recovery, async rollback, discard, ref claiming, edit-org ref,
manual similar-name warning, duplicate scoring. Run with -p no:xdist."""
import concurrent.futures as cf
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

from tests.test_sage_sicon_customer_import import API, BASE, H, _analyze, _db, _rollback, _run, _sage_csv  # noqa: F401

R = f"{BASE}/api"
_JOBS: list = []


def _an(*a, **k):
    j = _analyze(*a, **k)
    _JOBS.append(j["id"])
    return j


import pytest  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _drop_jobs():
    yield
    db = _db()
    for c in ("customer_import_rows", "customer_import_undo", "customer_import_preimages"):
        db[c].delete_many({"job_id": {"$in": _JOBS}})
    db.customer_import_jobs.delete_many({"id": {"$in": _JOBS}})


def _ago(sec):
    return (datetime.now(timezone.utc) - timedelta(seconds=sec)).isoformat()


def _fake_job(status, age=600, **extra):
    jid = "TEST_job_" + uuid.uuid4().hex[:10]
    _db().customer_import_jobs.insert_one({"id": jid, "kind": "sage_accounts", "status": status, "filename": "TEST_fake.csv",
                                           "created_at": _ago(age), "heartbeat_at": _ago(age), "preview": {},
                                           "created_by": "TEST", **extra})
    return jid


def _cleanup_orgs(ids):
    db = _db()
    for i in ids:
        db.customer_account_refs.delete_many({"org_id": i})
        db.crm2_contacts.delete_many({"linked_organization_id": i})
        db.crm2_companies.delete_many({"linked_organization_id": i})
        db.onboarding_audit_events.delete_many({"detail.org_id": i})
    db.organizations.delete_many({"id": {"$in": ids}})


# Stale worker recovery (scenario: server restart kills the worker)
def test_stale_jobs_flip_to_recoverable_status(H):
    db = _db()
    ids = {s: _fake_job(s) for s in ("committing", "analysing", "rolling_back")}
    fresh = _fake_job("committing", age=5)
    try:
        exp = {"committing": "interrupted", "analysing": "analysis_failed", "rolling_back": "rollback_interrupted"}
        for s, jid in ids.items():
            j = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
            assert j["status"] == exp[s], (s, j["status"])
            assert "Retry" in (db.customer_import_jobs.find_one({"id": jid}).get("error") or "")
        assert requests.get(f"{API}/jobs/{fresh}", headers=H, timeout=30).json()["status"] == "committing"
    finally:
        db.customer_import_jobs.delete_many({"id": {"$in": list(ids.values()) + [fresh]}})


# A stale job in the jobs LIST / history (no GET on the job) — does it still show as running?
def test_stale_job_in_list_and_history(H):
    db = _db()
    jid = _fake_job("committing")
    try:
        lst = requests.get(f"{API}/jobs", headers=H, timeout=30).json()
        items = lst.get("jobs", lst) if isinstance(lst, dict) else lst
        mine = [x for x in items if x.get("id") == jid]
        print("list status for stale job:", [m.get("status") for m in mine])
        hr = requests.get(f"{API}/history", headers=H, params={"limit": 200}, timeout=30)
        assert hr.status_code == 200, f"history breaks with a stale job present: {hr.status_code} {hr.text[:200]}"
        hs = hr.json()["imports"]
        print("history status for stale job:", [h.get("status") for h in hs if h.get("id") == jid])
    finally:
        db.customer_import_jobs.delete_one({"id": jid})


# Rollback killed mid-way -> 'interrupted' -> commit "Retry" must NOT be accepted (it is an undo, not an import)
def test_interrupted_rollback_is_not_recommittable(H):
    db = _db()
    jid = _fake_job("rolling_back")
    try:
        assert requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()["status"] == "rollback_interrupted"
        r = requests.post(f"{API}/jobs/{jid}/commit", headers=H, timeout=30)
        time.sleep(2)
        st = db.customer_import_jobs.find_one({"id": jid})["status"]
        print("commit on interrupted-rollback:", r.status_code, "->", st)
        assert r.status_code == 409, f"Retry re-commits a half-undone import (status now {st})"
    finally:
        db.customer_import_jobs.delete_one({"id": jid})


# Discard
def test_discard_lifecycle(H):
    db = _db()
    jid = _fake_job("analysed", age=5)
    run = _fake_job("completed", age=5)
    try:
        r = requests.post(f"{API}/jobs/{jid}/discard", headers=H, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "discarded", r.text
        assert db.customer_import_jobs.find_one({"id": jid})["discarded_by"]
        assert requests.post(f"{API}/jobs/{jid}/discard", headers=H, timeout=30).status_code == 409
        assert requests.post(f"{API}/jobs/{jid}/commit", headers=H, timeout=30).status_code == 409
        assert requests.post(f"{API}/jobs/{jid}/approve", headers=H, timeout=30).status_code == 409
        assert requests.post(f"{API}/jobs/{jid}/rollback", headers=H, timeout=30).status_code == 409
        assert requests.post(f"{API}/jobs/{run}/discard", headers=H, timeout=30).status_code == 409
        rv = requests.get(f"{API}/review", headers=H, params={"limit": 200}, timeout=60).json()
        assert not any(jid in str(i) for i in rv["items"])
    finally:
        db.customer_import_jobs.delete_many({"id": {"$in": [jid, run]}})


# Real Sage import -> concurrent double rollback (async): exactly one accepted, orgs removed
def test_async_rollback_concurrent(H):
    db = _db()
    company = "TQ" + uuid.uuid4().hex[:5].upper()
    rows = [{"AccountNumber": f"R{i}{company[-3:]}", "AccountName": f"TEST_Rb Gym {company} {i}", "City": "Leeds"} for i in range(3)]
    j = _an(H, _sage_csv(rows), "rb.csv", "sage_accounts", company)
    j = _run(H, j["id"])
    jid = j["id"]
    created = [o["id"] for o in db.organizations.find({"created_via_job_id": jid}, {"id": 1})]
    try:
        assert j["status"] == "completed", j.get("status")
        assert len(created) == 3
        with cf.ThreadPoolExecutor(2) as ex:
            res = list(ex.map(lambda _: requests.post(f"{API}/jobs/{jid}/rollback", headers=H, timeout=60), range(2)))
        codes = sorted(r.status_code for r in res)
        assert codes == [200, 409], codes
        assert [r.json() for r in res if r.status_code == 200][0] == {"status": "rolling_back"}
        for _ in range(60):
            jj = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
            if jj["status"] != "rolling_back":
                break
            time.sleep(0.5)
        assert jj["status"] == "rolled_back" and jj["rollback"]["removed"] == 3, jj.get("rollback")
        assert db.organizations.count_documents({"id": {"$in": created}}) == 0
        assert db.customer_account_refs.count_documents({"job_id": jid}) == 0
    finally:
        _cleanup_orgs(created)


# A reference left pointing at a deleted organisation must not break new customer creation
def test_leftover_ref_manual_create(H):
    db = _db()
    ref = "LF" + uuid.uuid4().hex[:5].upper()
    dead = "TEST_dead_" + uuid.uuid4().hex[:8]
    db.customer_account_refs.insert_one({"system": "sage", "company": "", "ref": ref, "org_id": dead, "source": "TEST_leftover"})
    oid = None
    try:
        r = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_Leftover {uuid.uuid4().hex[:6]}", "account_ref": ref,
                                                             "confirm_new": True}, timeout=30)
        print("manual with leftover ref:", r.status_code, r.text[:200])
        if r.status_code == 200:
            oid = r.json().get("id")
        assert r.status_code == 200, r.text[:300]
        assert db.organizations.find_one({"id": oid}), "manual create returned an org that does not exist"
    finally:
        db.customer_account_refs.delete_many({"ref": ref})
        if oid:
            _cleanup_orgs([oid])


def test_leftover_ref_master_admin_create(H):
    db = _db()
    ref = "LM" + uuid.uuid4().hex[:5].upper()
    db.customer_account_refs.insert_one({"system": "sage", "company": "", "ref": ref, "org_id": "TEST_dead_x", "source": "TEST_leftover"})
    oid = None
    try:
        r = requests.post(f"{R}/master-admin/organizations", headers=H, timeout=60,
                          json={"name": f"TEST_LeftMA {uuid.uuid4().hex[:6]}", "customer_account_number": ref, "account_type": "lite"})
        print("MA create with leftover ref:", r.status_code, r.text[:200])
        if r.status_code in (200, 201):
            oid = r.json().get("id")
        assert r.status_code in (200, 201), r.text[:300]
    finally:
        db.customer_account_refs.delete_many({"ref": ref})
        if oid:
            _cleanup_orgs([oid])


def test_leftover_ref_sage_import(H):
    db = _db()
    company = "TL" + uuid.uuid4().hex[:5].upper()
    ref = "LS" + uuid.uuid4().hex[:4].upper()
    db.customer_account_refs.insert_one({"system": "sage", "company": company, "ref": ref, "org_id": "TEST_dead_y", "source": "TEST_leftover"})
    jid = None
    try:
        j = _an(H, _sage_csv([{"AccountNumber": ref, "AccountName": f"TEST_LeftSage {company}", "City": "York"}]), "l.csv",
                     "sage_accounts", company)
        jid = j["id"]
        print("preview for leftover ref:", j.get("preview"))
        j = _run(H, jid)
        n = db.organizations.count_documents({"customer_account_number": ref, "sage_company": company}) + \
            db.organizations.count_documents({"created_via_job_id": jid})
        print("job:", j["status"], j.get("results"), "orgs present:", n)
        assert n >= 1, f"import reported {j.get('results')} but no organisation exists for {ref} (attached to a deleted org)"
    finally:
        if jid:
            requests.post(f"{API}/jobs/{jid}/discard", headers=H, timeout=30)
            _rollback(H, jid)
            _cleanup_orgs([o["id"] for o in db.organizations.find({"created_via_job_id": jid}, {"id": 1})])
        db.customer_account_refs.delete_many({"company": company})


# Edit org account number: conflict 409; changing a ref releases the old one
def test_edit_org_ref_conflict_and_release(H):
    db = _db()
    a = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_EdA {uuid.uuid4().hex[:6]}", "confirm_new": True}, timeout=30).json()["id"]
    b = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_EdB {uuid.uuid4().hex[:6]}", "confirm_new": True}, timeout=30).json()["id"]
    r1, r2 = "EA" + uuid.uuid4().hex[:5].upper(), "EB" + uuid.uuid4().hex[:5].upper()
    u = f"{R}/master-admin/organizations/{{}}/details"
    try:
        x = requests.put(u.format(a), headers=H, json={"customer_account_number": r1.lower()}, timeout=30)
        assert x.status_code == 200, x.text
        assert db.organizations.find_one({"id": a})["customer_account_number"] == r1
        assert db.customer_account_refs.find_one({"ref": r1})["org_id"] == a
        assert requests.put(u.format(b), headers=H, json={"customer_account_number": r1}, timeout=30).status_code == 409
        assert requests.put(u.format(a), headers=H, json={"customer_account_number": r2}, timeout=30).status_code == 200
        o = db.organizations.find_one({"id": a})
        print("A after change:", o.get("customer_account_number"), o.get("sage_account_refs"),
              "refs owned:", [d["ref"] for d in db.customer_account_refs.find({"org_id": a})])
        y = requests.put(u.format(b), headers=H, json={"customer_account_number": r1}, timeout=30)
        assert y.status_code == 200, f"old ref {r1} still bound to A after A changed to {r2}: {y.status_code} {y.text[:150]}"
    finally:
        db.customer_account_refs.delete_many({"ref": {"$in": [r1, r2]}})
        _cleanup_orgs([a, b])


# Manual + new account number + similar name -> similar_customers warning
def test_manual_new_ref_returns_similar(H):
    word = "Zq" + uuid.uuid4().hex[:5]
    a = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_{word} Fitness", "confirm_new": True}, timeout=30).json()
    b = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_{word} Fitness", "account_ref": "SM" + uuid.uuid4().hex[:5].upper()},
                      timeout=30)
    ids = [a["id"]] + ([b.json()["id"]] if b.status_code == 200 else [])
    try:
        assert b.status_code == 200, b.text
        assert any(s["id"] == a["id"] for s in b.json()["similar_customers"])
        assert all(s["id"] != b.json()["id"] for s in b.json()["similar_customers"])
    finally:
        _cleanup_orgs(ids)


# duplicate_suggestions scoring: same postcode + shared word suggested; same postcode, unrelated name not
def test_duplicate_scoring_postcode(H):
    w = "Qx" + uuid.uuid4().hex[:5]
    pc = "ZZ9 " + str(uuid.uuid4().int % 9) + "QZ"
    o = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_{w} Leisure Centre", "postcode": pc, "confirm_new": True},
                      timeout=30).json()["id"]
    try:
        d = requests.get(f"{API}/duplicates", headers=H, params={"name": f"{w} Gym", "postcode": pc}, timeout=30).json()
        assert any(s["id"] == o for s in d["suggestions"]), d
        d2 = requests.get(f"{API}/duplicates", headers=H, params={"name": "Unrelated Name", "postcode": pc}, timeout=30).json()
        assert not any(s["id"] == o for s in d2["suggestions"])
        d3 = requests.get(f"{API}/duplicates", headers=H, params={"name": f"TEST_{w} Leisure Centre"}, timeout=30).json()
        assert any(s["id"] == o and s["reason"] == "same name" for s in d3["suggestions"])
    finally:
        _cleanup_orgs([o])


# Scenario 9: worker killed after writing an org but before marking the row done -> stale -> Retry: no duplicate, Undo clean
def test_interrupted_commit_retry_no_duplicate(H):
    db = _db()
    company = "TK" + uuid.uuid4().hex[:5].upper()
    refs = [f"K{i}{company[-4:]}" for i in range(3)]
    rows = [{"AccountNumber": r, "AccountName": f"TEST_Kill Gym {company} {i}", "City": "Hull"} for i, r in enumerate(refs)]
    j = _run(H, _an(H, _sage_csv(rows), "k.csv", "sage_accounts", company)["id"])
    jid = j["id"]
    try:
        assert j["status"] == "completed"
        last = max(r["row"] for r in db.customer_import_rows.find({"job_id": jid, "commit_status": "done"}, {"row": 1}))
        db.customer_import_rows.update_one({"job_id": jid, "row": last}, {"$unset": {"commit_status": "", "result": ""}})
        db.customer_import_jobs.update_one({"id": jid}, {"$set": {"status": "committing", "heartbeat_at": _ago(900)}})
        assert requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()["status"] == "interrupted"
        assert requests.post(f"{API}/jobs/{jid}/commit", headers=H, timeout=30).status_code == 200
        for _ in range(60):
            jj = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
            if jj["status"] != "committing":
                break
            time.sleep(0.5)
        print("after retry:", jj["status"], jj.get("results"))
        assert jj["status"] == "completed"
        for r in refs:
            assert db.customer_account_refs.count_documents({"company": company, "ref": r}) == 1
        n = db.organizations.count_documents({"name": {"$regex": f"^TEST_Kill Gym {company}"}})
        assert n == 3, f"retry produced {n} orgs for 3 accounts"
        rb = _rollback(H, jid)
        print("rollback:", rb)
        left = db.organizations.count_documents({"name": {"$regex": f"^TEST_Kill Gym {company}"}})
        assert left == 0, f"{left} org(s) left after Undo of a retried import"
    finally:
        _cleanup_orgs([o["id"] for o in db.organizations.find({"name": {"$regex": f"^TEST_Kill Gym {company}"}}, {"id": 1})])
        db.customer_account_refs.delete_many({"company": company})


def _drop_pk(pid, org_ids):
    db = _db()
    for o in org_ids:
        db.sites.delete_many({"organization_id": o})
        db.crm_companies.delete_many({"$or": [{"linked_organization_id": o}, {"organization_id": o}]})
        db.equipment.delete_many({"organization_id": o})
    _cleanup_orgs(org_ids)
    db.onboarding_packets.delete_one({"id": pid})


def _packet(H, name, ref=""):
    r = requests.post(f"{R}/onboarding-packets", headers=H, json={"target_tier": "pro"}, timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    org = {"legal_name": name, "trading_name": name, "billing_postcode": "ZZ1 1ZZ", "primary_contact_email": "test.packet@example.com"}
    if ref:
        org["customer_account_number"] = ref
    # owner = an EXISTING user -> provisioning skips user creation and sends no email
    x = requests.put(f"{R}/onboarding-packets/{pid}", headers=H, timeout=30, json={
        "organisation": org, "sites": [{"name": f"{name} Site", "postcode": "ZZ1 1ZZ"}],
        "staff": [{"full_name": "Existing Admin", "email": "admin@pulsefitness.com", "role": "owner"}]})
    assert x.status_code == 200, x.text
    return pid


# Packets: similar name -> 409; ?confirm_new_customer=true -> provisioned
def test_packet_similar_name_then_confirm(H):
    w = "Pk" + uuid.uuid4().hex[:5]
    ex = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_{w} Fitness", "confirm_new": True}, timeout=30).json()["id"]
    pid = _packet(H, f"TEST_{w} Fitness")
    made = []
    try:
        a = requests.post(f"{R}/onboarding-packets/{pid}/provision", headers=H, timeout=60)
        if a.status_code == 200:
            made.append(a.json()["organization_id"])
        assert a.status_code == 409 and "similar name" in str(a.json().get("detail")), a.text
        b = requests.post(f"{R}/onboarding-packets/{pid}/provision", headers=H, params={"confirm_new_customer": "true"}, timeout=60)
        if b.status_code == 200:
            made.append(b.json()["organization_id"])
        assert b.status_code == 200, b.text[:300]
        assert _db().organizations.find_one({"id": made[0]})
    finally:
        _drop_pk(pid, made + [ex])


# Packets with an account number: claimed in customer_account_refs on provision; a second packet with same ref -> 409
def test_packet_claims_ref(H):
    ref = "PR" + uuid.uuid4().hex[:5].upper()
    p1 = _packet(H, f"TEST_PkRef {uuid.uuid4().hex[:6]}", ref)
    p2 = _packet(H, f"TEST_PkRef2 {uuid.uuid4().hex[:6]}", ref)
    made = []
    try:
        a = requests.post(f"{R}/onboarding-packets/{p1}/provision", headers=H, timeout=60)
        assert a.status_code == 200, a.text[:300]
        made.append(a.json()["organization_id"])
        assert _db().customer_account_refs.find_one({"ref": ref})["org_id"] == made[0]
        b = requests.post(f"{R}/onboarding-packets/{p2}/provision", headers=H, params={"confirm_new_customer": "true"}, timeout=60)
        assert b.status_code == 409, b.text[:200]
    finally:
        _drop_pk(p1, made)
        _drop_pk(p2, [])
        _db().customer_account_refs.delete_many({"ref": ref})
