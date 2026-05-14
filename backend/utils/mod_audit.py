"""MOD Audit Trail — tamper-evident append-only ledger.

Iter 216h115 — single source of truth for every mutating action on a MOD
site or HQ org. Each row carries a SHA-256 hash of the previous row's
hash + its own canonical payload, forming a chain. Tampering with any
row breaks every subsequent row's verification — surfacing in the
``verify_audit_chain()`` integrity check.

Schema (``db.mod_audit_log``):
    id              str   uuid4
    site_id         str   target organisation (or HQ org) id
    user_id         str   actor user id (or None for system)
    actor_email     str   denormalised for human-readable export
    actor_role      str   role at time of action (owner/manager/staff)
    action          str   canonical action verb — see ACTION_VERBS below
    target_type     str   resource type touched (issue, equipment, …)
    target_id       str   resource id (or None for collection ops)
    payload         dict  redacted, JSON-safe metadata
    ip              str   request IP if available
    user_agent      str   truncated UA string if available
    prev_hash       str   hash of preceding row (or "GENESIS" for first)
    row_hash        str   sha256(prev_hash + canonical_payload + created_at)
    created_at      str   ISO timestamp (UTC, microsecond precision)

The helper is intentionally fail-soft — auditing must never block the
operation that triggered it. Failures are logged but swallowed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from utils.database import db

logger = logging.getLogger(__name__)

# Sensitive keys we never persist on the audit row's payload.
_REDACT_KEYS = {
    "password", "password_hash", "new_password", "site_code",
    "bcrypt", "token", "refresh_token", "api_key", "secret",
}

# Canonical action verbs — one source of truth so exports / filters / UI
# can group consistently. Extend here when adding new audited events.
ACTION_VERBS = {
    # Identity / access
    "login.success", "login.failure", "site_login.provision",
    "site_login.rotate", "password.rotate",
    # Fault lifecycle
    "fault.create", "fault.update", "fault.resolve", "fault.reopen",
    "fault.confirm_fix", "fault.classification_flag",
    # Equipment
    "equipment.create", "equipment.update", "equipment.delete",
    "equipment.move", "equipment.supplier_change",
    # Staff
    "staff.create", "staff.update", "staff.delete",
    "staff.transfer", "staff.posting_out",
    # Suppliers
    "supplier.create", "supplier.update", "supplier.delete",
    "supplier.notify_assignment",
    # Drills / red-team
    "drill.start", "drill.complete",
    # Compliance / inspections (future)
    "compliance.event",
}


def _canonicalise(value: Any) -> Any:
    """Return a JSON-safe, deterministic representation of ``value``.

    Used as the input to the hash so that two structurally-identical
    payloads hash identically regardless of dict key order.
    """
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in sorted(value.items())
                if k not in _REDACT_KEYS}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _hash_row(prev_hash: str, payload: dict, created_at: str) -> str:
    """sha256 of prev_hash || canonical(payload) || created_at."""
    canonical = json.dumps(_canonicalise(payload), separators=(",", ":"))
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(b"|")
    digest.update(canonical.encode("utf-8"))
    digest.update(b"|")
    digest.update(created_at.encode("utf-8"))
    return digest.hexdigest()


async def audit_event(
    *,
    site_id: str,
    action: str,
    user: Optional[dict] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload: Optional[dict] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """Append a tamper-evident audit row.

    Returns the persisted row on success, or ``None`` if the write
    failed (auditing must never block the calling operation).
    """
    if action not in ACTION_VERBS:
        logger.warning("[mod-audit] unknown action verb %r — accepting anyway",
                       action)
    try:
        # Fetch the latest row to chain off. We index on (site_id,
        # created_at) so this is O(1).
        prev = await db.mod_audit_log.find_one(
            {"site_id": site_id},
            sort=[("created_at", -1)],
            projection={"_id": 0, "row_hash": 1},
        )
        prev_hash = (prev or {}).get("row_hash") or "GENESIS"
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        clean_payload = _canonicalise(payload or {})
        row_hash = _hash_row(prev_hash, clean_payload, now)
        row = {
            "id": str(uuid.uuid4()),
            "site_id": site_id,
            "user_id": (user or {}).get("id"),
            "actor_email": (user or {}).get("email"),
            "actor_role": (user or {}).get("role"),
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": clean_payload,
            "ip": ip,
            "user_agent": (user_agent or "")[:200] or None,
            "prev_hash": prev_hash,
            "row_hash": row_hash,
            "created_at": now,
        }
        await db.mod_audit_log.insert_one(row)
        row.pop("_id", None)
        return row
    except Exception as exc:  # pragma: no cover
        logger.warning("[mod-audit] append failed (%s): %s", action, exc)
        return None


async def list_audit_for_site(site_id: str, limit: int = 500) -> list[dict]:
    """Return the most-recent audit rows for ``site_id`` (newest first)."""
    return await db.mod_audit_log.find(
        {"site_id": site_id}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)


async def verify_audit_chain(site_id: str) -> dict:
    """Walk the chain forwards and verify each row's hash. Returns a
    summary dict ``{rows, valid, first_break_at}``. Used by HQ exports
    and integrity checks.

    Pre-chain rows (legacy, no ``row_hash`` field) are tolerated and
    counted under ``legacy_rows`` — the chain officially starts from
    the first row that has a hash present.
    """
    cursor = db.mod_audit_log.find(
        {"site_id": site_id}, {"_id": 0},
    ).sort("created_at", 1)
    prev_hash = "GENESIS"
    rows = 0
    legacy_rows = 0
    first_break: Optional[str] = None
    async for row in cursor:
        if not row.get("row_hash"):
            legacy_rows += 1
            continue
        rows += 1
        expected = _hash_row(prev_hash, row.get("payload", {}),
                             row.get("created_at", ""))
        if expected != row.get("row_hash") or prev_hash != row.get("prev_hash"):
            first_break = row.get("created_at")
            break
        prev_hash = row["row_hash"]
    return {
        "rows": rows,
        "legacy_rows": legacy_rows,
        "valid": first_break is None,
        "first_break_at": first_break,
    }
