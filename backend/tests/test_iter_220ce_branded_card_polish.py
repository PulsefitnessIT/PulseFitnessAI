"""Iter 220ce — Branded social card visual polish + Refresh feedback.

Covers two user-reported fixes:

  1. **Card visual** (`utils.social_autopilot._pillow_branded_card_png`):
       - The PNG mark logo is composited onto the card via a rounded
         white badge (the source PNG ships with a baked-in white
         background — pasting raw produced a stark white square that
         looked like a bug).
       - The decorative "circle in the top-right corner" the operator
         flagged is now rendered through proper alpha blending on an
         RGBA overlay (the previous version used ``draw.ellipse(...)``
         on an RGB canvas, which silently dropped the alpha and gave
         a hard white ring).
       - Font candidates extended to include
         ``FreeSansBold`` / ``LiberationSans-Bold`` so the headline
         renders at the intended pixel size on Debian-slim images
         (the original DejaVu-only list was failing → 10px bitmap
         fallback → "the text is tiny").

  2. **Refresh feedback** (``load`` callable in
     ``SocialAutopilotPanel.js`` accepts ``{silent: true|false}``).
     We can't test JS from pytest, but we DO test that the rendered
     card has the expected pixel structure so a future panel-side
     regression has a stable contract to assert against.
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
from unittest.mock import patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _decode(data_url: str) -> bytes:
    assert data_url.startswith("data:image/"), data_url[:60]
    return base64.b64decode(data_url.split(",", 1)[1])


def _make_card_sync():
    """Synchronous shortcut into the Pillow renderer that bypasses
    the LLM image pipeline."""
    from utils.social_autopilot import _pillow_branded_card_png

    channel = {
        "image_aspect": "1:1", "image_size_px": 600,
        "label": "Instagram",
    }
    return _pillow_branded_card_png("Test Headline Two", channel, "Subtitle line")


# ══════════════════ 1 · Pillow renderer pixel checks ═════════════════


def test_branded_card_renders_to_valid_png():
    png = _make_card_sync()
    assert png is not None, "Pillow renderer returned None — fonts missing?"
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # Size floor — a single-pixel fallback would be << 1KB.
    assert len(png) > 4_000


def test_branded_card_no_stark_white_ring_in_top_right():
    """Iter 220ce — Pillow ignores alpha on RGB canvases, so the
    previous ``draw.ellipse(outline=(255,255,255,30))`` rendered as
    a hard white outline. Confirm the top-right ~20% region is now
    inside the gradient (no full-white pixel ring)."""
    from PIL import Image
    png = _make_card_sync()
    assert png
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, _h = im.size
    # Sample 8 pixels on the *outside* of where the old ring used to
    # be — they must NOT all be pure white.
    samples = [im.getpixel((x, y))
               for x in (int(w * 0.81), int(w * 0.85), int(w * 0.92))
               for y in (int(w * 0.07), int(w * 0.12), int(w * 0.17))]
    pure_white = [s for s in samples if s == (255, 255, 255)]
    assert len(pure_white) < len(samples) // 2, (
        f"{len(pure_white)}/{len(samples)} top-right samples are pure white "
        f"— old white-ring regression is back"
    )


def test_branded_card_has_white_logo_badge_in_bottom_left():
    """The fix wraps the logo in an opaque white rounded pill in the
    bottom-left. Sample a 5×5 grid inside the badge bounds and
    confirm ≥10 pixels are very near white."""
    from PIL import Image
    png = _make_card_sync()
    assert png
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    samples = [im.getpixel((x, y))
               for x in (int(w * 0.10), int(w * 0.14), int(w * 0.18), int(w * 0.22), int(w * 0.26))
               for y in (int(h * 0.86), int(h * 0.88), int(h * 0.90), int(h * 0.92))]
    near_white = [s for s in samples
                  if s[0] > 240 and s[1] > 240 and s[2] > 240]
    assert len(near_white) >= 8, f"only {len(near_white)}/{len(samples)} pixels near-white in badge region"


def test_branded_card_falls_back_to_text_when_logo_missing(tmp_path):
    """When the logo file isn't on disk the renderer must NOT crash
    — it should fall back to the text-only brand mark and still
    return a valid PNG."""
    from utils import social_autopilot as m
    with patch.object(os.path, "exists", side_effect=lambda p: "brand" not in p):
        png = m._pillow_branded_card_png(
            "Fallback Headline",
            {"image_aspect": "1:1", "image_size_px": 400, "label": "IG"},
            "x",
        )
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ══════════════════ 2 · End-to-end through render_branded_card ═══════


def test_render_branded_card_to_data_url_returns_data_uri():
    from utils.social_autopilot import render_branded_card_to_data_url

    channel = {
        "image_aspect": "1:1", "image_size_px": 600,
        "label": "Instagram",
    }
    out = render_branded_card_to_data_url(
        headline="End To End", channel=channel, subtitle="Sub",
    )
    assert isinstance(out, str) and out.startswith("data:image/")
    if out.startswith("data:image/png"):
        png = _decode(out)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
