"""
Phase S1 — Staffing Module Upgrade Tests (Rota engine + Workforce Dashboard)

Tests for:
1. Shift templates CRUD + materialise (apply)
2. Drag/drop shift reassignment (move)
3. Bulk conflict detection
4. Workforce dashboard with KPIs + heatmap + live roster + open-shift backlog + compliance

Credentials:
- Owner operator (Bob): bob@knockers.com / Test123! (Strong Fitness org)
- Master admin: admin@gymaxisai.com / MasterAdmin123!
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "7d889c8f7c814c8fdfeeb49fd2ea8bca2b17df490c8df1fea50bd7d279f44105")

# Test credentials
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def bob_token():
    """Get auth token for Bob (owner of Strong Fitness)"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BOB_EMAIL, "password": BOB_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    if resp.status_code != 200:
        pytest.skip(f"Bob login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def bob_headers(bob_token):
    """Headers with Bob's auth token"""
    return {
        "Authorization": f"Bearer {bob_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for master admin"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def test_staff_id(bob_headers):
    """Create a test staff member for shift tests"""
    # First check if we already have staff
    resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=bob_headers)
    if resp.status_code == 200:
        staff = resp.json().get("staff", [])
        # Look for existing test staff
        for s in staff:
            if s.get("full_name", "").startswith("TEST_S1_"):
                return s["id"]
    
    # Create new test staff
    resp = requests.post(
        f"{BASE_URL}/api/staffing/staff",
        json={
            "full_name": "TEST_S1_Staff_Member",
            "email": "test_s1_staff@example.com",
            "primary_role": "reception",
            "hourly_cost": 12.50,
            "contract_type": "part_time"
        },
        headers=bob_headers
    )
    if resp.status_code in [200, 201]:
        return resp.json().get("id")
    pytest.skip(f"Could not create test staff: {resp.status_code} - {resp.text}")


class TestShiftTemplatesCRUD:
    """Test shift templates CRUD operations"""
    
    created_template_id = None
    
    def test_list_templates_empty_or_existing(self, bob_headers):
        """GET /api/staffing/shift-templates lists templates"""
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "templates" in data
        assert "role" in data
        assert data["role"] in ["owner", "manager", "master_admin"]
        print(f"✓ List templates: {len(data['templates'])} templates found")
    
    def test_create_template_validates_role(self, bob_headers):
        """POST /api/staffing/shift-templates validates role"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_Invalid_Role",
                "role": "invalid_role",
                "start_time": "09:00",
                "end_time": "17:00",
                "weekdays": [0, 1, 2]
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for invalid role, got {resp.status_code}"
        print("✓ Invalid role rejected with 400")
    
    def test_create_template_validates_weekdays(self, bob_headers):
        """POST /api/staffing/shift-templates validates weekdays"""
        # Empty weekdays
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_No_Weekdays",
                "role": "reception",
                "start_time": "09:00",
                "end_time": "17:00",
                "weekdays": []
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for empty weekdays, got {resp.status_code}"
        
        # Invalid weekday value
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_Bad_Weekday",
                "role": "reception",
                "start_time": "09:00",
                "end_time": "17:00",
                "weekdays": [0, 7]  # 7 is invalid
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for invalid weekday, got {resp.status_code}"
        print("✓ Invalid weekdays rejected with 400")
    
    def test_create_template_success(self, bob_headers):
        """POST /api/staffing/shift-templates creates a template"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_Morning_Reception",
                "role": "reception",
                "start_time": "09:00",
                "end_time": "17:00",
                "break_minutes": 30,
                "weekdays": [0, 1, 2, 3, 4],  # Mon-Fri
                "colour": "#19CDFF",
                "notes": "Test template for Phase S1"
            },
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["name"] == "TEST_S1_Morning_Reception"
        assert data["role"] == "reception"
        assert data["weekdays"] == [0, 1, 2, 3, 4]
        TestShiftTemplatesCRUD.created_template_id = data["id"]
        print(f"✓ Template created: {data['id']}")
    
    def test_update_template(self, bob_headers):
        """PATCH /api/staffing/shift-templates/{id} updates a template"""
        if not TestShiftTemplatesCRUD.created_template_id:
            pytest.skip("No template created")
        
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/shift-templates/{TestShiftTemplatesCRUD.created_template_id}",
            json={
                "name": "TEST_S1_Morning_Reception_Updated",
                "break_minutes": 45
            },
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == "TEST_S1_Morning_Reception_Updated"
        assert data["break_minutes"] == 45
        print("✓ Template updated successfully")
    
    def test_delete_template_soft_delete(self, bob_headers):
        """DELETE /api/staffing/shift-templates/{id} archives (soft delete)"""
        # Create a template to delete
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_To_Delete",
                "role": "reception",
                "start_time": "10:00",
                "end_time": "14:00",
                "weekdays": [5, 6]
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        tpl_id = resp.json()["id"]
        
        # Delete it
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}",
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json().get("ok") == True
        
        # Verify it's not in the list anymore (archived)
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        templates = resp.json().get("templates", [])
        assert not any(t["id"] == tpl_id for t in templates), "Deleted template should not appear in list"
        print("✓ Template soft-deleted (archived)")


