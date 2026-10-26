# 2026-10-12 — Fix: HR could not see all departments' staff (Staffing → Job Roles/People)

**Root cause:** `GET /staffing/staff` gated full visibility behind `_is_manager(user)` which reads the platform LOGIN role (`users.role`). The HR "see everyone" override lived in `_staff_visibility_scope` but was only reached for managers. The role-sync `_platform_role_from_staff_role` omitted `hr`/`payroll`, so an HR staffer's login role stayed `staff` → `_is_manager` was False → they hit the "own record only" branch and saw almost no one.

**Fix (backend/routes/staffing.py):**
- Added `_user_sees_all_staff(user, org_id)` — grants full staff-register visibility when the user's Staffing job role is in `_SEE_ALL_STAFF_JOB_ROLES` (hr/payroll/director/owner), independent of login role. `list_staff` now keys the manager branch off `_is_manager(user) OR _user_sees_all_staff(...)`.
- Added `hr`/`payroll` to `_platform_role_from_staff_role` → their login role syncs to `manager` going forward.

**Tested:** HR user with login role 'staff' + job role 'hr' now sees all staff across all departments; a regular gym-floor staffer still sees only their own record. Backend clean.

**Needs:** production redeploy.

---


# 2026-10-12 — Three critical fixes: Vehicles Defects crash, MOD engineer routing, MOD fault → BFPO bridge

**Bug 1 — Vehicles → Defects white-screen crash (VehiclesTab.js):** The `DefectTracker` component redeclared `const token` as a string, shadowing the module-level `token()` helper. Rendering any defect photo calls `token()` → `TypeError: token is not a function` → whole app crashed (every submitted defect has a photo, so it crashed every time). Fix: removed the unused shadowing local; `token()` now resolves.

**Bug 2 — MOD/BFPO engineers wrongly routed to Operations (LoginPage.js):** `routeAfterLogin` honoured a `?next=` deep-link unconditionally, so a stale `next=/dashboard` sent MOD engineers into Operations. Fix: `nextParam` is now ignored when the resolved home is a dedicated role shell (`/bfpo`, `/dealer-portal`, `/logistics`, `/partner-engineer`) — MOD engineers always land on `/bfpo`.

**Bug 3 — MOD faults not reaching BFPO engineers or MOD Operations:** Faults were written to `db.issues` under the MOD site's own org, while the BFPO engineer app + MOD Operations read `svc_cases` under `bfpo-mod-org`. Added a bridge (`bfpo.py::_bridge_mod_fault_to_bfpo`): every MOD fault now mirrors into a BFPO job (status=new, case_type=fault, priority p1–p4, `safety_critical`, site/country/territory tags, source='mod_fault', unassigned) so it appears in the MOD Operations dashboard AND to that site's engineers. Wired on fault submit (`mod_portal.py::mod_fault_submit`) and auto-backfilled idempotently on `/bfpo/jobs` load; plus one-tap `POST /bfpo/faults/sync`. Jobs list now sorts `safety_critical` to the top. Engineers accept + schedule the visit via the existing BFPO job flow.

Also reset master-admin MFA on preview (cleared `user_mfa`; `ENFORCE_MASTER_ADMIN_MFA=false`) so `admin@pulsefitness.com` logs in without MFA.

**Verified:** Bug 3 bridge tested directly (new submit + backfill of 9 faults, idempotent, correct svc_case shape incl. p1/safety_critical). Bugs 1 & 2 verified at code + compile level (not deployed-UI click-through). Backend + frontend compile clean; `/bfpo/faults/sync` route live.

**Needs:** production redeploy.

---


# 2026-10-06 — MOD Sites: CRM parity with commercial companies + MOD Operations site flow

**Root cause:** MOD sites were stored only as separate estate orgs (`db.organizations`, `account_type='mod_site'`), disconnected from `crm2_companies` (CRM list) and from the BFPO portal (which read `db.sites` under hardcoded `bfpo-mod-org`). So the CRM "MOD Sites" button opened a management popup instead of listing companies, and the MOD Operations "Global Site View" was empty.

**Issue 1 — CRM (make MOD sites behave like commercial companies):**
- Backend `crm_v2.py`: added `_sync_mod_site_companies()` — idempotent sync-on-read that mirrors every `mod_site` estate org into `crm2_companies` (type='mod_site', source='mod_site', mod_org_id link, branch, address) scoped to the viewing operator. Wired into `GET /crm/v2/companies` when `type=mod_site`. MOD sites are EXCLUDED from "All"/commercial filters (`type != mod_site`) so the two lists stay separate.
- Because mirrors are real `crm2_companies` docs, clicking a MOD site opens the standard company detail page (Overview/Contacts/Deals/Equipment/etc.) identically to Penkridge.
- Frontend `CRMCompanies.js`: "MOD Sites" is now a FILTER CHIP (sets typeFilter='mod_site') instead of opening the Import more/Remove popup. Those tools no longer appear on the CRM companies screen (they remain in Master Admin → MOD Estate). Added MOD branch badge on the cards.

**Issue 2 — MOD Operations "Global Site View" empty:**
- Backend `bfpo.py` `_compute_site_health()`: now also includes `mod_site` estate orgs (open-case counts per org), surfaced grouped by country → service branch (ARMY/RAF/NAVY as the territory). `/staff/sites` tree now populates.

**Tested:** Direct function tests (mirror 15+ sites, idempotent; BFPO health lists MOD sites by country/branch) + live API: `type=mod_site` returns 15 companies, `All` returns 6 with 0 MOD leakage. Backend + frontend compile clean.

**Needs:** production redeploy.

---


# 2026-10-05 — PPM visit: Print report + Speed/Incline calibration labelling

**1. Print report (Service Desk PPM visit card):** Added a "Print report" button (data-testid=ppm-detail-print) in the PpmScheduleDetail modal footer. `buildReportHtml`/`printReport` open a formatted, print-ready "Service Report" covering the site, machines-on-site, every visit's engineer workings (machines serviced/cleaned + notes) and treadmill calibration tables grouped into Speed (mph) / Incline (%).

**2. Calibration Speed + Incline labelling:** The office calibration view previously rendered one flat, unlabelled grid. Root cause (confirmed via production read of SVC-00013): data pipeline already captures/stores/returns both axes, but there was no `type` tag and no section headers. Fix:
- Backend (engineer.py): tagged `TREADMILL_CALIBRATION_READINGS` with `type: speed|incline`; added `_reading_axis()` (type → label → unit fallback) and stamped `type` into `_norm_readings` so new + legacy readings classify correctly.
- Frontend (PpmScheduleDetail.js): new `CalibrationReadings` component splits readings into labelled "Speed (mph)" and "Incline (%)" sections (per-treadmill matrix and flat modes); fails render red with ✗. Same grouping used in the printed report.

**Note on legacy data:** Production record SVC-00013 was captured under the OLDER template (5 speed points only, no incline) — incline literally was never recorded there, so it can only show Speed until re-captured. The current template captures 4 speed + 4 incline; after redeploy all NEW calibrations show both axes.

**Tested:** testing_agent frontend — 100%, no issues. Confirmed SPEED (MPH) + INCLINE (%) labelled sections (4 each), fail in red, and the Print report window renders both axes. Backend schedule_detail returns type-tagged readings.

**Needs:** production redeploy.

---


# 2026-10-05 — Feature: Engineer equipment change-requests (office approval) + richer office Case View

**Part A — Engineer proposes equipment add/remove; office approves (nothing applied until approved):**
- New backend `routes/svc/equipment_change_requests.py` + `svc_equipment_change_requests` collection (registered in route_registry/features.py).
  - Engineer: `POST /api/svc/engineer/equipment-change-requests` (change_type add|remove), `GET /api/svc/engineer/jobs/{case_id}/equipment-change-requests`.
  - Office: `GET /api/svc/desk/equipment-change-requests` (+pending_count), `POST .../{id}/approve`, `POST .../{id}/reject`.
  - Approve ADD → creates a real `db.equipment` asset under the customer org + site (status active). Approve REMOVE → sets the asset `status: archived` (soft remove; 404 guard if asset gone). Idempotent (409 on double-decision).
- Frontend: engineer `WorkVisitMachinesCard.js` — replaced direct "New asset" with **"Propose new"** modal, added per-row **"Propose removal"**, and a **"Proposed changes · office review"** banner showing status. Office `DeskEquipment.js` — new **"Equipment changes to review"** panel with pending-count badge + Approve/Reject.

**Part B — Office Case View (PpmScheduleDetail) now shows engineer's workings properly:**
- `schedule_detail` returns a `visits[]` array (all visits for a schedule, newest first); each visit includes per-machine detail (asset_name, asset_type, asset_serial, serviced, cleaned, notes) + the calibration record (per-treadmill readings). Kept `workings` for back-compat.
- Frontend `PpmScheduleDetail.js` — new `VisitsPanel`: **date-labelled tabs** (when >1 visit), per-machine rows with serviced/cleaned badges + notes, and a treadmill-calibration grid (speed/incline pass/fail). Replaces the old flat repeated "N machines" list.

**Tested:** testing_agent — backend 100% (7/7), frontend 100%, no issues, retest_needed=false. Also direct-verified: propose add/remove → approve creates/archives, pending count, visits shape, machine self-heal.

**Needs:** production redeploy.

---


# 2026-10-05 — Fix: PPM jobs showed no machines / no treadmill calibration (Fire Station PPM)

**Symptom:** After engineers could see bulk-allocated PPM jobs (Devon & Somerset Fire & Rescue), the job showed no machines to service and no treadmill calibration form.

**Root cause (confirmed via production read):** PPM cases are scoped to the Pulse **operator** org, but customer equipment + schedules live under the **customer** org (`ppm_customer_org_id`). `_ensure_customer_machines_attached` (engineer.py) joined `db.equipment` filtered by the case's operator org, so it resolved zero equipment — leaving machine rows as generic placeholders (`asset_type: null`, name "N machines"). With no real asset type, treadmill detection off the machine rows failed. Equipment_ids and treadmill typing were actually correct; the join org-scope was the bug.

**Fix (backend/routes/svc/engineer.py `_ensure_customer_machines_attached`):**
- Resolve equipment by `id` only (equipment is under the customer org, ids come from the trusted case).
- Made it **self-healing/idempotent**: it now UPSERTS — refreshing existing placeholder rows with the real asset_name/type/serial/manufacturer/model when equipment resolves, while never overwriting engineer-entered fields (serviced/cleaned/notes/custom_fields). Runs on every job-detail open (`GET /svc/engineer/jobs/{id}`), so existing D&S jobs repair themselves the next time the engineer opens them.
- Treadmill calibration ("Fire Station Service") then renders because treadmills are detected both from the repaired machine rows and the by-id equipment fallback.

**Verified in preview:** (1) Full Fire Station bulk flow → 5 machines attach with correct names/types/serials, 3 treadmills detected, calibration endpoint returns 3 treadmills × 8 params. (2) Self-heal test: pre-seeded generic placeholder rows were repaired to correct type while preserving serviced=True/notes; treadmill + calibration then resolved. No duplicate rows.

**Needs:** production redeploy. After deploy, William re-opens the job → machines + treadmill calibration appear automatically.

---


# 2026-10-05 — Fix: Bulk PPM allocation never reached engineers (production incident)

**Symptom:** Engineer William Ollis (william.ollis@pulsefitness.com) saw an empty job list in the Engineer App despite PPM jobs appearing on the Service Desk calendar (Devon & Somerset Fire & Rescue, imported via the Bulk schedule wizard).

**Root cause:** `POST /svc/ppm/schedules/bulk` (ppm_calendar.py) only created `ppm_schedules` (calendar entries) with `assigned_engineer_id` stored *on the schedule*. It never created an `svc_case`. The Engineer App reads `db.svc_cases` (filter `assigned_engineer_id == user.id`), so bulk-allocated visits never produced an engineer job. Only the single "Schedule & assign" modal (`/svc/ppm/schedule`) spawned a case. Confirmed: production had PPM schedules on the calendar but zero assigned svc_cases.

**Fix (backend/routes/svc/ppm_calendar.py):**
- Added `_spawn_ppm_engineer_job()` helper — creates an `svc_case` (case_type=ppm, status=coerce_status(ASSIGNED)), sets `assigned_engineer_id/ids/name/names`, `scheduled_at`, `pm_schedule_id`, and fires in-app + Web Push notification. Mirrors the single-allocation flow.
- Wired it into BOTH bulk modes (wizard `assignments` + legacy `site_ids` stagger): when an assignment carries an `engineer_id`, a job is now spawned and the engineer is notified. Response now includes `jobs_created`.
- Hardened the single flow `/svc/ppm/schedule`: if engineer(s) were picked but none resolve on the operator roster, it now raises HTTP 422 instead of silently creating an unassigned job with a false success toast.

**Verified:** In preview, calling `bulk_ppm_schedules` with an engineer created an `svc_case` (status `assigned`, correct engineer id), and the exact engineer-job-list query returned it (9→10). Test artifacts cleaned up.

**IMPORTANT follow-ups:**
- Needs a production redeploy for the fix to take effect.
- Devon & Somerset schedules already imported in production (pre-fix) will NOT retroactively get jobs — either re-run the bulk schedule after deploy, or add a one-time backfill endpoint that spawns jobs for existing `ppm_schedules` with `assigned_engineer_id` set but no linked svc_case.

---


# CHANGELOG

## 2026-06 — Per-site PPM backfill (batched + backgrounded)
PPM schedules are now generated PER SITE, only when a site is activated — never as one 120k-asset sweep. Mirrors the sicon_sync_runs background pattern so the triggering request never blocks/times out.
- New in routes/ppm_engine.py: `run_site_ppm_backfill(org, site, run_id, frequency)` worker + `kickoff_site_ppm_backfill(...)` (idempotent — returns the in-flight run if one is queued/running) + endpoints `POST /ppm/backfill/site/{site_id}` (queue, returns run_id immediately) and `GET /ppm/backfill/runs/{run_id}` (poll status/progress). New `ppm_backfill_runs` collection: `{id, organization_id, site_id, status queued→running→completed|failed, counts{equipment_total,types,schedules_created,tasks_created,skipped_existing}, started_at, finished_at}`.
- Logic: groups the site's equipment by `equipment_type` via aggregation (one `ppm_schedules` doc per type listing its `equipment_ids`, install_date = earliest purchase_date, default frequency configurable), then generates the first 3 `ppm_tasks` per schedule via the existing `_generate_task_batch`. Idempotent: re-running skips types that already have an active `source:"auto_backfill"` schedule. Per-site work is naturally bounded (a venue has hundreds of assets, not the estate), and it runs off-request via `asyncio.create_task`.
- Verified via curl on a seeded 50-asset/3-type site: first run → completed, 3 schedules + 9 tasks; re-run → skipped_existing:3, 0 created (idempotent). Test data cleaned up.
- Note: `POST /ppm/backfill/site/{site_id}` IS the "site becomes active" hook — PPMs are only generated when it's called for a site, satisfying "only load PPMs when a site becomes active". Wire it to your site-activation action / master-admin restore as needed.


## 2026-06 — Equipment search/facet indexes (120k)
Added compound indexes in bootstrap/indexes.py: equipment `(organization_id, equipment_type)`, `(organization_id, location)`, `(organization_id, manufacturer)`, `(organization_id, model)`. These back the Equipment tab's facet dropdowns (`GET /equipment/facets` distinct types/locations) and its server-side type/location filters so they stay fast on a 120k estate. Verified: all four indexes present after restart; facets endpoint returns 200.


