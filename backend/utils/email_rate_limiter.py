"""Resend rate limiter — async token-bucket pacer (Iter 216h100).

Resend's free / shared tier enforces ``5 requests per second``. Our
signup-journey worker and lifecycle email batcher routinely fire 20+
emails inside the same second, which triggers ``Too many requests`` —
~10k of those failures show in ``email_send_events`` historically.

This module sits in front of every ``resend.Emails.send`` call. It:

* Allows ``MAX_RPS`` requests per second (default 4 — one below the
  ceiling for safety margin).
* If the bucket is empty, callers ``await`` until a slot opens.
* Multiple producers fan into one shared semaphore so the pacing is
  process-wide.
* A tiny jitter (0-30ms) breaks lock-step bursts when 50 producers
  all woke up on the same tick.

The implementation is a simple sliding-window timestamp deque guarded
by an ``asyncio.Lock`` — cheap, no extra deps, single-process safe
which is what we run under supervisor.

We DO NOT use a separate queue process: backpressure is implicit
(callers naturally wait). This avoids the "stuck queue" failure mode
where messages live in Redis forever.

For observability, ``pending()`` returns the number of waiters and is
surfaced on ``/api/health/full`` as ``email.queue_depth`` so the
Master Admin can see when a backlog is building.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections import deque

logger = logging.getLogger(__name__)

# Configurable via env. Defaults chosen to sit one tick below Resend's
# 5 req/s shared limit so background bursts (signup welcome series,
# lifecycle emails) never trip the rate-limit.
MAX_RPS = int(os.environ.get("RESEND_MAX_RPS", "4"))
WINDOW_SECONDS = 1.0

_lock = asyncio.Lock()
_recent: deque[float] = deque()   # monotonic timestamps of recent sends
_waiting = 0                       # current count of awaiting tasks


async def acquire() -> None:
    """Block until a slot in the rate window is available."""
    global _waiting
    _waiting += 1
    try:
        while True:
            async with _lock:
                now = time.monotonic()
                # Drop timestamps that fell out of the rolling window.
                while _recent and now - _recent[0] >= WINDOW_SECONDS:
                    _recent.popleft()
                if len(_recent) < MAX_RPS:
                    _recent.append(now)
                    return
                # Sleep until the oldest entry rolls out + jitter.
                sleep_for = WINDOW_SECONDS - (now - _recent[0])
            # Add 0-30ms jitter to break lock-step bursts where many
            # producers all woke up on the same clock tick.
            await asyncio.sleep(max(0.001, sleep_for) + random.uniform(0.0, 0.03))
    finally:
        _waiting -= 1


def pending() -> int:
    """Current number of tasks blocked waiting for a send slot."""
    return max(0, _waiting)


def stats() -> dict:
    """Diagnostic snapshot used by ``/api/health/full``."""
    now = time.monotonic()
    while _recent and now - _recent[0] >= WINDOW_SECONDS:
        _recent.popleft()
    return {
        "max_rps": MAX_RPS,
        "in_window": len(_recent),
        "queue_depth": pending(),
    }
