"""Iter 283 — Org Chart: import an existing chart document (async OCR job).

Uploads a small generated PDF, polls the async job to completion, and asserts
the extracted rows + hierarchy. Exercises the full pipeline (fitz extraction
→ text/vision LLM → rows). Makes one live LLM call.
"""
import asyncio
import io
import os
import time
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://fitness-ai-migrate.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter283-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter283-owner-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter283 Co"})
    await db.users.insert_one({"id": _OWNER, "organization_id": _ORG, "email": f"o-{_ORG}@ex.com", "full_name": "Owner", "role": "owner", "disabled": False})
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    for col in ("organizations", "users", "org_charts", "org_chart_nodes", "org_chart_import_jobs"):
        await db[col].delete_many({"organization_id": _ORG})
    c.close()


def _mini_pdf() -> bytes:
    import fitz
    doc = fitz.open(); p = doc.new_page()
    p.insert_text((72, 72), "Org Chart\nJane Smith - CEO\nTom Brown - CTO reports to Jane Smith\nLina Ray - Engineer reports to Tom Brown", fontsize=12)
    buf = doc.tobytes()
    doc.close()
    return buf


def test_orgchart_import_document():
    _run(_seed())
    try:
        h = {"Authorization": f"Bearer {create_token(_OWNER)}"}
        cid = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "Imp", "auto_build": False}, headers=h).json()["id"]

        files = {"file": ("mini_org.pdf", io.BytesIO(_mini_pdf()), "application/pdf")}
        start = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/import/document", files=files, headers=h)
        assert start.status_code == 200, start.text
        job_id = start.json()["job_id"]
        assert start.json()["status"] == "processing"

        job = None
        for _ in range(40):  # up to ~120s
            job = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/import/document/{job_id}", headers=h).json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(3)
        assert job["status"] == "done", job
        names = {r["full_name"] for r in job["rows"]}
        assert "Jane Smith" in names and "Tom Brown" in names
        tom = next(r for r in job["rows"] if r["full_name"] == "Tom Brown")
        assert tom["manager_name"] == "Jane Smith"

        # rows feed straight into the existing apply pipeline → editable cards
        applied = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/import/apply",
                                json={"rows": job["rows"], "options": {}}, headers=h).json()
        assert applied["imported"] >= 3

        requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h)
    finally:
        _run(_cleanup())
