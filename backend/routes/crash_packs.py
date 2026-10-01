"""
Crash Pack — in the event of a crash in a company vehicle, the driver completes
a guided "crash pack". Employee-facing wizard lives in the Staff Portal (Vehicle
tab); managers see submitted packs under Operations > Staffing > Vehicles.

Collections:
  • db.crash_packs           — one doc per incident (status draft|submitted)
  • db.crash_pack_settings   — per-org insurance/broker details (editable)
Photos reuse db.files (category "vehicle-photos") so the existing dual-auth
image proxy GET /api/vehicle-checks/photo/{file_id} serves them for both the
driver portal token and the manager platform token.
"""
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from utils.auth import get_current_user, get_current_user_portal
from utils.database import db, put_object, APP_NAME
from routes.staff_portal import (
    _portal_staff, notify_staff, _line_manager_user_id, _is_manager,
)

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Printed on the physical Crash Pack — used as the per-org default.
_INSURANCE_DEFAULTS = {
    "qbe_claim_line": "0808 100 8181",
    "qbe_claim_note": "Select option 3, then give the nearest approved repairer and arrange recovery to an approved repairer if the vehicle is not driveable.",
    "qbe_policy_number": "Y157953FLT0125A",
    "broker_name": "Circle Insurance Services Ltd",
    "broker_phone": "01260 292873",
    "broker_note": "Contact during normal office hours.",
    "rules": [
        "Do not admit liability to anyone.",
        "If the police request documents, tell them you will present them at the nearest Police Station.",
        "Get as much detail as you can while it is still fresh in your mind.",
    ],
}


async def _insurance_for(org: str) -> dict:
    doc = await db.crash_pack_settings.find_one({"organization_id": org}, {"_id": 0}) or {}
    merged = {**_INSURANCE_DEFAULTS, **{k: v for k, v in doc.items() if v not in (None, "", []) and k != "organization_id"}}
    return merged


def _public(p: dict) -> dict:
    p.pop("_id", None)
    return p


# ───────────────────────────── Driver (portal) ──────────────────────────────
@router.get("/new-starter/portal/crash-packs/bootstrap")
async def crash_bootstrap(user: dict = Depends(get_current_user_portal)):
    """Assigned vehicles + prefill + insurance guidance for the wizard."""
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    vehicles = await db.vehicles.find(
        {"organization_id": org, "active": {"$ne": False}, "driver_staff_ids": staff["id"]},
        {"_id": 0, "id": 1, "reg_no": 1, "make_model": 1, "odometer": 1, "vehicle_type": 1, "check_type": 1},
    ).sort("reg_no", 1).to_list(50)
    prefill = {
        "name": staff.get("full_name") or "",
        "mobile": staff.get("mobile") or staff.get("phone") or "",
        "address": staff.get("address") or "",
        "date_of_birth": staff.get("date_of_birth") or "",
    }
    return {"vehicles": vehicles, "prefill": prefill, "insurance": await _insurance_for(org),
            "can_report": len(vehicles) > 0}


