"""Jun 2026 — Sicon engineer allocation via appointments (Sicon Q&A follow-up).

- Engineers come from Appointment.EmployeeIDs (SIJCEMPID), never
  case.AssignedToSageUserID (that's the case admin).
- Sicon wins: inbound changes re-assign + notify; outbound PUT is skipped
  (outbox row → 'conflict', case flagged) when Sicon changed since last read.
"""
import asyncio
import os
import uuid

import pytest

HUB_ORG = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"
CASE_ID = f"pytest-sicon-alloc-{uuid.uuid4().hex[:6]}"
SICON_CASE = 995551


def _db():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


ENG_A = f"pytest-eng-a-{uuid.uuid4().hex[:4]}"
ENG_B = f"pytest-eng-b-{uuid.uuid4().hex[:4]}"


@pytest.fixture(scope="module", autouse=True)
def seed():
    async def setup():
        import utils.database as udb
        udb.db = _db()
        db = _db()
        await db.svc_engineers.insert_many([
            {"id": ENG_A, "organization_id": HUB_ORG, "full_name": "Pytest Alpha", "sicon_employee_id": "61001"},
            {"id": ENG_B, "organization_id": HUB_ORG, "full_name": "Pytest Bravo", "email": "bravo.pytest@example.com"},
        ])
        await db.sicon_engineers.insert_one({"id": f"{HUB_ORG}:61002", "organization_id": HUB_ORG,
                                             "sicon_employee_id": 61002, "email": "bravo.pytest@example.com"})
        await db.svc_cases.insert_one({"id": CASE_ID, "organization_id": HUB_ORG, "reference": CASE_ID,
                                       "status": "new", "sicon_case_id": SICON_CASE, "title": "Pytest alloc"})

    async def teardown():
        db = _db()
        await db.svc_engineers.delete_many({"id": {"$in": [ENG_A, ENG_B]}})
        await db.sicon_engineers.delete_many({"id": f"{HUB_ORG}:61002"})
        await db.svc_cases.delete_many({"id": CASE_ID})
        await db.svc_case_events.delete_many({"case_id": CASE_ID})
        await db.svc_notifications.delete_many({"source_id": CASE_ID})
        await db.svc_sicon_outbox.delete_many({"payload.CaseID": CASE_ID})
    run(setup())
    yield
    run(teardown())


def _appt(emp_ids, appt_id=70001, complete=False):
    return {"SiconAppointmentID": appt_id, "SiSMCaseID": SICON_CASE, "ScheduledStartDate": "2026-07-01T09:00:00",
            "EmployeeIDs": emp_ids, "AppointmentComplete": complete}


def test_inbound_appointment_sets_engineer_and_admin_is_ignored():
    from utils.sicon_appointments import merge_sicon_appointment
    case = run(merge_sicon_appointment(HUB_ORG, _appt([61001])))
    assert case["assigned_engineer_id"] == ENG_A
    assert case["status"] == "assigned"
    assert case["sicon_current_appointment_id"] == 70001
    assert case["sicon_employee_ids"] == ["61001"]


def test_sicon_change_reassigns_and_notifies_via_directory_email():
    from utils.sicon_appointments import merge_sicon_appointment
    case = run(merge_sicon_appointment(HUB_ORG, _appt([61002])))
    assert case["assigned_engineer_id"] == ENG_B, "email fallback via sicon_engineers"

    async def check():
        db = _db()
        eng = await db.svc_engineers.find_one({"id": ENG_B})
        assert eng["sicon_employee_id"] == "61002", "back-filled"
        ev = await db.svc_case_events.find_one({"case_id": CASE_ID, "extra.kind": "sicon_engineer_change",
                                                "extra.to": [ENG_B]})
        assert ev
        users = {n["user_id"] async for n in db.svc_notifications.find({"source_id": CASE_ID})}
        assert {ENG_A, ENG_B} <= users
    run(check())


def test_outbound_allocation_enqueues_put_with_expected_ids():
    from utils.sicon_appointments import push_engineer_allocation

    async def go():
        case = await _db().svc_cases.find_one({"id": CASE_ID}, {"_id": 0})
        res = await push_engineer_allocation(case, [ENG_A])
        row = await _db().svc_sicon_outbox.find_one({"payload.CaseID": CASE_ID, "kind": "appointment_engineers"})
        return res, row
    res, row = run(go())
    assert res["queued"] is True
    assert row["payload"]["EmployeeIDs"] == [61001]
    assert row["payload"]["ExpectedEmployeeIDs"] == ["61002"]
    assert row["endpoint"] == "/api/Service/Appointments/70001"


class _FakeClient:
    def __init__(self, current):
        self.current, self.put = current, None

    async def get_appointment(self, appt_id):
        return {"entity": {"SiconAppointmentID": appt_id, "EmployeeIDs": self.current}}

    async def update_appointment(self, appt_id, body):
        self.put = body
        return {"ok": True}


def test_worker_sends_only_when_sicon_unchanged():
    from utils.sicon_appointments import SiconAllocationConflict, send_engineer_allocation
    payload = {"AppointmentID": 70001, "EmployeeIDs": [61001], "ExpectedEmployeeIDs": ["61002"], "CaseID": CASE_ID}
    ok = _FakeClient([61002])
    run(send_engineer_allocation(ok, payload))
    assert ok.put == {"EmployeeIDs": [61001]}, "only engineers change"
    changed = _FakeClient([69999])
    with pytest.raises(SiconAllocationConflict):
        run(send_engineer_allocation(changed, payload))
    assert changed.put is None, "Sicon wins — no overwrite"


def test_non_sicon_case_is_silent():
    from utils.sicon_appointments import push_engineer_allocation
    res = run(push_engineer_allocation({"id": "x", "organization_id": HUB_ORG}, [ENG_A]))
    assert res == {"queued": False, "reason": "Case not yet in Sicon"}
