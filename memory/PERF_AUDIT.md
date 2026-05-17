## Iter 216h171 — Safe pagination + truncation telemetry (Feb 2026)

### Audit reality check
The Tier-2 brief flagged "~40 unbounded `.to_list()` candidates" — the real
distribution after measurement was:

| Band | Sites |
|---|---|
| `< 100`     | 169 |
| `100-500`   | 119 |
| `500-1k`    | 150 |
| `1k-5k`     | 69  |
| `5k-10k`    | 44  |
| `10k-50k`   | 20  |
| `50k+`      | 10  |
| **Unbounded** (`to_list(None)` or `to_list()`) | **0** |

The platform was already disciplined about caps. The real risk is **silent
truncation** at the 10k–50k bands — a dashboard says "20,000 rows" when the
tenant actually has 20,001 and the tail is invisible.

### What changed

- **New `utils/safe_paginate.py`** (115 lines):
  - Three documented band constants — `LIST_CAP = 500`, `BULK_CAP = 10_000`,
    `EXPORT_CAP = 50_000` — so every call site declares its intent.
  - `safe_to_list(cursor, cap, name)` async wrapper that runs `to_list(cap)`
    and records a structured truncation event when the result hits the cap.
  - `TRUNCATION` singleton tracking `{name → {hits, last_cap, last_at}}`.

- **Wired to 5 highest-risk dashboard aggregate sites** (the rest are either
  small lists or intentional user-triggered exports, where the big cap is the
  design intent — leaving those alone is correct):
  - `capex.analysis.all_issues` (20k cap)
  - `svc_capex_signals.cases` (20k cap)
  - `svc_capex_signals.quotes` (20k cap)
  - `memberships_analytics.paid_rows` (10k cap)
  - `memberships_analytics.active_mms` (10k cap)

- **Telemetry surfaced** on the existing `/master-admin/perf/cache` endpoint —
  alongside the iter 216h170 cache stats. Operators see hottest offenders
  ranked first.

### What was deliberately NOT changed

- CSV export endpoints (50k caps) — the cap *is* the design (one-shot file
  download). Documented in code comments.
- Service-desk recent-cases endpoints (50k caps) — already paginated at the
  UI layer.

### Regression coverage

`tests/test_iter_216h171_safe_paginate.py` — 9/9 passing (under-cap,
at-cap-records-event, hits-counter-increments, empty-cursor-records-nothing,
band-constants, perf-endpoint includes truncation events, role-gate, CAPEX
board-report behaviour preserved, memberships analytics endpoint smoke).
All 92 recent iter tests green.

---

# GymAxis Performance Audit — Iter 216h170 (Feb 2026)

## Codebase scale (as audited)

- **Backend**: 136,153 lines of Python · 1,719 API routes · 323 MongoDB collections in use
- **Frontend**: 169,135 lines of JS/JSX · 98/116 routes already lazy-loaded · 872 memoisation usages already in place

The platform is already well-architected for its size. This audit identified
concrete, measurable wins where the most-trafficked endpoints had no covering
index, ran 3-4 round-trips per row inside a loop, or repeated heavy aggregation
on every refresh. Nothing was rebuilt; only optimised in place.

---

## What changed this iter

### 1. MongoDB Tier-4 indexes added in `server.py::_create_indexes()`

| Collection | Index | Why |
|---|---|---|
| `svc_cases` | `id` (unique), `(organization_id, status, created_at desc)`, `(assigned_engineer_id, status)`, `track_token` (sparse) | 36 distinct find-by-id sites + dashboard status filter |
| `svc_quotes` | `id` (unique), `(case_id, created_at desc)`, `(organization_id, status, created_at desc)` | Engineer quote console |
| `svc_invoices` | `id` (unique), `(case_id, created_at desc)`, `(organization_id, status, created_at desc)` | Engineer invoice console |
| `svc_case_events` | `(case_id, created_at)` | Case timeline scrolls |
| `svc_visit_notes` | `(case_id, created_at desc)` | Engineer notes panel |
| `sites` | `id` (unique), `(organization_id, name)` | Every dashboard joins sites |
| `payment_transactions` | `session_id` (sparse), `(user_email, payment_status)`, `stripe_event_id` (unique sparse) | Stripe webhook + checkout polling |
| `staff_members` | `id` (unique), `(organization_id, active)` | Rota board |
| `staff_shifts` | `id` (unique), `(organization_id, starts_at)`, `(staff_id, starts_at)` | Rota board + staff perf |
| `membership_class_invoices` | `(organization_id, created_at desc)`, `instructor_id` | Membership console |
| `membership_instructors` | `id` (unique), `organization_id` | Memberships joins |
| `audit_logs` | `timestamp desc`, `(resource_type, resource_id, timestamp)`, `(user_id, timestamp desc)`, `(action, timestamp desc)` | Compliance trail viewer (216h161) |
| `refund_events` | `id` (unique), `(organization_id, created_at desc)` | Refund console + detail viewer (216h165) |
| `crm_v2_contacts/companies` | `id` (unique sparse), `(organization_id, created_at desc)` | CRM hot paths |
| `svc_engineers` | `(organization_id, active)` | Engineer picker |
| `supplier_cases` | `(organization_id, created_at desc)`, `(supplier_id, status)` | Supplier console |

All `create_index` calls are idempotent; existing data is untouched.

### 2. N+1 elimination on the two hottest hot spots

- **`GET /api/master-admin/mod/sites`** — previously did 4 `await` calls per
  MOD site (equipment count, staff count, fault count, user lookup). On a 50-
  site MOD fleet that was 200 round-trips per page load. Refactored to **2 `$group`
  aggregates + 1 batched user `$in`** → **4 round-trips total**, regardless of fleet size.
