# Pulse Fitness Platform — Data Architecture (maintained)

Last updated: Nov 2026, Release A. This document covers what exists today and the gaps that remain. Nothing below describes a feature that has not been built.

## 1. Authoritative sources

| Data | Authoritative service / collection | Notes |
|---|---|---|
| Customer organisation | `organizations`, via `utils/customer_identity.provision_customer_org` | The permanent `id` never changes. Every Pulse-managed creation path goes through this service (see ONBOARDING_CONSOLIDATION.md). |
| Sage/Sicon references | `customer_account_refs`, unique on (system, company, ref) | Scoped by Sage company. Site refs (`sites.invoice_customer_ref`) are trusted only for the default company. |
| Confidential Sage data | `customer_account_internal` | Staff only. Never returned by customer APIs. |
| Operational sites | `sites` | Sage addresses are only *proposed* (`customer_proposed_sites`). Each one is confirmed, linked to an existing site or rejected. |
| Internal Pulse CRM | `crm2_companies` / `crm2_contacts` under the operator org "Pulse Fitness Ltd" | Linked by `linked_organization_id`. Never visible to customers. Never activates the customer's CRM product. |
| Customer CRM product | `crm2_*` with the customer's own `organization_id` | Gated by `has_module(...,"crm")` (utils/module_access.py:195). |
| Members | `members` | Gated by `has_module(...,"memberships")`. |
| Marketing | `marketing_contacts`, `marketing_campaigns`, `comms_segments` | Audiences read `members` directly (routes/marketing/audiences.py:179). |
| Communication suppression | `comms_optouts` (utils/comms_dispatch.py:104-117) | A second preference store, `notification_prefs`, is NOT unified with it (gap). |
| Entitlements | `organizations.enabled_modules` / `modules`, checked by `utils/module_access.has_module` | Server-side. |
| Import audit | `customer_import_jobs`, `customer_import_rows`, `customer_import_undo`, `customer_import_preimages`, `onboarding_audit_events` | |

## 2. Cross-module data-flow matrix (current state)

| Flow | Status | Evidence |
|---|---|---|
| Organisation → every product | **Shared**: every product reads `organizations` by `organization_id` | |
| Sites shared across products | **Partial**: Operations, Memberships and Marketing use `sites`/`site_id`; CRM also has its own `crm2_sites` | Gap: CRM sites are not linked to `sites` |
| One user identity across products | **Partial**: `users` plus a separate `crm_users` store | Gap: two auth stores, so revocation is not central |
| Shared person (prospect / member / marketing) | **Missing**: three identity collections (`crm2_contacts`, `members`, `marketing_contacts`) with no shared person id; joined ad hoc | Release D |
| CRM lead → member | **Partial**: `crm_lead_conversion.convert_lead` creates CRM artefacts, not a `members` link | Release D |
| Members → Marketing audiences | **Works (read)**: direct query of `members`, filtered on `marketing_consent` | |
| Opt-outs respected everywhere | **Partial**: `comms_optouts` is checked at dispatch; `notification_prefs` is separate | Release D |
| Cross-module events / outbox | **Missing** for products (outbox exists only for Sage/Sicon finance sync) | Release D |
| Gym-floor access | **Site-specific** device logins (`gym_floor_credentials` id `<org>:<site>`; sessions carry `site_id`, expire after 16 h, end on disable/re-key). Older org-wide logins keep working and are flagged for replacement | Release C (done) |
| LITE → PRO upgrade | Same org / equipment records; recorded in `commercial_events`; ending PRO returns to LITE with data kept | Release E (done, tested in preview with Stripe events simulated) |

## 3. Release A safeguards (done and tested)
- New imported customers get LITE only, status pending_activation / not_activated. No users, passwords or emails are created.
- Company-code sign-up is refused (403) for any organisation that is pending activation, not activated, or still importing, unless a pending invitation exists.
- Plaintext passwords: Reveal returns nothing and the "email credentials" endpoint returns 410. Plaintext is no longer stored by master_admin primary-contact provisioning or user password reset. Existing users' passwords stay valid (user's choice); `POST /customer-import/security/initial-passwords?apply=true` wipes any stored copies.
- Sage branches are **separate until verified**. The head-office link is recorded as `head_office_link_status=proposed`. Bulk verify or reject is available in the Review Centre (`POST /customer-import/branch-links`). Verifying records the relationship only: no merge and no shared access.
- Source-company isolation covers identity lookup, the preview ref index, CRM company matching (account-number match only for the default company), and contact staging (unique on company + ref + fingerprint).
- The approval snapshot now includes resolved org ids, proposed fills and conflicts, relationship decisions and matched contact ids. A change invalidates the approval.
- Safe Undo:
  - `GET /jobs/{id}/undo-preview` shows what will be removed and what is kept.
  - A created customer is kept if it has users, invitations, equipment, assets, contracts, faults, service cases, work orders, members, CRM activities, real sites, another live import, paid products or activation.
  - A pre-import value is restored only when the field still holds what the import wrote.
