# Contracts & Renewals — Release Candidate report (24 Nov 2026)

## 1. Work completed this sprint
- **Exception Resolution Centre** (Maintenance Master preview): you can filter by unresolved, issue type, coordinator or search text. The row panel shows why the row was flagged and its original workbook cells, and lets you search CRM customers. A coordinator can record a correction with a required reason, or decide "not a duplicate" / "do not import"; every decision is logged. Exceptions are recalculated after each correction or decision, and unresolved items can be exported.
- **Missing-information rows are no longer committed.** They stay in the review queue until corrected, so nothing fabricated reaches the contract register.
- **Coordinator Daily View** (top of the Maintenance Master panel). Nine cards, filterable by coordinator:
  - Expiring in 90 days
  - Renewals awaiting action
  - Missing contract information
  - Awaiting approval
  - Service visits needing attention
  - Follow-ups due
  - Unresolved import exceptions
  - Billing to verify
  - Awaiting Sicon reconciliation
- **Monthly invoice-run preview** (Finance tab), preview only:
  - Sources: the agreement billing schedules plus imported annual contracts.
  - Monthly and quarterly contracts need a confirmed instalment amount; they are never annualised.
  - Duplicate obligations are excluded, already-invoiced rows are shown, and billing for missing or not-live contracts is never proposed.
  - VAT is calculated only when it is configured. The preview can be exported.
- **Sicon states** now read Local only / Awaiting verification / Ready for approval / Held for Sicon / Changes since last approval / Conflict / Failed / Synchronised (verified).
  - The held queue records held revision, previous approved revision and last result.
  - Identity conflicts are recorded; `SICON_ALLOW_WRITES` is still unset, so writes stay off.
- **Contract editor:** new "confirmed instalment amount" field and a saved/unsaved indicator.
- **Updated Master export:** a blank value never overwrites a populated workbook cell, and edits to fields that have no column in the workbook are listed on the "Pulse Fitness Pro changes" sheet.
- **Backup / restore** script `backend/scripts/cm_backup.py`: per-organisation BSON backup with a manifest, restore that only inserts missing documents and refuses the live DB without `--live`, and a verify step.
- **Defects fixed:**
  - Renewal of an imported contract crashed (unique key copied).
  - `/crm/v2/contracts/workspace` returned 404 (route order).
  - Duplicate React key in Build Quote warranty opportunities.
  - Stale "identical upload" badge.
  - 45 lint errors in the Contracts & Renewals screens; those screens now pass ESLint with zero warnings.

## 2. GitHub status
- Work is saved in this environment on `main`; the last platform commit before this sprint was `661b5da1`. Push with **Save to GitHub** — the agent cannot push directly.
- CI gates (repo-wide) fail on **pre-existing** issues outside this module: 422 ruff findings and 842 ESLint problems platform-wide. All Contracts & Renewals backend files pass ruff, and all Aftersales/Contract Management frontend files pass ESLint with `--max-warnings 0`. The production build (`yarn build`) succeeds.

## 3. Test evidence
- `tests/test_cm_maintenance_master.py`: 3 tests passed, covering scenarios A, C, D, E, F, G, I and J (backup/restore to a scratch DB, live restore refused, backend restart persistence).
- Contracts & Renewals regression: 51 tests passed (Service Planner, quote-to-contract, e-signature, Build Quote import, stage-2 integrity, phase A/B), with H covered by the Service Planner suite.
- Wider regression: 174 passed, 14 skipped. MOD contract board, MOD service desk visibility, MOD readiness, CRM quote fulfilment, PPM/Sicon suites all pass.
- `test_crm_contracts.py`: 22 of 24 pass. The 2 failures expect Sicon/Sage "sync" to report success while writes are disabled; this is intended behaviour and those tests need updating once live Sicon is approved.
- Browser testing:
  - iteration_313: frontend 85% — all findings fixed.
  - iteration_314: backend 100%, frontend 92% — all findings fixed afterwards; those last fixes were checked in code and the 3 automated tests, but not re-run in the browser.
- Not verified here: production deployment, live Sicon/Sage, real customer data matching (the preview DB has no live CRM customers).

## 4. Migration readiness (real 12 Nov 2026 workbook, preview only — NOT committed)

**Contract rows: 9,206 in total** (Maintenance Database 813 + Expired 8,393)

| Classification | Rows |
|---|---|
| New | 8,067 |
| Duplicate / overlap | 11 |
| Missing information | 1,127 |
| Review | 1 |

**Missing information breakdown** (rows can have more than one problem)

| Problem | Rows |
|---|---|
| No contract number | 786 |
| Missing start / expiry date | 433 |
| No contract amount | 382 |

**Supporting sheets read:**
- MOD: 200 rows, held for MOD Operations.
- Service Planner: 1,273 service records linked by Record ID.
- Sicon Contracts: 1,676 contract numbers with Sicon IDs.
- The other 10 sheets are kept unchanged in the stored original and in the updated export.

**Source totals**

| Sheet | Contract amount £ | Stated annual £ |
|---|---|---|
| Maintenance Database | 546,296.75 | 135,303.56 |
| Expired | 1,738,624.96 | 936,274.44 |

**Manager actions before the live import**
1. Run the preview against the production database, so it matches against the real CRM customers.
2. Resolve or accept the exception queue (export "Unresolved items").
3. Decide whether unmatched customers may be created.
4. Take a backup with `cm_backup.py`.
5. Approve & commit.
6. Check the reconciliation report totals.
7. Record the cutover.

## 5. Release decision

| Area | Status | Reason |
|---|---|---|
| Contracts operational pilot | **READY WITH RESTRICTIONS** | Use with the real workbook only after the manager actions above, against production data. |
| Full everyday release | **READY WITH RESTRICTIONS** | After the pilot sign-off by the coordinators and resolution of the 1,139 exceptions. Agreement generation directly from an *imported* contract is not available; use Build Quote → agreement for renewals. |
| Customer-facing quotation / agreement issuance | **READY WITH RESTRICTIONS** | Blocked per record until an approved tariff exists and the approved Terms PDF is uploaded and approved. Drafts are always available. |
| Maintenance invoice-run preview | **READY WITH RESTRICTIONS** | Preview only. Monthly and quarterly contracts need confirmed instalment amounts; VAT needs to be configured in Aftersales settings. |
| Sicon integration | **BLOCKED** (by design) | Needs verified API family, Sage company/account mapping, a controlled reconciliation and management approval. Data and queue are prepared. |

## 6. External dependencies
- **Management:** approval to commit the real workbook; whether unmatched customers may be created; cutover date.
- **Coordinators:** resolve the exception queue; confirm instalment amounts for monthly and quarterly contracts.
- **Commercial / legal:** approved maintenance tariffs, and the approved Terms & Conditions PDF.
- **Sage:** customer account references for unmatched customers; the VAT configuration to use.
- **Sicon:** confirmation that the Legacy Contracts API (R260200c) is installed, test credentials, and written approval before writes.

## 7. Rollback
- Use the platform **Rollback** to a checkpoint for code.
- For data, restore the pre-import backup into a scratch DB, verify it, then restore missing documents. Imported contracts are tagged `source=maintenance_master` and `mm_source.upload_id`, so they can be identified.
