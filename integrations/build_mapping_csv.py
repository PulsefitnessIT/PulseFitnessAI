"""Generate the Pulse ↔ Sicon Service WebAPI v1 field mapping as BOTH
mapping.csv and FIELD_MAPPING.md.

Columns (per integration design): Sicon Entity, Sicon JSON Path, Pulse Entity,
Pulse Field/Path, Direction, Data Type, Sicon Behaviour Status, Notes.
Every Sicon field carries an explicit behaviour status — nothing is UNMAPPED.
"""
import csv
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_OUT = os.path.join(ROOT, "Pulse-Sicon-Field-Mapping.csv")
MD_OUT = os.path.join(ROOT, "FIELD_MAPPING.md")

PULSE_ENTITY = {
    "Case": "issue (+ joined equipment / site / crm_links)",
    "Appointment": "appointment (+ issue)",
    "AppointmentTimeBooking": "appointment_time_booking",
    "Equipment": "equipment",
    "CaseTrackingNote": "tracking_note",
}

# Explicit behaviour for fields we intentionally do NOT push as objects / or that
# are mappable-but-pending. Keeps the mapping honest — no "UNMAPPED".
BEHAVIOUR = {
    ("Case", "sopDelAddress"): "Not used by Pulse — Sage SOP delivery-address link",
    ("Case", "defaultAppointmentLabel"): "Sicon-owned config value (case-type default)",
    ("Case", "coverType"): "Mappable — awaiting Pulse cover-type source + Sicon cover IDs",
    ("Case", "sla"): "Partial — SLA tier sent in analysisField6; structured object awaiting Sicon SLA IDs",
    ("Case", "skill"): "Mappable — awaiting Pulse required-skill source + Sicon skill IDs",
    ("Case", "lastTrackingStatus"): "Sicon-derived / read-only (computed from tracking notes)",
    ("Case", "contract"): "Resolved by Sicon from the contract link — do not push object",
    ("Case", "contractLine"): "Resolved by Sicon — do not push object",
    ("Case", "project"): "Mappable — only when the job belongs to a Sicon Job-Costing project",
    ("Case", "caseAdmin"): "Mappable — awaiting Pulse→Sage user mapping",
    ("Case", "internalTeam"): "Resolved by Sicon from internalTeamId (id is sent)",
    ("Case", "externalTeam"): "Resolved by Sicon from externalTeamId (id is sent)",
    ("Case", "customer"): "Resolved by Sicon from siconCRMCompanyId — do not push object",
    ("Case", "customerContact"): "Resolved by Sicon from siconCRMPersonId — do not push object",
    ("CaseTrackingNote", "reassignedToCaseOwnerId"): "Conditional — set only when a note reassigns the case",
    ("CaseTrackingNote", "reassignedToInternalTeamId"): "Conditional — set only on reassignment",
    ("CaseTrackingNote", "reassignedToExternalTeamId"): "Conditional — set only on reassignment",
}
# Sicon primary keys captured back from responses (round-trip)
ROUNDTRIP = {
    ("Case", "siSMCaseId"), ("Case", "caseNumber"),
    ("Appointment", "siconAppointmentId"), ("Equipment", "siconEquipmentId"),
    ("CaseTrackingNote", "siSMCaseTrackingNoteId"),
}
# Lookup/reference IDs that must come from Sicon lookup records (never hardcode 0)
LOOKUP = {
    ("Case", "siSMCaseTypeId"), ("Case", "siSMPriorityId"),
    ("Case", "internalTeamId"), ("Case", "externalTeamId"),
    ("Case", "siconCRMPersonId"), ("Case", "siconCRMCompanyId"),
    ("Case", "equipmentIds"), ("Appointment", "employeeIds"),
    ("Appointment", "chargeRateId"), ("Appointment", "labelId"),
    ("CaseTrackingNote", "statusId"),
}

R = []


def add(entity, field, path, typ, source, direction="Pulse → Sicon", notes=""):
    R.append([entity, field, path, typ, source, direction, notes])


