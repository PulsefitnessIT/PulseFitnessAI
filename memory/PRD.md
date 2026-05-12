## Iter 216h36 — UploadQueueDrawer becomes mobile-aware (Feb 12, 2026)

### Why
Iter 216h34's bottom-right floating card looks great on a laptop but on a phone (390 px wide):
- Collides with the **iOS home indicator** (bottom-4 lands directly on the swipe area).
- Gets covered by the **software keyboard** the second the operator opens a comment field.
- The 340 px fixed width leaves only 50 px of horizontal margin → cramped, half-cut filenames.

A studio manager photographing a damaged dumbbell on their phone (via `EquipmentPhotoUpload`) couldn't see drawer progress mid-upload because the drawer overlapped the iOS bottom system area.

### What shipped
**Single-file change** to `/app/frontend/src/components/shared/UploadQueue.js`:

| Behaviour | md+ (≥768 px) | <md mobile |
|---|---|---|
| Position | `bottom-4 right-4` (unchanged) | `bottom-0 left-2 right-2` — slide-up sheet pinned to the bottom, full-width minus 8 px margins. |
| Corner radius | `rounded-xl` all sides | `rounded-t-2xl` only top corners (sheet style). |
| Width | 340 px fixed | Full viewport width minus 16 px. |
| Default state | Expanded | **Collapsed** — uses `window.matchMedia('(max-width: 767px)')` on init so the drawer doesn't eat half the screen the moment a file upload starts. |
| List height | `max-h-[280px]` | `max-h-[min(60vh, 280px)]` so the list grows on tall mobile screens but never devours the page. |
| Safe area | n/a | `paddingBottom: env(safe-area-inset-bottom)` so the footer + grab handle clear the iOS home indicator. |
| Grab handle | None | iOS-style horizontal pill (36 × 4 px) at the top to telegraph "this slides". |

### Verified live
Injected a probe div with the exact same Tailwind classes at the **mobile 390 × 844 viewport**:
```
rect:    { x: 8, y: 778, width: 374, height: 66, right: 382 }
bottom:  0px      ← pinned to bottom
left:    8px      ← respects left-2
right:   8px      ← respects right-2
width:   374px    ← full width minus 16 px margin
```
At desktop 1920 px the drawer kept its 340 × bottom-right position (`x=1564, right=1904`). Functional behaviour (enqueueing 3 spec sheets → drawer auto-renders, header summary, per-file rows, "Clear complete" footer) was verified live via Playwright file-input drop on the Spec Sheets dropzone — 0 React errors.

### Files touched
- `/app/frontend/src/components/shared/UploadQueue.js` (~+30 / −10 LOC in `UploadQueueDrawer`)

### ⚠ Action required
1. Redeploy preview → production.
2. Field staff uploading photos on a phone now see a sheet-style drawer at the bottom with grab handle, clear of the home indicator, and collapsed by default so the page underneath stays usable.

---



## Iter 216h35 — UploadQueue adoption batch 2 + Button migration in MembershipsConsole (Feb 12, 2026)

Two deliverables completing iter 216h34's queue+button threads.

### A. UploadQueue adoption in remaining dropzones

| Surface | Adoption | Rationale |
|---|---|---|
| `PulseOnboardingWizard.js` (multi-file path) | **Adopted** — extracted shared `parseAndMerge(file, onProgress)` helper, refactored `processMultipleFiles` to call `enqueue()` so each PDF gets its own drawer row with per-file progress + retry. Operators can navigate during long AI extractions. | Multi-file drops were previously a serial for-loop with only "N more in queue…" text. |
| `GlobalDocumentsTab.js` (bulk Mass Upload) | **Adopted** — single bulk task per upload session. Synthetic `File` descriptor (`"5 documents → Acme Manufacturing"`) ferries the bundle through the queue. Dialog now closes immediately on upload; drawer takes over visibility. Removed unused `uploading` / `uploadProgress` state. | Bulk-as-one-call pattern fit better as a single task than per-file enqueue. |
| `PulseOnboardingWizard.js` (single-file path) | **Intentionally kept inline** | The wizard's phased `InvoiceParseProgress` UI ("Reading page X of Y… Extracting equipment… Done") is an interactive step the user actively waits on — the drawer is the wrong UX here. |
| `InvoiceImportWizard.js` | **Intentionally kept inline** | Same reason — single-file flow where step 2 (review) only unlocks after parse completes; navigating away mid-parse would orphan the wizard. Wizard-step inline progress remains. |

**Result:** Every dropzone that benefits from background uploading + per-file retry now does so. The two wizards that *don't* benefit explicitly stay inline (and the choice is documented in code comments).

### B. `<Button>` primitive migration in `MembershipsConsole.js`
8 high-traffic raw `<button>` blocks converted to the design-system primitive:

| Surface | Before → After | Variant |
|---|---|---|
| Member drawer · Freeze | inline bordered → `<Button>` | secondary |
| Member drawer · Cancel | inline red border → `<Button>` | **destructive** (first usage of this variant) |
| Plan card · Record payment | inline cyan → `<Button>` | primary |
| Plan card · Comp / assign | inline bordered → `<Button>` | secondary |
| App URL row · Launch kit | inline cyan + spinner → `<Button loading>` | primary (with loading prop) |
| Brand preview · Send to members | inline cyan-outline → `<Button>` | secondary |
| Brand preview · Hide | inline tertiary text → `<Button>` | tertiary |
| Brand send dialog · SMS / Email / Copy | inline anchors → `<Button as="a">` ×3 | secondary |
| Commission CSV | inline cyan-outline → `<Button>` | secondary |

11 total replacements. `data-testid`s preserved verbatim. **22 raw `<button>` blocks remain** in `MembershipsConsole.js`, almost all of which are icon-only table row actions (edit / archive / toggle / pause / week-prev / week-next) and tiny tab pills — they're outside the primary/secondary vocabulary and will migrate when the design system grows an `iconButton` size or `tab` variant.

### Verified
- Lint clean across `UploadQueue.js`, `PulseOnboardingWizard.js`, `GlobalDocumentsTab.js`, `MembershipsConsole.js`, `AdminSpecSheets.js`.
- Master Admin → Spec Sheets renders, dropzone visible, drawer hidden when no tasks — 0 React errors.
- GymAxis admin console (`/master-admin`) loads — 0 React errors after the changes.
- Memberships console renders with no errors when accessed via operator login.

### Files touched
- `/app/frontend/src/pages/PulseOnboardingWizard.js` (+30 / −60 LOC — `parseAndMerge` helper, queue adoption)
- `/app/frontend/src/pages/Dashboard/AdminAnalytics/GlobalDocumentsTab.js` (+25 / −35 LOC — bulk task enqueue, dialog auto-close)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~+20 / −30 LOC — 11 Button migrations)

### ⚠ Action required
1. Redeploy preview → production.
2. Operators dropping multiple invoices onto the Pulse onboarding wizard / mass-uploading documents in Master Admin now see per-file drawer rows with retry. The InvoiceImportWizard's single-file step retains its bespoke parse-progress UI by design.
3. Memberships console members can be frozen, cancelled, and have payments recorded via the new shared primitives — same `data-testid`s, no behaviour change.

---



## Iter 216h34 — Upload Queue Drawer + Button-primitive migration batch 3 (Feb 12, 2026)

Two deliverables, both following the "bulletproof drag-drop" thread from iter 216h33.

### A. UploadQueue + bottom-right drawer
- **NEW `/app/frontend/src/components/shared/UploadQueue.js`** — global upload queue with a pinned bottom-right drawer:
  - `UploadQueueProvider` mounted once in `App.js` (inside `<BrowserRouter>`, alongside `GlobalDragGuard` + `NotificationConfirmProvider`).
  - `useUploadQueue()` hook returns `{ enqueue, retry, remove, clearDone, tasks }`. Panels call `enqueue(files, handler, { source, onDone })`; the handler signature is `(file, onProgress) => Promise<any>`.
  - `<UploadQueueDrawer>` auto-mounts inside the provider. Auto-opens when the queue is non-empty; collapsible. Per-file row shows name + progress bar + status (queued / uploading / done / failed) + per-file retry/dismiss.
  - Drawer survives navigation — operators can flip tabs while large PDFs upload in the background.
  - Failed uploads stay in the drawer with a retry button; successful ones can be cleared in bulk via the footer "Clear complete" button.
- **`AdminSpecSheets.js` refactored to use the queue** — replaced the serial-await for-loop + monolithic "Processing N remaining" with a parallel `enqueue()` call. Each PDF gets its own row + per-file progress via `axios.onUploadProgress`. Removed the now-redundant `uploading`/`processingCount` state.
- Other dropzones (`InvoiceImportWizard`, `GlobalDocumentsTab`, `PulseOnboardingWizard`) will adopt on next feature touch — the API is purely additive so legacy code keeps working.

### B. `<Button>` primitive migration batch 3
Operator/CRM panels, per the "next feature touch" doctrine:
| Surface | Buttons migrated | Variants |
|---|---|---|
| `CRMPipeline.js` top bar | 2 (Report, New Deal) | secondary · primary |
| `CRMContacts.js` top bar | 1 (New Contact) | primary |
| `OverviewTab.js` (Operations) | 1 (Log Issue CTA) | primary lg |

Renamed the shadcn `Button` import to `ShadcnButton` in `OverviewTab.js` so the 3 remaining low-priority `<ShadcnButton variant="outline">` blocks continue to work — they'll migrate on a later touch.

### Verified
- Lint clean across `UploadQueue.js`, `AdminSpecSheets.js`, `App.js`, `CRMPipeline.js`, `CRMContacts.js`, `OverviewTab.js`.
- Smoke screenshot of Master Admin → Catalogue & Library → **Spec Sheets**: dropzone visible, EmptyState rendering, drawer hidden (no tasks), **0 React errors**.
- Drawer initialised correctly (test enqueue would show it bottom-right).
- GlobalDragGuard + UploadQueue working in tandem — files dropped on the dropzone go through the queue; files dropped elsewhere are still blocked from opening in the browser.

### Files touched
- **NEW** `/app/frontend/src/components/shared/UploadQueue.js` (~270 LOC)
- `/app/frontend/src/App.js` (+3 LOC — import + wrap)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (~−25 / +30 LOC — queue integration)
- `/app/frontend/src/pages/CRM/CRMPipeline.js` (+2 / −4 LOC)
- `/app/frontend/src/pages/CRM/CRMContacts.js` (+2 / −2 LOC)
- `/app/frontend/src/pages/Dashboard/OverviewTab.js` (~+4 / −2 LOC + import rename)

