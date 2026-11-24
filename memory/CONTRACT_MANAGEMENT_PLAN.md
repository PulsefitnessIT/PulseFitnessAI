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

## B. Remaining — prioritised
| # | Capability | Existing code to extend | Notes |
|---|---|---|---|
| P1 | Accepted sale → one coordinator action → Build Quote pre-filled | `crm_quote_handover.py`, `crm_quote_fulfilment.py`, Aftersales warranty opportunities | dedupe key per sales quote; link `source_sales_quote_id` |
| P1 | Accepted agreement → one active contract + PPM plan + billing schedule | `crm_aftersales` agreements activate, `ppm_engine`, `crm2_afs_billing` | idempotent on retry |
| P1 | Build Quote: delivery-note / invoice import → Master Price List match → qty/serial confirm | `EstateOnboarding.js` (PDF path), `crm_price_list.py`, `AutoQuoteTab` | reuse the onboarding row-confirmation UI |
| P1 | Service planner: contractual PPM vs Service Desk/Sicon verified visits | `LiveCompliancePanel`, `svc_cases`, `sicon_links` | flag visits needing scheduling |
| P1 | Finance invoice-run preview + Sage ref tracking + duplicate-post guard | `FinanceDashboard`, `crm2_afs_finance_sync` | preview by billing date |
| P2 | Canonical-ID matching in `svc_crm_sync` (no name/email fallback without review) | `utils/svc_crm_sync.py` | review queue for ambiguous matches |
| P2 | Contract print/download agreement in CM | `utils/crm_contract_pdf.py` | button exists in CRM contract view |
| P2 | Coordinator assignment rules (per customer / region) | `cm_actions._assignee` | currently contract coordinator → owner → pool |

## C. Tests before everyday use
`tests/test_contract_management_workspace.py`, `tests/test_cm_workspace_extended.py`, `tests/test_cm_stage2_integrity.py`
(35 backend checks). Plus browser checks for the Action Centre, onboarding, renewals and the MOD rate card.
Real-environment checks still needed: a real MOD price file, live Sage references and a production cron fire.
