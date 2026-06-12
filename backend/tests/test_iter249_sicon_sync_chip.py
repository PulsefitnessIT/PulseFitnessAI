"""Iter 249 — Sicon sync chip on the Service Desk case board.

`GET /api/svc/cases` enriches each row with `sicon_sync_state`
(error > queued > synced > dry_run, worst-wins from the Sicon outbox;
cases that came FROM Sicon with no outbound rows count as synced) and
`sicon_sync_pending`. The desk board renders it as a chip under the
status pill.
"""

import asyncio
import os

import pytest
import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
HUB_ORG = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"
SICON_CASE_ID = 991249
SICON_REF = "PYTEST-SICON-CHIP"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


def _db():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cleanup():
    async def run():
        db = _db()
        case = await db.svc_cases.find_one({"reference": SICON_REF}, {"_id": 0, "id": 1})
        if case:
            await db.svc_case_events.delete_many({"case_id": case["id"]})
        await db.svc_cases.delete_many({"reference": SICON_REF})
        await db.svc_sicon_inbox.delete_many({"sicon_key": str(SICON_CASE_ID)})
        await db.svc_sicon_outbox.delete_many({"$or": [
            {"payload.ServiceCallReference": SICON_REF},
            {"payload.CallReference": SICON_REF},
        ]})
    _run(run())


@pytest.fixture(scope="module", autouse=True)
def clean_slate():
    _cleanup()
    yield
    _cleanup()


def _find_case(admin: requests.Session) -> dict:
    r = admin.get(f"{BASE_URL}/api/svc/cases", params={"search": SICON_REF}, timeout=30)
    assert r.status_code == 200, r.text
    rows = [c for c in r.json()["cases"] if c["reference"] == SICON_REF]
    assert rows, "test case missing from the board"
    return rows[0]


def test_inbound_only_case_shows_synced():
    admin = _login(*MASTER_ADMIN)
    r = admin.post(f"{BASE_URL}/api/integrations/admin/sicon/simulate-inbound", json={
        "organization_id": HUB_ORG,
        "payload": {"SiSMCaseId": SICON_CASE_ID, "CallReference": SICON_REF,
                    "Description": "Chip test", "StatusID": "Logged", "PriorityID": 3},
    }, timeout=30)
    assert r.status_code == 200, r.text
    case = _find_case(admin)
    assert case["sicon_sync_state"] == "synced", case.get("sicon_sync_state")
    assert case["sicon_sync_pending"] == 0


def test_local_edit_flips_chip_to_queued():
    admin = _login(*MASTER_ADMIN)
    case = _find_case(admin)
    r = admin.put(f"{BASE_URL}/api/svc/cases/{case['id']}",
                  json={"priority": "p2"}, timeout=30)
    assert r.status_code == 200, r.text
    case = _find_case(admin)
    assert case["sicon_sync_state"] == "queued"
    assert case["sicon_sync_pending"] >= 1


def test_drain_flips_chip_to_dry_run():
    admin = _login(*MASTER_ADMIN)

    async def age_rows():
        await _db().svc_sicon_outbox.update_many(
            {"status": "pending", "$or": [
                {"payload.ServiceCallReference": SICON_REF},
                {"payload.CallReference": SICON_REF},
            ]},
            {"$set": {"created_at": "1970-01-01T00:00:00+00:00"}})
    _run(age_rows())

    r = admin.post(f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain?max_rows=10",
                   timeout=60)
    assert r.status_code == 200, r.text
    case = _find_case(admin)
    assert case["sicon_sync_state"] == "dry_run", case.get("sicon_sync_state")
    assert case["sicon_sync_pending"] == 0


def test_frontend_renders_chip():
    src = open("/app/frontend/src/pages/ServiceOps/ServiceDeskPage.js", encoding="utf-8").read()
    assert "SICON_SYNC_META" in src
    assert "case-sicon-sync-" in src
    assert "sicon_sync_state" in src
