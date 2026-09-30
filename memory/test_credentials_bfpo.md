# BFPO / MOD Engineer Portal — test credentials

Portal URL (preview): {REACT_APP_BACKEND_URL}/bfpo
All BFPO logins require the backend `portal:"mod"` flag — the frontend BFPO login
page sends this automatically. Direct /api/auth/login calls must include `"portal":"mod"`.

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
