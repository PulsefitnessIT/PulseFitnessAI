"""Iter 220cq — Channel Performance reports endpoint.

Pins ``GET /api/svc/reports/channel-performance`` which aggregates
``svc_cases`` by ``intake_channel`` (falls back to ``source``) over
the requested window and joins invoiced quote totals so the tenant
operator can see WHERE jobs come from and which channel actually
turns into £.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="u-1"):
    return {"id": uid, "organization_id": org}


def _async_iter(items):
    class _It:
        def __init__(self, xs):
            self.xs = list(xs)
            self.i = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.i >= len(self.xs):
                raise StopAsyncIteration
            v = self.xs[self.i]
            self.i += 1
            return v

    return _It(items)


def _fake_db(*, cases, quotes_agg):
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_async_iter(cases))
    fdb.svc_quotes.aggregate = MagicMock(return_value=_async_iter(quotes_agg))
    return fdb


def _iso(days_ago: int = 0, hours_ago: int = 0) -> str:
    return (
        datetime.now(timezone.utc)
        - timedelta(days=days_ago, hours=hours_ago)
    ).isoformat()


def test_channel_performance_buckets_by_intake_channel():
    """Three cases on portal (1 closed with invoice), 2 on phone
    (both closed, no invoice) → portal wins on revenue, phone wins
    on close-rate."""
    cases = [
        {"id": "c1", "status": "closed", "intake_channel": "portal",
         "created_at": _iso(days_ago=5), "closed_at": _iso(days_ago=4)},
        {"id": "c2", "status": "new", "intake_channel": "portal",
         "created_at": _iso(days_ago=2)},
        {"id": "c3", "status": "in_progress", "intake_channel": "portal",
         "created_at": _iso(days_ago=1)},
        {"id": "c4", "status": "closed", "intake_channel": "phone",
         "created_at": _iso(days_ago=8), "closed_at": _iso(days_ago=7)},
        {"id": "c5", "status": "invoiced", "intake_channel": "phone",
         "created_at": _iso(days_ago=10), "closed_at": _iso(days_ago=9)},
    ]
    # Only c1 has an invoiced quote.
    quotes_agg = [{"_id": "c1", "gross": 850.0}]
    fdb = _fake_db(cases=cases, quotes_agg=quotes_agg)

    async def run():
        with patch("routes.svc.reports.db", fdb):
            from routes.svc.reports import channel_performance
            return await channel_performance(
                from_=None, to=None, user=_user(),
            )

    out = _run(run())
    rows = {r["channel"]: r for r in out["rows"]}
    assert rows["portal"]["count"] == 3
    assert rows["portal"]["closed_count"] == 1
    assert rows["portal"]["revenue_gbp"] == 850.0
    assert rows["portal"]["close_rate"] == round(1 / 3, 4)
    assert rows["phone"]["count"] == 2
    assert rows["phone"]["closed_count"] == 2
    assert rows["phone"]["close_rate"] == 1.0
    assert rows["phone"]["revenue_gbp"] == 0.0
    # Totals across all channels.
    assert out["totals"]["case_count"] == 5
    assert out["totals"]["closed_count"] == 3
    assert out["totals"]["revenue_gbp"] == 850.0


def test_channel_performance_falls_back_to_source_for_legacy_rows():
    """Legacy cases without ``intake_channel`` must still bucket
    correctly via the ``source`` field."""
    cases = [
        {"id": "c1", "status": "closed", "source": "portal",
         "created_at": _iso(days_ago=5), "closed_at": _iso(days_ago=4)},
        # No intake_channel AND no source → bucket as "other".
        {"id": "c2", "status": "new",
         "created_at": _iso(days_ago=1)},
    ]
    fdb = _fake_db(cases=cases, quotes_agg=[])

    async def run():
        with patch("routes.svc.reports.db", fdb):
            from routes.svc.reports import channel_performance
            return await channel_performance(
                from_=None, to=None, user=_user(),
            )

    out = _run(run())
    channels = {r["channel"] for r in out["rows"]}
    assert "portal" in channels
    assert "other" in channels


def test_channel_performance_avg_hours_only_uses_closed_rows():
    """A bucket with 2 cases (1 closed, 1 still open) must compute
    avg_hours over the 1 closed row only — never blend in the open
    row as a zero."""
    cases = [
        {"id": "c1", "status": "closed", "intake_channel": "email",
         "created_at": _iso(days_ago=2, hours_ago=0),
         "closed_at":  _iso(days_ago=1, hours_ago=0)},  # ≈24h
        {"id": "c2", "status": "in_progress", "intake_channel": "email",
         "created_at": _iso(days_ago=10)},
    ]
    fdb = _fake_db(cases=cases, quotes_agg=[])

    async def run():
        with patch("routes.svc.reports.db", fdb):
            from routes.svc.reports import channel_performance
            return await channel_performance(
                from_=None, to=None, user=_user(),
            )

    out = _run(run())
    row = next(r for r in out["rows"] if r["channel"] == "email")
    assert row["count"] == 2
    assert row["closed_count"] == 1
    # ~24h give-or-take a few seconds of test runtime.
    assert 23.5 <= row["avg_hours"] <= 24.5


def test_channel_performance_unknown_channels_collapse_to_other():
    """Anything not in the known set is bucketed as 'other' so the
    UI can rely on a closed taxonomy."""
    cases = [
        {"id": "c1", "status": "new", "intake_channel": "sky_writing",
         "created_at": _iso(days_ago=1)},
    ]
    fdb = _fake_db(cases=cases, quotes_agg=[])

    async def run():
        with patch("routes.svc.reports.db", fdb):
            from routes.svc.reports import channel_performance
            return await channel_performance(
                from_=None, to=None, user=_user(),
            )

    out = _run(run())
    assert out["rows"][0]["channel"] == "other"
    assert out["rows"][0]["count"] == 1


def test_channel_performance_empty_window_returns_zero_totals():
    """Empty window must NOT raise — degrades to zero totals and an
    empty rows list."""
    fdb = _fake_db(cases=[], quotes_agg=[])

    async def run():
        with patch("routes.svc.reports.db", fdb):
            from routes.svc.reports import channel_performance
            return await channel_performance(
                from_=None, to=None, user=_user(),
            )

    out = _run(run())
    assert out["rows"] == []
    assert out["totals"]["case_count"] == 0
    assert out["totals"]["revenue_gbp"] == 0
