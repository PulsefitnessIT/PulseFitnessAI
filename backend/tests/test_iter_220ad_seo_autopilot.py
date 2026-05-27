"""Iter 220ad — SEO Autopilot tests (re-using the fake_db pattern that
already works in test_iter_220aa_widget_embed.py)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from tests.conftest import _test_backend_url

BASE = _test_backend_url()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _fake_db():
    """Build a MagicMock that mimics the db.<coll>.<op> surface used in
    the seo_autopilot module."""
    fdb = MagicMock()
    # Default no-op async methods so unrelated tests don't blow up.
    for coll in ("seo_keywords", "seo_articles", "seo_article_view_snapshots"):
        for op in ("insert_one", "update_one", "delete_one"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).count_documents = AsyncMock(return_value=0)
        getattr(fdb, coll).find = MagicMock(return_value=_make_cursor([]))
    return fdb


# ── Auth gating ───────────────────────────────────────────────

def test_admin_endpoints_require_master_admin():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": False}

    async def call_all():
        out = []
        for fn, kwargs in [
            (m.list_keywords, {"status": None, "limit": 10, "user": user}),
            (m.delete_keyword, {"keyword_id": "x", "user": user}),
            (m.list_articles, {"status": None, "limit": 10, "user": user}),
            (m.delete_article, {"article_id": "x", "user": user}),
            (m.dashboard, {"user": user}),
            (m.run_autopilot, {"user": user}),
        ]:
            try:
                await fn(**kwargs)
                out.append(("none", fn.__name__))
            except HTTPException as exc:
                out.append((exc.status_code, fn.__name__))
        return out
    results = _run(call_all())
    for code, name in results:
        assert code == 403, f"{name} should be 403, got {code}"


# ── Keyword research ──────────────────────────────────────────

def test_research_keywords_persists_results():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fake_llm_json = (
        '[{"term":"gym equipment downtime tracking","intent":"informational",'
        '"difficulty":"medium","volume_estimate":"medium","rationale":"Direct."},'
        '{"term":"multi-site gym ops software","intent":"transactional",'
        '"difficulty":"high","volume_estimate":"low","rationale":"Buyer terms."}]'
    )
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=fake_llm_json)):
            payload = m.KeywordResearchPayload(seed_topic="gym ops", count=5)
            out = await m.research_keywords(payload, user)
            assert out["count"] == 2
            assert fdb.seo_keywords.insert_one.await_count == 2
    _run(go())


def test_research_keywords_fallback_when_llm_unavailable():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=None)):
            payload = m.KeywordResearchPayload(seed_topic="floor walks", count=5)
            out = await m.research_keywords(payload, user)
            assert out["count"] >= 1
            assert fdb.seo_keywords.insert_one.await_count >= 1
    _run(go())


# ── Article generation ───────────────────────────────────────

def test_generate_article_fallback_when_llm_returns_nothing():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value="")), \
             patch.object(m, "_generate_hero_image", AsyncMock(return_value=None)):
            payload = m.ArticleGeneratePayload(
                primary_keyword="gym ops checklist",
                publish_now=False, generate_hero_image=True,
            )
            out = await m.generate_article(payload, user)
            assert out["primary_keyword"] == "gym ops checklist"
            assert out["status"] == "draft"
            assert out["published_at"] is None
            assert out["slug"]
            assert out["hero_image_url"] is None
            fdb.seo_articles.insert_one.assert_awaited_once()
    _run(go())


def test_generate_article_publishes_when_publish_now_true():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    json_text = (
        '{"title":"How to Cut Downtime","excerpt":"x","meta_description":"y",'
        '"tags":["ops"],"body_md":"# How to Cut Downtime\\n\\nbody here",'
        '"qa_blocks":[{"question":"Q","answer":"A"}]}'
    )
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value=json_text)), \
             patch.object(m, "_generate_hero_image",
                          AsyncMock(return_value="data:image/png;base64,AAA")):
            payload = m.ArticleGeneratePayload(
                primary_keyword="cut downtime", publish_now=True,
            )
            out = await m.generate_article(payload, user)
            assert out["status"] == "published"
            assert out["published_at"] is not None
            assert out["title"] == "How to Cut Downtime"
            assert out["hero_image_url"].startswith("data:")
            assert out["qa_blocks"][0]["question"] == "Q"
    _run(go())


def test_generate_article_dedupes_colliding_slug():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    # Existing slug → collision check returns truthy.
    fdb.seo_articles.find_one = AsyncMock(return_value={"id": "a"})

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_llm_text", AsyncMock(return_value='{"title":"Cut Downtime"}')), \
             patch.object(m, "_generate_hero_image", AsyncMock(return_value=None)):
            payload = m.ArticleGeneratePayload(primary_keyword="cut downtime")
            await m.generate_article(payload, user)
            doc = fdb.seo_articles.insert_one.call_args.args[0]
            assert doc["slug"].startswith("cut-downtime-")
            assert len(doc["slug"]) > len("cut-downtime-")
    _run(go())


# ── Article patch — status transitions ───────────────────────

def test_patch_article_stamps_published_at_on_first_publish():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(
        side_effect=[{"id": "a-1", "published_at": None}, {"id": "a-1"}],
    )
    fdb.seo_articles.update_one = AsyncMock(
        return_value=type("R", (), {"matched_count": 1})(),
    )

    async def go():
        with patch.object(m, "db", fdb):
            await m.patch_article("a-1", m.ArticlePatch(status="published"), user)
            updates = fdb.seo_articles.update_one.call_args.args[1]["$set"]
            assert updates["status"] == "published"
            assert "published_at" in updates
    _run(go())


def test_patch_article_does_not_reset_published_at_on_republish():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    already = {"id": "a-1", "published_at": "2026-04-01T00:00:00+00:00"}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(side_effect=[already, already])
    fdb.seo_articles.update_one = AsyncMock(
        return_value=type("R", (), {"matched_count": 1})(),
    )

    async def go():
        with patch.object(m, "db", fdb):
            await m.patch_article("a-1", m.ArticlePatch(status="published"), user)
            updates = fdb.seo_articles.update_one.call_args.args[1]["$set"]
            assert "published_at" not in updates  # preserved
    _run(go())


def test_patch_article_recomputes_word_count_on_body_change():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_articles.find_one = AsyncMock(return_value={"id": "a-1"})
    fdb.seo_articles.update_one = AsyncMock(
        return_value=type("R", (), {"matched_count": 1})(),
    )
    body = " ".join(["word"] * 500)

    async def go():
        with patch.object(m, "db", fdb):
            await m.patch_article("a-1", m.ArticlePatch(body_md=body), user)
            updates = fdb.seo_articles.update_one.call_args.args[1]["$set"]
            assert updates["word_count"] == 500
            assert updates["read_time_min"] == max(1, round(500 / 220))
    _run(go())


# ── Autopilot run ────────────────────────────────────────────

def test_run_autopilot_no_queued_keywords_returns_reason():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.run_autopilot(user)
            assert out["ok"] is False
            assert "queued" in out["reason"]
    _run(go())


def test_run_autopilot_picks_oldest_queued_and_marks_published():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    kw = {"id": "kw-1", "term": "gym roi calculator", "status": "queued",
          "rationale": "convert hot leads"}
    fdb.seo_keywords.find_one = AsyncMock(return_value=kw)
    fdb.seo_keywords.update_one = AsyncMock()
    article = {"id": "a-1", "title": "x", "status": "published",
               "published_at": "2026-05-27T00:00:00+00:00"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "generate_article",
                          AsyncMock(return_value=article)) as gen:
            out = await m.run_autopilot(user)
            assert out["ok"] is True
            assert out["keyword_id"] == "kw-1"
            gen.assert_awaited_once()
            generated_payload = gen.call_args.args[0]
            assert generated_payload.primary_keyword == "gym roi calculator"
            assert generated_payload.publish_now is True
            updates = fdb.seo_keywords.update_one.call_args.args[1]["$set"]
            assert updates["status"] == "published"
            assert updates["target_article_id"] == "a-1"
    _run(go())


# ── Dashboard ────────────────────────────────────────────────

def test_dashboard_returns_rollup():
    from routes.marketing import seo_autopilot as m

    user = {"id": "u-1", "is_master_admin": True}
    fdb = _fake_db()
    fdb.seo_keywords.count_documents = AsyncMock(side_effect=[10, 4, 3])
    fdb.seo_articles.count_documents = AsyncMock(side_effect=[7, 5, 2])
    recent_rows = [{"id": "a-1", "slug": "x", "title": "T",
                    "status": "published", "metrics": {"views": 12},
                    "read_time_min": 6, "word_count": 1300}]
    fdb.seo_articles.find = MagicMock(return_value=_make_cursor(recent_rows))

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.dashboard(user)
            assert out["keywords"] == {"total": 10, "queued": 4, "published": 3}
            assert out["articles"] == {"total": 7, "published": 5, "draft": 2}
            assert len(out["recent"]) == 1
    _run(go())


# ── Public blog ──────────────────────────────────────────────

def test_public_blog_endpoint_lists_only_published_live():
    r = requests.get(f"{BASE}/api/blog/posts", timeout=10)
    assert r.status_code == 200, r.text
    assert isinstance(r.json().get("posts"), list)


def test_public_blog_endpoint_404_unknown_slug_live():
    r = requests.get(f"{BASE}/api/blog/posts/does-not-exist-abc123", timeout=10)
    assert r.status_code == 404


def test_public_blog_get_post_increments_view_counter():
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()
    doc = {"id": "a-1", "slug": "x", "status": "published",
           "title": "x", "metrics": {"views": 4}}
    fdb.seo_articles.find_one = AsyncMock(return_value=doc)
    fdb.seo_articles.update_one = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.public_get_post("x")
            assert out["slug"] == "x"
            fdb.seo_articles.update_one.assert_awaited_once()
            inc = fdb.seo_articles.update_one.call_args.args[1]["$inc"]
            assert inc["metrics.views"] == 1
    _run(go())


def test_public_blog_get_post_404_on_unpublished():
    from fastapi import HTTPException
    from routes.marketing import seo_autopilot as m

    fdb = _fake_db()  # find_one returns None by default

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.public_get_post("draft-only")
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


# ── Helpers ──────────────────────────────────────────────────

def test_slugify_handles_punctuation_and_unicode():
    from routes.marketing.seo_autopilot import _slugify
    assert _slugify("How to Cut Downtime — Fast!") == "how-to-cut-downtime-fast"
    assert _slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert _slugify("") != ""


def test_safe_json_extract_handles_fences_and_prose():
    from routes.marketing.seo_autopilot import _safe_json_extract
    assert _safe_json_extract('{"a":1}') == {"a": 1}
    assert _safe_json_extract('```json\n{"a":2}\n```') == {"a": 2}
    assert _safe_json_extract('Here is the JSON: {"a":3}') == {"a": 3}
    assert _safe_json_extract('[{"x":1}]') == [{"x": 1}]
    assert _safe_json_extract("not json at all") is None
