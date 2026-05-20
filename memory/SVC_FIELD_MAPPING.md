> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> Service Ops field mapping below is unchanged. Worth noting the new
> activation-bus side effects (NOT a Sicon/Sage data flow, internal-
> only):
>
> - On engineer escalation from `issues.py`, the `_mirror_issue_to_svc_case`
>   helper copies the issue into `svc_cases`. The same record then
>   shows in CRM via `/api/crm/v2/companies/{id}/timeline`.
> - `first_fault_logged` fires once per org on the first issue intake
>   (best-effort, never blocks intake).

---


# GymAxis Service Operations — Sicon Service / Sage 200 Field Mapping
**Iter 215dp · Feb 2026 · Source-of-truth for Service Ops cross-system data flow**

> ⚠️ **From iter 215dy onwards, the master mapping document is**
> [`INTEGRATION_FIELD_MAPPING.md`](./INTEGRATION_FIELD_MAPPING.md). It
> covers every GymAxis module (Service Ops, CRM, Memberships, Operations,
> Equipment) and the credentials matrix. **This file remains authoritative
> for sections 2-18 (Service-Ops-only detail)**; the master file
> deliberately points back here rather than duplicating the long tables.
>
> Whenever a new field is added to any `svc_*` collection it MUST be entered
> in this table with its Sicon Service and Sage 200 mapping (or marked
> `gymaxis_only` with a reason). Lint rule: **"if it isn't in this table or
> the master file, it doesn't ship."**

---

## 1. Source-of-truth ownership

| Domain | Master | Reason |
|---|---|---|
| Customer / Account financials | **Sage 200** | `SLCustomerAccountID`, statements, ledgers, nominal codes |
| Customer / Account commercial enrichment | **GymAxis CRM** | usage, NPS, marketing consent — Sage doesn't care |
| Site / sub-location | **GymAxis** | front-line operators keep this current |
| Equipment register | **Sicon** (read) / **GymAxis** (display) | Sicon `EquipmentIDs` is the master; GymAxis enriches with QR / photos |
| Engineer roster (employee records) | **Sage 200 / Sicon** | `Employee` / `AppointmentResource` |
| Engineer day-to-day activity | **GymAxis** | mobile app is primary engineer UX; Sicon receives a sync |
| Service case lifecycle | **GymAxis** (post-cutover) / **Sicon** (during cutover) | bidirectional bridge until Phase 8 |
| Parts catalogue & van stock | **GymAxis** | new capability — not in Sicon |
| Invoice posting | **Sage 200** | only Sage issues invoices |

---

## 2. `svc_cases` ↔ Sicon `ServiceCall` ↔ Sage

