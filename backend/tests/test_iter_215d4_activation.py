"""Iter 215d4 — Activation funnel event wiring + operator-facing endpoint.

Covers:
- `POST /api/memberships/members` fires `first_member_added`
- `POST /api/organization/invite` fires `first_staff_invited`
- `GET /api/activation/me` returns the current user's org timeline
- Idempotency: duplicate events per (org, event_type) are silently dropped
"""
from __future__ import annotations

import os
import time
import uuid
import requests

BASE = os.environ.get("PUBLIC_BASE") or "http://localhost:8001"


def _rl_headers():
    sec = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    return {"X-RateLimit-Bypass": sec} if sec else {}


def _register_and_login() -> tuple[str, str]:
    """Register a fresh operator and return (email, token)."""
    ts = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    email = f"activation.iter215d4+{ts}@example.com"
    requests.post(
        f"{BASE}/api/auth/register",
        json={
            "email": email,
            "password": "Test1234!",
            "full_name": "Activation Tester",
            "company_name": f"Activation Gym {ts}",
        },
        headers=_rl_headers(),
        timeout=10,
    )
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": "Test1234!"},
        headers=_rl_headers(),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return email, r.json()["token"]


def _timeline(token: str) -> dict:
    r = requests.get(
        f"{BASE}/api/activation/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _fired(timeline: list[dict]) -> set[str]:
    return {e["event_type"] for e in timeline if e["fired"]}


def test_activation_me_shape():
    _, token = _register_and_login()
    data = _timeline(token)
    assert "timeline" in data
    assert data["total"] == 8
    # First-login should fire during the explicit /auth/login in _register_and_login.
    assert "first_login" in _fired(data["timeline"])


def test_first_member_added_fires_once():
    _, token = _register_and_login()
    before = _fired(_timeline(token)["timeline"])
    assert "first_member_added" not in before

    r = requests.post(
        f"{BASE}/api/memberships/members",
        json={"first_name": "Emma", "last_name": "Test", "email": f"emma-{uuid.uuid4().hex[:6]}@test.com"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text

    after = _fired(_timeline(token)["timeline"])
    assert "first_member_added" in after

    # Idempotency — adding a second member must not fire the event again.
    occurred_at_1 = next(e["occurred_at"] for e in _timeline(token)["timeline"] if e["event_type"] == "first_member_added")
    time.sleep(0.2)
    requests.post(
        f"{BASE}/api/memberships/members",
        json={"first_name": "Oliver", "last_name": "Test2", "email": f"oliver-{uuid.uuid4().hex[:6]}@test.com"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    occurred_at_2 = next(e["occurred_at"] for e in _timeline(token)["timeline"] if e["event_type"] == "first_member_added")
    assert occurred_at_1 == occurred_at_2, "event must not re-fire"


def test_first_staff_invited_fires():
    _, token = _register_and_login()
    assert "first_staff_invited" not in _fired(_timeline(token)["timeline"])

    r = requests.post(
        f"{BASE}/api/organization/invite",
        json={"email": f"invitee-{uuid.uuid4().hex[:6]}@test.com", "full_name": "Invited Staff", "role": "staff"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert "first_staff_invited" in _fired(_timeline(token)["timeline"])
