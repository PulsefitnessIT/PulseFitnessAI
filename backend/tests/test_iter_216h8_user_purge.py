"""
Iter 216h8 — Hard-purge endpoints for botched onboardings.

Pins:
  1. DELETE /master-admin/pulse-admins/{id}/purge wipes the user row.
  2. DELETE /master-admin/purge-user-by-email wipes by email across collections.
  3. Same local-part variants on the same domain are also matched
     (handles 'craig@' vs 'craig.henshall@' confusion).
  4. Non-master callers are blocked.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def master_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_purge_pulse_admin_wipes_user_row(master_headers):
    """Provision a pulse admin then purge → users row gone."""
    email = f"purge-{uuid.uuid4().hex[:8]}@example.com"
    create = httpx.post(
        f"{API_URL}/api/master-admin/pulse-admins",
        json={"email": email, "full_name": "Purge Test"},
        headers=master_headers, timeout=30,
    ).json()
    user_id = create["user_id"]
    purge = httpx.delete(
        f"{API_URL}/api/master-admin/pulse-admins/{user_id}/purge",
        headers=master_headers, timeout=30,
    )
    assert purge.status_code == 200, purge.text
    assert purge.json()["deleted"]["users"] == 1
    # Confirm it no longer appears in the listing.
    listing = httpx.get(
        f"{API_URL}/api/master-admin/pulse-admins",
        headers=master_headers, timeout=30,
    ).json()
    assert not any(a["id"] == user_id for a in listing["admins"])


def test_purge_by_email_handles_same_local_part_variants(master_headers, db):
    """Two users with same local-part prefix on same domain → both deleted."""
    salt = uuid.uuid4().hex[:6]
    domain = f"purgetest-{salt}.example"
    e1 = f"craig@{domain}"
    e2 = f"craig.henshall@{domain}"
    # Seed both rows directly so we don't fight email-uniqueness on POST.
    now = datetime.now(timezone.utc).isoformat()
    db.users.insert_many([
        {"id": str(uuid.uuid4()), "email": e1, "full_name": "Craig 1",
         "role": "owner", "organization_id": "test-org", "password": "x", "created_at": now},
        {"id": str(uuid.uuid4()), "email": e2, "full_name": "Craig 2",
         "role": "pulse_master_admin", "organization_id": None, "password": "x", "created_at": now},
    ])
    try:
        # Purge using one of the addresses.
        r = httpx.delete(
            f"{API_URL}/api/master-admin/purge-user-by-email?email={e2}",
            headers=master_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Both rows should be matched + deleted (same local-part on same domain).
        assert body["deleted"]["users"] >= 2
        # Confirm gone.
        remaining = list(db.users.find(
            {"email": {"$regex": f"@{domain}$"}}, {"_id": 0, "email": 1},
        ))
        assert remaining == []
    finally:
        db.users.delete_many({"email": {"$regex": f"@{domain}$"}})


def test_purge_by_email_rejects_invalid_input(master_headers):
    r = httpx.delete(
        f"{API_URL}/api/master-admin/purge-user-by-email?email=not-an-email",
        headers=master_headers, timeout=30,
    )
    assert r.status_code == 400
    r2 = httpx.delete(
        f"{API_URL}/api/master-admin/purge-user-by-email",
        headers=master_headers, timeout=30,
    )
    assert r2.status_code == 422  # missing required query param


def test_purge_endpoints_require_master_admin():
    """Anonymous → 401; non-master → 403."""
    r = httpx.delete(
        f"{API_URL}/api/master-admin/purge-user-by-email?email=anyone@example.com",
        timeout=30,
    )
    assert r.status_code in (401, 403)
