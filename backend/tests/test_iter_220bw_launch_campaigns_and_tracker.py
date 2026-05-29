"""Iter 220bw — Social Autopilot launch campaigns + IG tracker.

Covers:

  1. Launch archetypes registered (feature_reveal, problem_solution_story,
     built_by_ops) + deterministic round-robin pick.
  2. ``should_use_launch_tone(0.7, n)`` is the 70/30 blend predicted —
     7 of every 10 posts are on-campaign.
  3. ``build_launch_prompt`` injects the campaign name, keywords, and
     the archetype instruction, AND explicitly forbids the
     "established-platform" voice (no fake metrics, no "X hours saved").
  4. ``generate_post_for_channel`` stamps the campaign metadata onto
     the saved doc when an active launch campaign exists.
  5. Tracker URL-platform detection (instagram/tiktok/linkedin).
  6. OpenGraph engagement parser handles the real IG/TikTok preview
     shapes — likes, comments, caption snippet.
  7. ``fetch_public_post`` returns ``blocked`` (not raises) when IG
     shows the login wall and ``failed`` (not raises) on 5xx.
  8. ``crawl_due_tracked_posts`` appends an engagement history entry
     per row + caps history at 60 entries.
  9. Campaign CRUD + activation enforces the "one active campaign of
     a given type" singleton invariant.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


_ADMIN = {"id": "u-admin", "is_master_admin": True, "email": "admin@x"}


# ══════════════════ 1 · Launch archetypes registered ═════════════════


def test_launch_archetypes_registered():
    from utils import social_autopilot as m
    ids = {a["id"] for a in m.LAUNCH_ARCHETYPES}
    assert ids == {"feature_reveal", "problem_solution_story", "built_by_ops"}
    for a in m.LAUNCH_ARCHETYPES:
        assert a["instruction"]
        assert "{feature}" in a["instruction"] or "{feature}" in a["card_headline_hint"]


def test_pick_launch_archetype_round_robins():
    from utils import social_autopilot as m
    picks = [m.pick_launch_archetype(i)["id"] for i in range(7)]
    # 3 archetypes — first 3 distinct, then cycle.
    assert picks[0] != picks[1] != picks[2]
    assert picks[3] == picks[0]
    assert picks[4] == picks[1]


# ══════════════════ 2 · 70/30 blend predicate ════════════════════════


def test_should_use_launch_tone_70_30_split():
    from utils.social_autopilot import should_use_launch_tone
    # Over a cycle of 10 posts at blend 0.7 → 7 launch, 3 established.
    counts = [should_use_launch_tone(0.7, i) for i in range(10)]
    assert sum(counts) == 7
    # First 7 positions are on-campaign, last 3 are off — predictable.
    assert counts[:7] == [True] * 7
    assert counts[7:] == [False] * 3


def test_should_use_launch_tone_edge_cases():
    from utils.social_autopilot import should_use_launch_tone
    # blend=0 → always established.
    assert not any(should_use_launch_tone(0.0, i) for i in range(15))
    # blend=1 → always launch.
    assert all(should_use_launch_tone(1.0, i) for i in range(15))
    # blend=0.5 → half + half across a cycle.
    counts = [should_use_launch_tone(0.5, i) for i in range(10)]
    assert sum(counts) == 5


# ══════════════════ 3 · build_launch_prompt safeguards ═══════════════


def test_build_launch_prompt_forbids_established_voice():
    """The post is for a BRAND NEW platform — must never claim
    track-record metrics like '4 hours saved' or 'cut dispatch by 30%'."""
    from utils.social_autopilot import (
        build_launch_prompt, channel_by_id, pick_launch_archetype,
    )
    ch = channel_by_id("instagram")
    topic = {"topic_id": "f-1", "kind": "feature", "label": "GymAxis Schedule",
             "hook": "Smart engineer dispatch."}
    campaign = {
        "id": "c-1", "name": "GymAxis Launch Week",
        "type": "launch", "blend_ratio": 0.7,
        "keywords": ["launch", "early access", "ops-first"],
    }
    prompt = build_launch_prompt(ch, topic, campaign, pick_launch_archetype(0))
    # Explicit anti-hallucination guardrail.
    assert "BRAND NEW" in prompt or "brand new" in prompt.lower()
    assert "DO NOT" in prompt or "do not" in prompt.lower()
    # Campaign name + keywords woven in.
    assert "GymAxis Launch Week" in prompt
    for kw in ("early access", "ops-first"):
        assert kw in prompt
    # Archetype instruction embedded.
    assert "FEATURE-REVEAL" in prompt or "feature-reveal" in prompt.lower()


def test_build_launch_prompt_tiktok_includes_video_script_schema():
    from utils.social_autopilot import (
        build_launch_prompt, channel_by_id, pick_launch_archetype,
    )
    ch = channel_by_id("tiktok")
    topic = {"topic_id": "f-1", "kind": "feature", "label": "Tenders AI",
             "hook": "Tender Q&A in minutes."}
    campaign = {"id": "c-1", "name": "Launch", "type": "launch",
                "blend_ratio": 0.7, "keywords": []}
    prompt = build_launch_prompt(ch, topic, campaign, pick_launch_archetype(0))
    assert "video_script" in prompt
    assert "12-15 second" in prompt


# ══════════════════ 4 · generate_post_for_channel stamps campaign ═══


def test_generate_post_stamps_campaign_when_active():
    """When the active campaign blend says "use launch tone for this
    post", the saved doc should carry the campaign id + archetype id
    in generation_meta."""
    from utils import social_autopilot as m

    fdb = MagicMock()
    # 0 existing posts → position 0 → on-campaign (blend 0.7).
    fdb.social_autopilot_posts.count_documents = AsyncMock(return_value=0)
    fdb.social_autopilot_posts.insert_one = AsyncMock()
    fdb.social_autopilot_campaigns.find_one = AsyncMock(return_value={
        "id": "camp-1", "name": "GymAxis Launch Week",
        "type": "launch", "status": "active", "blend_ratio": 0.7,
        "keywords": ["early access", "ops-first"],
    })
    # Stub pick_topic_for to control the topic kind.
    async def _topic(_db, _channel):
        return {"topic_id": "f-1", "kind": "feature",
                "label": "GymAxis Schedule", "hook": "Smart dispatch."}

    # Stub the LLM call to return the parsed JSON dict directly
    # (matches the real ``_llm_chat`` contract).
    async def _llm(_prompt):
        return {
            "caption": "Launching",
            "hashtags": ["#one", "#two"],
            "image_brief": "brief",
            "card_headline": "Just shipped",
            "video_script": None,
        }

    async def go():
        with patch.object(m, "pick_topic_for", side_effect=_topic), \
             patch.object(m, "_llm_chat", side_effect=_llm), \
             patch.object(m, "render_branded_card_to_data_url",
                          AsyncMock(return_value=("data:image/png;base64,xxx", "card"))), \
             patch.object(m, "render_nano_banana_image",
                          AsyncMock(return_value=None)):
            return await m.generate_post_for_channel(fdb, "instagram")
    out = _run(go())

    assert out["generation_meta"]["on_campaign"] is True
    assert out["generation_meta"]["campaign_id"] == "camp-1"
    assert out["generation_meta"]["campaign_name"] == "GymAxis Launch Week"
    assert out["generation_meta"]["campaign_archetype"] in {
        "feature_reveal", "problem_solution_story", "built_by_ops",
    }


def test_generate_post_no_campaign_uses_established_prompt():
    """No active launch campaign → on_campaign=False, campaign_id=None."""
    from utils import social_autopilot as m

    fdb = MagicMock()
    fdb.social_autopilot_posts.count_documents = AsyncMock(return_value=0)
    fdb.social_autopilot_posts.insert_one = AsyncMock()
    fdb.social_autopilot_campaigns.find_one = AsyncMock(return_value=None)

    async def _topic(_db, _channel):
        return {"topic_id": "f-1", "kind": "feature",
                "label": "X", "hook": "y"}

    async def _llm(_prompt):
        return {
            "caption": "Hi",
            "hashtags": ["#a", "#b"],
            "image_brief": "b",
            "card_headline": "H",
            "video_script": None,
        }

    async def go():
        with patch.object(m, "pick_topic_for", side_effect=_topic), \
             patch.object(m, "_llm_chat", side_effect=_llm), \
             patch.object(m, "render_branded_card_to_data_url",
                          AsyncMock(return_value=("data:image/png;base64,xxx", "card"))), \
             patch.object(m, "render_nano_banana_image",
                          AsyncMock(return_value=None)):
            return await m.generate_post_for_channel(fdb, "instagram")
    out = _run(go())
    assert out["generation_meta"]["on_campaign"] is False
    assert out["generation_meta"]["campaign_id"] is None


# ══════════════════ 5 · Platform detection ═══════════════════════════


def test_detect_platform_handles_all_supported():
    from utils.social_tracker import detect_platform
    assert detect_platform("https://www.instagram.com/p/DYfu35JNbkJ/") == "instagram"
    assert detect_platform("https://instagram.com/p/x/") == "instagram"
    assert detect_platform("https://www.tiktok.com/@gymaxis/video/1234") == "tiktok"
    assert detect_platform("https://www.linkedin.com/posts/x") == "linkedin"
    assert detect_platform("https://twitter.com/x") is None
    assert detect_platform("") is None
    assert detect_platform("not-a-url") is None


# ══════════════════ 6 · OG / engagement parsing ══════════════════════


def test_parse_engagement_extracts_likes_comments_caption():
    from utils.social_tracker import parse_engagement_from_html
    # Realistic IG shape — they use property=og:description with a
    # leading "N Likes, M Comments — caption" string.
    html = """
    <html><head>
      <meta property="og:title" content="GymAxis (@gymaxis) on Instagram" />
      <meta property="og:description" content='1,234 likes, 56 comments - GymAxis (@gymaxis) on Instagram: "Launch week is here. Smart engineer dispatch is live."' />
      <meta property="og:image" content="https://scontent.cdninstagram.com/v/x.jpg" />
    </head></html>
    """
    out = parse_engagement_from_html(html)
    assert out["likes"] == 1234
    assert out["comments"] == 56
    assert "Launch week is here" in out["caption_snippet"]
    assert out["preview_image_url"].endswith(".jpg")


def test_parse_engagement_handles_tiktok_shape():
    from utils.social_tracker import parse_engagement_from_html
    html = '''
    <meta property="og:title" content="GymAxis on TikTok" />
    <meta property="og:description" content='4,567 Likes, 89 Comments, 12 Shares. TikTok video from GymAxis: "Built by ops people, for ops people."' />
    '''
    out = parse_engagement_from_html(html)
    assert out["likes"] == 4567
    assert out["comments"] == 89
    assert out["shares"] == 12


def test_parse_engagement_returns_empty_on_garbage_html():
    from utils.social_tracker import parse_engagement_from_html
    assert parse_engagement_from_html("") == {}
    assert parse_engagement_from_html("<html><body>nothing</body></html>") == {}


# ══════════════════ 7 · fetch_public_post failure modes ══════════════


def test_fetch_public_post_marks_blocked_on_401():
    from utils import social_tracker as m
    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = ""
    fake_response.url = "https://www.instagram.com/p/x/"

    async def go():
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_response),
        ))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch.object(m, "httpx") as fake_httpx:
            fake_httpx.AsyncClient = MagicMock(return_value=ctx)
            return await m.fetch_public_post("https://x")
    out = _run(go())
    assert out["status"] == "blocked"
    assert out["http_status"] == 401


def test_fetch_public_post_marks_blocked_on_login_wall_redirect():
    from utils import social_tracker as m
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = "Login • Instagram"
    fake_response.url = "https://www.instagram.com/accounts/login/?next=/p/x/"

    async def go():
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_response),
        ))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch.object(m, "httpx") as fake_httpx:
            fake_httpx.AsyncClient = MagicMock(return_value=ctx)
            return await m.fetch_public_post("https://x")
    out = _run(go())
    assert out["status"] == "blocked"


def test_fetch_public_post_marks_failed_on_5xx():
    from utils import social_tracker as m
    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.text = ""
    fake_response.url = "https://x"

    async def go():
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_response),
        ))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch.object(m, "httpx") as fake_httpx:
            fake_httpx.AsyncClient = MagicMock(return_value=ctx)
            return await m.fetch_public_post("https://x")
    out = _run(go())
    assert out["status"] == "failed"
    assert out["http_status"] == 503


def test_fetch_public_post_never_raises_on_network_error():
    from utils import social_tracker as m

    async def go():
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(side_effect=Exception("network unreachable")),
        ))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch.object(m, "httpx") as fake_httpx:
            fake_httpx.AsyncClient = MagicMock(return_value=ctx)
            return await m.fetch_public_post("https://x")
    out = _run(go())
    assert out["status"] == "failed"
    assert "network unreachable" in out["error"]


# ══════════════════ 8 · crawl_due_tracked_posts updates rows ═════════


def test_crawl_due_tracked_posts_records_history():
    from utils import social_tracker as m

    fdb = MagicMock()
    rows = [
        {"id": "tp-1", "url": "https://www.instagram.com/p/A/",
         "platform": "instagram", "active": True},
        {"id": "tp-2", "url": "https://www.instagram.com/p/B/",
         "platform": "instagram", "active": True},
    ]
    fdb.social_tracked_posts.find = MagicMock(return_value=_cursor(rows))
    fdb.social_tracked_posts.update_one = AsyncMock()

    async def _fetch(url):
        # First URL returns ok, second blocked.
        if "/A/" in url:
            return {"status": "ok", "http_status": 200,
                    "engagement": {"likes": 100, "comments": 5,
                                   "caption_snippet": "Hi"},
                    "fetched_at": "2026-02-29T10:00:00+00:00"}
        return {"status": "blocked", "http_status": 401,
                "engagement": {}, "fetched_at": "2026-02-29T10:00:00+00:00"}

    async def go():
        with patch.object(m, "fetch_public_post", side_effect=_fetch):
            return await m.crawl_due_tracked_posts(fdb)
    out = _run(go())
    assert out == {"crawled": 2, "ok": 1, "blocked": 1, "failed": 0}
    assert fdb.social_tracked_posts.update_one.await_count == 2
    # Verify the engagement_history $push has $slice -60 for retention.
    first_call = fdb.social_tracked_posts.update_one.call_args_list[0]
    push_doc = first_call.args[1]["$push"]["engagement_history"]
    assert push_doc["$slice"] == -60


# ══════════════════ 9 · Campaign endpoints — singleton & RBAC ════════


def test_create_campaign_master_admin_only():
    from routes.marketing import social_autopilot as m
    user = {"id": "u-1", "is_master_admin": False}
    payload = m.CampaignPayload(
        name="Launch Week", type="launch", keywords=["x"], blend_ratio=0.7,
    )
    async def go():
        with pytest.raises(HTTPException) as exc:
            await m.create_campaign(payload=payload, user=user)
        assert exc.value.status_code in (401, 403)
    _run(go())


def test_activate_campaign_pauses_other_active_of_same_type():
    """Singleton invariant — at most one active campaign per type."""
    from routes.marketing import social_autopilot as m

    target = {"id": "camp-new", "type": "launch", "status": "paused"}
    fdb = MagicMock()
    fdb.social_autopilot_campaigns.find_one = AsyncMock(return_value=target)
    fdb.social_autopilot_campaigns.update_many = AsyncMock()
    fdb.social_autopilot_campaigns.update_one = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.activate_campaign(campaign_id="camp-new", user=_ADMIN)
    out = _run(go())
    assert out["status"] == "active"
    # update_many was called to pause the others of the same type.
    fdb.social_autopilot_campaigns.update_many.assert_awaited_once()
    q = fdb.social_autopilot_campaigns.update_many.call_args.args[0]
    assert q["type"] == "launch"
    assert q["status"] == "active"
    assert q["id"]["$ne"] == "camp-new"


# ══════════════════ 10 · Tracked-posts endpoints ═════════════════════


def test_add_tracked_post_rejects_unsupported_platform():
    from routes.marketing import social_autopilot as m
    payload = m.TrackedPostPayload(url="https://twitter.com/x", label="")

    async def go():
        with pytest.raises(HTTPException) as exc:
            await m.add_tracked_post(payload=payload, user=_ADMIN)
        assert exc.value.status_code == 400
    _run(go())


def test_add_tracked_post_dedupes_by_url():
    """Adding the same URL twice should re-activate the existing row,
    not create a duplicate."""
    from routes.marketing import social_autopilot as m
    fdb = MagicMock()
    fdb.social_tracked_posts.find_one = AsyncMock(return_value={
        "id": "tp-x", "active": False,
    })
    fdb.social_tracked_posts.update_one = AsyncMock()
    fdb.social_tracked_posts.insert_one = AsyncMock()
    payload = m.TrackedPostPayload(
        url="https://www.instagram.com/p/DYfu35JNbkJ/", label="Launch teaser",
    )

    async def go():
        with patch.object(m, "db", fdb):
            return await m.add_tracked_post(payload=payload, user=_ADMIN)
    out = _run(go())
    assert out["ok"] is True
    assert out["id"] == "tp-x"
    fdb.social_tracked_posts.insert_one.assert_not_called()
    fdb.social_tracked_posts.update_one.assert_awaited_once()


def test_server_wires_social_tracker_loop_on_startup():
    """server.py startup must register the daily tracker loop."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text()
    assert "run_social_tracker_loop" in src
    assert "SOCIAL_TRACKER_INTERVAL_SEC" in src
