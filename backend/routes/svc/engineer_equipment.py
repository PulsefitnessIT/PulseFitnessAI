"""
Iter 220ci — Engineer Equipment Tab.

The engineer in the field needs to create new equipment records the
moment they discover an unlogged machine on site. Until now, the
engineer could only PICK from existing equipment (via the `/equipment`
list inside ``WorkVisitMachinesCard``). When a machine wasn't already
on the operations portal they'd type a free-text name on the report
row, and the asset was never persisted as a first-class record.

This module closes that gap with a strict-validation create flow
designed for one-handed use on a phone:

  * ``GET    /api/svc/engineer/equipment`` — list, scoped to the
    engineer's org with optional ``site_id`` / ``q`` filters.
  * ``POST   /api/svc/engineer/equipment`` — create with **server-side
    enforced** mandatory fields + curated picklists. Accepts an
    optional ``case_id`` query so the new asset is *also* dropped onto
    the current job's per-machine work-report rows in one round-trip.
  * ``GET    /api/svc/engineer/equipment/picklists`` — canonical
    dropdown values (type / location / status / manufacturer) so the
    UI never lets the engineer free-type tags that would dirty the
    operations portal's reports.

The freshly-created row is written to the platform-wide ``equipment``
collection, so the master admin / customer portal sees it
automatically — the engineer is just another producer on the same
table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Equipment (iter 220ci)"],
)


# ─────────────────────────────────────────────────────────────────────
# Picklists — server-authoritative so engineers can't free-type
# ─────────────────────────────────────────────────────────────────────

EQUIPMENT_TYPE_OPTIONS = [
    "Treadmill",
    "Exercise Bike",
    "Spin Bike",
    "Cross Trainer",
    "Rowing Machine",
    "Stair Climber",
    "Strength Machine",
    "Cable Machine",
    "Power Rack",
    "Smith Machine",
    "Weight Bench",
    "Free Weights",
    "Functional Trainer",
    "Plate-Loaded",
    "Stretching Equipment",
    "Other",
]

EQUIPMENT_LOCATION_OPTIONS = [
    "Cardio Zone",
    "Strength Zone",
    "Free Weights",
    "Functional Area",
    "Stretch / Mobility",
    "Studio 1",
    "Studio 2",
    "Group Cycling",
    "HIIT / Bootcamp Zone",
    "Reception",
    "Changing Rooms",
    "Pool Area",
    "Spa / Wellness",
    "Outdoor / Garden",
    "Storage",
    "Maintenance Bay",
]

EQUIPMENT_STATUS_OPTIONS = [
    "in_service",
    "out_of_service",
    "awaiting_parts",
    "decommissioned",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    """Return the ``{organization_id: …}`` filter, 403'ing if missing.
    Mirrors ``per_machine_reports._of`` so tenant scoping is identical
    across engineer endpoints."""
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────


class EngineerEquipmentCreate(BaseModel):
    """Strict create payload. Five fields are **mandatory** so the
    operations portal never receives a half-typed row from the field:

      * ``name``            — short label, e.g. "Treadmill #14".
      * ``equipment_type``  — picklist (see ``EQUIPMENT_TYPE_OPTIONS``).
      * ``manufacturer``    — short freeform (curated dropdown on the UI
        but allow "Other" + freetext fallback to keep edge brands).
      * ``model``           — short freeform (text + autocomplete on UI).
      * ``location``        — picklist (see ``EQUIPMENT_LOCATION_OPTIONS``).

    Serial number is **strongly recommended** but optional — gym staff
    sometimes pull the QR sticker off and the engineer logs the asset
    anyway. ``site_id`` is required when the org has more than one
    active site (validated against the sites collection at create-time).
    """

    name: str = Field(min_length=2, max_length=120)
    equipment_type: str = Field(min_length=2, max_length=80)
    manufacturer: str = Field(min_length=2, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=2, max_length=80)

    # Optional but commonly captured in the field.
    serial_number: Optional[str] = Field(default=None, max_length=80)
    status: Optional[str] = Field(default="in_service", max_length=24)
    site_id: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    purchase_date: Optional[str] = Field(default=None, max_length=32)
    warranty_expiry: Optional[str] = Field(default=None, max_length=32)

    @field_validator("equipment_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = v.strip()
        # Allow the curated list verbatim; reject anything else so the
        # operations-portal reports stay clean.
        if v not in EQUIPMENT_TYPE_OPTIONS:
            raise ValueError(
                f"equipment_type must be one of: {', '.join(EQUIPMENT_TYPE_OPTIONS)}"
            )
        return v

    @field_validator("location")
    @classmethod
    def _validate_location(cls, v: str) -> str:
        v = v.strip()
        if v not in EQUIPMENT_LOCATION_OPTIONS:
            raise ValueError(
                f"location must be one of: {', '.join(EQUIPMENT_LOCATION_OPTIONS)}"
            )
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v not in EQUIPMENT_STATUS_OPTIONS:
            raise ValueError(
                f"status must be one of: {', '.join(EQUIPMENT_STATUS_OPTIONS)}"
            )
        return v

    @field_validator("name", "manufacturer", "model")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return (v or "").strip()


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get("/equipment/picklists")
async def get_picklists(user=Depends(get_current_user)):
    """Return the canonical dropdown values for the field-side form.

    Sites are filtered to the engineer's org and surfaced as
    ``{id, name}`` tuples so the UI can require a site pick when the
    org has multiple active sites.
    """
    of = _of(user)
    sites_cursor = db.sites.find(
        {**of, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1},
    ).sort("name", 1)
    sites = await sites_cursor.to_list(500)
    return {
        "equipment_type_options": EQUIPMENT_TYPE_OPTIONS,
        "location_options": EQUIPMENT_LOCATION_OPTIONS,
        "status_options": EQUIPMENT_STATUS_OPTIONS,
        "sites": sites,
    }


@router.get("/equipment")
async def list_engineer_equipment(
    user=Depends(get_current_user),
    site_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """List the org's equipment with optional site + free-text filters.

    Returns a flat projection (no ``stats`` rollup) so the mobile list
    renders snappily over flaky-3G connections.
    """
    of = _of(user)
    flt: dict = {**of}
    if site_id:
        flt["site_id"] = site_id
    if q:
        # Case-insensitive contains across name / serial / model.
        # We don't bother with a $text index — list is bounded at 200.
        needle = q.strip()
        if needle:
            flt["$or"] = [
                {"name": {"$regex": needle, "$options": "i"}},
                {"serial_number": {"$regex": needle, "$options": "i"}},
                {"model": {"$regex": needle, "$options": "i"}},
                {"manufacturer": {"$regex": needle, "$options": "i"}},
            ]
    rows = (
        await db.equipment.find(
            flt,
            {
                "_id": 0, "id": 1, "name": 1, "equipment_type": 1,
                "manufacturer": 1, "model": 1, "serial_number": 1,
                "location": 1, "status": 1, "site_id": 1,
                "created_at": 1, "created_by_id": 1, "created_via": 1,
            },
        )
        .sort("created_at", -1)
        .to_list(limit)
    )
    return {"equipment": rows, "count": len(rows)}


@router.post("/equipment")
async def create_engineer_equipment(
    payload: EngineerEquipmentCreate,
    user=Depends(get_current_user),
    case_id: Optional[str] = Query(default=None),
):
    """Create an equipment record from the engineer app.

    Side-effects:
      * Persists the row to the platform-wide ``equipment`` collection
        so the operations portal / customer dashboard see it.
      * When ``case_id`` is supplied AND the case belongs to this org,
        also inserts a matching row into
        ``svc_work_visit_machines`` so the new asset auto-appears on
        the current job's report.

    Multi-site safety: when the org has more than one active site, a
    ``site_id`` is required (the request 422's at the validator, then
    400's here if the supplied id doesn't belong to the org).
    """
    of = _of(user)
    body = payload.model_dump(exclude_none=True)

    # ── site_id resolution / validation ──
    site_id = body.get("site_id")
    org_sites = await db.sites.find(
        {**of, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(50)
    site_lookup = {s["id"]: s for s in org_sites}
    if site_id:
        if site_id not in site_lookup:
            raise HTTPException(400, "site_id is not a valid site for this org")
    elif len(org_sites) == 1:
        # Single-site orgs — auto-inherit so the engineer doesn't have
        # to pick the only option.
        site_id = org_sites[0]["id"]
        body["site_id"] = site_id
    elif len(org_sites) > 1:
        raise HTTPException(
            400,
            "site_id is required: this org has multiple sites",
        )
    # If org has zero sites we leave site_id null — the operations
    # portal's lazy backfill will heal it once the first site is added.

    now = _now()
    equipment_doc = {
        "id": str(uuid.uuid4()),
        **of,
        "user_id": user.get("id"),
        "created_by_id": user.get("id"),
        "created_via": "engineer_app",
        "manuals": [],
        "stats": {},
        "created_at": now,
        "updated_at": now,
        **body,
    }
    await db.equipment.insert_one(equipment_doc)
    equipment_doc.pop("_id", None)

    # ── Optional: attach to the current job's machines tab ──
    attached_to_case = False
    if case_id:
        case = await db.svc_cases.find_one(
            {"id": case_id, **of}, {"_id": 0, "id": 1},
        )
        if not case:
            # We've already persisted the equipment — don't blow up the
            # whole request; just signal that the side-effect was
            # skipped so the UI can prompt the engineer.
            return {
                **equipment_doc,
                "attached_to_case": False,
                "case_skip_reason": "case_not_found",
            }
        order_index = await db.svc_work_visit_machines.count_documents(
            {**of, "case_id": case_id},
        )
        label = (
            f"{equipment_doc['manufacturer']} {equipment_doc['model']}"
            .strip()
        ) or equipment_doc["name"]
        machine_row = {
            "id": str(uuid.uuid4()),
            **of,
            "case_id": case_id,
            "asset_id": equipment_doc["id"],
            "asset_name": label[:200],
            "asset_serial": (equipment_doc.get("serial_number") or "")[:120] or None,
            "asset_type": (equipment_doc.get("equipment_type") or "")[:120] or None,
            "serviced": False,
            "cleaned": False,
            "notes": None,
            "custom_fields": {},
            "order_index": order_index,
            "created_at": now,
            "created_by_id": user.get("id"),
            "updated_at": now,
        }
        await db.svc_work_visit_machines.insert_one(machine_row)
        attached_to_case = True

    return {**equipment_doc, "attached_to_case": attached_to_case}


async def ensure_indexes() -> None:
    """Lightweight indexes for the engineer-equipment list filters.

    ``equipment`` is shared with the operations portal so we don't
    re-create the indexes that ``routes/equipment.py`` already manages.
    Defensive ``try/except`` mirrors the rest of the engineer-side
    modules — never break cold-start on an index error.
    """
    try:
        await db.equipment.create_index([("organization_id", 1), ("site_id", 1)])
        await db.equipment.create_index([("organization_id", 1), ("created_at", -1)])
    except Exception:  # noqa: BLE001
        pass
