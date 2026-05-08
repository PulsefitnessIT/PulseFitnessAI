"""
Sicon outbox worker (Phase 8 A · iter 215dz).

Drains `svc_sicon_outbox` rows by calling the live Sicon WebAPI via the
existing `utils.sicon_client.SiconClient` (per organization config).

State machine:

  pending → in_flight → succeeded
                    → failed (retry < 5)
                    → dead_letter (retry == 5)

  pending → simulated → simulated_succeeded   (dry-run "demo" mode only)

The worker is **demand-driven** today (run via the admin endpoints
`/api/integrations/admin/sicon/drain-now` and
`/api/integrations/admin/sicon/simulate-drain`). When we have credentials
we'll swap to a 30s background task in `server.py`. The interface is
already shaped that way (`tick()` returns a `DrainResult` so the loop
can pace itself / report stats).

Endpoint mapping (must match the `endpoint` field on outbox rows, which
in turn matches the `_to_sicon_*` payload builders in
`routes/svc/integrations/sicon_sync.py`):

  /api/Service/Calls           → SiconClient.create_case      (kind="case")
  /api/Service/TrackingNotes   → SiconClient.create_tracking_note (kind="tracking_note")
  /api/Service/Appointments    → SiconClient.create_appointment   (kind="appointment")
  /api/Service/Signatures      → SiconClient.create_tracking_note (kind="signature" — Sicon uses a tracking note for signatures)
  /api/Service/Attachments     → SiconClient.create_tracking_note (kind="attachment" — same fallback)
  /api/Service/StockMovements  → SiconClient.create_tracking_note (kind="part_movement" — same fallback until Sicon exposes a dedicated endpoint)

The fallback to `create_tracking_note` for kinds Sicon doesn't yet model
in their public API means *every* outbound write is recorded against the
service call as a structured note, which is exactly what Pulse asked for
during the last requirements pass.

The "simulate" mode bypasses HTTP entirely — it's the demo screen for
the customer before real credentials change hands.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from utils.database import db
from utils.sicon_client import SiconAPIError, SiconClient
from utils.sicon_common import get_sicon_client, log_sicon_event

logger = logging.getLogger(__name__)

OUTBOX = "svc_sicon_outbox"
MAX_RETRIES = 5
BATCH_SIZE = 25


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
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)

    def bump(self, kind: str, status: str) -> None:
        d = self.by_kind.setdefault(kind, {"succeeded": 0, "failed": 0, "dead_letter": 0, "simulated": 0})
        d[status] = d.get(status, 0) + 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_to_sicon(client: SiconClient, kind: str, payload: dict) -> dict:
    """Dispatch the payload to the right SiconClient method based on `kind`."""
    if kind == "case":
        # Sicon's API has both create + amend; we lean on amend's idempotent
        # "create-or-update by reference" behaviour.
        return await client.amend_case(payload)
    if kind == "tracking_note":
        case_ref = payload.get("ServiceCallReference") or ""
        # We need the numeric Sicon case id, not the GymAxis reference.
        # The amend_case response on the case push records this — we look it up.
        sicon_case_id = await _resolve_sicon_case_id(client, case_ref)
        return await client.create_tracking_note(sicon_case_id, payload)
    if kind == "appointment":
        return await client.create_appointment(payload)
    if kind in {"signature", "attachment", "part_movement"}:
        # Sicon doesn't expose dedicated endpoints for these yet — record
        # them as a structured tracking note so the audit trail is intact.
        case_ref = payload.get("ServiceCallReference") or ""
        sicon_case_id = await _resolve_sicon_case_id(client, case_ref)
        return await client.create_tracking_note(sicon_case_id, {
            "NoteTypeID": kind,  # use the kind tag as a structured note type
            "NoteText": _structured_note_body(kind, payload),
            "VisibleToEngineer": True,
            "VisibleToCustomer": False,
            "CreatedAt": payload.get("CreatedAt") or payload.get("MovedAt") or _now_iso(),
            "Metadata": payload,
        })
    raise SiconAPIError(f"Unknown outbox kind: {kind!r}", http_status=0)


def _structured_note_body(kind: str, payload: dict) -> str:
    if kind == "signature":
        return (
            f"Sign-off received from {payload.get('CustomerName','?')} "
            f"({payload.get('CustomerRole','?')}) at {payload.get('SignedAt','?')}. "
            f"Work done: {payload.get('WorkDoneSummary','')}"
        )
    if kind == "attachment":
        return f"Attachment uploaded: {payload.get('Description','(no caption)')} ({payload.get('FileURL','')})"
    if kind == "part_movement":
        return (
            f"Stock movement {payload.get('MovementTypeID')}: "
            f"{payload.get('Quantity',0)} × {payload.get('PartCode','?')} "
            f"({payload.get('FromLocation','?')} → {payload.get('ToLocation','?')})"
        )
    return f"{kind}: {payload}"


async def _resolve_sicon_case_id(client: SiconClient, case_reference: str) -> int:
    """GymAxis stores the GymAxis-generated reference; Sicon expects its own
    numeric case id. We resolve via lookup.
    """
    if not case_reference:
        raise SiconAPIError("No case reference on payload — cannot route to Sicon", http_status=0)
    try:
        case = await client.get_case_by_reference(case_reference)
        sicon_id = case.get("ServiceCallID") or case.get("CallID") or case.get("Id")
        if sicon_id:
            return int(sicon_id)
    except SiconAPIError as e:
        if e.http_status not in (404, 0):
            raise
    raise SiconAPIError(f"Sicon could not resolve case reference {case_reference!r}", http_status=404)


async def _process_row(row: dict, *, simulate: bool) -> tuple[str, Optional[str]]:
    """Process a single outbox row. Returns (final_status, error_or_none)."""
    kind = row.get("kind") or "unknown"
    org_id = row.get("organization_id")
    if simulate:
        return "simulated_succeeded", None
    if not org_id:
        return "failed", "missing organization_id"
    client = await get_sicon_client(org_id)
    if client is None:
        return "skipped_no_config", "Sicon not configured for organization"
    try:
        await _send_to_sicon(client, kind, row.get("payload") or {})
        return "succeeded", None
    except SiconAPIError as e:
        logger.warning("sicon worker: kind=%s ref=%s api error: %s", kind, row.get("our_reference"), e)
        return "failed", str(e)
    except Exception as e:
        logger.exception("sicon worker: kind=%s ref=%s unexpected error", kind, row.get("our_reference"))
        return "failed", f"{type(e).__name__}: {e}"


async def tick(*, organization_id: Optional[str] = None,
                 simulate: bool = False,
                 max_rows: int = BATCH_SIZE) -> DrainResult:
    """One drain pass over the outbox.

    If `simulate=True`, every pending row is moved to `simulated_succeeded`
    without any HTTP call (demo / dry-run "watch the rows transition" mode).

    If `organization_id` is given, only that org's rows are drained.
    """
    started = _now_iso()
    result = DrainResult(started_at=started, finished_at=started, simulated=simulate)

    q: dict[str, Any] = {"status": "pending"}
    if organization_id:
        q["organization_id"] = organization_id

    cursor = db[OUTBOX].find(q, projection={"_id": 0}).sort("created_at", 1).limit(max_rows)
    rows = [r async for r in cursor]
    if not rows:
        result.finished_at = _now_iso()
        return result

    seen_orgs: set[str] = set()

    for row in rows:
        result.attempted += 1
        kind = row.get("kind") or "unknown"
        if row.get("organization_id"):
            seen_orgs.add(row["organization_id"])

        # Move to in_flight (or simulated) so concurrent workers skip it.
        target_in_flight = "simulated" if simulate else "in_flight"
        upd = await db[OUTBOX].update_one(
            {"id": row["id"], "status": "pending"},
            {"$set": {"status": target_in_flight, "updated_at": _now_iso()},
             "$inc": {"attempts": 1}},
        )
        if upd.modified_count == 0:
            continue  # someone else grabbed it

        final_status, error = await _process_row(row, simulate=simulate)

        if final_status == "succeeded" or final_status == "simulated_succeeded":
            result.succeeded += 1
            result.bump(kind, "simulated" if simulate else "succeeded")
            await db[OUTBOX].update_one(
                {"id": row["id"]},
                {"$set": {
                    "status": final_status,
                    "updated_at": _now_iso(),
                    "error": None,
                }},
            )
            if not simulate:
                await log_sicon_event(
                    organization_id=row.get("organization_id") or "",
                    action=f"outbox/{kind}",
                    details=f"ref={row.get('our_reference')} succeeded",
                    success=True,
                    user_id="worker",
                )
        elif final_status == "skipped_no_config":
            result.skipped_no_config += 1
            await db[OUTBOX].update_one(
                {"id": row["id"]},
                {"$set": {"status": "pending", "updated_at": _now_iso(),
                          "error": "no Sicon config for org"}},
            )
        else:
            attempts = (row.get("attempts") or 0) + 1
            target = "dead_letter" if attempts >= MAX_RETRIES else "failed"
            if target == "dead_letter":
                result.dead_letter += 1
                result.bump(kind, "dead_letter")
            else:
                result.failed += 1
                result.bump(kind, "failed")
            await db[OUTBOX].update_one(
                {"id": row["id"]},
                {"$set": {"status": target, "updated_at": _now_iso(),
                          "error": (error or "")[:1000]}},
            )

    result.organizations = len(seen_orgs)
    result.finished_at = _now_iso()
    return result


async def requeue_failed(*, organization_id: Optional[str] = None,
                          include_dead_letter: bool = False) -> int:
    """Move `failed` (and optionally `dead_letter`) rows back to `pending`.

    Used by the admin "retry now" button.
    """
    q: dict[str, Any] = {"status": {"$in": ["failed"] + (["dead_letter"] if include_dead_letter else [])}}
    if organization_id:
        q["organization_id"] = organization_id
    upd = await db[OUTBOX].update_many(
        q,
        {"$set": {"status": "pending", "updated_at": _now_iso()},
         "$unset": {"error": ""}},
    )
    return upd.modified_count


async def run_loop(*, interval_seconds: float = 30.0,
                       organization_id: Optional[str] = None,
                       simulate: bool = False) -> None:
    """Background loop. Used by `server.py` once auto-start is enabled.

    Currently demand-driven only (admin endpoints) — this is reserved for
    when SICON_AUTOSTART_WORKER=true is added to the env.
    """
    logger.info("sicon outbox worker loop starting (interval=%ss simulate=%s)", interval_seconds, simulate)
    while True:
        try:
            await tick(organization_id=organization_id, simulate=simulate)
        except Exception:
            logger.exception("sicon worker loop tick failed")
        await asyncio.sleep(interval_seconds)


__all__ = ["tick", "requeue_failed", "run_loop", "DrainResult"]
