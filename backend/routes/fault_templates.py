"""Fault-template CRUD — admins save frequently-used fault patterns as reusable shortcuts.

Scope model:
  - scope = 'org'      → visible to all users in the org; owner/manager can create/edit/delete.
  - scope = 'personal' → visible only to the creator; any user can manage their own.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
import uuid

from utils.auth import get_current_user, get_organization_filter
from utils.database import db
from utils.security import sanitise_string
from constants.fault_codes import VALID_FAULT_CODES

router = APIRouter()

_PRIVILEGED_ROLES = {"owner", "manager", "master_admin"}
_PROJECTION = {"_id": 0}


def _can_manage_org_templates(user: dict) -> bool:
    return bool(user.get("is_master_admin")) or user.get("role") in _PRIVILEGED_ROLES


def _validate_template_fields(data: dict) -> None:
    """Fail fast on malformed payloads."""
    if not data.get("name") or not data.get("machine_type") or not data.get("issue_description"):
        raise HTTPException(status_code=400, detail="Template must include name, machine_type, and issue_description")
    fc = data.get("fault_code")
    if fc and fc not in VALID_FAULT_CODES:
        raise HTTPException(status_code=400, detail=f"Invalid fault_code '{fc}'")
    scope = data.get("scope", "personal")
    if scope not in {"org", "personal"}:
        raise HTTPException(status_code=400, detail="scope must be 'org' or 'personal'")


def _build_template_doc(data: dict, user: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "created_by_user_id": user["id"],
        "created_by_name": user.get("full_name", ""),
        "scope": data.get("scope", "personal"),
        "name": sanitise_string(data["name"])[:80],
        "machine_type": sanitise_string(data["machine_type"])[:120],
        "issue_description": sanitise_string(data["issue_description"])[:500],
        "severity": data.get("severity") or "operational_minor",
        "supplier": sanitise_string(data.get("supplier") or ""),
        "steps_taken": sanitise_string(data.get("steps_taken") or "")[:500],
        "fault_code": data.get("fault_code") or None,
        "usage_count": 0,
        "last_used_at": None,
        "created_at": now,
        "updated_at": now,
    }


async def _load_template_or_404(template_id: str, user: dict) -> dict:
    org_filter = get_organization_filter(user)
    tpl = await db.fault_templates.find_one({"id": template_id, **org_filter}, _PROJECTION)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


def _assert_manage_permission(template: dict, user: dict) -> None:
    """org-scoped → requires privileged role; personal → creator-only (admins still allowed)."""
    if template["scope"] == "org":
        if not _can_manage_org_templates(user):
            raise HTTPException(status_code=403, detail="Only owner/manager can manage org-wide templates")
    else:
        if template["created_by_user_id"] != user["id"] and not user.get("is_master_admin"):
            raise HTTPException(status_code=403, detail="You can only manage your own personal templates")


@router.get("/fault-templates")
async def list_fault_templates(user: dict = Depends(get_current_user)) -> dict:
    """Return all templates visible to the current user: org-wide + their own personal ones."""
    org_filter = get_organization_filter(user)
    query = {
        **org_filter,
        "$or": [{"scope": "org"}, {"scope": "personal", "created_by_user_id": user["id"]}],
    }
    cursor = db.fault_templates.find(query, _PROJECTION).sort("usage_count", -1)
    templates = await cursor.to_list(length=500)
    return {"templates": templates}


@router.post("/fault-templates")
async def create_fault_template(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    _validate_template_fields(data)
    scope = data.get("scope", "personal")
    if scope == "org" and not _can_manage_org_templates(user):
        raise HTTPException(status_code=403, detail="Only owner/manager can create org-wide templates")

    doc = _build_template_doc(data, user)
    await db.fault_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/fault-templates/{template_id}")
async def update_fault_template(template_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    tpl = await _load_template_or_404(template_id, user)
    _assert_manage_permission(tpl, user)

    # Only allow scope change from personal → org if user is privileged
    new_scope = data.get("scope", tpl["scope"])
    if new_scope != tpl["scope"] and new_scope == "org" and not _can_manage_org_templates(user):
        raise HTTPException(status_code=403, detail="Only owner/manager can promote a template to org-wide")

    # Merge + re-validate
    merged = {**tpl, **{k: v for k, v in data.items() if k in {
        "name", "machine_type", "issue_description", "severity",
        "supplier", "steps_taken", "fault_code", "scope",
    }}}
    _validate_template_fields(merged)

    updates = {
        "name": sanitise_string(merged["name"])[:80],
        "machine_type": sanitise_string(merged["machine_type"])[:120],
        "issue_description": sanitise_string(merged["issue_description"])[:500],
        "severity": merged.get("severity") or "operational_minor",
        "supplier": sanitise_string(merged.get("supplier") or ""),
        "steps_taken": sanitise_string(merged.get("steps_taken") or "")[:500],
        "fault_code": merged.get("fault_code") or None,
        "scope": merged["scope"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fault_templates.update_one({"id": template_id}, {"$set": updates})
    return {"success": True, **updates}


@router.delete("/fault-templates/{template_id}")
async def delete_fault_template(template_id: str, user: dict = Depends(get_current_user)) -> dict:
    tpl = await _load_template_or_404(template_id, user)
    _assert_manage_permission(tpl, user)
    await db.fault_templates.delete_one({"id": template_id})
    return {"success": True}


@router.post("/fault-templates/{template_id}/used")
async def mark_template_used(template_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Increment usage_count + set last_used_at — powers 'most used' sorting and analytics."""
    await _load_template_or_404(template_id, user)  # enforces visibility
    await db.fault_templates.update_one(
        {"id": template_id},
        {"$inc": {"usage_count": 1}, "$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}
