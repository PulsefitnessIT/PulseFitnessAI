# Domain Cutover Runbook — `gymaxisai.com` + `pulsefitness.ai`

This is the step-by-step play for moving the live app off the
`*.preview.emergentagent.com` host onto the two customer-facing domains.
Follow it top-to-bottom on cutover day.

> **Time required:** ~30 min hands-on. DNS propagation ~15 min after
> records are added.

---

## 1. DNS (do this first)

Add these records at your registrar. TTL: 300 seconds during cutover so
mistakes propagate fast — bump to 86400 once stable.

| Domain                | Type  | Name | Value                                     |
|-----------------------|-------|------|-------------------------------------------|
| `gymaxisai.com`       | A     | @    | `<Emergent prod ingress IP>`              |
| `gymaxisai.com`       | CNAME | www  | `gymaxisai.com.`                          |
| `gymaxisai.com`       | CNAME | app  | `<emergent app hostname>`                 |
| `pulsefitness.ai`     | A     | @    | `<Emergent prod ingress IP>`              |
| `pulsefitness.ai`     | CNAME | www  | `pulsefitness.ai.`                        |
| `pulsefitness.ai`     | CNAME | app  | `<emergent app hostname>`                 |

Plus optional MX records for transactional email (Resend):

| Domain                | Type  | Name | Value (per Resend dashboard)              |
|-----------------------|-------|------|-------------------------------------------|
| `gymaxisai.com`       | TXT   | @    | Resend domain-verify token                |
| `pulsefitness.ai`     | TXT   | @    | Resend domain-verify token                |

---

## 2. TLS certificates

Emergent's ingress should auto-provision Let's Encrypt certs once DNS
resolves. Verify with:

```bash
curl -sI https://app.gymaxisai.com   | head -1
curl -sI https://app.pulsefitness.ai | head -1
```

Both must return `HTTP/2 200` (or `HTTP/2 301` from the apex). If you see
a cert warning, contact Emergent Support — do **not** flip prod traffic.

---

## 3. Backend env vars (Emergent dashboard)

Set on the **production** environment of the FastAPI service:

```
ENVIRONMENT=production
FRONTEND_URL=https://app.gymaxisai.com
BRAND_URL_GYMAXIS=https://app.gymaxisai.com
BRAND_URL_PULSE=https://app.pulsefitness.ai

# Comma-separated. Exact match — protocol + host + (optional) port.
CORS_ORIGINS=https://app.gymaxisai.com,https://gymaxisai.com,https://www.gymaxisai.com,https://app.pulsefitness.ai,https://pulsefitness.ai,https://www.pulsefitness.ai
```

> **Note:** if `CORS_ORIGINS` is omitted in production, the app now
> falls back to the six brand defaults above — but explicit > implicit.

If using Sentry, also set:

```
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENV=production
SENTRY_TRACES_SAMPLE_RATE=0.05
```

If using Resend, also set:

```
RESEND_API_KEY=re_...
RESEND_FROM_GYMAXIS=GymAxis AI <hello@gymaxisai.com>
RESEND_FROM_PULSE=Pulse Fitness <hello@pulsefitness.ai>
```

---

## 4. Frontend env vars

Set in the React build environment **before** rebuilding the frontend:

```
REACT_APP_BACKEND_URL=https://app.gymaxisai.com
# Optional Sentry:
REACT_APP_SENTRY_DSN=https://...@sentry.io/...
REACT_APP_SENTRY_ENV=production
```

> The **single** `REACT_APP_BACKEND_URL` works for both brands because
> all customers hit the same FastAPI service — the brand split is only
> on the customer-facing domain that *serves* the SPA, not on the API
> origin. Pulse customers reach `https://app.pulsefitness.ai` and the
> SPA still calls `app.gymaxisai.com/api/*` (covered by CORS).

---

## 5. Trigger a fresh deploy

In Emergent dashboard → Deployments → "Redeploy" with the env above.
This rebuilds both backend (picks up the new `CORS_ORIGINS` and
`BRAND_URL_*` vars) and frontend (picks up the new
`REACT_APP_BACKEND_URL`).

---

## 6. One-shot data fixes

Run **once** after the new code lands:

```bash
# Clean up any HTML-entity-encoded strings from before iteration 205.
cd /app/backend
python scripts/fix_iteration204_data.py
```

Idempotent — safe to re-run.

---

## 7. Smoke test (5 min)

```bash
# 1. Health
curl -s https://app.gymaxisai.com/api/health
# → {"status":"ok"}

# 2. Login
curl -s -X POST https://app.gymaxisai.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<your-prod-admin>","password":"..."}'
# → {"access_token":"...", "user":{...}}

# 3. CORS pre-flight from a Pulse origin
curl -s -X OPTIONS https://app.gymaxisai.com/api/health \
  -H "Origin: https://app.pulsefitness.ai" \
  -H "Access-Control-Request-Method: GET" -i | head -5
# → HTTP/2 200, Access-Control-Allow-Origin: https://app.pulsefitness.ai
```

Then in a real browser:

- Visit `https://app.gymaxisai.com` → GymAxis landing page.
- Visit `https://app.pulsefitness.ai` → Pulse Fitness landing page.
- Log in to both via existing test accounts.
- Trigger a supplier-case email — confirm the "View & Reply" link uses
  the brand-correct domain.

---

## 8. Rollback plan

If smoke tests fail, point both domains' DNS records back to the old
preview hostname (or just unflip the apex A records — the SPA still
works on `*.preview.emergentagent.com` because nothing requires the
custom domain server-side). Drop the cutover env vars or set
`CORS_ORIGINS` back to the preview origin and redeploy.

DNS-level rollback completes in 5 minutes with TTL 300.

---

## 9. Post-cutover (T+1 day)

- Bump DNS TTL back to 86400.
- Confirm Sentry is receiving events from both brand origins.
- Confirm UptimeRobot / BetterStack monitors are green from at least
  three geographies on both `app.gymaxisai.com/api/health` and
  `app.pulsefitness.ai/api/health`.
- Update internal docs, customer-success runbook, and the Trust &
  Reliability "build hardening timeline" with the cutover date.
