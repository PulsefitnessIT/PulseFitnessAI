from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import uuid
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter

logger = logging.getLogger(__name__)
router = APIRouter()


CHECK_SHEET_TEMPLATES = {
    "Treadmills": [
        "All Areas Cleaned", "Hoover Underneath", "E-Stop Check",
        "Console + & - Keys Check", "Heart Rate Check", "Speed Test",
        "Incline Check", "Belt Aligned", "Power/Ethernet Cable Fitted OK",
        "TV Tuned/Internet Connected",
    ],
    "Upright & Recumbent Bikes": [
        "All Areas Cleaned", "Hoover Underneath", "Seat Adjustment Working",
        "Foot Straps & Pedals Check", "+ & - Keys Check", "Resistance Check",
        "Heart Rate Check", "Console Check", "Power Cable/Ethernet Cable Fitted OK",
        "TV Tuned/Internet Connected",
    ],
    "Cross Trainers": [
        "All Areas Cleaned", "Hoover Underneath", "Handles Move Smoothly",
        "Pedals Check", "+ & - Keys Check", "Resistance Check",
        "Heart Rate Check", "Console Check", "Power Cable/Ethernet Cable Fitted OK",
        "TV Tuned/Internet Connected",
    ],
    "Rowers & Ski-Ergs": [
        "All Areas Cleaned", "Hoover Underneath", "Foot Straps & Heel Lock Check",
        "Console Check/Batteries OK", "Console Keys Check",
        "Smooth Chain/Seat Rail - Lubricate If Required",
        "Heart Rate Check", "Resistance Check/Fan", "Hoover Fan",
        "Inspect Bungees and Drive Cords",
    ],
    "Group Cycles": [
        "All Areas Cleaned", "All Locking Levers/Knobs Checked",
        "Pedals Screwed In Tightly", "Toe Straps Secure",
        "Crank Feels Smooth", "Handlebars Check",
        "Console Batteries OK", "Speed Test", "Resistance Check",
    ],
    "Free Weights & Benches": [
        "Framework Dusted", "Upholstery Clean", "Clean Mirrors",
        "Wipe down Weight Plates", "Check Weight Bars for Defects",
        "Check Rubber Weight Covers", "Check & Clean Dumbbell Stack",
        "Lubricate Moving Parts", "Check Upholstery for Splits",
        "Tighten Weight Bolts",
    ],
    "Strength/Selectorised": [
        "All Areas Cleaned", "Hoover Around", "Check Upholstery for Splits",
        "Tighten Upholstery Bolts", "Lubricate Guiding Rods",
        "Lubricate Moving Parts When Needed", "Check all Cables & Pulleys",
        "Smooth Seat Movement", "Weight Pin Available & Can Select Each Weight",
        "Handles Move Smoothly",
    ],
    "StepMills & Steppers": [
        "All Areas Cleaned", "Hoover Underneath", "Steps Move Smoothly",
        "E-Stop Check", "+ & - Keys Check", "Speed Test",
        "Heart Rate Check", "Console Check", "Power Cable/Ethernet Cable Fitted OK",
        "TV Tuned/Internet Connected",
    ],
}


@router.get("/check-sheets/templates")
async def get_check_sheet_templates():
    return {"templates": CHECK_SHEET_TEMPLATES}


