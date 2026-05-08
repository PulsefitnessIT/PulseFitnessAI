"""
Phase A-D Sicon field-mapping regression tests.
Covers the deeper field coverage added on 2026-04-21:
- Phase A: AnalysisFields 9-20, full SubLocation, CRM cross-links, Equipments[]
- Phase B: appointment completion + time booking payloads
- Phase C: engineer directory mapping
- Phase D: ContractLine + spare-slot mapping
"""

from utils.sicon_client import (
    map_gymaxis_to_sicon_case,
    map_sicon_case_to_gymaxis,
    map_sicon_resource_to_engineer,
    map_gymaxis_contract_to_sicon,
    map_gymaxis_contract_line_to_sicon,
    build_appointment_payload,
    build_appointment_completion_payload,
    build_time_booking_payload,
    build_tracking_note_payload,
)


# ── Phase A ─────────────────────────────────────────────────────────

def _issue_fixture() -> dict:
    return {
        "id": "iss-1234-uuid",
        "organization_id": "org-pulse",
        "severity": "high",
        "fault_type": "standard",
        "machine_type": "Treadmill",
        "serial_number": "T-987654",
        "issue_description": "Belt slipping",
        "fault_code": "BEL-01",
        "created_by_name": "Lee Somers",
        "reporter_email": "lee@pulsefitness.com",
        "ppm_schedule_id": "ppm-42",
        "source": "ask_gymaxis_orb",
        "reporter_role": "manager",
        "csat_rating": 4,
        "ai_triage_summary": "Belt tensioner assembly loose; replace",
        "ai_triage_parsed": {"summary": "Replace belt + tensioner", "severity": "high"},
        "sicon_sub_status_id": 17,
        "created_at": "2026-04-21T10:00:00Z",
    }


def _config_fixture() -> dict:
    return {
        "default_case_type_id": 2,
        "default_priority_id": 3,
        "default_assigned_user_id": 11,
        "default_internal_team_id": 5,
        "default_external_team_id": 9,
        "default_contract_id": 100,
        "default_contract_line_id": 200,
        "default_crm_person_id": 55,
        "default_crm_company_id": 66,
        "priority_mapping": {"low": 1, "medium": 2, "high": 3, "critical": 4, "safety_critical": 5},
        "equipment_id_mapping": {"T-987654": 7777},
        "location_address": {"name": "Main Gym", "line1": "1 Road", "city": "Newcastle", "postcode": "NE1 1AA"},
    }


def _equipment_fixture() -> dict:
    return {
        "serial_number": "T-987654",
        "make": "Matrix",
        "model_code": "T7XE",
        "install_date": "2024-03-15",
        "warranty_expiry": "2027-03-15",
        "sage_item_id": 8008,
        "display_name": "Treadmill #3",
    }


def _site_fixture() -> dict:
    return {
        "id": "site-abc",
        "name": "Pulse Newcastle West",
        "sicon_sub_location_id": 321,
        "sage_delivery_address_id": 987,
        "floor_or_zone": "Cardio Zone A",
    }


def test_phase_a_analysis_fields_9_to_20():
    payload = map_gymaxis_to_sicon_case(
        _issue_fixture(), _config_fixture(), org_name="Pulse",
        equipment=_equipment_fixture(),
    )
    assert payload["AnalysisField9"]  == "BEL-01"
    assert payload["AnalysisField10"] == "Treadmill"
    assert payload["AnalysisField11"] == "Matrix"
    assert payload["AnalysisField12"] == "T7XE"
    assert payload["AnalysisField13"] == "2024-03-15"
    assert payload["AnalysisField14"] == "2027-03-15"
    assert payload["AnalysisField15"] == "iss-1234-uuid"
    assert payload["AnalysisField16"] == "ppm-42"
    assert payload["AnalysisField17"].startswith("Belt tensioner")
    assert payload["AnalysisField18"] == "ask_gymaxis_orb"
    assert payload["AnalysisField19"] == "manager"
    assert payload["AnalysisField20"] == "4"


def test_phase_a_full_sub_location_from_site():
    payload = map_gymaxis_to_sicon_case(
        _issue_fixture(), _config_fixture(), org_name="Pulse",
        site=_site_fixture(),
    )
    assert payload["SubLocation"]["SiconSubLocationID"] == 321
    assert payload["SubLocation"]["CustDeliveryAddressID"] == 987
    assert "Newcastle West" in payload["SubLocation"]["Description"]
    assert payload["SubLocation"]["Comment"] == "Cardio Zone A"


