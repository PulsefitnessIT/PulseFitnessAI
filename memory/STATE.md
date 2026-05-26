# GymAxis · Module State (Live)

> **Purpose**: Single-page snapshot of the *current state* of every module.
> Updated on every iteration. Never older than the latest commit.
> The next agent reads THIS first — not PRD.md (which is archival).
>
> **Status legend**: ✅ live & verified · 🟡 live but rough · ⚠️ partial / gated · ❌ broken / mocked

_Last refreshed: Iter 220m · May 26 2026 — Partner Engineer journey RELEASE-READY (P0 gates + P1 polish + monthly reputation reports shipped)._

---

## Quick Map

| Module               | Operator surface             | Public/Member surface                | Backend route prefix          | State |
|----------------------|------------------------------|--------------------------------------|-------------------------------|-------|
| Operations           | `/dashboard`, `/pulse`       | n/a                                  | `/api/issues`, `/api/equipment` | ✅ |
| Memberships          | `/memberships`               | `/m/:slug`, `/m/:slug/join`, `/members`, `/instructor` | `/api/memberships/*` | 🟡 |
| Service Desk         | `/service-desk`              | `/track/:token`, `/q/:shortcode`     | `/api/svc/*`, `/api/issues`   | ✅ |
| CRM                  | `/crm`                       | n/a                                  | `/api/crm/*`, `/api/crm/v2/*` | 🟡 |
| MOD Portal           | `/dashboard` (mod_*)         | `/MODService`                        | `/api/mod/*`                  | ✅ |
| Master Admin         | `/master-admin`              | n/a                                  | `/api/master-admin/*`         | ✅ |
| Marketing Suite      | `/marketing`                 | `/p/:slug`, `/forms/:slug`           | `/api/marketing/*`            | 🟡 |
| Engineer App         | `/svc/engineer/*`            | `/r/:slug`, `/engineer`              | `/api/svc/engineer/*`         | ✅ |
| Gym Floor            | `/gym-floor`                 | n/a                                  | `/api/gym-floor/*`            | ✅ |
| Partner Engineers    | `/partner-engineer`          | `/partners/engineers`                | `/api/partners/*`             | ✅ release-ready (iter 220k/l/m) |
| **Diagnostics**      | `/master-admin?section=login-events` & `?section=client-errors` · Home tile (h215): 24h platform-issues aggregator at `/master-admin?section=overview` | n/a | `/api/master-admin/{login-events,client-errors,platform-issues-24h}` | ✅ NEW h210/h215 |

---

## Memberships (most active)

### Operator console — `/memberships` (top-level tabs)
Start · Dashboard · Classes & Timetable · Studio brain · Members · **Plans** · Family billing · Parent portal · Events · Instructors · Promotions · Check-in · Invoicing · Desk sales · Ads · Analytics · AI Insights · CRM Loop · Booking rules · Mobile app.

**Plans tab subtabs** (after h209):
- **Plans** — subscriptions, fixed-term, courses (kind ≠ class_pack)
- **Credit Packs** — class_pack only (NEW, h209) → `[data-testid="mbr-plans-tab-credit-packs"]` · CTA `mbr-credit-pack-add` opens `PlanEditorModal` with `defaultKind="class_pack"`.
- **Courses** — multi-week course templates.

**Classes & Timetable subtabs**: Timetable · Weekly builder · All classes
- The "+ New class" CTA lives ONLY on **All classes** subtab. From Timetable, click "All classes" first.
- ClassEditorModal opens via `mbr-class-editor` testid. Requires GET `/api/memberships/instructors` to populate picker; falls back to free-text if no instructors.

### Member portal — `/members` and `/m/:slug`
- Forced-dark surface (`data-theme="dark"` on root).
- Tabs: Book · Bookings · Pass (TOTP) · Plan · Profile.
- **Buy Credits modal**: `BuyCreditPackModal.js` triggers when booking returns 402, or via wallet/profile CTA. Calls `GET /api/member/credit-packs`, `POST /api/member/credit-pack-checkout`.
- Lives at `/m/:slug` (branded) and `/members` (canonical). White-label uses `BrandedMemberApp`.

