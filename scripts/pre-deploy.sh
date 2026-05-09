#!/usr/bin/env bash
#
# pre-deploy.sh — Run before every preview→production deploy.
#
# Iter 216o-11 (Feb 2026) — protects against the "wrong env shipped to
# live" disaster (e.g. test keys leaking into production, or a Price ID
# drifting in Stripe Dashboard without the codebase noticing).
#
# What it checks (in order — fails fast):
#
#   0.  Iter-216 regression suite          → tests/test_iter_216c_*, 216bl, 216af
#   0b. ruff + bandit baseline             → backend/scripts/security-scan.sh
#   1.  STRIPE keys are present and not the pod-stub placeholders.
#   2.  STRIPE_API_KEY is sk_live_* (test keys must NEVER go to prod).
#   3.  All 12 Stripe Price IDs exist in Stripe and match the expected
#       amount/interval/product/currency  → tests/test_stripe_prices_guard_216o.py
#   4.  Webhook handler tests pass (signature validation, idempotency,
#       dunning state)                     → tests/test_stripe_integration_216o.py
#   5.  MONGO_URL is reachable.
#   6.  Frontend lint clean.
#
# Exit code:
#   0 = safe to deploy
#   1 = STOP — fix the failure before pushing live
#
# How to wire into your deploy flow:
#   - Manual: just run `bash /app/scripts/pre-deploy.sh` before clicking
#     "Deploy to production" in the platform UI.
#   - CI:     add a "Pre-deploy guard" job that calls this script.

set -euo pipefail

# ANSI colours (only when stdout is a TTY).
if [[ -t 1 ]]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; RESET=''
fi

ok()    { echo "${GREEN}✓${RESET}  $1"; }
fail()  { echo "${RED}✗  $1${RESET}"; exit 1; }
note()  { echo "${CYAN}»${RESET}  $1"; }
warn()  { echo "${YELLOW}!${RESET}  $1"; }

cd /app/backend

# ---------------------------------------------------------------------------
# 0) Iter-216 regression guard (cheap, no env deps, runs FIRST)
# ---------------------------------------------------------------------------
# Each suite below pins the contract for a recent production bug fix. If
# any of these fail, the bug they fixed is back. They run before the
# Stripe / live-mode checks because they are fast, free, and catch the
# most common class of regressions (auth, branding, site-lock, drift).
note 'Iter-216 regression suite — branding sync + site-lock + brand inheritance'
REGRESSION_SUITE=(
  tests/test_iter_216c_branding_org_sync.py     # iter-216c — name ↔ branding.company_name
  tests/test_iter_216bl_site_lock.py            # iter-216bl — server-side site-lock
  tests/test_iter_216af_brand_inheritance.py    # iter-216af — brand inheritance
)
python3 -m pytest "${REGRESSION_SUITE[@]}" -q --tb=line --no-header \
  || fail 'Iter-216 regression suite failed — a previously-fixed bug has resurfaced. See test output above.'
ok 'Iter-216 regressions pinned (branding sync, site-lock, brand inheritance)'

# ---------------------------------------------------------------------------
# 0b) Security + lint baseline (ruff + bandit)
# ---------------------------------------------------------------------------
if [[ "${SKIP_SECURITY_SCAN:-0}" == 1 ]]; then
  warn 'SKIP_SECURITY_SCAN=1 — bypassing ruff + bandit baseline'
else
  note 'ruff + bandit baseline (Medium+ findings fail the deploy)'
  bash /app/backend/scripts/security-scan.sh > /tmp/predeploy-security.log 2>&1 \
    || { cat /tmp/predeploy-security.log; fail 'ruff or bandit reported a regression. Review /tmp/predeploy-security.log.'; }
  ok 'ruff clean · bandit 0 High / 0 Medium'
fi

