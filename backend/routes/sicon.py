"""
Sicon Service Integration Routes
Settings management, sync endpoints, poll & queue management, audit logging.
See /app/memory/SICON_INTEGRATION_SPEC.md for the full field model.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.sicon_client import (
    SiconAPIError, encrypt_value, map_gymaxis_to_sicon_case, map_sicon_case_to_gymaxis,
    build_tracking_note_payload, build_appointment_payload,
    build_appointment_completion_payload, build_time_booking_payload,
    map_gymaxis_contract_to_sicon, map_gymaxis_contract_line_to_sicon,
)
from utils.sicon_common import (
    get_sicon_config, get_sicon_client, log_sicon_event,
)
from utils.sicon_sync import (
    enqueue_failed_operation, retry_queue_for_org,
    poll_sicon_updates_for_org,
    post_tracking_note as post_note_hook,
    sync_issue_to_sicon as do_sync_issue,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_owner_or_manager(user: Dict) -> None:
    if user.get("role") not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def _require_org(user: Dict) -> str:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organization")
    return org_id


# ── Settings ──────────────────────────────────────────────────────

@router.get("/sicon/config")
async def get_config(user: dict = Depends(get_current_user)):
    """Get Sicon integration config (credentials are masked)."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    config = await get_sicon_config(org_id)
    if not config:
        return {"configured": False, "enabled": False}
    return {
        "configured": True,
        "enabled": config.get("enabled", False),
        "base_url": config.get("base_url", ""),
        "username": "••••••••" if config.get("username_enc") else "",
        "has_password": bool(config.get("password_enc")),
        "company_id": config.get("company_id", 0),
        "default_case_type_id": config.get("default_case_type_id", 0),
        "default_case_type_name": config.get("default_case_type_name", ""),
        "default_priority_id": config.get("default_priority_id", 0),
        "default_internal_team_id": config.get("default_internal_team_id", 0),
        "default_external_team_id": config.get("default_external_team_id", 0),
        "default_assigned_user_id": config.get("default_assigned_user_id", 0),
        "default_contract_id": config.get("default_contract_id", 0),
        "default_contract_line_id": config.get("default_contract_line_id", 0),
        "auto_sync_faults": config.get("auto_sync_faults", False),
        "auto_sync_status": config.get("auto_sync_status", False),
        "priority_mapping": config.get("priority_mapping", {"low": 0, "medium": 0, "critical": 0}),
        "location_address": config.get("location_address", {}),
        "last_sync_at": config.get("last_sync_at"),
        "last_poll_at": config.get("last_poll_at"),
        "last_poll_counts": config.get("last_poll_counts", {}),
        "connection_status": config.get("connection_status", "unknown"),
    }


