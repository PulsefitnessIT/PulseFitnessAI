# CHANGELOG

## 2026-06 — Duplicate-invoice guard surfaced in the AI review panel (before Apply)
- The AI review panel now shows a prominent red "Duplicate invoice — already allocated" banner
  (dealer name + allocated date) BEFORE Apply, driven by `aiReview.duplicate`. Since the deterministic
  scanners now return duplicate info (see prior entry), this fires for CSV/PDF fast paths too, not just LLM.
- Added a required acknowledgment checkbox (data-testid dp-wiz-ai-review-dup-ack): when a duplicate is
  detected the Apply button (dp-wiz-ai-review-apply) is disabled and relabelled until the user ticks
  "I understand — apply anyway to review". `dupAck` state resets on each new parse and on reset().
- Files: frontend/src/pages/DealerWarrantyParts/AllocationWizardTab.js.
- Verified backend chain via curl: seeded a fake allocation for INV-2051 → re-parsing the sample CSV
  returned duplicate_invoice=true with dealer name; test record cleaned up afterward.


## 2026-06 — Invoice-number capture for the fast (deterministic) invoice scanners
- Problem: only the LLM parse path returned an invoice number; the fast deterministic PDF and
  spreadsheet scanners returned order_reference="", so the wizard's Invoice-number field stayed empty
  after Apply for the common fast path.
