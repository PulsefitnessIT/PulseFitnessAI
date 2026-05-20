> **📋 Status — Iter 216h240 (Feb 19, 2026)**
>
> Field mapping below remains the canonical reference. Iter 216h240
> closed the import-surface gaps that prevented end-to-end Sicon /
> Sage / Orbit 4 round-trips at migration time. **No additional
> sections** are introduced — the existing §19, §22, §23, §29
> rows are now fully reachable through the import + manual UIs:
>
> | Surface | Now captures |
> | --- | --- |
> | `POST /api/equipment` (manual add dialog) | `qr_code`, `manufacturing_date`, `deprecation_date`, `orbit4_asset_id`, `orbit4_product_id`, `sicon_equipment_id` |
> | `POST /api/equipment/import/csv` + `/import-csv` + `GET /equipment/csv-template` + `/equipment/template/csv` | Same six round-trip columns appended to both CSV variants |
> | `POST /api/equipment` AI invoice flow (`equipment_import._build_equipment_doc`) | Best-effort pass-through of the same six fields when the AI extractor surfaces them |
> | `POST /api/sites` + `PATCH /api/sites/{id}` + sites CSV import template | `opening_hours`, `access_notes`, `default_engineer_email` (§22 Sicon engineer-scheduling fields) |
> | `POST /api/crm/companies` (manual + UI) | `sage_customer_account_id`, `sage_customer_reference`, `sicon_company_id`, `sicon_company_reference`, `vat_registration`, `currency`, `nominal_default`, `payment_terms_days`, `credit_limit`, `account_status` |
> | **`GET /api/crm/companies-csv-template`** (new) | Same 10 Sage/Sicon refs |
> | **`POST /api/crm/companies-import-csv`** (new) | Idempotent dedupe on `sage_customer_reference` → `sicon_company_reference` → `name` |
> | `POST /api/crm/import/contacts` (existing) | Now also accepts `sage_ref`, `sage_id`, `sage_customer_account_id` — dedupes on `sage_ref` first, then email |
> | `POST /api/crm/contracts` (existing) | Default doc now carries `orbit4_contract_id` slot (PUT already accepted unknown fields) |
>
> Earlier h-series additions retained:
>
> | New surface | Section |
> | --- | --- |
> | CRM activation events that fire Sage/Sicon-relevant business signals | §27 |
> | `primary_module` flow (signup → org doc → trial funnel) | §28 |
> | Two-step CRM ↔ Sage customer sync (already in `routes/crm_sage200.py`) | §29 — formalised mapping |
> | Orbit 4 platform — overview, credentials, webhook events | §30 |
> | Orbit 4 → GymAxis (inbound mappers) — tickets, assets, contracts, users | §31 |
> | GymAxis → Orbit 4 (outbound mappers) — equipment, contracts, tickets, users + status crosswalk | §32 |
>
> Earlier h232 addendum:
>
> | New field | Direction | Notes |
> | --- | --- | --- |
> | `users.primary_module` | inbound from signup | One of `operations` / `memberships` / `crm` / `marketing`. Narrows post-signup `/activation/me` + `/account/onboarding`. |
> | `organizations.primary_module` | persisted at register-time | Same; used when the user-level field isn't cached. |
> | `activation_events.event_type` | internal | 16 types now (was 8). See `routes/activation_events.py:EVENT_TYPES` for the canonical list. |
> | `activation_events.module` | internal | Tag: `always` / `operations` / `memberships` / `crm` / `marketing`. |
>
> No outbound Sicon/Sage payload changes vs 215dy.

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

