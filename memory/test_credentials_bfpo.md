# BFPO / MOD Engineer Portal — test credentials

Portal URL (preview): {REACT_APP_BACKEND_URL}/bfpo
LOGIN: BFPO users sign in through the **MOD Service login screen** (the same
modservice.pulsefitness.com login the rest of MOD uses) — there is NO separate
BFPO login. That screen posts /api/auth/login with `portal:"mod"`; on success
resolveHomePath() routes any user whose `bfpo_role` is engineer/lead/staff
straight to /bfpo. The /bfpo app reuses the shared platform cookie session
(no separate token). Direct API calls must include `"portal":"mod"`.
On the preview domain, /MODService external-redirects to the production MOD
domain; to exercise the flow in preview, log in via the /api/auth/login API on
the preview origin (portal:mod) then open /bfpo.

## BFPO Engineer (Gibraltar-scoped)
- Email: engineer.gib@bfpo.pulsefitness.test
- Password: Bfpo123!
- Role: engineer · territory: Gibraltar

## BFPO Engineer (Cyprus-scoped)
- Email: engineer.cyp@bfpo.pulsefitness.test
- Password: Bfpo123!
- Role: engineer · territory: Cyprus (SBA)

## BFPO Lead Engineer (all territories)
- Email: lead@bfpo.pulsefitness.test
- Password: Bfpo123!
- Role: lead

## Pulse MOD Service Staff (UK, global oversight)
- Email: staff@bfpo.pulsefitness.test
- Password: Bfpo123!
- Role: staff

Re-seed demo data: `cd /app/backend && python -m scripts.seed_bfpo`
Rate-limit bypass header for automated login tests: `x-ratelimit-bypass: test-bypass-secret-for-ci-runs-only-2026`
