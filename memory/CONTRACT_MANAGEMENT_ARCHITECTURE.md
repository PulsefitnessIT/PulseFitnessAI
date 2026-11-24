# Contract Management Workspace — Architecture & Implementation Matrix

Baseline: GitHub `main` = `ffe2534` (2026-11-10). The preview workspace contains `ffe2534` plus 23 newer
commits (engineer reports, parts price list, follow-up jobs) that are not yet on GitHub. Push with "Save to GitHub".

## 1. Principle
One login, one CRM provider (`CRMContext` in `CRMApp.js`), one `crm_users`/`users` identity bridge, one MongoDB.
Contract Management = `CRMApp` rendered with `workspace="contract_management"`. It is not a second application.

## 2. Reused code vs changes (Stage 1 = DONE, later stages = PLANNED)
| Area | Existing code reused | Change | Stage |
|---|---|---|---|
| Launcher tile | `LauncherPage.js` (remember-my-area, one-destination forward) | New `contract_management` tile, gated on `user.crm_workspaces` | 1 ✅ |
| Switch area menu | `AreaSwitcher.js` | CRM + Contract Management entries, same flag as launcher | 1 ✅ |
| CRM pills | `ModuleSwitcher.js` | CRM pill hidden when `crm_workspaces.crm === false` | 1 ✅ |
| Route | `AppRoutes.js` `CrmRouteElement` | `/contract-management` guard; coordinators on `/crm` go to CM | 1 ✅ |
| Shell | `CRMApp.js` (auth bootstrap, cross-login, Navbar, PillTabBar) | `workspace` prop, CM nav, `?tab=&sub=` kept in URL for refresh | 1 ✅ |
| Sections | `AftersalesApp.js` sub-tabs, `CRMCompanies`, `LiveCompliancePanel` | `sections` / `initialTab` / `onLeaveSection` props, nothing copied | 1 ✅ |
| Roles + perms | `crm_auth.get_crm_user` (already mirrors the platform role) | `utils/crm_workspace.py` and `routes/crm_workspace.py` | 1 ✅ |
| Login payload | `auth.py` login + `/auth/me` | `crm_workspace_role`, `crm_permissions`, `crm_workspaces` | 1 ✅ |
| Action Centre | Aftersales `DashboardTab` (alerts, priorities) | Unified work item lifecycle on `crm2_activities` | 4 |
| Sales → contract handover | `crm_quote_handover.py`, `crm_quote_fulfilment.py`, warranty opportunities | One idempotent coordinator action for each accepted sale | 3 |
| Sicon/Sage simulated refs | `crm_contracts.py` L775 `SICON-…`, L810 `SAGE-…` | Replace with Pending / Not Configured / Failed states | 2/5 |
| Estate onboarding duplicates | `crm_afs_onboarding.py /build` | Match existing customers and sites before any insert | 2 |
| Renewal auto-send | `crm_contract_lifecycle.py` renewals | Dry run, approval first, calendar-aware dates | 4 |
| MOD placeholder rates | `crm_mod_quote.build_seed_rate_card` | Mark rates unverified; block them as authorised prices | 2 |
| Name/email matching | `utils/svc_crm_sync.py` fallbacks | Use canonical IDs first; ambiguous matches go to review | 2 |

## 3. Workspace roles → permissions (backend `ROLE_PERMISSIONS`)
| Permission | Coordinator | Sales Mgr | Aftersales Mgr | Finance | Admin |
|---|---|---|---|---|---|
| workspace.crm | – | ✓ | ✓ | – | ✓ |
| workspace.contract_management | ✓ | – | ✓ | ✓ | ✓ |
| quotes.maintenance (build/send AFS quotes) | ✓ | – | ✓ | – | ✓ |
| agreements.process | ✓ | – | ✓ | – | ✓ |
| contracts.manage (amendments, estate import) | ✓ | – | ✓ | – | ✓ |
| renewals.review / renewals.approve | ✓ / – | – | ✓ / ✓ | – | ✓ |
| quotes.commercial, pricing.commercial (price list) | – | ✓ | ✓ | – | ✓ |
| quotes.mod (and the operator-company gate) | – | ✓ | ✓ | – | ✓ |
| finance.sync / finance.post (mark synced) | – / – | – | ✓ / – | ✓ / ✓ | ✓ |
| pricing.manage (AFS tariffs, MOD rate card) | – | – | – | – | ✓ |
| permissions.admin, integrations.admin | – | – | – | – | ✓ |

How the role is resolved (from the platform `users` record, not from `crm_users.role`):
1. Platform/master admin → admin.
2. Explicit `users.crm_workspace_role`, set by an admin in CM Settings → Workspace roles.
3. A pending grant in `crm_workspace_role_grants` (the initial coordinator list), applied once.
4. Otherwise the platform role: owner/admin → admin, finance → finance, everyone else → sales manager.
Users outside the operator company get `crm_user`, which keeps their historical CRM behaviour unchanged.

Fix for blanket `manager` provisioning: cross-login now provisions the real platform role, and a boot task reconciles existing `manager` rows.

## 4. Backend-enforced endpoints (Stage 1)
- `crm_aftersales.py`: tariffs and settings (pricing.manage), quote build/send (quotes.maintenance), agreements (agreements.process),
  amendments (contracts.manage), finance sync (finance.sync / finance.post), RPI (renewals.review / approve), alerts (tasks.manage).
- `crm_afs_onboarding.py`: analyze/build (contracts.manage).
- `crm_mod_quote.py`: the operator-company gate is kept, plus quotes.mod and pricing.manage.
- `crm_price_list.py`: price-list editors also need pricing.commercial.

## 5. Shared record ownership
| Object | Authoritative store | Stable ID | External IDs | Who may update |
|---|---|---|---|---|
| Customer | `crm2_companies` | `id` | Sage account ref, Sicon customer | CRM and CM (shared API) |
| Site | `crm2_contract_sites` / company locations | `id` | Sicon site | CRM and CM |
| Equipment | `equipment` (+ `crm2_contract_assets` links) | `id`, serial | Sicon asset | Operations / Service Desk; CM verifies |
| Sales quote | `crm_quotes` (CPQ) | `id` | Sage SOP | Sales (CRM) only |
| Maintenance quote | `crm2_afs_quotes` | `id` | – | Coordinator (CM) |
| MOD quote | `crm2_quotes` (+ `mod_sor_rate_card`) | `id` | – | Sales/Aftersales, operator only |
| Contract / agreement | `crm2_contracts` / `crm2_afs_agreements` | `id` | Sicon contract, Sage | CM through the activation workflow |
| Service case | `svc_cases` | `id` | Sicon job (read-only) | Service Desk |
| Invoice | Sage 200 (finance sync outbox) | contract + period | Sage invoice no. | Finance |

## 6. Duplicated functionality to retire (later stages)
Separate standalone contract and quotation apps. Their business rules (Maintenance Master reconciliation, machine-code matching,
serial confirmation, pricing exceptions, setup readiness) will be moved into the Aftersales components. No SQLite import.

## 7. Regression tests
`backend/tests/test_contract_management_workspace.py` covers role resolution, workspace flags, 403s for each role, the operator gate,
role assignment, and CRM still working for sales. Frontend checks are run by the testing agent with the `cm.*@pulsefitness.test` accounts.
