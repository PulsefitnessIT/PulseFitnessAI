"""Pre-Install Site Survey — CRM Corporate feature.

A structured, permanent survey attached to an EXISTING CRM company
(``crm2_companies``) + site (``sites``) record, optionally linked to an
existing opportunity / quote / project (``onboarding_projects``) /
service job (``svc_cases``). No core records are duplicated.

Collections
-----------
* ``pre_install_site_surveys``      — one doc per survey (nested sections)
* ``pre_install_survey_attachments``— photos / videos / floor plans (b64)
* ``pre_install_survey_versions``   — snapshots when a survey is superseded
* ``pre_install_survey_audit``      — immutable audit trail
* ``pre_install_survey_settings``   — per-org configuration (singleton)

Phase 1 scope: create/edit structured survey, statuses + history,
readiness check (with manager override), version history, audit trail,
role permissions, attachments, branded handover PDF, and surfacing in
the company + site records. AI / customer-portal / notifications /
reporting dashboard are Phase 2+.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File as FastAPIFile
from fastapi.responses import Response
from pydantic import BaseModel

from utils.database import db
from routes.crm_auth import get_crm_user
from utils.site_scope import effective_site_filter
from routes.crm_site_surveys_schema import (
    SURVEY_SCHEMA, SURVEY_TYPES, SURVEY_STATUSES, READINESS_CHECKS,
    READINESS_STATUSES, ATTACHMENT_CATEGORIES, CRITICAL_READINESS_KEYS,
)

router = APIRouter(prefix="/crm/site-surveys", tags=["CRM Pre-Install Site Surveys"])

SURVEYS = "pre_install_site_surveys"
ATTACH = "pre_install_survey_attachments"
VERSIONS = "pre_install_survey_versions"
AUDIT = "pre_install_survey_audit"
SETTINGS = "pre_install_survey_settings"

# Roles allowed to approve installation readiness / apply manager override.
_APPROVER_ROLES = {"owner", "admin", "manager", "master", "master_admin",
                   "pulse_master_admin", "installation_manager"}
_MAX_ATTACH_BYTES = 25 * 1024 * 1024  # 25MB per file (base64 in Mongo)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _of(user: dict) -> dict:
    """Org + per-request site RBAC filter (mirrors crm_v2._of)."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"organization_id": "__NONE__"}
    return {"organization_id": org_id, **effective_site_filter()}


def _is_approver(user: dict) -> bool:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    return (user.get("role") or "").lower() in _APPROVER_ROLES


async def _log_audit(survey_id: str, user: dict, action: str, *,
                     old=None, new=None, reason: str = "", field: str = ""):
    await db[AUDIT].insert_one({
        "id": _id(),
        "survey_id": survey_id,
        "organization_id": user.get("organization_id"),
        "user_id": user.get("id"),
        "user_name": user.get("full_name") or user.get("email") or "",
        "action": action,
        "field": field,
        "old_value": old,
        "new_value": new,
        "reason": reason,
        "created_at": _now(),
    })


async def _next_reference(org_id: str) -> str:
    n = await db[SURVEYS].count_documents({"organization_id": org_id})
    return f"PIS-{n + 1:05d}"