- Added `_extract_invoice_number(text)` in routes/dealer_parts_data.py — label-driven, most-specific-first
  (Tax Invoice/Invoice No/Invoice #/Inv/Credit Note/Document/Sales Order/Order Ref), value must contain a
  digit, isn't a date, isn't a stop-word (TOTAL/DATE/etc). Correctly skips "Invoice Date 12/06/2026".
- Wired into `_scan_pdf_invoice` (scans extracted text) and `_scan_spreadsheet_invoice` (scans a joined
  blob of the first 60 rows' cells). `_parse_and_match_invoice` now passes the detected order_reference
  through for both branches, appends it to the note, and runs `_invoice_duplicate_info` so a repeat
  invoice number is flagged on upload for these paths too (previously LLM-only).
- Frontend needed no change — it already maps res.order_reference → aiReview and setInvoiceRef on Apply.
- Verified via curl on both samples: /app/test_samples/dealer_invoice_sample.csv → INV-2051;
  /app/test_samples/dealer_invoice_sample.pdf → INV-3090 (order value + matches also correct).


## 2026-06 — Intelligence made the org default (Pulse Fitness Ltd) + Input import fix
- Owner opted to make wizard intelligence ON by default: `blend_actuals=true, blend_weight_pct=40,
  trend_sensitivity=med`. Set the org-level `dealer_parts_data_settings` doc for Pulse Fitness Ltd
  (`3ece2d0c-...`) AND `iso-demo-org` (the org that actually holds the dealer-parts warranty plan +
  4879 BOM machines in this preview, so it's testable now). NOT changed globally — DEFAULT_DATA_SETTINGS
  stays off so other/new orgs remain opt-in, per owner's "just Pulse Fitness Ltd" scope.
  Duplicate-avoidance (netting vs dealer held/on-order stock) is unaffected — blend/trend only change the
  target quantity; `send = max(0, target − already_held_or_allocated)` still runs on top.
- Fixed pre-existing blocking lint: `frontend/src/pages/LiteDashboard/LiteDialogs.js` used `<Input>`
  without importing it — added `import { Input } from '@/components/ui/input'`.
- NOTE for future agent: in this preview the Dealer Parts module data lives under `iso-demo-org`,
  not Pulse Fitness Ltd — confirm which org holds the live dealer-parts data in production before
  changing dealer-parts settings there.


## 2026-06 — Dealer Parts Allocation Wizard: Smarter Recommendations, Tunable Thresholds, AI Review Step
Owner asked for three wizard improvements (b, c, d). All shipped, tested (frontend E2E 100%, backend curl-verified), demo org reset to opt-in defaults.

- (b) SMARTER RECOMMENDATIONS — backend `recommend_from_invoice` now optionally BLENDS real
  historical usage into the warranty-plan quantities and applies a usage-TREND multiplier.
  New settings in `DEFAULT_DATA_SETTINGS`: `blend_actuals` (bool), `blend_weight_pct` (0-100),
  `trend_sensitivity` (off/low/med/high). `_trend_multiplier()` maps increasing/new_failure_trend→up,
  decreasing/dormant→down. Blend applies to plan parts (needs a plan baseline); trend applies to both
  plan parts and usage/supplementary items. Item `reason` strings explain the maths. Response returns
  an `intelligence` block. UI: collapsible "Recommendation intelligence" card on Step 0
  (data-testid dp-wiz-intel-*), saves instantly via PUT /data/settings; Step-1 badge dp-wiz-intel-badge.
- (c) TUNABLE THRESHOLDS — per-machine-group Plan-vs-Actuals sensitivity overrides. New collection
  `dealer_parts_pva_overrides` + endpoints GET /data/pva-thresholds, POST /data/pva-thresholds/override,
  DELETE /data/pva-thresholds/override/{group}. `plan_vs_actuals` loads overrides and returns per-machine
  over_pct/under_pct/threshold_overridden. UI: per-machine override editor in PlanVsActualsPanel.js
  (dp-wiz-pva-override-*), plus a quick "reset" next to the override badge.
- (d) AI PARSING REVIEW STEP — `parseInvoice` no longer auto-populates the form. It now stores an
  `aiReview` object and renders a confirm panel (dp-wiz-ai-review) listing extracted machines with
  matched/unmatched badges, editable qty, removable rows. Form fills ONLY on Apply (dp-wiz-ai-review-apply);
  Discard clears with no side-effects. Duplicate-invoice detection surfaced in the review panel.
- Files: backend/routes/dealer_parts_data.py; frontend AllocationWizardTab.js, PlanVsActualsPanel.js, api.js.
- Sample matching invoice for testing: /app/test_samples/dealer_invoice_sample.csv.
- Non-blocking follow-ups noted by review: AllocationWizardTab.js now ~809 lines (could split
  IntelligenceCard/AIReviewPanel/MachinePicker); dev-only <span>-in-<option> hydration warning (harmless).


## 2026-06 — Equipment Sales: Customer Register Handover

Push a deal's GRN-created equipment into the customer's OWN Pulse portal so they can log faults from day one — into the existing equipment/company processes, no new module.

- **Backend** `routes/crm_quote_handover.py`: `POST /crm/v2/quotes/{id}/handover/register` copies each deal-registered equipment unit into the customer's portal org (resolved via `crm2_companies.tenant_org_id`), stamping provenance (`source=deal_handover`, `origin_org_id`, `origin_equipment_id`, `quote_id`); the seller row records `customer_equipment_id`. `GET /{id}/handover` now returns a `customer_portal` block (linked, tenant name, registered/handed-over/pending counts). 400 when the company has no linked portal.
- **Provenance quality** (post-report fixes): copied unit's `supplier` = the SELLING org (not the customer); `user_id` left unset when the customer org has no users (no cross-tenant id); `site_id` = customer's head-office/only site else unset; idempotency now keyed on the customer copy still existing, so a deleted copy is re-pushable (repair path).
- **Frontend** `CRM/CRMQuoteHandover.js`: "Customer register handover" section — shows link status + "X/Y pushed to <portal>", a "Hand over N unit(s)" button, and "All handed over ✓".
- VERIFIED: testing_agent backend 5/5 pytest + frontend 6/6 e2e; provenance fixes re-confirmed via curl (supplier=selling org, user_id=None, re-push after deletion=1). Test: `/app/backend/tests/test_crm_quote_customer_handover_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 4: handover & close

Into the existing quote + service-jobs (`issues`) processes — no new module. Completes the Equipment-Sales journey (Phases 1–4).

- **Backend NEW** `routes/crm_quote_handover.py` (`/crm/v2/quotes`): `GET /{id}/handover` (linked jobs + install-job suggestions + completion readiness), `POST /{id}/handover/jobs` (auto = one install job per registered equipment unit, or explicit specs — created as real `db.issues` jobs on the Operations board, stamped with quote_id/equipment/source=`deal_handover`), `POST /{id}/complete` (only when fully delivered + invoiced; managers force with a reason), `POST /{id}/reopen`. Readiness reuses the invoicing + fulfilment views. Registered in `route_registry/crm.py`.
- **Frontend NEW** `CRM/CRMQuoteHandover.js` (`QuoteHandoverPanel`): deal-status badge, linked-jobs list, "Auto-create install jobs" + "Add job" dialog, a delivered/invoiced/open-jobs checklist, "Complete deal" (disabled with reasons until ready), "Complete anyway" force dialog, and Reopen. Mounted in `CRMCPQ.js` QuoteDetail below the fulfilment panel.
- **Polish** (post-report): reopen now clears the forced/reason residue and 400s when already open; the misleading svc_case mirror call removed (jobs already land on the ops board); completion reasons formatted as currency (£5,000.00); jobs checklist row shown as informational ("doesn't block close"); auto-jobs spec copies fixed.
- VERIFIED: testing_agent backend 8/8 pytest + full frontend flow (incl. force-complete + reopen); polish re-confirmed via curl (8/8 pytest still green). Test: `/app/backend/tests/test_crm_quote_handover_phase4_aug2026.py`.

### Equipment Sales — ALL 4 PHASES COMPLETE (into the existing CPQ engine, one engine for Pulse Fitness Ltd + Global Dealers)
P1 line types (trade-ins/spares/contracts) · P2 staged invoicing + credit notes · P3 PO-from-quote + GRN auto-equipment · P4 handover jobs + Complete Deal.


## 2026-06 — Equipment Sales into CPQ, Phase 3: fulfilment (PO-from-quote + GRN auto-equipment)

Into the existing quote → purchase_orders → equipment processes (no new module).

- **Backend NEW** `routes/crm_quote_fulfilment.py` (`/crm/v2/quotes`): `GET /{id}/fulfilment` (procurable lines + POs + created equipment + summary), `POST /{id}/purchase-orders` (build a PO from the deal's sale/spare lines priced at COST, into `purchase_orders`, linked by quote_id; trade-ins excluded), `POST /{id}/purchase-orders/{poId}/status`, `POST /{id}/purchase-orders/{poId}/receive` (GRN → auto-creates `equipment` records, one per serial, valued at the SELL price, source=`deal_grn`, traceable via quote_id/po_number). Registered in `route_registry/crm.py`.
- **Root-cause fix (critical)**: CPQ v2 quote lines now get a stable `id` at create/revise (`crm_v2._normalize_quote_line`), and `crm_quote_fulfilment` heals legacy quotes on read. Previously ids were minted per-request so Raise-PO always 400'd. GRN now rejects unknown line ids / empty receipts (422).
- **Frontend NEW** `CRM/CRMQuoteFulfilment.js` (`QuoteFulfilmentPanel`): raise-PO dialog (pick lines + supplier), PO rows with status, GRN dialog (qty + comma-separated serials), and an "Equipment registered from this deal" chip list. Mounted in `CRMCPQ.js` QuoteDetail below the invoicing panel. GRN submit disabled until a qty is entered.
- VERIFIED: testing_agent pytest now 9/9 (was 6/9 before the line-id fix); happy-path + guards confirmed; frontend GRN→equipment flow passed. Test: `/app/backend/tests/test_crm_quote_fulfilment_phase3_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 2: staged invoicing + running balance + credit notes

Deposit / interim / final payments on a CPQ v2 quote — built into the existing quote process, no new module.

- **Backend NEW** `routes/crm_quote_invoicing.py` (router `/crm/v2/quotes`): schedule stored on `crm2_quotes.invoice_schedule`; invoice + credit-note records in `crm2_invoices`. Endpoints: `GET /{id}/invoicing` (stages + invoices + running-balance summary), `PUT /{id}/schedule`, `POST /{id}/schedule/auto` (deposit/interim/final preset), `POST /{id}/stages/{sid}/invoice|pay|credit-note`. Running balance = total − paid − credited; per-stage outstanding tracked. Registered in `route_registry/crm.py`.
- **Guards**: can't drop an already-invoiced stage (400); can't over-schedule beyond deal total (422); percent capped 0–100 / amounts ≥ 0; can't invoice beyond deal total (400); can't overpay a stage (422); auto percentages must total 100 (422).
- **Frontend NEW** `CRM/CRMQuoteInvoicing.js` (`QuoteInvoicingPanel`, `canManage` from useAuth): running-balance cards, quick presets (25/75, 50/50, thirds), inline schedule editor with over-schedule warning + guarded save, per-stage Raise invoice / Record payment / Credit note dialogs. Mounted in `CRMCPQ.js` QuoteDetail under the line-items table.
- VERIFIED by testing_agent: backend 13/13 pytest, frontend panel flows 100%. Full lifecycle numbers confirmed (deposit→pay→final invoice→part-pay→credit note; balance 10000→7500→2500→1500). Over-schedule/over-invoice guards added after the report and re-verified via curl. Test: `/app/backend/tests/test_crm_quote_staged_invoicing_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 1: line types (trade-ins, spares, contracts)

Extending the EXISTING CRM Quote (CPQ v2) engine — no new module — to cover ServiceGeeni-style equipment sales, for Pulse Fitness Ltd AND Global Dealers (one engine, confirmed by user).

- **Backend** `crm_v2.py`: new `compute_quote_totals()` + `_normalize_quote_line()`. Each quote line carries `line_type` ∈ {sale, spare_part, service_contract, trade_in}. Trade-ins are entered as a positive allowance but applied as NEGATIVE net (`net_subtotal`), reducing the deal. Returns a per-category breakdown (equipment/parts/contract/trade_in) + `gross_profit`/`gross_margin_percent` (None when net ≤ 0). Used by both `create_quote` and `revise_quote`.
- **Backend** `crm_product_perms.py`: `gross_profit`/`gross_margin_percent` added to `QUOTE_COST_FIELDS` so cost-blind reps don't see deal margin.
- **Backend** `crm_quote_pdf.py`: `_line_net()` prefers `net_subtotal` and signs trade-ins negative.
- **Frontend** `CRM/CRMCPQ.js`: per-line Type selector (`quote-line-type-{i}`), trade-in "credit to customer" hint, live category breakdown rows (`quote-parts-subtotal`, `quote-contract-subtotal`, `quote-tradein-total`), net Subtotal/Total, margin badge; detail view shows a Type column with trade-ins rendered negative. Added `quote-submit-btn`/`quote-cancel-btn` testids and a static column header row.
- VERIFIED by testing_agent (backend 7/7 pytest, frontend builder + detail e2e 100%). Test: `/app/backend/tests/test_iter294_cpq_line_types.py`.

### Equipment Sales roadmap (agreed phases — into existing processes)
- Phase 1 ✅ trade-ins + spares + service-contract line types with live totals/margin
- Phase 2 (money): staged invoicing (deposit/interim/final) + running balance + credit notes → Quote + financial_ops/invoice_dunning
- Phase 3 (fulfilment): PO-from-quote + GRN auto-equipment + supplier/location transfers with delivery tracking → purchase_orders/equipment/equipment_transfer
- Phase 4 (handover + close): sales→service job handover (issues) + deal P&L (roll in PO/job costs) + "Complete Deal" action
- Known follow-ups: cost input on manual quote lines (margin badge only lights up on catalogue lines today); no single GET /crm/v2/quotes/{id} or DELETE endpoint.


## 2026-06 — 4 bug fixes: job-role chips, Forgot Password, archive layout, operator-portal context

- **Bug 1 (Job roles)** `LiteDashboard/staffing/HRTab.js`: built-in role chips in the "Manage job roles" modal are now clickable buttons (`job-roles-builtin-{role}`) that populate the "Add a role" input. VERIFIED by testing_agent (owner@isodemo.com, 9/9 chips).
- **Bug 2 (Forgot Password)** root causes fixed & VERIFIED:
  - `utils/security.py`: split the single 3/15min limiter into `rate_limit_password_reset` (requests, key `resetreq:`, 5/15min) and NEW `rate_limit_password_reset_submit` (submissions, key `resetsubmit:`, 15/15min). `routes/auth.py` reset-password now uses the submit limiter. Previously a user who requested a link then mistyped their new password 2-3× got locked out (429).
  - `pages/ResetPasswordPage.js`: live password-requirements checklist (12+/upper/lower/digit/symbol, `reset-password-rules`) mirroring backend policy; client-side validation before POST; minLength 12 on both fields; added `CaptchaWidget` to the request form (was missing the captcha token → would 400 in prod if captcha enabled).
- **Bug 3 (Archive layout)** `MasterAdmin/AdminOrganizations.js`: org-user row no longer collapses the name/email into a vertical one-letter column when extra buttons appear (archived). Name column reserves `sm:w-60 flex-shrink-0` + `truncate`; actions use `sm:flex-1` and wrap. NOTE: verified by code only — live master-admin UI check blocked by TOTP MFA.
- **Bug 4 (Pulse Fitness Portal)** `routes/auth.py` `/auth/refresh` + `utils/auth.py`: refresh now PRESERVES the `act_org` (and `imp_grants`) JWT claim via `extra_claims`. Previously the frontend's on-load/15-min refresh minted a token without `act_org`, silently reverting a master admin out of the operator company (Pulse Fitness Ltd) back to their home org within seconds — cause of "portal shows no data" and "reverts to Head Office after visiting CRM". VERIFIED by curl: refreshed act_org token still returns the 6 Pulse Fitness Ltd staff. Live master-admin UI check blocked by MFA.


## 2026-06 — MOD Tender pack (LSL/DC/0223) finalised in-place

Edited all 6 `.docx` responses in place (templates, images, headers/footers, tables preserved) against Red Team reviews + Sheen/Director comments. Then a tender-writer QA pass drove a final correction round.

### Final correction round (tender-writer QA)
- **Figures embedded**: user-supplied corrected process maps for 2.2A (UK) and 2.3A (overseas) swapped into `word/media/image3.png` in each docx, with drawing extents adjusted to the new aspect ratios (no distortion).
- **All `[PULSE INPUT]` removed** across all 6 docs, populated with confirmed data:
  - Contract **LSL/DC/0186** (1 Apr 2023–31 Mar 2027); original value **£4,000,000**; delivered **£966,886.64** (UK £851,241.43; UK 2yr-to-30Jun2026 £719,479.54); overseas £115,645.30 (£84,549.87 2yr); **127 contract sites (9 overseas)** within **226-site** estate.
  - Overseas: **100%** ack within 48h and 100% scheduled within 5 working days; Type C **9/9** accepted. Canada = direct UK Type C. Gibraltar: Sean Coakley removed → Jimmy Connors.
  - UK 48/72 historic split confirmed unavailable → handled transparently (no fabricated stat).
- **2.1**: QP149 caption → Issue 02, 1 Nov 2025; UKAS/ISO 9001 assurance paragraph reinstated; MI wording → "agreed contract reporting route".
- **2.2B**: contract identified with values/sites; HMS testimonials no longer over-claimed as priority sites; KPI historic positions stated honestly.
- **2.3A/2.3B**: courier 3–10 days; portal caption transparency; 2.3B reframed as contract, Cyprus/Jersey/Norway reconciled.

**Deliverables** (`/app/tender_deliverables/`): `FINAL_Submission_Edited/` (6 docs), `MOD2026_Submission_EDITED.zip`, `Figure_Build_Specs.docx`, `Figure_Handover_Brief.docx`, `Pulse_Input_Required_Register.docx` (all resolved), `Score_Review.docx`.

**Estimated score after this pass: ~96–100/100** (from ~76). 2.2B carries a residual risk (unprovable historic 48/72 split, handled transparently).

---

## 2026-08-26 — Equipment Sales: Handover Pack PDF + sellable warranty tiers
Extends the existing CRM CPQ (Quotes) Equipment Sales workflow — no new module.

- **Sellable warranty levels**: new `utils/warranty.py` catalog (standard 12mo / extended_3yr 36mo / premium_5yr 60mo). Exposed via `GET /api/crm/v2/warranty-tiers`. Per-equipment-line `warranty_tier` selector added to the CPQ new-quote modal (data-testid `quote-line-warranty-{i}`, shown only for `sale` lines). Tier flows quote line → `_procurable_lines` → PO item → GRN, which now stamps `warranty_tier/warranty_months/warranty_start/warranty_expiry` on each created `equipment` record. Customer-portal handover copy carries the warranty fields.
- **Branded Handover Pack PDF**: `GET /api/crm/v2/quotes/{id}/handover/pack` (new `utils/handover_pack_pdf.py`, rendered on the shared `pulse_doc_template` shell). Contains cover/meta, equipment table (item, manufacturer/model, serial, warranty, cover-until), warranty summary, and "how to log a fault" — portal URL when the customer company is linked to a tenant org (`app_url_for_org`), else Pulse service-desk phone/email. Branding uses the selling org's brand with Pulse fallback (`_resolve_crm_brand`). Available as soon as GRN equipment exists (400 otherwise). Legacy GRN equipment gets warranty backfilled on read.
- **Frontend**: "Download pack (PDF)" button in the Handover & close panel (data-testid `handover-download-pack`, row `handover-pack-row`), visible once `equipment_created>0`.
- **Testing**: backend 9/9 pytest green (`/app/backend/tests/test_handover_pack_warranty_jul2026.py`); frontend verified after tester fixed a Rules-of-Hooks crash (moved `downloading` useState above the early return in CRMQuoteHandover.js). Both branches of fault instructions verified via extracted PDF text.

## 2026-08-26 — CRM: one-click "Connect portal" on the Company screen
- **Unified the portal-link field**: the handover pack / customer equipment push previously read `crm2_companies.tenant_org_id`, but the platform stores the customer's Pulse portal org in `linked_operator_org_id`. `crm_quote_handover._customer_portal` now resolves `linked_operator_org_id` (canonical) with `tenant_org_id` fallback, and the new link endpoint keeps BOTH fields in sync.
- **Backend (CRM token)** in `crm_v2.py`: `GET /crm/v2/portal-link/candidates?q=` (searches customer portal orgs: lite/pulse_pro/pro/full, excludes seller org), `GET /crm/v2/companies/{id}/portal-link` (current link + can_manage), `POST /crm/v2/companies/{id}/portal-link {org_id}` (link/clear; owners/admins/managers only; 400 on own-org; audited).
- **Frontend** `CRMCompanies.js` CompanyDetail: green/grey "Portal: <name> / Not connected" chip (data-testid `portal-link-chip`), a "Connect portal / Portal connected" header button (`company-connect-portal-btn`) for managers, and a searchable modal (`connect-portal-dialog`, `connect-portal-search`, `connect-portal-org-{id}`, `connect-portal-disconnect`) to link/unlink in one click.
- **Verified**: candidates + get/set/clear via curl; both fields sync; own-org rejected; UI modal renders and shows current link with disconnect. Backend + FE compile clean.

## 2026-08-26 — CRM: Equipment Sales leadership dashboard tile
- **Backend** `GET /crm/v2/equipment-sales/summary` (crm_v2.py, CRM token, org/site scoped): aggregates open equipment deals (quotes with >=1 'sale' line, status in draft/pending_approval/sent/accepted, deal_status != completed) → open_deal_value + count; units_expected vs units_delivered (equipment aggregate by quote_id) → units_awaiting_delivery; crm2_invoices aggregate → invoiced_gross/net, collected, credited, outstanding, collection_rate.
- **Frontend** `EquipmentSalesTile` in CRMDashboard.js (rendered in SalesManagerDash under the KPI row): three stats (Open deal value, Awaiting delivery, Cash collected) + a colour-coded collected-vs-invoiced progress bar with outstanding/credited caption. data-testids: equipment-sales-tile, es-open-deal-value, es-units-awaiting, es-cash-collected, es-collection-rate, es-outstanding, equipment-sales-view-quotes (→ Quotes tab).
- **Verified**: endpoint returns correct math (curl); tile renders on CRM Dashboard with live figures matching backend (£1,200 open / 1 awaiting / £7,500 of £9,000 collected / 83%). Both files compile clean.

## 2026-08-26 — CRM: Email the Handover Pack via Resend
- **Backend** `POST /crm/v2/quotes/{id}/handover/pack/email` (crm_quote_handover.py, owners/admins/managers): builds the branded handover pack (shared `_build_pack_bytes` helper, refactored out of the download endpoint), resolves recipient (`to` or the deal's linked contact email), and sends via the existing `utils.email.send_email` Resend pipeline with the PDF as a base64 attachment (kind="crm_handover_pack", category="service"). Logs a CRM activity + audit; stamps handover_pack_last_sent_to/at. Returns 400 if no GRN equipment yet.
- **Frontend** `CRMQuoteHandover.js`: "Email pack" button (data-testid handover-email-pack) beside "Download pack (PDF)" opens a dialog (handover-email-dialog) with optional To/Subject/Message (handover-email-to/subject/message) and Send (handover-email-send). Blank recipient falls back to the linked contact.
- **Verified**: 400-before-GRN correct; after GRN the endpoint builds the PDF and calls Resend correctly. ⚠️ Actual delivery is BLOCKED in this preview because `RESEND_API_KEY` is invalid (`ResendError('API key is invalid')`) — a platform-wide env limitation (same as the existing quote-email); needs the user's real Resend key. Files compile clean.

## 2026-08-26 — Customer portal: Warranty Register view
- **Backend** (customer_deliveries.py, `get_current_user`, org-scoped): `GET /customer/warranties` returns the signed-in customer's equipment with computed warranty status (active / expiring ≤60d / expired), days_remaining, tier label + summary, cover-until date; sorted soonest-cover-end first; includes counts. `GET /customer/warranties/summary` gives has_warranties + counts to show/hide the nav. Backfills expiry from warranty_start/purchase_date + tier months for legacy rows; shows any equipment with a warranty_expiry or warranty_tier.
- **Frontend** `CustomerWarrantiesTab.js` + wired into LiteDashboardPage `/pulse`: a "Warranties" tab (only when has_warranties) with 3 count cards (In cover / Expiring soon / Expired) and per-unit cards (status pill, tier label, cover-until + days left). data-testids: customer-warranties-tab, warranties-content, customer-warranties-list, customer-warranty-{id}, warranties-count-active/expiring/expired.
- **Verified**: endpoint returns correct classification/sorting (curl with seeded data); tab renders live in the demo customer's Pulse dashboard (lite.docs@pulsedemo.test) showing In cover/Expiring/Expired correctly. Seed cleaned up. Files compile clean.

## 2026-08-26 — CRM: Create & invite a portal from the Connect-portal modal
- **Frontend only** (CRMCompanies.js): when a company has no portal linked, the Connect-portal modal now shows a "Customer has no portal yet?" section with a "Create & invite portal" button (data-testid connect-portal-invite-section / connect-portal-invite-btn). It reuses the existing `POST /crm/v2/companies/{id}/portal-invite/resend` endpoint (pulse_onboarding.provision_customer_portal), then refreshes the link state + closes the modal. Handles statuses: provisioned / linked_existing / resent / already_active / missing_email (prompts to add a contact email).
- **Verified**: end-to-end — creating a company + contact then inviting provisions a new Lite org, sets linked_operator_org_id, and the portal-link endpoint immediately reports connected. (Setup email won't deliver in preview due to the invalid RESEND_API_KEY, but provisioning/linking succeed regardless.) Compiles clean.

## 2026-08-26 — Warranty Renewal Nudge (→ aftersales contracts) + Awaiting-delivery drill-down
### Renewal nudge & aftersales enquiry (ties into existing crm2_contracts)
- **Backend** (customer_deliveries.py): `POST /customer/warranties/enquire` — when a customer enquires from their portal, creates a DRAFT aftersales contract (crm2_contracts, tier=bronze, status=draft, source=customer_warranty_enquiry) in the SELLER's org pre-filled with company + equipment/serials + optional customer note; creates a high-priority follow-up TASK (crm2_activities) for the account owner (due +3d); best-effort emails the owner a heads-up. De-duped within 24h per customer. `GET /customer/warranties` now also returns `renewal_enquiry_open` (draft enquiry in last 30d).
- **Frontend** (CustomerWarrantiesTab.js): amber nudge banner when any unit is expiring(≤60d)/expired with an "Enquire about aftersales cover" button (all at-risk) + per-unit "Enquire about cover" buttons; optional-note dialog; shows "Enquiry sent — the Pulse team will be in touch" once open. testids: warranty-renewal-nudge, warranty-enquire-all, warranty-enquire-{id}, warranty-enquiry-dialog/note/send, warranty-enquiry-open.
- **Verified** end-to-end: enquiry creates the bronze draft contract + high-priority task in the seller org (iso-demo-org), dedupe returns already_requested, flag flips to open; nudge/banner/dialog render in the demo customer portal. (Owner heads-up email won't deliver in preview — invalid Resend key — records still created.)

### Awaiting-delivery drill-down
- **Backend** `GET /crm/v2/equipment-sales/awaiting-delivery` (crm_v2.py): per-open-deal breakdown (company, quote_number, total, units_expected/delivered/awaiting) for deals with undelivered units, sorted most-awaiting first.
- **Frontend** (CRMDashboard.js EquipmentSalesTile): the "Awaiting delivery" stat is now clickable → modal listing each deal; rows jump to the Quotes tab. testids: awaiting-delivery-modal/list/close, awaiting-deal-{quote_id}.
- **Verified**: endpoint returns the exact open deal; modal renders with matching figures (1 awaiting, 0/1 delivered). All files compile clean.

## 2026-08-26 — Customer Warranty Certificate PDF (consolidated, grouped)
- Per user feedback: NOT per-unit certificates — a single consolidated certificate with the kit list grouped by warranty level.
- **Backend** (customer_deliveries.py `GET /customer/warranties/certificate`, new utils/warranty_certificate_pdf.py): one branded (Pulse) PDF "Warranty Certificate" issued to the customer org, grouping their equipment by tier (Standard/Extended/Premium/Manufacturer) with a table per group (equipment, manufacturer/model, serial, cover-until) + standard terms note. 400 if no warranties.
- **Frontend** (CustomerWarrantiesTab.js): "Download certificate" button in the register header (data-testid warranty-download-certificate), blob download.
- **Verified**: endpoint returns HTTP 200 %PDF; PDF content confirmed grouped-by-tier with correct serials + cover-until dates (analyze_file_tool); button renders in the demo customer portal. Seed cleaned up; files compile clean.

## 2026-08-26 — Cover-tier choice in renewal enquiry + Awaiting-delivery deep-link
### Cover tier choice
- **Backend** (customer_deliveries.py enquire): accepts `preferred_tier` (bronze/silver/gold, validated, default bronze) → the draft aftersales contract now starts on the chosen tier; tier is recorded in coverage_notes, the owner task and the heads-up email.
- **Frontend** (CustomerWarrantiesTab.js): Bronze/Silver/Gold selector cards in the enquiry dialog (data-testid warranty-tier-choice, warranty-tier-{id}).
- **Verified**: enquiry with preferred_tier=gold created a draft contract with tier=gold + "Preferred cover level: Gold" note; selector renders with Gold highlighted.

### Awaiting-delivery deep-link (drill-down → Fulfilment)
- **Frontend**: `navigateTo` (CRMApp.js) extended to take an `extra` payload and to switch to Business/Corporate mode when the target tab is Corporate-only (fixes bounce-back from Members mode). Drill-down rows (CRMDashboard EquipmentSalesTile) now call `navigateTo('quote', quote_id, { focus: 'fulfilment' })`. CRMCPQ QuoteDetail accepts `focusSection` and auto-scrolls to the new `#quote-fulfilment-section` anchor.
- **Bug fixed**: QuoteHandoverPanel had `emailDialog`/`emailBusy` useState declared AFTER the `if (!data) return null` early return (introduced in the Email-Pack feature) → "Rendered more hooks than during the previous render" crash when the quote detail loaded. Moved both hooks above the early return.
- **Verified**: clicking a drill-down deal opens the specific quote and scrolls straight to its Fulfilment panel. All files compile clean; visual-test seed cleaned up.

## 2026-08-26 — Convert aftersales contract → sent quote (one click)
- **Backend** `POST /crm/v2/contracts/{id}/convert-to-quote` (crm_contracts.py): builds a CPQ quote (crm2_quotes) from the contract — one service_contract line at the contract's tier + annual_value, org-localized VAT via compute_quote_totals — sets it status='sent', links quote_id ↔ contract both ways, moves the contract to 'sent', logs an activity + audit. Idempotent (returns existing quote if already converted).
- **Frontend** (CRMContracts.js ContractDetail): "Convert to quote" button in the header when a contract is draft/pending_approval/approved and not yet linked; after converting it deep-links to the new quote via navigateTo('quote', id). A "View quote" button shows once linked. Renamed the unused `_navigateTo` prop to `navigateTo` (from crm context).
- **Verified**: E2E via curl — silver contract (£2,400) converted to a SENT quote (service_contract line, £2,880 inc VAT), contract → sent + quote_id linked, re-convert returns already_converted. Files compile clean. NOTE: contract-detail button not visually captured (Contracts sub-tab sits in a hidden overflow in the test viewport); the button is a minimal conditional mirroring the existing Send button.

## 2026-08-26 — Auto-send the converted quote to the customer
- **Backend** (crm_contracts.py convert-to-quote): now accepts `send_email` + optional `email_to`. After creating the sent quote it optionally emails it via the existing `send_quote_email` (renders quote PDF + Resend), resolving the recipient as email_to → contract contact → company's first contact-with-email. Email is best-effort — conversion never fails if the email can't send; returns `emailed` + `email_error`.
- **Frontend** (CRMContracts.js ContractDetail): "Convert to quote" now opens a small dialog (data-testid contract-convert-dialog) with a "Email the quote to the customer" checkbox (contract-convert-email-toggle) + optional recipient (contract-convert-email-to); confirm button reads "Convert & email" / "Convert to quote" (contract-convert-confirm). Surfaces an alert if the quote was created but couldn't be emailed, then deep-links to the quote.
- **Verified**: E2E — convert with send_email=true created a SENT quote and executed the email path (emailed=true). Consistent with the existing quote send-email, dispatch is reported on send; real delivery needs a valid RESEND_API_KEY (invalid in preview). Files compile clean.

## 2026-08-26 — Itemise converted aftersales quote from the enquiry equipment
- **Backend** (crm_contracts.py convert-to-quote): when the contract carries `enquiry_equipment_ids` (captured from the customer's warranty enquiry), the quote is now built with ONE service_contract line per unit — description includes name · manufacturer/model · serial (S/N), plus equipment_id + serial_number on the line. The contract's annual_value is split evenly across units with the last line rounded so the quote total matches exactly. Falls back to a single summary line when there are no enquiry equipment ids.
- **Verified**: full E2E — customer enquiry (3 units, Silver) → team priced the contract at £1,500 → convert produced a quote with 3 lines (£500 each, serials IT-001/002/003), subtotal £1,500, total £1,800 inc VAT. Backend-only change; compiles/runs clean.

## 2026-08-26 — BUG FIX: "Temporary password has expired" after admin reset
- **Root cause**: PUT /api/master-admin/users/{id}/reset-password set a new password + password_reset_required but never refreshed `temp_password_expires_at`. The login gate (auth.py `_enforce_account_status`) blocks when `must_change_password` AND `temp_password_expires_at < now`, so the user's STALE expiry (from original provisioning) rejected every freshly-issued temp password as "expired". Reissuing never helped.
- **Fix** (master_admin_users.py admin_reset_password): reset now sets `must_change_password=True` + `temp_password_expires_at = now+7 days`. Also hardened to update BOTH db.users AND db.crm_users (was either/or) so a mirrored user can't keep a stale *valid* password on the CRM side after a reset.
- **Verified**: testing_agent — 5/5 pytest against the LIVE endpoint (repro 401 'expired' → real master-admin reset (through mandatory TOTP MFA) → login now succeeds with the new temp password, no expiry block → old password now 'Invalid credentials' not 'expired' → DB shows fresh +7d expiry). Dual-collection change re-passes the suite (5/5). Suite: /app/backend/tests/test_temp_password_reset_expiry_aug2026.py. Backend-only.

## 2026-06 — Staffing: login re-issue fix, DBS, Fleet Manager, bell, dark mode
- **CRITICAL fix — "Re-issue login" reset token**: Root cause = re-issue mint path (`account.py _issue_reset_token`, `master_admin.py _mint_invite_link`) built links from raw `FRONTEND_URL` (preview host → different DB → token not found → "Invalid or expired reset token"). Now use brand-aware `app_url_for_org`. Also: re-issue now archives ALL prior unused tokens at mint time (old links die instantly); `/auth/reset-password` gives clear messages (invalid vs already-used vs expired) and falls back to matching the user by email if the account shell was re-created. Verified 5 branches (testing agent, backend 100%).
- **Enhanced DBS**: `dbs_number` + `dbs_expiry_date` added to staff profile (`staffing_hr.py` PROFILE_FIELDS/ProfileUpdate, `HRTab.js` new section with expiry status badge).
- **Fleet Register → Fleet Manager**: New vehicle fields `fleet_department, lease_company, lease_end_date, fuel_card_number, dart, congestion, m6_toll, driver_label` (`vehicle_checks.py VehicleBody` + create/update). Register now grouped-by-department cards; clicking opens a themed detail/edit modal (VehiclesTab.js) with sections + calendar date pickers; service info moved out of the old edit `<details>`. Driver's Staff Portal vehicle card shows lease/MOT/fuel/toll details. Imported 45 Pulse Fitness Ltd vehicles via `scripts/import_fleet_pulse_ltd.py` (drivers stored as labels; link to staff once seeded).
- **Notification bell**: moved to the right of the Operations sub-nav bar on desktop (visible in every Operations tab, `LiteDashboardPage.js`), removed the duplicate inside StaffingConsole (new `hideBell` prop), and added to the mobile top header (`Navbar.js`). Gap above the Staffing sub-menu closed.
- **Staff Portal**: removed the "Active employee ✓" badge.
- **Dark mode**: fixed white cards bleeding into dark mode on Attendance/Payroll tabs (dark: tokens) and themed the vehicle modal + register + staff vehicle card.
- Test login for Pulse Fitness Ltd operations: portal@pulsefitness.ltd / PulseFleet123! (route '/').

## 2026-06 (b) — Staff portal DBS, vehicle 2-options, fleet fines, exports & mobile polish
- Staff Portal "My details" now shows a **Compliance** section with Enhanced DBS number + expiry (via /new-starter/me compliance).
- Staff Portal vehicle card split into **two actions**: "Vehicle details" (expands lease/MOT/service + fines) and "Complete check".
- **Fleet fines**: vehicle detail modal has a Fines section — add (type/date/value/paid + scan upload), toggle paid, view scan, delete. Assigned driver sees fines on their portal. Backend: fines array on vehicle + endpoints (add/patch/delete) + /vehicles/fine-upload (object storage). Curl-verified.
- **Fleet Register export**: "Export / Print (CSV)" button → GET /api/vehicles/export.csv (all fields). Verified.
- **Notification bell** restyled transparent/theme-aware (no more white box on the dark header); mobile dropdown lowered (top-24) so the title clears the header.
- **Mobile**: Staffing secondary sub-tab bar now horizontally scrollable (no more bunched rows).
- Testing agent: frontend 100% (bell, mobile panel, sub-tab scroll, CSV export, fines CRUD).

## 2026-06 (c) — Link fleet drivers (easy manual linking)
- Vehicle modal 'Assigned driver' is now a SEARCHABLE picker (type to filter staff by name/department/title) — easy with a large team.
- When a vehicle carries an imported driver-name label but no linked staff, a hint shows "Imported driver: <name> — search above to link them", so matching the 40 imported vehicles is one click.
- Links persist via existing PATCH (driver_staff_ids) and resolve to driver_names; the register card + staff portal then show the real driver. Curl-verified (BT75NDG↔Craig Henshall) + testing agent frontend 100%.
- Driver list comes from /vehicles/driver-options (all active staff), so the full team appears in production.

## 2026-06 (d) — Fleet PDF pack
- Added GET /api/vehicles/export.pdf: Pulse-branded, board/insurance-ready PDF of the whole fleet register, grouped by department (Reg, Make/model, Driver, Lease co, Lease end, MOT due, Fuel card, Fines). Uses utils/pulse_doc_template.
- Fleet register toolbar now has two buttons: "Export CSV" (vehicles-export-csv) and "Print / PDF" (vehicles-export-pdf).
- Verified: endpoint returns valid application/pdf (45 vehicles, ~3 pages, no overflow/overlap — confirmed via document analysis).

## 2026-06 (e) — Fix password-manager autofill (Edge / iCloud Passwords)
- Root cause: login inputs were React CONTROLLED (value=formData), so after a manager autofilled the password React re-render clobbered it back to empty; password field also lacked name/autocomplete so Edge didn't recognise the login form.
- Fix (Navbar.js): email input name='username' autocomplete='username'; password input name='password' autocomplete='current-password' (new-password on signup); made email+password UNCONTROLLED (defaultValue + onChange, no value binding) so autofill sticks; handleAuth now reads live values from form.elements.username/password (effForm) so submit always uses the actual autofilled/typed values.
- Regression: manual typed login, show/hide toggle, and wrong-password error all pass (testing agent 100%).


## 2026-06 — Platform Visual Continuity (Phase 1: sub-menus + sign-in logos)
User request: full design continuity across the platform (headers/footers/menu bars/options uniform; uniform logos on all sign-in pages).

**Delivered this pass (Phase 1):**
- New shared components:
  - `frontend/src/components/shared/SubTabBar.js` — canonical secondary/"lateral options" menu; wraps `PillTabBar` and renders the standard cyan rounded-full pills (active = `--color-brand-cyan` bg + `--color-ink` text + shadow; inactive = `--theme-text-muted` transparent).
  - `frontend/src/components/shared/BrandWordmark.js` — single canonical Pulse Fitness logo (the hosted primary-logo badge image the Navbar uses), exported `PULSE_LOGO_SRC`.
- CRM Aftersales page: removed the redundant `<h1>Aftersales Contracts</h1>` + "Enter once → reuse everywhere → manage by exception." tagline; content moved up; sub-menu migrated to `SubTabBar` (cyan pills). (AftersalesApp.js)
- Sign-in logo unification → `BrandWordmark`: `LoginPage.js` (was bold "Pulse Fitness.AI" text), `StaffLogin.js`, `CRMLogin.js` (login + 2FA + signup header). MOD Service login left with its MoD defence branding intentionally.
- Sub-tab bars migrated to the cyan pill standard:
  - Service Ops: restyled shared `.svc-tabs`/`.svc-tab` in `_serviceops.css` → pills (updates Parts Inventory, Comms Hub, Case Drawer, Integrations Console at once).
  - Dealer Warranty Parts (`DealerWarrantyPartsPage.js`) → SubTabBar (kept unsaved-work guard).
  - Master Admin: `AdminRoles`, `PlatformHealth`, `SiconIntegrationPage`, `AdminMemberships` → SubTabBar; `AdminOnboardingHub` grouped bar restyled to pills in place (keeps Manage/Customers/Partners/Team grouping).
  - Memberships: `AnalyticsTab` (section bar) + `AIInsightsTab` (was fuchsia) → SubTabBar.
  - `PulseCheckSheetsTab` → pill buttons in place.
  - Engineer mobile stock strip (`EngineerStock.js`) intentionally left (equal-width mobile tab pattern, already cyan).

**Verification:** frontend compiles clean. Testing agent (owner@isodemo.com / IsoDemo123!) verified LIVE: sign-in logos, Memberships Analytics + AI Insights cyan pills. Source/compile-verified: Aftersales, Service Ops svc-tabs, Dealer Parts. Master Admin pages NOT runtime-verified (master admin has enforced TOTP MFA — cannot automate); low risk (same SubTabBar swap).

**NOT yet done (Phase 2 — larger, pending):** unify the module SHELL HEADERS/FOOTERS (ServiceOpsShell hero header, MarketingShell/PulseMarketingShell, MemberPortal, Engineer app shell, Dealer standalone portal header, MOD footer) and theme the Service Desk/Inventory SIDE NAV to match. The main authenticated `Navbar` + `Footer` are the intended standard.



## 2026-06 — Bug batch (temp-pw / reset page / engineer access / territory roles)
- **Bug 1 — Temp passwords / reset links expiring too quickly** → standardised to **7 days**.
  - `utils/auth_guards.py`: `PASSWORD_RESET_TTL_MINUTES` default 15 → 10080 (7 days).
  - `staff_onboarding_wizard.py:1551`: staff reset-link TTL 1h → 7 days.
  - `auth.py:_enforce_account_status`: hardened temp-password expiry check to parse the datetime (tz-aware) instead of a fragile ISO string compare.
  - `ResetPasswordPage.js`: copy "expires in 15 minutes" → "7 days".
- **Bug 2 — "Change password" reset link page showing blank** → the emailed reset page was stuck on the app's black auth "Loading…" splash whenever a stale login token was in localStorage. Fixed in `App.js` loading-gate: added `/reset-password` + `/staff-reset` to the public-exception list and made the splash condition skip them (`!isPublicException && (hasSessionToken || isProtectedRoute)`). Verified: reset form now renders even with a stale token.
- **Bug 4 — Engineers gaining Operations access** → engineers now get Operations only if a master admin explicitly grants it.
  - Backend enforcement (new + existing engineers): `utils/module_access.py:resolve_module_access` — `_engineer_ops_guard` forces `operations=False` for `role==engineer` unless `module_overrides.operations is True`.
  - Frontend UX: `AdminOrganizations.js` add-user + edit-user permission grids default the Operations checkbox OFF for engineer role.
- **Bug 5 — CRM Territories pulling wrong Operations job roles** → only **sales managers & engineers** now appear; admins/regional-managers/unclassified are excluded (previously defaulted to "Sales Manager").
  - `crm_territories.py`: `staff-palette` + `staff-locations` now skip any crm_user whose `territory_role` isn't in `_TERRITORY_ROLES` (sales_manager/engineer/both), using the raw stored value (no silent default to sales_manager).
  - `crm_core.py:_territory_role_from_staff`: engineer keywords now checked BEFORE sales (so "Sales Engineer"→engineer); "Administrator"/"Regional Manager"→None (excluded).
- Verified: bug1/4/5 via backend unit checks; bug2 via browser screenshot.

### OPEN — Bug 3 (staff-login on pulsefitness.ai) — PRODUCTION-ONLY
- `/staff-login` works in PREVIEW (backend POST /api/new-starter/staff-login returns 200; page renders; submit disabled only until fields typed). The failure ("press login, nothing happens / button dead") is reported ONLY on the live pulsefitness.ai domain. Main app login works there, so REACT_APP_BACKEND_URL is fine for the main bundle. Most likely: the production deployment is a STALE build predating recent staff-login changes, OR a prod-only routing/CORS quirk on /staff-login. Requires a redeploy (ships the above fixes too) and, if still failing, a production RCA via the deployer.



## 2026-06 — CRM bridging root-cause + Service Desk PM/Equipment build
### #1 CRITICAL — Master Admin imports never appeared in Pulse Fitness Ltd CRM (recurring)
- ROOT CAUSE: the import→CRM bridge stamped `crm2_companies.organization_id` with the *importing admin's* org (the Master Admin super-user org, e.g. `9fa701ef…` / preview `d19de469` "Pulse Fitness AI Admin"), NOT the operator company `3ece2d0c…` (Pulse Fitness Ltd) that the CRM Companies list filters by. So bridged companies were written to the wrong tenant and were invisible.
- FIX (`routes/master_admin_bulk_import.py`): new `_resolve_operator_org()` resolves the org flagged `is_operator_company: True` (Pulse Fitness Ltd) and is used at all 4 bridge call-sites. `_ensure_crm_company_for_org` is now SELF-HEALING — matches an existing bridged company by `linked_organization_id` across orgs and RE-POINTS it to the operator org (no duplicates) on the next import/backfill.
- Verified against live DB: resolver→3ece2d0c; fresh create lands under operator; mis-bridged doc re-points (same id, 1 doc).
- This also fixes **#2** (Service Desk "Log a Case" customer picker) — it reads the same operator-scoped `crm2_companies` with `linked_organization_id`.
- ⚠️ PRODUCTION: after redeploy, run **Backfill CRM** (`POST /master-admin/bulk-import/backfill-crm`) once to re-point existing imported estates into Pulse Fitness Ltd.
### #5 — Maintenance All/Commercial/MOD buttons "whited out" → restyled to cyan-active / readable-inactive pills (`PPMCalendar.js`).
### #3 — Service Desk Equipment: site-first + multi-select + Log case
- `DeskEquipment.js`: added Customer→Site selector + machine checklist (multi-select) + "Log case for N machines" opening `ServiceDeskIntakeForm` pre-filled.
- `ServiceDeskIntakeForm.js`: now accepts `initial={customerOrgId, siteId, equipmentIds}` and submits `equipment_ids` for MULTIPLE machines on one case.
### #4 — Create PM from Service Desk + manage service types + bulk scheduling
- Backend (`routes/svc/ppm_calendar.py`): `ppm_service_types` collection + CRUD (`/svc/ppm/service-types`), seeded with Preventative Maintenance Service, **Treadmill Calibration** (checklist: belt speed/incline/e-stop), Safety Inspection. New `POST /svc/ppm/schedules` (single) and `POST /svc/ppm/schedules/bulk` (per-site or per-machine, staggered dates for the 85-station case). `/svc/ppm/services` now unions custom types.
- Frontend (`PPMCalendar.js`): "Create PM" button → `CreatePpmModal` with Single/Bulk modes, service-type picker + inline add-type, frequency, first-visit, bulk site multi-select + stagger + granularity.
- Verified: single create, bulk (2 sites staggered 14d), calendar surfacing, add-type — all via curl; frontend flows 100% pass (testing agent report `iteration_ppm_create_desk_equipment_jan2026.json`).
- Fixed `/svc/desk/customers` duplicate org rows (dedupe by organization_id). Seed fix: `seed_site_isolation_demo.py` now sets `is_service_desk: True` on owner@isodemo (was missing → /service-desk bounced to /launch).



## 2026-06 — Calibration Capture (audit certificates)
Engineers record equipment calibration readings on a case and generate a branded pass/fail certificate for audits (e.g. Fire Station treadmill calibration).
- Backend:
  - New collection `svc_case_calibrations`. Engineer endpoints (`routes/svc/engineer.py`): `GET /svc/engineer/jobs/{case_id}/calibration` (loads existing + default checklist items from the case's PM service type), `POST .../calibration` (saves readings [{label,target,measured,unit,tolerance,result}], overall pass/fail auto-derived, notes, signature; stamps `calibration_captured`/`calibration_result` on the case), `GET .../calibration/certificate.pdf`.
  - Office/manager download: `GET /svc/cases/{case_id}/calibration/certificate.pdf` (`routes/svc/cases.py`).
  - New PDF util `utils/calibration_certificate_pdf.py` (ReportLab, shared Pulse doc shell like warranty cert): meta, OVERALL RESULT banner (green/red), readings table with per-row pass/fail, engineer notes + signature image, audit footer.
  - PM→case gap closed: `ppm_calendar.py schedule_ppm` now copies `checklist_items` onto the created case, so calibration rows pre-fill from the "Treadmill Calibration" service type.
- Frontend (`EngineerJobDetailV2.js`): new `CalibrationCapture` panel in the engineer Complete tab — editable readings grid (parameter/target/measured/unit/result), add/remove rows, notes, signature (reuses `SignatureCanvas`), Save, and Download certificate (blob fetch with auth). Auto-opens when the job's service type is calibration or has checklist items.
- Verified: certificate PDF generates (HTTP 200, valid %PDF, ~121KB) via office route with seeded data; both new routes registered (engineer route gated by Partner Engineer Network access = 402 for non-engineers); frontend serves HTTP 200 (no compile failure). NOTE: the engineer capture UI was NOT driven in a live engineer session (needs a Partner Engineer Network account); backend fully verified + UI compiles/serves — recommend a quick engineer-app walkthrough after deploy.


## 2026-06 · Calibration certificate: office drawer + customer Documents
- Office ServiceCaseDrawer: added "Calibration certificate" footer block (View + Download, PASS/FAIL pill) gated on doc.calibration_captured, hitting GET /api/svc/cases/{id}/calibration/certificate.pdf.
- Customer portal: on case close (operator sign-off), utils/calibration_cert_publish.py persists the cert PDF into db.files under the customer estate org (category "certificates") via company_id → crm2_companies.linked_organization_id. Idempotent. Wired into /cases/{id}/transition.
- Master Admin Sync (backfill-crm) now backfills historical closed-case certs so they appear once a customer estate is onboarded.
- CRITICAL FIX: EngineerJobDetailV2.js had a real syntax error (unclosed profitability component) that was breaking the entire frontend compile since the prior session's "Calibration Capture" work — now fixed; app compiles/renders.
- Added /app/memory/PLATFORM_CONTEXT.md (always-read purpose/tenancy reference).
- Verified: testing_agent 100% BE+FE (iteration_calibration_cert_office_drawer_jan2026.json).

## 2026-06 · Calibration cert: email-to-customer + parameters match Certificate of Service
- Office drawer: added "Email customer" button (data-testid drawer-calibration-cert-email) next to View/Download in the calibration cert block, plus a blue "Sent" pill (drawer-calibration-cert-sent) after a successful send. Backend POST /api/svc/cases/{id}/calibration/certificate/email (mirrors service-report email, Resend, category "service"); records calibration_cert_sent_at/to + timeline event.
- Treadmill calibration parameters now MATCH the customer's "Certificate of Service": Speed 3/6/9/12 mph, Incline 0/5/10/15%. Backend serves canonical params via engineer.py _default_calibration_readings + GET /jobs/{id}/calibration default_readings; frontend CalibrationCapture pre-fills them; PPM seed "Treadmill Calibration" checklist updated. Verified in generated PDF (all 8 params present).
- Verified: testing_agent frontend 100% (iteration_calibration_cert_email_button_jan2026.json); cert PDF text-extraction confirms the 8 params; email endpoint reaches Resend (502 only due to invalid preview key — delivers in prod).
- Task 1 (DSFR): publish/backfill already shipped; DSFR has no portal accounts / no closed calibration jobs yet, so nothing to backfill now — deploy makes it live for their upcoming services.

## 2026-06 · MOD estate bridging fix + AI custom tender pricing (Build Quote)
- FIX (production RCA): CRM backfill/Sync skipped MOD estates because account_type "mod_org"/"mod_site" didn't match the allow-list ("mod"). Added _is_pulse_visible_account_type (accepts pulse_pro/lite/mod/full + any mod*), broadened the backfill candidate set to include Pulse-visible estates even with no sites/equipment (so MOD HQs surface), and applied the helper to the sites-import gate too. master_admin_bulk_import.py.
- NEW: Aftersales → Build Quote "Custom (tender)" package. Upload a signed agreement/pricing sheet → Claude Sonnet 4.6 extracts per-machine-type SERVICE prices + per-site TRAVEL costs. Scanned PDFs handled via PyMuPDF page-render → Claude vision OCR; text PDFs/Excel/Word via pdfminer/openpyxl/python-docx. Review/edit panel → Apply matches prices to the estate by machine type (equipment_type/name/model keyword) with a needs-review fallback, adds travel per site, computes annual/term totals, and saves the quote. Endpoints: POST /crm/v2/aftersales/extract-pricing-document (file or ?file_id=), POST /crm/v2/aftersales/build-custom-quote. Large uploads route via /files/upload then file_id (bypasses proxy 413).
- Verified: extract on the real 6.7MB scanned DSFR agreement → all 7 machine prices + 85 travel rows (vision OCR); build priced 17/23 with correct discount/term maths; testing_agent frontend 100% (iteration_afs_custom_tender_frontend_jan2026.json). Model: Claude Sonnet 4.6 via Emergent LLM key.

## 2026-06 · Reusable customer rate cards (saved tenders)
- Each extracted/edited tender in Build Quote → Custom (tender) can be saved as a reusable RATE CARD on the customer ("Save as rate card"). Saved cards appear as pills ("<name> · N machines") whenever that customer + Custom package is selected; clicking one repopulates the pricing review panel with NO re-upload, then Apply builds the quote.
- Backend: crm2_afs_rate_cards collection; POST /crm/v2/aftersales/rate-cards, GET ?company_id=, DELETE /{id}. Frontend: AutoQuoteTab rateCards state + saveCard/loadCard.
- Verified: CRUD via curl; testing_agent frontend 100% save→reload→load→build (iteration_afs_ratecard_save_reload_jan2026.json).

## 2026-06 · Tender Quote Wizard (repairs + multi-schedule + AI summary)
- Aftersales → Build Quote → Custom (tender) now has a mode toggle: Quick (single panel) OR a stepped Tender Wizard (kept both).
- Wizard steps: Upload → Summary → Service → Repairs → Travel → Build. AI now also extracts REPAIR labour £/hr per machine type (single 'All' rate if flat) and a TENDER SUMMARY (headline, term, PPM visits/yr, SLA, key points). Summary step lets the user tick which schedules (Service/Repairs/Travel) to include.
- Repairs: stored on the quote/rate card AND optionally costed — "estimated repair hours/yr" × effective rate (mean of provided rates) adds an indicative repair line to the annual total.
- Rate cards now persist repair_rates and round-trip into Quick mode.
- Backend: extract-pricing-document returns repairs+summary; build-custom-quote accepts repair_rates+estimated_repair_hours (repair cost line); rate-cards store repairs. Frontend: AutoQuoteTab customMode/wizStep/incl/estHours + wizard JSX (afs-wiz-* testids).
- Verified: curl (extraction repairs+summary; 40h×£27.5=£1100 costing) + testing_agent frontend 100% (iteration_afs_tender_wizard_repairs_jan2026.json). Model: Claude Sonnet 4.6.

## 2026-06 — Aftersales Contracts: quote gaps closed (release-readiness fixes)
Fixed the founder-reported gaps that made the custom/tender quote NOT release-ready:
- **Itemised PDF + £0.00/VAT bug FIXED**: custom-tender quotes saved line items as {type,unit_price,line_total} but the PDF read {model,annual_unit,annual_total} → machines rendered "—" and every price + VAT + "Annual inc VAT" showed £0.00. Backend now writes model/annual_unit/annual_total on grouped lines; PDF (utils/afs_quote_pdf.py) reads both shapes, adds a dedicated "Travel & visits" table (Site | Per visit | Visits/yr | Annual), an itemised charge breakdown (Service/Travel/Repairs), and defensive VAT/monthly fallbacks. Verified via live PDF endpoint.
- **Travel charged per visit**: CustomQuoteIn.visits_per_year (default 1). Travel = per-site rate × visits/year; travel_lines carry per_visit/visits/annual. (Devon = 1 PPM service/yr; repairs still costed separately by hours.)
- **VAT default 20%** with per-quote override (CustomQuoteIn.vat_pct); summary now always includes vat_pct/vat_amount/final_annual_inc_vat/monthly.
- **Review missed machines + block send**: unmatched machines are grouped by model (asset_ids + count) in needs_review. UI adds per-group "Exclude" buttons; quote auto-rebuilds; unpriced_count/quote_health tracked. send-email AND portal-link now return HTTP 400 until unpriced_count==0; the Agreements list shows "N unpriced — edit to send" and disables Send/Create-link.
- **Edit a saved quote (overwrite)**: CustomQuoteIn.overwrite_quote_id updates the existing doc keeping id + quote_number. AgreementsTab "Edit" button loads the saved rates into the builder (purple editing banner); Save reads "Save changes (overwrite)".

Files: backend/routes/crm_aftersales.py (build_custom_quote, send-email/portal-link guards), backend/utils/afs_quote_pdf.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js (AutoQuoteTab + AgreementsTab + parent editQuote lift).
Testing: backend + PDF verified via curl (customer iso-cA); frontend 8/8 UI states verified by testing agent (iteration_afs_custom_tender_frontend_verify_jan2026.json). No functional issues.
Pre-existing (NOT from this change, noted for later): 2× 500s on CRM/Aftersales navigation (likely warranty-opps/settings), and a hydration warning `<span>` inside `<option>` in the CRM company <select>.

## 2026-06 — Fix: Aftersales navigation 500 (warranty-opportunities)
- GET /api/crm/v2/aftersales/revenue/warranty-opportunities returned 500 ("can't compare offset-naive and offset-aware datetimes", crm_aftersales.py:2865). It's loaded by AutoQuoteTab on entering Build Quote → the console 500 the testing agent flagged.
- Root cause: _parse_dt() returned a tz-naive datetime for warranty_expiry values stored without an offset; compared against tz-aware now/horizon.
- Fix: _parse_dt() now normalises naive datetimes to UTC-aware. Verified 200 + returns opportunities; full Aftersales nav endpoint sweep all 200.

## 2026-06 — Feature: optional per-site equipment appendix on quote PDF
- New optional "Appendix A — Equipment by site" in the customer quote PDF, for large estates (e.g. Devon & Somerset's 85 sites).
- Toggle: CustomQuoteIn.include_site_annexe (persisted on the quote); UI checkbox in AutoQuoteTab custom panel (data-testid afs-aq-annexe-checkbox), prefilled on edit.
- Render: render_afs_quote_pdf builds a per-site breakdown at render time (_build_site_annexe) from db.equipment/db.sites for the quote's linked_organization_id (respecting site_ids), grouping identical model/console into quantities, listing serials, and marking excluded_asset_ids as "(not covered)". build_afs_quote_pdf renders it after a PageBreak. Fixed a pulse_title-returns-list bug (must use `flow += pulse_title(...)`).
- Verified via live PDF endpoint (iso-cA): appendix present + correct when flag on, absent when off; all cleaned up.
Files: backend/routes/crm_aftersales.py, backend/utils/afs_quote_pdf.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js.

## 2026-06 — Feature: unpaid vehicle fine reminders (bell nudge, P1)
- The Staffing/Fleet notification bell now nudges managers about vehicle fines left unpaid for 14+ days.
- Implemented as a computed nudge in GET /api/staffing/notifications (staff_portal.py) mirroring the DBS-expiry pattern: scans db.vehicles embedded `fines`, ages each unpaid fine by `created_at` (fallback: parse free-text `date`), and surfaces a "Unpaid vehicle fines" nudge (type `vehicle_fine_overdue`, link `vehicles`) listing up to 3 regs. Owners see the whole org; line managers see only fines on vehicles driven by their direct reports. Auto-clears as soon as a fine is marked paid (no cron, no stored notification).
- Frontend: added `vehicle_fine_overdue` rose tone to StaffNotificationBell TONE map.
- Verified via curl (iso-demo-org, vehicle AB12 CDE): counts only 14+ day unpaid fines (1 of 3 seeded: skipped a 3-day-old unpaid and a 30-day-old paid), and the nudge disappears once the fine is marked paid.
Files: backend/routes/staff_portal.py, frontend/src/components/staffing/StaffNotificationBell.js.

## 2026-06 — Feature: Aftersales quote versioning (view / revert) + hydration warning fix
- Editing a saved custom/tender quote now archives the prior state to `crm2_afs_quote_versions` before overwriting. Main quote doc carries a `version` counter (starts 1).
- New endpoints (crm_aftersales.py): GET /quotes/{id}/versions (history metadata, newest first), GET /quotes/{id}/versions/{version} (full snapshot for viewing), POST /quotes/{id}/versions/{version}/revert (restores a snapshot as current; archives current first so revert is reversible; keeps quote number). Helper `_archive_quote_version`.
- Frontend (AftersalesApp.js AgreementsTab): a 'History (vN)' button on custom quotes with version>1 opens a modal listing the current version + all prior versions (£/yr, editor, timestamp), each with View (read-only snapshot) and Revert.
- Verified: backend via curl (v1→v2→v3, list, view snapshot returns historical figures, revert restores £ and is reversible); frontend History modal via testing agent (5/5 scenarios, 100%).
- BONUS FIX (hydration warning): the long-standing "<span> cannot be a child of <option>" console warning was traced (by the testing agent) to the Emergent Visual-Edit tool injecting a <span> wrapper around MULTI-EXPRESSION children inside <option> (afs-ag-quote select, and the AI-tab contract select). Fixed by giving each such <option> a single template-string child. Verified live on the Agreements tab: 0 injected spans, 0 nesting warnings.
Files: backend/routes/crm_aftersales.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js.

## 2026-06 — Feature: Payroll monthly timesheets (customer Excel template) + Payroll nav regroup
- New payroll export that reproduces the customer's "TIME SHEETS 2026.xlsx" template 1:1: exact layout, [h]:mm number formats, and every formula (per-day H=(D-C)-E, weekly SUM totals, Grand Total, Standard Hours =C3/24, =D3*D4, Overtime/Unpaid-Leave IFs). Pre-filled per staff from recorded self_entries (start/finish/break/PT). Yellow hand-in Friday cell. Filename "Timesheet <Mon><YY> - <Full Name>.xlsx".
- Per-year hand-in SCHEDULE: auto-generated with a contiguous Mon-start 5-4-4 calendar (Jan ends 2nd Sunday of Jan; hand-in = Friday of each period's final week) — matches the supplied 2026 file exactly (Jan26 8 Dec–11 Jan, hand-in 9 Jan, etc.). Payroll can edit period start/weeks/hand-in per month and Save; selecting a future year auto-generates it ("AI creates the new year"). Collection: timesheet_schedules (org+year).
- Endpoints (staffing_clock.py): GET/PUT /staffing/timesheet-schedule; GET /staffing/timesheets/month-export (single staff xlsx); GET /staffing/timesheets/month-pack (ZIP, one file per active staff — no duplicates). New util utils/payroll_timesheet_xlsx.py.
- Frontend: new PayrollTimesheetsTab.js. Payroll is now a nav GROUP: Workspace + Timesheets + Attendance. The standalone "Time Clock" tab was removed (per request).
- Verified: auto-schedule matches sample; xlsx replica (layout/formulas/formats/yellow/footer rows 48/50/52/54); pre-fill of recorded hours (start/finish/break/PT); filename; 10-file pack with no dupes; UI smoke (Time Clock gone, Timesheets tab renders, no console errors).
Files: backend/routes/staffing_clock.py, backend/utils/payroll_timesheet_xlsx.py, frontend/src/pages/LiteDashboard/StaffingConsole.js, frontend/src/pages/LiteDashboard/staffing/PayrollTimesheetsTab.js.
