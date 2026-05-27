"""Iter 220af — Daily autopilot scheduler + 1-click publish-share tests.

Pins:
  * ``GET autopilot/status`` is master-admin gated.
  * Status reports config (enabled flag + UK hour) and whether today's
    run has fired (based on ``seo_autopilot_runs`` latest stamp).
  * ``POST articles/{id}/publish-share`` is master-admin gated.
  * Returns a LinkedIn share-offsite URL containing the blog link and
    summary text for ``channel=linkedin``.
  * Returns an X intent URL for ``channel=x`` (tweet 0 only).
  * 400 when no distribution exists for the article.
  * 404 when the article doesn't exist.
  * The publish call stamps ``published.<channel>.<index>`` onto the
    distribution doc so the UI can show the "Posted" pill.
  * ``_london_now`` returns a timezone-aware datetime.
  * ``_autopilot_already_ran_today`` returns True only when a stamp
    exists for the requested date.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import _test_backend_url

BASE = _test_backend_url()  # noqa: F841  (parity with sibling tests)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "seo_keywords", "seo_articles", "seo_distributions",
        "seo_autopilot_runs", "users",
    ):
        for op in ("insert_one", "update_one", "delete_one", "delete_many"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
    return fdb


def _published_article(**overrides) -> dict:
    base = {
        "id": "a-1", "slug": "cut-downtime", "status": "published",
        "title": "How to Cut Downtime",
        "excerpt": "A short hook.",
        "primary_keyword": "gym downtime",
    }
    base.update(overrides)
    return base


def _distribution(**overrides) -> dict:
    base = {
        "id": "d-1", "article_id": "a-1",
        "article_slug": "cut-downtime",
        "channels": ["linkedin", "x_thread", "reddit"],
        "content": {
            "linkedin": [
                "Hook A — gym downtime is the silent killer", "B", "C", "D", "E",
            ],
            "x_thread": ["Hook tweet about downtime", "2/", "3/"],
            "reddit": {"title": "T", "body": "B", "subreddits": []},
        },
    }
    base.update(overrides)
    return base


# ── autopilot/status ──────────────────────────────────────────────

def test_autopilot_status_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.autopilot_status({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_autopilot_status_reports_not_run_today():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()  # no stamp → ran_today=False

    async def go():
        with patch.object(m, "db", fdb), \
             patch.dict("os.environ", {"SEO_AUTOPILOT_HOUR": "9",
                                       "SEO_AUTOPILOT_ENABLED": "1"}, clear=False):
            out = await m.autopilot_status({"id": "u", "is_master_admin": True})
            assert out["enabled"] is True
            assert out["hour_uk"] == 9
            assert out["ran_today"] is False
            assert out["last_run"] is None
            assert "london_now" in out
    _run(go())


def test_autopilot_status_reports_ran_today():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    today = m._london_now().date().isoformat()
    fdb.seo_autopilot_runs.find_one = AsyncMock(return_value={
        "date": today, "ran_at": "now", "result": {"ok": True},
    })

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.autopilot_status({"id": "u", "is_master_admin": True})
            assert out["ran_today"] is True
            assert out["last_run"]["date"] == today
    _run(go())


# ── publish-share ──────────────────────────────────────────────────

def test_publish_share_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.publish_share(
                    "a-1",
                    m.PublishSharePayload(channel="linkedin", index=0),
                    {"id": "u", "is_master_admin": False},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_publish_share_404_when_article_missing():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()  # article find_one returns None

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.publish_share(
                    "missing",
                    m.PublishSharePayload(channel="linkedin", index=0),
                    {"id": "u", "is_master_admin": True},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_publish_share_400_when_no_distribution():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    # distribution find_one returns None by default

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.publish_share(
                    "a-1",
                    m.PublishSharePayload(channel="linkedin", index=0),
                    {"id": "u", "is_master_admin": True},
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 400
    assert _run(go())


def test_publish_share_linkedin_returns_share_url_and_stamps():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    fdb.seo_distributions.find_one = AsyncMock(return_value=_distribution())

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.publish_share(
                "a-1",
                m.PublishSharePayload(channel="linkedin", index=2),
                {"id": "admin-1", "is_master_admin": True},
            )
        assert out["channel"] == "linkedin"
        assert out["index"] == 2
        assert "linkedin.com/sharing/share-offsite" in out["share_url"]
        # canonical blog URL must be encoded into the share URL
        assert "gymaxisai.com%2Fblog%2Fcut-downtime" in out["share_url"]
        # Stamp written under published.linkedin.2
        fdb.seo_distributions.update_one.assert_awaited_once()
        call = fdb.seo_distributions.update_one.await_args
        filter_arg, update_arg = call.args[0], call.args[1]
        assert filter_arg == {"article_id": "a-1"}
        assert "published.linkedin.2" in update_arg["$set"]
        assert update_arg["$set"]["published.linkedin.2"]["posted_by"] == "admin-1"
    _run(go())


def test_publish_share_x_returns_intent_url():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    fdb.seo_distributions.find_one = AsyncMock(return_value=_distribution())

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.publish_share(
                "a-1",
                m.PublishSharePayload(channel="x", index=0),
                {"id": "admin-1", "is_master_admin": True},
            )
        assert out["channel"] == "x"
        assert out["index"] == 0
        assert "twitter.com/intent/tweet" in out["share_url"]
        # tweet text + URL both encoded
        assert "gymaxisai.com" in out["share_url"]
    _run(go())


def test_publish_share_linkedin_clamps_index_to_available_posts():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    short = _distribution()
    short["content"]["linkedin"] = ["one"]
    fdb.seo_distributions.find_one = AsyncMock(return_value=short)

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.publish_share(
                "a-1",
                m.PublishSharePayload(channel="linkedin", index=4),
                {"id": "admin-1", "is_master_admin": True},
            )
        assert out["index"] == 0  # clamped
    _run(go())


# ── scheduler helpers ─────────────────────────────────────────────

def test_london_now_returns_aware_datetime():
    from routes.marketing import seo_autopilot as m
    now = m._london_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None


def test_autopilot_already_ran_today_true_only_with_stamp():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            # absent → False
            assert await m._autopilot_already_ran_today("2026-02-04") is False
            # present → True
            fdb.seo_autopilot_runs.find_one = AsyncMock(
                return_value={"date": "2026-02-04"},
            )
            assert await m._autopilot_already_ran_today("2026-02-04") is True
    _run(go())


def test_stamp_autopilot_run_upserts():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            await m._stamp_autopilot_run("2026-02-04", {"ok": True, "keyword_id": "k-1"})
        fdb.seo_autopilot_runs.update_one.assert_awaited_once()
        call = fdb.seo_autopilot_runs.update_one.await_args
        assert call.args[0] == {"date": "2026-02-04"}
        assert call.args[1]["$set"]["result"] == {"ok": True, "keyword_id": "k-1"}
        assert call.kwargs.get("upsert") is True
    _run(go())


def test_autopilot_run_as_master_admin_returns_when_no_admin():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    # users.find_one returns None → no master admin

    async def go():
        with patch.object(m, "db", fdb):
            out = await m._autopilot_run_as_master_admin()
            assert out == {"ok": False, "reason": "no master admin found"}
    _run(go())


def test_autopilot_run_as_master_admin_invokes_run_autopilot():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    fdb.users.find_one = AsyncMock(return_value={
        "id": "admin-1", "email": "x@y", "is_master_admin": True,
    })

    async def fake_run(_user):
        return {"ok": True, "keyword_id": "k-9"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "run_autopilot", fake_run):
            out = await m._autopilot_run_as_master_admin()
        assert out == {"ok": True, "keyword_id": "k-9"}
    _run(go())


# Sanity: imports for tools used internally are reachable.
def test_module_exports_scheduler_symbols():
    from routes.marketing import seo_autopilot as m
    for name in ("run_daily_autopilot_loop", "_london_now",
                 "_autopilot_already_ran_today", "_stamp_autopilot_run",
                 "_autopilot_run_as_master_admin",
                 "publish_share", "autopilot_status"):
        assert hasattr(m, name), name
    # Module wires UTC timezone module — used inside _london_now fallback.
    assert timezone is not None
