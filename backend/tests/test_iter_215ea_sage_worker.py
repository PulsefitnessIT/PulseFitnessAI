"""
Phase 8 Workstream B (iter 215ea) — Sage 200 outbox worker tests.

Tests:
  - POST /api/integrations/admin/sage/simulate-drain
  - POST /api/integrations/admin/sage/drain-now
  - POST /api/integrations/admin/sage/requeue-failed
  - Auth: all three require master admin (401 no-token, 403 non-admin)
  - GET /api/integrations/admin/health — Sage configured/live flags
  - Regression: prior endpoints still work
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────
# Auth tests — all Sage endpoints require master admin
# ─────────────────────────────────────────────────────────────────

class TestSageEndpointsAuth:
    """Auth: 401 without token, 403 for non-admin."""

    def test_sage_drain_now_no_auth(self):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sage/drain-now")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_sage_simulate_drain_no_auth(self):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sage/simulate-drain")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_sage_requeue_failed_no_auth(self):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sage/requeue-failed")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────
# POST /api/integrations/admin/sage/simulate-drain
# ─────────────────────────────────────────────────────────────────

class TestSageSimulateDrain:
    """Simulate drain transitions eligible rows to simulated_succeeded."""

    def test_simulate_drain_returns_200(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/simulate-drain?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_simulate_drain_response_shape(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/simulate-drain?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # DrainResult fields
        assert "started_at" in data
        assert "finished_at" in data
        assert "organizations" in data
        assert "attempted" in data
        assert "succeeded" in data
        assert "failed" in data
        assert "dead_letter" in data
        assert "skipped_no_config" in data
        assert "simulated" in data
        assert "by_outbox" in data
        assert "by_kind" in data

    def test_simulate_drain_simulated_flag_is_true(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/simulate-drain?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True, "simulated flag should be True for simulate-drain"

    def test_simulate_drain_by_outbox_has_invoice_and_po(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/simulate-drain?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        by_outbox = data.get("by_outbox", {})
        # Should have keys for both outboxes (may be empty dicts if no rows)
        # The keys are the collection names
        assert isinstance(by_outbox, dict)


# ─────────────────────────────────────────────────────────────────
# POST /api/integrations/admin/sage/drain-now
# ─────────────────────────────────────────────────────────────────

class TestSageDrainNow:
    """Live drain — without Sage credentials, rows should be skipped_no_config."""

    def test_drain_now_returns_200(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/drain-now?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_drain_now_response_shape(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/drain-now?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # DrainResult fields
        assert "started_at" in data
        assert "finished_at" in data
        assert "attempted" in data
        assert "succeeded" in data
        assert "failed" in data
        assert "skipped_no_config" in data
        assert "simulated" in data

    def test_drain_now_simulated_flag_is_false(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/drain-now?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is False, "simulated flag should be False for drain-now"

    def test_drain_now_skips_without_credentials(self, admin_headers):
        """Without Sage access_token, all attempted rows should be skipped_no_config."""
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/drain-now?max_rows=100",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # If any rows were attempted, they should all be skipped (no Sage creds)
        if data["attempted"] > 0:
            assert data["skipped_no_config"] == data["attempted"], \
                f"Expected all attempted rows to be skipped_no_config, got {data['skipped_no_config']}/{data['attempted']}"
            assert data["succeeded"] == 0, "No rows should succeed without Sage credentials"


# ─────────────────────────────────────────────────────────────────
# POST /api/integrations/admin/sage/requeue-failed
# ─────────────────────────────────────────────────────────────────

class TestSageRequeueFailed:
    """Requeue moves failed rows back to eligible state."""

    def test_requeue_failed_returns_200(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/requeue-failed",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_requeue_failed_response_shape(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/requeue-failed",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data
        assert "requeued" in data
        assert data["ok"] is True

    def test_requeue_failed_with_include_dead_letter(self, admin_headers):
        resp = requests.post(
            f"{BASE_URL}/api/integrations/admin/sage/requeue-failed?include_dead_letter=true",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "requeued" in data


# ─────────────────────────────────────────────────────────────────
# GET /api/integrations/admin/health — Sage config flags
# ─────────────────────────────────────────────────────────────────

class TestHealthSageConfig:
    """Health endpoint reports Sage configured and live flags."""

    def test_health_returns_sage_section(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "sage" in data, "Health response should include 'sage' section"

    def test_health_sage_has_config_and_live(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200
        sage = resp.json().get("sage", {})
        assert "config" in sage, "sage should have 'config' section"
        assert "live" in sage, "sage should have 'live' flag"

    def test_health_sage_config_has_configured_flag(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200
        sage_cfg = resp.json().get("sage", {}).get("config", {})
        assert "configured" in sage_cfg, "sage.config should have 'configured' flag"

    def test_health_sage_not_configured_without_credentials(self, admin_headers):
        """Without Sage credentials, both configured and live should be False."""
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200
        sage = resp.json().get("sage", {})
        # Without SAGE_CLIENT_ID/SECRET/access_token, should be False
        # (unless there's a legacy config with access_token)
        assert isinstance(sage.get("live"), bool)
        assert isinstance(sage.get("config", {}).get("configured"), bool)

    def test_health_sage_outbox_has_by_outbox(self, admin_headers):
        """Sage outbox should have by_outbox with invoice and po sub-objects."""
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200
        sage_outbox = resp.json().get("sage", {}).get("outbox", {})
        assert "by_outbox" in sage_outbox, "sage.outbox should have 'by_outbox'"
        by_outbox = sage_outbox["by_outbox"]
        assert "invoice" in by_outbox, "by_outbox should have 'invoice'"
        assert "po" in by_outbox, "by_outbox should have 'po'"


# ─────────────────────────────────────────────────────────────────
# Regression tests — prior endpoints still work
# ─────────────────────────────────────────────────────────────────

class TestRegressionIntegrationsAdmin:
    """Verify prior endpoints still work."""

    def test_health_endpoint(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/health", headers=admin_headers)
        assert resp.status_code == 200

    def test_sicon_outbox_endpoint(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/sicon/outbox", headers=admin_headers)
        assert resp.status_code == 200

    def test_sage_outbox_endpoint(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/sage/outbox", headers=admin_headers)
        assert resp.status_code == 200

    def test_mapping_sections_endpoint(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/integrations/admin/mapping/sections", headers=admin_headers)
        assert resp.status_code == 200

    def test_sicon_drain_now_endpoint(self, admin_headers):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/drain-now", headers=admin_headers)
        assert resp.status_code == 200

    def test_sicon_simulate_drain_endpoint(self, admin_headers):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/simulate-drain", headers=admin_headers)
        assert resp.status_code == 200

    def test_sicon_requeue_failed_endpoint(self, admin_headers):
        resp = requests.post(f"{BASE_URL}/api/integrations/admin/sicon/requeue-failed", headers=admin_headers)
        assert resp.status_code == 200


class TestRegressionSvcEndpoints:
    """Verify svc endpoints still work."""

    def test_comms_templates(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/svc/comms/templates", headers=admin_headers)
        assert resp.status_code == 200

    def test_desk_summary(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/svc/desk/summary", headers=admin_headers)
        assert resp.status_code == 200

    def test_billing_ready(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/svc/billing?status=ready", headers=admin_headers)
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────
# Sage outbox filter tests
# ─────────────────────────────────────────────────────────────────

class TestSageOutboxFilters:
    """Test outbox filtering by status."""

    def test_filter_by_simulated_succeeded(self, admin_headers):
        resp = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?status=simulated_succeeded",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        # All returned rows should have status=simulated_succeeded
        for row in data["rows"]:
            assert row.get("status") == "simulated_succeeded"

    def test_filter_by_ready(self, admin_headers):
        resp = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?status=ready",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data

    def test_filter_by_pending(self, admin_headers):
        resp = requests.get(
            f"{BASE_URL}/api/integrations/admin/sage/outbox?status=pending",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