| GymAxis field | Sicon `ServiceCall` field | Sage 200 field | Direction | Notes |
|---|---|---|---|---|
| `id` | `OurReference` (string) | — | GymAxis → Sicon | UUID stored on Sicon for back-link |
| `reference` (`SVC-00123`) | `CallReference` | — | GymAxis → Sicon | Customer-facing reference |
| `organization_id` | (implicit via Sicon company) | `SLCustomerAccountID` | GymAxis → Sicon | Resolved through CRM company |
| `status` | `StatusID` (mapped enum) | — | bidirectional | See §6 status crosswalk |
| `priority` (`p1…p4`) | `PriorityID` | — | GymAxis → Sicon | `p1=1, p2=2, p3=3, p4=4` |
| `cover_type` (`contract\|warranty\|chargeable\|ppm`) | `CallTypeID` | `NominalCode` (per type) | GymAxis → Sicon, Sage receives via Sicon | Drives nominal posting |
| `title` | `Description` (truncate 80) | — | GymAxis → Sicon |  |
| `description` | `Notes` (long text) | — | GymAxis → Sicon |  |
| `fault_code` | `FaultCodeID` | — | GymAxis → Sicon | `fault_codes.py` maps internal → Sicon ID |
| `fault_category` | `FaultCategoryID` | — | GymAxis → Sicon |  |
| `asset_id` (GymAxis equipment doc id) | resolved → `EquipmentIDs[0]` | — | GymAxis → Sicon | Lookup by serial |
| `asset_name` | display-only | — | GymAxis only | Cached for offline mobile |
| `equipment_ids[]` (multi-select at intake) | `EquipmentIDs[]` | — | GymAxis → Sicon | Multi-equipment cases — site-wide outages, paired machines |
| `equipment_serials[]` | `EquipmentSerials[]` (custom) | — | GymAxis → Sicon | Free-text for kit not yet in the register |
| `allocated_parts[]` (intake-time triage + van pulls) | `Parts[]` (PartCode/Description/Quantity/Source) | Sage `Stock.Code` lookup via `sage_stock_code` | GymAxis → Sicon → Sage | Source = warehouse \| van; engineer_id when from van |
| `required_skills[]` | `RequiredSkills[]` | — | GymAxis → Sicon | Drives the auto-assign scoring engine |
| `site_postcode` | (Sicon SubLocation `LocationPostCode`) | — | GymAxis → Sicon | Used by the geo scoring helper |
| `site_id` | `SubLocation.SiconSubLocationID` | — | GymAxis → Sicon |  |
| `site_name` | `SubLocation.Description` | — | GymAxis → Sicon |  |
| `contract_id` | `ContractID` | — | GymAxis → Sicon |  |
| `customer_name` / `customer_email` / `customer_phone` | `ContactName` / `ContactEmail` / `ContactPhone` | (CRM passes through) | GymAxis → Sicon |  |
| `assigned_engineer_id` | `AssignedToSageUserID` | Sage `Employee.SageUserID` | bidirectional | Sicon overrides GymAxis on conflict |
| `assigned_engineer_name` | `AssignedToSageUser` | Sage `Employee.FullName` | Sicon → GymAxis | read-only |
| `scheduled_at` | `ScheduledDateTime` (or first `Appointment.StartDateTime`) | — | bidirectional |  |
| `estimated_minutes` | `EstimatedMinutes` | — | GymAxis → Sicon |  |
| `sla_response_at` / `sla_resolve_at` | `SLATargetResponseAt` / `SLATargetResolveAt` | — | GymAxis → Sicon | Recomputed on cover_type change |
| `sla_paused_at` | `SLAPausedAt` (custom field) | — | GymAxis → Sicon | Pause/resume audited |
| `closed_at` | `CompletedDateTime` | — | bidirectional |  |
| `created_at` | `LoggedDateTime` | — | GymAxis → Sicon |  |
| `source` (`portal\|phone\|email\|whatsapp`) | `LoggedByMethod` (custom field) | — | GymAxis → Sicon |  |
| `logged_by_id` / `logged_by_name` | `LoggedBySageUserID` / `LoggedByUserName` | — | GymAxis → Sicon |  |
| `attachments[]` | `/Service/Calls/{id}/Attachments` (separate POST per file) | — | GymAxis → Sicon |  |
| `tags[]` | `Tags` (semicolon-joined string in Sicon) | — | GymAxis → Sicon |  |

---

## 3. `svc_case_events` ↔ Sicon `TrackingNote`

| GymAxis field | Sicon field | Direction | Notes |
|---|---|---|---|
| `id` | `TrackingNote.OurReference` | GymAxis → Sicon |  |
| `case_id` → `reference` | `ServiceCallReference` | GymAxis → Sicon |  |
| `type` (`intake\|note\|state_change\|edit\|comm\|photo\|signature`) | `NoteTypeID` (mapped enum) | GymAxis → Sicon | See §6 type crosswalk |
| `body` | `NoteText` | GymAxis → Sicon |  |
| `from_state` / `to_state` (state_change) | `NoteText` (formatted: "X → Y · reason") | GymAxis → Sicon |  |
| `actor_id` / `actor_name` | `CreatedBySageUserID` / `CreatedByUserName` | GymAxis → Sicon |  |
| `at` | `CreatedDateTime` | GymAxis → Sicon |  |
| `extra.changes[]` (edit) | rendered into `NoteText` | GymAxis → Sicon |  |
| `extra.visibility` (`internal\|customer`) | `VisibleToCustomer` (bool) | GymAxis → Sicon |  |
| `extra.visibility` (`engineer-only`) | `VisibleToEngineer` (bool) | GymAxis → Sicon |  |

---

## 4. `svc_engineers` ↔ Sage `Employee` ↔ Sicon `AppointmentResource`

**Source of truth = Sage 200**. GymAxis copy is a denormalised cache for the mobile UX so the app works without a live Sage call.

