> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> Field mapping below remains the canonical reference. Additions since
> iter 215dy:
>
> | New field | Direction | Notes |
> | --- | --- | --- |
> | `users.primary_module` | inbound from signup | One of `operations` / `memberships` / `crm` / `marketing`. Narrows post-signup `/activation/me` + `/account/onboarding`. |
> | `organizations.primary_module` | persisted at register-time | Same; used when the user-level field isn't cached. |
> | `activation_events.event_type` | internal | 16 types now (was 8). See `routes/activation_events.py:EVENT_TYPES` for the canonical list. |
> | `activation_events.module` | internal | Tag: `always` / `operations` / `memberships` / `crm` / `marketing`. |
>
> No outbound integration field changes vs 215dy.

---


# GymAxis · Integration Field Mapping (Master)

**Iter 215dy · Feb 2026 · Source-of-truth for cross-system data flow**

> Master mapping document covering **every** GymAxis module that talks to
> Sicon Service Manager and/or Sage 200 UK. Supersedes the Service-Ops-only
> `SVC_FIELD_MAPPING.md` (which now redirects here).
>
> **Lint rule of thumb during PR review**: *"if it isn't in this table, it
> doesn't ship."* Adding a Pydantic field anywhere in `routes/svc/*`,
> `routes/crm_*`, `routes/memberships/*`, or `routes/operations*` requires
> either (a) an entry in the relevant section below, OR (b) a `gymaxis_only`
> tag with a stated reason.
>
> The matching CI lint at `/app/backend/scripts/check_integration_mapping.py`
> parses this file and verifies the reverse direction — every `sicon:` /
> `sage:` annotation in the code resolves to a row here.

---

## 0. Module integration matrix

Which modules are wired to which external system, and at what fidelity.

| Module | Sicon Service Manager | Sage 200 UK | Direction | Fidelity |
|---|---|---|---|---|
| **Service Operations** (`routes/svc/*`) | Cases, tracking notes, appointments, signatures, parts, attachments | Invoice posting (`SLInvoice`), nominal codes, employee + stock + customer reads | bidirectional with Sicon · outbound to Sage | **Master spec — sections 2-18** |
| **CRM · Companies** (`crm_v2`, `crm_core`) | Read-only customer reference (Sicon `Company.SiconCompanyID`) | `SLCustomerAccount` (master) | Sage → GymAxis bootstrap, GymAxis → Sage on commercial enrichment | §19 below |
| **CRM · Contracts** (`crm_contracts.py`) | Sicon Service Contracts (`ServiceContractID`) | `SLContract` / recurring `SLInvoice` | bidirectional · Sicon owns lifecycle, Sage owns billing | §20 below |
| **CRM · CPQ Quotes** (`crm_cpq.py`) | — | `SLQuote` / `SLInvoice` (on signature) | GymAxis → Sage | §21 below |
| **Operations · Sites** (`sites.py`, `crm_v2`) | Sicon `SubLocation` | Sage `DeliveryAddress` | bidirectional, Sicon canonical for service routing | §22 below |
| **Operations · Equipment** (`equipment_import.py`) | Sicon `Equipment` (master) | Sage `FixedAsset` (if customer uses Sage Assets) | Sicon → GymAxis primary; Sage optional | §23 below |
| **Memberships · Plans / Members** (`routes/memberships/*`) | — (Pulse Fitness members are not Sicon-tracked) | `SLInvoice` (recurring), `SLCustomerAccount` (member as account) | GymAxis → Sage | §24 below |
| **Memberships · Booking** | — | — | gymaxis_only | §24 below |
| **Marketing** (`routes/marketing/*`) | — | — | gymaxis_only | not externally synced |

---

## 1. Source-of-truth ownership

