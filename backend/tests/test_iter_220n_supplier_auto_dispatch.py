"""Iter 220n — Auto-dispatch faults to the gym's primary service supplier.

The Partner Plan promise is "every gym you bring in is recurring revenue
AND recurring work". This iter delivers the second half:

  1. When a gym signs up with an engineer's referral code, the engineer
     is auto-added as the gym's primary `auto_dispatch=True` service
     supplier (with `partner_engineer_id` link + `is_primary_supplier=True`).
  2. When that gym logs a fault that's escalated to an engineer
     (`resolution_type='engineer'`), the fault is auto-dispatched to the
     primary supplier via the existing supplier-portal token flow.
  3. The gym keeps full agency — they can toggle off auto_dispatch,
     swap the primary, or add more suppliers via the Supplier Dashboard.

Idempotency invariants:
  * Supplier auto-attach is a no-op if a row already links partner to org.
  * Auto-dispatch is a no-op if a supplier_case already exists for the
    (issue_id, supplier_email) pair (covers batch flows + retries).

Anti-bug invariants:
  * Pulse orgs are explicitly skipped at referral time (programme is
    GymAxis-only), so no auto-supplier rows get created there.
  * In-house resolution faults (resolution_type != 'engineer') do NOT
    trigger dispatch — only escalations go to the engineer.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _run(coro):
    """Drive a coroutine synchronously, gracefully handling the
    Python 3.11 "no current event loop" edge case (see conftest
    `_ensure_event_loop` fixture for the full story)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Test 1 — supplier auto-attach on referral ───────────────────────


def test_attach_referral_creates_auto_dispatch_supplier():
    """When a non-Pulse org signs up with an engineer's referral code,
    a `suppliers` row is created with the right shape so faults can
    auto-route to that engineer from day one."""
    from routes.partners import attach_referral_to_org

    partner = {
        "id": "p_engineer_1",
        "referral_code": "ABC123",
        "status": "approved",
        "owner_organization_id": "p_org_1",
        "full_name": "Test Engineer",
        "email": "engineer@example.com",
        "phone": "+447700900111",
        "address": "1 High Street",
        "rates": {"callout_fee": 60, "labour_rate_per_hour": 55, "mileage_rate": 0.45,
                  "parts_markup_pct": 12},
    }

    inserted = {"partner_referrals": [], "suppliers": [], "audit": []}

    async def find_partner(*args, **kwargs):
        return partner

    async def find_org(*args, **kwargs):
        # First call: looking up referred_by_partner_id (returns None → free to attach)
        # Subsequent: skip — the auto-supplier path uses find_one too
        return None

    async def find_supplier(*args, **kwargs):
        return None  # no existing row → free to insert

    async def insert_referral(doc):
        inserted["partner_referrals"].append(doc)

    async def insert_supplier(doc):
        inserted["suppliers"].append(doc)

    async def update_org(*args, **kwargs):
        return None

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(side_effect=find_partner)
    fake_db.organizations.find_one = AsyncMock(side_effect=find_org)
    fake_db.organizations.update_one = AsyncMock(side_effect=update_org)
    fake_db.partner_referrals.insert_one = AsyncMock(side_effect=insert_referral)
    fake_db.suppliers.find_one = AsyncMock(side_effect=find_supplier)
    fake_db.suppliers.insert_one = AsyncMock(side_effect=insert_supplier)

    # The Pulse-org guard must report False so the referral isn't blocked.
    async def not_pulse(*args, **kwargs):
        return False

    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._is_pulse_org", side_effect=not_pulse), \
         patch("routes.partners._audit", new=AsyncMock(return_value=None)):
        res = _run(attach_referral_to_org(organization_id="org_gym_1", ref_code="ABC123"))

    assert res is not None, "Referral should attach for a non-Pulse org"
    assert inserted["partner_referrals"], "partner_referrals row must be inserted"
    assert inserted["suppliers"], "auto-supplier row must be inserted"

    s = inserted["suppliers"][0]
    assert s["organization_id"] == "org_gym_1"
    assert s["partner_engineer_id"] == "p_engineer_1"
    assert s["auto_dispatch"] is True
    assert s["is_primary_supplier"] is True
    assert s["auto_created_from_referral"] is True
    assert s["name"] == "Test Engineer"
    assert s["email"] == "engineer@example.com"
    assert "service_engineer" in s["supplier_types"]
    # Rates carried through from the partner profile
    assert s["callout_fee"] == 60
    assert s["labour_rate_per_hour"] == 55


