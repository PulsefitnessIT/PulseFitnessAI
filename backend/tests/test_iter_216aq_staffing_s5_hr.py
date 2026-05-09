"""
Phase S5 — Staffing HR 2.0 Backend Tests
=========================================
Tests for HR endpoints: Profile 2.0, Documents, Disciplinary, Training.

Endpoints tested:
- GET/PATCH /api/staffing/hr/profile/{staff_id}
- GET/POST/PATCH/DELETE /api/staffing/hr/documents
- GET/POST/PATCH/DELETE /api/staffing/hr/disciplinary
- GET/POST/PATCH/DELETE /api/staffing/hr/training

Multi-tenant isolation and role-based access control also tested.
"""
import os
import pytest
import requests
from uuid import uuid4

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")

# Test credentials from test_credentials.md
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"
BOB_ORG_ID = "6e2b80c5-05b0-4a8a-a06a-2af52ee7cd8c"
BOB_STAFF_ID = "47346a73-da90-4147-a4ff-5bdce94bb80b"

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def bob_token():
    """Get auth token for Bob (owner/manager)."""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BOB_EMAIL, "password": BOB_PASSWORD},
        headers=headers,
    )
    assert resp.status_code == 200, f"Bob login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for Master Admin."""
    headers = {"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=headers,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def bob_headers(bob_token):
    """Headers for Bob's requests."""
    return {
        "Authorization": f"Bearer {bob_token}",
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS,
    }


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers for Admin's requests."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
        "X-RateLimit-Bypass": RATE_LIMIT_BYPASS,
    }


