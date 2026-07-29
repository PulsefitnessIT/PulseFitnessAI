# i18n Phase 3 — Operations Dashboards (LiteDashboard) progress

Goal: wrap hardcoded strings in `t('staffing.KEY','English default')` across
/app/frontend/src/pages/LiteDashboard/*. Then batch-translate FR/DE and merge
into i18n/locales/{en,fr,de}.json.

## Conventions
- Namespace prefixes (all under top-level `staffing`): use `staffing.<area>_<key>`.
  - MyClockTab -> staffing.clock_*
  - WorkforceDashboardTab -> staffing.wf_* + staffing.day_*
  - TeamAccessTab -> staffing.access_*
  - AIWorkforceTab -> staffing.ai_*
  - SiteStaffManager -> staffing.ssm_*
- Watch for local `t` shadowing (e.g. `.map((t)=>)`) — rename to `st`/`item`.
- Inline EN defaults mean untranslated keys still show English (fallbackLng=en),
  so no raw-key leaks even before FR/DE merge.

## DONE (wrapped with useTranslation + t())
- [x] staffing/MyClockTab.js
- [x] staffing/WorkforceDashboardTab.js
- [x] staffing/TeamAccessTab.js
- [x] staffing/AIWorkforceTab.js  (renamed SUB_TABS.map t->st)
- [x] staffing/SiteStaffManager.js
- [x] staffing/ShiftTemplatesTab.js  (renamed [t,s]->[tRes,sRes], map t->tpl)
- [x] staffing/TimeClockTab.js  (renamed filter/map t->item; hooks in each panel)
- [x] GymFloorManagerTab.js  (renamed topics t->tp/topic)
- [x] StaffingConsole.js — NAV LABELS ONLY (trLabel helper, staffing.nav_*). Deep inline
      panels (Rota schedule, Leave, Market, Rules, Announcements, payroll drawers, staff
      portal preview/credentials) still English — TODO.
- [x] AllSitesOverview.js — general estate overview (ops.as_*). MOD SiteLoginModal left
      English (MOD skip scope).
- [x] staffing/OperationsTab.js (staffing.ops_*; renamed filter/map t->tk, [t,s]->[tplRes,subRes],
      remove(t)->tpl, map t->tpl; translated SUB_TABS + CERT_BANDS labels)
- [x] staffing/CommsTab.js (staffing.comms_*; renamed [t,s]->[thRes,sRes] and all thread
      map/filter/find t->th; translated KIND_META labels; dayLabel(iso,t))

## STILL TODO (P1/P2 backlog — all render English via fallback, functional)
- [x] staffing/HRTab.js — DONE (staffing.hr_*; renamed SUB_TABS.map t->st; translated SUB_TABS +
      field-arrays in Docs/Disciplinary/Training + JobRolesModal + AddStaffDialog)
- [x] staffing/StaffOnboarding.js (~1074) P1 — DONE (staffing.onb_*, 174 keys FR/DE). Shadows renamed
      (CaseDetail load t->tRes, offer/contract map t->tpl, TemplateManager load t->tRes). Verified via
      testing_agent (100% FE, 0 raw-key leaks EN/FR/DE).
- [x] StaffingConsole.js DEEP inline panels P1 — DONE (staffing.sc_*, 119 keys FR/DE). Added useTranslation
      to RotaTab/AddShiftDialog/StaffTab/CopyableField/LeaveTab/MarketTab/PerformanceTab/PayrollTab/
      LiveFloorTab/RulesTab/AnnouncementsTab/AIInsightsTab. Renamed shadows: RotaTab day-totals t->dt,
      LeaveTab leave-type map t->lt. Verified via testing_agent (100% FE, 0 raw-key leaks EN/FR/DE).
      Report: /app/test_reports/iteration_staffing_console_deep_i18n_fr_de_jan2026.json
- [x] staffing/orgchart/* (14 files ~2100 lines) P2 — DONE (orgchart.*, 257 keys FR/DE).
      Localized: OrgChartTab, Canvas, OrgCard, ListView, Vacancies, Templates, AIPanel, HistoryTab,
      ImportExport, DocumentImport, Settings, ShareModal, Presentation, panels (AddNodeModal/NodeDrawer/
      MoveConfirmModal). Shadows renamed: Templates map t->tpl, AIPanel copyJd t->jdText,
      Canvas setTimeout t->tid, panels EDGE_TYPES map/find t->et, RotaTab-style day map n/a.
      Dynamic keys (node_/field_/col_/action_/subtab_/ie_field_) added to i18n_translate_ops.py
      as explicit orgchart_dyn dict (48 keys). Verified via testing_agent: 100% (24/24 sub-tab
      renders EN/FR/DE, 0 raw-key leaks). Testing agent fixed 1 latent crash (DocumentImport.js
      missing useTranslation hook — an edit lost to the recurring trailing-duplicate corruption).
      Report: /app/test_reports/iteration_orgchart_i18n_fr_de_jan2026.json
      i18n Phase 3 (Operations/Staffing FR+DE) is now COMPLETE.

## PIPELINE BUILT & VERIFIED (idempotent, re-runnable)
- /app/backend/scripts/i18n_translate_ops.py — extracts t('staffing/ops/orgchart.*','en')
  from LiteDashboard, translates NEW/untranslated keys EN->FR & EN->DE via Claude
  (emergentintegrations), merges into en/fr/de.json. Re-run after wrapping more files:
  `cd /app/backend && python scripts/i18n_translate_ops.py`
- Ran once: 243 keys translated. Frontend compiles clean.

## ALREADY TRANSLATED (pre-existing, skip)
- LiteDialogs.js, LiteDocumentsTab.js, LiteEquipmentTab.js, LiteFaultsTab.js,
  LiteOverviewTab.js, OperationsStartTab.js

## SKIP (per user)
- MODStaffTab, MODStaffTransferTab, MODComplianceCalendar, MODAuditLogPanel, MODDIOContractModal
- groupIssuesByJob.js, staffing/orgchart/api.js, staffing/orgchart/layout.js (no UI strings)

## FINAL STEPS
1. Run /app/scripts/i18n_extract_ops.py (to build) — extract t('staffing.*','..') & t('ops.*') keys.
2. LLM-translate EN->FR, EN->DE (emergent key). Merge into en/fr/de.json.
3. testing_agent frontend: render LiteDashboard tabs in EN/FR/DE, no raw key leaks.

## ═══ 2026-07-29 · MODULE ROLLOUT (Memberships / Marketing / ServiceOps) — BATCH 1 ═══
User asked to continue FR/DE rollout across Memberships, Marketing, ServiceOps (SKIP MOD Portal — UK only).
NEW generalised pipeline: /app/backend/scripts/i18n_translate_modules.py
  - Scans pages/Memberships, pages/Marketing, pages/ServiceOps, pages/ServiceDesk for t('ns.key','English')
    in namespaces (memberships_console, mkt, service, sicon). Translates NEW/untranslated keys EN->FR/DE via
    Claude, merges en/fr/de.json. Has the same useTranslation() guard (`--check`). Re-run after wrapping more files:
    `cd /app/backend && python scripts/i18n_translate_modules.py`

BATCH 1 DONE (Memberships console shell + core inline screens), VERIFIED DE render via screenshot:
  - MembershipsConsole.js: all TAB labels (tab_*), header subtitle (memberships_console.header_subtitle).
  - DashboardTab: hook + Header (dash_*) + all 10 KPI labels (kpi_*) + "Today at a glance" + empty + load error.
  - MembersTab: hook + Header (mem_*) + search placeholder + CSV/import/add buttons + table col headers (col_*) + empty state.
  - TimetableTab: hook + Header (tt_*).
  - CommissionSection: hook + header (comm_*).
  - 80 memberships_console keys now in en/fr/de.json (69 FR + 65 DE freshly translated this batch).

REMAINING Memberships (TODO — still English via fallback, functional):
  - MembershipsConsole.js DEEP: PlansInnerView, ClassesTab, SchedulingHubTab pills, RecordPaymentModal,
    PAY_METHODS/DAYS_OF_WEEK arrays, LegacyMemberDetailDrawer (NOTE: not rendered — skip), AdsTab, SetupNudge,
    the Members table mobile card ("No plan"/"Loading…"/no-shows), notify/confirm strings.
  - Separate files (each needs its own useTranslation): MembershipsStartTab, StudioQuickstart ("Let's get your
    studio live" onboarding — HIGH visibility), MemberPortal, InstructorPortal, AnalyticsTab, StudioBuilderTab,
    MobileAppBuilderTab, InvoicingTab, EventsTab, PromotionsTab, CheckinTab, FamilyBillingTab, CRMLoopTab,
    MemberEditDrawer, InstructorRosterView, CoursesView, tabs/*, modals/*, DunningPanel, RevenueAutopilotPanel,
    GDPRPanel, BookingRulesTab, etc. (~55 files, ~20k lines).

NOT STARTED: Marketing module (namespace mkt — partial), ServiceOps (namespace service — partial), ServiceDesk.
Watch for `t` SHADOWS in Memberships (e.g. ClassesTab `.map((t)=>t.name)` at old line ~1373 — rename to `tpl`).

## ═══ 2026-07-29 · BATCH 1b — ServiceOps / Service Desk shell (VERIFIED DE live) ═══
NOTE: /service-desk route renders pages/ServiceDeskPage.js (top-level SHELL with the sidebar). The
pages/ServiceOps/ServiceDeskPage.js is the "Cases" tab content, mounted as <OpsCases/> inside that shell
(NOT dead — the `_ServiceOpsDeskPage` unused import in AppRoutes.js is a separate red herring).

DONE (namespace `service`), VERIFIED DE render via screenshot (sidebar fully German):
  - pages/ServiceDeskPage.js SHELL: sidebar nav labels via t(`service.nav_${id}`, label) for primary tabs
    (dashboard/cases/scheduler/customers/equipment/maintenance/stores/billing/analytics/expenses/safety/
    compliance), insights (overview/suppliers/reports), options (imports/integrations/audit/account/engineers),
    + brand ("Service Desk"/"Field service ops"), Inventory & Distribution, Insights group, Options.
    Renamed the useState-initializer `t` SHADOW (searchParams.get('tab')) -> `tp`.
  - pages/ServiceOps/ServiceDeskPage.js (Cases queue): hero buttons, Header (desk_title/subtitle), all KPI
    labels+hints, filter option lists (status/priority/type), search placeholder, table col headers, empty/loading.
  - Explicit `service_nav` dict added to i18n_translate_modules.py (template-literal keys the scanner can't see).

REMAINING ServiceDesk/ServiceOps (TODO): the Dashboard tab content (Total Customers/Active/Pending/Archived KPIs,
Recent Activity, Team Performance) + all other tab bodies (Customers, Equipment, Maintenance, Stores, Billing,
Scheduler, Analytics, Engineers, Compliance, Imports, Integrations, Audit) + ServiceOps/Engineer/* (the large
EngineerJobDetailV2 4039 lines etc.) + ServiceCaseDrawer. These render English via fallback (functional).

## MARKETING: not touched this session (already partial via `mkt` namespace + MarketingShell/PulseMarketingShell
use t). Pipeline i18n_translate_modules.py scans pages/Marketing too, so wrapping more Marketing strings + re-run
will translate them. TODO next.

TOTALS after this session: service ns has +~50 new keys, memberships_console 80 keys, all en/fr/de populated.
Run to translate future batches: `cd /app/backend && python scripts/i18n_translate_modules.py`

## ═══ 2026-07-29 · BATCH 2 — Memberships DEEP FILES (VERIFIED DE live) ═══
Fully localized (FR+DE, namespace memberships_console with per-file prefixes), all compile clean:
  - StudioQuickstart.js (prefix sqs_) — 6 components: onboarding wizard (brand/pricing/schedule/review/done steps).
  - MembershipsStartTab.js (prefix start_) — 4 components: onboarding checklist, module discovery card, logo upload modal.
  - PromotionsTab.js (prefix promo_) — 4 components: list, promo card badges, editor modal. Moved KIND_OPTIONS/
    DURATION_OPTIONS inside the modal so t() calls are statically scannable.
  - InvoicingTab.js (prefix inv_) — monthly invoicing: controls, preview table, history table, actions, notifications.
    inv_status_{draft,sent,paid,void} added to pipeline explicit dict (template-literal keys).
  - EventsTab.js (prefix evt_) — 4 components: list, detail (rehearsals/costumes/AI comms), 3 modals. evt_kind_* and
    evt_costume_* added to pipeline explicit dict.
VERIFIED: Promotions tab live in German ("Noch keine Werbeaktionen", empty CTA, tab pills Veranstaltungen/Aktionen/
Anzeigen/Analysen). memberships_console namespace now ~330 keys, all en/fr/de populated.

PIPELINE GOTCHA fixed: DE chunks failed json.loads when a source English string had embedded double-quotes
(e.g. `e.g. "Spring Recital 2026"`). FIX: removed inner double-quotes from source defaults. RULE: avoid embedded
double-quotes in t() default strings (the LLM emits them unescaped and breaks JSON). If a DE run shows
"parse fail chunk N / DE translated: 0", check the newest keys for inner double-quotes.

REMAINING Memberships files (next batch, still English via fallback): AnalyticsTab (1001), MobileAppBuilderTab
(1294), StudioBuilderTab (907), MemberPortal (999), MemberEventsTab, CheckinTab, FamilyBillingTab, CRMLoopTab,
DeskSalesTab, InstructorsTab, MobileAppTab, plans/classes inline in MembershipsConsole, tabs/*, modals/*, and the
deep parts of MembershipsConsole (PlansInnerView, ClassesTab, SchedulingHubTab, RecordPaymentModal, AdsTab).
Then: Marketing module (mkt ns).

## ═══ 2026-07-29 · BATCH 3 — Memberships mid-size tabs (VERIFIED DE live) ═══
Fully localized (FR+DE, all compile clean, guard passes):
  - InstructorsTab.js (prefix inst_) — roster/performance/cover-board subtabs, metrics, cover assign modal.
  - FamilyBillingTab.js (prefix fam_) — AI risk table, sibling/multi-class discount ladders, payment plans.
    RISK_TONES.label -> labelKey (fam_risk_high/medium/low). RENAMED a `t` SHADOW: tiers.map((t)) -> (tier).
  - CRMLoopTab.js (prefix crml_) — dashboard/rules/signals/sends subtabs. RENAMED tab-map `t` -> `tab` shadow.
    KIND_META.label -> labelKey; crml_kind_* added to pipeline dict.
  - CheckinTab.js (prefix chk_) — toolbar, roster drawer, walk-in/broadcast/kiosk/search/share dialogs, all
    notifications. RENAMED a `t` SHADOW in MemberSearchDialog (setTimeout const t -> timer).
VERIFIED: Check-in tab live in German (Heute/3 Tage/Aktualisieren/Mitglied finden/Kiosk-Modus, empty state).
Pipeline now extracts 775 keys total across the 4 module namespaces.

REMAINING Memberships (4 LARGE files, next batch — still EN via fallback, functional):
  AnalyticsTab.js (1001), MobileAppBuilderTab.js (1294), StudioBuilderTab.js (907), MemberPortal.js (999).
  Plus deep inline parts of MembershipsConsole (PlansInnerView, ClassesTab, SchedulingHubTab, RecordPaymentModal,
  AdsTab), tabs/* (BookTab, BookingsTab, PassTab, PlanTab, ProfileTab), modals/*, MemberEventsTab, DeskSalesTab,
  MobileAppTab. Then the Marketing module (mkt ns).

## ═══ 2026-06 · BATCH 4 — Memberships 4 LARGE files (VERIFIED EN/FR/DE via testing_agent) ═══
Fully localized (FR+DE, all compile clean, guard passes, 0 raw-key leaks):
  - MemberPortal.js (prefix mp_) — finished the remaining sub-components (StreakCard, RequiredFormsBanner,
    ReferralCampaignBanner, TopBar, InstallPrompt, BottomNav, MoreSheet). Renamed BottomNav map `t`->`nav`.
    Tab/more labels via template-literal keys mp_tab_* / mp_more_* (added to pipeline dict). Removed embedded
    double-quotes from mp_login_bad_detail (broke DE JSON — the recurring quote hazard).
  - StudioBuilderTab.js (prefix sb_) — full rewrite w/ i18n. Renamed all `t` template-object shadows -> `tpl`
    (main handlers, BuilderGrid find/filter, TemplateChip & ScheduledCard props). Day abbreviations via
    sb_day_0..6 (pipeline dict), reused by AnalyticsTab heatmap.
  - AnalyticsTab.js (prefix an_) — full rewrite. Renamed KpiCard `const t = toneMap` shadow -> `tn`, and added
    a stable `testId` prop so data-testid mbr-kpi-<slug> stays language-stable. Section/role labels via
    an_sec_* / an_role_* (pipeline dict). Recharts legend `name=` props localized too.
  - MobileAppBuilderTab.js (prefix mab_) — full rewrite. No `t` shadows. font/button/share-format labels via
    template-literal keys mab_font_* / mab_btn_* / mab_fmt_* (pipeline dict). Canvas + printQr HTML strings localized.
VERIFIED: testing_agent iteration_memberships_i18n_fr_de_jan2026.json — 100% FE, 0 raw-key leaks in 15 states
  (analytics/studio-builder/mobile-app × en/fr/de + member portal). ~39 memberships_console keys intentionally
  stay == EN (brand/proper nouns: Dashboard, Home, CRM, "Mobile App Builder", etc.) — not leaks.
This COMPLETES the 4 large Memberships tabs the user asked for. NEXT: Marketing module (mkt ns).
