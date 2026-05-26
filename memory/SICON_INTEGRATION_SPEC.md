> **📋 Status — Iter 220m (May 26, 2026)**
>
> Still **P1 — waiting on live Sicon credentials** to switch from
> mocked endpoints to production. The integration code path, admin
> field-mapping UI (`/master-admin/integrations` → Sicon panel) and
> unit tests are all in place and stable. The companion
> `docs/SICON_INTEGRATION_PROOF.md` tracks the hand-over package
> for the Pulse IT / Sicon partner team.
>
> Recent operational context:
>
> - The 2026-05 Partner Engineer release (iter 220i → 220m) shipped
>   **independently** of Sicon — none of the Partner Engineer flow
>   blocks on Sicon being live. Operators can keep self-managing
>   parts/labour while we await credentials.
> - The admin field-mapping UI ships with its own horizontal-scroll
>   wrapper (iter 216h229 mobile audit) so the read-only mapping
>   table is usable on phones.
>
> No model / endpoint changes since v1.0 below; only awaiting
> credentials. Once Pulse IT returns with the keys, switching from
> the mocked adapter to the live one is a single env-var flip
> (`SICON_LIVE_MODE=true` + `SICON_API_KEY=…`).

---


# GymAxis AI x Sicon Service Integration Model
## Production-Ready Enterprise Integration Specification
### Version 1.0 | April 2026

---

# 1. ARCHITECTURE OVERVIEW

## System Roles

| System | Role | Owns |
|--------|------|------|
| GymAxis AI | Customer-facing portal, AI triage, KPI engine, PPM scheduling, supplier collaboration | Fault initiation, AI diagnosis, customer comms, KPIs, PPM schedules |
| Sicon Service (R260200c) | Service execution layer, engineer dispatch, time tracking, costing | Case lifecycle, appointments, engineer activity, time bookings, cost tracking |
| Sage 200 | Financial master | Customer accounts (SLCustomerAccountID), invoicing, contract billing |
| GymAxis CRM | Commercial operations | Deals, quotes, contract negotiation, tender responses |

## Integration Principle

GymAxis AI is the INITIATOR and INTELLIGENCE layer. Sicon Service is the EXECUTION layer. Neither system duplicates the other — they complement.

- GymAxis creates the service case from the customer's fault report + AI triage
- Sicon manages the case lifecycle: engineer dispatch, appointments, time booking, parts, completion
- GymAxis reads back from Sicon for KPI calculation, customer visibility, and performance reporting
- Sage 200 owns all financial data; Sicon routes financials to Sage

---

# 2. ENTITY MAPPING

| GymAxis Entity | Sicon Entity | Sicon API Resource | Relationship |
|---|---|---|---|
| Issue (Fault) | Service Case | `/api/service/cases` | 1:1 — GymAxis creates, Sicon manages lifecycle |
| Equipment | Equipment | `EquipmentIDs` on Service Case | 1:1 — GymAxis is display layer, Sicon/Sage owns master |
| Company (CRM) | Customer Account | `SLCustomerAccountID` | 1:1 — Sage owns, GymAxis CRM enriches |
| Site | Sub Location / Delivery Address | `SubLocation` on Service Case | 1:1 — GymAxis site maps to Sicon customer delivery address |
| Contract (CRM) | Service Contract | `SiconContractID` / `SiconContractNumber` | 1:1 — GymAxis CRM negotiates, Sicon activates |
| Engineer Visit | Appointment | `/api/Service/Appointments` | 1:many per case — Sicon owns completely |
| Time Booking | Time Booking | `/api/Service/Appointments/{id}/TimeBookings` | 1:many per appointment — Sicon owns |
| Fault Timeline Event | Tracking Note | `/api/Service/Cases/{caseID}/TrackingNotes` | Many per case — bi-directional |
| Fault Type | Case Type | `/api/service/case-types` | Lookup — Sicon master, GymAxis references |
| Fault Status | Document Status | `SiSMDocumentStatusID` | Sicon owns — GymAxis reads |
| Priority | Priority | `PriorityID` / `PriorityName` | Sicon master — mapped from GymAxis severity |
| Tracking Status | Case Tracking Status | `/api/service/case-tracking-statuses` | Sicon master — GymAxis reads |
| Engineer | Appointment Resource (Employee) | `/api/service/appointments/resources` | Sicon/Sage owns — GymAxis reads |

