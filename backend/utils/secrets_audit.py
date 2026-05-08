"""Startup secrets audit — iter 215ae.

Runs once at server boot and surfaces configuration smells that a
pentester would flag within minutes. Issues are logged at CRITICAL
level so they appear in supervisor / stdout logs, but startup is NOT
aborted in dev (to avoid breaking local workflows). Deployments running
with ``APP_ENV=production`` DO abort — fail-fast is the right posture.

Checked today:

1. JWT_SECRET length (≥ 32 chars) and entropy (not a known-weak value).
2. STRIPE_WEBHOOK_SECRET presence when STRIPE_API_KEY is set.
3. CORS_ORIGINS not wide-open in production.
4. MASTER_ADMIN_PASSWORD != a known-weak test password in production.

Add new checks here instead of sprinkling validation across routes.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Iterable

logger = logging.getLogger(__name__)


# Known-weak strings that MUST never appear as a real secret.
_WEAK_JWT_NEEDLES = (
    "gymaxis-ai-secret",       # Legacy dev default shipped before iter 215ae.
    "secret-key",
    "change-me",
    "changeme",
    "your-secret",
    "dev-secret",
    "test-secret",
    "super-secret",
    "jwt-secret",
)

_WEAK_ADMIN_PWS = (
    "MasterAdmin123!",   # Dev seed — fine in local, never in prod.
    "Admin123!",
    "Password123!",
    "password",
    "admin",
)


def _is_prod() -> bool:
    return (os.environ.get("APP_ENV") or "").lower() == "production"


def _findings() -> list[dict]:
    out: list[dict] = []

    jwt_secret = os.environ.get("JWT_SECRET") or ""
    if len(jwt_secret) < 32:
        out.append({
            "severity": "critical",
            "key": "JWT_SECRET",
            "message": f"length={len(jwt_secret)} — must be at least 32 chars of entropy.",
        })
    low = jwt_secret.lower()
    for needle in _WEAK_JWT_NEEDLES:
        if needle in low:
            out.append({
                "severity": "critical",
                "key": "JWT_SECRET",
                "message": f"contains known-weak substring {needle!r}. Rotate immediately.",
            })
            break

    if os.environ.get("STRIPE_API_KEY") and not os.environ.get("STRIPE_WEBHOOK_SECRET"):
        out.append({
            "severity": "high",
            "key": "STRIPE_WEBHOOK_SECRET",
            "message": "STRIPE_API_KEY is set but STRIPE_WEBHOOK_SECRET is blank — webhook signatures cannot be verified.",
        })

    cors = (os.environ.get("CORS_ORIGINS") or "").strip()
    if cors == "*" and _is_prod():
        out.append({
            "severity": "high",
            "key": "CORS_ORIGINS",
            "message": "'*' wildcard in production — restrict to known origins.",
        })

    pw = os.environ.get("MASTER_ADMIN_PASSWORD") or ""
    if pw in _WEAK_ADMIN_PWS and _is_prod():
        out.append({
            "severity": "critical",
            "key": "MASTER_ADMIN_PASSWORD",
            "message": "matches a known-weak test password. Rotate before shipping to production.",
        })

    return out


def _format_line(f: dict) -> str:
    return f"[security-audit] {f['severity'].upper()} · {f['key']} — {f['message']}"


def run_startup_audit(*, abort_on_critical_in_prod: bool = True) -> list[dict]:
    """Log every finding at CRITICAL. In production, abort startup if
    any critical finding is present. Returns the findings list so the
    caller (or tests) can inspect them."""
    findings = _findings()
    if not findings:
        logger.info("[security-audit] all checks passed (JWT, Stripe webhook, CORS, admin pw)")
        return findings

    for f in findings:
        logger.critical(_format_line(f))

    has_critical = any(f["severity"] == "critical" for f in findings)
    if abort_on_critical_in_prod and _is_prod() and has_critical:
        sys.stderr.write(
            "\n\n=== GymAxis startup aborted: critical security misconfiguration ===\n"
        )
        for f in findings:
            sys.stderr.write(_format_line(f) + "\n")
        sys.stderr.write(
            "Set APP_ENV=production and fix the findings above before retrying.\n\n"
        )
        sys.exit(2)

    return findings


def iter_findings() -> Iterable[dict]:
    """Exposed for the /api/security/manifest admin endpoint so operators
    can see the current audit state without restarting."""
    return _findings()
