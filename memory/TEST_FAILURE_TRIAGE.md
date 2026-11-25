# Regression failure triage — 2026-11-25

Run: `make regression` in preview (backend live at REACT_APP_BACKEND_URL). Result: **2443 passed, 159 failed, 41 errors, 26 skipped** (248 s).
Baseline evidence: the identical 201 failure IDs reproduced on an untouched worktree of commit 1036d3d3 (before the repo-wide lint changes) — none were introduced by the lint/MOD work.
Classified failure tracebacks: 147 (one test can emit more than one line).

| Category | Count | Severity | Owner | Fix path |
|---|---|---|---|---|
| A. Shared preview account locked / login rate-limited (auth setup) | 47 | Low (env) | QA / platform | Run with LOGIN_RATE_LIMIT_MAX=500 (as CI does) on an isolated DB; unlock test accounts between runs |
| B. Seeded test credential missing/changed or breached-password policy (auth setup) | 4 | Medium (test infra) | QA / platform | Re-seed test users via scripts; rotate breached-list test passwords |
| C. Outdated unit test: sync MagicMock for async code / calls route without DI (broken test) | 14 | Low (test) | QA / platform | Rewrite mocks with AsyncMock / call through ASGI client |
| D. Source-text assertion on superseded UI/brand copy (outdated test; behaviour changed by later iterations, e.g. GymAxis→Pulse rebrand, i18n files moved) | 46 | Low (test) | QA / platform | Update assertions to current copy with equivalent behavioural tests |
| E. Missing fixture data in shared preview DB (missing test fixture) | 19 | Medium (test infra) | QA / platform | Add per-test fixtures instead of relying on shared preview data |
| F. Permission matrix: test user lacks renewals.review (authorisation setup) | 0 | Low (test) | QA / platform | Grant renewals.review to the CRM test role in seed |
| Unclassified | 17 | Review | Engineering | see list below |

No failure in this set exercises MOD quotation pricing, MODService publication, Sicon write controls or financial posting — those are covered by passing suites (test_mod_ops_quotes.py 13/13, test_mod_quotes_http.py 13/13, Sicon/PPM suites).

## Unclassified

- `/app/backend/tests/test_iter_220aq_growth_hub_fixes.py:39: AssertionError: assert 'Visit https:...ess.ai today!' == 'Visit https:...ai.com today!'`
- `/app/backend/tests/test_iter_220aq_growth_hub_fixes.py:48: AssertionError: gym-axis.com not scrubbed: Try https://pulsefitness.ai for more`
- `/app/backend/tests/test_iter_220au_auth_hardening.py:36: AssertionError: assert 10080 == 15`
- `/app/backend/tests/test_iter_220au_auth_hardening.py:159: AssertionError: assert 403 == 401`
- `/app/backend/tests/test_iter_220ba_pre_pentest_polish.py:144: AssertionError: Handover-diary pin-to-first logic missing from StaffingConsole`
- `/app/backend/tests/test_iter_220bc_homepage_modules_consolidation.py:36: AssertionError: module id 'engineers' missing from MarketingHome.MODULES`
- `/app/backend/tests/test_iter_220bc_homepage_modules_consolidation.py:54: AssertionError: Engineers module missing required feature 'Job Routing'`
- `/app/backend/tests/test_iter_220bc_homepage_modules_consolidation.py:96: AssertionError: Engineers missing from top nav`
- `/app/backend/tests/test_iter_220bc_homepage_modules_consolidation.py:101: AssertionError: homepage badge must read 'Five modules'`
- `/app/backend/tests/test_iter_220be_pentest_final_hardening.py:224: AssertionError: Hard-coded credentials found in shipped backend code:`
- `/app/backend/tests/test_iter_220bh_doc_consistency_polish.py:124: AssertionError: Pack docs missing canonical finding phrasing ('33 risk-register findings (F-01`
- `/app/backend/tests/test_iter_220bl_social_autopilot.py:263: AssertionError: assert '#19cdff' == '#d946ef'`
- `/app/backend/tests/test_iter_220da_barcode_lookup.py:81: AssertionError: assert {'asset_tag',...sticker_code'} == {'asset_tag',...erial_number'}`
- `/app/backend/tests/test_iter_220da_barcode_lookup.py:102: AssertionError: assert 'exact' == 'fuzzy'`
- `/app/backend/tests/test_iter_220dy_server_modularisation.py:79: AssertionError: server.py grew back to 813 lines — refactor regressed`
- `/app/backend/tests/test_iter_220ea_30_engineer_recruit.py:101: AssertionError: no spec sheets found`
- `/app/backend/tests/test_iter_220p_my_gyms_queue.py:228: AssertionError: My-gyms pill must use the canonical navy→purple gradient — see /app/BRAND_PALETTE.md`
