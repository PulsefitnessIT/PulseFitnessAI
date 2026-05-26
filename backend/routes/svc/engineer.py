"""
GymAxis Service Operations — Engineer Mobile API.

Iter 215dp (Phase 2).

Mobile-tuned endpoints used by the React PWA at `/svc/engineer`. Designed
for spotty connectivity:
  • Every write accepts an `Idempotency-Key` header so the offline queue
    can replay safely.
  • Reads are snapshot-friendly (today's jobs in one round-trip).
  • Writes return 200/201 even when the object already existed under the
    same key (200) — the offline queue treats that as success.

Engineer identity:
  An engineer is any user with a row in `svc_engineers` keyed by
  `id == user.id`. If the user has no row yet we auto-create a minimal
  profile from their account on first call (this matches Sage's
  Employee → AppointmentResource auto-mirror behaviour).

All field names map 1:1 to /app/memory/SVC_FIELD_MAPPING.md (§4, §5, §6, §7).
"""
__integration_fields__ = {
    # svc_engineers (mirrors Sage Employee per SVC_FIELD_MAPPING §4)
    "engineers.id":                  "sage: Employee.ID · sicon: AppointmentResourceID · bidirectional",
    "engineers.organization_id":     "gymaxis_only: tenant scoping",
    "engineers.sage_user_id":        "sage: Employee.Reference · bidirectional",
    "engineers.full_name":           "sage: Employee.FullName · sicon: AppointmentResourceName · bidirectional",
    "engineers.email":               "sage: Employee.Email · GymAxis → Sage",
    "engineers.mobile":               "sage: Employee.Mobile · GymAxis → Sage",
    "engineers.home_address":        "sage: Employee.Address (postcode used by scheduler scoring) · GymAxis → Sage",
    "engineers.vehicle_reg":         "gymaxis_only: van identifier",
    "engineers.skills":              "sicon: ResourceSkills[] · GymAxis → Sicon",
    "engineers.working_hours":       "sicon: ResourceCalendar · GymAxis → Sicon",
    "engineers.active":              "sage: Employee.IsActive · bidirectional",
    # svc_time_entries (one per engineer × case × shift) — §6
    "time_entries.id":               "sicon: TimeEntryID · GymAxis → Sicon",
    "time_entries.organization_id":  "gymaxis_only: tenant scoping",
    "time_entries.case_id":          "sicon: ServiceCallID · GymAxis → Sicon",
    "time_entries.case_reference":   "sicon: ServiceCallReference · sage: line description fragment · GymAxis → both",
    "time_entries.engineer_id":      "sicon: AppointmentResourceID · sage: Employee.Reference · GymAxis → both",
    "time_entries.engineer_sage_user_id": "sage: Employee.Reference · GymAxis → Sage",
    "time_entries.engineer_name":    "sicon: AppointmentResourceName · GymAxis → Sicon",
    "time_entries.category":         "sicon: TimeEntryCategory (travel|on_site|admin) · GymAxis → Sicon",
    "time_entries.chargeable":       "sage: BillableFlag (drives whether labour line lands on SLInvoice) · GymAxis → Sage",
    "time_entries.start_at":         "sicon: TimeEntryStart · sage: Timesheet.StartAt · GymAxis → both",
    "time_entries.end_at":           "sicon: TimeEntryEnd · sage: Timesheet.EndAt · GymAxis → both",
    "time_entries.duration_minutes": "sicon: TimeEntryDurationMinutes · sage: Quantity (hours converted on quote) · GymAxis → both",
    "time_entries.notes":            "sicon: TimeEntryNotes · GymAxis → Sicon",
    "time_entries.idempotency_key":  "gymaxis_only: offline-queue replay guard",
    # svc_engineer_photos — §7
    "photos.id":                     "sicon: AttachmentID · GymAxis → Sicon",
    "photos.case_id":                "sicon: ServiceCallID · GymAxis → Sicon",
    "photos.case_reference":         "sicon: ServiceCallReference · GymAxis → Sicon",
    "photos.file_url":               "sicon: AttachmentURL · GymAxis → Sicon",
    "photos.mime_type":              "sicon: AttachmentMimeType · GymAxis → Sicon",
    "photos.caption":                "sicon: AttachmentDescription · GymAxis → Sicon",
    "photos.geo":                    "sicon: AttachmentGeo (lat,lng) · GymAxis → Sicon",
    "photos.taken_at":               "sicon: AttachmentTakenAt · GymAxis → Sicon",
    "photos.taken_by_id":            "sicon: AttachmentTakenByID · GymAxis → Sicon",
    "photos.ai":                     "gymaxis_only: persisted AI photo classification (tags/severity/summary)",
    # svc_signatures — §7
    "signatures.id":                 "sicon: SignatureID · GymAxis → Sicon",
    "signatures.case_id":            "sicon: ServiceCallID · GymAxis → Sicon",
    "signatures.case_reference":     "sicon: ServiceCallReference · GymAxis → Sicon",
    "signatures.signed_by_name":     "sicon: SignedByName · sage: SLInvoice.SignedByName · GymAxis → both",
    "signatures.signed_by_role":     "sicon: SignedByRole · GymAxis → Sicon",
    "signatures.signed_at":          "sicon: SignedAt · sage: SLInvoice.SignedAt · GymAxis → both",
    "signatures.image_data":         "sicon: SignatureImageData (base64) · GymAxis → Sicon",
    "signatures.summary":            "sicon: SignatureSummary · GymAxis → Sicon",
    "signatures.captured_by_id":     "sicon: CapturedByID · GymAxis → Sicon",
}

