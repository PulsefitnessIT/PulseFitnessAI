"""
Pulse Fitness Service Operations — Intake API.

Iter 215dn (Phase 1) · annotations backfilled iter 215eb.

Three intake channels share a single normaliser. Each call lands in
`svc_cases` as `status=new`, allocates a SVC reference, and writes a
`source` event so the timeline shows where the case originated.
"""

# Integration field manifest — see SVC_FIELD_MAPPING.md § 2.
__integration_fields__ = {
    "intake.title":                 "sicon: ServiceCallTitle · Pulse Fitness → Sicon",
    "intake.description":           "sicon: ServiceCallDescription · Pulse Fitness → Sicon",
    "intake.priority":              "sicon: PriorityID (PRIORITY_CROSSWALK) · Pulse Fitness → Sicon",
    "intake.cover_type":            "sicon: CoverTypeID · sage: NominalCode (COVER_NOMINAL) · Pulse Fitness → both",
    "intake.case_type":             "sicon: JobTypeID (repair|ppm|install) · Pulse Fitness → Sicon",
    "intake.site_id":               "sicon: SubLocationID · sage: SLDeliveryAddressID · Pulse Fitness → both",
    "intake.site_name":             "sicon: SubLocationName · Pulse Fitness → Sicon",
    "intake.site_postcode":         "sicon: SubLocationPostcode · Pulse Fitness → Sicon",
    "intake.asset_id":              "sicon: EquipmentID · Pulse Fitness → Sicon",
    "intake.asset_name":            "sicon: EquipmentDescription · Pulse Fitness → Sicon",
    "intake.equipment_ids":         "sicon: CoveredEquipmentIDs[] · Pulse Fitness → Sicon",
    "intake.equipment_serials":     "sicon: SerialNumbers[] · Pulse Fitness → Sicon",
    "intake.fault_code":            "sicon: FaultCode · Pulse Fitness → Sicon",
    "intake.customer_name":         "sicon: CustomerContactName · sage: SLCustomerAccount.Name · Pulse Fitness → both",
    "intake.customer_phone":        "sicon: CustomerContactPhone · Pulse Fitness → Sicon",
    "intake.customer_email":        "sicon: CustomerContactEmail · Pulse Fitness → Sicon",
    "intake.contact_id":            "gymaxis_only: gym_floor_staff.id back-reference",
    "intake.contract_id":           "sicon: ServiceContractID · sage: SLContract.ID · Pulse Fitness → both",
    "intake.quote_required":        "sage: SLQuote.Required (drives chargeable quote workflow) · Pulse Fitness → Sage",
    "intake.customer_po_number":    "sage: SLInvoice.SecondReference / CustomerPONumber · Pulse Fitness → Sage",
    "intake.sage_quote_outbox":     "sage: SLQuote draft persisted on svc_sage_quote_outbox · Pulse Fitness → Sage (drained by sage_outbox_worker)",
    "intake.allocated_parts":       "sicon: AllocatedParts[] (per-line StockMovement) · Pulse Fitness → Sicon",
    "intake.attachments":           "sicon: AttachmentURLs[] · Pulse Fitness → Sicon",
    "intake.source":                "sicon: ServiceCallSource (phone|email|web|portal) · Pulse Fitness → Sicon",
    "intake.source_meta":           "gymaxis_only: bridge metadata (issue_id when ops-portal mirrored)",
    "intake.organization_id":       "gymaxis_only: tenant scoping",
    "intake.logged_by_id":          "sicon: CreatedBySageUserID · Pulse Fitness → Sicon",
    "intake.logged_by_name":        "sicon: CreatedByUserName · Pulse Fitness → Sicon",
}

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from utils.auth import get_current_user
from routes.svc.cases import compute_sla_targets, next_reference
from utils.svc_state import append_event, NEW

