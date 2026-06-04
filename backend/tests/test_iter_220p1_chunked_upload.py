"""Iter 220 P1 — chunked / streamed price-list upload.

Large workbooks are uploaded in slices to bypass proxy body-size limits,
then reassembled and analysed exactly like a single-request upload.

Endpoints:
  - POST /api/crm/price-list/import/upload-chunk
  - POST /api/crm/price-list/import/upload-finalize
"""
import io
import math
import os
import uuid

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL, ADMIN_PASS = "admin@gymaxisai.com", "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _sample_xlsx_bytes(rows=300) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catalogue"
    ws.append(["SKU", "Name", "Cost", "Sell"])
    for i in range(rows):
        ws.append([f"SK-{i:04d}", f"Product {i}", i + 1, (i + 1) * 2])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _upload_chunked(admin_h, data: bytes, name: str, chunk_size=8 * 1024):
    total = math.ceil(len(data) / chunk_size)
    uid = str(uuid.uuid4())
    for i in range(total):
        blob = data[i * chunk_size:(i + 1) * chunk_size]
        r = requests.post(
            f"{BASE_URL}/api/crm/price-list/import/upload-chunk", headers=admin_h,
            data={"upload_id": uid, "chunk_index": i, "total_chunks": total, "filename": name},
            files={"chunk": (name, blob)}, timeout=60,
        )
        assert r.status_code == 200, (i, r.status_code, r.text[:200])
    return uid, total


def test_chunked_upload_reassembles_and_analyzes(admin_h):
    data = _sample_xlsx_bytes(300)
    uid, total = _upload_chunked(admin_h, data, "chunked_catalogue.xlsx")
    assert total >= 2, "test should exercise multiple chunks"
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload-finalize",
                      headers=admin_h, json={"upload_id": uid}, timeout=120)
    assert r.status_code == 200, r.text[:300]
    imp = r.json()["import"]
    assert imp["size"] == len(data)
    sheet = imp["sheets"][0]
    assert sheet["product_count"] == 300
    assert sheet["has_code"] is True


def test_finalize_missing_chunk_errors(admin_h):
    data = _sample_xlsx_bytes(200)
    chunk_size = 4 * 1024
    total = math.ceil(len(data) / chunk_size)
    if total < 2:
        pytest.skip("file too small to drop a chunk")
    uid = str(uuid.uuid4())
    # send all but the last chunk
    for i in range(total - 1):
        blob = data[i * chunk_size:(i + 1) * chunk_size]
        requests.post(f"{BASE_URL}/api/crm/price-list/import/upload-chunk", headers=admin_h,
                      data={"upload_id": uid, "chunk_index": i, "total_chunks": total, "filename": "x.xlsx"},
                      files={"chunk": ("x.xlsx", blob)}, timeout=60)
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload-finalize",
                      headers=admin_h, json={"upload_id": uid}, timeout=60)
    assert r.status_code == 400
    assert "incomplete" in r.text.lower()


def test_finalize_unknown_upload_404(admin_h):
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload-finalize",
                      headers=admin_h, json={"upload_id": "does-not-exist"}, timeout=30)
    assert r.status_code == 404


def test_chunk_rejects_bad_filename(admin_h):
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload-chunk", headers=admin_h,
                      data={"upload_id": str(uuid.uuid4()), "chunk_index": 0, "total_chunks": 1, "filename": "notes.txt"},
                      files={"chunk": ("notes.txt", b"hello")}, timeout=30)
    assert r.status_code == 415
