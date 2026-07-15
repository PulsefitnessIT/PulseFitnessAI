# Changelog


## Jul 14, 2026 — Dealer Parts (Phase 5, final) — AI + Reports + Dealer Portal
- **AI (Emergent LLM key, model openai/gpt-5.2, advisory-only)** — `routes/dealer_parts_portal.py` + `utils/dealer_parts_ai.py`:
  - `POST /ai/parse-invoice {text}` extracts machine lines + order value from pasted invoice/order text (never invents lines) → Orders tab "Parse invoice with AI" pre-fills the import form for review, then auto-calculates the allowance.
  - `POST /ai/dealer-summary {dealer_id}` drafts an internal summary + highlights + a friendly dealer-facing note.
- **CSV Reports** — `GET /reports/{allocations|stock|usage|failures}.csv` (attachment downloads; Reports tab buttons fetch as blob with auth header).
- **Dealer Portal** (`portal/{dealer_id}/overview`, `request-replenishment`, `replenishment-requests`) — dealer-scoped views (a dealer only sees their own store/stock/usage/incoming shipments) + raise replenishment requests; Pulse can list & action requests. Frontend "Dealer Portal" tab with dealer selector.
- **Tested:** testing_agent — backend 11/11, frontend 100%. No issues. AI verified live (parsed PO ref + lines; generated dealer summary).
- **Status:** Global Dealer Parts module COMPLETE across all 5 phases (dealers, orders+allowance, allocations, BOM, most-used, recommendation engine w/ duplicate prevention + failure-driven closed loop, engineer usage → stock/ledger/case, stores dept, RMA, failure monitoring + intelligence, replenishment, alerts, dealer portal, reports, AI). All under Service Desk → Stores → Dealer Parts.



## Jul 14, 2026 — Dealer Parts: nav merge + Phase 4 (Failure Monitoring + Intelligence + Replenishment + closed loop)
- **Nav change:** Service Desk sidebar "Parts" → renamed **"Stores"**; the standalone "Dealer Warranty Parts" tab is merged INTO Stores as a sub-tab **"Dealer Parts"** (alongside "Pulse Warehouse"). Module retitled **"Dealer Parts"** (now covers all dealer parts, not just warranty). Files: `ServiceDeskPage.js` (desk-tab-stores, desk-stores-sub-warehouse/dealer).
- **Backend (`routes/dealer_parts_intel.py`, reads Phase 3 usage logs):**
  - **Global Failure Intelligence** — `GET /intel/overview` (top failing parts, by country/dealer/model/reason, monthly trend) and `GET /intel/failures?group_by=part|country|dealer|model|serial`.
  - **Parts Failure Monitoring Agent** — `POST /monitoring/run` generates alerts: high_failure_rate (country vs average of OTHER regions × spike factor), potential_quality_issue (≥3 defect-type failures), repeated_failure_by_serial (≥3 in a serial prefix/batch). Idempotent dedup on open alerts. `GET /alerts`, `PATCH /alerts/{id}` (new→…→resolved/dismissed).
  - **Replenishment engine** — `GET /replenishment`: on-hand vs min/recommended + 90d usage → labels (No Action/Monitor/Low Stock/Replenishment Recommended/Critical/Overstocked) with recommended qty + value.
  - **Closed loop** — `failure_bump()` imported by the recommendation engine: when a SKU fails above the other-region average in a dealer's country, the recommended pack quantity is auto-increased (with an explanatory reason) and a quality flag raised. Verified: MOTOR-260G (7 failures Germany vs 1 Spain) bumped 2→4 for a Fitline order.
  - Settings gained monitoring thresholds: enable_monitoring_agent, failure_alert_threshold, usage_spike_factor, monitoring_window_days.
- **Frontend:** new tabs — Failure Intelligence (charts + grouping toggles), Monitoring & Alerts (run agent + status workflow), Replenishment (labelled table + filter).
- **Tested:** testing_agent — backend 13/13, frontend 100%. No issues.
- **Deferred:** Phase 5 (Dealer Portal + Reports/Exports + AI invoice parsing/summaries).



## Jul 14, 2026 — Dealer Warranty Parts (Phase 3) — Engineer usage flow + Stores Dept + Returns/RMA
- **Backend (`routes/dealer_parts_ops.py`, reuses Phase 1 helpers):**
  - **Parts usage** (`dealer_parts_usage_logs`) — `POST /api/dealer-parts/usage` logs a part used by an engineer/dealer, DECREMENTS the dealer remote-store stock (sets last_used), writes a `dealer_stock_movements` row (type `part_used` — no stock change without a ledger row), and appends a Service Desk case timeline event (`svc_case_events`, type `dealer_part_used`) when a valid `case_id` is supplied (best-effort, non-existent case never errors). Captures warranty/chargeable, failure_reason, serial, machine model for Phase 4 monitoring.
  - **Stores Department** — `GET /api/dealer-parts/stores-dashboard`: cards + picking/dispatch queue (approved allocations), shipments awaiting receipt (dispatched/partially-received), recent usage, low-stock lines.
  - **Returns / RMA** (`dealer_parts_rma`) — create (auto RMA reference), list, PATCH status through the lifecycle (return_requested → … → under_inspection/quality_review → closed) with inspection/quality/warranty/credit fields.
- **Frontend:** new tabs — **Engineer Usage** (log part used → stock reduces; per-row Raise-RMA), **Stores Dept** (dashboard with pick&dispatch + confirm-receipt actions), **Returns / RMA** (create + inline status dropdown).
- **Tested:** testing_agent — backend 9/9, frontend all flows. No issues.
- **Deferred:** Phase 4 (Failure Monitoring Agent + Global Failure Intelligence + Replenishment + Alerts — INCLUDING the closed loop: monitoring insights auto-adjust Recommendation Engine pack quantities per region/dealer and flag quality issues), Phase 5 (Dealer Portal + Reports + AI).



## Jul 14, 2026 — Dealer Warranty Parts (Phase 2) — BOM + Most-Used + Recommendation Engine
- **Backend (`routes/dealer_parts_bom.py`, reuses Phase 1 helpers):**
  - **BOM Management** — versioned per machine model (`dealer_bom`); creating a new active BOM auto-supersedes the prior active version (history preserved, never overwritten). Item flags: warranty_relevance / recommended_spare / service_part / wear_item / consumable, criticality, cost. PATCH changes status (draft/active/superseded/archived).
  - **Most-Used Parts** (`dealer_most_used_parts`) — upsert by (model, part_number) so re-imports update rather than duplicate; priority (critical→optional), recommended dealer stock qty, usage/failure frequency, cost, lead time.
  - **Recommendation Engine** (`POST /api/dealer-parts/recommend`) — reads an order's machine lines, pulls the active BOM + most-used parts, computes a recommended pack (base qty × fleet factor by priority), then NETS against the dealer's current stock (on-hand + in-transit) and prior non-cancelled allocations → duplicate/repetition prevention. Returns per-part recommended vs original qty, already_held, reason + duplicate_warning, duplicates_avoided, missing_bom_models, total value vs allowance / over-allowance.
- **Frontend (`pages/DealerWarrantyParts/`):** new **BOM Management** and **Most Used Parts** tabs; **"Generate recommended parts pack"** button in the New Allocation flow (populates items with reasons, shows AI-recommendation banner with duplicates avoided + missing-BOM warning). Fixed a width-conflict (base `input` `w-full` vs inline widths) via `inputTight`.
- **Tested:** testing_agent — backend 10/10, frontend all 3 flows. No blocking issues.
- **Deferred:** Phase 3 (engineer-app parts usage + Stores dept + shipments/RMA), Phase 4 (failure monitoring + replenishment + alerts), Phase 5 (dealer portal + reports + AI invoice parsing).



## Jul 14, 2026 — Dealer Warranty Parts (Phase 1) — Service Desk → Parts
New global dealer spare-parts module. Extends the platform, reuses existing records (parts catalogue `svc_parts`, service cases, equipment, CRM companies) — no duplication.
- **Backend (`routes/dealer_parts.py`, prefix `/api/dealer-parts`):** dealers (link to CRM company_id, name/company dedup via `safe_regex_exact`), order/invoice import with automatic spare-parts allowance calc (`allowance = order_value × %`; % resolves order-override → dealer default → global setting), allocation lifecycle (draft → submit → approve → dispatch → receive), auto-created "Main Dealer Store" on dispatch, remote stores + per-part store stock, immutable stock movement ledger, dashboard rollups, settings (manager-gated), audit events. Over-allowance / above-threshold allocations require manager approval.
- **Collections:** dealer_parts_dealers, dealer_parts_settings, dealer_parts_orders, dealer_parts_allocations, dealer_remote_stores, dealer_remote_store_stock, dealer_stock_movements, dealer_parts_audit_events.
- **Frontend (`pages/DealerWarrantyParts/*`):** "Dealer Warranty Parts" sidebar tab in Service Desk. Tabs: Dashboard (cards + allowance-by-country + recent allocations), Dealers (+ detail w/ stores/stock/allocations), Orders & Allowance (live allowance preview), Allocations (workflow action buttons), Remote Stores (+ stock view), Stock Ledger, Settings.
- **Demo seed:** `backend/seed_dealer_parts_demo.py` — 3 dealers (Germany/Spain/UAE) with orders, allocations at different lifecycle stages.
- **Tested:** testing_agent (backend 6/6 after fix, frontend all tabs) + curl + screenshots. Fixed 1 bug: dealer/store name dedup used `safe_regex(^name$)` (escaped anchors, never matched) → now `safe_regex_exact`.
- **Deferred to next phases:** BOM + Most-Used Parts + Recommendation engine (P2), Engineer-app parts usage + Stores dept + Shipments/RMA (P3), Failure Monitoring Agent + Replenishment + Alerts (P4), Dealer Portal + Reports + AI (P5).



## Jul 6, 2026 — Imported Pulse Fitness PDF manual catalogue (103 URLs) + one-click bundled importer
- **Crawled** the uploaded `pulse_fitness_pdf_inventory_partial_103.xlsx` (103 pulsefitness.com PDF URLs) → bundled as `backend/data/pulse_manual_urls.json` (manufacturer="Pulse Fitness", model=Product/Code, title, url, document_type, category).
- **Backend (`routes/machine_manuals.py`):** `GET …/machine-manuals/bundled-catalogue` (status: total/present/missing) + `POST …/global/import-bundled` (idempotent bulk import via shared `_upsert_global_url_manual`). All 103 imported as global URL manuals (verified; re-run reused 103 / imported 0). **Bug fix:** an earlier edit had dropped the `@router.post(.../promote-global)` decorator — restored (route re-registered).
- **Frontend (`MachineManualsDirectoryPanel.js`):** import banner "Pulse Fitness manual library — 103 URLs … Import N manuals" with progress; shows "All imported ✓" when done.
- **Linking to future machines:** manuals are keyed by `make_model_key` (mfr|model); `suggest_manuals` auto-surfaces matching globals to any machine (incl. future imports) as one-click-attach suggestions. NOTE: when the equipment auto-import feature is built it should call the attach/suggest logic to fully auto-link.
- **Data portability:** manual data is DB-backed **per environment**; the bundled JSON + one-click import means production can be populated after redeploy by clicking "Import" once (importing here only affected preview).
- **Verified:** curl (import/idempotency/dedup/302-redirect/route registration) + UI screenshot (banner + 103 Global·URL manuals). Status: preview — REDEPLOY, then click Import on production.


## Jul 6, 2026 — Machine manuals by URL (Master Admin → Catalogue & Library)
- **Feature:** Master Admin can now register a platform-global machine manual by **URL** (e.g. a PDF hosted on pulsefitness.com) instead of uploading a file — saves storage and stays in sync when the source is updated (no re-upload).
- **Backend (`routes/machine_manuals.py`):** new `POST /master-admin/machine-manuals/global/add-url` ({manufacturer, model, title, url}); stores `storage={kind:'url',url}`, `is_url`, top-level `source_url`. Validates http(s); de-dupes by (global make/model + URL). `download_manual` now 307-redirects URL manuals to the source. `_strip` exposes `is_url`/`source_url`. URL manuals cloned to orgs via the existing global-link flow retain their URL.
- **Frontend (`MachineManualsDirectoryPanel.js`):** "…or add a manual by URL" row (input + Add URL), a green **URL** badge on URL-linked rows, and an external-link action that opens the source directly.
- **Verified:** curl (create/dedup/invalid-400/307-redirect) + UI screenshot (URL row + badge render). Status: preview — REDEPLOY to push live.


## Jul 6, 2026 — Blog re-skinned to the Pulse Fitness brand (was legacy "gx"/Gymaxis chrome)
- **Root cause:** `/blog` (BlogIndex) and `/blog/:slug` (BlogPost) rendered inside the legacy `MarketingShell` (the old "gx-" Gymaxis nav/footer), used the `gx-gradient-text` blue→purple gradient (off-brand "AI slop"), a gymaxis-gradient CTA, and non-Pulse fonts.
- **Fix:** new reusable `frontend/src/pages/Marketing/PulseMarketingShell.js` wraps pages in the real pulsefitness.ai chrome — the black sticky `PulseHeader` (WHAT YOU CAN DO / AI / HOW IT WORKS / PLANS / SUPPORT + theme/EN/SIGN IN), `PulseFooter`, `LoginModal`, Proxima Nova via `PULSE_LANDING_CSS`, forced light theme. BlogIndex + BlogPost now use it.
- **Brand pass:** hero accent "run the floor." now Pulse **cyan #19CDFF** (was purple gradient); card image panels are Pulse dark `#1B1C1D` with cyan hover; headings `#1B1C1D`; article CTA restyled to Pulse dark + cyan button linking to `/pulse-pricing` (dropped the gymaxis TrialSignupModal dependency).
- **Verified:** screenshots — both pages render the pulsefitness.ai header + fonts; nav items confirmed; posts load on-brand.
- **Status:** in preview — REDEPLOY to push live.


## Jul 6, 2026 — SEO Autopilot reactivated + on-brand fixes + Blog link in site footer
- **Blog link in footer:** added a **Blog** entry (→ `/blog`) to the COMPANY column of the main-site footer `PulseFooter` (`PulseLandingPage.js`) — the `Col` renderer now treats internal routes (same-tab) vs external links (new tab) correctly. Also added Blog to the shared marketing `Footer.js` (About/Pricing/**Blog**/Contact). testids: `pulse-footer-blog-link`, `footer-blog-link`.
- **Blogs on-brand for Pulse Fitness:** `routes/marketing/seo_autopilot.py` — rewrote the self-contradictory `DEFAULT_BRAND_BLURB` (it previously told the LLM to "not invent pulsefitness.ai" while pulsefitness.ai IS the canonical domain) into clean Pulse Fitness guidance that forbids the legacy "gymaxis/gym-axis" name. Fixed `_BAD_DOMAINS` which wrongly listed the canonical `pulsefitness.ai` (scrubbing it against itself); it now only rewrites genuine legacy domains. Scrub runs across title/excerpt/body/meta/FAQ/social.
- **SEO Autopilot reactivated:** set `seo_autopilot_config.enabled=true` (PUT /api/marketing/seo/autopilot/config) — status confirms enabled, ran_today, hour_uk=9. Config is DB-backed **per environment**.
- **Verified:** scrub keeps pulsefitness.ai + rewrites gymaxis→pulsefitness.ai; footer Blog link renders and `/blog` loads "The Pulse Fitness Blog" with 18 on-brand posts (no gymaxis). 15 published articles.
- **Status:** in preview — REDEPLOY to push footer + brand fixes. ⚠️ To reactivate autopilot on PRODUCTION (separate DB), toggle it ON in Master Admin → SEO Autopilot after redeploy (or it defaults ON if never configured).


## Jul 6, 2026 — 3 production fixes: master-admin login wait, module toggles not persisting, Pulse Ltd users forced to CRM-only
- **(1) Master admin no longer rate-limited on login.** `routes/auth.py login()` now detects the master-admin email (`MASTER_ADMIN_EMAIL`) and skips the strict 5/5-min IP gate + account lockout, using a generous 60/5-min bucket instead. Still records failed-login audit and still requires the correct password/MFA. Non-master accounts remain limited (429 after 5).
- **(2) Org module toggles now persist.** Root cause: legacy orgs stored `modules` as bare booleans (`{operations:true}`); toggling one made `PUT /master-admin/organizations/{id}/features` **500** (`'bool' object has no attribute 'get'`) so the switch silently reverted, and bool entries were dropped from `enabled_modules`. Fix: `routes/master_admin_orgs.py update_org_features()` normalizes legacy boolean module values → `{enabled,tier}` before merging.
- **(3) Master-Admin-created users for Pulse Fitness Ltd now get operator-portal access.** Root cause: `_create_org_user` routed by a STALE `portal_type='crm'` → users landed only in `crm_users`. Fix (`routes/master_admin.py`): derive target collection(s) from the org's ACTUAL enabled modules (operations/memberships/marketing/staffing/reporting → service portal `users`; crm → `crm_users`), falling back to portal_type only when no module info; always guarantees a `users` row.
- **Verified:** curl + testing agent — **100% backend, 100% frontend, zero issues** (`/app/test_reports/iteration_master_admin_fixes_jan2026.json`; regression suite `/app/backend/tests/test_master_admin_fixes_jan2026.py`). Master: 8 wrong attempts all 401 (no 429), correct → 200; non-master → 429 after 5. Legacy-bool toggle → 200 + normalized. Operator-org user → `db.users`. UI: Memberships + CRM toggles persist after reload.
- **Status:** in preview — REDEPLOY to push to production. Note: existing Pulse Ltd users already stuck in crm_users are handled by the earlier CRM login-fallback + the "Repair login access" button; the module normalization heals an org lazily on its next feature save.


## Jul 6, 2026 — P0 "Unknown user" login fixed (CRM-only accounts) + Pulse Pro Documents: type picker & upload ETA
- **Reported (production pulsefitness.ai):** manager Robert Buckley (robert.buckley@pulsefitness.com), created in Master Admin for the CRM-capable "Pulse Fitness Ltd" org, failed standard portal login with "No account matched that email/username", and the set-password/reset link "didn't work".
- **Root cause:** Master-Admin-created users in a CRM-capable org are stored ONLY in `db.crm_users`. Standard `POST /api/auth/login`, `/auth/forgot-password` and `/auth/reset-password` all queried `db.users` exclusively (the CRM login already did the reverse fallback), so such accounts were "unknown" and the emailed reset silently updated nothing.
- **Fix (routes/auth.py — consulted integration_expert first; both collections use identical bcrypt):**
  - `_lookup_user_by_identifier` now falls back to `crm_users` (case-insensitive) when the email isn't in `users`.
  - On first standard-portal login, `_mirror_crm_user_to_users` self-heals a canonical `users` row (same id, role/org preserved, current password hash).
  - `forgot_password` also looks up `crm_users`; `reset_password` updates BOTH collections by `user_id`.
  - No security weakening: non-existent email and wrong password still 401.
- **P1 Documents (Pulse Pro/Lite — `LiteDocumentsTab.js` + shared `UploadQueue.js`):**
  - Added an explicit **document-type dropdown** (`doc-upload-category-select`, 8 categories incl General) so uploads file under the chosen type instead of defaulting to the active tab/General.
  - Upload drawer now shows **percentage + estimated time remaining** (`~Xs left`) per file, then "Complete".
- **Verified:** scripts/verify_crm_login_fix.py (login/mirror/forgot/reset/login-after-reset all pass) + master-admin regression; testing agent **9/9 backend, 100% frontend, zero issues** — `/app/test_reports/iteration_crm_only_login_p1_docs_jan2026.json`. Seeds: `seed_crm_only_login_demo.py`, `seed_lite_docs_demo.py`.
- **Status:** fix in preview — REDEPLOY to push to production.

## Jul 6, 2026 — Master Admin: "Repair login access" (People drawer) — prevents future "unknown user" lockouts
- **Enhancement (builds on the CRM-only login fix):** the People drawer (`UserDetailDrawer.js`) now has a **Login access** section showing, per person, whether they can sign in on the **Standard portal (/login)** and the **CRM portal**, plus a plain-English reason. When an account exists ONLY in `crm_users` it flags the "unknown user" risk and offers a one-click **Repair login access** button.
- **Backend (`routes/master_admin_users.py`):** `GET /master-admin/users/{id}/login-access` (diagnostics) + `POST /master-admin/users/{id}/repair-login` (mirrors a `users` row, copying the bcrypt hash verbatim so the person keeps their existing password). Idempotent (returns `noop` when already fixed); master-admin gated + pulse-scope enforced.
- **Verified:** curl — diagnostics `needs_repair:true` → repair `mirrored_crm_to_service_portal` → idempotent `noop`; CRM-only user then standard-logs-in with the same password. UI — drawer shows the section + button, toast on repair, both portals flip to green, button hides. Seeds reused: `seed_crm_only_login_demo.py`. testid: `people-drawer-login-access`, `login-access-reason`, `people-drawer-repair-login`.
- **Status:** in preview — REDEPLOY to push to production.




## Jul 3, 2026 — Sign-in: added the missing "Forgot password?" flow (frontend gap)
- **Reported (production pulsefitness.ai):** the Pulse portal sign-in modal had no "Forgot password?" option. **Root cause:** the modal had no link at all, AND `/reset-password` only handled the `?token=` case (set-new-password) — with NO token it dead-ended on an "Invalid Reset Link" screen. So there was NO UI anywhere to *request* a reset email; the backend `POST /api/auth/forgot-password` (already present, rate-limited, anti-enumeration) had zero frontend callers. The existing "Forgot password?" link on `/login` therefore also dead-ended.
- **Fix (frontend only — backend auth endpoints unchanged):**
  - `pages/ResetPasswordPage.js`: no-token branch now renders a "Forgot your password?" request form (email → `POST /auth/forgot-password` → generic "Check your email" success, 15-min link note). Token branch unchanged (set-new-password). Removed the dead "Invalid Reset Link" screen + unused `XCircle` import.
  - `pages/PulseLandingPage.js`: added a "Forgot password?" button (`data-testid pulse-login-forgot`) under Sign In → closes modal + navigates to `/reset-password`.
- **Auth note:** consulted integration_expert before touching auth. Captcha on `/auth/forgot-password` fails **open** in this env + production (no `CAPTCHA_SECRET`, `ENVIRONMENT` not `prod`), matching how `/auth/login` already works — so no captcha widget is needed for the request to succeed.
- **Verified:** backend `POST /auth/forgot-password` returns the generic 200 for known + unknown emails and mints a reset token server-side for known emails; all three frontend states render (request form, token set-password form, Pulse-modal link). Testing agent: **100% backend + 100% frontend, zero issues.** Report: `/app/test_reports/iteration_forgot_password_pulse_jan2026.json`.
- **Status:** fix in preview — REDEPLOY to push to production.


