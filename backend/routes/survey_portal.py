"""Pre-Install Site Survey — Customer Portal (platform-auth).

Surfaced inside Account Settings → Onboarding for the org's own users
(the "customer / site contact"). Uses the platform JWT (`get_current_user`)
and is scoped to the caller's organisation. The customer may only view +
edit a WHITELISTED subset of fields (see CUSTOMER_PORTAL_FIELDS) and
upload floor plans / photos — they never see internal notes, risks,
layout notes, internal review or readiness scoring.

Gated per-org by the `allow_customer_portal_input` survey setting.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from pydantic import BaseModel

from starlette.concurrency import run_in_threadpool

from utils.database import db, put_object, APP_NAME
from utils.auth import get_current_user
from routes.crm_site_surveys_schema import (
    CUSTOMER_PORTAL_FIELDS, CUSTOMER_UPLOAD_CATEGORIES, customer_portal_schema,
    SURVEY_TYPES, SURVEY_STATUSES,
)

router = APIRouter(prefix="/survey-portal", tags=["Site Survey Customer Portal"])

SURVEYS = "pre_install_site_surveys"
ATTACH = "pre_install_survey_attachments"
AUDIT = "pre_install_survey_audit"
SETTINGS = "pre_install_survey_settings"

_MAX_ATTACH_BYTES = 25 * 1024 * 1024
_CUST_CATS = {c["key"] for c in CUSTOMER_UPLOAD_CATEGORIES}
# Surveys the customer can act on (not internal-only / closed states).
_PORTAL_STATUSES = {"awaiting_customer_information", "in_progress", "draft",
                    "awaiting_internal_review", "awaiting_design_review"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _portal_enabled(org_id: str) -> bool:
    s = await db[SETTINGS].find_one({"organization_id": org_id}, {"_id": 0, "allow_customer_portal_input": 1})
    # Default OFF unless a manager explicitly enabled it.
    return bool(s and s.get("allow_customer_portal_input"))


async def _log(survey_id: str, user: dict, action: str, new=None):
    await db[AUDIT].insert_one({
        "id": str(uuid.uuid4()), "survey_id": survey_id,
        "organization_id": user.get("organization_id"),
        "user_id": user.get("id"),
        "user_name": (user.get("full_name") or user.get("email") or "") + " (customer portal)",
        "action": action, "new_value": new, "created_at": _now(),
    })


def _customer_view(doc: dict) -> dict:
    """Strip the survey to customer-safe fields only."""
    data = doc.get("data") or {}
    safe_data = {}
    for sec_id, allowed in CUSTOMER_PORTAL_FIELDS.items():
        val = data.get(sec_id)
        if val is None:
            continue
        if allowed == "*" or isinstance(val, list):
            safe_data[sec_id] = val
        elif isinstance(val, dict):
            safe_data[sec_id] = {k: v for k, v in val.items() if k in allowed}
    # A read-only site reference so the customer knows which site.
    site_ref = (data.get("site_details") or {}).get("site_name") or doc.get("site_name")
    return {
        "id": doc.get("id"),
        "reference": doc.get("reference"),
        "site_name": doc.get("site_name") or site_ref,
        "survey_type": doc.get("survey_type"),
        "target_install_date": doc.get("target_install_date"),
        "status": doc.get("status"),
        "data": safe_data,
    }


async def _load(survey_id: str, user: dict) -> dict:
    org_id = user.get("organization_id")
    if not await _portal_enabled(org_id):
        raise HTTPException(403, "The site survey customer portal is not enabled for your organisation")
    doc = await db[SURVEYS].find_one(
        {"id": survey_id, "organization_id": org_id, "is_current": True}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Survey not found")
    return doc


class PortalUpdate(BaseModel):
    data: dict


@router.get("/schema")
async def portal_schema(user=Depends(get_current_user)):
    return {
        "sections": customer_portal_schema(),
        "upload_categories": CUSTOMER_UPLOAD_CATEGORIES,
        "survey_types": SURVEY_TYPES,
        "statuses": SURVEY_STATUSES,
    }


@router.get("/surveys")
async def list_portal_surveys(user=Depends(get_current_user)):
    org_id = user.get("organization_id")
    if not org_id or not await _portal_enabled(org_id):
        return {"surveys": [], "enabled": False}
    docs = await db[SURVEYS].find(
        {"organization_id": org_id, "is_current": True, "status": {"$in": list(_PORTAL_STATUSES)}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"enabled": True, "surveys": [_customer_view(d) for d in docs]}


@router.get("/surveys/{survey_id}")
async def get_portal_survey(survey_id: str, user=Depends(get_current_user)):
    doc = await _load(survey_id, user)
    view = _customer_view(doc)
    view["schema"] = customer_portal_schema()
    view["upload_categories"] = CUSTOMER_UPLOAD_CATEGORIES
    return view


@router.put("/surveys/{survey_id}")
async def update_portal_survey(survey_id: str, payload: PortalUpdate, user=Depends(get_current_user)):
    doc = await _load(survey_id, user)
    incoming = payload.data or {}
    merged = dict(doc.get("data") or {})
    touched = []
    for sec_id, allowed in CUSTOMER_PORTAL_FIELDS.items():
        if sec_id not in incoming:
            continue
        val = incoming[sec_id]
        if allowed == "*":
            merged[sec_id] = val  # whole repeatable section (e.g. site_contacts)
            touched.append(sec_id)
        elif isinstance(val, dict):
            base = dict(merged.get(sec_id) or {})
            for k, v in val.items():
                if k in allowed:  # ignore any non-whitelisted keys
                    base[k] = v
            merged[sec_id] = base
            touched.append(sec_id)
    await db[SURVEYS].update_one(
        {"id": survey_id},
        {"$set": {"data": merged, "updated_at": _now(),
                  "customer_last_contributed_at": _now()}})
    await _log(survey_id, user, "customer_information_received", new={"sections": touched})
    return _customer_view({**doc, "data": merged})


@router.get("/surveys/{survey_id}/attachments")
async def list_portal_attachments(survey_id: str, user=Depends(get_current_user)):
    await _load(survey_id, user)
    items = await db[ATTACH].find(
        {"survey_id": survey_id, "visible_to_customer": True}, {"_id": 0, "data_b64": 0, "storage_path": 0}
    ).sort("created_at", -1).to_list(200)
    return {"attachments": items}


@router.post("/surveys/{survey_id}/attachments")
async def upload_portal_attachment(
    survey_id: str,
    category: str = "floor_plans",
    description: str = "",
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_current_user),
):
    doc = await _load(survey_id, user)
    if category not in _CUST_CATS:
        category = "other"
    content = await file.read()
    if len(content) > _MAX_ATTACH_BYTES:
        raise HTTPException(413, "File too large (max 25MB)")
    att_id = str(uuid.uuid4())
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    storage_path = f"{APP_NAME}/surveys/{survey_id}/{att_id}.{ext}"
    content_type = file.content_type or "application/octet-stream"
    result = await run_in_threadpool(put_object, storage_path, content, content_type)
    att = {
        "id": att_id,
        "survey_id": survey_id,
        "organization_id": user.get("organization_id"),
        "category": category,
        "description": description,
        "original_filename": file.filename,
        "content_type": content_type,
        "size": len(content),
        "storage_path": result.get("path", storage_path),
        "is_deleted": False,
        "visible_to_installer": True,
        "visible_to_customer": True,
        "uploaded_by": user.get("id"),
        "uploaded_by_name": (user.get("full_name") or user.get("email") or "") + " (customer)",
        "source": "customer_portal",
        "created_at": _now(),
    }
    await db[ATTACH].insert_one(dict(att))
    is_plan = category == "floor_plans"
    set_fields = {"attachment_count": doc.get("attachment_count", 0) + 1, "updated_at": _now()}
    if is_plan:
        set_fields["has_floor_plan"] = True
    await db[SURVEYS].update_one({"id": survey_id}, {"$set": set_fields})
    await _log(survey_id, user, "customer_file_uploaded",
               new={"filename": file.filename, "category": category})
    return att
