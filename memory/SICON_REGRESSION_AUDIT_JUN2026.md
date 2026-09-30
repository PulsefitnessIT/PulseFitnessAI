# Sicon ⇄ PulseFitness.ai — Regression Audit (June 2026)

Ran before proceeding to Phase 2, to confirm recent work (read-side alignment,
case relationships, engineer mapping, case_equipment resolve, write-path
consolidation) did NOT break existing Sicon⇄Pulse links.

## Result: ZERO regressions.

### Positive proof — link-critical OFFLINE suites (no HTTP login): 110/110 PASS
test_sicon_readside, test_sicon_case_engine, test_sicon_import_engine,
test_sicon_deep_mapping, test_iter_220bi_sicon_field_mapping,
test_sicon_camelcase_inbound, test_iter_216h240_integration_field_capture,
test_orbit4_deep_mapping, test_iter_216h280_link_audit,
test_iter272_partner_relink_selfheal, and the 4 new Jun-2026 suites
(case_relationships, caseeq_resolve, engineer_mapping, bridge_consolidation).

### Live HTTP smoke on changed endpoints (owner account)
- POST /api/sicon/test-connection → 200
- GET  /api/sicon/priorities → 200
- GET  /api/sicon/read/engineer-mapping → 200
- GET  /api/sicon/read/conflicts?entity=case_equipment → 200
- POST /api/integrations/bridge/{id}/retry → 403 (correct: master-admin-gated; owner is manager)

## The broad run's 31 failures + 19 errors — all explained, none are regressions
1. **~23 = HTTP 429 auth-lockout.** Running many login-based suites back-to-back
   brute-force-locks the shared accounts (owner@isodemo.com, admin@gymaxisai.com,
   master admin) → "Account temporarily locked. Try again in N minutes." Purely
   environmental/test-ordering. Affected: test_iter_216h135_sicon_connect,
   test_iter_216h153_sicon_producers, test_iter_216h7_sicon_mapping_audit,
   test_integration_health, test_iter252_ops_portal_bridge, test_iter_216g_phase2.
2. **8 = pre-existing outdated WRITE tests.** test_sicon_service_webapi_v1 (6) +
   test_sicon_bruno_artifacts (2) expect Sicon writes to be *sent*, but the
   write-guard correctly refuses them because SICON_ALLOW_WRITES=false (Phase 1
   read-only). Confirmed pre-existing via git-baseline checkout of sicon_client.py;
   my changes never touched svc_create_case/svc_update_case/etc. or the .bru files.
   These tests should be updated to construct the client with allow_writes=True
   (or assert the guard) — noted as tech-debt, not a break.

## Method
- git auto-commits each step, so `git stash` finds nothing; baseline obtained by
  `git checkout <pre-work-commit> -- <file>` then restoring to HEAD.
- Pre-work commit boundary: sicon_* work began at 0a915d75; integrations.py
  consolidation at 4d11179d (prev 890b1daa).

## Follow-up tech-debt (not blocking)
- Update test_sicon_service_webapi_v1_jan2026.py + test_sicon_bruno_artifacts.py
  to reflect the write-guard (they predate strict SICON_ALLOW_WRITES enforcement).
- Login-based test suites should share a session token / bypass rate-limit in the
  test harness to avoid 429 cascades when run together.