# ─── CASE ───
E = "Case"
add(E, "siSMCaseId", "", "int", "issue.sicon_case_id", "both", "0 on create; captured from response → issue.sicon_case_id")
add(E, "caseNumber", "", "string", "issue.sicon_case_number", "both", "Captured from response")
add(E, "siSMDocumentStatusId", "", "int", "issue.sicon_document_status_id", "both")
add(E, "siSMDocumentStatusName", "", "string", "issue.sicon_document_status_name", "both")
add(E, "siSMDocumentSubStatusId", "", "int", "issue.sicon_sub_status_id OR config.sub_status_mapping[issue.workflow_state]")
add(E, "summary", "", "string", "issue.machine_type + ' — ' + issue.serial_number")
add(E, "description", "", "string", "issue.issue_description", "Pulse → Sicon", "Max 4000 chars")
add(E, "callDate", "", "datetime", "issue.created_at")
add(E, "contactName", "", "string", "issue.created_by_name OR issue.reporter_name")
add(E, "contactPhoneNumber", "", "string", "issue.reporter_phone")
add(E, "contactEmail", "", "string", "issue.reporter_email OR issue.user_email")
add(E, "lastUpdatedDate", "", "datetime", "issue.updated_at")
add(E, "isNonContract", "", "bool", "issue.is_non_contract")
for f, src in [("postalName", "site_address.name OR site_name"), ("addressLine1", "site_address.line1"),
               ("addressLine2", "site_address.line2"), ("addressLine3", "site_address.line3"),
               ("addressLine4", "site_address.line4"), ("city", "site_address.city"),
               ("county", "site_address.county"), ("postCode", "site_address.postcode")]:
    add(E, f, "address", "string", f"issue.{src}")
add(E, "sopDelAddress", "address", "object", "—", "Pulse → Sicon")
add(E, "customerOrderNo", "", "string", "issue.customer_order_no OR issue.po_number")
add(E, "createdBy", "", "string", "issue.created_by_name OR issue.reporter_name")
_af = {1: "issue.ai_triage_summary", 2: "AI severity (UPPERCASE)", 3: "AI suggested parts (250)",
       4: "issue.id", 5: "organisation name", 6: "issue.sla_category OR sla_tier",
       7: "issue.ppm_schedule_id", 8: "issue.supplier_case_token", 9: "issue.fault_code",
       10: "issue.machine_type", 11: "equipment.make OR manufacturer", 12: "equipment.model_code OR model",
       13: "equipment.install_date", 14: "equipment.warranty_expiry", 15: "issue.id (lineage)",
       16: "issue.ppm_schedule_id (lineage)", 17: "issue.ai_triage_summary (200)", 18: "issue.source",
       19: "issue.reporter_role OR created_by_role", 20: "issue.csat_rating"}
for i in range(1, 21):
    add(E, f"analysisField{i}", "", "string", f"issue → {_af[i]}", "Pulse → Sicon", "Sicon analysis field")
add(E, "siconCRMPersonId", "", "int", "crm_links.crm_person_id OR config.default_crm_person_id", "both")
add(E, "siconCRMCompanyId", "", "int", "crm_links.crm_company_id OR config.default_crm_company_id", "both")
add(E, "siSMCaseTypeId", "caseType", "int", "config.default_case_type_id (from CaseType lookup)")
add(E, "name", "caseType", "string", "config.default_case_type_name OR FAULT_TYPE_TO_CASE_TYPE[issue.fault_type]")
add(E, "systemType", "caseType", "string", "const ''")
add(E, "isPreventativeMaintenanceType", "caseType", "bool", "issue.fault_type=='ppm' OR issue.ppm_schedule_id")
add(E, "isEnabled", "caseType", "bool", "const true")
add(E, "isCustom", "caseType", "bool", "const false")
add(E, "defaultAppointmentLabel", "caseType", "object", "—", "Sicon → Pulse")
add(E, "coverType", "", "object", "—")
add(E, "sla", "", "object", "—")
add(E, "faultCode", "", "string", "issue.fault_code (50)")
add(E, "skill", "", "object", "—")
add(E, "siSMPriorityId", "priority", "int", "config.priority_mapping[issue.severity] OR default_priority_id (from Priority lookup)")
add(E, "name", "priority", "string", "SEVERITY_TO_PRIORITY_NAME[issue.severity]")
add(E, "colour", "priority", "string", "const ''")
add(E, "lastTrackingStatus", "", "object", "—", "Sicon → Pulse")
add(E, "contract", "", "object", "—")
add(E, "contractLine", "", "object", "—")
add(E, "project", "", "object", "—")
add(E, "caseAdmin", "", "object", "—")
add(E, "internalTeamId", "", "int", "config.default_internal_team_id (from Team lookup)")
add(E, "internalTeam", "", "object", "—")
add(E, "externalTeamId", "", "int", "config.default_external_team_id (from Team lookup)")
add(E, "externalTeam", "", "object", "—")
add(E, "customer", "", "object", "—")
add(E, "customerContact", "", "object", "—")
add(E, "siconSubLocationId", "subLocation", "int", "site.sicon_sub_location_id OR issue.sicon_sub_location_id")
add(E, "custDeliveryAddressId", "subLocation", "int", "site.sage_delivery_address_id")
add(E, "description", "subLocation", "string", "site.name OR site.label")
add(E, "comment", "subLocation", "string", "site.notes OR site.floor_or_zone")
add(E, "equipmentIds", "", "int[]", "config.equipment_id_mapping[serial] OR equipment.sicon_equipment_id")

