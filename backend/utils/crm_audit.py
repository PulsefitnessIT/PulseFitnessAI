"""
CRM Enterprise Audit Trail — iter 215dd.

Captures who changed what and when across the key CRM entities
(contact / company / opportunity / contract). Write-path is a single
helper `record_audit` used by CRM v2 create/update/delete endpoints;
read-path is exposed via `routes/crm_audit.py`.

Design goals:
 - Zero external deps; stored in `crm_audit_log` Mongo collection.
 - Field-level diffs on UPDATE so managers can pinpoint "John lowered
   the deal value from £50k to £30k at 14:22 on Tuesday".
 - Never block business writes — every call is best-effort, wrapped in
   a try/except inside the caller helper.
 - Small, bounded payloads: we only log fields the caller opted into.
"""
from datetime import datetime, timezone
from typing import Any
import uuid

from utils.database import db


# Fields we DO NOT want to log (secrets / noise / bloat / PII with no value).
_EXCLUDE_FIELDS = {
    "password", "password_hash", "mfa_secret", "_id", "id",
    "organization_id", "created_at", "updated_at", "stage_history",
    "rr_cursor",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _diff(before: dict | None, after: dict | None) -> list[dict]:
    """Return a list of {field, before, after} for fields that changed."""
    if not before and not after:
        return []
    if not before:
        return [
            {"field": k, "before": None, "after": v}
            for k, v in (after or {}).items()
            if k not in _EXCLUDE_FIELDS and v not in (None, "", [], {})
        ]
    if not after:
        return []
    changed: list[dict] = []
    keys = set((before or {}).keys()) | set((after or {}).keys())
    for k in keys:
        if k in _EXCLUDE_FIELDS:
            continue
        b = before.get(k) if before else None
        a = after.get(k) if after else None
        if b != a:
            changed.append({"field": k, "before": b, "after": a})
    return changed


async def record_audit(
    *,
    entity_type: str,
    entity_id: str,
    action: str,  # create | update | delete | stage_change | sign | approve
    user: dict,
    before: dict | None = None,
    after: dict | None = None,
    summary: str = "",
    extra: dict | None = None,
) -> None:
    """Persist a single audit row. Best-effort — never raises."""
    try:
        org_id = (user or {}).get("organization_id", "")
        changes = _diff(before, after) if action in ("update", "stage_change") else []
        entry = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "actor_id": (user or {}).get("id", ""),
            "actor_name": (user or {}).get("full_name", "") or (user or {}).get("email", ""),
            "actor_email": (user or {}).get("email", ""),
            "summary": summary or _default_summary(entity_type, action, after or before or {}),
            "changes": changes,
            "at": _now(),
        }
        if extra:
            entry["extra"] = extra
        await db.crm_audit_log.insert_one(entry)
    except Exception:
        # Absolutely never bubble — audit failure must not break business writes.
        pass


def _default_summary(entity_type: str, action: str, doc: dict) -> str:
    name = (
        doc.get("title")
        or doc.get("name")
        or " ".join(filter(None, [doc.get("first_name", ""), doc.get("last_name", "")])).strip()
        or entity_type.title()
    )
    verb = {
        "create": "created",
        "update": "updated",
        "delete": "deleted",
        "stage_change": "moved to new stage",
        "sign": "signed",
        "approve": "approved",
    }.get(action, action)
    return f"{entity_type.title()} {verb}: {name}".strip()


async def audit_timeline(
    *,
    organization_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict[str, Any]]:
    q: dict = {"organization_id": organization_id}
    if entity_type:
        q["entity_type"] = entity_type
    if entity_id:
        q["entity_id"] = entity_id
    if actor_id:
        q["actor_id"] = actor_id
    rows = (
        await db.crm_audit_log
        .find(q, {"_id": 0})
        .sort("at", -1)
        .skip(max(0, skip))
        .limit(max(1, min(200, limit)))
        .to_list(max(1, min(200, limit)))
    )
    return rows