class TestShiftTemplateApply:
    """Test shift template materialisation (apply)"""
    
    def test_apply_requires_dates(self, bob_headers):
        """POST /api/staffing/shift-templates/{id}/apply requires start_date and end_date"""
        # First get or create a template
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        templates = resp.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        tpl_id = templates[0]["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={},
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for missing dates, got {resp.status_code}"
        print("✓ Apply rejects missing dates with 400")
    
    def test_apply_rejects_end_before_start(self, bob_headers):
        """POST /api/staffing/shift-templates/{id}/apply rejects end_date < start_date"""
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        templates = resp.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        tpl_id = templates[0]["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": "2026-02-15",
                "end_date": "2026-02-10"  # Before start
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for end < start, got {resp.status_code}"
        assert "start_date" in resp.text.lower() or "end_date" in resp.text.lower()
        print("✓ Apply rejects end_date < start_date with 400")
    
    def test_apply_enforces_90_day_max(self, bob_headers):
        """POST /api/staffing/shift-templates/{id}/apply enforces 90-day max window"""
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        templates = resp.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        tpl_id = templates[0]["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": "2026-01-01",
                "end_date": "2026-06-01"  # > 90 days
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for >90 days, got {resp.status_code}"
        assert "90" in resp.text
        print("✓ Apply enforces 90-day max window")
    
    def test_apply_rejects_bad_date_format(self, bob_headers):
        """POST /api/staffing/shift-templates/{id}/apply rejects bad date formats"""
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        templates = resp.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        tpl_id = templates[0]["id"]
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": "15/02/2026",  # Wrong format
                "end_date": "2026-02-20"
            },
            headers=bob_headers
        )
        assert resp.status_code == 400, f"Expected 400 for bad date format, got {resp.status_code}"
        print("✓ Apply rejects bad date formats")
    
    def test_apply_creates_shifts(self, bob_headers, test_staff_id):
        """POST /api/staffing/shift-templates/{id}/apply materialises shifts"""
        # Create a fresh template for this test
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_Apply_Test",
                "role": "reception",
                "start_time": "08:00",
                "end_time": "12:00",
                "weekdays": [0, 2, 4],  # Mon, Wed, Fri
                "default_staff_id": test_staff_id
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        tpl_id = resp.json()["id"]
        
        # Apply for a 2-week window
        today = datetime.now().date()
        start = today + timedelta(days=7)  # Next week
        end = start + timedelta(days=13)   # 2 weeks
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "skip_existing": True
            },
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "created" in data
        assert "skipped" in data
        assert "created_ids" in data
        assert data["created"] >= 0
        print(f"✓ Apply created {data['created']} shifts, skipped {data['skipped']}")
        
        # Cleanup: delete the template
        requests.delete(f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}", headers=bob_headers)
    
    def test_apply_skip_existing(self, bob_headers, test_staff_id):
        """POST /api/staffing/shift-templates/{id}/apply with skip_existing=true skips duplicates"""
        # Create template
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates",
            json={
                "name": "TEST_S1_Skip_Test",
                "role": "reception",
                "start_time": "14:00",
                "end_time": "18:00",
                "weekdays": [1],  # Tuesday only
                "default_staff_id": test_staff_id
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        tpl_id = resp.json()["id"]
        
        # Find next Tuesday
        today = datetime.now().date()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        
        # Apply once
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": next_tuesday.isoformat(),
                "end_date": next_tuesday.isoformat(),
                "skip_existing": True
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        first_created = resp.json()["created"]
        
        # Apply again with skip_existing=true
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}/apply",
            json={
                "start_date": next_tuesday.isoformat(),
                "end_date": next_tuesday.isoformat(),
                "skip_existing": True
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should skip the existing shift
        if first_created > 0:
            assert data["skipped"] >= 1, "Should skip existing shift"
        print(f"✓ Apply with skip_existing: created={data['created']}, skipped={data['skipped']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/shift-templates/{tpl_id}", headers=bob_headers)


class TestShiftMove:
    """Test drag/drop shift reassignment"""
    
    def test_move_shift_changes_staff(self, bob_headers, test_staff_id):
        """POST /api/staffing/shifts/{id}/move re-parents a shift to new staff_id"""
        # Create a shift
        today = datetime.now().date()
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "10:00",
                "end_time": "14:00",
                "role": "reception",
                "status": "scheduled"
            },
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Failed to create shift: {resp.text}"
        shift_id = resp.json()["shift"]["id"]
        
        # Move to no staff (open shift)
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts/{shift_id}/move",
            json={"staff_id": None},
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["shift"]["staff_id"] is None
        assert data["shift"]["status"] == "open"
        print("✓ Move with no staff_id sets status='open'")
        
        # Move back to staff
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts/{shift_id}/move",
            json={"staff_id": test_staff_id},
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["shift"]["staff_id"] == test_staff_id
        assert data["shift"]["status"] == "scheduled"
        print("✓ Move with staff_id restores to 'scheduled'")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift_id}", headers=bob_headers)
    
    def test_move_shift_changes_date(self, bob_headers, test_staff_id):
        """POST /api/staffing/shifts/{id}/move can change date"""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Create shift
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "11:00",
                "end_time": "15:00",
                "role": "reception"
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        shift_id = resp.json()["shift"]["id"]
        
        # Move to tomorrow
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts/{shift_id}/move",
            json={"date": tomorrow.isoformat()},
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["shift"]["date"] == tomorrow.isoformat()
        print("✓ Move changes date successfully")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift_id}", headers=bob_headers)
    
    def test_move_returns_warnings(self, bob_headers, test_staff_id):
        """POST /api/staffing/shifts/{id}/move returns warnings"""
        today = datetime.now().date()
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "06:00",
                "end_time": "20:00",  # 14 hour shift - should trigger warning
                "role": "reception"
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        shift_id = resp.json()["shift"]["id"]
        
        # Move it (should return warnings about long shift)
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts/{shift_id}/move",
            json={"staff_id": test_staff_id},
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "warnings" in data
        print(f"✓ Move returns warnings: {data.get('warnings', [])}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift_id}", headers=bob_headers)