---

# 3. FIELD MAPPING TABLES

## 3.1 SERVICE CASE (Issue → Sicon Case)

| GymAxis Field | Sicon Field | Type | Source of Truth | Sync Direction | Trigger |
|---|---|---|---|---|---|
| `id` | — | string | GymAxis | — | Internal reference only |
| — | `SiSMCaseId` | int64 | Sicon | Sicon → GymAxis | On case creation response |
| — | `CaseNumber` | string | Sicon | Sicon → GymAxis | On case creation response |
| `issue_description` | `Description` | string | GymAxis | GymAxis → Sicon | Real-time on create |
| `machine_type` + `serial_number` | `Summary` | string | GymAxis | GymAxis → Sicon | Real-time on create |
| `created_at` | `CallDate` | datetime | GymAxis | GymAxis → Sicon | Real-time on create |
| `severity` | `PriorityID` / `PriorityName` | int64/string | GymAxis (initial), Sicon (ongoing) | GymAxis → Sicon | On create; Sicon can re-prioritise |
| `fault_type` | `CaseTypeID` / `CaseTypeName` | int64/string | GymAxis | GymAxis → Sicon | Real-time on create |
| `status` | `SiSMDocumentStatusID` / `SiSMDocumentStatusName` | int64/string | **Sicon** | Sicon → GymAxis | Polled or webhook |
| `site_name` + address | `LocationPostalName`, `LocationAddressLine1-4`, `LocationCity`, `LocationCounty`, `LocationPostCode` | string | GymAxis | GymAxis → Sicon | On create |
| `created_by_name` | `ContactName` | string | GymAxis | GymAxis → Sicon | On create |
| User email | `ContactEmail` | string | GymAxis | GymAxis → Sicon | On create |
| User phone | `ContactPhoneNumber` | string | GymAxis | GymAxis → Sicon | On create |
| Equipment `serial_number` | `EquipmentIDs` (array of int64) | int64[] | **Sicon** (equipment master) | GymAxis → Sicon (by lookup) | On create |
| Company Sage ref | `SLCustomerAccountID` | int64 | **Sage** | GymAxis → Sicon (from CRM) | On create |
| Company Sage ref | `CustomerReference` | string | **Sage** | GymAxis → Sicon (fallback) | On create |
| Site | `SubLocation.SiconSubLocationID` | int64 | Sicon | GymAxis → Sicon (by lookup) | On create |
| Contract `sicon_contract_id` | `SiconContractID` | int64 | **Sicon** | GymAxis → Sicon | On create (if under contract) |
| Contract `sicon_contract_number` | `SiconContractNumber` | string | Sicon | GymAxis → Sicon (fallback) | On create |
| — | `AssignedToSageUserID` | int64 | **Sicon** | Sicon → GymAxis | Sicon assigns engineer |
| — | `AssignedToSageUser` | string | Sicon | Sicon → GymAxis | Read-back |
| — | `InternalTeamID` / `InternalTeam` | int64/string | **Sicon** | Sicon → GymAxis | On case read-back |
| — | `ExternalTeamID` / `ExternalTeam` | int64/string | **Sicon** | Sicon → GymAxis | On case read-back |
| AI triage summary | `AnalysisField1` | string | GymAxis | GymAxis → Sicon | On create |
| AI triage severity | `AnalysisField2` | string | GymAxis | GymAxis → Sicon | On create |
| AI recommended parts | `AnalysisField3` | string | GymAxis | GymAxis → Sicon | On create |
| GymAxis Issue ID | `AnalysisField4` | string | GymAxis | GymAxis → Sicon | On create (cross-reference) |
| GymAxis org name | `AnalysisField5` | string | GymAxis | GymAxis → Sicon | On create |
| `sla_category` | `AnalysisField6` | string | GymAxis | GymAxis → Sicon | On create |
| — | `SiconCRMCompanyID` | int64 | Sicon CRM | GymAxis → Sicon | On create (if mapped) |
| — | `SiconCRMPersonID` | int64 | Sicon CRM | GymAxis → Sicon | On create (if mapped) |
| — | `SiJcJobID` | int64 | Sicon | Pass 0 on create | — |

