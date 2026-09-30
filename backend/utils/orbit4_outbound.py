"""Orbit4 outbound — Pulse → Orbit4 case status resync (Phase δ).

Powers POST /svc/orbit4/cases/{id}/resync. Read-safe by design: it only mirrors
a Pulse case's current status onto its EXISTING Orbit4 ticket (PUT /tickets/{id}).
It never creates, deletes or fabricates Orbit4 records. Per-org connection +
API token come from db.svc_orbit4_connections (decrypted at use). Every attempt
stamps svc_cases.orbit4_sync for observability in the desk UI.
"""
from datetime import datetime, timezone
import logging

from utils.database import db
from utils.secret_vault import decrypt_secrets_in_dict
from utils.orbit4_client import (
    Orbit4Client, Orbit4APIError, map_gymaxis_status_to_orbit4_patch,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _stamp(case_id: str, sync: dict) -> None:
    await db.svc_cases.update_one(
        {"id": case_id}, {"$set": {"orbit4_sync": sync, "updated_at": _now()}})


async def resync_case(case: dict, user: dict) -> dict:
    """Mirror a Pulse case's status onto its linked Orbit4 ticket. Returns a
    small result dict; also persists svc_cases.orbit4_sync."""
    case_id = case.get("id")
    org_id = case.get("organization_id")
    ticket_id = case.get("orbit4_ticket_id")

    if not ticket_id:
        sync = {"status": "skipped", "reason": "no_orbit4_ticket", "at": _now()}
        await _stamp(case_id, sync)
        return {"ok": False, "reason": "This case has no linked Orbit 4 ticket."}

    conn = await db.svc_orbit4_connections.find_one({"organization_id": org_id})
    if not conn:
        sync = {"status": "error", "reason": "no_connection", "at": _now()}
        await _stamp(case_id, sync)
        return {"ok": False, "reason": "No Orbit 4 connection configured for this organisation."}

    conn = decrypt_secrets_in_dict(conn)
    api_token = (conn.get("api_token") or "").strip()
    if not api_token:
        sync = {"status": "error", "reason": "no_api_token", "at": _now()}
        await _stamp(case_id, sync)
        return {"ok": False, "reason": "Orbit 4 connection has no API token."}

    base_url = conn.get("base_url") or "https://api.orbit4.org/v1"
    patch = map_gymaxis_status_to_orbit4_patch(
        case.get("status"), case.get("resolution_notes") or case.get("resolution"))
    client = Orbit4Client(base_url=base_url, api_token=api_token)

    try:
        await client.update_ticket(int(ticket_id), patch)
    except (Orbit4APIError, ValueError, Exception) as e:  # noqa: BLE001 — never crash the caller
        logger.warning("orbit4 resync failed for case %s: %s", case_id, e)
        sync = {"status": "error", "reason": str(e)[:250], "at": _now(),
                "attempted_status": patch.get("status")}
        await _stamp(case_id, sync)
        return {"ok": False, "reason": f"Orbit 4 update failed: {str(e)[:200]}"}

    sync = {"status": "synced", "orbit4_status": patch.get("status"),
            "at": _now(), "by": user.get("id")}
    await _stamp(case_id, sync)
    return {"ok": True, "orbit4_status": patch.get("status")}
