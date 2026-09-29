"""PPM (Planned Preventive Maintenance) Engine.

Manages maintenance schedules per contract/SLA, auto-assigns tasks,
tracks completion, stores service certificates, and handles reminders.

Schedule frequency is driven by SLA tier or manual input:
- Gold/Platinum SLA = 1 service per year (anniversary of install date)
- Manual = user-defined frequency
"""

from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import uuid
import base64
import logging
import asyncio

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.module_guard import require_module_or_roles

logger = logging.getLogger(__name__)
# PPM is an Operations surface, also used by Service Desk (their PPM calendar)
# and MOD orgs. Guarded to Operations (+ service-desk / inventory / MOD via the
# guard); Memberships/Marketing/CRM-only staff are blocked server-side.
router = APIRouter(dependencies=[Depends(require_module_or_roles(("operations",)))])


# ── PPM Schedule CRUD ────────────────────────────────────────────

@router.get("/ppm/schedules")
async def list_schedules(user: dict = Depends(get_current_user)):
    """List all PPM schedules with their tasks embedded."""
    org_filter = get_organization_filter(user)
    schedules = await db.ppm_schedules.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(500)

    # Embed tasks into each schedule
    schedule_ids = [s["id"] for s in schedules]
    if schedule_ids:
        all_tasks = await db.ppm_tasks.find(
            {"schedule_id": {"$in": schedule_ids}}, {"_id": 0}
        ).sort("scheduled_date", 1).to_list(5000)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tasks_by_sched: dict = {}
        for t in all_tasks:
            if t.get("status") == "scheduled" and t.get("scheduled_date", "9999") < now_str:
                t["status"] = "overdue"
            tasks_by_sched.setdefault(t["schedule_id"], []).append(t)

        for s in schedules:
            s["tasks"] = tasks_by_sched.get(s["id"], [])

    return {"schedules": schedules}


