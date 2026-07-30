"""Iter 281 — Org Chart AI endpoints (live LLM via Emergent key).

Validates:
- POST /api/staffing/orgchart/charts/{cid}/ai/generate  → rows w/ inferred reporting + vacancy
- POST .../ai/analyze   → {summary, issues[], suggestions[]}
- POST .../ai/draft-jd  → {title, summary, responsibilities[], requirements[]}
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter281ai-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter281ai-owner-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter281 AI Co"})
    await db.users.insert_one({"id": _OWNER, "organization_id": _ORG, "email": f"owner-{_ORG}@ex.com", "full_name": "Owner", "role": "owner", "disabled": False})
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    for col in ("organizations", "users", "org_charts", "org_chart_nodes",
                "org_chart_versions", "org_chart_audit", "org_chart_edges", "org_chart_notes"):
        await db[col].delete_many({"organization_id": _ORG})
    c.close()


def test_orgchart_ai_live():
    _run(_seed())
    try:
        h = {"Authorization": f"Bearer {create_token(_OWNER)}"}
        # Create a chart
        r = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "AI Test", "auto_build": True}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        print(f"chart_id={cid}")

        # --- AI generate ---
        payload = {"text": "Sarah is the Gym Manager. Tom is a personal trainer reporting to Sarah. We need a receptionist."}
        r = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/ai/generate", headers=h, json=payload, timeout=90)
        assert r.status_code == 200, f"ai/generate failed: {r.status_code} {r.text}"
        gen = r.json()
        rows = gen.get("rows") or []
        assert isinstance(rows, list) and len(rows) >= 2, f"expected rows, got: {gen}"
        # Tom should report to Sarah
        tom_row = next((row for row in rows if "tom" in (row.get("full_name") or row.get("name") or "").lower()), None)
        assert tom_row, f"no Tom row: {rows}"
        mgr = (tom_row.get("manager_name") or "").lower()
        assert "sarah" in mgr, f"Tom manager not Sarah: {tom_row}"
        # Receptionist should be a vacancy
        recep = next((row for row in rows if "recept" in (row.get("job_title") or row.get("title") or row.get("full_name") or row.get("name") or "").lower()), None)
        assert recep, f"no receptionist row: {rows}"
        assert str(recep.get("vacancy") or "").lower() in ("yes", "true", "1"), f"receptionist not vacancy: {recep}"
        print(f"AI generate OK: {len(rows)} rows")

        # Apply a template to add nodes so analyze has data
        ap = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/apply-template/service_company", headers=h, timeout=30)
        assert ap.status_code == 200, ap.text

        # --- AI analyze ---
        r = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/ai/analyze", headers=h, json={}, timeout=90)
        assert r.status_code == 200, f"ai/analyze failed: {r.status_code} {r.text}"
        an = r.json()
        assert "summary" in an and "issues" in an and "suggestions" in an, f"analyze shape: {an}"
        assert isinstance(an["issues"], list) and isinstance(an["suggestions"], list)
        print(f"AI analyze OK: summary len={len(an.get('summary') or '')}, issues={len(an['issues'])}, suggestions={len(an['suggestions'])}")

        # --- AI draft-jd ---
        r = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/ai/draft-jd", headers=h, json={"title": "Field Engineer"}, timeout=90)
        assert r.status_code == 200, f"ai/draft-jd failed: {r.status_code} {r.text}"
        jd = r.json()
        assert jd.get("title") and jd.get("summary"), f"jd missing title/summary: {jd}"
        assert isinstance(jd.get("responsibilities"), list) and len(jd["responsibilities"]) >= 3, f"jd responsibilities: {jd}"
        assert isinstance(jd.get("requirements"), list) and len(jd["requirements"]) >= 2, f"jd requirements: {jd}"
        print(f"AI draft-jd OK: {len(jd['responsibilities'])} resp / {len(jd['requirements'])} req")
    finally:
        _run(_cleanup())
