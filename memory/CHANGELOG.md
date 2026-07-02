# Changelog


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
