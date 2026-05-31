"""Iter 220e9 — Chunked upload protocol for engineer media.

Asserts the init → put-chunk → complete happy path, idempotent
retries, size/range/category guards, resume-status, and abort
cleanup.
"""
from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


USER = {"id": "u-eng", "organization_id": "org-1", "full_name": "Eng"}


def _request_with_body(body: bytes):
    """Build a minimal `fastapi.Request`-shaped object that returns the
    provided bytes when ``await request.body()`` is invoked."""
    req = MagicMock()
    req.body = AsyncMock(return_value=body)
    return req


# ── Shared DB fixture ──────────────────────────────────────────


def _chunk_db():
    """In-memory mock that satisfies every chunked-upload call."""
    state = {
        "sessions": {},  # upload_id -> dict
        "chunks": [],    # list of {upload_id, index, bytes, size}
        "files": [],
    }
    fdb = MagicMock()

    async def _ins_session(d):
        state["sessions"][d["id"]] = d
    fdb.file_upload_sessions.insert_one = AsyncMock(side_effect=_ins_session)

    async def _find_session(q, p=None):
        s = state["sessions"].get(q.get("id"))
        if s and all(s.get(k) == v for k, v in q.items()):
            return {k: v for k, v in s.items() if k != "_id"}
        return None
    fdb.file_upload_sessions.find_one = AsyncMock(side_effect=_find_session)

    async def _upd_session(q, upd):
        s = state["sessions"].get(q.get("id"))
        if s:
            s.update(upd.get("$set", {}))
        return MagicMock(modified_count=1)
    fdb.file_upload_sessions.update_one = AsyncMock(side_effect=_upd_session)

    async def _upd_chunk(q, upd, upsert=False):
        existing = next(
            (c for c in state["chunks"]
             if c["upload_id"] == q["upload_id"] and c["index"] == q["index"]),
            None,
        )
        sets = upd.get("$set", {})
        if existing:
            existing.update(sets)
        elif upsert:
            state["chunks"].append({**q, **sets})
        return MagicMock(matched_count=1 if existing else 0)
    fdb.file_upload_chunks.update_one = AsyncMock(side_effect=_upd_chunk)

    async def _count(q):
        return len([c for c in state["chunks"] if c["upload_id"] == q["upload_id"]])
    fdb.file_upload_chunks.count_documents = AsyncMock(side_effect=_count)

    def _find_chunks(q, p=None):
        rows = [c for c in state["chunks"] if c["upload_id"] == q["upload_id"]]
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=rows)
        return cur
    fdb.file_upload_chunks.find = MagicMock(side_effect=_find_chunks)

    async def _del_chunks(q):
        before = len(state["chunks"])
        state["chunks"][:] = [c for c in state["chunks"] if c["upload_id"] != q["upload_id"]]
        return MagicMock(deleted_count=before - len(state["chunks"]))
    fdb.file_upload_chunks.delete_many = AsyncMock(side_effect=_del_chunks)

    async def _ins_file(d):
        state["files"].append(d)
    fdb.files.insert_one = AsyncMock(side_effect=_ins_file)

    return fdb, state


# ── 1 · init ───────────────────────────────────────────────────


def test_init_creates_session_and_returns_upload_id():
    from routes.files_chunked import init_chunked_upload
    fdb, state = _chunk_db()
    with patch("routes.files_chunked.db", fdb):
        out = _run(init_chunked_upload({
            "filename": "treadmill.mp4", "size": 8 * 1024 * 1024,
            "content_type": "video/mp4", "category": "service-media",
            "total_chunks": 8,
        }, user=USER))
    assert out["upload_id"]
    assert out["max_chunk_bytes"] == 4 * 1024 * 1024
    sess = state["sessions"][out["upload_id"]]
    assert sess["status"] == "in_progress"
    assert sess["total_chunks"] == 8
    assert sess["organization_id"] == "org-1"


@pytest.mark.parametrize("payload, code", [
    ({"filename": "", "size": 100, "total_chunks": 1}, 400),
    ({"filename": "x.bin", "size": 0, "total_chunks": 1}, 400),
    ({"filename": "x.bin", "size": 300 * 1024 * 1024, "total_chunks": 1}, 413),
    ({"filename": "x.bin", "size": 100, "total_chunks": 0}, 400),
    ({"filename": "x.bin", "size": 100, "total_chunks": 5000}, 400),
])
def test_init_validates_payload(payload, code):
    from routes.files_chunked import init_chunked_upload
    fdb, _ = _chunk_db()
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(init_chunked_upload(payload, user=USER))
    assert exc.value.status_code == code


