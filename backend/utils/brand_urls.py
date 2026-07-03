"""Brand-aware app URL helpers.

Every customer-facing email link (supplier cases, onboarding packets,
password resets, trial reminders, digests, etc.) must point at the
*correct* domain for the organisation's brand. We never want a customer
to see ``preview.emergentagent.com`` in a real email — it both leaks
the build platform and breaks once the link is opened on a phone that
doesn't recognise that hostname.

Resolution order (first hit wins)
    1. Per-brand env override:
       - Pulse Fitness orgs  → ``BRAND_URL_GYMAXIS``
       - Pulse orgs    → ``BRAND_URL_PULSE``
    2. Production defaults (post-DNS cutover):
       - Pulse Fitness orgs  → ``https://pulsefitness.ai``
       - Pulse orgs    → ``https://pulsefitness.ai``
    3. Last-resort fallback: ``FRONTEND_URL``. Used during preview /
       staging where DNS isn't live yet.

Why an env override?
    Pre-DNS-cutover, ops wants to point both brands at the preview
    deployment without touching code. Setting ``BRAND_URL_GYMAXIS`` and
    ``BRAND_URL_PULSE`` to the preview URL temporarily achieves that.

What is "account_type"?
    The ``organizations`` collection stores ``account_type`` (one of
    ``"gymaxis"``, ``"pulse"``, ``"lite"``, ``"enterprise"``). Anything
    starting with ``pulse`` routes to the Pulse domain; everything else
    goes to Pulse Fitness.
"""
from __future__ import annotations

import os
from typing import Optional


_DEFAULT_GYMAXIS = "https://pulsefitness.ai"
_DEFAULT_PULSE = "https://pulsefitness.ai"


def _is_pulse(account_type: Optional[str]) -> bool:
    """Pulse-branded orgs include ``pulse``, ``pulse_lite``, ``pulse_pro``…"""
    if not account_type:
        return False
    return str(account_type).strip().lower().startswith("pulse")


def _is_production() -> bool:
    """True when the process is flagged as production. In production the
    customer-facing brand domain MUST win — we never leak the deploy
    platform host (``FRONTEND_URL`` = ``…emergent.host``/preview) into a
    real email link."""
    return (
        (os.environ.get("APP_ENV") or "").lower() == "production"
        or (os.environ.get("ENVIRONMENT", "development") or "").lower().startswith("prod")
    )


def app_url_for(account_type: Optional[str]) -> str:
    """Return the public app URL for an org's ``account_type``.

    Always returns a host *without* a trailing slash, e.g.
    ``https://pulsefitness.ai``. Callers append their own path.

    Resolution order (matches this module's docstring):
      1. Per-brand env override (``BRAND_URL_PULSE`` / ``BRAND_URL_GYMAXIS``).
      2. Production: the live brand default (``https://pulsefitness.ai``) —
         ``FRONTEND_URL`` is IGNORED so the deploy-platform host can never
         appear in customer emails.
      3. Preview/staging (non-production): ``FRONTEND_URL`` if set (so email
         links point at the preview deploy before DNS cutover), else the
         brand default.
    """
    brand_override = (
        os.environ.get("BRAND_URL_PULSE") if _is_pulse(account_type)
        else os.environ.get("BRAND_URL_GYMAXIS")
    )
    default = _DEFAULT_PULSE if _is_pulse(account_type) else _DEFAULT_GYMAXIS

    if brand_override:
        return brand_override.rstrip("/")
    if _is_production():
        return default.rstrip("/")
    fallback = os.environ.get("FRONTEND_URL", "").strip()
    return (fallback or default).rstrip("/")


def app_url_for_org(org: Optional[dict]) -> str:
    """Convenience: resolve from the org document directly."""
    return app_url_for((org or {}).get("account_type"))


__all__ = ["app_url_for", "app_url_for_org"]
