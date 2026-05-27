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


def _fake_db(
    *,
    partners,
    open_count=0,
    overdue_count=0,
    suppliers=None,
    organizations=None,
    issues_opened=0,
    issues_resolved=0,
):
    """Return a MagicMock-based fake `db` that mimics motor's async API
    for the queries the sweep makes (partner_engineers.find /
    partner_engineers.update_one / supplier_cases.count_documents /
    suppliers.find / organizations.find / issues.count_documents /
    partner_welcome_thanks_tokens.find_one + insert_one)."""
    fake = MagicMock()
    fake.partner_engineers.find = MagicMock(return_value=_make_cursor(partners))
    fake.partner_engineers.update_one = AsyncMock()
    # First call (base filter) → open_count; second (overdue filter) → overdue_count.
    fake.supplier_cases.count_documents = AsyncMock(side_effect=[open_count, overdue_count])
    fake.suppliers.find = MagicMock(return_value=_make_cursor(suppliers or []))
    fake.organizations.find = MagicMock(return_value=_make_cursor(organizations or []))
    # issues.count_documents alternates opened/resolved per gym; provide
    # a stable side_effect list that's long enough for two calls per
    # supplier row in tests.
    n = max(2, len(suppliers or []) * 2)
    fake.issues.count_documents = AsyncMock(
        side_effect=([issues_opened, issues_resolved] * n),
    )
    fake.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value=None)
    fake.partner_welcome_thanks_tokens.insert_one = AsyncMock()
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



# ── Iter 220r-2 — "While you were away" recap + thanks tokens ────


def test_sweep_surfaces_per_gym_activity_and_mints_thanks_token():
    """When a referred gym had any issue activity during the leave
    window, the digest receives a `recent_activity` row with
    opened/resolved counts and a one-click thanks_url. A token is
    persisted for the gym."""
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane Doe",
        "availability": {
            "status": "unavailable",
            "resumes_on": _today_iso(),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=10),
        },
    }]
    suppliers = [{"organization_id": "org-acme"}]
    organizations = [{"id": "org-acme", "name": "Acme Gym"}]
    fake = _fake_db(
        partners=partners,
        suppliers=suppliers,
        organizations=organizations,
        issues_opened=2,
        issues_resolved=1,
    )
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        _run(partner_return_digest.sweep_once())

    kwargs = send.call_args.kwargs
    activity = kwargs["recent_activity"]
    assert isinstance(activity, list) and len(activity) == 1
    row = activity[0]
    assert row["gym_name"] == "Acme Gym"
    assert row["organization_id"] == "org-acme"
    assert row["opened_during_leave"] == 2
    assert row["resolved_during_leave"] == 1
    assert row["thanks_url"].endswith("/api/partners/welcome-back/thanks/" + row["thanks_url"].rsplit("/", 1)[1])
    # Thanks-token persisted.
    fake.partner_welcome_thanks_tokens.insert_one.assert_called_once()
    token_doc = fake.partner_welcome_thanks_tokens.insert_one.call_args[0][0]
    assert token_doc["partner_id"] == "p1"
    assert token_doc["organization_id"] == "org-acme"
    assert token_doc["gym_name"] == "Acme Gym"
    assert token_doc["engineer_name"] == "Jane Doe"
    assert token_doc["engineer_email"] == "jane@x.io"
    assert token_doc["used_at"] is None
    # 60-day expiry on the token.
    assert (token_doc["expires_at"] - token_doc["created_at"]).days == 60


def test_sweep_skips_quiet_referred_gyms_in_recap():
    """Gyms with zero issue activity during the leave window must NOT
    appear in `recent_activity` (no point thanking a silent gym)."""
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane Doe",
        "availability": {
            "status": "unavailable",
            "resumes_on": _today_iso(),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=10),
        },
    }]
    suppliers = [{"organization_id": "org-quiet"}]
    organizations = [{"id": "org-quiet", "name": "Quiet Gym"}]
    fake = _fake_db(
        partners=partners,
        suppliers=suppliers,
        organizations=organizations,
        issues_opened=0,
        issues_resolved=0,
    )
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        _run(partner_return_digest.sweep_once())
    kwargs = send.call_args.kwargs
    assert kwargs["recent_activity"] == []
    fake.partner_welcome_thanks_tokens.insert_one.assert_not_called()