from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.audit import audit_log
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, EN_ROUTE, ON_SITE, REPAIRED, AWAITING_SIGN_OFF, CLOSED,
)
from routes.svc.integrations import sicon_sync, sage_invoice

logger = logging.getLogger(__name__)
# Iter 216h77 — Engineer App access guard. Every endpoint under this
# router requires the caller to either:
#   • have an active Partner Engineer Plan subscription, OR
#   • qualify for the free tier (10+ active referrals), OR
#   • have at least one active customer-added grant, OR
#   • be a master/pulse admin (support & QA access).
# On denial we return 402 with a structured body so the PWA can redirect
# the engineer to the subscription page rather than silently 401.
from routes.partners import require_engineer_app_access  # noqa: E402

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Mobile"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Engineer profile (auto-mirrored from user account)
# ─────────────────────────────────────────────────────────────────

async def _ensure_engineer(user: dict) -> dict:
    """Look up or auto-create an `svc_engineers` row for the caller.

    Maps 1:1 to Sage `Employee` per SVC_FIELD_MAPPING.md §4.
    """
    of = _of(user)
    eng = await db.svc_engineers.find_one({**of, "id": user["id"]})
    if eng:
        return _strip(eng)
    profile = {
        "id": user["id"],
        "organization_id": of["organization_id"],
        "sage_user_id": user.get("sage_user_id") or user.get("id"),
        "full_name": user.get("full_name") or user.get("email") or "Engineer",
        "email": user.get("email") or "",
        "mobile": user.get("phone") or "",
        "home_address": {},
        "vehicle_reg": "",
        "skills": [],
        "working_hours": {},
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_engineers.insert_one(profile)
    profile.pop("_id", None)
    return profile


@router.get("/me")
async def engineer_me(user=Depends(get_current_user)):
    """Profile + today's job count for the home screen."""
    eng = await _ensure_engineer(user)
    of = _of(user)
    today = datetime.now(timezone.utc).date().isoformat()
    open_q = {**of, "assigned_engineer_id": user["id"], "status": {"$in": list(OPEN_STATES)}}
    today_count = await db.svc_cases.count_documents({**open_q, "scheduled_at": {"$regex": f"^{today}"}})
    open_count = await db.svc_cases.count_documents(open_q)
    # Active timer (an entry with no end_at) — drives the "you're on the clock" pill.
    active = await db.svc_time_entries.find_one(
        {**of, "engineer_id": user["id"], "end_at": None}, {"_id": 0},
    )
    return {
        "engineer": eng,
        "stats": {
            "today_jobs": today_count,
            "open_jobs": open_count,
        },
        "active_timer": active,
    }


# ─────────────────────────────────────────────────────────────────
# Today's jobs feed
# ─────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def engineer_jobs(
    when: str = Query("today", description="today | upcoming | open"),
    user=Depends(get_current_user),
):
    """List jobs assigned to the calling engineer, mobile-friendly subset."""
    of = _of(user)
    q = {**of, "assigned_engineer_id": user["id"], "status": {"$in": list(OPEN_STATES)}}
    if when == "today":
        today = datetime.now(timezone.utc).date().isoformat()
        q["$or"] = [
            {"scheduled_at": {"$regex": f"^{today}"}},
            {"scheduled_at": None, "status": {"$in": [EN_ROUTE, ON_SITE]}},
        ]
    elif when == "upcoming":
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        q["scheduled_at"] = {"$gte": tomorrow}
    rows = (
        await db.svc_cases.find(
            q,
            {
                "_id": 0,
                # Keep payload lean for mobile.
                "id": 1, "reference": 1, "title": 1, "priority": 1, "status": 1,
                "site_name": 1, "asset_name": 1, "fault_code": 1, "scheduled_at": 1,
                "estimated_minutes": 1, "sla_resolve_at": 1, "customer_name": 1,
                "customer_phone": 1,
            },
        ).sort([("scheduled_at", 1), ("sla_resolve_at", 1)]).to_list(200)
    )
    return {"jobs": rows, "count": len(rows)}


