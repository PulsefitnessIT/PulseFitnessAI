# Pulse Fitness AI × Sicon / Sage 200 — Integration Brief

**Prepared for:** Sicon Integration / Partner Team
**Prepared by:** Pulse Fitness AI (pulsefitness.ai)
**Date:** 29 June 2026
**Status:** For review — confirmation requested on the open items in §6

---

## 1. Executive Summary

Pulse Fitness AI is onboarding our customer base onto the platform and needs to migrate and
then continuously synchronise three data domains from Sicon / Sage 200:

1. **Customers** (Sage 200 customer accounts + CRM companies/contacts)
2. **Equipment** (installed, serial-numbered assets under service)
3. **Service Contracts** (maintenance/SLA cover)

**Scale:** ~**5,000 customers** and ~**300,000 pieces of equipment**.

We have reviewed six published Sicon/Sage WebAPI specifications (listed in §2). Our connection and
authentication layer is **built and tested** against the documented Basic-auth + `companyId` model.

**Headline finding:** Two of the three domains are achievable today with the published APIs, but
**one critical capability is missing from every published spec we have**:

> ⚠️ **There is no published endpoint to list/read the installed Equipment register (serial-numbered
> service assets).** This is our single largest data domain (300k records) and the primary blocker to a
> fully automated migration. **§6 contains the specific questions we need Sicon to answer.**

| Domain | Volume | Read/List API available? | Verdict |
|---|---|---|---|
| Customers | ~5,000 | ✅ Yes (Sage Core + Sicon CRM) | Ready to automate |
| Contracts | (per customer) | 🔴 No (push-only API) | Manual/export interim; needs read API for sync |
| **Equipment** | **~300,000** | 🔴 **No list endpoint found** | **Blocked — Sicon input required** |

---

## 2. APIs Reviewed

| # | Specification | Scope | Relevance |
|---|---|---|---|
| 1 | `Service.R260200c` | Service Management — cases, appointments, tracking notes, resources | Operational case sync; equipment only embedded on cases |
| 2 | `Contracts.R260200c` | Service Contracts | **Push-only** (4× POST, no GET) |
| 3 | `CRM.R221200c` | Sicon CRM — companies, people, opportunities, tenders | Customer/contact read (paged) |
| 4 | `CoreWebAPI.R260200c` | Sage 200 Core — customers, suppliers, stock, SOP, ledgers | Customer master read (incremental) |
| 5 | `Projects.R260200c` | Sicon Project/Job Costing (SIJC) | Jobs/labour/budgets — no equipment |
| 6 | Sicon WebAPI Auth Guide | Basic auth + companyId | Connection model confirmed |

---

## 3. Connection & Authentication (confirmed)

- **Method:** HTTP Basic over TLS — `Authorization: Basic base64(username:password)` (ISO-8859-1).
- **Company scoping:** `companyId` query parameter on every request.
- **Credential source (per customer/company):**
  Sage 200 client → **Sicon WebAPI → Maintain WebAPI Users**; `companyId` from **Sage System Administration**.
- **Pulse Fitness storage:** credentials are **Fernet-encrypted at rest**, per-organisation, never exposed
  to the browser; all calls are server-to-server.

**What we need from each customer at go-live:** Base URL · WebAPI username/password · Sage `companyId`.

---

## 4. Entity Mapping

### 4.1 Customers — ✅ READY

**Source of truth: Sage 200** (customer account); enriched by Sicon CRM.

| Pulse Fitness field | Sicon/Sage field | Source API | Direction |
|---|---|---|---|
| `company_name` | Customer Account Name / `Name` | Core `GET /api/Customer/GetCustomers` | Sage → Pulse |
| `sage_customer_id` | `SLCustomerAccountID` | Core / CRM `Companies/SL/{slCustomerAccountid}` | Sage → Pulse |
| `sage_customer_reference` | Customer `Reference` | Core `GetCustomers?Reference=` | Sage → Pulse |
| `sicon_company_id` | `SiconCRMCompanyID` | CRM `GET /api/CRM/Companies` | Sicon → Pulse |
| address / postcode / phone | Customer + delivery addresses | Core `CustomerDeliveryAddress`, CRM `Addresses` | Sage → Pulse |
| contacts (people) | Customer Contacts / CRM People | Core `Customers/Contacts`, CRM `GET /api/CRM/People` | Sage/Sicon → Pulse |
| VAT / currency / payment terms / credit limit / account status | Customer financial fields | Core Customer | Sage → Pulse |

**Incremental sync:** Core `GetCustomers` supports **`AmendedAfterDate`** → delta pulls (only changed
records). CRM list endpoints support `page` / `pageSize` pagination. Both scale cleanly to 5,000.

### 4.2 Equipment — 🔴 BLOCKED (no read/list API found)

**Intended model:** Pulse Fitness is the display + fault-initiation layer; Sicon/Sage owns the master.

| Pulse Fitness field | Expected Sicon field | Status |
|---|---|---|
| `sicon_equipment_id` | `SiconEquipmentID` | Schema exists in `Service` spec **but only embedded on a Case** (`Equipments[]` / `EquipmentIDs[]`) |
| `serial_number` | (equipment identifier) | No list/search endpoint |
| `sage_item_id` | `ItemID` (stock link) | Stock catalogue only (SKU, not installed asset) |
| `machine_type` / make / model | Equipment `Name` / item attributes | No standalone read |
| install / warranty / contract cover | — | No standalone read |

