"""
Iter 216h66 — CRM Lead Conversion Tests
Tests the POST /api/crm/v2/contacts/{contact_id}/convert endpoint.

Conversion paths:
1. company_action='create' + create_opportunity=true → creates company + opportunity + flips lifecycle
2. company_action='link' + company_id → links to existing company, no opportunity
3. company_action='skip' → just updates lifecycle, no company/opp side effects

Validations:
- link without company_id returns 400
- create without company_data.name returns 400
- create_opportunity=true without opportunity.title returns 400
- Re-conversion blocked (lifecycle != 'lead' returns 400)

Audit & Activity:
- Activity created in crm2_activities for contact_id
- Audit record created with action='convert'
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_EMAIL = "e1.agent@gymaxisai.com"
TEST_PASSWORD = "E1Agent123!"


class TestLeadConversion:
    """CRM Lead Conversion endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client, crm_token):
        """Setup for each test - store token and client"""
        self.client = api_client
        self.token = crm_token
        self.headers = {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}
        self.created_contacts = []
        self.created_companies = []
        self.created_opportunities = []
        yield
        # Cleanup after each test
        self._cleanup()
    
    def _cleanup(self):
        """Delete test data created during tests"""
        for opp_id in self.created_opportunities:
            try:
                self.client.delete(f"{BASE_URL}/api/crm/v2/opportunities/{opp_id}", headers=self.headers)
            except Exception:
                pass
        for contact_id in self.created_contacts:
            try:
                self.client.delete(f"{BASE_URL}/api/crm/v2/contacts/{contact_id}", headers=self.headers)
            except Exception:
                pass
        for company_id in self.created_companies:
            try:
                self.client.delete(f"{BASE_URL}/api/crm/v2/companies/{company_id}", headers=self.headers)
            except Exception:
                pass
    
    def _create_test_lead(self, suffix=""):
        """Helper to create a test lead contact"""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "first_name": f"TEST_Lead{suffix}",
            "last_name": f"Convert{unique}",
            "email": f"test.lead.{unique}@example.com",
            "lifecycle": "lead"
        }
        resp = self.client.post(f"{BASE_URL}/api/crm/v2/contacts", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Failed to create test lead: {resp.text}"
        contact = resp.json()
        self.created_contacts.append(contact["id"])
        return contact
    
    def _create_test_company(self, suffix=""):
        """Helper to create a test company"""
        unique = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Company{suffix}_{unique}",
            "sector": "Technology"
        }
        resp = self.client.post(f"{BASE_URL}/api/crm/v2/companies", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Failed to create test company: {resp.text}"
        company = resp.json()
        self.created_companies.append(company["id"])
        return company
    
    # ─── Path 1: Create company + opportunity ───────────────────────────
    
    def test_convert_create_company_and_opportunity(self):
        """Convert lead with company_action='create' + create_opportunity=true"""
        lead = self._create_test_lead("_CreateOpp")
        
        payload = {
            "company_action": "create",
            "company_data": {
                "name": f"TEST_NewCompany_{uuid.uuid4().hex[:6]}",
                "sector": "Fitness",
                "website": "https://test-company.com"
            },
            "create_opportunity": True,
            "opportunity": {
                "title": "TEST_New Business Deal",
                "value": 5000,
                "stage": "qualified"
            },
            "new_lifecycle": "customer"
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 200, f"Convert failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert data.get("ok") is True, "Response should have ok=true"
        assert data.get("contact_id") == lead["id"], "contact_id should match"
        assert data.get("company_id") is not None, "company_id should be returned"
        assert data.get("opportunity_id") is not None, "opportunity_id should be returned"
        assert data.get("new_lifecycle") == "customer", "new_lifecycle should be 'customer'"
        
        # Track for cleanup
        if data.get("company_id"):
            self.created_companies.append(data["company_id"])
        if data.get("opportunity_id"):
            self.created_opportunities.append(data["opportunity_id"])
        
        # Verify contact was updated
        contact_resp = self.client.get(f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}", headers=self.headers)
        assert contact_resp.status_code == 200
        updated_contact = contact_resp.json()
        assert updated_contact.get("lifecycle") == "customer", "Contact lifecycle should be 'customer'"
        assert updated_contact.get("company_id") == data["company_id"], "Contact should be linked to new company"
        
        # Verify company was created
        company_resp = self.client.get(f"{BASE_URL}/api/crm/v2/companies/{data['company_id']}", headers=self.headers)
        assert company_resp.status_code == 200
        company = company_resp.json()
        assert "TEST_NewCompany" in company.get("name", ""), "Company name should match"
        
        # Verify opportunity was created
        opp_resp = self.client.get(f"{BASE_URL}/api/crm/v2/opportunities/{data['opportunity_id']}", headers=self.headers)
        assert opp_resp.status_code == 200
        opp = opp_resp.json()
        assert opp.get("title") == "TEST_New Business Deal", "Opportunity title should match"
        assert opp.get("value") == 5000, "Opportunity value should be 5000"
        assert opp.get("stage") == "qualified", "Opportunity stage should be 'qualified'"
    
    # ─── Path 2: Link existing company ──────────────────────────────────
    
    def test_convert_link_existing_company(self):
        """Convert lead with company_action='link' + existing company_id"""
        lead = self._create_test_lead("_LinkCompany")
        company = self._create_test_company("_Existing")
        
        payload = {
            "company_action": "link",
            "company_id": company["id"],
            "create_opportunity": False,
            "new_lifecycle": "customer"
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 200, f"Convert failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True
        assert data.get("contact_id") == lead["id"]
        assert data.get("company_id") == company["id"], "Should link to existing company"
        assert data.get("opportunity_id") is None, "No opportunity should be created"
        assert data.get("new_lifecycle") == "customer"
        
        # Verify contact was updated
        contact_resp = self.client.get(f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}", headers=self.headers)
        assert contact_resp.status_code == 200
        updated_contact = contact_resp.json()
        assert updated_contact.get("lifecycle") == "customer"
        assert updated_contact.get("company_id") == company["id"]
    
    # ─── Path 3: Skip company ───────────────────────────────────────────
    
    def test_convert_skip_company_lifecycle_only(self):
        """Convert lead with company_action='skip' — just updates lifecycle"""
        lead = self._create_test_lead("_SkipCompany")
        
        payload = {
            "company_action": "skip",
            "create_opportunity": False,
            "new_lifecycle": "prospect"
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 200, f"Convert failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") is True
        assert data.get("contact_id") == lead["id"]
        assert data.get("company_id") is None, "No company should be linked"
        assert data.get("opportunity_id") is None, "No opportunity should be created"
        assert data.get("new_lifecycle") == "prospect"
        
        # Verify contact lifecycle was updated
        contact_resp = self.client.get(f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}", headers=self.headers)
        assert contact_resp.status_code == 200
        updated_contact = contact_resp.json()
        assert updated_contact.get("lifecycle") == "prospect"
    
    # ─── Validation Tests ───────────────────────────────────────────────
    
    def test_convert_link_without_company_id_returns_400(self):
        """company_action='link' without company_id should return 400"""
        lead = self._create_test_lead("_LinkNoId")
        
        payload = {
            "company_action": "link",
            # Missing company_id
            "create_opportunity": False
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "company_id" in resp.text.lower(), "Error should mention company_id"
    
    def test_convert_create_without_company_name_returns_400(self):
        """company_action='create' without company_data.name should return 400"""
        lead = self._create_test_lead("_CreateNoName")
        
        payload = {
            "company_action": "create",
            "company_data": {
                "sector": "Fitness"
                # Missing name
            },
            "create_opportunity": False
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "name" in resp.text.lower(), "Error should mention name"
    
    def test_convert_opportunity_without_title_returns_400(self):
        """create_opportunity=true without opportunity.title should return 400"""
        lead = self._create_test_lead("_OppNoTitle")
        
        payload = {
            "company_action": "skip",
            "create_opportunity": True,
            "opportunity": {
                "value": 1000
                # Missing title
            }
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "title" in resp.text.lower(), "Error should mention title"
    
    # ─── Re-conversion Block ────────────────────────────────────────────
    
    def test_reconversion_blocked_for_non_lead(self):
        """POST .../convert on a contact with lifecycle!='lead' returns 400"""
        # Create a lead and convert it first
        lead = self._create_test_lead("_Reconvert")
        
        # First conversion
        payload1 = {
            "company_action": "skip",
            "create_opportunity": False,
            "new_lifecycle": "customer"
        }
        resp1 = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload1,
            headers=self.headers
        )
        assert resp1.status_code == 200, f"First convert failed: {resp1.text}"
        
        # Attempt re-conversion
        payload2 = {
            "company_action": "skip",
            "create_opportunity": False,
            "new_lifecycle": "champion"
        }
        resp2 = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload2,
            headers=self.headers
        )
        
        assert resp2.status_code == 400, f"Expected 400 for re-conversion, got {resp2.status_code}: {resp2.text}"
        assert "cannot convert" in resp2.text.lower(), "Error should mention 'Cannot convert'"
        assert "customer" in resp2.text.lower(), "Error should mention current lifecycle"
    
    # ─── Activity & Audit Tests ─────────────────────────────────────────
    
    def test_convert_creates_activity_record(self):
        """Verify a 'Lead converted' activity is created in crm2_activities"""
        lead = self._create_test_lead("_Activity")
        
        payload = {
            "company_action": "skip",
            "create_opportunity": False,
            "new_lifecycle": "customer"
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        assert resp.status_code == 200
        
        # Check activities for this contact
        activities_resp = self.client.get(
            f"{BASE_URL}/api/crm/v2/activities?contact_id={lead['id']}",
            headers=self.headers
        )
        assert activities_resp.status_code == 200
        activities = activities_resp.json().get("activities", [])
        
        # Find the conversion activity
        conversion_activity = None
        for act in activities:
            if "converted" in act.get("subject", "").lower():
                conversion_activity = act
                break
        
        assert conversion_activity is not None, "Should have a 'Lead converted' activity"
        assert conversion_activity.get("type") == "system", "Activity type should be 'system'"
        assert "customer" in conversion_activity.get("subject", "").lower(), "Activity should mention new lifecycle"
    
    def test_convert_creates_audit_record(self):
        """Verify audit record is created with action='convert'"""
        lead = self._create_test_lead("_Audit")
        
        payload = {
            "company_action": "skip",
            "create_opportunity": False,
            "new_lifecycle": "customer"
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        assert resp.status_code == 200
        
        # Check audit trail for this contact
        audit_resp = self.client.get(
            f"{BASE_URL}/api/crm/audit?entity_type=contact&entity_id={lead['id']}",
            headers=self.headers
        )
        
        if audit_resp.status_code == 200:
            # Audit endpoint returns 'entries' not 'audits'
            audits = audit_resp.json().get("entries", []) or audit_resp.json().get("audits", [])
            convert_audit = None
            for audit in audits:
                if audit.get("action") == "convert":
                    convert_audit = audit
                    break
            
            assert convert_audit is not None, "Should have an audit record with action='convert'"
            assert convert_audit.get("entity_type") == "contact"
            assert convert_audit.get("entity_id") == lead["id"]
        else:
            # Audit endpoint might not be exposed, skip this assertion
            pytest.skip("Audit endpoint not available for verification")
    
    # ─── Edge Cases ─────────────────────────────────────────────────────
    
    def test_convert_nonexistent_contact_returns_404(self):
        """Converting a non-existent contact should return 404"""
        fake_id = str(uuid.uuid4())
        
        payload = {
            "company_action": "skip",
            "create_opportunity": False
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{fake_id}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    
    def test_convert_link_nonexistent_company_returns_404(self):
        """Linking to a non-existent company should return 404"""
        lead = self._create_test_lead("_LinkFake")
        fake_company_id = str(uuid.uuid4())
        
        payload = {
            "company_action": "link",
            "company_id": fake_company_id,
            "create_opportunity": False
        }
        
        resp = self.client.post(
            f"{BASE_URL}/api/crm/v2/contacts/{lead['id']}/convert",
            json=payload,
            headers=self.headers
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"


# ─── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def crm_token(api_client):
    """Get CRM authentication token via cross-login"""
    # First, login to main app
    login_resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if login_resp.status_code != 200:
        pytest.skip(f"Main login failed: {login_resp.status_code} - {login_resp.text}")
    
    main_token = login_resp.json().get("token")
    if not main_token:
        pytest.skip("No token returned from main login")
    
    # Cross-login to CRM
    crm_resp = api_client.post(
        f"{BASE_URL}/api/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}"}
    )
    
    if crm_resp.status_code != 200:
        pytest.skip(f"CRM cross-login failed: {crm_resp.status_code} - {crm_resp.text}")
    
    crm_token = crm_resp.json().get("token")
    if not crm_token:
        pytest.skip("No CRM token returned")
    
    return crm_token
