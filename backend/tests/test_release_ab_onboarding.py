"""Release A/B: manual-customer reconciliation, one onboarding project per customer, delegated staff permissions,
confidential Sage record access. Synthetic TST* data only; everything created is removed by id."""
import uuid

import requests

from tests.test_sage_sicon_customer_import import API, BASE, H, _analyze, _db, _decide, _rollback, _run, _sage_csv  # noqa: F401
from tests.test_customer_import_release_a import _co, _org, _purge_orgs, _row


def test_manual_customer_reconciled_by_later_sage_import(H):
    db, co = _db(), _co()
    name = f"TST Manual Gym {uuid.uuid4().hex[:5]}"
    oid = str(uuid.uuid4())
    db.organizations.insert_one({"id": oid, "name": name, "account_type": "lite", "status": "active",
                                 "subscription_tier": "pro", "enabled_modules": ["operations", "pro"]})
    db.sites.insert_one({"id": f"s-{oid}", "organization_id": oid, "name": "Main"})
    jobs = []
    try:
        ref = "MR" + uuid.uuid4().hex[:4].upper()
        j = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": name, "AddressLine4": "Four"}]), "m.csv", "sage_accounts", co)
        jobs.append(j["id"])
        o = _row(H, j["id"], ref)["outcome"]
        assert o["category"] == "possible_existing_customer" and any(c["id"] == oid for c in o["candidates"])
        # blocked until decided
        assert requests.post(f"{API}/jobs/{j['id']}/approve", headers=H, timeout=60).status_code in (400, 409)
        row = _row(H, j["id"], ref)["row"]
        _decide(H, j["id"], [{"row": row, "link_org_id": oid}])
        assert _row(H, j["id"], ref)["outcome"]["category"] == "reconcile_existing_customer"
        assert _run(H, j["id"])["status"] == "completed"
        org = db.organizations.find_one({"id": oid}, {"_id": 0})
        assert org["customer_account_number"] == ref and org["sage_company"] == co
        assert org["subscription_tier"] == "pro" and "pro" in org["enabled_modules"]  # paid plan preserved
        assert db.organizations.count_documents({"customer_account_number": ref}) == 1
        assert db.sites.count_documents({"organization_id": oid}) == 1
        # a second import of the same account now matches the same permanent id
        j2 = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": name}]), "m2.csv", "sage_accounts", co)
        jobs.append(j2["id"])
        assert _row(H, j2["id"], ref)["outcome"].get("org_id") == oid
    finally:
        for jid in jobs:
            requests.post(f"{API}/jobs/{jid}/discard", headers=H, timeout=30)
        _purge_orgs(db, [oid])
        db.onboarding_projects.delete_many({"organization_id": oid})


def test_one_onboarding_project_per_customer_and_undo(H):
    db, co = _db(), _co()
    ref = "OP" + uuid.uuid4().hex[:4].upper()
    j = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": f"TST Project {ref}"}]), "p.csv", "sage_accounts", co)
    assert _run(H, j["id"])["status"] == "completed"
    org = _org(db, ref, co)
    try:
        assert db.onboarding_projects.count_documents({"organization_id": org["id"], "status": {"$ne": "archived"}}) == 1
        j2 = _analyze(H, _sage_csv([{"AccountNumber": ref, "AccountName": f"TST Project {ref}"}]), "p2.csv", "sage_accounts", co)
        assert _run(H, j2["id"])["status"] == "completed"
        assert db.onboarding_projects.count_documents({"organization_id": org["id"], "status": {"$ne": "archived"}}) == 1
        p = db.onboarding_projects.find_one({"organization_id": org["id"]}, {"_id": 0, "id": 1})
        steps = requests.get(f"{BASE}/api/onboarding/projects/{p['id']}/estate-progress", headers=H, timeout=30).json()["steps"]
        st = {s["key"]: s["status"] for s in steps}
        assert st["account_imported"] == "done" and st["portal_activated"] == "todo" and st["contracts_linked"] == "not_required"
        _rollback(H, j2["id"])
        _rollback(H, j["id"])
        assert not db.organizations.find_one({"id": org["id"]})
        assert db.onboarding_projects.count_documents({"organization_id": org["id"], "status": {"$ne": "archived"}}) == 0
    finally:
        _purge_orgs(db, [org["id"]])
        db.onboarding_projects.delete_many({"organization_id": org["id"]})


