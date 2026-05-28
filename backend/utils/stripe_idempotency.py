"""Stripe webhook idempotency helper — Iter 220as.

Stripe retries webhook deliveries with the same ``event.id`` on any
5xx or network failure response from us. Without dedupe, that means
the same ``checkout.session.completed`` (or any other event) can
trigger double sub-grants, double partner-engineer payouts, and
double inventory side-effects.

Usage::

    @router.post("/api/payments/stripe/webhook")
    async def handle(request: Request):
        ...
        event = stripe.Webhook.construct_event(...)
        if not await mark_event_processed(event["id"], handler="payments"):
            return {"received": True, "duplicate": True}
        # ... do the work ...

The first call for a given ``event_id`` returns True (proceed). Any
later call returns False (skip — already processed). We persist a
small marker row with a 30-day TTL so the collection self-prunes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.database import db


async def mark_event_processed(event_id: str, *, handler: str = "default") -> bool:
    """Return True if this is the first time we've seen ``event_id``,
    False if it was already processed. Atomic via Mongo's unique
    index + ``upsert``."""
    if not event_id:
        # Defensive: empty event_id means malformed event — let the
        # caller proceed but emit a warning. Don't dedupe.
        return True
    now = datetime.now(timezone.utc)
    try:
        # ``find_one_and_update`` with upsert + check the pre-image:
        # if we get a doc back, it existed before — duplicate.
        existing = await db.stripe_webhook_events.find_one_and_update(
            {"event_id": event_id},
            {"$setOnInsert": {
                "event_id": event_id,
                "handler": handler,
                "processed_at": now,
            }},
            upsert=True,
            return_document=False,  # return pre-image
        )
        # find_one_and_update returns None if the doc didn't exist
        # before (and we inserted it). Any non-None value means it
        # was a duplicate.
        return existing is None
    except Exception:
        # If the unique index races, the second writer raises a
        # DuplicateKeyError and ends up here. Fail-safe: treat as
        # duplicate (skip processing) so we never double-apply.
        return False


async def ensure_indexes() -> None:
    """Idempotent: create the unique index + TTL on first call."""
    try:
        await db.stripe_webhook_events.create_index(
            "event_id", unique=True, name="event_id_unique",
        )
        # 30-day TTL — well past Stripe's retry window (which is 3 days).
        await db.stripe_webhook_events.create_index(
            "processed_at",
            expireAfterSeconds=30 * 24 * 60 * 60,
            name="processed_at_ttl",
        )
    except Exception:
        pass


__all__ = ["mark_event_processed", "ensure_indexes"]
