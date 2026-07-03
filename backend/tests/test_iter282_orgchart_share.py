"""Iter 282 — Org Chart public share link (publish / public fetch / rotate / unpublish).

Verifies the read-only public endpoint requires NO auth, never leaks
sensitive fields, and that rotate/unpublish immediately invalidate access.
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://ops-parts-request.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter282-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter282-owner-{uuid.uuid4().hex[:8]}"
_S1 = f"iter282-s1-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter282 Co"})
    await db.users.insert_one({"id": _OWNER, "organization_id": _ORG, "email": f"owner-{_ORG}@ex.com", "full_name": "Owner", "role": "owner", "disabled": False})
    await db.staff_members.insert_one({"id": _S1, "organization_id": _ORG, "full_name": "Alice", "primary_role": "manager", "email": "alice@secret.com", "phone": "0700", "active": True, "site_ids": []})
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    for col in ("organizations", "users", "staff_members", "org_charts", "org_chart_nodes",
                "org_chart_audit", "org_chart_edges", "org_chart_notes", "org_chart_versions"):
        await db[col].delete_many({"organization_id": _ORG})
    c.close()


def test_orgchart_public_share():
    _run(_seed())
    try:
        h = {"Authorization": f"Bearer {create_token(_OWNER)}"}
        cid = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "Public", "auto_build": True}, headers=h).json()["id"]

        # add a confidential note — must NEVER appear publicly
        n1 = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).json()["nodes"][0]
        requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/nodes/{n1['id']}/notes",
                      json={"node_id": n1["id"], "body": "TOP SECRET", "confidential": True}, headers=h)

        # publish without contact
        pub = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/publish", json={"show_contact": False}, headers=h).json()
        token = pub["public_token"]

        # public fetch — NO auth header
        pr = requests.get(f"{API}/api/staffing/orgchart/public/{token}")
        assert pr.status_code == 200, pr.text
        body = pr.json()
        assert body["name"] == "Public" and body["nodes"]
        node = body["nodes"][0]
        # leak guards
        assert "email" not in node and "phone" not in node
        assert "staff_id" not in node and "notes" not in node and "salary_band" not in node
        raw = pr.text
        assert "TOP SECRET" not in raw and "alice@secret.com" not in raw

        # opt-in contact → email/phone now present
        requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/publish", json={"show_contact": True}, headers=h)
        node2 = requests.get(f"{API}/api/staffing/orgchart/public/{token}").json()["nodes"][0]
        assert "email" in node2

        # rotate invalidates old token
        new_token = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/publish/rotate", headers=h).json()["public_token"]
        assert new_token != token
        assert requests.get(f"{API}/api/staffing/orgchart/public/{token}").status_code == 404
        assert requests.get(f"{API}/api/staffing/orgchart/public/{new_token}").status_code == 200

        # unpublish kills the link
        requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}/publish", headers=h)
        assert requests.get(f"{API}/api/staffing/orgchart/public/{new_token}").status_code == 404

        requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h)
    finally:
        _run(_cleanup())