| Domain | Master | Reason |
|---|---|---|
| Customer/Account financials | **Sage 200** | `SLCustomerAccountID`, statements, ledgers, nominal codes |
| Customer/Account commercial enrichment | **GymAxis CRM** | usage, NPS, marketing consent — Sage doesn't care |
| Site / sub-location | **GymAxis** | front-line operators keep this current |
| Equipment register | **Sicon** (read) / **GymAxis** (display) | Sicon `EquipmentIDs` is master; GymAxis enriches with QR / photos |
| Engineer roster (employee records) | **Sage 200 / Sicon** | `Employee` / `AppointmentResource` |
| Engineer day-to-day activity | **GymAxis** | mobile app is primary engineer UX; Sicon receives a sync |
| Service case lifecycle | **GymAxis** (with bidirectional Sicon mirror) | Sicon stays in lock-step — Pulse demo requirement |
| Parts catalogue & van stock | **GymAxis** (catalogue) / **Sicon** (van), **Sage** (warehouse) | new capability — GymAxis owns van stock UX |
| Invoice posting | **Sage 200** | only Sage issues invoices |
| Service contracts | **Sicon Service Contracts** (operational SLA) / **Sage** (billing) | CRM is the commercial mirror |
| Membership financials | **Sage 200** | recurring `SLInvoice` per member or per family |

---

## 2 – 18. Service Operations sections

Sections 2-18 (Service Cases, events, engineers, time entries, signatures,
photos, status crosswalk, note types, cover-type → nominal mapping, parts,
van stock, part movements, purchase orders, warehouse stock, AI artefacts,
quotes/invoices) are documented in the legacy file
`/app/memory/SVC_FIELD_MAPPING.md`. They remain authoritative for those
collections — nothing has been moved or rewritten.

---

## 19. CRM Companies ↔ Sage `SLCustomerAccount` ↔ Sicon `Company`

`crm_companies` collection mirrors a Sage customer account 1:1 (each
GymAxis company is one Sage SLCustomerAccount). Sicon's company record
is a denormalised copy used by the Service Manager for site routing.

| GymAxis field | Sage `SLCustomerAccount` | Sicon `Company` | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only | local uuid |
| `name` | `Name` | `CompanyName` | Sage → GymAxis bootstrap, GymAxis → both on edit | natural display name |
| `sage_customer_account_id` | `SLCustomerAccountID` | — | Sage → GymAxis | natural key |
| `sage_customer_reference` | `Reference` (e.g. `PULSE001`) | `SiconCompanyReference` | Sage → GymAxis | human-readable |
| `sicon_company_id` | — | `SiconCompanyID` (uuid) | Sicon → GymAxis | natural key on Sicon side |
| `vat_registration` | `VatRegistration` | — | Sage → GymAxis |  |
| `currency` | `Currency` | — | Sage → GymAxis | usually `GBP` |
| `nominal_default` | `DefaultNominalCode` | — | Sage → GymAxis | falls back per-line if cover_type drives it |
| `address_*` (lines, postcode, country) | `Address` block | `Address` block | bidirectional | Sage primary on first sync |
| `primary_contact_name` / `_email` / `_phone` | `Contacts[0]` | `PrimaryContact` | bidirectional |  |
| `account_status` (`active\|hold\|prospect\|closed`) | `Status` | — | bidirectional |  |
| `payment_terms_days` | `PaymentTermsDays` | — | Sage → GymAxis |  |
| `credit_limit` | `CreditLimit` | — | Sage → GymAxis | drives risk warnings on Service Desk |
| `crm_*` enrichment (NPS, segment, owner, tags) | — | — | gymaxis_only | reason: Sage doesn't model these |

**Demo-readiness note**: Sage onboarding flow when keys arrive →
1. `POST /api/crm/sage200/config` with `client_id`, `client_secret`, `site_id`, `company_id`.
2. `POST /api/crm/sage200/sync/customers` does first import — populates `crm_companies`.
3. From then on, edits in GymAxis push to Sage on save (debounced).

---

## 20. CRM Contracts ↔ Sicon Service Contracts ↔ Sage `SLContract`

`crm_contracts` collection is the GymAxis contractual record. Sicon owns
the operational Service Contract (SLA tier, covered equipment, callouts).
Sage owns the billing schedule (`SLContract` recurring invoices, or
plain `SLInvoice` if billed ad-hoc).