### Priority Mapping

| GymAxis Severity | Sicon Priority Name | Sicon Priority ID |
|---|---|---|
| `safety_critical` | "Safety Critical" or "Emergency" | Lookup on first sync |
| `critical` | "Critical" / "Urgent" | Lookup |
| `high` | "High" | Lookup |
| `medium` | "Medium" / "Normal" | Lookup |
| `low` | "Low" | Lookup |

### Case Type Mapping

| GymAxis `fault_type` | Sicon Case Type Name | `IsPreventativeMaintenance` |
|---|---|---|
| `standard` | "Reactive" / "Breakdown" | false |
| `safety_critical` | "Safety Critical" | false |
| `ppm` | "Preventative Maintenance" | true |

---

## 3.2 APPOINTMENTS (Engineer Visits)

**Source of Truth: Sicon** — GymAxis reads appointment data for display and KPI calculation.

| GymAxis Field | Sicon Field | Type | Direction |
|---|---|---|---|
| — | `SiconAppointmentID` | int64 | Sicon → GymAxis |
| `engineer_assigned_at` | `ScheduledStartDate` | datetime | Sicon → GymAxis |
| `work_completed_at` | `ScheduledEndDate` | datetime | Sicon → GymAxis |
| — | `AppointmentType` | enum: Other/Work/Travel | Sicon → GymAxis |
| `engineer_notes` | `WorkDoneDescription` | string | Sicon → GymAxis |
| — | `FurtherAction` | string | Sicon → GymAxis |
| — | `ArrivalSignee` | string | Sicon → GymAxis |
| — | `DepartureSignee` | string | Sicon → GymAxis |
| `engineer_arrived_at` (GPS lat) | `ArrivalLatitude` / `ArrivalLongitude` | decimal | Sicon → GymAxis |
| — | `DepartureLatitude` / `DepartureLongitude` | decimal | Sicon → GymAxis |
| — | `AppointmentComplete` | boolean | Sicon → GymAxis |
| — | `Confirmed` | boolean | Sicon → GymAxis |
| — | `EmployeeIDs` | int64[] | Sicon → GymAxis |
| — | `WorkBriefing` | string | GymAxis → Sicon (AI triage as briefing) |
| — | `Subject` | string | GymAxis → Sicon |

---

## 3.3 TIME BOOKINGS (Labour)

**Source of Truth: Sicon** — read-only for GymAxis (used for KPI: actual hours worked).

| GymAxis KPI Field | Sicon Field | Type | Direction |
|---|---|---|---|
| `work_started_at` | `StartDate` | datetime | Sicon → GymAxis |
| `work_completed_at` | `EndDate` | datetime | Sicon → GymAxis |
| Downtime hours calc | `ActualHours` | decimal | Sicon → GymAxis |
| — | `ChargeRate` | int64 | Sicon only (costing) |
| — | `EmployeeIDs` | int64[] | Sicon → GymAxis |

---

## 3.4 TRACKING NOTES (Case Timeline)

**Bi-directional** — both systems post notes to the case timeline.

| GymAxis Field | Sicon Field | Type | Direction |
|---|---|---|---|
| Timeline event `message` | `TrackingNote` | string | Bi-directional |
| Timeline event `timestamp` | `Time` | datetime | Bi-directional |
| Timeline event `by` | `User` / `CreatedBy` | string | Bi-directional |
| — | `CaseTrackingStatusID` | int64 | Sicon → GymAxis |
| — | `Status` / `StatusID` | string/int | Sicon → GymAxis |
| — | `VisibleToEngineer` | boolean | Sicon → GymAxis |
| — | `VisibleToCustomer` | boolean | Sicon → GymAxis |
| — | `InternalTeamID` / `InternalTeam` | int64/string | Sicon → GymAxis |
| — | `CaseOwner` / `CaseOwnerID` | string/int | Sicon → GymAxis |
| — | `SiconAppointmentID` | int64 | Link to appointment |
| GPS location | `Longitude` / `Latitude` | decimal | Sicon → GymAxis |

