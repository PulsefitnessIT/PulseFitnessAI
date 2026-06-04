"""Iter 220p1 — per-org timezone threading (USA readiness, slice 5).

Reminders / quiet-hours / booking windows must resolve on the ORG's local
clock, not a hard-coded Europe/London. Tested via the pure quiet-hours
evaluator (timezone-sensitive) and the centralised timezone resolver.
"""
from datetime import datetime, timezone

import pytest


def test_get_org_timezone_default_is_uk():
    import asyncio
    from utils.localization import get_org_timezone
    assert asyncio.get_event_loop_policy()  # sanity
    # organization_id=None short-circuits without touching the DB.
    tz = asyncio.new_event_loop().run_until_complete(get_org_timezone(None))
    assert tz == "Europe/London"


QH = {"quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}


def test_quiet_hours_honours_org_timezone():
    """02:00 UTC (Jan, no DST): London=02:00 (inside 22:00→07:00 → quiet),
    New York=21:00 prev day (EST, UTC-5 → outside → NOT quiet).
    Proves the same instant is gated differently per timezone."""
    from routes.svc.notifications import _in_quiet_hours
    now = datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc)
    assert _in_quiet_hours({**QH, "timezone": "Europe/London"}, now=now) is True
    assert _in_quiet_hours({**QH, "timezone": "America/New_York"}, now=now) is False


def test_quiet_hours_no_window_is_never_quiet():
    from routes.svc.notifications import _in_quiet_hours
    assert _in_quiet_hours({"timezone": "America/New_York"}) is False


def test_basics_body_timezone_currency_optional():
    """Membership wizard no longer hard-defaults GB — None means inherit
    the org's market (so a US studio isn't reset to UK/£)."""
    from routes.memberships_ops import BasicsBody
    b = BasicsBody(name="US Studio")
    assert b.timezone is None
    assert b.currency is None
