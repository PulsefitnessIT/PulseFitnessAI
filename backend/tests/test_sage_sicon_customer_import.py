"""Sage Customer Accounts + Sicon Customer Contacts import — acceptance tests A–D and key edge cases.

Uses the real supplied templates (tests/fixtures/sage_sicon) and isolated synthetic fixtures under source
company codes starting with TST so live-looking data is never touched. Every committed job is rolled back.
"""
import csv
import io
import os
import time
import uuid

import openpyxl
import pytest
import requests

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sage_sicon")
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
API = f"{BASE}/api/master-admin/customer-import"


_DB = None


def _db():
    """One shared client for the whole test session (a client per call exhausted mongod connections)."""
    global _DB
    if _DB is None:
        from pymongo import MongoClient
        env = dict(line.split("=", 1) for line in open("/app/backend/.env").read().splitlines() if "=" in line)
        _DB = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
    return _DB


def _token(email):
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.auth import create_token
    u = _db().users.find_one({"email": email}, {"id": 1})
    return create_token(u["id"], mfa_verified=True)


@pytest.fixture(scope="module")
def H():
    return {"Authorization": f"Bearer {_token(os.environ.get('MASTER_ADMIN_EMAIL', 'admin@pulsefitness.com'))}"}


def _analyze(H, data: bytes, name: str, expected=None, company=""):
    form = {"source_company": company}
    if expected:
        form["expected"] = expected
    r = requests.post(f"{API}/analyze", headers=H, files={"file": (name, data)}, data=form, timeout=300)
    assert r.status_code == 200, r.text
    return _settle(H, r.json()["id"])


def _settle(H, jid):
    for _ in range(600):
        j = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
        if j["status"] != "analysing":
            return j
        time.sleep(0.5)
    raise AssertionError("analysis did not finish")


def _decide(H, jid, decisions):
    r = requests.post(f"{API}/jobs/{jid}/decisions", headers=H, timeout=120, json={"decisions": decisions})
    assert r.status_code == 200, r.text
    return _settle(H, jid)


def _rows(H, jid, **q):
    return requests.get(f"{API}/jobs/{jid}/rows", headers=H, params={"limit": 500, **q}, timeout=60).json()["rows"]


def _run(H, jid):
    r = requests.post(f"{API}/jobs/{jid}/approve", headers=H, timeout=300)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/jobs/{jid}/commit", headers=H, timeout=60)
    assert r.status_code == 200, r.text
    for _ in range(600):
        j = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
        if j["status"] not in ("committing",):
            return j
        time.sleep(1)
    raise AssertionError("commit did not finish")


def _rollback(H, jid):
    r = requests.post(f"{API}/jobs/{jid}/rollback", headers=H, timeout=120)
    if r.status_code == 409:  # already rolled back (test cleanup)
        return {}
    assert r.status_code == 200, r.text
    for _ in range(600):
        j = requests.get(f"{API}/jobs/{jid}", headers=H, timeout=30).json()
        if j["status"] != "rolling_back":
            return j.get("rollback") or {}
        time.sleep(0.5)
    raise AssertionError("rollback did not finish")


