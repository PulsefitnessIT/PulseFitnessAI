"""Generate the Pulse ↔ Sicon Service WebAPI v1 field-mapping CSV.
Run: python integrations/build_mapping_csv.py → integrations/Pulse-Sicon-Field-Mapping.csv
Source of truth: backend/utils/sicon_service_models.py + utils/sicon_client.py helpers.
"""
import csv
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "Pulse-Sicon-Field-Mapping.csv")

HEADER = ["Entity", "Sicon Field", "Nested Path", "Type", "Pulse Source / Derivation", "Direction", "Notes"]

R = []  # rows


def add(entity, field, path, typ, source, direction="Pulse → Sicon", notes=""):
    R.append([entity, field, path, typ, source, direction, notes])


# ─────────────────────────── CASE ───────────────────────────
E = "Case"
add(E, "siSMCaseId", "", "int", "issue.sicon_case_id", "both", "0 on create; Sicon returns the id which we persist as issue.sicon_case_id (key for updates)")
add(E, "caseNumber", "", "string", "issue.sicon_case_number", "both", "Returned by Sicon on create; stored back on the issue")
add(E, "siSMDocumentStatusId", "", "int", "issue.sicon_document_status_id", "both")
add(E, "siSMDocumentStatusName", "", "string", "issue.sicon_document_status_name", "both")
add(E, "siSMDocumentSubStatusId", "", "int", "issue.sicon_sub_status_id  OR  config.sub_status_mapping[issue.workflow_state]", "Pulse → Sicon")
add(E, "summary", "", "string", "issue.machine_type + ' — ' + issue.serial_number")
add(E, "description", "", "string", "issue.issue_description", "Pulse → Sicon", "Truncated to 4000 chars")
add(E, "callDate", "", "datetime", "issue.created_at")
add(E, "contactName", "", "string", "issue.created_by_name  OR  issue.reporter_name")
add(E, "contactPhoneNumber", "", "string", "issue.reporter_phone")
add(E, "contactEmail", "", "string", "issue.reporter_email  OR  issue.user_email")
add(E, "lastUpdatedDate", "", "datetime", "issue.updated_at")
add(E, "isNonContract", "", "bool", "issue.is_non_contract")
add(E, "postalName", "address", "string", "issue.site_address.name  OR  issue.site_name")
add(E, "addressLine1", "address", "string", "issue.site_address.line1")
add(E, "addressLine2", "address", "string", "issue.site_address.line2")
add(E, "addressLine3", "address", "string", "issue.site_address.line3")
add(E, "addressLine4", "address", "string", "issue.site_address.line4")
add(E, "city", "address", "string", "issue.site_address.city")
add(E, "county", "address", "string", "issue.site_address.county")
add(E, "postCode", "address", "string", "issue.site_address.postcode")
add(E, "sopDelAddress", "address", "object", "(reserved / null)", "Pulse → Sicon", "Not currently populated")
add(E, "customerOrderNo", "", "string", "issue.customer_order_no  OR  issue.po_number")
add(E, "createdBy", "", "string", "issue.created_by_name  OR  issue.reporter_name")
# analysisField1..20
_af = {
    1: "issue AI triage summary (ai_triage_summary)",
    2: "AI severity (UPPERCASE)",
    3: "AI suggested parts (max 250)",
    4: "issue.id (GymAxis issue id)",
    5: "organisation name (max 100)",
    6: "issue.sla_category OR issue.sla_tier",
    7: "issue.ppm_schedule_id",
    8: "issue.supplier_case_token",
    9: "issue.fault_code (max 50)",
    10: "issue.machine_type (max 80)",
    11: "equipment.make OR equipment.manufacturer",
    12: "equipment.model_code OR equipment.model",
    13: "equipment.install_date",
    14: "equipment.warranty_expiry OR warranty_end_date",
    15: "issue.id (equipment-lineage copy)",
    16: "issue.ppm_schedule_id (lineage copy)",
    17: "issue.ai_triage_summary (max 200)",
    18: "issue.source (default 'manual')",
    19: "issue.reporter_role OR created_by_role",
    20: "issue.csat_rating",
}
for i in range(1, 21):
    add(E, f"analysisField{i}", "", "string", _af[i], "Pulse → Sicon", "Sicon analysis/custom field")
