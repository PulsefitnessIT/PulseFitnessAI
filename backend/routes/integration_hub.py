"""
Pulse Fitness AI — Integration Hub (Event Bus)
==========================================
Central event routing layer that connects CRM, Service Portal, Finance, and AI systems.
All cross-system events flow through here for logging, routing, retry, and monitoring.

Architecture:
  Service Portal → Event Bus → CRM (case, contact, opportunity)
  CRM (deal won) → Event Bus → Sage 200 (sales order)
  Sage 200 (invoice) → Event Bus → CRM (financial status)
  Engineer (BER flag) → Event Bus → CRM (replacement opportunity)
  Any system → Event Bus → Audit Log + Monitoring
"""

from fastapi import APIRouter, Depends, HTTPException
from utils.security_plus import safe_regex
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/integration-hub", tags=["Integration Hub"])
logger = logging.getLogger(__name__)


# ── Event Data Model ──────────────────────────────────────────────

@dataclass
class IntegrationEvent:
    event_type: str
    source_system: str
    target_system: str
    entity_type: str
    entity_id: str
    payload: dict
    organization_id: str = ""
    triggered_by: str = "system"
    priority: str = "normal"


# ── Core Event Bus ────────────────────────────────────────────────

# Kwargs accepted by publish_event — mirrors IntegrationEvent dataclass fields.
_EVENT_FIELDS = (
    "event_type", "source_system", "target_system",
    "entity_type", "entity_id", "payload",
    "organization_id", "triggered_by", "priority",
)


async def publish_event(**kwargs):
    """Publish an event to the integration hub via keyword arguments.

    For new code prefer `publish(IntegrationEvent(...))` — this wrapper exists so
    existing callers can keep their readable keyword-based callsites without
    inflating the signature here.
    """
    unknown = set(kwargs) - set(_EVENT_FIELDS)
    if unknown:
        raise TypeError(f"publish_event got unexpected kwargs: {sorted(unknown)}")
    evt = IntegrationEvent(**{k: kwargs[k] for k in _EVENT_FIELDS if k in kwargs})
    return await _publish(evt)


async def publish(event: IntegrationEvent):
    """Publish a pre-built IntegrationEvent (preferred for new code)."""
    return await _publish(event)


async def _publish(evt: IntegrationEvent) -> dict:
    """Internal publish: store event and route to handler."""
    event = {
        **asdict(evt),
        "id": str(uuid.uuid4()),
        "status": "pending",
        "attempts": 0,
        "max_attempts": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": None,
        "error": None,
    }
    await db.integration_events.insert_one(event)
    logger.info(f"Event published: {evt.event_type} [{evt.source_system}→{evt.target_system}] entity={evt.entity_type}/{evt.entity_id}")
    result = await _route_event(event)
    return {k: v for k, v in {**event, **result}.items() if k != "_id"}


async def _route_event(event: dict) -> dict:
    """Route event to the appropriate handler based on event_type."""
    handlers = {
        # Service Portal → CRM
        "service_issue_created": _handle_service_to_crm_case,
        "service_issue_updated": _handle_service_update_crm,
        "engineer_ber_flagged": _handle_ber_to_opportunity,
        # CRM → Finance
        "deal_closed_won": _handle_deal_won_to_order,
        "quote_accepted": _handle_quote_to_order,
        # Finance → CRM
        "invoice_created": _handle_invoice_to_crm,
        "payment_received": _handle_payment_to_crm,
        "account_on_hold": _handle_account_hold_alert,
        # CRM → Service Portal
        "contract_activated": _handle_contract_to_service,
        # Asset lifecycle
        "asset_end_of_life": _handle_asset_eol_opportunity,
    }

    handler = handlers.get(event["event_type"])
    if not handler:
        await _mark_event(event["id"], "skipped", error=f"No handler for {event['event_type']}")
        return {"routed": False}

    try:
        await handler(event)
        await _mark_event(event["id"], "completed")
        return {"routed": True, "status": "completed"}
    except Exception as e:
        attempts = event.get("attempts", 0) + 1
        status = "failed" if attempts >= event.get("max_attempts", 3) else "retry"
        await _mark_event(event["id"], status, error=str(e), attempts=attempts)
        logger.error(f"Event {event['id']} handler failed: {e}")
        return {"routed": True, "status": status, "error": str(e)}


async def _mark_event(event_id: str, status: str, error: str = None, attempts: int = None):
    update = {"status": status, "processed_at": datetime.now(timezone.utc).isoformat()}
    if error:
        update["error"] = error
    if attempts is not None:
        update["attempts"] = attempts
    await db.integration_events.update_one({"id": event_id}, {"$set": update})


