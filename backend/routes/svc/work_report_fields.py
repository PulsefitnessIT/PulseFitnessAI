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
import uuid
from datetime import datetime, timezone
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
MAX_NAME_LEN = 60
MAX_FIELDS_PER_ORG = 200


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
    options: list[str] = Field(default_factory=list)
    required: bool = False
    help_text: Optional[str] = None


class WorkReportFieldPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=MAX_NAME_LEN)
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    help_text: Optional[str] = None
    archived: Optional[bool] = None


def _validate_payload(p: WorkReportFieldIn) -> None:
    if p.field_type not in FIELD_TYPES:
        raise HTTPException(400, f"field_type must be one of {FIELD_TYPES}")
    if p.scope_kind not in SCOPE_KINDS:
        raise HTTPException(400, f"scope_kind must be one of {SCOPE_KINDS}")
    if p.scope_kind != "global" and not (p.scope_value or "").strip():
        raise HTTPException(400, "scope_value is required when scope_kind is not 'global'")
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


@router.get("/work-report-fields/for-case/{case_id}")
async def fields_for_case(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "asset_id": 1, "asset_name": 1,
         "asset_manufacturer": 1, "asset_model": 1, "asset_type": 1,
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

    rows = await db.svc_work_report_field_defs.find(
        {**of, "archived": {"$ne": True}, "$or": or_clauses},
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


__all__ = ["router", "validate_and_normalise_custom_field_values", "ensure_indexes"]
