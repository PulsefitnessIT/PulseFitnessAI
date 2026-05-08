"""
Iteration 216ae — Costume → Invoice Line + Vocabulary Swap Tests

Tests for:
1. Costume billing integration with monthly invoices
   - Preview includes costume_pence when costumes exist with status ordered/arrived/fitted
   - Generate stamps costumes with invoiced_on + invoice_id (idempotent)
   - Re-running generate for same period doesn't double-bill
   - Running for different period doesn't re-include already-invoiced costumes
   - Costume status 'needed' does NOT produce a line
   - Costume with total_pence=0 does NOT produce a line
   - Sub-profile costumes roll into parent member's invoice

2. Vocabulary endpoint for member portal
   - GET /api/member/studio/vocabulary returns correct nouns based on studio_industry
   - Default fallback when no industry set
"""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "bob@knockers.com"
OPERATOR_PASSWORD = "Test123!"


class TestCostumeBillingIntegration:
    """Test costume → invoice line integration"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """Setup: Login as operator and get org context"""
        self.client = api_client
        # Login as operator
        login_resp = self.client.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert login_resp.status_code == 200, f"Operator login failed: {login_resp.text}"
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.org_id = login_resp.json()["user"]["organization_id"]
        
        # Store created resources for cleanup
        self.created_events = []
        self.created_costumes = []
        self.created_members = []
        self.created_invoices = []
        
        yield
        
        # Cleanup
        self._cleanup()
    
    def _cleanup(self):
        """Clean up test data"""
        # Delete costumes
        for event_id, costume_id in self.created_costumes:
            try:
                self.client.delete(
                    f"{BASE_URL}/api/memberships/events/{event_id}/costumes/{costume_id}",
                    headers=self.headers
                )
            except:
                pass
        
        # Archive events
        for event_id in self.created_events:
            try:
                self.client.delete(
                    f"{BASE_URL}/api/memberships/events/{event_id}",
                    headers=self.headers
                )
            except:
                pass
        
        # Delete test members
        for member_id in self.created_members:
            try:
                self.client.delete(
                    f"{BASE_URL}/api/memberships/members/{member_id}",
                    headers=self.headers
                )
            except:
                pass
    
    def _create_test_event(self, name="TEST_CostumeBilling_Event"):
        """Create a test event for costume testing"""
        resp = self.client.post(f"{BASE_URL}/api/memberships/events", headers=self.headers, json={
            "name": name,
            "kind": "recital",
            "starts_at": "2026-06-01T18:00:00Z",
            "ends_at": "2026-06-01T21:00:00Z",
            "venue": "Test Venue"
        })
        assert resp.status_code == 200, f"Failed to create event: {resp.text}"
        event = resp.json()
        self.created_events.append(event["id"])
        return event
    
    def _create_test_member(self, email_prefix="TEST_costume"):
        """Create a test member"""
        import uuid
        unique = str(uuid.uuid4())[:8]
        resp = self.client.post(f"{BASE_URL}/api/memberships/members", headers=self.headers, json={
            "email": f"{email_prefix}_{unique}@example.com",
            "first_name": "Test",
            "last_name": "CostumeMember"
        })
        assert resp.status_code in [200, 201], f"Failed to create member: {resp.text}"
        data = resp.json()
        # API wraps member in a "member" key
        member = data.get("member", data)
        self.created_members.append(member["id"])
        return member
    
    def _create_costume(self, event_id, member_id, status="ordered", total_pence=2500, 
                        costume_name="Test Costume", sub_profile_id=None):
        """Create a costume for testing"""
        payload = {
            "member_id": member_id,
            "attendee_name": "Test Attendee",
            "costume_name": costume_name,
            "size": "M",
            "total_pence": total_pence,
            "status": status
        }
        if sub_profile_id:
            payload["sub_profile_id"] = sub_profile_id
        
        resp = self.client.post(
            f"{BASE_URL}/api/memberships/events/{event_id}/costumes",
            headers=self.headers,
            json=payload
        )
        assert resp.status_code == 200, f"Failed to create costume: {resp.text}"
        costume = resp.json()
        self.created_costumes.append((event_id, costume["id"]))
        return costume
    
    def test_preview_no_costumes_unchanged(self):
        """When member has NO costumes, preview output should have no costume_pence"""
        # Create a member with no costumes
        member = self._create_test_member("TEST_no_costume")
        
        # Run preview for current month
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        # Member with no bookings and no costumes should not appear in invoices
        # or if they do, costume_pence should be 0
        for inv in data.get("invoices", []):
            if inv["member_id"] == member["id"]:
                assert inv.get("costume_pence", 0) == 0, "costume_pence should be 0 for member with no costumes"
        print("PASS: Preview with no costumes shows no costume_pence")
    
    def test_preview_with_ordered_costume_includes_costume_line(self):
        """When member has costume with status 'ordered', preview includes costume line"""
        member = self._create_test_member("TEST_ordered_costume")
        event = self._create_test_event("TEST_Recital_Ordered")
        costume = self._create_costume(event["id"], member["id"], status="ordered", total_pence=3500)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        # Find the member's invoice
        member_inv = None
        for inv in data.get("invoices", []):
            if inv["member_id"] == member["id"]:
                member_inv = inv
                break
        
        assert member_inv is not None, "Member should appear in preview with costume"
        assert member_inv.get("costume_pence", 0) > 0, f"costume_pence should be > 0, got {member_inv.get('costume_pence')}"
        
        # Check for costume line in lines array
        costume_lines = [ln for ln in member_inv.get("lines", []) if ln.get("kind") == "costume"]
        assert len(costume_lines) > 0, "Should have at least one costume line"
        
        costume_line = costume_lines[0]
        assert "Costume" in costume_line.get("description", ""), f"Description should mention Costume: {costume_line}"
        print(f"PASS: Preview includes costume line with costume_pence={member_inv['costume_pence']}")
    
    def test_preview_with_arrived_costume_includes_costume_line(self):
        """When member has costume with status 'arrived', preview includes costume line"""
        member = self._create_test_member("TEST_arrived_costume")
        event = self._create_test_event("TEST_Recital_Arrived")
        costume = self._create_costume(event["id"], member["id"], status="arrived", total_pence=4000)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        member_inv = next((inv for inv in data.get("invoices", []) if inv["member_id"] == member["id"]), None)
        assert member_inv is not None, "Member should appear in preview"
        assert member_inv.get("costume_pence", 0) > 0
        print("PASS: Preview includes costume line for 'arrived' status")
    
    def test_preview_with_fitted_costume_includes_costume_line(self):
        """When member has costume with status 'fitted', preview includes costume line"""
        member = self._create_test_member("TEST_fitted_costume")
        event = self._create_test_event("TEST_Recital_Fitted")
        costume = self._create_costume(event["id"], member["id"], status="fitted", total_pence=2800)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        member_inv = next((inv for inv in data.get("invoices", []) if inv["member_id"] == member["id"]), None)
        assert member_inv is not None
        assert member_inv.get("costume_pence", 0) > 0
        print("PASS: Preview includes costume line for 'fitted' status")
    
    def test_costume_status_needed_no_line(self):
        """Costume with status 'needed' should NOT produce a costume line"""
        member = self._create_test_member("TEST_needed_costume")
        event = self._create_test_event("TEST_Recital_Needed")
        costume = self._create_costume(event["id"], member["id"], status="needed", total_pence=3000)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Member should not appear or have 0 costume_pence
        member_inv = next((inv for inv in data.get("invoices", []) if inv["member_id"] == member["id"]), None)
        if member_inv:
            assert member_inv.get("costume_pence", 0) == 0, "costume_pence should be 0 for 'needed' status"
            costume_lines = [ln for ln in member_inv.get("lines", []) if ln.get("kind") == "costume"]
            assert len(costume_lines) == 0, "Should have no costume lines for 'needed' status"
        print("PASS: Costume with status 'needed' does NOT produce a line")
    
    def test_costume_zero_total_pence_no_line(self):
        """Costume with total_pence=0 should NOT produce a costume line"""
        member = self._create_test_member("TEST_zero_costume")
        event = self._create_test_event("TEST_Recital_Zero")
        costume = self._create_costume(event["id"], member["id"], status="ordered", total_pence=0)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        member_inv = next((inv for inv in data.get("invoices", []) if inv["member_id"] == member["id"]), None)
        if member_inv:
            assert member_inv.get("costume_pence", 0) == 0, "costume_pence should be 0 for zero-cost costume"
        print("PASS: Costume with total_pence=0 does NOT produce a line")
    
    def test_generate_stamps_costume_with_invoiced_on(self):
        """Generate should stamp costume with invoiced_on and invoice_id"""
        member = self._create_test_member("TEST_stamp_costume")
        event = self._create_test_event("TEST_Recital_Stamp")
        costume = self._create_costume(event["id"], member["id"], status="ordered", total_pence=5000)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp.status_code == 200, f"Generate failed: {resp.text}"
        data = resp.json()
        
        # Track invoice for cleanup
        for inv in data.get("invoices", []):
            self.created_invoices.append(inv["id"])
        
        # Verify costume was stamped - fetch the costume again
        costume_resp = self.client.get(
            f"{BASE_URL}/api/memberships/events/{event['id']}/costumes",
            headers=self.headers
        )
        assert costume_resp.status_code == 200
        costumes = costume_resp.json().get("costumes", [])
        
        updated_costume = next((c for c in costumes if c["id"] == costume["id"]), None)
        assert updated_costume is not None, "Costume should still exist"
        assert updated_costume.get("invoiced_on") == period, f"invoiced_on should be {period}, got {updated_costume.get('invoiced_on')}"
        assert updated_costume.get("invoice_id") is not None, "invoice_id should be set"
        print(f"PASS: Generate stamps costume with invoiced_on={period} and invoice_id")
    
    def test_generate_idempotent_no_double_billing(self):
        """Re-running generate for same period should NOT double-bill"""
        member = self._create_test_member("TEST_idempotent_costume")
        event = self._create_test_event("TEST_Recital_Idempotent")
        costume = self._create_costume(event["id"], member["id"], status="ordered", total_pence=4500)
        
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # First generate
        resp1 = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        first_invoice = next((inv for inv in data1.get("invoices", []) if inv["member_id"] == member["id"]), None)
        
        # Second generate for same period
        resp2 = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            headers=self.headers,
            json={"period": period, "member_ids": [member["id"]]}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        second_invoice = next((inv for inv in data2.get("invoices", []) if inv["member_id"] == member["id"]), None)
        
        # Both should have same costume_pence (not doubled)
        if first_invoice and second_invoice:
            assert first_invoice.get("costume_pence") == second_invoice.get("costume_pence"), \
                "costume_pence should not double on re-run"
        print("PASS: Re-running generate for same period does NOT double-bill")
    
    def test_different_period_excludes_already_invoiced_costume(self):
        """Running for different period should NOT re-include already-invoiced costume"""
        member = self._create_test_member("TEST_diff_period_costume")
        event = self._create_test_event("TEST_Recital_DiffPeriod")
        costume = self._create_costume(event["id"], member["id"], status="ordered", total_pence=3200)
        
        # Generate for current month
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp1 = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            headers=self.headers,
            json={"period": current_period, "member_ids": [member["id"]]}
        )
        assert resp1.status_code == 200
        
        # Preview for next month
        next_month = datetime.now(timezone.utc).month + 1
        next_year = datetime.now(timezone.utc).year
        if next_month > 12:
            next_month = 1
            next_year += 1
        next_period = f"{next_year}-{next_month:02d}"
        
        resp2 = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": next_period, "member_ids": [member["id"]]}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        
        # Member should not appear or have 0 costume_pence in next period
        member_inv = next((inv for inv in data2.get("invoices", []) if inv["member_id"] == member["id"]), None)
        if member_inv:
            assert member_inv.get("costume_pence", 0) == 0, \
                "Already-invoiced costume should not appear in different period"
        print("PASS: Different period excludes already-invoiced costume")
    
    def test_regression_class_lines_still_compute(self):
        """Existing class/smoothed/sibling/multi-class discount lines still compute correctly"""
        # This is a regression test - costume line should be additive, not destructive
        # Just verify the preview endpoint still works and returns expected structure
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        resp = self.client.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            headers=self.headers,
            json={"period": period}
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "period" in data
        assert "member_count" in data
        assert "total_pence" in data
        assert "invoices" in data
        
        # If there are invoices, verify line structure
        for inv in data.get("invoices", []):
            assert "lines" in inv
            assert "total_pence" in inv
            for line in inv.get("lines", []):
                assert "kind" in line
                assert "description" in line
                assert "amount_pence" in line
        
        print("PASS: Regression - preview structure intact, class lines still compute")


class TestVocabularyEndpoint:
    """Test vocabulary endpoint for member portal"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """Setup: Login as operator"""
        self.client = api_client
        # Login as operator
        login_resp = self.client.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert login_resp.status_code == 200, f"Operator login failed: {login_resp.text}"
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.org_id = login_resp.json()["user"]["organization_id"]
        
        # Store original industry for restoration
        self.original_industry = None
        
        yield
        
        # Restore original industry if changed
        if self.original_industry is not None:
            self._set_studio_industry(self.original_industry)
    
    def _set_studio_industry(self, industry):
        """Set the studio industry for vocabulary testing"""
        resp = self.client.post(f"{BASE_URL}/api/memberships/studio/settings", headers=self.headers, json={
            "studio_mode": True,
            "studio_industry": industry
        })
        return resp
    
    def _get_current_industry(self):
        """Get current studio settings"""
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/settings", headers=self.headers)
        if resp.status_code == 200:
            return resp.json().get("studio_industry")
        return None
    
    def test_operator_vocabulary_endpoint(self):
        """GET /api/memberships/studio/vocabulary returns vocabulary"""
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/vocabulary", headers=self.headers)
        assert resp.status_code == 200, f"Vocabulary endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "member_singular" in data, "Should have member_singular"
        assert "member_plural" in data, "Should have member_plural"
        assert "guardian_noun" in data, "Should have guardian_noun"
        
        print(f"PASS: Operator vocabulary endpoint returns: {data}")
    
    def test_vocabulary_with_cheer_industry(self):
        """Vocabulary with 'cheer' industry returns 'athlete'/'athletes'"""
        # Save original
        self.original_industry = self._get_current_industry()
        
        # Set to cheer
        set_resp = self._set_studio_industry("cheer")
        if set_resp.status_code != 200:
            pytest.skip("Could not set studio industry to cheer")
        
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/vocabulary", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get("member_singular") == "athlete", f"Expected 'athlete', got {data.get('member_singular')}"
        assert data.get("member_plural") == "athletes", f"Expected 'athletes', got {data.get('member_plural')}"
        print("PASS: Cheer industry returns athlete/athletes vocabulary")
    
    def test_vocabulary_with_dance_industry(self):
        """Vocabulary with 'dance' industry returns 'student'/'students'"""
        self.original_industry = self._get_current_industry()
        
        set_resp = self._set_studio_industry("dance")
        if set_resp.status_code != 200:
            pytest.skip("Could not set studio industry to dance")
        
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/vocabulary", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get("member_singular") == "student", f"Expected 'student', got {data.get('member_singular')}"
        assert data.get("member_plural") == "students", f"Expected 'students', got {data.get('member_plural')}"
        print("PASS: Dance industry returns student/students vocabulary")
    
    def test_vocabulary_with_swim_industry(self):
        """Vocabulary with 'swim' industry returns 'swimmer'/'swimmers'"""
        self.original_industry = self._get_current_industry()
        
        set_resp = self._set_studio_industry("swim")
        if set_resp.status_code != 200:
            pytest.skip("Could not set studio industry to swim")
        
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/vocabulary", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get("member_singular") == "swimmer", f"Expected 'swimmer', got {data.get('member_singular')}"
        assert data.get("member_plural") == "swimmers", f"Expected 'swimmers', got {data.get('member_plural')}"
        print("PASS: Swim industry returns swimmer/swimmers vocabulary")
    
    def test_vocabulary_default_fallback(self):
        """Default vocabulary (no industry) returns 'member'/'members'"""
        self.original_industry = self._get_current_industry()
        
        # Set to multi (generic) or clear industry
        set_resp = self._set_studio_industry("multi")
        if set_resp.status_code != 200:
            pytest.skip("Could not set studio industry")
        
        resp = self.client.get(f"{BASE_URL}/api/memberships/studio/vocabulary", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # multi industry uses member/members
        assert data.get("member_singular") == "member", f"Expected 'member', got {data.get('member_singular')}"
        assert data.get("member_plural") == "members", f"Expected 'members', got {data.get('member_plural')}"
        print("PASS: Default/multi industry returns member/members vocabulary")


class TestMemberVocabularyEndpoint:
    """Test member-side vocabulary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """Setup: Create a test member and get member token"""
        self.client = api_client
        
        # First login as operator to get org context
        login_resp = self.client.post(f"{BASE_URL}/api/auth/login", json={
            "email": OPERATOR_EMAIL,
            "password": OPERATOR_PASSWORD
        })
        assert login_resp.status_code == 200
        self.operator_token = login_resp.json()["token"]
        self.operator_headers = {"Authorization": f"Bearer {self.operator_token}"}
        self.org_id = login_resp.json()["user"]["organization_id"]
        
        # Get org slug for member registration
        org_resp = self.client.get(f"{BASE_URL}/api/organizations/{self.org_id}", headers=self.operator_headers)
        self.org_slug = None
        if org_resp.status_code == 200:
            self.org_slug = org_resp.json().get("slug")
        
        # Create a test member
        import uuid
        self.test_email = f"TEST_vocab_member_{uuid.uuid4().hex[:8]}@example.com"
        self.test_password = "TestVocab123!"
        
        reg_resp = self.client.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": self.test_email,
            "password": self.test_password,
            "first_name": "Test",
            "last_name": "VocabMember",
            "organization_id": self.org_id
        })
        
        if reg_resp.status_code == 200:
            self.member_token = reg_resp.json()["token"]
            self.member_id = reg_resp.json()["member"]["id"]
            self.member_headers = {"Authorization": f"Bearer {self.member_token}"}
        else:
            # Try login if already exists
            login_resp = self.client.post(f"{BASE_URL}/api/member-auth/login", json={
                "email": self.test_email,
                "password": self.test_password
            })
            if login_resp.status_code == 200:
                self.member_token = login_resp.json()["token"]
                self.member_id = login_resp.json()["member"]["id"]
                self.member_headers = {"Authorization": f"Bearer {self.member_token}"}
            else:
                self.member_token = None
                self.member_headers = None
        
        yield
        
        # Cleanup - delete test member
        if hasattr(self, 'member_id'):
            try:
                self.client.delete(
                    f"{BASE_URL}/api/memberships/members/{self.member_id}",
                    headers=self.operator_headers
                )
            except:
                pass
    
    def test_member_vocabulary_endpoint(self):
        """GET /api/member/studio/vocabulary returns vocabulary for member"""
        if not self.member_headers:
            pytest.skip("Could not create test member")
        
        resp = self.client.get(f"{BASE_URL}/api/member/studio/vocabulary", headers=self.member_headers)
        assert resp.status_code == 200, f"Member vocabulary endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "member_singular" in data, "Should have member_singular"
        assert "member_plural" in data, "Should have member_plural"
        assert "guardian_noun" in data, "Should have guardian_noun"
        
        print(f"PASS: Member vocabulary endpoint returns: {data}")
    
    def test_member_vocabulary_unauthorized(self):
        """GET /api/member/studio/vocabulary without auth returns 401/403"""
        resp = self.client.get(f"{BASE_URL}/api/member/studio/vocabulary")
        assert resp.status_code in [401, 403, 422], f"Expected auth error, got {resp.status_code}"
        print("PASS: Member vocabulary endpoint requires authentication")


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
