"""Service Desk — Preventative Maintenance (PM) scheduling.

Operators schedule recurring PM visits per piece of customer equipment.
A PM schedule is stored as a ``ppm_schedules`` document (``source =
"service_desk"``) so it ALSO surfaces in the Operations portal's
Preventative Maintenance page automatically (both read the same
org-scoped collection). Where the customer is linked to a separate
Operations org, the schedule is mirrored there too.

Frequencies: quarterly (3mo) · biannual / 6-monthly (6mo) · annual (12mo).

When a PM falls due the operator CONFIRMS it, which spawns a real
engineer job (``svc_cases`` of ``case_type="ppm"``) scheduled for the
due date and rolls the schedule forward to the next interval.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user, get_organization_filter
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/pm", tags=["Service Ops · Preventative Maintenance"])

# Frequency → calendar delta. Accepts a couple of friendly aliases.
_FREQ = {
    "quarterly": relativedelta(months=3),
    "biannual": relativedelta(months=6),
    "6_monthly": relativedelta(months=6),
    "6month": relativedelta(months=6),
    "annual": relativedelta(months=12),
}
_FREQ_CANON = {"6_monthly": "biannual", "6month": "biannual"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _canon_freq(freq: str) -> str:
    f = (freq or "annual").strip().lower()
    f = _FREQ_CANON.get(f, f)
    if f not in ("quarterly", "biannual", "annual"):
        raise HTTPException(400, "frequency must be quarterly, biannual or annual")
    return f


def _advance(date_str: str, freq: str) -> str:
    base = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (base + _FREQ[freq]).date().isoformat()


def _is_due(sched: dict, lead_days: int = 0) -> bool:
    nxt = sched.get("next_pm")
    if not sched.get("active", True) or not nxt:
        return False
    cutoff = (datetime.now(timezone.utc).date()
              + relativedelta(days=lead_days)).isoformat()
    return nxt[:10] <= cutoff


async def _linked_ops_orgs(customer: dict | None) -> list[str]:
    """Operations org ids to ALSO mirror the PM into, when a Service-Desk
    customer is explicitly linked to a separate Operations tenant."""
    if not customer:
        return []
    ops_id = customer.get("operations_org_id")
    return [ops_id] if ops_id else []


async def mirror_schedule_into(schedule: dict, target_org: str) -> bool:
    """Insert a mirror PPM schedule (+ next task) into a linked customer
    Operations org so the PM shows on their Preventative Maintenance page.
    Idempotent — skips when a mirror already exists. Returns True if created."""
    if not target_org or target_org == schedule.get("organization_id"):
        return False
    existing = await db.ppm_schedules.find_one(
        {"mirrored_from": schedule["id"], "organization_id": target_org}, {"_id": 0, "id": 1})
    if existing:
        return False
    provider = await db.organizations.find_one(
        {"id": schedule.get("organization_id")}, {"_id": 0, "name": 1})
    mirror = {**schedule, "id": str(uuid.uuid4()),
              "organization_id": target_org,
              "mirrored_from": schedule["id"],
              "mirrored_from_org": schedule.get("organization_id"),
              "mirrored_from_provider_name": (provider or {}).get("name") or "Service provider"}
    mirror.pop("_id", None)
    await db.ppm_schedules.insert_one(mirror)
    mirror.pop("_id", None)
    if mirror.get("next_pm"):
        await db.ppm_tasks.insert_one(_make_task(mirror, mirror["next_pm"]))
    return True


async def _resync_mirrors(schedule_id: str, *, last_pm: str | None = None,
                          next_pm: str | None = None, frequency: str | None = None,
                          add_task_at: str | None = None) -> None:
    """Propagate schedule changes (roll-forward / edit) to every mirror."""
    upd: dict = {"updated_at": _now()}
    if last_pm is not None:
        upd["last_pm"] = last_pm
    if next_pm is not None:
        upd["next_pm"] = next_pm
    if frequency is not None:
        upd["frequency"] = frequency
    async for m in db.ppm_schedules.find({"mirrored_from": schedule_id}, {"_id": 0, "id": 1, "organization_id": 1}):
        await db.ppm_schedules.update_one({"id": m["id"]}, {"$set": upd})
        if add_task_at:
            await db.ppm_tasks.insert_one(
                _make_task({**m, "schedule_id": m["id"], "equipment_ids": [],
                            "site_name": ""}, add_task_at))


async def _delete_mirrors(schedule_id: str) -> None:
    ids = [m["id"] async for m in db.ppm_schedules.find(
        {"mirrored_from": schedule_id}, {"_id": 0, "id": 1})]
    if ids:
        await db.ppm_tasks.delete_many({"schedule_id": {"$in": ids}})
        await db.ppm_schedules.delete_many({"mirrored_from": schedule_id})


async def delete_mirrors_for_customer(source_org: str, customer_id: str, target_org: str) -> None:
    """Remove every mirrored schedule (+ tasks) for a customer in a linked org
    (used when the operator unlinks the customer)."""
    src_ids = [s["id"] async for s in db.ppm_schedules.find(
        {"organization_id": source_org, "source": "service_desk", "customer_id": customer_id},
        {"_id": 0, "id": 1})]
    if not src_ids:
        return
    mirror_ids = [m["id"] async for m in db.ppm_schedules.find(
        {"mirrored_from": {"$in": src_ids}, "organization_id": target_org}, {"_id": 0, "id": 1})]
    if mirror_ids:
        await db.ppm_tasks.delete_many({"schedule_id": {"$in": mirror_ids}})
        await db.ppm_schedules.delete_many({"id": {"$in": mirror_ids}})


def _make_task(schedule: dict, scheduled_date: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "organization_id": schedule.get("organization_id"),
        "schedule_id": schedule["id"],
        "schedule_title": schedule.get("title", ""),
        "site_id": schedule.get("site_id"),
        "site_name": schedule.get("site_name", ""),
        "equipment_ids": schedule.get("equipment_ids", []),
        "assigned_to": schedule.get("assigned_to", ""),
        "checklist_items": schedule.get("checklist_items", []),
        "scheduled_date": scheduled_date[:10],
        "status": "scheduled",
        "completed_date": None,
        "completed_by": None,
        "completion_notes": None,
        "checklist_results": [],
        "source": "service_desk",
        "created_at": _now(),
    }


async def _equipment(equipment_id: str, of: dict) -> dict:
    eq = await db.equipment.find_one({"id": equipment_id, **of}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    return eq


def _enrich(sched: dict) -> dict:
    sched["is_due"] = _is_due(sched)
    return sched


# ── Schedule CRUD ────────────────────────────────────────────────

@router.get("/schedules")
async def list_pm_schedules(
    equipment_id: str | None = Query(None),
    customer_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """List the org's Service-Desk PM schedules (newest first)."""
    of = _of(user)
    q = {**of, "source": "service_desk"}
    if equipment_id:
        q["equipment_ids"] = equipment_id
    if customer_id:
        q["customer_id"] = customer_id
    rows = await db.ppm_schedules.find(q, {"_id": 0}).sort("next_pm", 1).to_list(1000)
    return {"schedules": [_enrich(r) for r in rows]}


