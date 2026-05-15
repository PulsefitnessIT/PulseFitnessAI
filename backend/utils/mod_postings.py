"""Personnel rotation sweeper.

Iter 216h116 — auto-deactivates ``mod_site_staff`` records 14 days
after their ``posting_out_date``. Called from the proactive-nudges
cycle. Fail-soft — failures are logged but never raised.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

POSTING_GRACE_DAYS = 14


async def sweep_posting_outs() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=POSTING_GRACE_DAYS)).date()
    cursor = db.mod_site_staff.find(
        {
            "is_active": True,
            "posting_out_date": {"$lte": cutoff.isoformat()},
        },
        {"_id": 0, "id": 1, "site_id": 1, "name": 1, "posting_out_date": 1},
    )
    deactivated = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    async for staff in cursor:
        try:
            await db.mod_site_staff.update_one(
                {"id": staff["id"], "is_active": True},
                {"$set": {
                    "is_active": False,
                    "deactivated_at": now_iso,
                    "deactivation_reason": "posting_out_complete",
                    "updated_at": now_iso,
                }},
            )
            deactivated += 1
            try:
                from utils.mod_audit import audit_event
                await audit_event(
                    site_id=staff["site_id"],
                    action="staff.posting_out",
                    target_type="staff", target_id=staff["id"],
                    payload={
                        "auto_deactivated": True,
                        "posting_out_date": staff.get("posting_out_date"),
                    },
                )
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover
            logger.warning("[mod-postings] deactivate failed for %s: %s",
                           staff.get("id"), exc)
    if deactivated:
        logger.info("[mod-postings] auto-deactivated %s staff", deactivated)
    return {"deactivated": deactivated}
