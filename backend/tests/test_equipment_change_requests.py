"""Backend tests for engineer equipment-change-request flow + PPM visits."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pulse-mod-estate--6ncsuzra.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASS = "IsoDemo123!"
CASE_ID = "0bf5a90a-e9c4-454a-a1b1-912b5cebee4d"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    token = body.get("token") or body.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def created_add_request(auth_session):
    r = auth_session.post(f"{API}/svc/engineer/equipment-change-requests", json={
        "case_id": CASE_ID,
        "change_type": "add",
        "proposed": {
            "name": "TEST_Rowing Machine",
            "equipment_type": "rower",
            "serial_number": "TESTSN-1001",
        },
    })
    assert r.status_code == 200, f"propose add failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("success") is True
    req = data.get("request") or {}
    assert req.get("status") == "pending"
    assert req.get("change_type") == "add"
    assert req.get("proposed", {}).get("name") == "TEST_Rowing Machine"
    return req


def test_01_propose_add(created_add_request):
    assert created_add_request["id"]


def test_02_desk_list_shows_pending(auth_session, created_add_request):
    r = auth_session.get(f"{API}/svc/desk/equipment-change-requests?status=pending")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("pending_count", 0) >= 1
    ids = [x["id"] for x in data.get("requests", [])]
    assert created_add_request["id"] in ids


def test_03_propose_remove_requires_equipment_id(auth_session):
    # Fetch job to find an existing machine id
    r = auth_session.get(f"{API}/svc/engineer/jobs/{CASE_ID}")
    assert r.status_code == 200, r.text
    job = r.json()
    job_body = job.get("job") or job
    eq_ids = job_body.get("equipment_ids") or []
    assert eq_ids, f"No equipment_ids on job: {list(job_body.keys())}"
    eq_id = eq_ids[0]
    eq_name = (job_body.get("equipment_serials") or {}).get(eq_id) or "Machine"
    r2 = auth_session.post(f"{API}/svc/engineer/equipment-change-requests", json={
        "case_id": CASE_ID,
        "change_type": "remove",
        "equipment_id": eq_id,
        "equipment_name": eq_name,
    })
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["success"]
    assert body["request"]["change_type"] == "remove"
    assert body["request"]["equipment_id"] == eq_id
    pytest.remove_req_id = body["request"]["id"]
    pytest.remove_eq_id = eq_id


def test_04_approve_add_creates_asset(auth_session, created_add_request):
    rid = created_add_request["id"]
    r = auth_session.post(f"{API}/svc/desk/equipment-change-requests/{rid}/approve", json={"note": "ok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    assert body["applied"].get("equipment_id")

    # verify pending decreased & this id not in pending
    r2 = auth_session.get(f"{API}/svc/desk/equipment-change-requests?status=pending")
    assert r2.status_code == 200
    ids = [x["id"] for x in r2.json().get("requests", [])]
    assert rid not in ids


def test_05_reject_remove(auth_session):
    rid = getattr(pytest, "remove_req_id", None)
    assert rid, "remove request not created in test_03"
    r = auth_session.post(f"{API}/svc/desk/equipment-change-requests/{rid}/reject", json={"note": "nope"})
    assert r.status_code == 200, r.text
    assert r.json()["success"]
    # verify status rejected via list=all
    r2 = auth_session.get(f"{API}/svc/desk/equipment-change-requests?status=rejected")
    assert r2.status_code == 200
    recs = [x for x in r2.json().get("requests", []) if x["id"] == rid]
    assert recs and recs[0]["status"] == "rejected"


def test_06_approve_double_fails(auth_session, created_add_request):
    rid = created_add_request["id"]
    r = auth_session.post(f"{API}/svc/desk/equipment-change-requests/{rid}/approve", json={})
    assert r.status_code == 409


def test_07_ppm_schedule_detail_has_visits(auth_session):
    # Need to find schedule_id for the case
    r = auth_session.get(f"{API}/svc/engineer/jobs/{CASE_ID}")
    assert r.status_code == 200, r.text
    job = r.json()
    job_body = job.get("job") or job
    schedule_id = job_body.get("pm_schedule_id") or job.get("pm_schedule_id")
    assert schedule_id, f"No pm_schedule_id in job keys={list(job_body.keys())}"
    r2 = auth_session.get(f"{API}/svc/ppm/schedules/{schedule_id}")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    sched = data.get("schedule") or data
    visits = sched.get("visits") or data.get("visits") or []
    assert isinstance(visits, list), f"visits not a list: {type(visits)}"
    # Visits may be empty for not-yet-completed jobs; just assert shape
    if visits:
        v = visits[0]
        assert "reference" in v or "case_reference" in v or "visit_reference" in v
        assert "machine_work" in v or "machines" in v