@router.put("/sicon/config")
async def save_config(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Save or update Sicon integration config. Credentials encrypted at rest."""
    if user.get("role") != "owner" and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners can configure Sicon integration")
    org_id = _require_org(user)

    update_doc = {
        "organization_id": org_id,
        "base_url": (data.get("base_url") or "").rstrip("/"),
        "company_id": data.get("company_id", 0),
        "enabled": data.get("enabled", False),
        "auto_sync_faults": data.get("auto_sync_faults", False),
        "auto_sync_status": data.get("auto_sync_status", False),
        "default_case_type_id": data.get("default_case_type_id", 0),
        "default_case_type_name": data.get("default_case_type_name", ""),
        "default_priority_id": data.get("default_priority_id", 0),
        "default_internal_team_id": data.get("default_internal_team_id", 0),
        "default_external_team_id": data.get("default_external_team_id", 0),
        "default_assigned_user_id": data.get("default_assigned_user_id", 0),
        "default_contract_id": data.get("default_contract_id", 0),
        "default_contract_line_id": data.get("default_contract_line_id", 0),
        "priority_mapping": data.get("priority_mapping", {"low": 0, "medium": 0, "critical": 0}),
        "location_address": data.get("location_address", {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["id"],
    }

    # Encrypt credentials if provided (skip if masked/empty)
    if data.get("username") and data["username"] != "••••••••":
        update_doc["username_enc"] = encrypt_value(data["username"])
    if data.get("password"):
        update_doc["password_enc"] = encrypt_value(data["password"])

    await db.sicon_config.update_one(
        {"organization_id": org_id},
        {"$set": update_doc},
        upsert=True
    )

    await log_sicon_event(org_id, "config_updated", "Sicon integration settings saved", True, user["id"])
    return {"success": True, "message": "Sicon configuration saved"}


# ── Connection Test ───────────────────────────────────────────────

@router.post("/sicon/test-connection")
async def test_connection(user: dict = Depends(get_current_user)):
    """Test the Sicon WebAPI connection with stored credentials."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    client = await get_sicon_client(org_id)
    if not client:
        return {"connected": False, "error": "Sicon integration not configured"}

    try:
        is_up = await client.ping()
        status = "connected" if is_up else "unreachable"
        await db.sicon_config.update_one(
            {"organization_id": org_id},
            {"$set": {"connection_status": status, "last_tested_at": datetime.now(timezone.utc).isoformat()}}
        )
        await log_sicon_event(org_id, "connection_test", f"Result: {status}", is_up, user["id"])
        return {"connected": is_up, "status": status}
    except Exception as e:
        await db.sicon_config.update_one(
            {"organization_id": org_id},
            {"$set": {"connection_status": "error", "last_error": str(e)[:500]}}
        )
        await log_sicon_event(org_id, "connection_test", f"Error: {str(e)[:200]}", False, user["id"])
        return {"connected": False, "error": str(e)[:200]}


# ── Fetch Sicon Reference Data ────────────────────────────────────

@router.get("/sicon/case-types")
async def fetch_case_types(user: dict = Depends(get_current_user)):
    client = await get_sicon_client(_require_org(user))
    if not client:
        return {"case_types": [], "error": "Not configured"}
    try:
        result = await client.get_case_types()
        return {"case_types": result.get("entities", [])}
    except SiconAPIError as e:
        return {"case_types": [], "error": str(e)[:200]}


@router.get("/sicon/tracking-statuses")
async def fetch_tracking_statuses(user: dict = Depends(get_current_user)):
    client = await get_sicon_client(_require_org(user))
    if not client:
        return {"statuses": [], "error": "Not configured"}
    try:
        result = await client.get_tracking_statuses()
        return {"statuses": result.get("entities", [])}
    except SiconAPIError as e:
        return {"statuses": [], "error": str(e)[:200]}


@router.get("/sicon/engineers")
async def fetch_engineers(user: dict = Depends(get_current_user),
                          refresh: bool = False,
                          include_leavers: bool = False):
    """List engineers. By default returns the local cache (fast, offline-safe).

    Set ?refresh=true to force a live pull from Sicon + upsert the cache."""
    from utils.database import db
    from utils.sicon_sync import refresh_sicon_engineers
    org_id = _require_org(user)
    if refresh:
        await refresh_sicon_engineers(org_id)
    query: dict = {"organization_id": org_id}
    if not include_leavers:
        query["is_leaver"] = {"$ne": True}
    cached = await db.sicon_engineers.find(query, {"_id": 0}).sort("full_name", 1).to_list(length=1000)
    return {"engineers": cached, "count": len(cached), "source": "cache" if not refresh else "live"}


@router.post("/sicon/engineers/refresh")
async def refresh_engineers(user: dict = Depends(get_current_user)):
    """Manual trigger for the engineer-directory refresh (Phase C)."""
    from utils.sicon_sync import refresh_sicon_engineers
    org_id = _require_org(user)
    counts = await refresh_sicon_engineers(org_id)
    return {"success": True, **counts}


@router.get("/sicon/priorities")
async def fetch_priorities(user: dict = Depends(get_current_user)):
    """Return configured priority mapping.

    The Sicon Service WebAPI (R260200c) has NO priorities lookup endpoint, so
    priorities cannot be pulled live. We surface the manually-configured
    priority_mapping / default_priority_id from the org's Sicon config instead.
    """
    org_id = _require_org(user)
    config = await get_sicon_config(org_id) or {}
    return {
        "priorities": [],
        "priority_mapping": config.get("priority_mapping", {}),
        "default_priority_id": config.get("default_priority_id", 0),
        "note": "Sicon WebAPI has no priorities list endpoint; set IDs manually in config.",
    }


# ── Outbound: Pulse Fitness → Sicon ─────────────────────────────────────

@router.post("/sicon/sync-case/{issue_id}")
@router.post("/sicon/sync-issue/{issue_id}")  # alias kept for backwards compatibility
async def sync_issue(issue_id: str, user: dict = Depends(get_current_user)):
    """Manually push a Pulse Fitness issue to Sicon as a new service case."""
    _require_org(user)
    org_filter = get_organization_filter(user)

    # Scope check
    exists = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0, "id": 1})
    if not exists:
        raise HTTPException(status_code=404, detail="Issue not found")

    try:
        sicon_id = await do_sync_issue(issue_id, user_id=user["id"])
        if sicon_id is None:
            raise HTTPException(status_code=400, detail="Sicon integration not configured or already synced")
        return {"success": True, "sicon_case_id": sicon_id}
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon sync failed: {str(e)[:200]}")