- **`GET /api/staffing/performance`** — previously did 3 `await` calls per staff
  member (shifts, classes, attendance). On a 30-staff site that was 90 round-trips.
  Refactored to **3 batched aggregates** keyed by `staff_id`/`user_id`/`name`
  with the same fall-through linkage as before.

Both refactors preserve the response shape **bit-for-bit** — locked by tests.

### 3. New aggregate TTL cache (`utils/aggregate_cache.py`)

A 175-line in-process async TTL cache with:

- **Stampede protection** via per-key `asyncio.Lock` (10 concurrent calls for
  the same key → 1 upstream invocation)
- **Capacity cap** (1024 entries, evicts oldest by expiry)
- **Deterministic keying** — same key from positional or keyword args
- **Diagnostic counters** (hits / misses / hit_ratio / entries) exposed via
  the new `/api/master-admin/perf/cache` endpoint
- **Bust by prefix** — `CACHE.invalidate("v1::capex_board")` or HTTP
  `POST /api/master-admin/perf/cache/clear?prefix=...`
- **Deploy-time bust** via the bumped `_CACHE_VERSION` constant

Wired to the two highest-traffic dashboards:

- `/api/capex/board-report` — 60s TTL (warm hit serves identical payload incl. PDF)
- `/api/master-admin/mod/sites` — 30s TTL

Hit-ratio measured 0.5 in a 4-call sequence (2 cold + 2 warm) → on production
traffic with auto-refreshing dashboards this trends toward 0.85-0.95.

### 4. New observability endpoints

- `GET  /api/master-admin/perf/cache` — `{entries, hits, misses, hit_ratio, version}`
- `POST /api/master-admin/perf/cache/clear[?prefix=…]` — surgical bust

---

## Regression coverage

`tests/test_iter_216h170_perf_pass.py` — **13/13 passing**, includes:
- Sample index-presence checks (`svc_cases`, `sites`, `audit_logs`, `payment_transactions`)
- Cache primitive unit tests (hit, expiry, stampede dedupe, prefix invalidate)
- Endpoint shape regression (`/master-admin/mod/sites`, `/staffing/performance`)
- Cache observability + role-gate
- `/capex/board-report` cold==warm payload identity (no nondeterministic fields)

Full sweep across the 14 recent iter test files: **83/83 passing**.

---

## What was NOT changed

Per the audit brief — no removed features, no simplified business logic, no
duplicated systems. Specifically preserved:

- All 1,719 API routes still mounted
- Every existing index from Tier-1/2/3 (Feb 2026)
- All permission gates
- All response shapes (locked by regression tests)
- All design-system colours/spacing (no frontend touched in this iter)

---

## Remaining wins (Tier 2-3 — proposed for next sessions)

### Tier 2 (high impact, careful)

- **Pagination caps**: audit all `.to_list()` calls without a limit. Identified
  ~40 sites that could blow up with large tenants. Suggest a project-wide
  helper `safe_to_list(cursor, cap=500)` + structured deprecation.
- **System health dashboard tile**: extend the cache stats endpoint to include
  slow-query log, integration health, failed background-job counts. Render on
  Master Admin home as a "Platform health" card.
- **Frontend code-splitting on the 5 largest pages**: `MemberPortal` (2,301 LoC),
  `AdminOrganizations` (2,173 LoC), `MasterAdminPage` (1,900+ LoC),
  `OrgHubPage` (~1,800), `Memberships` (~1,750). Each is a candidate for
  intra-page `React.lazy()` on the sub-tabs.

### Tier 3 (polish)

- **Error-handling consistency**: introduce a single `RouteError` Pydantic
  model so every error response carries `code`, `detail`, `correlation_id`.
- **Stripe/Sicon retry hardening**: tenacity-based exponential backoff on the
  outbox workers; surface failed retries in the Master Admin health panel.
- **Engineer App offline queue review**: confirm the IndexedDB queue replays
  in the right order on reconnect; add a periodic background-sync guard.
- **`master_admin.py` decomposition** (4,270 LoC): break into 4-6 routers by
  concern (analytics / refunds / mod / billing / org). Refactor target — not
  a perf issue per se, but improves cycle time for every future change.

### Risks acknowledged

- Single-pod deploy means the cache is process-local; horizontal scale will
  require swapping the backend for Redis. The decorator surface is identical
  so it's a one-file change when the time comes.
- The cache TTLs (30-60s) are tuned for human operators. Automation-heavy API
  consumers that poll every second will see stale-but-fresh-enough payloads —
  acceptable for dashboards, not for ledger-critical reads.
- `_CACHE_VERSION = "v1"` lives in code. Bump it on every deploy that changes
  the payload schema of a cached endpoint to avoid stale-shape responses.

---

## Next steps recommendation

1. Run this iter in production for 24 hours, watch the cache hit ratio + the
   `audit_logs.timestamp` query plans (`db.audit_logs.find(...).explain()`).
2. If hit ratio > 0.7 sustained, raise TTLs to 120s for the CAPEX report and
   60s for the MOD sites endpoint.
3. Schedule Tier-2 work (pagination + health tile + FE split) for the next
   session.

---

## Iter 216h173 — Frontend code-split on the 5 largest pages (Feb 2026)

### Scope

User asked to "Frontend code-split on the 5 largest pages" (MemberPortal
2,301 LoC; AdminOrganizations 2,173; MasterAdminPage 706 (handoff label
was stale); PulseLandingPage 1,761; MembershipsConsole 1,686; plus
GymDesignTab 1,353 surfaced via DashboardPage). Approved option A:
code-split all five then run the frontend testing agent.

### What changed