@router.get("/jobs/{case_id}")
async def engineer_job_detail(case_id: str, user=Depends(get_current_user)):
    """Full job context for the engineer detail screen."""
    of = _of(user)
    case = _strip(await db.svc_cases.find_one({"id": case_id, **of}))
    if not case:
        raise HTTPException(404, "Job not found")
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"]:
        # Engineers may only see their own jobs.
        raise HTTPException(403, "Not assigned to this job")
    events = (
        await db.svc_case_events
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("at", -1).limit(50).to_list(50)
    )
    photos = (
        await db.svc_engineer_photos
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("taken_at", -1).limit(50).to_list(50)
    )
    time_entries = (
        await db.svc_time_entries
        .find({"case_id": case_id, **of, "engineer_id": user["id"]}, {"_id": 0})
        .sort("start_at", -1).limit(20).to_list(20)
    )
    # Iter 216h85 — Asset history (last 3 prior cases on the same asset)
    asset_history: list = []
    asset_id = case.get("asset_id") or ""
    asset_name = (case.get("asset_name") or "").strip()
    if asset_id or asset_name:
        history_q: dict = {
            **of,
            "id": {"$ne": case_id},
            "status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]},
        }
        if asset_id:
            history_q["asset_id"] = asset_id
        else:
            history_q["asset_name"] = asset_name
        asset_history = (
            await db.svc_cases.find(
                history_q,
                {
                    "_id": 0, "id": 1, "reference": 1, "title": 1,
                    "fault_code": 1, "status": 1, "closed_at": 1,
                    "created_at": 1, "customer_rating": 1, "resolution_notes": 1,
                },
            ).sort([("closed_at", -1), ("created_at", -1)]).limit(3).to_list(3)
        )
    # Iter 216h89 — Pre-job H&S signoff state (so PWA gates on-site timer)
    safety_signoff = await db.svc_case_safety_signoffs.find_one(
        {"case_id": case_id, **of, "engineer_id": user["id"]},
        {"_id": 0, "id": 1, "signed_at": 1, "ticked_item_ids": 1, "remarks": 1},
        sort=[("signed_at", -1)],
    )
    safety_template = None
    if not safety_signoff:
        from routes.svc.safety import _resolve_template
        tpl = await _resolve_template(of["organization_id"])
        safety_template = {"id": tpl["id"], "items": tpl["items"]}
    return {
        **case,
        "events": events,
        "photos": photos,
        "time_entries": time_entries,
        "asset_history": asset_history,
        "safety_signoff": safety_signoff,
        "safety_template": safety_template,
    }


# ─────────────────────────────────────────────────────────────────
# Time tracking — start / stop
# ─────────────────────────────────────────────────────────────────

async def _idempotent_insert(collection, doc: dict, idem_key: str | None) -> dict | None:
    """Insert under an idempotency key; if a row exists return it (None == proceed)."""
    if idem_key:
        existing = await collection.find_one({"idempotency_key": idem_key}, {"_id": 0})
        if existing:
            return existing
        doc["idempotency_key"] = idem_key
    await collection.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _check_idempotent(collection, idem_key: str | None) -> dict | None:
    """Pre-check for idempotent replay so the caller can short-circuit
    expensive side effects (timer auto-stop, SLA transitions, sicon push).
    """
    if not idem_key:
        return None
    return await collection.find_one({"idempotency_key": idem_key}, {"_id": 0})


