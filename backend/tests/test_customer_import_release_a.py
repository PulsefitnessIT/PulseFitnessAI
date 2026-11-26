"""Release A — safe customer import hardening (iteration 332).

Branch default=separate + verify/reject, Review Centre branch items, source-company isolation, undo preview/keep-in-use,
pre-image restore only-if-unchanged, approval snapshot 409, proposed-site confirm/link/force, pending-activation sign-up
block, reveal-password retirement. Synthetic TEST*/TST* data only; everything created is removed by id.
"""
import os
import uuid

import requests

from tests.test_sage_sicon_customer_import import (API, BASE, H, _analyze, _db, _decide, _rows, _rollback,  # noqa: F401
                                                   _run, _sage_csv, _sicon_csv)


def _co():
    return "TST" + uuid.uuid4().hex[:5].upper()


def _row(H, jid, ref):
    return next(r for r in _rows(H, jid) if (r.get("record") or {}).get("account_ref") == ref)


def _org(db, ref, co):
    return db.organizations.find_one({"customer_account_number": ref, "sage_company": co}, {"_id": 0})


def _purge_orgs(db, ids):
    """Remove orgs (and import-side records) that a rollback intentionally kept."""
    for oid in ids:
        db.organizations.delete_one({"id": oid})
        db.customer_account_refs.delete_many({"org_id": oid})
        db.customer_account_internal.delete_many({"org_id": oid})
        db.customer_proposed_sites.delete_many({"org_id": oid})
        db.crm2_contacts.delete_many({"linked_organization_id": oid})
        db.crm2_companies.delete_many({"linked_organization_id": oid})
        db.sites.delete_many({"organization_id": oid})


# Branch relationships: default separate -> proposed link -> verify / reject; non-proposed ignored
def test_branch_default_separate_verify_reject(H):
    db, co = _db(), _co()
    rows = [{"AccountNumber": "HO1", "AccountName": "TEST HO Gym", "AssociatedOfficeType": "2"},
            {"AccountNumber": "BR1", "AccountName": "TEST Branch One", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "HO1"},
            {"AccountNumber": "BR2", "AccountName": "TEST Branch Two", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "HO1"}]
    j = _analyze(H, _sage_csv(rows), "br.csv", "sage_accounts", co)
    for ref in ("BR1", "BR2"):
        o = _row(H, j["id"], ref)["outcome"]
        assert o["category"] == "new_customer_organisation", o
        assert o["relationship"]["mode"] == "separate", o
    done = _run(H, j["id"])
    try:
        assert done["status"] == "completed", done
        ho, b1, b2 = _org(db, "HO1", co), _org(db, "BR1", co), _org(db, "BR2", co)
        assert b1["head_office_link_status"] == "proposed" and b2["head_office_link_status"] == "proposed"
        assert b1["id"] != ho["id"] and not b1.get("head_office_org_id")
        rv = requests.get(f"{API}/review", headers=H, params={"type": "Unverified branch relationship", "limit": 200}, timeout=60).json()
        mine = [i for i in rv["items"] if i.get("branch_org_id") in (b1["id"], b2["id"])]
        assert len(mine) == 2, rv["total"]
        assert all(i["type"] == "Unverified branch relationship" for i in rv["items"])
        assert rv["types"]["Unverified branch relationship"] == rv["total"]
        r = requests.post(f"{API}/branch-links", headers=H, json={"org_ids": [b1["id"]], "decision": "verify"}, timeout=30)
        assert r.status_code == 200 and r.json()["updated"] == 1, r.text
        b1 = _org(db, "BR1", co)
        assert b1["head_office_link_status"] == "verified" and b1["head_office_org_id"] == ho["id"]
        r = requests.post(f"{API}/branch-links", headers=H, json={"org_ids": [b2["id"]], "decision": "reject"}, timeout=30)
        assert r.json()["updated"] == 1
        b2 = _org(db, "BR2", co)
        assert b2["head_office_link_status"] == "rejected" and not b2.get("head_office_org_id")
        # non-proposed (already decided / HO itself) ignored
        r = requests.post(f"{API}/branch-links", headers=H, json={"org_ids": [b1["id"], b2["id"], ho["id"]], "decision": "reject"}, timeout=30)
        assert r.json()["updated"] == 0
        assert _org(db, "BR1", co)["head_office_link_status"] == "verified"
    finally:
        _rollback(H, j["id"])
    assert db.organizations.count_documents({"sage_company": co}) == 0


