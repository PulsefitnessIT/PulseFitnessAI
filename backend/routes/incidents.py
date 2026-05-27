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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
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
