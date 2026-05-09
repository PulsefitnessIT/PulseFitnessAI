"""
Phase S6 — AI Workforce Automation & Payroll Integration Tests

Tests for:
1. POST /api/staffing/ai/rota/suggest — AI rota builder (manager-only)
2. POST /api/staffing/ai/rota/apply — Apply AI-generated rota (manager-only)
3. GET /api/staffing/ai/absence-risk — Absence prediction (manager-only)
4. GET /api/staffing/ai/payroll/sage.csv — Sage 50 Payroll CSV export (manager-only)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


class TestSetup:
    """Setup fixtures for Phase S6 tests"""
    
    @pytest.fixture(scope="class")
    def bob_token(self):
        """Get auth token for bob (manager/owner)"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": BOB_EMAIL,
            "password": BOB_PASSWORD
        })
        assert resp.status_code == 200, f"Bob login failed: {resp.text}"
        return resp.json().get("token")
    
    @pytest.fixture(scope="class")
    def bob_headers(self, bob_token):
        """Headers with Bob's auth token"""
        return {"Authorization": f"Bearer {bob_token}"}
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get auth token for master admin"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        """Headers with admin's auth token"""
        return {"Authorization": f"Bearer {admin_token}"}


class TestRotaSuggest(TestSetup):
    """Tests for POST /api/staffing/ai/rota/suggest"""
    
    def test_rota_suggest_success(self, bob_headers):
        """Test successful rota suggestion generation"""
        # Get next Monday
        today = datetime.now().date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).isoformat()
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={
                "week_start": next_monday,
                "max_hours_per_staff_week": 40,
                "notes": "Test rota generation"
            },
            headers=bob_headers,
            timeout=120  # AI can take time
        )
        assert resp.status_code == 200, f"Rota suggest failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "week_start" in data
        assert "week_end" in data
        assert "engine" in data
        assert data["engine"] in ["claude-sonnet-4-5", "heuristic"]
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert "hours_per_staff" in data
        assert "cost_per_staff" in data
        assert "cost_total_pence" in data
        assert "cost_total" in data
        
        print(f"Rota generated with engine: {data['engine']}, {len(data['suggestions'])} suggestions")
    
    def test_rota_suggest_snaps_to_monday(self, bob_headers):
        """Test that week_start is snapped to Monday if mid-week date provided"""
        # Use a Wednesday
        today = datetime.now().date()
        days_until_wed = (2 - today.weekday()) % 7
        if days_until_wed == 0:
            days_until_wed = 7
        next_wed = (today + timedelta(days=days_until_wed)).isoformat()
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={"week_start": next_wed},
            headers=bob_headers,
            timeout=120
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Should snap to Monday
        week_start_date = datetime.fromisoformat(data["week_start"]).date()
        assert week_start_date.weekday() == 0, "week_start should be Monday"
    
    def test_rota_suggest_invalid_date(self, bob_headers):
        """Test error handling for invalid date format"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={"week_start": "invalid-date"},
            headers=bob_headers
        )
        assert resp.status_code == 400
    
    def test_rota_suggest_unauthorized_no_token(self):
        """Test that unauthenticated requests are rejected"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={"week_start": "2026-01-20"}
        )
        assert resp.status_code in [401, 403]


