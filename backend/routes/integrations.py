"""
Integrations Management Routes
Manages third-party integration configs, logs, and the Orbit 4 → Sicon bridge.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging
import uuid
import hashlib
import hmac
import json
import httpx

from utils.database import db
from utils.auth import get_current_user
from utils.orbit4_client import (
    ORBIT4_SUPPORTED_EVENTS,
    Orbit4APIError,
    Orbit4Client,
    map_gymaxis_contract_to_orbit4,
    map_gymaxis_equipment_to_orbit4,
    map_gymaxis_issue_to_orbit4_ticket,
    map_gymaxis_status_to_orbit4_patch,
    map_gymaxis_user_to_orbit4,
    map_orbit4_asset_to_gymaxis,
    map_orbit4_ticket_full,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────

async def verify_admin(user: dict):
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin access required")


async def get_integration_config(integration_id: str) -> Optional[Dict]:
    config = await db.integrations.find_one({"integration_id": integration_id}, {"_id": 0})
    return config


async def log_integration_event(
    integration_id: str,
    event_type: str,
    direction: str,
    summary: str,
    payload: dict = None,
    success: bool = True,
    error: str = None,
):
    await db.integration_logs.insert_one({
        "id": str(uuid.uuid4()),
        "integration_id": integration_id,
        "event_type": event_type,
        "direction": direction,
        "summary": summary,
        "payload": payload or {},
        "success": success,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Integration Config CRUD ───────────────────────────────────────

@router.get("/integrations")
async def list_integrations(user: dict = Depends(get_current_user)):
    await verify_admin(user)
    integrations = await db.integrations.find({}, {"_id": 0}).to_list(100)
    # Add log counts
    for integ in integrations:
        integ["total_events"] = await db.integration_logs.count_documents(
            {"integration_id": integ["integration_id"]}
        )
        integ["recent_errors"] = await db.integration_logs.count_documents(
            {"integration_id": integ["integration_id"], "success": False}
        )
    return {"integrations": integrations}


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: str, user: dict = Depends(get_current_user)):
    await verify_admin(user)
    config = await get_integration_config(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    config["total_events"] = await db.integration_logs.count_documents(
        {"integration_id": integration_id}
    )
    config["recent_errors"] = await db.integration_logs.count_documents(
        {"integration_id": integration_id, "success": False}
    )
    return config


@router.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, body: Dict[str, Any], user: dict = Depends(get_current_user)):
    await verify_admin(user)
    config = await get_integration_config(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")

    allowed_fields = ["enabled", "api_token", "webhook_secret", "base_url", "credentials", "field_mappings", "settings", "branding"]
    update = {k: v for k, v in body.items() if k in allowed_fields}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.integrations.update_one(
        {"integration_id": integration_id},
        {"$set": update}
    )
    await log_integration_event(integration_id, "config_updated", "internal", f"Configuration updated by {user.get('email')}")
    # P2.15 fail-closed audit for sensitive integration changes.
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "integration.config.updated", "actor_id": user["id"],
        "actor_email": user.get("email"), "integration_id": integration_id,
        "fields": list(update.keys()),
    })
    return {"status": "ok", "message": "Integration updated"}


@router.get("/integrations/{integration_id}/logs")
async def get_integration_logs(
    integration_id: str,
    limit: int = 50,
    offset: int = 0,
    success_only: Optional[bool] = None,
    user: dict = Depends(get_current_user),
):
    await verify_admin(user)
    query = {"integration_id": integration_id}
    if success_only is not None:
        query["success"] = success_only

    total = await db.integration_logs.count_documents(query)
    logs = await db.integration_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(offset).limit(limit).to_list(limit)
    return {"logs": logs, "total": total}


@router.get("/integrations/{integration_id}/stats")
async def get_integration_stats(integration_id: str, user: dict = Depends(get_current_user)):
    await verify_admin(user)
    total = await db.integration_logs.count_documents({"integration_id": integration_id})
    success = await db.integration_logs.count_documents({"integration_id": integration_id, "success": True})
    errors = await db.integration_logs.count_documents({"integration_id": integration_id, "success": False})

    # Recent events (last 24h)
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = await db.integration_logs.count_documents(
        {"integration_id": integration_id, "timestamp": {"$gte": cutoff}}
    )

    # Last event
    last_event = await db.integration_logs.find_one(
        {"integration_id": integration_id},
        {"_id": 0, "timestamp": 1, "event_type": 1, "success": 1},
        sort=[("timestamp", -1)]
    )

    return {
        "total_events": total,
        "successful": success,
        "errors": errors,
        "last_24h": recent,
        "last_event": last_event,
        "success_rate": round((success / total * 100), 1) if total > 0 else 0,
    }


# ── Orbit 4 Webhook Receiver ─────────────────────────────────────

async def _validate_orbit4_webhook(request: Request, config: dict) -> dict:
    """Validate and parse an Orbit 4 webhook request."""
    body = await request.body()
    webhook_secret = config.get("webhook_secret")
    if webhook_secret:
        signature = request.headers.get("X-Signature", "")
        expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            await log_integration_event("orbit4", "webhook_rejected", "inbound", "Invalid webhook signature", success=False, error="Signature mismatch")
            raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        await log_integration_event("orbit4", "webhook_error", "inbound", "Invalid JSON payload", success=False, error="JSON decode error")
        raise HTTPException(status_code=400, detail="Invalid JSON")


@router.post("/webhooks/orbit4")
async def orbit4_webhook(request: Request):
    """Receives webhooks from Orbit 4. Handles ticket, asset, note, media and user events."""
    config = await get_integration_config("orbit4")
    if not config or not config.get("enabled"):
        return {"status": "ignored", "reason": "integration_disabled"}

    payload = await _validate_orbit4_webhook(request, config)
    event_type = payload.get("event", "unknown")
    data_envelope = payload.get("data", {})

    # Preferred shape is {"event": "...", "data": {"ticket": {...}}} but some
    # older payloads nest the entity directly under data.
    entity = (
        data_envelope.get("ticket")
        or data_envelope.get("asset")
        or data_envelope.get("note")
        or data_envelope.get("media")
        or data_envelope.get("user")
        or data_envelope
    )

    summary_id = entity.get("id") or entity.get("number") or "unknown"
    summary_desc = (entity.get("description") or entity.get("subject") or entity.get("note") or "")[:100]
    await log_integration_event("orbit4", event_type, "inbound",
                                f"#{summary_id} — {summary_desc}", payload=payload)

    handlers = {
        "ticket.created": process_new_ticket,
        "ticket.updated": process_ticket_update,
        "ticket.closed":  process_ticket_closed,
        "asset.created":  process_asset_upsert,
        "asset.updated":  process_asset_upsert,
        "asset.moved":    process_asset_moved,
        "note.created":   process_note_created,
        "media.created":  process_media_created,
        "user.created":   process_user_upsert,
        "user.updated":   process_user_upsert,
    }
    handler = handlers.get(event_type)
    if handler:
        await handler(entity, config)
    elif event_type not in ORBIT4_SUPPORTED_EVENTS:
        logger.info(f"[orbit4] unhandled event type {event_type}")

    processor = config.get("branding", {}).get("display_name", "Pulse Fitness")
    return {"status": "ok", "event": event_type, "processor": processor}


# ── Phase α — Inbound: deep ticket mapper ─────────────────────────

def _map_orbit4_to_sicon(ticket_data: dict) -> dict:
    """Build the Sicon-bound case dict using the full Orbit4 mapper.

    Preserved for backward compatibility with the bridge record shape."""
    full = map_orbit4_ticket_full(ticket_data)
    sicon = {
        "description": full.get("description", ""),
        "subject": full.get("subject"),
        "asset_serial": full.get("asset_serial", ""),
        "asset_name": full.get("asset_name", ""),
        "asset_qr_code": full.get("asset_qr_code", ""),
        "priority": map_orbit4_priority(str(full.get("orbit4_priority") or "normal")),
        "location": (full.get("orbit4_gym_operator") or {}).get("site_name", ""),
        "reporter_name": (full.get("orbit4_gym_operator") or {}).get("name", ""),
        "reporter_email": (full.get("orbit4_gym_operator") or {}).get("email", ""),
        "orbit4_ticket_id": full["orbit4_ticket_id"],
        "orbit4_reference": full["orbit4_ticket_number"],
        "orbit4_status": full["orbit4_status"],
        "orbit4_type": full["orbit4_type"],
        "orbit4_problem_type": full["orbit4_problem_type"],
    }
    return sicon


async def _forward_and_log_sicon(sicon_case: dict, sicon_config: dict, bridge_record: dict) -> None:
    """Attempt to forward a ticket to Sicon and update the bridge record."""
    if not (sicon_config and sicon_config.get("enabled") and sicon_config.get("base_url")):
        bridge_record["status"] = "queued"
        await log_integration_event("sicon", "case_queued", "internal", f"Sicon not configured — ticket {sicon_case['orbit4_ticket_id']} queued")
        return

    try:
        sicon_result = await forward_to_sicon(sicon_case, sicon_config)
        bridge_record["sicon_case_id"] = sicon_result.get("case_id")
        bridge_record["status"] = "forwarded"
        await log_integration_event("sicon", "case_created", "outbound", f"Service case for Orbit 4 ticket {sicon_case['orbit4_ticket_id']}", payload={"sicon_case": sicon_result.get("case_id")})
    except Exception as e:
        bridge_record["status"] = "error"
        bridge_record["error"] = str(e)
        await log_integration_event("sicon", "case_create_failed", "outbound", f"Failed for Orbit 4 ticket {sicon_case['orbit4_ticket_id']}", success=False, error=str(e))


async def process_new_ticket(ticket_data: dict, orbit4_config: dict):
    """Transform Orbit 4 ticket into Sicon service case and forward."""
    sicon_config = await get_integration_config("sicon")
    sicon_case = _map_orbit4_to_sicon(ticket_data)
    full = map_orbit4_ticket_full(ticket_data)

    bridge_record = {
        "id": str(uuid.uuid4()),
        "orbit4_ticket_id": sicon_case["orbit4_ticket_id"],
        "orbit4_reference": sicon_case["orbit4_reference"],
        "sicon_case_id": None, "status": "pending",
        "orbit4_data": ticket_data, "sicon_data": sicon_case,
        # Phase α — keep the full mapped form for the UI + KPI engine
        "orbit4_full": full,
        "orbit4_contract": full.get("orbit4_contract") or {},
        "orbit4_attachments": full.get("orbit4_attachments") or [],
        "orbit4_notes": full.get("orbit4_notes") or [],
        "orbit4_lifecycle": {
            "deployed_at": full.get("orbit4_engineer_deployed_at"),
            "arrived_at":  full.get("orbit4_engineer_arrived_at"),
            "closed_at":   full.get("orbit4_closed_at"),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await _forward_and_log_sicon(sicon_case, sicon_config, bridge_record)
    await db.integration_bridge.insert_one(bridge_record)


async def process_ticket_update(ticket_data: dict, config: dict):
    """Handle ticket update from Orbit 4 — mirror status + lifecycle timestamps."""
    ticket_id = str(ticket_data.get("id", ""))
    bridge = await db.integration_bridge.find_one({"orbit4_ticket_id": ticket_id}, {"_id": 0})
    if not bridge:
        return
    full = map_orbit4_ticket_full(ticket_data)
    await db.integration_bridge.update_one(
        {"orbit4_ticket_id": ticket_id},
        {"$set": {
            "orbit4_data": ticket_data,
            "orbit4_full": full,
            "orbit4_contract": full.get("orbit4_contract") or {},
            "orbit4_attachments": full.get("orbit4_attachments") or [],
            "orbit4_notes": full.get("orbit4_notes") or [],
            "orbit4_lifecycle": {
                "deployed_at": full.get("orbit4_engineer_deployed_at"),
                "arrived_at":  full.get("orbit4_engineer_arrived_at"),
                "closed_at":   full.get("orbit4_closed_at"),
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    await log_integration_event(
        "orbit4", "ticket_updated", "inbound",
        f"Ticket {ticket_id} updated",
    )


async def process_ticket_closed(ticket_data: dict, config: dict):
    """Handle ticket closure from Orbit 4."""
    ticket_id = str(ticket_data.get("id", ""))
    bridge = await db.integration_bridge.find_one({"orbit4_ticket_id": ticket_id}, {"_id": 0})
    if not bridge:
        return
    full = map_orbit4_ticket_full(ticket_data)
    await db.integration_bridge.update_one(
        {"orbit4_ticket_id": ticket_id},
        {"$set": {
            "status": "closed",
            "orbit4_data": ticket_data,
            "orbit4_full": full,
            "orbit4_lifecycle.closed_at": full.get("orbit4_closed_at"),
            "closed_at": full.get("orbit4_closed_at") or datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    await log_integration_event("orbit4", "ticket_closed", "inbound", f"Ticket {ticket_id} closed")


# ── Phase β — New inbound handlers ────────────────────────────────

def _orbit4_org_from_metadata(metadata: Any) -> Optional[str]:
    """Webhooks coming back from Orbit4 carry our own integration_id in metadata
    so we can resolve the originating GymAxis organisation in O(1)."""
    if not metadata:
        return None
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(metadata, dict):
        return metadata.get("organization_id")
    return None


async def process_asset_upsert(asset_data: dict, config: dict):
    """Mirror a created/updated Orbit4 asset into our equipment cache."""
    mapped = map_orbit4_asset_to_gymaxis(asset_data)
    org_id = _orbit4_org_from_metadata(asset_data.get("metadata"))
    serial = mapped.get("serial_number") or ""
    orbit_id = mapped.get("orbit4_asset_id")

    query: Dict = {"$or": []}
    if orbit_id:
        query["$or"].append({"orbit4_asset_id": orbit_id})
    if serial and org_id:
        query["$or"].append({"organization_id": org_id, "serial_number": serial})
    if not query["$or"]:
        await log_integration_event("orbit4", "asset_upsert_skipped", "inbound",
                                    "No serial/id/org to match", success=False)
        return

    mapped["updated_at"] = datetime.now(timezone.utc).isoformat()
    if org_id:
        mapped["organization_id"] = org_id
    await db.equipment.update_one(query, {"$set": mapped}, upsert=False)
    await log_integration_event(
        "orbit4", "asset_upserted", "inbound",
        f"Asset {orbit_id} / {serial} mirrored",
    )


async def process_asset_moved(asset_data: dict, config: dict):
    """Equipment transferred between sites/orgs — re-home it."""
    target_org = (asset_data.get("target") or {}).get("organization_id") \
                 or _orbit4_org_from_metadata(asset_data.get("metadata"))
    orbit_id = asset_data.get("id")
    if not (target_org and orbit_id):
        await log_integration_event("orbit4", "asset_move_skipped", "inbound",
                                    "Missing target/asset_id", success=False)
        return
    await db.equipment.update_one(
        {"orbit4_asset_id": orbit_id},
        {"$set": {
            "organization_id": target_org,
            "moved_at": datetime.now(timezone.utc).isoformat(),
            "orbit4_moved_from": (asset_data.get("source") or {}).get("organization_id"),
        }},
    )
    await log_integration_event("orbit4", "asset_moved", "inbound",
                                f"Asset {orbit_id} → org {target_org}")


async def process_note_created(note_data: dict, config: dict):
    """Append an Orbit4 note into the matching issue timeline."""
    ticket_id = str(note_data.get("ticket_id") or (note_data.get("ticket") or {}).get("id") or "")
    if not ticket_id:
        return
    bridge = await db.integration_bridge.find_one({"orbit4_ticket_id": ticket_id},
                                                  {"_id": 0, "gymaxis_issue_id": 1})
    timeline_entry = {
        "type": "orbit4_note",
        "message": note_data.get("note") or "",
        "by": ((note_data.get("user") or {}).get("first_name", "") + " "
               + (note_data.get("user") or {}).get("last_name", "")).strip() or "Orbit4",
        "timestamp": note_data.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    await db.integration_bridge.update_one(
        {"orbit4_ticket_id": ticket_id},
        {"$push": {"orbit4_notes": timeline_entry}},
    )
    issue_id = (bridge or {}).get("gymaxis_issue_id")
    if issue_id:
        await db.issues.update_one({"id": issue_id}, {"$push": {"timeline": timeline_entry}})
    await log_integration_event("orbit4", "note_created", "inbound",
                                f"Ticket {ticket_id} note appended")


async def process_media_created(media_data: dict, config: dict):
    """Mirror a new media/image/document onto the linked issue."""
    ticket_id = str(media_data.get("ticket_id") or (media_data.get("ticket") or {}).get("id") or "")
    if not ticket_id:
        return
    attachment = {
        "id": media_data.get("id"),
        "url": media_data.get("url"),
        "type": media_data.get("type") or "media",
        "source": "orbit4",
        "created_at": media_data.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    bridge = await db.integration_bridge.find_one({"orbit4_ticket_id": ticket_id},
                                                  {"_id": 0, "gymaxis_issue_id": 1})
    await db.integration_bridge.update_one(
        {"orbit4_ticket_id": ticket_id},
        {"$push": {"orbit4_attachments": attachment}},
    )
    issue_id = (bridge or {}).get("gymaxis_issue_id")
    if issue_id:
        await db.issues.update_one({"id": issue_id},
                                   {"$push": {"attachments": attachment}})
    await log_integration_event("orbit4", "media_created", "inbound",
                                f"Ticket {ticket_id} media mirrored")


async def process_user_upsert(user_data: dict, config: dict):
    """Mirror an Orbit4 user row into our orbit4_users cache."""
    doc = {
        "orbit4_user_id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "email": user_data.get("email"),
        "role": user_data.get("role"),
        "site_name": user_data.get("site_name"),
        "company_name": (user_data.get("company") or {}).get("name"),
        "language": user_data.get("language"),
        "metadata": user_data.get("metadata") or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orbit4_users.update_one(
        {"orbit4_user_id": doc["orbit4_user_id"]},
        {"$set": doc}, upsert=True,
    )
    await log_integration_event("orbit4", "user_upserted", "inbound",
                                f"User {doc['email']} mirrored")


async def forward_to_sicon(case_data: dict, sicon_config: dict) -> dict:
    """Forward a service case to Sicon Service API."""
    base_url = sicon_config.get("base_url", "").rstrip("/")
    credentials = sicon_config.get("credentials", {})
    branding = sicon_config.get("branding", {})
    user_agent = branding.get("user_agent", "PulseFitness-ServiceBridge/1.0")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/api/service/cases",
            json=case_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {credentials.get('api_key', '')}",
                "User-Agent": user_agent,
            }
        )
        response.raise_for_status()
        return response.json()


def map_orbit4_priority(orbit4_priority: str) -> str:
    """Map Orbit 4 priority values to Sicon priority."""
    mapping = {
        "low": "low",
        "normal": "medium",
        "medium": "medium",
        "high": "high",
        "urgent": "critical",
        "critical": "critical",
    }
    return mapping.get(str(orbit4_priority).lower(), "medium")


# ── Bridge Records ────────────────────────────────────────────────

@router.get("/integrations/bridge/records")
async def get_bridge_records(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    await verify_admin(user)
    query = {}
    if status:
        query["status"] = status

    total = await db.integration_bridge.count_documents(query)
    records = await db.integration_bridge.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    return {"records": records, "total": total}


@router.post("/integrations/bridge/{record_id}/retry")
async def retry_bridge_record(record_id: str, user: dict = Depends(get_current_user)):
    """Retry forwarding a failed/queued bridge record to Sicon."""
    await verify_admin(user)
    record = await db.integration_bridge.find_one({"id": record_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Bridge record not found")

    sicon_config = await get_integration_config("sicon")
    if not sicon_config or not sicon_config.get("enabled"):
        raise HTTPException(status_code=400, detail="Sicon integration not configured")

    try:
        result = await forward_to_sicon(record["sicon_data"], sicon_config)
        await db.integration_bridge.update_one(
            {"id": record_id},
            {"$set": {
                "sicon_case_id": result.get("case_id"),
                "status": "forwarded",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }}
        )
        await log_integration_event("sicon", "case_retried", "outbound", f"Retry successful for record {record_id}")
        return {"status": "ok", "sicon_case_id": result.get("case_id")}
    except Exception as e:
        await log_integration_event("sicon", "case_retry_failed", "outbound", f"Retry failed for record {record_id}", success=False, error=str(e))
        raise HTTPException(status_code=502, detail=f"Sicon forwarding failed: {str(e)}")


# ── Orbit 4 API Endpoints (Test Connection, Fetch Assets) ─────────

@router.post("/integrations/orbit4/test-connection")
async def test_orbit4_connection(user: dict = Depends(get_current_user)):
    """Test the Orbit 4 API connection using stored token."""
    await verify_admin(user)
    config = await get_integration_config("orbit4")
    if not config:
        raise HTTPException(status_code=404, detail="Orbit 4 integration not found")

    api_token = config.get("api_token", "")
    base_url = config.get("base_url", "https://api.orbit4.org/v1").rstrip("/")
    branding = config.get("branding", {})
    user_agent = branding.get("user_agent", "PulseFitness-ServiceBridge/1.0")

    if not api_token:
        return {"status": "error", "message": "No API token configured"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/assets?per_page=1",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": user_agent,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                total_assets = data.get("meta", {}).get("total", 0)
                await log_integration_event("orbit4", "connection_test", "outbound", f"Connection successful — {total_assets} assets found")
                return {
                    "status": "connected",
                    "message": "Successfully connected to Orbit 4",
                    "total_assets": total_assets,
                    "rate_limit": resp.headers.get("x-ratelimit-remaining"),
                    "base_url": base_url,
                }
            elif resp.status_code == 401:
                await log_integration_event("orbit4", "connection_test", "outbound", "Authentication failed", success=False, error="401 Unauthorized")
                return {"status": "error", "message": "Authentication failed — invalid API token"}
            else:
                await log_integration_event("orbit4", "connection_test", "outbound", f"Unexpected response: {resp.status_code}", success=False, error=resp.text[:200])
                return {"status": "error", "message": f"Unexpected response: {resp.status_code}"}
    except Exception as e:
        await log_integration_event("orbit4", "connection_test", "outbound", f"Connection failed: {str(e)}", success=False, error=str(e))
        return {"status": "error", "message": f"Connection failed: {str(e)}"}


@router.get("/integrations/orbit4/assets")
async def fetch_orbit4_assets(
    page: int = 1,
    per_page: int = 25,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Fetch assets from Orbit 4 API for display in the admin panel."""
    await verify_admin(user)
    config = await get_integration_config("orbit4")
    if not config:
        raise HTTPException(status_code=404, detail="Orbit 4 integration not found")

    api_token = config.get("api_token", "")
    base_url = config.get("base_url", "https://api.orbit4.org/v1").rstrip("/")
    branding = config.get("branding", {})
    user_agent = branding.get("user_agent", "PulseFitness-ServiceBridge/1.0")

    if not api_token:
        raise HTTPException(status_code=400, detail="No API token configured")

    params = {"page": page, "per_page": per_page}
    if search:
        params["search"] = search

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/assets",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": user_agent,
                },
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "assets": data.get("data", []),
                "meta": data.get("meta", {}),
                "total": data.get("meta", {}).get("total", 0),
            }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Orbit 4 API error: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch assets: {str(e)}")