| Module | Sicon Service Manager | Sage 200 UK | Orbit 4 | Direction | Fidelity |
|---|---|---|---|---|---|
| **Service Operations** (`routes/svc/*`) | Cases, tracking notes, appointments, signatures, parts, attachments | Invoice posting (`SLInvoice`), nominal codes, employee + stock + customer reads | Inbound tickets via webhook → forwarded as Sicon cases (`routes/integrations.py`) | bidirectional with Sicon · outbound to Sage · inbound from Orbit 4 | **Master spec — sections 2-18 (Sicon/Sage), §30-§32 (Orbit 4)** |
| **CRM · Companies** (`crm_v2`, `crm_core`) | Read-only customer reference (Sicon `Company.SiconCompanyID`) | `SLCustomerAccount` (master) | — | Sage → GymAxis bootstrap, GymAxis → Sage on commercial enrichment | §19 below |
| **CRM · Contracts** (`crm_contracts.py`) | Sicon Service Contracts (`ServiceContractID`) | `SLContract` / recurring `SLInvoice` | Mirrored to Orbit 4 `/contracts` (active + dates + parties — §32) | bidirectional · Sicon owns lifecycle, Sage owns billing, Orbit 4 holds operator-facing copy | §20 below + §32 |
| **CRM · CPQ Quotes** (`crm_cpq.py`) | — | `SLQuote` / `SLInvoice` (on signature) | — | GymAxis → Sage | §21 below |
| **Operations · Sites** (`sites.py`, `crm_v2`) | Sicon `SubLocation` | Sage `DeliveryAddress` | `user.site_name` on Orbit 4 user records (denormalised, §32) | bidirectional, Sicon canonical for service routing | §22 below |
| **Operations · Equipment** (`equipment_import.py`) | Sicon `Equipment` (master) | Sage `FixedAsset` (if customer uses Sage Assets) | Orbit 4 `/assets` — bidirectional (qr_code, brand/range/product, lifecycle dates — §31/§32) | Sicon → GymAxis primary; Sage optional; Orbit 4 bidirectional | §23 below + §31/§32 |
| **Issues / Faults** (`routes/issues.py`, `routes/faults.py`) | Mirrored as `svc_cases` (existing §2-§4 pipeline) | — | Orbit 4 `/contracts/{id}/tickets` — outbound mirror with status crosswalk (§32) | inbound from Orbit 4 via webhook; outbound for GymAxis-originated faults | §31/§32 |
| **Memberships · Plans / Members** (`routes/memberships/*`) | — (Pulse Fitness members are not Sicon-tracked) | `SLInvoice` (recurring), `SLCustomerAccount` (member as account) | — | GymAxis → Sage | §24 below |
| **Memberships · Booking** | — | — | — | gymaxis_only | §24 below |
| **Marketing** (`routes/marketing/*`) | — | — | — | gymaxis_only | not externally synced |

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

---

## 27. Activation event bus — Sage/Sicon-relevant signals

The activation bus (`routes/activation_events.py`) emits internal
"first wins" signals that often map onto upstream CRM events Sage
and Sicon care about. These are NOT pushed to Sage/Sicon directly —
the bus is internal — but each one is also the natural moment to
fire the outbound integration write.

| Activation event | Fires from | Sage / Sicon side effect |
|---|---|---|
| `first_lead_added` | `crm_core.py:POST /companies` | Same handler creates a `crm_v2_companies` row that holds `sage_customer_account_id`. When the field is set later (manual or via §29 sync), no extra hook needed. |
| `first_deal_created` | `crm_core.py:POST /deals` | Sage doesn't model deals — pure GymAxis. CRM forecasting only. |
| `first_quote_sent` | `crm_cpq.py:POST /quotes/{id}/send` | Quote send emits to `svc_sage_quote_outbox` (§25). Worker posts `SLQuote` to Sage. |
| `first_brand_discovered` | `marketing/brand_discovery.py:POST /apply` | Pure marketing; no Sage/Sicon write. |
| `first_audience_built` | `marketing/audiences.py:POST /audiences` | Pure marketing. |
| `first_campaign_launched` | `marketing/campaigns.py:POST /campaigns/{id}/send` | When `sent > 0`, fires `first_campaign_launched`. No Sage write — campaign metering is internal. |
| `first_equipment_added` | `equipment.py:POST /equipment` | New equipment row is Sicon-bound via §23 — `_enqueue` to `svc_sicon_outbox` for `Equipment` upsert (existing wiring). |
| `first_fault_logged` | `issues.py:POST /issues` | When escalated → `_mirror_issue_to_svc_case` clones into `svc_cases`. From there the existing Sicon push (§2) fires. |
| `first_member_added` | `memberships/members.py:POST /members` | New `members` row creates a Sage `SLCustomerAccount` on first `SLInvoice` (lazy creation per §24). |
| `first_booking_taken` | `memberships/bookings.py:POST /bookings` | Pure memberships; no Sage write at booking time. |
| `first_invoice_generated` | `memberships/billing.py` recurring run | Direct Sage `SLInvoice` write (§24). |
| `first_class_scheduled` | `memberships/class_templates.py:POST /class-templates` | Pure memberships. |

