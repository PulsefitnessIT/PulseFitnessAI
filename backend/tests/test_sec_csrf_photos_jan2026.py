"""Security fixes Jan 2026 — SEC-003 CSRF Origin guard + P3 BFPO site-photo path allow-list.

SEC-003: state-changing /api/* calls with a foreign Origin are 403 'Cross-site request blocked'
         unless Bearer auth; trusted origins / no Origin / GET pass.
P3: /api/bfpo/jobs/{id}/site-photos only lists mod-attachments/{site}/ and issues/{issue}/ paths.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient


def _env(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = BASE + "/api"
BYPASS = {"X-RateLimit-Bypass": _env("/app/backend/.env", "RATE_LIMIT_BYPASS_SECRET")}
DB = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]
COOKIE = {"Cookie": "access_token=garbage; session=x"}
LEE_PW = os.environ.get("LEE_PW", "TempPass123!")
FOREIGN = "https://evil.example"


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, headers=BYPASS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed {r.status_code} {r.text[:120]}")
    j = r.json()
    return j.get("access_token") or j.get("token"), r


# ── SEC-003 CSRF origin guard ──────────────────────────────────
class TestCsrfGuard:
    URL = f"{API}/auth/logout"

    def _post(self, extra):
        return requests.post(self.URL, headers={**BYPASS, **extra}, timeout=30)

    def test_foreign_origin_with_cookie_blocked(self):
        r = self._post({**COOKIE, "Origin": FOREIGN})
        assert r.status_code == 403
        assert r.json()["detail"] == "Cross-site request blocked"

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_other_methods_blocked(self, method):
        r = getattr(requests, method)(f"{API}/bfpo/jobs/x", headers={**BYPASS, **COOKIE, "Origin": FOREIGN}, timeout=30)
        assert r.status_code == 403 and "Cross-site" in r.text

    @pytest.mark.parametrize("origin", ["https://modservice.pulsefitness.com", "https://pulsefitness.ai", BASE])
    def test_trusted_origins_pass(self, origin):
        r = self._post({**COOKIE, "Origin": origin})
        assert r.status_code != 403, r.text[:200]

    def test_no_origin_passes(self):
        assert self._post(COOKIE).status_code != 403

    def test_bearer_with_foreign_origin_passes(self):
        r = self._post({**COOKIE, "Origin": FOREIGN, "Authorization": "Bearer abc"})
        assert r.status_code != 403 or "Cross-site" not in r.text

    def test_get_with_foreign_origin_passes(self):
        r = requests.get(f"{API}/health", headers={**BYPASS, **COOKIE, "Origin": FOREIGN}, timeout=30)
        assert r.status_code != 403

    def test_null_origin_with_cookie_blocked(self):
        assert self._post({**COOKIE, "Origin": "null"}).status_code == 403

    def test_foreign_origin_no_cookie_public_not_blocked(self):
        # Spec: no-cookie public embeds should NOT be blocked.
        r = requests.post(f"{API}/public/signup/TEST_nope/track", json={"event": "x"},
                          headers={**BYPASS, "Origin": FOREIGN}, timeout=30)
        assert not (r.status_code == 403 and "Cross-site" in r.text), "public no-cookie call blocked by CSRF guard"

    def test_cookie_session_login_flow_same_origin(self):
        # Cookie-auth browser flow from the preview origin must work end-to-end.
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": "lee.somers@pulsefitness.com", "password": LEE_PW},
                   headers={**BYPASS, "Origin": BASE}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        r2 = s.post(f"{API}/auth/logout", headers={**BYPASS, "Origin": BASE}, timeout=30)
        assert r2.status_code != 403


# ── P3 site-photo path allow-list ──────────────────────────────
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082") + b"\0" * 300


@pytest.fixture(scope="module")
def seeded():
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.database import put_object, APP_NAME
    tmpl = DB.svc_cases.find_one({"bfpo": True, "territory_id": "terr-gib"}, {"_id": 0})
    if not tmpl:
        pytest.skip("no terr-gib template case")
    org = "TEST_modsite_" + uuid.uuid4().hex[:6]
    iid, cid = str(uuid.uuid4()), str(uuid.uuid4())
    good = f"{APP_NAME}/mod-attachments/{org}/TEST_{uuid.uuid4().hex}.png"
    good2 = f"{APP_NAME}/issues/{iid}/TEST_{uuid.uuid4().hex}.png"
    stored = []
    for p in (good, good2):
        res = put_object(p, PNG, "image/png")
        stored.append(res.get("path", p))
    urls = [stored[0],
            f"{APP_NAME}/mod-attachments/OTHER_ORG/secret.png",
            f"{APP_NAME}/mod-attachments/{org}/../OTHER_ORG/secret.png",
            f"{APP_NAME}/staff-documents/abc/passport.pdf",
            stored[1]]
    DB.issues.insert_one({"id": iid, "organization_id": org, "mod_site_id": org, "attachment_urls": urls,
                          "title": "TEST_ p3", "test_seed": "sec_p3"})
    d = {k: tmpl.get(k) for k in ("organization_id", "bfpo", "case_type", "territory_id", "territory_name",
                                  "country", "site_id", "site_name", "customer_name")}
    d.update({"id": cid, "reference": "TEST-P3", "status": "new", "priority": "p3", "title": "TEST_ P3",
              "mod_issue_id": iid, "assigned_engineer_id": "bfpo-eng-gib", "events": [], "test_seed": "sec_p3",
              "created_at": "2026-01-10T10:00:00+00:00", "updated_at": "2026-01-10T10:00:00+00:00"})
    DB.svc_cases.insert_one(d)
    yield cid
    DB.svc_cases.delete_many({"test_seed": "sec_p3"})
    DB.issues.delete_many({"test_seed": "sec_p3"})


class TestSitePhotosAllowList:
    def _h(self, who):
        creds = {"gib": ("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!", "mod"),
                 "lee": ("lee.somers@pulsefitness.com", LEE_PW, None)}[who]
        tok, _ = _login(*creds)
        return {"Authorization": f"Bearer {tok}", **BYPASS}

    def test_list_only_allowed(self, seeded):
        for who in ("gib", "lee"):
            r = requests.get(f"{API}/bfpo/jobs/{seeded}/site-photos", headers=self._h(who), timeout=30)
            assert r.status_code == 200, f"{who}: {r.status_code} {r.text[:200]}"
            photos = r.json()["photos"]
            assert [p["index"] for p in photos] == [0, 1], photos

    def test_valid_photos_stream(self, seeded):
        h = self._h("lee")
        for i in (0, 1):
            r = requests.get(f"{API}/bfpo/jobs/{seeded}/site-photos/{i}", headers=h, timeout=30)
            assert r.status_code == 200 and r.content[:4] == b"\x89PNG", (i, r.status_code)

    def test_out_of_range_404(self, seeded):
        r = requests.get(f"{API}/bfpo/jobs/{seeded}/site-photos/2", headers=self._h("gib"), timeout=30)
        assert r.status_code == 404


# ── Retest: genuinely cookie-less foreign-origin POST (fresh requests call) ──
class TestCsrfNoCookieRetest:
    def test_logout_foreign_origin_no_cookie_not_blocked(self):
        r = requests.post(f"{API}/auth/logout", headers={**BYPASS, "Origin": FOREIGN}, timeout=30)
        assert r.request.headers.get("Cookie") is None
        assert not (r.status_code == 403 and "Cross-site" in r.text), r.text[:200]

    def test_logout_foreign_origin_with_cookie_blocked(self):
        r = requests.post(f"{API}/auth/logout", headers={**BYPASS, "Origin": FOREIGN, "Cookie": "access_token=x"}, timeout=30)
        assert r.status_code == 403 and "Cross-site" in r.text
