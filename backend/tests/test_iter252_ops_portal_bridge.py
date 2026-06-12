"""Iter 252 — Operations Portal ⇄ Service Desk reverse bridge.

Forward (pre-existing): an Ops-Portal fault escalated to engineer creates
an `svc_cases` row stamped `source_meta.issue_id`.

Reverse (NEW, under test): as that case moves through the Service Desk /
Engineer App, `utils.svc_ops_bridge.mirror_case_state_to_issue` (hooked
into `utils.svc_state.transition`) mirrors progress back onto the
originating `issues` doc — so the customer's Operations Portal shows
live status, KPI timestamps, a timeline, and the case reference, and the
fault is auto-resolved when the case closes.
"""

import asyncio
import os
import uuid

import pytest
import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
HUB_ORG = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"

ISSUE_ID = f"pytest-issue-{uuid.uuid4().hex[:10]}"
CASE_REF = "PYTEST-OPS-BRIDGE"


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


def _seed_issue_and_case() -> str:
    """Seed an Ops-Portal issue + a linked Service Desk case (assigned,
    so transitions are legal). Returns the case id."""
    case_id = str(uuid.uuid4())

    async def run():
        db = _db()
        now = "2026-06-12T00:00:00+00:00"
        await db.issues.insert_one({
            "id": ISSUE_ID, "organization_id": HUB_ORG,
            "machine_type": "Treadmill", "serial_number": "PYTEST-SN-1",
            "issue_description": "Belt slipping",
            "status": "open", "resolution_type": "engineer",
            "severity": "high", "created_at": now,
            "timeline": [{"event": "fault_logged", "timestamp": now, "by": "Gym Manager"}],
        })
        await db.svc_cases.insert_one({
            "id": case_id, "organization_id": HUB_ORG,
            "reference": CASE_REF, "title": "Treadmill belt", "description": "Belt slipping",
            "status": "assigned", "priority": "p2", "source": "operations_portal",
            "source_meta": {"issue_id": ISSUE_ID, "channel": "operations_portal"},
            "created_at": now, "updated_at": now,
        })

    _run(run())
    return case_id


def _cleanup():
    async def run():
        db = _db()
        await db.issues.delete_many({"id": ISSUE_ID})
        await db.svc_cases.delete_many({"reference": CASE_REF})
        await db.svc_case_events.delete_many({"organization_id": HUB_ORG, "case_id": {"$exists": True}, "reason": "pytest"})
    _run(run())


@pytest.fixture(scope="module", autouse=True)
def fixtures():
    _cleanup()
    _seed_issue_and_case.case_id = _seed_issue_and_case()
    yield
    _cleanup()


def _issue() -> dict:
    async def run():
        return await _db().issues.find_one({"id": ISSUE_ID}, {"_id": 0})
    return _run(run())


def _transition(admin: requests.Session, case_id: str, to: str):
    r = admin.post(f"{BASE_URL}/api/svc/cases/{case_id}/transition",
                   json={"to": to, "reason": "pytest"}, timeout=30)
    assert r.status_code == 200, f"transition to {to}: {r.text}"


def test_en_route_mirrors_to_issue():
    admin = _login(*MASTER_ADMIN)
    cid = _seed_issue_and_case.case_id
    _transition(admin, cid, "en_route")
    issue = _issue()
    assert issue["case_status"] == "en_route"
    assert issue["linked_case_reference"] == CASE_REF
    assert issue["linked_case_id"] == cid
    assert issue.get("engineer_assigned_at")
    assert issue.get("first_response_at")
    assert any(e["event"] == "engineer_en_route" for e in issue["timeline"])
    # fault must still be open at this stage
    assert issue["status"] == "open"


def test_on_site_mirrors_to_issue():
    admin = _login(*MASTER_ADMIN)
    cid = _seed_issue_and_case.case_id
    _transition(admin, cid, "on_site")
    issue = _issue()
    assert issue["case_status"] == "on_site"
    assert issue.get("engineer_arrived_at")
    assert issue.get("work_started_at")
    assert any(e["event"] == "engineer_on_site" for e in issue["timeline"])
    assert issue["status"] == "open"


def test_close_resolves_the_ops_portal_fault():
    admin = _login(*MASTER_ADMIN)
    cid = _seed_issue_and_case.case_id
    _transition(admin, cid, "repaired")
    issue = _issue()
    assert issue.get("work_completed_at")
    assert any(e["event"] == "work_completed" for e in issue["timeline"])
    assert issue["status"] == "open", "still open until the case actually closes"

    _transition(admin, cid, "closed")
    issue = _issue()
    assert issue["status"] == "resolved", "closing the case must resolve the gym's fault"
    assert issue.get("resolved_at")
    assert issue.get("resolution_type") == "engineer"
    assert issue.get("resolved_by")
    assert issue["case_status"] == "closed"
    assert any(e["event"] == "resolved_by_engineer" for e in issue["timeline"])


def test_non_ops_case_is_untouched():
    """A case with no source_meta.issue_id must never write to issues."""
    admin = _login(*MASTER_ADMIN)
    plain_id = str(uuid.uuid4())

    async def seed():
        await _db().svc_cases.insert_one({
            "id": plain_id, "organization_id": HUB_ORG,
            "reference": "PYTEST-PLAIN", "title": "Direct case",
            "status": "assigned", "priority": "p3", "source": "phone",
            "created_at": "2026-06-12T00:00:00+00:00",
        })
    _run(seed())
    try:
        # Should not raise / not affect any issue.
        r = admin.post(f"{BASE_URL}/api/svc/cases/{plain_id}/transition",
                       json={"to": "en_route", "reason": "pytest"}, timeout=30)
        assert r.status_code == 200, r.text
    finally:
        async def drop():
            await _db().svc_cases.delete_many({"id": plain_id})
        _run(drop())


def test_bridge_wired_into_transition_engine():
    src = open("/app/backend/utils/svc_state.py", encoding="utf-8").read()
    assert "mirror_case_state_to_issue" in src, "reverse bridge must be hooked into transition()"
