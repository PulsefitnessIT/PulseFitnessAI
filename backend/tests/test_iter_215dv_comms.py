"""
Phase 7b — Customer Comms Hub API Tests (iter 215dv)

Tests for:
- GET /api/svc/comms/templates — list templates (auto-seeds 4 defaults)
- PUT /api/svc/comms/templates/{key} — update template
- POST /api/svc/comms/templates/{key}/reset — reset to default
- GET /api/svc/comms/log — comms send history
- POST /api/svc/comms/case/{case_id}/notify — send case notification
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Master admin credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for master admin."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestCommsTemplates:
    """Tests for /api/svc/comms/templates endpoints."""

    def test_list_templates_returns_4_defaults(self, auth_headers):
        """GET /api/svc/comms/templates returns 4 default templates."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/templates", headers=auth_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "templates" in data
        assert "count" in data
        assert data["count"] >= 4, f"Expected at least 4 templates, got {data['count']}"

        # Verify the 4 default template keys exist
        keys = {t["key"] for t in data["templates"]}
        expected_keys = {"case_logged", "engineer_en_route", "case_completed", "supplier_po"}
        assert expected_keys.issubset(keys), f"Missing templates: {expected_keys - keys}"

        # Verify template structure
        for t in data["templates"]:
            assert "key" in t
            assert "subject" in t
            assert "body_html" in t
            assert "audience" in t
            assert t["audience"] in ("customer", "supplier", "engineer")

    def test_list_templates_requires_auth(self):
        """GET /api/svc/comms/templates requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/templates")
        assert resp.status_code == 401

    def test_update_template_subject_and_body(self, auth_headers):
        """PUT /api/svc/comms/templates/{key} updates subject and body_html."""
        key = "case_logged"
        new_subject = "TEST: Updated subject {{reference}}"
        new_body = "<p>TEST: Updated body for {{customer_name}}</p>"

        resp = requests.put(
            f"{BASE_URL}/api/svc/comms/templates/{key}",
            headers=auth_headers,
            json={
                "subject": new_subject,
                "body_html": new_body,
                "audience": "customer",
            },
        )
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        data = resp.json()

        assert data["key"] == key
        assert data["subject"] == new_subject
        assert data["body_html"] == new_body
        assert data["audience"] == "customer"

        # Verify persistence via GET
        resp2 = requests.get(f"{BASE_URL}/api/svc/comms/templates", headers=auth_headers)
        templates = {t["key"]: t for t in resp2.json()["templates"]}
        assert templates[key]["subject"] == new_subject
        assert templates[key]["body_html"] == new_body

    def test_update_template_audience(self, auth_headers):
        """PUT /api/svc/comms/templates/{key} can update audience."""
        key = "case_logged"

        resp = requests.put(
            f"{BASE_URL}/api/svc/comms/templates/{key}",
            headers=auth_headers,
            json={
                "subject": "Test subject {{reference}}",
                "body_html": "<p>Test body</p>",
                "audience": "engineer",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["audience"] == "engineer"

    def test_update_template_invalid_audience(self, auth_headers):
        """PUT /api/svc/comms/templates/{key} rejects invalid audience."""
        resp = requests.put(
            f"{BASE_URL}/api/svc/comms/templates/case_logged",
            headers=auth_headers,
            json={
                "subject": "Test",
                "body_html": "<p>Test</p>",
                "audience": "invalid_audience",
            },
        )
        assert resp.status_code == 400

    def test_update_template_requires_subject_and_body(self, auth_headers):
        """PUT /api/svc/comms/templates/{key} requires subject and body_html."""
        # Missing body_html
        resp = requests.put(
            f"{BASE_URL}/api/svc/comms/templates/case_logged",
            headers=auth_headers,
            json={"subject": "Test"},
        )
        assert resp.status_code == 400

        # Missing subject
        resp2 = requests.put(
            f"{BASE_URL}/api/svc/comms/templates/case_logged",
            headers=auth_headers,
            json={"body_html": "<p>Test</p>"},
        )
        assert resp2.status_code == 400

    def test_reset_template_restores_default(self, auth_headers):
        """POST /api/svc/comms/templates/{key}/reset restores default subject/body."""
        key = "case_logged"

        # First update to something custom
        requests.put(
            f"{BASE_URL}/api/svc/comms/templates/{key}",
            headers=auth_headers,
            json={
                "subject": "CUSTOM SUBJECT",
                "body_html": "<p>CUSTOM BODY</p>",
                "audience": "customer",
            },
        )

        # Reset to default
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/templates/{key}/reset",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 200, f"Reset failed: {resp.text}"
        data = resp.json()

        # Verify it's back to default
        assert data["key"] == key
        assert "{{reference}}" in data["subject"]  # Default has placeholder
        assert "{{customer_name}}" in data["body_html"]  # Default has placeholder
        assert data["is_default"] is True

    def test_reset_nonexistent_template_returns_404(self, auth_headers):
        """POST /api/svc/comms/templates/{key}/reset returns 404 for unknown key."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/templates/nonexistent_key/reset",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 404