@router.get("/integrations/orbit4/users")
async def fetch_orbit4_users(
    page: int = 1,
    per_page: int = 25,
    user: dict = Depends(get_current_user),
):
    """Fetch users from Orbit 4 API."""
    await verify_admin(user)
    config = await get_integration_config("orbit4")
    if not config:
        raise HTTPException(status_code=404, detail="Orbit 4 integration not found")

    api_token = config.get("api_token", "")
    base_url = config.get("base_url", "https://api.orbit4.org/v1").rstrip("/")
    branding = config.get("branding", {})
    user_agent = branding.get("user_agent", "PulseFitness-ServiceBridge/1.0")

    if not api_token:
        raise HTTPException(status_code=400, detail="No API token configured")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/users",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": user_agent,
                },
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "users": data.get("data", []),
                "meta": data.get("meta", {}),
                "total": data.get("meta", {}).get("total", 0),
            }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Orbit 4 API error: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch users: {str(e)}")



# ── Phases γ-δ — Outbound Orbit4 mirror ──────────────────────────

async def _orbit4_client_or_none() -> Optional[Orbit4Client]:
    config = await get_integration_config("orbit4")
    if not config or not config.get("enabled") or not config.get("api_token"):
        return None
    branding = config.get("branding") or {}
    return Orbit4Client(
        base_url=config.get("base_url", "https://api.orbit4.org/v1"),
        api_token=config.get("api_token", ""),
        user_agent=branding.get("user_agent", "PulseFitness-ServiceBridge/1.0"),
    )


