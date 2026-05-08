"""
Test PPM Engine and KPI Engine - Iteration 118
Tests for:
1. GET /api/ppm/checklists - 7 equipment categories with correct item counts
2. POST /api/ppm/schedules - creates schedule with auto-generated tasks, SLA tier, supplier info
3. GET /api/ppm/schedules - returns schedules WITH embedded tasks
4. POST/GET/DELETE /api/ppm/schedules/{id}/certificates - certificate upload/download/delete
5. PATCH /api/ppm/tasks/{id} - complete task correctly
6. GET /api/master-admin/kpi/{org_id} - master admin per-org KPI
7. GET /api/master-admin/kpi/{org_id}/export-csv - CSV export for tender
8. GET /api/reports/kpi-dashboard - KPI dashboard with Tottenham Green data
"""

import pytest
import requests
import os
import io
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")
TOTTENHAM_GREEN_ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Master admin login failed: {response.text}"
    data = response.json()
    assert data.get("user", {}).get("is_master_admin") == True, "User is not master admin"
    return data["token"]


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get Pulse Pro user token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    assert response.status_code == 200, f"Pulse Pro login failed: {response.text}"
    data = response.json()
    assert data.get("user", {}).get("organization_id") == TOTTENHAM_GREEN_ORG_ID
    return data["token"]


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def pulse_pro_headers(pulse_pro_token):
    return {"Authorization": f"Bearer {pulse_pro_token}", "Content-Type": "application/json"}


# ── 1. PPM Checklists Tests ──────────────────────────────────────

class TestPPMChecklists:
    """Test GET /api/ppm/checklists returns 7 equipment categories"""

    def test_checklists_returns_7_categories(self, pulse_pro_headers):
        """Verify 7 equipment categories from Pulse Fitness service document"""
        response = requests.get(f"{BASE_URL}/api/ppm/checklists", headers=pulse_pro_headers)
        assert response.status_code == 200

        data = response.json()
        checklists = data.get("checklists", {})

        # Must have exactly 7 categories
        expected_categories = ["Treadmill", "X-Trainer", "Stepper", "U-Cycle / R-Cycle", "L-Train", "Group Cycle", "Resistance"]
        assert len(checklists) == 7, f"Expected 7 categories, got {len(checklists)}"

        for cat in expected_categories:
            assert cat in checklists, f"Missing category: {cat}"
            assert len(checklists[cat]) > 0, f"Category {cat} has no items"

    def test_treadmill_checklist_items(self, pulse_pro_headers):
        """Verify Treadmill checklist has correct items"""
        response = requests.get(f"{BASE_URL}/api/ppm/checklists", headers=pulse_pro_headers)
        assert response.status_code == 200

        checklists = response.json().get("checklists", {})
        treadmill = checklists.get("Treadmill", [])

        # Treadmill should have 22 items
        assert len(treadmill) == 22, f"Treadmill should have 22 items, got {len(treadmill)}"

        # Check some key items exist
        assert any("belt" in item.lower() for item in treadmill), "Missing belt-related items"
        assert any("incline" in item.lower() for item in treadmill), "Missing incline-related items"
        assert any("e-stop" in item.lower() for item in treadmill), "Missing E-Stop check"

    def test_group_cycle_checklist_items(self, pulse_pro_headers):
        """Verify Group Cycle checklist has correct items"""
        response = requests.get(f"{BASE_URL}/api/ppm/checklists", headers=pulse_pro_headers)
        assert response.status_code == 200

        checklists = response.json().get("checklists", {})
        group_cycle = checklists.get("Group Cycle", [])

        # Group Cycle should have 10 items
        assert len(group_cycle) == 10, f"Group Cycle should have 10 items, got {len(group_cycle)}"


# ── 2. PPM Schedule CRUD Tests ───────────────────────────────────

