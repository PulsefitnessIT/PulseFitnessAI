"""
Pulse Fitness Service Operations — Cases API.

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
    "site_name":              "sicon: SubLocationName · gymaxis_only display copy · Pulse Fitness → Sicon",
    "asset_id":               "sicon: EquipmentID · Sicon → Pulse Fitness",
    "asset_name":             "sicon: EquipmentDescription · Pulse Fitness → Sicon",
    "title":                  "sicon: ServiceCallTitle · gymaxis_only on Sage · Pulse Fitness → Sicon",
    "description":            "sicon: ServiceCallDescription · Pulse Fitness → Sicon",
    "priority":               "sicon: PriorityID (mapped via PRIORITY_CROSSWALK) · Pulse Fitness → Sicon",
    "status":                 "sicon: StatusID (mapped via STATUS_CROSSWALK) · bidirectional",
    "fault_code":             "sicon: FaultCode · Pulse Fitness → Sicon",
    "cover_type":             "sicon: CoverTypeID · sage: NominalCode (via COVER_NOMINAL) · Pulse Fitness → both",
    "case_type":              "sicon: JobTypeID (repair|ppm|install) · Pulse Fitness → Sicon",
    "customer_name":          "sicon: CustomerContactName · sage: SLCustomerAccount.Name · bidirectional",
    "customer_phone":         "sicon: CustomerContactPhone · Pulse Fitness → Sicon",
    "customer_email":         "sicon: CustomerContactEmail · Pulse Fitness → Sicon",
    "assigned_engineer_id":   "sicon: AppointmentResourceID · sage: Employee.Reference · Pulse Fitness → Sicon",
    "assigned_engineer_name": "sicon: AppointmentResourceName · Pulse Fitness → Sicon",
    "scheduled_at":           "sicon: AppointmentStartDate · Pulse Fitness → Sicon",
    "estimated_minutes":      "sicon: AppointmentDurationMinutes · Pulse Fitness → Sicon",
    "sla_response_at":        "sicon: SLAResponseTarget · Pulse Fitness → Sicon",
    "sla_resolve_at":         "sicon: SLAResolveTarget · Pulse Fitness → Sicon",
    "logged_by_id":           "sicon: CreatedBySageUserID · sage: Employee.Reference · Pulse Fitness → Sicon",
    "logged_by_name":         "sicon: CreatedByUserName · Pulse Fitness → Sicon",
    "source":                 "sicon: ServiceCallSource (phone|email|web|portal) · Pulse Fitness → Sicon",
    "allocated_parts":        "sicon: AllocatedParts[] (rolled into StockMovements per allocation) · Pulse Fitness → Sicon",
    "equipment_ids":          "sicon: CoveredEquipmentIDs[] · bidirectional",
    "equipment_serials":      "sicon: SerialNumbers[] · Pulse Fitness → Sicon",
    "contact_id":             "gymaxis_only: gym_floor_staff.id back-reference (intake cascade)",
    "quote_required":         "sage: SLQuote.Required (drives auto-draft on intake) · Pulse Fitness → Sage",
    "customer_po_number":     "sage: SLInvoice.SecondReference / CustomerPONumber · Pulse Fitness → Sage",
    # svc_case_events collection (timeline)
    "events.id":              "gymaxis_only: local event uuid",
    "events.case_id":         "gymaxis_only: FK → svc_cases.id",
    "events.type":            "sicon: NoteTypeID (mapped via NOTE_TYPE_CROSSWALK) · Pulse Fitness → Sicon",
    "events.body":             "sicon: NoteText · Pulse Fitness → Sicon",
    "events.from_state":      "sicon: PreviousStatusID · Pulse Fitness → Sicon (state_change events only)",
    "events.to_state":        "sicon: NewStatusID · Pulse Fitness → Sicon (state_change events only)",
    "events.reason":          "sicon: TrackingNoteReason · Pulse Fitness → Sicon",
    "events.actor_id":        "sicon: CreatedBySageUserID · Pulse Fitness → Sicon",
    "events.actor_name":      "sicon: CreatedByUserName · Pulse Fitness → Sicon",
    "events.at":              "sicon: CreatedAt · Pulse Fitness → Sicon",
    "events.visibility":      "gymaxis_only: internal|customer drives Sicon VisibleToCustomer flag at push time",
}

from datetime import datetime, timezone, timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex

from utils.audit import audit_log
from utils.database import db
from utils.auth import get_current_user
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, ALL_STATES, SLA_RISK_WINDOW_HOURS,
)
from routes.svc.integrations import sicon_sync, sage_invoice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc", tags=["Service Ops · Cases"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
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
    assigned: str = Query("", description="unassigned → cases with no engineer"),
    sla: str = Query("", description="at_risk | breached"),
    rtf: str = Query("", description="1 → Return-to-Fix: open jobs needing a repeat visit"),
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
    # Iter 262 — KPI drill-downs from the desk dashboard. `$in: [None, ""]`
    # also matches docs where the field is missing entirely.
    if assigned == "unassigned":
        q["assigned_engineer_id"] = {"$in": [None, ""]}
    if sla in ("at_risk", "breached"):
        now_iso = datetime.now(timezone.utc).isoformat()
        if sla == "breached":
            q["sla_resolve_at"] = {"$ne": None, "$lt": now_iso}
        else:
            risk_iso = (datetime.now(timezone.utc) + timedelta(hours=SLA_RISK_WINDOW_HOURS)).isoformat()
            q["sla_resolve_at"] = {"$gte": now_iso, "$lt": risk_iso}
        q.setdefault("status", {"$in": list(OPEN_STATES)})
    # Iter 290d — Return-to-Fix drill-down: open jobs flagged for a repeat
    # visit or parked for parts (matches the desk performance KPI + engineer
    # app). Uses `$and` so it composes with the `search` `$or` below.
    if rtf in ("1", "true", "yes"):
        q.setdefault("status", {"$in": list(OPEN_STATES)})
        q.setdefault("$and", []).append({"$or": [
            {"return_to_fix": {"$ne": None}},
            {"status": {"$in": ["paused_parts", "awaiting_parts", "paused_customer"]}},
        ]})
    if search:
        q["$or"] = [
            {"reference": safe_regex(search)},
            {"title": safe_regex(search)},
            {"customer_name": safe_regex(search)},
            {"site_name": safe_regex(search)},
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

    # Iter 249 — Sicon sync chip. One aggregate over the outbox for this
    # page's references; worst state wins: error > queued > synced > dry_run.
    # Cases that only exist via inbound Sicon sync (no outbox rows yet)
    # count as synced — Sicon is the writer of record for them.
    refs = [c.get("reference") for c in items if c.get("reference")]
    if refs:
        sync_counts: dict[str, dict[str, int]] = {}
        pipe = [
            {"$match": {
                "organization_id": q["organization_id"],
                "$or": [
                    {"payload.ServiceCallReference": {"$in": refs}},
                    {"payload.CallReference": {"$in": refs}},
                ],
            }},
            {"$project": {
                "_id": 0, "status": 1,
                "ref": {"$ifNull": ["$payload.ServiceCallReference", "$payload.CallReference"]},
            }},
            {"$group": {"_id": {"ref": "$ref", "status": "$status"}, "n": {"$sum": 1}}},
        ]
        async for row in db.svc_sicon_outbox.aggregate(pipe):
            d = sync_counts.setdefault(row["_id"]["ref"], {})
            d[row["_id"]["status"]] = d.get(row["_id"]["status"], 0) + row["n"]
        for c in items:
            counts = sync_counts.get(c.get("reference") or "", {})
            pending = counts.get("pending", 0) + counts.get("in_flight", 0)
            if counts.get("failed") or counts.get("dead_letter"):
                state = "error"
            elif pending:
                state = "queued"
            elif counts.get("succeeded"):
                state = "synced"
            elif counts.get("simulated_succeeded") or counts.get("simulated"):
                state = "dry_run"
            elif c.get("sicon_case_id") or c.get("last_sicon_sync_at"):
                state = "synced"
            else:
                state = None
            if state:
                c["sicon_sync_state"] = state
                c["sicon_sync_pending"] = pending

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


@router.get("/cases/{case_id}/crm-context")
async def case_crm_context(case_id: str, user=Depends(get_current_user)):
    """Reverse view — surface the CRM/sales context for a case so the
    Service Desk sees who owns the account, open deals and the contract
    tier. Resolves the linked CRM company by canonical ``company_id``
    (name/email fallback). Read-only; never mutates."""
    case = await db.svc_cases.find_one(
        {"id": case_id, **_of(user)},
        {"_id": 0, "company_id": 1, "customer_name": 1, "customer_email": 1, "site_postcode": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    org = (user.get("organization_id") or user.get("service_org_id"))

    company_id = case.get("company_id") or ""
    if not company_id:
        from utils.svc_crm_sync import find_company_id
        company_id = await find_company_id(
            org, name=case.get("customer_name") or "",
            email=case.get("customer_email") or "", postcode=case.get("site_postcode") or "")

    if not company_id:
        return {"linked": False}

    company = await db.crm2_companies.find_one(
        {"organization_id": org, "id": company_id},
        {"_id": 0, "id": 1, "name": 1, "type": 1, "status": 1, "sla_tier": 1,
         "account_owner_name": 1, "owner_name": 1, "phone": 1, "website": 1})
    if not company:
        return {"linked": False}

    opps = await db.crm2_opportunities.find(
        {"organization_id": org, "company_id": company_id},
        {"_id": 0, "id": 1, "name": 1, "value": 1, "stage": 1, "close_date": 1}
    ).sort("value", -1).to_list(100)
    open_deals = [o for o in opps if o.get("stage") not in ("closed_won", "closed_lost")]
    won = [o for o in opps if o.get("stage") == "closed_won"]

    contracts = await db.crm2_contracts.find(
        {"organization_id": org, "company_id": company_id},
        {"_id": 0, "id": 1, "tier": 1, "status": 1, "contract_number": 1,
         "end_date": 1, "sla": 1}
    ).sort("created_at", -1).to_list(20)
    active_contract = next((c for c in contracts if (c.get("status") or "").lower() in ("active", "signed", "live")), contracts[0] if contracts else None)

    return {
        "linked": True,
        "company_id": company_id,
        "company_name": company.get("name"),
        "account_owner": company.get("account_owner_name") or company.get("owner_name") or "",
        "account_type": company.get("type"),
        "account_status": company.get("status"),
        "contract_tier": (active_contract or {}).get("tier") or company.get("sla_tier") or "",
        "active_contract": ({
            "contract_number": active_contract.get("contract_number"),
            "status": active_contract.get("status"),
            "end_date": active_contract.get("end_date"),
        } if active_contract else None),
        "open_deal_count": len(open_deals),
        "open_pipeline_value": round(sum(float(o.get("value") or 0) for o in open_deals), 2),
        "open_deals": [
            {"id": o.get("id"), "name": o.get("name"), "value": o.get("value"),
             "stage": o.get("stage"), "close_date": o.get("close_date")}
            for o in open_deals[:5]
        ],
        "won_revenue": round(sum(float(o.get("value") or 0) for o in won), 2),
    }


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
            case_id=case_id, organization_id=(user.get("organization_id") or user.get("service_org_id")),
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
            organization_id=(user.get("organization_id") or user.get("service_org_id")),
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
        case_id=case_id, organization_id=(user.get("organization_id") or user.get("service_org_id")),
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
