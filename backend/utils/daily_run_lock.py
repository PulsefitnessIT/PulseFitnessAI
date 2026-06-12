"""Iter 264 — Atomic daily-run claim for in-process schedulers.

Root cause of the duplicate blog posts (production, Jun 6 + Jun 11):
``run_daily_autopilot_loop`` used a *check-then-act* stamp —

    if not already_ran_today():   # both replicas pass
        result = run()            # minutes of LLM work
        stamp()                   # stamped only AFTER the run

Production runs more than one backend process, each with its own loop.
Both woke in the same 15-minute window, both saw "not ran today", both
generated and published the same keyword seconds apart (the observed
pairs are 4s / 12s apart, the second one with a ``-xxxxxx`` slug suffix
from the slug-collision path).

``claim_daily_run`` closes the race: the day's doc is created
*atomically before* any work starts, backed by a unique index on
``date``. Exactly one process owns the claim; everyone else gets False
immediately. If the claimant crashes mid-run (claimed but no result
after ``stale_minutes``), the next wake-up may atomically reclaim it.
"""

import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

_indexed_collections: set[str] = set()


async def _ensure_unique_date_index(collection) -> None:
    """Unique index on ``date`` makes the claim upsert race-proof.
    Cached per process so it runs once per collection."""
    if collection.name in _indexed_collections:
        return
    try:
        await collection.create_index("date", unique=True)
        _indexed_collections.add(collection.name)
    except Exception as exc:  # pragma: no cover — index may already exist
        logger.warning("[daily-run-lock] index init on %s failed: %s",
                       collection.name, exc)


async def claim_daily_run(collection, date_str: str, *,
                          stale_minutes: int = 120) -> bool:
    """Atomically claim ``date_str``'s run. Returns True iff THIS caller
    owns the run and should execute it. Completed days (a ``result`` is
    present, or a manual stamp) always return False."""
    await _ensure_unique_date_index(collection)
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    try:
        await collection.update_one(
            {"date": date_str},
            {"$setOnInsert": {
                "date": date_str,
                "status": "running",
                "claim_token": token,
                "claimed_at": now.isoformat(),
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        # Two upserts raced on the unique index — the other one won the
        # insert; fall through and inspect the stored doc.
        pass

    doc = await collection.find_one({"date": date_str}, {"_id": 0}) or {}
    if doc.get("claim_token") == token:
        return True

    # Day already completed (result stamped, or a manual run).
    if doc.get("result") is not None or doc.get("manual"):
        return False

    # A previous claimant may have crashed mid-run: reclaim atomically
    # once the claim is stale. The token filter makes this a CAS — only
    # one process can swap the token.
    if doc.get("status") == "running":
        claimed_at = doc.get("claimed_at")
        try:
            claimed_dt = datetime.fromisoformat(claimed_at) if claimed_at else None
        except ValueError:
            claimed_dt = None
        if claimed_dt is None or now - claimed_dt > timedelta(minutes=stale_minutes):
            res = await collection.update_one(
                {"date": date_str, "claim_token": doc.get("claim_token"),
                 "result": None},
                {"$set": {"claim_token": token,
                          "claimed_at": now.isoformat(),
                          "reclaimed": True}},
            )
            if res.modified_count == 1:
                logger.info("[daily-run-lock] reclaimed stale %s run on %s",
                            date_str, collection.name)
                return True
    return False
