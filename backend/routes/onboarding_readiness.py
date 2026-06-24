"""Module readiness — wires onboarding checklists to LIVE module data.

For a given onboarding project (and its linked organisation) we count real
records across the existing collections to decide whether each module is
"ready". Nothing is duplicated — these are read-only counts over the live
data, plus an opt-in sync that ticks matching checklist steps complete.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.pulse_master_admin import _require_pulse_or_master

logger = logging.getLogger(__name__)
router = APIRouter()

MULTI = {"multi_site", "enterprise", "franchise"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# check tuple: (key, label, collection, extra_filter, required)
READINESS_AREAS = {
    "crm": {
        "label": "CRM",
        "checks": [
            ("contacts", "Contacts imported", "crm_contacts", {}, True),
            ("pipeline", "CRM pipeline configured", "crm_pipelines", {}, False),
            ("users", "Users assigned", "users", {}, True),
        ],
    },
    "service_desk": {
        "label": "Service Desk",
        "checks": [
            ("sites", "Sites added", "sites", {}, True),
            ("assets", "Assets imported", "equipment", {}, True),
            ("suppliers", "Suppliers / service providers", "suppliers", {}, False),
            ("jobs", "Faults / service jobs present", "issues", {}, False),
        ],
    },
    "memberships": {
        "label": "Memberships",
        "checks": [
            ("membership_types", "Membership types created", "membership_plans", {}, True),
            ("members", "Members imported", "members", {}, True),
            ("classes", "Classes configured", "class_templates", {}, False),
        ],
    },
    "marketing": {
        "label": "Marketing",
        "checks": [
            ("segments", "Segments created", "comms_segments", {}, False),
            ("campaigns", "Campaign templates", "marketing_campaigns", {}, False),
        ],
    },
    "engineer": {
        "label": "Engineer App",
        "checks": [
            ("engineers", "Engineers created", "users", {"role": "engineer"}, True),
            ("regions", "Service regions / sites", "sites", {}, False),
        ],
    },
    "stock": {
        "label": "Stock / Parts",
        "checks": [
            ("parts", "Parts imported", "parts", {}, True),
        ],
    },
}


def _areas_for(project: dict) -> list:
    mods = set(project.get("modules") or [])
    ctype = project.get("customer_type")
    areas = []
    if "crm" in mods or ctype in {"b2b", "service_co"}:
        areas.append("crm")
    if "operations" in mods or ctype in MULTI | {"single_site", "service_co"}:
        areas.append("service_desk")
    if "memberships" in mods:
        areas.append("memberships")
    if "marketing" in mods:
        areas.append("marketing")
    if ctype == "service_co":
        areas += ["engineer", "stock"]
    return areas


async def _count(collection: str, org_id: str, extra: dict) -> int:
    try:
        q = {"organization_id": org_id, **extra}
        return await db[collection].count_documents(q)
    except Exception:
        logger.exception("readiness count failed for %s", collection)
        return 0


async def _compute(project: dict) -> dict:
    org_id = project.get("organization_id")
    out = []
    if not org_id:
        return {"linked": False, "areas": []}
    # marketing audience = contacts + members (special: at least one to market to)
    for area in _areas_for(project):
        spec = READINESS_AREAS[area]
        checks = []
        for key, label, coll, extra, required in spec["checks"]:
            n = await _count(coll, org_id, extra)
            checks.append({"key": key, "label": label, "count": n, "ok": n > 0, "required": required})
        if area == "marketing":
            aud = await _count("crm_contacts", org_id, {}) + await _count("members", org_id, {})
            checks.insert(0, {"key": "audience", "label": "Audience to market to", "count": aud, "ok": aud > 0, "required": True})
        ready = all(c["ok"] for c in checks if c["required"])
        out.append({"area": area, "label": spec["label"], "ready": ready, "checks": checks})
    ready_count = sum(1 for a in out if a["ready"])
    return {"linked": True, "areas": out, "ready_count": ready_count, "total_areas": len(out)}


# step.key (checklist) → readiness predicate keyed by area+check
_STEP_SIGNALS = {
    "contacts": ("crm_contacts", {}),
    "members": ("members", {}),
    "assets": ("equipment", {}),
    "primary_site": ("sites", {}),
    "sites": ("sites", {}),
    "site_hierarchy": ("sites", {}),
    "primary_users": ("users", {}),
    "membership_types": ("membership_plans", {}),
    "engineers": ("users", {"role": "engineer"}),
    "crm_pipeline": ("crm_pipelines", {}),
    "stock": ("parts", {}),
}


@router.get("/onboarding/projects/{project_id}/readiness")
async def get_readiness(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    proj = await db.onboarding_projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return await _compute(proj)


@router.post("/onboarding/projects/{project_id}/readiness/sync")
async def sync_readiness(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Tick checklist steps complete where live data now satisfies them.
    Only advances steps — never downgrades manual progress."""
    _require_pulse_or_master(user)
    proj = await db.onboarding_projects.find_one({"id": project_id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    org_id = proj.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Link an organisation to this project before syncing live data")

    checklist = proj.get("checklist", [])
    advanced = []
    for step in checklist:
        sig = _STEP_SIGNALS.get(step.get("key"))
        if not sig:
            continue
        coll, extra = sig
        if step.get("status") == "complete":
            continue
        if await _count(coll, org_id, extra) > 0:
            step["status"] = "complete"
            advanced.append(step["key"])

    if advanced:
        await db.onboarding_projects.update_one(
            {"id": project_id}, {"$set": {"checklist": checklist, "updated_at": _now()}}
        )
        try:
            await db.onboarding_audit_events.insert_one({
                "id": str(uuid.uuid4()), "project_id": project_id, "action": "readiness_synced",
                "detail": {"advanced": advanced}, "actor_email": user.get("email"), "at": _now(),
            })
        except Exception:
            logger.exception("readiness sync audit failed")

    proj = await db.onboarding_projects.find_one({"id": project_id}, {"_id": 0})
    readiness = await _compute(proj)
    return {"advanced": advanced, "project": proj, "readiness": readiness}