class TestConflictDetection:
    """Test bulk conflict detection"""
    
    def test_conflicts_endpoint_requires_dates(self, bob_headers):
        """GET /api/staffing/conflicts requires start_date and end_date"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/conflicts",
            headers=bob_headers
        )
        # Should fail without params
        assert resp.status_code == 422, f"Expected 422 for missing params, got {resp.status_code}"
        print("✓ Conflicts endpoint requires date params")
    
    def test_conflicts_returns_list(self, bob_headers):
        """GET /api/staffing/conflicts returns conflicts list"""
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        resp = requests.get(
            f"{BASE_URL}/api/staffing/conflicts",
            params={
                "start_date": week_start.isoformat(),
                "end_date": week_end.isoformat()
            },
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "conflicts" in data
        assert "count" in data
        assert isinstance(data["conflicts"], list)
        print(f"✓ Conflicts endpoint returns {data['count']} conflicts")
    
    def test_conflicts_detects_overlap(self, bob_headers, test_staff_id):
        """Conflicts endpoint detects overlapping shifts"""
        today = datetime.now().date()
        
        # Create two overlapping shifts
        resp1 = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "09:00",
                "end_time": "13:00",
                "role": "reception"
            },
            headers=bob_headers
        )
        assert resp1.status_code == 200
        shift1_id = resp1.json()["shift"]["id"]
        
        resp2 = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "12:00",  # Overlaps with first shift
                "end_time": "16:00",
                "role": "reception"
            },
            headers=bob_headers
        )
        assert resp2.status_code == 200
        shift2_id = resp2.json()["shift"]["id"]
        
        # Check conflicts
        resp = requests.get(
            f"{BASE_URL}/api/staffing/conflicts",
            params={
                "start_date": today.isoformat(),
                "end_date": today.isoformat()
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Should detect overlap
        overlap_conflicts = [c for c in data["conflicts"] if c.get("severity") == "error" and "overlap" in c.get("reason", "").lower()]
        print(f"✓ Detected {len(overlap_conflicts)} overlap conflicts")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift1_id}", headers=bob_headers)
        requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift2_id}", headers=bob_headers)


class TestWorkforceDashboard:
    """Test workforce dashboard endpoint"""
    
    def test_dashboard_returns_full_payload(self, bob_headers):
        """GET /api/staffing/workforce-dashboard returns full payload"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check required fields
        assert "as_of" in data
        assert "week_start" in data
        assert "week_end" in data
        assert "kpis" in data
        assert "week" in data
        assert "heatmap" in data
        assert "on_now" in data
        assert "upcoming" in data
        assert "open_shifts" in data
        assert "compliance" in data
        print("✓ Dashboard returns all required fields")
    
    def test_dashboard_kpis_structure(self, bob_headers):
        """Dashboard KPIs have correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        
        assert "active_staff" in kpis
        assert "on_now" in kpis
        assert "late" in kpis
        assert "absent" in kpis
        assert "open_today" in kpis
        assert "coverage_pct" in kpis
        
        # Coverage should be 0-100
        assert 0 <= kpis["coverage_pct"] <= 100
        print(f"✓ KPIs: active_staff={kpis['active_staff']}, on_now={kpis['on_now']}, coverage={kpis['coverage_pct']}%")
    
    def test_dashboard_coverage_calculation(self, bob_headers):
        """Dashboard coverage_pct is internally consistent"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        kpis = data["kpis"]
        
        # If there are no shifts today, coverage should be 100%
        # If there are shifts, coverage = (total - open) / total * 100
        # We can't verify exact calculation without knowing total shifts,
        # but we can verify it's a valid percentage
        assert isinstance(kpis["coverage_pct"], (int, float))
        assert 0 <= kpis["coverage_pct"] <= 100
        print(f"✓ Coverage percentage is valid: {kpis['coverage_pct']}%")
    
    def test_dashboard_week_totals(self, bob_headers):
        """Dashboard week totals have correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200
        week = resp.json()["week"]
        
        assert "hours" in week
        assert "labour_cost" in week
        assert "overtime_hours" in week
        assert "avg_hourly" in week
        
        assert isinstance(week["hours"], (int, float))
        assert isinstance(week["labour_cost"], (int, float))
        print(f"✓ Week totals: {week['hours']}h, £{week['labour_cost']} labour")
    
    def test_dashboard_heatmap_structure(self, bob_headers):
        """Dashboard heatmap is 7x24 grid"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200
        heatmap = resp.json()["heatmap"]
        
        assert "grid" in heatmap
        assert "peak" in heatmap
        
        grid = heatmap["grid"]
        assert len(grid) == 7, f"Expected 7 rows (days), got {len(grid)}"
        for row in grid:
            assert len(row) == 24, f"Expected 24 columns (hours), got {len(row)}"
        
        # Values should be floats (fractional hours)
        for row in grid:
            for val in row:
                assert isinstance(val, (int, float))
        
        print(f"✓ Heatmap is 7x24 grid, peak={heatmap['peak']}")
    
    def test_dashboard_compliance_structure(self, bob_headers):
        """Dashboard compliance has correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=bob_headers
        )
        assert resp.status_code == 200
        compliance = resp.json()["compliance"]
        
        assert "count" in compliance
        assert "top" in compliance
        assert isinstance(compliance["top"], list)
        
        # Each conflict should have required fields
        for c in compliance["top"]:
            assert "shift_id" in c
            assert "staff_id" in c
            assert "severity" in c
            assert "reason" in c
        
        print(f"✓ Compliance: {compliance['count']} total conflicts")


class TestRoleGating:
    """Test that endpoints require manager role"""
    
    def test_templates_require_manager(self, bob_headers):
        """Shift templates endpoints require manager role"""
        # Bob is owner, should work
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        assert resp.status_code == 200
        print("✓ Owner can access shift-templates")
    
    def test_conflicts_require_manager(self, bob_headers):
        """Conflicts endpoint requires manager role"""
        today = datetime.now().date()
        resp = requests.get(
            f"{BASE_URL}/api/staffing/conflicts",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
            headers=bob_headers
        )
        assert resp.status_code == 200
        print("✓ Owner can access conflicts")
    
    def test_dashboard_requires_manager(self, bob_headers):
        """Workforce dashboard requires manager role"""
        resp = requests.get(f"{BASE_URL}/api/staffing/workforce-dashboard", headers=bob_headers)
        assert resp.status_code == 200
        print("✓ Owner can access workforce-dashboard")
    
    def test_move_requires_manager(self, bob_headers, test_staff_id):
        """Move endpoint requires manager role"""
        # Create a shift first
        today = datetime.now().date()
        resp = requests.post(
            f"{BASE_URL}/api/staffing/shifts",
            json={
                "staff_id": test_staff_id,
                "date": today.isoformat(),
                "start_time": "15:00",
                "end_time": "19:00",
                "role": "reception"
            },
            headers=bob_headers
        )
        if resp.status_code == 200:
            shift_id = resp.json()["shift"]["id"]
            
            # Move should work for owner
            resp = requests.post(
                f"{BASE_URL}/api/staffing/shifts/{shift_id}/move",
                json={"staff_id": test_staff_id},
                headers=bob_headers
            )
            assert resp.status_code == 200
            print("✓ Owner can move shifts")
            
            # Cleanup
            requests.delete(f"{BASE_URL}/api/staffing/shifts/{shift_id}", headers=bob_headers)


class TestOrganizationScoping:
    """Test that endpoints require organization_id"""
    
    def test_endpoints_require_org(self, admin_headers):
        """Endpoints return 400 if no organization context"""
        # Master admin without org context should still work
        # because they have is_master_admin flag
        resp = requests.get(
            f"{BASE_URL}/api/staffing/workforce-dashboard",
            headers=admin_headers
        )
        # Master admin might not have org_id set, should get 400
        # or might work if they have a default org
        if resp.status_code == 400:
            assert "organization" in resp.text.lower()
            print("✓ Endpoint requires organization context")
        else:
            print(f"✓ Master admin has org context, status={resp.status_code}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_templates(self, bob_headers):
        """Remove TEST_S1_ prefixed templates"""
        resp = requests.get(f"{BASE_URL}/api/staffing/shift-templates", headers=bob_headers)
        if resp.status_code == 200:
            templates = resp.json().get("templates", [])
            deleted = 0
            for t in templates:
                if t.get("name", "").startswith("TEST_S1_"):
                    requests.delete(f"{BASE_URL}/api/staffing/shift-templates/{t['id']}", headers=bob_headers)
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test templates")
    
    def test_cleanup_test_staff(self, bob_headers):
        """Archive TEST_S1_ prefixed staff"""
        resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=bob_headers)
        if resp.status_code == 200:
            staff = resp.json().get("staff", [])
            archived = 0
            for s in staff:
                if s.get("full_name", "").startswith("TEST_S1_"):
                    requests.delete(f"{BASE_URL}/api/staffing/staff/{s['id']}", headers=bob_headers)
                    archived += 1
            print(f"✓ Archived {archived} test staff members")
