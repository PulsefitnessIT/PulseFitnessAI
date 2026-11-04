# ESP (External Service Provider) engineer — identity flag, Engineer-App job scope, queue, claim scoping.
# Fixture data: backend/tests/_esp_seed.py (user esp-test-eng-1, cases esp-test-case-1 [own site] / esp-test-case-other).
import os
import subprocess
import sys

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ESP_EMAIL, ESP_PW = "esp.test.eng@example.com", "EspTest123!"
OWN_CASE, OTHER_CASE = "esp-test-case-1", "esp-test-case-other"


def _db_exec(code: str) -> str:
    script = (
        "import asyncio,sys\nsys.path.insert(0,'/app/backend')\n"
        "from dotenv import load_dotenv; load_dotenv('/app/backend/.env')\n"
        "async def m():\n    from utils.database import db\n" + "\n".join("    " + l for l in code.splitlines())
        + "\nasyncio.run(m())\n"
    )
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60).stdout


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    return requests.post(f"{BASE_URL}/api/auth/login", json=body, timeout=30)


@pytest.fixture(scope="module")
def esp_login():
    # reset own-site case to unassigned/new so the queue + claim flow is exercised
    _db_exec(
        f"await db.svc_cases.update_one({{'id':'{OWN_CASE}'}},{{'$set':{{'status':'new','assigned_engineer_id':None,'assigned_engineer_name':None}}}})"
    )
    r = _login(ESP_EMAIL, ESP_PW, "mod")
    if r.status_code != 200 or not r.json().get("token"):
        r = _login(ESP_EMAIL, ESP_PW)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"ESP login failed {r.status_code} {r.text[:200]}")
    return r.json()


@pytest.fixture(scope="module")
def esp(esp_login):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {esp_login['token']}"
    return s


class TestEspIdentity:
    def test_login_payload_flag(self, esp_login):
        assert esp_login["user"].get("is_external_engineer") is True

    def test_me_flag(self, esp):
        r = esp.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json().get("is_external_engineer") is True


class TestEspJobScope:
    def test_unassigned_queue_shows_own_site_only(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/queue/unassigned")
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()["jobs"]]
        assert OWN_CASE in ids
        assert OTHER_CASE not in ids
        assert any(t["name"] for t in r.json()["territories"])

    def test_territory_queue(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/queue/territory")
        assert r.status_code == 200, r.text
        ids = [j["id"] for j in r.json()["jobs"]]
        assert OWN_CASE in ids and OTHER_CASE not in ids

    def test_jobs_open_includes_unassigned_site_job(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
        assert r.status_code == 200, r.text
        data = r.json()
        jobs = data.get("jobs", data if isinstance(data, list) else [])
        ids = [j["id"] for j in jobs]
        assert OWN_CASE in ids and OTHER_CASE not in ids

    def test_engineer_me(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/me")
        assert r.status_code == 200, r.text

    def test_claim_other_site_404(self, esp):
        r = esp.post(f"{BASE_URL}/api/svc/engineer/queue/{OTHER_CASE}/claim", json={})
        assert r.status_code in (403, 404), r.text
        out = _db_exec(f"print((await db.svc_cases.find_one({{'id':'{OTHER_CASE}'}}))['assigned_engineer_id'])")
        assert out.strip() == "None"

    def test_claim_own_site_job(self, esp):
        r = esp.post(f"{BASE_URL}/api/svc/engineer/queue/{OWN_CASE}/claim", json={})
        assert r.status_code == 200, r.text
        out = _db_exec(f"print((await db.svc_cases.find_one({{'id':'{OWN_CASE}'}}))['assigned_engineer_id'])")
        assert out.strip() == "esp-test-eng-1"
        r2 = esp.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
        data = r2.json()
        jobs = data.get("jobs", data if isinstance(data, list) else [])
        assert OWN_CASE in [j["id"] for j in jobs]

    def test_acknowledge_other_site_blocked(self, esp):
        r = esp.post(f"{BASE_URL}/api/svc/engineer/jobs/{OTHER_CASE}/acknowledge", json={})
        assert r.status_code in (403, 404), r.text

    def test_acknowledge_own_job(self, esp):
        r = esp.post(f"{BASE_URL}/api/svc/engineer/jobs/{OWN_CASE}/acknowledge", json={})
        assert r.status_code in (200, 409), r.text

    def test_job_detail_own(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/jobs/{OWN_CASE}")
        assert r.status_code == 200, r.text

    def test_job_detail_other_site_blocked(self, esp):
        r = esp.get(f"{BASE_URL}/api/svc/engineer/jobs/{OTHER_CASE}")
        assert r.status_code in (403, 404), r.text


class TestRegressionInternal:
    def test_internal_bfpo_engineer_not_external(self):
        r = _login("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!", "mod")
        if r.status_code != 200 or not r.json().get("token"):
            pytest.skip(f"internal eng login {r.status_code}")
        assert r.json()["user"].get("is_external_engineer") is False
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        j = requests.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"}, headers=h, timeout=30)
        assert j.status_code == 200

    def test_owner_not_external(self):
        r = _login("owner@isodemo.com", "IsoDemo123!")
        if r.status_code != 200 or not r.json().get("token"):
            pytest.skip("owner login failed")
        assert r.json()["user"].get("is_external_engineer") is False
