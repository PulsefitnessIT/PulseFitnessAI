# Creative Studio AI Director: role gating (lead 403), poster stored in object storage, launch → asset file URL
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PW = "IsoDemo123!"
OWNER = "owner@isodemo.com"
LEAD = "lead@isodemo.com"
_tokens = {}
state = {}
FILE_PREFIX = "/api/marketing/creative/file/"


def _login(email):
    if email in _tokens:
        return _tokens[email]
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    _tokens[email] = r.json()["token"]
    return _tokens[email]


def H(email):
    return {"Authorization": f"Bearer {_login(email)}"}


# --- Permissions endpoint
class TestPermissions:
    def test_owner_can_create(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative/permissions", headers=H(OWNER), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json() == {"can_create": True}

    def test_lead_cannot_create(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative/permissions", headers=H(LEAD), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json() == {"can_create": False}


# --- Lead gets 403 on director mutation endpoints (before any validation)
class TestLeadDirector403:
    def test_build(self):
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/build", headers=H(LEAD),
                          json={"prompt": "x"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_build_empty_body(self):
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/build", headers=H(LEAD),
                          json={}, timeout=30)
        assert r.status_code == 403, r.text

    def test_refine(self):
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/refine", headers=H(LEAD),
                          json={"brief_id": "nope", "instruction": "x"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_delete(self):
        r = requests.delete(f"{BASE_URL}/api/marketing/creative/director/briefs/nope", headers=H(LEAD), timeout=30)
        assert r.status_code == 403, r.text

    def test_launch(self):
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/briefs/nope/launch",
                          headers=H(LEAD), json={}, timeout=30)
        assert r.status_code == 403, r.text

    def test_lead_can_still_list_briefs(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative/director/briefs", headers=H(LEAD), timeout=30)
        assert r.status_code == 200, r.text


# --- File endpoint 404 handling
class TestFile404:
    def test_unknown_token(self):
        r = requests.get(f"{BASE_URL}{FILE_PREFIX}TEST_unknown_token_xyz", timeout=30)
        assert r.status_code == 404, r.text


# --- Owner build (ONE LLM call) → stored poster → launch → asset file URL
class TestOwnerBuildLaunch:
    def test_build(self):
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/build", headers=H(OWNER),
                          json={"prompt": "TEST_ Spin class promo Saturday", "goal": "promote_class",
                                "tone": "high_energy"}, timeout=240)
        assert r.status_code == 200, r.text[:500]
        b = r.json()
        state["brief"] = b
        assert b.get("id")
        assert "poster_variant" not in b
        assert "storage_path" not in str(b)
        pu = b.get("poster_data_url") or ""
        assert not pu.startswith("data:"), "base64 poster leaked"
        assert pu.startswith(FILE_PREFIX), f"unexpected poster url: {pu[:120]}"

    def test_poster_file_serves(self):
        b = state.get("brief") or pytest.skip("no brief")
        r = requests.get(f"{BASE_URL}{b['poster_data_url']}", timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
        assert len(r.content) > 1000

    def test_brief_get(self):
        b = state.get("brief") or pytest.skip("no brief")
        r = requests.get(f"{BASE_URL}/api/marketing/creative/director/briefs/{b['id']}", headers=H(OWNER), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["poster_data_url"] == b["poster_data_url"]
        assert "poster_variant" not in d

    def test_lead_can_get_brief(self):
        b = state.get("brief") or pytest.skip("no brief")
        r = requests.get(f"{BASE_URL}/api/marketing/creative/director/briefs/{b['id']}", headers=H(LEAD), timeout=30)
        assert r.status_code == 200

    def test_lead_cannot_launch_or_delete_real_brief(self):
        b = state.get("brief") or pytest.skip("no brief")
        r1 = requests.post(f"{BASE_URL}/api/marketing/creative/director/briefs/{b['id']}/launch",
                           headers=H(LEAD), json={}, timeout=30)
        r2 = requests.delete(f"{BASE_URL}/api/marketing/creative/director/briefs/{b['id']}", headers=H(LEAD), timeout=30)
        assert r1.status_code == 403 and r2.status_code == 403

    def test_launch(self):
        b = state.get("brief") or pytest.skip("no brief")
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/briefs/{b['id']}/launch",
                          headers=H(OWNER), json={}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("poster_asset_id") and d.get("campaign_id")
        state["launch"] = d
        lst = requests.get(f"{BASE_URL}/api/marketing/creative", headers=H(OWNER), timeout=60).json()
        asset = next((a for a in lst["assets"] if a["id"] == d["poster_asset_id"]), None)
        assert asset, "launched poster asset not in gallery"
        url = asset["variants"][0]["url"]
        assert url.startswith(FILE_PREFIX)
        assert "storage_path" not in asset["variants"][0]
        f = requests.get(f"{BASE_URL}{url}", timeout=60)
        assert f.status_code == 200 and f.headers["content-type"].startswith("image/")
        state["asset_url"] = url
