"""Iter 216h215 — Platform-issues-24h aggregator.

Combines three feeds (failed logins · client crashes · trust events) into
a single 24h trust signal for the Master Admin home tile.

Run: pytest backend/tests/test_iter_216h215_platform_issues_24h.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_db(failed_logins: int, client_errors: int, trust_high: int):
    fake = MagicMock()
    fake.audit_logs = MagicMock()
    fake.audit_logs.count_documents = AsyncMock(return_value=failed_logins)
    fake.client_errors = MagicMock()
    fake.client_errors.count_documents = AsyncMock(return_value=client_errors)
    fake.trust_events = MagicMock()
    fake.trust_events.count_documents = AsyncMock(return_value=trust_high)
    return fake


def test_platform_issues_master_admin_only():
    from routes import platform_issues as p

    with pytest.raises(HTTPException) as exc:
        _run(p.platform_issues_24h(user={}))
    assert exc.value.status_code == 403


def test_platform_issues_green_when_quiet():
    from routes import platform_issues as p

    with patch.object(p, "db", _fake_db(0, 0, 0)):
        out = _run(p.platform_issues_24h(user={"is_master_admin": True}))
    assert out["total"] == 0
    assert out["tone"] == "green"
    assert len(out["breakdown"]) == 3


def test_platform_issues_amber_at_mid_volume():
    from routes import platform_issues as p

    # 5 + 3 + 2 = 10 → amber
    with patch.object(p, "db", _fake_db(5, 3, 2)):
        out = _run(p.platform_issues_24h(user={"is_master_admin": True}))
    assert out["total"] == 10
    assert out["tone"] == "amber"


def test_platform_issues_red_when_noisy():
    from routes import platform_issues as p

    with patch.object(p, "db", _fake_db(30, 5, 0)):
        out = _run(p.platform_issues_24h(user={"is_master_admin": True}))
    assert out["total"] == 35
    assert out["tone"] == "red"


def test_platform_issues_breakdown_contract():
    """Breakdown rows must carry the panel id the frontend deep-links to."""
    from routes import platform_issues as p

    with patch.object(p, "db", _fake_db(2, 1, 0)):
        out = _run(p.platform_issues_24h(user={"is_master_admin": True}))
    panels = {row["key"]: row["panel"] for row in out["breakdown"]}
    assert panels["failed_logins"] == "login-events"
    assert panels["client_errors"] == "client-errors"
    assert panels["trust_high"] == "trust"
