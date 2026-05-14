"""
Test suite for Partner Engineer Public Application (iter 216h104)
Tests:
- POST /api/partners/public-apply (public, no auth)
- GET /api/partners/applications (master admin only)
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Master admin credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def master_admin_token(api_client):
    """Get master admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Master admin authentication failed")


@pytest.fixture
def authenticated_admin_client(api_client, master_admin_token):
    """Session with master admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {master_admin_token}"})
    return api_client


class TestPublicPartnerApplication:
    """Tests for POST /api/partners/public-apply (PUBLIC endpoint - no auth)"""
    
    def test_public_apply_missing_full_name(self):
        """Missing full_name should return 400 or 422"""
        # Use requests directly without Content-Type header for multipart
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "",
                "email": "test@example.com",
                "terms_accepted": "true"
            }
        )
        # FastAPI returns 422 for validation errors, 400 for business logic errors
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}: {response.text}"
        print("✓ Missing full_name returns 400/422")
    
    def test_public_apply_invalid_email(self):
        """Invalid email should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "Test Engineer",
                "email": "invalid-email",
                "terms_accepted": "true"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "email" in response.text.lower()
        print("✓ Invalid email returns 400")
    
    def test_public_apply_terms_not_accepted(self):
        """terms_accepted not true should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "Test Engineer",
                "email": "test.terms@example.com",
                "terms_accepted": "false"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "terms" in response.text.lower()
        print("✓ terms_accepted=false returns 400")
    
    def test_public_apply_valid_payload(self):
        """Valid payload should return success with application_id"""
        import uuid
        unique_email = f"test.engineer.{uuid.uuid4().hex[:8]}@example.com"
        
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "TEST_Public Engineer",
                "email": unique_email,
                "phone": "+447700900123",
                "company_name": "TEST_Engineering Ltd",
                "service_postcode": "SW1A 1AA",
                "travel_radius_km": "30",
                "brands_supported": "Life Fitness, Technogym",
                "skills": "cardio, strength, electrical",
                "qualifications": "IOSH, PAT, CSCS",
                "years_experience": "5",
                "has_insurance": "true",
                "insurance_provider": "Hiscox",
                "referral_source": "Google",
                "cover_letter": "I am an experienced fitness engineer.",
                "terms_accepted": "true"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") is True
        assert "application_id" in data
        assert data.get("status") == "pending"
        print(f"✓ Valid application created: {data.get('application_id')}")
        return data
    
    def test_public_apply_idempotent_resubmit(self):
        """Resubmitting with same email should update existing application"""
        import uuid
        unique_email = f"test.resubmit.{uuid.uuid4().hex[:8]}@example.com"
        
        # First submission
        response1 = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "TEST_First Submission",
                "email": unique_email,
                "terms_accepted": "true"
            }
        )
        assert response1.status_code == 200
        data1 = response1.json()
        app_id = data1.get("application_id")
        
        # Second submission with same email
        response2 = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "TEST_Updated Name",
                "email": unique_email,
                "phone": "+447700900999",
                "terms_accepted": "true"
            }
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("resubmitted") is True
        assert data2.get("application_id") == app_id  # Same application ID
        print(f"✓ Idempotent resubmit works: {app_id}")
    
    def test_public_apply_with_cv_file(self):
        """CV file upload should work"""
        import uuid
        unique_email = f"test.cv.{uuid.uuid4().hex[:8]}@example.com"
        
        # Create a small test file
        cv_content = b"This is a test CV content for testing purposes."
        files = {
            'cv_file': ('test_cv.txt', io.BytesIO(cv_content), 'text/plain')
        }
        data = {
            "full_name": "TEST_CV Upload Engineer",
            "email": unique_email,
            "terms_accepted": "true"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data=data,
            files=files
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert result.get("ok") is True
        print(f"✓ CV file upload works: {result.get('application_id')}")
        return result.get("application_id")
    
    def test_public_apply_file_too_large(self):
        """File >10MB should return 400 or 413"""
        import uuid
        unique_email = f"test.large.{uuid.uuid4().hex[:8]}@example.com"
        
        # Create a file larger than 10MB
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {
            'cv_file': ('large_file.txt', io.BytesIO(large_content), 'text/plain')
        }
        data = {
            "full_name": "TEST_Large File Engineer",
            "email": unique_email,
            "terms_accepted": "true"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data=data,
            files=files
        )
        # Accept both 400 and 413 (Request Entity Too Large)
        assert response.status_code in [400, 413], f"Expected 400/413 for large file, got {response.status_code}"
        print("✓ File >10MB returns 400/413")
    
    def test_public_apply_unsupported_extension(self):
        """Unsupported file extension (.exe) should return 400"""
        import uuid
        unique_email = f"test.exe.{uuid.uuid4().hex[:8]}@example.com"
        
        files = {
            'cv_file': ('malicious.exe', io.BytesIO(b"fake exe content"), 'application/octet-stream')
        }
        data = {
            "full_name": "TEST_Exe File Engineer",
            "email": unique_email,
            "terms_accepted": "true"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data=data,
            files=files
        )
        assert response.status_code == 400, f"Expected 400 for .exe file, got {response.status_code}"
        assert "unsupported" in response.text.lower() or "type" in response.text.lower()
        print("✓ Unsupported extension (.exe) returns 400")


class TestPartnerApplicationsAdmin:
    """Tests for GET /api/partners/applications (master admin only)"""
    
    def test_applications_requires_auth(self, api_client):
        """GET /api/partners/applications without auth should return 401/403"""
        response = api_client.get(f"{BASE_URL}/api/partners/applications")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ GET /api/partners/applications requires auth")
    
    def test_applications_master_admin_access(self, authenticated_admin_client):
        """Master admin should be able to list applications"""
        response = authenticated_admin_client.get(f"{BASE_URL}/api/partners/applications")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "applications" in data
        assert "total" in data
        assert isinstance(data["applications"], list)
        print(f"✓ Master admin can list applications: {data['total']} total")
    
    def test_applications_includes_test_data(self, authenticated_admin_client):
        """Applications list should include recently created test applications"""
        import uuid
        unique_email = f"test.verify.{uuid.uuid4().hex[:8]}@example.com"
        
        # Create a test application first (using requests directly for multipart)
        create_response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data={
                "full_name": "TEST_Verify Application",
                "email": unique_email,
                "terms_accepted": "true"
            }
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        app_id = create_response.json().get("application_id")
        
        # Now verify it appears in the admin list
        list_response = authenticated_admin_client.get(f"{BASE_URL}/api/partners/applications")
        assert list_response.status_code == 200
        data = list_response.json()
        
        # Find our application
        found = any(app.get("id") == app_id for app in data["applications"])
        assert found, f"Application {app_id} not found in admin list"
        print(f"✓ Created application {app_id} appears in admin list")
    
    def test_applications_with_attachments(self, authenticated_admin_client):
        """Applications with CV uploads should show attachments in admin view"""
        import uuid
        unique_email = f"test.attach.{uuid.uuid4().hex[:8]}@example.com"
        
        # Create application with CV
        cv_content = b"Test CV content for attachment verification"
        files = {
            'cv_file': ('test_cv.pdf', io.BytesIO(cv_content), 'application/pdf')
        }
        data = {
            "full_name": "TEST_Attachment Verify",
            "email": unique_email,
            "terms_accepted": "true"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/partners/public-apply",
            data=data,
            files=files
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        app_id = create_response.json().get("application_id")
        
        # Verify attachments in admin list
        list_response = authenticated_admin_client.get(f"{BASE_URL}/api/partners/applications")
        assert list_response.status_code == 200
        apps = list_response.json()["applications"]
        
        app = next((a for a in apps if a.get("id") == app_id), None)
        assert app is not None, f"Application {app_id} not found"
        assert "attachments" in app
        assert len(app["attachments"]) > 0
        assert app["attachments"][0].get("kind") == "cv"
        print(f"✓ Application {app_id} has attachments visible in admin view")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