**Rule**: every activation event is wrapped in `try/except` so a
failed activation write NEVER blocks the primary CRM/Marketing/
Memberships/Operations write. The outbox writes that drive Sage/Sicon
are separately resilient via their own outbox retry logic (§25).

---

## 28. `primary_module` flow

Captured at trial signup so the post-signup First Wins funnel and
Setup Checklist tailor to the operator's intent (iter 216h227).

| GymAxis field | Source | Destination | Direction | Notes |
|---|---|---|---|---|
| `UserRegister.primary_module` | Frontend signup form (`TrialSignupModal.openTrial('crm'|'marketing'|'memberships'|'operations')`) | `/api/auth/register` POST body | inbound | Optional — null when prospect arrives via direct-sales / partner path |
| `organizations.primary_module` | `auth.py:register` `enrichment_fields["primary_module"]` | MongoDB `organizations` doc | persisted | Read by `activation_for_me` + `onboarding_status` |
| `users.primary_module` | Cached on login | `users` doc | derived | Fallback when org doc isn't cached |
| activation funnel filter | `_primary_modules_for()` in `activation_events.py` | computed | internal | Narrows visible events to JUST the primary module + universal events |
| onboarding step filter | `routes/account.py:_step_visible()` | computed | internal | Hides ops-only steps (import_machines, print_qr_codes) for non-ops trials; hides `connect_stripe` for CRM trials |

**No outbound mapping** — `primary_module` is a GymAxis-internal
funnel-shaping signal that never reaches Sage or Sicon. Documented
here because the field touches the same `organizations` doc that
holds `sage_customer_account_id` / `sicon_company_id`.

---

## 29. CRM `crm_contacts` ↔ Sage `SLCustomerAccount` (already-implemented sync)

The route `routes/crm_sage200.py` has both directions wired up
(introduced earlier than the current spec was written). Documenting
formally here so the field-mapping CI lint can validate against
the canonical rows.

### Direction A — Sage → CRM (`POST /api/crm/sage200/sync/customers`)

Implemented in `_map_sage_customer_to_contact()`.

| GymAxis `crm_contacts` field | Sage `SLCustomerAccount` field | Direction | Notes |
|---|---|---|---|
| `id` | — | gymaxis_only | UUID at first insert |
| `company_name` | `name` | Sage → GymAxis |  |
| `sage_ref` | `reference` | Sage → GymAxis | Natural key for upsert |
| `sage_id` | `id` | Sage → GymAxis | Sage's own customer GUID |
| `phone` | `telephone_subscriber_number` | Sage → GymAxis |  |
| `website` | `website` | Sage → GymAxis |  |
| `first_name` / `last_name` | `contacts[0].first_name/last_name` | Sage → GymAxis | First primary contact, if any |
| `tags` | — | gymaxis_only | Set to `["sage200"]` on first insert |
| `source` | — | gymaxis_only | Set to `"sage200"` |
| `lead_score` | — | gymaxis_only | Default 0 |
| `owner_id` | — | gymaxis_only | Set to the syncing user's id |

### Direction B — CRM → Sage (`POST /api/crm/sage200/sync/customers-to-sage`)

Implemented inline in `push_contacts_to_sage()`. Only pushes contacts
where `sage_ref` is unset (never re-syncs).

| GymAxis `crm_contacts` field | Sage `SLCustomerAccount` payload | Direction | Notes |
|---|---|---|---|
| `id[:8].upper()` | `reference` | GymAxis → Sage | Generated as `CRM-{first 8 of UUID}` |
| `first_name + last_name` (fallback `company_name`) | `name` | GymAxis → Sage |  |
| `first_name` | `contacts[0].first_name` | GymAxis → Sage |  |
| `last_name` | `contacts[0].last_name` | GymAxis → Sage |  |
| Sage returned `id` | persisted to `sage_id` | Sage → GymAxis | Round-trip — sets `sage_id` on success so subsequent syncs are no-ops |

### Mode

