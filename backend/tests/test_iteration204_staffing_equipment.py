"""
Iteration 204 Tests — Staffing Tab, Equipment Photo Upload, Onboarding Wizard

Tests:
1. P0: Staffing backend endpoints (GET /api/staffing/staff, live-floor, rules, announcements, leave, marketplace/open)
2. P0: POST /api/staffing/staff to create staff, POST /api/staffing/shifts to create shift
3. P0: Equipment photo upload with PNG magic bytes (tests file_validation.py fallback)
4. P1: GET /api/equipment/template/csv returns CSV template
5. Regression: Health, login, equipment endpoints
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
LEE_SOMERS_EMAIL = "lee.somers@pulsefitness.com"
LEE_SOMERS_PASSWORD = "TempPass123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def lee_somers_token():
    """Get auth token for Lee Somers (Pulse Pro owner)"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": LEE_SOMERS_EMAIL,
        "password": LEE_SOMERS_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for master admin"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["token"]


class TestRegression:
    """Sanity checks — ensure existing endpoints still work"""

    def test_health_endpoint(self):
        """GET /api/health returns 200"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_login_lee_somers(self, lee_somers_token):
        """Login with lee.somers works"""
        assert lee_somers_token is not None
        assert len(lee_somers_token) > 20

    def test_get_equipment(self, lee_somers_token):
        """GET /api/equipment returns 200"""
        resp = requests.get(f"{BASE_URL}/api/equipment", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should have equipment list
        assert "equipment" in data or isinstance(data, list)


class TestStaffingEndpoints:
    """P0: Test all staffing backend endpoints"""

    def test_get_staffing_staff(self, lee_somers_token):
        """GET /api/staffing/staff returns 200 with staff list"""
        resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "staff" in data
        assert "role" in data
        print(f"Staff count: {len(data['staff'])}, role: {data['role']}")

    def test_get_staffing_live_floor(self, lee_somers_token):
        """GET /api/staffing/live-floor returns 200"""
        resp = requests.get(f"{BASE_URL}/api/staffing/live-floor", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "as_of" in data
        assert "on_now" in data
        assert "upcoming" in data
        assert "coverage" in data
        print(f"Live floor: {data['coverage']}")

    def test_get_staffing_rules(self, lee_somers_token):
        """GET /api/staffing/rules returns 200 with compliance rules"""
        resp = requests.get(f"{BASE_URL}/api/staffing/rules", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        # Should have default rules
        assert "max_hours_per_week" in data
        assert "min_rest_hours_between_shifts" in data
        print(f"Rules: max_hours={data.get('max_hours_per_week')}")

    def test_get_staffing_announcements(self, lee_somers_token):
        """GET /api/staffing/announcements returns 200"""
        resp = requests.get(f"{BASE_URL}/api/staffing/announcements", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "announcements" in data
        print(f"Announcements count: {len(data['announcements'])}")

    def test_get_staffing_leave(self, lee_somers_token):
        """GET /api/staffing/leave returns 200"""
        resp = requests.get(f"{BASE_URL}/api/staffing/leave", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "leave" in data
        assert "role" in data
        print(f"Leave requests: {len(data['leave'])}")

    def test_get_staffing_marketplace_open(self, lee_somers_token):
        """GET /api/staffing/marketplace/open returns 200"""
        resp = requests.get(f"{BASE_URL}/api/staffing/marketplace/open", headers={
            "Authorization": f"Bearer {lee_somers_token}"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "open_shifts" in data
        print(f"Open shifts: {len(data['open_shifts'])}")


class TestStaffingCRUD:
    """P0: Test staff and shift creation"""

    def test_create_staff_member(self, lee_somers_token):
        """POST /api/staffing/staff creates a staff record"""
        unique_name = f"TEST_Staff_{uuid.uuid4().hex[:8]}"
        resp = requests.post(f"{BASE_URL}/api/staffing/staff",
            headers={"Authorization": f"Bearer {lee_somers_token}"},
            json={
                "full_name": unique_name,
                "primary_role": "reception",
                "hourly_cost": 15.0
            }
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("full_name") == unique_name
        assert data.get("primary_role") == "reception"
        assert data.get("hourly_cost") == 15.0
        assert "id" in data
        print(f"Created staff: {data['id']}")
        # Store for shift test
        pytest.staff_id = data["id"]

    def test_get_shifts_with_date_range(self, lee_somers_token):
        """GET /api/staffing/shifts with date_from/date_to returns 200"""
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        resp = requests.get(f"{BASE_URL}/api/staffing/shifts",
            headers={"Authorization": f"Bearer {lee_somers_token}"},
            params={"date_from": today, "date_to": next_week}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "shifts" in data
        print(f"Shifts in range: {len(data['shifts'])}")

    def test_create_shift(self, lee_somers_token):
        """POST /api/staffing/shifts creates a shift"""
        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Use the staff_id from previous test if available
        staff_id = getattr(pytest, 'staff_id', None)

        resp = requests.post(f"{BASE_URL}/api/staffing/shifts",
            headers={"Authorization": f"Bearer {lee_somers_token}"},
            json={
                "staff_id": staff_id,
                "date": tomorrow,
                "start_time": "09:00",
                "end_time": "17:00",
                "role": "reception",
                "status": "scheduled"
            }
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "shift" in data
        shift = data["shift"]
        assert shift.get("date") == tomorrow
        assert shift.get("start_time") == "09:00"
        assert shift.get("end_time") == "17:00"
        print(f"Created shift: {shift.get('id')}")


class TestEquipmentPhotoUpload:
    """P0: Test equipment photo upload with file validation"""

    def test_create_equipment_and_upload_photo(self, lee_somers_token):
        """Create equipment then upload a PNG photo"""
        # First create equipment
        unique_name = f"TEST_Equipment_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {lee_somers_token}"},
            json={
                "name": unique_name,
                "serial_number": f"SN-{uuid.uuid4().hex[:8]}",
                "equipment_type": "Treadmill",
                "manufacturer": "Test Manufacturer"
            }
        )
        assert create_resp.status_code in [200, 201], f"Create equipment failed: {create_resp.text}"
        equipment = create_resp.json()
        equipment_id = equipment.get("id")
        assert equipment_id, "No equipment ID returned"
        print(f"Created equipment: {equipment_id}")

        # Create a valid PNG file (minimal PNG with correct magic bytes)
        # PNG magic bytes: \x89PNG\r\n\x1a\n
        png_header = b'\x89PNG\r\n\x1a\n'
        # IHDR chunk (image header)
        ihdr_data = b'\x00\x00\x00\x01'  # width: 1
        ihdr_data += b'\x00\x00\x00\x01'  # height: 1
        ihdr_data += b'\x08\x02'  # bit depth: 8, color type: 2 (RGB)
        ihdr_data += b'\x00\x00\x00'  # compression, filter, interlace

        import zlib
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr_chunk = b'\x00\x00\x00\x0d' + b'IHDR' + ihdr_data + ihdr_crc.to_bytes(4, 'big')

        # IDAT chunk (image data - minimal)
        idat_data = zlib.compress(b'\x00\xff\x00\x00')  # one red pixel
        idat_crc = zlib.crc32(b'IDAT' + idat_data) & 0xffffffff
        idat_chunk = len(idat_data).to_bytes(4, 'big') + b'IDAT' + idat_data + idat_crc.to_bytes(4, 'big')

        # IEND chunk
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend_chunk = b'\x00\x00\x00\x00' + b'IEND' + iend_crc.to_bytes(4, 'big')

        png_bytes = png_header + ihdr_chunk + idat_chunk + iend_chunk

        # Upload photo
        files = {'file': ('test_photo.png', png_bytes, 'image/png')}
        upload_resp = requests.post(
            f"{BASE_URL}/api/equipment/{equipment_id}/photo",
            headers={"Authorization": f"Bearer {lee_somers_token}"},
            files=files
        )
        assert upload_resp.status_code == 200, f"Photo upload failed: {upload_resp.text}"
        data = upload_resp.json()
        assert "photo_url" in data
        print(f"Photo uploaded: {data['photo_url']}")


class TestOnboardingWizardCSVTemplate:
    """P1: Test CSV template download endpoint"""

    def test_get_equipment_csv_template(self, lee_somers_token):
        """GET /api/equipment/template/csv returns CSV with correct headers"""
        resp = requests.get(f"{BASE_URL}/api/equipment/template/csv",
            headers={"Authorization": f"Bearer {lee_somers_token}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

        # Check content type
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type or "text/plain" in content_type, f"Wrong content type: {content_type}"

        # Check Content-Disposition header
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, f"Missing attachment header: {content_disp}"

        # Check CSV content
        csv_content = resp.text
        assert len(csv_content) > 0, "Empty CSV"
        print(f"CSV template first 200 chars: {csv_content[:200]}")


class TestTrialUserOnboarding:
    """P1: Test fresh trial user registration for onboarding wizard"""

    def test_register_fresh_trial_user(self):
        """POST /api/auth/register creates a fresh trial user"""
        unique_email = f"onboard.test+{uuid.uuid4().hex[:8]}@example.com"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "OnboardTest123!",
            "full_name": "Onboarding Tester",
            "company_name": "Onboard Test Gym"
        })
        # Accept 200 or 201
        assert resp.status_code in [200, 201], f"Registration failed: {resp.text}"
        data = resp.json()
        # Should have token or user info
        assert "token" in data or "user" in data or "id" in data
        print(f"Registered trial user: {unique_email}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
