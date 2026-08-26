# CHANGELOG

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
