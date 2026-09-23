# PulseFitness.ai ↔ Sicon Service WebAPI v1 — Field Mapping

Total mapped fields: **164**. Every field has an explicit behaviour status — nothing is UNMAPPED.

Direction key: `Pulse → Sicon` (write), `Sicon → Pulse` (read/import), `both` (ID round-trip / read & write).

## Case

| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |
|---|---|---|---|---|---|
| `siSMCaseId` | issue.sicon_case_id | both | int | Mapped — ID round-trip (captured from Sicon response) | 0 on create; captured from response → issue.sicon_case_id |
| `caseNumber` | issue.sicon_case_number | both | string | Mapped — ID round-trip (captured from Sicon response) | Captured from response |
| `siSMDocumentStatusId` | issue.sicon_document_status_id | both | int | Mapped — read & write |  |
| `siSMDocumentStatusName` | issue.sicon_document_status_name | both | string | Mapped — read & write |  |
| `siSMDocumentSubStatusId` | issue.sicon_sub_status_id OR config.sub_status_mapping[issue.workflow_state] | Pulse → Sicon | int | Mapped — Pulse → Sicon write |  |
| `summary` | issue.machine_type + ' — ' + issue.serial_number | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `description` | issue.issue_description | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Max 4000 chars |
| `callDate` | issue.created_at | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `contactName` | issue.created_by_name OR issue.reporter_name | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `contactPhoneNumber` | issue.reporter_phone | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `contactEmail` | issue.reporter_email OR issue.user_email | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `lastUpdatedDate` | issue.updated_at | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `isNonContract` | issue.is_non_contract | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `address.postalName` | issue.site_address.name OR site_name | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.addressLine1` | issue.site_address.line1 | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.addressLine2` | issue.site_address.line2 | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.addressLine3` | issue.site_address.line3 | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.addressLine4` | issue.site_address.line4 | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.city` | issue.site_address.city | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.county` | issue.site_address.county | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.postCode` | issue.site_address.postcode | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `address.sopDelAddress` | — | Pulse → Sicon | object | Not used by Pulse — Sage SOP delivery-address link |  |
| `customerOrderNo` | issue.customer_order_no OR issue.po_number | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `createdBy` | issue.created_by_name OR issue.reporter_name | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `analysisField1` | issue → issue.ai_triage_summary | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField2` | issue → AI severity (UPPERCASE) | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField3` | issue → AI suggested parts (250) | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField4` | issue → issue.id | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField5` | issue → organisation name | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField6` | issue → issue.sla_category OR sla_tier | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField7` | issue → issue.ppm_schedule_id | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField8` | issue → issue.supplier_case_token | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField9` | issue → issue.fault_code | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField10` | issue → issue.machine_type | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField11` | issue → equipment.make OR manufacturer | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField12` | issue → equipment.model_code OR model | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField13` | issue → equipment.install_date | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField14` | issue → equipment.warranty_expiry | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField15` | issue → issue.id (lineage) | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField16` | issue → issue.ppm_schedule_id (lineage) | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField17` | issue → issue.ai_triage_summary (200) | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField18` | issue → issue.source | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField19` | issue → issue.reporter_role OR created_by_role | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `analysisField20` | issue → issue.csat_rating | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Sicon analysis field |
| `siconCRMPersonId` | crm_links.crm_person_id OR config.default_crm_person_id | both | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `siconCRMCompanyId` | crm_links.crm_company_id OR config.default_crm_company_id | both | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `caseType.siSMCaseTypeId` | config.default_case_type_id (from CaseType lookup) | Pulse → Sicon | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `caseType.name` | config.default_case_type_name OR FAULT_TYPE_TO_CASE_TYPE[issue.fault_type] | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `caseType.systemType` | const '' | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `caseType.isPreventativeMaintenanceType` | issue.fault_type=='ppm' OR issue.ppm_schedule_id | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `caseType.isEnabled` | const true | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `caseType.isCustom` | const false | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `caseType.defaultAppointmentLabel` | — | Sicon → Pulse | object | Sicon-owned config value (case-type default) |  |
| `coverType` | — | Pulse → Sicon | object | Mappable — awaiting Pulse cover-type source + Sicon cover IDs |  |
| `sla` | — | Pulse → Sicon | object | Partial — SLA tier sent in analysisField6; structured object awaiting Sicon SLA IDs |  |
| `faultCode` | issue.fault_code (50) | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `skill` | — | Pulse → Sicon | object | Mappable — awaiting Pulse required-skill source + Sicon skill IDs |  |
| `priority.siSMPriorityId` | config.priority_mapping[issue.severity] OR default_priority_id (from Priority lookup) | Pulse → Sicon | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `priority.name` | SEVERITY_TO_PRIORITY_NAME[issue.severity] | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `priority.colour` | const '' | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `lastTrackingStatus` | — | Sicon → Pulse | object | Sicon-derived / read-only (computed from tracking notes) |  |
| `contract` | — | Pulse → Sicon | object | Resolved by Sicon from the contract link — do not push object |  |
| `contractLine` | — | Pulse → Sicon | object | Resolved by Sicon — do not push object |  |
| `project` | — | Pulse → Sicon | object | Mappable — only when the job belongs to a Sicon Job-Costing project |  |
| `caseAdmin` | — | Pulse → Sicon | object | Mappable — awaiting Pulse→Sage user mapping |  |
| `internalTeamId` | config.default_internal_team_id (from Team lookup) | Pulse → Sicon | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `internalTeam` | — | Pulse → Sicon | object | Resolved by Sicon from internalTeamId (id is sent) |  |
| `externalTeamId` | config.default_external_team_id (from Team lookup) | Pulse → Sicon | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `externalTeam` | — | Pulse → Sicon | object | Resolved by Sicon from externalTeamId (id is sent) |  |
| `customer` | — | Pulse → Sicon | object | Resolved by Sicon from siconCRMCompanyId — do not push object |  |
| `customerContact` | — | Pulse → Sicon | object | Resolved by Sicon from siconCRMPersonId — do not push object |  |
| `subLocation.siconSubLocationId` | site.sicon_sub_location_id OR issue.sicon_sub_location_id | Pulse → Sicon | int | Mapped — Pulse → Sicon write |  |
| `subLocation.custDeliveryAddressId` | site.sage_delivery_address_id | Pulse → Sicon | int | Mapped — Pulse → Sicon write |  |
| `subLocation.description` | site.name OR site.label | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `subLocation.comment` | site.notes OR site.floor_or_zone | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `equipmentIds` | config.equipment_id_mapping[serial] OR equipment.sicon_equipment_id | Pulse → Sicon | int[] | Mapped — value sourced from Sicon lookup/reference record |  |

## Appointment

| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |
|---|---|---|---|---|---|
| `siconAppointmentId` | appointment.sicon_appointment_id | both | int | Mapped — ID round-trip (captured from Sicon response) | 0 on create; captured from response → appointment.sicon_appointment_id |
| `siSMCaseId` | issue.sicon_case_id | Pulse → Sicon | int | Mapped — Pulse → Sicon write |  |
| `appointmentType` | appt.appointment_type | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Work|Travel|Other |
| `parentWorkAppointmentId` | appt.parent_work_appointment_id | Pulse → Sicon | int? | Mapped — Pulse → Sicon write |  |
| `subject` | appt.subject OR machine_type+serial | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `description` | appt.description | Pulse → Sicon | string | Mapped — Pulse → Sicon write | Max 2000 chars |
| `workBriefing` | appt.work_briefing OR issue.issue_description | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `employeeIds` | appt.employee_ids (from Employee lookup) | Pulse → Sicon | int[] | Mapped — value sourced from Sicon lookup/reference record |  |
| `chargeRateId` | appt.charge_rate_id (lookup) | Pulse → Sicon | int? | Mapped — value sourced from Sicon lookup/reference record |  |
| `labelId` | appt.label_id (lookup) | Pulse → Sicon | int? | Mapped — value sourced from Sicon lookup/reference record |  |
| `colour` | appt.colour | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `confirmed` | appt.confirmed | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `scheduledStartDate` | appt.scheduled_start | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `scheduledEndDate` | appt.scheduled_end | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `appointmentComplete` | appt.complete | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `workDoneDescription` | appt.work_done_description | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `workDoneAcknowledged` | appt.work_done_acknowledged | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `furtherAction` | appt.further_action | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `furtherActionAcknowledged` | appt.further_action_acknowledged | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `arrivalSignee` | appt.arrival_signee | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `departureSignee` | appt.departure_signee | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `arrivalLatitude` | appt.arrival_latitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |
| `arrivalLongitude` | appt.arrival_longitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |
| `departureLatitude` | appt.departure_latitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |
| `departureLongitude` | appt.departure_longitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |

## AppointmentTimeBooking

| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |
|---|---|---|---|---|---|
| `employeeIds` | timebooking.employee_ids (Employee lookup) | Pulse → Sicon | int[] | Mapped — Pulse → Sicon write |  |
| `startDate` | timebooking.start | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `endDate` | timebooking.end | Pulse → Sicon | datetime | Mapped — Pulse → Sicon write |  |
| `costingHours` | timebooking.costing_hours | Pulse → Sicon | decimal? | Mapped — Pulse → Sicon write |  |
| `chargingHours` | timebooking.charging_hours | Pulse → Sicon | decimal? | Mapped — Pulse → Sicon write |  |
| `chargeRate` | timebooking.charge_rate | Pulse → Sicon | decimal? | Mapped — Pulse → Sicon write |  |
| `isEstimate` | timebooking.is_estimate | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |

## Equipment

| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |
|---|---|---|---|---|---|
| `siconEquipmentId` | equipment.sicon_equipment_id | both | int | Mapped — ID round-trip (captured from Sicon response) | 0 on create; captured from response |
| `itemId` | equipment.sage_item_id | both | int? | Mapped — read & write |  |
| `description` | equipment.display_name OR name OR machine_type | both | string | Mapped — read & write |  |
| `serialNumber` | equipment.serial_number | both | string | Mapped — read & write | Import match key |
| `idNumber` | equipment.asset_tag OR id_number | both | string | Mapped — read & write |  |
| `warrantyExpiry` | equipment.warranty_expiry OR warranty_end_date | both | datetime? | Mapped — read & write |  |
| `installDate` | equipment.install_date | both | datetime? | Mapped — read & write |  |
| `serviceIntervalMeasurement` | equipment.service_interval_measurement | both | string | Mapped — read & write |  |
| `serviceIntervalDuration` | equipment.service_interval_duration | both | int? | Mapped — read & write |  |
| `notes` | equipment.notes | both | string | Mapped — read & write |  |
| `customerId` | equipment.sage_customer_id | both | int? | Mapped — read & write |  |
| `siconEquipmentGroupDbKey` | equipment.sicon_equipment_group_id | both | int? | Mapped — read & write |  |
| `make` | equipment.make OR manufacturer | both | string | Mapped — read & write |  |
| `model` | equipment.model_code OR model | both | string | Mapped — read & write |  |
| `lastServiceDate` | equipment.last_service_date | both | datetime? | Mapped — read & write |  |
| `nextServiceDate` | equipment.next_service_date | both | datetime? | Mapped — read & write |  |
| `siconCrmCompanyId` | equipment.sicon_crm_company_id | both | int? | Mapped — read & write |  |
| `siconCrmPersonId` | equipment.sicon_crm_person_id | both | int? | Mapped — read & write |  |
| `siconCrmEndUserCompanyId` | equipment.sicon_crm_end_user_company_id | both | int? | Mapped — read & write |  |
| `siconCrmEndUserPersonId` | equipment.sicon_crm_end_user_person_id | both | int? | Mapped — read & write |  |
| `custDeliveryAddressDbKey` | equipment.sage_delivery_address_id | both | int? | Mapped — read & write |  |
| `siconSubLocationDbKey` | equipment.sicon_sub_location_id | both | int? | Mapped — read & write |  |
| `siconContactDbKey` | equipment.sicon_contact_id | both | int? | Mapped — read & write |  |
| `analysisCode1` | equipment.analysis_code_1 | both | string | Mapped — read & write |  |
| `analysisCode2` | equipment.analysis_code_2 | both | string | Mapped — read & write |  |
| `analysisCode3` | equipment.analysis_code_3 | both | string | Mapped — read & write |  |
| `analysisCode4` | equipment.analysis_code_4 | both | string | Mapped — read & write |  |
| `analysisCode5` | equipment.analysis_code_5 | both | string | Mapped — read & write |  |
| `analysisCode6` | equipment.analysis_code_6 | both | string | Mapped — read & write |  |
| `analysisCode7` | equipment.analysis_code_7 | both | string | Mapped — read & write |  |
| `analysisCode8` | equipment.analysis_code_8 | both | string | Mapped — read & write |  |
| `analysisCode9` | equipment.analysis_code_9 | both | string | Mapped — read & write |  |
| `analysisCode10` | equipment.analysis_code_10 | both | string | Mapped — read & write |  |
| `analysisCode11` | equipment.analysis_code_11 | both | string | Mapped — read & write |  |
| `analysisCode12` | equipment.analysis_code_12 | both | string | Mapped — read & write |  |
| `analysisCode13` | equipment.analysis_code_13 | both | string | Mapped — read & write |  |
| `analysisCode14` | equipment.analysis_code_14 | both | string | Mapped — read & write |  |
| `analysisCode15` | equipment.analysis_code_15 | both | string | Mapped — read & write |  |
| `analysisCode16` | equipment.analysis_code_16 | both | string | Mapped — read & write |  |
| `analysisCode17` | equipment.analysis_code_17 | both | string | Mapped — read & write |  |
| `analysisCode18` | equipment.analysis_code_18 | both | string | Mapped — read & write |  |
| `analysisCode19` | equipment.analysis_code_19 | both | string | Mapped — read & write |  |
| `analysisCode20` | equipment.analysis_code_20 | both | string | Mapped — read & write |  |

## CaseTrackingNote

| Sicon JSON Path | Pulse Field/Path | Direction | Type | Behaviour Status | Notes |
|---|---|---|---|---|---|
| `siSMCaseTrackingNoteId` | tracking_note.sicon_tracking_note_id | both | int | Mapped — ID round-trip (captured from Sicon response) | 0 on create; captured from response |
| `note` | tracking_note.text | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `time` | tracking_note.created_at | Pulse → Sicon | datetime? | Mapped — Pulse → Sicon write |  |
| `status` | tracking_note.status_name | Pulse → Sicon | string | Mapped — Pulse → Sicon write |  |
| `statusId` | config.tracking_status_mapping[status] (TrackingStatus lookup) | Pulse → Sicon | int | Mapped — value sourced from Sicon lookup/reference record |  |
| `appointmentId` | tracking_note.appointment_id → appointment.sicon_appointment_id | Pulse → Sicon | int? | Mapped — Pulse → Sicon write | Links the note to its Sicon appointment |
| `visibleToEngineer` | tracking_note.visible_to_engineer (default true) | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `visibleToCustomer` | tracking_note.visible_to_customer (default false) | Pulse → Sicon | bool | Mapped — Pulse → Sicon write |  |
| `reassignedToCaseOwnerId` | tracking_note.reassigned_to_case_owner_id | Pulse → Sicon | int? | Conditional — set only when a note reassigns the case |  |
| `reassignedToInternalTeamId` | tracking_note.reassigned_to_internal_team_id | Pulse → Sicon | int? | Conditional — set only on reassignment |  |
| `reassignedToExternalTeamId` | tracking_note.reassigned_to_external_team_id | Pulse → Sicon | int? | Conditional — set only on reassignment |  |
| `latitude` | tracking_note.latitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |
| `longitude` | tracking_note.longitude | Pulse → Sicon | float? | Mapped — Pulse → Sicon write |  |