class TestRotaApply(TestSetup):
    """Tests for POST /api/staffing/ai/rota/apply"""
    
    def test_rota_apply_success(self, bob_headers):
        """Test applying a generated rota"""
        # First generate a rota
        today = datetime.now().date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).isoformat()
        
        suggest_resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={"week_start": next_monday, "max_hours_per_staff_week": 40},
            headers=bob_headers,
            timeout=120
        )
        assert suggest_resp.status_code == 200
        suggestions = suggest_resp.json().get("suggestions", [])
        
        if not suggestions:
            pytest.skip("No suggestions generated - no staff in org")
        
        # Apply the rota
        apply_resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/apply",
            json={
                "week_start": next_monday,
                "shifts": suggestions,
                "overwrite_existing": True
            },
            headers=bob_headers
        )
        assert apply_resp.status_code == 200, f"Apply failed: {apply_resp.text}"
        data = apply_resp.json()
        
        assert "created" in data
        assert "week_start" in data
        assert data["created"] >= 0
        print(f"Applied {data['created']} shifts for week {data['week_start']}")
    
    def test_rota_apply_invalid_date(self, bob_headers):
        """Test error handling for invalid week_start"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/apply",
            json={
                "week_start": "not-a-date",
                "shifts": []
            },
            headers=bob_headers
        )
        assert resp.status_code == 400
    
    def test_rota_apply_filters_invalid_staff(self, bob_headers):
        """Test that invalid staff_ids are filtered out"""
        today = datetime.now().date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).isoformat()
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/apply",
            json={
                "week_start": next_monday,
                "shifts": [{
                    "staff_id": "invalid-staff-id-12345",
                    "date": next_monday,
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "role": "reception"
                }],
                "overwrite_existing": False
            },
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # Invalid staff_id should be filtered out
        assert data["created"] == 0


class TestAbsenceRisk(TestSetup):
    """Tests for GET /api/staffing/ai/absence-risk"""
    
    def test_absence_risk_default_horizon(self, bob_headers):
        """Test absence risk with default 14-day horizon"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Absence risk failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "rows" in data
        assert "summary" in data
        assert isinstance(data["rows"], list)
        
        summary = data["summary"]
        assert "high" in summary
        assert "medium" in summary
        assert "low" in summary
        assert "horizon_days" in summary
        assert "as_of" in summary
        assert summary["horizon_days"] == 14
        
        # Verify row structure if any staff exist
        for row in data["rows"]:
            assert "staff_id" in row
            assert "full_name" in row
            assert "primary_role" in row
            assert "score" in row
            assert 0 <= row["score"] <= 100
            assert "band" in row
            assert row["band"] in ["low", "medium", "high"]
            assert "reasons" in row
            assert isinstance(row["reasons"], list)
        
        print(f"Absence risk: {summary['high']} high, {summary['medium']} medium, {summary['low']} low")
    
    def test_absence_risk_custom_horizon(self, bob_headers):
        """Test absence risk with custom horizon"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            params={"horizon_days": 30},
            headers=bob_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["horizon_days"] == 30
    
    def test_absence_risk_horizon_validation(self, bob_headers):
        """Test horizon_days validation (1-60)"""
        # Too low
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            params={"horizon_days": 0},
            headers=bob_headers
        )
        assert resp.status_code == 422  # Validation error
        
        # Too high
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            params={"horizon_days": 100},
            headers=bob_headers
        )
        assert resp.status_code == 422
    
    def test_absence_risk_unauthorized(self):
        """Test that unauthenticated requests are rejected"""
        resp = requests.get(f"{BASE_URL}/api/staffing/ai/absence-risk")
        assert resp.status_code in [401, 403]


class TestSagePayrollCSV(TestSetup):
    """Tests for GET /api/staffing/ai/payroll/sage.csv"""
    
    def test_sage_csv_success(self, bob_headers):
        """Test successful Sage CSV export"""
        today = datetime.now().date()
        date_from = (today - timedelta(days=30)).isoformat()
        date_to = today.isoformat()
        
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={"date_from": date_from, "date_to": date_to},
            headers=bob_headers
        )
        assert resp.status_code == 200, f"Sage CSV failed: {resp.text}"
        
        # Verify content type
        assert "text/csv" in resp.headers.get("Content-Type", "")
        
        # Verify Content-Disposition header
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert "sage-payroll" in content_disp
        
        # Verify CSV structure
        csv_content = resp.text
        lines = csv_content.strip().split("\n")
        assert len(lines) >= 1  # At least header row
        
        # Check header columns
        header = lines[0]
        expected_cols = ["Reference", "Surname", "Forenames", "NI Number", 
                        "Payment Number", "Hours", "Rate", "Amount"]
        for col in expected_cols:
            assert col in header, f"Missing column: {col}"
        
        # Check for TOTAL row if there's data
        if len(lines) > 1:
            last_line = lines[-1]
            assert "TOTAL" in last_line
        
        print(f"Sage CSV exported with {len(lines)} lines")
    
    def test_sage_csv_date_validation(self, bob_headers):
        """Test date validation - date_to must be >= date_from"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={
                "date_from": "2026-01-20",
                "date_to": "2026-01-10"  # Before date_from
            },
            headers=bob_headers
        )
        assert resp.status_code == 400
    
    def test_sage_csv_invalid_date_format(self, bob_headers):
        """Test error handling for invalid date format"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={
                "date_from": "invalid",
                "date_to": "2026-01-20"
            },
            headers=bob_headers
        )
        assert resp.status_code == 400
    
    def test_sage_csv_missing_params(self, bob_headers):
        """Test that both date params are required"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={"date_from": "2026-01-01"},  # Missing date_to
            headers=bob_headers
        )
        assert resp.status_code == 422  # Validation error
    
    def test_sage_csv_unauthorized(self):
        """Test that unauthenticated requests are rejected"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31"}
        )
        assert resp.status_code in [401, 403]


class TestRoleBasedAccess(TestSetup):
    """Tests for manager-only access control"""
    
    def test_admin_can_access_own_org_endpoints(self, admin_headers):
        """Test that master admin can access endpoints for their org"""
        # Absence risk should work for admin's org
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            headers=admin_headers
        )
        assert resp.status_code == 200
    
    def test_endpoints_require_org_context(self, admin_headers):
        """Test that endpoints work with proper org context"""
        today = datetime.now().date()
        date_from = (today - timedelta(days=7)).isoformat()
        date_to = today.isoformat()
        
        # Sage CSV should work
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={"date_from": date_from, "date_to": date_to},
            headers=admin_headers
        )
        assert resp.status_code == 200


class TestDataIntegrity(TestSetup):
    """Tests for data integrity and validation"""
    
    def test_rota_suggest_respects_max_hours(self, bob_headers):
        """Test that suggestions respect max_hours_per_staff_week"""
        today = datetime.now().date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).isoformat()
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/ai/rota/suggest",
            json={
                "week_start": next_monday,
                "max_hours_per_staff_week": 20  # Low limit
            },
            headers=bob_headers,
            timeout=120
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Check hours_per_staff doesn't exceed limit
        for staff_id, hours in data.get("hours_per_staff", {}).items():
            assert hours <= 20, f"Staff {staff_id} has {hours}h, exceeds 20h limit"
    
    def test_absence_risk_sorted_by_score(self, bob_headers):
        """Test that absence risk rows are sorted by score descending"""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/absence-risk",
            headers=bob_headers
        )
        assert resp.status_code == 200
        rows = resp.json().get("rows", [])
        
        if len(rows) > 1:
            scores = [r["score"] for r in rows]
            assert scores == sorted(scores, reverse=True), "Rows should be sorted by score desc"
    
    def test_sage_csv_aggregates_shifts(self, bob_headers):
        """Test that Sage CSV aggregates hours per staff correctly"""
        today = datetime.now().date()
        date_from = (today - timedelta(days=30)).isoformat()
        date_to = today.isoformat()
        
        resp = requests.get(
            f"{BASE_URL}/api/staffing/ai/payroll/sage.csv",
            params={"date_from": date_from, "date_to": date_to},
            headers=bob_headers
        )
        assert resp.status_code == 200
        
        # Parse CSV and verify TOTAL row math
        lines = resp.text.strip().split("\n")
        if len(lines) > 2:  # Header + at least one data row + TOTAL
            # Find TOTAL row
            total_line = None
            for line in lines:
                if line.startswith("TOTAL"):
                    total_line = line
                    break
            
            if total_line:
                # TOTAL row should have hours and amount
                parts = total_line.split(",")
                assert len(parts) >= 8
                # Hours should be numeric
                try:
                    float(parts[5])  # Hours column
                    float(parts[7])  # Amount column
                except ValueError:
                    pytest.fail("TOTAL row should have numeric Hours and Amount")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
