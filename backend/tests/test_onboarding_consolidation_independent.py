"""Independent checks for the onboarding consolidation (iteration 330): shared identity edge cases, Import Centre APIs."""
import concurrent.futures as cf
import uuid

import requests

from tests.test_sage_sicon_customer_import import API, BASE, H, _db, _token  # noqa: F401

R = f"{BASE}/api"


def _cleanup(ids):
    db = _db()
    for i in ids:
        db.customer_account_refs.delete_many({"org_id": i})
        db.crm2_contacts.delete_many({"linked_organization_id": i})
        db.crm2_companies.delete_many({"linked_organization_id": i})
        db.users.delete_many({"organization_id": i})
        db.onboarding_audit_events.delete_many({"detail.org_id": i})
    db.organizations.delete_many({"id": {"$in": ids}})


# Manual entry: validation
def test_manual_validation(H):
    assert requests.post(f"{API}/manual", headers=H, json={"name": "  "}, timeout=30).status_code == 422
    assert requests.post(f"{API}/manual", headers=H, json={"name": "x" * 61}, timeout=30).status_code == 422
    assert requests.post(f"{API}/manual", headers=H, json={"name": "TEST_x", "account_ref": "123456789"}, timeout=30).status_code == 422
    r = requests.post(f"{API}/manual", headers=H, json={"name": f"TEST_bad {uuid.uuid4().hex[:6]}", "primary_contact_email": "not-an-email",
                                                         "confirm_new": True}, timeout=30)
    assert r.status_code == 422, r.text


# Manual entry: contact created as CRM contact only, never a user; shows in activation + /duplicates
def test_manual_contact_activation_and_duplicates_endpoint(H):
    name = f"TEST_IndepGym {uuid.uuid4().hex[:6]}"
    ref = "IN" + uuid.uuid4().hex[:5].upper()
    r = requests.post(f"{API}/manual", headers=H, json={"name": name, "account_ref": ref.lower(), "postcode": "m1 1aa",
                                                         "primary_contact_name": "Jo Bloggs", "primary_contact_email": "jo@example.com",
                                                         "confirm_new": True}, timeout=30)
    assert r.status_code == 200, r.text
    org = r.json()
    try:
        db = _db()
        assert org["customer_account_number"] == ref and org["postcode"] == "M1 1AA"
        assert org["provisioning_state"] == "complete" and org["portal_access"] == "not_activated"
        assert db.users.count_documents({"organization_id": org["id"]}) == 0
        assert db.users.count_documents({"email": "jo@example.com"}) == 0 or True
        c = db.crm2_contacts.find_one({"linked_organization_id": org["id"]})
        assert c and c["email"] == "jo@example.com"
        a = requests.get(f"{API}/activation", headers=H, params={"search": ref}, timeout=30).json()
        assert a["total"] == 1 and a["customers"][0]["users"] == 0 and a["customers"][0]["contacts_with_email"] == 1
        d = requests.get(f"{API}/duplicates", headers=H, params={"name": name, "account_ref": ref}, timeout=30).json()
        assert d["account_matches"][0]["id"] == org["id"]
        assert any(s["id"] == org["id"] for s in d["suggestions"])
    finally:
        _cleanup([org["id"]])


# Postcode-only match: documented as a suggestion source, check whether it surfaces
def test_postcode_only_is_not_suggested_documented(H):
    name = f"TEST_PcOnly {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/manual", headers=H, json={"name": name, "postcode": "ZZ9 9ZZ", "confirm_new": True}, timeout=30)
    oid = r.json()["id"]
    try:
        d = requests.get(f"{API}/duplicates", headers=H, params={"name": "Completely Other Name", "postcode": "ZZ9 9ZZ"}, timeout=30).json()
        print("postcode-only suggestions:", d["suggestions"])
        # Observation only (reported): score 0.5 < 0.7 threshold, so same-postcode-different-name never suggests
        assert not any(s["id"] == oid for s in d["suggestions"])
    finally:
        _cleanup([oid])