| GymAxis field | Sicon `ServiceContract` | Sage `SLContract` | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only | local uuid |
| `contract_number` (`CON-2026-001`) | `ContractReference` | `ContractReference` | bidirectional | natural key, GymAxis-generated |
| `sicon_contract_id` | `ServiceContractID` | — | Sicon → GymAxis |  |
| `sage_contract_id` | — | `SLContractID` | Sage → GymAxis |  |
| `company_id` (FK → crm_companies) | resolved → Sicon Company | resolved → `SLCustomerAccountID` | bidirectional |  |
| `status` (`draft\|active\|paused\|expired\|cancelled`) | `Status` | `Status` | bidirectional |  |
| `start_date` / `end_date` | `StartDate` / `EndDate` | `StartDate` / `EndDate` | bidirectional |  |
| `cover_tier` (`bronze\|silver\|gold\|platinum`) | `CoverLevelID` | — | GymAxis → Sicon | drives SLA defaults |
| `sla_response_hours` / `sla_resolve_hours` | `ResponseHours` / `ResolveHours` | — | GymAxis → Sicon | per cover_tier defaults, override-able |
| `included_callouts` / `included_ppm_visits` | `IncludedCallouts` / `IncludedPPM` | — | GymAxis → Sicon |  |
| `equipment_ids[]` (covered) | `CoveredEquipment[]` | — | GymAxis → Sicon | at signing |
| `value` (annual GBP) | — | `RecurringAmount × Periods` | GymAxis → Sage | derived |
| `billing_frequency` (`monthly\|quarterly\|annual`) | — | `Frequency` | GymAxis → Sage |  |
| `next_invoice_date` | — | `NextInvoiceDate` | Sage → GymAxis | dashboard reminder |
| `signed_pdf_url` | `Attachments[]` | — | GymAxis → Sicon |  |
| `crm_owner_id` | — | — | gymaxis_only | sales rep |

**Lifecycle**:
- *Draft* → CRM only, no external sync.
- *Active* → triggers `sync-sicon` (currently mocked at `/api/crm/contracts/{id}/sync-sicon`) and `sync-sage` (recurring `SLContract`).
- *Cancelled* → marks Sicon contract `Cancelled`, ends Sage recurring run.

---

## 21. CRM CPQ Quotes ↔ Sage `SLQuote` / `SLInvoice`

Distinct from Service-Ops quotes (§18). CRM CPQ quotes are sales-side
quotes for new contracts / equipment sales / one-off projects.

| GymAxis field | Sage field | Direction | Notes |
|---|---|---|---|
| `id` | — | gymaxis_only | local uuid |
| `quote_number` (`Q-2026-001`) | `SLQuote.Reference` | bidirectional | natural key |
| `company_id` | resolved → `SLCustomerAccountID` | bidirectional |  |
| `status` (`draft\|sent\|accepted\|declined\|expired`) | `Status` | bidirectional |  |
| `lines[].sku` | `SLQuoteLine.StockCode` | bidirectional |  |
| `lines[].qty` | `SLQuoteLine.Quantity` | bidirectional |  |
| `lines[].unit_amount` | `SLQuoteLine.UnitPrice` | bidirectional |  |
| `lines[].nominal_code` | `SLQuoteLine.NominalCode` | GymAxis → Sage | overrides default |
| `valid_until` | `ExpiryDate` | bidirectional |  |
| `accepted_at` (→ converts to invoice) | triggers `SLInvoice` create | GymAxis → Sage |  |
| `accepted_signature_url` | `SignedDocURL` | GymAxis → Sage |  |

---

## 22. Operations Sites ↔ Sicon `SubLocation` ↔ Sage `DeliveryAddress`

A "site" in GymAxis is a physical location (gym branch) where service
work happens. Sicon holds the canonical sub-location record because
its routing engine relies on the postcode.

| GymAxis field | Sicon `SubLocation` | Sage `DeliveryAddress` | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only |  |
| `name` | `Description` | `Name` | bidirectional |  |
| `company_id` (parent) | `SiconCompanyID` | `SLCustomerAccountID` | bidirectional |  |
| `sicon_sublocation_id` | `SiconSubLocationID` | — | Sicon → GymAxis |  |
| `sage_delivery_address_id` | — | `SLDeliveryAddressID` | Sage → GymAxis |  |
| `address_lines[]` / `postcode` / `country` | `LocationAddress` | `Address` block | bidirectional |  |
| `geo_lat` / `geo_lng` | `Latitude` / `Longitude` | — | GymAxis → Sicon | populated by postcode lookup if missing |
| `opening_hours` | `OpeningHours` (custom) | — | GymAxis → Sicon | drives engineer scheduling cut-offs |
| `access_notes` | `AccessNotes` (custom) | — | GymAxis → Sicon | "ring buzzer 14, gym is on the second floor" |
| `primary_contact_*` | `PrimaryContact` | — | bidirectional |  |
| `default_engineer_id` | `DefaultResourceID` | — | GymAxis → Sicon | preferred engineer for this site |
| `pulse_qr_id` | — | — | gymaxis_only | QR code for member checkin (Pulse Memberships) |

