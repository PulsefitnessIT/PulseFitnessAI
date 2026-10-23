# Retest: per-staff staffing endpoints site-scope (403 for manager on Site B, 200 for owner + manager own-site staff)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SITE_B_ID = "deptdemo-sales-b"
PER_STAFF = ["/api/staffing/hr/profile/{id}", "/api/staffing/staff/{id}/employee-file",
             "/api/staffing/staff/{id}/module-access"]
LISTS = ["/api/staffing/clock/board", "/api/staffing/performance", "/api/staffing/team/module-matrix",
         "/api/staffing/compliance/tracker", "/api/staffing/ai/absence-risk"]


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "IsoDemo123!"}, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed {email}: {r.status_code}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login("owner@isodemo.com")


@pytest.fixture(scope="module")
def manager():
    return _login("manager@isodemo.com")


def _staff(sess):
    r = sess.get(f"{BASE_URL}/api/staffing/staff", timeout=30)
    assert r.status_code == 200
    d = r.json()
    return d if isinstance(d, list) else d.get("staff") or d.get("items") or []


@pytest.mark.parametrize("tpl", PER_STAFF)
def test_manager_403_site_b(manager, tpl):
    r = manager.get(BASE_URL + tpl.format(id=SITE_B_ID), timeout=60)
    assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("tpl", PER_STAFF)
def test_owner_200_site_b(owner, tpl):
    r = owner.get(BASE_URL + tpl.format(id=SITE_B_ID), timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("tpl", PER_STAFF)
def test_manager_200_own_site_staff(manager, tpl):
    staff = [s for s in _staff(manager) if s.get("id") != SITE_B_ID]
    assert staff, "manager sees no staff"
    sid = staff[0]["id"]
    r = manager.get(BASE_URL + tpl.format(id=sid), timeout=60)
    assert r.status_code == 200, f"{sid}: {r.status_code} {r.text[:200]}"


def test_owner_sees_site_b_in_lists(owner):
    hits = []
    for p in LISTS:
        r = owner.get(BASE_URL + p, timeout=60)
        assert r.status_code == 200, f"{p} {r.status_code}"
        if SITE_B_ID in r.text or "Sid Sales B" in r.text:
            hits.append(p)
    print("owner lists containing Site B:", hits)
    assert hits, "owner sees Site B staff in none of the list endpoints"


def test_manager_lists_subset_of_staff(manager):
    visible = {s.get("id") for s in _staff(manager)}
    import re
    for p in LISTS:
        r = manager.get(BASE_URL + p, timeout=60)
        assert r.status_code == 200, f"{p} {r.status_code}"
        ids = set(re.findall(r'"staff(?:_member)?_id"\s*:\s*"([^"]+)"', r.text))
        extra = ids - visible
        assert not extra, f"{p} returns staff not in manager's /staff list: {extra}"


# ---- Write-scope + workforce dashboard (expected to FAIL until the main agent adds assert_staff_visible) ----
def test_manager_cannot_patch_site_b_staff(manager):
    # no-op name write; must be 403 for out-of-scope staff
    r = manager.patch(f"{BASE_URL}/api/staffing/staff/{SITE_B_ID}", json={"full_name": "Sid Sales B"}, timeout=30)
    assert r.status_code in (403, 404), f"manager PATCH Site B staff -> {r.status_code}"


def test_manager_cannot_create_shift_for_site_b(manager, owner):
    from datetime import date
    r = manager.post(f"{BASE_URL}/api/staffing/shifts", json={
        "staff_id": SITE_B_ID, "date": date.today().isoformat(), "start_time": "00:00",
        "end_time": "00:30", "notes": "TEST_scope"}, timeout=30)
    if r.status_code == 200:
        owner.delete(f"{BASE_URL}/api/staffing/shifts/{r.json()['shift']['id']}", timeout=30)
    assert r.status_code in (403, 404), f"manager created shift for Site B staff -> {r.status_code}"


def test_workforce_dashboard_scoped(manager, owner):
    from datetime import date
    s = owner.post(f"{BASE_URL}/api/staffing/shifts", json={
        "staff_id": SITE_B_ID, "site_id": "iso-demo-site-b", "date": date.today().isoformat(),
        "start_time": "00:00", "end_time": "23:59", "notes": "TEST_scope"}, timeout=30).json()["shift"]["id"]
    try:
        r = manager.get(f"{BASE_URL}/api/staffing/workforce-dashboard", timeout=30)
        assert r.status_code == 200
        assert "Sid Sales B" not in r.text and SITE_B_ID not in r.text, "workforce-dashboard leaks Site B staff"
        assert r.json()["kpis"]["active_staff"] == len(_staff(manager)), "active_staff KPI not scoped"
    finally:
        owner.delete(f"{BASE_URL}/api/staffing/shifts/{s}", timeout=30)