- Site confirmation is atomic (no double confirm) and keeps all four address lines. A site at the same postcode returns 409 with existing sites, giving Link / Confirm (`force`) / Reject.
- The Review Centre no longer caps at 5,000 or 2,000 items, so totals are complete. It also lists unverified branch links.

## 4. Remaining work by release
- **B:** Move sites, equipment and contracts onto the shared job model. Shared asset identity (serial only when validated) and contract identity. Estate Onboarding inside the Import Centre. One onboarding project per customer. Delegated staff permissions. Legacy bulk Undo safeguards.
- **C:** Owner verification and invitations (single-use, scanner-safe, MFA). Manager and staff roles with site scope. Site-specific gym-floor devices. Branded activation email. Investigate trial-reminder duplicates.
- **D:** Shared person id across `crm2_contacts` / `members` / `marketing_contacts`. Unify `comms_optouts` and `notification_prefs`. Durable product event outbox. Link CRM sites to `sites`. Unify `crm_users` and `users`.
- **E:** Tested LITE → PRO upgrade, purchasing, cancellation and reactivation, commercial reporting.

## 5. Backup and recovery
- Before any live import, take a platform database backup.
- Every import can be undone from Import History (preview first).
- Removed documents are archived in `customer_import_rollback_archive`.
- No destructive migration has been run. The only index change is that the staging unique index was replaced by the company-scoped one.


## Update (Nov 2026)
The Sicon sync and Aftersales estate onboarding now resolve customers through utils/customer_identity.py, the same matching that Sage imports use. Org-level matching is limited to the Pulse operator workspace and eligible Pulse-managed customer orgs (see crm_afs_onboarding._eligible_customer_org).

## Release A/B identity update (26 Nov 2026), tested in iterations 336–337

### Shared identity: what is now authoritative
| Entity | Authoritative key | Where |
|---|---|---|
| Customer organisation | `organizations.id`; external ref `customer_account_refs(system, company, ref)` (unique) | utils/customer_identity.py |
| Sicon external ids | `sicon_external_links(integration_source, source_company, external_entity_type, external_id)`, unique index `uniq_sicon_external_link_v2`; `source_company` = Sicon connection companyId | utils/sicon_links.py |
| Sage company for Sicon customer matching | `sicon_config.sage_company`, else env `SICON_SAGE_COMPANY` ("Pulse Fitness" → `PULSE FITNESS`) | sicon_links.sage_company_for |
| Operational site ↔ Sicon sub-location | `sites.sicon_sub_location_id`; unknown sub-locations become `customer_proposed_sites(account_ref="SICON:<id>")` | sicon_onboarding._Run.operational_site |
| Equipment from Sicon (operator workspace) | written into the customer org resolved by customerCode under the configured Sage company; never into the operator org; unknown customers are held | sicon_onboarding._Run.destination_org |
| Onboarding project | one per Pulse-managed org, keyed `onboarding_projects.auto_org_key` (unique, sparse) | onboarding_projects.ensure_project_for_org |

### Rules enforced
- **Links are never reassigned by a sync.** A different Pulse id marks the link `conflict`. Only admin decisions (`reassign=True`) or clearing a link can change it.
- **Legacy links** (no `source_company`) are reused, never duplicated. They are scoped only by the audited migration: `GET/POST /api/master-admin/customer-import/sicon-links/migration[/apply]`. Links that can't be placed go to the Review Centre as "Unscoped Sicon link".
- **Reference reservations:** `claim_ref` never steals a reservation held by an active job. It waits, then raises `RefReserved`. A failed org insert releases our own reservation.
- **Placeholder serials** (N/A, UNKNOWN, WORN, …) never match. A serial match with a different model is a conflict. An asset already bound to another Sicon id is never matched.
- **Sicon runs** finish `partial` with `missing_resources` when a resource is unavailable (contracts) or fewer records were retrieved than `totalRecords`. Each run records pages and records retrieved per resource, plus the source company.
- **Preview → apply:** preview stores a fingerprint for every record (`sicon_preview_fingerprints`). Apply writes only records identical to the approved preview; anything else is queued for review.
- **Direct Sage 200 pull** (`POST /api/crm/sage200/sync/customers?source_company=`) reads every `$top/$skip` page (50,000 cap, fails loudly above it). It creates an Import Centre job and no longer writes legacy `crm_contacts`.
- **Manual customer reconciliation:** a Sage row matching a customer that has no Sage account becomes `possible_existing_customer` (blocks approval). `link_org_id` attaches the ref and keeps the id, sites, users and plan. `confirm_new` creates a new customer.
- **Delegated Pulse staff:** permissions `imports.prepare/review/approve/commit/undo`, `activation.view`, `sage.confidential`, granted at `/api/master-admin/customer-import/delegates`. Only operator-org or platform-org users can hold them.

