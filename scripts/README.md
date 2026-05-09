# Deploy guards

## `pre-deploy.sh` — run before every preview → production deploy

Verifies that the running configuration is safe to ship to live customers.

### What it checks

1. All `STRIPE_*` env vars are populated (no pod-stub placeholders).
2. `STRIPE_API_KEY` is `sk_live_*` (not test mode).
3. Secret-key mode and publishable-key mode match (no `sk_live_` + `pk_test_` mismatch).
4. All 12 Stripe Price IDs exist in Stripe and match the expected amount, interval, currency, and product (via `pytest tests/test_stripe_prices_guard_216o.py`).
5. The `/api/webhook/stripe` handler still passes its 4 offline tests (bad-signature reject, idempotency, subscription-deleted, dunning cycle).
6. MongoDB is reachable.
7. Frontend lint is clean.

### How to run

```bash
bash /app/scripts/pre-deploy.sh
```

Exits `0` if safe to deploy, `1` otherwise. Total runtime ~5 seconds.

### Bypass flags (use sparingly)

| Env var | Effect |
|---|---|
| `SKIP_LIVE_CHECK=1`       | Allow deploys with `sk_test_*` keys (preview/staging only). |
| `SKIP_FRONTEND_LINT=1`    | Skip the `yarn lint` step (only when you've already linted manually). |

### Wire-up suggestions

- **Manual habit**: run before clicking "Deploy to production" in the Emergent platform.
- **CI**: add as the first step of any production-deploy job; failure aborts the deploy.
- **Git pre-push hook** (optional): symlink to `.git/hooks/pre-push` if you push directly.


---

## `mobile-smoke.js` — catch mobile-layout regressions before redeploy

Walks the most-used Master Admin pages at a 414×900 viewport (iPhone-class)
and asserts the right rows surface user identity (name + email) without
their action buttons squeezing the content off-screen. Designed to catch
the iter 216bi class of "looks fine on desktop, broken on mobile" bugs.

### Run

```bash
NODE_PATH=/app/frontend/node_modules node /app/scripts/mobile-smoke.js
```

Optional flags:
- `--base=<url>` — override `REACT_APP_BACKEND_URL`
- `--email=<addr>` — override default master-admin email
- `--password=<pw>` — override default master-admin password

Exit code `0` if all checks pass (or skip due to empty data), `1` otherwise.

### Report

Writes `/app/test_reports/mobile_smoke_${timestamp}.json` for the
testing agent to pick up.

### Adding new pages

Append to the `PAGES` array. Each entry needs:
- `name`: display label
- `route`: SPA path (e.g. `/master-admin`)
- `setup(page)`: optional async fn to navigate to the right sub-tab
- `asserts`: array of `{ kind, selector }` — selector should match all
  rows that **must** be visible at this viewport. The runner fails if
  any matched element has zero width/height, and skips if zero rows
  match (interpretation: empty data, not a bug).

A horizontal-overflow detector (`scrollWidth - clientWidth ≤ 2px`) runs
on every page automatically.