**Problem:** Across `Service`, `CRM`, `Core` and `Projects` there is **no endpoint that lists or searches
installed equipment**. `Service` exposes `Equipment` only as a child array on a Service Case; `Core`
`StockItem` is the **product/SKU catalogue** (with traceable serial/batch stock, but not the installed
service-asset register). We cannot enumerate 300k assets from any documented route. **→ See §6, Q1–Q3.**

### 4.3 Service Contracts — 🟠 PARTIAL (push-only; no read)

| Pulse Fitness field | Sicon field | API | Direction |
|---|---|---|---|
| `contract_number` | `SiconContractNumber` | `POST /api/Contract/CreateUpdateContract` | Pulse → Sicon |
| `sicon_contract_id` | `SiconContractID` | (creation response) | Sicon → Pulse |
| customer link | `CustomerNumber` / `SLCustomerAccountID` | Contract POST | Pulse → Sicon |
| `customer_order_number` | — | `POST /api/Contract/UpdateContractCustomerOrderNumber` | Pulse → Sicon |
| contract lines | — | `POST /api/ContractLine/PostContractLine` | Pulse → Sicon |
| start / end / value / SLA | Contract fields | Contract POST | Pulse → Sicon |

**Problem:** `Contracts.R260200c` contains **only POST endpoints** — there is **no GET/list/read** of
existing contracts or contract lines. We can write contracts *into* Sicon but cannot pull a customer's
existing contract book *out* for migration, nor read contract state back for two-way sync. **→ §6, Q4.**

### 4.4 Service Cases / Appointments / Notes — ✅ (operational, already built)

| Pulse Fitness | Sicon | API |
|---|---|---|
| Issue (fault) | Service Case | `POST /api/service/cases` / `CreateNewCase`; `GET /api/service/cases` (list) |
| Case status / engineer / teams | Case fields | `GET /api/service/cases/{id}` (poll) |
| Appointments / time bookings | Appointments | `Service/Appointments`, `.../TimeBookings` |
| Timeline notes | Tracking Notes | `Service/Cases/{caseID}/TrackingNotes` (bi-directional) |
| Engineers | Appointment Resources / SIJCEMP | `GET /api/service/appointments/resources`, `Projects SIJCEMP/GetEmployees` |

This domain is fully mapped and implemented (push + 5-minute poll-back).

---

## 5. What Works vs What's Missing (summary)

**✅ Available now via published APIs**
- Customer/contact migration + incremental sync (Sage Core `GetCustomers` + Sicon CRM).
- Suppliers, stock catalogue, sales orders, invoices/ledgers (Sage Core) — if needed.
- Service case create + status/appointment/notes sync (Service API) — already live.
- Contract **creation/push** into Sicon (Contracts API).
- Authentication / multi-company connection.

**🔴 Missing / blocked**
1. **Equipment register read/list API** (installed serial-numbered assets) — *critical, 300k records*.
2. **Contracts read/list API** — cannot pull existing contracts or read them back for sync.
3. **Equipment ↔ contract / site linkage read** — needed to know which assets a contract covers.

---

## 6. Questions for Sicon (what we need to proceed)

> Please confirm the following so we can complete an automated, scalable migration and ongoing sync.

**Equipment (highest priority)**
- **Q1.** Is there an API (published or otherwise) to **list/search the installed Equipment / Service
  Asset register** for a company — ideally paged and with a "changed since" filter for incremental sync?
- **Q2.** If not a dedicated endpoint, can Equipment be read via the Service API's generic
  `GET /~/api/v2/TEntity` paged entity reader? If so, **what is the entity type/identifier for Equipment**,
  and what fields are returned?
- **Q3.** If no API path exists, can you provide a **one-time SQL/DB or CSV export** of all equipment
  (per company) with: `SiconEquipmentID`, serial number, make/model/type, install date, warranty/contract
  cover, linked customer (`SLCustomerAccountID`) and site/sub-location? We have an importer ready to ingest it.

**Contracts**
- **Q4.** Is there (or planned) a **GET/list endpoint for Service Contracts and contract lines** so we can
  migrate existing contracts and read contract state back? If not, can you provide a CSV/DB export?

**Equipment ↔ coverage**
- **Q5.** How is the **link between an equipment asset, its site/sub-location, and its covering contract**
  exposed for reading?

**Operational**
- **Q6.** Recommended **rate limits / page sizes** for bulk reads at our scale (5k customers / 300k assets)?
- **Q7.** Any **webhooks / change-notification** mechanism, or is scheduled polling
  (`AmendedAfterDate` / `updated-since`) the expected pattern?
- **Q8.** Confirm the **production base URL pattern** per customer instance and any IP-allow-listing needs.

---

## 7. Proposed Plan

| Phase | Scope | Dependency |
|---|---|---|
| **1 (in progress)** | CSV importers for equipment + contracts (idempotent, batched for scale); capture `SiconEquipmentID` / `SiconContractID` for later linkage | None — live |
| **2** | Automated **customer** pull + incremental sync (Sage Core `GetCustomers` / CRM) | None — ready to build |
| **3** | Automated **equipment** migration + sync | **Q1–Q3 (Sicon)** |
| **4** | **Contract** migration + two-way read | **Q4 (Sicon)** |

---

*Contact: the Pulse Fitness AI integration team. We're happy to join a technical call to walk through
any of the above.*
