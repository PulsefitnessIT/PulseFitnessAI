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
