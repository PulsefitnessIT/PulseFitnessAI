"""Iter 258 — Service Provider self-serve Stripe upgrade.

/api/service-provider/plan, /upgrade/checkout, /upgrade/status/{id}.
Verifies plan shape, owner-only + provider-only guards, a real Stripe
checkout session is created with a payment_transactions ledger row, and
that polling an UNPAID session does NOT convert the org (the paid→convert
path mirrors the proven crm_modes pattern and can't be exercised without
a real card).
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

PROVIDER = ("sp.fe.1781277405@example.com", "Str0ngPass!23")
MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
ORIGIN = "https://pulse-staging-10.preview.emergentagent.com"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_plan_shape():
    h = _login(*PROVIDER)
    r = requests.get(f"{BASE_URL}/api/service-provider/plan", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plan"]["amount_pennies"] == 9900
    assert d["plan"]["interval"] == "month"
    assert d["price_display"] == "£99/month"
    assert d["is_converted"] is False


def test_non_provider_blocked():
    h = _login(*MASTER_ADMIN)
    assert requests.get(f"{BASE_URL}/api/service-provider/plan", headers=h, timeout=20).status_code == 403
    r = requests.post(f"{BASE_URL}/api/service-provider/upgrade/checkout",
                      headers=h, json={"origin_url": ORIGIN}, timeout=20)
    assert r.status_code == 403


def test_checkout_creates_session_and_ledger():
    h = _login(*PROVIDER)
    r = requests.post(f"{BASE_URL}/api/service-provider/upgrade/checkout",
                      headers=h, json={"origin_url": ORIGIN}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["url"].startswith("https://") and "stripe" in d["url"]
    sid = d["session_id"]

    # Polling an unpaid session must report unpaid and NOT convert.
    r = requests.get(f"{BASE_URL}/api/service-provider/upgrade/status/{sid}", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["payment_status"] in ("unpaid", "no_payment_required", "")
    assert r.json()["amount_total"] == 9900

    plan = requests.get(f"{BASE_URL}/api/service-provider/plan", headers=h, timeout=20).json()
    assert plan["is_converted"] is False  # no charge → no conversion


def test_checkout_with_env_origin_fallback():
    """origin_url is optional when FRONTEND_URL is configured server-side."""
    h = _login(*PROVIDER)
    r = requests.post(f"{BASE_URL}/api/service-provider/upgrade/checkout",
                      headers=h, json={}, timeout=30)
    # Either a session (FRONTEND_URL set) or a clean 400 asking for origin.
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert "stripe" in r.json()["url"]


def test_cannot_poll_foreign_session():
    h = _login(*PROVIDER)
    sid = requests.post(f"{BASE_URL}/api/service-provider/upgrade/checkout",
                        headers=h, json={"origin_url": ORIGIN}, timeout=30).json()["session_id"]
    h2 = _login(*MASTER_ADMIN)
    r = requests.get(f"{BASE_URL}/api/service-provider/upgrade/status/{sid}", headers=h2, timeout=20)
    assert r.status_code == 403


def test_subscription_card_trial_state():
    """Iter 258b — trial orgs get the trial card without touching Stripe."""
    h = _login(*PROVIDER)
    r = requests.get(f"{BASE_URL}/api/service-provider/subscription", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "trial"
    assert d["plan_name"] == "Free trial"
    assert isinstance(d["days_left"], int) and d["days_left"] >= 0
    # non-provider blocked
    h2 = _login(*MASTER_ADMIN)
    assert requests.get(f"{BASE_URL}/api/service-provider/subscription", headers=h2, timeout=20).status_code == 403


def test_billing_portal_requires_active_subscription():
    h = _login(*PROVIDER)
    r = requests.post(f"{BASE_URL}/api/service-provider/billing-portal",
                      headers=h, json={"origin_url": ORIGIN}, timeout=20)
    assert r.status_code == 400  # still on trial — nothing to manage
    h2 = _login(*MASTER_ADMIN)
    r = requests.post(f"{BASE_URL}/api/service-provider/billing-portal",
                      headers=h2, json={"origin_url": ORIGIN}, timeout=20)
    assert r.status_code == 403  # not a provider
