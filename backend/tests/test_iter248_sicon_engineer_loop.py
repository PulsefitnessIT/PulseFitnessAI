"""Iter 248 — Full Sicon ↔ Engineer App loop.

    Sicon Service Desk schedules a case
        → inbound worker merges it into `svc_cases`
        → assigned engineer receives it in the Engineer App
        → engineer actions (time / notes / photos / signature) enqueue
          to `svc_sicon_outbox`
        → outbox worker drains them back to the Sicon Service Desk.

New pieces under test:
- `utils/sicon_inbound_worker.py` (merge_sicon_case, resolve_engineer,
  poll/tick, reverse crosswalks built from the outbound maps).
- Admin endpoints `POST /api/integrations/admin/sicon/poll-now` and
  `POST /api/integrations/admin/sicon/simulate-inbound`.
- Env-gated background workers in server.py (SICON_AUTOSTART_WORKER).
"""

import asyncio
import os

import pytest
import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
ENGINEER = ("engineer.smoke@gymaxisai.com", "EngTest123!")

HUB_ORG = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"
SMOKE_ENGINEER_ID = "7cc0455f-3206-4069-ab95-6db51276a553"
SMOKE_SAGE_USER_ID = "TEST-216v-SAGE001"

SICON_CASE_ID = 991234
SICON_REF = "PYTEST-SICON-LOOP"


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


def _cleanup():
    async def run():
        db = _db()
        case = await db.svc_cases.find_one({"reference": SICON_REF}, {"_id": 0, "id": 1})
        if case:
            await db.svc_case_events.delete_many({"case_id": case["id"]})
            await db.svc_time_entries.delete_many({"case_id": case["id"]})
        await db.svc_cases.delete_many({"reference": SICON_REF})
        await db.svc_sicon_inbox.delete_many({"sicon_key": str(SICON_CASE_ID)})
        await db.svc_sicon_outbox.delete_many({"payload.ServiceCallReference": SICON_REF})
    asyncio.new_event_loop().run_until_complete(run())


@pytest.fixture(scope="module", autouse=True)
def clean_slate():
    _cleanup()
    yield
    _cleanup()


