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
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.dual_auth import get_current_user_or_crm as get_current_user
from utils.database import db

from routes.staffing import (
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
    _resolve_staff_login_flags,
    grant_viewer_can_see,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ───────────────── Pydantic schemas ──────────────────────────────

PROFILE_FIELDS = {
    "address_line1", "address_line2", "city", "postcode", "country",
    "date_of_birth", "ni_number", "contract_type", "hours_per_week",
    "hire_date", "termination_date", "termination_reason",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
    "bank_name", "bank_sort_code", "bank_account", "bank_account_last4",
    "right_to_work_status", "notes",
    "dbs_number", "dbs_expiry_date",
}


# Personal / financial fields hidden from cross-department grant viewers.
_GRANT_VIEWER_HIDDEN = (
    "address_line1", "address_line2", "city", "postcode", "date_of_birth", "ni_number",
    "bank_name", "bank_sort_code", "bank_account", "bank_account_last4", "hourly_cost",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
)


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
    bank_account: str | None = None
    bank_account_last4: str | None = None
    right_to_work_status: str | None = None
    notes: str | None = None
    dbs_number: str | None = None
    dbs_expiry_date: str | None = None


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
    other = False
    if not _is_manager(user) and staff_id != await _my_staff_id_async(user, org_id) \
            and await grant_viewer_can_see(user, org_id, staff_id):
        other = True  # cross-department grant holder — read-only, scrubbed
    else:
        await _check_view_scope(user, org_id, staff_id)
    sm = await _staff_or_404(org_id, staff_id)
    if other:
        for k in _GRANT_VIEWER_HIDDEN:
            sm.pop(k, None)
    # Recognise whether this person already has / was sent a platform login so
    # the UI can show "Re-issue login" vs "Invite to platform".
    await _resolve_staff_login_flags(org_id, [sm])
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
    # Iter 216h241 — mirror hours_per_week → weekly_hours so the staff
    # list (which reads ``weekly_hours``) and the HR profile (which
    # writes ``hours_per_week``) never disagree.
    if "hours_per_week" in patch:
        patch["weekly_hours"] = patch["hours_per_week"]
    # Full account number edited → refresh the derived last-4 display field.
    if "bank_account" in patch:
        from utils.personal_sync import _last4
        patch["bank_account_last4"] = _last4(patch["bank_account"])
    await db.staff_members.update_one(
        {"id": staff_id, "organization_id": org_id}, {"$set": patch},
    )
    # Unify: mirror the personal fields HR just edited back into the sign-up
    # form data so the Staff Portal My Details tab stays in sync.
    from utils.personal_sync import sync_from_staff
    await sync_from_staff(db, org_id, staff_id, patch)
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



# ═════════════════ Offboarding / Leaver workflow ═════════════════
# A guided leaver process: HR records the last working day + reason, works
# through a return-of-property / access-revocation checklist, then completes
# the case — which archives the staff record, sets the termination fields and
# REVOKES the person's login (auth record disabled + live JWTs invalidated).

OFFBOARDING_CHECKLIST = [
    ("return_keys", "Return keys / entry fob"),
    ("return_uniform", "Return uniform / PPE"),
    ("return_equipment", "Return equipment (laptop, phone, tools)"),
    ("return_vehicle", "Return company vehicle"),
    ("revoke_building", "Revoke building / gym access"),
    ("revoke_systems", "Revoke portal & system access"),
    ("final_timesheet", "Final timesheet approved"),
    ("final_pay", "Flag final pay to payroll"),
    ("exit_interview", "Exit interview completed"),
    ("p45", "P45 / leaver documents issued"),
]


class OffboardStart(BaseModel):
    reason: str | None = None
    last_working_day: str | None = None
    notice_date: str | None = None


class OffboardPatch(BaseModel):
    checklist: dict | None = None
    notes: str | None = None
    reason: str | None = None
    last_working_day: str | None = None
    exit_interview_notes: str | None = None


def _new_checklist() -> list[dict]:
    return [{"key": k, "label": lbl, "done": False, "done_at": None} for k, lbl in OFFBOARDING_CHECKLIST]


@router.get("/staffing/offboarding")
async def list_offboarding(status: str = Query("all"), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if status and status != "all":
        q["status"] = status
    rows = await db.staff_offboarding_cases.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        s = await db.staff_members.find_one({"id": r.get("staff_id")}, {"_id": 0, "full_name": 1, "primary_role": 1, "photo_url": 1}) or {}
        r["person"] = {"full_name": s.get("full_name"), "primary_role": s.get("primary_role"), "photo_url": s.get("photo_url")}
    in_progress = await db.staff_offboarding_cases.count_documents({"organization_id": org_id, "status": "in_progress"})
    return {"cases": rows, "in_progress": in_progress}


@router.get("/staffing/offboarding/{staff_id}")
async def get_offboarding(staff_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    case = await db.staff_offboarding_cases.find_one({"staff_id": staff_id, "organization_id": org_id}, {"_id": 0})
    return {"exists": bool(case), "case": case}


@router.post("/staffing/offboarding/{staff_id}/start")
async def start_offboarding(staff_id: str, body: OffboardStart, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    staff = await _staff_or_404(org_id, staff_id)
    existing = await db.staff_offboarding_cases.find_one({"staff_id": staff_id, "organization_id": org_id})
    if existing and existing.get("status") == "in_progress":
        return _strip(existing)
    case = {
        "id": str(uuid4()), "organization_id": org_id, "staff_id": staff_id,
        "staff_name": staff.get("full_name"), "status": "in_progress",
        "reason": (body.reason or "").strip(), "last_working_day": body.last_working_day,
        "notice_date": body.notice_date, "checklist": _new_checklist(),
        "notes": "", "exit_interview_notes": "",
        "initiated_by": user.get("full_name"), "created_at": _now().isoformat(),
        "completed_at": None, "completed_by": None,
    }
    await db.staff_offboarding_cases.replace_one(
        {"staff_id": staff_id, "organization_id": org_id}, case, upsert=True)
    return _strip(case)


@router.patch("/staffing/offboarding/{staff_id}")
async def update_offboarding(staff_id: str, body: OffboardPatch, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    case = await db.staff_offboarding_cases.find_one({"staff_id": staff_id, "organization_id": org_id})
    if not case:
        raise HTTPException(404, "No offboarding case — start one first.")
    if case.get("status") == "complete":
        raise HTTPException(400, "This offboarding has already been completed.")
    patch: dict = {}
    if body.checklist is not None:
        items = case.get("checklist") or _new_checklist()
        now = _now().isoformat()
        for it in items:
            if it["key"] in body.checklist:
                it["done"] = bool(body.checklist[it["key"]])
                it["done_at"] = now if it["done"] else None
        patch["checklist"] = items
    for fld in ("notes", "reason", "last_working_day", "exit_interview_notes"):
        val = getattr(body, fld)
        if val is not None:
            patch[fld] = val.strip() if isinstance(val, str) else val
    patch["updated_at"] = _now().isoformat()
    await db.staff_offboarding_cases.update_one({"id": case["id"]}, {"$set": patch})
    return await db.staff_offboarding_cases.find_one({"id": case["id"]}, {"_id": 0})


@router.post("/staffing/offboarding/{staff_id}/complete")
async def complete_offboarding(staff_id: str, user: dict = Depends(get_current_user)):
    """Finalise the leaver: set termination fields, archive the staff record and
    REVOKE their login (auth disabled + live sessions invalidated)."""
    _require_manager(user)
    org_id = _org(user)
    case = await db.staff_offboarding_cases.find_one({"staff_id": staff_id, "organization_id": org_id})
    if not case:
        raise HTTPException(404, "No offboarding case — start one first.")
    if case.get("status") == "complete":
        raise HTTPException(400, "This offboarding has already been completed.")
    staff = await _staff_or_404(org_id, staff_id)
    lwd = case.get("last_working_day")
    await db.staff_members.update_one(
        {"id": staff_id, "organization_id": org_id},
        {"$set": {"active": False, "archived_at": _now().isoformat(), "lifecycle_stage": "leaver",
                  "termination_date": lwd, "termination_reason": case.get("reason"),
                  "updated_at": _now().isoformat()}})
    uid = staff.get("user_id")
    if uid:
        await db.users.update_one(
            {"id": uid},
            {"$set": {"active": False, "tokens_revoked_before": int(_now().timestamp()),
                      "updated_at": _now().isoformat()}})
    await db.staff_offboarding_cases.update_one(
        {"id": case["id"]},
        {"$set": {"status": "complete", "completed_at": _now().isoformat(),
                  "completed_by": user.get("full_name"), "access_revoked": bool(uid)}})
    return {"ok": True, "access_revoked": bool(uid), "termination_date": lwd}


# ═════════════════ Full Employee File export (PDF / Excel) ═════════════════
# One-click, audit/SAR-ready record spanning personal + employment + onboarding
# + documents + attendance/pay + leave + disciplinary + training.

def _fv(v):
    return "" if v is None else str(v)


async def _employee_file_data(org_id: str, staff: dict) -> dict:
    sid = staff["id"]
    case = await db.staff_onboarding_cases.find_one({"staff_id": sid, "organization_id": org_id}) or {}
    emp = case.get("employment_proposal") or {}
    rate = float(staff.get("hourly_cost") or 0)

    kv = [
        ("Personal", [
            ("Full name", staff.get("full_name")),
            ("Date of birth", staff.get("date_of_birth")),
            ("National Insurance", staff.get("ni_number")),
            ("Email", staff.get("email")),
            ("Address", ", ".join([x for x in [staff.get("address_line1"), staff.get("address_line2"),
                                               staff.get("city"), staff.get("postcode")] if x])),
            ("Emergency contact", staff.get("emergency_contact_name")),
            ("Emergency phone", staff.get("emergency_contact_phone")),
            ("Emergency relationship", staff.get("emergency_contact_relationship")),
            ("Bank", staff.get("bank_name")),
            ("Sort code", staff.get("bank_sort_code")),
            ("Account (last 4)", staff.get("bank_account_last4")),
        ]),
        ("Employment", [
            ("Primary role", staff.get("primary_role")),
            ("Department", staff.get("department")),
            ("Job title", emp.get("job_title") or emp.get("position")),
            ("Employment type", emp.get("employment_type") or staff.get("contract_type")),
            ("Line manager", emp.get("line_manager")),
            ("Hours / week", staff.get("hours_per_week") or emp.get("hours_per_week")),
            ("Hourly rate", f"£{rate:.2f}" if rate else ""),
            ("Hire / start date", staff.get("hire_date") or emp.get("proposed_start_date")),
            ("Right to work", staff.get("right_to_work_status")),
            ("Status", "Leaver" if staff.get("active") is False else "Active"),
            ("Termination date", staff.get("termination_date")),
            ("Termination reason", staff.get("termination_reason")),
        ]),
        ("Onboarding", [
            ("Case status", case.get("status")),
            ("Forms submitted", "Yes" if case.get("submitted") else "No"),
            ("Offer status", (case.get("offer") or {}).get("status")),
            ("Contract status", (case.get("contract") or {}).get("status")),
            ("Paperwork complete", "Yes" if case.get("paperwork_complete") else "No"),
            ("Activated at", (case.get("activated_at") or "")[:16].replace("T", " ")),
        ]),
    ]

    docs = await db.staff_documents.find({"staff_id": sid, "organization_id": org_id}, {"_id": 0}).to_list(200)
    leave = await db.staff_leave_requests.find({"staff_id": sid, "organization_id": org_id}, {"_id": 0}).sort("start_date", -1).to_list(200)
    disc = await db.staff_disciplinary.find({"staff_id": sid, "organization_id": org_id}, {"_id": 0}).sort("occurred_at", -1).to_list(200)
    train = await db.staff_training.find({"staff_id": sid, "organization_id": org_id}, {"_id": 0}).sort("completed_at", -1).to_list(200)

    # Attendance & pay — compute per recent stored week.
    pay_rows, tot_hours, tot_pay = [], 0.0, 0.0
    try:
        from routes.staffing_clock import _ensure_timesheet_doc, _week_bounds
        weeks = await db.staff_timesheets.find({"staff_id": sid, "organization_id": org_id}, {"_id": 0, "week_start": 1}).sort("week_start", -1).to_list(16)
        for w in weeks:
            ws, we = _week_bounds(w["week_start"])
            ts = await _ensure_timesheet_doc(org_id, sid, ws, we)
            ah = round(ts.get("actual_hours", 0), 2)
            pay = round(ah * rate, 2)
            tot_hours += ah; tot_pay += pay
            pay_rows.append([ws, f"{ah:.2f}", f"{ts.get('overtime_hours', 0):g}",
                             (ts.get("approval_status") or "").title(), f"£{pay:.2f}"])
    except Exception:
        pass

    tables = [
        ("Documents", ["Name", "Type", "Expires", "Notes"],
         [[d.get("name"), d.get("kind"), d.get("expires_at"), d.get("notes")] for d in docs]),
        ("Attendance & Pay", ["Week", "Hours", "Overtime", "Status", "Pay"],
         pay_rows + ([["TOTAL", f"{tot_hours:.2f}", "", "", f"£{tot_pay:.2f}"]] if pay_rows else [])),
        ("Leave", ["Type", "From", "To", "Status", "Reason"],
         [[l.get("leave_type"), l.get("start_date"), l.get("end_date"), l.get("status"), l.get("reason")] for l in leave]),
        ("Disciplinary", ["Date", "Severity", "Summary", "Actions agreed", "Resolved"],
         [[d.get("occurred_at"), d.get("severity"), d.get("summary"), d.get("actions_agreed"), d.get("resolved_at")] for d in disc]),
        ("Training", ["Course", "Provider", "Completed", "Expires", "Score"],
         [[t.get("course_name"), t.get("provider"), t.get("completed_at"), t.get("expires_at"), t.get("score")] for t in train]),
    ]
    return {"name": staff.get("full_name") or "Employee", "kv": kv, "tables": tables}


def _emp_xlsx(f: dict, brand: dict | None = None) -> bytes:
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from utils.export_branding import xlsx_brand_band
    wb = Workbook(); wb.remove(wb.active)
    thin = Side(style="thin", color="D0D5DD"); border = Border(thin, thin, thin, thin)
    head = PatternFill("solid", fgColor="0B0C10"); hfont = Font(bold=True, color="FFFFFF")
    lab = Font(bold=True, color="475467")
    ws = wb.create_sheet("Summary")
    o = xlsx_brand_band(ws, brand)
    tr = o + 1
    ws.cell(tr, 1, f"EMPLOYEE FILE — {f['name']}").font = Font(bold=True, size=15)
    r = tr + 2
    for title, kvs in f["kv"]:
        ws.cell(r, 1, title).font = Font(bold=True, size=12, color="0E7490"); r += 1
        for k, v in kvs:
            ws.cell(r, 1, k).font = lab; ws.cell(r, 2, v if v is None else str(v)); r += 1
        r += 1
    ws.column_dimensions["A"].width = 26; ws.column_dimensions["B"].width = 52
    for title, cols, rows in f["tables"]:
        sh = wb.create_sheet(title[:28])
        for c, col in enumerate(cols, 1):
            cell = sh.cell(1, c, col); cell.fill = head; cell.font = hfont; cell.border = border
        for i, row in enumerate(rows, 2):
            for c, val in enumerate(row, 1):
                cell = sh.cell(i, c, "" if val is None else str(val)); cell.border = border
        for c in range(1, len(cols) + 1):
            sh.column_dimensions[chr(64 + c)].width = 22
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _emp_pdf(f: dict, brand: dict | None = None) -> bytes:
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from utils.export_branding import pdf_brand_header
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#0E7490"), spaceBefore=8, spaceAfter=3)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=8, leading=10)
    story = pdf_brand_header(brand) + [Paragraph(f"Employee File — {f['name']}", h1)]
    for title, kvs in f["kv"]:
        story.append(Paragraph(title, h2))
        data = [[Paragraph(f"<b>{k}</b>", cell), Paragraph(_fv(v), cell)] for k, v in kvs]
        t = Table(data, colWidths=[55 * mm, 122 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story.append(t)
    for title, cols, rows in f["tables"]:
        story.append(Paragraph(f"{title} ({len(rows)})", h2))
        if not rows:
            story.append(Paragraph("<i>No records.</i>", cell)); continue
        data = [cols] + [[Paragraph(_fv(x), cell) for x in row] for row in rows]
        n = len(cols); w = (182 * mm) / n
        t = Table(data, colWidths=[w] * n, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B0C10")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 4))
    doc.build(story)
    return buf.getvalue()


@router.get("/staffing/staff/{staff_id}/employee-file")
async def export_employee_file(staff_id: str, format: str = Query("pdf"),
                               user: dict = Depends(get_current_user)):
    """Download a full employee file (PDF or Excel) for audits / SARs."""
    _require_manager(user)
    org_id = _org(user)
    staff = await _staff_or_404(org_id, staff_id)
    f = await _employee_file_data(org_id, staff)
    from utils.export_branding import resolve_export_brand
    brand = await resolve_export_brand(db, org_id)
    from fastapi.responses import Response
    safe = (staff.get("full_name") or "employee").replace(" ", "_")
    if (format or "pdf").lower() == "xlsx":
        return Response(content=_emp_xlsx(f, brand),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="employee-file-{safe}.xlsx"'})
    return Response(content=_emp_pdf(f, brand), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="employee-file-{safe}.pdf"'})
