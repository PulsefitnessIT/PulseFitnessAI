"""
Sicon sync queue management and event-hook helpers.
See /app/memory/SICON_INTEGRATION_SPEC.md §6.3 for retry strategy.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from utils.database import db
from utils.sicon_common import get_sicon_client, get_sicon_config
from utils.sicon_client import (
    SiconAPIError,
    build_internal_issue_payload,
    build_stock_adjustment_payload,
    build_stock_transfer_payload,
    build_tracking_note_payload,
    map_gymaxis_to_sicon_case,
    map_sicon_appointment_to_gymaxis,
    map_sicon_case_to_gymaxis,
    map_sicon_resource_to_engineer,
    map_sicon_tracking_note_to_gymaxis,
)

logger = logging.getLogger(__name__)

# Retry backoff schedule per error type (spec §6.3)
RETRY_BACKOFF_SECONDS = {
    500: [5, 30, 120],
    502: [5, 30, 120],
    503: [5, 30, 120],
    504: [5, 30, 120],
    408: [10, 60, 300],
    0: [5, 15, 45, 120, 300],  # network errors
}
# Non-retryable HTTP statuses
NO_RETRY_STATUS = {400, 401, 403, 404, 409, 422}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _log_event(organization_id: str, action: str, details: str, success: bool, user_id: str = "system") -> None:
    await db.sicon_audit_log.insert_one({
        "organization_id": organization_id, "action": action, "details": details,
        "success": success, "user_id": user_id, "timestamp": _now(),
    })


async def enqueue_failed_operation(
    organization_id: str,
    operation: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
    error: SiconAPIError,
) -> None:
    """Write a failed operation to the sicon_sync_queue for later retry."""
    if error.http_status in NO_RETRY_STATUS:
        # Still log but mark as non-retryable
        await db.sicon_sync_queue.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "operation": operation,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "error": str(error)[:500],
            "http_status": error.http_status,
            "attempts": 1,
            "max_attempts": 1,
            "next_retry_at": None,
            "retryable": False,
            "created_at": _now(),
            "resolved_at": None,
        })
        return

    backoff = RETRY_BACKOFF_SECONDS.get(error.http_status, RETRY_BACKOFF_SECONDS[0])
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff[0])
    await db.sicon_sync_queue.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "operation": operation,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload,
        "error": str(error)[:500],
        "http_status": error.http_status,
        "attempts": 1,
        "max_attempts": len(backoff),
        "next_retry_at": next_retry.isoformat(),
        "retryable": True,
        "created_at": _now(),
        "resolved_at": None,
    })


async def mark_queue_resolved(queue_id: str, resolution: str = "retry_succeeded") -> None:
    await db.sicon_sync_queue.update_one(
        {"id": queue_id},
        {"$set": {"resolved_at": _now(), "resolution": resolution}}
    )


async def bump_queue_attempt(queue_id: str, error: SiconAPIError) -> None:
    """Increment attempts and schedule next retry, or mark exhausted."""
    item = await db.sicon_sync_queue.find_one({"id": queue_id}, {"_id": 0})
    if not item:
        return
    backoff = RETRY_BACKOFF_SECONDS.get(error.http_status, RETRY_BACKOFF_SECONDS[0])
    attempts = item.get("attempts", 0) + 1
    if attempts >= len(backoff):
        await db.sicon_sync_queue.update_one(
            {"id": queue_id},
            {"$set": {
                "attempts": attempts,
                "retryable": False,
                "resolved_at": _now(),
                "resolution": "retries_exhausted",
                "error": str(error)[:500],
                "http_status": error.http_status,
            }}
        )
        return
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff[attempts])
    await db.sicon_sync_queue.update_one(
        {"id": queue_id},
        {"$set": {
            "attempts": attempts,
            "next_retry_at": next_retry.isoformat(),
            "error": str(error)[:500],
            "http_status": error.http_status,
        }}
    )


# ── Event hooks: Pulse Fitness → Sicon ──────────────────────────────────

async def _get_org_name(organization_id: str) -> str:
    org = await db.organizations.find_one({"id": organization_id}, {"_id": 0, "name": 1})
    return org.get("name", "") if org else ""


def _preflight_sync_skip_reason(issue: dict, config: dict | None) -> str | None:
    """Return a skip reason if this issue shouldn't be synced, else None."""
    if not issue:
        return "issue_not_found"
    if not issue.get("organization_id"):
        return "no_organization_id"
    if not config or not config.get("enabled") or not config.get("auto_sync_faults", True):
        return "sicon_disabled"
    return None


