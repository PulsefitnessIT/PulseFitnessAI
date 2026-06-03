"""Iter 220w — Stripe Connect "Connect Stripe" onboarding self-serve.

Regression guards for the production bug where the Account Settings setup
checklist "Connect Stripe" step routed owners to the marketing /pricing page
instead of starting Stripe Connect onboarding.

What we lock in:
  1. The `connect_stripe` onboarding step no longer carries `cta_route` and
     now drives the client via `cta_action == 'connect_stripe'`.
  2. The owner self-serve endpoint exists, requires auth, and for an owner
     reaches Stripe (i.e. it is NOT a 404/route-miss and NOT a 403 auth-gate)
     — a Stripe-config 400 in the shared test env is acceptable.
"""
import requests

from routes.account import ONBOARDING_STEPS
from tests.conftest import _test_backend_url


def test_connect_stripe_step_uses_action_not_pricing_route():
    step = next((s for s in ONBOARDING_STEPS if s.get("id") == "connect_stripe"), None)
    assert step is not None, "connect_stripe onboarding step missing"
    assert step.get("cta_action") == "connect_stripe"
    # The /pricing redirect (the bug) must be gone.
    assert step.get("cta_route") != "/pricing"
    assert "cta_route" not in step


def test_me_onboarding_link_requires_auth():
    base = _test_backend_url()
    r = requests.post(f"{base}/api/stripe-connect/me/onboarding-link", json={})
    assert r.status_code in (401, 403), r.text


def test_owner_reaches_stripe_not_pricing(regular_user_token):
    """An authenticated owner hits the Stripe layer (not a route/auth miss)."""
    assert regular_user_token, "regular owner token unavailable"
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/stripe-connect/me/onboarding-link",
        headers={"Authorization": f"Bearer {regular_user_token}", "Origin": base},
        json={"return_path": "/dashboard"},
    )
    # 404 would mean the route is missing; 403 would mean the owner was wrongly
    # blocked. 200 (link) or 400 (Stripe platform-profile config in shared test
    # env) both prove the request reached Stripe with proper auth.
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        assert r.json().get("url", "").startswith("http")
    else:
        assert "stripe" in r.text.lower()


def test_connect_error_helper_maps_platform_profile():
    """Platform-profile blocker → structured code + dashboard help link."""
    from utils.stripe_connect_errors import stripe_connect_http_exception

    class _Exc(Exception):
        user_message = (
            "Please review the responsibilities of managing losses for connected "
            "accounts at https://dashboard.stripe.com/settings/connect/platform-profile."
        )

        def __str__(self):
            return self.user_message

    http = stripe_connect_http_exception(_Exc())
    assert http.status_code == 400
    assert isinstance(http.detail, dict)
    assert http.detail["code"] == "stripe_connect_profile_incomplete"
    assert "platform-profile" in http.detail["help_url"]


def test_connect_error_helper_passthrough_generic():
    from utils.stripe_connect_errors import stripe_connect_http_exception

    class _Exc(Exception):
        user_message = "Your card was declined."

        def __str__(self):
            return self.user_message

    http = stripe_connect_http_exception(_Exc())
    # Unknown errors fall through as a plain string detail (not the banner code).
    assert isinstance(http.detail, str)
    assert "Stripe error" in http.detail
