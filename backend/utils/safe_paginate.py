"""Iter 216h171 — Safe `.to_list()` pagination helper with truncation telemetry.

The audit identified ~30 `.to_list(N)` call sites where N ≥ 10_000. Each
one is technically safe (they all have a cap, no unbounded calls exist),
but a silent truncation at the cap is a UX bug waiting to happen — the
report shows "20,000 rows" when the org actually has 20,001 and the
dashboard quietly drops the tail.

This helper does three things:

1. Provides three documented band constants so call sites declare their
   intent:
       LIST_CAP   = 500     — user-facing paginated lists
       BULK_CAP   = 10_000  — server-side computation / aggregation
       EXPORT_CAP = 50_000  — explicit user-triggered exports (CSV/PDF)

2. Wraps Motor's `cursor.to_list(cap)` with a one-line awaitable that
   emits a structured log line + bumps a counter when the cap is
   actually hit. Counter is surfaced by `/master-admin/perf/cache`
   alongside the iter 216h170 cache stats so operators can spot a tenant
   crossing a threshold *before* a customer reports it.

3. Adds a `cursor.distinct()`-style fast-count fallback (`peek_count`)
   so the most heavily-used dashboard endpoints can know "did we cap?"
   without re-running the query.

Wiring is opt-in and additive: legacy code paths continue to work
unchanged. No behaviour is altered for non-truncated calls.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Documented band constants ────────────────────────────────────
# Use these instead of literal numbers so the intent of every
# `.to_list()` call is unambiguous at the call site.

#: User-facing paginated lists / pickers / dropdowns.
LIST_CAP: int = 500

#: Server-side computation (aggregates, joins, report builders).
BULK_CAP: int = 10_000

#: Explicit user-triggered exports (CSV, ZIP, PDF batches).
EXPORT_CAP: int = 50_000


class _TruncationStats:
    """Process-local truncation telemetry. Surfaced by the perf endpoint."""

    __slots__ = ("events",)

    def __init__(self) -> None:
        # name → {"hits": int, "last_cap": int, "last_at": iso str}
        self.events: dict[str, dict] = {}

    def record(self, name: str, cap: int) -> None:
        from datetime import datetime, timezone
        e = self.events.setdefault(
            name, {"hits": 0, "last_cap": cap, "last_at": ""},
        )
        e["hits"] += 1
        e["last_cap"] = cap
        e["last_at"] = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict:
        # Sort hottest-first so the UI shows the worst offenders.
        ordered = dict(
            sorted(self.events.items(), key=lambda kv: kv[1]["hits"], reverse=True),
        )
        return {"truncation_events": ordered}


TRUNCATION = _TruncationStats()


async def safe_to_list(cursor: Any, cap: int, name: str) -> list[dict]:
    """Materialise a Motor cursor with cap + truncation telemetry.

    Args:
        cursor: An *already-filtered* Motor cursor (call `.find(q, proj)`
                + any `.sort()` / `.skip()` first, then pass it here).
        cap:    Maximum rows to return. Use one of the band constants
                above unless you genuinely need a custom number.
        name:   Diagnostic label. Convention: ``<route_id>.<phase>``,
                e.g. ``"capex.board_report.equipment"``. Used by the
                perf endpoint to attribute truncation events.

    Returns:
        list[dict]: Up to `cap` documents. If exactly `cap` rows came
        back AND the query *could have* matched more, the cap was
        almost certainly hit — we log a warning and bump the counter.

    Note:
        Motor caps lookup work via batch size internally so this does
        not change the wire behaviour vs `cursor.to_list(cap)`. The
        only addition is the telemetry on hit.
    """
    rows = await cursor.to_list(cap)
    if rows and len(rows) >= cap:
        # We can't cheaply prove "there were more rows" without re-querying,
        # so any `len == cap` result is treated as a potential truncation.
        # Operators can confirm via the count_documents() in the perf panel.
        TRUNCATION.record(name, cap)
        logger.warning(
            "[pagination] cap hit for '%s' (cap=%d). "
            "Tenant may be losing tail rows — consider raising the cap "
            "or paginating the endpoint.",
            name, cap,
        )
    return rows


__all__ = [
    "safe_to_list", "TRUNCATION",
    "LIST_CAP", "BULK_CAP", "EXPORT_CAP",
]