_ORBIT4_ID_KEY = {
    "equipment": "orbit4_asset_id",
    "crm_contracts": "orbit4_contract_id",
    "issues": "orbit4_ticket_id",
}


async def _update_orbit4_id(collection: str, doc_id: str, orbit4_id: Any) -> None:
    key = _ORBIT4_ID_KEY.get(collection, "orbit4_id")
    await db[collection].update_one(
        {"id": doc_id},
        {"$set": {
            key: orbit4_id,
            "orbit4_synced_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


async def mirror_equipment_to_orbit4(equipment: Dict) -> Optional[int]:
    """Phase γ — create or update an Orbit4 asset from our equipment doc."""
    client = await _orbit4_client_or_none()
    if not client:
        return None
    payload = map_gymaxis_equipment_to_orbit4(equipment)
    try:
        if equipment.get("orbit4_asset_id"):
            res = await client.update_asset(int(equipment["orbit4_asset_id"]), payload)
            orbit4_id = res.get("id") or equipment["orbit4_asset_id"]
        else:
            res = await client.create_asset(payload)
            orbit4_id = res.get("id")
        if orbit4_id and equipment.get("id"):
            await _update_orbit4_id("equipment", equipment["id"], orbit4_id)
        await log_integration_event("orbit4", "asset_mirrored", "outbound",
                                    f"Equipment {equipment.get('id')} → asset {orbit4_id}")
        return int(orbit4_id) if orbit4_id else None
    except Orbit4APIError as e:
        await log_integration_event("orbit4", "asset_mirror_failed", "outbound",
                                    f"Equipment {equipment.get('id')}",
                                    success=False, error=str(e)[:300])
        return None


async def mirror_contract_to_orbit4(contract: Dict, *,
                                     gym_operator_id: int,
                                     service_provider_id: int) -> Optional[int]:
    """Phase γ — create an Orbit4 contract from our CRM contract."""
    client = await _orbit4_client_or_none()
    if not client:
        return None
    payload = map_gymaxis_contract_to_orbit4(
        contract, gym_operator_id=gym_operator_id,
        service_provider_id=service_provider_id,
    )
    try:
        res = await client.create_contract(payload)
        orbit4_id = res.get("id")
        if orbit4_id and contract.get("id"):
            await _update_orbit4_id("crm_contracts", contract["id"], orbit4_id)
        await log_integration_event("orbit4", "contract_mirrored", "outbound",
                                    f"Contract {contract.get('id')} → {orbit4_id}")
        return int(orbit4_id) if orbit4_id else None
    except Orbit4APIError as e:
        await log_integration_event("orbit4", "contract_mirror_failed", "outbound",
                                    f"Contract {contract.get('id')}",
                                    success=False, error=str(e)[:300])
        return None


async def mirror_issue_to_orbit4(issue: Dict, *,
                                  orbit4_contract_id: int,
                                  orbit4_asset_id: Optional[int] = None,
                                  gym_operator_id: Optional[int] = None,
                                  service_provider_id: Optional[int] = None) -> Optional[int]:
    """Phase δ — raise an Orbit4 ticket for a newly logged fault."""
    client = await _orbit4_client_or_none()
    if not client:
        return None
    payload = map_gymaxis_issue_to_orbit4_ticket(
        issue, asset_id=orbit4_asset_id,
        gym_operator_id=gym_operator_id,
        service_provider_id=service_provider_id,
        problem_type=issue.get("fault_code") or "undefined",
    )
    try:
        res = await client.create_ticket(int(orbit4_contract_id), payload)
        orbit4_id = res.get("id")
        if orbit4_id and issue.get("id"):
            await _update_orbit4_id("issues", issue["id"], orbit4_id)
        await log_integration_event("orbit4", "ticket_mirrored", "outbound",
                                    f"Issue {issue.get('id')} → ticket {orbit4_id}")
        return int(orbit4_id) if orbit4_id else None
    except Orbit4APIError as e:
        await log_integration_event("orbit4", "ticket_mirror_failed", "outbound",
                                    f"Issue {issue.get('id')}",
                                    success=False, error=str(e)[:300])
        return None


async def mirror_issue_status_to_orbit4(issue: Dict,
                                         resolution: Optional[str] = None) -> bool:
    """Phase δ — PUT a status change onto the matching Orbit4 ticket."""
    client = await _orbit4_client_or_none()
    orbit4_id = issue.get("orbit4_ticket_id")
    if not (client and orbit4_id):
        return False
    patch = map_gymaxis_status_to_orbit4_patch(issue.get("status", "open"), resolution)
    try:
        await client.update_ticket(int(orbit4_id), patch)
        await log_integration_event("orbit4", "ticket_status_mirrored", "outbound",
                                    f"Ticket {orbit4_id} → {patch['status']}")
        return True
    except Orbit4APIError as e:
        await log_integration_event("orbit4", "ticket_status_failed", "outbound",
                                    f"Ticket {orbit4_id}",
                                    success=False, error=str(e)[:300])
        return False


async def provision_orbit4_user(user: Dict, *, role: str = "gym_operator",
                                 site_name: Optional[str] = None) -> Optional[int]:
    """Phase γ — create a matching Orbit4 user row."""
    client = await _orbit4_client_or_none()
    if not client:
        return None
    payload = map_gymaxis_user_to_orbit4(user, role=role, site_name=site_name)
    try:
        res = await client.create_user(payload)
        orbit4_id = res.get("id")
        if orbit4_id and user.get("id"):
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"orbit4_user_id": orbit4_id,
                          "orbit4_synced_at": datetime.now(timezone.utc).isoformat()}},
            )
        await log_integration_event("orbit4", "user_provisioned", "outbound",
                                    f"User {user.get('email')} → {orbit4_id}")
        return int(orbit4_id) if orbit4_id else None
    except Orbit4APIError as e:
        await log_integration_event("orbit4", "user_provision_failed", "outbound",
                                    f"User {user.get('email')}",
                                    success=False, error=str(e)[:300])
        return None