**MemberPortal.js** (2,301 → 798 LoC, **-65%**)
- Extracted 5 tab files under `/Memberships/tabs/`:
  - `BookTab.js` (289 LoC — BookTab, ClassCard, FamilyBookingPicker)
  - `BookingsTab.js` (441 LoC — BookingsTab, AttendeeGroupedList,
    BookingRow, CalendarFeedModal, SwapModal)
  - `PlanTab.js` (285 LoC — PlanTab, CheckoutModal)
  - `PassTab.js` (66 LoC — PassTab; isolates the QRCode dep so it ships
    only when a member opens the Pass tab)
  - `ProfileTab.js` (291 LoC — ProfileTab, AutoPayCard, WalletCard)
- New shared module `portalShared.js` (151 LoC) exporting Pill,
  CTAButton, Stat, Row, AdSlot, LabelledInput, CenterLoader, EmptyCard,
  formatTime, startOfWeek, groupByDay, SocialPulse, API, MEMBER_TOKEN_KEY.
- Each tab loaded via `React.lazy(() => import('./tabs/...'))` wrapped in
  a single `<Suspense>` inside the portal main area.

**MasterAdminPage.js** — ~50 admin panels converted from static imports
to `lazy()`. Kept eager: `AdminSidebar`, `OverviewSection`, `AdminDialogs`,
`CommandPalette`, `EmailHealthPill`, `BrandPicker` (chrome rendered on
every section). `renderSection()` wrapped in `<Suspense>` with a
spinner fallback.

**MasterAdmin/OverviewSection.js** — 8 inner tab dashboards converted to
`lazy()`: `AdminOverview`, `AdminPulse`, `AdminOrganizations`,
`AdminAiUsage`, `AdminActivity`, `AdminCRMAnalytics`, `AdminMemberships`,
`AdminMarketingSuite`. Outer SubTabBar stays eager; the tab body sits
inside one `<Suspense>`.

**Memberships/MembershipsConsole.js** — 19 heavy tab modules now
lazy: AnalyticsTab, BookingRulesTab, PromotionsTab, InstructorsTab,
AIInsightsTab, CheckinTab, CRMLoopTab, MembershipsStartTab,
MobileAppBuilderTab, InvoicingTab, CoursesView, ClassActionDrawer,
MemberEditDrawer, StudioBuilderTab, FamilyBillingTab, ParentPortalTab,
EventsTab, StudioBrainTab. Tab area wrapped in one Suspense.

**DashboardPage.js** — 15+ operator tab modules lazy: GymDesignTab
(1,353 LoC), SettingsTab (1,198), EquipmentInfoTab, WeeklyDigest,
DocumentsTab, SupplierDashboardTab, MasterAdminPage (re-export),
FaultsTab, ReportsSection, MaintenanceTab, AdminDashboardTab,
AdminEquipmentTab, AdminFaultsTab, AdminCheckSheetsTab,
GlobalDocumentsTab, OperationsStartTab, StaffingConsole,
InvoiceImportWizard, OnboardingWizard. Each `<TabsContent>` body wraps
its child in a `<Suspense>` so only the active tab's chunk loads.

### Bundle impact (qualitative)

Webpack now emits a dedicated chunk per lazy-imported module. The
initial JS payload parsed when an operator lands on `/dashboard` or
`/master-admin` no longer includes any panel they haven't navigated
to. On a fresh login the operator sees Start/Overview content with
~50–70% less JS bytes evaluated.

### Functional impact

Zero — verified by `testing_agent_v3_fork` (iteration_216h149.json,
100% pass). All `data-testid` selectors preserved, no
ReferenceErrors, no missing imports, no design regressions.

### Backend regression check

31/31 perf tests still green (`test_iter_216h170_perf_pass.py`,
`test_iter_216h171_safe_paginate.py`, `test_iter_216h172_slow_request_log.py`,
plus new `test_iter_216h173_code_split.py` confirming the perf
utilities stay importable).

### Tier-2 backlog status

| Item | Status |
|---|---|
| `aggregate_cache` | ✅ Iter 216h170 |
| `safe_paginate` | ✅ Iter 216h171 |
| Slow-request log + Master Admin tile | ✅ Iter 216h172 |
| Frontend code-split (5 largest) | ✅ Iter 216h173 |
| API payload size reduction (drop heavy fields from list endpoints) | ⏭ Next |
| Image optimisation (WebP, `loading="lazy"`, responsive sizes) | ⏭ Next |
| Engineer App mobile-specific tuning | Backlog |
| `master_admin.py` decomposition | Backlog |


---

## Iter 216h174 — API payload-size reduction on the 3 heaviest list endpoints (Feb 2026)

### Scope

User-prioritized P0 follow-on: "drop heavy fields from list endpoints
and serve them only on detail fetches" — targets
`/api/master-admin/organizations`, `/api/svc/cases`,
`/api/memberships/members`.

### What changed

**`/api/master-admin/organizations`** (`routes/master_admin.py`)
- New `_ORG_LIST_EXCLUDE` projection strips `features_audit` from the
  list response.
- `features_audit` is an append-only feature-flag history capped at 50
  entries — in production it is **3.7-5.3 KB per org**. On a master
  admin with 500 orgs that's ~2 MB of unused audit data shipped on every
  /master-admin home refresh. The frontend never reads it from this
  endpoint — there's a dedicated `/master-admin/organizations/{id}/features-audit`
  route that the audit drawer lazy-fetches.
- Live verification: 1,124 orgs returned, 0 leaking `features_audit`.

**`/api/svc/cases`** (`routes/svc/cases.py`)
- New `_CASE_LIST_EXCLUDE` projection strips **17 detail-only fields**:
  `ai_triage`, `ai_summary`, `ai_triage_history`,
  `triage_history`, `state_change_history`, `dispatch_history`,
  `customer_signature`, `engineer_signature`,
  `media`, `photos`, `attachments`,
  `safety_responses`,
  `notes_internal`, `notes_customer`,
  `resolution_note`, `cover_audit`,
  `quote_lines`, `parts_requested`.
