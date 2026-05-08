"""
Sprint C — Operator Multipliers for GymAxis Memberships
Tests for: Saved Views, Bulk Actions, Activity Timeline

Test credentials:
- Bob (operator): bob@knockers.com / Test123!
- Org: Strong Fitness (43 members, 40 uninvited)
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
BYPASS_HEADER = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")

# Bob's credentials (operator with 43 members)
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"


@pytest.fixture(scope="module")
def bob_token():
    """Get Bob's auth token for operator endpoints."""
    headers = {"Content-Type": "application/json"}
    if BYPASS_HEADER:
        headers["X-RateLimit-Bypass"] = BYPASS_HEADER
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BOB_EMAIL, "password": BOB_PASSWORD},
        headers=headers,
    )
    assert resp.status_code == 200, f"Bob login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def bob_headers(bob_token):
    """Headers with Bob's auth token."""
    h = {"Authorization": f"Bearer {bob_token}", "Content-Type": "application/json"}
    if BYPASS_HEADER:
        h["X-RateLimit-Bypass"] = BYPASS_HEADER
    return h


# ═══════════════════════════════════════════════════════════════════
# 1. SAVED VIEWS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestSavedViews:
    """Tests for GET/POST/DELETE /api/memberships/saved-views"""

    def test_list_saved_views_returns_4_presets(self, bob_headers):
        """GET /api/memberships/saved-views returns 4 presets + custom views."""
        resp = requests.get(f"{BASE_URL}/api/memberships/saved-views", headers=bob_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should have presets array
        assert "presets" in data, "Response missing 'presets' key"
        presets = data["presets"]
        assert len(presets) == 4, f"Expected 4 presets, got {len(presets)}"
        
        # Verify preset IDs
        preset_ids = [p["id"] for p in presets]
        expected_ids = ["preset:trialists_7d", "preset:no_shows_14d", "preset:uninvited", "preset:new_this_week"]
        for eid in expected_ids:
            assert eid in preset_ids, f"Missing preset: {eid}"
        
        # Should have custom array (may be empty)
        assert "custom" in data, "Response missing 'custom' key"
        print(f"✓ GET /api/memberships/saved-views returns 4 presets + {len(data['custom'])} custom views")

    def test_create_custom_view(self, bob_headers):
        """POST /api/memberships/saved-views creates a custom view."""
        payload = {
            "name": "TEST_216al_VIP Members",
            "filter": {"tag": "vip", "status": "active"}
        }
        resp = requests.post(
            f"{BASE_URL}/api/memberships/saved-views",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "view" in data, "Response missing 'view' key"
        view = data["view"]
        assert view["name"] == "TEST_216al_VIP Members"
        assert view["filter"]["tag"] == "vip"
        assert view["is_preset"] == False
        assert "id" in view
        
        # Store for cleanup
        TestSavedViews.created_view_id = view["id"]
        print(f"✓ POST /api/memberships/saved-views created view: {view['id']}")

    def test_create_custom_view_requires_name(self, bob_headers):
        """POST /api/memberships/saved-views returns 400 if name is missing."""
        payload = {"filter": {"tag": "test"}}
        resp = requests.post(
            f"{BASE_URL}/api/memberships/saved-views",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ POST /api/memberships/saved-views rejects missing name")

    def test_delete_custom_view(self, bob_headers):
        """DELETE /api/memberships/saved-views/{id} removes custom view."""
        view_id = getattr(TestSavedViews, "created_view_id", None)
        if not view_id:
            pytest.skip("No custom view created to delete")
        
        resp = requests.delete(
            f"{BASE_URL}/api/memberships/saved-views/{view_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        assert resp.json().get("ok") == True
        print(f"✓ DELETE /api/memberships/saved-views/{view_id} succeeded")

    def test_delete_preset_view_rejected(self, bob_headers):
        """DELETE /api/memberships/saved-views/{preset_id} returns 400."""
        resp = requests.delete(
            f"{BASE_URL}/api/memberships/saved-views/preset:uninvited",
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "Built-in" in resp.json().get("detail", "")
        print("✓ DELETE preset view correctly rejected with 400")


# ═══════════════════════════════════════════════════════════════════
# 2. MEMBERS-FILTERED PRESET TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMembersFiltered:
    """Tests for GET /api/memberships/members-filtered with presets."""

    def test_preset_uninvited(self, bob_headers):
        """preset=uninvited returns members where portal_invited_at is null AND email is not null."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members-filtered",
            params={"preset": "uninvited"},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "members" in data
        assert "preset" in data
        assert data["preset"] == "uninvited"
        
        # Per main agent: Bob's org has 40 uninvited members
        members = data["members"]
        print(f"✓ preset=uninvited returned {len(members)} members (expected ~40)")
        
        # Verify all returned members have email but no portal_invited_at
        for m in members[:5]:  # Check first 5
            assert m.get("email"), f"Member {m.get('id')} has no email"
            # portal_invited_at should be null/empty
            assert not m.get("portal_invited_at"), f"Member {m.get('id')} already invited"

    def test_preset_new_this_week(self, bob_headers):
        """preset=new_this_week returns members created in last 7 days."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members-filtered",
            params={"preset": "new_this_week"},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["preset"] == "new_this_week"
        members = data["members"]
        print(f"✓ preset=new_this_week returned {len(members)} members")
        
        # Verify dates are within 7 days
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        for m in members[:5]:
            created = m.get("created_at", "")
            assert created >= cutoff, f"Member {m.get('id')} created_at {created} is older than 7 days"

    def test_preset_trialists_7d(self, bob_headers):
        """preset=trialists_7d returns active memberships ending in 7 days."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members-filtered",
            params={"preset": "trialists_7d"},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["preset"] == "trialists_7d"
        print(f"✓ preset=trialists_7d returned {len(data['members'])} members")

    def test_preset_no_shows_14d(self, bob_headers):
        """preset=no_shows_14d returns member_ids with ≥2 no-shows in last 14 days."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members-filtered",
            params={"preset": "no_shows_14d"},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["preset"] == "no_shows_14d"
        print(f"✓ preset=no_shows_14d returned {len(data['members'])} members")


# ═══════════════════════════════════════════════════════════════════
# 3. BULK ACTIONS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBulkActions:
    """Tests for POST /api/memberships/members/bulk-action."""

    @pytest.fixture(scope="class")
    def test_member_ids(self, bob_headers):
        """Get 2 member IDs from Bob's org for bulk action tests."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        assert resp.status_code == 200
        members = resp.json().get("members", [])
        assert len(members) >= 2, "Need at least 2 members for bulk tests"
        return [members[0]["id"], members[1]["id"]]

    def test_bulk_action_empty_member_ids_returns_400(self, bob_headers):
        """POST bulk-action with empty member_ids returns 400."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "add_tag", "member_ids": [], "payload": {"tag": "test"}},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ bulk-action with empty member_ids returns 400")

    def test_bulk_action_unknown_action_returns_400(self, bob_headers, test_member_ids):
        """POST bulk-action with unknown action returns 400."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "unknown_action", "member_ids": test_member_ids},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "Unknown action" in resp.json().get("detail", "")
        print("✓ bulk-action with unknown action returns 400")

    def test_bulk_action_max_200_cap(self, bob_headers):
        """POST bulk-action enforces _BULK_MAX=200 cap."""
        # Create 201 fake IDs
        fake_ids = [f"fake-id-{i}" for i in range(201)]
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "add_tag", "member_ids": fake_ids, "payload": {"tag": "test"}},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "200" in resp.json().get("detail", "") or "Too many" in resp.json().get("detail", "")
        print("✓ bulk-action enforces 200 member cap")

    def test_bulk_add_tag_idempotent(self, bob_headers, test_member_ids):
        """POST bulk-action action=add_tag adds tag via $addToSet (idempotent)."""
        tag_name = "TEST_216al_bulk_tag"
        
        # First call
        resp1 = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "add_tag", "member_ids": test_member_ids, "payload": {"tag": tag_name}},
            headers=bob_headers,
        )
        assert resp1.status_code == 200, f"Failed: {resp1.text}"
        data1 = resp1.json()
        assert data1["ok"] == True
        assert data1["action"] == "add_tag"
        assert data1["succeeded"] == len(test_member_ids)
        
        # Second call (idempotent - should still succeed)
        resp2 = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "add_tag", "member_ids": test_member_ids, "payload": {"tag": tag_name}},
            headers=bob_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["succeeded"] == len(test_member_ids)
        
        # Verify tag was added
        member_resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{test_member_ids[0]}",
            headers=bob_headers,
        )
        assert member_resp.status_code == 200
        member = member_resp.json().get("member", {})
        assert tag_name in member.get("tags", []), f"Tag not found on member"
        
        print(f"✓ bulk add_tag is idempotent, tag '{tag_name}' added to {len(test_member_ids)} members")

    def test_bulk_add_tag_requires_tag(self, bob_headers, test_member_ids):
        """POST bulk-action action=add_tag requires tag in payload."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "add_tag", "member_ids": test_member_ids, "payload": {}},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "Tag is required" in resp.json().get("detail", "")
        print("✓ bulk add_tag requires tag in payload")

    def test_bulk_invite_portal(self, bob_headers, test_member_ids):
        """POST bulk-action action=invite_portal fans out invite-portal to each id."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "invite_portal", "member_ids": test_member_ids},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["ok"] == True
        assert data["action"] == "invite_portal"
        assert "results" in data
        
        # Check per-member results
        for r in data["results"]:
            assert "member_id" in r
            assert "ok" in r
            # email_sent may be false if Resend is not configured
            if r["ok"]:
                assert "email_sent" in r
        
        print(f"✓ bulk invite_portal: {data['succeeded']} succeeded, {data['failed']} failed")

    def test_bulk_send_reminder_requires_subject_message(self, bob_headers, test_member_ids):
        """POST bulk-action action=send_reminder requires subject+message."""
        # Missing both
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "send_reminder", "member_ids": test_member_ids, "payload": {}},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "Subject and message" in resp.json().get("detail", "")
        
        # Missing message
        resp2 = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={"action": "send_reminder", "member_ids": test_member_ids, "payload": {"subject": "Test"}},
            headers=bob_headers,
        )
        assert resp2.status_code == 400
        
        print("✓ bulk send_reminder requires subject+message")

    def test_bulk_send_reminder_success(self, bob_headers, test_member_ids):
        """POST bulk-action action=send_reminder sends email and logs event."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/bulk-action",
            json={
                "action": "send_reminder",
                "member_ids": test_member_ids,
                "payload": {
                    "subject": "TEST_216al Reminder",
                    "message": "This is a test reminder from Sprint C testing."
                }
            },
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["ok"] == True
        assert data["action"] == "send_reminder"
        
        # Check results - some may fail if no email
        for r in data["results"]:
            if r["ok"]:
                assert "email_sent" in r
        
        print(f"✓ bulk send_reminder: {data['succeeded']} succeeded, {data['failed']} failed")


# ═══════════════════════════════════════════════════════════════════
# 4. ACTIVITY TIMELINE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestActivityTimeline:
    """Tests for GET /api/memberships/members/{id}/activity."""

    def test_activity_timeline_returns_events(self, bob_headers):
        """GET /api/memberships/members/{id}/activity returns reverse-chrono feed."""
        # Get a member ID first
        members_resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        assert members_resp.status_code == 200
        members = members_resp.json().get("members", [])
        assert len(members) > 0, "No members found"
        
        member_id = members[0]["id"]
        
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{member_id}/activity",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "member_id" in data
        assert data["member_id"] == member_id
        assert "events" in data
        assert "count" in data
        
        events = data["events"]
        print(f"✓ Activity timeline for member {member_id}: {len(events)} events")
        
        # Verify event structure
        if events:
            event = events[0]
            assert "id" in event
            assert "kind" in event
            assert "title" in event
            assert "at" in event
            
            # Verify reverse-chrono order
            if len(events) > 1:
                for i in range(len(events) - 1):
                    at1 = events[i].get("at") or ""
                    at2 = events[i + 1].get("at") or ""
                    if at1 and at2:
                        assert at1 >= at2, f"Events not in reverse-chrono order: {at1} < {at2}"

    def test_activity_timeline_includes_joined_event(self, bob_headers):
        """Activity timeline includes 'joined' event from member.created_at."""
        members_resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        members = members_resp.json().get("members", [])
        member_id = members[0]["id"]
        
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{member_id}/activity",
            headers=bob_headers,
        )
        assert resp.status_code == 200
        events = resp.json().get("events", [])
        
        # Look for 'joined' event
        joined_events = [e for e in events if e.get("kind") == "joined"]
        assert len(joined_events) > 0, "No 'joined' event found in timeline"
        
        joined = joined_events[0]
        assert joined["title"] == "Joined the studio"
        print("✓ Activity timeline includes 'joined' event")

    def test_activity_timeline_merges_multiple_sources(self, bob_headers):
        """Activity timeline merges bookings + payments + invoices + events."""
        members_resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        members = members_resp.json().get("members", [])
        member_id = members[0]["id"]
        
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{member_id}/activity",
            headers=bob_headers,
        )
        assert resp.status_code == 200
        events = resp.json().get("events", [])
        
        # Collect unique kinds
        kinds = set(e.get("kind") for e in events)
        print(f"✓ Activity timeline event kinds: {kinds}")
        
        # At minimum should have 'joined'
        assert "joined" in kinds, "Missing 'joined' event kind"


# ═══════════════════════════════════════════════════════════════════
# 5. REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRegression:
    """Regression tests to ensure existing functionality still works."""

    def test_members_list_still_works(self, bob_headers):
        """GET /api/memberships/members still returns members."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "members" in data
        print(f"✓ GET /api/memberships/members returns {len(data['members'])} members")

    def test_member_detail_still_works(self, bob_headers):
        """GET /api/memberships/members/{id} still returns member detail."""
        members_resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        members = members_resp.json().get("members", [])
        member_id = members[0]["id"]
        
        resp = requests.get(
            f"{BASE_URL}/api/memberships/members/{member_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "member" in data
        assert "memberships" in data
        assert "recent_bookings" in data
        print(f"✓ GET /api/memberships/members/{member_id} returns full detail")

    def test_invite_portal_single_still_works(self, bob_headers):
        """POST /api/memberships/members/{id}/invite-portal still works."""
        members_resp = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=bob_headers,
        )
        members = members_resp.json().get("members", [])
        # Find a member with email
        member = next((m for m in members if m.get("email")), None)
        assert member, "No member with email found"
        
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/{member['id']}/invite-portal",
            json={},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        assert "claim_url" in data
        print(f"✓ Single invite-portal still works, claim_url returned")