# ── Event Handlers ────────────────────────────────────────────────

async def _handle_service_to_crm_case(event: dict):
    """Service Portal issue → CRM Service Case + linked company/contact."""
    payload = event["payload"]
    org_id = event["organization_id"]
    now = datetime.now(timezone.utc).isoformat()

    # Look up or create the company in CRM
    company_id = None
    if payload.get("organization_name"):
        company = await db.crm2_companies.find_one(
            {"organization_id": org_id, "name": safe_regex(payload["organization_name"])},
            {"_id": 0, "id": 1}
        )
        if company:
            company_id = company["id"]

    # Create CRM service case
    case = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "title": payload.get("title", "Service Request"),
        "description": payload.get("description", ""),
        "status": "open", "priority": payload.get("priority", "medium"),
        "company_id": company_id or "",
        "contact_id": payload.get("contact_id", ""),
        "source": "service_portal",
        "source_issue_id": payload.get("issue_id", ""),
        "equipment_id": payload.get("equipment_id", ""),
        "equipment_name": payload.get("equipment_name", ""),
        "created_by": event["triggered_by"],
        "created_at": now, "updated_at": now,
    }
    await db.crm2_service_cases.insert_one(case)

    # Log activity in CRM
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "type": "system", "subject": f"Service case created from portal: {case['title']}",
        "body": f"Issue #{payload.get('issue_id', '')} logged via Self-Service Portal",
        "company_id": company_id or "",
        "owner_id": "system", "owner_name": "System",
        "created_at": now,
    })


async def _handle_service_update_crm(event: dict):
    """Service Portal issue update → sync to CRM case."""
    payload = event["payload"]
    source_id = payload.get("issue_id", "")
    if source_id:
        await db.crm2_service_cases.update_one(
            {"source_issue_id": source_id},
            {"$set": {"status": payload.get("status", "open"), "updated_at": datetime.now(timezone.utc).isoformat()}}
        )


async def _handle_ber_to_opportunity(event: dict):
    """Engineer flags 'Beyond Economical Repair' → auto-create CRM opportunity."""
    payload = event["payload"]
    org_id = event["organization_id"]
    now = datetime.now(timezone.utc).isoformat()

    opp = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "title": f"Replacement: {payload.get('equipment_name', 'Equipment')}",
        "stage": "lead", "value": payload.get("estimated_value", 0),
        "probability": 60,
        "company_id": payload.get("company_id", ""),
        "company_name": payload.get("company_name", ""),
        "contact_id": payload.get("contact_id", ""),
        "source": "engineer_ber",
        "source_case_id": payload.get("case_id", ""),
        "next_step": "Contact customer about replacement options",
        "created_by": event["triggered_by"],
        "owner_id": "", "owner_name": "",
        "weighted_value": 0, "close_date": "",
        "created_at": now, "updated_at": now,
        "stage_history": [{"stage": "lead", "entered_at": now, "by": "system"}],
    }
    await db.crm2_opportunities.insert_one(opp)

    # Log activity
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "type": "system",
        "subject": f"Replacement opportunity auto-created: {opp['title']}",
        "body": f"Engineer flagged {payload.get('equipment_name', '')} as Beyond Economical Repair. Case #{payload.get('case_id', '')}",
        "opportunity_id": opp["id"], "company_id": opp["company_id"],
        "owner_id": "system", "owner_name": "System",
        "created_at": now,
    })
    logger.info(f"BER → Opportunity created: {opp['id']}")


async def _handle_deal_won_to_order(event: dict):
    """CRM deal closed won → create sales order (for Sage 200 when connected)."""
    payload = event["payload"]
    org_id = event["organization_id"]
    now = datetime.now(timezone.utc).isoformat()

    order = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "order_number": f"SO-{str(uuid.uuid4())[:6].upper()}",
        "opportunity_id": payload.get("opportunity_id", ""),
        "company_id": payload.get("company_id", ""),
        "company_name": payload.get("company_name", ""),
        "contact_id": payload.get("contact_id", ""),
        "value": payload.get("value", 0),
        "status": "pending_sync",
        "sage_synced": False, "sage_order_id": None,
        "lines": payload.get("lines", []),
        "created_by": event["triggered_by"],
        "created_at": now, "updated_at": now,
    }
    await db.crm2_orders.insert_one(order)

    # Update opportunity with order reference
    if payload.get("opportunity_id"):
        await db.crm2_opportunities.update_one(
            {"id": payload["opportunity_id"]},
            {"$set": {"order_id": order["id"], "order_number": order["order_number"]}}
        )
    logger.info(f"Deal Won → Order created: {order['order_number']}")