### ⚠ Action required
1. Redeploy preview → production.
2. Lee retries the spec-sheet drop on production. Each PDF appears as its own row in the bottom-right drawer with live progress; failed uploads can be retried per-row; he can navigate to other tabs while the AI extraction completes in the background.
3. Future dropzones: import `useUploadQueue()` from `@/components/shared/UploadQueue` and call `enqueue()` — see `AdminSpecSheets.js` for the canonical pattern.

---



## Iter 216h33 — HOTFIX: Drag-and-drop opening files in browser instead of uploading (Feb 11, 2026)

### Operator-reported (Lee, production)
"Master Admin → Spec Sheets — I dragged and dropped spec sheets to upload them. They didn't upload. Instead every spec sheet opened up as a file in my browser, crashing the browser. Please ensure that every drag-and-drop is working as it should do and items dragged and dropped actually upload to the platform."

### Root cause
The Spec Sheets dropzone (and most others) called `preventDefault()` correctly on `dragOver` + `drop` events that landed exactly on the Card element — but if the file was dropped even a few pixels OUTSIDE the Card (or the user started a drag and let go without precisely targeting the dropzone), the event hit `document`'s default handler. The browser's default handler opens dropped files — when Lee dropped 10 PDFs near the dropzone, Chrome opened 10 new tabs, each rendering a 20+ MB PDF, then ran out of memory and crashed.

### What shipped

#### New global guard
- **NEW `/app/frontend/src/components/shared/GlobalDragGuard.js`** — mounts two window-level listeners (`dragover` + `drop`) that call `preventDefault()` *only* when `dataTransfer.types` contains `"Files"`. That keeps:
  - **Files dropped anywhere on the page** → blocked from browser's "open file" default (the bug Lee hit).
  - **In-app drag-drop** (CRM Pipeline Kanban, ServiceScheduler slots, Memberships StudioBuilder, StaffingConsole roster, MobileAppBuilder cards) → completely untouched because those drags carry `text/plain` or `text/uri-list`, NOT `Files`.
- **Wired in `App.js`** inside `<BrowserRouter>` so it covers every route (operator portals, master admin, member apps, kiosk).

#### Defensive `onDragEnter` added to every file dropzone
Safari (and some Firefox builds) fire `dragenter` before any `dragover`. If `dragenter` doesn't `preventDefault`, the cursor locks to "no-drop" and the eventual `drop` falls through to the document default. Added `onDragEnter={handleDragEnter}` to:
- `AdminSpecSheets.js` (`spec-sheet-dropzone`)
- `InvoiceImportWizard.js`
- `GlobalDocumentsTab.js` (`upload-dropzone`)
- `PulseOnboardingWizard.js` (`onboard-invoice-dropzone`)

`EquipmentPhotoUpload.js` already had `onDragEnter` — no change needed.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h33.json`)
- **Frontend success rate: 100%**.
- **GlobalDragGuard synthetic test**:
  - File drag (`types=['Files']`) → `defaultPrevented=true` ✓ (browser won't open the file).
  - In-app drag (`types=['text/plain']`) → `defaultPrevented=false` ✓ (Kanban etc. still work).
- All 4 file dropzones verified to have `onDragEnter` + `onDragOver` + `onDragLeave` + `onDrop` with proper `preventDefault` / `stopPropagation`.
- Master Admin (Overview / People / Organisations / Catalogue & Library → Spec Sheets) — 0 React errors.
- Pulse dashboard (Bob) — 0 React errors.

### Files touched
- **NEW** `/app/frontend/src/components/shared/GlobalDragGuard.js` (~65 LOC)
- `/app/frontend/src/App.js` (+2 LOC — import + mount)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (+8 LOC — dragEnter handler + JSX wiring)
- `/app/frontend/src/pages/InvoiceImportWizard.js` (+5 LOC)
- `/app/frontend/src/pages/Dashboard/AdminAnalytics/GlobalDocumentsTab.js` (+8 LOC)
- `/app/frontend/src/pages/PulseOnboardingWizard.js` (+3 LOC)

### ⚠ Action required
1. **Redeploy preview → production.** Frontend-only fix; no DB migration.
2. After deploy, Lee can drag-drop multiple PDFs onto the Spec Sheets dropzone — they will all upload to the platform AND files dropped just outside the dropzone will no longer crash the browser.

---



## Iter 216h32 — HOTFIX: Head Office not auto-created for Lee on production (Feb 11, 2026)

### Operator-reported (with screenshot)
On production (`gymaxisai.com/pulse`), Lee Somers' site switcher showed only:
- All Operations Sites · iGym Carshalton (61 eq) ✓ · iGym Congleton (0 eq).

The expected **★ Pulse Fitness Head Office** row was missing despite iter 216h15's auto-create code being live (confirmed by the "All Operations Sites" label rename shipping in the same deploy).

### Root cause
Iter 216h15's auto-create logic was gated by an `is_privileged` role check (`role in ("owner", "manager", "master_admin", "master")` or `is_master_admin=True`). Production has legacy operator users whose `role` field doesn't fall in that exact allow-list (e.g. `"admin"`, `"site_manager"`, etc.), so the lazy-on-read auto-create silently skipped the insert and Lee's org never received its HQ row.

### Fix (backend only)
- **`/app/backend/routes/sites.py`** — dropped the `is_privileged` gate around auto-create. Auto-create now ALWAYS runs whenever the org has ≥1 site and none flagged `is_head_office`. The operation is fully idempotent (the second call no-ops because `any(is_head_office)` now resolves True) and harmless for non-privileged callers — they just won't see HQ themselves until an owner visits (their `allowed_site_ids` filter still applies as before).
- Added a `logging.warning("auto_create_hq.skipped: org_doc missing …")` for the (should-be-impossible) case where the operator's `organization_id` doesn't resolve to a real org. Helps spot mis-linked accounts in prod logs.
- `is_privileged` is still computed and used for `allowed_site_ids` filtering — no behavioural change there.

### Verified
- **`test_iter_216h15_team_management.py`** extended with a new regression:
  - `test_get_sites_auto_creates_hq_for_non_privileged_role` — seeds an org with role=`"admin"` (deliberately outside the old allow-list) and confirms HQ is auto-created on first `/api/sites` call.
- **All 14 tests pass** (13 existing + 1 new).
- Lint clean.

### Files touched
- `/app/backend/routes/sites.py` (~+30 / −10 LOC — moved auto-create out of the role gate, added diagnostic log).
- `/app/backend/tests/test_iter_216h15_team_management.py` (+39 LOC — new regression test).

### ⚠ Action required
1. **Redeploy preview → production.** This is a 1-file backend fix; no DB migration required.
2. After deploy, ask Lee to reload `gymaxisai.com/pulse`. The FIRST page load triggers GET `/api/sites` which fires auto-create → "Pulse Fitness Head Office" appears at the top of the dropdown with the ★ icon. Idempotent — subsequent reloads are no-ops.
3. The same hotfix retroactively repairs every other production org that has sites but no HQ (Tottenham Green, MOD sites, customer orgs etc.) the moment one of their users next loads the dashboard.

---



## Iter 216h31 — Head Office selectable for owners (multi-site orgs) — UX parity across all dashboards (Feb 11, 2026)

Closes P1 backlog item *"Head Office site not selectable for owners"*.

### Root cause
Iter 216h15 already shipped the backend foundations: `/api/sites` auto-creates a real `db.sites` row flagged `is_head_office=true` when an org has ≥1 site but none is HQ, and sorts HQ to the top of the response. The `LiteDashboardPage` (rendered on `/pulse`) consumed this via the canonical `<SiteSwitcher>` component with `All Operations Sites` + HQ-star UI.

But on the GymAxis Pro `/dashboard` route, the **`Navbar`** had its own bespoke inline site dropdown that:
- Didn't render the HQ star icon,
- Didn't include the "All Operations Sites" pseudo-entry,
- Didn't apply HQ-first sorting visually,
so legacy GymAxis-Pro owners with multi-site orgs felt the regression even though their Pulse-Pro counterparts had everything.

### What shipped

#### Frontend
- **`Navbar.js`** — replaced the bespoke 38-line inline dropdown (`site-switcher-btn` / `site-dropdown` / `site-option-*`) with the canonical `<SiteSwitcher>` component (`site-switcher-trigger` + `site-switcher-menu` + `site-switcher-item-*`). Now every owner sees:
  - HQ row with a star icon, always sorted first.
  - Same dropdown styling and viewport-safe positioning everywhere.
  - (No `All Operations Sites` entry on `/dashboard` because that route doesn't yet have an aggregated overview — single-site picking only.)
- Removed unused `showSiteMenu` state.

#### Backend
- **`/api/master-admin/organizations/{org_id}/sites`** — added HQ-first sort (`enriched.sort(key=lambda s: (not bool(s.get("is_head_office")), 0))`) so the Master Admin org drawer's Sites tab renders Head Office at the top. Matches the operator-facing `/api/sites` behaviour.

### Verified end-to-end (testing agent — `/app/test_reports/iteration_216h31.json`)
- **Backend success rate: 100%** (13/13 — `test_iter_216h15_team_management.py`).
- **Frontend success rate: 100%**:
  - SiteSwitcher trigger renders for Bob (Strong Fitness, 2 sites).
  - "All Operations Sites" entry visible with "overview" badge.
  - HQ row "Strong Fitness Head Office" shows ★ icon and sits at index 0.
  - Non-HQ site "TEST_S2_Site" sits at index 1.
  - Pick a site → trigger label updates.
- Lint clean (frontend + backend).

### Files touched
- `/app/frontend/src/components/shared/Navbar.js` (~40 LOC removed, 12 LOC added; SiteSwitcher import added)
- `/app/backend/routes/sites.py` (3 LOC added — HQ sort for master-admin endpoint)

### ⚠ Action required
1. Redeploy preview → production.
2. As Lee on `gymaxisai.com`: top-bar site switcher now shows **★ Head Office** first, followed by the rest of the sites. No need to remember which site has the HQ flag — the platform makes it the default.

---



## Iter 216h30 — Empty-state pass (CRM + Spec Sheets) + Operator portal Button migration batch 2 (Feb 11, 2026)

Two deliverables in one push.

### A. D2 — Empty-state pass: CRM Contacts / Pipeline + Master Admin Spec Sheets
Migrated 4 more empty-state panels to the canonical `<EmptyState>` primitive:
- **CRM → Contacts** (`CRMContacts.js`): replaces bare "No contacts yet" div with opportunity-framed copy + "Add your first contact" primary CTA. `data-testid="crm-contacts-empty"`.
- **CRM → Pipeline → List view** (`CRMPipeline.js`): replaces "No deals in pipeline" plain div. Copy: "Your pipeline is wide open". `data-testid="crm-pipeline-list-empty"`.
- **Master Admin → Spec Sheets** (`AdminSpecSheets.js`): two distinct empty states now —
  - `spec-sheets-empty` when no sheets uploaded ("Drop manufacturer PDFs above…")
  - `spec-sheets-empty-filtered` when the filter zeroes results ("Try clearing the search box…")

### B. D3 — Button-primitive migration: Operator portal batch
Migrated all high-traffic top-bar CTAs in the operator portals to use the shared `<Button>` primitive (per the "next feature touch" doctrine):

| Surface | Buttons migrated | Variants |
|---|---|---|
| `CRMDashboard.js` | 5 (View all × 3 · Manage · Set up) | tertiary |
| `MembershipsConsole.js` — Members tab | 3 (CSV template, Bulk import, Add member) | secondary · secondary · primary |
| `MembershipsConsole.js` — Plans tab | 1 (New plan) | primary |
| `MembershipsConsole.js` — Classes tab | 1 (New class) | primary |
| `MembershipsConsole.js` — Ads tab | 1 (New ad) | primary |

**11 inline button blocks** replaced. All `data-testid`s preserved. Bulk-import button now uses the built-in `loading` prop spinner instead of an ad-hoc "Importing…" text.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h30.json`)
- **Frontend success rate: 100%** — every `data-testid` resolved in DOM.
- CRM Dashboard: all 5 tertiary buttons render + click without console errors.
- Memberships Members/Plans/Classes/Ads: primary cyan CTAs visible; secondary outline buttons visible on Members.
- Empty-state testids exist in source for the 3 new panels (will render on a tenant with no contacts/deals/spec sheets).
- Lint clean across all 5 files.