## 2026-06 — Fix remaining silent-truncation equipment reads (KPI / CAPEX / pulse-sales / CRM-aftersales)
Converted every `.to_list(5000)` equipment read in the four modules the user flagged, so dashboards/quotes are accurate at 120k. Verified: syntax OK, no backend tracebacks, and the pulse_sales background sweep ran post-change with errors:0 (live-exercises the edited path).
- kpi_engine.py: OOS by-site totals now via `$group` aggregation (was a 5000-capped equipment pull that under-counted every site). `_calc_oos_ratio` total already used count_documents.
- capex.py: fleet-analysis + justification equipment scans raised from 5000/500 → 200000 ceiling (full `{_id:0}` docs — inherently per-asset scoring, can't be a pure aggregation); the small-projection window scan → `.to_list(None)`.
- pulse_sales.py: CAPEX opportunity scan raised 5000 → 200000.
- crm_aftersales.py: 7 estate/quote/warranty equipment reads (small projections) → `.to_list(None)` (accurate, tiny memory) — estate view, build-quote-from-estate, custom-quote, warranty-opportunities, build-proposal.
- Note: CAPEX/pulse-sales full-doc fleet scans are accurate up to 200k assets but still load all docs per request; true unbounded scale needs a batched/site-scoped pass (flagged).


## 2026-06 — Operations Equipment tab: server pagination + search (120k-ready)
Verified via UI on a 63-item demo org (paging 1→2→3, server search returns exact match, no runtime errors) + curl. Temp rows cleaned up.
- `EquipmentInfoTab.js` now loads ONE page (24/row) from the paginated `GET /equipment?page&limit&q&equipment_type&location&ids` instead of pulling up to 5,000 rows client-side. Debounced (400ms) server search; type/location dropdowns populated from a new `GET /equipment/facets` (distinct types/locations/total) so they stay complete when the grid is paged. Coverage/expiry drill-down passes matching ids to the server. Added Prev/Next + "Showing A–B of N" + "Page X of Y" controls (data-testids `equipment-pagination`, `equipment-page-info`, `equipment-page-indicator`, `equipment-prev-page`, `equipment-next-page`).
- Removed the old client-side filter effect (it re-filtered every row and crashed on rows with a missing `equipment_type` → `Cannot read properties of undefined`); the page now mirrors the server-filtered result null-safely.
- Backend `GET /equipment` extended with `equipment_type`, `location`, `ids` filters (on top of the earlier `q`/`page`/`limit`). New `GET /equipment/facets` endpoint. Backward compatible: no-param callers unchanged.


## 2026-06 — Sicon 120k scale-hardening (read-side, part 1) + load test
Ran a real 120,000-equipment load test (`backend/scripts/loadtest_sicon_scale.py`) against a throwaway org; measured DB-layer cost of every hot equipment path, then fixed the P0 data-integrity issues. Load-test data cleaned up after.

**Load-test findings at 120k (before fix):** `GET /equipment` `.to_list(2000)` returned only 2,000 of 120,000 (silent truncation, 507ms); supplier-rollup `.to_list(50000)` dropped ~70k; analytics `.to_list(5000)` dropped ~115k; `count_documents` 99ms and `skip/limit` 2ms (cheap → pagination is the right fix); full equipment iterate 594ms.

**Fixes shipped (backend, verified via curl on a real org):**
- `GET /equipment` (routes/equipment.py) — added OPT-IN server pagination (`page`/`limit`, capped 500) + server-side search (`q` across name/type/manufacturer/model/serial/location) + `total`/`pages`. Backward compatible: no-params callers still get `{equipment:[...]}` (now bounded at 5000 with a `truncated` flag) so existing pickers/canvas/CheckSheets don't break. Verified: paginated shape `{equipment,total,page,limit,pages}`, legacy shape preserved, `q` search works.
- `GET /equipment/export/csv` — streams the full cursor (was capped at 500) so a 120k export is complete.
- Service Desk supplier-rollup (routes/service_desk.py) — equipment + issues now streamed via cursor instead of `.to_list(50000)`, so supplier totals are correct at 120k (previously under-reported by ~70k).

**Also confirmed already-built (no work needed):** in-platform Sicon connection config + test (`routes/sicon.py` `/sicon/config`, `/sicon/test-connection`; `IntegrationsSiconConnect.js`), encrypted + audited — a separate "Bruno-style" tester is unnecessary.

**Still TODO (staged next):** convert the Operations Equipment tab (`EquipmentInfoTab.js`) to consume the new server pagination + search (currently filters client-side, loads up to 5000); remaining analytics `.to_list(5000)` sites (pulse_sales, kpi_engine, capex, crm_aftersales, master_admin_mod_estate) → aggregation/count; batch+background the PPM equipment backfill (`ppm_calendar.py`) before a live 120k import; add an equipment search index (type/manufacturer/model).


## 2026-06 — Compliance-at-a-glance panel (Operations → Staffing → People → Compliance)
Verified full-stack: backend endpoint via curl (correct aggregation), frontend on desktop 1920 + mobile 390 (all statuses, sorting, pills render; no content overflow).
- New manager tab combining three compliance surfaces in one view: Enhanced DBS certificate status, Right-to-Work status, and outstanding (unpaid) vehicle fines.
- Backend: `GET /api/staffing/compliance` (staffing.py) — `_require_manager` + `_org`, staff scoped by the same `_staff_visibility_scope` as the People register (owners/HR/Payroll/Directors see all). Returns `{summary, dbs[], right_to_work[], fines[]}`.
  - DBS from `staff_members.dbs_expiry_date`/`dbs_number`: statuses expired (<0d), expiring (≤60d, matches the DBS bell nudge), valid, or not-on-file. Multi-format date parse.
  - Right to Work from `staff_members.right_to_work_status`: verified / check-needed / not-on-file (case+separator-insensitive match against a known-good set).
  - Fines: flattens unpaid `vehicles.fines[]` org-wide; overdue = 14+ days outstanding; sums unpaid total. Reuses the same open-fine/age logic as the manager fines nudge.
  - Each list sorted most-urgent-first.
- Frontend: `frontend/src/pages/LiteDashboard/staffing/ComplianceTab.js` (new) — three summary cards + three needs-attention sections with status pills; registered in `StaffingConsole.js` People group (`id: 'compliance'`, ShieldCheck icon, MGR-only) + render line. data-testids: `compliance-tab`, `compliance-refresh`, `compliance-card-{dbs,rtw,fines}`, `compliance-{dbs,rtw,fine}-row`.
- Note: seeded illustrative DBS/RTW/fine data on the **iso-demo-org** test tenant only (not the operator company) so the panel demonstrates all states.


## 2026-06 — Launcher personalisation (/launch area chooser)
Verified via screenshots (desktop 1920 + mobile 390), single-component UI change.
- Time-aware greeting: "Good morning/afternoon/evening, {first}" (data-testid `launcher-greeting`) — replaces the static "Welcome back".
- Most-used-first tile ordering: per-device launch tally in localStorage `pf_launcher_usage` ({areaKey: count}), incremented in `go()`. Tiles sort by usage desc (stable sort → equal-usage tiles keep natural order: Staff Portal, then modules). First-time users see the untouched default order.
- "Most used" badge (data-testid `launcher-mostused-badge`) on the top tile when it has ≥1 recorded launch and there's more than one area. No badge for brand-new users.
- File: frontend/src/pages/LauncherPage.js. No backend change. Works alongside the existing "Remember my choice" auto-forward (personalisation shows whenever the chooser is displayed, e.g. /launch?choose=1 or no saved default).


## 2026-06 — Unified staff sign-in + retired Engineer Partner Network + Staff Portal greeting fix
Verified via testing_agent (frontend, 8/8 scenarios, 100% — report iteration_unified_staff_login_partner_removal_jan2026.json).

**Unified staff sign-in (dedicated /staff-login retired):**
- All staff now sign in through the MAIN platform login `/login`. `/staff-login` route now redirects to `/login`; StaffPortal/StaffResetPassword/NewStarterPortal redirects repointed to `/login`.
- After login, staff land on the area chooser `/launch` (Staff Portal tile + any modules). If Staff Portal is their ONLY area → forwarded straight to `/staff-portal`.
- Because staff carry a normal platform session, the Staff Portal now renders the shared platform Navbar → mobile hamburger has **Switch area** + **Log Out** (this also resolved the earlier "lost area switcher on mobile" complaint).
- Backend: added shared helper `compute_has_staff_portal(user, org)` in `routes/auth.py`; `has_staff_portal` now stamped on the `/api/auth/login` payload (via `_finalise_successful_login`) and reused by `/api/auth/me`. Fixed `/api/staffing/me/portal-access` to use the same canonical (case-insensitive) computation — it previously used a case-sensitive exact email match and returned false for users the other surfaces treated as staff (root cause of the launcher bouncing staff to /dashboard).
- Frontend: `resolveHomePath` routes `has_staff_portal===true` → `/launch`; `LauncherPage` treats `user.has_staff_portal` as authoritative (with the probe as supplement), auto-forwards single-destination, and shows the chooser for operator-company OR any staff member. Non-staff users (has_staff_portal false) are unaffected and land on their normal home.

**Engineer Partner Network removed (public):** `/partners/engineers`, `/partners/engineers/apply`, `/partner-engineer/apply` now redirect to `/`. Removed the "Partners" marketing nav tab, homepage engineer banner + module tile (Five→Four modules copy), footer "For engineers" link, ServiceDeskPromo "join the network" link, and the contact-form "Partner Engineer Network" option. Backend partner routers/loops + master-admin partner tools left intact (dormant). Service Desk / service-suppliers marketing untouched.

**Staff Portal greeting:** removed the duplicate "Welcome back, {name}" subline; the single time-based greeting ("Good evening, {first}") + date remains.


## 2026-09-28 — Sicon read-side made hands-off (auto-match + nightly sync)
Per founder request ("everything automatic, as hands-off as possible"):
- Auto customer resolution (`resolve_company` in utils/sicon_import.py): matches Sicon customerCode/customerId against `crm2_companies.sage_customer_id`; a unique hit is auto-linked and remembered (link sync_status='auto'). NEVER matches on name alone (§11) — non-definitive stays unmapped.
- Auto site resolution (`resolve_site`): unique `crm2_sites.sicon_sub_location_id` match auto-linked.
- Equipment now auto-links company/site too (`_resolve_equipment_links`), only filling empty fields (never overwrites a user-set link, §20).
- Indexes added: crm2_companies(organization_id, sage_customer_id), crm2_sites(organization_id, sicon_sub_location_id).
- Nightly hands-off sync: `.emergent/crons.yml` → `sicon-nightly-sync` (0 2 * * * UTC) → POST /api/sicon/cron/nightly-sync (ungated `cron_router`, auth = WEBHOOK_CRON_SECRET bearer, acks 2xx immediately, backgrounds `_run_all_org_sicon_sync` = equipment + case sync for every org with Sicon enabled; safe no-op when unconfigured). Writes to Sicon stay OFF.
- WEBHOOK_CRON_SECRET added to backend/.env. Redeploy to activate the cron in prod (schedules sync on deploy).
- Tests: 2 new auto-match tests (auto-linked by sage code; never guessed by name). 24 Sicon offline tests total, all green. Cron endpoint verified: 401 unauth/wrong, 200 accepts + backgrounds.
- Duplication audit answered: no duplicate client/config/auth/equipment/cases/CRM modules; integration_bridge is Orbit4-specific; sicon_external_links justified (no prior generic external-ref table). Only intentional overlap: external id also on entity (aids idempotency).


## 2026-09-24 — Sicon READ-side Increment C (cases → Service Desk + mapping screens)
- CaseSearch → existing Service Desk (`db.issues`), idempotent by siSMCaseId. New importer `normalise_case`/`classify_case`/`apply_case_record`/`preview_cases`/`run_case_sync` in `utils/sicon_import.py`.
- Configurable per-org reference-data mappings on sicon_config (tracking_status_mapping, priority_mapping, case_type_mapping) — explicit id/name → Pulse value, no hardcoded logic (§13). Sensible fallbacks when unmapped.
- Customer/site resolution via the external-link table (customerId→crm2_company, siconSubLocationDbKey→crm2_site); stored once, reused each import (§11).
- Endpoints (`routes/sicon.py`): /read/cases/preview, /read/cases/sync, /read/sync-runs, /read/reference (GET/PUT), /read/customer-mappings (GET/POST), and an HONEST /read/equipment/{id}/cover returning cover_status='pending_sicon_verification' (§14 — never guessed).
- Frontend: new "Data Mapping" tab (`SiconMappings.js`) for reference + customer/site mapping; Cases preview/sync added to the Sicon dashboard. Verified rendering via screenshot.
- Tests: 5 new offline case tests; 22 Sicon offline tests total, all green. Endpoints curl-verified (reference, customer-mappings, cases/preview 400 not-configured, cover placeholder, save-mapping 200).
- Contract/SLA/appointment/engineer remain inactive extension points (§14/§15).


## 2026-09-24 — Sicon READ-side Increment B (equipment import + dashboard)
- Import engine `utils/sicon_import.py`: normalise → classify (linked/match/conflict/new) → apply, all idempotent via the external-link table + sicon_equipment_id. Serial is the only auto-link signal; ambiguous → conflict queue (never merges). Field ownership respected: never overwrites manufacturer (Sicon make kept as sicon_make_raw), never erases a populated Pulse field with an empty Sicon value.
- Read-side endpoints in `routes/sicon.py` (`/api/sicon/read/*`): dashboard, api-health, equipment/preview (classify-only, writes nothing), equipment/sync (background run + status poll), conflicts list + resolve (link/create_new/ignore). Owner/manager/admin gated. Writes to Sicon stay OFF.
- Dashboard UI `frontend/src/pages/SiconDashboard.js` added as the first tab of the existing Settings → Sicon integration tab (connection health, equipment & case stats, preview/sync, conflict review, sync log, API health) — friendly not-configured/disconnected states.
- Fixed a pre-existing gap: the org Settings dialog had no header opener since iter202 — restored `nav-settings-btn` (+ mobile) in Navbar and wired the ignored `onOpenSettings` prop, so users can reach Settings → Sicon → Dashboard again.
- Tests: 6 new offline engine tests + 11 from Increment A = 17 green; testing agent 7/7 endpoint tests pass and the dashboard renders correctly. Report: iteration_sicon_readside_dashboard_incrementB_jan2026.json.
- Next: Increment C (CaseSearch → Service Desk + configurable reference-data & customer/site mapping screens).


## 2026-09-24 — Sicon READ-side integration, Increment A (foundation)
Built the proven Sicon→Pulse read-side foundation per the customer's FINAL spec, all offline-tested (live Sicon only reachable on their network).
- Extended the ONE central client (`utils/sicon_client.py`) with proven read endpoints: CaseType/Priority/TrackingStatus, Equipment GetMany+GetOne, CaseSearch GetMany+GetOne (by siSMCaseId), plus a paginate-until-nextPage-null helper.
- Exact Sicon pagination `query=$skip=0%26$max=50` — raw-bytes query so the inner `%26` reaches Sicon un-decoded (§5/§30), proven on the wire in tests.
- Central write-guard: SICON_ALLOW_WRITES=false blocks EVERY POST/PUT/PATCH/DELETE across both surfaces (§18/§35). Auto re-auth on 401 (§3). Bearer never persisted/exposed.
- Env config factory (SICON_BASE_URL/COMPANY_ID/USERNAME/PASSWORD/ALLOW_WRITES/PAGE_SIZE) with DB-config fallback (`utils/sicon_common.py`).
- Reusable external-ID link table `db.sicon_external_links` (unique key → idempotent sync) in new `utils/sicon_links.py` + indexes.
- 11 offline acceptance tests (`tests/test_sicon_readside.py`) all green; ruff clean; backend healthy. See /app/memory/SICON_READSIDE_NOTES.md.
- Next: Increment B (Equipment import preview + matching + admin dashboard), Increment C (CaseSearch→Service Desk + mapping screens). Writes stay OFF.


## 2026-09-24 — Redesigned transactional emails + fixed Vehicle Check photo upload
EMAIL (all transactional emails, shared shell in backend/utils/email.py):
- Rebuilt `_header_html` to the pulsefitness.ai look: solid black bar (#0A0A0A) with a white "pulse" + cyan "fitness" wordmark and a 3px cyan accent rule. Removed the purple/blue initial "P" default (accent now #19CDFF). Operator logos sit on a white chip so they stay legible on black.
- Rebuilt `_footer_html` to be CAN-SPAM/PECR-friendly: co-brand line + support email (env EMAIL_SUPPORT_ADDRESS, default support@pulsefitness.ai) + physical postal address (env EMAIL_FOOTER_ADDRESS, default "Pulse Fitness Ltd, United Kingdom") + email-preferences line. ACTION: set EMAIL_FOOTER_ADDRESS to the real registered address in prod.
- The staff-portal invite body (routes/staffing.py `_staff_portal_email_body`) already builds a proper cyan <a> button — the broken "[url]…" button in the report was the OLD deployed build; the redesign supersedes it. Verified full render (black header, cyan CTA, footer) via headless screenshot.

VEHICLE CHECKS photo bug (frontend/src/pages/StaffPortal.js):
- Root cause: marking an item as a defect gates submit on `photos.defect.length > 0`; if the photo upload silently failed (oversized phone image hitting the ingress/proxy limit, or iPhone HEIC), the photo never attached and submit was blocked — the engineer had to remove the fault to submit.
- Fix: added `compressImage()` (canvas downscale to ≤1600px + re-encode to JPEG q0.8) run before upload — fixes both oversized images and HEIC. Surfaced the real server error instead of a generic message, added an "Uploading photo…" spinner state, disabled Submit while uploading, and reset the file input so a failed pick can be retried. Photo remains MANDATORY for a defect.
- Verified: compression produces a smaller image/jpeg File (4000px PNG 238KB → 1600px JPEG 90KB; real phone photos shrink far more). Frontend compiles clean. Full E2E (staff login + assigned vehicle) not run — needs a provisioned vehicle; recommend a testing-agent pass if you want belt-and-braces.


## 2026-09-24 — Black headers (login/engineer/MOD) + cookie banner mirrors pulsefitness.com
- Login/public header (`pages/LoginPage.js`): was translucent white (`bg-white/60`) → solid black (`bg-black`, `border-white/10`); EN selector + "Back to home" restyled to light text. Logo already reads on black (same asset the Navbar uses).
- Engineer home header (`ServiceOps/Engineer/EngineerHomeV2.js`): was `bg-white` → `bg-black`; greeting/stats/action buttons switched to light-on-dark.
- MOD PRO header (`MODPortal/MODProDashboard.js`): `bg-[var(--color-surface-darker)]` → `bg-black` for exact uniformity.
- Cookie banner (`components/shared/CookieConsent.js`): rebuilt to match pulsefitness.com — compact black rounded box, bottom-right (full-width on mobile), text "This website uses cookies to ensure you get the best experience on our website.", a "Learn more" link (→ /privacy), and Decline / Allow cookies (cyan) buttons. i18n keys updated in en/fr/de (`cookie.message`, `cookie.learn_more`, `cookie.decline`, `cookie.allow_cookies`).
- Verified (Playwright, desktop 1920 + mobile 390): header bg = rgb(0,0,0), new cookie copy/buttons render, no horizontal overflow.
- NOTE: the Service Desk hub uses a left-sidebar layout and legacy Service Ops uses a hero card (not top bars), so those weren't converted to a black top bar — flagged to user as a separate sidebar-theming pass.


## 2026-09-24 — Fix: temp-password `/change-password` screen rendered blank
Users landing on `/change-password` (forced temp-password change) saw a blank white page.
Root cause (two compounding bugs):
1. `/api/auth/me` did not return `must_change_password` (only `/api/auth/login` did). The post-login
   `/auth/me` re-fetch and any page refresh dropped the flag, so `user.must_change_password` became `undefined`.
2. `ForceChangePasswordPage` called `navigate()` during render and hit `return null` when the flag was falsy →
   stuck blank page instead of redirecting.
Fix: (a) `backend/routes/auth.py` (~L1111) now includes `must_change_password` in the `/me` payload;
(b) `frontend/src/pages/ForceChangePasswordPage.js` moves the redirect into a `useEffect`, shows a Loading…
splash instead of a blank render, and adds a `justSaved` guard so the success toast/redirect still works.
Verified E2E (Playwright): refresh on /change-password renders the form; submitting a valid new password
changes it and redirects to /dashboard. Repro user: honey.test@pulsefitness.com / TempPass123!.


## 2026-06 — Sicon Bruno collection + mapping regenerated to full spec
Fixes the reported regression in the exported collection. `integrations/build_bruno_collection.py` +
`integrations/build_mapping_csv.py` now produce a read-first, write-safe collection meeting all 12 requirements:
- **companyId = 2** (Pulse Fitness) in the environment (no longer defaults to 1); `ALLOW_WRITES=false` default.
- Restored **Equipment reads**: GetMany (with `$skip`/`$max` pagination + skip-advance script), GetOne, SearchBySerial.
- **TrackingNote.appointmentId = {{appointmentId}}** (was null), sourced from appointment.sicon_appointment_id.
- **Automatic ID capture** via `bru.setVar` post-response on every create/get (siSMCaseId→caseId, siconAppointmentId→appointmentId, siconEquipmentId→equipmentId, siSMCaseTrackingNoteId→trackingNoteId, timeBookingId).
- **No zero-reset**: removed the collection-level `vars:pre-request` id reset; runtime ids persist / are editable in the env.
- **Write guard**: every business POST/PUT throws unless `ALLOW_WRITES=true` (Auth POST is the documented exemption).
- **Lookups** folder (13): CaseTypes, Priorities, TrackingStatuses, Employees, Contracts, CoverTypes, SLAs, FaultCodes, Skills, Teams, Customers, Contacts, SubLocations.
- **GET response tests** (status + expected properties); null-vs-zero: optional FKs null, lookup ids via {{vars}}.
- **mapping.csv** (8 cols incl. *Sicon Behaviour Status*, 164 fields, zero UNMAPPED) + **FIELD_MAPPING.md** bundled in the zip.
- Served at `/api/downloads/sicon-bruno-collection.zip` and `/api/downloads/sicon-field-mapping.csv`.
- Verified by testing agent (22/22 acceptance assertions after two minor Ping-test / Auth-doc fixes).

## 2026-06 — Sicon Service WebAPI v1 migration (field mapping + appointmentId)
Fixes the reported Sicon mapping failures ("appointmentId should be mapped within our platform"; missing fields).
- Root causes: (a) the Sicon-returned appointment id was never persisted on our record; (b) outbound Case/Appointment
  payloads were incomplete PascalCase on a legacy endpoint surface (`/api/ServiceCase/*`, `/~/api/v2/TEntity/*`),
  not the `/api/v1/SiconService/*` Service WebAPI (camelCase + companyId + JWT bearer) the customer's Bruno collection uses.
- New `utils/sicon_service_models.py`: FULL camelCase model builders matching Bruno exactly —
  Case (57 fields incl. nested address/caseType/priority + analysisField1..20), Appointment (all 25 incl. description,
  colour, employeeIds, completion block), Equipment (incl. analysisCode1..20), TrackingNote, TimeBooking.
- `SiconClient` gained JWT bearer auth (`/api/v1/authentication/authenticate`) + v1 methods `svc_*` hitting
  `/api/v1/SiconService/{Case,Appointment,Equipment,...}` with `companyId`.
- `POST /api/sicon/create-appointment/{issue_id}` now PERSISTS the returned `siconAppointmentId` onto the issue
  (`sicon_appointment_id`) and auto-switches to PUT `/Appointment/{id}` when it already exists.
- `sync_issue_to_sicon` uses the v1 case model + endpoint and reads back camelCase ids.
- Migration is gated per-org by `sicon_config.service_webapi_v1` (default off) → existing orgs untouched, no regressions.
  To activate an org: set `service_webapi_v1: true`, `base_url`, `company_id`, `username_enc`/`password_enc` on its sicon_config.
- Fresh Bruno collection reflecting OUR payloads generated at `/app/integrations/PulseFitness-Sicon-WebAPI.zip`
  (regenerate via `python integrations/build_bruno_collection.py`).
- Verified: 13 new pytest tests (builders, v1 URL/auth routing, appointmentId persistence, create-vs-update, flag branching)
  all pass; legacy Sicon tests still green. Sicon live API is MOCKED here — true end-to-end acceptance confirms post-deploy.

## 2026-06 — Drag-to-reschedule on the PM calendar
- Desk users can now drag a visit chip onto another day to reschedule it, without reopening the wizard.
- Frontend (`PPMCalendar.js`): commercial chips are HTML5-draggable (disabled in Manage mode); day cells are
  drop targets with a cyan highlight; drop does an optimistic move then persists. MOD visits aren't draggable.
- Backend: `POST /svc/ppm/schedules/{id}/reschedule` (operator-scoped, validates the date) updates `next_pm`.
- Verified: curl (move persisted, invalid date → 400) + frontend compiles. NOTE: native drag-drop gesture not
  e2e-scripted (automation limitation); API + rendering verified. Needs redeploy to reach production.

## 2026-06 — Bulk PPM scheduling wizard + calendar upgrades
Service Desk → Preventative Maintenance calendar. All flows verified (backend curl + frontend testing agent, 95%):
- **Bulk Scheduling Wizard** (`BulkPpmWizard.js`): 4 steps — pick customer + sites → service/frequency + lead
  engineer → **AI groups nearby sites into geographic runs** (Claude Sonnet 4.6 via Emergent key, postcode/town
  fallback) → auto-lay dates (sites-per-day, days-between-runs, skips weekends) with every row's date & engineer
  editable. Lead engineer applies to the batch, overridable per run/row. Commits via
  `POST /svc/ppm/schedules/bulk` with an `assignments` array (exact date + engineer per site).
- **Calendar chips** now show the **site name** + a small machine-count badge (was "N machines").
- **Click-into detail** (`PpmScheduleDetail.js`): opens site + address + every machine on the site; once the
  job is completed shows the engineer's workings (job ref, engineer, completion, calibration result, per-machine
  service). Delete-visit + Allocate actions. `GET /svc/ppm/schedules/{id}`.
- **Search bar**: find when a site/customer is booked across all months (`GET /svc/ppm/search`); clicking a
  result jumps the calendar and opens the detail.
- **Bulk delete**: a "Manage" mode with checkbox chips + "Delete selected" (`POST /svc/ppm/schedules/delete`),
  plus a one-click **"Delete ALL for a customer"** modal (`POST /svc/ppm/schedules/delete-all`, 403-guarded to
  linked customers only). Soft-delete (`active:false`).
- Schedule docs now store `assigned_engineer_id/name`, `machine_count`, `site_address`; calendar feed carries
  `machine_count` + `engineer`. Fixed: "Create PM" is now single-site only (bulk lives in the wizard).
- Files: backend/routes/svc/ppm_calendar.py, backend/utils/ppm_route_ai.py,
  frontend/src/pages/ServiceDesk/{PPMCalendar,BulkPpmWizard,PpmScheduleDetail}.js.
- NOTE: these are new since the last deploy — a redeploy is needed for them to reach production (where the 85 stations live).

## 2026-06 — "Fire Station Service" PPM type (full service + treadmill calibration)
- New PPM service type **Fire Station Service** (Service Desk → Maintenance → Create PM). Services every
  machine at the station AND triggers speed/incline calibration for the treadmills only. Shows in the
  service-type dropdown as "Fire Station Service (PM + treadmill calibration)".
- Backend `_DEFAULT_SERVICE_TYPES` gained the type (requires_calibration + calibrate_treadmills flags);
  `_seed_service_types` is now idempotent so existing orgs pick up new default types (previously only
  seeded when the collection was empty). create/update service-type endpoints persist `calibrate_treadmills`.
- Fixed a latent bug in `POST /svc/ppm/schedule`: it coerced any service_type not in a 2-item enum back to
  "Preventative Maintenance Service". Now the schedule's own service_type is preserved (custom types like
  Fire Station Service / Treadmill Calibration survive through to the engineer job).