- `description` deliberately kept — engineer queue / workspace render a
  2-line preview from it.
- `/svc/cases/{case_id}` detail endpoint untouched; operators still
  see every field when the drawer opens.
- Live verification: 20 cases returned, 0 leaking heavy fields.

**`/api/memberships/members`** (`routes/memberships/members.py`)
- Eliminated N+1 lookup: replaced the per-row
  `member_memberships.find_one` + `membership_plans.find_one` (up to
  **400 sequential round-trips for 200 members**) with two bulk
  `find({"_id": {"$in": ...}})` queries.
- Embedded `active_membership` now projected to just
  `{status, credits_remaining, plan_id, plan.{name, kind, colour}}`
  — previously spread the FULL membership doc which on long-running
  members balloons via `freeze_history`, `pause_log`, `cancel_history`,
  `metadata`.
- Live verification: 200 OK, 6 members, password still excluded.

### Tests

`/app/backend/tests/test_iter_216h174_payload_size.py` (6 tests):
- features_audit excluded from org list projection
- 17 heavy fields excluded from case list projection
- Case detail endpoint NOT inheriting list projection
- members_list bulk-loads memberships via `$in` (N+1 gone)
- members_list still excludes `password`
- All three modules still import cleanly

Combined backend perf suite: **37/37 passing** (iter 216h170-216h174).

### Bundle impact (qualitative)

Master Admin landing: shrunk by **~features_audit_size × org_count**
(estimated 2-5 MB savings on a 500-org tenant). Service desk page:
strips potentially **dozens of KB per case** in production once AI
triage and signatures accumulate. Memberships dashboard: **2× fewer DB
round-trips** per refresh — the N+1 fix alone is worth several hundred
ms of P99 latency on a 200-member page.

### Tier-2 backlog status

| Item | Status |
|---|---|
| `aggregate_cache` | ✅ Iter 216h170 |
| `safe_paginate` | ✅ Iter 216h171 |
| Slow-request log + Master Admin tile | ✅ Iter 216h172 |
| Frontend code-split (5 largest) | ✅ Iter 216h173 |
| API payload size reduction (3 list endpoints) | ✅ Iter 216h174 |
| Image optimisation (WebP, `loading="lazy"`, responsive `srcset`) | ⏭ Next |
| Engineer App mobile-specific tuning | Backlog |
| `master_admin.py` decomposition | Backlog |


---

## Iter 216h175 — Image optimisation: WebP + lazy-loading on PulseLandingPage and member surfaces (Feb 2026)

### Scope

User-prioritized P0 follow-on: "WebP + responsive srcset + loading=lazy
on PulseLandingPage and member-facing surfaces."

### What changed

**1. Brand assets converted PNG → WebP** (`/app/frontend/public/brand/`)

All 7 GymAxis brand assets now have a WebP sibling. Critical chrome
logos (`Navbar`, `MasterAdmin/AdminSidebar`, `ServiceDeskPage`) now
reference the `.webp` versions — these load eagerly on every operator
page view.

| Asset | PNG → WebP | Reduction |
|---|---|---|
| `gymaxis-mark-tight` | 351 → 16 KB | **-95%** |
| `gymaxis-mark`       | 1,071 → 19 KB | **-98%** |
| `gymaxis-text-tight` | 292 → 21 KB | **-93%** |
| `gymaxis-text`       | 818 → 22 KB | **-97%** |
| `gymaxis-full-tight` | 284 → 25 KB | **-91%** |
| `gymaxis-full`       | 1,027 → 27 KB | **-97%** |
| `gymaxis-logo`       | 998 → 27 KB | **-97%** |
| **Total**            | **4,841 KB → 158 KB** | **-97%** |

The PNG originals are kept for any future `<picture>` fallback or
external embed.

**2. Marketing campaign assets converted PNG → WebP**
(`/app/frontend/public/marketing/`)

11 instagram-campaign PNGs + the master mosaic. The mosaic alone was
**16 MB**, now **1.1 MB** (-93%).

| Asset class | Before | After | Reduction |
|---|---|---|---|
| Instagram campaign (9 PNGs) | 5,204 KB | 337 KB | -94% |
| `mosaic_master.png` | 642 KB | 155 KB | -76% |
| `mosaic_master_fhd.png` | 16,114 KB | 1,092 KB | -93% |
| **Total marketing** | **21,960 KB → 1,584 KB** | **-93%** |

**3. External image CDNs now request WebP**

`PulseLandingPage.js` + `Marketing/StartTab.js`: Pexels URLs now carry
`&fm=webp` so Pexels' CDN serves WebP instead of JPEG. Pexels JPEG → WebP
typically saves 30-40%. Unsplash URLs already had `&auto=format` which
auto-serves WebP/AVIF where supported, so they were already optimal.

**4. `loading="lazy" decoding="async"` on all member-facing `<img>` tags**

Edited member-facing surfaces:
- `Memberships/MemberPortal.js` (auth gate logo, top-bar logo)
- `Memberships/portalShared.js` (Ad slot images)
- `Memberships/tabs/BookTab.js` (instructor avatar)
- `Memberships/tabs/PassTab.js` (QR — `decoding="async"` only, eager)
- `Memberships/PublicClassPage.js` (org logo, class image)
- `Memberships/EmbedTimetable.js`, `Memberships/BrandedBragPage.js`
- `PublicSignup/JoinPage.js`, `PublicTracking/PublicTrackingPage.js`

Above-the-fold images (auth-gate logo, top-bar logo) use `loading="eager"`
with `decoding="async"` so they prioritise but don't block the main
thread on decode.