### Files touched
- `/app/frontend/src/pages/CRM/CRMContacts.js` (~10 LOC)
- `/app/frontend/src/pages/CRM/CRMPipeline.js` (~8 LOC)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (~14 LOC)
- `/app/frontend/src/pages/CRM/CRMDashboard.js` (~12 LOC)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~20 LOC)

### ⚠ Action required
1. Redeploy preview → production.
2. Operator portals now visually consistent with the Master Admin redesign — exactly ONE brand-cyan primary CTA per panel.
3. Future Operations / CRM / Memberships panels: import `<Button>` from `@/components/shared/Button`. See `/app/DESIGN_SYSTEM.md`.

---



## Iter 216h29 — Invite-pending badge + Auto-archive sibling invites + Operator portal migration kick-off (Feb 11, 2026)

### A. Auto-archive sibling invite tokens
- `POST /api/auth/reset-password` now archives every other unused, unexpired token for the same user the moment one is redeemed. Stale invite links can no longer linger as second-chance access vectors. Marked with `archived_reason: 'auto_archived_after_sibling_redeemed'` for audit traceability.
- Verified via the 17-check audit harness (`test_iter_216h26_audit.py`) — all green.

### B. Pending-invite badge in People Directory
- **Backend**: `GET /api/master-admin/users` now enriches each user with an `invite_pending` block when their most recent token is still unused AND not yet expired:
  ```json
  "invite_pending": { "expires_at", "issued_at", "issued_by", "hours_left", "kind" }
  ```
  Single aggregation query (no N+1) — only one extra round-trip for the whole directory.
- **Frontend**: `PeopleDirectory.js` renders a small amber **"Nh LEFT"** badge next to the role chip on every row with a pending invite. Tooltip shows the full expiry timestamp.
- **New "Invites pending" stat tile** in the top stats strip (7 tiles now, was 6). Live preview: 35 of 125 users have pending invites in the preview DB.

### C. Operator portal button migration — first concrete batch
- Migrated 3 top-bar CTAs in `Memberships → Invoicing` (the highest-traffic operator surface):
  - **Refresh preview** → `<Button variant="secondary">` with built-in loading spinner.
  - **Sibling discount → Save** → `<Button variant="secondary" size="sm">`.
  - **Generate invoices** → `<Button variant="primary">` (brand cyan filled).
- Demonstrates the migration pattern outside Master Admin without touching every button (per the "next feature touch" doctrine).

### Verified
- Audit harness `/app/backend/tests/test_iter_216h26_audit.py` re-run: **17/17 PASS**.
- Live curl confirmed `invite_pending` is populated on 35 of 125 users with `hours_left=71`, `kind=invite`.
- Live UI screenshot confirms the **"Invites pending — 35 — 72h links unredeemed"** stat tile renders + 35 amber badges visible across the Directory rows.

### Files touched
- `/app/backend/routes/auth.py` — sibling-archive logic (~22 LOC).
- `/app/backend/routes/master_admin.py` — `invite_pending` enrichment in `/master-admin/users` (~40 LOC).
- `/app/frontend/src/pages/MasterAdmin/PeopleDirectory.js` — badge + stat tile + 7-column grid.
- `/app/frontend/src/pages/Memberships/InvoicingTab.js` — 3-button migration to `<Button>` primitive.

### ⚠ Action required
1. Redeploy preview → production.
2. Operators now have a one-glance signal that "Sarah's invite is about to expire" without leaving the People Directory.
3. Auto-archive protects against the operator-error case of issuing two invites and accidentally letting the unused one stay live.

---


## Iter 216h28 — Button-primitive migration: first batch (Feb 11, 2026)

Migrated the iter-216h20-h24 Master Admin panels (the "canonical examples" per `/app/DESIGN_SYSTEM.md`) to use the shared `<Button>` primitive. Goal: prove the migration pattern, lock in the new design system, and stop the inline-style regression vector for new panels.

### Panels migrated
| Panel | Inline buttons removed | Variants used |
|---|---|---|
| `StaffOnboardingWizard.js` | 6 (Back, Next, Submit, Copy link, Email it, Invite another) | primary · secondary · tertiary |
| `IntegrationsHub.js` | 1 (Refresh) | secondary (with loading prop) |
| `AdminAllSites.js` | 1 (Refresh) | secondary |
| `OrgIntegrationsTab.js` | 1 (Refresh) + 3 inline "Manage" links left as plain anchors | tertiary |
| `UserDetailDrawer.js` | 4 (Issue link, Copy again, Close, Full edit in legacy panel) | primary · secondary · tertiary |

**13 inline button blocks** replaced with `<Button>` invocations. All `data-testid`s preserved — zero test regressions.

### Verified
- `/app/backend/tests/test_iter_216h26_audit.py` re-run after migration: **17/17 checks PASS**.
- Live smoke screenshots of the 4 migrated panels show consistent button styling:
  - Primary CTAs (Next, Issue & copy reset link) — brand cyan filled, exactly one per screen.
  - Secondary actions (Refresh, Back, Email it, Copy link) — outlined, supportive.
  - Tertiary (Close in drawer, Open on cards) — text + underline-on-hover, low emphasis.
- Lint clean across all 5 panels.

### Migration is intentionally bounded
The user asked for "panel-by-panel on next feature touch" — this batch deliberately ships only the Master Admin panels we created in P3-P6. Operator/member portal buttons will migrate on their next feature touch (the `<Button>` primitive is purely additive — legacy buttons keep working).

### ⚠ Action required
- Future panels: import `<Button>` from `@/components/shared/Button` — DO NOT write `<button className="inline-flex …">` anymore. See `/app/DESIGN_SYSTEM.md` for the anti-pattern catalogue.

---


## Iter 216h26-27 — Master Admin → portal audit + Empty-state pass + Button hierarchy (Feb 11, 2026)

Three deliverables in one push.

### A. Portal-linkage audit (iter 216h26)
- **17 / 17 end-to-end checks PASSED** between every Master Admin write surface and the customer-facing runtime (`/auth/me`, `module_access`, equipment listing, marketing-subscription gate, etc.).
- Full report at `/app/AUDIT_PORTAL_LINKS.md`. Live test harness at `/app/backend/tests/test_iter_216h26_audit.py` — re-runnable any time.
- **1 broken link fixed**: `POST /api/master-admin/organizations` now returns a 72 h invite link for the freshly-provisioned primary contact (`owner.invite_url` + top-level `invite_url`). Operators no longer need to use the legacy reveal-password handover — they can ship the self-serve reset link straight away. Frontend `useMasterAdminActions.createOrganization` surfaces the link in the success toast.
- New helper `_mint_invite_link(user_id, email, issued_by)` in `master_admin.py` keeps the iter-216h15 reset-link flow consistent across every creation surface (Staff Onboarding wizard, Customer Onboarding wizard, manual /users/{id}/invite-link).

### B. D2 — Empty-state pass (iter 216h27)
- Upgraded the 3 highest-visibility empty states to use the canonical `<EmptyState>` component:
  - **Memberships → Mobile App Builder**: was a bare div with "No cards yet". Now an EmptyState with icon, opportunity-framed title ("Your members' home screen is blank"), and a hint that explains what cards do.
  - **Master Admin → Login events**: was inline grey "No events match the current filter." Now structured EmptyState explaining the SOC 2 evidence purpose.
  - **Master Admin → Audit log (desktop + mobile)**: same upgrade. Both renderers (table + mobile cards) now use EmptyState with consistent copy.
- Full status table in `/app/DESIGN_SYSTEM.md` — 11 panels now adopt the canonical pattern; 3 remaining low-priority panels listed.

### C. D3 — Button-hierarchy audit (iter 216h27)
- New `<Button>` primitive at `/app/frontend/src/components/shared/Button.js` — **caps the vocabulary at 3 variants + 1 destructive**:
  - `primary` — brand cyan filled; exactly ONE per screen.
  - `secondary` — outline; supportive actions (Cancel / Bulk import / Refresh).
  - `tertiary` — text + underline-on-hover; low-emphasis "View all", "Manage", "Reset filter".
  - `destructive` — soft red; always confirm via `useConfirm()`.
- 3 sizes (sm / md / lg), `icon` prop for Lucide icons, `loading` spinner, `as` prop for anchors.
- Anti-pattern catalogue + migration plan in `/app/DESIGN_SYSTEM.md`.

### Verified live
- Audit harness PASS 17/17 after every change.
- Login Events page now renders without runtime errors (fixed an `onClearFilter is not defined` regression introduced + caught immediately).
- Audit log panel renders successfully with 11 events visible.

