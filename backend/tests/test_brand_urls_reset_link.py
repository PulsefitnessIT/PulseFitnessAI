"""Guard: customer-facing email links use the brand domain in PRODUCTION.

Regression (Jul 2026): the password-reset email link rendered
``https://fitness-ai-migrate.emergent.host/reset-password?token=…`` in
production because ``app_url_for`` let ``FRONTEND_URL`` (set to the deploy
platform host in prod) override the ``https://pulsefitness.ai`` brand default.
The deploy host must NEVER appear in a real customer email.
"""
import os

import utils.brand_urls as brand_urls

_KEYS = ("APP_ENV", "ENVIRONMENT", "FRONTEND_URL", "BRAND_URL_PULSE", "BRAND_URL_GYMAXIS")


def _with_env(env: dict, account_type: str) -> str:
    """Evaluate app_url_for under a temporary env, then restore."""
    old = {k: os.environ.get(k) for k in _KEYS}
    try:
        for k in _KEYS:
            os.environ.pop(k, None)
        os.environ.update(env)
        return brand_urls.app_url_for(account_type)
    finally:
        for k in _KEYS:
            os.environ.pop(k, None)
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v


def test_production_ignores_frontend_url_uses_brand_domain():
    env = {"APP_ENV": "production",
           "FRONTEND_URL": "https://fitness-ai-migrate.emergent.host"}
    assert _with_env(env, "pulse_pro") == "https://pulsefitness.ai"
    assert _with_env(env, "full") == "https://pulsefitness.ai"


def test_production_respects_explicit_brand_override():
    env = {"APP_ENV": "production",
           "FRONTEND_URL": "https://fitness-ai-migrate.emergent.host",
           "BRAND_URL_PULSE": "https://app.pulsefitness.ai"}
    assert _with_env(env, "pulse_pro") == "https://app.pulsefitness.ai"


def test_preview_still_uses_frontend_url():
    env = {"FRONTEND_URL": "https://mod-hq-email.preview.emergentagent.com"}
    assert _with_env(env, "pulse_pro") == "https://mod-hq-email.preview.emergentagent.com"


def test_preview_without_frontend_url_falls_back_to_brand_default():
    assert _with_env({}, "pulse_pro") == "https://pulsefitness.ai"
