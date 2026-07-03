"""Iter 216h93 — Master-admin platform vitals endpoint.

Endpoints under test:
  GET /api/health/full     (master admin only)
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://ops-parts-request.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


class TestHealthFull:
    def test_master_admin_can_fetch(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/health/full", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Core blocks present
        for k in ("overall", "mongo", "integrations", "business",
                  "service_desk", "partner_network", "sender_email",
                  "jwt", "latency_ms", "partner_plan_prices"):
            assert k in body, f"missing key {k}"
        # Mongo ping passes in the preview env
        assert body["mongo"]["status"] == "ok"
        # Counts are non-negative integers
        for sub in ("business", "service_desk", "partner_network"):
            for k, v in body[sub].items():
                assert isinstance(v, int) and v >= 0, f"{sub}.{k} = {v!r}"
        # NEVER echo the actual env var values
        for v in body["integrations"].values():
            assert isinstance(v, bool)
        # Partner plan price IDs detected correctly (preview env has both)
        assert body["partner_plan_prices"]["p30"] is True
        assert body["partner_plan_prices"]["p15"] is True
        # Stripe webhook secret present
        assert body["integrations"]["stripe"] is True
        assert body["integrations"]["stripe_webhook"] is True

    def test_non_master_admin_forbidden(self):
        # E1 demo operator user from test_credentials.md
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "e1.agent@gymaxisai.com", "password": "E1Agent123!"},
            timeout=10,
        )
        if r.status_code != 200:
            pytest.skip("E1 demo operator unavailable")
        tok = r.json()["token"]
        r = requests.get(
            f"{BASE_URL}/api/health/full",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10,
        )
        assert r.status_code == 403

    def test_unauthenticated_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/health/full", timeout=10)
        assert r.status_code in (401, 403)
