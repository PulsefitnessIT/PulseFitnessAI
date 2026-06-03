"""
GymAxis Service Operations — Configurable Case Types.

Iter 220ec (Phase 2) — Lets each organisation manage its own case-type
taxonomy (Repair / PPM / Installation / …) instead of a hard-coded enum.

Why this matters
----------------
``case_type`` drives:
  • the friendly "Job type" row on the customer Service Report,
  • which custom report questions an engineer is asked (the existing
    ``work_report_fields`` engine filters by ``job_types`` — those slugs
    are exactly the case-type slugs managed here), and
  • service-desk / reporting taxonomy.

Six built-in types ship with every org (lazily seeded on first read).
Orgs can add their own, rename/recolour any type, deactivate the ones
they don't use, and reorder them. Built-in types can be deactivated
(soft) but not deleted; custom types can be deleted outright.

Permission model mirrors ``work_report_fields``: any authenticated user
with an organisation context (owners + engineers) may manage types.

Endpoints (mounted under ``/api``):
    GET    /svc/case-types?include_inactive=bool   list (lazy-seeds builtins)
    POST   /svc/case-types                         create custom type
    PATCH  /svc/case-types/{id}                     update label/colour/active/order
    DELETE /svc/case-types/{id}                     delete (custom only)
    POST   /svc/case-types/reorder                  set explicit order
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
router = APIRouter(prefix="/svc", tags=["Service Ops · Case Types"])

MAX_LABEL_LEN = 50
MAX_TYPES_PER_ORG = 60

# The six types that ship with the platform. Lazily seeded per-org the
# first time the list endpoint is called. ``order_index`` mirrors list
# order; ``slug`` is the stable key used by case_type / job_types.
BUILTIN_CASE_TYPES = [
    {"slug": "repair", "label": "Repair", "color": "#dc2626",
     "description": "Reactive fix for a reported fault."},
    {"slug": "ppm", "label": "PPM Service", "color": "#0891b2",
     "description": "Planned preventative maintenance visit."},
    {"slug": "install", "label": "Installation", "color": "#7c3aed",
     "description": "New equipment install / commissioning."},
    {"slug": "inspection", "label": "Inspection", "color": "#2563eb",
     "description": "Safety / condition inspection."},
    {"slug": "callout", "label": "Emergency callout", "color": "#ea580c",
     "description": "Urgent unscheduled attendance."},
    {"slug": "audit", "label": "Asset audit", "color": "#16a34a",
     "description": "Asset register / condition audit."},
]
BUILTIN_SLUGS = {t["slug"] for t in BUILTIN_CASE_TYPES}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _slug(label: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", (label or "").strip()).strip("_").lower()
    return base[:40] or "type"


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if doc:
        doc.pop("_id", None)
    return doc


async def _seed_builtins(org_id: str) -> None:
    """Insert any missing built-in types for the org (idempotent)."""
    existing = await db.svc_case_types.find(
        {"organization_id": org_id, "is_builtin": True},
        {"_id": 0, "slug": 1},
    ).to_list(100)
    have = {r["slug"] for r in existing}
    now = _now()
    to_insert = []
    for idx, t in enumerate(BUILTIN_CASE_TYPES):
        if t["slug"] in have:
            continue
        to_insert.append({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "slug": t["slug"],
            "label": t["label"],
            "description": t["description"],
            "color": t["color"],
            "is_builtin": True,
            "active": True,
            "order_index": idx,
            "created_at": now,
            "updated_at": now,
        })
    if to_insert:
        await db.svc_case_types.insert_many(to_insert)


async def list_case_types(org_id: str, include_inactive: bool = True) -> list[dict]:
    await _seed_builtins(org_id)
    q: dict = {"organization_id": org_id}
    if not include_inactive:
        q["active"] = {"$ne": False}
    rows = (
        await db.svc_case_types.find(q, {"_id": 0})
        .sort([("order_index", 1), ("created_at", 1)])
        .to_list(MAX_TYPES_PER_ORG)
    )
    return rows


async def resolve_case_type_label(org_id: str, slug: str) -> str:
    """Friendly label for a case_type slug (used by the report)."""
    if not slug:
        return ""
    row = await db.svc_case_types.find_one(
        {"organization_id": org_id, "slug": str(slug).lower()},
        {"_id": 0, "label": 1},
    )
    if row and row.get("label"):
        return row["label"]
    builtin = next((t for t in BUILTIN_CASE_TYPES if t["slug"] == str(slug).lower()), None)
    if builtin:
        return builtin["label"]
    return str(slug).replace("_", " ").title()


async def active_slugs(org_id: str) -> set[str]:
    """Set of case-type slugs accepted on intake (active types + builtins)."""
    await _seed_builtins(org_id)
    rows = await db.svc_case_types.find(
        {"organization_id": org_id, "active": {"$ne": False}},
        {"_id": 0, "slug": 1},
    ).to_list(MAX_TYPES_PER_ORG)
    return {r["slug"] for r in rows} | BUILTIN_SLUGS


# ─────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────


class CaseTypeIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=MAX_LABEL_LEN)
    description: Optional[str] = Field(default=None, max_length=200)
    color: Optional[str] = Field(default="#475569", max_length=20)


class CaseTypePatch(BaseModel):
    label: Optional[str] = Field(default=None, max_length=MAX_LABEL_LEN)
    description: Optional[str] = Field(default=None, max_length=200)
    color: Optional[str] = Field(default=None, max_length=20)
    active: Optional[bool] = None
    order_index: Optional[int] = None


class ReorderIn(BaseModel):
    ordered_ids: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────


@router.get("/case-types")
async def get_case_types(
    include_inactive: bool = Query(True),
    user=Depends(get_current_user),
):
    of = _of(user)
    rows = await list_case_types(of["organization_id"], include_inactive=include_inactive)
    return {"case_types": rows, "count": len(rows)}


@router.post("/case-types", status_code=201)
async def create_case_type(payload: CaseTypeIn, user=Depends(get_current_user)):
    of = _of(user)
    await _seed_builtins(of["organization_id"])
    label = payload.label.strip()
    if not label:
        raise HTTPException(400, "label is required")
    total = await db.svc_case_types.count_documents(of)
    if total >= MAX_TYPES_PER_ORG:
        raise HTTPException(400, f"Case-type limit reached ({MAX_TYPES_PER_ORG})")
    # Unique slug within the org.
    slug = _slug(label)
    base, suffix = slug, 1
    while await db.svc_case_types.find_one({**of, "slug": slug}, {"_id": 1}):
        suffix += 1
        slug = f"{base}_{suffix}"
    doc = {
        "id": str(uuid.uuid4()),
        **of,
        "slug": slug,
        "label": label,
        "description": (payload.description or "").strip() or None,
        "color": (payload.color or "#475569").strip(),
        "is_builtin": False,
        "active": True,
        "order_index": total,
        "created_at": _now(),
        "created_by_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email") or "",
        "updated_at": _now(),
    }
    await db.svc_case_types.insert_one(doc)
    return _strip(doc)


@router.patch("/case-types/{type_id}")
async def update_case_type(
    type_id: str, payload: CaseTypePatch, user=Depends(get_current_user),
):
    of = _of(user)
    existing = await db.svc_case_types.find_one({"id": type_id, **of})
    if not existing:
        raise HTTPException(404, "Case type not found")
    updates: dict = {"updated_at": _now()}
    if payload.label is not None:
        label = payload.label.strip()
        if not label:
            raise HTTPException(400, "label cannot be empty")
        updates["label"] = label
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.color is not None:
        updates["color"] = payload.color.strip() or "#475569"
    if payload.active is not None:
        updates["active"] = bool(payload.active)
    if payload.order_index is not None:
        updates["order_index"] = int(payload.order_index)
    await db.svc_case_types.update_one({"id": type_id, **of}, {"$set": updates})
    return _strip(await db.svc_case_types.find_one({"id": type_id, **of}, {"_id": 0}))


@router.delete("/case-types/{type_id}")
async def delete_case_type(type_id: str, user=Depends(get_current_user)):
    of = _of(user)
    existing = await db.svc_case_types.find_one({"id": type_id, **of})
    if not existing:
        raise HTTPException(404, "Case type not found")
    if existing.get("is_builtin"):
        raise HTTPException(
            400,
            "Built-in types can't be deleted — deactivate it instead so it "
            "stops appearing on new jobs.",
        )
    await db.svc_case_types.delete_one({"id": type_id, **of})
    return {"ok": True, "id": type_id, "deleted": True}


@router.post("/case-types/reorder")
async def reorder_case_types(payload: ReorderIn, user=Depends(get_current_user)):
    of = _of(user)
    for idx, tid in enumerate(payload.ordered_ids):
        await db.svc_case_types.update_one(
            {"id": tid, **of}, {"$set": {"order_index": idx, "updated_at": _now()}},
        )
    rows = await list_case_types(of["organization_id"])
    return {"case_types": rows, "count": len(rows)}


async def ensure_indexes() -> None:
    await db.svc_case_types.create_index(
        [("organization_id", 1), ("slug", 1)], unique=True,
    )
    await db.svc_case_types.create_index([("organization_id", 1), ("order_index", 1)])


__all__ = ["router", "resolve_case_type_label", "active_slugs", "list_case_types", "ensure_indexes"]