# ─── APPOINTMENT ───
E = "Appointment"
add(E, "siconAppointmentId", "", "int", "appointment.sicon_appointment_id", "both", "0 on create; captured from response → appointment.sicon_appointment_id")
add(E, "siSMCaseId", "", "int", "issue.sicon_case_id")
add(E, "appointmentType", "", "string", "appt.appointment_type", "Pulse → Sicon", "Work|Travel|Other")
add(E, "parentWorkAppointmentId", "", "int?", "appt.parent_work_appointment_id")
add(E, "subject", "", "string", "appt.subject OR machine_type+serial")
add(E, "description", "", "string", "appt.description", "Pulse → Sicon", "Max 2000 chars")
add(E, "workBriefing", "", "string", "appt.work_briefing OR issue.issue_description")
add(E, "employeeIds", "", "int[]", "appt.employee_ids (from Employee lookup)")
add(E, "chargeRateId", "", "int?", "appt.charge_rate_id (lookup)")
add(E, "labelId", "", "int?", "appt.label_id (lookup)")
add(E, "colour", "", "string", "appt.colour")
add(E, "confirmed", "", "bool", "appt.confirmed")
add(E, "scheduledStartDate", "", "datetime", "appt.scheduled_start")
add(E, "scheduledEndDate", "", "datetime", "appt.scheduled_end")
add(E, "appointmentComplete", "", "bool", "appt.complete")
add(E, "workDoneDescription", "", "string", "appt.work_done_description")
add(E, "workDoneAcknowledged", "", "bool", "appt.work_done_acknowledged")
add(E, "furtherAction", "", "string", "appt.further_action")
add(E, "furtherActionAcknowledged", "", "bool", "appt.further_action_acknowledged")
add(E, "arrivalSignee", "", "string", "appt.arrival_signee")
add(E, "departureSignee", "", "string", "appt.departure_signee")
add(E, "arrivalLatitude", "", "float?", "appt.arrival_latitude")
add(E, "arrivalLongitude", "", "float?", "appt.arrival_longitude")
add(E, "departureLatitude", "", "float?", "appt.departure_latitude")
add(E, "departureLongitude", "", "float?", "appt.departure_longitude")

# ─── TIME BOOKING ───
E = "AppointmentTimeBooking"
for f, t, s in [("employeeIds", "int[]", "timebooking.employee_ids (Employee lookup)"),
                ("startDate", "datetime", "timebooking.start"), ("endDate", "datetime", "timebooking.end"),
                ("costingHours", "decimal?", "timebooking.costing_hours"),
                ("chargingHours", "decimal?", "timebooking.charging_hours"),
                ("chargeRate", "decimal?", "timebooking.charge_rate"),
                ("isEstimate", "bool", "timebooking.is_estimate")]:
    add(E, f, "", t, s)

# ─── EQUIPMENT ───
E = "Equipment"
_eq = [("siconEquipmentId", "int", "equipment.sicon_equipment_id", "both", "0 on create; captured from response"),
       ("itemId", "int?", "equipment.sage_item_id", "both"),
       ("description", "string", "equipment.display_name OR name OR machine_type", "both"),
       ("serialNumber", "string", "equipment.serial_number", "both", "Import match key"),
       ("idNumber", "string", "equipment.asset_tag OR id_number", "both"),
       ("warrantyExpiry", "datetime?", "equipment.warranty_expiry OR warranty_end_date", "both"),
       ("installDate", "datetime?", "equipment.install_date", "both"),
       ("serviceIntervalMeasurement", "string", "equipment.service_interval_measurement", "both"),
       ("serviceIntervalDuration", "int?", "equipment.service_interval_duration", "both"),
       ("notes", "string", "equipment.notes", "both"),
       ("customerId", "int?", "equipment.sage_customer_id", "both"),
       ("siconEquipmentGroupDbKey", "int?", "equipment.sicon_equipment_group_id", "both"),
       ("make", "string", "equipment.make OR manufacturer", "both"),
       ("model", "string", "equipment.model_code OR model", "both"),
       ("lastServiceDate", "datetime?", "equipment.last_service_date", "both"),
       ("nextServiceDate", "datetime?", "equipment.next_service_date", "both"),
       ("siconCrmCompanyId", "int?", "equipment.sicon_crm_company_id", "both"),
       ("siconCrmPersonId", "int?", "equipment.sicon_crm_person_id", "both"),
       ("siconCrmEndUserCompanyId", "int?", "equipment.sicon_crm_end_user_company_id", "both"),
       ("siconCrmEndUserPersonId", "int?", "equipment.sicon_crm_end_user_person_id", "both"),
       ("custDeliveryAddressDbKey", "int?", "equipment.sage_delivery_address_id", "both"),
       ("siconSubLocationDbKey", "int?", "equipment.sicon_sub_location_id", "both"),
       ("siconContactDbKey", "int?", "equipment.sicon_contact_id", "both")]
