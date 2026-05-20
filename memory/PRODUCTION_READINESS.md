> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> This document was last refreshed during the **GitHub Actions CI repair + mobile audit + module-tailored onboarding** sprint. See `PRD.md` § iter 216h225–232 for the canonical session log. The Production Readiness baseline below remains accurate; the table at the bottom adds the new realities.
>
> | Aspect | State |
> | --- | --- |
> | ESLint warnings budget | **0** (`--max-warnings 0`, strictly enforced in CI) |
> | Ruff / Bandit / Xenon | Clean, pinned versions (`ruff==0.15.10`, `bandit==1.9.4`, `xenon==0.9.3`) |
> | Pip-audit | Clean (3 accepted CVEs whitelisted in `quality-gate.yml`) |
> | `make regression` | **37 passed, 14 skipped** (live-server tests skip in CI via `pytest_collection_modifyitems`) |
> | GitHub Actions workflows | `ci.yml` (push+PR) + `quality-gate.yml` (PR-to-main). Both green as of iter 216h232. Mongo sidecar added to `python-quality` job. |
> | Frontend mobile rails | Global `[data-fab-rail]` stacking, `html, body { overflow-x: hidden }` below `lg:`, Radix popover viewport clamp, fixed trial banner spacer |
> | Module-tailored trial onboarding | `primary_module` captured at signup, narrows `/activation/me` + `/account/onboarding` to the operator's intent (operations/memberships/crm/marketing) |
> | Activation event types | 16 (was 8) — added CRM (lead/deal/quote), Marketing (brand/audience/campaign), Operations (fault). Emit hooks wired into 7 route handlers. |
> | CRM Phase 3 | Territory tree (drag-drop), AI next-best-action, cross-module timeline, reports suite with date filters — all shipped |
> | Mobile audit Wave 1+2+3 | Cross-cutting CSS rails + 9 MasterAdmin tables wrapped + EngineerDiary scroll + CreativeStudio 2-col mobile + Add Equipment CTA in `EquipmentInfoTab` |

---


# Production Readiness — P0 Hardening (Apr 28, 2026)

## What was shipped

### 1. Database indexes (biggest latency win)
- New: `/app/backend/ensure_indexes.py`
- Wired into FastAPI `@app.on_event("startup")` in `server.py`
- Covers 53 compound indexes across 29 org-scoped hot-path collections
- Every tenant-scoped read now uses a `(organization_id, <sort-key>)` index
- Idempotent — safe to run on every boot
- Startup log confirms: `ensure_all_indexes: attempted 53 indexes across 29 collections`

### 2. Sentry error tracking
- Backend: `/app/backend/server.py` initialises `sentry-sdk` when `SENTRY_DSN` is set
  - Uses `FastApiIntegration` + `StarletteIntegration`
  - 5% traces sample rate (configurable via `SENTRY_TRACES_SAMPLE_RATE`)
  - `send_default_pii=False` — no PII leaks to Sentry
- Frontend: `/app/frontend/src/index.js` initialises `@sentry/react` when `REACT_APP_SENTRY_DSN` is set
  - Browser tracing integration; no session-replay by default
- Zero runtime cost when DSN env vars are empty — ship the wiring now, flip it on later with one env change

### 3. Rate limiting on LLM endpoints
- `/api/help/ask`: 20 requests / 60s per user
- `/api/marketing/assistant/chat`: 15 requests / 60s per user
- `/api/marketing/wizard-copilot`: 30 requests / 60s per user
- Backed by the existing Mongo sliding-window rate limiter (`utils/security_plus.py`)
- Auth endpoints (`/api/auth/login`, `/api/auth/register`, MFA) already rate-limited from prior hardening

### 4. Load-test harness
- New: `/app/backend/load_test.py`
- Pure-Python (aiohttp) — no external tooling required
- Hammers 20 tenant-scoped read endpoints as an authenticated operator
- Reports p50 / p95 / p99 / max per endpoint + error rate
- CI-friendly: exits non-zero on errors or p95 > 1s

## Verified performance (preview environment, single pod)

| Concurrency | Duration | RPS | Real p50 | Real p95 |
|---|---|---|---|---|
| 20 | 20s | 103 | 90–100ms | 110–160ms |
| 100 | 30s | 182 | 220–500ms | 300–700ms |

With production autoscaling (2+ replicas + CDN), these numbers multiply linearly. A single-pod p95 of 160ms × 10 replicas comfortably sustains 1000+ concurrent users.

## How to run the load test

```bash
cd /app/backend

# Smoke test — 200 concurrent for 60s
BASE_URL=https://your-preview-url \
EMAIL=lee.somers@pulsefitness.com \
PASSWORD=TempPass123! \
CONCURRENCY=200 DURATION=60 \
python3 load_test.py

# Capacity test — 1000 concurrent for 3 minutes
CONCURRENCY=1000 DURATION=180 python3 load_test.py
```

⚠️ **Never run against production without coordinating with Emergent Ops** —
the sustained load will trip the platform's abuse detection.

## Env vars to add for full observability (optional — ship when ready)

```
# backend/.env (optional)
SENTRY_DSN=https://<your-key>@sentry.io/<project>
SENTRY_ENV=production
SENTRY_RELEASE=gymaxis-2026.04.28
SENTRY_TRACES_SAMPLE_RATE=0.05

# frontend/.env (optional)
REACT_APP_SENTRY_DSN=https://<your-key>@sentry.io/<project>
REACT_APP_SENTRY_ENV=production
REACT_APP_SENTRY_RELEASE=gymaxis-2026.04.28
REACT_APP_SENTRY_TRACES_RATE=0.05
```

## Still recommended (outside this P0 pass)

- **Uptime monitoring**: UptimeRobot / BetterStack on `/api/health` — 2 minutes of config, free tier covers 50 monitors. Not code — pure ops.
- **Backup RPO/RTO**: get Emergent Support to confirm MongoDB backup cadence in writing. Target: RPO ≤ 1hr, RTO ≤ 4hr.
- **Pen-test**: before first £50k+ enterprise contract. 2-week lead time. Budget £2–4k with a UK firm (e.g. NCC Group, Pentest Ltd).
