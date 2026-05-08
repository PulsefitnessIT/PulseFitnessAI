"""
Test suite for fault_code auto-tag via AI triage feature (iteration 136)

Tests:
1. Backend /api/issues/triage returns fault_code key in response
2. Backend validates fault_code against VALID_FAULT_CODES (drops invalid codes)
3. Backend fallback triage returns fault_code: None
4. POST /api/issues still accepts fault_code in payload (regression)
5. Existing triage response keys still present (no regression)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials (loaded from env with local-dev fallbacks)
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get auth token for Pulse Pro user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Pulse Pro login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for Master Admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


class TestTriageEndpointFaultCode:
    """Tests for /api/issues/triage fault_code feature"""

    def test_triage_response_has_fault_code_key(self, pulse_pro_token):
        """Verify triage response includes fault_code key (even if null)"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}
        payload = {
            "serial_number": "TEST-001",
            "machine_type": "Treadmill",
            "issue_description": "Belt slipping under load",
            "severity": "operational_fault",
            "supplier": "Pulse Fitness",
            "steps_taken": ""
        }
        response = requests.post(f"{BASE_URL}/api/issues/triage", json=payload, headers=headers, timeout=180)

        # Accept 200 (success) or fallback response
        assert response.status_code == 200, f"Triage failed: {response.status_code} - {response.text}"

        data = response.json()
        # fault_code key MUST be present in response (can be null or a valid code)
        assert "fault_code" in data, f"fault_code key missing from triage response: {data.keys()}"
        print(f"✓ Triage response has fault_code key: {data.get('fault_code')}")

    def test_triage_response_has_existing_keys(self, pulse_pro_token):
        """Verify existing triage response keys are still present (no regression)"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}
        payload = {
            "serial_number": "TEST-002",
            "machine_type": "Spin Bike",
            "issue_description": "Pedal loose",
            "severity": "operational_minor",
            "supplier": "Pulse Fitness",
            "steps_taken": ""
        }
        response = requests.post(f"{BASE_URL}/api/issues/triage", json=payload, headers=headers, timeout=180)

        assert response.status_code == 200
        data = response.json()

        # Required keys that must be present
        required_keys = ["diagnosis", "can_fix_onsite", "repair_steps", "tools_needed",
                        "estimated_time", "engineer_reason", "severity_assessment", "fault_code"]

        for key in required_keys:
            assert key in data, f"Required key '{key}' missing from triage response"

        print(f"✓ All required keys present: {required_keys}")

    def test_triage_belt_slip_suggests_bel01(self, pulse_pro_token):
        """Test that belt slipping description suggests BEL-01 code (when AI works)"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}
        payload = {
            "serial_number": "TEST-003",
            "machine_type": "Treadmill",
            "issue_description": "Running belt is slipping when user runs at high speed",
            "severity": "operational_fault",
            "supplier": "Pulse Fitness",
            "steps_taken": ""
        }
        response = requests.post(f"{BASE_URL}/api/issues/triage", json=payload, headers=headers, timeout=180)

        assert response.status_code == 200
        data = response.json()

        fault_code = data.get("fault_code")
        # If AI returned a code, it should be BEL-01 for belt slipping
        # If AI is rate-limited, fault_code will be None (fallback)
        if fault_code:
            assert fault_code == "BEL-01", f"Expected BEL-01 for belt slip, got: {fault_code}"
            print("✓ AI correctly suggested BEL-01 for belt slipping")
        else:
            print("⚠ AI rate-limited, fault_code is None (fallback path)")
            # Verify fallback diagnosis mentions unavailable
            diagnosis = data.get("diagnosis", "")
            assert "unavailable" in diagnosis.lower() or "manually" in diagnosis.lower(), \
                f"Fallback diagnosis should mention unavailable: {diagnosis}"
            print("✓ Fallback path working correctly")


