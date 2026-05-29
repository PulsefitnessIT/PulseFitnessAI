"""Iter 220bi — Sicon ↔ GymAxis field-mapping completeness lock.

Pins down two things so future drift gets caught at PR time:

1. **Spec parity** — `/app/memory/SICON_INTEGRATION_SPEC.md` must have
   zero remaining blank ("—") cells in the *GymAxis Field* column of
   the §3 mapping tables, and must reference the new
   `sicon_sync_status` / `sicon_sync_error` lifecycle fields.

2. **Mapper coverage** — `map_sicon_case_to_gymaxis` and
   `map_sicon_appointment_to_gymaxis` must surface every field the
   spec promises to read back from Sicon. We assert on a
   representative payload so the JSON keys, not just docstrings,
   are tested.

3. **Tracking note timeline** — `_sync_tracking_notes` must carry
   the full Sicon tracking-note payload (GPS, visibility flags,
   appointment link, status) onto the GymAxis `timeline[]` entry
   so the UI can render it without a second fetch.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from utils.sicon_client import (
    map_sicon_case_to_gymaxis,
    map_sicon_appointment_to_gymaxis,
    map_sicon_tracking_note_to_gymaxis,
)


REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SPEC = REPO / "memory" / "SICON_INTEGRATION_SPEC.md"


# ── 1) Spec parity ────────────────────────────────────────────────


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _spec_section(name: str) -> str:
    """Return body of a `## §x` section by header substring."""
    body = _spec_text()
    pattern = rf"##\s+{re.escape(name)}[\s\S]+?(?=\n##\s|\n#\s|\Z)"
    m = re.search(pattern, body)
    assert m, f"Section not found in spec: {name}"
    return m.group(0)


# Tables we audit — anything left as "| — |" in the GymAxis column
# would mean a field is being dropped silently between Sicon and us.
@pytest.mark.parametrize("section", [
    "3.1 SERVICE CASE (Issue → Sicon Case)",
    "3.2 APPOINTMENTS (Engineer Visits)",
    "3.3 TIME BOOKINGS (Labour)",
    "3.4 TRACKING NOTES (Case Timeline)",
])
def test_no_blank_gymaxis_field_cells(section: str):
    body = _spec_section(section)
    hits: list[str] = []
    for ln, line in enumerate(body.splitlines(), start=1):
        # Match a table row whose first cell (GymAxis Field) is just "—" or empty.
        if re.match(r"^\|\s*—\s*\|", line) or re.match(r"^\|\s*\|", line):
            hits.append(f"L{ln}: {line.strip()[:120]}")
    assert not hits, (
        f"Section '{section}' still has blank GymAxis-field cells. "
        f"Populate each with the actual persisted path (e.g. `sicon_case_id`, "
        f"`sicon_appointments[].scheduled_start`). Found: {hits}"
    )


def test_spec_documents_sync_lifecycle_fields():
    """Sync-status lifecycle fields must be in the §3.1 table."""
    section = _spec_section("3.1 SERVICE CASE (Issue → Sicon Case)")
    for required in (
        "sicon_sync_status",
        "sicon_sync_error",
        "sicon_synced_at",
        "sicon_last_polled_at",
    ):
        assert required in section, (
            f"Sync-lifecycle field `{required}` missing from §3.1 spec table"
        )


def test_spec_ui_section_references_panel():
    body = _spec_text()
    assert "SiconServicePanel.js" in body, (
        "UI requirements section must reference the actual frontend panel "
        "so future engineers can trace the data flow."
    )
    for tid in ("sicon-sync-status-badge", "sicon-sync-error", "sicon-resync-btn"):
        assert tid in body, f"UI section must list the {tid} test-id"


# ── 2) Mapper coverage ────────────────────────────────────────────


CASE_FIELDS_PERSISTED = {
    "sicon_case_id",
    "sicon_case_number",
    "sicon_status",
    "sicon_status_id",
    "sicon_sub_status_id",
    "sicon_priority",
    "sicon_priority_id",
    "sicon_assigned_to",
    "sicon_assigned_to_id",
    "sicon_internal_team",
    "sicon_internal_team_id",
    "sicon_external_team",
    "sicon_external_team_id",
    "sicon_contact_name",
    "sicon_contact_email",
    "sicon_contact_phone",
    "sicon_customer_reference",
    "sicon_sl_customer_account_id",
    "sicon_case_type_id",
    "sicon_case_type_name",
    "sicon_contract_id",
    "sicon_contract_number",
    "sicon_contract_line_id",
    "sicon_contract_line_number",
    "sicon_job_id",
    "sicon_crm_person_id",
    "sicon_crm_company_id",
    "sicon_sub_location_id",
    "sicon_sub_location_description",
    "sicon_sub_location_comment",
    "sicon_call_date",
    "sicon_equipment_ids",
    "sicon_description",
    "sicon_summary",
}


def test_case_mapper_returns_all_persisted_fields():
    sample = {
        "entity": {
            "SiSMCaseId": 4242,
            "CaseNumber": "C-001",
            "SiSMDocumentStatusID": 3,
            "SiSMDocumentStatusName": "In Progress",
            "SiSMDocumentSubStatusID": 7,
            "PriorityID": 2,
            "PriorityName": "High",
            "AssignedToSageUserID": 88,
            "AssignedToSageUser": "Alice Smith",
            "InternalTeamID": 1,
            "InternalTeam": "Engineers North",
            "ExternalTeamID": 9,
            "ExternalTeam": "ACME Subs",
            "ContactName": "Joe Manager",
            "ContactEmail": "joe@example.com",
            "ContactPhoneNumber": "0700 0000",
            "CustomerReference": "CR-1",
            "SLCustomerAccountID": 999,
            "CaseTypeID": 4,
            "CaseTypeName": "Reactive",
            "SiconContractID": 11,
            "SiconContractNumber": "CT-100",
            "SiconContractLineID": 2,
            "SiconContractLineNumber": "L-1",
            "SiJcJobID": 33,
            "SiconCRMPersonID": 55,
            "SiconCRMCompanyID": 66,
            "Description": "broken treadmill",
            "Summary": "TM-500 — SN123",
            "CallDate": "2026-02-10T10:00:00Z",
            "SubLocation": {
                "SiconSubLocationID": 5,
                "Description": "Cardio Zone",
                "Comment": "ground floor",
            },
            "EquipmentIDs": [101, 102],
        }
    }
    out = map_sicon_case_to_gymaxis(sample)
    missing = CASE_FIELDS_PERSISTED - set(out.keys())
    assert not missing, f"Case mapper missing keys: {missing}"
    assert out["sicon_assigned_to"] == "Alice Smith"
    assert out["sicon_internal_team_id"] == 1
    assert out["sicon_sub_location_description"] == "Cardio Zone"


APPT_FIELDS_PERSISTED = {
    "sicon_appointment_id",
    "scheduled_start",
    "scheduled_end",
    "appointment_type",
    "work_done_description",
    "further_action",
    "arrival_signee",
    "departure_signee",
    "arrival_latitude",
    "arrival_longitude",
    "departure_latitude",
    "departure_longitude",
    "appointment_complete",
    "confirmed",
    "employee_ids",
    "subject",
}


def test_appointment_mapper_returns_all_persisted_fields():
    sample = {
        "SiconAppointmentID": 1010,
        "ScheduledStartDate": "2026-02-11T09:00:00Z",
        "ScheduledEndDate": "2026-02-11T11:00:00Z",
        "AppointmentType": "Work",
        "WorkDoneDescription": "Replaced belt",
        "FurtherAction": "Order new motor",
        "ArrivalSignee": "Site Mgr",
        "DepartureSignee": "Site Mgr",
        "ArrivalLatitude": 51.5,
        "ArrivalLongitude": -0.1,
        "DepartureLatitude": 51.51,
        "DepartureLongitude": -0.11,
        "AppointmentComplete": True,
        "Confirmed": True,
        "EmployeeIDs": [88, 89],
        "Subject": "TM-500 — SN123",
    }
    out = map_sicon_appointment_to_gymaxis(sample)
    missing = APPT_FIELDS_PERSISTED - set(out.keys())
    assert not missing, f"Appointment mapper missing keys: {missing}"
    assert out["departure_latitude"] == 51.51
    assert out["employee_ids"] == [88, 89]


NOTE_FIELDS_PERSISTED = {
    "sicon_note_id",
    "message",
    "timestamp",
    "by",
    "case_tracking_status_id",
    "status",
    "visible_to_engineer",
    "visible_to_customer",
    "sicon_appointment_id",
    "latitude",
    "longitude",
}


def test_tracking_note_mapper_returns_all_persisted_fields():
    sample = {
        "ID": 7,
        "TrackingNote": "On site, diagnosing fault",
        "Time": "2026-02-11T09:30:00Z",
        "User": "Alice Smith",
        "CaseTrackingStatusID": 4,
        "Status": "On Site",
        "VisibleToEngineer": True,
        "VisibleToCustomer": False,
        "SiconAppointmentID": 1010,
        "Latitude": 51.5,
        "Longitude": -0.1,
    }
    out = map_sicon_tracking_note_to_gymaxis(sample)
    missing = NOTE_FIELDS_PERSISTED - set(out.keys())
    assert not missing, f"Tracking-note mapper missing keys: {missing}"
    assert out["sicon_appointment_id"] == 1010


# ── 3) Timeline preservation in _sync_tracking_notes ──────────────


def test_sync_tracking_notes_preserves_rich_fields():
    """Inline-check the timeline_entries list-comprehension in
    `utils/sicon_sync.py::_sync_tracking_notes` includes every field
    the UI needs (GPS, visibility, appointment link, status)."""
    body = (REPO / "backend" / "utils" / "sicon_sync.py").read_text(encoding="utf-8")
    for required in (
        "case_tracking_status_id",
        "visible_to_engineer",
        "visible_to_customer",
        "sicon_appointment_id",
        "latitude",
        "longitude",
        "sicon_note_id",
    ):
        assert required in body, (
            f"_sync_tracking_notes must carry `{required}` onto timeline entries "
            "so the UI can render Sicon notes without a second fetch."
        )


# ── 4) Frontend panel surfaces sync state + retry ────────────────


def test_panel_renders_sync_status_and_retry():
    panel = (
        REPO / "frontend" / "src" / "pages" / "SiconServicePanel.js"
    ).read_text(encoding="utf-8")
    for token in (
        "sicon-sync-status-badge",
        "sicon-sync-error",
        "sicon-resync-btn",
        "Push to Sicon",
        "Retry sync",
        "sicon_contact_name",
        "sicon_assigned_to_id",
        "departure_latitude",
    ):
        assert token in panel, (
            f"SiconServicePanel must surface `{token}` so the spec's UI "
            f"requirements (§7) are met."
        )
