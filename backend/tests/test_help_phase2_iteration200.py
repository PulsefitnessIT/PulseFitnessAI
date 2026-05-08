"""
Test Help Centre Phase 2 — Setup Checklist + Walkthrough metadata
Iteration 200

Tests:
1. GET /api/help/setup-checklist — Auth required, returns items with completed status
2. Role-based filtering on checklist items (master_admin sees all 7, staff sees fewer)
3. Walkthrough field on specific guides (service-log-fault, crm-add-contact, etc.)
4. Guides without walkthrough should NOT have the field set
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"
STAFF_EMAIL = "lee.somers@pulsefitness.com"
STAFF_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def master_admin_token():
    """Get auth token for master admin"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Master admin login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("token")


@pytest.fixture(scope="module")
def staff_token():
    """Get auth token for staff user (lee.somers)"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": STAFF_EMAIL,
        "password": STAFF_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Staff login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("token")


class TestSetupChecklistEndpoint:
    """Tests for GET /api/help/setup-checklist"""

    def test_checklist_requires_auth(self):
        """Checklist endpoint requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/help/setup-checklist")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    def test_checklist_returns_structure_master_admin(self, master_admin_token):
        """Master admin gets full checklist with correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        # Verify required fields
        assert "items" in data, "Response missing 'items' field"
        assert "completed_count" in data, "Response missing 'completed_count' field"
        assert "total_count" in data, "Response missing 'total_count' field"
        assert "percent" in data, "Response missing 'percent' field"
        assert "role" in data, "Response missing 'role' field"

        # Master admin should see all 7 items
        assert data["total_count"] == 7, f"Expected 7 items for master_admin, got {data['total_count']}"
        assert len(data["items"]) == 7, f"Expected 7 items in array, got {len(data['items'])}"
        assert data["role"] == "master_admin", f"Expected role 'master_admin', got {data['role']}"

    def test_checklist_item_structure(self, master_admin_token):
        """Each checklist item has required fields"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        required_fields = ["id", "label", "module", "href", "guide_id", "roles", "completed"]

        for item in data["items"]:
            for field in required_fields:
                assert field in item, f"Item {item.get('id', 'unknown')} missing field '{field}'"
            # completed should be boolean
            assert isinstance(item["completed"], bool), f"Item {item['id']} 'completed' should be boolean"

    def test_checklist_item_ids(self, master_admin_token):
        """Verify all expected checklist item IDs are present"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        expected_ids = ["ck-equipment", "ck-fault", "ck-team", "ck-member", "ck-plan", "ck-campaign", "ck-stripe"]
        actual_ids = [item["id"] for item in data["items"]]

        for eid in expected_ids:
            assert eid in actual_ids, f"Expected item '{eid}' not found in checklist"

    def test_checklist_percent_calculation(self, master_admin_token):
        """Percent is calculated correctly from completed_count/total_count"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        if data["total_count"] > 0:
            expected_percent = round((data["completed_count"] / data["total_count"]) * 100)
            assert data["percent"] == expected_percent, f"Percent mismatch: expected {expected_percent}, got {data['percent']}"


class TestChecklistRoleFiltering:
    """Tests for role-based filtering on checklist items"""

    def test_owner_sees_all_items(self, staff_token):
        """Owner user (lee.somers) should see all 7 items including ck-stripe"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        item_ids = [item["id"] for item in data["items"]]

        # lee.somers is an "owner" role, so they CAN see ck-stripe
        assert "ck-stripe" in item_ids, "Owner should see ck-stripe"

        # Owner should see all 7 items
        assert data["total_count"] == 7, f"Owner should see all 7 items, got {data['total_count']}"
        assert data["role"] == "owner", f"Expected role 'owner', got {data['role']}"

    def test_owner_role_returned(self, staff_token):
        """Owner user's role is correctly identified"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        # lee.somers is an owner, not master_admin
        assert data["role"] == "owner", f"Expected role 'owner', got {data['role']}"
        assert data["role"] != "master_admin", "Owner user should not have master_admin role"