# Explicit relationship=merge still merges the branch into the head office
def test_branch_explicit_merge(H):
    db, co = _db(), _co()
    rows = [{"AccountNumber": "HO2", "AccountName": "TEST HO Two", "AssociatedOfficeType": "2"},
            {"AccountNumber": "BR3", "AccountName": "TEST Branch Three", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "HO2"}]
    j = _analyze(H, _sage_csv(rows), "brm.csv", "sage_accounts", co)
    row = _row(H, j["id"], "BR3")
    j = _decide(H, j["id"], [{"row": row["row"], "relationship": "merge"}])
    assert _row(H, j["id"], "BR3")["outcome"]["category"] == "branch_merged_into_head_office"
    done = _run(H, j["id"])
    try:
        assert done["status"] == "completed", done
        assert _org(db, "BR3", co) is None
        ho = _org(db, "HO2", co)
        assert "BR3" in (ho.get("sage_branch_refs") or []) and "BR3" in ho["sage_account_refs"]
    finally:
        _rollback(H, j["id"])
    assert db.organizations.count_documents({"sage_company": co}) == 0


# Source-company isolation: same account in two companies -> two orgs; Sicon contacts only reconcile within company
def test_source_company_isolation(H):
    db, a, b = _db(), _co(), _co()
    jobs = []
    try:
        ja = _analyze(H, _sage_csv([{"AccountNumber": "ISO1", "AccountName": "TEST Iso A"}]), "a.csv", "sage_accounts", a)
        jobs.append(ja["id"])
        assert _run(H, ja["id"])["status"] == "completed"
        jb = _analyze(H, _sage_csv([{"AccountNumber": "ISO1", "AccountName": "TEST Iso B"}]), "b.csv", "sage_accounts", b)
        jobs.append(jb["id"])
        assert _row(H, jb["id"], "ISO1")["outcome"]["category"] == "new_customer_organisation"
        assert _run(H, jb["id"])["status"] == "completed"
        oa, ob = _org(db, "ISO1", a), _org(db, "ISO1", b)
        assert oa and ob and oa["id"] != ob["id"]
        # Sicon staged under company A for an account not yet imported in A; B imports it -> must not take A's contacts
        js = _analyze(H, _sicon_csv([{"CustomerCode": "ISO2", "FirstName": "Tess", "LastName": "TESTstage",
                                      "Email": "tess.teststage@example.com"}]), "s.csv", "sicon_contacts", a)
        jobs.append(js["id"])
        assert _row(H, js["id"], "ISO2")["outcome"]["category"] == "unresolved_contact"
        assert _run(H, js["id"])["status"] in ("completed", "completed_with_errors")
        jb2 = _analyze(H, _sage_csv([{"AccountNumber": "ISO2", "AccountName": "TEST Iso2 B"}]), "b2.csv", "sage_accounts", b)
        jobs.append(jb2["id"])
        assert _run(H, jb2["id"])["status"] == "completed"
        ob2 = _org(db, "ISO2", b)
        assert db.crm2_contacts.count_documents({"linked_organization_id": ob2["id"], "last_name": "TESTstage"}) == 0
        # Site invoice refs only trusted for default company ''
        sid, toid = str(uuid.uuid4()), str(uuid.uuid4())
        ref = "SIT" + uuid.uuid4().hex[:4].upper()
        db.organizations.insert_one({"id": toid, "name": "TEST Site Ref Org", "status": "active"})
        db.sites.insert_one({"id": sid, "organization_id": toid, "name": "TEST site", "invoice_customer_ref": ref})
        try:
            jc = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": "TEST Site Ref Org"}]), "c.csv", "sage_accounts", a)
            assert _row(H, jc["id"], ref)["outcome"]["category"] == "new_customer_organisation"
            jd = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": "TEST Site Ref Org"}]), "d.csv", "sage_accounts", "")
            od = _row(H, jd["id"], ref)["outcome"]
            assert od["org_id"] == toid, od
            for x in (jc, jd):
                requests.post(f"{API}/jobs/{x['id']}/discard", headers=H, timeout=30)
        finally:
            db.sites.delete_one({"id": sid})
            db.organizations.delete_one({"id": toid})
    finally:
        for jid in reversed(jobs):
            _rollback(H, jid)
        db.customer_contact_staging.delete_many({"source_job_id": {"$in": jobs}})
    assert db.organizations.count_documents({"sage_company": {"$in": [a, b]}}) == 0


