"""Iter 220j — Engineer attention digest.

Tests the new `/api/svc/engineer/attention` endpoint that aggregates
"needs my attention" items (compliance docs expiring, subscription
past_due, partner application pending, Stripe Connect unfinished)
into a single payload consumed by the Engineer Home hamburger badge
+ the Account Settings drawer.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://engineer-jobs-live.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
        data = r.json()
    _CACHE[email] = data.get("token") or data.get("access_token")
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def me_user_id(db):
    """Resolve the master admin's user_id so partner fixtures can
    attach to it without churning real partner data."""
    u = db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0, "id": 1})
    assert u, "Seed admin missing"
    return u["id"]


def _cleanup_partner(db, user_id):
    db.partner_engineers.delete_many({"user_id": user_id, "_iter_220j_test": True})


def test_attention_default_green_when_no_partner_record(db, me_user_id):
    """Engineers with no partner record are still serviced — the
    endpoint must return a clean green payload."""
    _cleanup_partner(db, me_user_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/svc/engineer/attention", headers=_hdr())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["severity"] == "green"
    assert body["count"] == 0
    assert body["items"] == []


def test_attention_flags_past_due_subscription(db, me_user_id):
    """A partner with subscription.status == 'past_due' must surface
    a RED item with the right CTA."""
    _cleanup_partner(db, me_user_id)
    partner_id = f"pe_iter220j_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220j_test": True,
        "user_id": me_user_id,
        "status": "approved",
        "subscription": {"status": "past_due", "stripe_subscription_id": "sub_test_220j"},
        "compliance_docs": {},
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/api/svc/engineer/attention", headers=_hdr())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["severity"] == "red"
        keys = {i["key"] for i in body["items"]}
        assert "subscription_past_due" in keys
        red = next(i for i in body["items"] if i["key"] == "subscription_past_due")
        assert red["severity"] == "red"
        assert red["cta_to"] == "/partner-engineer"
    finally:
        _cleanup_partner(db, me_user_id)


def test_attention_flags_expiring_compliance(db, me_user_id):
    """Compliance doc expiring in <14 days → amber; expired → red."""
    _cleanup_partner(db, me_user_id)
    soon = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    gone = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    partner_id = f"pe_iter220j_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220j_test": True,
        "user_id": me_user_id,
        "status": "approved",
        "subscription": {"status": "active", "stripe_subscription_id": "sub_test_220j"},
        "compliance_docs": {
            "insurance": {"file": "x", "expires_at": soon},
            "dbs": {"file": "y", "expires_at": gone},
        },
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/api/svc/engineer/attention", headers=_hdr())
        assert r.status_code == 200, r.text
        body = r.json()
        keys = {i["key"] for i in body["items"]}
        assert "compliance_expiring_insurance" in keys
        assert "compliance_expired_dbs" in keys
        # Severity should be red because of the expired DBS doc.
        assert body["severity"] == "red"
        # Items sort red-first so the expired entry comes first.
        first = body["items"][0]
        assert first["severity"] == "red"
    finally:
        _cleanup_partner(db, me_user_id)


def test_attention_flags_stripe_connect_pending(db, me_user_id):
    """charges_enabled = False → amber Stripe Connect prompt."""
    _cleanup_partner(db, me_user_id)
    partner_id = f"pe_iter220j_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220j_test": True,
        "user_id": me_user_id,
        "status": "approved",
        "subscription": {"status": "active", "stripe_subscription_id": "sub_test_220j"},
        "compliance_docs": {},
        "payout": {"stripe_connect": {"charges_enabled": False}},
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/api/svc/engineer/attention", headers=_hdr())
        assert r.status_code == 200, r.text
        body = r.json()
        keys = {i["key"] for i in body["items"]}
        assert "stripe_connect_pending" in keys
        # Only amber items present → severity is amber.
        assert body["severity"] == "amber"
        amb = next(i for i in body["items"] if i["key"] == "stripe_connect_pending")
        assert amb["cta_to"] == "/svc/engineer/payouts"
    finally:
        _cleanup_partner(db, me_user_id)


def test_attention_requires_auth():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/svc/engineer/attention")
    assert r.status_code in (401, 403), r.text
