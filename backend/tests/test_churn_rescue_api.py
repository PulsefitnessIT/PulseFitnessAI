"""API endpoint tests for Churn Rescue feature.

Tests all 6 churn endpoints:
- GET /api/marketing/creative/director/churn-risk/scan
- POST /api/marketing/creative/director/churn-risk/generate
- GET /api/marketing/creative/director/churn-risk/queue
- POST /api/marketing/creative/director/churn-risk/{id}/approve
- POST /api/marketing/creative/director/churn-risk/{id}/reject
- POST /api/marketing/creative/director/churn-risk/{id}/refine
- POST /api/marketing/creative/director/churn-risk/approve-bulk

Run: cd /app/backend && python -m pytest tests/test_churn_rescue_api.py -v
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for local testing
    BASE_URL = "https://aftersales-engine-1.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for master admin."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    data = resp.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def operator_token():
    """Get auth token for Tottenham operator."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text[:200]}")
    data = resp.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


class TestChurnRiskScan:
    """Tests for GET /api/marketing/creative/director/churn-risk/scan"""

    def test_scan_requires_auth(self):
        """Scan endpoint should return 401 without auth token."""
        resp = requests.get(f"{BASE_URL}/api/marketing/creative/director/churn-risk/scan")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_scan_returns_200_with_correct_structure(self, admin_headers):
        """Scan should return 200 with targets, count, signal_labels, scanned_at."""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/scan?limit=50",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()

        # Validate response structure
        assert "targets" in data, "Response missing 'targets'"
        assert "count" in data, "Response missing 'count'"
        assert "signal_labels" in data, "Response missing 'signal_labels'"
        assert "scanned_at" in data, "Response missing 'scanned_at'"

        # Validate signal_labels contains all 6 keys
        expected_signals = {
            "payment_failure", "frozen_membership", "late_cancel_streak",
            "class_affinity_drop", "frequency_drop", "lapsed_visit"
        }
        actual_signals = set(data["signal_labels"].keys())
        assert expected_signals == actual_signals, (
            f"signal_labels missing keys. Expected {expected_signals}, got {actual_signals}"
        )

    def test_scan_with_operator_token(self, operator_headers):
        """Operator should also be able to scan (Tottenham org may have empty targets)."""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/scan?limit=50",
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "targets" in data
        assert "signal_labels" in data


class TestChurnRiskGenerate:
    """Tests for POST /api/marketing/creative/director/churn-risk/generate"""

    def test_generate_requires_auth(self):
        """Generate endpoint should return 401 without auth token."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/generate",
            json={"member_ids": ["test-id"]}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_generate_empty_member_ids_returns_400(self, admin_headers):
        """Generate with empty member_ids should return 400."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/generate",
            headers=admin_headers,
            json={"member_ids": []}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "member_ids is required" in data.get("detail", ""), (
            f"Expected 'member_ids is required' in detail, got: {data}"
        )

    def test_generate_bogus_member_ids_returns_400(self, admin_headers):
        """Generate with bogus member_ids (not in detector results) should return 400."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/generate",
            headers=admin_headers,
            json={"member_ids": ["bogus-id-12345", "fake-member-xyz"]}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "None of the supplied member_ids currently match a churn signal" in data.get("detail", ""), (
            f"Expected specific error message, got: {data}"
        )


class TestChurnRiskQueue:
    """Tests for GET /api/marketing/creative/director/churn-risk/queue"""

    def test_queue_requires_auth(self):
        """Queue endpoint should return 401 without auth token."""
        resp = requests.get(f"{BASE_URL}/api/marketing/creative/director/churn-risk/queue")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_queue_returns_200_with_correct_structure(self, admin_headers):
        """Queue should return 200 with rescues and count."""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/queue",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()

        assert "rescues" in data, "Response missing 'rescues'"
        assert "count" in data, "Response missing 'count'"
        assert isinstance(data["rescues"], list), "rescues should be a list"
        assert isinstance(data["count"], int), "count should be an integer"

    def test_queue_accepts_status_filter(self, admin_headers):
        """Queue should accept status filter parameter."""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/queue?status=sent",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "rescues" in data
        assert "count" in data


class TestChurnRiskApprove:
    """Tests for POST /api/marketing/creative/director/churn-risk/{id}/approve"""

    def test_approve_requires_auth(self):
        """Approve endpoint should return 401 without auth token."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-id/approve",
            json={}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_approve_bogus_id_returns_404(self, admin_headers):
        """Approve with bogus rescue_id should return 404."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-rescue-id-12345/approve",
            headers=admin_headers,
            json={}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "Rescue not found" in data.get("detail", ""), (
            f"Expected 'Rescue not found' in detail, got: {data}"
        )


class TestChurnRiskReject:
    """Tests for POST /api/marketing/creative/director/churn-risk/{id}/reject"""

    def test_reject_requires_auth(self):
        """Reject endpoint should return 401 without auth token."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-id/reject",
            json={}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_reject_bogus_id_returns_404(self, admin_headers):
        """Reject with bogus rescue_id should return 404."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-rescue-id-12345/reject",
            headers=admin_headers,
            json={}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:300]}"


class TestChurnRiskRefine:
    """Tests for POST /api/marketing/creative/director/churn-risk/{id}/refine"""

    def test_refine_requires_auth(self):
        """Refine endpoint should return 401 without auth token."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-id/refine",
            json={"instruction": "make it shorter"}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_refine_empty_instruction_returns_400(self, admin_headers):
        """Refine with empty instruction should return 400."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-rescue-id/refine",
            headers=admin_headers,
            json={"instruction": ""}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "instruction is required" in data.get("detail", ""), (
            f"Expected 'instruction is required' in detail, got: {data}"
        )

    def test_refine_bogus_id_returns_404(self, admin_headers):
        """Refine with bogus rescue_id should return 404."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/bogus-rescue-id-12345/refine",
            headers=admin_headers,
            json={"instruction": "make it shorter"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:300]}"


class TestChurnRiskApproveBulk:
    """Tests for POST /api/marketing/creative/director/churn-risk/approve-bulk"""

    def test_approve_bulk_requires_auth(self):
        """Approve-bulk endpoint should return 401 without auth token."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/approve-bulk",
            json={"rescue_ids": ["test-id"]}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_approve_bulk_empty_rescue_ids_returns_400(self, admin_headers):
        """Approve-bulk with empty rescue_ids should return 400."""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/creative/director/churn-risk/approve-bulk",
            headers=admin_headers,
            json={"rescue_ids": []}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "rescue_ids is required" in data.get("detail", ""), (
            f"Expected 'rescue_ids is required' in detail, got: {data}"
        )
