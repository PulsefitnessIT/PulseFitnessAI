"""
GymAxis Service Operations — Cases API.

Iter 215dn (Phase 1) · annotations backfilled iter 215eb.

Endpoints under `/api/svc`:
  GET    /cases                        — list with filters (status, priority, site, engineer)
  GET    /cases/{id}                   — detail w/ rolled-up timeline
  PUT    /cases/{id}                   — patch fields (priority, engineer, scheduled_at…)
  POST   /cases/{id}/transition        — move state via the state machine
  POST   /cases/{id}/notes             — append free-text note to timeline
  GET    /cases/{id}/events            — paginated timeline

All endpoints scope by `organization_id` from the caller; rejected if missing.
"""

# ─────────────────────────────────────────────────────────────────
# Integration field manifest — see /app/memory/SVC_FIELD_MAPPING.md § 2-3.
# Format: "field_name": "sicon: <SiconField> · sage: <SageField> · <direction>"
# Use `gymaxis_only: <reason>` for fields that don't sync externally.
# Lint at /app/backend/scripts/check_integration_mapping.py reads this dict.
# ─────────────────────────────────────────────────────────────────
__integration_fields__ = {
    # svc_cases collection
    "id":                     "gymaxis_only: local uuid",
    "reference":              "sicon: ServiceCallReference · sage: SLInvoice.Reference · bidirectional",
    "organization_id":        "gymaxis_only: tenant scoping",
    "site_id":                "sicon: SubLocationID · sage: SLDeliveryAddressID · bidirectional",
    "site_name":              "sicon: SubLocationName · gymaxis_only display copy · GymAxis → Sicon",
    "asset_id":               "sicon: EquipmentID · Sicon → GymAxis",
    "asset_name":             "sicon: EquipmentDescription · GymAxis → Sicon",
    "title":                  "sicon: ServiceCallTitle · gymaxis_only on Sage · GymAxis → Sicon",
    "description":            "sicon: ServiceCallDescription · GymAxis → Sicon",
    "priority":               "sicon: PriorityID (mapped via PRIORITY_CROSSWALK) · GymAxis → Sicon",
    "status":                 "sicon: StatusID (mapped via STATUS_CROSSWALK) · bidirectional",
    "fault_code":             "sicon: FaultCode · GymAxis → Sicon",
    "cover_type":             "sicon: CoverTypeID · sage: NominalCode (via COVER_NOMINAL) · GymAxis → both",
    "case_type":              "sicon: JobTypeID (repair|ppm|install) · GymAxis → Sicon",
    "customer_name":          "sicon: CustomerContactName · sage: SLCustomerAccount.Name · bidirectional",
    "customer_phone":         "sicon: CustomerContactPhone · GymAxis → Sicon",
    "customer_email":         "sicon: CustomerContactEmail · GymAxis → Sicon",
    "assigned_engineer_id":   "sicon: AppointmentResourceID · sage: Employee.Reference · GymAxis → Sicon",
    "assigned_engineer_name": "sicon: AppointmentResourceName · GymAxis → Sicon",
    "scheduled_at":           "sicon: AppointmentStartDate · GymAxis → Sicon",
    "estimated_minutes":      "sicon: AppointmentDurationMinutes · GymAxis → Sicon",
    "sla_response_at":        "sicon: SLAResponseTarget · GymAxis → Sicon",
    "sla_resolve_at":         "sicon: SLAResolveTarget · GymAxis → Sicon",
    "logged_by_id":           "sicon: CreatedBySageUserID · sage: Employee.Reference · GymAxis → Sicon",
    "logged_by_name":         "sicon: CreatedByUserName · GymAxis → Sicon",
    "source":                 "sicon: ServiceCallSource (phone|email|web|portal) · GymAxis → Sicon",
    "allocated_parts":        "sicon: AllocatedParts[] (rolled into StockMovements per allocation) · GymAxis → Sicon",
    "equipment_ids":          "sicon: CoveredEquipmentIDs[] · bidirectional",
    "equipment_serials":      "sicon: SerialNumbers[] · GymAxis → Sicon",
    "contact_id":             "gymaxis_only: gym_floor_staff.id back-reference (intake cascade)",
    "quote_required":         "sage: SLQuote.Required (drives auto-draft on intake) · GymAxis → Sage",
    "customer_po_number":     "sage: SLInvoice.SecondReference / CustomerPONumber · GymAxis → Sage",
    # svc_case_events collection (timeline)
    "events.id":              "gymaxis_only: local event uuid",
    "events.case_id":         "gymaxis_only: FK → svc_cases.id",
    "events.type":            "sicon: NoteTypeID (mapped via NOTE_TYPE_CROSSWALK) · GymAxis → Sicon",
    "events.body":             "sicon: NoteText · GymAxis → Sicon",
    "events.from_state":      "sicon: PreviousStatusID · GymAxis → Sicon (state_change events only)",
    "events.to_state":        "sicon: NewStatusID · GymAxis → Sicon (state_change events only)",
    "events.reason":          "sicon: TrackingNoteReason · GymAxis → Sicon",
    "events.actor_id":        "sicon: CreatedBySageUserID · GymAxis → Sicon",
    "events.actor_name":      "sicon: CreatedByUserName · GymAxis → Sicon",
    "events.at":              "sicon: CreatedAt · GymAxis → Sicon",
    "events.visibility":      "gymaxis_only: internal|customer drives Sicon VisibleToCustomer flag at push time",
}

