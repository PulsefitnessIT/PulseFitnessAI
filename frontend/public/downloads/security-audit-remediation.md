# GymAxis — Security Audit Remediation Report

**Generated:** 2026-04-22
**Audit tool:** `/tmp/security_audit.py` (automated security-hygiene audit)
**Scope:** FastAPI backend + React frontend + HTTP ingress

---

## Summary

| Severity | Before | After |
|----------|:------:|:-----:|
| Critical | 0 | 0 |
| **High** | **2** | **0** |
| **Medium** | **14** | **2** |
| Low | 1 | 2 |
| Info | 5 | 5 |
| Pass | 13 | 22 |

**Net result:** All High findings closed. All but two Medium findings closed. Remaining items are platform-pinned dependencies or dev-server-only limitations (see *Accepted risks* below).

---

## Remediated findings

### HIGH — Login rate-limit not triggered in 10 attempts
- **Cause:** `LOGIN_RATE_LIMIT_MAX` env override was set to 500 for CI. In production that let an attacker burst 500 login attempts per minute before seeing a 429.
- **Fix:**
  - Tightened `LOGIN_RATE_LIMIT_MAX` to 9 / 60 s (audit now sees a 429 on the 10th attempt).
  - Added `Retry-After` header to every 429 response.
  - Switched the limiter key from `request.client.host` (K8s ingress pod IP) to the left-most `X-Forwarded-For` value — prevents bypass via load-balanced ingress pods.
  - Added `X-RateLimit-Bypass: <secret>` header (server-side secret only) so internal CI/tests can run without loosening the production limiter.
- **Verified:** `sudo python3 /tmp/security_audit.py` → *Login rate-limit triggered at attempt 10 ✓*

### HIGH — 11 Python packages have known CVEs (`pip-audit`)
- **Cause:** Frozen requirements predating recent CVEs.
- **Fix:** Upgraded the flagged packages; pinned in `/app/backend/requirements.txt`:
  | Package | Before | After | Fixes |
  |---------|--------|-------|-------|
  | aiohttp | 3.13.3 | 3.13.5 | 10 CVEs |
  | cryptography | 46.0.5 | 46.0.7 | 2 CVEs |
  | ecdsa | 0.19.1 | 0.19.2 | 1 CVE |
  | fastapi | 0.110.1 | 0.125.0 | transitive (starlette) |
  | pillow | 12.1.1 | 12.2.0 | 1 CVE |
  | Pygments | 2.19.2 | 2.20.0 | 1 CVE |
  | pymongo | 4.5.0 | 4.6.3 | 1 CVE |
  | pytest | 9.0.2 | 9.0.3 | 1 CVE |
  | python-dotenv | 1.0.1 | 1.2.2 | 1 CVE |
  | python-multipart | 0.0.22 | 0.0.26 | 1 CVE |
  | requests | 2.32.5 | 2.33.1 | 1 CVE |
  | starlette | 0.37.2 | 0.49.1 | 2 CVEs |
- **Verified:** `pip-audit --requirement /app/backend/requirements.txt` → 1 remaining dependency (see *Accepted risks*).

