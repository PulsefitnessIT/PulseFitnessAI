"""Phase 2 Sicon write-back facade — the single, documented entry point for
"reporting into Sicon".

Design (deliberately NOT a parallel path):
- Enqueue is delegated to the proven, idempotent outbox helpers in
  routes/svc/integrations/sicon_sync (push_case / push_event / ...). Those write
  intents to `svc_sicon_outbox`.
- Nothing is SENT here. The outbox worker (utils/sicon_outbox_worker) drains the
  queue, and every actual HTTP write is centrally gated by SICON_ALLOW_WRITES
  (SiconClient._guard_write) AND by the worker's write-gate. While the flag is
  false, intents sit safely as 'pending'.
- So `report_*` is always safe to call from anywhere in the app; it captures the
  intent to report into Sicon without any risk of a live write during Phase 1.

Imports of the enqueue helpers are lazy to avoid any import-time coupling
between utils/* and routes/*.
"""
from __future__ import annotations

from typing import Any, Dict

from utils.database import db
from utils.sicon_common import env_allow_writes

OUTBOX = "svc_sicon_outbox"


def writeback_enabled() -> bool:
    """True only when live Sicon writes are turned on (SICON_ALLOW_WRITES)."""
    return env_allow_writes()


def _sync():
    # Lazy import — keeps utils import-safe regardless of route load order.
    from routes.svc.integrations import sicon_sync
    return sicon_sync


async def report_case(case: Dict[str, Any]) -> None:
    await _sync().push_case(case)


async def report_event(event: Dict[str, Any], *, case_reference: str = "") -> None:
    await _sync().push_event(event, case_reference=case_reference)


async def report_time_entry(entry: Dict[str, Any], *, case_reference: str = "") -> None:
    await _sync().push_time_entry(entry, case_reference=case_reference)


async def report_signature(sig: Dict[str, Any], *, case_reference: str = "") -> None:
    await _sync().push_signature(sig, case_reference=case_reference)


async def report_attachment(photo: Dict[str, Any], *, case_reference: str = "") -> None:
    await _sync().push_attachment(photo, case_reference=case_reference)


async def report_part_movement(movement: Dict[str, Any], *, case_reference: str = "") -> None:
    await _sync().push_part_movement(movement, case_reference=case_reference)


async def outbox_summary(organization_id: str) -> Dict[str, Any]:
    """Observability: outbox row counts by status for an org, plus the flag."""
    pipeline = [
        {"$match": {"organization_id": organization_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    counts: Dict[str, int] = {}
    async for r in db[OUTBOX].aggregate(pipeline):
        counts[r["_id"]] = r["n"]
    return {
        "enabled": env_allow_writes(),
        "pending": counts.get("pending", 0),
        "in_flight": counts.get("in_flight", 0),
        "succeeded": counts.get("succeeded", 0),
        "failed": counts.get("failed", 0),
        "dead_letter": counts.get("dead_letter", 0),
        "simulated_succeeded": counts.get("simulated_succeeded", 0),
        "total": sum(counts.values()),
    }
