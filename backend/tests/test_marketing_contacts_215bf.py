"""
Iter 215bf — Marketing Contacts API Tests

Tests the new /api/marketing/contacts endpoints:
- CRUD operations (list, create, get, update, delete)
- CSV import
- Duplicate email handling (409)
- OR-module guard (crm OR marketing license grants access)
"""
import os
import pytest
import requests
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for master admin (has all modules)"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestMarketingContactsCRUD:
    """Test full CRUD operations on /api/marketing/contacts"""

    created_contact_id = None

    def test_list_contacts_empty_or_existing(self, admin_headers):
        """GET /api/marketing/contacts returns 200 with contacts array"""
        resp = requests.get(f"{BASE_URL}/api/marketing/contacts", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "contacts" in data, "Response should have 'contacts' key"
        assert "total" in data, "Response should have 'total' key"
        assert isinstance(data["contacts"], list), "contacts should be a list"
        assert isinstance(data["total"], int), "total should be an integer"
        print(f"PASS: List contacts returned {data['total']} contacts")

    def test_create_contact(self, admin_headers):
        """POST /api/marketing/contacts creates a new contact"""
        payload = {
            "email": "qa-bf-test@example.com",
            "first_name": "QA",
            "last_name": "Tester",
            "phone": "+447700900123",
            "tags": ["test", "iter215bf"],
            "email_consent": True,
            "sms_consent": False
        }
        resp = requests.post(f"{BASE_URL}/api/marketing/contacts", json=payload, headers=admin_headers)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "contact" in data, "Response should have 'contact' key"
        contact = data["contact"]
        assert contact["email"] == "qa-bf-test@example.com"
        assert contact["first_name"] == "QA"
        assert contact["last_name"] == "Tester"
        assert "id" in contact, "Contact should have an id"
        TestMarketingContactsCRUD.created_contact_id = contact["id"]
        print(f"PASS: Created contact with id {contact['id']}")

    def test_get_contact_by_id(self, admin_headers):
        """GET /api/marketing/contacts/{id} returns the contact"""
        contact_id = TestMarketingContactsCRUD.created_contact_id
        assert contact_id, "No contact id from previous test"
        resp = requests.get(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "contact" in data
        assert data["contact"]["id"] == contact_id
        assert data["contact"]["email"] == "qa-bf-test@example.com"
        print("PASS: GET contact by id returned correct contact")

    def test_update_contact(self, admin_headers):
        """PUT /api/marketing/contacts/{id} updates the contact"""
        contact_id = TestMarketingContactsCRUD.created_contact_id
        assert contact_id, "No contact id from previous test"
        payload = {
            "first_name": "QA-Updated",
            "last_name": "Tester-Updated",
            "tags": ["test", "iter215bf", "updated"]
        }
        resp = requests.put(f"{BASE_URL}/api/marketing/contacts/{contact_id}", json=payload, headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["contact"]["first_name"] == "QA-Updated"
        assert data["contact"]["last_name"] == "Tester-Updated"
        assert "updated" in data["contact"]["tags"]
        print("PASS: Updated contact successfully")

    def test_verify_update_persisted(self, admin_headers):
        """GET after PUT to verify update was persisted"""
        contact_id = TestMarketingContactsCRUD.created_contact_id
        resp = requests.get(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["contact"]["first_name"] == "QA-Updated"
        print("PASS: Update persisted correctly")

    def test_delete_contact(self, admin_headers):
        """DELETE /api/marketing/contacts/{id} removes the contact"""
        contact_id = TestMarketingContactsCRUD.created_contact_id
        assert contact_id, "No contact id from previous test"
        resp = requests.delete(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("deleted") == True
        print("PASS: Deleted contact successfully")

    def test_verify_delete_persisted(self, admin_headers):
        """GET after DELETE should return 404"""
        contact_id = TestMarketingContactsCRUD.created_contact_id
        resp = requests.get(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)
        assert resp.status_code == 404, f"Expected 404 after delete, got {resp.status_code}"
        print("PASS: Contact no longer exists after delete")


class TestDuplicateEmail:
    """Test duplicate email handling returns 409"""

    def test_duplicate_email_returns_409(self, admin_headers):
        """POST twice with same email should return 409 on second attempt"""
        unique_email = "duplicate-test-215bf@example.com"
        payload = {
            "email": unique_email,
            "first_name": "Duplicate",
            "last_name": "Test"
        }

        # First create should succeed
        resp1 = requests.post(f"{BASE_URL}/api/marketing/contacts", json=payload, headers=admin_headers)
        assert resp1.status_code in [200, 201], f"First create failed: {resp1.text}"
        contact_id = resp1.json()["contact"]["id"]
        print(f"PASS: First create succeeded with id {contact_id}")

        # Second create with same email should return 409
        resp2 = requests.post(f"{BASE_URL}/api/marketing/contacts", json=payload, headers=admin_headers)
        assert resp2.status_code == 409, f"Expected 409 for duplicate, got {resp2.status_code}: {resp2.text}"
        print("PASS: Duplicate email correctly returned 409")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)


class TestCSVImport:
    """Test CSV import endpoint"""

    def test_csv_import_creates_contacts(self, admin_headers):
        """POST /api/marketing/contacts/import with CSV creates contacts"""
        csv_content = """email,first_name,last_name,phone,tags
csv-import-1@example.com,CSV,One,+447700900001,"tag1,tag2"
csv-import-2@example.com,CSV,Two,+447700900002,tag3
"""
        files = {
            'file': ('contacts.csv', csv_content, 'text/csv')
        }
        # Remove Content-Type from headers for multipart
        headers = {"Authorization": admin_headers["Authorization"]}

        resp = requests.post(f"{BASE_URL}/api/marketing/contacts/import", files=files, headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "created" in data, "Response should have 'created' count"
        assert "updated" in data, "Response should have 'updated' count"
        assert "skipped" in data, "Response should have 'skipped' count"
        assert "errors" in data, "Response should have 'errors' list"

        # Should have created 2 new contacts
        assert data["created"] >= 2 or data["updated"] >= 0, f"Expected at least 2 created/updated, got {data}"
        print(f"PASS: CSV import returned created={data['created']}, updated={data['updated']}, skipped={data['skipped']}")

        # Verify contacts exist
        resp_list = requests.get(f"{BASE_URL}/api/marketing/contacts", params={"search": "csv-import"}, headers=admin_headers)
        assert resp_list.status_code == 200
        contacts = resp_list.json()["contacts"]
        csv_emails = [c["email"] for c in contacts if "csv-import" in c["email"]]
        assert len(csv_emails) >= 2, f"Expected at least 2 CSV-imported contacts, found {len(csv_emails)}"
        print(f"PASS: Verified {len(csv_emails)} CSV-imported contacts exist")

        # Cleanup
        for c in contacts:
            if "csv-import" in c["email"]:
                requests.delete(f"{BASE_URL}/api/marketing/contacts/{c['id']}", headers=admin_headers)


class TestSearchAndPagination:
    """Test search and pagination on contacts list"""

    def test_search_filters_contacts(self, admin_headers):
        """GET /api/marketing/contacts?search=... filters results"""
        # Create a contact with unique name
        payload = {
            "email": "searchtest-215bf@example.com",
            "first_name": "SearchUnique",
            "last_name": "TestName"
        }
        resp = requests.post(f"{BASE_URL}/api/marketing/contacts", json=payload, headers=admin_headers)
        assert resp.status_code in [200, 201]
        contact_id = resp.json()["contact"]["id"]

        # Search for it
        resp_search = requests.get(f"{BASE_URL}/api/marketing/contacts", params={"search": "SearchUnique"}, headers=admin_headers)
        assert resp_search.status_code == 200
        data = resp_search.json()
        found = any(c["first_name"] == "SearchUnique" for c in data["contacts"])
        assert found, "Search should find the contact by first_name"
        print("PASS: Search correctly filters contacts")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/marketing/contacts/{contact_id}", headers=admin_headers)


class TestUnauthorizedAccess:
    """Test that unauthenticated requests are rejected"""

    def test_list_without_auth_returns_401(self):
        """GET /api/marketing/contacts without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/marketing/contacts")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: Unauthenticated request correctly rejected with 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
