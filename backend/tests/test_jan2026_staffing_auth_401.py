# Staffing endpoints: unauthenticated -> 401 (not 500); platform token -> 200; CRM token fallback works
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
BYPASS = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}


def _login(path, email, pw):
    for _ in range(3):
        r = requests.post(f"{BASE_URL}{path}", json={"email": email, "password": pw}, headers=BYPASS, timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        return r
    return r


@pytest.fixture(scope="module")
def ops_token():
    r = _login("/api/auth/login", "portal@pulsefitness.ltd", "PulseFleet123!")
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"ops login failed {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def crm_token():
    r = _login("/api/crm/auth/login", "owner@isodemo.com", "IsoDemo123!")
    if r.status_code != 200:
        pytest.skip(f"crm login failed {r.status_code} {r.text[:200]}")
    d = r.json()
    tok = d.get("token") or d.get("access_token")
    if not tok:
        pytest.skip(f"no crm token in {list(d.keys())}")
    return tok


@pytest.mark.parametrize("ep", ["/api/staffing/compliance", "/api/staffing/shifts"])
def test_unauth_returns_401(ep):
    r = requests.get(f"{BASE_URL}{ep}", timeout=30)
    assert r.status_code == 401, f"{ep} -> {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("ep", ["/api/staffing/compliance", "/api/staffing/shifts"])
def test_bad_token_returns_401(ep):
    r = requests.get(f"{BASE_URL}{ep}", headers={"Authorization": "Bearer garbage.token.value"}, timeout=30)
    assert r.status_code == 401, f"{ep} -> {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("ep", ["/api/staffing/compliance", "/api/staffing/shifts"])
def test_ops_token_200(ops_token, ep):
    r = requests.get(f"{BASE_URL}{ep}", headers={"Authorization": f"Bearer {ops_token}"}, timeout=30)
    assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text[:200]}"
    assert isinstance(r.json(), (dict, list))


def test_crm_token_fallback_shifts(crm_token):
    r = requests.get(f"{BASE_URL}/api/staffing/shifts", headers={"Authorization": f"Bearer {crm_token}"}, timeout=30)
    assert r.status_code not in (401, 500), f"{r.status_code} {r.text[:200]}"
    assert r.status_code == 200
