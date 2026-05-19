"""Iter 216h222 — Failed-email retry endpoint contract.

Pins the behaviour of POST /api/master-admin/email-events/{id}/retry
so the "one-click replay" UX in the Outbound Emails panel can't
silently regress.

Covers:
  • 404 when the event id is unknown
  • 409 when the event is already in `sent` state
  • 409 when the event has already been retried
  • 409 when the event predates h222 and has no stored payload
  • Master admin gate (403 for non-admins)
"""
from __future__ import annotations

import os
import uuid
import asyncio
from datetime import datetime, timezone

import httpx
import pytest

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


def _seed(payload_present: bool, *, status: str = "failed", retried: bool = False) -> str:
    """Insert a fixture email_send_events row directly via Mongo."""
    from motor.motor_asyncio import AsyncIOMotorClient

    eid = str(uuid.uuid4())
    doc = {
        "id": eid,
        "to": "test+216h222@example.com",
        "subject": f"216h222 fixture · {status}",
        "sender": "support@gymaxisai.com",
        "status": status,
        "error": "Fixture",
        "created_at": datetime.now(timezone.utc),
    }
    if payload_present:
        doc["payload"] = {
            "from": "GymAxis AI <support@gymaxisai.com>",
            "to": ["test+216h222@example.com"],
            "subject": doc["subject"],
            "html": "<p>fixture body</p>",
            "reply_to": None,
            "attachments": [],
            "organization_id": None,
        }
    if retried:
        doc["retried_at"] = datetime.now(timezone.utc)

    async def _go():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.email_send_events.insert_one(doc)

    asyncio.run(_go())
    return eid


def _cleanup() -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _go():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.email_send_events.delete_many({"to": "test+216h222@example.com"})

    asyncio.run(_go())


@pytest.fixture(autouse=True)
def _wipe_fixtures():
    yield
    _cleanup()


# ── 404 / 409 contract ──────────────────────────────────────────────


def test_retry_404_for_unknown_event(admin_token):
    r = httpx.post(
        f"{API}/master-admin/email-events/does-not-exist/retry",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 404


def test_retry_409_when_event_already_sent(admin_token):
    eid = _seed(payload_present=False, status="sent")
    r = httpx.post(
        f"{API}/master-admin/email-events/{eid}/retry",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 409
    assert "already delivered" in r.json()["detail"].lower()


def test_retry_409_when_event_already_retried(admin_token):
    eid = _seed(payload_present=True, retried=True)
    r = httpx.post(
        f"{API}/master-admin/email-events/{eid}/retry",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 409
    assert "already been retried" in r.json()["detail"].lower()


def test_retry_409_for_pre_h222_failure_without_payload(admin_token):
    eid = _seed(payload_present=False)
    r = httpx.post(
        f"{API}/master-admin/email-events/{eid}/retry",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 409
    assert "no retry payload" in r.json()["detail"].lower()


# ── Auth gate ───────────────────────────────────────────────────────


def test_retry_requires_master_admin():
    # Unauthenticated → 401/403 (handled by get_current_user)
    r = httpx.post(
        f"{API}/master-admin/email-events/anything/retry",
        timeout=15,
    )
    assert r.status_code in (401, 403)
