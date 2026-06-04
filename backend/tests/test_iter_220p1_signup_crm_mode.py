"""Iter 220p1 — CRM audience choice at signup (Gym / Corporate / Both).

When a prospect picks CRM in the trial modal and sends `crm_mode`, the new
org lands on the right CRM mode (verified via GET /api/me/crm-modes):
  gym       -> {leisure: True,  business: False}
  corporate -> {leisure: False, business: True}
  both      -> {leisure: True,  business: True}
"""
import asyncio
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

_CREATED = {"orgs": [], "emails": []}


def _register(crm_mode=None):
    tag = uuid.uuid4().hex[:8]
    email = f"crmmode_pytest_{tag}@example.com"
    name = f"CRMMode Pytest {tag}"
    payload = {"email": email, "password": "Test1234!", "full_name": "Pytest",
               "company_name": name, "is_trial": True, "trial_modules": ["crm"]}
    if crm_mode is not None:
        payload["crm_mode"] = crm_mode
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    _CREATED["orgs"].append(name)
    _CREATED["emails"].append(email)
    return r


def _modes(token):
    r = requests.get(f"{BASE_URL}/api/me/crm-modes",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["modes"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_after():
    yield
    async def go():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.organizations.delete_many({"name": {"$in": _CREATED["orgs"]}})
        await db.users.delete_many({"email": {"$in": _CREATED["emails"]}})
        client.close()
    asyncio.run(go())


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
