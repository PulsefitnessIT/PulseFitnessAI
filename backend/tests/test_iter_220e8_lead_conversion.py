"""Iter 220e8 — CRM lead conversion flow.

Covers the opportunity → Company/Contact/Site/Artifact bridge plus
idempotency and closed-state guards.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


USER = {"id": "u-1", "organization_id": "org-1", "full_name": "Sam"}


def _opp(stage: str = "lead", **extra) -> dict:
    base = {
        "id": "opp-1", "organization_id": "org-1",
        "title": "Pulse — Service Deal",
        "company_name": "Pulse Fitness", "contact_name": "Jane Doe",
        "value": 12000.0, "stage": stage,
    }
    base.update(extra)
    return base


def _db_for_convert(opportunity: dict | None):
    """Build an in-memory ``db`` mock covering every collection the
    conversion route touches. Captures inserts/updates for assertion."""
    fdb = MagicMock()
    state = {
        "opp": opportunity,
        "companies_v2": [], "contacts_v2": [], "sites": [],
        "contracts": [], "quotes": [], "activities": [],
        "companies_legacy": [], "contacts_legacy": [],
        "audit": [], "opp_updates": [],
    }

    fdb.crm2_opportunities.find_one = AsyncMock(side_effect=lambda q, p=None: state["opp"])

    async def _opp_update(q, upd):
        sets = upd.get("$set", {})
        if state["opp"]:
            state["opp"].update(sets)
        state["opp_updates"].append(sets)
        return MagicMock(modified_count=1)
    fdb.crm2_opportunities.update_one = AsyncMock(side_effect=_opp_update)

    fdb.crm2_companies.find_one = AsyncMock(
        side_effect=lambda q, p=None: next((c for c in state["companies_v2"]
                                            if c["id"] == q.get("id")), None),
    )
    fdb.crm2_companies.insert_one = AsyncMock(
        side_effect=lambda d: state["companies_v2"].append(d) or MagicMock(),
    )
    fdb.crm2_contacts.find_one = AsyncMock(
        side_effect=lambda q, p=None: next((c for c in state["contacts_v2"]
                                            if c["id"] == q.get("id")), None),
    )
    fdb.crm2_contacts.insert_one = AsyncMock(
        side_effect=lambda d: state["contacts_v2"].append(d) or MagicMock(),
    )
    fdb.crm2_sites.find_one = AsyncMock(
        side_effect=lambda q, p=None: next((s for s in state["sites"]
                                            if s["id"] == q.get("id")), None),
    )
    fdb.crm2_sites.insert_one = AsyncMock(
        side_effect=lambda d: state["sites"].append(d) or MagicMock(),
    )
    fdb.crm2_contracts.insert_one = AsyncMock(
        side_effect=lambda d: state["contracts"].append(d) or MagicMock(),
    )
    fdb.crm2_quotes.insert_one = AsyncMock(
        side_effect=lambda d: state["quotes"].append(d) or MagicMock(),
    )
    fdb.crm2_activities.insert_one = AsyncMock(
        side_effect=lambda d: state["activities"].append(d) or MagicMock(),
    )

    # Legacy mirror collections — upsert into list.
    def _make_legacy_upsert(target):
        async def _upd(q, upd, upsert=False):
            doc = upd.get("$setOnInsert")
            if doc:
                target.append(doc)
            return MagicMock(matched_count=0, upserted_id=(doc or {}).get("id"))
        return _upd
    fdb.crm_companies.update_one = AsyncMock(
        side_effect=_make_legacy_upsert(state["companies_legacy"]),
    )
    fdb.crm_contacts.update_one = AsyncMock(
        side_effect=_make_legacy_upsert(state["contacts_legacy"]),
    )

    # Audit log goes through the helper from crm_core — patch separately
    # in callers when they need to assert. Default no-op below.
    return fdb, state


# ── 1 · Happy paths ──────────────────────────────────────────────


def test_convert_creates_company_contact_and_contract_draft():
    from routes.crm_lead_conversion import convert_lead
    fdb, state = _db_for_convert(_opp())
    payload = {
        "company":  {"mode": "create", "data": {"name": "Pulse Fitness Ltd"}},
        "contact":  {"mode": "create",
                     "data": {"first_name": "Jane", "last_name": "Doe",
                              "email": "jane@pulse.io"}},
        "site":     {"mode": "skip"},
        "artifact": {"kind": "contract_draft"},
        "target_stage": "qualified",
    }
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()):
        out = _run(convert_lead("opp-1", payload, user=USER))

    assert out["already_converted"] is False
    assert out["stage_moved"] is True
    assert out["target_stage"] == "qualified"

    assert len(state["companies_v2"]) == 1
    assert state["companies_v2"][0]["name"] == "Pulse Fitness Ltd"
    assert state["companies_v2"][0]["created_from_opportunity_id"] == "opp-1"

    assert len(state["contacts_v2"]) == 1
    assert state["contacts_v2"][0]["email"] == "jane@pulse.io"

    # Contract drafted, value carried across, opportunity linked.
    assert len(state["contracts"]) == 1
    contract = state["contracts"][0]
    assert contract["annual_value"] == 12000.0
    assert contract["opportunity_id"] == "opp-1"
    assert contract["tier"] == "silver"

    # Opportunity stamped with conversion metadata + stage moved.
    upd = state["opp_updates"][0]
    assert upd["stage"] == "qualified"
    assert upd["converted_at"]
    assert upd["conversion_company_id"] == out["company_id"]
    assert upd["conversion_contact_id"] == out["contact_id"]

    # Legacy mirror collections received entries.
    assert len(state["companies_legacy"]) == 1
    assert len(state["contacts_legacy"]) == 1

    # An activity row landed on the opportunity timeline.
    assert state["activities"]
    assert "Lead converted" in state["activities"][0]["body"]


def test_convert_with_existing_company_links_without_duplicating():
    from routes.crm_lead_conversion import convert_lead
    fdb, state = _db_for_convert(_opp())
    state["companies_v2"].append({
        "id": "co-EX", "organization_id": "org-1", "name": "Existing Co",
    })
    payload = {
        "company":  {"mode": "existing", "company_id": "co-EX"},
        "contact":  {"mode": "create", "data": {"first_name": "Tom"}},
        "site":     {"mode": "skip"},
        "artifact": {"kind": "none"},
        "target_stage": "qualified",
    }
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()):
        out = _run(convert_lead("opp-1", payload, user=USER))

    assert out["company_id"] == "co-EX"
    assert out["company_name"] == "Existing Co"
    # No new company row inserted (the prepopulated row remains the only one).
    assert len(state["companies_v2"]) == 1
    # No artifact when kind=none.
    assert out["artifact"] is None
    assert state["contracts"] == []
    assert state["quotes"] == []


def test_convert_with_site_create_attaches_site_to_company():
    from routes.crm_lead_conversion import convert_lead
    fdb, state = _db_for_convert(_opp())
    payload = {
        "company": {"mode": "create", "data": {"name": "Acme Gyms"}},
        "contact": {"mode": "create", "data": {"first_name": "Jane"}},
        "site":    {"mode": "create",
                    "data": {"name": "Acme — Manchester", "postcode": "M1"}},
        "artifact": {"kind": "quote_draft"},
    }
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()):
        out = _run(convert_lead("opp-1", payload, user=USER))

    assert out["site_id"]
    assert out["site_name"] == "Acme — Manchester"
    site = state["sites"][0]
    assert site["company_id"] == out["company_id"]
    assert site["company_name"] == "Acme Gyms"
    # Quote draft created.
    assert out["artifact"]["type"] == "quote_draft"
    assert state["quotes"][0]["amount"] == 12000.0


# ── 2 · Guards & idempotency ────────────────────────────────────


def test_convert_404s_for_unknown_opportunity():
    from routes.crm_lead_conversion import convert_lead
    fdb, _ = _db_for_convert(None)
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()), \
         pytest.raises(HTTPException) as exc:
        _run(convert_lead("ghost", {}, user=USER))
    assert exc.value.status_code == 404


def test_convert_rejects_closed_opportunity():
    from routes.crm_lead_conversion import convert_lead
    fdb, _ = _db_for_convert(_opp(stage="closed_won"))
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()), \
         pytest.raises(HTTPException) as exc:
        _run(convert_lead("opp-1", {
            "company": {"mode": "create", "data": {"name": "X"}},
            "contact": {"mode": "create", "data": {"first_name": "Y"}},
        }, user=USER))
    assert exc.value.status_code == 400


def test_convert_is_idempotent_when_already_converted():
    from routes.crm_lead_conversion import convert_lead
    fdb, state = _db_for_convert(_opp(
        converted_at="2026-02-01T10:00:00",
        conversion_company_id="co-OLD", conversion_company_name="OldCo",
        conversion_contact_id="ct-OLD", conversion_contact_name="OldContact",
        conversion_site_id=None, conversion_artifact=None,
    ))
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()):
        out = _run(convert_lead("opp-1", {
            "company": {"mode": "create", "data": {"name": "Would-be-duplicate"}},
        }, user=USER))

    assert out["already_converted"] is True
    assert out["company_id"] == "co-OLD"
    assert out["contact_id"] == "ct-OLD"
    # No new writes happened.
    assert state["companies_v2"] == []
    assert state["contacts_v2"] == []
    assert state["opp_updates"] == []


def test_convert_requires_company_name_when_create_mode():
    from routes.crm_lead_conversion import convert_lead
    # Empty deal company_name and empty data → 400.
    fdb, _ = _db_for_convert(_opp(company_name=""))
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()), \
         pytest.raises(HTTPException) as exc:
        _run(convert_lead("opp-1", {
            "company": {"mode": "create", "data": {}},
            "contact": {"mode": "skip"},
        }, user=USER))
    assert exc.value.status_code == 400
    assert "Company name" in exc.value.detail


def test_convert_existing_company_requires_company_id():
    from routes.crm_lead_conversion import convert_lead
    fdb, _ = _db_for_convert(_opp())
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()), \
         pytest.raises(HTTPException) as exc:
        _run(convert_lead("opp-1", {
            "company": {"mode": "existing"},
            "contact": {"mode": "skip"},
        }, user=USER))
    assert exc.value.status_code == 400


def test_convert_skip_mode_carries_existing_opportunity_links():
    """When the opp already has company_id/contact_id, skip-mode
    on both should just move the stage forward without creating
    new records."""
    from routes.crm_lead_conversion import convert_lead
    fdb, state = _db_for_convert(_opp(
        company_id="co-FIXED", contact_id="ct-FIXED",
    ))
    with patch("routes.crm_lead_conversion.db", fdb), \
         patch("routes.crm_lead_conversion.log_audit", AsyncMock()):
        out = _run(convert_lead("opp-1", {
            "company": {"mode": "skip"},
            "contact": {"mode": "skip"},
            "site":    {"mode": "skip"},
            "artifact": {"kind": "none"},
            "target_stage": "proposal",
        }, user=USER))

    assert out["company_id"] == "co-FIXED"
    assert out["contact_id"] == "ct-FIXED"
    assert state["companies_v2"] == []
    assert state["contacts_v2"] == []
    assert state["opp_updates"][0]["stage"] == "proposal"
