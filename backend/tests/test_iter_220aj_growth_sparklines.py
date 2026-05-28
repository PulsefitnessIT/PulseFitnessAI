"""Iter 220aj — Growth Hub 30-day sparklines.

Pins the new ``GET /api/master-admin/growth/sparklines`` endpoint that
powers the inline SVG sparklines under each KPI tile.

  * Master-admin gated.
  * Returns 30 daily points per metric, oldest first, every point has
    ``date`` (ISO ``YYYY-MM-DD``) and integer ``value``.
  * Series catalogue is the 5 the Hub renders: ``trials_started``,
    ``blog_views``, ``emails_sent``, ``deals_created``, ``chat_sessions``.
  * Blog-view snapshot writes today's total to
    ``seo_view_snapshots`` so the historical line accumulates from
    "now".
  * ``_bucket_count_by_day`` accepts both ``datetime`` and ISO-string
    date fields — the platform inserts both shapes historically.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, items):
            self._items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    return _Cur(items)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "users", "organizations", "seo_articles", "seo_view_snapshots",
        "email_send_events", "crm_deals", "crm2_opportunities",
        "mkt_chat_sessions",
    ):
        c = getattr(fdb, coll)
        c.count_documents = AsyncMock(return_value=0)
        c.find_one = AsyncMock(return_value=None)
        c.find = MagicMock(return_value=_async_iter([]))
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()

    # Iter 220aq — sparklines now scope deal-creation buckets to the
    # master-admin org via ``_master_admin_org_id``; stub the resolver
    # path so tests don't need to opt in.
    fdb.users.find_one = AsyncMock(return_value={"organization_id": "ma-org"})
    fdb.organizations.find_one = AsyncMock(return_value={"id": "ma-org"})

    # `seo_view_snapshots.find(...).to_list(...)` is used directly.
    snap_cur = MagicMock()
    snap_cur.to_list = AsyncMock(return_value=[])
    fdb.seo_view_snapshots.find = MagicMock(return_value=snap_cur)

    return fdb


# ── Gating ─────────────────────────────────────────────────────────

def test_sparklines_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.growth_sparklines({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


# ── Shape contract ────────────────────────────────────────────────

def test_sparklines_returns_five_series_with_30_points_each():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_sparklines(
                {"id": "u", "is_master_admin": True},
            )
    out = _run(go())
    assert out["days"] == 30
    assert set(out["series"].keys()) == {
        "trials_started", "blog_views", "emails_sent",
        "deals_created", "chat_sessions",
    }
    for series in out["series"].values():
        assert len(series) == 30
        for p in series:
            assert "date" in p and "value" in p
            assert isinstance(p["value"], int)
        # Oldest first → dates monotonic.
        dates = [p["date"] for p in series]
        assert dates == sorted(dates)


# ── Bucketing by created_at datetime ──────────────────────────────

def test_sparklines_buckets_emails_by_day():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    today = datetime.now(timezone.utc)
    # Drop 3 sent emails on yesterday and 2 on today.
    yesterday = today - timedelta(days=1)
    rows = (
        [{"created_at": yesterday}] * 3 +
        [{"created_at": today}] * 2
    )
    fdb.email_send_events.find = MagicMock(return_value=_async_iter(rows))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_sparklines(
                {"id": "u", "is_master_admin": True},
            )
    out = _run(go())
    s = out["series"]["emails_sent"]
    # Map back by date for an exact assertion (avoids "off-by-one"
    # surprises around timezone date-flip).
    by_date = {p["date"]: p["value"] for p in s}
    assert by_date.get(today.date().isoformat()) == 2
    assert by_date.get(yesterday.date().isoformat()) == 3


# ── ISO-string dates (CRM deals historically used strings) ───────

def test_sparklines_buckets_deals_with_iso_string_dates():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    rows = [
        {"created_at": f"{today.isoformat()}T10:00:00+00:00"},
        {"created_at": f"{today.isoformat()}T12:30:00+00:00"},
        {"created_at": f"{yesterday.isoformat()}T08:00:00+00:00"},
    ]
    fdb.crm_deals.find = MagicMock(return_value=_async_iter(rows))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_sparklines(
                {"id": "u", "is_master_admin": True},
            )
    out = _run(go())
    by_date = {p["date"]: p["value"] for p in out["series"]["deals_created"]}
    assert by_date[today.isoformat()] == 2
    assert by_date[yesterday.isoformat()] == 1


# ── Blog-view snapshot accumulates over time ─────────────────────

def test_sparklines_snapshots_blog_views_today():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    # Two published articles with 10 and 15 views.
    fdb.seo_articles.find = MagicMock(side_effect=lambda q, p=None: _async_iter([
        {"metrics": {"views": 10}},
        {"metrics": {"views": 15}},
    ]) if q.get("status") == "published" else _async_iter([]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_sparklines(
                {"id": "u", "is_master_admin": True},
            )
    _run(go())
    # Upsert hit with the right shape.
    fdb.seo_view_snapshots.update_one.assert_awaited()
    call = fdb.seo_view_snapshots.update_one.await_args
    filter_arg, update_arg = call.args[0], call.args[1]
    today = datetime.now(timezone.utc).date().isoformat()
    assert filter_arg == {"date": today}
    assert update_arg["$set"]["total_views"] == 25
    assert call.kwargs.get("upsert") is True


def test_blog_view_series_carries_forward_last_known_value():
    """Days without a snapshot inherit the previous day's total so
    the sparkline line stays continuous instead of dropping to zero."""
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    today = datetime.now(timezone.utc).date()
    # Only days -10 and -3 have a stamp; everything else is implied.
    snaps = [
        {"date": (today - timedelta(days=10)).isoformat(), "total_views": 40},
        {"date": (today - timedelta(days=3)).isoformat(), "total_views": 80},
    ]
    snap_cur = MagicMock()
    snap_cur.to_list = AsyncMock(return_value=snaps)
    fdb.seo_view_snapshots.find = MagicMock(return_value=snap_cur)

    async def go():
        with patch.object(m, "db", fdb):
            return await m._blog_views_series()
    out = _run(go())
    by_date = {p["date"]: p["value"] for p in out}
    # Before day -10 → 0 (no prior snapshot)
    assert by_date[(today - timedelta(days=29)).isoformat()] == 0
    # Day -10 → 40
    assert by_date[(today - timedelta(days=10)).isoformat()] == 40
    # Day -7 → still 40 (no stamp between -10 and -3)
    assert by_date[(today - timedelta(days=7)).isoformat()] == 40
    # Day -3 → 80
    assert by_date[(today - timedelta(days=3)).isoformat()] == 80
    # Day -1 → 80 (carried forward)
    assert by_date[(today - timedelta(days=1)).isoformat()] == 80


# ── _bucket_dates helper ─────────────────────────────────────────

def test_bucket_dates_returns_30_chronological_iso_strings():
    from routes import master_admin_growth_hub as m
    now = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    out = m._bucket_dates(now)
    assert len(out) == 30
    assert out[-1] == "2026-05-27"
    assert out[0] == "2026-04-28"
    # strictly monotonic
    assert all(out[i] < out[i + 1] for i in range(len(out) - 1))


# ── Bucketing tolerance ──────────────────────────────────────────

def test_bucket_count_by_day_skips_rows_without_date_field():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    # Mix valid + None dates — only valid ones should bucket.
    today = datetime.now(timezone.utc)
    rows = [
        {"created_at": today},
        {"created_at": None},
        {},  # missing field
    ]
    fdb.mkt_chat_sessions.find = MagicMock(return_value=_async_iter(rows))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_sparklines(
                {"id": "u", "is_master_admin": True},
            )
    out = _run(go())
    s = out["series"]["chat_sessions"]
    by_date = {p["date"]: p["value"] for p in s}
    assert by_date[today.date().isoformat()] == 1
