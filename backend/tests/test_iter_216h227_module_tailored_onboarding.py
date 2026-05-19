"""Iter 216h227 — module-tailored activation funnel + onboarding checklist.

Lee's audit (Feb 2026): "If a user signs up for marketing, why are we
asking them to add a machine? If a user signs up for operations, how
are they going to add a member?"

The fix narrows two surfaces to the operator's declared `primary_module`:

1. ``GET /api/activation/me`` — the "Your first wins" timeline.
2. ``GET /api/account/onboarding`` — the Account Settings → Onboarding
   "Setup checklist".

This test stubs the Motor client so each module's intent is exercised
in isolation without touching the live DB.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_activation_db(org=None):
    fake = MagicMock()
    fake.activation_events = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    fake.activation_events.find.return_value = cursor
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value=org)
    return fake


def _user_for(primary):
    """Synthetic owner of a trial org with all 4 modules unlocked and an
    optional primary_module intent set on the user row (mirrors the
    shape /auth/login caches)."""
    user = {
        "id": "u-test",
        "organization_id": "org-test",
        "email": "owner@example.com",
        "full_name": "Test Owner",
        "role": "owner",
        "is_trial": True,
        "module_access": {
            "operations": True, "memberships": True,
            "crm": True, "marketing": True,
        },
    }
    if primary:
        user["primary_module"] = primary
    return user


# ─── /activation/me — module intent filter ─────────────────────────


@pytest.mark.parametrize(
    ("primary", "must_have", "must_not_have"),
    [
        ("operations",
         {"first_equipment_added", "first_fault_logged", "first_login"},
         {"first_member_added", "first_lead_added", "first_campaign_launched"}),
        ("memberships",
         {"first_member_added", "first_booking_taken", "first_invoice_generated",
          "first_class_scheduled", "first_login"},
         {"first_equipment_added", "first_lead_added", "first_campaign_launched"}),
        ("crm",
         {"first_lead_added", "first_deal_created", "first_quote_sent", "first_login"},
         {"first_equipment_added", "first_member_added", "first_campaign_launched"}),
        ("marketing",
         {"first_brand_discovered", "first_audience_built",
          "first_campaign_launched", "first_login"},
         {"first_equipment_added", "first_member_added", "first_lead_added"}),
    ],
)
def test_activation_funnel_filters_by_primary_module(primary, must_have, must_not_have):
    from routes import activation_events as ae

    user = _user_for(primary)
    fake = _fake_activation_db()
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    assert must_have <= event_types, (
        f"[{primary}] expected {must_have} ⊆ {event_types}"
    )
    assert not (must_not_have & event_types), (
        f"[{primary}] unexpected events leaked: {must_not_have & event_types}"
    )
    # Universal events ALWAYS surface — they're the only milestones a
    # bare-minimum trial user can hit before module-specific actions.
    assert "first_login" in event_types
    assert "first_staff_invited" in event_types
    assert "module_activated" in event_types
    assert out["primary_module"] == primary


def test_activation_funnel_legacy_org_falls_back_to_ops_plus_memberships():
    """Orgs that pre-date the primary_module schema keep the historical
    core checklist (ops + memberships) — we never want a pre-existing
    operator to suddenly see Marketing / CRM events the day this ships."""
    from routes import activation_events as ae

    # No primary_module on user, no module_access, no enabled_modules.
    user = {
        "id": "u-legacy", "organization_id": "org-legacy",
        "email": "legacy@example.com", "role": "owner",
    }
    fake = _fake_activation_db(org={
        "id": "org-legacy", "modules": {}, "enabled_modules": [],
        "account_type": "", "primary_module": None,
    })
    with patch.object(ae, "db", fake):
        out = _run(ae.activation_for_me(user=user))

    event_types = {t["event_type"] for t in out["timeline"]}
    # Universal always present.
    assert {"first_login", "first_staff_invited", "module_activated"} <= event_types
    # Legacy fallback: only ops + memberships modules' events.
    assert "first_equipment_added" in event_types
    assert "first_member_added" in event_types
    # CRM + marketing events should NOT leak into a legacy view.
    assert "first_lead_added" not in event_types
    assert "first_campaign_launched" not in event_types


# ─── /account/onboarding — checklist step filter ───────────────────


def _fake_account_db(org=None, signals=None):
    """A more complete fake that satisfies _gather_onboarding_signals."""
    fake = MagicMock()
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value=org or {})
    # Site lookups
    fake.sites = MagicMock()
    fake.sites.count_documents = AsyncMock(return_value=0)
    fake.sites.find_one = AsyncMock(return_value=None)
    # Users / equipment / payments
    fake.users = MagicMock()
    fake.users.count_documents = AsyncMock(return_value=0)
    fake.equipment = MagicMock()
    fake.equipment.count_documents = AsyncMock(return_value=0)
    fake.payment_transactions = MagicMock()
    fake.payment_transactions.find_one = AsyncMock(return_value=None)
    # Apply signal overrides — used to flip individual flags True.
    for k, v in (signals or {}).items():
        getattr(fake, k).count_documents = AsyncMock(return_value=v)
    return fake


@pytest.mark.parametrize(
    ("primary", "must_have_step", "must_not_have_step"),
    [
        ("operations", "import_machines", None),
        ("marketing",  "site_details",    "import_machines"),
        ("crm",        "invite_staff",    "import_machines"),
        ("memberships", "connect_stripe", "import_machines"),
    ],
)
def test_onboarding_checklist_filters_by_primary_module(
    primary, must_have_step, must_not_have_step,
):
    from routes import account as account_mod

    user = _user_for(primary)
    fake = _fake_account_db(org={
        "id": "org-test", "primary_module": primary,
        "enabled_modules": ["operations", "memberships", "crm", "marketing"],
        "modules": {},
    })
    with patch.object(account_mod, "db", fake):
        out = _run(account_mod.onboarding_status(user=user))

    step_ids = {s["id"] for s in out["steps"]}
    assert must_have_step in step_ids, (
        f"[{primary}] expected '{must_have_step}' present, got {step_ids}"
    )
    if must_not_have_step:
        assert must_not_have_step not in step_ids, (
            f"[{primary}] '{must_not_have_step}' should be hidden, got {step_ids}"
        )
    # Universal "complete profile" is always there regardless of module.
    assert "complete_profile" in step_ids
    # And the percent helper survives module filtering.
    assert isinstance(out["percent"], int)
    assert 0 <= out["percent"] <= 100
