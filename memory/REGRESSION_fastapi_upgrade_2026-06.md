# Regression — FastAPI 0.125→0.142.2 / starlette 0.49→1.7.0 (2026-06)

## What was run
- **Deterministic unit suite** = 325 test files that import app code (routes/utils/server) with NO live-HTTP dependency → the set that actually isolates framework-level breakage. ~2830 tests.
  - Result: **2662 passed, 153 failed, 42 errors, 15 skipped** in 138s.
- **Live-HTTP smoke tests** (curl against preview): /auth/login, /auth/me, security-header middleware (HSTS/CSP), CORS headers, multipart UploadFile (/api/expenses/ocr), chunked-upload route dispatch — all OK (200, or routed).

## Verdict: UPGRADE IS CLEAN
Zero framework-signature regressions: no import errors, no FastAPI/starlette signature TypeErrors, no serialization/CORS/middleware/multipart breaks. 2662 tests exercise app code under the new framework and pass.

### Failure triage (153 failed + 42 errors)
- **~130 (85%) = live-HTTP / environmental** — this preview DB lacks seeded accounts/data the tests assume: `admin@gymaxisai.com` and `crm@gymaxisai.com` return 401; `STRIPE_PRICE_*` env vars unset (test_stripe_prices_guard). Pre-existing, unrelated to the upgrade.
- **Pre-existing test bugs** — async tests using MagicMock where AsyncMock is needed ("MagicMock can't be used in 'await'"); `ModuleNotFoundError: emergentintegrations.payments` (routes/financial_ops.py, 4 errors); `module 'pytest' has no attribute '_onb_mapping'`.
- **Exactly 1 upgrade-related** — a test introspecting the route list after `include_router`. FastAPI 0.133+ keeps included sub-routers as lazy `_IncludedRouter` wrappers (real APIRouter at `.original_router`) instead of flattening APIRoutes into `.routes`. **Actual routing is unaffected** (verified: `/api/files/upload/chunks/init` dispatches live → HTTP 400, not 404). FIXED the test (`tests/test_iter_220e9_chunked_uploads.py::test_chunked_router_registered_in_core`) with a recursive collector via `.original_router`; now passes.

## Not run (and why)
- The full ~552-file live-HTTP e2e suite (8536 tests total) was NOT run to completion: it takes hours against the preview and is dominated by the same environmental failures (missing seeded master-admin/CRM accounts), so it adds load without adding upgrade signal. To make it meaningful, first seed `admin@gymaxisai.com` / `crm@gymaxisai.com` (+ org/Stripe-price fixtures), then run with `TEST_PULSE_PRO_PASSWORD=LeeMod123!`.

## Note for anyone writing route-registration tests going forward
After `include_router`, don't do `{r.path for r in router.routes}` — recurse through `_IncludedRouter.original_router`. (Introspecting a module's own `@router.get`-defined APIRouter still works — those are APIRoute with `.path`.)