router = APIRouter(prefix="/svc/intake", tags=["Service Ops · Intake"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_priority(p: str) -> str:
    p = (p or "").strip().lower()
    return p if p in ("p1", "p2", "p3", "p4") else "p3"


async def _create_case(*, payload: dict, source: str, user: dict) -> dict:
    org_id = (user.get("organization_id") or user.get("service_org_id"))
    if not org_id:
        raise HTTPException(403, "Organization context required")

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    if not title and not description:
        raise HTTPException(400, "title or description required")

    priority = _normalise_priority(payload.get("priority"))
    cover_type = (payload.get("cover_type") or "").lower()
    # case_type is the workflow taxonomy (Repair / PPM / Install) introduced
    # in iter 216t to separate it cleanly from cover_type (warranty / contract
    # / chargeable). Defaulting to "repair" matches the historic implicit
    # behaviour for back-compat with intake calls that omit the field.
    case_type = (payload.get("case_type") or "repair").lower()
    # Iter 220dt — extended job-type taxonomy.
    # Iter 220ec — case types are now org-configurable (Account Settings
    # → Case Types). Accept any active type the org has defined, falling
    # back to "repair" for unknown values.
    try:
        from routes.svc.case_types import active_slugs as _active_case_type_slugs
        _allowed = await _active_case_type_slugs(org_id)
    except Exception:
        _allowed = {"repair", "ppm", "install", "inspection", "callout", "audit"}
    if case_type not in _allowed:
        case_type = "repair"

    sla = await compute_sla_targets(
        organization_id=org_id, priority=priority, cover_type=cover_type,
    )
    reference = await next_reference(org_id)

    case = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "reference": reference,
        "status": NEW,
        "priority": priority,
        "cover_type": cover_type,
        "case_type": case_type,
        "title": title or description[:80],
        "description": description,
        "fault_code": payload.get("fault_code") or "",
        "fault_category": payload.get("fault_category") or "",
        # Iter — carry the Operations "Log a fault" AI Triage + severity onto
        # the case so the engineer / service desk see the full context that
        # was logged (rendered behind a "View AI Triage" button in the app).
        "ai_triage": payload.get("ai_triage") or "",
        "fault_severity": payload.get("fault_severity") or "",
        "asset_id": payload.get("asset_id") or "",
        "asset_name": payload.get("asset_name") or "",
        # Multi-equipment selection (iter 215dq) — operators can attach
        # several machines to one case (e.g. site-wide outage). Maps to
        # Sicon ServiceCall.EquipmentIDs[] per SVC_FIELD_MAPPING.md §2.
        "equipment_ids": list(payload.get("equipment_ids") or []),
        "equipment_serials": list(payload.get("equipment_serials") or []),
        # Pre-allocated parts (Phase 3 intake enhancement). Operators
        # triage at log time so the engineer arrives loaded.
        "allocated_parts": list(payload.get("allocated_parts") or []),
        "site_id": payload.get("site_id") or "",
        "site_name": payload.get("site_name") or "",
        "site_postcode": payload.get("site_postcode") or "",
        "contract_id": payload.get("contract_id") or "",
        "contact_id": payload.get("contact_id") or "",
        "customer_name": payload.get("customer_name") or "",
        "customer_email": payload.get("customer_email") or "",
        "customer_phone": payload.get("customer_phone") or "",
        # Site Staff Shared Login — who actually logged the fault so the
        # engineer app + supplier portal can show their role and a
        # click-to-call / click-to-email button.
        "reporter_job_title": payload.get("reporter_job_title") or "",
        "logged_via_shared_login": bool(payload.get("logged_via_shared_login") or False),
        # Chargeable workflow extras (cascade step 5) — captured at intake when
        # the operator confirms the case is out of contract / warranty cover.
        "quote_required": bool(payload.get("quote_required") or False),
        "customer_po_number": (payload.get("customer_po_number") or "").strip(),
        "attachments": payload.get("attachments") or [],
        # Iter 220dt — Serial-unknown escape hatch. When the
        # operator / customer can't read the serial plate (rubbed
        # off, behind cladding, never had one) the case carries a
        # `capture_serial_required` flag so the engineer's app
        # raises a "Snap the serial plate on visit 1" task without
        # blocking intake.
        "capture_serial_required": bool(payload.get("capture_serial_required") or False),
        "capture_serial_reason": (payload.get("capture_serial_reason") or "").strip() or None,
        "tags": payload.get("tags") or [],
        "required_skills": list(payload.get("required_skills") or []),
        "source": source,
        # Iter 220cp — cross-module channel unification. The engineer
        # app reads ``intake_channel``; the operations portal / service
        # desk write ``source``. Mirror the value so both modules speak
        # the same language and the engineer detail page shows the right
        # "Logged via" pill regardless of which entrypoint created the
        # case. Engineer-self-create (`independence.py::jobs_self_create`)
        # is the one path that sets ``intake_channel`` directly; it is
        # not affected by this change.
        "intake_channel": source,
        "source_meta": payload.get("source_meta") or {},
        "logged_by_id": user.get("id"),
        "logged_by_name": user.get("full_name") or user.get("email") or "",
        "assigned_engineer_id": "",
        "assigned_engineer_name": "",
        "scheduled_at": None,
        "estimated_minutes": payload.get("estimated_minutes") or 0,
        "sla_response_at": sla["sla_response_at"],
        "sla_resolve_at": sla["sla_resolve_at"],
        "sla_paused_at": None,
        "closed_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Iter 220ea·26 (G1) — stamp the canonical CRM (v2) company id so the
    # case, CRM timeline, Sage link and engineer book all share one spine.
    # Operator-picked id wins; otherwise best-effort match by name/email.
    case["company_id"] = (payload.get("company_id") or "").strip()
    if not case["company_id"]:
        try:
            from utils.svc_crm_sync import find_company_id
            case["company_id"] = await find_company_id(
                org_id,
                name=case.get("customer_name") or "",
                email=case.get("customer_email") or "",
                postcode=case.get("site_postcode") or "",
            )
        except Exception:
            case["company_id"] = ""
    await db.svc_cases.insert_one(case)

    # Seed timeline with the intake event so it's never empty.
    await append_event(
        case_id=case["id"], organization_id=org_id,
        event_type="intake", actor=user,
        body=f"Case logged via {source}",
        extra={
            "source": source,
            "priority": priority,
            "fault_code": case["fault_code"],
            "site_name": case["site_name"],
        },
    )

    # Iter 215ed — chargeable + quote_required cases auto-draft a Sage SLQuote
    # on `svc_sage_quote_outbox` so the operator can hand the customer a quote
    # without leaving the Service Desk. The outbox row drains via the same
    # worker that already handles invoice / PO outboxes when Sage credentials
    # arrive.
    quote_outbox: dict | None = None
    if case["cover_type"] == "chargeable" and case.get("quote_required"):
        try:
            from utils.svc_crm_sync import resolve_sage_customer_id
            sage_customer_id = await resolve_sage_customer_id(
                org_id,
                name=case.get("customer_name") or "",
                email=case.get("customer_email") or "",
                company_id=case.get("company_id") or "",
            )
            from routes.svc.integrations.sage_invoice import enqueue_quote_for_case
            quote_outbox = await enqueue_quote_for_case(
                case,
                sage_customer_id=sage_customer_id,
                customer_po_number=case.get("customer_po_number") or "",
            )
            if quote_outbox:
                await append_event(
                    case_id=case["id"], organization_id=org_id,
                    event_type="note", actor=user,
                    body=f"Sage SLQuote drafted on outbox · ref {case.get('reference')}",
                    extra={
                        "kind": "quote_drafted",
                        "outbox_id": quote_outbox.get("id"),
                        "customer_po_number": case.get("customer_po_number") or "",
                        "visibility": "internal",
                    },
                )
        except Exception as e:
            # Best-effort — never block the case write.
            import logging as _log
            _log.getLogger(__name__).warning(
                "intake quote auto-draft failed for %s: %s", case.get("id"), e,
            )

    case.pop("_id", None)
    if quote_outbox is not None:
        case["sage_quote_outbox"] = {
            "id": quote_outbox.get("id"),
            "status": quote_outbox.get("status"),
            "created_at": quote_outbox.get("created_at"),
            "customer_po_number": quote_outbox.get("customer_po_number"),
        }

    # Iter 216u (Phase 2) — best-effort AI engineer recommendation on every
    # new case. Stamps `recommended_engineer_id/name/score/reason` so the
    # service desk UI can show a one-click "Auto-assign" suggestion. Never
    # blocks the case write; failures are silent.
    try:
        from routes.svc.scheduler import _score_engineers_for_case  # type: ignore
        suggestions = await _score_engineers_for_case(case, organization_id=org_id, limit=1)
        top = suggestions[0] if suggestions else None
        if top:
            await db.svc_cases.update_one(
                {"id": case["id"]},
                {"$set": {
                    "recommended_engineer_id": top.get("engineer_id", ""),
                    "recommended_engineer_name": top.get("engineer_name", ""),
                    "recommended_engineer_score": top.get("score", 0),
                    "recommended_engineer_reason": top.get("reason", ""),
                }},
            )
            case["recommended_engineer_id"] = top.get("engineer_id", "")
            case["recommended_engineer_name"] = top.get("engineer_name", "")
            case["recommended_engineer_score"] = top.get("score", 0)
            case["recommended_engineer_reason"] = top.get("reason", "")
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).info(
            "intake auto-assign suggestion failed for %s: %s", case.get("id"), exc,
        )

    return case


# ─────────────────────────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────────────────────────

@router.post("/portal")
async def intake_portal(payload: dict, user=Depends(get_current_user)):
    """Customer self-serve portal submission."""
    return await _create_case(payload=payload, source="portal", user=user)


@router.post("/phone")
async def intake_phone(payload: dict, user=Depends(get_current_user)):
    """Service-desk operator logs a phoned-in case."""
    return await _create_case(payload=payload, source="phone", user=user)


@router.post("/email")
async def intake_email(payload: dict, user=Depends(get_current_user)):
    """Email-to-case stub — Phase 1 manual; mailbox poller in Phase 7."""
    return await _create_case(payload=payload, source="email", user=user)
