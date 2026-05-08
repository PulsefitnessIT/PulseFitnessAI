"""
PPM Auto-Generator
==================
Bridges the standalone PPM scheduling engine (``ppm_engine.py``) with the
Service Desk so every PPM task that's coming due automatically lands in
the engineers' worklist as a ``svc_cases`` document with
``case_type="ppm"``. Idempotent — each PPM task carries a one-shot
``svc_case_id`` once it's been linked.

Runs as part of the existing ``sicon_poller`` cron tick (5-min cadence).
The lookahead window (``LOOKAHEAD_DAYS``) determines how far in advance a
PPM task spawns its service case so engineers can plan parts/travel.

Iter 216u (Phase 2).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

LOOKAHEAD_DAYS = 14


def _next_reference_for(org_id: str, count: int) -> str:
    return f"SVC-{count + 1:05d}"


async def run_ppm_autogen_cycle() -> dict:
    """For every PPM task scheduled to occur within the next
    ``LOOKAHEAD_DAYS`` and not yet linked to a service case, create a
    ``svc_cases`` doc and link it back via ``ppm_tasks.svc_case_id``.

    Returns a stats dict so the caller can log/observe runs.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=LOOKAHEAD_DAYS)
    horizon_iso = horizon.isoformat()

    cursor = db.ppm_tasks.find({
        "due_date": {"$lte": horizon_iso},
        "status": {"$in": ["scheduled", "overdue", None]},
        "$or": [{"svc_case_id": {"$exists": False}}, {"svc_case_id": None}, {"svc_case_id": ""}],
    }, {"_id": 0})

    spawned = 0
    skipped_no_org = 0
    errors = 0
    async for task in cursor:
        org_id = task.get("organization_id")
        if not org_id:
            skipped_no_org += 1
            continue
        try:
            schedule = None
            if task.get("schedule_id"):
                schedule = await db.ppm_schedules.find_one(
                    {"id": task["schedule_id"]}, {"_id": 0},
                )
            schedule = schedule or {}

            ref_count = await db.svc_cases.count_documents({"organization_id": org_id})
            new_case_id = str(uuid.uuid4())
            reference = _next_reference_for(org_id, ref_count)
            site_id = task.get("site_id") or schedule.get("site_id") or ""
            asset_name = task.get("asset_name") or schedule.get("asset_name") or schedule.get("equipment_name") or ""
            title = task.get("title") or schedule.get("name") or "Scheduled PPM visit"

            new_case = {
                "id": new_case_id,
                "organization_id": org_id,
                "reference": reference,
                "status": "new",
                "priority": "p3",
                "case_type": "ppm",
                "cover_type": (schedule.get("cover_type") or "contract"),
                "title": title,
                "description": (
                    f"Auto-generated PPM visit for schedule "
                    f"'{schedule.get('name', '')}'. Frequency: "
                    f"{schedule.get('frequency', 'manual')}. Due {task.get('due_date', '')[:10]}."
                ).strip(),
                "fault_code": "PPM",
                "fault_category": "preventive",
                "asset_id": task.get("asset_id") or schedule.get("asset_id") or "",
                "asset_name": asset_name,
                "equipment_ids": (
                    [task.get("equipment_id")] if task.get("equipment_id")
                    else schedule.get("equipment_ids", [])
                ),
                "equipment_serials": [],
                "allocated_parts": [],
                "site_id": site_id,
                "site_name": task.get("site_name") or schedule.get("site_name") or "",
                "site_postcode": schedule.get("site_postcode") or "",
                "customer_name": schedule.get("contact_name") or "",
                "customer_email": schedule.get("contact_email") or "",
                "customer_phone": schedule.get("contact_phone") or "",
                "contract_id": schedule.get("contract_id") or "",
                "ppm_task_id": task.get("id"),
                "ppm_schedule_id": task.get("schedule_id") or "",
                "due_at": task.get("due_date"),
                "estimated_minutes": int(schedule.get("estimated_duration_minutes", 60)),
                "assigned_engineer_id": "",
                "assigned_engineer_name": "",
                "recommended_engineer_id": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "timeline": [{
                    "id": str(uuid.uuid4()),
                    "type": "ppm_autogen",
                    "actor": "system",
                    "at": now.isoformat(),
                    "body": f"Service case auto-spawned from PPM task {task.get('id', '')[:8]}.",
                }],
            }
            await db.svc_cases.insert_one(new_case)
            await db.ppm_tasks.update_one(
                {"id": task["id"]},
                {"$set": {"svc_case_id": new_case_id, "svc_case_reference": reference}},
            )
            spawned += 1
        except Exception:
            logger.exception("[ppm-autogen] failed to spawn case for task %s", task.get("id"))
            errors += 1

    if spawned or errors:
        logger.info(
            "[ppm-autogen] cycle complete spawned=%s skipped_no_org=%s errors=%s",
            spawned, skipped_no_org, errors,
        )
    return {"spawned": spawned, "skipped_no_org": skipped_no_org, "errors": errors}
