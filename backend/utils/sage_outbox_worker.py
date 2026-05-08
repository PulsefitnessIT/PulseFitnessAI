"""
Sage 200 outbox worker (Phase 8 B · iter 215ea).

Drains:
  * `svc_sage_invoice_outbox`  (rows with status="ready")  → POST /sales-invoices
  * `svc_sage_po_outbox`       (rows with status="pending") → POST /purchase-orders

State machine:

  invoice:  pending → ready → in_flight → posted
                                       → failed (retry < 5) → dead_letter
  po:       pending          → in_flight → posted
                                       → failed (retry < 5) → dead_letter

  + simulate path: ready/pending → simulated → simulated_succeeded

Demand-driven via three admin endpoints in routes/svc/integrations/health.py:

  POST /api/integrations/admin/sage/drain-now
  POST /api/integrations/admin/sage/simulate-drain
  POST /api/integrations/admin/sage/requeue-failed

Mirrors `utils/sicon_outbox_worker.py` 1:1; the only differences are the
state names (Sage uses `ready`/`posted` not `pending`/`succeeded` for the
invoice flow) and the per-kind dispatch. When credentials arrive
(SAGE_CLIENT_ID / SECRET / SITE_ID / COMPANY_ID via the per-org config UI
in CRM Settings → Sage 200), no code changes are needed.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from utils.database import db
from utils.sage_client import SageAPIError, post_payload, get_sage_config, _is_live_config  # type: ignore

logger = logging.getLogger(__name__)

INVOICE_OUTBOX = "svc_sage_invoice_outbox"
PO_OUTBOX = "svc_sage_po_outbox"
QUOTE_OUTBOX = "svc_sage_quote_outbox"
MAX_RETRIES = 5
BATCH_SIZE = 25

# Per-outbox: which row statuses are eligible for live drain, and the
# kind name that determines which Sage endpoint we POST to.
_DRAIN_PROFILE: dict[str, dict[str, Any]] = {
    INVOICE_OUTBOX: {"eligible": ["ready"],     "kind": "invoice", "success": "posted"},
    PO_OUTBOX:      {"eligible": ["pending"],   "kind": "po",      "success": "posted"},
    QUOTE_OUTBOX:   {"eligible": ["pending"],   "kind": "quote",   "success": "posted"},
}


@dataclass
class DrainResult:
    started_at: str
    finished_at: str
    organizations: int = 0
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    dead_letter: int = 0
    skipped_no_config: int = 0
    simulated: bool = False
    by_outbox: dict[str, dict[str, int]] = field(default_factory=dict)
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, outbox: str, kind: str, status: str) -> None:
        ob = self.by_outbox.setdefault(outbox, {"succeeded": 0, "failed": 0, "dead_letter": 0, "simulated": 0, "skipped_no_config": 0})
        ob[status] = ob.get(status, 0) + 1
        kd = self.by_kind.setdefault(kind, {"succeeded": 0, "failed": 0, "dead_letter": 0, "simulated": 0, "skipped_no_config": 0})
        kd[status] = kd.get(status, 0) + 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _process_row(coll_name: str, row: dict, *, simulate: bool) -> tuple[str, Optional[str]]:
    """Return (final_status, error_or_None). Status is one of:
      simulated_succeeded · posted · failed · skipped_no_config
    """
    profile = _DRAIN_PROFILE[coll_name]
    kind = profile["kind"]
    if simulate:
        return "simulated_succeeded", None
    org_id = row.get("organization_id")
    if not org_id:
        return "failed", "missing organization_id"
    cfg = await get_sage_config(organization_id=org_id)
    if not _is_live_config(cfg):
        return "skipped_no_config", "Sage 200 not configured for organization"
    try:
        await post_payload(kind=kind, payload=row.get("payload") or {}, organization_id=org_id)
        return "posted", None
    except SageAPIError as e:
        logger.warning("sage worker: kind=%s ref=%s api error: %s", kind, row.get("our_reference") or row.get("case_reference") or row.get("po_reference"), e)
        return "failed", str(e)
    except Exception as e:
        logger.exception("sage worker: kind=%s unexpected error", kind)
        return "failed", f"{type(e).__name__}: {e}"


async def _drain_collection(coll_name: str, *, simulate: bool, max_rows: int,
                              organization_id: Optional[str], result: DrainResult) -> int:
    profile = _DRAIN_PROFILE[coll_name]
    kind = profile["kind"]
    in_flight_status = "simulated" if simulate else "in_flight"
    final_success_status = "simulated_succeeded" if simulate else profile["success"]

    q: dict[str, Any] = {"status": {"$in": profile["eligible"]}}
    if organization_id:
        q["organization_id"] = organization_id

    cursor = db[coll_name].find(q, projection={"_id": 0}).sort("created_at", 1).limit(max_rows)
    rows = [r async for r in cursor]
    seen_orgs: set[str] = set()

    for row in rows:
        result.attempted += 1
        if row.get("organization_id"):
            seen_orgs.add(row["organization_id"])

        # Lock the row by transitioning to in_flight / simulated.
        upd = await db[coll_name].update_one(
            {"id": row["id"], "status": {"$in": profile["eligible"]}},
            {"$set": {"status": in_flight_status, "updated_at": _now_iso()},
             "$inc": {"attempts": 1}},
        )
        if upd.modified_count == 0:
            continue  # raced with another worker

        final_status, error = await _process_row(coll_name, row, simulate=simulate)

        if final_status in ("posted", "simulated_succeeded"):
            result.succeeded += 1
            result.bump(coll_name, kind, "simulated" if simulate else "succeeded")
            await db[coll_name].update_one(
                {"id": row["id"]},
                {"$set": {"status": final_success_status, "updated_at": _now_iso(), "error": None}},
            )
        elif final_status == "skipped_no_config":
            result.skipped_no_config += 1
            result.bump(coll_name, kind, "skipped_no_config")
            # Restore row to its original eligible state so the next drain re-picks it up.
            await db[coll_name].update_one(
                {"id": row["id"]},
                {"$set": {"status": profile["eligible"][0], "updated_at": _now_iso(),
                          "error": "no Sage config for org"}},
            )
        else:
            attempts = (row.get("attempts") or 0) + 1
            target = "dead_letter" if attempts >= MAX_RETRIES else "failed"
            if target == "dead_letter":
                result.dead_letter += 1
                result.bump(coll_name, kind, "dead_letter")
            else:
                result.failed += 1
                result.bump(coll_name, kind, "failed")
            await db[coll_name].update_one(
                {"id": row["id"]},
                {"$set": {"status": target, "updated_at": _now_iso(),
                          "error": (error or "")[:1000]}},
            )

    return len(seen_orgs)


async def tick(*, organization_id: Optional[str] = None,
                 simulate: bool = False,
                 max_rows: int = BATCH_SIZE) -> DrainResult:
    """One drain pass over all three Sage outboxes (invoice + po + quote)."""
    started = _now_iso()
    result = DrainResult(started_at=started, finished_at=started, simulated=simulate)
    seen_orgs: set[str] = set()
    outbox_names = (INVOICE_OUTBOX, PO_OUTBOX, QUOTE_OUTBOX)
    # Spread max_rows across the outboxes so none starves.
    per_box = max(1, max_rows // len(outbox_names))
    for coll_name in outbox_names:
        n_orgs_before = len(seen_orgs)
        n_orgs = await _drain_collection(
            coll_name, simulate=simulate, max_rows=per_box,
            organization_id=organization_id, result=result,
        )
        if n_orgs > 0:
            seen_orgs.add(f"{coll_name}#{n_orgs}-{n_orgs_before}")
    result.organizations = max(1, len(seen_orgs)) if result.attempted else 0
    result.finished_at = _now_iso()
    return result


async def requeue_failed(*, organization_id: Optional[str] = None,
                          include_dead_letter: bool = False) -> int:
    """Move `failed` (and optionally `dead_letter`) rows back to their eligible state."""
    total = 0
    statuses = ["failed"] + (["dead_letter"] if include_dead_letter else [])
    for coll_name, profile in _DRAIN_PROFILE.items():
        target_status = profile["eligible"][0]
        q: dict[str, Any] = {"status": {"$in": statuses}}
        if organization_id:
            q["organization_id"] = organization_id
        upd = await db[coll_name].update_many(
            q,
            {"$set": {"status": target_status, "updated_at": _now_iso()},
             "$unset": {"error": ""}},
        )
        total += upd.modified_count
    return total


async def run_loop(*, interval_seconds: float = 60.0,
                       organization_id: Optional[str] = None,
                       simulate: bool = False) -> None:
    """Reserved for supervisor-driven 60s background loop once
    SAGE_AUTOSTART_WORKER=true is added to the env."""
    logger.info("sage outbox worker loop starting (interval=%ss simulate=%s)", interval_seconds, simulate)
    while True:
        try:
            await tick(organization_id=organization_id, simulate=simulate)
        except Exception:
            logger.exception("sage worker loop tick failed")
        await asyncio.sleep(interval_seconds)


__all__ = ["tick", "requeue_failed", "run_loop", "DrainResult"]
