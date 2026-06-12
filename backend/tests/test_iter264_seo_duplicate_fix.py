"""Iter 264 — SEO autopilot duplicate-article fix.

User report (production): duplicate blog posts keep appearing on
https://gymaxisai.com/blog. Confirmed pairs (identical titles, published
4s / 12s apart, second slug carries a ``-xxxxxx`` suffix):
  • "Preventative maintenance benchmarks UK gyms…"  (Jun 11, 08:13:02 + 08:12:58)
  • "Gym CRM and operations software UK…"           (Jun 06, 08:09:35 + 08:09:23)

ROOT CAUSE: ``run_daily_autopilot_loop`` used check-then-act — it read
the "ran today" stamp, spent minutes generating, and stamped only AFTER
publishing. Production runs >1 backend process, each with its own loop:
both passed the check and both published.

FIX (three layers):
 1. ``utils.daily_run_lock.claim_daily_run`` — atomic per-day claim
    (unique index on ``date``) acquired BEFORE any work. SEO + social
    loops both use it.
 2. Publish-time guard in ``generate_article`` — a base-slug collision
    with an equal normalised title is held as ``needs_review`` instead
    of auto-publishing with a suffixed slug.
 3. ``dedupe_published_duplicate_titles`` — idempotent startup migration
    (via ``init_seo_indexes``) archives all but the earliest copy of any
    published duplicate-title group, so redeploying self-heals the
    production database.
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from utils.database import db
from utils.daily_run_lock import claim_daily_run


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_claim_is_exclusive_under_concurrency():
    """5 concurrent claimants on the same day — exactly ONE wins."""
    async def scenario():
        coll = db.test_iter264_runs
        await coll.delete_many({})
        day = "2099-01-01"
        results = await asyncio.gather(*[
            claim_daily_run(coll, day) for _ in range(5)
        ])
        docs = await coll.count_documents({"date": day})
        await coll.drop()
        return results, docs
    results, docs = _run(scenario())
    assert sum(1 for r in results if r) == 1, results
    assert docs == 1


def test_claim_completed_day_returns_false():
    """A day with a stamped result (legacy or new format) is never
    re-claimed — including old prod docs without claim_token."""
    async def scenario():
        coll = db.test_iter264_runs
        await coll.delete_many({})
        await coll.insert_one({"date": "2099-01-02",
                               "result": {"ok": True}, "ran_at": "x"})
        claimed = await claim_daily_run(coll, "2099-01-02")
        await coll.drop()
        return claimed
    assert _run(scenario()) is False


def test_claim_stale_crashed_run_is_reclaimed():
    """A claimant that died mid-run (running, no result, stale) can be
    reclaimed exactly once."""
    async def scenario():
        coll = db.test_iter264_runs
        await coll.delete_many({})
        stale = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        await coll.insert_one({"date": "2099-01-03", "status": "running",
                               "claim_token": "dead-process",
                               "claimed_at": stale, "result": None})
        first = await claim_daily_run(coll, "2099-01-03", stale_minutes=120)
        second = await claim_daily_run(coll, "2099-01-03", stale_minutes=120)
        await coll.drop()
        return first, second
    first, second = _run(scenario())
    assert first is True
    assert second is False


def test_fresh_running_claim_is_not_stolen():
    async def scenario():
        coll = db.test_iter264_runs
        await coll.delete_many({})
        now = datetime.now(timezone.utc).isoformat()
        await coll.insert_one({"date": "2099-01-04", "status": "running",
                               "claim_token": "alive-process",
                               "claimed_at": now, "result": None})
        claimed = await claim_daily_run(coll, "2099-01-04", stale_minutes=120)
        await coll.drop()
        return claimed
    assert _run(scenario()) is False


def test_dedupe_archives_newer_duplicate_keeps_oldest():
    """The startup migration archives all but the EARLIEST published
    copy of a duplicate-title group — exactly the production scenario."""
    from routes.marketing.seo_autopilot import dedupe_published_duplicate_titles

    marker = uuid.uuid4().hex[:8]
    title = f"Iter264 dedupe test article {marker}"
    base = {
        "title": title, "status": "published", "body_md": "x",
        "created_at": "2099-01-01T00:00:00+00:00",
    }
    a_id, b_id = str(uuid.uuid4()), str(uuid.uuid4())

    async def scenario():
        await db.seo_articles.insert_many([
            {**base, "id": a_id, "slug": f"iter264-{marker}",
             "published_at": "2099-01-01T08:00:00+00:00"},
            {**base, "id": b_id, "slug": f"iter264-{marker}-abc123",
             "published_at": "2099-01-01T08:00:12+00:00"},
        ])
        result = await dedupe_published_duplicate_titles()
        a = await db.seo_articles.find_one({"id": a_id}, {"_id": 0, "status": 1})
        b = await db.seo_articles.find_one(
            {"id": b_id}, {"_id": 0, "status": 1, "archived_reason": 1})
        # Idempotency — second run archives nothing further for this group.
        again = await dedupe_published_duplicate_titles()
        await db.seo_articles.delete_many({"id": {"$in": [a_id, b_id]}})
        return result, a, b, again

    result, a, b, again = _run(scenario())
    assert f"iter264-{marker}-abc123" in result["archived"]
    assert a["status"] == "published", "the ORIGINAL must stay live"
    assert b["status"] == "archived"
    assert b["archived_reason"] == "duplicate_title_auto_dedupe"
    assert f"iter264-{marker}" not in again["archived"]


def test_source_pins():
    seo = open("/app/backend/routes/marketing/seo_autopilot.py", encoding="utf-8").read()
    assert "claim_daily_run(db.seo_autopilot_runs" in seo, (
        "SEO daily loop must claim the day atomically before running"
    )
    assert "held_duplicate_title" in seo, (
        "generate_article must hold identical-title collisions for review"
    )
    assert "dedupe_published_duplicate_titles" in seo

    social = open("/app/backend/routes/marketing/social_autopilot.py", encoding="utf-8").read()
    assert "claim_daily_run(db.social_autopilot_runs" in social, (
        "social daily loop must claim the day atomically before running"
    )


def test_runs_collection_has_unique_date_index():
    async def scenario():
        coll = db.test_iter264_runs2
        await coll.delete_many({})
        # First claim creates the unique index lazily.
        await claim_daily_run(coll, "2099-02-01")
        info = await coll.index_information()
        await coll.drop()
        return info
    info = _run(scenario())
    assert any(v.get("unique") and v.get("key") == [("date", 1)]
               for v in info.values()), info