add(E, "siconCRMPersonId", "", "int", "crm_links.crm_person_id  OR  config.default_crm_person_id")
add(E, "siconCRMCompanyId", "", "int", "crm_links.crm_company_id  OR  config.default_crm_company_id")
add(E, "siSMCaseTypeId", "caseType", "int", "config.default_case_type_id")
add(E, "name", "caseType", "string", "config.default_case_type_name  OR  FAULT_TYPE_TO_CASE_TYPE[issue.fault_type]")
add(E, "systemType", "caseType", "string", "(const '')")
add(E, "isPreventativeMaintenanceType", "caseType", "bool", "issue.fault_type == 'ppm'  OR  issue.ppm_schedule_id present")
add(E, "isEnabled", "caseType", "bool", "(const true)")
add(E, "isCustom", "caseType", "bool", "(const false)")
add(E, "defaultAppointmentLabel", "caseType", "object", "(null)")
add(E, "coverType", "", "object", "(reserved / null)")
add(E, "sla", "", "object", "(reserved / null)")
add(E, "faultCode", "", "string", "issue.fault_code (max 50)")
add(E, "skill", "", "object", "(reserved / null)")
add(E, "siSMPriorityId", "priority", "int", "config.priority_mapping[issue.severity]  OR  config.default_priority_id")
add(E, "name", "priority", "string", "SEVERITY_TO_PRIORITY_NAME[issue.severity] (Low/Medium/High/Critical)")
add(E, "colour", "priority", "string", "(const '')")
add(E, "lastTrackingStatus", "", "object", "(reserved / null)")
add(E, "contract", "", "object", "(reserved / null)")
add(E, "contractLine", "", "object", "(reserved / null)")
add(E, "project", "", "object", "(reserved / null)")
add(E, "caseAdmin", "", "object", "(reserved / null)")
add(E, "internalTeamId", "", "int", "config.default_internal_team_id")
add(E, "internalTeam", "", "object", "(reserved / null)")
add(E, "externalTeamId", "", "int", "config.default_external_team_id")
add(E, "externalTeam", "", "object", "(reserved / null)")
add(E, "customer", "", "object", "(reserved / null)")
add(E, "customerContact", "", "object", "(reserved / null)")
add(E, "siconSubLocationId", "subLocation", "int", "site.sicon_sub_location_id  OR  issue.sicon_sub_location_id", "Pulse → Sicon", "subLocation is null when the site is not mapped")
add(E, "custDeliveryAddressId", "subLocation", "int", "site.sage_delivery_address_id")
add(E, "description", "subLocation", "string", "site.name OR site.label")
add(E, "comment", "subLocation", "string", "site.notes OR site.floor_or_zone")
add(E, "equipmentIds", "", "int[]", "config.equipment_id_mapping[issue.serial_number]  OR  equipment.sicon_equipment_id")

# ───────────────────────── APPOINTMENT ─────────────────────────
E = "Appointment"
add(E, "siconAppointmentId", "", "int", "issue.sicon_appointment_id", "both", "0 on create; Sicon returns the id which we PERSIST as issue.sicon_appointment_id and use for PUT updates")
add(E, "siSMCaseId", "", "int", "issue.sicon_case_id")
add(E, "appointmentType", "", "string", "appt.appointment_type", "Pulse → Sicon", "Work | Travel | Other (default Work)")
add(E, "parentWorkAppointmentId", "", "int?", "appt.parent_work_appointment_id")
add(E, "subject", "", "string", "appt.subject  OR  machine_type + serial")
add(E, "description", "", "string", "appt.description", "Pulse → Sicon", "Max 2000 chars")
add(E, "workBriefing", "", "string", "appt.work_briefing  OR  issue.issue_description")
add(E, "employeeIds", "", "int[]", "appt.employee_ids (mapped Sicon employee ids)")
add(E, "chargeRateId", "", "int?", "appt.charge_rate_id")
add(E, "labelId", "", "int?", "appt.label_id")
add(E, "colour", "", "string", "appt.colour")
add(E, "confirmed", "", "bool", "appt.confirmed")
add(E, "scheduledStartDate", "", "datetime", "appt.scheduled_start (PM visit / calendar date)")
add(E, "scheduledEndDate", "", "datetime", "appt.scheduled_end")
add(E, "appointmentComplete", "", "bool", "appt.complete")
add(E, "workDoneDescription", "", "string", "appt.work_done_description (engineer work report)")
add(E, "workDoneAcknowledged", "", "bool", "appt.work_done_acknowledged")
add(E, "furtherAction", "", "string", "appt.further_action")
add(E, "furtherActionAcknowledged", "", "bool", "appt.further_action_acknowledged")
add(E, "arrivalSignee", "", "string", "appt.arrival_signee")
add(E, "departureSignee", "", "string", "appt.departure_signee")
add(E, "arrivalLatitude", "", "float?", "appt.arrival_latitude (engineer GPS)")
add(E, "arrivalLongitude", "", "float?", "appt.arrival_longitude")
add(E, "departureLatitude", "", "float?", "appt.departure_latitude")
add(E, "departureLongitude", "", "float?", "appt.departure_longitude")

