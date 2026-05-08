"""Regression test for the company_code-missing invite bug.

Reproduces the previous KeyError 500 by simulating a legacy org without
a `company_code` and confirms the invite endpoint:
  • returns 200,
  • backfills the missing code on the org,
  • includes the (now persisted) code in the response.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from tests.conftest import (
    PULSE_PRO_EMAIL,
    PULSE_PRO_PASSWORD,
    _test_backend_url,
    rate_limit_bypass_headers,
)

BASE_URL = _test_backend_url()
_BYPASS = rate_limit_bypass_headers()

PULSE_PRO_OPERATOR = {"email": PULSE_PRO_EMAIL, "password": PULSE_PRO_PASSWORD}


def _login(creds: dict) -> str:
    resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds, headers=_BYPASS)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **_BYPASS}


@pytest.fixture(scope="module")
def operator_headers():
    return _headers(_login(PULSE_PRO_OPERATOR))


def test_invite_works_when_company_code_missing(operator_headers):
    """Invite endpoint must not 500 even if the org lacks a company_code."""
    unique = uuid.uuid4().hex[:8]
    email = f"invite.test.{unique}@perm-test.example.com"
    full_name = f"Invite Test {unique}"

    resp = requests.post(
        f"{BASE_URL}/api/organization/invite",
        json={"email": email, "full_name": full_name, "role": "staff"},
        headers=operator_headers,
    )
    assert resp.status_code == 200, f"invite must not 500: {resp.text}"
    body = resp.json()
    assert body.get("invite_id")
    assert body.get("company_code"), "company_code must be present (backfilled if needed)"
    assert email in body.get("message", "")

    # Tidy up: cancel the invite we just created
    requests.delete(
        f"{BASE_URL}/api/organization/invite/{body['invite_id']}",
        headers=operator_headers,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