async def _persist_sync_success(issue_id: str, sicon_id, sicon_num: str, org_id: str, user_id: str) -> None:
    """Mark the issue as synced and log the event."""
    await db.issues.update_one(
        {"id": issue_id},
        {"$set": {
            "sicon_case_id": sicon_id,
            "sicon_case_number": sicon_num,
            "sicon_synced_at": _now(),
            "sicon_sync_status": "synced",
            "sicon_sync_error": None,
        }}
    )
    await _log_event(org_id, "issue_synced", f"Issue {issue_id} → Sicon case {sicon_id}", True, user_id)


def _extract_triage_summary(issue: dict) -> str:
    """Pick the best available AI-triage summary text, stripped to 1500 chars."""
    triage = issue.get("ai_triage_parsed") or {}
    raw = (
        triage.get("summary") or triage.get("diagnosis")
        or issue.get("ai_triage_summary") or issue.get("ai_triage") or ""
    )
    return str(raw)[:1500]


async def _post_first_tracking_note(issue_id: str, triage_summary: str) -> None:
    """Best-effort first tracking note carrying the AI triage summary."""
    if not triage_summary:
        return
    try:
        updated = await db.issues.find_one({"id": issue_id}, {"_id": 0, "sicon_case_id": 1})
        if updated and updated.get("sicon_case_id"):
            await post_tracking_note(
                issue_id=issue_id,
                note_text=f"AI Triage: {triage_summary}",
                created_by="Pulse Fitness AI", visible_to_customer=False,
            )
    except Exception as ex:
        logger.warning(f"AI triage note post failed (non-blocking): {ex}")


async def _fetch_case_context(issue: Dict) -> Dict:
    """Phase A — load equipment, site, and org CRM links to feed the richer mapper."""
    ctx: Dict = {"equipment": None, "site": None, "crm_links": {}}
    org_id = issue.get("organization_id")

    serial = issue.get("serial_number")
    if serial and org_id:
        ctx["equipment"] = await db.equipment.find_one(
            {"organization_id": org_id, "serial_number": serial}, {"_id": 0},
        )

    site_id = issue.get("site_id") or (ctx["equipment"] or {}).get("site_id")
    if site_id:
        ctx["site"] = await db.sites.find_one({"id": site_id}, {"_id": 0})

    if org_id:
        org_doc = await db.organizations.find_one(
            {"id": org_id},
            {"_id": 0, "sicon_crm_person_id": 1, "sicon_crm_company_id": 1},
        )
        if org_doc:
            ctx["crm_links"] = {
                "crm_person_id": org_doc.get("sicon_crm_person_id") or 0,
                "crm_company_id": org_doc.get("sicon_crm_company_id") or 0,
            }
    return ctx


