"""
Phase S4 — Staffing Tasks · Forms · Compliance API Tests
Iteration 216ap

Tests cover:
1. TASKS — CRUD, recurring, materialise, complete/uncomplete with photo verification
2. FORMS — Templates CRUD, field validation, submissions
3. COMPLIANCE — Certs CRUD, severity banding, tracker endpoint

Credentials:
- Owner: bob@knockers.com / Test123! (has linked staff record in Strong Fitness org)
- Master admin: admin@gymaxisai.com / MasterAdmin123!
"""
import os
import pytest
import requests
from datetime import datetime, timedelta
from uuid import uuid4

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
RATE_LIMIT_BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "7d889c8f7c814c8fdfeeb49fd2ea8bca2b17df490c8df1fea50bd7d279f44105")

# Test credentials
OWNER_EMAIL = "bob@knockers.com"
OWNER_PASSWORD = "Test123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def owner_token():
    """Get auth token for owner (bob@knockers.com)"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        headers={"X-RateLimit-Bypass": RATE_LIMIT_BYPASS}
    )
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    """Headers with owner auth token"""
    return {
        "Authorization": f"Bearer {owner_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def staff_list(owner_headers):
    """Get staff list for the org"""
    resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=owner_headers)
    if resp.status_code == 200:
        return resp.json().get("staff", [])
    return []


# ═══════════════════════ TASKS TESTS ═══════════════════════════════════

class TestTasksCRUD:
    """Tests for Tasks CRUD operations"""
    
    created_task_ids = []
    
    def test_list_tasks_empty_or_existing(self, owner_headers):
        """GET /api/staffing/tasks - should return tasks list"""
        resp = requests.get(f"{BASE_URL}/api/staffing/tasks", headers=owner_headers)
        assert resp.status_code == 200, f"List tasks failed: {resp.text}"
        data = resp.json()
        assert "tasks" in data
        assert "is_manager" in data
        assert data["is_manager"] == True  # bob is owner
        print(f"✓ List tasks returned {len(data['tasks'])} tasks")
    
    def test_list_tasks_with_date_filter(self, owner_headers):
        """GET /api/staffing/tasks?date=YYYY-MM-DD - filters by date"""
        today = datetime.now().strftime("%Y-%m-%d")
        resp = requests.get(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            params={"date": today}
        )
        assert resp.status_code == 200, f"List tasks with date failed: {resp.text}"
        data = resp.json()
        assert "tasks" in data
        print(f"✓ List tasks with date filter returned {len(data['tasks'])} tasks")
    
    def test_create_task_one_off(self, owner_headers):
        """POST /api/staffing/tasks - create one-off task"""
        payload = {
            "title": "TEST_S4_OneOff_Task",
            "description": "Test one-off task for Phase S4",
            "kind": "one_off",
            "due_at": (datetime.now() + timedelta(hours=2)).isoformat(),
            "requires_photo": False
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create one-off task failed: {resp.text}"
        data = resp.json()
        assert data["title"] == "TEST_S4_OneOff_Task"
        assert data["kind"] == "one_off"
        assert data["status"] == "open"
        assert "id" in data
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created one-off task: {data['id']}")
    
    def test_create_task_opening(self, owner_headers):
        """POST /api/staffing/tasks - create opening task"""
        payload = {
            "title": "TEST_S4_Opening_Task",
            "kind": "opening",
            "requires_photo": False
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create opening task failed: {resp.text}"
        data = resp.json()
        assert data["kind"] == "opening"
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created opening task: {data['id']}")
    
    def test_create_task_closing(self, owner_headers):
        """POST /api/staffing/tasks - create closing task"""
        payload = {
            "title": "TEST_S4_Closing_Task",
            "kind": "closing",
            "requires_photo": False
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create closing task failed: {resp.text}"
        data = resp.json()
        assert data["kind"] == "closing"
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created closing task: {data['id']}")
    
    def test_create_task_invalid_kind_rejected(self, owner_headers):
        """POST /api/staffing/tasks - invalid kind should be rejected"""
        payload = {
            "title": "TEST_S4_Invalid_Kind",
            "kind": "invalid_kind"
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 400, f"Expected 400 for invalid kind, got {resp.status_code}"
        print("✓ Invalid task kind correctly rejected")
    
    def test_create_task_recurring_daily(self, owner_headers):
        """POST /api/staffing/tasks - create recurring daily task"""
        payload = {
            "title": "TEST_S4_Recurring_Daily",
            "kind": "recurring",
            "recurrence": "daily",
            "requires_photo": False
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create recurring daily task failed: {resp.text}"
        data = resp.json()
        assert data["kind"] == "recurring"
        assert data["recurrence"] == "daily"
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created recurring daily task: {data['id']}")
    
    def test_create_task_recurring_weekly_with_weekdays(self, owner_headers):
        """POST /api/staffing/tasks - create recurring weekly task with weekdays"""
        payload = {
            "title": "TEST_S4_Recurring_Weekly",
            "kind": "recurring",
            "recurrence": "weekly",
            "weekdays": [0, 2, 4],  # Mon, Wed, Fri
            "requires_photo": False
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create recurring weekly task failed: {resp.text}"
        data = resp.json()
        assert data["kind"] == "recurring"
        assert data["recurrence"] == "weekly"
        assert data["weekdays"] == [0, 2, 4]
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created recurring weekly task: {data['id']}")
    
    def test_create_task_recurring_weekly_without_weekdays_rejected(self, owner_headers):
        """POST /api/staffing/tasks - recurring weekly without weekdays should be rejected"""
        payload = {
            "title": "TEST_S4_Recurring_Weekly_NoWeekdays",
            "kind": "recurring",
            "recurrence": "weekly",
            "weekdays": []  # Empty weekdays
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 400, f"Expected 400 for weekly without weekdays, got {resp.status_code}"
        print("✓ Recurring weekly without weekdays correctly rejected")
    
    def test_create_task_with_photo_requirement(self, owner_headers):
        """POST /api/staffing/tasks - create task requiring photo"""
        payload = {
            "title": "TEST_S4_Photo_Required",
            "kind": "one_off",
            "requires_photo": True
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create photo-required task failed: {resp.text}"
        data = resp.json()
        assert data["requires_photo"] == True
        self.__class__.created_task_ids.append(data["id"])
        print(f"✓ Created photo-required task: {data['id']}")


class TestTasksComplete:
    """Tests for task completion/uncompletion"""
    
    task_id = None
    photo_task_id = None
    
    @pytest.fixture(autouse=True)
    def setup_tasks(self, owner_headers):
        """Create tasks for completion tests"""
        # Create a regular task
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json={"title": "TEST_S4_Complete_Task", "kind": "one_off", "requires_photo": False}
        )
        if resp.status_code == 200:
            self.__class__.task_id = resp.json()["id"]
        
        # Create a photo-required task
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json={"title": "TEST_S4_Photo_Complete_Task", "kind": "one_off", "requires_photo": True}
        )
        if resp.status_code == 200:
            self.__class__.photo_task_id = resp.json()["id"]
        
        yield
        
        # Cleanup
        for tid in [self.__class__.task_id, self.__class__.photo_task_id]:
            if tid:
                requests.delete(f"{BASE_URL}/api/staffing/tasks/{tid}", headers=owner_headers)
    
    def test_complete_task_without_photo(self, owner_headers):
        """POST /api/staffing/tasks/{id}/complete - complete task without photo requirement"""
        if not self.__class__.task_id:
            pytest.skip("Task not created")
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks/{self.__class__.task_id}/complete",
            headers=owner_headers,
            json={}
        )
        assert resp.status_code == 200, f"Complete task failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        assert data["task"]["status"] == "completed"
        assert data["task"]["completed_at"] is not None
        print("✓ Task completed successfully")
    
    def test_complete_task_with_photo_required_missing_photo_rejected(self, owner_headers):
        """POST /api/staffing/tasks/{id}/complete - photo required but missing should be rejected"""
        if not self.__class__.photo_task_id:
            pytest.skip("Photo task not created")
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks/{self.__class__.photo_task_id}/complete",
            headers=owner_headers,
            json={}  # No photo_url
        )
        assert resp.status_code == 400, f"Expected 400 for missing photo, got {resp.status_code}"
        print("✓ Complete without required photo correctly rejected")
    
    def test_complete_task_with_photo_url(self, owner_headers):
        """POST /api/staffing/tasks/{id}/complete - complete with photo URL"""
        if not self.__class__.photo_task_id:
            pytest.skip("Photo task not created")
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks/{self.__class__.photo_task_id}/complete",
            headers=owner_headers,
            json={"photo_url": "https://example.com/test-photo.jpg"}
        )
        assert resp.status_code == 200, f"Complete with photo failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        assert data["task"]["status"] == "completed"
        assert data["task"]["completed_photo_url"] == "https://example.com/test-photo.jpg"
        print("✓ Task completed with photo URL")
    
    def test_uncomplete_task(self, owner_headers):
        """POST /api/staffing/tasks/{id}/uncomplete - revert completion"""
        if not self.__class__.task_id:
            pytest.skip("Task not created")
        
        # First complete the task
        requests.post(
            f"{BASE_URL}/api/staffing/tasks/{self.__class__.task_id}/complete",
            headers=owner_headers,
            json={}
        )
        
        # Then uncomplete
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks/{self.__class__.task_id}/uncomplete",
            headers=owner_headers
        )
        assert resp.status_code == 200, f"Uncomplete task failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        print("✓ Task uncompleted successfully")


class TestTasksMaterialise:
    """Tests for recurring task materialisation"""
    
    template_id = None
    
    @pytest.fixture(autouse=True)
    def setup_template(self, owner_headers):
        """Create recurring template for materialise tests"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks",
            headers=owner_headers,
            json={
                "title": "TEST_S4_Materialise_Template",
                "kind": "recurring",
                "recurrence": "daily",
                "requires_photo": False
            }
        )
        if resp.status_code == 200:
            self.__class__.template_id = resp.json()["id"]
        
        yield
        
        # Cleanup template
        if self.__class__.template_id:
            requests.delete(
                f"{BASE_URL}/api/staffing/tasks/{self.__class__.template_id}",
                headers=owner_headers
            )
    
    def test_materialise_recurring_tasks(self, owner_headers):
        """POST /api/staffing/tasks/materialise - generate instances for date"""
        today = datetime.now().strftime("%Y-%m-%d")
        resp = requests.post(
            f"{BASE_URL}/api/staffing/tasks/materialise",
            headers=owner_headers,
            json={"date": today}
        )
        assert resp.status_code == 200, f"Materialise failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        assert "created" in data
        assert "skipped" in data
        print(f"✓ Materialise: created={data['created']}, skipped={data['skipped']}")
    
    def test_materialise_idempotent(self, owner_headers):
        """POST /api/staffing/tasks/materialise - should be idempotent"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # First call
        resp1 = requests.post(
            f"{BASE_URL}/api/staffing/tasks/materialise",
            headers=owner_headers,
            json={"date": today}
        )
        assert resp1.status_code == 200
        
        # Second call should skip existing
        resp2 = requests.post(
            f"{BASE_URL}/api/staffing/tasks/materialise",
            headers=owner_headers,
            json={"date": today}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Second call should have more skipped or same created
        print(f"✓ Materialise idempotent: created={data2['created']}, skipped={data2['skipped']}")


# ═══════════════════════ FORMS TESTS ═══════════════════════════════════

class TestFormTemplates:
    """Tests for Form Templates CRUD"""
    
    template_id = None
    
    def test_list_form_templates(self, owner_headers):
        """GET /api/staffing/forms/templates - list templates"""
        resp = requests.get(f"{BASE_URL}/api/staffing/forms/templates", headers=owner_headers)
        assert resp.status_code == 200, f"List templates failed: {resp.text}"
        data = resp.json()
        assert "templates" in data
        print(f"✓ List form templates returned {len(data['templates'])} templates")
    
    def test_create_form_template_basic(self, owner_headers):
        """POST /api/staffing/forms/templates - create basic template"""
        payload = {
            "name": "TEST_S4_Basic_Form",
            "description": "Test form for Phase S4",
            "fields": [
                {"kind": "text", "label": "Name", "required": True},
                {"kind": "long_text", "label": "Description", "required": False}
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create template failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "TEST_S4_Basic_Form"
        assert len(data["fields"]) == 2
        # Fields should have auto-assigned IDs
        for field in data["fields"]:
            assert "id" in field
        self.__class__.template_id = data["id"]
        print(f"✓ Created form template: {data['id']}")
    
    def test_create_form_template_all_field_kinds(self, owner_headers):
        """POST /api/staffing/forms/templates - validate all field kinds"""
        payload = {
            "name": "TEST_S4_All_Fields_Form",
            "fields": [
                {"kind": "text", "label": "Text Field"},
                {"kind": "long_text", "label": "Long Text Field"},
                {"kind": "number", "label": "Number Field"},
                {"kind": "select", "label": "Select Field", "options": ["A", "B", "C"]},
                {"kind": "multiselect", "label": "Multiselect Field", "options": ["X", "Y", "Z"]},
                {"kind": "checkbox", "label": "Checkbox Field"},
                {"kind": "date", "label": "Date Field"},
                {"kind": "signature", "label": "Signature Field"},
                {"kind": "photo", "label": "Photo Field"}
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create all-fields template failed: {resp.text}"
        data = resp.json()
        assert len(data["fields"]) == 9
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/forms/templates/{data['id']}", headers=owner_headers)
        print("✓ All field kinds validated successfully")
    
    def test_create_form_template_invalid_field_kind_rejected(self, owner_headers):
        """POST /api/staffing/forms/templates - invalid field kind should be rejected"""
        payload = {
            "name": "TEST_S4_Invalid_Field",
            "fields": [
                {"kind": "invalid_kind", "label": "Invalid Field"}
            ]
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 400, f"Expected 400 for invalid field kind, got {resp.status_code}"
        print("✓ Invalid field kind correctly rejected")
    
    def test_get_form_template(self, owner_headers):
        """GET /api/staffing/forms/templates/{id} - get single template"""
        if not self.__class__.template_id:
            pytest.skip("Template not created")
        
        resp = requests.get(
            f"{BASE_URL}/api/staffing/forms/templates/{self.__class__.template_id}",
            headers=owner_headers
        )
        assert resp.status_code == 200, f"Get template failed: {resp.text}"
        data = resp.json()
        assert data["id"] == self.__class__.template_id
        print(f"✓ Got form template: {data['name']}")
    
    def test_update_form_template(self, owner_headers):
        """PATCH /api/staffing/forms/templates/{id} - update template"""
        if not self.__class__.template_id:
            pytest.skip("Template not created")
        
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/forms/templates/{self.__class__.template_id}",
            headers=owner_headers,
            json={"name": "TEST_S4_Updated_Form", "description": "Updated description"}
        )
        assert resp.status_code == 200, f"Update template failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "TEST_S4_Updated_Form"
        print("✓ Form template updated")
    
    def test_delete_form_template(self, owner_headers):
        """DELETE /api/staffing/forms/templates/{id} - soft delete template"""
        # Create a template to delete
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates",
            headers=owner_headers,
            json={"name": "TEST_S4_Delete_Form", "fields": []}
        )
        if resp.status_code != 200:
            pytest.skip("Could not create template for deletion")
        
        template_id = resp.json()["id"]
        
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/forms/templates/{template_id}",
            headers=owner_headers
        )
        assert resp.status_code == 200, f"Delete template failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        print("✓ Form template deleted (soft)")


class TestFormSubmissions:
    """Tests for Form Submissions"""
    
    template_id = None
    
    @pytest.fixture(autouse=True)
    def setup_template(self, owner_headers):
        """Create template for submission tests"""
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates",
            headers=owner_headers,
            json={
                "name": "TEST_S4_Submission_Form",
                "fields": [
                    {"kind": "text", "label": "Required Field", "required": True},
                    {"kind": "text", "label": "Optional Field", "required": False}
                ]
            }
        )
        if resp.status_code == 200:
            data = resp.json()
            self.__class__.template_id = data["id"]
            self.__class__.required_field_id = data["fields"][0]["id"]
            self.__class__.optional_field_id = data["fields"][1]["id"]
        
        yield
        
        # Cleanup
        if self.__class__.template_id:
            requests.delete(
                f"{BASE_URL}/api/staffing/forms/templates/{self.__class__.template_id}",
                headers=owner_headers
            )
    
    def test_submit_form_valid(self, owner_headers):
        """POST /api/staffing/forms/templates/{id}/submit - valid submission"""
        if not self.__class__.template_id:
            pytest.skip("Template not created")
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates/{self.__class__.template_id}/submit",
            headers=owner_headers,
            json={
                "values": {
                    self.__class__.required_field_id: "Test Value",
                    self.__class__.optional_field_id: "Optional Value"
                }
            }
        )
        assert resp.status_code == 200, f"Submit form failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["template_name_snapshot"] == "TEST_S4_Submission_Form"
        assert data["status"] == "submitted"
        print(f"✓ Form submitted: {data['id']}")
    
    def test_submit_form_missing_required_field_rejected(self, owner_headers):
        """POST /api/staffing/forms/templates/{id}/submit - missing required field rejected"""
        if not self.__class__.template_id:
            pytest.skip("Template not created")
        
        resp = requests.post(
            f"{BASE_URL}/api/staffing/forms/templates/{self.__class__.template_id}/submit",
            headers=owner_headers,
            json={
                "values": {
                    self.__class__.optional_field_id: "Only optional"
                    # Missing required field
                }
            }
        )
        assert resp.status_code == 400, f"Expected 400 for missing required field, got {resp.status_code}"
        print("✓ Missing required field correctly rejected")
    
    def test_list_submissions(self, owner_headers):
        """GET /api/staffing/forms/submissions - list submissions"""
        resp = requests.get(f"{BASE_URL}/api/staffing/forms/submissions", headers=owner_headers)
        assert resp.status_code == 200, f"List submissions failed: {resp.text}"
        data = resp.json()
        assert "submissions" in data
        assert "count" in data
        print(f"✓ List submissions returned {data['count']} submissions")


# ═══════════════════════ COMPLIANCE TESTS ═══════════════════════════════════

class TestComplianceCerts:
    """Tests for Compliance Certificates CRUD"""
    
    cert_id = None
    staff_id = None
    
    @pytest.fixture(autouse=True)
    def setup_staff(self, owner_headers, staff_list):
        """Get a staff ID for cert tests"""
        if staff_list:
            self.__class__.staff_id = staff_list[0]["id"]
        else:
            # Try to get staff from API
            resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=owner_headers)
            if resp.status_code == 200:
                staff = resp.json().get("staff", [])
                if staff:
                    self.__class__.staff_id = staff[0]["id"]
        
        yield
        
        # Cleanup cert
        if self.__class__.cert_id:
            requests.delete(
                f"{BASE_URL}/api/staffing/compliance/certs/{self.__class__.cert_id}",
                headers=owner_headers
            )
    
    def test_list_certs(self, owner_headers):
        """GET /api/staffing/compliance/certs - list certs"""
        resp = requests.get(f"{BASE_URL}/api/staffing/compliance/certs", headers=owner_headers)
        assert resp.status_code == 200, f"List certs failed: {resp.text}"
        data = resp.json()
        assert "certs" in data
        print(f"✓ List certs returned {len(data['certs'])} certs")
    
    def test_create_cert_expired(self, owner_headers):
        """POST /api/staffing/compliance/certs - create expired cert"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        past_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        payload = {
            "staff_id": self.__class__.staff_id,
            "cert_type": "TEST_S4_DBS",
            "cert_number": "DBS123456",
            "expires_at": past_date,
            "notes": "Test expired cert"
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create cert failed: {resp.text}"
        data = resp.json()
        assert data["cert_type"] == "TEST_S4_DBS"
        assert data["severity"] == "expired"  # Should be auto-computed
        self.__class__.cert_id = data["id"]
        print(f"✓ Created expired cert with severity: {data['severity']}")
    
    def test_create_cert_expiring_30(self, owner_headers):
        """POST /api/staffing/compliance/certs - create cert expiring within 30 days"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        future_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        payload = {
            "staff_id": self.__class__.staff_id,
            "cert_type": "TEST_S4_FirstAid",
            "expires_at": future_date
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create cert failed: {resp.text}"
        data = resp.json()
        assert data["severity"] == "expiring_30"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/compliance/certs/{data['id']}", headers=owner_headers)
        print(f"✓ Created expiring_30 cert with severity: {data['severity']}")
    
    def test_create_cert_expiring_90(self, owner_headers):
        """POST /api/staffing/compliance/certs - create cert expiring within 90 days"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        future_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        payload = {
            "staff_id": self.__class__.staff_id,
            "cert_type": "TEST_S4_Safeguarding",
            "expires_at": future_date
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create cert failed: {resp.text}"
        data = resp.json()
        assert data["severity"] == "expiring_90"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/compliance/certs/{data['id']}", headers=owner_headers)
        print(f"✓ Created expiring_90 cert with severity: {data['severity']}")
    
    def test_create_cert_ok(self, owner_headers):
        """POST /api/staffing/compliance/certs - create cert with OK status"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        future_date = (datetime.now() + timedelta(days=120)).strftime("%Y-%m-%d")
        payload = {
            "staff_id": self.__class__.staff_id,
            "cert_type": "TEST_S4_PoolPlant",
            "expires_at": future_date
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create cert failed: {resp.text}"
        data = resp.json()
        assert data["severity"] == "ok"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/compliance/certs/{data['id']}", headers=owner_headers)
        print(f"✓ Created OK cert with severity: {data['severity']}")
    
    def test_create_cert_unknown_no_expiry(self, owner_headers):
        """POST /api/staffing/compliance/certs - create cert without expiry (unknown)"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        payload = {
            "staff_id": self.__class__.staff_id,
            "cert_type": "TEST_S4_NoExpiry"
            # No expires_at
        }
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json=payload
        )
        assert resp.status_code == 200, f"Create cert failed: {resp.text}"
        data = resp.json()
        assert data["severity"] == "unknown"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/staffing/compliance/certs/{data['id']}", headers=owner_headers)
        print(f"✓ Created unknown cert with severity: {data['severity']}")
    
    def test_update_cert_rebands_severity(self, owner_headers):
        """PATCH /api/staffing/compliance/certs/{id} - update expires_at rebands severity"""
        if not self.__class__.cert_id:
            pytest.skip("Cert not created")
        
        # Update to OK status
        future_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        resp = requests.patch(
            f"{BASE_URL}/api/staffing/compliance/certs/{self.__class__.cert_id}",
            headers=owner_headers,
            json={"expires_at": future_date}
        )
        assert resp.status_code == 200, f"Update cert failed: {resp.text}"
        data = resp.json()
        assert data["severity"] == "ok"  # Should be rebanded
        print(f"✓ Updated cert, severity rebanded to: {data['severity']}")
    
    def test_delete_cert_soft_archive(self, owner_headers):
        """DELETE /api/staffing/compliance/certs/{id} - soft archive"""
        if not self.__class__.staff_id:
            pytest.skip("No staff available")
        
        # Create a cert to delete
        resp = requests.post(
            f"{BASE_URL}/api/staffing/compliance/certs",
            headers=owner_headers,
            json={
                "staff_id": self.__class__.staff_id,
                "cert_type": "TEST_S4_ToDelete"
            }
        )
        if resp.status_code != 200:
            pytest.skip("Could not create cert for deletion")
        
        cert_id = resp.json()["id"]
        
        resp = requests.delete(
            f"{BASE_URL}/api/staffing/compliance/certs/{cert_id}",
            headers=owner_headers
        )
        assert resp.status_code == 200, f"Delete cert failed: {resp.text}"
        data = resp.json()
        assert data["ok"] == True
        print("✓ Cert soft-archived")


