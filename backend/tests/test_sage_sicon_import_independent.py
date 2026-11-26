"""Independent checks for Sage/Sicon customer import (iteration 329) — complements test_sage_sicon_customer_import.py.

All synthetic data uses TST* source company codes; every committed job is rolled back and test-inserted orgs removed by id.
"""
import io
import threading
import uuid

import openpyxl
import pytest
import requests

from tests.test_sage_sicon_customer_import import (API, BASE, H, _analyze, _db, _decide, _rows, _sage_csv, _settle,  # noqa: F401
                                                   _token)


def _co():
    return "TST" + uuid.uuid4().hex[:5].upper()


def _approve_commit(H, jid):
    r = requests.post(f"{API}/jobs/{jid}/approve", headers=H, timeout=300)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/jobs/{jid}/commit", headers=H, timeout=60)
    assert r.status_code == 200, r.text
    return _wait_commit(H, jid)


def _wait_commit(H, jid):
    import time
    for _ in range(300):
        j = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
        if j["status"] != "committing":
            return j
        time.sleep(1)
    raise AssertionError("commit did not finish")


def _rollback(H, jid):
    return requests.post(f"{API}/jobs/{jid}/rollback", headers=H, timeout=120)


def _cat(H, jid, ref):
    return next(r for r in _rows(H, jid) if (r.get("record") or {}).get("account_ref") == ref)


# Parsing: XLSX leading zeros via number format '0000'
def test_xlsx_leading_zero_account(H):
    from utils.sage_sicon_import import SAGE_FIELDS
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(SAGE_FIELDS)
    row = ["" for _ in SAGE_FIELDS]
    row[SAGE_FIELDS.index("AccountNumber")] = 42
    row[SAGE_FIELDS.index("AccountName")] = "TEST Zero Pad Gym"
    ws.append(row)
    ws.cell(row=2, column=SAGE_FIELDS.index("AccountNumber") + 1).number_format = "0000"
    b = io.BytesIO()
    wb.save(b)
    j = _analyze(H, b.getvalue(), "zero.xlsx", "sage_accounts", _co())
    assert j["file_type"] == "xlsx"
    refs = [r["record"]["account_ref"] for r in _rows(H, j["id"]) if r.get("record")]
    assert refs == ["0042"], refs


# Parsing: UTF-8 BOM CSV header detected
def test_bom_csv_detected(H):
    data = b"\xef\xbb\xbf" + _sage_csv([{"AccountNumber": "BOM1", "AccountName": "TEST BOM Café"}])
    j = _analyze(H, data, "bom.csv", "sage_accounts", _co())
    assert j["detection"]["format"] == "sage_accounts" and j["detection"]["fields_recognised"] == 115
    r = _rows(H, j["id"])[0]
    assert r["record"]["account_ref"] == "BOM1" and r["record"]["org"]["name"] == "TEST BOM Café"
    assert j["preview"].get("new_customer_organisation") == 1