def _simulate_inbound(admin: requests.Session, payload: dict) -> dict:
    r = admin.post(
        f"{BASE_URL}/api/integrations/admin/sicon/simulate-inbound",
        json={"organization_id": HUB_ORG, "payload": payload}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ── Crosswalk integrity ──────────────────────────────────────────

def test_reverse_crosswalks_cover_every_outbound_value():
    import sys
    sys.path.insert(0, "/app/backend")
    from routes.svc.integrations.sicon_sync import STATUS_CROSSWALK, PRIORITY_CROSSWALK
    from utils.sicon_inbound_worker import REVERSE_STATUS, REVERSE_PRIORITY
    for gym_status, sicon_status in STATUS_CROSSWALK.items():
        assert REVERSE_STATUS[sicon_status] in STATUS_CROSSWALK, sicon_status
    for gym_p, sicon_p in PRIORITY_CROSSWALK.items():
        assert REVERSE_PRIORITY[sicon_p] == gym_p


# ── Sicon schedules → engineer receives ──────────────────────────

def test_sicon_scheduled_case_lands_in_engineer_app():
    admin = _login(*MASTER_ADMIN)
    out = _simulate_inbound(admin, {
        "SiSMCaseId": SICON_CASE_ID,
        "CallReference": SICON_REF,
        "Description": "Pytest loop — treadmill belt",
        "Notes": "Scheduled by the Sicon service team.",
        "StatusID": "Assigned",
        "PriorityID": 2,
        "AssignedToSageUserID": SMOKE_SAGE_USER_ID,
        "ScheduledDateTime": "2026-06-13T09:00:00+00:00",
        "SubLocation": {"Description": "Pulse Gym — Manchester Central"},
        "ContactName": "Site Manager",
    })
    assert out["created"] is True
    assert out["reference"] == SICON_REF
    assert out["status"] == "assigned"
    assert out["assigned_engineer_id"] == SMOKE_ENGINEER_ID, (
        "AssignedToSageUserID must resolve via svc_engineers.sage_user_id"
    )

    eng = _login(*ENGINEER)
    r = eng.get(f"{BASE_URL}/api/svc/engineer/jobs?when=open", timeout=20)
    assert r.status_code == 200, r.text
    refs = [j["reference"] for j in r.json()["jobs"]]
    assert SICON_REF in refs, f"engineer must receive the Sicon-scheduled case: {refs}"


def test_sicon_amend_updates_not_duplicates():
    admin = _login(*MASTER_ADMIN)
    out = _simulate_inbound(admin, {
        "SiSMCaseId": SICON_CASE_ID,  # same Sicon id → must merge
        "StatusID": "OnSite",
        "PriorityID": 1,
    })
    assert out["created"] is False, "re-merge must update, never duplicate"
    assert out["status"] == "on_site"
    assert out["reference"] == SICON_REF

    async def count():
        return await _db().svc_cases.count_documents({"reference": SICON_REF})
    assert asyncio.new_event_loop().run_until_complete(count()) == 1


def test_inbound_merge_does_not_echo_back_to_outbox():
    """Anti-echo: an inbound merge must NOT enqueue a `case` push — Sicon
    already owns that state."""
    async def count():
        return await _db().svc_sicon_outbox.count_documents({
            "kind": "case", "payload.CallReference": SICON_REF})
    assert asyncio.new_event_loop().run_until_complete(count()) == 0


# ── Engineer actions flow back to Sicon ──────────────────────────

def test_engineer_time_entry_enqueues_sicon_appointment():
    eng = _login(*ENGINEER)
    async def case_id():
        c = await _db().svc_cases.find_one({"reference": SICON_REF}, {"_id": 0, "id": 1})
        return c["id"]
    cid = asyncio.new_event_loop().run_until_complete(case_id())

    r = eng.post(f"{BASE_URL}/api/svc/engineer/time/start",
                 json={"case_id": cid, "category": "travel"}, timeout=20)
    assert r.status_code == 200, r.text
    r = eng.post(f"{BASE_URL}/api/svc/engineer/time/stop",
                 json={"case_id": cid, "notes": "pytest travel leg"}, timeout=20)
    assert r.status_code == 200, r.text

    async def outbox():
        return await _db().svc_sicon_outbox.find_one(
            {"kind": "appointment", "payload.ServiceCallReference": SICON_REF},
            {"_id": 0, "status": 1, "endpoint": 1})
    row = asyncio.new_event_loop().run_until_complete(outbox())
    assert row, "engineer time must enqueue an appointment for Sicon"
    assert row["status"] == "pending"
    assert row["endpoint"] == "/api/Service/Appointments"


def test_outbox_drain_flushes_engineer_info():
    admin = _login(*MASTER_ADMIN)

    # The shared outbox holds ~1.8k legacy pending rows (no creds yet) and
    # drains oldest-first. Age our row so one bounded drain pass picks it
    # up without mass-simulating the whole backlog.
    async def age_row():
        await _db().svc_sicon_outbox.update_one(
            {"kind": "appointment", "payload.ServiceCallReference": SICON_REF},
            {"$set": {"created_at": "1970-01-01T00:00:00+00:00"}})
    asyncio.new_event_loop().run_until_complete(age_row())

    r = admin.post(f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain?max_rows=5",
                   timeout=60)
    assert r.status_code == 200, r.text

    async def outbox():
        return await _db().svc_sicon_outbox.find_one(
            {"kind": "appointment", "payload.ServiceCallReference": SICON_REF},
            {"_id": 0, "status": 1})
    row = asyncio.new_event_loop().run_until_complete(outbox())
    assert row and row["status"] == "simulated_succeeded"


# ── Ops surfaces ─────────────────────────────────────────────────

def test_poll_now_and_health_endpoints():
    admin = _login(*MASTER_ADMIN)
    r = admin.post(f"{BASE_URL}/api/integrations/admin/sicon/poll-now", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"organizations", "fetched", "created", "updated", "errors"}

    r = admin.get(f"{BASE_URL}/api/integrations/admin/health", timeout=30)
    assert r.status_code == 200, r.text
    sicon = r.json()["sicon"]
    assert sicon["inbox"]["exists"] is True
    assert "pending" in sicon["outbox"]


def test_case_timeline_records_sicon_sync_events():
    async def events():
        db = _db()
        c = await db.svc_cases.find_one({"reference": SICON_REF}, {"_id": 0, "id": 1})
        return [e async for e in db.svc_case_events.find(
            {"case_id": c["id"], "type": "sicon_sync"}, {"_id": 0, "actor_name": 1})]
    rows = asyncio.new_event_loop().run_until_complete(events())
    assert len(rows) >= 2, "create + amend must both leave an audit event"
    assert rows[0]["actor_name"] == "Sicon Service Desk"


def test_workers_are_wired_for_autostart():
    src = open("/app/backend/server.py", encoding="utf-8").read()
    assert "SICON_AUTOSTART_WORKER" in src
    assert "sicon_inbound_worker" in src and "sicon_outbox_worker" in src
    ui = open("/app/frontend/src/pages/Admin/IntegrationsConsole.js", encoding="utf-8").read()
    assert "sicon-poll-inbound" in ui, "console must expose the inbound poll control"
