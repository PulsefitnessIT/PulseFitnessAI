"""Staffing Phase S5 — HR 2.0.

Adds the operator-facing HR surface that the Phase S1-S4 sprints
were missing:

  • Employee profile 2.0 — emergency contacts, address, DOB, NI
    number, contract type, hire/term dates. Embedded directly on
    `staff_members` so existing endpoints continue to return it
    without a join.
  • Documents — contracts, ID, onboarding paperwork stored as
    URLs in `staff_documents` (full file-upload pipeline lands
    later). Keeps a doc kind, expires_at, and uploaded_by.
  • Disciplinary records — incidents, warnings, suspensions,
    PIPs. Includes severity, summary, manager note, follow-up
    date. Soft-delete only; full audit trail.
  • Training history — courses completed (course name, provider,
    completed_at, expiry, score, notes). Plays alongside the
    Phase S4 cert tracker but captures *learning* events
    (in-house workshops, e-learning, refreshers) rather than
    formal certs.

Endpoints
---------
    GET    /staffing/hr/profile/{staff_id}          (decorated profile)
    PATCH  /staffing/hr/profile/{staff_id}          (manager — update HR fields)

    GET    /staffing/hr/documents
    POST   /staffing/hr/documents
    PATCH  /staffing/hr/documents/{id}
    DELETE /staffing/hr/documents/{id}

    GET    /staffing/hr/disciplinary
    POST   /staffing/hr/disciplinary
    PATCH  /staffing/hr/disciplinary/{id}
    DELETE /staffing/hr/disciplinary/{id}

    GET    /staffing/hr/training
    POST   /staffing/hr/training
    PATCH  /staffing/hr/training/{id}
    DELETE /staffing/hr/training/{id}

Visibility
----------
Each list endpoint accepts `?staff_id=...`. Without it, managers
see the whole org; staff see only their own records.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db

from routes.staffing import (
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ───────────────── Pydantic schemas ──────────────────────────────

PROFILE_FIELDS = {
    "address_line1", "address_line2", "city", "postcode", "country",
    "date_of_birth", "ni_number", "contract_type", "hours_per_week",
    "hire_date", "termination_date", "termination_reason",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
    "bank_name", "bank_sort_code", "bank_account_last4",
    "right_to_work_status", "notes",
}


class ProfileUpdate(BaseModel):
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postcode: str | None = None
    country: str | None = None
    date_of_birth: str | None = None
    ni_number: str | None = None
    contract_type: str | None = None
    hours_per_week: float | None = None
    hire_date: str | None = None
    termination_date: str | None = None
    termination_reason: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relationship: str | None = None
    bank_name: str | None = None
    bank_sort_code: str | None = None
    bank_account_last4: str | None = None
    right_to_work_status: str | None = None
    notes: str | None = None


class DocumentCreate(BaseModel):
    staff_id: str
    name: str
    kind: str = "contract"            # contract | id | onboarding | training | other
    url: str
    expires_at: str | None = None
    notes: str | None = None


class DocumentUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    url: str | None = None
    expires_at: str | None = None
    notes: str | None = None


class DisciplinaryCreate(BaseModel):
    staff_id: str
    occurred_at: str                   # ISO date
    severity: str = "verbal"           # verbal | written | final | suspension | dismissal
    summary: str
    actions_agreed: str | None = None
    follow_up_at: str | None = None
    confidential: bool = True
    manager_note: str | None = None


class DisciplinaryUpdate(BaseModel):
    severity: str | None = None
    summary: str | None = None
    actions_agreed: str | None = None
    follow_up_at: str | None = None
    resolved_at: str | None = None
    manager_note: str | None = None


class TrainingCreate(BaseModel):
    staff_id: str
    course_name: str
    provider: str | None = None
    completed_at: str | None = None
    expires_at: str | None = None
    score: float | None = None
    notes: str | None = None


class TrainingUpdate(BaseModel):
    course_name: str | None = None
    provider: str | None = None
    completed_at: str | None = None
    expires_at: str | None = None
    score: float | None = None
    notes: str | None = None


VALID_DOC_KINDS = {"contract", "id", "onboarding", "training", "policy", "other"}
VALID_SEVERITY = {"verbal", "written", "final", "suspension", "dismissal", "informal"}


# ───────────────── Helpers ───────────────────────────────────────

def _strip(d: dict) -> dict:
    out = dict(d)
    out.pop("_id", None)
    return out


async def _staff_or_404(org_id: str, staff_id: str) -> dict:
    sm = await db.staff_members.find_one(
        {"id": staff_id, "organization_id": org_id}, {"_id": 0},
    )
    if not sm:
        raise HTTPException(404, "Staff not found")
    return sm


async def _check_view_scope(user: dict, org_id: str, staff_id: str | None) -> str | None:
    """Return the staff_id we should restrict to (None = no restriction).
    Managers see everything; staff see only themselves. If a staff
    member asks about someone else, raise 403."""
    if _is_manager(user):
        return staff_id  # manager filter passes through
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(403, "No staff record linked to your account.")
    if staff_id and staff_id != sid:
        raise HTTPException(403, "Not your record")
    return sid


# ═══════════════════ PROFILE 2.0 ═════════════════════════════════

@router.get("/staffing/hr/profile/{staff_id}")
async def get_profile(staff_id: str, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    await _check_view_scope(user, org_id, staff_id)
    sm = await _staff_or_404(org_id, staff_id)
    # Safe profile: scrub sensitive fields for non-managers about *themselves* only.
    if not _is_manager(user):
        for k in ("bank_sort_code", "bank_account_last4", "ni_number"):
            sm.setdefault(k, None)
    return sm


@router.patch("/staffing/hr/profile/{staff_id}")
async def update_profile(
    staff_id: str,
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    """Manager-only update of HR profile fields. Existing core fields
    (full_name / role / hourly_cost) keep their dedicated endpoint to
    avoid scope creep on this one."""
    _require_manager(user)
    org_id = _org(user)
    await _staff_or_404(org_id, staff_id)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    # Whitelist guard
    patch = {k: v for k, v in patch.items() if k in PROFILE_FIELDS}
    if not patch:
        raise HTTPException(400, "No valid HR fields in payload")
    patch["hr_updated_at"] = _now().isoformat()
    patch["hr_updated_by"] = user.get("email")
    await db.staff_members.update_one(
        {"id": staff_id, "organization_id": org_id}, {"$set": patch},
    )
    return await db.staff_members.find_one({"id": staff_id}, {"_id": 0})


# ═══════════════════ DOCUMENTS ═══════════════════════════════════

@router.get("/staffing/hr/documents")
async def list_documents(
    staff_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    sid_filter = await _check_view_scope(user, org_id, staff_id)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if sid_filter:
        q["staff_id"] = sid_filter
    rows = await db.staff_documents.find(q, {"_id": 0}).sort("uploaded_at", -1).to_list(500)
    return {"documents": rows}


@router.post("/staffing/hr/documents")
async def add_document(body: DocumentCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _staff_or_404(org_id, body.staff_id)
    if body.kind not in VALID_DOC_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(VALID_DOC_KINDS)}")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": body.staff_id,
        "name": body.name.strip()[:120],
        "kind": body.kind,
        "url": body.url.strip(),
        "expires_at": body.expires_at,
        "notes": (body.notes or "").strip() or None,
        "archived": False,
        "uploaded_at": _now().isoformat(),
        "uploaded_by": user.get("email"),
    }
    await db.staff_documents.insert_one(doc.copy())
    return _strip(doc)


@router.patch("/staffing/hr/documents/{doc_id}")
async def update_document(
    doc_id: str, body: DocumentUpdate, user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    if "kind" in patch and patch["kind"] not in VALID_DOC_KINDS:
        raise HTTPException(400, "Invalid kind")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_documents.update_one(
        {"id": doc_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Document not found")
    return await db.staff_documents.find_one({"id": doc_id}, {"_id": 0})


@router.delete("/staffing/hr/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_documents.update_one(
        {"id": doc_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Document not found")
    return {"ok": True}


# ═══════════════════ DISCIPLINARY ════════════════════════════════

@router.get("/staffing/hr/disciplinary")
async def list_disciplinary(
    staff_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Disciplinary records — manager-only by default. A staff member
    can fetch their own (with confidential=true rows redacted)."""
    org_id = _org(user)
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        if not sid:
            raise HTTPException(403, "No staff record linked")
        if staff_id and staff_id != sid:
            raise HTTPException(403, "Not your record")
        rows = await db.staff_disciplinary.find(
            {"organization_id": org_id, "staff_id": sid, "archived": {"$ne": True}, "confidential": {"$ne": True}},
            {"_id": 0, "manager_note": 0},  # never expose manager note to staff
        ).sort("occurred_at", -1).to_list(200)
        return {"records": rows}
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if staff_id:
        q["staff_id"] = staff_id
    rows = await db.staff_disciplinary.find(q, {"_id": 0}).sort("occurred_at", -1).to_list(500)
    return {"records": rows}


