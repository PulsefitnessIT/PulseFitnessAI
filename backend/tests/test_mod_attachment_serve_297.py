# Iter 297: GET /api/mod/site/attachments/serve auth — JWT query OR HttpOnly session cookie
# Requires: python tests/_seed_fault_photos_295.py seed (clean afterwards)
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SERVE = f"{BASE_URL}/api/mod/site/attachments/serve"
PW = "TestPhoto295#2026"
P1 = "gymaxis-ai/mod-attachments/TEST_295_modorg/TEST_295_photo1.webp"
P2 = "gymaxis-ai/mod-attachments/TEST_295_modorg/TEST_295_photo2.webp"


def _login(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PW, "portal": "mod"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    return s, r.json()


@pytest.fixture(scope="module")
def site():
    return _login("test_295_siteuser@example.test")


@pytest.fixture(scope="module")
def outsider():
    return _login("test_295_outsider@example.test")


def _jwt(sess, data):
    return data.get("token") if data.get("token") not in (None, "", "cookie") else sess.cookies.get("ga_session")


class TestServeAuth:
    def test_login_sets_cookie(self, site):
        s, data = site
        assert s.cookies.get("ga_session"), f"no ga_session cookie; cookies={list(s.cookies.keys())}"

    def test_jwt_query_no_cookie(self, site):
        tok = _jwt(*site)
        r = requests.get(SERVE, params={"path": P1, "token": tok})
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("image/webp")
        assert r.content[:4] == b"RIFF"

    def test_cookie_only(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": P2})
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("image/webp")
        assert len(r.content) > 20

    def test_token_cookie_sentinel_plus_cookie(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": P1, "token": "cookie"})
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("image/webp")

    def test_garbage_token_plus_cookie(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": P1, "token": "garbage.jwt.value"})
        assert r.status_code == 200, r.text[:200]

    def test_no_token_no_cookie_401(self):
        r = requests.get(SERVE, params={"path": P1})
        assert r.status_code == 401

    def test_token_cookie_sentinel_no_cookie_401(self):
        r = requests.get(SERVE, params={"path": P1, "token": "cookie"})
        assert r.status_code == 401

    def test_outsider_cookie_403(self, outsider):
        s, _ = outsider
        r = s.get(SERVE, params={"path": P1})
        assert r.status_code == 403, r.text[:200]

    def test_outsider_jwt_403(self, outsider):
        tok = _jwt(*outsider)
        r = requests.get(SERVE, params={"path": P1, "token": tok})
        assert r.status_code == 403

    def test_path_outside_400(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": "gymaxis-ai/other/TEST_x.webp"})
        assert r.status_code == 400

    def test_path_dotdot_400(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": "gymaxis-ai/mod-attachments/TEST_295_modorg/../TEST_295_otherorg/x.webp"})
        assert r.status_code == 400

    def test_missing_file_404(self, site):
        s, _ = site
        r = s.get(SERVE, params={"path": "gymaxis-ai/mod-attachments/TEST_295_modorg/TEST_nope.webp"})
        assert r.status_code == 404


# Iter 298: ?token= branch must reject revoked JWTs and inactive users
import sys
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


class TestServeRevocation298:
    def test_logged_out_jwt_query_401(self):
        s, data = _login("test_295_outsider@example.test")
        tok = _jwt(s, data)
        # own-org-less: outsider can't see P1 (403) — use own-org check via a path in its org? use status before/after
        before = requests.get(SERVE, params={"path": P1, "token": tok})
        assert before.status_code == 403, before.text[:200]
        lo = s.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        assert lo.status_code == 200, lo.text[:200]
        r = requests.get(SERVE, params={"path": P1, "token": tok})
        assert r.status_code == 401, f"{r.status_code} {r.text[:200]}"

    def test_logged_out_site_jwt_query_401_and_cookie_fallback(self, site):
        s2, d2 = _login("test_295_siteuser@example.test")
        tok = _jwt(s2, d2)
        ok = requests.get(SERVE, params={"path": P1, "token": tok})
        assert ok.status_code == 200
        lo = s2.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {tok}"})
        assert lo.status_code == 200
        r = requests.get(SERVE, params={"path": P1, "token": tok})
        assert r.status_code == 401, f"{r.status_code} {r.text[:200]}"
        # revoked query token + still-valid cookie (other session) -> 200 via cookie
        s, _ = site
        r2 = s.get(SERVE, params={"path": P1, "token": tok})
        assert r2.status_code == 200, r2.text[:200]
        assert r2.headers["content-type"].startswith("image/webp")

    def test_is_active_false_query_401(self, site):
        tok = _jwt(*site)
        _db.users.update_one({"id": "TEST_295_siteuser"}, {"$set": {"is_active": False}})
        try:
            r = requests.get(SERVE, params={"path": P1, "token": tok})
            assert r.status_code == 401, f"{r.status_code} {r.text[:200]}"
        finally:
            _db.users.update_one({"id": "TEST_295_siteuser"}, {"$unset": {"is_active": ""}})
        assert requests.get(SERVE, params={"path": P1, "token": tok}).status_code == 200

    def test_active_false_query_401(self, site):
        """Canonical deactivation field used by login (_enforce_account_status) is `active`."""
        tok = _jwt(*site)
        _db.users.update_one({"id": "TEST_295_siteuser"}, {"$set": {"active": False}})
        try:
            r = requests.get(SERVE, params={"path": P1, "token": tok})
            assert r.status_code == 401, f"active=False still served: {r.status_code}"
        finally:
            _db.users.update_one({"id": "TEST_295_siteuser"}, {"$set": {"active": True}})
