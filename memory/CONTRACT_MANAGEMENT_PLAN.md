# Contract Management — Functional Development Plan (Stage 2+)

Design is frozen: every change reuses existing components and styling.

## A. Completed
| Capability | Where |
|---|---|
| Workspace, area selector, Switch area, roles, backend permissions (Stage 1) | `utils/crm_workspace.py`, `routes/crm_workspace.py`, `CRMApp.js` |
| Honest Sicon/Sage status, no fabricated refs (P0) | `routes/crm_contracts.py` sync-sicon / sync-sage, `utils/finance_sync.py` (SICON_ALLOW_WRITES gate, no-ref = unconfirmed), boot clean-up `run_integrity_boot` |
| Manual "mark synced" needs a real Sage reference (P0) | `crm_aftersales.finance_sync_mark_synced` |
| Estate onboarding reconciliation (P0) | `crm_afs_onboarding.py`: `/reconcile`, commit requires a link-or-new decision, reuses sites by name/code and equipment by serial, atomic single commit, no invented dates/billing |
| Approval-first renewals (P0) | `utils/cm_renewals.py`: verified data checks, one draft per contract, calendar-aware term, coordinator approve & send |
| MOD rate verification + price-file upload (P0) | `crm_mod_quote.py`: `price_status`, validity window, `/rate-card/import` (preview → apply), history, send blocked on unverified/expired |
| One Action Centre lifecycle (P1) | `utils/cm_actions.py`: idempotent `dedupe_key`, auto-assign, auto-resolve when fixed, re-open if it recurs |
| Weekday 7am UK checks (P1) | `.emergent/crons.yml` `cm-daily-checks` → `/api/crm/workspace/cron/daily-checks` |

| Phase 3 Service Planner: obligations ↔ Service Desk bookings ↔ verified completions, reconciliation, Action Centre (Nov 2026) | `utils/cm_service_link.py`, `routes/crm_service_planner.py`, `ServicePlanner` in `AftersalesApp.js` |

## Phase 3 data mapping (one obligation, one booking, one history)
| Information | Authoritative record | Link field |
|---|---|---|
| Contract, term, covered machines, visits/year, approved `service_dates` | `crm2_contracts`, `crm2_afs_agreements` | `contract_id`, `agreement_id` |
| Contractual obligation (per contract-year visit **per site**) | `crm2_afs_service_schedules.visits[]` | `obligation_id` (deterministic uuid5 of contract/year/visit/site), `site_id`, `equipment_ids`, `scope` |
| Booking, engineer, appointment, work report | `svc_cases` (`case_type: ppm`) | `contract_obligation_id`, `contract_id` on the case; `case_id` on the visit |
| Machines serviced on the visit | `svc_work_visit_machines` (`asset_id`, `serviced`) | `case_id` |
| Sicon evidence | `svc_cases.sicon_case_id`, `sicon_completed_at` (inbound worker), `sicon_external_links` | read-only; Sicon write-back unchanged (still gated) |
| Coordinator work | `crm2_activities` via `cm_actions` | `svc:{obligation_id}:book / :cancelled / :review` |
Rules: completion only from a PPM case with an engineer report, an actual completion date (Sicon > Service Desk > report > closed; never created/assigned/planned) and every covered machine at that site serviced. Repairs never count. Auto-link only on canonical refs (obligation id, contract id, covered equipment); site+date alone → authorised review. Annual auto-PPM (`ensure_annual_ppm`) skips machines under an active contract. Booking is idempotent (array-element lock + canonical lookup).

## B. Remaining — prioritised
| # | Capability | Existing code to extend | Notes |
|---|---|---|---|
| P1 | Accepted sale → one coordinator action → Build Quote pre-filled | `crm_quote_handover.py`, `crm_quote_fulfilment.py`, Aftersales warranty opportunities | dedupe key per sales quote; link `source_sales_quote_id` |
| P1 | Accepted agreement → one active contract + PPM plan + billing schedule | `crm_aftersales` agreements activate, `ppm_engine`, `crm2_afs_billing` | idempotent on retry |
| P1 | Build Quote: delivery-note / invoice import → Master Price List match → qty/serial confirm | `EstateOnboarding.js` (PDF path), `crm_price_list.py`, `AutoQuoteTab` | reuse the onboarding row-confirmation UI |
| P1 | Monthly maintenance invoice-run preview + Sage ref tracking + duplicate-post guard | `FinanceDashboard`, `crm2_afs_finance_sync`, `crm2_afs_billing` | preview by billing date; Phase 3 did not touch billing |
| P1 | Sage 200 financial reconciliation | `utils/finance_sync.py` | needs live Sicon WebAPI credentials |
| P1 | Approved pricing data load (Master Price List / tariffs) | `crm_price_list.py`, `crm2_afs_service_configs` | needs Pulse-approved data |
| P1 | Maintenance Master migration (12 Nov 2026 baseline) → contracts + historic visits via the Phase 3 reconciliation | `crm_afs_onboarding.py`, `cm_service_link` reconciliation | workbook not in repo; never fabricate dates |
| P1 | MOD contract obligations shared read-only with CM | `crm_mod_*`, `MODVisitCalendar` | MOD kept separate in Phase 3 |
| P1 | Sicon appointment-level actual completion dates (field names to confirm with Sicon) | `utils/sicon_inbound_worker.py` | currently maps ActualCompletedDateTime/CompletedDateTime/ActualEndDateTime |
| P1 | Coordinator operational acceptance + production release | — | not ready to replace Excel until history is reconciled |
| P2 | Canonical-ID matching in `svc_crm_sync` (no name/email fallback without review) | `utils/svc_crm_sync.py` | review queue for ambiguous matches |
| P2 | Contract print/download agreement in CM | `utils/crm_contract_pdf.py` | button exists in CRM contract view |
| P2 | Coordinator assignment rules (per customer / region) | `cm_actions._assignee` | currently contract coordinator → owner → pool |

## C. Tests before everyday use
Phase 3: `tests/test_cm_phase3_service_planner.py`, `tests/test_cm_phase3_import_regression.py`, `tests/test_cm_phase3_planner_fixes_iter310.py`.
`tests/test_contract_management_workspace.py`, `tests/test_cm_workspace_extended.py`, `tests/test_cm_stage2_integrity.py`
(35 backend checks). Plus browser checks for the Action Centre, onboarding, renewals and the MOD rate card.
Real-environment checks still needed: a real MOD price file, live Sage references and a production cron fire.