| GymAxis field | Sage Employee field | Sicon field | Direction | Notes |
|---|---|---|---|---|
| `id` | — | `AppointmentResource.ResourceID` | Sage → GymAxis (mirror) |  |
| `sage_user_id` | `SageUserID` | `AppointmentResource.SageUserID` | Sage → GymAxis | natural key |
| `full_name` | `FullName` | `AppointmentResource.Name` | Sage → GymAxis |  |
| `email` | `Email` | — | Sage → GymAxis |  |
| `mobile` | `Mobile` | — | Sage → GymAxis |  |
| `home_address.line1…postcode` | Sage employee address | — | Sage → GymAxis | for routing engine |
| `vehicle_reg` | (custom field) | — | gymaxis_only | not in Sage; PPE reasons |
| `skills[]` | (custom Sage field) | `AppointmentResource.Skills` | bidirectional |  |
| `working_hours` | Sage rota | `AppointmentResource.WorkingPattern` | Sage → GymAxis |  |
| `tracker_token` | — | — | gymaxis_only | scoped JWT for engineer mobile only |

---

## 5. `svc_time_entries` ↔ Sicon `Appointment` & Sage timesheet

| GymAxis field | Sicon `Appointment` field | Sage field | Direction | Notes |
|---|---|---|---|---|
| `id` | `Appointment.OurReference` | — | GymAxis → Sicon |  |
| `case_id` → `reference` | `Appointment.ServiceCallReference` | — | GymAxis → Sicon |  |
| `engineer_id` → `sage_user_id` | `Appointment.ResourceID` | `Timesheet.SageUserID` | GymAxis → Sicon → Sage |  |
| `start_at` | `Appointment.StartDateTime` | `Timesheet.StartTime` | GymAxis → Sicon |  |
| `end_at` | `Appointment.EndDateTime` | `Timesheet.EndTime` | GymAxis → Sicon |  |
| `category` (`travel\|on_site\|admin`) | `Appointment.AppointmentTypeID` | `Timesheet.ActivityCode` | GymAxis → Sicon |  |
| `chargeable` | `Appointment.Chargeable` | `Timesheet.Billable` | GymAxis → Sicon |  |
| `duration_minutes` (computed) | derived | `Timesheet.Hours` | GymAxis → Sicon |  |
| `notes` | `Appointment.Notes` | — | GymAxis → Sicon |  |

---

## 6. `svc_signatures` ↔ Sicon `CompletionSignature`