### GymAxis → Sicon Note Triggers

| GymAxis Event | Tracking Note Content |
|---|---|
| Fault created | "Case created via GymAxis AI. AI Diagnosis: {summary}" |
| AI triage completed | "AI Triage: {diagnosis}. Recommended: {steps}" |
| Supplier contacted | "Supplier {name} contacted via GymAxis portal" |
| Supplier responded | "Supplier response received: {message}" |
| Engineer visit scheduled (supplier) | "Supplier scheduled engineer visit: {date}" |
| Status changed in GymAxis | "Status updated to {status} by {user}" |
| Photo/video attached | "Media attachment added by {user}" |

---

## 3.5 APPOINTMENT RESOURCES (Engineers)

**Source of Truth: Sicon/Sage** — read-only for GymAxis.

| GymAxis Display Field | Sicon Field | Type |
|---|---|---|
| Engineer Name | `FullName` | string |
| First Name | `FirstName` | string |
| Surname | `Surname` | string |
| Employee ID | `SIJCEMPID` | int64 |
| Team | `Team` | string |
| Team ID | `SiconTeamID` | int64 |
| Email | `Email` | string |
| Mobile | `MobileNo` | string |
| Postcode Area | `PostCodeArea` | string |
| Is Team Leader | `IsTeamLeader` | boolean |
| Start Date | `StartDate` | datetime |

---

## 3.6 CONTRACTS

**GymAxis CRM creates and negotiates. Sicon activates and executes.**

| GymAxis CRM Field | Sicon Field | Type | Direction |
|---|---|---|---|
| `contract_number` | `SiconContractNumber` | string | GymAxis → Sicon (on activation) |
| `sicon_contract_id` (stored) | `SiconContractID` | int64 | Sicon → GymAxis (on creation response) |
| `company_id` → Sage ref | `CustomerId` (via Sage SLCustomerAccountID) | int64 | GymAxis → Sicon |
| `start_date` | `StartDate` | date | GymAxis → Sicon |
| `end_date` | `EndDate` | date | GymAxis → Sicon |
| `tier` (Gold/Platinum etc.) | Service Level / SLA Profile | string | GymAxis → Sicon |
| `sla.response_hours` | SLA Response Target | hours | GymAxis → Sicon |
| `sla.resolution_hours` | SLA Resolution Target | hours | GymAxis → Sicon |
| `annual_value` | Contract Value | decimal | GymAxis → Sage (via Sicon) |
| `status` (active/expired) | Contract Status | string | Bi-directional |

### Contract Lifecycle

1. GymAxis CRM: Sales team creates contract, configures SLA, gets customer signature
2. GymAxis CRM → Sicon: On status change to "Active", push contract to Sicon
3. Sicon: Activates service contract, links to customer account
4. GymAxis: When creating a service case, includes `SiconContractID` so Sicon knows coverage
5. GymAxis CRM: On renewal, creates new contract version, pushes new dates to Sicon

---

## 3.7 CUSTOMER / SITE

**Source of Truth: Sage 200** (master customer account). GymAxis CRM enriches with commercial data.

| GymAxis Field | Sicon/Sage Field | Direction |
|---|---|---|
| CRM `company_name` | Sage Customer Account Name | Sage → GymAxis (initial), GymAxis reads |
| CRM `company_id` | — | GymAxis internal only |
| `sage_customer_id` | `SLCustomerAccountID` | Sage → GymAxis CRM (stored for case creation) |
| Site `name` | Sub Location `Description` | GymAxis → Sicon (on case) |
| Site `address` | `LocationAddressLine1-4`, `LocationCity`, `LocationPostCode` | GymAxis → Sicon (on case) |
| `sicon_sub_location_id` | `SubLocation.SiconSubLocationID` | Sicon → GymAxis (stored for case creation) |

---

# 4. SYNC RULES

## 4.1 Real-Time (Event-Driven)