class TestPPMScheduleCRUD:
    """Test PPM schedule creation with auto-generated tasks"""

    @pytest.fixture
    def test_schedule_data(self):
        return {
            "title": "TEST_Annual Treadmill Service",
            "description": "Annual service for gym treadmills",
            "frequency": "annual",
            "site_name": "Test Gym Site",
            "sla_tier": "gold",
            "source": "sla",
            "supplier_name": "Pulse Fitness",
            "supplier_email": "service@pulsefitness.com",
            "equipment_type": "Treadmill",
            "install_date": "2024-06-15",
            "checklist_category": "Treadmill",
            "assigned_to": "Service Team"
        }

    def test_create_schedule_with_auto_tasks(self, pulse_pro_headers, test_schedule_data):
        """Create schedule and verify auto-generated tasks"""
        response = requests.post(f"{BASE_URL}/api/ppm/schedules",
                                 json=test_schedule_data, headers=pulse_pro_headers)
        assert response.status_code == 200, f"Create failed: {response.text}"

        schedule = response.json()

        # Verify schedule fields
        assert schedule.get("id"), "Schedule should have ID"
        assert schedule.get("title") == test_schedule_data["title"]
        assert schedule.get("sla_tier") == "gold"
        assert schedule.get("source") == "sla"
        assert schedule.get("supplier_name") == "Pulse Fitness"
        assert schedule.get("install_date") == "2024-06-15"

        # Verify auto-generated tasks
        tasks = schedule.get("tasks", [])
        assert len(tasks) >= 1, "Should have auto-generated tasks"

        # Cleanup
        schedule_id = schedule["id"]
        requests.delete(f"{BASE_URL}/api/ppm/schedules/{schedule_id}", headers=pulse_pro_headers)

    def test_get_schedules_with_embedded_tasks(self, pulse_pro_headers, test_schedule_data):
        """Verify GET schedules returns tasks embedded in each schedule"""
        # Create a schedule first
        create_resp = requests.post(f"{BASE_URL}/api/ppm/schedules",
                                    json=test_schedule_data, headers=pulse_pro_headers)
        assert create_resp.status_code == 200
        schedule_id = create_resp.json()["id"]

        try:
            # Get all schedules
            response = requests.get(f"{BASE_URL}/api/ppm/schedules", headers=pulse_pro_headers)
            assert response.status_code == 200

            schedules = response.json().get("schedules", [])
            assert len(schedules) > 0, "Should have at least one schedule"

            # Find our test schedule
            test_sched = next((s for s in schedules if s["id"] == schedule_id), None)
            assert test_sched is not None, "Test schedule not found"

            # Verify tasks are embedded
            assert "tasks" in test_sched, "Schedule should have embedded tasks"
            assert isinstance(test_sched["tasks"], list), "Tasks should be a list"
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/ppm/schedules/{schedule_id}", headers=pulse_pro_headers)


# ── 3. Certificate Upload/Download Tests ─────────────────────────