async def sync_issue_to_sicon(issue_id: str, user_id: str = "system") -> Optional[int]:
    """Push a Pulse Fitness issue to Sicon as a new service case. Returns sicon_case_id or None."""
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    org_id = issue.get("organization_id") if issue else None
    config = await get_sicon_config(org_id) if org_id else None
    if _preflight_sync_skip_reason(issue, config):
        return None
    if issue.get("sicon_case_id"):
        return issue["sicon_case_id"]  # already synced

    client = await get_sicon_client(org_id)
    if not client:
        return None

    ctx = await _fetch_case_context(issue)
    use_v1 = bool(config.get("service_webapi_v1"))
    if use_v1:
        from utils.sicon_service_models import build_case_model_v1
        payload = build_case_model_v1(
            issue, config, org_name=await _get_org_name(org_id),
            equipment=ctx["equipment"], site=ctx["site"], crm_links=ctx["crm_links"])
    else:
        payload = map_gymaxis_to_sicon_case(
            issue, config,
            org_name=await _get_org_name(org_id),
            equipment=ctx["equipment"],
            site=ctx["site"],
            crm_links=ctx["crm_links"],
        )
    try:
        if use_v1:
            result = await client.svc_create_case(payload)
            entity = result.get("entity", result) if isinstance(result, dict) else {}
            sicon_id = entity.get("siSMCaseId") or entity.get("SiSMCaseId") or entity.get("id")
            sicon_num = entity.get("caseNumber") or entity.get("CaseNumber", "") or ""
        else:
            result = await client.create_case(payload)
            entity = result.get("entity", result) if isinstance(result, dict) else {}
            sicon_id = entity.get("SiSMCaseId") or entity.get("ID")
            sicon_num = entity.get("CaseNumber", "")
        await _persist_sync_success(issue_id, sicon_id, sicon_num, org_id, user_id)
        await _post_first_tracking_note(issue_id, _extract_triage_summary(issue))
        return sicon_id
    except SiconAPIError as e:
        await db.issues.update_one(
            {"id": issue_id},
            {"$set": {"sicon_sync_status": "failed", "sicon_sync_error": str(e)[:300]}}
        )
        await enqueue_failed_operation(org_id, "create_case", "issue", issue_id, payload, e)
        await _log_event(org_id, "issue_sync_failed", f"Issue {issue_id}: {str(e)[:200]}", False, user_id)
        raise


async def post_tracking_note(issue_id: str, note_text: str, created_by: str = "Pulse Fitness AI",
                              visible_to_customer: bool = True) -> Optional[int]:
    """
    Post a tracking note to the Sicon case linked to a Pulse Fitness issue.
    Non-blocking event hook — errors are queued, not raised.
    """

    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not issue or not issue.get("sicon_case_id"):
        return None  # no case to attach note to

    org_id = issue.get("organization_id")
    if not org_id:
        return None
    config = await get_sicon_config(org_id)
    if not config or not config.get("enabled"):
        return None
    client = await get_sicon_client(org_id)
    if not client:
        return None

    sicon_case_id = issue["sicon_case_id"]
    payload = build_tracking_note_payload(
        note_text=note_text,
        created_by=created_by,
        visible_to_customer=visible_to_customer,
    )
    try:
        result = await client.create_tracking_note(sicon_case_id, payload)
        entity = result.get("entity", result) if isinstance(result, dict) else {}
        note_id = entity.get("ID") or entity.get("TrackingNoteID")
        await _log_event(org_id, "tracking_note_posted", f"Case {sicon_case_id}: {note_text[:80]}", True)
        return note_id
    except SiconAPIError as e:
        await enqueue_failed_operation(
            org_id, "create_tracking_note", "note", f"{issue_id}:{_now()}", payload, e
        )
        await _log_event(org_id, "tracking_note_failed", f"Case {sicon_case_id}: {str(e)[:200]}", False)
        logger.warning(f"Sicon tracking note queued for retry: {e}")
        return None


async def on_ai_triage_completed(issue_id: str, triage_summary: str) -> None:
    """Event hook — post AI triage summary as tracking note."""
    note = f"AI Triage: {triage_summary[:1500]}"
    await post_tracking_note(issue_id, note, created_by="Pulse Fitness AI", visible_to_customer=False)


async def on_supplier_contacted(issue_id: str, supplier_name: str) -> None:
    """Event hook — log supplier contact in Sicon timeline."""
    note = f"Supplier '{supplier_name}' contacted via Pulse Fitness portal"
    await post_tracking_note(issue_id, note, created_by="Pulse Fitness AI")


async def on_supplier_responded(issue_id: str, supplier_name: str, message: str) -> None:
    """Event hook — log supplier response in Sicon timeline."""
    note = f"Supplier '{supplier_name}' responded: {message[:1000]}"
    await post_tracking_note(issue_id, note, created_by="Pulse Fitness AI")


