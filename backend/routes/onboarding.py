from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Body
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import csv
import io
import uuid
import logging

from utils.database import db, APP_NAME, put_object
from utils.auth import get_current_user, get_organization_filter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/organization/logo")
async def upload_org_logo(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from utils.file_validation import validate_upload, MIME_IMAGES
    if not user.get('organization_id'):
        raise HTTPException(status_code=400, detail="No organization")

    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_IMAGES, max_size=10 * 1024 * 1024)
    storage_path = f"{APP_NAME}/logos/{user['organization_id']}/{uuid.uuid4()}.{ext}"
    result = put_object(storage_path, data, ct)
    storage_url = result.get("url") or storage_path

    # Iter 216n — register a `files` doc so the public-files route
    # (used by the GET /organization/logo helper to resolve relative
    # paths into /api/public/files/{id} URLs) can find the upload.
    # Previously, free-trial logos uploaded successfully but Navbar
    # never rendered them because the storage_path lookup returned
    # None — the file doc was missing.
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id,
        "organization_id": user["organization_id"],
        "uploader_id": user.get("id"),
        "uploader_email": user.get("email"),
        "filename": f"{user['organization_id']}-logo.{ext}",
        "original_filename": file.filename,
        "storage_path": storage_path,
        "storage_url": storage_url,
        "mime_type": ct,
        "size_bytes": len(data),
        "category": "branding",
        "is_public": True,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Persist BOTH the canonical `/api/public/files/{id}` URL on the
    # org doc AND on the branding subdoc so every consumer
    # (Navbar, supplier case page, branded membership pages, brag
    # share cards) renders the logo without extra plumbing.
    public_url = f"/api/public/files/{file_id}"
    await db.organizations.update_one(
        {"id": user['organization_id']},
        {"$set": {
            "logo_url": public_url,
            "branding.logo_url": public_url,
        }}
    )

    return {"logo_url": public_url, "file_id": file_id}


@router.post("/organization/po-template")
async def upload_po_template(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from utils.file_validation import validate_upload, MIME_OFFICE
    if not user.get('organization_id'):
        raise HTTPException(status_code=400, detail="No organization")

    ext = file.filename.split(".")[-1] if "." in file.filename else "docx"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_OFFICE, max_size=15 * 1024 * 1024)
    path = f"{APP_NAME}/po-templates/{user['organization_id']}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ct)

    template_url = result.get("url", result["path"])
    await db.organizations.update_one(
        {"id": user['organization_id']},
        {"$set": {"po_template_url": template_url, "po_template_name": file.filename}}
    )

    return {"template_url": template_url, "filename": file.filename}


@router.post("/onboarding/equipment")
async def onboard_equipment(data: dict, user: dict = Depends(get_current_user)):
    items = data.get("items", [])
    # Iter 216h194 — Craig's regression: equipment added via the
    # onboarding wizard didn't show up in the Equipment tab because the
    # per-site filter (`site_id=<active>`) excluded rows with no site
    # attached. The wizard now sends an explicit `site_id`; for older
    # callers that didn't, infer it: if the caller passed a top-level
    # `site_id` in the payload we use that, else if the org has exactly
    # one site we tag every row with it, else we leave it blank (legacy
    # behaviour). This guarantees the rows immediately match the
    # active-site filter that drives the Equipment list.
    payload_site_id = (data.get("site_id") or "").strip() or None
    inferred_site_id = payload_site_id
    if not inferred_site_id:
        org_id = user.get("organization_id")
        if org_id:
            org_sites = await db.sites.find(
                {"organization_id": org_id, "status": {"$ne": "archived"}},
                {"_id": 0, "id": 1},
            ).to_list(2)
            if len(org_sites) == 1:
                inferred_site_id = org_sites[0].get("id")
    onboarded = []
    for item in items:
        equip = {
            "id": str(uuid.uuid4()),
            "name": item.get("name", ""),
            "serial_number": item.get("serial_number", ""),
            "equipment_type": item.get("equipment_type", ""),
            "manufacturer": item.get("manufacturer", ""),
            "model": item.get("model", ""),
            "supplier": item.get("manufacturer", ""),
            "location": item.get("location", ""),
            "photo_url": item.get("photo_url"),
            "purchase_date": item.get("purchase_date", ""),
            "warranty_expiry": item.get("warranty_expiry", ""),
            "sla_response_time": item.get("sla_response_time", ""),
            "sla_contract_ref": item.get("sla_contract_ref", ""),
            "sla_expiry": item.get("sla_expiry", ""),
            "status": "operational",
            "organization_id": user.get('organization_id'),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get('full_name', user.get('email')),
        }
        # Per-item site_id overrides the inferred one (lets bulk import
        # tools spread one onboarding call across multiple sites).
        item_site_id = (item.get("site_id") or "").strip() or inferred_site_id
        if item_site_id:
            equip["site_id"] = item_site_id
        await db.equipment.insert_one(equip)
        equip.pop('_id', None)
        onboarded.append(equip)
    return {"onboarded": onboarded, "count": len(onboarded), "site_id": inferred_site_id}


