"""
Sicon Service WebAPI v1 migration tests (Jan 2026).

Covers the mapping-correctness + persistence fix requested by the customer:
  1. V1 model builders (utils.sicon_service_models) produce the FULL Sicon
     camelCase payload — Case (57 keys), Appointment (25 keys), Equipment
     (43 keys), TrackingNote (13 keys).
  2. SiconClient.svc_* methods route to the correct /api/v1/SiconService/*
     URLs with Bearer auth + companyId query param.
  3. POST /api/sicon/create-appointment/{issue_id} persists the returned
     siconAppointmentId on the issue and switches to PUT (update) when the
     issue already carries one.
  4. utils.sicon_sync.sync_issue_to_sicon branches on config.service_webapi_v1
     — v1 calls svc_create_case; legacy calls create_case.

All Sicon HTTP calls are stubbed — no live network.
"""
from __future__ import annotations

import os
import sys
import uuid
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv

# Load JWT_SECRET/MONGO_URL/DB_NAME before importing backend modules —
# utils.sicon_client raises at import time if JWT_SECRET is missing.
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from utils import sicon_service_models as ssm  # noqa: E402
from utils.sicon_client import SiconClient  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────

def _issue():
    return {
        "id": "iss-abc-1234",
        "organization_id": "org-pulse",
        "severity": "high",
        "fault_type": "standard",
        "machine_type": "Treadmill",
        "serial_number": "SN-9001",
        "issue_description": "Belt slipping under load",
        "created_at": "2026-01-10T09:00:00Z",
        "updated_at": "2026-01-10T10:00:00Z",
        "created_by_name": "Alice Reporter",
        "reporter_email": "alice@pulsefitness.com",
        "reporter_phone": "+441234567890",
        "fault_code": "BLT-01",
        "customer_order_no": "PO-77",
        "workflow_state": "in_progress",
        "site_address": {"name": "PF Central", "line1": "1 Main St",
                         "line2": "", "line3": "", "line4": "",
                         "city": "London", "county": "Greater London",
                         "postcode": "W1A 1AA"},
        "sicon_case_id": 0,
        "ai_triage_parsed": {"summary": "Belt slip", "severity": "high",
                             "recommended_parts": ["belt", "roller"]},
    }


def _config():
    return {
        "enabled": True,
        "service_webapi_v1": True,
        "default_case_type_id": 12,
        "default_case_type_name": "Reactive",
        "default_priority_id": 3,
        "priority_mapping": {"high": 4},
        "default_internal_team_id": 8,
        "default_external_team_id": 9,
        "default_crm_person_id": 100,
        "default_crm_company_id": 200,
        "sub_status_mapping": {"in_progress": 55},
    }


def _appt():
    return {
        "scheduled_start": "2026-02-01T08:00:00Z",
        "scheduled_end": "2026-02-01T10:00:00Z",
        "appointment_type": "Work",
        "description": "Attend site, replace belt",
        "colour": "#ff0000",
        "work_briefing": "Bring spare belt",
        "confirmed": True,
        "arrival_latitude": 51.5, "arrival_longitude": -0.12,
        "departure_latitude": 51.5, "departure_longitude": -0.12,
    }


# ── 1. V1 MODEL BUILDERS ────────────────────────────────────────────

CASE_REQUIRED_KEYS = {
    "siSMCaseId", "caseNumber", "siSMDocumentStatusId", "siSMDocumentStatusName",
    "siSMDocumentSubStatusId", "summary", "description", "callDate", "contactName",
    "contactPhoneNumber", "contactEmail", "lastUpdatedDate", "isNonContract",
    "address", "customerOrderNo", "createdBy", "siconCRMPersonId", "siconCRMCompanyId",
    "caseType", "coverType", "sla", "faultCode", "skill", "priority",
    "lastTrackingStatus", "contract", "contractLine", "project", "caseAdmin",
    "internalTeamId", "internalTeam", "externalTeamId", "externalTeam",
    "customer", "customerContact", "subLocation", "equipmentIds",
} | {f"analysisField{i}" for i in range(1, 21)}

APPT_REQUIRED_KEYS = {
    "siconAppointmentId", "siSMCaseId", "appointmentType", "parentWorkAppointmentId",
    "subject", "description", "workBriefing", "employeeIds", "chargeRateId",
    "labelId", "colour", "confirmed", "scheduledStartDate", "scheduledEndDate",
    "appointmentComplete", "workDoneDescription", "workDoneAcknowledged",
    "furtherAction", "furtherActionAcknowledged", "arrivalSignee", "departureSignee",
    "arrivalLatitude", "arrivalLongitude", "departureLatitude", "departureLongitude",
}