# ── Admin-triggered mirror endpoints ─────────────────────────────

@router.post("/integrations/orbit4/mirror/equipment/{equipment_id}")
async def trigger_equipment_mirror(equipment_id: str, user: dict = Depends(get_current_user)):
    await verify_admin(user)
    equipment = await db.equipment.find_one({"id": equipment_id}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    asset_id = await mirror_equipment_to_orbit4(equipment)
    if not asset_id:
        raise HTTPException(status_code=502, detail="Orbit4 mirror failed — see integration logs")
    return {"success": True, "orbit4_asset_id": asset_id}


@router.post("/integrations/orbit4/mirror/contract/{contract_id}")
async def trigger_contract_mirror(contract_id: str, body: Dict[str, int],
                                   user: dict = Depends(get_current_user)):
    await verify_admin(user)
    contract = await db.crm_contracts.find_one({"id": contract_id}, {"_id": 0})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    orbit4_id = await mirror_contract_to_orbit4(
        contract,
        gym_operator_id=int(body.get("gym_operator_id") or 0),
        service_provider_id=int(body.get("service_provider_id") or 0),
    )
    if not orbit4_id:
        raise HTTPException(status_code=502, detail="Orbit4 mirror failed")
    return {"success": True, "orbit4_contract_id": orbit4_id}


@router.post("/integrations/orbit4/mirror/issue/{issue_id}")
async def trigger_issue_mirror(issue_id: str, body: Dict[str, int],
                                user: dict = Depends(get_current_user)):
    await verify_admin(user)
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    ticket_id = await mirror_issue_to_orbit4(
        issue,
        orbit4_contract_id=int(body.get("orbit4_contract_id") or 0),
        orbit4_asset_id=body.get("orbit4_asset_id"),
        gym_operator_id=body.get("gym_operator_id"),
        service_provider_id=body.get("service_provider_id"),
    )
    if not ticket_id:
        raise HTTPException(status_code=502, detail="Orbit4 mirror failed")
    return {"success": True, "orbit4_ticket_id": ticket_id}


# ── Seed Default Integrations ─────────────────────────────────────

_DEFAULT_ORBIT4_CONFIG = {
    "integration_id": "orbit4", "name": "Orbit 4",
    "description": "Gym operator fault logging platform. Receives webhooks and forwards tickets to Sicon.",
    "type": "inbound", "enabled": False, "api_token": "", "webhook_secret": "",
    "webhook_url": "/api/webhooks/orbit4", "base_url": "https://api.orbit4.org/v1",
    "field_mappings": {"description": "description", "subject": "subject", "asset_serial": "asset_serial_number", "asset_name": "asset_name", "priority": "priority"},
    "settings": {"auto_forward_to_sicon": True, "log_all_events": True},
    "branding": {"display_name": "Pulse Fitness", "contact_email": "", "production_webhook_domain": "", "user_agent": "PulseFitness-ServiceBridge/1.0"},
}

_DEFAULT_SICON_CONFIG = {
    "integration_id": "sicon", "name": "Sicon Service",
    "description": "Service management ERP. Receives forwarded fault tickets as service cases.",
    "type": "outbound", "enabled": False, "base_url": "",
    "credentials": {"api_key": "", "username": "", "password": "", "company_id": ""},
    "field_mappings": {}, "settings": {},
    "branding": {"display_name": "Pulse Fitness", "contact_email": "", "user_agent": "PulseFitness-ServiceBridge/1.0"},
}


async def seed_integrations():
    """Create default integration config records if they don't exist."""
    now = datetime.now(timezone.utc).isoformat()
    for config in (_DEFAULT_ORBIT4_CONFIG, _DEFAULT_SICON_CONFIG):
        existing = await db.integrations.find_one({"integration_id": config["integration_id"]})
        if not existing:
            await db.integrations.insert_one({**config, "created_at": now, "updated_at": now})
            logger.info(f"Seeded integration config: {config['integration_id']}")
