"""Backend tests for:
- BUG 1: Master Admin purge test-data — sites detection + scoped deletion
- BUG 2: /auth/me exposes org_module_access alongside module_access (master bypass)
"""
import os
import uuid
import pytest
import requests

_ENV = os.environ.get("REACT_APP_BACKEND_URL")
if not _ENV:
    # load from /app/frontend/.env
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    _ENV = _line.strip().split("=", 1)[1]
                    break
    except Exception:
        pass
BASE_URL = (_ENV or "").rstrip("/")
MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"
MASTER_ORG_ID = "d19de469-645a-4b66-93b1-52455a643f5b"


@pytest.fixture(scope="module")
def master_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def auth(master_token):
    return {"Authorization": f"Bearer {master_token}"}


# ── BUG 1: purge test data ────────────────────────────────────────────────

def test_candidates_unauth_returns_401():
    r = requests.get(f"{BASE_URL}/api/master-admin/test-data/candidates", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_candidates_returns_sites_array(auth):
    r = requests.get(f"{BASE_URL}/api/master-admin/test-data/candidates",
                     headers=auth, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert "sites" in j and isinstance(j["sites"], list)
    assert "organizations" in j and "users" in j
    # Each site entry must have the required shape
    for s in j["sites"]:
        assert set(["id", "name", "organization_id", "org_name", "reason"]).issubset(s.keys())
        assert s["reason"] in ("orphaned (org deleted)", "test/demo name")


def test_dry_run_purge_returns_sites_previews(auth):
    r = requests.post(f"{BASE_URL}/api/master-admin/test-data/purge",
                      headers=auth, json={"dry_run": True}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j.get("dry_run") is True
    assert "sites" in j and isinstance(j["sites"], list)
    for s in j["sites"]:
        assert s.get("would_delete") is True


def _create_throwaway_site(auth):
    """Insert a QA site directly via a common admin sites API. Fallbacks tried."""
    # Try to find any existing site to grab an org id to attach to.
    site_id = f"qa-purge-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": site_id,
        "name": "ZZ QA Purge (test) Site",
        "organization_id": MASTER_ORG_ID,
    }
    # Attempt via /api/sites (common route)
    r = requests.post(f"{BASE_URL}/api/sites", headers=auth, json=payload, timeout=20)
    if r.status_code in (200, 201):
        data = r.json()
        return data.get("id") or site_id
    # Attempt admin route
    r2 = requests.post(f"{BASE_URL}/api/master-admin/sites", headers=auth,
                       json=payload, timeout=20)
    if r2.status_code in (200, 201):
        data = r2.json()
        return data.get("id") or site_id
    return None


def test_scoped_purge_site_deletion(auth):
    sid = _create_throwaway_site(auth)
    if not sid:
        pytest.skip("No sites-create endpoint reachable; skipping deletion path")
    # candidates should now include it (matches '(test)' pattern)
    r = requests.get(f"{BASE_URL}/api/master-admin/test-data/candidates",
                     headers=auth, timeout=30)
    assert r.status_code == 200
    site_ids = [s["id"] for s in r.json().get("sites", [])]
    assert sid in site_ids, f"created site {sid} not in candidates.sites"
    # scoped delete
    r2 = requests.post(f"{BASE_URL}/api/master-admin/test-data/purge",
                       headers=auth,
                       json={"dry_run": False, "site_ids": [sid]}, timeout=30)
    assert r2.status_code == 200, r2.text[:300]
    j = r2.json()
    found = [s for s in j.get("sites", []) if s.get("site_id") == sid]
    assert found and found[0].get("deleted") is True
    # re-check candidates → gone
    r3 = requests.get(f"{BASE_URL}/api/master-admin/test-data/candidates",
                      headers=auth, timeout=30)
    assert sid not in [s["id"] for s in r3.json().get("sites", [])]


# ── BUG 2: /auth/me exposes org_module_access ─────────────────────────────

def _feature_toggle(auth, org_id, key, enabled):
    r = requests.put(
        f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
        headers=auth,
        json={"modules": {key: {"enabled": enabled}}}, timeout=30)
    assert r.status_code == 200, f"toggle {key}={enabled} failed: {r.status_code} {r.text[:200]}"


def test_auth_me_exposes_both_access_maps(auth, master_token):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth, timeout=20)
    assert r.status_code == 200
    me = r.json()
    assert "module_access" in me, "module_access missing"
    assert "org_module_access" in me, "org_module_access missing"
    assert isinstance(me["org_module_access"], dict)


def test_org_module_access_reflects_toggle(auth):
    # baseline — turn Marketing OFF then ON, verifying org_module_access flips
    try:
        _feature_toggle(auth, MASTER_ORG_ID, "marketing", False)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth, timeout=15).json()
        assert me["module_access"].get("marketing") is True, "master bypass broken"
        assert me["org_module_access"].get("marketing") is False, \
            f"org_module_access.marketing should be False, got {me['org_module_access']}"
    finally:
        _feature_toggle(auth, MASTER_ORG_ID, "marketing", True)
    me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=auth, timeout=15).json()
    assert me2["org_module_access"].get("marketing") is True, "restore failed"
