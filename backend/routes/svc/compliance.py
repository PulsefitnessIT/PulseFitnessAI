"""
GymAxis Service Operations — Compliance Pack (Iter 220de).

Three field-engineering compliance gates shipped together because
they share patterns and a single engineer-side surface
(``ComplianceCard`` on ``JobAtAGlance``):

  1. **Permit to Work (PTW)** — formal authorization for hazardous
     work (hot work, electrical isolation, height, confined space).
     Engineer requests → admin issues → engineer completes.
  2. **COSHH register** — org-level chemicals register (cleaning
     agents, lubricants, refrigerants). Engineer ticks usage per
     visit; surfaces on the service report.
  3. **LOTO procedure** — lockout/tagout checklist per case (energy
     sources verified, locks applied). Engineer signs off; locked
     into the case timeline.

Each section follows the safety.py pattern:
  * org-level template / register endpoint (lazy-seeds a default)
  * engineer per-case endpoint to request/complete
  * append_event hook so completions show on the timeline.

Compliance value:
  * Mandatory for MOD / NHS / national-chain contracts.
  * Insurance discount evidence pack.
  * Required by HSE for hot work + confined-space + electrical isolation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import append_event

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _require_admin(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    if (user.get("role") or "").lower() in ("owner", "manager"):
        return
    raise HTTPException(403, "Owner or Manager role required")


# ═════════════════════════════════════════════════════════════════
# 1 · Permit to Work (PTW)
# ═════════════════════════════════════════════════════════════════
#
# Hazard categories follow HSE convention:
#   hot_work, electrical, height, confined_space, asbestos, lifting,
#   excavation, other.
# Templates are org-level (admin defines once); requests are per-case.
PTW_CATEGORIES = {
    "hot_work", "electrical", "height", "confined_space",
    "asbestos", "lifting", "excavation", "other",
}

PTW_STATUSES = {"requested", "issued", "completed", "expired", "cancelled"}


# Default templates lazy-seeded on first read. Operators can edit.
DEFAULT_PTW_TEMPLATES = [
    {
        "name": "Hot Work Permit",
        "hazard_category": "hot_work",
        "validity_hours": 8,
        "hazards": [
            "Open flame / spark hazard",
            "Combustible materials within 10 m",
            "Fire extinguisher required on standby",
        ],
        "controls": [
            "Clear 10m of combustibles",
            "Fire watch for 30 min post-work",
            "Fire extinguisher within reach",
        ],
    },
    {
        "name": "Electrical Isolation Permit",
        "hazard_category": "electrical",
        "validity_hours": 4,
        "hazards": [
            "Live conductors present",
            "Stored energy in capacitors",
        ],
        "controls": [
            "Verified zero energy with test meter",
            "Lockout/Tagout applied",
            "PPE: insulated gloves, eye protection",
        ],
    },
    {
        "name": "Working at Height Permit",
        "hazard_category": "height",
        "validity_hours": 8,
        "hazards": [
            "Fall hazard >2 m",
            "Falling-object hazard below",
        ],
        "controls": [
            "Edge protection or harness in use",
            "Exclusion zone established below",
            "Equipment inspected pre-use",
        ],
    },
]


async def _seed_ptw_templates(org_id: str) -> None:
    if await db.svc_ptw_templates.count_documents({"organization_id": org_id}) > 0:
        return
    now = _now()
    docs = [
        {
            **t,
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        for t in DEFAULT_PTW_TEMPLATES
    ]
    if docs:
        await db.svc_ptw_templates.insert_many(docs)


# ── Templates (admin) ──


class PtwTemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    hazard_category: str
    validity_hours: int = Field(default=8, ge=1, le=72)
    hazards: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    active: bool = True


@router.get("/svc/compliance/ptw/templates")
async def list_ptw_templates(user=Depends(get_current_user)):
    of = _of(user)
    await _seed_ptw_templates(of["organization_id"])
    rows = (
        await db.svc_ptw_templates
        .find(of, {"_id": 0})
        .sort("hazard_category", 1)
        .to_list(200)
    )
    return {"items": rows, "categories": sorted(PTW_CATEGORIES)}


@router.post("/svc/compliance/ptw/templates")
async def create_ptw_template(body: PtwTemplateIn, user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    if body.hazard_category not in PTW_CATEGORIES:
        raise HTTPException(422, f"hazard_category must be one of {sorted(PTW_CATEGORIES)}")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "name": body.name.strip(),
        "hazard_category": body.hazard_category,
        "validity_hours": body.validity_hours,
        "hazards": [h.strip() for h in body.hazards if h.strip()],
        "controls": [c.strip() for c in body.controls if c.strip()],
        "active": body.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_ptw_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/svc/compliance/ptw/templates/{tpl_id}")
async def delete_ptw_template(tpl_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    r = await db.svc_ptw_templates.delete_one({"id": tpl_id, **of})
    if r.deleted_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


# ── Requests (engineer + admin) ──


class PtwRequestIn(BaseModel):
    template_id: str
    hazards_noted: list[str] = Field(default_factory=list)
    notes: Optional[str] = ""


@router.post("/svc/engineer/jobs/{case_id}/ptw-requests")
async def create_ptw_request(
    case_id: str, body: PtwRequestIn, user=Depends(get_current_user),
):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1, "reference": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    tpl = await db.svc_ptw_templates.find_one(
        {"id": body.template_id, **of, "active": True}, {"_id": 0},
    )
    if not tpl:
        raise HTTPException(404, "Template not found or inactive")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "template_id": tpl["id"],
        "template_name": tpl["name"],
        "hazard_category": tpl["hazard_category"],
        "validity_hours": tpl.get("validity_hours", 8),
        "hazards": tpl.get("hazards", []),
        "controls": tpl.get("controls", []),
        "hazards_noted": [h.strip() for h in body.hazards_noted if h.strip()],
        "notes": (body.notes or "").strip(),
        "status": "requested",
        "requested_by_id": user["id"],
        "requested_by_name": user.get("full_name") or user.get("email") or "",
        "requested_at": _now(),
        "issued_by_id": None,
        "issued_by_name": None,
        "issued_at": None,
        "valid_from": None,
        "valid_until": None,
        "completed_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_ptw_requests.insert_one(doc)
    doc.pop("_id", None)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"PTW requested: {tpl['name']}",
        extra={"kind": "ptw_request", "request_id": doc["id"]},
    )
    return doc


@router.get("/svc/engineer/jobs/{case_id}/ptw-requests")
async def list_ptw_requests_for_case(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    rows = (
        await db.svc_ptw_requests
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("requested_at", -1)
        .to_list(50)
    )
    return {"items": rows}


@router.post("/svc/admin/ptw-requests/{request_id}/issue")
async def issue_ptw_request(request_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    req = await db.svc_ptw_requests.find_one({"id": request_id, **of}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "requested":
        raise HTTPException(409, f"Request is {req['status']}")
    now = datetime.now(timezone.utc)
    valid_from = now.isoformat()
    from datetime import timedelta
    valid_until = (now + timedelta(hours=int(req.get("validity_hours") or 8))).isoformat()
    await db.svc_ptw_requests.update_one(
        {"id": request_id, **of},
        {"$set": {
            "status": "issued",
            "issued_by_id": user["id"],
            "issued_by_name": user.get("full_name") or user.get("email") or "",
            "issued_at": valid_from,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "updated_at": valid_from,
        }},
    )
    await append_event(
        case_id=req["case_id"], organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"PTW issued: {req['template_name']} valid until {valid_until}",
        extra={"kind": "ptw_issued", "request_id": request_id},
    )
    return await db.svc_ptw_requests.find_one({"id": request_id, **of}, {"_id": 0})


@router.post("/svc/engineer/ptw-requests/{request_id}/complete")
async def complete_ptw_request(request_id: str, user=Depends(get_current_user)):
    of = _of(user)
    req = await db.svc_ptw_requests.find_one({"id": request_id, **of}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "issued":
        raise HTTPException(409, f"Cannot complete a {req['status']} permit")
    now = _now()
    await db.svc_ptw_requests.update_one(
        {"id": request_id, **of},
        {"$set": {
            "status": "completed",
            "completed_at": now,
            "completed_by_id": user["id"],
            "updated_at": now,
        }},
    )
    await append_event(
        case_id=req["case_id"], organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"PTW completed: {req['template_name']}",
        extra={"kind": "ptw_completed", "request_id": request_id},
    )
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════
# 2 · COSHH register
# ═════════════════════════════════════════════════════════════════

COSHH_HAZARD_CLASSES = {
    "flammable", "corrosive", "irritant", "toxic", "harmful",
    "environmental", "oxidising", "other",
}

DEFAULT_COSHH_ENTRIES = [
    {"name": "WD-40 Multi-Use", "supplier": "WD-40 Co.",
     "hazard_class": "flammable",
     "controls": "Ventilate; avoid eye contact; no smoking."},
    {"name": "Isopropyl Alcohol 70%", "supplier": "Generic",
     "hazard_class": "flammable",
     "controls": "Ventilate; keep away from ignition sources."},
    {"name": "Treadmill belt lubricant (silicone)", "supplier": "Pulse Fitness",
     "hazard_class": "irritant",
     "controls": "Wear gloves; avoid eye contact."},
]


async def _seed_coshh_register(org_id: str) -> None:
    if await db.svc_coshh_entries.count_documents({"organization_id": org_id}) > 0:
        return
    now = _now()
    docs = [
        {
            **e,
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "sds_url": None,
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        for e in DEFAULT_COSHH_ENTRIES
    ]
    if docs:
        await db.svc_coshh_entries.insert_many(docs)


class CoshhIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    supplier: Optional[str] = ""
    hazard_class: str
    controls: Optional[str] = ""
    sds_url: Optional[str] = None
    active: bool = True


@router.get("/svc/compliance/coshh")
async def list_coshh_entries(user=Depends(get_current_user)):
    of = _of(user)
    await _seed_coshh_register(of["organization_id"])
    rows = await db.svc_coshh_entries.find(of, {"_id": 0}).sort("name", 1).to_list(500)
    return {"items": rows, "hazard_classes": sorted(COSHH_HAZARD_CLASSES)}


@router.post("/svc/compliance/coshh")
async def create_coshh_entry(body: CoshhIn, user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    if body.hazard_class not in COSHH_HAZARD_CLASSES:
        raise HTTPException(422, f"hazard_class must be one of {sorted(COSHH_HAZARD_CLASSES)}")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "name": body.name.strip(),
        "supplier": (body.supplier or "").strip(),
        "hazard_class": body.hazard_class,
        "controls": (body.controls or "").strip(),
        "sds_url": (body.sds_url or "").strip() or None,
        "active": body.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_coshh_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/svc/compliance/coshh/{entry_id}")
async def delete_coshh_entry(entry_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    of = _of(user)
    r = await db.svc_coshh_entries.update_one(
        {"id": entry_id, **of},
        {"$set": {"active": False, "updated_at": _now()}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Entry not found")
    return {"ok": True}


@router.get("/svc/engineer/coshh/active")
async def list_active_coshh(user=Depends(get_current_user)):
    of = _of(user)
    await _seed_coshh_register(of["organization_id"])
    rows = (
        await db.svc_coshh_entries
        .find({**of, "active": True}, {"_id": 0})
        .sort("name", 1)
        .to_list(200)
    )
    return {"items": rows}


class CoshhUsageIn(BaseModel):
    entry_ids: list[str] = Field(..., max_length=20)
    notes: Optional[str] = ""


@router.post("/svc/engineer/jobs/{case_id}/coshh-used")
async def record_coshh_usage(
    case_id: str, body: CoshhUsageIn, user=Depends(get_current_user),
):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    if not body.entry_ids:
        raise HTTPException(400, "Pick at least one COSHH entry")
    entries = await db.svc_coshh_entries.find(
        {"id": {"$in": body.entry_ids}, **of, "active": True}, {"_id": 0},
    ).to_list(20)
    if not entries:
        raise HTTPException(404, "No matching active COSHH entries")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "entries": [
            {"id": e["id"], "name": e["name"], "hazard_class": e["hazard_class"]}
            for e in entries
        ],
        "notes": (body.notes or "").strip(),
        "recorded_at": _now(),
    }
    await db.svc_coshh_usage.insert_one(doc)
    doc.pop("_id", None)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"COSHH usage recorded: {', '.join(e['name'] for e in doc['entries'])}",
        extra={"kind": "coshh_usage", "usage_id": doc["id"]},
    )
    return doc


# ═════════════════════════════════════════════════════════════════
# 3 · LOTO (Lockout / Tagout)
# ═════════════════════════════════════════════════════════════════
#
# A LOTO sign-off is per-case (or per-machine on a case). Each
# checklist captures: energy sources isolated, locks applied, zero-
# energy verified, signature. We embed a generic template in the
# GET response so the engineer has steps to tick without us
# maintaining a separate templates collection.

DEFAULT_LOTO_STEPS = [
    {"id": "notify",    "label": "Notify affected staff",                     "required": True},
    {"id": "shutdown",  "label": "Normal shutdown procedure followed",        "required": True},
    {"id": "isolate",   "label": "Energy sources isolated (electrical/pneumatic/hydraulic)", "required": True},
    {"id": "lockout",   "label": "Lockout device applied",                    "required": True},
    {"id": "tagout",    "label": "Tagout label attached with engineer name",  "required": True},
    {"id": "dissipate", "label": "Stored energy released (capacitors, springs)", "required": False},
    {"id": "verify",    "label": "Zero-energy verified with appropriate instrument", "required": True},
]


@router.get("/svc/engineer/jobs/{case_id}/loto")
async def get_loto_for_case(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    existing = (
        await db.svc_loto_checklists
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("completed_at", -1)
        .to_list(10)
    )
    return {
        "case_id": case_id,
        "steps": DEFAULT_LOTO_STEPS,
        "completed": existing,
    }


class LotoIn(BaseModel):
    ticked_step_ids: list[str] = Field(..., min_length=1)
    energy_sources: list[str] = Field(default_factory=list)
    machine_id: Optional[str] = None
    signature_url: Optional[str] = None
    notes: Optional[str] = ""


@router.post("/svc/engineer/jobs/{case_id}/loto")
async def submit_loto_checklist(
    case_id: str, body: LotoIn, user=Depends(get_current_user),
):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    required = {s["id"] for s in DEFAULT_LOTO_STEPS if s["required"]}
    missing = required - set(body.ticked_step_ids)
    if missing:
        raise HTTPException(400, f"Missing required steps: {sorted(missing)}")
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "machine_id": body.machine_id or None,
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "ticked_step_ids": list(body.ticked_step_ids),
        "energy_sources": [s.strip() for s in body.energy_sources if s.strip()],
        "signature_url": (body.signature_url or "").strip() or None,
        "notes": (body.notes or "").strip(),
        "completed_at": _now(),
    }
    await db.svc_loto_checklists.insert_one(doc)
    doc.pop("_id", None)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"LOTO checklist completed ({len(doc['ticked_step_ids'])} steps)",
        extra={"kind": "loto_checklist", "loto_id": doc["id"]},
    )
    return doc


# ═════════════════════════════════════════════════════════════════
# 4 · Engineer compliance summary per case
# ═════════════════════════════════════════════════════════════════
#
# Powers the ``ComplianceCard`` on the JobAtAGlance header. Returns
# the open compliance items per job so the engineer can see at a
# glance what's still needed: PTW required-not-issued, LOTO not yet
# completed, COSHH not yet recorded.


@router.get("/svc/engineer/jobs/{case_id}/compliance-summary")
async def compliance_summary(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "ptw_required": 1, "hazard_category": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    ptw_rows = await db.svc_ptw_requests.find(
        {"case_id": case_id, **of}, {"_id": 0},
    ).sort("requested_at", -1).to_list(20)
    loto_count = await db.svc_loto_checklists.count_documents(
        {"case_id": case_id, **of},
    )
    coshh_count = await db.svc_coshh_usage.count_documents(
        {"case_id": case_id, **of},
    )
    active_ptw = next(
        (p for p in ptw_rows if p["status"] in {"requested", "issued"}),
        None,
    )
    return {
        "case_id": case_id,
        "ptw": {
            "requests": ptw_rows,
            "active": active_ptw,
            "needs_action": bool(case.get("ptw_required")) and not any(
                p["status"] in {"issued", "completed"} for p in ptw_rows
            ),
        },
        "loto": {
            "completed_count": loto_count,
            "needs_action": loto_count == 0,
        },
        "coshh": {
            "recorded_count": coshh_count,
        },
    }


__all__ = ["router"]