---

## 23. Equipment register ↔ Sicon `Equipment` ↔ Sage `FixedAsset`

| GymAxis field | Sicon `Equipment` | Sage `FixedAsset` | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only |  |
| `serial_number` | `SerialNumber` | `AssetReference` | bidirectional | natural key |
| `sicon_equipment_id` | `EquipmentID` | — | Sicon → GymAxis |  |
| `sage_asset_id` | — | `FixedAssetID` | Sage → GymAxis | optional — only customers using Sage Assets |
| `manufacturer` | `Manufacturer` | `Manufacturer` (custom) | bidirectional |  |
| `model` | `Model` | `Model` | bidirectional |  |
| `category` (`treadmill\|bike\|strength\|other`) | `EquipmentTypeID` | — | GymAxis → Sicon |  |
| `site_id` | `SubLocationID` | — | bidirectional |  |
| `purchased_at` / `purchase_price` | `PurchasedAt` / `PurchasePrice` | `AcquisitionDate` / `Cost` | bidirectional |  |
| `warranty_expires_at` | `WarrantyExpiresAt` | — | bidirectional |  |
| `qr_code_url` | — | — | gymaxis_only | GymAxis QR system |
| `last_serviced_at` | derived from `ServiceCalls[]` | — | Sicon → GymAxis | computed |
| `lifecycle_state` (`in_service\|retired\|sold\|stolen`) | `Status` | `Status` | bidirectional |  |

The `equipment_import.py` route already produces a Sicon-compatible CSV
(see `equipment_import.py:343`); this section is the API-driven equivalent.

---

## 24. Memberships ↔ Sage `SLInvoice` (recurring) ↔ Sage `SLCustomerAccount`

Pulse Fitness members are billed via Sage as recurring invoices. Each
member or family unit becomes one `SLCustomerAccount`. Sicon does **not**
hold member data — members are not service customers.

| GymAxis field (memberships) | Sage field | Direction | Notes |
|---|---|---|---|
| `members.id` | — | gymaxis_only |  |
| `members.email` | `SLCustomerAccount.PrimaryEmail` | GymAxis → Sage |  |
| `members.full_name` | `SLCustomerAccount.Name` | GymAxis → Sage |  |
| `members.sage_customer_account_id` | `SLCustomerAccountID` | Sage → GymAxis | populated on first invoice |
| `members.organization_id` | `SLCustomerAccount.ParentAccountID` (gym tenant) | GymAxis → Sage | invoices roll up to the gym tenant |
| `member_subscriptions.plan_id` | `SLInvoiceLine.NominalCode` (per plan) | GymAxis → Sage | each plan maps to a nominal |
| `member_subscriptions.amount` (monthly) | `SLInvoiceLine.UnitNetAmount` | GymAxis → Sage |  |
| `member_subscriptions.next_billing_at` | `SLInvoice.InvoiceDate` (next) | bidirectional |  |
| `member_subscriptions.status` (`active\|paused\|cancelled`) | invoice run skip flag | GymAxis → Sage |  |
| `family_autopay.payer_member_id` | one `SLCustomerAccount` | GymAxis → Sage | the payer is the Sage account; family members are dependants |
| `bookings.*` | — | gymaxis_only | reason: Sage doesn't track class bookings |
| `classes.*` | — | gymaxis_only |  |
| `instructors.*` | (potentially Sage `Employee` for payroll) | — | future: link via `sage_employee_id` |

**Demo-readiness note**: Memberships → Sage requires:
1. `crm_companies` configured (parent gym tenant → SLCustomerAccount).
2. Sage nominal codes per plan, loaded into `membership_plans.sage_nominal_code` (already a free field, currently nullable).
3. Outbox worker drains pending recurring invoices on the 1st of each month.

---

## 25. Credentials matrix — what's needed when keys arrive

The system is currently in **dry-run mode** for both Sicon and Sage. Every
write is enqueued to an outbox collection but no HTTP call is made until the
relevant credentials are present. The moment the keys arrive, drop them into
`/app/backend/.env` (or via the per-org config UI), restart the backend, and
the workers will start draining the outboxes.

### Sicon Service Manager (per-org config — stored encrypted in MongoDB)

