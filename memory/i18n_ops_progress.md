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

## ═══ 2026-06 · MARKETING module FR/DE (mkt namespace) — IN PROGRESS ═══
User directive: localize the ENTIRE Marketing module (Group A operator console + Group B public/SEO pages).
DONE this session (compile OK, guard OK, FR+DE translated, prefixes noted):
  - InsightsTab.js (mkt.ins_), PerformanceTab.js (mkt.perf_), SocialTab.js (mkt.soc_),
    AudiencesTab.js (mkt.aud_), JourneysTab.js (mkt.jn_ — renamed no shadow; test-send dialog),
    StartTab.js (mkt.start_ — FULL REWRITE, moved OUTCOMES/STEPS/TEMPLATES/quickStart/jump arrays inside
      component to use t(); renamed TEMPLATES map `t`->`tpl`),
    ContactsTab.js (mkt.ct_ — renamed tag map `t`->`tag` in list + ContactDialog),
    DynamicListsTab.js (mkt.dl_ — refresh-opts via template-literal keys dl_refresh_opt_{15,60,240,1440} in pipeline dict),
    FormSubmissionsDrawer.js (mkt.fsd_), FormsAndPagesTab.js (mkt.fp_ + SurveyResultsDialog).
⚠️ RECURRING TOOL BUG: search_replace on the LAST lines of a file sometimes duplicates/corrupts the tail
   (saw it on SocialTab, ContactsTab, DynamicListsTab, FormsAndPagesTab — stray `rt default X;` / doubled
   `export default`). ALWAYS babel-parse each edited file (node @babel/core) and fix the tail before moving on.
