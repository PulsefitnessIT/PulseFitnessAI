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
| Gym-floor access | **Org-wide** shared credential (`gym_floor_credentials` keyed by org; sessions carry no `site_id`) | Release C (must become site-specific) |
| LITE → PRO upgrade | Same org / equipment records (modules flag only) | Not yet independently tested (Release E) |

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
