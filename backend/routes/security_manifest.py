"""
Public security manifest endpoint — drives the customer-facing
``/security`` page. No auth; purely informational. Lets enterprise IT teams
audit our security posture at a glance without a 40-page questionnaire.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from utils.security import rate_limit_by_ip

router = APIRouter()


def _flag(name: str) -> bool:
    return bool((os.environ.get(name, "") or "").strip())


def _malware_scan_state() -> bool:
    try:
        from utils.malware_scan import scan_available
        return scan_available()
    except Exception:
        return False


def _sso_enabled() -> bool:
    try:
        from utils.sso import sso_enabled
        return sso_enabled()
    except Exception:
        return False


@router.get("/security/manifest")
async def security_manifest(request: Request, response: Response) -> dict:
    """Return a snapshot of the hardened controls currently in effect."""
    rate_limit_by_ip(request, max_requests=20, window_seconds=60)
    # Cache headers — multi-layer defence.
    #
    # Standard: browsers + intermediaries. This works on ANY deployment
    # without CDN config changes (self-hosted, Render, Fly, Railway, etc.).
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=600"
    # CDN-Cache-Control: overrides Cache-Control for CDN edges that
    # understand it (Cloudflare Enterprise, Fastly, Akamai). Browsers and
    # the generic Cache-Control above are not affected.
    response.headers["CDN-Cache-Control"] = "public, max-age=600"
    # Surrogate-Control: same idea, older convention still honoured by
    # Varnish / Fastly and some Cloudflare tiers.
    response.headers["Surrogate-Control"] = "public, max-age=600"
    # Vary — cache key safety. The response body is identical for all
    # origins, so we explicitly say so.
    response.headers.setdefault("Vary", "Accept-Encoding")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "encryption": {
            "transport": "TLS 1.2+ via ingress",
            "at_rest": "MongoDB Atlas encryption + Fernet for MFA secrets",
            "mfa_key_configured": _flag("MFA_ENCRYPTION_KEY"),
        },
        "authentication": {
            "password_hashing": "bcrypt (12 rounds)",
            "jwt_rotation": True,
            "jwt_revocation": "deny-list with TTL sweep",
            "mfa": "TOTP (RFC 6238) with single-use backup codes",
            "mfa_required_for_master_admin": True,
            "sso_oidc_enabled": _sso_enabled(),
            "account_lockout": "progressive, 5 failures",
            "password_policy": {
                "min_length": 12,
                "max_age_days": int(os.environ.get("PASSWORD_MAX_AGE_DAYS", "180")),
            },
        },
        "authorization": {
            "model": "org-scoped RBAC (owner/manager/staff)",
            "master_admin_ip_allowlist": _flag("MASTER_ADMIN_IP_ALLOWLIST"),
        },
        "rate_limiting": {
            "login_attempts": "IP + email per window",
            "public_token_endpoints": "60 req / 5 min per IP",
            "llm_budget": "per-user daily + per-org monthly caps",
        },
        "network": {
            "cors": "allowlist via CORS_ORIGINS (prod fails fast)",
            "body_size_limit_mb": 2,
            "upload_size_limit_mb": 25,
            "security_headers": ["HSTS", "X-Frame-Options: DENY", "X-Content-Type-Options: nosniff",
                                 "Referrer-Policy: strict-origin-when-cross-origin",
                                 "CSP (no unsafe-eval, object-src none, frame-ancestors none)",
                                 "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy",
                                 "Permissions-Policy (camera/mic/geo denied)"],
        },
        "audit": {
            "fail_closed_writer": True,
            "events_tracked": [
                "auth.logout", "mfa.enabled", "mfa.disabled", "mfa.verify.success", "mfa.verify.fail",
                "org.branding.updated", "staff.role.changed", "staff.removed",
                "integration.config.updated", "equipment.deleted",
                "onboarding.packet.provisioned", "supplier.token.issued",
                "pii.retention.purged",
            ],
        },
        "data_protection": {
            "captcha_provider": os.environ.get("CAPTCHA_PROVIDER", "turnstile"),
            "captcha_enabled": _flag("CAPTCHA_SECRET"),
            "upload_content_type_validation": True,
            "malware_scan": _malware_scan_state(),
            "pii_retention_days": int(os.environ.get("PII_RETENTION_DAYS", "365")),
        },
        "integrations": {
            "webhook_verification": "HMAC-SHA256 signature required",
            "supplier_token_ttl_days": 30,
        },
        "monitoring": {
            "trust_events": "5xx + slow-API telemetry captured per request",
            "proactive_nudges": "nightly scanners for warranty, PPM, supplier SLA drift",
        },
        "compliance_posture": {
            "gdpr_pii_retention": True,
            "soc2_audit_trail": True,
            "iso27001_access_control": True,
        },
    }