# Mapping: invalid email kept-not-used, international phone, 4 address lines, analysis/internal isolation, no users/emails
def test_record_mapping_commit_and_isolation(H):
    db = _db()
    co = _co()
    before_emails = db.email_send_events.count_documents({})
    sage = [{"AccountNumber": "MAP1", "AccountName": "TEST Mapping Gym", "AddressLine1": "L1", "AddressLine2": "L2",
             "AddressLine3": "L3", "AddressLine4": "L4", "City": "Paris", "PostCode": "75001", "Country": "FR",
             "ContactFirstName": "Zed", "ContactLastName": "Quinn", "ContactEmail": "zed@@bad",
             "ContactTelephoneCountryCode": "33", "ContactTelephoneAreaCode": "1", "ContactTelephoneSubscriberNumber": "23456789",
             "AnalysisName\\1": "Region", "AnalysisValue\\1": "EU", "CreditLimit": "999", "AccountBalance": "12.50"}]
    j = _analyze(H, _sage_csv(sage), "map.csv", "sage_accounts", co)
    row = _rows(H, j["id"])[0]
    assert any("Invalid email" in w for w in row["outcome"]["warnings"]), row["outcome"]
    assert row["record"]["contact"]["email"] == "" and row["record"]["contact"]["email_source"] == "zed@@bad"
    assert row["record"]["contact"]["telephone"]["display"] == "+33 123456789", row["record"]["contact"]["telephone"]
    assert "analysis" not in row["record"] and "internal" not in row["record"]
    done = _approve_commit(H, j["id"])
    try:
        assert done["status"] == "completed", done
        org = db.organizations.find_one({"customer_account_number": "MAP1", "sage_company": co}, {"_id": 0})
        assert [org[f"address_line{i}"] for i in (1, 2, 3, 4)] == ["L1", "L2", "L3", "L4"]
        s = str(org)
        assert "Region" not in s and "CreditLimit" not in s and "999" not in s and "analysis" not in org
        internal = db.customer_account_internal.find_one({"org_id": org["id"]})
        assert internal["analysis"] == [{"index": 1, "name": "Region", "value": "EU"}]
        assert internal["fields"].get("CreditLimit") == "999"
        c = db.crm2_contacts.find_one({"linked_organization_id": org["id"]})
        assert c and c["email"] == "" and c["last_name"] == "Quinn"
        assert db.users.count_documents({"organization_id": org["id"]}) == 0
        assert db.crm_users.count_documents({"organization_id": org["id"]}) == 0
        assert db.users.count_documents({"email": {"$regex": "zed", "$options": "i"}, "created_at": {"$gte": j["created_at"]}}) == 0
        assert db.customer_proposed_sites.find_one({"org_id": org["id"]})["status"] == "proposed"
        assert db.sites.count_documents({"organization_id": org["id"]}) == 0
        assert db.email_send_events.count_documents({"to": {"$regex": "zed|quinn", "$options": "i"}}) == 0
    finally:
        _rollback(H, j["id"])
    assert db.organizations.count_documents({"sage_company": co}) == 0


# Existing org: blank never overwrites, conflict only with apply_changes, paid modules preserved; rollback restores
def test_existing_org_fill_conflict_apply_and_paid_preserved(H):
    db = _db()
    co = _co()
    oid = str(uuid.uuid4())
    db.organizations.insert_one({"id": oid, "name": "TEST Existing Pro", "customer_account_number": "EX1", "sage_company": co,
                                 "subscription_tier": "pro", "enabled_modules": ["operations", "crm", "memberships", "marketing"],
                                 "website": "old.example.com", "city": "Leeds", "address_line1": "", "status": "active"})
    jobs = []
    try:
        sage = [{"AccountNumber": "EX1", "AccountName": "TEST Existing Pro", "MainWebsite": "", "City": "York",
                 "AddressLine1": "1 New St"}]
        j = _analyze(H, _sage_csv(sage), "ex.csv", "sage_accounts", co)
        jobs.append(j["id"])
        o = _rows(H, j["id"])[0]["outcome"]
        assert o["category"] == "existing_update_proposed" and o["paid_preserved"] is True
        assert o["fills"] == {"address_line1": "1 New St"} and "city" in o["conflicts"] and "website" not in o["conflicts"]
        assert j["summary"]["existing_paid_preserved"] == 1
        _approve_commit(H, j["id"])
        org = db.organizations.find_one({"id": oid})
        assert org["city"] == "Leeds" and org["website"] == "old.example.com" and org["address_line1"] == "1 New St"
        assert org["subscription_tier"] == "pro" and set(org["enabled_modules"]) == {"operations", "crm", "memberships", "marketing"}
        # apply_changes=true
        j2 = _analyze(H, _sage_csv(sage), "ex2.csv", "sage_accounts", co)
        jobs.append(j2["id"])
        row = _rows(H, j2["id"])[0]
        _decide(H, j2["id"], [{"row": row["row"], "apply_changes": True}])
        _approve_commit(H, j2["id"])
        org = db.organizations.find_one({"id": oid})
        assert org["city"] == "York" and org["website"] == "old.example.com" and org["subscription_tier"] == "pro"
        assert "crm" in org["enabled_modules"]
        rb = _rollback(H, j2["id"]).json()
        assert rb["restored"] == 1 and rb["removed"] == 0
        assert db.organizations.find_one({"id": oid})["city"] == "Leeds"
    finally:
        for jid in reversed(jobs):
            _rollback(H, jid)
        db.organizations.delete_one({"id": oid})
        db.customer_account_refs.delete_many({"company": co})
        db.customer_account_internal.delete_many({"org_id": oid})
        db.customer_proposed_sites.delete_many({"org_id": oid})
        db.crm2_contacts.delete_many({"linked_organization_id": oid})
        db.crm2_companies.delete_many({"linked_organization_id": oid})