| Event | Source | Target | Action | API Call |
|---|---|---|---|---|
| Fault logged in GymAxis | GymAxis | Sicon | Create Service Case | `POST /api/ServiceCase/CreateNewCase` |
| AI triage completed | GymAxis | Sicon | Add Tracking Note with AI summary | `POST /api/Service/Cases/{caseID}/TrackingNotes` |
| Supplier schedules visit | GymAxis | Sicon | Create Appointment | `POST /api/Service/Appointments` |
| GymAxis user adds note | GymAxis | Sicon | Create Tracking Note | `POST /api/Service/Cases/{caseID}/TrackingNotes` |
| Contract activated in CRM | GymAxis CRM | Sicon | Create/Update Service Contract | Sicon Contract API |
| Case status changes in Sicon | Sicon | GymAxis | Update issue status + timeline | Poll `GET /api/service/cases/{id}` |
| Appointment completed in Sicon | Sicon | GymAxis | Update KPI timestamps | Poll appointments endpoint |
| Engineer adds tracking note | Sicon | GymAxis | Add to GymAxis timeline | Poll tracking notes |

## 4.2 Scheduled (Batch)

| Job | Frequency | Description |
|---|---|---|
| Case status sync | Every 5 minutes | Poll all open Sicon cases linked to GymAxis, update statuses |
| Appointment sync | Every 5 minutes | Poll appointments for open cases, update engineer timestamps |
| Tracking notes sync | Every 5 minutes | Pull new tracking notes since last sync |
| Engineer list refresh | Daily | Refresh appointment resources list |
| Case type / Priority / Status refresh | Daily | Refresh lookup tables from Sicon |
| KPI recalculation | Every 15 minutes | Recalculate KPIs using latest Sicon data |

---

# 5. CONFLICT RESOLUTION

| Data Domain | Winner | Reason |
|---|---|---|
| Service Case Status | **Sicon** | Sicon is the execution layer; engineers update status there |
| Case Priority (after creation) | **Sicon** | Service coordinator may reprioritise based on engineer assessment |
| Customer/Company details | **Sage 200** | Sage is the financial master; GymAxis CRM enriches but doesn't override |
| Site address | **GymAxis** | Customer-facing portal has the most up-to-date site information |
| Contract terms (SLA, dates) | **GymAxis CRM** | CRM negotiates and manages contract lifecycle |
| Engineer assignment | **Sicon** | Sicon's scheduler manages engineer dispatch |
| Financial data (invoices, costs) | **Sage 200** | Sage is the accounting system of record |
| AI triage data | **GymAxis** | Only GymAxis has the AI engine |
| Fault description (initial) | **GymAxis** | Customer logs the fault in GymAxis |
| Work done description | **Sicon** | Engineer records work done in Sicon |
| Parts used | **Sicon** | Sicon tracks parts and stock |
| Tracking notes | **Originating system** | Notes from GymAxis tagged as "GymAxis"; notes from Sicon tagged as "Sicon" |

---

# 6. API DESIGN

## 6.1 Authentication

Sicon WebAPI uses **API Key + Base URL** authentication:

```
Base URL: https://{customer-instance}.sicon.co.uk/api/
Headers:
  - Authorization: Bearer {SICON_API_KEY}
  - Content-Type: application/json
  - CompanyId: {SAGE_COMPANY_ID} (optional, for multi-company)
```

## 6.2 GymAxis Integration Endpoints

### Outbound (GymAxis → Sicon)

| GymAxis Endpoint | Sicon API Call | When |
|---|---|---|
| `POST /api/sicon/sync-case/{issue_id}` | `POST /api/ServiceCase/CreateNewCase` | User clicks "Push to Sicon" or auto on fault create |
| `POST /api/sicon/amend-case/{issue_id}` | `POST /api/ServiceCase/AmendCase` | When GymAxis fault is updated |
| `POST /api/sicon/add-note/{issue_id}` | `POST /api/Service/Cases/{caseID}/TrackingNotes` | When note/comment added in GymAxis |
| `POST /api/sicon/create-appointment/{issue_id}` | `POST /api/Service/Appointments` | When supplier schedules engineer via GymAxis |
| `POST /api/sicon/sync-contract/{contract_id}` | Sicon Contract API | When CRM contract goes Active |

