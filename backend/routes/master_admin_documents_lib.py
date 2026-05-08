"""Master Admin — platform & per-org Documents library.

A unified store for:

  • **Auto-captured documents** — invoice PDFs, security audit exports,
    onboarding packets and similar generated files. The endpoints that
    create them call ``record_generated_document(...)`` so the file
    appears in the library automatically.
  • **Manually-uploaded documents** — DPAs, signed contracts, NDAs,
    supplier certs, ad-hoc files. Master admin uploads through the UI.

Both kinds live in the same ``documents`` collection and share the
same access surface so the master admin has *one* place to find a doc.

Schema (`documents`)
====================
::

    {
        "id":              uuid,
        "scope":           "platform" | "org",
        "organization_id": str | null,    # null when scope == "platform"
        "title":           str,
        "category":        "invoice" | "contract" | "dpa" | "audit" |
                           "onboarding" | "compliance" | "other",
        "tags":            [str, …],
        "source":          "auto" | "upload",
        "filename":        str,
        "content_type":    str,
        "size_bytes":      int,
        "storage": {
            "kind": "inline-base64" | "ref",
            "data": str | None,           # base64 for tiny files
            "ref":  str | None,           # path or external URL
        },
        "linked_to": {                    # backref to the source object
            "type": "invoice" | "audit_log" | …,
            "id":   str
        } | None,
        "uploaded_by":     user_id,
        "uploaded_at":     iso,
        "version":         int            # bumps on replace
    }

The doc body is stored inline as base64 because every artefact we
generate today is < 200 KB (invoice PDF ≈ 2.5 KB, audit ≈ 50 KB).
For larger files the ``storage.kind == "ref"`` slot holds a URL/path
to be plugged in later.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)

CATEGORIES = ("invoice", "contract", "dpa", "audit", "onboarding", "compliance", "other")
MAX_INLINE_BYTES = 5 * 1024 * 1024   # 5 MB — anything larger needs the ref-storage backend


# ── Helpers ─────────────────────────────────────────────────────────


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_storage(doc: dict) -> dict:
    """List endpoints don't need the base64 blob — strip to keep the
    response small."""
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "storage"}
    out["has_body"] = bool(doc.get("storage", {}).get("data") or doc.get("storage", {}).get("ref"))
    return out


# ── Internal helper for in-process callers ──────────────────────────


async def record_generated_document(
    *,
    title: str,
    category: str,
    body: bytes,
    content_type: str,
    filename: str,
    organization_id: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    tags: list[str] | None = None,
    actor_id: str | None = None,
) -> str:
    """Auto-capture a generated PDF/file into the documents library.

    Returns the new document's id. Best-effort — never raises so the
    primary workflow (e.g. invoice generation) is never blocked.
    """
    if category not in CATEGORIES:
        category = "other"
    if len(body) > MAX_INLINE_BYTES:
        # Skip auto-capture for oversized blobs — we'd need real object
        # storage. The caller still returns the file to the user.
        logger.warning("auto-capture skipped: %s exceeded MAX_INLINE_BYTES", title)
        return ""
    try:
        doc_id = str(uuid.uuid4())
        await db.documents.insert_one({
            "id": doc_id,
            "scope": "org" if organization_id else "platform",
            "organization_id": organization_id,
            "title": title[:200],
            "category": category,
            "tags": list(tags or []),
            "source": "auto",
            "filename": filename[:160],
            "content_type": content_type,
            "size_bytes": len(body),
            "storage": {"kind": "inline-base64", "data": base64.b64encode(body).decode(), "ref": None},
            "linked_to": ({"type": linked_type, "id": linked_id} if linked_type and linked_id else None),
            "uploaded_by": actor_id,
            "uploaded_at": _now(),
            "version": 1,
        })
        return doc_id
    except Exception:
        logger.exception("record_generated_document failed for %s", title)
        return ""


# ── Public endpoints ────────────────────────────────────────────────


@router.get("/master-admin/document-library")
async def list_documents(
    scope: str | None = None,
    organization_id: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
) -> dict:
    """Paginated list. Filter by scope / org / category / fuzzy title."""
    _require_master(user)
    query: dict[str, Any] = {}
    if scope in ("platform", "org"):
        query["scope"] = scope
    if organization_id:
        query["organization_id"] = organization_id
    if category and category in CATEGORIES:
        query["category"] = category
    if q:
        # Cheap case-insensitive contains. Index is on (scope, uploaded_at)
        # so this is fine for libraries up to a few thousand docs.
        query["title"] = {"$regex": q.strip(), "$options": "i"}
    cursor = db.documents.find(query, {"_id": 0}).sort("uploaded_at", -1).limit(min(int(limit or 100), 500))
    rows = await cursor.to_list(length=500)
    return {
        "documents": [_strip_storage(r) for r in rows],
        "categories": list(CATEGORIES),
        "as_of": _now(),
    }


@router.post("/master-admin/document-library")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("other"),
    scope: str = Form("platform"),
    organization_id: str = Form(""),
    tags: str = Form(""),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload a file from the Master Admin UI. ``tags`` is a comma-separated
    string for form-friendliness; we split + clean here.
    """
    _require_master(user)
    if scope not in ("platform", "org"):
        raise HTTPException(400, "scope must be platform|org")
    if scope == "org" and not organization_id:
        raise HTTPException(400, "organization_id required when scope=org")
    if category not in CATEGORIES:
        category = "other"

    body = await file.read()
    if not body:
        raise HTTPException(400, "Empty upload")
    if len(body) > MAX_INLINE_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_INLINE_BYTES // 1024 // 1024} MB inline limit")

    doc = {
        "id": str(uuid.uuid4()),
        "scope": scope,
        "organization_id": organization_id or None,
        "title": title[:200],
        "category": category,
        "tags": [t.strip()[:60] for t in (tags or "").split(",") if t.strip()][:20],
        "source": "upload",
        "filename": (file.filename or "file")[:160],
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(body),
        "storage": {"kind": "inline-base64", "data": base64.b64encode(body).decode(), "ref": None},
        "linked_to": None,
        "uploaded_by": user.get("id"),
        "uploaded_at": _now(),
        "version": 1,
    }
    await db.documents.insert_one(dict(doc))
    return {"document": _strip_storage(doc)}