# Undo preview + rollback keeps in-use orgs; restores pre-import values only if unchanged
def test_undo_preview_keep_in_use_and_preimage(H):
    db, co = _db(), _co()
    exid = str(uuid.uuid4())
    db.organizations.insert_one({"id": exid, "name": "TEST Existing Undo", "customer_account_number": "UEX", "sage_company": co,
                                 "city": "", "address_line1": "", "status": "active", "subscription_tier": "none",
                                 "enabled_modules": ["operations"]})
    rows = [{"AccountNumber": "UEX", "AccountName": "TEST Existing Undo", "City": "York", "AddressLine1": "1 Import St"}] + \
           [{"AccountNumber": f"U{i}", "AccountName": f"TEST Undo {i}"} for i in range(1, 4)]
    j = _analyze(H, _sage_csv(rows), "undo.csv", "sage_accounts", co)
    eq, inv = str(uuid.uuid4()), str(uuid.uuid4())
    keep_ids = []
    try:
        assert _run(H, j["id"])["status"] == "completed"
        ex = db.organizations.find_one({"id": exid})
        assert ex["city"] == "York" and ex["address_line1"] == "1 Import St"
        db.organizations.update_one({"id": exid}, {"$set": {"city": "Bath"}})  # later legitimate edit
        o1, o2 = _org(db, "U1", co), _org(db, "U2", co)
        keep_ids = [o1["id"], o2["id"]]
        db.equipment.insert_one({"id": eq, "organization_id": o1["id"], "name": "TEST treadmill"})
        db.invites.insert_one({"id": inv, "organization_id": o2["id"], "email": "test_undo_inv@example.com", "status": "pending"})
        p = requests.get(f"{API}/jobs/{j['id']}/undo-preview", headers=H, timeout=30)
        assert p.status_code == 200, p.text
        p = p.json()
        assert p["customers_to_remove"] == 1, p
        kept = {k["org_id"]: k["in_use"] for k in p["customers_kept_in_use"]}
        assert kept.get(o1["id"]) == {"equipment": 1} and kept.get(o2["id"]) == {"invitations": 1}, kept
        assert p["changes_to_revert"] > 0
        rb = _rollback(H, j["id"])
        assert rb.get("removed") == 1 and rb.get("kept") == 2, rb
        assert _org(db, "U3", co) is None
        assert _org(db, "U1", co) and _org(db, "U2", co)
        ex = db.organizations.find_one({"id": exid})
        assert ex["city"] == "Bath", ex.get("city")  # edit kept
        assert ex["address_line1"] == "", ex.get("address_line1")  # untouched import value restored
    finally:
        _rollback(H, j["id"])
        db.equipment.delete_one({"id": eq})
        db.invites.delete_one({"id": inv})
        _purge_orgs(db, keep_ids + [exid])


