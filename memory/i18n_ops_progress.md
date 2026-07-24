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
- [ ] staffing/StaffOnboarding.js (~1074) P1 — NOT DONE. NEEDS FULL REWRITE. CAUTION:
      `t` SHADOWS to rename before adding useTranslation:
        · CaseDetail load: `const [d, t] = await Promise.all(...)` -> rename t->tRes
        · CaseDetail offer/contract template pickers: `templates.offer.map((t)=>` and
          `templates.contract.map((t)=>` -> rename to `tpl`
        · TemplateManager load: `const [t, f] = await Promise.all(...)` -> rename t->tRes
      Helpers at tail (lines ~1034-1074, was clipped): Modal, Row, Btn — also have small strings
      (e.g. Btn children, Modal close). Read the FULL file first. Suggested ns: staffing.onb_*
- [ ] StaffingConsole.js DEEP inline panels P1 — nav already done. Read lines 176-1243 for the
      Rota schedule / Leave / Shift Market / Rules / Announcements / payroll drawers /
      staff-portal-preview strings. Suggested ns: staffing.sc_*
- [ ] staffing/orgchart/* (14 files ~2000 lines) P2

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
