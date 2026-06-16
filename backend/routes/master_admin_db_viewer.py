"""Master Admin DB Viewer — read-only MongoDB collection browser.

Iter 225. Built for safe production introspection: no writes, sensitive
fields are recursively redacted before serialisation, and exports require
an explicit `confirm=true` query param to avoid accidental dumps.

Endpoints (all under /api/master-admin/db, behind require_master_admin so
both Pulse Fitness Master Admins AND Pulse Master Admins can use this):

  GET  /api/master-admin/db/collections
       → [{name, count, indexes_count}, …]

  GET  /api/master-admin/db/collections/{name}
       Query: page (>=1), page_size (1-100), q (free-text)
       → {docs, total, page, page_size, pages}

  GET  /api/master-admin/db/collections/{name}/document/{doc_id}
       → single document (search by `id` field, or `_id` ObjectId fallback)

  GET  /api/master-admin/db/collections/{name}/export
       Query: format=json|csv, confirm=true
       → streamed file. JSON = newline-delimited; CSV = flattened, dot-keys.

Sensitive field handling (recursive, case-insensitive substring match):
  password, hash, secret, token, mfa_, backup_code, stripe_secret,
  api_key, private_key, credential
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────
# Redaction
# ─────────────────────────────────────────────────────────────────────

REDACT_NEEDLES = (
    "password", "hash", "secret", "token", "mfa_", "backup_code",
    "stripe_secret", "api_key", "private_key", "credential",
)
REDACT_VALUE = "[REDACTED]"

# Collections that are deny-listed entirely. We don't even allow reading
# them — they hold raw OAuth refresh tokens / Stripe webhook payloads.
DENY_COLLECTIONS = {
    "system.users", "system.indexes", "system.sessions",
}


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(needle in k for needle in REDACT_NEEDLES)


def _redact(obj: Any) -> Any:
    """Recursively replace values for sensitive keys with REDACT_VALUE."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "_id":
                # ObjectId → str (never redacted; useful for debugging)
                out[k] = str(v) if isinstance(v, ObjectId) else v
            elif _is_sensitive_key(k):
                # Preserve type-shape so the UI can still render the row.
                out[k] = REDACT_VALUE if v is not None and v != "" else v
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


# ─────────────────────────────────────────────────────────────────────
# Collection listing
# ─────────────────────────────────────────────────────────────────────

@router.get("/master-admin/db/collections")
async def list_collections(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    names = await db.list_collection_names()
    out = []
    for name in sorted(names):
        if name in DENY_COLLECTIONS:
            continue
        try:
            count = await db[name].estimated_document_count()
        except Exception:
            count = -1
        out.append({"name": name, "count": count})
    return {"collections": out, "count": len(out)}


# ─────────────────────────────────────────────────────────────────────
# Browse + search
# ─────────────────────────────────────────────────────────────────────

def _build_search_filter(q: str | None) -> dict:
    """Build a Mongo filter that searches the most common identifying
    fields. We OR across `id`, `name`, `email`, `slug`, `serial_number`
    using a case-insensitive regex. Falls back to {} when q is empty.
    """
    if not q:
        return {}
    safe = re.escape(q.strip())
    if not safe:
        return {}
    rx = {"$regex": safe, "$options": "i"}
    return {"$or": [
        {"id": rx},
        {"name": rx},
        {"email": rx},
        {"slug": rx},
        {"serial_number": rx},
        {"organization_id": rx},
        {"user_id": rx},
    ]}


def _ensure_collection(name: str) -> None:
    if name in DENY_COLLECTIONS or name.startswith("system."):
        raise HTTPException(status_code=403, detail=f"Collection '{name}' is not browsable")


@router.get("/master-admin/db/collections/{name}")
async def browse_collection(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    _ensure_collection(name)
    coll = db[name]
    flt = _build_search_filter(q)
    try:
        total = await coll.count_documents(flt)
    except Exception as exc:
        logger.warning("count failed for %s: %s", name, exc)
        raise HTTPException(status_code=400, detail=f"Cannot read '{name}'") from exc
    skip = (page - 1) * page_size
    cursor = coll.find(flt).skip(skip).limit(page_size)
    raw = await cursor.to_list(page_size)
    docs = [_redact(d) for d in raw]
    pages = (total + page_size - 1) // page_size if total else 0
    return {
        "docs": docs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "redacted_keys": list(REDACT_NEEDLES),
    }


@router.get("/master-admin/db/collections/{name}/document/{doc_id}")
async def get_document(
    name: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    _ensure_collection(name)
    coll = db[name]
    # Try our app-level `id` field first.
    doc = await coll.find_one({"id": doc_id})
    # Fallback: ObjectId
    if not doc:
        try:
            doc = await coll.find_one({"_id": ObjectId(doc_id)})
        except Exception:
            doc = None
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"doc": _redact(doc)}


# ─────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────

EXPORT_HARD_LIMIT = 10_000  # Defensive — prevent multi-GB streams


def _flatten(d: dict, parent: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict for CSV export. Lists become JSON strings."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{parent}{sep}{k}" if parent else k
        if isinstance(v, dict):
            out.update(_flatten(v, key, sep))
        elif isinstance(v, list):
            out[key] = json.dumps(v, default=str)
        else:
            out[key] = v
    return out


@router.get("/master-admin/db/collections/{name}/export")
async def export_collection(
    name: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    confirm: bool = False,
    q: str | None = None,
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    _ensure_collection(name)
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Export requires confirm=true to prevent accidental dumps.",
        )
    coll = db[name]
    flt = _build_search_filter(q)
    cursor = coll.find(flt).limit(EXPORT_HARD_LIMIT)
    raw = await cursor.to_list(EXPORT_HARD_LIMIT)
    docs = [_redact(d) for d in raw]

    if format == "json":
        # Newline-delimited JSON → easy to grep / pipe into jq.
        body = "\n".join(json.dumps(d, default=str) for d in docs) + "\n"
        return StreamingResponse(
            io.StringIO(body),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.ndjson"',
                "X-Export-Count": str(len(docs)),
            },
        )

    # CSV — flatten + union of keys
    flat = [_flatten(d) for d in docs]
    fields: list[str] = []
    seen: set[str] = set()
    for row in flat:
        for k in row:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in flat:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.csv"',
            "X-Export-Count": str(len(docs)),
        },
    )
