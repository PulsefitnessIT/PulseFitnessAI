"""Pulse Fitness 1-pager send flow — iteration 217."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_send_pulse_pager_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/send",
        headers=_h(pulse_pro_token),
        json={"variant": "sales", "to_email": "x@example.com"},
        timeout=10,
    )
    assert r.status_code == 403


def test_send_pulse_pager_rejects_bad_variant(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/send",
        headers=_h(master_admin_token_session),
        json={"variant": "bogus", "to_email": "x@example.com"},
        timeout=10,
    )
    assert r.status_code == 400


def test_send_pulse_pager_requires_recipient(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/send",
        headers=_h(master_admin_token_session),
        json={"variant": "sales", "to_email": " "},
        timeout=10,
    )
    assert r.status_code == 400


def test_send_pulse_pager_creates_share_and_public_works(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    payload = {
        "variant": "trust",
        "to_email": "iter217+pytest@example.com",
        "message": "Pytest send.",
        "ttl_days": 14,
    }
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/send",
        headers=headers,
        json=payload,
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipient"] == payload["to_email"]
    assert body["variant"] == "trust"
    assert body["share_id"]
    assert "/api/public/sales-pack-share/" in body["share_url"]

    # TTL clamp.
    exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(days=13) < delta < timedelta(days=15)

    # Public download — no auth.
    token = body["share_url"].rsplit("/", 1)[-1]
    r2 = requests.get(f"{base}/api/public/sales-pack-share/{token}", timeout=20)
    assert r2.status_code == 200
    assert r2.content[:4] == b"%PDF"
    assert len(r2.content) > 1000


def test_send_pulse_pager_ttl_clamped(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/send",
        headers=headers,
        json={"variant": "sales", "to_email": "iter217+ttl@example.com", "ttl_days": 9999},
        timeout=20,
    )
    assert r.status_code == 200
    exp = datetime.fromisoformat(r.json()["expires_at"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert delta < timedelta(days=181)
    assert delta > timedelta(days=179)


def test_public_sales_pack_share_unknown_token_returns_404():
    base = _test_backend_url()
    r = requests.get(f"{base}/api/public/sales-pack-share/does-not-exist-token", timeout=10)
    assert r.status_code == 404


def test_public_sales_pack_share_rejects_invoice_share_token(master_admin_token_session):
    """Tokens minted by the invoice-send flow must NOT resolve via the
    sales-pack public endpoint (kind filter must do its job)."""
    base = _test_backend_url()
    headers = _h(master_admin_token_session)

    # Mint an invoice share so we have a token of the wrong kind.
    from tests.conftest import TOTTENHAM_GREEN_ORG_ID
    org_id = TOTTENHAM_GREEN_ORG_ID
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
    inv_r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice",
        headers=headers,
        json={},
        timeout=15,
    )
    invoice_id = inv_r.json()["invoice"]["id"]
    send_r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/send",
        headers=headers,
        json={"to_email": "iter217+wrong-kind@example.com"},
        timeout=15,
    )
    invoice_token = send_r.json()["share_url"].rsplit("/", 1)[-1]

    # Sales-pack public endpoint must reject it.
    r = requests.get(f"{base}/api/public/sales-pack-share/{invoice_token}", timeout=10)
    assert r.status_code == 404
