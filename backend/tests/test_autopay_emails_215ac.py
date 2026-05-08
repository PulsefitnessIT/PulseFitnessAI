"""Iter 215ac — Auto-Bill email receipts.

Ensures:
  - _send_autopay_success_email hits send_email with a Paid subject
  - _send_autopay_decline_email hits send_email with Action needed subject
  - Both silently skip when the member has no email
"""
import asyncio
from unittest.mock import AsyncMock, patch

from routes.memberships import family_autopay


def _member(email="p@example.com"):
    return {"id": "m1", "first_name": "Pat", "last_name": "K", "email": email}


def _invoice(period="2026-04", total=5000, org_id="org1"):
    return {"id": "inv1", "period": period, "total_pence": total, "organization_id": org_id}


def test_success_email_sent_with_paid_subject():
    org_find = AsyncMock(return_value={"name": "Rising Stars Dance", "primary_color": "#E91E63"})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", type("X", (), {"find_one": org_find})), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_success_email(
            member=_member(), invoice=_invoice(total=4500),
            charged_pence=4500, wallet_applied_pence=0,
            card_brand="visa", card_last4="4242",
        ))
    assert send.await_count == 1
    to, subj, html = send.await_args.args
    assert to == "p@example.com"
    assert "Paid" in subj
    assert "April 2026" in subj
    assert "£45.00" in html
    assert "VISA •••• 4242" in html


def test_success_email_shows_wallet_row_when_applied():
    org_find = AsyncMock(return_value={"name": "Studio", "primary_color": "#00B2C7"})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", type("X", (), {"find_one": org_find})), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_success_email(
            member=_member(), invoice=_invoice(total=6000),
            charged_pence=3000, wallet_applied_pence=3000,
            card_brand="mastercard", card_last4="1111",
        ))
    html = send.await_args.args[2]
    assert "Wallet applied" in html
    assert "−£30.00" in html


def test_success_email_without_email_noop():
    org_find = AsyncMock(return_value={})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", type("X", (), {"find_one": org_find})), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_success_email(
            member=_member(email=""), invoice=_invoice(),
            charged_pence=5000, wallet_applied_pence=0,
            card_brand="visa", card_last4="4242",
        ))
    send.assert_not_awaited()


def test_decline_email_sent_with_action_subject():
    org_find = AsyncMock(return_value={"name": "Pulse Pilates"})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", type("X", (), {"find_one": org_find})), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_decline_email(
            member=_member(), invoice=_invoice(period="2026-05"),
            error_msg="Your card was declined.",
            card_brand="visa", card_last4="4242",
        ))
    assert send.await_count == 1
    to, subj, html = send.await_args.args
    assert "Action needed" in subj
    assert "May 2026" in subj
    assert "Your card was declined." in html
    assert "VISA •••• 4242" in html


def test_decline_email_without_email_noop():
    org_find = AsyncMock(return_value={})
    send = AsyncMock()
    with patch.object(family_autopay.db, "organizations", type("X", (), {"find_one": org_find})), \
         patch.object(family_autopay, "send_email", new=send):
        asyncio.run(family_autopay._send_autopay_decline_email(
            member=_member(email=""), invoice=_invoice(),
            error_msg="fail", card_brand=None, card_last4=None,
        ))
    send.assert_not_awaited()


def test_period_label_fallbacks():
    assert family_autopay._period_label("2026-01") == "January 2026"
    assert family_autopay._period_label("bad") == "bad"
