"""Iter 220ea·26c (G2 follow-up) — PPM recurrence rollover.

G2 seeds the *first* preventive-maintenance visit when a contract
activates. This worker makes the cadence self-driving: once a visit is
completed (or cancelled), it auto-creates the *next* visit on the books,
``interval_days`` later, until the contract's ``end_date``.

Self-healing by design — a periodic sweep (not just an event hook) so it
also catches visits completed while the app was down, and never
double-creates (one open visit per schedule at a time).

  ``roll_ppm_schedules_once(organization_id=None)`` → {created, advanced,
    completed_schedules, skipped}. Scans active ``svc_ppm_schedules``:
      • latest visit still open      → skip (a visit is already pending)
      • latest visit closed/cancelled→ create the next at due+interval
      • next due beyond end_date      → deactivate the schedule
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

# A visit is "done" (roll forward) when closed/invoiced, or cancelled
# (so a skipped visit doesn't stall the whole schedule).
DONE_STATUSES = {"closed", "invoiced"}
ROLL_TRIGGERS = DONE_STATUSES | {"cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


async def _create_next_visit(sch: dict, due: datetime) -> str | None:
    """Create the next PPM case for a schedule via the canonical intake
    creator, then stamp the schedule link + due date onto it."""
    from routes.svc.intake import _create_case
    org = sch["organization_id"]
    name = sch.get("customer_name") or ""
    visits = int(sch.get("visits_per_year") or 0)
    user = {"id": "system", "organization_id": org, "full_name": "PPM scheduler"}
    payload = {
        "title": f"PPM visit — {name}".strip(" —"),
        "description": (
            f"Recurring preventive maintenance visit "
            f"({visits}/year) under the maintenance contract."),
        "priority": "p3",
        "cover_type": "contract",
        "case_type": "ppm",
        "customer_name": name,
        "customer_email": sch.get("customer_email") or "",
        "site_postcode": sch.get("site_postcode") or "",
        "contract_id": sch.get("contract_id") or "",
        "company_id": sch.get("company_id") or "",
    }
    case = await _create_case(payload=payload, source="ppm_rollover", user=user)
    case_id = case.get("id")
    if case_id:
        await db.svc_cases.update_one(
            {"id": case_id},
            {"$set": {
                "scheduled_at": due.isoformat(),
                "ppm_schedule_id": sch["id"],
                "ppm_due_date": due.date().isoformat(),
            }})
    return case_id


async def roll_ppm_schedules_once(organization_id: str | None = None) -> dict:
    """Roll every active PPM schedule forward by one visit where due.
    Org-scoped when ``organization_id`` is given (used by the manual
    trigger); otherwise sweeps all orgs (the background worker)."""
    result = {"created": 0, "advanced": 0, "completed_schedules": 0, "skipped": 0}
    query: dict = {"active": True}
    if organization_id:
        query["organization_id"] = organization_id
    now = _now()
    try:
        cursor = db.svc_ppm_schedules.find(query)
        async for sch in cursor:
            try:
                interval = max(1, int(sch.get("interval_days") or 0))
                end = _parse(sch.get("end_date"))
                # Latest visit for this schedule (most recent due date).
                latest = await db.svc_cases.find_one(
                    {"organization_id": sch["organization_id"], "ppm_schedule_id": sch["id"]},
                    sort=[("ppm_due_date", -1), ("created_at", -1)],
                    projection={"_id": 0, "status": 1, "ppm_due_date": 1,
                                "scheduled_at": 1},
                )
                if latest:
                    if (latest.get("status") or "") not in ROLL_TRIGGERS:
                        result["skipped"] += 1
                        continue  # a visit is still open — nothing to roll
                    base = (_parse(latest.get("ppm_due_date"))
                            or _parse(latest.get("scheduled_at")) or now)
                    next_due = base + timedelta(days=interval)
                else:
                    # Self-heal: schedule exists but has no visit yet.
                    next_due = _parse(sch.get("next_due_date")) or now

                # Contract finished — retire the schedule.
                if end and next_due.date() > end.date():
                    await db.svc_ppm_schedules.update_one(
                        {"id": sch["id"]},
                        {"$set": {"active": False, "updated_at": now.isoformat()}})
                    result["completed_schedules"] += 1
                    continue

                # Dedupe guard — don't create a second visit for the same due date.
                dup = await db.svc_cases.find_one(
                    {"organization_id": sch["organization_id"], "ppm_schedule_id": sch["id"],
                     "ppm_due_date": next_due.date().isoformat()},
                    {"_id": 1})
                if dup:
                    result["skipped"] += 1
                    continue

                case_id = await _create_next_visit(sch, next_due)
                if case_id:
                    await db.svc_ppm_schedules.update_one(
                        {"id": sch["id"]},
                        {"$set": {"next_due_date": next_due.date().isoformat(),
                                  "updated_at": now.isoformat()},
                         "$inc": {"visits_generated": 1}})
                    result["created"] += 1
                    result["advanced"] += 1
            except Exception:
                logger.warning("PPM rollover failed for schedule %s",
                               sch.get("id"), exc_info=True)
    except Exception:
        logger.warning("roll_ppm_schedules_once failed", exc_info=True)
    return result


async def run_forever(interval_hours: int = 6):
    """Background loop — roll PPM schedules forward every N hours."""
    interval = max(1, int(interval_hours)) * 3600
    # Small initial delay so startup isn't competing with other loops.
    await asyncio.sleep(45)
    while True:
        try:
            res = await roll_ppm_schedules_once()
            if res.get("created"):
                logger.info("[ppm-rollover] sweep: %s", res)
        except Exception:
            logger.warning("[ppm-rollover] sweep error", exc_info=True)
        # Link up: send ~2-week pre-visit EMAIL reminders (commercial PPM),
        # mirroring the MOD annual-visit reminder. Idempotent per due-date.
        try:
            from routes.svc.ppm_reminders import run_ppm_email_reminders
            rem = await run_ppm_email_reminders()
            if rem.get("sent"):
                logger.info("[ppm-email-reminder] sweep: %s", rem)
        except Exception:
            logger.warning("[ppm-email-reminder] sweep error", exc_info=True)
        await asyncio.sleep(interval)


__all__ = ["roll_ppm_schedules_once", "run_forever"]
