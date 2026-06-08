"""Iter 222 — Social Autopilot template engine (no hallucinated imagery).

Verifies the deterministic, brand-accurate card renderer that replaced
the generative-AI image path which produced off-brand fake dashboards,
wrong logos and blank gradients.
"""
import os

from utils import social_autopilot as sa
from utils.social_templates import render_social_card, LAYOUTS


def _ch(cid):
    return sa.channel_by_id(cid)


def _dims(cid):
    c = _ch(cid)
    return sa._card_dimensions(c["image_aspect"], c["image_size_px"])


# ── Layout selection is deterministic + safe ──────────────────────────
def test_feature_layout_rotation_is_deterministic():
    topic = {"kind": "feature", "feature_id": "service_desk"}
    seen = [sa.pick_layout("instagram", topic, n) for n in range(4)]
    # service_desk HAS a screenshot, so index 0 stays "screenshot"
    assert seen == ["screenshot", "feature", "stat", "hook"]


def test_screenshot_falls_back_when_no_real_screenshot():
    # An industry topic / a feature with no mapped screenshot must never
    # try to show a screenshot (there is no real product image for it).
    topic = {"kind": "feature", "feature_id": "no_such_feature"}
    assert sa.pick_layout("instagram", topic, 0) == "feature"


def test_linkedin_swaps_cheeky_punchline_for_numbers():
    topic = {"kind": "industry"}
    # industry rotation index 1 == "punchline"; LinkedIn must downgrade it.
    assert sa.pick_layout("linkedin", topic, 1) == "stat"
    assert sa.pick_layout("instagram", topic, 1) == "punchline"


# ── Stats are curated, never fabricated ───────────────────────────────
def test_feature_stats_are_product_facts():
    topic = {"kind": "feature"}
    stat = sa._pick_stat(topic, 0)
    assert stat["kind"] == "product"
    assert stat in [{**s, "kind": "product"} for s in sa.PRODUCT_STATS]


def test_industry_stats_are_clearly_framed():
    topic = {"kind": "industry"}
    stat = sa._pick_stat(topic, 0)
    assert stat["kind"] == "industry"
    assert stat["value"] and stat["label"]


# ── Real screenshots exist on disk ────────────────────────────────────
def test_mapped_screenshots_are_real_files():
    found = 0
    for fid in sa.SCREENSHOT_MAP:
        p = sa._screenshot_path_for(fid)
        if p:
            assert os.path.exists(p)
            found += 1
    assert found >= 5  # most feature pillars map to a real product screen


# ── Renderer produces a real PNG for every layout / channel ───────────
def test_every_layout_renders_png():
    brand = sa.BRAND
    logo = sa._resolve_logo_path()
    fields = {
        "headline": "Stop Chasing PPMs Manually",
        "subtitle": brand["tagline"],
        "stat_value": "13", "stat_label": "operational modules, one login",
        "stat_kind": "product",
        "bullets": ["Triage in 4 seconds", "Right engineer first time", "No guesswork"],
        "setup": "When a treadmill breaks...", "payoff": "Your CRM already knows.",
        "screenshot_path": sa._screenshot_path_for("service_desk"),
    }
    for layout in LAYOUTS:
        for cid in ("instagram", "tiktok", "linkedin"):
            w, h = _dims(cid)
            png = render_social_card(layout, w=w, h=h, brand=brand,
                                     fields=fields, logo_path=logo)
            assert png and png[:8] == b"\x89PNG\r\n\x1a\n", f"{layout}/{cid} not a PNG"
            assert len(png) > 2000


# ── Prompt carries layout-specific JSON keys ──────────────────────────
def test_feature_prompt_requests_bullets():
    ch = _ch("instagram")
    topic = {"kind": "feature", "label": "AI Fault Triage", "hook": "h"}
    p = sa.build_prompt(ch, topic, layout="feature")
    assert "feature_bullets" in p


def test_punchline_prompt_requests_setup_payoff():
    ch = _ch("instagram")
    topic = {"kind": "industry", "label": "X", "hook": "h"}
    p = sa.build_prompt(ch, topic, layout="punchline")
    assert "punchline_setup" in p and "punchline_payoff" in p


def test_stat_prompt_injects_curated_figure_and_disclaims_customer_results():
    ch = _ch("linkedin")
    topic = {"kind": "industry", "label": "X", "hook": "h"}
    stat = {"value": "5×", "label": "more costly to win than keep", "kind": "industry"}
    p = sa.build_prompt(ch, topic, layout="stat", stat=stat)
    assert "5×" in p
    assert "INDUSTRY" in p.upper()
    assert "customer result" in p.lower()