# Matching: one account ref linked to two orgs -> ambiguous_organisation, approval blocked
def test_ambiguous_organisation_blocks(H):
    db = _db()
    co = _co()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for i, x in enumerate(ids):
        db.organizations.insert_one({"id": x, "name": f"TEST Amb {i}", "customer_account_number": "AMB1", "sage_company": co})
    try:
        j = _analyze(H, _sage_csv([{"AccountNumber": "AMB1", "AccountName": "TEST Amb"}]), "amb.csv", "sage_accounts", co)
        assert j["preview"].get("ambiguous_organisation") == 1, j["preview"]
        assert j["summary"]["blocking"] == 1
        assert requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=60).status_code == 409
        assert requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60).status_code == 409
    finally:
        db.organizations.delete_many({"id": {"$in": ids}})


# Relationships: branch before HO merges; missing HO -> warning + separate; self-reference blocks
def test_relationship_variants(H):
    co = _co()
    sage = [{"AccountNumber": "B1", "AccountName": "TEST B1", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "H1"},
            {"AccountNumber": "H1", "AccountName": "TEST H1", "AssociatedOfficeType": "2"},
            {"AccountNumber": "B2", "AccountName": "TEST B2", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "NOPE9"}]
    j = _analyze(H, _sage_csv(sage), "rel.csv", "sage_accounts", co)
    assert _cat(H, j["id"], "B1")["outcome"]["category"] == "branch_merged_into_head_office"
    b2 = _cat(H, j["id"], "B2")["outcome"]
    assert b2["category"] == "new_customer_organisation" and any("NOPE9" in w for w in b2["warnings"]), b2
    # admin chooses 'separate' for B1
    jd = _decide(H, j["id"], [{"row": _cat(H, j["id"], "B1")["row"], "relationship": "separate"}])
    assert _cat(H, j["id"], "B1")["outcome"]["category"] == "new_customer_organisation"
    assert jd["summary"]["new_lite_organisations"] == 3
    js = _analyze(H, _sage_csv([{"AccountNumber": "SR1", "AccountName": "TEST SR", "AssociatedOfficeType": "1",
                                  "AssociatedHeadOfficeAccountNum": "SR1"}]), "self.csv", "sage_accounts", co)
    assert js["preview"].get("invalid_relationship") == 1
    assert requests.post(f"{API}/jobs/{js['id']}/approve", headers=H, timeout=60).status_code == 409


# Approval lifecycle: decisions withdraw approval; commit requires approval
def test_decision_withdraws_approval(H):
    co = _co()
    j = _analyze(H, _sage_csv([{"AccountNumber": "AP1", "AccountName": "TEST AP1"}]), "ap.csv", "sage_accounts", co)
    assert requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60).status_code == 409
    r = requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=60)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    jd = _decide(H, j["id"], [{"row": _rows(H, j["id"])[0]["row"], "include": False}])
    assert jd["status"] == "analysed" and not jd.get("approval")
    assert requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60).status_code == 409


