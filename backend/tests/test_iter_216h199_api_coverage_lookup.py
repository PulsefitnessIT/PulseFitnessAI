"""Iter 216h199 — Phase 3 API-level tests for auto-warranty-check.

Tests the HTTP endpoints:
  • GET /api/issues/coverage-lookup?serial_number=X
  • GET /api/equipment/{id}/coverage (regression)
  • POST /api/issues (coverage_meta stamping)
  • POST /api/issues/batch (coverage_meta stamping)

Run: pytest backend/tests/test_iter_216h199_api_coverage_lookup.py -v
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin JWT for authenticated requests."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def e1_token():
    """Get E1 agent JWT for authenticated requests."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "e1.agent@gymaxisai.com", "password": "E1Agent123!"},
    )
    if resp.status_code != 200:
        pytest.skip(f"E1 login failed: {resp.status_code} {resp.text}")
    return resp.json().get("token")


class TestCoverageLookupEndpoint:
    """GET /api/issues/coverage-lookup?serial_number=X"""

    def test_coverage_lookup_returns_400_when_serial_empty(self, e1_token):
        """Empty serial_number should return 400."""
        resp = requests.get(
            f"{BASE_URL}/api/issues/coverage-lookup",
            params={"serial_number": ""},
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "serial_number" in data.get("detail", "").lower() or "required" in data.get("detail", "").lower()

    def test_coverage_lookup_returns_400_when_serial_missing(self, e1_token):
        """Missing serial_number param should return 400."""
        resp = requests.get(
            f"{BASE_URL}/api/issues/coverage-lookup",
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        # FastAPI may return 422 for missing required param or 400 if handled
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"

    def test_coverage_lookup_unknown_serial_returns_uncovered(self, e1_token):
        """Unknown serial should return uncovered meta, NOT 500."""
        resp = requests.get(
            f"{BASE_URL}/api/issues/coverage-lookup",
            params={"serial_number": "GHOST-SERIAL-DOES-NOT-EXIST-12345"},
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify the coverage_to_case_meta shape
        assert data.get("coverage_status") == "uncovered"
        assert data.get("cover_type") == "chargeable"
        assert data.get("contract_id") == ""
        assert data.get("warranty_active") is False

    def test_coverage_lookup_returns_full_meta_shape(self, e1_token):
        """Verify the response contains all expected keys."""
        resp = requests.get(
            f"{BASE_URL}/api/issues/coverage-lookup",
            params={"serial_number": "ANY-SERIAL"},
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # All keys from coverage_to_case_meta should be present
        expected_keys = [
            "cover_type", "coverage_status", "contract_id", "contract_number",
            "contract_title", "contract_tier", "contract_end_date",
            "contract_coverage_type", "contract_expiring_soon",
            "warranty_active", "warranty_expiry", "warranty_days_remaining",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"


class TestEquipmentCoverageRegression:
    """GET /api/equipment/{id}/coverage — regression test for iter h198."""

    def test_equipment_coverage_returns_crm_coverage_dict(self, e1_token):
        """Verify the endpoint still returns crm_coverage after refactor."""
        # First get an equipment ID from the org
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        if resp.status_code != 200:
            pytest.skip(f"Equipment list failed: {resp.status_code}")
        equipment_list = resp.json().get("equipment", [])
        if not equipment_list:
            pytest.skip("No equipment in org to test coverage endpoint")

        equip_id = equipment_list[0]["id"]
        resp = requests.get(
            f"{BASE_URL}/api/equipment/{equip_id}/coverage",
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Legacy keys preserved
        assert "equipment_id" in data
        assert "covered" in data
        assert "warranty_active" in data
        # New crm_coverage dict from h198
        assert "crm_coverage" in data
        crm = data["crm_coverage"]
        assert "has_coverage" in crm
        assert "best" in crm
        assert "all_contracts" in crm

    def test_equipment_coverage_returns_404_for_missing(self, e1_token):
        """Non-existent equipment ID should return 404."""
        resp = requests.get(
            f"{BASE_URL}/api/equipment/nonexistent-id-12345/coverage",
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 404


class TestIssueCreateCoverageMeta:
    """POST /api/issues — verify coverage_meta is stamped."""

    def test_create_issue_stamps_coverage_meta(self, e1_token):
        """Issue created with resolution_type='engineer' should have coverage_meta."""
        import uuid
        payload = {
            "serial_number": f"TEST-SERIAL-{uuid.uuid4().hex[:8]}",
            "machine_type": "Treadmill",
            "issue_description": "Test issue for coverage_meta verification",
            "severity": "operational_minor",
            "resolution_type": "engineer",
            "steps_taken": "None",
        }
        resp = requests.post(
            f"{BASE_URL}/api/issues",
            json=payload,
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify coverage_meta is present
        assert "coverage_meta" in data, "coverage_meta should be stamped on issue"
        meta = data["coverage_meta"]
        # Since the serial is fake, it should be uncovered
        assert meta.get("coverage_status") == "uncovered"
        assert meta.get("cover_type") == "chargeable"

    def test_create_issue_self_fix_also_has_coverage_meta(self, e1_token):
        """Even self_fix issues should have coverage_meta stamped."""
        import uuid
        payload = {
            "serial_number": f"TEST-SERIAL-{uuid.uuid4().hex[:8]}",
            "machine_type": "Bike",
            "issue_description": "Self-fixed issue",
            "severity": "operational_minor",
            "resolution_type": "self_fix",
            "steps_taken": "Rebooted",
        }
        resp = requests.post(
            f"{BASE_URL}/api/issues",
            json=payload,
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "coverage_meta" in data


class TestIssuesBatchCoverageMeta:
    """POST /api/issues/batch — verify each issue gets coverage_meta."""

    def test_batch_issues_each_has_coverage_meta(self, e1_token):
        """Each issue in a batch should have its own coverage_meta."""
        import uuid
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        payload = {
            "job_id": job_id,
            "machines": [
                {
                    "serial_number": f"BATCH-A-{uuid.uuid4().hex[:6]}",
                    "machine_type": "Treadmill",
                    "issue_description": "Belt slipping",
                    "severity": "operational_major",
                    "resolution_type": "engineer",
                },
                {
                    "serial_number": f"BATCH-B-{uuid.uuid4().hex[:6]}",
                    "machine_type": "Bike",
                    "issue_description": "Pedal loose",
                    "severity": "operational_minor",
                    "resolution_type": "engineer",
                },
            ],
        }
        resp = requests.post(
            f"{BASE_URL}/api/issues/batch",
            json=payload,
            headers={"Authorization": f"Bearer {e1_token}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "issues" in data
        assert len(data["issues"]) == 2
        for issue in data["issues"]:
            assert "coverage_meta" in issue, f"Issue {issue.get('id')} missing coverage_meta"
            meta = issue["coverage_meta"]
            assert "cover_type" in meta
            assert "coverage_status" in meta


class TestCRMAuthRegressions:
    """Regression tests for iter h192-h198 endpoints."""

    def test_crm_login_fallback_works(self, admin_token):
        """POST /api/crm/auth/login should work for CRM users."""
        # This is a regression test — just verify the endpoint exists and responds
        resp = requests.post(
            f"{BASE_URL}/api/crm/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        )
        # May return 200 (success) or 401 (not a CRM user) — both are valid
        assert resp.status_code in (200, 401, 403), f"Unexpected status: {resp.status_code}"

    def test_crm_cross_login_works(self, admin_token):
        """POST /api/crm/auth/cross-login should exchange JWT for CRM token."""
        resp = requests.post(
            f"{BASE_URL}/api/crm/auth/cross-login",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Master admin should be able to cross-login
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data