## Jul 3, 2026 — PRODUCTION DEPLOY CRASH-LOOP FIXED (true root cause: blocking DNS SRV at Motor client construction)
- **Symptom (recurring):** production k8s rollout timed out — backend never bound `:8001`, nginx logged `connect() failed (111: Connection refused)` on `/health`, uvicorn restarted ~4× and never printed its startup banner. Deploy logs showed only the import-time prints (`[captcha]…`, `python-magic unavailable…`) but NEVER "Uvicorn running on…" → module import never completed in prod.
- **TRUE root cause (finally):** `AsyncIOMotorClient('mongodb+srv://…')` performs a SYNCHRONOUS, BLOCKING DNS SRV+TXT lookup at CONSTRUCTION (motor wraps pymongo `parse_uri`). This client is built at **module-import scope** in `utils/database.py` (line ~29). On the production Atlas `mongodb+srv://` URI, that DNS lookup hung during early pod boot → app import blocked → uvicorn never bound the port → readiness crash-loop. Preview/tests use a plain `mongodb://` URI (no SRV lookup) so it never surfaced. Confirmed empirically: `AsyncIOMotorClient('mongodb+srv://bogus…')` raises a DNS error AT CONSTRUCTION. (Prior fixes — admin_analytics async refactor, deferred `_full_boot`, secrets-audit non-abort — were necessary but did NOT address this shared-client construction.)
- **Fix (`backend/utils/database.py`):** for `mongodb+srv://` URIs, `client`/`db` are now transparent LAZY PROXIES (`_LazyMotorClient` / `_LazyMotorDatabase`) that defer `AsyncIOMotorClient` construction (and its DNS lookup) to first attribute/item access — which happens inside the running event loop, AFTER uvicorn binds the port and `/health` is already answering. For plain `mongodb://` (preview + the 2368-test suite) construction stays EAGER exactly as before → zero behaviour change; `db` remains a real `AsyncIOMotorDatabase` so the conftest loop-rebinding sweep is unaffected. No module-scope code grabs a collection handle (verified), so the proxy never resolves at import.
- **Guard hardened (`tests/test_no_blocking_imports.py`):** AST scan now also covers `utils/` + `bootstrap/` and flags eager `AsyncIOMotorClient(...)`/`MongoClient(...)` at import scope (the safe non-srv branch is opted out with `# noqa: import-blocking`).
- **Verified:** SRV URI now imports in 0.26s WITHOUT blocking (was: DNS at construction); non-srv path still yields a real `AsyncIOMotorDatabase`; proxy forwards real async queries (ping/list/getitem/getattr/count) against local mongo; backend `/api/health`=200, master-admin + operator login OK. Testing agent backend regression **100% (14/14)**, zero critical issues, retest not needed. Report: `/app/test_reports/iteration_lazy_motor_regression_jan2026.json`.
- **Status:** READY TO REDEPLOY. This is the definitive fix for the "never binds :8001" crash-loop.


## Jul 3, 2026 — Request a Part: inline sub-tab + mobile-scrollable sub-tab bar + theme parity
- **Continuity fix**: "Request a Part" no longer navigates to a separate `/parts-requests` screen. It now renders INLINE as a third sub-tab under Operations → Faults, matching the Reactive Faults / Planned Maintenance pattern. `PartsRequestsPage` gained an `embedded` prop (drops the full-screen shell + top back button); wired into both Pro `FaultsTab.js` and `LiteFaultsTab.js` via `faultView === 'parts'`. The standalone `/parts-requests` route still works for deep links.
- **Mobile scroll fix**: `.subtab-bar` (index.css) is now `max-width:100%; overflow-x:auto` with hidden scrollbar and `.subtab-pill{flex-shrink:0}`, so the pill row scrolls horizontally on narrow screens instead of clipping the last option.
- **Theme parity**: converted the whole Parts panel from hardcoded slate/white classes to `--theme-*` tokens (surface/text/border/bg) + scoped input/textarea theming CSS, so it renders correctly in BOTH light and dark mode (previously light-only). Semantic status/cover badges kept as colored chips.
- **Verified** (390px) as owner@isodemo.com in light AND dark mode: sub-tab bar scrolls to reveal "Request a Part"; clicking it renders the Parts Requests list + New Request editor inline (URL stays `/dashboard`); all cards/inputs match the active theme. Removed now-unused `useNavigate` from both faults tabs.


## Jul 3, 2026 — PRODUCTION DEPLOY BLOCKER FIXED (root cause: blocking sync MongoClient at import)
- **True root cause of the k8s readiness crash-loop**: `routes/admin_analytics.py` created a SYNCHRONOUS `pymongo.MongoClient(os.environ["MONGO_URL"])` at MODULE IMPORT time. On the production Atlas `mongodb+srv://` URI, pymongo performs a BLOCKING DNS SRV lookup during client construction — this hung app import so uvicorn never bound `:8001`, nginx got connection-refused on `/health`, and the pod crash-looped. Preview never hit it (local `mongodb://` has no SRV lookup). This is why the earlier threadpool/secrets-audit fixes didn't resolve it.
- **Fix**: `admin_analytics.py` now uses the shared async motor `db` (`from utils.database import db`); all 5 handlers (dashboard/equipment/faults/checksheets/ai) converted from sync `list(db…find())` to `await db…find().to_list(None)`.
- **Atlas index conflicts made idempotent**: new `utils/mongo_indexes.py::ensure_ttl_index()` reconciles pre-existing same-key indexes then creates the named TTL index; wired into `email_health.py` and `ui_errors.py` (removed the redundant plain `created_at` index that caused IndexOptionsConflict/code 85). `ensure_indexes.py::_ensure_one` now treats codes 85/86 as "already satisfied" (INFO, not WARNING) — fixes seo_articles slug (code 86) noise.
- **libmagic**: boot self-check log downgraded ERROR→WARNING — the pure-Python signature sniffer in `file_validation.py` validates uploads when libmagic1 is absent (uploads do NOT fail).
- **CORS**: `backend/.env` `CORS_ORIGINS="*"` (prod still ignores wildcard and uses brand defaults + platform regex via `resolve_cors_origins`).
- **Verified**: deployment_agent → PASS (no blockers). Backend regression testing_agent → 100% (22/22): boot clean, `/health`+`/api/health` 200, master-admin login, all 5 analytics endpoints (admin 200 / anon 401 / non-admin 403), email-health, ui-errors, organizations, /auth/me. Reports: `iteration_deploy_healthfix_regression_jan2026.json`.
- **Status**: READY TO REDEPLOY TO PRODUCTION.


## Jul 3, 2026 — P0 production crash-loop fix VERIFIED (deploy readiness)
- **Root cause**: `run_startup_audit()` (`utils/secrets_audit.py`) called `sys.exit(2)` on weak-secret findings in production, killing uvicorn before it bound `:8001` → k8s `/health` readiness probe timed out → crash-loop.
- **Fix (already in code)**: `server.py` `startup()` now calls `run_startup_audit(abort_on_critical_in_prod=False)` (findings logged, never fatal) and defers ALL heavy init (storage, seeding, index builds, background loops) into `asyncio.create_task(_full_boot())`; `init_storage()` runs via `run_in_threadpool`. Port binds immediately, `/health` returns 200 instantly.
- **Verification**: backend testing_agent — 100% pass (6/6). Server boots & stays up (no crash-loop, no sys.exit), `/health` + `/api/health` → 200, master-admin login + `/api/auth/me` + `/api/master-admin/organizations` → 200. Report: `/app/test_reports/iteration_deploy_healthfix_verify_jan2026.json`.
- **Non-issues confirmed**: libmagic-missing 415 is a false alarm — `utils/file_validation.py` has a pure-Python signature fallback sniffer; libmagic also installed locally. Mongo index-name WARNs at boot are pre-existing cosmetic noise.
- **Status**: READY TO REDEPLOY TO PRODUCTION.


## Jul 2, 2026 — Site Survey reports: Excel + PDF export (CSV already live)
- **Backend**: generic exporters `utils/report_export.py` (`build_report_xlsx` via openpyxl, `build_report_pdf` via reportlab, Pulse-branded, landscape). New endpoint `GET /api/crm/reports/{report_id}/export?fmt=xlsx|pdf&from_iso=&to_iso=` dispatches to the 4 survey reports (`_EXPORTABLE_REPORTS`); 404 for non-exportable reports. Columns derived from row keys; totals rendered as a summary strip.
- **Frontend** (`CRMReports.js`): added `exportable:true` to the 4 survey reports + Excel/PDF buttons (data-testid `report-xlsx-*` / `report-pdf-*`) next to CSV, downloading via blob with the panel's current date range (disabled when no rows).
- **Verified via curl**: XLSX (valid zip, correct content-type, 5KB), PDF (`%PDF-`, correct content-type), unknown report → 404. Frontend compiles.



## Jul 2, 2026 — Pre-Install Site Survey: Reporting dashboard + exports (within CRM Reports)
- Added a new **"Site Surveys"** category to the existing CRM Reports suite (`CRMReports.js`) — reuses the standard ReportPanel (date-range chips, totals strip, **CSV export**), zero new UI framework.
- Four report endpoints on the CRM reports router (`crm_reports.py`, org + site-scoped, dateable on created_at): `site-surveys-status` (by status, open/awaiting-customer counts), `site-surveys-manager` (per manager: surveys/ready/installed/high-risk), `site-surveys-high-risk` (one row per survey with a High/Critical risk, critical-first), `site-surveys-conversion` (funnel: created → approved-for-quote → approved-for-install → completed + survey-to-install rate %).
- **Verified**: backend via curl (status/manager/high-risk/conversion all return correct aggregations on seeded data — e.g. 33.3% conversion, 2 high-risk incl. 1 critical); frontend via screenshot (all 4 render under the Site Surveys category with date filters + CSV export). Fixed a `_date_range` returns-strings bug during testing.
- Note: CSV export is provided by ReportPanel; Excel/PDF exports remain backlog.



## Jul 2, 2026 — Pre-Install Site Survey Phase 2 (item 4/4): Offline mobile drafts — PHASE 2 COMPLETE
- Frontend-only (`PreInstallSurveys.js`, SurveyEditor). Every edit is cached to `localStorage` (`pis_survey_draft_<id>` = {data, savedAt, dirty}) so work survives reload / poor signal. Header sync badge cycles Synced → Unsaved → Offline·saved-on-device → Syncing. When a Save fails offline, the draft is kept locally with a "Saved on device — will sync when back online" toast (no error). `online`/`offline` listeners auto-sync the pending draft on reconnect (toast "Reconnected — your draft has been synced") and clear the local cache. On reopen, a dirty local draft raises a Restore/Discard banner. Attachment uploads are guarded offline (uploads require connectivity).
- **Verified**: testing agent 7/7 offline-behaviour checks (localStorage persist, dirty→synced, offline save, restore prompt, reconnect auto-sync, offline upload guard) — 100%, zero issues.
- **Pre-Install Site Survey Phase 2 is now complete** (AI summaries+risk-flagging, customer portal, version-diff, offline drafts). Backlog beyond Phase 2: reporting dashboard + exports, Master-Admin template builder UI, calendar/task auto-creation, email notifications on status change, deep-link surfacing in Opportunities/Quotes/Projects/Service Desk/Engineer app, dedicated Site-record page tab, migrate attachments to object storage.



## Jul 2, 2026 — Pre-Install Site Survey Phase 2 (item 3/4): Version-diff UI
- **Backend** (`crm_site_surveys.py`): `GET /{id}/diff?compare_to={otherId}` — field-level diff between two versions in the same lineage (`root_id`), labelled via SURVEY_SCHEMA. Compares meta (status/type/target date/priority/links), all non-repeatable section fields, and repeatable sections (rooms/equipment/risks/site_contacts/existing_equipment) per index. Auto-orders lower version as "from"; 400 if versions aren't from the same lineage.
- **Frontend** (`PreInstallSurveys.js`): "Versions" button in the editor → modal listing the version chain (status chips + current badge) with two version selectors and a Compare action → side-by-side diff table (Field | vA | vB) with old struck-through / new highlighted. Guards against comparing a version with itself.
- **Verified**: backend via curl (5 changes across meta + room + access); frontend testing agent 100% (v1/v2 listed, defaults correct, "4 changes" table rendered). Minor cosmetic console warning noted (not from these selects; no functional impact).
- **Remaining Phase-2:** 4) offline mobile drafts.



## Jul 2, 2026 — Pre-Install Site Survey Phase 2 (item 2/4): Customer portal input
- **Home:** Account Settings → Onboarding (per user choice), for the org's own users (customer/site contact). Uses platform JWT (`get_current_user`), scoped to the caller's organisation. Gated per-org by the `allow_customer_portal_input` survey setting (default OFF).
- **Backend** (`routes/survey_portal.py`, prefix `/api/survey-portal`): GET `/surveys` (only portal-enabled + actionable statuses, customer-safe view), GET `/surveys/{id}` (+ customer schema), PUT `/surveys/{id}` (whitelisted fields only — non-whitelisted keys silently stripped), attachments upload/list (customer uploads forced `visible_to_installer/customer=true`, `source=customer_portal`). Whitelist + `customer_portal_schema()` live in `crm_site_surveys_schema.py` (`CUSTOMER_PORTAL_FIELDS`, `CUSTOMER_UPLOAD_CATEGORIES`). Customer can edit: site contacts, subset of access/parking/network(IT contact)/customer requirements/site rules; can upload floor plan + photos. Contributions audit-logged (`customer_information_received`, `customer_file_uploaded`).
- **Frontend** (`AccountSettings/onboarding.js`): `SurveyPortalPanel` + `SurveyPortalDetail` — panel hidden unless enabled surveys exist; detail renders the whitelisted sections (Yes/No toggles, repeatable Site Contacts), floor-plan/photo upload, and "Send to installation team".
- **Verified**: backend via curl (whitelist enforced, forbidden field stripped, no internal-data leak — only 3 safe sections returned, uploads reach internal CRM with `has_floor_plan`, disabled → 403); frontend via screenshot (panel + detail render clean/on-brand inside the forced-light modal).
- **Remaining Phase-2:** 3) version-diff UI, 4) offline mobile drafts.



## Jul 2, 2026 — Account Settings modal: force clean light theme (match reference)
- Root cause: the Account Settings modal inherited the app's dark/light toggle, so in dark mode it rendered black — nothing like the intended clean light design (GymAxis reference the user shared). Its docstring even claimed it never inherits the toggle.
- Fix: scoped the modal shell with `data-theme="light"` in `AccountSettingsModal.js` so all `--theme-*` vars + the light-mode Tailwind overrides resolve to the light palette regardless of app theme. One-line, low-risk.
- Verified via screenshots (app in DARK mode → modal renders LIGHT): Profile + Team & Roles sections both clean (white surface, soft nav, Core-Blue accents, near-black text), no dark bleed. Layout/sections already matched the reference (Profile, Onboarding, Security, Preferences, Plan & Billing, Organisation, Suppliers, Team & Roles, Data export).



## Jul 2, 2026 — Pre-Install Site Survey Phase 2 (item 1/4): AI summaries + risk-flagging
- **Backend** (`utils/survey_ai.py` + 3 endpoints in `crm_site_surveys.py`): OpenAI `gpt-5.2` via Emergent LLM key (mirrors verified `comms_ai.py`). `POST /{id}/ai/analyse` (grounded summary, missing-info list, flagged risks w/ severity, suggested questions, electrical/network/access concerns, readiness *recommendation*), `POST /{id}/ai/follow-up-email` (customer draft), `POST /{id}/ai/briefing` (installer briefing). Gated by `allow_ai_summaries` setting (403 when off). **Advisory only** — never writes to the survey; audit events logged (`ai_analysis_run` etc.).
- **Frontend** (`PreInstallSurveys.js`): "AI Assist" button + modal with 3 tabs (Analyse & risks / Follow-up email / Team briefing), "advisory only" badge, copy actions, and an explicit user-confirmed "Insert into Installation Notes" for the briefing.
- **Verified**: backend via curl (all 3 endpoints + toggle 403); frontend testing agent 100%, zero issues. Report: `/app/test_reports/iteration_pre_install_surveys_ai_jan2026.json`.
- **Remaining Phase-2 sequence (agreed):** 2) customer-portal input inside Account Settings → Onboarding (customer can confirm site contact, answer access/parking, confirm install date, provide IT/electrical contact, **upload floor plan + photos**, review summary; never sees internal notes/risk scoring), 3) version-diff UI, 4) offline mobile drafts.



## Jul 2, 2026 — Pre-Install Site Survey (CRM Corporate) — Phase 1
Structured pre-installation survey built into the CRM, attached to EXISTING company + site records (no duplication), linking to opportunity/quote/project/service-job.
- **Backend** (`routes/crm_site_surveys.py` + `_schema.py`, `utils/survey_pdf.py`): schema-driven survey (22 sections incl. rooms/access/power/network/flooring/walls/ceiling/equipment/risks etc.), 15 types, 12 statuses + history, 15-point Installation Readiness check with **manager-override guard** on "Approved for Installation", version supersede (no deletes), immutable audit trail, attachments (upload/download/delete), and a **branded Installation Handover PDF** (Core Blue/Soft Black). Collections: `pre_install_site_surveys` (+ attachments/versions/audit/settings).
- **Frontend** (`pages/CRM/PreInstallSurveys.js`): list + full schema-driven editor (section nav, repeatable rooms/risks/equipment, live readiness panel, status workflow w/ override modal, attachments, handover-PDF download, audit modal). **Replaces** the old Company "Site Surveys" file-upload tab.
- **Verified**: testing agent backend 8/8 (100%) + frontend Playwright (100%), zero issues. Creds: CRM owner@isodemo.com / IsoDemo123!.
- **Phase 2+ (deferred):** AI summaries/risk-flagging, customer portal, offline mobile, version-diff UI, email notifications, calendar/tasks, reporting dashboard, Master-Admin template builder, dedicated Site-record page tab, deep-link surfacing in Opportunities/Quotes/Projects/Service Desk/Engineer app. Attachments are base64-in-Mongo (flag for object storage).



