"""MOD Acceptance-loop sweeper.

Iter 216h115 — every fault marked resolved triggers a confirmation
email to the original reporter. If the reporter does not act within
``ACCEPTANCE_GRACE_HOURS`` (default 48h) the fault auto-reopens with a
``reopened_reason="awaiting_reporter_review"`` flag so HQ + supplier
see it on their dashboard.

This module exposes a single coroutine ``sweep_pending_acceptances()``
that the existing proactive-nudges cycle (or a standalone cron) can
call. It is fail-soft — exceptions are logged but never raised.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

ACCEPTANCE_GRACE_HOURS = int(os.environ.get("MOD_ACCEPTANCE_GRACE_HOURS", "48"))


async def sweep_pending_acceptances() -> dict:
    """Find faults whose acceptance email has been outstanding past the
    grace window and auto-reopen them. Returns ``{scanned, reopened}``."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=ACCEPTANCE_GRACE_HOURS)
    ).isoformat()
    cursor = db.issues.find(
        {
            "acceptance_status": "pending",
            "acceptance_sent_at": {"$lte": cutoff},
            "status": "resolved",
        },
        {"_id": 0, "id": 1, "organization_id": 1, "mod_ticket_ref": 1},
    )
    scanned = 0
    reopened = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    async for issue in cursor:
        scanned += 1
        try:
            await db.issues.update_one(
                {"id": issue["id"], "acceptance_status": "pending"},
                {"$set": {
                    "status": "open",
                    "acceptance_status": "timed_out",
                    "reopened_at": now_iso,
                    "reopened_reason": "awaiting_reporter_review",
                }},
            )
            reopened += 1
            # Audit (fail-soft).
            try:
                from utils.mod_audit import audit_event
                await audit_event(
                    site_id=issue["organization_id"],
                    action="fault.reopen",
                    target_type="issue",
                    target_id=issue["id"],
                    payload={
                        "ticket_ref": issue.get("mod_ticket_ref"),
                        "reason": "acceptance_timeout",
                    },
                )
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover
            logger.warning("[mod-acceptance] reopen failed for %s: %s",
                           issue.get("id"), exc)
    if scanned:
        logger.info("[mod-acceptance] swept %s · reopened %s", scanned, reopened)
    return {"scanned": scanned, "reopened": reopened}