async def _handle_quote_to_order(event: dict):
    """Quote accepted → create order."""
    await _handle_deal_won_to_order(event)


async def _handle_invoice_to_crm(event: dict):
    """Sage invoice → CRM financial record."""
    payload = event["payload"]
    org_id = event["organization_id"]
    now = datetime.now(timezone.utc).isoformat()

    await db.crm2_invoices.update_one(
        {"sage_invoice_id": payload.get("sage_invoice_id")},
        {"$set": {
            "organization_id": org_id,
            "sage_invoice_id": payload.get("sage_invoice_id"),
            "invoice_number": payload.get("invoice_number", ""),
            "company_id": payload.get("company_id", ""),
            "opportunity_id": payload.get("opportunity_id", ""),
            "amount": payload.get("amount", 0),
            "status": payload.get("status", "outstanding"),
            "due_date": payload.get("due_date", ""),
            "updated_at": now,
        }, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
        upsert=True,
    )


async def _handle_payment_to_crm(event: dict):
    """Payment received → update CRM financial status."""
    payload = event["payload"]
    if payload.get("sage_invoice_id"):
        await db.crm2_invoices.update_one(
            {"sage_invoice_id": payload["sage_invoice_id"]},
            {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat(), "payment_amount": payload.get("amount", 0)}}
        )
    if payload.get("company_id"):
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()), "organization_id": event["organization_id"],
            "type": "system", "subject": f"Payment received: £{payload.get('amount', 0):,.2f}",
            "company_id": payload["company_id"],
            "owner_id": "system", "owner_name": "System",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })


