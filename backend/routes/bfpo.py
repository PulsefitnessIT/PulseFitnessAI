"""
Pulse Fitness — MOD / BFPO Engineer Portal API.

A role-scoped experience layered on top of the shared service-case engine
(`db.svc_cases` + `utils.svc_state`). It does NOT create a duplicate job
store: BFPO jobs ARE svc_cases, tagged with territory/site/country and a
`bfpo=True` marker, worked by engineers and tracked by MOD staff.

Roles (stored on the user doc as `bfpo_role`):
  • engineer  — sees only their territory's sites & jobs; does the work.
  • lead      — everything an engineer can do + territory-wide visibility.
  • staff     — UK MOD service staff; global oversight + allocation.

Server-side scoping is enforced on every read/write so an engineer can
never reach another territory's job by changing an id.
"""
from datetime import datetime, timezone, date
from typing import Optional
import io
import uuid
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response

from utils.database import db
from utils.auth import get_current_user
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, ASSIGNED, ON_SITE, PAUSED_PARTS, AWAITING_SIGN_OFF, CLOSED, NEW,
)
from routes.svc.cases import next_reference, compute_sla_targets

logger = logging.getLogger(__name__)

BFPO_ORG_ID = "bfpo-mod-org"

router = APIRouter(prefix="/bfpo", tags=["MOD · BFPO Engineer Portal"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────
# Identity + scoping
# ─────────────────────────────────────────────────────────────────

def _role(user: dict) -> str:
    r = (user.get("bfpo_role") or "").lower()
    if r in ("engineer", "lead", "staff"):
        return r
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return "staff"
    return ""


async def _require_bfpo(user=Depends(get_current_user)) -> dict:
    role = _role(user)
    if not role:
        raise HTTPException(403, "Not a MOD / BFPO portal user")
    return user


async def _require_staff(user=Depends(_require_bfpo)) -> dict:
    if _role(user) != "staff":
        raise HTTPException(403, "MOD service staff access required")
    return user


def _of() -> dict:
    return {"organization_id": BFPO_ORG_ID, "bfpo": True}


async def _engineer_scope(user: dict) -> dict:
    """Return {'territory_ids', 'active_site_ids', 'all_site_ids'} the caller
    may see. Leads/staff see everything (empty => unrestricted)."""
    role = _role(user)
    if role in ("lead", "staff"):
        return {"unrestricted": True, "territory_ids": list(user.get("bfpo_territory_ids") or []),
                "active_site_ids": [], "all_site_ids": []}
    terr = list(user.get("bfpo_territory_ids") or [])
    active_sites: set[str] = set()
    all_sites: set[str] = set()
    today = _today()
    async for g in db.bfpo_visiting_access.find(
        {"organization_id": BFPO_ORG_ID, "engineer_id": user["id"]}, {"_id": 0},
    ):
        sid = g.get("site_id")
        if sid:
            all_sites.add(sid)
            if (g.get("from_date") or "") <= today <= (g.get("to_date") or "9999"):
                active_sites.add(sid)
    return {"unrestricted": False, "territory_ids": terr,
            "active_site_ids": list(active_sites), "all_site_ids": list(all_sites)}


async def _scoped_case_query(user: dict, *, read: bool = True) -> dict:
    """Base Mongo query restricting cases to what the caller may see."""
    q = dict(_of())
    scope = await _engineer_scope(user)
    if scope["unrestricted"]:
        return q
    ors = [{"assigned_engineer_id": user["id"]}]
    if scope["territory_ids"]:
        ors.append({"territory_id": {"$in": scope["territory_ids"]}})
    site_ids = scope["all_site_ids"] if read else scope["active_site_ids"]
    if site_ids:
        ors.append({"site_id": {"$in": site_ids}})
    q["$or"] = ors
    return q


async def _get_scoped_case(user: dict, case_id: str, *, read: bool = True) -> dict:
    q = await _scoped_case_query(user, read=read)
    q["id"] = case_id
    case = await db.svc_cases.find_one(q, {"_id": 0})
    if not case:
        raise HTTPException(404, "Job not found")
    return case


# ─────────────────────────────────────────────────────────────────
# Engineer — home + jobs
# ─────────────────────────────────────────────────────────────────

_TERMINAL = ["closed", "invoiced", "repaired", "awaiting_sign_off", "rejected"]


async def _kpis(base_q: dict) -> dict:
    open_q = {**base_q, "status": {"$in": list(OPEN_STATES)}}
    today = _today()
    urgent = {**open_q, "$and": [{"$or": [{"priority": "p1"}, {"safety_critical": True}]}]}
    return {
        "open": await db.svc_cases.count_documents(open_q),
        "urgent": await db.svc_cases.count_documents(urgent),
        "waiting_parts": await db.svc_cases.count_documents({**base_q, "status": PAUSED_PARTS}),
        "return_visit": await db.svc_cases.count_documents({**base_q, "return_visit": True, "status": {"$in": list(OPEN_STATES)}}),
        "overdue": await db.svc_cases.count_documents({
            **open_q, "sla_resolve_at": {"$lt": _now(), "$ne": None},
        }),
    }


@router.get("/me")
async def bfpo_me(user=Depends(_require_bfpo)):
    role = _role(user)
    base_q = await _scoped_case_query(user)
    terr_ids = list(user.get("bfpo_territory_ids") or [])
    territories = []
    if terr_ids:
        territories = await db.bfpo_territories.find(
            {"organization_id": BFPO_ORG_ID, "id": {"$in": terr_ids}}, {"_id": 0},
        ).to_list(50)
    return {
        "user": {"id": user["id"], "name": user.get("full_name") or user.get("email"),
                 "email": user.get("email"), "role": role},
        "territories": territories,
        "kpis": await _kpis(base_q),
    }


_FILTER_MAP = {
    "all_open": {"status": {"$in": list(OPEN_STATES)}},
    "new": {"status": {"$in": [NEW, "triaged", ASSIGNED]}},
    "in_progress": {"status": {"$in": ["en_route", ON_SITE]}},
    "waiting_parts": {"status": PAUSED_PARTS},
    "return_visit": {"return_visit": True, "status": {"$in": list(OPEN_STATES)}},
    "completed": {"status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]}},
}

_JOB_PROJECTION = {
    "_id": 0, "id": 1, "reference": 1, "title": 1, "description": 1, "priority": 1,
    "status": 1, "safety_critical": 1, "site_name": 1, "site_id": 1, "territory_name": 1,
    "country": 1, "asset_name": 1, "fault_code": 1, "scheduled_at": 1, "sla_resolve_at": 1,
    "assigned_engineer_id": 1, "assigned_engineer_name": 1, "return_visit": 1,
    "waiting_reason": 1, "created_at": 1, "closed_at": 1, "customer_name": 1,
}


@router.get("/jobs")
async def bfpo_jobs(when: str = Query("all_open"), user=Depends(_require_bfpo)):
    base_q = await _scoped_case_query(user)
    q = {**base_q, **_FILTER_MAP.get(when, _FILTER_MAP["all_open"])}
    sort = [("closed_at", -1)] if when == "completed" else [("priority", 1), ("sla_resolve_at", 1)]
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort(sort).to_list(200)
    return {"jobs": rows, "count": len(rows)}


@router.get("/jobs/{case_id}")
async def bfpo_job_detail(case_id: str, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    events = await db.svc_case_events.find(
        {"case_id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0},
    ).sort("at", -1).limit(80).to_list(80)
    photos = await db.svc_engineer_photos.find(
        {"case_id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0},
    ).sort("taken_at", -1).limit(40).to_list(40)
    site = None
    if case.get("site_id"):
        site = await db.sites.find_one(
            {"id": case["site_id"], "organization_id": BFPO_ORG_ID}, {"_id": 0},
        )
    equipment = []
    eq_ids = list(case.get("equipment_ids") or [])
    if case.get("asset_id"):
        eq_ids.append(case["asset_id"])
    if eq_ids:
        equipment = await db.equipment.find(
            {"id": {"$in": eq_ids}, "organization_id": BFPO_ORG_ID}, {"_id": 0},
        ).to_list(50)
    # asset history — prior closed jobs on the same asset
    asset_history = []
    if case.get("asset_id"):
        asset_history = await db.svc_cases.find(
            {"organization_id": BFPO_ORG_ID, "asset_id": case["asset_id"],
             "id": {"$ne": case_id}, "status": {"$in": ["closed", "invoiced", "repaired"]}},
            {"_id": 0, "id": 1, "reference": 1, "title": 1, "closed_at": 1, "resolution_notes": 1},
        ).sort("closed_at", -1).limit(5).to_list(5)
    signature = await db.svc_signatures.find_one(
        {"case_id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0}, sort=[("signed_at", -1)],
    )
    return {**case, "events": events, "photos": photos, "site": site,
            "equipment": equipment, "asset_history": asset_history,
            "signature": signature, "viewer_role": _role(user)}


# ─────────────────────────────────────────────────────────────────
# Engineer — guided workflow
# ─────────────────────────────────────────────────────────────────

async def _op_update(case: dict, user: dict, update_type: str, body: str, extra: dict | None = None):
    await append_event(
        case_id=case["id"], organization_id=BFPO_ORG_ID,
        event_type="operational_update", actor=user, body=body,
        extra={"update_type": update_type, **(extra or {})},
    )


@router.post("/jobs/{case_id}/accept")
async def bfpo_accept(case_id: str, data: dict = Body(default={}), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    await db.svc_cases.update_one(
        {"id": case_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"assigned_engineer_id": user["id"],
                  "assigned_engineer_name": user.get("full_name") or user.get("email"),
                  "updated_at": _now()}},
    )
    if case.get("status") in (NEW, "triaged"):
        try:
            await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                                   target_state=ASSIGNED, actor=user, reason="engineer accepted job")
        except ValueError:
            pass
    await _op_update(case, user, "acknowledged", "Engineer accepted the job")
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/arrive")
async def bfpo_arrive(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    safe = bool(data.get("safe"))
    notes = (data.get("notes") or "").strip()
    updates = {"safety_confirmed": safe, "safety_notes": notes, "arrived_at": _now(), "updated_at": _now()}
    if not safe:
        updates["safety_critical"] = True
    await db.svc_cases.update_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    try:
        await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                               target_state=ON_SITE, actor=user, reason="engineer arrived on site")
    except ValueError:
        pass
    await _op_update(case, user, "arrived",
                     "Engineer arrived on site — " + ("safe to work" if safe else "SAFETY CONCERN raised"),
                     {"safe": safe, "notes": notes})
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/diagnosis")
async def bfpo_diagnosis(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    text = (data.get("diagnosis") or "").strip()
    if not text:
        raise HTTPException(400, "diagnosis required")
    await db.svc_cases.update_one({"id": case_id, "organization_id": BFPO_ORG_ID},
                                  {"$set": {"diagnosis": text, "updated_at": _now()}})
    await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="note",
                       actor=user, body=text, extra={"kind": "diagnosis", "visibility": "internal"})
    return {"ok": True}


@router.post("/jobs/{case_id}/parts")
async def bfpo_parts(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Log a part needed — never requires a Pulse part number.
    Body: {name, description?, part_number?, photo_url?, equipment_id?}"""
    case = await _get_scoped_case(user, case_id, read=False)
    name = (data.get("name") or data.get("description") or "").strip()
    if not name and not data.get("photo_url"):
        raise HTTPException(400, "Describe the part or attach a photo")
    part = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "case_id": case_id,
        "case_reference": case.get("reference"), "engineer_id": user["id"],
        "name": name or "Part (see photo)", "description": (data.get("description") or "").strip(),
        "part_number": (data.get("part_number") or "").strip(),
        "photo_url": data.get("photo_url") or "", "equipment_id": data.get("equipment_id") or "",
        "status": "pending", "created_at": _now(),
    }
    await db.bfpo_parts_requests.insert_one(part)
    await db.svc_cases.update_one({"id": case_id, "organization_id": BFPO_ORG_ID},
                                  {"$set": {"waiting_reason": "Parts required", "updated_at": _now()}})
    try:
        await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                               target_state=PAUSED_PARTS, actor=user, reason="parts required")
    except ValueError:
        pass
    await _op_update(case, user, "parts_required", f"Parts required: {part['name']}",
                     {"part_id": part["id"], "part_name": part["name"]})
    part.pop("_id", None)
    return {"ok": True, "part": part}


@router.post("/jobs/{case_id}/outcome")
async def bfpo_outcome(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Record a non-repair outcome that keeps the job open.
    Body: {outcome: return_visit|unable_access|equipment_unsafe, reason, details?}"""
    case = await _get_scoped_case(user, case_id, read=False)
    outcome = (data.get("outcome") or "").lower()
    reason = (data.get("reason") or "").strip()
    details = (data.get("details") or "").strip()
    label = {"return_visit": "Return visit needed", "unable_access": "Unable to access",
             "equipment_unsafe": "Equipment unsafe"}.get(outcome)
    if not label:
        raise HTTPException(400, "outcome must be return_visit | unable_access | equipment_unsafe")
    updates = {"return_visit": True, "waiting_reason": label,
               "return_reason": reason or label, "updated_at": _now()}
    if outcome == "equipment_unsafe":
        updates["safety_critical"] = True
    await db.svc_cases.update_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    await _op_update(case, user, outcome, f"{label}: {reason or details or '—'}", {"details": details})
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/report-fault")
async def bfpo_report_fault(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Report an ADDITIONAL fault during a visit → creates a linked case.
    Body: {title, description, equipment_id?, safety_critical?, priority?}"""
    parent = await _get_scoped_case(user, case_id, read=False)
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title required")
    equipment_id = data.get("equipment_id") or ""
    warning = None
    if equipment_id:
        dup = await db.svc_cases.find_one({
            "organization_id": BFPO_ORG_ID, "asset_id": equipment_id,
            "status": {"$in": list(OPEN_STATES)},
        }, {"_id": 0, "id": 1, "reference": 1})
        if dup:
            warning = f"That equipment already has an open job ({dup.get('reference')})"
    priority = (data.get("priority") or "p3").lower()
    if priority not in ("p1", "p2", "p3", "p4"):
        priority = "p3"
    sla = await compute_sla_targets(organization_id=BFPO_ORG_ID, priority=priority)
    reference = await next_reference(BFPO_ORG_ID)
    asset_name = ""
    if equipment_id:
        eq = await db.equipment.find_one({"id": equipment_id, "organization_id": BFPO_ORG_ID},
                                         {"_id": 0, "name": 1, "model": 1, "manufacturer": 1})
        if eq:
            asset_name = f"{eq.get('manufacturer') or ''} {eq.get('model') or eq.get('name') or ''}".strip()
    new_case = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "bfpo": True,
        "reference": reference, "status": NEW, "priority": priority, "case_type": "repair",
        "title": title, "description": (data.get("description") or "").strip(),
        "safety_critical": bool(data.get("safety_critical")),
        "territory_id": parent.get("territory_id"), "territory_name": parent.get("territory_name"),
        "country": parent.get("country"), "site_id": parent.get("site_id"),
        "site_name": parent.get("site_name"), "site_timezone": parent.get("site_timezone"),
        "customer_name": parent.get("customer_name"), "asset_id": equipment_id,
        "asset_name": asset_name, "equipment_ids": [equipment_id] if equipment_id else [],
        "linked_from_case_id": case_id, "linked_from_reference": parent.get("reference"),
        "assigned_engineer_id": "", "assigned_engineer_name": "", "scheduled_at": None,
        "sla_response_at": sla["sla_response_at"], "sla_resolve_at": sla["sla_resolve_at"],
        "source": "engineer_report", "logged_by_id": user["id"],
        "logged_by_name": user.get("full_name") or user.get("email"),
        "closed_at": None, "created_at": _now(), "updated_at": _now(),
    }
    await db.svc_cases.insert_one(new_case)
    await append_event(case_id=new_case["id"], organization_id=BFPO_ORG_ID, event_type="intake",
                       actor=user, body=f"Additional fault reported during visit to {parent.get('reference')}",
                       extra={"linked_from": case_id})
    await _op_update(parent, user, "additional_fault",
                     f"Additional fault logged: {title} ({reference})", {"new_case_id": new_case["id"]})
    new_case.pop("_id", None)
    return {"ok": True, "case": new_case, "warning": warning}


@router.post("/jobs/{case_id}/photos")
async def bfpo_add_photo(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    file_url = data.get("file_url")
    if not file_url:
        raise HTTPException(400, "file_url required")
    photo = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "case_id": case_id,
        "case_reference": case.get("reference"), "file_url": file_url,
        "mime_type": data.get("mime_type") or "image/jpeg", "kind": "photo",
        "caption": (data.get("caption") or "").strip(), "taken_at": _now(),
        "taken_by_id": user["id"], "taken_by_name": user.get("full_name") or user.get("email"),
        "created_at": _now(),
    }
    await db.svc_engineer_photos.insert_one(photo)
    await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="photo",
                       actor=user, body=photo["caption"] or "Photo attached", extra={"file_url": file_url})
    photo.pop("_id", None)
    return {"ok": True, "photo": photo}


@router.post("/jobs/{case_id}/signature")
async def bfpo_signature(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Body: {signed_by_name, image_data} OR {unavailable: true, reason}"""
    case = await _get_scoped_case(user, case_id, read=False)
    if data.get("unavailable"):
        reason = (data.get("reason") or "").strip() or "Signature unavailable"
        sig = {"id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "case_id": case_id,
               "case_reference": case.get("reference"), "signed_by_name": "", "image_data": "",
               "unavailable": True, "unavailable_reason": reason, "signed_at": _now(),
               "captured_by_id": user["id"], "created_at": _now()}
    else:
        name = (data.get("signed_by_name") or "").strip()
        image = data.get("image_data") or ""
        if not name or not image:
            raise HTTPException(400, "signed_by_name and image_data required")
        sig = {"id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "case_id": case_id,
               "case_reference": case.get("reference"), "signed_by_name": name,
               "signed_by_role": (data.get("signed_by_role") or "").strip(), "image_data": image,
               "unavailable": False, "signed_at": _now(), "captured_by_id": user["id"],
               "created_at": _now()}
    await db.svc_signatures.insert_one(sig)
    await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="signature",
                       actor=user, body=("Signature unavailable" if sig.get("unavailable")
                                         else f"Signed by {sig['signed_by_name']}"))
    sig.pop("_id", None)
    return {"ok": True, "signature": sig}


@router.post("/jobs/{case_id}/complete")
async def bfpo_complete(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Body: {summary, parts_used?, safe_and_working: bool, photo_urls?[]}"""
    case = await _get_scoped_case(user, case_id, read=False)
    summary = (data.get("summary") or "").strip()
    if not summary:
        raise HTTPException(400, "summary required")
    safe_working = bool(data.get("safe_and_working"))
    updates = {
        "resolution_notes": summary, "parts_used": data.get("parts_used") or "",
        "safe_and_working": safe_working, "return_visit": False,
        "waiting_reason": "", "completed_at": _now(), "updated_at": _now(),
    }
    if safe_working:
        updates["safety_critical"] = False
    await db.svc_cases.update_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    # walk state → on_site → closed
    if case.get("status") in (ASSIGNED, "en_route", "triaged", NEW, PAUSED_PARTS):
        try:
            await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                                   target_state=ON_SITE, actor=user, reason="auto: completing job")
        except ValueError:
            pass
    for tgt in (AWAITING_SIGN_OFF, CLOSED):
        try:
            await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                                   target_state=tgt, actor=user, reason=summary[:200])
        except ValueError:
            continue
    await _op_update(case, user, "job_completed", f"Job completed: {summary[:120]}",
                     {"safe_and_working": safe_working})
    updated = await db.svc_cases.find_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    return {"ok": True, "case": updated,
            "job_sheet_url": f"/api/bfpo/jobs/{case_id}/job-sheet.pdf"}


@router.post("/jobs/{case_id}/update")
async def bfpo_operational_update(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    update_type = (data.get("update_type") or "general").lower()
    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    await _op_update(case, user, update_type, message)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Engineer — sites, equipment, history
# ─────────────────────────────────────────────────────────────────

async def _visible_site_ids(user: dict) -> Optional[list]:
    scope = await _engineer_scope(user)
    if scope["unrestricted"]:
        return None  # all
    ids = set(scope["all_site_ids"])
    if scope["territory_ids"]:
        async for s in db.sites.find(
            {"organization_id": BFPO_ORG_ID, "territory_id": {"$in": scope["territory_ids"]}},
            {"_id": 0, "id": 1},
        ):
            ids.add(s["id"])
    return list(ids)


@router.get("/sites")
async def bfpo_sites(user=Depends(_require_bfpo)):
    q = {"organization_id": BFPO_ORG_ID}
    ids = await _visible_site_ids(user)
    if ids is not None:
        q["id"] = {"$in": ids}
    sites = await db.sites.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    can_sensitive = _role(user) in ("lead", "staff")
    for s in sites:
        if not can_sensitive:
            s.pop("access_instructions", None)
            s.pop("security_notes", None)
    return {"sites": sites, "count": len(sites)}


@router.get("/sites/{site_id}")
async def bfpo_site_detail(site_id: str, user=Depends(_require_bfpo)):
    ids = await _visible_site_ids(user)
    if ids is not None and site_id not in ids:
        raise HTTPException(404, "Site not found")
    site = await db.sites.find_one({"id": site_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not site:
        raise HTTPException(404, "Site not found")
    equipment = await db.equipment.find(
        {"organization_id": BFPO_ORG_ID, "site_id": site_id}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    open_jobs = await db.svc_cases.count_documents(
        {"organization_id": BFPO_ORG_ID, "site_id": site_id, "status": {"$in": list(OPEN_STATES)}})
    return {"site": site, "equipment": equipment, "open_jobs": open_jobs,
            "sensitive_visible": _role(user) in ("lead", "staff")}


@router.get("/equipment")
async def bfpo_equipment(search: str = Query(""), user=Depends(_require_bfpo)):
    q = {"organization_id": BFPO_ORG_ID}
    ids = await _visible_site_ids(user)
    if ids is not None:
        q["site_id"] = {"$in": ids}
    if search:
        from utils.security_plus import safe_regex
        q["$or"] = [{"serial_number": safe_regex(search)}, {"model": safe_regex(search)},
                    {"name": safe_regex(search)}, {"manufacturer": safe_regex(search)}]
    rows = await db.equipment.find(q, {"_id": 0}).sort("name", 1).limit(300).to_list(300)
    return {"equipment": rows, "count": len(rows)}


@router.get("/equipment/{equipment_id}")
async def bfpo_equipment_detail(equipment_id: str, user=Depends(_require_bfpo)):
    eq = await db.equipment.find_one({"id": equipment_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    ids = await _visible_site_ids(user)
    if ids is not None and eq.get("site_id") not in ids:
        raise HTTPException(404, "Equipment not found")
    history = await db.svc_cases.find(
        {"organization_id": BFPO_ORG_ID, "asset_id": equipment_id}, {"_id": 0,
         "id": 1, "reference": 1, "title": 1, "status": 1, "closed_at": 1, "created_at": 1,
         "resolution_notes": 1},
    ).sort("created_at", -1).limit(30).to_list(30)
    return {"equipment": eq, "history": history}


@router.get("/history")
async def bfpo_history(user=Depends(_require_bfpo)):
    q = await _scoped_case_query(user)
    q["status"] = {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]}
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort("closed_at", -1).limit(200).to_list(200)
    return {"jobs": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# MOD staff — global oversight
# ─────────────────────────────────────────────────────────────────

def _site_health(stats: dict) -> str:
    if stats.get("unsafe") or stats.get("overdue_urgent"):
        return "critical"
    if stats.get("machines_down", 0) >= 2 or stats.get("waiting_parts") or stats.get("access_problem") or stats.get("overdue"):
        return "attention"
    return "normal"


@router.get("/staff/dashboard")
async def staff_dashboard(user=Depends(_require_staff)):
    base = {"organization_id": BFPO_ORG_ID}
    open_q = {**base, "status": {"$in": list(OPEN_STATES)}}
    kpis = {
        "open": await db.svc_cases.count_documents(open_q),
        "urgent": await db.svc_cases.count_documents(
            {**open_q, "$or": [{"priority": "p1"}, {"safety_critical": True}]}),
        "waiting_parts": await db.svc_cases.count_documents({**base, "status": PAUSED_PARTS}),
        "overdue": await db.svc_cases.count_documents(
            {**open_q, "sla_resolve_at": {"$lt": _now(), "$ne": None}}),
    }
    # sites requiring attention
    site_health = await _compute_site_health()
    kpis["sites_attention"] = sum(1 for s in site_health if s["health"] != "normal")
    urgent_list = await db.svc_cases.find(
        {**open_q, "$or": [{"priority": "p1"}, {"safety_critical": True}]}, _JOB_PROJECTION,
    ).sort("sla_resolve_at", 1).limit(20).to_list(20)
    return {"kpis": kpis, "urgent_jobs": urgent_list,
            "attention_sites": [s for s in site_health if s["health"] != "normal"]}


async def _compute_site_health() -> list:
    sites = await db.sites.find({"organization_id": BFPO_ORG_ID}, {"_id": 0}).to_list(1000)
    now = _now()
    out = []
    for s in sites:
        open_cases = await db.svc_cases.find(
            {"organization_id": BFPO_ORG_ID, "site_id": s["id"], "status": {"$in": list(OPEN_STATES)}},
            {"_id": 0, "priority": 1, "safety_critical": 1, "sla_resolve_at": 1, "status": 1, "waiting_reason": 1},
        ).to_list(500)
        stats = {"machines_down": len(open_cases),
                 "unsafe": any(c.get("safety_critical") for c in open_cases),
                 "waiting_parts": any(c.get("status") == PAUSED_PARTS for c in open_cases),
                 "access_problem": any((c.get("waiting_reason") or "").lower().startswith("unable") for c in open_cases),
                 "overdue": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now for c in open_cases),
                 "overdue_urgent": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now
                                       and (c.get("priority") == "p1" or c.get("safety_critical")) for c in open_cases)}
        out.append({"site_id": s["id"], "site_name": s.get("name"),
                    "country": s.get("country"), "territory_id": s.get("territory_id"),
                    "territory_name": s.get("territory_name"),
                    "open_jobs": len(open_cases), "health": _site_health(stats)})
    return out


@router.get("/staff/sites")
async def staff_sites(user=Depends(_require_staff)):
    health = await _compute_site_health()
    grouped: dict = {}
    for s in health:
        country = s.get("country") or "Other"
        terr = s.get("territory_name") or "Unassigned"
        grouped.setdefault(country, {}).setdefault(terr, []).append(s)
    tree = [{"country": c,
             "territories": [{"territory_name": t, "sites": sites,
                              "health": ("critical" if any(x["health"] == "critical" for x in sites)
                                         else "attention" if any(x["health"] == "attention" for x in sites)
                                         else "normal")}
                             for t, sites in terrs.items()]}
            for c, terrs in sorted(grouped.items())]
    return {"tree": tree}


@router.get("/staff/jobs")
async def staff_jobs(
    territory: str = Query(""), site: str = Query(""), engineer: str = Query(""),
    status: str = Query(""), priority: str = Query(""), safety: str = Query(""),
    overdue: str = Query(""), user=Depends(_require_staff),
):
    q = {"organization_id": BFPO_ORG_ID}
    if territory:
        q["territory_id"] = territory
    if site:
        q["site_id"] = site
    if engineer:
        q["assigned_engineer_id"] = engineer
    if status == "open":
        q["status"] = {"$in": list(OPEN_STATES)}
    elif status:
        q["status"] = status
    if priority:
        q["priority"] = priority
    if safety == "true":
        q["safety_critical"] = True
    if overdue == "true":
        q["sla_resolve_at"] = {"$lt": _now(), "$ne": None}
        q.setdefault("status", {"$in": list(OPEN_STATES)})
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort([("priority", 1), ("sla_resolve_at", 1)]).limit(300).to_list(300)
    return {"jobs": rows, "count": len(rows)}


@router.get("/staff/jobs/{case_id}")
async def staff_job_detail(case_id: str, user=Depends(_require_staff)):
    return await bfpo_job_detail(case_id, user)


@router.get("/staff/engineers")
async def staff_engineers(user=Depends(_require_staff)):
    rows = await db.users.find(
        {"organization_id": BFPO_ORG_ID, "bfpo_role": {"$in": ["engineer", "lead"]}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "bfpo_role": 1, "bfpo_territory_ids": 1},
    ).to_list(200)
    return {"engineers": rows}


@router.post("/staff/jobs/{case_id}/allocate")
async def staff_allocate(case_id: str, data: dict = Body(...), user=Depends(_require_staff)):
    case = await db.svc_cases.find_one({"id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Job not found")
    eng_id = data.get("engineer_id")
    eng = await db.users.find_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eng:
        raise HTTPException(404, "Engineer not found")
    handover = (data.get("handover") or "").strip()
    previous = case.get("assigned_engineer_name")
    await db.svc_cases.update_one(
        {"id": case_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"assigned_engineer_id": eng_id,
                  "assigned_engineer_name": eng.get("full_name") or eng.get("email"),
                  "updated_at": _now()}},
    )
    if case.get("status") in (NEW, "triaged"):
        try:
            await state_transition(case_id=case_id, organization_id=BFPO_ORG_ID,
                                   target_state=ASSIGNED, actor=user, reason="allocated by MOD staff")
        except ValueError:
            pass
    body = f"Allocated to {eng.get('full_name') or eng.get('email')}"
    if previous:
        body = f"Reallocated from {previous} to {eng.get('full_name') or eng.get('email')}"
    await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="allocation",
                       actor=user, body=body, extra={"engineer_id": eng_id, "handover": handover})
    if handover:
        await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="note",
                           actor=user, body=handover, extra={"kind": "handover"})
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# MOD staff — temporary visiting-engineer access
# ─────────────────────────────────────────────────────────────────

@router.get("/staff/visiting-access")
async def list_visiting_access(user=Depends(_require_staff)):
    rows = await db.bfpo_visiting_access.find({"organization_id": BFPO_ORG_ID}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"grants": rows}


@router.post("/staff/visiting-access")
async def grant_visiting_access(data: dict = Body(...), user=Depends(_require_staff)):
    eng = await db.users.find_one({"id": data.get("engineer_id"), "organization_id": BFPO_ORG_ID}, {"_id": 0})
    site = await db.sites.find_one({"id": data.get("site_id"), "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eng or not site:
        raise HTTPException(404, "Engineer or site not found")
    grant = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID,
        "engineer_id": eng["id"], "engineer_name": eng.get("full_name") or eng.get("email"),
        "site_id": site["id"], "site_name": site.get("name"),
        "territory_id": site.get("territory_id"), "territory_name": site.get("territory_name"),
        "from_date": data.get("from_date") or _today(), "to_date": data.get("to_date") or _today(),
        "granted_by": user.get("full_name") or user.get("email"), "created_at": _now(),
    }
    await db.bfpo_visiting_access.insert_one(grant)
    grant.pop("_id", None)
    return {"ok": True, "grant": grant}


@router.delete("/staff/visiting-access/{grant_id}")
async def revoke_visiting_access(grant_id: str, user=Depends(_require_staff)):
    res = await db.bfpo_visiting_access.delete_one({"id": grant_id, "organization_id": BFPO_ORG_ID})
    if not res.deleted_count:
        raise HTTPException(404, "Grant not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Branded job sheet PDF
# ─────────────────────────────────────────────────────────────────

@router.get("/jobs/{case_id}/job-sheet.pdf")
async def bfpo_job_sheet(case_id: str, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    events = await db.svc_case_events.find(
        {"case_id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0},
    ).sort("at", 1).to_list(200)
    signature = await db.svc_signatures.find_one(
        {"case_id": case_id, "organization_id": BFPO_ORG_ID}, {"_id": 0}, sort=[("signed_at", -1)])
    pdf = _build_job_sheet_pdf(case, events, signature)
    fname = f"Job Sheet - {case.get('reference')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


def _build_job_sheet_pdf(case: dict, events: list, signature: dict | None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    cyan = colors.HexColor("#0891b2")
    ink = colors.HexColor("#0f172a")
    y = h - 22 * mm
    c.setFillColor(ink)
    c.rect(0, h - 30 * mm, w, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(18 * mm, h - 18 * mm, "PULSE FITNESS")
    c.setFillColor(cyan)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, h - 24 * mm, "MOD / BFPO Service — Electronic Job Sheet")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - 18 * mm, h - 20 * mm, case.get("reference") or "")
    y = h - 40 * mm

    def line(label, value):
        nonlocal y
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(18 * mm, y, label.upper())
        c.setFillColor(ink)
        c.setFont("Helvetica", 10)
        c.drawString(18 * mm, y - 5 * mm, str(value or "—")[:90])
        y -= 12 * mm

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(18 * mm, y, case.get("title") or "Service Job")
    y -= 9 * mm
    line("Site", f"{case.get('site_name') or ''} · {case.get('territory_name') or ''} · {case.get('country') or ''}")
    line("Equipment", case.get("asset_name"))
    line("Reported fault", case.get("description"))
    line("Priority / Status", f"{(case.get('priority') or '').upper()} · {case.get('status')}")
    line("Assigned engineer", case.get("assigned_engineer_name"))
    line("Diagnosis", case.get("diagnosis"))
    line("Work carried out", case.get("resolution_notes"))
    line("Parts used", case.get("parts_used"))
    line("Safe & working confirmed", "Yes" if case.get("safe_and_working") else "No")

    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(18 * mm, y, w - 18 * mm, y)
    y -= 10 * mm
    c.setFillColor(cyan)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18 * mm, y, "SIGN-OFF")
    y -= 8 * mm
    c.setFillColor(ink)
    c.setFont("Helvetica", 10)
    if signature and not signature.get("unavailable"):
        c.drawString(18 * mm, y, f"Signed by: {signature.get('signed_by_name')}  ({signature.get('signed_by_role') or 'customer'})")
        img = signature.get("image_data") or ""
        if img.startswith("data:image"):
            try:
                import base64
                from reportlab.lib.utils import ImageReader
                raw = base64.b64decode(img.split(",", 1)[1])
                c.drawImage(ImageReader(io.BytesIO(raw)), 18 * mm, y - 30 * mm, width=60 * mm,
                            height=25 * mm, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
    elif signature and signature.get("unavailable"):
        c.drawString(18 * mm, y, f"Signature unavailable — {signature.get('unavailable_reason')}")
    else:
        c.drawString(18 * mm, y, "No signature captured")

    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 7)
    c.drawString(18 * mm, 12 * mm, f"Generated {_now()[:16].replace('T', ' ')} · Pulse Fitness Ltd · MOD/BFPO Service")
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = ["router"]
