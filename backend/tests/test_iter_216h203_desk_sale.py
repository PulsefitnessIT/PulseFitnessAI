"""Iter 216h203 — Operator desk-sale "Sold a pack at the desk".

Backend coverage for POST /api/memberships/members/{member_id}/sell-pack-at-desk.

Key invariants under test:
  (1) Only class_pack plans accepted (subscription plans are rejected
      with a clear error so the operator picks the right tool).
  (2) Existing recurring/active memberships are NEVER retired — packs
      coexist with subscriptions. This is the headline differentiator
      vs the legacy record_payment endpoint.
  (3) If the member already has an active pack on the SAME plan, the
      endpoint TOPS UP credits_remaining rather than spawning a
      duplicate row.
  (4) payment_transactions ledger row is written (mode='manual',
      kind='credit_pack_desk', status='complete').
  (5) lifetime_value_pence is bumped (except for comp sales).
  (6) Payment method is whitelisted: cash / card_terminal /
      bank_transfer / comp / other.

Run: pytest backend/tests/test_iter_216h203_desk_sale.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_db(*, member=None, plan=None, existing_mm=None, org_currency="GBP"):
    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=member)
    fake.members.update_one = AsyncMock()
    fake.membership_plans = MagicMock()
    fake.membership_plans.find_one = AsyncMock(return_value=plan)
    fake.member_memberships = MagicMock()
    fake.member_memberships.find_one = AsyncMock(return_value=existing_mm)
    fake.member_memberships.insert_one = AsyncMock()
    fake.member_memberships.update_one = AsyncMock()
    fake.payment_transactions = MagicMock()
    fake.payment_transactions.insert_one = AsyncMock()
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(
        return_value={"currency": org_currency} if org_currency else None,
    )
    return fake


def _body(**overrides):
    from routes.memberships.credit_packs import DeskSaleBody
    defaults = {"plan_id": "p1", "method": "cash"}
    defaults.update(overrides)
    return DeskSaleBody(**defaults)


# ── Validation: rejects non-class_pack plans ──────────────────────────

def test_rejects_subscription_plan() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "recurring", "credits_count": 0,
              "price_pence": 5000},
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        with pytest.raises(HTTPException) as exc:
            _run(cp.sell_pack_at_desk(
                member_id="m1", body=_body(),
                user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400
        assert "class pack" in str(exc.value.detail).lower()


def test_rejects_unknown_method() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db()

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        with pytest.raises(HTTPException) as exc:
            _run(cp.sell_pack_at_desk(
                member_id="m1", body=_body(method="bitcoin"),
                user={"id": "u1"},
            ))
        assert exc.value.status_code == 400


def test_404_when_member_not_found() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(member=None)

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        with pytest.raises(HTTPException) as exc:
            _run(cp.sell_pack_at_desk(
                member_id="ghost", body=_body(),
                user={"id": "u1"},
            ))
        assert exc.value.status_code == 404
        assert "member" in str(exc.value.detail).lower()


def test_404_when_plan_not_found() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan=None,
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        with pytest.raises(HTTPException) as exc:
            _run(cp.sell_pack_at_desk(
                member_id="m1", body=_body(),
                user={"id": "u1"},
            ))
        assert exc.value.status_code == 404
        assert "plan" in str(exc.value.detail).lower()


def test_400_when_pack_has_no_credits_configured() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "class_pack", "credits_count": 0,
              "price_pence": 5000},
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        with pytest.raises(HTTPException) as exc:
            _run(cp.sell_pack_at_desk(
                member_id="m1", body=_body(),
                user={"id": "u1"},
            ))
        assert exc.value.status_code == 400


# ── Happy path: new pack ──────────────────────────────────────────────

def test_creates_new_pack_when_none_exists_and_records_ledger() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "class_pack", "credits_count": 5,
              "pack_expiry_days": 90, "price_pence": 5000,
              "name": "5pk"},
        existing_mm=None,
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        result = _run(cp.sell_pack_at_desk(
            member_id="m1", body=_body(method="cash"),
            user={"id": "u1"},
        ))

    assert result["ok"] is True
    assert result["topped_up"] is False
    assert result["credits_added"] == 5
    assert result["amount_pence"] == 5000

    fake.member_memberships.insert_one.assert_called_once()
    mm_doc = fake.member_memberships.insert_one.call_args[0][0]
    assert mm_doc["credits_remaining"] == 5
    assert mm_doc["status"] == "active"
    assert mm_doc["purchased_via"] == "desk_sale"
    assert mm_doc["desk_sale_method"] == "cash"
    assert mm_doc["credits_expires_at"] is not None

    fake.payment_transactions.insert_one.assert_called_once()
    txn = fake.payment_transactions.insert_one.call_args[0][0]
    assert txn["kind"] == "credit_pack_desk"
    assert txn["mode"] == "manual"
    assert txn["status"] == "complete"
    assert txn["method"] == "cash"
    assert txn["amount_pence"] == 5000
    assert txn["currency"] == "GBP"

    fake.members.update_one.assert_called_once()
    inc = fake.members.update_one.call_args[0][1]
    assert inc["$inc"]["lifetime_value_pence"] == 5000


# ── Happy path: top-up ────────────────────────────────────────────────

def test_tops_up_existing_pack_on_same_plan() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "class_pack", "credits_count": 5,
              "price_pence": 5000},
        existing_mm={"id": "mm-1", "credits_remaining": 2,
                     "plan_id": "p1", "status": "active"},
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        result = _run(cp.sell_pack_at_desk(
            member_id="m1", body=_body(method="card_terminal"),
            user={"id": "u1"},
        ))

    assert result["topped_up"] is True
    assert result["credits_added"] == 5
    fake.member_memberships.insert_one.assert_not_called()
    fake.member_memberships.update_one.assert_called_once()
    upd = fake.member_memberships.update_one.call_args[0][1]
    assert upd["$set"]["credits_remaining"] == 7  # 2 + 5
    assert upd["$set"]["last_topup_method"] == "card_terminal"


# ── Comp sale: amount is 0 and lifetime value is NOT bumped ──────────

def test_comp_sale_records_zero_amount_and_skips_ltv() -> None:
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "class_pack", "credits_count": 5,
              "price_pence": 5000},
        existing_mm=None,
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        result = _run(cp.sell_pack_at_desk(
            member_id="m1", body=_body(method="comp", note="Birthday gift"),
            user={"id": "u1"},
        ))

    assert result["amount_pence"] == 0
    txn = fake.payment_transactions.insert_one.call_args[0][0]
    assert txn["amount_pence"] == 0
    assert txn["payment_status"] == "comp"
    # No LTV bump for comp sales.
    fake.members.update_one.assert_not_called()


# ── Coexistence: existing subscription is NOT retired ─────────────────

def test_does_not_retire_existing_subscription() -> None:
    """The big diff vs legacy record_payment: a member on Gold should
    keep their subscription when they buy a 5-pack at the desk."""
    from routes.memberships import credit_packs as cp

    fake = _fake_db(
        member={"id": "m1", "organization_id": "org-1"},
        plan={"id": "p1", "organization_id": "org-1",
              "kind": "class_pack", "credits_count": 5,
              "price_pence": 5000},
        existing_mm=None,
    )
    # Add a sub-membership the endpoint should NOT touch.
    fake.member_memberships.update_many = AsyncMock(
        return_value=MagicMock(modified_count=0),
    )

    async def _stub_req_org(u): return "org-1"

    with patch.object(cp, "db", fake), \
         patch.object(cp, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_req_org)):
        _run(cp.sell_pack_at_desk(
            member_id="m1", body=_body(),
            user={"id": "u1"},
        ))

    # The endpoint must NEVER call update_many with a "retire all" filter.
    fake.member_memberships.update_many.assert_not_called()