### Inbound (Sicon → GymAxis)

| GymAxis Endpoint | Sicon Source | When |
|---|---|---|
| `POST /api/sicon/poll-updates` | Multiple GET endpoints | Scheduled every 5 minutes |
| `GET /api/sicon/case/{sicon_case_id}` | `GET /api/service/cases/{id}` | On-demand read-back |
| `GET /api/sicon/appointments/{sicon_case_id}` | Appointment resources | On-demand |
| `GET /api/sicon/engineers` | `GET /api/service/appointments/resources` | Daily refresh |
| `GET /api/sicon/case-types` | `GET /api/service/case-types` | Daily refresh |
| `GET /api/sicon/tracking-statuses` | `GET /api/service/case-tracking-statuses` | Daily refresh |

## 6.3 Error Handling

### Retry Strategy

| Error Type | Retry | Max Retries | Backoff |
|---|---|---|---|
| 500 Server Error | Yes | 3 | Exponential: 5s, 30s, 120s |
| 408 Timeout | Yes | 3 | Exponential: 10s, 60s, 300s |
| 401 Unauthorized | No | 0 | Alert admin — API key may have expired |
| 400 Bad Request | No | 0 | Log error with full payload for manual review |
| 404 Not Found | No | 0 | Log — entity may have been deleted in Sicon |
| Network Error | Yes | 5 | Exponential: 5s, 15s, 45s, 120s, 300s |

### Failure Queue

All failed sync operations are written to `sicon_sync_queue` collection:

```
{
  "id": "uuid",
  "operation": "create_case" | "amend_case" | "add_note" | "create_appointment",
  "entity_type": "issue" | "contract" | "note",
  "entity_id": "gymaxis-issue-id",
  "payload": { ... full request body ... },
  "error": "error message",
  "http_status": 500,
  "attempts": 2,
  "max_attempts": 3,
  "next_retry_at": "2026-04-17T14:30:00Z",
  "created_at": "2026-04-17T14:00:00Z",
  "resolved_at": null,
  "resolved_by": null
}
```

---

# 7. UI REQUIREMENTS

## Per-Record Sync Status

Every GymAxis issue/contract that maps to Sicon displays:

| UI Element | Data |
|---|---|
| Sync Status Badge | "Synced" (green) / "Pending" (amber) / "Failed" (red) / "Not Synced" (gray) |
| Sicon Case Number | `CaseNumber` from Sicon (displayed as link) |
| Last Sync Time | Timestamp of last successful sync |
| Error Detail | If failed, show error message with "Retry" button |
| Manual Re-sync Button | Triggers immediate push to Sicon |
| Sicon Status | Current `SiSMDocumentStatusName` from Sicon |
| Engineer Assigned | `AssignedToSageUser` from Sicon |
| Next Appointment | From appointments data |

---

# 8. WORKFLOW EXAMPLES

## Workflow 1: Fault Logged → Engineer Attends → Closed

```
1. Gym staff logs fault in GymAxis (Pulse Pro)
   → GymAxis creates Issue with AI triage
   
2. GymAxis pushes to Sicon:
   POST /api/ServiceCase/CreateNewCase
   - Description = fault description
   - Summary = "{machine_type} - {serial_number}"
   - PriorityName = mapped from GymAxis severity
   - CaseTypeName = "Reactive"
   - SLCustomerAccountID = from CRM company record
   - AnalysisField1 = AI triage summary
   - AnalysisField4 = GymAxis Issue ID
   
3. Sicon returns SiSMCaseId + CaseNumber
   → GymAxis stores sicon_case_id and sicon_case_number on the issue

4. GymAxis adds AI triage as Tracking Note:
   POST /api/Service/Cases/{caseID}/TrackingNotes
   - TrackingNote = "AI Diagnosis: {diagnosis}. Steps: {steps}. Parts: {parts}"
   - CreatedBy = "GymAxis AI"

5. Sicon service coordinator assigns engineer and creates Appointment
   (Done within Sicon — GymAxis polls to detect)

6. GymAxis 5-min poll detects appointment:
   → Updates issue: engineer_assigned_at, engineer name
   → Adds timeline entry: "Engineer {name} assigned, visit scheduled {date}"

7. Engineer arrives on site, logs arrival in Sicon
   → Creates Time Booking with StartDate
   → GymAxis poll detects: updates engineer_arrived_at

8. Engineer completes work, marks appointment complete in Sicon
   → WorkDoneDescription populated
   → AppointmentComplete = true
   → Time Booking EndDate populated

9. GymAxis poll detects completion:
   → Updates issue: work_completed_at, engineer_notes, status = "resolved"
   → Adds timeline: "Case resolved by {engineer}. Work done: {description}"
   → KPI engine recalculates: downtime hours, response time
```

