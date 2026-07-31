from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid
import csv
import io
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.default_supplier import ensure_default_supplier, can_add_extra_suppliers
from routes.supplier_portal import send_supplier_welcome_email, send_supplier_reassignment_email

logger = logging.getLogger(__name__)
router = APIRouter()

# CSV columns accepted by the equipment import endpoint. Matches the column
# order in the welcome-email CSV so round-trips are easy.
_CSV_COLUMN_ALIASES = {
    "name": "name",
    "equipment type": "equipment_type", "equipment_type": "equipment_type", "type": "equipment_type",
    "manufacturer": "manufacturer", "make": "manufacturer",
    "model": "model",
    "serial number": "serial_number", "serial_number": "serial_number", "serial": "serial_number",
    "location": "location", "site": "location",
    "install date": "install_date", "install_date": "install_date",
    "purchase date": "purchase_date", "purchase_date": "purchase_date",
    "warranty expiry": "warranty_expiry", "warranty_expiry": "warranty_expiry", "warranty": "warranty_expiry",
    "notes": "notes",
}


def _require_owner_or_manager(user: dict) -> None:
    if user.get("role") not in ("owner", "manager", "master_admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owners and managers can manage suppliers",
        )


async def _load_supplier_or_404(supplier_id: str, user: dict) -> dict:
    org_filter = get_organization_filter(user)
    supplier = await db.suppliers.find_one({"id": supplier_id, **org_filter}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.post("/suppliers")
async def add_supplier(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    _require_owner_or_manager(user)
    # Lite orgs keep only the locked Pulse Fitness default supplier; Pro/Full
    # (and Pulse admins) may add unlimited extra suppliers.
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "account_type": 1}) or {}
    if not can_add_extra_suppliers(user, org):
        raise HTTPException(
            status_code=403,
            detail="Adding suppliers is a Pulse Pro feature. Your account uses Pulse Fitness Ltd as its default supplier; upgrade to Pro to add your own.",
        )
    # Iter 216o-7 — accept multi-select supplier_types array. Default to the
    # singular `supplier_type` string for legacy callers.
    supplier_types_raw = data.get('supplier_types') or []
    if isinstance(supplier_types_raw, str):
        supplier_types_raw = [supplier_types_raw]
    supplier_types = [t for t in supplier_types_raw if t]
    if not supplier_types and data.get('supplier_type'):
        supplier_types = [data['supplier_type']]

    supplier_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get('organization_id'),
        "name": data.get('name', ''),
        "email": data.get('email', ''),
        "phone": data.get('phone', ''),
        "contact_person": data.get('contact_person', ''),
        "address": data.get('address', ''),
        "notes": data.get('notes', ''),
        "supplier_types": supplier_types,
        # Keep singular field populated for any legacy reads (e.g. UI filters).
        "supplier_type": supplier_types[0] if supplier_types else '',
        "callout_fee": float(data.get('callout_fee', 0)) if data.get('callout_fee') else 0,
        "labour_rate_per_hour": float(data.get('labour_rate_per_hour', 0)) if data.get('labour_rate_per_hour') else 0,
        "mileage_rate": float(data.get('mileage_rate', 0)) if data.get('mileage_rate') else 0,
        "parts_markup_pct": float(data.get('parts_markup_pct', 0)) if data.get('parts_markup_pct') else 0,
        "custom_items": data.get('custom_items', []),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.suppliers.insert_one(supplier_doc)
    supplier_doc.pop('_id', None)

    # The caller (e.g. the equipment wizard) can set `send_welcome=False` to
    # defer the onboarding email until they've assigned machines — the wizard
    # then triggers POST /suppliers/{id}/send-welcome at the end and the CSV
    # of machines is auto-attached to the email.
    send_welcome_now = data.get('send_welcome', True)
    if send_welcome_now:
        sent = await send_supplier_welcome_email(supplier_doc, user.get('organization_id'))
        if sent:
            now = datetime.now(timezone.utc).isoformat()
            await db.suppliers.update_one(
                {"id": supplier_doc["id"]},
                {"$set": {"welcome_email_sent_at": now}},
            )
            supplier_doc["welcome_email_sent_at"] = now
    return supplier_doc


