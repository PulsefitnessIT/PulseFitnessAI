"""Iter 216h210 — Login-failure reason classification + diagnostics.

When login fails, the audit row should now carry a structured
``reason`` (user_not_found / wrong_password / account_disabled /
temp_password_expired / portal_mismatch_* / rate_limited /
account_locked). Master Admin's `/login-events` endpoint surfaces
this as ``failure_reason`` on each row.

Run: pytest backend/tests/test_iter_216h210_login_failure_reason.py -q
"""
from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Req:
    """Bare-minimum Request stand-in for the helper under test."""
    def __init__(self, ip: str = "10.0.0.1", ua: str = "test-agent/1.0"):
        self.client = MagicMock(host=ip)
        self.headers = {"User-Agent": ua}


def _patches_for_failed_login():
    """The helper writes to audit_logs and (optionally) trust_events.
    Stub both so we can introspect what was recorded."""
    audit_calls = []

    async def _audit(*args, **kwargs):
        audit_calls.append((args, kwargs))

    return audit_calls, _audit


def test_user_not_found_reason_audited():
    from routes import auth as auth_mod
    audit_calls, audit_stub = _patches_for_failed_login()
    with patch("utils.audit.audit_log", new=audit_stub), \
         patch.object(auth_mod, "record_failed_login"):
        _run(auth_mod._record_failed_login_with_trust(
            "ghost@example.com", _Req(), reason="user_not_found",
        ))
    assert len(audit_calls) == 1
    args, _ = audit_calls[0]
    assert args[0] == "login_failed"
    assert args[2] == "ghost@example.com"
    assert "reason=user_not_found" in args[5]


def test_wrong_password_reason_audited():
    from routes import auth as auth_mod
    audit_calls, audit_stub = _patches_for_failed_login()
    with patch("utils.audit.audit_log", new=audit_stub), \
         patch.object(auth_mod, "record_failed_login"):
        _run(auth_mod._record_failed_login_with_trust(
            "admin@example.com", _Req(), reason="wrong_password",
            user_id="u-1",
        ))
    args, _ = audit_calls[0]
    assert "reason=wrong_password" in args[5]
    assert args[1] == "u-1"  # user_id on the row


def test_account_locked_reason_audited():
    from routes import auth as auth_mod
    audit_calls, audit_stub = _patches_for_failed_login()
    with patch("utils.audit.audit_log", new=audit_stub), \
         patch.object(auth_mod, "record_failed_login"):
        _run(auth_mod._record_failed_login_with_trust(
            "admin@example.com", _Req(), reason="account_locked",
        ))
    args, _ = audit_calls[0]
    assert "reason=account_locked" in args[5]


# ──── /master-admin/login-events parses failure_reason ────

def test_login_events_endpoint_surfaces_failure_reason():
    """The endpoint regex-extracts ``reason=<code>`` from the audit
    details column and attaches it as ``failure_reason``."""
    from routes import master_admin_login_events as mod

    rows = [
        {"action": "login_failed", "user_email": "a@b.com",
         "details": "reason=wrong_password; ua=ua/1.0", "timestamp": "2026-05-18T20:00:00"},
        {"action": "login", "user_email": "a@b.com",
         "details": "Successful login", "timestamp": "2026-05-18T20:00:01"},
        {"action": "login_failed", "user_email": "x@y.com",
         "details": "reason=user_not_found; ua=ua/1.0", "timestamp": "2026-05-18T20:00:02"},
    ]

    fake_audit_cursor = MagicMock()
    fake_audit_cursor.sort.return_value = fake_audit_cursor
    fake_audit_cursor.limit.return_value = fake_audit_cursor
    fake_audit_cursor.to_list = AsyncMock(return_value=rows)

    fake_trust_cursor = MagicMock()
    fake_trust_cursor.sort.return_value = fake_trust_cursor
    fake_trust_cursor.limit.return_value = fake_trust_cursor
    fake_trust_cursor.to_list = AsyncMock(return_value=[])

    fake_db = MagicMock()
    fake_db.audit_logs.find.return_value = fake_audit_cursor
    fake_db.trust_events.find.return_value = fake_trust_cursor

    with patch.object(mod, "db", fake_db):
        out = _run(mod.list_login_events(
            user_id=None, email=None, since=None, limit=100,
            user={"is_master_admin": True},
        ))

    found = out["events"]
    assert found[0]["failure_reason"] == "wrong_password"
    assert found[1]["failure_reason"] is None  # success row has no reason
    assert found[2]["failure_reason"] == "user_not_found"
    assert out["stats"]["failure"] == 2
    assert out["stats"]["success"] == 1


# ──── Client errors list endpoint (master admin only) ────

def test_client_errors_endpoint_master_admin_only():
    from routes import client_errors as ce

    with pytest.raises(HTTPException) as exc:
        _run(ce.list_client_errors(limit=10, label=None, user={}))
    assert exc.value.status_code == 403


def test_client_errors_endpoint_returns_grouped_counts():
    from routes import client_errors as ce

    rows = [
        {"id": "1", "label": "Class Builder", "message": "x", "server_ts": "2026-05-18T20:00:00"},
        {"id": "2", "label": "Class Builder", "message": "y", "server_ts": "2026-05-18T20:00:01"},
        {"id": "3", "label": "Plan Editor",   "message": "z", "server_ts": "2026-05-18T20:00:02"},
    ]
    fake_cursor = MagicMock()
    fake_cursor.sort.return_value = fake_cursor
    fake_cursor.limit.return_value = fake_cursor
    fake_cursor.to_list = AsyncMock(return_value=rows)
    fake_db = MagicMock()
    fake_db.client_errors.find.return_value = fake_cursor

    with patch.object(ce, "db", fake_db):
        out = _run(ce.list_client_errors(
            limit=100, label=None,
            user={"is_master_admin": True},
        ))

    assert out["count"] == 3
    grouped = {x["label"]: x["count"] for x in out["by_label"]}
    assert grouped["Class Builder"] == 2
    assert grouped["Plan Editor"] == 1
