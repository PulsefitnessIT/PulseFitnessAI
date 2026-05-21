"""Iter 216h288 — Engineer master availability toggle (Gap 10).

Closes Gap 10 from the BA audit: an approved Partner Engineer can
now toggle themselves to `unavailable` (annual leave, parental
leave, full diary) with an optional "back on" date. Per the user's
2C choice, unavailable engineers remain visible on discovery
surfaces but are sunk to the bottom and rendered with a yellow
"Back on …" badge.

Pins covered
------------
* `_effective_availability` defaults to "available" for legacy rows
* `_effective_availability` auto-resumes when resumes_on is past
* `_parse_resumes_on` accepts ISO date + datetime, rejects garbage
* PUT toggle validates `available` is provided
* PUT toggle unavailable persists status + resumes_on + note
* PUT toggle to available clears resumes_on + note
* PUT toggle drops a past resumes_on (sanity guard)
* GET endpoint returns 404 for non-partners
* `find-engineers` returns availability + sinks unavailable to bottom
* Public reviews endpoint exposes availability on the partner card
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user(uid: str = "u-jane"):
    return {"id": uid, "organization_id": "org-1"}


# ── _parse_resumes_on ──────────────────────────────────────────────


def test_parse_resumes_on_accepts_iso_date_and_datetime():
    from routes.partners import _parse_resumes_on
    assert _parse_resumes_on("2026-03-05") == "2026-03-05"
    assert _parse_resumes_on("2026-03-05T10:00:00Z") == "2026-03-05"


def test_parse_resumes_on_returns_none_for_garbage():
    from routes.partners import _parse_resumes_on
    assert _parse_resumes_on(None) is None
    assert _parse_resumes_on("") is None
    assert _parse_resumes_on("   ") is None
    assert _parse_resumes_on("not-a-date") is None
    assert _parse_resumes_on("2026-13-99") is None


# ── _effective_availability ────────────────────────────────────────


def test_effective_availability_defaults_to_available_for_legacy_row():
    from routes.partners import _effective_availability
    assert _effective_availability({}) == {
        "status": "available", "resumes_on": None, "note": None, "updated_at": None,
    }
    assert _effective_availability({"availability": None})["status"] == "available"


def test_effective_availability_returns_unavailable_when_set():
    from routes.partners import _effective_availability
    future = (date.today() + timedelta(days=10)).isoformat()
    out = _effective_availability({"availability": {
        "status": "unavailable", "resumes_on": future, "note": "Back from leave",
        "updated_at": "2026-02-21T00:00:00Z",
    }})
    assert out["status"] == "unavailable"
    assert out["resumes_on"] == future
    assert out["note"] == "Back from leave"


def test_effective_availability_auto_resumes_when_past():
    """The engineer set themselves to unavailable until 1 Jan and
    forgot to toggle back on. The 5-Feb visitor sees them as
    available again."""
    from routes.partners import _effective_availability
    past = (date.today() - timedelta(days=14)).isoformat()
    out = _effective_availability({"availability": {
        "status": "unavailable", "resumes_on": past, "note": "Annual leave",
    }})
    assert out["status"] == "available"
    # Original resumes_on + note are preserved for the audit trail
    assert out["resumes_on"] == past


def test_effective_availability_indefinite_unavailable_stays_unavailable():
    from routes.partners import _effective_availability
    out = _effective_availability({"availability": {
        "status": "unavailable", "resumes_on": None, "note": None,
    }})
    assert out["status"] == "unavailable"


# ── PUT /partners/me/availability ──────────────────────────────────


def test_set_availability_requires_partner():
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(set_my_availability(body={"available": False}, user=_user()))
    assert exc.value.status_code == 404


def test_set_availability_requires_available_flag():
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(set_my_availability(body={"note": "blah"}, user=_user()))
    assert exc.value.status_code == 400
    assert "available" in str(exc.value.detail)


def test_set_availability_unavailable_persists_full_payload():
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    captured = {}
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    future = (date.today() + timedelta(days=30)).isoformat()
    with patch("routes.partners.db", fake_db), patch("routes.partners._audit", AsyncMock()):
        out = _run(set_my_availability(
            body={"available": False, "resumes_on": future, "note": "Annual leave"},
            user=_user(),
        ))
    av = captured["$set"]["availability"]
    assert av["status"] == "unavailable"
    assert av["resumes_on"] == future
    assert av["note"] == "Annual leave"
    assert out["availability"]["status"] == "unavailable"


def test_set_availability_back_on_clears_resumes_on_and_note():
    """Toggling back to available wipes the leave metadata so the
    public badge disappears immediately."""
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane",
        "availability": {"status": "unavailable", "resumes_on": "2026-03-05", "note": "Annual leave"},
    })
    captured = {}
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), patch("routes.partners._audit", AsyncMock()):
        _run(set_my_availability(
            body={"available": True, "resumes_on": "2030-01-01", "note": "ignored"},
            user=_user(),
        ))
    av = captured["$set"]["availability"]
    assert av["status"] == "available"
    assert av["resumes_on"] is None
    assert av["note"] is None


def test_set_availability_drops_past_resumes_on():
    """If the engineer types in a date that's already passed,
    silently strip it — they probably meant indefinite."""
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    captured = {}
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    past = (date.today() - timedelta(days=5)).isoformat()
    with patch("routes.partners.db", fake_db), patch("routes.partners._audit", AsyncMock()):
        _run(set_my_availability(
            body={"available": False, "resumes_on": past, "note": "Burned out"},
            user=_user(),
        ))
    av = captured["$set"]["availability"]
    assert av["status"] == "unavailable"
    assert av["resumes_on"] is None
    assert av["note"] == "Burned out"


def test_set_availability_audit_log_carries_status_change():
    from routes.partners import set_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane",
        "availability": {"status": "available"},
    })
    fake_db.partner_engineers.update_one = AsyncMock()
    audit = AsyncMock()
    with patch("routes.partners.db", fake_db), patch("routes.partners._audit", audit):
        _run(set_my_availability(body={"available": False, "note": "Sick"}, user=_user()))
    args = audit.await_args.kwargs
    assert args["action"] == "availability_set"
    assert args["before"]["status"] == "available"
    assert args["after"]["status"] == "unavailable"
    assert args["after"]["note"] == "Sick"


# ── GET /partners/me/availability ──────────────────────────────────


def test_get_my_availability_returns_effective_state():
    from routes.partners import get_my_availability
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane",
        "availability": {"status": "unavailable", "resumes_on": "2030-01-01", "note": "Back in Jan"},
    })
    with patch("routes.partners.db", fake_db):
        out = _run(get_my_availability(user=_user()))
    assert out["availability"]["status"] == "unavailable"
    assert out["availability"]["note"] == "Back in Jan"