@router.post("/suppliers/{supplier_id}/send-welcome")
async def send_welcome_email(supplier_id: str, user: dict = Depends(get_current_user)):
    """Manually (re)send the onboarding email to an existing supplier.

    Useful when a supplier was added before welcome emails were enabled, when
    the email address was corrected, or when an admin wants to re-brief them.
    """
    _require_owner_or_manager(user)
    org_filter = get_organization_filter(user)
    supplier = await db.suppliers.find_one({"id": supplier_id, **org_filter}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not (supplier.get("email") or "").strip():
        raise HTTPException(status_code=400, detail="Supplier has no email address on file")

    sent = await send_supplier_welcome_email(supplier, user.get('organization_id'))
    if not sent:
        raise HTTPException(
            status_code=503,
            detail="Could not send welcome email (check Resend config and org tier — Pulse Lite is not eligible)",
        )
    now = datetime.now(timezone.utc).isoformat()
    await db.suppliers.update_one(
        {"id": supplier_id, **org_filter},
        {"$set": {"welcome_email_sent_at": now}},
    )
    return {"success": True, "welcome_email_sent_at": now}


@router.get("/suppliers")
async def get_suppliers(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Iter 216h62 — `site_id` query param filters the list down to
    suppliers that actually service equipment at that site. Omitted =
    all suppliers in the org (used when SiteSwitcher is on "All
    Operations Sites"). Matches by supplier_id first, then falls back
    to supplier_name for legacy equipment rows that pre-date the
    supplier-directory pivot."""
    org_filter = get_organization_filter(user)
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "account_type": 1, "is_mod": 1}) or {}
    # Guarantee every org has the locked Pulse Fitness Ltd default supplier.
    await ensure_default_supplier(user.get("organization_id"), org)
    can_add = can_add_extra_suppliers(user, org)
    if site_id:
        # Pull the set of supplier ids + names attached to equipment at
        # the requested site, then return only the supplier directory
        # entries that intersect.
        eq_rows = await db.equipment.find(
            {**org_filter, "site_id": site_id},
            {"_id": 0, "supplier": 1, "supplier_id": 1},
        ).to_list(2000)
        ids = {r["supplier_id"] for r in eq_rows if r.get("supplier_id")}
        names = {(r.get("supplier") or "").strip() for r in eq_rows if (r.get("supplier") or "").strip()}
        # Always include the locked Pulse default (it's the fallback for any
        # machine at the site with no specific supplier).
        supplier_filter = {"$or": [{"is_default_pulse": True}]}
        if ids:
            supplier_filter["$or"].append({"id": {"$in": list(ids)}})
        if names:
            supplier_filter["$or"].append({"name": {"$in": list(names)}})
        suppliers = await db.suppliers.find(
            {**org_filter, **supplier_filter}, {"_id": 0},
        ).to_list(200)
        suppliers.sort(key=lambda s: (not s.get("is_default_pulse"), (s.get("name") or "").lower()))
        return {"suppliers": suppliers, "can_add_suppliers": can_add}
    suppliers = await db.suppliers.find(org_filter, {"_id": 0}).to_list(100)
    # Pin the Pulse Fitness default to the top, then alphabetical.
    suppliers.sort(key=lambda s: (not s.get("is_default_pulse"), (s.get("name") or "").lower()))
    return {"suppliers": suppliers, "can_add_suppliers": can_add}


@router.get("/suppliers/dispatch-readiness")
async def supplier_dispatch_readiness(user: dict = Depends(get_current_user)):
    """Iter 220ea·40 — which machines would *silently* fail to auto-dispatch
    a fault because their linked supplier has no email on file (or isn't in
    the supplier directory). Lets operators spot the gaps so every logged
    fault actually reaches a supplier.
    """
    org_filter = get_organization_filter(user)
    suppliers = await db.suppliers.find(
        org_filter, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    by_id = {s["id"]: s for s in suppliers if s.get("id")}
    by_name = {(s.get("name") or "").strip().lower(): s for s in suppliers if (s.get("name") or "").strip()}

    equipment = await db.equipment.find(
        org_filter,
        {"_id": 0, "supplier": 1, "supplier_id": 1},
    ).to_list(5000)

    def _resolve(eq: dict) -> Optional[dict]:
        sid = (eq.get("supplier_id") or "").strip()
        if sid and sid in by_id:
            return by_id[sid]
        nm = (eq.get("supplier") or "").strip().lower()
        return by_name.get(nm)

    machines_ready = machines_blocked = machines_no_supplier = 0
    blocked: Dict[str, dict] = {}
    for eq in equipment:
        has_link = bool((eq.get("supplier_id") or "").strip() or (eq.get("supplier") or "").strip())
        if not has_link:
            # No specific supplier → routes to the locked Pulse Fitness default,
            # which always has an email, so the fault WILL auto-dispatch.
            machines_no_supplier += 1
            machines_ready += 1
            continue
        sup = _resolve(eq)
        if sup and (sup.get("email") or "").strip():
            machines_ready += 1
            continue
        machines_blocked += 1
        if sup:
            key = sup.get("id") or f"name:{(sup.get('name') or '').lower()}"
            entry = blocked.setdefault(key, {
                "supplier_id": sup.get("id"), "name": sup.get("name"),
                "reason": "no_email", "machine_count": 0})
        else:
            raw = (eq.get("supplier") or "Unknown supplier").strip()
            entry = blocked.setdefault(f"name:{raw.lower()}", {
                "supplier_id": None, "name": raw,
                "reason": "not_in_directory", "machine_count": 0})
        entry["machine_count"] += 1

    missing_email = [
        {"id": s.get("id"), "name": s.get("name")}
        for s in suppliers if not (s.get("email") or "").strip()
    ]
    return {
        "total_machines": len(equipment),
        "machines_ready": machines_ready,
        "machines_blocked": machines_blocked,
        "machines_no_supplier": machines_no_supplier,
        "blocked_suppliers": sorted(blocked.values(), key=lambda x: -x["machine_count"]),
        "suppliers_missing_email": missing_email,
        "suppliers_missing_email_count": len(missing_email),
        "total_suppliers": len(suppliers),
    }


@router.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)):
    _require_owner_or_manager(user)
    org_filter = get_organization_filter(user)
    locked = await db.suppliers.find_one(
        {"id": supplier_id, **org_filter}, {"_id": 0, "is_default_pulse": 1})
    if locked and locked.get("is_default_pulse"):
        raise HTTPException(
            status_code=403,
            detail="The Pulse Fitness Ltd default supplier is locked and can't be edited.",
        )
    update_fields = {}
    for field in ['name', 'email', 'phone', 'contact_person', 'address', 'notes', 'custom_items']:
        if field in data:
            update_fields[field] = data[field]
    for field in ['callout_fee', 'labour_rate_per_hour', 'mileage_rate', 'parts_markup_pct']:
        if field in data:
            update_fields[field] = float(data[field]) if data[field] else 0
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.suppliers.update_one(
        {"id": supplier_id, **org_filter},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    updated = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    return updated


@router.get("/suppliers/{supplier_id}/pricing")
async def get_supplier_pricing(supplier_id: str, user: dict = Depends(get_current_user)):
    """Get pricing for a specific supplier - used by PO auto-populate"""
    org_filter = get_organization_filter(user)
    supplier = await db.suppliers.find_one({"id": supplier_id, **org_filter}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {
        "callout_fee": supplier.get("callout_fee", 0),
        "labour_rate_per_hour": supplier.get("labour_rate_per_hour", 0),
        "mileage_rate": supplier.get("mileage_rate", 0),
        "parts_markup_pct": supplier.get("parts_markup_pct", 0),
        "custom_items": supplier.get("custom_items", [])
    }


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, user: dict = Depends(get_current_user)):
    _require_owner_or_manager(user)
    org_filter = get_organization_filter(user)
    locked = await db.suppliers.find_one(
        {"id": supplier_id, **org_filter}, {"_id": 0, "is_default_pulse": 1})
    if locked and locked.get("is_default_pulse"):
        raise HTTPException(
            status_code=403,
            detail="The Pulse Fitness Ltd default supplier is locked and can't be removed.",
        )
    result = await db.suppliers.delete_one({"id": supplier_id, **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"success": True}


# ── Equipment assignment (Pulse Pro supplier-machine wizard) ─────

@router.get("/suppliers/{supplier_id}/equipment")
async def list_supplier_equipment(supplier_id: str, user: dict = Depends(get_current_user)):
    """Return equipment currently assigned to this supplier (within the caller's org)."""
    supplier = await _load_supplier_or_404(supplier_id, user)
    org_filter = get_organization_filter(user)
    items = await db.equipment.find(
        {**org_filter, "supplier": supplier["name"]},
        {"_id": 0},
    ).to_list(length=2000)
    return {"equipment": items, "count": len(items)}


@router.post("/suppliers/{supplier_id}/assign-equipment")
async def assign_equipment_to_supplier(
    supplier_id: str,
    body: Dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Bulk-reassign existing equipment (by IDs) to this supplier.

    Body:
      {
        "equipment_ids": ["...", "..."],
        "notify": false   // optional — when true, emails the supplier with the machines
      }
    Overwrites any previous supplier on each machine. Returns the number of
    docs updated and whether a notification was dispatched.
    """
    _require_owner_or_manager(user)
    supplier = await _load_supplier_or_404(supplier_id, user)
    equipment_ids: List[str] = body.get("equipment_ids") or []
    if not isinstance(equipment_ids, list) or not equipment_ids:
        raise HTTPException(status_code=400, detail="equipment_ids must be a non-empty list")

    org_filter = get_organization_filter(user)
    result = await db.equipment.update_many(
        {"id": {"$in": equipment_ids}, **org_filter},
        {"$set": {
            "supplier": supplier["name"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    notified = False
    if body.get("notify") and result.modified_count:
        # Re-read the just-updated docs so the email carries accurate data.
        updated_docs = await db.equipment.find(
            {"id": {"$in": equipment_ids}, **org_filter},
            {"_id": 0},
        ).to_list(length=len(equipment_ids))
        notified = await send_supplier_reassignment_email(
            supplier, user.get("organization_id"), updated_docs,
        )

    return {
        "success": True,
        "assigned": result.modified_count,
        "matched": result.matched_count,
        "supplier_name": supplier["name"],
        "notified": notified,
    }


def _normalise_csv_row(raw: Dict[str, str]) -> Dict[str, Any]:
    """Map arbitrary CSV column names (case/space-insensitive) to our schema keys."""
    mapped: Dict[str, Any] = {}
    for raw_key, raw_val in raw.items():
        if raw_key is None:
            continue
        key = _CSV_COLUMN_ALIASES.get(str(raw_key).strip().lower())
        if key and raw_val is not None:
            mapped[key] = str(raw_val).strip()
    return mapped


def _build_equipment_from_csv(
    row: Dict[str, Any], organization_id: str, user_id: str, supplier_name: str,
) -> Optional[Dict[str, Any]]:
    name = (row.get("name") or "").strip()
    if not name:
        return None
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "organization_id": organization_id,
        "name": name,
        "equipment_type": row.get("equipment_type") or "Other",
        "manufacturer": row.get("manufacturer", ""),
        "model": row.get("model", ""),
        "serial_number": row.get("serial_number", ""),
        "location": row.get("location", ""),
        "install_date": row.get("install_date", ""),
        "purchase_date": row.get("purchase_date", ""),
        "warranty_expiry": row.get("warranty_expiry", ""),
        "notes": row.get("notes", ""),
        "supplier": supplier_name,
        "manuals": [],
        "created_at": now,
        "updated_at": now,
    }


@router.post("/suppliers/{supplier_id}/import-equipment-csv")
async def import_equipment_csv(
    supplier_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Create equipment rows from an uploaded CSV, all assigned to this supplier.

    Accepts friendly column names (case-insensitive):
      Name, Equipment Type, Manufacturer, Model, Serial Number, Location,
      Install Date, Purchase Date, Warranty Expiry, Notes

    Rows with a `Serial Number` that already exists for this organisation are
    rejected with a clear error. Rows without a serial number are inserted
    (duplicates cannot be detected reliably without a serial).
    """
    _require_owner_or_manager(user)
    supplier = await _load_supplier_or_404(supplier_id, user)

    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    raw_bytes = await file.read()
    validate_upload(file_bytes=raw_bytes, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    raw = raw_bytes.decode("utf-8-sig", errors="ignore")
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    reader = csv.DictReader(io.StringIO(raw))
    created, errors = [], []
    org_id = user.get("organization_id")

    # Pre-fetch existing serial numbers for this org so we can detect duplicates
    # without a round-trip per row.
    existing = {}
    async for doc in db.equipment.find(
        {"organization_id": org_id, "serial_number": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "supplier": 1},
    ):
        serial = (doc.get("serial_number") or "").strip().lower()
        if serial:
            existing[serial] = doc

    for idx, raw_row in enumerate(reader, start=2):  # row 1 is the header
        mapped = _normalise_csv_row(raw_row)
        doc = _build_equipment_from_csv(mapped, org_id, user["id"], supplier["name"])
        if not doc:
            errors.append({"row": idx, "error": "Missing required 'Name' column"})
            continue

        serial_key = (doc.get("serial_number") or "").strip().lower()
        if serial_key and serial_key in existing:
            dup = existing[serial_key]
            errors.append({
                "row": idx,
                "error": (
                    f"Serial '{doc['serial_number']}' already exists as "
                    f"'{dup.get('name','Unknown')}'"
                    + (f" (under {dup['supplier']})" if dup.get("supplier") else "")
                    + " — row skipped"
                ),
            })
            continue

        try:
            await db.equipment.insert_one(doc)
            created.append({"id": doc["id"], "name": doc["name"]})
            if serial_key:
                existing[serial_key] = doc  # guard against intra-file dupes
        except Exception as e:
            errors.append({"row": idx, "error": str(e)[:200]})

    return {
        "success": True,
        "created": len(created),
        "errors": errors,
        "supplier_name": supplier["name"],
    }