class TestCertificateManagement:
    """Test certificate upload, download, and delete"""

    @pytest.fixture
    def schedule_with_cert(self, pulse_pro_headers):
        """Create a schedule for certificate testing"""
        schedule_data = {
            "title": "TEST_Certificate Test Schedule",
            "frequency": "annual",
            "site_name": "Test Site"
        }
        response = requests.post(f"{BASE_URL}/api/ppm/schedules",
                                 json=schedule_data, headers=pulse_pro_headers)
        assert response.status_code == 200
        schedule = response.json()
        yield schedule
        # Cleanup
        requests.delete(f"{BASE_URL}/api/ppm/schedules/{schedule['id']}", headers=pulse_pro_headers)

    def test_upload_certificate(self, pulse_pro_headers, schedule_with_cert):
        """Test uploading a certificate to a schedule"""
        schedule_id = schedule_with_cert["id"]

        # Create a test file
        test_content = b"Test certificate content for PPM service"
        files = {"file": ("test_certificate.pdf", io.BytesIO(test_content), "application/pdf")}

        # Remove Content-Type for multipart upload
        upload_headers = {"Authorization": pulse_pro_headers["Authorization"]}

        response = requests.post(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates",
            files=files,
            headers=upload_headers
        )
        assert response.status_code == 200, f"Upload failed: {response.text}"

        data = response.json()
        assert data.get("success") == True
        assert data.get("certificate_id"), "Should return certificate ID"
        assert data.get("filename") == "test_certificate.pdf"

        return data.get("certificate_id")

    def test_download_certificate(self, pulse_pro_headers, schedule_with_cert):
        """Test downloading a certificate"""
        schedule_id = schedule_with_cert["id"]

        # First upload a certificate
        test_content = b"Test certificate content for download test"
        files = {"file": ("download_test.pdf", io.BytesIO(test_content), "application/pdf")}
        upload_headers = {"Authorization": pulse_pro_headers["Authorization"]}

        upload_resp = requests.post(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates",
            files=files,
            headers=upload_headers
        )
        assert upload_resp.status_code == 200
        cert_id = upload_resp.json()["certificate_id"]

        # Download the certificate
        download_resp = requests.get(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates/{cert_id}",
            headers=pulse_pro_headers
        )
        assert download_resp.status_code == 200
        assert download_resp.content == test_content
        assert "attachment" in download_resp.headers.get("Content-Disposition", "")

    def test_delete_certificate(self, pulse_pro_headers, schedule_with_cert):
        """Test deleting a certificate"""
        schedule_id = schedule_with_cert["id"]

        # First upload a certificate
        test_content = b"Test certificate to delete"
        files = {"file": ("delete_test.pdf", io.BytesIO(test_content), "application/pdf")}
        upload_headers = {"Authorization": pulse_pro_headers["Authorization"]}

        upload_resp = requests.post(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates",
            files=files,
            headers=upload_headers
        )
        assert upload_resp.status_code == 200
        cert_id = upload_resp.json()["certificate_id"]

        # Delete the certificate
        delete_resp = requests.delete(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates/{cert_id}",
            headers=pulse_pro_headers
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json().get("success") == True

        # Verify it's deleted - should return 404
        download_resp = requests.get(
            f"{BASE_URL}/api/ppm/schedules/{schedule_id}/certificates/{cert_id}",
            headers=pulse_pro_headers
        )
        assert download_resp.status_code == 404


# ── 4. Task Completion Tests ─────────────────────────────────────

class TestTaskCompletion:
    """Test PATCH /api/ppm/tasks/{id} for task completion"""

    def test_complete_task(self, pulse_pro_headers):
        """Test completing a PPM task"""
        # Create a schedule to get tasks
        schedule_data = {
            "title": "TEST_Task Completion Test",
            "frequency": "annual",
            "site_name": "Test Site"
        }
        create_resp = requests.post(f"{BASE_URL}/api/ppm/schedules",
                                    json=schedule_data, headers=pulse_pro_headers)
        assert create_resp.status_code == 200
        schedule = create_resp.json()
        schedule_id = schedule["id"]

        try:
            # Get tasks from the schedule
            tasks = schedule.get("tasks", [])
            assert len(tasks) > 0, "Should have auto-generated tasks"

            task_id = tasks[0]["id"]

            # Complete the task
            patch_resp = requests.patch(
                f"{BASE_URL}/api/ppm/tasks/{task_id}",
                json={"status": "completed", "completion_notes": "Service completed successfully"},
                headers=pulse_pro_headers
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json().get("success") == True

            # Verify task is completed by getting schedules
            get_resp = requests.get(f"{BASE_URL}/api/ppm/schedules", headers=pulse_pro_headers)
            schedules = get_resp.json().get("schedules", [])
            test_sched = next((s for s in schedules if s["id"] == schedule_id), None)

            if test_sched:
                completed_task = next((t for t in test_sched.get("tasks", []) if t["id"] == task_id), None)
                if completed_task:
                    assert completed_task["status"] == "completed"
                    assert completed_task.get("completed_date") is not None
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/ppm/schedules/{schedule_id}", headers=pulse_pro_headers)


# ── 5. Master Admin KPI Tests ────────────────────────────────────

class TestMasterAdminKPI:
    """Test master admin KPI endpoints for specific org"""

    def test_get_org_kpi_as_master_admin(self, master_admin_headers):
        """Test GET /api/master-admin/kpi/{org_id} returns KPIs for Tottenham Green"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/kpi/{TOTTENHAM_GREEN_ORG_ID}?period=365d",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"

        data = response.json()

        # Verify structure
        assert data.get("organization_id") == TOTTENHAM_GREEN_ORG_ID
        assert "organization_name" in data
        assert "ppm_compliance" in data
        assert "equipment_downtime" in data
        assert "reactive_response" in data
        assert "safety_critical" in data
        assert "safety_compliance" in data
        assert "oos_ratio" in data
        assert "commissioning" in data

    def test_get_org_kpi_forbidden_for_non_admin(self, pulse_pro_headers):
        """Test that non-master-admin cannot access org KPI endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/kpi/{TOTTENHAM_GREEN_ORG_ID}",
            headers=pulse_pro_headers
        )
        assert response.status_code == 403, "Should be forbidden for non-master-admin"

    def test_export_kpi_csv(self, master_admin_headers):
        """Test GET /api/master-admin/kpi/{org_id}/export-csv returns CSV"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/kpi/{TOTTENHAM_GREEN_ORG_ID}/export-csv?period=365d",
            headers=master_admin_headers
        )
        assert response.status_code == 200, f"CSV export failed: {response.text}"

        # Verify it's CSV
        assert "text/csv" in response.headers.get("Content-Type", "")
        assert "attachment" in response.headers.get("Content-Disposition", "")

        # Verify CSV content
        csv_content = response.text
        assert "GymAxis AI - KPI Performance Report" in csv_content
        assert "PPM Compliance" in csv_content
        assert "Avg Machine Downtime" in csv_content
        assert "Safety SLA Compliance" in csv_content
        assert "Machine Availability" in csv_content

        # Check for worst performing machines section
        assert "Worst Performing Machines" in csv_content

    def test_export_csv_forbidden_for_non_admin(self, pulse_pro_headers):
        """Test that non-master-admin cannot export CSV"""
        response = requests.get(
            f"{BASE_URL}/api/master-admin/kpi/{TOTTENHAM_GREEN_ORG_ID}/export-csv",
            headers=pulse_pro_headers
        )
        assert response.status_code == 403


# ── 6. KPI Dashboard Tests ───────────────────────────────────────

class TestKPIDashboard:
    """Test KPI dashboard endpoint"""

    def test_kpi_dashboard_returns_all_7_kpis(self, master_admin_headers):
        """Test GET /api/reports/kpi-dashboard returns all 7 KPIs (KPI is GymAxis/master-admin gated)."""
        response = requests.get(
            f"{BASE_URL}/api/reports/kpi-dashboard?period=30d",
            headers=master_admin_headers
        )
        assert response.status_code == 200

        data = response.json()

        # Verify all 7 KPIs present
        assert "ppm_compliance" in data
        assert "equipment_downtime" in data
        assert "reactive_response" in data
        assert "safety_critical" in data
        assert "safety_compliance" in data
        assert "oos_ratio" in data
        assert "commissioning" in data

        # Verify PPM compliance structure
        ppm = data["ppm_compliance"]
        assert "total_scheduled" in ppm
        assert "total_completed" in ppm
        assert "compliance_pct" in ppm

        # Verify equipment downtime structure
        dt = data["equipment_downtime"]
        assert "total_faults" in dt
        assert "avg_downtime_hours" in dt
        assert "worst_performing_assets" in dt

    def test_kpi_dashboard_period_filter(self, master_admin_headers):
        """Test KPI dashboard with different period filters (master-admin; Pulse Pro is feature-gated out)."""
        for period in ["7d", "30d", "90d", "365d", "all"]:
            response = requests.get(
                f"{BASE_URL}/api/reports/kpi-dashboard?period={period}",
                headers=master_admin_headers
            )
            assert response.status_code == 200, f"Failed for period {period}"
            assert response.json().get("period") == period


# ── 7. PPM Summary Tests ─────────────────────────────────────────

class TestPPMSummary:
    """Test PPM summary endpoint"""

    def test_ppm_summary_returns_correct_fields(self, pulse_pro_headers):
        """Test GET /api/ppm/summary returns all summary fields"""
        response = requests.get(f"{BASE_URL}/api/ppm/summary", headers=pulse_pro_headers)
        assert response.status_code == 200

        data = response.json()

        # Verify all summary fields
        assert "active_schedules" in data
        assert "total_tasks" in data
        assert "completed" in data
        assert "scheduled" in data
        assert "overdue" in data
        assert "upcoming_90d" in data
        assert "compliance_pct" in data

        # Values should be non-negative
        assert data["active_schedules"] >= 0
        assert data["compliance_pct"] >= 0
        assert data["compliance_pct"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