@router.post("/time/start")
async def time_start(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Start a work timer.

    Body: {case_id, category?: 'travel'|'on_site'|'admin', notes?: str}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    if not case_id:
        raise HTTPException(400, "case_id required")
    # Idempotent replay short-circuit (must run before auto-stop side effects).
    replay = await _check_idempotent(db.svc_time_entries, idempotency_key)
    if replay:
        return replay
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    # Iter 216h89 — H&S gate. Engineers must complete the pre-job safety
    # signoff before starting the on_site timer. Travel/admin timers are
    # not gated (the gate fires when the engineer arrives on site).
    if (data.get("category") or "on_site") == "on_site" and not case.get("safety_signoff_at"):
        raise HTTPException(
            status_code=412,
            detail={
                "code": "safety_signoff_required",
                "message": "Complete the H&S checklist before starting the on-site timer.",
            },
        )
    # Stop any open timer on this engineer first — only one active at a time.
    await db.svc_time_entries.update_many(
        {**of, "engineer_id": user["id"], "end_at": None},
        {"$set": {"end_at": _now(), "auto_stopped": True, "updated_at": _now()}},
    )
    eng = await _ensure_engineer(user)
    entry = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_sage_user_id": eng.get("sage_user_id") or "",
        "engineer_name": eng.get("full_name") or "",
        "category": (data.get("category") or "on_site"),
        "chargeable": bool(data.get("chargeable")),
        "start_at": _now(),
        "end_at": None,
        "duration_minutes": 0,
        "notes": (data.get("notes") or "").strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    entry = await _idempotent_insert(db.svc_time_entries, entry, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="time_start", actor=user,
        body=f"Engineer started {entry['category']} timer",
        extra={"time_entry_id": entry["id"], "category": entry["category"]},
    )
    # If engineer not yet on site, transition appropriately.
    target = ON_SITE if entry["category"] == "on_site" else EN_ROUTE if entry["category"] == "travel" else None
    if target and case.get("status") != target:
        try:
            await state_transition(
                case_id=case_id, organization_id=of["organization_id"],
                target_state=target, actor=user, reason="auto: engineer started timer",
            )
        except ValueError:
            # Illegal transition (e.g., from on_site→en_route) — ignore and keep current state.
            pass
    await sicon_sync.push_time_entry(entry, case_reference=case.get("reference"))
    return entry


@router.post("/time/stop")
async def time_stop(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Stop the active timer (or a specific entry by id)."""
    of = _of(user)
    entry_id = (data or {}).get("entry_id")
    q = {**of, "engineer_id": user["id"]}
    if entry_id:
        q["id"] = entry_id
    else:
        q["end_at"] = None
    entry = await db.svc_time_entries.find_one(q)
    if not entry:
        raise HTTPException(404, "No active time entry")
    end_at = _now()
    start_dt = datetime.fromisoformat(entry["start_at"])
    duration_minutes = max(0, int((datetime.fromisoformat(end_at) - start_dt).total_seconds() // 60))
    await db.svc_time_entries.update_one(
        {"id": entry["id"]},
        {"$set": {
            "end_at": end_at,
            "duration_minutes": duration_minutes,
            "notes": (data.get("notes") or entry.get("notes") or "").strip(),
            "updated_at": _now(),
        }},
    )
    entry["end_at"] = end_at
    entry["duration_minutes"] = duration_minutes
    await append_event(
        case_id=entry["case_id"], organization_id=of["organization_id"],
        event_type="time_stop", actor=user,
        body=f"Stopped {entry['category']} timer ({duration_minutes}m)",
        extra={"time_entry_id": entry["id"], "duration_minutes": duration_minutes},
    )
    await sicon_sync.push_time_entry(entry, case_reference=entry.get("case_reference") or "")
    entry.pop("_id", None)
    return entry


# ─────────────────────────────────────────────────────────────────
# Photo & signature capture
# ─────────────────────────────────────────────────────────────────

@router.post("/photos")
async def add_photo(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Attach a photo or short video (already uploaded via /api/files/upload)
    to a case.

    Body: {case_id, file_url, mime_type?, caption?, geo?: {lat,lng},
           taken_at?, duration_seconds?}

    The `kind` field is derived from `mime_type`:
      * `image/*` → kind="photo" (default)
      * `video/*` → kind="video"
    The frontend uses this to render a play overlay on video tiles.
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    file_url = (data or {}).get("file_url")
    if not case_id or not file_url:
        raise HTTPException(400, "case_id and file_url required")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    mime = (data.get("mime_type") or "image/jpeg").lower()
    kind = "video" if mime.startswith("video/") else "photo"
    photo = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "file_url": file_url,
        "mime_type": mime,
        "kind": kind,
        "duration_seconds": data.get("duration_seconds"),
        "caption": (data.get("caption") or "").strip(),
        "geo": data.get("geo") or {},
        "taken_at": data.get("taken_at") or _now(),
        "taken_by_id": user["id"],
        "taken_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
    }
    photo = await _idempotent_insert(db.svc_engineer_photos, photo, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="photo" if kind == "photo" else "note",
        actor=user,
        body=photo.get("caption") or ("Video attached" if kind == "video" else "Photo attached"),
        extra={"photo_id": photo["id"], "file_url": file_url, "kind": kind},
    )
    await sicon_sync.push_attachment(photo, case_reference=case.get("reference"))
    return photo


@router.post("/signature")
async def add_signature(
    data: dict,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Record a customer sign-off signature.

    Body: {case_id, signed_by_name, signed_by_role?, image_data (base64),
           summary?}
    """
    of = _of(user)
    case_id = (data or {}).get("case_id")
    signed_by_name = ((data or {}).get("signed_by_name") or "").strip()
    image_data = (data or {}).get("image_data") or ""
    if not case_id or not signed_by_name or not image_data:
        raise HTTPException(400, "case_id, signed_by_name, image_data required")
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    sig = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "signed_by_name": signed_by_name,
        "signed_by_role": (data.get("signed_by_role") or "").strip(),
        "signed_at": _now(),
        "image_data": image_data,
        "summary": (data.get("summary") or "").strip(),
        "device_meta": data.get("device_meta") or {},
        "captured_by_id": user["id"],
        "captured_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(),
    }
    sig = await _idempotent_insert(db.svc_signatures, sig, idempotency_key)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="signature", actor=user,
        body=f"Signed by {signed_by_name}",
        extra={"signature_id": sig["id"], "summary": sig["summary"]},
    )
    await sicon_sync.push_signature(sig, case_reference=case.get("reference"))
    # Iter 216h155 — compliance audit. Customer signature is a legally
    # binding sign-off — must be in the immutable audit ledger.
    try:
        await audit_log(
            action="svc.case.signature_captured",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_signature",
            resource_id=sig["id"],
            details=f"case={case.get('reference', '')} · "
                    f"signed_by={signed_by_name}",
        )
    except Exception as e:
        logger.warning("[audit] signature failed: %s", e)
    return sig


