# Sicon WebAPI — Import/Migration Readiness Audit (2026-06-29)

Founder asked: is pulsefitness.ai ready to auto-import customers / equipment / contracts
from Sicon once credentials are entered? Scale: **5,000+ customers, 300,000 equipment.**

## Canonical Sicon API docs (ReDoc — OpenAPI JSON directly fetchable)
- Service:   https://webapidocs.blob.core.windows.net/published/Redoc.html?page=Service.R260200c
  - spec JSON: https://webapidocs.blob.core.windows.net/published/Service.R260200c.json
- Contracts: https://webapidocs.blob.core.windows.net/published/Redoc.html?page=Contracts.R260200c
  - spec JSON: https://webapidocs.blob.core.windows.net/published/Contracts.R260200c.json
- CRM:       https://webapidocs.blob.core.windows.net/published/Redoc.html?page=CRM.R221200c
  - spec JSON: https://webapidocs.blob.core.windows.net/published/CRM.R221200c.json
(ReDoc loads `<page>.json` — append `.json` to the page name to grab the raw OpenAPI spec.)

## Endpoint inventory (what the APIs actually expose)

### Service.R260200c — 26 paths (case execution layer)
- `GET /api/service/cases`, `GET /api/service/cases/{id}` — LIST + read cases (paged)
- `POST /api/service/cases`, `POST /api/ServiceCase/CreateNewCase`, `/AmendCase`
- Appointments, TimeBookings, TrackingNotes, case-types, tracking-statuses, resources (engineers)
- `GET /api/SMConnectivity/Ping`
- ⚠️ **NO equipment/asset list endpoint.** Equipment only referenced via `EquipmentIDs` on a case.

### Contracts.R260200c — 4 paths — **PUSH ONLY**
- `POST /api/Contract/CreateUpdateContract`
- `POST /api/Contract/UpdateContractCustomerOrderNumber`
- `POST /api/ContractLine/PostContractLine`
- `POST /api/ContractSOP/SetSOPDeliveryAddressStatus`
- 🔴 **NO GET/list/read of contracts or contract lines.** You can write contracts INTO Sicon
  but cannot pull existing ones OUT via this API.

### CRM.R221200c — 405 paths — **rich, paginated, read-capable** (Sicon CRM / Sage CRM)
- Customers/Companies: `GET /api/CRM/Companies?searchTerm&page&pageSize&companyId`,
  `/Companies/Search`, `/Companies/Count`, `/Companies/{id}`,
  `GET /api/CRM/Companies/SL/{slCustomerAccountid}` (link to Sage SLCustomerAccountID),
  `POST /Companies/CreateCompanyFromCustomer` / `FromSupplier`.
- Contacts/People: `GET /api/CRM/People?…page&pageSize`, `/People/Search`, `/People/Count`,
  `/Companies/{id}/People`.
- Addresses, Opportunities (pipeline), Tenders, Cases, Communications, AnalysisCodes, GDPR.
- Lookups: Currencies, TaxCodes, Nominals, CountryCodes, AccountTypes, PaymentTerms.
- `GET /api/CRM/StockItems/Search?filter&page&pageSize` — ⚠️ **product/SKU catalogue, NOT installed
  serial-numbered customer assets.**
- ✅ Pagination (`page`/`pageSize`) on all list endpoints → safe for 5k+ records.

## VERDICT — auto-import feasibility per entity

| Entity | Auto-import via these APIs? | How |
|---|---|---|
| **Customers (5,000+)** | ✅ YES | CRM API `GET /api/CRM/Companies` (paged) + `/People` for contacts; `SL/{id}` links Sage |
| **Contracts** | 🔴 NO (read) | Contracts API is push-only; no GET. Cannot pull existing contracts from Sicon |
| **Equipment (300,000)** | 🔴 NO | No installed-asset list in Service or CRM (StockItems = catalogue, not assets). Likely lives in Sage 200 / Sicon Asset Mgmt / contract lines — needs a different source/export |

