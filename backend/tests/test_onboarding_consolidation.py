"""Onboarding consolidation: shared customer identity, closed legacy customer-creation routes, Import Centre APIs."""
import io
import uuid

import requests

from tests.test_sage_sicon_customer_import import API, BASE, FIX, H, _analyze, _db, _run, _sage_csv, _token  # noqa: F401

R = f"{BASE}/api"


def test_legacy_customer_creation_routes_are_closed(H):
    assert requests.post(f"{R}/master-admin/onboard-head-office", headers=H, json={}, timeout=30).status_code == 410
    assert requests.post(f"{R}/master-admin/onboard-pulse-site", headers=H, json={}, timeout=30).status_code == 410
    r = requests.post(f"{R}/onboarding/import/commit", headers=H, timeout=30,
                      json={"import_type": "customer_orgs", "mapping": {}, "rows": [{"name": "X"}]})
    assert r.status_code == 410, r.text
    types = requests.get(f"{R}/onboarding/import/types", headers=H, timeout=30).json()["types"]
    assert not any(t["creates_tenant"] for t in types)


def test_manual_customer_duplicate_check_and_lite(H):
    db = _db()
    name = f"TEST Manual Gym {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/manual", headers=H, json={"name": name, "postcode": "LS1 4AB"}, timeout=30)
    assert r.status_code == 200, r.text
    org = r.json()
    assert org["account_type"] == "lite" and org["enabled_modules"] == ["operations"] and org["onboarding_status"] == "pending_activation"
    assert db.users.count_documents({"organization_id": org["id"]}) == 0
    # Same name again → suggestions, nothing created until confirmed
    r2 = requests.post(f"{API}/manual", headers=H, json={"name": name, "postcode": "LS1 4AB"}, timeout=30)
    assert r2.status_code == 409 and r2.json()["detail"]["suggestions"][0]["id"] == org["id"]
    r3 = requests.post(f"{API}/manual", headers=H, json={"name": name, "confirm_new": True}, timeout=30)
    assert r3.status_code == 200 and r3.json()["id"] != org["id"]
    # Account number already owned → refused
    ref = "M" + uuid.uuid4().hex[:6].upper()
    r4 = requests.post(f"{API}/manual", headers=H, json={"name": f"{name} A", "account_ref": ref, "confirm_new": True}, timeout=30)
    assert r4.status_code == 200
    r5 = requests.post(f"{API}/manual", headers=H, json={"name": "Anything", "account_ref": ref}, timeout=30)
    assert r5.status_code == 409
    # Sage import of the same account number recognises the manual customer (no duplicate)
    j = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": f"{name} A"}]), "s.csv", "sage_accounts")
    assert j["preview"].get("existing_unchanged") == 1 or j["preview"].get("existing_update_proposed") == 1, j["preview"]
    requests.post(f"{API}/jobs/{j['id']}/discard", headers=H, timeout=60)
    ids = [org["id"], r3.json()["id"], r4.json()["id"]]
    for i in ids:
        db.customer_account_refs.delete_many({"org_id": i})
        db.crm2_contacts.delete_many({"linked_organization_id": i})
        db.crm2_companies.delete_many({"linked_organization_id": i})
    db.organizations.delete_many({"id": {"$in": ids}})


def test_master_admin_create_uses_shared_identity(H):
    db = _db()
    name = f"TEST MA Org {uuid.uuid4().hex[:6]}"
    ref = "MA" + uuid.uuid4().hex[:5].upper()
    r = requests.post(f"{R}/master-admin/organizations", headers=H, json={"name": name, "customer_account_number": ref,
                                                                          "account_type": "lite"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    oid = r.json()["id"]
    r2 = requests.post(f"{R}/master-admin/organizations", headers=H, json={"name": "Other", "customer_account_number": ref}, timeout=30)
    assert r2.status_code == 409
    r3 = requests.post(f"{R}/master-admin/organizations", headers=H, json={"name": name, "account_type": "lite"}, timeout=30)
    assert r3.status_code == 409 and r3.json()["detail"]["suggestions"]
    db.customer_account_refs.delete_many({"org_id": oid})
    db.users.delete_many({"organization_id": oid})
    db.organizations.delete_one({"id": oid})


def test_detect_review_history_activation_templates(H):
    raw = open(f"{FIX}/SageCustomerAccountsImportTemplate.xls", "rb").read()
    d = requests.post(f"{API}/detect", headers=H, files={"file": ("a.xls", raw)}, timeout=60).json()
    assert d["type"] == "sage_accounts" and d["confidence"] == "certain"
    eq = b"Sicon Customer Ref,Location Description,Description,Make,Model,Serial Number\nA1,Gym,Bike,X,Y,S1\n"
    assert requests.post(f"{API}/detect", headers=H, files={"file": ("e.csv", eq)}, timeout=60).json()["type"] == "equipment"
    unk = b"foo,bar\n1,2\n"
    assert requests.post(f"{API}/detect", headers=H, files={"file": ("u.csv", unk)}, timeout=60).json()["confidence"] == "needs_choice"
    rv = requests.get(f"{API}/review", headers=H, params={"limit": 5}, timeout=60)
    assert rv.status_code == 200 and "types" in rv.json()
    hs = requests.get(f"{API}/history", headers=H, timeout=60)
    assert hs.status_code == 200 and isinstance(hs.json()["imports"], list)
    assert requests.get(f"{API}/activation", headers=H, timeout=60).status_code == 200
    t = requests.get(f"{API}/templates/sage_accounts.csv", headers=H, timeout=30)
    assert t.status_code == 200 and t.text.count(",") == 114


def test_afs_estate_shared_customer_identity():
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from utils import customer_identity as CI

    async def go():
        name = f"TEST Estate {uuid.uuid4().hex[:6]}"
        a, created = await CI.provision_customer_org({"name": name}, source="test", actor="t", confirmed_new=True)
        assert created
        try:
            await CI.provision_customer_org({"name": name}, source="test", actor="t")
            raise AssertionError("expected duplicate suggestion")
        except CI.DuplicateSuspected as e:
            assert e.suggestions[0]["id"] == a
        ref = "E" + uuid.uuid4().hex[:6].upper()
        b, c1 = await CI.provision_customer_org({"name": name + " B"}, source="test", actor="t", ref=ref)
        b2, c2 = await CI.provision_customer_org({"name": "Different name"}, source="test", actor="t", ref=ref)
        assert c1 and not c2 and b == b2
        from utils.database import db
        await db.customer_account_refs.delete_many({"org_id": {"$in": [a, b]}})
        await db.organizations.delete_many({"id": {"$in": [a, b]}})
    asyncio.run(go())


def test_non_admin_cannot_use_import_centre():
    db = _db()
    other = db.users.find_one({"email": "owner@isodemo.com"}, {"email": 1}) or db.users.find_one(
        {"is_master_admin": {"$ne": True}, "role": {"$nin": ["pulse_master_admin"]}}, {"email": 1})
    h = {"Authorization": f"Bearer {_token(other['email'])}"}
    for path in ("/review", "/history", "/activation", "/overview"):
        assert requests.get(f"{API}{path}", headers=h, timeout=30).status_code in (401, 403)
    assert requests.post(f"{API}/manual", headers=h, json={"name": "x"}, timeout=30).status_code in (401, 403)
    assert requests.post(f"{API}/detect", headers=h, files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"))}, timeout=30).status_code in (401, 403)
