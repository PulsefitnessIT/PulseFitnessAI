"""Iter 220cg — Social card text rendering + headline hygiene.

User reported (Feb 2026): "Social media AI text falling off edge & not
making sense". Two root causes:

  1. The wrap heuristic in ``_pillow_branded_card_png`` used a fixed
     18-char budget. With TrueType rendering on portrait (9:16) cards
     a single line could easily exceed the safe right margin → text
     literally ran off the card.
  2. The over-image headline came straight from the LLM and was
     sometimes a teaser ("How to...", "The 5 things..."), a
     mid-sentence fragment, or a quoted phrase — none of which read
     as a clean standalone headline.

Pins:
  * ``clean_card_headline`` strips quotes, trailing punctuation, caps
    word count at 6, and rejects mid-sentence starters.
  * Rendered card has NO white pixels in the right-margin band (a
    proxy for "text didn't bleed off the edge").
  * Even a 12-word headline renders cleanly inside the safe area.
  * ``generate_post_for_channel`` stores the cleaned headline (not the
    raw LLM string) under ``card_headline`` so the UI agrees with the
    rendered card.
"""
from __future__ import annotations

import asyncio
import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _decode(data_url: str) -> bytes:
    assert data_url.startswith("data:image/"), data_url[:60]
    return base64.b64decode(data_url.split(",", 1)[1])


def _channel(aspect="1:1", size=720):
    return {"image_aspect": aspect, "image_size_px": size, "label": "Instagram"}


# ── 1 · clean_card_headline ───────────────────────────────────────────


def test_clean_headline_strips_wrapping_quotes():
    from utils.social_autopilot import clean_card_headline
    assert clean_card_headline('"Cut Engineer Dispatch Time"') == "Cut Engineer Dispatch Time"
    assert clean_card_headline("'Stop Chasing PPMs'") == "Stop Chasing PPMs"
    assert clean_card_headline("“Curly quotes too”") == "Curly Quotes Too"


def test_clean_headline_strips_trailing_punctuation():
    from utils.social_autopilot import clean_card_headline
    assert clean_card_headline("Cut Engineer Dispatch Time.") == "Cut Engineer Dispatch Time"
    assert clean_card_headline("Save 4 hours...") == "Save 4 Hours"
    assert clean_card_headline("PPMs Done Right!") == "PPMs Done Right"


def test_clean_headline_caps_at_six_words():
    from utils.social_autopilot import clean_card_headline
    out = clean_card_headline(
        "This Is A Really Long Headline That Should Be Cut Off",
        fallback="Fallback",
    )
    assert len(out.split()) <= 6


def test_clean_headline_falls_back_on_mid_sentence_starter():
    from utils.social_autopilot import clean_card_headline
    assert clean_card_headline("and then we built it", fallback="Feature X") == "Feature X"
    assert clean_card_headline("the silent killer of margins", fallback="Downtime") == "Downtime"
    assert clean_card_headline("when you have 50 sites", fallback="Multi Site Ops") == "Multi Site Ops"


def test_clean_headline_falls_back_on_empty_input():
    from utils.social_autopilot import clean_card_headline
    assert clean_card_headline("", fallback="Topic Label") == "Topic Label"
    assert clean_card_headline("   ", fallback="Topic Label") == "Topic Label"


def test_clean_headline_preserves_brand_casing():
    from utils.social_autopilot import clean_card_headline
    # GymAxis should keep its camel-case
    out = clean_card_headline("gymaxis launches today")
    assert "GymAxis" in out
    # Short acronyms (PPM, KPI) should survive
    out2 = clean_card_headline("PPM Tracking Made Easy")
    assert "PPM" in out2


def test_clean_headline_title_cases_lowercase_input():
    from utils.social_autopilot import clean_card_headline
    assert clean_card_headline("cut engineer dispatch time") == "Cut Engineer Dispatch Time"


def test_clean_headline_clips_to_80_chars():
    from utils.social_autopilot import clean_card_headline
    out = clean_card_headline("A" * 200)
    assert len(out) <= 80


# ── 2 · Rendered card text doesn't run off the edge ───────────────────


def _has_text_in_right_band(png_bytes: bytes, band_pct: float = 0.05) -> bool:
    """Returns True if there are any near-white pixels in the rightmost
    ``band_pct`` of the card's middle horizontal third — a proxy for
    "the headline bled into the right margin / off the edge"."""
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    band_w = max(1, int(w * band_pct))
    crop = img.crop((w - band_w, int(h * 0.30), w, int(h * 0.65)))
    pixels = crop.load()
    cw, ch = crop.size
    for y in range(ch):
        for x in range(cw):
            r, g, b = pixels[x, y]
            # Near-white pixels mean text rendered there.
            if r > 230 and g > 230 and b > 230:
                return True
    return False


def test_short_headline_stays_inside_safe_area():
    from utils.social_autopilot import _pillow_branded_card_png
    png = _pillow_branded_card_png("Cut Dispatch Time", _channel(), "Tagline")
    assert png is not None
    assert not _has_text_in_right_band(png), \
        "Short headline must not touch the right edge"


def test_long_headline_does_not_bleed_off_edge_square():
    from utils.social_autopilot import _pillow_branded_card_png
    long_headline = "Stop Wasting Hours Chasing Engineers Across Your Sites Forever"
    png = _pillow_branded_card_png(long_headline, _channel("1:1", 720), "x")
    assert png is not None
    assert not _has_text_in_right_band(png), \
        "Long Instagram headline must wrap inside the safe area"


