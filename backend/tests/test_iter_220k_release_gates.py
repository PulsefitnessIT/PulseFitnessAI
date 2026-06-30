"""Iter 220k — Partner Engineer release-gates (P0 batch).

Three things must be true before a Partner Engineer can pick up a
paid job, and one thing must happen when they lose access:

  P0-1  /  P0-3 — Compliance-to-claim gate (combined)
    * `compliance_paused` flag set by the nightly job → 403.
    * No DBS *and* no RTW document on file → 403.
    * Internal employees + customer-grant engineers are EXEMPT.

  P0-2 — Mid-job cancellation recovery
    * When subscription flips to canceled/unpaid/incomplete_expired,
      any in-flight `svc_cases` assigned to that engineer get bounced
      back to NEW with `needs_reassignment` flagged and a system
      audit entry. The case-owning org is notified by email
      (best-effort).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://admin-portal-fix-37.preview.emergentagent.com",
)
_TOKENS: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _TOKENS.get(email):
        return _TOKENS[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
        data = r.json()
    _TOKENS[email] = data.get("token") or data.get("access_token")
    return _TOKENS[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def me_user_id(db):
    u = db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0, "id": 1, "organization_id": 1})
    assert u, "Seed admin missing"
    return u["id"]


def _cleanup(db, user_id):
    """Remove any test partner records / svc_engineers row owned by
    this user that we mutated during the test."""
    db.partner_engineers.delete_many({"user_id": user_id, "_iter_220k_test": True})
    db.svc_engineers.delete_many({"id": user_id, "_iter_220k_test": True})


# ────────────────────────────────────────────────────────────────────
# Unit: _has_valid_claim_doc
# ────────────────────────────────────────────────────────────────────


def test_has_valid_claim_doc_helper():
    from datetime import datetime, timedelta, timezone
    from routes.partners import _has_valid_claim_doc

    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    # No docs at all
    assert _has_valid_claim_doc({}) is False
    assert _has_valid_claim_doc({"compliance_docs": {}}) is False

    # DBS with no expiry → valid
    assert _has_valid_claim_doc({"compliance_docs": {"dbs": {"file": "x"}}}) is True

    # RTW expired, DBS missing → invalid
    assert _has_valid_claim_doc({"compliance_docs": {"rtw": {"file": "x", "expires_at": past}}}) is False

    # RTW future expiry → valid
    assert _has_valid_claim_doc({"compliance_docs": {"rtw": {"file": "x", "expires_at": future}}}) is True

    # Only safeguarding/public_liability uploaded → invalid (those don't count)
    assert _has_valid_claim_doc({"compliance_docs": {
        "safeguarding": {"file": "x"},
        "public_liability": {"file": "y"},
    }}) is False


# ────────────────────────────────────────────────────────────────────
# require_engineer_compliance_to_claim — gate logic (direct invocation)
#
# We call the gate function directly with a fake user dict rather than
# going through HTTP. This avoids the master_admin / e1.agent test-user
# coupling and lets us exercise every branch deterministically.
# ────────────────────────────────────────────────────────────────────


def _invoke_gate(user_dict):
    """Run the gate function synchronously and return either the user
    on pass or the HTTPException raised on block."""
    from fastapi import HTTPException
    from routes.partners import require_engineer_compliance_to_claim
    try:
        return asyncio.get_event_loop().run_until_complete(
            require_engineer_compliance_to_claim(user_dict)
        )
    except HTTPException as e:
        return e


def test_gate_blocks_when_no_compliance_docs(db, me_user_id):
    """Approved partner, active sub, but zero DBS/RTW → 403 compliance_required."""
    _cleanup(db, me_user_id)
    fake_user_id = f"u_iter220k_{uuid.uuid4().hex[:6]}"
    partner_id = f"pe_iter220k_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220k_test": True,
        "user_id": fake_user_id,
        "status": "approved",
        "subscription": {"status": "active", "stripe_subscription_id": "sub_test"},
        "compliance_docs": {},
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        fake_user = {"id": fake_user_id, "email": "test@example.test"}
        result = _invoke_gate(fake_user)
        from fastapi import HTTPException
        assert isinstance(result, HTTPException), f"Expected block, got {result}"
        assert result.status_code == 403
        assert result.detail["reason"] == "compliance_required"
        assert "dbs" in result.detail["required_one_of"]
    finally:
        db.partner_engineers.delete_one({"id": partner_id})


def test_gate_blocks_when_compliance_paused(db):
    """compliance_paused=True → 403 compliance_paused, regardless of docs."""
    fake_user_id = f"u_iter220k_{uuid.uuid4().hex[:6]}"
    partner_id = f"pe_iter220k_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220k_test": True,
        "user_id": fake_user_id,
        "status": "approved",
        "subscription": {"status": "active", "stripe_subscription_id": "sub_test"},
        "compliance_docs": {"dbs": {"file": "x"}},
        "compliance_paused": True,
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        from fastapi import HTTPException
        fake_user = {"id": fake_user_id, "email": "test@example.test"}
        result = _invoke_gate(fake_user)
        assert isinstance(result, HTTPException), f"Expected block, got {result}"
        assert result.status_code == 403
        assert result.detail["reason"] == "compliance_paused"
    finally:
        db.partner_engineers.delete_one({"id": partner_id})


def test_gate_passes_when_compliant(db):
    """DBS on file + not paused + active sub → returns the user dict."""
    fake_user_id = f"u_iter220k_{uuid.uuid4().hex[:6]}"
    partner_id = f"pe_iter220k_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220k_test": True,
        "user_id": fake_user_id,
        "status": "approved",
        "subscription": {"status": "active", "stripe_subscription_id": "sub_test"},
        "compliance_docs": {"dbs": {"file": "x"}},
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        fake_user = {"id": fake_user_id, "email": "test@example.test"}
        result = _invoke_gate(fake_user)
        assert isinstance(result, dict), f"Expected user dict on pass, got {result}"
        assert result["id"] == fake_user_id
    finally:
        db.partner_engineers.delete_one({"id": partner_id})


def test_gate_passes_for_master_admin(db, me_user_id):
    """Master admins are exempt — they can claim/test without compliance."""
    fake_master = {"id": me_user_id, "email": "admin@gymaxisai.com", "is_master_admin": True}
    result = _invoke_gate(fake_master)
    assert isinstance(result, dict), f"Expected pass for master admin, got {result}"


def test_gate_blocks_when_subscription_missing(db):
    """No subscription → 402 (inherited from require_engineer_app_access)."""
    fake_user_id = f"u_iter220k_{uuid.uuid4().hex[:6]}"
    partner_id = f"pe_iter220k_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220k_test": True,
        "user_id": fake_user_id,
        "status": "approved",
        "subscription": {},
        # Paid tier so free-tier bypass doesn't kick in.
        "app_fee_tier": {"price_gbp": 30, "label": "£30/mo", "enhanced_review_required": False},
        "compliance_docs": {"dbs": {"file": "x"}},
        "payout": {"stripe_connect": {"charges_enabled": True}},
    })
    try:
        from fastapi import HTTPException
        fake_user = {"id": fake_user_id, "email": "test@example.test"}
        result = _invoke_gate(fake_user)
        assert isinstance(result, HTTPException), f"Expected block, got {result}"
        assert result.status_code == 402
        assert result.detail["reason"] == "needs_subscription"
    finally:
        db.partner_engineers.delete_one({"id": partner_id})


# ────────────────────────────────────────────────────────────────────
# Smoke: HTTP-level — master admin bypass keeps existing flows working
# ────────────────────────────────────────────────────────────────────


def test_claim_endpoint_404s_for_master_admin(db, me_user_id):
    """Master admin hits the claim endpoint with a bogus case_id — the
    gate must let them through (master_admin bypass) and the handler
    then 404s on case lookup. Proves we haven't accidentally broken
    admin support flows."""
    # Need a svc_engineers row for the admin so claim_case can resolve.
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    existing = db.svc_engineers.find_one({"id": me_user_id, "organization_id": org_id})
    cleanup_engineer = not bool(existing)
    if cleanup_engineer:
        db.svc_engineers.insert_one({
            "id": me_user_id,
            "_iter_220k_test": True,
            "organization_id": org_id,
            "full_name": "Master Admin",
            "email": "admin@gymaxisai.com",
            "active": True,
        })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(f"{BASE}/api/svc/engineer/queue/__nope__/claim", headers=_hdr(), json={})
        assert r.status_code == 404, f"Expected 404 (case lookup) got {r.status_code}: {r.text}"
    finally:
        if cleanup_engineer:
            db.svc_engineers.delete_one({"id": me_user_id, "_iter_220k_test": True})


# ────────────────────────────────────────────────────────────────────
# P0-2 — Mid-job cancellation recovery
# ────────────────────────────────────────────────────────────────────


def test_subscription_cancel_bounces_inflight_cases_back_to_queue(db, me_user_id):
    """When Stripe says the engineer's plan is cancelled, in-flight
    cases assigned to them must be flipped to NEW with
    needs_reassignment=True so the dispatch admin sees them."""
    _cleanup(db, me_user_id)
    org_id = db.users.find_one({"id": me_user_id})["organization_id"]
    partner_id = f"pe_iter220k_{uuid.uuid4().hex[:6]}"
    db.partner_engineers.insert_one({
        "id": partner_id,
        "_iter_220k_test": True,
        "user_id": me_user_id,
        "full_name": "Test Engineer 220k",
        "status": "approved",
        "subscription": {"status": "active",
                         "stripe_subscription_id": "sub_iter220k"},
        "compliance_docs": {"dbs": {"file": "x"}},
    })

    # Two in-flight cases assigned to the engineer + one closed case
    # that should be left alone.
    in_flight_id = f"case_220k_inflight_{uuid.uuid4().hex[:6]}"
    closed_id = f"case_220k_closed_{uuid.uuid4().hex[:6]}"
    db.svc_cases.insert_many([
        {
            "id": in_flight_id, "organization_id": org_id,
            "reference": "REF-IF-001", "title": "On-site work",
            "status": "on_site",
            "assigned_engineer_id": me_user_id,
            "assigned_engineer_name": "Test Engineer 220k",
        },
        {
            "id": closed_id, "organization_id": org_id,
            "reference": "REF-CL-001", "title": "Already closed",
            "status": "closed",
            "assigned_engineer_id": me_user_id,
        },
    ])

    try:
        from routes.partners import handle_partner_subscription_event
        # Simulate Stripe canceled event
        result = asyncio.get_event_loop().run_until_complete(
            handle_partner_subscription_event({
                "id": "sub_iter220k",
                "status": "canceled",
                "metadata": {"kind": "partner_engineer_plan", "partner_id": partner_id},
                "items": {"data": []},
                "current_period_end": 0,
                "cancel_at_period_end": False,
            })
        )
        assert result is not None
        assert result["status"] == "canceled"

        # Allow time for the side-effect to land (the function awaits, so
        # this is synchronous in practice — kept for clarity).
        if_doc = db.svc_cases.find_one({"id": in_flight_id})
        assert if_doc["status"] == "new", if_doc
        assert if_doc.get("assigned_engineer_id") in (None, ""), if_doc
        assert if_doc.get("needs_reassignment") is True
        assert "subscription_canceled" in (if_doc.get("needs_reassignment_reason") or "")

        # Closed case must be untouched.
        cl_doc = db.svc_cases.find_one({"id": closed_id})
        assert cl_doc["status"] == "closed"
        assert cl_doc.get("assigned_engineer_id") == me_user_id

        # Audit event was appended.
        ev = db.svc_case_events.find_one({"case_id": in_flight_id, "extra.kind": "partner_access_lost"})
        assert ev, "Expected partner_access_lost event on the in-flight case"
    finally:
        db.svc_cases.delete_many({"id": {"$in": [in_flight_id, closed_id]}})
        db.svc_case_events.delete_many({"case_id": {"$in": [in_flight_id, closed_id]}})
        _cleanup(db, me_user_id)
