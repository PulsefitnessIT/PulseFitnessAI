"""PulseFitness Service Desk — PPM engineer allocation follow-up features.

Covers:
  FEATURE 1  — svc_cases.status is lowercase 'assigned' (regression of earlier fix).
  FEATURE 2  — Allocating a PPM creates an in-app 'job_assigned' notification
               for the engineer; unread-count increments.
  FEATURE 3a — First GET /api/svc/engineer/jobs/{id} auto-sets received_at.
  FEATURE 3b — POST /api/svc/engineer/jobs/{id}/acknowledge sets acknowledged_at.
  FEATURE 3b — Non-assigned user gets 404 from /acknowledge.
  FEATURE 3c — GET /api/svc/ppm/schedules/{schedule_id} exposes
               received_at / acknowledged_at inside 'workings'.
  REGRESSION — Allocated PPM remains visible in engineer's GET /jobs?when=open.
"""
import os
import time
import pytest
import requests
from datetime import date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
BYPASS = "test-bypass-secret-for-ci-runs-only-2026"

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"
JORDAN_ENG_ID = "4cb67443-d6a3-4279-bad3-765207cbd13a"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-RateLimit-Bypass": BYPASS})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def my_id(session):
    r = session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    uid = r.json().get("id") or r.json().get("user", {}).get("id")
    assert uid, "could not get my id"
    return uid


# ---------- helpers ----------
def _find_schedule(session):
    for q in ["Fire", "PPM", "Service", "Preventative", "demo", "iso", "Treadmill"]:
        r = session.get(f"{BASE_URL}/api/svc/ppm/search", params={"q": q})
        if r.status_code == 200:
            res = r.json().get("results") or []
            if res:
                return res[0].get("schedule_id")
    return None


def _create_schedule(session):
    r = session.get(f"{BASE_URL}/api/svc/customers")
    if r.status_code != 200:
        return None
    body = r.json()
    customers = body if isinstance(body, list) else (body.get("customers") or body.get("results") or [])
    for cust in customers:
        cust_id = cust.get("id") or cust.get("organization_id")
        if not cust_id:
            continue
        rs = session.get(f"{BASE_URL}/api/svc/customers/{cust_id}/sites")
        if rs.status_code != 200:
            continue
        sb = rs.json()
        sites = sb if isinstance(sb, list) else (sb.get("sites") or [])
        for site in sites:
            site_id = site.get("id")
            if not site_id:
                continue
            payload = {
                "customer_org_id": cust_id, "site_id": site_id,
                "service_type": "Fire Service PPM", "frequency": "annual",
                "first_visit": date.today().isoformat(), "equipment_ids": [],
            }
            rc = session.post(f"{BASE_URL}/api/svc/ppm/schedules", json=payload)
            if rc.status_code == 200:
                return rc.json().get("schedule_id")
    return None


def _allocate(session, schedule_id, engineer_ids):
    r = session.post(f"{BASE_URL}/api/svc/ppm/schedule", json={
        "schedule_id": schedule_id, "engineer_ids": engineer_ids,
        "scheduled_at": date.today().isoformat(),
    })
    assert r.status_code == 200, f"allocate failed: {r.status_code} {r.text[:400]}"
    return r.json().get("case_id"), r.json()


# ---------- shared state ----------
_state = {}


# ---------- tests ----------
def test_01_allocate_ppm_self_and_create_case(session, my_id):
    """Allocate a PPM to the owner (also an engineer); capture case id."""
    schedule_id = _find_schedule(session) or _create_schedule(session)
    assert schedule_id, "No PPM schedule available"
    _state["schedule_id"] = schedule_id

    # Get baseline unread notification count BEFORE allocation
    r_pre = session.get(f"{BASE_URL}/api/svc/engineer/notifications/unread-count")
    assert r_pre.status_code == 200, r_pre.text[:200]
    _state["unread_before"] = int(r_pre.json().get("unread") or r_pre.json().get("count") or 0)

    case_id, resp = _allocate(session, schedule_id, [my_id])
    assert case_id, f"no case_id in response: {resp}"
    _state["case_id"] = case_id
    print(f"[info] schedule_id={schedule_id} case_id={case_id} unread_before={_state['unread_before']}")


def test_02_feature1_status_is_lowercase_assigned(session, my_id):
    """FEATURE 1 — case status must be lowercase 'assigned', and the job must
    appear in engineer open jobs list."""
    case_id = _state["case_id"]
    r = session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
    assert r.status_code == 200
    body = r.json()
    jobs = body if isinstance(body, list) else (body.get("jobs") or body.get("results") or [])
    found = next((j for j in jobs if j.get("id") == case_id or j.get("case_id") == case_id), None)
    assert found, f"case {case_id} not in engineer open jobs ({len(jobs)})"
    status = (found.get("status") or "")
    assert status == "assigned", f"expected lowercase 'assigned', got '{status}'"
    _state["job_row"] = found


def test_03_feature2_notification_created_for_engineer(session, my_id):
    """FEATURE 2 — an in-app 'job_assigned' notification exists for me, and
    unread count increased by at least 1."""
    case_id = _state["case_id"]
    # Give any async writers a moment (create_notification is awaited inline but harmless).
    time.sleep(0.5)

    r = session.get(f"{BASE_URL}/api/svc/engineer/notifications")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    notifs = body.get("notifications") or body.get("results") or []
    # Filter notifications for THIS case
    for n in notifs:
        print("  notif:", n.get("kind"), n.get("source_id"), n.get("title") or n.get("body"))
    hit = next((n for n in notifs
                if (n.get("kind") == "job_assigned"
                    and (n.get("source_id") == case_id
                         or case_id in (n.get("link") or "")))), None)
    assert hit, f"No job_assigned notification for case {case_id} found. {len(notifs)} total."
    _state["notif_id"] = hit.get("id")

    r2 = session.get(f"{BASE_URL}/api/svc/engineer/notifications/unread-count")
    assert r2.status_code == 200
    unread_after = int(r2.json().get("unread") or r2.json().get("count") or 0)
    assert unread_after >= _state["unread_before"] + 1, \
        f"unread_count didn't go up: before={_state['unread_before']} after={unread_after}"
    print(f"[pass] notification unread {_state['unread_before']} -> {unread_after}")


