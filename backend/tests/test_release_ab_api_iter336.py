"""Iter 336 — Release A/B HTTP-level checks: Sage 200 pull guard rails, Sicon link migration (dry run / apply / audit),
delegated Pulse staff permissions per action, confidential Sage record, backfill dry run, Review Centre item types,
estate-progress. Synthetic TEST_/TST data only; everything created is removed by id."""
import uuid

import pytest
import requests

from tests.test_sage_sicon_customer_import import API, BASE, H, _db, _token  # noqa: F401

OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"


@pytest.fixture(scope="module")
def crm_admin(H):
    r = requests.post(f"{BASE}/api/crm/auth/cross-login", headers=H, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def staff():
    """TEST_ Pulse staff user in the operator org (deleted afterwards)."""
    db = _db()
    uid = f"TEST_staff_{uuid.uuid4().hex[:6]}"
    email = f"{uid.lower()}@test.pulse.local"
    db.users.insert_one({"id": uid, "email": email, "full_name": "TEST Staff", "organization_id": OP, "role": "staff",
                         "is_active": True})
    yield {"id": uid, "email": email}
    db.users.delete_one({"id": uid})
    db.onboarding_audit_events.delete_many({"action": "onboarding_permissions_set", "detail.email": email})


# --- Sage 200 pull: Pulse admins only, company required
def test_sage_pull_requires_pulse_admin():
    r = requests.post(f"{BASE}/api/crm/auth/login", json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}, timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers?source_company=X", headers=h, timeout=30)
    assert r.status_code == 403, r.text


def test_sage_pull_requires_company(crm_admin):
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers", headers=crm_admin, timeout=30)
    assert r.status_code == 400 and "company" in r.text.lower(), r.text
    # the company now comes from the Sage connection itself; a typed label can never override it
    r = requests.post(f"{BASE}/api/crm/sage200/sync/customers?source_company=TSTX", headers=crm_admin, timeout=60)
    assert r.status_code in (400, 409, 503), r.text


# --- Sicon link migration
def test_link_migration_dry_run_apply_and_audit(H):
    db = _db()
    ext = f"TSTMIG{uuid.uuid4().hex[:6].upper()}"
    db.sicon_external_links.insert_one({"integration_source": "sicon", "external_entity_type": "equipment", "external_id": ext,
                                        "organization_id": OP, "pulse_entity_type": "equipment", "pulse_entity_id": "legacy-x",
                                        "sync_status": "linked"})
    try:
        d = requests.get(f"{API}/sicon-links/migration", headers=H, timeout=30)
        assert d.status_code == 200, d.text
        d = d.json()
        mine = [x for x in d["sample"] if x["external_id"] == ext] + [x for x in d["review"] if x["external_id"] == ext]
        assert len(mine) == 1, d
        # dry run wrote nothing
        assert "source_company" not in db.sicon_external_links.find_one({"external_id": ext})
        others = [x for x in d["sample"] + d["review"] if x["external_id"] != ext]
        if others:
            pytest.skip(f"Other legacy links exist ({len(others)}) — not applying migration on real data")
        r = requests.post(f"{API}/sicon-links/migration/apply", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        link = db.sicon_external_links.find_one({"external_id": ext}, {"_id": 0})
        assert link.get("source_company") or link.get("migration_status") == "needs_review"
        ev = db.onboarding_audit_events.find_one({"action": "sicon_links_scoped"}, sort=[("at", -1)])
        assert ev and ev["actor_email"] == "admin@pulsefitness.com"
        # idempotent: second dry run no longer lists it as to-scope
        d2 = requests.get(f"{API}/sicon-links/migration", headers=H, timeout=30).json()
        assert not any(x["external_id"] == ext for x in d2["sample"])
    finally:
        db.sicon_external_links.delete_many({"external_id": ext})


# --- Delegated permissions
def test_delegate_customer_user_rejected(H):
    r = requests.post(f"{API}/delegates", headers=H, json={"email": "owner@isodemo.com", "permissions": ["imports.review"]}, timeout=30)
    assert r.status_code == 400, r.text
    assert not (_db().users.find_one({"email": "owner@isodemo.com"}, {"onboarding_permissions": 1}) or {}).get("onboarding_permissions")


def test_delegate_unknown_permission_and_missing_user(H, staff):
    r = requests.post(f"{API}/delegates", headers=H, json={"email": staff["email"], "permissions": ["imports.everything"]}, timeout=30)
    assert r.status_code == 400
    r = requests.post(f"{API}/delegates", headers=H, json={"email": "nobody-tst@none.local", "permissions": []}, timeout=30)
    assert r.status_code == 404


def test_delegate_review_permission_enforced_per_action(H, staff):
    sh = {"Authorization": f"Bearer {_token(staff['email'])}"}
    # before delegation: nothing
    assert requests.get(f"{API}/jobs", headers=sh, timeout=30).status_code == 403
    r = requests.post(f"{API}/delegates", headers=H, json={"email": staff["email"], "permissions": ["imports.review"]}, timeout=30)
    assert r.status_code == 200 and r.json()["permissions"] == ["imports.review"], r.text
    lst = requests.get(f"{API}/delegates", headers=H, timeout=30).json()
    assert any(d["email"] == staff["email"] for d in lst["delegates"]) and "sage.confidential" in lst["permissions"]
    assert requests.get(f"{API}/jobs", headers=sh, timeout=30).status_code == 200
    assert requests.get(f"{API}/review", headers=sh, timeout=60).status_code == 200
    assert requests.post(f"{API}/jobs/nonexistent-tst/approve", headers=sh, timeout=30).status_code == 403
    assert requests.post(f"{API}/jobs/nonexistent-tst/commit", headers=sh, timeout=30).status_code == 403
    assert requests.get(f"{API}/activation", headers=sh, timeout=30).status_code == 403
    assert requests.get(f"{API}/orgs/{OP}/sage-internal", headers=sh, timeout=30).status_code == 403
    # delegate management stays admin-only
    assert requests.get(f"{API}/delegates", headers=sh, timeout=30).status_code == 403
    assert requests.get(f"{API}/sicon-links/migration", headers=sh, timeout=30).status_code == 403
    # grant confidential + approve
    r = requests.post(f"{API}/delegates", headers=H, json={"email": staff["email"],
                                                            "permissions": ["imports.approve", "sage.confidential"]}, timeout=30)
    assert r.status_code == 200
    assert requests.get(f"{API}/orgs/{OP}/sage-internal", headers=sh, timeout=30).status_code == 200
    assert requests.post(f"{API}/jobs/nonexistent-tst/approve", headers=sh, timeout=30).status_code in (404, 400, 409)
    assert requests.get(f"{API}/review", headers=sh, timeout=60).status_code == 403  # review revoked
    # revoke all
    r = requests.post(f"{API}/delegates", headers=H, json={"email": staff["email"], "permissions": []}, timeout=30)
    assert r.status_code == 200
    assert requests.get(f"{API}/orgs/{OP}/sage-internal", headers=sh, timeout=30).status_code == 403


def test_customer_user_cannot_read_sage_internal():
    h = {"Authorization": f"Bearer {_token('owner@isodemo.com')}"}
    assert requests.get(f"{API}/orgs/iso-demo-org/sage-internal", headers=h, timeout=30).status_code == 403
    assert requests.get(f"{API}/delegates", headers=h, timeout=30).status_code == 403


# --- Backfill dry run + Review Centre types + estate progress
def test_backfill_dry_run_writes_nothing(H):
    db = _db()
    n = db.onboarding_projects.count_documents({})
    r = requests.post(f"{API}/onboarding-projects/backfill?apply=false", headers=H, timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["created"] == 0 and isinstance(j["missing_projects"], int)
    assert db.onboarding_projects.count_documents({}) == n


def test_review_centre_shows_unscoped_link_and_held_sicon(H):
    db = _db()
    ext = f"TSTRC{uuid.uuid4().hex[:6].upper()}"
    db.sicon_external_links.insert_one({"integration_source": "sicon", "source_company": f"TSTRC{ext}", "external_entity_type": "site",
                                        "external_id": ext, "pulse_entity_id": "p", "migration_status": "needs_review",
                                        "migration_reason": "test"})
    db.sicon_import_conflicts.insert_one({"id": ext, "organization_id": OP, "external_entity_type": "equipment", "external_id": ext,
                                          "status": "open", "reasons": ["TST held"], "sicon_record": {"sicon_customer_code": ext}})
    try:
        r = requests.get(f"{API}/review?search={ext}", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        types = {i["type"] for i in r.json()["items"]}
        assert {"Unscoped Sicon link", "Sicon record held for review"} <= types, types
    finally:
        db.sicon_external_links.delete_many({"external_id": ext})
        db.sicon_import_conflicts.delete_many({"id": ext})


def test_estate_progress_unknown_project_404(H):
    r = requests.get(f"{BASE}/api/onboarding/projects/tst-nope-{uuid.uuid4().hex[:4]}/estate-progress", headers=H, timeout=30)
    assert r.status_code == 404


# --- Known defects found in iter 336 (fail until fixed)
def test_sync_never_reassigns_link_even_after_conflict():
    """A 2nd sync claiming a different Pulse id must stay a conflict (today it silently reassigns)."""
    import asyncio
    from utils import sicon_links as L
    from utils.database import db as adb
    t = f"TSTRA{uuid.uuid4().hex[:6].upper()}"

    async def go():
        try:
            await L.upsert_link("equipment", t, "equipment", "pa", organization_id="o1", source_company="101")
            await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101")
            await L.upsert_link("equipment", t, "equipment", "pz", organization_id="o1", source_company="101")
            return await L.get_pulse_id("equipment", t, "o1", "101")
        finally:
            await adb.sicon_external_links.delete_many({"external_id": t})
    assert asyncio.run(go()) == "pa"


def test_scoped_link_leaves_review_centre(H):
    """After a needs_review legacy link is scoped by a later migration, it must no longer show as 'Unscoped Sicon link'."""
    db = _db()
    ext = f"TSTMS{uuid.uuid4().hex[:6].upper()}"
    d = requests.get(f"{API}/sicon-links/migration", headers=H, timeout=30).json()
    if d["to_scope"] or d["needs_review"]:
        pytest.skip("Other legacy links exist — not applying migration on real data")
    db.sicon_external_links.insert_one({"integration_source": "sicon", "external_entity_type": "equipment", "external_id": ext,
                                        "organization_id": OP, "pulse_entity_type": "equipment", "pulse_entity_id": "legacy",
                                        "sync_status": "linked", "migration_status": "needs_review", "migration_reason": "test"})
    try:
        assert requests.post(f"{API}/sicon-links/migration/apply", headers=H, timeout=30).status_code == 200
        lk = db.sicon_external_links.find_one({"external_id": ext}, {"_id": 0})
        assert lk.get("source_company")
        items = requests.get(f"{API}/review?search={ext}", headers=H, timeout=60).json()["items"]
        assert not any(i["type"] == "Unscoped Sicon link" for i in items)
    finally:
        db.sicon_external_links.delete_many({"external_id": ext})


def test_tenant_service_desk_user_cannot_read_pulse_onboarding_projects():
    """owner@isodemo.com (customer tenant, is_service_desk) must not see Pulse onboarding projects / estate progress."""
    h = {"Authorization": f"Bearer {_token('owner@isodemo.com')}"}
    assert requests.get(f"{BASE}/api/onboarding/projects", headers=h, timeout=30).status_code == 403