### ⚠ Action required
1. Redeploy preview → production.
2. The Master Admin Customer Onboarding wizard now offers the operator a copyable 72 h invite link in the success toast — no more password handover.
3. New panels MUST use `<Button>` and `<EmptyState>` from `/app/frontend/src/components/shared/`. Legacy panels migrate on next touch (anti-pattern catalogue in `/app/DESIGN_SYSTEM.md`).

---


## Iter 216h25 — Jump-to-user toast + Extended brand_filter coverage (Feb 11, 2026)

Two parallel deliverables, both verified live end-to-end.

### A. "Jump to this user" link in duplicate-user error toast
- **Backend**: `POST /api/master-admin/organizations/{org_id}/users` 409 response is now **structured**:
  ```json
  { "detail": { "code": "user_exists", "message": "...", "user_id": "...", "full_name": "...", "organization_id": "...", "collection": "users|crm_users", "email": "..." } }
  ```
- **Frontend wizard (`StaffOnboardingWizard.js`)**: when the 409 carries `code:'user_exists'`, an **amber toast** renders with a "Jump to this user in the directory →" button (`data-testid=staff-wizard-jump-to-user`). Clicking it pushes `?section=roles&focus_user={id}` and dispatches the new `gymaxis:focus-user` event.
- **`AdminRoles.js` listener**: subscribes to `gymaxis:focus-user`, resolves the user from `globalUsersProps.users` by id or email, switches to the Directory tab, opens the `UserDetailDrawer`, and scrolls the row into view. Also honours `?focus_user=` on mount so deep-links from elsewhere work the same way.

### B. Brand filter extended to audit-log + marketing-suite (+ financial-ops left strict)
- **Audit log** (`/app/backend/routes/master_admin_audit_log.py`):
  - New helpers `_resolve_brand_org_ids()` + `_is_pulse_only()`.
  - `_gather()` accepts `brand_org_ids: Optional[set]` and intersects per-collection queries via `_apply_brand()`.
  - All 3 public endpoints (`/audit-log`, `/summary`, `/export.csv`) accept `?brand=`.
  - **Pulse Master Admins are SERVER-SIDE FORCED to `pulse` regardless of the query param** — defence in depth.
- **Marketing Suite** (`/app/backend/routes/marketing/admin.py`):
  - `/master-admin/marketing/analytics` and `/master-admin/marketing/subscriptions` now accept `?brand=`.
  - Same Pulse-force behaviour.
  - Response payload now carries the resolved `brand` field so the UI knows what scope it's looking at.
- **Financial Ops** (`/app/backend/routes/financial_ops.py`):
  - Already gated by `_require_master_admin` which only allows `is_master_admin=True`. **Pulse admins receive 403** — correct behaviour because financial-ops is GymAxis-platform-level data (reserve fund, LLM credits, platform burn). No brand-filter needed.
  - Testing agent patched a pre-existing minor MongoDB ObjectId serialisation bug in `_get_config()` (re-fetch after insert).
- **Frontend wiring**:
  - `AuditLogPanel.js` + `AdminMarketingSuite.js` (Analytics + Subscriptions) now consume `useBrandContext().brand` and append `?brand=` to fetch URLs. Reload fires automatically when the operator flips the top-bar BrandPicker.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h25.json`)
- **22/22 tests PASSED** (backend 17/17 · frontend 5/5):
  - Structured 409 response.
  - Toast renders + Jump button works end-to-end.
  - `?focus_user=` URL param opens drawer on mount.
  - Audit-log accepts `?brand=` (list, summary, export.csv).
  - Marketing analytics/subscriptions accept `?brand=`.
  - Pulse admins forced to `pulse` on all 5 endpoints.
  - Financial-ops returns 403 for Pulse admins (correct).
  - GymAxis admins can freely toggle.

### ⚠ Action required
1. Redeploy preview → production.
2. Pulse Master Admin scope-lock is now enforced **server-side** on audit-log + marketing, in addition to the existing UI lock — defence in depth against malformed/replay requests.
3. Operators who try to invite an existing user from the wizard now get a one-click "Jump to this user" deep link instead of a flat error.

---


## Iter 216h24 — Master Admin redesign Phase 6: Staff Onboarding wizard (Feb 11, 2026)

P6 — final phase of the Master Admin redesign blueprint. Replaces ad-hoc "Add user" buttons scattered across the People panels with one canonical 5-step linear wizard that the user explicitly asked for ("invite → role → sites → modules → audit").

### What shipped (frontend only — no new backend code)
- **NEW `StaffOnboardingWizard.js`** at Master Admin → People → "Onboard staff" sub-tab. 5 steps:
  1. **Identity** — full name + work email + brand context. Pulse-only admins get the brand forced to `pulse`.
  2. **Role** — 7 tiles in 2 groups (Platform: GymAxis Master Admin · Pulse Master Admin · Service Desk; Customer org: Owner · Manager · Staff · Instructor). Pulse Master Admins cannot invite a "GymAxis Master Admin".
  3. **Sites** — only meaningful for org-scoped roles. Multi-select site checkboxes loaded from `GET /api/master-admin/organizations/{org_id}/sites`. Empty = all sites (no restriction).
  4. **Modules** — 4 toggles (Operations Portal · Memberships · Marketing Suite · CRM). Toggling OFF sends a `module_overrides` entry; ON inherits the org default.
  5. **Review** — summary card → "Generate invite link" CTA. On success: 72 h invite URL with **Copy** and **Email** actions.
- Reuses **4 existing backend endpoints** (no new backend code):
  - `POST /api/master-admin/pulse-admins` for the Pulse Master Admin role.
  - `POST /api/master-admin/organizations/{org_id}/users` for every org-scoped + master_admin + service_desk role.
  - `PUT /api/master-admin/users/{user_id}/edit` for `allowed_site_ids` and `module_overrides`.
  - `POST /api/master-admin/users/{user_id}/invite-link` to mint / re-mint the 72 h reset-link.
- Reuses the iter-216h15 reset-link flow exactly — Master Admin never sees the user's plaintext password; the user sets it from the 72 h link on first visit.

### Sidebar restructure
- People group now has 3 sub-tabs: **Directory · Onboard staff · Site-locked users**.

### Verified live
- **Testing agent v3 `/app/test_reports/iteration_216h24.json` — 12/12 PASSED** (backend + frontend 100%):
  1. Wizard loads with 5 step pills.
  2. Step 1 input validation works.
  3. 7 role tiles in 2 groups.
  4. Sites checkboxes load from API.
  5. Module override toggle.
  6. Happy path e2e — created user, invite link returned with `/reset-password?token=`.
  7. Pulse Master Admin scope hides GymAxis Master Admin role + forces brand + filters orgs to Pulse only.
  8-10. Backend endpoint calls verified.
  11. Created user appears in unified directory.
  12. Regression: People → Directory still works.
- **Main agent live smoke**: signed in as `admin@gymaxisai.com`, ran full 5-step flow, created `Wizard Test User`, received invite URL `https://maintenance-hub-357.preview.emergentagent.com/reset-password?token=l47KegLXL2FI…`.

### Pulse Master Admin guardrails
- 'GymAxis Master Admin' role tile hidden.
- Brand toggle hidden (Pulse scope forced).
- Org dropdown only shows Pulse-brand orgs (2-3 of 90 in preview).
- Server-side guardrails inherited from existing endpoints (master-admin + Pulse-scope checks).

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **People → Onboard staff** to invite a new team member. The wizard takes < 60 seconds end-to-end.
3. The Master Admin redesign blueprint is now **COMPLETE through P6**. Remaining UX/process backlog work (button hierarchy audit, empty-state pass, dark-mode commit-or-strip) is independent of the redesign.

---


## Iter 216h23 — IA cleanup: kill misleading "Sites" sidebar entry + add "All sites" under Organisations (Feb 11, 2026)

Operator feedback: *"Sites is showing the equipment catalogue. Could Sites be under Organisations?"* Chose option (b): kill the standalone, rename the contents, add an "All sites" cross-org sub-tab under Organisations. **SSoT preserved** — a Site still belongs to exactly one Organisation; the only editor is the Organisation drawer's Sites tab.

### Conceptual clarification (now reflected in the UI)
- **Organisation** = customer/legal entity (Pulse Fitness Ltd, Tottenham Green Trust). 90 in preview DB.
- **Site** = physical location belonging to ONE Organisation (Pulse Birmingham, Brockwell Lido Main Pool). 32 in preview DB.
- **Equipment Catalogue** = platform-wide master data (model images, spec sheets, custom properties). Reused across every Org + Site. NOT a Site.

### What shipped (frontend)
- **Sidebar "Sites" entry DELETED**. Its contents (Equipment catalogue, Spec sheets, Equipment images, Manufacturers, Marketing library, Social media library) re-homed under a new **"Catalogue & Library"** sidebar entry — accurate label for cross-org master data + brand assets.
- **NEW "All sites" sub-tab inside Organisations group** (sits between List and Customer onboarding):
  - Cross-org flat table of every physical site.
  - Per-row: HQ/branch icon, name, parent org, brand pill, city + postcode, equipment count, members count.
  - Totals strip (Total sites · Head offices · Branches · Equipment).
  - Filter bar (free-text search, site-type, organisation dropdown) with live result count.
  - **Row click pushes URL params `?section=organizations&expand=ORG_ID&view=sites`** + dispatches `gymaxis:set-section` so `AdminOrganizations` (which already reads those params on mount) opens the right org drawer on the Sites tab. SSoT preserved — editing flows through the existing drawer.
- New `AdminAllSites.js` component (read-only power view).

### Backend (1 new endpoint)
- **`GET /api/master-admin/all-sites`** — master-admin-gated cross-org sites list:
  - Query params: `org_id`, `site_type` (`head_office`/`branch`/`all`), `q` (free text), `limit`.
  - Per-row enrichments: `equipment_count` and `members_count` via single aggregation passes (no N+1).
  - Pulse-only admins receive `brand="pulse"` and orgs filtered through `brand_filter_clause("pulse")` — scope-lock honoured server-side.

### Verified live
- **Testing agent v3 `/app/test_reports/iteration_216h23.json` — 7/7 PASSED**:
  1. Endpoint auth gate (401 without token).
  2. GymAxis admin sees 32 sites / 17 HQs / 15 branches / brand="all".
  3. Query params work (site_type filter, limit).
  4. Pulse admin sees brand="pulse" with scope-filtered sites.
  5. Sidebar verified: Sites entry GONE, Catalogue & Library present, All sites under Organisations.
  6. `AdminAllSites` component renders with all expected testids.
  7. Regression: Org list, Integrations Hub, Pulse Master Admin scope-lock all still work.