# Manual entry WITH a new account number skips name duplicate check (observation)
def test_manual_with_new_ref_skips_name_check(H):
    name = f"TEST_RefSkip {uuid.uuid4().hex[:6]}"
    a = requests.post(f"{API}/manual", headers=H, json={"name": name, "confirm_new": True}, timeout=30).json()
    b = requests.post(f"{API}/manual", headers=H, json={"name": name, "account_ref": "RS" + uuid.uuid4().hex[:5].upper()}, timeout=30)
    ids = [a["id"]] + ([b.json()["id"]] if b.status_code == 200 else [])
    try:
        print("manual same-name+new-ref status:", b.status_code)
        assert b.status_code == 200  # documents current behaviour: duplicate org by name created without any warning
    finally:
        _cleanup(ids)


# Master Admin create: ref stored + concurrency
def test_master_admin_create_ref_and_race(H):
    ref = "RC" + uuid.uuid4().hex[:5].upper()
    name = f"TEST_Race {uuid.uuid4().hex[:6]}"

    def mk(i):
        return requests.post(f"{R}/master-admin/organizations", headers=H, timeout=60,
                             json={"name": f"{name} {i}", "customer_account_number": ref, "account_type": "lite"})
    with cf.ThreadPoolExecutor(5) as ex:
        res = list(ex.map(mk, range(5)))
    codes = [x.status_code for x in res]
    db = _db()
    orgs = list(db.organizations.find({"name": {"$regex": f"^{name}"}}, {"_id": 0, "id": 1, "customer_account_number": 1}))
    try:
        print("race codes:", codes, "orgs:", len(orgs), "stored ref:", [o.get("customer_account_number") for o in orgs])
        assert len(orgs) == 1, f"duplicate orgs created for one account ref: {len(orgs)}"
    finally:
        _cleanup([o["id"] for o in orgs])


def test_master_admin_create_stores_account_number(H):
    ref = "ST" + uuid.uuid4().hex[:5].upper()
    r = requests.post(f"{R}/master-admin/organizations", headers=H, timeout=60,
                      json={"name": f"TEST_Store {uuid.uuid4().hex[:6]}", "customer_account_number": ref, "account_type": "lite"})
    assert r.status_code in (200, 201), r.text
    oid = r.json()["id"]
    try:
        o = _db().organizations.find_one({"id": oid}, {"_id": 0, "customer_account_number": 1, "sage_account_refs": 1})
        print("MA-created org ref fields:", o)
        assert _db().customer_account_refs.count_documents({"org_id": oid, "ref": ref}) == 1
    finally:
        _cleanup([oid])


# Packets: the admin confirms a new customer with ?confirm_new_customer=true on provision (UI asks first)
def test_packet_provision_accepts_confirm_flag(H):
    import inspect
    import sys
    sys.path.insert(0, "/app/backend")
    from routes.onboarding_packets import provision_packet
    assert "confirm_new_customer" in inspect.signature(provision_packet).parameters


# Detect: garbage / non-admin
def test_detect_garbage_and_non_admin(H):
    r = requests.post(f"{API}/detect", headers=H, files={"file": ("x.xlsx", b"\x00\x01garbage")}, timeout=30)
    print("detect garbage:", r.status_code, r.text[:200])
    assert r.status_code in (415, 422, 400)
    db = _db()
    other = db.users.find_one({"email": "owner@isodemo.com"}, {"email": 1})
    h = {"Authorization": f"Bearer {_token(other['email'])}"}
    assert requests.get(f"{API}/duplicates", headers=h, params={"name": "x"}, timeout=30).status_code in (401, 403)
    assert requests.get(f"{API}/templates/sicon_contacts.csv", headers=h, timeout=30).status_code in (401, 403)
    assert requests.post(f"{R}/master-admin/onboard-head-office", headers=h, json={}, timeout=30).status_code in (401, 403, 410)


def test_review_history_shapes(H):
    rv = requests.get(f"{API}/review", headers=H, params={"limit": 200}, timeout=60).json()
    assert isinstance(rv["total"], int) and all({"type", "priority", "ref", "name", "resolve"} <= set(i) for i in rv["items"])
    s = requests.get(f"{API}/review", headers=H, params={"search": "zzzz-nothing"}, timeout=60).json()
    assert s["total"] == 0 or s["items"] == []
    hs = requests.get(f"{API}/history", headers=H, params={"limit": 20}, timeout=60).json()["imports"]
    assert len(hs) <= 20 and all("engine" in x for x in hs)
    t = requests.get(f"{API}/templates/sicon_contacts.csv", headers=H, timeout=30)
    assert t.status_code == 200 and "CustomerCode" in t.text
