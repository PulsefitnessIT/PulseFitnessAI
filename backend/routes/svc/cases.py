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
        # Iter — on operator sign-off (close), publish the calibration
        # certificate into the customer's Documents so they can pull audit
        # evidence from their own Operations Portal. Best-effort.
        if case.get("calibration_captured"):
            try:
                from utils.calibration_cert_publish import publish_calibration_certificate
                await publish_calibration_certificate(case)
            except Exception as e:
                logger.warning("[calib-cert] publish on close failed: %s", e)
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


# ── Iter 292 — GymAxis parity: case lifecycle timeline (cost-to-serve) ──
_CLOSED_STATES = {"closed", "invoiced", "resolved", "completed"}


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


@router.get("/cases/{case_id}/lifecycle")
async def case_lifecycle(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = _strip(await db.svc_cases.find_one({"id": case_id, **of}))
    if not case:
        raise HTTPException(404, "Case not found")

    # ── Asset ──
    asset = None
    if case.get("asset_id"):
        asset = await db.equipment.find_one(
            {"id": case["asset_id"]},
            {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1,
             "category": 1, "serial_number": 1, "status": 1, "site_name": 1, "location": 1},
        )

    # ── Labour (svc_time_entries) ──
    total_mins = on_site_mins = 0
    async for e in db.svc_time_entries.find({**of, "case_id": case_id}, {"_id": 0, "category": 1, "duration_minutes": 1}):
        m = int(e.get("duration_minutes") or 0)
        total_mins += m
        if (e.get("category") or "on_site") == "on_site":
            on_site_mins += m
    labour_hours = round(total_mins / 60.0, 2)

    # ── Mileage (svc_mileage_entries) ──
    miles = 0.0
    try:
        async for mm in db.svc_mileage_entries.find({**of, "case_id": case_id}, {"_id": 0, "miles": 1}):
            miles += float(mm.get("miles") or 0)
    except Exception:  # noqa: BLE001
        miles = 0.0

    # ── Parts (allocated on the case) ──
    parts = list(case.get("allocated_parts") or [])
    parts_count = sum(int(p.get("qty") or p.get("quantity") or 1) for p in parts)

    # ── Invoice (latest for this case) ──
    inv = await db.svc_engineer_invoices.find_one(
        {"case_id": case_id, **of},
        {"_id": 0, "id": 1, "reference": 1, "number": 1, "status": 1, "total": 1,
         "currency": 1, "sent_at": 1, "paid_at": 1, "created_at": 1, "lines": 1},
        sort=[("created_at", -1)],
    )
    inv = inv or {}

    # ── Timestamps & time-to-resolve ──
    created_at = case.get("created_at")
    scheduled_at = case.get("scheduled_at")
    status = case.get("status")
    resolved = status in _CLOSED_STATES
    resolved_at = None
    if resolved:
        ev = await db.svc_case_events.find_one(
            {"case_id": case_id, **of, "type": "state_change"},
            {"_id": 0, "at": 1}, sort=[("at", -1)],
        )
        resolved_at = (ev or {}).get("at") or case.get("updated_at")
    ttr_hours = None
    c0, c1 = _parse_dt(created_at), _parse_dt(resolved_at)
    if c0 and c1 and c1 >= c0:
        ttr_hours = round((c1 - c0).total_seconds() / 3600.0, 1)

    paid = inv.get("status") == "paid"
    currency = inv.get("currency") or "£"

    # ── Cost-to-serve breakdown (from invoice lines) ──
    # Invoice lines carry a `kind` (labour / travel / part) + `line_total`,
    # so we can split the job cost into labour vs parts vs travel without
    # any rate guessing. Empty when there's no invoice yet.
    _KIND_BUCKET = {"labour": "labour", "travel": "travel", "part": "parts", "parts": "parts"}
    cost = {"labour": 0.0, "parts": 0.0, "travel": 0.0, "other": 0.0}
    for ln in (inv.get("lines") or []):
        kind = (ln.get("kind") or "other").lower()
        bucket = _KIND_BUCKET.get(kind, "other")
        try:
            cost[bucket] += float(ln.get("line_total") or 0)
        except (TypeError, ValueError):
            pass
    cost = {k: round(v, 2) for k, v in cost.items()}
    cost_total = round(sum(cost.values()), 2)

    # ── Internal cost basis → margin (best-effort, degrades gracefully) ──
    # Charge (above) comes from the invoice. Internal cost is sourced from
    # the parts catalogue (`parts.cost`) and the assigned engineer's pay
    # rate (`payout.labour_rate_gbp`). Margin is reported ONLY over the
    # value-add components we actually know the cost of — never faked.
    part_skus = [(p.get("part_sku") or p.get("sku")) for p in parts]
    part_skus = [s for s in part_skus if s]
    sku_cost: dict[str, float] = {}
    if part_skus:
        async for pr in db.parts.find({**of, "sku": {"$in": part_skus}}, {"_id": 0, "sku": 1, "cost": 1}):
            sku_cost[pr["sku"]] = float(pr.get("cost") or 0)
    parts_cost = 0.0
    parts_cost_known = False
    for p in parts:
        sku = p.get("part_sku") or p.get("sku")
        if sku in sku_cost:
            parts_cost += sku_cost[sku] * int(p.get("qty") or p.get("quantity") or 1)
            parts_cost_known = True

    labour_cost = 0.0
    labour_cost_known = False
    eng_id = case.get("assigned_engineer_id")
    if eng_id and labour_hours > 0:
        eng = await db.svc_engineers.find_one(
            {"id": eng_id}, {"_id": 0, "payout": 1, "labour_rate_gbp": 1},
        ) or {}
        pay_rate = (eng.get("payout") or {}).get("labour_rate_gbp") or eng.get("labour_rate_gbp")
        if pay_rate:
            labour_cost = round(float(pay_rate) * labour_hours, 2)
            labour_cost_known = True

    # Build margin over known value-add components (labour + parts). Travel
    # is a reimbursable pass-through (HMRC mileage) — excluded from margin.
    internal_cost = {
        "labour": round(labour_cost, 2) if labour_cost_known else None,
        "parts": round(parts_cost, 2) if parts_cost_known else None,
    }
    known_charge = known_cost = 0.0
    missing_cost: list[str] = []
    if cost["labour"] > 0:
        if labour_cost_known:
            known_charge += cost["labour"]; known_cost += labour_cost
        else:
            missing_cost.append("labour")
    if cost["parts"] > 0:
        if parts_cost_known:
            known_charge += cost["parts"]; known_cost += parts_cost
        else:
            missing_cost.append("parts")
    has_basis = labour_cost_known or parts_cost_known
    margin_total = round(known_charge - known_cost, 2) if has_basis else None
    margin_pct = round(margin_total / known_charge * 100, 1) if (has_basis and known_charge > 0) else None
    cost_basis = "none" if not has_basis else ("complete" if not missing_cost else "partial")
    margin = {
        "internal_cost": internal_cost,
        "internal_cost_total": round(known_cost, 2) if has_basis else None,
        "margin_total": margin_total,
        "margin_pct": margin_pct,
        "cost_basis": cost_basis,
        "missing_cost": missing_cost,
    }

    def stage(key, label, done, at=None, detail=None, meta=None):
        return {"key": key, "label": label, "done": bool(done), "at": at, "detail": detail, "meta": meta or {}}

    stages = [
        stage("asset", "Asset", bool(asset or case.get("asset_name")), None,
              (asset or {}).get("name") or case.get("asset_name") or "—",
              {"asset_id": case.get("asset_id"),
               "manufacturer": (asset or {}).get("manufacturer"), "model": (asset or {}).get("model"),
               "category": (asset or {}).get("category"), "serial": (asset or {}).get("serial_number"),
               "site": case.get("site_name")}),
        stage("fault", "Fault logged", True, created_at,
              case.get("title") or case.get("fault_code") or "Fault reported",
              {"fault_code": case.get("fault_code"), "fault_category": case.get("fault_category"),
               "priority": case.get("priority"), "source": case.get("source")}),
        stage("dispatch", "Engineer dispatched", bool(case.get("assigned_engineer_id")), scheduled_at,
              case.get("assigned_engineer_name") or ("Engineer assigned" if case.get("assigned_engineer_id") else "Unassigned"),
              {"scheduled_at": scheduled_at}),
        stage("onsite", "On-site & labour", on_site_mins > 0, None,
              f"{labour_hours} h logged" if total_mins > 0 else "No time logged yet",
              {"labour_hours": labour_hours, "miles": round(miles, 1)}),
        stage("parts", "Parts fitted", len(parts) > 0, None,
              f"{parts_count} part(s)" if parts else "No parts used",
              {"parts": [{"id": p.get("id"),
                          "name": (p.get("name") or p.get("part_name") or p.get("sku") or p.get("part_sku") or "Part"),
                          "sku": p.get("part_sku") or p.get("sku"),
                          "qty": int(p.get("qty") or p.get("quantity") or 1),
                          "source": p.get("source"),
                          "fulfilled": bool(p.get("fulfilled"))} for p in parts][:12]}),
        stage("resolution", "Resolved", resolved, resolved_at,
              (f"Resolved in {ttr_hours} h" if ttr_hours is not None else (status or "")),
              {"status": status, "time_to_resolve_hours": ttr_hours}),
        stage("invoice", "Invoiced", bool(inv), inv.get("sent_at") or inv.get("created_at"),
              (f"{currency}{inv.get('total') or 0}" if inv else "Not invoiced"),
              {"invoice_id": inv.get("id"), "reference": inv.get("reference") or inv.get("number"),
               "status": inv.get("status"), "total": inv.get("total")}),
        stage("paid", "Paid", paid, inv.get("paid_at"),
              "Paid" if paid else (inv.get("status") or "Awaiting invoice"), {}),
    ]

    return {
        "case_id": case_id,
        "reference": case.get("reference"),
        "status": status,
        "summary": {
            "time_to_resolve_hours": ttr_hours,
            "labour_hours": labour_hours,
            "miles": round(miles, 1),
            "parts_count": parts_count,
            "invoice_id": inv.get("id"),
            "invoice_total": inv.get("total"),
            "invoice_currency": currency,
            "invoice_status": inv.get("status"),
            "paid": paid,
            "cost_breakdown": cost,
            "cost_total": cost_total,
            "margin": margin,
        },
        "stages": stages,
    }


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




async def _build_calibration_certificate(case_id: str, of: dict):
    """Shared: build the calibration certificate PDF for a case. Returns
    (pdf_bytes, case, calibration, filename). Raises 404 if none recorded."""
    from utils.calibration_certificate_pdf import build_calibration_certificate_pdf
    cal = await db.svc_case_calibrations.find_one(
        {"case_id": case_id, **of}, {"_id": 0}, sort=[("created_at", -1)])
    if not cal:
        raise HTTPException(404, "No calibration recorded for this case")
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0}) or {}
    pdf = build_calibration_certificate_pdf(
        case_ref=case.get("reference") or case_id,
        customer_name=case.get("customer_name") or "",
        site_name=case.get("site_name") or "",
        equipment_name=cal.get("equipment_name") or case.get("asset_name") or "",
        service_type=cal.get("service_type") or case.get("service_type") or "Calibration",
        readings=cal.get("readings") or [],
        overall_result=cal.get("overall_result") or "",
        engineer_name=cal.get("engineer_name") or "",
        issued_at=(cal.get("created_at") or "")[:16].replace("T", " "),
        notes=cal.get("notes") or "",
        signature_data_url=cal.get("signature") or None,
    )
    fname = f"calibration-{case.get('reference') or case_id}.pdf"
    return pdf, case, cal, fname


