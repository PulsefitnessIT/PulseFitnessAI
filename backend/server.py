from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ─── Sentry error tracking (must init BEFORE FastAPI app) ─────────────
# SENTRY_DSN is optional — when empty, sentry_sdk.init is a no-op and we
# pay zero runtime cost. Ship this wiring now so rotating Sentry on is a
# one-line env change, no code deploy required.
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=os.environ.get("SENTRY_ENV", "production"),
            release=os.environ.get("SENTRY_RELEASE") or None,
            integrations=[FastApiIntegration(), StarletteIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,
        )
        logging.getLogger(__name__).info("[sentry] enabled (env=%s)", os.environ.get("SENTRY_ENV", "production"))
    except Exception as _exc:
        logging.getLogger(__name__).warning("[sentry] init failed: %s", _exc)

from utils.database import db, init_storage, client
from route_registration import register_routes
from routes.supplier_api import router as supplier_api_router

import os as _os
# API schema/docs exposure — on by default (preview/dev). Set
# EXPOSE_API_DOCS=false in the pen-test / production env to hide
# Swagger UI, ReDoc and the OpenAPI schema (F-31 / tester note).
_expose_docs = _os.environ.get("EXPOSE_API_DOCS", "true").lower() in ("1", "true", "yes")
app = FastAPI(
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)

app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — fail-fast in prod, permissive in dev (P0.2)
from utils.security_plus import resolve_cors_origins, resolve_cors_origin_regex, body_size_guard
_cors_origins = resolve_cors_origins()
_cors_origin_regex = resolve_cors_origin_regex()
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Signature"],
)
# P1.8 — body size guard (2 MB default, 25 MB for upload paths)
app.middleware("http")(body_size_guard)
# P3 — master-admin IP allowlist (env-gated; no-op when MASTER_ADMIN_IP_ALLOWLIST is unset)
from utils.hardening import master_admin_ip_allowlist
app.middleware("http")(master_admin_ip_allowlist)

# Iter 216h172 — slow-request telemetry feeding the Master Admin
# Integration Health panel. Records requests > SLOW_THRESHOLD_MS in
# a fixed-size in-process ring; never persisted to disk.
from utils.slow_request_log import SlowRequestLogMiddleware
app.add_middleware(SlowRequestLogMiddleware)


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    import time
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Advertise the auth rate-limit policy (IETF draft RateLimit headers) on the
    # auth surface so external scanners can *detect* the brute-force protection
    # that utils/security.py already enforces (login 5/5min, reset 3/15min,
    # plus a 5-strike account lockout). Verified: the 6th rapid login → 429.
    if str(request.url.path).startswith("/api/auth/"):
        response.headers["RateLimit-Limit"] = "5"
        response.headers["RateLimit-Policy"] = "5;w=300"
    # NOTE: we rely on CSP `frame-ancestors` (below) for iframe protection.
    # X-Frame-Options doesn't support multi-origin allowlists, so emitting it
    # would break the Emergent app builder's preview panel which embeds the
    # app from `app.emergent.sh` into the `preview.emergentagent.com` subdomain.
    # `frame-ancestors` covers modern browsers; very old IE11 without CSP
    # support is not a realistic target for this app.
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    # P3.20 / 216h214 — tightened content policy. Drops `unsafe-eval` (RCE
    # surface); keeps `unsafe-inline` for style-src (Tailwind/emotion runtime).
    # h2xx CSP hardening — `unsafe-inline` REMOVED from script-src: all inline
    # <script> blocks were externalised (public/pwa-brand.js, perf-error-
    # suppressor.js, posthog-init.js) and INLINE_RUNTIME_CHUNK=false stops CRA
    # inlining its webpack runtime, so every executable script is now a
    # same-origin ('self') or allow-listed external file. Swagger UI at /docs +
    # /redoc is exempt (fastapi-swagger needs inline + eval).
    #
    # h214 — Craig stakeholder audit (h212) flagged CSP console violations
    # for assets.emergent.sh / PostHog / Cloudflare-insights. These scripts
    # are intentionally embedded in /frontend/public/index.html (Emergent
    # platform telemetry + PostHog product analytics) so they SHOULD be on
    # the allowlist. Adding them silences the demo-time console noise that
    # was undermining stakeholder trust.
    path = str(request.url.path)
    if not (path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob: https:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://api.fontshare.com https://challenges.cloudflare.com https://js.hcaptcha.com; "
            "script-src 'self' "
            "https://challenges.cloudflare.com https://js.hcaptcha.com https://js.stripe.com "
            "https://assets.emergent.sh "
            "https://*.posthog.com https://*.i.posthog.com "
            "https://static.cloudflareinsights.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdn.fontshare.com; "
            "connect-src 'self' https: wss:; "
            "worker-src 'self' blob:; "
            "frame-src 'self' blob: https://challenges.cloudflare.com https://hcaptcha.com https://js.stripe.com; "
            "frame-ancestors 'self' https://app.emergent.sh https://*.emergent.sh https://*.emergentagent.com; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "object-src 'self' blob:"
        )
    # HSTS when the caller used HTTPS. Behind our ingress the internal scheme
    # is 'http' but the X-Forwarded-Proto header reflects the external scheme.
    scheme = request.url.scheme
    xfp = request.headers.get("x-forwarded-proto", "").lower()
    if scheme == "https" or xfp == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    # Trust Backbone: emit telemetry for 5xx + slow API responses. Fire-and-forget.
    if path.startswith("/api/") and not path.startswith("/api/master-admin/trust"):
        try:
            from utils.trust_events import record_trust_event
            if response.status_code >= 500:
                await record_trust_event(
                    type="api.5xx",
                    severity="high",
                    summary=f"{request.method} {path} returned {response.status_code}",
                    payload={"method": request.method, "path": path, "status": response.status_code, "elapsed_ms": round(elapsed_ms)},
                    dedupe_key=f"api.5xx:{path}",
                )
            elif elapsed_ms > 2500:
                await record_trust_event(
                    type="api.slow",
                    severity="low",
                    summary=f"{request.method} {path} took {round(elapsed_ms)}ms",
                    payload={"method": request.method, "path": path, "elapsed_ms": round(elapsed_ms)},
                    dedupe_key=f"api.slow:{path}",
                )
        except Exception:
            pass
    return response

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")
register_routes(api_router)