def test_delegated_staff_permissions(H):
    db = _db()
    op = db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1})
    uid, email = str(uuid.uuid4()), f"tst.delegate.{uuid.uuid4().hex[:6]}@pulsefitness.com"
    db.users.insert_one({"id": uid, "email": email, "full_name": "TST Delegate", "organization_id": op["id"], "role": "manager",
                         "is_active": True})
    other = str(uuid.uuid4())
    db.users.insert_one({"id": other, "email": f"tst.cust.{uuid.uuid4().hex[:6]}@example.com", "organization_id": "tst-cust-org",
                         "role": "owner", "is_active": True})
    try:
        from utils.auth import create_token
        tok = create_token(uid)
        D = {"Authorization": f"Bearer {tok}"}
        assert requests.get(f"{API}/jobs", headers=D, timeout=30).status_code == 403
        r = requests.post(f"{API}/delegates", headers=H, timeout=30, json={"email": email, "permissions": ["imports.review"]})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/jobs", headers=D, timeout=30).status_code == 200
        assert requests.get(f"{API}/review", headers=D, timeout=30).status_code == 200
        assert requests.post(f"{API}/jobs/x/approve", headers=D, timeout=30).status_code == 403
        assert requests.get(f"{API}/orgs/x/sage-internal", headers=D, timeout=30).status_code == 403
        assert requests.get(f"{API}/orgs/x/sage-internal", headers=H, timeout=30).status_code == 200
        bad = requests.post(f"{API}/delegates", headers=H, timeout=30,
                            json={"email": db.users.find_one({"id": other})["email"], "permissions": ["imports.review"]})
        assert bad.status_code == 400  # customers can never be delegated Pulse onboarding access
        assert requests.post(f"{API}/delegates", headers=D, timeout=30, json={"email": email, "permissions": ["imports.commit"]}).status_code == 403
    finally:
        db.users.delete_many({"id": {"$in": [uid, other]}})


def test_transferred_pulse_user_loses_all_pulse_access(H):
    db = _db()
    from utils.auth import create_token
    op = db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1})
    uid, email = str(uuid.uuid4()), f"tst.mover.{uuid.uuid4().hex[:6]}@pulsefitness.com"
    db.users.insert_one({"id": uid, "email": email, "organization_id": op["id"], "role": "manager", "is_active": True,
                         "is_service_desk": True})
    try:
        r = requests.post(f"{API}/delegates", headers=H, timeout=30,
                          json={"email": email, "permissions": ["imports.review", "imports.approve", "sage.confidential"]})
        assert r.status_code == 200
        D = {"Authorization": f"Bearer {create_token(uid)}"}
        assert requests.get(f"{API}/jobs", headers=D, timeout=30).status_code == 200
        assert requests.get(f"{API}/orgs/x/sage-internal", headers=D, timeout=30).status_code == 200
        assert requests.get(f"{BASE}/api/onboarding/projects", headers=D, timeout=30).status_code == 200
        # transferred to a customer organisation: stale flags must not keep any Pulse-only access
        db.users.update_one({"id": uid}, {"$set": {"organization_id": "iso-demo-org"}})
        for url in (f"{API}/jobs", f"{API}/review", f"{API}/orgs/x/sage-internal", f"{BASE}/api/onboarding/projects"):
            assert requests.get(url, headers=D, timeout=30).status_code == 403, url
        hist = requests.get(f"{API}/delegates", headers=H, timeout=30).json()
        assert any(d["email"] == email for d in hist["delegates"])
        assert db.onboarding_permission_history.find_one({"email": email})
    finally:
        db.users.delete_one({"id": uid})
        db.onboarding_permission_history.delete_many({"email": email})


def test_sage_connection_is_pulse_only_and_read_only(H):
    from tests.test_release_ab_iter338 import _crm_session as crm_token
    tenant = {"Authorization": f"Bearer {crm_token('owner@isodemo.com', 'IsoDemo123!')}"}
    for m, path in (("get", "/config"), ("post", "/config"), ("get", "/customers"), ("post", "/sync/customers"),
                    ("post", "/sync/customers-to-sage")):
        r = getattr(requests, m)(f"{BASE}/api/crm/sage200{path}", headers=tenant, json={}, timeout=30)
        assert r.status_code == 403, (path, r.status_code)
    admin = {"Authorization": f"Bearer {crm_token('admin@pulsefitness.com', 'C2s9yJ3YAhydB4d34-Bykg')}"}
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers-to-sage", headers=admin, timeout=30)
    assert r.status_code == 403 and "read-only" in r.text