Currently **dry-run** until per-org Sage credentials are configured
via `POST /api/crm/sage200/config` (UI: CRM Settings → Sage 200).
When `enabled=false` (default), every sync call returns `503 Sage 200
not configured`. The moment `enabled=true` with valid `client_id /
client_secret / site_id / company_id`, the two endpoints start
hitting the real Sage API immediately — no separate worker drain,
because these are synchronous endpoints triggered by an operator,
not background outbox writes.

---


## 30. Orbit 4 platform — overview, credentials, webhook events

Orbit 4 (`api.orbit4.org/v1`) is the gym-operator-facing fault &
asset register used by Pulse Fitness members. Wired in
`routes/integrations.py` + `utils/orbit4_client.py`. Three flows:

| Flow | Direction | Mode | Code path |
|---|---|---|---|
| **Webhook receiver** | Orbit 4 → GymAxis | Inbound, real-time | `POST /api/webhooks/orbit4` (HMAC-SHA256 verified via `X-Signature`) |
| **REST client** | GymAxis → Orbit 4 | Outbound, on-demand | `utils.orbit4_client.Orbit4Client` (httpx, Bearer auth) |
| **Sicon bridge** | Orbit 4 → Sicon | Forwarded | `process_new_ticket()` → `_map_orbit4_to_sicon()` → `svc_cases` outbox |

### Credentials matrix (per-org or platform-level via `db.integrations`)

Configured via `PUT /api/integrations/orbit4` (UI: Admin Console →
Integrations → Orbit 4). Defaults seeded by `seed_integrations()` in
`routes/integrations.py:_DEFAULT_ORBIT4_CONFIG`.

| Field | Required | Notes |
|---|---|---|
| `enabled` | yes | master switch — false = webhook returns `{"status":"ignored","reason":"integration_disabled"}` |
| `api_token` | yes (for outbound) | OAuth Bearer token sent as `Authorization: Bearer …` |
| `webhook_secret` | yes (for inbound) | HMAC-SHA256 shared secret. Webhook signature header: `X-Signature` |
| `base_url` | yes | default `https://api.orbit4.org/v1`; per-tenant overrides supported |
| `webhook_url` | derived | always `/api/webhooks/orbit4` (the GymAxis route — give this to Orbit 4 ops) |
| `field_mappings` | optional | JSON overrides for the default field map (description / subject / asset_serial / asset_name / priority) |
| `settings.auto_forward_to_sicon` | optional | when true (default), inbound tickets fan out to `svc_cases` (§2-4) |
| `settings.log_all_events` | optional | drop every webhook into `integration_logs` for replay |
| `branding.display_name` | optional | tenant label shown in the webhook ack response |
| `branding.user_agent` | optional | sent as `User-Agent` header on outbound calls (default `PulseFitness-ServiceBridge/1.0`) |

### Webhook event types (set by `utils.orbit4_client.ORBIT4_SUPPORTED_EVENTS`)

Handled by `routes.integrations.orbit4_webhook` → dispatcher:

| Event | Handler | GymAxis side effect |
|---|---|---|
| `ticket.created` | `process_new_ticket` | Insert `integration_bridge` row, create `svc_cases` row (when `auto_forward_to_sicon=true`) |
| `ticket.updated` | `process_ticket_update` | Mirror status + lifecycle timestamps onto existing bridge row |
| `ticket.closed`  | `process_ticket_closed` | Set `svc_cases.status="closed"`, populate `closed_at` |
| `asset.created`  | `process_asset_upsert` | Upsert `equipment` row keyed on `orbit4_asset_id` |
| `asset.updated`  | `process_asset_upsert` | Same upsert (idempotent) |
| `asset.moved`    | `process_asset_moved`  | Reassign `equipment.site_id` |
| `note.created`   | `process_note_created` | Append `svc_case_notes` row tagged `source="orbit4"` |
| `media.created`  | `process_media_created` | Append `svc_case_attachments` row |
| `user.created`   | `process_user_upsert`  | Provision `users` row (kiosk operator role) |
| `user.updated`   | `process_user_upsert`  | Same upsert |

Inbound webhook ack body:
```json
{"status": "ok", "event": "<event_type>", "processor": "<branding.display_name>"}
```

---

## 31. Orbit 4 → GymAxis (inbound mappers — Phase α/β)

