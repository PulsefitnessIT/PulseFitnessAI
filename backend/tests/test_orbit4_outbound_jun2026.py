"""Offline tests for utils/orbit4_outbound.resync_case — the Pulse→Orbit4 case
status resync that previously 501'd (missing module). Orbit4 API is mocked; no
network. Verifies: no-ticket skip, status mirror to the right ticket, error
capture, and that svc_cases.orbit4_sync is stamped each time.
"""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
import utils.orbit4_outbound as ob


class FakeClient:
    calls = []

    def __init__(self, base_url, api_token, **kw):
        self.base_url = base_url
        self.api_token = api_token

    async def update_ticket(self, ticket_id, payload):
        FakeClient.calls.append((self.base_url, self.api_token, ticket_id, payload))
        if getattr(FakeClient, "raise_error", False):
            from utils.orbit4_client import Orbit4APIError
            raise Orbit4APIError("PUT /tickets → 500")
        return {"id": ticket_id, "status": payload.get("status")}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeClient.calls = []
    FakeClient.raise_error = False
    monkeypatch.setattr(ob, "Orbit4Client", FakeClient)
    monkeypatch.setattr(ob, "decrypt_secrets_in_dict", lambda d: d)  # tokens stored plain in test
    yield


@pytest.fixture
def org():
    o = f"itest-o4out-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(db.svc_cases.delete_many({"organization_id": o}))
    drive_async(db.svc_orbit4_connections.delete_many({"organization_id": o}))


def _user():
    return {"id": "u-1"}


async def _seed(org, *, ticket=True, conn=True, token="TOK"):
    case_id = str(uuid.uuid4())
    doc = {"id": case_id, "organization_id": org, "status": "closed",
           "resolution": "Belt replaced"}
    if ticket:
        doc["orbit4_ticket_id"] = "9090"
    await db.svc_cases.insert_one(doc)
    if conn:
        await db.svc_orbit4_connections.insert_one(
            {"id": str(uuid.uuid4()), "organization_id": org,
             "base_url": "https://api.orbit4.test/v1", "api_token": token, "enabled": True})
    return case_id


def test_resync_mirrors_status_to_ticket(org):
    async def run():
        cid = await _seed(org)
        res = await ob.resync_case(await db.svc_cases.find_one({"id": cid}, {"_id": 0}), _user())
        case = await db.svc_cases.find_one({"id": cid}, {"_id": 0})
        return res, case
    res, case = drive_async(run())
    assert res["ok"] is True
    assert res["orbit4_status"] == "closed"                    # mapped from case status
    assert FakeClient.calls, "Orbit4 update_ticket was not called"
    base, token, tid, payload = FakeClient.calls[0]
    assert base == "https://api.orbit4.test/v1" and token == "TOK" and tid == 9090
    assert payload["status"] == "closed" and "closed_at" in payload
    assert case["orbit4_sync"]["status"] == "synced"


def test_resync_skips_when_no_ticket(org):
    async def run():
        cid = await _seed(org, ticket=False)
        res = await ob.resync_case(await db.svc_cases.find_one({"id": cid}, {"_id": 0}), _user())
        case = await db.svc_cases.find_one({"id": cid}, {"_id": 0})
        return res, case
    res, case = drive_async(run())
    assert res["ok"] is False and "no linked Orbit 4 ticket" in res["reason"]
    assert not FakeClient.calls
    assert case["orbit4_sync"]["status"] == "skipped"


def test_resync_errors_when_no_connection(org):
    async def run():
        cid = await _seed(org, conn=False)
        res = await ob.resync_case(await db.svc_cases.find_one({"id": cid}, {"_id": 0}), _user())
        case = await db.svc_cases.find_one({"id": cid}, {"_id": 0})
        return res, case
    res, case = drive_async(run())
    assert res["ok"] is False and "No Orbit 4 connection" in res["reason"]
    assert case["orbit4_sync"]["reason"] == "no_connection"


def test_resync_captures_api_error(org):
    async def run():
        FakeClient.raise_error = True
        cid = await _seed(org)
        res = await ob.resync_case(await db.svc_cases.find_one({"id": cid}, {"_id": 0}), _user())
        case = await db.svc_cases.find_one({"id": cid}, {"_id": 0})
        return res, case
    res, case = drive_async(run())
    assert res["ok"] is False and "Orbit 4 update failed" in res["reason"]
    assert case["orbit4_sync"]["status"] == "error"
    assert case["orbit4_sync"]["attempted_status"] == "closed"