# ── 2 · put chunk ──────────────────────────────────────────────


def _seed_session(state, *, total_chunks=2, size=2048, category="service-media",
                   filename="img.jpg", content_type="image/jpeg",
                   user_id="u-eng"):
    sid = "sess-1"
    state["sessions"][sid] = {
        "id": sid, "user_id": user_id, "organization_id": "org-1",
        "filename": filename, "size": size, "content_type": content_type,
        "category": category, "total_chunks": total_chunks,
        "status": "in_progress", "created_at": "2026-02-14",
    }
    return sid


def test_put_chunk_stores_and_returns_progress():
    from routes.files_chunked import put_chunk
    fdb, state = _chunk_db()
    sid = _seed_session(state)
    with patch("routes.files_chunked.db", fdb):
        out = _run(put_chunk(sid, 0, _request_with_body(b"x" * 1024), user=USER))
    assert out["received_chunks"] == 1
    assert out["total_chunks"] == 2
    assert state["chunks"][0]["index"] == 0
    assert state["chunks"][0]["size"] == 1024


def test_put_chunk_is_idempotent_overwrite_on_retry():
    from routes.files_chunked import put_chunk
    fdb, state = _chunk_db()
    sid = _seed_session(state)
    with patch("routes.files_chunked.db", fdb):
        _run(put_chunk(sid, 0, _request_with_body(b"first"), user=USER))
        out = _run(put_chunk(sid, 0, _request_with_body(b"retry-payload"), user=USER))
    assert out["received_chunks"] == 1  # still just one chunk row.
    assert state["chunks"][0]["bytes"] == b"retry-payload"


def test_put_chunk_rejects_out_of_range_index():
    from routes.files_chunked import put_chunk
    fdb, state = _chunk_db()
    sid = _seed_session(state, total_chunks=2)
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(put_chunk(sid, 9, _request_with_body(b"x"), user=USER))
    assert exc.value.status_code == 400


def test_put_chunk_rejects_oversized_payload():
    from routes.files_chunked import put_chunk, MAX_CHUNK_BYTES
    fdb, state = _chunk_db()
    sid = _seed_session(state)
    big = b"\x00" * (MAX_CHUNK_BYTES + 1)
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(put_chunk(sid, 0, _request_with_body(big), user=USER))
    assert exc.value.status_code == 413


def test_put_chunk_rejects_empty_body():
    from routes.files_chunked import put_chunk
    fdb, state = _chunk_db()
    sid = _seed_session(state)
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(put_chunk(sid, 0, _request_with_body(b""), user=USER))
    assert exc.value.status_code == 400


def test_put_chunk_404s_for_unknown_session():
    from routes.files_chunked import put_chunk
    fdb, _ = _chunk_db()
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(put_chunk("ghost", 0, _request_with_body(b"x"), user=USER))
    assert exc.value.status_code == 404


def test_put_chunk_is_user_scoped():
    """Another user with the same upload_id must NOT be able to write."""
    from routes.files_chunked import put_chunk
    fdb, state = _chunk_db()
    sid = _seed_session(state, user_id="u-eng")
    intruder = {"id": "u-evil", "organization_id": "org-1", "full_name": "Evil"}
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(put_chunk(sid, 0, _request_with_body(b"x"), user=intruder))
    assert exc.value.status_code == 404


# ── 3 · complete ───────────────────────────────────────────────


# 1×1 transparent PNG — survives the MIME sniff for image categories.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01_\xc7\xb0"
    b"\x83\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _stub_put_object(*_a, **_kw):
    return {"path": "obj/path.png", "url": "https://cdn/obj.png", "size": len(_PNG_BYTES)}