def test_build_case_model_v1_has_full_camelcase_shape():
    model = ssm.build_case_model_v1(_issue(), _config(), org_name="Pulse Fitness")
    missing = CASE_REQUIRED_KEYS - set(model.keys())
    assert not missing, f"Case model missing keys: {missing}"
    # Nested address
    for k in ("postalName", "addressLine1", "addressLine2", "addressLine3",
              "addressLine4", "city", "county", "postCode", "sopDelAddress"):
        assert k in model["address"], f"address missing {k}"
    assert model["address"]["postCode"] == "W1A 1AA"
    # Nested caseType
    for k in ("siSMCaseTypeId", "name", "systemType",
              "isPreventativeMaintenanceType", "isEnabled", "isCustom",
              "defaultAppointmentLabel"):
        assert k in model["caseType"]
    assert model["caseType"]["siSMCaseTypeId"] == 12
    # Nested priority
    for k in ("siSMPriorityId", "name", "colour"):
        assert k in model["priority"]
    assert model["priority"]["siSMPriorityId"] == 4  # from mapping[high]
    assert model["priority"]["name"] == "High"
    # Sub-status via workflow_state map
    assert model["siSMDocumentSubStatusId"] == 55
    # CRM
    assert model["siconCRMPersonId"] == 100
    assert model["siconCRMCompanyId"] == 200
    # analysisField1..20 exist
    assert all(f"analysisField{i}" in model for i in range(1, 21))


def test_build_appointment_model_v1_has_25_keys_and_sourced_values():
    model = ssm.build_appointment_model_v1(
        _issue(), _appt(),
        sicon_appointment_id=0, sicon_case_id=1234, employee_ids=[7],
    )
    missing = APPT_REQUIRED_KEYS - set(model.keys())
    assert not missing, f"Appointment model missing: {missing}"
    assert len(APPT_REQUIRED_KEYS) == 25
    assert model["siSMCaseId"] == 1234
    assert model["description"] == "Attend site, replace belt"
    assert model["colour"] == "#ff0000"
    assert model["employeeIds"] == [7]
    assert model["confirmed"] is True
    assert model["scheduledStartDate"] == "2026-02-01T08:00:00Z"


def test_build_equipment_model_v1_has_analysis_codes_1_to_20():
    eq = {"sicon_equipment_id": 42, "serial_number": "SN-1", "make": "Life",
          "model_code": "T-100", "display_name": "Treadmill A"}
    for i in range(1, 21):
        eq[f"analysis_code_{i}"] = f"V{i}"
    model = ssm.build_equipment_model_v1(eq)
    assert model["siconEquipmentId"] == 42
    assert model["serialNumber"] == "SN-1"
    for i in range(1, 21):
        assert model[f"analysisCode{i}"] == f"V{i}"


def test_build_tracking_note_model_v1_has_required_shape():
    m = ssm.build_tracking_note_model_v1(
        note="Engineer en route", status_id=5, appointment_id=99,
        visible_to_engineer=True, visible_to_customer=False,
        latitude=51.5, longitude=-0.12,
    )
    for k in ("siSMCaseTrackingNoteId", "note", "statusId", "appointmentId",
              "visibleToEngineer", "visibleToCustomer", "latitude", "longitude"):
        assert k in m, f"note model missing {k}"
    assert m["appointmentId"] == 99
    assert m["statusId"] == 5
    assert m["visibleToEngineer"] is True
    assert m["latitude"] == 51.5


# ── 2. V1 CLIENT ROUTING ────────────────────────────────────────────

class _Recorder:
    """Replacement for httpx.AsyncClient that records the last request."""
    def __init__(self, *a, **kw): self.last = None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    async def request(self, method, url, params=None, json=None, headers=None, **kw):
        self.last = {"method": method, "url": url, "params": params,
                     "json": json, "headers": headers or {}}
        class R:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = ""
            def json(self): return {"entity": {"siSMCaseId": 999,
                                                "siconAppointmentId": 55501}}
        return R()


def _make_client():
    # allow_writes=True so the write-guard permits POST/PUT to reach the mock;
    # the guard's disabled-by-default behaviour is covered in test_sicon_readside.py.
    c = SiconClient("https://sicon.example.com", "u", "p", company_id=77, allow_writes=True)
    c._bearer = "TEST_BEARER"  # skip real auth
    return c