async def on_supplier_scheduled_visit(issue_id: str, supplier_name: str, visit_date: str) -> None:
    note = f"Supplier '{supplier_name}' scheduled engineer visit: {visit_date}"
    await post_tracking_note(issue_id, note, created_by="Pulse Fitness AI")


async def on_status_changed(issue_id: str, new_status: str, user_name: str) -> None:
    note = f"Status updated to '{new_status}' by {user_name}"
    await post_tracking_note(issue_id, note, created_by=user_name)


async def on_media_attached(issue_id: str, user_name: str) -> None:
    note = f"Media attachment added by {user_name}"
    await post_tracking_note(issue_id, note, created_by=user_name)


# ── Event hooks: Pulse Fitness stock → Sicon (CoreWebAPI) ───────────────
# Dry-run safe: every hook is a no-op unless the org's Sicon config has
# both `enabled` and `auto_sync_stock` true AND a client is configured.
# Failures are queued (never raised) so a stock-sync blip can't break the
# engineer/office flow. See INTEGRATION_FIELD_MAPPING.md §33.13.

def _warehouse_for(config: Dict, location_type: str, engineer_id: str = "") -> str:
    """Resolve the Sage warehouse name for one of our stock locations.

    `warehouse` → the org's main Sage warehouse; `van` → the engineer's
    van warehouse via the per-org `van_warehouse_mapping` (engineer_id →
    warehouse name), falling back to the configured default."""
    default_wh = config.get("default_warehouse_name") or "Warehouse"
    if location_type == "van" and engineer_id:
        return (config.get("van_warehouse_mapping") or {}).get(engineer_id) or default_wh
    return default_wh


async def _stock_sync_ready(organization_id: str):
    """Return (config, client) when stock sync is on for the org, else (None, None)."""
    if not organization_id:
        return None, None
    config = await get_sicon_config(organization_id)
    if not config or not config.get("enabled") or not config.get("auto_sync_stock"):
        return None, None
    client = await get_sicon_client(organization_id)
    return (config, client) if client else (None, None)


async def on_part_consumed(organization_id: str, movement: Dict) -> bool:
    """A part was consumed on a job → book a Sage internal issue out of the
    engineer's van. `movement` is the `svc_part_movements` consume doc."""
    config, client = await _stock_sync_ready(organization_id)
    if not client:
        return False
    payload = build_internal_issue_payload(
        movement.get("part_sku") or "",
        movement.get("qty") or 0,
        _warehouse_for(config, "van", movement.get("engineer_id") or ""),
        reference=(movement.get("case_reference") or movement.get("case_id") or "")[:60],
        second_ref=(movement.get("case_id") or "")[:60],
        cover_category=movement.get("cover_category") or "",
        narrative=movement.get("part_name") or movement.get("part_sku") or "",
    )
    try:
        await client.internal_issue(payload)
        await _log_event(organization_id, "stock_internal_issue",
                         f"Issued {payload['Quantity']} × {payload['ItemCode']}", True)
        return True
    except SiconAPIError as e:
        await enqueue_failed_operation(
            organization_id, "stock_internal_issue", "movement",
            movement.get("id") or _now(), payload, e)
        logger.warning(f"Sicon internal-issue queued for retry: {e}")
        return False


async def on_stock_transferred(organization_id: str, transfer: Dict) -> bool:
    """A warehouse↔van transfer happened → mirror it to Sage. `transfer` is
    {part_sku, qty, from:{type,engineer_id}, to:{type,engineer_id},
    transfer_id, part_name}."""
    config, client = await _stock_sync_ready(organization_id)
    if not client:
        return False
    src = transfer.get("from") or {}
    dst = transfer.get("to") or {}
    payload = build_stock_transfer_payload(
        transfer.get("part_sku") or "",
        transfer.get("qty") or 0,
        _warehouse_for(config, src.get("type") or "", src.get("engineer_id") or ""),
        _warehouse_for(config, dst.get("type") or "", dst.get("engineer_id") or ""),
        reference=(transfer.get("transfer_id") or "")[:60],
        second_reference=(transfer.get("part_name") or "")[:60],
    )
    try:
        await client.transfer_stock(payload)
        await _log_event(organization_id, "stock_transfer",
                         f"Transferred {payload['Quantity']} × {payload['ItemCode']}", True)
        return True
    except SiconAPIError as e:
        await enqueue_failed_operation(
            organization_id, "stock_transfer", "transfer",
            transfer.get("transfer_id") or _now(), payload, e)
        logger.warning(f"Sicon stock-transfer queued for retry: {e}")
        return False


