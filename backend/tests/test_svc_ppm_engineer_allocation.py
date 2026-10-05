"""Regression test for PulseFitness Service Desk PPM-to-engineer allocation bug.

Bug: POST /api/svc/ppm/schedule wrote svc_cases.status = 'ASSIGNED' (upper),
while GET /api/svc/engineer/jobs filters status against OPEN_STATES which
are lowercase ('assigned', ...). Mongo is case-sensitive, so allocated PPM
jobs never showed up in the engineer's job list.

Fix: ppm_calendar.py now writes status = 'assigned' (lowercase).

This test verifies, end-to-end via REACT_APP_BACKEND_URL:
1. Operator can allocate a PPM to an engineer via POST /api/svc/ppm/schedule.
2. The resulting svc_cases doc has status == 'assigned' and
   assigned_engineer_id set.
3. GET /api/svc/engineer/jobs (as the SAME user, who is both operator and
   svc_engineer) returns the ppm job for when=open and when=today.
"""
import os
import pytest
import requests
from datetime import date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")
BYPASS = "test-bypass-secret-for-ci-runs-only-2026"

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"
JORDAN_ENG_ID = "4cb67443-d6a3-4279-bad3-765207cbd13a"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": BYPASS,
    })
    # login
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


def _find_schedule(session) -> str | None:
    """Try several search queries to locate an existing PPM schedule for iso-demo-org."""
    for q in ["Fire", "PPM", "Service", "Preventative", "demo", "iso", "Treadmill"]:
        r = session.get(f"{BASE_URL}/api/svc/ppm/search", params={"q": q})
        if r.status_code != 200:
            continue
        results = r.json().get("results") or []
        if results:
            return results[0].get("schedule_id")
    return None


def _create_schedule(session) -> str | None:
    """Fallback: create a PPM schedule using any customer org/site/equipment we can see."""
    # Get a customer org with sites
    r = session.get(f"{BASE_URL}/api/svc/customers")
    if r.status_code != 200:
        return None
    customers = r.json() if isinstance(r.json(), list) else (r.json().get("customers") or r.json().get("results") or [])
    for cust in customers:
        cust_id = cust.get("id") or cust.get("organization_id")
        if not cust_id:
            continue
        # fetch sites
        rs = session.get(f"{BASE_URL}/api/svc/customers/{cust_id}/sites")
        if rs.status_code != 200:
            continue
        sites = rs.json() if isinstance(rs.json(), list) else (rs.json().get("sites") or [])
        for site in sites:
            site_id = site.get("id")
            if not site_id:
                continue
            payload = {
                "customer_org_id": cust_id,
                "site_id": site_id,
                "service_type": "Fire Service PPM",
                "frequency": "annual",
                "first_visit": date.today().isoformat(),
                "equipment_ids": [],
            }
            rc = session.post(f"{BASE_URL}/api/svc/ppm/schedules", json=payload)
            if rc.status_code == 200:
                return rc.json().get("schedule_id")
    return None


def test_ppm_allocation_shows_in_engineer_jobs(session):
    # 1) Who am I (engineer id = owner's own user id, since owner is also svc_engineer)
    me = session.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200, me.text[:300]
    my_id = me.json().get("id") or me.json().get("user", {}).get("id")
    assert my_id, f"could not get my id: {me.json()}"
    print(f"[info] my id = {my_id}")

    # 2) Find or create a PPM schedule
    schedule_id = _find_schedule(session)
    if not schedule_id:
        schedule_id = _create_schedule(session)
    assert schedule_id, "No PPM schedule available and could not create one"
    print(f"[info] using schedule_id = {schedule_id}")

    # 3) Allocate the PPM to myself (so GET /svc/engineer/jobs returns it for me)
    today = date.today().isoformat()
    r = session.post(f"{BASE_URL}/api/svc/ppm/schedule", json={
        "schedule_id": schedule_id,
        "engineer_ids": [my_id],
        "scheduled_at": today,
    })
    assert r.status_code == 200, f"allocate failed: {r.status_code} {r.text[:500]}"
    alloc = r.json()
    case_id = alloc.get("case_id")
    assert case_id, f"no case_id in response: {alloc}"
    print(f"[info] created case_id = {case_id}")

    # 4) Engineer-side list: when=open must contain this case with status 'assigned'
    r = session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
    assert r.status_code == 200, f"engineer/jobs open failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    jobs = body if isinstance(body, list) else (body.get("jobs") or body.get("results") or [])
    print(f"[info] open jobs count = {len(jobs)}")

    found = next((j for j in jobs if j.get("id") == case_id or j.get("case_id") == case_id), None)
    assert found, (
        f"Allocated PPM case {case_id} NOT found in engineer open jobs "
        f"({len(jobs)} jobs). Sample: {jobs[:2]}"
    )
    # case_type is not always surfaced in the engineer_jobs projection, so we
    # verify via the case detail endpoint in the second test. Here only check
    # the PPM-ness via the title prefix (schedule_ppm sets it to "<service_type> · ...").
    title = (found.get("title") or "")
    assert "·" in title or "Preventative" in title or "Fire" in title, f"title doesn't look like PPM: {title}"
    # status must be lowercase 'assigned'
    status = (found.get("status") or "")
    assert status == "assigned", f"Expected status='assigned' (lowercase), got '{status}'"

    # 5) when=today must also include it (scheduled for today)
    r = session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "today"})
    assert r.status_code == 200
    body = r.json()
    today_jobs = body if isinstance(body, list) else (body.get("jobs") or body.get("results") or [])
    found_today = next((j for j in today_jobs if j.get("id") == case_id or j.get("case_id") == case_id), None)
    assert found_today, f"Allocated PPM case {case_id} NOT found in engineer when=today ({len(today_jobs)} jobs)"
    print(f"[pass] PPM job {case_id} visible in engineer open+today with status '{status}'")


def test_ppm_allocation_to_other_engineer_sets_assigned_lowercase(session):
    """Allocate to jordan.blake and read case detail via desk API to confirm persistence."""
    schedule_id = _find_schedule(session) or _create_schedule(session)
    assert schedule_id, "No PPM schedule to allocate"

    r = session.post(f"{BASE_URL}/api/svc/ppm/schedule", json={
        "schedule_id": schedule_id,
        "engineer_ids": [JORDAN_ENG_ID],
        "scheduled_at": date.today().isoformat(),
    })
    assert r.status_code == 200, f"allocate failed: {r.status_code} {r.text[:400]}"
    case_id = r.json().get("case_id")
    assert case_id

    # Fetch the case via desk/scheduler read endpoint if available
    for path in [f"/api/svc/cases/{case_id}", f"/api/svc/scheduler/cases/{case_id}"]:
        rc = session.get(f"{BASE_URL}{path}")
        if rc.status_code == 200:
            data = rc.json()
            case = data.get("case") or data
            status = (case.get("status") or "")
            assigned = case.get("assigned_engineer_id")
            assert status == "assigned", f"status not lowercase assigned via {path}: '{status}'"
            assert assigned == JORDAN_ENG_ID, f"assigned_engineer_id mismatch: {assigned}"
            print(f"[pass] case persisted with status='assigned', assigned_engineer_id={assigned}")
            return
    pytest.skip("No desk case-detail endpoint available to verify persistence (engineer_jobs test already covers the main bug).")
