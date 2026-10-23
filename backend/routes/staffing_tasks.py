"""Staffing Phase S4 — Tasks · Forms · Compliance.

Three operator-side subsystems bundled into one router because they
share the same audience (managers + on-shift staff) and lean on the
existing staffing helpers without duplicating them.

  1. Tasks & checklists ────────────────────────────────────────
     One-off, shift-linked, opening/closing, or recurring tasks
     with optional photo proof. Recurring templates *materialise*
     a fresh task per relevant day on demand (no cron worker —
     same trick we used for scheduled comms).

  2. Custom forms ───────────────────────────────────────────────
     Operators define a template (incident report, risk
     assessment, onboarding) with a typed field array. Staff
     submit values; submissions are immutable and timestamped.
     Field kinds: text, long_text, number, select, checkbox,
     date, signature (data-URL), photo (URL).

  3. Compliance & cert expiry ──────────────────────────────────
     Generic `staff_certs` collection (arbitrary types — DBS,
     First Aid, Safeguarding, Pool Plant, Lifeguard, NPLQ, etc.)
     plus a tracker endpoint that bands every cert by severity
     (expired / expiring 30d / 90d / ok) and returns a digest
     ready for an email or dashboard tile.

Endpoints
---------
Tasks:
    GET    /staffing/tasks
    POST   /staffing/tasks
    PATCH  /staffing/tasks/{task_id}
    POST   /staffing/tasks/{task_id}/complete
    POST   /staffing/tasks/{task_id}/uncomplete
    DELETE /staffing/tasks/{task_id}
    POST   /staffing/tasks/materialise        (manager — generates today's recurring instances)

Forms:
    GET    /staffing/forms/templates
    POST   /staffing/forms/templates
    PATCH  /staffing/forms/templates/{id}
    DELETE /staffing/forms/templates/{id}
    GET    /staffing/forms/templates/{id}
    GET    /staffing/forms/submissions
    POST   /staffing/forms/templates/{id}/submit

Compliance:
    GET    /staffing/compliance/certs           (per-staff certs)
    POST   /staffing/compliance/certs           (add cert)
    PATCH  /staffing/compliance/certs/{id}
    DELETE /staffing/compliance/certs/{id}
    GET    /staffing/compliance/tracker         (org-wide expiry digest)
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

# Re-use staffing helpers
from routes.staffing import (
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────── Constants / schemas ─────────────────────

TASK_KINDS = {"one_off", "shift_linked", "opening", "closing", "recurring"}
TASK_RECURRENCE = {"daily", "weekly", "monthly", None}

FORM_FIELD_KINDS = {
    "text", "long_text", "number", "select", "multiselect",
    "checkbox", "date", "signature", "photo",
}

CERT_SEVERITY_BANDS = [
    ("expired",   -10**9, 0),
    ("expiring_30",  0, 30),
    ("expiring_90", 30, 90),
    ("ok",         90, 10**9),
]


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    kind: str = "one_off"                 # one_off | shift_linked | opening | closing | recurring
    recurrence: str | None = None         # daily | weekly | monthly (only if kind=recurring)
    weekdays: list[int] = Field(default_factory=list)  # for weekly recurrence
    shift_id: str | None = None
    site_id: str | None = None
    assigned_staff_id: str | None = None
    role_filter: str | None = None
    due_at: str | None = None             # ISO-8601
    requires_photo: bool = False
    sort_order: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_staff_id: str | None = None
    role_filter: str | None = None
    due_at: str | None = None
    requires_photo: bool | None = None
    sort_order: int | None = None


class FormFieldDef(BaseModel):
    id: str | None = None
    kind: str
    label: str
    required: bool = False
    options: list[str] = Field(default_factory=list)
    placeholder: str | None = None
    help_text: str | None = None


class FormTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    fields: list[FormFieldDef] = Field(default_factory=list)
    audience_role: str | None = None      # managers can scope visibility


class FormTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[FormFieldDef] | None = None
    audience_role: str | None = None
    archived: bool | None = None


class CertCreate(BaseModel):
    staff_id: str
    cert_type: str                          # 'dbs' | 'first_aid' | 'safeguarding' | freeform
    cert_number: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    notes: str | None = None


class CertUpdate(BaseModel):
    cert_number: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    notes: str | None = None


# ─────────────────────── Helpers ─────────────────────────────────

def _strip(d: dict) -> dict:
    out = dict(d)
    out.pop("_id", None)
    return out


async def _can_complete_task(t: dict, user: dict, my_staff_id: str | None) -> bool:
    """Operators can always tick anything; staff can tick if they
    are the assignee, no assignee was set (open task), or they
    match the role_filter."""
    if _is_manager(user):
        return True
    if not my_staff_id:
        return False
    if t.get("assigned_staff_id") in (None, "", my_staff_id):
        # Optionally narrow by role
        rf = t.get("role_filter")
        if rf:
            sm = await db.staff_members.find_one(
                {"id": my_staff_id, "organization_id": t.get("organization_id")},
                {"_id": 0, "primary_role": 1},
            )
            return bool(sm and sm.get("primary_role") == rf)
        return True
    return False


def _band_for_cert(expires_at: str | None) -> str:
    """Return one of: expired | expiring_30 | expiring_90 | ok | unknown."""
    if not expires_at:
        return "unknown"
    try:
        exp = datetime.fromisoformat(expires_at).date()
    except ValueError:
        return "unknown"
    today = _now().date()
    delta_days = (exp - today).days
    for label, lo, hi in CERT_SEVERITY_BANDS:
        if lo <= delta_days < hi:
            return label
    return "ok"


# ═══════════════════════ TASKS ═══════════════════════════════════

@router.get("/staffing/tasks")
async def list_tasks(
    date: str | None = Query(None),
    shift_id: str | None = Query(None),
    status_f: str | None = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
):
    """List tasks visible to the caller.

    `date` filters to that day's due (incl. recurring instances).
    Staff only see their own assignments + open tasks; managers see all.
    """
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if shift_id:
        q["shift_id"] = shift_id
    if status_f in ("open", "completed"):
        q["status"] = status_f
    if date:
        # Match either exact due_at YYYY-MM-DD prefix or recurring with weekday match
        d_iso = date
        try:
            wkday = datetime.fromisoformat(date).weekday()
        except ValueError as err:
            raise HTTPException(400, "date must be YYYY-MM-DD") from err
        q["$or"] = [
            {"due_at": {"$regex": f"^{d_iso}"}},
            {"kind": "recurring", "recurrence": "daily"},
            {"kind": "recurring", "recurrence": "weekly", "weekdays": wkday},
        ]
    if not _is_manager(user):
        # Staff: my assignments OR unassigned + matching role
        sub = [{"assigned_staff_id": sid}, {"assigned_staff_id": {"$in": [None, ""]}}]
        # AND with the existing $or — wrap with $and
        existing_or = q.pop("$or", None)
        and_clauses = [{"$or": sub}]
        if existing_or:
            and_clauses.append({"$or": existing_or})
        if and_clauses:
            q["$and"] = and_clauses
    rows = await db.staff_tasks.find(q, {"_id": 0}).sort([("sort_order", 1), ("due_at", 1)]).to_list(500)
    return {"tasks": rows, "my_staff_id": sid, "is_manager": _is_manager(user)}


@router.post("/staffing/tasks")
async def create_task(body: TaskCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    if body.kind not in TASK_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(TASK_KINDS)}")
    if body.kind == "recurring":
        if body.recurrence not in TASK_RECURRENCE:
            raise HTTPException(400, "Invalid recurrence")
        if body.recurrence == "weekly" and not body.weekdays:
            raise HTTPException(400, "weekly recurrence needs at least one weekday (0..6)")
    now_iso = _now().isoformat()
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "title": body.title.strip(),
        "description": (body.description or "").strip() or None,
        "kind": body.kind,
        "recurrence": body.recurrence,
        "weekdays": list(body.weekdays or []),
        "shift_id": body.shift_id,
        "site_id": body.site_id,
        "assigned_staff_id": body.assigned_staff_id,
        "role_filter": body.role_filter,
        "due_at": body.due_at,
        "requires_photo": bool(body.requires_photo),
        "sort_order": int(body.sort_order or 0),
        "status": "open",
        "completed_at": None,
        "completed_by": None,
        "completed_photo_url": None,
        "archived": False,
        "created_at": now_iso,
        "created_by": user.get("email"),
    }
    await db.staff_tasks.insert_one(doc.copy())
    return _strip(doc)


@router.patch("/staffing/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_tasks.update_one(
        {"id": task_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Task not found")
    return await db.staff_tasks.find_one({"id": task_id}, {"_id": 0})


@router.post("/staffing/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    t = await db.staff_tasks.find_one({"id": task_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    sid = await _my_staff_id_async(user, org_id)
    if not await _can_complete_task(t, user, sid):
        raise HTTPException(403, "Not your task")
    if t.get("requires_photo") and not body.get("photo_url"):
        raise HTTPException(400, "This task requires a photo before completion.")
    patch = {
        "status": "completed",
        "completed_at": _now().isoformat(),
        "completed_by": sid or user.get("email"),
        "completed_photo_url": body.get("photo_url"),
        "completion_notes": body.get("notes"),
    }
    await db.staff_tasks.update_one(
        {"id": task_id, "organization_id": org_id}, {"$set": patch},
    )
    return {"ok": True, "task": {**t, **patch}}


@router.post("/staffing/tasks/{task_id}/uncomplete")
async def uncomplete_task(task_id: str, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    t = await db.staff_tasks.find_one({"id": task_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    if not _is_manager(user) and t.get("completed_by") != await _my_staff_id_async(user, org_id):
        raise HTTPException(403, "Only the completer or a manager can undo")
    await db.staff_tasks.update_one(
        {"id": task_id, "organization_id": org_id},
        {"$set": {"status": "open", "completed_at": None, "completed_by": None, "completed_photo_url": None}},
    )
    return {"ok": True}


@router.delete("/staffing/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_tasks.update_one(
        {"id": task_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@router.post("/staffing/tasks/materialise")
async def materialise_recurring(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Stamp instances of recurring task templates for `date` (default
    today). Each generated instance is a one-off task with
    `parent_template_id` pointing back to the recurring template, so
    completions are captured without polluting the template itself.
    Idempotent: instances are de-duped on (parent_template_id, due_at)."""
    _require_manager(user)
    org_id = _org(user)
    date_str = body.get("date") or _now().date().isoformat()
    try:
        d = datetime.fromisoformat(date_str).date()
    except ValueError as err:
        raise HTTPException(400, "date must be YYYY-MM-DD") from err
    wkday = d.weekday()
    templates = await db.staff_tasks.find(
        {
            "organization_id": org_id,
            "kind": "recurring",
            "archived": {"$ne": True},
            "$or": [
                {"recurrence": "daily"},
                {"recurrence": "weekly", "weekdays": wkday},
            ],
        },
        {"_id": 0},
    ).to_list(500)
    created = 0
    skipped = 0
    for tpl in templates:
        due_iso = f"{d.isoformat()}T{(tpl.get('due_at') or '23:59:00').split('T')[-1]}"
        existing = await db.staff_tasks.find_one(
            {
                "organization_id": org_id,
                "parent_template_id": tpl["id"],
                "due_at": {"$regex": f"^{d.isoformat()}"},
                "archived": {"$ne": True},
            },
            {"_id": 0, "id": 1},
        )
        if existing:
            skipped += 1
            continue
        instance = {
            "id": str(uuid4()),
            "organization_id": org_id,
            "title": tpl["title"],
            "description": tpl.get("description"),
            "kind": "one_off",
            "parent_template_id": tpl["id"],
            "shift_id": None,
            "site_id": tpl.get("site_id"),
            "assigned_staff_id": tpl.get("assigned_staff_id"),
            "role_filter": tpl.get("role_filter"),
            "due_at": due_iso,
            "requires_photo": tpl.get("requires_photo", False),
            "sort_order": tpl.get("sort_order", 0),
            "status": "open",
            "completed_at": None,
            "completed_by": None,
            "archived": False,
            "created_at": _now().isoformat(),
            "created_by": "auto:materialise",
        }
        await db.staff_tasks.insert_one(instance.copy())
        created += 1
    return {"ok": True, "date": date_str, "created": created, "skipped": skipped}