# Approval snapshot: a matched org changing after approval -> commit 409
def test_commit_409_when_changed_after_approval(H):
    db, co = _db(), _co()
    oid = str(uuid.uuid4())
    db.organizations.insert_one({"id": oid, "name": "TEST Snap Org", "customer_account_number": "SNP1", "sage_company": co,
                                 "website": "", "status": "active"})
    try:
        j = _analyze(H, _sage_csv([{"AccountNumber": "SNP1", "AccountName": "TEST Snap Org", "MainWebsite": "new.example.com"}]),
                     "snap.csv", "sage_accounts", co)
        assert _row(H, j["id"], "SNP1")["outcome"]["fills"].get("website") == "new.example.com"
        r = requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=120)
        assert r.status_code == 200, r.text
        db.organizations.update_one({"id": oid}, {"$set": {"website": "other.example.com"}})
        r = requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60)
        assert r.status_code == 409 and "changed after approval" in r.text, r.text
        assert db.organizations.find_one({"id": oid})["website"] == "other.example.com"
        requests.post(f"{API}/jobs/{j['id']}/discard", headers=H, timeout=30)
    finally:
        _purge_orgs(db, [oid])


# Proposed sites: double confirm 409, postcode twin 409, force, link own vs other org's site, address_line4 kept
def test_proposed_sites_confirm_link_force(H):
    db, co = _db(), _co()
    rows = [{"AccountNumber": f"PS{i}", "AccountName": f"TEST PS {i}", "AddressLine1": f"{i} Gym Rd", "AddressLine4": "Line Four",
             "City": "Leeds", "PostCode": f"LS{i} 1AA"} for i in range(1, 4)]
    j = _analyze(H, _sage_csv(rows), "ps.csv", "sage_accounts", co)
    s2, s3, other_site, other_org = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    ids = []
    try:
        assert _run(H, j["id"])["status"] == "completed"
        o = {i: _org(db, f"PS{i}", co) for i in (1, 2, 3)}
        ids = [x["id"] for x in o.values()]
        p = {i: db.customer_proposed_sites.find_one({"org_id": o[i]["id"]}) for i in (1, 2, 3)}
        r = requests.post(f"{API}/proposed-sites/{p[1]['id']}/confirm", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        site = db.sites.find_one({"id": r.json()["site_id"]})
        assert site["address_line4"] == "Line Four" and site["organization_id"] == o[1]["id"]
        r = requests.post(f"{API}/proposed-sites/{p[1]['id']}/confirm", headers=H, timeout=30)
        assert r.status_code == 409
        # twin postcode on PS2 and PS3 orgs (manually created sites)
        db.sites.insert_one({"id": s2, "organization_id": o[2]["id"], "name": "TEST existing 2", "postcode": "ls21aa"})
        db.sites.insert_one({"id": s3, "organization_id": o[3]["id"], "name": "TEST existing 3", "postcode": "LS3 1AA"})
        db.organizations.insert_one({"id": other_org, "name": "TEST Other Org"})
        db.sites.insert_one({"id": other_site, "organization_id": other_org, "name": "TEST other site", "postcode": "LS2 1AA"})
        r = requests.post(f"{API}/proposed-sites/{p[2]['id']}/confirm", headers=H, timeout=30)
        assert r.status_code == 409, r.text
        assert [s["id"] for s in r.json()["detail"]["existing_sites"]] == [s2]
        r = requests.post(f"{API}/proposed-sites/{p[2]['id']}/link", headers=H, params={"link_site_id": other_site}, timeout=30)
        assert r.status_code == 422, r.text
        r = requests.post(f"{API}/proposed-sites/{p[2]['id']}/link", headers=H, params={"link_site_id": s2}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "linked", r.text
        assert db.sites.find_one({"id": s2})["invoice_customer_ref"] == "PS2"
        r = requests.post(f"{API}/proposed-sites/{p[3]['id']}/confirm", headers=H, params={"force": "true"}, timeout=30)
        assert r.status_code == 200, r.text
        assert db.sites.count_documents({"organization_id": o[3]["id"]}) == 2
    finally:
        _rollback(H, j["id"])
        db.sites.delete_many({"id": {"$in": [s2, s3, other_site]}})
        db.organizations.delete_one({"id": other_org})
        _purge_orgs(db, ids)


# Company-code sign-up: blocked for imported pending-activation orgs (no invite); active org still works
def test_company_code_signup_block_and_regression(H):
    db, co = _db(), _co()
    hdr = {"x-ratelimit-bypass": open("/app/backend/.env").read().split("RATE_LIMIT_BYPASS_SECRET=")[1].split()[0].strip().strip('"')}
    j = _analyze(H, _sage_csv([{"AccountNumber": "SGN1", "AccountName": "TEST Signup Lite"}]), "sg.csv", "sage_accounts", co)
    act = str(uuid.uuid4())
    code = "T" + uuid.uuid4().hex[:7].upper()
    created_users = []
    try:
        assert _run(H, j["id"])["status"] == "completed"
        org = _org(db, "SGN1", co)
        assert org["onboarding_status"] == "pending_activation" and org.get("company_code")
        email = f"test_sgn_{uuid.uuid4().hex[:6]}@example.com"
        pw = "Zq!" + uuid.uuid4().hex + "Aa9"
        r = requests.post(f"{BASE}/api/auth/register", headers=hdr, timeout=30,
                          json={"email": email, "password": pw, "full_name": "TEST Signup", "company_code": org["company_code"]})
        assert r.status_code == 403, r.text
        assert db.users.count_documents({"email": email}) == 0
        db.organizations.insert_one({"id": act, "name": "TEST Active Code Org", "company_code": code, "status": "active",
                                     "subscription_tier": "pro"})
        email2 = f"test_sgn_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE}/api/auth/register", headers=hdr, timeout=30,
                          json={"email": email2, "password": pw, "full_name": "TEST Signup Two", "company_code": code})
        assert r.status_code in (200, 201), r.text
        u = db.users.find_one({"email": email2})
        created_users.append(email2)
        assert u and u["organization_id"] == act and u["role"] == "staff"
    finally:
        for e in created_users:
            db.users.delete_many({"email": e})
        db.organizations.delete_one({"id": act})
        _rollback(H, j["id"])


# Reveal password retired + no plaintext stored on create / reset
def test_reveal_password_retired(H):
    db = _db()
    email = f"test_pc_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE}/api/master-admin/organizations", headers=H, timeout=60,
                      json={"name": f"TEST Reveal {uuid.uuid4().hex[:4]}", "confirm_new": True, "enabled_modules": ["operations"],
                            "primary_contact_name": "TEST Contact", "primary_contact_email": email})
    assert r.status_code in (200, 201), r.text
    org = db.organizations.find_one({"primary_contact_email": email}, {"_id": 0})
    try:
        assert org and "primary_contact_initial_password" not in org
        r = requests.get(f"{BASE}/api/master-admin/organizations/{org['id']}/primary-contact-credentials", headers=H, timeout=30)
        assert r.status_code == 200 and r.json()["initial_password"] is None and r.json()["available"] is False
        r = requests.post(f"{BASE}/api/master-admin/organizations/{org['id']}/send-primary-contact-credentials", headers=H, timeout=30)
        assert r.status_code == 410, r.text
        u = db.users.find_one({"email": email}, {"_id": 0, "id": 1}) or db.crm_users.find_one({"email": email}, {"_id": 0, "id": 1})
        assert u, "primary contact user not provisioned"
        r = requests.put(f"{BASE}/api/master-admin/users/{u['id']}/reset-password", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        assert "primary_contact_initial_password" not in db.organizations.find_one({"id": org["id"]}, {"_id": 0})
    finally:
        if org:
            db.organizations.delete_one({"id": org["id"]})
        db.users.delete_many({"email": email})
        db.crm_users.delete_many({"email": email})