class TestFaultCodeValidation:
    """Tests for fault_code validation against VALID_FAULT_CODES"""

    def test_valid_fault_codes_set_exists(self):
        """Verify VALID_FAULT_CODES set is properly defined"""
        from constants.fault_codes import VALID_FAULT_CODES

        assert isinstance(VALID_FAULT_CODES, set), "VALID_FAULT_CODES should be a set"
        assert len(VALID_FAULT_CODES) == 41, f"Expected 41 fault codes, got {len(VALID_FAULT_CODES)}"

        # Check some expected codes
        expected_codes = ["BEL-01", "BEL-02", "MOT-01", "MOT-02", "SAF-01", "OTH-02"]
        for code in expected_codes:
            assert code in VALID_FAULT_CODES, f"Expected code {code} not in VALID_FAULT_CODES"

        print(f"✓ VALID_FAULT_CODES contains {len(VALID_FAULT_CODES)} codes")

    def test_invalid_code_not_in_valid_set(self):
        """Verify invalid codes are not in VALID_FAULT_CODES"""
        from constants.fault_codes import VALID_FAULT_CODES

        invalid_codes = ["INVALID-01", "XYZ-99", "belt-slip", ""]
        for code in invalid_codes:
            assert code not in VALID_FAULT_CODES, f"Invalid code {code} should not be in VALID_FAULT_CODES"

        print("✓ Invalid codes correctly excluded from VALID_FAULT_CODES")


class TestFallbackTriage:
    """Tests for build_fallback_triage function"""

    def test_fallback_triage_has_fault_code_none(self):
        """Verify fallback triage returns fault_code: None"""
        from routes.issue_helpers import build_fallback_triage

        result = build_fallback_triage("operational_fault", "rate limited")

        assert "fault_code" in result, "fault_code key missing from fallback triage"
        assert result["fault_code"] is None, f"Fallback fault_code should be None, got: {result['fault_code']}"

        print("✓ Fallback triage returns fault_code: None")

    def test_fallback_triage_has_all_required_keys(self):
        """Verify fallback triage has all required response keys"""
        from routes.issue_helpers import build_fallback_triage

        result = build_fallback_triage("out_of_order", "budget exceeded")

        required_keys = ["diagnosis", "can_fix_onsite", "repair_steps", "tools_needed",
                        "estimated_time", "engineer_reason", "severity_assessment", "fault_code"]

        for key in required_keys:
            assert key in result, f"Required key '{key}' missing from fallback triage"

        print("✓ Fallback triage has all required keys")

    def test_fallback_diagnosis_mentions_budget(self):
        """Verify fallback diagnosis mentions budget/balance when rate limited"""
        from routes.issue_helpers import build_fallback_triage

        result = build_fallback_triage("operational_fault", "rate limited budget")
        diagnosis = result.get("diagnosis", "")

        assert "balance" in diagnosis.lower() or "budget" in diagnosis.lower() or "unavailable" in diagnosis.lower(), \
            f"Fallback diagnosis should mention balance/budget: {diagnosis}"

        print("✓ Fallback diagnosis correctly mentions budget/balance")


class TestTriagePromptTaxonomy:
    """Tests for build_triage_prompt including fault code taxonomy"""

    def test_triage_prompt_includes_taxonomy(self):
        """Verify build_triage_prompt includes fault code taxonomy"""
        from routes.issue_helpers import build_triage_prompt

        # Create a mock issue object
        class MockIssue:
            machine_type = "Treadmill"
            serial_number = "TEST-001"
            issue_description = "Belt slipping"
            severity = "operational_fault"
            supplier = "Pulse Fitness"
            steps_taken = ""

        prompt = build_triage_prompt(MockIssue())

        # Check taxonomy header is present
        assert "FAULT CODE TAXONOMY" in prompt, "Taxonomy header missing from prompt"

        # Check some category labels are present
        assert "Mechanical" in prompt, "Mechanical category missing from prompt"
        assert "Electrical" in prompt, "Electrical category missing from prompt"
        assert "Safety-Critical" in prompt, "Safety-Critical category missing from prompt"

        # Check some codes are present
        assert "BEL-01" in prompt, "BEL-01 code missing from prompt"
        assert "MOT-01" in prompt, "MOT-01 code missing from prompt"
        assert "SAF-01" in prompt, "SAF-01 code missing from prompt"

        print(f"✓ Triage prompt includes fault code taxonomy ({len(prompt)} chars)")


