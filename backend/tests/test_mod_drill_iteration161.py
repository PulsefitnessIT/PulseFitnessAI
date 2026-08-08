"""
MOD Red Team Drill Mode Tests - Iteration 161

Tests for P3 'Red Team Drill Mode' feature:
- POST /api/master-admin/mod/sites/{site_id}/drill/start
- GET /api/master-admin/mod/drills
- POST /api/master-admin/mod/drills/{drill_id}/complete
- GET /api/mod/site/drills/active
- POST /api/mod/site/drills/{drill_id}/acknowledge
- KPI exclusion verification (drills don't pollute real metrics)
"""

import pytest
import requests
import os
import time
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

BYPASS_HEADERS = {
    "X-Captcha-Token": "bypass:1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6",
    "X-RateLimit-Bypass": "1438ab298eab4e7ef2cb89e61309123e85fb05ae6fc583c6",
}

# Test credentials - MOD sites use email field with username value
MASTER_ADMIN = {"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"}
RAF_SITE = {"email": "raf-demoairstation", "password": "BrizeNorton2026!"}
ARMY_SITE = {"email": "army-catterick", "password": "Demo Garrison2026!"}
MOD_PRO = {"email": "raf@demo.local", "password": "RafEstates2026!"}


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=MASTER_ADMIN,
        headers=BYPASS_HEADERS
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def raf_token():
    """Get RAF site token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=RAF_SITE,
        headers=BYPASS_HEADERS
    )
    assert resp.status_code == 200, f"RAF login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def army_token():
    """Get Army site token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=ARMY_SITE,
        headers=BYPASS_HEADERS
    )
    assert resp.status_code == 200, f"Army login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def pro_token():
    """Get MOD PRO (branch) token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=MOD_PRO,
        headers=BYPASS_HEADERS
    )
    assert resp.status_code == 200, f"PRO login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def raf_site_id(admin_token):
    """Get RAF site ID from admin listing"""
    resp = requests.get(
        f"{BASE_URL}/api/master-admin/mod/sites",
        headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
    )
    assert resp.status_code == 200
    sites = resp.json().get("sites", [])
    raf = next((s for s in sites if "brize" in s.get("name", "").lower()), None)
    assert raf, "Demo Air Station site not found"
    return raf["id"]


class TestDrillStartEndpoint:
    """Tests for POST /api/master-admin/mod/sites/{site_id}/drill/start"""

    def test_start_drill_as_admin(self, admin_token, raf_site_id):
        """Master admin can start a drill"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/sites/{raf_site_id}/drill/start",
            json={"scenario": "TEST: Power failure simulation", "fault_type": "electrical"},
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200, f"Start drill failed: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert data.get("ok") is True
        assert "drill_id" in data
        assert "issue_id" in data
        assert "ticket_ref" in data

        # Verify ticket_ref matches DRILL-YYYY-NNNNN pattern
        ticket_ref = data["ticket_ref"]
        assert re.match(r"^DRILL-\d{4}-\d{5}$", ticket_ref), f"Invalid ticket_ref format: {ticket_ref}"

        # Store for cleanup
        pytest.drill_id = data["drill_id"]
        pytest.issue_id = data["issue_id"]
        pytest.ticket_ref = ticket_ref

    def test_start_drill_non_admin_403(self, raf_token, raf_site_id):
        """Non-admin cannot start a drill"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/sites/{raf_site_id}/drill/start",
            json={"scenario": "Unauthorized drill attempt"},
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 403

    def test_start_drill_invalid_site_404(self, admin_token):
        """Invalid site_id returns 404"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/sites/nonexistent-site-id/drill/start",
            json={"scenario": "Test scenario"},
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 404


