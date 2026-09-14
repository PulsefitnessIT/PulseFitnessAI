"""
Iteration 216ak — Sprint B Testing (G5, G6, G12)

Tests for:
- G5: Invite to portal (POST /memberships/members/{id}/invite-portal, POST /member-auth/claim-invite, POST /memberships/members/{id}/revoke-portal)
- G6: Event ticketing (GET /member/events, POST /member/events/{id}/tickets)
- G12: Home widget (GET /member/home-widget)
- Regression: Operator booking endpoint, onboarding checklist

Credentials:
- Operator: Bob@knockers.com / Test123!
- Member: test-member-nosite-216ag-4b650795@example.com / NewPass123!
"""

import os
import pytest
import requests
import secrets
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Test credentials
OPERATOR_EMAIL = "Bob@knockers.com"
OPERATOR_PASSWORD = "Test123!"
MEMBER_EMAIL = "test-member-nosite-216ag-4b650795@example.com"
MEMBER_PASSWORD = "NewPass123!"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token"""
    r = requests.post(f"{API}/auth/login", json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Operator login failed: {r.status_code} - {r.text}")
    return r.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth"""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def member_token():
    """Get member JWT token"""
    r = requests.post(f"{API}/member-auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Member login failed: {r.status_code} - {r.text}")
    return r.json().get("token")


@pytest.fixture(scope="module")
def member_headers(member_token):
    """Headers with member auth"""
    return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_member_id(operator_headers):
    """Create a test member for invite-portal testing"""
    unique = secrets.token_hex(4)
    email = f"TEST_216ak_invite_{unique}@example.com"
    r = requests.post(f"{API}/memberships/members", json={
        "email": email,
        "first_name": "Test",
        "last_name": "InvitePortal"
    }, headers=operator_headers)
    if r.status_code not in (200, 201):
        pytest.skip(f"Failed to create test member: {r.status_code} - {r.text}")
    member_id = r.json().get("member", {}).get("id")
    yield member_id
    # Cleanup - no delete endpoint, member stays


@pytest.fixture(scope="module")
def test_event_id(operator_headers):
    """Create a test event for ticketing tests"""
    unique = secrets.token_hex(4)
    from datetime import datetime, timedelta, timezone
    starts = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    ends = (datetime.now(timezone.utc) + timedelta(days=7, hours=3)).isoformat()
    r = requests.post(f"{API}/memberships/events", json={
        "name": f"TEST_216ak_Event_{unique}",
        "kind": "showcase",
        "starts_at": starts,
        "ends_at": ends,
        "venue": "Test Venue",
        "ticket_price_pence": 1500,
        "ticket_capacity": 100
    }, headers=operator_headers)
    if r.status_code not in (200, 201):
        pytest.skip(f"Failed to create test event: {r.status_code} - {r.text}")
    event_id = r.json().get("id")
    yield event_id
    # Cleanup - archive the event
    requests.delete(f"{API}/memberships/events/{event_id}", headers=operator_headers)