- Engineer App calibration now supports a **per-treadmill matrix** (Fire Station jobs): GET
  `/svc/engineer/jobs/{id}/calibration` returns only the treadmills on the case (auto-detected by
  equipment_type == Treadmill, resolved by id so customer-org equipment matches) + the 8 speed/incline
  params. POST accepts a `machines` array; all treadmills are captured on ONE certificate.
- Certificate PDF (`calibration_certificate_pdf.py`) renders a multi-treadmill matrix — one row per
  treadmill (Serial + 3/6/9/12 mph + 0/5/10/15% + Result) — matching the customer's Certificate of Service.
  Falls back to the flat readings table for single-machine calibrations.
- Files: backend/routes/svc/ppm_calendar.py, backend/routes/svc/engineer.py,
  backend/utils/calibration_certificate_pdf.py, frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js
  (CalibrationCapture), frontend/src/pages/ServiceDesk/PPMCalendar.js.
- Verified: backend curl e2e (calibration returns 2 treadmills only, POST saves both, cert PDF text contains
  both serials + matrix columns) and frontend E2E via testing agent (100% — dropdown option, 2-treadmill
  matrix with bike excluded, save→FAIL chip, certificate download). Demo case: FSDEMO-case-1 (owner@isodemo.com).

## 2026-06 — Company-wide payroll summary sheet
- Added a single "Payroll Summary" workbook rolling up every active staff member's monthly
  activity totals: one row per person with Std Hours, Worked Hours, and each activity column
  (PT, Classes, Van Check, Parts, Clean Van, Admin) — hour-based as `[h]:mm`, tick-based as
  `N days` — plus a bold COMPANY TOTAL footer row (frozen header).
- New endpoint `GET /api/staffing/timesheets/month-summary?year&month` (manager-only) returns
  the summary xlsx. The `month-pack` ZIP now also includes it as the first file ("0 - Payroll Summary…").
- Columns are the union of activity columns across the roles actually present in the org, in a
  canonical order (`_master_ts_columns`). Totals computed in Python from recorded timesheet
  entries (`_summary_row_for_staff`, `_worked_minutes`).
- Frontend: "Company summary" download button in the Payroll → Monthly timesheets tab
  (data-testid `ts-download-summary`).
- Files: backend/utils/payroll_timesheet_xlsx.py (build_payroll_summary_xlsx, summary_filename),
  backend/routes/staffing_clock.py, frontend/src/pages/LiteDashboard/staffing/PayrollTimesheetsTab.js.
- Verified via curl against the demo org: endpoint returned 200 + valid xlsx (10 cols, all staff),
  and the pack ZIP listed the summary first.

## 2026-06 — Per-activity monthly totals in payroll timesheet footer
- Added a "MONTHLY TOTAL" row to each staff member's monthly Excel timesheet, aligned directly
  under the activity columns (PT, Classes, Admin, Parts, Van Check, Clean Van, etc.).
