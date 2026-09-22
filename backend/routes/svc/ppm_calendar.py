"""Service Desk — Preventative Maintenance across ALL customers.

Adds a unified, all-customers PPM calendar on top of the per-org PM engine
(`ppm_schedules`). Key ideas:

* When equipment is installed we auto-plan an ANNUAL PPM whose next due date
  is the anniversary of the install date (falls back to purchase date).
* PPM schedules live under the equipment's own org (an imported customer's
  org). The operator (Pulse Fitness Ltd) sees them all via the CRM link
  (`crm2_companies.linked_organization_id`).
* The calendar merges commercial PPM due dates with MOD contract annual
  visits, filterable by segment (all / commercial / mod).
* Scheduling a due PPM creates one engineer job (`svc_cases`, case_type
  "ppm") under the operator, assigns one OR MORE engineers, sets the date,
  and rolls the schedule forward a year.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/ppm", tags=["Service Ops · PPM Calendar"])

# The desk's service catalogue. Warranty / contract services are the same as
# a standard PPM; Calibration is the extra option (used for Fire Stations).
PPM_SERVICES = ["Preventative Maintenance Service", "Calibration"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _operator(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


async def _customer_org_ids(operator: str) -> list[str]:
    """Operator's own org + every CRM-linked customer org."""
    ids = {operator}
    cursor = db.crm2_companies.find(
        {"organization_id": operator, "linked_organization_id": {"$nin": [None, ""]}},
        {"_id": 0, "linked_organization_id": 1},
    )
    async for c in cursor:
        if c.get("linked_organization_id"):
            ids.add(c["linked_organization_id"])
    return list(ids)