def test_phase_a_crm_cross_links_fallback_to_config():
    payload = map_gymaxis_to_sicon_case(
        _issue_fixture(), _config_fixture(), org_name="Pulse",
        crm_links={},  # empty → use config defaults
    )
    assert payload["SiconCRMPersonID"] == 55
    assert payload["SiconCRMCompanyID"] == 66


def test_phase_a_crm_cross_links_from_org():
    payload = map_gymaxis_to_sicon_case(
        _issue_fixture(), _config_fixture(), org_name="Pulse",
        crm_links={"crm_person_id": 999, "crm_company_id": 888},
    )
    assert payload["SiconCRMPersonID"] == 999
    assert payload["SiconCRMCompanyID"] == 888


def test_phase_a_sub_status_passthrough():
    payload = map_gymaxis_to_sicon_case(_issue_fixture(), _config_fixture(), org_name="Pulse")
    assert payload["SiSMDocumentSubStatusID"] == 17


def test_phase_a_equipments_full_objects():
    payload = map_gymaxis_to_sicon_case(
        _issue_fixture(), _config_fixture(), org_name="Pulse",
        equipment=_equipment_fixture(),
    )
    assert payload["Equipments"][0]["SiconEquipmentID"] == 7777
    assert payload["Equipments"][0]["ItemID"] == 8008
    assert payload["Equipments"][0]["Name"] == "Treadmill"
    assert payload["EquipmentIDs"] == [7777]


def test_phase_a_inbound_mapper_reads_sub_status_and_sub_location():
    sicon_case = {
        "entity": {
            "SiSMCaseId": 500, "CaseNumber": "CASE-500",
            "SiSMDocumentStatusID": 2, "SiSMDocumentStatusName": "In Progress",
            "SiSMDocumentSubStatusID": 17,
            "SubLocation": {"SiconSubLocationID": 42, "Description": "Plant Room",
                             "Comment": "Needs ladder"},
            "Equipments": [{"SiconEquipmentID": 9}, {"SiconEquipmentID": 10}],
        }
    }
    mapped = map_sicon_case_to_gymaxis(sicon_case)
    assert mapped["sicon_sub_status_id"] == 17
    assert mapped["sicon_sub_location_id"] == 42
    assert mapped["sicon_sub_location_description"] == "Plant Room"
    assert mapped["sicon_equipment_ids"] == [9, 10]


# ── Phase B ─────────────────────────────────────────────────────────

def test_phase_b_appointment_travel_links_to_parent_work():
    payload = build_appointment_payload(
        {"sicon_case_id": 42, "machine_type": "Treadmill", "serial_number": "T-1"},
        "2026-04-22T09:00:00Z", "2026-04-22T10:00:00Z",
        employee_ids=[5],
        appointment_type="Travel", parent_work_appointment_id=99,
        charge_rate_id=3, label_id=2,
    )
    assert payload["AppointmentType"] == "Travel"
    assert payload["ParentWorkAppointmentID"] == 99
    assert payload["ChargeRateID"] == 3
    assert payload["LabelID"] == 2
    assert payload["EmployeeIDs"] == [5]


def test_phase_b_appointment_completion_packs_proof_of_work():
    payload = build_appointment_completion_payload(
        work_done="Replaced belt; calibrated speed",
        further_action="Needs to return for new deck",
        arrival_signee="Lee Somers", departure_signee="Emma King",
        arrival_lat=54.9, arrival_lon=-1.6,
        departure_lat=54.9, departure_lon=-1.6,
        work_done_acknowledged=True,
    )
    assert payload["AppointmentComplete"] is True
    assert payload["WorkDoneAcknowledged"] is True
    assert payload["ArrivalSignee"] == "Lee Somers"
    assert payload["ArrivalLatitude"] == 54.9
    assert payload["DepartureLongitude"] == -1.6
    assert "Replaced belt" in payload["WorkDoneDescription"]


def test_phase_b_time_booking_payload_shape():
    payload = build_time_booking_payload(
        employee_ids=[7, 8], start_date="2026-04-22T09:00:00Z",
        end_date="2026-04-22T10:30:00Z", actual_hours=1.5, charge_rate=45,
    )
    assert payload == {
        "EmployeeIDs": [7, 8],
        "StartDate": "2026-04-22T09:00:00Z",
        "EndDate": "2026-04-22T10:30:00Z",
        "ActualHours": 1.5,
        "ChargeRate": 45,
    }


def test_phase_b_tracking_note_with_appointment_and_gps():
    payload = build_tracking_note_payload(
        "Arrived on site, belt cover removed", created_by="eng-jake",
        status_id=12, sicon_appointment_id=88,
        latitude=54.97, longitude=-1.61,
    )
    assert payload["SiconAppointmentID"] == 88
    assert payload["Latitude"] == 54.97
    assert payload["Longitude"] == -1.61
    assert payload["CaseTrackingStatusID"] == 12


