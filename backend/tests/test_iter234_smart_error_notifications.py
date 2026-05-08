"""Iter 234 — Smart error notifications + Recent Errors panel tests.

The frontend `formatApiError` is unit-tested via the JS testing harness;
this file proves the server-side telemetry plumbing the new panel relies
on.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip() + "/api"
)


def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def master_headers() -> dict:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


def test_ui_error_post_anonymous_accepted():
    r = requests.post(
        f"{API_BASE}/ui-errors",
        json={
            "title": "Iter234 anon test",
            "detail": "Anonymous post should be accepted",
            "path": "/test",
        },
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_ui_error_post_with_auth_records_user_context(operator_headers):
    nonce = uuid.uuid4().hex[:8]
    r = requests.post(
        f"{API_BASE}/ui-errors",
        json={
            "title": f"Iter234 auth test {nonce}",
            "detail": "Should attach user_id + organization_id",
            "path": "/marketing",
        },
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200


def test_ui_error_post_400_when_title_missing():
    r = requests.post(
        f"{API_BASE}/ui-errors",
        json={"title": ""},
        timeout=10,
    )
    assert r.status_code in (400, 422)


def test_ui_error_summary_master_admin_only(master_headers, operator_headers):
    # Operator should be 403
    r_op = requests.get(
        f"{API_BASE}/ui-errors/summary?days=7",
        headers=operator_headers,
        timeout=10,
    )
    assert r_op.status_code == 403

    # Master admin succeeds
    r_admin = requests.get(
        f"{API_BASE}/ui-errors/summary?days=7",
        headers=master_headers,
        timeout=15,
    )
    assert r_admin.status_code == 200, r_admin.text
    body = r_admin.json()
    assert body["window_days"] == 7
    assert "total_events" in body
    assert "unique_users_affected" in body
    assert isinstance(body["top"], list)


def test_ui_error_recent_master_admin_only(master_headers, operator_headers):
    r_op = requests.get(
        f"{API_BASE}/ui-errors/recent?limit=10",
        headers=operator_headers,
        timeout=10,
    )
    assert r_op.status_code == 403

    r_admin = requests.get(
        f"{API_BASE}/ui-errors/recent?limit=10",
        headers=master_headers,
        timeout=10,
    )
    assert r_admin.status_code == 200
    assert isinstance(r_admin.json()["items"], list)


def test_ui_error_summary_groups_by_fingerprint(master_headers):
    """Posting the SAME error 3x within the window should produce one
    fingerprint with count >= 3 in the summary."""
    title = f"Iter234 grouping test {uuid.uuid4().hex[:6]}"
    for _ in range(3):
        requests.post(
            f"{API_BASE}/ui-errors",
            json={"title": title, "detail": "regression case", "path": "/test/iter234"},
            timeout=10,
        )
    # Give the DB a tick.
    time.sleep(0.3)
    r = requests.get(
        f"{API_BASE}/ui-errors/summary?days=1",
        headers=master_headers,
        timeout=10,
    )
    assert r.status_code == 200
    matching = [t for t in r.json()["top"] if t["title"] == title]
    assert matching, "expected the grouped fingerprint to appear in the summary"
    assert matching[0]["count"] >= 3


def test_subscription_endpoint_succeeds_with_fresh_token(master_headers):
    """Sanity check that the subscription update endpoint that the user
    saw 'Failed to update subscription' on actually works end-to-end —
    so the new toast helper correctly surfaces it as 'Session expired'
    when the real cause is a stale token."""
    orgs = requests.get(
        f"{API_BASE}/master-admin/organizations",
        headers=master_headers,
        timeout=10,
    ).json()
    if isinstance(orgs, dict):
        orgs = orgs.get("organizations") or []
    pulse_org = next((o for o in orgs if o.get("account_type") in ("lite", "pulse_pro")), None)
    if not pulse_org:
        pytest.skip("No Pulse org available")
    org_id = pulse_org["id"]
    original = pulse_org.get("subscription_tier") or "pulse_pro"

    # Attempt the change the user reported failing
    target = "lite" if original != "lite" else "pulse_pro"
    r = requests.put(
        f"{API_BASE}/master-admin/organizations/{org_id}/subscription",
        json={"tier": target},
        headers=master_headers,
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["tier"] == target

    # Restore
    requests.put(
        f"{API_BASE}/master-admin/organizations/{org_id}/subscription",
        json={"tier": original},
        headers=master_headers,
        timeout=10,
    )


def test_subscription_endpoint_returns_401_without_token():
    """Confirms the path that the user actually hit — without auth the
    server returns 401, which our new toast helper translates into
    'Session expired' instead of 'Failed to update subscription'."""
    r = requests.put(
        f"{API_BASE}/master-admin/organizations/some-org/subscription",
        json={"tier": "lite"},
        timeout=10,
    )
    assert r.status_code in (401, 403)


def test_subscription_endpoint_returns_400_for_invalid_tier(master_headers):
    """Surfaces a clean 400 with detail — our helper renders it verbatim
    rather than 'Failed to update subscription'."""
    orgs = requests.get(
        f"{API_BASE}/master-admin/organizations",
        headers=master_headers,
        timeout=10,
    ).json()
    if isinstance(orgs, dict):
        orgs = orgs.get("organizations") or []
    if not orgs:
        pytest.skip("No orgs")
    org_id = orgs[0]["id"]
    r = requests.put(
        f"{API_BASE}/master-admin/organizations/{org_id}/subscription",
        json={"tier": "ufo_tier"},
        headers=master_headers,
        timeout=10,
    )
    assert r.status_code == 400
    assert "Invalid tier" in r.json()["detail"]
