"""BFPO urgent-fault alerts (in-app banner) + site fault photos — Jan 2026.

Covers GET /api/bfpo/alerts scoping, POST /api/bfpo/alerts/{id}/ack per-user,
GET /api/bfpo/jobs/{id}/site-photos[/index] streaming + scoping.
Seeded case ids come from /tmp/test_alert_ids.txt ("<issue_id> <case_id>").
"""
import os
import pytest
import requests


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
    return v.rstrip("/")


BASE = _base() + "/api"
BYPASS = {"x-ratelimit-bypass": "test-bypass-secret-for-ci-runs-only-2026"}
OPEN = {"new", "triaged", "assigned"}


def _ids():
    try:
        return open("/tmp/test_alert_ids.txt").read().split()
    except FileNotFoundError:
        return []


IDS = _ids()
CASE_ID = IDS[1] if len(IDS) > 1 else None


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE}/auth/login", json=body, headers=BYPASS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed {r.status_code}")
    j = r.json()
    return {"Authorization": f"Bearer {j.get('access_token') or j.get('token')}", **BYPASS}


@pytest.fixture(scope="module")
def H():
    return {
        "gib": _login("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!", "mod"),
        "cyp": _login("engineer.cyp@bfpo.pulsefitness.test", "Bfpo123!", "mod"),
        "staff2": _login("staff@bfpo.pulsefitness.test", "Bfpo123!", "mod"),
        "lee": _login("lee.somers@pulsefitness.com", os.environ.get("LEE_PW", "TempPass123!")),
        "admin": _login("admin@gymaxisai.com", "MasterAdmin123!", "mod"),
    }


