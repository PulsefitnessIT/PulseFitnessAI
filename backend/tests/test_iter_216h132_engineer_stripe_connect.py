"""Iter 216h132 — Stripe Connect (Express) for Engineer Partners.

These tests do **not** hit the live Stripe API. Instead they:
  * hammer the status endpoint to confirm shape & default values
  * monkey-patch the partner doc to simulate connected / ready state
  * confirm the payment-link endpoint now demands a connected account
  * confirm the webhook handler caches `account.updated` flags

We log in via Master Admin (who can also accept engineer-app gated
endpoints since the partner gate is bypassed for org admins serving
their own org). For the negative test we patch via mongo direct.
"""
import os
import uuid
import json

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://staffing-ops-preview.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _mongo():
    return pymongo.MongoClient(os.environ.get("MONGO_URL"))[DB_NAME]


def _ensure_partner_for(user_email: str) -> str:
    """Ensure a partner_engineers doc exists for the given user. Returns partner_id."""
    db = _mongo()
    user = db["users"].find_one({"email": user_email}, {"_id": 0})
    assert user, f"user {user_email} not found"
    partner = db["partner_engineers"].find_one({"user_id": user["id"]}, {"_id": 0})
    if partner:
        return partner["id"]
    pid = str(uuid.uuid4())
    db["partner_engineers"].insert_one({
        "id": pid,
        "user_id": user["id"],
        "email": user_email,
        "owner_organization_id": user.get("organization_id"),
        "status": "approved",
        "level": "engineer_partner",
        "referral_code": "TESTCODE",
        "active_referral_count": 0,
        "app_fee_tier": {"min": 0, "max": 4, "price_gbp": 30, "label": "Basic"},
        "subscription": {"status": "active"},
        "payout": {"method": "manual_csv", "stripe_account_id": None},
        "created_at": "2026-02-01T00:00:00+00:00",
    })
    return pid


# ─────────────────────────── tests ────────────────────────────


def test_status_endpoint_returns_default_shape_for_unconnected_engineer():
    tok = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    pid = _ensure_partner_for("e1.agent@gymaxisai.com")
    # Force-disconnect to ensure the default-state assertions hold
    _mongo()["partner_engineers"].update_one(
        {"id": pid},
        {"$set": {"payout.stripe_account_id": None,
                  "payout.stripe_connect": None}},
    )
    r = requests.get(f"{API}/api/svc/engineer/stripe/connect/status",
                     headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    for k in ("connected", "ready", "account_id", "charges_enabled",
              "payouts_enabled", "details_submitted",
              "requirements_currently_due"):
        assert k in data, f"missing {k}"
    assert data["connected"] is False
    assert data["ready"] is False
    assert data["account_id"] is None
    assert data["requirements_currently_due"] == []


def test_payment_link_endpoint_rejects_unconnected_engineer():
    """When the engineer has no stripe_account_id we must 412 with
    code=engineer_not_connected and onboarding_required."""
    tok = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    pid = _ensure_partner_for("e1.agent@gymaxisai.com")
    _mongo()["partner_engineers"].update_one(
        {"id": pid}, {"$set": {"payout.stripe_account_id": None}},
    )
    inv = requests.post(
        f"{API}/api/svc/engineer/invoices", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Disconnected Card Test",
              "customer_email": "test@example.com",
              "description_of_work": "Belt change",
              "lines": [{"kind": "labour", "description": "Visit",
                         "quantity": 1, "unit_price": 100}]},
    )
    if inv.status_code != 201:
        import pytest
        pytest.skip(f"engineer cannot create invoices: {inv.status_code}")
    inv = inv.json()
    r = requests.post(
        f"{API}/api/svc/engineer/invoices/{inv['id']}/payment-link",
        headers=_hdr(tok), timeout=20,
    )
    assert r.status_code == 412, r.text[:300]
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "engineer_not_connected"


def test_payment_link_endpoint_rejects_incomplete_onboarding():
    """If `stripe_account_id` is set but `charges_enabled=false` we must
    surface `onboarding_incomplete`."""
    tok = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    pid = _ensure_partner_for("e1.agent@gymaxisai.com")
    _mongo()["partner_engineers"].update_one(
        {"id": pid},
        {"$set": {
            "payout.stripe_account_id": "acct_test_partial",
            "payout.stripe_connect": {
                "charges_enabled": False,
                "payouts_enabled": False,
                "details_submitted": False,
                "requirements_currently_due": ["individual.dob.day"],
            },
        }},
    )
    inv = requests.post(
        f"{API}/api/svc/engineer/invoices", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Partial Onboarding",
              "customer_email": "p@example.com",
              "description_of_work": "Belt change",
              "lines": [{"kind": "labour", "description": "Visit",
                         "quantity": 1, "unit_price": 50}]},
    )
    if inv.status_code != 201:
        import pytest
        pytest.skip(f"engineer create blocked: {inv.status_code}")
    inv = inv.json()
    r = requests.post(
        f"{API}/api/svc/engineer/invoices/{inv['id']}/payment-link",
        headers=_hdr(tok), timeout=20,
    )
    assert r.status_code == 412, r.text[:300]
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "onboarding_incomplete"
    # Requirements bubble through to the client UI
    assert "individual.dob.day" in (detail.get("requirements") or [])


def test_connect_webhook_caches_account_updated_flags():
    """Hit `/api/webhooks/stripe/connect` with a synthetic
    `account.updated` event and confirm the partner doc is updated.

    Since prod has `STRIPE_WEBHOOK_SECRET` set, the unsigned-body path
    returns 400; in that case we skip — the live signed path is
    exercised by Stripe in test mode."""
    pid = _ensure_partner_for("e1.agent@gymaxisai.com")
    test_acct = f"acct_{uuid.uuid4().hex[:16]}"
    _mongo()["partner_engineers"].update_one(
        {"id": pid},
        {"$set": {"payout.stripe_account_id": test_acct,
                  "payout.stripe_connect": {"charges_enabled": False,
                                             "payouts_enabled": False,
                                             "details_submitted": False}}},
    )
    fake_event = {
        "id": f"evt_{uuid.uuid4().hex[:24]}",
        "type": "account.updated",
        "account": test_acct,
        "data": {"object": {
            "id": test_acct,
            "object": "account",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
            "requirements": {"currently_due": []},
        }},
    }
    r = requests.post(f"{API}/api/webhooks/stripe/connect",
                      data=json.dumps(fake_event),
                      headers={"Content-Type": "application/json"},
                      timeout=15)
    if r.status_code == 400:
        import pytest
        pytest.skip("STRIPE_WEBHOOK_SECRET active; signed-payload required")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True
    if body.get("ignored"):
        # Acceptable only if the partner lookup failed — but we just
        # inserted them so it really shouldn't.
        raise AssertionError(body)
    # Confirm the cache was updated
    fresh = _mongo()["partner_engineers"].find_one({"id": pid}, {"_id": 0})
    flags = (fresh.get("payout") or {}).get("stripe_connect") or {}
    assert flags.get("charges_enabled") is True
    assert flags.get("payouts_enabled") is True


def test_login_link_requires_connection():
    tok = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    pid = _ensure_partner_for("e1.agent@gymaxisai.com")
    _mongo()["partner_engineers"].update_one(
        {"id": pid}, {"$set": {"payout.stripe_account_id": None}},
    )
    r = requests.post(f"{API}/api/svc/engineer/stripe/connect/login-link",
                      headers=_hdr(tok), timeout=15)
    assert r.status_code == 412, r.text[:300]
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "engineer_not_connected"