### Sage / Sicon capability matrix (preview has no live servers; nothing below is live-verified)
| Resource | Route | Status |
|---|---|---|
| Sicon equipment | GET /api/v1/SiconService/Equipment (nested `query=$skip..%26$max..`, svc_paginate) | implemented; tested offline with fakes; live verification needed |
| Sicon cases / case equipment / appointments | CaseSearch, Case/{id}/Equipment, Case/{id}/Appointment | implemented earlier; tested offline |
| Sicon contracts (read) | none in Contracts.R260200c (POST only); candidate GETs not confirmed | **UNAVAILABLE**: runs report `partial`; use the spreadsheet contracts template |
| Sicon customer master | not available; customers are found only through equipment, contracts or cases | **INCOMPLETE**: use the Sage customer file or Sage 200 pull as the customer master |
| Sage 200 customers | GET {base}/customers `$top/$skip` | implemented; tested with mocks; field mapping needs live verification |
| Sage / Sicon writeback | — | disabled (`SICON_ALLOW_WRITES` unset/false) |

### Mapping regression
No field mappings were changed. `normalise_equipment`, `SICON_SYNCED_FIELDS` and the case and contract mappings are untouched; make still goes to `sicon_make_raw`. Only the matching logic changed (serial reliability, destination customer, link scoping), so `gen_bruno_sicon_mapping.py` was not re-run.

### Measured scale
Sicon equipment through the operator workspace into one customer:
- **2,000 records:** about 11–13 s per pass.
- **20,000 records:** second pass (all matched, 0 duplicates) took 106 s with peak RSS 88 MB.
- **Projected 111k estate:** about 10–12 min per pass. Not run at full scale.

### Still open
Release B items:
- Contract and service-record identity consolidation.
- Safe legacy Undo for site/equipment/contract imports.
- Unified history across all engines.
- Delegated staff UI outside Master Admin.

Releases C–E have not started: activation and invitations, MFA, site-specific gym floor, shared person identity, consent, events, upgrades and purchasing.

## Final Release A/B corrections (27 Nov 2026), iteration 338 plus fixes
- **One write path for multi-customer estates.** In the Pulse workspace (operator or platform org), `run_equipment_sync` returns `blocked`. Only the customer-aware onboarding engine (preview → approve → apply) writes there.
  - Nightly sync runs only when `SICON_NIGHTLY_SYNC_ENABLED=true` (unset = off).
  - Onboarding, equipment and case syncs share one `estate` lock per org.
- **Source connection.** Each run sets `sicon_links.SOURCE_CTX` to `connection_company(sync org)` = `<sicon host>#<companyId>`. Links are scoped by it; it is never inferred from the destination customer.
  - `reserve_link` claims a Sicon id before an asset is created. An id already held by another customer gives a conflict for review: no cross-tenant link, no twin asset, and the other customer's link is never changed.
  - The Pulse workspace may read customer-held links (cases → customer assets). Customer orgs may not.
- **Preview approval.**
  - **Fingerprint:** covers the source record plus connection, destination org, site, bucket, matched asset id and asset version.
  - **Records without a Sicon id:** held for review and never auto-created.
  - **Single use:** a preview can be applied only once (`applied_at` in the route, `consumed_by` in the engine).
- **Sites.** Sicon proposals use `sicon_source` + `sicon_sub_location_id`, under a unique partial index, with `account_ref` left empty. Sage refs and Sicon ids stay separate.
  - Confirming or linking keeps both and attaches equipment already synced there.
  - Re-syncs recognise the site, and a failed decision never leaves a proposal stuck in 'deciding'.
- **Sage 200.** Every endpoint is Pulse-admin only. The pull's company comes from the connection (`company_name` / `company_id`): 409 if a typed label disagrees. Push is blocked unless `SAGE_ALLOW_WRITES=true` (central guard `sage_writes_allowed`).
- **Delegated staff.** `_require_admin` is async and re-checks the user's current organisation (operator or platform) on every call, so stale flags never grant access. Grants and revocations are logged in `onboarding_permission_history`.
- **Cases.** A case in the Pulse workspace stores `customer_org_id` and `customer_site_id` of the resolved customer-owned asset. No second asset or case is created.
- **Live acceptance:** see `memory/LIVE_ACCEPTANCE_SAGE_SICON.md`.

