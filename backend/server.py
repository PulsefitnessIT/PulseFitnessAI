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

app = FastAPI()

app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — fail-fast in prod, permissive in dev (P0.2)
from utils.security_plus import resolve_cors_origins, body_size_guard
_cors_origins = resolve_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
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
    # surface); keeps `unsafe-inline` for style-src (Tailwind/emotion runtime)
    # and script-src (third-party SDKs like Turnstile/hCaptcha inject inline
    # bootstrap code). Swagger UI at /docs + /redoc is exempt because
    # fastapi-swagger needs eval.
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
            "script-src 'self' 'unsafe-inline' "
            "https://challenges.cloudflare.com https://js.hcaptcha.com https://js.stripe.com "
            "https://assets.emergent.sh "
            "https://*.posthog.com https://*.i.posthog.com "
            "https://static.cloudflareinsights.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdn.fontshare.com; "
            "connect-src 'self' https: wss:; "
            "frame-src 'self' https://challenges.cloudflare.com https://hcaptcha.com https://js.stripe.com; "
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

# Iter 220ao — GDPR Article 17 right-to-erasure workflow (master-admin only).
from routes.gdpr_erasure import router as _gdpr_erasure_router
app.include_router(_gdpr_erasure_router)


async def _seed_master_admin() -> None:
    """Seed/heal master admin account on every startup.

    The seed is **self-healing**: on every boot we make sure the master
    admin's password matches the `MASTER_ADMIN_PASSWORD` env var, clear
    any lockouts / temp-password flags, and ensure `is_master_admin=True`.
    This means a fresh deployment is always recoverable: just set
    `MASTER_ADMIN_PASSWORD` in the deployment env (or rely on the
    documented default) and the user can always sign in.

    Set `MASTER_ADMIN_RESET_ON_BOOT=0` to opt out (e.g. once you've
    rotated the admin password through the UI and want it to stick).
    """
    from utils.auth import hash_password
    from utils.security import clear_failed_logins
    import uuid
    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
    master_pwd = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
    reset_on_boot = os.environ.get("MASTER_ADMIN_RESET_ON_BOOT", "1") != "0"
    existing = await db.users.find_one({"email": master_email})
    if not existing:
        admin_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": org_id, "name": "GymAxis AI Admin",
            "subscription_tier": "premium",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.users.insert_one({
            "id": admin_id, "email": master_email,
            "full_name": "Master Admin",
            "password": hash_password(master_pwd),
            "role": "owner", "organization_id": org_id,
            "is_master_admin": True,
            "active": True,
            "must_change_password": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Master admin seeded: {master_email}")
        return

    set_doc = {"is_master_admin": True, "active": True}
    if reset_on_boot:
        set_doc.update({
            "password": hash_password(master_pwd),
            "must_change_password": False,
            "temp_password_expires_at": None,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        })
    await db.users.update_one(
        {"email": master_email},
        {"$set": set_doc, "$unset": {"lockout_until": ""}},
    )
    # Also drop any in-memory rate-limit lockout against this email so a
    # fresh deploy after a brute-force test doesn't lock the admin out.
    clear_failed_logins(master_email)

    # Iter 216h272 — self-heal the master admin's home org if the
    # org doc was deleted out from under the user (data-wipe scripts,
    # restored backups, partial migrations). Without this guard the
    # operator-facing `/api/me/module-trials` endpoint 404s and the
    # whole Memberships / CRM / Marketing module pages render the
    # raw "Organisation not found" string. Verified live: master
    # admin + every Pulse Fitness user share org id 9fa701ef-... and
    # all five module pages failed when the org doc went missing.
    org_id = existing.get("organization_id")
    if org_id:
        org_doc = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1})
        if not org_doc:
            await db.organizations.insert_one({
                "id": org_id,
                "name": "GymAxis AI Admin",
                "account_type": "full",
                "subscription_tier": "premium",
                "modules": {
                    "memberships": {"enabled": True, "source": "seed"},
                    "crm": {"enabled": True, "source": "seed"},
                    "marketing": {"enabled": True, "source": "seed"},
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.warning(
                "Master admin org doc %s was missing — re-seeded so module pages can render", org_id,
            )

    if reset_on_boot:
        logger.info(f"Master admin healed (password re-synced): {master_email}")
    else:
        logger.info(f"Master admin verified (password reset on boot disabled): {master_email}")


async def _seed_services() -> None:
    """Seed integrations and CRM admin."""
    from routes.integrations import seed_integrations
    await seed_integrations()
    from routes.crm_auth import seed_crm_admin
    await seed_crm_admin()
    logger.info("CRM admin seeded")
    # Iter 216h223 — CRM Picklists global defaults + Stakeholder map indexes.
    # Iter 216h224 — CRM Products (master price list) indexes.
    try:
        from routes.crm_picklists import seed_global_picklists
        from routes.crm_stakeholders import ensure_stakeholder_indexes
        from routes.crm_products import ensure_product_indexes
        from routes.crm_website_recognize import ensure_website_cache_indexes
        from utils.tenant_mirror import ensure_tenant_mirror_indexes, mirror_pulse_tenants_to_crm
        from routes.incidents import ensure_incident_indexes
        await seed_global_picklists()
        await ensure_stakeholder_indexes()
        await ensure_product_indexes()
        await ensure_website_cache_indexes()
        await ensure_tenant_mirror_indexes()
        await ensure_incident_indexes()
        # Iter 216h276 — mirror Pulse tenants into the master admin's
        # CRM so paying customers (Pulse Fitness Limited, Third Space)
        # show up in CRM Companies. Idempotent on every boot.
        try:
            await mirror_pulse_tenants_to_crm()
        except Exception:
            logger.exception("tenant mirror reconciliation failed (non-fatal)")
        logger.info("CRM picklists + stakeholder + products indexes ready")
    except Exception as e:  # pragma: no cover
        logger.warning("CRM picklists / stakeholder / products seed failed (non-fatal): %s", e)
    # MOD demo tree (idempotent) — disabled in fresh-platform mode
    if os.environ.get("ENABLE_DEMO_SEED", "0") == "1":
        try:
            from utils.mod_seed import seed_mod_demo, ensure_mod_indexes
            await ensure_mod_indexes()
            await seed_mod_demo()
            logger.info("MOD demo tree seeded")
        except Exception as e:  # pragma: no cover
            logger.warning("MOD demo seed failed: %s", e)
    # GymAxis Memberships — indexes always; demo seed only when ENABLE_DEMO_SEED=1
    try:
        from routes.memberships import ensure_memberships_indexes
        await ensure_memberships_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships index ensure failed: %s", e)
    try:
        from routes.memberships_phase4 import ensure_phase4_indexes
        await ensure_phase4_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships Phase 4 index ensure failed: %s", e)
    try:
        from routes.memberships_phase6 import ensure_phase6_indexes
        await ensure_phase6_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships Phase 6 index ensure failed: %s", e)
    try:
        from routes.master_admin_pricing import ensure_pricing_indexes
        from routes.master_admin_billing import ensure_org_billing_indexes
        from routes.activation_events import ensure_activation_indexes
        from routes.master_admin_documents_lib import ensure_documents_indexes
        from routes.invoice_share import ensure_invoice_share_indexes
        from routes.email_health import ensure_email_send_events_indexes
        from routes.triage_feedback import ensure_triage_attempts_indexes
        await ensure_pricing_indexes()
        await ensure_org_billing_indexes()
        await ensure_activation_indexes()
        await ensure_documents_indexes()
        await ensure_invoice_share_indexes()
        await ensure_email_send_events_indexes()
        await ensure_triage_attempts_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Pricing / billing index ensure failed: %s", e)
    if os.environ.get("ENABLE_DEMO_SEED", "0") == "1":
        try:
            from utils.memberships_seed import seed_memberships_demo
            from utils.memberships_analytics_seed import seed_memberships_analytics_demo
            await seed_memberships_demo()
            await seed_memberships_analytics_demo()
            logger.info("Memberships demo seeded")
        except Exception as e:  # pragma: no cover
            logger.warning("Memberships seed failed: %s", e)


async def _create_indexes() -> None:
    """Create MongoDB indexes for performance."""
    # Core indexes
    await db.issues.create_index([("organization_id", 1), ("created_at", -1)])
    await db.issues.create_index([("organization_id", 1), ("status", 1)])
    await db.issues.create_index("user_id")
    await db.equipment.create_index([("organization_id", 1)])
    await db.equipment.create_index("serial_number")
    await db.files.create_index([("organization_id", 1), ("category", 1)])
    await db.files.create_index([("content_hash", 1)])
    await db.files.create_index([("supplier_name", 1)])
    await db.users.create_index("email", unique=True)
    await db.users.create_index("organization_id")
    await db.suppliers.create_index("organization_id")
    await db.risk_assessments.create_index("organization_id")
    await db.gym_layouts.create_index("organization_id")
    await db.check_sheet_history.create_index([("organization_id", 1), ("created_at", -1)])
    await db.purchase_orders.create_index([("organization_id", 1), ("created_at", -1)])
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token")
    # Iter 220as — Stripe webhook idempotency (event_id unique + 30-day TTL).
    try:
        from utils.stripe_idempotency import ensure_indexes as _ensure_stripe_idemp
        await _ensure_stripe_idemp()
    except Exception:
        pass
    # Iter 220at — AI guardrails (token-usage rollup + ai_actions audit).
    try:
        from utils.ai_guardrails import ensure_indexes as _ensure_ai_guardrails
        await _ensure_ai_guardrails()
    except Exception:
        pass
    # CRM indexes
    await db.crm_users.create_index("email", unique=True)
    await db.crm_contacts.create_index([("email", 1)])
    await db.crm_contacts.create_index([("company_id", 1)])
    await db.crm_contacts.create_index([("created_at", -1)])
    await db.crm_deals.create_index([("stage", 1)])
    await db.crm_deals.create_index([("pipeline_id", 1)])
    await db.crm_deals.create_index([("contact_id", 1)])
    await db.crm_activities.create_index([("contact_id", 1), ("created_at", -1)])
    await db.crm_activities.create_index([("deal_id", 1)])
    await db.crm_audit_log.create_index([("created_at", -1)])
    await db.crm_conversations.create_index([("status", 1), ("updated_at", -1)])
    await db.crm_conversations.create_index([("assigned_to", 1)])
    await db.crm_messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.crm_meetings.create_index([("contact_id", 1), ("created_at", -1)])
    await db.crm_workflows.create_index([("active", 1), ("trigger.type", 1)])
    await db.crm_workflow_logs.create_index([("workflow_id", 1), ("executed_at", -1)])
    await db.crm_quotes.create_index([("status", 1), ("created_at", -1)])
    await db.crm_quotes.create_index([("contact_id", 1)])
    await db.crm_integrations.create_index([("type", 1)], unique=True)
    # Service Desk indexes
    await db.service_desk_audit_log.create_index([("timestamp", -1)])
    await db.service_desk_audit_log.create_index([("actor_id", 1), ("timestamp", -1)])
    await db.service_desk_audit_log.create_index([("target_type", 1), ("target_id", 1)])
    await db.users.create_index("is_service_desk")
    # Trust Backbone indexes
    from utils.trust_events import ensure_trust_event_indexes
    await ensure_trust_event_indexes()
    # Support audit indexes (SOC 2 / ISO 27001 evidence stream)
    from utils.support_audit import ensure_support_audit_indexes
    await ensure_support_audit_indexes()
    from routes.support_escalate import ensure_support_escalate_indexes
    await ensure_support_escalate_indexes()
    # Iter 216h75 — Partner Engineer Network indexes
    from routes.partners import ensure_partner_indexes
    await ensure_partner_indexes()
    # Iter 220aa — Embeddable Widget (iframe Log-a-Fault) indexes
    from routes.widget_embed import init_widget_embed_indexes
    await init_widget_embed_indexes()
    # Iter 220ad — SEO Autopilot indexes
    from routes.marketing.seo_autopilot import init_seo_indexes
    await init_seo_indexes()
    # Iter 216h140 — Engineer Diary indexes
    from routes.svc.diary import ensure_diary_indexes
    await ensure_diary_indexes()
    # Iter 216h142 — Notifications indexes
    from routes.svc.notifications import ensure_notification_indexes
    await ensure_notification_indexes()
    # Iter 216h144 — Engineer independence indexes
    from routes.svc.independence import ensure_independence_indexes
    await ensure_independence_indexes()
    # Iter 216h146 — Inbound email log indexes
    from routes.svc.inbound_email import ensure_inbound_email_indexes
    await ensure_inbound_email_indexes()
    # Iter 216h259 — Engineer Lite CRM indexes
    from routes.svc.engineer_customers import ensure_indexes as ensure_engineer_customer_indexes
    await ensure_engineer_customer_indexes()
    # Iter 220 — Work Report custom fields indexes
    from routes.svc.work_report_fields import ensure_indexes as ensure_work_report_fields_indexes
    await ensure_work_report_fields_indexes()
    # Iter 220c — Engineer job-draft autosave (unique per engineer×case)
    await db.svc_engineer_job_drafts.create_index(
        [("organization_id", 1), ("engineer_id", 1), ("case_id", 1)],
        unique=True,
        name="svc_engineer_job_drafts_unique",
    )
    # Iter 220d — Per-machine reports + note presets
    from routes.svc.per_machine_reports import ensure_indexes as ensure_per_machine_indexes
    await ensure_per_machine_indexes()
    # Iter 220g — Postcode geocode cache
    from routes.svc.scheduling_suggestions import ensure_indexes as ensure_scheduling_indexes
    await ensure_scheduling_indexes()
    # Security hardening indexes (rate-limit TTL, JWT revocations, LLM budgets)
    from utils.security_plus import ensure_security_indexes
    await ensure_security_indexes()
    # MFA replay-protection indexes
    from utils.mfa import ensure_mfa_indexes
    await ensure_mfa_indexes()
    # SSO indexes (state TTL + unique link)
    from utils.sso import ensure_sso_indexes
    await ensure_sso_indexes()
    # Digest preferences index
    from utils.digest import ensure_digest_indexes
    await ensure_digest_indexes()

    # ───────────────────────────────────────────────────────────────
    # Tier-2 performance indexes (added Apr 2026)
    # Every `.find().sort()` in routes/ was audited; collections that
    # sorted without a matching compound index were hitting in-memory
    # sort on large collections. These indexes let the optimiser stream
    # results directly from the B-tree (~10-100× faster on collections
    # with >10 k docs). Safe to create — MongoDB no-ops if the index
    # already exists with the same definition.
    # ───────────────────────────────────────────────────────────────
    # Equipment list sorted by created_at per org
    await db.equipment.create_index([("organization_id", 1), ("created_at", -1)])
    # Audits per-equipment history view
    await db.audits.create_index([("equipment_id", 1), ("created_at", -1)])
    # Master admin org + user listings
    await db.organizations.create_index([("created_at", -1)])
    await db.users.create_index([("created_at", -1)])
    await db.crm_users.create_index([("created_at", -1)])
    # Admin activity & analytics streams
    await db.admin_activity_log.create_index([("timestamp", -1)])
    # Integration observability (logs + bridge records)
    await db.integration_logs.create_index([("timestamp", -1)])
    await db.integration_bridge.create_index([("created_at", -1)])
    # Supplier portal case timeline
    await db.supplier_cases.create_index([("created_at", -1)])
    await db.supplier_case_comments.create_index([("case_id", 1), ("created_at", 1)])
    # CRM v2 contracts + activities
    await db.crm2_contracts.create_index([("created_at", -1)])
    await db.crm2_activities.create_index([("created_at", -1)])
    # Purchase orders: most common query is emailed=true sorted by date
    await db.purchase_orders.create_index([("emailed", 1), ("created_at", -1)])
    # Files with dedupe hash lookup
    await db.files.create_index([("organization_id", 1), ("created_at", -1)])
    try:
        await db.sicon_engineers.create_index([("organization_id", 1), ("is_leaver", 1)])
        await db.sicon_engineers.create_index([("organization_id", 1), ("post_code_area", 1)])
        await db.sicon_engineers.create_index([("id", 1)], unique=True)
        await db.organizations.create_index([("sicon_crm_person_id", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"sicon_engineers index creation warning: {_e}")

    # ───────────────────────────────────────────────────────────────
    # Tier-3 performance indexes (added Feb 2026)
    # Audited every collection with >0 organization_id queries that
    # was missing a covering index. Each `create_index` is idempotent.
    # ───────────────────────────────────────────────────────────────
    try:
        # Sites: every operator dashboard hits /api/sites which filters by org
        await db.sites.create_index([("organization_id", 1), ("created_at", 1)])
        # Per-org assistant action log queries (Trust Dashboard + Undo flow)
        await db.assistant_action_log.create_index(
            [("organization_id", 1), ("executed_at", -1)]
        )
        await db.assistant_action_log.create_index([("id", 1)], unique=True)
        await db.assistant_action_log.create_index([("executed_at", -1)])
        # CRM v2 service cases — heavy joins from Operations + integration_hub
        await db.crm2_service_cases.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
        # Marketing & memberships — campaign lists and segment lookups
        await db.marketing_campaigns.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
        await db.marketing_audiences.create_index([("organization_id", 1)])
        await db.marketing_creative_assets.create_index([("organization_id", 1)])
        # Onboarding packets dashboard
        await db.onboarding_packets.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
        await db.onboarding_packets.create_index([("status", 1), ("created_at", 1)])
        # Check sheets list per org (already had history; add the live one)
        await db.check_sheets.create_index([("organization_id", 1), ("created_at", -1)])
        # Gym floor: handover diary + sessions both filter by org+date
        await db.gym_floor_sessions.create_index(
            [("organization_id", 1), ("started_at", -1)]
        )
        await db.gym_floor_handover.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
        # Faults legacy collection (separate from issues — used by service portal)
        await db.faults.create_index([("organization_id", 1), ("created_at", -1)])
        # AI Creative Director briefs (Phase 1+2)
        await db.marketing_director_briefs.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
        await db.marketing_director_briefs.create_index([("id", 1)], unique=True)
        # Integration events (used by Sage 200 + Orbit 4 sync polling)
        await db.integration_events.create_index(
            [("organization_id", 1), ("created_at", -1)]
        )
    except Exception as _e:  # pragma: no cover
        logger.warning(f"tier-3 index creation warning: {_e}")

    # ───────────────────────────────────────────────────────────────
    # Tier-4 performance indexes (added iter 216h170 — Feb 2026)
    # Filled gaps surfaced by the structured query-pattern audit:
    # every collection in the top-30 by query volume that lacked a
    # covering index on its hottest filter pair. Each is idempotent.
    # ───────────────────────────────────────────────────────────────
    try:
        # Engineer Service hub — id, case_id and timeline lookups
        # `id` lookups are by far the hottest path (36 sites) but
        # we kept the existing organization_id+created_at index too.
        await db.svc_cases.create_index([("id", 1)], unique=True)
        await db.svc_cases.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )
        await db.svc_cases.create_index([("assigned_engineer_id", 1), ("status", 1)])
        await db.svc_cases.create_index([("track_token", 1)], sparse=True)

        # Engineer quotes — id + case_id + status views
        await db.svc_quotes.create_index([("id", 1)], unique=True)
        await db.svc_quotes.create_index([("case_id", 1), ("created_at", -1)])
        await db.svc_quotes.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )

        # Engineer invoices — id + case_id + organization
        await db.svc_invoices.create_index([("id", 1)], unique=True)
        await db.svc_invoices.create_index([("case_id", 1), ("created_at", -1)])
        await db.svc_invoices.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )
        # Case timeline events (sub-doc per case)
        await db.svc_case_events.create_index([("case_id", 1), ("created_at", 1)])
        # Visit notes per case
        await db.svc_visit_notes.create_index([("case_id", 1), ("created_at", -1)])

        # Sites: every dashboard hits this by id + by org+name search
        await db.sites.create_index([("id", 1)], unique=True)
        await db.sites.create_index([("organization_id", 1), ("name", 1)])

        # Payment transactions — Stripe session lookups are the hottest
        # path (webhook + session-status polling). User_id + status used
        # by the onboarding dashboard.
        await db.payment_transactions.create_index([("session_id", 1)], sparse=True)
        await db.payment_transactions.create_index(
            [("user_email", 1), ("payment_status", 1)],
        )
        await db.payment_transactions.create_index(
            [("stripe_event_id", 1)], unique=True, sparse=True,
        )

        # Staff: org + active for rota board; id lookups
        await db.staff_members.create_index([("id", 1)], unique=True)
        await db.staff_members.create_index([("organization_id", 1), ("active", 1)])
        await db.staff_shifts.create_index([("id", 1)], unique=True)
        await db.staff_shifts.create_index(
            [("organization_id", 1), ("starts_at", 1)],
        )
        await db.staff_shifts.create_index([("staff_id", 1), ("starts_at", 1)])

        # Memberships sub-tables (the consoles join these heavily)
        await db.membership_class_invoices.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.membership_class_invoices.create_index([("instructor_id", 1)])
        await db.membership_instructors.create_index([("id", 1)], unique=True)
        await db.membership_instructors.create_index([("organization_id", 1)])

        # Audit logs — the Compliance trail viewer (iter 216h161) reads
        # by user_id + by resource pair, both with time sort.
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index(
            [("resource_type", 1), ("resource_id", 1), ("timestamp", 1)],
        )
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("action", 1), ("timestamp", -1)])

        # Refund events (iter 215c9 + iter 216h165 detail viewer)
        await db.refund_events.create_index([("id", 1)], unique=True)
        await db.refund_events.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )

        # CRM v2 contacts / companies — hot lookup paths
        await db.crm_v2_contacts.create_index([("id", 1)], unique=True, sparse=True)
        await db.crm_v2_contacts.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.crm_v2_companies.create_index([("id", 1)], unique=True, sparse=True)
        await db.crm_v2_companies.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )

        # Engineers (legacy svc_engineers collection)
        await db.svc_engineers.create_index([("organization_id", 1), ("active", 1)])

        # Supplier cases (extra index — existing one only covered timestamp)
        await db.supplier_cases.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.supplier_cases.create_index([("supplier_id", 1), ("status", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"tier-4 index creation warning: {_e}")
    logger.info("MongoDB indexes created/verified")


@app.on_event("startup")
async def startup() -> None:
    # Iter 215ae — surface secret/config misconfiguration at boot. Aborts
    # startup in APP_ENV=production when a critical finding is present.
    try:
        from utils.secrets_audit import run_startup_audit
        run_startup_audit()
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Secrets audit failed: {e}")

    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

    try:
        await _seed_master_admin()
    except Exception as e:
        logger.error(f"Master admin seed failed: {e}")

    try:
        await _seed_services()
    except Exception as e:
        logger.error(f"Service seed failed: {e}")

    # Iter 216g · Phase 2 — start the sign-up journey worker (welcome
    # emails + abandoned-cart recovery). One-shot per pod.
    try:
        from routes.signup_journeys import start_worker_once, _try_schedule_for_pending_events
        start_worker_once()
        await _try_schedule_for_pending_events()
    except Exception as e:
        logger.error(f"Sign-up journey worker init failed: {e}")

    try:
        await _create_indexes()
    except Exception as e:
        logger.error(f"Index creation failed: {e}")

    try:
        from routes.ui_errors import ensure_indexes as _ui_err_indexes
        await _ui_err_indexes()
    except Exception as e:
        logger.error(f"ui_error index setup failed: {e}")

    # Compound-index bootstrap for every org-scoped hot-path collection —
    # single biggest latency win at tenant scale. Idempotent; safe on reboot.
    try:
        from ensure_indexes import ensure_all_indexes
        await ensure_all_indexes(db)
    except Exception as e:
        logger.error(f"ensure_all_indexes failed: {e}")

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

    # File-validation self-check — fails loudly so libmagic regressions
    # (e.g. libmagic1 missing from the container image) cannot ship silently.
    # The file_validation module fails closed on every upload if libmagic
    # isn't loaded, which is invisible until a user tries to upload a file.
    try:
        from utils.file_validation import selftest as _file_validation_selftest
        _fv = _file_validation_selftest()
        if _fv.get("enabled"):
            logger.info("[security] file validation: ENABLED (libmagic ok, detected=%s)", _fv.get("detected"))
        else:
            logger.error(
                "[security] file validation: DISABLED — uploads will fail with HTTP 415. "
                "Reason: %s. Fix: %s",
                _fv.get("reason"), _fv.get("fix"),
            )
    except Exception as e:
        logger.error(f"file validation self-check crashed: {e}")

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


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    try:
        from utils.sicon_poller import stop_poller
        stop_poller()
    except Exception:
        pass
    client.close()
