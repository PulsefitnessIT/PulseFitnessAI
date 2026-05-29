"""Iter 220bj — Blog freshness & dedup helpers.

Locks in the four anti-repetition layers:

1. Recent-articles context is built + formatted for the prompt.
2. Archetype rotation picks the least-recently-used scenario.
3. Keyword similarity flags near-duplicates above threshold.
4. Post-generation uniqueness gate scores new drafts against
   existing published articles.
"""
from __future__ import annotations

import pytest

from tests.shared_loop import run_async as drive_async
from utils.seo_article_freshness import (
    ARCHETYPES,
    article_similarity_score,
    build_recent_articles_context,
    check_article_uniqueness,
    collect_token_overlaps,
    find_similar_keywords,
    format_recent_articles_for_prompt,
    keyword_similarity,
    pick_next_archetype,
    _first_paragraph,
)


# ── In-memory fake DB ────────────────────────────────────────────────


class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def sort(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, _filter=None, _proj=None, **_kw):
        return _Cursor(self.rows)

    def aggregate(self, _pipeline, **_kw):
        # Minimal: group by archetype_id then return last_used_at per id.
        seen: dict[str, str] = {}
        for r in self.rows:
            aid = r.get("archetype_id")
            if not aid:
                continue
            pub = r.get("published_at") or ""
            if aid not in seen or pub > seen[aid]:
                seen[aid] = pub
        result = [{"_id": k, "last_used_at": v} for k, v in seen.items()]
        return _Cursor(result)


class _FakeDB:
    def __init__(self, articles=None, keywords=None):
        self.seo_articles = _Collection(articles)
        self.seo_keywords = _Collection(keywords)


# ── Layer 1: recent-articles context ────────────────────────────────


def test_first_paragraph_skips_headings_and_blanks():
    body = "# Title\n\n## Heading\n\nFirst real paragraph with words."
    assert _first_paragraph(body).startswith("First real paragraph")


def test_first_paragraph_truncates_long_text():
    body = "Para " + ("x" * 1000)
    out = _first_paragraph(body, max_chars=100)
    assert len(out) == 100


def test_recent_articles_context_built_and_formatted():
    db = _FakeDB(articles=[
        {"title": "Downtime Guide", "primary_keyword": "downtime",
         "body_md": "# H\n\n## S1\n\nA broken treadmill ruins a morning.\n\n## S2\n\nFollow these steps.",
         "archetype_id": "peak_hour_failure",
         "status": "published", "published_at": "2026-02-01"},
    ])
    recent = drive_async(build_recent_articles_context(db, limit=4))
    assert len(recent) == 1
    assert recent[0]["title"] == "Downtime Guide"
    assert "broken treadmill" in recent[0]["opener"]
    assert recent[0]["archetype_id"] == "peak_hour_failure"

    block = format_recent_articles_for_prompt(recent)
    assert "DO NOT echo" in block
    assert "broken treadmill" in block
    assert "Downtime Guide" in block


def test_recent_articles_prompt_block_empty_when_no_articles():
    assert format_recent_articles_for_prompt([]) == ""


# ── Layer 2: archetype rotation ─────────────────────────────────────


def test_archetypes_have_unique_ids_and_hints():
    ids = [a["id"] for a in ARCHETYPES]
    assert len(ids) == len(set(ids)), "Archetype ids must be unique"
    assert len(ARCHETYPES) >= 6, "Need at least 6 archetypes for meaningful rotation"
    for a in ARCHETYPES:
        assert a["prompt_hint"] and len(a["prompt_hint"]) > 30


def test_pick_next_archetype_prefers_never_used():
    # If only peak_hour_failure has been used, picker must avoid it.
    db = _FakeDB(articles=[
        {"archetype_id": "peak_hour_failure", "status": "published",
         "published_at": "2026-02-10"},
    ])
    pick = drive_async(pick_next_archetype(db))
    assert pick["id"] != "peak_hour_failure"


def test_pick_next_archetype_falls_back_when_no_articles():
    pick = drive_async(pick_next_archetype(_FakeDB()))
    assert pick["id"] in [a["id"] for a in ARCHETYPES]


# ── Layer 3: keyword similarity ─────────────────────────────────────