# ═══════════════════════ FORMS ═══════════════════════════════════

@router.get("/staffing/forms/templates")
async def list_form_templates(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    rows = await db.staff_form_templates.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    # Filter by audience for non-managers
    if not _is_manager(user):
        sm = await db.staff_members.find_one(
            {"email": user.get("email"), "organization_id": org_id},
            {"_id": 0, "primary_role": 1},
        )
        my_role = (sm or {}).get("primary_role")
        rows = [r for r in rows if not r.get("audience_role") or r.get("audience_role") == my_role]
    return {"templates": rows}


@router.post("/staffing/forms/templates")
async def create_form_template(body: FormTemplateCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    fields = []
    for f in body.fields or []:
        if f.kind not in FORM_FIELD_KINDS:
            raise HTTPException(400, f"Field kind '{f.kind}' is not allowed")
        fields.append({
            "id": f.id or str(uuid4()),
            "kind": f.kind,
            "label": f.label.strip()[:120],
            "required": bool(f.required),
            "options": f.options or [],
            "placeholder": f.placeholder,
            "help_text": f.help_text,
        })
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "name": body.name.strip()[:120],
        "description": (body.description or "").strip() or None,
        "audience_role": body.audience_role,
        "fields": fields,
        "archived": False,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    }
    await db.staff_form_templates.insert_one(doc.copy())
    return _strip(doc)


@router.get("/staffing/forms/templates/{tpl_id}")
async def get_form_template(tpl_id: str, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    tpl = await db.staff_form_templates.find_one(
        {"id": tpl_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not tpl:
        raise HTTPException(404, "Template not found")
    return tpl


@router.patch("/staffing/forms/templates/{tpl_id}")
async def update_form_template(
    tpl_id: str, body: FormTemplateUpdate,
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name.strip()[:120]
    if body.description is not None:
        patch["description"] = body.description.strip() or None
    if body.audience_role is not None:
        patch["audience_role"] = body.audience_role or None
    if body.archived is not None:
        patch["archived"] = bool(body.archived)
    if body.fields is not None:
        out = []
        for f in body.fields:
            if f.kind not in FORM_FIELD_KINDS:
                raise HTTPException(400, f"Field kind '{f.kind}' is not allowed")
            out.append({
                "id": f.id or str(uuid4()),
                "kind": f.kind,
                "label": f.label.strip()[:120],
                "required": bool(f.required),
                "options": f.options or [],
                "placeholder": f.placeholder,
                "help_text": f.help_text,
            })
        patch["fields"] = out
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_form_templates.update_one(
        {"id": tpl_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Template not found")
    return await db.staff_form_templates.find_one({"id": tpl_id}, {"_id": 0})


@router.delete("/staffing/forms/templates/{tpl_id}")
async def delete_form_template(tpl_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_form_templates.update_one(
        {"id": tpl_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.post("/staffing/forms/templates/{tpl_id}/submit")
async def submit_form(
    tpl_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Validate values against the template fields and persist a
    submission. Submissions are immutable."""
    org_id = _org(user)
    tpl = await db.staff_form_templates.find_one(
        {"id": tpl_id, "organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    )
    if not tpl:
        raise HTTPException(404, "Template not found")
    values = body.get("values") or {}
    if not isinstance(values, dict):
        raise HTTPException(400, "values must be an object")
    # Required-field check
    for f in tpl.get("fields", []):
        if f.get("required"):
            v = values.get(f["id"])
            empty = v in (None, "", [])
            if empty:
                raise HTTPException(400, f"Missing required field: {f['label']}")
    sid = await _my_staff_id_async(user, org_id)
    sub = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "template_id": tpl_id,
        "template_name_snapshot": tpl.get("name"),
        "submitted_by": user.get("email"),
        "submitted_by_staff_id": sid,
        "submitted_at": _now().isoformat(),
        "values": values,
        "status": body.get("status") or "submitted",
        "linked_shift_id": body.get("linked_shift_id"),
    }
    await db.staff_form_submissions.insert_one(sub.copy())
    return _strip(sub)


@router.get("/staffing/forms/submissions")
async def list_form_submissions(
    template_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    q: dict = {"organization_id": org_id}
    if template_id:
        q["template_id"] = template_id
    if not _is_manager(user):
        q["submitted_by_staff_id"] = sid or "__none__"
    rows = await db.staff_form_submissions.find(q, {"_id": 0}).sort("submitted_at", -1).limit(500).to_list(500)
    return {"submissions": rows, "count": len(rows)}


# ═══════════════════════ COMPLIANCE ══════════════════════════════

@router.get("/staffing/compliance/certs")
async def list_certs(
    staff_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """List certs. Staff see only their own; managers see everything
    (optionally filtered by `staff_id`)."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    sid = await _my_staff_id_async(user, org_id)
    if not _is_manager(user):
        q["staff_id"] = sid or "__none__"
    elif staff_id:
        q["staff_id"] = staff_id
    rows = await db.staff_certs.find(q, {"_id": 0}).sort([("staff_id", 1), ("expires_at", 1)]).to_list(2000)
    for r in rows:
        r["severity"] = _band_for_cert(r.get("expires_at"))
    return {"certs": rows}


@router.post("/staffing/compliance/certs")
async def add_cert(body: CertCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    sm = await db.staff_members.find_one(
        {"id": body.staff_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if not sm:
        raise HTTPException(404, "Staff not found")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": body.staff_id,
        "cert_type": body.cert_type.strip()[:60],
        "cert_number": (body.cert_number or "").strip() or None,
        "issued_at": body.issued_at,
        "expires_at": body.expires_at,
        "notes": (body.notes or "").strip() or None,
        "archived": False,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
    }
    await db.staff_certs.insert_one(doc.copy())
    out = _strip(doc)
    out["severity"] = _band_for_cert(out["expires_at"])
    return out


@router.patch("/staffing/compliance/certs/{cert_id}")
async def update_cert(cert_id: str, body: CertUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_certs.update_one(
        {"id": cert_id, "organization_id": org_id}, {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Cert not found")
    out = await db.staff_certs.find_one({"id": cert_id}, {"_id": 0})
    out["severity"] = _band_for_cert(out.get("expires_at"))
    return out


@router.delete("/staffing/compliance/certs/{cert_id}")
async def delete_cert(cert_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_certs.update_one(
        {"id": cert_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Cert not found")
    return {"ok": True}


@router.get("/staffing/compliance/tracker")
async def compliance_tracker(user: dict = Depends(get_current_user)):
    """Org-wide expiry digest grouped by severity. Powers the
    compliance dashboard tile + auto-reminder digest."""
    _require_manager(user)
    org_id = _org(user)
    certs = await db.staff_certs.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    ).to_list(5000)
    from routes.staffing import scoped_staff_filter
    _scope = await scoped_staff_filter(user, org_id)
    staff = {
        s["id"]: s async for s in db.staff_members.find(
            {"organization_id": org_id, "active": True, **_scope},
            {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1, "email": 1},
        )
    }
    buckets = {"expired": [], "expiring_30": [], "expiring_90": [], "ok": [], "unknown": []}
    for c in certs:
        sev = _band_for_cert(c.get("expires_at"))
        s = staff.get(c.get("staff_id")) or {}
        buckets[sev].append({
            **c,
            "severity": sev,
            "staff_name": s.get("full_name"),
            "primary_role": s.get("primary_role"),
            "staff_email": s.get("email"),
        })
    summary = {k: len(v) for k, v in buckets.items()}
    # Staff with no cert at all (gaps):
    cert_staff_ids = {c.get("staff_id") for c in certs}
    missing_staff = [
        {"staff_id": sid, "staff_name": s.get("full_name"), "primary_role": s.get("primary_role")}
        for sid, s in staff.items()
        if sid not in cert_staff_ids
    ]
    return {
        "as_of": _now().isoformat(),
        "summary": summary,
        "buckets": buckets,
        "missing_staff": missing_staff,
        "missing_count": len(missing_staff),
    }
