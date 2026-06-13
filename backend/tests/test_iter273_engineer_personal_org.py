"""Iter 273 — Engineer App works for independent (org-less) partner engineers.

The whole Engineer App (/svc/engineer/*) scopes by organization_id, so an
independent partner engineer (created org-less) got 403 "Organization
context required" on the home/dashboard — the app was unusable for them.

Fix: provision a personal single-tenant organization for org-less partner
engineers (at login via the claim hook + a startup backfill migration), so
the Engineer App loads and their data is isolated per engineer. Also unflag
users wrongly marked is_partner_engineer with no partner row (they were
routed to the empty Apply screen).
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()


def _db():
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        pytest.skip("MONGO_URL/DB_NAME not set")
    return MongoClient(url)[name]


def _hash(pw):
    from utils.auth import hash_password
    return hash_password(pw)


def test_orgless_engineer_gets_personal_org_and_dashboard_loads():
    db = _db()
    email = f"indie.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"indie-{uuid.uuid4().hex}"
    pw = "IndiePass123!"
    db.users.delete_many({"email": email})
    db.partner_engineers.delete_many({"email": email})
    created_org = None
    try:
        db.users.insert_one({
            "id": uid, "email": email, "password": _hash(pw),
            "role": "engineer_partner", "account_type": "partner_engineer",
            "is_partner_engineer": True, "organization_id": None,
            "service_org_id": None, "full_name": "Indie Eng", "active": True,
        })
        db.partner_engineers.insert_one({
            "id": f"pe-{uuid.uuid4().hex}", "email": email, "user_id": uid,
            "status": "approved", "referral_code": f"IN{uuid.uuid4().hex[:6].upper()}",
            "country_code": "US", "created_at": "2026-01-01T00:00:00+00:00",
        })

        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                   headers=rate_limit_bypass_headers(), timeout=15)
        assert r.status_code == 200, r.text[:200]

        # Login (claim hook) should have provisioned a personal org.
        u = db.users.find_one({"id": uid}, {"_id": 0, "organization_id": 1})
        created_org = u.get("organization_id")
        assert created_org, "no personal org provisioned at login"
        org = db.organizations.find_one({"id": created_org}, {"_id": 0})
        assert org["account_type"] == "partner_engineer"
        assert org["country_code"] == "US" and org["currency"] == "USD"
        assert org.get("is_engineer_personal_org") is True

        # The Engineer App home/dashboard now loads (was 403 before).
        d = s.get(f"{BASE}/api/svc/engineer/dashboard", timeout=15)
        assert d.status_code == 200, f"dashboard 403/err: {d.status_code} {d.text[:150]}"
        assert "kpis" in d.json()
        me = s.get(f"{BASE}/api/svc/engineer/me", timeout=15)
        assert me.status_code == 200
    finally:
        if created_org:
            db.organizations.delete_one({"id": created_org})
        db.users.delete_many({"email": email})
        db.partner_engineers.delete_many({"email": email})


def test_personal_org_provisioning_is_idempotent():
    import asyncio
    from utils.partner_claim import ensure_engineer_personal_org
    db = _db()
    email = f"idem.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"idem-{uuid.uuid4().hex}"
    db.users.delete_many({"email": email})
    org_ids = set()
    try:
        db.users.insert_one({
            "id": uid, "email": email, "is_partner_engineer": True,
            "organization_id": None, "service_org_id": None, "full_name": "Idem",
        })
        loop = asyncio.get_event_loop()
        for _ in range(3):
            u = db.users.find_one({"id": uid}, {"_id": 0})
            oid = loop.run_until_complete(ensure_engineer_personal_org(u))
            org_ids.add(oid)
        assert len(org_ids) == 1, f"provisioning not idempotent: {org_ids}"
        assert db.organizations.count_documents(
            {"is_engineer_personal_org": True, "name": "Idem (Engineer)"}) == 1
    finally:
        for oid in org_ids:
            if oid:
                db.organizations.delete_one({"id": oid})
        db.users.delete_many({"email": email})


def test_unflag_misflagged_keeps_real_partner():
    import asyncio
    from utils.partner_claim import unflag_misflagged_partner_engineers
    db = _db()
    bad_email = f"bad.{uuid.uuid4().hex[:8]}@example.com"
    good_email = f"good.{uuid.uuid4().hex[:8]}@example.com"
    bad_uid = f"bad-{uuid.uuid4().hex}"
    good_uid = f"good-{uuid.uuid4().hex}"
    db.users.delete_many({"email": {"$in": [bad_email, good_email]}})
    db.partner_engineers.delete_many({"email": good_email})
    try:
        # Wrongly flagged, NO partner row → should be unflagged.
        db.users.insert_one({"id": bad_uid, "email": bad_email,
                             "is_partner_engineer": True, "role": "owner"})
        # Real partner (has a row) → must stay flagged.
        db.users.insert_one({"id": good_uid, "email": good_email,
                             "is_partner_engineer": True, "role": "engineer_partner"})
        db.partner_engineers.insert_one({
            "id": f"pe-{uuid.uuid4().hex}", "email": good_email, "user_id": good_uid,
            "status": "approved", "referral_code": f"GD{uuid.uuid4().hex[:6].upper()}"})

        asyncio.get_event_loop().run_until_complete(
            unflag_misflagged_partner_engineers(dry_run=False))

        assert db.users.find_one({"id": bad_uid}).get("is_partner_engineer") is False
        assert db.users.find_one({"id": good_uid}).get("is_partner_engineer") is True
    finally:
        db.users.delete_many({"email": {"$in": [bad_email, good_email]}})
        db.partner_engineers.delete_many({"email": good_email})