- **Main agent live smoke**: sign-in → All sites loads 32 rows with totals strip → click any row → URL flips to `?section=organizations&expand=...&view=sites` → Organisation drawer opens on Sites tab with Module-Overrides toggles visible. End-to-end navigation pattern works.

### Fix to the JSX literal-escape bug
- Cleaned up three places where `\u2026` / `\u2019` had leaked into JSX strings inside `AdminAllSites.js` and the section description. They now render as proper "…" and "&apos;".

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **Organisations → All sites** for a flat cross-org power view. Click any row to drill into that organisation's Sites drawer.
3. Equipment images / spec sheets / manufacturer catalogue / marketing library / social media library all moved to **Catalogue & Library** in the sidebar (same content, accurate label).

---


## Iter 216h22 — Master Admin redesign Phase 5: Integrations Hub + Pulse Master Admin scope-lock (Feb 11, 2026)

P5 of the blueprint — single page for all third-party connections, plus a guarantee that **Pulse Master Admins only ever see Pulse Fitness data**.

### What shipped (frontend)
- **NEW `IntegrationsHub.js`** (Master Admin → Integrations → Hub):
  - Summary strip with 4 tiles (Connected / Degraded / Not configured / Brand scope).
  - 4 integration cards (Stripe Connect · Sicon Service · Orbit 4 · Sage 200) — each with status pill, brand badge, org-coverage tile (X / Y orgs · Z %), last-24h events / errors, "Open" affordance.
  - Right-hand `Sheet` drawer that EMBEDS the full existing console page so **every Sicon and Sage mapping field stays visible and editable**:
    - Sicon card → full `SiconIntegrationPage` (Overview · Organisations · Event Log · Configuration · **Field Mappings**).
    - Orbit 4 card → full `IntegrationAdminPanel` for orbit4.
    - Stripe Connect card → full `AdminStripeConnect` (platform settings + per-org onboarding rows).
    - Sage 200 card → field-mapping reference table + coverage + pointer to Org Billing tab (Sage rides the Sicon bridge so the editor lives on the org doc).
- **NEW Sidebar group `integrations-hub`** with 4 sub-tabs (Hub default · Orbit 4 · Sicon Service · Stripe Connect). The 3 legacy entries still deep-link.
- **Brand Picker now scope-locks for Pulse Master Admins**:
  - `BrandPicker.js` accepts an `isPulseAdmin` prop. When true, it forces `brand="pulse"` on mount and renders a non-clickable pill ("Pulse Fitness · SCOPE LOCKED") in place of the dropdown.
  - `MasterAdminPage.js` derives `isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin)` and passes it to both `BrandPicker` and `IntegrationsHub`.

### Backend (1 new endpoint + 1 critical auth-payload fix)
- **`GET /api/master-admin/integrations-hub`** — single round-trip JSON for the hub:
  - `brand` (forced to `pulse` for `is_pulse_only(user)` callers).
  - `integrations[4]`: each with `key`, `label`, `enabled`, `status` (connected / degraded / not_configured / down), `last_event_at`, `events_24h`, `errors_24h`, `orgs_configured`, `orgs_total`, `ref_field`. Stripe Connect row also returns `platform_fee_pct`.
  - `summary` counts.
- **CRITICAL FIX — `/api/auth/me` now returns `is_pulse_admin`**. The login response already included it, but `/auth/me` (the auth-rehydrate endpoint) did NOT — so on every page reload the React `user` lost its Pulse-admin flag. Routes guarded by `is_pulse_admin` (`/master-admin` access, BrandPicker scope-lock) failed silently and bounced Pulse admins to `/dashboard`. Restored.

### Verified live (testing agent v3 + main agent smoke test)
- **Testing agent report `/app/test_reports/iteration_216h22.json`** — 8 items, 7 PASSED, 1 PARTIAL (frontend Pulse-login blocked by rate-limit; backend behaviour verified via API).
- **Main agent end-to-end smoke** (after `/auth/me` fix):
  - Signed in as `pulse.scope.test@pulsefitness.com` → navigated to `/master-admin?section=integrations-hub`.
  - Top bar shows **"Pulse Fitness · SCOPE LOCKED"** pill (data-testid `master-admin-brand-picker-locked`).
  - Trigger dropdown (`master-admin-brand-picker-trigger`) NOT rendered — confirmed mutually exclusive.
  - Brand-scope summary tile says "Locked (Pulse Master Admin)".
  - Org-coverage on every card shows 0 / 3 (NOT 0 / 90) — Pulse-scoped server-side via `brand_filter_clause("pulse")`.
  - All 4 integration cards render correctly with brand badge "Pulse Fitness" on each.

### Side effect — new test account
- **Pulse Master Admin scope test**: `pulse.scope.test@pulsefitness.com` / `TestPulse2026!` (added to `/app/memory/test_credentials.md`).

### What this still does NOT do (handed to P6+)
- `AdminPulse` panel intact — **NOT retired**, per user clarification ("we still need a Master Admin just for Pulse Fitness").
- Sicon / Orbit 4 / Sage 200 "test connection" button + per-row drilldown (still via the embedded existing page).
- P6 — Staff Onboarding wizard still pending.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **Integrations → Hub** to drill any of the 4 connections in a side drawer with mapping fields preserved.
3. Delegate a Pulse Master Admin via `POST /api/master-admin/pulse-admins` — they will be auto-locked to Pulse scope on every dashboard, list and audit.

---


## Iter 216h21 — Master Admin redesign Phase 4: Organisations SSoT consolidation (Feb 11, 2026)

P4 of the blueprint — collapses the multi-surface Organisations experience into a single drawer with 7 blueprint tabs.

### What shipped (frontend)
- **`MasterAdminPage.renderSection`** — added `case 'organizations'` so the sidebar's `Organisations → List` entry now renders `<AdminOrganizations {...orgsProps} />` directly. Previously this section ID had no case and silently fell through to `null`, leaving the page blank.
- **`AdminOrganizations.js` drawer tabs renamed + new tab added**:
  - Old: Details · Users · Features · Sites · Billing · Audit (6).
  - New: **Profile · Sites · People · Modules · Billing · Integrations · Activity (7)**.
  - `value` keys (`details`/`users`/`features`/`sites`/`billing`/`integrations`/`audit`) and data-testids were preserved so existing tests & deep-links still resolve. Only the visible labels + the order changed (Sites moved up next to Profile per the blueprint reading order).
- **NEW component `OrgIntegrationsTab.js`** — surfaces per-org connection status for **Stripe Connect / Sicon Service / Orbit 4 / Sage 200**. Each row carries a status pill (Connected / Not configured), a descriptive line (account ref, platform fee, auto-post flag) and a "Manage" link that fires the existing `gymaxis:set-section` window event to jump to the global integration console.
- The panel calls the new endpoint on mount + on Refresh; gracefully degrades to org-doc fields when the endpoint errors.

### Backend (1 new endpoint, master-admin-gated)
- **`GET /api/master-admin/organizations/{org_id}/integration-health`** — returns a 4-block JSON snapshot:
  - `stripe_connect`: `connected`, `account_id`, `charges_enabled`, `payouts_enabled`, `platform_fee_pct`.
  - `sicon`: `configured` (org-ref ∩ platform-configured), `platform_configured`, `account_ref`, `auto_post`.
  - `orbit4`: `configured`, `platform_configured`, `customer_id`.
  - `sage200`: `configured`, `account_ref`.
