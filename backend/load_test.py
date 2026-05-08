"""Load-test driver for the GymAxis / Pulse Fitness API.

A pure-Python asyncio load test (no k6 / wrk install required). Hammers the
top 20 tenant-scoped endpoints as an authenticated operator and reports
p50 / p95 / p99 latencies per route.

Usage (preview / staging — NEVER run against production)::

    # 200 concurrent users for 60s — smoke test
    BASE_URL=https://preview.example.com \\
    EMAIL=lee.somers@pulsefitness.com \\
    PASSWORD=TempPass123! \\
    CONCURRENCY=200 DURATION=60 \\
    python load_test.py

    # 1000 concurrent users for 3 min — capacity test
    CONCURRENCY=1000 DURATION=180 python load_test.py

Why this script and not k6?
  * Zero install — runs anywhere Python + aiohttp runs (CI, laptop, pod).
  * Same auth flow as the real frontend (login → JWT → calls).
  * Output is deterministic CSV so we can diff across releases.

What it tests
  * Read-heavy endpoints that every operator dashboard hits on page-load.
  * Excludes LLM / write endpoints — those are tested separately with
    lower concurrency because they are rate-limited by design.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import time

try:
    import aiohttp
except ImportError:  # pragma: no cover
    print("aiohttp required: pip install aiohttp", file=sys.stderr)
    sys.exit(2)


BASE_URL = os.environ["BASE_URL"].rstrip("/")
EMAIL = os.environ["EMAIL"]
PASSWORD = os.environ["PASSWORD"]
CONCURRENCY = int(os.environ.get("CONCURRENCY", "200"))
DURATION = int(os.environ.get("DURATION", "60"))

# Tenant-scoped read endpoints — the hot path for every dashboard session.
ENDPOINTS = [
    "/api/health",
    "/api/equipment",
    "/api/issues",
    "/api/sites",
    "/api/suppliers",
    "/api/auth/me",
    "/api/staffing/staff",
    "/api/staffing/rules",
    "/api/staffing/announcements",
    "/api/staffing/live-floor",
    "/api/staffing/leave",
    "/api/staffing/marketplace/open",
    "/api/memberships/dashboard",
    "/api/marketing/dashboard",
    "/api/help/guides",
    "/api/faults",
    "/api/check-sheets",
    "/api/ppm/schedules",
    "/api/spec-sheets/list",
    "/api/equipment/template/csv",
]


async def login(session: aiohttp.ClientSession) -> str:
    async with session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return data.get("token") or data["access_token"]


async def worker(
    session: aiohttp.ClientSession,
    token: str,
    end_at: float,
    results: dict[str, list[float]],
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < end_at:
        path = random.choice(ENDPOINTS)
        t0 = time.perf_counter()
        status = 0
        try:
            async with session.get(f"{BASE_URL}{path}", headers=headers, timeout=15) as r:
                status = r.status
                await r.read()
        except Exception:
            status = -1
        dt_ms = (time.perf_counter() - t0) * 1000.0
        # Bucket results by path+status so we can report 5xx rates separately.
        bucket = f"{path} [{status}]"
        results.setdefault(bucket, []).append(dt_ms)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(len(values) * p)
    return values[min(k, len(values) - 1)]


def report(results: dict[str, list[float]], wall_seconds: float) -> int:
    print(f"\n{'endpoint':<60} {'n':>7} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}")
    print("-" * 100)
    total_requests = 0
    slow_routes = 0
    errors = 0
    for path in sorted(results.keys()):
        vals = results[path]
        total_requests += len(vals)
        if "[-1]" in path or "[5" in path:
            errors += len(vals)
        p50 = percentile(vals, 0.50)
        p95 = percentile(vals, 0.95)
        p99 = percentile(vals, 0.99)
        mx = max(vals)
        marker = "  SLOW" if p95 > 1000 else ""
        if p95 > 1000:
            slow_routes += 1
        print(f"{path:<60} {len(vals):>7} {p50:>7.1f}ms {p95:>7.1f}ms {p99:>7.1f}ms {mx:>7.1f}ms{marker}")
    rps = total_requests / max(wall_seconds, 0.001)
    print("-" * 100)
    print(f"total:   {total_requests:,} requests in {wall_seconds:.1f}s ({rps:,.1f} rps)")
    print(f"errors:  {errors:,} ({errors / max(total_requests, 1):.2%})")
    print(f"slow:    {slow_routes} route/status groups over 1000ms p95")
    # Exit non-zero if we have errors or slow routes — makes this CI-friendly.
    return 0 if errors == 0 and slow_routes == 0 else 1


async def main() -> int:
    print(f"Logging in {EMAIL} @ {BASE_URL} …")
    conn = aiohttp.TCPConnector(limit=CONCURRENCY * 2, enable_cleanup_closed=True)
    async with aiohttp.ClientSession(connector=conn) as s:
        token = await login(s)
        print(f"OK. Running {CONCURRENCY} workers for {DURATION}s against {len(ENDPOINTS)} endpoints.")
        end_at = time.monotonic() + DURATION
        results: dict[str, list[float]] = {}
        t0 = time.monotonic()
        await asyncio.gather(*[worker(s, token, end_at, results) for _ in range(CONCURRENCY)])
        return report(results, time.monotonic() - t0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