def test_04_feature3a_received_at_is_null_before_open(session):
    """FEATURE 3a — right after allocation the case has NO received_at."""
    case_id = _state["case_id"]
    # Use the schedule detail (workings) to inspect (tests FEATURE 3c too).
    r = session.get(f"{BASE_URL}/api/svc/ppm/schedules/{_state['schedule_id']}")
    assert r.status_code == 200, r.text[:300]
    workings = r.json().get("workings") or {}
    # Note: workings may be from a different (older) job for same schedule.
    # The field exists in the response shape — assert key is exposed.
    assert "received_at" in workings and "acknowledged_at" in workings, \
        f"workings missing receipt fields: keys={list(workings.keys())}"
    # On the FRESH case we just created, received_at should be empty.
    # Workings is sorted by created_at DESC so it should be the new case.
    assert not workings.get("received_at"), \
        f"received_at should be empty right after allocation, got {workings.get('received_at')}"
    assert not workings.get("acknowledged_at"), \
        f"acknowledged_at should be empty, got {workings.get('acknowledged_at')}"


def test_05_feature3a_received_at_set_on_first_open(session):
    """FEATURE 3a — opening the job detail as the assigned engineer sets received_at."""
    case_id = _state["case_id"]
    r = session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case_id}")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    case = body.get("case") or body.get("job") or body
    recv = case.get("received_at")
    assert recv, f"received_at NOT set after first open: {case.get('received_at')}"
    _state["received_at"] = recv
    print(f"[pass] received_at set to {recv}")


def test_06_feature3c_workings_shows_received_at(session):
    """FEATURE 3c — the PPM schedule detail workings now reflects received_at."""
    r = session.get(f"{BASE_URL}/api/svc/ppm/schedules/{_state['schedule_id']}")
    assert r.status_code == 200
    workings = r.json().get("workings") or {}
    assert workings.get("received_at"), f"workings.received_at empty: {workings}"
    assert not workings.get("acknowledged_at"), \
        f"acknowledged_at should still be empty: {workings.get('acknowledged_at')}"


def test_07_feature3b_acknowledge_sets_acknowledged_at(session):
    """FEATURE 3b — POST /acknowledge sets acknowledged_at; persists via case detail."""
    case_id = _state["case_id"]
    r = session.post(f"{BASE_URL}/api/svc/engineer/jobs/{case_id}/acknowledge")
    assert r.status_code == 200, f"ack failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("ok") is True, f"ok flag missing: {data}"
    assert data.get("acknowledged_at"), f"acknowledged_at missing from response: {data}"
    _state["acknowledged_at"] = data["acknowledged_at"]

    # Verify persistence via GET
    r2 = session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case_id}")
    assert r2.status_code == 200
    case = r2.json().get("case") or r2.json().get("job") or r2.json()
    assert case.get("acknowledged_at"), "acknowledged_at not persisted on case"


def test_08_feature3c_workings_shows_acknowledged_at(session):
    """FEATURE 3c — schedule workings now exposes acknowledged_at too."""
    r = session.get(f"{BASE_URL}/api/svc/ppm/schedules/{_state['schedule_id']}")
    assert r.status_code == 200
    workings = r.json().get("workings") or {}
    assert workings.get("acknowledged_at"), f"workings.acknowledged_at empty: {workings}"
    assert workings.get("received_at"), f"workings.received_at should still be set: {workings}"


def test_09_feature3b_acknowledge_404_for_non_assigned(session):
    """FEATURE 3b — Allocate a NEW case to jordan.blake and verify owner (not
    assigned) gets 404 trying to acknowledge it."""
    schedule_id = _find_schedule(session) or _create_schedule(session)
    assert schedule_id
    case_id, _ = _allocate(session, schedule_id, [JORDAN_ENG_ID])
    # Owner is NOT the assigned engineer here. Owner is master_admin? Check.
    r = session.get(f"{BASE_URL}/api/auth/me")
    is_master = bool(r.json().get("is_master_admin") or r.json().get("user", {}).get("is_master_admin"))
    r2 = session.post(f"{BASE_URL}/api/svc/engineer/jobs/{case_id}/acknowledge")
    if is_master:
        # master_admin bypass allowed; just ensure it doesn't 500
        assert r2.status_code in (200, 404), f"master got {r2.status_code}: {r2.text[:200]}"
        print(f"[info] owner is master_admin — ack returned {r2.status_code}")
    else:
        assert r2.status_code == 404, \
            f"expected 404 for non-assigned user, got {r2.status_code}: {r2.text[:200]}"


def test_10_regression_allocated_ppm_in_open_jobs(session):
    """REGRESSION — the originally allocated PPM is still visible in engineer open jobs."""
    case_id = _state["case_id"]
    r = session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
    assert r.status_code == 200
    body = r.json()
    jobs = body if isinstance(body, list) else (body.get("jobs") or body.get("results") or [])
    found = next((j for j in jobs if j.get("id") == case_id or j.get("case_id") == case_id), None)
    assert found, f"case {case_id} missing from open jobs after full lifecycle"