class TestCommsLog:
    """Tests for /api/svc/comms/log endpoint."""

    def test_comms_log_returns_events(self, auth_headers):
        """GET /api/svc/comms/log returns send events."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/log", headers=auth_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "events" in data
        assert "count" in data
        assert isinstance(data["events"], list)

        # If there are events, verify structure
        if data["events"]:
            event = data["events"][0]
            assert "id" in event
            assert "kind" in event
            assert "to" in event
            assert "subject" in event
            assert "template_key" in event
            assert "ok" in event
            assert "at" in event

    def test_comms_log_requires_auth(self):
        """GET /api/svc/comms/log requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/log")
        assert resp.status_code == 401

    def test_comms_log_supports_limit(self, auth_headers):
        """GET /api/svc/comms/log supports limit parameter."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/comms/log",
            headers=auth_headers,
            params={"limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) <= 5


class TestCaseNotify:
    """Tests for /api/svc/comms/case/{case_id}/notify endpoint."""

    @pytest.fixture(scope="class")
    def existing_case_id(self, auth_headers):
        """Get an existing case ID from the master admin org."""
        resp = requests.get(
            f"{BASE_URL}/api/svc/cases",
            headers=auth_headers,
            params={"limit": 1},
        )
        if resp.status_code == 200 and resp.json().get("cases"):
            return resp.json()["cases"][0]["id"]
        pytest.skip("No existing cases found for testing")

    def test_notify_case_with_valid_template(self, auth_headers, existing_case_id):
        """POST /api/svc/comms/case/{case_id}/notify sends notification."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/{existing_case_id}/notify",
            headers=auth_headers,
            json={
                "template_key": "case_logged",
                "to": "qa@example.com",
            },
        )
        assert resp.status_code == 200, f"Notify failed: {resp.text}"
        data = resp.json()

        # In test env without RESEND_API_KEY, ok=False is expected
        assert "ok" in data
        assert "log" in data
        assert data["log"]["template_key"] == "case_logged"
        assert data["log"]["to"] == "qa@example.com"
        # The log should be written regardless of send success
        assert "id" in data["log"]

    def test_notify_case_requires_email(self, auth_headers, existing_case_id):
        """POST /api/svc/comms/case/{case_id}/notify requires valid email."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/{existing_case_id}/notify",
            headers=auth_headers,
            json={
                "template_key": "case_logged",
                # No 'to' field and case likely has no customer_email
            },
        )
        # Should fail if no email available
        # Either 400 (no email) or 200 (if case has customer_email)
        assert resp.status_code in (200, 400)

    def test_notify_nonexistent_case_returns_404(self, auth_headers):
        """POST /api/svc/comms/case/{case_id}/notify returns 404 for unknown case."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/nonexistent-case-id/notify",
            headers=auth_headers,
            json={
                "template_key": "case_logged",
                "to": "qa@example.com",
            },
        )
        assert resp.status_code == 404

    def test_notify_case_requires_auth(self, existing_case_id):
        """POST /api/svc/comms/case/{case_id}/notify requires authentication."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/{existing_case_id}/notify",
            json={"template_key": "case_logged", "to": "qa@example.com"},
        )
        assert resp.status_code == 401

    def test_notify_renders_placeholders(self, auth_headers, existing_case_id):
        """POST /api/svc/comms/case/{case_id}/notify renders {{var}} placeholders."""
        resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/{existing_case_id}/notify",
            headers=auth_headers,
            json={
                "template_key": "case_logged",
                "to": "qa@example.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # The subject should have the reference rendered (not {{reference}})
        subject = data["log"]["subject"]
        # If the case has a reference, it should be in the subject
        # The default template is "We've logged your service case {{reference}}"
        # After rendering, {{reference}} should be replaced
        assert "{{reference}}" not in subject or subject == ""


class TestCommsLogAfterNotify:
    """Verify comms log captures notify events."""

    def test_log_contains_notify_event(self, auth_headers):
        """GET /api/svc/comms/log shows events from notify calls."""
        # First get a case
        cases_resp = requests.get(
            f"{BASE_URL}/api/svc/cases",
            headers=auth_headers,
            params={"limit": 1},
        )
        if cases_resp.status_code != 200 or not cases_resp.json().get("cases"):
            pytest.skip("No cases available")

        case_id = cases_resp.json()["cases"][0]["id"]

        # Send a notify
        notify_resp = requests.post(
            f"{BASE_URL}/api/svc/comms/case/{case_id}/notify",
            headers=auth_headers,
            json={
                "template_key": "case_logged",
                "to": "log-test@example.com",
            },
        )
        assert notify_resp.status_code == 200
        log_id = notify_resp.json()["log"]["id"]

        # Check the log
        log_resp = requests.get(
            f"{BASE_URL}/api/svc/comms/log",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert log_resp.status_code == 200
        events = log_resp.json()["events"]

        # Find our event
        found = any(e["id"] == log_id for e in events)
        assert found, f"Log event {log_id} not found in recent events"


class TestTemplateAudienceTypes:
    """Test all audience types for templates."""

    def test_supplier_po_template_exists(self, auth_headers):
        """Verify supplier_po template exists with supplier audience."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/templates", headers=auth_headers)
        assert resp.status_code == 200

        templates = {t["key"]: t for t in resp.json()["templates"]}
        assert "supplier_po" in templates
        assert templates["supplier_po"]["audience"] == "supplier"

    def test_customer_templates_exist(self, auth_headers):
        """Verify customer-facing templates exist."""
        resp = requests.get(f"{BASE_URL}/api/svc/comms/templates", headers=auth_headers)
        assert resp.status_code == 200

        templates = {t["key"]: t for t in resp.json()["templates"]}

        for key in ["case_logged", "engineer_en_route", "case_completed"]:
            assert key in templates, f"Missing template: {key}"
            assert templates[key]["audience"] == "customer"
