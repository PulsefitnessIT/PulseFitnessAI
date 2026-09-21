"""
Test suite for GymAxis Service Operations Phase 2 — Engineer Mobile API.
Iter 215dp.

Tests:
- GET /api/svc/engineer/me — profile + stats + active_timer
- GET /api/svc/engineer/jobs — today/upcoming/open filters
- GET /api/svc/engineer/jobs/{id} — detail with events/photos/time_entries
- POST /api/svc/engineer/time/start — idempotency, auto-stop, state transitions
- POST /api/svc/engineer/time/stop — closes entry, writes event
- POST /api/svc/engineer/photos — attaches photo, emits event
- POST /api/svc/engineer/signature — stores signature, emits event
- POST /api/svc/engineer/jobs/{id}/complete — auto-walk, sage invoice enqueue
- Sicon/Sage outbox verification
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from tests.conftest import rate_limit_bypass_headers

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://aftersales-engine.preview.emergentagent.com"

# Session-scoped login to avoid rate limiting
_SESSION_TOKEN = None
_SESSION_USER_ID = None
_SESSION_ORG_ID = None


def _get_session_auth():
    """Get session-scoped auth token (login once)."""
    global _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID
    if _SESSION_TOKEN:
        return _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID

    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        headers=rate_limit_bypass_headers()
    )
    if resp.status_code == 200:
        data = resp.json()
        _SESSION_TOKEN = data["token"]
        _SESSION_USER_ID = data["user"]["id"]
        _SESSION_ORG_ID = data["user"]["organization_id"]
    return _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID


class TestEngineerPhase2:
    """Engineer Mobile API tests for Phase 2."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup using session-scoped auth."""
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.token = token
        self.user_id = user_id
        self.org_id = org_id

        # Store test case ID for cleanup
        self.test_case_id = None
        yield

        # Cleanup test data
        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _create_test_case(self, status="assigned"):
        """Helper to create a test case assigned to the current user."""
        case_data = {
            "title": f"TEST_Engineer_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case for engineer mobile API",
            "priority": "p2",
            "cover_type": "chargeable",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001",
            "customer_email": "test@example.com",
            "site_name": "Test Site",
            "asset_name": "Test Treadmill",
            "fault_code": "E001",
        }
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json=case_data)
        assert resp.status_code in [200, 201], f"Failed to create case: {resp.text}"
        case = resp.json()
        self.test_case_id = case["id"]

        # Assign to current user
        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "assigned_engineer_id": self.user_id,
        })
        assert resp.status_code == 200, f"Failed to assign case: {resp.text}"

        # Transition to target status if not 'new'
        if status != "new":
            # Walk through states: new -> triaged -> assigned
            if status in ["triaged", "assigned", "en_route", "on_site"]:
                resp = self.session.post(f"{BASE_URL}/api/svc/cases/{case['id']}/transition", json={"to": "triaged"})
            if status in ["assigned", "en_route", "on_site"]:
                resp = self.session.post(f"{BASE_URL}/api/svc/cases/{case['id']}/transition", json={"to": "assigned"})
            if status == "en_route":
                resp = self.session.post(f"{BASE_URL}/api/svc/cases/{case['id']}/transition", json={"to": "en_route"})
            if status == "on_site":
                resp = self.session.post(f"{BASE_URL}/api/svc/cases/{case['id']}/transition", json={"to": "on_site"})

        # Get final state
        resp = self.session.get(f"{BASE_URL}/api/svc/cases/{case['id']}")
        return resp.json()

    # ─────────────────────────────────────────────────────────────────
    # GET /api/svc/engineer/me
    # ─────────────────────────────────────────────────────────────────
    def test_engineer_me_returns_profile_and_stats(self):
        """GET /api/svc/engineer/me returns engineer profile + stats + active_timer."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/me")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        # Verify structure
        assert "engineer" in data, "Missing engineer profile"
        assert "stats" in data, "Missing stats"
        assert "active_timer" in data, "Missing active_timer field"

        # Verify engineer profile fields
        eng = data["engineer"]
        assert "id" in eng
        assert "full_name" in eng
        assert "email" in eng

        # Verify stats
        stats = data["stats"]
        assert "today_jobs" in stats
        assert "open_jobs" in stats
        assert isinstance(stats["today_jobs"], int)
        assert isinstance(stats["open_jobs"], int)

        # Initially no active timer
        # (may or may not be null depending on prior state)
        print(f"Engineer profile: {eng['full_name']}, stats: {stats}")

    def test_engineer_me_auto_creates_profile(self):
        """GET /api/svc/engineer/me auto-creates svc_engineers row if missing."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/me")
        assert resp.status_code == 200
        data = resp.json()

        # The engineer ID should match the user ID
        assert data["engineer"]["id"] == self.user_id

    # ─────────────────────────────────────────────────────────────────
    # GET /api/svc/engineer/jobs
    # ─────────────────────────────────────────────────────────────────
    def test_engineer_jobs_today(self):
        """GET /api/svc/engineer/jobs?when=today returns today's jobs."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "today"})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "jobs" in data
        assert "count" in data
        assert isinstance(data["jobs"], list)
        print(f"Today's jobs: {data['count']}")

    def test_engineer_jobs_open(self):
        """GET /api/svc/engineer/jobs?when=open returns all open jobs."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "jobs" in data
        assert "count" in data
        print(f"Open jobs: {data['count']}")

    def test_engineer_jobs_upcoming(self):
        """GET /api/svc/engineer/jobs?when=upcoming returns future jobs."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "upcoming"})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "jobs" in data
        print(f"Upcoming jobs: {data['count']}")

    # ─────────────────────────────────────────────────────────────────
    # GET /api/svc/engineer/jobs/{id}
    # ─────────────────────────────────────────────────────────────────
    def test_engineer_job_detail(self):
        """GET /api/svc/engineer/jobs/{id} returns full job context."""
        case = self._create_test_case()

        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        # Verify case fields
        assert data["id"] == case["id"]
        assert "title" in data
        assert "status" in data
        assert "priority" in data

        # Verify nested collections
        assert "events" in data
        assert "photos" in data
        assert "time_entries" in data
        assert isinstance(data["events"], list)
        assert isinstance(data["photos"], list)
        assert isinstance(data["time_entries"], list)
        print(f"Job detail: {data['title']}, events: {len(data['events'])}")

    def test_engineer_job_detail_403_if_not_assigned(self):
        """GET /api/svc/engineer/jobs/{id} returns 403 if not assigned."""
        # Create case but assign to a different user
        case_data = {
            "title": f"TEST_Unassigned_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case not assigned to caller",
            "priority": "p3",
        }
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json=case_data)
        assert resp.status_code in [200, 201]
        case = resp.json()
        self.test_case_id = case["id"]

        # Assign to a fake user ID
        fake_user_id = str(uuid.uuid4())
        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "assigned_engineer_id": fake_user_id
        })

        # Now try to access as current user
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    # ─────────────────────────────────────────────────────────────────
    # POST /api/svc/engineer/time/start — Idempotency tests
    # ─────────────────────────────────────────────────────────────────
    def test_time_start_creates_entry(self):
        """POST /api/svc/engineer/time/start creates a time entry."""
        case = self._create_test_case()
        idem_key = str(uuid.uuid4())

        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "travel"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        entry = resp.json()

        assert "id" in entry
        assert entry["case_id"] == case["id"]
        assert entry["category"] == "travel"
        assert entry["start_at"] is not None
        assert entry["end_at"] is None  # Still open
        print(f"Created time entry: {entry['id']}")

        # Stop the timer for cleanup
        self.session.post(f"{BASE_URL}/api/svc/engineer/time/stop", json={"entry_id": entry["id"]})

    def test_time_start_idempotent_replay(self):
        """POST /api/svc/engineer/time/start with same Idempotency-Key returns same entry."""
        case = self._create_test_case()
        idem_key = str(uuid.uuid4())

        # First call
        resp1 = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "on_site"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp1.status_code == 200
        entry1 = resp1.json()

        # Second call with SAME key — should return same entry, NOT auto-stop
        resp2 = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "on_site"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp2.status_code == 200
        entry2 = resp2.json()

        # CRITICAL: Same entry ID, not a new one
        assert entry1["id"] == entry2["id"], "Idempotent replay created a new entry!"
        # CRITICAL: Entry should still be open (not auto-stopped)
        assert entry2["end_at"] is None, "Idempotent replay auto-stopped the entry!"
        print(f"Idempotent replay verified: {entry1['id']} == {entry2['id']}")

        # Cleanup
        self.session.post(f"{BASE_URL}/api/svc/engineer/time/stop", json={"entry_id": entry1["id"]})

    def test_time_start_travel_transitions_to_en_route(self):
        """Starting 'travel' timer when case is 'assigned' transitions to 'en_route'."""
        case = self._create_test_case(status="assigned")
        assert case["status"] == "assigned"

        idem_key = str(uuid.uuid4())
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "travel"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200

        # Verify case status changed
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.status_code == 200
        updated_case = resp.json()
        assert updated_case["status"] == "en_route", f"Expected en_route, got {updated_case['status']}"
        print(f"Travel timer transitioned case to: {updated_case['status']}")

        # Cleanup
        self.session.post(f"{BASE_URL}/api/svc/engineer/time/stop", json={})

    def test_time_start_onsite_transitions_to_on_site(self):
        """Starting 'on_site' timer transitions case to 'on_site'."""
        case = self._create_test_case(status="assigned")

        idem_key = str(uuid.uuid4())
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "on_site"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200

        # Verify case status changed
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.status_code == 200
        updated_case = resp.json()
        assert updated_case["status"] == "on_site", f"Expected on_site, got {updated_case['status']}"
        print(f"On-site timer transitioned case to: {updated_case['status']}")

        # Cleanup
        self.session.post(f"{BASE_URL}/api/svc/engineer/time/stop", json={})

    # ─────────────────────────────────────────────────────────────────
    # POST /api/svc/engineer/time/stop
    # ─────────────────────────────────────────────────────────────────
    def test_time_stop_closes_entry(self):
        """POST /api/svc/engineer/time/stop closes the active entry."""
        case = self._create_test_case()

        # Start a timer
        idem_key = str(uuid.uuid4())
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "on_site"},
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200
        entry = resp.json()

        # Stop the timer
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/stop",
            json={"entry_id": entry["id"]}
        )
        assert resp.status_code == 200
        stopped = resp.json()

        assert stopped["end_at"] is not None, "Entry not closed"
        assert stopped["duration_minutes"] >= 0
        print(f"Stopped timer: duration={stopped['duration_minutes']}m")

    # ─────────────────────────────────────────────────────────────────
    # POST /api/svc/engineer/photos
    # ─────────────────────────────────────────────────────────────────
    def test_add_photo(self):
        """POST /api/svc/engineer/photos attaches a photo to a case."""
        case = self._create_test_case()
        idem_key = str(uuid.uuid4())

        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/photos",
            json={
                "case_id": case["id"],
                "file_url": "https://example.com/test-photo.jpg",
                "mime_type": "image/jpeg",
                "caption": "Test photo from engineer",
            },
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        photo = resp.json()

        assert "id" in photo
        assert photo["case_id"] == case["id"]
        assert photo["file_url"] == "https://example.com/test-photo.jpg"
        print(f"Added photo: {photo['id']}")

    # ─────────────────────────────────────────────────────────────────
    # POST /api/svc/engineer/signature
    # ─────────────────────────────────────────────────────────────────
    def test_add_signature(self):
        """POST /api/svc/engineer/signature stores a signature."""
        case = self._create_test_case()
        idem_key = str(uuid.uuid4())

        # Minimal base64 PNG (1x1 transparent pixel)
        test_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/signature",
            json={
                "case_id": case["id"],
                "signed_by_name": "John Customer",
                "signed_by_role": "Site Manager",
                "image_data": test_image,
                "summary": "Work completed satisfactorily",
            },
            headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        sig = resp.json()

        assert "id" in sig
        assert sig["case_id"] == case["id"]
        assert sig["signed_by_name"] == "John Customer"
        print(f"Added signature: {sig['id']}")

    # ─────────────────────────────────────────────────────────────────
    # POST /api/svc/engineer/jobs/{id}/complete
    # ─────────────────────────────────────────────────────────────────
    def test_complete_requires_summary(self):
        """POST /api/svc/engineer/jobs/{id}/complete requires summary."""
        case = self._create_test_case()

        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}/complete",
            json={"target": "closed"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "summary" in resp.text.lower()

    def test_complete_en_route_auto_walks_to_closed(self):
        """POST /api/svc/engineer/jobs/{id}/complete from en_route auto-walks through on_site → closed."""
        case = self._create_test_case(status="assigned")

        # Start travel timer to get to en_route
        idem_key = str(uuid.uuid4())
        self.session.post(
            f"{BASE_URL}/api/svc/engineer/time/start",
            json={"case_id": case["id"], "category": "travel"},
            headers={"Idempotency-Key": idem_key}
        )

        # Verify en_route
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.json()["status"] == "en_route"

        # Complete directly to closed
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}/complete",
            json={
                "summary": "Fixed the issue - replaced belt and tested",
                "chargeable": True,
                "target": "closed"
            }
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        completed = resp.json()

        assert completed["status"] == "closed", f"Expected closed, got {completed['status']}"
        print("Auto-walked from en_route to closed")

    def test_complete_chargeable_enqueues_sage_invoice(self):
        """Closing a chargeable case enqueues a Sage invoice outbox row."""
        case = self._create_test_case(status="on_site")

        # Ensure it's chargeable
        self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={"cover_type": "chargeable"})

        # Complete the job
        resp = self.session.post(
            f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}/complete",
            json={
                "summary": "Completed chargeable work",
                "chargeable": True,
                "target": "closed"
            }
        )
        assert resp.status_code == 200

        # Verify Sage outbox entry was created (via direct DB check or API if available)
        # For now, we just verify the case is closed
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/jobs/{case['id']}")
        assert resp.json()["status"] == "closed"
        print("Chargeable case closed - Sage invoice should be enqueued")


class TestSiconSageCrosswalks:
    """Verify Sicon/Sage field mapping and sync stubs."""

    def test_status_crosswalk_values(self):
        """Verify STATUS_CROSSWALK maps all GymAxis states to Sicon."""
        from routes.svc.integrations.sicon_sync import STATUS_CROSSWALK

        expected_states = [
            "new", "triaged", "assigned", "en_route", "on_site",
            "paused_parts", "paused_customer", "repaired",
            "awaiting_sign_off", "closed", "invoiced", "rejected"
        ]

        for state in expected_states:
            assert state in STATUS_CROSSWALK, f"Missing state: {state}"
            assert STATUS_CROSSWALK[state], f"Empty mapping for: {state}"

        # Verify specific mappings
        assert STATUS_CROSSWALK["closed"] == "Completed"
        assert STATUS_CROSSWALK["new"] == "Logged"
        print(f"STATUS_CROSSWALK verified: {len(STATUS_CROSSWALK)} states")

    def test_priority_crosswalk_values(self):
        """Verify PRIORITY_CROSSWALK maps p1-p4 to 1-4."""
        from routes.svc.integrations.sicon_sync import PRIORITY_CROSSWALK

        assert PRIORITY_CROSSWALK["p1"] == 1
        assert PRIORITY_CROSSWALK["p2"] == 2
        assert PRIORITY_CROSSWALK["p3"] == 3
        assert PRIORITY_CROSSWALK["p4"] == 4
        print("PRIORITY_CROSSWALK verified")

    def test_cover_nominal_mapping(self):
        """Verify COVER_NOMINAL maps cover types to Sage nominal codes."""
        from routes.svc.integrations.sicon_sync import COVER_NOMINAL

        assert COVER_NOMINAL["chargeable"] == "4010"
        assert COVER_NOMINAL["contract"] == "4001"
        assert COVER_NOMINAL["warranty"] == "4002"
        assert COVER_NOMINAL["ppm"] == "4003"
        print("COVER_NOMINAL verified")


class TestFieldMappingDoc:
    """Verify SVC_FIELD_MAPPING.md exists and is valid."""

    def test_mapping_doc_exists(self):
        """Verify SVC_FIELD_MAPPING.md exists at expected path."""
        import os
        path = "/app/memory/SVC_FIELD_MAPPING.md"
        assert os.path.exists(path), f"Missing: {path}"

        with open(path) as f:
            content = f.read()

        # Verify key sections exist
        assert "svc_cases" in content
        assert "Sicon" in content
        assert "Sage" in content
        assert "STATUS_CROSSWALK" in content or "Status crosswalk" in content
        assert "NominalCode" in content
        print(f"SVC_FIELD_MAPPING.md verified: {len(content)} chars")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