def test_attach_referral_skips_supplier_when_already_linked():
    """A second activation of the same code for the same gym must NOT
    create a duplicate supplier row (idempotency)."""
    from routes.partners import attach_referral_to_org

    partner = {
        "id": "p_engineer_1",
        "referral_code": "ABC123",
        "status": "approved",
        "owner_organization_id": "p_org_1",
        "full_name": "Test Engineer",
        "email": "e@e.com",
    }
    inserted = {"suppliers": []}

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    # Org doc — first call returns None (no prior referral). After the
    # update, the referral_attributed audit runs; we don't care.
    fake_db.organizations.find_one = AsyncMock(return_value=None)
    fake_db.organizations.update_one = AsyncMock(return_value=None)
    fake_db.partner_referrals.insert_one = AsyncMock(return_value=None)
    # Existing supplier row → must skip the insert.
    fake_db.suppliers.find_one = AsyncMock(
        return_value={"id": "s_existing", "organization_id": "org_gym_1",
                      "partner_engineer_id": "p_engineer_1"},
    )
    fake_db.suppliers.insert_one = AsyncMock(
        side_effect=lambda doc: inserted["suppliers"].append(doc),
    )

    async def not_pulse(*args, **kwargs):
        return False

    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._is_pulse_org", side_effect=not_pulse), \
         patch("routes.partners._audit", new=AsyncMock(return_value=None)):
        _run(attach_referral_to_org(organization_id="org_gym_1", ref_code="ABC123"))

    assert inserted["suppliers"] == [], (
        "Auto-supplier insert must be skipped when one already links to this partner"
    )


# ── Test 2 — fault auto-dispatch to primary supplier ────────────────


def test_engineer_escalated_fault_dispatches_to_primary_supplier():
    """A fault with resolution_type='engineer' on a gym with an
    auto-dispatch supplier triggers create_supplier_case + tags the
    issue with auto_dispatched_supplier_id."""
    from routes.issues import _auto_dispatch_to_primary_supplier

    issue_doc = {
        "id": "issue_1",
        "organization_id": "org_gym_1",
        "resolution_type": "engineer",
    }

    supplier = {
        "id": "s_engineer_1",
        "name": "Test Engineer",
        "email": "engineer@example.com",
        "partner_engineer_id": "p_engineer_1",
    }

    created_supplier_cases = []
    issue_updates = []

    async def find_supplier(*args, **kwargs):
        return supplier

    async def find_issue_already(*args, **kwargs):
        return None  # no existing supplier_case → free to dispatch

    async def find_org(*args, **kwargs):
        return {"name": "Test Gym Ltd"}

    async def fake_create_supplier_case(*, issue_id, supplier_name, supplier_email,
                                         organization_name, base_url):
        created_supplier_cases.append({
            "issue_id": issue_id, "supplier_name": supplier_name,
            "supplier_email": supplier_email, "organization_name": organization_name,
        })
        return {"token": "tok_1", "url": "https://x.test/supplier/case/tok_1",
                "case_id": "sc_1"}

    async def update_issue(filt, upd):
        issue_updates.append({"filter": filt, "update": upd})

    fake_db = MagicMock()
    fake_db.suppliers.find_one = AsyncMock(side_effect=find_supplier)
    fake_db.supplier_cases.find_one = AsyncMock(side_effect=find_issue_already)
    fake_db.organizations.find_one = AsyncMock(side_effect=find_org)
    fake_db.issues.update_one = AsyncMock(side_effect=update_issue)

    with patch("routes.issues.db", fake_db), \
         patch("routes.supplier_portal.create_supplier_case",
               side_effect=fake_create_supplier_case):
        _run(_auto_dispatch_to_primary_supplier(issue_doc, user={"id": "u1"}))

    assert len(created_supplier_cases) == 1
    case = created_supplier_cases[0]
    assert case["issue_id"] == "issue_1"
    assert case["supplier_email"] == "engineer@example.com"
    assert case["organization_name"] == "Test Gym Ltd"

    assert len(issue_updates) == 1, "Issue must be stamped with dispatch metadata"
    set_doc = issue_updates[0]["update"]["$set"]
    assert set_doc["auto_dispatched_supplier_id"] == "s_engineer_1"
    assert set_doc["auto_dispatched_supplier_name"] == "Test Engineer"
    assert set_doc["auto_dispatched_partner_engineer_id"] == "p_engineer_1"
    assert "auto_dispatched_at" in set_doc


def test_in_house_resolution_does_not_trigger_dispatch():
    """Faults the gym intends to fix in-house (resolution_type != 'engineer')
    MUST NOT auto-dispatch — that's exactly the cohort the manager wants
    to handle without bothering the supplier."""
    from routes.issues import _auto_dispatch_to_primary_supplier

    issue_doc = {
        "id": "issue_in_house",
        "organization_id": "org_gym_1",
        "resolution_type": "in_house",  # ← the key bit
    }

    fake_db = MagicMock()
    fake_db.suppliers.find_one = AsyncMock(return_value={"id": "s_1", "email": "e@e.com"})
    fake_db.supplier_cases.find_one = AsyncMock(return_value=None)
    fake_db.organizations.find_one = AsyncMock(return_value={"name": "Gym"})
    fake_db.issues.update_one = AsyncMock(return_value=None)

    called = []

    async def fake_create(*args, **kwargs):
        called.append(1)
        return {"token": "x", "url": "x", "case_id": "x"}

    with patch("routes.issues.db", fake_db), \
         patch("routes.supplier_portal.create_supplier_case", side_effect=fake_create):
        _run(_auto_dispatch_to_primary_supplier(issue_doc, user={"id": "u1"}))

    assert called == [], "In-house faults must NEVER auto-dispatch"
    fake_db.suppliers.find_one.assert_not_called()


