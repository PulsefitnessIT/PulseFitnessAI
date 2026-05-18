"""Iter 216h202 — Buy-credits feature (member self-serve class packs).

Backend coverage:
  (A) GET /api/member/credit-packs — surface every active class_pack
      plan for the member's org. Hide packs that have
      visible_for_self_purchase=False.
  (B) POST /api/member/credit-pack-checkout — read price from the
      server's plan (NEVER trust the frontend) and build a Stripe
      Checkout session with metadata.gymaxis_kind='credit_pack'.
  (C) complete_credit_pack_purchase webhook handler — idempotent on
      session_id; either tops up an existing active pack OR creates a
      fresh `member_memberships` row with credits_remaining and
      credits_expires_at.

Run: pytest backend/tests/test_iter_216h202_credit_packs.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── GET /api/member/credit-packs ──────────────────────────────────────

def _async_find(rows):
    cur = MagicMock()
    cur.sort = lambda *_a, **_k: cur
    cur.to_list = AsyncMock(return_value=rows or [])

    async def _aiter():
        for r in rows or []:
            yield r
    cur.__aiter__ = lambda self=cur: _aiter()
    return cur


def _fake_db_for_list(packs):
    fake = MagicMock()
    fake.membership_plans = MagicMock()
    fake.membership_plans.find = MagicMock(return_value=_async_find(packs))
    return fake


def test_list_credit_packs_returns_only_active_class_packs() -> None:
    from routes.memberships import credit_packs as cp

    packs = [
        {"id": "p1", "name": "5-class pack", "price_pence": 5000,
         "credits_count": 5, "pack_expiry_days": 90, "kind": "class_pack",
         "status": "active"},
        {"id": "p2", "name": "10-class pack", "price_pence": 9000,
         "credits_count": 10, "kind": "class_pack", "status": "active"},
    ]
    fake = _fake_db_for_list(packs)

    async def _stub_req_member(req): return {"id": "m1", "organization_id": "org-1"}

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_current_member",
                      new=AsyncMock(side_effect=_stub_req_member)):
        result = _run(cp.list_credit_packs(request=MagicMock()))

    assert result["currency"] == "gbp"
    assert len(result["packs"]) == 2
    p1 = result["packs"][0]
    assert p1["id"] == "p1"
    assert p1["credits_count"] == 5
    assert p1["value_per_credit_pence"] == 1000  # 5000 / 5


def test_list_credit_packs_with_no_org_returns_empty() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_list([])

    async def _stub_req_member(req): return {"id": "m1"}  # no organization_id

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_current_member",
                      new=AsyncMock(side_effect=_stub_req_member)):
        result = _run(cp.list_credit_packs(request=MagicMock()))

    assert result["packs"] == []


# ── POST /api/member/credit-pack-checkout ─────────────────────────────

def _fake_db_for_checkout(plan):
    fake = MagicMock()
    fake.membership_plans = MagicMock()
    fake.membership_plans.find_one = AsyncMock(return_value=plan)
    fake.payment_transactions = MagicMock()
    fake.payment_transactions.insert_one = AsyncMock()
    return fake


def test_checkout_404_when_plan_missing() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_checkout(None)

    async def _stub_req_member(req): return {"id": "m1", "organization_id": "org-1"}
    async def _stub_rate_limit(*a, **kw): return None

    with patch.object(cp, "db", fake), \
         patch.object(cp, "STRIPE_API_KEY", "sk_test_x"), \
         patch.object(cp, "_require_current_member",
                      new=AsyncMock(side_effect=_stub_req_member)), \
         patch("utils.security_plus.rate_limit_async",
               new=AsyncMock(side_effect=_stub_rate_limit)):
        body = cp.PackCheckoutIn(plan_id="ghost")
        with pytest.raises(HTTPException) as exc:
            _run(cp.create_credit_pack_checkout(request=MagicMock(), body=body))
        assert exc.value.status_code == 404


def test_checkout_400_when_pack_has_no_price() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_checkout({"id": "p1", "name": "Broken",
                                   "price_pence": 0, "credits_count": 5,
                                   "kind": "class_pack", "status": "active"})

    async def _stub_req_member(req): return {"id": "m1", "organization_id": "org-1"}
    async def _stub_rate_limit(*a, **kw): return None

    with patch.object(cp, "db", fake), \
         patch.object(cp, "STRIPE_API_KEY", "sk_test_x"), \
         patch.object(cp, "_require_current_member",
                      new=AsyncMock(side_effect=_stub_req_member)), \
         patch("utils.security_plus.rate_limit_async",
               new=AsyncMock(side_effect=_stub_rate_limit)):
        body = cp.PackCheckoutIn(plan_id="p1")
        with pytest.raises(HTTPException) as exc:
            _run(cp.create_credit_pack_checkout(request=MagicMock(), body=body))
        assert exc.value.status_code == 400


def test_checkout_503_when_stripe_not_configured() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_checkout({"id": "p1", "name": "5pk", "price_pence": 5000,
                                   "credits_count": 5})

    async def _stub_req_member(req): return {"id": "m1", "organization_id": "org-1"}

    with patch.object(cp, "db", fake), \
         patch.object(cp, "STRIPE_API_KEY", ""):
        body = cp.PackCheckoutIn(plan_id="p1")
        with pytest.raises(HTTPException) as exc:
            _run(cp.create_credit_pack_checkout(request=MagicMock(), body=body))
        assert exc.value.status_code == 503


def test_checkout_happy_path_creates_session_and_pending_txn() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_checkout({
        "id": "p1", "name": "5-class pack", "price_pence": 5000,
        "credits_count": 5, "pack_expiry_days": 90,
        "kind": "class_pack", "status": "active",
    })

    async def _stub_req_member(req): return {"id": "m1", "organization_id": "org-1",
                                              "email": "m@x.com"}
    async def _stub_rate_limit(*a, **kw): return None

    fake_session = MagicMock(url="https://checkout.stripe.test/s/abc",
                              id="cs_test_abc")

    with patch.object(cp, "db", fake), \
         patch.object(cp, "STRIPE_API_KEY", "sk_test_x"), \
         patch.object(cp, "_require_current_member",
                      new=AsyncMock(side_effect=_stub_req_member)), \
         patch("utils.security_plus.rate_limit_async",
               new=AsyncMock(side_effect=_stub_rate_limit)), \
         patch("stripe.checkout.Session.create", return_value=fake_session):
        body = cp.PackCheckoutIn(plan_id="p1")
        result = _run(cp.create_credit_pack_checkout(request=MagicMock(), body=body))

    assert result["checkout_url"] == "https://checkout.stripe.test/s/abc"
    assert result["session_id"] == "cs_test_abc"
    fake.payment_transactions.insert_one.assert_called_once()
    txn = fake.payment_transactions.insert_one.call_args[0][0]
    assert txn["kind"] == "credit_pack"
    assert txn["status"] == "pending"
    assert txn["amount_pence"] == 5000
    assert txn["plan_id"] == "p1"


# ── Webhook completion: complete_credit_pack_purchase ─────────────────

def _fake_db_for_webhook(*, existing_mm=None, plan=None,
                          dedup_match=None):
    fake = MagicMock()
    fake.member_memberships = MagicMock()
    fake.member_memberships.find_one = AsyncMock(
        side_effect=[dedup_match, existing_mm],
    )
    fake.member_memberships.insert_one = AsyncMock()
    fake.member_memberships.update_one = AsyncMock()
    fake.membership_plans = MagicMock()
    fake.membership_plans.find_one = AsyncMock(return_value=plan)
    fake.payment_transactions = MagicMock()
    fake.payment_transactions.update_one = AsyncMock()
    return fake


def test_webhook_creates_new_pack_membership_when_none_exists() -> None:
    from routes.memberships import credit_packs as cp

    plan = {"id": "p1", "name": "5pk", "credits_count": 5, "pack_expiry_days": 90}
    fake = _fake_db_for_webhook(existing_mm=None, plan=plan)

    meta = {"gymaxis_kind": "credit_pack",
            "gymaxis_member_id": "m1",
            "gymaxis_org_id": "org-1",
            "gymaxis_plan_id": "p1"}
    session = MagicMock(id="cs_test_abc")

    with patch.object(cp, "db", fake):
        _run(cp.complete_credit_pack_purchase(meta, session))

    fake.member_memberships.insert_one.assert_called_once()
    doc = fake.member_memberships.insert_one.call_args[0][0]
    assert doc["member_id"] == "m1"
    assert doc["plan_id"] == "p1"
    assert doc["credits_remaining"] == 5
    assert doc["status"] == "active"
    assert doc["stripe_session_id"] == "cs_test_abc"
    assert doc["credits_expires_at"] is not None  # 90 days set
    fake.payment_transactions.update_one.assert_called_once()


def test_webhook_tops_up_existing_pack_when_same_plan_active() -> None:
    from routes.memberships import credit_packs as cp

    plan = {"id": "p1", "name": "5pk", "credits_count": 5, "pack_expiry_days": 90}
    existing_mm = {"id": "mm-1", "credits_remaining": 3, "plan_id": "p1",
                    "status": "active"}
    fake = _fake_db_for_webhook(existing_mm=existing_mm, plan=plan)

    meta = {"gymaxis_kind": "credit_pack",
            "gymaxis_member_id": "m1",
            "gymaxis_org_id": "org-1",
            "gymaxis_plan_id": "p1"}
    session = MagicMock(id="cs_test_xyz")

    with patch.object(cp, "db", fake):
        _run(cp.complete_credit_pack_purchase(meta, session))

    fake.member_memberships.insert_one.assert_not_called()
    fake.member_memberships.update_one.assert_called_once()
    update = fake.member_memberships.update_one.call_args[0][1]
    assert update["$set"]["credits_remaining"] == 8, "3 existing + 5 new"
    assert update["$set"]["stripe_session_id"] == "cs_test_xyz"


def test_webhook_is_idempotent_on_session_id() -> None:
    """If we've already processed this session_id, do nothing."""
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_webhook(
        existing_mm=None,
        plan={"id": "p1", "credits_count": 5},
        dedup_match={"id": "mm-existing"},  # first find_one returns hit
    )

    meta = {"gymaxis_kind": "credit_pack",
            "gymaxis_member_id": "m1",
            "gymaxis_plan_id": "p1"}
    session = MagicMock(id="cs_test_dupe")

    with patch.object(cp, "db", fake):
        _run(cp.complete_credit_pack_purchase(meta, session))

    fake.member_memberships.insert_one.assert_not_called()
    fake.member_memberships.update_one.assert_not_called()


def test_webhook_skips_when_meta_missing_required_fields() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_webhook(existing_mm=None, plan=None)

    # missing plan_id
    meta = {"gymaxis_kind": "credit_pack", "gymaxis_member_id": "m1"}
    session = MagicMock(id="cs_test_noplan")

    with patch.object(cp, "db", fake):
        _run(cp.complete_credit_pack_purchase(meta, session))

    fake.member_memberships.insert_one.assert_not_called()


def test_webhook_skips_when_plan_lookup_fails() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db_for_webhook(existing_mm=None, plan=None)

    meta = {"gymaxis_kind": "credit_pack",
            "gymaxis_member_id": "m1",
            "gymaxis_plan_id": "p1"}
    session = MagicMock(id="cs_test_ghostplan")

    with patch.object(cp, "db", fake):
        _run(cp.complete_credit_pack_purchase(meta, session))

    fake.member_memberships.insert_one.assert_not_called()
