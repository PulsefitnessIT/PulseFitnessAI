> **📋 Status — Iter 220ea·18 (Feb 2026)**
>
> **Canonical hand-over is `INTEGRATION_FIELD_MAPPING.md` §33.** This
> file is the partner-facing **completion-evidence pack** (coverage
> counts, test suites, change log). Hand-over package status unchanged:
> code path complete + tested against mocked Sicon endpoints, awaiting
> partner credentials from Pulse IT. The
> `/master-admin/integrations → Sicon` mapping panel is mobile-friendly
> (iter 216h229).
>
> Go-live is the **per-org `enabled=true` flip** on the Sicon config
> (valid Basic-auth credentials + `companyId`) — no redeploy. *(The
> legacy `SICON_LIVE_MODE` / `SICON_API_KEY` env flip in older revisions
> is superseded — see §33 / spec §6.1.)*

---


# Sicon Integration — Proof of Completion

**Document for hand-over to the Sicon partner team**
Prepared by the GymAxis engineering team.
Last refreshed: Iter 216h7 (May 2026).

---

## 1. Executive summary

GymAxis has implemented a deep, bi-directional integration with the Sicon Service WebAPI (R260200c). This document is the definitive snapshot of what is shipped, where the field mappings live, and which Sicon capabilities we currently consume.

**Coverage by Sicon entity:**

| Sicon entity | Wire fields mapped | Direction(s) |
|---|---|---|
| Service Case | 55 | ↔ push + pull, including AnalysisField1-20, full Location & SubLocation, Equipments[] |
| Service Contract (header) | 13 + 21 spare slots (7 text + 7 numeric + 7 date) | ↔ |
| Contract Line | 50 (with CLAnalysisCode1-15 wired out of 150 available) | → push (full); ← pull via case enrichment |
| Tracking Note | 10 (including GPS lat/long, appointment link, customer/engineer visibility flags) | ↔ |
| Appointment | 21 (split into scheduling + completion; signatures + GPS arrival/departure) | ↔ |
| Time Booking | 5 | ↔ |
| Resource / Engineer | 25 | ← pull (nightly directory refresh) |
| Customer / Organisation | 2 (identity + name) | ↔ |

**Total wire fields actively used: ~200**
(Up from 27 documented in the previous mapping-table revision — iter-221.)

**Auditable mapping table**: served by `GET /api/sicon/field-mapping` and rendered in the **Master Admin → Sicon → Mapping** panel. Source: [`backend/routes/sicon_mapping.py`](../backend/routes/sicon_mapping.py).

---

## 2. API client coverage

All Sicon endpoints listed in spec sections §3 and §6 are wrapped in [`backend/utils/sicon_client.py`](../backend/utils/sicon_client.py). The client class `SiconClient` exposes:

### Cases (§3.1, §6.2)
- `ping()` — connectivity check
- `get_case(case_id)` / `get_case_by_reference(case_reference)`
- `create_case(case_data)` — primary create via R260200c
- `amend_case(case_data)`
- `list_cases_updated_since(since_iso)` — inbound delta poll

### Tracking statuses, priorities, case types (§3.5 lookups)
- `get_case_types()`
- `get_tracking_statuses()`
- `get_priorities()`

### Tracking notes (§3.4)
- `get_tracking_notes(case_id)`
- `create_tracking_note(case_id, note_data)`

### Appointments (§3.2)
- `get_appointment(appointment_id)`
- `get_appointments_for_case(case_id)`
- `create_appointment(appointment_data)`
- `update_appointment(appointment_id, appointment_data)` — for completion + amendments
- `delete_appointment(appointment_id)`

### Resources / Engineers
- `get_resources()` — full directory pull
- `get_resources_for_appointment(appointment_id)` — assignment lookup

### Time Bookings (§3.3)
- `get_time_bookings(appointment_id)`
- `create_time_booking(appointment_id, booking_data)`
- `update_time_booking(appointment_id, booking_id, booking_data)`

### Contracts
- `create_or_update_contract(contract_data)`
- `update_contract_customer_order_number(sicon_contract_id, customer_order_number)` — **Iter 216h7 — now exposed via `POST /api/sicon/update-contract-po/{contract_id}`** so finance can attach a PO post-creation without re-syncing the full contract.
- `post_contract_line(line_data)`
- `create_contract(contract_data)` / `update_contract(contract_id, contract_data)`

