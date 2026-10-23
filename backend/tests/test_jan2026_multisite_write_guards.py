# Multi-site write guards retest: per-staff writes, shift writes and workforce-dashboard scoping
import os
from datetime import datetime, timezone, timedelta
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
SITE_A, SITE_B = "iso-demo-site-a", "iso-demo-site-b"
STAFF_B = "deptdemo-sales-b"
STAFF_A = "deptdemo-svc"


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "IsoDemo123!"},
                      headers={"X-RateLimit-Bypass": BYPASS}, timeout=30)
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


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _now_window():
    n = datetime.now(timezone.utc)
    a = max(n - timedelta(minutes=30), n.replace(hour=0, minute=0))
    b = min(n + timedelta(minutes=60), n.replace(hour=23, minute=59))
    return a.strftime("%H:%M"), b.strftime("%H:%M")


# ── Disposable Site B staff (created by owner) for destructive checks ──
@pytest.fixture(scope="module")
def temp_b(owner):
    r = owner.post(f"{BASE_URL}/api/staffing/staff", json={
        "full_name": "TEST_SiteB Temp", "email": "test_siteb_temp@isodemo.test",
        "site_ids": [SITE_B], "department": "Sales"}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    d = r.json()
    sid = (d.get("staff") or d).get("id")
    yield sid
    owner.delete(f"{BASE_URL}/api/staffing/staff/{sid}", timeout=30)


# ── 1. per-staff write guards ──
class TestStaffWrites:
    def test_mgr_patch_staff_b_403(self, manager):
        r = manager.patch(f"{BASE_URL}/api/staffing/staff/{STAFF_B}", json={"full_name": "Sid Sales B"}, timeout=30)
        assert r.status_code == 403, r.text[:200]

    def test_mgr_patch_hr_profile_b_403(self, manager, owner):
        cur = owner.get(f"{BASE_URL}/api/staffing/hr/profile/{STAFF_B}", timeout=30).json().get("city")
        r = manager.patch(f"{BASE_URL}/api/staffing/hr/profile/{STAFF_B}", json={"city": cur or "X"}, timeout=30)
        if r.status_code == 200 and not cur:
            owner.patch(f"{BASE_URL}/api/staffing/hr/profile/{STAFF_B}", json={"city": ""}, timeout=30)
        assert r.status_code == 403, r.text[:200]

    @pytest.mark.parametrize("method,path,body", [
        ("delete", "/api/staffing/staff/{id}", None),
        ("post", "/api/staffing/staff/{id}/issue-credentials", {}),
        ("post", "/api/staffing/staff/{id}/module-access/crm/grant", None),
        ("post", "/api/staffing/staff/{id}/module-access/crm/revoke", None),
        ("put", "/api/staffing/staff/{id}/dept-visibility", {"all_departments": False, "departments": []}),
        ("patch", "/api/staffing/offboarding/{id}", {}),
        ("post", "/api/staffing/offboarding/{id}/start", {}),
    ])
    def test_mgr_destructive_403_on_temp_b(self, manager, temp_b, method, path, body):
        r = getattr(manager, method)(BASE_URL + path.format(id=temp_b), json=body, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_owner_writes_temp_b_200(self, owner, temp_b):
        r = owner.patch(f"{BASE_URL}/api/staffing/staff/{temp_b}", json={"full_name": "TEST_SiteB Temp2"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        r = owner.patch(f"{BASE_URL}/api/staffing/hr/profile/{temp_b}", json={"city": "Leeds"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        r = owner.put(f"{BASE_URL}/api/staffing/staff/{temp_b}/dept-visibility",
                      json={"all_departments": False, "departments": []}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        r = owner.post(f"{BASE_URL}/api/staffing/staff/{temp_b}/issue-credentials", json={}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        r = owner.post(f"{BASE_URL}/api/staffing/staff/{temp_b}/module-access/crm/grant", timeout=30)
        assert r.status_code == 200, r.text[:200]
        r = owner.post(f"{BASE_URL}/api/staffing/staff/{temp_b}/module-access/crm/revoke", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_mgr_patch_own_site_staff_200(self, manager):
        cur = manager.get(f"{BASE_URL}/api/staffing/hr/profile/{STAFF_A}", timeout=30).json()
        r = manager.patch(f"{BASE_URL}/api/staffing/staff/{STAFF_A}", json={"full_name": cur["full_name"]}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        r = manager.patch(f"{BASE_URL}/api/staffing/hr/profile/{STAFF_A}", json={"city": cur.get("city") or "Manchester"}, timeout=30)
        assert r.status_code == 200, r.text[:200]

    # Code-review gaps: body.staff_id endpoints
    def test_mgr_add_hr_document_for_b_403(self, manager, owner, temp_b):
        r = manager.post(f"{BASE_URL}/api/staffing/hr/documents", json={
            "staff_id": temp_b, "name": "TEST_doc", "kind": "other", "url": "https://x.test/a.pdf"}, timeout=30)
        if r.status_code == 200:
            owner.delete(f"{BASE_URL}/api/staffing/hr/documents/{r.json().get('id')}", timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


# ── 2. shift guards ──
@pytest.fixture(scope="module")
def shifts(owner, manager):
    a, b = _now_window()
    made = {}
    r = owner.post(f"{BASE_URL}/api/staffing/shifts", json={"staff_id": STAFF_B, "site_id": SITE_B, "date": _today(),
                   "start_time": a, "end_time": b, "notes": "TEST_B"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    made["b"] = r.json()["shift"]["id"]
    r = owner.post(f"{BASE_URL}/api/staffing/shifts", json={"site_id": SITE_B, "date": _today(),
                   "start_time": "23:00", "end_time": "23:59", "notes": "TEST_B_open"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    made["b_open"] = r.json()["shift"]["id"]
    yield made
    for sid in made.values():
        owner.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30)


class TestShifts:
    def test_mgr_create_for_b_staff_403(self, manager, owner):
        r = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"staff_id": STAFF_B, "date": _today(),
                         "start_time": "10:00", "end_time": "11:00"}, timeout=30)
        if r.status_code == 200:
            owner.delete(f"{BASE_URL}/api/staffing/shifts/{r.json()['shift']['id']}")
        assert r.status_code == 403

    def test_mgr_create_open_on_b_403(self, manager, owner):
        r = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"site_id": SITE_B, "date": _today(),
                         "start_time": "10:00", "end_time": "11:00"}, timeout=30)
        if r.status_code == 200:
            owner.delete(f"{BASE_URL}/api/staffing/shifts/{r.json()['shift']['id']}")
        assert r.status_code == 403

    def test_mgr_patch_delete_move_b_403(self, manager, shifts):
        sid = shifts["b"]
        assert manager.patch(f"{BASE_URL}/api/staffing/shifts/{sid}", json={"notes": "x"}, timeout=30).status_code == 403
        assert manager.post(f"{BASE_URL}/api/staffing/shifts/{sid}/move", json={"staff_id": STAFF_A}, timeout=30).status_code == 403
        assert manager.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30).status_code == 403
        assert manager.patch(f"{BASE_URL}/api/staffing/shifts/{shifts['b_open']}", json={"notes": "x"}, timeout=30).status_code == 403

    def test_mgr_site_a_lifecycle(self, manager, owner):
        r = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"staff_id": STAFF_A, "site_id": SITE_A,
                         "date": _today(), "start_time": "06:00", "end_time": "07:00", "notes": "TEST_A"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        sid = r.json()["shift"]["id"]
        try:
            assert manager.patch(f"{BASE_URL}/api/staffing/shifts/{sid}", json={"notes": "TEST_A2"}, timeout=30).status_code == 200
            r2 = manager.post(f"{BASE_URL}/api/staffing/shifts/{sid}/move", json={"staff_id": "deptdemo-lead"}, timeout=30)
            assert r2.status_code == 200 and r2.json()["shift"]["staff_id"] == "deptdemo-lead"
            # moving onto Site B staff must be blocked
            assert manager.post(f"{BASE_URL}/api/staffing/shifts/{sid}/move", json={"staff_id": STAFF_B}, timeout=30).status_code == 403
            ro = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"site_id": SITE_A, "date": _today(),
                              "start_time": "06:00", "end_time": "07:00", "notes": "TEST_A_open"}, timeout=30)
            assert ro.status_code == 200 and ro.json()["shift"]["status"] == "open"
            assert manager.delete(f"{BASE_URL}/api/staffing/shifts/{ro.json()['shift']['id']}", timeout=30).status_code == 200
        finally:
            assert manager.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30).status_code == 200

    def test_mgr_cannot_repoint_site_a_shift_to_site_b(self, manager, owner):
        r = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"site_id": SITE_A, "date": _today(),
                         "start_time": "05:00", "end_time": "05:30", "notes": "TEST_A_repoint"}, timeout=30)
        sid = r.json()["shift"]["id"]
        try:
            rp = manager.patch(f"{BASE_URL}/api/staffing/shifts/{sid}", json={"site_id": SITE_B}, timeout=30)
            assert rp.status_code == 403, f"manager moved own shift to Site B: {rp.status_code}"
        finally:
            owner.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30)

    def test_owner_unaffected(self, owner, shifts):
        assert owner.patch(f"{BASE_URL}/api/staffing/shifts/{shifts['b']}", json={"notes": "TEST_B2"}, timeout=30).status_code == 200
        r = owner.post(f"{BASE_URL}/api/staffing/shifts/{shifts['b']}/move", json={"staff_id": STAFF_B}, timeout=30)
        assert r.status_code == 200


# ── 3. workforce dashboard ──
class TestDashboard:
    def test_mgr_dashboard_scoped(self, manager, shifts):
        vis = manager.get(f"{BASE_URL}/api/staffing/staff", timeout=30).json()
        vis = vis if isinstance(vis, list) else vis.get("staff") or vis.get("items")
        d = manager.get(f"{BASE_URL}/api/staffing/workforce-dashboard", timeout=60)
        assert d.status_code == 200
        j = d.json()
        assert j["kpis"]["active_staff"] == len([s for s in vis if s.get("active", True)])
        txt = d.text
        assert STAFF_B not in txt and "Sid Sales B" not in txt, "Site B staff in manager dashboard"
        assert shifts["b"] not in txt
        assert shifts["b_open"] not in txt, "Site B open shift leaked in open_shifts"
        for sec in ("on_now", "upcoming", "open_shifts"):
            for row in j.get(sec) or []:
                assert row.get("site_id") in (None, "", SITE_A), f"{sec}: {row.get('site_id')}"

    def test_mgr_dashboard_compliance_scoped(self, manager):
        vis = manager.get(f"{BASE_URL}/api/staffing/staff", timeout=30).json()
        vis = {s["id"] for s in (vis if isinstance(vis, list) else vis.get("staff") or vis.get("items"))}
        j = manager.get(f"{BASE_URL}/api/staffing/workforce-dashboard", timeout=60).json()
        extra = [c for c in ((j.get("compliance") or {}).get("top") or []) if c.get("staff_id") and c["staff_id"] not in vis]
        assert not extra, f"compliance has out-of-scope staff: {[(c['staff_id'], c.get('staff_name')) for c in extra]}"

    def test_owner_dashboard_full(self, owner, shifts):
        d = owner.get(f"{BASE_URL}/api/staffing/workforce-dashboard", timeout=60)
        j = d.json()
        assert j["kpis"]["active_staff"] >= 16
        assert shifts["b"] in d.text
        assert shifts["b_open"] in d.text


# ── 4. conflicts endpoint + bulk copy-week scoping ──
SRC_WEEK, TGT_WEEK = "2027-03-01", "2027-03-08"


@pytest.fixture(scope="module")
def b_overlap(owner):
    ids = []
    for st, en in (("09:00", "12:00"), ("10:00", "13:00")):
        r = owner.post(f"{BASE_URL}/api/staffing/shifts", json={"staff_id": STAFF_B, "site_id": SITE_B, "date": SRC_WEEK,
                       "start_time": st, "end_time": en, "notes": "TEST_B_overlap"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        ids.append(r.json()["shift"]["id"])
    yield ids
    for sid in ids:
        owner.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30)


class TestConflictsAndBulk:
    def test_conflicts_scoped(self, manager, owner, b_overlap):
        p = {"start_date": SRC_WEEK, "end_date": "2027-03-07"}
        ro = owner.get(f"{BASE_URL}/api/staffing/conflicts", params=p, timeout=30)
        assert ro.status_code == 200
        assert any(c.get("staff_id") == STAFF_B for c in ro.json()["conflicts"]), "owner should see Site B conflict"
        rm = manager.get(f"{BASE_URL}/api/staffing/conflicts", params=p, timeout=30)
        assert rm.status_code == 200
        assert not any(c.get("staff_id") == STAFF_B for c in rm.json()["conflicts"]), "Site B conflict leaked to manager"
        assert "Sid Sales B" not in rm.text

    def test_bulk_site_b_403(self, manager):
        r = manager.post(f"{BASE_URL}/api/staffing/shifts/bulk", json={"source_start": SRC_WEEK, "target_start": TGT_WEEK,
                         "site_id": SITE_B}, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_bulk_copies_only_site_a(self, manager, owner, b_overlap):
        ra = manager.post(f"{BASE_URL}/api/staffing/shifts", json={"staff_id": STAFF_A, "site_id": SITE_A, "date": SRC_WEEK,
                          "start_time": "06:00", "end_time": "07:00", "notes": "TEST_A_bulk"}, timeout=30)
        assert ra.status_code == 200, ra.text[:200]
        a_id = ra.json()["shift"]["id"]
        created = []
        try:
            r = manager.post(f"{BASE_URL}/api/staffing/shifts/bulk", json={"source_start": SRC_WEEK, "target_start": TGT_WEEK},
                             timeout=30)
            assert r.status_code == 200, r.text[:200]
            created = r.json()["created_ids"]
            assert r.json()["created_count"] >= 1
            rows = owner.get(f"{BASE_URL}/api/staffing/shifts", params={"date_from": TGT_WEEK, "date_to": "2027-03-14"},
                             timeout=30).json()
            rows = rows if isinstance(rows, list) else rows.get("shifts") or rows.get("items") or []
            mine = [s for s in rows if s["id"] in created]
            assert len(mine) == len(created)
            assert all(s.get("site_id") != SITE_B and s.get("staff_id") != STAFF_B for s in mine), \
                f"bulk copied Site B: {[(s.get('site_id'), s.get('staff_id')) for s in mine]}"
            assert any(s.get("notes") == "TEST_A_bulk" for s in mine)
        finally:
            for sid in created + [a_id]:
                owner.delete(f"{BASE_URL}/api/staffing/shifts/{sid}", timeout=30)
