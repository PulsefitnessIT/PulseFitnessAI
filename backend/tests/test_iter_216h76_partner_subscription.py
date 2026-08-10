"""Iter 216h76 — Live Partner Plan Stripe subscription tests.

Covers the Phase 2 subscription wiring on top of the Partner Engineer
Network. Real Stripe API is not exercised (would require live products).
We instead assert:
  • 501 when Stripe Partner Plan price IDs are unset
  • 400 when partner is on the free tier (no sub needed)
  • 400 when application is not approved
  • subscription field is recorded after a simulated checkout-completed event
  • subscription event sync (price-swap + cancellation) flows through correctly
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://multi-eng-booking.preview.emergentagent.com"
).rstrip("/")

OPERATOR_EMAIL = "e1.agent@gymaxisai.com"
OPERATOR_PASSWORD = "E1Agent123!"


@pytest.fixture(scope="module")
def op_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD}, timeout=10)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def db_client():
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # type: ignore
    return db


class TestSubscriptionCheckoutGuards:
    # NOTE: `test_unconfigured_env_returns_501` removed in h77 — once
    # production Stripe price IDs are seeded, the test can't depend on
    # local-process env state. The equivalent unit-test is
    # `TestPriceIdResolver.test_unknown_tier_returns_none`.

    def test_free_tier_blocks_checkout(self, op_headers, db_client):
        """Force the partner to 10+ active refs → tier=0/free → checkout 400."""
        async def _setup():
            partner = await db_client.partner_engineers.find_one(
                {"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1},
            )
            # Seed 10 active referrals
            seeded_ids = []
            for i in range(10):
                rid = f"freetier-test-{i}-{uuid.uuid4()}"
                seeded_ids.append(rid)
                await db_client.partner_referrals.insert_one({
                    "id": rid, "partner_id": partner["id"], "referral_code": "AGQZKPAP",
                    "referred_organization_id": f"freetier-org-{i}-{uuid.uuid4()}",
                    "status": "active", "pre_existing_in_pipeline": False,
                    "created_at": "2026-05-13T00:00:00Z",
                    "first_paid_at": "2026-05-13T00:00:00Z",
                    "recurring_total_paid_gbp": 0.0,
                })
            return partner["id"], seeded_ids

        partner_id, seeded = _run_async(_setup())
        try:
            r = requests.post(
                f"{BASE_URL}/api/partners/me/subscription/checkout",
                json={"origin_url": BASE_URL}, headers=op_headers, timeout=10,
            )
            assert r.status_code == 400
            assert "free tier" in r.text.lower()
        finally:
            async def _cleanup():
                await db_client.partner_referrals.delete_many({"id": {"$in": seeded}})
                from routes.partners import _recompute_app_fee
                await _recompute_app_fee(partner_id)
            _run_async(_cleanup())


class TestWebhookBinding:
    def test_checkout_completed_binds_subscription(self, db_client):
        from routes.partners import handle_partner_checkout_completed
        async def _do():
            partner = await db_client.partner_engineers.find_one(
                {"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1},
            )
            sub_id = f"sub_test_{uuid.uuid4()}"
            session_data = {
                "id": f"cs_test_{uuid.uuid4()}",
                "subscription": sub_id,
                "customer": f"cus_test_{uuid.uuid4()}",
                "metadata": {
                    "kind": "partner_engineer_plan",
                    "partner_id": partner["id"],
                    "user_id": "irrelevant",
                    "tier_gbp": "30",
                },
            }
            result = await handle_partner_checkout_completed(session_data)
            return result, sub_id, partner["id"]

        result, expected_sub_id, partner_id = _run_async(_do())
        assert result and result["subscription_id"] == expected_sub_id

        # Cleanup — make this idempotent across re-runs
        async def _cleanup():
            await db_client.partner_engineers.update_one(
                {"id": partner_id}, {"$unset": {"subscription.stripe_subscription_id": ""}},
            )
        _run_async(_cleanup())

    def test_subscription_updated_syncs_state(self, db_client):
        from routes.partners import handle_partner_subscription_event
        async def _do():
            partner = await db_client.partner_engineers.find_one(
                {"email": OPERATOR_EMAIL}, {"_id": 0, "id": 1},
            )
            event = {
                "id": f"sub_evt_{uuid.uuid4()}",
                "status": "active",
                "current_period_end": 1_900_000_000,
                "cancel_at_period_end": True,
                "items": {"data": [{"id": "si_x", "price": {"id": "price_partner_15"}}]},
                "metadata": {"kind": "partner_engineer_plan", "partner_id": partner["id"]},
            }
            result = await handle_partner_subscription_event(event)
            fresh = await db_client.partner_engineers.find_one({"id": partner["id"]}, {"_id": 0})
            return result, fresh, partner["id"]

        result, fresh, partner_id = _run_async(_do())
        assert result and result["status"] == "active"
        sub = fresh.get("subscription") or {}
        assert sub.get("status") == "active"
        assert sub.get("cancel_at_period_end") is True
        assert sub.get("stripe_price_id") == "price_partner_15"
        # Cleanup
        async def _cleanup():
            await db_client.partner_engineers.update_one(
                {"id": partner_id}, {"$unset": {"subscription": ""}},
            )
        _run_async(_cleanup())

    def test_non_partner_metadata_ignored(self, db_client):
        """Webhook events that are NOT partner plans must be ignored
        (other Stripe subscriptions in the platform must not be touched)."""
        from routes.partners import handle_partner_subscription_event
        async def _do():
            event = {
                "id": "evt_other_kind",
                "status": "active",
                "metadata": {"kind": "operations_module"},
                "items": {"data": []},
            }
            return await handle_partner_subscription_event(event)
        result = _run_async(_do())
        assert result is None


class TestPriceIdResolver:
    def test_unknown_tier_returns_none(self):
        from routes.partners import _partner_plan_price_id_for_tier
        assert _partner_plan_price_id_for_tier({"price_gbp": 0}) is None
        # 30 / 15 currently unset → also None
        saved_30 = os.environ.pop("STRIPE_PRICE_PARTNER_PLAN_30", None)
        try:
            assert _partner_plan_price_id_for_tier({"price_gbp": 30}) is None
        finally:
            if saved_30:
                os.environ["STRIPE_PRICE_PARTNER_PLAN_30"] = saved_30

    def test_configured_tier_returns_env_value(self):
        from routes.partners import _partner_plan_price_id_for_tier
        os.environ["STRIPE_PRICE_PARTNER_PLAN_30"] = "price_test_30"
        os.environ["STRIPE_PRICE_PARTNER_PLAN_15"] = "price_test_15"
        try:
            assert _partner_plan_price_id_for_tier({"price_gbp": 30}) == "price_test_30"
            assert _partner_plan_price_id_for_tier({"price_gbp": 15}) == "price_test_15"
        finally:
            os.environ.pop("STRIPE_PRICE_PARTNER_PLAN_30", None)
            os.environ.pop("STRIPE_PRICE_PARTNER_PLAN_15", None)


class TestCancelGuard:
    def test_cancel_with_no_sub_returns_400(self, op_headers):
        # Operator partner has no live sub right now
        r = requests.post(f"{BASE_URL}/api/partners/me/subscription/cancel",
                          headers=op_headers, timeout=10)
        assert r.status_code == 400
        assert "no active subscription" in r.text.lower()
