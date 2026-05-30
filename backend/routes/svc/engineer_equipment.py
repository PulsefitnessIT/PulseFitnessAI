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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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
    customer_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=1000),
    include_unassigned: bool = Query(default=False),
):
    """List the org's equipment scoped to **customer-owned records**.

    Iter 220cl — User feedback: "the engineer should only be able to
    see equipment that has been imported into the customer's account
    via the onboarding process". So by default we now require a
    ``customer_id`` column on the row (set by the customer-scoped CSV
    import or the customer-detail "Add equipment" flow). To preserve
    the original behaviour for any code-path that still needs the
    full org catalogue, ``include_unassigned=true`` opts back in.
    """
    of = _of(user)
    flt: dict = {**of}
    if not include_unassigned:
        flt["customer_id"] = {"$exists": True, "$ne": None}
    if customer_id:
        flt["customer_id"] = customer_id
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
                "customer_id": 1, "customer_name": 1,
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


# ─────────────────────────────────────────────────────────────────────
# Iter 220cl — Engineer-scoped CSV template + import bound to a
# customer record. The "Orbit 4 Asset ID" and "Sicon Equipment ID"
# columns from the operations-portal template are intentionally
# omitted here — those are Pulse Fitness-only fields (their stock
# system uses them for ERP round-tripping) and don't belong on a
# generic engineer's import.
# ─────────────────────────────────────────────────────────────────────


_ENGINEER_CSV_HEADERS = [
    "Name", "Type", "Manufacturer", "Model", "Serial Number",
    "Purchase Date (YYYY-MM-DD)", "Warranty Expiry (YYYY-MM-DD)",
    "Length (m)", "Width (m)", "Height (m)", "Location", "Notes",
]

_ENGINEER_CSV_FIELD_MAP = {
    "name": "Name",
    "type": "Type",
    "manufacturer": "Manufacturer",
    "model": "Model",
    "serial": "Serial Number",
    "purchase_date": "Purchase Date (YYYY-MM-DD)",
    "warranty": "Warranty Expiry (YYYY-MM-DD)",
    "length": "Length (m)",
    "width": "Width (m)",
    "height": "Height (m)",
    "location": "Location",
    "notes": "Notes",
}


@router.get("/equipment/template-csv")
async def get_engineer_csv_template(user=Depends(get_current_user)):
    """Slim CSV template — no Pulse-specific integration columns.

    Engineers download this from the customer-onboarding flow,
    populate it offline at the gym, and re-upload via
    ``POST /svc/engineer/customers/{customer_id}/equipment/import-csv``
    so every row is auto-tagged with the right customer.
    """
    _of(user)  # 403 if no org context.
    import csv as _csv
    import io as _io
    from fastapi.responses import Response  # local import to avoid cycle

    out = _io.StringIO()
    writer = _csv.writer(out)
    writer.writerow(_ENGINEER_CSV_HEADERS)
    writer.writerow([
        "Treadmill #1", "Treadmill", "Life Fitness", "Integrity DX",
        "LF-12345", "2024-01-15", "2027-01-15", "2.1", "0.9", "1.6",
        "Cardio Zone", "Captured during PM visit",
    ])
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=equipment-import-engineer.csv",
        },
    )


def _parse_engineer_csv_row(row: dict, user: dict, *, customer: dict,
                            now: str) -> Optional[dict]:
    """Build an equipment doc from a single engineer-template CSV row.
    Returns None for rows missing the mandatory ``Name`` cell so we
    skip blank trailing lines silently."""
    fm = _ENGINEER_CSV_FIELD_MAP
    name = (row.get(fm["name"]) or "").strip()
    if not name:
        return None
    of = _of(user)

    def _opt(field: str) -> Optional[str]:
        v = (row.get(fm[field]) or "").strip()
        return v or None

    def _float(field: str) -> Optional[float]:
        v = (row.get(fm[field]) or "").strip()
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    return {
        "id": str(uuid.uuid4()),
        **of,
        "user_id": user.get("id"),
        "created_by_id": user.get("id"),
        "created_via": "engineer_customer_csv",
        "customer_id": customer.get("id"),
        "customer_name": customer.get("name"),
        "site_id": customer.get("site_id"),
        "name": name[:120],
        "equipment_type": (_opt("type") or "Other")[:80],
        "manufacturer": _opt("manufacturer"),
        "model": _opt("model"),
        "serial_number": _opt("serial"),
        "location": _opt("location"),
        "status": "in_service",
        "purchase_date": _opt("purchase_date"),
        "warranty_expiry": _opt("warranty"),
        "length": _float("length"),
        "width": _float("width"),
        "height": _float("height"),
        "notes": _opt("notes"),
        "manuals": [],
        "stats": {},
        "created_at": now,
        "updated_at": now,
    }


