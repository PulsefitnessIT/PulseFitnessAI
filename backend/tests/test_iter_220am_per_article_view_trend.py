"""Iter 220am — Per-article view trend.

Pins:

  * Dashboard now writes a daily snapshot per published article into
    ``seo_article_view_snapshots`` (idempotent upsert on
    ``{article_id, date}``) and surfaces a ``trend`` block on every
    top-performer row.
  * Brand-new articles (no prior snapshot) return ``is_new: True`` and
    ``delta_pct: None`` so the UI can render "+N new" instead of a
    percent change (which is mathematically undefined).
  * Articles with a 7-day-prior snapshot return ``delta_pct`` as a
    rounded percent so the UI can show "+47% wk".
  * ``GET /articles/{id}/view-trend?days=N`` returns a continuous
    daily series with gap-day carry-forward and a live tail-snap to
    today's running counter.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, items): self._items = list(items)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    return _Cur(items)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "seo_keywords", "seo_articles", "seo_distributions",
        "seo_autopilot_runs", "seo_autopilot_config",
        "seo_article_view_snapshots", "users",
    ):
        c = getattr(fdb, coll)
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()
        c.find_one = AsyncMock(return_value=None)
        c.count_documents = AsyncMock(return_value=0)
    return fdb


def _build_top_cursor(rows):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=rows)
    return cur


# ── Dashboard now writes snapshots + decorates top performers ────

def test_dashboard_snapshots_each_published_article_today():
    """Every dashboard fetch upserts today's snapshot row for every
    published article. Idempotent — re-fetching the same minute
    doesn't double-record."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    today_iso = m._london_now().date().isoformat()

    published_rows = [
        {"id": "a1", "metrics": {"views": 100},
         "slug": "s1", "title": "A1", "primary_keyword": "kw1",
         "published_at": None, "read_time_min": 5},
        {"id": "a2", "metrics": {"views": 50},
         "slug": "s2", "title": "A2", "primary_keyword": "kw2",
         "published_at": None, "read_time_min": 5},
    ]

    # recent + top + total-views cursor all read from the same find
    # call. Easiest: dispatch by projection shape.
    def _find_side(query, projection=None):
        if query == {"status": {"$ne": "archived"}}:
            return _build_top_cursor(published_rows)
        if query == {"status": "published"} and "primary_keyword" in (projection or {}):
            return _build_top_cursor(published_rows)
        if query == {"status": "published"}:
            return _async_iter([{"id": r["id"], "metrics": r["metrics"]} for r in published_rows])
        return _build_top_cursor([])
    fdb.seo_articles.find = MagicMock(side_effect=_find_side)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.dashboard({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["performance"]["total_views"] == 150
    # Each published article should have triggered a snapshot upsert.
    calls = fdb.seo_article_view_snapshots.update_one.await_args_list
    assert len(calls) == 2
    seen_ids = set()
    for c in calls:
        filter_arg, update_arg = c.args[0], c.args[1]
        assert filter_arg["date"] == today_iso
        seen_ids.add(filter_arg["article_id"])
        assert update_arg["$set"]["views"] in (100, 50)
        assert c.kwargs.get("upsert") is True
    assert seen_ids == {"a1", "a2"}


def test_dashboard_marks_brand_new_articles_with_is_new_flag():
    """No prior snapshot → ``is_new: True``, ``delta_pct: None``,
    ``delta_abs`` = current views."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    rows = [{
        "id": "a1", "metrics": {"views": 12},
        "slug": "s1", "title": "A1", "primary_keyword": "kw1",
        "published_at": None, "read_time_min": 5,
    }]
    def _find_side(query, projection=None):
        if query == {"status": {"$ne": "archived"}}:
            return _build_top_cursor(rows)
        if query == {"status": "published"} and "primary_keyword" in (projection or {}):
            return _build_top_cursor(rows)
        if query == {"status": "published"}:
            return _async_iter([{"id": r["id"], "metrics": r["metrics"]} for r in rows])
        return _build_top_cursor([])
    fdb.seo_articles.find = MagicMock(side_effect=_find_side)
    # No prior snapshot.
    fdb.seo_article_view_snapshots.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.dashboard({"id": "u", "is_master_admin": True})
    out = _run(go())
    trend = out["performance"]["top"][0]["trend"]
    assert trend["is_new"] is True
    assert trend["views_7d_ago"] == 0
    assert trend["delta_abs"] == 12
    assert trend["delta_pct"] is None


def test_dashboard_computes_weekly_percent_delta():
    """7-day-prior snapshot returns a rounded percent change."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    rows = [{
        "id": "a1", "metrics": {"views": 147},
        "slug": "s1", "title": "A1", "primary_keyword": "kw1",
        "published_at": None, "read_time_min": 5,
    }]
    def _find_side(query, projection=None):
        if query == {"status": {"$ne": "archived"}}:
            return _build_top_cursor(rows)
        if query == {"status": "published"} and "primary_keyword" in (projection or {}):
            return _build_top_cursor(rows)
        if query == {"status": "published"}:
            return _async_iter([{"id": r["id"], "metrics": r["metrics"]} for r in rows])
        return _build_top_cursor([])
    fdb.seo_articles.find = MagicMock(side_effect=_find_side)
    # 7-day-prior snapshot: 100 views. Today: 147 → +47%.
    fdb.seo_article_view_snapshots.find_one = AsyncMock(
        return_value={"views": 100, "date": "2026-05-20"},
    )

    async def go():
        with patch.object(m, "db", fdb):
            return await m.dashboard({"id": "u", "is_master_admin": True})
    out = _run(go())
    trend = out["performance"]["top"][0]["trend"]
    assert trend["is_new"] is False
    assert trend["views_7d_ago"] == 100
    assert trend["delta_abs"] == 47
    assert trend["delta_pct"] == 47.0


