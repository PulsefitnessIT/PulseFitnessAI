"""
GymAxis Service Operations — Work Report custom fields.

Iter 220 — Allow engineers (and master admins) to define machine-specific
custom fields that appear on the Engineer App's job-complete screen and
are persisted onto the case + rendered into the customer Service Report.

Scope hierarchy (most specific wins for the resolved set returned to the
engineer):

    global               always shown
    equipment_type       shown when case.asset.equipment_type matches
    manufacturer         shown when case.asset.manufacturer matches
    model                shown when case.asset.model matches
    asset                shown only on that exact asset_id

Endpoints (all mounted under `/api`):

    GET    /svc/work-report-fields              list (paged) — admin/engineer config
    GET    /svc/work-report-fields/for-case/{id} resolved field set for a case
    POST   /svc/work-report-fields              create (admin or engineer)
    PATCH  /svc/work-report-fields/{id}         update
    DELETE /svc/work-report-fields/{id}         soft-archive

File-type fields reuse the standard `/api/files/upload?category=...`
endpoint — no dedicated upload route is needed here.
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc", tags=["Service Ops · Work Report Custom Fields"])

FIELD_TYPES = ("text", "number", "dropdown", "checkbox", "date", "file")
SCOPE_KINDS = ("global", "equipment_type", "manufacturer", "model", "asset")
SCOPE_SPECIFICITY = {
    "global": 0,
    "equipment_type": 1,
    "manufacturer": 2,
    "model": 3,
    "asset": 4,
}
# Iter 220du — parallel filter dimension. When a field has a
# non-empty job_types list it only resolves when the case's
# case_type is in the list; an empty list matches every job type
# (the default, fully backwards-compatible with iter 220 fields).
JOB_TYPES = ("repair", "ppm", "install", "inspection", "callout", "audit")
MAX_NAME_LEN = 60
MAX_FIELDS_PER_ORG = 200

# ─── Iter 220ea·14 · Suggested-field templates ────────────────────
# Out-of-the-box presets for new operators — pick a template and
# get 5–8 sensible custom fields seeded in one tap. Saves the
# cold-start "what should I even ask the engineer to capture?"
# problem for fitness-equipment operators who are setting up
# GymAxis for the first time. Templates are scoped to a single
# (scope_kind, scope_value) — typically `equipment_type=Treadmill`
# — and a job_types filter so engineers see the right set at the
# right moment.
#
# Templates are stored in code (not in the DB) because they're
# editorial content that ships with the platform; operators can
# subsequently edit/archive any seeded field like a normal field.

FIELD_TEMPLATES: list[dict] = [
    {
        "id": "treadmill_ppm",
        "name": "Treadmill PPM checklist",
        "scope_kind": "equipment_type",
        "scope_value": "Treadmill",
        "job_types": ["ppm"],
        "summary": "6 standard checks for a treadmill preventative maintenance visit.",
        "fields": [
            {"name": "Walking-belt tension (mm)", "field_type": "number", "required": True,
             "help_text": "Manufacturer spec usually 12-15 mm of deflection mid-belt."},
            {"name": "Walking-belt wear (cm)", "field_type": "number", "required": False,
             "help_text": "Measure thickness with calipers; replace if <2 mm thinner than new."},
            {"name": "Motor brush length (mm)", "field_type": "number", "required": False},
            {"name": "Deck waxed", "field_type": "checkbox", "required": True},
            {"name": "Console firmware version", "field_type": "text", "required": False},
            {"name": "Incline calibration verified", "field_type": "checkbox", "required": True},
        ],
    },
    {
        "id": "treadmill_repair",
        "name": "Treadmill repair report",
        "scope_kind": "equipment_type",
        "scope_value": "Treadmill",
        "job_types": ["repair"],
        "summary": "Fault-finding data points common to most treadmill repairs.",
        "fields": [
            {"name": "Fault code on console", "field_type": "text", "required": False,
             "help_text": "E.g. E02 / E06. Helps the customer report read clearly."},
            {"name": "Motor amp draw at 8 km/h (A)", "field_type": "number", "required": False},
            {"name": "Belt slip observed", "field_type": "checkbox", "required": False},
            {"name": "Drive belt condition",
             "field_type": "dropdown", "required": True,
             "options": ["New", "Good", "Acceptable", "Worn", "Replace"]},
            {"name": "Cable harness OK", "field_type": "checkbox", "required": False},
        ],
    },
    {
        "id": "cycle_ppm",
        "name": "Indoor cycle PPM",
        "scope_kind": "equipment_type",
        "scope_value": "Indoor Cycle",
        "job_types": ["ppm"],
        "summary": "5 checks for a Spinner / Indoor Cycle preventative service.",
        "fields": [
            {"name": "Crank-arm play",
             "field_type": "dropdown", "required": True,
             "options": ["None", "Slight", "Excessive — replace"]},
            {"name": "Brake-pad wear (mm)", "field_type": "number", "required": False},
            {"name": "Bottom bracket greased", "field_type": "checkbox", "required": True},
            {"name": "Saddle rail OK", "field_type": "checkbox", "required": False},
            {"name": "Console batteries replaced", "field_type": "checkbox", "required": False},
        ],
    },
    {
        "id": "rower_ppm",
        "name": "Rower PPM (Concept2 et al)",
        "scope_kind": "equipment_type",
        "scope_value": "Rower",
        "job_types": ["ppm"],
        "summary": "Standard Concept2/WaterRower PPM data points.",
        "fields": [
            {"name": "Drag factor (low)", "field_type": "number", "required": True,
             "help_text": "Concept2 PM5: target 100-130 at damper setting 1."},
            {"name": "Chain lubricated", "field_type": "checkbox", "required": True},
            {"name": "Shock cord tension OK", "field_type": "checkbox", "required": True},
            {"name": "Seat rollers worn", "field_type": "checkbox", "required": False},
            {"name": "PM monitor firmware", "field_type": "text", "required": False},
        ],
    },
    {
        "id": "strength_ppm",
        "name": "Strength station PPM",
        "scope_kind": "equipment_type",
        "scope_value": "Strength",
        "job_types": ["ppm"],
        "summary": "Cable, pulley, weight-stack PPM checklist.",
        "fields": [
            {"name": "Cable condition",
             "field_type": "dropdown", "required": True,
             "options": ["New", "Good", "Frayed — monitor", "Replace"]},
            {"name": "Pulleys spin freely", "field_type": "checkbox", "required": True},
            {"name": "Weight-pin chain OK", "field_type": "checkbox", "required": False},
            {"name": "Upholstery cracks", "field_type": "checkbox", "required": False},
            {"name": "Stack guide rods greased", "field_type": "checkbox", "required": True},
        ],
    },
    {
        "id": "installation_handover",
        "name": "Installation hand-over",
        "scope_kind": "global",
        "scope_value": None,
        "job_types": ["install"],
        "summary": "Final hand-over capture for any newly installed asset.",
        "fields": [
            {"name": "Serial number photographed", "field_type": "file", "required": True},
            {"name": "Customer present at hand-over",
             "field_type": "text", "required": True,
             "help_text": "Full name of person who signed off."},
            {"name": "Warranty terms explained", "field_type": "checkbox", "required": True},
            {"name": "Floor protector fitted", "field_type": "checkbox", "required": False},
            {"name": "Cleaning instructions given", "field_type": "checkbox", "required": True},
        ],
    },
]



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _slug(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip()).strip("_").lower()
    if not base:
        base = "field"
    return base[:40]


class WorkReportFieldIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LEN)
    field_type: str
    scope_kind: str = "global"
    scope_value: Optional[str] = None
    # Iter 220du — restrict to one or more job types. Empty list =
    # all job types (the historic behaviour).
    job_types: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    required: bool = False
    help_text: Optional[str] = None


class WorkReportFieldPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=MAX_NAME_LEN)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    help_text: Optional[str] = None
    job_types: Optional[list[str]] = None
    archived: Optional[bool] = None


def _validate_payload(p: WorkReportFieldIn) -> None:
    if p.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"field_type must be one of {FIELD_TYPES}")
    if p.scope_kind not in SCOPE_KINDS:
        raise HTTPException(400, f"scope_kind must be one of {SCOPE_KINDS}")
    if p.scope_kind != "global" and not (p.scope_value or "").strip():
        raise HTTPException(400, "scope_value is required when scope_kind is not 'global'")
    # Iter 220du — validate job-type filter when set.
    if p.job_types:
        for jt in p.job_types:
            if jt not in JOB_TYPES:
                raise HTTPException(400, f"job_types entries must be one of {JOB_TYPES}")
    if p.field_type == "dropdown":
        opts = [o.strip() for o in (p.options or []) if (o or "").strip()]
        if len(opts) < 2:
            raise HTTPException(400, "dropdown fields need at least 2 options")
        if len(opts) > 50:
            raise HTTPException(400, "dropdown fields can have at most 50 options")


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# CRUD endpoints
# ─────────────────────────────────────────────────────────────────


@router.get("/work-report-fields")
async def list_work_report_fields(
    include_archived: bool = Query(False),
    scope_kind: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    of = _of(user)
    q: dict = {**of}
    if not include_archived:
        q["archived"] = {"$ne": True}
    if scope_kind:
        q["scope_kind"] = scope_kind
    rows = (
        await db.svc_work_report_field_defs
        .find(q, {"_id": 0})
        .sort([("position", 1), ("created_at", 1)])
        .to_list(MAX_FIELDS_PER_ORG)
    )
    return {"fields": rows, "count": len(rows)}


@router.get("/work-report-fields/for-machine-row/{row_id}")
async def fields_for_machine_row(row_id: str, user=Depends(get_current_user)):
    """Iter 220i — resolve applicable custom-field defs for a single
    machine row in the Machines card. Same scoping rules as
    `for-case`, but anchored to the row's own asset link rather than
    the case-level asset.

    Returns the set of defs PLUS the row's already-saved values and
    the last-reading map keyed by field key, so the UI can pre-fill.
    """
    of = _of(user)
    row = await db.svc_work_visit_machines.find_one(
        {"id": row_id, **of},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Machine row not found")
    asset_id = row.get("asset_id") or ""
    asset = None
    if asset_id:
        asset = await db.equipment.find_one(
            {"id": asset_id, **of},
            {"_id": 0, "id": 1, "equipment_type": 1, "manufacturer": 1, "model": 1},
        )
    equipment_type = (asset or {}).get("equipment_type") or row.get("asset_type") or ""
    manufacturer = (asset or {}).get("manufacturer") or ""
    model = (asset or {}).get("model") or ""

    or_clauses: list[dict] = [{"scope_kind": "global"}]
    if equipment_type:
        or_clauses.append({"scope_kind": "equipment_type", "scope_value": equipment_type})
    if manufacturer:
        or_clauses.append({"scope_kind": "manufacturer", "scope_value": manufacturer})
    if model:
        or_clauses.append({"scope_kind": "model", "scope_value": model})
    if asset_id:
        or_clauses.append({"scope_kind": "asset", "scope_value": asset_id})

    # Iter 220du — pull the parent case's case_type so the per-row
    # resolver also filters by job type. Defaults to "repair" when
    # the row's case is missing the field (legacy cases).
    case_type_match = "repair"
    parent_case_id = row.get("case_id")
    if parent_case_id:
        parent = await db.svc_cases.find_one(
            {"id": parent_case_id, **of},
            {"_id": 0, "case_type": 1},
        )
        if parent and parent.get("case_type"):
            case_type_match = str(parent["case_type"]).lower()

    defs = await db.svc_work_report_field_defs.find(
        {**of, "archived": {"$ne": True}, "$or": or_clauses,
         "$and": [{"$or": [
             {"job_types": {"$exists": False}},
             {"job_types": {"$size": 0}},
             {"job_types": case_type_match},
         ]}]},
        {"_id": 0},
    ).sort([("position", 1), ("created_at", 1)]).to_list(MAX_FIELDS_PER_ORG)
    defs.sort(key=lambda r: (
        SCOPE_SPECIFICITY.get(r.get("scope_kind", "global"), 0),
        r.get("position", 0),
        r.get("created_at", ""),
    ))
    return {
        "fields": defs,
        "values": row.get("custom_fields") or {},
        "context": {
            "asset_id": asset_id,
            "equipment_type": equipment_type,
            "manufacturer": manufacturer,
            "model": model,
        },
    }


@router.get("/work-report-fields/for-case/{case_id}")
async def fields_for_case(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "asset_id": 1, "asset_name": 1,
         "asset_manufacturer": 1, "asset_model": 1, "asset_type": 1,
         "case_type": 1,
         "work_report_custom_fields": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    asset_id = case.get("asset_id") or ""
    asset = None
    if asset_id:
        asset = await db.equipment.find_one(
            {"id": asset_id, **of},
            {"_id": 0, "id": 1, "equipment_type": 1, "manufacturer": 1, "model": 1},
        )
    equipment_type = (asset or {}).get("equipment_type") or case.get("asset_type") or ""
    manufacturer = (asset or {}).get("manufacturer") or case.get("asset_manufacturer") or ""
    model = (asset or {}).get("model") or case.get("asset_model") or ""

    # Build a single $or against the field-defs collection.
    or_clauses: list[dict] = [{"scope_kind": "global"}]
    if equipment_type:
        or_clauses.append({"scope_kind": "equipment_type", "scope_value": equipment_type})
    if manufacturer:
        or_clauses.append({"scope_kind": "manufacturer", "scope_value": manufacturer})
    if model:
        or_clauses.append({"scope_kind": "model", "scope_value": model})
    if asset_id:
        or_clauses.append({"scope_kind": "asset", "scope_value": asset_id})

    # Iter 220du — case_type filter. Match defs that EITHER have no
    # job_types restriction (all-jobs, the historic behaviour) OR
    # explicitly include this case's case_type. Falls back to
    # `repair` so historic cases without a stamped type still
    # resolve a sensible set.
    case_type_match = (case.get("case_type") or "repair").lower()
    rows = await db.svc_work_report_field_defs.find(
        {**of, "archived": {"$ne": True}, "$or": or_clauses,
         "$and": [{"$or": [
             {"job_types": {"$exists": False}},
             {"job_types": {"$size": 0}},
             {"job_types": case_type_match},
         ]}]},
        {"_id": 0},
    ).sort([("position", 1), ("created_at", 1)]).to_list(MAX_FIELDS_PER_ORG)

    rows.sort(key=lambda r: (
        SCOPE_SPECIFICITY.get(r.get("scope_kind", "global"), 0),
        r.get("position", 0),
        r.get("created_at", ""),
    ))
    # Iter 220a — last-reading pre-fill. Pull the most recent prior case
    # on the same asset (or asset_name when the row isn't asset-linked)
    # that has a non-empty `work_report_custom_fields` map, and surface
    # those values so the engineer only has to update what changed.
    last_values: dict = {}
    last_values_meta: dict = {}
    field_keys = {r["key"] for r in rows}
    if field_keys:
        history_q: dict = {
            **of,
            "id": {"$ne": case_id},
            "work_report_custom_fields": {"$exists": True, "$ne": {}},
            "status": {"$in": ["repaired", "awaiting_sign_off", "closed", "invoiced"]},
        }
        asset_name = case.get("asset_name") or ""
        if asset_id:
            history_q["asset_id"] = asset_id
        elif asset_name:
            history_q["asset_name"] = asset_name
        else:
            history_q = {}  # no anchor → don't seed anything
        if history_q:
            prior = (
                await db.svc_cases.find(
                    history_q,
                    {"_id": 0, "id": 1, "reference": 1, "closed_at": 1,
                     "updated_at": 1, "work_report_custom_fields": 1,
                     "work_report_custom_fields_updated_at": 1},
                )
                .sort([("closed_at", -1), ("updated_at", -1)])
                .limit(10)
                .to_list(10)
            )
            for p in prior:
                cf = p.get("work_report_custom_fields") or {}
                for k, v in cf.items():
                    if k in field_keys and k not in last_values and v not in (None, ""):
                        last_values[k] = v
                        last_values_meta[k] = {
                            "case_id": p.get("id"),
                            "case_reference": p.get("reference"),
                            "captured_at": (
                                p.get("work_report_custom_fields_updated_at")
                                or p.get("closed_at")
                                or p.get("updated_at")
                            ),
                        }
                if len(last_values) >= len(field_keys):
                    break
    return {
        "fields": rows,
        "values": case.get("work_report_custom_fields") or {},
        "last_values": last_values,
        "last_values_meta": last_values_meta,
        "context": {
            "asset_id": asset_id,
            "equipment_type": equipment_type,
            "manufacturer": manufacturer,
            "model": model,
        },
    }


@router.post("/work-report-fields")
async def create_work_report_field(
    payload: WorkReportFieldIn,
    user=Depends(get_current_user),
):
    _validate_payload(payload)
    of = _of(user)
    total = await db.svc_work_report_field_defs.count_documents({**of, "archived": {"$ne": True}})
    if total >= MAX_FIELDS_PER_ORG:
        raise HTTPException(400, f"Field limit reached ({MAX_FIELDS_PER_ORG})")
    key = _slug(payload.name)
    # Disambiguate the key within the same scope.
    base_key = key
    suffix = 1
    while await db.svc_work_report_field_defs.find_one(
        {**of, "key": key,
         "scope_kind": payload.scope_kind,
         "scope_value": (payload.scope_value or None),
         "archived": {"$ne": True}},
        {"_id": 1},
    ):
        suffix += 1
        key = f"{base_key}_{suffix}"
    doc = {
        "id": str(uuid.uuid4()),
        **of,
        "name": payload.name.strip(),
        "key": key,
        "field_type": payload.field_type,
        "scope_kind": payload.scope_kind,
        "scope_value": (payload.scope_value or None) if payload.scope_kind != "global" else None,
        # Iter 220du — persisted job-type filter (empty = all).
        "job_types": [jt for jt in (payload.job_types or []) if jt in JOB_TYPES],
        "options": [o.strip() for o in (payload.options or []) if o and o.strip()],
        "required": bool(payload.required),
        "help_text": (payload.help_text or "").strip() or None,
        "archived": False,
        "position": total,
        "created_at": _now(),
        "created_by_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "updated_at": _now(),
    }
    await db.svc_work_report_field_defs.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/work-report-fields/{field_id}")
async def update_work_report_field(
    field_id: str,
    payload: WorkReportFieldPatch,
    user=Depends(get_current_user),
):
    of = _of(user)
    existing = await db.svc_work_report_field_defs.find_one({"id": field_id, **of})
    if not existing:
        raise HTTPException(404, "Field not found")
    updates: dict = {"updated_at": _now()}
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        updates["name"] = name
    if payload.options is not None:
        if existing.get("field_type") == "dropdown":
            opts = [o.strip() for o in payload.options if (o or "").strip()]
            if len(opts) < 2:
                raise HTTPException(400, "dropdown fields need at least 2 options")
            updates["options"] = opts
        else:
            updates["options"] = [o.strip() for o in payload.options if (o or "").strip()]
    if payload.required is not None:
        updates["required"] = bool(payload.required)
    if payload.help_text is not None:
        updates["help_text"] = payload.help_text.strip() or None
    if payload.archived is not None:
        updates["archived"] = bool(payload.archived)
    if payload.job_types is not None:
        # Iter 220du — allow admins to retarget an existing field.
        updates["job_types"] = [
            jt for jt in payload.job_types if jt in JOB_TYPES
        ]
    await db.svc_work_report_field_defs.update_one({"id": field_id, **of}, {"$set": updates})
    refreshed = await db.svc_work_report_field_defs.find_one({"id": field_id, **of}, {"_id": 0})
    return _strip(refreshed)


@router.delete("/work-report-fields/{field_id}")
async def archive_work_report_field(field_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_work_report_field_defs.update_one(
        {"id": field_id, **of},
        {"$set": {"archived": True, "updated_at": _now()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Field not found")
    return {"ok": True, "id": field_id, "archived": True}


# ─── Iter 220ea·14 · Template endpoints ───────────────────────────


@router.get("/work-report-fields/templates")
async def list_field_templates(_user=Depends(get_current_user)):
    """List the catalogue of suggested-field templates an operator
    can one-tap apply. Read-only; templates ship with the platform
    so every org sees the same set. Returns the template metadata
    plus a count of fields each template seeds."""
    return {
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "summary": t["summary"],
                "scope_kind": t["scope_kind"],
                "scope_value": t["scope_value"],
                "job_types": list(t["job_types"]),
                "field_count": len(t["fields"]),
                "fields": [
                    {
                        "name": f["name"],
                        "field_type": f["field_type"],
                        "required": bool(f.get("required")),
                        "help_text": f.get("help_text"),
                        "options": list(f.get("options") or []),
                    }
                    for f in t["fields"]
                ],
            }
            for t in FIELD_TEMPLATES
        ],
        "count": len(FIELD_TEMPLATES),
    }


class TemplateApplyIn(BaseModel):
    template_id: str = Field(..., min_length=1)
    # Optional overrides. The operator picked a Treadmill template
    # but they call them "Cardio · Belt" in their taxonomy → let
    # them override scope_value at apply time.
    scope_kind: Optional[str] = None
    scope_value: Optional[str] = None
    job_types: Optional[list[str]] = None


@router.post("/work-report-fields/apply-template", status_code=201)
async def apply_field_template(
    payload: TemplateApplyIn,
    user=Depends(get_current_user),
):
    """Seed the operator's field set with one of the platform's
    suggested-field templates. Idempotent: if a non-archived field
    already exists with the same (name, scope_kind, scope_value)
    for the org, it's skipped — we don't create duplicates.
    """
    of = _of(user)
    template = next((t for t in FIELD_TEMPLATES if t["id"] == payload.template_id), None)
    if not template:
        raise HTTPException(404, f"Template '{payload.template_id}' not found")

    scope_kind = (payload.scope_kind or template["scope_kind"]).strip()
    if scope_kind not in SCOPE_KINDS:
        raise HTTPException(400, f"scope_kind must be one of {SCOPE_KINDS}")
    scope_value = (
        (payload.scope_value or template.get("scope_value") or "").strip()
        if scope_kind != "global"
        else None
    )
    job_types = [
        jt for jt in (payload.job_types if payload.job_types is not None else template["job_types"])
        if jt in JOB_TYPES
    ]

    # Respect the per-org field cap.
    total = await db.svc_work_report_field_defs.count_documents(
        {**of, "archived": {"$ne": True}},
    )
    if total + len(template["fields"]) > MAX_FIELDS_PER_ORG:
        raise HTTPException(
            400,
            f"Applying this template would exceed the field cap "
            f"({MAX_FIELDS_PER_ORG}). Archive unused fields first.",
        )

    created: list[dict] = []
    skipped: list[dict] = []
    now = _now()
    for idx, spec in enumerate(template["fields"]):
        # Skip if an identical field already lives at this scope.
        dup = await db.svc_work_report_field_defs.find_one(
            {
                **of,
                "name": spec["name"],
                "scope_kind": scope_kind,
                "scope_value": scope_value,
                "archived": {"$ne": True},
            },
            {"_id": 0, "id": 1},
        )
        if dup:
            skipped.append({"name": spec["name"], "existing_id": dup["id"]})
            continue
        # Generate a unique slug within the scope.
        key = _slug(spec["name"])
        base_key, suffix = key, 1
        while await db.svc_work_report_field_defs.find_one(
            {**of, "key": key, "scope_kind": scope_kind,
             "scope_value": scope_value, "archived": {"$ne": True}},
            {"_id": 1},
        ):
            suffix += 1
            key = f"{base_key}_{suffix}"
        doc = {
            "id": str(uuid.uuid4()),
            **of,
            "name": spec["name"].strip(),
            "key": key,
            "field_type": spec["field_type"],
            "scope_kind": scope_kind,
            "scope_value": scope_value,
            "job_types": job_types,
            "options": list(spec.get("options") or []),
            "required": bool(spec.get("required")),
            "help_text": (spec.get("help_text") or "").strip() or None,
            "archived": False,
            "position": total + idx,
            "created_at": now,
            "created_by_id": user.get("id"),
            "created_by_name": user.get("full_name") or user.get("email") or "",
            "created_via_template": template["id"],
            "updated_at": now,
        }
        await db.svc_work_report_field_defs.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
    return {
        "ok": True,
        "template_id": template["id"],
        "scope_kind": scope_kind,
        "scope_value": scope_value,
        "job_types": job_types,
        "created": created,
        "created_count": len(created),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }



# ─── Iter 220ea·24 · Cross-org field share links ──────────────────
# An operator can bundle some (or all) of their custom fields into a
# share token, hand the link to another org, and that org imports the
# fields into their own library in one tap. Unlike the platform
# `FIELD_TEMPLATES` (editorial, ships with the product), these are
# user-authored bundles. Idempotent import (skip dup by name+scope).
# Stored in ``svc_work_report_field_shares`` with a 30-day expiry.


def _share_spec(r: dict) -> dict:
    """Snapshot the portable spec of a field def for a share bundle."""
    return {
        "name": r.get("name"),
        "field_type": r.get("field_type"),
        "scope_kind": r.get("scope_kind") or "global",
        "scope_value": r.get("scope_value"),
        "job_types": list(r.get("job_types") or []),
        "options": list(r.get("options") or []),
        "required": bool(r.get("required")),
        "help_text": r.get("help_text"),
    }


async def _live_share(token: str) -> dict:
    share = await db.svc_work_report_field_shares.find_one({"token": token}, {"_id": 0})
    if not share:
        raise HTTPException(404, "Share link not found")
    exp = share.get("expires_at") or ""
    if exp and exp < _now():
        raise HTTPException(410, "This share link has expired")
    return share


class FieldShareIn(BaseModel):
    # Empty list = share every non-archived field on the org.
    field_ids: list[str] = Field(default_factory=list)
    label: Optional[str] = None


@router.post("/work-report-fields/share", status_code=201)
async def share_fields(payload: FieldShareIn, user=Depends(get_current_user)):
    """Bundle the org's custom fields into a share token another org
    can import. Snapshots the field specs at share time so later edits
    don't mutate an outstanding link."""
    of = _of(user)
    q: dict = {**of, "archived": {"$ne": True}}
    if payload.field_ids:
        q["id"] = {"$in": payload.field_ids}
    rows = await db.svc_work_report_field_defs.find(q, {"_id": 0}).to_list(MAX_FIELDS_PER_ORG)
    if not rows:
        raise HTTPException(400, "No fields to share")
    snapshot = [_share_spec(r) for r in rows]
    org = await db.organizations.find_one(
        {"id": of["organization_id"]}, {"_id": 0, "name": 1})
    token = secrets.token_urlsafe(9)
    now = datetime.now(timezone.utc)
    label = (payload.label or "").strip()[:80] or f"{len(snapshot)} custom field{'s' if len(snapshot) != 1 else ''}"
    doc = {
        "id": str(uuid.uuid4()),
        "token": token,
        **of,
        "source_org_name": (org or {}).get("name") or "",
        "label": label,
        "fields": snapshot,
        "field_count": len(snapshot),
        "created_by_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }
    await db.svc_work_report_field_shares.insert_one(doc)
    return {
        "ok": True, "token": token, "label": label,
        "field_count": len(snapshot), "expires_at": doc["expires_at"],
    }


@router.get("/work-report-fields/shared/{token}")
async def preview_shared_fields(token: str, user=Depends(get_current_user)):
    """Preview a share bundle before importing it."""
    share = await _live_share(token)
    return {
        "token": token,
        "label": share.get("label"),
        "source_org_name": share.get("source_org_name"),
        "field_count": share.get("field_count"),
        "fields": share.get("fields") or [],
        "expires_at": share.get("expires_at"),
        "is_own_org": share.get("organization_id") == user.get("organization_id"),
    }


@router.post("/work-report-fields/shared/{token}/import", status_code=201)
async def import_shared_fields(token: str, user=Depends(get_current_user)):
    """Import a share bundle into the caller's org. Idempotent: skips any
    field whose (name, scope_kind, scope_value) already exists."""
    of = _of(user)
    share = await _live_share(token)
    specs = share.get("fields") or []
    total = await db.svc_work_report_field_defs.count_documents(
        {**of, "archived": {"$ne": True}})
    if total + len(specs) > MAX_FIELDS_PER_ORG:
        raise HTTPException(
            400,
            f"Importing would exceed the field cap ({MAX_FIELDS_PER_ORG}). "
            f"Archive unused fields first.",
        )
    created: list[dict] = []
    skipped: list[dict] = []
    now = _now()
    for idx, spec in enumerate(specs):
        name = (spec.get("name") or "").strip()
        if not name or spec.get("field_type") not in FIELD_TYPES:
            continue
        scope_kind = spec.get("scope_kind") or "global"
        if scope_kind not in SCOPE_KINDS:
            scope_kind = "global"
        scope_value = (spec.get("scope_value") or None) if scope_kind != "global" else None
        dup = await db.svc_work_report_field_defs.find_one(
            {**of, "name": name, "scope_kind": scope_kind,
             "scope_value": scope_value, "archived": {"$ne": True}},
            {"_id": 0, "id": 1},
        )
        if dup:
            skipped.append({"name": name, "existing_id": dup["id"]})
            continue
        key = _slug(name)
        base_key, suffix = key, 1
        while await db.svc_work_report_field_defs.find_one(
            {**of, "key": key, "scope_kind": scope_kind,
             "scope_value": scope_value, "archived": {"$ne": True}},
            {"_id": 1},
        ):
            suffix += 1
            key = f"{base_key}_{suffix}"
        doc = {
            "id": str(uuid.uuid4()),
            **of,
            "name": name,
            "key": key,
            "field_type": spec.get("field_type"),
            "scope_kind": scope_kind,
            "scope_value": scope_value,
            "job_types": [jt for jt in (spec.get("job_types") or []) if jt in JOB_TYPES],
            "options": list(spec.get("options") or []),
            "required": bool(spec.get("required")),
            "help_text": (spec.get("help_text") or "").strip() or None,
            "archived": False,
            "position": total + idx,
            "created_at": now,
            "created_by_id": user.get("id"),
            "created_by_name": user.get("full_name") or user.get("email") or "",
            "imported_from_share": token,
            "updated_at": now,
        }
        await db.svc_work_report_field_defs.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
    return {
        "ok": True,
        "source_org_name": share.get("source_org_name"),
        "created": created,
        "created_count": len(created),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


@router.get("/work-report-fields/history/{case_id}")
async def field_history_for_case(
    case_id: str,
    limit: int = Query(8, ge=2, le=30),
    user=Depends(get_current_user),
):
    """Iter 220b — per-asset time-series for numeric custom fields.

    Returns the last `limit` readings for each numeric/checkbox field
    applicable to the case's asset, oldest-first, so the engineer can
    spot drift (e.g. Drag Factor 122 → 118 → 114) before it becomes a
    breakdown. Excludes the current case from the series.
    """
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "asset_id": 1, "asset_name": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    asset_id = case.get("asset_id") or ""
    asset_name = (case.get("asset_name") or "").strip()
    if not asset_id and not asset_name:
        return {"series": {}, "count": 0}

    q: dict = {
        **of,
        "id": {"$ne": case_id},
        "work_report_custom_fields": {"$exists": True, "$ne": {}},
        "status": {"$in": ["repaired", "awaiting_sign_off", "closed", "invoiced"]},
    }
    if asset_id:
        q["asset_id"] = asset_id
    else:
        q["asset_name"] = asset_name

    rows = (
        await db.svc_cases.find(
            q,
            {"_id": 0, "id": 1, "reference": 1, "closed_at": 1,
             "updated_at": 1, "work_report_custom_fields": 1,
             "work_report_custom_fields_updated_at": 1},
        )
        .sort([("closed_at", -1), ("updated_at", -1)])
        .limit(limit)
        .to_list(limit)
    )

    series: dict[str, list[dict]] = {}
    for r in rows:
        cf = r.get("work_report_custom_fields") or {}
        when = (
            r.get("work_report_custom_fields_updated_at")
            or r.get("closed_at")
            or r.get("updated_at")
        )
        for k, v in cf.items():
            if v in (None, ""):
                continue
            # Only trend-worthy types: numbers & booleans (rendered as 0/1).
            if isinstance(v, bool):
                num = 1.0 if v else 0.0
            elif isinstance(v, (int, float)):
                num = float(v)
            else:
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    continue
            series.setdefault(k, []).append({
                "value": num,
                "captured_at": when,
                "case_id": r.get("id"),
                "case_reference": r.get("reference"),
            })
    # Sort each series oldest-first for chart rendering.
    for k in series:
        series[k] = list(reversed(series[k]))
    return {"series": series, "count": sum(len(v) for v in series.values())}


# ─────────────────────────────────────────────────────────────────
# Helper used by engineer_complete to validate + persist values.
# ─────────────────────────────────────────────────────────────────


async def validate_and_normalise_custom_field_values(
    organization_id: str,
    case: dict,
    raw_values: dict,
) -> dict:
    """Given the user-submitted `custom_fields` dict, validate every value
    against the applicable field defs and return a sanitised dict suitable
    for persistence on `svc_cases.work_report_custom_fields`.
    """
    if not isinstance(raw_values, dict):
        raise HTTPException(400, "custom_fields must be a dict")
    if not raw_values:
        # Still need to enforce `required` even when caller sent nothing.
        raw_values = {}

    asset_id = case.get("asset_id") or ""
    asset = None
    if asset_id:
        asset = await db.equipment.find_one(
            {"id": asset_id, "organization_id": organization_id},
            {"_id": 0, "equipment_type": 1, "manufacturer": 1, "model": 1},
        )
    equipment_type = (asset or {}).get("equipment_type") or case.get("asset_type") or ""
    manufacturer = (asset or {}).get("manufacturer") or case.get("asset_manufacturer") or ""
    model = (asset or {}).get("model") or case.get("asset_model") or ""

    or_clauses: list[dict] = [{"scope_kind": "global"}]
    if equipment_type:
        or_clauses.append({"scope_kind": "equipment_type", "scope_value": equipment_type})
    if manufacturer:
        or_clauses.append({"scope_kind": "manufacturer", "scope_value": manufacturer})
    if model:
        or_clauses.append({"scope_kind": "model", "scope_value": model})
    if asset_id:
        or_clauses.append({"scope_kind": "asset", "scope_value": asset_id})

    defs = await db.svc_work_report_field_defs.find(
        {"organization_id": organization_id, "archived": {"$ne": True}, "$or": or_clauses},
        {"_id": 0},
    ).to_list(MAX_FIELDS_PER_ORG)

    cleaned: dict = {}
    for d in defs:
        key = d["key"]
        ftype = d["field_type"]
        value = raw_values.get(key)
        if value in (None, "", []):
            if d.get("required"):
                raise HTTPException(400, f"'{d['name']}' is required")
            continue
        if ftype == "text":
            cleaned[key] = str(value)[:2000]
        elif ftype == "number":
            try:
                cleaned[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, f"'{d['name']}' must be a number") from exc
        elif ftype == "checkbox":
            cleaned[key] = bool(value)
        elif ftype == "date":
            cleaned[key] = str(value)[:32]
        elif ftype == "dropdown":
            sv = str(value)
            if sv not in (d.get("options") or []):
                raise HTTPException(400, f"'{d['name']}' must be one of the configured options")
            cleaned[key] = sv
        elif ftype == "file":
            if isinstance(value, dict):
                cleaned[key] = {
                    "storage_path": str(value.get("storage_path") or value.get("url") or "")[:512],
                    "original_filename": str(value.get("original_filename") or "")[:200],
                    "content_type": str(value.get("content_type") or "")[:120],
                }
            else:
                cleaned[key] = {"storage_path": str(value)[:512]}
        else:
            cleaned[key] = str(value)[:500]
    return cleaned


async def ensure_indexes() -> None:
    """Index helper called from server startup."""
    await db.svc_work_report_field_defs.create_index(
        [("organization_id", 1), ("scope_kind", 1), ("scope_value", 1)],
    )
    await db.svc_work_report_field_defs.create_index([("organization_id", 1), ("archived", 1)])
    # Iter 220ea·24 — share-link lookups by token.
    await db.svc_work_report_field_shares.create_index([("token", 1)], unique=True)


__all__ = ["router", "validate_and_normalise_custom_field_values", "ensure_indexes"]
