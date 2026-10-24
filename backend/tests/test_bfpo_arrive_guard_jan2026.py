"""BFPO /arrive guard (409 on 'new') + legacy ack user_key backfill — Jan 2026."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
    return v.rstrip("/")


BASE = _base() + "/api"
ENV = dotenv_values("/app/backend/.env")
BYPASS = {"x-ratelimit-bypass": ENV.get("RATE_LIMIT_BYPASS_SECRET")}
DB = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
TEMPLATE_ID = "354c9636-8507-4e19-bf7e-003ca47badd8"


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE}/auth/login", json=body, headers=BYPASS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed {r.status_code}")
    j = r.json()
    return {"Authorization": f"Bearer {j.get('access_token') or j.get('token')}", **BYPASS}


def _new_case(status="new"):
    t = DB.svc_cases.find_one({"id": TEMPLATE_ID}, {"_id": 0})
    if not t:
        pytest.skip("template case missing")
    cid = str(uuid.uuid4())
    keep = {k: t[k] for k in ("organization_id", "bfpo", "case_type", "cover_type", "territory_id", "territory_name",
                              "country", "site_id", "site_name", "site_timezone", "customer_name", "asset_id",
                              "asset_name", "equipment_ids", "sla_response_at", "sla_resolve_at", "created_at")}
    keep.update({"id": cid, "reference": f"TEST-{cid[:6].upper()}", "status": status, "priority": "p3",
                 "title": "TEST_ arrive guard", "description": "TEST_", "safety_critical": False,
                 "assigned_engineer_id": None, "return_visit": False, "updated_at": t["updated_at"],
                 "test_seed": "bfpo_arrive_guard", "events": []})
    DB.svc_cases.insert_one(keep)
    return cid


@pytest.fixture(scope="module")
def gib():
    return _login("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!", "mod")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    ids = [c["id"] for c in DB.svc_cases.find({"test_seed": "bfpo_arrive_guard"}, {"id": 1})]
    for coll in ("svc_cases",):
        DB[coll].delete_many({"id": {"$in": ids}})
    for coll in ("svc_case_events", "bfpo_parts_requests", "bfpo_job_updates"):
        try:
            DB[coll].delete_many({"case_id": {"$in": ids}})
        except Exception:
            pass


# Arrive guard
class TestArriveGuard:
    def test_arrive_on_new_returns_409_and_no_change(self, gib):
        cid = _new_case("new")
        r = requests.post(f"{BASE}/bfpo/jobs/{cid}/arrive", json={"safe": True, "notes": "x"}, headers=gib, timeout=30)
        assert r.status_code == 409, r.text[:300]
        assert "Accept the job before marking yourself on site" in r.text
        c = DB.svc_cases.find_one({"id": cid}, {"_id": 0})
        assert c["status"] == "new"
        assert "arrived_at" not in c and "safety_confirmed" not in c

    def test_unsafe_arrive_on_new_does_not_flag_safety(self, gib):
        cid = _new_case("new")
        r = requests.post(f"{BASE}/bfpo/jobs/{cid}/arrive", json={"safe": False, "notes": "x"}, headers=gib, timeout=30)
        assert r.status_code == 409
        assert DB.svc_cases.find_one({"id": cid})["safety_critical"] is False

    def test_accept_then_arrive_then_repeat(self, gib):
        cid = _new_case("new")
        r = requests.post(f"{BASE}/bfpo/jobs/{cid}/accept", json={}, headers=gib, timeout=30)
        assert r.status_code == 200, r.text[:300]
        r = requests.post(f"{BASE}/bfpo/jobs/{cid}/arrive", json={"safe": True, "notes": "ok"}, headers=gib, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert DB.svc_cases.find_one({"id": cid})["status"] == "on_site"
        r2 = requests.post(f"{BASE}/bfpo/jobs/{cid}/arrive", json={"safe": True, "notes": "again"}, headers=gib, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        assert DB.svc_cases.find_one({"id": cid})["status"] == "on_site"

    def test_arrive_from_en_route(self, gib):
        cid = _new_case("new")
        requests.post(f"{BASE}/bfpo/jobs/{cid}/accept", json={}, headers=gib, timeout=30)
        DB.svc_cases.update_one({"id": cid}, {"$set": {"status": "en_route"}})
        r = requests.post(f"{BASE}/bfpo/jobs/{cid}/arrive", json={"safe": True}, headers=gib, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert DB.svc_cases.find_one({"id": cid})["status"] == "on_site"


# Startup backfill result
class TestAckBackfill:
    def test_no_acks_missing_user_key(self):
        assert DB.bfpo_alert_acks.count_documents({"user_key": {"$exists": False}}) == 0