@pytest.mark.parametrize("a,b,expected_high", [
    ("gym equipment downtime", "gym equipment downtime management software UK", True),
    ("gym equipment downtime", "member retention strategies", False),
    ("treadmill servicing UK", "treadmill servicing", True),
    ("CRM for fitness operators", "PPM scheduling for gyms", False),
])
def test_keyword_similarity_jaccard(a, b, expected_high):
    score = keyword_similarity(a, b)
    if expected_high:
        assert score >= 0.5, f"Expected high similarity, got {score} for {a!r}/{b!r}"
    else:
        assert score < 0.5, f"Expected low similarity, got {score} for {a!r}/{b!r}"


def test_keyword_similarity_handles_empty():
    assert keyword_similarity("", "anything") == 0.0
    assert keyword_similarity("anything", "") == 0.0


def test_find_similar_keywords_returns_matches():
    db = _FakeDB(
        articles=[
            {"id": "a1", "title": "Gym equipment downtime guide",
             "primary_keyword": "gym equipment downtime", "status": "published"},
        ],
        keywords=[
            {"id": "k1", "term": "gym equipment downtime management software",
             "status": "queued"},
            {"id": "k2", "term": "member churn analytics", "status": "queued"},
        ],
    )
    hits = drive_async(find_similar_keywords(db, "gym equipment downtime", threshold=0.5))
    kinds = {h["kind"] for h in hits}
    assert "keyword" in kinds
    assert "article" in kinds
    assert all("churn" not in (h.get("term") or "") for h in hits)


def test_collect_token_overlaps_threshold():
    items = ["gym equipment downtime guide", "member retention",
             "gym downtime cost reduction"]
    out = collect_token_overlaps(items, "gym equipment downtime", threshold=0.5)
    assert any("downtime guide" in t for t, _ in out)
    assert all(s >= 0.5 for _, s in out)


# ── Layer 4: article uniqueness ─────────────────────────────────────


def test_article_similarity_score_high_when_openers_overlap():
    score = article_similarity_score(
        "Reduce gym equipment downtime",
        "A broken treadmill at 6 am costs more than a repair bill. "
        "Here are practical strategies operators use to cut downtime.",
        "Gym equipment downtime management software UK",
        "A broken treadmill at 6 am costs more than a repair bill. "
        "Here is how UK operators are using software to cut downtime.",
    )
    assert score >= 0.5, f"Two near-identical openers should score high, got {score}"


def test_article_similarity_score_low_when_distinct():
    score = article_similarity_score(
        "Member retention playbook",
        "Members leave when they don't see results in the first 90 days.",
        "PPM scheduling guide for multi-site gyms",
        "A spreadsheet can hold three sites; by site four the wheels come off.",
    )
    assert score < 0.4, f"Distinct articles should score low, got {score}"


def test_check_article_uniqueness_flags_duplicate():
    db = _FakeDB(articles=[
        {"id": "a1", "title": "Reduce gym equipment downtime",
         "slug": "reduce-downtime",
         "body_md": "# Title\n\nA broken treadmill at 6 am costs more than a repair bill. "
                    "Here are practical strategies operators use to cut downtime and protect members.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db,
        title="Gym equipment downtime management software UK",
        body_md="# Title\n\nA broken treadmill at 6 am costs more than a repair bill. "
                "Here is how UK operators use software to cut downtime and keep members.",
        threshold=0.3,
    ))
    assert not result["ok"]
    assert result["best_match"]["id"] == "a1"
    assert result["best_score"] > 0.3


def test_check_article_uniqueness_ok_when_distinct():
    db = _FakeDB(articles=[
        {"id": "a1", "title": "Member retention playbook",
         "body_md": "# T\n\nMembers churn fast in the first 90 days.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db,
        title="PPM scheduling for multi-site gyms",
        body_md="# T\n\nA spreadsheet collapses by your fourth gym opening.",
        threshold=0.6,
    ))
    assert result["ok"]


def test_check_article_uniqueness_skips_excluded_id():
    db = _FakeDB(articles=[
        {"id": "self", "title": "Same article",
         "body_md": "# T\n\nSame opener text right here.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db, title="Same article",
        body_md="# T\n\nSame opener text right here.",
        exclude_id="self", threshold=0.5,
    ))
    assert result["ok"]
    assert result["best_match"] is None