---

## 3. End-to-end orchestration

### Outbound (GymAxis → Sicon)

| Trigger | Endpoint | Worker | Behaviour on failure |
|---|---|---|---|
| Issue created in GymAxis | `POST /api/sicon/sync-case/{issue_id}` | `utils/sicon_outbox_worker.py` | Enqueued to `sicon_sync_queue` with exponential backoff. Retry surface in Master Admin → Sicon → Sync Queue. |
| Issue amended | `POST /api/sicon/amend-case/{issue_id}` | same | same |
| Note added | `POST /api/sicon/add-note/{issue_id}` | sync (fast path) | Failed notes captured to outbox. |
| Appointment created | `POST /api/sicon/create-appointment/{issue_id}` | sync | same |
| Contract pushed | `POST /api/sicon/sync-contract/{contract_id}` | sync | Outbox + audit log. |
| PO attached post-sync | `POST /api/sicon/update-contract-po/{contract_id}` *(Iter 216h7)* | sync | Outbox + audit log. |
| Tracking note (ad-hoc) | `POST /api/sicon/tracking-note` | sync | Outbox. |

### Inbound (Sicon → GymAxis)
- `POST /api/sicon/poll-updates` — manual trigger from the Master Admin UI.
- `utils/sicon_poller.py` — background poller (configurable cadence per-org via `sicon_settings.poll_interval_minutes`).
- Pulls cases updated since the last poll watermark; reverse-maps via `map_sicon_case_to_gymaxis` and writes deltas onto the GymAxis `issues` collection.
- Status transitions on the Sicon side are honoured immediately (e.g. Sicon-side close → GymAxis `issue.status = "resolved"`).

### Worker observability
- Every outbox attempt writes to `sicon_audit_log` (event_type, success bool, payload digest, user id).
- The Master Admin → Sicon → Audit panel renders the last 1000 events with filters.
- Failed outbox items show up in `sicon_sync_queue` with the original payload preserved for replay.

---

## 4. Field-level mapping — capability deep dive

### 4.1 Service Case — what we send

A single `create_case` call now carries up to **55 wire fields**, grouped as:

| Group | Fields | Notes |
|---|---|---|
| **Identity** | `SiSMCaseId`, `CaseNumber`, `CaseTypeID`, `CaseTypeName` | Both ID and denormalised name sent for Sicon-side search. |
| **Top-level** | `Description`, `Summary`, `CallDate`, `PriorityID`, `PriorityName` | |
| **Status** | `SiSMDocumentStatusID`, `SiSMDocumentStatusName`, `SiSMDocumentSubStatusID` | **Iter 216h7** — sub-status resolves from `issue.workflow_state` via a per-org `sub_status_mapping` (e.g. `awaiting_parts` → 4, `on_site` → 7). |
| **Contact** | `ContactName`, `ContactEmail`, `ContactPhoneNumber`, `CustomerReference`, `SLCustomerAccountID` | Caller details denormalised onto the case. |
| **Assignment** | `AssignedToSageUserID`, `InternalTeamID`, `ExternalTeamID`, `SiconContractID`, `SiconContractNumber`, `SiconContractLineID`, `SiconCRMPersonID`, `SiconCRMCompanyID`, `SiJcJobID` | CRM cross-links required on create per spec §6.2. |
| **Location** | `LocationPostalName`, `LocationAddressLine1-4`, `LocationCity`, `LocationCounty`, `LocationPostCode` | Full 8-field postal address per spec §3.1. |
| **SubLocation** | `SiconSubLocationID`, `CustDeliveryAddressID`, `Description`, `Comment` | Floor / zone within the site. |
| **Equipment** | `Equipments[]` array (SiconEquipmentID, ItemID, Name) **plus** flat `EquipmentIDs[]` fallback | Preferred over flat IDs per spec recommendation. |
| **AnalysisField1-8** | AI triage core: summary, severity, parts, issue_id, org_name, SLA category, PPM schedule, supplier token | Spec §10. |
| **AnalysisField9-20** | Extended: fault_code, machine_type, equipment make/model/install/warranty, source, reporter_role, **CSAT rating** | Phase A. |