# ── Phase C ─────────────────────────────────────────────────────────

def test_phase_c_engineer_mapping_flags_and_names():
    entity = {
        "SIJCEMPID": 42, "FullName": "Jake Wilson", "FirstName": "Jake", "Surname": "Wilson",
        "DiaryColour": "#0055FF", "EmployeeNumber": 501, "PostCodeArea": "NE1",
        "Team": "North East", "SiconTeamID": 3,
        "MobileNo": "07123 456 789", "Email": "jake@pulse.com",
        "IsTeamLeader": True, "IsLeaver": False, "IsShopFloorUser": True,
    }
    mapped = map_sicon_resource_to_engineer(entity)
    assert mapped["sicon_employee_id"] == 42
    assert mapped["full_name"] == "Jake Wilson"
    assert mapped["team_name"] == "North East"
    assert mapped["team_id"] == 3
    assert mapped["post_code_area"] == "NE1"
    assert mapped["is_team_leader"] is True
    assert mapped["is_leaver"] is False
    assert mapped["diary_colour"] == "#0055FF"


# ── Phase D ─────────────────────────────────────────────────────────

def test_phase_d_contract_header_uses_spare_text_slots():
    contract = {
        "sicon_contract_id": 0,
        "contract_number": "CONT-2026-001",
        "title": "Pulse Newcastle 2026 Service Cover",
        "description": "Annual all-sites cover",
        "customer_order_number": "PO-8899",
        "sage_customer_number": "PULSENC01",
        "spare_text_map": ["tender_reference", "renewal_flag", "territory"],
        "tender_reference": "TEN-2026-Q1-007",
        "renewal_flag": "auto",
        "territory": "North East",
    }
    payload = map_gymaxis_contract_to_sicon(contract)
    assert payload["ContractNumber"] == "CONT-2026-001"
    assert payload["CustomerOrderNumber"] == "PO-8899"
    assert payload["CustomerNumber"] == "PULSENC01"
    assert payload["SpareText1"] == "TEN-2026-Q1-007"
    assert payload["SpareText2"] == "auto"
    assert payload["SpareText3"] == "North East"


def test_phase_d_contract_line_analysis_codes_encode_sla():
    line = {
        "item_code": "SVC-TREAD-12",
        "description": "Treadmill quarterly PPM",
        "quantity": 4, "unit_price": 180,
        "start_date": "2026-04-01", "end_date": "2027-03-31",
        "invoice_frequency_value": 3, "invoice_frequency_interval": "months",
        "is_rolling": True, "ppm_frequency_override": "quarterly",
        "tier": "Gold",
        "safety_critical": False,
        "asset_id": "eq-42",
        "site_id": "site-7",
        "tender_reference": "TEN-2026-Q1-007",
        "renewal_notice_days": 60,
        "sla": {"response_hours": 4, "resolution_hours": 24, "oos_credit_terms": "pro-rata"},
        "visit_frequency": "Quarterly",
        "pl_supplier_id": 321, "supplier_unit_price": 120,
    }
    payload = map_gymaxis_contract_line_to_sicon(line, sicon_contract_id=555)
    assert payload["SiconContractID"] == "555"
    assert payload["ItemCode"] == "SVC-TREAD-12"
    assert payload["CLAnalysisCode1"] == "Gold"
    assert payload["CLAnalysisCode2"] == "4"
    assert payload["CLAnalysisCode3"] == "24"
    assert payload["CLAnalysisCode4"] == "pro-rata"
    assert payload["CLAnalysisCode5"] == "NO"
    assert payload["CLAnalysisCode6"] == "eq-42"
    assert payload["CLAnalysisCode7"] == "site-7"
    assert payload["CLAnalysisCode8"] == "quarterly"
    assert payload["CLAnalysisCode9"] == "TEN-2026-Q1-007"
    assert payload["CLAnalysisCode10"] == "60"
    assert payload["VisitFrequency"] == "Quarterly"
    assert payload["IsRolling"] is True
    assert payload["InvoiceFrequencyInterval"] == "months"
    assert payload["SupplierUnitPrice"] == 120


def test_phase_d_contract_line_custom_analysis_code_override():
    line = {
        "item_code": "X",
        "sla": {},
        "analysis_codes": {"CLAnalysisCode50": "custom-value", "AnalysisCode1": "extra"},
    }
    payload = map_gymaxis_contract_line_to_sicon(line, sicon_contract_id=1)
    assert payload["CLAnalysisCode50"] == "custom-value"
    assert payload["AnalysisCode1"] == "extra"