from datetime import datetime, timezone, timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.audit import audit_log
from utils.database import db
from utils.auth import get_current_user
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, ALL_STATES,
)
from routes.svc.integrations import sicon_sync, sage_invoice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc", tags=["Service Ops · Cases"])


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
# READS
# ─────────────────────────────────────────────────────────────────

@router.get("/cases")
async def list_cases(
    status: str = Query("", description="open | closed | <state>"),
    priority: str = Query(""),
    site_id: str = Query(""),
    engineer_id: str = Query(""),
    contract_id: str = Query(""),
    cover_type: str = Query(""),
    case_type: str = Query(""),
    search: str = Query(""),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    q = {**_of(user)}
    if status:
        if status == "open":
            q["status"] = {"$in": list(OPEN_STATES)}
        elif status == "closed":
            q["status"] = {"$in": ["closed", "invoiced"]}
        else:
            q["status"] = status
    if priority:
        q["priority"] = priority
    if site_id:
        q["site_id"] = site_id
    if engineer_id:
        q["assigned_engineer_id"] = engineer_id
    if contract_id:
        q["contract_id"] = contract_id
    if cover_type:
        q["cover_type"] = cover_type
    if case_type:
        q["case_type"] = case_type
    if search:
        q["$or"] = [
            {"reference": {"$regex": search, "$options": "i"}},
            {"title": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"site_name": {"$regex": search, "$options": "i"}},
        ]
    # Iter 216h174 — Payload-size pass. Exclude heavy detail-only fields
    # from the case list response. The desk-page list only needs ~15
    # summary fields (reference, title, status, priority, SLA, assigned
    # engineer name, fault code/category, site name, customer name).
    # `events` lives in svc_case_events (already excluded) but the case
    # doc itself can accumulate large embedded blobs:
    #   • `ai_triage`, `ai_summary`, `ai_triage_history`  — Claude outputs
    #   • `triage_history`, `state_change_history`, `dispatch_history`
    #   • `customer_signature`, `engineer_signature`     — base64 PNG
    #   • `media`, `photos`, `attachments`               — file blobs
    #   • `safety_responses`                              — checklist payload
    #   • `notes_internal`, `notes_customer`             — long text
    #   • `resolution_note`, `cover_audit`               — append-only
    #   • `quote_lines`, `parts_requested`               — embedded arrays
    # These are still served on /cases/{id} (detail) — only stripped
    # from the list response.
    _CASE_LIST_EXCLUDE = {
        "_id": 0,
        "ai_triage": 0, "ai_summary": 0, "ai_triage_history": 0,
        "triage_history": 0, "state_change_history": 0, "dispatch_history": 0,
        "customer_signature": 0, "engineer_signature": 0,
        "media": 0, "photos": 0, "attachments": 0,
        "safety_responses": 0,
        "notes_internal": 0, "notes_customer": 0,
        "resolution_note": 0, "cover_audit": 0,
        "quote_lines": 0, "parts_requested": 0,
    }
    total = await db.svc_cases.count_documents(q)
    items = (
        await db.svc_cases
        .find(q, _CASE_LIST_EXCLUDE)
        .sort([("sla_resolve_at", 1), ("created_at", -1)])
        .skip(skip).limit(limit)
        .to_list(limit)
    )
    return {"cases": items, "total": total}


@router.get("/cases/{case_id}")
async def get_case(case_id: str, user=Depends(get_current_user)):
    case = _strip(await db.svc_cases.find_one({"id": case_id, **_of(user)}))
    if not case:
        raise HTTPException(404, "Case not found")
    events = (
        await db.svc_case_events
        .find({"case_id": case_id, **_of(user)}, {"_id": 0})
        .sort("at", -1)
        .limit(200)
        .to_list(200)
    )
    case["events"] = events
    return case


@router.get("/cases/{case_id}/events")
async def list_case_events(
    case_id: str, skip: int = 0, limit: int = 100,
    user=Depends(get_current_user),
):
    rows = (
        await db.svc_case_events
        .find({"case_id": case_id, **_of(user)}, {"_id": 0})
        .sort("at", -1).skip(skip).limit(limit)
        .to_list(limit)
    )
    return {"events": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# WRITES
# ─────────────────────────────────────────────────────────────────

_VALID_PATCH_FIELDS = {
    "title", "description", "priority", "fault_code", "fault_category",
    "assigned_engineer_id", "assigned_engineer_name", "scheduled_at",
    "asset_id", "asset_name", "site_id", "site_name", "site_postcode",
    "contract_id", "cover_type", "case_type", "customer_name", "customer_email",
    "customer_phone", "estimated_minutes", "tags",
    "equipment_ids", "equipment_serials", "required_skills",
    "comms_auto_notify",
    # Iter 216h79 — customer rating captured at case sign-off, feeds the
    # partner performance score.
    "customer_rating", "customer_rating_comment",
}


@router.put("/cases/{case_id}")
async def update_case(case_id: str, data: dict, user=Depends(get_current_user)):
    existing = await db.svc_cases.find_one({"id": case_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Case not found")
    updates = {k: v for k, v in data.items() if k in _VALID_PATCH_FIELDS}
    if not updates:
        return _strip(existing)
    updates["updated_at"] = _now()
    await db.svc_cases.update_one({"id": case_id}, {"$set": updates})
    # Audit edit on timeline
    changes = [
        {"field": k, "before": existing.get(k), "after": v}
        for k, v in updates.items()
        if k != "updated_at" and existing.get(k) != v
    ]
    if changes:
        await append_event(
            case_id=case_id, organization_id=user["organization_id"],
            event_type="edit", actor=user, body=f"{len(changes)} field(s) updated",
            extra={"changes": changes},
        )
    out = {**existing, **updates}
    await sicon_sync.push_case(out)
    return _strip(out)


@router.post("/cases/{case_id}/transition")
async def transition_case(case_id: str, data: dict, user=Depends(get_current_user)):
    target = (data.get("to") or "").lower()
    reason = data.get("reason") or ""
    if target not in ALL_STATES:
        raise HTTPException(400, f"to must be one of {sorted(ALL_STATES)}")
    try:
        case = await state_transition(
            case_id=case_id,
            organization_id=user["organization_id"],
            target_state=target,
            actor=user,
            reason=reason,
            extra=data.get("extra"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # Sicon outbox push on every state change; Sage draft on close.
    await sicon_sync.push_case(case)
    # Mirror the state-change event as a tracking note (Phase 8 A wiring).
    last_event = await db.svc_case_events.find_one(
        {"case_id": case_id, "type": "state_change"},
        sort=[("at", -1)], projection={"_id": 0},
    )
    if last_event:
        await sicon_sync.push_event(last_event, case_reference=case.get("reference"))
    if case.get("status") == "closed":
        await sage_invoice.enqueue_invoice_for_case(case)
    # Iter 216h152 — emit a CRM activity on close so the company timeline
    # and "service revenue YTD" tile can see the service visit. Best-
    # effort, swallowed errors — never blocks the response.
    if case.get("status") == "closed":
        try:
            from utils.svc_crm_sync import emit_case_close_activity
            await emit_case_close_activity(case, user)
        except Exception as e:
            logger.warning("[svc→crm] emit_case_close_activity failed: %s", e)
    # Iter 216h155 — compliance audit. Records every state transition
    # in the immutable `audit_logs` collection so the GDPR / SOC2 path
    # has a tamper-evident answer to "who did what, when, to which
    # service case".
    try:
        await audit_log(
            action=f"svc.case.transition.{target}",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_case",
            resource_id=case_id,
            details=f"{case.get('reference', '')} → {target}"
                    + (f" · {reason}" if reason else ""),
        )
    except Exception as e:
        logger.warning("[audit] transition_case failed: %s", e)
    return _strip(case)


@router.post("/cases/{case_id}/notes")
async def add_note(case_id: str, data: dict, user=Depends(get_current_user)):
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "Note body required")
    case = await db.svc_cases.find_one({"id": case_id, **_of(user)})
    if not case:
        raise HTTPException(404, "Case not found")
    event = await append_event(
        case_id=case_id, organization_id=user["organization_id"],
        event_type="note", actor=user, body=body,
        extra={"visibility": data.get("visibility", "internal")},
    )
    await db.svc_cases.update_one({"id": case_id}, {"$set": {"updated_at": _now()}})
    # Mirror the note to Sicon as a tracking note (Phase 8 A wiring).
    await sicon_sync.push_event(event, case_reference=case.get("reference"))
    return event


# ─────────────────────────────────────────────────────────────────
# SLA helpers (lightweight Phase 1 — full policy engine in Phase 7)
# ─────────────────────────────────────────────────────────────────

# Default SLA matrix used when no policy doc is found. Hours.
_DEFAULT_SLA = {
    "p1": {"response_h": 1, "resolve_h": 4},
    "p2": {"response_h": 4, "resolve_h": 24},
    "p3": {"response_h": 8, "resolve_h": 72},
    "p4": {"response_h": 24, "resolve_h": 168},
}


async def compute_sla_targets(*, organization_id: str, priority: str, cover_type: str = "") -> dict:
    """Return (sla_response_at_iso, sla_resolve_at_iso) given priority + cover."""
    pol = await db.svc_sla_policies.find_one(
        {"organization_id": organization_id, "priority": priority, "cover_type": cover_type},
        {"_id": 0},
    )
    if not pol and cover_type:
        pol = await db.svc_sla_policies.find_one(
            {"organization_id": organization_id, "priority": priority, "cover_type": ""},
            {"_id": 0},
        )
    matrix = pol or _DEFAULT_SLA.get(priority, _DEFAULT_SLA["p3"])
    now = datetime.now(timezone.utc)
    return {
        "sla_response_at": (now + timedelta(hours=matrix["response_h"])).isoformat(),
        "sla_resolve_at": (now + timedelta(hours=matrix["resolve_h"])).isoformat(),
    }


def reference_for_org(org_id: str, seq: int) -> str:
    """Generate human-friendly case reference: SVC-<seq>."""
    return f"SVC-{seq:05d}"


async def next_reference(organization_id: str) -> str:
    """Atomically allocate the next case reference for the org."""
    res = await db.svc_counters.find_one_and_update(
        {"organization_id": organization_id, "key": "case_seq"},
        {"$inc": {"value": 1}, "$setOnInsert": {"created_at": _now()}},
        upsert=True, return_document=True,
    )
    seq = (res or {}).get("value", 1)
    return reference_for_org(organization_id, seq)


# Re-export helpers for sibling modules
__all__ = ["router", "compute_sla_targets", "next_reference"]
