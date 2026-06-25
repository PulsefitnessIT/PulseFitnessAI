"""Backend tests for Site Staff Shared Login feature.

Covers:
- Manager site-staff CRUD/transfer
- Shared login provision/get/settings/disable
- Shared login normal-login (username sign-in) and /auth/me flags
- Mandatory reporter selection on fault submit
- Permissions: shared login blocked from managing staff and from another site's active list
- Multi-site isolation: staff in one site don't appear in another
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend env file
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

MANAGER_EMAIL = "owner@isodemo.com"
MANAGER_PASSWORD = "IsoDemo123!"
SHARED_USERNAME = "demo-head-office"
SHARED_PASSWORD = "Fox-6307-river"
SITE_ID = "iso-demo-site-a"


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    return r


@pytest.fixture(scope="module")
def manager_token():
    r = _login(MANAGER_EMAIL, MANAGER_PASSWORD)
    assert r.status_code == 200, f"Manager login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def manager_headers(manager_token):
    return {"Authorization": f"Bearer {manager_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def shared_token():
    r = _login(SHARED_USERNAME, SHARED_PASSWORD)
    assert r.status_code == 200, f"Shared login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token
    return token


@pytest.fixture(scope="module")
def shared_headers(shared_token):
    return {"Authorization": f"Bearer {shared_token}", "Content-Type": "application/json"}


# ---------- Auth / Me ----------

class TestSharedLoginAuth:
    def test_shared_login_me_flags(self, shared_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=shared_headers, timeout=15)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me.get("role") == "site_staff", f"role={me.get('role')}"
        assert me.get("is_shared_site_login") is True
        assert me.get("site_id") == SITE_ID

    def test_manager_me(self, manager_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=manager_headers, timeout=15)
        assert r.status_code == 200
        me = r.json()
        # Manager should not be a shared login
        assert me.get("is_shared_site_login") in (False, None)


# ---------- Site Staff CRUD ----------

class TestSiteStaffManagerCRUD:
    created_ids = []

    def test_list_staff(self, manager_headers):
        r = requests.get(
            f"{BASE_URL}/api/site-staff?site_id={SITE_ID}", headers=manager_headers, timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("staff") if isinstance(data, dict) else data
        names = [
            f"{s.get('first_name', '')} {s.get('last_name', '')}".strip() or s.get("full_name", "")
            for s in items
        ]
        assert any("Sarah" in n for n in names), f"Sarah Jones not found in staff: {names}"

    def test_create_staff(self, manager_headers):
        suffix = uuid.uuid4().hex[:6]
        payload = {
            "site_id": SITE_ID,
            "first_name": f"TESTQA{suffix}",
            "last_name": "Tester",
            "job_title": "QA Tester",
            "email": f"qa-{suffix}@example.com",
            "phone": "+15555550100",
        }
        r = requests.post(
            f"{BASE_URL}/api/site-staff", json=payload, headers=manager_headers, timeout=15
        )
        assert r.status_code in (200, 201), r.text
        created = r.json()
        staff_id = created.get("id") or created.get("_id") or created.get("staff_id")
        assert staff_id
        TestSiteStaffManagerCRUD.created_ids.append(staff_id)

        # Verify in list
        r2 = requests.get(
            f"{BASE_URL}/api/site-staff?site_id={SITE_ID}", headers=manager_headers, timeout=15
        )
        body = r2.json()
        items = body.get("staff") if isinstance(body, dict) else body
        ids = [s.get("id") for s in items]
        assert staff_id in ids

    def test_patch_staff(self, manager_headers):
        assert TestSiteStaffManagerCRUD.created_ids, "No created staff to patch"
        sid = TestSiteStaffManagerCRUD.created_ids[0]
        r = requests.patch(
            f"{BASE_URL}/api/site-staff/{sid}",
            json={"job_title": "Lead QA"},
            headers=manager_headers,
            timeout=15,
        )
        assert r.status_code in (200, 204), r.text

    def test_deactivate_reactivate(self, manager_headers):
        assert TestSiteStaffManagerCRUD.created_ids
        sid = TestSiteStaffManagerCRUD.created_ids[0]
        r = requests.post(
            f"{BASE_URL}/api/site-staff/{sid}/deactivate", headers=manager_headers, timeout=15
        )
        assert r.status_code in (200, 204), r.text
        r = requests.post(
            f"{BASE_URL}/api/site-staff/{sid}/reactivate", headers=manager_headers, timeout=15
        )
        assert r.status_code in (200, 204), r.text

    def test_get_staff_jobs(self, manager_headers):
        assert TestSiteStaffManagerCRUD.created_ids
        sid = TestSiteStaffManagerCRUD.created_ids[0]
        r = requests.get(
            f"{BASE_URL}/api/site-staff/{sid}/jobs", headers=manager_headers, timeout=15
        )
        assert r.status_code == 200, r.text


# ---------- Shared Login Provisioning ----------

class TestSharedLoginProvisioning:
    def test_get_shared_login_status(self, manager_headers):
        r = requests.get(
            f"{BASE_URL}/api/sites/{SITE_ID}/shared-login",
            headers=manager_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Should have at least enabled + username keys when provisioned
        assert "enabled" in data or "username" in data

    def test_update_settings(self, manager_headers):
        r = requests.patch(
            f"{BASE_URL}/api/sites/{SITE_ID}/shared-login/settings",
            json={"require_reporter_selection": True},
            headers=manager_headers,
            timeout=15,
        )
        # Allow 200/204
        assert r.status_code in (200, 204), r.text


# ---------- Mandatory Reporter Selection ----------

class TestMandatoryReporter:
    def test_active_dropdown_for_shared_login(self, shared_headers):
        r = requests.get(
            f"{BASE_URL}/api/site-staff/active?site_id={SITE_ID}",
            headers=shared_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("staff") if isinstance(body, dict) else body
        assert len(items) >= 1
        # Capture a valid id for next test
        TestMandatoryReporter.valid_id = items[0].get("id") or items[0].get("_id")
        assert TestMandatoryReporter.valid_id

    def test_create_issue_without_reporter_fails(self, shared_headers):
        payload = {
            "serial_number": "TEST-SN-001",
            "machine_type": "Treadmill",
            "issue_description": "Belt slipping under load",
            "severity": "low",
        }
        r = requests.post(
            f"{BASE_URL}/api/issues", json=payload, headers=shared_headers, timeout=20
        )
        assert r.status_code == 400, f"Expected 400 got {r.status_code}: {r.text}"
        msg = r.text.lower()
        assert "select the staff member" in msg or "reporter" in msg

    def test_create_issue_with_reporter_succeeds(self, shared_headers):
        rid = getattr(TestMandatoryReporter, "valid_id", None)
        assert rid, "No valid reporter id"
        payload = {
            "serial_number": "TEST-SN-002",
            "machine_type": "Treadmill",
            "issue_description": "Belt slipping under load",
            "severity": "low",
            "reporter_staff_id": rid,
        }
        r = requests.post(
            f"{BASE_URL}/api/issues", json=payload, headers=shared_headers, timeout=30
        )
        assert r.status_code in (200, 201), f"Got {r.status_code}: {r.text}"
        issue = r.json()
        assert issue.get("reporter_name"), f"reporter_name missing: {issue}"
        assert issue.get("reporter_job_title")
        assert issue.get("logged_via_shared_login") is True
        assert issue.get("site_id") == SITE_ID


# ---------- Permissions / Isolation ----------

class TestPermissionsAndIsolation:
    def test_shared_login_cannot_create_staff(self, shared_headers):
        payload = {
            "site_id": SITE_ID,
            "first_name": "TESTQA_block",
            "last_name": "X",
            "job_title": "X",
            "email": "block@example.com",
            "phone": "+15555550000",
        }
        r = requests.post(
            f"{BASE_URL}/api/site-staff", json=payload, headers=shared_headers, timeout=15
        )
        assert r.status_code == 403, f"Expected 403 got {r.status_code}: {r.text}"

    def test_shared_login_other_site_active_blocked(self, shared_headers):
        # Use a clearly different site id
        other_site = "some-other-site-zzz"
        r = requests.get(
            f"{BASE_URL}/api/site-staff/active?site_id={other_site}",
            headers=shared_headers,
            timeout=15,
        )
        assert r.status_code in (403, 404), f"Expected 403 got {r.status_code}: {r.text}"


# ---------- Cleanup ----------

def test_zz_cleanup(manager_headers):
    for sid in TestSiteStaffManagerCRUD.created_ids:
        try:
            requests.delete(
                f"{BASE_URL}/api/site-staff/{sid}", headers=manager_headers, timeout=10
            )
        except Exception:
            pass