async def on_stock_adjusted(organization_id: str, adjustment: Dict) -> bool:
    """A stock-take variance was posted → mirror to Sage AddStock/WriteOff.
    `adjustment` is {part_sku, qty_delta, location, engineer_id, reference}."""
    config, client = await _stock_sync_ready(organization_id)
    if not client:
        return False
    operation, payload = build_stock_adjustment_payload(
        adjustment.get("part_sku") or "",
        adjustment.get("qty_delta") or 0,
        _warehouse_for(config, adjustment.get("location") or "",
                       adjustment.get("engineer_id") or ""),
        reference=(adjustment.get("reference") or "stock-take")[:60],
        narrative=adjustment.get("part_name") or "",
    )
    try:
        if operation == "stock_add":
            await client.add_stock(payload)
        else:
            await client.write_off_stock(payload)
        await _log_event(organization_id, operation,
                         f"Adjusted {payload['Quantity']} × {payload['ItemCode']}", True)
        return True
    except SiconAPIError as e:
        await enqueue_failed_operation(
            organization_id, operation, "adjustment",
            adjustment.get("id") or _now(), payload, e)
        logger.warning(f"Sicon stock-adjust queued for retry: {e}")
        return False


# ── Inbound poll: Sicon → Pulse Fitness ─────────────────────────────────

async def _sync_case_status(client, issue: Dict, sicon_case_id) -> bool:
    """Pull fresh Sicon case status; update issue sicon_* fields. Return True if updated."""
    case_resp = await client.get_case(sicon_case_id)
    mapped = map_sicon_case_to_gymaxis(case_resp)
    update_fields = {k: v for k, v in mapped.items() if v is not None and k.startswith("sicon_")}
    if not update_fields:
        return False
    update_fields["sicon_last_polled_at"] = _now()
    await db.issues.update_one({"id": issue["id"]}, {"$set": update_fields})
    return True


async def _sync_appointments(client, issue: Dict, sicon_case_id) -> bool:
    """Pull appointments for a case; apply latest scheduling/completion. Returns True if updated."""
    try:
        appt_resp = await client.get_appointments_for_case(sicon_case_id)
    except SiconAPIError as e:
        logger.warning(f"Appointment poll failed for case {sicon_case_id}: {e}")
        return False
    appt_entities = appt_resp.get("entities", []) if isinstance(appt_resp, dict) else []
    if not appt_entities:
        return False
    latest_appt = map_sicon_appointment_to_gymaxis(appt_entities[-1])
    issue_update: Dict = {"sicon_appointments": [map_sicon_appointment_to_gymaxis(a) for a in appt_entities]}
    if latest_appt.get("scheduled_start"):
        issue_update["engineer_assigned_at"] = latest_appt["scheduled_start"]
    if latest_appt.get("appointment_complete"):
        issue_update["work_completed_at"] = latest_appt.get("scheduled_end")
        issue_update["engineer_notes"] = latest_appt.get("work_done_description")
    await db.issues.update_one({"id": issue["id"]}, {"$set": issue_update})
    return True