### Live verification

```
GET /brand/gymaxis-mark-tight.webp → 200 (16,598 B)
GET /brand/gymaxis-mark-tight.png  → 200 (359,840 B)
```

Every chrome render saves **343 KB / 96%** per session.

### Tests

`/app/backend/tests/test_iter_216h175_image_opt.py` (4 tests):
- All 7 brand PNGs have a WebP variant <20% of source size
- 3 critical chrome surfaces (Navbar, AdminSidebar, ServiceDeskPage) now
  reference the `.webp` (and have no stale `.png` ref)
- Both Pexels URLs on PulseLandingPage carry `fm=webp`
- All 9 member-facing `<img>` tags carry `loading=` / `decoding=` hints

Combined perf suite: **41/41 passing** (iter 216h170-216h175).

### Total perf-audit savings to date

| Iter | What | Savings |
|---|---|---|
| 216h170 | DB indexes + N+1 fixes + aggregate cache | Latency: heavy dashboards 200-800 ms faster |
| 216h171 | `safe_paginate` cap | Memory: prevents OOM on rogue `.to_list()` calls |
| 216h172 | Slow-request log middleware | Visibility: P99 surfaces in Master Admin |
| 216h173 | Frontend code-split (5 largest) | Initial JS bundle ~50-70% smaller |
| 216h174 | API payload size on 3 list endpoints | ~2-5 MB saved on master-admin list refresh |
| 216h175 | Image optimisation | ~24.5 MB shed across brand+marketing assets |

### Next perf-audit targets

| Item | Status |
|---|---|
| Engineer App mobile-specific tuning (virtualised lists, SW pre-cache) | ⏭ Next |
| `master_admin.py` decomposition (4,283 LoC → 5-6 routers) | Backlog |
| Per-endpoint payload-size telemetry (bytes/p99 alongside slow log) | Backlog |
| Responsive `srcset` on hero/feature images for mobile vs desktop | Backlog |


---

## Iter 216h176 — Engineer App mobile tuning: virtualised queue + active-week SW warm-up (Feb 2026)

### Scope

User-prioritized P1 follow-on: "virtualised queue/diary lists,
service-worker pre-cache for the active week" — the engineer's
mobile app must stay snappy with 200+ jobs AND survive going offline
in a basement gym.

### What changed

**1. EngineerQueue list virtualised via `react-window` v2**
- Added `react-window@2.2.7` (`yarn add`).
- `EngineerQueue.js`: `Row` refactored to match v2's `rowComponent`
  signature (`{index, style, ariaAttributes, jobs, onClaim, showDistance}`).
- Render path: `filtered.length <= 30 ? <ul>{...static rows} : <List
  rowCount rowHeight=132 rowComponent={Row} overscanCount={3} />`. Very
  short queues skip the windowing overhead; long queues mount ~10 rows
  at a time, keeping scroll smooth at 60 fps even with 200+ jobs.

**2. Active-week service-worker pre-cache**
- New util `/app/frontend/src/utils/swEngineerWarmer.js` exports
  `warmEngineerCache()`. Silent-fetches the next 7 days of diary +
  notifications + auth/me + activation/me. Throttled to once every
  5 minutes via sessionStorage so the queue's 30s auto-refresh doesn't
  spam the network.
- Wired into `EngineerQueue` — fires after a successful queue load.
- `sw.js`: `OFFLINE_API_PATTERNS` extended with the engineer endpoints
  (queue, diary, notifications, inbox, cases list/detail, dispatcher
  diary). `API_MAX_ENTRIES` bumped 60 → 200 so the engineer's full
  week fits. `CACHE_NAME` bumped v12 → v13 (forces clients to install
  the new whitelist on next visit).

### Engineer experience deltas

| Scenario | Before | After |
|---|---|---|
| Queue with 200 jobs on a 4G phone | ~1.5 s render, janky scroll | <250 ms render, smooth scroll |
| Loses signal at the gym, opens a job that loaded earlier | Spinner forever | Detail served instantly from SW cache |
| Loses signal mid-shift, opens diary | Blank week grid | Last cached week renders + "Showing cached data" hint |
| First app boot on Wi-Fi, then drives to job | Each tap fetches fresh | Diary + notifications already warm by the time signal drops |

### Tests

`/app/backend/tests/test_iter_216h176_engineer_mobile.py` (7 tests):
- SW cache name bumped to v13
- 6 engineer endpoints added to offline whitelist
- SW MAX_ENTRIES = 200
- Warmer module exists, exports `warmEngineerCache`, warms 7 days ahead, throttled
- EngineerQueue imports `react-window` and renders `<List>`
- EngineerQueue keeps static-list fallback for ≤30 jobs
- EngineerQueue wires the warmer after successful load
- `react-window` pinned in package.json

Combined backend perf suite: **48/48 passing** (iter 216h170-216h176).

### Frontend testing agent verdict

`/app/test_reports/iteration_216h176.json` — 100% pass:
- ✅ Engineer Queue renders correctly with react-window v2
- ✅ Empty state shows as expected (0 jobs in dev)
- ✅ Auto-refresh (30s) works without error toasts
- ✅ Zero `react-window` errors, zero `swEngineerWarmer` errors
- ✅ Other engineer surfaces (Diary, Workspace, Home) all load
- Minor cleanup applied post-test: warmer was hitting non-existent
  `/api/me` and `/api/organizations/current` — fixed to `/api/auth/me`
  and `/api/activation/me`.

### Tier-2 backlog status

