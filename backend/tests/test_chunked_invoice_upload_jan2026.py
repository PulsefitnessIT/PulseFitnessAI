"""
Backend tests for chunked invoice upload + decoupled background extraction.
Covers:
 - Single-chunk happy path (chunk → finalize → status done)
 - Multi-chunk reassembly (>1.5MB PDF split into multiple chunks)
 - Error: finalize with unknown upload_id → 404
 - Error: corrupt/non-PDF surfaces as job-level error (NOT a 520/hang)
 - Verify chunk docs are deleted after finalize
"""

import io
import os
import time
import uuid
import pytest
import requests
import fitz  # PyMuPDF

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fallback: read from frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not configured"
    return url.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

CHUNK_SIZE = int(1.5 * 1024 * 1024)  # 1.5MB


@pytest.fixture(scope="session")
def auth_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"No token in login response: {r.json()}"
    return {"Authorization": f"Bearer {token}"}


# ── PDF generation helpers ─────────────────────────────────────────────────
def _build_small_invoice_pdf() -> bytes:
    """A 1-page invoice-like PDF (small) for the single-chunk happy path."""
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "INVOICE\n"
        "Supplier: Pulse Fitness Equipment Ltd\n"
        "Invoice #: TEST-INV-001\n"
        "Date: 2026-01-15\n"
        "\n"
        "Description                Serial      Qty    Unit Price\n"
        "Commercial Treadmill T1    TM-SN-1001  1      4500.00\n"
        "Exercise Bike EB-200       EB-SN-2002  1      1200.00\n"
        "\n"
        "Subtotal: 5700.00\n"
        "VAT (20%): 1140.00\n"
        "Total: 6840.00\n"
    )
    page.insert_text((50, 60), text, fontsize=11)
    return doc.tobytes()


def _build_large_invoice_pdf(target_bytes: int = 3 * 1024 * 1024) -> bytes:
    """Build a multi-page invoice PDF ≥ target_bytes by inserting a JPEG image
    on each page (text-only pages compress too well to reach 3MB)."""
    doc = fitz.open()

    # First page: real invoice text the LLM should extract from.
    p0 = doc.new_page()
    text = (
        "INVOICE\n"
        "Supplier: Pulse Fitness Equipment Ltd\n"
        "Invoice #: TEST-INV-MULTI-001\n"
        "Date: 2026-01-15\n"
        "\n"
        "Description                Serial         Qty    Unit Price\n"
        "Commercial Treadmill T1    TM-SN-LRG-01   1      4500.00\n"
        "Rowing Machine R-9         RW-SN-LRG-02   1      1800.00\n"
        "\n"
        "Total: 6300.00\n"
    )
    p0.insert_text((50, 60), text, fontsize=11)

    # Build a large incompressible JPEG (random-ish noise) once and re-insert.
    import struct, random
    random.seed(42)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1200, 1600), 0)
    samples = bytearray()
    for _ in range(1200 * 1600):
        samples += struct.pack("BBB", random.randrange(256), random.randrange(256), random.randrange(256))
    pix = fitz.Pixmap(fitz.csRGB, 1200, 1600, bytes(samples), 0)
    img_bytes = pix.tobytes("jpeg", jpg_quality=92)

    # Insert filler pages until we hit target_bytes.
    while True:
        page = doc.new_page()
        page.insert_image(page.rect, stream=img_bytes)
        out = doc.tobytes()
        if len(out) >= target_bytes:
            return out