### Instructor portal — `/instructor`
- Forced-dark; Today · Week · Pay · Profile. Reuses standard JWT login.
- Demo: `jake.ellis@demo.gymaxis / Instructor2026!`.

### Backend mocks / gates
- **Stripe Connect Express** — required for actual checkout. Test orgs without it can build plans + credit packs but checkout 402s. Onboard via Master Admin → Memberships → org drawer → Payments tab → "Connect Stripe".
- **Email** — Resend SDK wired but no key → in-dev emails log to console.
- **SMS** — TWILIO MOCKED (see Known Bugs).

---

## Operations

### Fault flow
- `/pulse` (Pulse Pro) or `/dashboard` (full). Equipment list + Log fault flow.
- POST `/api/issues` now (h208) inherits `site_id` from matched equipment. **Was missing before h208 → newly-logged faults invisible on site-filtered dashboard.**
- Multi-machine job: POST `/api/issues/batch` returns shared `job_id`.
- Coverage banner (h205): `CoverageBanner.jsx` shows manufacturer warranty + CRM aftersales contract status on both equipment drawer + Service Desk case.

_h218: Supplier picker sweep COMPLETE. `SupplierMultiPicker single` now wraps every supplier free-text input across Operations (PartsInventory, EquipmentInfoTab, InvoiceImportWizard, LiteDialogs.SupplierEditor) + Partner apply wizards. Curated UK fitness suppliers + org-custom suppliers come from `/api/suppliers/catalogue` (auth) and `/api/suppliers/catalogue/public` (anon)._
_h218: Pinned the strict per-site scope contract for `apply_site_lock` in tests (`test_iter_216bl_site_lock.py`). Brought the regression gate back to 100% green (23 pass + 96 trust-recovery)._

### Gym Floor
- Shared kiosk login per org. Tottenham test: `e2e-test-floor / password123!`.
- Two tabs: Handover Diary · Log a Fault. Fault POST inherits `site_id` (already did pre-h208).

---

## Service Desk

- `/service-desk` — unified hub (merged Service Ops in h53). Tabs: Dashboard · Cases · Scheduler · Engineers · Parts · Billing · Reports · Comms · Customers.
- Master admin + `is_service_desk` grant → access. Members granted via `POST /api/master-admin/service-desk/members/grant`.
- Engineer mobile app: `/svc/engineer/*` (jobs, quotes, invoices, payouts, diary, workspace, notifications, inbox, queue, sync panel).
- Public engineer card: `/r/:slug` (Iter 216h144) · Quote-accept landing `/q/:shortcode`.

_iter 220i: Per-machine work reports with custom-field templates, branded service-report PDFs (engineer logo + colours override org defaults), engineer branding upload UI at `/svc/engineer/branding`, fixed broken email logo (was 403 on dead `customer-assets.emergentagent.com` URL), `/svc/engineer/upcoming` interactive list._
_iter 220j: Pulsing attention badge on hamburger — single endpoint `GET /api/svc/engineer/attention` aggregates compliance expiries (<14d), past_due subscription, missing Stripe Connect, application status. Red pulse blocks paid work, amber is time-sensitive._
_iter 220k: Release-blocking P0 gates — `require_engineer_compliance_to_claim` dependency on `/queue/{id}/claim` + `/jobs/self-create` blocks engineers without DBS/RTW or with `compliance_paused`. Mid-job recovery: subscription cancellation auto-unassigns in-flight cases and emails dispatch admin._
_iter 220l: VAT-exempt toggle on partner record (auto-applies vat_rate=0 + "Not chargeable" on every invoice/quote PDF), engineer "My Ratings" page at `/svc/engineer/ratings` (avg / count / 30-day trend / distribution / per-case comments), customer "Request this engineer again" CTA on `/track/:token` post-rating, job-grant max-age (30 days default, capped 365)._
_iter 220m: Monthly engineer reputation report email — fires on the 1st via async background loop (`utils/reputation_reports.py`), includes avg / trend pill / star histogram / quote of the month / "Share on LinkedIn" CTA. Admin trigger at `POST /api/partners/admin/{id}/send-reputation-report` for manual resends._

---

## Partner Engineer Program

