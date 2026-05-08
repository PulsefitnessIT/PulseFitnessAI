"""
Weekly equipment image backfill cron — runs every Monday 03:00 UTC via the
main sicon_poller loop. Scans all organisations for equipment with no
uploaded photo, no auto-looked-up image, and a recognised manufacturer.
Calls the lookup pipeline per item, capped per-org so one gym with 2000
pieces of kit can't monopolise the slot.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from utils.database import db
from utils.equipment_image_lookup import (
    get_manufacturer_domain,
    lookup_equipment_image,
)

logger = logging.getLogger(__name__)

PER_ORG_CAP = 50       # don't spend >50 lookups on one org per weekly run
GLOBAL_CAP = 300       # ceiling across all orgs per run (rate-limit guardrail)
RUN_WEEKDAY = 0        # Monday (Python weekday() convention)
RUN_HOUR_UTC = 3       # 03:00 UTC

_LAST_RUN: dict = {"date": None}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def run_equipment_image_backfill() -> dict:
    """Execute one weekly backfill sweep across all orgs.

    Idempotent per UTC date — safe to call on every poll cycle."""
    now = _now()
    today = now.date().isoformat()
    # Only run once per day, on Monday, after 03:00 UTC.
    if _LAST_RUN.get("date") == today:
        return {"skipped": "already_ran_today"}
    if now.weekday() != RUN_WEEKDAY or now.hour < RUN_HOUR_UTC:
        return {"skipped": "not_window"}

    _LAST_RUN["date"] = today

    logger.info("[equipment-image-backfill] weekly sweep starting")
    processed_global = 0
    orgs_touched = 0
    matched_global = 0

    cursor = db.organizations.find(
        {"is_test": {"$ne": True}, "account_type": {"$ne": "member"}},
        {"_id": 0, "id": 1, "name": 1},
    )
    async for org in cursor:
        if processed_global >= GLOBAL_CAP:
            break
        org_id = org["id"]
        eq_cursor = db.equipment.find({
            "organization_id": org_id,
            "photo_url": {"$in": [None, ""]},
            "auto_image_url": {"$in": [None, ""]},
        }, {"_id": 0}).limit(PER_ORG_CAP)
        items = await eq_cursor.to_list(PER_ORG_CAP)
        if not items:
            continue
        orgs_touched += 1
        per_org_matched = 0
        for eq in items:
            if processed_global >= GLOBAL_CAP:
                break
            processed_global += 1
            manufacturer = eq.get("manufacturer") or eq.get("supplier") or ""
            if not get_manufacturer_domain(manufacturer):
                continue
            try:
                result = await lookup_equipment_image(
                    manufacturer=manufacturer,
                    name=eq.get("name"),
                    equipment_type=eq.get("equipment_type"),
                    verify=True,
                )
                if result and result.get("image_url"):
                    await db.equipment.update_one(
                        {"id": eq["id"]},
                        {"$set": {
                            "auto_image_url": result["image_url"],
                            "auto_image_source_url": result.get("source_url"),
                            "auto_image_verified": bool(result.get("verified")),
                            "auto_image_looked_up_at": _now_iso(),
                            "photo_source": "auto" if not eq.get("photo_url") else eq.get("photo_source"),
                        }},
                    )
                    matched_global += 1
                    per_org_matched += 1
            except Exception as exc:
                logger.info("[equipment-image-backfill] lookup failed for %s: %s", eq.get("id"), exc)

        if per_org_matched:
            logger.info(
                "[equipment-image-backfill] org=%s matched=%d/%d",
                org.get("name") or org_id,
                per_org_matched,
                len(items),
            )

    summary = {
        "orgs_touched": orgs_touched,
        "processed": processed_global,
        "matched": matched_global,
        "at": _now_iso(),
    }
    # Record run for audit / observability
    await db.equipment_image_backfill_runs.insert_one({**summary, "date": today})
    logger.info("[equipment-image-backfill] weekly sweep complete %s", summary)
    return summary
