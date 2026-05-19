"""Iter 216h216 — Module-aware activation timeline.

Craig's audit: "why do I need to add equipment if I chose the
Memberships module?" The activation checklist now filters to the
modules the org has switched on. Operations-only orgs lose
"First class scheduled", Memberships-only orgs lose "Add equipment".

Run: pytest backend/tests/test_iter_216h216_activation_module_filter.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_db(activation_rows=None, org=None):
    fake = MagicMock()
    fake.activation_events = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=activation_rows or [])
    fake.activation_events.find.return_value = cursor
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value=org)
    return fake


def test_memberships_only_org_hides_equipment_milestone():
    from routes import activation_events as ae

    user = {
        "id": "u1", "organization_id": "org-1",
        "module_access": {"memberships": True, "operations": False},
        "account_type": "lite",
    }
    fake = _fake_db()
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    assert "first_member_added" in event_types
    assert "first_booking_taken" in event_types
    assert "first_class_scheduled" in event_types
    # Operations-only milestone hidden
    assert "first_equipment_added" not in event_types
    # Universal milestones still present
    assert "first_login" in event_types
    assert "module_activated" in event_types
    assert out["total"] == len(event_types)


def test_operations_only_org_hides_memberships_milestones():
    from routes import activation_events as ae

    user = {
        "id": "u1", "organization_id": "org-1",
        "module_access": {"operations": True, "memberships": False},
        "account_type": "lite",
    }
    fake = _fake_db()
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    assert "first_equipment_added" in event_types
    # All memberships-only milestones hidden
    assert "first_member_added" not in event_types
    assert "first_booking_taken" not in event_types
    assert "first_invoice_generated" not in event_types
    assert "first_class_scheduled" not in event_types


def test_full_account_type_sees_every_milestone():
    """`account_type=full` implies all four modules (operations,
    memberships, CRM, marketing) — must show every milestone across
    every module, plus the three universal events.

    Iter 216h227 — the milestone set grew when CRM / Marketing trials
    got dedicated first-win events. Update expectation accordingly.
    """
    from routes import activation_events as ae

    user = {
        "id": "u1", "organization_id": "org-1",
        "module_access": {},  # empty cache — account_type should still imply
        "account_type": "full",
    }
    fake = _fake_db()
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    assert event_types == {
        # Universal
        "first_login", "first_staff_invited", "module_activated",
        # Operations
        "first_equipment_added", "first_fault_logged",
        # Memberships
        "first_member_added", "first_booking_taken",
        "first_invoice_generated", "first_class_scheduled",
        # CRM
        "first_lead_added", "first_deal_created", "first_quote_sent",
        # Marketing
        "first_brand_discovered", "first_audience_built", "first_campaign_launched",
    }


def test_legacy_user_with_no_module_data_sees_ops_plus_memberships():
    """Fallback path: no module_access cached AND org doc has no modules
    → show the historical core checklist (universal + ops + memberships).

    Iter 216h227 — previously this returned EVERY event; that leaked
    Marketing/CRM milestones to legacy operators who couldn't reach
    them. The legacy fallback now matches what the checklist looked
    like before CRM/Marketing events existed.
    """
    from routes import activation_events as ae

    user = {
        "id": "u1", "organization_id": "org-1",
        "account_type": "lite",
        # No module_access at all.
    }
    fake = _fake_db(org={})  # org doc returns no modules either
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    assert "first_equipment_added" in event_types
    assert "first_member_added" in event_types
    # CRM / Marketing events must NOT leak into a legacy view.
    assert "first_lead_added" not in event_types
    assert "first_campaign_launched" not in event_types
    # 3 universal + 2 ops + 4 memberships = 9
    assert out["total"] == 9


def test_no_org_returns_empty_timeline():
    """Master admins without an organization_id get an empty timeline."""
    from routes import activation_events as ae

    fake = _fake_db()
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user={"id": "u1"}))

    assert out["timeline"] == []
    assert out["fired_count"] == 0
