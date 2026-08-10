"""Tests for BUG A — Large invoice chunked upload (master admin auth)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-eng-booking.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

CHUNK_SIZE = int(1.5 * 1024 * 1024)  # 1.5 MB
PDF_PATH = "/tmp/cars.pdf"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    return s


def test_login_master_admin(session):
    # Confirm session works
    r = session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200, f"/auth/me failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("is_master_admin") is True or data.get("email") == ADMIN_EMAIL


def test_pdf_present():
    assert os.path.exists(PDF_PATH), "Test PDF missing at /tmp/cars.pdf"
    assert os.path.getsize(PDF_PATH) > 2 * 1024 * 1024


def test_chunked_upload_full_flow(session):
    size = os.path.getsize(PDF_PATH)
    total_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
    upload_id = f"TEST_chunk_{int(time.time())}"
    print(f"File size={size} bytes, total_chunks={total_chunks}, upload_id={upload_id}")

    with open(PDF_PATH, "rb") as f:
        for i in range(total_chunks):
            part = f.read(CHUNK_SIZE)
            files = {"file": (f"part_{i}.bin", part, "application/octet-stream")}
            data = {"upload_id": upload_id, "chunk_index": str(i), "total_chunks": str(total_chunks)}
            r = session.post(f"{API}/equipment-import/parse-invoice/chunk", files=files, data=data, timeout=60)
            assert r.status_code == 200, (
                f"Chunk {i}/{total_chunks} failed: status={r.status_code} body={r.text[:300]}"
            )
            print(f"  chunk {i} OK ({len(part)} bytes)")

    # Finalize
    r = session.post(
        f"{API}/equipment-import/parse-invoice/finalize",
        data={"upload_id": upload_id, "filename": "cars.pdf", "content_type": "application/pdf"},
        timeout=60,
    )
    assert r.status_code == 200, f"Finalize failed: status={r.status_code} body={r.text[:500]}"
    fin = r.json()
    assert "job_id" in fin, f"No job_id in finalize response: {fin}"
    job_id = fin["job_id"]
    print(f"Job created: {job_id}")

    # Poll up to 5 minutes
    deadline = time.time() + 300
    last_status = None
    while time.time() < deadline:
        r = session.get(f"{API}/equipment-import/parse-invoice/status/{job_id}", timeout=30)
        assert r.status_code == 200, f"Status poll failed: {r.status_code} {r.text[:200]}"
        j = r.json()
        last_status = j.get("status")
        print(f"  status={last_status}")
        if last_status == "done":
            result = j.get("result") or j
            equipment_count = (
                result.get("equipment_count")
                or len(result.get("equipment", []) or [])
                or len((result.get("result") or {}).get("equipment", []) or [])
            )
            assert equipment_count and equipment_count > 0, f"equipment_count=0 in result: {j}"
            print(f"DONE: equipment_count={equipment_count}")
            return
        if last_status == "error":
            pytest.fail(f"Background job failed: {j}")
        time.sleep(5)

    pytest.fail(f"Job did not complete within 5 min; last_status={last_status}")


def test_small_non_chunked_invoice_still_works(session):
    """Confirm legacy single-shot endpoint still works for small PDFs."""
    # Build a tiny valid PDF (~1 KB)
    tiny_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 10 100 Td (Test Invoice) Tj ET\nendstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n"
        b"0000000110 00000 n \n0000000180 00000 n \ntrailer<</Size 5/Root 1 0 R>>\n"
        b"startxref\n260\n%%EOF\n"
    )
    files = {"file": ("tiny.pdf", tiny_pdf, "application/pdf")}
    r = session.post(f"{API}/equipment-import/parse-invoice", files=files, timeout=180)
    # We don't require equipment to be extracted from a fake PDF, just that the endpoint accepts it (no 413/502)
    # Accept 200/400/422/500 — only fail on transport-level regressions (413 = body too large, 502 = proxy)
    assert r.status_code != 413, "Got 413 on small single-shot upload (regression)"
    assert r.status_code != 502, "Got 502 on small single-shot upload (regression)"
    assert r.status_code in (200, 400, 422, 500), f"Unexpected status {r.status_code}: {r.text[:300]}"
    print(f"Small upload returned {r.status_code}")