# ── Tests ─────────────────────────────────────────────────────────────────
class TestChunkedInvoiceUpload:

    def _chunk_upload(self, headers, pdf_bytes: bytes, filename: str, upload_id: str = None):
        upload_id = upload_id or f"test-{uuid.uuid4().hex[:16]}"
        chunks = [pdf_bytes[i:i + CHUNK_SIZE] for i in range(0, len(pdf_bytes), CHUNK_SIZE)]
        total = len(chunks)
        for idx, part in enumerate(chunks):
            files = {"file": (f"{filename}.part{idx}", part, "application/octet-stream")}
            data = {"upload_id": upload_id, "chunk_index": str(idx), "total_chunks": str(total)}
            r = requests.post(
                f"{BASE_URL}/api/equipment-import/parse-invoice/chunk",
                headers=headers, data=data, files=files, timeout=60,
            )
            assert r.status_code == 200, f"chunk {idx}/{total} failed: {r.status_code} {r.text}"
            body = r.json()
            assert body["ok"] is True
            assert body["upload_id"] == upload_id
            assert body["received"] == idx + 1
        return upload_id, total

    def _finalize(self, headers, upload_id, filename, expect_status=200):
        r = requests.post(
            f"{BASE_URL}/api/equipment-import/parse-invoice/finalize",
            headers=headers,
            data={"upload_id": upload_id, "filename": filename, "content_type": "application/pdf"},
            timeout=30,
        )
        assert r.status_code == expect_status, f"finalize: {r.status_code} {r.text}"
        return r.json() if r.status_code == 200 else r

    def _poll(self, headers, job_id, timeout=180):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            r = requests.get(
                f"{BASE_URL}/api/equipment-import/parse-invoice/status/{job_id}",
                headers=headers, timeout=15,
            )
            assert r.status_code == 200, f"status: {r.status_code} {r.text}"
            j = r.json()
            last = j
            if j.get("status") in ("done", "error"):
                return j
            time.sleep(2)
        pytest.fail(f"Job did not finish within {timeout}s: last={last}")

    # 1. SINGLE-CHUNK HAPPY PATH
    def test_single_chunk_happy_path(self, auth_headers):
        pdf = _build_small_invoice_pdf()
        assert len(pdf) < CHUNK_SIZE, f"sanity: small pdf should fit in one chunk (size={len(pdf)})"
        upload_id, total = self._chunk_upload(auth_headers, pdf, "TEST_small_invoice.pdf")
        assert total == 1

        fin = self._finalize(auth_headers, upload_id, "TEST_small_invoice.pdf")
        assert "job_id" in fin
        assert fin["status"] == "processing"

        job = self._poll(auth_headers, fin["job_id"], timeout=120)
        assert job["status"] == "done", f"Job did not reach done: {job}"
        result = job.get("result") or {}
        assert "equipment_count" in result
        assert result["equipment_count"] >= 1, f"Expected >=1 equipment; got: {result}"
        assert "supplier_name" in result
        assert "import_id" in result and result["import_id"], "Missing import_id in result"
        # page_count should be set on the job (set by worker, fitz)
        assert job.get("page_count") == 1

    # 2. MULTI-CHUNK REASSEMBLY
    def test_multi_chunk_reassembly(self, auth_headers):
        pdf = _build_large_invoice_pdf(target_bytes=int(3.2 * 1024 * 1024))
        assert len(pdf) > CHUNK_SIZE, f"sanity: large pdf must exceed chunk size (size={len(pdf)})"

        upload_id, total = self._chunk_upload(auth_headers, pdf, "TEST_large_invoice.pdf")
        assert total >= 2, f"Expected multiple chunks, got {total}"

        fin = self._finalize(auth_headers, upload_id, "TEST_large_invoice.pdf")
        assert "job_id" in fin
        assert fin["status"] == "processing"

        job = self._poll(auth_headers, fin["job_id"], timeout=240)
        assert job["status"] == "done", f"Multi-chunk job did not finish cleanly: {job}"
        result = job.get("result") or {}
        # Reassembled bytes must yield a usable PDF that gets extracted.
        assert result.get("equipment_count", 0) >= 1, f"Multi-chunk extraction returned 0 equipment: {result}"

    # 3. FINALIZE with bogus upload_id → 404
    def test_finalize_unknown_upload_id_returns_404(self, auth_headers):
        bogus = f"does-not-exist-{uuid.uuid4().hex[:10]}"
        r = requests.post(
            f"{BASE_URL}/api/equipment-import/parse-invoice/finalize",
            headers=auth_headers,
            data={"upload_id": bogus, "filename": "bogus.pdf", "content_type": "application/pdf"},
            timeout=15,
        )
        assert r.status_code == 404, f"Expected 404 for unknown upload; got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "upload" in detail and ("not found" in detail or "expired" in detail), f"Unexpected detail: {detail}"

    # 4. CORRUPT / non-PDF file → either validate_upload 4xx OR job error (NOT 520/hang)
    def test_corrupt_pdf_surfaces_clean_error(self, auth_headers):
        garbage = b"this is not a pdf, just garbage bytes" * 100
        upload_id, total = self._chunk_upload(auth_headers, garbage, "TEST_garbage.pdf")
        assert total == 1
        r = requests.post(
            f"{BASE_URL}/api/equipment-import/parse-invoice/finalize",
            headers=auth_headers,
            data={"upload_id": upload_id, "filename": "TEST_garbage.pdf", "content_type": "application/pdf"},
            timeout=30,
        )
        # Two valid behaviours: validate_upload rejects synchronously (4xx),
        # OR finalize accepts and the background worker marks the job as error.
        assert r.status_code in (200, 400, 415, 422), f"Unexpected status from finalize on garbage: {r.status_code} {r.text}"
        if r.status_code == 200:
            job_id = r.json()["job_id"]
            job = self._poll(auth_headers, job_id, timeout=120)
            assert job["status"] == "error", f"Expected job error for garbage PDF, got: {job}"
            assert job.get("error"), "Job error should include an error message"

    # 5. CHUNK DOCS DELETED AFTER FINALIZE
    def test_chunks_deleted_after_finalize(self, auth_headers):
        pdf = _build_small_invoice_pdf()
        upload_id, _ = self._chunk_upload(auth_headers, pdf, "TEST_cleanup.pdf")
        # Finalize → chunks should be removed before worker runs.
        self._finalize(auth_headers, upload_id, "TEST_cleanup.pdf")
        # Re-finalize with same upload_id → must now 404 (chunks gone).
        r = requests.post(
            f"{BASE_URL}/api/equipment-import/parse-invoice/finalize",
            headers=auth_headers,
            data={"upload_id": upload_id, "filename": "TEST_cleanup.pdf", "content_type": "application/pdf"},
            timeout=15,
        )
        assert r.status_code == 404, f"Chunks should be deleted; got: {r.status_code} {r.text}"

    # 6. FINALIZE returns IMMEDIATELY (no synchronous long-hold)
    def test_finalize_returns_immediately(self, auth_headers):
        pdf = _build_small_invoice_pdf()
        upload_id, _ = self._chunk_upload(auth_headers, pdf, "TEST_immediate.pdf")
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/equipment-import/parse-invoice/finalize",
            headers=auth_headers,
            data={"upload_id": upload_id, "filename": "TEST_immediate.pdf", "content_type": "application/pdf"},
            timeout=30,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200
        # Finalize must NOT block on extraction. AI extraction takes ~3-15s;
        # finalize itself should return in well under 10s (typically <1s).
        assert elapsed < 10, f"finalize took {elapsed:.2f}s — synchronous long-hold suspected"
        assert r.json().get("status") == "processing"
