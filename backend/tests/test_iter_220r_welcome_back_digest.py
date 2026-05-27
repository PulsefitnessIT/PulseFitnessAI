"""Iter 220r — Return-day welcome-back digest sweep tests.

Pins the behaviour of ``utils.partner_return_digest.sweep_once``:

* Fires the digest when a partner's ``resumes_on`` is today / past.
* Skips partners still on leave with future ``resumes_on``.
* Skips already-available partners.
* Idempotency — once the digest has fired for a given ``resumes_on``
  ISO date, a re-run does not refire.
* Auto-resume — the sweep flips ``availability.status = 'available'``
  and clears ``resumes_on`` / ``note`` after firing.
* Email body — ``send_welcome_back_digest`` is called with the
  derived open-case count, overdue count, and compliance warnings.
* Compliance — both legacy (``insurance_expires_at``) and nested
  (``compliance_docs.dbs.expires_at``) entries surface in the digest.
* Missing email — sweep still flips availability but does not crash.

All tests are pure-unit: ``db`` and ``send_email`` are patched so we
never hit Mongo / Resend.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils import partner_return_digest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _yesterday_iso() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def _tomorrow_iso() -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def _make_cursor(items):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _fake_db(*, partners, open_count=0, overdue_count=0):
    """Return a MagicMock-based fake `db` that mimics motor's async API
    for the queries the sweep makes (partner_engineers.find /
    partner_engineers.update_one / supplier_cases.count_documents)."""
    fake = MagicMock()
    fake.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake.partner_engineers.update_one = AsyncMock()
    # First call (base filter) → open_count; second (overdue filter) → overdue_count.
    fake.supplier_cases.count_documents = AsyncMock(side_effect=[open_count, overdue_count])
    return fake


# ── Happy path ───────────────────────────────────────────────────


def test_sweep_fires_digest_when_resumes_on_is_today():
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane Doe",
        "availability": {
            "status": "unavailable",
            "resumes_on": _today_iso(),
            "note": "Back from paternity leave",
            "updated_at": datetime.now(timezone.utc) - timedelta(days=14),
        },
    }]
    fake = _fake_db(partners=partners, open_count=3, overdue_count=1)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())

    assert summary == {"checked": 1, "sent": 1, "skipped": 0}
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["email"] == "jane@x.io"
    assert kwargs["full_name"] == "Jane Doe"
    assert kwargs["leave_note"] == "Back from paternity leave"
    assert kwargs["my_gyms_open_count"] == 3
    assert kwargs["my_gyms_overdue_count"] == 1
    # days_away derived from updated_at (~14 days ago)
    assert kwargs["days_away"] is not None and kwargs["days_away"] >= 13

    # Persisted auto-resume.
    set_doc = fake.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["availability.status"] == "available"
    assert set_doc["availability.welcome_back_fired_on"] == _today_iso()
    assert set_doc["availability.resumes_on"] is None
    assert set_doc["availability.note"] is None


def test_sweep_fires_digest_for_overdue_resumes_on():
    """``resumes_on`` set in the past (engineer forgot to toggle back)
    must still fire — the sweep is the safety-net."""
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane Doe",
        "availability": {
            "status": "unavailable",
            "resumes_on": _yesterday_iso(),
            "note": None,
            "updated_at": datetime.now(timezone.utc) - timedelta(days=3),
        },
    }]
    fake = _fake_db(partners=partners, open_count=0, overdue_count=0)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())

    assert summary["sent"] == 1
    # Marker = the actual resumes_on, not "today"
    set_doc = fake.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["availability.welcome_back_fired_on"] == _yesterday_iso()
    send.assert_called_once()


# ── Idempotency ──────────────────────────────────────────────────


def test_sweep_does_not_double_fire_same_resumes_on():
    iso = _today_iso()
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane",
        "availability": {
            "status": "unavailable",
            "resumes_on": iso,
            "welcome_back_fired_on": iso,  # already fired today
        },
    }]
    fake = _fake_db(partners=partners)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())
    send.assert_not_called()
    fake.partner_engineers.update_one.assert_not_called()
    assert summary == {"checked": 1, "sent": 0, "skipped": 1}


# ── Skips ────────────────────────────────────────────────────────


def test_sweep_skips_partner_still_on_leave_future_resumes_on():
    """Mongo query already filters by ``resumes_on < tomorrow``, but
    the per-row check is also belt-and-braces — make sure that
    branch returns None safely if a future date ever slips through."""
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane",
        "availability": {
            "status": "unavailable",
            "resumes_on": _tomorrow_iso(),
        },
    }]
    fake = _fake_db(partners=partners)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())
    send.assert_not_called()
    fake.partner_engineers.update_one.assert_not_called()
    assert summary["skipped"] == 1


def test_sweep_skips_available_partners():
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane",
        "availability": {"status": "available", "resumes_on": _today_iso()},
    }]
    fake = _fake_db(partners=partners)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())
    send.assert_not_called()
    fake.partner_engineers.update_one.assert_not_called()
    assert summary["skipped"] == 1


# ── Compliance heads-up surfaces correctly ───────────────────────


def test_sweep_includes_compliance_warnings_in_digest():
    now = datetime.now(timezone.utc)
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane",
        "availability": {"status": "unavailable", "resumes_on": _today_iso()},
        # Legacy (top-level) expiring soon
        "insurance_expires_at": now + timedelta(days=5),
        # Nested compliance doc, already expired
        "compliance_docs": {
            "dbs": {"expires_at": now - timedelta(days=2)},
        },
    }]
    fake = _fake_db(partners=partners, open_count=0, overdue_count=0)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        _run(partner_return_digest.sweep_once())
    kwargs = send.call_args.kwargs
    warnings = kwargs["compliance_warnings"]
    assert any("Public liability insurance" in w for w in warnings)
    assert any("DBS check" in w and "expired" in w for w in warnings)


# ── Missing email still auto-resumes ─────────────────────────────


def test_sweep_handles_partner_without_email():
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "",  # missing
        "full_name": "Jane",
        "availability": {"status": "unavailable", "resumes_on": _today_iso()},
    }]
    fake = _fake_db(partners=partners)
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        summary = _run(partner_return_digest.sweep_once())
    send.assert_not_called()
    # Still auto-resumes so we don't loop forever.
    set_doc = fake.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["availability.status"] == "available"
    assert set_doc["availability.welcome_back_fired_on"] == _today_iso()
    assert summary["sent"] == 0


# ── Email template snapshot ──────────────────────────────────────


def test_welcome_back_email_template_renders_with_workload():
    """Smoke-test the email body so future refactors don't drop the
    key copy beats (welcome-back headline, open-case count, compliance
    block, CTA URL)."""
    from utils import partner_emails

    captured = {}

    async def _capture(*, to, subject, html):
        captured["to"] = to
        captured["subject"] = subject
        captured["html"] = html
        return True

    with patch("utils.partner_emails.send_email", _capture):
        _run(partner_emails.send_welcome_back_digest(
            email="jane@x.io",
            full_name="Jane Doe",
            leave_note="Back from paternity leave",
            days_away=14,
            my_gyms_open_count=3,
            my_gyms_overdue_count=1,
            compliance_warnings=["DBS check expired on 12 Feb — update to keep getting jobs."],
            dashboard_url="https://example.test/partner-engineer",
        ))

    assert captured["to"] == "jane@x.io"
    assert "Welcome back" in captured["subject"]
    assert "3 jobs waiting" in captured["subject"]
    html = captured["html"]
    assert "Welcome back, Jane." in html
    assert "<strong>3 jobs</strong>" in html
    assert "1 overdue" in html
    assert "DBS check expired" in html
    assert "Back from paternity leave" in html
    assert "https://example.test/partner-engineer" in html


def test_welcome_back_email_template_handles_quiet_inbox():
    """No open cases → friendlier copy + different subject line."""
    from utils import partner_emails
    captured = {}

    async def _capture(*, to, subject, html):
        captured.update({"to": to, "subject": subject, "html": html})
        return True

    with patch("utils.partner_emails.send_email", _capture):
        _run(partner_emails.send_welcome_back_digest(
            email="quiet@x.io",
            full_name="Quiet Engineer",
            leave_note=None,
            days_away=None,
            my_gyms_open_count=0,
            my_gyms_overdue_count=0,
            compliance_warnings=None,
            dashboard_url=None,
        ))

    assert "queue is clear" in captured["subject"]
    assert "queue is clear" in captured["html"]
    # When no leave note + no compliance warnings, those blocks omitted entirely.
    assert "Back from" not in captured["html"]
    assert "Compliance to handle" not in captured["html"]
