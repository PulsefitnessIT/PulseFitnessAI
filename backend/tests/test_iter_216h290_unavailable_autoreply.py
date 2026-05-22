"""Iter 216h290 — Auto-on-leave responder for engineer contact requests.

Closes the Gap-10 follow-up: when a customer expresses interest via
``/partners/find-engineers/{id}/request-contact`` and the targeted
engineer is currently flagged unavailable, we fire a polite Resend
autoreply (with up to 3 in-area alternatives) so the customer
isn't left wondering. The contact-request row is still persisted —
this is purely an additive courtesy email.

Pins covered
------------
* `_format_leave_date` renders ISO date as "5 March"
* `_alternatives_block` empty / non-empty rendering
* `_alternative_engineers_for` filters by postcode AND skips
  unavailable engineers + the requested partner itself
* `_maybe_send_unavailable_autoreply` no-ops when the engineer
  is available
* When unavailable: autoreply fires with correct payload AND
  the contact-request row is stamped with `auto_reply_sent_at`
* When the requester has no email: no autoreply, no crash
* `request_engineer_contact` swallows Resend failures
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _format_leave_date ─────────────────────────────────────────────


def test_format_leave_date_renders_human_readable():
    from utils.partner_emails import _format_leave_date
    assert _format_leave_date("2026-03-05") == "5 March"
    assert _format_leave_date("2026-12-25") == "25 December"


def test_format_leave_date_passes_through_garbage():
    from utils.partner_emails import _format_leave_date
    assert _format_leave_date(None) is None
    assert _format_leave_date("") is None
    assert _format_leave_date("not-a-date") == "not-a-date"


# ── _alternatives_block ────────────────────────────────────────────


def test_alternatives_block_empty_when_no_rows():
    from utils.partner_emails import _alternatives_block
    assert _alternatives_block([]) == ""
    assert _alternatives_block([{"full_name": "Bob"}]).startswith("<p")


def test_alternatives_block_includes_name_company_area():
    from utils.partner_emails import _alternatives_block
    html = _alternatives_block([
        {"full_name": "Sue Engineer", "company_name": "BiceptHub", "service_postcode_area": "M1"},
    ])
    assert "Sue Engineer" in html
    assert "BiceptHub" in html
    assert "M1" in html


def test_alternatives_block_caps_at_three():
    from utils.partner_emails import _alternatives_block
    html = _alternatives_block([
        {"full_name": f"Eng {i}"} for i in range(7)
    ])
    # 3 list items only — count <li>
    assert html.count("<li") == 3


# ── _alternative_engineers_for ─────────────────────────────────────


def _cur(rows):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def test_alternative_engineers_skips_unavailable_and_self():
    from routes.partners import _alternative_engineers_for
    rows = [
        # Self — must be excluded by the query (we still verify the filter)
        {"id": "p-self", "full_name": "Self", "service_postcode": "M1 1AA"},
        # In-area + available — keeper
        {"id": "p-ok", "full_name": "Available Eng", "company_name": "OK Ltd",
         "service_postcode": "M1 2BB", "availability": {"status": "available"}},
        # In-area but on leave — must be filtered out
        {"id": "p-leave", "full_name": "Leave Eng",
         "service_postcode": "M1 3CC",
         "availability": {"status": "unavailable", "resumes_on": "2099-01-01"}},
        # Out-of-area — must be filtered out
        {"id": "p-far", "full_name": "Far Eng",
         "service_postcode": "EH1 1AA", "availability": {"status": "available"}},
    ]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_cur(rows))
    with patch("routes.partners.db", fake_db):
        out = _run(_alternative_engineers_for(partner_id="p-self", postcode="M1 9ZZ", limit=3))
    # The Mongo $ne filter is applied by the query — verify it's set up right
    flt = fake_db.partner_engineers.find.call_args[0][0]
    assert flt.get("id") == {"$ne": "p-self"}
    assert flt.get("status") == "approved"
    # Only the in-area available engineer survives
    assert [r["id"] for r in out] == ["p-ok"]
    assert out[0]["service_postcode_area"] == "M1"


def test_alternative_engineers_returns_empty_for_blank_postcode():
    from routes.partners import _alternative_engineers_for
    out = _run(_alternative_engineers_for(partner_id="p1", postcode="", limit=3))
    assert out == []


def test_alternative_engineers_caps_at_limit():
    from routes.partners import _alternative_engineers_for
    rows = [
        {"id": f"p{i}", "full_name": f"Eng {i}", "service_postcode": "M1 1AA",
         "availability": {"status": "available"}}
        for i in range(10)
    ]
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_cur(rows))
    with patch("routes.partners.db", fake_db):
        out = _run(_alternative_engineers_for(partner_id="self", postcode="M1 2BB", limit=3))
    assert len(out) == 3


# ── _maybe_send_unavailable_autoreply ──────────────────────────────


def test_autoreply_noop_when_engineer_available():
    from routes.partners import _maybe_send_unavailable_autoreply
    sender = AsyncMock(return_value=True)
    with patch("utils.partner_emails.send_engineer_unavailable_autoreply", sender):
        _run(_maybe_send_unavailable_autoreply(
            partner={"id": "p1", "full_name": "Jane",
                     "availability": {"status": "available"}},
            requester={"id": "u-jane", "email": "x@y.io"},
            request_id="r1",
        ))
    sender.assert_not_awaited()


def test_autoreply_noop_when_requester_has_no_email():
    from routes.partners import _maybe_send_unavailable_autoreply
    sender = AsyncMock(return_value=True)
    with patch("utils.partner_emails.send_engineer_unavailable_autoreply", sender):
        _run(_maybe_send_unavailable_autoreply(
            partner={"id": "p1", "full_name": "Jane",
                     "availability": {"status": "unavailable", "resumes_on": "2099-06-04"}},
            requester={"id": "u-no-email"},
            request_id="r1",
        ))
    sender.assert_not_awaited()


def test_autoreply_fires_with_correct_payload_and_stamps_request():
    from routes.partners import _maybe_send_unavailable_autoreply
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_cur([
        {"id": "p-alt", "full_name": "Alt Eng", "company_name": "Alt Ltd",
         "service_postcode": "M1 2BB", "availability": {"status": "available"}},
    ]))
    captured_update = {}
    fake_db.partner_contact_requests.update_one = AsyncMock(
        side_effect=lambda _f, upd: captured_update.update(upd),
    )
    sender = AsyncMock(return_value=True)
    with patch("routes.partners.db", fake_db), \
         patch("utils.partner_emails.send_engineer_unavailable_autoreply", sender):
        _run(_maybe_send_unavailable_autoreply(
            partner={
                "id": "p1", "full_name": "Jane Doe", "company_name": "JD Eng",
                "service_postcode": "M1 1AA",
                "availability": {"status": "unavailable", "resumes_on": "2099-06-04",
                                  "note": "On annual leave"},
            },
            requester={"id": "u-bob", "email": "bob@gym.io", "full_name": "Bob Smith"},
            request_id="r1",
        ))
    sender.assert_awaited_once()
    kwargs = sender.await_args.kwargs
    assert kwargs["to_email"] == "bob@gym.io"
    assert kwargs["engineer_first_name"] == "Jane"
    assert kwargs["engineer_company"] == "JD Eng"
    assert kwargs["resumes_on"] == "2099-06-04"
    assert kwargs["leave_note"] == "On annual leave"
    assert kwargs["requester_first_name"] == "Bob"
    assert len(kwargs["alternatives"]) == 1
    assert kwargs["alternatives"][0]["id"] == "p-alt"
    # Contact-request row got stamped
    assert "auto_reply_sent_at" in captured_update["$set"]


def test_autoreply_skips_stamp_if_email_send_returns_false():
    """If send_email returns False (rate limited / Resend down), we
    don't stamp the row so a later worker can retry."""
    from routes.partners import _maybe_send_unavailable_autoreply
    fake_db = MagicMock()
    fake_db.partner_engineers.find = MagicMock(return_value=_cur([]))
    fake_db.partner_contact_requests.update_one = AsyncMock()
    with patch("routes.partners.db", fake_db), \
         patch("utils.partner_emails.send_engineer_unavailable_autoreply", AsyncMock(return_value=False)):
        _run(_maybe_send_unavailable_autoreply(
            partner={"id": "p1", "full_name": "Jane",
                     "availability": {"status": "unavailable", "resumes_on": "2099-06-04"}},
            requester={"id": "u-bob", "email": "bob@gym.io"},
            request_id="r1",
        ))
    fake_db.partner_contact_requests.update_one.assert_not_awaited()


# ── request_engineer_contact swallows autoreply failures ───────────


def test_request_engineer_contact_swallows_autoreply_error():
    """Resend going down must not break the customer's form submission."""
    from routes.partners import request_engineer_contact
    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "portal_type": "gymaxis"})
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "email": "jane@x.io", "full_name": "Jane",
        "service_postcode": "M1 1AA", "company_name": "JD",
        "availability": {"status": "unavailable", "resumes_on": "2099-06-04"},
    })
    fake_db.partner_contact_requests.insert_one = AsyncMock()
    user = {"id": "u-bob", "email": "bob@gym.io", "organization_id": "org-1",
            "is_master_admin": False, "role": "owner"}
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._is_pulse_org", AsyncMock(return_value=False)), \
         patch("routes.partners._require_gymaxis_only", lambda u: None), \
         patch("routes.partners._maybe_send_unavailable_autoreply",
               AsyncMock(side_effect=RuntimeError("Resend down"))):
        out = _run(request_engineer_contact("p1", body={"note": "hi"}, user=user))
    # Form still succeeded
    assert out["ok"] is True
    assert out["request"]["partner_id"] == "p1"