Implemented in `utils/orbit4_client.py`. Every Orbit 4 entity has a
dedicated mapper that flattens the upstream JSON into a GymAxis-shaped
dict ready for Mongo insert.

### 31.1 Ticket → GymAxis fault / svc_case  (`map_orbit4_ticket_full`)

| GymAxis field | Orbit 4 field | Notes |
|---|---|---|
| `orbit4_ticket_id` | `id` | natural key — string |
| `orbit4_ticket_number` | `number` | human reference (e.g. `O4-12345`) |
| `subject` | derived: `f"Orbit4 #{number} — {asset.product}"` | shown on Service Desk row |
| `description` | `description` | also mirrored to `issue_description` |
| `severity` | `priority` via `ORBIT4_PRIORITY_TO_GYMAXIS` | `critical/urgent → critical · high → high · normal/medium → medium · low → low` |
| `orbit4_status` | `status` | raw Orbit 4 status, not yet remapped |
| `orbit4_type` | `type` | Orbit 4 ticket type tag |
| `orbit4_problem_type` | `problem_type` | drives Sicon `problem_type` field |
| `orbit4_priority` | `priority` | raw value preserved for analytics |
| `orbit4_tags[]` | `tags[]` | string list |
| `orbit4_engineer_deployed_at` | `engineer_deployed_at` | ISO-8601 |
| `orbit4_engineer_arrived_at`  | `engineer_arrived_at`  | ISO-8601 |
| `orbit4_closed_at` | `closed_at` | ISO-8601 |
| `orbit4_created_at` | `created_at` | ISO-8601 |
| `orbit4_gym_operator{}` | `gym_operator` (user) | flattened via `_user_summary()`: `{id, name, email, role, site_name, company_name}` |
| `orbit4_service_provider{}` | `service_provider` (user) | same shape |
| `orbit4_ticket_admin{}` | `ticket_admin` (user) | same shape |
| `orbit4_engineer{}` | `engineer` (user) | same shape |
| `orbit4_caretaker{}` | `caretaker` (user) | same shape |
| `orbit4_contract{}` | `contract` (summary) | `{id, number, type, active, start_date, end_date}` |
| `orbit4_attachments[]` | flattened `media[]` + `images[]` + `documents[]` | `{id, url, type, source:"orbit4", created_at}` |
| `orbit4_notes[]` | `notes[]` | `{type:"orbit4_note", message, by, is_system, timestamp}` |
| `orbit4_metadata{}` | `metadata` | raw passthrough (JSON object) |
| `asset_serial` | `asset.serial_number` | only set when `asset` block present |
| `asset_name` | derived from `asset.brand / asset.range / asset.product` | display friendly |
| `asset_qr_code` | `asset.qr_code` | QR code on the machine |
| `machine_type` | `asset.product` | category bucket |
| (asset fan-out) | inlined via `map_orbit4_asset_to_gymaxis(asset)` | see §31.2 |
| `source` | hard-coded `"orbit4"` | provenance tag for audit |

### 31.2 Asset → GymAxis equipment  (`map_orbit4_asset_to_gymaxis`)

| GymAxis field | Orbit 4 field | Notes |
|---|---|---|
| `orbit4_asset_id` | `id` | natural key (int) |
| `orbit4_product_id` | `product_id` | Orbit 4 catalogue id |
| `orbit4_qr_code` | `qr_code` | physical sticker on the machine |
| `serial_number` | `serial_number` | bidirectional with Sicon §23 |
| `manufacturer` | `brand` |  |
| `model` | `range` | Orbit 4 calls the model line "range" |
| `equipment_type` | `product` | e.g. "Treadmill", "Bike" |
| `install_date` | `installation_date` | ISO date |
| `manufacturing_date` | `manufacturing_date` |  |
| `warranty_expiry` | `warranty_end_date` |  |
| `orbit4_deprecation_date` | `deprecation_date` | end-of-life flag |
| `orbit4_current_spend` | `current_spend` | YTD spend on this asset |
| `orbit4_max_spend` | `max_spend` | budget cap |
| `orbit4_residual_price` | `residual_price` | depreciated book value |
| `orbit4_fitness_product` | `fitness_product` | boolean — `true` for cardio/strength |
| `orbit4_has_odometer` | `has_odometer` | boolean — true for treadmills/bikes |
| `orbit4_image_url` | `image` | hero image |
| `orbit4_metadata{}` | `metadata` | raw passthrough |

