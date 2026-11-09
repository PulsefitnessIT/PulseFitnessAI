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
