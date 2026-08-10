# PulseFitness.ai — Security Hardening Programme

_Last updated: 2026-08-10_

This document tracks the platform-wide Zero-Trust security programme requested
by Pulse Fitness (54-section brief). It is delivered in **phases** on a live
production platform; requirement #53 (do not break the platform) governs every
change. This is the working security package for the upcoming independent
penetration test.

---

## A. Executive summary

**Current posture (pre-programme):** the platform already had strong security
*primitives* — JWT with `jti` revocation, HttpOnly/Secure/SameSite cookies,
MFA claim pinned in the token, an active-session registry with bulk
revocation (`tokens_revoked_before`), portal-user blocking (SEC-001),
`get_organization_filter` tenant scoping, a centralised per-request
`site_scope` engine, MOD estate scoping, shared-store (Mongo) rate limiting
(SEC-002 XFF hardening), and a hardened production CSP.

**Root weakness (the incident class):** those primitives were applied
**inconsistently** across ~2,965 endpoints (≈40 different `require_*` guards,
ad-hoc `find_one({"id": ...})` lookups, `require_same_org` defined but unused).
This is exactly the BOLA/IDOR + broken-object-level-authorisation class in the
referenced incident (cancelling another user's reservation).

### Phase 2 — DELIVERED (engine rollout)
- **Quotes** (`crm_v2.py`): approval **state machine** wired into
  `submit-approval` and `approve` — a `draft` can no longer be approved
  directly (skip-approval blocked, §8), and finalised quotes can't be
  re-approved. Statuses aligned to the real CRM vocabulary.
- **MOD incidents** (`mod_incidents.py`): closure **state machine** + central
  audit on `close-incident`; reopening a closed incident is privileged-only.
- **Documents/files** (`files.py`): `GET /files/{id}` and `DELETE /files/{id}`
  now enforce **site isolation** + central audit via the engine (previously
  tenant-only) — closes the cross-site document-download gap (§25).
- **MOD personnel** (`mod_portal.py`): staff transfer now writes a central
  high-sensitivity security event (kept its bespoke same-force/DOB checks — the
  engine's tenant guard is deliberately NOT applied to the legitimate
  cross-site-within-force flow).
- **Contracts / invoices / stock**: verified their mutation endpoints are
  already tenant-scoped (`_of(user)` / `{id, organization_id}`); registered in
  the engine (`quote`, `contract`, `invoice`, `file`, `mod_site_staff`,
  `mod_incident`) for adoption as they're next touched. Contract transition
  enforcement deferred (complex multi-stage lifecycle — avoid regression).
- **Contracts** (`crm_contracts.py`, `crm_contract_send.py`): **workflow lock**
  — the draft→pending_approval→approved→sent→signed/active lifecycle is now
  server-enforced. `sign` can't activate an unapproved draft; `approve` only
  works from `pending_approval`; `send` refuses any unapproved contract
  (closing the draft→sent→public-sign→active skip path); the public customer
  sign link defensively re-checks the transition. (Contract Workflow Lock.)
- Acceptance suite extended to **13 tests** (added contract workflow lock) —
  all passing.

### Phase 1 — DELIVERED
- **Central Authorisation Engine** (`utils/authz.py`) — one deny-by-default
  `authorize_resource(user, type, id, action)` enforcing tenant → site →
  ownership → role for a registry of high-risk resources. Cross-tenant → 404
  (no existence leak); cross-site → 403; every denial audited.
- **Protected state machines** (`assert_transition`) for `issue`, `quote`,
  `contract` — illegal jumps → 409, privileged-only transitions → 403, all
  privileged transitions logged. (Sections 7, 8.)
- **Mass-assignment defence** (`filter_writable` + `PROTECTED_FIELDS`) — client
  cannot rebind tenant/site/owner or escalate role/approval/warranty/billing
  fields; attempts are stripped and audited. (Section 9.)
- **Immutable security telemetry** (`utils/security_events.py`) — append-only
  `security_events` collection (actor/tenant/site/action/resource/result/IP/UA/
  method/path/request-id), indexed, fail-open. (Sections 32, 34, 35.)
- **Wired into flagship high-risk routes:** `PATCH /api/issues/{id}` (tenant +
  state machine + audit), `PATCH /api/equipment/{id}` and
  `DELETE /api/equipment/{id}` (added the missing **site isolation** + audit).
- **Permanent acceptance-test suite** (`tests/test_security_authz_matrix.py`)
  — Tests A–H all passing (see section G).

### Findings register (live)
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| SEC-101 | High | Object-level authz applied inconsistently across ~2,965 endpoints (BOLA/IDOR risk) | Phase 1 engine shipped; rollout to all resource routes = Phase 2 |
| SEC-102 | High | Equipment update/delete lacked site-level isolation (cross-site within a tenant) | **Fixed** (engine wired) |
| SEC-103 | Med | Fault status had no server-side state machine (illegal transitions possible) | **Fixed** for issues; quotes/contracts engine ready, wiring = Phase 2 |
| SEC-104 | Med | No central mass-assignment guard / protected-field allow-list | **Fixed** (helper shipped); sweep of write routes = Phase 2 |
| SEC-105 | Med | No immutable security event log / alert centre | Log **shipped**; Master-Admin Alert Centre UI = Phase 3 |
| SEC-106 | Low | Master-Admin MFA capability exists but not enforced | Capability present (`ENFORCE_MASTER_ADMIN_MFA`), left **OFF** by user choice |

### Remaining risks / not yet done (honest status)
Phase 2+ (planned, see ROADMAP): roll the engine across all listed resource
routes (quotes, contracts, MOD sites/personnel, stock, documents, invoices);
mass-assignment sweep of remaining `$set` write paths; step-up auth for
destructive ops; Security Alert Centre UI; automated full role×resource matrix;
CI/CD security gates (#39), SBOM (#40), TLS/infra (#43), backup/ransomware
(#45), IR runbook (#46) — these are infra/process, documented here for the
pen-test rather than implemented in the app container.

---

## B. Central Authorisation Engine — usage

```python
from utils.authz import authorize_resource, assert_transition, filter_writable

# 1. Load + authorise (tenant/site/ownership) in one deny-by-default call:
doc = await authorize_resource(user, "issue", issue_id, "update", request=request)

# 2. Enforce the server-side workflow state machine:
await assert_transition("issue", doc["status"], new_status, user,
                        resource_id=issue_id, request=request)

# 3. Strip mass-assignment / protected fields from client payloads:
clean = await filter_writable(payload, allowed_fields={"description", "notes"},
                              user=user, resource_type="issue", resource_id=issue_id)
```

**Registered resources:** issue, equipment, booking, member, document,
supplier_case, quote, contract, svc_case, invoice, site, mod_site_staff,
mod_incident. Adding a resource = one `ResourceSpec` entry; an unregistered
type **fails closed** (500), forcing every new sensitive route to declare scope.

---

## G. Acceptance-test results (section 51 — permanent regression tests)

`backend/tests/test_security_authz_matrix.py` — **9 passed**:

| Test | Scenario | Required result | Result |
|------|----------|-----------------|--------|
| A | User modifies another user's (member's) booking | 404, no change, logged | ✅ |
| B | Site-A-only manager touches Site-B kit (same tenant) | 403 server-side | ✅ |
| C | Tenant A accesses Tenant B by ID | 404 at authz layer + logged | ✅ |
| D | Illegal state transition (closed→open) via direct call | 409 backend reject | ✅ |
| E | Privileged-only transition (closed→reopened) as site_staff | 403 | ✅ |
| F | Payload adds role/org/site/is_admin/approval | protected fields stripped + logged | ✅ |
| G | Rapid enumeration of another tenant's resources | every attempt denied + logged | ✅ |
| H | Replay of a sensitive mutation | idempotent no-op, no duplicate effect | ✅ |
| — | Master-admin bypass is allowed **and** audited | passes + event written | ✅ |

Run: `cd /app/backend && python -m pytest tests/test_security_authz_matrix.py -q`

---

## I. Step-Up Authentication (§18)

Fresh re-authentication is required before especially destructive actions.
- **Module:** `utils/step_up.py` — `require_step_up(user, action=…)` (deny with
  403 `step_up_required` unless a fresh step-up exists), `verify_step_up_challenge`
  (TOTP/backup code if MFA enrolled, else account password), `record_step_up`,
  `step_up_status`. Email-keyed so it spans operator + CRM tokens. TTL
  `STEP_UP_TTL_SECONDS` (default 300s).
- **Endpoints:** `GET /api/auth/step-up/status`, `POST /api/auth/step-up`
  (rate-limited 6/5min, all attempts audited to `security_events`).
- **Wired into:** `DELETE /crm/v2/companies/{id}` (delete company),
  `PUT /sicon/config` (set/rotate integration credentials),
  `POST /svc/orbit4/connection/rotate-key` (rotate integration secret).
- **Enforcement:** gated by `STEP_UP_ENFORCED` (**default OFF**) — capability
  shipped and wired; enable deliberately once the FE prompt is live (same
  pattern as `ENFORCE_MASTER_ADMIN_MFA`). While OFF, `require_step_up` is a
  safe no-op so no existing flow breaks.
- **FE contract:** on a `403 {"error":"step_up_required","mfa_enabled":bool}`
  from any action, show a prompt (authenticator code if `mfa_enabled` else
  password), `POST /api/auth/step-up`, then retry the original request.
- **Tests:** `tests/test_step_up.py` (4) — challenge/freshness, enforced gate,
  disabled no-op, expiry. All passing.

## H. Pen-test readiness notes
- **Test accounts:** see `/app/memory/test_credentials.md` (Master Admin,
  operator owner/manager, site-restricted manager, MOD site, member portal).
- **Tenant isolation evidence:** Tests C + G (negative cross-tenant).
- **Site isolation evidence:** Test B.
- **Business-logic evidence:** Tests D + E (state machine), F (mass assignment).
- **Auth design:** `utils/auth.py` (JWT+jti, cookie, MFA claim, session
  registry, bulk revoke), `utils/auth_guards.py` (role gates, MFA, PII strip).
- **Infra items to confirm with the tester (not app-container implementable
  here):** CI/CD SAST/SCA/secret-scan gates, SBOM, TLS config & HSTS at the
  edge, encrypted/immutable backups + restore drills, documented IR runbook.
