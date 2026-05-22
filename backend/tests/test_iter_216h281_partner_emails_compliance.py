"""Iter 216h281 — Partner Engineer transactional emails + compliance sweep.

Closes Gaps 1 + 2 from the BA audit:

Gap 1: applicants never heard back. We now fire 3 lifecycle emails:
  * application received  (public-apply)
  * application approved  (master-admin approve)
  * application rejected  (master-admin reject)

Gap 2: insurance / qualifications could lapse silently. We now:
  * capture `insurance_expires_at` + `qualifications_expires_at`
  * run a nightly sweep that emails T-30 / T-7 / T-0 reminders
  * flip `compliance_paused = True` once anything expires
  * expose a self-service `PUT /partners/me/compliance` endpoint
    that auto-unpauses when both docs are renewed

These tests pin the integration points so a future refactor of
`utils.email` / `routes/partners` can't silently drop them.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.partners import (
    _parse_iso_date,
    _is_doc_valid,
    admin_approve_partner,
    admin_reject_partner,
    update_my_compliance,
)
from utils import partner_compliance


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "u-admin", "is_master_admin": True, "role": "owner"}


def _partner_user():
    return {"id": "u-jane", "organization_id": "gymaxis-ai-admin"}


# ── _parse_iso_date helper ────────────────────────────────────────


def test_parse_iso_date_handles_date_only_and_full_iso_and_blanks():
    assert _parse_iso_date("") is None
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("not-a-date") is None
    d = _parse_iso_date("2026-12-31")
    assert d is not None and d.year == 2026 and d.month == 12 and d.day == 31
    assert d.tzinfo == timezone.utc
    z = _parse_iso_date("2026-12-31T10:00:00Z")
    assert z is not None and z.hour == 10 and z.tzinfo == timezone.utc


def test_is_doc_valid_none_defaults_to_valid_for_rollout():
    # During rollout we don't pause partners who haven't backfilled
    # their expiry dates — but as soon as a date is set, it must be
    # in the future.
    assert _is_doc_valid(None) is True
    future = datetime.now(timezone.utc) + timedelta(days=5)
    past = datetime.now(timezone.utc) - timedelta(days=5)
    assert _is_doc_valid(future) is True
    assert _is_doc_valid(past) is False


# ── Approve fires the approved email ──────────────────────────────


def test_admin_approve_fires_approved_email():
    fake_db = MagicMock()
    partner = {
        "id": "p1", "status": "pending", "email": "jane@x.io",
        "full_name": "Jane Doe", "referral_code": "JANE-X",
    }
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("utils.partner_emails.send_application_approved", AsyncMock(return_value=True)) as send:
        result = _run(admin_approve_partner("p1", body={"level": "engineer_partner"}, user=_admin()))
    assert result == {"ok": True}
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["email"] == "jane@x.io"
    assert kwargs["referral_code"] == "JANE-X"


def test_admin_approve_email_failure_does_not_break_approve():
    """A flaky Resend response can't fail the approval — the row is
    already updated by the time we attempt the send."""
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "status": "pending", "email": "x@y", "full_name": "X"})
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("utils.partner_emails.send_application_approved", AsyncMock(side_effect=RuntimeError("boom"))):
        result = _run(admin_approve_partner("p1", body={}, user=_admin()))
    assert result == {"ok": True}


# ── Reject fires the rejected email ───────────────────────────────


def test_admin_reject_fires_rejected_email_with_reason():
    fake_db = MagicMock()
    partner = {"id": "p1", "status": "pending", "email": "tom@x", "full_name": "Tom"}
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("utils.partner_emails.send_application_rejected", AsyncMock(return_value=True)) as send:
        _run(admin_reject_partner("p1", body={"reason": "Missing insurance docs"}, user=_admin()))
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["email"] == "tom@x"
    assert kwargs["reason"] == "Missing insurance docs"


def test_admin_reject_strips_default_reason_from_email():
    """When the admin doesn't type a reason we don't want the user to
    see the placeholder 'Not approved' string — pass None instead."""
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "status": "pending", "email": "z@x", "full_name": "Z"})
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("utils.partner_emails.send_application_rejected", AsyncMock()) as send:
        _run(admin_reject_partner("p1", body={}, user=_admin()))
    assert send.call_args.kwargs["reason"] is None


# ── Self-service compliance endpoint ──────────────────────────────


def test_update_my_compliance_persists_dates_and_unpauses_when_renewed():
    fake_db = MagicMock()
    future = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
    partner = {
        "id": "p1", "user_id": "u-jane", "compliance_paused": True,
        "insurance_expires_at": datetime.now(timezone.utc) - timedelta(days=2),
        "qualifications_expires_at": None,
    }
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    captured = {}

    async def cap(filt, update):
        captured.update(update)
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=cap)
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("routes.partners._public", side_effect=lambda d: d):
        out = _run(update_my_compliance(
            body={"insurance_expires_at": future, "insurance_provider": "Hiscox"},
            user=_partner_user(),
        ))
    assert out["ok"] is True
    patch_doc = captured["$set"]
    assert isinstance(patch_doc["insurance_expires_at"], datetime)
    assert patch_doc["insurance_provider"] == "Hiscox"
    # Partner was paused, renewing insurance + no qual-expiry set → unpause.
    assert patch_doc["compliance_paused"] is False
    assert patch_doc["compliance_pause_reason"] is None


def test_update_my_compliance_rejects_empty_body():
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        with pytest.raises(Exception) as exc:
            _run(update_my_compliance(body={}, user=_partner_user()))
        assert "Nothing to update" in str(exc.value.detail)


# ── Nightly compliance sweep ──────────────────────────────────────


def _async_iter(items):
    class _C:
        def __init__(self, xs):
            self.xs = list(xs)

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self.xs):
                raise StopAsyncIteration
            x = self.xs[self._i]
            self._i += 1
            return x
    return _C(items)


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def test_sweep_fires_t7_reminder_and_does_not_pause():
    """Partner with insurance expiring in 5 days → T-7 reminder sent,
    no pause yet."""
    now = datetime.now(timezone.utc)
    expires_in_5_days = now + timedelta(days=5)
    partners = [{
        "id": "p1", "status": "approved", "email": "jane@x", "full_name": "Jane",
        "insurance_expires_at": expires_in_5_days,
    }]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("utils.partner_compliance.db", fake_db), \
         patch("utils.partner_compliance.send_compliance_reminder", AsyncMock(return_value=True)) as send:
        summary = _run(partner_compliance.sweep_once())
    assert summary["checked"] == 1
    assert summary["reminders_sent"] == 1
    assert summary["paused"] == 0
    send.assert_called_once()
    # The window saved was 7 (because 5 ≤ 7 ≤ 30).
    set_doc = fake_db.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["insurance_reminder_fired_window"] == 7


def test_sweep_pauses_partner_when_doc_expired():
    """Partner with insurance expired yesterday → fire T-0 reminder
    AND flip compliance_paused = True."""
    now = datetime.now(timezone.utc)
    expired_yesterday = now - timedelta(days=1)
    partners = [{
        "id": "p1", "status": "approved", "email": "jane@x", "full_name": "Jane",
        "insurance_expires_at": expired_yesterday,
    }]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("utils.partner_compliance.db", fake_db), \
         patch("utils.partner_compliance.send_compliance_reminder", AsyncMock(return_value=True)):
        summary = _run(partner_compliance.sweep_once())
    assert summary["paused"] == 1
    set_doc = fake_db.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["compliance_paused"] is True
    assert "insurance" in set_doc["compliance_pause_reason"]


def test_sweep_does_not_double_fire_same_window():
    """Idempotency — once the T-7 reminder has fired for a partner,
    a same-day re-run must NOT email them again."""
    now = datetime.now(timezone.utc)
    expires_in_5_days = now + timedelta(days=5)
    partners = [{
        "id": "p1", "status": "approved", "email": "jane@x", "full_name": "Jane",
        "insurance_expires_at": expires_in_5_days,
        "insurance_reminder_fired_window": 7,  # already fired
    }]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("utils.partner_compliance.db", fake_db), \
         patch("utils.partner_compliance.send_compliance_reminder", AsyncMock(return_value=True)) as send:
        summary = _run(partner_compliance.sweep_once())
    send.assert_not_called()
    assert summary["reminders_sent"] == 0
    fake_db.partner_engineers.update_one.assert_not_called()


def test_sweep_skips_partners_without_email():
    """No email → can't send reminder, but still mark the window so we
    don't re-check the same partner every night."""
    now = datetime.now(timezone.utc)
    partners = [{
        "id": "p1", "status": "approved", "email": "", "full_name": "Jane",
        "insurance_expires_at": now + timedelta(days=3),
    }]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake_db.partner_engineers.update_one = AsyncMock()
    with patch("utils.partner_compliance.db", fake_db), \
         patch("utils.partner_compliance.send_compliance_reminder", AsyncMock()) as send:
        summary = _run(partner_compliance.sweep_once())
    send.assert_not_called()
    assert summary["reminders_sent"] == 0
    # Window marker still saved.
    set_doc = fake_db.partner_engineers.update_one.call_args[0][1]["$set"]
    assert set_doc["insurance_reminder_fired_window"] == 7
