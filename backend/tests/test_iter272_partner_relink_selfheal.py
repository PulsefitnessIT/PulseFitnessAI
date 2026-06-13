"""Iter 272 — Partner Engineer "Become a Partner / Apply now" loop fix.

Reproduces and guards the production bug where a partner engineer who
signs in is routed to /partner-engineer but sees the EMPTY "Become a
Partner Engineer / Apply now" screen instead of their dashboard.

Root cause: the login claim hook flags the user as a partner engineer by
EMAIL match, but the dashboard (`GET /partners/me`) resolves the partner
row by `user_id` ONLY. When the partner_engineers row points at a stale /
placeholder user_id (e.g. the engineer's original account was removed and
they re-registered with the same email), the two disagree → flagged but
empty dashboard.

Fix: the claim hook now self-heals by relinking the email-matched row to
the current user, and `GET /partners/me` re-runs the claim on a null
partner. This test seeds the stale-link scenario, logs in, and asserts
`/partners/me` returns the (relinked) partner.
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


def _hash(pw: str) -> str:
    from utils.auth import hash_password
    return hash_password(pw)


def test_partners_me_self_heals_stale_user_id_link():
    db = _db()
    email = f"reseed.partner.{uuid.uuid4().hex[:8]}@example.com"
    real_uid = f"real-{uuid.uuid4().hex}"
    pe_id = f"pe-{uuid.uuid4().hex}"
    password = "ReseedPass123!"

    db.partner_engineers.delete_many({"email": email})
    db.users.delete_many({"email": email})
    try:
        # Partner row points at a DEAD/stale user_id (not pending, not real).
        db.partner_engineers.insert_one({
            "id": pe_id,
            "email": email,
            "user_id": f"dead-account-{uuid.uuid4().hex}",
            "status": "approved",
            "referral_code": f"RS{uuid.uuid4().hex[:6].upper()}",
            "created_at": "2026-01-01T00:00:00+00:00",
            "app_fee_tier": {},
        })
        # The engineer re-registered: flagged as a partner (by email) but the
        # row points elsewhere → would land on the empty Apply screen.
        db.users.insert_one({
            "id": real_uid,
            "email": email,
            "password": _hash(password),
            "role": "engineer_partner",
            "account_type": "partner_engineer",
            "is_partner_engineer": True,
            "organization_id": None,
            "full_name": "Reseed Engineer",
            "active": True,
        })

        # Pre-condition: lookup by the real user_id finds nothing.
        assert db.partner_engineers.find_one({"user_id": real_uid}) is None

        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login",
                   json={"email": email, "password": password},
                   headers=rate_limit_bypass_headers(), timeout=15)
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"

        me = s.get(f"{BASE}/api/partners/me", timeout=15)
        assert me.status_code == 200, me.text[:200]
        partner = me.json().get("partner")
        assert partner is not None, "partner is None → engineer still stuck on Apply screen"
        assert partner.get("status") == "approved"

        # The row was relinked to the real user (self-heal persisted).
        relinked = db.partner_engineers.find_one({"id": pe_id}, {"_id": 0, "user_id": 1})
        assert relinked and relinked["user_id"] == real_uid
    finally:
        db.partner_engineers.delete_many({"email": email})
        db.users.delete_many({"email": email})


def test_claim_hook_noop_for_non_partner():
    """A normal (non-partner) user must NOT be flagged or relinked."""
    import asyncio
    from utils.partner_claim import claim_pending_partner_for_user

    db = _db()
    email = f"normal.user.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"normal-{uuid.uuid4().hex}"
    db.users.delete_many({"email": email})
    try:
        db.users.insert_one({"id": uid, "email": email, "role": "owner"})
        result = asyncio.get_event_loop().run_until_complete(
            claim_pending_partner_for_user(email, uid)
        )
        assert result is False
        u = db.users.find_one({"id": uid}, {"_id": 0, "is_partner_engineer": 1})
        assert not u.get("is_partner_engineer")
    finally:
        db.users.delete_many({"email": email})



def test_backfill_relinks_stale_and_skips_other_live_user():
    """The proactive backfill relinks a placeholder/stale row to the owning
    user, but must NOT steal a row that's already linked to another LIVE user."""
    import asyncio
    from utils.partner_claim import backfill_partner_relink

    db = _db()
    em_stale = f"bf.stale.{uuid.uuid4().hex[:8]}@example.com"
    uid_stale = f"bf-real-{uuid.uuid4().hex}"
    pe_stale = f"pe-{uuid.uuid4().hex}"

    em_live = f"bf.live.{uuid.uuid4().hex[:8]}@example.com"
    uid_live_a = f"bf-livea-{uuid.uuid4().hex}"   # real, owns the row
    uid_live_b = f"bf-liveb-{uuid.uuid4().hex}"   # real, owns the email (collision-ish)
    pe_live = f"pe-{uuid.uuid4().hex}"

    for em in (em_stale, em_live):
        db.partner_engineers.delete_many({"email": em})
        db.users.delete_many({"email": em})
    try:
        # Stale row → owning user exists, row points at a dead id → relink.
        db.partner_engineers.insert_one({
            "id": pe_stale, "email": em_stale, "user_id": f"dead-{uuid.uuid4().hex}",
            "status": "approved", "referral_code": f"BF{uuid.uuid4().hex[:6].upper()}",
        })
        db.users.insert_one({"id": uid_stale, "email": em_stale, "role": "engineer_partner"})

        # Row linked to a real, different user → must be left alone.
        db.partner_engineers.insert_one({
            "id": pe_live, "email": em_live, "user_id": uid_live_a,
            "status": "approved", "referral_code": f"BF{uuid.uuid4().hex[:6].upper()}",
        })
        db.users.insert_one({"id": uid_live_a, "email": "other.owner@example.com", "role": "owner"})
        db.users.insert_one({"id": uid_live_b, "email": em_live, "role": "engineer_partner"})

        asyncio.get_event_loop().run_until_complete(backfill_partner_relink(dry_run=False))

        relinked = db.partner_engineers.find_one({"id": pe_stale}, {"_id": 0, "user_id": 1})
        assert relinked["user_id"] == uid_stale, "stale row should be relinked to owning user"
        assert db.users.find_one({"id": uid_stale}, {"_id": 0, "is_partner_engineer": 1}).get("is_partner_engineer")

        untouched = db.partner_engineers.find_one({"id": pe_live}, {"_id": 0, "user_id": 1})
        assert untouched["user_id"] == uid_live_a, "must NOT steal a row owned by another live user"
    finally:
        for em in (em_stale, em_live, "other.owner@example.com"):
            db.partner_engineers.delete_many({"email": em})
            db.users.delete_many({"email": em})
        db.users.delete_many({"id": {"$in": [uid_live_a, uid_live_b]}})