def test_dashboard_handles_zero_baseline_with_zero_current():
    """Edge case — both baseline and current are 0. We should return
    ``delta_pct: None`` and ``is_new: False`` so the UI doesn't
    miscategorise as brand new."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    rows = [{
        "id": "a1", "metrics": {"views": 0},
        "slug": "s1", "title": "A1", "primary_keyword": "kw1",
        "published_at": None, "read_time_min": 5,
    }]
    def _find_side(query, projection=None):
        if query == {"status": {"$ne": "archived"}}:
            return _build_top_cursor(rows)
        if query == {"status": "published"} and "primary_keyword" in (projection or {}):
            return _build_top_cursor(rows)
        if query == {"status": "published"}:
            return _async_iter([{"id": r["id"], "metrics": r["metrics"]} for r in rows])
        return _build_top_cursor([])
    fdb.seo_articles.find = MagicMock(side_effect=_find_side)
    # Snapshot exists from 7d ago at 0 views (the article was published
    # but no one read it). Today still 0 → delta = 0, pct undefined.
    fdb.seo_article_view_snapshots.find_one = AsyncMock(
        return_value={"views": 0, "date": "2026-05-20"},
    )

    async def go():
        with patch.object(m, "db", fdb):
            return await m.dashboard({"id": "u", "is_master_admin": True})
    trend = _run(go())["performance"]["top"][0]["trend"]
    assert trend["is_new"] is False  # we have a snapshot
    assert trend["delta_pct"] is None  # baseline = 0
    assert trend["delta_abs"] == 0


# ── /articles/{id}/view-trend ────────────────────────────────────


def test_view_trend_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.article_view_trend("a1", 30, {"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_view_trend_404_when_article_missing():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.article_view_trend("a-missing", 30, {"id": "u", "is_master_admin": True})
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_view_trend_returns_continuous_series_with_carry_forward():
    """Days with no snapshot inherit the previous known value; today
    is tail-snapped to the article's live ``metrics.views`` so the
    last point is always current."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value={
        "id": "a1", "metrics": {"views": 200},
    })
    today = m._london_now().date()
    snaps = [
        {"date": (today - timedelta(days=20)).isoformat(), "views": 40},
        {"date": (today - timedelta(days=5)).isoformat(), "views": 150},
    ]
    snap_cur = MagicMock()
    snap_cur.to_list = AsyncMock(return_value=snaps)
    fdb.seo_article_view_snapshots.find = MagicMock(return_value=snap_cur)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.article_view_trend("a1", 30, {"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["days"] == 30
    assert len(out["series"]) == 30
    by_date = {p["date"]: p["views"] for p in out["series"]}
    # Day -25 → 0 (no snapshot before -20)
    assert by_date[(today - timedelta(days=25)).isoformat()] == 0
    # Day -20 → 40
    assert by_date[(today - timedelta(days=20)).isoformat()] == 40
    # Day -10 → still 40 (carry-forward)
    assert by_date[(today - timedelta(days=10)).isoformat()] == 40
    # Day -5 → 150
    assert by_date[(today - timedelta(days=5)).isoformat()] == 150
    # Today → 200 (tail-snap to live counter)
    assert by_date[today.isoformat()] == 200


def test_view_trend_clamps_days_to_safe_range():
    """``days`` is clamped to 1..90 — protects from accidental queries
    that would scan the entire collection."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value={
        "id": "a1", "metrics": {"views": 0},
    })
    snap_cur = MagicMock()
    snap_cur.to_list = AsyncMock(return_value=[])
    fdb.seo_article_view_snapshots.find = MagicMock(return_value=snap_cur)

    async def too_big():
        with patch.object(m, "db", fdb):
            return await m.article_view_trend("a1", 9999, {"id": "u", "is_master_admin": True})
    out = _run(too_big())
    assert out["days"] == 90

    async def too_small():
        with patch.object(m, "db", fdb):
            return await m.article_view_trend("a1", 0, {"id": "u", "is_master_admin": True})
    out = _run(too_small())
    assert out["days"] == 1