### Not done
- **P1-8:** an equipment quantity-preserving review UI for serial-less spreadsheet assets. Serial-less Sicon records are held, but there is no dedicated quantity UI yet.
- **P1-9:** contract identity across sources, plus safe legacy Undo for sites, equipment and contracts.
- **Delegated staff UI outside Master Admin.**
- **Releases C–E.** The existing `/auth/organization/invite` shares a company code and is not a secure invitation; Release C must replace it, using the clerk-auth skill.


## 6. Release C — secure access (Nov 2026)
- **One invitation service** (`utils/secure_invites.py`, collection `secure_invitations`) for owner activation and staff invites.
  - A random token is shown only in the link; only its SHA-256 hash is stored. One pending invitation per person per organisation (unique partial index); a new one supersedes the old.
  - **Scanner-safe:** the link is `/accept-invite#token=…`. The fragment is never sent to the server and opening the link changes nothing. Inspect and accept are explicit POSTs.
  - **Single use:** acceptance claims the invitation atomically (`pending → accepting → accepted`). It expires after 72 h. Five wrong email confirmations lock it.
  - **Emails held by default:** nothing is sent unless `INVITATION_EMAILS_LIVE=true`. While held, the one-time link is shown once to whoever created it and never stored. The branded email is `send_activation_invite_email`.
- **Owner activation** (`/master-admin/customer-activation/*`, permission `activation.invite` or full Pulse admin):
  - Requires a recorded verification method and notes. Sage hold/hidden accounts need an explicit "confirmed with Accounts".
  - Acceptance creates the owner with forced MFA enrolment (`mfa_enrolment_required`) and sets the org `active` / `activated`.
  - Entitlements are untouched: LITE stays LITE.
- **Staff invitations** (`/organization/invite`) replace sharing the company code.
  - Owners invite managers or staff; managers invite staff only, and only to sites they manage. Sites are validated against the org.
  - Managers must enrol MFA.
  - Release 1 (27 Nov 2026, founder-approved): company-code self-registration is closed for **every** organisation. A code identifies an organisation, never authorises joining. Legacy invites are migrated through the secure service.
- **Gym floor:** one device login per site. Devices see only their site's equipment and handover diary. Faults can only be logged against equipment at that site. Managers can disable or sign out devices.
- **Trial reminder duplicates (root cause):** every sender checked, sent, then marked, so two workers could both send. There were also three overlapping "trial ending" emails (`trial_lifecycle` day 13, `lifecycle_emails` expiry_warn, `pro_trial_reminders`).
  - Now every sender claims before sending (`utils/email_claims.py`, unique key).
  - One shared "trial ending" claim per org per trial end date.

## 7. Release E — commercial lifecycle (Nov 2026)
- `utils/commercial_lifecycle.py`. Every product change is written to `commercial_events`: purchased, upgraded_lite_to_pro, cancellation_scheduled / withdrawn, ended, reactivated.
- A paid product ends only on Stripe `customer.subscription.deleted` (or status canceled / unpaid). Products included by Pulse (source `admin`) are never switched off by Stripe events. Ending Operations returns the org to LITE with all sites, equipment and history kept.
- Owner self-service: `GET /account/billing/modules`, `POST /account/billing/modules/{m}/cancel` (at period end) and `/reactivate` (undo before the end). Invoiced products must be cancelled through Pulse. Buying again after an end is recorded as a re-subscription on the same organisation.
- Pulse reporting: `GET /master-admin/commercial/summary` gives MRR from list prices (annual as /12), plus per-product paying, cancelling, trial, included and ended counts, the activation funnel and the last 30 days of events. It is in Master Admin → Finance → Commercial lifecycle.
- **Not done:** Stripe checkout was not run against real test-mode subscriptions here; webhooks were exercised by calling the handlers directly. Price changes and proration, and invoiced (BACS) customers' lifecycle, are outside this release.


## 8. Release 1 — access hardening (27 Nov 2026)
- One staff-administration rule set (`utils/team_guards.py`), used by `auth.py` (`/organization/staff/*`) and `account.py` (`/account/team/*`). Ownership changes only via `POST /organization/ownership/transfer` (password + new owner already on MFA).
- Central session checks (`utils/auth._load_user_core`): disabled users (`active` / `is_active` false or `status` "disabled") lose every session. Role and site changes revoke sessions.
- Members of `pending_activation` organisations cannot sign in.
- Gym floor: older org-wide logins in multi-site organisations are refused.
- Sicon supervised acceptance: an apply can be limited to `sample_org_ids`.
- Commercial gate: imported customers can't check out until `IMPORTED_CUSTOMER_PURCHASES_ENABLED=true`.
- Report: `memory/RELEASE_1_REPORT.md`.