async def _handle_account_hold_alert(event: dict):
    """Account on hold in Sage → alert CRM users."""
    payload = event["payload"]
    org_id = event["organization_id"]
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "type": "system", "subject": f"ALERT: Account on hold — {payload.get('company_name', '')}",
        "body": f"Reason: {payload.get('reason', 'Financial hold')}. All sales activities should be reviewed.",
        "company_id": payload.get("company_id", ""),
        "priority": "high",
        "owner_id": "system", "owner_name": "System",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _handle_contract_to_service(event: dict):
    """Contract activated → set up service SLA in portal."""
    payload = event["payload"]
    org_id = event["organization_id"]
    await db.service_contracts.update_one(
        {"contract_id": payload.get("contract_id")},
        {"$set": {
            "organization_id": org_id,
            "company_id": payload.get("company_id", ""),
            "sla_tier": payload.get("sla_tier", "standard"),
            "start_date": payload.get("start_date", ""),
            "end_date": payload.get("end_date", ""),
            "assets": payload.get("asset_ids", []),
            "active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "$setOnInsert": {"contract_id": payload.get("contract_id"), "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _handle_asset_eol_opportunity(event: dict):
    """Asset approaching end of life → auto-create renewal opportunity."""
    payload = event["payload"]
    org_id = event["organization_id"]
    now = datetime.now(timezone.utc).isoformat()
    opp = {
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "title": f"Renewal: {payload.get('asset_name', 'Equipment')}",
        "stage": "lead", "value": payload.get("estimated_value", 0),
        "probability": 40, "source": "asset_lifecycle",
        "company_id": payload.get("company_id", ""),
        "company_name": payload.get("company_name", ""),
        "next_step": "Review asset condition and propose replacement/renewal",
        "created_by": "system", "owner_id": "", "owner_name": "",
        "weighted_value": 0, "close_date": "",
        "created_at": now, "updated_at": now,
        "stage_history": [{"stage": "lead", "entered_at": now, "by": "system"}],
    }
    await db.crm2_opportunities.insert_one(opp)


# ── API Endpoints ─────────────────────────────────────────────────

@router.get("/events")
async def list_events(
    status: str = "", source: str = "", limit: int = 50, skip: int = 0,
    user=Depends(get_crm_user),
):
    """List integration events with filtering."""
    query = {"organization_id": user.get("organization_id", "")}
    if status:
        query["status"] = status
    if source:
        query["source_system"] = source
    events = await db.integration_events.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.integration_events.count_documents(query)
    return {"events": events, "total": total}


@router.post("/events/{event_id}/retry")
async def retry_event(event_id: str, user=Depends(get_crm_user)):
    """Manually retry a failed event."""
    event = await db.integration_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Event not found")
    if event["status"] not in ("failed", "retry"):
        raise HTTPException(400, "Only failed events can be retried")
    event["attempts"] = 0
    result = await _route_event(event)
    return {"success": True, **result}


@router.get("/health")
async def integration_health(user=Depends(get_crm_user)):
    """Integration health dashboard data."""
    org_id = user.get("organization_id", "")
    base = {"organization_id": org_id}

    total = await db.integration_events.count_documents(base)
    completed = await db.integration_events.count_documents({**base, "status": "completed"})
    failed = await db.integration_events.count_documents({**base, "status": "failed"})
    pending = await db.integration_events.count_documents({**base, "status": "pending"})
    retry_q = await db.integration_events.count_documents({**base, "status": "retry"})

    # Per-system stats
    pipeline = [
        {"$match": base},
        {"$group": {"_id": "$source_system", "count": {"$sum": 1}, "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}}}},
    ]
    system_stats = {}
    async for doc in db.integration_events.aggregate(pipeline):
        system_stats[doc["_id"]] = {"total": doc["count"], "failed": doc["failed"]}

    # Recent errors
    recent_errors = await db.integration_events.find(
        {**base, "status": "failed"}, {"_id": 0, "id": 1, "event_type": 1, "error": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    return {
        "total_events": total, "completed": completed, "failed": failed,
        "pending": pending, "retry_queue": retry_q,
        "success_rate": round(completed / max(total, 1) * 100, 1),
        "system_stats": system_stats,
        "recent_errors": recent_errors,
    }


@router.get("/data-model")
async def get_data_model(user=Depends(get_crm_user)):
    """Return the canonical data model with source-of-truth rules."""
    return {"entities": DATA_MODEL, "sync_rules": SYNC_RULES}


# ── Source of Truth & Data Model ──────────────────────────────────

DATA_MODEL = {
    "company": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_companies"], "relationships": ["contacts", "opportunities", "quotes", "cases", "assets", "invoices"]},
    "site": {"owner": "service_portal", "id_strategy": "uuid4", "collections": ["sites"], "relationships": ["company", "assets", "issues"]},
    "contact": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_contacts"], "relationships": ["company", "opportunities", "activities"]},
    "opportunity": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_opportunities"], "relationships": ["company", "contact", "quotes", "orders", "activities"]},
    "quote": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_quotes"], "relationships": ["company", "contact", "opportunity", "quote_versions"]},
    "order": {"owner": "shared_crm_finance", "id_strategy": "uuid4", "collections": ["crm2_orders"], "relationships": ["opportunity", "company", "invoice"]},
    "contract": {"owner": "shared_crm_service", "id_strategy": "uuid4", "collections": ["service_contracts"], "relationships": ["company", "assets"]},
    "asset": {"owner": "service_portal", "id_strategy": "uuid4", "collections": ["equipment"], "relationships": ["company", "site", "issues", "contracts"]},
    "service_case": {"owner": "service_portal", "id_strategy": "uuid4", "collections": ["crm2_service_cases", "issues"], "relationships": ["company", "contact", "asset", "engineer_visits"]},
    "engineer_visit": {"owner": "service_portal", "id_strategy": "uuid4", "collections": ["issues"], "relationships": ["service_case", "asset", "engineer"]},
    "invoice": {"owner": "sage_200", "id_strategy": "sage_ref", "collections": ["crm2_invoices"], "relationships": ["company", "order"]},
    "payment": {"owner": "sage_200", "id_strategy": "sage_ref", "collections": ["crm2_payments"], "relationships": ["invoice", "company"]},
    "user": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm_users"], "relationships": ["team", "activities"]},
    "activity": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_activities"], "relationships": ["company", "contact", "opportunity"]},
    "document": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_documents"], "relationships": ["company", "opportunity", "tender"]},
    "ai_output": {"owner": "crm", "id_strategy": "uuid4", "collections": ["crm2_tenders"], "relationships": ["opportunity", "company"]},
}

SYNC_RULES = {
    "company": {"crm_to_sage": "on_deal_won", "sage_to_crm": "scheduled_daily", "conflict": "crm_wins_name_sage_wins_financial"},
    "contact": {"crm_to_sage": "on_deal_won", "sage_to_crm": "manual_sync", "conflict": "crm_wins"},
    "invoice": {"sage_to_crm": "real_time_webhook", "conflict": "sage_wins"},
    "payment": {"sage_to_crm": "real_time_webhook", "conflict": "sage_wins"},
    "asset": {"service_to_crm": "on_case_created", "conflict": "service_wins_spec_crm_wins_commercial"},
    "service_case": {"service_to_crm": "real_time", "crm_to_service": "on_assignment", "conflict": "service_wins_status_crm_wins_commercial"},
}
