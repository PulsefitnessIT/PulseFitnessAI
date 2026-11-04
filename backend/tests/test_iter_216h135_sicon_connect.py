"""Iter 216h135 — Sicon Connect (prep) tests.

Confirms the existing `routes/sicon.py` admin-config endpoints behave
correctly so that the new `IntegrationsSiconConnect` panel works the
moment credentials land:

  • GET  /api/sicon/config          → masked, no plaintext password leak
  • PUT  /api/sicon/config          → saves base_url + creds (encrypted)
  • PUT  /api/sicon/config          → blank password preserves prior pwd
  • PUT  /api/sicon/config          → `username = "••••••••"` preserves
  • POST /api/sicon/test-connection → returns connected=false for unreachable

Auth: master admin only (or role=owner).
"""
import os
import uuid

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://pulse-mod-estate--6ncsuzra.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _scrub(org_id):
    _mongo()["sicon_config"].delete_many({"organization_id": org_id})


def test_get_config_returns_dry_run_when_nothing_saved():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    _scrub(user["organization_id"])
    r = requests.get(f"{API}/api/sicon/config", headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("configured") is False
    assert body.get("enabled") is False


def test_put_config_then_get_masks_credentials():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    org = user["organization_id"]
    _scrub(org)
    payload = {
        "base_url": "https://sicon.example.com",
        "username": f"test-{uuid.uuid4().hex[:6]}",
        "password": "s3cretP@ssword!",
        "company_id": 1,
        "enabled": False,
        "auto_sync_faults": True,
        "auto_sync_status": True,
    }
    r = requests.put(f"{API}/api/sicon/config", headers=_hdr(tok),
                      json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True

    # Reading back must mask the username and never leak password
    g = requests.get(f"{API}/api/sicon/config", headers=_hdr(tok), timeout=10).json()
    assert g["configured"] is True
    assert g["base_url"] == payload["base_url"]
    assert g["username"] == "••••••••"
    assert "password" not in g
    assert g.get("has_password") is True

    # Mongo doc: plaintext credentials must NEVER be stored
    raw = _mongo()["sicon_config"].find_one({"organization_id": org}, {"_id": 0})
    assert raw is not None
    assert "username" not in raw or raw["username"] != payload["username"]
    assert "password" not in raw
    assert raw.get("username_enc") and raw["username_enc"] != payload["username"]
    assert raw.get("password_enc") and raw["password_enc"] != payload["password"]


def test_put_config_blank_password_preserves_prior():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    org = user["organization_id"]
    _scrub(org)
    # Seed
    seed = {"base_url": "https://sicon.example.com", "username": "u1",
            "password": "initial", "company_id": 0, "enabled": False}
    requests.put(f"{API}/api/sicon/config", headers=_hdr(tok),
                  json=seed, timeout=10)
    first = _mongo()["sicon_config"].find_one({"organization_id": org}, {"_id": 0})
    first_pwd_enc = first.get("password_enc")
    assert first_pwd_enc

    # Update with blank password and masked username → both preserved
    update = {"base_url": "https://sicon.example.com",
              "username": "••••••••", "password": "", "company_id": 5}
    r = requests.put(f"{API}/api/sicon/config", headers=_hdr(tok),
                      json=update, timeout=10)
    assert r.status_code == 200
    after = _mongo()["sicon_config"].find_one({"organization_id": org}, {"_id": 0})
    assert after.get("password_enc") == first_pwd_enc, "password should be preserved"
    assert after.get("username_enc") == first.get("username_enc"), "username should be preserved"
    assert after.get("company_id") == 5


def test_test_connection_reports_not_configured_after_scrub():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    _scrub(user["organization_id"])
    r = requests.post(f"{API}/api/sicon/test-connection",
                      headers=_hdr(tok), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("connected") is False
    assert "not configured" in (body.get("error") or "").lower()


def test_test_connection_with_unreachable_host_returns_false():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    _scrub(user["organization_id"])
    requests.put(f"{API}/api/sicon/config", headers=_hdr(tok),
                  json={"base_url": "https://sicon-doesnt-exist-12345.invalid",
                        "username": "x", "password": "y", "company_id": 0,
                        "enabled": False}, timeout=10)
    r = requests.post(f"{API}/api/sicon/test-connection",
                      headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("connected") is False, body


def test_config_requires_auth():
    r = requests.get(f"{API}/api/sicon/config", timeout=10)
    assert r.status_code in (401, 403)
    r2 = requests.put(f"{API}/api/sicon/config",
                       json={"base_url": "x"}, timeout=10)
    assert r2.status_code in (401, 403)
