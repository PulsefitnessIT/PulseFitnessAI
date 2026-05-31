"""Iter 220ea·4 — Engineer resume-failed-upload UX.

Source-level guards that hold the three moving pieces together:

* `chunkedUpload` accepts a `resumeUploadId` + an `onSession`
  hook, doesn't auto-abort on resumable failures, and stamps the
  thrown error with the upload_id so the caller can keep the
  stash row aligned.
* `engineerUploadStash` exposes a stable IndexedDB CRUD surface
  scoped to the current engineer's token.
* `PausedUploadsPill` renders inside `EngineerHomeV2`, lists the
  paused rows, and exposes Resume + Discard CTAs with the right
  data-testids.

Behavioural tests for the resume path itself live in the
chunked-upload backend suite (status / put / complete are already
covered there). What we are guarding here is the WIRING — the
seams that would otherwise drift silently.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")
CHUNKED  = FRONTEND / "utils/chunkedUpload.js"
STASH    = FRONTEND / "utils/engineerUploadStash.js"
PILL     = FRONTEND / "pages/ServiceOps/Engineer/PausedUploadsPill.js"
HOME_V2  = FRONTEND / "pages/ServiceOps/Engineer/EngineerHomeV2.js"
WV_CARD  = FRONTEND / "pages/ServiceOps/Engineer/WorkVisitMachinesCard.js"


# ── 1 · chunkedUpload helper ─────────────────────────────────────


def test_chunked_upload_accepts_resume_id_and_session_hook():
    src = CHUNKED.read_text()
    assert "onSession" in src
    assert "resumeUploadId" in src
    # The status pre-fetch + missing-chunks skip path is what makes
    # resume actually resume.
    assert "/files/upload/chunks/" in src
    assert "/status" in src
    assert "missing" in src
    # And the session-expired UX channel.
    assert "session_expired" in src


def test_chunked_upload_does_not_auto_abort_on_resumable_failure():
    """A resume path must NOT call DELETE on failure — the session
    is still live for the next attempt."""
    src = CHUNKED.read_text()
    # The DELETE call is gated on `!resumeUploadId`.
    assert "if (!resumeUploadId)" in src
    # And the thrown error carries the upload_id so the caller can
    # keep the stash row pointed at the right server session.
    assert "err.uploadId = uploadId" in src


def test_chunked_upload_session_hook_fires_before_first_chunk():
    """`onSession` must be invoked after init returns but BEFORE the
    worker pool starts pushing chunks, so a tab-close between the
    very first PUT and the next page-load can still be resumed."""
    src = CHUNKED.read_text()
    init_idx     = src.index("/files/upload/chunks/init")
    onSession_idx = src.index("onSession === 'function'")
    worker_idx   = src.index("async function worker()")
    assert init_idx < onSession_idx < worker_idx


# ── 2 · IndexedDB stash ───────────────────────────────────────────


def test_stash_module_exposes_full_crud_surface():
    src = STASH.read_text()
    for fn in (
        "stashPausedUpload",
        "dropPausedUpload",
        "listPausedUploads",
        "getPausedUpload",
        "countPausedUploads",
        "subscribePausedUploads",
    ):
        assert f"export async function {fn}" in src or f"export function {fn}" in src, (
            f"stash module missing public helper: {fn}"
        )


def test_stash_scopes_rows_to_current_engineer():
    """Two engineers sharing a tablet must NOT see each other's
    paused uploads — the owner-namespacing must stay in place."""
    src = STASH.read_text()
    assert "currentOwner" in src
    assert "token.slice(0, 12)" in src
    # And the list query must filter by owner.
    assert "r.owner === owner" in src


def test_stash_persists_blob_so_resume_works_after_tab_close():
    """We deliberately persist the actual file bytes (Blob) — without
    that, resume would require the engineer to re-select the file,
    which defeats the purpose."""
    src = STASH.read_text()
    assert "blob" in src.lower()
    # IDB schema version + store name (open-DB pattern).
    assert "DB_NAME" in src
    assert "DB_VER" in src
    assert "indexedDB.open" in src


# ── 3 · PausedUploadsPill component ──────────────────────────────


def test_paused_uploads_pill_renders_pill_only_when_rows_exist():
    src = PILL.read_text()
    # Conditional render — no rows → no pill (header doesn't get a
    # phantom "0 uploads paused" chip).
    assert "if (rows.length === 0) return null" in src
    # The pill has its test-id and a clear resume / discard surface.
    assert 'data-testid="paused-uploads-pill"' in src
    assert 'data-testid="paused-uploads-sheet"' in src
    assert "paused-upload-resume-${" in src
    assert "paused-upload-discard-${" in src


def test_paused_uploads_pill_uses_chunked_upload_resume_path():
    src = PILL.read_text()
    assert "resumeUploadId: row.upload_id" in src
    # After a successful resume the stash row is dropped — otherwise
    # the pill would keep showing the same upload as paused forever.
    assert "dropPausedUpload(row.upload_id)" in src
    # Session-expired path must drop the row + warn the engineer.
    assert "session_expired" in src


def test_paused_uploads_pill_handles_finalisation():
    """Post-assembly the pill must POST to /svc/engineer/photos so
    the resumed file actually appears against the case — otherwise
    the bytes land on disk but never show in the engineer UI."""
    src = PILL.read_text()
    assert "/svc/engineer/photos" in src
    assert "case_id: row.case_id" in src
    assert "caption: row.caption" in src


def test_paused_uploads_pill_polls_on_focus_and_interval():
    """A 30 s interval + window.focus listener means a paused upload
    that happened in another tab still surfaces on the home screen
    when the engineer returns."""
    src = PILL.read_text()
    assert "addEventListener('focus'" in src
    assert "setInterval(refresh, 30_000)" in src or "setInterval(refresh, 30000)" in src


# ── 4 · Engineer home mount + Work-visit wiring ──────────────────


def test_pill_is_mounted_in_engineer_home_v2():
    src = HOME_V2.read_text()
    assert "import PausedUploadsPill" in src
    assert "<PausedUploadsPill />" in src
    # Lives next to the offline outbox pill so the engineer sees the
    # two transport states side-by-side.
    outbox_idx = src.index("<OutboxStatusPill />")
    pill_idx   = src.index("<PausedUploadsPill />")
    assert 0 < outbox_idx < pill_idx, (
        "PausedUploadsPill should mount right after OutboxStatusPill"
    )


def test_work_visit_attach_photo_uses_chunked_upload_and_stash():
    """The REAL field-engineer media flow lives in
    WorkVisitMachinesCard.attachPhoto. Iter 220e9 wired chunkedUpload
    only into a dead `PhotosTab`; iter 220ea·4 promotes it into the
    flow that actually runs, AND stashes the session blob so resume
    is possible."""
    src = WV_CARD.read_text()
    assert "import { chunkedUpload }" in src
    assert "import { stashPausedUpload }" in src
    block_start = src.index("const attachPhoto = async")
    block_end = src.index("const removePhoto", block_start)
    block = src[block_start:block_end]
    assert "chunkedUpload({" in block, (
        "attachPhoto must route through chunkedUpload"
    )
    assert "onSession" in block, (
        "attachPhoto must stash the session before any chunk PUTs"
    )
    assert "blob: file" in block, (
        "stash must carry the actual Blob so resume can read the bytes"
    )
    # And the dead single-shot path is gone.
    assert "FormData" not in block, (
        "attachPhoto must not fall back to FormData / single-shot"
    )


def test_work_visit_clears_stash_on_successful_upload():
    """After a successful chunkedUpload the row in the stash must be
    dropped — otherwise the pill keeps showing the completed upload
    as 'paused'."""
    src = WV_CARD.read_text()
    # Best-effort cleanup walks the stash for any row matching this
    # case/filename/size and drops it. (We can't capture the
    # uploadId in the outer scope because chunkedUpload owns it.)
    assert "listPausedUploads" in src
    assert "dropPausedUpload: drop" in src
    assert "row.size === file.size" in src