@router.post("/staffing/hr/disciplinary")
async def add_disciplinary(body: DisciplinaryCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _staff_or_404(org_id, body.staff_id)
    if body.severity not in VALID_SEVERITY:
        raise HTTPException(400, f"severity must be one of {sorted(VALID_SEVERITY)}")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": body.staff_id,
        "occurred_at": body.occurred_at,
        "severity": body.severity,
        "summary": body.summary.strip()[:2000],
        "actions_agreed": (body.actions_agreed or "").strip() or None,
        "follow_up_at": body.follow_up_at,
        "confidential": bool(body.confidential),
        "manager_note": (body.manager_note or "").strip() or None,
        "resolved_at": None,
        "archived": False,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    }
    await db.staff_disciplinary.insert_one(doc.copy())
    return _strip(doc)


@router.patch("/staffing/hr/disciplinary/{rec_id}")
async def update_disciplinary(
    rec_id: str, body: DisciplinaryUpdate,
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    if "severity" in patch and patch["severity"] not in VALID_SEVERITY:
        raise HTTPException(400, "Invalid severity")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_disciplinary.update_one(
        {"id": rec_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Record not found")
    return await db.staff_disciplinary.find_one({"id": rec_id}, {"_id": 0})


@router.delete("/staffing/hr/disciplinary/{rec_id}")
async def delete_disciplinary(rec_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_disciplinary.update_one(
        {"id": rec_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Record not found")
    return {"ok": True}


# ═══════════════════ TRAINING ════════════════════════════════════

@router.get("/staffing/hr/training")
async def list_training(
    staff_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    sid_filter = await _check_view_scope(user, org_id, staff_id)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if sid_filter:
        q["staff_id"] = sid_filter
    rows = await db.staff_training.find(q, {"_id": 0}).sort("completed_at", -1).to_list(500)
    return {"records": rows}


@router.post("/staffing/hr/training")
async def add_training(body: TrainingCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _staff_or_404(org_id, body.staff_id)
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": body.staff_id,
        "course_name": body.course_name.strip()[:160],
        "provider": (body.provider or "").strip() or None,
        "completed_at": body.completed_at,
        "expires_at": body.expires_at,
        "score": body.score,
        "notes": (body.notes or "").strip() or None,
        "archived": False,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    }
    await db.staff_training.insert_one(doc.copy())
    return _strip(doc)


@router.patch("/staffing/hr/training/{rec_id}")
async def update_training(
    rec_id: str, body: TrainingUpdate, user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_training.update_one(
        {"id": rec_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Record not found")
    return await db.staff_training.find_one({"id": rec_id}, {"_id": 0})


@router.delete("/staffing/hr/training/{rec_id}")
async def delete_training(rec_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_training.update_one(
        {"id": rec_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Record not found")
    return {"ok": True}