Configured via `PUT /api/sicon/config` (UI: Admin Console → Integrations → Sicon).

| Field | Required | Notes |
|---|---|---|
| `base_url` | yes | e.g. `https://customer.sicon-cloud.com/api` |
| `username` | yes | encrypted at rest as `username_enc` |
| `password` | yes | encrypted at rest as `password_enc` |
| `enabled` | yes | master switch — false = dry-run |
| `tenant_id` | optional | Sicon multi-tenant (R260200c+) |

### Sage 200 UK (per-org config — stored encrypted in MongoDB)

Configured via `POST /api/crm/sage200/config` (UI: CRM Settings → Sage 200).

| Field | Required | Notes |
|---|---|---|
| `client_id` | yes | OAuth2 client id — from Sage developer portal |
| `client_secret` | yes | OAuth2 client secret — encrypted |
| `site_id` | yes | Sent as `X-Site` header |
| `company_id` | yes | Sent as `X-Company` header |
| `tier` | yes | `standard` or `professional` (drives base URL) |
| `enabled` | yes | master switch — false = dry-run |

### Optional fallback env vars (master admin / dev)

These are only used by the master-admin-driven test endpoints
(`POST /api/integrations/test/sicon`, `…/sage`) — production tenants always
go through the per-org UI.

```bash
SICON_BASE_URL=
SICON_USERNAME=
SICON_PASSWORD=
SICON_POLL_INTERVAL_SECONDS=300            # default 5 min
SICON_KPI_RECALC_INTERVAL_SECONDS=900      # default 15 min

SAGE_CLIENT_ID=
SAGE_CLIENT_SECRET=
SAGE_SITE_ID=
SAGE_COMPANY_ID=
SAGE_TIER=standard                         # or `professional`
```

### Outbox state model (live readiness)

| Collection | Drained by | Trigger | Status flow |
|---|---|---|---|
| `svc_sicon_outbox` | `utils/sicon_sync.worker` (Phase 8 A) | every 30s while Sicon enabled | `pending → in_flight → succeeded \| failed (retry ≤ 5) → dead_letter` |
| `svc_sage_invoice_outbox` | `utils/sage_invoice.worker` (Phase 8 B) | on quote finalisation + every 5 min | `pending → ready → submitted → posted \| failed` |
| `svc_sage_po_outbox` | `utils/sage_outbox_worker` (Phase 8 B) | on PO submission + every 5 min | `pending → in_flight → posted \| failed (retry ≤ 5) → dead_letter` |
| `svc_sage_quote_outbox` | `utils/sage_outbox_worker` (iter 215ed) | on chargeable case intake when `quote_required=true` + every 5 min | `pending → in_flight → posted \| failed (retry ≤ 5) → dead_letter` |
| `svc_sicon_inbox` (poll results) | `utils/sicon_poller` | every `SICON_POLL_INTERVAL_SECONDS` | merge into `svc_cases` |

---

## 26. Process rule going forward

1. Adding a non-private field to a Pydantic model in any of:
   - `routes/svc/*` · `routes/crm_*` · `routes/memberships/*` · `routes/operations*`

   …requires either:

   - An entry in the relevant section of this file with sicon/sage mapping, **or**
   - An inline `gymaxis_only: <reason>` annotation in the Pydantic `Field(description=…)`.

2. The CI lint at `/app/backend/scripts/check_integration_mapping.py` parses
   this file (sections 2-24) and validates internal consistency — no broken
   references, no duplicate natural keys, and that every documented Sicon
   endpoint actually exists in `routes/svc/integrations/sicon_sync.py` or
   `routes/sicon.py`.

3. **This file wins** if the code annotations diverge — the code is corrected.

4. Any change touching a `bidirectional` field MUST update both directions
   atomically (the outbox enqueue + the poller merge logic).

---

**Owner**: GymAxis Engineering · iter 215dy · Feb 2026

**See also**:
- `/app/memory/SVC_FIELD_MAPPING.md` — sections 2-18 (Service Ops detail)
- `/app/memory/SERVICE_OPS_ARCHITECTURE.md` — module architecture
- `/app/memory/SICON_INTEGRATION_SPEC.md` — Sicon API contract
- `/app/backend/routes/svc/integrations/INTEGRATIONS_README.md` — code-side wiring guide
- `/app/backend/scripts/check_integration_mapping.py` — CI lint