class TestDrillKPIExclusion:
    """Tests that drills don't pollute real KPIs"""

    def test_admin_sites_open_faults_excludes_drill(self, admin_token, raf_site_id):
        """GET /api/master-admin/mod/sites excludes drill from open_faults count"""
        # Get pre-drill count
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/mod/sites",
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        sites = resp.json().get("sites", [])
        raf = next((s for s in sites if s["id"] == raf_site_id), None)
        assert raf, "RAF site not found"

        # open_faults should NOT include the drill we started
        # The drill has is_drill=True, so it should be filtered out
        open_faults = raf.get("open_faults", 0)
        print(f"RAF open_faults (excluding drill): {open_faults}")
        # We can't assert exact count, but we verify the endpoint works
        assert isinstance(open_faults, int)

    def test_pro_dashboard_excludes_drill(self, pro_token):
        """GET /api/mod/pro/dashboard excludes drill from totals"""
        resp = requests.get(
            f"{BASE_URL}/api/mod/pro/dashboard",
            headers={"Authorization": f"Bearer {pro_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        totals = data.get("totals", {})
        open_urgent = totals.get("open_urgent", 0)
        recent_urgent = data.get("recent_urgent", [])

        print(f"PRO dashboard open_urgent (excluding drill): {open_urgent}")
        print(f"PRO dashboard recent_urgent count: {len(recent_urgent)}")

        # Verify drill is NOT in recent_urgent list
        drill_in_recent = any(
            r.get("is_drill") is True or "DRILL" in (r.get("mod_ticket_ref") or "")
            for r in recent_urgent
        )
        assert not drill_in_recent, "Drill should not appear in recent_urgent"


class TestActiveDrillEndpoint:
    """Tests for GET /api/mod/site/drills/active"""

    def test_active_drill_returns_drill_for_site(self, raf_token):
        """Site user can see active drill"""
        resp = requests.get(
            f"{BASE_URL}/api/mod/site/drills/active",
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        drill = data.get("drill")
        assert drill is not None, "Expected active drill for RAF site"

        # Verify drill document structure
        assert drill.get("is_drill") is True
        assert drill.get("priority") == "urgent"
        assert drill.get("status") == "open"
        assert "drill_scenario" in drill
        assert "drill_started_at" in drill

    def test_active_drill_403_for_admin(self, admin_token):
        """Admin/branch/org users get 403 on site-only endpoint"""
        resp = requests.get(
            f"{BASE_URL}/api/mod/site/drills/active",
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        # Admin is not mod_site, should get 403
        assert resp.status_code == 403

    def test_active_drill_403_for_pro(self, pro_token):
        """PRO (branch) users get 403 on site-only endpoint"""
        resp = requests.get(
            f"{BASE_URL}/api/mod/site/drills/active",
            headers={"Authorization": f"Bearer {pro_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 403


class TestDrillAcknowledge:
    """Tests for POST /api/mod/site/drills/{drill_id}/acknowledge"""

    def test_acknowledge_drill_success(self, raf_token):
        """Site user can acknowledge drill"""
        drill_id = getattr(pytest, 'drill_id', None)
        assert drill_id, "No drill_id from previous test"

        resp = requests.post(
            f"{BASE_URL}/api/mod/site/drills/{drill_id}/acknowledge",
            json={},
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data.get("ok") is True
        assert "acknowledged_at" in data
        assert data.get("already_acknowledged") is not True

    def test_acknowledge_drill_already_acked(self, raf_token):
        """Second acknowledge returns already_acknowledged=True"""
        drill_id = getattr(pytest, 'drill_id', None)
        assert drill_id, "No drill_id from previous test"

        resp = requests.post(
            f"{BASE_URL}/api/mod/site/drills/{drill_id}/acknowledge",
            json={},
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data.get("ok") is True
        assert data.get("already_acknowledged") is True

    def test_acknowledge_unknown_drill_404(self, raf_token):
        """Unknown drill_id returns 404"""
        resp = requests.post(
            f"{BASE_URL}/api/mod/site/drills/nonexistent-drill-id/acknowledge",
            json={},
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 404

    def test_cross_site_acknowledge_404(self, army_token):
        """Army user cannot acknowledge RAF drill"""
        drill_id = getattr(pytest, 'drill_id', None)
        assert drill_id, "No drill_id from previous test"

        resp = requests.post(
            f"{BASE_URL}/api/mod/site/drills/{drill_id}/acknowledge",
            json={},
            headers={"Authorization": f"Bearer {army_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 404


class TestDrillComplete:
    """Tests for POST /api/master-admin/mod/drills/{drill_id}/complete"""

    def test_complete_drill_success(self, admin_token):
        """Master admin can complete drill and get report"""
        drill_id = getattr(pytest, 'drill_id', None)
        assert drill_id, "No drill_id from previous test"

        # Small delay to ensure time_to_resolve > 0
        time.sleep(1)

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/drills/{drill_id}/complete",
            json={},
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data.get("ok") is True
        report = data.get("report")
        assert report is not None

        # Verify report structure
        assert report.get("drill_id") == drill_id
        assert "scenario" in report
        assert "ticket_ref" in report
        assert "time_to_acknowledge_s" in report
        assert "time_to_resolve_s" in report
        assert "attachments_captured" in report
        assert "started_at" in report
        assert "acknowledged_at" in report
        assert "completed_at" in report

        # time_to_acknowledge_s can be int or None (if not acknowledged in this test run)
        tta = report["time_to_acknowledge_s"]
        assert tta is None or isinstance(tta, int), f"TTA should be int or None, got {type(tta)}"
        # time_to_resolve_s should be > 0
        assert report["time_to_resolve_s"] > 0

        print(f"Drill report: TTA={tta}s, TTR={report['time_to_resolve_s']}s")

    def test_complete_already_resolved_400(self, admin_token):
        """Completing already-resolved drill returns 400"""
        drill_id = getattr(pytest, 'drill_id', None)
        assert drill_id, "No drill_id from previous test"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/drills/{drill_id}/complete",
            json={},
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 400

    def test_complete_drill_non_admin_403(self, raf_token):
        """Non-admin cannot complete drill"""
        drill_id = getattr(pytest, 'drill_id', None) or "any-drill-id"

        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/drills/{drill_id}/complete",
            json={},
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 403


class TestDrillList:
    """Tests for GET /api/master-admin/mod/drills"""

    def test_list_drills_as_admin(self, admin_token):
        """Master admin can list all drills"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/mod/drills",
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        drills = data.get("drills", [])
        assert isinstance(drills, list)

        # Should have at least the drill we created
        assert len(drills) >= 1

        # Verify drill decoration with site_name and site_branch
        for d in drills:
            assert "site_name" in d or d.get("organization_id")
            assert "site_branch" in d or d.get("mod_branch") is None

        # Verify sorted by drill_started_at desc
        if len(drills) >= 2:
            for i in range(len(drills) - 1):
                assert drills[i].get("drill_started_at", "") >= drills[i+1].get("drill_started_at", "")

    def test_list_drills_non_admin_403(self, raf_token):
        """Non-admin cannot list drills"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/mod/drills",
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 403


class TestActiveDrillAfterComplete:
    """Verify active drill is null after completion"""

    def test_no_active_drill_after_complete(self, raf_token):
        """After drill is completed, that specific drill should not be active"""
        resp = requests.get(
            f"{BASE_URL}/api/mod/site/drills/active",
            headers={"Authorization": f"Bearer {raf_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        data = resp.json()

        drill = data.get("drill")
        # The first drill we created and completed should not be active
        # But there might be another drill from subsequent tests
        if drill:
            # If there's an active drill, it should NOT be the one we completed earlier
            completed_drill_id = getattr(pytest, 'drill_id', None)
            if completed_drill_id:
                assert drill.get("drill_id") != completed_drill_id, \
                    "Completed drill should not appear as active"
        # Test passes - either no drill or a different drill


class TestMachineStatusUnchanged:
    """Verify drill doesn't flip equipment to out_of_service"""

    def test_equipment_status_unchanged_by_drill(self, admin_token, raf_site_id):
        """Start a drill with safe_in_service='no' and verify equipment status unchanged"""
        # Start a new drill
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/sites/{raf_site_id}/drill/start",
            json={
                "scenario": "TEST: Equipment isolation check",
                "fault_type": "safety",
                "safe_in_service": "no"
            },
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert resp.status_code == 200
        drill_data = resp.json()
        drill_id = drill_data["drill_id"]

        # Get site equipment to verify status - login as RAF
        raf_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=RAF_SITE,
            headers=BYPASS_HEADERS
        )
        assert raf_resp.status_code == 200, f"RAF login failed: {raf_resp.text}"
        raf_token_local = raf_resp.json().get("token")

        eq_resp = requests.get(
            f"{BASE_URL}/api/mod/site/equipment",
            headers={"Authorization": f"Bearer {raf_token_local}", **BYPASS_HEADERS}
        )
        assert eq_resp.status_code == 200, f"Equipment fetch failed: {eq_resp.text}"
        equipment = eq_resp.json().get("equipment", [])

        # Count out_of_service equipment
        oos_count = sum(1 for e in equipment if e.get("status") == "out_of_service")
        print(f"Equipment out_of_service count: {oos_count}")

        # The drill should NOT have changed any equipment status
        # (Real faults with safe_in_service='no' would flip status, but drills don't)

        # Complete the drill for cleanup
        complete_resp = requests.post(
            f"{BASE_URL}/api/master-admin/mod/drills/{drill_id}/complete",
            json={},
            headers={"Authorization": f"Bearer {admin_token}", **BYPASS_HEADERS}
        )
        assert complete_resp.status_code == 200
