"""Audit-log + 404/403 disambiguation helpers — Iter 220ax (Wave 6).

Closes 4 audit-hygiene findings from the risk register:

  * **F-20** — Audit-log decorator on exports. ``@audit_export(name)``
    records every PDF/CSV/ZIP export into ``db.export_events``: actor,
    org, resource id (when extractable), IP, user-agent, response size,
    timestamp.
  * **F-28** — Impersonation audit. ``record_impersonation_event(...)``
    writes a dedicated row to ``db.impersonation_events`` (separate
    from the generic ``activity_logs`` so pen-testers can grep cleanly).
  * **F-29** — Engineer-app horizontal-access helpers.
    ``assert_engineer_owns()`` raises a 404 (not 403, to defeat
    enumeration) when the engineer caller doesn't own the row.
  * **F-33** — 404-vs-403 disambiguation. ``not_found_unless_owned()``
    is the canonical "is-this-mine?" gate; same-tenant rows return the
    row, non-same-tenant rows return 404 so the caller can't probe
    other tenants by ID.
"""
from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from utils.database import db

log = logging.getLogger(__name__)


# ── F-20 · @audit_export decorator ────────────────────────────────


def _extract_actor(args: tuple, kwargs: dict) -> tuple[dict | None, Request | None]:
    """Look through (args, kwargs) for the first dict that smells like
    an authenticated user, and the first ``Request`` instance."""
    user: dict | None = None
    request: Request | None = None
    for v in (*args, *kwargs.values()):
        if user is None and isinstance(v, dict) and ("id" in v or "email" in v):
            user = v
        if request is None and isinstance(v, Request):
            request = v
    return user, request


def audit_export(name: str, *, resource_kwarg: str | None = None):
    """Decorator that records the export to ``db.export_events``
    AFTER the wrapped endpoint returns successfully.

    Best-effort — DB write failures never break the user-facing
    download. Use on any endpoint that streams a file, generates a
    PDF, or returns a CSV download.

    Example::

        @router.get("/tenders/{tender_id}/export/pitch")
        @audit_export("tender.pitch.pdf", resource_kwarg="tender_id")
        async def export_pitch(tender_id: str, user=Depends(get_crm_user)):
            ...
    """
    def _decorator(fn: Callable[..., Awaitable[Any]]):

        @functools.wraps(fn)
        async def _wrapper(*args, **kwargs):
            result = await fn(*args, **kwargs)
            try:
                user, request = _extract_actor(args, kwargs)
                resource_id = (
                    kwargs.get(resource_kwarg) if resource_kwarg else None
                )
                size = None
                if hasattr(result, "headers"):
                    cl = result.headers.get("content-length") if result.headers else None
                    try:
                        size = int(cl) if cl is not None else None
                    except (ValueError, TypeError):
                        size = None
                elif hasattr(result, "body") and result.body is not None:
                    size = len(result.body)
                doc = {
                    "id": f"exp_{datetime.now(timezone.utc).timestamp()}_{os.urandom(4).hex()}",
                    "name": name,
                    "resource_id": resource_id,
                    "actor_id": (user or {}).get("id"),
                    "actor_email": (user or {}).get("email"),
                    "organization_id": (user or {}).get("organization_id"),
                    "ip": (request.client.host if (request and request.client) else None),
                    "user_agent": (
                        (request.headers.get("user-agent") or "")[:200] if request else None
                    ),
                    "response_bytes": size,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.export_events.insert_one(doc)
            except Exception:
                # Audit-log failures must NEVER break the download.
                log.exception("[audit-export] failed to record %s", name)
            return result

        return _wrapper

    return _decorator


# ── F-28 · impersonation audit ────────────────────────────────────


async def record_impersonation_event(
    *,
    actor: dict,
    target_user_id: str,
    target_email: str | None,
    target_organization_id: str | None,
    token_jti: str | None,
    expires_at: datetime | str | None,
    request: Request | None = None,
    reason: str | None = None,
) -> None:
    """Persist an impersonation row to ``db.impersonation_events``.

    Separate from ``activity_logs`` so the security team can grep this
    collection in isolation during a pen-test or incident review.
    Best-effort — DB failures swallowed.
    """
    try:
        if isinstance(expires_at, datetime):
            expires_at = expires_at.isoformat()
        doc = {
            "id": f"imp_{datetime.now(timezone.utc).timestamp()}_{os.urandom(4).hex()}",
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "actor_role": actor.get("role"),
            "target_user_id": target_user_id,
            "target_email": target_email,
            "target_organization_id": target_organization_id,
            "token_jti": token_jti,
            "expires_at": expires_at,
            "reason": (reason or "")[:500],
            "ip": (request.client.host if (request and request.client) else None),
            "user_agent": (
                (request.headers.get("user-agent") or "")[:200] if request else None
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.impersonation_events.insert_one(doc)
    except Exception:
        log.exception("[impersonation-audit] failed to record event")


# ── F-29 / F-33 · 404-vs-403 disambiguation ───────────────────────


def not_found_unless_owned(
    doc: dict | None,
    user: dict | None,
    *,
    label: str = "Resource",
    tenant_key: str = "organization_id",
) -> dict:
    """Return ``doc`` when the caller owns it (same tenant) else raise
    404 — never 403 — so an attacker can't enumerate IDs by comparing
    response codes.

    Master admins / Pulse admins always pass. Single-tenant rows
    without a tenant key (legacy data) also pass (defence-in-depth
    must not break legitimate ops mid-migration).
    """
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    if not user:
        # No authenticated user → behave as not-found (route should
        # have a Depends gate; this is the safety net).
        raise HTTPException(status_code=404, detail=f"{label} not found")
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return doc
    tenant_a = doc.get(tenant_key)
    tenant_b = user.get(tenant_key)
    if tenant_a is None or tenant_b is None:
        return doc
    if tenant_a == tenant_b:
        return doc
    log.info(
        "[acl] cross-tenant access denied label=%s actor=%s actor_org=%s row_org=%s",
        label, user.get("email"), tenant_b, tenant_a,
    )
    raise HTTPException(status_code=404, detail=f"{label} not found")


def assert_engineer_owns(
    engineer_id: str | None,
    row_engineer_id: str | None,
    *,
    label: str = "Resource",
) -> None:
    """Engineer-app horizontal-access gate. Raises 404 (not 403) when
    the engineer caller doesn't own the row.

    F-29 — Iter 220ax. Use on any Engineer-App endpoint that takes a
    resource id from the URL and reads / mutates it without a full
    re-check against the engineer's owned set.
    """
    if not engineer_id or not row_engineer_id or engineer_id != row_engineer_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")


# ── F-20 + F-28 startup index helper ──────────────────────────────


async def ensure_indexes() -> None:
    """Build TTL + lookup indexes for the two new audit collections."""
    try:
        await db.export_events.create_index("created_at")
        await db.export_events.create_index([("organization_id", 1), ("created_at", -1)])
        await db.export_events.create_index([("actor_id", 1), ("created_at", -1)])
    except Exception:
        log.exception("export_events index build failed")
    try:
        await db.impersonation_events.create_index("created_at")
        await db.impersonation_events.create_index([("actor_id", 1), ("created_at", -1)])
        await db.impersonation_events.create_index([("target_user_id", 1), ("created_at", -1)])
    except Exception:
        log.exception("impersonation_events index build failed")


__all__ = [
    "audit_export",
    "record_impersonation_event",
    "not_found_unless_owned",
    "assert_engineer_owns",
    "ensure_indexes",
]