# Concurrency: two simultaneous commits -> one claims, no duplicate orgs
def test_concurrent_commit(H):
    db = _db()
    co = _co()
    rows = [{"AccountNumber": f"CC{i}", "AccountName": f"TEST CC {i}"} for i in range(30)]
    j = _analyze(H, _sage_csv(rows), "cc.csv", "sage_accounts", co)
    assert requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=120).status_code == 200
    res = []

    def go():
        r = requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60)
        res.append((r.status_code, r.json().get("id") if r.status_code == 200 else None))
    ts = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    codes = sorted(c for c, _ in res)
    assert codes in ([200, 409], [200, 200]), res
    done = _wait_commit(H, j["id"])
    try:
        assert done["status"] == "completed", done
        assert db.organizations.count_documents({"sage_company": co}) == 30
        assert db.customer_account_refs.count_documents({"company": co}) == 30
    finally:
        _rollback(H, j["id"])
    assert db.organizations.count_documents({"sage_company": co}) == 0


# Review queue: proposed site confirm/reject
def test_proposed_site_confirm_reject(H):
    db = _db()
    co = _co()
    sage = [{"AccountNumber": "PS1", "AccountName": "TEST PS1", "AddressLine1": "1 Site Rd", "PostCode": "LS1 1AA"},
            {"AccountNumber": "PS2", "AccountName": "TEST PS2", "AddressLine1": "2 Site Rd", "PostCode": "LS2 2AA"}]
    j = _analyze(H, _sage_csv(sage), "ps.csv", "sage_accounts", co)
    _approve_commit(H, j["id"])
    try:
        sites = [s for s in requests.get(f"{API}/proposed-sites", headers=H, timeout=30).json()["sites"] if s["source_job_id"] == j["id"]]
        assert len(sites) == 2
        a = requests.post(f"{API}/proposed-sites/{sites[0]['id']}/confirm", headers=H, timeout=30)
        assert a.status_code == 200 and a.json()["status"] == "confirmed"
        site = db.sites.find_one({"id": a.json()["site_id"]})
        assert site["address_line1"] in ("1 Site Rd", "2 Site Rd")
        b = requests.post(f"{API}/proposed-sites/{sites[1]['id']}/reject", headers=H, timeout=30)
        assert b.json()["status"] == "rejected"
        assert requests.post(f"{API}/proposed-sites/{sites[1]['id']}/confirm", headers=H, timeout=30).status_code == 404
        sid = a.json()["site_id"]
    finally:
        rb = _rollback(H, j["id"]).json()
    # Rollback should not leave an orphan confirmed site behind
    orphan = db.sites.find_one({"id": sid})
    db.sites.delete_one({"id": sid})
    assert rb["removed"] == 2
    assert orphan is None, "rollback left a confirmed site pointing at a deleted organisation"


# Misc endpoints: overview, staged-contacts, report, initial-passwords dry-run
def test_misc_endpoints(H):
    ov = requests.get(f"{API}/overview", headers=H, timeout=30)
    assert ov.status_code == 200 and {"customer_organisations", "proposed_sites", "unmatched_contacts"} <= set(ov.json())
    assert "groups" in requests.get(f"{API}/staged-contacts", headers=H, timeout=30).json()
    r = requests.post(f"{API}/security/initial-passwords?apply=false", headers=H, timeout=30)
    assert r.status_code == 200 and r.json()["purged"] == 0
    j = _analyze(H, _sage_csv([{"AccountNumber": "RP1", "AccountName": "TEST RP"}]), "rp.csv", "sage_accounts", _co())
    rep = requests.get(f"{API}/jobs/{j['id']}/report.csv", headers=H, timeout=30)
    assert rep.status_code == 200 and "Account reference" in rep.text and "RP1" in rep.text
    rows = requests.get(f"{API}/jobs/{j['id']}/rows", headers=H, params={"search": "rp1"}, timeout=30).json()
    assert rows["total"] == 1
    assert requests.get(f"{API}/jobs/{j['id']}/rows", headers=H, params={"category": "invalid"}, timeout=30).json()["total"] == 0


