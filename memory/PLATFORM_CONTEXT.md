# PulseFitness.ai — Platform Context (READ FIRST, every session)

> Purpose of this file: so no agent ever has to re-ask "what is this platform for".
> This is the single source of truth for the product's intent and tenancy model.
> Update it when the product's purpose or core architecture changes.

## What this platform is
PulseFitness.ai is an **Aftersales Maintenance Contract Automation Engine** for
**Pulse Fitness Ltd**, a commercial gym-equipment manufacturer/servicer. The
platform runs the full service lifecycle: estate onboarding, preventative
maintenance (PPM) scheduling, intelligent engineer dispatch, calibration &
compliance evidence, fleet/vehicle management, and Sage 200 / Sicon Service
WebAPI integration.

Pulse Fitness Ltd is the **operator** (the service provider). Their customers
are **estates / organisations** that Pulse provides preventative maintenance to
(e.g. **Devon and Somerset Fire and Rescue**). Those customers have their own
**Operations Portal** where they view documents, certificates and compliance
evidence for **their own organisation only**.

## Tenancy model (critical)
- Everything is scoped by `organization_id`.
- **Operator org** = Pulse Fitness Ltd. Marked `organizations.is_operator_company = True`.
  Operator org id (current data): `3ece2d0c-57ea-4acd-a6b4-d748478ed117`.
- **Master Admin org** is a separate internal tooling tenant. Imported estates
  must NEVER be stamped with the Master Admin org id — they map to the **Operator** org.
- **Customer estate orgs** = the organisations Pulse services (imported via
  Master Admin bulk import). They have `account_type` in
  {`pulse_pro`,`lite`,`mod`,`full`}. Their portal users log in with
  `users.organization_id = <estate org id>` and see only their own data.
- A customer estate may exist (imported) **before** any portal login accounts
  are created for it ("not set up on the portal yet"). Data stamped with their
  org id becomes visible to them the moment their accounts are created.

## Key linkage: service case → customer estate org
`svc_cases.company_id` → `crm2_companies.linked_organization_id` → `organizations.id`
of the customer estate. The CRM company row lives in the **operator** tenant
(`crm2_companies.organization_id = operator`) and points to the estate via
`linked_organization_id`. There is NO reverse field on the org doc. Use
`utils.svc_crm_sync.find_company_id(...)` as a name/email/postcode fallback when
`company_id` is missing.

## Service case state machine (`utils/svc_state.py`)
`new → triaged → assigned → en_route → on_site → (paused_*) → repaired →
awaiting_sign_off → closed → invoiced`  (plus `rejected`).
- `repaired` = engineer finished the work.
- `awaiting_sign_off` = ready for customer sign-off.
- **`closed` = the service desk operator has OK'd/approved the job.** ← use this
  as the trigger for "job OK'd by the operator" side effects.
- `invoiced` = billed after close. Terminal: {closed, invoiced, rejected}.

## Documents / certificates
- Customer-facing documents live in `db.files`, scoped by `organization_id`,
  grouped by a free-text `category` string.
- The "Service Certificates" tab uses `category = "certificates"`
  (LiteDashboard's tab also aliases `certificates`). Store customer-facing
  certs under `category="certificates"` and the estate's own org id.
- Calibration certificates are generated on-the-fly by
  `utils/calibration_certificate_pdf.py`. When a case with a captured
  calibration is **closed** (operator OK), `utils/calibration_cert_publish.py`
  persists the PDF into `db.files` under the customer estate org so it shows in
  their Operations Portal → Documents → Service Certificates. Backfill for
  already-closed cases runs from the Master Admin "Sync" (backfill-crm) action.

## Operational gotchas
- `EngineerJobDetailV2.js` is huge and trips Webpack/Node OOM. If the frontend
  fails to compile with a heap error, `sudo supervisorctl restart frontend`.
- Master Admin account enforces TOTP MFA — automated UI tests can't log in as it.
  Use `owner@isodemo.com / admin123` (no MFA) for manager-level testing.
- Sage 200 / Sicon live API calls are MOCKED in preview.
