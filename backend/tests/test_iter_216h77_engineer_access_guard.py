"""Iter 216h77 — Engineer App access guard tests (sync DB).

Uses pymongo (sync) for fixture DB writes — avoids Motor event-loop
pinning across the fixture chain so the file plays nicely with
neighbouring async test modules.

Coverage:
  • Master / pulse admin always allowed
  • Approved + active subscription → allowed (active OR trialing)
  • Approved + free tier (10+ active referrals) → allowed
  • Active customer grant → allowed (even without partner profile)
  • Revoked grant → blocked
  • Suspended partner → blocked with reason=suspended
  • Paid tier + no sub + no grant → 402 needs_subscription
  • /partners/me/engineer-access never 402s (returns the reason for UI)
  • Customer can create + list + revoke grants
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://mod-hq-email.preview.emergentagent.com"
).rstrip("/")

OPERATOR_EMAIL = "e1.agent@gymaxisai.com"
OPERATOR_PASSWORD = "E1Agent123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def op_headers(): return _login(OPERATOR_EMAIL, OPERATOR_PASSWORD)
@pytest.fixture(scope="module")
def admin_headers(): return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def db():
    """Sync pymongo handle. Pytest plays nicely with multiple async test
    modules because we never touch a Motor event loop here."""
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


@pytest.fixture
def reset_operator(db):
    """Each test starts with the operator partner in a known state:
    approved, paid tier (£30), no subscription, no grants, no extra
    referrals (so app_fee_tier is recomputed to £30/mo)."""
    def _reset():
        # Drop any test-seeded referrals + force tier back to £30.
        db.partner_engineers.update_one(
            {"email": OPERATOR_EMAIL},
            {"$set": {"status": "approved",
                      "active_referral_count": 0,
                      "app_fee_tier": {"price_gbp": 30, "label": "£30/mo",
                                        "enhanced_review_required": False}},
             "$unset": {"subscription.stripe_subscription_id": "",
                        "subscription.status": "", "subscription.stripe_price_id": "",
                        "subscription.cancel_at_period_end": ""}},
        )
        db.partner_job_grants.delete_many({"engineer_email": OPERATOR_EMAIL})
        # Clean any orphan referrals from previous-run failures
        partner = db.partner_engineers.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})
        if partner:
            db.partner_referrals.delete_many({
                "partner_id": partner["id"],
                "referred_organization_id": {"$regex": "^freetier-"},
            })
    _reset()
    yield
    _reset()


# ─────────────────────────────────────────────────────────────────────────────


class TestAdminBypass:
    def test_admin_can_call_engineer_endpoints(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=admin_headers, timeout=10)
        assert r.status_code == 200


class TestBlockedStates:
    def test_paid_tier_no_sub_returns_402(self, op_headers, reset_operator):
        r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
        assert r.status_code == 402
        detail = r.json()["detail"]
        assert detail["code"] == "engineer_app_blocked"
        assert detail["reason"] == "needs_subscription"
        assert detail["app_fee_tier_gbp"] == 30

    def test_access_endpoint_returns_status_without_402(self, op_headers, reset_operator):
        r = requests.get(f"{BASE_URL}/api/partners/me/engineer-access", headers=op_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is False
        assert body["reason"] == "needs_subscription"


class TestActiveSubscriptionUnblocks:
    def test_simulated_active_sub_grants_access(self, db, op_headers, reset_operator):
        db.partner_engineers.update_one(
            {"email": OPERATOR_EMAIL},
            {"$set": {"subscription.status": "active",
                      "subscription.stripe_subscription_id": "sub_test_h77"}},
        )
        r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
        assert r.status_code == 200

    def test_trialing_status_also_grants_access(self, db, op_headers, reset_operator):
        db.partner_engineers.update_one(
            {"email": OPERATOR_EMAIL},
            {"$set": {"subscription.status": "trialing",
                      "subscription.stripe_subscription_id": "sub_trial_h77"}},
        )
        r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
        assert r.status_code == 200


class TestFreeTierUnblocks:
    def test_free_tier_grants_access(self, db, op_headers, reset_operator):
        """Seed 10 active refs → /partners/me triggers _recompute_app_fee
        → tier flips to £0/free → access granted."""
        partner = db.partner_engineers.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})
        seeded = []
        for i in range(10):
            rid = f"freetier-{i}-{uuid.uuid4()}"
            seeded.append(rid)
            db.partner_referrals.insert_one({
                "id": rid, "partner_id": partner["id"], "referral_code": "AGQZKPAP",
                "referred_organization_id": f"freetier-org-{i}-{uuid.uuid4()}",
                "status": "active", "pre_existing_in_pipeline": False,
                "created_at": "2026-05-13T00:00:00Z",
                "first_paid_at": "2026-05-13T00:00:00Z",
                "recurring_total_paid_gbp": 0.0,
            })
        try:
            # Force recompute via the live API
            requests.get(f"{BASE_URL}/api/partners/me", headers=op_headers, timeout=10)
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
            assert r.status_code == 200
        finally:
            db.partner_referrals.delete_many({"id": {"$in": seeded}})
            # Hit /partners/me again to recompute back to £30 tier
            requests.get(f"{BASE_URL}/api/partners/me", headers=op_headers, timeout=10)


class TestCustomerGrants:
    def test_grant_unlocks_engineer_app(self, db, op_headers, reset_operator):
        eng_user = db.users.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})
        grant_id = f"grant-{uuid.uuid4()}"
        db.partner_job_grants.insert_one({
            "id": grant_id, "engineer_user_id": eng_user["id"],
            "engineer_email": OPERATOR_EMAIL, "engineer_name": "E1 Test Engineer",
            "granted_by_organization_id": "fake-customer-org",
            "granted_by_user_id": "fake-user-id",
            "case_ids": ["case-1"], "scope": "per_case", "note": "test",
            "active": True, "created_at": "2026-05-13T00:00:00Z",
            "revoked_at": None, "revoked_by": None,
        })
        try:
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
            assert r.status_code == 200
            ar = requests.get(f"{BASE_URL}/api/partners/me/engineer-access", headers=op_headers, timeout=10)
            assert ar.json()["reason"] == "customer_grant"
        finally:
            db.partner_job_grants.delete_many({"id": grant_id})

    def test_revoked_grant_does_not_unlock(self, db, op_headers, reset_operator):
        eng_user = db.users.find_one({"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1})
        grant_id = f"grant-revoked-{uuid.uuid4()}"
        db.partner_job_grants.insert_one({
            "id": grant_id, "engineer_user_id": eng_user["id"],
            "engineer_email": OPERATOR_EMAIL, "engineer_name": "E1 Test Engineer",
            "granted_by_organization_id": "fake-customer-org",
            "granted_by_user_id": "fake-user-id",
            "case_ids": ["case-1"], "scope": "per_case", "note": "test",
            "active": False,  # revoked
            "created_at": "2026-05-13T00:00:00Z",
            "revoked_at": "2026-05-13T00:00:00Z", "revoked_by": "x",
        })
        try:
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
            assert r.status_code == 402
        finally:
            db.partner_job_grants.delete_many({"id": grant_id})


class TestCustomerGrantManagement:
    def test_customer_can_create_and_revoke_grant(self, db, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/customer-engineer-grants",
            json={"engineer_email": OPERATOR_EMAIL, "case_ids": ["c1", "c2"],
                  "scope": "per_case", "note": "ad-hoc contractor"},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        grant = r.json()["grant"]
        assert grant["active"] is True
        grant_id = grant["id"]

        lr = requests.get(f"{BASE_URL}/api/customer-engineer-grants", headers=admin_headers, timeout=10)
        assert lr.status_code == 200
        assert any(g["id"] == grant_id for g in lr.json()["grants"])

        dr = requests.delete(f"{BASE_URL}/api/customer-engineer-grants/{grant_id}",
                             headers=admin_headers, timeout=10)
        assert dr.status_code == 200
        db.partner_job_grants.delete_many({"id": grant_id})

    def test_unknown_engineer_email_404(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/customer-engineer-grants",
                          json={"engineer_email": "ghost@nobody.test", "case_ids": []},
                          headers=admin_headers, timeout=10)
        assert r.status_code == 404


class TestSuspendedBlocked:
    def test_suspended_partner_blocked(self, db, op_headers, reset_operator):
        db.partner_engineers.update_one(
            {"email": OPERATOR_EMAIL}, {"$set": {"status": "suspended"}},
        )
        try:
            r = requests.get(f"{BASE_URL}/api/svc/engineer/me", headers=op_headers, timeout=10)
            assert r.status_code == 402
            assert r.json()["detail"]["reason"] == "suspended"
        finally:
            db.partner_engineers.update_one(
                {"email": OPERATOR_EMAIL}, {"$set": {"status": "approved"}},
            )