for row in _eq:
    f, t, s, d = row[0], row[1], row[2], row[3]
    add(E, f, "", t, s, d, row[4] if len(row) > 4 else "")
for i in range(1, 21):
    add(E, f"analysisCode{i}", "", "string", f"equipment.analysis_code_{i}", "both")

# ─── TRACKING NOTE ───
E = "CaseTrackingNote"
add(E, "siSMCaseTrackingNoteId", "", "int", "tracking_note.sicon_tracking_note_id", "both", "0 on create; captured from response")
add(E, "note", "", "string", "tracking_note.text")
add(E, "time", "", "datetime?", "tracking_note.created_at")
add(E, "status", "", "string", "tracking_note.status_name")
add(E, "statusId", "", "int", "config.tracking_status_mapping[status] (TrackingStatus lookup)")
add(E, "appointmentId", "", "int?", "tracking_note.appointment_id → appointment.sicon_appointment_id", "Pulse → Sicon", "Links the note to its Sicon appointment")
add(E, "visibleToEngineer", "", "bool", "tracking_note.visible_to_engineer (default true)")
add(E, "visibleToCustomer", "", "bool", "tracking_note.visible_to_customer (default false)")
add(E, "reassignedToCaseOwnerId", "", "int?", "tracking_note.reassigned_to_case_owner_id")
add(E, "reassignedToInternalTeamId", "", "int?", "tracking_note.reassigned_to_internal_team_id")
add(E, "reassignedToExternalTeamId", "", "int?", "tracking_note.reassigned_to_external_team_id")
add(E, "latitude", "", "float?", "tracking_note.latitude")
add(E, "longitude", "", "float?", "tracking_note.longitude")


def json_path(entity, field, nested):
    return f"{nested}.{field}" if nested else field


def behaviour(entity, field, direction):
    if (entity, field) in BEHAVIOUR:
        return BEHAVIOUR[(entity, field)]
    if (entity, field) in ROUNDTRIP:
        return "Mapped — ID round-trip (captured from Sicon response)"
    if (entity, field) in LOOKUP:
        return "Mapped — value sourced from Sicon lookup/reference record"
    if direction == "both":
        return "Mapped — read & write"
    return "Mapped — Pulse → Sicon write"


HEADER = ["Sicon Entity", "Sicon JSON Path", "Pulse Entity", "Pulse Field/Path",
          "Direction", "Data Type", "Sicon Behaviour Status", "Notes"]


def rows_out():
    out = []
    for entity, field, nested, typ, source, direction, notes in R:
        pf = "—" if source == "—" else source
        out.append([entity, json_path(entity, field, nested), PULSE_ENTITY.get(entity, entity),
                    pf, direction, typ, behaviour(entity, field, direction), notes])
    return out


def main():
    rows = rows_out()
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    # Markdown
    lines = ["# PulseFitness.ai ↔ Sicon Service WebAPI v1 — Field Mapping", "",
             f"Total mapped fields: **{len(rows)}**. Every field has an explicit behaviour "
             "status — nothing is UNMAPPED.", "",
             "Direction key: `Pulse → Sicon` (write), `Sicon → Pulse` (read/import), "
             "`both` (ID round-trip / read & write).", ""]
    by_entity: dict = {}
    for r in rows:
        by_entity.setdefault(r[0], []).append(r)
    for entity, ers in by_entity.items():
        lines.append(f"## {entity}")
        lines.append("")
        lines.append("| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |")
        lines.append("|---|---|---|---|---|---|")
        for r in ers:
            lines.append(f"| `{r[1]}` | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
        lines.append("")
    with open(MD_OUT, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {CSV_OUT} and {MD_OUT} — {len(rows)} field mappings")


if __name__ == "__main__":
    main()