## Workflow 2: Contract Created → Service Activated

```
1. GymAxis CRM: Sales team creates contract for "Tottenham Green"
   - Type: Service, Tier: Gold, SLA: 4hr response / 24hr resolution
   - Links to company (Sage CustomerAccountID stored)
   
2. Contract goes through approval workflow in GymAxis CRM
   
3. Customer signs contract (digital signature in GymAxis)
   → Status changes to "Active"
   
4. GymAxis pushes contract to Sicon:
   - SiconContractNumber = GymAxis contract_number
   - CustomerID = Sage SLCustomerAccountID
   - StartDate, EndDate from contract
   - Service Level = "Gold"
   
5. Sicon returns SiconContractID
   → GymAxis stores sicon_contract_id on the contract record
   
6. All future fault reports for this customer now include:
   - SiconContractID on case creation
   - SLA rules applied automatically in Sicon
```

## Workflow 3: Engineer Flags Replacement → CRM Opportunity

```
1. Engineer inspects equipment during service visit
   → Adds Tracking Note in Sicon: "Equipment BER - recommend replacement"
   → Sets specific tracking status indicating BER
   
2. GymAxis 5-min poll picks up the tracking note and status
   → Updates GymAxis issue with BER flag
   → Timeline entry: "Engineer flagged equipment as Beyond Economical Repair"
   
3. GymAxis Integration Hub fires event: "engineer_ber_flagged"
   → Target: CRM
   → Action: Creates replacement opportunity in CRM pipeline
   - Company: from the service case customer
   - Title: "Equipment Replacement - {machine_type} at {site}"
   - Value: estimated from equipment catalog
   - Stage: "Qualification"
   
4. CRM sales team picks up the opportunity
   → Full commercial cycle: quote → negotiate → contract → fulfil
```

---

# 9. CONNECTIVITY CHECK

Before any sync, GymAxis verifies Sicon is available:

```
GET /api/SMConnectivity/Ping
Expected: 200 OK "Pong"
```

If Ping fails, all sync operations queue to the failure queue and retry on the next cycle.

---

# 10. ANALYSIS FIELDS USAGE

Sicon provides 20 free-text `AnalysisField` slots on every case. GymAxis uses these for cross-system data:

| Field | Usage | Example |
|---|---|---|
| `AnalysisField1` | AI Triage Diagnosis Summary | "Motor bearing failure suspected..." |
| `AnalysisField2` | AI Severity Assessment | "HIGH - immediate attention required" |
| `AnalysisField3` | AI Recommended Parts | "Drive belt, motor bearing, lubricant" |
| `AnalysisField4` | GymAxis Issue ID (cross-reference) | "614475b8-xxxx-xxxx-xxxx" |
| `AnalysisField5` | GymAxis Organisation Name | "Tottenham Green Leisure Centre" |
| `AnalysisField6` | SLA Category | "Gold - 4hr response" |
| `AnalysisField7` | GymAxis PPM Schedule ID (if PPM) | "e8044e53-xxxx" |
| `AnalysisField8` | Supplier Case Token (if supplier involved) | "abc123-token" |
| `AnalysisField9-20` | Reserved for future use | — |

---

*Document generated April 2026 — GymAxis AI x Sicon Service Integration Specification v1.0*