| GymAxis field | Sicon field | Direction | Notes |
|---|---|---|---|
| `id` | `CompletionSignature.OurReference` | GymAxis → Sicon |  |
| `case_id` → `reference` | `CompletionSignature.ServiceCallReference` | GymAxis → Sicon |  |
| `signed_by_name` | `CustomerName` | GymAxis → Sicon |  |
| `signed_by_role` | `CustomerRole` | GymAxis → Sicon |  |
| `signed_at` | `SignedAt` | GymAxis → Sicon |  |
| `image_url` (PNG, base64-encoded SVG → PNG) | `SignatureImage` (base64) | GymAxis → Sicon |  |
| `summary` (engineer's fix description) | `WorkDoneSummary` | GymAxis → Sicon |  |
| `device_meta` (UA, geo) | (custom) | gymaxis_only | audit-only |

---

## 7. `svc_engineer_photos` ↔ Sicon `ServiceCallAttachment`

| GymAxis field | Sicon field | Direction | Notes |
|---|---|---|---|
| `id` | `Attachment.OurReference` | GymAxis → Sicon |  |
| `case_id` → `reference` | `Attachment.ServiceCallReference` | GymAxis → Sicon |  |
| `file_url` | `Attachment.FileURL` | GymAxis → Sicon | uploaded via `/api/files/upload` first |
| `mime_type` | `Attachment.ContentType` | GymAxis → Sicon |  |
| `caption` | `Attachment.Description` | GymAxis → Sicon |  |
| `taken_at` | `Attachment.CreatedAt` | GymAxis → Sicon |  |
| `taken_by_id` / `taken_by_name` | `CreatedBySageUserID` / `CreatedByUserName` | GymAxis → Sicon |  |
| `geo` (lat/lng) | (custom) | gymaxis_only | proof-of-attendance |

---

## 8. Status crosswalk (`svc_cases.status` ↔ Sicon `ServiceCall.StatusID`)

| GymAxis state | Sicon status | Notes |
|---|---|---|
| `new` | `Logged` | initial |
| `triaged` | `Triaged` |  |
| `assigned` | `Assigned` |  |
| `en_route` | `EnRoute` |  |
| `on_site` | `OnSite` |  |
| `paused_parts` | `OnHoldAwaitingParts` | SLA pause flag set both sides |
| `paused_customer` | `OnHoldAwaitingCustomer` | SLA pause |
| `repaired` | `Repaired` |  |
| `awaiting_sign_off` | `AwaitingCustomerSignOff` |  |
| `closed` | `Completed` | triggers Sage invoice draft if chargeable |
| `invoiced` | `Invoiced` | Sage `Invoice.SLInvoiceID` linked back |
| `rejected` | `Cancelled` |  |

## 9. Note-type crosswalk (`svc_case_events.type` ↔ Sicon `NoteTypeID`)

| GymAxis type | Sicon `NoteTypeID` |
|---|---|
| `intake` | `Logged` |
| `note` | `EngineerNote` (visibility=internal) / `CustomerNote` (visibility=customer) |
| `state_change` | `StatusChange` |
| `edit` | `RecordEdit` |
| `comm` | `Communication` |
| `photo` | `Attachment` |
| `signature` | `CompletionSignature` |
| `time_start` / `time_stop` | `Timesheet` |

---

## 10. Sage 200 cover-type → nominal mapping

| GymAxis `cover_type` | Sage Nominal | Reasoning |
|---|---|---|
| `contract` | `4001 — Service Contract Revenue` | recurring; recognised over period |
| `warranty` | `4002 — Warranty (zero-rated)` | not customer-billed |
| `chargeable` | `4010 — Chargeable Service` | ad-hoc invoice |
| `ppm` | `4003 — PPM Revenue` | scheduled preventive |

(Codes are placeholders — to be confirmed with Pulse Fitness finance before live Sage push.)

---

## 11. Process rule going forward

1. Adding a field to a Pydantic model in `models/svc/*.py` requires an inline annotation:
   ```python
   class Case(BaseModel):
       priority: str = Field(..., description="sicon: ServiceCall.PriorityID; sage: n/a")
   ```
2. The CI lint job (TODO Phase 8 cutover) parses these descriptions and fails the build if any non-private field is missing the `sicon:` / `sage:` prefix.
3. The mapping table in this doc is the source of truth — code annotations must agree with this file. If they diverge, **this file wins** and the code is corrected.

---

**Owner**: GymAxis Engineering · iter 215dp · Feb 2026

---

## 12. `svc_parts` ↔ Sage `Stock` ↔ Sicon parts catalogue

| GymAxis field | Sage Stock field | Sicon field | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only |  |
| `sku` | `StockCode` | `PartCode` | bidirectional | Pulse Fitness syncs from Sage |
| `name` | `Description` | `Description` | bidirectional |  |
| `manufacturer` | `Manufacturer` (custom) | `Manufacturer` | Sage → GymAxis |  |
| `supplier` | `Supplier.Name` | `Supplier.Name` | Sage → GymAxis |  |
| `cost` | `LastCost` | — | Sage → GymAxis |  |
| `lead_time_days` | `LeadTimeDays` | — | Sage → GymAxis |  |
| `sage_stock_code` | `StockCode` | — | Sage → GymAxis | natural key on Sage side |
| `sicon_part_id` | — | `PartID` | Sicon → GymAxis | natural key on Sicon side |

## 13. `svc_van_stock` ↔ Sicon engineer van inventory

| GymAxis field | Sicon field | Direction | Notes |
|---|---|---|---|
| `engineer_id` | `Engineer.SageUserID` | bidirectional |  |
| `part_sku` | `Part.PartCode` | bidirectional |  |
| `qty` | `VanQuantity` | bidirectional |  |
| `min_qty` / `max_qty` | reorder rules (Phase 4) | bidirectional |  |

## 14. `svc_part_movements` ↔ Sicon `PartMovement`

| GymAxis field | Sicon field | Direction | Notes |
|---|---|---|---|
| `id` | `PartMovement.OurReference` | GymAxis → Sicon |  |
| `case_id` → `reference` | `ServiceCallReference` | GymAxis → Sicon |  |
| `movement_type` (`allocate\|deallocate\|consume\|transfer`) | `MovementTypeID` | GymAxis → Sicon |  |
| `part_sku` | `Part.PartCode` | GymAxis → Sicon |  |
| `qty` | `Quantity` | GymAxis → Sicon |  |
| `source` (`warehouse\|van`) | `FromLocation` | GymAxis → Sicon |  |
| `engineer_id` | `Engineer.SageUserID` | GymAxis → Sicon |  |
| `at` | `MovedAt` | GymAxis → Sicon |  |

## 15. `svc_purchase_orders` ↔ Sage `POPOrder` ↔ Sicon Order

| GymAxis field | Sage Order field | Sicon field | Direction | Notes |
|---|---|---|---|---|
| `id` | — | — | gymaxis_only |  |
| `reference` (`PO-00001`) | `OrderReference` | `OrderReference` | bidirectional | natural key |
| `supplier` | `Supplier.Name` | `Supplier.Name` | bidirectional |  |
| `supplier_email` | `Supplier.Email` | — | GymAxis → Sage |  |
| `status` (`draft\|submitted\|received\|cancelled`) | `OrderStatus` | `OrderStatus` | bidirectional |  |
| `lines[].part_sku` | `OrderLine.StockCode` | `OrderLine.PartCode` | bidirectional |  |
| `lines[].qty` | `OrderLine.Quantity` | `OrderLine.Quantity` | bidirectional |  |
| `lines[].received_qty` | `OrderLine.ReceivedQuantity` | `OrderLine.ReceivedQuantity` | bidirectional |  |
| `lines[].unit_cost` | `OrderLine.UnitCost` | — | bidirectional |  |
| `lines[].sage_stock_code` | `OrderLine.StockCode` | — | Sage → GymAxis | echo natural key |
| `lines[].sicon_part_id` | — | `OrderLine.PartID` | Sicon → GymAxis |  |
| `total` | `OrderTotal` | — | derived |  |
| `submitted_at` | `OrderDate` | `OrderDate` | GymAxis → Sage/Sicon |  |
| `received_at` | `ReceivedDate` | `ReceivedDate` | GymAxis → Sage/Sicon |  |

## 16. `svc_warehouse_stock` ↔ Sage `Stock.QtyInStock` ↔ Sicon `WarehouseStock`

| GymAxis field | Sage field | Sicon field | Direction | Notes |
|---|---|---|---|---|
| `location` | `WarehouseCode` | `WarehouseID` | bidirectional |  |
| `part_sku` | `Stock.StockCode` | `Part.PartCode` | bidirectional |  |
| `qty` | `Stock.QtyInStock` | `WarehouseStock.Quantity` | bidirectional |  |

---

## 17. AI artefacts — `svc_ai_calls` and `svc_engineer_photos.ai`

These are *internal* GymAxis records (not synced to Sicon/Sage) used for
observability and to avoid re-paying the LLM cost on the same photo.

| GymAxis field | Notes |
|---|---|
| `svc_ai_calls.kind` | `triage \| photo_classify \| summary \| tiebreak` |
| `svc_ai_calls.latency_ms` | observability — flag p95 > 5s |
| `svc_ai_calls.ok` | false when Claude returned malformed JSON or the call errored |
| `svc_engineer_photos.ai` | `{tags, severity, summary, at}` cached on the photo doc on first classify |

---

## 18. `svc_quotes` ↔ Sage `SLInvoice` (line composition)

GymAxis quotes are an internal pre-invoice artefact; their lines drive
the Sage `SLInvoice.Lines[]` payload pushed via `svc_sage_invoice_outbox`.

| GymAxis field | Sage field | Direction | Notes |
|---|---|---|---|
| `id` | — | gymaxis_only | local quote uuid |
| `reference` (`Q-00001`) | `SLInvoice.QuoteReference` (custom) | GymAxis → Sage | for finance trace-back |
| `case_id` → case `id` | `SLInvoice.OurReference` | GymAxis → Sage |  |
| `total` (gross) | `SLInvoice.GrossAmount` (derived) | GymAxis → Sage |  |
| `lines[].kind=labour` | `SLInvoiceLine` with NominalCode = chargeable nominal | GymAxis → Sage |  |
| `lines[].kind=part` | `SLInvoiceLine.StockCode = sage_stock_code or part_sku` | GymAxis → Sage |  |
| `lines[].kind=adjustment` | extra `SLInvoiceLine` (discount or surcharge) | GymAxis → Sage |  |
| `lines[].qty` | `SLInvoiceLine.Quantity` | GymAxis → Sage |  |
| `lines[].unit_amount` | `SLInvoiceLine.UnitNetAmount` | GymAxis → Sage |  |
| `lines[].nominal_code` | `SLInvoiceLine.NominalCode` | GymAxis → Sage | overrides cover-type default |
| `lines[].tax_code` | `SLInvoiceLine.TaxCode` | GymAxis → Sage |  |
| `vat_rate` / `discount_pct` | applied client-side; net/vat carried in payload | GymAxis → Sage |  |
| `status` (`draft\|approved\|invoiced\|void`) | — | gymaxis_only | Sage status owned by `svc_sage_invoice_outbox.status` |
| `version` + `history[]` | — | gymaxis_only | quote revisions / audit |

The `svc_sage_invoice_outbox.status` lifecycle is now:
`pending` (case closed, no quote yet) → `ready` (quote finalised) → `submitted` (worker delivered, Phase 8) → `posted` (Sage invoice id returned) | `failed`.
