"""Iteration 199 — Service Desk user creation tests.

Validates the new `POST /api/master-admin/service-desk/users` endpoint and
the brand-aware grant flow.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    _test_backend_url,
    rate_limit_bypass_headers,
)

BASE_URL = _test_backend_url()
_BYPASS = rate_limit_bypass_headers()


def _login(creds: dict) -> str:
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds, headers=_BYPASS)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **_BYPASS}


@pytest.fixture(scope="module")
def admin_headers():
    return _headers(_login({"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD}))


@pytest.fixture(scope="module")
def admin_token():
    return _login({"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD})


class TestServiceDeskCreate:
    def test_create_gymaxis_service_desk_user(self, admin_headers):
        unique = uuid.uuid4().hex[:8]
        email = f"sd.gymaxis.{unique}@perm-test.example.com"
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/service-desk/users",
            json={"email": email, "full_name": f"SD GymAxis {unique}", "brand": "gymaxis"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["brand"] == "gymaxis"
        assert body["temp_password"]
        # Listing reflects the new user with brand
        listing = requests.get(
            f"{BASE_URL}/api/master-admin/service-desk/members",
            headers=admin_headers,
        ).json()
        match = next((m for m in listing["members"] if m["email"] == email), None)
        assert match is not None
        assert match["service_desk_brand"] == "gymaxis"
        assert match["must_change_password"] is True

    def test_create_pulse_service_desk_user_can_login_and_must_change(self, admin_headers):
        unique = uuid.uuid4().hex[:8]
        email = f"sd.pulse.{unique}@perm-test.example.com"
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/service-desk/users",
            json={"email": email, "full_name": f"SD Pulse {unique}", "brand": "pulse"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        temp_pwd = body["temp_password"]

        # New SD user can log in with the temp password
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": temp_pwd},
            headers=_BYPASS,
        )
        assert login.status_code == 200, login.text
        login_body = login.json()
        # /auth/me reflects service desk + must change pwd
        me = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={**_BYPASS, "Authorization": f"Bearer {login_body['token']}"},
        ).json()
        assert me["is_service_desk"] is True
        assert me["password_needs_rotation"] is True or login_body["user"].get("must_change_password")

    def test_duplicate_email_rejected(self, admin_headers):
        unique = uuid.uuid4().hex[:8]
        email = f"sd.dup.{unique}@perm-test.example.com"
        first = requests.post(
            f"{BASE_URL}/api/master-admin/service-desk/users",
            json={"email": email, "full_name": "First", "brand": "gymaxis"},
            headers=admin_headers,
        )
        assert first.status_code == 200
        second = requests.post(
            f"{BASE_URL}/api/master-admin/service-desk/users",
            json={"email": email, "full_name": "Second", "brand": "pulse"},
            headers=admin_headers,
        )
        assert second.status_code == 409
        assert "already exists" in second.text.lower()

    def test_invalid_brand_rejected(self, admin_headers):
        unique = uuid.uuid4().hex[:8]
        email = f"sd.bad.{unique}@perm-test.example.com"
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/service-desk/users",
            json={"email": email, "full_name": "Bad Brand", "brand": "facebook"},
            headers=admin_headers,
        )
        assert resp.status_code == 422  # pydantic validation


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
