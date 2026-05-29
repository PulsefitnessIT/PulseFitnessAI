"""Iter 220bz — Mandatory trial-signup profile completion.

Covers the new `/api/account/complete-profile` endpoint and the
`profile_completed_at` plumbing through `/auth/me`.

  1. Missing-required-fields → 400 with a useful detail message.
  2. Happy path → stamps `profile_completed_at` on the org doc + the
     payload is mirrored back to the caller.
  3. Idempotent — re-submitting preserves the original timestamp but
     overwrites editable fields (e.g. operator fat-fingered their phone
     and corrects it on a second pass).
  4. `/auth/me` surfaces `profile_completed_at` so the React gate can
     short-circuit on already-completed accounts.
  5. The whitelist strips non-allowed keys — a malicious caller cannot
     escalate via `subscription_tier`, `is_master_admin`, etc.
  6. Missing org → 404 (not 500); missing auth → 401.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


_FULL_PROFILE = {
    "primary_contact_name": "Trial Test",
    "primary_contact_phone": "+447700900222",
    "primary_contact_address_line1": "42 Test St",
    "primary_contact_address_line2": "",
    "primary_contact_address_line3": "",
    "primary_contact_city": "London",
    "primary_contact_postcode": "N1 1AA",
    "primary_contact_country": "GB",
    "address_line1": "Trial Test Gym",
    "address_line2": "",
    "address_line3": "",
    "city": "London",
    "postcode": "EC1 1AA",
    "country": "GB",
    "company_phone": "+442012345678",
}

_OWNER = {"id": "u-1", "email": "trial@x", "organization_id": "org-1", "role": "owner"}


def _patched_account_db():
    """Return a MagicMock(`organizations`) with the standard methods."""
    from routes import account as route
    fdb = MagicMock()
    fdb.organizations.find_one = AsyncMock()
    fdb.organizations.update_one = AsyncMock()
    return route, fdb


# ══════════════════ 1 · Missing required fields → 400 ════════════════


def test_complete_profile_missing_required_returns_400():
    route, fdb = _patched_account_db()

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(
                {"address_line1": "X"}, user=_OWNER,
            )

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 400
    # Every missing required key is named, not just the first.
    detail = exc.value.detail
    for k in (
        "primary_contact_name", "primary_contact_phone",
        "primary_contact_postcode", "city", "postcode", "country",
    ):
        assert k in detail, f"{k} missing from error detail: {detail}"


# ══════════════════ 2 · Happy path stamps + persists ═════════════════


def test_complete_profile_happy_path_stamps_and_persists():
    route, fdb = _patched_account_db()
    fdb.organizations.find_one = AsyncMock(side_effect=[
        # First call — pre-update lookup.
        {"id": "org-1"},
        # Second call — serialise after update.
        {"id": "org-1", "name": "Trial Gym", **_FULL_PROFILE,
         "profile_completed_at": "2026-05-29T12:00:00+00:00"},
    ])

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(dict(_FULL_PROFILE), user=_OWNER)

    out = _run(go())
    assert out["profile_completed_at"] == "2026-05-29T12:00:00+00:00"
    assert out["primary_contact_name"] == "Trial Test"
    assert out["company_phone"] == "+442012345678"
    # update_one was called once with $set containing the profile keys.
    fdb.organizations.update_one.assert_awaited_once()
    args, _kw = fdb.organizations.update_one.await_args
    assert args[0] == {"id": "org-1"}
    set_payload = args[1]["$set"]
    assert "profile_completed_at" in set_payload
    assert set_payload["primary_contact_name"] == "Trial Test"


# ══════════════════ 3 · Idempotent — preserves original stamp ════════


def test_complete_profile_preserves_existing_completion_stamp():
    route, fdb = _patched_account_db()
    original_stamp = "2026-05-28T08:00:00+00:00"
    fdb.organizations.find_one = AsyncMock(side_effect=[
        {"id": "org-1", "profile_completed_at": original_stamp},
        {"id": "org-1", "profile_completed_at": original_stamp,
         "primary_contact_name": "Renamed", **_FULL_PROFILE},
    ])

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(
                {**_FULL_PROFILE, "primary_contact_name": "Renamed"},
                user=_OWNER,
            )

    out = _run(go())
    assert out["profile_completed_at"] == original_stamp
    set_payload = fdb.organizations.update_one.await_args.args[1]["$set"]
    # The stamp on the $set payload is the original — NOT a new now()
    # timestamp. That's the contract: idempotent re-submits never
    # re-stamp.
    assert set_payload["profile_completed_at"] == original_stamp


# ══════════════════ 4 · Whitelist strips unknown keys ════════════════


def test_complete_profile_strips_unallowed_fields():
    """A caller passing ``is_master_admin: true`` (or any non-allowed
    key) must NOT see it persisted — the route projects the payload
    through ``ORG_ALLOWED_FIELDS`` before update."""
    route, fdb = _patched_account_db()
    fdb.organizations.find_one = AsyncMock(side_effect=[
        {"id": "org-1"},
        {"id": "org-1", **_FULL_PROFILE},
    ])

    payload = {
        **_FULL_PROFILE,
        "is_master_admin": True,          # not allowed
        "subscription_tier": "enterprise",  # not allowed
        "id": "spoofed",                   # not allowed
    }

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(payload, user=_OWNER)

    _run(go())
    set_payload = fdb.organizations.update_one.await_args.args[1]["$set"]
    assert "is_master_admin" not in set_payload
    assert "subscription_tier" not in set_payload
    # `id` is NOT in ORG_ALLOWED_FIELDS so it must be stripped too.
    assert "id" not in set_payload or set_payload["id"] == "org-1"


# ══════════════════ 5 · No org → 404 ═════════════════════════════════


def test_complete_profile_404_when_org_missing():
    route, fdb = _patched_account_db()
    fdb.organizations.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(dict(_FULL_PROFILE), user=_OWNER)

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 404


def test_complete_profile_404_when_user_has_no_org_id():
    route, fdb = _patched_account_db()

    async def go():
        with patch.object(route, "db", fdb):
            return await route.complete_profile(
                dict(_FULL_PROFILE),
                user={"id": "u-2", "organization_id": ""},
            )

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 404


# ══════════════════ 6 · /auth/me surfaces the stamp ══════════════════


def test_auth_me_includes_profile_completed_at():
    """The /auth/me payload must surface the org's
    ``profile_completed_at`` so the React DashboardRoute gate can
    short-circuit on already-completed accounts."""
    from routes.auth import _build_login_user_payload
    org_done = {
        "id": "org-1", "name": "X",
        "profile_completed_at": "2026-05-29T12:00:00+00:00",
    }
    out = _build_login_user_payload(
        {"id": "u-1", "email": "x@y", "full_name": "Z", "role": "owner",
         "organization_id": "org-1"},
        org_done,
        trial_state={"is_trial": True},
        features=[],
    )
    assert out["profile_completed_at"] == "2026-05-29T12:00:00+00:00"

    org_pending = {"id": "org-2", "name": "Y"}
    out2 = _build_login_user_payload(
        {"id": "u-2", "email": "a@b", "full_name": "C", "role": "owner",
         "organization_id": "org-2"},
        org_pending,
        trial_state={"is_trial": True},
        features=[],
    )
    assert out2["profile_completed_at"] == ""
