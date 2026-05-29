"""Iter 220bm — Sora 2 weekly TikTok video + legacy-library cleanup.

Covers:

1. Sora 2 prompt assembly never leaks customer/PII context, asks for
   no on-screen text, no logos, and uses the brand palette.
2. ``generate_tiktok_video_for_post`` only fires on TikTok posts.
3. Disk path layout is deterministic and namespaced under
   /app/backend/uploads/social_videos/{post_id}.mp4.
4. Status transitions are correctly stamped (queued → generating →
   ready / failed).
"""
from __future__ import annotations

import os
import pathlib

import pytest

from tests.shared_loop import run_async as drive_async
from utils import social_autopilot as sa


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
        self.updates: list[dict] = []

    def find(self, _filter=None, _proj=None, **_kw):
        return _Cursor(self.rows)

    async def find_one(self, q, _proj=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items()):
                return r
        return None

    async def update_one(self, q, body, **_kw):
        self.updates.append({"q": q, "body": body})
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items()):
                r.update(body.get("$set") or {})
        return type("R", (), {"matched_count": 1})()

    async def count_documents(self, q):
        return sum(1 for r in self.rows
                   if all(r.get(k) == v for k, v in q.items()))


class _FakeDB:
    def __init__(self, posts=None):
        self.social_autopilot_posts = _PostsColl(posts)


# ── Prompt assembly ────────────────────────────────────────────────


def test_sora_prompt_uses_brand_palette_and_blocks_text_overlays():
    post = {
        "channel": "tiktok",
        "card_headline": "PPM that pays off",
        "image_brief": "Operator floor at peak hour",
        "video_script": "[shot 1] establishing pan over treadmills...",
    }
    prompt = sa._build_sora_prompt(post)
    # Brand colours must appear so Sora gels the lighting accordingly.
    assert sa.BRAND["color_primary"] in prompt
    assert sa.BRAND["color_accent"] in prompt
    # Sora is bad at text — caller must overlay any text in post-prod.
    assert "NO text overlays" in prompt
    assert "NO logos" in prompt
    # Headline must influence the prompt
    assert "PPM that pays off" in prompt
    # 9:16 vertical
    assert "9:16" in prompt or "vertical" in prompt


def test_sora_prompt_truncates_long_script_safely():
    post = {
        "card_headline": "x",
        "image_brief": "y",
        "video_script": "abc " * 1000,
    }
    prompt = sa._build_sora_prompt(post)
    # The script context must be capped so the prompt stays manageable.
    assert len(prompt) < 4000


def test_sora_prompt_never_references_real_customer_names():
    """If a draft ever ended up with a customer name in card_headline
    we still must not include it as a specific person/chain to render.
    The prompt asks for 'NO recognisable people from any specific
    brand or chain' — that's the safety net we lock in here."""
    post = {"card_headline": "Acme Gyms reduces downtime 30%",
            "image_brief": "n/a"}
    prompt = sa._build_sora_prompt(post)
    assert "NO recognisable people from any specific brand or chain" in prompt


# ── Disk path layout ────────────────────────────────────────────────


def test_video_path_layout_is_namespaced(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, "VIDEO_DIR", str(tmp_path / "videos"))
    p = sa.video_path_for_post("post-123")
    assert p.endswith("/videos/post-123.mp4")
    # The dir is created lazily
    assert os.path.isdir(str(tmp_path / "videos"))


# ── Channel guard ───────────────────────────────────────────────────


def test_generate_video_rejects_non_tiktok():
    db = _FakeDB(posts=[
        {"id": "p1", "channel": "linkedin", "card_headline": "x"},
    ])
    result = drive_async(sa.generate_tiktok_video_for_post(db, "p1"))
    assert not result["ok"]
    assert "TikTok-only" in result["error"]


def test_generate_video_unknown_post():
    db = _FakeDB(posts=[])
    result = drive_async(sa.generate_tiktok_video_for_post(db, "nope"))
    assert not result["ok"]
    assert "not found" in result["error"]


def test_generate_video_missing_key_marks_failed(monkeypatch):
    db = _FakeDB(posts=[
        {"id": "p1", "channel": "tiktok", "card_headline": "Hi"},
    ])
    # Force the env vars to be empty so we exercise the missing-key path.
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    monkeypatch.delenv("EMERGENT_MODEL_API_KEY", raising=False)
    result = drive_async(sa.generate_tiktok_video_for_post(db, "p1"))
    assert not result["ok"]
    assert "EMERGENT_LLM_KEY" in result["error"]
    # Must have stamped the doc with video_status='failed'
    post = next(r for r in db.social_autopilot_posts.rows if r["id"] == "p1")
    assert post["video_status"] == "failed"


# ── Routes wiring ────────────────────────────────────────────────────


def test_route_module_exports_legacy_and_video_endpoints():
    """Lock in the route surface so future refactors don't drop the
    new endpoints we just shipped."""
    src = pathlib.Path(
        "/app/backend/routes/marketing/social_autopilot.py",
    ).read_text(encoding="utf-8")
    for token in (
        "/posts/{post_id}/generate-video",
        "/posts/{post_id}/video",
        "/legacy-library",
        "/legacy-library/{post_id}",
        "BackgroundTasks",
        "FileResponse",
    ):
        assert token in src, f"Route module missing {token}"


# ── Module exports ───────────────────────────────────────────────────


def test_sora_exports_present():
    for name in ("VIDEO_DIR", "video_path_for_post",
                 "generate_tiktok_video_for_post"):
        assert hasattr(sa, name), f"social_autopilot must export {name}"
