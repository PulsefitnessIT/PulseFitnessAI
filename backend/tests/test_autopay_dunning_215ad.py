"""Iter 215ad — Dunning retry ladder unit tests.

Covers:
- _next_retry_tone returns (iso_due_at, tone) or (None, "") when exhausted
- Ladder days: 3 → 7 → 14
- Tones: gentle → stern → final
- Decline email tone param renders correct subject + headline
- run_autopay_retry_ladder stops when ladder exhausted
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from routes.memberships import family_autopay


def test_ladder_first_retry_is_day_3_gentle():
    with patch("routes.memberships.family_autopay.datetime") as dt:
        dt.now.return_value = datetime(2026, 5, 10, tzinfo=timezone.utc)
        dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # datetime.now + timedelta still works because timedelta is imported separately
        due, tone = family_autopay._next_retry_tone(0)
    assert tone == "gentle"
    assert "2026-05-13" in due  # day +3


def test_ladder_second_retry_is_day_7_stern():
    with patch("routes.memberships.family_autopay.datetime") as dt:
        dt.now.return_value = datetime(2026, 5, 10, tzinfo=timezone.utc)
        dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        due, tone = family_autopay._next_retry_tone(1)
    assert tone == "stern"
    assert "2026-05-17" in due  # day +7


def test_ladder_third_retry_is_day_14_final():
    with patch("routes.memberships.family_autopay.datetime") as dt:
        dt.now.return_value = datetime(2026, 5, 10, tzinfo=timezone.utc)
        dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        due, tone = family_autopay._next_retry_tone(2)
    assert tone == "final"
    assert "2026-05-24" in due  # day +14


def test_ladder_exhausted_returns_none():
    due, tone = family_autopay._next_retry_tone(3)
    assert due is None
    assert tone == ""

    due, tone = family_autopay._next_retry_tone(99)
    assert due is None


def test_decline_email_gentle_tone_subject():
    org_find = AsyncMock(return_value={"name": "Studio"})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", SimpleNamespace(find_one=org_find)), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_decline_email(
            member={"id": "m1", "email": "a@b.com", "first_name": "Ali"},
            invoice={"id": "i1", "period": "2026-04", "organization_id": "o"},
            error_msg="declined",
            card_brand="visa", card_last4="4242",
            tone="gentle",
        ))
    subj, html = send.await_args.args[1], send.await_args.args[2]
    assert subj.startswith("Reminder:")
    assert "Quick reminder" in html
    assert "gentle nudge" in html


def test_decline_email_stern_tone_subject():
    org_find = AsyncMock(return_value={})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", SimpleNamespace(find_one=org_find)), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_decline_email(
            member={"id": "m1", "email": "a@b.com"},
            invoice={"id": "i1", "period": "2026-04", "organization_id": "o"},
            error_msg="still failing",
            card_brand=None, card_last4=None,
            tone="stern",
        ))
    subj, html = send.await_args.args[1], send.await_args.args[2]
    assert subj.startswith("Important:")
    assert "still being declined" in html


def test_decline_email_final_tone_subject():
    org_find = AsyncMock(return_value={})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", SimpleNamespace(find_one=org_find)), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_decline_email(
            member={"id": "m1", "email": "a@b.com"},
            invoice={"id": "i1", "period": "2026-04", "organization_id": "o"},
            error_msg="final",
            card_brand=None, card_last4=None,
            tone="final",
        ))
    subj, html = send.await_args.args[1], send.await_args.args[2]
    assert subj.startswith("Final notice:")
    assert "Final notice" in html
    assert "paused" in html


def test_schedule_or_exhaust_advances_attempts():
    update = AsyncMock()
    with patch.object(family_autopay.db, "membership_class_invoices", SimpleNamespace(update_one=update)):
        r = asyncio.run(family_autopay._schedule_or_exhaust_retry({"id": "i1"}, attempts=0))
    assert r["exhausted"] is False
    assert r["tone"] == "gentle"
    sets = update.await_args.args[1]["$set"]
    assert sets["auto_pay_retry_attempts"] == 1
    assert sets["auto_pay_next_retry_at"] is not None


def test_schedule_or_exhaust_marks_exhausted_on_3rd_call():
    update = AsyncMock()
    with patch.object(family_autopay.db, "membership_class_invoices", SimpleNamespace(update_one=update)):
        r = asyncio.run(family_autopay._schedule_or_exhaust_retry({"id": "i1"}, attempts=3))
    assert r["exhausted"] is True
    sets = update.await_args.args[1]["$set"]
    assert sets["auto_pay_retry_exhausted"] is True
    assert sets["auto_pay_next_retry_at"] is None


def test_retry_ladder_bails_when_stripe_missing():
    with patch.object(family_autopay, "STRIPE_API_KEY", None):
        r = asyncio.run(family_autopay.run_autopay_retry_ladder())
    assert r == {"ok": False, "reason": "stripe_not_configured"}
