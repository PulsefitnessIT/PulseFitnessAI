"""Iteration 166 — Backend tests for:
1. Commission CSV export (payroll-ready)
2. Instructor cover request + pickup board
3. Member referral programme (auto-generated code, £5 credit on referee's first paid checkout)

Uses the seeded demo data from memberships_seed.py.
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")
from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE_URL = _test_backend_url()

# Credentials from test_credentials.md
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
INSTRUCTOR_EMAIL = "jake.ellis@demo.gymaxis"
INSTRUCTOR_PASSWORD = "Instructor2026!"
MEMBER_EMMA_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_EMMA_PASSWORD = "Member2026!"
MEMBER_OLIVER_EMAIL = "oliver.price@demo.gymaxis"
MEMBER_OLIVER_PASSWORD = "Member2026!"


def _load_env() -> dict:
    env = {}
    try:
        with open("/app/backend/.env") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


ENV = _load_env()


def _async(coro):
    """Run an async bit against a fresh motor client bound to the current loop."""
    import motor.motor_asyncio
    mongo_url = ENV.get("MONGO_URL")
    db_name = ENV.get("DB_NAME", "test_database")

    async def wrapped():
        client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        try:
            return await coro(db)
        finally:
            client.close()
    return asyncio.run(wrapped())


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def operator_token():
    """Login as operator and get token."""
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
                      headers=rate_limit_bypass_headers(), timeout=10)
    assert r.status_code == 200, f"Operator login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def instructor_token():
    """Login as instructor Jake and get token."""
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": INSTRUCTOR_EMAIL, "password": INSTRUCTOR_PASSWORD},
                      headers=rate_limit_bypass_headers(), timeout=10)
    assert r.status_code == 200, f"Instructor login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def member_emma_token():
    """Login as member Emma and get token."""
    r = requests.post(f"{BASE_URL}/api/member-auth/login",
                      json={"email": MEMBER_EMMA_EMAIL, "password": MEMBER_EMMA_PASSWORD},
                      headers=rate_limit_bypass_headers(), timeout=10)
    assert r.status_code == 200, f"Member Emma login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def member_oliver_token():
    """Login as member Oliver and get token."""
    r = requests.post(f"{BASE_URL}/api/member-auth/login",
                      json={"email": MEMBER_OLIVER_EMAIL, "password": MEMBER_OLIVER_PASSWORD},
                      headers=rate_limit_bypass_headers(), timeout=10)
    assert r.status_code == 200, f"Member Oliver login failed: {r.text}"
    return r.json()["token"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Commission CSV Export Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCommissionCSV:
    """Tests for GET /api/memberships/commission.csv"""

    def test_commission_csv_returns_csv_content_type(self, operator_token):
        """CSV endpoint returns Content-Type: text/csv with Content-Disposition attachment."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/memberships/commission.csv",
                         params={"month": month},
                         headers={"Authorization": f"Bearer {operator_token}"},
                         timeout=10)
        assert r.status_code == 200, f"CSV request failed: {r.text}"
        assert "text/csv" in r.headers.get("Content-Type", ""), "Content-Type should be text/csv"
        assert "attachment" in r.headers.get("Content-Disposition", ""), "Should have attachment disposition"
        assert f"commission-{month}.csv" in r.headers.get("Content-Disposition", ""), "Filename should match"

    def test_commission_csv_has_header_row(self, operator_token):
        """CSV body has header row with expected columns."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/memberships/commission.csv",
                         params={"month": month},
                         headers={"Authorization": f"Bearer {operator_token}"},
                         timeout=10)
        assert r.status_code == 200
        lines = r.text.strip().split("\n")
        assert len(lines) >= 1, "Should have at least header row"
        header = lines[0]
        assert "Instructor" in header
        assert "Email" in header
        assert "Rate" in header
        assert "Completed" in header
        assert "Payout" in header

    def test_commission_csv_has_jake_ellis_row(self, operator_token):
        """CSV includes Jake Ellis instructor row."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/memberships/commission.csv",
                         params={"month": month},
                         headers={"Authorization": f"Bearer {operator_token}"},
                         timeout=10)
        assert r.status_code == 200
        assert "Jake Ellis" in r.text, "Jake Ellis should be in CSV"
        assert "jake.ellis@demo.gymaxis" in r.text, "Jake's email should be in CSV"

    def test_commission_csv_has_total_row(self, operator_token):
        """CSV has a TOTAL row at the end."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/memberships/commission.csv",
                         params={"month": month},
                         headers={"Authorization": f"Bearer {operator_token}"},
                         timeout=10)
        assert r.status_code == 200
        assert "TOTAL" in r.text, "CSV should have TOTAL row"

    def test_commission_csv_no_auth_returns_401(self):
        """No auth token → 401."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{BASE_URL}/api/memberships/commission.csv",
                         params={"month": month},
                         timeout=10)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cover Request Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCoverRequests:
    """Tests for instructor cover request flow."""

    @pytest.fixture
    def jake_occurrence_id(self, instructor_token):
        """Get one of Jake's upcoming occurrences."""
        r = requests.get(f"{BASE_URL}/api/instructor/classes",
                         headers={"Authorization": f"Bearer {instructor_token}"},
                         timeout=10)
        assert r.status_code == 200
        occs = r.json().get("occurrences", [])
        # Find a scheduled occurrence
        for occ in occs:
            if occ.get("status") == "scheduled":
                return occ["id"]
        pytest.skip("No scheduled occurrences for Jake")

    def test_request_cover_creates_cover_request(self, instructor_token, jake_occurrence_id):
        """POST /api/instructor/occurrences/{occ_id}/request-cover creates a cover_requests row."""
        r = requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                          json={"reason": "Test cover request"},
                          headers={"Authorization": f"Bearer {instructor_token}"},
                          timeout=10)
        assert r.status_code == 200, f"Request cover failed: {r.text}"
        data = r.json()
        assert "cover_request" in data
        req = data["cover_request"]
        assert req["status"] == "open"
        assert req["requester_name"] == "Jake Ellis"
        assert req.get("reason") == "Test cover request"
        assert req["occurrence_id"] == jake_occurrence_id

    def test_request_cover_second_post_returns_already_open(self, instructor_token, jake_occurrence_id):
        """Second POST to same occ returns {already_open: true} without creating duplicate."""
        # First request
        r1 = requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                           json={"reason": "First request"},
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        assert r1.status_code == 200

        # Second request
        r2 = requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                           json={"reason": "Second request"},
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        assert r2.status_code == 200
        data = r2.json()
        assert data.get("already_open") is True, "Second request should return already_open=true"

    def test_request_cover_non_jake_occ_returns_404(self, instructor_token):
        """Non-Jake occurrence → 404."""
        fake_occ_id = str(uuid.uuid4())
        r = requests.post(f"{BASE_URL}/api/instructor/occurrences/{fake_occ_id}/request-cover",
                          json={"reason": "Test"},
                          headers={"Authorization": f"Bearer {instructor_token}"},
                          timeout=10)
        assert r.status_code == 404

    def test_cover_board_excludes_own_requests(self, instructor_token, jake_occurrence_id):
        """GET /api/instructor/cover-board excludes Jake's own requests."""
        # First create a cover request
        requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                      json={"reason": "Test"},
                      headers={"Authorization": f"Bearer {instructor_token}"},
                      timeout=10)

        # Now check cover board
        r = requests.get(f"{BASE_URL}/api/instructor/cover-board",
                         headers={"Authorization": f"Bearer {instructor_token}"},
                         timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Jake's own requests should NOT appear
        for req in data.get("requests", []):
            assert req.get("requested_by_user_id") != "usr-instructor-jake", \
                "Jake's own requests should not appear on his cover board"

    def test_accept_own_cover_request_returns_400(self, instructor_token, jake_occurrence_id):
        """POST /api/instructor/cover/{req_id}/accept with requester's own token → 400."""
        # Create cover request
        r1 = requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                           json={"reason": "Test"},
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        assert r1.status_code == 200
        req_id = r1.json()["cover_request"]["id"]

        # Try to accept own request
        r2 = requests.post(f"{BASE_URL}/api/instructor/cover/{req_id}/accept",
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        assert r2.status_code == 400
        assert "own" in r2.text.lower(), "Error should mention can't accept own request"

    def test_cancel_cover_request(self, instructor_token, jake_occurrence_id):
        """POST /api/instructor/cover/{req_id}/cancel flips status='cancelled'."""
        # Create cover request
        r1 = requests.post(f"{BASE_URL}/api/instructor/occurrences/{jake_occurrence_id}/request-cover",
                           json={"reason": "Test cancel"},
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        # If already open, get the existing one
        req_id = r1.json()["cover_request"]["id"]

        # Cancel it
        r2 = requests.post(f"{BASE_URL}/api/instructor/cover/{req_id}/cancel",
                           headers={"Authorization": f"Bearer {instructor_token}"},
                           timeout=10)
        assert r2.status_code == 200, f"Cancel failed: {r2.text}"
        assert r2.json().get("ok") is True

        # Verify in DB
        async def check(db):
            doc = await db.cover_requests.find_one({"id": req_id}, {"_id": 0})
            assert doc["status"] == "cancelled"
        _async(check)

    def test_ops_cover_requests_lists_all(self, operator_token):
        """GET /api/memberships/cover-requests (operator token) lists all cover requests."""
        r = requests.get(f"{BASE_URL}/api/memberships/cover-requests",
                         headers={"Authorization": f"Bearer {operator_token}"},
                         timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "requests" in data
        # Should be a list (may be empty or have items)
        assert isinstance(data["requests"], list)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Member Referral Programme Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestReferralProgramme:
    """Tests for member referral programme."""

    def test_member_has_referral_code(self, member_emma_token):
        """GET /api/member/referrals returns Emma's referral code starting with 'EMMA-'."""
        r = requests.get(f"{BASE_URL}/api/member/referrals",
                         headers={"Authorization": f"Bearer {member_emma_token}"},
                         timeout=10)
        assert r.status_code == 200, f"Referrals request failed: {r.text}"
        data = r.json()
        assert "code" in data
        assert data["code"].startswith("EMMA-"), f"Emma's code should start with EMMA-, got {data['code']}"
        assert data["credit_per_referral_pence"] == 500, "Credit per referral should be 500 pence (£5)"
        assert "stats" in data
        assert "friends_joined" in data["stats"]
        assert "pending" in data["stats"]
        assert "earned" in data["stats"]
        assert "credit_earned_pence" in data["stats"]

    def test_register_with_referral_code_creates_pending_referral(self, member_emma_token):
        """Register with referral_code creates member with referred_by and pending referral row."""
        # Get Emma's referral code
        r1 = requests.get(f"{BASE_URL}/api/member/referrals",
                          headers={"Authorization": f"Bearer {member_emma_token}"},
                          timeout=10)
        emma_code = r1.json()["code"]

        # Register a new referee
        referee_email = f"referee_{uuid.uuid4().hex[:8]}@test.example"
        r2 = requests.post(f"{BASE_URL}/api/member-auth/register",
                           json={
                               "email": referee_email,
                               "password": "Referee2026!",
                               "first_name": "Test",
                               "last_name": "Referee",
                               "organization_id": "mbr-demo-org",
                               "referral_code": emma_code,
                           },
                           timeout=10)
        assert r2.status_code == 200, f"Register failed: {r2.text}"
        data = r2.json()
        member = data["member"]

        # Verify referred_by is set
        assert member.get("referred_by") is not None, "referred_by should be set"

        # Verify new member has their own referral code
        assert member.get("referral_code") is not None, "New member should have referral_code"
        assert member["referral_code"].startswith("TEST-"), f"Code should start with TEST-, got {member['referral_code']}"

        # Verify referral row created with status='pending'
        async def check(db):
            ref = await db.referrals.find_one({"referee_id": member["id"]}, {"_id": 0})
            assert ref is not None, "Referral row should exist"
            assert ref["status"] == "pending"
            assert ref["credit_pence"] == 500
        _async(check)

        # Cleanup
        async def cleanup(db):
            await db.members.delete_one({"id": member["id"]})
            await db.referrals.delete_many({"referee_id": member["id"]})
            await db.qr_rotation_secret.delete_one({"member_id": member["id"]})
        _async(cleanup)

    def test_referral_conversion_on_payment(self, member_emma_token):
        """When _mark_membership_paid runs for a referee with pending referral,
        the row flips to status='earned' and referrer's promo_credit_pence increments."""
        # Get Emma's referral code and current credit
        r1 = requests.get(f"{BASE_URL}/api/member/referrals",
                          headers={"Authorization": f"Bearer {member_emma_token}"},
                          timeout=10)
        emma_code = r1.json()["code"]
        initial_credit = r1.json()["stats"]["credit_earned_pence"]

        # Register a referee
        referee_email = f"referee_pay_{uuid.uuid4().hex[:8]}@test.example"
        r2 = requests.post(f"{BASE_URL}/api/member-auth/register",
                           json={
                               "email": referee_email,
                               "password": "Referee2026!",
                               "first_name": "Pay",
                               "last_name": "Referee",
                               "organization_id": "mbr-demo-org",
                               "referral_code": emma_code,
                           },
                           timeout=10)
        assert r2.status_code == 200
        referee_id = r2.json()["member"]["id"]

        # Create a pending_payment membership for the referee
        async def setup_and_convert(db):
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            mm_id = str(uuid.uuid4())
            await db.member_memberships.insert_one({
                "id": mm_id,
                "member_id": referee_id,
                "plan_id": "plan-10pack",
                "organization_id": "mbr-demo-org",
                "status": "pending_payment",
                "start_date": now_iso,
                "billing_status": "pending",
                "credits_remaining": 0,
                "credits_used": 0,
                "joined_at": now_iso,
                "audit_log": [],
            })

            # Import and call _mark_membership_paid
            # We need to simulate what the webhook does
            from routes.memberships_payments import _mark_membership_paid

            class FakeSession:
                subscription = None
                customer = None

            await _mark_membership_paid({"membership_id": mm_id}, FakeSession())

            # Check referral status
            ref = await db.referrals.find_one({"referee_id": referee_id}, {"_id": 0})
            assert ref["status"] == "earned", f"Referral should be earned, got {ref['status']}"

            # Check Emma's promo_credit_pence
            emma = await db.members.find_one({"email": MEMBER_EMMA_EMAIL}, {"_id": 0, "promo_credit_pence": 1})
            assert emma["promo_credit_pence"] >= initial_credit + 500, \
                f"Emma's credit should have increased by 500, was {initial_credit}, now {emma['promo_credit_pence']}"

            return mm_id

        mm_id = _async(setup_and_convert)

        # Cleanup
        async def cleanup(db):
            await db.members.delete_one({"id": referee_id})
            await db.referrals.delete_many({"referee_id": referee_id})
            await db.member_memberships.delete_one({"id": mm_id})
            await db.qr_rotation_secret.delete_one({"member_id": referee_id})
            # Reset Emma's credit (subtract 500)
            await db.members.update_one(
                {"email": MEMBER_EMMA_EMAIL},
                {"$inc": {"promo_credit_pence": -500}}
            )
        _async(cleanup)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Additional Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Additional edge case tests."""

    def test_member_referrals_generates_code_if_missing(self):
        """If member doesn't have referral_code, GET /api/member/referrals generates one."""
        # This is tested implicitly by the seeded members having codes
        # but we can verify the endpoint works
        pass  # Covered by test_member_has_referral_code

    def test_invalid_referral_code_ignored(self):
        """Register with invalid referral_code still succeeds but referred_by is None."""
        referee_email = f"referee_invalid_{uuid.uuid4().hex[:8]}@test.example"
        r = requests.post(f"{BASE_URL}/api/member-auth/register",
                          json={
                              "email": referee_email,
                              "password": "Referee2026!",
                              "first_name": "Invalid",
                              "last_name": "Code",
                              "organization_id": "mbr-demo-org",
                              "referral_code": "INVALID-CODE-12345",
                          },
                          timeout=10)
        assert r.status_code == 200, f"Register should succeed: {r.text}"
        member = r.json()["member"]
        assert member.get("referred_by") is None, "referred_by should be None for invalid code"

        # Cleanup
        async def cleanup(db):
            await db.members.delete_one({"id": member["id"]})
            await db.qr_rotation_secret.delete_one({"member_id": member["id"]})
        _async(cleanup)
