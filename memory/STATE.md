# GymAxis · Module State (Live)

> **Purpose**: Single-page snapshot of the *current state* of every module.
> Updated on every iteration. Never older than the latest commit.
> The next agent reads THIS first — not PRD.md (which is archival).
>
> **Status legend**: ✅ live & verified · 🟡 live but rough · ⚠️ partial / gated · ❌ broken / mocked

_Last refreshed: Iter 216h209 · Feb 18 2026_

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
| Engineer App         | `/svc/engineer/*`            | `/r/:slug`, `/engineer`              | `/api/svc/engineer/*`         | 🟡 |
| Gym Floor            | `/gym-floor`                 | n/a                                  | `/api/gym-floor/*`            | ✅ |
| Partner Engineers    | `/partner-engineer`          | `/partners/engineers`                | `/api/partners/*`             | 🟡 |

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

### Gym Floor
- Shared kiosk login per org. Tottenham test: `e2e-test-floor / password123!`.
- Two tabs: Handover Diary · Log a Fault. Fault POST inherits `site_id` (already did pre-h208).

---

## Service Desk

- `/service-desk` — unified hub (merged Service Ops in h53). Tabs: Dashboard · Cases · Scheduler · Engineers · Parts · Billing · Reports · Comms · Customers.
- Master admin + `is_service_desk` grant → access. Members granted via `POST /api/master-admin/service-desk/members/grant`.
- Engineer mobile app: `/svc/engineer/*` (jobs, quotes, invoices, payouts, diary, workspace, notifications, inbox, queue, sync panel).
- Public engineer card: `/r/:slug` (Iter 216h144) · Quote-accept landing `/q/:shortcode`.

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