@router.post("/sicon/amend-case/{issue_id}")
async def amend_case(issue_id: str, user: dict = Depends(get_current_user)):
    """Push updated Pulse Fitness issue details to an existing Sicon case."""
    org_id = _require_org(user)
    org_filter = get_organization_filter(user)

    issue = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not issue.get("sicon_case_id"):
        raise HTTPException(status_code=400, detail="Issue not yet synced to Sicon")

    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon integration not configured")

    config = await get_sicon_config(org_id)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    payload = map_gymaxis_to_sicon_case(issue, config, org_name=(org or {}).get("name", ""))
    payload["SiSMCaseId"] = issue["sicon_case_id"]

    try:
        await client.amend_case(payload)
        await db.issues.update_one(
            {"id": issue_id},
            {"$set": {"sicon_synced_at": datetime.now(timezone.utc).isoformat(),
                      "sicon_sync_status": "synced", "sicon_sync_error": None}}
        )
        await log_sicon_event(org_id, "amend_case", f"Issue {issue_id}", True, user["id"])
        return {"success": True}
    except SiconAPIError as e:
        await enqueue_failed_operation(org_id, "amend_case", "issue", issue_id, payload, e)
        raise HTTPException(status_code=502, detail=f"Sicon amend failed: {str(e)[:200]}")


@router.post("/sicon/add-note/{issue_id}")
async def add_note(issue_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Add a tracking note to the Sicon case linked to this issue."""
    org_filter = get_organization_filter(user)
    issue = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0, "sicon_case_id": 1})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not issue.get("sicon_case_id"):
        raise HTTPException(status_code=400, detail="Issue not yet synced to Sicon")

    note_text = data.get("note", "")
    if not note_text:
        raise HTTPException(status_code=400, detail="note required")

    note_id = await post_note_hook(
        issue_id=issue_id, note_text=note_text,
        created_by=user.get("full_name", "Pulse Fitness User"),
        visible_to_customer=data.get("visible_to_customer", True),
    )
    return {"success": True, "note_id": note_id}


@router.post("/sicon/create-appointment/{issue_id}")
async def create_appointment(issue_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Schedule a Sicon appointment for an existing case (e.g., supplier-arranged)."""
    org_id = _require_org(user)
    org_filter = get_organization_filter(user)
    issue = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0})
    if not issue or not issue.get("sicon_case_id"):
        raise HTTPException(status_code=400, detail="Issue not yet synced to Sicon")

    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon integration not configured")

    payload = build_appointment_payload(
        issue=issue,
        scheduled_start=data.get("scheduled_start"),
        scheduled_end=data.get("scheduled_end"),
        employee_ids=data.get("employee_ids", []),
        work_briefing=data.get("work_briefing", issue.get("ai_triage_summary", "")),
    )
    try:
        result = await client.create_appointment(payload)
        entity = result.get("entity", result) if isinstance(result, dict) else {}
        appt_id = entity.get("SiconAppointmentID") or entity.get("ID")
        await log_sicon_event(org_id, "appointment_created",
                              f"Issue {issue_id} → appointment {appt_id}", True, user["id"])
        return {"success": True, "sicon_appointment_id": appt_id}
    except SiconAPIError as e:
        await enqueue_failed_operation(org_id, "create_appointment", "appointment", issue_id, payload, e)
        raise HTTPException(status_code=502, detail=f"Sicon appointment failed: {str(e)[:200]}")


