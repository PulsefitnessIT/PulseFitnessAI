# Onboarding Consolidation — Import Inventory & Decisions (Nov 2026, P0)

Decisions:
- P0 only in this release.
- Old customer-creating screens are REMOVED, so there is one source of truth.
- Manual customers without a Sage account number are allowed after a duplicate check.
- The Import Centre is for Pulse admins only.

## Shared services
- **`backend/utils/customer_identity.py`** — the only way to create a Pulse-managed customer.
  - `find_orgs_by_ref` / `claim_ref`: a Sage/Sicon account number, scoped by Sage company, is bound to exactly one organisation by the unique `customer_account_refs` index.
  - `duplicate_suggestions`: name + postcode matches are shown to a person as suggestions, never auto-matched.
  - `provision_customer_org`: creates the organisation as LITE only, pending activation, with no users or emails, and writes an audit event.
- **`backend/utils/sage_sicon_import.py`** — parser, field classification, and contact identity/matching (account-scoped; generic mailboxes never merge people).

## Inventory of import routines and what happened to each

| # | Routine (UI → API) | Writes | Decision |
|---|---|---|---|
| 1 | Import Centre → Customer Accounts (Sage file) → `/master-admin/customer-import/*` | organizations, customer_account_refs, internal record, crm2 companies and contacts, proposed sites | **Authoritative**. Uses the shared identity service. |
| 2 | Import Centre → Customer Accounts → *Add one customer by hand* → `POST /customer-import/manual` | organizations (LITE) | **Authoritative** for manual entry. Duplicate check, plus confirmation if there is no account number. |
| 3 | Import Centre → Customer Contacts (Sicon file) | crm2_contacts, staging | **Authoritative**. |
| 4 | Import Centre → Customer Accounts → *Read directly from Sicon* (SiconOnboardingSync → `/sicon/read/onboarding/*`) | sites/equipment for the tenant | **Kept as an alternative source** inside the Import Centre. Its configuration stays in Integrations. |
| 5 | Guided ImportWizard → `/onboarding/import/*` | sites, equipment, contacts; formerly also customer tenants | **Customer type removed**: hidden from types, and commit returns 410. Other types kept as "guided column mapping" inside Sites/Equipment/Contracts. |
| 6 | Quick CSV cards (AdminBulkImports) → `/master-admin/bulk-import/{sites,equipment,contracts}` | sites, equipment, contracts | **Kept as specialist adapters** inside the Import Centre (Sites / Equipment / Contracts). The "Bulk import customers" card was **removed** (its endpoint was already unregistered and returned 404). |
| 7 | Onboard Site wizard (PulseOnboardingWizard) → `POST /master-admin/onboard-pulse-site` | org + owner user + password | **Removed**. UI deleted, API returns 410. |
| 8 | Head Office wizard → `POST /master-admin/onboard-head-office` | org + owner user + sites | **Removed**. UI deleted, API returns 410. |
| 9 | Organisations → Create organisation → `POST /master-admin/organizations` | org (any account type) + primary-contact user | **Kept** for paid/specialist accounts. Now uses the shared identity service: an account number that already exists returns 409; without an account number, similar names need `confirm_new`. |
| 10 | Org drawer → Sites → Import CSV (OrgSitesPanel) | sites | **Redirected**: the button now opens Import Centre → Sites with that customer preselected. |
| 11 | Aftersales Estate Onboarding → `/crm/v2/aftersales/onboarding/*/commit` | org, CRM company, sites, equipment, draft contracts | **Kept as the specialist estate pathway**. Customer creation now goes through `provision_customer_org` (account number from the CRM company; duplicate suggestions return 409 unless "create new" is chosen). The pricing engine is untouched. |
| 12 | Onboarding Packets (customer questionnaires) → `/onboarding-packets/{id}/provision` | org + users from the packet | **Kept**, now under the Specialist tab group. Blocked if the account number exists or a similar name exists without `confirm_new_customer`. |
| 13 | MOD Estate / MOD Sites CSV / MOD bulk import / MOD equipment | MOD orgs + kiosk logins | **Kept as specialist (MOD only)**. Not changed in P0. Reviewing kiosk provisioning against the MOD access policy is P1. |
| 14 | Service Desk Imports (`/svc/imports/*`) | svc_engineer_customers (the Service Desk tenant's own customers) | **Kept**: customer-owned module data, not Pulse-managed estates. |
| 15 | Public signup / CRM register / service-provider signup | org + user | **Kept**: legitimate self-registration and paid signup. |
| 16 | `pulse_onboarding.provision_customer_portal` | LITE org + pending owner | **Kept** (matches by owner email). Consolidation into Customer Activation is P1. |
| 17 | Customer-owned imports (memberships, CRM leads, marketing contacts, suppliers, parts) | tenant data | **Kept**, gated by entitlements. Not Pulse-managed customer creation. |

## Navigation (Master Admin)
Overview · People · Organisations (List, All sites, Module subscriptions, Activation funnel) · **Onboarding** · Catalogue · Finance · … · Integrations · Compliance · Settings.

**Onboarding → Onboarding Centre** tabs:
- **Onboarding:** Onboarding Dashboard · Import Centre · Onboarding Projects · Review Centre · Customer Activation · Import History · Templates & Guidance · Reports
- **Specialist:** Customer Questionnaires · MOD Estate Setup · MOD Sites (CSV) · MOD Equipment & Readiness · External Service Providers
- **Pulse staff:** Onboard Pulse Staff

Old bookmarks redirect to Import Centre: `?tab=site | head-office | sage-import | imports`. Deep links: `/master-admin?section=onboarding&tab=import-centre&type=sites&org=<id>`.

## Import history
- `GET /customer-import/history` combines:
  - customer_import_jobs
  - legacy `import_batches` (with their existing undo)
  - legacy guided-import audit events
  - Aftersales estate onboarding runs
- Nothing was migrated or deleted.

## Review Centre
`GET /customer-import/review` collects, by priority, with search and pagination:
- possible duplicate or conflicting accounts
- failed rows
- branch relationship problems
- uncertain contacts
- invalid records and emails
- unmatched Sicon contacts
- proposed sites
- hidden and on-hold Sage accounts
- customers missing owner details

## Not done in P0 (P1)
- One onboarding project created per imported customer, with automatic steps.
- Customer Activation invitations, MFA for customer roles, gym-floor devices.
- Moving the site, equipment and contract engines onto the shared job model (they keep their own batch and undo for now).
- Shared asset and contract identity services across the Aftersales and bulk engines.
- MOD kiosk policy review.
- Delegated permissions for Aftersales and Service Desk.