@router.post("/schedules")
async def create_pm_schedule(data: dict = Body(...), user: dict = Depends(get_current_user)):
    """Schedule recurring PM for one piece of equipment."""
    of = _of(user)
    equipment_id = (data.get("equipment_id") or "").strip()
    if not equipment_id:
        raise HTTPException(400, "equipment_id required")
    freq = _canon_freq(data.get("frequency"))
    next_pm = (data.get("next_pm") or "").strip()
    if not next_pm:
        raise HTTPException(400, "next_pm (YYYY-MM-DD) required")
    try:
        datetime.strptime(next_pm[:10], "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "next_pm must be YYYY-MM-DD")
    last_pm = (data.get("last_pm") or "").strip() or None

    eq = await _equipment(equipment_id, of)
    customer = None
    if eq.get("customer_id"):
        customer = await db.svc_engineer_customers.find_one(
            {"id": eq["customer_id"], **of}, {"_id": 0})

    now = _now()
    schedule = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "source": "service_desk",
        "title": data.get("title") or f"PM · {eq.get('name') or 'Equipment'}",
        "description": data.get("description", ""),
        "equipment_id": equipment_id,
        "equipment_ids": [equipment_id],
        "equipment_name": eq.get("name"),
        "equipment_type": eq.get("equipment_type") or "",
        "customer_id": eq.get("customer_id"),
        "customer_name": eq.get("customer_name"),
        "site_id": eq.get("site_id"),
        "site_name": eq.get("site_name") or eq.get("customer_name") or "",
        "frequency": freq,
        "last_pm": last_pm,
        "next_pm": next_pm[:10],
        "install_date": last_pm or eq.get("purchase_date") or "",
        "assigned_to": data.get("assigned_to", ""),
        "checklist_items": data.get("checklist_items", []),
        "checklist_category": data.get("checklist_category", ""),
        "certificates": [],
        "active": True,
        "created_by": user.get("full_name") or user.get("email") or "",
        "created_by_id": user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.ppm_schedules.insert_one(schedule)
    schedule.pop("_id", None)
    await db.ppm_tasks.insert_one(_make_task(schedule, next_pm))

    # Stamp PM fields onto the equipment for at-a-glance + import round-trip.
    await db.equipment.update_one(
        {"id": equipment_id, **of},
        {"$set": {"pm_schedule_id": schedule["id"], "pm_frequency": freq,
                  "next_pm": next_pm[:10], "last_pm": last_pm, "updated_at": now}},
    )

    # Mirror into a linked Operations org's PPM, where a link exists.
    for ops_org in await _linked_ops_orgs(customer):
        await mirror_schedule_into(schedule, ops_org)

    return _enrich(schedule)


@router.put("/schedules/{schedule_id}")
async def update_pm_schedule(schedule_id: str, data: dict = Body(...),
                             user: dict = Depends(get_current_user)):
    of = _of(user)
    updates: dict = {"updated_at": _now()}
    if "frequency" in data:
        updates["frequency"] = _canon_freq(data.get("frequency"))
    if data.get("next_pm"):
        try:
            datetime.strptime(data["next_pm"][:10], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "next_pm must be YYYY-MM-DD")
        updates["next_pm"] = data["next_pm"][:10]
    if "last_pm" in data:
        updates["last_pm"] = data["last_pm"] or None
    if "active" in data:
        updates["active"] = bool(data["active"])
    if "assigned_to" in data:
        updates["assigned_to"] = data["assigned_to"]
    res = await db.ppm_schedules.update_one(
        {"id": schedule_id, "source": "service_desk", **of}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Schedule not found")
    if "next_pm" in updates or "frequency" in updates:
        eq_set = {k: updates[k] for k in ("next_pm",) if k in updates}
        if "frequency" in updates:
            eq_set["pm_frequency"] = updates["frequency"]
        sched = await db.ppm_schedules.find_one({"id": schedule_id, **of}, {"_id": 0, "equipment_id": 1})
        if sched and sched.get("equipment_id"):
            await db.equipment.update_one({"id": sched["equipment_id"], **of}, {"$set": eq_set})
        await _resync_mirrors(schedule_id, next_pm=updates.get("next_pm"),
                              frequency=updates.get("frequency"))
    fresh = await db.ppm_schedules.find_one({"id": schedule_id, **of}, {"_id": 0})
    return _enrich(fresh)


@router.delete("/schedules/{schedule_id}")
async def delete_pm_schedule(schedule_id: str, user: dict = Depends(get_current_user)):
    of = _of(user)
    sched = await db.ppm_schedules.find_one(
        {"id": schedule_id, "source": "service_desk", **of}, {"_id": 0})
    if not sched:
        raise HTTPException(404, "Schedule not found")
    await db.ppm_schedules.delete_one({"id": schedule_id, **of})
    await db.ppm_tasks.delete_many({"schedule_id": schedule_id})
    await _delete_mirrors(schedule_id)
    if sched.get("equipment_id"):
        await db.equipment.update_one(
            {"id": sched["equipment_id"], **of},
            {"$unset": {"pm_schedule_id": "", "next_pm": "", "pm_frequency": ""}},
        )
    return {"success": True}


# ── Due list + operator confirmation ─────────────────────────────

@router.get("/due")
async def list_due_pm(lead_days: int = Query(0, ge=0, le=90),
                      user: dict = Depends(get_current_user)):
    """PM schedules due now (or within ``lead_days``) awaiting operator
    confirmation to spawn the engineer job."""
    of = _of(user)
    rows = await db.ppm_schedules.find(
        {**of, "source": "service_desk", "active": True}, {"_id": 0},
    ).sort("next_pm", 1).to_list(1000)
    due = [r for r in rows if _is_due(r, lead_days)]
    return {"due": due, "count": len(due)}


@router.post("/schedules/{schedule_id}/confirm")
async def confirm_pm_visit(schedule_id: str, data: dict = Body(default={}),
                           user: dict = Depends(get_current_user)):
    """Operator confirms a due PM → creates the engineer job and rolls the
    schedule forward to the next interval."""
    of = _of(user)
    sched = await db.ppm_schedules.find_one(
        {"id": schedule_id, "source": "service_desk", **of}, {"_id": 0})
    if not sched:
        raise HTTPException(404, "Schedule not found")
    due_date = (data.get("scheduled_at") or sched.get("next_pm") or _today())[:10]
    freq = _canon_freq(sched.get("frequency"))

    from routes.svc.intake import _create_case  # lazy — avoid import cycle
    payload = {
        "title": f"PM visit · {sched.get('equipment_name') or 'Equipment'}",
        "description": data.get("notes")
                       or f"Scheduled preventative maintenance ({freq}).",
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
    scheduled_at = f"{due_date}T09:00:00+00:00"
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {"scheduled_at": scheduled_at, "pm_schedule_id": schedule_id,
                  "updated_at": _now()}},
    )

    # Mark the due task as converted, roll the schedule forward.
    next_pm = _advance(due_date, freq)
    await db.ppm_tasks.update_one(
        {"schedule_id": schedule_id, "scheduled_date": due_date},
        {"$set": {"status": "job_created", "case_id": case_id,
                  "case_reference": case.get("reference"), "converted_at": _now()}},
    )
    await db.ppm_schedules.update_one(
        {"id": schedule_id, **of},
        {"$set": {"last_pm": due_date, "next_pm": next_pm, "updated_at": _now()}},
    )
    # Refresh the equipment + drop a fresh upcoming task.
    if sched.get("equipment_id"):
        await db.equipment.update_one(
            {"id": sched["equipment_id"], **of},
            {"$set": {"last_pm": due_date, "next_pm": next_pm, "updated_at": _now()}},
        )
    fresh = {**sched, "next_pm": next_pm}
    await db.ppm_tasks.insert_one(_make_task(fresh, next_pm))
    # Keep any linked customer-org mirrors in step.
    await _resync_mirrors(schedule_id, last_pm=due_date, next_pm=next_pm, add_task_at=next_pm)

    return {"case_id": case_id, "reference": case.get("reference"),
            "scheduled_at": scheduled_at, "next_pm": next_pm}


async def ensure_pm_indexes() -> None:
    try:
        await db.ppm_schedules.create_index([("organization_id", 1), ("source", 1), ("next_pm", 1)])
        await db.ppm_schedules.create_index([("equipment_id", 1)])
    except Exception:  # noqa: BLE001
        logger.warning("[svc.pm] index creation failed", exc_info=True)
