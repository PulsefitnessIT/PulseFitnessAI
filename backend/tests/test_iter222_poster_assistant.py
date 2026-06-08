"""Iter 222 — AI Poster Assistant (prompt → on-brand poster draft).

The compose flow must: pick/honour a layout, NEVER fabricate a stat,
render a real PNG via the template engine, and persist a draft doc in
the expected shape. The LLM is monkeypatched so the test is hermetic.
"""
import asyncio

import pytest

from utils import social_autopilot as sa


class _FakeColl:
    def __init__(self):
        self.last = None

    async def insert_one(self, doc):
        self.last = dict(doc)
        return type("R", (), {"inserted_id": "x"})()


class _FakeDB:
    def __init__(self):
        self.social_autopilot_posts = _FakeColl()


def _run(coro):
    return asyncio.run(coro)


def _patch_llm(monkeypatch, payload):
    async def _fake(_prompt):
        return payload
    monkeypatch.setattr(sa, "_llm_chat", _fake)


# ── build_compose_prompt carries the safety rails ─────────────────────
def test_compose_prompt_has_numbers_rule_and_curated_stats():
    ch = sa.channel_by_id("linkedin")
    p = sa.build_compose_prompt(ch, "a numbers post about downtime")
    assert "NUMBERS RULE" in p
    # at least one curated product stat label must be offered to the model
    assert any(s["label"] in p for s in sa.PRODUCT_STATS)
    assert "STRICT JSON" in p


def test_compose_prompt_pins_layout_when_requested():
    ch = sa.channel_by_id("tiktok")
    p = sa.build_compose_prompt(ch, "make it funny", layout="punchline")
    assert "Use the 'punchline' layout" in p


# ── compose_post_from_prompt renders + persists ───────────────────────
def test_compose_stat_renders_png_and_persists_draft(monkeypatch):
    _patch_llm(monkeypatch, {
        "layout": "stat", "caption": "Operators lose hours every week.",
        "hashtags": ["#FitnessOps", "#GymManagement"],
        "card_headline": "Hours Lost Chasing Engineers",
        "stat_value": "Hours",
        "stat_label": "lost every week chasing engineers across WhatsApp & email",
        "stat_kind": "industry",
    })
    db = _FakeDB()
    doc = _run(sa.compose_post_from_prompt(
        db, channel_id="linkedin", prompt="a numbers post about chasing engineers"))
    assert doc["image_variant"] == "stat"
    assert doc["image_model"] == "prompt:stat"
    assert doc["image_url"].startswith("data:image/png;base64,")
    assert doc["status"] == "draft"
    assert doc["generation_meta"]["source"] == "manual_prompt"
    assert doc["topic_kind"] == "manual"
    assert db.social_autopilot_posts.last["id"] == doc["id"]


def test_compose_empty_stat_falls_back_to_curated_never_blank(monkeypatch):
    # Model returned the stat layout but forgot the figure — we must NOT
    # render an empty/invented number; fall back to a curated product fact.
    _patch_llm(monkeypatch, {
        "layout": "stat", "caption": "x", "hashtags": ["#Ops"],
        "card_headline": "One Platform", "stat_value": "", "stat_label": "",
    })
    db = _FakeDB()
    doc = _run(sa.compose_post_from_prompt(db, channel_id="instagram", prompt="numbers"))
    assert doc["image_url"].startswith("data:image/png;base64,")
    assert len(doc["image_url"]) > 3000  # a real card, not an empty render


def test_compose_feature_uses_bullets(monkeypatch):
    _patch_llm(monkeypatch, {
        "layout": "feature", "caption": "x", "hashtags": ["#Ops"],
        "card_headline": "AI Fault Triage",
        "feature_bullets": ["Triage in seconds", "Right engineer first time", "Full audit trail"],
    })
    db = _FakeDB()
    doc = _run(sa.compose_post_from_prompt(db, channel_id="linkedin", prompt="feature post"))
    assert doc["image_variant"] == "feature"
    assert doc["image_url"].startswith("data:image/png;base64,")


def test_compose_requested_layout_overrides_model(monkeypatch):
    _patch_llm(monkeypatch, {
        "layout": "hook", "caption": "x", "hashtags": ["#Ops"],
        "card_headline": "Stop Chasing Engineers",
    })
    db = _FakeDB()
    doc = _run(sa.compose_post_from_prompt(
        db, channel_id="tiktok", prompt="funny", layout="punchline"))
    assert doc["image_variant"] == "punchline"


def test_compose_requires_prompt_or_headline(monkeypatch):
    _patch_llm(monkeypatch, {"layout": "hook", "caption": "x", "hashtags": []})
    db = _FakeDB()
    with pytest.raises(ValueError):
        _run(sa.compose_post_from_prompt(db, channel_id="linkedin", prompt="   "))
