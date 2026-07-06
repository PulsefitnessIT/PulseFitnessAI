"""
Service Desk — self-serve Orbit 4 connection.

Lets a Service Desk admin connect their OWN Orbit 4 account WITHOUT any
involvement from the Pulse Fitness master admin. Each desk org gets:
  - a unique webhook URL  (/api/webhooks/orbit4/{connection_key})
  - its own API token + webhook secret (encrypted at rest)
Inbound Orbit 4 tickets land as Service Desk cases in the connection's org.
"""
from datetime import datetime, timezone, timedelta
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from utils.database import db
from utils.auth import get_current_user
from utils.secret_vault import (
    encrypt_secrets_in_dict,
    decrypt_secrets_in_dict,
    redact_secrets_in_dict,
)

router = APIRouter(prefix="/svc/orbit4", tags=["Service Desk · Orbit 4"])

ORBIT4_DEFAULT_BASE_URL = "https://api.orbit4.org/v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_orbit4_admin(user: dict = Depends(get_current_user)) -> dict:
    """Org owner / admin, Service Desk agent or Master Admin may manage the
    connection. Scoped to the caller's own organisation."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    if not org_id:
        raise HTTPException(400, "Organization context required")
    allowed = (
        user.get("is_master_admin")
        or user.get("is_service_desk")
        or user.get("is_pulse_admin")
        or user.get("role") in ("owner", "admin", "pulse_master_admin")
    )
    if not allowed:
        raise HTTPException(403, "Service Desk admin access required")
    return user


def _webhook_url(request: Request, connection_key: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/webhooks/orbit4/{connection_key}"


async def _get_or_create_connection(org_id: str, user: dict) -> dict:
    conn = await db.svc_orbit4_connections.find_one({"organization_id": org_id})
    if conn:
        return conn
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "connection_key": secrets.token_urlsafe(24),
        "enabled": False,
        "api_token": "",
        "webhook_secret": "",
        "base_url": ORBIT4_DEFAULT_BASE_URL,
        "created_by_id": user.get("id"),
        "created_by_email": user.get("email"),
        "last_event_at": None,
        "stats": {"events_total": 0},
        "created_at": _now(),
        "updated_at": _now(),
    }
    encrypt_secrets_in_dict(doc)
    await db.svc_orbit4_connections.insert_one(doc)
    return doc


def _public_view(conn: dict, request: Request) -> dict:
    safe = redact_secrets_in_dict({k: v for k, v in conn.items() if k != "_id"})
    # The admin is authorised, so returning their own connection key (which
    # they must paste into Orbit 4 anyway) is expected. The frontend prefers
    # building the URL from REACT_APP_BACKEND_URL via `webhook_path`.
    safe["webhook_path"] = f"/api/webhooks/orbit4/{conn['connection_key']}"
    safe["webhook_url"] = _webhook_url(request, conn["connection_key"])
    return safe


@router.get("/connection")
async def get_connection(request: Request, user: dict = Depends(_require_orbit4_admin)):
    """Get (auto-creating on first call) the caller-org Orbit 4 connection."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    conn = await _get_or_create_connection(org_id, user)
    return _public_view(conn, request)


@router.put("/connection")
async def update_connection(request: Request, body: dict,
                            user: dict = Depends(_require_orbit4_admin)):
    """Update connection fields. Secrets are encrypted at rest; omit a secret
    to leave it unchanged, send empty string to clear it."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    conn = await _get_or_create_connection(org_id, user)

    allowed = ("enabled", "api_token", "webhook_secret", "base_url", "web_base_url")
    update = {k: v for k, v in body.items() if k in allowed}
    # Treat the redaction mask as "leave unchanged".
    for secret in ("api_token", "webhook_secret"):
        if update.get(secret) in ("••••••",):
            update.pop(secret, None)
    if "enabled" in update:
        update["enabled"] = bool(update["enabled"])
    if not update.get("base_url"):
        update.pop("base_url", None)
    update["updated_at"] = _now()
    encrypt_secrets_in_dict(update)

    await db.svc_orbit4_connections.update_one(
        {"organization_id": org_id}, {"$set": update})
    fresh = await db.svc_orbit4_connections.find_one({"organization_id": org_id})
    return _public_view(fresh, request)


@router.post("/connection/rotate-key")
async def rotate_key(request: Request, user: dict = Depends(_require_orbit4_admin)):
    """Regenerate the webhook key — invalidates the old webhook URL."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    await _get_or_create_connection(org_id, user)
    new_key = secrets.token_urlsafe(24)
    await db.svc_orbit4_connections.update_one(
        {"organization_id": org_id},
        {"$set": {"connection_key": new_key, "updated_at": _now()}})
    fresh = await db.svc_orbit4_connections.find_one({"organization_id": org_id})
    return _public_view(fresh, request)