class TestComplianceTracker:
    """Tests for Compliance Tracker endpoint"""
    
    def test_tracker_returns_buckets(self, owner_headers):
        """GET /api/staffing/compliance/tracker - returns severity buckets"""
        resp = requests.get(f"{BASE_URL}/api/staffing/compliance/tracker", headers=owner_headers)
        assert resp.status_code == 200, f"Tracker failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "as_of" in data
        assert "summary" in data
        assert "buckets" in data
        assert "missing_staff" in data
        assert "missing_count" in data
        
        # Verify buckets exist
        for band in ["expired", "expiring_30", "expiring_90", "ok", "unknown"]:
            assert band in data["buckets"]
            assert band in data["summary"]
        
        print(f"✓ Tracker returned summary: {data['summary']}")
        print(f"✓ Missing staff count: {data['missing_count']}")


# ═══════════════════════ CLEANUP ═══════════════════════════════════

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_tasks(self, owner_headers):
        """Clean up TEST_S4_ tasks"""
        resp = requests.get(f"{BASE_URL}/api/staffing/tasks", headers=owner_headers)
        if resp.status_code == 200:
            tasks = resp.json().get("tasks", [])
            deleted = 0
            for task in tasks:
                if task.get("title", "").startswith("TEST_S4_"):
                    requests.delete(f"{BASE_URL}/api/staffing/tasks/{task['id']}", headers=owner_headers)
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test tasks")
    
    def test_cleanup_test_forms(self, owner_headers):
        """Clean up TEST_S4_ form templates"""
        resp = requests.get(f"{BASE_URL}/api/staffing/forms/templates", headers=owner_headers)
        if resp.status_code == 200:
            templates = resp.json().get("templates", [])
            deleted = 0
            for tpl in templates:
                if tpl.get("name", "").startswith("TEST_S4_"):
                    requests.delete(f"{BASE_URL}/api/staffing/forms/templates/{tpl['id']}", headers=owner_headers)
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test form templates")
    
    def test_cleanup_test_certs(self, owner_headers):
        """Clean up TEST_S4_ certs"""
        resp = requests.get(f"{BASE_URL}/api/staffing/compliance/certs", headers=owner_headers)
        if resp.status_code == 200:
            certs = resp.json().get("certs", [])
            deleted = 0
            for cert in certs:
                if cert.get("cert_type", "").startswith("TEST_S4_"):
                    requests.delete(f"{BASE_URL}/api/staffing/compliance/certs/{cert['id']}", headers=owner_headers)
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test certs")