@router.get("/api-keys")
async def list_api_keys(user: dict = Depends(get_current_user)):
    keys = await db.api_keys.find({"user_id": user['id']}, {"_id": 0, "key": 0}).to_list(50)
    return {"api_keys": keys}


@router.post("/api-keys/generate")
async def generate_api_key(user: dict = Depends(get_current_user)):
    api_key = f"gfx_{uuid.uuid4().hex}"
    key_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "key": api_key,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None
    }
    await db.api_keys.insert_one(key_doc)
    return {
        "api_key": api_key,
        "created_at": key_doc['created_at'],
        "note": "Store this key securely. It won't be shown again."
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    result = await db.api_keys.update_one(
        {"id": key_id, "user_id": user['id']},
        {"$set": {"active": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True}


# ─────────── Gamified onboarding progress (4-stage flow) ───────────

_ONBOARDING_STAGES = ("suppliers", "equipment", "staff", "live")


async def _count_onboarding_state(user: dict) -> dict:
    org_filter = get_organization_filter(user)
    organization_id = user.get("organization_id")
    suppliers = await db.suppliers.count_documents(org_filter)
    equipment = await db.equipment.count_documents(org_filter)
    staff_active = await db.users.count_documents({
        "organization_id": organization_id,
        "role": {"$in": ["manager", "staff"]},
        "disabled": {"$ne": True},
    })
    staff_invited = await db.invites.count_documents({
        "organization_id": organization_id, "status": "pending",
    })
    return {
        "suppliers": suppliers, "equipment": equipment,
        "staff_active": staff_active, "staff_invited": staff_invited,
    }


@router.get("/onboarding/status")
async def get_onboarding_status(user: dict = Depends(get_current_user)) -> dict:
    """Return progress through the 4-stage gamified onboarding journey."""
    counts = await _count_onboarding_state(user)
    staff_total = counts["staff_active"] + counts["staff_invited"]

    stages = {
        "suppliers": counts["suppliers"] > 0,
        "equipment": counts["equipment"] > 0,
        "staff":     staff_total > 0,
    }
    stages["live"] = stages["suppliers"] and stages["equipment"] and stages["staff"]

    completed = sum(1 for done in stages.values() if done)
    percent = round((completed / len(_ONBOARDING_STAGES)) * 100)

    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    return {
        "stages": stages,
        "completed_count": completed,
        "total_count": len(_ONBOARDING_STAGES),
        "percent": percent,
        "dismissed": bool((org or {}).get("onboarding_banner_dismissed")),
        "completed_at": (org or {}).get("onboarding_completed_at"),
        "counts": counts,
    }


@router.post("/onboarding/dismiss")
async def dismiss_onboarding_banner(user: dict = Depends(get_current_user)) -> dict:
    await db.organizations.update_one(
        {"id": user.get("organization_id")},
        {"$set": {"onboarding_banner_dismissed": True}},
    )
    return {"success": True}


@router.post("/onboarding/complete")
async def mark_onboarding_complete(user: dict = Depends(get_current_user)) -> dict:
    await db.organizations.update_one(
        {"id": user.get("organization_id")},
        {"$set": {
            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
            "onboarding_banner_dismissed": True,
        }},
    )
    return {"success": True}


_EQUIPMENT_CSV_HEADERS = [
    "name", "equipment_type", "manufacturer", "model",
    "serial_number", "location", "purchase_date", "warranty_expiry",
    "supplier", "sla_response_time",
]

_EQUIPMENT_CSV_SAMPLE_ROWS = [
    ["Treadmill 1", "cardio", "Precor", "TRM 425", "SN-TRM-001", "Cardio Floor", "2023-06-15", "2025-06-15", "Precor", "4 hours"],
    ["Chest Press 1", "strength", "Life Fitness", "Insignia CP", "SN-LF-CP-01", "Strength Zone", "2023-01-10", "2026-01-10", "Life Fitness", "Next business day"],
    ["Spin Bike 1", "cardio", "Keiser", "M3i", "SN-KI-M3-001", "Studio 1", "2022-11-05", "", "Keiser", ""],
]


@router.get("/onboarding/equipment-template.csv")
async def download_equipment_csv_template(_user: dict = Depends(get_current_user)) -> StreamingResponse:
    """Download a ready-to-fill equipment CSV template with 3 sample rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EQUIPMENT_CSV_HEADERS)
    writer.writerows(_EQUIPMENT_CSV_SAMPLE_ROWS)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gymaxis-equipment-template.csv"},
    )


def _strip(row: dict, key: str, default: str = "") -> str:
    """Trim whitespace from a CSV cell; return `default` if empty."""
    return (row.get(key) or default).strip()


def _csv_row_to_equipment_doc(row: dict, organization_id: str, now: str) -> dict | None:
    """Convert a CSV row to an equipment doc, or return None if row is skippable."""
    name = _strip(row, "name")
    serial = _strip(row, "serial_number")
    if not name and not serial:
        return None
    return {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "name": name or serial,
        "equipment_type": _strip(row, "equipment_type", "other").lower(),
        "manufacturer": _strip(row, "manufacturer"),
        "model": _strip(row, "model"),
        "serial_number": serial,
        "location": _strip(row, "location"),
        "purchase_date": _strip(row, "purchase_date") or None,
        "warranty_expiry": _strip(row, "warranty_expiry") or None,
        "supplier": _strip(row, "supplier"),
        "sla_response_time": _strip(row, "sla_response_time"),
        "created_at": now,
    }


async def _upsert_equipment_by_serial(doc: dict) -> None:
    """Insert equipment, or update in place if serial_number already exists in the org."""
    serial = doc.get("serial_number")
    if serial:
        existing = await db.equipment.find_one(
            {"organization_id": doc["organization_id"], "serial_number": serial},
            {"_id": 0, "id": 1},
        )
        if existing:
            await db.equipment.update_one(
                {"id": existing["id"]},
                {"$set": {**doc, "id": existing["id"]}},
            )
            return
    await db.equipment.insert_one(doc)


@router.post("/onboarding/equipment-csv-import")
async def import_equipment_csv(payload: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Bulk insert equipment from a CSV payload. Payload shape: {csv_content: str}.
    Rows with neither a name nor a serial are skipped. Duplicates (matching serial
    within the org) are merged in-place.
    """
    csv_content = payload.get("csv_content", "")
    if not csv_content.strip():
        raise HTTPException(status_code=400, detail="Empty CSV content")

    reader = csv.DictReader(io.StringIO(csv_content))
    organization_id = user.get("organization_id")
    now = datetime.now(timezone.utc).isoformat()

    imported = 0
    skipped = 0
    for row in reader:
        doc = _csv_row_to_equipment_doc(row, organization_id, now)
        if doc is None:
            skipped += 1
            continue
        await _upsert_equipment_by_serial(doc)
        imported += 1

    return {"success": True, "imported": imported, "skipped": skipped}