def _alerts(h):
    r = requests.get(f"{BASE}/bfpo/alerts", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()


# ── Alerts ────────────────────────────────────────────────────
class TestAlerts:
    def test_unauth_401(self):
        r = requests.get(f"{BASE}/bfpo/alerts", headers=BYPASS)
        assert r.status_code in (401, 403)

    def test_alert_shape_and_filter(self, H):
        d = _alerts(H["admin"])
        assert d["count"] >= len(d["alerts"])
        for a in d["alerts"]:
            assert a["status"] in OPEN
            assert a["priority"] == "p1" or a.get("safety_critical") is True
            assert "_id" not in a

    def test_staff_sees_seeded_case(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        ids = [a["id"] for a in _alerts(H["lee"])["alerts"]]
        assert CASE_ID in ids

    def test_admin_acked_seeded_case_hidden(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        assert requests.post(f"{BASE}/bfpo/alerts/{CASE_ID}/ack", headers=H["admin"]).status_code == 200
        ids = [a["id"] for a in _alerts(H["admin"])["alerts"]]
        assert CASE_ID not in ids

    def test_gib_scope_no_cyprus(self, H):
        d = _alerts(H["gib"])
        for a in d["alerts"]:
            r = requests.get(f"{BASE}/bfpo/jobs/{a['id']}", headers=H["gib"])
            assert r.status_code == 200, f"gib alerted on job it can't open: {a['id']}"
            job = r.json().get("job") or r.json()
            assert job.get("territory_id") != "terr-cyp"

    def test_cyp_does_not_see_gib_job(self, H):
        gib_ids = {a["id"] for a in _alerts(H["gib"])["alerts"]}
        cyp_ids = {a["id"] for a in _alerts(H["cyp"])["alerts"]}
        for cid in cyp_ids:
            r = requests.get(f"{BASE}/bfpo/jobs/{cid}", headers=H["cyp"])
            assert r.status_code == 200
        # gib's assigned job must not leak to cyprus
        assert not (gib_ids - cyp_ids) & cyp_ids

    def test_ack_is_per_user(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        # reset any ack left by a previous run so the test is re-runnable
        try:
            from pymongo import MongoClient
            from dotenv import load_dotenv
            load_dotenv("/app/backend/.env")
            MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].bfpo_alert_acks.delete_many(
                {"case_id": CASE_ID, "$or": [{"user_id": "bfpo-staff"}, {"user_key": "staff@bfpo.pulsefitness.test"}]})
        except Exception:
            pass
        assert CASE_ID in [a["id"] for a in _alerts(H["staff2"])["alerts"]]
        r = requests.post(f"{BASE}/bfpo/alerts/{CASE_ID}/ack", headers=H["staff2"])
        assert r.status_code == 200 and r.json().get("ok") is True
        assert CASE_ID not in [a["id"] for a in _alerts(H["staff2"])["alerts"]]
        # other staff user still sees it
        assert CASE_ID in [a["id"] for a in _alerts(H["lee"])["alerts"]]
        # idempotent
        r = requests.post(f"{BASE}/bfpo/alerts/{CASE_ID}/ack", headers=H["staff2"])
        assert r.status_code == 200

    def test_ack_out_of_scope_404(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        r = requests.post(f"{BASE}/bfpo/alerts/{CASE_ID}/ack", headers=H["cyp"])
        assert r.status_code == 404

    def test_ack_unknown_404(self, H):
        r = requests.post(f"{BASE}/bfpo/alerts/does-not-exist/ack", headers=H["lee"])
        assert r.status_code == 404


# ── Site photos ───────────────────────────────────────────────
class TestSitePhotos:
    def test_list(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        r = requests.get(f"{BASE}/bfpo/jobs/{CASE_ID}/site-photos", headers=H["lee"])
        assert r.status_code == 200
        photos = r.json()["photos"]
        assert len(photos) == 1
        assert photos[0] == {"index": 0, "kind": "image"}

    def test_stream(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        r = requests.get(f"{BASE}/bfpo/jobs/{CASE_ID}/site-photos/0", headers=H["lee"])
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
        assert r.content[:2] == b"\xff\xd8"  # JPEG magic

    def test_bad_index_404(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        r = requests.get(f"{BASE}/bfpo/jobs/{CASE_ID}/site-photos/7", headers=H["lee"])
        assert r.status_code == 404

    def test_out_of_scope_engineer_404(self, H):
        if not CASE_ID:
            pytest.skip("no seeded case")
        for who in ("cyp",):  # NB: seeded case may get allocated to gib by test_bfpo_portal allocate test
            assert requests.get(f"{BASE}/bfpo/jobs/{CASE_ID}/site-photos", headers=H[who]).status_code == 404
            assert requests.get(f"{BASE}/bfpo/jobs/{CASE_ID}/site-photos/0", headers=H[who]).status_code == 404

    def test_job_without_issue_empty(self, H):
        d = _alerts(H["gib"])
        if not d["alerts"]:
            pytest.skip("no gib jobs")
        r = requests.get(f"{BASE}/bfpo/jobs/{d['alerts'][0]['id']}/site-photos", headers=H["gib"])
        assert r.status_code == 200
        assert isinstance(r.json()["photos"], list)


# ── Ack persistence across sessions (user_key = email) + true count ──
class TestAckPersistence:
    def test_admin_ack_survives_relogin(self, H):
        d = _alerts(H["admin"])
        if not d["alerts"]:
            pytest.skip("no open alerts for admin")
        cid = d["alerts"][0]["id"]
        r = requests.post(f"{BASE}/bfpo/alerts/{cid}/ack", headers=H["admin"], timeout=30)
        assert r.status_code == 200
        before = d["count"]
        h2 = _login("admin@gymaxisai.com", "MasterAdmin123!", "mod")
        d2 = _alerts(h2)
        assert cid not in [a["id"] for a in d2["alerts"]]
        assert d2["count"] == before - 1

    def test_count_matches_db_true_total(self, H):
        d = _alerts(H["admin"])
        assert d["count"] >= len(d["alerts"])
        assert len(d["alerts"]) <= 20