async def _sync_tracking_notes(client, issue: Dict, sicon_case_id) -> int:
    """Pull tracking notes; append new ones to timeline. Returns count of new notes."""
    try:
        notes_resp = await client.get_tracking_notes(sicon_case_id)
    except SiconAPIError as e:
        logger.warning(f"Notes poll failed for case {sicon_case_id}: {e}")
        return 0
    note_entities = notes_resp.get("entities", []) if isinstance(notes_resp, dict) else []
    known_ids = set(issue.get("sicon_note_ids", []))
    new_notes = []
    for n in note_entities:
        mn = map_sicon_tracking_note_to_gymaxis(n)
        if mn.get("sicon_note_id") and mn["sicon_note_id"] not in known_ids:
            new_notes.append(mn)
    if not new_notes:
        return 0
    # Iter 220bi — preserve every Sicon tracking-note field on the
    # timeline entry so the UI can surface GPS, visibility flags,
    # appointment link, status, etc. without a second fetch.
    timeline_entries = [
        {
            "type": "sicon_note",
            "source": "sicon",
            "sicon_note_id": n.get("sicon_note_id"),
            "message": n.get("message", ""),
            "timestamp": n.get("timestamp"),
            "by": n.get("by", "Sicon"),
            "case_tracking_status_id": n.get("case_tracking_status_id"),
            "status": n.get("status"),
            "visible_to_engineer": n.get("visible_to_engineer", True),
            "visible_to_customer": n.get("visible_to_customer", False),
            "sicon_appointment_id": n.get("sicon_appointment_id"),
            "latitude": n.get("latitude"),
            "longitude": n.get("longitude"),
        }
        for n in new_notes
    ]
    await db.issues.update_one(
        {"id": issue["id"]},
        {"$push": {
            "timeline": {"$each": timeline_entries},
            "sicon_note_ids": {"$each": [n["sicon_note_id"] for n in new_notes]},
        }}
    )
    return len(new_notes)


async def _sync_single_issue(client, issue: Dict, counts: Dict[str, int]) -> None:
    """Drive all 3 sync steps for a single issue; swallow Sicon errors."""
    sicon_case_id = issue["sicon_case_id"]
    try:
        if await _sync_case_status(client, issue, sicon_case_id):
            counts["cases_updated"] += 1
        if await _sync_appointments(client, issue, sicon_case_id):
            counts["appointments_updated"] += 1
        counts["notes_added"] += await _sync_tracking_notes(client, issue, sicon_case_id)
    except SiconAPIError as e:
        counts["errors"] += 1
        logger.warning(f"Sicon poll for issue {issue['id']} failed: {e}")


async def poll_sicon_updates_for_org(organization_id: str) -> Dict[str, int]:
    """For an org, pull case statuses / appointments / notes from Sicon.
    Returns counts of updates applied.
    """
    counts = {"cases_updated": 0, "appointments_updated": 0, "notes_added": 0, "errors": 0}
    client = await get_sicon_client(organization_id)
    if not client:
        return counts
    config = await get_sicon_config(organization_id)
    if not config or not config.get("enabled"):
        return counts

    cursor = db.issues.find(
        {"organization_id": organization_id,
         "sicon_case_id": {"$exists": True, "$ne": None},
         "status": {"$in": ["open", "in_progress", "awaiting_engineer", "engineer_assigned"]}},
        {"_id": 0}
    )
    async for issue in cursor:
        await _sync_single_issue(client, issue, counts)

    await db.sicon_config.update_one(
        {"organization_id": organization_id},
        {"$set": {"last_poll_at": _now(), "last_poll_counts": counts}}
    )
    return counts


async def _retry_create_case(client, item: dict) -> None:
    result = await client.create_case(item.get("payload", {}))
    entity = result.get("entity", result) if isinstance(result, dict) else {}
    sicon_id = entity.get("SiSMCaseId") or entity.get("ID")
    if sicon_id and item.get("entity_id"):
        await db.issues.update_one(
            {"id": item["entity_id"]},
            {"$set": {
                "sicon_case_id": sicon_id,
                "sicon_case_number": entity.get("CaseNumber", ""),
                "sicon_synced_at": _now(),
                "sicon_sync_status": "synced",
                "sicon_sync_error": None,
            }}
        )


async def _retry_tracking_note(client, item: dict) -> None:
    entity_id = item.get("entity_id", "")
    issue_id = entity_id.split(":")[0] if ":" in entity_id else entity_id
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0, "sicon_case_id": 1})
    if issue and issue.get("sicon_case_id"):
        await client.create_tracking_note(issue["sicon_case_id"], item.get("payload", {}))


