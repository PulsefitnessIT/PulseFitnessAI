"""Iter 216h172 — Slow-request log surfaced on the Integration Health panel.

The platform already has a comprehensive health surface
(`IntegrationHealthPanel.js` at Master Admin → Security → Integration
Health). This module adds **slow-request telemetry** to the same panel
without building a parallel dashboard — purely an extension to the
existing observability story.

How it works:
  * `SlowRequestLogMiddleware` is registered on the FastAPI app.
  * Every request that exceeds `SLOW_THRESHOLD_MS` (default 1500ms) is
    recorded with method + path + duration + a short user-agent tag.
  * Records are kept in a fixed-size ring (default 200 entries) so we
    never leak memory regardless of traffic.
  * Aggregated stats (`hottest_endpoints`) are computed on demand so
    the ring stays cheap to write.

Why a middleware rather than a per-route decorator:
  * Catches everything — including the long-tail endpoints we haven't
    yet identified as risky.
  * Zero code changes per route — opt-out by design (we'd remove the
    middleware) rather than opt-in.

Why fixed-size ring rather than DB write:
  * The point is "what's been slow in the last 5 minutes?" — a tail
    log is the wrong storage primitive. The ring lets us answer that
    question in O(1) memory with no DB pressure.
  * Multi-pod fleets that need cross-pod aggregation can later flip
    `SlowRequestRing` to push into Redis ZADD with TTL; the public API
    of `record()` / `snapshot()` doesn't change.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── Knobs ─────────────────────────────────────────────────────────
SLOW_THRESHOLD_MS = 1_500
RING_SIZE = 200
# Endpoint patterns to ignore — health probes + static + websockets.
# These are hit on every Kubernetes probe cycle and would drown the ring.
_IGNORE_PATH_PREFIXES = (
    "/health", "/api/health", "/api/auth/me",  # routine high-volume
    "/static", "/_next", "/favicon", "/api/ws", "/ws/",
)


class SlowRequestRing:
    """Thread-safe fixed-size ring of slow requests.

    Each entry is a small dict — we deliberately avoid storing the
    raw request/response so this can never become a privacy bomb."""

    __slots__ = ("_ring", "_lock", "_total_slow_count")

    def __init__(self, capacity: int = RING_SIZE) -> None:
        self._ring: deque[dict] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._total_slow_count = 0

    def record(
        self, *, method: str, path: str, duration_ms: float,
        status: int, user_agent: str | None,
    ) -> None:
        entry = {
            "method": method,
            "path": path,
            "duration_ms": round(duration_ms, 1),
            "status": status,
            "user_agent": (user_agent or "")[:80],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._ring.append(entry)
            self._total_slow_count += 1

    def snapshot(self, top_n: int = 10) -> dict:
        """Return the most recent entries + a per-endpoint roll-up of
        hit count and worst observed duration."""
        with self._lock:
            recent = list(self._ring)
            total = self._total_slow_count
        # Per-endpoint roll-up
        agg: dict[str, dict] = {}
        for e in recent:
            key = f"{e['method']} {_normalize_path(e['path'])}"
            a = agg.setdefault(
                key, {"endpoint": key, "hits": 0, "worst_ms": 0.0, "last_ts": ""},
            )
            a["hits"] += 1
            if e["duration_ms"] > a["worst_ms"]:
                a["worst_ms"] = e["duration_ms"]
                a["last_ts"] = e["ts"]
        hottest = sorted(
            agg.values(), key=lambda r: (r["worst_ms"], r["hits"]), reverse=True,
        )[:top_n]
        return {
            "slow_threshold_ms": SLOW_THRESHOLD_MS,
            "ring_size": RING_SIZE,
            "total_slow_count": total,
            "recent": list(reversed(recent))[:top_n],
            "hottest_endpoints": hottest,
        }

    def reset(self) -> int:
        with self._lock:
            n = self._total_slow_count
            self._ring.clear()
            self._total_slow_count = 0
        return n


def _normalize_path(path: str) -> str:
    """Collapse UUID-like + numeric segments so the roll-up groups
    `/api/svc/cases/abc-123` and `/api/svc/cases/xyz-456` together."""
    out = []
    for seg in path.split("/"):
        if not seg:
            out.append(seg)
            continue
        if len(seg) >= 8 and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg):
            out.append("{id}")
        elif seg.isdigit():
            out.append("{n}")
        else:
            out.append(seg)
    return "/".join(out)


SLOW_REQUESTS = SlowRequestRing()


class SlowRequestLogMiddleware(BaseHTTPMiddleware):
    """Records every request over the slow threshold into `SLOW_REQUESTS`."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _IGNORE_PATH_PREFIXES):
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms >= SLOW_THRESHOLD_MS:
            SLOW_REQUESTS.record(
                method=request.method,
                path=path,
                duration_ms=elapsed_ms,
                status=response.status_code,
                user_agent=request.headers.get("user-agent"),
            )
            logger.warning(
                "[slow-request] %s %s -> %d in %.0fms",
                request.method, path, response.status_code, elapsed_ms,
            )
        return response


__all__ = [
    "SLOW_REQUESTS", "SlowRequestLogMiddleware",
    "SLOW_THRESHOLD_MS", "RING_SIZE",
]