@router.post("/sicon/sync-contract/{contract_id}")
async def sync_contract(contract_id: str, user: dict = Depends(get_current_user)):
    """Push a CRM contract to Sicon as a Service Contract."""
    org_id = _require_org(user)
    contract = await db.crm_contracts.find_one({"id": contract_id}, {"_id": 0})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon integration not configured")

    # Resolve Sage customer account ID from the company
    sage_customer_id = 0
    if contract.get("company_id"):
        comp = await db.crm_companies.find_one({"id": contract["company_id"]},
                                                {"_id": 0, "sage_customer_id": 1})
        if comp:
            sage_customer_id = comp.get("sage_customer_id", 0) or 0

    payload = map_gymaxis_contract_to_sicon(contract, sage_customer_id)
    try:
        result = await client.create_contract(payload)
        entity = result.get("entity", result) if isinstance(result, dict) else {}
        sicon_contract_id = entity.get("SiconContractID") or entity.get("ID")
        await db.crm_contracts.update_one(
            {"id": contract_id},
            {"$set": {
                "sicon_contract_id": sicon_contract_id,
                "sicon_sync_status": "synced",
                "sicon_synced_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        await log_sicon_event(org_id, "contract_synced",
                              f"Contract {contract_id} → Sicon {sicon_contract_id}", True, user["id"])
        return {"success": True, "sicon_contract_id": sicon_contract_id}
    except SiconAPIError as e:
        await enqueue_failed_operation(org_id, "create_contract", "contract", contract_id, payload, e)
        raise HTTPException(status_code=502, detail=f"Sicon contract sync failed: {str(e)[:200]}")


@router.post("/sicon/update-contract-po/{contract_id}")
async def update_contract_purchase_order(
    contract_id: str,
    data: Dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Attach / amend a CustomerOrderNumber (PO) on an already-synced Sicon contract.

    Iter 216h7 — surfaces `update_contract_customer_order_number` so finance
    can attach a PO post-creation without re-syncing the whole contract
    (which would overwrite header edits made directly in Sicon).
    """
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    po = (data.get("customer_order_number") or "").strip()
    if not po:
        raise HTTPException(status_code=400, detail="customer_order_number is required")

    contract = await db.crm_contracts.find_one(
        {"id": contract_id, "organization_id": org_id}, {"_id": 0},
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    sicon_contract_id = contract.get("sicon_contract_id")
    if not sicon_contract_id:
        raise HTTPException(
            status_code=400,
            detail="Contract not yet synced to Sicon — push the contract first.",
        )

    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon integration not configured")

    try:
        await client.update_contract_customer_order_number(int(sicon_contract_id), po)
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.crm_contracts.update_one(
            {"id": contract_id},
            {"$set": {
                "customer_order_number": po,
                "po_last_updated_at": now_iso,
                "po_last_updated_by": user.get("email"),
            }},
        )
        await log_sicon_event(
            org_id, "contract_po_updated",
            f"Contract {contract_id} (Sicon {sicon_contract_id}) PO updated to '{po}'",
            True, user["id"],
        )
        return {"success": True, "customer_order_number": po, "updated_at": now_iso}
    except SiconAPIError as e:
        await enqueue_failed_operation(
            org_id, "update_contract_po", "contract", contract_id,
            {"sicon_contract_id": sicon_contract_id, "customer_order_number": po}, e,
        )
        raise HTTPException(status_code=502, detail=f"Sicon PO update failed: {str(e)[:200]}")


# ── Inbound Poll ──────────────────────────────────────────────────

@router.post("/sicon/poll-updates")
async def poll_updates(user: dict = Depends(get_current_user)):
    """Manually trigger the inbound poll for this organization."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    counts = await poll_sicon_updates_for_org(org_id)
    retry_counts = await retry_queue_for_org(org_id)
    return {"poll": counts, "retry": retry_counts}


@router.get("/sicon/case/{sicon_case_id}")
async def get_sicon_case(sicon_case_id: int, user: dict = Depends(get_current_user)):
    """Retrieve a specific case from Sicon on demand."""
    client = await get_sicon_client(_require_org(user))
    if not client:
        raise HTTPException(status_code=400, detail="Sicon not configured")
    try:
        result = await client.get_case(sicon_case_id)
        return map_sicon_case_to_gymaxis(result)
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon error: {str(e)[:200]}")


@router.post("/sicon/tracking-note")
async def add_sicon_tracking_note(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    """(Legacy) Add a tracking note to a Sicon case by case ID directly."""
    org_id = _require_org(user)
    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon not configured")

    sicon_case_id = data.get("sicon_case_id")
    if not sicon_case_id:
        raise HTTPException(status_code=400, detail="sicon_case_id required")

    payload = build_tracking_note_payload(
        note_text=data.get("note", ""),
        created_by=user.get("full_name", "Pulse Fitness User"),
        visible_to_customer=data.get("visible_to_customer", True),
        visible_to_engineer=data.get("visible_to_engineer", True),
        status_id=data.get("status_id", 0),
    )
    try:
        result = await client.create_tracking_note(sicon_case_id, payload)
        entity = result.get("entity", result) if isinstance(result, dict) else {}
        await log_sicon_event(org_id, "tracking_note_created", f"Case {sicon_case_id}", True, user["id"])
        return {"success": True, "note_id": entity.get("ID") or entity.get("TrackingNoteID")}
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon error: {str(e)[:200]}")


# ── Sync Queue Management ─────────────────────────────────────────

@router.get("/sicon/sync-queue")
async def list_sync_queue(
    user: dict = Depends(get_current_user),
    status: str = "pending",  # pending | resolved | all
    limit: int = 100,
):
    """List sync queue items for this organization."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    query: Dict[str, Any] = {"organization_id": org_id}
    if status == "pending":
        query["resolved_at"] = None
    elif status == "resolved":
        query["resolved_at"] = {"$ne": None}
    items = await db.sicon_sync_queue.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"items": items, "count": len(items)}


@router.post("/sicon/sync-queue/{queue_id}/retry")
async def retry_queue_item(queue_id: str, user: dict = Depends(get_current_user)):
    """Force retry of a single queued item."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    item = await db.sicon_sync_queue.find_one(
        {"id": queue_id, "organization_id": org_id}, {"_id": 0}
    )
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    # Set next_retry_at to now so retry_queue_for_org picks it up
    await db.sicon_sync_queue.update_one(
        {"id": queue_id}, {"$set": {"next_retry_at": datetime.now(timezone.utc).isoformat(), "retryable": True}}
    )
    counts = await retry_queue_for_org(org_id)
    return {"success": True, "counts": counts}


@router.delete("/sicon/sync-queue/{queue_id}")
async def delete_queue_item(queue_id: str, user: dict = Depends(get_current_user)):
    """Discard a queue item (mark resolved without retry)."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    res = await db.sicon_sync_queue.update_one(
        {"id": queue_id, "organization_id": org_id},
        {"$set": {"resolved_at": datetime.now(timezone.utc).isoformat(),
                  "resolution": "discarded_by_admin", "retryable": False}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return {"success": True}


# ── Audit Log ─────────────────────────────────────────────────────

@router.get("/sicon/audit-log")
async def get_audit_log(user: dict = Depends(get_current_user)):
    """Get the Sicon integration audit log."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    logs = await db.sicon_audit_log.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(100)
    return {"logs": logs}



# ── Phase B: Appointment completion + Time bookings ─────────────────

from pydantic import BaseModel, Field  # noqa: E402  (local import to avoid cycle)


class AppointmentCompleteReq(BaseModel):
    work_done: str = Field(..., max_length=4000)
    further_action: str = Field(default="", max_length=4000)
    arrival_signee: str = Field(default="", max_length=200)
    departure_signee: str = Field(default="", max_length=200)
    arrival_latitude: Optional[float] = None
    arrival_longitude: Optional[float] = None
    departure_latitude: Optional[float] = None
    departure_longitude: Optional[float] = None
    work_done_acknowledged: bool = False
    further_action_acknowledged: bool = False


class TimeBookingReq(BaseModel):
    employee_ids: list[int]
    start_date: str
    end_date: str
    actual_hours: float
    charge_rate: int = 0


@router.post("/sicon/appointments/{appointment_id}/complete")
async def complete_appointment(appointment_id: int, req: AppointmentCompleteReq,
                               user: dict = Depends(get_current_user)):
    """Close out a visit with work-done + signatures + GPS proof-of-work (Phase B)."""
    org_id = _require_org(user)
    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon not configured")
    payload = build_appointment_completion_payload(
        work_done=req.work_done, further_action=req.further_action,
        arrival_signee=req.arrival_signee, departure_signee=req.departure_signee,
        arrival_lat=req.arrival_latitude, arrival_lon=req.arrival_longitude,
        departure_lat=req.departure_latitude, departure_lon=req.departure_longitude,
        work_done_acknowledged=req.work_done_acknowledged,
        further_action_acknowledged=req.further_action_acknowledged,
    )
    try:
        result = await client.update_appointment(appointment_id, payload)
        await log_sicon_event(org_id, "appointment_complete",
                              f"Apt {appointment_id} signed off", True, user.get("id"))
        return {"success": True, "result": result, "payload": payload}
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon error: {e}")


@router.post("/sicon/appointments/{appointment_id}/time-bookings")
async def create_time_booking(appointment_id: int, req: TimeBookingReq,
                              user: dict = Depends(get_current_user)):
    """Log engineer labour hours against an appointment (Phase B)."""
    org_id = _require_org(user)
    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon not configured")
    payload = build_time_booking_payload(
        employee_ids=req.employee_ids, start_date=req.start_date,
        end_date=req.end_date, actual_hours=req.actual_hours, charge_rate=req.charge_rate,
    )
    try:
        result = await client.create_time_booking(appointment_id, payload)
        await log_sicon_event(org_id, "time_booking_created",
                              f"Apt {appointment_id} · {req.actual_hours}h", True, user.get("id"))
        return {"success": True, "result": result}
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon error: {e}")


# ── Phase D: Contract + ContractLine writeback ──────────────────────

class ContractLineSyncReq(BaseModel):
    contract_id: str
    line_index: Optional[int] = None  # if None → push every item on the contract


@router.post("/sicon/contracts/{contract_id}/sync")
async def sync_contract_to_sicon(contract_id: str, user: dict = Depends(get_current_user)):
    """Push a Pulse Fitness CRM contract header + all items to Sicon (Phase D)."""
    _require_owner_or_manager(user)
    org_id = _require_org(user)
    contract = await db.crm_contracts.find_one({"id": contract_id, "organization_id": org_id}, {"_id": 0})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    client = await get_sicon_client(org_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sicon not configured")

    header_payload = map_gymaxis_contract_to_sicon(contract)
    try:
        header_res = await client.create_or_update_contract(header_payload)
    except SiconAPIError as e:
        raise HTTPException(status_code=502, detail=f"Sicon contract upsert failed: {e}")
    sicon_contract_id = header_res.get("ContractID") or contract.get("sicon_contract_id") or 0
    sicon_contract_number = header_res.get("ContractNumber") or contract.get("contract_number", "")

    pushed_lines = []
    for idx, line in enumerate(contract.get("items") or []):
        line_payload = map_gymaxis_contract_line_to_sicon(line, sicon_contract_id)
        try:
            line_res = await client.post_contract_line(line_payload)
            pushed_lines.append({"index": idx, "result": line_res})
        except SiconAPIError as e:
            pushed_lines.append({"index": idx, "error": str(e)[:300]})

    await db.crm_contracts.update_one(
        {"id": contract_id},
        {"$set": {
            "sicon_contract_id": sicon_contract_id,
            "contract_number": sicon_contract_number or contract.get("contract_number", ""),
            "sicon_synced_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_sicon_event(org_id, "contract_synced",
                          f"Contract {contract_id} · {len(pushed_lines)} lines", True, user.get("id"))
    return {
        "success": True,
        "sicon_contract_id": sicon_contract_id,
        "contract_number": sicon_contract_number,
        "lines": pushed_lines,
    }