@router.get("/cases/{case_id}/calibration/certificate.pdf")
async def case_calibration_certificate(case_id: str, user=Depends(get_current_user)):
    """Office/manager download of the calibration audit certificate."""
    from fastapi.responses import Response
    pdf, _case, _cal, fname = await _build_calibration_certificate(case_id, _of(user))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


@router.post("/cases/{case_id}/calibration/certificate/email")
async def case_calibration_certificate_email(case_id: str, data: dict | None = None,
                                             user=Depends(get_current_user)):
    """Email the calibration certificate to the customer (or override `to`).

    Body (optional): {to: 'name@domain.com', note: 'Optional cover note'}
    """
    import base64
    from utils.email import send_email
    of = _of(user)
    pdf, case, cal, fname = await _build_calibration_certificate(case_id, of)
    body_data = data or {}
    to = ((body_data.get("to") or "").strip() or (case.get("customer_email") or "").strip()).lower()
    if not to or "@" not in to:
        raise HTTPException(400, "Customer email is missing. Provide `to` or set customer_email on the case.")
    note = (body_data.get("note") or "").strip()
    org = await db.organizations.find_one({"id": of["organization_id"]}, {"_id": 0, "name": 1}) or {}
    org_name = org.get("name") or "Your service team"
    customer_first = (case.get("customer_name") or "there").split()[0] if case.get("customer_name") else "there"
    verdict = (cal.get("overall_result") or "").upper()
    subject = f"Calibration certificate · {case.get('reference', case_id[:8])}"
    note_html = (
        f"<p style='margin:0 0 16px 0;color:#1f2937;font-size:14px;line-height:1.6'>{note}</p>"
        if note else ""
    )
    html = (
        f"<div style='font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px'>"
        f"<h2 style='color:#0f172a;font-size:18px;margin:0 0 12px 0'>Hi {customer_first},</h2>"
        f"<p style='color:#1f2937;font-size:14px;line-height:1.6;margin:0 0 16px 0'>"
        f"Please find attached the calibration certificate for "
        f"<b>{case.get('reference', '')}</b>"
        + (f" ({cal.get('equipment_name')})" if cal.get('equipment_name') else "")
        + f". Overall result: <b>{verdict or '—'}</b>. This certificate is provided as audit evidence "
        f"of the calibration checks performed at the visit.</p>"
        f"{note_html}"
        f"<p style='color:#64748B;font-size:13px;line-height:1.5;margin:24px 0 0 0'>"
        f"Thanks,<br/><b>{org_name}</b></p>"
        f"</div>"
    )
    attachments = [{"filename": fname, "content": base64.b64encode(pdf).decode("ascii")}]
    ok = await send_email(
        to=to, subject=subject, html=html, attachments=attachments,
        organization_id=of["organization_id"], category="service",
    )
    if not ok:
        raise HTTPException(502, "Email send failed — check sender domain verification.")
    now_iso = _now()
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {"calibration_cert_sent_at": now_iso, "calibration_cert_sent_to": to, "updated_at": now_iso}},
    )
    try:
        await append_event(
            case_id=case_id, organization_id=of["organization_id"],
            event_type="note", actor=user,
            body=f"Calibration certificate emailed to {to}",
            extra={"kind": "calibration_cert_emailed", "to": to},
        )
    except Exception as e:
        logger.warning(f"calibration-cert: failed to append audit event: {e!r}")
    return {"ok": True, "to": to, "sent_at": now_iso, "filename": fname}
