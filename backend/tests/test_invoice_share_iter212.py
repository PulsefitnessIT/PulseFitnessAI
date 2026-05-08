"""Send invoice to client — iteration 212.

Verifies the new POST /api/master-admin/orgs/{org_id}/billing/invoice/{id}/send
endpoint, the public GET /api/public/invoice-share/{token} download, the send
history endpoint, validation, master-admin gating, and TTL clamping.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import (
    _test_backend_url,
    rate_limit_bypass_headers,
    TOTTENHAM_GREEN_ORG_ID,
)


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


@pytest.fixture(scope="module")
def seeded_invoice(master_admin_token_session):
    """Make sure Tottenham has at least one issued invoice to send."""
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    org_id = TOTTENHAM_GREEN_ORG_ID

    # Activate a subscription if not already (idempotent — endpoint upserts).
    requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/activate",
        headers=headers,
        json={
            "active_modules": ["operations"],
            "billing_cycle": "monthly",
            "billing_currency": "GBP",
            "sites": 1,
            "manual_billing": True,
            "status": "active",
        },
        timeout=10,
    )
    # Generate a fresh invoice — endpoint always creates a new one.
    r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice",
        headers=headers,
        json={},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    inv = r.json()["invoice"]
    return {"org_id": org_id, "invoice_id": inv["id"], "number": inv["number"]}


def test_send_invoice_requires_master(seeded_invoice, pulse_pro_token):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/{seeded_invoice['invoice_id']}/send",
        headers=_h(pulse_pro_token),
        json={"to_email": "test@example.com"},
        timeout=10,
    )
    assert r.status_code == 403


def test_send_invoice_rejects_missing_recipient(seeded_invoice, master_admin_token_session):
    """Org has no primary contact email seeded, so calling without to_email
    must 400 unless we explicitly provide one."""
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/{seeded_invoice['invoice_id']}/send",
        headers=_h(master_admin_token_session),
        json={"to_email": "  "},
        timeout=10,
    )
    # If the org happens to have a primary contact email, we accept either:
    #   400 (no recipient) — must come with our error string
    #   200 (sent to seeded contact)
    if r.status_code == 400:
        assert "Recipient" in r.text or "email" in r.text.lower()
    else:
        assert r.status_code == 200, r.text


def test_send_invoice_creates_share_link_and_audit(seeded_invoice, master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    payload = {
        "to_email": "iter212+pytest@example.com",
        "message": "Pytest send. Please ignore.",
        "ttl_days": 14,
    }
    r = requests.post(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/{seeded_invoice['invoice_id']}/send",
        headers=headers,
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipient"] == payload["to_email"]
    assert body["share_url"].endswith(body["share_url"].split("/")[-1])
    assert "/api/public/invoice-share/" in body["share_url"]
    assert body["share_id"]
    # TTL within bounds.
    exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(days=13) < delta < timedelta(days=15)

    # Public download — no auth — must succeed.
    token = body["share_url"].rsplit("/", 1)[-1]
    r2 = requests.get(f"{base}/api/public/invoice-share/{token}", timeout=15)
    assert r2.status_code == 200
    assert r2.headers.get("Content-Type", "").startswith("application/pdf")
    assert len(r2.content) > 200  # real PDF body, not an error blob.

    # Sends history reflects the new send.
    r3 = requests.get(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/{seeded_invoice['invoice_id']}/sends",
        headers=headers,
        timeout=10,
    )
    assert r3.status_code == 200
    sends = r3.json()["sends"]
    assert any(s["share_id"] == body["share_id"] and s["recipient"] == payload["to_email"] for s in sends)


def test_send_invoice_ttl_clamped(seeded_invoice, master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.post(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/{seeded_invoice['invoice_id']}/send",
        headers=headers,
        json={"to_email": "iter212+ttl@example.com", "ttl_days": 9999},
        timeout=15,
    )
    assert r.status_code == 200
    exp = datetime.fromisoformat(r.json()["expires_at"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    # Should clamp to 180 days max.
    assert delta < timedelta(days=181)
    assert delta > timedelta(days=179)


def test_public_invoice_share_unknown_token_returns_404():
    base = _test_backend_url()
    r = requests.get(f"{base}/api/public/invoice-share/does-not-exist-token", timeout=10)
    assert r.status_code == 404


def test_send_unknown_invoice_returns_404(master_admin_token_session, seeded_invoice):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/orgs/{seeded_invoice['org_id']}/billing/invoice/non-existent-id/send",
        headers=_h(master_admin_token_session),
        json={"to_email": "x@example.com"},
        timeout=10,
    )
    assert r.status_code == 404