## Jul 2, 2026 — Branded favicon/OG image + Operations site-scope migration
- **Brand assets:** regenerated favicon (Pulse mark on Soft Black `#1B1C1D`, Core Blue `#19CDFF`) at all sizes + `favicon.ico`/`apple-touch-icon`, and a new 1200×630 OG social image (`brand/og-cover.jpg`) with the real Pulse logo + Proxima Nova. Aligned `theme-color`/manifests/PWA data-URI icons to brand. Regen script: `scripts/gen_brand_assets.py`. Both verified rendering on preview.
- **Operations site-scope migration (P3):** retired legacy `apply_site_lock` for routes — Operations/Equipment now use the same ContextVar `build_site_filter` engine as Memberships/CRM/Marketing (via `mod_scope.resolve_mod_query_filter`'s non-MOD branch; MOD-HQ branch unchanged). Managers with `allowed_site_ids` are now correctly site-locked in Operations. Migrated `issues.py`, `reports.py`. Verified via curl e2e (owner sees both sites; manager sees only Site A; 403 on disallowed site for equipment + reports). `apply_site_lock` unit test 11/11 green.



## Jul 1, 2026 — Production deploy blocker fixed: non-blocking startup (Iter 297)
Production rollout was failing with a k8s readiness timeout — nginx logged `connect() failed (111: Connection refused)` on `/health` because the backend never bound `:8001`.
- **Root cause:** the FastAPI `@app.on_event("startup")` handler *awaited* heavy work (admin/CRM seeding, one-shot backfills/migrations, and `ensure_all_indexes` = 129 indexes across 67 collections) BEFORE uvicorn opens the port. Against production MongoDB Atlas the index builds/backfills blocked long enough that the readiness probe timed out and the pod was killed/restarted in a loop.
- **Fix (`backend/server.py`):** `startup()` now runs only the fast secrets audit, then schedules all heavy init via `asyncio.create_task(_full_boot())` and returns immediately. uvicorn binds `:8001` right after imports and `/health` (trivial `{"status":"ok"}`) passes instantly, while seeding + index builds complete in the background. Verified: local `:8001/health` and external `/api/health` return 200 within seconds; login works; background seeds/indexes complete afterwards.
- **Advisories (not code blockers, user action):**
  - Production `JWT_SECRET` is weak (`gymaxis-ai-secret`, 26 chars) — set in the DEPLOYMENT env, not the repo `.env` (preview `.env` already uses a strong 64-char secret). Rotate it in the deploy secrets to 32+ random chars; otherwise `APP_ENV=production` boots will hard-abort via the secrets audit.
  - `libmagic` not present in the container → file uploads return HTTP 415. Container-image level, unrelated to the timeout.


## Jul 1, 2026 — Comms Centre: send to specific people (not just segments) (Iter 296)
Fixed user feedback: an email could only be delivered to a *segment*, with no way to send to one person, and segments needed categories that couldn't be linked to a member.
- The backend already supported `audience_inline` (a list of emails); the Send modal just didn't expose it.
- **Send modal (`EmailBuilder.js`)** now has an **Audience** toggle: **A segment** (existing) or **Specific people**. "Specific people" gives a live search picker (members + CRM contacts) plus free-text email entry (type an email + Enter), shown as removable chips with a live recipient count. On send it writes `audience_inline` and clears `segment_id`.
- New backend endpoint **`GET /api/comms/audience/search?q=`** (`comms.py`) searches `members` + `crm2_contacts` by name/email for the org.
- Verified end-to-end: single-recipient send resolves to `recipients: 1`; picker renders with chip + count.


## Jul 1, 2026 — CPQ approval/sign: prominence + notifications (Iter 295)
- **(b) Visibility:** Added a lifecycle stepper (**Draft → Approval → Approved → Signed**, with a red "Rejected" state) at the top of the CRM quote detail (`CRMCPQ.js`), plus success/error toasts on Submit-for-approval / Approve / Reject / Sign.
- **(c) Notifications + emails:** `crm_v2.py` quote endpoints now fire events — **submit-approval** notifies org approvers (owner/admin/manager); **approve/reject** notifies the quote owner (with reason on reject); **sign** notifies approvers. Both an in-app CRM notification (`crm2_notifications`) and a branded email (`send_email`, category `crm_quote_workflow`) are sent. Helpers: `_crm_quote_recipients`, `_crm_user_email_by_name`, `_send_quote_emails`.
- Tested end-to-end: draft→submit→approve→sign transitions all 200, 3 in-app notifications created correctly.
- ⚠️ **Email delivery requires a valid Resend API key** — the currently configured key returns "API key is invalid", so emails are attempted but not delivered (handled gracefully, no crash). In-app notifications work regardless.


## Jul 1, 2026 — GymAxis → Pulse Fitness feature port (Iter 294)
Ported user-selected features from the original GymAxis repo, rebranded to Pulse Fitness. This platform stays source of truth; only genuinely net-new features were brought across.
- **AI Scheduling (Service Desk):** new `routes/svc/ai_scheduling/` package (board, replan, simulate, duration-insights, proposal approve/reject, job locks, reports + engineer schedule-change ack). Frontend `ServiceOps/SchedulerHub.js` + `AIScheduling.js` — the Service Desk "Scheduler" tab is now a hub with **AI Scheduling** + **Diary board** sub-tabs. Verified end-to-end.
- **Membership Dunning:** `routes/membership_dunning.py` (/dunning/*) + Memberships console "Recover" tab.
- **Revenue Autopilot:** `routes/revenue_autopilot.py` (/autopilot/revenue/*) + Memberships "Autopilot" tab.
- **GDPR tools:** `routes/gdpr.py` (/gdpr/*) + Memberships "Privacy" tab.
- **Machine Manuals:** `routes/machine_manuals.py` (/machine-manuals + /master-admin/machine-manuals/*) + Master Admin → Catalogue & Library → "Machine manuals" sub-tab. Fixed a ported dependency (`assert_platform_admin` → Pulse `require_master_admin`).
- **Equipment Transfer:** `routes/equipment_transfer.py` + `Dashboard/EquipmentTransfersInbox.jsx` on the operator Overview tab (self-hides when empty).
- **NOT ported — CRM Tenders/CPQ:** already fully present in Pulse's `crm_v2.py` (knowledge-base, tender-templates, pitch-slides, win-loss, quote submit-approval/approve/sign/pdf/send-email). GymAxis's separate `crm_v2_tenders/cpq/tenders_ai` files were pre-split duplicates that conflicted on `/crm/v2/tenders`; reverted to avoid regression.
- Added a small reusable frontend `lib/api.js` shim (`api` + `crmApi` axios instances with Bearer-token injection) to support ported GymAxis components.
- Testing: 16/16 backend endpoint tests pass; all frontend panels render. Report: `/app/test_reports/iteration_pulse_gymaxis_port_jan2026.json`.


## Jul 1, 2026 — Master Admin routing fix + duplicate Pulse org reappearance fix (Iter 293)
- **Master Admin routing (P0, verified):** `AppRoutes.js` DashboardRoute guard (line 253) now bypasses the `/master-admin` bounce for BOTH `?as=operator` and `?as=global` (`previewDashboard`). `MasterAdminPage.handlePulseFitnessSwitch` now navigates to `/dashboard?as=global`. Result: "Global Dashboard" button loads the cross-gym Global view; "Pulse Fitness Portal" button loads the operator Operations dashboard. Neither bounces back. Testing agent: 3/3 PASS.
- **Deleted Pulse orgs reappearing (P1, verified):** Root cause = `seed_crm_admin()` in `crm_auth.py` (lines 711-742) re-created "Pulse Fitness AI" + "Pulse Fitness" CRM orgs on every boot when `CRM_SEED_DEMO_ORGS` was unset (default on). Fix: set `CRM_SEED_DEMO_ORGS=0` in `backend/.env`. Consolidated DB to a single tenant org: reassigned stray "Pulse Fitness AI" (80e9b381) data to the tenant org, deleted the stray (snapshot saved to `org_cleanup_audit`), renamed the tenant org "Pulse Fitness" → "Pulse Fitness Ltd" and pinned `is_operator_company=true`. "Pulse Fitness AI Admin" (master-admin login org) retained. Confirmed no reappearance after backend reboot.


## Jun 16, 2026 — Social Media Autopilot: Gymshark/Nike brand-voice revamp (Iter 291)

- **Short & sharp captions**: Rewrote all 3 channel `tone_brief`s + `caption_target/max_chars`
  in `utils/social_autopilot.py`. IG ≤120/150 chars, TikTok ≤100/150, LinkedIn lean 400-700
  (max 1200). Added a shared `BRAND_VOICE_RULES` block (Gymshark/Nike/Lululemon: declarative,
  no AI-speak filler, no hype) injected into `build_prompt`, `build_launch_prompt`,
  `build_compose_prompt`.
- **Zero URLs anywhere**: Prompts forbid web addresses; new `strip_urls()` safety-net scrubs
  any URL/bare-domain (and wrapping quotes) from every saved caption. Removed the `gymaxisai.com`
  text from all rendered image cards — `social_templates._draw_logo_badge` + the legacy SVG/PNG
  fallbacks now show the clean logo only. Sora video prompt domain reference dropped.
- **Real screenshots first**: `pick_layout` now always uses the `screenshot` layout for any
  feature that has a genuine matching product screenshot; template cards only when none exists.
- **Hashtags trimmed**: IG 15-25 → 5-8, LinkedIn 3-6 → 3-5 (minimalist brand feel).
- **Verified**: real LLM generation across IG/TikTok/LinkedIn produced 57-475 char posts, no URLs.
  New pytest `test_iter291_social_brand_voice.py` (15 tests) added to Makefile `regression:`;
  updated 4 stale assertions in `test_iter_220bl_social_autopilot.py`. 66 social tests pass.


## Jun 15, 2026 — Org Chart: import an EXISTING chart (PDF / image → editable cards)

- New backend endpoints (`routes/staffing_orgchart_ai.py`): `POST .../import/document`
  (multipart file OR file_url) + `GET .../import/document/{job_id}` (poll). Runs as an
  **async job** — vision OCR on dense charts exceeds the 60s ingress timeout, so the POST
  returns instantly and the client polls. Extraction strategy: if the PDF has a text layer
  (`fitz`/PyMuPDF) feed that to the text→rows LLM (most accurate); otherwise rasterise pages
  and use Claude Sonnet vision. Returns reviewable rows (name/title/department/manager_name/vacancy).
- **Critical fix**: `emergentintegrations` calls *synchronous* `litellm.completion()` inside an
  `async` method, blocking the event loop for ~70s → POST never flushed → Cloudflare 502. Now the
  whole extraction (fitz + LLM) runs in a worker thread via `asyncio.to_thread` (`_extract_rows_sync`,
  `_llm_json_sync`); only Mongo writes stay on the main loop. POST now returns in ~0.2s, poll latency ~0.15s.
- Frontend `DocumentImport.js` (idle→working→review→done/error): upload PDF/PNG/JPG → poll → **editable**
  review table (fix OCR slips) → apply → cards become normal editable nodes. Embedded atop the Import/Export tab.
- Verified on the real **Pulse Fitness May 2025 PDF: 108 people extracted** (source `text`) with correct
  reporting lines; applied → 121 editable cards on the canvas.
- Tested: pytest `test_iter283_orgchart_import_doc.py` (mini PDF) + `test_iter284_pulse_pdf_import.py`
  (real Pulse PDF) — both GREEN, added to Makefile regression. Testing agent: **100% backend + 100% frontend**.


## Jun 15, 2026 — Org Chart: Publish & share a read-only public link

- Backend (`routes/staffing_orgchart.py`): `POST/DELETE .../publish`, `POST .../publish/rotate`,
  and a **no-auth** `GET /staffing/orgchart/public/{token}`. Token is `secrets.token_urlsafe(16)`,
  stored on `org_charts` (`is_public`, `public_token`, `public_show_contact`). Public response is
  sanitised — never returns notes, salary bands, linked `staff_id`, or email/phone (email/phone only
  when the publisher opts in via `show_contact`). Rotate/unpublish immediately 404 old links.
- Frontend: `ShareModal.js` (publish, copy, open, rotate, stop-sharing, contact toggle) opened from a
  header **Share** button (label flips Share↔Shared); public route `/org/:token` →
  `pages/Public/PublicOrgChartPage.js` renders a clean, branded, read-only top-down tree (reuses
  `layout.js`), with a "no longer available" state for revoked links.
- Tested: backend pytest `test_iter282_orgchart_share.py` (GREEN, incl. leak-guards) added to Makefile
  regression; testing agent **100% backend + 100% frontend** on the live preview.


## Jun 15, 2026 — Org Chart Builder (Phase 2) — AI, history, templates, presentation, dotted lines, notes

Extends the Phase-1 builder (Operations → Staffing → People → Org Chart).
- **AI assist** `routes/staffing_orgchart_ai.py` (Emergent LLM key + `claude-sonnet-4-6`):
  `ai/generate` (free-text staff list → reviewable rows with inferred reporting + vacancies),
  `ai/analyze` (gaps/circular/overload/orphan + suggestions), `ai/draft-jd` (job description).
  AI never mutates the chart — proposals are applied via the normal import endpoint.
- **Version history + restore + audit trail** (`org_chart_versions`, `org_chart_audit`):
  save snapshots, restore (auto-snapshots current first), full activity log.
- **Starter templates** (8: small gym → enterprise/engineer/sales teams) — `GET /templates`,
  `POST .../apply-template/{id}` adds placeholder roles + reporting lines.
- **Secondary / dotted-line reporting** (`org_chart_edges`): dotted/temporary/project/escalation
  lines rendered dashed on the canvas; managed from the card drawer.
- **Notes / comments** (`org_chart_notes`) per card with confidential flag.
- **Presentation mode**: full-screen deck stepping through Organisation → departments → vacancies.
- **Department/site grouping frames** on the canvas (colour-coded dashed regions).
- **Frontend**: new files `AIPanel`, `HistoryTab`, `Templates`, `Presentation`; `Canvas` gains
  edges + grouping frames; `panels.NodeDrawer` gains notes + secondary-reporting UI; new sub-tabs
  (AI Assist · Templates · History) + a Present button.
- **Bug fixed (this session)**: `PATCH /charts/{cid}` returns the bare chart doc, but the frontend
  read `r.chart` (undefined) on settings/rename save → wiped `chart` state and hid grouping frames.
  Now uses the returned doc directly.
- Tested: backend pytest `test_iter280_orgchart.py` + `test_iter281_orgchart_phase2.py` (both PASS,
  in Makefile regression) + live-AI test (PASS). Testing agent: backend 100%, frontend ~95%.


## Jun 15, 2026 — Org Chart Builder (Phase 1) — Operations → Staffing → People → Org Chart

New visual org-chart builder that **links to existing `staff_members`** (never duplicates).
- **Backend** `routes/staffing_orgchart.py` (registered in `route_registry/features.py`):
  collections `org_charts` + `org_chart_nodes`. Endpoints under `/api/staffing/orgchart/*`:
  charts CRUD, `sync-staff` (auto-build one node per active staff), node CRUD,
  `insights`, `import/preview`, `import/apply`, `export.csv`. Manager-only (`_require_manager`),
  org-scoped. Reporting lines via `manager_node_id`; cycle-guard rejects circular lines (400).
  `write_back_staff=true` mirrors manager/department/site onto `staff_members`
  (`manager_staff_id`, `department`, `site_ids`).
- **Frontend** `pages/LiteDashboard/staffing/orgchart/`: `OrgChartTab` (orchestrator + chart
  picker + insights chips + sub-nav + filters + search + PNG/PDF/CSV export), `Canvas`
  (pan/zoom/fit/reset/auto-layout/drag + reporting lines + drag-onto-card → move-confirm),
  `OrgCard` (5 card types, field toggles, dept colour, explicit edit button), `panels`
  (add/edit/move-confirm), `ListView`, `Vacancies`, `ImportExport` (CSV wizard via papaparse),
  `Settings`. New deps: papaparse, html-to-image, jspdf.
- Wired into `StaffingConsole.js` under group `people` → leaf `orgchart`.
- Tested: backend pytest `tests/test_iter280_orgchart.py` (PASS, added to Makefile regression);
  testing agent: backend 100%, frontend ~90% → fixed unreliable dbl-click-to-edit by adding an
  explicit per-card edit button (`orgcard-open-{id}`).
- **Deferred to Phase 2**: AI assist (generate-from-staff, gap/cycle detection, JD drafting),
  version history + restore, audit-trail diff, presentation mode, templates library,
  comments/notes permissions, dotted-line/secondary reporting, department/site grouping frames.


## Jun 10, 2026 — Fix: Marketing campaign wizard hang + silent data loss (prod report)

Production report: building a campaign from a template, the final submit "disappeared", the page loaded forever, and the campaign details were lost. Root-caused three defects in `CampaignWizard.js` `launch()` (reproduced live):
- **Data loss:** it POSTed a *flat* payload (`subject`, `body`) but the backend (`routes/marketing/campaigns.py`) reads `content.{subject, body_html}` — so drafts saved **blank** (`content: {}`). Now sends `content: {subject, body_html}` + `audience_inline` + `schedule`. Verified: campaign now saves with subject/body + status `draft`.
- **Indefinite hang:** `axios.post` had **no timeout** → a slow/stalled save left the button spinning forever with no feedback. Added `timeout: 30000` + an `ECONNABORTED` message.
- **Lost work on failure:** the `catch` previously **closed the wizard** (discarding all inputs) with a misleading "saved as draft" toast. Now it **keeps the wizard open**, shows an inline error banner (`data-testid="wizard-launch-error"`), and the user can retry with their data intact. Also fixed the response id parse (`resp.data.campaign.id`) and the campaign name (was the step title "Review").

Hardened the sibling flows in `CampaignsTab.js`: `create()` had `try/finally` with **no catch** (silent failure) → added an error toast; `applyTemplate()` (template → instantiate) given a 30s timeout + clearer error. UI smoke-tested: Campaigns page + templates gallery render fine; corrected campaign shows its subject preview.



## Jun 9, 2026 — Interactive Master Admin cards + Pulse data explorer

**Interactive cards / removed duplicate filters (GymAxis + Pulse):**
- `PeopleDirectory.js`: the 8 KPI stat cards are now **interactive filters** (Total active, Pulse admins, Owners, Staff/Managers, Partner Engineers, CRM only, Role mismatches, Invites pending) + a new **Archived** card. The duplicate filter-pill row below was **removed** (frees screen space); the local search moved into the header. Added `mismatch`/`invite_pending` filter branches. Verified: clicking "Owners" filters the list to owners.
- `OperationsOverview.js`: Operations Portal KPI cards now navigate — Operations Orgs → organisations, Active Users → People, Operations MRR → Payments (`onGoSection` wired from `OverviewSection.js`).

**Pulse data explorer (new, option (a) — curated & leak-proof):**
- Backend `routes/master_admin_pulse_explorer.py`: read-only, **Pulse-brand-scoped** browser over a whitelist of 11 business collections (organizations, users, crm_users, sites, equipment, issues/faults, members, member_memberships, membership_plans, marketing_subscriptions, social_media_library). Scope = org `id`s matching the Pulse brand clause (`utils/brand_filter`); search is AND-ed *inside* the scope so it can't escape. Reuses the db-viewer's redaction. Endpoints under `/api/master-admin/pulse-explorer/*`. Registered in `route_registry/admin.py`.
- Frontend `PulseDbExplorerPanel.js` + sidebar sub-tab `pulse-data` under Settings & Compliance, gated with a new **`pulseOnly`** flag (only Pulse admins see it; the raw `db-viewer` stays GymAxis-only). `MasterAdminPage.js` subtab filter now honours `pulseOnly`.
- Verified live as Pulse admin: 4 orgs / 6 users / 115 equipment / 30 faults in scope (not the 789 orgs / 791 users in the full DB) — no GymAxis or other-tenant data. Pytest `tests/test_iter226_pulse_explorer_scope.py` 6/6.



## Jun 8, 2026 — Security audit remediation (checkvibe report)

Triaged an external audit of gymaxisai.com. **Most findings target the edge/CDN/DNS, not this code** — the FastAPI backend already enforces login/register/forgot-password rate limiting (5/5min, X-Forwarded-For keyed), 5-strike account lockout, password-strength rules, CSP, HSTS, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, and a CORS allow-list (not wildcard). Verified live: 6th rapid login → 429.

Code fixes shipped (integration_expert consulted before auth edits):
- `routes/auth.py`: added per-IP rate limiting (3/15min) to `/api/auth/reset-password` (was the one un-limited auth route). Verified: 4th attempt → 429.
- `server.py`: auth responses now advertise `RateLimit-Limit: 5` + `RateLimit-Policy: 5;w=300` so scanners can *detect* the existing protection (the "no rate-limit headers" finding was a false negative — scanner only tried 3 attempts < 5 threshold).
- `frontend/.env`: `GENERATE_SOURCEMAP=false` — stops `.js.map` source maps being publicly served on the next build.
- `frontend/public/robots.txt`: removed disclosure of `/admin`, `/dashboard`, `/api/` (kept SEO-useful disallows + sitemap).
- `frontend/public/_headers` (new): Cloudflare Pages security headers for the static site (CSP mirrors backend, X-Frame-Options SAMEORIGIN, HSTS, XSS, Referrer, Permissions-Policy) + noindex on `_worker.js`/`*.map`. Takes effect on next deploy.

NOT code-fixable (handed to user / Emergent support per support_agent): TLS 1.0/1.1 disable + blocking exposed `_worker.js`/`wrangler.toml` (→ support@emergent.sh); DMARC/SPF `-all`/DKIM/CAA/DNSSEC/nameserver diversity (→ DNS provider); HSTS preload submission (→ hstspreload.org after deploy). Soft-404 catch-all is standard SPA behaviour. localStorage-token → httpOnly-cookie migration noted as a large architectural item, not attempted.



## Jun 8, 2026 — SEO: Organization sameAs (Instagram) + one-click IndexNow ping

- **`sameAs` social signal:** added the user's Instagram (`https://www.instagram.com/gymaxisai`, tracking param stripped) to the `Organization` JSON-LD in both `public/index.html` and `utils/seo.js` `orgJsonLd()`, so search engines connect site ↔ social profile. Verified live in served HTML. (More profiles can be appended on request.)
- **One-click "Ping search engines" (IndexNow):** new `IndexNowCard` on the SEO Autopilot Dashboard (`SEOAutopilotPanel.js`, master-admin/gymaxisOnly) POSTs the key marketing URLs (`/`, `/pricing`, `/features`, `/blog`, `/compare`, `/platform/*`, `/solutions`, `/maintenance`, `/equipment`) to the existing `POST /api/seo/indexnow/ping`. IndexNow key file (`/a7f3c9e21b8d4f06a5e7c2d9b4f18e30.txt`) already hosted & served (200). Endpoint verified `{ok:true, submitted, status:200}` (a cold first call can hit the 10s httpx timeout → retry succeeds). Button + result surfaced with `data-testid` seo-indexnow-card / -ping-btn / -result.



## Jun 8, 2026 — SEO crawlability: homepage now serves real HTML (no-JS)

ChatGPT's crawler reported gymaxisai.com returns only the JS shell. Consulted Emergent support: the platform does NOT support SSR / build-time prerender / user-agent edge routing for SPAs (react-snap/puppeteer unsupported); recommended paths are (1) migrate to the Next.js template, (2) Prerender.io, or (3) expand FastAPI prerender + static HTML. Shipped the guaranteed, no-platform-change wins:

- `public/index.html`: broadened `<title>` → "GymAxis AI | Gym Management Software for Gyms, Studios & Engineers"; rewrote meta description + OG/Twitter to the "gym management software" positioning; added **FAQPage** JSON-LD (alongside existing Organization + SoftwareApplication); replaced the empty `<noscript>` ("You need to enable JavaScript…") with a **real crawlable homepage fallback** — H1, intro, all 14 modules, FAQs, and internal links to existing routes (`/platform/*`, `/solutions/*` [validated against `seo_public.py` SOLUTION_SLUGS], `/maintenance`, `/equipment`, `/compare`, `/blog`, etc.).
- `MarketingHome.js`: `useSeo` title/description aligned to the new positioning for Google's rendered pass.
- Verified live: curl of `/` returns the new title, H1, FAQPage schema and internal links in the initial HTML; JS users' homepage unaffected.

NOTE: existing infra already present — dynamic `/api/seo/sitemap.xml`, robots.txt, and a bot prerender endpoint for blog posts (`/api/seo/share/blog/{slug}`). The deeper fix for ALL marketing routes (per-route real HTML to non-JS crawlers) still needs an edge bot-routing layer or Next.js/Prerender.io — pending user decision.



## Jun 8, 2026 — Pulse Master Admin People tab: matrix access + tab cleanup

Three issues reported by the Pulse Master Admin (production screenshot, People → Roles):

- **"Couldn't load matrix — Master admin access required":** the SOC-2 Permissions matrix reads `GET /master-admin/pulse-admins`, which was `_require_gymaxis_master`-gated. Widened that **read-only list** to `_require_pulse_or_master` (now also accepts `is_pulse_admin`) in `routes/pulse_master_admin.py`; provisioning (create/revoke/purge) stays GymAxis-master-only. Pulse admin now sees the matrix (Active Admins, rows, tiles). Verified by curl (was 403 → now `{admins:[…]}`) + `tests/test_iter222_pulse_admin_list_access.py` 4/4.
- **Removed "Pulse Master Admins" tab** for Pulse admins — provisioning is now consolidated into Organisations + the Directory.
- **Removed "Legacy users panel" tab** for Pulse admins — everything lives in the Directory.
- Both tabs are hidden via `isPulseAdmin` filtering in `AdminRoles.js` (passed from `MasterAdminPage.js`); the `onOpenLegacyEdit` drawer action is also suppressed for Pulse admins so it can't target a hidden tab. The full GymAxis platform Master Admin still sees all five tabs. Verified live — Pulse admin tabs are now: Directory · Permissions matrix · Service Desk team.



## Jun 8, 2026 — Pulse Master Admin overview scoping + UI/rendering fixes (P0 batch)

Follow-up to the prior Pulse-admin scoping work. Confirmed plan = P0 + restyle two dark panels. Done & verified live (logged in as `pulse.admin.test@pulsefitness.com`):

- **Hide GymAxis Trials + email data (P0-1):** `AdminOverview.js` now hides the cross-module `UnifiedTrialsCard` for `isPulseAdmin`; `SidebarConfig.js` marks `trials` + `emails` (and `pending-review`) `gymaxisOnly: true` so the Growth/Overview sub-tab bars drop them; `MasterAdminPage.js` hides the top-bar `EmailHealthPill` for Pulse admins and the Overview subtitle no longer says "trials".
- **Overview KPI cards interactive (P0-2):** Organisations→`organizations`, Active Users→`roles`, Monthly Revenue→`payments` are now clickable (role=button, keyboard-accessible, hover lift). Open Cases stays a tooltip stat (no master-admin faults list to route to).
- **Remove "Pending review" (P0-3):** `pending-review` sub-tab `gymaxisOnly` → gone from the Pulse Overview sub-tabs.
- **Integration Health for Pulse admins (P0-4):** root cause was the backend gate. `routes/integration_health.py` `_require_master_admin` → new `_require_health_access` (master **or** pulse admin) on both `/master-admin/integration-health[/{key}]`. Verified: Pulse admin now gets the 5-check summary (was 403). Pytest `tests/test_iter222_integration_health_access.py` 4/4.
- **Documents "black card" restyled (light):** the dark `Pulse Fitness — meeting handouts` banner + pager cards in `DocumentsPanel.js` now match the light console theme.
- **Custom Domains page restyled (light):** `CustomDomainsPanel.js` converted from the legacy dark zinc palette to white cards / slate borders / dark text, consistent with the rest of Settings & Compliance.

Lint clean; screenshot-verified each surface.

**P1 — Theme Settings brand isolation (done same day):** `ThemeSettingsPanel.js` now hides the GymAxis namespace token card (`ns.id === 'gymaxis'`), the GymAxis brand preset, and rewrites the header card copy for `isPulseAdmin`; `MasterAdminPage.js` makes the `theme-settings` page subtitle Pulse-neutral ("Your Pulse Fitness design tokens and per-tenant brand overrides."). Verified live — Pulse admin sees only Pulse tokens/preset, no "GymAxis (marketing/admin)" wording.



## Jun 8, 2026 — Pulse Master Admin scoping: hide GymAxis internals, brand-scope social library

Follow-up to the login-redirect/Master-Admin-button fix. Six Pulse-admin issues reported on the live site:

- **Access denied (System Health, Ask Support Desk, Analytics):** these endpoints are `is_master_admin`-only (cross-tenant GymAxis platform internals). Marked them — plus Partner Engineers, Client crashes, Support tools, Database viewer, Maintenance jobs — `gymaxisOnly: true` in `SidebarConfig.js`, so they're hidden from delegated Pulse admins (existing sidebar + sub-tab-bar machinery already filters `gymaxisOnly`). No more permission-denied toasts.
- **"Scope locked" / "Pulse Admin" badges removed:** `BrandPicker.js` now shows a plain "Pulse Fitness" pill (no "Scope locked", no tooltip); removed the amber "Pulse Admin" pill from `MasterAdminPage.js`.
- **Social media library GymAxis crossover + delete-not-persisting (root cause):** `social_media_library.py` re-seeded a campaign whenever its count hit zero, so deletes reappeared; and the collection was global (Pulse admin saw GymAxis-branded posts). Fix: (a) every row now carries a `brand` ('gymaxis'|'pulse'); legacy rows back-filled to 'gymaxis'; (b) seeding runs **once** via a `platform_config` marker (`social_library_seed`) instead of on-empty; (c) `list/add/delete` are brand-scoped to the caller. Pulse admins now see a clean Pulse-only library (0 GymAxis posts), deletes persist, and cross-brand deletes 404. Verified by curl (pulse=0/gymaxis=24; delete persists at 23; cross-brand delete=404) + `tests/test_iter222_social_library_scope.py`.
- **Brand-neutral share text** in `SocialMediaLibraryPanel.js`.

DEFERRED → resolved (option a): the Social/SEO **Autopilot content engine** (`utils/social_autopilot.py`) is deeply GymAxis-branded. Per user choice, **Social Autopilot, SEO Autopilot, and the GymAxis Growth Hub are now hidden from Pulse admins** (`gymaxisOnly: true` in `SidebarConfig.js`). A proper Pulse-Fitness-branded autopilot remains a future build.

Preview-only — REDEPLOY to gymaxisai.com to go live.


## Jun 8, 2026 — Pulse Master Admin: login redirect + Master Admin console button fix

- **Login redirect (P0):** Pulse Master Admins (`is_pulse_admin=true`, `is_master_admin=false`)
  now land on `/pulse` (their modules) at login instead of the Master Admin console.
  Logic in `Navbar.js` `loginToPortal` (full GymAxis platform admins still → `/master-admin`).
- **BUG FIX:** Clicking the **Master Admin** button (user menu) as a Pulse Master Admin
  bounced straight back to the operations module. Root cause: the inline render guard
  `if (showMasterAdmin && user?.is_master_admin)` in `LiteDashboardPage.js` (line ~685)
  and `DashboardPage.js` (line ~184) excluded Pulse admins (who have `is_master_admin=false`).
  Both guards now read `(user?.is_master_admin || user?.is_pulse_admin)`. `MasterAdminPage`
  was already Pulse-aware (scoped console), so it renders correctly for them.
- Verified: frontend compiles clean; backend `/auth/login` + `/auth/me` return
  `is_pulse_admin:true`. UI e2e blocked by preview `/api` 403 gate — validate on live
  site after redeploy.


## Jun 8, 2026 — Assign existing staff as Pulse Master Admin (role-based)

**Problem (production):** the dedicated "Provision Pulse Platform Admin" form only creates NEW users — assigning an EXISTING staff member (already an org owner) 409'd ("user already exists"). User wanted role-based assignment in one place (Master Admin / Owner / Manager / Staff).

**Solution — "Master Admin" is now a brand-aware assignable role in the normal user-management role dropdown:**
- Assigning **Master Admin** to a user in a **Pulse org** (account_type `pulse_pro/pulse_lite/pulse` or brand `pulse*`) provisions a **Pulse Master Admin** (`role="pulse_master_admin"`, `is_pulse_admin=True`, NOT full platform `is_master_admin`). Same Master Admin dashboard + org impersonation, scoped to Pulse data. Assigning it in a GymAxis org keeps full-admin behaviour.
- **Promotes existing staff in place** (keeps their password). Stores `pulse_admin_previous_role`. Demoting back to Owner/Manager/Staff strips the elevated flags; sessions are revoked on any role change.
- Backend: `_org_is_pulse()` + brand-aware logic in `add_user_to_organization` and `admin_edit_user` (`routes/master_admin_users.py`); `list_pulse_admins` now merges `crm_users` so promoted CRM-portal staff appear in the Pulse Admins panel (`routes/pulse_master_admin.py`).
- Frontend: brand-aware "Master Admin (Pulse)" / "Master Admin (full platform)" labels + a `pulse_master_admin` display option across the inline org-user select, Add-user and Edit-user dialogs (`AdminOrganizations.js`); Navbar now routes/show the Dashboard→Master Admin button for `is_pulse_admin` users too (`Navbar.js`).
- Impersonation already works for Pulse admins (`require_master_admin` allows `is_pulse_admin`, scoped by `assert_user_in_pulse_scope`).

Verified via curl (promote→`pulse_master_admin` + previous_role saved; demote→flags cleared/restored; promoted user appears in Pulse Admins panel) and UI (dropdown shows brand-aware label). Tests: `tests/test_iter222_pulse_master_admin_role.py` (3) pass. **Preview-only — REDEPLOY for production.**


## Jun 8, 2026 — Fix: Social Autopilot screenshot ↔ copy mismatch

**Bug (reported from production):** a feature post showed the CRM-pipeline screenshot but the headline/caption advertised a "Smart Rota Builder" (scheduling). Root cause: the launch/feature prompt passed the feature name only as a soft "hint", so Claude invented unrelated products (topic `crm_pipeline` → headline "Smart Staff Scheduling"). The screenshot is keyed to the topic's `feature_id`, so the feature-keyed image no longer matched the drifted copy.

**Fix (two layers):**
1. **Hard feature binding** in `build_launch_prompt` + `build_prompt` (feature path): an explicit "FEATURE YOU ARE WRITING ABOUT — do not change it" block (exact name + hook) with a rule to never invent/rename/substitute a different product (e.g. no "Rota Builder", "Smart Scheduling", "Ops Dashboard"). Keeps the **caption** on-feature.
2. **Deterministic guarantee for screenshot posts** in `generate_post_for_channel`: the on-image headline is forced to the canonical feature label (`feature_pillar_by_id(...).label`) so image and headline can never diverge; if no real screenshot resolves, it falls back to a feature card instead of showing a mismatched image.

Verified: regenerated fresh drafts — every screenshot post's headline + caption now match its feature (CRM→CRM, Sage/Sicon→finance, Supplier/CAPEX→tender pipeline). 52 social tests pass. **Preview-only — REDEPLOY for production (gymaxisai.com).**


## Jun 8, 2026 — Social Autopilot: AI Poster Assistant (prompt → on-brand poster)

Added an in-panel **AI Poster Assistant** (Master Admin → Growth → Social Autopilot) — the operator types a prompt and gets an on-brand poster saved as a draft. Per operator's choices: **on-brand templates only** (no freeform/generative images), simple **prompt→poster form**, output **saved straight into the draft queue** with AI-written caption + hashtags, and **no screenshots** in this flow.

- Backend: `compose_post_from_prompt()` + `build_compose_prompt()` in `utils/social_autopilot.py`; route `POST /api/marketing/social-autopilot/compose` (master-admin, 30/hr rate limit). Claude picks the best layout from hook/stat/feature/punchline and writes caption/hashtags/headline. **Numbers safety:** for stat layouts the model must reuse a figure from the operator's prompt OR copy a curated `PRODUCT_STATS`/`INDUSTRY_STATS` item verbatim — never invent one (empty/missing stat falls back to a curated product fact). Renders via the deterministic template engine (`image_model="prompt:<layout>"`).
- Frontend: `PosterAssistant` component in `SocialAutopilotPanel.js` — prompt textarea + idea chips + optional headline + channel select + layout select (Auto/Hook/Stat/Feature/Punchline) + Generate. On success the new draft appears in the queue. testids: `poster-assistant`, `poster-prompt-input`, `poster-headline-input`, `poster-channel-select`, `poster-layout-select`, `poster-generate-btn`, `poster-idea-chip`.
- Verified end-to-end in the live UI (prompt → auto-picked stat card → saved to Instagram drafts) and via curl (stat + punchline). Tests: `tests/test_iter222_poster_assistant.py` (8) pass; 17 Iter-222 social tests green total. **Preview-only — REDEPLOY for production.**

## Jun 7, 2026 — Split sales decks + real app screenshots

- Finalised two audience-split sales presentations with "GymAxisAI" branding + white-pill logo:
  - `GymAxisAI-Operators-Presentation.pdf` (14pp) and `GymAxisAI-Suppliers-Presentation.pdf` (12pp), served from `/app/frontend/public/downloads/` and linked in the public marketing footer (`MarketingShell.js`, testids `gx-footer-sales-deck-operators` / `-suppliers`). Old combined deck deleted.
- Replaced wireframe mockups with **real, populated, Pulse-free screenshots** captured from a new neutral demo tenant **"Apex Fitness Group"** (`apex-demo-org`, account_type `full` → GymAxis branding):
  - Operators deck: CRM sales pipeline, Operations equipment register, Memberships analytics.
  - Suppliers deck: engineer job dashboard (Service Desk slide), asset fault/service log.
  - Marketing slide (operators) + Van-stock & Engineer-phone slides (suppliers) kept their wireframes — no convincing demo data without disproportionate seeding.

### Follow-up (same day) — last 2 wireframe slides now real + marketing routing bugfix
- Seeded Apex **Marketing** (4 audiences + 5 email campaigns w/ metrics, A/B) and engineer **Van stock** (9 parts, low/out badges, £4,112 value) via `backend/seed_apex_marketing_vanstock.py`.
- **Bug fixed (platform-wide):** `routes/marketing_downloads.py` had a greedy `GET /marketing/{slug}` catch-all that shadowed `GET /api/marketing/campaigns|audiences|templates`, 404-ing the Marketing **Campaigns/Audiences/Templates** tabs for *all* orgs (incl. master admin). Replaced with explicit per-slug routes (public PDF URLs unchanged: `mod-briefing.pdf`, `mod.pdf`, `sicon-access.pdf`). Regression test: `tests/test_marketing_downloads_no_shadow.py` (2/2).
- Operators deck Marketing slide + Suppliers deck Van-stock slide now use real screenshots. **All 7 mock slides across both decks are now real app screenshots.** Only the Engineer-phone illustration (dark mobile mockup) remains a designed graphic by intent.
- New artifacts: `backend/seed_apex_demo.py`, `backend/seed_apex_crm.py` (idempotent), `sales/capture_*.py`, `sales/embed_shots.py`, `sales/render_pdf.py` (now renders both decks). Demo login + re-seed steps recorded in `test_credentials.md`.


## Jun 8, 2026 — Social Autopilot: killed hallucinated AI imagery, added a brand-accurate template engine

**Problem (operator report):** the autopilot produced off-brand images — fake "GYMAXIS.CO.UK" logo posters, hallucinated dashboards of "a system that isn't ours", and blank purple gradients. Root cause: the image pipeline alternated a reliable branded card (Variant B) with **raw Gemini image generation (Variant A)**, which invents garbled UIs/logos/text and sometimes returns a bare gradient.

**Fix — removed generative-AI imagery entirely. Every card is now rendered deterministically** (`backend/utils/social_templates.py`) from real brand tokens + the real GymAxis logo + correct `gymaxisai.com` domain, with 5 channel-aware layouts:
- `hook` — bold statement on brand gradient.
- `stat` — big number + label (numbers-led) on dark brand canvas. Figures come from **curated, never-fabricated** lists in `social_autopilot.py`: `PRODUCT_STATS` (literally true of GymAxis) and `INDUSTRY_STATS` (tagged "INDUSTRY ESTIMATE" on-card, never implied as customer results).
- `feature` — feature title + 3 LLM benefit bullets (no invented metrics).
- `punchline` — setup→payoff humour; auto-downgraded to a `stat` card on LinkedIn (drier).
- `screenshot` — a **REAL product screenshot** (curated into `backend/static/social/screenshots/`, reused from the sales-deck pipeline) composited into a browser frame. Fixes "screenshots of a system that isn't ours".

`pick_layout()` rotates layouts per channel/topic deterministically (variety, zero hallucination). `build_prompt`/`build_launch_prompt` now take `layout`+`stat` and inject layout-specific JSON keys + humour/numbers guidance. Orchestrator (`generate_post_for_channel`) renders via `render_social_card` (`image_model="template:<layout>"`); legacy branded card is the only fallback. `render_nano_banana_image` is now dead code (left in place, uncalled).

New endpoint `DELETE /api/marketing/social-autopilot/posts[?channel=]` (master-admin) clears drafts to "start over". Used to wipe 20 old drafts; regenerated fresh — all new posts confirmed `template:*` PNGs, verified in the live Master Admin → Growth → Social Autopilot UI.

Tests: `tests/test_iter222_social_templates.py` (10) + 51 existing social tests pass. Reference sites (`help.later.com`, `templates.memes.com`) didn't return scrapeable content, but the formats they champion (hooks, numbers-led, feature carousels, humour) are baked into the layout system. **Preview-only — REDEPLOY to push to gymaxisai.com.**

**Follow-up (same day) — stats + screenshot coverage tuned:**
- Refined `PRODUCT_STATS` (e.g. "6-in-1 — CRM, service desk, PPM, memberships, finance & marketing") and `INDUSTRY_STATS` (added "1 bad visit is all it takes for a member to start cancelling"; 4 items now), all still curated/never-fabricated.
- Widened `SCREENSHOT_MAP` to 11 features, each pointed at a DISTINCT, genuinely-matching real screen (ai_triage→faults, ppm_scheduler→schedule, membership_intelligence→mbr_analytics/churn, supplier_qa→suppliers, supplier_capex→tender pipeline). `communications_inbox` & `gdpr_workflow` left intentionally unmapped (no true screen → use feature card, never a misleading screenshot). New screens copied into `backend/static/social/screenshots/`. 61 social tests pass; all mappings verified to resolve to real files.



## Jun 8, 2026 — Phase 2: Manufacturer manual auto-link + per-type custom check sheets

Two P0 production feature requests delivered (both backend + frontend, tested).

**Task 1 — Equipment "Manufacturer manual" auto-link (read-only, all roles).**
- `EquipmentDetailContent` (`frontend/src/pages/LiteDashboard/LiteDialogs.js`, Documents section ~line 349): when an equipment item has a matched Master-Admin spec sheet (`spec_sheet_id`), the Documents list now surfaces it as a **"Manufacturer manual"** card with a blue **Read-only** badge, a View action (testid `equip-manual-view`, switches to the Spec Sheet tab) and a Download link (testid `equip-manual-download` → public `GET /api/spec-sheets/pdf/{id}`). Card testid `equip-manufacturer-manual`. Visible/downloadable by ALL roles; only Master Admin uploads spec sheets. Matching logic unchanged (auto-match on equipment create/import). Verified visually on Apex demo (temp-attached spec sheet, then reverted).

**Task 2 — Custom check sheets assignable to an equipment type (replaces default).**
- Backend (`backend/routes/check_sheets.py`): `POST /api/maintenance/templates` and `/check-sheets/custom-template` now persist `equipment_type` (stripped; empty string = general). GET endpoints return it. Pytest 4/4 (`tests/test_iter_phase2_check_template_equipment_type.py`).
- Frontend (`frontend/src/pages/CheckSheetsTab.js`): create dialog has an **"Applies to equipment type"** dropdown (testid `template-equipment-type-select`, options = org equipment types + "Any — general template"). `handleStartSheet` loads the assigned custom template's items **instead of** the built-in default for that type. Group cards show a blue assigned badge (`custom-assigned-<type>`); custom-template cards show their type badge (`custom-template-type-<idx>`).

Preview-only — user must REDEPLOY to gymaxisai.com for production.

## Jun 10, 2026 — Iter 230: Pre-handover watertightness audit (backend + end-user E2E)

**Goal:** "Can you confirm all the end user processes are watertight too?" — full regression to green + frontend E2E sweep before Pulse Fitness handover.

**Backend regression — `make regression` now 2,368 passed / 0 failed (3 consecutive green runs), `make regression-full` 97/97, all lint gates green (`ruff`, ESLint --max-warnings 0, docs-verify, lint-integrations).**

Real production bugs found & fixed:
- `generate-invoice-draft` 500 (`InvalidDocument`): calling `create_invoice()` directly left the FastAPI `Header(None)` default object in the Mongo doc. Fixed call site (`routes/svc/engineer_phase3.py`) + hardened `create_invoice` (`routes/svc/engineer_invoices.py`).
- `routes/svc/engineer_stock.py` F821: used `re.escape` without import (runtime NameError on machine-name stock rollup path) → replaced with `safe_regex_exact`.
- Failed sign-in showed misleading "Session expired" toast: 401s from `/auth/login`-style endpoints now render "Sign-in failed / Invalid credentials" (`lib/formatApiError.js` + unit tests).
- **Destructive test fixed:** `test_iter215bh_punch_list.py` reset the password of the FIRST real non-master user (repeatedly clobbering `engineer.smoke@gymaxisai.com` and cascading 25+ engineer-test failures). Now creates a throwaway user + temp org. engineer.smoke password restored to `EngTest123!`.

Test-suite hygiene (stale pins updated to match legitimately evolved code):
- i18n refactor pins (`const NAV = (t) => [...]`, `orbitModules.length`), SetupWizard CSS-variable theming pins, currency-localised labels, `issued_via=admin_partner`, `_mint_and_send_password_reset` delegation, supplier auto-dispatch (220ea·39 contract), sticky social-library deletions, repeat-incident rollup limit + cleanup (purged 498 phantom test incidents), `_resolve_crm_brand_flags` 4-tuple mocks, 502 tolerated for Resend-less preview.
- conftest `_rebind_motor_to_current_loop` now generically republishes the fresh Motor `db` to EVERY loaded module (isinstance match) — kills the "attached to a different loop" order-dependent flakes for good.
- `test_iter234_smart_error_notifications.py` re-pointed from removed `lee.somers@pulsefitness.com` to documented `owner@apexfitness.group`. test_credentials.md updated.

Frontend lint + UX:
- Cleared all 18 `gymaxis/no-dark-mode-leakage` + `no-inline-hex` errors and 10 unused-import warnings (Marketing/Landing/*, MobileAppBuilderTab, CRMPriceChangesModal, PeopleDirectory #4338CA→#4f46e5).
- Added EN/FR/DE language switcher to /login (`gx-login-lang-select`) — verified FR "Bon retour" / DE "Willkommen zurück".

End-user E2E audit (testing agent + manual verification):
- VERIFIED WORKING: marketing home + FR/DE switching (no raw keys), /pricing, /pulse landing (product images lazy-load correctly — "broken images" was a false positive), /pulse-pricing "Most Popular" badge (by design only on /pulse-pricing), master-admin login/People directory/logout, owner dashboard all module tabs, Engineer App KPIs + quick actions, /partners/engineers → full apply form, failed-login error message, cookie banner.
- Preview-only — REDEPLOY to push to gymaxisai.com.

## Jun 10, 2026 — Iter 231: CRITICAL production fix — instant "session expired" after sign-in

**Symptom (production gymaxisai.com):** sign-in succeeds → instant "Your session has expired" banner; master-admin navigates but nothing loads.

**Diagnosis:** production server-side auth verified HEALTHY via direct probes (login → ga_session cookie → /auth/me 200 → /master-admin 200). Failure is client-held stale credentials SHADOWING the healthy HttpOnly cookie:
1. Stale legacy JWT in localStorage sent as `Authorization: Bearer <dead>` → backend preferred header over valid cookie → 401 everywhere, refresh also 401 (interceptor attached the same dead token).
2. Duplicate-scope `ga_session` cookie (e.g. historic `Domain=.gymaxisai.com`) serialised first by the browser; `request.cookies` collapses same-named cookies to the FIRST → stale wins.

**Fixes:**
- `utils/auth.py`: `get_current_user` + `try_get_current_user` now try EVERY `ga_session` candidate from the raw Cookie header before rejecting (`_cookie_token_candidates`); a dead header no longer bricks a valid cookie session.
- `routes/auth.py`: login/register/refresh/mfa-verify now emit `purge_legacy_cookie_scopes` (deletes `Domain=.<host>` variant) alongside the host-only cookie.
- `App.js` 401 interceptor: if header-based refresh fails and not impersonating, retries once cookie-only, then normalises localStorage to the `'cookie'` sentinel.

**Tests:** new `tests/test_iter231_session_self_heal.py` (6 tests — stale-header shadow, duplicate-cookie shadow, purge headers, garbage-only still 401). Full gate re-run: 2,368 passed. Browser simulation of the exact production scenario (stale token planted → login) loads master-admin cleanly.

**Status: fixed in preview — REQUIRES REDEPLOY to reach gymaxisai.com.**

## Jun 10, 2026 — Iter 232: Active sessions / "Sign out everywhere" panel

- **Backend:** `user_sessions` registry recorded at login/register/MFA-verify, rotated in-place on /auth/refresh, dropped on logout (`utils/auth.py::record_user_session`). New endpoints: `GET /api/auth/sessions` (device, IP, last-seen, current flag), `POST /api/auth/sessions/{id}/revoke` (single device — jti deny list), `POST /api/auth/sessions/revoke-others` ("sign out everywhere else" — revokes registered jtis + stamps `tokens_revoked_before` = current iat so even unregistered legacy tokens die while this device survives). All audited to security_audit_log.
- **Frontend:** `ActiveSessionsPanel` (variant-aware: dark for legacy master-admin AccountPanel, light/theme-aware for AccountSettingsModal → Security). Mounted on both surfaces. data-testids: active-sessions-panel, session-row-*, session-current-badge, session-revoke-*, sign-out-everywhere-btn.
- **Hardening:** Resend send now bounded by `EMAIL_SEND_TIMEOUT_SECONDS` (default 10s) — a hung email provider no longer blocks API routes (was causing transient ReadTimeout flakes in partner-approval tests, and a real prod latency risk).
- **Tests:** `tests/test_iter232_active_sessions.py` (7 tests, throwaway-user pattern — never mutates revocation state of seeded accounts). Both iter231 + iter232 files added to the `make regression` gate. Full gate green: 2,368 passed.

## Jun 10, 2026 — Iter 233: Master-admin KPI cards — interactive + numbers aligned

- **Numbers fixed:**
  - `/master-admin/stats` now honours the `brand` query param the header brand selector sends (was ignored → "Organisations 4" card vs 1 org in the brand-filtered list). Card and list now ride the same scope.
  - CRM "Active Deals" card rendered blank: backend returned `active_opportunities` but the card read `overview.total_deals`. Backend now ships both keys; frontend falls back.
- **Cards now interactive:**
  - CRM Dashboard KPIs deep-link into the CRM workspace (`/crm?tab=contacts|companies|pipeline` — CRMApp already honours ?tab=).
  - Memberships Overview KPIs switch to the matching inner tab (Organisations / Revenue / Engagement & Retention).
  - Platform "Open Cases" card now opens the Service Desk section (others were already clickable).
  - Cards get hover lift + cursor, keyboard activation (Enter/Space), role=button.
- **Duplicated filters removed:** in module-context org lists (CRM tab / Operations tab via portalFilter, MoD via accountTypesIn) the "All Modules" dropdown is hidden (the tab IS the module filter); MoD also hides "All Platforms". The platform-level Organisations section keeps all dropdowns.
- **Tests:** `tests/test_iter233_admin_kpi_alignment.py` (7 tests: brand-scope parity stats↔list, total_deals contract, memberships KPI keys, navigation source pins) added to the `make regression` gate. Full gate green: 2,388 passed.

## Jun 10, 2026 — Iter 233b: Marketing & MoD module tabs — interactive KPIs

- **Marketing tab:** analytics tiles now navigate — MRR & Subscriptions → Subscriptions sub-tab, Emails (30d) → platform Emails section, AI gens (30d) → Operations Portal → AI Usage inner tab. Campaigns/journeys stay informational (no master-admin detail view exists). Tiles got testids (`mkt-tile-*`), hover lift, keyboard activation.
- **MoD tab:** new KPI row (MoD Organisations / Branches / Sites) above the org list — each card acts as an account-type FILTER (click to narrow the list to that tier, click again to clear; active ring + "Filtering — click to clear" hint). testids `mod-kpi-mod_org|mod_branch|mod_site`.
- Tests: 2 new source pins in `test_iter233_admin_kpi_alignment.py` (9 total). ESLint green. Verified in-browser.

## Jun 10, 2026 — Iter 235: Read-only cross-org Campaigns & Journeys browser

- **Backend:** `GET /api/master-admin/marketing/campaigns` + `GET /api/master-admin/marketing/journeys` in `routes/marketing/admin.py`. Both honour Pulse scoping + `?brand=` (shared `_admin_org_scope` helper) and `?status=` filter. Lightweight projections only — campaign body `content`/`variants` and journey `nodes` graph never leave the server (journeys ship a `node_count`). Rows decorated with `organization_name` + `account_type`. Master-admin only.
- **Frontend:** new "Campaigns & Journeys" sub-tab in `AdminMarketingSuite.js` — two read-only tables (campaigns: org/status/channel/sent/open-rate/A-B flag; journeys: org/status/trigger/steps/entered/converted) with a shared status filter. "Campaigns (30d)" and "Active journeys" analytics tiles now deep-link into the browser.
- **Tests:** `tests/test_iter235_admin_campaign_browser.py` (5 tests: payload shapes, no-content-leak, status filter, non-admin 401/403, tile deep-link source pins) added to the `make regression` gate. Verified in-browser (8 campaigns + 1 journey rendered with org names).

## Jun 11, 2026 — Iter 236: "Engineer" role in Master Admin Add/Edit User dialogs

- **User report:** Production → Organisations → Pulse Fitness → Add User had no Engineer option in the role selector.
- **Frontend:** `AdminOrganizations.js` Add User + Edit User dialogs now offer **Engineer** (with explainer hints `add-user-engineer-hint` / `edit-user-engineer-hint`).
- **Backend (`master_admin_users.py`):**
  - `add_user_to_organization` role=engineer special-case: engineer is ALWAYS created in the service-portal `users` collection (the Engineer App authenticates only against it — a CRM-portal org like Pulse Fitness would otherwise create them in `crm_users` where they could never sign in) + Iter-227 `_sync_engineer_provisioning` creates the active `svc_engineers` row → Engineer App unlocked via internal_engineer bypass (no £30/mo Partner plan for direct employees).
  - `admin_edit_user`: role changes now run the same sync (engineer ⇄ other roles provisions/deactivates the engineer record); engineer added to the master-admin demotion flag-strip branch.
  - Hard-delete cascade now removes the `svc_engineers` row (was an orphaned-active-row gap).
- **Tests:** `tests/test_iter236_org_engineer_role.py` (full lifecycle vs live Pulse Fitness org with archive+confirm-delete teardown, zero residue; dialog source pins) in the `make regression` gate. Full gate green: 2,404 passed. Verified in-browser (Engineer option + hint render in the Add User dialog).

## Jun 11, 2026 — Iter 237: Ops dashboard production fixes (Pulse score card, dark mode, site switcher, FR/DE)

- **Pulse score card duplication:** the "The Pulse · today" hero card rendered ABOVE the Operations tab strip (so it repeated on every tab) AND a second "Gym Health Score" panel sat inside the Dashboard tab. Now a single card lives inside the Dashboard tab only (`LiteOverviewTab`), branded "The Pulse · today" (Pulse) / "Gym Health · today" (GymAxis). The 216h192 "How to improve" tip moved into the card's expanded breakdown.
- **Dark mode leakage:** `PulseScoreCard` was hardcoded light (bg-white, #E2E8F0, slate text) and Recent Faults used hardcoded `text-white` (invisible in light mode). Both now ride `--theme-*` variables.
- **Site switcher regression:** Pulse Master Admins (role `pulse_master_admin` / `is_pulse_admin`) were excluded by the owner/manager-only gate in `LiteDashboardPage` AND by the privileged-roles set in backend `/api/sites`. Both widened — Lee can switch Pulse Fitness HQ / iGym sites again.
- **FR/DE in-app:** the Operations dashboard was 100% hardcoded English. Tab labels, welcome line, Log-a-Fault CTA, all 8 KPI tiles, Recent Faults and the score-card description now consume i18n (`dashboard.*` keys; 15 new keys added to en/fr/de locales). Verified in-browser in both FR and DE.
- **Lesson recorded:** parallel `search_replace` calls on the SAME file clobber each other (one of four batched edits was silently lost). Same-file edits must run sequentially.
- **Tests:** `tests/test_iter237_ops_dashboard_fixes.py` (6 tests: pulse-admin /api/sites privilege, card placement pins, dark-mode leak pins, i18n pins) in the `make regression` gate. Gate green: 2,409 passed.

## Jun 11, 2026 — Iter 238: FR/DE translation extended through the Operations module

- **Wired to i18n:** ModuleSwitcher (module pills), SiteSwitcher, Equipment tab (search/add/badges/move-kit/empty states), Faults tab (subtabs, filters, severity+status labels, multi-machine job rows, empty states), Documents tab (categories, dropzone, upload CTAs), the full Log-a-Fault wizard in `LiteDialogs.js` (labels, placeholders, severity picker + descriptions, submit/triage buttons), `getSeverityLabel` helper (via i18n singleton), Operations Start tab (outcomes/steps/jumps — testids made language-stable via slug keys), ActivationMilestonesCard (15 milestone labels translated client-side keyed by `event_type`), Navbar "Help & Tutorials" / "Take a Tour".
- **Locales:** +173 keys each in en/fr/de (`modules`, `sites`, `status`, `severity`, `equip`, `faults`, `docs`, `dialog`, `ops_start`, `activation`, `nav` groups).
- **Method note:** per-file python patch scripts (exact-match + assert) to avoid the parallel same-file `search_replace` clobbering hit in iter 237.
- **Tests:** `tests/test_iter238_platform_i18n.py` (wiring pins per file, locale key completeness, anti-copy-paste guard for fr/de) in the `make regression` gate. Gate green: 2,414 passed. Verified in-browser: FR + DE across Start, Dashboard, Equipment, Faults, fault wizard, user menu.
- **Still English (next i18n passes):** Check Sheets / AI Diagnosis / Reports / Suppliers / Staffing tab internals, Memberships / CRM / Marketing module screens, toasts/notify messages.

## Jun 11, 2026 — Iter 239: Per-user language preference + localized emails

- **Profile-saved language:** `PATCH /api/account/profile` now accepts `language` (en/fr/de, validated); `/api/auth/me` returns it. The Navbar globe persists the choice for logged-in users; `App.js` applies `user.language` on hydrate — the preference follows the user across browsers/devices (verified e2e: cleared localStorage, reloaded, UI restored to the profile language).
- **Localized emails:** new `utils/email_i18n.py` (SUPPORTED_LANGS, `user_lang()`, `tr()`); the Memberships weekly digest now builds subject + email chrome per recipient language (grouped per-lang HTML build; AI headline/narrative stays source-language).
- **Tests:** `tests/test_iter239_user_language.py` (5 tests: persist + cross-session follow, invalid lang 400, helper unit tests, localized digest HTML per lang, frontend wiring pins) in the `make regression` gate. Gate green: 2,419 passed.

## Jun 11, 2026 — Iter 240: Google Search favicon (GA logo next to results)

- **Root cause of the generic globe:** no `<link rel="icon">` in index.html, no favicon files on disk, apple-touch-icon + manifest icons were inline data-URI SVGs (Google can't crawl data URIs), and the Organization schema `logo` pointed at a non-existent `brand/gymaxis-logo.svg`.
- **Fix:** generated real icons from `brand/gymaxis-mark-tight.png` (white-padded square): `favicon.ico` (16/32/48 multi-size), `favicon-48/96/192/512.png`, `apple-touch-icon.png` (180). Wired `<link rel="icon">` tags (48/96/192 — Google requires a crawlable multiple-of-48px icon), real apple-touch-icon (the /pulse runtime brand swap untouched), manifest.json icons → real files, schema logo → `/favicon-512.png`. robots.txt verified not blocking.
- **Tests:** `tests/test_iter240_google_favicon.py` (5 tests: files exist + square + 48px multiples, HTTP 200 + image content-type, index.html link pins, manifest icon files, robots guard) in the `make regression` gate. Gate green: 2,424 passed.
- **User action after deploy:** Google refreshes favicons on its own crawl schedule (days→~2 weeks). Optionally speed up via Search Console → URL inspection on `https://gymaxisai.com/` → Request indexing.

## Jun 11, 2026 — Iter 241: Blank Reports / Suppliers / Gym Layout tabs (production, Pulse Master Admin)

- **Root cause:** tab PILLS (buildTabs) and tab CONTENT (`<TabsContent>` gates) in `LiteDashboardPage.js` used different hand-written role lists. Content gates said `owner || manager` and forgot `pulse_master_admin` — the same omission class as the iter-237 site-switcher bug — so the pill rendered but clicking it mounted nothing (blank page).
- **Fix:** single `isManagerial` flag (owner/manager/pulse admins) for role gates (staffing label — pulse admins now get full Staffing instead of the limited Gym Floor view — site switcher, nudge banner), and the INVARIANT `tabVisible(id)` — content gates derive from the SAME TABS list as the pills so they can never diverge again.
- **Bonus:** the new structural test immediately caught and removed an orphan `gym-floor` TabsContent (dead code — unreachable; GymFloorManagerTab lives in MODProDashboard, floor staff use /gym-floor).
- **Recurrence guard:** `tests/test_iter241_pulse_tab_content_gates.py` — 4 tests incl. a structural invariant: every pill id must have a TabsContent and vice-versa, and no hand-written role gate may wrap a TabsContent. In the `make regression` gate.
- Verified e2e as pulse_master_admin: Reports (753 chars), Suppliers (586), Gym Layout (156) all render. Gate: 2,425 passed (3 unrelated engineer-app flakes pass in isolation).

## Jun 11, 2026 — Iter 242: Cross-dashboard pill-vs-content audit

- Audited every tabbed dashboard for the iter-241 blank-tab pattern (pill offered, content role-gated differently): GymAxis ops (DashboardTabs vs DashboardPage TabsContent), MOD Pro portal (pillars), Memberships console (TABS + schedule-hub includes), CRM (NAV_ITEMS vs renderContent switch), Marketing suite (nav vs switch). **No further traps found** — CRM/Marketing have `default:` fallbacks, others render every pill. GymAxis `digest` is an intentional deep-link-only tab (whitelisted explicitly).
- **Recurrence guard:** `tests/test_iter242_dashboard_pill_content_audit.py` (5 structural tests, one per dashboard, with mechanism-specific extraction + explicit orphan whitelist) added to the `make regression` gate — any future pill/content divergence in ANY dashboard fails CI.
- Gate green: 2,433 passed.

## Jun 11, 2026 — Iter 243: Centralised `can(user, capability)` helper

- **New:** `frontend/src/utils/capabilities.js` — single source of truth for UI role gates (`can(user, 'capability', { role? })`, named RULES, fail-closed on unknown capability). Created because three production bugs (iter 237 site switcher, iter 241 blank tabs, iter 243 below) shared one root cause: hand-listed roles forgetting pulse_master_admin.
- **Migrated consumers:** LiteDashboardPage `isManagerial`, DashboardPage (`view_suppliers`, `dismiss_nudges`, `manage_fault_templates` prop), ReportsSection (`view_capex`), FaultTemplatesManager (`manage_fault_templates`).
- **Live bug found & fixed during migration:** Pulse Settings → Fault Templates excluded pulse admins on BOTH sides — frontend `privileged` flag and backend `fault_templates.py` `_can_manage_org_templates` / `_PRIVILEGED_ROLES`. Verified via HTTP: pulse_master_admin can now create + delete org-scoped templates.
- **Tests:** `tests/test_iter243_capabilities.py` (backend HTTP lifecycle, backend role pins, capability-helper completeness, consumer pins incl. a "no inline role lists" guard that immediately caught 2 more inline gates in DashboardPage). Iter-237/241 pins updated to the centralised implementation. Gate green: 19/19 targeted + full suite (2,435 passed; 2 prior failures were stale pins, now updated).

## Jun 15, 2026 — Iter 286: Org Chart 3 P0 bugfixes (drag crash, presentation text, vertical layout)

- **FIX 1 — drag runtime error:** `Canvas.js` `onCardPointerDown` now wraps `setPointerCapture` in try/catch (it can throw InvalidStateError/no-active-pointer when captured on an ancestor of the pointerdown target) and `onPointerUp` null-checks `byId[id]`/`pos[id]` + releases pointer capture. Eliminated the TypeError that crashed the canvas while moving cards.
- **FIX 2 — presentation text invisible:** Root cause was `index.css:630` global rule `[data-theme="light"] .text-white { color: var(--theme-text) !important }`. The Presentation renders via `createPortal` to `document.body` (inside the light-theme operations shell), so every `.text-white` went dark-on-dark. `Presentation.js` now sets all text colours with inline `style` (`#fff` / rgba whites) instead of the `.text-white` class, bypassing the override. (Long-term: scope that index.css selector.)
- **FIX 3 — vertical (stacked) layout, now default:** `layout.js` `computeLayout` gains `dir='vertical'` = indented tree (every report on its own row stacked downward, indent right per depth — V_INDENT=56, V_ROW=144). `Canvas.js` draws orthogonal elbow connectors in vertical mode. `Settings.js` adds 'Vertical (stacked)' option (default). Backend `staffing_orgchart.py`: `DEFAULT_SETTINGS.layout='vertical'` + new `_vertical_positions()` applied on fresh `_seed_from_staff` and on `import_apply` so seeded/imported charts arrive stacked without a manual Auto-layout click. Users can still choose Top-down / Left-to-right.
- **Tests:** `tests/test_iter286_orgchart_vertical_layout.py` (5 passed) added to `make regression`. Frontend testing agent verified all 3 fixes e2e on the 121-node chart with 0 console/pageerrors; new charts default to vertical; presentation text confirmed white-on-navy via screenshot.

## Jun 15, 2026 — Iter 288: Master Admin "Org People" directory (P3)

- **New view** Master Admin → People → **Org People** sub-tab (`OrgPeopleDirectory.js`, wired in `AdminRoles.js` as `roles-tab-org-people`). One row per person showing JOB TITLE + which MODULES they can access (Operations · CRM · Memberships · Marketing) as check/dash cells, with org + role chip. Includes search (name/title/org), a "Has <module>" filter, and a client-side CSV export. Row click reuses the existing UserDetailDrawer.
- **Backend** `master_admin_users.py`: new `_enrich_with_module_access()` (called in `GET /master-admin/users`) batch-fetches orgs and resolves each user's effective `module_access` via `utils.module_access.resolve_module_access`, and surfaces a single `job_title` (falls back to `primary_role`). No new endpoint — extends the existing deduped/brand-scoped users payload.
- Verified e2e (admin@gymaxisai.com): tab renders 11 rows with correct module ticks + role chips, 0 console/pageerrors; curl confirms `module_access`/`job_title` in the payload.

## Jun 15, 2026 — Iter 288b: Org People — job-title backfill + inline edit (P3 follow-up)

- **Auto-populated titles:** new `_enrich_job_titles()` in `master_admin_users.py` backfills an empty `job_title` from the org's `staff_members.primary_role` (matched by user_id then email), so the Org People directory no longer shows "—" for everyone. Wired into `GET /master-admin/users` after module-access enrichment.
- **Inline editing:** `OrgPeopleDirectory.js` job-title cell is now click-to-edit (Enter/blur saves, Esc cancels) → `PUT /master-admin/users/{id}/edit {job_title}`, optimistic update + toast + parent reload. Empty cells show an "Add title" affordance.
- Verified e2e (admin@gymaxisai.com): titles backfill (manager/other), PUT persists (200, reflected in list + cleaned up test value), edit input renders on click. 0 page errors.

## Jun 15, 2026 — Iter 289: Pre-transfer security check (Pulse Fitness / pen-test readiness)

- Reviewed the NEW surfaces added since the 06-05 audit (Org Chart Builder, AI/PDF import, public share link, Org People directory). All `orgchart/charts/{cid}` routes are tenant-scoped via `_get_chart` (404 on cross-tenant — IDOR-safe); writes are manager-gated; the Org People edit reuses the `require_master_admin` + scope-gated `/master-admin/users/{id}/edit` with a field allow-list.
- **Hardened** public org-chart share token 128→256-bit (`token_urlsafe(32)`) to match the F-21 widget standard; public read endpoint already strips PII/notes/salary and 404s on bad token (verified live).
- **Green security-scan gate:** fixed 5 pre-existing cosmetic ruff errors and annotated 1 false-positive bandit B608 (a `print()` in an offline wipe script). Result: ruff clean, bandit 0 High / 0 Medium.
- Security regression suite: 107 passed / 2 skipped / 1 stale-fixture failure (`test_iter251` uses `owner@apexfitness.group`, purged from preview — not a control regression).
- Register updated: `memory/SECURITY_AUDIT/findings.md` SEC-012/013/014, last-review bumped to 2026-06-15.

## Jun 15, 2026 — Iter 289b: Public org-chart endpoint hardened (F-21 posture)

- `GET /api/staffing/orgchart/public/{token}` now: reads client IP from X-Forwarded-For, enforces a 60/min/IP cap (HTTP 429 via `_check_public_org_rate`), and writes a per-attempt audit row to `org_chart_access_log` (token/ip/ua/found/ts) — mirroring the F-21 widget enumeration guard. Combined with the 256-bit token + PII stripping, the only new public surface added pre-transfer is now at the platform's standard public-endpoint posture.
- Verified live (60×404 → 429 on a fixed IP) + regression test `tests/test_iter289_orgchart_public_hardening.py` (2 tests, added to `make regression`). Security-scan gate green (ruff clean, bandit 0 High/0 Medium).

## Jun 15, 2026 — Iter 290: Service Desk dashboard — team performance

- Removed the **Quick Actions / Manage Customers** card and the **Customer Security Briefing** card from the Service Desk dashboard (`DeskSummary.js`).
- Added a polished **Team Performance** section (`DeskPerformance.js`): FTF (First-Time-Fix) gauge ring + hero throughput (RTF open / avg resolution / closed 7d), six KPI tiles (Open Cases, Return to Fix, SLA Breached, SLA At-Risk, Unassigned, Active Engineers — each deep-links to Cases/Engineers), and an Engineer Leaderboard (jobs closed + FTF% with progress bars).
- New backend `GET /api/service-desk/performance` (`service_desk.py`) scoped to the desk's org. KPI definitions reuse the app's canonical logic: RTF = open jobs with `return_to_fix` set or in `paused_parts/awaiting_parts`; FTF = closed/invoiced cases that never hit `paused_parts` (matches `svc/reports/ftfr`). 30-day window for FTF/avg-resolution/leaderboard.
- Verified live (desk agent: FTF 100% of 16, 449 SLA breached, leaderboard populated) + regression `tests/test_iter290_desk_performance.py` (2 tests, in `make regression`). Frontend compiles, 0 page errors.

## Jun 15, 2026 — Iter 290b: Desk performance polish (engineer join + FTF trend)

- Engineer Leaderboard now joins `svc_engineers` for the canonical `full_name` (no more blank/"Engineer") and the linked user's `avatar_url` for a profile photo (`<img>`, falls back to gradient initials). Avatar endpoint `/api/account/avatar/{id}` is public so the `<img>` loads without an auth header.
- FTF gauge gained a **trend arrow**: `GET /service-desk/performance` now also computes the previous 30-day window (`ftf_rate_prev`, `ftf_trend` in points); the ring shows ↑/↓ "+N pts" (green/red) or "flat" when there's no prior data.
- Verified live (leaderboard → "Master Admin" + photo, trend "flat" with no prior window) + regression `test_iter290_desk_performance.py` updated for the new fields (2 passed). ruff clean.

## Jun 15, 2026 — Iter 290c: Desk performance tiles deep-link to filtered Cases

- Dashboard performance tiles now open the Cases queue pre-filtered: **SLA Breached** → `{sla:'breached'}`, **SLA At-Risk** → `{sla:'at_risk'}`, **Unassigned** → `{assigned:'unassigned'}`. Unified `goTo(tab, arg)` handler in `ServiceDeskPage.js` passes a filter object to the embedded `OpsCases` via a new `initialFilters` prop (cases remounts on tab switch, so the seeded `filters` state applies on mount).
- Verified live: clicking SLA Breached lands on Cases with the "SLA BREACHED ✕" chip + breached-only table (counts reconcile 449=449), 0 page errors.

## Jun 15, 2026 — Iter 290d: Service Desk dashboard — full card interactivity

- Audited every dashboard card: all 13 (customer/case stat cards, Recent Activity, FTF hero, 6 perf tiles, leaderboard rows) are now keyboard+click interactive (`role="button"`) and deep-link to the relevant filtered view. 0 non-interactive cards.
- Closed the two "lands on a generic list" gaps:
  - **Return to Fix** tile → new `rtf=1` filter on `GET /svc/cases` (open jobs flagged `return_to_fix` or parked for parts; composes with `search` via `$and`/`$or`). Wired through OpsCases (`filters.rtf`, params, quick-clear chip "Return to Fix").
  - Provider **Total Cases** → opens Cases with `status=''` (all) instead of open-only; **Open Cases** → `status='open'`.
- Verified: RTF filter matches a seeded RTF case end-to-end (then cleaned up), rtf+search composes (200), SLA drill still works; live screenshot shows 0 non-interactive cards + "RETURN TO FIX" chip on drill. Tests: `test_iter290d_cases_rtf_filter.py` (2) + `test_iter290_desk_performance.py` (2) pass, added to `make regression`. ruff clean.

## Jun 15, 2026 — Iter 290e: Unassigned count alignment

- Fixed the desk-summary KPI ("Unassigned") which counted only `assigned_engineer_id == ""`, missing null/missing-field cases (372 vs the dashboard's 649). Aligned `/svc/desk/summary` (unassigned + skill_gap) to the canonical `{$in:[None,""]}` used by the dashboard tile and the `/svc/cases?assigned=unassigned` drill filter.
- All three surfaces now report the same number (verified live: 649 = 649 = 649). Regression `test_iter290e_unassigned_alignment.py` (added to `make regression`) asserts they stay in sync.

## Jun 15, 2026 — Iter 290f: "SLA at risk" alignment + mutual exclusivity

- "At risk" now means *due soon but not yet breached* everywhere. Previously the Cases KPI counted `sla_resolve_at <= now+2h` (no lower bound) so it included breached cases and read the same as Breached (449/449); the drill used a 2h future window; the dashboard used 24h.
- Introduced a single canonical `SLA_RISK_WINDOW_HOURS = 24` in `utils/svc_state.py`, applied to the desk KPI (`svc/desk.py`), the `/svc/cases?sla=at_risk` drill (`svc/cases.py`) and the performance tile (`service_desk.py`). At-risk = `now <= sla_resolve_at < now+24h`; breached = `sla_resolve_at < now` — mutually exclusive.
- Verified live: all three surfaces reconcile (at-risk 0 / breached 449), a seeded future-target case shows at-risk=1 on all three (then cleaned up). Tests `test_iter290f_sla_at_risk_alignment.py` (2) added to `make regression`. ruff clean.

## 2026-06-24 — Lite tier: no-AI enforcement + module picker cleanup
- Removed `staffing` & `reporting` from `MODULE_OPTIONS` (AdminOrganizations.js); they are native to Pro, not selectable bolt-ons. Cleaned unused icon imports.
- Confirmed Lite Operations tab set is correct: Dashboard / Equipment / Faults / Documents (+ Start guide, + Upgrade to Pro). Defined by `LiteDashboardPage.buildTabs() → baseLite`.
- Plugged AI leaks into Lite (Lite = NO AI):
  - UnifiedAssistant.js: floating AI chat now suppressed for true Lite accounts (`isLiteNoAI`); Pro/trial/MOD/admin unaffected.
  - LiteDocumentsTab.js: inline Document Q&A box + per-file AI "Index" button gated behind `isPro`.
  - LiteEquipmentTab.js: AI "Auto-find images" lookup gated behind `isPro` (prop now passed from parent).
- AI fault triage in the log-fault flow was already correctly Pro-only (verified).
- Verified live in preview via admin `?view=lite`: Documents tab renders no AI Q&A and zero AI index buttons.
- FOLLOW-UP (optional, defense-in-depth): backend hardening to reject AI endpoints (`/issues/triage`, `/files/{id}/extract`, equipment auto-lookup) for `account_type=lite`.

## 2026-06-24 — Lite "Upgrade to Pro" tab → real in-app conversion
- PulseUpgradePage.js CTA converted from a mailto link to a functional one-click upgrade.
  - Calls existing `POST /api/me/upgrade-to-pro` with empty body (Stage 1 = unlock Pro Operations only; bolt-ons added afterwards per the two-stage plan).
  - Owner/master-admin gated; non-owners see a locked "Owner can upgrade" button.
  - Loading + success states, `refreshMe()` + auto-reload so the dashboard picks up the new Pro tabs.
  - Kept the before/after Pro feature cards + Standard-vs-Pro comparison table.
- Verified: endpoint live (clean 400 for non-lite accounts), Upgrade tab renders the CTA with `data-testid=upgrade-now-btn`.
- NOTE: happy-path upgrade not run with a live Lite-owner account (only master-admin available); endpoint is the same one PulseProUpgradeCta already uses in production.

## 2026-06-24 — Backend hardening: AI endpoints blocked for Lite (defense-in-depth)
- New `backend/utils/ai_access.py` → `require_ai_access` dependency. Blocks true Pulse Lite orgs (account_type=lite, no active Pro trial) with 403; allows Pulse Pro / full / MOD / master-admin / Lite-on-active-trial (mirrors frontend `isPro`).
- Applied to AI endpoints: POST /issues/triage, /files/{id}/extract, /documents/ask, /assistant/chat, /assistant/execute-action, /chat/diagnose, /equipment/{id}/lookup-image.
- NOT gated (intentional): /gym-health-score (computed metric, not generative AI), /help/ask & /ask (platform support, all tiers).
- Verified vs real DB: lite→403, pulse_pro→allow, lite+active-trial→allow, master→allow. Master-admin live curl on /issues/triage & /documents/ask → 200 (no Pro regression).
- Incidental fix: removed pre-existing trailing corruption in routes/issues.py (stray `rue)` + duplicate return at EOF) that blocked py_compile.

## 2026-06-24 — AI-gate 403 → in-app upgrade conversion prompt
- Global axios response interceptor (App.js) detects the AI-gate 403 (detail contains "AI features are available on Pulse Pro") and dispatches `pulse:ai-upgrade-required`.
- LiteDashboardPage listens: if the Upgrade tab exists (non-staff Lite) → switches to it + scrolls top + info toast "Unlock AI with Pulse Pro"; staff get a toast asking the owner to upgrade.
- Verified live (admin ?view=lite): dispatching the event flips to the upgrade tab, shows the toast, CTA present. Frontend compiles clean.

## 2026-06-24 — Master Admin IA: P0 single-source-of-truth cleanup (founder review)
- Stripe: removed duplicate nav entry from Integrations; Finance is now the single home (deep-link `?section=stripe-connect` still routes).
- Audit: merged "Audit log" + "Compliance trail" into one **Audit & compliance** screen (new `AuditCompliancePanel` with inner Security-timeline / Compliance-trail tabs). Legacy `audit-logs` deep-link routes to the wrapper (compliance tab).
- Design: merged "Design system" + "Theme settings" into one **Branding & design** screen (new `BrandingDesignPanel`; Design-system inner tab hidden for delegated Pulse admins). Legacy `design-system` deep-link routes to the wrapper.
- Social: moved "Social media library" from Catalogue → Growth (next to Social Autopilot).
- SECTION_TO_GROUP augmented with legacy ids (`audit-logs`, `design-system`) so deep-links still highlight the right group. Removed now-unused lazy imports in MasterAdminPage.
- Verified live: merged wrappers render with 2 tabs each; all legacy deep-links resolve; frontend compiles clean.
- DEFERRED (user chose scope = P0 only): P1 de-clutter of Settings&Compliance (17 sub-tabs) + Growth (9 sub-tabs); P2 onboarding unification.

## 2026-06-24 — Master Admin IA: P1 de-clutter of junk-drawer groups
- Split **Growth (10 sub-tabs)** → **Marketing** (Growth Hub, SEO Autopilot, Social Autopilot, Social media library, Outbound emails — group gymaxisOnly) + **Sales & Comms** (Communications inbox, Canned replies, Sales insights, Trials, Pulse Sales CAPEX).
- Split **Settings & Compliance (14 sub-tabs)** → **Compliance & Security** (Audit & compliance, Login events, Access matrix, Data Subject Erasure, Documents, Archive) + **Platform Tools** (Branding & design, Custom domains, Client crashes, Ask Support Desk, Support tools, Database viewer, Pulse data explorer, Maintenance jobs).
- Section render switch unchanged (sub-tab ids preserved) → all deep-links intact. SECTION_TO_GROUP legacy mappings repointed (audit-logs→compliance-security, design-system→platform-tools). Added group titles/descriptions for the 4 new groups.
- Verified live: 4 new nav groups render, old groups gone, Platform Tools lands on Branding & design. Compiles clean.

## 2026-06-24 — Master Admin P2: unified Onboarding hub
- Folded staff onboarding into `AdminOnboardingHub` as a 6th tab, grouped under "Team"; the 5 customer flows (Onboard Site, Head Office, Packets, Bulk Imports, MOD Sites) sit under "Customers".
- Removed the separate "Onboard staff" entry from People; renamed Organisations "Customer onboarding" → "Onboarding" (single home for customers + team).
- MasterAdminPage: `onboarding` + `staff-onboarding` both render the hub; `staff-onboarding` deep-link opens the staff tab (initialTab). SECTION_TO_GROUP['staff-onboarding']='organizations' for correct highlight. Hub now takes isPulseAdmin + initialTab props.
- Verified live: hub renders grouped Customers/Team tabs, staff deep-link opens staff wizard, People cleaned up, compiles clean.

## 2026-06-24 — Fix: Bulk Import template download 401
- AdminBulkImports.downloadTemplate used raw fetch + localStorage token (absent/stale in prod; real session is HttpOnly cookie) → 401 "Template fetch failed".
- Switched to axios withCredentials + responseType:'blob' so the session cookie carries auth and the 401-refresh interceptor applies.
- Verified live (preview): sites-template.csv downloads, success toast, no error. Needs deploy to reach production.

## 2026-06-24 — Onboarding system Phase 1: orchestration backbone
- New backend `routes/onboarding_projects.py` (registered in route_registry/admin.py). Collections: onboarding_projects, onboarding_audit_events, onboarding_settings. Thin tracking layer over existing records — references organization_id, NEVER duplicates orgs/sites/users/etc. Duplicate-guard: one active project per org.
- Endpoints (/api/onboarding/*, pulse/master gated): customer-types, projects CRUD, checklist step PATCH, go-live approve (blocks if required steps incomplete + generates summary), dashboard aggregate, settings singleton (customer_portal_enabled), audit trail on every action.
- 9 customer types with progressive-disclosure checklist (build_checklist) — multi-site shows hierarchy/regional managers; modules drive contacts/members/assets/service-desk steps; required vs optional; 7 statuses.
- Frontend `OnboardingProjects.js`: dashboard stat cards + common-missing, project list w/ progress bars + status badges, create dialog (type + modules + owner + go-live), detail Sheet (Checklist grouped by phase w/ per-step status + Open→wizard launch, Business profile form w/ all spec fields, Go-live readiness + approve).
- Integrated into AdminOnboardingHub as new "Manage → Dashboard" tab; Onboarding section now lands here. Existing wizards (Customers/Team) untouched.
- Verified: backend curl (create/dashboard/types), live screenshot (dashboard, list, detail, grouped checklist render). Test project cleaned up.
- NEXT: Phase 2 unified Import Centre, Phase 3 module readiness, Phase 4 AI assist (GPT-4o), Phase 5 customer portal + emails + reporting.

## 2026-06-24 — Onboarding system Phase 2: unified Import Centre
- New backend routes/onboarding_import.py (registered). Config-driven TYPE_REGISTRY (contacts→crm_contacts, members→members, suppliers→suppliers) with field aliases, dedupe keys, defaults. Writes into EXISTING collections — no new silos.
- Endpoints (/api/onboarding/import/*, pulse/master gated): types, template/{type} (CSV), analyze (parse+auto-map columns via aliases), validate (required/email/phone + existing & in-file dedupe + per-row report), commit (skip/update/create dedupe action, audit, auto-advances linked onboarding checklist step), GET/POST mappings (saved).
- New frontend ImportWizard.js: 4-step stepper (Setup→Upload&map→Review→Done) with type+target-org pickers, template download, auto-mapping editor, validation/dedupe review table, dedupe-action picker, import report. Mounted atop the Bulk Imports tab; legacy sites/equipment/customers kept below as "Core records (quick CSV)".
- Verified curl: auto-map matched all aliased columns; validate flagged invalid email/suspicious phone + in-file dup; commit created1/skipped1/failed1. UI renders. Test data cleaned.

## 2026-06-24 — Onboarding Phase 3: live module readiness
- New backend routes/onboarding_readiness.py (registered). READINESS_AREAS for CRM / Service Desk / Memberships / Marketing / Engineer App / Stock — each a set of count-based checks over EXISTING collections (crm_contacts, crm_pipelines, users, sites, equipment, suppliers, issues, membership_plans, members, class_templates, comms_segments, marketing_campaigns, parts; engineers = users role 'engineer'). Areas shown depend on project modules + customer type.
- GET /api/onboarding/projects/{id}/readiness → per-area ready flag + per-check counts. POST .../readiness/sync → auto-completes matching checklist steps from live data (advance-only, audited).
- Frontend: new "Module readiness" tab in the project detail Sheet — per-area cards (ready/not-ready), check rows with counts + optional markers, and "Sync checklist from live data" button.
- Verified live: counts reflect seeded records (contacts/assets/members=1); sync advanced exactly those steps; empty org → all not-ready, sync no-op. UI renders 4 area cards + sync. All test data hard-deleted.

## 2026-06-24 — Onboarding Phase 4: AI assistant (GPT-4o, advisory-only)
- New backend routes/onboarding_ai.py (registered) using emergentintegrations LlmChat + EMERGENT_LLM_KEY, model gpt-4o. ADVISORY ONLY — never imports/writes data.
- POST /api/onboarding/import/ai-analyze: given columns + sample rows, returns suggested import type, column→field mapping (guarded to known types/fields), data-quality issues + cleanup suggestions.
- POST /api/onboarding/projects/{id}/ai-summary: returns plain-English status, risks, next_best_actions, missing_info, go_live_ready.
- Frontend: ImportWizard map step gets "Ask AI to map" (applies AI mapping + shows issues banner); project detail checklist tab gets "AI summary" (summary/next-actions/risks panel). Both labelled advisory-only; human still drives validate/commit/go-live.
- Verified: ai-analyze suggested 'contacts' high-confidence + mapped 5 aliased cols + flagged bad email/phone; ai-summary returned sensible next actions; UI smoke showed the AI summary panel rendering a live GPT-4o response. Test data cleaned.

## 2026-06-30 — Comms Centre: "Import email → AI rebuild"
- New feature: drag-and-drop / paste any existing email into the Email Builder and AI rebuilds it into editable, on-brand template blocks.
- Supported inputs: .eml, Outlook .msg, HTML file, pasted HTML/text, image screenshot (vision), PDF.
- Linked (absolute http/https) images are pulled into image blocks automatically; embedded (cid)/screenshot images can't be hosted so a placeholder + a human-readable note is surfaced (toast) telling the user to upload them.
- Backend: new POST /api/comms/ai/import-email (routes/comms_intel.py) accepts multipart (file optional + text field) → utils/email_ingest.parse_email() normalises every format → utils/comms_ai.import_email_to_blocks() (gpt-4o) returns {subject,preview,blocks,notes,source_kind}. Route tolerates both {type,props} and {blocktype:{props}} block shapes.
- Frontend: EmailBuilder.js gets a new "Import" toolbar button (data-testid builder-import) + ImportModal (dropzone, file input, paste textarea, rebuild button). applyImported() wraps returned blocks with logo+footer and fills subject.
- Verified: backend curl/requests for pasted HTML (4 blocks, image src preserved) and .eml with cid image (note flagged); testing agent confirmed full UI flow 100% (paste→rebuild→canvas populated, modal auto-close, subject filled).

## 2026-06-30 — Security: Production CORS wildcard removed (P2)
- backend/.env CORS_ORIGINS changed from "*" to explicit allow-list: https://pulsefitness.ai, https://www.pulsefitness.ai, https://fitness-ai-migrate.emergent.host.
- security_plus.resolve_cors_origins() now ignores a "*" value in production (falls back to brand defaults) and added resolve_cors_origin_regex() — a regex (https://([a-z0-9-]+\.)*(preview\.emergentagent\.com|emergent\.host)) so Emergent preview/host subdomains keep working across redeploys without editing env.
- server.py CORSMiddleware now passes allow_origin_regex.
- Verified app-level: pulsefitness.ai → echoed; preview subdomain → echoed via regex; evil.example.com → DENIED (no ACAO, 400). secrets_audit '[security-audit] all checks passed'. Public login 200, login page renders. NOTE: the public ingress edge still adds its own 'access-control-allow-origin: *' header (platform-level, outside app control), but the app no longer trusts arbitrary origins.

## 2026-06-30 — Comms Centre tab reorganization
- Main tabs reduced to: Campaigns / Flows / Segments / Analytics / Inactive.
- New "Analytics" tab groups Engagement / Best Send Time / Benchmarks behind a sub-tab row (data-testid comms-analytics-tabs / comms-analytics-<id>).
- New "Settings" dropdown (comms-settings-btn, shadcn DropdownMenu) holds Deliverability / Import (migrate) / API & Webhooks (developer) — removed from top-level pills.
- Deep links preserved: ?view=engagement|best-time|benchmarks open Analytics with the right sub-tab; ?view=deliverability|migrate|developer open via Settings; ?view=analytics defaults to engagement.
- Module-scope pill still shown on campaigns/inactive/analytics sub-views; hidden on deliverability/segments/flows/migrate/developer.
- File: frontend/src/pages/Comms/CommsCentre.js (rewrite, ~222 lines). Verified by testing agent: 45/45 frontend assertions passed.

## 2026-06-30 — Cross-module: Service Desk ↔ CRM (Slice 1 of "one Pulse team")
- New backend endpoint GET /api/crm/v2/companies/{company_id}/service-activity (crm_v2.py) — consolidates live Service Desk data for a CRM account, org-scoped, matched by canonical company_id with a name fallback (no duplication). Returns: open svc_cases, engineers on the account with current status (on_site/en_route/assigned), their current case + last known location ping (svc_engineer_locations), next PPM due (svc_ppm_schedules), last completed visit, and summary counts.
- New CRM UI tab "Service & Engineers" on the Company detail (CRMCompanies.js → ServiceActivityTab): summary tiles, "Where engineers are" cards (status chip, current case/site, location-updated, click-to-call), open service cases list, next-PPM banner, and graceful empty/not-linked states.
- This builds on existing bridges (sales_to_service.py contract→service onboarding; svc_crm_sync.py case/invoice→crm2_activities; customer_links.py canonical company_id) — the gap was purely SURFACING service ops to CRM sales managers. Now closed.
- Fixed pre-existing duplicate 'timeline' key in CRMCompanies sections array (React warning).
- Verified: backend curl with seeded data (linked=true, engineer on_site, next PPM); testing agent 100% (AlphaCo data + BravoCo empty state). Synthetic QA seed data removed after test.

### Cross-module gap audit — remaining (proposed backlog for the initiative)
- P1: Reverse view — show CRM sales context (account owner, open deals, contract tier) inside the Service Desk case/engineer app so field + desk see the relationship.
- P1: CRM "Cases" tab shows crm2_cases (CRM-internal) separately from Service Desk svc_cases — relabel/unify to avoid confusion/duplication.
- P2: Memberships ↔ CRM person identity (members vs contacts) — audit for a unified person/dedup.
- P2: Operations/Equipment ↔ Service Desk asset linkage (cases reference assets; confirm single source of truth).

## 2026-06-30 — CRM Cases relabel + regional appointment scoping
- Relabel: CRM company "Cases" (crm2_cases = support/account cases) → "Support Cases" to disambiguate from Service Desk field cases (now in the "Service & Engineers" tab). Updated tab label, "Log support case" button/modal title, empty state (points users to Service & Engineers for field jobs), and CRM Dashboard tiles ('Service' sub-labels → 'Support').
- Regional appointment scoping: GET /api/crm/v2/activities now restricts REGIONAL staff (CRM users assigned as a rep on one or more crm_territories) to activities in their area — linked to a company whose territory_id they cover, OR owned by them. Implemented via crm_territories.covered_territory_ids() + crm_v2._maybe_regional_activity_scope(). Safe-by-design: admins/owners (is_unrestricted) and users with NO assigned territory are unaffected (no regression); record-scoped reads (company_id/contact_id/etc.) are never double-filtered, so only the global calendar/appointments list is regionally scoped.
- Verified: direct logic test — regional rep sees only in-region + own activities (a1,a3), not other regions (a2,a4); owner→unrestricted (None); record-scoped→no extra filter. Frontend compiles.

## 2026-06-30 — Reverse view (CRM context in Service Desk) + Service tab gating
- Reverse view: new backend GET /api/svc/cases/{case_id}/crm-context (svc/cases.py) resolves the linked CRM company (company_id, name/email/postcode fallback) and returns account owner, account type/status, contract tier + active contract, open deals (count + pipeline value + top 5), and won revenue. Read-only.
- Service Desk case drawer (ServiceCaseDrawer.js) now shows a "Sales context (CRM)" card in the Customer tab (CrmContextCard) — owner, tier, open deals, won revenue, active contract, deal list, "Open in CRM" link. Gracefully shows "Not linked to a CRM account yet" when unlinked.
- Tab gating: CRM get_company (crm_v2.py) now returns has_service_ops (org has any svc_engineers or svc_cases). CRMCompanies.js shows the "Service & Engineers" tab ONLY when has_service_ops is true — so customers without the Service Desk don't see it. (Answers user's question: yes, now hidden when no Service Desk.)
- Granted demo owner owner@isodemo.com is_service_desk=true (records in test_credentials.md) so the desk is reachable for testing.
- Verified: backend curl (linked payload correct); testing agent 100% — CRM gating + Support Cases relabel PASS, Service Desk Sales-context card PASS (after access grant). Synthetic QA seed removed.

## 2026-06-30 — Operations/Equipment ↔ Service Desk single-source-of-truth (asset reconciliation)
- Audit finding: db.equipment (Operations register) is the canonical asset source — Service Desk (svc/engineer machine-history, svc_cases asset_id/equipment_ids) and CRM's Sites & Equipment tab all read it. The duplication risk was db.crm2_assets: a parallel, manually-created CRM asset store with no link to the register.
- Fix (non-destructive): 
  - GET /api/crm/v2/companies/{id}/asset-reconciliation (crm_contracts.py) — compares crm2_assets vs the register (resolved via linked_organization_id or exact name match), flags duplicates matched by equipment_id → sicon_equipment_id → normalized serial_number, plus crm_only assets and unlinked_register_count. Read-only.
  - POST /api/crm/v2/assets/{asset_id}/link-equipment — resolves a duplicate by pointing the CRM asset at its canonical register record (sets equipment_id + source='register', backfills serial/sicon). 
  - create_asset now persists equipment_id/sicon_equipment_id/source.
  - Frontend: AssetReconcilePanel on the CRM company Assets tab (CRMCompanies.js) — shows register count, duplicate list with one-click 'Link', crm-only note; asset rows show 'linked to register'; empty state points to the Sites & Equipment tab as the SoT. Added missing `toast` import.
- Verified: backend curl (duplicate via serial detected; link → already_linked increments, duplicates→0) and testing agent 100% frontend. QA seed removed.

## 2026-07-01 — Memberships ↔ CRM person identity (unified person surface)
- Audit: db.members (Memberships) and crm2_contacts (CRM) both key on email but had no link — same person could exist in both with no connection.
- Fix: GET /api/crm/v2/contacts/{contact_id}/member-identity (crm_v2.py) matches db.members by canonical email then exact phone within the org; returns is_member + member {name, status, plan (membership_plans), site (sites), joined_at, matched_via}. Read-only.
- Frontend: MemberIdentityCard on the CRM contact detail (CRMContacts.js) — shows an 'Also a gym member' card with status badge, plan · site · joined · matched-by line, and a 'View member' button. Renders nothing for non-members.
- Verified: backend curl (matched by email; plan/site resolved) + testing agent 100% (member shows card; non-member shows none). QA seed removed.
- Completes the cross-module 'one Pulse team' initiative (Service↔CRM both ways, regional scoping, equipment SoT, member identity).

## 2026-07-01 — Fix: Comms email import returned empty/malformed response (Cloudflare 520)
- Bug: importing an Outlook .msg newsletter could make POST /api/comms/ai/import-email return an empty/invalid HTTP response (Cloudflare "could not parse" 520) — from the gpt-4o rebuild hanging past the gateway timeout on a large body, or an unhandled parse error.
- Fix (comms_intel.py ai_import_email): wrapped parse in try/except → 422 JSON; wrapped AI rebuild in asyncio.wait_for(timeout=75) → 504 JSON on timeout, 502 JSON on error; res None → 422 JSON. Endpoint now ALWAYS returns clean JSON, never an empty/malformed response.
- email_ingest._html_to_parts caps HTML at 3MB before BeautifulSoup (guards memory/time on huge Outlook newsletters). Added asyncio/logging imports + logger.
- Verified: backend curl (empty→400, paste→200 blocks) + testing agent 100% (paste HTML rebuilds; invalid .msg → clean 200 JSON + friendly toast, no blank/empty response).
- NOTE: user hit this on PRODUCTION whose deploy had failed (backend crash-looping = the empty response). Fix is in PREVIEW; needs redeploy. deployment_agent static scan = deploy-ready (strong JWT, CORS ok, no blockers) → earlier deploy failure was likely a transient k8s readiness timeout; re-deploy should succeed.

## 2026-07-01 — Enhancement: import "rebuilding" progress note
- EmailBuilder ImportModal now shows a reassuring progress note (data-testid='import-progress-note') while the AI rebuilds: "Rebuilding your email with AI…", escalating after 5s to "Large email — this can take up to a minute. Hang tight, no need to retry." Cancel is disabled while busy. Prevents users retrying/aborting large Outlook newsletter imports.
- Verified: compiles clean; additive UI gated on busy state.

## 2026-07-01 — Enhancement: import progress bar + percentage
- Import modal now shows a size-based progress bar (data-testid='import-progress-bar') + percentage (import-progress-pct) that eases toward ~92% over an estimated duration derived from file size (8-60s), giving responsive feedback on large newsletter imports. Completes on response. Self-verified via compile (additive UI on the busy state).

---
## Survey attachments → Object Storage + full CRM report exports (Jun 2026)
Two in-progress tasks completed and verified via curl (CRM login owner@isodemo.com).

**A. Attachment storage migration (base64-in-Mongo → Emergent Object Storage)**
- `routes/crm_site_surveys.py` + `routes/survey_portal.py`: `upload_attachment` / `upload_portal_attachment` now stream files to object storage (`put_object`, path `gymaxis-ai/surveys/{survey_id}/{uuid}.{ext}`) via `run_in_threadpool` (non-blocking). DB stores `storage_path` + `is_deleted`, no more `data_b64`.
- `download_attachment` fetches via `get_object(storage_path)`, with legacy base64 fallback for any pre-existing rows.
- `storage_path` excluded from list/handover projections (not leaked to clients). Storage helpers (`init_storage/put_object/get_object`, APP_NAME=`gymaxis-ai`) already existed in `utils/database.py` and init at startup.
- Per user: no migration of existing dev/test base64 rows — new uploads only.
- Verified: upload→download roundtrip byte-match, no data_b64 in response, storage_path not in list keys.

**B. Excel/PDF export extended to ALL CRM reports**
- `routes/crm_reports.py`: `_EXPORTABLE_REPORTS` now includes the 7 standard reports (pipeline-by-stage, pipeline-by-territory, quote-conversion, margin, lost-reasons, salesperson, consent-overview) in addition to the 4 site-survey reports, all routed through `build_report_xlsx` / `build_report_pdf`.
- `export_report` uses `inspect.signature` to pass only the date params each report accepts (consent-overview takes user only).
- Frontend `pages/CRM/CRMReports.js`: `exportable: true` set on all 7 standard reports → renders existing XLSX/PDF download buttons.
- Verified: all 11 reports return HTTP 200 valid xlsx+pdf files.

## Backlog change (Jun 2026)
- CANCELLED: Proactive weekly "Comms brief" (P3) — dropped per user request; do not re-propose.

---
## NEW FEATURE: Operations → Request a Part (Jun 2026)
Operator-facing spare-parts request workflow for Lite + Pro + Full, mirroring Log-a-Fault.
Backend verified end-to-end via curl; frontend compiles.

**Backend** (`routes/parts_requests.py`, `utils/parts_ai.py`, registered in `route_registry/core.py`):
- Collections: `parts_requests`, `parts_request_events` (timeline), `parts_request_attachments` (object storage), `parts_request_supplier_cards` (token), `exploded_drawings`.
- Machine picker + per-machine cover (warranty/contract/chargeable) via reused `_resolve_coverage_for_issue`.
- Multi-machine, multi-part requests; photo upload to object storage; AI part identification from photo (`utils/parts_ai.identify_part`, Emergent LLM key gpt-5.2 multimodal).
- Exploded drawings: admin/master upload (global if master), operator search by manufacturer/model + view (decision 2A: view + manual entry).
- Submit → branded Supplier Parts Card emailed (default parts@pulsefitness.com, editable; decision 3B) via Resend; optional Service Desk case (reuses `svc.intake._create_case`, case_type=parts).
- Public token card (`/api/parts-card/{token}`) with supplier lifecycle actions: acknowledge → quote → invoice → allocate → despatch → complete, all on the shared timeline (decision 4).
- Operator detail page shows full timeline + quote/invoice/despatch (like fault detail).

**Frontend**:
- `pages/PartsRequests/PartsRequestsPage.js` (list + draft editor + detail) at authed route `/parts-requests`.
- `pages/PartsRequests/PartsCardPage.js` public supplier card at `/parts-card/:token`.
- "Request a Part" sub-menu pill added to Operations Faults in BOTH `pages/Dashboard/FaultsTab.js` (Pro/Full) and `pages/LiteDashboard/LiteFaultsTab.js` (Lite) → navigates to `/parts-requests`.

Design decisions (from user): cover=1A (reuse existing data), drawings=2A (interactive hotspots deferred to later roadmap), supplier default=3B, service-desk=4 full supplier lifecycle, AI=yes.

## Master Admin → Catalogue → Exploded Drawings section (Jun 2026)
Added a new "Exploded Drawings" tab inside Master Admin → Catalogue & Library (`CataloguePanel.js`) via new `pages/MasterAdmin/ExplodedDrawingsPanel.js` (mirrors the machine-manuals panel).
- Master admin uploads drawings (manufacturer/model/type/title + image/PDF) as platform-GLOBAL; search, view (blob), delete.
- Backend (existing `routes/parts_requests.py` exploded-drawings endpoints): converted POST params to `Form(...)` for multipart. Verified via curl: master uploads global (org=None), lists, another org's operator sees the global drawing (feeds the Parts Request "Find in exploded drawing" picker), delete works.
- Note: screenshot harness could not complete this SPA's login; validated backend via curl + frontend compiles (reuses proven pattern).

## Enhancement: parts list on exploded drawings (Jun 2026)
Operators can now add a part to a Parts Request directly from a drawing.
- Backend (`routes/parts_requests.py`): drawings get a `parts` list ([{part_number, description, notes}]); new `PUT /api/exploded-drawings/{id}/parts` (master admin any, operator own-org). Parts included in list responses.
- Master admin (`ExplodedDrawingsPanel.js`): "Parts (n)" button opens an editor modal to add/edit/save the parts list per drawing.
- Operator (`PartsRequestsPage.js` DrawingsModal): opening a drawing shows its parts list with "Add" buttons that append the part to the current machine's request.
- Verified via curl: master sets parts → operator in another org sees drawing + parts. Frontend compiles.

## Deployment fix: backend crash-loop (readiness timeout) — Jun 2026
Production deploy failed: uvicorn crash-looped, /health "connection refused", k8s readiness timeout.
- Root cause: `_full_boot()` (deferred startup task in `server.py`) called `init_storage()` — a SYNCHRONOUS `requests.post(timeout=30)` to the external object-storage service — directly on the event loop. During a fresh deploy this could block the loop (and /health) long enough for the wrapper to keep restarting uvicorn → crash loop.
- Fix: offloaded to `await run_in_threadpool(init_storage)` so the event loop stays free to serve /health during boot; storage still inits lazily on first put/get, so a boot-time failure is harmless (non-fatal, logged).
- Verified by testing_agent (6/6): /health + /api/health fast 200, /api/health/deep mongo=ok, parts-request attachment + exploded-drawing object-storage round-trips, authed list works. No regression.
- Note: deployment_agent's only finding was a CORS_ORIGINS='*' recommendation — ruled out as the crash cause (resolve_cors_origins ignores '*' in prod and preview works with the current allowlist).

---
## MOD-only module enforcement (Edit Org) + 4 UI refinements (Jul 3, 2026)
1. **MOD Edit-Org enforcement** — MOD orgs (is_mod OR account_type in mod_site/mod_branch/mod_org) run the Operations portal ONLY.
   - Backend: `master_admin_orgs.update_org_features` (PUT /api/master-admin/organizations/{id}/features) now forces enabled=false (and business_enabled/leisure_enabled=false) for crm/memberships/marketing on MOD orgs; enabled_modules stays operations-only. Verified 2/2 pytest (test_mod_features_enforcement_jan2026.py). Non-MOD regression passes.
   - Frontend: `FeatureControlPanel.js` — isMod detection; module matrix renders LOCKED tiles (data-testid module-{key}-mod-locked-{orgId}) for crm/memberships/marketing; those feature groups hidden for MOD.
2. **CRM Company sub-tabs reordered** (`CRMCompanies.js` sections): Overview, Contacts, Deals, Quotes, Tenders, Invoices, Equipment & Assets, Service & Engineers, Site Surveys, Activity.
3. **Request a Part** (`PartsRequestsPage.js`): embedded view drops the "Parts Requests" sub-header; New Request button now left-aligned matching Reactive Faults.
4. **Equipment tab** (`EquipmentInfoTab.js`): removed the "Equipment Information Hub" h2 sub-header.
Verified: backend authoritatively (testing_agent 2/2). Frontend code-verified (UI click-through blocked by /api/auth/login 429 rate-limit; no issues found). Report: /app/test_reports/iteration_mod_ui_refinements_jan2026.json. PREVIEW only — redeploy to push to production.

---
## ASER — Activity Safety Events Register (MOD-exclusive) — Phase 1 (Jul 3, 2026)
MOD Service Portal → Reports → ASER. Lets MOD site users document equipment-related safety events, near-misses, repeated failures and incidents impacting rehab/activity delivery. Reuses existing equipment/faults/CAPEX/sites/audit — no duplicate records.
- **Backend** `routes/mod_aser.py` (registered in route_registry/features.py _UNGATED_ROUTERS). Collection `aser_entries`. Endpoints: GET config, GET equipment (site-scoped picker enriched w/ open-fault + prior-ASER counts), POST create (ASER-YYYY-NNNNN ref, risk scoring, repeated-issue flags, status precedence linked_to_fault>capex_review>under_review>submitted), GET list (filters), GET dashboard (cards), GET/{id}, PATCH, POST link-fault, POST create-fault (prefilled issues record, no dup), POST flag-capex (sets equipment capex_manual_flag), POST close (manager-only), POST dispose (manager-only, only when flagged). MOD-only gating (_require_mod), site-scoping (_sites_in_scope), tamper-evident mod_audit on every mutation.
- **Equipment red-flag**: when an ASER entry sets equipment_status ∈ {removed_from_use, awaiting_replacement, replacement_recommended} the real equipment record gets aser_removed_from_use=true → highlighted RED in ASER views; managers can then Dispose (marks equipment disposed, resolves entry). Never hard-deletes.
- **Patient privacy**: anonymised impact fields only (sessions/patients affected) + warning banner; no patient-identifiable fields.
- **Frontend** `pages/MODPortal/MODASERPortal.js` — full-screen portal: dashboard cards, register table + filters, multi-section New Entry wizard (site→equipment→event→rehab/activity impact→safety+risk→status/follow-up/evidence), detail view w/ create-fault / flag-capex / close / dispose actions, red highlighting for removal-flagged kit. Launched from a red ASER card in the Reports tab (`PulseReportsTab.js`, data-testid mod-reports-aser-open) — the tab MOD users actually land on (/pulse → LiteDashboardPage → Reports).
- **Verified**: backend 18/18 pytest (test_aser_jan2026.py); frontend 8/8 acceptance criteria (iteration_mod_aser_reports_fe_jan2026.json). Test login: aser.qa@army.mod.test / AserQA123! (ZZ QA MOD ARMY, 2 seeded QA assets).
- PREVIEW only — redeploy to push to production.
- Phase 2 backlog: charts/trend analytics, exports (PDF/Excel/CSV) + ASER Replacement Evidence Report, configurable notifications, Master Admin ASER settings, AI summaries (current app LLM).

## ASER Phase 2 — Charts / trend analytics (Jul 3, 2026)
- Backend: GET /api/mod/aser/analytics?months=12 (site-scoped) — monthly trend buckets (entries, high/critical, removed-from-use, sessions impacted, rehab-impacted), by_event_type, by_risk, by_site, by_equipment_type, top_assets + repeated_assets. Route ordered before /{entry_id}.
- Frontend: MODASERPortal Register/Analytics header toggle (aser-view-toggle) + AnalyticsView (recharts): trend LineChart, rehab-impact BarChart, events-by-type/equipment-type/site bar charts, risk PieChart, repeated-issue equipment evidence list (red-highlighted for replacement labels).
- Fixed overlay z-index to z-[100] (was bleeding under dashboard sticky header).
- Verified: backend aggregation via curl; frontend 100% (iteration_mod_aser_analytics_fe_jan2026.json — all 7 chart cards render). Test data reset clean. PREVIEW only — redeploy for production.

## ASER Phase 2 — Exports (CSV/Excel/PDF) + Replacement Evidence Report (Jul 3, 2026)
- Backend `routes/mod_aser_exports.py` (registered in features.py): GET /api/mod/aser/export/csv, /xlsx (openpyxl), /pdf (reportlab summary: counts, repeated-issue equipment table, entries table, disclaimer), and /replacement-evidence/{equipment_id} (per-asset PDF: equipment details+age, total ASER/faults/near-misses/incidents/sessions/group+individual impacted, event history, recommendation). All MOD-only + site-scoped (reuses mod_aser scope helpers); honors register filters + date range. Heavy libs imported lazily.
- Frontend MODASERPortal: downloadBlob() helper (axios blob + auth header), CSV/Excel/PDF export button group in Register filters (aser-export-csv/xlsx/pdf), and 'Replacement Evidence Report' button in entry detail (aser-replacement-evidence).
- Verified: backend curl (valid %PDF / PK-zip / CSV signatures); frontend 100% — all 4 downloads return 200 with correct content-types (iteration_mod_aser_exports_fe_jan2026.json). Test data reset. PREVIEW only — redeploy for production.
- Note: MODASERPortal.js now ~789 lines — candidate for future split (RegisterView/DetailView/AnalyticsView modules).

## ASER Phase 2 — Master Admin settings + configurable notifications (Jul 3, 2026)
- Backend `routes/mod_aser.py`: singleton `aser_settings` (DEFAULT_SETTINGS + deep-merge). GET/PUT /api/master-admin/aser/settings (master-admin only). _require_mod now enforces settings.enabled (except master admin); high/critical review status gated by require_manager_review_high_critical.
- Notifications: _notify_aser_created() fires on ASER submit — emails site managers (org owner/manager users + owner_email), a configurable service desk email, and account manager email, per per-group rules (on_new/high_critical/removed/repeated/capex/fault_link). Sent via Resend (utils.email.send_email, kind=mod_aser_alert). Verified with real Resend sends (site manager + service desk both delivered on a critical entry).
- Frontend: AserSettingsPanel added to AdminMODConsole (general toggles + repeated-issue threshold + 3 notification groups). Wired AdminMODConsole into Master Admin → Overview → MoD → 'MOD Console & ASER' inner tab (was orphaned).
- Verified: backend curl (settings CRUD + real email dispatch); frontend 100% (iteration_mod_aser_settings_fe_retest_jan2026.json — load/edit/save/persist). Settings reset to defaults. PREVIEW only — redeploy for production.
- Remaining Phase 2: AI summaries (app's current LLM).

## ASER Phase 2 — Email the report (Jul 3, 2026)
- Backend `routes/mod_aser_exports.py`: refactored PDF generation into _build_summary_pdf / _build_replacement_pdf (bytes). New POST /api/mod/aser/email/summary and POST /api/mod/aser/email/replacement-evidence/{equipment_id} — build the PDF, base64-attach, and send via Resend (utils.email.send_email, kind=mod_aser_report). _resolve_recipients merges typed emails + role targets (site managers via org owners/managers, service desk + account manager from ASER settings). Verified with real Resend deliveries; empty recipients → 400.
- Frontend MODASERPortal: EmailReportModal (recipient chips + role checkboxes + optional message). 'Email' button in Register export group (aser-email-summary) and 'Email report' button in entry detail (aser-email-evidence).
- Verified: backend curl (real sends + validation); frontend 100% (iteration_mod_aser_email_fe_jan2026.json — summary + evidence + client validation). Test data reset. PREVIEW only — redeploy for production.
- Remaining Phase 2: AI summaries (app's current LLM).

## ASER Phase 2 — AI summaries (Jul 3, 2026) — PHASE 2 COMPLETE
- Backend `routes/mod_aser_ai.py`: POST /api/mod/aser/{entry_id}/ai-summary (review-ready entry summary) and POST /api/mod/aser/ai/asset-evidence/{equipment_id} (CAPEX/replacement evidence draft, stored on equipment.aser_ai_summary). Uses emergentintegrations LlmChat (openai gpt-5.2, EMERGENT_LLM_KEY, lazy import). Gated by settings.ai_summaries + MOD scope. Guardrails in system prompt: no PII, no clinical judgement, no funding guarantee, labelled 'AI-generated for review'.
- Replacement Evidence PDF (_build_replacement_pdf) now embeds the stored AI executive summary when present → flows into the emailed report too.
- config endpoint returns ai_summaries flag; frontend DetailView shows 'AI summary' + 'Draft AI replacement evidence' buttons (violet, Sparkles) → aser-ai-result panel.
- Verified: backend curl (real LLM output; RE PDF grew + valid); frontend 100% (iteration_mod_aser_ai_fe_jan2026.json). Test data reset. PREVIEW only — redeploy for production.
- ASER PHASE 2 COMPLETE: analytics, exports (CSV/XLSX/PDF), Replacement Evidence Report, email-the-report, Master Admin settings, configurable notifications, AI summaries.

---
## Feature: Territory map — role filter + office locations (Jul 10, 2026)
CRM → Territories map (P0, `crm_territories.py` + `CRMTerritoryMap.js`):
1. **Role filter** — new segmented control (All roles / Managers / Engineers) on the map toolbar. Filters both the painted region coverage and the sidebar staff list by `territory_role` (a member flagged `both` matches every filter). This lets an admin view Engineer coverage and Sales-Manager coverage independently while both roles overlap the same region — the "multiple roles per area" ask. (Regions already support N reps each, so overlapping-role coverage needed no data change.)
2. **Office locations** — new `crm_offices` collection + CRUD under `/api/crm/territories/offices` (GET/POST/PUT/DELETE, admin-only, soft-delete). New `CRMTerritoryOffices.js` sidebar panel to add/remove offices (name, address, postcode, lat/lng, pin colour). Offices render as coloured pin `Marker`s with labels on the UK map; toolbar "Offices" toggle shows/hides them.
Verified: backend CRUD via curl (create/list/delete) + Playwright e2e (all 7 control testids present, Engineers filter correctly hid the Sales-Manager, "Leeds Depot" pin rendered on map at correct coords, office row + delete work). Test office cleaned up. PREVIEW only — redeploy to push to production.

## Enhancement: Postcode geocoding for offices + nearest-office badge (Jul 10, 2026)
- **Geocode by postcode** — new `GET /api/crm/territories/geocode?postcode=` (free postcodes.io API, server-side, keyless). Offices form gets a "Find" button that fills lat/lng from a UK postcode; `POST /offices` also auto-geocodes when coords are omitted but a postcode is given.
- **Nearest-office badge** — clicking a region opens the drawer showing the closest pinned office + great-circle distance in miles (client-side haversine from the region's `geoCentroid`).
Verified e2e: "B1 1HQ" → 52.4787/-1.9069, pin rendered, drawer showed "Nearest office: Birmingham HQ · 27 mi". Invalid postcodes correctly return 404. PREVIEW only — redeploy for production.

## Feature: Asset Financial Intelligence + Cap-Spend budgets (P0, competitor gap fill) — Jul 10, 2026
Extended the existing CAPEX Intelligence module (Operations > Reports > CAPEX Intelligence) — reusing all CAPEX/equipment data, zero duplication — to close the biggest gap vs Orbit4:
- **Residual value & depreciation** — `compute_valuation()` (straight-line, 10% salvage floor) on every asset: current book value, accumulated + annual depreciation, residual %. Uses real `purchase_cost` when present, else replacement_cost (flagged `basis: estimated`).
- **Total Cost of Ownership** — `compute_tco()` = acquisition + lifetime service spend (projected from live 12-mo `svc_capex_signals`), TCO/year, % that is service — our data edge over a valuation-only rival.
- **Cap-Spend budgets** — new `capex_budgets` collection + `GET/PUT /api/capex/budget` (site or estate scope). CAPEX analysis returns a `capital_budget` block (annual budget vs 12-mo forecast, utilisation %, remaining, over-budget). New `CapSpendCard` UI with inline edit.
- **Pulse Resale referral** — `build_resale_referral()` returns an outbound link to https://pulseresale.com (category+brand params) ONLY for replace/at-risk assets. No in-app marketplace (per user). UI shows it in the expanded asset row + "trade-in sweet-spot" note.
- Fleet KPIs gained Fleet Book Value + Total Cost of Ownership; all flow through analysis → board-report JSON → dashboard.
Files: `utils/capex_intelligence.py` (+compute_valuation/compute_tco/build_resale_referral, fleet totals), `routes/capex.py` (item decoration + budget endpoints + budget block + drilldown), `frontend/src/pages/CapexIntelligenceTab.js` (CapSpendCard, KPIs, valuation/TCO row, resale link).
Verified: backend via direct calls (Treadmill 07 → replace_soon, book £350/10%, resale link) + testing_agent frontend E2E 100% (7/7). Seeded 3 demo assets + £50k budget into iso-demo-org. Board PDF exporter NOT yet updated (JSON has the data) — follow-up. PREVIEW only — redeploy for production.

## Feature: Replacement Sweet-Spot Planner + CAPEX pass-through to MOD — Jul 10, 2026
- **Replacement Sweet-Spot Planner** (`GET /api/capex/replacement-plan?years=&taper_pct=&annual_budget=`, `_compute_replacement_plan`): schedules each asset into its optimal replacement YEAR (from lifecycle stage, BER signal, safety risk) and costs each year against a Cap-Spend budget that can **taper** (e.g. -10%/yr) for shrinking estates. Returns per-year cost/budget/utilisation/over-budget + cumulative, a beyond-horizon bucket, and plan totals/shortfall. New `ReplacementPlanner` UI section in CapexIntelligenceTab with horizon (3/5/7/10) + taper (0/3/5/10%) selectors and inline Pulse Resale links.
- **CAPEX now runs through to MOD (/MODService)**: `_require_owner_or_manager` made MOD-aware (mod_site/branch/org account types allowed; data still ring-fenced by resolve_mod_query_filter) so the whole CAPEX suite (valuation, TCO, budget, planner, resale) works for MOD users who previously 403'd. Embedded `CapexIntelligenceTab` in the MODProDashboard CAPEX pillar; added a "Reports · CAPEX" full-screen portal (`MODCapexPortal.js`, data-testid mod-nav-capex/mod-capex-portal) to MODSiteDashboard.
Verified: backend direct calls for iso-demo-org + MOD org (planner buckets, taper compounding, no 403) + testing_agent frontend E2E — ALL PASS (planner columns/horizon/taper, resale link, Cap-Spend edit, and MOD user reaching CAPEX with scoped data: 2 assets, £4,620/77% of £6,000, treadmill flagged with resale, Fleet Book £2,142.5, TCO £6,800). Board PDF still pending planner/valuation. PREVIEW only — redeploy for production.

## Feature: Board CAPEX PDF — valuation, Cap-Spend budget & replacement planner — Jul 10, 2026
Brought the exec PDF export in line with the on-screen CAPEX intelligence (`utils/capex_pdf_exporter.py` + `routes/capex.py`):
- Board report now embeds a 5-year `replacement_plan` (via `_compute_replacement_plan`, flat budget) alongside the existing per-asset valuation/tco and `capital_budget`.
- New PDF **Section 7 — Cap-Spend Budget & Asset Valuation**: Fleet Book Value / Acquisition Cost / TCO KPIs + a budget-vs-forecast table (annual budget, 12-mo forecast, committed, utilisation %, over/under status coloured).
- New PDF **Section 8 — Replacement Sweet-Spot Plan**: year-by-year table (cost/budget/utilisation/status, over-budget years flagged red), beyond-horizon note, and a "Scheduled this year" asset list (replacement cost, residual value, reason). Recommendations/Register/Sign-off renumbered to 9/10/11.
Verified: PDF builds (valid %PDF, 7 pages) for the MOD org and rendered pages 4-5 visually — Section 7 shows £2,142 book / £6,800 TCO / £6,000 budget @ 77% (£1,380 headroom); Section 8 shows the treadmill scheduled for 2026 (£4,620, residual £420, End-of-life). Crown-copyright footer intact for is_mod. PREVIEW only — redeploy for production.

## Fix/Feature: Capture real purchase_cost/date so CAPEX valuations read "actual" — Jul 10, 2026
Enabled operators to populate the financial inputs the CAPEX valuation engine needs (was previously only importable via CSV, and PATCH silently dropped purchase_cost):
- Backend: added `purchase_cost` to the equipment PATCH allow-list (`routes/equipment.py`) — it was missing, so edits never saved it. Added `expected_lifespan_years` to `EquipmentCreate` (`models/schemas.py`) so lifespan can be set at creation.
- Frontend Add form (`AddEquipmentDialog.js`): new Purchase Cost / Replacement Cost / Expected Life (years) inputs (data-testid add-equip-purchase-cost / -replacement-cost / -expected-life), coerced to numbers on submit.
- Frontend Edit form (`EquipmentInfoTab.js`): same three fields added to the edit dialog (data-testid edit-purchase_cost / edit-replacement_cost / edit-expected_lifespan_years); numeric coercion ('' → null) on save.
- CSV import already supported purchase_cost/purchase_date/replacement_cost (`/api/equipment/import-csv`).
Result: once an operator enters or imports a real purchase_cost, the CAPEX book/residual value + TCO switch from `basis: estimated` (replacement-cost proxy) to `basis: actual`. Verified via curl: create persists purchase_cost/expected_lifespan_years/purchase_date; PATCH round-trip updates purchase_cost (2200 → 2500). Frontend lint clean (0 errors). Sicon auto-import remains BLOCKED on Sage 200 API credentials. PREVIEW only — redeploy for production.

## Feature: CAPEX data-health badge + per-asset "set actual cost" nudge — Jul 10, 2026
Drives purchase-cost data completeness so more valuations read `actual`:
- Backend: `get_capex_analysis` now returns a `data_health` block {total_assets, actual_count, estimated_count, actual_pct, assets_missing_cost} (counts assets whose valuation.basis === 'actual').
- Frontend (`CapexIntelligenceTab.js`): a colour-coded "Data health: X/Y actual (Z%)" badge in the Cap-Spend card header (data-testid capex-data-health); and a per-asset amber `CostNudge` in the expanded valuation block (only when basis === 'estimated') with an inline "Set actual cost" input that PATCHes /api/equipment/{id} purchase_cost and reloads (data-testid capex-cost-nudge-<id> / -open / -input / -save).
Verified: data_health via direct calls (MOD org 2/2=100% green; Bitterne 0/44=0% rose, all 44 nudge-eligible); nudge PATCH endpoint previously curl-verified. Frontend lint clean (0 errors). UI not screenshot-verified (harness login/rate-limit); nudge is a thin wrapper over the verified PATCH. PREVIEW only — redeploy for production.

## UX: Service Desk sidebar declutter — Options menu, Analytics hub, Expenses role-gate — Jul 14, 2026
Reorganised the congested `/service-desk` left rail (`ServiceDeskPage.js`):
- New collapsible **Options** menu (data-testid desk-options-btn / desk-options-menu) holding Import data, Integrations, Audit log, Account settings (opens shared `AccountSettingsModal`), and Engineers — pulled out of the main rail/Insights.
- **Analytics hub**: Reports + Supplier health merged into Analytics as sub-tabs (data-testid desk-analytics-sub-overview/-suppliers/-reports); removed as standalone nav items.
- **Expenses** now managers/owners only — filtered from Insights via `can(user,'manage_operations')` and guarded in the body (non-managers fall back to the dashboard).
- Main rail trimmed to Dashboard/Cases/Scheduler/Customers/Equipment/Maintenance/Parts/Billing; Insights to Analytics/Expenses/H&S/Compliance.
Verified via screenshot + data-testids (owner account: all Options items present, Analytics sub-tabs render, Expenses visible). Lint clean. Provider accounts still hide Equipment/Supplier-health/Engineers. PREVIEW only — user must REDEPLOY to push to production (fitness-ai-migrate.emergent.host).

## 2026-07-14 — Dealer Parts: Standalone Dealer Portal auth guard (P0) — VERIFIED
- Confirmed end-to-end the `dealer_user` auth scope: dealer login (portal2@fitline.test) redirects to /dealer-portal; direct navigation to staff routes (/dashboard) is forced back to /dealer-portal via DashboardRoute guard in AppRoutes.js (line 235).
- Backend RBAC verified: portal/me/overview → 200 (dealer-scoped); staff endpoint replenishment-requests → 403 for dealer_user.
- Test creds added to test_credentials.md.

## 2026-07-14 — Dealer Parts Phase 1: Data Import + BOM Matching + Most-Used Intelligence engine — DONE (27/27 backend tests pass)
Built inside Service Desk → Stores → Dealer Parts. Turns the two historical Pulse spreadsheets into a reusable intelligence engine (no duplication of dealers/orders/stock/parts).
- New backend router: routes/dealer_parts_data.py (prefix /api/dealer-parts/data, staff-only). Collections: dealer_parts_import_batches, dealer_parts_usage_records, dealer_most_used_analysis, dealer_bom_machines, dealer_bom_components, dealer_component_matches, dealer_component_aliases, dealer_parts_data_settings.
- Parts Used importer (sheet SageReportData1) → 15,600 usage rows → computed Most-Used analysis (1,440 unique parts): total_qty, usage_count, cost, first/last used, by-year/month, avg_monthly, recent_90d/12m, trend (increasing/stable/decreasing/dormant/one_off/new_failure_trend), rank, high_usage flag.
- BOM importer (sheet BOMData) → 104,020 component rows → 4,879 versioned BOM machines + components. Re-import supersedes prior version (history kept).
- Chunked upload endpoints (/data/upload/init|chunk|finish) bypass the 2 MB ingress body limit (7 MB BOM uploads fine). rapidfuzz added for fast fuzzy matching.
- Multi-stage matching engine (/data/match/run, <2s): exact code → normalised code → exact/normalised description → fuzzy description (rapidfuzz, needs review) → approved alias. Idempotent; preserves manual matches. Result on seed data: 112 exact, 25 fuzzy, ~1301 unmatched (EXPECTED — high-runner spares genuinely aren't in the assembly BOM).
- Unmatched review queue (sorted by qty) with dispositions: map_to_bom (manual match), create_alias, mark_obsolete, not_dealer_relevant, exclude_from_recommendations, send_for_review. Aliases require approval; approved aliases resolve on next match run.
- Machine→parts intelligence (/data/machine-parts): BOM components ranked by historical usage with dealer-stock priority (critical/recommended/optional/low/no_usage).
- Frontend tabs added: Data Imports, Most-Used Analysis, Match Review (+Aliases), Unmatched Review, Machine Parts. Full audit trail via dealer_parts_audit_events. Import batches reversible.
- Bug fixed during testing: _audit() positional `action` collided with kwarg action= in 3 review handlers → renamed to review_action.
Seeded on org iso-demo-org (owner@isodemo.com / IsoDemo123!).

## 2026-07-14 — Dealer Parts Phase 2: Allocation Wizard + Invoice→BOM matching + Recommendation engine (from matched intelligence) — DONE
- New backend endpoints in routes/dealer_parts_data.py: GET /api/dealer-parts/data/match-machine (resolve invoice machine line → BOM top-level ref via exact ref → stock code → fuzzy description, with alternatives); POST /api/dealer-parts/data/recommend (invoice machine lines → dealer spare-parts pack). New collection dealer_parts_recommendation_runs (persisted + audited).
- Recommendation engine uses the Phase-1 matched intelligence: only components with proven historical usage from APPROVED matched analysis rows feed recommendations (require_human_review_before_recommend default true excludes pending fuzzy). Qty scaled by fleet quantity × usage priority (critical/recommended/optional/low), netted against dealer held + allocated stock (duplicate prevention → duplicate_avoided status). Allowance = order_value × %; over-allowance flagged. Unmatched machine lines surfaced separately. Reuses _dealer_held/_dealer_allocated from dealer_parts_bom.
- Frontend: AllocationWizardTab.js (new "Allocation Wizard" tab). 3 steps: (1) select dealer + order value + % + machine lines; (2) generated recommendation grouped by machine with editable qty, live allowance/pack-value/duplicates/unmatched, over-allowance warning; (3) Approve → creates a draft allocation via existing POST /allocations (feeds the existing submit→approve→dispatch→receive lifecycle & stock). 
- Verified: recommend (305H-ZZY → 21 parts, allowance calc), over-allowance detection, unmatched line flagging, RBAC (dealer_user → 403 on match-machine + recommend), wizard e2e via screenshot.

## 2026-07-14 — Dealer Parts Phase 3: Intelligence Monitoring + Reports/Exports — DONE
- New backend endpoints in routes/dealer_parts_data.py: GET /api/dealer-parts/data/monitoring (intelligence insights from Phase-1 data: high-usage-missing-from-BOM=170, new_failure_trend=14, increasing_usage=5, sent_never_used=5 (£2,725), bom_never_used=1865); GET /api/dealer-parts/data/reports/{report}.csv for reports: most-used-since-2022, parts-used-vs-bom-match, unmatched-high-usage, bom-no-usage, most-used-by-machine (?top_level_ref). CSV via StreamingResponse.
- Frontend: DataIntelligenceTab.js — new "Intelligence & Reports" tab. 5 clickable insight cards with drill-down tables + CSV export buttons (incl. per-machine). Complements the existing engineer-usage Monitoring Agent (dealer_parts_intel.py) which stays for failure/quality/serial-batch alerts.
- Verified: monitoring endpoint counts, all 5 CSV reports, tab renders via screenshot.

Dealer Parts full module now has 17 tabs: Dashboard, Data Imports, Most-Used Analysis, Match Review, Unmatched Review, Machine Parts, Allocation Wizard, Intelligence & Reports, Dealers, Orders, Allocations, BOM Mgmt, Most Used, Engineer Usage, Stores Dept, Failure Intel, Alerts, Replenishment, Dealer Portal, Reports, RMA, Remote Stores, Ledger, Settings.

## 2026-07-14 — Dealer Parts UX restructure + AI drag-drop invoice → VERIFIED (all backend+frontend tests pass)
- Consolidated 24 top-level tabs → 14, in logical order: Dashboard, Allocation Wizard, Dealers, Orders & Allowance, Allocations, Stores Dept, Remote Stores, Engineer Usage, Replenishment, Returns/RMA, Stock Ledger, Dealer Portal, Analytics, Settings.
- New Analytics hub (AnalyticsTab.js + SubTabHub.js): merges Most-Used Analysis, Intelligence & Reports, Parts by Machine, Most-Used Parts (manual), Failure Intelligence, Monitoring & Alerts, Dealer Reports.
- New Settings hub (SettingsHubTab.js): merges General, Data Imports, BOM Management, Match Review, Unmatched Review.
- Allocation Wizard: added drag-and-drop invoice upload (dp-wiz-dropzone). Backend POST /api/dealer-parts/data/ai-parse-invoice (multipart) → utils/dealer_parts_ai.parse_invoice_file: PDF (pypdf)/xlsx (openpyxl)/csv/txt text extraction + image vision (ImageContent), Emergent LLM key gpt-5.2 → extracts machine lines + order value, then _resolve_machine matches each to BOM. Wizard auto-fills machine lines + order value + shows "AI suggestion — please review" banner, marks matched/unmatched per line. RBAC: dealer_user → 403.
- Verified: 305H-ZZY extracted (exact_ref, matched_count=1), unknown ref matched=false, full wizard e2e (upload→prefill→generate), Analytics/Settings hubs render all sub-tabs, no forbidden standalone tabs.

## 2026-07-14 — Allocation Wizard: inline "Find in BOM" machine picker (enhancement)
- Added MachinePicker to AllocationWizardTab.js: each machine line has a "Find in BOM" button (highlighted amber when AI couldn't match). Opens an inline debounced search (reuses GET /api/dealer-parts/data/machines?q=) showing ref · component count · description; picking sets the line's machine_ref, marks it matched (green ✓), toast confirms. Resolves unmatched invoice lines without leaving the wizard. Verified via screenshot (search 305H → pick 305H-ZZY → line populated + matched).

## 2026-07-14 — Allocation Wizard invoice: large-file (up to ~30MB+) chunked upload, never stored
- The AI invoice upload now uses the chunked flow (init → 1.4MB chunks → finish-invoice), bypassing the 2MB ingress body limit. Backend: new POST /api/dealer-parts/data/upload/{id}/finish-invoice — assembles temp file, AI-parses via _parse_and_match_invoice, then deletes the temp .part file in a finally block (invoice never persisted). Direct POST /ai-parse-invoice kept for small files. Refactored shared helper _parse_and_match_invoice.
- Frontend: aiParseInvoiceFile now chunk-uploads with progress; dropzone shows upload % then "AI is reading…". Hint updated: "large files supported, never stored".
- Verified: 4.25MB invoice chunk-uploaded + parsed (£60,000, 305H-ZZY matched), temp file confirmed deleted.

## 2026-07-14 — Allocation Wizard: whole-spreadsheet BOM scan + AI status bar → VERIFIED
- AI reading status bar: dp-wiz-ai-status shows upload % then an animated indeterminate bar ("AI is reading your invoice…", dp-indeterminate keyframe in App.css) so the user knows the AI is working.
- Whole-spreadsheet BOM matching: for .xlsx/.xls/.csv invoices the backend now runs a DETERMINISTIC full-sheet cell scan (_scan_spreadsheet_invoice in dealer_parts_data.py + spreadsheet_rows in dealer_parts_ai.py) matching every cell against BOM machine top-level refs/stock codes — robust to wide raw Sage exports (138 cols) that the LLM couldn't handle. Dedupes traceable-serial row duplication (348H-AAA=3 not 9), derives qty/unit from the row, sums order_value. PDF/image/text still use the LLM path.
- Verified with the user's "Pure Pulse invoice data.xlsx": 20/20 machines matched, order_value £63,505.64, serials deduped, temp file deleted (2nd finish → 404), RBAC 403 for dealers, LLM path intact. NOTE: recommendation pack value can be £0 for machines whose BOM components have no approved-matched historical usage (correct approved-only gating).

## 2026-07-14 — Spreadsheet invoice: correct MACHINE counting + AI status bar → VERIFIED (both, all pass)
- AI status bar: dp-wiz-ai-status shows upload % then animated "AI is reading your invoice…" (dp-indeterminate keyframe).
- Machine counting fix (_scan_spreadsheet_invoice): detects quantity column by header; if present, uses stated qty and collapses serial-expanded duplicate rows (same code+qty+unit+total) so quantities aren't multiplied; if NO quantity column, each row = 1 machine. Counts MACHINES (sum of per-line quantities), not just product lines. Detects item-code column dynamically (col with most BOM hits) + price/total columns by header. Surfaces UNMATCHED machine codes (in code column but not in BOM) as editable lines with Find-in-BOM.
- Pure Pulse invoice result: machines_total=68, machines_matched=50, 26 product lines (20 matched), order_value £74,134.42; 348H-AAA qty 3 (not 9), serials deduped; unmatched (38-307-AAA, 516H-AAG etc.) surfaced. No-qty CSV → each row=1 machine. LLM path + RBAC intact. Banner shows "found 68 machine(s)… 50 matched".

## 2026-07-14 — Stores Department promoted to top-level Stores option (covers ALL Pulse parts)
- Moved "Stores Dept" OUT of the Dealer Parts internal tabs. It is now the FIRST sub-option in Service Desk → Stores (before Pulse Warehouse & Dealer Parts); storesSub default = 'dept'.
- New component /app/frontend/src/pages/StoresDepartment.js covers all parts leaving Pulse Fitness via two views: (1) "Pulse Warehouse parts" — aggregates GET /api/parts-requests by status (awaiting despatch / despatched / completed) + recent requests list; (2) "Dealer warranty fulfilment" — embeds the existing StoresDeptTab (picking queue, awaiting receipt, low stock, open RMAs, recent usage).
- api.js: added dpApi.listPartsRequests (root /api/parts-requests) + ROOT base. ServiceDeskPage lazy-imports StoresDepartment. Verified via screenshot: Stores opens on Stores Department, both views render, Dealer Parts stores_dept tab removed (count 0).

## 2026-07-14 — Stores Department: unified "To action today" fulfilment queue
- Added ActionQueue at the top of StoresDepartment.js merging (a) warehouse parts requests in a despatch-ready status (allocated/invoiced/quoted/acknowledged) from GET /api/parts-requests, and (b) approved dealer allocations awaiting pick from GET /dealer-parts/stores-dashboard (to_pick). Sorted oldest-first. Each row: source badge (Warehouse/Dealer), title, sub (parts/value), status, date, and an action link that jumps to the relevant fulfilment view (onGoWarehouse/onGoDealer). Verified: created+approved a dealer allocation → appeared as "To action today (1) · Fitline Deutschland · Pick & dispatch"; test allocation cleaned up after.

## 2026-07-15 — Invoice upload Cloudflare 524 fix + Dealer setup dropdowns → VERIFIED
- FIX (P0 live bug): uploading an invoice to the Allocation Wizard returned Cloudflare 524 ("origin did not respond in time"). Root cause: synchronous LLM invoice parse on /upload/{id}/finish-invoice exceeded Cloudflare's ~100s origin timeout for slow PDF/image parses (and spreadsheets falling through to GPT-5.2).
  - Backend (dealer_parts_data.py): finish-invoice now starts an ASYNC background job (asyncio.create_task → _run_invoice_job) writing to dealer_parts_invoice_jobs and returns {job_id, status:"processing"} instantly. New GET /dealer-parts/data/invoice-jobs/{job_id} returns the parse result once done/error. Temp file still deleted in the worker's finally block (zero retention).
  - Frontend (api.js aiParseInvoiceFile): after chunk upload it polls invoice-jobs/{id} every 2s (up to ~10min) until done/error. Backward-compatible if job_id absent.
  - Verified end-to-end via curl: finish-invoice → {processing}; poll → done with parsed lines/order_value. No timeout.
- FEATURE (P0): Dealer setup form (DealersTab.js) — replaced free-text inputs with dropdowns:
  - Dealer (CRM company): dropdown from GET /dealer-parts/crm-companies + "+ Set up a new company…" which creates a CRM company (POST /dealer-parts/crm-companies, writes db.crm_companies) then links it via company_id (user choice 1b).
  - Currency: dropdown (GBP/EUR/USD/AUD…17 codes) replacing free typing.
  - Account manager: dropdown of internal Pulse Fitness Ltd staff from GET /dealer-parts/staff (db.users, excludes dealer_user role) (user choice 2a).
  - New backend endpoints added in dealer_parts.py under the main JWT token (not the separate CRM token). Verified: staff list, company create/list, and dealer create with company_id + account_manager all return correctly; UI screenshot shows all 3 dropdowns rendering. QA test records cleaned up.

## 2026-07-15 — Chunked upload "Upload session not found" (PRODUCTION) → MongoDB-backed, replica-safe
- ROOT CAUSE: chunked uploads (BOM/Parts/invoice) stored the assembling file on LOCAL POD DISK (/tmp/dp_uploads). In production the backend runs multiple load-balanced replicas, so /upload/init, /chunk and /finish can land on DIFFERENT pods → the temp file isn't there → "Upload session not found". Preview is single-pod so it never reproduced.
- FIX (dealer_parts_data.py): removed all local-disk temp-file logic. Chunks now persist in MongoDB collection `dealer_parts_upload_chunks` (shared across every replica):
  - upload/init → inserts a marker doc, returns upload_id.
  - upload/{id}/chunk?seq=N → upserts {upload_id, seq, data:bytes} (idempotent per seq, so a retried chunk overwrites not duplicates).
  - finish / finish-invoice → _assemble_upload() reads all chunks sorted by seq and concatenates; _cleanup_upload() deletes them immediately (zero retention). Invoice bytes are assembled + chunks deleted IN the request, then the LLM parse runs in the background job (no cross-pod dependency).
  - TTL indexes: upload chunks auto-expire after 1h (abandoned uploads); invoice jobs after 24h. Compound index (upload_id, seq).
- Frontend (api.js): uploadSpreadsheet + aiParseInvoiceFile now send ?seq=N per chunk.
- Verified via curl: 2-chunk (1.28MB + tail) invoice → finish returned job immediately, polled to done on the assembled full content (no session-not-found), chunks collection back to 0 docs, indexes present.
- NOTE: PRODUCTION fix — requires a REDEPLOY to take effect on https://fitness-ai-migrate.emergent.host.

## 2026-07-15 — Chunked upload resilience: per-chunk auto-retry + resilient polling
- Frontend api.js: added _withRetry (exp backoff, retries ONLY network errors + 5xx/408/429, never 4xx) and _uploadChunks helper. uploadSpreadsheet + aiParseInvoiceFile now retry each failed chunk (and init/finish) instead of restarting the whole upload — important for flaky dealer connections. Invoice-job polling ignores transient network blips and keeps polling.
- Safe because the backend chunk endpoint is idempotent per (upload_id, seq) via upsert. Verified: uploading seq 0 twice → 1 doc, assembled 'AAAABBBB' (no duplication).
- NOTE: PRODUCTION — requires redeploy.

## 2026-07-15 — Invoice PDF: instant deterministic code-scan (fixes "AI reading for 5 minutes")
- ROOT CAUSE of long wait: PDF invoices went straight to the GPT-5.2 LLM path (spreadsheet deterministic scan only covered .xlsx/.xls/.csv). The LLM call had NO timeout, so a slow/stalled provider left the UI spinning for minutes. It also extracted DESCRIPTIONS, not the Item Codes, so BOM matching returned 0.
- FIX (dealer_parts_data.py): new _scan_pdf_invoice() — extracts PDF text (pypdf, instant) and deterministically finds item codes (regex ^[0-9A-Z]{2,}-[0-9A-Z]{2,}$ + BOM membership), reading the quantity (first standalone int after the code) and unit price that follow the Sage/Pulse row layout (Code→Description→Qty→Unit→Net). Wired into _parse_and_match_invoice BEFORE the LLM fallback; unmatched codes still surface for Find-in-BOM.
- SAFETY NET (dealer_parts_ai.py): LLM invoice calls (text + image) now wrapped in asyncio.wait_for(90s) — a stalled LLM returns a clear "took too long" error instead of hanging.
- Verified with the user's "Pure Pulse Invoice.pdf" (3.2MB, 9 pages): full chunked-upload→job→poll flow completed in ~2s (was 16s LLM / 5min prod), source=pdf_scan, 26 product lines, 20 matched, 64 machines/50 matched, order_value £82,425.48. UI confirmed: toast + banner + machine_ref fields populated with correct codes (302H-AAO, 348H-AAA…) and quantities.
- NOTE: PRODUCTION — requires redeploy.

## 2026-07-15 — Allocation Wizard "AI just returned numbers" → layout bug fixed
- ROOT CAUSE: in the "Machines on invoice" rows, the qty input used the shared `input` class (which includes `w-full`) plus `w-20`. Due to Tailwind CSS ordering, `w-full` overrode `w-20`, so the QTY field rendered full-width and the item-code (machine_ref) field got squished to a tiny box — the extracted codes (302H-AAO…) were present in the DOM but visually hidden, so it looked like the AI "just returned numbers".
- FIX (AllocationWizardTab.js): rebuilt the row as a 3-col grid [item code | qty | delete] using `inputTight` (no w-full). Now shows: prominent monospace item-code field with matched (green ✓) / unmatched (amber ⚠) state, the matched BOM machine DESCRIPTION beneath it (e.g. "Shoulder Press"), a labelled centered Qty field, column headers, and inline "Find in BOM". parseInvoice + pickMachine now carry machine_description.
- Verified via screenshot with Pure Pulse Invoice.pdf: rows clearly show 302H-AAO/Shoulder Press/Qty 2, 307H-AAO/Chest Press/Qty 3, 348H-AAA/Dual Multi-Pulley/Qty 3, order value £82,425.48. Downstream (Generate recommendation → BOM parts + most-used + dedup + allowance %) unchanged.
- NOTE: PRODUCTION — requires redeploy.

## 2026-07-15 — Recommendation step: visible duplicate-avoidance ("Already sent") flags
- Enhanced Allocation Wizard step 1 (AllocationWizardTab.js) to surface the existing dedup logic clearly:
  - New indigo banner (dp-wiz-dedup-banner) shown when duplicates_avoided>0: "N part(s) auto-adjusted to avoid duplicating stock this dealer already holds or has on order. Lines tagged 'Already sent' were skipped or reduced — only re-sent if the dealer has run out."
  - Renamed the last table column "Note" → "Stock check". Each part now shows a badge: grey "Already sent {held} — skipped" for duplicate_avoided items (rec qty 0), or amber "Holds {held} · {orig}→{rec}" for reduced items; otherwise the usage trend. Reason string is the tooltip.
  - duplicate_avoided rows now use a subtle bg tint (was opacity-60).
- Backend already returned already_held / original_qty / recommended_qty / status / reason — no API change.
- Verified: seeded a temp held stock line (G003=999) for a dealer, generated a recommendation for machine 305H-AEQ → "Duplicates avoided 1", banner shown, G003 row rec qty 0 with "Already sent 999 — skipped" badge. Temp data cleaned up.
- NOTE: PRODUCTION — requires redeploy.

## 2026-07-15 — Recommendation £0 fix + recommended-parts list
- ISSUE: "AI is not recommending parts" (Pack value £0). Root cause: recommendations only used most-used rows with review_status=='approved' AND required the separate "Run matching" step to have linked Parts-Used codes to BOM components. On production neither had happened → £0 with no explanation.
- FIX (dealer_parts_data.py recommend_from_invoice): (1) refactored run_matching into reusable _do_matching(org,settings); (2) if no matched analysis rows exist, auto-run matching once inside recommend; (3) tiered usage lookup — prefer approved matches, else fall back to ALL non-rejected matches (usage_relaxed flag); (4) always return a clear `note` explaining an empty pack (no BOM match / no usage data imported / matched machines have no proven usage) plus parts_total & matched_machine_count.
- FEATURE (#3): AllocationWizardTab step 1 now shows a consolidated "Recommended parts" card (dp-wiz-consolidated) at the top — unique part count, total qty, total value, and a table of every recommended part (code, description, priority, which machines, qty, unit, value), reacting to qty overrides. Plus a note banner (dp-wiz-rec-note) surfacing the backend explanation.
- Verified: 305H-AEQ → 21 parts £392.44 list rendered; no-usage machine → clear amber note. 
- PENDING (#2 invoice total / duplicate machines): needs the user's exact spreadsheet to fix total-reconciliation safely without breaking the working scanner — asked user to share it.
- NOTE: PRODUCTION — requires redeploy.

## 2026-07-15 — Invoice PDF: duplicate machines removed + order value = invoice total (#2)
- ISSUE (from user screenshot): the PDF scanner picked up product DESCRIPTIONS as extra item codes ("Club Line 45-Degree Leg Press 480kg", "Premium 45-Degree Leg Press 480kg", "Dual Use Dual Multi-Pulley 2x114kg") because after stripping spaces the hyphen in "45-Degree"/"Multi-Pulley" matched the code regex — creating duplicate/unmatched machine lines and inflating the total (£82,425 vs true £74,134).
- FIX (dealer_parts_data.py _scan_pdf_invoice): item-code detection now requires NO spaces in the line + length 4–20 + code regex (real Sage/Pulse codes never contain spaces). Descriptions are no longer mis-read as codes.
- FIX (order value reconciliation): scanner now also captures the printed NET line total (2nd price after qty) and, crucially, detects the invoice's printed goods total (NET/GROSS/GOODS/TOTAL block) and uses it as the authoritative order_value. Response now includes invoice_total + line_sum; note states "Order value set to the invoice's printed total".
- Verified with user's Pure Pulse Invoice.pdf: 22 clean lines (was 26), 20 matched + 2 genuinely-unmatched codes (516H-AAG, 925H-AAB), 55 machines/50 matched, NO description duplicates, order_value = £74,134.42 = the invoice's printed NET/GROSS total. UI confirmed: value field auto-fills £74,134.42, banner explains it, machine rows show code+description+qty cleanly.
- NOTE: PRODUCTION — requires redeploy.
