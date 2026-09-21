"""Sicon field mapping reference table — authoritative truth.

Iter 216h7 (May 2026) — comprehensive rewrite from the iter-221 stub. The
previous 27-row table covered only the top-level Case/Contract fields and
was dramatically out of date with the actual wire payload, which carries
~200 fields across 7 entities (Case, Contract, ContractLine, TrackingNote,
Appointment, TimeBooking, Resource).

This module is the single source of truth shown to:
  • Master Admin → Sicon → Mapping panel (audit screen)
  • SOC 2 / ISO 27001 access-review evidence
  • Sicon partner team during integration sign-off

Backed by a static module-level constant rather than a Mongo collection
because the mapping is part of the integration contract (version-controlled
alongside the mapper functions in ``utils/sicon_client.py``).

Direction legend:
  →   Pulse Fitness → Sicon (push)
  ←   Sicon → Pulse Fitness (pull / poll)
  ↔   Bi-directional (push + pull both wired)

To add a new mapping: append to the relevant section below AND wire the
corresponding mapper helper in ``utils/sicon_client.py``. The two MUST
move together — the test ``test_iter_216h7_sicon_mapping_audit.py``
guards against drift.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user


router = APIRouter()


# ── Helper to keep the table readable ──────────────────────────────
def _row(entity, gx, si, direction, ftype, notes):
    return {
        "entity": entity, "gymaxis_field": gx, "sicon_field": si,
        "direction": direction, "type": ftype, "notes": notes,
    }


SICON_FIELD_MAPPING: list[dict] = [
    # ════════════════════════════════════════════════════════════════
    # CASE (Service Case / Issue) — spec §3.1
    # Wire-mapped by: map_gymaxis_to_sicon_case + map_sicon_case_to_gymaxis
    # ════════════════════════════════════════════════════════════════
    # ── Identity & top-level ────────────────────────────────────────
    _row("Case", "issue.sicon_case_id",                  "case.SiSMCaseId",                "↔", "int",      "Round-trip identity. Set after first sync."),
    _row("Case", "issue.sicon_case_number",              "case.CaseNumber",                "↔", "string",   "Human-readable Sicon-side reference."),
    _row("Case", "issue.case_type",                      "case.CaseTypeID",                "→", "enum",     "Mapped via priority_mapping config (Reactive / PPM / Project)."),
    _row("Case", "issue.case_type",                      "case.CaseTypeName",              "→", "string",   "Denormalised name for Sicon-side search/filtering."),
    _row("Case", "issue.issue_description",              "case.Description",               "↔", "text",     "Truncated to 4000 chars."),
    _row("Case", "issue.machine_type + serial_number",   "case.Summary",                   "↔", "string",   "Composed summary for case-list views."),
    _row("Case", "issue.created_at",                     "case.CallDate",                  "→", "datetime", "ISO 8601 in UTC."),
    _row("Case", "issue.severity",                       "case.PriorityID",                "→", "enum",     "Mapped via priority_mapping config (low/medium/critical → numeric)."),
    _row("Case", "issue.severity",                       "case.PriorityName",              "→", "string",   "Denormalised priority name."),
    _row("Case", "issue.status",                         "case.SiSMDocumentStatusID",      "↔", "enum",     "Bi-directional. Sicon close pulls back."),
    _row("Case", "issue.status",                         "case.SiSMDocumentStatusName",    "←", "string",   "Pulled denormalised."),
    _row("Case", "issue.workflow_state / sub_status_id", "case.SiSMDocumentSubStatusID",   "→", "enum",     "Iter 216h7: resolves via per-org sub_status_mapping (e.g. 'awaiting_parts' → 4). Explicit sicon_sub_status_id wins."),
    # ── Sicon-confirmed id-link / status fields (2026-06 meeting) — read casing-agnostically ──
    _row("Case", "issue.sicon_tracking_status_id",       "case.statusId",                  "↔", "int",      "Current tracking-status id. Sicon confirmed this is exposed on the case."),
    _row("Case", "issue.sicon_tracking_status",          "case.status",                    "←", "string",   "Denormalised tracking-status name."),
    _row("Case", "issue.sicon_last_tracking_status",     "case.lastTrackingStatus",        "←", "string",   "Last tracking status applied."),
    _row("Case", "issue.sicon_last_updated_at",          "case.lastUpdatedDate",           "←", "datetime", "Sicon-side last-modified timestamp for poll delta."),
    _row("Case", "issue.sicon_appointment_id",           "case.appointmentId",             "←", "int",      "Linked appointment id returned on the case (Sicon confirmed)."),
    _row("Case", "issue.sicon_latest_note_id",           "case.siSMCaseTrackingNoteId",    "←", "int",      "Latest tracking-note id on the case."),
    _row("Case", "contract.customer_order_number",       "case.customerOrderNo",           "↔", "string",   "Customer PO surfaced on the case."),
    _row("Case", "site.address (composed)",              "case.address",                   "→", "object",   "Container: postalName + addressLine1-4 + city + county + postCode (see Location* rows)."),
    _row("Case", "site.sicon_sub_location_id",           "case.subLocation",               "↔", "object",   "Container: SiconSubLocationID + description + comment."),
    _row("Case", "issue.case_type",                      "case.caseType",                  "→", "object",   "Container: siSMCaseTypeId + name (see CaseTypeID rows)."),
    _row("Case", "issue.severity",                       "case.priority",                  "→", "object",   "Container: siSMPriorityId + name (see PriorityID rows)."),
    _row("Case", "contract.sicon_contract_id",           "case.contract",                  "↔", "object",   "Container: SiconContractID + number."),
    _row("Case", "contract_line.sicon_contract_line_id", "case.contractLine",              "↔", "object",   "Container: SiconContractLineID + number."),
    _row("Case", "company (Sage customer)",              "case.customer",                  "→", "object",   "Container: SLCustomerAccountID + reference."),
    _row("Case", "user.contact (composed)",              "case.customerContact",           "→", "object",   "Container: contact name/email/phone."),
    _row("Case", "config.default_internal_team_id",      "case.internalTeam",              "↔", "object",   "Container: InternalTeamID + name."),
    _row("Case", "config.default_external_team_id",      "case.externalTeam",              "↔", "object",   "Container: ExternalTeamID + name."),
    # ── Sicon meeting follow-up (2026-06): these 6 now map to Pulse too ──
    _row("Case", "issue.cover_type",                     "case.coverType",                 "↔", "enum",     "Contract cover type (warranty / contract / chargeable)."),
    _row("Case", "issue.fault_code",                     "case.faultCode",                 "↔", "string",   "Fault classification code."),
    _row("Case", "issue.sla_category",                   "case.sla",                       "↔", "string",   "SLA band applied to the case."),
    _row("Case", "issue.latest_note",                    "case.note",                      "←", "text",     "Latest case note text (read-back)."),
    _row("Case", "issue.sicon_project_id",               "case.project",                   "↔", "object",   "Linked Sicon Projects job (id + name)."),
    _row("Case", "issue.sicon_case_admin_id",            "case.caseAdmin",                 "↔", "object",   "Case admin / owning Sage user (id + name)."),
    # ── Contact / Customer ──────────────────────────────────────────
    _row("Case", "issue.created_by_name / reporter_name", "case.ContactName",              "→", "string",   "Caller name on the ticket."),
    _row("Case", "issue.reporter_email / user_email",     "case.ContactEmail",             "→", "string",   "Caller email."),
    _row("Case", "issue.reporter_phone",                  "case.ContactPhoneNumber",       "→", "string",   "Caller phone."),
    _row("Case", "issue.sage_customer_reference",         "case.CustomerReference",        "→", "string",   "From CRM company → company_sage_ref fallback."),
    _row("Case", "issue.sage_customer_account_id",        "case.SLCustomerAccountID",      "→", "int",      "Sales-ledger account identity."),
    _row("Case", "issue.org.id",                          "case.CustomerId",               "→", "ref",      "Org → Sicon customer mapping."),
    # ── Assignment ──────────────────────────────────────────────────
    _row("Case", "config.default_assigned_user_id",       "case.AssignedToSageUserID",     "↔", "int",      "Per-org default; pulled back on Sicon edits."),
    _row("Case", "config.default_internal_team_id",       "case.InternalTeamID",           "↔", "int",      "Per-org default internal team."),
    _row("Case", "config.default_external_team_id",       "case.ExternalTeamID",           "↔", "int",      "Per-org default external team."),
    _row("Case", "issue.sicon_contract_id",               "case.SiconContractID",          "→", "ref",      "Falls back to config.default_contract_id."),
    _row("Case", "issue.sicon_contract_number",           "case.SiconContractNumber",      "→", "string",   "Denormalised contract number."),
    _row("Case", "config.default_contract_line_id",       "case.SiconContractLineID",      "→", "ref",      "Per-org default contract line."),
    _row("Case", "(reserved)",                            "case.SiJcJobID",                "→", "int",      "Job costing reference, sent 0 until JC integration lands."),
    _row("Case", "crm_links.crm_person_id",               "case.SiconCRMPersonID",         "→", "ref",      "Required on create per Sicon spec §6.2."),
    _row("Case", "crm_links.crm_company_id",              "case.SiconCRMCompanyID",        "→", "ref",      "Required on create per Sicon spec §6.2."),
    _row("Case", "issue.assignee_engineer_id",            "case.EngineerId",               "↔", "ref",      "From /sicon/engineers refresh."),
    _row("Case", "issue.resolved_at",                     "case.ClosedDate",               "↔", "datetime", "Null until close. Sicon close pulls back."),
    # ── Location (8 fields per spec §3.1) ──────────────────────────
    _row("Case", "issue.site_address.name",               "case.LocationPostalName",       "→", "string",   "Site name for postal labelling."),
    _row("Case", "issue.site_address.line1",              "case.LocationAddressLine1",     "→", "string",   ""),
    _row("Case", "issue.site_address.line2",              "case.LocationAddressLine2",     "→", "string",   ""),
    _row("Case", "issue.site_address.line3",              "case.LocationAddressLine3",     "→", "string",   ""),
    _row("Case", "issue.site_address.line4",              "case.LocationAddressLine4",     "→", "string",   ""),
    _row("Case", "issue.site_address.city",               "case.LocationCity",             "→", "string",   ""),
    _row("Case", "issue.site_address.county",             "case.LocationCounty",           "→", "string",   ""),
    _row("Case", "issue.site_address.postcode",           "case.LocationPostCode",         "→", "string",   ""),
    # ── SubLocation ────────────────────────────────────────────────
    _row("Case", "site.sicon_sub_location_id",            "case.SubLocation.SiconSubLocationID",  "↔", "ref",     "Floor / zone within the site."),
    _row("Case", "site.sage_delivery_address_id",         "case.SubLocation.CustDeliveryAddressID","→", "int",    "Sage delivery-address join."),
    _row("Case", "site.name / label",                     "case.SubLocation.Description",  "→", "string",   "Truncated to 100 chars."),
    _row("Case", "site.notes / floor_or_zone",            "case.SubLocation.Comment",      "→", "string",   "Truncated to 250 chars."),
    # ── Equipment cross-link ───────────────────────────────────────
    _row("Case", "issue.equipment.sicon_equipment_id",    "case.Equipments[].SiconEquipmentID","↔", "ref",  "Preferred over flat EquipmentIDs[]."),
    _row("Case", "issue.equipment.sage_item_id",          "case.Equipments[].ItemID",      "→", "int",      "Sage stock item identity."),
    _row("Case", "issue.machine_type / equipment.display_name","case.Equipments[].Name",   "→", "string",   "Human-readable; truncated to 120 chars."),
    _row("Case", "(computed)",                            "case.EquipmentIDs[]",           "→", "int[]",    "Flat fallback list of equipment IDs."),
    # ── AnalysisField1-8 (core triage) — spec §10 ──────────────────
    _row("Case", "issue.ai_triage_parsed.summary",        "case.AnalysisField1",           "→", "string",   "AI triage diagnosis. Truncated 250 chars."),
    _row("Case", "issue.ai_triage_parsed.severity",       "case.AnalysisField2",           "→", "string",   "AI-detected severity (UPPERCASE)."),
    _row("Case", "issue.ai_triage_parsed.recommended_parts","case.AnalysisField3",         "→", "string",   "Comma-joined parts list. 250 chars."),
    _row("Case", "issue.id",                              "case.AnalysisField4",           "→", "string",   "Pulse Fitness issue id for joins."),
    _row("Case", "organization.name",                     "case.AnalysisField5",           "→", "string",   "Truncated 100 chars."),
    _row("Case", "issue.sla_category / sla_tier",         "case.AnalysisField6",           "→", "string",   "SLA bucket for breach calc."),
    _row("Case", "issue.ppm_schedule_id",                 "case.AnalysisField7",           "→", "string",   "PPM schedule join if relevant."),
    _row("Case", "issue.supplier_case_token",             "case.AnalysisField8",           "→", "string",   "Supplier-portal correlation token."),
    # ── AnalysisField9-20 (extended — Phase A iter 216g) ───────────
    _row("Case", "issue.fault_code",                      "case.AnalysisField9",           "→", "string",   "Equipment-emitted error code if known. 50 chars."),
    _row("Case", "issue.machine_type",                    "case.AnalysisField10",          "→", "string",   "80 chars."),
    _row("Case", "equipment.make / manufacturer",         "case.AnalysisField11",          "→", "string",   "80 chars."),
    _row("Case", "equipment.model_code / model",          "case.AnalysisField12",          "→", "string",   "80 chars."),
    _row("Case", "equipment.install_date",                "case.AnalysisField13",          "→", "date",     "ISO date string."),
    _row("Case", "equipment.warranty_expiry",             "case.AnalysisField14",          "→", "date",     "ISO date string."),
    _row("Case", "issue.id (duplicate for join)",         "case.AnalysisField15",          "→", "string",   "60 chars."),
    _row("Case", "issue.ppm_schedule_id (duplicate)",     "case.AnalysisField16",          "→", "string",   "60 chars."),
    _row("Case", "issue.ai_triage_summary (verbose)",     "case.AnalysisField17",          "→", "string",   "200 chars."),
    _row("Case", "issue.source",                          "case.AnalysisField18",          "→", "string",   "manual / api / qr-scan / portal / email. 30 chars."),
    _row("Case", "issue.reporter_role / created_by_role", "case.AnalysisField19",          "→", "string",   "member / staff / engineer / public. 30 chars."),
    _row("Case", "issue.csat_rating",                     "case.AnalysisField20",          "→", "int",      "1-5 customer satisfaction post-resolution. Iter 216h7 — CRM module populates on rating submit."),

    # ════════════════════════════════════════════════════════════════
    # CONTRACT (CRM Contract → Sicon Service Contract) — spec §Contract
    # Wire-mapped by: map_gymaxis_contract_to_sicon
    # ════════════════════════════════════════════════════════════════
    _row("Contract", "contract.sicon_contract_id",        "contract.ContractID",           "↔", "int",      "Identity round-trip after first sync."),
    _row("Contract", "contract.contract_number",          "contract.ContractNumber",       "↔", "string",   "Human reference."),
    _row("Contract", "contract.sage_customer_number",     "contract.CustomerNumber",       "→", "string",   "Falls back to sage_customer_id or sage_customer_account_id."),
    _row("Contract", "contract.description / title",      "contract.Description",          "→", "string",   ""),
    _row("Contract", "contract.billing_description / title","contract.SOPBillingDescription","→","string",  "Sales-order printable description."),
    _row("Contract", "contract.customer_order_number",    "contract.CustomerOrderNumber",  "↔", "string",   "Iter 216h7: amendable post-sync via POST /sicon/update-contract-po."),
    _row("Contract", "contract.start_date",               "contract.StartDate",            "→", "date",     "Header start date."),
    _row("Contract", "contract.end_date",                 "contract.EndDate",              "→", "date",     "Header end date."),
    _row("Contract", "contract.value_pence",              "contract.AnnualValue",          "→", "money",    "Minor units in Pulse Fitness, GBP major in Sicon."),
    _row("Contract", "contract.org.id",                   "contract.CustomerId",           "→", "ref",      "Org → Sicon customer mapping."),
    _row("Contract", "contract.renewal_date",             "contract.RenewalDate",          "→", "date",     "Drives auto-renewal reminders both sides."),
    # ── Spare slots (Iter 216h7 full coverage) ─────────────────────
    _row("Contract", "contract.spare_text_map[i] / spare_text{i}","contract.SpareText1-7", "→", "string[]","7 string slots. 250 chars each."),
    _row("Contract", "contract.spare_num_map[i] / spare_num{i}",  "contract.SpareNum1-7",  "→", "float[]", "7 numeric slots. Finance/KPI signals."),
    _row("Contract", "contract.spare_date_map[i] / spare_date{i}","contract.SpareDate1-7", "→", "date[]",  "7 ISO-date slots. Renewal anchors / review dates."),

    # ════════════════════════════════════════════════════════════════
    # CONTRACT LINE — spec §ContractLine
    # Wire-mapped by: map_gymaxis_contract_line_to_sicon
    # ════════════════════════════════════════════════════════════════
    _row("ContractLine", "line.sicon_contract_id",        "line.SiconContractID",          "→", "ref",      ""),
    _row("ContractLine", "line.sicon_contract_line_id",   "line.SiconContractLineID",      "↔", "int",      "Identity once line synced."),
    _row("ContractLine", "line.item_code / equipment_item_code","line.ItemCode",           "→", "string",   "Sage stock item code."),
    _row("ContractLine", "line.sop_description / description","line.SalesOrderDescription","→", "string",   "250 chars."),
    _row("ContractLine", "line.internal_description / description","line.InternalDescription","→","string","500 chars."),
    # Dates & price
    _row("ContractLine", "line.start_date",               "line.ContractStartDate",        "→", "date",     ""),
    _row("ContractLine", "line.end_date",                 "line.ContractEndDate",          "→", "date",     ""),
    _row("ContractLine", "line.quantity",                 "line.Quantity",                 "→", "float",    "Default 1."),
    _row("ContractLine", "line.unit_price",               "line.UnitPrice",                "→", "float",    "Internal unit price."),
    _row("ContractLine", "line.sop_unit_price",           "line.SOPUnitPrice",             "→", "float",    "Sales-order unit price (falls back to UnitPrice)."),
    _row("ContractLine", "line.price_interval",           "line.PriceInterval",            "→", "string",   "years / months / weeks."),
    _row("ContractLine", "line.amended_quantity",         "line.AmendedQuantity",          "→", "float",    "For mid-term amendments."),
    _row("ContractLine", "line.amended_unit_price",       "line.AmendedUnitPrice",         "→", "float",    "For mid-term amendments."),
    _row("ContractLine", "line.bill_cover_from",          "line.BillCoverFrom",            "→", "date",     ""),
    _row("ContractLine", "line.order_date",               "line.OrderDate",                "→", "date",     ""),
    _row("ContractLine", "line.original_start_date",      "line.OriginalStartDate",        "→", "date",     "For renewed contracts: original anchor."),
    _row("ContractLine", "line.annual_unit_cost",         "line.AnnualUnitCost",           "→", "float",    "Pre-discount annualised cost."),
    # Renewal
    _row("ContractLine", "line.renewal_quantity",         "line.RenewalQuantity",          "→", "float",    ""),
    _row("ContractLine", "line.renewal_unit_price",       "line.RenewalUnitPrice",         "→", "float",    ""),
    _row("ContractLine", "line.renewal_frequency",        "line.RenewalFrequency",         "→", "int",      ""),
    _row("ContractLine", "line.renewal_price_freq_interval","line.RenewalPriceFreqInterval","→","string",   ""),
    _row("ContractLine", "line.renewal_duration",         "line.RenewalDuration",          "→", "int",      "Months in the renewal term."),
    _row("ContractLine", "line.contract_extended",        "line.ContractExtended",         "→", "bool",     ""),
    _row("ContractLine", "line.initial_contract_duration","line.InitialContractDuration",  "→", "int",      "Default 12."),
    _row("ContractLine", "line.extended_contract_duration","line.ExtendedContractDuration","→", "int",      ""),
    _row("ContractLine", "line.contract_duration",        "line.ContractDuration",         "→", "int",      ""),
    _row("ContractLine", "line.is_renewal_update",        "line.isRenewalUpdate",          "→", "bool",     "True when this is an amendment."),
    _row("ContractLine", "line.reason_code",              "line.ReasonCode",               "→", "string",   "Audit code for the amendment."),
    # Billing
    _row("ContractLine", "line.invoice_frequency_value",  "line.InvoiceFrequencyValue",    "→", "int",      "Default 1."),
    _row("ContractLine", "line.invoice_frequency_interval","line.InvoiceFrequencyInterval","→", "string",   "Default 'months'."),
    _row("ContractLine", "line.bill_cover_duration",      "line.BillCoverDuration",        "→", "int",      ""),
    _row("ContractLine", "line.bill_month_in_advance_arrears_qty","line.BillMonthInAdvanceArrearsQty","→","int",""),
    _row("ContractLine", "line.bill_in_arrears",          "line.BillInArrears",            "→", "bool",     ""),
    _row("ContractLine", "line.pro_rata",                 "line.ProRata",                  "→", "bool",     ""),
    _row("ContractLine", "line.is_rolling",               "line.IsRolling",                "→", "bool",     "Auto-renewing line."),
    # Discounts (3 banks)
    _row("ContractLine", "line.discount1_percent",        "line.Discount1Percent",         "→", "float",    ""),
    _row("ContractLine", "line.discount1_value",          "line.Discount1Value",           "→", "float",    ""),
    _row("ContractLine", "line.discount2_percent",        "line.Discount2Percent",         "→", "float",    ""),
    _row("ContractLine", "line.discount2_value",          "line.Discount2Value",           "→", "float",    ""),
    _row("ContractLine", "line.discount3_percent",        "line.Discount3Percent",         "→", "float",    ""),
    _row("ContractLine", "line.discount3_value",          "line.Discount3Value",           "→", "float",    ""),
    # Supplier
    _row("ContractLine", "line.visit_frequency / sla.ppm_frequency","line.VisitFrequency", "→", "string",   "PPM cadence (e.g. 'quarterly')."),
    _row("ContractLine", "line.who_sold",                 "line.WhoSold",                  "→", "string",   "Sales attribution."),
    _row("ContractLine", "line.pl_supplier_id",           "line.PLSupplierID",             "→", "int",      "Purchase-ledger supplier identity."),
    _row("ContractLine", "line.supplier_code",            "line.SupplierCode",             "→", "string",   ""),
    _row("ContractLine", "line.supplier_unit_price",      "line.SupplierUnitPrice",        "→", "float",    "Cost-of-goods for margin calc."),
    # Analysis codes (15 of 150 wired; rest are caller-overrideable)
    _row("ContractLine", "line.tier / sla.tier",          "line.CLAnalysisCode1",          "→", "string",   "SLA tier (Gold/Platinum/Silver)."),
    _row("ContractLine", "line.sla.response_hours",       "line.CLAnalysisCode2",          "→", "string",   "Response-hours target."),
    _row("ContractLine", "line.sla.resolution_hours",     "line.CLAnalysisCode3",          "→", "string",   "Resolution-hours target."),
    _row("ContractLine", "line.sla.oos_credit_terms",     "line.CLAnalysisCode4",          "→", "string",   "Out-of-service credit terms."),
    _row("ContractLine", "line.safety_critical",          "line.CLAnalysisCode5",          "→", "enum",     "YES/NO."),
    _row("ContractLine", "line.asset_id / equipment_id",  "line.CLAnalysisCode6",          "→", "string",   "Pulse Fitness asset id for joins."),
    _row("ContractLine", "line.site_id",                  "line.CLAnalysisCode7",          "→", "string",   "Pulse Fitness site id."),
    _row("ContractLine", "line.ppm_frequency_override",   "line.CLAnalysisCode8",          "→", "string",   ""),
    _row("ContractLine", "line.tender_reference",         "line.CLAnalysisCode9",          "→", "string",   ""),
    _row("ContractLine", "line.renewal_notice_days",      "line.CLAnalysisCode10",         "→", "int",      "Default 90."),
    _row("ContractLine", "line.sla_penalty_band",         "line.CLAnalysisCode11",         "→", "string",   "Iter 216h7: penalty schedule '0/5/10/25%' or absolute code."),
    _row("ContractLine", "line.kpi_breach_flag",          "line.CLAnalysisCode12",         "→", "enum",     "Iter 216h7: OK / WARN / BREACH from the SLA worker."),
    _row("ContractLine", "line.finance_approver_email",   "line.CLAnalysisCode13",         "→", "string",   "Iter 216h7: last amend authoriser email."),
    _row("ContractLine", "line.billing_cycle_override",   "line.CLAnalysisCode14",         "→", "string",   "Iter 216h7: annual / semi-annual / quarterly."),
    _row("ContractLine", "line.holdback_pct",             "line.CLAnalysisCode15",         "→", "float",    "Iter 216h7: retention against final invoice."),
    _row("ContractLine", "line.analysis_codes[CL*]",      "line.CLAnalysisCode16-150",     "→", "string",   "Caller-overrideable slots; 135 free for future use."),

    # ════════════════════════════════════════════════════════════════
    # TRACKING NOTE — spec §3.4
    # Wire-mapped by: build_tracking_note_payload + map_sicon_tracking_note_to_gymaxis
    # ════════════════════════════════════════════════════════════════
    _row("TrackingNote", "note.text",                     "note.TrackingNote",             "↔", "string",   "Truncated to 2000 chars."),
    _row("TrackingNote", "note.status_id",                "note.CaseTrackingStatusID",     "↔", "int",      "Optional status transition with the note."),
    _row("TrackingNote", "note.visible_to_engineer",      "note.VisibleToEngineer",        "↔", "bool",     "Default true."),
    _row("TrackingNote", "note.visible_to_customer",      "note.VisibleToCustomer",        "↔", "bool",     "Customer-portal visibility."),
    _row("TrackingNote", "note.created_by",               "note.CreatedBy",                "↔", "string",   "Default 'Pulse Fitness AI'."),
    _row("TrackingNote", "note.timestamp",                "note.Time",                     "↔", "datetime", "ISO 8601."),
    _row("TrackingNote", "note.sicon_appointment_id",     "note.SiconAppointmentID",       "→", "ref",      "Optional appointment link."),
    _row("TrackingNote", "note.latitude",                 "note.Latitude",                 "→", "float",    "GPS from engineer portal — proof-of-location."),
    _row("TrackingNote", "note.longitude",                "note.Longitude",                "→", "float",    "GPS from engineer portal — proof-of-location."),
    _row("TrackingNote", "note.reassign_to_sage_user",    "note.ReassignToSageUserNumber", "→", "int",      "Optional same-call reassignment."),
    _row("TrackingNote", "(Sicon-side identity)",         "note.ID / TrackingNoteID",      "←", "int",      "Pulled on retrieval."),

    # ════════════════════════════════════════════════════════════════
    # APPOINTMENT — spec §3.2
    # Wire-mapped by: build_appointment_payload + build_appointment_completion_payload + map_sicon_appointment_to_gymaxis
    # ════════════════════════════════════════════════════════════════
    _row("Appointment", "appt.sicon_appointment_id",      "appt.SiconAppointmentID",       "↔", "int",      "Identity once created."),
    _row("Appointment", "appt.case_id",                   "appt.SiSMCaseId / SiSMCaseID",  "→", "int",      "Parent case (both casings supported)."),
    _row("Appointment", "appt.scheduled_start",           "appt.ScheduledStartDate",       "↔", "datetime", ""),
    _row("Appointment", "appt.scheduled_end",             "appt.ScheduledEndDate",         "↔", "datetime", ""),
    _row("Appointment", "appt.type",                      "appt.AppointmentType",          "↔", "enum",     "Work / Travel / Other."),
    _row("Appointment", "appt.subject (derived)",         "appt.Subject",                  "→", "string",   "Composed from machine_type + serial."),
    _row("Appointment", "appt.work_briefing",             "appt.WorkBriefing",             "→", "string",   "Pre-visit notes. 1000 chars."),
    _row("Appointment", "appt.employee_ids",              "appt.EmployeeIDs",              "↔", "int[]",    "Assigned engineers."),
    _row("Appointment", "appt.confirmed",                 "appt.Confirmed",                "↔", "bool",     ""),
    _row("Appointment", "appt.parent_work_appointment_id","appt.ParentWorkAppointmentID",  "→", "int",      "Only when type=Travel."),
    _row("Appointment", "appt.charge_rate_id",            "appt.ChargeRateID",             "→", "int",      ""),
    _row("Appointment", "appt.label_id",                  "appt.LabelID",                  "→", "int",      "Calendar label."),
    # Completion
    _row("Appointment", "appt.completion.work_done",      "appt.WorkDoneDescription",      "↔", "text",     "2000 chars."),
    _row("Appointment", "appt.completion.complete",       "appt.AppointmentComplete",      "↔", "bool",     "Set true on completion."),
    _row("Appointment", "appt.completion.work_done_ack",  "appt.WorkDoneAcknowledged",     "→", "bool",     "Customer ack."),
    _row("Appointment", "appt.completion.further_action", "appt.FurtherAction",            "↔", "text",     "Follow-up notes."),
    _row("Appointment", "appt.completion.further_action_ack","appt.FurtherActionAcknowledged","→","bool",   ""),
    _row("Appointment", "appt.completion.arrival_signee", "appt.ArrivalSignee",            "↔", "string",   "Sign-in name."),
    _row("Appointment", "appt.completion.departure_signee","appt.DepartureSignee",         "↔", "string",   "Sign-out name."),
    _row("Appointment", "appt.completion.arrival_lat",    "appt.ArrivalLatitude",          "↔", "float",    "Engineer GPS on arrival."),
    _row("Appointment", "appt.completion.arrival_lon",    "appt.ArrivalLongitude",         "↔", "float",    ""),
    _row("Appointment", "appt.completion.departure_lat",  "appt.DepartureLatitude",        "↔", "float",    "Engineer GPS on departure."),
    _row("Appointment", "appt.completion.departure_lon",  "appt.DepartureLongitude",       "↔", "float",    ""),

    # ════════════════════════════════════════════════════════════════
    # TIME BOOKING — spec §3.3
    # Wire-mapped by: build_time_booking_payload + map_sicon_time_booking_to_gymaxis
    # ════════════════════════════════════════════════════════════════
    _row("TimeBooking", "tb.employee_ids",                "tb.EmployeeIDs",                "↔", "int[]",    ""),
    _row("TimeBooking", "tb.start_date",                  "tb.StartDate",                  "↔", "datetime", ""),
    _row("TimeBooking", "tb.end_date",                    "tb.EndDate",                    "↔", "datetime", ""),
    _row("TimeBooking", "tb.actual_hours",                "tb.ActualHours",                "↔", "float",    "Labour for profitability calc."),
    _row("TimeBooking", "tb.charge_rate",                 "tb.ChargeRate",                 "→", "int",      "Rate code for invoicing."),
    _row("TimeBooking", "tb.costing_hours",               "tb.costingHours",               "↔", "float",    "Internal cost hours (Sicon confirmed)."),
    _row("TimeBooking", "tb.charging_hours",              "tb.chargingHours",              "↔", "float",    "Billable/charge hours."),
    _row("TimeBooking", "tb.is_estimate",                 "tb.isEstimate",                 "↔", "bool",     "Estimate vs actual flag."),

    # ════════════════════════════════════════════════════════════════
    # RESOURCE / ENGINEER — pulled via /sicon/engineers/refresh
    # Wire-mapped by: map_sicon_resource_to_engineer
    # ════════════════════════════════════════════════════════════════
    _row("Resource", "engineer.sicon_employee_id",        "resource.SIJCEMPID",            "←", "int",      "Sicon employee identity."),
    _row("Resource", "engineer.full_name",                "resource.FullName",             "←", "string",   "Composed from FirstName + Surname."),
    _row("Resource", "engineer.first_name",               "resource.FirstName",            "←", "string",   ""),
    _row("Resource", "engineer.surname",                  "resource.Surname",              "←", "string",   ""),
    _row("Resource", "engineer.email",                    "resource.Email",                "←", "string",   "Used for in-app deep-links."),
    _row("Resource", "engineer.mobile_no",                "resource.MobileNo",             "←", "string",   ""),
    _row("Resource", "engineer.telephone_no",             "resource.TelephoneNo",          "←", "string",   ""),
    _row("Resource", "engineer.address_line1",            "resource.AddressLine1",         "←", "string",   ""),
    _row("Resource", "engineer.city",                     "resource.City",                 "←", "string",   ""),
    _row("Resource", "engineer.postcode",                 "resource.PostCode",             "←", "string",   ""),
    _row("Resource", "engineer.post_code_area",           "resource.PostCodeArea",         "←", "string",   "Coverage zone for dispatch."),
    _row("Resource", "engineer.employee_number",          "resource.EmployeeNumber",       "←", "string",   ""),
    _row("Resource", "engineer.payroll_reference",        "resource.PayrollReference",     "←", "string",   ""),
    _row("Resource", "engineer.diary_colour",             "resource.DiaryColour",          "←", "string",   "Calendar tint."),
    _row("Resource", "engineer.team_name",                "resource.Team",                 "←", "string",   ""),
    _row("Resource", "engineer.team_id",                  "resource.SiconTeamID",          "←", "int",      ""),
    _row("Resource", "engineer.subcontractor_account_id", "resource.SubContractorAccountID","←", "int",     ""),
    _row("Resource", "engineer.contract_expiry_date",     "resource.ContractExpiryDate",   "←", "date",     ""),
    _row("Resource", "engineer.warehouse_name",           "resource.WarehouseName",        "←", "string",   ""),
    _row("Resource", "engineer.warehouse_id",             "resource.WarehouseID",          "←", "int",      ""),
    _row("Resource", "engineer.is_team_leader",           "resource.IsTeamLeader",         "←", "bool",     ""),
    _row("Resource", "engineer.is_leaver",                "resource.IsLeaver",             "←", "bool",     "Filtered out upstream."),
    _row("Resource", "engineer.is_project_manager",       "resource.IsProjectManager",     "←", "bool",     ""),
    _row("Resource", "engineer.is_shop_floor_user",       "resource.IsShopFloorUser",      "←", "bool",     ""),
    _row("Resource", "engineer.start_date",               "resource.StartDate",            "←", "date",     ""),

    # ════════════════════════════════════════════════════════════════
    # EQUIPMENT (Service WebAPI Equipment entity) — /api/v1/SiconService/Equipment
    # Added 2026-06 from the live Sicon Service WebAPI Bruno collection
    # (Equipment CRUD now exists in the Service plugin — full asset round-trip).
    # ════════════════════════════════════════════════════════════════
    _row("Equipment", "equipment.sicon_equipment_id",     "equipment.siconEquipmentId",          "↔", "int",      "Identity round-trip. Ignored on create, returned by POST."),
    _row("Equipment", "equipment.sage_item_id",           "equipment.itemId",                    "→", "int",      "Sage stock item identity (nullable)."),
    _row("Equipment", "equipment.display_name / description","equipment.description",            "↔", "string",   "Human-readable equipment description."),
    _row("Equipment", "equipment.serial_number",          "equipment.serialNumber",              "↔", "string",   "Machine serial — primary match key."),
    _row("Equipment", "equipment.asset_tag / id_number",  "equipment.idNumber",                  "↔", "string",   "Pulse asset tag / customer id number."),
    _row("Equipment", "equipment.warranty_expiry",        "equipment.warrantyExpiry",            "↔", "date",     "ISO date; drives warranty-to-maintenance opportunities."),
    _row("Equipment", "equipment.install_date",           "equipment.installDate",               "→", "date",     "ISO date."),
    _row("Equipment", "equipment.service_interval_unit",  "equipment.serviceIntervalMeasurement","→", "string",   "days / weeks / months / years."),
    _row("Equipment", "equipment.service_interval_value", "equipment.serviceIntervalDuration",   "→", "int",      "Interval count for the unit above."),
    _row("Equipment", "equipment.notes",                  "equipment.notes",                     "→", "text",     "Free-text asset notes."),
    _row("Equipment", "organization.id",                  "equipment.customerId",                "→", "ref",      "Org → Sicon customer mapping (nullable)."),
    _row("Equipment", "equipment.sicon_group_key",        "equipment.siconEquipmentGroupDbKey",  "↔", "ref",      "Sicon equipment-group db key."),
    _row("Equipment", "equipment.make / manufacturer",    "equipment.make",                      "↔", "string",   "Manufacturer."),
    _row("Equipment", "equipment.model / model_code",     "equipment.model",                     "↔", "string",   "Model / model code."),
    _row("Equipment", "equipment.last_service_date",      "equipment.lastServiceDate",           "↔", "date",     "Most recent completed service."),
    _row("Equipment", "equipment.next_service_date",      "equipment.nextServiceDate",           "↔", "date",     "Next planned service (PPM)."),
    _row("Equipment", "crm_links.crm_company_id",         "equipment.siconCrmCompanyId",         "→", "ref",      "Owning CRM company."),
    _row("Equipment", "crm_links.crm_person_id",          "equipment.siconCrmPersonId",          "→", "ref",      "Owning CRM person."),
    _row("Equipment", "crm_links.end_user_company_id",    "equipment.siconCrmEndUserCompanyId",  "→", "ref",      "End-user company (differs from bill-to)."),
    _row("Equipment", "crm_links.end_user_person_id",     "equipment.siconCrmEndUserPersonId",   "→", "ref",      "End-user person."),
    _row("Equipment", "site.sage_delivery_address_id",    "equipment.custDeliveryAddressDbKey",  "→", "ref",      "Sage delivery-address join for the asset location."),
    _row("Equipment", "site.sicon_sub_location_id",       "equipment.siconSubLocationDbKey",     "↔", "ref",      "Floor / zone within the site."),
    _row("Equipment", "site.sicon_contact_key",           "equipment.siconContactDbKey",         "→", "ref",      "Site contact db key."),
    _row("Equipment", "equipment.analysis_codes[1-20]",   "equipment.analysisCode1-20",          "→", "string[]", "20 analysis-code slots (asset/site/tier joins & KPI signals)."),

    # ════════════════════════════════════════════════════════════════
    # METADATA LOOKUPS (Service WebAPI reference data — pulled, cached to config)
    # /api/v1/SiconService/CaseType | /Priority | /TrackingStatus
    # ════════════════════════════════════════════════════════════════
    _row("Metadata", "config.case_type_mapping{}",        "caseType.siSMCaseTypeId",             "←", "int",      "Lookup: Reactive/PPM/Project → numeric CaseTypeId."),
    _row("Metadata", "config.case_type_mapping{}.name",   "caseType.name",                       "←", "string",   "Denormalised case-type name."),
    _row("Metadata", "config.priority_mapping{}",         "priority.siSMPriorityId",             "←", "int",      "Lookup: low/medium/critical → numeric PriorityId."),
    _row("Metadata", "config.priority_mapping{}.name",    "priority.name",                       "←", "string",   "Denormalised priority name."),
    _row("Metadata", "config.tracking_status_mapping{}",  "trackingStatus.siSMTrackingStatusId", "←", "int",      "Lookup: workflow_state → numeric TrackingStatusId."),
    _row("Metadata", "config.tracking_status_mapping{}.name","trackingStatus.name",              "←", "string",   "Denormalised tracking-status name."),

    # ════════════════════════════════════════════════════════════════
    # Entity-scoped fills (2026-06) — fields present on specific Service
    # requests that need their own per-entity Pulse mapping (no cross-entity).
    # ════════════════════════════════════════════════════════════════
    _row("TrackingNote", "note.message",                  "note.note",                     "→", "text",   "Note body text."),
    _row("TrackingNote", "note.sicon_note_id",            "note.siSMCaseTrackingNoteId",   "↔", "int",    "Tracking-note id."),
    _row("TrackingNote", "note.status",                   "note.status",                   "↔", "string", "Tracking-status name carried on the note."),
    _row("TrackingNote", "note.case_tracking_status_id",  "note.statusId",                 "↔", "int",    "Tracking-status id applied by the note."),
    _row("TrackingNote", "note.sicon_appointment_id (via linked Pulse appointment)", "note.appointmentId", "→", "int", "Resolve the note's linked Pulse appointment and send its appt.sicon_appointment_id here."),
    _row("Appointment",  "appt.sicon_case_id",            "appt.siSMCaseId",               "↔", "int",    "Parent case link on the appointment."),
    _row("Appointment",  "appt.work_briefing / description", "appt.description",           "→", "text",   "Appointment description / work briefing."),
    _row("Case",         "issue.created_by",              "case.createdBy",                "←", "string", "Sage user who created the case (read-back)."),

    # ════════════════════════════════════════════════════════════════
    # CUSTOMER / ORGANISATION — handled by integration ops, not auto-synced
    # ════════════════════════════════════════════════════════════════
    _row("Customer", "organization.id",                   "customer.Id",                   "↔", "ref",      "Two-way map maintained by integration ops."),
    _row("Customer", "organization.name",                 "customer.Name",                 "→", "string",   "Push-only on first sync; manual edits live in Sicon thereafter."),
]


@router.get("/sicon/field-mapping")
async def get_sicon_field_mapping(user: dict = Depends(get_current_user)) -> dict:
    """Return the full Sicon field mapping table for the Master Admin
    Sicon panel. Master-admin only — this exposes integration internals."""
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")
    # Group by entity for the UI's tabbed/grouped table layout.
    grouped: dict[str, list[dict]] = {}
    for row in SICON_FIELD_MAPPING:
        grouped.setdefault(row["entity"], []).append(row)
    # Direction summary helps audit reviewers spot push-only entities.
    direction_summary: dict[str, dict[str, int]] = {}
    for entity, rows in grouped.items():
        counts = {"→": 0, "←": 0, "↔": 0}
        for r in rows:
            counts[r["direction"]] = counts.get(r["direction"], 0) + 1
        direction_summary[entity] = counts
    return {
        "mappings": SICON_FIELD_MAPPING,
        "grouped": grouped,
        "total": len(SICON_FIELD_MAPPING),
        "entities": list(grouped.keys()),
        "direction_summary": direction_summary,
        "version": "iter-216h7",
        "revision": "consolidated-2026-06",
        "source_of_truth": "/app/integrations/sicon/",
    }
