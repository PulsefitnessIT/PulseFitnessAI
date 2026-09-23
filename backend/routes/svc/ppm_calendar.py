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
import re
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
    operator = _operator(user)
    await _seed_service_types(operator)
    names = list(PPM_SERVICES)
    async for st in db.ppm_service_types.find(
        {"organization_id": operator, "active": {"$ne": False}}, {"_id": 0, "name": 1},
    ):
        if st.get("name") and st["name"] not in names:
            names.append(st["name"])
    return {"services": names}


# ── Service type catalogue (operator-managed) ────────────────────

_DEFAULT_SERVICE_TYPES = [
    {"name": "Preventative Maintenance Service", "description": "Standard scheduled PM visit.",
     "default_frequency": "annual", "checklist_items": [], "requires_calibration": False},
    {"name": "Treadmill Calibration", "description": "Speed / incline calibration for treadmills (e.g. Fire Station fitness suites).",
     "default_frequency": "annual",
     "checklist_items": ["Speed — 3 mph", "Speed — 6 mph", "Speed — 9 mph", "Speed — 12 mph",
                          "Incline — 0%", "Incline — 5%", "Incline — 10%", "Incline — 15%"],
     "requires_calibration": True},
    {"name": "Safety / Compliance Inspection", "description": "Statutory safety inspection.",
     "default_frequency": "annual", "checklist_items": ["Visual safety check", "Electrical safety (PAT)"],
     "requires_calibration": False},
    {"name": "Fire Station Service",
     "description": "Full PM service on every machine at the station, plus speed / incline "
                    "calibration for the treadmills. One certificate covers all treadmills.",
     "default_frequency": "annual",
     "checklist_items": ["Visual safety check", "Frame & fixings", "Console & display",
                         "Belt & deck condition", "Lubrication", "Electrical safety (PAT)"],
     "requires_calibration": True, "calibrate_treadmills": True},
]


async def _seed_service_types(operator: str) -> None:
    """Ensure the operator has every default service type. Idempotent — inserts
    only defaults whose name is missing, so new defaults (e.g. Fire Station
    Service) propagate to orgs seeded before they existed, without duplicating
    or resurrecting operator-deleted types."""
    existing = set()
    async for st in db.ppm_service_types.find(
        {"organization_id": operator}, {"_id": 0, "name": 1}):
        if st.get("name"):
            existing.add(st["name"])
    now = _now()
    docs = [{"id": str(uuid.uuid4()), "organization_id": operator, "active": True,
             "created_at": now, "updated_at": now, **st}
            for st in _DEFAULT_SERVICE_TYPES if st["name"] not in existing]
    if docs:
        await db.ppm_service_types.insert_many(docs)


@router.get("/service-types")
async def list_service_types(user: dict = Depends(get_current_user)) -> dict:
    operator = _operator(user)
    await _seed_service_types(operator)
    rows = await db.ppm_service_types.find(
        {"organization_id": operator, "active": {"$ne": False}}, {"_id": 0},
    ).sort("name", 1).to_list(200)
    return {"service_types": rows, "count": len(rows)}


@router.post("/service-types")
async def create_service_type(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    operator = _operator(user)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    now = _now()
    doc = {
        "id": str(uuid.uuid4()), "organization_id": operator, "name": name,
        "description": (data.get("description") or "").strip(),
        "default_frequency": (data.get("default_frequency") or "annual"),
        "checklist_items": [str(c).strip() for c in (data.get("checklist_items") or []) if str(c).strip()],
        "requires_calibration": bool(data.get("requires_calibration")),
        "calibrate_treadmills": bool(data.get("calibrate_treadmills")),
        "active": True, "created_at": now, "updated_at": now,
    }
    await db.ppm_service_types.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "service_type": doc}