# Force .env to take precedence over pod stubs (matches utils/database.py
# behaviour at runtime).
note "Loading /app/backend/.env (overrides pod env)"
set -a
# shellcheck disable=SC1091
source <(python3 -c "
from dotenv import dotenv_values
for k, v in dotenv_values('/app/backend/.env').items():
    if v is not None:
        # bash export-safe escaping for embedded single quotes
        v = v.replace(\"'\", \"'\\\\''\")
        print(f\"export {k}='{v}'\")
")
set +a

# ---------------------------------------------------------------------------
# 1) STRIPE keys present
# ---------------------------------------------------------------------------
note "Checking STRIPE_* env vars"
[[ -n "${STRIPE_API_KEY:-}" ]]           || fail 'STRIPE_API_KEY is empty'
[[ -n "${STRIPE_PUBLISHABLE_KEY:-}" ]]   || fail 'STRIPE_PUBLISHABLE_KEY is empty'
[[ -n "${STRIPE_WEBHOOK_SECRET:-}" ]]    || fail 'STRIPE_WEBHOOK_SECRET is empty'
[[ "$STRIPE_API_KEY" != 'sk_test_emergent' ]] || fail 'STRIPE_API_KEY is the pod placeholder (sk_test_emergent)'
ok 'Stripe API/webhook keys are set'

# ---------------------------------------------------------------------------
# 2) Live mode required for production deploys
# ---------------------------------------------------------------------------
if [[ "${SKIP_LIVE_CHECK:-0}" == 1 ]]; then
  warn 'SKIP_LIVE_CHECK=1 — bypassing sk_live check (use only for preview deploys)'
elif [[ "$STRIPE_API_KEY" == sk_live_* ]]; then
  ok 'Stripe is in LIVE mode'
else
  fail "Stripe is in TEST mode (key prefix: ${STRIPE_API_KEY:0:8}...). Restore from .env.live.bak before deploying to production. (Set SKIP_LIVE_CHECK=1 to deploy preview/staging.)"
fi

# Publishable key mode must match secret key mode.
if [[ "$STRIPE_API_KEY" == sk_live_* && "$STRIPE_PUBLISHABLE_KEY" != pk_live_* ]]; then
  fail 'Mode mismatch: STRIPE_API_KEY=sk_live_… but STRIPE_PUBLISHABLE_KEY is not pk_live_…'
fi
if [[ "$STRIPE_API_KEY" == sk_test_* && "$STRIPE_PUBLISHABLE_KEY" != pk_test_* ]]; then
  fail 'Mode mismatch: STRIPE_API_KEY=sk_test_… but STRIPE_PUBLISHABLE_KEY is not pk_test_…'
fi
ok 'Secret/publishable key modes match'

# ---------------------------------------------------------------------------
# 3) All 12 Price IDs valid in Stripe + match expected catalogue
# ---------------------------------------------------------------------------
note 'Verifying all 12 Stripe Price IDs against live Stripe API'
python3 -m pytest tests/test_stripe_prices_guard_216o.py -q --tb=line --no-header \
  || fail 'One or more Stripe Price IDs failed validation. See test output above.'
ok 'All 12 Price IDs match the expected catalogue'

# ---------------------------------------------------------------------------
# 4) Webhook handler tests (offline — no live API hits)
# ---------------------------------------------------------------------------
note 'Running offline webhook handler tests'
python3 -m pytest tests/test_stripe_integration_216o.py -q --tb=line --no-header -k offline \
  || fail 'Stripe webhook handler tests failed. The /api/webhook/stripe handler is in a broken state.'
ok 'Webhook handler tests pass (signature validation, idempotency, dunning)'

# ---------------------------------------------------------------------------
# 5) MongoDB reachable
# ---------------------------------------------------------------------------
note 'Pinging MongoDB'
python3 - <<'PYEOF' || fail 'Could not reach MongoDB'
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000)
    await client.admin.command('ping')
    client.close()
asyncio.run(main())
PYEOF
ok 'MongoDB reachable'

# ---------------------------------------------------------------------------
# 6) Frontend lint
# ---------------------------------------------------------------------------
if [[ "${SKIP_FRONTEND_LINT:-0}" == 1 ]]; then
  warn 'SKIP_FRONTEND_LINT=1 — bypassing frontend lint'
else
  # Iter 216c — scope eslint to files actually changed in HEAD so the
  # gate catches "you broke the file you just edited" without dragging
  # in 535 pre-existing errors / 5,696 warnings of legacy debt across
  # the whole `frontend/src` tree. Allows warnings; fails only on
  # genuine errors (parse failures, undefined globals, etc.) in the
  # diff.
  cd /app
  CHANGED_JS=$(git diff --name-only HEAD~1 HEAD -- 'frontend/src/**/*.js' 'frontend/src/**/*.jsx' 2>/dev/null || true)
  if [[ -z "$CHANGED_JS" ]]; then
    note 'No frontend JS/JSX changes in HEAD — skipping focused eslint'
    ok 'Frontend lint skipped (no diff)'
  else
    note "Linting changed frontend files in HEAD: $(echo "$CHANGED_JS" | wc -l) file(s)"
    if (cd /app/frontend && yarn -s eslint $(echo "$CHANGED_JS" | sed 's|^frontend/||g') > /tmp/predeploy-lint.log 2>&1); then
      ok 'Frontend lint clean for changed files'
    else
      cat /tmp/predeploy-lint.log
      fail 'Frontend lint failed for files changed in HEAD. Fix the errors above or set SKIP_FRONTEND_LINT=1 to bypass.'
    fi
  fi
  cd /app/backend
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "${GREEN}════════════════════════════════════════════════════════════${RESET}"
echo "${GREEN}  ✅  PRE-DEPLOY GUARD PASSED — safe to deploy${RESET}"
echo "${GREEN}════════════════════════════════════════════════════════════${RESET}"
echo "  Stripe mode:       $([[ "$STRIPE_API_KEY" == sk_live_* ]] && echo "LIVE" || echo "TEST")"
echo "  Stripe API key:    ${STRIPE_API_KEY:0:12}…${STRIPE_API_KEY: -4}"
echo "  Webhook secret:    ${STRIPE_WEBHOOK_SECRET:0:12}…"
echo "  Backend status:    ready"
echo "  Frontend lint:     $([[ "${SKIP_FRONTEND_LINT:-0}" == 1 ]] && echo "skipped" || echo "clean")"
echo ""
exit 0
