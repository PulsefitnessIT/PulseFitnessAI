"""Stripe **client-side** idempotency helper — Iter 220bo.

The platform already dedupes inbound webhook events via
``utils.stripe_idempotency`` (Iter 220as). This module covers the
*outbound* direction: every Stripe SDK write call (``checkout.Session.create``,
``Subscription.modify``, ``PaymentIntent.create``, etc.) accepts an
``idempotency_key`` request option so retries on transient 5xx/network
hiccups don't create duplicate sessions or duplicate subscription
mutations.

Usage::

    from utils.stripe_client_idempotency import stripe_idem_key

    session = stripe.checkout.Session.create(
        ...,
        idempotency_key=stripe_idem_key("partner_plan_checkout", partner["id"]),
    )

Conventions:
* Keys are deterministic per (caller-intent, identity, action) tuple
  so a retry from the same client lands on the same key — the whole
  point of idempotency.
* Per Stripe docs, keys must be unique per (account, endpoint) pair
  for 24 hours. We salt with a ``minute_bucket`` so a deliberate
  retry within a minute hits the same key, but a deliberate retry the
  next day generates a fresh charge (correct semantics for
  e.g. "subscribe again next month").
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def stripe_idem_key(intent: str, *identity: str,
                    bucket_minutes: int = 1) -> str:
    """Return a deterministic, Stripe-safe idempotency key.

    Keys are ``≤ 255`` ASCII chars (Stripe limit), composed as a
    SHA-256 hex digest of the intent + identity tuple + minute bucket.

    ``bucket_minutes`` controls the retry window — within the same
    bucket, the same call generates the same key. Defaults to 1
    minute, which is long enough to absorb any reasonable retry from
    a flaky network or a double-click, but short enough that the
    next legitimate "subscribe again" attempt generates a fresh key.
    """
    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp() // (max(1, bucket_minutes) * 60))
    raw = f"{intent}|{'|'.join(str(p) for p in identity)}|{bucket}"
    return f"gx_{hashlib.sha256(raw.encode()).hexdigest()[:48]}"


__all__ = ["stripe_idem_key"]
