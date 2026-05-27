"""Iter 220ae — Distribution Engine tests.

Pins:
  * ``POST articles/{id}/distribute`` is master-admin gated.
  * Happy path: full Claude JSON parsed → linkedin[5] / x_thread / reddit
    stored on ``seo_distributions``.
  * Idempotent: re-running OVERWRITES the previous distribution
    (no stale duplicates per article).
  * Fallback: when the LLM returns empty/unparseable, the response is
    still well-formed — never blanks the UI.
  * LinkedIn array padded to exactly 5 even when Claude under-delivers.
  * X-thread tweets truncated to ≤280 chars each.
  * Channel allow-list enforced — bogus channel names are silently
    dropped, 400 when none remain.
  * 404 when the source article doesn't exist.
  * 400 when the article is archived.
  * ``GET articles/{id}/distributions`` returns null shape when no
    distribution exists.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import _test_backend_url

BASE = _test_backend_url()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db():
    fdb = MagicMock()
    for coll in ("seo_keywords", "seo_articles", "seo_distributions"):
        for op in ("insert_one", "update_one", "delete_one", "delete_many"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
    return fdb


def _published_article(**overrides) -> dict:
    base = {
        "id": "a-1", "slug": "cut-downtime", "status": "published",
        "title": "How to Cut Downtime",
        "excerpt": "A short hook.",
        "body_md": "# How to Cut Downtime\n\nbody",
        "primary_keyword": "gym downtime",
    }
    base.update(overrides)
    return base


# ── Gating ─────────────────────────────────────────────────────────

def test_distribute_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": False}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.distribute_article(
                    "a-1", m.DistributePayload(), user,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_get_distribution_requires_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": False}
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.get_article_distribution("a-1", user)
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


# ── Happy path ─────────────────────────────────────────────────────

def test_distribute_happy_path_stores_full_content():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())

    llm_payload = (
        '{'
        '"linkedin": ['
        '"Hook A\\n\\nBody A\\n\\nhttps://www.gymaxisai.com/blog/cut-downtime\\n\\n#gymops",'
        '"Hook B\\n\\nBody B\\n\\nhttps://www.gymaxisai.com/blog/cut-downtime\\n\\n#fitness",'
        '"Hook C\\n\\nBody C\\n\\nhttps://www.gymaxisai.com/blog/cut-downtime\\n\\n#crm",'
        '"Hook D\\n\\nBody D\\n\\nhttps://www.gymaxisai.com/blog/cut-downtime\\n\\n#ops",'
        '"Hook E\\n\\nBody E\\n\\nhttps://www.gymaxisai.com/blog/cut-downtime\\n\\n#tech"'
        '],'
        '"x_thread": ['
        '"Cut downtime — the playbook",'
        '"1/ Most operators bleed 6h/week.",'
        '"2/ The fix isn\\u2019t more software.",'
        '"3/ Link \\u2192 https://www.gymaxisai.com/blog/cut-downtime"'
        '],'
        '"reddit": {'
        '"title": "Curious how others handle gym equipment downtime",'
        '"body": "## Background\\nWe have ...",'
        '"subreddits": ["gymsnark","personaltraining","smallbusiness"]'
        '}'
        '}'
    )

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=llm_payload)):
            out = await m.distribute_article(
                "a-1", m.DistributePayload(), user,
            )
            assert out["article_id"] == "a-1"
            assert set(out["channels"]) == {"linkedin", "x_thread", "reddit"}
            assert len(out["content"]["linkedin"]) == 5
            assert all(p.startswith("Hook ") for p in out["content"]["linkedin"])
            assert len(out["content"]["x_thread"]) == 4
            assert out["content"]["reddit"]["title"].startswith("Curious")
            assert out["content"]["reddit"]["subreddits"] == [
                "gymsnark", "personaltraining", "smallbusiness",
            ]
            # Idempotent — old rows deleted before insert.
            fdb.seo_distributions.delete_many.assert_awaited_once_with(
                {"article_id": "a-1"},
            )
            fdb.seo_distributions.insert_one.assert_awaited_once()
    _run(go())


def test_distribute_pads_linkedin_to_five_when_llm_under_delivers():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    short_payload = '{"linkedin": ["only one"], "x_thread": [], "reddit": {}}'

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=short_payload)):
            out = await m.distribute_article(
                "a-1", m.DistributePayload(), user,
            )
            assert len(out["content"]["linkedin"]) == 5
            assert out["content"]["linkedin"][0] == "only one"
            # Filler posts mention the title or primary keyword and the link.
            for filler in out["content"]["linkedin"][1:]:
                assert "https://www.gymaxisai.com/blog/" in filler
    _run(go())


def test_distribute_fallback_when_llm_unreachable():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=None)):
            out = await m.distribute_article(
                "a-1", m.DistributePayload(), user,
            )
            assert len(out["content"]["linkedin"]) == 5
            assert len(out["content"]["x_thread"]) >= 1
            assert out["content"]["reddit"]["title"]
            assert out["content"]["reddit"]["body"]
            # Fallback subreddits are still useful.
            assert out["content"]["reddit"]["subreddits"]
    _run(go())


def test_distribute_truncates_long_tweets():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())
    long_tweet = "x" * 400  # > 280 chars
    import json as _json
    payload = _json.dumps({"linkedin": [], "x_thread": [long_tweet], "reddit": {}})

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=payload)):
            out = await m.distribute_article(
                "a-1", m.DistributePayload(), user,
            )
            assert all(len(t) <= 280 for t in out["content"]["x_thread"])
    _run(go())


# ── Channel allow-list ────────────────────────────────────────────

def test_distribute_filters_unknown_channels():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value='{"linkedin": [], "x_thread": [], "reddit": {}}')):
            out = await m.distribute_article(
                "a-1",
                m.DistributePayload(channels=["linkedin", "tiktok"]),
                user,
            )
            assert set(out["channels"]) == {"linkedin"}
            # Only the asked-for channel is in the spun content.
            assert "linkedin" in out["content"]
            assert "x_thread" not in out["content"]
            assert "reddit" not in out["content"]
    _run(go())


def test_distribute_400_when_no_valid_channels():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value=_published_article())

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.distribute_article(
                    "a-1",
                    m.DistributePayload(channels=["tiktok"]),
                    user,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 400
    assert _run(go())


# ── 404 / 400 on the source article ───────────────────────────────

def test_distribute_404_when_article_missing():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()  # find_one returns None by default

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.distribute_article(
                    "no-such-article", m.DistributePayload(), user,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_distribute_400_when_article_archived():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(
        return_value=_published_article(status="archived"),
    )

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.distribute_article(
                    "a-1", m.DistributePayload(), user,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 400
    assert _run(go())


# ── GET endpoint ──────────────────────────────────────────────────

def test_get_distribution_returns_null_when_absent():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.get_article_distribution("a-1", user)
            assert out == {"distribution": None}
    _run(go())


def test_get_distribution_returns_existing_doc():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    existing = {"id": "d-1", "article_id": "a-1",
                "channels": ["linkedin"],
                "content": {"linkedin": ["a", "b", "c", "d", "e"]}}
    fdb = _fake_db()
    fdb.seo_distributions.find_one = AsyncMock(return_value=existing)

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.get_article_distribution("a-1", user)
            assert out["distribution"]["article_id"] == "a-1"
            assert len(out["distribution"]["content"]["linkedin"]) == 5
    _run(go())
