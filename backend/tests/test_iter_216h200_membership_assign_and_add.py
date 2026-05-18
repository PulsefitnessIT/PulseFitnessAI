"""Iter 216h200 — Craig's Memberships Add Member + Plan-assignment bugs.

Two related bugs reported on the Memberships console:

(A) Plan-column says "No plan" even though the member's activity log
    shows "Assigned plan 'Gym Membership'" 3 times. Root cause: clicking
    the assign button repeatedly created multiple rows with
    `status='pending_payment'` (recurring plan), and the list join only
    matched `active`/`frozen`. Fix: idempotent assign-plan + list now
    surfaces `pending_payment` rows with the right status pill.

(B) Add member form has no email validation, optional phone, no GDPR.
    Fix: backend POST /memberships/members now rejects invalid email,
    empty phone, empty emergency phone, and missing GDPR consent.

Run: pytest backend/tests/test_iter_216h200_membership_assign_and_add.py -q
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── (A) assign-plan idempotency ───────────────────────────────────────

def _build_fake_db_for_assign(*, member, plan, existing_mm=None):
    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=member)
    fake.members.update_one = AsyncMock()
    fake.membership_plans = MagicMock()
    fake.membership_plans.find_one = AsyncMock(return_value=plan)
    fake.member_memberships = MagicMock()
    fake.member_memberships.find_one = AsyncMock(return_value=existing_mm)
    fake.member_memberships.update_many = AsyncMock(
        return_value=MagicMock(modified_count=0),
    )
    fake.member_memberships.insert_one = AsyncMock()
    return fake


def test_assign_plan_is_idempotent_on_same_plan() -> None:
    """Clicking 'Assign plan' twice with the same plan_id must NOT
    create a duplicate row — return the existing one instead."""
    from routes.memberships import members as mm_routes

    member = {"id": "m1", "organization_id": "org-1"}
    plan = {"id": "plan-A", "organization_id": "org-1", "kind": "recurring",
            "name": "Gym Membership"}
    existing = {"id": "mm-1", "member_id": "m1", "plan_id": "plan-A",
                "status": "pending_payment"}
    fake = _build_fake_db_for_assign(member=member, plan=plan, existing_mm=existing)

    async def _stub_require_operator_org(u): return "org-1"
    async def _stub_load_member(mid, org): return member

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)), \
         patch.object(mm_routes, "_load_member",
                      new=AsyncMock(side_effect=_stub_load_member)):
        result = _run(mm_routes.members_assign_plan(
            "m1", body={"plan_id": "plan-A"},
            user={"id": "u1", "organization_id": "org-1"},
        ))

    assert result.get("idempotent") is True
    assert result["membership"]["id"] == "mm-1"
    # No new row inserted, no retire query run.
    fake.member_memberships.insert_one.assert_not_called()
    fake.member_memberships.update_many.assert_not_called()


def test_assign_plan_creates_row_when_no_open_membership() -> None:
    from routes.memberships import members as mm_routes

    member = {"id": "m1", "organization_id": "org-1"}
    plan = {"id": "plan-A", "organization_id": "org-1", "kind": "recurring",
            "name": "Gym Membership"}
    fake = _build_fake_db_for_assign(member=member, plan=plan, existing_mm=None)

    async def _stub_require_operator_org(u): return "org-1"
    async def _stub_load_member(mid, org): return member

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)), \
         patch.object(mm_routes, "_load_member",
                      new=AsyncMock(side_effect=_stub_load_member)):
        _run(mm_routes.members_assign_plan(
            "m1", body={"plan_id": "plan-A"},
            user={"id": "u1", "organization_id": "org-1"},
        ))

    # Should have retired existing (none matched → still called) AND inserted.
    fake.member_memberships.update_many.assert_called_once()
    fake.member_memberships.insert_one.assert_called_once()


def test_assign_plan_retires_pending_payment_rows_when_switching_plans() -> None:
    """Switching from plan-A → plan-B must retire the existing
    pending_payment row for plan-A (previously left orphan)."""
    from routes.memberships import members as mm_routes

    member = {"id": "m1", "organization_id": "org-1"}
    plan_b = {"id": "plan-B", "organization_id": "org-1", "kind": "fixed_term",
              "name": "Annual"}
    # find_one for THIS plan returns None (no existing row on plan-B).
    fake = _build_fake_db_for_assign(member=member, plan=plan_b, existing_mm=None)
    # The update_many will run with status: {"$in": ["active", "frozen", "pending_payment"]}

    async def _stub_require_operator_org(u): return "org-1"
    async def _stub_load_member(mid, org): return member

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)), \
         patch.object(mm_routes, "_load_member",
                      new=AsyncMock(side_effect=_stub_load_member)):
        _run(mm_routes.members_assign_plan(
            "m1", body={"plan_id": "plan-B"},
            user={"id": "u1", "organization_id": "org-1"},
        ))

    # Assert the retire query was called with pending_payment in the filter.
    call_args = fake.member_memberships.update_many.call_args
    filter_doc = call_args[0][0]
    assert "pending_payment" in filter_doc["status"]["$in"], \
        "assign-plan must retire pending_payment rows so they don't accumulate"


# ── (A2) members_list now includes pending_payment ────────────────────

def test_members_list_surfaces_pending_payment_in_active_membership() -> None:
    """Previously the list join filtered to active/frozen so a
    pending_payment member showed 'No plan'. Now they show the plan
    with a pending_payment status."""
    from routes.memberships import members as mm_routes

    def _async_find(rows):
        cur = MagicMock()
        cur.sort = lambda *_a, **_k: cur
        cur.limit = lambda *_a, **_k: cur
        cur.to_list = AsyncMock(return_value=rows or [])
        return cur

    members_rows = [{"id": "m1", "organization_id": "org-1",
                     "first_name": "Keir", "last_name": "Burnham",
                     "email": "keir@example.com", "status": "active"}]
    mm_rows = [{"member_id": "m1", "plan_id": "plan-A",
                "status": "pending_payment", "credits_remaining": 0}]
    plan_rows = [{"id": "plan-A", "name": "Gym Membership", "kind": "recurring",
                  "colour": "#22d3ee"}]

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find = MagicMock(return_value=_async_find(members_rows))
    fake.member_memberships = MagicMock()
    fake.member_memberships.find = MagicMock(return_value=_async_find(mm_rows))
    fake.membership_plans = MagicMock()
    fake.membership_plans.find = MagicMock(return_value=_async_find(plan_rows))

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        result = _run(mm_routes.members_list(
            user={"id": "u1", "organization_id": "org-1"},
        ))

    members = result["members"]
    assert len(members) == 1
    assert members[0]["active_membership"]["status"] == "pending_payment"
    assert members[0]["active_membership"]["plan"]["name"] == "Gym Membership"


def test_members_list_prefers_active_over_pending_when_both_exist() -> None:
    """If a member has 1 active + 3 pending_payment rows (Craig's case),
    the list must surface the ACTIVE one, not whichever Mongo happens
    to return last."""
    from routes.memberships import members as mm_routes

    def _async_find(rows):
        cur = MagicMock()
        cur.sort = lambda *_a, **_k: cur
        cur.limit = lambda *_a, **_k: cur
        cur.to_list = AsyncMock(return_value=rows or [])
        return cur

    members_rows = [{"id": "m1", "organization_id": "org-1",
                     "first_name": "Keir", "last_name": "Burnham",
                     "status": "active"}]
    # Mongo could return these in any order — the prioritisation has to
    # pick active.
    mm_rows = [
        {"member_id": "m1", "plan_id": "plan-A", "status": "pending_payment"},
        {"member_id": "m1", "plan_id": "plan-A", "status": "pending_payment"},
        {"member_id": "m1", "plan_id": "plan-A", "status": "active"},
        {"member_id": "m1", "plan_id": "plan-A", "status": "pending_payment"},
    ]
    plan_rows = [{"id": "plan-A", "name": "Gym Membership", "kind": "recurring"}]

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find = MagicMock(return_value=_async_find(members_rows))
    fake.member_memberships = MagicMock()
    fake.member_memberships.find = MagicMock(return_value=_async_find(mm_rows))
    fake.membership_plans = MagicMock()
    fake.membership_plans.find = MagicMock(return_value=_async_find(plan_rows))

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        result = _run(mm_routes.members_list(
            user={"id": "u1", "organization_id": "org-1"},
        ))

    assert result["members"][0]["active_membership"]["status"] == "active"


# ── (B) members_create validation ─────────────────────────────────────

def _build_fake_db_for_create(*, existing_email=False):
    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(
        return_value={"id": "x"} if existing_email else None,
    )
    fake.members.insert_one = AsyncMock()
    fake.qr_rotation_secret = MagicMock()
    fake.qr_rotation_secret.insert_one = AsyncMock()
    return fake


def _make_valid_body():
    return {
        "first_name": "Keir",
        "email": "keir@example.com",
        "phone": "07700900000",
        "emergency_contact_phone": "07700900111",
        "gdpr_consent": True,
        "marketing_consent": False,
    }


def _patch_create_deps(monkeypatch_target):
    """Patch the dependencies used by members_create in one block."""
    async def _stub_require_operator_org(u): return "org-1"
    return [
        patch.object(monkeypatch_target, "_require_operator_org",
                     new=AsyncMock(side_effect=_stub_require_operator_org)),
    ]


def test_create_member_rejects_invalid_email() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    body["email"] = "not-an-email"

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(mm_routes.members_create(
                body=body, user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400
        assert "email" in str(exc.value.detail).lower()


def test_create_member_rejects_empty_phone() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    body["phone"] = "  "

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(mm_routes.members_create(
                body=body, user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400
        assert "phone" in str(exc.value.detail).lower()


def test_create_member_rejects_empty_emergency_phone() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    body["emergency_contact_phone"] = ""

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(mm_routes.members_create(
                body=body, user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400
        assert "emergency" in str(exc.value.detail).lower()


def test_create_member_rejects_missing_gdpr_consent() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    body["gdpr_consent"] = False

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(mm_routes.members_create(
                body=body, user={"id": "u1", "organization_id": "org-1"},
            ))
        assert exc.value.status_code == 400
        assert "gdpr" in str(exc.value.detail).lower() or "consent" in str(exc.value.detail).lower()


def test_create_member_happy_path_persists_consent_and_uppercases_postcode() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    body["postcode"] = "sw1a 1aa"
    body["marketing_consent"] = True

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        _run(mm_routes.members_create(
            body=body, user={"id": "u1", "organization_id": "org-1"},
        ))

    # Inspect the inserted document.
    insert_args = fake.members.insert_one.call_args
    doc = insert_args[0][0]
    assert doc["gdpr_consent"] is True
    assert doc["gdpr_consent_at"] is not None
    assert doc["marketing_consent"] is True
    assert doc["marketing_consent_at"] is not None
    assert doc["postcode"] == "SW1A 1AA", "postcode must be uppercased"
    assert doc["phone"] == "07700900000"
    assert doc["emergency_contact_phone"] == "07700900111"


def test_create_member_marketing_consent_defaults_false_when_omitted() -> None:
    from routes.memberships import members as mm_routes

    fake = _build_fake_db_for_create()
    body = _make_valid_body()
    # marketing_consent intentionally omitted from body.
    body.pop("marketing_consent", None)

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(mm_routes, "db", fake), \
         patch.object(mm_routes, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        _run(mm_routes.members_create(
            body=body, user={"id": "u1", "organization_id": "org-1"},
        ))

    doc = fake.members.insert_one.call_args[0][0]
    assert doc["marketing_consent"] is False, "must default to False, NEVER True"
    assert doc["marketing_consent_at"] is None