def _record_request(client, coro):
    rec = _Recorder()
    # patch the AsyncClient used inside _svc_request
    with patch("utils.sicon_client.httpx.AsyncClient", return_value=rec):
        asyncio.get_event_loop().run_until_complete(coro)
    return rec.last


@pytest.fixture(autouse=True)
def _fresh_loop():
    # ensure a usable loop per test
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


def test_svc_create_case_routes_and_auth():
    client = _make_client()
    last = _record_request(client, client.svc_create_case({"x": 1}))
    assert last["method"] == "POST"
    assert last["url"] == "https://sicon.example.com/api/v1/SiconService/Case"
    assert last["params"].get("companyId") == 77
    assert last["headers"].get("Authorization") == "Bearer TEST_BEARER"
    assert last["json"] == {"x": 1}


def test_svc_update_case_uses_put_with_id():
    client = _make_client()
    last = _record_request(client, client.svc_update_case(5, {"a": 2}))
    assert last["method"] == "PUT"
    assert last["url"].endswith("/api/v1/SiconService/Case/5")


def test_svc_create_and_update_appointment_urls():
    client = _make_client()
    last_c = _record_request(client, client.svc_create_appointment({"a": 1}))
    assert last_c["method"] == "POST"
    assert last_c["url"].endswith("/api/v1/SiconService/Appointment")

    last_u = _record_request(client, client.svc_update_appointment(9, {"a": 1}))
    assert last_u["method"] == "PUT"
    assert last_u["url"].endswith("/api/v1/SiconService/Appointment/9")


def test_svc_appointment_time_booking_url():
    client = _make_client()
    last = _record_request(client, client.svc_appointment_time_booking(9, {"h": 1}))
    assert last["method"] == "POST"
    assert last["url"].endswith("/api/v1/SiconService/Appointment/9/TimeBooking")


def test_svc_tracking_note_url_scoped_to_case():
    client = _make_client()
    last = _record_request(client, client.svc_create_tracking_note(5, {"note": "x"}))
    assert last["method"] == "POST"
    assert last["url"].endswith("/api/v1/SiconService/Case/5/TrackingNote")


def test_svc_create_equipment_url():
    client = _make_client()
    last = _record_request(client, client.svc_create_equipment({"e": 1}))
    assert last["method"] == "POST"
    assert last["url"].endswith("/api/v1/SiconService/Equipment")


# ── 3. APPOINTMENT ID PERSISTENCE ──────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_create_appointment_persists_sicon_appointment_id():
    """POST /api/sicon/create-appointment/{issue_id} must persist
    issue.sicon_appointment_id when the org has service_webapi_v1=true
    and no existing appointment id."""
    from utils.database import db
    from routes.sicon import create_appointment

    org_id = f"org-test-{uuid.uuid4().hex[:8]}"
    issue_id = f"iss-{uuid.uuid4().hex[:8]}"
    user = {"id": "u1", "organization_id": org_id, "role": "owner"}

    async def setup_and_call():
        await db.issues.insert_one({
            "id": issue_id, "organization_id": org_id,
            "sicon_case_id": 1234, "machine_type": "T", "serial_number": "S",
        })
        await db.organizations.insert_one({"id": org_id, "name": "Test"})
        await db.sicon_config.insert_one({
            "organization_id": org_id,
            "enabled": True, "service_webapi_v1": True,
            "base_url": "https://sicon.example.com", "company_id": 1,
            "username_enc": "", "password_enc": "",
        })
        # fake client
        fake = AsyncMock()
        fake.svc_create_appointment = AsyncMock(return_value={
            "entity": {"siconAppointmentId": 55501}
        })
        fake.svc_update_appointment = AsyncMock(return_value={
            "entity": {"siconAppointmentId": 55501}
        })
        with patch("routes.sicon.get_sicon_client", AsyncMock(return_value=fake)):
            res = await create_appointment(issue_id, {
                "scheduled_start": "2026-02-01T08:00:00Z",
                "scheduled_end": "2026-02-01T10:00:00Z",
                "employee_ids": [7],
            }, user=user)
            # First call: create path
            assert fake.svc_create_appointment.await_count == 1
            assert fake.svc_update_appointment.await_count == 0

        doc = await db.issues.find_one({"id": issue_id})
        assert doc["sicon_appointment_id"] == 55501
        assert doc.get("sicon_appointment_synced_at")
        assert res["sicon_appointment_id"] == 55501

        # Second call: since id now exists, must call UPDATE not CREATE
        fake2 = AsyncMock()
        fake2.svc_create_appointment = AsyncMock(return_value={"entity": {}})
        fake2.svc_update_appointment = AsyncMock(return_value={
            "entity": {"siconAppointmentId": 55501}})
        with patch("routes.sicon.get_sicon_client", AsyncMock(return_value=fake2)):
            await create_appointment(issue_id, {
                "scheduled_start": "2026-02-02T08:00:00Z",
                "scheduled_end": "2026-02-02T10:00:00Z",
                "employee_ids": [7],
            }, user=user)
            assert fake2.svc_update_appointment.await_count == 1
            assert fake2.svc_create_appointment.await_count == 0

        # cleanup
        await db.issues.delete_one({"id": issue_id})
        await db.organizations.delete_one({"id": org_id})
        await db.sicon_config.delete_one({"organization_id": org_id})

    _run(setup_and_call())