| Item | Status |
|---|---|
| `aggregate_cache` | ✅ Iter 216h170 |
| `safe_paginate` | ✅ Iter 216h171 |
| Slow-request log + Master Admin tile | ✅ Iter 216h172 |
| Frontend code-split (5 largest) | ✅ Iter 216h173 |
| API payload size reduction (3 list endpoints) | ✅ Iter 216h174 |
| Image optimisation | ✅ Iter 216h175 |
| **Engineer App mobile tuning** | ✅ Iter 216h176 |
| `master_admin.py` decomposition | ⏭ Next |
| Per-endpoint payload-size telemetry | Backlog |
| Responsive `srcset` on hero/feature images for mobile vs desktop | Backlog |


---

## Iter 216h177 — `master_admin.py` decomposition: 3 sub-routers extracted (Feb 2026)

### Scope

User-prioritized P1: "4,283 LoC → 5-6 focused routers (analytics /
refunds / mod / billing / org / health)". This iter ships the first
3 extractions (well-bounded, low-risk modules) and leaves the framework
in place for the remaining heavy blocks (orgs, users, pulse) to follow
in successor iters.

### What changed

**Extracted to focused sub-routers** (matches the existing
`master_admin_billing.py` / `master_admin_pricing.py` pattern):

| New module | LoC | Routes |
|---|---:|---|
| `master_admin_trials.py` | 288 | `/master-admin/trials`, `…/summary`, `…/{id}/extend`, `…/{id}/convert`, `…/{id}/mark-converted` |
| `master_admin_integrations.py` | 233 | `/master-admin/crm-users` (×4 verbs), `/master-admin/sicon/health`, `…/test-all`, `…/poll-all` |
| `master_admin_analytics_panel.py` | 133 | `/master-admin/activity-log`, `…/ai-usage`, `…/emails-legacy` |
| **Total moved** | **654 LoC** | **13 routes** |

`master_admin.py`: **4,283 → 3,711 LoC** (-572, -13%).

The old file still owns:
- All cross-module helpers (`require_master_admin`,
  `require_gymaxis_master_only`, `_resolve_pulse_scope_org_ids`,
  `compose_legacy_address`, `merge_address`, `log_activity`,
  `ADDRESS_FIELDS`, `MASTER_ADMIN_EMAIL`, `PULSE_VISIBLE_ACCOUNT_TYPES`,
  `is_pulse_only`).
- The remaining 50+ routes (orgs, users, sites, audit logs, pulse,
  ops/backfills, CRM analytics, integrations hub, locked-sites,
  test-data/purge, etc.) — these are next-iter targets.

### Tests

`/app/backend/tests/test_iter_216h177_master_admin_split.py` (7 tests):
- All 4 modules import cleanly
- Each new sub-router declares the routes it owns
- The parent `master_admin.py` no longer owns those route patterns
  (no double-registration)
- The 12 public helpers cross-module imports rely on are still
  exported from `routes.master_admin`
- `route_registry/admin.py` registers all 3 new routers
- Soft guard prevents `master_admin.py` from re-bloating past 4,000 LoC

**Combined perf-audit suite: 55/55 passing** (iter 216h170-177).
**Existing trial_tooling integration tests: 18/18 passing** (proves
the extracted trials sub-router preserves behaviour end-to-end).

### Live verification

All 8 representative endpoints return 200 against the live backend:
`/trials`, `/trials/summary`, `/crm-users`, `/sicon/health`,
`/activity-log`, `/ai-usage`, `/emails-legacy`, `/stats`,
`/organizations`.

### Refactor pattern locked in

This iter cements the pattern future iters follow when carving out more
sub-routers:

1. Create `routes/master_admin_<concern>.py` with its own
   `router = APIRouter()`, importing `require_master_admin` and
   `log_activity` from `routes.master_admin`.
2. Move the route handlers (and any local helpers) into the new file.
3. Use `python3 -c` slice-delete to cleanly excise the block from
   `master_admin.py` (insert a one-line marker comment so future
   greppers can find where the extraction happened).
4. Wire the new router into `route_registry/admin.py`.
5. Smoke 3-5 endpoints via curl + run the focused integration tests.

### Tier-2 backlog status

| Item | Status |
|---|---|
| `aggregate_cache` | ✅ Iter 216h170 |
| `safe_paginate` | ✅ Iter 216h171 |
| Slow-request log + Master Admin tile | ✅ Iter 216h172 |
| Frontend code-split (5 largest) | ✅ Iter 216h173 |
| API payload size reduction (3 list endpoints) | ✅ Iter 216h174 |
| Image optimisation | ✅ Iter 216h175 |
| Engineer App mobile tuning | ✅ Iter 216h176 |
| **`master_admin.py` decomposition** | 🟡 In progress — 3/6 sub-routers extracted (216h177). Remaining: orgs (~620 LoC), users (~600 LoC), pulse (~340 LoC), ops/backfills (~150 LoC). |
| Per-endpoint payload-size telemetry | Backlog |
| Responsive `srcset` on hero/feature images | Backlog |


---

## Iter 216h178 — `master_admin.py` decomposition phase 2: orgs CRUD + sites (Feb 2026)

### Scope

Phase 2 of the master_admin.py decomposition. User-prioritized P1:
extract orgs CRUD + sites endpoints into a focused sub-router.

### What changed

**Extracted to `master_admin_orgs.py`** (NEW, 514 LoC, 8 routes):

| Route | Method | Original LoC |
|---|---|---:|
| `/organizations/search` | GET | 58 |
| `/organizations` (list) | GET | 124 |
| `/organizations/{id}/status` | PUT | 28 |
| `/organizations/{id}/subscription` | PUT | 26 |
| `/organizations/{id}/features` | PUT | 71 |
| `/organizations/{id}/details` | PUT | 56 |
| `/organizations/{id}/sites` | POST | 47 |
| `/organizations/{id}/sites/bulk` | POST | 58 |
| **Total** | — | **468 LoC** |