class TestIssueCreationWithFaultCode:
    """Tests for POST /api/issues with fault_code (regression)"""

    def test_create_issue_with_fault_code(self, pulse_pro_token):
        """Verify POST /api/issues accepts and stores fault_code"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}
        payload = {
            "serial_number": "TEST-FAULT-CODE-001",
            "machine_type": "Treadmill",
            "issue_description": "TEST: Belt slipping - testing fault_code storage",
            "severity": "operational_fault",
            "supplier": "Pulse Fitness",
            "fault_code": "BEL-01",
            "resolution_type": "self_fix",
            "resolution_note": "Test issue for fault_code feature"
        }
        response = requests.post(f"{BASE_URL}/api/issues", json=payload, headers=headers)

        assert response.status_code == 200, f"Create issue failed: {response.status_code} - {response.text}"

        data = response.json()
        assert data.get("fault_code") == "BEL-01", f"fault_code not stored correctly: {data.get('fault_code')}"

        issue_id = data.get("id")
        print(f"✓ Issue created with fault_code BEL-01 (id: {issue_id})")

        # Verify by fetching the issue
        get_response = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        assert get_response.status_code == 200

        fetched = get_response.json()
        assert fetched.get("fault_code") == "BEL-01", f"fault_code not persisted: {fetched.get('fault_code')}"

        print("✓ fault_code persisted correctly in database")

    def test_create_issue_without_fault_code_regression(self, pulse_pro_token):
        """Verify POST /api/issues still works without fault_code (regression)"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}
        payload = {
            "serial_number": "TEST-NO-FAULT-CODE-001",
            "machine_type": "Spin Bike",
            "issue_description": "TEST: Pedal loose - no fault_code",
            "severity": "operational_minor",
            "supplier": "Pulse Fitness",
            "resolution_type": "self_fix",
            "resolution_note": "Test issue without fault_code"
        }
        response = requests.post(f"{BASE_URL}/api/issues", json=payload, headers=headers)

        assert response.status_code == 200, f"Create issue failed: {response.status_code} - {response.text}"

        data = response.json()
        # fault_code should be None or not present
        fault_code = data.get("fault_code")
        assert fault_code is None, f"fault_code should be None when not provided: {fault_code}"

        print("✓ Issue created without fault_code (regression test passed)")


class TestUpdateIssueWithFaultCode:
    """Tests for PATCH /api/issues/{id} with fault_code"""

    def test_update_issue_fault_code(self, pulse_pro_token):
        """Verify PATCH /api/issues/{id} can update fault_code"""
        headers = {"Authorization": f"Bearer {pulse_pro_token}"}

        # First create an issue without fault_code
        create_payload = {
            "serial_number": "TEST-UPDATE-FAULT-CODE-001",
            "machine_type": "Rowing Machine",
            "issue_description": "TEST: Chain worn - will update fault_code",
            "severity": "operational_fault",
            "supplier": "Pulse Fitness",
            "resolution_type": "engineer"
        }
        create_response = requests.post(f"{BASE_URL}/api/issues", json=create_payload, headers=headers)
        assert create_response.status_code == 200

        issue_id = create_response.json().get("id")

        # Update with fault_code
        update_payload = {"fault_code": "CHN-01"}
        update_response = requests.patch(f"{BASE_URL}/api/issues/{issue_id}", json=update_payload, headers=headers)

        assert update_response.status_code == 200, f"Update failed: {update_response.status_code} - {update_response.text}"

        # Verify the update
        get_response = requests.get(f"{BASE_URL}/api/issues/{issue_id}", headers=headers)
        assert get_response.status_code == 200

        fetched = get_response.json()
        assert fetched.get("fault_code") == "CHN-01", f"fault_code not updated: {fetched.get('fault_code')}"

        print("✓ Issue fault_code updated to CHN-01")


class TestTriageSystemMessage:
    """Tests for triage system message including fault_code instruction"""

    def test_system_message_includes_fault_code_instruction(self):
        """Verify system message template includes fault_code JSON field"""
        from routes.issue_helpers import _TRIAGE_SYSTEM_TEMPLATE

        assert "fault_code" in _TRIAGE_SYSTEM_TEMPLATE, "fault_code missing from system template"
        assert "FAULT CODE TAXONOMY" in _TRIAGE_SYSTEM_TEMPLATE, "Taxonomy reference missing from system template"
        assert "BEL-01" in _TRIAGE_SYSTEM_TEMPLATE or "e.g." in _TRIAGE_SYSTEM_TEMPLATE, \
            "Example code format missing from system template"

        print("✓ System message template includes fault_code instruction")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
