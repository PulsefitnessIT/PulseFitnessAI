"""Iter 216h137 — DIO contract UI plumbing tests.

Exercises:
  • Existing PUT /api/mod/pro/sites/{site_id}/dio-contract — now also
    callable by master admin (cross-tenant support).
  • Existing GET /api/mod/pro/sites/{site_id}/dio-contract — extended
    response shape (now includes `configured` boolean).
  • NEW GET /api/mod/site/dio-contract — read-only view scoped to the
    caller's own site (used by IssueDetailPanel pre-escalation).

We seed a MOD site directly in Mongo (master admin can hit the PUT
without needing an mod_org HQ user) and exercise both reader paths.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://engineer-hub-114.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _seed_mod_site() -> dict:
    """Insert a MOD site directly. mod_root_id and mod_branch are set
    so the HQ-scoped endpoint would refuse a non-MOD HQ user — that's
    fine because we only call it as master admin."""
    db = _mongo()
    sid = str(uuid.uuid4())
    db["organizations"].insert_one({
        "id": sid,
        "name": f"Test MOD Site {sid[:6]}",
        "account_type": "mod_site",
        "mod_root_id": "test-mod-root-001",
        "mod_branch": "army",
        "created_at": _now(),
    })
    return {"id": sid}


def test_master_admin_can_put_and_get_dio_contract():
    tok, _ = _login("admin@gymaxisai.com", "MasterAdmin123!")
    site = _seed_mod_site()
    ref = f"GBC/{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "dio_contract_ref": ref,
        "dio_contact_name": "Lt Col J. Smith",
        "dio_contact_email": "j.smith@dio.mod.uk",
    }
    r = requests.put(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                      headers=_hdr(tok), json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dio_contract_ref"] == ref

    g = requests.get(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                      headers=_hdr(tok), timeout=10)
    assert g.status_code == 200, g.text
    data = g.json()
    assert data["dio_contract_ref"] == ref
    assert data["dio_contact_email"] == "j.smith@dio.mod.uk"
    assert data["configured"] is True
    assert data["dio_updated_at"]


def test_master_admin_get_returns_configured_false_when_empty():
    tok, _ = _login("admin@gymaxisai.com", "MasterAdmin123!")
    site = _seed_mod_site()
    g = requests.get(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                      headers=_hdr(tok), timeout=10)
    assert g.status_code == 200
    assert g.json()["configured"] is False


def test_master_admin_put_404s_for_non_mod_site():
    tok, _ = _login("admin@gymaxisai.com", "MasterAdmin123!")
    db = _mongo()
    sid = str(uuid.uuid4())
    db["organizations"].insert_one({
        "id": sid, "name": "Plain site",
        "account_type": "owner", "created_at": _now(),
    })
    r = requests.put(f"{API}/api/mod/pro/sites/{sid}/dio-contract",
                      headers=_hdr(tok), json={"dio_contract_ref": "X"},
                      timeout=10)
    assert r.status_code == 404, r.text


def test_master_admin_can_clear_dio_contract():
    """PUT with all nulls should clear and report configured=false."""
    tok, _ = _login("admin@gymaxisai.com", "MasterAdmin123!")
    site = _seed_mod_site()
    requests.put(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                  headers=_hdr(tok),
                  json={"dio_contract_ref": "GBC/INITIAL",
                        "dio_contact_email": "x@dio.mod.uk"}, timeout=10)
    requests.put(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                  headers=_hdr(tok),
                  json={"dio_contract_ref": None,
                        "dio_contact_name": None,
                        "dio_contact_email": None}, timeout=10)
    g = requests.get(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                      headers=_hdr(tok), timeout=10).json()
    assert g["dio_contract_ref"] in (None, "")
    assert g["configured"] is False


def test_dio_endpoints_require_auth():
    site = _seed_mod_site()
    r1 = requests.get(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                       timeout=10)
    assert r1.status_code in (401, 403)
    r2 = requests.put(f"{API}/api/mod/pro/sites/{site['id']}/dio-contract",
                       json={"dio_contract_ref": "x"}, timeout=10)
    assert r2.status_code in (401, 403)
    r3 = requests.get(f"{API}/api/mod/site/dio-contract", timeout=10)
    assert r3.status_code in (401, 403)


def test_mod_site_own_endpoint_403s_for_non_mod_user():
    """The site-scoped read endpoint must reject non-MOD-site users."""
    tok, _ = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/mod/site/dio-contract",
                      headers=_hdr(tok), timeout=10)
    # Master admin is not a mod_site user → _require_mod_site rejects
    assert r.status_code in (403, 401), r.text[:200]