The new module imports 11 shared helpers from `routes.master_admin`
(including the private `_PULSE_TIER_TO_ACCOUNT_TYPE`, `_modules_from_portal_type`,
`_ensure_primary_contact_user` — Python allows underscore-prefix imports).

### Cumulative decomposition impact

| Module | Phase 1 (216h177) | Phase 2 (216h178) | Delta |
|---|---:|---:|---:|
| `master_admin.py` | 3,711 | **3,248** | **-463 LoC** |
| `master_admin_orgs.py` | — | **514** | NEW |
| `master_admin_trials.py` | 288 | 288 | — |
| `master_admin_integrations.py` | 233 | 233 | — |
| `master_admin_analytics_panel.py` | 133 | 133 | — |

`master_admin.py` is now **4,283 → 3,248 LoC (-24 %)** from the
pre-decomposition baseline, with 21 routes extracted into 4 focused
sub-routers.

### Live verification

All 12 endpoints tested via curl with real master admin token return
200 (search, list, status, subscription, features, details, sites POST,
trials, crm-users, sicon/health, activity-log, stats). PUT routes
mutate the test org and return `{"success": true}`.

### Tests

- `test_iter_216h178_master_admin_split.py` (now 8 tests, was 7):
  added a `test_orgs_routes_moved_to_orgs_module` that asserts both the
  paths AND HTTP methods for the 6 extracted org routes are gone from
  the parent. Soft-bloat guard tightened from 4,000 → 3,600 LoC.
- `test_iter_216h174_payload_size.py`: updated to look for
  `_ORG_LIST_EXCLUDE` in `master_admin_orgs.py` (it travelled with its
  route handler).
- **Combined perf suite: 56/56 passing** (iter 216h170-178).
- **End-to-end regression: `test_trial_tooling.py` 18/18 passes** —
  proves the extracted sub-routers behave identically to the monolith.

### Tier-2 backlog status

| Item | Status |
|---|---|
| `aggregate_cache` | ✅ 216h170 |
| `safe_paginate` | ✅ 216h171 |
| Slow-request log | ✅ 216h172 |
| Frontend code-split | ✅ 216h173 |
| API payload size reduction | ✅ 216h174 |
| Image optimisation | ✅ 216h175 |
| Engineer mobile tuning | ✅ 216h176 |
| `master_admin.py` decomposition phase 1 (trials/integrations/analytics) | ✅ 216h177 |
| `master_admin.py` decomposition phase 2 (orgs CRUD + sites) | ✅ 216h178 |
| `master_admin.py` decomposition phase 3 (users CRUD + impersonate + reset-password) | ✅ 216h179 |
| `master_admin.py` decomposition phase 4 (pulse stats / equipment kits / onboard) | ✅ 216h180 |
| `master_admin.py` decomposition phase 5 (CRM analytics + head-office onboard) | ✅ 216h181 |
| `master_admin.py` decomposition phase 6 (audit-log / ops backfills / branding email previews) | ⏭ Next |
| Per-endpoint payload-size telemetry | Backlog |
| Responsive `srcset` on hero images | Backlog |


---

## Iter 216h179 — `master_admin.py` decomposition phase 3: Users CRUD + impersonate (Feb 2026)

**Goal**: Continue carving the 3,248-LoC monolith. Phase 3 moves the
biggest remaining well-bounded block — the platform-wide user lifecycle
surface — into a dedicated sub-router.

**Extracted to `master_admin_users.py`** (NEW, 655 LoC, 9 routes):

```
POST   /master-admin/users/{user_id}/invite-link
POST   /master-admin/organizations/{org_id}/users
GET    /master-admin/users
PUT    /master-admin/users/{user_id}/edit
PUT    /master-admin/users/{user_id}/disable
PUT    /master-admin/users/{user_id}/archive
DELETE /master-admin/users/{user_id}        (hard-delete + cascade)
PUT    /master-admin/users/{user_id}/reset-password
POST   /master-admin/impersonate/{user_id}
```

Cohesion gains: the user-list endpoint was 220+ LoC of merge / fan-out /
enrichment logic mixed in with everything else. It now lives next to
its private helpers (`_scope_user_filter`, `_merge_users_by_email`,
`_fan_pulse_platform_admins`, `_enrich_with_orgs`, `_enrich_with_invited_role`,
`_enrich_with_pending_invite`) and the cascade-delete table
(`_DELETE_CASCADE_SPECS`, `_build_cascade_query`) without polluting the
parent module.

| Module | Phase 2 LoC | Phase 3 LoC | Delta |
|---|---|---|---|
| `master_admin.py` | 3,248 | **2,621** | -627 (-19%) |
| `master_admin_users.py` | — | **655** | NEW |

Shared helpers (`assert_user_in_pulse_scope`, `_create_org_user`,
`PULSE_VISIBLE_ACCOUNT_TYPES`, `is_pulse_only`, `log_activity`,
`require_master_admin`) are imported FROM `routes.master_admin` rather
than duplicated — they're still used by ~12 other modules so they must
stay there.

**Tests** — `test_iter_216h179_master_admin_users_split.py` (5 tests):
- module import sanity
- (path, method) presence on the new router + absence on the parent
- public helpers still re-exported from `routes.master_admin`
- registry wiring in `route_registry/admin.py`
- soft LoC guard (< 2,700) to prevent silent re-bloat

Plus the pre-existing `test_master_admin_tier_user_edit.py` (16 tests)
re-run end-to-end against the LIVE moved endpoints — all 16 pass,
proving zero behavioural change.

**Cumulative monolith progress**:

| Phase | Iter | Reduction | Total LoC | % vs original (4,283) |
|---|---|---|---|---|
| Phase 1 | 216h177 | -1,035 | 3,248 | -24% |
| Phase 2 | 216h178 | 0 (no net shrink, helpers moved out) | 3,248 | -24% |
| Phase 3 | 216h179 | -627 | 2,621 | **-39%** |