@router.put("/service-types/{st_id}")
async def update_service_type(st_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    operator = _operator(user)
    upd: dict = {"updated_at": _now()}
    for k in ("name", "description", "default_frequency"):
        if k in data:
            upd[k] = data[k]
    if "checklist_items" in data:
        upd["checklist_items"] = [str(c).strip() for c in (data.get("checklist_items") or []) if str(c).strip()]
    if "requires_calibration" in data:
        upd["requires_calibration"] = bool(data["requires_calibration"])
    if "calibrate_treadmills" in data:
        upd["calibrate_treadmills"] = bool(data["calibrate_treadmills"])
    r = await db.ppm_service_types.update_one({"id": st_id, "organization_id": operator}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Service type not found")
    return {"success": True}


@router.delete("/service-types/{st_id}")
async def delete_service_type(st_id: str, user: dict = Depends(get_current_user)) -> dict:
    operator = _operator(user)
    await db.ppm_service_types.update_one(
        {"id": st_id, "organization_id": operator}, {"$set": {"active": False, "updated_at": _now()}})
    return {"success": True}


# ── Manual + bulk PM schedule creation ───────────────────────────

async def _make_ppm_schedule(*, org, customer_id, customer_name, site_id, site_name,
                             equipment_ids, equipment_name, service_type, frequency,
                             next_pm, checklist_items, created_by, title=None,
                             assigned_engineer_id="", assigned_engineer_name="",
                             machine_count=None, site_address="") -> dict:
    now = _now()
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org, "source": "service_desk",
        "auto_generated": False,
        "title": title or f"{service_type} · {site_name or equipment_name or 'Site'}",
        "description": "", "equipment_id": (equipment_ids[0] if equipment_ids else None),
        "equipment_ids": equipment_ids or [], "equipment_name": equipment_name or "",
        "equipment_type": "", "customer_id": customer_id, "customer_name": customer_name or "",
        "site_id": site_id, "site_name": site_name or "", "site_address": site_address or "",
        "service_type": service_type,
        "frequency": frequency, "last_pm": None,
        "next_pm": next_pm.isoformat() if hasattr(next_pm, "isoformat") else next_pm,
        "install_date": "", "assigned_to": "",
        "assigned_engineer_id": assigned_engineer_id or "",
        "assigned_engineer_name": assigned_engineer_name or "",
        "machine_count": (machine_count if machine_count is not None else len(equipment_ids or [])),
        "checklist_items": checklist_items or [],
        "active": True, "created_by": created_by, "created_at": now, "updated_at": now,
    }
    await db.ppm_schedules.insert_one(doc)
    return doc


async def _service_type_checklist(operator, name) -> list:
    st = await db.ppm_service_types.find_one(
        {"organization_id": operator, "name": name}, {"_id": 0, "checklist_items": 1})
    return (st or {}).get("checklist_items") or []


@router.post("/schedules")
async def create_ppm_schedule(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Manually create a single PM schedule for a customer site / equipment."""
    operator = _operator(user)
    customer_org = (data.get("customer_org_id") or "").strip()
    site_id = (data.get("site_id") or "").strip()
    if not customer_org or not site_id:
        raise HTTPException(400, "customer_org_id and site_id required")
    service_type = (data.get("service_type") or "Preventative Maintenance Service").strip()
    frequency = (data.get("frequency") or "annual").strip()
    first = _parse_ymd(data.get("first_visit")) or _today()
    equipment_ids = [e for e in (data.get("equipment_ids") or []) if e]
    site = await db.sites.find_one({"id": site_id}, {"_id": 0, "name": 1})
    cust = await db.organizations.find_one({"id": customer_org}, {"_id": 0, "name": 1})
    eq_name = ""
    if equipment_ids:
        first_eq = await db.equipment.find_one({"id": equipment_ids[0]}, {"_id": 0, "name": 1})
        eq_name = (first_eq or {}).get("name") or f"{len(equipment_ids)} machines"
    checklist = await _service_type_checklist(operator, service_type)
    doc = await _make_ppm_schedule(
        org=customer_org, customer_id=customer_org, customer_name=(cust or {}).get("name"),
        site_id=site_id, site_name=(site or {}).get("name"), equipment_ids=equipment_ids,
        equipment_name=eq_name, service_type=service_type, frequency=frequency,
        next_pm=first, checklist_items=checklist, created_by=user.get("id") or "operator")
    return {"success": True, "schedule_id": doc["id"], "next_pm": doc["next_pm"]}


@router.post("/schedules/bulk")
async def bulk_ppm_schedules(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Bulk-schedule PM across many sites for one customer (e.g. 85 fire
    stations).

    Two modes:
    * Wizard mode — `assignments`: [{site_id, date, engineer_id, engineer_name}]
      creates one schedule per site on its exact planned date + engineer.
    * Legacy mode — `site_ids` + `start_date` + `stagger_days` + `granularity`.
    """
    operator = _operator(user)
    customer_org = (data.get("customer_org_id") or "").strip()
    if not customer_org:
        raise HTTPException(400, "customer_org_id required")
    service_type = (data.get("service_type") or "Preventative Maintenance Service").strip()
    frequency = (data.get("frequency") or "annual").strip()
    cust = await db.organizations.find_one({"id": customer_org}, {"_id": 0, "name": 1})
    cust_name = (cust or {}).get("name")
    checklist = await _service_type_checklist(operator, service_type)
    created = 0

    assignments = data.get("assignments") or []
    if assignments:
        for a in assignments:
            sid = (a.get("site_id") or "").strip()
            if not sid:
                continue
            site = await db.sites.find_one({"id": sid}, {"_id": 0, "name": 1, "address": 1})
            if not site:
                continue
            visit = _parse_ymd(a.get("date")) or _today()
            eqs = await db.equipment.find(
                {"organization_id": customer_org, "site_id": sid}, {"_id": 0, "id": 1}).to_list(4000)
            eq_ids = [e["id"] for e in eqs]
            await _make_ppm_schedule(
                org=customer_org, customer_id=customer_org, customer_name=cust_name,
                site_id=sid, site_name=site.get("name"), site_address=site.get("address") or "",
                equipment_ids=eq_ids,
                equipment_name=(f"{len(eq_ids)} machines" if eq_ids else site.get("name")),
                service_type=service_type, frequency=frequency, next_pm=visit,
                checklist_items=checklist, created_by=user.get("id") or "operator",
                assigned_engineer_id=(a.get("engineer_id") or "").strip(),
                assigned_engineer_name=(a.get("engineer_name") or "").strip(),
                machine_count=len(eq_ids))
            created += 1
        return {"success": True, "schedules_created": created, "sites": len(assignments)}

    # ── Legacy stagger mode ──
    site_ids = [s for s in (data.get("site_ids") or []) if s]
    if not site_ids:
        raise HTTPException(400, "site_ids or assignments required")
    start = _parse_ymd(data.get("start_date")) or _today()
    try:
        stagger = max(0, int(data.get("stagger_days") or 0))
    except (TypeError, ValueError):
        stagger = 0
    granularity = (data.get("granularity") or "site").strip()
    eng_id = (data.get("engineer_id") or "").strip()
    eng_name = (data.get("engineer_name") or "").strip()
    for i, sid in enumerate(site_ids):
        site = await db.sites.find_one({"id": sid}, {"_id": 0, "name": 1, "address": 1})
        if not site:
            continue
        eqs = await db.equipment.find(
            {"organization_id": customer_org, "site_id": sid}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(2000)
        if granularity == "equipment" and eqs:
            for e in eqs:
                visit = start + relativedelta(days=created * stagger) if stagger else start
                await _make_ppm_schedule(
                    org=customer_org, customer_id=customer_org, customer_name=cust_name,
                    site_id=sid, site_name=site.get("name"), site_address=site.get("address") or "",
                    equipment_ids=[e["id"]], equipment_name=e.get("name"),
                    service_type=service_type, frequency=frequency, next_pm=visit,
                    checklist_items=checklist, created_by=user.get("id") or "operator",
                    assigned_engineer_id=eng_id, assigned_engineer_name=eng_name, machine_count=1)
                created += 1
        else:
            visit = start + relativedelta(days=i * stagger) if stagger else start
            eq_ids = [e["id"] for e in eqs]
            await _make_ppm_schedule(
                org=customer_org, customer_id=customer_org, customer_name=cust_name,
                site_id=sid, site_name=site.get("name"), site_address=site.get("address") or "",
                equipment_ids=eq_ids,
                equipment_name=(f"{len(eq_ids)} machines" if eq_ids else site.get("name")),
                service_type=service_type, frequency=frequency, next_pm=visit,
                checklist_items=checklist, created_by=user.get("id") or "operator",
                assigned_engineer_id=eng_id, assigned_engineer_name=eng_name,
                machine_count=len(eq_ids))
            created += 1
    return {"success": True, "schedules_created": created, "sites": len(site_ids)}


@router.post("/plan/group")
async def plan_group_sites(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """AI-group the selected sites into geographic runs (nearby sites together)
    and return them in a sensible visiting order, for the bulk scheduling wizard."""
    operator = _operator(user)
    customer_org = (data.get("customer_org_id") or "").strip()
    site_ids = [s for s in (data.get("site_ids") or []) if s]
    if not customer_org or not site_ids:
        raise HTTPException(400, "customer_org_id and site_ids required")
    from utils.ppm_route_ai import group_sites_by_proximity
    sites = await db.sites.find(
        {"id": {"$in": site_ids}}, {"_id": 0, "id": 1, "name": 1, "address": 1}).to_list(4000)
    # keep only the requested ids, preserving lookup of machine counts
    counts = {}
    for sid in site_ids:
        counts[sid] = await db.equipment.count_documents(
            {"organization_id": customer_org, "site_id": sid})
    by_id = {s["id"]: s for s in sites}
    ordered = [by_id[s] for s in site_ids if s in by_id]
    result = await group_sites_by_proximity(ordered)
    # decorate groups with site names + machine counts for the UI
    for g in result.get("groups", []):
        g["sites"] = [{
            "id": sid,
            "name": (by_id.get(sid) or {}).get("name") or "Site",
            "address": (by_id.get(sid) or {}).get("address") or "",
            "machine_count": counts.get(sid, 0),
        } for sid in g.get("site_ids", [])]
    return result


@router.get("/search")
async def search_schedules(
    q: str = Query("", min_length=0),
    user: dict = Depends(get_current_user),
) -> dict:
    """Search booked PM visits by site / customer / service name across all
    months — so desk users can quickly find when a site is booked in."""
    operator = _operator(user)
    term = (q or "").strip()
    if len(term) < 2:
        return {"results": []}
    org_ids = await _customer_org_ids(operator)
    today = _today()
    rx = {"$regex": re.escape(term), "$options": "i"}
    cursor = db.ppm_schedules.find(
        {"organization_id": {"$in": org_ids}, "source": "service_desk", "active": True,
         "$or": [{"site_name": rx}, {"customer_name": rx}, {"service_type": rx}]},
        {"_id": 0},
    ).limit(60)
    scheduled_ids = await _scheduled_schedule_ids(operator)
    out = []
    async for s in cursor:
        npm = _parse_ymd(s.get("next_pm"))
        if not npm:
            continue
        out.append({
            "schedule_id": s.get("id"), "date": s.get("next_pm"),
            "site_name": s.get("site_name") or "", "customer_name": s.get("customer_name") or "",
            "service_type": s.get("service_type") or "", "site_id": s.get("site_id") or "",
            "machine_count": s.get("machine_count", len(s.get("equipment_ids") or [])),
            "engineer": s.get("assigned_engineer_name") or "",
            "status": _status_for(npm, s.get("id") in scheduled_ids, today),
        })
    out.sort(key=lambda x: x["date"])
    return {"results": out[:40], "count": len(out)}


async def _scheduled_schedule_ids(operator: str) -> set:
    ids = set()
    async for c in db.svc_cases.find(
        {"organization_id": operator, "pm_schedule_id": {"$nin": [None, ""]},
         "status": {"$nin": ["closed", "resolved", "cancelled", "CLOSED", "RESOLVED", "CANCELLED"]}},
        {"_id": 0, "pm_schedule_id": 1},
    ):
        ids.add(c.get("pm_schedule_id"))
    return ids


@router.get("/schedules/{schedule_id}")
async def schedule_detail(schedule_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Full detail for one PM visit: site + every machine involved; and once a
    job has been completed against it, the engineer's workings."""
    operator = _operator(user)
    org_ids = await _customer_org_ids(operator)
    s = await db.ppm_schedules.find_one(
        {"id": schedule_id, "organization_id": {"$in": org_ids}, "source": "service_desk"},
        {"_id": 0})
    if not s:
        raise HTTPException(404, "PM visit not found")
    eq_ids = s.get("equipment_ids") or []
    machines = []
    if eq_ids:
        eqs = await db.equipment.find(
            {"id": {"$in": eq_ids}},
            {"_id": 0, "id": 1, "name": 1, "equipment_type": 1, "manufacturer": 1,
             "model": 1, "serial_number": 1},
        ).to_list(4000)
        machines = [{
            "id": e.get("id"), "name": e.get("name") or "Equipment",
            "equipment_type": e.get("equipment_type") or "", "manufacturer": e.get("manufacturer") or "",
            "model": e.get("model") or "", "serial_number": e.get("serial_number") or "",
        } for e in eqs]

    # Related engineer job (if scheduled / completed)
    job = await db.svc_cases.find_one(
        {"pm_schedule_id": schedule_id, "organization_id": operator},
        {"_id": 0, "id": 1, "reference": 1, "status": 1, "scheduled_at": 1,
         "assigned_engineer_name": 1, "assigned_engineer_names": 1, "completed_at": 1,
         "resolution": 1, "resolution_notes": 1, "work_summary": 1, "engineer_notes": 1,
         "calibration_result": 1, "calibration_captured": 1},
        sort=[("created_at", -1)])
    workings = None
    if job:
        status = str(job.get("status") or "").lower()
        completed = status in ("closed", "resolved", "completed")
        engineer = job.get("assigned_engineer_name") or ", ".join(job.get("assigned_engineer_names") or [])
        machine_work = []
        if completed:
            async for m in db.svc_work_visit_machines.find(
                {"case_id": job["id"]},
                {"_id": 0, "asset_name": 1, "serviced": 1, "cleaned": 1, "notes": 1,
                 "result": 1, "custom_fields": 1}):
                machine_work.append({
                    "asset_name": m.get("asset_name") or "", "serviced": m.get("serviced"),
                    "cleaned": m.get("cleaned"), "notes": m.get("notes") or "",
                    "result": m.get("result") or "",
                })
        workings = {
            "reference": job.get("reference") or "", "status": job.get("status") or "",
            "completed": completed, "engineer": engineer,
            "scheduled_at": job.get("scheduled_at") or "", "completed_at": job.get("completed_at") or "",
            "summary": job.get("work_summary") or job.get("resolution") or job.get("resolution_notes") or "",
            "engineer_notes": job.get("engineer_notes") or "",
            "calibration_result": job.get("calibration_result") or "",
            "calibration_captured": bool(job.get("calibration_captured")),
            "machine_work": machine_work,
        }

    return {
        "schedule": {
            "id": s.get("id"), "site_name": s.get("site_name") or "",
            "site_address": s.get("site_address") or "", "customer_name": s.get("customer_name") or "",
            "service_type": s.get("service_type") or "", "frequency": s.get("frequency") or "",
            "date": s.get("next_pm"), "machine_count": s.get("machine_count", len(eq_ids)),
            "engineer": s.get("assigned_engineer_name") or "",
            "site_id": s.get("site_id") or "", "organization_id": s.get("organization_id"),
        },
        "machines": machines,
        "workings": workings,
    }


@router.post("/schedules/{schedule_id}/reschedule")
async def reschedule_schedule(schedule_id: str, data: dict = Body(...),
                              user: dict = Depends(get_current_user)) -> dict:
    """Move a single PM visit to a new date (drag-and-drop on the calendar)."""
    operator = _operator(user)
    new_date = _parse_ymd(data.get("date"))
    if not new_date:
        raise HTTPException(400, "Valid date required")
    org_ids = await _customer_org_ids(operator)
    res = await db.ppm_schedules.update_one(
        {"id": schedule_id, "organization_id": {"$in": org_ids},
         "source": "service_desk", "active": True},
        {"$set": {"next_pm": new_date.isoformat(), "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "PM visit not found")
    return {"success": True, "date": new_date.isoformat()}


@router.post("/schedules/delete")
async def bulk_delete_schedules(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Soft-delete (active:false) the given PM schedules. Scoped to the
    operator's own + CRM-linked customer orgs."""
    operator = _operator(user)
    ids = [x for x in (data.get("schedule_ids") or []) if x]
    if not ids:
        raise HTTPException(400, "schedule_ids required")
    org_ids = await _customer_org_ids(operator)
    res = await db.ppm_schedules.update_many(
        {"id": {"$in": ids}, "organization_id": {"$in": org_ids}, "source": "service_desk"},
        {"$set": {"active": False, "updated_at": _now()}})
    return {"success": True, "deleted": res.modified_count}


@router.post("/schedules/delete-all")
async def delete_all_for_customer(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """One-click: soft-delete every PM schedule for a single customer (used to
    clear a mistaken bulk import). Optional from/to date window."""
    operator = _operator(user)
    customer_org = (data.get("customer_org_id") or "").strip()
    if not customer_org:
        raise HTTPException(400, "customer_org_id required")
    org_ids = await _customer_org_ids(operator)
    if customer_org not in org_ids:
        raise HTTPException(403, "Customer not linked to your organisation")
    q = {"organization_id": customer_org, "source": "service_desk", "active": True}
    d_from = _parse_ymd(data.get("from"))
    d_to = _parse_ymd(data.get("to"))
    if d_from or d_to:
        rng = {}
        if d_from:
            rng["$gte"] = d_from.isoformat()
        if d_to:
            rng["$lte"] = d_to.isoformat()
        q["next_pm"] = rng
    res = await db.ppm_schedules.update_many(q, {"$set": {"active": False, "updated_at": _now()}})
    return {"success": True, "deleted": res.modified_count}



@router.get("/engineer-load")
async def engineer_load(
    date_str: str = Query(..., alias="date"),
    site_id: str = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    """Each engineer's existing jobs (count + time slots) on a given day, plus
    a suggested engineer (least-loaded, tie-broken by proximity to the site) —
    so the desk can slot a PPM into a free gap and allocate fast."""
    operator = _operator(user)
    day = _parse_ymd(date_str)
    if not day:
        raise HTTPException(400, "Invalid date")
    lo, hi = f"{day.isoformat()}T00:00:00", f"{day.isoformat()}T23:59:59.999999"

    def _outward(pc):
        return (str(pc or "").strip().upper().split(" ")[0] or "")[:4]

    # 1) Gather the day's jobs (with their site) per engineer.
    load: dict = {}
    slots: dict = {}
    day_site_ids: dict = {}  # engineer -> set of their job site_ids that day
    all_site_ids: set = set()
    cursor = db.svc_cases.find(
        {"organization_id": operator,
         "status": {"$nin": ["closed", "resolved", "cancelled", "CLOSED", "RESOLVED", "CANCELLED"]},
         "scheduled_at": {"$gte": lo, "$lte": hi}},
        {"_id": 0, "assigned_engineer_id": 1, "assigned_engineer_ids": 1,
         "scheduled_at": 1, "title": 1, "estimated_minutes": 1, "site_id": 1, "site_name": 1},
    )
    async for c in cursor:
        ids = c.get("assigned_engineer_ids") or ([c["assigned_engineer_id"]] if c.get("assigned_engineer_id") else [])
        t = str(c.get("scheduled_at") or "")[11:16] or "—"
        sid = c.get("site_id")
        if sid:
            all_site_ids.add(sid)
        slot = {"time": t, "title": c.get("title") or "Job", "minutes": c.get("estimated_minutes") or 0,
                "site_name": c.get("site_name") or "", "site_id": sid or ""}
        for eid in ids:
            if eid:
                load[eid] = load.get(eid, 0) + 1
                slots.setdefault(eid, []).append(slot)
                if sid:
                    day_site_ids.setdefault(eid, set()).add(sid)
    for lst in slots.values():
        lst.sort(key=lambda s: s["time"])

    # 2) Resolve postcode outward codes for the target + every job site.
    site_out = ""
    site_out_by_id: dict = {}
    lookup_ids = set(all_site_ids)
    if site_id:
        lookup_ids.add(site_id)
    if lookup_ids:
        async for s in db.sites.find({"id": {"$in": list(lookup_ids)}}, {"_id": 0, "id": 1, "postcode": 1}):
            site_out_by_id[s["id"]] = _outward(s.get("postcode"))
        site_out = site_out_by_id.get(site_id, "")

    # 3) Suggest: prefer an engineer already working the target's area that day
    #    (efficient back-to-back), then least-loaded, then home proximity.
    FULL_DAY = 4  # don't pile onto an already-full engineer for the travel bonus
    suggested = None
    best_key = None
    async for e in db.svc_engineers.find(
        {"organization_id": operator, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "home_postcode": 1, "postcode": 1, "home_address": 1},
    ):
        eid = e.get("id")
        n = load.get(eid, 0)
        eng_out = _outward(e.get("home_postcode") or e.get("postcode"))
        if not eng_out and e.get("home_address"):
            import re as _re
            m = _re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b", str(e["home_address"]).upper())
            eng_out = m.group(1) if m else ""
        # Travel-aware: is this engineer already at the target's area today?
        near_today = bool(site_out) and n < FULL_DAY and any(
            site_out_by_id.get(sid) == site_out for sid in day_site_ids.get(eid, ())
        )
        home_near = bool(site_out) and bool(eng_out) and eng_out == site_out
        # lower = better: already in-area today, then fewer jobs, then home-near
        key = (0 if near_today else 1, n, 0 if home_near else 1)
        if best_key is None or key < best_key:
            best_key, suggested = key, eid

    suggested_reason = None
    if suggested is not None and best_key is not None:
        if best_key[0] == 0:
            suggested_reason = "already working this area today"
        elif best_key[2] == 0:
            suggested_reason = "based nearest & least busy"
        else:
            suggested_reason = "least busy that day"

    return {"date": day.isoformat(), "load": load, "slots": slots,
            "suggested_engineer_id": suggested, "suggested_reason": suggested_reason}


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
                "customer_org_id": s.get("organization_id"),
                "site_id": s.get("site_id") or "",
                "title": s.get("title") or "Preventative maintenance",
                "customer_name": s.get("customer_name") or "",
                "site_name": s.get("site_name") or "",
                "equipment_name": s.get("equipment_name") or "",
                "machine_count": s.get("machine_count", len(s.get("equipment_ids") or [])),
                "engineer": s.get("assigned_engineer_name") or "",
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
    req_service_type = (data.get("service_type") or "").strip()

    org_ids = await _customer_org_ids(operator)
    sched = await db.ppm_schedules.find_one(
        {"id": schedule_id, "organization_id": {"$in": org_ids}, "source": "service_desk"},
        {"_id": 0},
    )
    if not sched:
        raise HTTPException(404, "PPM schedule not found")

    # Preserve the schedule's own service type (incl. custom types like
    # "Fire Station Service" / "Treadmill Calibration"); only override when the
    # request explicitly sends a different one. No coercion to a 2-item enum.
    service_type = req_service_type or (sched.get("service_type") or "Preventative Maintenance Service")

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
        "checklist_items": sched.get("checklist_items") or [],
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
