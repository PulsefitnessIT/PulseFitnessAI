"""Regression test for the corporate-CRM quote email bug.

`send_email()` previously had no `cc` parameter, so the
`POST /crm/v2/quotes/{id}/send-email` endpoint (which passes `cc=`) raised
`TypeError: send_email() got an unexpected keyword argument 'cc'` and reps
could not send quotes to customers. This test asserts `send_email` accepts
`cc` and forwards it to the Resend payload.
"""
import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import utils.email as email_mod


def test_send_email_accepts_cc_param():
    sig = inspect.signature(email_mod.send_email)
    assert "cc" in sig.parameters, "send_email must accept a `cc` argument (quote send-email depends on it)"


def test_send_email_forwards_cc_to_resend():
    captured = {}

    def fake_send(params):
        captured.update(params)
        return {"id": "test-id"}

    async def _run():
        with patch.object(email_mod, "RESEND_API_KEY", "test-key"), \
             patch.object(email_mod, "SENDER_EMAIL", "noreply@gymaxisai.com"), \
             patch.object(email_mod, "_record_email_event", AsyncMock()), \
             patch.object(email_mod.resend.Emails, "send", side_effect=fake_send):
            return await email_mod.send_email(
                to="buyer@example.com",
                subject="Quote QT-TEST",
                html="<p>hi</p>",
                cc=["manager@example.com"],
            )

    ok = asyncio.run(_run())
    assert ok is not False
    assert captured.get("cc") == ["manager@example.com"], "cc must be forwarded to the Resend payload"
