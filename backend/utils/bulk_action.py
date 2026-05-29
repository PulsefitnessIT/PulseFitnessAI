"""Bulk-action security guards (F-10 — Iter 220be).

Every operator-facing bulk endpoint (CRM contacts/deals/activities,
membership members, churn-approval, territory re-assign, mod transfer
…) MUST run incoming payloads through these guards before issuing the
underlying writes. The guards enforce:

    1. ``max_rows`` cap (default 200) — DoS + accidental fat-finger.
    2. Per-row tenant filter — the bulk action MUST execute against
       a server-side ``$in`` query that also pins ``organization_id``
       so a hostile payload mixing other-tenant IDs is silently dropped.
    3. Per-row audit — one ``bulk_action_events`` row per affected
       resource id captures who did what to what, when, from where.

Usage::

    from utils.bulk_action import (
        validate_bulk_ids,
        assert_same_tenant_payload,
        record_bulk_action,
    )

    ids = validate_bulk_ids(body.get("ids"), max_rows=200)
    affected = await db.contacts.find(
        {"id": {"$in": ids}, "organization_id": org_id},
        {"_id": 0, "id": 1},
    ).to_list(len(ids))
    affected_ids = [r["id"] for r in affected]
    # … perform writes …
    await record_bulk_action(
        name="contacts.bulk_delete",
        actor=user, org_id=org_id, ids=affected_ids, request=request,
    )
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, Request

from utils.database import db


logger = logging.getLogger(__name__)

# Default per-call cap. Individual endpoints may pass a smaller value
# (e.g. destructive bulk-delete should typically be 50) but MUST NOT
# exceed this hard ceiling — the registry rejects anything bigger.
DEFAULT_MAX_ROWS = int(os.environ.get("BULK_ACTION_DEFAULT_MAX_ROWS", "200"))
HARD_CEILING = int(os.environ.get("BULK_ACTION_HARD_CEILING", "1000"))


def validate_bulk_ids(
    ids: Optional[Iterable[str]],
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    field_label: str = "ids",
) -> list[str]:
    """Validate + de-dupe an inbound list of resource IDs.

    Raises 400 for non-list, empty, > max_rows or non-string entries.
    Returns the de-duplicated list preserving original order.
    """
    if max_rows > HARD_CEILING:
        # Defensive — refuse insane callers configuring an unbounded cap.
        raise HTTPException(500, "bulk-action max_rows exceeds hard ceiling")
    if not isinstance(ids, list):
        raise HTTPException(400, f"{field_label} must be a list")
    if not ids:
        raise HTTPException(400, f"{field_label} is required")
    if len(ids) > max_rows:
        raise HTTPException(
            400,
            f"Too many rows ({len(ids)}). Max {max_rows} per bulk action.",
        )
    seen: set[str] = set()
    cleaned: list[str] = []
    for v in ids:
        if not isinstance(v, str):
            raise HTTPException(400, f"{field_label} entries must be strings")
        v = v.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        cleaned.append(v)
    if not cleaned:
        raise HTTPException(400, f"{field_label} contained only blanks")
    return cleaned


def assert_destructive_role(user: dict) -> None:
    """Destructive bulk actions (delete-many, archive-many) require an
    elevated operator role. Master/Pulse admins always pass; otherwise
    the caller must be an owner / manager / org admin. Front-line
    staff cannot mass-delete tenant data.
    """
    if user.get("is_master_admin") or user.get("is_pulse_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role in {"owner", "manager", "admin", "org_admin"}:
        return
    raise HTTPException(
        403,
        "Destructive bulk actions require owner / manager role.",
    )


async def record_bulk_action(
    *,
    name: str,
    actor: dict,
    org_id: Optional[str],
    ids: list[str],
    request: Optional[Request] = None,
    succeeded_ids: Optional[list[str]] = None,
    failed_ids: Optional[list[str]] = None,
    extra: Optional[dict] = None,
) -> int:
    """Write one row per affected resource id to ``bulk_action_events``.

    The collection is the same shape as ``export_events`` (F-20) so
    the master-admin audit dashboard can fold both into one stream.
    Returns the number of rows inserted.
    """
    if not ids:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    ip = ""
    ua = ""
    if request is not None:
        try:
            client = request.client
            ip = (client.host if client else "") or ""
            ua = (request.headers.get("user-agent") or "")[:200]
        except Exception:
            pass
    succ = set(succeeded_ids or [])
    fail = set(failed_ids or [])
    rows = []
    for rid in ids:
        status = (
            "succeeded" if rid in succ
            else "failed" if rid in fail
            else "attempted"
        )
        rows.append({
            "action": name,
            "actor_id": actor.get("id") or "",
            "actor_role": (actor.get("role") or "")[:60],
            "actor_email": (actor.get("email") or "")[:200],
            "organization_id": org_id or "",
            "resource_id": rid,
            "status": status,
            "ip": ip,
            "user_agent": ua,
            "extra": extra or {},
            "created_at": now,
        })
    try:
        await db.bulk_action_events.insert_many(rows)
        return len(rows)
    except Exception as e:  # never let audit failures break the write
        logger.warning("bulk_action audit insert failed name=%s err=%s", name, e)
        return 0


async def filter_same_tenant_ids(
    ids: list[str],
    *,
    collection: str,
    org_id: str,
    id_field: str = "id",
    org_field: str = "organization_id",
) -> list[str]:
    """Resolve the subset of ``ids`` that genuinely belong to ``org_id``.

    Returns the resolved id list (preserves input order). Callers
    should then run the underlying write against this filtered set —
    any other-tenant IDs are silently dropped to avoid leaking which
    IDs exist in foreign tenants via differential error messages.
    """
    if not ids:
        return []
    rows = await db[collection].find(
        {id_field: {"$in": ids}, org_field: org_id},
        {"_id": 0, id_field: 1},
    ).to_list(len(ids))
    found = {r[id_field] for r in rows}
    return [v for v in ids if v in found]


__all__ = [
    "DEFAULT_MAX_ROWS",
    "HARD_CEILING",
    "validate_bulk_ids",
    "assert_destructive_role",
    "record_bulk_action",
    "filter_same_tenant_ids",
]
