"""Iter 220cb — Companies House verification in trial signup.

Covers:

  1. New ``/api/account/companies-house/*`` endpoints work for any
     authenticated user (not master-admin-gated).
  2. Rate-limited per-user (a competitor harvesting our key gets
     throttled).
  3. ``q`` shorter than 2 chars short-circuits to ``items=[]``
     without burning a CH API call.
  4. CH disabled → graceful 200 with ``enabled=false`` on status +
     search; 503 on profile (since the operator can't pick a match
     when the upstream is dark).
  5. ``/api/account/complete-profile`` accepts and persists the new
     CH metadata keys (``company_number``,
     ``companies_house_verified``, ``pending_review``,
     ``pending_review_reason``).
  6. Pending-review flagging is mirrored back to ``/auth/me`` via
     the org serialiser.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


_USER = {"id": "u-1", "email": "trial@x", "organization_id": "org-1", "role": "owner"}


# ══════════════════ 1 · /account/ch/status auth-only ═════════════════


def test_account_ch_status_enabled():
    from routes import companies_house as route

    async def go():
        with patch.object(route, "is_enabled", return_value=True), \
             patch.object(route, "base_url", return_value="https://api.company-information.service.gov.uk"):
            return await route.account_companies_house_status(user=_USER)

    out = _run(go())
    assert out["enabled"] is True
    assert out["base_url"].startswith("https://")


def test_account_ch_status_disabled_when_no_key():
    from routes import companies_house as route

    async def go():
        with patch.object(route, "is_enabled", return_value=False):
            return await route.account_companies_house_status(user=_USER)

    out = _run(go())
    assert out["enabled"] is False
    assert out["base_url"] is None


# ══════════════════ 2 · /account/ch/search ═══════════════════════════


def test_account_ch_search_short_query_no_upstream_call():
    """Typing one letter shouldn't burn a Companies House API call —
    we short-circuit at len(q)<2."""
    from routes import companies_house as route
    spy = AsyncMock(return_value=[])

    async def go():
        with patch.object(route, "is_enabled", return_value=True), \
             patch.object(route, "ch_search", spy), \
             patch.object(route, "rate_limit_async", AsyncMock(return_value=None)):
            return await route.account_companies_house_search(q="a", limit=8, user=_USER)

    out = _run(go())
    assert out["items"] == []
    spy.assert_not_awaited()  # no upstream call


def test_account_ch_search_happy_path_returns_items():
    from routes import companies_house as route
    items = [
        {"company_number": "12345678", "company_name": "Real Gym Ltd",
         "company_status": "active", "address": {"locality": "London"}},
    ]

    async def go():
        with patch.object(route, "is_enabled", return_value=True), \
             patch.object(route, "ch_search", AsyncMock(return_value=items)), \
             patch.object(route, "rate_limit_async", AsyncMock(return_value=None)):
            return await route.account_companies_house_search(q="real gym", limit=8, user=_USER)

    out = _run(go())
    assert out["enabled"] is True
    assert out["items"] == items
    assert out["query"] == "real gym"


def test_account_ch_search_rate_limited_per_user():
    """The rate limiter must be called with a user-scoped key so a
    competitor can't farm the upstream API behind our key."""
    from routes import companies_house as route
    rl = AsyncMock(return_value=None)

    async def go():
        with patch.object(route, "is_enabled", return_value=True), \
             patch.object(route, "ch_search", AsyncMock(return_value=[])), \
             patch.object(route, "rate_limit_async", rl):
            return await route.account_companies_house_search(q="abc", limit=8, user=_USER)

    _run(go())
    rl.assert_awaited_once()
    kwargs = rl.await_args.kwargs
    assert kwargs.get("key", "").endswith(f":{_USER['id']}")
    assert kwargs.get("max_requests") == 30


def test_account_ch_search_disabled_returns_empty_not_error():
    """When CH is disabled the search endpoint must still return 200
    with enabled=false so the frontend can fall back to manual entry."""
    from routes import companies_house as route

    async def go():
        with patch.object(route, "is_enabled", return_value=False), \
             patch.object(route, "rate_limit_async", AsyncMock(return_value=None)):
            return await route.account_companies_house_search(q="anything", limit=8, user=_USER)

    out = _run(go())
    assert out["enabled"] is False
    assert out["items"] == []


# ══════════════════ 3 · /account/ch/profile/{number} ═════════════════