### 4.2 Contract — what we send

| Block | Fields |
|---|---|
| Identity | `ContractID`, `ContractNumber`, `CustomerNumber` |
| Descriptions | `Description`, `SOPBillingDescription` |
| Order ref | `CustomerOrderNumber` (now amendable post-sync via `POST /api/sicon/update-contract-po`) |
| **Spare slots (Iter 216h7)** | `SpareText1-7` (already existed) **+** new `SpareNum1-7` **+** new `SpareDate1-7` |

The spare-slot resolver accepts two input shapes for backward compat:
- `contract.spare_text_map = ["renewal_strategy", ...]` — index-ordered key list.
- `contract.spare_num = {3: 5.5}` — direct slot override.

Both can coexist; direct overrides win.

### 4.3 Contract Line — what we send

50 fields per line, in 6 banks:

1. **Identity** (`SiconContractID`, `SiconContractLineID`, `ItemCode`, `SalesOrderDescription`, `InternalDescription`).
2. **Dates & price** (12 fields: start, end, quantity, unit price, SOP unit price, interval, amended fields, bill cover, order date, original start, annual unit cost).
3. **Renewal** (11 fields: quantity, unit price, frequency, interval, duration, extended flag, initial/extended/total duration, isRenewalUpdate flag, ReasonCode).
4. **Billing** (7 fields: invoice frequency value+interval, bill cover duration, advance/arrears qty, BillInArrears, ProRata, IsRolling flags).
5. **Discounts** (6 fields: 3 banks of percent+value).
6. **Supplier** (5 fields: visit frequency, who sold, PL supplier id, supplier code, supplier unit price).
7. **Analysis codes** (15 of 150 available slots wired — **Iter 216h7** added 11-15 for finance/governance):

| Slot | GymAxis source | Sicon purpose |
|---|---|---|
| CL1 | `line.tier` / `sla.tier` | SLA tier (Gold/Platinum/Silver) |
| CL2 | `sla.response_hours` | Response-hours target |
| CL3 | `sla.resolution_hours` | Resolution-hours target |
| CL4 | `sla.oos_credit_terms` | OOS credit terms |
| CL5 | `line.safety_critical` | YES/NO flag |
| CL6 | `line.asset_id` / `equipment_id` | Asset join key |
| CL7 | `line.site_id` | Site join key |
| CL8 | `line.ppm_frequency_override` | PPM cadence override |
| CL9 | `line.tender_reference` | Tender pack ref |
| CL10 | `line.renewal_notice_days` | Renewal notice (default 90) |
| **CL11** | `line.sla_penalty_band` | **Iter 216h7** — Penalty schedule e.g. `0/5/10/25%` |
| **CL12** | `line.kpi_breach_flag` | **Iter 216h7** — `OK` / `WARN` / `BREACH` (driven by GymAxis SLA worker) |
| **CL13** | `line.finance_approver_email` | **Iter 216h7** — Last amendment authoriser |
| **CL14** | `line.billing_cycle_override` | **Iter 216h7** — `annual` / `semi-annual` / `quarterly` |
| **CL15** | `line.holdback_pct` | **Iter 216h7** — Retention against final invoice |
| CL16-150 | `line.analysis_codes[]` | Caller-overrideable; 135 free slots for future use |

### 4.4 Tracking Note — what we send

10 wire fields, including **GPS proof-of-location** (`Latitude`, `Longitude`) — set by the GymAxis engineer portal when posting notes from-the-field. Visible-to-engineer / visible-to-customer flags are bi-directional. Notes can transition status atomically via `CaseTrackingStatusID`.

### 4.5 Appointment — what we send

21 fields split across **scheduling** (subject, briefing, type, employees, charge rate, label, confirmed, parent travel link) and **completion** (work-done description, further action, dual signatures, arrival + departure GPS, both acknowledgement flags). Forms the proof-of-work chain auditors expect for service-contract billing.

### 4.6 Time Booking — what we send

5 fields per booking: employee IDs, start/end, actual hours, charge rate. Wired into `POST /api/Service/Appointments/{id}/TimeBookings` — currently surfaced via the engineer-portal time-tracking module.

### 4.7 Resource / Engineer — what we pull