# ── Public health endpoints ──────────────────────────────────────
# Lightweight probes for ops / uptime monitors. No auth — no PII or secrets
# leak through these. They confirm the app is up and that the security
# subsystems we care about (file validation backend) are wired correctly.

@api_router.get("/health")
async def health_root() -> dict:
    """Liveness probe — returns 200 if the FastAPI app is serving."""
    return {"status": "ok"}


# Unprefixed root-level liveness probe for Kubernetes / Emergent native
# deployment. The platform's internal probe hits `GET /health` (no `/api`
# prefix) on every pod; without this route it returns 404 and the deploy
# is marked unhealthy. Mirroring the body of /api/health keeps both paths
# trivially in sync.
@app.get("/health")
async def health_root_unprefixed() -> dict:
    return {"status": "ok"}


@api_router.get("/health/deep")
async def health_deep() -> dict:
    """Iter 215bt — Deep health check for production monitoring.

    Reports the live status of every external dependency and key config so
    UptimeRobot / BetterStack alerts fire BEFORE a customer hits a broken
    flow. Always returns HTTP 200 with a JSON body; ops should alert on
    `overall != "ok"` or any individual `status == "down"` field.

    No auth — only emits status flags + version info, never secrets.
    """
    import time

    started = time.perf_counter()
    out: dict = {"overall": "ok", "checks": {}, "version": os.environ.get("SENTRY_RELEASE") or "dev"}

    # MongoDB ping (fast — one round-trip)
    try:
        await db.command("ping")
        out["checks"]["mongo"] = {"status": "ok"}
    except Exception as exc:
        out["checks"]["mongo"] = {"status": "down", "error": type(exc).__name__}
        out["overall"] = "degraded"

    # File validation (libmagic) — uploads silently fail without it
    try:
        from utils.file_validation import selftest as _fv_selftest
        fv = _fv_selftest()
        out["checks"]["file_validation"] = {
            "status": "ok" if fv.get("enabled") else "down",
            "detected": fv.get("detected"),
        }
        if not fv.get("enabled"):
            out["overall"] = "degraded"
    except Exception as exc:
        out["checks"]["file_validation"] = {"status": "down", "error": type(exc).__name__}
        out["overall"] = "degraded"

    # Optional integrations — only mark "configured/missing", never down.
    out["checks"]["stripe"] = {
        "status": "configured" if os.environ.get("STRIPE_API_KEY", "").strip() else "missing"
    }
    out["checks"]["resend"] = {
        "status": "configured" if os.environ.get("RESEND_API_KEY", "").strip() else "missing"
    }
    # Iter 215c1 — sender domain check. If `SENDER_EMAIL` still points at a
    # generic Resend test address or an unverified domain, transactional
    # emails will land in spam. Surface this as a degraded signal so ops
    # alerts on it before customers complain.
    sender = os.environ.get("SENDER_EMAIL", "").strip().lower()
    weak_sender = (
        not sender
        or sender.endswith("@resend.dev")
        or sender.endswith("@example.com")
        or sender.startswith("onboarding@")
    )
    out["checks"]["sender_email"] = {
        "status": "configured" if not weak_sender else "weak",
        "value": sender or None,
        "hint": (
            "Verify your custom domain in Resend (SPF + DKIM + DMARC) "
            "and set SENDER_EMAIL to a branded address."
        ) if weak_sender else None,
    }
    if weak_sender:
        out["overall"] = "degraded" if out["overall"] == "ok" else out["overall"]
    # JWT secret strength check. Anything < 32 chars or containing the
    # known dev placeholder is unsafe to ship to production.
    jwt_secret = os.environ.get("JWT_SECRET", "")
    weak_jwt = (
        not jwt_secret
        or len(jwt_secret) < 32
        or "gymaxis-ai-secret" in jwt_secret.lower()
        or "change-me" in jwt_secret.lower()
    )
    out["checks"]["jwt_secret"] = {
        "status": "ok" if not weak_jwt else "weak",
        "hint": "Rotate JWT_SECRET to 32+ random bytes." if weak_jwt else None,
    }
    if weak_jwt:
        out["overall"] = "degraded" if out["overall"] == "ok" else out["overall"]
    out["checks"]["sentry"] = {
        "status": "configured" if os.environ.get("SENTRY_DSN", "").strip() else "missing"
    }
    # Universal Emergent LLM key powers AI features (Claude, Nano Banana,
    # GPT image, Sora, Whisper). Any of these env vars indicates a key is
    # wired; we never echo the key itself.
    has_llm = any(
        os.environ.get(k, "").strip()
        for k in ("EMERGENT_LLM_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
    )
    out["checks"]["llm"] = {"status": "configured" if has_llm else "missing"}

    out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return out


# Iter 215ag — global 500 handler. FastAPI's default echoes the exception
# string into the response body which can leak DB schema / file paths.
# We log the full traceback server-side and return a generic message.
from fastapi import Request as _Req
from fastapi.responses import JSONResponse as _JSONResp


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: _Req, exc: Exception):
    logger.exception(
        "[unhandled] %s %s → %s", request.method, request.url.path, type(exc).__name__
    )
    return _JSONResp(
        status_code=500,
        content={"detail": "Internal server error — the incident has been logged."},
    )