def test_sweep_reuses_existing_thanks_token_when_present():
    """If the engineer already has an unused, unexpired thanks token
    for a gym, the sweep reuses it instead of minting another."""
    partners = [{
        "id": "p1",
        "status": "approved",
        "email": "jane@x.io",
        "full_name": "Jane Doe",
        "availability": {
            "status": "unavailable",
            "resumes_on": _today_iso(),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=5),
        },
    }]
    suppliers = [{"organization_id": "org-acme"}]
    organizations = [{"id": "org-acme", "name": "Acme Gym"}]
    fake = _fake_db(
        partners=partners,
        suppliers=suppliers,
        organizations=organizations,
        issues_opened=1,
        issues_resolved=0,
    )
    fake.partner_welcome_thanks_tokens.find_one = AsyncMock(
        return_value={"token": "PRE-EXISTING-TOKEN"},
    )
    with patch("utils.partner_return_digest.db", fake), \
         patch("utils.partner_return_digest.send_welcome_back_digest",
               AsyncMock(return_value=True)) as send:
        _run(partner_return_digest.sweep_once())
    fake.partner_welcome_thanks_tokens.insert_one.assert_not_called()
    activity = send.call_args.kwargs["recent_activity"]
    assert activity[0]["thanks_url"].endswith("/PRE-EXISTING-TOKEN")


def test_while_away_block_renders_thanks_buttons_in_email():
    """Email body should include the gym name + a clickable
    'Send thanks →' link for each entry in `recent_activity`."""
    from utils import partner_emails
    captured = {}

    async def _capture(*, to, subject, html):
        captured["html"] = html
        return True

    with patch("utils.partner_emails.send_email", _capture):
        _run(partner_emails.send_welcome_back_digest(
            email="jane@x.io",
            full_name="Jane Doe",
            leave_note=None,
            days_away=7,
            my_gyms_open_count=1,
            my_gyms_overdue_count=0,
            compliance_warnings=None,
            recent_activity=[
                {
                    "gym_name": "Acme Gym",
                    "organization_id": "org-acme",
                    "opened_during_leave": 2,
                    "resolved_during_leave": 1,
                    "thanks_url": "https://api.test/api/partners/welcome-back/thanks/TKN-1",
                },
                {
                    "gym_name": "FitHQ",
                    "organization_id": "org-fithq",
                    "opened_during_leave": 1,
                    "resolved_during_leave": 0,
                    "thanks_url": "https://api.test/api/partners/welcome-back/thanks/TKN-2",
                },
            ],
            dashboard_url="https://api.test/partner-engineer",
        ))
    html = captured["html"]
    assert "While you were away" in html
    assert "Acme Gym" in html
    assert "FitHQ" in html
    assert "2 new faults" in html
    assert "1 fault resolved" in html
    assert "TKN-1" in html and "TKN-2" in html
    assert "Send thanks" in html


# ── Iter 220r-2 — thanks endpoint ────────────────────────────────