@router.post("/check-sheets/complete")
async def complete_check_sheet_legacy(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    sheet_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "completed_by": user.get('full_name'),
        "equipment_category": data.get('equipment_category') or data.get('template_name'),
        "template_name": data.get('template_name') or data.get('equipment_category'),
        "template_id": data.get('template_id'),
        "checks": data.get('checks', {}),
        "items": data.get('items', []),
        "notes": data.get('notes', ''),
        "date": data.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')),
        "completed_date": data.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.check_sheets.insert_one(sheet_doc)
    sheet_doc.pop('_id', None)
    return sheet_doc


@router.get("/check-sheets/history")
async def get_check_sheet_history(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    sheets = await db.check_sheets.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(200)

    completions = []
    for s in sheets:
        completions.append({
            "id": s.get("id"),
            "template_name": s.get("template_name") or s.get("equipment_category", "Unknown"),
            "completed_by": s.get("completed_by", "Unknown"),
            "completed_date": s.get("completed_date") or s.get("date", ""),
            "items": s.get("items") or [{"name": k, "checked": v} for k, v in (s.get("checks") or {}).items()],
            "notes": s.get("notes", ""),
            "created_at": s.get("created_at", "")
        })
    return {"completions": completions}


@router.get("/check-sheets/report")
async def get_check_sheet_report_main(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    sheets = await db.check_sheets.find(org_filter, {"_id": 0}).to_list(500)

    by_staff = {}
    for s in sheets:
        name = s.get('completed_by', 'Unknown')
        if name not in by_staff:
            by_staff[name] = {"count": 0, "last_completed": None, "sheets": {}}
        by_staff[name]["count"] += 1
        by_staff[name]["last_completed"] = s.get('date') or s.get('created_at')
        sheet = s.get('template_name') or s.get('equipment_category', 'Unknown')
        by_staff[name]["sheets"][sheet] = by_staff[name]["sheets"].get(sheet, 0) + 1

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = [s for s in sheets if s.get('created_at', '') >= week_ago]

    return {
        "by_staff": by_staff,
        "total_completions": len(sheets),
        "last_7_days": len(recent),
        "staff_count": len(by_staff),
    }


@router.post("/check-sheets/custom-template")
async def create_custom_template(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    template_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get('organization_id'),
        "name": data.get('name', ''),
        "equipment_type": (data.get('equipment_type') or '').strip(),
        "items": data.get('items', []),
        "created_by": user.get('full_name'),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.custom_check_templates.insert_one(template_doc)
    template_doc.pop('_id', None)
    return template_doc


@router.get("/check-sheets/custom-templates")
async def get_custom_templates(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    templates = await db.custom_check_templates.find(org_filter, {"_id": 0}).to_list(50)
    return {"templates": templates}


@router.put("/check-sheets/custom-template/{template_id}")
async def update_custom_template(template_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    result = await db.custom_check_templates.update_one(
        {"id": template_id, **org_filter},
        {"$set": {"name": data.get('name'), "items": data.get('items', []), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


@router.delete("/check-sheets/custom-template/{template_id}")
async def delete_custom_template(template_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    result = await db.custom_check_templates.delete_one({"id": template_id, **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


@router.get("/maintenance/templates")
async def get_maintenance_templates(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    templates = await db.custom_check_templates.find(org_filter, {"_id": 0}).to_list(50)
    return {"templates": templates}


@router.post("/maintenance/templates")
async def create_maintenance_template(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    template_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "name": data.get('name', 'Untitled'),
        "category": data.get('category', 'Custom'),
        # Iter 222 — optional assignment to a specific equipment type.
        # When set, this template replaces the built-in default checklist
        # for that equipment type in the Check Sheets grid.
        "equipment_type": (data.get('equipment_type') or '').strip(),
        "items": data.get('items', []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.custom_check_templates.insert_one(template_doc)
    template_doc.pop('_id', None)
    return template_doc


@router.delete("/maintenance/templates/{template_id}")
async def delete_maintenance_template(template_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    result = await db.custom_check_templates.delete_one({"id": template_id, **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


DEFAULT_MAINTENANCE_TASKS = [
        {"id": "1", "title": "All Areas Cleaned", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "2", "title": "Hoover Underneath", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "3", "title": "E-Stop Check", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "4", "title": "Console + & - Keys Check", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "5", "title": "Heart Rate Check", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "6", "title": "Speed Test", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "7", "title": "Incline Check", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "8", "title": "Belt Aligned", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "9", "title": "Power/Ethernet Cable Check", "frequency": "daily", "equipment": "Treadmills"},
        {"id": "10", "title": "All Areas Cleaned", "frequency": "daily", "equipment": "Exercise Bikes"},
        {"id": "11", "title": "Seat Adjustment Working", "frequency": "daily", "equipment": "Exercise Bikes"},
        {"id": "12", "title": "Foot Straps & Pedals Check", "frequency": "daily", "equipment": "Exercise Bikes"},
        {"id": "13", "title": "Resistance Check", "frequency": "daily", "equipment": "Exercise Bikes"},
        {"id": "14", "title": "Console Check", "frequency": "daily", "equipment": "Exercise Bikes"},
        {"id": "15", "title": "All Areas Cleaned", "frequency": "daily", "equipment": "Cross Trainers"},
        {"id": "16", "title": "Handles Move Smoothly", "frequency": "daily", "equipment": "Cross Trainers"},
        {"id": "17", "title": "Pedals Check", "frequency": "daily", "equipment": "Cross Trainers"},
        {"id": "18", "title": "Resistance Check", "frequency": "daily", "equipment": "Cross Trainers"},
        {"id": "19", "title": "All Areas Cleaned", "frequency": "daily", "equipment": "Rowers"},
        {"id": "20", "title": "Foot Straps & Heel Lock Check", "frequency": "daily", "equipment": "Rowers"},
        {"id": "21", "title": "Console Check", "frequency": "daily", "equipment": "Rowers"},
        {"id": "22", "title": "Inspect Bungees and Drive Cords", "frequency": "weekly", "equipment": "Rowers"},
        {"id": "23", "title": "Smooth Chain/Seat Rail - Lubricate", "frequency": "monthly", "equipment": "Rowers"},
        {"id": "24", "title": "All Areas Cleaned", "frequency": "daily", "equipment": "Strength Equipment"},
        {"id": "25", "title": "Check Upholstery for Splits", "frequency": "daily", "equipment": "Strength Equipment"},
        {"id": "26", "title": "Check all Cables & Pulleys", "frequency": "daily", "equipment": "Strength Equipment"},
        {"id": "27", "title": "Weight Pin Available", "frequency": "daily", "equipment": "Strength Equipment"},
        {"id": "28", "title": "Lubricate Guiding Rods", "frequency": "monthly", "equipment": "Strength Equipment"},
        {"id": "29", "title": "Tighten Upholstery Bolts", "frequency": "monthly", "equipment": "Strength Equipment"},
        {"id": "30", "title": "Framework Dusted", "frequency": "daily", "equipment": "Free Weights"},
        {"id": "31", "title": "Upholstery Clean", "frequency": "daily", "equipment": "Free Weights"},
        {"id": "32", "title": "Wipe down Weight Plates", "frequency": "daily", "equipment": "Free Weights"},
        {"id": "33", "title": "Check Weight Bars for Defects", "frequency": "weekly", "equipment": "Free Weights"},
        {"id": "34", "title": "Lubricate Moving Parts", "frequency": "monthly", "equipment": "Free Weights"},
]

VALID_FREQUENCIES = {"daily", "weekly", "monthly", "quarterly", "yearly"}


@router.get("/maintenance/tasks")
async def get_maintenance_tasks(user: dict = Depends(get_current_user)):
    """Scheduled maintenance tasks for the operator's org: built-in defaults
    (with any per-org frequency overrides applied) plus custom tasks the
    operator has added."""
    org_filter = get_organization_filter(user)
    prefs = await db.maintenance_tasks.find(org_filter, {"_id": 0}).to_list(500)
    overrides = {p["task_id"]: p["frequency"] for p in prefs if p.get("type") == "override"}
    custom = [
        {"id": p["id"], "title": p["title"], "frequency": p["frequency"],
         "equipment": p.get("equipment") or "General", "is_custom": True}
        for p in prefs if p.get("type") == "custom"
    ]
    tasks = []
    for d in DEFAULT_MAINTENANCE_TASKS:
        t = dict(d)
        if d["id"] in overrides:
            t["frequency"] = overrides[d["id"]]
        t["is_custom"] = False
        tasks.append(t)
    tasks.extend(custom)
    return {"tasks": tasks}


@router.post("/maintenance/tasks")
async def create_maintenance_task(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")
    freq = (data.get("frequency") or "daily").strip().lower()
    if freq not in VALID_FREQUENCIES:
        raise HTTPException(status_code=400, detail="Invalid frequency")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "organization_id": user.get("organization_id"),
        "type": "custom",
        "title": title[:200],
        "equipment": (data.get("equipment") or "General").strip()[:120],
        "frequency": freq,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.maintenance_tasks.insert_one(doc)
    doc.pop("_id", None)
    return {"id": doc["id"], "title": doc["title"], "frequency": doc["frequency"],
            "equipment": doc["equipment"], "is_custom": True}


@router.patch("/maintenance/tasks/{task_id}")
async def update_maintenance_task_frequency(task_id: str, data: Dict[str, Any],
                                            user: dict = Depends(get_current_user)):
    freq = (data.get("frequency") or "").strip().lower()
    if freq not in VALID_FREQUENCIES:
        raise HTTPException(status_code=400, detail="Invalid frequency")
    org_filter = get_organization_filter(user)
    # Custom task owned by the org → update it directly.
    custom = await db.maintenance_tasks.find_one({"id": task_id, "type": "custom", **org_filter})
    if custom:
        await db.maintenance_tasks.update_one(
            {"id": task_id}, {"$set": {"frequency": freq, "updated_at": datetime.now(timezone.utc).isoformat()}})
        return {"success": True, "id": task_id, "frequency": freq}
    # Otherwise treat as a built-in default → upsert a per-org frequency override.
    if not any(d["id"] == task_id for d in DEFAULT_MAINTENANCE_TASKS):
        raise HTTPException(status_code=404, detail="Task not found")
    await db.maintenance_tasks.update_one(
        {"organization_id": user.get("organization_id"), "type": "override", "task_id": task_id},
        {"$set": {"frequency": freq, "updated_at": datetime.now(timezone.utc).isoformat(),
                  "organization_id": user.get("organization_id"), "type": "override", "task_id": task_id}},
        upsert=True)
    return {"success": True, "id": task_id, "frequency": freq}


@router.delete("/maintenance/tasks/{task_id}")
async def delete_maintenance_task(task_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    result = await db.maintenance_tasks.delete_one({"id": task_id, "type": "custom", **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Custom task not found (built-in tasks cannot be deleted)")
    return {"success": True}