# ─────────────────────────────────────────────────────────────────
# Job complete / sign-off
# ─────────────────────────────────────────────────────────────────

@router.post("/jobs/{case_id}/complete")
async def engineer_complete(
    case_id: str,
    data: dict,
    user=Depends(get_current_user),
):
    """Engineer flags the job as repaired/closed.

    Body: {summary, chargeable?, target?: 'repaired'|'awaiting_sign_off'|'closed'}
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of})
    if not case:
        raise HTTPException(404, "Case not found")
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"]:
        raise HTTPException(403, "Not assigned to this job")
    summary = ((data or {}).get("summary") or "").strip()
    if not summary:
        raise HTTPException(400, "summary required")
    target = (data.get("target") or "awaiting_sign_off").lower()
    if target not in (REPAIRED, AWAITING_SIGN_OFF, CLOSED):
        raise HTTPException(400, "target must be repaired | awaiting_sign_off | closed")

    # Iter 220 — Validate & normalise work-report custom fields before any
    # state transitions, so required-field errors don't leave half-applied
    # side effects (timer stop, status change) behind.
    raw_custom_fields = data.get("custom_fields")
    custom_fields_clean: dict | None = None
    if raw_custom_fields is not None:
        from routes.svc.work_report_fields import validate_and_normalise_custom_field_values
        custom_fields_clean = await validate_and_normalise_custom_field_values(
            organization_id=of["organization_id"],
            case=case,
            raw_values=raw_custom_fields,
        )

    # Stop any open timer first.
    await db.svc_time_entries.update_many(
        {**of, "engineer_id": user["id"], "end_at": None},
        {"$set": {"end_at": _now(), "duration_minutes": 0, "updated_at": _now()}},
    )
    # Append the engineer's fix summary to the timeline so it's captured even
    # before the customer sign-off completes.
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=summary,
        extra={"visibility": "customer", "kind": "fix_summary"},
    )
    if data.get("chargeable") is not None:
        await db.svc_cases.update_one(
            {"id": case_id}, {"$set": {"chargeable": bool(data["chargeable"]), "updated_at": _now()}},
        )
    # Iter 220 — Persist sanitised work-report custom fields onto the case.
    if custom_fields_clean is not None:
        await db.svc_cases.update_one(
            {"id": case_id, **of},
            {"$set": {
                "work_report_custom_fields": custom_fields_clean,
                "work_report_custom_fields_updated_at": _now(),
                "updated_at": _now(),
            }},
        )
    # If the engineer is still en_route or assigned, walk through on_site
    # first — the engineer is clearly on site (about to complete).
    current = case.get("status")
    if current in ("assigned", "en_route") and target != ON_SITE:
        try:
            case = await state_transition(
                case_id=case_id, organization_id=of["organization_id"],
                target_state=ON_SITE, actor=user, reason="auto: engineer wrap-up",
            )
        except ValueError:
            pass
    try:
        case = await state_transition(
            case_id=case_id, organization_id=of["organization_id"],
            target_state=target, actor=user, reason=summary[:200],
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await sicon_sync.push_case(case)
    if target == CLOSED:
        await sage_invoice.enqueue_invoice_for_case(case)
    # Iter 220c — successful complete → drop the engineer's in-flight
    # draft so the form isn't pre-filled with old text the next time
    # they open the case.
    await db.svc_engineer_job_drafts.delete_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
    )
    case.pop("_id", None)
    return case


# ─────────────────────────────────────────────────────────────────
# Iter 220c — Engineer draft autosave (data-loss prevention)
# ─────────────────────────────────────────────────────────────────
# Engineers were losing their Work Summary text when switching between
# tabs in the job detail (the React component unmounts on tab change).
# We persist a debounced draft per (engineer, case) here so an offline
# device crash, app close, or tab navigation never wipes mid-job notes.


@router.get("/jobs/{case_id}/draft")
async def get_engineer_draft(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    doc = await db.svc_engineer_job_drafts.find_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
        {"_id": 0},
    )
    return doc or {"case_id": case_id, "engineer_id": user["id"], "draft": {}}


@router.put("/jobs/{case_id}/draft")
async def upsert_engineer_draft(
    case_id: str,
    data: dict,
    user=Depends(get_current_user),
):
    """Body: {draft: {summary?, target?, signature_name?, custom_fields?, ...}}

    The draft blob is opaque to the backend — the frontend owns its
    shape — but we cap the size to keep one runaway client from
    flooding the collection. 32 KB is plenty for the longest plausible
    work-summary + custom-fields blob.
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    draft = (data or {}).get("draft") or {}
    if not isinstance(draft, dict):
        raise HTTPException(400, "draft must be an object")
    import json as _json
    try:
        payload_size = len(_json.dumps(draft).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "draft is not JSON-serialisable") from exc
    if payload_size > 32 * 1024:
        raise HTTPException(413, "draft too large (max 32 KB)")
    now_iso = _now()
    await db.svc_engineer_job_drafts.update_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
        {"$set": {
            **of,
            "case_id": case_id,
            "engineer_id": user["id"],
            "draft": draft,
            "updated_at": now_iso,
            "bytes": payload_size,
        }, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    return {"ok": True, "case_id": case_id, "saved_at": now_iso, "bytes": payload_size}


@router.delete("/jobs/{case_id}/draft")
async def clear_engineer_draft(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    await db.svc_engineer_job_drafts.delete_one(
        {**of, "case_id": case_id, "engineer_id": user["id"]},
    )
    return {"ok": True, "case_id": case_id}


__all__ = ["router"]
