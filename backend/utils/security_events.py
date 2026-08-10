"""Append-only security telemetry (OWASP logging & monitoring · sections 32/34/35).

Every access-control denial, privileged state transition, mass-assignment
attempt and abnormal-behaviour signal is written here as an *immutable*
audit row: routes only ever INSERT — there is no update/delete API, and the
Master Admin Security Alert Centre reads it read-only.

Design goals
------------
* Non-blocking & fail-open: security logging must NEVER break a request. All
  writes are wrapped in try/except and also mirrored to the structured logger
  so telemetry survives even if Mongo is briefly unreachable.
* Correlatable: every row carries actor, tenant, site, action, resource,
  result, source IP/UA, HTTP method/path and a request/correlation id.
* No secrets: we never persist tokens, passwords or raw payloads — only the
  NAMES of any rejected/protected fields.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from utils.database import db

logger = logging.getLogger("security")

# Severities
SEV_INFO = "info"
SEV_WARNING = "warning"
SEV_CRITICAL = "critical"

_COLLECTION = "security_events"


def _client_ip_safe(request) -> Optional[str]:
    if request is None:
        return None
    try:
        from utils.security import client_ip
        return client_ip(request)
    except Exception:
        try:
            return request.client.host if request.client else None
        except Exception:
            return None


async def log_security_event(
    event_type: str,
    *,
    user: Optional[dict] = None,
    request=None,
    severity: str = SEV_WARNING,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    result: str = "denied",
    detail: Optional[str] = None,
    tenant_id: Optional[str] = None,
    site_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Persist a single security event. Best-effort — never raises."""
    now = datetime.now(timezone.utc)
    actor = user or {}
    org = tenant_id or actor.get("organization_id") or actor.get("_acting_org_id")

    ip = ua = req_id = path = method = None
    if request is not None:
        try:
            ip = _client_ip_safe(request)
            ua = (request.headers.get("user-agent") or "")[:300]
            req_id = (
                request.headers.get("x-request-id")
                or request.headers.get("x-correlation-id")
            )
            path = str(request.url.path)
            method = request.method
        except Exception:
            pass
    if not req_id:
        req_id = str(uuid.uuid4())

    doc: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "severity": severity,
        "result": result,
        "actor_id": actor.get("id"),
        "actor_email": actor.get("email"),
        "actor_role": (actor.get("role") or None),
        "is_master_admin": bool(actor.get("is_master_admin") or actor.get("is_pulse_admin")),
        "tenant_id": org,
        "site_id": site_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "detail": detail,
        "ip": ip,
        "user_agent": ua,
        "method": method,
        "path": path,
        "request_id": req_id,
        "created_at": now.isoformat(),
        "ts": now,
    }
    if extra:
        # Only shallow, non-sensitive metadata (never raw payloads/secrets).
        doc["meta"] = {k: v for k, v in extra.items() if k not in ("password", "token", "secret")}

    try:
        await db[_COLLECTION].insert_one(dict(doc))
    except Exception:
        logger.exception("security_events insert failed for %s", event_type)

    # Structured mirror (survives DB outages; feeds log-based alerting).
    logger.warning(
        "SECURITY event=%s severity=%s result=%s actor=%s tenant=%s resource=%s:%s action=%s ip=%s req=%s detail=%s",
        event_type, severity, result, actor.get("id"), org,
        resource_type, resource_id, action, ip, req_id, detail,
    )


async def ensure_indexes() -> None:
    """Create the query indexes for the Security Alert Centre. Idempotent."""
    try:
        await db[_COLLECTION].create_index([("ts", -1)])
        await db[_COLLECTION].create_index([("event_type", 1), ("ts", -1)])
        await db[_COLLECTION].create_index([("severity", 1), ("ts", -1)])
        await db[_COLLECTION].create_index([("tenant_id", 1), ("ts", -1)])
        await db[_COLLECTION].create_index([("actor_id", 1), ("ts", -1)])
        await db[_COLLECTION].create_index([("ip", 1), ("ts", -1)])
    except Exception:
        logger.exception("security_events index setup failed")


__all__ = [
    "log_security_event",
    "ensure_indexes",
    "SEV_INFO", "SEV_WARNING", "SEV_CRITICAL",
]