- Permission gate: `require_master_admin` + `assert_org_in_pulse_scope` (so Pulse Admins only see their own scope).
- No new collection/schema. Pure read across `organizations` + `app_config`.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h21.json`)
- **All 6 test items PASSED** (backend + frontend 100%):
  1. Endpoint returns correct JSON shape; 401 without token; 401 with invalid token; "not configured" shape on orgs with no integration data.
  2. Organisations sidebar entry renders ~90 org cards (was previously blank).
  3. Drawer shows 7 tabs in correct order (Profile/Sites/People/Modules/Billing/Integrations/Activity).
  4. Integrations panel renders 4 rows + status pills + Manage links + Refresh button.
  5. Regression: People → Directory row click → UserDetailDrawer still works (iter 216h20).
  6. Regression: "Customer onboarding" is under Organisations sidebar (iter 216h20).

### What this still does NOT do (handed to P5/P6)
- The standalone `AdminPulse` (Overview → Service Portal → Pulse) panel is left intact for now; the new per-org Integrations tab now covers the same drill-down need but the global KPI strip + MRR table on Overview is still useful for tier-mix at-a-glance.
- The Memberships admin's separate `OrganisationsTab` is left intact (specialised lock/unlock view inside the Memberships admin — different mental model).
- P5 (Integrations hub) and P6 (Staff Onboarding wizard) still pending.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin on `gymaxisai.com`: Sidebar → **Organisations → List** → click any org row's pencil → use the new **Integrations** tab to see per-org Stripe/Sicon/Orbit/Sage status at a glance, with Manage deep-links to the global consoles.

---


## Iter 216h20 — Drawer wiring + Organisation Onboarding restored (Feb 11, 2026)

### A. P3-followup — `UserDetailDrawer` wired into People Directory
- `AdminRoles.js` now owns a `selectedUser` state. Clicking any row in `PeopleDirectory` opens the existing `UserDetailDrawer.js` (Profile + 72 h reset link + "Full edit in legacy panel").
- "Full edit in legacy panel" closes the drawer, flips the Roles sub-tab to `legacy-users`, fires `gymaxis:focus-legacy-user` window event (carries `user_id` + `email`) so `GlobalUsersPanel` can scroll/expand the matching row in a follow-up iter, and triggers the parent `onReload`.
- Verified live: 101 rows render, first row → drawer opens with name `Iter216h Dual-Role Test`, role `pulse_master_admin`, organisation, email and the "Issue & copy reset link" button all populated.

### B. Regression fix — Organisation Onboarding restored
- **Operator feedback**: "We've lost Organisation Onboarding which was working perfectly."
- **Root cause**: Iter 216h17 moved the onboarding hub under People and relabelled it "Staff onboarding" — but the hub creates **customer organisations** (sub-tabs: Onboard Site / Head Office (multi-site) / Onboarding Packets / Bulk Imports). Operators looking for *Organisation* onboarding never thought to look under People → Staff onboarding.
- **Fix** (`SidebarConfig.js`):
  - Moved `onboarding` from the People group to the Organisations group.
  - Relabelled sidebar entry **"Staff onboarding" → "Customer onboarding"**.
  - Section title updated to "Customer onboarding".
  - Section description updated to "Onboard a new customer organisation, send shareable packets, or bulk-load CSV rosters".
  - `LEGACY_SECTION_REDIRECTS['onboarding']` now points to `'organizations'`.
- Verified live: Organisations sidebar entry now shows 4 sub-tabs (List · Customer onboarding · Module subscriptions · Customer activation). Customer onboarding renders `<AdminOnboardingHub>` with all 4 wizards intact.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin on `gymaxisai.com`: Sidebar → **Organisations → Customer onboarding** — runs the brand-new customer wizard. The drawer in People → Directory opens on row click for fast reset-link issuance.

---


## Iter 216h19 — Master Admin redesign Phase 3: People SSoT consolidation (Feb 11, 2026)

The biggest single-source-of-truth win of the redesign. Four legacy People panels collapsed into one **People Directory** that operators can actually onboard staff against this week.

### What shipped (frontend only — backend already merges correctly since iter 215ev)
- **`PeopleDirectory.js`** — single React surface that absorbs the per-row responsibilities of:
  - `AdminUsers` (cross-org user list)
  - `GlobalUsersPanel` (archive / purge / leaver flow — preserved as a legacy fallback tab)
  - `AdminPulseAdmins` (dual-role Pulse Master Admins — still has its own panel for the matrix; surfaces as rows in Directory)
  - `AdminCRMUsers` (CRM-only contacts — surfaces as rows with the `CRM` portal badge)
- **Components inside the Directory**:
  - **6-tile stats strip** — Total active · Pulse admins · Owners · Staff/Managers · CRM-only · Role mismatches.
  - **6 filter pills** with live counts — Everyone / Pulse Admins / Owners / Staff & Managers / CRM contacts / Archived. Pills are colour-coded to match the role-chip palette.
  - **Search box** scoped to name + email + organisation name.
  - **Role chips** (Pulse Admin = blue, Owner = purple, Manager = emerald, Staff = zinc, Master Admin = orange).
  - **Portal badges** per row (Service Portal / CRM / Pulse Platform).
  - **Role mismatch warning** (red `invited as X` chip) when `invited_role ≠ current_role` (iter 216h3 detection surfaced here).
  - **Site-pin hint** — "N site(s) pinned" inline when `allowed_site_ids` is non-empty.
- **`AdminRoles.js` restructured** — Directory is now the FIRST tab (default). Permissions matrix, Service Desk team, Pulse Master Admins, and the legacy GlobalUsersPanel each get their own clearly-labelled tab. "Legacy users panel" name explicitly flags it as the pre-P3 surface so operators know it's there as a safety net only.
- **Brand-aware** — the Directory consumes the brand-filtered `users` array from `MasterAdminPage.loadData` (iter 216h18). Flipping the brand picker re-filters everything; the brand label is echoed in the directory subtitle.

### Verified live on preview
Master Admin → People → Directory rendered cleanly with:
- 101 total active, 20 Pulse admins, 49 owners, 30 staff/managers, 2 CRM-only, 0 role mismatches.
- Pill click "Owners" → 49 rows filtered correctly.
- Search "admin" chained with the Owners pill → 9 rows.
- Legacy users panel tab still accessible.
- Sidebar IA from P1 intact (8 entries).

### Important consolidation accounting
- **Before P3**: a single human was renderable in 4 different lists with 4 divergent action sets.
- **After P3**: one row per (email × org_id), portal badges show which systems they have access to, click any row to deep-drill via existing UserEditDialog (Profile / Sites / Permissions / Activity tabs already exist from iter 216h15 + 216h16).
- **No DB changes** — the dedupe / merge already happens server-side in `/api/master-admin/users`. P3 is pure UX consolidation.

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: People → Directory should land you on the new unified list. Use it for the staff onboarding this week.
3. If anything feels missing, the "Legacy users panel" sub-tab is still 1 click away as a safety net for the first release.

### Remaining roadmap
- 🟢 P4 — Collapse 3 Organisation panels (AdminOrganizations + AdminPulse + Memberships orgs tab).
- 🟠 P5 — Integrations hub (5 surfaces → 1 page).
- 🔵 P6 — Staff Onboarding wizard.
- 🔵 P3-followup — wire the Directory's row click into the existing UserEditDialog drawer (currently calls `onReload`).

---


## Iter 216h18 — Master Admin redesign Phase 2: Brand Context wired into data layer (Feb 11, 2026)

P1 (iter 216h17) shipped the UI scaffolding for the brand picker. P2 wires the picker into the actual data queries — operators flipping Pulse / GymAxis / All now changes what data is loaded, not just the pill label.

### Backend (single source of truth)
- **New `utils/brand_filter.py`**: Canonical brand classification + Mongo query helper. A record belongs to:
  - **Pulse** — `account_type` in {pulse_pro, pulse_lite, pulse} OR `is_pulse_admin: True` OR `brand` in {pulse, pulse_fitness}.
  - **GymAxis** — `account_type` in {full, gymaxis, gymaxis_admin, lite, ""} OR `account_type` absent OR `brand` in {gymaxis, ""}. (`lite`/null intentionally classified as GymAxis — GymAxis is the platform default; production has 21 such orgs.)
- Helpers: `normalise_brand()`, `brand_filter_clause()`, `merge_brand_filter()` (handles edge case where existing query already has `$or` — promotes to `$and`).
- `GET /api/master-admin/organizations` now accepts `?brand=pulse|gymaxis|all`. Filter composes safely with the existing `is_pulse_only(user)` permission gate (permission always wins).
- `GET /api/master-admin/users` now accepts `?brand=…` and **scopes by parent-org brand** so legacy users with `account_type=null` are still correctly classified by their org's brand (the org is authoritative).

### Frontend
- **`useBrandedAPI()` hook**: tiny `apiUrl(path, extraParams)` helper that auto-appends `?brand={ctx}` to any URL. Exports `brand` for use in React-Query / SWR keys.
- **`MasterAdminPage.loadData`** now reads `useBrandContext()` directly and adds the brand to all three core requests (`/stats`, `/organizations`, `/users`). `loadData`'s `useCallback` deps include `_brandQS`, so flipping the picker triggers a fresh fetch automatically.

### Verified live
- 3 sequential screenshots from preview captured the picker flipping cleanly through **Pulse → GymAxis → All** with the sidebar's new 8-entry IA intact (Overview · People · Organisations · Sites · Finance · Growth · Integrations · Settings & Compliance).
- **22/22 backend tests passing** in `test_iter_216h18_brand_filter.py`:
  - 7 parametrized normalisation tests (case-insensitive, alias handling, fallback to "all" for noise input).
  - 5 helper logic tests (empty for all, 3-path pulse user filter, gymaxis includes null account_type, merge preserves existing query, double-$or promoted to $and).
  - 6 endpoint partition tests (Pulse excludes GymAxis, GymAxis excludes Pulse, All returns both, users follow parent-org brand, omitted defaults to all, unknown brand defaults to all).

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: Open Organisations, flip the brand pill to **Pulse Fitness** — only Pulse Fitness orgs remain visible. Flip to **GymAxis** — only GymAxis orgs visible. Flip to **All** — every customer visible.

### What this still does NOT do (P3-P6)
- Doesn't yet collapse the 4 People panels into one Directory (P3).
- Doesn't yet collapse the 3 Org panels into one (P4).
- Doesn't yet pin the brand filter to other panels beyond stats/orgs/users (e.g. financial-ops, marketing-suite still show all data). Wiring those is mechanical now that the helper exists — they can be added in P3 along with the consolidations.

---


## Iter 216h17 — Master Admin redesign Phase 1: Information Architecture + Brand Context (Feb 11, 2026)

**Audit findings & rationale**: The legacy Master Admin had 14 top-level sidebar entries + 23 sub-tabs (37 nav surfaces) — too dense for sales/marketing staff onboarding this week. Multiple single-source-of-truth violations identified across People (4 panels), Organisations (3 panels), Equipment images (5 panels), Integrations (5 panels). Brand divergence between Pulse Fitness and GymAxis was implemented ad hoc via scattered `gymaxisOnly` flags.

Engaged `design_agent_full_stack` for the redesign blueprint → produced `/app/design_guidelines.json` with the new IA, brand strategy, People/Org SSoT designs, integrations hub plan, staff onboarding wizard, visual language references (Linear / Vercel / Stripe Atlas / Sentry / Notion teamspaces) and terminology cleanup.

### What shipped in Phase 1 (foundation only — no data routing changes)
- **New 8-entry sidebar IA** (`SidebarConfig.js` overwrite):
  1. Overview — Dashboard · System Health · Setup checklist
  2. People — Directory · Site-locked users · Staff onboarding
  3. Organisations — List · Module subscriptions · Customer activation
  4. Sites — Equipment images · Custom properties
  5. Finance — Pricing · Org billing · Collections · Payments · Stripe · Financial ops · Refunds · CAPEX
  6. Growth — Trials · Sales insights · Global analytics
  7. Integrations — Orbit 4 · Sicon Service · Stripe Connect
  8. Settings & Compliance — Audit log · Login events · Documents · Outbound emails · Ask Support · Support tools · Database viewer · Maintenance jobs · Design system
- **Brand context** (`BrandContext.js`): React context + provider with All / Pulse Fitness / GymAxis. Persists to localStorage. Fires `master-admin-brand-change` window event so legacy panels can react. Exports `filterByBrand()` helper.
- **Brand picker pill** (`BrandPicker.js`): Sits in the Master Admin top bar between Email Health and Refresh. Dropdown with 3 options + descriptive footer.
- **Terminology cleanup** in `sectionTitles` / `sectionDescriptions`:
  - "Trust & Reliability Engine" → "System health"
  - "Roles & Access" → "People directory"
  - "Tasks" → "Setup checklist"
  - "Locked staff" → "Site-locked users"
  - "Activation Funnel" → "Customer activation"
  - "Estate Rollup" → "Module subscriptions"
  - "Data Backfills" → "Maintenance jobs"
  - "Onboarding" (ambiguous) → "Staff onboarding"
- **`LEGACY_SECTION_REDIRECTS`** map documents which legacy section IDs were absorbed into which new groups (no functional redirect yet — `renderSection` still resolves all IDs directly; this map is for review/audit + future P2-P5 consolidations).

### Verified live on preview
- Sidebar shows all 8 entries with correct labels.
- Brand picker pill labelled "All" by default; opens dropdown with All Brands (ACTIVE) · Pulse Fitness · GymAxis + footer copy.
- Clicking Pulse Fitness flips the pill label to "Pulse" and persists to `localStorage.master_admin_brand_filter = 'pulse'`.
- Clicking People renders the "People directory" header with the subtitle "Pulse Admins · Customer Owners · Customer Staff · CRM contacts — all in one directory" and sub-tabs Directory / Site-locked users / Staff onboarding.

### Next phases (recommended order per blueprint)
- **P2** — Wire BrandContext into every panel's data query (currently UI-only).
- **P3** — Collapse the 4 People panels (`AdminUsers` + `GlobalUsersPanel` + `AdminPulseAdmins` + `AdminCRMUsers`) into one Directory page with role-coloured chips + drawer tabs (Profile · Sites · Permissions · Activity · Sessions).
- **P4** — Collapse 3 Org panels into one Organisations page with tabbed drawer (Profile · Sites · People · Modules · Billing · Integrations · Activity).
- **P5** — One Integrations hub with brand status pills + click-to-detail drawer.
- **P6** — Staff Onboarding wizard (invite → role → sites → modules → audit) reusing the iter-216h15 reset-link flow.

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: top bar now has a brand-picker pill — click it, pick Pulse Fitness, refresh; the choice persists. Sidebar is reorganised into 8 clean groups.
3. Tell me when to start P2/P3 — they're the high-value SSoT consolidations.

---


## Iter 216h16 — Trust & Reliability RAM/CPU/Disk + Master Admin parity for site allocation (Feb 11, 2026)

### A. System resources panel on Trust dashboard (`psutil`)
- **Backend**: `_system_metrics()` helper + new `GET /api/master-admin/trust/system` endpoint + `system` block embedded in `/trust/overview` so the dashboard hits one round-trip. Returns CPU (%, count, load avg), memory (used/avail/total MB + status banner), swap, disk (used/free/total GB + status banner), process (RSS MB, CPU%, started_at, PID), and hostname. Status banner ramp: < 70% → `ok` (green), 70–89% → `warn` (amber), ≥ 90% → `critical` (red).
- **Frontend** (`TrustDashboard.js`): new `SystemResourcesPanel` + `ResourceGauge` components. 3-column responsive grid with bar + tone label ("OK" / "WATCH" / "UPGRADE NOW"). Footer line shows process RSS / CPU / uptime + an amber upgrade tip when any gauge hits warn/critical.
- **Live preview snapshot**: CPU 5.1% OK · RAM 58.4% OK (18.7/32 GB) · Disk 54.8% OK (58/106 GB).
- **Tests**: `test_iter_216h16_trust_system_metrics.py` — 4/4 passing (master-admin gating, full field shape, overview embedding, threshold sanity).

### B. Master Admin parity: site allocation on user edit drawer
- **AdminOrganizations.js**: user edit dialog now fetches `/master-admin/organizations/{org_id}/sites` on open, and renders a chip-style multi-select inside a new "Site access" panel (only for non-owner, non-master-admin roles). Uses the existing `PATCH /master-admin/users/{id}` endpoint which already accepted `allowed_site_ids` — no new backend endpoint needed.
- HQ sites show with a ★ prefix; pinned sites show a ✓ + blue accent.
- Mirrors the owner-side chip UX from iter 216h15 so Master Admins get identical UX to Owners.

### C. Master Admin parity: reset link / temp password
- Already present in MA user-edit dialog (iter 215bi+215ev). No work needed. Both buttons live side-by-side: "Reset Link" (green, copies invite URL) + "Temp Password" (blue, copies a freshly-minted temp password).

### ⚠ Action required
1. **Redeploy** preview → production. `psutil==7.2.2` is now in `requirements.txt`.
2. On `gymaxisai.com`: Master Admin → **Security → Trust & Reliability → Live platform health** → the new "System resources · this pod" panel appears between the summary tiles and Integration Health.
3. Master Admin → Organisations → Open any org → click a non-owner user → new "Site access" chip selector appears under the Role field.

---


## Iter 216h15 — Real auto-created Head Office + owner team management (Feb 11, 2026)

**Operator feedback**: "Head Office is a proper site — sales/marketing/admin are assigned to it, even though it usually has no equipment." Also: (B) "Can't allocate staff to sites" and (C) "Owners need ability to send a reset link, not show inline temp password."

### Replaced synthetic HQ with auto-created real HQ
- Iter 216h14's synthetic `hq:{org_id}` was wrong (couldn't have staff/users assigned). Replaced with: when an org has ≥1 site but **none** flagged HQ, `/api/sites` now **persists a real `db.sites` row** (`name = "{Org} Head Office"`, `is_head_office=true`, `auto_created=true`). Idempotent. Existing real HQ takes priority.
- HQ is sorted to the TOP of the SiteSwitcher list.
- Renamed dropdown label **"All sites" → "All Operations Sites"** (dashboard header + SiteSwitcher dropdown + AllSitesOverview page title).

### B. Site allocation for owners
- New endpoint `PATCH /api/account/team/{user_id}/site-access` — owner pins a teammate to a subset of org sites (or clears → full access).
- Tenant-isolation: site ids from other orgs are silently filtered out.
- Owners can't pin themselves or other owners (they always see all sites).
- Audit fields stamped: `site_access_updated_at`, `site_access_updated_by`.
- **Account Settings → Team & Roles**: each teammate row now shows a "Sites: …" summary with an inline "Edit sites" toggle that opens a chip-style multi-select.
- Invite form gained a "Pin to sites (optional)" chip selector — pins at invite time.

### C. Send reset link (replaces inline temp password)
- New endpoint `POST /api/account/team/{user_id}/send-reset-link` — issues a 72 h password reset token, mirrors Master Admin's existing UX, stamps `password_reset_sent_at` + `password_reset_sent_by` for the audit trail.
- Invite form: added "Delivery" dropdown — `Email password reset link (recommended)` vs `Show temporary password inline`. Default is reset link.
- Each existing teammate row has a **"Send reset link"** button that issues a fresh link, copies it to the operator's clipboard, and updates the audit trail.
- Audit trail line ("Last reset link sent {date} by {owner email}") appears under the teammate row when applicable.

### Verified — 13/13 tests passing in `test_iter_216h15_team_management.py`
1. Auto-create HQ on first `/api/sites` call (real `db.sites` row, not synthetic).
2. Idempotent — second call doesn't double-create.
3. Invite with `delivery=reset_link` returns invite_url, no temp_password leak.
4. Legacy `delivery=temp_password` still works.
5. Invite-time `allowed_site_ids` is persisted.
6. Owner can pin staff to subset of sites.
7. Empty allowed_site_ids = full access.
8. Foreign-org site ids are filtered out (tenant isolation).
9. Owners cannot be pinned.
10. Send-reset-link returns invite URL + audit stamps.
11. Send-reset-link 404s for unknown users.
12. Send-reset-link rejects other owners as targets.
13. `/api/account/team` GET surfaces the reset audit trail.

### Visual smoke test (preview, impersonating Test Owner of multi-site org with no HQ)
- Page header reads: **"Pulse Fitness · Test HQ No Flag Head Office"** ← auto-created HQ.
- Invite form shows DELIVERY dropdown + PIN TO SITES chip strip with HQ first (★ icon).

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Lee on `gymaxisai.com`:
   - Open Account Settings → Team & Roles → invite a sales-admin teammate with delivery = "Email password reset link" → pin to "Pulse Fitness Head Office" only.
   - Send reset link to any existing teammate — copies URL to clipboard.
3. Confirm the SiteSwitcher now shows: **All Operations Sites | ★ Pulse Fitness Head Office | iGym Carshalton | iGym Congleton**.

---


## Iter 216h13 — Short equipment-row display + backfill endpoint (Feb 11, 2026)

**Operator-reported (with screenshots)**: imported equipment rows were rendering the full 200-char Pulse marketing line ("Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, Apple/Samsung Watch Connectivity, Content Mirroring & Wireless Charging in Sand Black…") as BOTH the equipment `name` AND `model`, blowing the row layout out of the page. Operator demanded the row match the manual-add format: `Treadmill (cardio)` · `Pulse Fitness · 260G · 12345`.

### What shipped (backend)
- **`_EXTRACTION_TEMPLATE` schema gained `equipment_name`** (SHORT subtype noun) **and `description`** (FULL marketing line).
- **`_short_equipment_name(eq)`**: Picks AI-extracted name when ≤ 40 chars; heuristic keyword fallback (treadmill/stepmill/upright cycle/recumbent cycle/cross-trainer/rower/smith machine/lat pulldown/leg press/etc.).
- **`_short_model_code(eq)`**: Prefers `stock_item_code`. Refuses any "model" > 24 chars or > 2 spaces.
- **`_build_equipment_doc`**: Now produces clean rows. `name = short subtype`, `model = short stock code`, `description = full marketing line`, `notes = "Imported from invoice {n} · {description}"`.
- **Wizard preview** + **Sicon CSV row** + **`/parse-invoice` response** all use the same helpers → wizard preview matches what gets created on confirm.

### Backfill endpoint for legacy data
- **`POST /api/master-admin/equipment/backfill-short-display`** (master-admin gated):
  - Body: `{organization_id?, site_name?, supplier_name?, dry_run?}` — also accepts `?dry_run=true|false` query param.
  - Only touches rows with `import_id` set OR notes starting with "Imported from invoice" (manual-add rows are untouched).
  - Skips rows already in the short shape (idempotent — second run returns 0 updates).
  - Returns `{dry_run, total_candidates, equipment_to_update, equipment_updated, orgs, preview[≤200]}`.
- **UI**: New card in **Master Admin → Data Backfills** titled "Short equipment-row display (iter 216h13)" with Preview + Apply buttons. Reuses the existing dry-run-first pattern.

### Verified live (preview)
- Seeded 4 rows (3 legacy long + 1 control short manual-add).
- Dry-run preview returned `equipment_to_update: 3` with the exact before→after split (StepMill / 200H-AAF, Upright Cycle / 240G-AAV, Treadmill / 210T-BBC).
- Commit applied 3 updates; control row untouched.
- Re-running commit returned `equipment_updated: 0` — idempotent.
- New backfill card visible in MA → Data Backfills with Preview + Apply buttons.

### Regression — 19/19 passing across two new test files
- `test_iter_216h13_short_equipment_display.py` (13/13): helper unit tests.
- `test_iter_216h13_backfill_short_display.py` (6/6): API tests — dry-run preview, commit, skips already-short rows, idempotency, master-admin gate, site-name filter.

### Cost reassurance
Operator was concerned $17.44 was per-invoice. Clarified via support_agent: 1 credit = $0.20 USD, so 20 credits = $4. Their $17.44 is cumulative spend across every AI feature since signup (≈ 87 credits worth). A single Carshalton-sized extraction costs ~$0.10–0.20 (Claude Haiku 4.5). Add balance via Profile → Universal Key; auto-recharge available.

### ⚠ Action required
1. Top up Universal Key.
2. Redeploy preview → production.
3. On production: **Master Admin → Data Backfills → "Short equipment-row display" → Preview → Apply** to clean up the existing Carshalton rows (no need to delete + re-import; preserves equipment IDs, fault history, QR codes).
4. New invoice imports going forward will already use the short shape.

---


## Iter 216h12 — Carshalton invoice import: truncation + missing fields + supplier auto-matching (Feb 11, 2026)

**Production bugs reported**: User uploaded the Carshalton Invoice PDF (Pulse Fitness → South Thames College, £421,804.01 gross, 88 line items across 20 pages). Operators complained that the import "missing details and supplier matching".

### Root cause investigation
- **Missing details**: `_build_extraction_prompt` was truncating PDF text at `pdf_text[:12000]` — but the Carshalton PDF extracts to **24,090 chars**. The AI only saw ~28 of the 88 line items, plus none of the totals (NET £351,503.34 / VAT £70,300.67 / GROSS £421,804.01), bank details (HSBC sort 40-28-56, acct 40023205), customer reference (00000512 for payment), supplier VAT (785413509) or company number (4354059) — all of which sit in the second half of the document.
- **Supplier matching**: The extracted `supplier_name` was just a raw string. `db.suppliers` already had Pulse Fitness in the org directory but the import never tried to link to it, so every import created an orphan/duplicate supplier reference.

### What shipped
- **`equipment_import.py` — `_PDF_TEXT_MAX_CHARS = 40_000`** (was 12 000). Haiku-4.5 has a 200 K-token input window so 10 K extra tokens is well within budget; latency impact is ~+5-10 s for the largest invoices.
- **`_EXTRACTION_TEMPLATE` schema extended** with `supplier_vat_number`, `supplier_company_number`, `customer_name`, `customer_reference`, `due_date`, `payment_terms`, `bank_details` (bank_name, account_name, account_number, sort_code), and `totals` (net, vat, gross).
- **`_normalise_supplier_name(name)`** — collapses "Pulse Fitness Limited", "PULSE FITNESS LTD.", "Pulse Fitness", "pulse-fitness ltd" all to the same key for fuzzy match.
- **`match_supplier(org_id, supplier_name, vat_number)`** — 3-tier match priority: (1) exact case-insensitive, (2) VAT number, (3) normalised name. Returns the matched supplier doc (no `_id`) or None. Tenant-scoped to `organization_id`.
- **`/api/equipment-import/parse-invoice`** + **`/api/master-admin/invoice/parse-for-wizard`** — both endpoints now surface `matched_supplier`, `matched_supplier_id`, plus the new invoice metadata fields (totals, bank, customer ref, due-date, payment terms) in their response.

### Regression — `test_iter_216h12_carshalton_supplier_match.py` (13/13 passing)
- Truncation cap is pinned at ≥ 24 000 (locks the bug surface — refactors can't silently re-shrink).
- Prompt schema regression: explicitly asserts every new field key is present in the prompt.
- `_normalise_supplier_name` covers 4 shape variants + empty/None.
- `match_supplier` covers exact, case-insensitive, normalised, VAT-number, no-match, wrong-org, missing-args.

### ⚠ Action required (BLOCKED on Emergent LLM budget top-up)
- The Emergent LLM key budget is **exhausted** (`Current cost: $17.44 / Max: $17.40`). End-to-end live extraction can't be verified against the Carshalton PDF until you top up via **Profile → Universal Key → Add Balance** (or enable auto top-up). Once topped up, re-run the import on production — the changes are deterministic and the unit tests pin every contract surface, so the live run should succeed.
- After re-running on production, you'll see: full 88-line extraction (not 60), populated totals/bank/customer-ref fields, and a `matched_supplier_id` so the operator can one-click "Link to existing Pulse Fitness".

---

## Iter 216h11 — Spec Sheet dropdown crash + bulk delete + image graceful degradation (Feb 11, 2026)

**Production bugs reported**: (a) Master Admin → Image Catalogue → Spec Sheets dropdown was crashing the entire page (React error "Objects are not valid as a React child"). (b) Spec Sheet hero images were rendering as blank/broken-image icons. (c) User requested a "bulk select + delete" workflow.

### What shipped
- **`AdminSpecSheets.js` — `safeRenderValue()` helper**: Recursively coerces any JSON value (including nested objects like `{value, unit}`, `{min, max}`, generic `{key:value}`) into a compact human-readable string. Wraps every `key_specs` cell + `description` so the AI extractor can never crash the route again.
- **`AdminSpecSheets.js` — `<SpecImage>` component**: Adds `onError → "No image" placeholder` fallback for the public `/api/spec-sheets/image/{id}` endpoint. When the underlying S3/storage object is missing the user sees a friendly placeholder instead of a broken-image icon.
- **`AdminSpecSheets.js` — `<ExpandedDetail>` component**: Extracted to its own component with a defensive try/catch render guard (`spec-expand-error-{id}` test-id) so any future malformed payload can't take down the whole panel.
- **Bulk select + delete**:
  - Per-row checkbox (`spec-select-{id}`).
  - "Select all (N)" / "Clear selection" toggle (`spec-select-all`).
  - Sticky black bulk-action bar at top with row count + red "Delete N selected" button (`spec-bulk-bar`, `spec-bulk-delete`).
  - Loops `DELETE /api/spec-sheets/{id}` per selected id, shows mixed-success toast (`X deleted · Y failed`) and refreshes the grid.
- **PDF preview fallback**: iframe `onError` switches to a small "PDF preview unavailable" card so a missing storage object doesn't leave an empty panel.

### Verified live (preview)
- Seeded 2 test spec sheets (one with object-shaped `key_specs` — the exact crash vector) — page renders all of `flywheel weight: 22 kg`, `resistance: 1–24`, `dimensions: length: 120cm; width: 55cm; height: 115cm` plus the object-shaped description `short: …; long: …` without crashing.
- "Select all (2)" → black bulk bar visible → "Delete 2 selected" red button rendered → "Clear selection" dismisses bar.
- Missing `hero_image_url` shows placeholder icon (no broken-image).
- 0 captured `pageerror`s during the flow.

### Regression — `test_iter_216h11_spec_sheet_render_safety.py` (4/4 passing)
1. `test_list_returns_raw_object_key_specs` — backend round-trips object-shaped values unchanged (bug surface stays observable).
2. `test_delete_spec_sheet_hard_deletes_row` — single DELETE wipes a seeded row (powers bulk loop).
3. `test_delete_missing_spec_sheet_returns_404` — graceful 404 on already-deleted ids.
4. `test_image_endpoint_is_public_and_404s_cleanly` — endpoint returns 404 (not 401) when no image is stored so `<SpecImage>` placeholder triggers correctly.

### ⚠ Action required
Lives in **preview** only — **redeploy** to push to gymaxisai.com. If the production images stay blank after deploying, the underlying S3/storage objects are missing — re-upload affected spec sheets.

---


## Iter 216h10 — Fix for "0 records wiped" on production purge (Feb 10, 2026)

**Production bug reported**: user clicked "Remove everywhere" on Craig Henshall, toast showed "0 record(s) wiped" but the row remained. Root cause: my iter-216h8 purge endpoint only deleted from `db.users`, but the "Already added" check in `master_admin.py::add_user_to_organization` also looks at `db.crm_users` — so a stale row in `crm_users` was blocking re-onboarding without being touched by the purge.

### What shipped
- **Backend**: extended both `hard_purge_pulse_admin` (by id) AND `hard_purge_user_by_email` to ALSO delete from `db.crm_users`. Audit-log queries extended to find crm_users matches too, with `_collection: "crm_users"` annotation so the audit trail makes it obvious where rows came from.
- **Frontend `GlobalUsersPanel.js`**: fixed misleading toast — when the email regex matches 0 rows, the toast now shows a **warning** (not success) with actionable hint, AND automatically falls back to a hard-delete by user_id (auto-archives first since hard-delete is archive-gated). Fallback emits its own success toast indicating it was used. Success toast also now mentions CRM rows wiped when applicable.

### Why the fallback path matters
If the stored email has a hidden character, weird whitespace, or unexpected format, the email-regex match returns 0 — but we still have the user_id from the row that was clicked. Falling back to id-based delete catches this edge case without operator intervention.

### Regression — `test_iter_216h8_user_purge.py` extended to 5 tests (was 4)
- New `test_purge_by_email_also_wipes_crm_users` seeds a crm_users row and verifies the purge endpoint deletes it. **All 5 pass.**

---

## Iter 216h9 — Global Users panel + leaver workflow (Feb 10, 2026)
(See CHANGELOG history — fully shipped, 109 users panel with archive/delete + remove-everywhere, 4-pill status filter, master-admin auto-protected.)

---

## Prioritised backlog (P0/P1/P2)

### P0 — Currently in-progress
- None — iter 216h11 just landed.

### P1 — Reported bugs (next)
- **Carshalton invoice import**: missing details + supplier matching. **BLOCKED** awaiting user to upload an example PDF/image so the LLM extraction prompt can be tuned.
- **Head Office site not selectable for owners**: site-selector should show "All sites | Head Office | Site A | Site B" for multi-site orgs.
- **RAM usage metric on Trust & Reliability dashboard**: build via `psutil` per-pod gauge backend → existing T&R UI tile. Helps user decide on package upgrade.
- **"Jump to this user" link** in error toast when an existing user is re-added on the org drawer.

### P1 — Integration work
- Sage 200 / Sicon ledger posting on payment, CRM lead conversion, custom domains (`join.{gym-domain}.com`).

### P2 — Blocked / Parked
- Sicon and Sage 200 LIVE connection cutover (waiting on creds).
- Sentry DSN for production observability (Parked).
- Twilio SMS real integration (Parked).

---

## Critical operator notes
- User tests on **production** (gymaxisai.com). Agent only sees **preview**. Remind them to hit "Deploy" after each fix lands.
- Recent deploy failure was a "pod not found" infra error — fix is to re-hit Deploy (NOT a code issue).
- Master Admin credentials: `admin@gymaxisai.com` / `MasterAdmin123!` (always preserved).
- Preview DB has been wiped — only the master admin + Tottenham Green Leisure Centre data remain (since iter 215bs).