@router.get("/new-starter/portal/crash-packs")
async def crash_list_mine(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    rows = await db.crash_packs.find(
        {"organization_id": staff["organization_id"], "reporter_staff_id": staff["id"]},
        {"_id": 0, "data": 0}).sort("created_at", -1).to_list(100)
    return {"packs": rows}


@router.post("/new-starter/portal/crash-packs")
async def crash_create(data: dict = Body(...), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    vehicle_id = (data.get("vehicle_id") or "").strip()
    veh = await db.vehicles.find_one(
        {"organization_id": org, "id": vehicle_id, "active": {"$ne": False}}, {"_id": 0})
    if not veh or staff["id"] not in (veh.get("driver_staff_ids") or []):
        raise HTTPException(403, "Pick one of your assigned vehicles.")
    now = _now()
    pack = {
        "id": str(uuid.uuid4()), "organization_id": org,
        "reporter_staff_id": staff["id"], "reporter_user_id": staff.get("user_id") or user.get("id"),
        "reporter_name": staff.get("full_name"), "reporter_email": staff.get("email"),
        "vehicle_id": vehicle_id, "reg_no": veh.get("reg_no"), "make_model": veh.get("make_model"),
        "status": "draft",
        "data": {"your_details": {"reg_number": veh.get("reg_no"), "make_model": veh.get("make_model"),
                                  "mileage": veh.get("odometer", "")},
                 "accident": {}, "third_parties": [], "witnesses": [], "police": {}},
        "photos": {"vehicle_damage": [], "scene": [], "other_vehicle": [], "sketch": []},
        "created_at": now, "updated_at": now,
    }
    await db.crash_packs.insert_one(pack.copy())
    return {"pack": _public(pack)}


async def _get_mine(pack_id: str, staff: dict) -> dict:
    pack = await db.crash_packs.find_one(
        {"id": pack_id, "organization_id": staff["organization_id"], "reporter_staff_id": staff["id"]},
        {"_id": 0})
    if not pack:
        raise HTTPException(404, "Crash pack not found")
    return pack


@router.get("/new-starter/portal/crash-packs/{pack_id}")
async def crash_get_mine(pack_id: str, user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    return {"pack": await _get_mine(pack_id, staff)}


@router.put("/new-starter/portal/crash-packs/{pack_id}")
async def crash_save(pack_id: str, body: dict = Body(...), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    pack = await _get_mine(pack_id, staff)
    if pack.get("status") == "submitted":
        raise HTTPException(400, "This crash pack has already been submitted.")
    upd = {"updated_at": _now()}
    if "data" in body and isinstance(body["data"], dict):
        upd["data"] = body["data"]
    if "photos" in body and isinstance(body["photos"], dict):
        upd["photos"] = body["photos"]
    await db.crash_packs.update_one({"id": pack_id}, {"$set": upd})
    return {"ok": True}


@router.post("/new-starter/portal/crash-packs/{pack_id}/submit")
async def crash_submit(pack_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    pack = await _get_mine(pack_id, staff)
    if pack.get("status") == "submitted":
        return {"ok": True, "already": True}
    data = body.get("data") if isinstance(body.get("data"), dict) else pack.get("data", {})
    photos = body.get("photos") if isinstance(body.get("photos"), dict) else pack.get("photos", {})
    if not ((data.get("accident") or {}).get("detail") or "").strip():
        raise HTTPException(400, "Please add a short description of the accident before submitting.")
    now = _now()
    mgr_uid = await _line_manager_user_id(org, staff)
    await db.crash_packs.update_one({"id": pack_id}, {"$set": {
        "data": data, "photos": photos, "status": "submitted", "submitted_at": now,
        "updated_at": now, "line_manager_user_id": mgr_uid,
    }})

    veh_label = f"{pack.get('reg_no') or ''} ({pack.get('make_model') or 'vehicle'})".strip()
    when = (data.get("accident") or {}).get("date") or ""
    title = "🚗 Crash Pack submitted — review needed"
    note = f"{staff.get('full_name')} reported a vehicle incident on {veh_label}" + (f" ({when})" if when else "")
    # In-app alert to the driver's line manager (falls back to all managers).
    await notify_staff(
        org=org, recipient_kind="manager", recipient_user_id=mgr_uid,
        type="crash_pack", title=title, body=note, link="vehicles",
        dedupe_key=f"crashpack-{pack_id}")
    # Email the line manager only (if we can resolve one).
    try:
        if mgr_uid:
            mgr = await db.users.find_one({"id": mgr_uid}, {"_id": 0, "email": 1, "full_name": 1})
            if mgr and mgr.get("email"):
                from utils.email import send_email
                html = (
                    f"<p>Hi {(mgr.get('full_name') or 'there')},</p>"
                    f"<p><strong>{staff.get('full_name')}</strong> has submitted a Crash Pack for "
                    f"<strong>{veh_label}</strong>{(' on ' + when) if when else ''}.</p>"
                    f"<p>{(data.get('accident') or {}).get('detail','')[:300]}</p>"
                    f"<p>Open <strong>Operations &rarr; Staffing &rarr; Vehicles &rarr; Crash Packs</strong> "
                    f"to review and print the full report.</p>"
                )
                await send_email(mgr["email"], "Crash Pack submitted for review", html,
                                 organization_id=org, category="support", kind="crash_pack")
    except Exception:  # noqa: BLE001 — never fail submission on email trouble
        pass
    return {"ok": True}


@router.post("/new-starter/portal/crash-packs/photo")
async def crash_upload_photo(file: UploadFile = File(...), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "heic", "heif"):
        raise HTTPException(415, "Please upload an image (JPG, PNG, WEBP or HEIC).")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Image too large — keep under 15MB.")
    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
          "webp": "image/webp", "heic": "image/heic", "heif": "image/heif"}.get(ext, "image/jpeg")
    path = f"{APP_NAME}/vehicle-photos/{org}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ct)
    fid = str(uuid.uuid4())
    await db.files.insert_one({
        "id": fid, "user_id": user.get("id"), "organization_id": org,
        "category": "vehicle-photos", "kind": "crash", "storage_path": result["path"],
        "original_filename": file.filename, "content_type": ct,
        "size": result.get("size", len(data)), "created_at": _now(),
    })
    return {"file_id": fid}


# ───────────────────────────── Manager (platform) ───────────────────────────
def _require_manager(user: dict):
    if not _is_manager(user):
        raise HTTPException(403, "Managers only.")


@router.get("/crash-packs")
async def manager_list(user: dict = Depends(get_current_user)):
    _require_manager(user)
    q = {"status": "submitted"}
    if not user.get("is_master_admin"):
        q["organization_id"] = user.get("organization_id")
    rows = await db.crash_packs.find(q, {"_id": 0, "data": 0}).sort("submitted_at", -1).to_list(500)
    return {"packs": rows}


@router.get("/crash-packs/insurance-settings")
async def manager_get_insurance(user: dict = Depends(get_current_user)):
    _require_manager(user)
    return {"insurance": await _insurance_for(user.get("organization_id")),
            "defaults": _INSURANCE_DEFAULTS}


@router.put("/crash-packs/insurance-settings")
async def manager_set_insurance(body: dict = Body(...), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = user.get("organization_id")
    allowed = ("qbe_claim_line", "qbe_claim_note", "qbe_policy_number",
               "broker_name", "broker_phone", "broker_note")
    upd = {k: (body.get(k) or "").strip() for k in allowed if k in body}
    if isinstance(body.get("rules"), list):
        upd["rules"] = [r.strip() for r in body["rules"] if r and r.strip()]
    upd["organization_id"] = org
    upd["updated_at"] = _now()
    await db.crash_pack_settings.update_one({"organization_id": org}, {"$set": upd}, upsert=True)
    return {"insurance": await _insurance_for(org)}


@router.get("/crash-packs/{pack_id}")
async def manager_get(pack_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    q = {"id": pack_id}
    if not user.get("is_master_admin"):
        q["organization_id"] = user.get("organization_id")
    pack = await db.crash_packs.find_one(q, {"_id": 0})
    if not pack:
        raise HTTPException(404, "Crash pack not found")
    return {"pack": pack, "insurance": await _insurance_for(pack.get("organization_id"))}


__all__ = ["router"]
