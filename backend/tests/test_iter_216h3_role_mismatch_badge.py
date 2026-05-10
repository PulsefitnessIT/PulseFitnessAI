"""
Iter 216h3 — Role-mismatch decoration on /master-admin/users.

When a user was invited as one role but their current `users.role` is
different (legit promotion, demotion, or an accidental dropdown reset),
the backend stamps `invited_role` on the response so the frontend can
surface a warning badge in the per-org Users list.

Sync-pymongo style to match the existing tests/* harness.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pymongo import MongoClient

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def master_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME, "MONGO_URL/DB_NAME must be set"
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def org_id(master_headers):
    r = httpx.get(
        f"{API_URL}/api/master-admin/organizations",
        headers=master_headers, timeout=30,
    )
    r.raise_for_status()
    return r.json()["organizations"][0]["id"]


def _fetch_user(headers, email):
    r = httpx.get(f"{API_URL}/api/master-admin/users", headers=headers, timeout=60)
    r.raise_for_status()
    return next((u for u in r.json()["users"] if u.get("email") == email), None)


def test_no_mismatch_when_roles_aligned(master_headers, db, org_id):
    email = f"role-aligned-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "full_name": "Aligned",
            "role": "manager", "organization_id": org_id,
            "password": "x", "created_at": now,
        })
        db.invites.insert_one({
            "email": email, "organization_id": org_id,
            "role": "manager", "status": "accepted",
            "accepted_at": now, "created_at": now,
        })
        me = _fetch_user(master_headers, email)
        assert me is not None
        assert me.get("invited_role") is None
    finally:
        db.users.delete_many({"email": email})
        db.invites.delete_many({"email": email})


def test_mismatch_decorates_invited_role(master_headers, db, org_id):
    email = f"role-mismatch-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "full_name": "Mismatch",
            "role": "staff", "organization_id": org_id,
            "password": "x", "created_at": now,
        })
        db.invites.insert_one({
            "email": email, "organization_id": org_id,
            "role": "manager", "status": "accepted",
            "accepted_at": now, "created_at": now,
        })
        me = _fetch_user(master_headers, email)
        assert me is not None
        assert me.get("invited_role") == "manager"
        assert me.get("role") == "staff"
    finally:
        db.users.delete_many({"email": email})
        db.invites.delete_many({"email": email})


def test_most_recent_accepted_invite_wins(master_headers, db, org_id):
    email = f"role-multi-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(days=30)).isoformat()
    later = now.isoformat()
    try:
        db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "full_name": "Multi",
            "role": "staff", "organization_id": org_id,
            "password": "x", "created_at": earlier,
        })
        db.invites.insert_many([
            {"email": email, "organization_id": org_id, "role": "staff",
             "status": "accepted", "accepted_at": earlier, "created_at": earlier},
            {"email": email, "organization_id": org_id, "role": "owner",
             "status": "accepted", "accepted_at": later, "created_at": later},
        ])
        me = _fetch_user(master_headers, email)
        assert me is not None
        assert me.get("invited_role") == "owner"
    finally:
        db.users.delete_many({"email": email})
        db.invites.delete_many({"email": email})


def test_pending_invite_does_not_drive_mismatch(master_headers, db, org_id):
    email = f"role-pending-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "full_name": "Pending",
            "role": "staff", "organization_id": org_id,
            "password": "x", "created_at": now,
        })
        db.invites.insert_one({
            "email": email, "organization_id": org_id,
            "role": "owner", "status": "pending",
            "created_at": now,
        })
        me = _fetch_user(master_headers, email)
        assert me is not None
        assert me.get("invited_role") is None
    finally:
        db.users.delete_many({"email": email})
        db.invites.delete_many({"email": email})