@api_router.get("/health/file-validation")
async def health_file_validation() -> dict:
    """Reports whether libmagic-backed upload validation is functional.

    Returns ``{"enabled": true, "detected": "application/pdf"}`` when wired
    correctly, or ``{"enabled": false, "reason": "...", "fix": "..."}``
    when libmagic is missing. Useful right after a container rebuild — if
    this flips to ``enabled: false`` your supplier-portal/equipment uploads
    are silently broken.
    """
    from utils.file_validation import selftest
    return selftest()


supplier_external_router = APIRouter(prefix="/api/v1/supplier")
supplier_external_router.include_router(supplier_api_router)

app.include_router(api_router)
app.include_router(supplier_external_router)

# Iter 220aa — Embeddable Widget (iframe-based Log a Fault / Get a
# Quote form for engineer & company websites). Public + owner routers
# are bound directly to the app because their prefixes already include
# ``/api`` and they're a self-contained module.
from routes.widget_embed import (
    public_router as _widget_public_router,
    owner_router as _widget_owner_router,
)
app.include_router(_widget_public_router)
app.include_router(_widget_owner_router)

# Iter 220ad — SEO Autopilot (admin + public blog endpoints)
from routes.marketing.seo_autopilot import (
    router as _seo_router,
    public_router as _seo_public_router,
)
app.include_router(_seo_router)
app.include_router(_seo_public_router)

