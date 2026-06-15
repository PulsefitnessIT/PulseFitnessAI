"""Iter 284 — Verify real Pulse PDF imports ~108 people via document-import flow.

Uploads the actual Pulse Fitness May 2025 PDF (text-layer source) and asserts
the async job returns ~100+ rows including known names with correct manager links.
"""
import asyncio
import os
import time
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
PULSE_PDF = "/tmp/pulse.pdf"

_ORG = f"iter284-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter284-owner-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter284 Co"})
    await db.users.insert_one({"id": _OWNER, "organization_id": _ORG, "email": f"o-{_ORG}@ex.com", "full_name": "Owner", "role": "owner", "disabled": False})
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    for col in ("organizations", "users", "org_charts", "org_chart_nodes", "org_chart_import_jobs"):
        await db[col].delete_many({"organization_id": _ORG})
    c.close()


def test_pulse_pdf_import():
    assert os.path.exists(PULSE_PDF), "download Pulse PDF first"
    _run(_seed())
    try:
        h = {"Authorization": f"Bearer {create_token(_OWNER)}"}
        cid = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "PulseImp", "auto_build": False}, headers=h).json()["id"]

        with open(PULSE_PDF, "rb") as fh:
            files = {"file": ("pulse.pdf", fh, "application/pdf")}
            start = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/import/document", files=files, headers=h)
        assert start.status_code == 200, start.text
        body = start.json()
        assert body["status"] == "processing"
        assert (start.elapsed.total_seconds() < 60), f"start took {start.elapsed.total_seconds()}s (>60s = 502 risk)"
        job_id = body["job_id"]

        job = None
        for _ in range(60):  # up to ~180s
            r = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/import/document/{job_id}", headers=h)
            assert r.status_code == 200, r.text
            job = r.json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(3)
        assert job["status"] == "done", job
        rows = job.get("rows", [])
        print(f"\nExtracted {len(rows)} rows; source={job.get('source')}")
        # text-layer extraction expected
        assert job.get("source") in ("text", "vision"), job
        assert len(rows) >= 80, f"expected ~108 rows, got {len(rows)}"
        names = {r["full_name"] for r in rows}
        assert "Chris Johnson" in names, f"missing Chris Johnson; sample: {list(names)[:10]}"
        # manager linkage spot-check
        with_mgr = [r for r in rows if r.get("manager_name")]
        assert len(with_mgr) >= 50, f"expected many reports-to links, got {len(with_mgr)}"

        requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h)
    finally:
        _run(_cleanup())