def test_no_dispatch_when_org_has_no_auto_dispatch_supplier():
    """A gym that hasn't onboarded an engineer (or has disabled
    auto_dispatch on the supplier row) must NOT have create_supplier_case
    called."""
    from routes.issues import _auto_dispatch_to_primary_supplier

    issue_doc = {
        "id": "issue_orphan",
        "organization_id": "org_no_engineer",
        "resolution_type": "engineer",
    }

    fake_db = MagicMock()
    fake_db.suppliers.find_one = AsyncMock(return_value=None)  # no supplier on file
    fake_db.supplier_cases.find_one = AsyncMock(return_value=None)
    fake_db.issues.update_one = AsyncMock(return_value=None)

    called = []

    async def fake_create(*args, **kwargs):
        called.append(1)
        return {}

    with patch("routes.issues.db", fake_db), \
         patch("routes.supplier_portal.create_supplier_case", side_effect=fake_create):
        _run(_auto_dispatch_to_primary_supplier(issue_doc, user={"id": "u1"}))

    assert called == [], "No supplier on file → no dispatch"
    # And NO issue tagging either (no point — there's nothing to tag).
    fake_db.issues.update_one.assert_not_called()


def test_idempotent_when_supplier_case_already_exists():
    """If a supplier_case already exists for this (issue, supplier),
    skip — guards against double-fire on batch flows + retries."""
    from routes.issues import _auto_dispatch_to_primary_supplier

    issue_doc = {
        "id": "issue_replay",
        "organization_id": "org_gym_1",
        "resolution_type": "engineer",
    }

    fake_db = MagicMock()
    fake_db.suppliers.find_one = AsyncMock(return_value={
        "id": "s_1", "name": "X", "email": "x@x.com",
    })
    fake_db.supplier_cases.find_one = AsyncMock(return_value={
        "id": "sc_existing", "issue_id": "issue_replay",
    })
    fake_db.issues.update_one = AsyncMock(return_value=None)

    called = []

    async def fake_create(*args, **kwargs):
        called.append(1)
        return {}

    with patch("routes.issues.db", fake_db), \
         patch("routes.supplier_portal.create_supplier_case", side_effect=fake_create):
        _run(_auto_dispatch_to_primary_supplier(issue_doc, user={"id": "u1"}))

    assert called == [], "Replay must be a no-op"


# ── Test 3 — UI brand-aware copy invariants ─────────────────────────


def test_pulse_score_card_imports_useauth_for_brand_switch():
    """The shared score card must read the active user's account_type
    to pick the right brand copy. We pin it at the source level so a
    future refactor that drops `useAuth` here can't silently revert the
    brand-aware label."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/components/PulseScoreCard.js").read_text()
    assert "useAuth" in src, "PulseScoreCard must read auth context for brand"
    assert "BRAND_COPY" in src, "Brand-copy constants must be present"
    assert "'Gym Health'" in src, "GymAxis brand label must be wired in"
    assert "'The Pulse'" in src, "Pulse brand label must remain"
    # GymAxis ring gradient must use the canonical navy → purple hex pair.
    assert "#2563EB" in src and "#9D4CDD" in src, (
        "GymAxis ring gradient must use the canonical navy→purple hexes "
        "(see /app/BRAND_PALETTE.md)"
    )


def test_ai_triage_tab_wired_into_dashboard_for_both_brands():
    """The AI triage / diagnosis tab must be reachable from the main
    operator dashboard — it was previously imported nowhere and only
    surfaced per-fault inside IssueDetailPanel."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/LiteDashboardPage.js").read_text()
    assert "PulseAIDiagnosisTab" in src, "AI Triage tab must be imported"
    assert "ai-triage" in src, "ai-triage tab id must be registered"
    # Brand-aware label switch must be present.
    assert "AI Triage" in src and "AI Diagnosis" in src, (
        "Both brand labels must be present in the tab-builder"
    )


def test_pulse_landing_has_no_fabricated_customer_names():
    """We have no real customers yet. Every name shown in the landing
    page mockups must be a clearly-placeholder string ('Floor Member',
    'Gym Manager', 'Example Gym') — not a plausible real name that a
    visitor could mistake for a customer reference."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/PulseLandingPage.js").read_text()
    # The previous-iter names that the user flagged as misleading.
    banned = ["Sarah Johnson", "Lee Somers", "Tottenham Green"]
    found = [b for b in banned if b in src]
    assert not found, (
        f"Found fabricated customer names in the Pulse landing page: {found}. "
        "Replace with clearly-placeholder strings until we have real customers."
    )