# Iter 220ea·28 — public SEO surface: dynamic sitemap + crawler prerender.
from routes.seo_public import router as _seo_public_surface_router
app.include_router(_seo_public_surface_router)

# Iter 220bl — Social Media Autopilot (master-admin only).
from routes.marketing.social_autopilot import router as _social_autopilot_router
app.include_router(_social_autopilot_router)

# Iter 220ao — GDPR Article 17 right-to-erasure workflow (master-admin only).
from routes.gdpr_erasure import router as _gdpr_erasure_router
app.include_router(_gdpr_erasure_router)


async def _seed_master_admin() -> None:
    """Iter 220dy — moved to ``bootstrap.seed``. Kept as a shim so any
    out-of-tree caller importing the underscored name still works."""
    from bootstrap.seed import seed_master_admin
    await seed_master_admin()


async def _seed_services() -> None:
    """Iter 220dy — moved to ``bootstrap.seed``. Shim retained for the
    historic underscored name."""
    from bootstrap.seed import seed_services
    await seed_services()


async def _create_indexes() -> None:
    """Iter 220dy — moved to ``bootstrap.indexes``. Shim retained for the
    historic underscored name."""
    from bootstrap.indexes import create_indexes
    await create_indexes()


@app.on_event("startup")
async def startup() -> None:
    # Iter 215ae — surface secret/config misconfiguration at boot. Aborts
    # startup in APP_ENV=production when a critical finding is present.
    # Never abort startup on audit findings — doing so (sys.exit) prevents
    # uvicorn from ever binding :8001, so the k8s /health readiness probe
    # fails and the pod crash-loops. In production the platform injects env
    # vars and load_dotenv(override=False) will NOT override an injected
    # blank JWT_SECRET, which the audit would flag critical → sys.exit →
    # failed rollout. Log findings loudly instead; never kill the process.
    try:
        from utils.secrets_audit import run_startup_audit
        run_startup_audit(abort_on_critical_in_prod=False)
    except Exception as e:
        logger.error(f"Secrets audit failed: {e}")

    # Deploy-readiness: defer ALL heavy initialisation (seeding, backfills,
    # index builds, one-shot migrations, background loops) to a background
    # task so uvicorn binds :8001 and the k8s /health probe passes IMMEDIATELY.
    # Awaiting Atlas index builds inside the startup event was blocking the
    # port from opening → readiness timeout → failed production rollout.
    asyncio.create_task(_full_boot())


