"""Onboarding Projects — the orchestration backbone for customer setup.

An *onboarding project* is a thin tracking layer that sits ON TOP of the
existing platform records. It NEVER duplicates customers, sites, users,
assets, contacts, members, staff, contracts or imports — it only references
an existing `organization_id` and tracks progress, a checklist, the business
profile and the go-live review.

Collections:
  • onboarding_projects      — one doc per customer onboarding
  • onboarding_audit_events  — immutable trail of every onboarding action

All endpoints are gated to Pulse / Master admins.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.pulse_master_admin import _require_pulse_or_master, MASTER_ADMIN_EMAIL, PULSE_ROLE

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin_no_desk(user: dict) -> None:
    """Stricter gate for DESTRUCTIVE onboarding actions (permanent delete /
    bulk purge). Master/Pulse admins only — Service Desk agents are excluded
    (they may import equipment, but must not irreversibly wipe onboarding
    records + audit trail)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    if user.get("role") == PULSE_ROLE or user.get("is_pulse_admin"):
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


# ── Customer types & progressive-disclosure step catalogue ────────────────

CUSTOMER_TYPES = [
    {"id": "single_site",  "label": "Single-site gym / studio"},
    {"id": "multi_site",   "label": "Multi-site operator"},
    {"id": "enterprise",   "label": "Enterprise organisation"},
    {"id": "franchise",    "label": "Franchise / group operator"},
    {"id": "service_co",   "label": "Service company"},
    {"id": "b2b",          "label": "B2B customer"},
    {"id": "supplier",     "label": "Supplier / partner organisation"},
    {"id": "demo",         "label": "Demo / trial customer"},
    {"id": "internal",     "label": "Internal / test account"},
]
CUSTOMER_TYPE_IDS = {t["id"] for t in CUSTOMER_TYPES}

MULTI = {"multi_site", "enterprise", "franchise"}


def _step(key, label, group, *, optional=False):
    return {"key": key, "label": label, "group": group, "optional": optional}


def build_checklist(customer_type: str, modules: list) -> list:
    """Return the ordered checklist for a customer type + selected modules.

    Progressive disclosure: only steps relevant to the type/modules appear.
    """
    mods = set(modules or [])
    steps = [
        _step("business_profile", "Capture business profile", "Profile"),
    ]

    # Sites
    if customer_type in MULTI:
        steps += [
            _step("site_hierarchy", "Define site hierarchy (regions / sites)", "Sites"),
            _step("sites", "Add or import sites", "Sites"),
            _step("regional_managers", "Assign regional / site managers", "Sites"),
            _step("site_permissions", "Configure site-level permissions", "Sites", optional=True),
        ]
    elif customer_type not in {"supplier", "b2b"}:
        steps += [_step("primary_site", "Add the primary site", "Sites")]

    # Users
    steps += [_step("primary_users", "Invite primary users", "Users")]

    # Data / module steps (progressive on selected modules)
    if "crm" in mods or customer_type in {"b2b", "service_co"}:
        steps += [
            _step("contacts", "Import contacts", "Data"),
            _step("crm_pipeline", "Configure CRM pipeline & tags", "Modules", optional=True),
        ]
    if "memberships" in mods:
        steps += [
            _step("membership_types", "Create membership types", "Modules"),
            _step("members", "Import members", "Data"),
        ]
    if "operations" in mods or customer_type in {"single_site", "multi_site", "enterprise", "franchise", "service_co"}:
        steps += [_step("assets", "Import assets / equipment", "Data", optional=(customer_type == "b2b"))]
    if customer_type == "service_co":
        steps += [
            _step("engineers", "Set up engineers & regions", "Modules"),
            _step("service_desk", "Configure Service Desk (job types, SLA)", "Modules"),
            _step("stock", "Import stock / parts", "Data", optional=True),
        ]
    if "marketing" in mods:
        steps += [_step("marketing_setup", "Marketing: consent, segments, sender domain", "Modules", optional=True)]

    steps += [
        _step("contracts", "Set up contracts", "Modules", optional=True),
        _step("reporting", "Configure reporting", "Modules", optional=True),
        _step("go_live_review", "Complete go-live review", "Go-Live"),
    ]

    # Materialise with ids + default status
    out = []
    for s in steps:
        out.append({
            "id": str(uuid.uuid4()),
            "key": s["key"],
            "label": s["label"],
            "group": s["group"],
            "optional": s["optional"],
            "status": "not_started",
            "owner": None,
            "due_date": None,
            "notes": "",
        })
    return out


