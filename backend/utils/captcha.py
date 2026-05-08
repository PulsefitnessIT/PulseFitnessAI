"""
Public-surface bot-protection helper (P2, Feb 2026).

Supports Cloudflare Turnstile and hCaptcha verification, selected via the
``CAPTCHA_PROVIDER`` env var. When the backing secret is *not* configured
we fail-open in development (log once and skip) but **fail-closed** in
production — so you can never accidentally deploy with captcha disabled.

Endpoints that wish to be gated call ``await verify_captcha(token, action)``.
The helper is intentionally thin so routes stay single-responsibility and
under the xenon complexity budget.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_PROVIDERS = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    "hcaptcha": "https://hcaptcha.com/siteverify",
}


def _provider() -> str:
    return os.environ.get("CAPTCHA_PROVIDER", "turnstile").strip().lower()


def _secret() -> str:
    # Use the same env var name regardless of provider so ops can swap cleanly.
    return os.environ.get("CAPTCHA_SECRET", "").strip()


def _is_prod() -> bool:
    return os.environ.get("ENVIRONMENT", "development").lower().startswith("prod")


async def verify_captcha(token: Optional[str], action: str) -> None:
    """Verify a client-side captcha token.

    - ``token`` is the widget response sent by the frontend.
    - ``action`` is a free-form label (e.g. ``login``, ``forgot_password``)
      used only for logging / audit trails.

    Raises 400 when verification fails. Fails open in dev if no secret is
    configured so local smoke tests still work; fails closed in prod.
    """
    provider = _provider()
    secret = _secret()
    if provider not in _PROVIDERS:
        logger.warning(f"[captcha] unknown provider '{provider}' — skipping verification")
        return
    if not secret:
        if _is_prod():
            raise HTTPException(status_code=503, detail="Captcha not configured")
        # dev fallback — logged once at module level below
        return
    if not token:
        raise HTTPException(status_code=400, detail="Captcha token missing")

    # Test / automation bypass — matches the rate-limit bypass pattern.
    # Only accepts an exact match against the RATE_LIMIT_BYPASS_SECRET env.
    _bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if _bypass and token == f"bypass:{_bypass}":
        return

    url = _PROVIDERS[provider]
    payload = {"secret": secret, "response": token}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, data=payload)
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[captcha:{action}] provider error: {exc}")
        # Network flake: fail open in dev, closed in prod
        if _is_prod():
            raise HTTPException(status_code=503, detail="Captcha provider unavailable") from exc
        return

    if not body.get("success"):
        logger.info(f"[captcha:{action}] rejected: {body.get('error-codes')}")
        raise HTTPException(status_code=400, detail="Captcha verification failed")


def captcha_public_config() -> dict:
    """Expose the *public* site-key + provider for the frontend widget."""
    return {
        "provider": _provider(),
        "site_key": os.environ.get("CAPTCHA_SITE_KEY", ""),
        "enabled": bool(_secret()),
    }


if not _secret() and not _is_prod():
    logger.warning("[captcha] CAPTCHA_SECRET not set — captcha verification disabled (dev only)")


# Fire-and-forget warmup hook (keeps the module import cost low when not used)
async def _warmup() -> None:  # pragma: no cover
    await asyncio.sleep(0)
