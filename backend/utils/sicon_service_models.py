"""
Sicon Service WebAPI v1 payload builders (camelCase, FULL models).

These mirror the request bodies in the customer's Bruno collection exactly —
POST/PUT to /api/v1/SiconService/{Case,Appointment,Equipment} and
/Case/{id}/TrackingNote — so every field Sicon expects is present and named
correctly. Field *sources* are shared with the legacy PascalCase mapper in
utils.sicon_client so both stay in step.

All builders are pure functions (no I/O) → unit-testable in isolation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.sicon_client import (
    SEVERITY_TO_PRIORITY_NAME,
    FAULT_TYPE_TO_CASE_TYPE,
    _extract_triage_fields,
    _build_contact_fields,
    _build_analysis_fields,
    _build_extended_analysis_fields,
)


def _iso(v) -> Optional[str]:
    if not v:
        return None
    return str(v)


def _analysis_camel(issue: Dict, triage_summary: str, ai_severity: str,
                    ai_parts: str, org_name: str, equipment: Optional[Dict]) -> Dict:
    """analysisField1..20 in Sicon camelCase, sourced from the same builders
    the legacy mapper uses (so the two never diverge)."""
    core = _build_analysis_fields(issue, triage_summary, ai_severity, ai_parts, org_name)
    ext = _build_extended_analysis_fields(issue, equipment)
    out: Dict = {}
    for i in range(1, 21):
        out[f"analysisField{i}"] = core.get(f"AnalysisField{i}", ext.get(f"AnalysisField{i}", "")) or ""
    return out


def build_case_model_v1(issue: Dict, config: Dict, org_name: str = "",
                        equipment: Optional[Dict] = None, site: Optional[Dict] = None,
                        crm_links: Optional[Dict] = None) -> Dict:
    """Full Sicon CaseModel (camelCase) — matches Bruno Cases/Case/PostOne.bru."""
    severity = issue.get("severity", "medium")
    priority_id = (config.get("priority_mapping") or {}).get(severity) or config.get("default_priority_id", 0)
    priority_name = SEVERITY_TO_PRIORITY_NAME.get(severity, "Medium")

    fault_type = issue.get("fault_type", "standard")
    case_type_id = config.get("default_case_type_id", 0)
    case_type_name = config.get("default_case_type_name") or FAULT_TYPE_TO_CASE_TYPE.get(fault_type, "Reactive")
    is_ppm = fault_type == "ppm" or bool(issue.get("ppm_schedule_id"))

    triage_summary, ai_severity, ai_parts = _extract_triage_fields(issue, severity)
    contact = _build_contact_fields(issue)
    crm = crm_links or {}

    # Sub-status resolution (explicit wins, else per-org workflow_state map)
    sub_status_id = issue.get("sicon_sub_status_id") or 0
    if not sub_status_id:
        ws = (issue.get("workflow_state") or "").lower()
        sub_status_id = (config.get("sub_status_mapping") or {}).get(ws, 0) or 0

    # Address (nested object, per v1 contract)
    addr_src = issue.get("site_address") or (config.get("location_address") or {})
    address = {
        "postalName": addr_src.get("name") or issue.get("site_name", "") or "",
        "addressLine1": addr_src.get("line1", "") or "",
        "addressLine2": addr_src.get("line2", "") or "",
        "addressLine3": addr_src.get("line3", "") or "",
        "addressLine4": addr_src.get("line4", "") or "",
        "city": addr_src.get("city", "") or "",
        "county": addr_src.get("county", "") or "",
        "postCode": addr_src.get("postcode", "") or "",
        "sopDelAddress": None,
    }

    # Equipment ids
    equipment_ids: List[int] = []
    serial = issue.get("serial_number") or (equipment or {}).get("serial_number")
    sicon_eq_id = (config.get("equipment_id_mapping") or {}).get(serial) if serial else None
    if not sicon_eq_id:
        sicon_eq_id = (equipment or {}).get("sicon_equipment_id")
    if sicon_eq_id:
        equipment_ids = [int(sicon_eq_id)]

    # Sub-location (nested), if the joined site is mapped to Sicon
    sub_location = None
    if site and site.get("sicon_sub_location_id"):
        sub_location = {
            "siconSubLocationId": site["sicon_sub_location_id"],
            "custDeliveryAddressId": site.get("sage_delivery_address_id", 0) or 0,
            "description": (site.get("name") or site.get("label") or "")[:100],
            "comment": (site.get("notes") or site.get("floor_or_zone") or "")[:250],
        }
    elif issue.get("sicon_sub_location_id"):
        sub_location = {"siconSubLocationId": issue["sicon_sub_location_id"]}

    model = {
        "siSMCaseId": issue.get("sicon_case_id", 0) or 0,
        "caseNumber": issue.get("sicon_case_number", "") or "",
        "siSMDocumentStatusId": issue.get("sicon_document_status_id", 0) or 0,
        "siSMDocumentStatusName": issue.get("sicon_document_status_name", "") or "",
        "siSMDocumentSubStatusId": int(sub_status_id) if sub_status_id else 0,
        "summary": f"{issue.get('machine_type', '')} — {issue.get('serial_number', '')}".strip(" —"),
        "description": (issue.get("issue_description", "") or "")[:4000],
        "callDate": _iso(issue.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        "contactName": contact.get("ContactName", "") or "",
        "contactPhoneNumber": contact.get("ContactPhoneNumber", "") or "",
        "contactEmail": contact.get("ContactEmail", "") or "",
        "lastUpdatedDate": _iso(issue.get("updated_at")),
        "isNonContract": bool(issue.get("is_non_contract", False)),
        "address": address,
        "customerOrderNo": issue.get("customer_order_no", "") or issue.get("po_number", "") or "",
        "createdBy": issue.get("created_by_name", "") or issue.get("reporter_name", "") or "",
        **_analysis_camel(issue, triage_summary, ai_severity, ai_parts, org_name, equipment),
        "siconCRMPersonId": crm.get("crm_person_id") or config.get("default_crm_person_id", 0) or 0,
        "siconCRMCompanyId": crm.get("crm_company_id") or config.get("default_crm_company_id", 0) or 0,
        "caseType": {
            "siSMCaseTypeId": case_type_id,
            "name": case_type_name,
            "systemType": "",
            "isPreventativeMaintenanceType": bool(is_ppm),
            "isEnabled": True,
            "isCustom": False,
            "defaultAppointmentLabel": None,
        },
        "coverType": None,
        "sla": None,
        "faultCode": (issue.get("fault_code") or "")[:50] or None,
        "skill": None,
        "priority": {
            "siSMPriorityId": priority_id or 0,
            "name": priority_name,
            "colour": "",
        },
        "lastTrackingStatus": None,
        "contract": None,
        "contractLine": None,
        "project": None,
        "caseAdmin": None,
        "internalTeamId": config.get("default_internal_team_id", 0) or 0,
        "internalTeam": None,
        "externalTeamId": config.get("default_external_team_id", 0) or 0,
        "externalTeam": None,
        "customer": None,
        "customerContact": None,
        "subLocation": sub_location,
        "equipmentIds": equipment_ids,
    }
    return model


_APPT_TYPES = ("Work", "Travel", "Other")


def build_appointment_model_v1(issue: Dict, appt: Optional[Dict] = None, *,
                               sicon_appointment_id: int = 0, sicon_case_id: int = 0,
                               employee_ids: Optional[List[int]] = None) -> Dict:
    """Full Sicon AppointmentModel (camelCase) — matches Bruno
    Appointments/Appointment/PostOne.bru. `appt` carries scheduling/completion
    detail from our visit/case record."""
    appt = appt or {}
    a_type = appt.get("appointment_type") or appt.get("type") or "Work"
    if a_type not in _APPT_TYPES:
        a_type = "Work"
    parent = appt.get("parent_work_appointment_id")
    subject = (appt.get("subject")
               or f"{issue.get('machine_type', '')} — {issue.get('serial_number', '')}".strip(" —")
               or "Service appointment")
    lat_a = appt.get("arrival_latitude")
    lon_a = appt.get("arrival_longitude")
    lat_d = appt.get("departure_latitude")
    lon_d = appt.get("departure_longitude")
    return {
        "siconAppointmentId": int(sicon_appointment_id or 0),
        "siSMCaseId": int(sicon_case_id or issue.get("sicon_case_id", 0) or 0),
        "appointmentType": a_type,
        "parentWorkAppointmentId": int(parent) if parent else None,
        "subject": subject[:200],
        "description": (appt.get("description") or "")[:2000],
        "workBriefing": (appt.get("work_briefing") or issue.get("issue_description") or "")[:1000],
        "employeeIds": [int(e) for e in (employee_ids or appt.get("employee_ids") or []) if e],
        "chargeRateId": int(appt["charge_rate_id"]) if appt.get("charge_rate_id") else None,
        "labelId": int(appt["label_id"]) if appt.get("label_id") else None,
        "colour": (appt.get("colour") or "") or "",
        "confirmed": bool(appt.get("confirmed", False)),
        "scheduledStartDate": _iso(appt.get("scheduled_start") or appt.get("start")),
        "scheduledEndDate": _iso(appt.get("scheduled_end") or appt.get("end")),
        "appointmentComplete": bool(appt.get("complete", False) or appt.get("appointment_complete", False)),
        "workDoneDescription": (appt.get("work_done_description") or "")[:2000],
        "workDoneAcknowledged": bool(appt.get("work_done_acknowledged", False)),
        "furtherAction": (appt.get("further_action") or "")[:1000],
        "furtherActionAcknowledged": bool(appt.get("further_action_acknowledged", False)),
        "arrivalSignee": (appt.get("arrival_signee") or "") or "",
        "departureSignee": (appt.get("departure_signee") or "") or "",
        "arrivalLatitude": float(lat_a) if lat_a not in (None, "") else None,
        "arrivalLongitude": float(lon_a) if lon_a not in (None, "") else None,
        "departureLatitude": float(lat_d) if lat_d not in (None, "") else None,
        "departureLongitude": float(lon_d) if lon_d not in (None, "") else None,
    }


def build_time_booking_model_v1(*, employee_ids: List[int], start: str, end: str,
                                costing_hours=None, charging_hours=None,
                                charge_rate=None, is_estimate: bool = False) -> Dict:
    """Matches Bruno Appointments/AppointmentTimeBooking/PostOne.bru."""
    return {
        "employeeIds": [int(e) for e in (employee_ids or []) if e],
        "startDate": _iso(start),
        "endDate": _iso(end),
        "costingHours": costing_hours,
        "chargingHours": charging_hours,
        "chargeRate": charge_rate,
        "isEstimate": bool(is_estimate),
    }


def build_equipment_model_v1(equipment: Dict) -> Dict:
    """Full Sicon EquipmentModel (camelCase) — matches Bruno Equipment/PostOne.bru."""
    e = equipment or {}
    model = {
        "siconEquipmentId": e.get("sicon_equipment_id", 0) or 0,
        "itemId": e.get("sage_item_id"),
        "description": (e.get("display_name") or e.get("name") or e.get("machine_type") or "")[:200],
        "serialNumber": e.get("serial_number", "") or "",
        "idNumber": (e.get("asset_tag") or e.get("id_number") or "")[:60],
        "warrantyExpiry": _iso(e.get("warranty_expiry") or e.get("warranty_end_date")),
        "installDate": _iso(e.get("install_date")),
        "serviceIntervalMeasurement": e.get("service_interval_measurement", "") or "",
        "serviceIntervalDuration": e.get("service_interval_duration"),
        "notes": (e.get("notes") or "")[:1000],
        "customerId": e.get("sage_customer_id"),
        "siconEquipmentGroupDbKey": e.get("sicon_equipment_group_id"),
        "make": (e.get("make") or e.get("manufacturer") or "")[:80],
        "model": (e.get("model_code") or e.get("model") or "")[:80],
        "lastServiceDate": _iso(e.get("last_service_date")),
        "nextServiceDate": _iso(e.get("next_service_date")),
        "siconCrmCompanyId": e.get("sicon_crm_company_id"),
        "siconCrmPersonId": e.get("sicon_crm_person_id"),
        "siconCrmEndUserCompanyId": e.get("sicon_crm_end_user_company_id"),
        "siconCrmEndUserPersonId": e.get("sicon_crm_end_user_person_id"),
        "custDeliveryAddressDbKey": e.get("sage_delivery_address_id"),
        "siconSubLocationDbKey": e.get("sicon_sub_location_id"),
        "siconContactDbKey": e.get("sicon_contact_id"),
    }
    for i in range(1, 21):
        model[f"analysisCode{i}"] = (e.get(f"analysis_code_{i}") or "") or ""
    return model


def build_tracking_note_model_v1(*, note: str, status_id: int = 0, status: str = "",
                                 appointment_id: Optional[int] = None,
                                 visible_to_engineer: bool = True,
                                 visible_to_customer: bool = False,
                                 note_id: int = 0, latitude=None, longitude=None,
                                 time: Optional[str] = None) -> Dict:
    """Full Sicon TrackingNoteModel (camelCase) — matches Bruno
    Cases/CaseTrackingNote/PostOne.bru."""
    return {
        "siSMCaseTrackingNoteId": int(note_id or 0),
        "note": note or "",
        "time": _iso(time),
        "status": status or "",
        "statusId": int(status_id or 0),
        "appointmentId": int(appointment_id) if appointment_id else None,
        "visibleToEngineer": bool(visible_to_engineer),
        "visibleToCustomer": bool(visible_to_customer),
        "reassignedToCaseOwnerId": None,
        "reassignedToInternalTeamId": None,
        "reassignedToExternalTeamId": None,
        "latitude": float(latitude) if latitude not in (None, "") else None,
        "longitude": float(longitude) if longitude not in (None, "") else None,
    }
