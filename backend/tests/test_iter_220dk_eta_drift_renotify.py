"""Iter 220dk — Mid-journey ETA drift re-notify.

Pins:

  * ``maybe_renotify_eta_drift`` is a no-op when:
      - ``status != en_route``
      - ``customer_email`` missing / invalid
      - ``comms_auto_notify is False``
      - no previous ``eta_last_minutes`` (first emit comes from the
        ``en_route`` auto-comm, not the drift checker)
      - fresh ETA estimate is ``None`` (stale ping / no coords)
      - drift is below ``DRIFT_THRESHOLD_MIN`` (10 minutes)
      - cooldown < ``DRIFT_COOLDOWN_SECONDS`` (5 min)
  * Happy path: drift ≥ 10 min, cooldown elapsed → fires
    ``_send_eta_email`` with ``trigger='eta_drift_renotify'`` and
    re-stamps ``eta_last_sent_at`` / ``eta_last_minutes``.
  * The location-ping endpoint runs the check after persisting the
    ping and never raises on a downstream failure.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user():
    return {
        "id": "eng-1", "organization_id": "org-1",
        "email": "u@x.test", "full_name": "Eng One",
    }


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _en_route_case(**overrides):
    base = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill #3",
        "assigned_engineer_id": "eng-1",
        "assigned_engineer_name": "Eng One",
        "status": "en_route",
        "customer_email": "customer@x.test",
        "customer_name": "Customer Co",
        "site_name": "London HQ",
        "site_lat": 51.5200, "site_lng": -0.1050,
        "track_token": "TOK_DRIFT0000000000000",
        "priority": "p2",
        "comms_auto_notify": True,
        "eta_last_minutes": 5,
        "eta_last_sent_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    }
    base.update(overrides)
    return base


def _patch_db_with(case, *, ping=None):
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_chain([case] if case else []))
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_engineer_locations.find_one = AsyncMock(return_value=ping)
    return fdb


def _fresh_ping():
    return {
        "lat": 51.5074, "lng": -0.1278,
        "recorded_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
    }


# ── 1 · No baseline → no auto re-notify ──────────────────────────


def test_no_renotify_when_no_eta_last_minutes_yet():
    """The first email comes from the en_route auto-comm transition.
    We don't second-guess it from the location ping."""
    fdb = _patch_db_with(_en_route_case(eta_last_minutes=None), ping=_fresh_ping())
    send = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", send):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    out = _run(run())
    assert out == []
    send.assert_not_called()


# ── 2 · No customer_email → no auto re-notify ────────────────────


def test_no_renotify_when_customer_email_missing():
    fdb = _patch_db_with(_en_route_case(customer_email=""), ping=_fresh_ping())
    send = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", send):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    _run(run())
    send.assert_not_called()


# ── 3 · comms_auto_notify False → no auto re-notify ──────────────


def test_no_renotify_when_comms_auto_notify_disabled():
    fdb = _patch_db_with(_en_route_case(comms_auto_notify=False), ping=_fresh_ping())
    send = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", send):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    _run(run())
    send.assert_not_called()


# ── 4 · Drift under threshold → no fire ──────────────────────────


def test_no_renotify_when_drift_under_threshold():
    """Engineer was at 5 min, fresh estimate is also ~3-4 min from
    London → diff < 10 → quiet."""
    fdb = _patch_db_with(
        _en_route_case(eta_last_minutes=5),
        ping=_fresh_ping(),
    )
    send = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", send):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    _run(run())
    send.assert_not_called()


# ── 5 · Drift ≥ threshold but cooldown active → no fire ──────────


def test_no_renotify_when_within_cooldown_window():
    case = _en_route_case(
        eta_last_minutes=30,  # Engineer said 30 min last time
        eta_last_sent_at=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
    )
    fdb = _patch_db_with(case, ping=_fresh_ping())
    send = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", send):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    _run(run())
    send.assert_not_called()


# ── 6 · Happy path ───────────────────────────────────────────────


def test_renotify_fires_when_drift_exceeds_threshold_and_cooldown_elapsed():
    """Engineer initially said 30 min; fresh estimate is ~3-4 min.
    |30 - 3| = 27 ≥ 10 AND last send was 10 min ago (>5 min cooldown)
    → fresh email fires."""
    case = _en_route_case(eta_last_minutes=30)
    fdb = _patch_db_with(case, ping=_fresh_ping())
    send_called_with: list = []

    async def fake_send_email(**kwargs):
        send_called_with.append(kwargs)
        return {"ok": True, "case_id": kwargs["case"]["id"]}

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.engineer_eta_update._send_eta_email", fake_send_email):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            return await maybe_renotify_eta_drift(user=_user())

    out = _run(run())
    assert len(send_called_with) == 1
    kwargs = send_called_with[0]
    assert kwargs["case"]["id"] == "case-1"
    assert kwargs["trigger"] == "eta_drift_renotify"
    # Fresh ETA passed (not the stale one). Should be small (a few min).
    assert kwargs["eta_mins"] is not None
    assert kwargs["eta_mins"] < 30
    assert len(out) == 1


def test_renotify_no_op_when_status_not_en_route():
    """The Mongo filter excludes anything but ``en_route``. Pin it."""
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
            await maybe_renotify_eta_drift(user=_user())

    _run(run())
    flt = fdb.svc_cases.find.call_args.args[0]
    assert flt["status"] == "en_route"
    assert flt["assigned_engineer_id"] == "eng-1"


# ── 7 · Constants ────────────────────────────────────────────────


def test_drift_constants_pinned():
    """Belt-and-braces: a refactor changing these silently would
    swing customer-facing email frequency in unexpected directions."""
    from routes.svc.engineer_eta_update import (
        DRIFT_THRESHOLD_MIN, DRIFT_COOLDOWN_SECONDS,
    )
    assert DRIFT_THRESHOLD_MIN == 10
    assert DRIFT_COOLDOWN_SECONDS == 300


# ── 8 · Location-ping endpoint wires the drift check ─────────────


def test_location_ping_invokes_drift_check_and_returns_renotified_ids():
    """The ping endpoint runs the check after persisting and returns
    the IDs that fired so the engineer mobile app can show a toast."""
    fdb = MagicMock()
    fdb.svc_engineer_locations.update_one = AsyncMock()
    renotify = AsyncMock(return_value=[
        {"case_id": "case-1", "ok": True},
        {"case_id": "case-2", "ok": False},  # template inactive
    ])

    async def run():
        with patch("routes.svc.engineer_location.db", fdb), \
             patch("routes.svc.engineer_eta_update.maybe_renotify_eta_drift", renotify):
            from routes.svc.engineer_location import post_location
            return await post_location(
                body={"lat": 51.5, "lng": -0.13, "accuracy_m": 8},
                user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    # Only ``ok=True`` IDs surfaced.
    assert out["eta_renotified_case_ids"] == ["case-1"]


def test_location_ping_safe_when_drift_check_explodes():
    """A bug in the drift checker must never break the engineer's
    location ping (critical mobile path)."""
    fdb = MagicMock()
    fdb.svc_engineer_locations.update_one = AsyncMock()
    broken = AsyncMock(side_effect=RuntimeError("DB fell over"))

    async def run():
        with patch("routes.svc.engineer_location.db", fdb), \
             patch("routes.svc.engineer_eta_update.maybe_renotify_eta_drift", broken):
            from routes.svc.engineer_location import post_location
            return await post_location(
                body={"lat": 51.5, "lng": -0.13},
                user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    assert out["eta_renotified_case_ids"] == []
