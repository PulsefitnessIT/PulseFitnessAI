"""Iter 220p1 — CRM audience choice at signup (Gym / Corporate / Both).

When a prospect picks CRM in the trial modal and sends `crm_mode`, the new
org lands on the right CRM mode (verified via GET /api/me/crm-modes):
  gym       -> {leisure: True,  business: False}
  corporate -> {leisure: False, business: True}
  both      -> {leisure: True,  business: True}

Notes for the next agent:
- The backend URL comes from conftest._test_backend_url() (REACT_APP_BACKEND_URL
  with a fall-back), NOT a bare os.environ read.
- Trial signups are captcha-gated; we pass the `bypass:<RATE_LIMIT_BYPASS_SECRET>`
  token (verify_captcha accepts it). The X-RateLimit-Bypass header is attached
  automatically by the autouse conftest fixture.
- Cleanup uses a SYNCHRONOUS pymongo client so it never touches / closes the
  shared Motor event loop (the old asyncio.run cleanup raised
  "RuntimeError: Event loop is closed").
"""
import os
import uuid

import pytest
import requests

from conftest import _test_backend_url

BASE_URL = _test_backend_url()

_CREATED = {"orgs": [], "emails": []}


def _bypass_secret() -> str:
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if not secret:
        try:
            with open("/app/backend/.env", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                        secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            pass
    return secret


def _register(crm_mode=None, country_code=None):
    tag = uuid.uuid4().hex[:8]
    email = f"crmmode_pytest_{tag}@example.com"
    name = f"CRMMode Pytest {tag}"
    payload = {
        "email": email, "password": "Test1234!", "full_name": "Pytest",
        "company_name": name, "is_trial": True, "trial_modules": ["crm"],
        "cf_turnstile_response": f"bypass:{_bypass_secret()}",
    }
    if crm_mode is not None:
        payload["crm_mode"] = crm_mode
    if country_code is not None:
        payload["country_code"] = country_code
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    _CREATED["orgs"].append(name)
    _CREATED["emails"].append(email)
    return r


def _localization(token):
    r = requests.get(f"{BASE_URL}/api/org/localization",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["localization"]


def _modes(token):
    r = requests.get(f"{BASE_URL}/api/me/crm-modes",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["modes"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_after():
    yield
    # Synchronous pymongo — does NOT touch the shared Motor event loop.
    try:
        from pymongo import MongoClient
        client = MongoClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        db.organizations.delete_many({"name": {"$in": _CREATED["orgs"]}})
        db.users.delete_many({"email": {"$in": _CREATED["emails"]}})
        client.close()
    except Exception:
        pass


@pytest.mark.parametrize("mode,leisure,business", [
    ("gym", True, False),
    ("corporate", False, True),
    ("both", True, True),
])
def test_signup_crm_mode(mode, leisure, business):
    r = _register(mode)
    assert r.status_code == 200, r.text[:200]
    token = r.json()["token"]
    m = _modes(token)
    assert m["leisure"] is leisure
    assert m["business"] is business


def test_signup_crm_mode_defaults_to_gym():
    r = _register(None)
    assert r.status_code == 200, r.text[:200]
    m = _modes(r.json()["token"])
    assert m["leisure"] is True
    assert m["business"] is False


def test_signup_country_code_us_sets_usd_market():
    r = _register(country_code="US")
    assert r.status_code == 200, r.text[:200]
    loc = _localization(r.json()["token"])
    assert loc["country_code"] == "US"
    assert loc["currency"] == "USD"
    assert loc["tax_label"] == "Sales Tax"


def test_signup_country_code_default_is_gb():
    r = _register()
    assert r.status_code == 200, r.text[:200]
    loc = _localization(r.json()["token"])
    assert loc["country_code"] == "GB"
    assert loc["currency"] == "GBP"