# ─────────────────── APPOINTMENT TIME BOOKING ───────────────────
E = "AppointmentTimeBooking"
add(E, "employeeIds", "", "int[]", "timesheet.employee_ids")
add(E, "startDate", "", "datetime", "timebooking.start")
add(E, "endDate", "", "datetime", "timebooking.end")
add(E, "costingHours", "", "decimal?", "timebooking.costing_hours")
add(E, "chargingHours", "", "decimal?", "timebooking.charging_hours")
add(E, "chargeRate", "", "decimal?", "timebooking.charge_rate")
add(E, "isEstimate", "", "bool", "timebooking.is_estimate")

# ───────────────────────── EQUIPMENT ─────────────────────────
E = "Equipment"
add(E, "siconEquipmentId", "", "int", "equipment.sicon_equipment_id", "both", "0 on create; persisted after create")
add(E, "itemId", "", "int?", "equipment.sage_item_id")
add(E, "description", "", "string", "equipment.display_name OR name OR machine_type")
add(E, "serialNumber", "", "string", "equipment.serial_number")
add(E, "idNumber", "", "string", "equipment.asset_tag OR id_number")
add(E, "warrantyExpiry", "", "datetime?", "equipment.warranty_expiry OR warranty_end_date")
add(E, "installDate", "", "datetime?", "equipment.install_date")
add(E, "serviceIntervalMeasurement", "", "string", "equipment.service_interval_measurement")
add(E, "serviceIntervalDuration", "", "int?", "equipment.service_interval_duration")
add(E, "notes", "", "string", "equipment.notes")
add(E, "customerId", "", "int?", "equipment.sage_customer_id")
add(E, "siconEquipmentGroupDbKey", "", "int?", "equipment.sicon_equipment_group_id")
add(E, "make", "", "string", "equipment.make OR manufacturer")
add(E, "model", "", "string", "equipment.model_code OR model")
add(E, "lastServiceDate", "", "datetime?", "equipment.last_service_date")
add(E, "nextServiceDate", "", "datetime?", "equipment.next_service_date")
add(E, "siconCrmCompanyId", "", "int?", "equipment.sicon_crm_company_id")
add(E, "siconCrmPersonId", "", "int?", "equipment.sicon_crm_person_id")
add(E, "siconCrmEndUserCompanyId", "", "int?", "equipment.sicon_crm_end_user_company_id")
add(E, "siconCrmEndUserPersonId", "", "int?", "equipment.sicon_crm_end_user_person_id")
add(E, "custDeliveryAddressDbKey", "", "int?", "equipment.sage_delivery_address_id")
add(E, "siconSubLocationDbKey", "", "int?", "equipment.sicon_sub_location_id")
add(E, "siconContactDbKey", "", "int?", "equipment.sicon_contact_id")
for i in range(1, 21):
    add(E, f"analysisCode{i}", "", "string", f"equipment.analysis_code_{i}")

# ───────────────────────── TRACKING NOTE ─────────────────────────
E = "CaseTrackingNote"
add(E, "siSMCaseTrackingNoteId", "", "int", "note.sicon_tracking_note_id", "both", "0 on create")
add(E, "note", "", "string", "note.text (case update / engineer note)")
add(E, "time", "", "datetime?", "note.created_at")
add(E, "status", "", "string", "note.status_name")
add(E, "statusId", "", "int", "config.tracking_status_mapping[note.status]")
add(E, "appointmentId", "", "int?", "issue.sicon_appointment_id (links note to its appointment)")
add(E, "visibleToEngineer", "", "bool", "note.visible_to_engineer (default true)")
add(E, "visibleToCustomer", "", "bool", "note.visible_to_customer (default false)")
add(E, "reassignedToCaseOwnerId", "", "int?", "(reserved / null)")
add(E, "reassignedToInternalTeamId", "", "int?", "(reserved / null)")
add(E, "reassignedToExternalTeamId", "", "int?", "(reserved / null)")
add(E, "latitude", "", "float?", "note.latitude (engineer GPS)")
add(E, "longitude", "", "float?", "note.longitude")


def main():
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(R)
    print(f"Wrote {OUT} — {len(R)} field mappings")


if __name__ == "__main__":
    main()
