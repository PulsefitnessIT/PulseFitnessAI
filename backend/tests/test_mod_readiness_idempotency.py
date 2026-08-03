"""Idempotency regression tests for MOD Estate Readiness weekly digest.

Verifies the fix for runaway duplicate emails (48 copies/hour) caused by a
broken $ne filter on the per-ISO-week claim in system_jobs. The corrected
implementation uses $setOnInsert keyed on (job, week_tag).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

# Ensure /app/backend is importable
BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.chdir(BACKEND_DIR)

from utils.database import db  # noqa: E402
from utils.mod_readiness_digest import (  # noqa: E402
    JOB_KEY,
    _iso_week_tag,
    run_mod_readiness_weekly,
    send_mod_readiness_email,
)


CURRENT_WEEK = _iso_week_tag(datetime.now(timezone.utc))


async def _count_current_week_docs() -> int:
    return await db.system_jobs.count_documents(
        {"job": JOB_KEY, "week_tag": CURRENT_WEEK}
    )


async def _count_any_week_docs() -> int:
    return await db.system_jobs.count_documents({"job": JOB_KEY})


async def _delete_current_week_claim() -> None:
    await db.system_jobs.delete_many({"job": JOB_KEY, "week_tag": CURRENT_WEEK})


async def _reclaim_lock_if_missing() -> None:
    """Safety net: ensure current-week lock exists after tests, so the live
    poller does not resend this week."""
    exists = await _count_current_week_docs()
    if exists == 0:
        await db.system_jobs.update_one(
            {"job": JOB_KEY, "week_tag": CURRENT_WEEK},
            {"$setOnInsert": {"job": JOB_KEY, "week_tag": CURRENT_WEEK,
                              "claimed_at": datetime.now(timezone.utc).isoformat(),
                              "reclaimed_by_test": True}},
            upsert=True,
        )


# ---------- IDEMPOTENCY (core fix) ----------
class TestIdempotency:
    def test_first_call_sends_second_call_skips(self):
        async def run():
            await _delete_current_week_claim()
            assert await _count_current_week_docs() == 0

            first = await send_mod_readiness_email()
            # First call must NOT be a skip
            assert "skipped" not in first, f"First call unexpectedly skipped: {first}"
            assert first.get("week_tag") == CURRENT_WEEK
            assert "sent" in first
            assert "recipient" in first

            # Exactly one claim doc now
            assert await _count_current_week_docs() == 1

            # Second call MUST skip
            second = await send_mod_readiness_email()
            assert second == {"skipped": "already_sent_this_week",
                              "week_tag": CURRENT_WEEK}, f"Second call: {second}"

            # No additional doc created
            assert await _count_current_week_docs() == 1

            await _reclaim_lock_if_missing()

        asyncio.run(run())

    def test_ten_rapid_calls_only_one_send(self):
        async def run():
            await _delete_current_week_claim()
            assert await _count_current_week_docs() == 0

            results = []
            for _ in range(10):
                results.append(await send_mod_readiness_email())

            sent_results = [r for r in results if "skipped" not in r]
            skipped_results = [r for r in results if r.get("skipped") == "already_sent_this_week"]

            assert len(sent_results) == 1, (
                f"Expected exactly 1 send, got {len(sent_results)}. Results: {results}"
            )
            assert len(skipped_results) == 9, (
                f"Expected 9 skips, got {len(skipped_results)}. Results: {results}"
            )

            # Only one claim doc for the current week
            assert await _count_current_week_docs() == 1

            await _reclaim_lock_if_missing()

        asyncio.run(run())

    def test_no_leak_of_system_jobs_docs(self):
        async def run():
            await _delete_current_week_claim()
            before_other_weeks = await db.system_jobs.count_documents(
                {"job": JOB_KEY, "week_tag": {"$ne": CURRENT_WEEK}}
            )

            for _ in range(5):
                await send_mod_readiness_email()

            # Current-week: exactly 1 doc
            assert await _count_current_week_docs() == 1
            # No new docs for other weeks were added
            after_other_weeks = await db.system_jobs.count_documents(
                {"job": JOB_KEY, "week_tag": {"$ne": CURRENT_WEEK}}
            )
            assert after_other_weeks == before_other_weeks, (
                f"Leak: other-week doc count changed {before_other_weeks} -> {after_other_weeks}"
            )

            await _reclaim_lock_if_missing()

        asyncio.run(run())


# ---------- FORCE PATH ----------
class TestForcePath:
    def test_force_true_bypasses_lock(self):
        async def run():
            # Ensure lock is claimed
            await send_mod_readiness_email()
            assert await _count_current_week_docs() >= 1

            # Force=True must still return a sent result (no skip)
            forced = await send_mod_readiness_email(force=True)
            assert "skipped" not in forced, f"force=True was skipped: {forced}"
            assert "sent" in forced
            assert forced.get("week_tag") == CURRENT_WEEK
            assert "recipient" in forced

            # Force path still doesn't leak claim docs (post-send update is upsert
            # keyed on job — a single doc for current week is still expected)
            # We only require lock still present:
            assert await _count_current_week_docs() >= 1

            await _reclaim_lock_if_missing()

        asyncio.run(run())

    def test_force_multiple_calls_all_send(self):
        async def run():
            r1 = await send_mod_readiness_email(force=True)
            r2 = await send_mod_readiness_email(force=True)
            r3 = await send_mod_readiness_email(force=True)
            for r in (r1, r2, r3):
                assert "skipped" not in r
                assert "sent" in r

            await _reclaim_lock_if_missing()

        asyncio.run(run())


# ---------- WEEKLY CRON GATING ----------
class TestWeeklyCron:
    def test_weekly_cron_never_double_sends(self):
        """Regardless of day/hour, invoking run_mod_readiness_weekly repeatedly
        must not produce more than one 'sent' result for the same ISO week."""
        async def run():
            await _delete_current_week_claim()
            results = []
            for _ in range(6):
                results.append(await run_mod_readiness_weekly())

            not_due = [r for r in results if r.get("skipped") == "not_due"]
            already_sent = [r for r in results if r.get("skipped") == "already_sent_this_week"]
            sent = [r for r in results if "skipped" not in r]

            # Either: all not_due (not Monday >= 09 UTC) — then 0 sends
            # Or: due — then exactly one send and rest skipped
            if not_due:
                # Not due path: no sends at all
                assert len(sent) == 0
                assert len(already_sent) == 0
                # weekday/hour keys present
                assert "weekday" in not_due[0] and "hour" in not_due[0]
            else:
                assert len(sent) == 1, f"Expected 1 send, got {len(sent)}. Results: {results}"
                assert len(already_sent) == 5

            # At most 1 claim doc for current week (0 if not_due path)
            claim_count = await _count_current_week_docs()
            assert claim_count <= 1

            await _reclaim_lock_if_missing()

        asyncio.run(run())

    def test_weekly_cron_when_already_claimed_does_not_resend(self):
        async def run():
            # Pre-claim
            await _reclaim_lock_if_missing()
            assert await _count_current_week_docs() == 1

            result = await run_mod_readiness_weekly()
            # Either not_due (wrong time) or already_sent (right time, already claimed)
            assert "skipped" in result, f"Unexpected send when lock present: {result}"
            assert result.get("skipped") in ("not_due", "already_sent_this_week")

            # No new claim docs
            assert await _count_current_week_docs() == 1

        asyncio.run(run())


# ---------- TEARDOWN ----------
@pytest.fixture(scope="module", autouse=True)
def _ensure_lock_after_all_tests():
    yield
    # Use a fresh event loop for teardown to avoid "attached to a different loop"
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_reclaim_lock_if_missing())
        loop.close()
    except Exception as e:  # pragma: no cover
        print(f"teardown reclaim failed (non-fatal): {e}")
