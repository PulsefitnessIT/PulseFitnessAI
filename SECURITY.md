# GymAxis AI — Security

## Reporting a vulnerability

Responsible disclosure is handled via the canonical
`security@gymaxisai.com` inbox. We publish the discovery policy at
`/.well-known/security.txt` (served from the frontend public folder).

## Hardening summary

| Area | Status | Notes |
|------|:------:|-------|
| JWT signing secret | ✅ | 64-hex random (iter 215ae). `.env` is git-ignored. `backend/.env.example` is the committed template. |
| Secrets startup audit | ✅ | `utils/secrets_audit.py` runs on every boot. Aborts in `APP_ENV=production` if a critical finding is present (short/weak JWT, missing Stripe webhook secret, wildcard CORS, weak admin pw). |
| Stripe webhook signatures | ✅ | `STRIPE_WEBHOOK_SECRET` is required in production (`memberships_payments.stripe_webhook`). Dev mode keeps the unsigned-payload path for Stripe CLI workflows. |
| Stripe Connect routing | ✅ | Member payments use **destination charges** into the gym's connected account, gated on `charges_enabled` + active `transfers` capability (`utils/stripe_connect_routing.py`); platform-account fallback otherwise. Engineer invoices use Direct Charges. Per-gym platform fee configurable by master-admin. |
| Secret sprawl | ✅ | `backend/.env.bak` / `backend/.env.live.bak` removed from the repo & index (iter 220y). `.env.*` is git-ignored. Note: full git-history purge requires a one-off history rewrite during a GitHub sync. |
| Rate-limiting on money endpoints | ✅ | `wallet_topup` (10/60s per member), `autopay_setup` (5/300s per member), `member_login_ip` (8/300s), `member_register_ip` (10/600s). Auth login + password reset already covered in `utils/security_plus.py`. |
| Cross-tenant IDOR | ✅ | All operator endpoints scope queries via `_require_operator_org(user)` → filter with `organization_id = org_id`. Locked in with 4 regression tests in `tests/test_security_regression_215af.py`. |
| Global 500 handler | ✅ | `server.py` exception handler returns a generic message; stack traces logged server-side only. No raw `str(exc)` reaches the client. |
| Dependency audit (Python) | ✅ | `pip-audit` 2026-05-01 — litellm upgraded 1.80.0 → 1.83.14 to close 3 CVEs (`CVE-2026-35029`, `CVE-2026-35030`, `GHSA-69x8-hrgq-fjj8`). `pip` itself has `CVE-2026-3219` (no fix yet; not in the runtime path). |
| Password hashing | ✅ | `passlib` with bcrypt for operators + members. |
| CORS | ⚠️ | Still a wildcard in dev. Set `CORS_ORIGINS` explicitly for production deploys. |
| CSP / security headers | ⚠️ | `SecurityHeadersMiddleware` adds HSTS / X-Frame-Options / X-Content-Type-Options. CSP allows `'unsafe-inline'` — acceptable today given the embedded Stripe / emoji widgets; can be tightened per-route. |

## Running the audit yourself

```bash
# Python vulns
cd /app/backend && pip-audit

# Node vulns
cd /app/frontend && yarn audit

# Unit tests for security regressions
cd /app/backend && python -m pytest tests/test_security_regression_215af.py tests/test_secrets_audit_215ae.py -v
```

## Generating a new JWT_SECRET

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Rotate by replacing `JWT_SECRET` in `backend/.env` and restarting
supervisor. **This logs everyone out** — plan the rotation window.
