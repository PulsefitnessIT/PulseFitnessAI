"""Brand-aware app URL helpers.

Every customer-facing email link (supplier cases, onboarding packets,
password resets, trial reminders, digests, etc.) must point at the
*correct* domain for the organisation's brand. We never want a customer
to see ``preview.emergentagent.com`` in a real email — it both leaks
the build platform and breaks once the link is opened on a phone that
doesn't recognise that hostname.

Resolution order (first hit wins)
    1. Per-brand env override:
       - GymAxis orgs  → ``BRAND_URL_GYMAXIS``
       - Pulse orgs    → ``BRAND_URL_PULSE``
    2. Production defaults (post-DNS cutover):
       - GymAxis orgs  → ``https://app.gymaxisai.com``
       - Pulse orgs    → ``https://app.pulsefitness.ai``
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
    goes to GymAxis.
"""
from __future__ import annotations

import os
from typing import Optional


_DEFAULT_GYMAXIS = "https://app.gymaxisai.com"
_DEFAULT_PULSE = "https://app.pulsefitness.ai"


def _is_pulse(account_type: Optional[str]) -> bool:
    """Pulse-branded orgs include ``pulse``, ``pulse_lite``, ``pulse_pro``…"""
    if not account_type:
        return False
    return str(account_type).strip().lower().startswith("pulse")


def app_url_for(account_type: Optional[str]) -> str:
    """Return the public app URL for an org's ``account_type``.

    Always returns a host *without* a trailing slash, e.g.
    ``https://app.gymaxisai.com``. Callers append their own path.
    """
    url = (
        os.environ.get("BRAND_URL_PULSE") or _DEFAULT_PULSE
        if _is_pulse(account_type)
        else os.environ.get("BRAND_URL_GYMAXIS") or _DEFAULT_GYMAXIS
    )

    # FRONTEND_URL acts as a global override during preview / staging.
    # When set, it wins over the brand defaults so we don't need DNS to
    # be live to test email flows. Per-brand env vars still beat it.
    fallback = os.environ.get("FRONTEND_URL", "").strip()
    if fallback and not (
        os.environ.get("BRAND_URL_PULSE") or os.environ.get("BRAND_URL_GYMAXIS")
    ):
        url = fallback

    return url.rstrip("/")


def app_url_for_org(org: Optional[dict]) -> str:
    """Convenience: resolve from the org document directly."""
    return app_url_for((org or {}).get("account_type"))


__all__ = ["app_url_for", "app_url_for_org"]
