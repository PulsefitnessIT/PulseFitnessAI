"""Backend tests for the Contract Activation Board (Type A MOD service contracts).

Covers:
- Master admin auth guard on GET /master-admin/mod-estate/contracts
- Board GET returns contracts[], pending_confirmation, active_count
- Sign a Type A quote (public link) -> contract active + pending_confirmation
- Confirm-visit sets confirmed and decrements pending count
- Reschedule-visit reverts to pending_confirmation with new proposed_date
"""

import os
import uuid
import datetime as dt
import requests
import pytest

def _get_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # read from frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _get_base()
API = f"{BASE}/api"

MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PW = "C2s9yJ3YAhydB4d34-Bykg"
CRM_EMAIL = "owner@isodemo.com"
CRM_PW = "IsoDemo123!"
MOD_ORG_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json().get("token") or r.json()["access_token"]


@pytest.fixture(scope="module")
def master_headers():
    return {"Authorization": f"Bearer {_login(MASTER_EMAIL, MASTER_PW)}"}


@pytest.fixture(scope="module")
def crm_headers():
    return {"Authorization": f"Bearer {_login(CRM_EMAIL, CRM_PW)}"}


# ── Auth guard ──

def test_board_requires_master_admin(crm_headers):
    r = requests.get(f"{API}/master-admin/mod-estate/contracts", headers=crm_headers, timeout=30)
    assert r.status_code in (401, 403), f"non-master-admin got {r.status_code}"


def test_board_unauth_rejected():
    r = requests.get(f"{API}/master-admin/mod-estate/contracts", timeout=30)
    assert r.status_code in (401, 403)


# ── Board shape ──

def test_board_shape(master_headers):
    r = requests.get(f"{API}/master-admin/mod-estate/contracts", headers=master_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert "contracts" in j and isinstance(j["contracts"], list)
    assert "pending_confirmation" in j and isinstance(j["pending_confirmation"], int)
    assert "active_count" in j and isinstance(j["active_count"], int)
    if j["contracts"]:
        c = j["contracts"][0]
        for k in ("id", "mod_site_name", "status", "annual_value", "equipment_count",
                  "start_date", "visit_status", "proposed_date"):
            assert k in c, f"missing key {k}"


# ── End-to-end: sign Type A → active + pending → confirm → reschedule ──

def _find_mod_site_for_org(crm_headers):
    r = requests.get(f"{API}/crm/mod/sites", headers=crm_headers, params={"org_id": MOD_ORG_ID}, timeout=30)
    if r.status_code == 200:
        rows = r.json() if isinstance(r.json(), list) else r.json().get("sites", [])
        if rows:
            return rows[0]
    return None


def test_esign_activates_contract_and_confirm_reschedule(master_headers, crm_headers):
    # 1) Generate a Type A MOD auto-quote
    site = _find_mod_site_for_org(crm_headers)
    if not site:
        pytest.skip("No MOD site available to generate a Type A quote")
    payload = {"mod_site_id": site.get("id") or site.get("mod_site_id"),
               "contract_type": "A", "term_months": 12}
    r = requests.post(f"{API}/crm/mod/auto-quote", json=payload, headers=crm_headers, timeout=60)
    if r.status_code not in (200, 201):
        pytest.skip(f"auto-quote unavailable: {r.status_code} {r.text[:200]}")
    q = r.json()
    quote_id = q.get("id") or q.get("quote_id") or (q.get("quote") or {}).get("id")
    if not quote_id:
        pytest.skip(f"no quote id in response: {q}")

    # 2) Get / create a public sign link
    link_r = requests.post(f"{API}/crm/mod/quotes/{quote_id}/public-link",
                           headers=crm_headers, timeout=30)
    if link_r.status_code not in (200, 201):
        pytest.skip(f"public-link unavailable: {link_r.status_code}")
    lj = link_r.json()
    token = lj.get("token") or lj.get("public_token") or (lj.get("link") or "").split("/")[-1]
    assert token, f"no token: {lj}"

    # 3) Public e-sign
    sig = {"signer_name": "TEST Signer", "signer_role": "Site Manager",
           "signature_data_url": "data:image/png;base64,iVBORw0KGgo="}
    sr = requests.post(f"{API}/public/mod-quote/{token}/sign", json=sig, timeout=60)
    assert sr.status_code in (200, 201), f"public sign: {sr.status_code} {sr.text[:200]}"

    # 4) Board should show contract active + pending
    br = requests.get(f"{API}/master-admin/mod-estate/contracts", headers=master_headers, timeout=30)
    assert br.status_code == 200
    board = br.json()
    match = [c for c in board["contracts"] if c.get("quote_id") == quote_id]
    assert match, "signed quote not present as a contract on board"
    c = match[0]
    assert c["status"] == "active"
    assert c["visit_status"] == "pending_confirmation"
    assert c["proposed_date"], "proposed_date should be set on activation"

    pending_before = board["pending_confirmation"]
    cid = c["id"]

    # 5) Confirm-visit
    conf_payload = {"scheduled_date": "2026-11-15", "engineer": "TEST Engineer",
                    "notes": "TEST confirmed with site POC"}
    cr = requests.post(f"{API}/master-admin/mod-estate/contracts/{cid}/confirm-visit",
                       json=conf_payload, headers=master_headers, timeout=30)
    assert cr.status_code == 200, cr.text[:200]
    cj = cr.json()
    assert cj["ok"] is True
    assert cj["annual_visit"]["status"] == "confirmed"
    assert cj["annual_visit"]["scheduled_date"] == "2026-11-15"
    assert cj["annual_visit"]["engineer"] == "TEST Engineer"
    assert cj["annual_visit"]["confirmed_by"]
    assert cj["annual_visit"]["confirmed_at"]

    # Verify persistence + pending decrement
    br2 = requests.get(f"{API}/master-admin/mod-estate/contracts", headers=master_headers, timeout=30).json()
    row = [x for x in br2["contracts"] if x["id"] == cid][0]
    assert row["visit_status"] == "confirmed"
    assert row["scheduled_date"] == "2026-11-15"
    assert br2["pending_confirmation"] == pending_before - 1

    # 6) Reschedule → back to pending_confirmation
    rr = requests.post(f"{API}/master-admin/mod-estate/contracts/{cid}/reschedule-visit",
                       json={"proposed_date": "2026-12-20"}, headers=master_headers, timeout=30)
    assert rr.status_code == 200, rr.text[:200]
    rj = rr.json()
    assert rj["annual_visit"]["status"] == "pending_confirmation"
    assert rj["annual_visit"]["proposed_date"] == "2026-12-20"

    br3 = requests.get(f"{API}/master-admin/mod-estate/contracts", headers=master_headers, timeout=30).json()
    row3 = [x for x in br3["contracts"] if x["id"] == cid][0]
    assert row3["visit_status"] == "pending_confirmation"
    assert row3["proposed_date"] == "2026-12-20"

    # Reschedule requires proposed_date
    bad = requests.post(f"{API}/master-admin/mod-estate/contracts/{cid}/reschedule-visit",
                        json={}, headers=master_headers, timeout=30)
    assert bad.status_code == 400


def test_confirm_unknown_contract_404(master_headers):
    r = requests.post(f"{API}/master-admin/mod-estate/contracts/does-not-exist/confirm-visit",
                      json={"scheduled_date": "2026-01-01"}, headers=master_headers, timeout=30)
    assert r.status_code == 404
