"""Iter 281 — Org Chart Builder Phase 2 (templates, versions, audit, edges, notes).

AI endpoints are validated separately via curl (they make live LLM calls and
are excluded from CI to avoid cost/flakiness). This covers the deterministic
Phase-2 surface end-to-end against the live preview API.
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://staffing-ops-preview.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter281-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter281-owner-{uuid.uuid4().hex[:8]}"
_S1 = f"iter281-s1-{uuid.uuid4().hex[:8]}"
_S2 = f"iter281-s2-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter281 Co"})
    await db.users.insert_one({"id": _OWNER, "organization_id": _ORG, "email": f"owner-{_ORG}@ex.com", "full_name": "Owner", "role": "owner", "disabled": False})
    for sid, name in [(_S1, "Alice"), (_S2, "Bob")]:
        await db.staff_members.insert_one({"id": sid, "organization_id": _ORG, "full_name": name, "primary_role": "manager", "active": True, "site_ids": []})
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
    for col in ("organizations", "users", "staff_members", "org_charts", "org_chart_nodes",
                "org_chart_versions", "org_chart_audit", "org_chart_edges", "org_chart_notes"):
        await db[col].delete_many({"organization_id": _ORG})
    c.close()


def test_orgchart_phase2():
    _run(_seed())
    try:
        h = {"Authorization": f"Bearer {create_token(_OWNER)}"}
        cid = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "P2", "auto_build": True}, headers=h).json()["id"]
        data = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).json()
        nodes = data["nodes"]
        assert "edges" in data
        n1, n2 = nodes[0], nodes[1]

        # templates
        tpls = requests.get(f"{API}/api/staffing/orgchart/templates", headers=h).json()["templates"]
        assert len(tpls) >= 8
        ap = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/apply-template/service_company", headers=h).json()
        assert ap["added"] > 0

        # versions: save + list + restore
        v = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/versions", json={"label": "v1"}, headers=h).json()
        assert v["version"] == 1
        vlist = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/versions", headers=h).json()["versions"]
        assert len(vlist) == 1 and "nodes" not in vlist[0]
        assert requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/versions/{v['id']}/restore", headers=h).status_code == 200

        # edges (secondary reporting) + guard
        e = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/edges",
                          json={"from_node_id": n1["id"], "to_node_id": n2["id"], "line_type": "dotted"}, headers=h)
        assert e.status_code == 200, e.text
        eid = e.json()["id"]
        bad = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/edges",
                            json={"from_node_id": n1["id"], "to_node_id": n1["id"], "line_type": "dotted"}, headers=h)
        assert bad.status_code == 400
        # edge surfaces in get_chart
        assert any(x["id"] == eid for x in requests.get(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).json()["edges"])
        assert requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}/edges/{eid}", headers=h).status_code == 200

        # notes
        note = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/nodes/{n1['id']}/notes",
                             json={"node_id": n1["id"], "body": "Succession plan", "confidential": True}, headers=h).json()
        assert note["confidential"] is True
        nl = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/nodes/{n1['id']}/notes", headers=h).json()["notes"]
        assert len(nl) == 1
        assert requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}/notes/{note['id']}", headers=h).status_code == 200

        # audit trail recorded the activity
        audit = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/audit", headers=h).json()["audit"]
        actions = {a["action"] for a in audit}
        assert {"template_applied", "version_saved", "version_restored", "edge_added"} <= actions

        requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h)
    finally:
        _run(_cleanup())
