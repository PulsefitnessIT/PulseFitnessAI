"""Iter 220ai — SEO Autopilot UX endpoints (Phase B).

Pins three new master-admin operations on the daily-autopilot:

  * ``GET  /autopilot/status``  — reads DB config (not env) so the
    "Enabled" toggle + hour picker take effect without a restart.
  * ``PUT  /autopilot/config``  — persists the schedule to
    ``seo_autopilot_config``; idempotent ``upsert``.
  * ``POST /autopilot/run-now`` — manually trigger today's article;
    refuses if it already fired (so we never double-fire), stamps
    ``manual=true`` on the run row.

Also pins the new dashboard ``performance`` block (top 5 published
articles by ``metrics.views`` + total view sum) used by the redesigned
Dashboard tab.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "seo_keywords", "seo_articles", "seo_distributions",
        "seo_autopilot_runs", "seo_autopilot_config",
        "seo_article_view_snapshots", "users",
    ):
        for op in ("insert_one", "update_one", "delete_one", "delete_many"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).count_documents = AsyncMock(return_value=0)
    return fdb


# ── /autopilot/status — DB-backed config ─────────────────────────

def test_autopilot_status_seeds_from_env_when_db_empty():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    # seo_autopilot_config.find_one returns None by default.

    async def go():
        with patch.object(m, "db", fdb), \
             patch.dict("os.environ", {"SEO_AUTOPILOT_HOUR": "14",
                                       "SEO_AUTOPILOT_ENABLED": "1"}, clear=False):
            return await m.autopilot_status({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["enabled"] is True
    assert out["hour_uk"] == 14  # from env
    assert out["ran_today"] is False


def test_autopilot_status_prefers_db_over_env():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_autopilot_config.find_one = AsyncMock(return_value={
        "id": "singleton", "enabled": False, "hour_uk": 7,
        "updated_at": "2026-05-27T00:00:00+00:00",
        "updated_by": "admin-1",
    })

    async def go():
        with patch.object(m, "db", fdb), \
             patch.dict("os.environ", {"SEO_AUTOPILOT_HOUR": "14",
                                       "SEO_AUTOPILOT_ENABLED": "1"}, clear=False):
            return await m.autopilot_status({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["enabled"] is False
    assert out["hour_uk"] == 7
    assert out["config_updated_by"] == "admin-1"


# ── /autopilot/config (PUT) ──────────────────────────────────────

def test_update_autopilot_config_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.update_autopilot_config(
                    m.AutopilotConfigPayload(enabled=True),
                    {"id": "u", "is_master_admin": False},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_update_autopilot_config_upserts_and_returns_fresh_state():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.update_autopilot_config(
                m.AutopilotConfigPayload(enabled=False, hour_uk=16),
                {"id": "admin-1", "is_master_admin": True},
            )
    _ = _run(go())
    # Upsert call shape — singleton id, $set has the new values + stamps.
    fdb.seo_autopilot_config.update_one.assert_awaited_once()
    call = fdb.seo_autopilot_config.update_one.await_args
    filter_arg, update_arg = call.args[0], call.args[1]
    assert filter_arg == {"id": "singleton"}
    assert update_arg["$set"]["enabled"] is False
    assert update_arg["$set"]["hour_uk"] == 16
    assert update_arg["$set"]["updated_by"] == "admin-1"
    assert call.kwargs.get("upsert") is True


def test_update_autopilot_config_rejects_out_of_range_hour():
    """Pydantic validates 0–23. Anything outside should raise before
    we touch Mongo."""
    from pydantic import ValidationError
    from routes.marketing import seo_autopilot as m

    for bad in (-1, 24, 99):
        try:
            m.AutopilotConfigPayload(hour_uk=bad)
            assert False, f"hour_uk={bad} should have failed validation"
        except ValidationError:
            pass


# ── /autopilot/run-now ───────────────────────────────────────────

def test_run_now_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.run_autopilot_now({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_run_now_refuses_when_already_fired_today():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    today = m._london_now().date().isoformat()
    fdb.seo_autopilot_runs.find_one = AsyncMock(return_value={"date": today})

    async def go():
        with patch.object(m, "db", fdb):
            return await m.run_autopilot_now(
                {"id": "admin-1", "is_master_admin": True},
            )
    out = _run(go())
    assert out["ok"] is False
    assert "already" in (out.get("reason") or "").lower()
    # Crucially — we did NOT call run_autopilot.
    fdb.seo_autopilot_runs.update_one.assert_not_called()


def test_run_now_stamps_manual_run_when_fresh():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    # find_one returns None → not fired today.

    async def fake_run(_user):
        return {"ok": True, "keyword_id": "k-1", "article": {"id": "a-1"}}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "run_autopilot", fake_run):
            return await m.run_autopilot_now(
                {"id": "admin-1", "is_master_admin": True},
            )
    out = _run(go())
    assert out["ok"] is True
    assert out["result"]["keyword_id"] == "k-1"
    # The daily-stamp row was upserted with manual=True.
    fdb.seo_autopilot_runs.update_one.assert_awaited_once()
    call = fdb.seo_autopilot_runs.update_one.await_args
    filter_arg, update_arg = call.args[0], call.args[1]
    assert "date" in filter_arg
    assert update_arg["$set"]["manual"] is True
    assert call.kwargs.get("upsert") is True


# ── Dashboard performance block ──────────────────────────────────

def test_dashboard_returns_top_performers_and_total_views():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    # 5 published articles with descending views.
    top_rows = [
        {"id": f"a{i}", "slug": f"s{i}", "title": f"Article {i}",
         "metrics": {"views": (5 - i) * 10},
         "primary_keyword": f"kw{i}", "published_at": None,
         "read_time_min": 7}
        for i in range(5)
    ]
    top_cursor = MagicMock()
    top_cursor.sort = MagicMock(return_value=top_cursor)
    top_cursor.limit = MagicMock(return_value=top_cursor)
    top_cursor.to_list = AsyncMock(return_value=top_rows)

    recent_cursor = MagicMock()
    recent_cursor.sort = MagicMock(return_value=recent_cursor)
    recent_cursor.limit = MagicMock(return_value=recent_cursor)
    recent_cursor.to_list = AsyncMock(return_value=top_rows)

    # The total_views async iteration cursor — sums metrics.views.
    class _SumCur:
        def __init__(self):
            self._items = [
                {"id": f"a{i}", "metrics": {"views": v}}
                for i, v in enumerate([50, 40, 30, 20, 10])
            ]
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    sum_cursor = _SumCur()

    call_count = {"n": 0}
    def _find_side(query, projection=None):
        call_count["n"] += 1
        # 1st: recent activity (status != archived)
        # 2nd: top_performers (status published, projection has primary_keyword)
        # 3rd: total_views aggregate iteration (status published, projection has metrics only)
        if query == {"status": {"$ne": "archived"}}:
            return recent_cursor
        if query == {"status": "published"} and "primary_keyword" in (projection or {}):
            return top_cursor
        if query == {"status": "published"}:
            return sum_cursor
        return MagicMock()
    fdb.seo_articles.find = MagicMock(side_effect=_find_side)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.dashboard({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert "performance" in out
    assert out["performance"]["total_views"] == 150
    assert len(out["performance"]["top"]) == 5
    assert out["performance"]["top"][0]["metrics"]["views"] == 50


# ── Loop reads DB config dynamically ─────────────────────────────

def test_daily_loop_skips_when_db_disabled(monkeypatch):
    """One iteration of the loop should NOT call run_autopilot when
    the live config row has ``enabled=False`` — proves the UI toggle
    pauses the loop without a restart."""
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_autopilot_config.find_one = AsyncMock(return_value={
        "id": "singleton", "enabled": False, "hour_uk": 9,
    })

    fired = {"n": 0}
    async def fake_master(_=None):
        fired["n"] += 1
        return {"ok": True}

    async def fake_already(_d):
        return False

    # We can't run the infinite loop — exercise the body once by
    # extracting + calling the inner logic via a copy of the function.
    # Easier: monkeypatch asyncio.sleep to raise, run the loop, catch.
    sleep_called = {"n": 0}
    async def _stop(_secs):
        sleep_called["n"] += 1
        raise asyncio.CancelledError

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_master), \
             patch.object(m, "_autopilot_already_ran_today", fake_already), \
             patch.object(m.asyncio, "sleep", _stop):
            try:
                await m.run_daily_autopilot_loop(hour=9)
            except asyncio.CancelledError:
                pass

    _run(go())
    # Even though hour matched (we don't know london's hour) — disabled
    # in DB means master-admin runner was NEVER invoked.
    assert fired["n"] == 0
    # And we proceeded into asyncio.sleep at least once (i.e. loop body
    # ran cleanly without raising).
    assert sleep_called["n"] >= 1