### 31.3 Contract → GymAxis CRM contract  (`map_orbit4_contract_to_gymaxis`)

Cross-references §20 (CRM contracts).

| GymAxis field | Orbit 4 field |
|---|---|
| `orbit4_contract_id` | `id` |
| `contract_number` | `number` |
| `contract_type` | `type` |
| `active` | `active` |
| `start_date` | `start_date` |
| `end_date` | `end_date` |
| `orbit4_gym_operator{}` | `gym_operator` (user summary) |
| `orbit4_service_provider{}` | `service_provider` (user summary) |
| `orbit4_metadata{}` | `metadata` |

### 31.4 Forward to Sicon  (`_map_orbit4_to_sicon`)

When `auto_forward_to_sicon=true`, the inbound ticket is *also* shaped into a
Sicon-friendly `svc_cases` row:

| svc_cases field | Built from |
|---|---|
| `issue_description` | `description` |
| `severity` | `ORBIT4_PRIORITY_TO_GYMAXIS[priority]` |
| `priority` | `map_orbit4_priority(priority)` |
| `location` | `orbit4_gym_operator.site_name` |
| `reporter_name` | `orbit4_gym_operator.name` |
| `reporter_email` | `orbit4_gym_operator.email` |
| `orbit4_ticket_id` | echoed onto the case for cross-ref |
| `orbit4_reference` | `orbit4_ticket_number` |
| `orbit4_status / type / problem_type` | echoed for analytics |

The created case then flows through the standard Sicon §2-§4 outbox
(no special-cased path). The `integration_bridge` collection holds the
`{orbit4_ticket_id ↔ svc_cases.id ↔ sicon_case_id}` triple-key for
deterministic reverse lookup on subsequent webhooks.

---

## 32. GymAxis → Orbit 4 (outbound mappers — Phase γ/δ)

GymAxis-originated changes mirror to Orbit 4 via the
`utils.orbit4_client.Orbit4Client` REST surface. All outbound payloads
strip `None`/`""` values for clean PUTs.

### 32.1 Equipment → Orbit 4 asset  (`map_gymaxis_equipment_to_orbit4`)

`POST /v1/assets` — invert of §31.2.

| Orbit 4 field | GymAxis field | Notes |
|---|---|---|
| `qr_code` | `equipment.qr_code` (fallback `GA-{id[:8]}`) | guarantees a unique QR even without user-set value |
| `serial_number` | `equipment.serial_number` | natural key |
| `brand` | `equipment.manufacturer` (fallback `make`) |  |
| `range` | `equipment.model` (fallback `model_code`) |  |
| `product` | `equipment.equipment_type` (fallback `name`) |  |
| `installation_date` | `equipment.install_date[:10]` | trimmed to YYYY-MM-DD |
| `manufacturing_date` | `equipment.manufacture_date[:10]` |  |
| `warranty_end_date` | `equipment.warranty_expiry[:10]` |  |
| `deprecation_date` | `equipment.deprecation_date[:10]` |  |
| `user_id` | optional integer (Orbit 4 gym operator id) | injected by caller |
| `product_id` | optional integer (Orbit 4 catalogue id) | injected by caller |
| `metadata` | JSON-stringified `{"integration_id": equipment.id, "organization_id": equipment.organization_id}` | reverse-lookup key |

### 32.2 CRM contract → Orbit 4 contract  (`map_gymaxis_contract_to_orbit4`)

`POST /v1/contracts` — natural extension of §20.

| Orbit 4 field | GymAxis field |
|---|---|
| `gym_operator_id` | caller-provided int (Orbit 4 user id of the gym) |
| `service_provider_id` | caller-provided int (Orbit 4 user id of Pulse / installer) |
| `number` | `contract.contract_number` (fallback `id`) |
| `type` | `contract.contract_type` (fallback `tier` or `"Full Annual"`) |
| `start_date` | `contract.start_date[:10]` |
| `end_date` | `contract.end_date[:10]` |
| `active` | `contract.status == "active"` |
| `metadata` | JSON-stringified `{integration_id, organization_id}` |

