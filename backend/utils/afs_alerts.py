"""Aftersales proactive alerts — warranty expiry + RPI anniversary reminders.

Auto-creates coordinator tasks (``crm2_activities``) + notifications
(``crm2_notifications``) as two signals cross the 180 / 120 / 90-day windows:

  1. WARRANTY  — uncovered assets whose Pulse warranty ends within a window,
                 grouped ONE task per company per window, linking to the
                 one-click warranty-to-maintenance proposal builder.
  2. RPI       — active contracts whose next annual anniversary falls within a
                 window and whose RPI hasn't been reviewed for that cycle,
                 prompting the coordinator to run the RPI increase.

Escalation is one task per window per item (180 → 120 → 90); a stable
``dedupe_key`` guarantees the sweep never double-creates. Self-healing: a
periodic sweep (not just an event hook) also catches windows crossed while the
app was down.

  ``run_afs_alerts_once(organization_id=None)`` → counts dict.
  ``run_forever(interval_hours=6)`` → background loop.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

WINDOWS = (90, 120, 180)  # tightest first


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(v):
    dt = None
    try:
        dt = datetime.fromisoformat((v or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            dt = datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _window_for(days: int):
    """Tightest window the item currently sits in, else None (>180 days away)."""
    for t in WINDOWS:
        if days <= t:
            return t
    return None


async def _emit(org_id: str, *, dedupe_key: str, activity: dict, notification: dict) -> bool:
    """Insert a task + notification once per dedupe_key. Returns True if created."""
    if await db.crm2_activities.find_one({"organization_id": org_id, "dedupe_key": dedupe_key}, {"_id": 1}):
        return False
    now = _now_iso()
    act = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "owner_id": "system", "owner_name": "Aftersales scanner",
        "status": "open", "source": "afs_alerts", "category": "aftersales_alert",
        "dedupe_key": dedupe_key, "created_at": now, "updated_at": now, **activity,
    }
    await db.crm2_activities.insert_one(act)
    note = {
        "id": str(uuid.uuid4()), "organization_id": org_id, "type": "aftersales_alert",
        "read": False, "created_at": now, "activity_id": act["id"], **notification,
    }
    await db.crm2_notifications.insert_one(note)
    return True


async def _scan_warranty(org_id: str, now: datetime) -> int:
    from routes.crm_aftersales import _resolve_linked_org_for_company
    created = 0
    horizon = now + timedelta(days=max(WINDOWS))
    pseudo = {"organization_id": org_id}
    companies = await db.crm2_companies.find({"organization_id": org_id}, {"_id": 0}).to_list(2000)
    for company in companies:
        linked = await _resolve_linked_org_for_company(company, pseudo)
        if not linked:
            continue
        equipment = await db.equipment.find(
            {"organization_id": linked},
            {"_id": 0, "warranty_expiry": 1, "contract_cover": 1}).to_list(5000)
        expiring = []
        for e in equipment:
            if e.get("contract_cover"):
                continue
            d = _parse(e.get("warranty_expiry"))
            if d and now <= d <= horizon:
                expiring.append((e, (d - now).days))
        if not expiring:
            continue
        earliest_days = min(days for _, days in expiring)
        window = _window_for(earliest_days)
        if window is None:
            continue
        count = sum(1 for _, days in expiring if days <= window)
        earliest_date = min(_parse(e.get("warranty_expiry")) for e, _ in expiring).strftime("%Y-%m-%d")
        name = company.get("name") or "Customer"
        if await _emit(
            org_id, dedupe_key=f"afs:warranty:{company['id']}:{window}",
            activity={
                "type": "warranty_alert", "priority": "high" if window <= 90 else "medium",
                "company_id": company["id"], "threshold_days": window,
                "due_date": earliest_date,
                "subject": f"Warranty alert [T{window}]: {name}",
                "body": (f"{count} machine(s) at {name} come out of Pulse warranty within {window} days "
                         f"(earliest {earliest_date}) and are not yet on a maintenance contract. "
                         f"Build a warranty-to-maintenance proposal."),
                "action": {"type": "build_warranty_proposal", "company_id": company["id"]},
            },
            notification={
                "title": f"{name}: warranty ending (≤{window}d)",
                "message": f"{count} uncovered machine(s) out of warranty within {window} days.",
                "entity_type": "company", "entity_id": company["id"], "entity_name": name,
                "priority": "high" if window <= 90 else "medium",
            }):
            created += 1
    return created


async def _scan_rpi(org_id: str, now: datetime) -> int:
    from routes.crm_aftersales import _next_anniversary
    created = 0
    async for cc in db.crm2_contracts.find(
            {"organization_id": org_id, "status": "active"},
            {"_id": 0, "id": 1, "company_name": 1, "company_id": 1, "contract_number": 1,
             "annual_value": 1, "start_date": 1}):
        anniv = _next_anniversary(cc.get("start_date"), now)
        if not anniv:
            continue
        days = (anniv - now).days
        window = _window_for(days)
        if window is None:
            continue
        cycle = anniv.strftime("%Y")
        review = await db.crm2_afs_rpi_reviews.find_one(
            {"organization_id": org_id, "contract_id": cc["id"], "cycle": cycle}, {"_id": 0, "status": 1})
        if (review or {}).get("status") == "approved":
            continue
        name = cc.get("company_name") or cc.get("contract_number") or "Contract"
        if await _emit(
            org_id, dedupe_key=f"afs:rpi:{cc['id']}:{cycle}:{window}",
            activity={
                "type": "rpi_review_due", "priority": "high" if window <= 90 else "medium",
                "company_id": cc.get("company_id", ""), "contract_id": cc["id"],
                "threshold_days": window, "due_date": anniv.strftime("%Y-%m-%d"),
                "subject": f"RPI review due [T{window}]: {cc.get('contract_number') or name}",
                "body": (f"{name} (£{float(cc.get('annual_value') or 0):,.0f}/yr) has its contract "
                         f"anniversary on {anniv.strftime('%Y-%m-%d')} (in {days} days). "
                         f"Run the {cycle} RPI review to apply the annual increase."),
                "action": {"type": "rpi_review", "contract_id": cc["id"], "cycle": cycle},
            },
            notification={
                "title": f"{name}: RPI review due (≤{window}d)",
                "message": f"Contract anniversary {anniv.strftime('%Y-%m-%d')} — run the {cycle} RPI increase.",
                "entity_type": "contract", "entity_id": cc["id"], "entity_name": name,
                "priority": "high" if window <= 90 else "medium",
            }):
            created += 1
    return created


async def run_afs_alerts_once(organization_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    if organization_id:
        org_ids = [organization_id]
    else:
        org_ids = await db.crm2_companies.distinct("organization_id")
    res = {"warranty_tasks": 0, "rpi_tasks": 0, "orgs_scanned": 0}
    for org_id in org_ids:
        if not org_id:
            continue
        res["orgs_scanned"] += 1
        try:
            res["warranty_tasks"] += await _scan_warranty(org_id, now)
        except Exception:
            logger.warning("[afs-alerts] warranty scan failed for %s", org_id, exc_info=True)
        try:
            res["rpi_tasks"] += await _scan_rpi(org_id, now)
        except Exception:
            logger.warning("[afs-alerts] RPI scan failed for %s", org_id, exc_info=True)
    res["notifications"] = res["warranty_tasks"] + res["rpi_tasks"]
    return res


async def run_forever(interval_hours: int = 6):
    interval = max(1, int(interval_hours)) * 3600
    await asyncio.sleep(60)
    while True:
        try:
            r = await run_afs_alerts_once()
            if r.get("notifications"):
                logger.info("[afs-alerts] sweep: %s", r)
        except Exception:
            logger.warning("[afs-alerts] sweep error", exc_info=True)
        await asyncio.sleep(interval)


__all__ = ["run_afs_alerts_once", "run_forever"]
