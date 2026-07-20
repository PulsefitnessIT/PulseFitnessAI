"""Backend tests for Staff Portal (activated employees) + provisioning flows.

Covers:
  - Employee /api/new-starter/portal/{rota,timesheet,timesheet/edit,holidays,documents,access}
  - HR /api/staff-onboarding/managers + assign line-manager on case
  - Line manager /api/staffing/access/my-reports + grant modules

Prereq: seed_staff_portal_demo.py has been run to populate:
  portal.staff@pulsedemo.test / Staff123!
  portal.manager@pulsedemo.test / Manager123!
  owner@isodemo.com / IsoDemo123!
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

STAFF_EMAIL = "portal.staff@pulsedemo.test"
STAFF_PASS = "Staff123!"
MGR_EMAIL = "portal.manager@pulsedemo.test"
MGR_PASS = "Manager123!"
HR_EMAIL = "owner@isodemo.com"
HR_PASS = "IsoDemo123!"


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": STAFF_EMAIL, "password": STAFF_PASS})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def hr_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": HR_EMAIL, "password": HR_PASS})
    if r.status_code == 429:
        time.sleep(40)
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": HR_EMAIL, "password": HR_PASS})
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def mgr_token():
    time.sleep(40)  # avoid 429 (rate limit)
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": MGR_EMAIL, "password": MGR_PASS})
    if r.status_code == 429:
        time.sleep(45)
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": MGR_EMAIL, "password": MGR_PASS})
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ── Employee ────────────────────────────────────────
class TestEmployeePortal:
    def test_me_activated(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/new-starter/me", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert d.get("activated") is True

    def test_rota(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/new-starter/portal/rota", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert "shifts" in d
        # seed creates 4 shifts
        assert len(d["shifts"]) >= 4
        s = d["shifts"][0]
        assert s.get("start_time") == "09:00"
        assert s.get("end_time") == "17:00"

    def test_timesheet_and_edit(self, staff_token):
        # get current week — use today's monday
        from datetime import date, timedelta
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        ws = monday.isoformat()
        r = requests.get(f"{BASE_URL}/api/new-starter/portal/timesheet?week_start={ws}",
                         headers=H(staff_token))
        assert r.status_code == 200
        ts = r.json()
        assert "line_items" in ts

        # submit correction
        r2 = requests.post(f"{BASE_URL}/api/new-starter/portal/timesheet/edit",
                           headers=H(staff_token),
                           json={"week_start": ws, "note": "TEST_correction from pytest"})
        assert r2.status_code == 200, r2.text
        assert r2.json().get("status") == "disputed"

        # re-fetch and confirm disputed
        r3 = requests.get(f"{BASE_URL}/api/new-starter/portal/timesheet?week_start={ws}",
                          headers=H(staff_token))
        assert r3.status_code == 200
        assert r3.json().get("approval_status") == "disputed"

    def test_holidays_get_and_create_cancel(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/new-starter/portal/holidays", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert "mine" in d and "team" in d and "allowance" in d
        assert d["allowance"].get("total") == 28
        # department team calendar — Jamie Fox approved
        team_names = [t.get("full_name") for t in d.get("team", [])]
        assert any("Jamie" in (n or "") for n in team_names), f"Team calendar missing Jamie: {team_names}"

        # create request
        from datetime import date, timedelta
        s = (date.today() + timedelta(days=60)).isoformat()
        e = (date.today() + timedelta(days=62)).isoformat()
        r2 = requests.post(f"{BASE_URL}/api/new-starter/portal/holidays", headers=H(staff_token),
                           json={"start_date": s, "end_date": e, "note": "TEST_ pytest holiday"})
        assert r2.status_code == 200, r2.text
        new_id = r2.json()["id"]
        assert r2.json()["status"] == "pending"

        # cancel it
        r3 = requests.delete(f"{BASE_URL}/api/new-starter/portal/holidays/{new_id}",
                             headers=H(staff_token))
        assert r3.status_code == 200

    def test_documents(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/new-starter/portal/documents", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert d.get("offer_available") is True
        assert d.get("contract_available") is True

    def test_access(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/new-starter/portal/access", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert "modules" in d
        # line manager assigned by seed
        assert d.get("line_manager") and "Morgan" in d["line_manager"]
        # 4 org modules
        keys = {m["key"] for m in d["modules"]}
        assert {"operations", "crm", "marketing", "memberships"}.issubset(keys)


# ── HR ────────────────────────────────────────
class TestHR:
    def test_list_managers(self, hr_token):
        r = requests.get(f"{BASE_URL}/api/staff-onboarding/managers", headers=H(hr_token))
        assert r.status_code == 200
        mgrs = r.json().get("managers", [])
        assert any("Morgan" in (m.get("full_name") or "") for m in mgrs)

    def test_get_and_assign_line_manager(self, hr_token):
        # get current
        r = requests.get(f"{BASE_URL}/api/staff-onboarding/cases/SPDEMO_case/line-manager",
                         headers=H(hr_token))
        assert r.status_code == 200
        cur = r.json()
        cur_id = cur.get("line_manager_staff_id")
        assert cur_id  # already assigned by seed

        # re-assign same to ensure idempotency
        r2 = requests.post(f"{BASE_URL}/api/staff-onboarding/cases/SPDEMO_case/line-manager",
                           headers=H(hr_token),
                           json={"line_manager_staff_id": cur_id})
        assert r2.status_code == 200


# ── Line manager ────────────────────────────────────────
class TestLineManager:
    def test_my_reports_and_grant(self, mgr_token, staff_token):
        r = requests.get(f"{BASE_URL}/api/staffing/access/my-reports", headers=H(mgr_token))
        assert r.status_code == 200, r.text
        d = r.json()
        reports = d.get("reports", [])
        assert any("Alex" in (x.get("full_name") or "") for x in reports), f"reports: {reports}"
        alex = next(x for x in reports if "Alex" in (x.get("full_name") or ""))

        # grant CRM + Operations
        r2 = requests.post(
            f"{BASE_URL}/api/staffing/access/reports/{alex['staff_id']}/modules",
            headers=H(mgr_token),
            json={"modules": ["crm", "operations"]})
        assert r2.status_code == 200, r2.text
        assert set(r2.json().get("granted_modules", [])) == {"crm", "operations"}

        # verify from staff perspective
        r3 = requests.get(f"{BASE_URL}/api/new-starter/portal/access", headers=H(staff_token))
        assert r3.status_code == 200
        mods = {m["key"]: m["granted"] for m in r3.json()["modules"]}
        assert mods.get("crm") is True
        assert mods.get("operations") is True
        assert r3.json().get("status") == "granted"