def _parse_ymd(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _next_anniversary(install: date, today: date | None = None) -> date:
    """Next annual anniversary of `install` that is >= today."""
    today = today or _today()
    try:
        cand = install.replace(year=today.year)
    except ValueError:  # 29 Feb → 28 Feb
        cand = install.replace(year=today.year, day=28)
    if cand < today:
        cand = cand.replace(year=today.year + 1)
    return cand


async def ensure_annual_ppm(equipment: dict) -> bool:
    """Create an annual PPM schedule for a piece of equipment if one doesn't
    already exist. Anniversary of install_date (fallback purchase_date).
    Returns True if a schedule was created. Idempotent per equipment."""
    org = equipment.get("organization_id")
    eq_id = equipment.get("id")
    if not org or not eq_id:
        return False
    existing = await db.ppm_schedules.find_one(
        {"organization_id": org, "equipment_id": eq_id, "source": "service_desk"},
        {"_id": 0, "id": 1},
    )
    if existing:
        return False
    install = _parse_ymd(equipment.get("install_date")) or _parse_ymd(equipment.get("purchase_date"))
    next_pm = (_next_anniversary(install) if install else None)
    now = _now()
    schedule = {
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "source": "service_desk",
        "auto_generated": True,
        "title": f"PM · {equipment.get('name') or 'Equipment'}",
        "description": "",
        "equipment_id": eq_id,
        "equipment_ids": [eq_id],
        "equipment_name": equipment.get("name"),
        "equipment_type": equipment.get("equipment_type") or "",
        "customer_id": equipment.get("customer_id"),
        "customer_name": equipment.get("customer_name"),
        "site_id": equipment.get("site_id"),
        "site_name": equipment.get("site_name") or "",
        "service_type": "Preventative Maintenance Service",
        "frequency": "annual",
        "last_pm": None,
        "next_pm": next_pm.isoformat() if next_pm else None,
        "install_date": (install.isoformat() if install else ""),
        "assigned_to": "",
        "checklist_items": [],
        "active": True,
        "created_by": "auto",
        "created_at": now,
        "updated_at": now,
    }
    await db.ppm_schedules.insert_one(schedule)
    await db.equipment.update_one(
        {"id": eq_id, "organization_id": org},
        {"$set": {"pm_schedule_id": schedule["id"], "pm_frequency": "annual",
                  "next_pm": schedule["next_pm"], "updated_at": now}},
    )
    return True


# ── Service catalogue ────────────────────────────────────────────

@router.get("/services")
async def list_services(user: dict = Depends(get_current_user)) -> dict:
    return {"services": PPM_SERVICES}


@router.get("/engineer-load")
async def engineer_load(
    date_str: str = Query(..., alias="date"),
    user: dict = Depends(get_current_user),
) -> dict:
    """How many jobs each engineer already has on a given day — so the desk
    can avoid double-booking when allocating a PPM."""
    operator = _operator(user)
    day = _parse_ymd(date_str)
    if not day:
        raise HTTPException(400, "Invalid date")
    lo, hi = f"{day.isoformat()}T00:00:00", f"{day.isoformat()}T23:59:59.999999"
    load: dict = {}
    cursor = db.svc_cases.find(
        {"organization_id": operator,
         "status": {"$nin": ["closed", "resolved", "cancelled", "CLOSED", "RESOLVED", "CANCELLED"]},
         "scheduled_at": {"$gte": lo, "$lte": hi}},
        {"_id": 0, "assigned_engineer_id": 1, "assigned_engineer_ids": 1},
    )
    async for c in cursor:
        ids = c.get("assigned_engineer_ids") or ([c["assigned_engineer_id"]] if c.get("assigned_engineer_id") else [])
        for eid in ids:
            if eid:
                load[eid] = load.get(eid, 0) + 1
    return {"date": day.isoformat(), "load": load}


# ── Back-fill: plan PPM for existing site-associated equipment ────

@router.post("/backfill")
async def backfill_ppm(user: dict = Depends(get_current_user)) -> dict:
    """Generate annual PPM schedules for equipment currently associated with a
    site across the operator + all linked customers. Idempotent."""
    operator = _operator(user)
    org_ids = await _customer_org_ids(operator)
    created = scanned = 0
    for org in org_ids:
        cursor = db.equipment.find(
            {"organization_id": org, "site_id": {"$nin": [None, ""]}}, {"_id": 0},
        )
        async for eq in cursor:
            scanned += 1
            try:
                if await ensure_annual_ppm(eq):
                    created += 1
            except Exception as exc:
                logger.warning("PPM backfill failed for equipment %s: %s", eq.get("id"), exc)
    return {"success": True, "schedules_created": created, "equipment_scanned": scanned}


# ── Unified calendar ─────────────────────────────────────────────

def _status_for(next_pm: date | None, scheduled: bool, today: date) -> str:
    if scheduled:
        return "scheduled"
    if next_pm is None:
        return "unplanned"
    if next_pm < today:
        return "overdue"
    if next_pm <= today + relativedelta(days=14):
        return "due_soon"
    return "planned"


@router.get("/calendar")
async def ppm_calendar(
    from_date: str = Query(None, alias="from"),
    to_date: str = Query(None, alias="to"),
    segment: str = Query("all"),
    user: dict = Depends(get_current_user),
) -> dict:
    """All-customers PPM calendar. Merges commercial PPM due dates with MOD
    contract annual visits. `segment` = all | commercial | mod."""
    operator = _operator(user)
    today = _today()
    d_from = _parse_ymd(from_date) or (today - relativedelta(months=1))
    d_to = _parse_ymd(to_date) or (today + relativedelta(months=6))
    items: list = []

    if segment in ("all", "commercial"):
        org_ids = await _customer_org_ids(operator)
        # Which schedules already have an open job scheduled?
        scheduled_ids = set()
        async for c in db.svc_cases.find(
            {"organization_id": operator, "pm_schedule_id": {"$nin": [None, ""]},
             "status": {"$nin": ["closed", "resolved", "cancelled", "CLOSED", "RESOLVED", "CANCELLED"]}},
            {"_id": 0, "pm_schedule_id": 1},
        ):
            scheduled_ids.add(c.get("pm_schedule_id"))
        cursor = db.ppm_schedules.find(
            {"organization_id": {"$in": org_ids}, "source": "service_desk", "active": True},
            {"_id": 0},
        )
        async for s in cursor:
            npm = _parse_ymd(s.get("next_pm"))
            if npm and not (d_from <= npm <= d_to):
                continue
            if npm is None:
                continue
            is_sched = s.get("id") in scheduled_ids
            items.append({
                "type": "commercial",
                "date": s.get("next_pm"),
                "schedule_id": s.get("id"),
                "organization_id": s.get("organization_id"),
                "title": s.get("title") or "Preventative maintenance",
                "customer_name": s.get("customer_name") or "",
                "site_name": s.get("site_name") or "",
                "equipment_name": s.get("equipment_name") or "",
                "service_type": s.get("service_type") or "Preventative Maintenance Service",
                "frequency": s.get("frequency") or "annual",
                "status": _status_for(npm, is_sched, today),
            })

    if segment in ("all", "mod"):
        async for c in db.mod_service_contracts.find(
            {"organization_id": operator}, {"_id": 0},
        ):
            av = c.get("annual_visit") or {}
            eff = av.get("scheduled_date") or av.get("proposed_date")
            edate = _parse_ymd(eff)
            if not edate or not (d_from <= edate <= d_to):
                continue
            vstatus = av.get("status") or "pending_confirmation"
            items.append({
                "type": "mod",
                "date": eff[:10],
                "contract_id": c.get("id"),
                "title": f"MOD annual visit · {c.get('mod_site_name') or ''}".strip(" ·"),
                "customer_name": c.get("mod_site_name") or "",
                "site_name": c.get("mod_site_name") or "",
                "equipment_name": "",
                "service_type": "MOD Annual Service Visit",
                "engineer": av.get("engineer") or "",
                "status": "scheduled" if vstatus == "confirmed" else "due_soon",
            })

    items.sort(key=lambda x: x["date"])
    return {"items": items, "count": len(items),
            "from": d_from.isoformat(), "to": d_to.isoformat(), "segment": segment}


# ── Schedule a due PPM (create job + allocate engineer(s)) ────────

@router.post("/schedule")
async def schedule_ppm(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Turn a due PPM into a scheduled engineer job. Picks the service,
    allocates one or more engineers and a date, in one step."""
    operator = _operator(user)
    schedule_id = (data.get("schedule_id") or "").strip()
    if not schedule_id:
        raise HTTPException(400, "schedule_id required")
    engineer_ids = [e for e in (data.get("engineer_ids") or []) if e]
    if not engineer_ids and data.get("engineer_id"):
        engineer_ids = [data["engineer_id"]]
    scheduled_at = (data.get("scheduled_at") or "").strip()
    service_type = (data.get("service_type") or "Preventative Maintenance Service").strip()
    if service_type not in PPM_SERVICES:
        service_type = "Preventative Maintenance Service"

    org_ids = await _customer_org_ids(operator)
    sched = await db.ppm_schedules.find_one(
        {"id": schedule_id, "organization_id": {"$in": org_ids}, "source": "service_desk"},
        {"_id": 0},
    )
    if not sched:
        raise HTTPException(404, "PPM schedule not found")

    due_date = (scheduled_at or sched.get("next_pm") or _today().isoformat())[:10]

    # Resolve engineer names (operator roster).
    engineers = []
    if engineer_ids:
        async for e in db.svc_engineers.find(
            {"organization_id": operator, "id": {"$in": engineer_ids}},
            {"_id": 0, "id": 1, "full_name": 1},
        ):
            engineers.append({"id": e["id"], "name": e.get("full_name") or ""})
    eng_names = ", ".join(e["name"] for e in engineers if e["name"])

    # Create the engineer job (operator-scoped svc_case).
    from routes.svc.intake import _create_case
    payload = {
        "title": f"{service_type} · {sched.get('equipment_name') or sched.get('site_name') or 'Equipment'}",
        "description": data.get("notes") or f"Scheduled {service_type.lower()} (annual PPM).",
        "case_type": "ppm",
        "priority": data.get("priority") or "p3",
        "equipment_ids": sched.get("equipment_ids") or [],
        "customer_name": sched.get("customer_name") or "",
        "site_id": sched.get("site_id") or "",
        "site_name": sched.get("site_name") or "",
        "asset_name": sched.get("equipment_name") or "",
        "estimated_minutes": data.get("estimated_minutes") or 90,
    }
    case = await _create_case(payload=payload, source="ppm", user=user)
    case_id = case["id"]

    sched_at_iso = f"{due_date}T09:00:00+00:00"
    case_update = {
        "scheduled_at": sched_at_iso,
        "pm_schedule_id": schedule_id,
        "service_type": service_type,
        "ppm_customer_org_id": sched.get("organization_id"),
        "updated_at": _now(),
    }
    if engineers:
        case_update.update({
            "assigned_engineer_ids": [e["id"] for e in engineers],
            "assigned_engineer_id": engineers[0]["id"],
            "assigned_engineer_name": eng_names,
            "assigned_engineer_names": [e["name"] for e in engineers],
            "status": "ASSIGNED",
            "assigned_at": _now(),
        })
    await db.svc_cases.update_one({"id": case_id, "organization_id": operator}, {"$set": case_update})

    # Roll the schedule forward one year (annual) from the scheduled date.
    next_pm = (_parse_ymd(due_date) + relativedelta(months=12)).isoformat()
    await db.ppm_schedules.update_one(
        {"id": schedule_id, "organization_id": sched.get("organization_id")},
        {"$set": {"last_pm": due_date, "next_pm": next_pm, "service_type": service_type,
                  "updated_at": _now()}},
    )
    await db.equipment.update_one(
        {"id": sched.get("equipment_id"), "organization_id": sched.get("organization_id")},
        {"$set": {"last_pm": due_date, "next_pm": next_pm, "updated_at": _now()}},
    )

    return {
        "success": True, "case_id": case_id, "reference": case.get("reference"),
        "scheduled_at": sched_at_iso, "engineers": engineers,
        "service_type": service_type, "next_pm": next_pm,
    }


__all__ = ["router", "ensure_annual_ppm", "PPM_SERVICES"]
