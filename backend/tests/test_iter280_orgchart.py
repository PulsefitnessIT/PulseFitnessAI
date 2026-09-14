"""Iter 280 — Org Chart Builder (Operations → Staffing → Org Chart).

Integration test: seeds a temp org + staff via motor, mints a real owner
JWT, drives the live preview API end-to-end (create chart → auto-build →
add vacancy → set reporting line → cycle guard → insights → import →
CSV export → delete), then cleans up.
"""
import asyncio
import os
import uuid

import requests
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import create_token

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_ORG = f"iter280-org-{uuid.uuid4().hex[:8]}"
_OWNER = f"iter280-owner-{uuid.uuid4().hex[:8]}"
_S1 = f"iter280-s1-{uuid.uuid4().hex[:8]}"
_S2 = f"iter280-s2-{uuid.uuid4().hex[:8]}"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _seed():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.insert_one({"id": _ORG, "name": "Iter280 Co", "custom_staff_roles": ["field_engineer"]})
    await db.users.insert_one({
        "id": _OWNER, "organization_id": _ORG, "email": f"owner-{_ORG}@ex.com",
        "full_name": "Owner Boss", "role": "owner", "disabled": False,
    })
    for sid, name, role in [(_S1, "Alice Manager", "manager"), (_S2, "Bob Engineer", "field_engineer")]:
        await db.staff_members.insert_one({
            "id": sid, "organization_id": _ORG, "full_name": name,
            "primary_role": role, "email": f"{sid}@ex.com", "active": True, "site_ids": [],
        })
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    await db.organizations.delete_one({"id": _ORG})
    await db.users.delete_many({"organization_id": _ORG})
    await db.staff_members.delete_many({"organization_id": _ORG})
    await db.org_charts.delete_many({"organization_id": _ORG})
    await db.org_chart_nodes.delete_many({"organization_id": _ORG})
    c.close()


def test_orgchart_full_flow():
    _run(_seed())
    try:
        token = create_token(_OWNER)
        h = {"Authorization": f"Bearer {token}"}

        # create chart with auto-build → should seed 2 staff nodes
        r = requests.post(f"{API}/api/staffing/orgchart/charts", json={"name": "Test Org", "auto_build": True}, headers=h)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        assert r.json()["node_count"] == 2, r.json()

        # get chart
        data = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).json()
        nodes = {n["full_name"]: n for n in data["nodes"]}
        assert "Alice Manager" in nodes and "Bob Engineer" in nodes
        assert nodes["Bob Engineer"]["is_engineer"] is True
        alice, bob = nodes["Alice Manager"], nodes["Bob Engineer"]

        # add a vacancy
        rv = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/nodes",
                           json={"type": "vacancy", "full_name": "New PT", "department": "Fitness"}, headers=h)
        assert rv.status_code == 200, rv.text
        assert rv.json()["recruitment_stage"] == "Planned"

        # set Bob to report to Alice WITH write-back to staff record
        ru = requests.patch(f"{API}/api/staffing/orgchart/charts/{cid}/nodes/{bob['id']}",
                            json={"manager_node_id": alice["id"], "write_back_staff": True}, headers=h)
        assert ru.status_code == 200, ru.text

        # cycle guard: Alice cannot now report to Bob
        rc = requests.patch(f"{API}/api/staffing/orgchart/charts/{cid}/nodes/{alice['id']}",
                            json={"manager_node_id": bob["id"]}, headers=h)
        assert rc.status_code == 400, rc.text

        # write-back persisted manager_staff_id on Bob's staff record
        async def _check():
            c = AsyncIOMotorClient(MONGO_URL); db = c[DB_NAME]
            doc = await db.staff_members.find_one({"id": _S2}); c.close(); return doc
        assert _run(_check()).get("manager_staff_id") == _S1

        # insights
        ins = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/insights", headers=h).json()
        assert ins["total_people"] == 2
        assert ins["total_managers"] == 1  # Alice has a report now
        assert ins["open_vacancies"] == 1

        # import preview + apply
        rows = [{"full_name": "Carol Sales", "email": "carol@ex.com", "job_title": "Sales", "manager_name": "Alice Manager"}]
        prev = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/import/preview", json={"rows": rows}, headers=h).json()
        assert prev["total"] == 1 and prev["new"] == 1
        appl = requests.post(f"{API}/api/staffing/orgchart/charts/{cid}/import/apply", json={"rows": rows, "options": {}}, headers=h).json()
        assert appl["imported"] == 1

        # CSV export
        csv = requests.get(f"{API}/api/staffing/orgchart/charts/{cid}/export.csv", headers=h)
        assert csv.status_code == 200 and "Carol Sales" in csv.text

        # delete chart
        assert requests.delete(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).status_code == 200
        assert requests.get(f"{API}/api/staffing/orgchart/charts/{cid}", headers=h).status_code == 404
    finally:
        _run(_cleanup())
