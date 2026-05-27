"""Iter 220s — Unified Accident, Near-Miss, Hazard, RIDDOR module.

One source of truth for all H&S incidents across every tenant profile
(gym, leisure centre, council, university, MOD, hotel, school, studio,
service engineer). Built on top of the existing GymAxis primitives
(``users``, ``organizations``, ``equipment``, ``svc_engineers``,
``issues``) — never duplicates them.

Phase 1 surface
---------------

* CRUD for incidents (typed by ``kind`` — ``accident`` /
  ``near_miss`` / ``hazard`` / ``dangerous_occurrence``)
* Severity classification (``minor`` … ``fatal``) with auto-escalation
  on Serious / Major / Fatal
* RIDDOR guided assessment via ``utils.riddor`` (10-question wizard)
* Witness records (embedded)
* Investigation sub-record (single per incident, manager-assigned)
* Corrective actions (own collection ``incident_corrective_actions``
  for cross-incident reporting later)
* Immutable audit trail (``incident_audit_log``)
* Mobile-first quick-log endpoint (``POST /incidents/quick``)
* Integrations: ``asset_id``, ``service_case_id`` / ``related_issue_id``
  link back to existing collections so the incident appears on the
  asset, fault, and engineer profile pages.

Storage
-------

``db.incidents`` — main row, keyed by ``id`` + scoped to
``organization_id``. Reference (``IR-{yr}-{seq}``) generated on write.

``db.incident_corrective_actions`` — one row per action, links to
``incident_id``. Queried independently for the actions kanban (Phase 3).

``db.incident_audit_log`` — append-only event log. Every state
mutation (create, status change, severity change, RIDDOR assessment,
investigation start, action close, manager sign-off) gets a row. Never
updated, never deleted.

``db.incident_witnesses`` — currently embedded on the incident
document for simplicity (Phase 1). Will graduate to its own collection
when the witness-statement signing flow lands in Phase 2.

Roles + RBAC
------------

* **Staff** — can log incidents (any kind), can read incidents they
  created.
* **Manager / owner / admin / hse_lead** — full read across their
  org, can update / assign / sign off.
* **Engineer** (svc) — can log field incidents, read their own.
* **Master admin** — full read across all orgs (existing pattern).

Permissions are checked against ``user["role"]`` and
``user["is_master_admin"]``; both are already populated by the
existing ``get_current_user`` dependency.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.riddor import WIZARD_QUESTIONS, assess as riddor_assess

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Incidents"])


# ── Picklists ─────────────────────────────────────────────────────

INCIDENT_KINDS = ("accident", "near_miss", "hazard", "dangerous_occurrence")
SEVERITIES = ("minor", "moderate", "serious", "major", "fatal")
STATUSES = (
    "draft", "reported", "investigating", "actions_pending",
    "closed", "escalated",
)
INJURED_ROLES = (
    "staff", "member", "visitor", "contractor", "engineer", "other",
)
CATEGORIES = (
    "slip_trip_fall",
    "equipment_failure",
    "trapping_crush",
    "electrical",
    "fire",
    "manual_handling",
    "chemical_exposure",
    "sharp_injury",
    "collision",
    "falling_object",
    "member_misuse",
    "contractor_incident",
    "engineer_incident",
    "poolside",
    "hazardous_substance",
    "violence_aggression",
    "safeguarding",
    "other",
)
ROOT_CAUSE_OPTIONS = (
    "equipment_failure",
    "maintenance_issue",
    "user_error",
    "training_gap",
    "environmental",
    "process_failure",
    "contractor_issue",
    "communication",
    "inadequate_supervision",
    "other",
)
SEVERITY_AUTO_ESCALATE = {"serious", "major", "fatal"}


# ── Helpers ───────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


async def _next_reference(org_id: str) -> str:
    """``IR-YYYY-NNNNN`` — incident reference scoped per org so a tenant
    can read their own counter without leaking the global volume."""
    year = _now().year
    seq_key = f"incidents:{org_id}:{year}"
    row = await db.counters.find_one_and_update(
        {"_id": seq_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,  # default false; many drivers ignore — fallback below
    )
    seq = (row or {}).get("seq") or 1
    return f"IR-{year}-{str(seq).zfill(5)}"


def _user_can_view_all(user: dict) -> bool:
    if user.get("is_master_admin"):
        return True
    role = (user.get("role") or "").lower()
    return role in {"owner", "admin", "manager", "hse_lead"}


def _user_can_close(user: dict) -> bool:
    if user.get("is_master_admin"):
        return True
    role = (user.get("role") or "").lower()
    return role in {"owner", "admin", "manager", "hse_lead"}


async def _require_org(user: dict) -> str:
    org_id = user.get("organization_id")
    if not org_id and not user.get("is_master_admin"):
        raise HTTPException(403, "No organization context")
    return org_id or ""


async def _scope_filter(user: dict, base: Optional[dict] = None) -> dict:
    """Return a Mongo filter that limits reads to incidents the user
    is allowed to see. Master admin → no filter. Org admin/manager/
    HSE lead → org-wide. Staff/engineer → own submissions only."""
    f: dict = dict(base or {})
    if user.get("is_master_admin"):
        return f
    org_id = user.get("organization_id")
    if org_id:
        f["organization_id"] = org_id
    if not _user_can_view_all(user):
        f["created_by_user_id"] = user.get("id")
    return f


async def _audit(*, incident_id: str, user: dict, action: str,
                 before: Optional[dict] = None, after: Optional[dict] = None,
                 notes: Optional[str] = None, request: Optional[Request] = None) -> None:
    """Append-only audit row. Never raises."""
    try:
        await db.incident_audit_log.insert_one({
            "id": _new_id(),
            "incident_id": incident_id,
            "at": _now(),
            "actor_user_id": user.get("id"),
            "actor_name": user.get("full_name") or user.get("email"),
            "actor_role": user.get("role"),
            "action": action,
            "before": before,
            "after": after,
            "notes": notes,
            "ip": (request.client.host if request and request.client else None),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incidents] audit write failed action=%s err=%s", action, exc)


async def _notify_escalation(incident: dict) -> None:
    """Email the org's H&S contact when an incident is Serious+ or
    potential/confirmed RIDDOR. Best-effort — never blocks the request."""
    try:
        org = await db.organizations.find_one(
            {"id": incident["organization_id"]},
            {"_id": 0, "name": 1, "hs_officer_email": 1, "admin_email": 1,
             "primary_contact_email": 1, "owner_email": 1},
        ) or {}
        recipient = (
            org.get("hs_officer_email")
            or org.get("primary_contact_email")
            or org.get("admin_email")
            or org.get("owner_email")
            or os.environ.get("INCIDENT_ESCALATION_EMAIL")
        )
        if not recipient:
            return
        from utils.email import send_email
        sev = incident.get("severity") or "moderate"
        riddor = (incident.get("riddor") or {}).get("status") or "not_assessed"
        kind = (incident.get("kind") or "incident").replace("_", " ")
        subject = (
            f"[H&S {sev.upper()}{' · RIDDOR' if riddor in {'potential','confirmed'} else ''}] "
            f"{incident.get('reference')} — {org.get('name', 'your site')}"
        )
        html = (
            '<div style="font-family:Arial,sans-serif;color:#0F172A;line-height:1.55;max-width:560px;margin:0 auto;">'
            f'<h2 style="margin:0 0 12px;font-size:22px;font-weight:800;">New {kind} reported.</h2>'
            f"<p><strong>Reference:</strong> {incident.get('reference')}<br/>"
            f"<strong>Site:</strong> {org.get('name', 'your site')}<br/>"
            f"<strong>Severity:</strong> {sev.title()}<br/>"
            f"<strong>RIDDOR:</strong> {riddor.replace('_', ' ').title()}</p>"
            f"<p style=\"white-space:pre-wrap;\">{(incident.get('description') or '')[:1200]}</p>"
            '<p style="margin-top:18px;font-size:13px;color:#475569;">'
            "Open the incident in GymAxis to investigate. "
            "Escalation rules fired automatically based on severity / RIDDOR status."
            "</p></div>"
        )
        await send_email(to=recipient, subject=subject, html=html)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[incidents] escalation email failed: %s", exc)


def _strip_internal(row: dict) -> dict:
    """Mongo ``_id`` is excluded at projection time; this is a belt+braces
    pass for inserts where the driver mutates the dict."""
    return {k: v for k, v in row.items() if k != "_id"}


# ── Payload models ────────────────────────────────────────────────


class _InjuredParty(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=20)
    contact: Optional[str] = Field(default=None, max_length=200)
    age: Optional[int] = None
    employee_id: Optional[str] = Field(default=None, max_length=80)


class _Witness(BaseModel):
    name: str = Field(..., max_length=200)
    role: Optional[str] = Field(default=None, max_length=80)
    contact: Optional[str] = Field(default=None, max_length=200)
    statement: Optional[str] = Field(default=None, max_length=4000)


class IncidentCreate(BaseModel):
    kind: str = Field(..., description="accident | near_miss | hazard | dangerous_occurrence")
    severity: str = Field(default="minor")
    category: str = Field(default="other")
    description: str = Field(..., min_length=10, max_length=8000)
    occurred_at: Optional[str] = None  # ISO; defaults to now
    location_area: Optional[str] = Field(default=None, max_length=200)
    location_notes: Optional[str] = Field(default=None, max_length=600)
    injured_party: Optional[_InjuredParty] = None
    witnesses: Optional[list[_Witness]] = None
    immediate_action_taken: Optional[str] = Field(default=None, max_length=2000)
    first_aid_given: Optional[bool] = None
    first_aider_name: Optional[str] = Field(default=None, max_length=200)
    emergency_services_called: Optional[bool] = None
    hospital_treatment: Optional[bool] = None
    work_absence_expected_days: Optional[int] = None
    fatality: Optional[bool] = None
    asset_id: Optional[str] = None
    service_case_id: Optional[str] = None
    related_issue_id: Optional[str] = None
    tenant_profile: Optional[str] = Field(default=None, max_length=24)
    attachment_ids: Optional[list[str]] = None


class IncidentUpdate(BaseModel):
    severity: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=8000)
    immediate_action_taken: Optional[str] = Field(default=None, max_length=2000)
    location_area: Optional[str] = Field(default=None, max_length=200)
    location_notes: Optional[str] = Field(default=None, max_length=600)
    asset_id: Optional[str] = None
    service_case_id: Optional[str] = None
    related_issue_id: Optional[str] = None
    work_absence_expected_days: Optional[int] = None
    hospital_treatment: Optional[bool] = None
    emergency_services_called: Optional[bool] = None
    first_aid_given: Optional[bool] = None
    first_aider_name: Optional[str] = Field(default=None, max_length=200)
    witnesses: Optional[list[_Witness]] = None


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/incidents/picklists")
async def incidents_picklists(_: dict = Depends(get_current_user)) -> dict:
    """Static picklists for the frontend. Cached client-side."""
    return {
        "kinds": list(INCIDENT_KINDS),
        "severities": list(SEVERITIES),
        "statuses": list(STATUSES),
        "injured_roles": list(INJURED_ROLES),
        "categories": list(CATEGORIES),
        "root_causes": list(ROOT_CAUSE_OPTIONS),
        "riddor_questions": WIZARD_QUESTIONS,
    }


@router.post("/incidents")
async def create_incident(
    payload: IncidentCreate,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Create an incident. Defaults to ``status=reported`` and
    auto-escalates on Serious+ severity or fatality flag."""
    if payload.kind not in INCIDENT_KINDS:
        raise HTTPException(400, f"kind must be one of {list(INCIDENT_KINDS)}")
    severity = payload.severity if payload.severity in SEVERITIES else "minor"
    category = payload.category if payload.category in CATEGORIES else "other"
    if payload.injured_party and payload.injured_party.role and \
            payload.injured_party.role not in INJURED_ROLES:
        raise HTTPException(400, f"injured_party.role must be one of {list(INJURED_ROLES)}")
    org_id = await _require_org(user)
    occurred_at = _now()
    if payload.occurred_at:
        try:
            occurred_at = datetime.fromisoformat(payload.occurred_at.replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"occurred_at must be ISO format: {exc}")

    reference = await _next_reference(org_id)
    incident_id = _new_id()
    fatality = bool(payload.fatality) or severity == "fatal"
    auto_escalated = severity in SEVERITY_AUTO_ESCALATE or fatality

    incident = {
        "id": incident_id,
        "organization_id": org_id,
        "reference": reference,
        "kind": payload.kind,
        "category": category,
        "severity": severity,
        "status": "escalated" if auto_escalated else "reported",
        "occurred_at": occurred_at,
        "reported_at": _now(),
        "description": payload.description.strip(),
        "immediate_action_taken": (payload.immediate_action_taken or "").strip() or None,
        "location": {
            "area": (payload.location_area or "").strip() or None,
            "notes": (payload.location_notes or "").strip() or None,
        },
        "injured_party": payload.injured_party.model_dump() if payload.injured_party else None,
        "witnesses": [w.model_dump() for w in (payload.witnesses or [])],
        "first_aid_given": payload.first_aid_given,
        "first_aider_name": payload.first_aider_name,
        "emergency_services_called": payload.emergency_services_called,
        "hospital_treatment": payload.hospital_treatment,
        "work_absence_expected_days": payload.work_absence_expected_days,
        "fatality": fatality,
        "asset_id": payload.asset_id,
        "service_case_id": payload.service_case_id,
        "related_issue_id": payload.related_issue_id,
        "attachment_ids": list(payload.attachment_ids or []),
        "tenant_profile": payload.tenant_profile or "default",
        "riddor": {
            "status": "not_assessed",
            "assessment": None,
            "form": None,
            "deadline_at": None,
            "submission_ref": None,
            "submitted_at": None,
            "submitted_by": None,
        },
        "investigation": None,
        "manager_signed_off_at": None,
        "manager_signed_off_by": None,
        "hse_lead_signed_off_at": None,
        "hse_lead_signed_off_by": None,
        "auto_escalated": auto_escalated,
        "created_at": _now(),
        "updated_at": _now(),
        "created_by_user_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email"),
        "created_by_role": user.get("role"),
    }
    await db.incidents.insert_one(incident)
    await _audit(
        incident_id=incident_id, user=user, action="created",
        after={"reference": reference, "kind": payload.kind, "severity": severity,
               "status": incident["status"]},
        request=request,
    )
    if payload.asset_id:
        # Phase 3 — repeat-incident detection. Fires synchronously so
        # the CAPEX flag is visible immediately after a 3rd incident.
        try:
            await _refresh_asset_incident_flag(payload.asset_id, org_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[incidents] repeat-flag refresh failed: %s", exc)
    if auto_escalated:
        await _notify_escalation(incident)
    return _strip_internal(incident)


@router.get("/incidents")
async def list_incidents(
    kind: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    riddor: Optional[str] = Query(default=None),
    site: Optional[str] = Query(default=None, description="organization_id"),
    asset_id: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None, description="comma-separated for multi"),
    date_from: Optional[str] = Query(default=None, description="ISO date / datetime"),
    date_to: Optional[str] = Query(default=None, description="ISO date / datetime"),
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_current_user),
) -> dict:
    base: dict = {}
    if kind and kind in INCIDENT_KINDS:
        base["kind"] = kind
    if status and status in STATUSES:
        base["status"] = status
    if severity and severity in SEVERITIES:
        base["severity"] = severity
    if riddor:
        base["riddor.status"] = riddor
    if asset_id:
        base["asset_id"] = asset_id
    if site and user.get("is_master_admin"):
        base["organization_id"] = site
    if category:
        cats = [c.strip() for c in category.split(",") if c.strip() in CATEGORIES]
        if cats:
            base["category"] = {"$in": cats}
    occ_filter: dict = {}
    for label, key in (("$gte", date_from), ("$lte", date_to)):
        if key:
            try:
                dt = datetime.fromisoformat(key.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                occ_filter[label] = dt
            except Exception:  # noqa: BLE001
                pass
    if occ_filter:
        base["occurred_at"] = occ_filter
    if q:
        # Mongo regex is fine here — incidents are bounded per-org.
        base["$or"] = [
            {"reference": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"injured_party.name": {"$regex": q, "$options": "i"}},
        ]
    final = await _scope_filter(user, base)
    rows = await db.incidents.find(final, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"incidents": rows, "count": len(rows)}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, user: dict = Depends(get_current_user)) -> dict:
    incident = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and incident.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    if not _user_can_view_all(user) and incident.get("created_by_user_id") != user.get("id"):
        raise HTTPException(403, "You can only view incidents you created")
    actions = await db.incident_corrective_actions.find(
        {"incident_id": incident_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(200)
    audit = await db.incident_audit_log.find(
        {"incident_id": incident_id}, {"_id": 0},
    ).sort("at", 1).to_list(500)
    return {"incident": incident, "actions": actions, "audit": audit}


@router.patch("/incidents/{incident_id}")
async def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can edit incidents")
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")

    body = payload.model_dump(exclude_unset=True)
    updates: dict = {}
    if "severity" in body and body["severity"] in SEVERITIES:
        updates["severity"] = body["severity"]
    if "category" in body and body["category"] in CATEGORIES:
        updates["category"] = body["category"]
    if "description" in body and body["description"]:
        updates["description"] = body["description"].strip()
    if "immediate_action_taken" in body:
        updates["immediate_action_taken"] = (body["immediate_action_taken"] or "").strip() or None
    if "location_area" in body or "location_notes" in body:
        loc = existing.get("location") or {}
        if "location_area" in body:
            loc["area"] = (body["location_area"] or "").strip() or None
        if "location_notes" in body:
            loc["notes"] = (body["location_notes"] or "").strip() or None
        updates["location"] = loc
    for key in ("asset_id", "service_case_id", "related_issue_id",
                "work_absence_expected_days", "hospital_treatment",
                "emergency_services_called", "first_aid_given",
                "first_aider_name"):
        if key in body:
            updates[key] = body[key]
    if "witnesses" in body and body["witnesses"] is not None:
        updates["witnesses"] = body["witnesses"]
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates["updated_at"] = _now()
    await db.incidents.update_one({"id": incident_id}, {"$set": updates})
    await _audit(
        incident_id=incident_id, user=user, action="updated",
        before={k: existing.get(k) for k in updates if k in existing},
        after=updates, request=request,
    )
    fresh = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    return {"incident": fresh}


# ── Status transitions + manager sign-off ─────────────────────────


@router.post("/incidents/{incident_id}/status")
async def change_status(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_close(user):
        raise HTTPException(403, "Only managers/H&S leads can change status")
    new_status = (body or {}).get("status") or ""
    if new_status not in STATUSES:
        raise HTTPException(400, f"status must be one of {list(STATUSES)}")
    notes = ((body or {}).get("notes") or "").strip() or None
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0, "status": 1, "organization_id": 1})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    patch: dict = {"status": new_status, "updated_at": _now()}
    if new_status == "closed":
        patch["closed_at"] = _now()
        patch["closed_by"] = user.get("id")
        patch["manager_signed_off_at"] = patch["closed_at"]
        patch["manager_signed_off_by"] = user.get("full_name") or user.get("email")
    await db.incidents.update_one({"id": incident_id}, {"$set": patch})
    await _audit(
        incident_id=incident_id, user=user, action="status_changed",
        before={"status": existing.get("status")},
        after={"status": new_status},
        notes=notes, request=request,
    )
    return {"ok": True, "status": new_status}


# ── RIDDOR assessment ────────────────────────────────────────────


@router.post("/incidents/{incident_id}/riddor/assess")
async def riddor_assess_endpoint(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Run the RIDDOR wizard against the supplied answers. Persists
    the verdict on the incident and writes an audit row. Never
    auto-submits to HSE — submission requires the explicit
    ``/riddor/submit`` call."""
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can run a RIDDOR assessment")
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    answers = (body or {}).get("answers") or {}
    verdict = riddor_assess(answers)
    occurred_at = existing.get("occurred_at") or _now()
    if isinstance(occurred_at, str):
        try:
            occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            occurred_at = _now()
    deadline_at = (
        occurred_at + timedelta(days=verdict.deadline_days)
        if verdict.deadline_days else None
    )
    riddor_patch = {
        "status": verdict.status,
        "assessment": {
            "answers": {k: v for k, v in answers.items() if isinstance(v, (bool, type(None)))},
            "reasons": list(verdict.reasons),
            "qualifying_questions": verdict.qualifying_questions,
            "assessed_at": _now(),
            "assessed_by_user_id": user.get("id"),
            "assessed_by_name": user.get("full_name") or user.get("email"),
        },
        "form": verdict.form,
        "deadline_at": deadline_at,
    }
    set_patch = {"riddor": {**(existing.get("riddor") or {}), **riddor_patch}, "updated_at": _now()}
    if verdict.status in {"potential", "confirmed"} and existing.get("status") not in {"closed", "escalated"}:
        set_patch["status"] = "escalated"
    await db.incidents.update_one({"id": incident_id}, {"$set": set_patch})
    await _audit(
        incident_id=incident_id, user=user, action="riddor_assessed",
        before={"riddor": existing.get("riddor")},
        after={"riddor": set_patch["riddor"]},
        request=request,
    )
    if verdict.status in {"potential", "confirmed"}:
        fresh = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
        if fresh:
            await _notify_escalation(fresh)
    return {"verdict": verdict.to_dict(), "deadline_at": deadline_at}


@router.post("/incidents/{incident_id}/riddor/submit")
async def riddor_submit(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Record that the incident has been submitted to HSE. The actual
    submission is a manual act on the HSE portal; we store the
    reference + signed-off-by-user for the audit trail."""
    if not _user_can_close(user):
        raise HTTPException(403, "Only managers/H&S leads can record a RIDDOR submission")
    submission_ref = ((body or {}).get("submission_ref") or "").strip()
    if not submission_ref:
        raise HTTPException(400, "submission_ref required")
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    riddor = existing.get("riddor") or {}
    if riddor.get("status") not in {"confirmed", "potential"}:
        raise HTTPException(400, "Run the RIDDOR assessment first")
    new_riddor = {
        **riddor,
        "status": "submitted",
        "submission_ref": submission_ref,
        "submitted_at": _now(),
        "submitted_by": user.get("full_name") or user.get("email"),
    }
    await db.incidents.update_one(
        {"id": incident_id},
        {"$set": {"riddor": new_riddor, "updated_at": _now()}},
    )
    await _audit(
        incident_id=incident_id, user=user, action="riddor_submitted",
        before={"riddor.status": riddor.get("status")},
        after={"riddor.status": "submitted", "submission_ref": submission_ref},
        request=request,
    )
    return {"ok": True, "submission_ref": submission_ref}


# ── Investigation ─────────────────────────────────────────────────


@router.post("/incidents/{incident_id}/investigation")
async def upsert_investigation(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can edit investigations")
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    inv = existing.get("investigation") or {}
    is_new = not inv.get("started_at")
    investigator_user_id = (body or {}).get("investigator_user_id") or inv.get("investigator_user_id") or user.get("id")
    investigator_name = (body or {}).get("investigator_name") or inv.get("investigator_name") or user.get("full_name") or user.get("email")
    findings = ((body or {}).get("findings") or inv.get("findings") or "").strip()
    root_causes = [c for c in ((body or {}).get("root_causes") or inv.get("root_causes") or []) if c in ROOT_CAUSE_OPTIONS]
    review_at_raw = (body or {}).get("review_at") or inv.get("review_at")
    review_at = None
    if review_at_raw:
        try:
            review_at = datetime.fromisoformat(str(review_at_raw).replace("Z", "+00:00"))
            if review_at.tzinfo is None:
                review_at = review_at.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            review_at = None
    completed = bool((body or {}).get("completed"))
    new_inv = {
        "investigator_user_id": investigator_user_id,
        "investigator_name": investigator_name,
        "started_at": inv.get("started_at") or _now(),
        "findings": findings,
        "root_causes": root_causes,
        "review_at": review_at,
        "completed_at": _now() if completed else inv.get("completed_at"),
    }
    set_patch = {"investigation": new_inv, "updated_at": _now()}
    if is_new and existing.get("status") in {"reported", "escalated"}:
        set_patch["status"] = "investigating"
    if completed and existing.get("status") in {"investigating", "escalated", "reported"}:
        set_patch["status"] = "actions_pending"
    await db.incidents.update_one({"id": incident_id}, {"$set": set_patch})
    await _audit(
        incident_id=incident_id, user=user,
        action="investigation_started" if is_new else ("investigation_completed" if completed else "investigation_updated"),
        before={"investigation": inv}, after={"investigation": new_inv},
        request=request,
    )
    return {"investigation": new_inv, "status": set_patch.get("status", existing.get("status"))}


# ── Corrective actions ───────────────────────────────────────────


@router.post("/incidents/{incident_id}/actions")
async def add_action(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can add corrective actions")
    incident = await db.incidents.find_one({"id": incident_id}, {"_id": 0, "id": 1, "organization_id": 1, "reference": 1})
    if not incident:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and incident.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    description = ((body or {}).get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description required")
    priority = ((body or {}).get("priority") or "medium").lower()
    if priority not in {"low", "medium", "high", "critical"}:
        priority = "medium"
    due_date_raw = (body or {}).get("due_date")
    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.fromisoformat(str(due_date_raw).replace("Z", "+00:00"))
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            due_date = None
    assigned_to_user_id = (body or {}).get("assigned_to_user_id")
    assigned_to_name = (body or {}).get("assigned_to_name")
    action_doc = {
        "id": _new_id(),
        "incident_id": incident_id,
        "organization_id": incident["organization_id"],
        "incident_reference": incident.get("reference"),
        "description": description,
        "priority": priority,
        "assigned_to_user_id": assigned_to_user_id,
        "assigned_to_name": assigned_to_name,
        "due_date": due_date,
        "status": "open",
        "evidence_attachment_ids": [],
        "created_at": _now(),
        "updated_at": _now(),
        "created_by_user_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email"),
    }
    await db.incident_corrective_actions.insert_one(action_doc)
    await db.incidents.update_one(
        {"id": incident_id},
        {"$set": {"updated_at": _now()}},
    )
    await _audit(
        incident_id=incident_id, user=user, action="action_added",
        after={"action_id": action_doc["id"], "description": description, "priority": priority},
        request=request,
    )
    return _strip_internal(action_doc)


@router.patch("/incidents/{incident_id}/actions/{action_id}")
async def update_action(
    incident_id: str,
    action_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can update actions")
    existing = await db.incident_corrective_actions.find_one(
        {"id": action_id, "incident_id": incident_id}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Action not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your action")
    patch: dict = {}
    if "status" in (body or {}):
        s = body["status"]
        if s not in {"open", "in_progress", "completed", "escalated"}:
            raise HTTPException(400, "invalid status")
        patch["status"] = s
        if s == "completed":
            patch["completed_at"] = _now()
            patch["completed_by_user_id"] = user.get("id")
    if "description" in (body or {}) and body["description"]:
        patch["description"] = body["description"].strip()
    if "priority" in (body or {}):
        p = body["priority"]
        if p in {"low", "medium", "high", "critical"}:
            patch["priority"] = p
    if "assigned_to_user_id" in (body or {}):
        patch["assigned_to_user_id"] = body["assigned_to_user_id"]
    if "assigned_to_name" in (body or {}):
        patch["assigned_to_name"] = body["assigned_to_name"]
    if "due_date" in (body or {}):
        raw = body["due_date"]
        if raw:
            try:
                d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                patch["due_date"] = d
            except Exception:  # noqa: BLE001
                pass
        else:
            patch["due_date"] = None
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = _now()
    await db.incident_corrective_actions.update_one(
        {"id": action_id}, {"$set": patch},
    )
    await _audit(
        incident_id=incident_id, user=user, action="action_updated",
        before={k: existing.get(k) for k in patch if k in existing},
        after=patch, request=request,
    )
    fresh = await db.incident_corrective_actions.find_one(
        {"id": action_id}, {"_id": 0},
    )
    return _strip_internal(fresh or {})


# ── Quick-log mobile-first endpoint ───────────────────────────────


@router.post("/incidents/quick")
async def quick_log_incident(
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Mobile/voice-first quick log. Accepts a thin payload, fills
    in defaults, returns the created incident reference. Designed so
    a field user can record the bare facts in <30s, then refine
    later via PATCH."""
    description = ((body or {}).get("description") or "").strip()
    if len(description) < 10:
        raise HTTPException(400, "description must be at least 10 characters")
    payload = IncidentCreate(
        kind=(body or {}).get("kind") or "accident",
        severity=(body or {}).get("severity") or "minor",
        category=(body or {}).get("category") or "other",
        description=description,
        occurred_at=(body or {}).get("occurred_at"),
        location_area=(body or {}).get("location_area"),
        asset_id=(body or {}).get("asset_id"),
        related_issue_id=(body or {}).get("related_issue_id"),
        attachment_ids=(body or {}).get("attachment_ids"),
    )
    return await create_incident(payload, request=request, user=user)


# ── Stats (lightweight; full dashboard ships in Phase 3) ─────────


@router.get("/incidents/stats/summary")
async def incidents_summary(user: dict = Depends(get_current_user)) -> dict:
    """Tiny dashboard tile — counts by status / severity / RIDDOR.
    Phase 3 ships the full trend dashboard; this gives a meaningful
    surface day one."""
    f = await _scope_filter(user)
    rows = await db.incidents.find(f, {"_id": 0, "status": 1, "severity": 1, "riddor.status": 1, "kind": 1}).to_list(2000)
    by_status: dict = {}
    by_severity: dict = {}
    by_kind: dict = {}
    riddor_potential = 0
    riddor_confirmed = 0
    for r in rows:
        by_status[r.get("status", "unknown")] = by_status.get(r.get("status", "unknown"), 0) + 1
        by_severity[r.get("severity", "unknown")] = by_severity.get(r.get("severity", "unknown"), 0) + 1
        by_kind[r.get("kind", "unknown")] = by_kind.get(r.get("kind", "unknown"), 0) + 1
        rs = (r.get("riddor") or {}).get("status")
        if rs == "potential":
            riddor_potential += 1
        elif rs in {"confirmed", "submitted"}:
            riddor_confirmed += 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "by_severity": by_severity,
        "by_kind": by_kind,
        "riddor_potential": riddor_potential,
        "riddor_confirmed": riddor_confirmed,
    }


# ── Phase 2 — Signatures + Witness workflow + PDFs + HSE dashboard ──


def _aware(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _safe_b64(s: str | None) -> str | None:
    """Validate a base64-encoded PNG ≤ 200 KB. Strip data-URL prefix."""
    if not s:
        return None
    if isinstance(s, str) and s.startswith("data:"):
        s = s.split(",", 1)[1] if "," in s else s
    if len(s) > 280_000:  # ~210 KB raw → ~280 KB base64
        raise HTTPException(400, "Signature image too large (max 200 KB)")
    return s


@router.post("/incidents/{incident_id}/signatures")
async def add_signature(
    incident_id: str,
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Capture a digital signature against an incident. ``role`` can be
    ``injured_person`` / ``witness`` / ``manager`` / ``investigator``
    / ``hse_lead`` — used both for the PDF rendering and the audit row.
    Up to 12 signatures per incident (defensive cap)."""
    name = ((body or {}).get("name") or "").strip()
    role = ((body or {}).get("role") or "").strip().lower()
    image = _safe_b64((body or {}).get("image_b64"))
    if not name:
        raise HTTPException(400, "Signer name required")
    if role not in {"injured_person", "witness", "manager", "investigator",
                    "hse_lead", "other"}:
        raise HTTPException(400, "Invalid role")
    existing = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and existing.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    sigs = list(existing.get("signatures") or [])
    if len(sigs) >= 12:
        raise HTTPException(400, "Signature cap reached (12)")
    sig = {
        "id": _new_id(),
        "name": name,
        "role": role,
        "image_b64": image,
        "signed_at": _now(),
        "signed_by_user_id": user.get("id"),
        "signed_by_ip": (request.client.host if request and request.client else None),
    }
    sigs.append(sig)
    await db.incidents.update_one({"id": incident_id},
                                  {"$set": {"signatures": sigs, "updated_at": _now()}})
    await _audit(incident_id=incident_id, user=user, action="signature_added",
                 after={"role": role, "name": name}, request=request)
    return {"signature": sig, "count": len(sigs)}


# ── Witness statement workflow (token-based external signing) ────


class _WitnessInvite(BaseModel):
    name: str = Field(..., max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=80)
    contact: Optional[str] = Field(default=None, max_length=200)


@router.post("/incidents/{incident_id}/witness-invite")
async def invite_witness(
    incident_id: str,
    payload: _WitnessInvite,
    request: Request = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Mint a single-use witness statement token and email it to the
    witness. The token has a 30-day expiry; on submit the witness's
    statement + drawn signature are appended to the incident."""
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can invite witnesses")
    incident = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and incident.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    token = secrets.token_urlsafe(28)
    doc = {
        "token": token,
        "incident_id": incident_id,
        "organization_id": incident["organization_id"],
        "incident_reference": incident.get("reference"),
        "name": payload.name.strip(),
        "email": (payload.email or "").strip() or None,
        "role": (payload.role or "").strip() or None,
        "contact": (payload.contact or "").strip() or None,
        "created_at": _now(),
        "expires_at": _now() + timedelta(days=30),
        "used_at": None,
        "invited_by": user.get("full_name") or user.get("email"),
    }
    await db.incident_witness_tokens.insert_one(doc)
    sent = False
    if doc["email"]:
        try:
            from utils.email import send_email
            base = (
                os.environ.get("EMAIL_PUBLIC_BASE_URL")
                or os.environ.get("FRONTEND_URL")
                or os.environ.get("REACT_APP_BACKEND_URL")
                or ""
            ).rstrip("/")
            link = f"{base}/witness-statement/{token}" if base else f"/witness-statement/{token}"
            html = (
                f'<div style="font-family:Arial,sans-serif;color:#0F172A;line-height:1.55;max-width:560px;margin:0 auto;">'
                f'<h2 style="margin:0 0 12px;font-size:22px;font-weight:800;">Witness statement requested.</h2>'
                f"<p>Hi {_esc_html(payload.name)},</p>"
                f"<p>You were named as a witness for incident "
                f"<strong>{incident.get('reference')}</strong> at "
                f"<strong>{(await _org_name(incident['organization_id']))}</strong>.</p>"
                f"<p>Please take a moment to record what you saw using the secure link below. "
                f"It's one-time-use and expires in 30 days.</p>"
                f'<p style="margin:18px 0;"><a href="{link}" '
                f'style="background:#1d4ed8;color:#fff;padding:10px 18px;border-radius:8px;'
                f'text-decoration:none;font-weight:700;font-size:14px;">Provide statement →</a></p>'
                f'<p style="font-size:11px;color:#94a3b8;">Sent by {_esc_html(doc["invited_by"])} on behalf of '
                f'{_esc_html(await _org_name(incident["organization_id"]))}.</p>'
                f"</div>"
            )
            sent = bool(await send_email(
                to=doc["email"],
                subject=f"Witness statement requested · {incident.get('reference')}",
                html=html,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[incidents] witness invite email failed: %s", exc)
    await _audit(incident_id=incident_id, user=user, action="witness_invited",
                 after={"witness_name": payload.name, "emailed": sent},
                 request=request)
    return {"token": token, "emailed": sent, "expires_at": doc["expires_at"]}


def _esc_html(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _org_name(org_id: str) -> str:
    try:
        o = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
        return (o or {}).get("name") or "your site"
    except Exception:
        return "your site"


@router.get("/incidents/witness-statement/{token}")
async def witness_statement_landing(token: str) -> dict:
    """Public — no auth. Returns the minimal context a witness needs
    to record their statement without leaking the full incident."""
    row = await db.incident_witness_tokens.find_one({"token": token}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Link not recognised")
    if row.get("used_at"):
        raise HTTPException(410, "This link has already been used")
    if row.get("expires_at") and _aware(row["expires_at"]) < _now():
        raise HTTPException(410, "This link has expired")
    incident = await db.incidents.find_one(
        {"id": row["incident_id"]},
        {"_id": 0, "reference": 1, "occurred_at": 1, "location": 1, "kind": 1, "organization_id": 1},
    )
    return {
        "name": row.get("name"),
        "email": row.get("email"),
        "incident_reference": row.get("incident_reference") or (incident or {}).get("reference"),
        "incident_occurred_at": (incident or {}).get("occurred_at"),
        "incident_location": ((incident or {}).get("location") or {}).get("area"),
        "incident_kind": (incident or {}).get("kind"),
        "org_name": await _org_name((incident or {}).get("organization_id") or row.get("organization_id")),
        "expires_at": row.get("expires_at"),
    }


@router.post("/incidents/witness-statement/{token}")
async def witness_statement_submit(token: str, body: dict = Body(...), request: Request = None) -> dict:
    row = await db.incident_witness_tokens.find_one({"token": token}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Link not recognised")
    if row.get("used_at"):
        raise HTTPException(410, "This link has already been used")
    if row.get("expires_at") and _aware(row["expires_at"]) < _now():
        raise HTTPException(410, "This link has expired")
    statement = ((body or {}).get("statement") or "").strip()
    if len(statement) < 20:
        raise HTTPException(400, "Statement must be at least 20 characters")
    signature_b64 = _safe_b64((body or {}).get("signature_b64"))
    incident = await db.incidents.find_one({"id": row["incident_id"]}, {"_id": 0})
    if not incident:
        raise HTTPException(404, "Incident no longer exists")
    new_witness = {
        "id": _new_id(),
        "name": row.get("name"),
        "role": row.get("role"),
        "contact": row.get("contact") or row.get("email"),
        "statement": statement,
        "statement_at": _now(),
        "signature": {
            "name": row.get("name"),
            "role": "witness",
            "image_b64": signature_b64,
            "signed_at": _now(),
            "signed_by_ip": (request.client.host if request and request.client else None),
        } if signature_b64 else None,
        "submitted_via_token": True,
    }
    witnesses = list(incident.get("witnesses") or [])
    witnesses.append(new_witness)
    await db.incidents.update_one(
        {"id": row["incident_id"]},
        {"$set": {"witnesses": witnesses, "updated_at": _now()}},
    )
    await db.incident_witness_tokens.update_one(
        {"token": token},
        {"$set": {"used_at": _now()}},
    )
    # Audit row attributed to the witness, not a user.
    await db.incident_audit_log.insert_one({
        "id": _new_id(),
        "incident_id": row["incident_id"],
        "at": _now(),
        "actor_user_id": None,
        "actor_name": row.get("name"),
        "actor_role": "witness",
        "action": "witness_statement_received",
        "after": {"witness_name": row.get("name")},
        "ip": (request.client.host if request and request.client else None),
    })
    return {"ok": True, "incident_reference": row.get("incident_reference")}


# ── PDF endpoints ─────────────────────────────────────────────────


async def _load_incident_and_actions(incident_id: str, user: dict) -> tuple[dict, list]:
    incident = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(404, "Incident not found")
    if not user.get("is_master_admin") and incident.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "Not your incident")
    actions = await db.incident_corrective_actions.find(
        {"incident_id": incident_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(200)
    return incident, actions


@router.get("/incidents/{incident_id}/pdf/accident")
async def pdf_accident(incident_id: str, user: dict = Depends(get_current_user)) -> Response:
    from utils.incident_pdf import accident_report_pdf
    incident, actions = await _load_incident_and_actions(incident_id, user)
    pdf = accident_report_pdf(incident, org_name=await _org_name(incident["organization_id"]), actions=actions)
    return _pdf_response(pdf, f"{incident['reference']}-accident.pdf")


@router.get("/incidents/{incident_id}/pdf/riddor")
async def pdf_riddor(incident_id: str, user: dict = Depends(get_current_user)) -> Response:
    from utils.incident_pdf import riddor_report_pdf
    incident, _ = await _load_incident_and_actions(incident_id, user)
    if not (incident.get("riddor") or {}).get("status") or incident["riddor"]["status"] == "not_assessed":
        raise HTTPException(400, "Run the RIDDOR assessment first")
    pdf = riddor_report_pdf(incident, org_name=await _org_name(incident["organization_id"]))
    return _pdf_response(pdf, f"{incident['reference']}-riddor.pdf")


@router.get("/incidents/{incident_id}/pdf/investigation")
async def pdf_investigation(incident_id: str, user: dict = Depends(get_current_user)) -> Response:
    from utils.incident_pdf import investigation_report_pdf
    incident, actions = await _load_incident_and_actions(incident_id, user)
    if not incident.get("investigation"):
        raise HTTPException(400, "No investigation started")
    pdf = investigation_report_pdf(incident, actions=actions, org_name=await _org_name(incident["organization_id"]))
    return _pdf_response(pdf, f"{incident['reference']}-investigation.pdf")


@router.get("/incidents/{incident_id}/pdf/witness/{witness_index}")
async def pdf_witness(incident_id: str, witness_index: int,
                     user: dict = Depends(get_current_user)) -> Response:
    from utils.incident_pdf import witness_statement_pdf
    incident, _ = await _load_incident_and_actions(incident_id, user)
    witnesses = incident.get("witnesses") or []
    if witness_index < 0 or witness_index >= len(witnesses):
        raise HTTPException(404, "Witness not found")
    pdf = witness_statement_pdf(incident, witnesses[witness_index],
                                org_name=await _org_name(incident["organization_id"]))
    safe = (witnesses[witness_index].get("name") or "witness").replace(" ", "_")
    return _pdf_response(pdf, f"{incident['reference']}-witness-{safe}.pdf")


@router.get("/incidents/pdf/actions-log")
async def pdf_actions_log(user: dict = Depends(get_current_user)) -> Response:
    """All corrective actions in the user's scope — open + closed."""
    from utils.incident_pdf import corrective_action_log_pdf
    f: dict = {}
    if not user.get("is_master_admin"):
        f["organization_id"] = user.get("organization_id")
    actions = await db.incident_corrective_actions.find(f, {"_id": 0}).sort("created_at", -1).to_list(1000)
    org_name = await _org_name(user.get("organization_id") or "")
    pdf = corrective_action_log_pdf(actions, org_name=org_name)
    return _pdf_response(pdf, "corrective-actions-log.pdf")


@router.get("/incidents/pdf/management-summary")
async def pdf_management_summary(days: int = Query(default=30, ge=1, le=365),
                                  user: dict = Depends(get_current_user)) -> Response:
    from utils.incident_pdf import management_summary_pdf
    stats = await _hse_dashboard_aggregates(user, days=days, include_categories=True, include_top_assets=True)
    org_name = await _org_name(user.get("organization_id") or "")
    pdf = management_summary_pdf(stats, org_name=org_name, period_label=f"Last {days} days")
    return _pdf_response(pdf, f"management-summary-{days}d.pdf")


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── HSE dashboard v1 ──────────────────────────────────────────────


async def _hse_dashboard_aggregates(user: dict, days: int = 30,
                                     include_categories: bool = True,
                                     include_top_assets: bool = True) -> dict:
    """Reusable aggregator. Returns the same shape as
    ``/incidents/stats/summary`` plus trend, top assets, and category
    breakdowns."""
    f = await _scope_filter(user)
    since = _now() - timedelta(days=days)
    f["created_at"] = {"$gte": since}
    rows = await db.incidents.find(
        f,
        {"_id": 0, "status": 1, "severity": 1, "riddor.status": 1, "kind": 1,
         "category": 1, "asset_id": 1, "created_at": 1, "fatality": 1},
    ).to_list(5000)
    by_status: dict = {}
    by_severity: dict = {}
    by_kind: dict = {}
    by_category: dict = {}
    by_day: dict = {}
    asset_counts: dict = {}
    riddor_potential = 0
    riddor_confirmed = 0
    riddor_submitted = 0
    fatalities = 0
    for r in rows:
        by_status[r.get("status", "unknown")] = by_status.get(r.get("status", "unknown"), 0) + 1
        by_severity[r.get("severity", "unknown")] = by_severity.get(r.get("severity", "unknown"), 0) + 1
        by_kind[r.get("kind", "unknown")] = by_kind.get(r.get("kind", "unknown"), 0) + 1
        by_category[r.get("category", "other")] = by_category.get(r.get("category", "other"), 0) + 1
        rs = (r.get("riddor") or {}).get("status")
        if rs == "potential":
            riddor_potential += 1
        elif rs == "confirmed":
            riddor_confirmed += 1
        elif rs == "submitted":
            riddor_submitted += 1
        if r.get("fatality"):
            fatalities += 1
        ca = r.get("created_at")
        if isinstance(ca, datetime):
            key = ca.date().isoformat()
            by_day[key] = by_day.get(key, 0) + 1
        if include_top_assets and r.get("asset_id"):
            asset_counts[r["asset_id"]] = asset_counts.get(r["asset_id"], 0) + 1

    out = {
        "period_days": days,
        "total": len(rows),
        "by_status": by_status,
        "by_severity": by_severity,
        "by_kind": by_kind,
        "by_category": by_category if include_categories else {},
        "by_day": [{"date": d, "count": by_day[d]} for d in sorted(by_day)],
        "riddor_potential": riddor_potential,
        "riddor_confirmed": riddor_confirmed,
        "riddor_submitted": riddor_submitted,
        "fatalities": fatalities,
    }
    if include_top_assets and asset_counts:
        ids = sorted(asset_counts.items(), key=lambda x: -x[1])[:8]
        equip = await db.equipment.find(
            {"id": {"$in": [aid for aid, _ in ids]}},
            {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1},
        ).to_list(50)
        names = {e["id"]: (e.get("name") or f"{e.get('manufacturer','')} {e.get('model','')}".strip())
                 for e in equip}
        out["top_assets"] = [
            {"asset_id": aid, "asset_name": names.get(aid) or aid, "count": cnt}
            for aid, cnt in ids
        ]
    return out


@router.get("/incidents/hse/dashboard")
async def hse_dashboard(days: int = Query(default=30, ge=1, le=365),
                         user: dict = Depends(get_current_user)) -> dict:
    """Aggregated HSE dashboard for managers/H&S leads.
    Same scope rules as /incidents (staff see their own; manager+ org-wide)."""
    return await _hse_dashboard_aggregates(user, days=days,
                                            include_categories=True,
                                            include_top_assets=True)


# ── Phase 3 — Repeat-incident detection · Heatmap · Risk hot-list ──


REPEAT_INCIDENT_DEFAULT_WINDOW_DAYS = 90
REPEAT_INCIDENT_DEFAULT_THRESHOLD = 3


async def _repeat_incident_rollup(
    user: dict,
    *,
    window_days: int = REPEAT_INCIDENT_DEFAULT_WINDOW_DAYS,
    threshold: int = REPEAT_INCIDENT_DEFAULT_THRESHOLD,
    limit: int = 50,
) -> list[dict]:
    """Return assets that crossed the repeat-incident threshold in the
    last ``window_days``. Joins onto ``db.equipment`` for friendly
    asset names + ``capex.status`` so the UI can show whether the
    asset is already flagged for CAPEX or whether *this* roll-up is
    what would have triggered the flag."""
    f = await _scope_filter(user)
    since = _now() - timedelta(days=window_days)
    f["created_at"] = {"$gte": since}
    f["asset_id"] = {"$ne": None}
    rows = await db.incidents.find(
        f,
        {"_id": 0, "id": 1, "asset_id": 1, "severity": 1, "created_at": 1,
         "reference": 1, "kind": 1, "organization_id": 1},
    ).to_list(5000)
    by_asset: dict[str, dict] = {}
    sev_weight = {"minor": 1, "moderate": 2, "serious": 4, "major": 6, "fatal": 10}
    for r in rows:
        aid = r["asset_id"]
        slot = by_asset.setdefault(aid, {
            "asset_id": aid, "organization_id": r.get("organization_id"),
            "count": 0, "severity_score": 0,
            "last_incident_at": None, "last_incident_ref": None,
            "kinds": {}, "incident_ids": [],
        })
        slot["count"] += 1
        slot["severity_score"] += sev_weight.get(r.get("severity", "minor"), 1)
        ca = r.get("created_at")
        if isinstance(ca, datetime) and (
            slot["last_incident_at"] is None or _aware(ca) > _aware(slot["last_incident_at"])
        ):
            slot["last_incident_at"] = ca
            slot["last_incident_ref"] = r.get("reference")
        slot["kinds"][r.get("kind", "unknown")] = slot["kinds"].get(r.get("kind", "unknown"), 0) + 1
        if len(slot["incident_ids"]) < 25:
            slot["incident_ids"].append(r["id"])
    flagged = [s for s in by_asset.values() if s["count"] >= threshold]
    if not flagged:
        return []
    asset_ids = [s["asset_id"] for s in flagged]
    equip = await db.equipment.find(
        {"id": {"$in": asset_ids}},
        {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1,
         "location": 1, "capex": 1},
    ).to_list(500)
    equip_by_id = {e["id"]: e for e in equip}
    for s in flagged:
        e = equip_by_id.get(s["asset_id"]) or {}
        s["asset_name"] = (
            e.get("name") or f"{e.get('manufacturer','')} {e.get('model','')}".strip() or s["asset_id"]
        )
        s["location"] = e.get("location")
        s["capex_status"] = (e.get("capex") or {}).get("status")
        s["capex_already_flagged"] = (e.get("capex") or {}).get("status") in {
            "replace_now", "replace_soon", "at_risk",
        }
    flagged.sort(key=lambda x: (-x["severity_score"], -x["count"]))
    return flagged[:limit]


@router.get("/incidents/hse/repeat-detection")
async def repeat_detection(
    window_days: int = Query(default=90, ge=7, le=365),
    threshold: int = Query(default=3, ge=2, le=20),
    user: dict = Depends(get_current_user),
) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can read repeat-incident detection")
    rows = await _repeat_incident_rollup(user, window_days=window_days, threshold=threshold)
    return {
        "window_days": window_days,
        "threshold": threshold,
        "flagged": rows,
        "total_flagged": len(rows),
    }


async def _refresh_asset_incident_flag(asset_id: str, organization_id: str) -> dict | None:
    """Idempotent — recomputes the asset's repeat-incident rollup
    (90 days, ≥3 threshold) and writes a tiny summary back onto the
    equipment doc under ``equipment.incident_flag``. Called from the
    incident-create hook so the CAPEX UI sees the flag the moment
    the 3rd incident lands."""
    since = _now() - timedelta(days=REPEAT_INCIDENT_DEFAULT_WINDOW_DAYS)
    rows = await db.incidents.find(
        {"asset_id": asset_id, "organization_id": organization_id,
         "created_at": {"$gte": since}},
        {"_id": 0, "severity": 1, "created_at": 1, "reference": 1, "id": 1},
    ).to_list(500)
    if not rows:
        await db.equipment.update_one(
            {"id": asset_id, "organization_id": organization_id},
            {"$unset": {"incident_flag": ""}},
        )
        return None
    sev_weight = {"minor": 1, "moderate": 2, "serious": 4, "major": 6, "fatal": 10}
    score = sum(sev_weight.get(r.get("severity", "minor"), 1) for r in rows)
    last = max(_aware(r["created_at"]) for r in rows if isinstance(r.get("created_at"), datetime))
    flag = {
        "count_90d": len(rows),
        "severity_score": score,
        "last_incident_at": last,
        "last_incident_ref": next(
            (r.get("reference") for r in rows
             if isinstance(r.get("created_at"), datetime) and _aware(r["created_at"]) == last),
            None,
        ),
        "capex_recommended": len(rows) >= REPEAT_INCIDENT_DEFAULT_THRESHOLD,
        "updated_at": _now(),
    }
    await db.equipment.update_one(
        {"id": asset_id, "organization_id": organization_id},
        {"$set": {"incident_flag": flag}},
    )
    return flag


@router.get("/incidents/hse/heatmap")
async def hse_heatmap(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
) -> dict:
    """7×24 grid of incident counts (day-of-week × hour-of-day). The
    UI renders this as a heatmap so operators can spot patterns
    like "Saturday afternoon poolside" without staring at a table."""
    f = await _scope_filter(user)
    since = _now() - timedelta(days=days)
    f["created_at"] = {"$gte": since}
    rows = await db.incidents.find(
        f, {"_id": 0, "created_at": 1, "severity": 1},
    ).to_list(5000)
    grid = [[0 for _ in range(24)] for _ in range(7)]  # [dow][hour]
    sev_grid = [[0 for _ in range(24)] for _ in range(7)]
    sev_weight = {"minor": 1, "moderate": 2, "serious": 4, "major": 6, "fatal": 10}
    for r in rows:
        ca = r.get("created_at")
        if not isinstance(ca, datetime):
            continue
        ca = _aware(ca)
        dow = ca.weekday()  # 0=Mon
        hour = ca.hour
        grid[dow][hour] += 1
        sev_grid[dow][hour] += sev_weight.get(r.get("severity", "minor"), 1)
    return {
        "period_days": days,
        "grid_counts": grid,
        "grid_severity_score": sev_grid,
        "day_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "total": sum(sum(row) for row in grid),
    }


# ── Phase 4 — AI assistance + Whisper voice-to-text ──────────────


@router.post("/incidents/{incident_id}/ai/summarise")
async def ai_summarise(incident_id: str, user: dict = Depends(get_current_user)) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can use AI summarisation")
    incident, _ = await _load_incident_and_actions(incident_id, user)
    from utils.incident_ai import summarise_incident
    summary = await summarise_incident(incident)
    if not summary:
        raise HTTPException(503, "AI summary unavailable — try again or write one manually")
    return {"summary": summary}


@router.post("/incidents/{incident_id}/ai/root-causes")
async def ai_root_causes(incident_id: str, user: dict = Depends(get_current_user)) -> dict:
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can use AI suggestions")
    incident, _ = await _load_incident_and_actions(incident_id, user)
    from utils.incident_ai import suggest_root_causes
    causes = await suggest_root_causes(incident)
    if causes is None:
        raise HTTPException(503, "AI root-cause hint unavailable")
    return {"root_causes": causes}


@router.post("/incidents/{incident_id}/ai/riddor-hint")
async def ai_riddor_hint(incident_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Returns pre-filled Yes/No/Don't-know answers for the RIDDOR
    wizard. **Strictly advisory** — the wizard still has to be run
    by a human."""
    if not _user_can_view_all(user):
        raise HTTPException(403, "Only managers/H&S leads can use the RIDDOR hint")
    incident, _ = await _load_incident_and_actions(incident_id, user)
    from utils.incident_ai import hint_riddor_qualification
    hint = await hint_riddor_qualification(incident)
    if not hint:
        raise HTTPException(503, "AI RIDDOR hint unavailable")
    return hint


@router.post("/incidents/ai/transcribe")
async def ai_transcribe(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Whisper voice-to-text endpoint. Accepts ``multipart/form-data``
    with a single ``file`` field (≤25 MB, mp3/m4a/wav/webm/mp4). Returns
    the transcript so the frontend can drop it into the description
    textarea for the user to edit before submitting."""
    from utils.incident_ai import transcribe_audio
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(400, "file upload required")
    # SpooledTemporaryFile-compatible — read into BytesIO so the
    # emergentintegrations client sees a proper file-like object.
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty audio file")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio file exceeds 25 MB limit")
    import io
    buf = io.BytesIO(raw)
    # Preserve a sensible filename so the API has a file extension hint.
    buf.name = getattr(file, "filename", None) or "audio.webm"
    text = await transcribe_audio(buf)
    if not text:
        raise HTTPException(503, "Transcription failed — please retype the description")
    return {"transcript": text}


# ── Indexes ──────────────────────────────────────────────────────


async def ensure_incident_indexes() -> None:
    await db.incidents.create_index([("organization_id", 1), ("created_at", -1)])
    await db.incidents.create_index([("id", 1)], unique=True)
    await db.incidents.create_index([("reference", 1)])
    await db.incidents.create_index([("status", 1)])
    await db.incidents.create_index([("severity", 1)])
    await db.incidents.create_index([("riddor.status", 1)])
    await db.incidents.create_index([("asset_id", 1)])
    await db.incident_corrective_actions.create_index([("incident_id", 1)])
    await db.incident_corrective_actions.create_index([("organization_id", 1), ("status", 1)])
    await db.incident_corrective_actions.create_index([("due_date", 1)])
    await db.incident_audit_log.create_index([("incident_id", 1), ("at", 1)])
    await db.incident_witness_tokens.create_index([("token", 1)], unique=True)
    await db.incident_witness_tokens.create_index([("incident_id", 1)])
    await db.incident_witness_tokens.create_index([("expires_at", 1)])