@router.get("/master-admin/document-library/{doc_id}/download")
async def download_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
) -> Response:
    _require_master(user)
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    storage = doc.get("storage") or {}
    if storage.get("kind") != "inline-base64" or not storage.get("data"):
        raise HTTPException(404, "Document body unavailable")
    body = base64.b64decode(storage["data"])
    # Audit who downloaded what.
    try:
        await db.document_access_log.insert_one({
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "action": "download",
            "by": user.get("id"),
            "at": _now(),
        })
    except Exception:
        pass
    return Response(
        content=body,
        media_type=doc.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{doc.get("filename","file")}"'},
    )


@router.delete("/master-admin/document-library/{doc_id}")
async def delete_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master(user)
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    await db.documents.delete_one({"id": doc_id})
    try:
        await db.document_access_log.insert_one({
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "action": "delete",
            "by": user.get("id"),
            "at": _now(),
        })
    except Exception:
        pass
    return {"deleted": True}


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_documents_indexes() -> None:
    try:
        await db.documents.create_index([("scope", 1), ("uploaded_at", -1)])
        await db.documents.create_index([("organization_id", 1), ("uploaded_at", -1)])
        await db.documents.create_index([("category", 1)])
        await db.documents.create_index([("title", "text"), ("tags", "text")])
        await db.document_access_log.create_index([("document_id", 1), ("at", -1)])
    except Exception:
        logger.exception("ensure_documents_indexes failed (non-fatal)")
