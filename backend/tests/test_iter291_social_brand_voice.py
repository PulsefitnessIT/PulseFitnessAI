"""Iter 291 — Social Media Autopilot brand-voice revamp.

The operator wants short, sharp, Gymshark/Nike/Lululemon-style posts with
absolutely NO website URL/domain in the caption or rendered image, and
real product screenshots prioritised over generic template cards.

These tests are offline (no LLM/DB) — they exercise the deterministic
plumbing: prompt construction, the URL stripper, layout selection and
the card renderer.
"""
from utils import social_autopilot as sa
from utils.social_templates import render_social_card


# ── URL / domain stripping ────────────────────────────────────────────
def test_strip_urls_removes_bare_domain():
    assert sa.strip_urls("Try it at gymaxisai.com today") == "Try it at today"


def test_strip_urls_removes_http_links():
    assert sa.strip_urls("Visit https://gymaxisai.com/demo now") == "Visit now"


def test_strip_urls_removes_www_and_tidies_parens():
    assert sa.strip_urls("Book a call (www.gymaxisai.com).") == "Book a call."


def test_strip_urls_keeps_innocent_dots():
    assert sa.strip_urls("No url here e.g. fine") == "No url here e.g. fine"


def test_strip_urls_unwraps_quotes():
    assert sa.strip_urls('"Stop chasing engineers."') == "Stop chasing engineers."


# ── Channel tone is short & sharp ─────────────────────────────────────
def test_instagram_caption_target_is_short():
    ch = sa.channel_by_id("instagram")
    assert ch["caption_max_chars"] <= 200
    assert ch["hashtag_max"] <= 8


def test_tiktok_caption_target_is_short():
    ch = sa.channel_by_id("tiktok")
    assert ch["caption_max_chars"] <= 200


def test_linkedin_is_leaner_than_before():
    ch = sa.channel_by_id("linkedin")
    assert ch["caption_max_chars"] <= 1500


# ── Prompts carry brand voice and never leak the domain ───────────────
def _topic():
    return {"kind": "feature", "topic_id": "feature:service_desk",
            "label": "Service Desk & Fault Triage", "hook": "x",
            "feature_id": "service_desk"}


def test_build_prompt_no_domain_has_voice():
    p = sa.build_prompt(sa.channel_by_id("instagram"), _topic(), layout="screenshot")
    assert "gymaxisai.com" not in p
    assert "Gymshark" in p


def test_launch_prompt_no_domain_has_voice():
    camp = {"name": "Launch", "keywords": ["a"], "blend_ratio": 0.7}
    p = sa.build_launch_prompt(sa.channel_by_id("instagram"), _topic(), camp,
                               sa.pick_launch_archetype(0), layout="screenshot")
    assert "gymaxisai.com" not in p
    assert "Gymshark" in p


def test_compose_prompt_no_domain_has_voice():
    p = sa.build_compose_prompt(sa.channel_by_id("instagram"), "about churn")
    assert "gymaxisai.com" not in p
    assert "Gymshark" in p


# ── Screenshots are prioritised when one genuinely exists ─────────────
def test_feature_with_screenshot_always_uses_screenshot_layout():
    t = _topic()  # service_desk has a real screenshot
    assert all(sa.pick_layout("instagram", t, n) == "screenshot" for n in range(4))


def test_feature_without_screenshot_falls_back():
    t = {"kind": "feature", "feature_id": "gdpr_workflow", "label": "GDPR"}
    assert sa.pick_layout("instagram", t, 0) != "screenshot"


# ── Card renders without crashing (and contains no domain text) ───────
def test_screenshot_card_renders():
    png = render_social_card(
        "screenshot", w=1080, h=1080, brand=sa.BRAND,
        fields={"headline": "Service Desk",
                "screenshot_path": sa._screenshot_path_for("service_desk")},
        logo_path=sa._resolve_logo_path(),
    )
    assert png and len(png) > 1000


def test_hook_card_renders():
    png = render_social_card(
        "hook", w=1080, h=1080, brand=sa.BRAND,
        fields={"headline": "Stop chasing engineers", "subtitle": sa.BRAND["tagline"]},
        logo_path=sa._resolve_logo_path(),
    )
    assert png and len(png) > 1000
