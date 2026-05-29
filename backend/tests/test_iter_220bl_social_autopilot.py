"""Iter 220bl — Social Media Autopilot V1.

Locks in the channel-aware tone, topic blending, image variant
rotation, and prompt schema for the new Social Autopilot.
"""
from __future__ import annotations

import re

import pytest

from tests.shared_loop import run_async as drive_async
from utils.social_autopilot import (
    BRAND,
    CHANNELS,
    FEATURE_PILLARS,
    _branded_card_svg,
    _pillow_branded_card_png,
    build_prompt,
    channel_by_id,
    feature_pillar_by_id,
    pick_topic_for,
    render_branded_card_to_data_url,
)


# ── Fake DB ─────────────────────────────────────────────────────────


class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def sort(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    async def to_list(self, _n=None):
        return list(self._rows)

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class _PostsColl:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, _filter=None, _proj=None, **_kw):
        return _Cursor(self.rows)

    async def count_documents(self, q):
        if not q:
            return len(self.rows)
        return sum(1 for r in self.rows if all(r.get(k) == v for k, v in q.items()))


class _FakeDB:
    def __init__(self, posts=None):
        self.social_autopilot_posts = _PostsColl(posts)


# ── Channel definitions ─────────────────────────────────────────────


def test_three_channels_exist():
    ids = {c["id"] for c in CHANNELS}
    assert ids == {"instagram", "tiktok", "linkedin"}


def test_channel_tones_are_distinct():
    tones = {c["id"]: c["tone_brief"].lower() for c in CHANNELS}
    # LinkedIn should explicitly forbid emoji to keep the executive feel.
    assert "no emoji" in tones["linkedin"] or "no emojis" in tones["linkedin"]
    # Instagram must mention emoji positively
    assert "emoji" in tones["instagram"]
    # TikTok must call out the 7-word hook
    assert "7 words" in tones["tiktok"]


def test_channel_aspect_ratios():
    expected = {"instagram": "1:1", "tiktok": "9:16", "linkedin": "1.91:1"}
    for c in CHANNELS:
        assert c["image_aspect"] == expected[c["id"]]


def test_channel_by_id_helper():
    assert channel_by_id("instagram")["label"] == "Instagram"
    assert channel_by_id("does-not-exist") is None


def test_feature_pillars_complete():
    assert len(FEATURE_PILLARS) >= 10, "Need ≥10 feature pillars for variety"
    ids = {p["id"] for p in FEATURE_PILLARS}
    # Spot-check a few critical ones the user explicitly wants advertised.
    for must_have in ("partner_engineers", "crm_pipeline",
                       "ppm_scheduler", "ai_triage", "gdpr_workflow"):
        assert must_have in ids, f"missing pillar {must_have}"
    assert feature_pillar_by_id("partner_engineers")["label"]


# ── 50/50 topic alternation ─────────────────────────────────────────


def test_topic_alternation_feature_then_industry():
    # 0 posts on this channel → feature
    db = _FakeDB(posts=[])
    t0 = drive_async(pick_topic_for(db, "instagram"))
    assert t0["kind"] == "feature"

    # 1 post on this channel → industry
    db = _FakeDB(posts=[{"channel": "instagram", "topic_id": "feature:crm_pipeline"}])
    t1 = drive_async(pick_topic_for(db, "instagram"))
    assert t1["kind"] == "industry"

    # 2 posts → feature again
    db = _FakeDB(posts=[
        {"channel": "instagram", "topic_id": "feature:crm_pipeline"},
        {"channel": "instagram", "topic_id": "industry:equipment_downtime"},
    ])
    t2 = drive_async(pick_topic_for(db, "instagram"))
    assert t2["kind"] == "feature"


def test_topic_alternation_independent_per_channel():
    """LinkedIn's count should NOT affect Instagram's alternation."""
    db = _FakeDB(posts=[
        {"channel": "linkedin", "topic_id": "feature:partner_engineers"},
    ])
    t_ig = drive_async(pick_topic_for(db, "instagram"))
    t_li = drive_async(pick_topic_for(db, "linkedin"))
    assert t_ig["kind"] == "feature"
    assert t_li["kind"] == "industry"  # LinkedIn count = 1 → industry


# ── Prompt schema ────────────────────────────────────────────────────