@router.post("/connection/test")
async def test_connection(user: dict = Depends(_require_orbit4_admin)):
    """Best-effort outbound connectivity check against the Orbit 4 API."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    conn = await db.svc_orbit4_connections.find_one({"organization_id": org_id})
    if not conn:
        raise HTTPException(404, "No connection configured")
    conn = decrypt_secrets_in_dict(conn)
    token = conn.get("api_token") or ""
    if not token:
        return {"ok": False, "reason": "no_api_token",
                "message": "Add your Orbit 4 API token before testing."}
    from utils.orbit4_client import Orbit4Client, Orbit4APIError
    client = Orbit4Client(
        base_url=conn.get("base_url") or ORBIT4_DEFAULT_BASE_URL,
        api_token=token,
        user_agent="PulseFitness-ServiceDesk/1.0",
    )
    try:
        await client.list_assets(limit=1)
        return {"ok": True, "message": "Connected to Orbit 4 successfully."}
    except Orbit4APIError as e:
        return {"ok": False, "reason": "api_error", "message": str(e)[:300]}
    except Exception as e:  # network/timeout — surface gracefully
        return {"ok": False, "reason": "unreachable", "message": str(e)[:300]}


@router.get("/connection/activity")
async def connection_activity(user: dict = Depends(_require_orbit4_admin)):
    """Summary of Orbit 4 cases + connection health for this org."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    q = {"organization_id": org_id, "source": "orbit4"}
    total = await db.svc_cases.count_documents(q)
    recent = await db.svc_cases.find(
        q, {"_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1,
            "priority": 1, "created_at": 1, "orbit4_ticket_id": 1},
    ).sort("created_at", -1).limit(10).to_list(10)

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cases_week = await db.svc_cases.count_documents({**q, "created_at": {"$gte": week_ago}})
    error_count = await db.svc_cases.count_documents(
        {"organization_id": org_id, "orbit4_sync.status": "error"})
    last_sync = await db.svc_cases.find(
        {"organization_id": org_id, "orbit4_sync.at": {"$exists": True, "$ne": None}},
        {"_id": 0, "orbit4_sync": 1},
    ).sort("orbit4_sync.at", -1).limit(1).to_list(1)
    conn = await db.svc_orbit4_connections.find_one(
        {"organization_id": org_id}, {"_id": 0, "last_event_at": 1, "enabled": 1})

    return {
        "cases_total": total,
        "recent_cases": recent,
        "cases_this_week": cases_week,
        "error_count": error_count,
        "enabled": bool((conn or {}).get("enabled")),
        "last_inbound_at": (conn or {}).get("last_event_at"),
        "last_outbound": (last_sync[0]["orbit4_sync"] if last_sync else None),
    }


@router.post("/cases/{case_id}/resync")
async def resync_case_endpoint(case_id: str, user: dict = Depends(get_current_user)):
    """Manual 'Sync now / Retry' — re-push a case's status to Orbit 4."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    case = await db.svc_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")
            or case.get("organization_id") == org_id):
        raise HTTPException(403, "Not allowed for this case")
    try:
        from utils.orbit4_outbound import resync_case
    except ImportError:
        raise HTTPException(501, "Orbit 4 outbound sync is not enabled on this deployment")
    result = await resync_case(case, user)
    fresh = await db.svc_cases.find_one({"id": case_id}, {"_id": 0, "orbit4_sync": 1})
    return {**result, "orbit4_sync": (fresh or {}).get("orbit4_sync")}


# ── Engineer ↔ Orbit 4 user mapping (Phase 2) ────────────────────

@router.get("/engineers")
async def list_engineer_mappings(user: dict = Depends(_require_orbit4_admin)):
    """Engineers in the org with their current Orbit 4 user mapping."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    engineers = await db.svc_engineers.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1,
         "orbit4_user_id": 1},
    ).to_list(500)
    o4_users = await db.orbit4_users.find(
        {}, {"_id": 0, "orbit4_user_id": 1, "first_name": 1, "last_name": 1,
             "email": 1},
    ).to_list(500)
    return {"engineers": engineers, "orbit4_users": o4_users}


@router.put("/engineers/{engineer_id}")
async def set_engineer_mapping(engineer_id: str, body: dict,
                               user: dict = Depends(_require_orbit4_admin)):
    """Set or clear an engineer's Orbit 4 user id."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    eng = await db.svc_engineers.find_one(
        {"id": engineer_id, "organization_id": org_id}, {"_id": 0, "id": 1})
    if not eng:
        raise HTTPException(404, "Engineer not found")
    raw = body.get("orbit4_user_id")
    update = {"orbit4_user_mapped_at": _now()}
    if raw in (None, ""):
        update["orbit4_user_id"] = None
    else:
        try:
            update["orbit4_user_id"] = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, "orbit4_user_id must be an integer")
    await db.svc_engineers.update_one({"id": engineer_id}, {"$set": update})
    return {"ok": True, "engineer_id": engineer_id,
            "orbit4_user_id": update["orbit4_user_id"]}