# ── 4. CASE SYNC V1 SWITCH ─────────────────────────────────────────

def test_sync_issue_to_sicon_v1_branch_calls_svc_create_case():
    from utils.database import db
    from utils.sicon_sync import sync_issue_to_sicon

    org_id = f"org-v1-{uuid.uuid4().hex[:8]}"
    issue_id = f"iss-v1-{uuid.uuid4().hex[:8]}"

    async def run():
        await db.issues.insert_one({
            "id": issue_id, "organization_id": org_id,
            "machine_type": "T", "serial_number": "S",
            "severity": "high", "fault_type": "standard",
            "issue_description": "test", "created_at": "2026-01-01T00:00:00Z",
        })
        await db.organizations.insert_one({"id": org_id, "name": "Org"})
        await db.sicon_config.insert_one({
            "organization_id": org_id, "enabled": True, "auto_sync_faults": True,
            "service_webapi_v1": True,
            "base_url": "https://s", "company_id": 1,
            "username_enc": "", "password_enc": "",
        })
        fake = AsyncMock()
        fake.svc_create_case = AsyncMock(return_value={
            "entity": {"siSMCaseId": 4242, "caseNumber": "SC-4242"}})
        fake.create_case = AsyncMock(return_value={"entity": {}})
        with patch("utils.sicon_sync.get_sicon_client",
                   AsyncMock(return_value=fake)):
            sicon_id = await sync_issue_to_sicon(issue_id)
        assert fake.svc_create_case.await_count == 1
        assert fake.create_case.await_count == 0
        assert sicon_id == 4242
        doc = await db.issues.find_one({"id": issue_id})
        assert doc["sicon_case_id"] == 4242
        assert doc["sicon_case_number"] == "SC-4242"
        # cleanup
        await db.issues.delete_one({"id": issue_id})
        await db.organizations.delete_one({"id": org_id})
        await db.sicon_config.delete_one({"organization_id": org_id})

    _run(run())


def test_sync_issue_to_sicon_legacy_branch_calls_create_case():
    from utils.database import db
    from utils.sicon_sync import sync_issue_to_sicon

    org_id = f"org-lg-{uuid.uuid4().hex[:8]}"
    issue_id = f"iss-lg-{uuid.uuid4().hex[:8]}"

    async def run():
        await db.issues.insert_one({
            "id": issue_id, "organization_id": org_id,
            "machine_type": "T", "serial_number": "S",
            "severity": "high", "fault_type": "standard",
            "issue_description": "test", "created_at": "2026-01-01T00:00:00Z",
        })
        await db.organizations.insert_one({"id": org_id, "name": "Org"})
        await db.sicon_config.insert_one({
            "organization_id": org_id, "enabled": True, "auto_sync_faults": True,
            "service_webapi_v1": False,  # legacy branch
            "base_url": "https://s", "company_id": 1,
            "username_enc": "", "password_enc": "",
        })
        fake = AsyncMock()
        fake.create_case = AsyncMock(return_value={
            "entity": {"SiSMCaseId": 8888, "CaseNumber": "SC-8888"}})
        fake.svc_create_case = AsyncMock(return_value={"entity": {}})
        with patch("utils.sicon_sync.get_sicon_client",
                   AsyncMock(return_value=fake)):
            sicon_id = await sync_issue_to_sicon(issue_id)
        assert fake.create_case.await_count == 1
        assert fake.svc_create_case.await_count == 0
        assert sicon_id == 8888
        await db.issues.delete_one({"id": issue_id})
        await db.organizations.delete_one({"id": org_id})
        await db.sicon_config.delete_one({"organization_id": org_id})

    _run(run())
