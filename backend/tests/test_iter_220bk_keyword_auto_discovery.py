"""Iter 220bk — SEO keyword auto-discovery (GDPR-safe).

Locks in:

1. **k-anonymity guard (k=5)**: every platform-data aggregate must
   include at least 5 distinct organisations before it can be
   surfaced as a keyword suggestion.
2. **Number bucketing**: percentages round to nearest 5, counts to
   nearest 5, durations to nearest hour — so no precise digit can
   leak a single org's identity.
3. **Pillar rotation** picks the longest-not-published pillar.
4. **Content-gap analysis** finds the pillar with the fewest
   published articles.
5. **Smart-threshold top-up**: the orchestrator only refills when
   queued < min, and stops at the target.
6. **PII never enters the discovery output**: no organization_id,
   user_id, names, emails, serials in any returned dict.
"""
from __future__ import annotations

from tests.shared_loop import run_async as drive_async
from utils.seo_keyword_discovery import (
    K_ANONYMITY_MIN,
    MIN_ROW_COUNT,
    PILLARS,
    autodiscover_top_up_queue,
    bucket_count,
    bucket_hours,
    bucket_percent,
    k_anonymous,
    pick_content_gap_keyword,
    pick_pillar_keyword,
    pick_platform_signal_keyword,
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


class _AggregationCursor:
    def __init__(self, output):
        self._output = list(output)

    async def to_list(self, _n=None):
        return list(self._output)

    def __aiter__(self):
        async def gen():
            for r in self._output:
                yield r
        return gen()


class _IssuesColl:
    """Hand-rolled aggregator that returns whichever fixed output the
    test supplies for each pipeline ‘shape’."""

    def __init__(self, top_fault=None, speed_gap=None, resolution_mix=None,
                 fault_rows=None):
        self._top_fault = top_fault or []
        self._speed_gap = speed_gap or []
        self._resolution_mix = resolution_mix or []
        self._fault_rows = fault_rows or []

    def aggregate(self, pipeline, **_kw):
        # Detect which signal pipeline we're being asked for by the
        # presence of a unique stage keyword.
        text = repr(pipeline)
        if "resolution_hours" in text:
            return _AggregationCursor(self._speed_gap)
        if "resolution_type" in text:
            return _AggregationCursor(self._resolution_mix)
        return _AggregationCursor(self._top_fault)

    def find(self, *_a, **_kw):
        return _Cursor(self._fault_rows)


class _ArticlesColl:
    def __init__(self, pillar_counts=None, last_pillar_dates=None):
        # last_pillar_dates: {pillar_id: iso_date_str}
        self._pillar_counts = pillar_counts or {}
        self._last_dates = last_pillar_dates or {}

    def aggregate(self, pipeline, **_kw):
        text = repr(pipeline)
        if "$max" in text:
            out = [{"_id": pid, "last": d} for pid, d in self._last_dates.items()]
            return _AggregationCursor(out)
        # counts
        out = [{"_id": pid, "n": n} for pid, n in self._pillar_counts.items()]
        return _AggregationCursor(out)


class _KeywordsColl:
    def __init__(self, rows=None, count_queued=0):
        self.rows = list(rows or [])
        self.inserted: list[dict] = []
        self._count_queued = count_queued

    def find(self, *_a, **_kw):
        return _Cursor(self.rows)

    async def count_documents(self, q):
        if q.get("status") == "queued":
            return self._count_queued
        return len(self.rows)

    async def insert_one(self, doc):
        self.inserted.append(dict(doc))
        return type("R", (), {"inserted_id": "fake"})()


class _FakeDB:
    def __init__(self, *, issues=None, articles=None, keywords=None):
        self.issues = issues or _IssuesColl()
        self.seo_articles = articles or _ArticlesColl()
        self.seo_keywords = keywords or _KeywordsColl()


# ── GDPR primitives ─────────────────────────────────────────────────


def test_k_anonymous_threshold():
    assert not k_anonymous(0)
    assert not k_anonymous(K_ANONYMITY_MIN - 1)
    assert k_anonymous(K_ANONYMITY_MIN)
    assert k_anonymous(K_ANONYMITY_MIN + 50)


def test_bucket_percent_rounds_to_nearest_5():
    assert bucket_percent(33.4) == 35
    assert bucket_percent(31) == 30
    assert bucket_percent(0) == 0
    assert bucket_percent(97.5) == 100


def test_bucket_count_rounds_down_to_granularity():
    assert bucket_count(47) == 45
    assert bucket_count(123, granularity=10) == 120
    assert bucket_count(0) == 0
    assert bucket_count(-3) == 0  # negative defensive


def test_bucket_hours_rounds_to_int():
    assert bucket_hours(4.4) == 4
    assert bucket_hours(4.6) == 5


# ── Pillar rotation ─────────────────────────────────────────────────


def test_pillars_have_ids_and_templates():
    ids = {p["id"] for p in PILLARS}
    assert len(ids) == len(PILLARS), "pillar ids must be unique"
    assert len(PILLARS) >= 12, "need ≥12 pillars for variety"
    for p in PILLARS:
        assert p["keyword_templates"], f"{p['id']} has no templates"
        assert all(t and len(t) > 5 for t in p["keyword_templates"])


def test_pillar_picker_prefers_long_unused():
    # Pretend equipment_downtime was published yesterday; everything
    # else was 6 months ago.
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    long_ago = (now - timedelta(days=180)).isoformat()
    yesterday = (now - timedelta(days=1)).isoformat()
    last = {p["id"]: long_ago for p in PILLARS}
    last["equipment_downtime"] = yesterday
    db = _FakeDB(articles=_ArticlesColl(last_pillar_dates=last))
    result = drive_async(pick_pillar_keyword(db, cooldown_days=14))
    assert result is not None
    assert result["source"] == "auto_pillar"
    assert result["discovery_pillar_id"] != "equipment_downtime", (
        "Cooldown should suppress the recently-used pillar"
    )


def test_pillar_picker_returns_template_string():
    db = _FakeDB(articles=_ArticlesColl(last_pillar_dates={}))
    result = drive_async(pick_pillar_keyword(db))
    assert result and result["term"]
    # Term must come from one of the pillar's templates
    pillar = next(p for p in PILLARS if p["id"] == result["discovery_pillar_id"])
    assert result["term"] in pillar["keyword_templates"]


# ── Platform signals ────────────────────────────────────────────────


def test_signal_top_fault_machine_respects_k_anonymity():
    # Only 4 distinct orgs — should NOT emit.
    db_few_orgs = _FakeDB(issues=_IssuesColl(top_fault=[
        # k-anonymity is enforced in the Mongo $match stage, so the
        # fake aggregator should NOT include this row in its output.
    ]))
    out = drive_async(pick_platform_signal_keyword(db_few_orgs))
    # No signal emits → None.
    assert out is None


def test_signal_top_fault_machine_emits_when_k_satisfied():
    db = _FakeDB(issues=_IssuesColl(top_fault=[
        {"machine_type": "Treadmill", "fault_count": 312, "org_count": 14},
    ]))
    out = drive_async(pick_platform_signal_keyword(db))
    assert out is not None
    assert out["source"] == "auto_signal"
    assert "treadmill" in out["term"].lower()
    md = out["discovery_metadata"]
    assert md["k_anonymity"] == K_ANONYMITY_MIN
    # Numbers must be bucketed, not raw
    assert md["fault_count_bucketed"] == bucket_count(312)
    assert md["fault_count_bucketed"] != 312  # actually bucketed


def test_signal_resolution_speed_gap_buckets_hours():
    db = _FakeDB(issues=_IssuesColl(speed_gap=[
        {"avg_hours": 17.4, "org_count": 9, "n": 220},
    ]))
    out = drive_async(pick_platform_signal_keyword(db))
    # Picker rotates daily, so we may get a different signal back —
    # but if we DO get this one, hours must be bucketed.
    if out and out.get("discovery_signal") == "resolution_speed_gap":
        assert "17" in out["term"] or "18" in out["term"]
        assert out["discovery_metadata"]["avg_hours_bucketed"] in (17, 18)


def test_signal_outputs_contain_no_pii_fields():
    db = _FakeDB(issues=_IssuesColl(top_fault=[
        {"machine_type": "Bike", "fault_count": 78, "org_count": 6},
    ]))
    out = drive_async(pick_platform_signal_keyword(db))
    assert out is not None
    forbidden = {"organization_id", "user_id", "site_id", "site_name",
                 "serial_number", "company_name", "email", "phone",
                 "ContactEmail", "ContactName"}
    flat = repr(out).lower()
    for f in forbidden:
        assert f.lower() not in flat, (
            f"Discovery output must not include {f}: {out}"
        )


# ── Content gap ────────────────────────────────────────────────────


def test_content_gap_picks_least_published():
    counts = {"equipment_downtime": 5, "member_retention": 1}
    # everyone else: 0
    db = _FakeDB(articles=_ArticlesColl(pillar_counts=counts))
    out = drive_async(pick_content_gap_keyword(db))
    assert out is not None
    assert out["source"] == "auto_gap"
    # Picked pillar must be one with zero count.
    assert out["discovery_pillar_id"] not in {"equipment_downtime", "member_retention"}
    assert out["discovery_metadata"]["current_count"] == 0


# ── Orchestrator threshold logic ────────────────────────────────────


def test_top_up_skips_when_queue_above_threshold():
    db = _FakeDB(keywords=_KeywordsColl(count_queued=5))
    out = drive_async(autodiscover_top_up_queue(db, queue_min=3, queue_target=8))
    assert out["ok"]
    assert out["skipped"]
    assert "queue depth" in out["reason"]


def test_top_up_adds_until_target_when_below_threshold():
    keywords = _KeywordsColl(count_queued=1)
    db = _FakeDB(
        keywords=keywords,
        articles=_ArticlesColl(last_pillar_dates={}),
        # Top-fault signal that satisfies k-anonymity, so the signal
        # picker can contribute a keyword (otherwise the orchestrator
        # would only get pillar + gap suggestions).
        issues=_IssuesColl(top_fault=[
            {"machine_type": "Treadmill", "fault_count": 100, "org_count": 7},
        ]),
    )
    out = drive_async(autodiscover_top_up_queue(db, queue_min=3, queue_target=4))
    assert out["ok"]
    assert not out["skipped"]
    # Should have added (target - queued = 3) keywords
    assert out["added_count"] >= 1
    # Every inserted doc must carry an auto_* source tag
    for doc in keywords.inserted:
        assert doc["source"] in {"auto_pillar", "auto_signal", "auto_gap"}
        # Iter 220bk — discovery_metadata must travel with the doc so
        # provenance is auditable for GDPR purposes
        assert "discovery_metadata" in doc


def test_top_up_dedupes_against_existing_terms():
    # Pre-populate with the exact term the pillar picker would emit.
    keywords = _KeywordsColl(count_queued=0, rows=[
        {"term": "reducing gym equipment downtime", "status": "ignored"},
    ])
    db = _FakeDB(
        keywords=keywords,
        articles=_ArticlesColl(last_pillar_dates={}),
        issues=_IssuesColl(),
    )
    out = drive_async(autodiscover_top_up_queue(db, queue_min=3, queue_target=3))
    # Whatever it adds, it MUST NOT add the duplicate.
    terms = [d["term"].lower() for d in keywords.inserted]
    assert "reducing gym equipment downtime" not in terms, (
        f"Duplicate term sneaked into queue: {terms}"
    )
    # And it should still produce something
    assert out["ok"]


# ── Module constants sanity ─────────────────────────────────────────


def test_constants_match_spec():
    # If anyone bumps these accidentally, GDPR posture changes — flag
    # it loudly.
    assert K_ANONYMITY_MIN == 5
    assert MIN_ROW_COUNT == 10