VALID_STATUSES = {
    "not_started", "in_progress", "waiting_customer", "waiting_admin",
    "blocked", "ready_for_review", "complete",
}


# ── Models ────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    customer_name: str
    customer_type: str
    modules: list = Field(default_factory=list)
    organization_id: Optional[str] = None
    profile: dict = Field(default_factory=dict)
    owner: Optional[str] = None
    cs_owner: Optional[str] = None
    support_level: Optional[str] = None
    go_live_target: Optional[str] = None


class ProjectUpdate(BaseModel):
    customer_name: Optional[str] = None
    modules: Optional[list] = None
    organization_id: Optional[str] = None
    profile: Optional[dict] = None
    owner: Optional[str] = None
    cs_owner: Optional[str] = None
    support_level: Optional[str] = None
    go_live_target: Optional[str] = None
    status: Optional[str] = None


class StepUpdate(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _progress(project: dict) -> dict:
    checklist = project.get("checklist", [])
    required = [s for s in checklist if not s.get("optional")]
    done = [s for s in checklist if s.get("status") == "complete"]
    req_done = [s for s in required if s.get("status") == "complete"]
    blocked = [s for s in checklist if s.get("status") == "blocked"]
    pct = round(len(req_done) / len(required) * 100) if required else 0
    return {
        "percent": pct,
        "required_total": len(required),
        "required_complete": len(req_done),
        "total": len(checklist),
        "complete": len(done),
        "blocked": len(blocked),
        "missing": [s["label"] for s in required if s.get("status") != "complete"],
    }


def _present(project: dict) -> dict:
    project.pop("_id", None)
    project["progress"] = _progress(project)
    return project


async def _audit(project_id: str, user: dict, action: str, detail: dict | None = None) -> None:
    try:
        await db.onboarding_audit_events.insert_one({
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "action": action,
            "detail": detail or {},
            "actor_email": user.get("email"),
            "actor_id": user.get("id"),
            "at": _now(),
        })
    except Exception:  # audit must never break the request
        logger.exception("onboarding audit write failed")


# ── Reference data ──────────────────────────────────────────────────────────

@router.get("/onboarding/customer-types")
async def list_customer_types(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    return {"types": CUSTOMER_TYPES}


# ── Projects CRUD ────────────────────────────────────────────────────────────

@router.get("/onboarding/projects")
async def list_projects(
    status: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    q: dict = {}
    if status:
        q["status"] = status
    if customer_type:
        q["customer_type"] = customer_type
    if owner:
        q["owner"] = owner
    docs = await db.onboarding_projects.find(q).sort("created_at", -1).to_list(500)
    return {"projects": [_present(d) for d in docs]}


@router.post("/onboarding/projects")
async def create_project(body: ProjectCreate, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    if body.customer_type not in CUSTOMER_TYPE_IDS:
        raise HTTPException(status_code=400, detail="Unknown customer type")

    # No duplication: if linking an existing org, verify it exists and that a
    # project isn't already tracking it.
    if body.organization_id:
        org = await db.organizations.find_one({"id": body.organization_id}, {"_id": 0, "id": 1, "name": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organisation not found")
        existing = await db.onboarding_projects.find_one(
            {"organization_id": body.organization_id, "status": {"$ne": "archived"}}, {"_id": 0, "id": 1}
        )
        if existing:
            raise HTTPException(status_code=409, detail="An onboarding project already exists for this organisation")

    profile = dict(body.profile or {})
    if body.go_live_target:
        profile.setdefault("go_live_target", body.go_live_target)

    project = {
        "id": str(uuid.uuid4()),
        "customer_name": body.customer_name.strip(),
        "customer_type": body.customer_type,
        "modules": body.modules or [],
        "organization_id": body.organization_id,
        "profile": profile,
        "owner": body.owner,
        "cs_owner": body.cs_owner,
        "support_level": body.support_level,
        "go_live_target": body.go_live_target,
        "status": "in_progress",
        "checklist": build_checklist(body.customer_type, body.modules or []),
        "go_live": {"approved": False, "approved_by": None, "approved_at": None, "summary": None},
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("email"),
    }
    await db.onboarding_projects.insert_one(dict(project))
    await _audit(project["id"], user, "project_created",
                 {"customer_type": body.customer_type, "modules": body.modules})
    return _present(project)


@router.get("/onboarding/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_projects.find_one({"id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return _present(doc)


@router.patch("/onboarding/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_projects.find_one({"id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    updates: dict = {"updated_at": _now()}
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in VALID_STATUSES | {"archived"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    # Re-link to an org → guard against duplicates
    if data.get("organization_id") and data["organization_id"] != doc.get("organization_id"):
        clash = await db.onboarding_projects.find_one(
            {"organization_id": data["organization_id"], "id": {"$ne": project_id}, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409, detail="Another project already tracks this organisation")
    for k in ("customer_name", "modules", "organization_id", "owner", "cs_owner",
              "support_level", "go_live_target", "status"):
        if k in data:
            updates[k] = data[k]
    if "profile" in data:
        merged = dict(doc.get("profile") or {})
        merged.update(data["profile"] or {})
        updates["profile"] = merged
    # Modules changed → reconcile checklist, preserving existing step statuses by key
    if "modules" in data:
        prior = {s["key"]: s for s in doc.get("checklist", [])}
        fresh = build_checklist(doc["customer_type"], data["modules"] or [])
        for s in fresh:
            if s["key"] in prior:
                old = prior[s["key"]]
                s.update({k: old[k] for k in ("status", "owner", "due_date", "notes") if k in old})
        updates["checklist"] = fresh

    await db.onboarding_projects.update_one({"id": project_id}, {"$set": updates})
    await _audit(project_id, user, "project_updated", {"fields": list(data.keys())})
    doc.update(updates)
    return _present(doc)


@router.patch("/onboarding/projects/{project_id}/checklist/{step_id}")
async def update_step(project_id: str, step_id: str, body: StepUpdate, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_projects.find_one({"id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    checklist = doc.get("checklist", [])
    step = next((s for s in checklist if s["id"] == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid step status")
    before = {k: step.get(k) for k in data}
    step.update(data)
    await db.onboarding_projects.update_one(
        {"id": project_id}, {"$set": {"checklist": checklist, "updated_at": _now()}}
    )
    await _audit(project_id, user, "step_updated",
                 {"step": step["key"], "before": before, "after": data})
    doc["checklist"] = checklist
    return _present(doc)


@router.post("/onboarding/projects/{project_id}/go-live")
async def approve_go_live(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_projects.find_one({"id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    prog = _progress(doc)
    if prog["missing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot go live — {len(prog['missing'])} required step(s) incomplete: {', '.join(prog['missing'][:5])}",
        )
    summary = {
        "customer_name": doc.get("customer_name"),
        "customer_type": doc.get("customer_type"),
        "modules": doc.get("modules", []),
        "organization_id": doc.get("organization_id"),
        "completed_steps": [s["label"] for s in doc.get("checklist", []) if s.get("status") == "complete"],
        "approved_at": _now(),
        "approved_by": user.get("email"),
    }
    await db.onboarding_projects.update_one(
        {"id": project_id},
        {"$set": {
            "status": "complete",
            "go_live": {"approved": True, "approved_by": user.get("email"), "approved_at": summary["approved_at"], "summary": summary},
            "updated_at": _now(),
        }},
    )
    await _audit(project_id, user, "go_live_approved", {"summary": summary})
    doc = await db.onboarding_projects.find_one({"id": project_id})
    return _present(doc)


@router.delete("/onboarding/projects/{project_id}")
async def archive_project(
    project_id: str,
    permanent: bool = Query(False),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_projects.find_one({"id": project_id}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    if permanent:
        # Hard-delete the onboarding TRACKING project only. This never touches
        # the underlying organisation/customer records — it just removes the
        # onboarding checklist entry (used to clear out test/demo projects).
        _require_admin_no_desk(user)  # destructive → full admin only
        await db.onboarding_projects.delete_one({"id": project_id})
        await db.onboarding_audit_events.delete_many({"project_id": project_id})
        return {"ok": True, "deleted": True}
    # Soft-archive only — never touches the underlying organisation/records.
    await db.onboarding_projects.update_one(
        {"id": project_id}, {"$set": {"status": "archived", "updated_at": _now()}}
    )
    await _audit(project_id, user, "project_archived")
    return {"ok": True}


@router.post("/onboarding/projects/purge-archived")
async def purge_archived_projects(user: dict = Depends(get_current_user)) -> dict:
    """Permanently delete ALL archived onboarding projects in one pass.

    Cleanup helper for clearing out old/test projects. Only removes the
    onboarding TRACKING records (+ their audit events) — never touches the
    underlying organisations, users, assets or any live data.
    """
    _require_admin_no_desk(user)
    ids = [d["id"] async for d in db.onboarding_projects.find(
        {"status": "archived"}, {"_id": 0, "id": 1}
    )]
    if not ids:
        return {"ok": True, "deleted": 0}
    res = await db.onboarding_projects.delete_many({"id": {"$in": ids}})
    await db.onboarding_audit_events.delete_many({"project_id": {"$in": ids}})
    return {"ok": True, "deleted": res.deleted_count}



# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/onboarding/dashboard")
async def dashboard(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    docs = await db.onboarding_projects.find({"status": {"$ne": "archived"}}).to_list(1000)
    active = [d for d in docs if d.get("status") != "complete"]
    blocked = []
    total_pct = 0
    by_owner: dict = {}
    missing_counter: dict = {}
    for d in docs:
        prog = _progress(d)
        total_pct += prog["percent"]
        if prog["blocked"]:
            blocked.append(d["id"])
        owner = d.get("owner") or "Unassigned"
        by_owner[owner] = by_owner.get(owner, 0) + (1 if d.get("status") != "complete" else 0)
        for m in prog["missing"]:
            missing_counter[m] = missing_counter.get(m, 0) + 1
    go_lives_due = [d["id"] for d in active if (d.get("go_live_target") or "")]
    top_missing = sorted(missing_counter.items(), key=lambda x: -x[1])[:5]
    return {
        "onboarding_count": len(active),
        "completed_count": len([d for d in docs if d.get("status") == "complete"]),
        "blocked_count": len(blocked),
        "avg_completion": round(total_pct / len(docs)) if docs else 0,
        "go_lives_due": len(go_lives_due),
        "owner_workload": by_owner,
        "common_missing": [{"label": k, "count": v} for k, v in top_missing],
    }


# ── Settings (singleton) ─────────────────────────────────────────────────────

_SETTINGS_ID = "onboarding-settings"


@router.get("/onboarding/settings")
async def get_settings(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.onboarding_settings.find_one({"id": _SETTINGS_ID}, {"_id": 0})
    return doc or {"id": _SETTINGS_ID, "customer_portal_enabled": False}


@router.patch("/onboarding/settings")
async def update_settings(body: dict, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    allowed = {"customer_portal_enabled"}
    updates = {k: v for k, v in (body or {}).items() if k in allowed}
    updates["updated_at"] = _now()
    await db.onboarding_settings.update_one({"id": _SETTINGS_ID}, {"$set": updates}, upsert=True)
    doc = await db.onboarding_settings.find_one({"id": _SETTINGS_ID}, {"_id": 0})
    return doc