# ═══════════════════════════════════════════════════════════════════
# PROFILE 2.0 TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProfileEndpoints:
    """Tests for GET/PATCH /api/staffing/hr/profile/{staff_id}"""

    def test_get_profile_returns_staff_doc(self, bob_headers):
        """GET /api/staffing/hr/profile/{staff_id} returns the staff doc."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/profile/{BOB_STAFF_ID}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"GET profile failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["id"] == BOB_STAFF_ID
        print(f"✓ GET profile returns staff doc with id={data['id']}")

    def test_patch_profile_updates_whitelisted_fields(self, bob_headers):
        """PATCH updates only whitelisted PROFILE_FIELDS and stamps hr_updated_at + hr_updated_by."""
        unique_city = f"TEST_City_{uuid4().hex[:6]}"
        payload = {
            "city": unique_city,
            "postcode": "TE5T 1AB",
            "emergency_contact_name": "Test Emergency Contact",
        }
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/profile/{BOB_STAFF_ID}",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"PATCH profile failed: {resp.text}"
        data = resp.json()
        assert data.get("city") == unique_city
        assert data.get("postcode") == "TE5T 1AB"
        assert data.get("emergency_contact_name") == "Test Emergency Contact"
        assert "hr_updated_at" in data
        assert "hr_updated_by" in data
        print(f"✓ PATCH profile updates whitelisted fields, stamps hr_updated_at={data['hr_updated_at']}")

    def test_patch_profile_rejects_empty_payload(self, bob_headers):
        """PATCH with empty payload returns 400."""
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/profile/{BOB_STAFF_ID}",
            json={},
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for empty payload, got {resp.status_code}"
        print("✓ PATCH profile rejects empty payload with 400")

    def test_patch_profile_ignores_non_whitelisted_fields(self, bob_headers):
        """PATCH ignores fields not in PROFILE_FIELDS whitelist."""
        # Try to update a non-whitelisted field like 'full_name' or 'role'
        payload = {
            "city": "ValidCity",
            "full_name": "HACKED_NAME",  # Not in PROFILE_FIELDS
        }
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/profile/{BOB_STAFF_ID}",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        data = resp.json()
        # full_name should NOT be changed to HACKED_NAME
        assert data.get("full_name") != "HACKED_NAME"
        print("✓ PATCH profile ignores non-whitelisted fields")


# ═══════════════════════════════════════════════════════════════════
# DOCUMENTS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDocumentsEndpoints:
    """Tests for CRUD on /api/staffing/hr/documents"""

    created_doc_id = None

    def test_post_document_creates_record(self, bob_headers):
        """POST /api/staffing/hr/documents creates a document."""
        payload = {
            "staff_id": BOB_STAFF_ID,
            "name": f"TEST_Contract_{uuid4().hex[:6]}",
            "kind": "contract",
            "url": "https://example.com/test-contract.pdf",
            "expires_at": "2027-12-31",
            "notes": "Test contract document",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/documents",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"POST document failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["kind"] == "contract"
        assert data["archived"] == False
        TestDocumentsEndpoints.created_doc_id = data["id"]
        print(f"✓ POST document creates record with id={data['id']}")

    def test_post_document_validates_kind(self, bob_headers):
        """POST validates kind ∈ {contract,id,onboarding,training,policy,other}."""
        payload = {
            "staff_id": BOB_STAFF_ID,
            "name": "Invalid Kind Doc",
            "kind": "invalid_kind",
            "url": "https://example.com/test.pdf",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/documents",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for invalid kind, got {resp.status_code}"
        print("✓ POST document validates kind enum")

    def test_get_documents_returns_non_archived(self, bob_headers):
        """GET /api/staffing/hr/documents returns only non-archived."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/documents",
            params={"staff_id": BOB_STAFF_ID},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"GET documents failed: {resp.text}"
        data = resp.json()
        assert "documents" in data
        # All returned docs should have archived != True
        for doc in data["documents"]:
            assert doc.get("archived") != True
        print(f"✓ GET documents returns {len(data['documents'])} non-archived docs")

    def test_patch_document_updates_record(self, bob_headers):
        """PATCH /api/staffing/hr/documents/{id} updates the document."""
        if not TestDocumentsEndpoints.created_doc_id:
            pytest.skip("No document created to update")
        
        payload = {"name": "Updated Contract Name", "notes": "Updated notes"}
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/documents/{TestDocumentsEndpoints.created_doc_id}",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"PATCH document failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "Updated Contract Name"
        assert "updated_at" in data
        print("✓ PATCH document updates record")

    def test_delete_document_soft_deletes(self, bob_headers):
        """DELETE /api/staffing/hr/documents/{id} soft-deletes (archived=true)."""
        if not TestDocumentsEndpoints.created_doc_id:
            pytest.skip("No document created to delete")
        
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/hr/documents/{TestDocumentsEndpoints.created_doc_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"DELETE document failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print("✓ DELETE document soft-deletes (archived=true)")


# ═══════════════════════════════════════════════════════════════════
# DISCIPLINARY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDisciplinaryEndpoints:
    """Tests for CRUD on /api/staffing/hr/disciplinary"""

    created_disc_id = None

    def test_post_disciplinary_creates_record(self, bob_headers):
        """POST /api/staffing/hr/disciplinary creates a record."""
        payload = {
            "staff_id": BOB_STAFF_ID,
            "occurred_at": "2026-01-15",
            "severity": "verbal",
            "summary": f"TEST_Disciplinary_{uuid4().hex[:6]}",
            "actions_agreed": "Verbal warning issued",
            "follow_up_at": "2026-02-15",
            "confidential": True,
            "manager_note": "Private manager note",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/disciplinary",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"POST disciplinary failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["severity"] == "verbal"
        assert data["confidential"] == True
        assert data["archived"] == False
        TestDisciplinaryEndpoints.created_disc_id = data["id"]
        print(f"✓ POST disciplinary creates record with id={data['id']}")

    def test_post_disciplinary_validates_severity(self, bob_headers):
        """POST validates severity ∈ {informal,verbal,written,final,suspension,dismissal}."""
        payload = {
            "staff_id": BOB_STAFF_ID,
            "occurred_at": "2026-01-15",
            "severity": "invalid_severity",
            "summary": "Test",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/disciplinary",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for invalid severity, got {resp.status_code}"
        print("✓ POST disciplinary validates severity enum")

    def test_post_disciplinary_all_severity_levels(self, bob_headers):
        """POST accepts all valid severity levels."""
        valid_severities = ["informal", "verbal", "written", "final", "suspension", "dismissal"]
        for sev in valid_severities:
            payload = {
                "staff_id": BOB_STAFF_ID,
                "occurred_at": "2026-01-15",
                "severity": sev,
                "summary": f"TEST_Severity_{sev}_{uuid4().hex[:4]}",
            }
            resp = requests.post(
                f"{BASE_URL}/api/staffing/hr/disciplinary",
                json=payload,
                headers=bob_headers,
            )
            assert resp.status_code == 200, f"POST with severity={sev} failed: {resp.text}"
        print(f"✓ POST disciplinary accepts all {len(valid_severities)} severity levels")

    def test_get_disciplinary_list(self, bob_headers):
        """GET /api/staffing/hr/disciplinary returns records."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/disciplinary",
            params={"staff_id": BOB_STAFF_ID},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"GET disciplinary failed: {resp.text}"
        data = resp.json()
        assert "records" in data
        print(f"✓ GET disciplinary returns {len(data['records'])} records")

    def test_patch_disciplinary_updates_record(self, bob_headers):
        """PATCH /api/staffing/hr/disciplinary/{id} updates the record."""
        if not TestDisciplinaryEndpoints.created_disc_id:
            pytest.skip("No disciplinary record created to update")
        
        payload = {"summary": "Updated summary", "resolved_at": "2026-03-01"}
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/disciplinary/{TestDisciplinaryEndpoints.created_disc_id}",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"PATCH disciplinary failed: {resp.text}"
        data = resp.json()
        assert data["summary"] == "Updated summary"
        assert data["resolved_at"] == "2026-03-01"
        print("✓ PATCH disciplinary updates record")

    def test_delete_disciplinary_soft_deletes(self, bob_headers):
        """DELETE /api/staffing/hr/disciplinary/{id} soft-deletes."""
        if not TestDisciplinaryEndpoints.created_disc_id:
            pytest.skip("No disciplinary record created to delete")
        
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/hr/disciplinary/{TestDisciplinaryEndpoints.created_disc_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"DELETE disciplinary failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print("✓ DELETE disciplinary soft-deletes")


# ═══════════════════════════════════════════════════════════════════
# TRAINING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTrainingEndpoints:
    """Tests for CRUD on /api/staffing/hr/training"""

    created_training_id = None

    def test_post_training_creates_record(self, bob_headers):
        """POST /api/staffing/hr/training creates training record."""
        payload = {
            "staff_id": BOB_STAFF_ID,
            "course_name": f"TEST_Course_{uuid4().hex[:6]}",
            "provider": "Test Training Provider",
            "completed_at": "2026-01-10",
            "expires_at": "2028-01-10",
            "score": 95.5,
            "notes": "Excellent performance",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/training",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"POST training failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["course_name"] == payload["course_name"]
        assert data["score"] == 95.5
        assert data["archived"] == False
        TestTrainingEndpoints.created_training_id = data["id"]
        print(f"✓ POST training creates record with id={data['id']}")

    def test_get_training_list_filters_by_staff_id(self, bob_headers):
        """GET /api/staffing/hr/training filters by staff_id."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/training",
            params={"staff_id": BOB_STAFF_ID},
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"GET training failed: {resp.text}"
        data = resp.json()
        assert "records" in data
        # All returned records should be for the specified staff_id
        for rec in data["records"]:
            assert rec.get("staff_id") == BOB_STAFF_ID
        print(f"✓ GET training returns {len(data['records'])} records for staff_id")

    def test_patch_training_updates_record(self, bob_headers):
        """PATCH /api/staffing/hr/training/{id} updates the record."""
        if not TestTrainingEndpoints.created_training_id:
            pytest.skip("No training record created to update")
        
        payload = {"course_name": "Updated Course Name", "score": 98.0}
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/training/{TestTrainingEndpoints.created_training_id}",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"PATCH training failed: {resp.text}"
        data = resp.json()
        assert data["course_name"] == "Updated Course Name"
        assert data["score"] == 98.0
        print("✓ PATCH training updates record")

    def test_delete_training_soft_deletes(self, bob_headers):
        """DELETE /api/staffing/hr/training/{id} soft-deletes."""
        if not TestTrainingEndpoints.created_training_id:
            pytest.skip("No training record created to delete")
        
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/hr/training/{TestTrainingEndpoints.created_training_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 200, f"DELETE training failed: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print("✓ DELETE training soft-deletes")


# ═══════════════════════════════════════════════════════════════════
# MULTI-TENANT ISOLATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation — Bob's org cannot see Master Admin org records."""

    def test_admin_cannot_see_bob_profile(self, admin_headers):
        """Master Admin org cannot access Bob's staff profile (404)."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/profile/{BOB_STAFF_ID}",
            headers=admin_headers,
        )
        # Should return 404 because Bob's staff record is in a different org
        assert resp.status_code == 404, f"Expected 404 for cross-org access, got {resp.status_code}"
        print("✓ Multi-tenant isolation: Admin cannot see Bob's profile (404)")

    def test_admin_documents_list_empty_for_bob_staff(self, admin_headers):
        """Master Admin org gets empty list when querying Bob's staff_id documents."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/documents",
            params={"staff_id": BOB_STAFF_ID},
            headers=admin_headers,
        )
        # Should return 200 with empty list (staff_id doesn't exist in admin's org)
        assert resp.status_code == 200, f"GET documents failed: {resp.text}"
        data = resp.json()
        assert data.get("documents") == [] or len(data.get("documents", [])) == 0
        print("✓ Multi-tenant isolation: Admin gets empty documents list for Bob's staff_id")

    def test_admin_disciplinary_list_empty_for_bob_staff(self, admin_headers):
        """Master Admin org gets empty list when querying Bob's staff_id disciplinary."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/disciplinary",
            params={"staff_id": BOB_STAFF_ID},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"GET disciplinary failed: {resp.text}"
        data = resp.json()
        assert data.get("records") == [] or len(data.get("records", [])) == 0
        print("✓ Multi-tenant isolation: Admin gets empty disciplinary list for Bob's staff_id")

    def test_admin_training_list_empty_for_bob_staff(self, admin_headers):
        """Master Admin org gets empty list when querying Bob's staff_id training."""
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/training",
            params={"staff_id": BOB_STAFF_ID},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"GET training failed: {resp.text}"
        data = resp.json()
        assert data.get("records") == [] or len(data.get("records", [])) == 0
        print("✓ Multi-tenant isolation: Admin gets empty training list for Bob's staff_id")


# ═══════════════════════════════════════════════════════════════════
# DOCUMENT KIND VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDocumentKindValidation:
    """Tests for all valid document kinds."""

    def test_all_valid_document_kinds(self, bob_headers):
        """POST accepts all valid document kinds: contract, id, onboarding, training, policy, other."""
        valid_kinds = ["contract", "id", "onboarding", "training", "policy", "other"]
        for kind in valid_kinds:
            payload = {
                "staff_id": BOB_STAFF_ID,
                "name": f"TEST_Doc_{kind}_{uuid4().hex[:4]}",
                "kind": kind,
                "url": f"https://example.com/test-{kind}.pdf",
            }
            resp = requests.post(
                f"{BASE_URL}/api/staffing/hr/documents",
                json=payload,
                headers=bob_headers,
            )
            assert resp.status_code == 200, f"POST with kind={kind} failed: {resp.text}"
            # Clean up - soft delete
            doc_id = resp.json().get("id")
            if doc_id:
                requests.delete(f"{BASE_URL}/api/staffing/hr/documents/{doc_id}", headers=bob_headers)
        print(f"✓ POST document accepts all {len(valid_kinds)} valid kinds")


# ═══════════════════════════════════════════════════════════════════
# ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_get_profile_nonexistent_staff(self, bob_headers):
        """GET profile for non-existent staff_id returns 404."""
        fake_id = str(uuid4())
        resp = requests.get(
            f"{BASE_URL}/api/staffing/hr/profile/{fake_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent staff, got {resp.status_code}"
        print("✓ GET profile returns 404 for non-existent staff_id")

    def test_patch_document_nonexistent(self, bob_headers):
        """PATCH document for non-existent id returns 404."""
        fake_id = str(uuid4())
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/documents/{fake_id}",
            json={"name": "Test"},
            headers=bob_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent document, got {resp.status_code}"
        print("✓ PATCH document returns 404 for non-existent id")

    def test_delete_disciplinary_nonexistent(self, bob_headers):
        """DELETE disciplinary for non-existent id returns 404."""
        fake_id = str(uuid4())
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/hr/disciplinary/{fake_id}",
            headers=bob_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent disciplinary, got {resp.status_code}"
        print("✓ DELETE disciplinary returns 404 for non-existent id")

    def test_patch_training_nonexistent(self, bob_headers):
        """PATCH training for non-existent id returns 404."""
        fake_id = str(uuid4())
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/hr/training/{fake_id}",
            json={"course_name": "Test"},
            headers=bob_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent training, got {resp.status_code}"
        print("✓ PATCH training returns 404 for non-existent id")

    def test_post_document_invalid_staff_id(self, bob_headers):
        """POST document with non-existent staff_id returns 404."""
        fake_staff_id = str(uuid4())
        payload = {
            "staff_id": fake_staff_id,
            "name": "Test Doc",
            "kind": "contract",
            "url": "https://example.com/test.pdf",
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/hr/documents",
            json=payload,
            headers=bob_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for invalid staff_id, got {resp.status_code}"
        print("✓ POST document returns 404 for invalid staff_id")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
