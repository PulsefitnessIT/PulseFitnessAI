"""
Test PPM Reminders and KPI/PPM Theming - Iteration 119
Tests for:
1. POST /api/ppm/send-reminders - event-driven PPM reminders endpoint
2. GET /api/reports/kpi-dashboard - verify all 7 KPIs still work
3. GET /api/ppm/schedules - verify PPM data for theming tests
"""

import pytest
import requests
import os
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")


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
    return response.json()["token"]


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def pulse_pro_headers(pulse_pro_token):
    return {"Authorization": f"Bearer {pulse_pro_token}", "Content-Type": "application/json"}


# ── 1. PPM Send Reminders Tests ──────────────────────────────────

class TestPPMSendReminders:
    """Test POST /api/ppm/send-reminders endpoint"""

    def test_send_reminders_endpoint_exists(self, pulse_pro_headers):
        """Test that send-reminders endpoint exists and returns valid response"""
        response = requests.post(f"{BASE_URL}/api/ppm/send-reminders", headers=pulse_pro_headers)
        assert response.status_code == 200, f"Send reminders failed: {response.text}"

        data = response.json()
        # Should return sent count and checked count
        assert "sent" in data, "Response should include 'sent' count"
        assert "checked" in data, "Response should include 'checked' count"
        assert isinstance(data["sent"], int), "'sent' should be an integer"
        assert isinstance(data["checked"], int), "'checked' should be an integer"
        assert data["sent"] >= 0, "'sent' should be non-negative"
        assert data["checked"] >= 0, "'checked' should be non-negative"

    def test_send_reminders_as_master_admin(self, master_admin_headers):
        """Test that master admin can also call send-reminders"""
        response = requests.post(f"{BASE_URL}/api/ppm/send-reminders", headers=master_admin_headers)
        assert response.status_code == 200, f"Send reminders failed for master admin: {response.text}"

        data = response.json()
        assert "sent" in data
        assert "checked" in data


# ── 2. KPI Dashboard Tests ───────────────────────────────────────

class TestKPIDashboard:
    """Test KPI dashboard returns all 7 KPIs correctly.

    Note: KPI is a GymAxis-only feature — Pulse Pro users are 403'd by default.
    These tests use master_admin_headers so they verify KPI shape regardless of the
    feature-gate status on the Pulse test org.
    """

    def test_kpi_dashboard_all_7_kpis(self, master_admin_headers):
        """Verify all 7 KPIs are returned"""
        response = requests.get(f"{BASE_URL}/api/reports/kpi-dashboard?period=30d", headers=master_admin_headers)
        assert response.status_code == 200, f"KPI dashboard failed: {response.text}"

        data = response.json()

        # All 7 KPIs must be present
        required_kpis = [
            "ppm_compliance",
            "equipment_downtime",
            "reactive_response",
            "safety_critical",
            "safety_compliance",
            "oos_ratio",
            "commissioning"
        ]

        for kpi in required_kpis:
            assert kpi in data, f"Missing KPI: {kpi}"

    def test_kpi_ppm_compliance_structure(self, master_admin_headers):
        """Verify PPM compliance KPI structure"""
        response = requests.get(f"{BASE_URL}/api/reports/kpi-dashboard?period=30d", headers=master_admin_headers)
        assert response.status_code == 200

        ppm = response.json().get("ppm_compliance", {})
        assert "total_scheduled" in ppm
        assert "total_completed" in ppm
        assert "completed_on_time" in ppm
        assert "overdue" in ppm
        assert "compliance_pct" in ppm

    def test_kpi_equipment_downtime_structure(self, master_admin_headers):
        """Verify equipment downtime KPI structure with worst performing assets"""
        response = requests.get(f"{BASE_URL}/api/reports/kpi-dashboard?period=30d", headers=master_admin_headers)
        assert response.status_code == 200

        dt = response.json().get("equipment_downtime", {})
        assert "total_faults" in dt
        assert "avg_downtime_hours" in dt
        assert "worst_performing_assets" in dt
        assert isinstance(dt["worst_performing_assets"], list)

    def test_kpi_safety_critical_structure(self, master_admin_headers):
        """Verify safety critical KPI structure"""
        response = requests.get(f"{BASE_URL}/api/reports/kpi-dashboard?period=30d", headers=master_admin_headers)
        assert response.status_code == 200

        sc = response.json().get("safety_critical", {})
        assert "total_safety_issues" in sc
        assert "sla_breaches" in sc
        assert "compliance_pct" in sc

    def test_kpi_oos_ratio_structure(self, master_admin_headers):
        """Verify OOS ratio KPI structure (machine availability)"""
        response = requests.get(f"{BASE_URL}/api/reports/kpi-dashboard?period=30d", headers=master_admin_headers)
        assert response.status_code == 200

        oos = response.json().get("oos_ratio", {})
        assert "total_equipment" in oos
        assert "out_of_service" in oos
        assert "oos_pct" in oos


# ── 3. PPM Schedules Tests ───────────────────────────────────────

class TestPPMSchedules:
    """Test PPM schedules endpoint for theming verification"""

    def test_ppm_schedules_returns_data(self, pulse_pro_headers):
        """Verify PPM schedules endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/ppm/schedules", headers=pulse_pro_headers)
        assert response.status_code == 200, f"PPM schedules failed: {response.text}"

        data = response.json()
        assert "schedules" in data
        assert isinstance(data["schedules"], list)

    def test_ppm_summary_returns_data(self, pulse_pro_headers):
        """Verify PPM summary endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/ppm/summary", headers=pulse_pro_headers)
        assert response.status_code == 200, f"PPM summary failed: {response.text}"

        data = response.json()
        assert "active_schedules" in data
        assert "completed" in data
        assert "overdue" in data
        assert "compliance_pct" in data


# ── 4. Auth Tests ────────────────────────────────────────────────

class TestAuth:
    """Test authentication for both user types"""

    def test_master_admin_login(self):
        """Test master admin can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("user", {}).get("is_master_admin") == True

    def test_pulse_pro_login(self):
        """Test Pulse Pro user can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
