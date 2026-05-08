"""Iter 215aa — Family Auto-Bill helper unit tests.

Covers pure helpers and the short-circuit logic in
``run_family_autopay_cycle``. Full charge-path is covered by the
testing agent + Stripe in staging.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

from routes.memberships import family_autopay


def test_previous_period_jan_wraps_to_december():
    with patch("routes.memberships.family_autopay.datetime") as dt:
        dt.now.return_value = datetime(2026, 1, 2, tzinfo=timezone.utc)
        dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert family_autopay._previous_period_iso() == "2025-12"


def test_previous_period_regular_month():
    with patch("routes.memberships.family_autopay.datetime") as dt:
        dt.now.return_value = datetime(2026, 5, 1, tzinfo=timezone.utc)
        dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert family_autopay._previous_period_iso() == "2026-04"


def test_cycle_skipped_outside_window(monkeypatch):
    """Day > 3 → short-circuit (no Stripe, no Mongo calls)."""
    monkeypatch.setattr(family_autopay, "STRIPE_API_KEY", "sk_test_x")

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 15, tzinfo=timezone.utc)

    monkeypatch.setattr(family_autopay, "datetime", FakeDT)
    result = asyncio.run(family_autopay.run_family_autopay_cycle())
    assert result == {"ok": True, "skipped": "not_invoice_window"}


def test_cycle_bail_when_stripe_not_configured(monkeypatch):
    monkeypatch.setattr(family_autopay, "STRIPE_API_KEY", None)
    result = asyncio.run(family_autopay.run_family_autopay_cycle())
    assert result == {"ok": False, "reason": "stripe_not_configured"}