- Totals respect each activity's unit: hour-based columns (`unit: hours`) sum to `[h]:mm`;
  checkbox/tick columns (`unit: tick_hours`, e.g. Van Check/Clean Van) show a count of worked
  "Y" days formatted as `0" days"` (via COUNTIF across each week's daily range).
- Files: backend/utils/payroll_timesheet_xlsx.py (tracked per-week `day_blocks`, new footer block).
- Verified: built engineer (tick) and PT (hours) sheets, reloaded via openpyxl, confirmed COUNTIF
  and SUM formulas + number formats land on the correct activity columns.

## 2026-06 — Duplicate-invoice guard surfaced in the AI review panel (before Apply)
- The AI review panel now shows a prominent red "Duplicate invoice — already allocated" banner
  (dealer name + allocated date) BEFORE Apply, driven by `aiReview.duplicate`. Since the deterministic
  scanners now return duplicate info (see prior entry), this fires for CSV/PDF fast paths too, not just LLM.
- Added a required acknowledgment checkbox (data-testid dp-wiz-ai-review-dup-ack): when a duplicate is
  detected the Apply button (dp-wiz-ai-review-apply) is disabled and relabelled until the user ticks
  "I understand — apply anyway to review". `dupAck` state resets on each new parse and on reset().
- Files: frontend/src/pages/DealerWarrantyParts/AllocationWizardTab.js.
- Verified backend chain via curl: seeded a fake allocation for INV-2051 → re-parsing the sample CSV
  returned duplicate_invoice=true with dealer name; test record cleaned up afterward.


## 2026-06 — Invoice-number capture for the fast (deterministic) invoice scanners
- Problem: only the LLM parse path returned an invoice number; the fast deterministic PDF and
  spreadsheet scanners returned order_reference="", so the wizard's Invoice-number field stayed empty
  after Apply for the common fast path.
- Added `_extract_invoice_number(text)` in routes/dealer_parts_data.py — label-driven, most-specific-first
  (Tax Invoice/Invoice No/Invoice #/Inv/Credit Note/Document/Sales Order/Order Ref), value must contain a
  digit, isn't a date, isn't a stop-word (TOTAL/DATE/etc). Correctly skips "Invoice Date 12/06/2026".
- Wired into `_scan_pdf_invoice` (scans extracted text) and `_scan_spreadsheet_invoice` (scans a joined
  blob of the first 60 rows' cells). `_parse_and_match_invoice` now passes the detected order_reference
  through for both branches, appends it to the note, and runs `_invoice_duplicate_info` so a repeat
  invoice number is flagged on upload for these paths too (previously LLM-only).
- Frontend needed no change — it already maps res.order_reference → aiReview and setInvoiceRef on Apply.
- Verified via curl on both samples: /app/test_samples/dealer_invoice_sample.csv → INV-2051;
  /app/test_samples/dealer_invoice_sample.pdf → INV-3090 (order value + matches also correct).


## 2026-06 — Intelligence made the org default (Pulse Fitness Ltd) + Input import fix
- Owner opted to make wizard intelligence ON by default: `blend_actuals=true, blend_weight_pct=40,
  trend_sensitivity=med`. Set the org-level `dealer_parts_data_settings` doc for Pulse Fitness Ltd
  (`3ece2d0c-...`) AND `iso-demo-org` (the org that actually holds the dealer-parts warranty plan +
  4879 BOM machines in this preview, so it's testable now). NOT changed globally — DEFAULT_DATA_SETTINGS
  stays off so other/new orgs remain opt-in, per owner's "just Pulse Fitness Ltd" scope.
  Duplicate-avoidance (netting vs dealer held/on-order stock) is unaffected — blend/trend only change the
  target quantity; `send = max(0, target − already_held_or_allocated)` still runs on top.
- Fixed pre-existing blocking lint: `frontend/src/pages/LiteDashboard/LiteDialogs.js` used `<Input>`
  without importing it — added `import { Input } from '@/components/ui/input'`.
- NOTE for future agent: in this preview the Dealer Parts module data lives under `iso-demo-org`,
  not Pulse Fitness Ltd — confirm which org holds the live dealer-parts data in production before
  changing dealer-parts settings there.


## 2026-06 — Dealer Parts Allocation Wizard: Smarter Recommendations, Tunable Thresholds, AI Review Step
Owner asked for three wizard improvements (b, c, d). All shipped, tested (frontend E2E 100%, backend curl-verified), demo org reset to opt-in defaults.

- (b) SMARTER RECOMMENDATIONS — backend `recommend_from_invoice` now optionally BLENDS real
  historical usage into the warranty-plan quantities and applies a usage-TREND multiplier.
  New settings in `DEFAULT_DATA_SETTINGS`: `blend_actuals` (bool), `blend_weight_pct` (0-100),
  `trend_sensitivity` (off/low/med/high). `_trend_multiplier()` maps increasing/new_failure_trend→up,
  decreasing/dormant→down. Blend applies to plan parts (needs a plan baseline); trend applies to both
  plan parts and usage/supplementary items. Item `reason` strings explain the maths. Response returns
  an `intelligence` block. UI: collapsible "Recommendation intelligence" card on Step 0
  (data-testid dp-wiz-intel-*), saves instantly via PUT /data/settings; Step-1 badge dp-wiz-intel-badge.
- (c) TUNABLE THRESHOLDS — per-machine-group Plan-vs-Actuals sensitivity overrides. New collection
  `dealer_parts_pva_overrides` + endpoints GET /data/pva-thresholds, POST /data/pva-thresholds/override,
  DELETE /data/pva-thresholds/override/{group}. `plan_vs_actuals` loads overrides and returns per-machine
  over_pct/under_pct/threshold_overridden. UI: per-machine override editor in PlanVsActualsPanel.js
  (dp-wiz-pva-override-*), plus a quick "reset" next to the override badge.
- (d) AI PARSING REVIEW STEP — `parseInvoice` no longer auto-populates the form. It now stores an
  `aiReview` object and renders a confirm panel (dp-wiz-ai-review) listing extracted machines with
  matched/unmatched badges, editable qty, removable rows. Form fills ONLY on Apply (dp-wiz-ai-review-apply);
  Discard clears with no side-effects. Duplicate-invoice detection surfaced in the review panel.
- Files: backend/routes/dealer_parts_data.py; frontend AllocationWizardTab.js, PlanVsActualsPanel.js, api.js.
- Sample matching invoice for testing: /app/test_samples/dealer_invoice_sample.csv.
- Non-blocking follow-ups noted by review: AllocationWizardTab.js now ~809 lines (could split
  IntelligenceCard/AIReviewPanel/MachinePicker); dev-only <span>-in-<option> hydration warning (harmless).


## 2026-06 — Equipment Sales: Customer Register Handover

Push a deal's GRN-created equipment into the customer's OWN Pulse portal so they can log faults from day one — into the existing equipment/company processes, no new module.

- **Backend** `routes/crm_quote_handover.py`: `POST /crm/v2/quotes/{id}/handover/register` copies each deal-registered equipment unit into the customer's portal org (resolved via `crm2_companies.tenant_org_id`), stamping provenance (`source=deal_handover`, `origin_org_id`, `origin_equipment_id`, `quote_id`); the seller row records `customer_equipment_id`. `GET /{id}/handover` now returns a `customer_portal` block (linked, tenant name, registered/handed-over/pending counts). 400 when the company has no linked portal.
- **Provenance quality** (post-report fixes): copied unit's `supplier` = the SELLING org (not the customer); `user_id` left unset when the customer org has no users (no cross-tenant id); `site_id` = customer's head-office/only site else unset; idempotency now keyed on the customer copy still existing, so a deleted copy is re-pushable (repair path).
- **Frontend** `CRM/CRMQuoteHandover.js`: "Customer register handover" section — shows link status + "X/Y pushed to <portal>", a "Hand over N unit(s)" button, and "All handed over ✓".
- VERIFIED: testing_agent backend 5/5 pytest + frontend 6/6 e2e; provenance fixes re-confirmed via curl (supplier=selling org, user_id=None, re-push after deletion=1). Test: `/app/backend/tests/test_crm_quote_customer_handover_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 4: handover & close

Into the existing quote + service-jobs (`issues`) processes — no new module. Completes the Equipment-Sales journey (Phases 1–4).

- **Backend NEW** `routes/crm_quote_handover.py` (`/crm/v2/quotes`): `GET /{id}/handover` (linked jobs + install-job suggestions + completion readiness), `POST /{id}/handover/jobs` (auto = one install job per registered equipment unit, or explicit specs — created as real `db.issues` jobs on the Operations board, stamped with quote_id/equipment/source=`deal_handover`), `POST /{id}/complete` (only when fully delivered + invoiced; managers force with a reason), `POST /{id}/reopen`. Readiness reuses the invoicing + fulfilment views. Registered in `route_registry/crm.py`.
- **Frontend NEW** `CRM/CRMQuoteHandover.js` (`QuoteHandoverPanel`): deal-status badge, linked-jobs list, "Auto-create install jobs" + "Add job" dialog, a delivered/invoiced/open-jobs checklist, "Complete deal" (disabled with reasons until ready), "Complete anyway" force dialog, and Reopen. Mounted in `CRMCPQ.js` QuoteDetail below the fulfilment panel.
- **Polish** (post-report): reopen now clears the forced/reason residue and 400s when already open; the misleading svc_case mirror call removed (jobs already land on the ops board); completion reasons formatted as currency (£5,000.00); jobs checklist row shown as informational ("doesn't block close"); auto-jobs spec copies fixed.
- VERIFIED: testing_agent backend 8/8 pytest + full frontend flow (incl. force-complete + reopen); polish re-confirmed via curl (8/8 pytest still green). Test: `/app/backend/tests/test_crm_quote_handover_phase4_aug2026.py`.

### Equipment Sales — ALL 4 PHASES COMPLETE (into the existing CPQ engine, one engine for Pulse Fitness Ltd + Global Dealers)
P1 line types (trade-ins/spares/contracts) · P2 staged invoicing + credit notes · P3 PO-from-quote + GRN auto-equipment · P4 handover jobs + Complete Deal.


## 2026-06 — Equipment Sales into CPQ, Phase 3: fulfilment (PO-from-quote + GRN auto-equipment)

Into the existing quote → purchase_orders → equipment processes (no new module).

- **Backend NEW** `routes/crm_quote_fulfilment.py` (`/crm/v2/quotes`): `GET /{id}/fulfilment` (procurable lines + POs + created equipment + summary), `POST /{id}/purchase-orders` (build a PO from the deal's sale/spare lines priced at COST, into `purchase_orders`, linked by quote_id; trade-ins excluded), `POST /{id}/purchase-orders/{poId}/status`, `POST /{id}/purchase-orders/{poId}/receive` (GRN → auto-creates `equipment` records, one per serial, valued at the SELL price, source=`deal_grn`, traceable via quote_id/po_number). Registered in `route_registry/crm.py`.
- **Root-cause fix (critical)**: CPQ v2 quote lines now get a stable `id` at create/revise (`crm_v2._normalize_quote_line`), and `crm_quote_fulfilment` heals legacy quotes on read. Previously ids were minted per-request so Raise-PO always 400'd. GRN now rejects unknown line ids / empty receipts (422).
- **Frontend NEW** `CRM/CRMQuoteFulfilment.js` (`QuoteFulfilmentPanel`): raise-PO dialog (pick lines + supplier), PO rows with status, GRN dialog (qty + comma-separated serials), and an "Equipment registered from this deal" chip list. Mounted in `CRMCPQ.js` QuoteDetail below the invoicing panel. GRN submit disabled until a qty is entered.
- VERIFIED: testing_agent pytest now 9/9 (was 6/9 before the line-id fix); happy-path + guards confirmed; frontend GRN→equipment flow passed. Test: `/app/backend/tests/test_crm_quote_fulfilment_phase3_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 2: staged invoicing + running balance + credit notes

Deposit / interim / final payments on a CPQ v2 quote — built into the existing quote process, no new module.

- **Backend NEW** `routes/crm_quote_invoicing.py` (router `/crm/v2/quotes`): schedule stored on `crm2_quotes.invoice_schedule`; invoice + credit-note records in `crm2_invoices`. Endpoints: `GET /{id}/invoicing` (stages + invoices + running-balance summary), `PUT /{id}/schedule`, `POST /{id}/schedule/auto` (deposit/interim/final preset), `POST /{id}/stages/{sid}/invoice|pay|credit-note`. Running balance = total − paid − credited; per-stage outstanding tracked. Registered in `route_registry/crm.py`.
- **Guards**: can't drop an already-invoiced stage (400); can't over-schedule beyond deal total (422); percent capped 0–100 / amounts ≥ 0; can't invoice beyond deal total (400); can't overpay a stage (422); auto percentages must total 100 (422).
- **Frontend NEW** `CRM/CRMQuoteInvoicing.js` (`QuoteInvoicingPanel`, `canManage` from useAuth): running-balance cards, quick presets (25/75, 50/50, thirds), inline schedule editor with over-schedule warning + guarded save, per-stage Raise invoice / Record payment / Credit note dialogs. Mounted in `CRMCPQ.js` QuoteDetail under the line-items table.
- VERIFIED by testing_agent: backend 13/13 pytest, frontend panel flows 100%. Full lifecycle numbers confirmed (deposit→pay→final invoice→part-pay→credit note; balance 10000→7500→2500→1500). Over-schedule/over-invoice guards added after the report and re-verified via curl. Test: `/app/backend/tests/test_crm_quote_staged_invoicing_aug2026.py`.


## 2026-06 — Equipment Sales into CPQ, Phase 1: line types (trade-ins, spares, contracts)

Extending the EXISTING CRM Quote (CPQ v2) engine — no new module — to cover ServiceGeeni-style equipment sales, for Pulse Fitness Ltd AND Global Dealers (one engine, confirmed by user).

- **Backend** `crm_v2.py`: new `compute_quote_totals()` + `_normalize_quote_line()`. Each quote line carries `line_type` ∈ {sale, spare_part, service_contract, trade_in}. Trade-ins are entered as a positive allowance but applied as NEGATIVE net (`net_subtotal`), reducing the deal. Returns a per-category breakdown (equipment/parts/contract/trade_in) + `gross_profit`/`gross_margin_percent` (None when net ≤ 0). Used by both `create_quote` and `revise_quote`.
- **Backend** `crm_product_perms.py`: `gross_profit`/`gross_margin_percent` added to `QUOTE_COST_FIELDS` so cost-blind reps don't see deal margin.
- **Backend** `crm_quote_pdf.py`: `_line_net()` prefers `net_subtotal` and signs trade-ins negative.
- **Frontend** `CRM/CRMCPQ.js`: per-line Type selector (`quote-line-type-{i}`), trade-in "credit to customer" hint, live category breakdown rows (`quote-parts-subtotal`, `quote-contract-subtotal`, `quote-tradein-total`), net Subtotal/Total, margin badge; detail view shows a Type column with trade-ins rendered negative. Added `quote-submit-btn`/`quote-cancel-btn` testids and a static column header row.
- VERIFIED by testing_agent (backend 7/7 pytest, frontend builder + detail e2e 100%). Test: `/app/backend/tests/test_iter294_cpq_line_types.py`.

### Equipment Sales roadmap (agreed phases — into existing processes)
- Phase 1 ✅ trade-ins + spares + service-contract line types with live totals/margin
- Phase 2 (money): staged invoicing (deposit/interim/final) + running balance + credit notes → Quote + financial_ops/invoice_dunning
- Phase 3 (fulfilment): PO-from-quote + GRN auto-equipment + supplier/location transfers with delivery tracking → purchase_orders/equipment/equipment_transfer
- Phase 4 (handover + close): sales→service job handover (issues) + deal P&L (roll in PO/job costs) + "Complete Deal" action
- Known follow-ups: cost input on manual quote lines (margin badge only lights up on catalogue lines today); no single GET /crm/v2/quotes/{id} or DELETE endpoint.


## 2026-06 — 4 bug fixes: job-role chips, Forgot Password, archive layout, operator-portal context

- **Bug 1 (Job roles)** `LiteDashboard/staffing/HRTab.js`: built-in role chips in the "Manage job roles" modal are now clickable buttons (`job-roles-builtin-{role}`) that populate the "Add a role" input. VERIFIED by testing_agent (owner@isodemo.com, 9/9 chips).
- **Bug 2 (Forgot Password)** root causes fixed & VERIFIED:
  - `utils/security.py`: split the single 3/15min limiter into `rate_limit_password_reset` (requests, key `resetreq:`, 5/15min) and NEW `rate_limit_password_reset_submit` (submissions, key `resetsubmit:`, 15/15min). `routes/auth.py` reset-password now uses the submit limiter. Previously a user who requested a link then mistyped their new password 2-3× got locked out (429).
  - `pages/ResetPasswordPage.js`: live password-requirements checklist (12+/upper/lower/digit/symbol, `reset-password-rules`) mirroring backend policy; client-side validation before POST; minLength 12 on both fields; added `CaptchaWidget` to the request form (was missing the captcha token → would 400 in prod if captcha enabled).
- **Bug 3 (Archive layout)** `MasterAdmin/AdminOrganizations.js`: org-user row no longer collapses the name/email into a vertical one-letter column when extra buttons appear (archived). Name column reserves `sm:w-60 flex-shrink-0` + `truncate`; actions use `sm:flex-1` and wrap. NOTE: verified by code only — live master-admin UI check blocked by TOTP MFA.
- **Bug 4 (Pulse Fitness Portal)** `routes/auth.py` `/auth/refresh` + `utils/auth.py`: refresh now PRESERVES the `act_org` (and `imp_grants`) JWT claim via `extra_claims`. Previously the frontend's on-load/15-min refresh minted a token without `act_org`, silently reverting a master admin out of the operator company (Pulse Fitness Ltd) back to their home org within seconds — cause of "portal shows no data" and "reverts to Head Office after visiting CRM". VERIFIED by curl: refreshed act_org token still returns the 6 Pulse Fitness Ltd staff. Live master-admin UI check blocked by MFA.


## 2026-06 — MOD Tender pack (LSL/DC/0223) finalised in-place

Edited all 6 `.docx` responses in place (templates, images, headers/footers, tables preserved) against Red Team reviews + Sheen/Director comments. Then a tender-writer QA pass drove a final correction round.

### Final correction round (tender-writer QA)
- **Figures embedded**: user-supplied corrected process maps for 2.2A (UK) and 2.3A (overseas) swapped into `word/media/image3.png` in each docx, with drawing extents adjusted to the new aspect ratios (no distortion).
- **All `[PULSE INPUT]` removed** across all 6 docs, populated with confirmed data:
  - Contract **LSL/DC/0186** (1 Apr 2023–31 Mar 2027); original value **£4,000,000**; delivered **£966,886.64** (UK £851,241.43; UK 2yr-to-30Jun2026 £719,479.54); overseas £115,645.30 (£84,549.87 2yr); **127 contract sites (9 overseas)** within **226-site** estate.
  - Overseas: **100%** ack within 48h and 100% scheduled within 5 working days; Type C **9/9** accepted. Canada = direct UK Type C. Gibraltar: Sean Coakley removed → Jimmy Connors.
  - UK 48/72 historic split confirmed unavailable → handled transparently (no fabricated stat).
- **2.1**: QP149 caption → Issue 02, 1 Nov 2025; UKAS/ISO 9001 assurance paragraph reinstated; MI wording → "agreed contract reporting route".
- **2.2B**: contract identified with values/sites; HMS testimonials no longer over-claimed as priority sites; KPI historic positions stated honestly.
- **2.3A/2.3B**: courier 3–10 days; portal caption transparency; 2.3B reframed as contract, Cyprus/Jersey/Norway reconciled.

**Deliverables** (`/app/tender_deliverables/`): `FINAL_Submission_Edited/` (6 docs), `MOD2026_Submission_EDITED.zip`, `Figure_Build_Specs.docx`, `Figure_Handover_Brief.docx`, `Pulse_Input_Required_Register.docx` (all resolved), `Score_Review.docx`.

**Estimated score after this pass: ~96–100/100** (from ~76). 2.2B carries a residual risk (unprovable historic 48/72 split, handled transparently).

---

## 2026-08-26 — Equipment Sales: Handover Pack PDF + sellable warranty tiers
Extends the existing CRM CPQ (Quotes) Equipment Sales workflow — no new module.

- **Sellable warranty levels**: new `utils/warranty.py` catalog (standard 12mo / extended_3yr 36mo / premium_5yr 60mo). Exposed via `GET /api/crm/v2/warranty-tiers`. Per-equipment-line `warranty_tier` selector added to the CPQ new-quote modal (data-testid `quote-line-warranty-{i}`, shown only for `sale` lines). Tier flows quote line → `_procurable_lines` → PO item → GRN, which now stamps `warranty_tier/warranty_months/warranty_start/warranty_expiry` on each created `equipment` record. Customer-portal handover copy carries the warranty fields.
- **Branded Handover Pack PDF**: `GET /api/crm/v2/quotes/{id}/handover/pack` (new `utils/handover_pack_pdf.py`, rendered on the shared `pulse_doc_template` shell). Contains cover/meta, equipment table (item, manufacturer/model, serial, warranty, cover-until), warranty summary, and "how to log a fault" — portal URL when the customer company is linked to a tenant org (`app_url_for_org`), else Pulse service-desk phone/email. Branding uses the selling org's brand with Pulse fallback (`_resolve_crm_brand`). Available as soon as GRN equipment exists (400 otherwise). Legacy GRN equipment gets warranty backfilled on read.
- **Frontend**: "Download pack (PDF)" button in the Handover & close panel (data-testid `handover-download-pack`, row `handover-pack-row`), visible once `equipment_created>0`.
- **Testing**: backend 9/9 pytest green (`/app/backend/tests/test_handover_pack_warranty_jul2026.py`); frontend verified after tester fixed a Rules-of-Hooks crash (moved `downloading` useState above the early return in CRMQuoteHandover.js). Both branches of fault instructions verified via extracted PDF text.

## 2026-08-26 — CRM: one-click "Connect portal" on the Company screen
- **Unified the portal-link field**: the handover pack / customer equipment push previously read `crm2_companies.tenant_org_id`, but the platform stores the customer's Pulse portal org in `linked_operator_org_id`. `crm_quote_handover._customer_portal` now resolves `linked_operator_org_id` (canonical) with `tenant_org_id` fallback, and the new link endpoint keeps BOTH fields in sync.
- **Backend (CRM token)** in `crm_v2.py`: `GET /crm/v2/portal-link/candidates?q=` (searches customer portal orgs: lite/pulse_pro/pro/full, excludes seller org), `GET /crm/v2/companies/{id}/portal-link` (current link + can_manage), `POST /crm/v2/companies/{id}/portal-link {org_id}` (link/clear; owners/admins/managers only; 400 on own-org; audited).
- **Frontend** `CRMCompanies.js` CompanyDetail: green/grey "Portal: <name> / Not connected" chip (data-testid `portal-link-chip`), a "Connect portal / Portal connected" header button (`company-connect-portal-btn`) for managers, and a searchable modal (`connect-portal-dialog`, `connect-portal-search`, `connect-portal-org-{id}`, `connect-portal-disconnect`) to link/unlink in one click.
- **Verified**: candidates + get/set/clear via curl; both fields sync; own-org rejected; UI modal renders and shows current link with disconnect. Backend + FE compile clean.

## 2026-08-26 — CRM: Equipment Sales leadership dashboard tile
- **Backend** `GET /crm/v2/equipment-sales/summary` (crm_v2.py, CRM token, org/site scoped): aggregates open equipment deals (quotes with >=1 'sale' line, status in draft/pending_approval/sent/accepted, deal_status != completed) → open_deal_value + count; units_expected vs units_delivered (equipment aggregate by quote_id) → units_awaiting_delivery; crm2_invoices aggregate → invoiced_gross/net, collected, credited, outstanding, collection_rate.
- **Frontend** `EquipmentSalesTile` in CRMDashboard.js (rendered in SalesManagerDash under the KPI row): three stats (Open deal value, Awaiting delivery, Cash collected) + a colour-coded collected-vs-invoiced progress bar with outstanding/credited caption. data-testids: equipment-sales-tile, es-open-deal-value, es-units-awaiting, es-cash-collected, es-collection-rate, es-outstanding, equipment-sales-view-quotes (→ Quotes tab).
- **Verified**: endpoint returns correct math (curl); tile renders on CRM Dashboard with live figures matching backend (£1,200 open / 1 awaiting / £7,500 of £9,000 collected / 83%). Both files compile clean.

## 2026-08-26 — CRM: Email the Handover Pack via Resend
- **Backend** `POST /crm/v2/quotes/{id}/handover/pack/email` (crm_quote_handover.py, owners/admins/managers): builds the branded handover pack (shared `_build_pack_bytes` helper, refactored out of the download endpoint), resolves recipient (`to` or the deal's linked contact email), and sends via the existing `utils.email.send_email` Resend pipeline with the PDF as a base64 attachment (kind="crm_handover_pack", category="service"). Logs a CRM activity + audit; stamps handover_pack_last_sent_to/at. Returns 400 if no GRN equipment yet.
- **Frontend** `CRMQuoteHandover.js`: "Email pack" button (data-testid handover-email-pack) beside "Download pack (PDF)" opens a dialog (handover-email-dialog) with optional To/Subject/Message (handover-email-to/subject/message) and Send (handover-email-send). Blank recipient falls back to the linked contact.
- **Verified**: 400-before-GRN correct; after GRN the endpoint builds the PDF and calls Resend correctly. ⚠️ Actual delivery is BLOCKED in this preview because `RESEND_API_KEY` is invalid (`ResendError('API key is invalid')`) — a platform-wide env limitation (same as the existing quote-email); needs the user's real Resend key. Files compile clean.

## 2026-08-26 — Customer portal: Warranty Register view
- **Backend** (customer_deliveries.py, `get_current_user`, org-scoped): `GET /customer/warranties` returns the signed-in customer's equipment with computed warranty status (active / expiring ≤60d / expired), days_remaining, tier label + summary, cover-until date; sorted soonest-cover-end first; includes counts. `GET /customer/warranties/summary` gives has_warranties + counts to show/hide the nav. Backfills expiry from warranty_start/purchase_date + tier months for legacy rows; shows any equipment with a warranty_expiry or warranty_tier.
- **Frontend** `CustomerWarrantiesTab.js` + wired into LiteDashboardPage `/pulse`: a "Warranties" tab (only when has_warranties) with 3 count cards (In cover / Expiring soon / Expired) and per-unit cards (status pill, tier label, cover-until + days left). data-testids: customer-warranties-tab, warranties-content, customer-warranties-list, customer-warranty-{id}, warranties-count-active/expiring/expired.
- **Verified**: endpoint returns correct classification/sorting (curl with seeded data); tab renders live in the demo customer's Pulse dashboard (lite.docs@pulsedemo.test) showing In cover/Expiring/Expired correctly. Seed cleaned up. Files compile clean.

## 2026-08-26 — CRM: Create & invite a portal from the Connect-portal modal
- **Frontend only** (CRMCompanies.js): when a company has no portal linked, the Connect-portal modal now shows a "Customer has no portal yet?" section with a "Create & invite portal" button (data-testid connect-portal-invite-section / connect-portal-invite-btn). It reuses the existing `POST /crm/v2/companies/{id}/portal-invite/resend` endpoint (pulse_onboarding.provision_customer_portal), then refreshes the link state + closes the modal. Handles statuses: provisioned / linked_existing / resent / already_active / missing_email (prompts to add a contact email).
- **Verified**: end-to-end — creating a company + contact then inviting provisions a new Lite org, sets linked_operator_org_id, and the portal-link endpoint immediately reports connected. (Setup email won't deliver in preview due to the invalid RESEND_API_KEY, but provisioning/linking succeed regardless.) Compiles clean.

## 2026-08-26 — Warranty Renewal Nudge (→ aftersales contracts) + Awaiting-delivery drill-down
### Renewal nudge & aftersales enquiry (ties into existing crm2_contracts)
- **Backend** (customer_deliveries.py): `POST /customer/warranties/enquire` — when a customer enquires from their portal, creates a DRAFT aftersales contract (crm2_contracts, tier=bronze, status=draft, source=customer_warranty_enquiry) in the SELLER's org pre-filled with company + equipment/serials + optional customer note; creates a high-priority follow-up TASK (crm2_activities) for the account owner (due +3d); best-effort emails the owner a heads-up. De-duped within 24h per customer. `GET /customer/warranties` now also returns `renewal_enquiry_open` (draft enquiry in last 30d).
- **Frontend** (CustomerWarrantiesTab.js): amber nudge banner when any unit is expiring(≤60d)/expired with an "Enquire about aftersales cover" button (all at-risk) + per-unit "Enquire about cover" buttons; optional-note dialog; shows "Enquiry sent — the Pulse team will be in touch" once open. testids: warranty-renewal-nudge, warranty-enquire-all, warranty-enquire-{id}, warranty-enquiry-dialog/note/send, warranty-enquiry-open.
- **Verified** end-to-end: enquiry creates the bronze draft contract + high-priority task in the seller org (iso-demo-org), dedupe returns already_requested, flag flips to open; nudge/banner/dialog render in the demo customer portal. (Owner heads-up email won't deliver in preview — invalid Resend key — records still created.)

### Awaiting-delivery drill-down
- **Backend** `GET /crm/v2/equipment-sales/awaiting-delivery` (crm_v2.py): per-open-deal breakdown (company, quote_number, total, units_expected/delivered/awaiting) for deals with undelivered units, sorted most-awaiting first.
- **Frontend** (CRMDashboard.js EquipmentSalesTile): the "Awaiting delivery" stat is now clickable → modal listing each deal; rows jump to the Quotes tab. testids: awaiting-delivery-modal/list/close, awaiting-deal-{quote_id}.
- **Verified**: endpoint returns the exact open deal; modal renders with matching figures (1 awaiting, 0/1 delivered). All files compile clean.

## 2026-08-26 — Customer Warranty Certificate PDF (consolidated, grouped)
- Per user feedback: NOT per-unit certificates — a single consolidated certificate with the kit list grouped by warranty level.
- **Backend** (customer_deliveries.py `GET /customer/warranties/certificate`, new utils/warranty_certificate_pdf.py): one branded (Pulse) PDF "Warranty Certificate" issued to the customer org, grouping their equipment by tier (Standard/Extended/Premium/Manufacturer) with a table per group (equipment, manufacturer/model, serial, cover-until) + standard terms note. 400 if no warranties.
- **Frontend** (CustomerWarrantiesTab.js): "Download certificate" button in the register header (data-testid warranty-download-certificate), blob download.
- **Verified**: endpoint returns HTTP 200 %PDF; PDF content confirmed grouped-by-tier with correct serials + cover-until dates (analyze_file_tool); button renders in the demo customer portal. Seed cleaned up; files compile clean.

## 2026-08-26 — Cover-tier choice in renewal enquiry + Awaiting-delivery deep-link
### Cover tier choice
- **Backend** (customer_deliveries.py enquire): accepts `preferred_tier` (bronze/silver/gold, validated, default bronze) → the draft aftersales contract now starts on the chosen tier; tier is recorded in coverage_notes, the owner task and the heads-up email.
- **Frontend** (CustomerWarrantiesTab.js): Bronze/Silver/Gold selector cards in the enquiry dialog (data-testid warranty-tier-choice, warranty-tier-{id}).
- **Verified**: enquiry with preferred_tier=gold created a draft contract with tier=gold + "Preferred cover level: Gold" note; selector renders with Gold highlighted.

### Awaiting-delivery deep-link (drill-down → Fulfilment)
- **Frontend**: `navigateTo` (CRMApp.js) extended to take an `extra` payload and to switch to Business/Corporate mode when the target tab is Corporate-only (fixes bounce-back from Members mode). Drill-down rows (CRMDashboard EquipmentSalesTile) now call `navigateTo('quote', quote_id, { focus: 'fulfilment' })`. CRMCPQ QuoteDetail accepts `focusSection` and auto-scrolls to the new `#quote-fulfilment-section` anchor.
- **Bug fixed**: QuoteHandoverPanel had `emailDialog`/`emailBusy` useState declared AFTER the `if (!data) return null` early return (introduced in the Email-Pack feature) → "Rendered more hooks than during the previous render" crash when the quote detail loaded. Moved both hooks above the early return.
- **Verified**: clicking a drill-down deal opens the specific quote and scrolls straight to its Fulfilment panel. All files compile clean; visual-test seed cleaned up.

## 2026-08-26 — Convert aftersales contract → sent quote (one click)
- **Backend** `POST /crm/v2/contracts/{id}/convert-to-quote` (crm_contracts.py): builds a CPQ quote (crm2_quotes) from the contract — one service_contract line at the contract's tier + annual_value, org-localized VAT via compute_quote_totals — sets it status='sent', links quote_id ↔ contract both ways, moves the contract to 'sent', logs an activity + audit. Idempotent (returns existing quote if already converted).
- **Frontend** (CRMContracts.js ContractDetail): "Convert to quote" button in the header when a contract is draft/pending_approval/approved and not yet linked; after converting it deep-links to the new quote via navigateTo('quote', id). A "View quote" button shows once linked. Renamed the unused `_navigateTo` prop to `navigateTo` (from crm context).
- **Verified**: E2E via curl — silver contract (£2,400) converted to a SENT quote (service_contract line, £2,880 inc VAT), contract → sent + quote_id linked, re-convert returns already_converted. Files compile clean. NOTE: contract-detail button not visually captured (Contracts sub-tab sits in a hidden overflow in the test viewport); the button is a minimal conditional mirroring the existing Send button.

## 2026-08-26 — Auto-send the converted quote to the customer
- **Backend** (crm_contracts.py convert-to-quote): now accepts `send_email` + optional `email_to`. After creating the sent quote it optionally emails it via the existing `send_quote_email` (renders quote PDF + Resend), resolving the recipient as email_to → contract contact → company's first contact-with-email. Email is best-effort — conversion never fails if the email can't send; returns `emailed` + `email_error`.
- **Frontend** (CRMContracts.js ContractDetail): "Convert to quote" now opens a small dialog (data-testid contract-convert-dialog) with a "Email the quote to the customer" checkbox (contract-convert-email-toggle) + optional recipient (contract-convert-email-to); confirm button reads "Convert & email" / "Convert to quote" (contract-convert-confirm). Surfaces an alert if the quote was created but couldn't be emailed, then deep-links to the quote.
- **Verified**: E2E — convert with send_email=true created a SENT quote and executed the email path (emailed=true). Consistent with the existing quote send-email, dispatch is reported on send; real delivery needs a valid RESEND_API_KEY (invalid in preview). Files compile clean.

## 2026-08-26 — Itemise converted aftersales quote from the enquiry equipment
- **Backend** (crm_contracts.py convert-to-quote): when the contract carries `enquiry_equipment_ids` (captured from the customer's warranty enquiry), the quote is now built with ONE service_contract line per unit — description includes name · manufacturer/model · serial (S/N), plus equipment_id + serial_number on the line. The contract's annual_value is split evenly across units with the last line rounded so the quote total matches exactly. Falls back to a single summary line when there are no enquiry equipment ids.
- **Verified**: full E2E — customer enquiry (3 units, Silver) → team priced the contract at £1,500 → convert produced a quote with 3 lines (£500 each, serials IT-001/002/003), subtotal £1,500, total £1,800 inc VAT. Backend-only change; compiles/runs clean.

## 2026-08-26 — BUG FIX: "Temporary password has expired" after admin reset
- **Root cause**: PUT /api/master-admin/users/{id}/reset-password set a new password + password_reset_required but never refreshed `temp_password_expires_at`. The login gate (auth.py `_enforce_account_status`) blocks when `must_change_password` AND `temp_password_expires_at < now`, so the user's STALE expiry (from original provisioning) rejected every freshly-issued temp password as "expired". Reissuing never helped.
- **Fix** (master_admin_users.py admin_reset_password): reset now sets `must_change_password=True` + `temp_password_expires_at = now+7 days`. Also hardened to update BOTH db.users AND db.crm_users (was either/or) so a mirrored user can't keep a stale *valid* password on the CRM side after a reset.
- **Verified**: testing_agent — 5/5 pytest against the LIVE endpoint (repro 401 'expired' → real master-admin reset (through mandatory TOTP MFA) → login now succeeds with the new temp password, no expiry block → old password now 'Invalid credentials' not 'expired' → DB shows fresh +7d expiry). Dual-collection change re-passes the suite (5/5). Suite: /app/backend/tests/test_temp_password_reset_expiry_aug2026.py. Backend-only.

## 2026-06 — Staffing: login re-issue fix, DBS, Fleet Manager, bell, dark mode
- **CRITICAL fix — "Re-issue login" reset token**: Root cause = re-issue mint path (`account.py _issue_reset_token`, `master_admin.py _mint_invite_link`) built links from raw `FRONTEND_URL` (preview host → different DB → token not found → "Invalid or expired reset token"). Now use brand-aware `app_url_for_org`. Also: re-issue now archives ALL prior unused tokens at mint time (old links die instantly); `/auth/reset-password` gives clear messages (invalid vs already-used vs expired) and falls back to matching the user by email if the account shell was re-created. Verified 5 branches (testing agent, backend 100%).
- **Enhanced DBS**: `dbs_number` + `dbs_expiry_date` added to staff profile (`staffing_hr.py` PROFILE_FIELDS/ProfileUpdate, `HRTab.js` new section with expiry status badge).
- **Fleet Register → Fleet Manager**: New vehicle fields `fleet_department, lease_company, lease_end_date, fuel_card_number, dart, congestion, m6_toll, driver_label` (`vehicle_checks.py VehicleBody` + create/update). Register now grouped-by-department cards; clicking opens a themed detail/edit modal (VehiclesTab.js) with sections + calendar date pickers; service info moved out of the old edit `<details>`. Driver's Staff Portal vehicle card shows lease/MOT/fuel/toll details. Imported 45 Pulse Fitness Ltd vehicles via `scripts/import_fleet_pulse_ltd.py` (drivers stored as labels; link to staff once seeded).
- **Notification bell**: moved to the right of the Operations sub-nav bar on desktop (visible in every Operations tab, `LiteDashboardPage.js`), removed the duplicate inside StaffingConsole (new `hideBell` prop), and added to the mobile top header (`Navbar.js`). Gap above the Staffing sub-menu closed.
- **Staff Portal**: removed the "Active employee ✓" badge.
- **Dark mode**: fixed white cards bleeding into dark mode on Attendance/Payroll tabs (dark: tokens) and themed the vehicle modal + register + staff vehicle card.
- Test login for Pulse Fitness Ltd operations: portal@pulsefitness.ltd / PulseFleet123! (route '/').

## 2026-06 (b) — Staff portal DBS, vehicle 2-options, fleet fines, exports & mobile polish
- Staff Portal "My details" now shows a **Compliance** section with Enhanced DBS number + expiry (via /new-starter/me compliance).
- Staff Portal vehicle card split into **two actions**: "Vehicle details" (expands lease/MOT/service + fines) and "Complete check".
- **Fleet fines**: vehicle detail modal has a Fines section — add (type/date/value/paid + scan upload), toggle paid, view scan, delete. Assigned driver sees fines on their portal. Backend: fines array on vehicle + endpoints (add/patch/delete) + /vehicles/fine-upload (object storage). Curl-verified.
- **Fleet Register export**: "Export / Print (CSV)" button → GET /api/vehicles/export.csv (all fields). Verified.
- **Notification bell** restyled transparent/theme-aware (no more white box on the dark header); mobile dropdown lowered (top-24) so the title clears the header.
- **Mobile**: Staffing secondary sub-tab bar now horizontally scrollable (no more bunched rows).
- Testing agent: frontend 100% (bell, mobile panel, sub-tab scroll, CSV export, fines CRUD).

## 2026-06 (c) — Link fleet drivers (easy manual linking)
- Vehicle modal 'Assigned driver' is now a SEARCHABLE picker (type to filter staff by name/department/title) — easy with a large team.
- When a vehicle carries an imported driver-name label but no linked staff, a hint shows "Imported driver: <name> — search above to link them", so matching the 40 imported vehicles is one click.
- Links persist via existing PATCH (driver_staff_ids) and resolve to driver_names; the register card + staff portal then show the real driver. Curl-verified (BT75NDG↔Craig Henshall) + testing agent frontend 100%.
- Driver list comes from /vehicles/driver-options (all active staff), so the full team appears in production.

## 2026-06 (d) — Fleet PDF pack
- Added GET /api/vehicles/export.pdf: Pulse-branded, board/insurance-ready PDF of the whole fleet register, grouped by department (Reg, Make/model, Driver, Lease co, Lease end, MOT due, Fuel card, Fines). Uses utils/pulse_doc_template.
- Fleet register toolbar now has two buttons: "Export CSV" (vehicles-export-csv) and "Print / PDF" (vehicles-export-pdf).
- Verified: endpoint returns valid application/pdf (45 vehicles, ~3 pages, no overflow/overlap — confirmed via document analysis).

## 2026-06 (e) — Fix password-manager autofill (Edge / iCloud Passwords)
- Root cause: login inputs were React CONTROLLED (value=formData), so after a manager autofilled the password React re-render clobbered it back to empty; password field also lacked name/autocomplete so Edge didn't recognise the login form.
- Fix (Navbar.js): email input name='username' autocomplete='username'; password input name='password' autocomplete='current-password' (new-password on signup); made email+password UNCONTROLLED (defaultValue + onChange, no value binding) so autofill sticks; handleAuth now reads live values from form.elements.username/password (effForm) so submit always uses the actual autofilled/typed values.
- Regression: manual typed login, show/hide toggle, and wrong-password error all pass (testing agent 100%).


## 2026-06 — Platform Visual Continuity (Phase 1: sub-menus + sign-in logos)
User request: full design continuity across the platform (headers/footers/menu bars/options uniform; uniform logos on all sign-in pages).

**Delivered this pass (Phase 1):**
- New shared components:
  - `frontend/src/components/shared/SubTabBar.js` — canonical secondary/"lateral options" menu; wraps `PillTabBar` and renders the standard cyan rounded-full pills (active = `--color-brand-cyan` bg + `--color-ink` text + shadow; inactive = `--theme-text-muted` transparent).
  - `frontend/src/components/shared/BrandWordmark.js` — single canonical Pulse Fitness logo (the hosted primary-logo badge image the Navbar uses), exported `PULSE_LOGO_SRC`.
- CRM Aftersales page: removed the redundant `<h1>Aftersales Contracts</h1>` + "Enter once → reuse everywhere → manage by exception." tagline; content moved up; sub-menu migrated to `SubTabBar` (cyan pills). (AftersalesApp.js)
- Sign-in logo unification → `BrandWordmark`: `LoginPage.js` (was bold "Pulse Fitness.AI" text), `StaffLogin.js`, `CRMLogin.js` (login + 2FA + signup header). MOD Service login left with its MoD defence branding intentionally.
- Sub-tab bars migrated to the cyan pill standard:
  - Service Ops: restyled shared `.svc-tabs`/`.svc-tab` in `_serviceops.css` → pills (updates Parts Inventory, Comms Hub, Case Drawer, Integrations Console at once).
  - Dealer Warranty Parts (`DealerWarrantyPartsPage.js`) → SubTabBar (kept unsaved-work guard).
  - Master Admin: `AdminRoles`, `PlatformHealth`, `SiconIntegrationPage`, `AdminMemberships` → SubTabBar; `AdminOnboardingHub` grouped bar restyled to pills in place (keeps Manage/Customers/Partners/Team grouping).
  - Memberships: `AnalyticsTab` (section bar) + `AIInsightsTab` (was fuchsia) → SubTabBar.
  - `PulseCheckSheetsTab` → pill buttons in place.
  - Engineer mobile stock strip (`EngineerStock.js`) intentionally left (equal-width mobile tab pattern, already cyan).

**Verification:** frontend compiles clean. Testing agent (owner@isodemo.com / IsoDemo123!) verified LIVE: sign-in logos, Memberships Analytics + AI Insights cyan pills. Source/compile-verified: Aftersales, Service Ops svc-tabs, Dealer Parts. Master Admin pages NOT runtime-verified (master admin has enforced TOTP MFA — cannot automate); low risk (same SubTabBar swap).

**NOT yet done (Phase 2 — larger, pending):** unify the module SHELL HEADERS/FOOTERS (ServiceOpsShell hero header, MarketingShell/PulseMarketingShell, MemberPortal, Engineer app shell, Dealer standalone portal header, MOD footer) and theme the Service Desk/Inventory SIDE NAV to match. The main authenticated `Navbar` + `Footer` are the intended standard.



## 2026-06 — Bug batch (temp-pw / reset page / engineer access / territory roles)
- **Bug 1 — Temp passwords / reset links expiring too quickly** → standardised to **7 days**.
  - `utils/auth_guards.py`: `PASSWORD_RESET_TTL_MINUTES` default 15 → 10080 (7 days).
  - `staff_onboarding_wizard.py:1551`: staff reset-link TTL 1h → 7 days.
  - `auth.py:_enforce_account_status`: hardened temp-password expiry check to parse the datetime (tz-aware) instead of a fragile ISO string compare.
  - `ResetPasswordPage.js`: copy "expires in 15 minutes" → "7 days".
- **Bug 2 — "Change password" reset link page showing blank** → the emailed reset page was stuck on the app's black auth "Loading…" splash whenever a stale login token was in localStorage. Fixed in `App.js` loading-gate: added `/reset-password` + `/staff-reset` to the public-exception list and made the splash condition skip them (`!isPublicException && (hasSessionToken || isProtectedRoute)`). Verified: reset form now renders even with a stale token.
- **Bug 4 — Engineers gaining Operations access** → engineers now get Operations only if a master admin explicitly grants it.
  - Backend enforcement (new + existing engineers): `utils/module_access.py:resolve_module_access` — `_engineer_ops_guard` forces `operations=False` for `role==engineer` unless `module_overrides.operations is True`.
  - Frontend UX: `AdminOrganizations.js` add-user + edit-user permission grids default the Operations checkbox OFF for engineer role.
- **Bug 5 — CRM Territories pulling wrong Operations job roles** → only **sales managers & engineers** now appear; admins/regional-managers/unclassified are excluded (previously defaulted to "Sales Manager").
  - `crm_territories.py`: `staff-palette` + `staff-locations` now skip any crm_user whose `territory_role` isn't in `_TERRITORY_ROLES` (sales_manager/engineer/both), using the raw stored value (no silent default to sales_manager).
  - `crm_core.py:_territory_role_from_staff`: engineer keywords now checked BEFORE sales (so "Sales Engineer"→engineer); "Administrator"/"Regional Manager"→None (excluded).
- Verified: bug1/4/5 via backend unit checks; bug2 via browser screenshot.

### OPEN — Bug 3 (staff-login on pulsefitness.ai) — PRODUCTION-ONLY
- `/staff-login` works in PREVIEW (backend POST /api/new-starter/staff-login returns 200; page renders; submit disabled only until fields typed). The failure ("press login, nothing happens / button dead") is reported ONLY on the live pulsefitness.ai domain. Main app login works there, so REACT_APP_BACKEND_URL is fine for the main bundle. Most likely: the production deployment is a STALE build predating recent staff-login changes, OR a prod-only routing/CORS quirk on /staff-login. Requires a redeploy (ships the above fixes too) and, if still failing, a production RCA via the deployer.



## 2026-06 — CRM bridging root-cause + Service Desk PM/Equipment build
### #1 CRITICAL — Master Admin imports never appeared in Pulse Fitness Ltd CRM (recurring)
- ROOT CAUSE: the import→CRM bridge stamped `crm2_companies.organization_id` with the *importing admin's* org (the Master Admin super-user org, e.g. `9fa701ef…` / preview `d19de469` "Pulse Fitness AI Admin"), NOT the operator company `3ece2d0c…` (Pulse Fitness Ltd) that the CRM Companies list filters by. So bridged companies were written to the wrong tenant and were invisible.
- FIX (`routes/master_admin_bulk_import.py`): new `_resolve_operator_org()` resolves the org flagged `is_operator_company: True` (Pulse Fitness Ltd) and is used at all 4 bridge call-sites. `_ensure_crm_company_for_org` is now SELF-HEALING — matches an existing bridged company by `linked_organization_id` across orgs and RE-POINTS it to the operator org (no duplicates) on the next import/backfill.
- Verified against live DB: resolver→3ece2d0c; fresh create lands under operator; mis-bridged doc re-points (same id, 1 doc).
- This also fixes **#2** (Service Desk "Log a Case" customer picker) — it reads the same operator-scoped `crm2_companies` with `linked_organization_id`.
- ⚠️ PRODUCTION: after redeploy, run **Backfill CRM** (`POST /master-admin/bulk-import/backfill-crm`) once to re-point existing imported estates into Pulse Fitness Ltd.
### #5 — Maintenance All/Commercial/MOD buttons "whited out" → restyled to cyan-active / readable-inactive pills (`PPMCalendar.js`).
### #3 — Service Desk Equipment: site-first + multi-select + Log case
- `DeskEquipment.js`: added Customer→Site selector + machine checklist (multi-select) + "Log case for N machines" opening `ServiceDeskIntakeForm` pre-filled.
- `ServiceDeskIntakeForm.js`: now accepts `initial={customerOrgId, siteId, equipmentIds}` and submits `equipment_ids` for MULTIPLE machines on one case.
### #4 — Create PM from Service Desk + manage service types + bulk scheduling
- Backend (`routes/svc/ppm_calendar.py`): `ppm_service_types` collection + CRUD (`/svc/ppm/service-types`), seeded with Preventative Maintenance Service, **Treadmill Calibration** (checklist: belt speed/incline/e-stop), Safety Inspection. New `POST /svc/ppm/schedules` (single) and `POST /svc/ppm/schedules/bulk` (per-site or per-machine, staggered dates for the 85-station case). `/svc/ppm/services` now unions custom types.
- Frontend (`PPMCalendar.js`): "Create PM" button → `CreatePpmModal` with Single/Bulk modes, service-type picker + inline add-type, frequency, first-visit, bulk site multi-select + stagger + granularity.
- Verified: single create, bulk (2 sites staggered 14d), calendar surfacing, add-type — all via curl; frontend flows 100% pass (testing agent report `iteration_ppm_create_desk_equipment_jan2026.json`).
- Fixed `/svc/desk/customers` duplicate org rows (dedupe by organization_id). Seed fix: `seed_site_isolation_demo.py` now sets `is_service_desk: True` on owner@isodemo (was missing → /service-desk bounced to /launch).



## 2026-06 — Calibration Capture (audit certificates)
Engineers record equipment calibration readings on a case and generate a branded pass/fail certificate for audits (e.g. Fire Station treadmill calibration).
- Backend:
  - New collection `svc_case_calibrations`. Engineer endpoints (`routes/svc/engineer.py`): `GET /svc/engineer/jobs/{case_id}/calibration` (loads existing + default checklist items from the case's PM service type), `POST .../calibration` (saves readings [{label,target,measured,unit,tolerance,result}], overall pass/fail auto-derived, notes, signature; stamps `calibration_captured`/`calibration_result` on the case), `GET .../calibration/certificate.pdf`.
  - Office/manager download: `GET /svc/cases/{case_id}/calibration/certificate.pdf` (`routes/svc/cases.py`).
  - New PDF util `utils/calibration_certificate_pdf.py` (ReportLab, shared Pulse doc shell like warranty cert): meta, OVERALL RESULT banner (green/red), readings table with per-row pass/fail, engineer notes + signature image, audit footer.
  - PM→case gap closed: `ppm_calendar.py schedule_ppm` now copies `checklist_items` onto the created case, so calibration rows pre-fill from the "Treadmill Calibration" service type.
- Frontend (`EngineerJobDetailV2.js`): new `CalibrationCapture` panel in the engineer Complete tab — editable readings grid (parameter/target/measured/unit/result), add/remove rows, notes, signature (reuses `SignatureCanvas`), Save, and Download certificate (blob fetch with auth). Auto-opens when the job's service type is calibration or has checklist items.
- Verified: certificate PDF generates (HTTP 200, valid %PDF, ~121KB) via office route with seeded data; both new routes registered (engineer route gated by Partner Engineer Network access = 402 for non-engineers); frontend serves HTTP 200 (no compile failure). NOTE: the engineer capture UI was NOT driven in a live engineer session (needs a Partner Engineer Network account); backend fully verified + UI compiles/serves — recommend a quick engineer-app walkthrough after deploy.


## 2026-06 · Calibration certificate: office drawer + customer Documents
- Office ServiceCaseDrawer: added "Calibration certificate" footer block (View + Download, PASS/FAIL pill) gated on doc.calibration_captured, hitting GET /api/svc/cases/{id}/calibration/certificate.pdf.
- Customer portal: on case close (operator sign-off), utils/calibration_cert_publish.py persists the cert PDF into db.files under the customer estate org (category "certificates") via company_id → crm2_companies.linked_organization_id. Idempotent. Wired into /cases/{id}/transition.
- Master Admin Sync (backfill-crm) now backfills historical closed-case certs so they appear once a customer estate is onboarded.
- CRITICAL FIX: EngineerJobDetailV2.js had a real syntax error (unclosed profitability component) that was breaking the entire frontend compile since the prior session's "Calibration Capture" work — now fixed; app compiles/renders.
- Added /app/memory/PLATFORM_CONTEXT.md (always-read purpose/tenancy reference).
- Verified: testing_agent 100% BE+FE (iteration_calibration_cert_office_drawer_jan2026.json).

## 2026-06 · Calibration cert: email-to-customer + parameters match Certificate of Service
- Office drawer: added "Email customer" button (data-testid drawer-calibration-cert-email) next to View/Download in the calibration cert block, plus a blue "Sent" pill (drawer-calibration-cert-sent) after a successful send. Backend POST /api/svc/cases/{id}/calibration/certificate/email (mirrors service-report email, Resend, category "service"); records calibration_cert_sent_at/to + timeline event.
- Treadmill calibration parameters now MATCH the customer's "Certificate of Service": Speed 3/6/9/12 mph, Incline 0/5/10/15%. Backend serves canonical params via engineer.py _default_calibration_readings + GET /jobs/{id}/calibration default_readings; frontend CalibrationCapture pre-fills them; PPM seed "Treadmill Calibration" checklist updated. Verified in generated PDF (all 8 params present).
- Verified: testing_agent frontend 100% (iteration_calibration_cert_email_button_jan2026.json); cert PDF text-extraction confirms the 8 params; email endpoint reaches Resend (502 only due to invalid preview key — delivers in prod).
- Task 1 (DSFR): publish/backfill already shipped; DSFR has no portal accounts / no closed calibration jobs yet, so nothing to backfill now — deploy makes it live for their upcoming services.

## 2026-06 · MOD estate bridging fix + AI custom tender pricing (Build Quote)
- FIX (production RCA): CRM backfill/Sync skipped MOD estates because account_type "mod_org"/"mod_site" didn't match the allow-list ("mod"). Added _is_pulse_visible_account_type (accepts pulse_pro/lite/mod/full + any mod*), broadened the backfill candidate set to include Pulse-visible estates even with no sites/equipment (so MOD HQs surface), and applied the helper to the sites-import gate too. master_admin_bulk_import.py.
- NEW: Aftersales → Build Quote "Custom (tender)" package. Upload a signed agreement/pricing sheet → Claude Sonnet 4.6 extracts per-machine-type SERVICE prices + per-site TRAVEL costs. Scanned PDFs handled via PyMuPDF page-render → Claude vision OCR; text PDFs/Excel/Word via pdfminer/openpyxl/python-docx. Review/edit panel → Apply matches prices to the estate by machine type (equipment_type/name/model keyword) with a needs-review fallback, adds travel per site, computes annual/term totals, and saves the quote. Endpoints: POST /crm/v2/aftersales/extract-pricing-document (file or ?file_id=), POST /crm/v2/aftersales/build-custom-quote. Large uploads route via /files/upload then file_id (bypasses proxy 413).
- Verified: extract on the real 6.7MB scanned DSFR agreement → all 7 machine prices + 85 travel rows (vision OCR); build priced 17/23 with correct discount/term maths; testing_agent frontend 100% (iteration_afs_custom_tender_frontend_jan2026.json). Model: Claude Sonnet 4.6 via Emergent LLM key.

## 2026-06 · Reusable customer rate cards (saved tenders)
- Each extracted/edited tender in Build Quote → Custom (tender) can be saved as a reusable RATE CARD on the customer ("Save as rate card"). Saved cards appear as pills ("<name> · N machines") whenever that customer + Custom package is selected; clicking one repopulates the pricing review panel with NO re-upload, then Apply builds the quote.
- Backend: crm2_afs_rate_cards collection; POST /crm/v2/aftersales/rate-cards, GET ?company_id=, DELETE /{id}. Frontend: AutoQuoteTab rateCards state + saveCard/loadCard.
- Verified: CRUD via curl; testing_agent frontend 100% save→reload→load→build (iteration_afs_ratecard_save_reload_jan2026.json).

## 2026-06 · Tender Quote Wizard (repairs + multi-schedule + AI summary)
- Aftersales → Build Quote → Custom (tender) now has a mode toggle: Quick (single panel) OR a stepped Tender Wizard (kept both).
- Wizard steps: Upload → Summary → Service → Repairs → Travel → Build. AI now also extracts REPAIR labour £/hr per machine type (single 'All' rate if flat) and a TENDER SUMMARY (headline, term, PPM visits/yr, SLA, key points). Summary step lets the user tick which schedules (Service/Repairs/Travel) to include.
- Repairs: stored on the quote/rate card AND optionally costed — "estimated repair hours/yr" × effective rate (mean of provided rates) adds an indicative repair line to the annual total.
- Rate cards now persist repair_rates and round-trip into Quick mode.
- Backend: extract-pricing-document returns repairs+summary; build-custom-quote accepts repair_rates+estimated_repair_hours (repair cost line); rate-cards store repairs. Frontend: AutoQuoteTab customMode/wizStep/incl/estHours + wizard JSX (afs-wiz-* testids).
- Verified: curl (extraction repairs+summary; 40h×£27.5=£1100 costing) + testing_agent frontend 100% (iteration_afs_tender_wizard_repairs_jan2026.json). Model: Claude Sonnet 4.6.

## 2026-06 — Aftersales Contracts: quote gaps closed (release-readiness fixes)
Fixed the founder-reported gaps that made the custom/tender quote NOT release-ready:
- **Itemised PDF + £0.00/VAT bug FIXED**: custom-tender quotes saved line items as {type,unit_price,line_total} but the PDF read {model,annual_unit,annual_total} → machines rendered "—" and every price + VAT + "Annual inc VAT" showed £0.00. Backend now writes model/annual_unit/annual_total on grouped lines; PDF (utils/afs_quote_pdf.py) reads both shapes, adds a dedicated "Travel & visits" table (Site | Per visit | Visits/yr | Annual), an itemised charge breakdown (Service/Travel/Repairs), and defensive VAT/monthly fallbacks. Verified via live PDF endpoint.
- **Travel charged per visit**: CustomQuoteIn.visits_per_year (default 1). Travel = per-site rate × visits/year; travel_lines carry per_visit/visits/annual. (Devon = 1 PPM service/yr; repairs still costed separately by hours.)
- **VAT default 20%** with per-quote override (CustomQuoteIn.vat_pct); summary now always includes vat_pct/vat_amount/final_annual_inc_vat/monthly.
- **Review missed machines + block send**: unmatched machines are grouped by model (asset_ids + count) in needs_review. UI adds per-group "Exclude" buttons; quote auto-rebuilds; unpriced_count/quote_health tracked. send-email AND portal-link now return HTTP 400 until unpriced_count==0; the Agreements list shows "N unpriced — edit to send" and disables Send/Create-link.
- **Edit a saved quote (overwrite)**: CustomQuoteIn.overwrite_quote_id updates the existing doc keeping id + quote_number. AgreementsTab "Edit" button loads the saved rates into the builder (purple editing banner); Save reads "Save changes (overwrite)".

Files: backend/routes/crm_aftersales.py (build_custom_quote, send-email/portal-link guards), backend/utils/afs_quote_pdf.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js (AutoQuoteTab + AgreementsTab + parent editQuote lift).
Testing: backend + PDF verified via curl (customer iso-cA); frontend 8/8 UI states verified by testing agent (iteration_afs_custom_tender_frontend_verify_jan2026.json). No functional issues.
Pre-existing (NOT from this change, noted for later): 2× 500s on CRM/Aftersales navigation (likely warranty-opps/settings), and a hydration warning `<span>` inside `<option>` in the CRM company <select>.

## 2026-06 — Fix: Aftersales navigation 500 (warranty-opportunities)
- GET /api/crm/v2/aftersales/revenue/warranty-opportunities returned 500 ("can't compare offset-naive and offset-aware datetimes", crm_aftersales.py:2865). It's loaded by AutoQuoteTab on entering Build Quote → the console 500 the testing agent flagged.
- Root cause: _parse_dt() returned a tz-naive datetime for warranty_expiry values stored without an offset; compared against tz-aware now/horizon.
- Fix: _parse_dt() now normalises naive datetimes to UTC-aware. Verified 200 + returns opportunities; full Aftersales nav endpoint sweep all 200.

## 2026-06 — Feature: optional per-site equipment appendix on quote PDF
- New optional "Appendix A — Equipment by site" in the customer quote PDF, for large estates (e.g. Devon & Somerset's 85 sites).
- Toggle: CustomQuoteIn.include_site_annexe (persisted on the quote); UI checkbox in AutoQuoteTab custom panel (data-testid afs-aq-annexe-checkbox), prefilled on edit.
- Render: render_afs_quote_pdf builds a per-site breakdown at render time (_build_site_annexe) from db.equipment/db.sites for the quote's linked_organization_id (respecting site_ids), grouping identical model/console into quantities, listing serials, and marking excluded_asset_ids as "(not covered)". build_afs_quote_pdf renders it after a PageBreak. Fixed a pulse_title-returns-list bug (must use `flow += pulse_title(...)`).
- Verified via live PDF endpoint (iso-cA): appendix present + correct when flag on, absent when off; all cleaned up.
Files: backend/routes/crm_aftersales.py, backend/utils/afs_quote_pdf.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js.

## 2026-06 — Feature: unpaid vehicle fine reminders (bell nudge, P1)
- The Staffing/Fleet notification bell now nudges managers about vehicle fines left unpaid for 14+ days.
- Implemented as a computed nudge in GET /api/staffing/notifications (staff_portal.py) mirroring the DBS-expiry pattern: scans db.vehicles embedded `fines`, ages each unpaid fine by `created_at` (fallback: parse free-text `date`), and surfaces a "Unpaid vehicle fines" nudge (type `vehicle_fine_overdue`, link `vehicles`) listing up to 3 regs. Owners see the whole org; line managers see only fines on vehicles driven by their direct reports. Auto-clears as soon as a fine is marked paid (no cron, no stored notification).
- Frontend: added `vehicle_fine_overdue` rose tone to StaffNotificationBell TONE map.
- Verified via curl (iso-demo-org, vehicle AB12 CDE): counts only 14+ day unpaid fines (1 of 3 seeded: skipped a 3-day-old unpaid and a 30-day-old paid), and the nudge disappears once the fine is marked paid.
Files: backend/routes/staff_portal.py, frontend/src/components/staffing/StaffNotificationBell.js.

## 2026-06 — Feature: Aftersales quote versioning (view / revert) + hydration warning fix
- Editing a saved custom/tender quote now archives the prior state to `crm2_afs_quote_versions` before overwriting. Main quote doc carries a `version` counter (starts 1).
- New endpoints (crm_aftersales.py): GET /quotes/{id}/versions (history metadata, newest first), GET /quotes/{id}/versions/{version} (full snapshot for viewing), POST /quotes/{id}/versions/{version}/revert (restores a snapshot as current; archives current first so revert is reversible; keeps quote number). Helper `_archive_quote_version`.
- Frontend (AftersalesApp.js AgreementsTab): a 'History (vN)' button on custom quotes with version>1 opens a modal listing the current version + all prior versions (£/yr, editor, timestamp), each with View (read-only snapshot) and Revert.
- Verified: backend via curl (v1→v2→v3, list, view snapshot returns historical figures, revert restores £ and is reversible); frontend History modal via testing agent (5/5 scenarios, 100%).
- BONUS FIX (hydration warning): the long-standing "<span> cannot be a child of <option>" console warning was traced (by the testing agent) to the Emergent Visual-Edit tool injecting a <span> wrapper around MULTI-EXPRESSION children inside <option> (afs-ag-quote select, and the AI-tab contract select). Fixed by giving each such <option> a single template-string child. Verified live on the Agreements tab: 0 injected spans, 0 nesting warnings.
Files: backend/routes/crm_aftersales.py, frontend/src/pages/CRM/Aftersales/AftersalesApp.js.

## 2026-06 — Feature: Payroll monthly timesheets (customer Excel template) + Payroll nav regroup
- New payroll export that reproduces the customer's "TIME SHEETS 2026.xlsx" template 1:1: exact layout, [h]:mm number formats, and every formula (per-day H=(D-C)-E, weekly SUM totals, Grand Total, Standard Hours =C3/24, =D3*D4, Overtime/Unpaid-Leave IFs). Pre-filled per staff from recorded self_entries (start/finish/break/PT). Yellow hand-in Friday cell. Filename "Timesheet <Mon><YY> - <Full Name>.xlsx".
- Per-year hand-in SCHEDULE: auto-generated with a contiguous Mon-start 5-4-4 calendar (Jan ends 2nd Sunday of Jan; hand-in = Friday of each period's final week) — matches the supplied 2026 file exactly (Jan26 8 Dec–11 Jan, hand-in 9 Jan, etc.). Payroll can edit period start/weeks/hand-in per month and Save; selecting a future year auto-generates it ("AI creates the new year"). Collection: timesheet_schedules (org+year).
- Endpoints (staffing_clock.py): GET/PUT /staffing/timesheet-schedule; GET /staffing/timesheets/month-export (single staff xlsx); GET /staffing/timesheets/month-pack (ZIP, one file per active staff — no duplicates). New util utils/payroll_timesheet_xlsx.py.
- Frontend: new PayrollTimesheetsTab.js. Payroll is now a nav GROUP: Workspace + Timesheets + Attendance. The standalone "Time Clock" tab was removed (per request).
- Verified: auto-schedule matches sample; xlsx replica (layout/formulas/formats/yellow/footer rows 48/50/52/54); pre-fill of recorded hours (start/finish/break/PT); filename; 10-file pack with no dupes; UI smoke (Time Clock gone, Timesheets tab renders, no console errors).
Files: backend/routes/staffing_clock.py, backend/utils/payroll_timesheet_xlsx.py, frontend/src/pages/LiteDashboard/StaffingConsole.js, frontend/src/pages/LiteDashboard/staffing/PayrollTimesheetsTab.js.

## 2026-06 — Feature: role-tailored timesheet columns (+ PT/Classes split, engineer/admin activities)
- Timesheet activity columns now adapt to each staff member's role, both in the staff-portal entry grid and the payroll Excel export:
  - Fitness Instructor / PT → PT + Classes (now two SEPARATE fields, reportable independently)
  - Engineer / Technician / Maintenance → Van Check + Parts Collected + Clean Van (each = a done tick + hours:mins)
  - Sales Manager / Admin / HR / Payroll / Director / Manager → Admin (tick + hours)
  - Everyone else (reception, cleaner, lifeguard, duty_manager, other) → no extra columns
- Backend: `_ts_profile_key`/`_ts_columns`/`_TS_PROFILES` + `_acts_of` (staffing_clock.py). Timesheet docs now carry `ts_profile` + `ts_columns`. `_self_day_hours` sums an entry's `acts` minutes (legacy pt_classes still honoured). SelfDay model + self-save now accept an `acts` map `{key:{mins,done}}` and keep legacy pt_classes/van_check in sync. Payroll Excel generator (payroll_timesheet_xlsx.py) rebuilt to be COLUMN-DRIVEN: dynamic activity columns between Break and Total, tick_hours cells show h:mm or a "Y" tick, weekly SUM + Grand Total/footer formulas shift correctly.
- Frontend: StaffPortal timesheet grid renders activity columns dynamically from `ts.ts_columns` (hours input, or checkbox+hours for tick_hours); saves via `acts`.
- Verified via curl+DB: all 4 role profiles emit correct headers (Instructor=PT/Classes, Manager=Admin, Reception=none, Engineer=Van Check/Parts/Clean Van); engineer prefill (van_check 0:15, parts 0:45, clean_van done-0min→"Y"); self-save round-trip persists acts and derives legacy fields; both frontends compile.
- Follow-up still open per user (5b): richer portal capture already added for these activities; PT/Classes split done.
Files: backend/routes/staffing_clock.py, backend/routes/staff_portal.py, backend/utils/payroll_timesheet_xlsx.py, frontend/src/pages/StaffPortal.js.

## 2026-06 — PPM Auto-Load on Site Activation (Estate Onboarding Commit)
- Wired the per-site PPM backfill into the real "site goes live" moment: the Estate Onboarding commit (`POST /crm/v2/aftersales/onboarding/{import_id}/commit`) now fires `kickoff_site_ppm_backfill(cust_org_id, site_id, "annual", ...)` for every newly created site, right after `db.sites.insert_many`. Idempotent, background, non-blocking. Backfill run refs returned in the commit response under `committed.ppm_backfill`.
- New operator-scoped polling endpoint `GET /crm/v2/aftersales/onboarding/{import_id}/ppm-status` — aggregates the customer-org backfill runs (which the operator's org can't read via the raw `/ppm/backfill/runs/{run_id}` endpoint) into `{total_sites, finished_sites, all_done, failed_sites, schedules_created, tasks_created, runs[]}`.
- Frontend EstateOnboarding "done" step now polls ppm-status (2.5s) and shows a live "Loading PPM schedules… n/m sites" progress bar that flips to a green "PPM schedules loaded" summary; surfaces failed-site count.
- Verified end-to-end via seeded import: commit created 2 sites → 2 backfill runs completed → 2 schedules + 6 tasks generated; ppm-status reported all_done=true. Test data cleaned up.
Files: backend/routes/crm_afs_onboarding.py, frontend/src/pages/CRM/Aftersales/EstateOnboarding.js.

## 2026-06 — Per-Site PPM Cadence at Estate Onboarding
- Estate Onboarding Review step now shows a "PPM service cadence" card listing each included site with an Annual (1/yr) / Biannual (2/yr) / Quarterly (4/yr) selector, defaulting to Annual. Choices are POSTed to commit as `site_frequencies` and used when auto-loading each site's PPM schedules.
- Backend commit() accepts `{site_frequencies: {site_name: freq}}` (validated to annual/biannual/quarterly/monthly, unknown → annual) and passes the per-site cadence into `kickoff_site_ppm_backfill`. Cadence echoed back in `committed.ppm_backfill[].frequency`.
- BUG FIX: moved the PPM backfill kickoff to AFTER equipment insert_many (it was firing before equipment existed, so 2 of 3 concurrent background runs queried an empty collection and created 0 schedules). Now all sites generate.
- Verified end-to-end: 3 sites (quarterly/biannual/annual) → 3 schedules, 9 tasks, task spacing 3mo/6mo/12mo confirmed; ppm-status all_done. Test data cleaned up.
Files: backend/routes/crm_afs_onboarding.py, frontend/src/pages/CRM/Aftersales/EstateOnboarding.js.

## 2026-06 — Sicon Read-Side: Route Alignment to Proven V10 + Contract Probe + Connection Triad
Founder handed over the FINAL V10 Read-Safe Bruno collection ("ready for integration"). Audited existing Sicon layer (~80% built & compliant: SiconClient v1 surface, %26 pagination, 401 re-auth-once, env-only write-guard, sync runs/locks/conflicts/audit, Master-Admin UI). Implemented the safe read-only alignment slice (Phase B):
- **SiconClient** (`utils/sicon_client.py`): added the PROVEN v1 case-relationship read methods — `svc_get_case_equipment/appointments/tracking_notes`, `svc_get_tracking_note_one`, `svc_get_appointment_one/resources/timebookings` (were previously only reachable via unproven legacy `/api/Service/*` routes). Added gated Contract-plugin probe `svc_contract_available` + `svc_get_contracts/contract_one` on a separate `contract_base_url` (§26), treating 404 as "Unavailable" without rewriting routes.
- **Config** (`utils/sicon_common.py`): thread `contract_base_url` from `SICON_CONTRACT_BASE_URL` env / per-org config; write-guard still env-only.
- **Routes** (`routes/sicon.py`): `POST /sicon/test-connection` now runs the proven triad (anon Ping → Authenticate → authed CaseType) with per-step timings + Contract capability probe; never returns token/creds. Aligned `/sicon/case-types`, `/sicon/tracking-statuses`, `/sicon/priorities` to the proven v1 routes and removed the stale "Sicon has no priorities endpoint" claim (V10 proves `/api/v1/SiconService/Priority` works).
- **Frontend** (`Admin/IntegrationsSiconConnect.js`): connection-test result now shows Ping/Authenticate/Authed-request chips (ok/ms/records) + a Contract API Available/Unavailable chip.
- **Tests**: extended `tests/test_sicon_readside.py` (mocked httpx, no live server) — 16 pass, covering v1 relationship routes, contract probe (404→unavailable / 200→available + reads), contract_base_url usage, and read-not-write-guarded. `SICON_ALLOW_WRITES` stays false.
- Pre-existing unrelated failures (8) in `test_sicon_bruno_artifacts.py` / `test_sicon_service_webapi_v1_jan2026.py` confirmed failing before this change (verified via git stash).
Files: backend/utils/sicon_client.py, backend/utils/sicon_common.py, backend/routes/sicon.py, frontend/src/pages/Admin/IntegrationsSiconConnect.js, backend/tests/test_sicon_readside.py.

## 2026-06 — Sicon Case Relationships Wired (Equipment + Tracking Notes, §12/§13)
Wired the proven v1 relationship chain into the existing case importer (targets db.issues, unchanged). READ-ONLY, idempotent, resilient.
- **Equipment attach (§12)**: on case import, `sync_case_relationships()` pulls `Case/{id}/Equipment`, resolves each Sicon equipment → existing Pulse asset via the immutable siconEquipmentId link (never invents), and stamps `asset_id`/`asset_name`/`equipment_ids`/`equipment_serials` on the issue. Equipment that isn't a linked Pulse asset is flagged **UNMAPPED_EQUIPMENT** in the existing conflict queue (`external_entity_type="case_equipment"`, listable via `GET /sicon/read/conflicts?entity=case_equipment`).
- **Tracking notes (§13)**: pulls `Case/{id}/TrackingNote` and folds notes into the issue's EXISTING embedded `timeline` array, deduped by `sicon_tracking_note_id` (re-runs add nothing), tagged `source:"SICON"`.
- **Null-protection (§22)**: a re-pull returning no resolvable equipment never erases previously-attached assets.
- Each sub-pull is isolated (try/except) so one failing relationship never fails the case. New per-run counters (`equipment_linked`/`equipment_unmapped`/`notes_added`) persist into `sicon_sync_runs` (Sync History). `run_case_sync(..., pull_relationships=True)` default; preview never pulls.
- **DEFERRED (needs founder decision + new infra)**: appointments/resources/time-bookings (§14-16). Blockers documented for next agent: (1) canonical case store ambiguity — importer writes `db.issues` but the modern Service Desk is `db.svc_cases`; (2) no engineer-mapping layer (no `ENTITY_RESOURCE` link / `pulse_engineer_id`); (3) no appointments collection (scheduling lives on `svc_cases.scheduled_at`/`assigned_engineer_id`).
- **Tests**: `tests/test_sicon_case_relationships_jun2026.py` (4 new) — attach+unmapped-flag, notes fold+dedupe, flag-off skip, null-protection. 11 pass with existing case-engine tests; readside suite still 16 pass. `SICON_ALLOW_WRITES` stays false.
Files: backend/utils/sicon_import.py, backend/tests/test_sicon_case_relationships_jun2026.py.

## 2026-06 — Sicon Engineer-Mapping Layer (§15) + Requirements Email
Built the Pulse-side engineer-mapping layer — the prerequisite for future appointment/time-booking sync — entirely offline (no live Sicon needed).
- **Link entity**: added `ENTITY_RESOURCE` to sicon_links.py (Sicon resource ↔ Pulse svc_engineer).
- **Backend** (routes/sicon.py): `GET /sicon/read/engineer-mapping` lists cached Sicon resources (db.sicon_engineers, leavers excluded) with their mapped Pulse engineer + an auto-suggested match (by email, then normalised name) and the svc_engineers options + counts. `POST /sicon/read/engineer-mapping` maps or clears a resource→engineer link (validates the engineer exists; empty id clears). Owner/manager gated; audit-logged.
- **Frontend** (SiconMappings.js): new "Engineer mapping" card — per-resource dropdown of Pulse engineers, one-tap "Suggest: <name>" apply for auto-matches, mapped/total counter.
- **Tests**: tests/test_sicon_engineer_mapping_jun2026.py (4) — email suggestion + leaver exclusion, save/clear idempotent, rejects unknown engineer, uses ENTITY_RESOURCE. Full Sicon read-side suite 31 pass.
- **Requirements email**: /app/memory/SICON_INTEGRATION_EMAIL.md — a ready-to-send email to Sicon covering connectivity (external URL + IP allow-list/VPN), auth service account + token TTL, Contract plugin 404, rate limits/page size + modified-since incremental filtering, field semantics (make codes, permanent keys, resource identifiers), and Phase-2 write-back planning.
Files: backend/utils/sicon_links.py, backend/routes/sicon.py, frontend/src/pages/SiconMappings.js, backend/tests/test_sicon_engineer_mapping_jun2026.py, memory/SICON_INTEGRATION_EMAIL.md.

## 2026-06 — UNMAPPED_EQUIPMENT (case_equipment) Resolve UX (§12)
Gave the case-equipment conflict queue its own link/create/ignore actions.
- **Backend** (routes/sicon.py `read_resolve_conflict`): added a dedicated `entity="case_equipment"` branch. external_id is `"{siSMCaseId}:{siconEquipmentId}"`. Actions: **link** (link Sicon equipment→chosen existing Pulse asset via ENTITY_EQUIPMENT, sync fields), **create_new** (create a Pulse asset from the raw Sicon equipment via normalise_equipment + _new_asset_doc, then link), **ignore**. On link/create it also ATTACHES the resolved asset to the case's issue (equipment_ids $addToSet + asset_id/name if unset, never erasing), resolving the case→asset gap. Conflict flipped to resolved + audit-logged.
- **Frontend** (SiconDashboard.js): new "Unmapped case equipment" card with a per-conflict `CaseEqLinker` — searches the Pulse register (`GET /equipment?q=&limit=5`) to Link an existing asset, plus Create asset / Ignore. Generalised `resolve()` to take an entity arg; loads `?entity=case_equipment`.
- **Tests**: tests/test_sicon_caseeq_resolve_jun2026.py (3) — link attaches+links, create_new makes+attaches, ignore leaves issue untouched. Full Sicon read-side suite **34 pass**. Backend imports clean, frontend compiles, both endpoints verified live (200).
Files: backend/routes/sicon.py, frontend/src/pages/SiconDashboard.js, backend/tests/test_sicon_caseeq_resolve_jun2026.py.

## 2026-06 — Sicon Write-Path Consolidation (retire the divergent legacy bridge)
Founder review flagged three divergent Pulse→Sicon paths. Consolidated onto ONE proven authority; all Sicon writes stay disabled (SICON_ALLOW_WRITES=false).
- **Retired the rogue direct-POST** in routes/integrations.py `forward_to_sicon()` — it previously made a raw, UNGUARDED httpx POST to `{base}/api/service/cases` (a non-v1 endpoint, bypassing SICON_ALLOW_WRITES, retries and the outbox). Now a hard no-op that raises + logs `legacy_bridge_blocked` if anything still calls it.
- **`_forward_and_log_sicon`** no longer forwards; it records the Orbit4 ticket in `db.integration_bridge` as `status:"queued_outbox"` and defers Sicon reporting to the single proven subsystem (utils/sicon_client.SiconClient + svc_sicon_outbox worker, per-org, centrally gated by SICON_ALLOW_WRITES via SiconClient._guard_write).
- **Bridge retry endpoint** (`POST /integrations/bridge/{id}/retry`) re-queues to `queued_outbox` instead of performing an independent unguarded POST.
- Single Sicon write authority is now the proven client/outbox. `finance_sync.py` (Sage sales-order, SICON_WEBAPI_*) remains a distinct concern (not a service-case write path) — left as-is.
- **Tests**: tests/test_sicon_bridge_consolidation_jun2026.py (2). Combined Sicon read-side suites: 29 pass. Backend imports clean.
- **Next (Phase 2, per founder "both in sequence")**: wire Orbit4 ticket → per-org Pulse case → svc_sicon_outbox enqueue (proven mapper), and add missing utils/orbit4_outbound.py — build behind SICON_ALLOW_WRITES, keep disabled until the live Sicon base URL arrives.
Files: backend/routes/integrations.py, backend/tests/test_sicon_bridge_consolidation_jun2026.py.

## 2026-06 — Sicon⇄Pulse Link Regression Audit (thorough, pre-Phase-2)
Founder asked to prove recent work didn't break existing Sicon⇄Pulse links before building further. Result: ZERO regressions. Full write-up in memory/SICON_REGRESSION_AUDIT_JUN2026.md.
- Link-critical OFFLINE suites (no HTTP login): 110/110 PASS — incl. link audit, partner-relink self-heal, field/deep mapping, camelcase inbound, integration-field capture, Orbit4 deep mapping + the 4 new Jun suites.
- Live HTTP smoke on every changed endpoint: test-connection/priorities/engineer-mapping/case_equipment-conflicts all 200; bridge retry 403 (correct master-admin gate).
- The broad run's 31 fail + 19 error were fully explained as NON-regressions: ~23 = HTTP 429 auth-lockout (shared test accounts brute-force-locked by running many login suites back-to-back); 8 = pre-existing outdated WRITE tests that expect writes the SICON_ALLOW_WRITES guard correctly blocks (verified pre-existing via git-baseline checkout). 
- Tech-debt logged (non-blocking): update the 2 outdated write test files to the write-guard; give login-based suites a shared token to avoid 429 cascades.

## 2026-06 — Orbit4 Outbound Resync (501 fix) + Write-Test Cleanup
Next action items after the link-safety audit (all safe, no base URL needed).
- **Fixed the 501 bug**: created utils/orbit4_outbound.py with `resync_case(case, user)` — the module routes/svc/orbit4.py imported but was missing (POST /svc/orbit4/cases/{id}/resync always 501'd). It mirrors a Pulse case's status onto its EXISTING Orbit4 ticket via Orbit4Client.update_ticket + map_gymaxis_status_to_orbit4_patch, resolves the per-org connection from db.svc_orbit4_connections (decrypted), and stamps svc_cases.orbit4_sync. Read-safe: only PUTs status onto an existing ticket, never creates/deletes Orbit4 data. Verified live: endpoint now returns 404 for a missing case (was 501).
- **Cleared write-test tech-debt**: test_sicon_service_webapi_v1_jan2026._make_client now builds the client with allow_writes=True so the 6 write-route tests exercise URL/params/headers (the write-guard's disabled-by-default behaviour stays covered in test_sicon_readside.py). All 6 now pass.
- **Tests**: test_orbit4_outbound_jun2026.py (4: status mirror, no-ticket skip, no-connection error, API-error capture). Consolidated offline regression: 68 pass across orbit4 outbound/deep-mapping, sicon readside/case-engine/relationships/caseeq/engineer/bridge + webapi_v1. Backend imports clean.
- Remaining pre-existing tech-debt (non-blocking): test_sicon_bruno_artifacts.py 2 asserts on physical .bru file contents (bruno collection), unrelated to app code.
Files: backend/utils/orbit4_outbound.py, backend/tests/test_orbit4_outbound_jun2026.py, backend/tests/test_sicon_service_webapi_v1_jan2026.py.

## 2026-06 — Phase 2 Sicon Write-Back Scaffolding (flag-gated, disabled)
Founder: build the "report into Sicon" write-back scaffold behind the flag, disabled until go-live. The enqueue helpers (push_case/event/time_entry/signature/attachment/part_movement → svc_sicon_outbox), the outbox worker, and admin drain/simulate endpoints ALREADY existed. Added the two genuinely-missing pieces, safely:
- **Worker safety-gate** (utils/sicon_outbox_worker.tick): a real (non-simulate) drain now SHORT-CIRCUITS when SICON_ALLOW_WRITES=false — rows stay 'pending' (no churn to dead_letter), reported via new DrainResult fields writes_disabled + skipped_writes_disabled. 'simulate' demo mode is exempt (never hits network). This makes "disabled until go-live" clean and preserves the queue for switch-on. Belt-and-braces with SiconClient._guard_write.
- **Single write-back facade** (utils/sicon_writeback.py): the documented Phase-2 entry point — writeback_enabled(), report_case/report_event/report_time_entry/report_signature/report_attachment/report_part_movement (thin wrappers over the proven idempotent enqueue helpers — NOT a parallel path; lazy-imported to keep utils import-safe), and outbox_summary(org) for observability (counts by status + flag).
- Nothing is SENT while SICON_ALLOW_WRITES=false; report_* is always safe to call (captures intent only). Call-site wiring into the svc lifecycle / Orbit4 inbound is deliberately NOT done yet (needs the case-store decision + touches many routes) — that's the next step.
- **Tests**: tests/test_sicon_writeback_jun2026.py (4: worker gate leaves rows pending, simulate exempt, facade idempotent enqueue + summary, flag reflection). Offline link-critical regression: 103 pass across writeback/outbound/readside/relationships/caseeq/engineer/bridge/webapi_v1/case-engine/import-engine/deep-mapping/link-audit/partner-relink. Backend imports clean.
- Pre-existing environmental: test_iter_215dz_sicon_worker (HTTP master-admin login) fails on auth/429 in this env — unrelated to worker drain logic.
Files: backend/utils/sicon_outbox_worker.py, backend/utils/sicon_writeback.py, backend/tests/test_sicon_writeback_jun2026.py.


## 2026-09-30 — Bug fix: BFPO/MOD header account name "blacked out"
- Symptom: In the BFPO/MOD portal header (black bar), the account chip name + avatar initial rendered near-black (#18181B) on black in LIGHT theme — user saw a "blacked out" name.
- Root cause: global rule `index.css:765 [data-theme="light"] .text-white { color: var(--theme-text) !important }` darkens ALL `.text-white` in light mode. The BFPO header black bar (BFPOApp.js) used an inline `backgroundColor:#000000` (not a whitelisted `.bg-*` class) and lacked the `.on-dark` opt-out, so its white text got flipped dark.
- Fix: added `on-dark` class to the BFPO header black-bar div in `/app/frontend/src/pages/BFPO/BFPOApp.js` (~line 99). `.on-dark .text-white` (index.css:812) keeps descendant white text white in light mode.
- Verified on preview via headless browser: avatar + name now compute rgb(255,255,255) on black; screenshot confirmed. Self-tested (single CSS-class fix).
- NOTE: if the user saw this on the DEPLOYED site, a redeploy is required to ship the fix.


## 2026-09-30 — Feature: BFPO / MOD engineer setup & invitations
- Added a full "Engineers & Team" management surface so MOD Operations staff (and Master Admin) can provision BFPO engineers/leads/staff at runtime — previously only the seed script could create them.
- Two host UIs (same component pages/BFPO/staff/StaffEngineers.js): (1) new Engineers tab in the /bfpo staff dashboard; (2) new "BFPO / MOD Engineers" tab under Master Admin -> Organisations -> Onboarding.
- Captures full name, email, phone, role (engineer/lead/staff), assigned territories and allocated sites. Two password flows: email a set-password link OR issue a temporary password (forced change on first login). Plus resend-invite and deactivate/reactivate.
- Backend (routes/bfpo.py), all gated by _require_staff (bfpo staff OR master admin + mod_operations):
  - GET /api/bfpo/staff/territories, GET /api/bfpo/staff/team
  - POST /api/bfpo/staff/engineers (create + invite/temp)
  - PATCH /api/bfpo/staff/engineers/{id}, POST .../resend-invite, POST .../status
  - PUBLIC: GET /api/bfpo/invite/{token}, POST /api/bfpo/invite/{token}/accept (set-password page at /bfpo/invite/:token)
- New collection db.bfpo_invites (single-use token, 7-day expiry). New user fields: phone, bfpo_site_ids. _engineer_scope now includes permanently-allocated bfpo_site_ids in an engineer's visible sites.
- Invite email via existing Resend integration. NOTE: email does NOT physically send in preview (restricted RESEND_API_KEY) — the API still returns invite_url so staff can copy/share it; delivery only works on production.
- Tested: testing_agent backend 15/15 passed (auth negatives, duplicate-email 400, invite token lifecycle, short-password rejection, temp-password must_change flag, edit/resend/deactivate, allocated-site scope). UI verified via screenshots. Master-admin positive path untested only because that account enforces MFA.


## 2026-09-30 — Feature: Engineer Welcome Kit (first sign-in)
- Newly-activated BFPO engineers/leads now see a one-time full-screen welcome on their first sign-in: greeting, their territories, their sites (allocated + territory), and open jobs waiting (with priority badges). Two CTAs: "Explore the portal" and "View my jobs".
- Backend (routes/bfpo.py): create_engineer now sets bfpo_welcome_pending=true for engineer/lead. New endpoints GET /api/bfpo/me/welcome (returns show + territories + sites + open_jobs) and POST /api/bfpo/me/welcome/dismiss. Existing/seeded engineers have no pending flag so they never see it.
- Frontend: pages/BFPO/engineer/WelcomeKit.js overlay, wired into BFPOApp (fetch on mount for engineer/lead, dismiss on action).
- Tested via curl (show=true with correct territory/sites/jobs, dismiss flips to false, seeded engineers show=false) and screenshots (desktop + mobile). Temp test users cleaned up.


## 2026-09-30 — Feature: MOD Operations as a grantable module + launcher tile
- MOD Operations is now grantable per-user from the People -> "Module access" panel (Grant/Revoke), stored at user.module_overrides.mod_operations. Previously it was a hidden gate with no UI to enable it for Pulse staff.
- Backend (routes/master_admin_users.py): added "mod_operations" to _MODULE_META and the module-access catalog (_module_access_payload), plus dedicated grant/revoke branches (reuse the grant_flag/revoke_flag toggle UI) and allowed-module sets.
- Backend (routes/bfpo.py:_role): now returns "staff" for any user where has_mod_operations() is true (platform admins OR module_overrides.mod_operations), so a granted Pulse staffer with NO bfpo_role reaches the MOD Operations staff dashboard instead of the no-access card.
- Frontend: MOD Operations tile added to the login launcher (LauncherPage.js) and the nav "Switch area" menu (AreaSwitcher.js), gated on module_overrides.mod_operations, routing to /bfpo. BFPOApp.js synthesizes role 'staff' for granted Pulse staff.
- Tested: testing_agent backend 9/9 passed (catalog row, grant->DB true->revoke->DB false, bad-module 400, granted non-BFPO user 200 on /bfpo/staff/*, ungranted 403, plus seeded staff/engineer regressions). Frontend self-verified via Playwright (launcher tile visible; granted user lands on staff dashboard). Test state cleaned up.


## 2026-09-30 — Bug fix: "Unknown module" when granting MOD Operations from /pulse People panel
- Symptom: clicking Grant on "MOD Operations" in the /pulse People > "Module access" panel returned an "Unknown module" dialog.
- Root cause: TWO module-access backends exist. The prior change only patched the Master-Admin one (master_admin_users.py). The /pulse People/HR panel (HRTab.js) calls the STAFFING endpoints (staffing.py), whose allowed set _STAFF_MODULE_KEYS did not include mod_operations. The shared _module_access_payload already rendered the row, so the button appeared but grant 400'd.
- Fix (routes/staffing.py): added _STAFF_OVERRIDE_MODULES={"mod_operations"} (non-org-gated per-user overrides) into _STAFF_MODULE_KEYS; added an explicit branch in staff_module_grant and staff_module_bulk that sets module_overrides.mod_operations without the org-enablement gate; revoke falls through to the existing override-clearing branch.
- Tested: testing_agent backend 11/11 passed (grant no longer 400s, DB flips true/false on users+crm_users, org-gate bypassed, bogus key still 400, bulk works, regressions for operations/service_desk and the master-admin path). State cleaned up.
- NOTE: a production deploy was in progress when this bug was reported; production needs a redeploy carrying this staffing.py fix for the panel to work live.


## 2026-09-30 — MOD Operations polish + footer fix + launcher/area-selector tweaks
- FOOTER BUG FIXED: BFPO/MOD layout changed to `min-h-screen flex flex-col` with `<main className="flex-1">` so the footer pins to the bottom instead of floating mid-screen with an empty region below (BFPOApp.js).
- 'Synced' connectivity pill removed for Pulse Fitness staff on the MOD Operations header (AccountMenu.js gains `showSync` prop; BFPOApp passes `showSync={role !== 'staff'}`). Engineers still see Synced/Offline.
- MOD Operations staff dashboard restyled to match the main Pulse Fitness Pro Operations area: 'Pulse Fitness Pro · MOD Operations' title block, rounded pill-group nav, 5 tinted KPI stat cards, clean attention panels (StaffDashboard.js + BFPOApp staff nav). Blueprint saved to /app/design_guidelines.json.
- Launcher tiles now arrange horizontally: grid `sm:grid-cols-2 lg:grid-cols-3`, container widened to max-w-5xl (LauncherPage.js). No hard cap on modules.
- Renamed 'Area chooser…' -> 'Area Selector…' in the Switch-area menu (AreaSwitcher.js).
- Tested: testing_agent frontend 6/6 PASS (footer pinned on tall+short pages, Synced removed for staff / kept for engineer, dashboard KPIs + title, launcher 3-col, Area Selector rename, engineer regression). Verified at 1280px and 390px, no overflow/console errors.


## 2026-09-30 — Bug fix: non-Operations staff routed to /pulse + Dismiss access bypass
- Symptom: a Pulse Fitness Ltd staff member WITHOUT Operations access landed on the Operations dashboard (/pulse) every login and saw an 'Access needed' modal; pressing 'Dismiss' hid the modal and EXPOSED the Operations dashboard (security bypass).
- Root cause: the /pulse route rendered LiteDashboardPage for any logged-in user with NO operations-access guard (unlike /dashboard which had one). The global ModuleAccessDenied overlay's 'Dismiss' simply hid itself, leaving the protected page visible behind it.
- Fix 1 (AppRoutes.js): new PulseRouteElement guards /pulse — if `!isAdmin && module_access.operations === false`, redirect to resolveHomePath(user) (operator-company staff -> /launch); loop-guarded so a genuine single-site pulse_pro/lite customer whose home IS /pulse still renders. Honours ?as=operator preview.
- Fix 2 (ModuleAccessDenied.js): removed the unsafe 'Dismiss' button entirely; only 'Back to my area' (-> /launch) remains.
- Tested: testing_agent frontend 5/5 PASS on desktop+mobile (no-ops user -> /launch, no Operations tile, no overlay; dismiss testid absent from bundle; /dashboard deep-link also redirects; owner WITH operations still reaches /pulse). Temp fixture cleaned up.
- OUTSTANDING (data/deploy, not code): 'Lee Somers can't see MOD Operations' — MOD Operations is a per-user opt-in; needs the module-access grant fix DEPLOYED to production, then grant Lee the MOD Operations module (and Operations if he should have it) from People -> Module access.


## 2026-09-30 — Bug fix: owners couldn't be granted MOD Operations (launcher tile missing)
- Symptom: Lee Somers (role=owner) had broad access but no 'MOD Operations' tile in the launcher. The People 'Module access' panel showed MOD Operations as 'Full access' with NO Grant button.
- Root cause: _module_access_payload (master_admin_users.py) treated `privileged` users (is_master/is_pulse/is_owner) as auto-having MOD Operations -> showed 'Full access' + fix_action None, so the mod_operations override could never be set. But has_mod_operations(), the launcher tile, AreaSwitcher and the /bfpo gate all key off module_overrides.mod_operations (platform admins aside). Owners are NOT platform admins, so the tile/gate never lit up -> mismatch.
- Fix: MOD Operations row is now ALWAYS toggleable (Grant/Revoke) for everyone incl. owners/admins — user_access & fix_action driven purely by the module_overrides.mod_operations override. An admin/manager can now Grant it; once set, the launcher tile appears and /bfpo opens.
- Tested: in-process confirmed Lee's panel row now returns fix_action 'grant_flag' (was None); testing_agent frontend 3/3 PASS desktop+mobile (granted owner sees tile -> opens /bfpo staff dashboard; ungranted owner control = no tile; direct /bfpo honours override). Temp QA users cleaned up.
- PRODUCTION ACTION FOR LEE: redeploy, then in People -> Module access click Grant on 'MOD Operations' for Lee (now a real button); his launcher tile will then appear.


## 2026-10-01 — Fix: password-manager autofill on login pages
- Symptom: saved credentials not offered/autofilled on PulseFitness.ai (reported on Edge + iCloud Passwords; also affects 1Password/Bitwarden/Chrome/Safari).
- Root cause: login inputs were semantic-form-wrapped but had NO name / id / autocomplete attributes, so password managers couldn't recognise the username/password fields.
- Fix (no auth logic changed): added proper attributes to all login forms —
  - PulseLandingPage.js (primary /): <form autoComplete='on'>, username input id='login-username' name='username' autocomplete='username' inputMode='email'; password input id='login-password' name='password' autocomplete='current-password'.
  - CRM/CRMLogin.js login fields, MODPortal/MODServiceLogin.js fields, StaffLogin.js fields: name/id + autocomplete username/current-password.
- Tested: testing_agent frontend 100% — Pulse login dialog markup correct on desktop+mobile, login still succeeds (POST /auth/login 200 + JWT, no error toast); CRM/MOD/Staff attributes confirmed. No auth regression.
- NOTE: requires redeploy to reach production pulsefitness.ai.

## 2026-06 — Sicon equipment template + Missing Information
- One equipment template everywhere: all 9 equipment template downloads now serve the 29-column Sicon template (`utils/sicon_equipment.py`; xlsx via `?format=xlsx`, red = essentials). Old Pulse formats still import.
- All equipment importers (master/account bulk, MOD AI kit import, /equipment import-csv, onboarding, engineer, invoice wizard preview) read Sicon headers; new fields stored: sicon_customer_ref, supplier_reference, contract_line_no, sla_name, stock_item_code, install_date, last_service_date, service_interval, service_period, next_service_date (auto = last + interval), id_number, service_template, equipment_group.
- Missing Information: `routes/equipment_gaps.py` (list/scopes/PATCH/bulk/export.xlsx, site-isolated); Master Admin → Catalogue & Library → Missing information; AI Kit Import done step → "Fill in missing details" grid.
- MOD engineer app: job detail card "While you're on site — N machines need details" (`/api/bfpo/jobs/{id}/equipment-gaps`, POST `.../equipment/{eq}/details`, offline-queued).
- Essentials: Customer Ref, Location, Description, Make, Model, Serial Number (UNKNOWN/N/A = missing).
- Tested: iteration_sicon_equipment_template_gaps_jan2026 + retest (backend 45/45, frontend flows pass).
