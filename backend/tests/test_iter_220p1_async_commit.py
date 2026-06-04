"""Iter 220 P1 — background (async) commit for large price-list imports.

Verifies the job lifecycle: commit-async -> poll -> done, with a version
created. Self-cleans all artifacts (products, version, items, import, job)
so it never pollutes the catalogue.

Endpoints:
  - POST /api/crm/price-list/import/{id}/commit-async
  - GET  /api/crm/price-list/import/commit-jobs/{job_id}
"""
import asyncio
import io
import os
import time

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


def _upload_test_sheet(admin_h, rows=120) -> dict:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Async Test"
    ws.append(["SKU", "Name", "Cost", "Sell"])
    for i in range(rows):
        ws.append([f"ASYNCTEST-{i:04d}", f"Async Product {i}", i + 1, (i + 1) * 2])
    buf = io.BytesIO()
    wb.save(buf)
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload", headers=admin_h,
                      files={"file": ("async_test.xlsx", buf.getvalue())}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    return r.json()["import"]


async def _cleanup(import_id, version_id, job_id):
    from utils.database import db
    await db.crm_products.delete_many({"import_batch_id": import_id})
    if version_id:
        await db.crm_price_list_version_items.delete_many({"version_id": version_id})
    await db.crm_price_list_versions.delete_many({"import_batch_id": import_id})
    await db.crm_price_imports.delete_many({"id": import_id})
    await db.crm_price_import_files.delete_many({"import_id": import_id})
    await db.crm_price_commit_jobs.delete_many({"id": job_id})


def test_async_commit_lifecycle(admin_h):
    imp = _upload_test_sheet(admin_h, rows=120)
    iid = imp["id"]
    s = imp["sheets"][0]
    cfg = {"name": s["name"], "header_row": s["header_row"], "header_band": s["header_band"],
           "code_col": s["code_col"], "name_col": s["name_col"], "mappings": s["auto_mapping"], "selected": True}

    start = requests.post(f"{BASE_URL}/api/crm/price-list/import/{iid}/commit-async",
                          headers=admin_h, json={"sheets": [cfg], "options": {"mode": "draft"}}, timeout=30)
    assert start.status_code == 200, start.text[:200]
    body = start.json()
    assert body["total"] == 120
    job_id = body["job_id"]

    final = None
    for _ in range(40):
        time.sleep(1)
        j = requests.get(f"{BASE_URL}/api/crm/price-list/import/commit-jobs/{job_id}", headers=admin_h, timeout=30).json()
        if j["status"] in ("done", "error"):
            final = j
            break
    try:
        assert final is not None, "commit job did not finish in time"
        assert final["status"] == "done", final.get("message")
        assert final["created"] == 120
        assert final["version_id"]
        assert final.get("version_label")
    finally:
        asyncio.run(_cleanup(iid, (final or {}).get("version_id"), job_id))


def test_commit_job_unknown_404(admin_h):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/import/commit-jobs/nope", headers=admin_h, timeout=30)
    assert r.status_code == 404