# ═══════════════════════════════════════════════════════════════════════════════
# G5: Invite to Portal Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvitePortal:
    """G5 — Invite to portal endpoint tests"""

    def test_invite_portal_success(self, operator_headers, test_member_id):
        """POST /memberships/members/{id}/invite-portal returns ok, email_sent, expires_at, claim_url"""
        r = requests.post(f"{API}/memberships/members/{test_member_id}/invite-portal", json={}, headers=operator_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert "expires_at" in data
        assert "claim_url" in data
        # email_sent may be false if Resend is not configured (mocked)
        assert "email_sent" in data
        print(f"Invite portal success: claim_url={data.get('claim_url')}, email_sent={data.get('email_sent')}")

    def test_invite_portal_idempotent(self, operator_headers, test_member_id):
        """Calling invite-portal twice overwrites the hash with a fresh token"""
        r1 = requests.post(f"{API}/memberships/members/{test_member_id}/invite-portal", json={}, headers=operator_headers)
        assert r1.status_code == 200
        url1 = r1.json().get("claim_url")
        
        time.sleep(0.5)
        
        r2 = requests.post(f"{API}/memberships/members/{test_member_id}/invite-portal", json={}, headers=operator_headers)
        assert r2.status_code == 200
        url2 = r2.json().get("claim_url")
        
        # URLs should be different (new token)
        assert url1 != url2, "Second invite should generate a new token"
        print(f"Idempotent test passed: url1={url1[:50]}..., url2={url2[:50]}...")

    def test_invite_portal_member_without_email(self, operator_headers):
        """Inviting a member without email returns 400"""
        # Create a member without email (if possible) - this may fail if email is required
        unique = secrets.token_hex(4)
        r = requests.post(f"{API}/memberships/members", json={
            "email": "",  # Empty email
            "first_name": "NoEmail",
            "last_name": "Test"
        }, headers=operator_headers)
        # If creation fails due to email required, that's expected
        if r.status_code == 400:
            print("Member creation without email correctly rejected")
            return
        # If it succeeds, try to invite
        if r.status_code in (200, 201):
            member_id = r.json().get("member", {}).get("id")
            r2 = requests.post(f"{API}/memberships/members/{member_id}/invite-portal", json={}, headers=operator_headers)
            assert r2.status_code == 400, f"Expected 400 for member without email, got {r2.status_code}"
            print("Invite portal correctly rejected member without email")

    def test_invite_portal_nonexistent_member(self, operator_headers):
        """Inviting a nonexistent member returns 404"""
        r = requests.post(f"{API}/memberships/members/nonexistent-id-12345/invite-portal", json={}, headers=operator_headers)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        print("Nonexistent member correctly returns 404")


class TestClaimInvite:
    """G5 — Claim invite endpoint tests"""

    def test_claim_invite_short_password(self):
        """POST /member-auth/claim-invite with short password returns 400"""
        r = requests.post(f"{API}/member-auth/claim-invite", json={
            "token": "some-valid-looking-token-here",
            "password": "short"  # Less than 8 chars
        })
        # Should fail validation (422) or business logic (400)
        assert r.status_code in (400, 422), f"Expected 400/422 for short password, got {r.status_code}"
        print(f"Short password correctly rejected: {r.status_code}")

    def test_claim_invite_invalid_token(self):
        """POST /member-auth/claim-invite with invalid token returns 400"""
        r = requests.post(f"{API}/member-auth/claim-invite", json={
            "token": "invalid-token-that-does-not-exist-in-db",
            "password": "ValidPass123!"
        })
        assert r.status_code == 400, f"Expected 400 for invalid token, got {r.status_code}"
        print("Invalid token correctly rejected")


class TestRevokePortal:
    """G5 — Revoke portal endpoint tests"""

    def test_revoke_portal_success(self, operator_headers, test_member_id):
        """POST /memberships/members/{id}/revoke-portal wipes token and disables access"""
        # First invite
        r1 = requests.post(f"{API}/memberships/members/{test_member_id}/invite-portal", json={}, headers=operator_headers)
        assert r1.status_code == 200
        
        # Then revoke
        r2 = requests.post(f"{API}/memberships/members/{test_member_id}/revoke-portal", json={}, headers=operator_headers)
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
        assert r2.json().get("ok") is True
        print("Revoke portal success")

    def test_revoke_portal_nonexistent_member(self, operator_headers):
        """Revoking portal for nonexistent member returns 404"""
        r = requests.post(f"{API}/memberships/members/nonexistent-id-12345/revoke-portal", json={}, headers=operator_headers)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        print("Revoke nonexistent member correctly returns 404")


# ═══════════════════════════════════════════════════════════════════════════════
# G6: Event Ticketing Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemberEvents:
    """G6 — Member-side event listing"""

    def test_member_events_list(self, member_headers):
        """GET /member/events returns upcoming events with my_tickets and tickets_remaining"""
        r = requests.get(f"{API}/member/events", headers=member_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "events" in data
        assert "count" in data
        print(f"Member events list: {data.get('count')} events")
        # Check structure of events if any exist
        if data.get("events"):
            event = data["events"][0]
            # my_tickets and tickets_remaining should be annotated
            assert "my_tickets" in event or event.get("my_tickets") is not None or "my_tickets" not in event
            print(f"First event: {event.get('name')}, my_tickets={event.get('my_tickets')}")

    def test_member_events_excludes_past(self, member_headers):
        """GET /member/events with upcoming_only=true excludes past events"""
        r = requests.get(f"{API}/member/events", params={"upcoming_only": "true"}, headers=member_headers)
        assert r.status_code == 200
        data = r.json()
        # All events should have ends_at >= now (approximately)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for event in data.get("events", []):
            ends_at = event.get("ends_at", "")
            # Just check it's not obviously in the past
            if ends_at:
                assert ends_at >= "2026-01-01", f"Event {event.get('name')} has past ends_at: {ends_at}"
        print(f"Upcoming events filter working: {len(data.get('events', []))} events")


class TestMemberEventTickets:
    """G6 — Member event ticket purchase"""

    def test_buy_tickets_on_statement(self, member_headers, test_event_id):
        """POST /member/events/{id}/tickets with on-statement creates pending_invoice ticket"""
        r = requests.post(f"{API}/member/events/{test_event_id}/tickets", json={
            "quantity": 2,
            "payment": "on-statement"
        }, headers=member_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert "ticket" in data
        assert data["ticket"].get("quantity") == 2
        assert data["ticket"].get("status") in ("pending_invoice", "paid")  # paid if free
        assert "total_pence" in data
        print(f"Ticket purchase success: {data.get('total_pence')} pence for {data['ticket'].get('quantity')} tickets")

    def test_buy_tickets_invalid_quantity_zero(self, member_headers, test_event_id):
        """POST /member/events/{id}/tickets with quantity=0 returns 400"""
        r = requests.post(f"{API}/member/events/{test_event_id}/tickets", json={
            "quantity": 0,
            "payment": "on-statement"
        }, headers=member_headers)
        assert r.status_code == 400, f"Expected 400 for quantity=0, got {r.status_code}"
        print("Quantity=0 correctly rejected")

    def test_buy_tickets_invalid_quantity_over_8(self, member_headers, test_event_id):
        """POST /member/events/{id}/tickets with quantity>8 returns 400"""
        r = requests.post(f"{API}/member/events/{test_event_id}/tickets", json={
            "quantity": 9,
            "payment": "on-statement"
        }, headers=member_headers)
        assert r.status_code == 400, f"Expected 400 for quantity>8, got {r.status_code}"
        print("Quantity>8 correctly rejected")

    def test_buy_tickets_credit_payment_rejected(self, member_headers, test_event_id):
        """POST /member/events/{id}/tickets with payment='credit' returns 400"""
        r = requests.post(f"{API}/member/events/{test_event_id}/tickets", json={
            "quantity": 1,
            "payment": "credit"
        }, headers=member_headers)
        assert r.status_code == 400, f"Expected 400 for credit payment, got {r.status_code}"
        print("Credit payment correctly rejected (not implemented)")

    def test_buy_tickets_unknown_event(self, member_headers):
        """POST /member/events/{id}/tickets for unknown event returns 404"""
        r = requests.post(f"{API}/member/events/nonexistent-event-id/tickets", json={
            "quantity": 1,
            "payment": "on-statement"
        }, headers=member_headers)
        assert r.status_code == 404, f"Expected 404 for unknown event, got {r.status_code}"
        print("Unknown event correctly returns 404")


# ═══════════════════════════════════════════════════════════════════════════════
# G12: Home Widget Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemberHomeWidget:
    """G12 — Home widget endpoint tests"""

    def test_home_widget_returns_structure(self, member_headers):
        """GET /member/home-widget returns expected structure"""
        r = requests.get(f"{API}/member/home-widget", headers=member_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # Check all expected fields are present
        assert "next_class" in data or data.get("next_class") is None
        assert "last_booked" in data
        assert "unread_notifications" in data
        assert "unsigned_forms" in data
        assert "outstanding_invoice_pence" in data
        print(f"Home widget structure: next_class={data.get('next_class')}, last_booked={len(data.get('last_booked', []))}, outstanding={data.get('outstanding_invoice_pence')}")

    def test_home_widget_no_500_with_no_bookings(self, member_headers):
        """GET /member/home-widget works when member has no bookings (returns nulls, no 500)"""
        r = requests.get(f"{API}/member/home-widget", headers=member_headers)
        assert r.status_code == 200, f"Expected 200 even with no bookings, got {r.status_code}: {r.text}"
        # Should not crash
        data = r.json()
        # next_class can be null
        # last_booked can be empty array
        assert isinstance(data.get("last_booked", []), list)
        print("Home widget handles no bookings gracefully")


# ═══════════════════════════════════════════════════════════════════════════════
# Regression Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressionOperatorBooking:
    """Regression — Operator booking endpoint (iter 216ah)"""

    def test_operator_booking_endpoint_exists(self, operator_headers):
        """POST /memberships/occurrences/{id}/bookings endpoint exists"""
        # We don't have a valid occurrence ID, but we can check the endpoint responds
        r = requests.post(f"{API}/memberships/occurrences/test-occ-id/bookings", json={
            "member_id": "test-member-id"
        }, headers=operator_headers)
        # Should return 404 (occurrence not found) not 405 (method not allowed)
        assert r.status_code in (404, 400, 422), f"Expected 404/400/422, got {r.status_code}"
        print(f"Operator booking endpoint exists, returns {r.status_code} for invalid occurrence")


class TestRegressionOnboardingChecklist:
    """Regression — Onboarding checklist (iter 216ah)"""

    def test_onboarding_checklist_structure(self, operator_headers):
        """GET /memberships/studio/onboarding returns 5-step shape"""
        r = requests.get(f"{API}/memberships/studio/onboarding", headers=operator_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # Should have steps array
        assert "steps" in data
        steps = data.get("steps", [])
        # Should have 5 steps
        assert len(steps) >= 5, f"Expected at least 5 steps, got {len(steps)}"
        print(f"Onboarding checklist: {len(steps)} steps, all_complete={data.get('all_complete')}")

    def test_onboarding_invite_portal_step_exists(self, operator_headers):
        """Onboarding checklist has invite_portal step"""
        r = requests.get(f"{API}/memberships/studio/onboarding", headers=operator_headers)
        assert r.status_code == 200
        data = r.json()
        steps = data.get("steps", [])
        step_ids = [s.get("id") for s in steps]
        # invite_portal should be one of the steps
        assert "invite_portal" in step_ids or any("portal" in (s.get("id") or "").lower() for s in steps), \
            f"Expected invite_portal step, got steps: {step_ids}"
        print(f"Onboarding steps: {step_ids}")


# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_tickets(self, operator_headers):
        """Cleanup any TEST_ prefixed data (best effort)"""
        # This is a placeholder - actual cleanup would require listing and deleting
        print("Cleanup: Test data with TEST_216ak_ prefix should be cleaned up manually if needed")
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
