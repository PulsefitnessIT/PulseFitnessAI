"""Tests for Dept Permissions (grant-based cross-dept visibility) — Jan 2026."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
PWD = "IsoDemo123!"
MGR_STAFF_ID = "996e6ae6-2ea4-4ead-a3e3-ebf7f43ed396"
LEAD_STAFF_ID = "deptdemo-lead"


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response for {email}: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def tokens():
    return {
        "owner": _login("owner@isodemo.com"),
        "manager": _login("manager@isodemo.com"),
        "lead": _login("lead@isodemo.com"),
    }


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- cleanup: ensure baseline before + after ----
def _clear_grants(owner_tok):
    for sid in (MGR_STAFF_ID, LEAD_STAFF_ID):
        requests.put(f"{BASE_URL}/api/staffing/staff/{sid}/dept-visibility", json={}, headers=_h(owner_tok), timeout=15)
    # revert manager row primary_role=manager
    requests.patch(f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}", json={"primary_role": "manager"}, headers=_h(owner_tok), timeout=15)


@pytest.fixture(scope="module", autouse=True)
def _baseline(tokens):
    _clear_grants(tokens["owner"])
    yield
    _clear_grants(tokens["owner"])


# ---------- GET /my-visibility ----------
class TestMyVisibility:
    def test_owner_sees_all(self, tokens):
        r = requests.get(f"{BASE_URL}/api/staffing/my-visibility", headers=_h(tokens["owner"]), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sees_all") is True
        assert d.get("can_grant") is True

    def test_manager_shape(self, tokens):
        r = requests.get(f"{BASE_URL}/api/staffing/my-visibility", headers=_h(tokens["manager"]), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("sees_all", "own_department", "grant", "has_grant", "can_grant"):
            assert k in d, f"missing key {k}: {d}"
        assert d["can_grant"] is False
        assert d["has_grant"] is False

    def test_lead_shape(self, tokens):
        r = requests.get(f"{BASE_URL}/api/staffing/my-visibility", headers=_h(tokens["lead"]), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["can_grant"] is False


# ---------- PUT /staff/{id}/dept-visibility auth ----------
class TestSetDeptVisibilityAuth:
    def test_plain_manager_forbidden(self, tokens):
        r = requests.put(
            f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
            json={"all_departments": True, "departments": []},
            headers=_h(tokens["manager"]),
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"

    def test_unknown_department_rejected(self, tokens):
        r = requests.put(
            f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
            json={"all_departments": False, "departments": ["NotARealDept_xyz"]},
            headers=_h(tokens["owner"]),
            timeout=15,
        )
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_empty_body_clears(self, tokens):
        # set then clear
        r = requests.put(
            f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
            json={"all_departments": False, "departments": ["Sales"]},
            headers=_h(tokens["owner"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        r2 = requests.put(
            f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
            json={}, headers=_h(tokens["owner"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        # verify cleared
        v = requests.get(f"{BASE_URL}/api/staffing/my-visibility", headers=_h(tokens["manager"]), timeout=15).json()
        assert v.get("has_grant") in (False, None), v


# ---------- GET /staffing/staff manager scope ----------
def _names(staff_list):
    return {(s.get("full_name") or s.get("name") or "").strip() for s in staff_list}


class TestManagerStaffScope:
    def test_manager_initial_service_only(self, tokens):
        r = requests.get(f"{BASE_URL}/api/staffing/staff", headers=_h(tokens["manager"]), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        staff = data if isinstance(data, list) else data.get("items") or data.get("staff") or []
        names = _names(staff)
        # must include Service staff at Site A
        assert any("Sam Service A" in n for n in names), f"expected Sam Service A in {names}"
        # must NOT include Sales/Warehouse/IT yet
        assert not any("Sally Sales" in n for n in names), f"Sally Sales leaked: {names}"
        assert not any("Wendy Warehouse" in n for n in names), f"Wendy Warehouse leaked: {names}"
        assert not any("Sid Sales B" in n for n in names), f"Site B leak: {names}"

    def test_manager_after_grant_sales_warehouse(self, tokens):
        g = requests.put(
            f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
            json={"all_departments": False, "departments": ["Sales", "Warehouse"]},
            headers=_h(tokens["owner"]), timeout=15,
        )
        assert g.status_code == 200, g.text
        r = requests.get(f"{BASE_URL}/api/staffing/staff", headers=_h(tokens["manager"]), timeout=20)
        assert r.status_code == 200
        staff = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("staff") or []
        names = _names(staff)
        assert any("Sally Sales A" in n for n in names), f"Sally Sales A missing after grant: {names}"
        assert any("Wendy Warehouse A" in n for n in names), f"Wendy Warehouse A missing: {names}"
        assert not any("Sid Sales B" in n for n in names), f"Site B must not leak: {names}"
        assert not any("Ian IT A" in n for n in names), f"IT not granted: {names}"
        # cleanup grant
        requests.put(f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}/dept-visibility",
                     json={}, headers=_h(tokens["owner"]), timeout=15)


# ---------- lead@isodemo.com (platform staff role) ----------
class TestLeadStaffScope:
    def test_lead_no_grant_sees_self_only(self, tokens):
        # ensure cleared
        requests.put(f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
                     json={}, headers=_h(tokens["owner"]), timeout=15)
        r = requests.get(f"{BASE_URL}/api/staffing/staff", headers=_h(tokens["lead"]), timeout=20)
        # may be 200 with 1 row OR 403; both are acceptable self-only semantics — but spec says "sees only self"
        assert r.status_code == 200, r.text
        staff = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("staff") or []
        names = _names(staff)
        # should contain only lead/self
        assert len(staff) <= 1, f"expected only self, got {names}"

    def test_lead_with_all_depts_grant_sees_site_a_only(self, tokens):
        g = requests.put(
            f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
            json={"all_departments": True, "departments": []},
            headers=_h(tokens["owner"]), timeout=15,
        )
        assert g.status_code == 200, g.text
        r = requests.get(f"{BASE_URL}/api/staffing/staff", headers=_h(tokens["lead"]), timeout=20)
        assert r.status_code == 200, r.text
        staff = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("staff") or []
        names = _names(staff)
        assert any("Ian IT A" in n for n in names), f"Ian IT A missing with all_depts: {names}"
        assert not any("Sid Sales B" in n for n in names), f"Site B leaked: {names}"
        # sensitive fields stripped
        for s in staff:
            for banned in ("bank_sort_code", "bank_account_number", "national_insurance", "address", "hourly_cost"):
                assert banned not in s or s[banned] in (None, ""), f"{banned} leaked: {s}"

    def test_lead_hr_profile_allowed_site_a_blocked_site_b(self, tokens):
        # Need a grant for lead to use hr profile endpoints
        requests.put(
            f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
            json={"all_departments": True, "departments": []},
            headers=_h(tokens["owner"]), timeout=15,
        )
        ok = requests.get(f"{BASE_URL}/api/staffing/hr/profile/deptdemo-sales-a",
                          headers=_h(tokens["lead"]), timeout=15)
        assert ok.status_code == 200, f"sales-a should work: {ok.status_code} {ok.text}"
        prof = ok.json()
        for banned in ("bank_sort_code", "bank_account_number", "national_insurance"):
            assert banned not in prof or prof[banned] in (None, ""), f"{banned} leaked in profile"
        bad = requests.get(f"{BASE_URL}/api/staffing/hr/profile/deptdemo-sales-b",
                           headers=_h(tokens["lead"]), timeout=15)
        assert bad.status_code == 403, f"sales-b should be 403: {bad.status_code} {bad.text}"

    def test_lead_cannot_patch_staff(self, tokens):
        r = requests.patch(
            f"{BASE_URL}/api/staffing/staff/deptdemo-sales-a",
            json={"notes": "hack"},
            headers=_h(tokens["lead"]), timeout=15,
        )
        assert r.status_code == 403, f"lead must not PATCH: {r.status_code}"
        # cleanup grant
        requests.put(f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
                     json={}, headers=_h(tokens["owner"]), timeout=15)


# ---------- HR job-role user can grant ----------
class TestHRJobRoleCanGrant:
    def test_hr_role_can_grant(self, tokens):
        # Promote manager row to primary_role=hr
        p = requests.patch(f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}",
                           json={"primary_role": "hr"}, headers=_h(tokens["owner"]), timeout=15)
        assert p.status_code == 200, p.text
        # Re-login as that user (role in token may need refresh)
        tok = _login("manager@isodemo.com")
        v = requests.get(f"{BASE_URL}/api/staffing/my-visibility", headers=_h(tok), timeout=15).json()
        assert v.get("can_grant") is True, f"HR job role should grant: {v}"
        # try PUT (grant someone else — use lead)
        r = requests.put(f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
                         json={"all_departments": False, "departments": ["Sales"]},
                         headers=_h(tok), timeout=15)
        assert r.status_code == 200, f"HR role PUT should succeed: {r.status_code} {r.text}"
        # revert
        requests.put(f"{BASE_URL}/api/staffing/staff/{LEAD_STAFF_ID}/dept-visibility",
                     json={}, headers=_h(tokens["owner"]), timeout=15)
        rev = requests.patch(f"{BASE_URL}/api/staffing/staff/{MGR_STAFF_ID}",
                             json={"primary_role": "manager"}, headers=_h(tokens["owner"]), timeout=15)
        assert rev.status_code == 200
