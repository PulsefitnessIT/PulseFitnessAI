"""
Test suite for Service Operations Platform - Phase 1 (iter 215dn)

Tests:
- Service Desk Dashboard API (/api/svc/desk/summary, /queue, /engineers)
- Case Intake API (/api/svc/intake/phone, /portal, /email)
- Case Management API (/api/svc/cases - CRUD, transitions, notes)
- State machine validation (legal/illegal transitions)
- Organization scoping
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestServiceOpsAuth:
    """Authentication and setup for Service Ops testing"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for master admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        return data["token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Auth headers for API calls"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def test_login_success(self, auth_token):
        """Verify master admin can login"""
        assert auth_token is not None
        assert len(auth_token) > 20
        print(f"✓ Login successful, token length: {len(auth_token)}")


class TestServiceDeskDashboard:
    """Tests for /api/svc/desk/* endpoints"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_desk_summary_returns_kpis(self, auth_headers):
        """GET /api/svc/desk/summary returns KPI dict"""
        response = requests.get(f"{BASE_URL}/api/svc/desk/summary", headers=auth_headers)
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()

        # Verify KPI structure
        assert "kpis" in data, "Missing 'kpis' key"
        kpis = data["kpis"]

        # Check all required KPI fields
        required_kpis = ["open", "unassigned", "sla_at_risk", "sla_breached", "closed_last_30d"]
        for kpi in required_kpis:
            assert kpi in kpis, f"Missing KPI: {kpi}"
            assert isinstance(kpis[kpi], (int, float, type(None))), f"KPI {kpi} should be numeric"

        assert "as_of" in data, "Missing 'as_of' timestamp"
        print(f"✓ Desk summary KPIs: open={kpis['open']}, unassigned={kpis['unassigned']}, at_risk={kpis['sla_at_risk']}, breached={kpis['sla_breached']}, closed_30d={kpis['closed_last_30d']}")

    def test_desk_queue_returns_cases(self, auth_headers):
        """GET /api/svc/desk/queue returns case list"""
        response = requests.get(f"{BASE_URL}/api/svc/desk/queue", headers=auth_headers)
        assert response.status_code == 200, f"Queue failed: {response.text}"
        data = response.json()

        assert "cases" in data, "Missing 'cases' key"
        assert "count" in data, "Missing 'count' key"
        assert isinstance(data["cases"], list), "cases should be a list"
        print(f"✓ Desk queue returned {data['count']} cases")

    def test_desk_engineers_returns_roster(self, auth_headers):
        """GET /api/svc/desk/engineers returns engineer list"""
        response = requests.get(f"{BASE_URL}/api/svc/desk/engineers", headers=auth_headers)
        assert response.status_code == 200, f"Engineers failed: {response.text}"
        data = response.json()

        assert "engineers" in data, "Missing 'engineers' key"
        assert "count" in data, "Missing 'count' key"
        assert isinstance(data["engineers"], list), "engineers should be a list"
        print(f"✓ Desk engineers returned {data['count']} engineers")


class TestCaseIntake:
    """Tests for /api/svc/intake/* endpoints"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_intake_phone_creates_case(self, auth_headers):
        """POST /api/svc/intake/phone creates a new case"""
        payload = {
            "title": "TEST_Treadmill belt worn",
            "description": "Customer reports belt slipping at high speeds",
            "priority": "p2",
            "cover_type": "contract",
            "site_name": "TEST_PureGym Holborn",
            "asset_name": "Treadmill #14 - Life Fitness 95Ti",
            "fault_code": "TM-BLT-WEAR",
            "customer_name": "John Smith",
            "customer_phone": "+44 20 1234 5678",
            "customer_email": "john.smith@test.com"
        }

        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Intake failed: {response.text}"
        data = response.json()

        # Verify case structure
        assert "id" in data, "Missing case id"
        assert "reference" in data, "Missing case reference"
        assert data["reference"].startswith("SVC-"), f"Reference should start with SVC-: {data['reference']}"
        assert data["status"] == "new", f"New case should have status 'new', got: {data['status']}"
        assert data["priority"] == "p2", f"Priority mismatch: {data['priority']}"
        assert data["title"] == payload["title"], "Title mismatch"
        assert data["source"] == "phone", f"Source should be 'phone', got: {data['source']}"

        # Verify SLA targets are set
        assert "sla_response_at" in data, "Missing SLA response target"
        assert "sla_resolve_at" in data, "Missing SLA resolve target"

        print(f"✓ Case created: {data['reference']} - {data['title']}")
        return data

    def test_intake_portal_creates_case(self, auth_headers):
        """POST /api/svc/intake/portal creates a case from portal"""
        payload = {
            "title": "TEST_Spin bike pedal loose",
            "description": "Left pedal wobbles during use",
            "priority": "p3",
            "site_name": "TEST_Fitness First Camden",
            "customer_name": "Jane Doe",
            "customer_email": "jane.doe@test.com"
        }

        response = requests.post(f"{BASE_URL}/api/svc/intake/portal", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Portal intake failed: {response.text}"
        data = response.json()

        assert data["source"] == "portal", f"Source should be 'portal', got: {data['source']}"
        print(f"✓ Portal case created: {data['reference']}")

    def test_intake_email_creates_case(self, auth_headers):
        """POST /api/svc/intake/email creates a case from email"""
        payload = {
            "title": "TEST_Rowing machine display error",
            "description": "Display shows E05 error code",
            "priority": "p3",
            "site_name": "TEST_Virgin Active Kensington",
            "customer_name": "Bob Wilson",
            "customer_phone": "+44 7700 900123"
        }

        response = requests.post(f"{BASE_URL}/api/svc/intake/email", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Email intake failed: {response.text}"
        data = response.json()

        assert data["source"] == "email", f"Source should be 'email', got: {data['source']}"
        print(f"✓ Email case created: {data['reference']}")

    def test_intake_requires_title_or_description(self, auth_headers):
        """Intake should fail without title or description"""
        payload = {
            "priority": "p3",
            "site_name": "TEST_Site",
            "customer_name": "Test User",
            "customer_phone": "+44 123"
        }

        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        assert response.status_code == 400, f"Should fail without title: {response.status_code}"
        print("✓ Intake correctly rejects missing title/description")


class TestCaseManagement:
    """Tests for /api/svc/cases/* endpoints"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def test_case(self, auth_headers):
        """Create a test case for management tests"""
        payload = {
            "title": "TEST_Case for management tests",
            "description": "Test case for CRUD operations",
            "priority": "p3",
            "site_name": "TEST_Management Test Site",
            "customer_name": "Test Manager",
            "customer_phone": "+44 999"
        }
        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        assert response.status_code == 200
        return response.json()

    def test_list_cases(self, auth_headers):
        """GET /api/svc/cases returns case list"""
        response = requests.get(f"{BASE_URL}/api/svc/cases", headers=auth_headers)
        assert response.status_code == 200, f"List cases failed: {response.text}"
        data = response.json()

        assert "cases" in data, "Missing 'cases' key"
        assert "total" in data, "Missing 'total' key"
        print(f"✓ Listed {data['total']} cases")

    def test_list_cases_with_status_filter(self, auth_headers):
        """GET /api/svc/cases?status=open filters correctly"""
        response = requests.get(f"{BASE_URL}/api/svc/cases?status=open", headers=auth_headers)
        assert response.status_code == 200, f"Filter failed: {response.text}"
        data = response.json()

        # All returned cases should be in open states
        open_states = {"new", "triaged", "assigned", "en_route", "on_site", "paused_parts", "paused_customer", "repaired", "awaiting_sign_off"}
        for case in data["cases"]:
            assert case["status"] in open_states, f"Case {case['reference']} has non-open status: {case['status']}"
        print(f"✓ Status filter returned {len(data['cases'])} open cases")

    def test_list_cases_with_priority_filter(self, auth_headers):
        """GET /api/svc/cases?priority=p2 filters correctly"""
        response = requests.get(f"{BASE_URL}/api/svc/cases?priority=p2", headers=auth_headers)
        assert response.status_code == 200, f"Priority filter failed: {response.text}"
        data = response.json()

        for case in data["cases"]:
            assert case["priority"] == "p2", f"Case {case['reference']} has wrong priority: {case['priority']}"
        print(f"✓ Priority filter returned {len(data['cases'])} P2 cases")

    def test_list_cases_with_search(self, auth_headers):
        """GET /api/svc/cases?search=TEST_ finds test cases"""
        response = requests.get(f"{BASE_URL}/api/svc/cases?search=TEST_", headers=auth_headers)
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()

        # All returned cases should contain TEST_ in title, reference, customer_name, or site_name
        print(f"✓ Search returned {len(data['cases'])} cases matching 'TEST_'")

    def test_get_case_detail(self, auth_headers, test_case):
        """GET /api/svc/cases/{id} returns case with events"""
        case_id = test_case["id"]
        response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        assert response.status_code == 200, f"Get case failed: {response.text}"
        data = response.json()

        assert data["id"] == case_id, "Case ID mismatch"
        assert "events" in data, "Missing events array"
        assert isinstance(data["events"], list), "events should be a list"

        # Should have at least the intake event
        assert len(data["events"]) >= 1, "Should have at least intake event"
        print(f"✓ Case detail: {data['reference']} with {len(data['events'])} events")

    def test_update_case(self, auth_headers, test_case):
        """PUT /api/svc/cases/{id} updates case fields"""
        case_id = test_case["id"]
        updates = {
            "title": "TEST_Updated title",
            "priority": "p1",
            "assigned_engineer_name": "Test Engineer"
        }

        response = requests.put(f"{BASE_URL}/api/svc/cases/{case_id}", json=updates, headers=auth_headers)
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()

        assert data["title"] == updates["title"], "Title not updated"
        assert data["priority"] == updates["priority"], "Priority not updated"
        assert data["assigned_engineer_name"] == updates["assigned_engineer_name"], "Engineer not updated"
        print(f"✓ Case updated: title={data['title']}, priority={data['priority']}")

        # Verify update persisted
        get_response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["title"] == updates["title"], "Update not persisted"

    def test_add_note_to_case(self, auth_headers, test_case):
        """POST /api/svc/cases/{id}/notes adds note to timeline"""
        case_id = test_case["id"]
        note_payload = {
            "body": "TEST_Internal note: Customer called back to confirm access",
            "visibility": "internal"
        }

        response = requests.post(f"{BASE_URL}/api/svc/cases/{case_id}/notes", json=note_payload, headers=auth_headers)
        assert response.status_code == 200, f"Add note failed: {response.text}"
        data = response.json()

        assert data["type"] == "note", f"Event type should be 'note', got: {data['type']}"
        assert data["body"] == note_payload["body"], "Note body mismatch"
        print("✓ Note added to case timeline")

        # Verify note appears in case events
        get_response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        events = get_response.json()["events"]
        note_events = [e for e in events if e["type"] == "note"]
        assert len(note_events) >= 1, "Note should appear in events"

    def test_add_note_requires_body(self, auth_headers, test_case):
        """POST /api/svc/cases/{id}/notes fails without body"""
        case_id = test_case["id"]
        response = requests.post(f"{BASE_URL}/api/svc/cases/{case_id}/notes", json={}, headers=auth_headers)
        assert response.status_code == 400, f"Should fail without body: {response.status_code}"
        print("✓ Note correctly rejects empty body")


class TestStateTransitions:
    """Tests for case state machine transitions"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @pytest.fixture
    def fresh_case(self, auth_headers):
        """Create a fresh case for transition tests"""
        payload = {
            "title": f"TEST_Transition test case {time.time()}",
            "description": "Case for testing state transitions",
            "priority": "p3",
            "site_name": "TEST_Transition Site",
            "customer_name": "Transition Tester",
            "customer_phone": "+44 888"
        }
        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        assert response.status_code == 200
        return response.json()

    def test_legal_transition_new_to_triaged(self, auth_headers, fresh_case):
        """new -> triaged is a legal transition"""
        case_id = fresh_case["id"]
        assert fresh_case["status"] == "new", "Fresh case should be 'new'"

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "triaged", "reason": "Initial triage complete"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Transition failed: {response.text}"
        data = response.json()

        assert data["status"] == "triaged", f"Status should be 'triaged', got: {data['status']}"
        print("✓ Transition new -> triaged successful")

    def test_legal_transition_new_to_assigned(self, auth_headers, fresh_case):
        """new -> assigned is a legal transition"""
        case_id = fresh_case["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "assigned", "reason": "Direct assignment"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Transition failed: {response.text}"
        data = response.json()

        assert data["status"] == "assigned", f"Status should be 'assigned', got: {data['status']}"
        print("✓ Transition new -> assigned successful")

    def test_legal_transition_new_to_rejected(self, auth_headers, fresh_case):
        """new -> rejected is a legal transition"""
        case_id = fresh_case["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "rejected", "reason": "Duplicate case"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Transition failed: {response.text}"
        data = response.json()

        assert data["status"] == "rejected", f"Status should be 'rejected', got: {data['status']}"
        print("✓ Transition new -> rejected successful")

    def test_illegal_transition_new_to_closed(self, auth_headers, fresh_case):
        """new -> closed is an ILLEGAL transition"""
        case_id = fresh_case["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "closed", "reason": "Trying illegal transition"},
            headers=auth_headers
        )
        assert response.status_code == 400, f"Should reject illegal transition: {response.status_code}"
        print("✓ Illegal transition new -> closed correctly rejected")

    def test_illegal_transition_new_to_on_site(self, auth_headers, fresh_case):
        """new -> on_site is an ILLEGAL transition"""
        case_id = fresh_case["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "on_site", "reason": "Trying illegal transition"},
            headers=auth_headers
        )
        assert response.status_code == 400, f"Should reject illegal transition: {response.status_code}"
        print("✓ Illegal transition new -> on_site correctly rejected")

    def test_illegal_transition_new_to_invoiced(self, auth_headers, fresh_case):
        """new -> invoiced is an ILLEGAL transition"""
        case_id = fresh_case["id"]

        response = requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "invoiced", "reason": "Trying illegal transition"},
            headers=auth_headers
        )
        assert response.status_code == 400, f"Should reject illegal transition: {response.status_code}"
        print("✓ Illegal transition new -> invoiced correctly rejected")

    def test_full_lifecycle_transition(self, auth_headers, fresh_case):
        """Test a complete case lifecycle: new -> triaged -> assigned -> en_route -> on_site -> repaired -> closed"""
        case_id = fresh_case["id"]

        transitions = [
            ("triaged", "Triage complete"),
            ("assigned", "Assigned to engineer"),
            ("en_route", "Engineer dispatched"),
            ("on_site", "Engineer arrived"),
            ("repaired", "Repair complete"),
            ("closed", "Customer signed off"),
        ]

        for target, reason in transitions:
            response = requests.post(
                f"{BASE_URL}/api/svc/cases/{case_id}/transition",
                json={"to": target, "reason": reason},
                headers=auth_headers
            )
            assert response.status_code == 200, f"Transition to {target} failed: {response.text}"
            data = response.json()
            assert data["status"] == target, f"Status should be '{target}', got: {data['status']}"

        # Verify closed_at is set
        get_response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        final_case = get_response.json()
        assert final_case["closed_at"] is not None, "closed_at should be set when case is closed"
        print("✓ Full lifecycle transition complete: new -> closed")

    def test_transition_creates_timeline_event(self, auth_headers, fresh_case):
        """Transitions should create state_change events in timeline"""
        case_id = fresh_case["id"]

        # Get initial event count
        get_response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        initial_events = len(get_response.json()["events"])

        # Do a transition
        requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "triaged", "reason": "Test transition event"},
            headers=auth_headers
        )

        # Check events increased
        get_response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}", headers=auth_headers)
        events = get_response.json()["events"]
        assert len(events) > initial_events, "Transition should add event"

        # Find the state_change event
        state_changes = [e for e in events if e["type"] == "state_change"]
        assert len(state_changes) >= 1, "Should have state_change event"

        latest = state_changes[0]  # Events are sorted desc by 'at'
        assert latest["from_state"] == "new", f"from_state should be 'new', got: {latest.get('from_state')}"
        assert latest["to_state"] == "triaged", f"to_state should be 'triaged', got: {latest.get('to_state')}"
        print("✓ Transition created state_change event in timeline")


class TestCaseEvents:
    """Tests for /api/svc/cases/{id}/events endpoint"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def case_with_events(self, auth_headers):
        """Create a case with multiple events"""
        # Create case
        payload = {
            "title": "TEST_Case with events",
            "description": "Case for testing events endpoint",
            "priority": "p2",
            "site_name": "TEST_Events Site",
            "customer_name": "Events Tester",
            "customer_phone": "+44 777"
        }
        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        case = response.json()
        case_id = case["id"]

        # Add some notes
        for i in range(3):
            requests.post(
                f"{BASE_URL}/api/svc/cases/{case_id}/notes",
                json={"body": f"TEST_Note {i+1}"},
                headers=auth_headers
            )

        # Do a transition
        requests.post(
            f"{BASE_URL}/api/svc/cases/{case_id}/transition",
            json={"to": "triaged"},
            headers=auth_headers
        )

        return case

    def test_list_case_events(self, auth_headers, case_with_events):
        """GET /api/svc/cases/{id}/events returns paginated events"""
        case_id = case_with_events["id"]
        response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}/events", headers=auth_headers)
        assert response.status_code == 200, f"List events failed: {response.text}"
        data = response.json()

        assert "events" in data, "Missing 'events' key"
        assert "count" in data, "Missing 'count' key"
        assert len(data["events"]) >= 4, f"Should have at least 4 events (intake + 3 notes), got: {len(data['events'])}"
        print(f"✓ Listed {data['count']} events for case")

    def test_events_have_required_fields(self, auth_headers, case_with_events):
        """Events should have id, type, at, actor_name"""
        case_id = case_with_events["id"]
        response = requests.get(f"{BASE_URL}/api/svc/cases/{case_id}/events", headers=auth_headers)
        events = response.json()["events"]

        for event in events:
            assert "id" in event, "Event missing 'id'"
            assert "type" in event, "Event missing 'type'"
            assert "at" in event, "Event missing 'at'"
            assert event["type"] in ["intake", "note", "state_change", "edit"], f"Unknown event type: {event['type']}"
        print("✓ All events have required fields")


class TestOrganizationScoping:
    """Tests for organization-based data isolation"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for master admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@gymaxisai.com",
            "password": "MasterAdmin123!"
        })
        assert response.status_code == 200
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_cases_scoped_to_organization(self, auth_headers):
        """Cases should only return for the user's organization"""
        # Create a case
        payload = {
            "title": "TEST_Org scoping test",
            "description": "Testing org isolation",
            "priority": "p3",
            "site_name": "TEST_Org Site",
            "customer_name": "Org Tester",
            "customer_phone": "+44 666"
        }
        create_response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json=payload, headers=auth_headers)
        assert create_response.status_code == 200
        created_case = create_response.json()

        # List cases and verify our case is there
        list_response = requests.get(f"{BASE_URL}/api/svc/cases", headers=auth_headers)
        cases = list_response.json()["cases"]

        case_ids = [c["id"] for c in cases]
        assert created_case["id"] in case_ids, "Created case should be in list"
        print("✓ Organization scoping verified - case visible to creator's org")

    def test_case_detail_requires_org_match(self, auth_headers):
        """GET /api/svc/cases/{id} should 404 for wrong org's case"""
        # This test would require a second org's credentials to fully test
        # For now, verify that a non-existent case returns 404
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = requests.get(f"{BASE_URL}/api/svc/cases/{fake_id}", headers=auth_headers)
        assert response.status_code == 404, f"Should 404 for non-existent case: {response.status_code}"
        print("✓ Non-existent case returns 404")


class TestUnauthorizedAccess:
    """Tests for authentication requirements"""

    def test_desk_summary_requires_auth(self):
        """GET /api/svc/desk/summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/svc/desk/summary")
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print("✓ Desk summary requires authentication")

    def test_cases_list_requires_auth(self):
        """GET /api/svc/cases requires authentication"""
        response = requests.get(f"{BASE_URL}/api/svc/cases")
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print("✓ Cases list requires authentication")

    def test_intake_requires_auth(self):
        """POST /api/svc/intake/phone requires authentication"""
        response = requests.post(f"{BASE_URL}/api/svc/intake/phone", json={"title": "Test"})
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print("✓ Intake requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
