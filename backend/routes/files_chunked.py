"""Iter 220e9 — Chunked file uploads for engineer media.

Field engineers on flaky 4G connections were losing 4–25 MB
photo/video uploads partway through, with no way to resume. This
module adds a three-step chunked upload protocol so the existing
``/files/upload`` single-shot endpoint stays untouched for small
files while large evidence media uses bounded ~1 MB chunks with
retry-per-chunk.

Endpoints (all under ``/api``):

* ``POST   /files/upload/chunks/init``
  Body: ``{filename, size, content_type, category, total_chunks}``
  Returns ``{upload_id, chunk_size, max_chunk_bytes, expires_at}``.

* ``PUT    /files/upload/chunks/{upload_id}/{index}``
  Raw ``application/octet-stream`` body. Stores one chunk under
  ``(upload_id, index)``. Idempotent — uploading the same index
  twice overwrites (so a retry-on-timeout is safe).
  Returns ``{received_chunks, total_chunks}``.

* ``POST   /files/upload/chunks/{upload_id}/complete``
  Assembles chunks in order, runs the SAME validation/storage/
  file_doc creation as the legacy endpoint, then deletes the chunk
  rows. Returns the file_doc — interface-identical to
  ``POST /files/upload`` so the frontend treats the two paths
  uniformly.

* ``DELETE /files/upload/chunks/{upload_id}`` — abort and cleanup.

Storage:
    Chunks live in MongoDB collection ``file_upload_chunks`` and
    are capped at 4 MB each (well under the 16 MB BSON limit). A
    TTL index on ``expires_at`` ensures abandoned uploads are
    auto-purged after one hour.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import APP_NAME, db, put_object
from utils.file_validation import (
    MIME_ALL_ATTACHMENTS,
    MIME_IMAGES,
    MIME_VIDEOS,
    validate_upload,
)


logger = logging.getLogger(__name__)
router = APIRouter()


# Hard ceiling per chunk. The frontend defaults to 1 MB; the cap here
# is a defensive limit so a misbehaving client cannot eat 16 MB of BSON.
MAX_CHUNK_BYTES = 4 * 1024 * 1024
# Max file size we'll accept via chunks. Photos compress well below
# this; engineer videos are validated at 30 MB / 30 s upstream.
MAX_TOTAL_BYTES = 200 * 1024 * 1024
SESSION_TTL_MINUTES = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _allow_for_category(category: str) -> set[str]:
    if category in ("videos", "service-videos", "case-videos"):
        return MIME_VIDEOS
    if category in ("photos", "service-photos", "case-photos"):
        return MIME_IMAGES
    if category in ("service-media", "case-media", "engineer-media"):
        return MIME_IMAGES | MIME_VIDEOS
    return MIME_ALL_ATTACHMENTS


@router.post("/files/upload/chunks/init")
async def init_chunked_upload(data: dict, user: dict = Depends(get_current_user)):
    """Reserve an upload_id and persist the session metadata."""
    filename = (data.get("filename") or "").strip()
    size = int(data.get("size") or 0)
    total_chunks = int(data.get("total_chunks") or 0)
    content_type = (data.get("content_type") or "application/octet-stream").strip()
    category = (data.get("category") or "general").strip()

    if not filename:
        raise HTTPException(400, "filename is required")
    if size <= 0:
        raise HTTPException(400, "size must be > 0")
    if size > MAX_TOTAL_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_TOTAL_BYTES} bytes)")
    if total_chunks <= 0 or total_chunks > 4096:
        raise HTTPException(400, "total_chunks must be between 1 and 4096")

    upload_id = str(uuid.uuid4())
    session = {
        "id": upload_id,
        "user_id": user["id"],
        "organization_id": user.get("organization_id"),
        "filename": filename,
        "size": size,
        "content_type": content_type,
        "category": category,
        "total_chunks": total_chunks,
        "status": "in_progress",
        "created_at": _now().isoformat(),
        "expires_at": _now() + timedelta(minutes=SESSION_TTL_MINUTES),
    }
    await db.file_upload_sessions.insert_one(session)
    return {
        "upload_id": upload_id,
        "max_chunk_bytes": MAX_CHUNK_BYTES,
        "expires_at": session["expires_at"].isoformat(),
    }


async def _load_session(upload_id: str, user: dict) -> dict:
    sess = await db.file_upload_sessions.find_one(
        {"id": upload_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not sess:
        raise HTTPException(404, "Upload session not found")
    if sess.get("status") not in ("in_progress",):
        raise HTTPException(409, f"Upload session is {sess.get('status')}")
    return sess


@router.put("/files/upload/chunks/{upload_id}/{index}")
async def put_chunk(upload_id: str, index: int, request: Request,
                    user: dict = Depends(get_current_user)):
    """Store one chunk. Idempotent on (upload_id, index)."""
    sess = await _load_session(upload_id, user)
    if index < 0 or index >= sess["total_chunks"]:
        raise HTTPException(400, "index out of range")
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty chunk body")
    if len(body) > MAX_CHUNK_BYTES:
        raise HTTPException(413, f"Chunk too large (max {MAX_CHUNK_BYTES} bytes)")
    await db.file_upload_chunks.update_one(
        {"upload_id": upload_id, "index": index},
        {"$set": {
            "upload_id": upload_id, "index": index,
            "bytes": body, "size": len(body),
            "updated_at": _now().isoformat(),
        }},
        upsert=True,
    )
    received = await db.file_upload_chunks.count_documents({"upload_id": upload_id})
    return {"received_chunks": received, "total_chunks": sess["total_chunks"]}


@router.post("/files/upload/chunks/{upload_id}/complete")
async def complete_chunked_upload(upload_id: str, user: dict = Depends(get_current_user)):
    """Assemble chunks, validate, store, return the file_doc."""
    sess = await _load_session(upload_id, user)
    received = await db.file_upload_chunks.count_documents({"upload_id": upload_id})
    if received != sess["total_chunks"]:
        raise HTTPException(400, f"Missing chunks: have {received}/{sess['total_chunks']}")

    cursor = db.file_upload_chunks.find(
        {"upload_id": upload_id}, {"_id": 0, "index": 1, "bytes": 1},
    ).sort("index", 1)
    parts = await cursor.to_list(sess["total_chunks"])
    data = b"".join(p["bytes"] for p in parts)
    if len(data) != sess["size"]:
        raise HTTPException(
            400,
            f"Assembled size mismatch: expected {sess['size']}, got {len(data)}",
        )

    # Mirror the validation / category logic of /files/upload. Sniffing
    # the assembled bytes catches polyglots that slipped past the
    # per-chunk content_type header.
    category = sess["category"]
    filename = sess["filename"]
    content_type = validate_upload(
        file_bytes=data,
        filename=filename,
        allowed=_allow_for_category(category),
    )

    ext = filename.split(".")[-1] if "." in filename else "bin"
    path = (
        f"{APP_NAME}/{category}/"
        f"{user.get('organization_id', user['id'])}/{uuid.uuid4()}.{ext}"
    )
    result = put_object(path, data, content_type)

    file_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "organization_id": user.get("organization_id"),
        "category": category,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "original_filename": filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "original_size": sess["size"],
        "compression_ratio": 0,
        "content_hash": hashlib.sha256(data).hexdigest(),
        "created_at": _now().isoformat(),
        "upload_method": "chunked",
    }
    await db.files.insert_one(file_doc)
    file_doc.pop("_id", None)

    # Cleanup chunks + mark session done.
    await db.file_upload_chunks.delete_many({"upload_id": upload_id})
    await db.file_upload_sessions.update_one(
        {"id": upload_id},
        {"$set": {"status": "complete", "completed_at": _now().isoformat(),
                  "file_id": file_doc["id"]}},
    )
    return file_doc


@router.delete("/files/upload/chunks/{upload_id}")
async def abort_chunked_upload(upload_id: str, user: dict = Depends(get_current_user)):
    """Cancel an in-progress upload and free its chunks."""
    sess = await db.file_upload_sessions.find_one(
        {"id": upload_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not sess:
        raise HTTPException(404, "Upload session not found")
    await db.file_upload_chunks.delete_many({"upload_id": upload_id})
    await db.file_upload_sessions.update_one(
        {"id": upload_id},
        {"$set": {"status": "aborted", "aborted_at": _now().isoformat()}},
    )
    return {"upload_id": upload_id, "status": "aborted"}


@router.get("/files/upload/chunks/{upload_id}/status")
async def chunk_session_status(upload_id: str, user: dict = Depends(get_current_user)):
    """Inspect progress + which chunks are missing — used by resume-on-reopen."""
    sess = await db.file_upload_sessions.find_one(
        {"id": upload_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not sess:
        raise HTTPException(404, "Upload session not found")
    received_idx = await db.file_upload_chunks.find(
        {"upload_id": upload_id}, {"_id": 0, "index": 1},
    ).to_list(sess["total_chunks"])
    have = sorted(c["index"] for c in received_idx)
    missing = [i for i in range(sess["total_chunks"]) if i not in set(have)]
    return {
        "upload_id": upload_id,
        "status": sess["status"],
        "total_chunks": sess["total_chunks"],
        "received_chunks": len(have),
        "missing": missing,
    }
