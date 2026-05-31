"""Iter 220db — Engineer photo upload: client-side image compression
+ visible upload progress.

Pure-frontend feature (no backend changes — the existing
``POST /files/upload`` endpoint is unchanged). This test file is a
static-source-level guard that:

  * The compression helper exists with the expected defaults
    (max-width 2048, JPEG q=0.8, skip-tiny threshold).
  * ``PhotosTab.uploadFile`` calls ``compressImage`` before posting.
  * Axios is wired with ``onUploadProgress``.
  * The progress bar UI renders with the expected ``data-testid``s.
"""
from __future__ import annotations

from pathlib import Path


JOB_DETAIL = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
COMPRESS_UTIL = Path("/app/frontend/src/utils/compressImage.js")


def test_compress_image_helper_exports_canonical_defaults():
    src = COMPRESS_UTIL.read_text()
    assert "export async function compressImage" in src
    assert "maxWidth: 2048" in src
    assert "quality: 0.8" in src
    assert "minBytes" in src
    # GIF / SVG are passed through (animation / vector preservation).
    assert "image/gif" in src
    assert "image/svg+xml" in src


def test_photos_tab_compresses_before_upload():
    src = JOB_DETAIL.read_text()
    assert "import { compressImage }" in src
    # The wired call inside uploadFile.
    assert "await compressImage(file)" in src


def test_photos_tab_tracks_upload_progress():
    src = JOB_DETAIL.read_text()
    # Iter 220e9 — progress is now driven by chunkedUpload's
    # `onProgress` callback (which in turn uses axios
    # `onUploadProgress` under the hood for small files and
    # per-chunk completion ratio for large ones).
    assert "onProgress:" in src
    assert "setUploadPct" in src
    # Progress UI test IDs.
    for tid in (
        "photo-upload-progress", "photo-upload-pct", "photo-upload-bar",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Underlying axios progress hook still wired inside the helper.
    chunked = Path("/app/frontend/src/utils/chunkedUpload.js").read_text()
    assert "onUploadProgress" in chunked


def test_video_path_skips_compression():
    """Compression must NOT run on videos (already validated, would
    waste CPU)."""
    src = JOB_DETAIL.read_text()
    # The ternary in uploadFile picks compressImage for photo only.
    assert "kind === 'video' ? file : await compressImage(file)" in src