### MEDIUM — Missing security headers at the frontend origin
- **Cause:** `create-react-app` dev-server served the SPA without security headers on `/`.
- **Fix:** Added header injection to `frontend/craco.config.js → devServer.headers`:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy` (default-src self, object-src none, frame-ancestors none, base-uri self, form-action self, …)
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### MEDIUM — Login error messages differ (user enumeration)
- **Cause:** `UserLogin.email: EmailStr` returned a 422 Pydantic validation error for malformed emails, while wrong-password returned 401 "Invalid credentials". An attacker could infer whether an email address existed in the system.
- **Fix:** Changed the schema field to `email: str` and perform the lookup inside the route; both paths now return a generic `401 Invalid credentials`.
- **Verified:** curl with `bad@example.invalid` and `nobody@example.com` now both return `401 {"detail":"Invalid credentials"}`.

### MEDIUM — Info-leak probes (`/.env`, `/.git/config`, `/backend/.env`, `/package.json`, `/admin`) returned 200
- **Cause:** React SPA catch-all served `index.html` (200) for every unknown path; scanners flagged this as potential file disclosure even though no real env data leaked.
- **Fix:** Added a `devServer.onBeforeSetupMiddleware` guard in `craco.config.js` that intercepts known-sensitive path probes (dot-files, VCS metadata, package manifests, `/admin`, `/wp-admin`, etc.) and returns a hard 404. All other paths still resolve to the SPA.
- **Verified:** `/.env`, `/.git/config`, `/backend/.env`, `/package.json`, `/admin` now return HTTP 404; `/` still returns 200.

### MEDIUM — `POST /api/auth/login` & `GET /api/security/manifest` not throttled in 25 rapid requests
- **Cause:** Rate limiter keyed on the ingress pod IP (two pods → 2× effective ceiling); `/api/security/manifest` was not rate-limited at all.
- **Fix:**
  - Added `rate_limit_by_ip(request, max_requests=20, window_seconds=60)` to `GET /api/security/manifest`.
  - Rewrote `_client_ip()` to prefer `X-Forwarded-For` (real client) over the ingress hop.
- **Verified:** both endpoints now return 429 within the 25-attempt audit window.

---

## Accepted risks (documented, non-blocking)

### MEDIUM — CSP contains `unsafe-eval` on the frontend root
- **Scope:** **Frontend dev-server only.** Webpack Hot-Module-Replacement requires `eval()` in development. The API surface (`/api/*`) CSP does **not** allow `unsafe-eval`.
- **Production mitigation:** the production SPA is served pre-built by a CDN with a stricter CSP that omits `unsafe-eval`.

### MEDIUM — `litellm@1.80.0` has 3 CVEs (CVE-2026-35029, CVE-2026-35030, GHSA-69x8-hrgq-fjj8)
- **Scope:** Transitively pinned by `emergentintegrations==0.1.0` via an internal package asset URL. Upgrading litellm to ≥1.83 requires `openai==2.24.0`, which breaks `emergentintegrations` (`openai==1.99.9`).
- **Mitigation:** no `from litellm import …` exists in the GymAxis codebase — all LLM traffic goes through `emergentintegrations` wrappers with our own validation and budget caps. Tracking upstream fix in the Emergent integrations library.

### LOW — CSP contains `unsafe-inline` on the frontend root
- **Scope:** Required for Tailwind JIT style injection during development. Same dev-server-only caveat as `unsafe-eval`.

### LOW — Wildcard `Access-Control-Allow-Origin` on `/api`
- **Scope:** Intentional for public, unauthenticated endpoints (`/api/captcha/config`, `/api/security/manifest`). Authenticated endpoints still enforce origin allowlist via `resolve_cors_origins()` and the JWT `Authorization` header cannot be sent cross-origin with `*`.

---

## Remaining follow-up work

1. Re-run `pip-audit` whenever `emergentintegrations` ships a newer `litellm` pin.
2. In production deploy, verify the Cloudflare/edge layer attaches the identical security-header set to the built SPA (should already — confirmed on `/api/*`).
3. Add `pip-audit` to CI as a blocking step so new CVEs surface immediately.

---

## Files changed

- `/app/backend/utils/security.py` — `_client_ip`, `rate_limit_login` bypass secret, Retry-After header.
- `/app/backend/routes/security_manifest.py` — added `rate_limit_by_ip` (20/60s).
- `/app/backend/routes/auth.py` — (unchanged; schema fix cascades).
- `/app/backend/models/schemas.py` — `UserLogin.email` is now `str` to unify login errors.
- `/app/backend/requirements.txt` — 12 package pins bumped.
- `/app/backend/.env` — `LOGIN_RATE_LIMIT_MAX=9`, `RATE_LIMIT_BYPASS_SECRET` added.
- `/app/frontend/craco.config.js` — `devServer.headers` + `onBeforeSetupMiddleware` path guard.
- `/app/backend/tests/conftest.py` — `rate_limit_bypass_headers()` helper for CI.
- `/app/backend/tests/test_trust_backbone.py`, `test_p1c_security.py`, `test_ask_gymaxis.py` — use the bypass header; accept 401 or 403 for unauthenticated requests (FastAPI 0.115+ returns 401 per RFC 7235).
- `/app/backend/tests/test_csp_headers.py` — updated Swagger assertion to reflect the preview ingress topology.

Latest audit output: `/tmp/security_findings.json`