async def _get_settings(org_id: str) -> dict:
    doc = await db[SETTINGS].find_one({"organization_id": org_id}, {"_id": 0})
    if not doc:
        doc = {
            "organization_id": org_id,
            "enabled": True,
            "require_design_review": False,
            "require_installation_review": True,
            "require_manager_approval_high_risk": True,
            "allow_customer_portal_input": False,
            "allow_ai_summaries": True,
            "allow_pdf_export": True,
            "updated_at": _now(),
        }
    doc.pop("_id", None)
    return doc


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _summary(doc: dict) -> dict:
    """Trim a survey doc to list-row essentials."""
    return {
        "id": doc.get("id"),
        "reference": doc.get("reference"),
        "company_id": doc.get("company_id"),
        "company_name": doc.get("company_name"),
        "site_id": doc.get("site_id"),
        "site_name": doc.get("site_name"),
        "survey_type": doc.get("survey_type"),
        "status": doc.get("status"),
        "readiness_status": doc.get("readiness_status"),
        "priority": doc.get("priority"),
        "target_install_date": doc.get("target_install_date"),
        "survey_date": doc.get("survey_date"),
        "completed_by_name": doc.get("completed_by_name"),
        "version": doc.get("version", 1),
        "is_current": doc.get("is_current", True),
        "opportunity_id": doc.get("opportunity_id"),
        "quote_id": doc.get("quote_id"),
        "project_id": doc.get("project_id"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ── Readiness engine ────────────────────────────────────────────────

def _field_filled(data: dict, section: str, key: str) -> bool:
    sec = (data or {}).get(section) or {}
    v = sec.get(key)
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return v not in (None, "", [])


def compute_readiness(doc: dict) -> dict:
    """Return {status, checks:[{key,label,done}], critical_missing:[...]}. """
    data = doc.get("data") or {}
    rooms = data.get("rooms") or []
    risks = data.get("risks") or []
    equipment = data.get("equipment") or []
    attachments = doc.get("attachment_count", 0)

    def done_for(key: str) -> bool:
        # Custom evaluators per readiness key.
        if key == "site_details_complete":
            return _field_filled(data, "site_details", "site_name")
        if key == "site_contact_confirmed":
            return len((data.get("site_contacts") or [])) > 0
        if key == "access_route_confirmed":
            return _field_filled(data, "access", "delivery_entrance")
        if key == "room_measurements_complete":
            return any((r.get("room_length") and r.get("room_width")) for r in rooms)
        if key == "floor_plan_uploaded":
            return bool(doc.get("has_floor_plan"))
        if key == "equipment_list_confirmed":
            return len(equipment) > 0
        if key == "quote_linked":
            return bool(doc.get("quote_id") or doc.get("opportunity_id"))
        if key == "power_reviewed":
            return _field_filled(data, "power", "electrical_supply_available")
        if key == "network_reviewed":
            return _field_filled(data, "network", "wifi_available")
        if key == "parking_loading_confirmed":
            return _field_filled(data, "parking", "parking_available")
        if key == "risks_reviewed":
            return len(risks) > 0 or bool((data.get("risks_meta") or {}).get("reviewed"))
        if key == "photos_uploaded":
            return attachments > 0
        if key == "customer_requirements_captured":
            return _field_filled(data, "customer_requirements", "customer_goal")
        if key == "installation_notes_complete":
            return _field_filled(data, "installation_notes", "notes")
        if key == "internal_approval_complete":
            return doc.get("status") in ("approved_for_installation", "completed")
        return False

    checks = [{"key": c["key"], "label": c["label"], "critical": c["key"] in CRITICAL_READINESS_KEYS,
               "done": done_for(c["key"])} for c in READINESS_CHECKS]
    critical_missing = [c["label"] for c in checks if c["critical"] and not c["done"]]

    # Derive readiness status.
    high_risk = any((r.get("risk_level") or "").lower() in ("high", "critical") for r in risks)
    all_done = all(c["done"] for c in checks)
    if high_risk and critical_missing:
        status = "risks_need_review"
    elif critical_missing:
        status = "information_missing"
    elif high_risk:
        status = "risks_need_review"
    elif all_done:
        status = "ready_for_installation"
    else:
        status = "ready_for_quote"
    return {"status": status, "checks": checks, "critical_missing": critical_missing,
            "high_risk": high_risk}


# ── Pydantic payloads ───────────────────────────────────────────────

class SurveyCreate(BaseModel):
    company_id: str
    site_id: str | None = None
    survey_type: str = "new_gym_installation"
    survey_date: str | None = None
    target_install_date: str | None = None
    priority: str = "normal"
    opportunity_id: str | None = None
    quote_id: str | None = None
    project_id: str | None = None
    svc_case_id: str | None = None
    template_id: str | None = None
    notes: str | None = None


class SurveyUpdate(BaseModel):
    data: dict | None = None                # merged section data
    survey_type: str | None = None
    survey_date: str | None = None
    target_install_date: str | None = None
    priority: str | None = None
    opportunity_id: str | None = None
    quote_id: str | None = None
    project_id: str | None = None
    svc_case_id: str | None = None
    project_manager: str | None = None
    installation_manager: str | None = None
    notes: str | None = None


class StatusChange(BaseModel):
    status: str
    reason: str | None = None
    override: bool = False


# ── Fixed (literal) routes — declared BEFORE /{survey_id} ───────────

@router.get("/schema")
async def get_schema(user=Depends(get_crm_user)):
    """Field catalogue that drives the form UI, AI and readiness rules."""
    return {
        "sections": SURVEY_SCHEMA,
        "survey_types": SURVEY_TYPES,
        "statuses": SURVEY_STATUSES,
        "readiness_checks": READINESS_CHECKS,
        "readiness_statuses": READINESS_STATUSES,
        "attachment_categories": ATTACHMENT_CATEGORIES,
    }


@router.get("/settings")
async def get_settings(user=Depends(get_crm_user)):
    return await _get_settings(user.get("organization_id"))


@router.put("/settings")
async def update_settings(payload: dict, user=Depends(get_crm_user)):
    if not _is_approver(user):
        raise HTTPException(403, "Only managers/admins can change survey settings")
    org_id = user.get("organization_id")
    current = await _get_settings(org_id)
    allowed = {"enabled", "require_design_review", "require_installation_review",
               "require_manager_approval_high_risk", "allow_customer_portal_input",
               "allow_ai_summaries", "allow_pdf_export", "default_template_id"}
    for k, v in (payload or {}).items():
        if k in allowed:
            current[k] = v
    current["organization_id"] = org_id
    current["updated_at"] = _now()
    await db[SETTINGS].update_one({"organization_id": org_id}, {"$set": current}, upsert=True)
    return current


@router.get("/summary")
async def survey_summary(company_id: str | None = None, site_id: str | None = None,
                         user=Depends(get_crm_user)):
    """Counts for tab badges on company / site records."""
    q = {**_of(user), "is_current": True}
    if company_id:
        q["company_id"] = company_id
    if site_id:
        q["site_id"] = site_id
    total = await db[SURVEYS].count_documents(q)
    open_q = {**q, "status": {"$nin": ["completed", "archived", "superseded"]}}
    open_count = await db[SURVEYS].count_documents(open_q)
    return {"total": total, "open": open_count}


@router.get("")
async def list_surveys(company_id: str | None = None, site_id: str | None = None,
                       status: str | None = None, include_superseded: bool = False,
                       user=Depends(get_crm_user)):
    q = {**_of(user)}
    if company_id:
        q["company_id"] = company_id
    if site_id:
        q["site_id"] = site_id
    if status:
        q["status"] = status
    if not include_superseded:
        q["is_current"] = True
    docs = await db[SURVEYS].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"surveys": [_summary(d) for d in docs], "total": len(docs)}


@router.post("")
async def create_survey(payload: SurveyCreate, user=Depends(get_crm_user)):
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "No organisation context")

    # Link to EXISTING company + site (never duplicate).
    company = await db.crm2_companies.find_one(
        {"id": payload.company_id, "organization_id": org_id}, {"_id": 0, "name": 1, "id": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    site_name = None
    if payload.site_id:
        site = await db.sites.find_one(
            {"id": payload.site_id, "organization_id": org_id}, {"_id": 0, "name": 1})
        if not site:
            raise HTTPException(404, "Site not found")
        site_name = site.get("name")

    doc = {
        "id": _id(),
        "reference": await _next_reference(org_id),
        "organization_id": org_id,
        "company_id": payload.company_id,
        "company_name": company.get("name"),
        "site_id": payload.site_id,
        "site_name": site_name,
        "survey_type": payload.survey_type,
        "survey_date": payload.survey_date,
        "target_install_date": payload.target_install_date,
        "priority": payload.priority,
        "opportunity_id": payload.opportunity_id,
        "quote_id": payload.quote_id,
        "project_id": payload.project_id,
        "svc_case_id": payload.svc_case_id,
        "template_id": payload.template_id,
        "notes": payload.notes,
        "status": "draft",
        "readiness_status": "not_ready",
        "version": 1,
        "is_current": True,
        "root_id": None,
        "data": {},
        "attachment_count": 0,
        "has_floor_plan": False,
        "completed_by": user.get("id"),
        "completed_by_name": user.get("full_name") or user.get("email") or "",
        "project_manager": None,
        "installation_manager": None,
        "status_history": [{"status": "draft", "at": _now(),
                            "by": user.get("full_name") or user.get("email") or ""}],
        "created_at": _now(),
        "updated_at": _now(),
    }
    doc["root_id"] = doc["id"]
    await db[SURVEYS].insert_one(dict(doc))
    await _log_audit(doc["id"], user, "survey_created",
                     new={"reference": doc["reference"], "company": company.get("name")})
    return _clean(dict(doc))


# ── Per-survey routes ───────────────────────────────────────────────

async def _load(survey_id: str, user: dict) -> dict:
    doc = await db[SURVEYS].find_one({"id": survey_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Survey not found")
    return doc


@router.get("/{survey_id}")
async def get_survey(survey_id: str, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    doc["readiness"] = compute_readiness(doc)
    return doc


@router.put("/{survey_id}")
async def update_survey(survey_id: str, payload: SurveyUpdate, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    if doc.get("status") in ("archived", "superseded"):
        raise HTTPException(400, "This survey is read-only (archived/superseded)")

    updates: dict = {"updated_at": _now()}
    # Deep-merge section data.
    if payload.data is not None:
        merged = dict(doc.get("data") or {})
        for k, v in payload.data.items():
            merged[k] = v
        updates["data"] = merged

    for f in ("survey_type", "survey_date", "target_install_date", "priority",
              "opportunity_id", "quote_id", "project_id", "svc_case_id",
              "project_manager", "installation_manager", "notes"):
        val = getattr(payload, f)
        if val is not None:
            updates[f] = val

    # Recompute readiness from the merged doc.
    merged_doc = {**doc, **updates}
    readiness = compute_readiness(merged_doc)
    updates["readiness_status"] = readiness["status"]

    await db[SURVEYS].update_one({"id": survey_id}, {"$set": updates})
    await _log_audit(survey_id, user, "survey_edited",
                     new={"sections": list((payload.data or {}).keys())})
    out = {**merged_doc, **updates}
    out["readiness"] = readiness
    return _clean(out)


@router.post("/{survey_id}/status")
async def change_status(survey_id: str, payload: StatusChange, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    valid = {s["key"] for s in SURVEY_STATUSES}
    if payload.status not in valid:
        raise HTTPException(400, f"Invalid status: {payload.status}")

    # Guard: installation approval requires all critical fields + approver
    # role, unless a manager override with a reason is recorded.
    if payload.status == "approved_for_installation":
        if not _is_approver(user):
            raise HTTPException(403, "Only an installation manager/admin can approve for installation")
        readiness = compute_readiness(doc)
        if readiness["critical_missing"] and not payload.override:
            raise HTTPException(400, {
                "error": "critical_fields_missing",
                "missing": readiness["critical_missing"],
                "message": "Critical information is missing. A manager override with a reason is required.",
            })
        if readiness["critical_missing"] and payload.override and not (payload.reason or "").strip():
            raise HTTPException(400, "A reason is required to override missing critical fields")

    old = doc.get("status")
    entry = {"status": payload.status, "at": _now(),
             "by": user.get("full_name") or user.get("email") or "",
             "reason": payload.reason or ""}
    if payload.override:
        entry["override"] = True
    await db[SURVEYS].update_one(
        {"id": survey_id},
        {"$set": {"status": payload.status, "updated_at": _now()},
         "$push": {"status_history": entry}})
    await _log_audit(survey_id, user, "status_changed", old=old, new=payload.status,
                     reason=payload.reason or ("manager override" if payload.override else ""))
    return {"status": payload.status, "history_entry": entry}


@router.post("/{survey_id}/supersede")
async def supersede_survey(survey_id: str, user=Depends(get_crm_user)):
    """Snapshot the current survey as a version and create a fresh v(n+1)
    copy that becomes the current one. Old surveys are never deleted."""
    doc = await _load(survey_id, user)
    # Snapshot into versions.
    snap = dict(doc)
    snap["id"] = _id()
    snap["snapshot_of"] = doc["id"]
    snap["snapshot_at"] = _now()
    await db[VERSIONS].insert_one(snap)
    # Mark the old one superseded + not current.
    await db[SURVEYS].update_one({"id": survey_id},
                                 {"$set": {"status": "superseded", "is_current": False,
                                           "updated_at": _now()}})
    # New current version.
    new = dict(doc)
    new["id"] = _id()
    new["reference"] = f"{doc.get('reference')}-v{doc.get('version', 1) + 1}"
    new["version"] = doc.get("version", 1) + 1
    new["is_current"] = True
    new["status"] = "draft"
    new["root_id"] = doc.get("root_id") or doc["id"]
    new["status_history"] = [{"status": "draft", "at": _now(),
                              "by": user.get("full_name") or user.get("email") or "",
                              "reason": f"New version of {doc.get('reference')}"}]
    new["created_at"] = _now()
    new["updated_at"] = _now()
    new.pop("_id", None)
    await db[SURVEYS].insert_one(dict(new))
    await _log_audit(new["id"], user, "survey_superseded",
                     old=doc.get("reference"), new=new.get("reference"))
    return _clean(dict(new))


@router.get("/{survey_id}/readiness")
async def get_readiness(survey_id: str, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    return compute_readiness(doc)


@router.get("/{survey_id}/audit")
async def get_audit(survey_id: str, user=Depends(get_crm_user)):
    await _load(survey_id, user)
    events = await db[AUDIT].find({"survey_id": survey_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"events": events, "total": len(events)}


@router.get("/{survey_id}/versions")
async def get_versions(survey_id: str, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    root = doc.get("root_id") or survey_id
    chain = await db[SURVEYS].find(
        {"$or": [{"root_id": root}, {"id": root}], **_of(user)}, {"_id": 0}
    ).sort("version", 1).to_list(100)
    return {"versions": [_summary(d) for d in chain], "total": len(chain)}


# ── Attachments ─────────────────────────────────────────────────────

@router.get("/{survey_id}/attachments")
async def list_attachments(survey_id: str, user=Depends(get_crm_user)):
    await _load(survey_id, user)
    items = await db[ATTACH].find(
        {"survey_id": survey_id}, {"_id": 0, "data_b64": 0}
    ).sort("created_at", -1).to_list(500)
    return {"attachments": items, "total": len(items)}


@router.post("/{survey_id}/attachments")
async def upload_attachment(
    survey_id: str,
    category: str = "room_photos",
    description: str = "",
    room_id: str = "",
    visible_to_installer: bool = True,
    visible_to_customer: bool = False,
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_crm_user),
):
    doc = await _load(survey_id, user)
    content = await file.read()
    if len(content) > _MAX_ATTACH_BYTES:
        raise HTTPException(413, "File too large (max 25MB)")
    att = {
        "id": _id(),
        "survey_id": survey_id,
        "organization_id": user.get("organization_id"),
        "category": category,
        "description": description,
        "room_id": room_id or None,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "data_b64": base64.b64encode(content).decode("utf-8"),
        "visible_to_installer": visible_to_installer,
        "visible_to_customer": visible_to_customer,
        "uploaded_by": user.get("id"),
        "uploaded_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
    }
    await db[ATTACH].insert_one(dict(att))
    is_plan = category in ("floor_plans", "drawings")
    set_fields = {"attachment_count": doc.get("attachment_count", 0) + 1, "updated_at": _now()}
    if is_plan:
        set_fields["has_floor_plan"] = True
    await db[SURVEYS].update_one({"id": survey_id}, {"$set": set_fields})
    await _log_audit(survey_id, user, "file_uploaded",
                     new={"filename": file.filename, "category": category})
    att.pop("data_b64", None)
    return att


@router.get("/{survey_id}/attachments/{attachment_id}/download")
async def download_attachment(survey_id: str, attachment_id: str, user=Depends(get_crm_user)):
    await _load(survey_id, user)
    att = await db[ATTACH].find_one({"id": attachment_id, "survey_id": survey_id}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    data = base64.b64decode(att.get("data_b64", ""))
    return Response(content=data, media_type=att.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "file")}"'})


@router.delete("/{survey_id}/attachments/{attachment_id}")
async def delete_attachment(survey_id: str, attachment_id: str, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    att = await db[ATTACH].find_one({"id": attachment_id, "survey_id": survey_id}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    await db[ATTACH].delete_one({"id": attachment_id})
    await db[SURVEYS].update_one(
        {"id": survey_id},
        {"$set": {"attachment_count": max(0, doc.get("attachment_count", 1) - 1), "updated_at": _now()}})
    await _log_audit(survey_id, user, "file_deleted", old={"filename": att.get("original_filename")})
    return {"success": True}


# ── Handover (JSON + branded PDF) ───────────────────────────────────

def _build_handover(doc: dict, attachments: list) -> dict:
    data = doc.get("data") or {}
    readiness = compute_readiness(doc)
    return {
        "reference": doc.get("reference"),
        "company_name": doc.get("company_name"),
        "site_name": doc.get("site_name"),
        "survey_type": doc.get("survey_type"),
        "survey_date": doc.get("survey_date"),
        "target_install_date": doc.get("target_install_date"),
        "completed_by": doc.get("completed_by_name"),
        "installation_manager": doc.get("installation_manager"),
        "status": doc.get("status"),
        "readiness": readiness,
        "site_details": data.get("site_details") or {},
        "access": data.get("access") or {},
        "parking": data.get("parking") or {},
        "power": data.get("power") or {},
        "network": data.get("network") or {},
        "flooring": data.get("flooring") or {},
        "walls": data.get("walls") or {},
        "ceiling": data.get("ceiling") or {},
        "rooms": data.get("rooms") or [],
        "equipment": data.get("equipment") or [],
        "risks": data.get("risks") or [],
        "customer_requirements": data.get("customer_requirements") or {},
        "installation_notes": (data.get("installation_notes") or {}).get("notes", ""),
        "site_rules": data.get("site_rules") or {},
        "attachments": [{"category": a.get("category"), "filename": a.get("original_filename"),
                         "description": a.get("description")} for a in attachments],
    }


@router.get("/{survey_id}/handover")
async def get_handover(survey_id: str, user=Depends(get_crm_user)):
    doc = await _load(survey_id, user)
    attachments = await db[ATTACH].find({"survey_id": survey_id},
                                        {"_id": 0, "data_b64": 0}).to_list(500)
    return _build_handover(doc, attachments)


@router.get("/{survey_id}/handover.pdf")
async def get_handover_pdf(survey_id: str, user=Depends(get_crm_user)):
    settings = await _get_settings(user.get("organization_id"))
    if not settings.get("allow_pdf_export", True):
        raise HTTPException(403, "PDF export is disabled for this organisation")
    doc = await _load(survey_id, user)
    attachments = await db[ATTACH].find({"survey_id": survey_id},
                                        {"_id": 0, "data_b64": 0}).to_list(500)
    handover = _build_handover(doc, attachments)
    from utils.survey_pdf import build_handover_pdf
    await _log_audit(survey_id, user, "pdf_generated", new={"reference": doc.get("reference")})
    pdf_bytes = build_handover_pdf(handover)
    fname = f"Installation_Handover_{doc.get('reference', 'survey')}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})



# ── AI assistant (advisory only — never writes to the survey) ───────

async def _ai_enabled(user: dict):
    settings = await _get_settings(user.get("organization_id"))
    if not settings.get("allow_ai_summaries", True):
        raise HTTPException(403, "AI summaries are disabled for this organisation")


@router.post("/{survey_id}/ai/analyse")
async def ai_analyse(survey_id: str, user=Depends(get_crm_user)):
    await _ai_enabled(user)
    doc = await _load(survey_id, user)
    from utils.survey_ai import analyse_survey
    result = await analyse_survey(doc, compute_readiness(doc))
    if result.get("available"):
        await _log_audit(survey_id, user, "ai_analysis_run",
                         new={"missing": len(result.get("missing_information") or []),
                              "risks": len(result.get("risks") or [])})
    return result


@router.post("/{survey_id}/ai/follow-up-email")
async def ai_follow_up_email(survey_id: str, user=Depends(get_crm_user)):
    await _ai_enabled(user)
    doc = await _load(survey_id, user)
    missing = compute_readiness(doc).get("critical_missing") or []
    from utils.survey_ai import draft_follow_up_email
    result = await draft_follow_up_email(doc, missing)
    if result.get("available"):
        await _log_audit(survey_id, user, "ai_followup_drafted")
    return result


@router.post("/{survey_id}/ai/briefing")
async def ai_briefing(survey_id: str, user=Depends(get_crm_user)):
    await _ai_enabled(user)
    doc = await _load(survey_id, user)
    from utils.survey_ai import draft_briefing
    result = await draft_briefing(doc)
    if result.get("available"):
        await _log_audit(survey_id, user, "ai_briefing_drafted")
    return result