REMAINING Marketing files (NOT yet localized):
  Group A console: CampaignsTab (621), CampaignWizard (574), CreativeStudioTab + CreativeStudioRoot (~655),
    FormBuilderDialog (327), PageBuilderDialog, BrandKitTab, BrandDiscoveryPanel, AIAssistant (311),
    AIDirectorPanel, ChurnRescuePanel, EmailVolumePanel, StarterPackPanel, MarketingChat, ROICalculator,
    TrialSignupModal, MarketingTour, UndoLaunchBanner, CRMProTrialNudge, SiteCalculatorUpsell,
    ProductPreviewModal, (MarketingHome/Shell/PulseMarketingShell/AxisOrbit already partly done earlier).
  Group B public/SEO: Blog/*, Compare/*, Landing/*, modules/*, ModulePage, PricingMarketingPage,
    SecurityMarketingPage, SecurityDocumentPage, ContactMarketingPage, PartnerApplyPublic,
    PartnerEngineerLanding, MigrationGuarantee, ServiceDeskPromo, LiveCustomer/EngineerAppPreview, etc.
Pipeline: `cd /app/backend && python scripts/i18n_translate_modules.py` (auto FR+DE; `--check` for guard).

## ═══ 2026-06 · MARKETING module — SESSION 2 batch (files 11-16) ═══
Additional DONE (compile OK, babel-parse OK, guard OK, FR+DE translated):
  - UndoLaunchBanner.js (mkt.ulb_), EmailVolumePanel.js (mkt.evp_), CRMProTrialNudge.js (mkt.cpn_),
    SiteCalculatorUpsell.js (mkt.scu_ — INCLUDED_PERKS moved inside component to use t()),
    CreativeStudioRoot.js (mkt.csr_), PageBuilderDialog.js (mkt.pbd_).
TOTAL Marketing files localized so far this session: 16
  (Insights, Performance, Social, Audiences, Journeys, Start, Contacts, DynamicLists,
   FormSubmissionsDrawer, FormsAndPagesTab, UndoLaunchBanner, EmailVolumePanel, CRMProTrialNudge,
   SiteCalculatorUpsell, CreativeStudioRoot, PageBuilderDialog).
⚠️ TOOL BUGS SEEN (verify every file): (1) tail-corruption on EOF edits; (2) occasional phantom
   "Edit was successful" that didn't actually apply (saw on SiteCalculatorUpsell scu_start_trial /
   scu_see_pricing — had to re-apply). ALWAYS babel-parse + grep the new key after editing near EOF.
STILL REMAINING (Marketing):
  Group A big console tabs: CampaignsTab (621), CampaignWizard (574), CreativeStudioTab/LegacyCreativeStudioTab (655),
    AIDirectorPanel (819), ChurnRescuePanel, BrandDiscoveryPanel, StarterPackPanel, BrandKitTab,
    FormBuilderDialog (327), AIAssistant (311), MarketingChat, ROICalculator, TrialSignupModal,
    MarketingTour, ProductPreviewModal, CRMLoop/other small nudges.
  Group B public/SEO: Blog/*, Compare/*, Landing/*, modules/*, ModulePage, PricingMarketingPage,
    SecurityMarketingPage, SecurityDocumentPage, ContactMarketingPage, PartnerApplyPublic,
    PartnerEngineerLanding, MigrationGuarantee, ServiceDeskPromo, LiveCustomer/EngineerAppPreview.
NOTE: testing_agent NOT yet run for the Marketing batch — run it once the console tabs are complete.



## Marketing module (mkt.*) — Batch 2 (2026-06, VERIFIED EN/FR/DE 100%, 0 key leaks)
Report: /app/test_reports/iteration_marketing_i18n_fr_de_jan2026.json
Files localized this session (11 components + shell fixes):
- [x] FormBuilderDialog.js (mkt.fb_*; renamed FIELD_TYPES.map((t)) shadow -> ft; moved FIELD_TYPES/CRM_PROPERTIES inside component)
- [x] MarketingChat.js (mkt.mc_*; renamed send() `const t` -> txt; SUGGESTIONS moved inside)
- [x] ROICalculator.js (mkt.roi_*; Slider/Line receive translated props at call site)
- [x] AIAssistant.js (mkt.aia_*; renamed all setTurns((t)) -> setTurns((prev)); STARTER_QUESTIONS inside)
- [x] BrandKitTab.js (mkt.bk_*; BannedPhrasesEditor now takes placeholder prop)
- [x] StarterPackPanel.js (mkt.sp_*; EMAIL_META label/hint via template keys mkt.sp_email_<id>_label/hint)
- [x] ProductPreviewModal.js (mkt.pp_*; scene title/caption via template keys mkt.pp_title_/caption_<sceneId>; mock scene body artwork left EN by design)
- [x] BrandDiscoveryPanel.js (mkt.bd_*)
- [x] ChurnRescuePanel.js (mkt.cr_*; renamed targets.map((t)) -> tg; RescueRow + RescueChannel each got own useTranslation; signal/status labels)
- [x] MarketingTour.js (mkt.mt_*; STEP title/body via template keys mkt.mt_<stepId>_title/body)
- [x] TrialSignupModal.js (mkt.ts_*; module label/blurb via template keys mkt.ts_mod_<key>_label/blurb)
- [x] MarketingSuite.js — top-tab strip labels wired to t('mkt.tab_<id>') (desktop + mobile)
- [x] FormsAndPagesTab.js — empty-state + loading strings (mkt.fp_no_forms/fp_loading) [gap-fill from prior batch]
Template-literal keys are NOT statically scannable — they are seeded in i18n_translate_modules.py via pairs.update({...}) blocks (pp_*, sp_email_*, mt_*, ts_mod_*, tab_*).
mkt.* key count: 878 in each of en/fr/de.json (as of this batch).

### STILL TODO — Marketing (next batch, Group A big console tabs):
- [ ] CampaignsTab.js (621 lines)
- [ ] CampaignWizard.js (574 lines)
- [ ] CreativeStudioTab.js (655 lines)
- [ ] AIDirectorPanel.js (819 lines)
### Group B (public/SEO pages, later): PricingMarketingPage hero, Blog/Compare/Landing/module/security pages.
### Minor shell gaps observed: MarketingSuite header subtitle "Campaigns, journeys, creative & growth insights", "Pro Marketing"/"manage packs" chip.


## Marketing module (mkt.*) — Batch 3 (2026-06, VERIFIED EN/FR/DE 100%, 0 key leaks)
Report: /app/test_reports/iteration_marketing_i18n_4tabs_jan2026.json
The 4 largest Group-A console tabs — Group A Marketing i18n now COMPLETE:
- [x] CampaignsTab.js (mkt.cmp_; + TemplateEditorModal; shadows renamed: load destructure t->tplRes, removeTemplate/resetStockTemplate param t->tpl, templates.map t->tpl)
- [x] CampaignWizard.js (mkt.wz_; ProgressBar + AICopilot got own useTranslation; TIME_SLOTS.map t->slot; step/goal/audience/channel/time labels via template keys mkt.wz_step_/goal_/aud_/chan_/time_*)
- [x] CreativeStudioTab.js (mkt.cs_; TYPES.map t->ty; type/style/mood/idea/category via template keys mkt.cs_type_/style_/mood_/idea_/cat_*)
- [x] AIDirectorPanel.js (mkt.dir_; PosterCard/ChannelCard/ChannelBody got own useTranslation; presets.tones.map t->tn; tone/goal/segment/quickstart/refine/channel via template keys mkt.dir_tone_/goal_/seg_/qs_/refine_/chan_*)
mkt.* key count now 1288/locale. Template-literal keys seeded in i18n_translate_modules.py pairs.update() blocks.
NOTE (from tester): AI Director & Churn Rescue live as SUB-tabs inside the Creative Studio tab (marketing-tab-creative), not separate top tabs.

### Marketing STILL TODO — Group B (public/SEO pages, later):
- [ ] PricingMarketingPage hero, Blog, Compare, Landing, module/security public pages.
### Next module areas after Marketing: ServiceOps, Staffing, Settings.


## ═══ 2026-06 · ServiceDesk tab bodies FR/DE — BATCH 1 (VERIFIED DE render, 0 leaks) ═══
User picked "C" (continue i18n: ServiceOps/Staffing/Settings). Staffing (Phase 3) already COMPLETE, so
started on the ServiceDesk/ServiceOps tab BODIES (only the shell + Cases queue were done before).
DONE this batch (namespace `service`, per-file prefixes; full rewrites via create_file; babel-parse OK; guard OK):
  - ServiceDesk/DeskSummary.js (service.sum_*) — Dashboard KPIs + Recent Activity + SubscriptionCard.
    Added stable `tid` field to stat objects so data-testid `desk-stat-<tid>` stays language-stable (was derived
    from the translated label → would have broken tests).
  - ServiceDesk/DeskCustomers.js (service.cust_*) — header, filters, OrgRow account-type labels, empty/loading.
  - ServiceDesk/DeskEquipment.js (service.eq_*) — global kit search, empty states, warranty label. Renamed
    debounce setTimeout `const t`->`timer` (shadow).
  - ServiceDesk/DeskPerformance.js (service.perf_*) — FTF ring, MiniStats, 6 KPI tiles, engineer leaderboard.
  - ServiceDesk/DeskSuppliers.js (service.sup_*) — supplier-health rollup. Moved SORTS inside component to use t();
    renamed supplier_types `.map((t))`->`(st)` shadow; WINDOW_OPTIONS labels (7d/30d/90d/1y) left as-is (universal).
Pipeline run: 113 new `service` batch keys × en/fr/de (229 FR + 222 DE translated). i18n guard passes.
VERIFIED: EN render clean; profile language→de (PATCH /api/account/profile {language:'de'}) → Service Desk
  dashboard + Team Performance render fully in German (Kunden gesamt/Aktiv/Letzte Aktivitäten/Team-Leistung/
  SOFORTLÖSUNG/Offene Fälle/SLA überschritten); 0 raw-key leaks on any tab. Demo account language reverted to 'en'.
NOTE: owner@isodemo.com is a Pulse OPERATOR desk so Equipment/Suppliers tabs are visible (provider desks hide them).
REMAINING ServiceDesk/ServiceOps (next batches, still EN via fallback = functional):
  ServiceDesk/: DeskAnalytics, DeskExpenses, DeskImports, DeskIntegrations, DeskProviderCustomers, DeskCustomerDetail,
    DeskAuditLog, DeskPreventativeMaintenance, Orbit4Wizard. (MODVisitCalendar = MOD, skip.)
  ServiceOps/: ServiceCaseDrawer (1125), ServiceOpsReportsPage (749), ServiceDeskIntakeForm (702), EngineersAdminPage,
    AIScheduling, ComplianceAdmin, PartsInventoryPage, AdminDispatchBoard, BillingPage, ServiceScheduler,
    ServiceCaseLifecycleTab, CommsHubPage, SafetyTemplateAdmin, PartsAllocator, EngineerRosterPanel, FindEngineerPanel,
    EquipmentMultiSelect, ServiceOpsShell, Engineer/* (large), Inventory/*.
THEN: Settings module.
Pipeline: `cd /app/backend && python scripts/i18n_translate_modules.py` (guard: `--check`).

## ═══ 2026-06 · ServiceDesk tab bodies FR/DE — BATCH 2 (VERIFIED DE render, 0 leaks) ═══
Localised 6 more ServiceDesk/ tabs (namespace `service`, full rewrites, babel-parse OK, guard OK):
  - DeskAuditLog.js (service.aud_*) — audit log header/filter/refresh/empty/Master Admin badge.
  - DeskCustomerDetail.js (service.cd_*) — back/impersonate, stat cards (added stable `tid`), editable
    Customer Details fields, Sites/Staff/Suppliers sections w/ interpolated counts, notify strings.
  - DeskAnalytics.js (service.anl_*) — range presets (via `{{n}} days`), 6 KPIs, weekly trend (Recharts
    Bar/Line names), SLA-by-priority, Revenue, Engineer utilisation. PRESETS kept module-level (label→key).
  - DeskExpenses.js (service.exp_*) — Approvals/Reports/Settings sub-views; each inner component wired its own
    useTranslation; renamed queue-map `t`->`tItem` shadow; GROUPS moved to {id,label} w/ stable data-testid.
  - DeskImports.js (service.imp_*) — 4-step migration wizard; moved TYPES + STEP_LABELS inside component to use t().
  - DeskIntegrations.js (service.o4_*) — Orbit 4 self-serve connection: status/creds/health/activity/engineer map + toasts.
Pipeline: +221 new `service` keys (aud7/cd33/anl33/exp54/imp43/o4 51) × en/fr/de (345 FR + 338 DE translated total run).
VERIFIED: babel-parse all 6 OK; i18n guard passes; keys present in en/fr/de. Live German smoke of the Analytics tab
  (Analysen / KPIs / Wöchentliche Fälle & SLA-Pünktlichkeit % / SLA-Einhaltung nach Priorität / Umsatz / Technikerauslastung)
  — renders fully in German, 0 raw-key leaks. Demo account (owner@isodemo.com) language reverted to 'en'.
ServiceDesk/ FR/DE is now COMPLETE except MODVisitCalendar (MOD-skip), DeskPreventativeMaintenance, DeskProviderCustomers, Orbit4Wizard.
NEXT: ServiceOps/ tab bodies (ServiceCaseDrawer, ServiceOpsReportsPage, EngineersAdminPage, etc.), then Settings.

## ═══ 2026-06 · SETTINGS MODULE FR/DE — (VERIFIED DE render across 5 panels, 0 leaks) ═══
User: "Bring the Settings module into the FR/DE rollout." Added a NEW `settings` namespace and wired the pipeline
to also scan `frontend/src/components/shared` (SCAN_DIRS + NAMESPACES in scripts/i18n_translate_modules.py).
Localised the entire Account Settings module (377 settings keys × en/fr/de):
  - AccountSettingsModal.js — title/subtitle + nav labels. NOTE: SECTIONS in shared.js uses a dynamic `labelKey`
    the extractor can't see statically, so nav labels are ALSO declared as static t() calls in a NAV_LABELS map
    inside the modal (settings.nav_*) so the pipeline picks them up. Keep that pattern for any new nav item.
  - AccountSettings/shared.js — SECTIONS now carries {labelKey, label} (label = English fallback).
  - profile.js (prof_*), security.js (sec_*), preferences.js (pref_*), LocalizationPanel.js (loc_*),
    organisation.js (org_*), billing.js (bill_*), team.js (team_*), onboarding.js (ob_*), suppliers.js (sup_*),
    ActiveSessionsPanel.js (sess_*), QrPrintInline.js (qr_*), EquipmentImportInline.js (eqimp_*).
  - Shadows fixed: PortalField `const t`->`inputType` (onboarding); boolean testid made language-stable (yes/no).
  - relTime(iso) in ActiveSessionsPanel now takes (iso, t).
Pipeline: guard passes; all 13 files babel-parse OK. VERIFIED live (profile lang→de via PATCH /api/account/profile,
  open modal via ServiceDesk Optionen→Kontoeinstellungen): modal + Profile/Security/Billing/Team/Suppliers panels all
  render in German, 0 raw-key leaks. Demo account (owner@isodemo.com) reverted to 'en'.
REMAINING (nested shared components rendered INSIDE settings panels, still English — NOT the AccountSettings files):
  MFASetupCard ("Two-factor authentication"/"Enable MFA"), DigestPreferencesCard, StripeConnectErrorBanner,
  AddEquipmentDialog, InvoiceImportWizard, and the separate DocumentBrandingSettings + SiteDataExportPanel pages.
  Also role-value display "Owner"/plan names come from backend data (dynamic).
NEXT FRONTIER: ServiceOps/ tab bodies (ServiceCaseDrawer, ServiceOpsReportsPage, EngineersAdminPage, etc.).

## ═══ 2026-06 (fork) · ServiceOps tab bodies FR/DE — BATCH 3 (VERIFIED EN/DE/FR via testing_agent, 0 leaks) ═══
User picked "B": finish ServiceCaseDrawer THEN continue into more ServiceOps files.
DONE this session (namespace `service`, babel-parse OK, guard OK, FR+DE translated, testing_agent 100% FE):
  - ServiceCaseDrawer.js (cd_*) — COMPLETED the remaining raw strings the prior fork left: Details tab
    (Estimated minutes/Description/Logged/Source/SLA meta), Customer tab, footer (Save changes/tracking/
    service report/transitions/No further transitions), RatingPromptModal (added own useTranslation),
    CommsTab (added own useTranslation; RENAMED templates.map((t)) shadow -> (tpl)). 144 unique cd_ keys.
  - ServiceDeskIntakeForm.js (intake_*) — FULL REWRITE via create_file. Moved PRIORITY_OPTIONS inside the
    component to use t(); CoveragePanel got its own useTranslation. 9 step legends, all selects/placeholders,
    AI triage block, coverage panels, notify messages. (NOTE: did NOT add case_type to payload — kept scope.)
  - BillingPage.js (svcbill_*) — added useTranslation to BillingPage + QuoteEditor. Shell title/subtitle/
    filters, table headers, quote editor line table, totals (Subtotal/Net/VAT/Gross), footer buttons, notifies.
  - ServiceScheduler.js (sched_*) — added useTranslation to CaseCard + ServiceScheduler. title/subtitle,
    Prev/Today/Next/day-select/Refresh, Unassigned queue, Auto-assign, engineer header, diary empty/loading,
    breach/risk/ok pills, notify messages. (const t = new Date() locals in callbacks are harmless shadows.)
⚠️ RECURRING TOOL HAZARDS HIT THIS BATCH (all fixed + re-verified):
  - Tail-corruption on EOF edits: BillingPage got a stray `}` at EOF; ServiceScheduler got a duplicated
    ServiceOpsShell tail. Fixed both, babel-parse OK.
  - PHANTOM-SUCCESS: several ServiceScheduler edits (main useTranslation hook, title/subtitle, breach/risk/ok,
    Unassigned/queue/Auto-assign) + BillingPage line-40 notify reported "Edit was successful" but did NOT apply.
    Caught via a post-edit grep of every key against the source, then re-applied one at a time. ALWAYS grep
    each key in the source after a batch, not just babel-parse.
Pipeline run TWICE (must run in BACKGROUND — foreground 120s timeout aborts before the final merge, losing
  all FR/DE work). `cd /app/backend && nohup python scripts/i18n_translate_modules.py > /tmp/x.log 2>&1 &`.
  Total this batch: ~490 FR + ~456 DE keys translated across the two runs. service ns fully populated EN/FR/DE.
VERIFIED: testing_agent iteration_serviceops_i18n_fr_de_jan2026.json — 100% FE, 0 raw-key leaks across all 4
  screens in EN/DE/FR. Demo account (owner@isodemo.com) language reset to 'en'.
PRE-EXISTING (out of scope, noted by tester): AIScheduling.js line 436 renders <span> child of <option>
  (React hydration warning). Low-priority console noise — fix when localizing AIScheduling.
REMAINING ServiceOps/ (still EN via fallback, functional): ServiceOpsReportsPage (done earlier), EngineersAdminPage
  (done earlier), AIScheduling, ComplianceAdmin, PartsInventoryPage, AdminDispatchBoard, ServiceCaseLifecycleTab,
  CommsHubPage, SafetyTemplateAdmin, PartsAllocator, EngineerRosterPanel, FindEngineerPanel, EquipmentMultiSelect,
  ServiceOpsShell chrome, Engineer/* (large), Inventory/*. THEN nested Settings shared cards (MFASetupCard etc).

## ═══ 2026-06 (fork) · ServiceOps FR/DE — BATCH 4 (Compliance + Parts, VERIFIED EN/DE, 0 leaks) ═══
User: "Bring ComplianceAdmin and PartsInventoryPage into the French/German rollout."
DONE (namespace `service`, full create_file rewrites, babel OK, guard OK, FR+DE translated):
  - ComplianceAdmin.js (comp_*, 48 keys) — PTW templates + COSHH register tabs. PtwAdmin/CoshhAdmin/ConfirmModal
    each got their own useTranslation. DraftListEditor now takes a `singular` prop (was slicing the label to get
    the singular — broke for DE), used for placeholder + "+ Add {item}".
  - PartsInventoryPage.js (parts_*, 93 keys) — Catalogue / Stock & reorder / Purchase orders tabs. CatalogueTab/
    StockTab/POTab each got useTranslation. Renamed the module-level TABS.map((t)) shadow -> (tb); tab labels
    render via t(`service.parts_tab_${tb.id}`, tb.label) — TEMPLATE-LITERAL keys, so seeded parts_tab_catalogue/
    stock/pos in the pipeline pairs.update() block (they are NOT statically scannable). Low-stock banner + on-hand
    line use interpolation.
Pipeline: run in BACKGROUND (foreground times out before merge). parts_tab_* were missing on the first run
  until added to the explicit dict — re-ran and confirmed present.
VERIFIED: testing_agent iteration_serviceops_comp_parts_i18n_fr_de_jan2026.json — 100% FE, 0 raw-key leaks in
  EN/DE on both screens + all tabs. FR key-parity confirmed (48 comp_ + 93 parts_ in en/fr/de). Demo account
  language reset to 'en'. Nav paths: Compliance = /service-desk left nav 'Compliance' (compliance-admin);
  Parts = left nav 'Stores'/'Lager' → subtab 'Pulse Warehouse' (desk-stores-sub-warehouse).
REMAINING ServiceOps/ (still EN via fallback, functional): AIScheduling, AdminDispatchBoard, ServiceCaseLifecycleTab,
  CommsHubPage, SafetyTemplateAdmin, PartsAllocator, EngineerRosterPanel, FindEngineerPanel, EquipmentMultiSelect,
  ServiceOpsShell chrome, Engineer/*, Inventory/*. Then nested Settings shared cards.
