"""Iter 216h258 — Email pipeline shows all senders.

User feedback (Feb 21, 2026):
"Master admin — can email pipeline include all email addresses.
Support, billing, service etc"

The /master-admin/email-health response previously surfaced only the
default `SENDER_EMAIL`. The modal now aggregates every distinct sender
address seen in the rolling 24h window with per-sender sent / failed
counts and last-activity timestamp. The configured default is always
included even if it hasn't sent anything yet.
"""
from __future__ import annotations

import asyncio
import pathlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_db(sender_rows, *, sent_24h=0, failed_24h=0):
    fake = MagicMock()
    fake.email_send_events = MagicMock()
    fake.email_send_events.count_documents = AsyncMock(side_effect=[sent_24h, failed_24h])
    fake.email_send_events.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    fake.email_send_events.find = MagicMock(return_value=cursor)

    sender_cursor = MagicMock()
    sender_cursor.to_list = AsyncMock(return_value=sender_rows)
    fake.email_send_events.aggregate = MagicMock(return_value=sender_cursor)
    return fake


def test_email_health_aggregates_all_senders():
    from routes import email_health as eh

    fake = _build_db(
        sender_rows=[
            {"_id": "support@gymaxisai.com", "sent": 12, "failed": 1, "last_at": datetime.now(timezone.utc)},
            {"_id": "billing@gymaxisai.com", "sent": 4,  "failed": 0, "last_at": datetime.now(timezone.utc)},
            {"_id": "service@gymaxisai.com", "sent": 7,  "failed": 2, "last_at": datetime.now(timezone.utc)},
        ],
        sent_24h=23, failed_24h=3,
    )
    user = {"is_master_admin": True, "email": "admin@example.com"}
    with patch.object(eh, "db", fake), \
         patch.object(eh, "RESEND_API_KEY", "rk_test"), \
         patch.object(eh, "SENDER_EMAIL", "support@gymaxisai.com"):
        out = _run(eh.email_health(user=user))

    senders = out["senders"]
    addrs = [s["address"] for s in senders]
    # All three present.
    assert "support@gymaxisai.com" in addrs
    assert "billing@gymaxisai.com" in addrs
    assert "service@gymaxisai.com" in addrs
    # Default flag set correctly.
    default = next(s for s in senders if s["address"] == "support@gymaxisai.com")
    assert default["is_default"] is True
    others = [s for s in senders if s["address"] != "support@gymaxisai.com"]
    assert all(s["is_default"] is False for s in others)
    # Counts surface per row.
    billing = next(s for s in senders if s["address"] == "billing@gymaxisai.com")
    assert billing["sent"] == 4
    assert billing["failed"] == 0


def test_email_health_includes_default_when_no_activity():
    """Default sender must show even if no rows have been logged yet."""
    from routes import email_health as eh

    fake = _build_db(sender_rows=[], sent_24h=0, failed_24h=0)
    user = {"is_master_admin": True, "email": "admin@example.com"}
    with patch.object(eh, "db", fake), \
         patch.object(eh, "RESEND_API_KEY", "rk_test"), \
         patch.object(eh, "SENDER_EMAIL", "support@gymaxisai.com"):
        out = _run(eh.email_health(user=user))

    assert len(out["senders"]) == 1
    assert out["senders"][0]["address"] == "support@gymaxisai.com"
    assert out["senders"][0]["is_default"] is True


def test_email_health_skips_empty_sender_addresses():
    from routes import email_health as eh

    fake = _build_db(sender_rows=[
        {"_id": "", "sent": 1, "failed": 0, "last_at": None},
        {"_id": None, "sent": 1, "failed": 0, "last_at": None},
        {"_id": "support@gymaxisai.com", "sent": 5, "failed": 0, "last_at": None},
    ], sent_24h=5, failed_24h=0)
    user = {"is_master_admin": True, "email": "admin@example.com"}
    with patch.object(eh, "db", fake), \
         patch.object(eh, "RESEND_API_KEY", "rk_test"), \
         patch.object(eh, "SENDER_EMAIL", "support@gymaxisai.com"):
        out = _run(eh.email_health(user=user))

    addrs = [s["address"] for s in out["senders"]]
    assert "" not in addrs and None not in addrs
    assert "support@gymaxisai.com" in addrs


def test_modal_renders_senders_list():
    src = pathlib.Path(
        "/app/frontend/src/pages/MasterAdmin/EmailHealthPill.js"
    ).read_text()
    # New list container and per-sender row test ids.
    assert 'data-testid="email-health-senders"' in src
    assert "data.senders.map" in src
    # The label changed from "Sender" → "Senders" with active count.
    assert "Senders {(data.senders || []).length > 1" in src
    # Default badge surfaces.
    assert "Default</span>" in src