def test_complete_assembles_chunks_into_file_doc():
    from routes.files_chunked import complete_chunked_upload
    fdb, state = _chunk_db()
    sid = _seed_session(
        state, total_chunks=2, size=len(_PNG_BYTES),
        category="service-media", filename="evidence.png",
        content_type="image/png",
    )
    midpoint = len(_PNG_BYTES) // 2
    state["chunks"].append({"upload_id": sid, "index": 0,
                            "bytes": _PNG_BYTES[:midpoint], "size": midpoint})
    state["chunks"].append({"upload_id": sid, "index": 1,
                            "bytes": _PNG_BYTES[midpoint:],
                            "size": len(_PNG_BYTES) - midpoint})

    with patch("routes.files_chunked.db", fdb), \
         patch("routes.files_chunked.put_object", side_effect=_stub_put_object):
        out = _run(complete_chunked_upload(sid, user=USER))

    assert out["upload_method"] == "chunked"
    assert out["original_filename"] == "evidence.png"
    assert out["category"] == "service-media"
    # Chunks were cleaned up + session marked complete.
    assert state["chunks"] == []
    assert state["sessions"][sid]["status"] == "complete"
    assert state["sessions"][sid]["file_id"] == out["id"]
    # File doc landed in the files collection.
    assert state["files"][0]["id"] == out["id"]


def test_complete_rejects_missing_chunks():
    from routes.files_chunked import complete_chunked_upload
    fdb, state = _chunk_db()
    sid = _seed_session(state, total_chunks=3, size=300)
    state["chunks"].append({"upload_id": sid, "index": 0, "bytes": b"a" * 100, "size": 100})
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(complete_chunked_upload(sid, user=USER))
    assert exc.value.status_code == 400
    assert "Missing chunks" in exc.value.detail


def test_complete_rejects_size_mismatch():
    from routes.files_chunked import complete_chunked_upload
    fdb, state = _chunk_db()
    # Declared size 999 but only 4 bytes received.
    sid = _seed_session(state, total_chunks=1, size=999)
    state["chunks"].append({"upload_id": sid, "index": 0, "bytes": b"abcd", "size": 4})
    with patch("routes.files_chunked.db", fdb), pytest.raises(HTTPException) as exc:
        _run(complete_chunked_upload(sid, user=USER))
    assert exc.value.status_code == 400
    assert "size mismatch" in exc.value.detail


def test_complete_rejects_disallowed_mime_for_category():
    """A PDF disguised in a `case-photos` category must be rejected by
    the byte sniff even after assembly succeeds."""
    from routes.files_chunked import complete_chunked_upload
    fdb, state = _chunk_db()
    # PDF magic but category restricts to images.
    pdf = b"%PDF-1.4\n%fake content\n" + b"\x00" * 100
    sid = _seed_session(state, total_chunks=1, size=len(pdf),
                        category="case-photos", filename="fake.png")
    state["chunks"].append({"upload_id": sid, "index": 0, "bytes": pdf, "size": len(pdf)})
    with patch("routes.files_chunked.db", fdb), \
         patch("routes.files_chunked.put_object", side_effect=_stub_put_object), \
         pytest.raises(HTTPException) as exc:
        _run(complete_chunked_upload(sid, user=USER))
    # validate_upload raises 415 on disallowed mime.
    assert exc.value.status_code == 415


# ── 4 · abort + status ─────────────────────────────────────────


def test_abort_clears_chunks_and_marks_session():
    from routes.files_chunked import abort_chunked_upload
    fdb, state = _chunk_db()
    sid = _seed_session(state)
    state["chunks"].append({"upload_id": sid, "index": 0, "bytes": b"x", "size": 1})
    with patch("routes.files_chunked.db", fdb):
        out = _run(abort_chunked_upload(sid, user=USER))
    assert out["status"] == "aborted"
    assert state["chunks"] == []
    assert state["sessions"][sid]["status"] == "aborted"


def test_status_reports_received_and_missing_chunks():
    from routes.files_chunked import chunk_session_status
    fdb, state = _chunk_db()
    sid = _seed_session(state, total_chunks=4)
    for idx in (0, 2):
        state["chunks"].append({"upload_id": sid, "index": idx, "bytes": b"x", "size": 1})
    with patch("routes.files_chunked.db", fdb):
        out = _run(chunk_session_status(sid, user=USER))
    assert out["received_chunks"] == 2
    assert sorted(out["missing"]) == [1, 3]


# ── 5 · Smoke: router registered in core registry ──────────────


def test_chunked_router_registered_in_core():
    from route_registry.core import register_core
    from fastapi import APIRouter
    api = APIRouter()
    register_core(api)
    paths = {r.path for r in api.routes}
    assert any("/files/upload/chunks/init" in p for p in paths)
    assert any("/files/upload/chunks/{upload_id}/complete" in p for p in paths)


# Force `io` import to remain (used previously during dev, kept for
# potential local debugging via BytesIO without re-importing).
_ = io.BytesIO