25 fields per resource — full HR-grade record (name parts, addresses, phone, payroll, team, leaver flag, team-leader/PM/shop-floor flags, contract expiry, warehouse). Pulled nightly into the GymAxis engineer directory and used for dispatch / coverage decisions.

---

## 5. What we currently do NOT consume (and why)

| Sicon capability | Status | Reason / next step |
|---|---|---|
| `EquipmentIDs[]` flat-only path | Sent as **fallback** alongside `Equipments[]` array | Spec recommends `Equipments[]`; we send both for compat. |
| `SiJcJobID` (Job Costing link) | Always sent `0` | JC module not yet integrated GymAxis-side. Easy to wire once costing schema lands. |
| CLAnalysisCode 16-150 | Free for caller-supplied overrides | 135 slots open for future SLA-engine signals. |
| SpareNum / SpareDate 1-7 on Contract Line | Header-only currently | Future iteration if Sicon spec confirms line-level spare bank exists. |
| Sage 200 ledger posting | Wired in `utils/sage_outbox_worker.py` but **MOCKED** pending live credentials | Cutover ready; awaits Sage 200 API key + endpoint URL from customer ops. |

---

## 6. Authentication, security, audit

- **Authentication**: HTTP Basic over TLS, per-org credentials stored encrypted at rest (`encrypt_value` / `decrypt_value` in `sicon_client.py` — Fernet symmetric).
- **Authorisation gates**: All `/api/sicon/*` mutation endpoints require GymAxis role `owner` or `manager` (`_require_owner_or_manager`).
- **Connectivity test**: `POST /api/sicon/test-connection` — returns latency + reachability + Sicon-reported company info.
- **Audit log**: every Sicon-touching operation writes a row to `sicon_audit_log` (timestamp, org, user, event_type/action, success, redacted detail).
- **Retry / outbox**: `sicon_sync_queue` collection. Failed operations preserve the full payload for human or automated replay. Exponential backoff capped at 6 attempts.
- **Mapping authority**: the field table in `routes/sicon_mapping.py` is the canonical reference. A drift-guard test (`test_iter_216h7_sicon_mapping_audit.py::test_mapping_covers_iter_216h7_extensions`) fails the build if a new wire field is shipped without a documentation row.

---

## 7. Test coverage

| Suite | Cases | Scope |
|---|---|---|
| `test_iter_216h7_sicon_mapping_audit.py` | 12 | Spare slots (text/num/date), CLAnalysisCode 11-15, sub-status state machine, mapping-table integrity, PO endpoint, drift guard. |
| `test_iter_216g_*.py` (Phase A) | (existing) | AnalysisField 9-20, Equipments array, SubLocation. |
| `test_iter_215_*_sicon.py` | (existing) | Core mappers, contract lines, tracking notes, appointments, time bookings. |

**Current run on preview: 40/40 iter-216h* tests passing.**

---

## 8. Change log

| Iter | Date | Headline |
|---|---|---|
| **216h7** | May 2026 | Mapping-table rewrite (27 → 175+ rows). SpareNum/SpareDate 1-7 on contract header. CLAnalysisCode 11-15 wired. Sub-status state machine via per-org workflow_state map. `update_contract_customer_order_number` exposed via REST. Drift-guard tests added. |
| 216g | Apr 2026 | Phase 2 online sign-up (welcome journey, abandoned cart recovery). |
| 221 (legacy) | Apr 2026 | First mapping table — 27 documented rows (now superseded). |
| 215m | Mar 2026 | AnalysisField 9-20 (equipment lineage + provenance + CSAT). Full Equipments[] array. SubLocation as object. SiSMDocumentSubStatusID introduced. |
| 215c | Feb 2026 | Initial outbox worker, sync queue, audit log. |
| 213a | Jan 2026 | First case mapper + R260200c create_case. |

---

## 9. Contact

For technical questions about this integration, contact the GymAxis engineering team via the Master Admin → Service Desk channel. For commercial / contractual questions, contact GymAxis customer ops.

Sicon API contract version: **R260200c**.
Mapping table version: **iter-216h7**.

---

*This document is auto-discoverable at `/app/docs/SICON_INTEGRATION_PROOF.md` and is regenerated each iteration that touches the Sicon surface area. Refer to commit history for the audit trail.*
