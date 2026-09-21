"""Sicon inbound mappers must read the ids Sicon actually returns, regardless
of casing (camelCase from the live Service WebAPI, or legacy PascalCase).

Confirmed at the 2026-06 Sicon meeting: caseId, appointmentId, trackingStatusId
etc. are all exposed — this guards that we successfully read them back."""
from utils.sicon_client import (
    map_sicon_case_to_gymaxis,
    map_sicon_appointment_to_gymaxis,
    map_sicon_tracking_note_to_gymaxis,
    map_sicon_time_booking_to_gymaxis,
)


def test_case_camelcase_ids():
    out = map_sicon_case_to_gymaxis({
        "siSMCaseId": 4321, "caseNumber": "CASE-4321",
        "statusId": 7, "status": "In Progress",
        "appointmentId": 99, "siSMCaseTrackingNoteId": 55,
        "caseType": {"siSMCaseTypeId": 2, "name": "Reactive"},
        "priority": {"siSMPriorityId": 3, "name": "High"},
        "subLocation": {"siconSubLocationDbKey": 12, "description": "Gym floor"},
    })
    assert out["sicon_case_id"] == 4321
    assert out["sicon_case_number"] == "CASE-4321"
    assert out["sicon_tracking_status_id"] == 7
    assert out["sicon_tracking_status"] == "In Progress"
    assert out["sicon_appointment_id"] == 99
    assert out["sicon_latest_note_id"] == 55
    assert out["sicon_case_type_id"] == 2
    assert out["sicon_priority_id"] == 3
    assert out["sicon_sub_location_id"] == 12


def test_case_pascalcase_still_works():
    out = map_sicon_case_to_gymaxis({
        "SiSMCaseId": 1, "CaseNumber": "C1",
        "CaseTypeID": 9, "PriorityID": 4,
        "SubLocation": {"SiconSubLocationID": 8},
    })
    assert out["sicon_case_id"] == 1
    assert out["sicon_case_type_id"] == 9
    assert out["sicon_priority_id"] == 4
    assert out["sicon_sub_location_id"] == 8


def test_appointment_camelcase():
    out = map_sicon_appointment_to_gymaxis({
        "siconAppointmentId": 700, "siSMCaseId": 4321,
        "scheduledStartDate": "2026-06-01T09:00:00Z",
        "appointmentComplete": True, "costingHours": 2.5, "isEstimate": False,
    })
    assert out["sicon_appointment_id"] == 700
    assert out["sicon_case_id"] == 4321
    assert out["appointment_complete"] is True
    assert out["costing_hours"] == 2.5


def test_tracking_note_camelcase_status_variants():
    out = map_sicon_tracking_note_to_gymaxis({
        "siSMCaseTrackingNoteId": 12, "note": "Parts ordered",
        "statusId": 5, "appointmentId": 700,
    })
    assert out["sicon_note_id"] == 12
    assert out["message"] == "Parts ordered"
    assert out["case_tracking_status_id"] == 5
    assert out["sicon_appointment_id"] == 700


def test_time_booking_camelcase():
    out = map_sicon_time_booking_to_gymaxis({
        "startDate": "2026-06-01T09:00:00Z", "endDate": "2026-06-01T11:00:00Z",
        "costingHours": 2.0, "chargingHours": 2.0, "isEstimate": True,
        "employeeIds": [10, 11],
    })
    assert out["costing_hours"] == 2.0
    assert out["charging_hours"] == 2.0
    assert out["is_estimate"] is True
    assert out["employee_ids"] == [10, 11]