def test_long_headline_does_not_bleed_off_edge_portrait():
    """TikTok 9:16 was the worst offender — narrower canvas + tall
    portrait → the old 18-char budget overflowed on almost every post."""
    from utils.social_autopilot import _pillow_branded_card_png
    long_headline = "Most Multi Site Operators Still Chase Engineers Manually"
    png = _pillow_branded_card_png(long_headline, _channel("9:16", 540), "x")
    assert png is not None
    assert not _has_text_in_right_band(png), \
        "Portrait TikTok headline must wrap inside the safe area"


def test_long_headline_does_not_bleed_off_edge_landscape():
    """LinkedIn 1.91:1 — wide but shorter, font sized off h so wraps
    must still respect the right margin."""
    from utils.social_autopilot import _pillow_branded_card_png
    long_headline = "Why Single Pane Of Glass Operations Always Wins For Chains"
    png = _pillow_branded_card_png(long_headline, _channel("1.91:1", 480), "x")
    assert png is not None
    assert not _has_text_in_right_band(png), \
        "LinkedIn landscape headline must wrap inside the safe area"


def test_single_oversized_word_truncates_with_ellipsis():
    """A pathological 40-char single word must not bleed off the edge
    — it should be truncated character-wise with an ellipsis."""
    from utils.social_autopilot import _pillow_branded_card_png
    png = _pillow_branded_card_png(
        "Antidisestablishmentarianismexamplelongword",
        _channel("1:1", 720), "",
    )
    assert png is not None
    assert not _has_text_in_right_band(png)


# ── 3 · LLM prompt mentions the headline guardrails ───────────────────


def test_build_prompt_requires_complete_headline_thought():
    from utils.social_autopilot import build_prompt, channel_by_id
    ch = channel_by_id("instagram")
    prompt = build_prompt(ch, {
        "topic_id": "x", "kind": "feature",
        "label": "Engineer Dispatch", "hook": "Save hours weekly",
    })
    low = prompt.lower()
    assert "complete" in low and "3-5 word" in low.replace(" ", " ")
    # Make sure the prompt explicitly rejects teaser headlines.
    assert "how to" in low or "teaser" in low


# ── 4 · Stored card_headline matches the cleaned/rendered version ────


def test_generate_post_stores_cleaned_card_headline():
    """End-to-end: when the LLM returns a teaser-style headline, the
    saved doc must contain the CLEAN version (used by the UI's
    'Caption headline' display) rather than the raw LLM string."""
    from utils import social_autopilot as m

    fake_db = MagicMock()
    fake_db.social_autopilot_posts.count_documents = AsyncMock(return_value=0)
    fake_db.social_autopilot_posts.insert_one = AsyncMock()
    fake_db.social_autopilot_posts.find_one = AsyncMock(return_value=None)
    fake_db.social_campaigns.find_one = AsyncMock(return_value=None)

    async def fake_pick(_db, _ch):
        return {
            "topic_id": "feature.engineer-dispatch",
            "kind": "feature",
            "label": "Engineer Dispatch",
            "hook": "Save hours weekly",
        }

    async def fake_llm(_prompt):
        return {
            "caption": "Caption body text",
            "hashtags": ["#GymOps", "#FitnessIndustry", "#GymAxis"],
            "image_brief": "Brand colour graphic",
            "card_headline": '"How to cut your dispatch time..."',
            "video_script": None,
        }

    async def fake_render_nb(*, prompt, channel):  # noqa: ARG001
        return None  # forces branded-card path

    async def go():
        with patch.object(m, "pick_topic_for", fake_pick), \
             patch.object(m, "_llm_chat", fake_llm), \
             patch.object(m, "render_nano_banana_image", fake_render_nb), \
             patch.object(m, "get_active_launch_campaign", AsyncMock(return_value=None)):
            return await m.generate_post_for_channel(fake_db, "instagram")

    doc = _run(go())
    # The teaser-style "How to..." must be rejected — fallback to topic label.
    assert doc["card_headline"] == "Engineer Dispatch", doc["card_headline"]


def test_generate_post_keeps_clean_llm_headline_as_is():
    """When the LLM behaves and returns a clean 3-5 word headline, the
    cleaner must preserve it (only normalising case / quotes)."""
    from utils import social_autopilot as m

    fake_db = MagicMock()
    fake_db.social_autopilot_posts.count_documents = AsyncMock(return_value=0)
    fake_db.social_autopilot_posts.insert_one = AsyncMock()
    fake_db.social_campaigns.find_one = AsyncMock(return_value=None)

    async def fake_pick(_db, _ch):
        return {
            "topic_id": "industry.downtime",
            "kind": "industry",
            "label": "Downtime",
            "hook": "Silent killer",
        }

    async def fake_llm(_prompt):
        return {
            "caption": "Body",
            "hashtags": ["#GymOps", "#FitnessIndustry", "#PPM"],
            "image_brief": "Brand graphic",
            "card_headline": "Cut Downtime In Half",
            "video_script": None,
        }

    async def fake_render_nb(*, prompt, channel):  # noqa: ARG001
        return None

    async def go():
        with patch.object(m, "pick_topic_for", fake_pick), \
             patch.object(m, "_llm_chat", fake_llm), \
             patch.object(m, "render_nano_banana_image", fake_render_nb), \
             patch.object(m, "get_active_launch_campaign", AsyncMock(return_value=None)):
            return await m.generate_post_for_channel(fake_db, "instagram")

    doc = _run(go())
    assert doc["card_headline"] == "Cut Downtime In Half"
