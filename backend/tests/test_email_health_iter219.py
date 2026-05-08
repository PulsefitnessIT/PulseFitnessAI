"""Email health pill — iteration 219.

Verifies GET /api/master-admin/email-health classification logic and
that ``send_email`` audit rows surface in the recent feed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def _purge():
    """Clear the email_send_events collection so each classification
    test starts from zero."""
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    async def run():
        await db.email_send_events.delete_many({})
    asyncio.get_event_loop().run_until_complete(run())


def _seed(rows: list[dict]):
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    async def run():
        for r in rows:
            r.setdefault("created_at", datetime.now(timezone.utc))
            await db.email_send_events.insert_one(r)
    asyncio.get_event_loop().run_until_complete(run())


def test_email_health_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(pulse_pro_token),
        timeout=10,
    )
    assert r.status_code == 403


def test_email_health_amber_when_no_activity(master_admin_token_session):
    _purge()
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "amber"
    assert "No email activity" in body["label"]
    assert body["sent"] == 0 and body["failed"] == 0
    assert body["recent"] == []


def test_email_health_green_when_all_sent(master_admin_token_session):
    _purge()
    _seed([
        {"to": "a@x.com", "subject": "ok 1", "status": "sent", "error": ""},
        {"to": "b@x.com", "subject": "ok 2", "status": "sent", "error": ""},
        {"to": "c@x.com", "subject": "ok 3", "status": "sent", "error": ""},
    ])
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    body = r.json()
    assert body["status"] == "green"
    assert body["sent"] == 3 and body["failed"] == 0
    assert body["domain_verified"] is True
    assert len(body["recent"]) == 3


def test_email_health_red_with_domain_not_verified(master_admin_token_session):
    _purge()
    _seed([{
        "to": "x@x.com",
        "subject": "boom",
        "status": "failed",
        "error": "ResendError('The example.com domain is not verified. Please, add and verify your domain on https://resend.com/domains')",
    }])
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    body = r.json()
    assert body["status"] == "red"
    assert "domain not verified" in body["label"].lower()
    assert body["domain_verified"] is False
    assert body["last_error"] and "domain is not verified" in body["last_error"]


def test_email_health_amber_when_mixed(master_admin_token_session):
    _purge()
    _seed([
        {"to": "a@x.com", "subject": "ok",   "status": "sent",   "error": ""},
        {"to": "b@x.com", "subject": "ok",   "status": "sent",   "error": ""},
        {"to": "c@x.com", "subject": "boom", "status": "failed", "error": "rate limit"},
    ])
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    body = r.json()
    assert body["status"] == "amber"
    assert "delivered" in body["label"] and "failed" in body["label"]
    assert body["sent"] == 2 and body["failed"] == 1
    # Mixed delivery → some sends succeeded → domain considered verified.
    assert body["domain_verified"] is True


def test_email_health_recent_capped_at_5(master_admin_token_session):
    _purge()
    _seed([
        {"to": f"a{i}@x.com", "subject": f"row {i}", "status": "sent", "error": ""}
        for i in range(10)
    ])
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/email-health",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    body = r.json()
    assert len(body["recent"]) == 5  # SAMPLE_SIZE