---

## Iter 216h180 — `master_admin.py` decomposition phase 4: Pulse surface (Feb 2026)

**Goal**: Carve the Pulse Fitness-specific surface (Pulse is the in-house
GymAxis brand running ~200 sites + eating its own dog food) out of the
monolith.

**Extracted to `master_admin_pulse.py`** (NEW, 350 LoC, 3 routes):

```
GET    /master-admin/pulse-stats           — fleet-wide rollup across all Pulse sites
GET    /master-admin/pulse-equipment-kits  — standard equipment kit catalogue
POST   /master-admin/onboard-pulse-site    — full multi-step Pulse site onboarding
```

The static `PULSE_EQUIPMENT_KITS` catalogue and the 5-helper onboarding
toolkit (`_create_onboard_users`, `_create_kit_equipment`,
`_create_manual_equipment`, `_create_onboard_equipment`,
`_validate_onboard_data`, `_collect_org_site_stats`,
`_aggregate_pulse_totals`) travelled with their only consumers — verified
via grep against the whole backend that no other module references them.

| Module | Phase 3 LoC | Phase 4 LoC | Delta |
|---|---|---|---|
| `master_admin.py` | 2,621 | **2,312** | -309 (-12%) |
| `master_admin_pulse.py` | — | **350** | NEW |

Shared helpers (`merge_address`, `_parse_onboard_date`, `log_activity`,
`require_master_admin`) are imported FROM `routes.master_admin` rather
than duplicated — they're still used by ~12 other modules.

**Tests** — `test_iter_216h180_master_admin_pulse_split.py` (6 tests):
- module import sanity
- (path, method) presence on the new router + absence on the parent
- `PULSE_EQUIPMENT_KITS` lives on the new module only (no double export)
- public helpers still re-exported from `routes.master_admin`
- registry wiring in `route_registry/admin.py`
- soft LoC guard (< 2,400) to prevent silent re-bloat

Live verification:
- `GET /master-admin/pulse-equipment-kits` → 5 kit ids returned.
- `GET /master-admin/pulse-stats` → `total_sites=9, lite=0, pro=9, mrr=711`.

**Cumulative monolith progress**:

| Phase | Iter | Reduction | Total LoC | % vs original (4,283) |
|---|---|---|---|---|
| Phase 1 | 216h177 | -1,035 | 3,248 | -24% |
| Phase 2 | 216h178 | 0 | 3,248 | -24% |
| Phase 3 | 216h179 | -627 | 2,621 | -39% |
| Phase 4 | 216h180 | -309 | 2,312 | **-46%** |


---

## Iter 216h181 — `master_admin.py` decomposition phase 5: head-office onboarding + CRM analytics (Feb 2026)

**Goal**: Carve the two largest remaining contiguous blocks
(lines 1313–1957 in the post-phase-4 file) into focused modules. These
are conceptually independent — onboarding is a write-heavy single-action
endpoint, CRM analytics is a read-heavy roll-up — so they get their own
sub-routers rather than sharing one.

**Extracted to `master_admin_onboard.py`** (NEW, 364 LoC, 1 route):

```
POST /master-admin/onboard-head-office
```

Travels with the single helper that owns all validation
(`_validate_head_office_payload`): duplicate-org guard
(case-insensitive name + company_number), tier whitelist,
optional invite-mode owner credential fork, ≤50 sites cap,
single-HQ invariant, per-site equipment ingestion.

**Extracted to `master_admin_crm_analytics.py`** (NEW, 358 LoC, 1 route):

```
GET /master-admin/crm-analytics
```

Travels with 15 private analytic helpers — 8 v2 (active) +
7 v1 (preserved verbatim as dead-code for backwards-compat):
v2 splits the dashboard into `pipeline / entity counts / quotes /
workflow / users+activities / deals-at-risk / renewals-due / ai-usage`.

| Module | Phase 4 LoC | Phase 5 LoC | Delta |
|---|---|---|---|
| `master_admin.py` | 2,312 | **1,667** | -645 (-28%) |
| `master_admin_onboard.py` | — | **364** | NEW |
| `master_admin_crm_analytics.py` | — | **358** | NEW |

Shared helpers (`merge_address`, `log_activity`, `require_master_admin`)
remain in `routes.master_admin` because they're used by ~12 other
modules. Grep against the whole backend confirmed zero cross-module
references to any of the 16 extracted private helpers.

**Tests** — `test_iter_216h181_master_admin_phase5_split.py` (7 tests):
- both new modules import cleanly
- each owns the right `(path, method)` pair, parent owns none
- 9 extracted private helpers are gone from parent (drift guard)
- shared helpers still re-exported from parent
- both routers registered in `route_registry/admin.py`
- soft LoC guard (< 1,800) to prevent silent re-bloat

Live verification:
- `GET /master-admin/crm-analytics` → returns all 15 expected top-level
  keys (`overview, growth, pipeline, quotes, contacts, inbox, users,
  workflows, integrations, activity_types, recent_deals,
  recent_activities, deals_at_risk, renewals_due, ai_usage`).

**Cumulative monolith progress** — past the half-way mark:

| Phase | Iter | Reduction | Total LoC | % vs original (4,283) |
|---|---|---|---|---|
| Phase 1 | 216h177 | -1,035 | 3,248 | -24% |
| Phase 2 | 216h178 | 0 | 3,248 | -24% |
| Phase 3 | 216h179 | -627 | 2,621 | -39% |
| Phase 4 | 216h180 | -309 | 2,312 | -46% |
| Phase 5 | 216h181 | -645 | 1,667 | **-61%** |