## Implication
"Enter credentials → everything flows in" is only true for **customers + contacts**.
**Equipment (the 300k — biggest volume) and existing contracts have NO read API here** and must
come from a Sage 200 export / Sicon Asset Management API / DB extract / CSV.

## Auth (confirmed by existing client + spec §6.1/§33.2)
HTTP Basic (username+password service account) over TLS + `companyId` query param on every call.
Stored Fernet-encrypted per-org in `sicon_config`. Same creds drive all three APIs (different base routes).

## CoreWebAPI.R260200c — Sage 200 Core WebAPI (added 2026-06-29, 135 paths)
Doc: https://webapidocs.blob.core.windows.net/published/Redoc.html?page=CoreWebAPI.R260200c
spec JSON: https://webapidocs.blob.core.windows.net/published/CoreWebAPI.R260200c.json
- ✅ Customers: `GET /api/Customer/GetCustomers` (Reference, **AmendedAfterDate** → incremental sync),
  `/GetCustomer`, `/SearchForCustomers`, `POST /api/Customers`, `/Customers/Contacts`, delivery addresses.
  → SECOND (better) route to auto-import customers + ongoing delta sync.
- Suppliers: `GET /api/Supplier/GetSuppliers`, `/Suppliers`, `/Suppliers/Contacts`.
- Stock: `GetStockItemsByCode`, `StockItem/Search` (paged), Create/Amend, Add/Transfer/WriteOff,
  **traceable items** (`GetTraceableItem` by StockItemCode+IdentificationNo/serial) — product/SKU + stock
  control, NOT installed assets.
- SOP (sales orders/quotes/despatch/invoice), SL/PL ledgers, SalesInvoices, PurchaseDocuments, credit notes,
  payments/receipts, Nominal journals/ledger, CashBook, PriceBook.
- ⚠️ **0 "equipment"/"asset" mentions.** Only Sage traceable stock (serial/batch) — NOT the Sicon Service
  equipment register. Confirms equipment auto-pull is still blocked (Sicon Service has no list endpoint).
- 🔴 No contracts here (Sicon-specific, push-only).

## Projects.R260200c — Sicon Projects / Job Costing (SIJC) (added 2026-06-29, 86 paths)
Doc: https://webapidocs.blob.core.windows.net/published/Redoc.html?page=Projects.R260200c
- Jobs/JobSheets (GetJobSheets, GetProjectHeadersForProjects, PostNewJobSheet, UpdateJob),
  ProjectLevel hierarchy (phases/stages/activities/statuses), `GET /api/customers/{traderaccountid}/projects`,
  SIJCBudgets (budgets/cost), SIJCCHD (job headers/cost codes), JobTimesheet + SIJCTRN (labour/timesheets/
  job completion), ProjectRates, SIJCEMP (employees), PlannedPurchase, HiredInPlant.
- 🔴 **0 equipment / 0 asset / 0 serial.** Job costing only — does NOT unlock equipment.

## EQUIPMENT HUNT — reviewed 5 APIs, NONE list installed equipment
Service (EquipmentIDs only, embedded on cases; generic `/~/api/v2/TEntity` paged reader exists but entity-type
for Equipment undocumented), Contracts (push-only), CRM (StockItems=catalogue), Core/Sage (traceable stock,
no equipment entity), Projects (job costing). → Equipment likely needs a SEPARATE Sicon Asset Management /
Service Equipment-register API doc, the Service TEntity entity-type name for Equipment, or a DB/SQL export.

## Recommended migration strategy (for 5k customers / 300k equipment)
1. **Customers + contacts** → live CRM API pull (paged, idempotent on Sage ref / sicon_company_id).
2. **Equipment** → bulk CSV/Excel/Sage-export pipeline (no Sicon API). MUST be batched + background +
   idempotent on `serial_number` / `sicon_equipment_id` at 300k scale.
3. **Contracts** → CSV importer (no Sicon read API) + optional push-back to Sicon via Contracts POST.