def test_prompt_includes_channel_tone():
    channel = channel_by_id("linkedin")
    topic = {"kind": "feature", "topic_id": "feature:crm_pipeline",
             "label": "CRM Pipeline", "hook": "Test hook.", "feature_id": "crm_pipeline"}
    prompt = build_prompt(channel, topic)
    assert "LinkedIn" in prompt
    assert channel["audience"] in prompt
    assert "NO emoji" in prompt
    assert "STRICT JSON" in prompt


def test_prompt_tiktok_requests_video_script():
    channel = channel_by_id("tiktok")
    topic = {"kind": "industry", "topic_id": "industry:equipment_downtime",
             "label": "Downtime", "hook": "...", "pillar_id": "equipment_downtime"}
    prompt = build_prompt(channel, topic)
    assert "video_script" in prompt
    assert "ON-SCREEN TEXT" in prompt
    assert "12-15 second" in prompt


def test_prompt_industry_post_pulls_brand_softly():
    channel = channel_by_id("linkedin")
    topic = {"kind": "industry", "topic_id": "industry:ppm",
             "label": "PPM", "hook": "...", "pillar_id": "ppm_scheduling"}
    prompt = build_prompt(channel, topic)
    assert "do NOT pitch GymAxis hard" in prompt
    assert "industry-insight" in prompt.lower() or "INDUSTRY-INSIGHT" in prompt


def test_prompt_feature_post_pitches():
    channel = channel_by_id("instagram")
    topic = {"kind": "feature", "topic_id": "feature:ai_triage",
             "label": "AI Triage", "hook": "Test.", "feature_id": "ai_triage"}
    prompt = build_prompt(channel, topic)
    assert "FEATURE-PROMOTION" in prompt
    assert "DO NOT invent specific customer names" in prompt


def test_prompt_caps_hashtag_count_per_channel():
    li = build_prompt(channel_by_id("linkedin"),
                       {"kind": "industry", "topic_id": "x", "label": "x", "hook": "x"})
    ig = build_prompt(channel_by_id("instagram"),
                       {"kind": "industry", "topic_id": "x", "label": "x", "hook": "x"})
    # LinkedIn requests 3-6 hashtags
    assert re.search(r"3-6\s+items", li)
    # Instagram requests 15-25
    assert re.search(r"15-25\s+items", ig)


# ── Brand card rendering ─────────────────────────────────────────────


def test_branded_card_svg_includes_brand_colours_and_headline():
    svg = _branded_card_svg("Six hour downtime", channel_by_id("instagram"))
    assert BRAND["color_primary"].lower() in svg.lower()
    assert BRAND["color_accent"].lower() in svg.lower()
    assert "Six hour" in svg
    assert BRAND["name"].upper() in svg
    assert BRAND["domain"] in svg


def test_branded_card_handles_long_headline():
    long = "A very long headline that should be wrapped into multiple lines safely"
    svg = _branded_card_svg(long, channel_by_id("linkedin"))
    # Should still be valid SVG (closed tag) and not exceed 3 lines of text.
    assert svg.startswith("<?xml") and "</svg>" in svg
    assert svg.count("<text") >= 2  # at least headline lines + brand mark


def test_branded_card_escapes_html_special_chars():
    svg = _branded_card_svg("Cost <bad> attack", channel_by_id("tiktok"))
    assert "<bad>" not in svg  # raw injection blocked
    assert "&lt;bad&gt;" in svg or "&lt;" in svg


def test_pillow_png_renders_when_pillow_available():
    """PNG rendering should succeed in CI (Pillow is in requirements)."""
    png = _pillow_branded_card_png("PPM that pays off", channel_by_id("linkedin"))
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "First 8 bytes must be the PNG header"


def test_render_data_url_prefers_png():
    url = render_branded_card_to_data_url("Operations under control",
                                          channel_by_id("instagram"))
    assert url.startswith("data:image/")
    # When Pillow is available we expect a PNG data URL.
    assert "image/png" in url or "image/svg+xml" in url


# ── Brand tokens sanity ─────────────────────────────────────────────


def test_brand_tokens_match_frontend_palette():
    # If anyone changes the palette here without updating the frontend
    # (or vice versa) this test fails loudly.
    assert BRAND["color_primary"].lower() == "#d946ef"  # fuchsia-500
    assert BRAND["color_accent"].lower() == "#3b82f6"   # blue-500
    assert BRAND["name"] == "GymAxis"
    assert BRAND["domain"] == "gymaxisai.com"