# Permissions: service-desk (non-pulse-admin) user gets 403
def test_service_desk_403():
    tok = _token("owner@isodemo.com")
    h = {"Authorization": f"Bearer {tok}"}
    for m, p in (("get", "/overview"), ("get", "/jobs"), ("post", "/security/initial-passwords?apply=true")):
        r = getattr(requests, m)(f"{API}{p}", headers=h, timeout=30)
        assert r.status_code == 403, (p, r.status_code)


# Legacy onboarding import: >5000 rows -> 413; customer_orgs commit creates no users / no stored password
def test_legacy_onboarding_import(H):
    db = _db()
    big = "name,customer account number\n" + "".join(f"TEST Big {i},TSTB{i}\n" for i in range(5001))
    r = requests.post(f"{BASE}/api/onboarding/import/analyze", headers=H, data={"import_type": "customer_orgs"},
                      files={"file": ("big.csv", big.encode())}, timeout=120)
    assert r.status_code == 413, r.status_code
    ok = "name\n" + "".join(f"TEST Ok {i}\n" for i in range(5000))
    r = requests.post(f"{BASE}/api/onboarding/import/analyze", headers=H, data={"import_type": "customer_orgs"},
                      files={"file": ("ok.csv", ok.encode())}, timeout=120)
    assert r.status_code == 200 and r.json()["row_count"] == 5000
    acct = "TSTL" + uuid.uuid4().hex[:4].upper()
    email = f"test_legacy_{uuid.uuid4().hex[:6]}@example.com"
    before_emails = db.email_send_events.count_documents({})
    body = {"import_type": "customer_orgs", "send_welcome": True,
            "mapping": {"name": "Name", "primary_contact_email": "Email", "customer_account_number": "Acct"},
            "rows": [{"Name": "TEST Legacy Gym", "Email": email, "Acct": acct}]}
    # Consolidation: legacy customer creation is closed — customers come only through the Import Centre.
    r = requests.post(f"{BASE}/api/onboarding/import/commit", headers=H, json=body, timeout=60)
    assert r.status_code == 410, r.text
    assert db.organizations.count_documents({"customer_account_number": acct}) == 0
    assert db.users.count_documents({"email": email}) == 0 and db.email_send_events.count_documents({}) == before_emails


def test_rollback_completeness_for_contacts(H):
    from tests.test_sage_sicon_customer_import import _sicon_csv
    db = _db()
    co = _co()
    j = _analyze(H, _sage_csv([{"AccountNumber": "RB1", "AccountName": "TEST RB1"}]), "rb.csv", "sage_accounts", co)
    _approve_commit(H, j["id"])
    org = db.organizations.find_one({"customer_account_number": "RB1", "sage_company": co})
    js = _analyze(H, _sicon_csv([{"CustomerCode": "RB1", "FirstName": "Rita", "LastName": "Bell", "Email": "rita@example.org"}]),
                  "c.csv", "sicon_contacts", co)
    assert js["preview"].get("new_business_contact") == 1, js["preview"]
    _approve_commit(H, js["id"])
    assert db.crm2_contacts.count_documents({"linked_organization_id": org["id"]}) == 1
    r = _rollback(H, js["id"])
    left = db.crm2_contacts.count_documents({"linked_organization_id": org["id"], "import_job_ids": js["id"]})
    _rollback(H, j["id"])
    db.crm2_contacts.delete_many({"linked_organization_id": org["id"]})
    assert r.status_code == 200
    assert left == 0, "Undo of a Sicon contacts import left the contacts it created in the CRM"