- `/partner-engineer` — application + dashboard for self-employed engineers (£30/mo plan, £15/mo at 5 referrals, free at 10).
- Access guard `require_engineer_app_access` enforces approved status + active subscription on every `/api/svc/engineer/*` route. Master admins / internal employees / customer-grant engineers bypass.
- **Release-ready as of iter 220m** (May 26 2026). Soft-launch target: 50 verified Partner Engineers via the Instagram campaign (assets in `/app/marketing/partner_engineer_launch/`).
- Compliance docs gate: `dbs` OR `rtw` (file uploaded, expiry future-or-absent) required to claim paid work. `compliance_paused` flag set by nightly sweep also blocks claims.
- Branding: engineer-level override (logo + primary/accent hex) beats org default on every PDF + portal.
- Ratings: customer rates from the public tracking page; engineer sees their reputation at `/svc/engineer/ratings`; happy customers can tap "Request {name} again" to flag the engineer for next time (stored in `svc_engineer_preferences`).
- Job Grants: customer-issued time-bound access to a specific case (30-day default expiry).
- Email: monthly reputation report on the 1st (idempotent via `reputation_reports.last_sent_period`).

---

## CRM

- `/crm` — CRMApp (lazy). Master admin / `module_access.crm = true` / full account_type. Pulse Pro / Lite / MOD pass via `<ModuleAccessGate>`.
- Contracts (`crm2_contracts`) — Aftersales coverage for Operations equipment; `serial_number` ↔ `crm2_contract_assets` is the join used by `utils/coverage.py`.
- CRM ↔ Operations bridge: `_mirror_issue_to_svc_case` fires when `resolution_type='engineer'`.

---

## MOD Portal

- MOD users (`account_type ∈ {mod_site, mod_branch, mod_org}`) — branded login at `/MODService`.
- Site-tier (LITE) — username login. Demo: `raf-brizenorton / BrizeNorton2026!`.
- HQ tiers (PRO) — email + mandatory MFA enrolment on first login. Demo: `catterick.demo.lead@army.mod.local / ArmyDemo2026!`.
- HQ scope helper: `utils/mod_scope.py` `resolve_mod_query_filter` rebinds queries to child orgs.

---

## Auth / SSO

- Standard JWT via `/api/auth/login`. Cookie + Bearer dual-auth.
- Silent refresh: 401 → one `/api/auth/refresh` retry (axios interceptor in `App.js`).
- Cross-login: CRM, Memberships, Service Desk use same JWT (UnifiedAuthProvider).
- Member portal uses SEPARATE token kind (`kind=member`) under `member_token` localStorage key.

---

## Active test credentials (one-stop reference)

| Role | Email | Password |
|------|-------|----------|
| Master Admin (always present) | admin@gymaxisai.com | MasterAdmin123! |
| Owner (canonical) — Pulse Fitness | e1.agent@gymaxisai.com | E1Agent123! |
| Engineer demo | jake.ellis@demo.gymaxis | Instructor2026! |
| Member demo (Emma) | emma.wright@demo.gymaxis | Member2026! |
| Service Desk | desk@pulsefitness.com | DeskAgent123! |
| MOD HQ (Catterick) | catterick.demo.lead@army.mod.local | ArmyDemo2026! |
| Gym Floor kiosk | `e2e-test-floor` | password123! |

See `/app/memory/test_credentials.md` for the full ledger (MOD branches, study test users, MFA users, etc.).

---

## Update protocol

When you change a module, edit THIS file in the same iteration:
1. Move the affected line in the Quick Map row if state changed.
2. Add a one-liner under the module section: `_h{iter}: <what changed>_`
3. If you mocked something, add it to `/app/memory/KNOWN_BUGS.md`.

## Pre-deployment gate (Iter 216h213)

Before every deploy, run **one of these**:
- `make pre-deploy` — full gate (regression + security + Stripe + lint)
- `make regression-full` — just the 84-test trust-recovery suite (~1 min)
- `bash /app/scripts/pre-deploy.sh` — same as `make pre-deploy`

On GitHub: the `Quality Gate` workflow runs the regression suite automatically
on every PR + push to `main`. Red = merge blocked.
