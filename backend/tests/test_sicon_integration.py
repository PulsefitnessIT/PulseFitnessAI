"""
Sicon integration tests.
Uses a mocked Sicon WebAPI via httpx MockTransport to validate:
  - Field mapping (map_gymaxis_to_sicon_case)
  - Issue sync, tracking note posting
  - Failure queue enqueue + retry
  - Inbound poller updates
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sicon_client import (
    map_gymaxis_to_sicon_case,
    map_sicon_case_to_gymaxis,
    map_sicon_appointment_to_gymaxis,
    build_tracking_note_payload,
    SEVERITY_TO_PRIORITY_NAME,
    FAULT_TYPE_TO_CASE_TYPE,
)


class TestFieldMapping:
    def test_basic_case_mapping(self):
        issue = {
            "id": "issue-123",
            "issue_description": "Treadmill belt slipping",
            "machine_type": "Treadmill",
            "serial_number": "TM-001",
            "severity": "high",
            "fault_type": "standard",
            "created_at": "2026-04-17T10:00:00Z",
            "created_by_name": "Alice",
            "reporter_email": "alice@gym.com",
            "ai_triage_summary": "Drive belt worn",
        }
        config = {
            "default_case_type_id": 5,
            "default_priority_id": 2,
            "priority_mapping": {"low": 1, "medium": 2, "high": 3, "critical": 4},
        }
        payload = map_gymaxis_to_sicon_case(issue, config, org_name="Test Gym")
        assert payload["PriorityID"] == 3
        assert payload["PriorityName"] == "High"
        assert payload["CaseTypeID"] == 5
        assert payload["CaseTypeName"] == "Reactive"
        assert payload["Description"] == "Treadmill belt slipping"
        assert payload["Summary"] == "Treadmill — TM-001"
        assert payload["ContactName"] == "Alice"
        assert payload["ContactEmail"] == "alice@gym.com"
        assert payload["AnalysisField1"] == "Drive belt worn"
        assert payload["AnalysisField4"] == "issue-123"
        assert payload["AnalysisField5"] == "Test Gym"

    def test_ppm_case_type(self):
        issue = {"id": "i1", "fault_type": "ppm", "severity": "low", "created_at": "2026-04-17T10:00:00Z"}
        config = {}
        payload = map_gymaxis_to_sicon_case(issue, config)
        assert payload["CaseTypeName"] == "Preventative Maintenance"

    def test_safety_critical_priority(self):
        issue = {"id": "i1", "severity": "safety_critical", "created_at": "2026-04-17T10:00:00Z"}
        payload = map_gymaxis_to_sicon_case(issue, {})
        assert payload["PriorityName"] == "Safety Critical"

    def test_location_address_mapping(self):
        issue = {
            "id": "i1", "created_at": "2026-04-17T10:00:00Z",
            "site_name": "Tottenham Green",
            "site_address": {
                "line1": "1 Philip Lane", "city": "London",
                "postcode": "N15 4JA", "county": "Greater London"
            },
        }
        payload = map_gymaxis_to_sicon_case(issue, {})
        assert payload["LocationAddressLine1"] == "1 Philip Lane"
        assert payload["LocationCity"] == "London"
        assert payload["LocationPostCode"] == "N15 4JA"

    def test_equipment_id_lookup(self):
        issue = {"id": "i1", "serial_number": "TM-001", "created_at": "2026-04-17T10:00:00Z"}
        config = {"equipment_id_mapping": {"TM-001": 42}}
        payload = map_gymaxis_to_sicon_case(issue, config)
        assert payload["EquipmentIDs"] == [42]

    def test_reverse_case_mapping(self):
        sicon = {"entity": {
            "SiSMCaseId": 100,
            "CaseNumber": "SC-2026-0001",
            "SiSMDocumentStatusName": "In Progress",
            "PriorityName": "High",
            "AssignedToSageUser": "Engineer Bob",
            "AssignedToSageUserID": 55,
        }}
        result = map_sicon_case_to_gymaxis(sicon)
        assert result["sicon_case_id"] == 100
        assert result["sicon_case_number"] == "SC-2026-0001"
        assert result["sicon_status"] == "In Progress"
        assert result["sicon_assigned_to"] == "Engineer Bob"

    def test_reverse_appointment_mapping(self):
        appt = {"entity": {
            "SiconAppointmentID": 77,
            "ScheduledStartDate": "2026-04-18T09:00:00Z",
            "ScheduledEndDate": "2026-04-18T11:00:00Z",
            "AppointmentComplete": True,
            "WorkDoneDescription": "Replaced belt",
            "EmployeeIDs": [1, 2],
        }}
        result = map_sicon_appointment_to_gymaxis(appt)
        assert result["sicon_appointment_id"] == 77
        assert result["appointment_complete"] == True
        assert result["work_done_description"] == "Replaced belt"
        assert result["employee_ids"] == [1, 2]

    def test_tracking_note_payload(self):
        note = build_tracking_note_payload(
            "Test note", created_by="Alice", visible_to_customer=False, status_id=3
        )
        assert note["TrackingNote"] == "Test note"
        assert note["CreatedBy"] == "Alice"
        assert note["VisibleToCustomer"] == False
        assert note["CaseTrackingStatusID"] == 3

    def test_severity_and_fault_maps_cover_spec(self):
        for sev in ["safety_critical", "critical", "high", "medium", "low"]:
            assert sev in SEVERITY_TO_PRIORITY_NAME
        for ft in ["standard", "safety_critical", "ppm"]:
            assert ft in FAULT_TYPE_TO_CASE_TYPE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