@router.post("/ppm/schedules")
async def create_schedule(data: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create a new PPM schedule. Frequency from SLA tier or manual."""
    now = datetime.now(timezone.utc).isoformat()
    schedule = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "contract_id": data.get("contract_id"),
        "sla_tier": data.get("sla_tier", ""),
        "site_id": data.get("site_id"),
        "site_name": data.get("site_name", ""),
        "supplier_name": data.get("supplier_name", ""),
        "supplier_email": data.get("supplier_email", ""),
        "equipment_type": data.get("equipment_type", ""),
        "equipment_ids": data.get("equipment_ids", []),
        "install_date": data.get("install_date", ""),
        "frequency": data.get("frequency", "annual"),
        "source": data.get("source", "manual"),  # "sla" or "manual"
        "assigned_to": data.get("assigned_to", ""),
        "checklist_category": data.get("checklist_category", ""),
        "checklist_items": data.get("checklist_items", []),
        "certificates": [],
        "active": True,
        "created_by": user.get("full_name", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.ppm_schedules.insert_one(schedule)
    schedule.pop("_id", None)

    # Auto-generate first batch of tasks
    tasks = _generate_task_batch(schedule, count=3)
    if tasks:
        await db.ppm_tasks.insert_many(tasks)
        for t in tasks:
            t.pop("_id", None)
    schedule["tasks"] = tasks

    return schedule


@router.put("/ppm/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update a PPM schedule."""
    org_filter = get_organization_filter(user)
    allowed = {"title", "description", "frequency", "assigned_to",
               "checklist_items", "checklist_category", "equipment_ids",
               "site_id", "site_name", "contract_id", "sla_tier",
               "supplier_name", "supplier_email", "equipment_type",
               "install_date", "source", "active"}
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.ppm_schedules.update_one({"id": schedule_id, **org_filter}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Schedule not found")
    return {"success": True}


@router.delete("/ppm/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    await db.ppm_schedules.delete_one({"id": schedule_id, **org_filter})
    await db.ppm_tasks.delete_many({"schedule_id": schedule_id})
    return {"success": True}


# ── Certificate Upload ───────────────────────────────────────────

@router.post("/ppm/schedules/{schedule_id}/certificates")
async def upload_certificate(
    schedule_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a service certificate to a PPM schedule."""
    from utils.file_validation import validate_upload, MIME_IMAGES, MIME_OFFICE
    org_filter = get_organization_filter(user)
    schedule = await db.ppm_schedules.find_one({"id": schedule_id, **org_filter})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    contents = await file.read()
    ct = validate_upload(
        file_bytes=contents, filename=file.filename,
        allowed=MIME_IMAGES | MIME_OFFICE, max_size=10 * 1024 * 1024,
    )

    cert = {
        "id": str(uuid.uuid4()),
        "filename": file.filename or "certificate",
        "content_type": ct,
        "data": base64.b64encode(contents).decode("utf-8"),
        "uploaded_by": user.get("full_name", ""),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.ppm_schedules.update_one(
        {"id": schedule_id}, {"$push": {"certificates": cert}}
    )
    return {"success": True, "certificate_id": cert["id"], "filename": cert["filename"]}


@router.get("/ppm/schedules/{schedule_id}/certificates/{cert_id}")
async def download_certificate(schedule_id: str, cert_id: str, user: dict = Depends(get_current_user)):
    """Download a specific service certificate."""
    from fastapi.responses import Response
    org_filter = get_organization_filter(user)
    schedule = await db.ppm_schedules.find_one({"id": schedule_id, **org_filter}, {"_id": 0, "certificates": 1})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    for cert in (schedule.get("certificates") or []):
        if cert["id"] == cert_id:
            return Response(
                content=base64.b64decode(cert["data"]),
                media_type=cert.get("content_type", "application/pdf"),
                headers={"Content-Disposition": f"attachment; filename={cert.get('filename', 'certificate')}"}
            )
    raise HTTPException(404, "Certificate not found")


@router.delete("/ppm/schedules/{schedule_id}/certificates/{cert_id}")
async def delete_certificate(schedule_id: str, cert_id: str, user: dict = Depends(get_current_user)):
    """Delete a certificate from a PPM schedule."""
    org_filter = get_organization_filter(user)
    await db.ppm_schedules.update_one(
        {"id": schedule_id, **org_filter},
        {"$pull": {"certificates": {"id": cert_id}}}
    )
    return {"success": True}


# ── Task Generation ──────────────────────────────────────────────

def _get_freq_delta(frequency: str):
    return {
        "weekly": relativedelta(weeks=1),
        "monthly": relativedelta(months=1),
        "quarterly": relativedelta(months=3),
        "biannual": relativedelta(months=6),
        "annual": relativedelta(years=1),
    }.get(frequency, relativedelta(years=1))


def _generate_task_batch(schedule: dict, count: int = 3) -> list[dict]:
    """Generate upcoming PPM task records for a schedule."""
    freq = schedule.get("frequency", "annual")
    delta = _get_freq_delta(freq)

    # Start from install_date anniversary or now
    install = schedule.get("install_date")
    if install:
        try:
            base = datetime.strptime(install[:10], "%Y-%m-%d")
            # Find the next anniversary after today
            now = datetime.now(timezone.utc)
            while base < now:
                base = base + delta
        except (ValueError, TypeError):
            base = datetime.now(timezone.utc)
    else:
        base = datetime.now(timezone.utc)

    tasks = []
    current = base
    for _ in range(count):
        tasks.append({
            "id": str(uuid.uuid4()),
            "organization_id": schedule.get("organization_id"),
            "schedule_id": schedule["id"],
            "schedule_title": schedule.get("title", ""),
            "site_id": schedule.get("site_id"),
            "site_name": schedule.get("site_name", ""),
            "equipment_ids": schedule.get("equipment_ids", []),
            "assigned_to": schedule.get("assigned_to", ""),
            "checklist_items": schedule.get("checklist_items", []),
            "scheduled_date": current.strftime("%Y-%m-%d"),
            "status": "scheduled",
            "completed_date": None,
            "completed_by": None,
            "completion_notes": None,
            "checklist_results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        current = current + delta
    return tasks


# ── Per-site PPM backfill (batched + backgrounded) ───────────────
# PPMs are generated per SITE, only when a site becomes active — never as one
# giant 120k-asset sweep. Per-site work is naturally bounded (a venue has
# hundreds of assets, not the whole estate) and runs in the background,
# mirroring the sicon_sync_runs pattern: insert a run doc, kick off an asyncio
# task, poll by run_id — so the triggering request never blocks or times out.
# Idempotent: re-running a site skips equipment-types that already have an
# auto-backfill schedule.

async def run_site_ppm_backfill(org_id: str, site_id: str, run_id: str,
                                frequency: str = "annual", created_by: str = "") -> None:
    def _now():
        return datetime.now(timezone.utc).isoformat()
    counts = {"equipment_total": 0, "types": 0, "schedules_created": 0,
              "tasks_created": 0, "skipped_existing": 0}
    await db.ppm_backfill_runs.update_one(
        {"id": run_id}, {"$set": {"status": "running", "started_at": _now()}})
    try:
        site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0, "name": 1})
        site_name = (site or {}).get("name", "")
        # Group the site's equipment by type (one schedule per type listing its
        # equipment_ids) — keeps schedule count tiny even for a big venue.
        groups = []
        async for g in db.equipment.aggregate([
            {"$match": {"organization_id": org_id, "site_id": site_id}},
            {"$group": {"_id": {"$ifNull": ["$equipment_type", "Unspecified"]},
                        "ids": {"$push": "$id"},
                        "install": {"$min": "$purchase_date"}}},
        ]):
            groups.append(g)
        counts["types"] = len(groups)
        for g in groups:
            etype = g["_id"] or "Unspecified"
            ids = [i for i in (g.get("ids") or []) if i]
            counts["equipment_total"] += len(ids)
            existing = await db.ppm_schedules.find_one(
                {"organization_id": org_id, "site_id": site_id,
                 "equipment_type": etype, "source": "auto_backfill", "active": True},
                {"_id": 0, "id": 1})
            if existing:
                counts["skipped_existing"] += 1
                await db.ppm_backfill_runs.update_one({"id": run_id}, {"$set": {"counts": counts}})
                continue
            ts = _now()
            install = g.get("install")
            sched = {
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "title": f"{etype} PPM — {site_name}" if site_name else f"{etype} PPM",
                "description": "Auto-generated when the site was activated.",
                "contract_id": None,
                "sla_tier": "",
                "site_id": site_id,
                "site_name": site_name,
                "supplier_name": "",
                "supplier_email": "",
                "equipment_type": etype,
                "equipment_ids": ids,
                "install_date": install[:10] if isinstance(install, str) else "",
                "frequency": frequency,
                "source": "auto_backfill",
                "assigned_to": "",
                "checklist_category": "",
                "checklist_items": [],
                "certificates": [],
                "active": True,
                "created_by": created_by,
                "created_at": ts,
                "updated_at": ts,
            }
            await db.ppm_schedules.insert_one(sched)
            sched.pop("_id", None)
            counts["schedules_created"] += 1
            tasks = _generate_task_batch(sched, count=3)
            if tasks:
                await db.ppm_tasks.insert_many(tasks)
                for t in tasks:
                    t.pop("_id", None)
                counts["tasks_created"] += len(tasks)
            await db.ppm_backfill_runs.update_one({"id": run_id}, {"$set": {"counts": counts}})
        await db.ppm_backfill_runs.update_one(
            {"id": run_id}, {"$set": {"status": "completed", "finished_at": _now(), "counts": counts}})
    except Exception as e:
        logger.exception(f"PPM backfill failed for site {site_id}")
        await db.ppm_backfill_runs.update_one(
            {"id": run_id}, {"$set": {"status": "failed", "error": str(e),
                                      "finished_at": _now(), "counts": counts}})


async def kickoff_site_ppm_backfill(org_id: str, site_id: str, frequency: str = "annual",
                                    created_by: str = "") -> dict:
    """Queue a background PPM backfill for one site. Idempotent: if a run is
    already queued/running for the site, return it instead of starting another."""
    active = await db.ppm_backfill_runs.find_one(
        {"organization_id": org_id, "site_id": site_id, "status": {"$in": ["queued", "running"]}},
        {"_id": 0})
    if active:
        return {"run_id": active["id"], "status": active["status"], "already_running": True}
    run_id = str(uuid.uuid4())
    await db.ppm_backfill_runs.insert_one({
        "id": run_id, "organization_id": org_id, "site_id": site_id,
        "status": "queued", "counts": {}, "started_at": None, "finished_at": None,
        "created_by": created_by, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(run_site_ppm_backfill(org_id, site_id, run_id, frequency, created_by))
    return {"run_id": run_id, "status": "queued"}


@router.post("/ppm/backfill/site/{site_id}")
async def start_site_ppm_backfill(site_id: str, data: dict = Body(default={}),
                                  user: dict = Depends(get_current_user)):
    """Load a site's PPM schedules in the background — call when a site becomes
    active. Returns a run_id to poll; never blocks on the actual generation."""
    org_id = user.get("organization_id")
    site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0, "id": 1})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    frequency = (data or {}).get("frequency", "annual")
    return await kickoff_site_ppm_backfill(org_id, site_id, frequency, user.get("full_name", ""))


@router.get("/ppm/backfill/runs/{run_id}")
async def get_ppm_backfill_run(run_id: str, user: dict = Depends(get_current_user)):
    """Poll a PPM backfill run's progress/status."""
    doc = await db.ppm_backfill_runs.find_one(
        {"id": run_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Backfill run not found")
    return doc


@router.post("/ppm/schedules/{schedule_id}/generate-tasks")
async def generate_tasks(schedule_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)):
    """Generate upcoming PPM tasks for a schedule."""
    org_filter = get_organization_filter(user)
    schedule = await db.ppm_schedules.find_one({"id": schedule_id, **org_filter}, {"_id": 0})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    count = data.get("count", 3)
    tasks = _generate_task_batch(schedule, count)

    # Dedupe — don't create if same schedule+date already exists
    created = []
    for task in tasks:
        existing = await db.ppm_tasks.find_one({"schedule_id": schedule_id, "scheduled_date": task["scheduled_date"]})
        if not existing:
            await db.ppm_tasks.insert_one(task)
            task.pop("_id", None)
            created.append(task)

    return {"created": len(created), "tasks": created}


# ── Task Actions ─────────────────────────────────────────────────

@router.get("/ppm/tasks")
async def list_ppm_tasks(
    status: str = "",
    schedule_id: str = "",
    limit: int = 500,
    user: dict = Depends(get_current_user),
):
    """List PPM tasks for the caller's organisation. Scheduled-but-past-due tasks
    are surfaced with status='overdue' so the UI can flag them without a separate query."""
    org_filter = get_organization_filter(user)
    query: dict = {**org_filter}
    if status:
        query["status"] = status
    if schedule_id:
        query["schedule_id"] = schedule_id

    tasks = await db.ppm_tasks.find(query, {"_id": 0}).sort("scheduled_date", 1).to_list(limit)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for t in tasks:
        if t.get("status") == "scheduled" and t.get("scheduled_date", "") < today:
            t["status"] = "overdue"

    return {"tasks": tasks, "total": len(tasks)}


@router.patch("/ppm/tasks/{task_id}")
async def update_task(task_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update a PPM task (complete, add notes, etc.)."""
    org_filter = get_organization_filter(user)
    task = await db.ppm_tasks.find_one({"id": task_id, **org_filter}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")

    updates: dict = {}
    if data.get("status"):
        updates["status"] = data["status"]
        if data["status"] == "completed":
            updates["completed_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            updates["completed_by"] = user.get("full_name", "")
    if "completion_notes" in data:
        updates["completion_notes"] = data["completion_notes"]
    if "checklist_results" in data:
        updates["checklist_results"] = data["checklist_results"]
    if "assigned_to" in data:
        updates["assigned_to"] = data["assigned_to"]

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.ppm_tasks.update_one({"id": task_id}, {"$set": updates})
    return {"success": True}


# ── PPM Summary ──────────────────────────────────────────────────

@router.get("/ppm/summary")
async def ppm_summary(user: dict = Depends(get_current_user)):
    """Quick summary of PPM status."""
    org_filter = get_organization_filter(user)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total = await db.ppm_tasks.count_documents(org_filter)
    completed = await db.ppm_tasks.count_documents({**org_filter, "status": "completed"})
    scheduled = await db.ppm_tasks.count_documents({**org_filter, "status": "scheduled"})
    overdue = await db.ppm_tasks.count_documents({
        **org_filter, "status": "scheduled", "scheduled_date": {"$lt": now_str}
    })
    upcoming_90d = await db.ppm_tasks.count_documents({
        **org_filter, "status": "scheduled",
        "scheduled_date": {"$gte": now_str, "$lte": (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")}
    })
    schedules = await db.ppm_schedules.count_documents({**org_filter, "active": True})

    return {
        "active_schedules": schedules,
        "total_tasks": total,
        "completed": completed,
        "scheduled": scheduled,
        "overdue": overdue,
        "upcoming_90d": upcoming_90d,
        "compliance_pct": round((completed / max(total, 1)) * 100, 1),
    }


# ── Default Checklists (from Pulse Fitness service document) ─────

@router.get("/ppm/checklists")
async def get_default_checklists():
    """Return the standard PPM service checklists by equipment category."""
    return {"checklists": DEFAULT_CHECKLISTS}


DEFAULT_CHECKLISTS = {
    "Treadmill": [
        "Place treadmill on incline, disconnect power",
        "Remove lid, vacuum inside main body",
        "Check all wires are correct and in good working order",
        "Inspect control board",
        "Check drive belt - Replace if needed",
        "Check pulley system",
        "Check belt condition",
        "Realign belt - If needed",
        "Check belt tension",
        "Check bed condition",
        "Lubricate belt if needed",
        "Clean rollers",
        "Check incline height is correct",
        "Ensure no free play on all joint assemblies",
        "Check machine stability - Adjust feet if required",
        "Check all entertainment options are working",
        "Check E-Stop",
        "Check all fixings and handles",
        "Check quick keys",
        "Check console is on latest software version",
        "Console - Inspect power pack",
        "Function test - Run on full incline at full speed for 5 mins",
    ],
    "X-Trainer": [
        "Remove side cover, vacuum inside main body",
        "Check all wires are correct and in good working order",
        "Inspect LCB and SPA board",
        "Check belt and tension",
        "Check pulley system",
        "Check crank arms - no movement or slipping when pedalling",
        "Check pedals and straps",
        "Ensure no free play on all joint assemblies",
        "Check machine stability - Adjust feet if required",
        "Check foot plate movement",
        "Check all entertainment options are working",
        "Check all fixings and handles",
        "Check quick keys",
        "Check console is on latest software version",
        "Console - Inspect power pack",
        "Function test",
    ],
    "Stepper": [
        "Remove side cover, vacuum inside main body",
        "Check all wires are correct and in good working order",
        "Inspect LCB and SPA board",
        "Check belts and springs",
        "Check pulley system",
        "Ensure no free play on all joint assemblies",
        "Check machine stability",
        "Check all entertainment options are working",
        "Check all fixings and handles",
        "Check quick keys",
        "Check console is on latest software version",
        "Console - Inspect power pack",
        "Function test",
    ],
    "U-Cycle / R-Cycle": [
        "Remove side cover, vacuum inside main body",
        "Check all wires are correct and in good working order",
        "Inspect LCB and SPA board",
        "Check belt",
        "Check pulley system",
        "Check crank arms - no movement or slipping when pedalling",
        "Check pedals and straps",
        "Ensure no free play on all joint assemblies",
        "Check machine stability - Adjust feet if required",
        "Check seat movement",
        "Check all entertainment options are working",
        "Check all fixings and handles",
        "Check quick keys",
        "Check console is on latest software version",
        "Console - Inspect power pack",
        "Function test",
    ],
    "L-Train": [
        "Remove top cover, vacuum inside main body",
        "Check all wires are correct and in good working order",
        "Inspect LCB and SPA board",
        "Check crank arms - no movement or slipping when pedalling",
        "Check pedals",
        "Ensure no free play on all joint assemblies",
        "Check machine stability - Adjust feet if required",
        "Check all entertainment options are working",
        "Check all fixings and handles",
        "Check quick keys",
        "Check console is on latest software version",
        "Console - Inspect power pack",
        "Function test",
    ],
    "Group Cycle": [
        "Check/adjust resistance",
        "Check sliding handlebars",
        "Check grub screw",
        "Lubricate handlebar stem",
        "Check crank arms - no movement or slipping when pedalling",
        "Check pedals and straps",
        "Check brake pads - Replace if needed",
        "Check seat adjustment",
        "Lubricate seat stem",
        "Check feet - Adjust/Replace if needed",
    ],
    "Resistance": [
        "Check barrel pins",
        "Check belt condition and swivel movement",
        "Check bronze brushes - Replace if required",
        "Check centralization",
        "Check movement in shafts - Adjust/replace as required",
        "Check tightness of all bolts",
        "Check/Lubricate linear/rod end bearings",
        "Lubricate case hardened shafts",
        "Check console",
        "Silicone seat stems",
        "Test for smooth function",
        "Visually inspect clamps and fasteners",
        "Function test",
    ],
}


# ── PPM Reminders Engine ─────────────────────────────────────────

def _init_resend_api():
    """Import resend and set API key. Returns the resend module or None if unconfigured."""
    try:
        import resend
        import os
        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            return None
        resend.api_key = api_key
        return resend
    except ImportError:
        return None


def _render_ppm_reminder_html(schedule: dict, task: dict, months_until: int, urgency: str) -> str:
    """Return the reminder email HTML body."""
    site_name = schedule.get("site_name", "Site")
    supplier_name = schedule.get("supplier_name", "Supplier")
    equip_type = schedule.get("equipment_type", "Equipment")
    sched_date = task.get("scheduled_date", "TBC")
    plural = "s" if months_until != 1 else ""
    return f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;">
  <div style="background:#0A0A0A;padding:20px 28px;">
    <h1 style="color:#fff;font-size:16px;margin:0;">{urgency}PPM Service Visit Reminder</h1>
    <p style="color:#888;font-size:12px;margin:4px 0 0;">via Pulse Fitness AI</p>
  </div>
  <div style="padding:28px;">
    <p style="color:#111;font-size:14px;line-height:1.5;">Dear {supplier_name},</p>
    <p style="color:#111;font-size:14px;line-height:1.5;">This is a reminder that a <strong>Planned Preventive Maintenance</strong> visit is due in approximately <strong>{months_until} month{plural}</strong>.</p>
    <div style="margin:16px 0;padding:16px;background:#F9FAFB;border-radius:8px;border-left:4px solid #3B82F6;">
      <p style="margin:0 0 8px;font-size:13px;color:#666;"><strong>Site:</strong> {site_name}</p>
      <p style="margin:0 0 8px;font-size:13px;color:#666;"><strong>Equipment:</strong> {equip_type}</p>
      <p style="margin:0 0 8px;font-size:13px;color:#666;"><strong>Schedule:</strong> {schedule.get("title", "PPM Service")}</p>
      <p style="margin:0;font-size:13px;color:#666;"><strong>Due Date:</strong> {sched_date}</p>
    </div>
    <p style="color:#111;font-size:14px;line-height:1.5;">Please contact us to arrange the visit at your earliest convenience.</p>
  </div>
  <div style="padding:14px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;">
    <p style="margin:0;font-size:11px;color:#999;">Sent via Pulse Fitness AI — Equipment Management Platform</p>
  </div>
</div>'''


async def _dispatch_ppm_reminder_email(resend_mod, schedule: dict, task: dict,
                                       months_until: int, supplier_email: str) -> bool:
    """Fire the reminder email. Returns True on success."""
    site_name = schedule.get("site_name", "Site")
    equip_type = schedule.get("equipment_type", "Equipment")
    sched_date = task.get("scheduled_date", "TBC")
    urgency = "URGENT: " if months_until <= 1 else ""
    html = _render_ppm_reminder_html(schedule, task, months_until, urgency)
    try:
        import asyncio
        await asyncio.to_thread(resend_mod.Emails.send, {
            "from": f"{site_name} <faults@service.pulsefitness.ai>",
            "to": [supplier_email],
            "subject": f"{urgency}PPM Service Due {sched_date} — {equip_type} at {site_name}",
            "html": html,
        })
        return True
    except Exception as e:
        logger.warning(f"PPM reminder email failed: {e}")
        return False


async def _send_ppm_reminder(schedule: dict, task: dict, months_until: int) -> bool:
    """Send email reminder to supplier about upcoming PPM visit."""
    resend_mod = _init_resend_api()
    if resend_mod is None:
        return False
    supplier_email = schedule.get("supplier_email")
    if not supplier_email:
        return False
    return await _dispatch_ppm_reminder_email(resend_mod, schedule, task, months_until, supplier_email)


def _reminder_window_months(days_until: int) -> int | None:
    """Return 3/2/1 months if within reminder window, else None."""
    if 85 <= days_until <= 95:
        return 3
    if 55 <= days_until <= 65:
        return 2
    if 25 <= days_until <= 35:
        return 1
    return None


def _ppm_days_until(sched_date: str, now: datetime) -> int | None:
    """Parse task's scheduled date and compute days until. Return None on bad date."""
    if not sched_date:
        return None
    try:
        due = datetime.strptime(sched_date, "%Y-%m-%d")
    except ValueError:
        return None
    return (due - now).days


async def _process_ppm_task(task: dict, now: datetime) -> bool:
    """Send PPM reminder for a task if in window and not already sent. Returns True if sent."""
    days_until = _ppm_days_until(task.get("scheduled_date", ""), now)
    if days_until is None:
        return False
    months_until = _reminder_window_months(days_until)
    if months_until is None:
        return False
    reminder_key = f"reminder_{months_until}m_sent"
    if task.get(reminder_key):
        return False
    schedule = await db.ppm_schedules.find_one({"id": task.get("schedule_id")}, {"_id": 0})
    if not schedule or not schedule.get("supplier_email"):
        return False
    if not await _send_ppm_reminder(schedule, task, months_until):
        return False
    await db.ppm_tasks.update_one(
        {"id": task["id"]},
        {"$set": {reminder_key: datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"PPM reminder sent: {months_until}m before {task['scheduled_date']} to {schedule['supplier_email']}")
    return True


@router.post("/ppm/send-reminders")
async def send_ppm_reminders(user: dict = Depends(get_current_user)):
    """Check all upcoming PPM tasks and send 3/2/1 month reminders to suppliers.
    Called manually or via scheduled job."""
    org_filter = get_organization_filter(user)
    now = datetime.now(timezone.utc)

    cutoff = (now + timedelta(days=95)).strftime("%Y-%m-%d")
    tasks = await db.ppm_tasks.find({
        **org_filter,
        "status": "scheduled",
        "scheduled_date": {"$lte": cutoff, "$gte": now.strftime("%Y-%m-%d")},
    }, {"_id": 0}).to_list(500)

    sent_count = 0
    for task in tasks:
        if await _process_ppm_task(task, now):
            sent_count += 1

    return {"sent": sent_count, "checked": len(tasks)}