@router.post("/customers/{customer_id}/equipment/import-csv")
async def import_customer_equipment_csv(
    customer_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Bulk-create equipment rows from a slim-template CSV, all tagged
    with the supplied ``customer_id``. The customer must belong to the
    engineer's org. Returns ``{inserted, skipped, rows}`` so the UI
    can show a quick result toast.
    """
    of = _of(user)
    customer = await db.svc_engineer_customers.find_one(
        {"id": customer_id, **of},
        {"_id": 0, "id": 1, "name": 1, "site_id": 1, "site_name": 1},
    )
    if not customer:
        raise HTTPException(404, "Customer not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Uploaded CSV is empty")
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(400, "CSV too large (max 2 MB)")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "Couldn't decode CSV") from exc

    import csv as _csv
    import io as _io
    reader = _csv.DictReader(_io.StringIO(text))
    now = _now()
    rows: list[dict] = []
    skipped = 0
    for raw_row in reader:
        doc = _parse_engineer_csv_row(raw_row, user, customer=customer, now=now)
        if doc is None:
            skipped += 1
            continue
        rows.append(doc)

    if rows:
        await db.equipment.insert_many(rows)

    return {
        "inserted": len(rows),
        "skipped": skipped,
        "customer_id": customer_id,
        "rows": [
            {"id": r["id"], "name": r["name"],
             "manufacturer": r.get("manufacturer"), "model": r.get("model")}
            for r in rows[:100]
        ],
    }


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


# ─────────────────────────────────────────────────────────────────────
# Iter 220cj — Site-equipment picker for the job's Machines tab
# ─────────────────────────────────────────────────────────────────────


class _BulkFromSiteBody(BaseModel):
    """Engineer picks specific equipment IDs (or ``select_all=True``)
    from a site's catalogue to fan out as machine rows on a job.
    Idempotent — equipment already on the case as a machine row is
    skipped so re-opening the picker doesn't create duplicates."""

    equipment_ids: list[str] = Field(default_factory=list, max_length=200)
    select_all: bool = False


@router.get("/jobs/{case_id}/site-equipment", tags=[
    "Service Ops · Engineer Equipment (iter 220cj)",
])
async def list_site_equipment_for_case(
    case_id: str,
    user=Depends(get_current_user),
):
    """Return the equipment catalogue for the job's site, annotated
    with ``already_on_job`` so the mobile picker can ghost rows the
    engineer has already added."""
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of}, {"_id": 0, "id": 1, "site_id": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    site_id = case.get("site_id")
    if not site_id:
        # No site → nothing to pre-load; the engineer can still add ad-hoc.
        return {"site_equipment": [], "already_on_job": [], "site_id": None}

    rows = (
        await db.equipment.find(
            {**of, "site_id": site_id},
            {
                "_id": 0, "id": 1, "name": 1, "equipment_type": 1,
                "manufacturer": 1, "model": 1, "serial_number": 1,
                "location": 1, "status": 1,
            },
        )
        .sort([("equipment_type", 1), ("name", 1)])
        .limit(500)
        .to_list(500)
    )
    existing = await db.svc_work_visit_machines.find(
        {**of, "case_id": case_id},
        {"_id": 0, "asset_id": 1},
    ).to_list(500)
    existing_ids = {r.get("asset_id") for r in existing if r.get("asset_id")}
    for r in rows:
        r["already_on_job"] = r["id"] in existing_ids
    return {
        "site_equipment": rows,
        "already_on_job": sorted(existing_ids),
        "site_id": site_id,
    }


@router.post("/jobs/{case_id}/machines/bulk-from-site", tags=[
    "Service Ops · Engineer Equipment (iter 220cj)",
])
async def bulk_attach_site_equipment(
    case_id: str,
    payload: _BulkFromSiteBody,
    user=Depends(get_current_user),
):
    """Fan out one machine row on the case for each requested
    equipment id. Idempotent against ``svc_work_visit_machines`` —
    equipment already attached is skipped. Returns the count actually
    inserted so the UI can show "Added 8 machines"."""
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of}, {"_id": 0, "id": 1, "site_id": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    site_id = case.get("site_id")

    # Resolve the equipment set.
    eq_filter: dict = {**of}
    if payload.select_all:
        if not site_id:
            raise HTTPException(400, "Case has no site_id; can't select-all")
        eq_filter["site_id"] = site_id
    else:
        ids = [e for e in (payload.equipment_ids or []) if e]
        if not ids:
            raise HTTPException(400, "Provide equipment_ids or select_all=true")
        eq_filter["id"] = {"$in": ids}

    candidates = await db.equipment.find(
        eq_filter,
        {
            "_id": 0, "id": 1, "name": 1, "equipment_type": 1,
            "manufacturer": 1, "model": 1, "serial_number": 1,
        },
    ).to_list(500)
    if not candidates:
        return {"inserted": 0, "skipped": 0, "machine_ids": []}

    # Skip equipment already on the case.
    existing = await db.svc_work_visit_machines.find(
        {**of, "case_id": case_id, "asset_id": {"$in": [c["id"] for c in candidates]}},
        {"_id": 0, "asset_id": 1},
    ).to_list(500)
    existing_ids = {r.get("asset_id") for r in existing if r.get("asset_id")}

    order_index = await db.svc_work_visit_machines.count_documents(
        {**of, "case_id": case_id},
    )

    now = _now()
    inserted_rows: list[dict] = []
    for eq in candidates:
        if eq["id"] in existing_ids:
            continue
        label = (
            f"{eq.get('manufacturer') or ''} {eq.get('model') or eq.get('name') or ''}"
            .strip()
            or eq.get("name") or "Equipment"
        )
        row = {
            "id": str(uuid.uuid4()),
            **of,
            "case_id": case_id,
            "asset_id": eq["id"],
            "asset_name": label[:200],
            "asset_serial": (eq.get("serial_number") or "")[:120] or None,
            "asset_type": (eq.get("equipment_type") or "")[:120] or None,
            "serviced": False,
            "cleaned": False,
            "notes": None,
            "custom_fields": {},
            "order_index": order_index,
            "created_at": now,
            "created_by_id": user.get("id"),
            "updated_at": now,
            "source": "site_equipment_bulk",
        }
        order_index += 1
        inserted_rows.append(row)

    if inserted_rows:
        await db.svc_work_visit_machines.insert_many(inserted_rows)

    return {
        "inserted": len(inserted_rows),
        "skipped": len(candidates) - len(inserted_rows),
        "machine_ids": [r["id"] for r in inserted_rows],
    }