async def _retry_item(client, item: dict) -> bool:
    """Dispatch a queue item to the right handler; return True if an op ran."""
    op = item.get("operation")
    payload = item.get("payload", {})
    handlers = {
        "create_case": lambda: _retry_create_case(client, item),
        "create_tracking_note": lambda: _retry_tracking_note(client, item),
        "amend_case": lambda: client.amend_case(payload),
        "create_appointment": lambda: client.create_appointment(payload),
        "create_contract": lambda: client.create_contract(payload),
        "stock_internal_issue": lambda: client.internal_issue(payload),
        "stock_transfer": lambda: client.transfer_stock(payload),
        "stock_add": lambda: client.add_stock(payload),
        "stock_writeoff": lambda: client.write_off_stock(payload),
    }
    handler = handlers.get(op)
    if handler is None:
        logger.warning(f"Unknown queued operation: {op}")
        return False
    await handler()
    return True


async def retry_queue_for_org(organization_id: str) -> Dict[str, int]:
    """Retry all due queue items for an organization."""
    counts = {"retried": 0, "succeeded": 0, "failed": 0, "exhausted": 0}
    client = await get_sicon_client(organization_id)
    if not client:
        return counts

    cursor = db.sicon_sync_queue.find({
        "organization_id": organization_id,
        "resolved_at": None,
        "retryable": True,
        "next_retry_at": {"$lte": _now()},
    }, {"_id": 0})

    async for item in cursor:
        counts["retried"] += 1
        try:
            if not await _retry_item(client, item):
                continue
            await mark_queue_resolved(item["id"], "retry_succeeded")
            counts["succeeded"] += 1
            await _log_event(
                organization_id, "queue_retry_success",
                f"{item.get('operation')} for {item.get('entity_id')}", True,
            )
        except SiconAPIError as e:
            await bump_queue_attempt(item["id"], e)
            counts["failed"] += 1
            if e.http_status in NO_RETRY_STATUS:
                counts["exhausted"] += 1
    return counts


# ─── Phase C: Engineer directory refresh ────────────────────────────

def _engineer_doc(org_id: str, raw: Dict) -> Dict:
    mapped = map_sicon_resource_to_engineer(raw)
    mapped["organization_id"] = org_id
    mapped["id"] = f"{org_id}:{mapped.get('sicon_employee_id') or raw.get('SIJCEMPID')}"
    mapped["updated_at"] = _now()
    return mapped


async def refresh_sicon_engineers(org_id: str) -> Dict:
    """Phase C — mirror /api/service/appointments/resources into sicon_engineers.

    Returns a count breakdown: {fetched, upserted, leavers_skipped}."""
    counts = {"fetched": 0, "upserted": 0, "leavers_skipped": 0}
    client = await get_sicon_client(org_id)
    if not client:
        return counts
    try:
        raw = await client.get_resources()
    except SiconAPIError as e:
        logger.warning(f"[engineers] fetch failed for org {org_id}: {e}")
        return counts

    entities = raw.get("entities") if isinstance(raw, dict) else None
    if not entities:
        return counts

    for entity in entities:
        counts["fetched"] += 1
        if entity.get("IsLeaver"):
            counts["leavers_skipped"] += 1
            continue
        doc = _engineer_doc(org_id, entity)
        await db.sicon_engineers.update_one(
            {"id": doc["id"]}, {"$set": doc}, upsert=True,
        )
        counts["upserted"] += 1
    return counts


async def refresh_all_sicon_engineers() -> Dict:
    """Called by the nightly poller — refresh every Sicon-enabled org's engineer cache."""
    totals = {"orgs": 0, "fetched": 0, "upserted": 0, "leavers_skipped": 0}
    async for cfg in db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1}):
        org_id = cfg.get("organization_id")
        if not org_id:
            continue
        totals["orgs"] += 1
        row = await refresh_sicon_engineers(org_id)
        for k in ("fetched", "upserted", "leavers_skipped"):
            totals[k] += row[k]
    return totals