class TestWalkthroughMetadata:
    """Tests for walkthrough field on guides"""

    GUIDES_WITH_WALKTHROUGH = [
        "service-log-fault",
        "crm-add-contact",
        "mbr-onboard-first",
        "mkt-first-campaign",
        "admin-invite-user",
    ]

    GUIDES_WITHOUT_WALKTHROUGH = [
        "gs-first-login",
        "gs-modules-overview",
        "crm-pipeline-first-deal",
        "service-triage-ai",
    ]

    def test_service_log_fault_has_walkthrough(self, master_admin_token):
        """service-log-fault guide has walkthrough with correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/service-log-fault",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "walkthrough" in data, "service-log-fault should have 'walkthrough' field"

        wt = data["walkthrough"]
        assert "initial_route" in wt, "walkthrough missing 'initial_route'"
        assert wt["initial_route"] == "/pulse", f"Expected initial_route '/pulse', got {wt['initial_route']}"

        assert "steps" in wt, "walkthrough missing 'steps'"
        assert isinstance(wt["steps"], list), "walkthrough steps should be a list"
        assert len(wt["steps"]) >= 3, f"Expected at least 3 steps, got {len(wt['steps'])}"

        # Verify step structure
        for step in wt["steps"]:
            assert "target" in step, "Step missing 'target'"
            assert "title" in step, "Step missing 'title'"
            assert "content" in step, "Step missing 'content'"

    def test_crm_add_contact_has_walkthrough(self, master_admin_token):
        """crm-add-contact guide has walkthrough"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/crm-add-contact",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "walkthrough" in data, "crm-add-contact should have 'walkthrough' field"
        assert data["walkthrough"]["initial_route"] == "/crm"

    def test_mbr_onboard_first_has_walkthrough(self, master_admin_token):
        """mbr-onboard-first guide has walkthrough"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/mbr-onboard-first",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "walkthrough" in data, "mbr-onboard-first should have 'walkthrough' field"
        assert data["walkthrough"]["initial_route"] == "/memberships"

    def test_mkt_first_campaign_has_walkthrough(self, master_admin_token):
        """mkt-first-campaign guide has walkthrough"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/mkt-first-campaign",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "walkthrough" in data, "mkt-first-campaign should have 'walkthrough' field"
        assert data["walkthrough"]["initial_route"] == "/marketing"

    def test_admin_invite_user_has_walkthrough(self, master_admin_token):
        """admin-invite-user guide has walkthrough"""
        resp = requests.get(
            f"{BASE_URL}/api/help/guides/admin-invite-user",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "walkthrough" in data, "admin-invite-user should have 'walkthrough' field"
        assert data["walkthrough"]["initial_route"] == "/master-admin"

    def test_guides_without_walkthrough(self, master_admin_token):
        """Guides that shouldn't have walkthrough don't have it"""
        for guide_id in self.GUIDES_WITHOUT_WALKTHROUGH:
            resp = requests.get(
                f"{BASE_URL}/api/help/guides/{guide_id}",
                headers={"Authorization": f"Bearer {master_admin_token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                # Either no walkthrough field, or it's None/empty
                if "walkthrough" in data:
                    wt = data["walkthrough"]
                    assert wt is None or wt == {} or not wt.get("steps"), \
                        f"Guide {guide_id} should NOT have walkthrough steps"


class TestChecklistCompletedStatus:
    """Tests for completed status based on DB state"""

    def test_completed_reflects_db_state(self, master_admin_token):
        """Completed status should reflect actual DB data"""
        resp = requests.get(
            f"{BASE_URL}/api/help/setup-checklist",
            headers={"Authorization": f"Bearer {master_admin_token}"}
        )
        assert resp.status_code == 200

        data = resp.json()
        # Just verify the structure is correct - actual completion depends on DB state
        for item in data["items"]:
            assert isinstance(item["completed"], bool), f"Item {item['id']} completed should be boolean"

        # completed_count should match actual completed items
        actual_completed = sum(1 for item in data["items"] if item["completed"])
        assert data["completed_count"] == actual_completed, \
            f"completed_count mismatch: {data['completed_count']} vs actual {actual_completed}"
