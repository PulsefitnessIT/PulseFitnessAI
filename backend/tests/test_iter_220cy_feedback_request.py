"""Iter 220cy — NPS feedback request email.

Pins ``POST /api/svc/cases/{case_id}/feedback-request/send``:

* 404 on missing case.
* 400 when the case has no customer email.
* Generates / reuses a public tracking token and links to
  ``{PUBLIC_APP_URL}/track/{token}`` in the email body.
* Skips (without erroring) when the request has already been sent.
* Skips when the customer already left a rating.
* On success: persists ``feedback_request_sent_at`` +
  ``feedback_request_sent_to`` on the case + appends an audit event.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1"):
    return {"id": uid, "organization_id": org,
            "full_name": "Eng", "email": "e@x"}


def _case(**overrides):
    return {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100",
        "customer_name": "Sarah Jones",
        "customer_email": "sarah@acme.com",
        "organization_name": "Acme Service Co",
        **overrides,
    }


def _stub_db(case):
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=case)
    fdb.svc_cases.update_one = AsyncMock()
    return fdb


def test_send_feedback_request_404s_on_missing_case():
    fdb = _stub_db(None)

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import send_feedback_request
            try:
                await send_feedback_request("nope", data=None, user=_user())
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 404

    _run(run())


def test_send_feedback_request_400s_when_no_customer_email():
    fdb = _stub_db(_case(customer_email=""))

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import send_feedback_request
            try:
                await send_feedback_request(
                    "case-1", data=None, user=_user(),
                )
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 400

    _run(run())


def test_send_feedback_request_skips_when_already_sent():
    fdb = _stub_db(_case(feedback_request_sent_at="2026-05-30T08:00:00Z"))

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import send_feedback_request
            return await send_feedback_request(
                "case-1", data=None, user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    assert out["skipped"] is True
    assert out["reason"] == "already_sent"


def test_send_feedback_request_skips_when_customer_already_rated():
    fdb = _stub_db(_case(customer_rating=5))

    async def run():
        with patch("routes.svc.service_report.db", fdb), \
             patch(
                 "routes.svc.public_tracking._mint_or_get_token",
                 AsyncMock(return_value="tok-abc"),
             ):
            from routes.svc.service_report import send_feedback_request
            return await send_feedback_request(
                "case-1", data=None, user=_user(),
            )

    out = _run(run())
    assert out["skipped"] is True
    assert out["reason"] == "already_rated"


def test_send_feedback_request_happy_path_emails_and_persists():
    fdb = _stub_db(_case())
    mailer = AsyncMock(return_value=True)

    async def run():
        with patch("routes.svc.service_report.db", fdb), \
             patch(
                 "routes.svc.public_tracking._mint_or_get_token",
                 AsyncMock(return_value="tok-abc"),
             ), \
             patch(
                 "routes.svc.service_report.send_email",
                 mailer,
             ), \
             patch(
                 "utils.svc_state.append_event",
                 AsyncMock(),
             ):
            from routes.svc.service_report import send_feedback_request
            return await send_feedback_request(
                "case-1", data=None, user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    assert out["to"] == "sarah@acme.com"
    assert "tok-abc" in out["track_url"]
    # Email body must point at the public tracking page.
    call_kwargs = mailer.await_args.kwargs
    assert "tok-abc" in call_kwargs["html"]
    assert "Leave feedback" in call_kwargs["html"]
    # Case is updated with the sent_at marker.
    update_call = fdb.svc_cases.update_one.await_args
    set_doc = update_call.args[1]["$set"]
    assert set_doc["feedback_request_sent_to"] == "sarah@acme.com"
    assert "feedback_request_sent_at" in set_doc


def test_send_feedback_request_502s_when_mailer_fails():
    fdb = _stub_db(_case())

    async def run():
        with patch("routes.svc.service_report.db", fdb), \
             patch(
                 "routes.svc.public_tracking._mint_or_get_token",
                 AsyncMock(return_value="tok-abc"),
             ), \
             patch(
                 "routes.svc.service_report.send_email",
                 AsyncMock(return_value=False),
             ):
            from routes.svc.service_report import send_feedback_request
            try:
                await send_feedback_request(
                    "case-1", data=None, user=_user(),
                )
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 502

    _run(run())


def test_send_feedback_request_endpoint_is_registered():
    """Contract guard so the fast-path close-out can rely on the
    path being stable."""
    from routes.svc.service_report import router
    paths = [
        (r.path, sorted(r.methods))
        for r in router.routes if hasattr(r, "path")
    ]
    assert any(
        p.endswith("/svc/cases/{case_id}/feedback-request/send")
        and "POST" in m
        for p, m in paths
    )