def test_thanks_endpoint_fires_email_and_marks_token_used():
    from routes.partners import welcome_back_send_thanks
    token_row = {
        "token": "TKN-1",
        "partner_id": "p1",
        "organization_id": "org-acme",
        "gym_name": "Acme Gym",
        "engineer_name": "Jane Doe",
        "engineer_email": "jane@x.io",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
        "used_at": None,
    }
    fake_db = MagicMock()
    fake_db.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value=token_row)
    fake_db.partner_welcome_thanks_tokens.update_one = AsyncMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "org-acme", "name": "Acme Gym", "primary_contact_email": "ops@acme.test",
    })

    sent_emails = []

    async def _capture(*, to, subject, html):
        sent_emails.append({"to": to, "subject": subject, "html": html})
        return True

    with patch("routes.partners.db", fake_db), \
         patch("utils.email.send_email", _capture):
        resp = _run(welcome_back_send_thanks("TKN-1"))

    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "Thanks sent" in body or "Acme Gym" in body
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "ops@acme.test"
    assert "Jane Doe" in sent_emails[0]["html"]
    assert "Acme Gym" in sent_emails[0]["html"]
    # Token flipped to used.
    update_set = fake_db.partner_welcome_thanks_tokens.update_one.call_args[0][1]["$set"]
    assert update_set["outcome"] == "sent"
    assert update_set["recipient"] == "ops@acme.test"
    assert update_set["used_at"] is not None


def test_thanks_endpoint_rejects_unknown_token():
    from routes.partners import welcome_back_send_thanks
    fake_db = MagicMock()
    fake_db.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db):
        resp = _run(welcome_back_send_thanks("NOPE"))
    assert resp.status_code == 404
    assert "not recognised" in resp.body.decode("utf-8").lower()


def test_thanks_endpoint_idempotent_after_used():
    """Already-used tokens render a friendly confirmation rather than
    re-firing the email."""
    from routes.partners import welcome_back_send_thanks
    fake_db = MagicMock()
    fake_db.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value={
        "token": "TKN-2",
        "partner_id": "p1",
        "organization_id": "org-acme",
        "gym_name": "Acme Gym",
        "engineer_name": "Jane Doe",
        "engineer_email": "jane@x.io",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
        "used_at": datetime.now(timezone.utc),
    })
    fake_db.partner_welcome_thanks_tokens.update_one = AsyncMock()
    captured = []

    async def _capture(*args, **kwargs):
        captured.append((args, kwargs))
        return True

    with patch("routes.partners.db", fake_db), \
         patch("utils.email.send_email", _capture):
        resp = _run(welcome_back_send_thanks("TKN-2"))
    assert resp.status_code == 200
    assert "Already sent" in resp.body.decode("utf-8")
    assert captured == []
    fake_db.partner_welcome_thanks_tokens.update_one.assert_not_called()


def test_thanks_endpoint_rejects_expired_token():
    from routes.partners import welcome_back_send_thanks
    fake_db = MagicMock()
    fake_db.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value={
        "token": "TKN-OLD",
        "partner_id": "p1",
        "organization_id": "org-acme",
        "gym_name": "Acme Gym",
        "engineer_name": "Jane Doe",
        "engineer_email": "jane@x.io",
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
        "used_at": None,
    })
    with patch("routes.partners.db", fake_db):
        resp = _run(welcome_back_send_thanks("TKN-OLD"))
    assert resp.status_code == 410
    assert "expired" in resp.body.decode("utf-8").lower()


def test_thanks_endpoint_handles_missing_recipient():
    """Gym without a primary contact → token still marked used,
    response explains why no email went out."""
    from routes.partners import welcome_back_send_thanks
    fake_db = MagicMock()
    fake_db.partner_welcome_thanks_tokens.find_one = AsyncMock(return_value={
        "token": "TKN-NO-EMAIL",
        "partner_id": "p1",
        "organization_id": "org-acme",
        "gym_name": "Acme Gym",
        "engineer_name": "Jane Doe",
        "engineer_email": "jane@x.io",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
        "used_at": None,
    })
    fake_db.partner_welcome_thanks_tokens.update_one = AsyncMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "org-acme", "name": "Acme Gym",
        # No primary_contact_email / admin_email / owner_email
    })
    with patch("routes.partners.db", fake_db):
        resp = _run(welcome_back_send_thanks("TKN-NO-EMAIL"))
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "No contact" in body or "doesn't have a primary contact" in body
    update_set = fake_db.partner_welcome_thanks_tokens.update_one.call_args[0][1]["$set"]
    assert update_set["outcome"] == "no-recipient"
