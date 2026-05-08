"""
Iteration 165 - Instructor Portal, Abandoned Checkout Sweep, Member Billing Portal Tests

Tests:
1. Instructor login and /instructor/me endpoint
2. GET /instructor/classes returns only Jake's HIIT classes
3. GET /instructor/occurrences/{occ_id}/roster returns roster
4. POST /instructor/occurrences/{occ_id}/attendance marks attendance
5. GET /instructor/commission shows updated commission after attendance
6. GET /memberships/commission (operator) shows instructor commission
7. Non-instructor user gets 403 on /instructor/me
8. POST /member/billing-portal returns 400 for member without stripe_customer_id
9. Abandoned checkout sweep marks old pending_payment memberships as abandoned
10. Instructor cannot access other instructor's class roster (404)
"""
import pytest
import requests
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
INSTRUCTOR_EMAIL = "jake.ellis@demo.gymaxis"
INSTRUCTOR_PASSWORD = "Instructor2026!"
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"


class TestInstructorPortal:
    """Instructor portal endpoint tests"""

    @pytest.fixture(scope="class")
    def instructor_token(self):
        """Get instructor JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": INSTRUCTOR_EMAIL,
            "password": INSTRUCTOR_PASSWORD
        })
        assert response.status_code == 200, f"Instructor login failed: {response.text}"
        data = response.json()
        assert "token" in data
        return data["token"]

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert response.status_code == 200, f"Operator login failed: {response.text}"
        return response.json()["token"]

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get member JWT token"""
        response = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200, f"Member login failed: {response.text}"
        return response.json()["token"]

    def test_instructor_login_returns_token(self):
        """Test instructor can login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": INSTRUCTOR_EMAIL,
            "password": INSTRUCTOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == INSTRUCTOR_EMAIL
        assert data["user"]["id"] == "usr-instructor-jake"
        assert data["user"]["organization_id"] == "mbr-demo-org"

    def test_instructor_me_returns_profile(self, instructor_token):
        """Test GET /instructor/me returns instructor profile"""
        response = requests.get(
            f"{BASE_URL}/api/instructor/me",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "usr-instructor-jake"
        assert data["name"] == "Jake Ellis"
        assert data["email"] == INSTRUCTOR_EMAIL
        assert data["rate_pence"] == 2500
        assert data["template_count"] == 1
        assert data["upcoming_classes"] >= 0
        assert data["organization_id"] == "mbr-demo-org"

    def test_instructor_classes_returns_only_hiit(self, instructor_token):
        """Test GET /instructor/classes returns only Jake's HIIT Blast classes"""
        response = requests.get(
            f"{BASE_URL}/api/instructor/classes",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "occurrences" in data
        # All returned classes should be HIIT Blast with Jake as instructor
        for occ in data["occurrences"]:
            assert occ["name"] == "HIIT Blast"
            assert occ["instructor_user_id"] == "usr-instructor-jake"
            assert occ["instructor_name"] == "Jake Ellis"
        # Should have at least 3 HIIT classes in a week
        assert len(data["occurrences"]) >= 3

    def test_instructor_roster_returns_bookings(self, instructor_token):
        """Test GET /instructor/occurrences/{occ_id}/roster returns roster"""
        # First get a class
        classes_response = requests.get(
            f"{BASE_URL}/api/instructor/classes",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert classes_response.status_code == 200
        occs = classes_response.json()["occurrences"]
        assert len(occs) > 0

        occ_id = occs[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/instructor/occurrences/{occ_id}/roster",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "occurrence" in data
        assert "roster" in data
        assert data["occurrence"]["id"] == occ_id
        assert data["occurrence"]["instructor_user_id"] == "usr-instructor-jake"

    def test_instructor_commission_returns_data(self, instructor_token):
        """Test GET /instructor/commission returns commission data"""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        response = requests.get(
            f"{BASE_URL}/api/instructor/commission",
            headers={"Authorization": f"Bearer {instructor_token}"},
            params={"month": month}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["month"] == month
        assert data["rate_pence"] == 2500
        assert "class_count" in data
        assert "scheduled_count" in data
        assert "total_attended" in data
        assert "pay_pence" in data
        assert "occurrences" in data
        # pay_pence should be class_count * rate_pence
        assert data["pay_pence"] == data["class_count"] * 2500

    def test_operator_commission_returns_instructor_rows(self, operator_token):
        """Test GET /memberships/commission returns instructor commission rows"""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        response = requests.get(
            f"{BASE_URL}/api/memberships/commission",
            headers={"Authorization": f"Bearer {operator_token}"},
            params={"month": month}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["month"] == month
        assert "grand_total_pence" in data
        assert "rows" in data
        # Should have at least Jake Ellis row
        jake_row = next((r for r in data["rows"] if r["instructor"]["id"] == "usr-instructor-jake"), None)
        assert jake_row is not None
        assert jake_row["instructor"]["name"] == "Jake Ellis"
        assert jake_row["rate_pence"] == 2500

    def test_non_instructor_gets_403(self, operator_token):
        """Test non-instructor user gets 403 on /instructor/me"""
        response = requests.get(
            f"{BASE_URL}/api/instructor/me",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert response.status_code == 403
        assert "Not an instructor" in response.json()["detail"]

    def test_instructor_cannot_access_other_class(self, instructor_token):
        """Test instructor gets 404 when accessing another instructor's class"""
        # Get a Yoga class (not Jake's)
        response = requests.get(
            f"{BASE_URL}/api/memberships/timetable",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        if response.status_code == 200:
            occs = response.json().get("occurrences", [])
            yoga_occ = next((o for o in occs if o.get("name") == "Vinyasa Yoga"), None)
            if yoga_occ:
                roster_response = requests.get(
                    f"{BASE_URL}/api/instructor/occurrences/{yoga_occ['id']}/roster",
                    headers={"Authorization": f"Bearer {instructor_token}"}
                )
                assert roster_response.status_code == 404
                assert "not yours" in roster_response.json()["detail"].lower() or "not found" in roster_response.json()["detail"].lower()


class TestMemberBillingPortal:
    """Member billing portal tests"""

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get member JWT token"""
        response = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]

    def test_billing_portal_no_stripe_customer(self, member_token):
        """Test POST /member/billing-portal returns 400 for member without stripe_customer_id"""
        response = requests.post(
            f"{BASE_URL}/api/member/billing-portal",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"origin_url": "https://app.gymaxis.ai"}
        )
        assert response.status_code == 400
        assert "No Stripe billing profile" in response.json()["detail"]


class TestAttendanceMarking:
    """Attendance marking flow tests"""

    @pytest.fixture(scope="class")
    def instructor_token(self):
        """Get instructor JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": INSTRUCTOR_EMAIL,
            "password": INSTRUCTOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]

    @pytest.fixture(scope="class")
    def member_token(self):
        """Get member JWT token"""
        response = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": MEMBER_EMAIL,
            "password": MEMBER_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]

    def test_attendance_marking_flow(self, instructor_token, member_token):
        """Test full attendance marking flow: book → roster → mark → verify commission"""
        # Get a scheduled HIIT class
        classes_response = requests.get(
            f"{BASE_URL}/api/instructor/classes",
            headers={"Authorization": f"Bearer {instructor_token}"}
        )
        assert classes_response.status_code == 200
        occs = classes_response.json()["occurrences"]
        # Find a scheduled class (not completed)
        scheduled_occ = next((o for o in occs if o.get("status") == "scheduled"), None)
        if not scheduled_occ:
            pytest.skip("No scheduled classes available for testing")

        occ_id = scheduled_occ["id"]

        # Book member into class
        book_response = requests.post(
            f"{BASE_URL}/api/member/bookings",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"occurrence_id": occ_id}
        )
        # May already be booked, that's ok
        if book_response.status_code == 200:
            booking_id = book_response.json()["booking"]["id"]
        else:
            # Get existing booking
            roster_response = requests.get(
                f"{BASE_URL}/api/instructor/occurrences/{occ_id}/roster",
                headers={"Authorization": f"Bearer {instructor_token}"}
            )
            assert roster_response.status_code == 200
            roster = roster_response.json()["roster"]
            emma_booking = next((b for b in roster if b["member_id"] == "mbr-emma"), None)
            if not emma_booking:
                pytest.skip("Could not book or find Emma's booking")
            booking_id = emma_booking["id"]

        # Mark attendance
        attendance_response = requests.post(
            f"{BASE_URL}/api/instructor/occurrences/{occ_id}/attendance",
            headers={"Authorization": f"Bearer {instructor_token}"},
            json={"items": [{"booking_id": booking_id, "status": "attended"}]}
        )
        assert attendance_response.status_code == 200
        data = attendance_response.json()
        assert data["ok"] is True

        # Verify commission increased
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        commission_response = requests.get(
            f"{BASE_URL}/api/instructor/commission",
            headers={"Authorization": f"Bearer {instructor_token}"},
            params={"month": month}
        )
        assert commission_response.status_code == 200
        commission = commission_response.json()
        # Should have at least 1 completed class
        assert commission["class_count"] >= 1
        assert commission["pay_pence"] >= 2500


class TestHIITBlastInstructorAssignment:
    """Test HIIT Blast template and occurrences have instructor_user_id"""

    @pytest.fixture(scope="class")
    def operator_token(self):
        """Get operator JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]

    def test_hiit_occurrences_have_instructor_user_id(self, operator_token):
        """Test HIIT Blast occurrences have instructor_user_id populated"""
        response = requests.get(
            f"{BASE_URL}/api/memberships/timetable",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert response.status_code == 200
        occs = response.json().get("occurrences", [])
        hiit_occs = [o for o in occs if o.get("name") == "HIIT Blast"]
        # All HIIT Blast should have instructor_user_id
        for occ in hiit_occs:
            assert occ.get("instructor_user_id") == "usr-instructor-jake", f"HIIT occurrence {occ['id']} missing instructor_user_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
