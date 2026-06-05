"""Regression tests for SEC-007 — CRM cross-tenant IDOR.

Before the fix, the legacy /api/crm CRUD endpoints (crm_core, crm_workflows,
crm_documents) fetched/mutated resources by id WITHOUT filtering on the
caller's organization_id, so a CRM user in org A could read/update/delete
records belonging to org B.

This test seeds two orgs and asserts a user in org B cannot touch org A's
contact (404), while still being able to access its own (200). It runs
against the live preview server using the same flow as production traffic.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

pytestmark = pytest.mark.skipif(
    not (API and MONGO_URL and DB_NAME),
    reason="REACT_APP_BACKEND_URL / MONGO_URL / DB_NAME not configured",
)


@pytest.fixture()
def seeded(tmp_path):
    from routes.crm_auth import crm_hash_password

    db = pymongo.MongoClient(MONGO_URL)[DB_NAME]
    suffix = uuid.uuid4().hex[:8]
    email = f"idor.{suffix}@example.com"
    org_a = f"idor-org-A-{suffix}"
    org_b = f"idor-org-B-{suffix}"
    contact_a = f"idor-contact-A-{suffix}"
    contact_b = f"idor-contact-B-{suffix}"
    now = datetime.now(timezone.utc).isoformat()

    db.crm_users.insert_one({
        "id": f"idor-user-{suffix}", "email": email,
        "password": crm_hash_password("IdorTest123!"), "full_name": "IDOR Test",
        "role": "admin", "organization_id": org_b, "is_active": True, "created_at": now,
    })
    db.crm_contacts.insert_one({"id": contact_a, "organization_id": org_a,
                                "first_name": "Foreign", "last_name": "Org", "created_at": now})
    db.crm_contacts.insert_one({"id": contact_b, "organization_id": org_b,
                                "first_name": "Own", "last_name": "Org", "created_at": now})
    try:
        yield {"email": email, "contact_a": contact_a, "contact_b": contact_b}
    finally:
        db.crm_users.delete_many({"email": email})
        db.crm_contacts.delete_many({"id": {"$in": [contact_a, contact_b]}})


def _token(email):
    r = requests.post(f"{API}/api/crm/auth/login",
                      json={"email": email, "password": "IdorTest123!"}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def test_crm_contact_cross_tenant_is_blocked(seeded):
    h = {"Authorization": f"Bearer {_token(seeded['email'])}"}
    a, b = seeded["contact_a"], seeded["contact_b"]

    # Foreign org's contact must be invisible / unmodifiable / undeletable.
    assert requests.get(f"{API}/api/crm/contacts/{a}", headers=h, timeout=20).status_code == 404
    assert requests.put(f"{API}/api/crm/contacts/{a}", headers=h,
                        json={"first_name": "HACKED"}, timeout=20).status_code == 404
    assert requests.delete(f"{API}/api/crm/contacts/{a}", headers=h, timeout=20).status_code == 404

    # Own org's contact remains fully accessible (no over-blocking).
    assert requests.get(f"{API}/api/crm/contacts/{b}", headers=h, timeout=20).status_code == 200

    # And the foreign record was never mutated.
    db = pymongo.MongoClient(MONGO_URL)[DB_NAME]
    doc = db.crm_contacts.find_one({"id": a})
    assert doc is not None and doc["first_name"] == "Foreign"


@pytest.fixture()
def two_org_users():
    """Two CRM admins in two distinct orgs."""
    from routes.crm_auth import crm_hash_password

    db = pymongo.MongoClient(MONGO_URL)[DB_NAME]
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    users = {
        "a": {"email": f"pl.a.{suffix}@example.com", "org": f"pl-org-A-{suffix}"},
        "b": {"email": f"pl.b.{suffix}@example.com", "org": f"pl-org-B-{suffix}"},
    }
    for key, u in users.items():
        db.crm_users.insert_one({
            "id": f"pl-user-{key}-{suffix}", "email": u["email"],
            "password": crm_hash_password("IdorTest123!"), "full_name": f"PL {key}",
            "role": "admin", "organization_id": u["org"], "is_active": True, "created_at": now,
        })
    try:
        yield users
    finally:
        emails = [u["email"] for u in users.values()]
        orgs = [u["org"] for u in users.values()]
        db.crm_users.delete_many({"email": {"$in": emails}})
        db.crm_pipelines.delete_many({"organization_id": {"$in": orgs}})


def test_crm_pipeline_cross_tenant_is_blocked(two_org_users):
    # Each user lists pipelines (auto-creates an org-scoped default).
    def own_pipeline(email):
        h = {"Authorization": f"Bearer {_token(email)}"}
        r = requests.get(f"{API}/api/crm/pipelines", headers=h, timeout=20)
        r.raise_for_status()
        pls = r.json()["pipelines"]
        assert len(pls) == 1, "list_pipelines must be org-scoped to one default"
        return h, pls[0]["id"]

    h_a, pid_a = own_pipeline(two_org_users["a"]["email"])
    h_b, pid_b = own_pipeline(two_org_users["b"]["email"])
    assert pid_a != pid_b, "each org must own a distinct pipeline document"

    # B can edit its own pipeline...
    assert requests.put(f"{API}/api/crm/pipelines/{pid_b}", headers=h_b,
                        json={"name": "B pipeline"}, timeout=20).status_code == 200
    # ...but NOT org A's pipeline.
    assert requests.put(f"{API}/api/crm/pipelines/{pid_a}", headers=h_b,
                        json={"name": "HACKED"}, timeout=20).status_code == 404

    db = pymongo.MongoClient(MONGO_URL)[DB_NAME]
    assert db.crm_pipelines.find_one({"id": pid_a})["name"] != "HACKED"