def _xlsx(header, rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(header)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _sage_rows():
    from utils import sage_sicon_import as S
    raw = open(f"{FIX}/SageCustomerAccountsImportTemplate.xls", "rb").read()
    _, sh = S.read_sheets(raw, "x.xls")
    d = S.detect(sh)
    return [r["values"] for r in d["records"] if r["role"] == "example"]


# ---------------------------------------------------------------- Test A
def test_A_unmodified_sage_template(H):
    raw = open(f"{FIX}/SageCustomerAccountsImportTemplate.xls", "rb").read()
    j = _analyze(H, raw, "SageCustomerAccountsImportTemplate.xls", "sage_accounts")
    d = j["detection"]
    assert d["worksheet"] == "CustomerAccounts"
    assert j["file_type"] == "xls" and d["fields_recognised"] == 115 and d["leading_metadata_column"]
    assert d["counts"] == {"metadata": 9, "example": 8, "genuine": 0, "uncertain": 0, "suspected_example": 0}
    s = j["summary"]
    assert s["new_lite_organisations"] == 0 and s["paid_subscriptions_to_activate"] == 0 and s["login_invitations_to_send"] == 0
    done = _run(H, j["id"])
    assert done["status"] == "completed"
    assert _db().organizations.count_documents({"created_via_job_id": j["id"]}) == 0


# ---------------------------------------------------------------- Test C
def test_C_unmodified_sicon_template(H):
    raw = open(f"{FIX}/Customer Contact Import.csv", "rb").read()
    j = _analyze(H, raw, "Customer Contact Import.csv", "sicon_contacts")
    d = j["detection"]
    assert d["fields_recognised"] == 25 and d["counts"]["metadata"] == 5 and d["counts"]["example"] == 3 and d["counts"]["genuine"] == 0
    done = _run(H, j["id"])
    assert done["status"] == "completed"
    assert _db().customer_contact_staging.count_documents({"source_job_id": j["id"]}) == 0


def test_wrong_type_and_permissions(H):
    raw = open(f"{FIX}/Customer Contact Import.csv", "rb").read()
    r = requests.post(f"{API}/analyze", headers=H, files={"file": ("c.csv", raw)}, data={"expected": "sage_accounts"}, timeout=60)
    assert r.status_code == 422
    other = _db().users.find_one({"email": {"$ne": os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.com")},
                                  "is_master_admin": {"$ne": True}, "is_pulse_admin": {"$ne": True},
                                  "role": {"$nin": ["pulse_master_admin"]}}, {"email": 1})
    r = requests.get(f"{API}/jobs", headers={"Authorization": f"Bearer {_token(other['email'])}"}, timeout=30)
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------- Test B
def test_B_production_style_fixture_lite_only_and_idempotent(H):
    from utils.sage_sicon_import import SAGE_FIELDS
    vals = _sage_rows()
    company = "TST" + uuid.uuid4().hex[:5].upper()
    data = _xlsx(SAGE_FIELDS, [[v.get(f, "") for f in SAGE_FIELDS] for v in vals])
    j = _analyze(H, data, "sage_prod_style.xlsx", "sage_accounts", company)
    assert j["detection"]["counts"]["suspected_example"] == 8 and j["detection"]["leading_metadata_column"] is False
    rows = _rows(H, j["id"])
    # Admin explicitly approves all eight as independent eligible test organisations.
    jd = _decide(H, j["id"], [{"row": x["row"], "include": True, "relationship": "separate"} for x in rows])
    assert jd["summary"]["new_lite_organisations"] == 8, jd["preview"]
    done = _run(H, j["id"])
    assert done["status"] == "completed", done
    db = _db()
    orgs = list(db.organizations.find({"created_via_job_id": j["id"]}, {"_id": 0}))
    assert len(orgs) == 8
    for o in orgs:
        assert o["enabled_modules"] == ["operations"] and o["subscription_tier"] == "free" and o["account_type"] == "lite"
        assert o["onboarding_status"] == "pending_activation" and "primary_contact_initial_password" not in o
        assert not any(k in o for k in ("AccountBalance", "CreditLimit", "Memo", "credit_limit", "analysis"))
        assert db.users.count_documents({"organization_id": o["id"]}) == 0
    m = next(o for o in orgs if o["customer_account_number"] == "1042")
    assert m["currency"] == "EUR" and m["address_country_code"]
    assert db.customer_account_internal.find_one({"org_id": m["id"]})["sage_status"]["on_hold"] is True
    contacts = db.crm2_contacts.count_documents({"linked_organization_id": {"$in": [o["id"] for o in orgs]}})
    companies = db.crm2_companies.count_documents({"linked_organization_id": {"$in": [o["id"] for o in orgs]}})
    assert contacts == 8 and companies == 8
    # Reimport the same fixture — nothing new.
    j2 = _analyze(H, data, "sage_prod_style.xlsx", "sage_accounts", company)
    assert j2["previously_imported"]
    rows2 = _rows(H, j2["id"])
    _decide(H, j2["id"], [{"row": x["row"], "include": True} for x in rows2])
    done2 = _run(H, j2["id"])
    assert done2["results"].get("org_created_lite", 0) == 0
    ids = [o["id"] for o in orgs]
    assert db.organizations.count_documents({"sage_company": company}) == 8
    assert db.crm2_contacts.count_documents({"linked_organization_id": {"$in": ids}}) == contacts
    assert db.crm2_companies.count_documents({"linked_organization_id": {"$in": ids}}) == companies
    # Report
    rep = requests.get(f"{API}/jobs/{j['id']}/report.csv", headers=H, timeout=60)
    assert rep.status_code == 200 and "LITE (new)" in rep.text
    for jid in (j2["id"], j["id"]):
        _rollback(H, jid)
    assert db.organizations.count_documents({"sage_company": company}) == 0


# ---------------------------------------------------------------- Test D
SICON_H = ["MetaDataDescription", "CustomerCode", "IsDefaultContact", "Salutation", "FirstName", "MiddleName", "LastName",
           "TelephoneCountryCode", "TelephoneAreaCode", "TelephoneNumber", "IsDefaultTelephoneNumber", "MobileCountryCode",
           "MobileAreaCode", "MobileNumber", "IsDefaultMobileNumber", "FaxCountryCode", "FaxAreaCode", "FaxNumber",
           "IsDefaultFax", "Email", "IsDefaultEmail", "Website", "IsDefaultWebsite", "ContactRole", "ContactRolePreferred"]


def _sicon_csv(rows) -> bytes:
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(SICON_H)
    for r in rows:
        w.writerow([r.get(h, "") for h in SICON_H])
    return ("\ufeff" + b.getvalue()).encode("utf-8")


def _sage_csv(rows) -> bytes:
    from utils.sage_sicon_import import SAGE_FIELDS
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(SAGE_FIELDS)
    for r in rows:
        w.writerow([r.get(f, "") for f in SAGE_FIELDS])
    return b.getvalue().encode("utf-8")


def test_D_combined_sage_and_sicon(H):
    db = _db()
    company = "TST" + uuid.uuid4().hex[:5].upper()
    a, b, ho, br, paid = "0071", "TQ2", "HQ1", "BR1", "PAID1"
    # Existing paid customer with this account reference must keep its products.
    paid_id = str(uuid.uuid4())
    db.organizations.insert_one({"id": paid_id, "name": "TEST Paid Gym", "customer_account_number": paid, "sage_company": company,
                                 "subscription_tier": "pro", "enabled_modules": ["operations", "crm", "memberships", "marketing"],
                                 "account_type": "pro", "status": "active", "city": "Leeds", "created_via": "test"})
    contacts1 = [
        {"CustomerCode": a, "FirstName": "Ann", "LastName": "Lee", "Email": "ann.lee@example.org", "ContactRole": "Manager"},
        {"CustomerCode": a, "FirstName": "Bob", "LastName": "Ray", "Email": "info@example.org"},
        {"CustomerCode": a, "FirstName": "Cat", "LastName": "Fox", "Email": "info@example.org"},
        {"CustomerCode": a, "FirstName": "Dan", "LastName": "Ito", "TelephoneNumber": "0113 496 0000"},
    ]
    # 1. Sicon before Sage → staged
    js = _analyze(H, _sicon_csv(contacts1), "contacts.csv", "sicon_contacts", company)
    assert js["preview"].get("unresolved_contact") == 4
    _run(H, js["id"])
    assert db.customer_contact_staging.count_documents({"account_ref": a, "status": "awaiting_account", "source_company": company}) == 4
    # 2. Sage accounts: new, head office + branch (branch listed first), paid existing, leading zero kept
    sage = [
        {"AccountNumber": br, "AccountName": "TEST Branch Gym", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": ho,
         "AddressLine1": "1 Branch St", "PostCode": "LS1 1AA"},
        {"AccountNumber": a, "AccountName": "TEST Alpha Leisure", "CurrencyISOCode": "GBP", "AddressLine1": "1 A Rd",
         "AddressLine2": "Unit 2", "AddressLine3": "Estate", "AddressLine4": "Area", "City": "Leeds", "PostCode": "LS2 2BB",
         "ContactFirstName": "Ann", "ContactLastName": "Lee", "ContactEmail": "ann.lee@example.org",
         "AnalysisName\\1": "Region", "AnalysisValue\\1": "North", "CreditLimit": "5000", "Memo": "confidential"},
        {"AccountNumber": ho, "AccountName": "TEST Head Office Ltd", "AssociatedOfficeType": "2", "City": "York"},
        {"AccountNumber": paid, "AccountName": "TEST Paid Gym", "Website": "", "AddressLine1": "9 Paid Way"},
        {"AccountNumber": b, "AccountName": "TEST Hidden Co", "ActiveStatus": "1"},
        {"AccountNumber": "TQX", "AccountName": ""},
    ]
    j = _analyze(H, _sage_csv(sage), "sage.csv", "sage_accounts", company)
    p = j["preview"]
    assert p.get("new_customer_organisation") == 3 and not p.get("branch_merged_into_head_office")
    assert p.get("hidden_sage_account") == 1 and p.get("invalid") == 1 and p.get("existing_update_proposed") == 1, p
    done = _run(H, j["id"])
    assert done["status"] == "completed", done
    alpha = db.organizations.find_one({"customer_account_number": a, "sage_company": company})
    assert alpha and alpha["address_line4"] == "Area" and alpha["subscription_tier"] == "free"
    hq = db.organizations.find_one({"customer_account_number": ho, "sage_company": company})
    bro = db.organizations.find_one({"customer_account_number": br, "sage_company": company})
    assert br not in hq["sage_account_refs"] and bro["head_office_link_status"] == "proposed"
    assert db.customer_proposed_sites.find_one({"org_id": bro["id"], "account_ref": br})["status"] == "proposed"
    v = requests.post(f"{API}/branch-links", headers=H, json={"org_ids": [bro["id"]], "decision": "verify"}, timeout=30).json()
    assert v["updated"] == 1
    bro = db.organizations.find_one({"id": bro["id"]})
    assert bro["head_office_link_status"] == "verified" and bro["head_office_org_id"] == hq["id"]
    pg = db.organizations.find_one({"id": paid_id})
    assert pg["subscription_tier"] == "pro" and "crm" in pg["enabled_modules"] and pg["address_line1"] == "9 Paid Way"
    assert "Memo" not in str(alpha) and db.customer_account_internal.find_one({"org_id": alpha["id"]})["fields"]["Memo"] == "confidential"
    # Staged contacts reconciled: Ann merged with Sage primary contact; Bob/Cat separate despite shared info@
    cs = list(db.crm2_contacts.find({"linked_organization_id": alpha["id"]}))
    assert len(cs) == 4, [(c["first_name"], c.get("email")) for c in cs]
    assert db.users.count_documents({"organization_id": {"$in": [alpha["id"], hq["id"]]}}) == 0
    # 3. Sicon again → unchanged, no duplicates
    js2 = _analyze(H, _sicon_csv(contacts1), "contacts.csv", "sicon_contacts", company)
    assert js2["preview"].get("existing_contact_unchanged") == 4, js2["preview"]
    for jid in (j["id"], js["id"]):
        _rollback(H, jid)
    db.organizations.delete_one({"id": paid_id})
    db.customer_account_refs.delete_many({"company": company})
    db.customer_contact_staging.delete_many({"account_ref": a, "source_job_id": js["id"]})


def test_edge_circular_duplicates_and_tamper(H):
    company = "TST" + uuid.uuid4().hex[:5].upper()
    sage = [
        {"AccountNumber": "C1", "AccountName": "TEST C1", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "C2"},
        {"AccountNumber": "C2", "AccountName": "TEST C2", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "C1"},
        {"AccountNumber": "S1", "AccountName": "TEST S1", "AssociatedOfficeType": "1", "AssociatedHeadOfficeAccountNum": "S1"},
        {"AccountNumber": "D1", "AccountName": "TEST D1"},
        {"AccountNumber": "D1", "AccountName": "TEST D1 other"},
        {"AccountNumber": "TOOLONGREF9", "AccountName": "TEST long"},
    ]
    j = _analyze(H, _sage_csv(sage), "edge.csv", "sage_accounts", company)
    p = j["preview"]
    assert p.get("circular_relationship") == 2 and p.get("invalid_relationship") == 1
    assert p.get("conflicting_duplicate") == 2 and p.get("invalid") == 1
    assert requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=60).status_code == 409
    assert requests.post(f"{API}/jobs/{j['id']}/commit", headers=H, timeout=60).status_code == 409
    assert requests.post(f"{API}/jobs/{j['id']}/discard", headers=H, timeout=60).json()["status"] == "discarded"


def test_large_file_over_5000_rows(H):
    company = "TST" + uuid.uuid4().hex[:5].upper()
    rows = [{"AccountNumber": f"L{i:06d}", "AccountName": f"TEST Large {i}"} for i in range(5200)]
    j = _analyze(H, _sage_csv(rows), "large.csv", "sage_accounts", company)
    assert j["detection"]["counts"]["genuine"] == 5200 and j["preview"]["new_customer_organisation"] == 5200
    done = _run(H, j["id"])
    assert done["status"] == "completed" and done["results"]["org_created_lite"] == 5200
    r = _rollback(H, j["id"])
    assert r["removed"] == 5200