### 32.3 Fault → Orbit 4 ticket  (`map_gymaxis_issue_to_orbit4_ticket`)

`POST /v1/contracts/{contract_id}/tickets`.

| Orbit 4 field | GymAxis field |
|---|---|
| `description` | `issue.issue_description` |
| `priority` | `_priority_for_orbit4(issue.severity)` via `GYMAXIS_SEVERITY_TO_ORBIT4` (see crosswalk below) |
| `problem_type` | caller-provided string (default `"undefined"`) |
| `tags[]` | `issue.fault_tags[]` |
| `asset_id` | optional Orbit 4 asset id |
| `gym_operator_id` | optional Orbit 4 user id |
| `service_provider_id` | optional Orbit 4 user id |
| `metadata` | JSON-stringified `{integration_id, organization_id, supplier_case_token, sicon_case_id}` |

### 32.4 Severity → priority crosswalk  (`GYMAXIS_SEVERITY_TO_ORBIT4`)

| GymAxis `severity` | Orbit 4 `priority` |
|---|---|
| `safety_critical` | `critical` |
| `critical` | `high` |
| `high` | `high` |
| `medium` | `normal` |
| `low` | `low` |

Reverse map (`ORBIT4_PRIORITY_TO_GYMAXIS`, used in §31.1) accepts
`critical / urgent / high / normal / medium / low`.

### 32.5 Status → status crosswalk  (`map_gymaxis_status_to_orbit4_patch`)

`PUT /v1/tickets/{id}` — conservative remap (Orbit 4 only knows
`open` / `in_progress` / `closed`).

| GymAxis `issue.status` | Orbit 4 `status` |
|---|---|
| `open` / `new` | `open` |
| `in_progress` / `scheduled` / `parts_on_order` / `awaiting_parts` / `engineer_assigned` | `in_progress` |
| `completed` / `resolved` / `closed` / `archived` | `closed` |

When the remapped status is `closed`, the PATCH body also includes
`closed_at` (now-UTC ISO) and an optional `resolution` string
(truncated to 1000 chars).

### 32.6 User → Orbit 4 user  (`map_gymaxis_user_to_orbit4`)

`POST /v1/users` — provisions a GymAxis operator onto Orbit 4 so
subsequent ticket/asset events have a known counterparty.

| Orbit 4 field | GymAxis field | Notes |
|---|---|---|
| `first_name` | `user.full_name.split(" ", 1)[0]` (≤60 chars) |  |
| `last_name`  | `user.full_name.split(" ", 1)[1]` (≤60 chars, fallback `"-"`) |  |
| `email` | `user.email` |  |
| `language` | `user.language` if in `ORBIT4_LANG_ENUM`, else `"en"` | enum: en/es/de/bg/pt/fr/jp/tr/ar/zh/zh-Hant/hi/bn/pl/id/th/vi/el |
| `role` | caller-provided (default `"gym_operator"`) |  |
| `site_name` | optional (≤120 chars) |  |
| `metadata` | JSON-stringified `{integration_id, organization_id}` |  |

### 32.7 Note / attachment add-ons

These ride on existing ticket calls — no dedicated mapper:
- `Orbit4Client.add_ticket_note(ticket_id, note, user_id?)` → `POST /v1/tickets/{id}/notes`
- `Orbit4Client.close_ticket(ticket_id, payload?)` → `POST /v1/tickets/{id}/close`
- `Orbit4Client.link_user(parent_id, child_id)` → `POST /v1/users/{parent_id}/link`

### Demo-readiness note

To go live with Orbit 4:
1. Add the `api_token` + `webhook_secret` via `PUT /api/integrations/orbit4`.
2. Set `enabled=true`. The webhook receiver becomes hot immediately.
3. Run `POST /api/integrations/orbit4/test-connection` for a credentials/handshake check, then verify outbound mirroring via `POST /api/integrations/orbit4/mirror/equipment/{equipment_id}` (and the equivalent `/mirror/contract/{contract_id}` + `/mirror/issue/{issue_id}` routes).
4. For outbound: ensure `gym_operator_id` and `service_provider_id` are populated on the GymAxis org → these are the Orbit 4 user ids to pass into the mappers.

---

