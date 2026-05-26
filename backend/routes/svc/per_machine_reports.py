"""
GymAxis Service Operations — Per-machine work reports.

Iter 220d — Engineers running PPM / service-visit jobs often touch
many machines on a single site visit. The legacy single-summary model
forces them to re-type the same notes for every Erg they serviced.

This module introduces a row-per-machine sub-collection on the case:

    svc_work_visit_machines

Each row captures: asset link, snapshot name, serviced/cleaned chips,
a free-text notes field, and a per-row `custom_fields` dict (uses the
iter-220 custom fields engine). Engineers add as many rows as they
need, in any order, and a "copy-down" helper lets them tick *Serviced*
on row 1 and propagate it to rows below.

Companion module: `svc_note_presets` — a shared (org-wide) + personal
quick-add chip library, so recurring notes like
"Shock cord worn — recommend replacement" become 1-tap entries after
the first time the engineer types them.

Endpoints (mounted under `/api`):

    GET    /svc/engineer/jobs/{case_id}/machines
    POST   /svc/engineer/jobs/{case_id}/machines
    PATCH  /svc/engineer/jobs/{case_id}/machines/{row_id}
    DELETE /svc/engineer/jobs/{case_id}/machines/{row_id}
    POST   /svc/engineer/jobs/{case_id}/machines/{row_id}/copy-down

    GET    /svc/engineer/note-presets
    POST   /svc/engineer/note-presets
    PATCH  /svc/engineer/note-presets/{id}
    DELETE /svc/engineer/note-presets/{id}
    POST   /svc/engineer/note-presets/{id}/used
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Per-machine work reports (iter 220d)"],
)

MAX_MACHINES_PER_CASE = 80
MAX_PRESETS_PER_ORG = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Machines on a visit
# ─────────────────────────────────────────────────────────────────


class MachineRowIn(BaseModel):
    asset_id: Optional[str] = None
    asset_name: Optional[str] = Field(default=None, max_length=200)
    asset_serial: Optional[str] = Field(default=None, max_length=120)
    asset_type: Optional[str] = Field(default=None, max_length=120)
    serviced: bool = False
    cleaned: bool = False
    notes: Optional[str] = Field(default=None, max_length=4000)
    custom_fields: Optional[dict] = None


class MachineRowPatch(BaseModel):
    asset_id: Optional[str] = None
    asset_name: Optional[str] = Field(default=None, max_length=200)
    asset_serial: Optional[str] = Field(default=None, max_length=120)
    asset_type: Optional[str] = Field(default=None, max_length=120)
    serviced: Optional[bool] = None
    cleaned: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    custom_fields: Optional[dict] = None
    order_index: Optional[int] = None


async def _ensure_case(case_id: str, of: dict) -> dict:
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    return case


async def _snapshot_asset(asset_id: str, of: dict) -> dict:
    """Pull a small projection of the equipment record so the machine
    row has stable name/serial/type even if the asset is renamed later.
    """
    if not asset_id:
        return {}
    asset = await db.equipment.find_one(
        {"id": asset_id, **of},
        {"_id": 0, "name": 1, "serial_number": 1, "equipment_type": 1,
         "manufacturer": 1, "model": 1},
    )
    if not asset:
        return {}
    label = asset.get("name") or asset.get("model") or ""
    if asset.get("manufacturer"):
        label = f"{asset['manufacturer']} {label}".strip()
    return {
        "asset_name": label[:200] or None,
        "asset_serial": (asset.get("serial_number") or "")[:120] or None,
        "asset_type": (asset.get("equipment_type") or "")[:120] or None,
    }


@router.get("/jobs/{case_id}/machines")
async def list_machines(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    await _ensure_case(case_id, of)
    rows = (
        await db.svc_work_visit_machines.find(
            {**of, "case_id": case_id},
            {"_id": 0},
        )
        .sort([("order_index", 1), ("created_at", 1)])
        .to_list(MAX_MACHINES_PER_CASE)
    )
    # Iter 220e — fan in any per-machine photos so the engineer can see
    # what they've already attached without an extra round-trip.
    if rows:
        row_ids = [r["id"] for r in rows]
        photos = await db.svc_engineer_photos.find(
            {**of, "case_id": case_id, "machine_row_id": {"$in": row_ids}},
            {"_id": 0, "id": 1, "machine_row_id": 1, "file_url": 1,
             "mime_type": 1, "kind": 1, "caption": 1, "taken_at": 1},
        ).sort([("taken_at", 1)]).to_list(500)
        bucket: dict[str, list[dict]] = {}
        for p in photos:
            bucket.setdefault(p["machine_row_id"], []).append(p)
        for r in rows:
            r["photos"] = bucket.get(r["id"], [])
    return {"machines": rows, "count": len(rows)}


@router.post("/jobs/{case_id}/machines")
async def create_machine(
    case_id: str,
    payload: MachineRowIn,
    user=Depends(get_current_user),
):
    of = _of(user)
    await _ensure_case(case_id, of)
    existing_count = await db.svc_work_visit_machines.count_documents({**of, "case_id": case_id})
    if existing_count >= MAX_MACHINES_PER_CASE:
        raise HTTPException(400, f"Max {MAX_MACHINES_PER_CASE} machines per visit")
    body = payload.model_dump(exclude_none=True)
    snapshot = await _snapshot_asset(body.get("asset_id") or "", of)
    # Prefer caller-supplied snapshot fields, fall back to the asset.
    for k, v in snapshot.items():
        body.setdefault(k, v)
    doc = {
        "id": str(uuid.uuid4()),
        **of,
        "case_id": case_id,
        "asset_id": body.get("asset_id"),
        "asset_name": body.get("asset_name"),
        "asset_serial": body.get("asset_serial"),
        "asset_type": body.get("asset_type"),
        "serviced": bool(body.get("serviced", False)),
        "cleaned": bool(body.get("cleaned", False)),
        "notes": (body.get("notes") or "").strip() or None,
        "custom_fields": body.get("custom_fields") or {},
        "order_index": existing_count,
        "created_at": _now(),
        "created_by_id": user.get("id"),
        "updated_at": _now(),
    }
    await db.svc_work_visit_machines.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/jobs/{case_id}/machines/{row_id}")
async def update_machine(
    case_id: str,
    row_id: str,
    payload: MachineRowPatch,
    user=Depends(get_current_user),
):
    of = _of(user)
    await _ensure_case(case_id, of)
    existing = await db.svc_work_visit_machines.find_one(
        {**of, "case_id": case_id, "id": row_id}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Machine row not found")
    updates = payload.model_dump(exclude_none=True)
    # If asset_id changed, re-snapshot.
    if updates.get("asset_id") and updates["asset_id"] != existing.get("asset_id"):
        snap = await _snapshot_asset(updates["asset_id"], of)
        for k, v in snap.items():
            updates.setdefault(k, v)
    if "notes" in updates:
        updates["notes"] = (updates["notes"] or "").strip() or None
    updates["updated_at"] = _now()
    await db.svc_work_visit_machines.update_one(
        {**of, "case_id": case_id, "id": row_id},
        {"$set": updates},
    )
    refreshed = await db.svc_work_visit_machines.find_one(
        {**of, "case_id": case_id, "id": row_id}, {"_id": 0},
    )
    return _strip(refreshed)


@router.delete("/jobs/{case_id}/machines/{row_id}")
async def delete_machine(
    case_id: str,
    row_id: str,
    user=Depends(get_current_user),
):
    of = _of(user)
    await _ensure_case(case_id, of)
    res = await db.svc_work_visit_machines.delete_one(
        {**of, "case_id": case_id, "id": row_id},
    )
    if not res.deleted_count:
        raise HTTPException(404, "Machine row not found")
    return {"ok": True, "id": row_id}


class CopyDownBody(BaseModel):
    fields: list[str] = Field(default_factory=list)
    """Which fields to copy down: any of `serviced`, `cleaned`, `notes`,
    `custom_fields`. Empty list = copy all four (handy default)."""


@router.post("/jobs/{case_id}/machines/{row_id}/copy-down")
async def copy_down_machine(
    case_id: str,
    row_id: str,
    body: CopyDownBody,
    user=Depends(get_current_user),
):
    """Apply this row's selected fields to every subsequent row on the
    same case. Saves engineers re-typing identical info on PPM visits
    where 8 BikeErgs all need the same calibration note."""
    of = _of(user)
    await _ensure_case(case_id, of)
    source = await db.svc_work_visit_machines.find_one(
        {**of, "case_id": case_id, "id": row_id}, {"_id": 0},
    )
    if not source:
        raise HTTPException(404, "Machine row not found")
    fields = body.fields or ["serviced", "cleaned", "notes", "custom_fields"]
    valid = {"serviced", "cleaned", "notes", "custom_fields"}
    fields = [f for f in fields if f in valid]
    if not fields:
        raise HTTPException(400, "No valid fields to copy")
    src_order = int(source.get("order_index", 0))
    updates = {k: source.get(k) for k in fields}
    updates["updated_at"] = _now()
    res = await db.svc_work_visit_machines.update_many(
        {
            **of, "case_id": case_id,
            "order_index": {"$gt": src_order},
        },
        {"$set": updates},
    )
    return {"ok": True, "updated": res.modified_count, "fields": fields}


# ─────────────────────────────────────────────────────────────────
# Quick-add note presets (shared + personal, with auto-learn)
# ─────────────────────────────────────────────────────────────────


class NotePresetIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    scope: str = "personal"
    pinned: bool = False


class NotePresetPatch(BaseModel):
    text: Optional[str] = Field(default=None, max_length=600)
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


def _validate_scope(scope: str) -> str:
    s = (scope or "personal").lower()
    if s not in ("shared", "personal"):
        raise HTTPException(400, "scope must be 'shared' or 'personal'")
    return s


@router.get("/note-presets")
async def list_note_presets(user=Depends(get_current_user)):
    of = _of(user)
    q = {
        **of,
        "archived": {"$ne": True},
        "$or": [
            {"scope": "shared"},
            {"scope": "personal", "engineer_id": user.get("id")},
        ],
    }
    rows = (
        await db.svc_note_presets.find(q, {"_id": 0})
        .sort([("pinned", -1), ("use_count", -1), ("updated_at", -1)])
        .to_list(MAX_PRESETS_PER_ORG)
    )
    return {"presets": rows, "count": len(rows)}


@router.post("/note-presets")
async def create_note_preset(payload: NotePresetIn, user=Depends(get_current_user)):
    of = _of(user)
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Text required")
    scope = _validate_scope(payload.scope)
    # Dedupe — if the same text already exists in the same scope, bump
    # the use_count and return it instead of inserting a duplicate.
    dedupe_q: dict = {**of, "scope": scope, "text": text, "archived": {"$ne": True}}
    if scope == "personal":
        dedupe_q["engineer_id"] = user.get("id")
    existing = await db.svc_note_presets.find_one(dedupe_q, {"_id": 0})
    if existing:
        await db.svc_note_presets.update_one(
            {"id": existing["id"]},
            {"$inc": {"use_count": 1}, "$set": {"updated_at": _now()}},
        )
        existing["use_count"] = (existing.get("use_count") or 0) + 1
        return existing
    doc = {
        "id": str(uuid.uuid4()),
        **of,
        "scope": scope,
        "engineer_id": user.get("id") if scope == "personal" else None,
        "text": text,
        "pinned": bool(payload.pinned),
        "archived": False,
        "use_count": 1,
        "created_at": _now(),
        "created_by_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "updated_at": _now(),
    }
    await db.svc_note_presets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/note-presets/{preset_id}")
async def update_note_preset(
    preset_id: str,
    payload: NotePresetPatch,
    user=Depends(get_current_user),
):
    of = _of(user)
    existing = await db.svc_note_presets.find_one({"id": preset_id, **of}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Preset not found")
    # Personal presets can only be edited by their owner. Shared presets
    # can be edited by anyone in the org (they're org-wide knowledge).
    if existing.get("scope") == "personal" and existing.get("engineer_id") != user.get("id"):
        raise HTTPException(403, "Cannot edit another engineer's personal preset")
    updates: dict = {}
    if payload.text is not None:
        t = payload.text.strip()
        if not t:
            raise HTTPException(400, "Text cannot be empty")
        updates["text"] = t
    if payload.pinned is not None:
        updates["pinned"] = bool(payload.pinned)
    if payload.archived is not None:
        updates["archived"] = bool(payload.archived)
    if not updates:
        return existing
    updates["updated_at"] = _now()
    await db.svc_note_presets.update_one({"id": preset_id, **of}, {"$set": updates})
    refreshed = await db.svc_note_presets.find_one({"id": preset_id, **of}, {"_id": 0})
    return _strip(refreshed)


@router.delete("/note-presets/{preset_id}")
async def archive_note_preset(preset_id: str, user=Depends(get_current_user)):
    of = _of(user)
    existing = await db.svc_note_presets.find_one({"id": preset_id, **of}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Preset not found")
    if existing.get("scope") == "personal" and existing.get("engineer_id") != user.get("id"):
        raise HTTPException(403, "Cannot archive another engineer's personal preset")
    await db.svc_note_presets.update_one(
        {"id": preset_id, **of},
        {"$set": {"archived": True, "updated_at": _now()}},
    )
    return {"ok": True, "id": preset_id, "archived": True}


@router.post("/note-presets/{preset_id}/used")
async def increment_preset_usage(preset_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_note_presets.update_one(
        {"id": preset_id, **of},
        {"$inc": {"use_count": 1}, "$set": {"updated_at": _now()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Preset not found")
    return {"ok": True, "id": preset_id}


async def ensure_indexes() -> None:
    await db.svc_work_visit_machines.create_index(
        [("organization_id", 1), ("case_id", 1), ("order_index", 1)],
    )
    await db.svc_note_presets.create_index(
        [("organization_id", 1), ("scope", 1), ("engineer_id", 1), ("archived", 1)],
    )
    await db.svc_note_presets.create_index(
        [("organization_id", 1), ("scope", 1), ("text", 1)],
    )


__all__ = ["router", "ensure_indexes"]