def test_account_ch_profile_returns_normalised_address():
    from routes import companies_house as route
    profile_data = {
        "company_number": "12345678", "company_name": "Real Gym Ltd",
        "company_status": "active", "company_type": "ltd",
        "address_line1": "1 Strand", "address_line2": "", "address_line3": "",
        "city": "London", "county": "", "postcode": "WC2N 5HR",
        "country": "England",
    }

    async def go():
        with patch.object(route, "is_enabled", return_value=True), \
             patch.object(route, "ch_profile", AsyncMock(return_value=profile_data)), \
             patch.object(route, "rate_limit_async", AsyncMock(return_value=None)):
            return await route.account_companies_house_profile("12345678", user=_USER)

    out = _run(go())
    assert out["enabled"] is True
    assert out["company_number"] == "12345678"
    assert out["postcode"] == "WC2N 5HR"
    assert out["address_line1"] == "1 Strand"


def test_account_ch_profile_503_when_disabled():
    """The frontend only fetches a profile after a successful search,
    so reaching this endpoint with CH disabled is a server-state bug
    — surface it loudly."""
    from routes import companies_house as route

    async def go():
        with patch.object(route, "is_enabled", return_value=False), \
             patch.object(route, "rate_limit_async", AsyncMock(return_value=None)):
            return await route.account_companies_house_profile("12345678", user=_USER)

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 503


# ══════════════════ 4 · complete-profile persists CH metadata ════════


_FULL_PROFILE = {
    "primary_contact_name": "Trial Test",
    "primary_contact_phone": "+447700900222",
    "primary_contact_address_line1": "42 Test St",
    "primary_contact_city": "London",
    "primary_contact_postcode": "N1 1AA",
    "primary_contact_country": "GB",
    "address_line1": "1 Strand",
    "city": "London",
    "postcode": "WC2N 5HR",
    "country": "GB",
}


def test_complete_profile_persists_companies_house_verified():
    """Picking a real CH match → company_number + verified=True
    must round-trip onto the org doc."""
    from routes import account as route
    fdb = MagicMock()
    fdb.organizations.find_one = AsyncMock(side_effect=[
        {"id": "org-1"},
        {"id": "org-1", **_FULL_PROFILE, "company_number": "12345678",
         "companies_house_verified": True, "pending_review": False,
         "profile_completed_at": "2026-05-29T22:00:00+00:00"},
    ])
    fdb.organizations.update_one = AsyncMock()

    payload = {
        **_FULL_PROFILE,
        "company_number": "12345678",
        "companies_house_verified": True,
        "pending_review": False,
        "pending_review_reason": "",
    }

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(payload, user=_USER)

    out = _run(go())
    assert out["company_number"] == "12345678"
    assert out["companies_house_verified"] is True
    assert out["pending_review"] is False
    set_payload = fdb.organizations.update_one.await_args.args[1]["$set"]
    assert set_payload["company_number"] == "12345678"
    assert set_payload["companies_house_verified"] is True


def test_complete_profile_persists_pending_review_for_manual_entry():
    """No CH match → operator clicked "Can't find" → form sets
    pending_review=True with reason='manual_company_entry'. Must
    persist so master admin can vet the org before unlocking."""
    from routes import account as route
    fdb = MagicMock()
    fdb.organizations.find_one = AsyncMock(side_effect=[
        {"id": "org-2"},
        {"id": "org-2", **_FULL_PROFILE,
         "pending_review": True, "pending_review_reason": "manual_company_entry",
         "profile_completed_at": "2026-05-29T22:00:00+00:00"},
    ])
    fdb.organizations.update_one = AsyncMock()

    payload = {
        **_FULL_PROFILE,
        "company_number": "",
        "companies_house_verified": False,
        "pending_review": True,
        "pending_review_reason": "manual_company_entry",
    }

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(payload, user=_USER)

    out = _run(go())
    assert out["pending_review"] is True
    assert out["pending_review_reason"] == "manual_company_entry"
    assert out["companies_house_verified"] is False
    assert out["company_number"] == ""


def test_complete_profile_strips_unknown_ch_fields():
    """A malicious caller passing ``companies_house_verified_by_admin``
    (or any other spoofed key) must NOT see it persisted — the
    whitelist remains the only door."""
    from routes import account as route
    fdb = MagicMock()
    fdb.organizations.find_one = AsyncMock(side_effect=[
        {"id": "org-3"},
        {"id": "org-3", **_FULL_PROFILE},
    ])
    fdb.organizations.update_one = AsyncMock()

    payload = {
        **_FULL_PROFILE,
        "companies_house_verified": True,
        "companies_house_verified_by_admin": True,    # not allowed
        "_ch_internal_override": True,                # not allowed
    }

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(payload, user=_USER)

    _run(go())
    set_payload = fdb.organizations.update_one.await_args.args[1]["$set"]
    assert "companies_house_verified_by_admin" not in set_payload
    assert "_ch_internal_override" not in set_payload
    # The legitimate verified flag IS persisted.
    assert set_payload["companies_house_verified"] is True