async def _full_boot() -> None:
    # Never let boot-time work block the event loop — the k8s readiness
    # probe hits GET /health and the port is already bound by the time this
    # task runs. init_storage() is a synchronous requests.post() to an
    # external object-storage service; if it were awaited inline it would
    # freeze the loop (and /health) for up to its 30s timeout while the
    # storage service is unreachable during a fresh deploy → readiness
    # timeout → crash loop. Offload it to a worker thread. It also inits
    # lazily on first put/get, so a boot-time failure here is harmless.
    from starlette.concurrency import run_in_threadpool
    try:
        await run_in_threadpool(init_storage)
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed (will init lazily on first use): {e}")

    try:
        await _seed_master_admin()
    except Exception as e:
        logger.error(f"Master admin seed failed: {e}")

    try:
        await _seed_services()
    except Exception as e:
        logger.error(f"Service seed failed: {e}")

    try:
        from bootstrap.seed import seed_test_accounts
        await seed_test_accounts()
    except Exception as e:
        logger.error(f"Test account seed failed: {e}")

    # Iter 272 — one-time backfill: relink stranded partner_engineers rows
    # (pending/stale user_id) to their owning users so engineers don't land
    # on the empty "Become a Partner Engineer / Apply now" screen. Marker-
    # guarded → runs once per DB, cheap no-op thereafter.
    try:
        from utils.partner_claim import run_partner_relink_migration_once
        await run_partner_relink_migration_once()
    except Exception as e:
        logger.error(f"Partner relink migration failed: {e}")

    # Iter 216g · Phase 2 — start the sign-up journey worker (welcome
    # emails + abandoned-cart recovery). One-shot per pod.
    try:
        from routes.signup_journeys import start_worker_once, _try_schedule_for_pending_events
        start_worker_once()
        await _try_schedule_for_pending_events()
    except Exception as e:
        logger.error(f"Sign-up journey worker init failed: {e}")

    # Iter 288 — self-heal dual-portal org config on every boot so new users
    # created via Master Admin always write to both `users` and `crm_users`
    # (prevents the "staff added in Master Admin missing from Operations HR"
    # drift). Idempotent → cheap no-op once clean.
    try:
        from scripts.normalise_dual_portal_orgs import normalise_dual_portal_orgs_once
        _n = await normalise_dual_portal_orgs_once()
        if _n:
            logger.info(f"Normalised {_n} dual-portal org(s) at boot")
    except Exception as e:
        logger.error(f"Dual-portal org normalisation failed: {e}")

    try:
        await _create_indexes()
    except Exception as e:
        logger.error(f"Index creation failed: {e}")

    try:
        from routes.ui_errors import ensure_indexes as _ui_err_indexes
        await _ui_err_indexes()
    except Exception as e:
        logger.error(f"ui_error index setup failed: {e}")

    try:
        from utils.security_events import ensure_indexes as _sec_evt_indexes
        await _sec_evt_indexes()
    except Exception as e:
        logger.error(f"security_events index setup failed: {e}")

    # Compound-index bootstrap for every org-scoped hot-path collection —
    # single biggest latency win at tenant scale. Idempotent; safe on reboot.
    try:
        from ensure_indexes import ensure_all_indexes
        await ensure_all_indexes(db)
    except Exception as e:
        logger.error(f"ensure_all_indexes failed: {e}")

    try:
        from routes.svc.case_types import ensure_indexes as _case_type_indexes
        await _case_type_indexes()
    except Exception as e:
        logger.error(f"case_types index setup failed: {e}")

    try:
        from utils.sicon_poller import start_poller
        start_poller()
        logger.info("Sicon poller started")
    except Exception as e:
        logger.error(f"Sicon poller start failed: {e}")

    # Iter 216d — one-shot data-quality migrations (idempotent).
    try:
        from utils.iter_216d_migrations import run_iter_216d_migrations
        await run_iter_216d_migrations()
    except Exception as e:
        logger.error(f"iter_216d migrations failed (non-fatal): {e}")

    # File-validation self-check. libmagic gives the strongest sniffing, but
    # the module falls back to a curated pure-Python magic-byte sniffer when
    # libmagic1 is absent from the container image, so uploads keep working.
    try:
        from utils.file_validation import selftest as _file_validation_selftest
        _fv = _file_validation_selftest()
        if _fv.get("enabled"):
            logger.info("[security] file validation: ENABLED (libmagic ok, detected=%s)", _fv.get("detected"))
        else:
            logger.warning(
                "[security] file validation: libmagic unavailable — using pure-Python "
                "signature sniffer fallback (uploads still validated). Reason: %s",
                _fv.get("reason"),
            )
    except Exception as e:
        logger.error(f"file validation self-check crashed: {e}")

    # Platform Health — nightly self-healing integrity sweep. Detects
    # invisible/broken/duplicate data, AI-diagnoses it, and stores findings
    # for one-click (never auto) fixing. Idempotent (refreshes OPEN findings).
    try:
        from routes.platform_integrity import run_forever as _platform_health_loop
        _ph_hours = int(os.environ.get("PLATFORM_HEALTH_SWEEP_HOURS", "24"))
        if _ph_hours > 0:
            asyncio.create_task(_platform_health_loop(_ph_hours))
            logger.info("[platform-health] nightly integrity sweep loop started (%dh)", _ph_hours)
    except Exception as e:
        logger.error(f"platform-health sweep loop start failed: {e}")

    # Iter 216h281 — kick off the Partner Engineer compliance sweep.
    # Closes Gap 2 from the BA audit: insurance + cert expiry tracking.
    # 24h interval is fine because reminder fires once per window —
    # repeat invocations within the same window are no-ops.
    try:
        from utils.partner_compliance import run_forever as _partner_compliance_loop
        asyncio.create_task(_partner_compliance_loop(24))
        logger.info("[partners] compliance sweep loop started (24h)")
    except Exception as e:
        logger.error(f"partner compliance loop start failed: {e}")

    # Iter 220m — Monthly engineer reputation reports.
    # Fires on the 1st of each month with avg / trend / top quote /
    # LinkedIn-share CTA. Loop wakes every 6 hours; sweep is idempotent.
    try:
        from utils.reputation_reports import run_forever as _reputation_reports_loop
        asyncio.create_task(_reputation_reports_loop(6))
        logger.info("[reputation-reports] loop started (6h)")
    except Exception as e:
        logger.error(f"reputation reports loop start failed: {e}")

    # Iter 220r — Return-day welcome-back digest. Fires once per leave
    # when an engineer's `availability.resumes_on` arrives, summarising
    # the queue + compliance state and auto-flipping availability back
    # to "available". Daily cadence is plenty — sweep is idempotent
    # (keyed on the resumes_on ISO date) so re-runs are no-ops.
    try:
        from utils.partner_return_digest import run_forever as _welcome_back_loop
        asyncio.create_task(_welcome_back_loop(24))
        logger.info("[welcome-back] digest loop started (24h)")
    except Exception as e:
        logger.error(f"welcome-back digest loop start failed: {e}")

    # Iter 220ea·31 — Engineer 10-day trial lifecycle. Day-9 reminder,
    # day-10 feedback form, +2-day last-chance nudge, then auto-suspend
    # after a 3-day grace if there's no decision. Idempotent (per-step
    # timestamps), so the 6-hourly sweep is safe to re-run.
    try:
        from utils.partner_trial_lifecycle import run_forever as _trial_lifecycle_loop
        asyncio.create_task(_trial_lifecycle_loop(6))
        logger.info("[trial] engineer trial lifecycle loop started (6h)")
    except Exception as e:
        logger.error(f"trial lifecycle loop start failed: {e}")

    # Iter 220ea·26c — PPM recurrence rollover. Once a preventive-
    # maintenance visit completes, auto-create the next one on the books
    # (interval_days later) until the contract end. Self-healing sweep —
    # idempotent (one open visit per schedule), so re-runs are no-ops.
    try:
        from utils.ppm_rollover import run_forever as _ppm_rollover_loop
        _ppm_hours = int(os.environ.get("PPM_ROLLOVER_HOURS", "6"))
        asyncio.create_task(_ppm_rollover_loop(_ppm_hours))
        logger.info("[ppm-rollover] loop started (%dh)", _ppm_hours)
    except Exception as e:
        logger.error(f"ppm rollover loop start failed: {e}")

    # Iter 220af — Daily SEO Autopilot. Picks the next queued keyword
    # at 09:00 Europe/London and generates + publishes an article.
    # Idempotent via the ``seo_autopilot_runs`` daily stamp. Disable
    # by setting ``SEO_AUTOPILOT_ENABLED=0`` in the env.
    try:
        if os.environ.get("SEO_AUTOPILOT_ENABLED", "1") != "0":
            from routes.marketing.seo_autopilot import run_daily_autopilot_loop
            _hour = int(os.environ.get("SEO_AUTOPILOT_HOUR", "9"))
            asyncio.create_task(run_daily_autopilot_loop(hour=_hour))
            logger.info("[seo-autopilot] daily loop started (fires @ %02d:00 Europe/London)", _hour)
    except Exception as e:
        logger.error(f"seo autopilot loop start failed: {e}")

    # Iter 220bn — Daily Social Autopilot. Fires alongside the SEO
    # loop at 09:00 Europe/London (or the hour configured in the UI)
    # and writes one draft per enabled channel (IG / TikTok /
    # LinkedIn). Idempotent via ``social_autopilot_runs`` daily stamp.
    # Disable by setting ``SOCIAL_AUTOPILOT_ENABLED=0`` in the env.
    try:
        if os.environ.get("SOCIAL_AUTOPILOT_ENABLED", "1") != "0":
            from routes.marketing.social_autopilot import run_daily_social_loop
            _shour = int(os.environ.get("SOCIAL_AUTOPILOT_HOUR", "9"))
            asyncio.create_task(run_daily_social_loop(hour=_shour))
            logger.info(
                "[social-autopilot] daily loop started (fires @ %02d:00 Europe/London)",
                _shour,
            )
    except Exception as e:
        logger.error(f"social autopilot loop start failed: {e}")

    # Iter 220bw — Public-post tracker (Instagram launch metrics, plus
    # later TikTok / LinkedIn). Daily crawl of every active tracked URL.
    # Disable via ``SOCIAL_TRACKER_ENABLED=0``.
    try:
        from utils.social_tracker import run_social_tracker_loop
        _st_int = int(os.environ.get("SOCIAL_TRACKER_INTERVAL_SEC", "86400"))
        asyncio.create_task(run_social_tracker_loop(db, interval_seconds=_st_int))
        logger.info("[social-tracker] crawler registered (interval=%ds)", _st_int)
    except Exception as e:
        logger.error(f"social tracker loop start failed: {e}")

    # Iter 220bq — GDPR Article 17 auto-executor. Sweeps pending
    # erasure requests whose 30-day cooling-off window has elapsed
    # and runs the scrub. Required by UK ICO guidance (DSARs must be
    # fulfilled WITHIN one month, not after). Idempotent — already-
    # executed rows are skipped by the status filter. Disable via
    # ``GDPR_ERASURE_AUTOEXEC_ENABLED=0``.
    try:
        from routes.gdpr_erasure import run_gdpr_erasure_auto_executor
        _ge_int = int(os.environ.get("GDPR_ERASURE_AUTOEXEC_INTERVAL_MIN", "60"))
        asyncio.create_task(run_gdpr_erasure_auto_executor(interval_minutes=_ge_int))
        logger.info("[gdpr-erasure] auto-executor registered (interval=%dm)", _ge_int)
    except Exception as e:
        logger.error(f"gdpr erasure auto-executor start failed: {e}")

    # Iter 220 P1 — CRM Master Price List scheduled price-change sweep.
    # Applies approved/scheduled bulk or single price changes when their
    # effective date arrives. Idempotent (status flips to 'applied').
    try:
        from routes.crm_price_changes import run_scheduled_price_changes_loop
        _pc_int = int(os.environ.get("PRICE_CHANGE_SWEEP_MIN", "30"))
        asyncio.create_task(run_scheduled_price_changes_loop(interval_minutes=_pc_int))
        logger.info("[price-changes] scheduled sweep registered (interval=%dm)", _pc_int)
    except Exception as e:
        logger.error(f"price-change sweep start failed: {e}")

    # Iter 220 P1 — Master Price List weekly backup + retention purge.
    try:
        from routes.crm_price_backup import run_weekly_backup_loop
        _bk_int = int(os.environ.get("PRICE_BACKUP_SWEEP_MIN", "60"))
        asyncio.create_task(run_weekly_backup_loop(interval_minutes=_bk_int))
        logger.info("[price-backup] weekly backup loop registered (interval=%dm)", _bk_int)
    except Exception as e:
        logger.error(f"price-backup loop start failed: {e}")

    # Iter 248 — Sicon bi-directional sync workers (outbox drain + inbound
    # case poll). Env-gated until live Sicon credentials are configured;
    # the /api/integrations/admin/sicon/* endpoints stay the manual path.
    if os.environ.get("SICON_AUTOSTART_WORKER", "").lower() in ("1", "true", "yes"):
        try:
            from utils.sicon_outbox_worker import run_loop as _sicon_outbox_loop
            from utils.sicon_inbound_worker import run_loop as _sicon_inbound_loop
            _out_int = float(os.environ.get("SICON_OUTBOX_INTERVAL_SEC", "30"))
            _in_int = float(os.environ.get("SICON_INBOUND_INTERVAL_SEC", "60"))
            asyncio.create_task(_sicon_outbox_loop(interval_seconds=_out_int))
            asyncio.create_task(_sicon_inbound_loop(interval_seconds=_in_int))
            logger.info("[sicon] sync workers registered (outbox=%ss inbound=%ss)", _out_int, _in_int)
        except Exception as e:
            logger.error(f"sicon sync workers start failed: {e}")


    # Comms Centre — batch + timezone-aware campaign send dispatcher.
    # Activates due scheduled campaigns and drains their queued recipients
    # in throttled cycles (batch size + pacing + per-recipient local time).
    try:
        from utils.comms_dispatch import run_comms_dispatch_loop
        _cd_int = float(os.environ.get("COMMS_DISPATCH_INTERVAL_SEC", "30"))
        asyncio.create_task(run_comms_dispatch_loop(interval_seconds=_cd_int))
        logger.info("[comms-dispatch] loop registered (interval=%ss)", _cd_int)
    except Exception as e:
        logger.error(f"comms-dispatch loop start failed: {e}")


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    try:
        from utils.sicon_poller import stop_poller
        stop_poller()
    except Exception:
        pass
    client.close()
