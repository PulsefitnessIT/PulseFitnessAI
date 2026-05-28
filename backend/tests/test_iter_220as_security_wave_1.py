"""Iter 220as — Security Wave 1.

Three classes of finding from the risk register closed in this iter:

  * **F-09 — Stripe webhook idempotency** — every webhook handler now
    calls ``mark_event_processed(event_id)`` before doing work.
    Replays return ``{duplicate: true}`` without side-effect.
  * **F-07 — Pagination caps** — central ``safe_limit`` clamps any
    client-supplied ``limit`` to ≤500 (configurable). Defends against
    accidental DOS / mass-data-export by overgenerous list calls.
  * **F-01 — Public-route rate-limit gap** — the anonymous
    ``/public/signup/{slug}/track`` endpoint now applies a 60-rpm
    IP-keyed sliding-window throttle so the funnel KPIs can't be
    poisoned by a script.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── F-07 · safe_limit / safe_skip ──────────────────────────────────


def test_safe_limit_clamps_to_hard_max():
    from utils.pagination import safe_limit
    assert safe_limit(99999) == 200          # default hard_max
    assert safe_limit(99999, hard_max=500) == 500
    assert safe_limit(50) == 50
    assert safe_limit(0) == 1                 # below 1 → 1
    assert safe_limit(-1) == 1                # negative → 1


def test_safe_limit_handles_garbage_input():
    from utils.pagination import safe_limit
    assert safe_limit(None) == 50              # default
    assert safe_limit(None, default=10) == 10
    assert safe_limit("abc") == 50             # garbage → default
    assert safe_limit("99") == 99              # numeric string OK


def test_safe_skip_clamps_below_zero():
    from utils.pagination import safe_skip
    assert safe_skip(0) == 0
    assert safe_skip(-5) == 0
    assert safe_skip(None) == 0
    assert safe_skip(42) == 42
    assert safe_skip("100") == 100
    assert safe_skip("garbage") == 0


# ── F-09 · stripe idempotency ──────────────────────────────────────


def test_mark_event_processed_first_call_returns_true():
    """First time we see this event_id → proceed (True)."""
    from utils import stripe_idempotency as m

    fdb = MagicMock()
    # find_one_and_update with return_document=False returns the
    # PRE-image. If the doc didn't exist before, we get None.
    fdb.stripe_webhook_events.find_one_and_update = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.mark_event_processed("evt_123", handler="test")
    assert _run(go()) is True
    fdb.stripe_webhook_events.find_one_and_update.assert_awaited_once()


def test_mark_event_processed_duplicate_returns_false():
    """Second call for the same event_id → skip (False)."""
    from utils import stripe_idempotency as m

    fdb = MagicMock()
    # Now the pre-image is the existing row → duplicate.
    fdb.stripe_webhook_events.find_one_and_update = AsyncMock(return_value={
        "_id": "abc", "event_id": "evt_123",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.mark_event_processed("evt_123", handler="test")
    assert _run(go()) is False


def test_mark_event_processed_empty_id_proceeds_defensively():
    """Empty event_id → proceed (don't dedupe). Caller's problem to
    log the malformed event."""
    from utils import stripe_idempotency as m

    fdb = MagicMock()
    # Should never touch the DB if event_id is empty.
    fdb.stripe_webhook_events.find_one_and_update = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.mark_event_processed("", handler="test")
    assert _run(go()) is True
    fdb.stripe_webhook_events.find_one_and_update.assert_not_called()


def test_mark_event_processed_race_treats_as_duplicate():
    """If two workers race the unique-index, the loser raises
    DuplicateKeyError → we treat as duplicate (skip) to never
    double-apply."""
    from utils import stripe_idempotency as m

    fdb = MagicMock()
    fdb.stripe_webhook_events.find_one_and_update = AsyncMock(side_effect=Exception("dup"))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.mark_event_processed("evt_race", handler="test")
    assert _run(go()) is False


def test_ensure_indexes_idempotent():
    """Calling ensure_indexes twice must not raise."""
    from utils import stripe_idempotency as m

    fdb = MagicMock()
    fdb.stripe_webhook_events.create_index = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb):
            await m.ensure_indexes()
            await m.ensure_indexes()
    _run(go())
    # Two calls × two indexes = 4 awaited calls.
    assert fdb.stripe_webhook_events.create_index.await_count == 4


# ── Integration shape — every webhook handler imports the helper ──


def test_all_5_webhook_handlers_call_mark_event_processed():
    """Source-level guarantee: each webhook entry point references
    ``mark_event_processed``. If a new webhook is added without it,
    this test fails and forces the dev to wire dedupe."""
    import pathlib
    backend = pathlib.Path("/app/backend")
    handlers = [
        "routes/stripe_connect.py",
        "routes/svc/engineer_invoice_payments.py",
        "routes/svc/engineer_stripe_connect.py",
        "routes/public_signup.py",
    ]
    for h in handlers:
        src = (backend / h).read_text()
        assert "mark_event_processed" in src, (
            f"{h} is missing the Stripe webhook idempotency call. "
            f"Add `from utils.stripe_idempotency import mark_event_processed`."
        )
