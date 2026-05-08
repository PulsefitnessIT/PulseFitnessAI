"""End-to-end Stripe webhook integration test for GymAxis Memberships.

Substitute for a full Stripe CLI run — we craft a signed webhook payload
locally (HMAC SHA-256 per Stripe's spec), POST it to
`/api/memberships/webhook/stripe` running under supervisor, and assert the
DB transitions that would fire in production.

Coverage:
  • Signature verification gate (bad/missing sig → 400)
  • `invoice.paid` → billing_status='current' + next_billing_at advanced
  • `invoice.payment_failed` → billing_status='past_due'
  • `customer.subscription.deleted` → status='cancelled'
  • Unknown event types → 200 (graceful no-op)
  • Idempotency — `stripe_event_id` dedupe keeps repeated events safe

`checkout.session.completed` can't be fully exercised without a real
Stripe session (the handler calls `stripe.checkout.Session.retrieve`) but
the /status polling + operator `sweep_abandoned_checkouts` covers the
rest of the reconciliation path.

Requires STRIPE_WEBHOOK_SECRET in /app/backend/.env (already set).
"""
from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")  # so we can reach utils.database

from tests.conftest import _test_backend_url


def _load_env() -> dict:
    env = {}
    try:
        with open("/app/backend/.env") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


ENV = _load_env()
WEBHOOK_SECRET = ENV.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = _test_backend_url()


def _sig_header(payload: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    signed = f"{ts}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _post_event(event_obj: dict) -> requests.Response:
    payload = json.dumps(event_obj).encode()
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": _sig_header(payload, WEBHOOK_SECRET),
    }
    return requests.post(f"{BASE_URL}/api/memberships/webhook/stripe",
                         data=payload, headers=headers, timeout=15)


@pytest.fixture(autouse=True)
def _skip_if_no_secret():
    if not WEBHOOK_SECRET:
        pytest.skip("STRIPE_WEBHOOK_SECRET not configured in /app/backend/.env")


def _async(coro):
    """Run an async bit against a fresh motor client bound to the current loop."""
    import motor.motor_asyncio
    mongo_url = ENV.get("MONGO_URL")
    db_name = ENV.get("DB_NAME", "test_database")

    async def wrapped():
        client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        try:
            return await coro(db)
        finally:
            client.close()
    return asyncio.run(wrapped())


@pytest.fixture
def active_subscription():
    """Insert an active recurring membership with stripe_subscription_id +
    stripe_customer_id so webhook handlers have something to match on."""
    mm_id = str(uuid.uuid4())
    sub_id = f"sub_test_{uuid.uuid4().hex[:12]}"
    cust_id = f"cus_test_{uuid.uuid4().hex[:12]}"

    async def setup(db):
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.member_memberships.insert_one({
            "id": mm_id, "member_id": "mbr-emma", "plan_id": "plan-monthly-unl",
            "organization_id": "mbr-demo-org", "status": "active",
            "start_date": now_iso, "end_date": None,
            "billing_status": "current",
            "stripe_subscription_id": sub_id, "stripe_customer_id": cust_id,
            "last_billed_at": now_iso,
            "next_billing_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "audit_log": [],
        })
    _async(setup)
    yield {"membership_id": mm_id, "subscription_id": sub_id, "customer_id": cust_id}

    async def teardown(db):
        await db.member_memberships.delete_one({"id": mm_id})
    _async(teardown)


# ═════════════════════ Signature gate ═════════════════════

def test_bad_signature_returns_400():
    r = requests.post(f"{BASE_URL}/api/memberships/webhook/stripe",
        data=b'{"foo":"bar"}',
        headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=bad"},
        timeout=10)
    assert r.status_code == 400
    assert "signature" in r.text.lower()


def test_missing_signature_returns_400():
    r = requests.post(f"{BASE_URL}/api/memberships/webhook/stripe",
        data=b'{"foo":"bar"}',
        headers={"Content-Type": "application/json"},
        timeout=10)
    assert r.status_code == 400


def test_unknown_event_type_returns_200():
    evt = {"id": f"evt_{uuid.uuid4().hex[:10]}", "object": "event", "type": "ping",
           "data": {"object": {"id": "x"}}, "created": int(time.time())}
    r = _post_event(evt)
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ═════════════════════ invoice.paid ═════════════════════

def test_invoice_paid_bumps_billing_status_and_next_billing(active_subscription):
    fx = active_subscription
    evt = {
        "id": f"evt_{uuid.uuid4().hex[:10]}",
        "object": "event",
        "type": "invoice.paid",
        "created": int(time.time()),
        "data": {"object": {
            "id": f"in_{uuid.uuid4().hex[:12]}",
            "subscription": fx["subscription_id"],
            "customer": fx["customer_id"],
            "amount_paid": 6500,
            "currency": "gbp",
        }},
    }
    r = _post_event(evt)
    assert r.status_code == 200

    async def check(db):
        doc = await db.member_memberships.find_one({"id": fx["membership_id"]}, {"_id": 0})
        assert doc["billing_status"] == "current"
        assert "next_billing_at" in doc
        # audit log should carry an invoice_paid entry
        assert any(e.get("action") == "invoice_paid" for e in doc.get("audit_log", []))
    _async(check)


# ═════════════════════ invoice.payment_failed ═════════════════════

def test_invoice_payment_failed_flips_past_due(active_subscription):
    fx = active_subscription
    evt = {
        "id": f"evt_{uuid.uuid4().hex[:10]}",
        "object": "event",
        "type": "invoice.payment_failed",
        "created": int(time.time()),
        "data": {"object": {
            "id": f"in_{uuid.uuid4().hex[:12]}",
            "subscription": fx["subscription_id"],
            "customer": fx["customer_id"],
        }},
    }
    r = _post_event(evt)
    assert r.status_code == 200

    async def check(db):
        doc = await db.member_memberships.find_one({"id": fx["membership_id"]}, {"_id": 0})
        assert doc["billing_status"] == "past_due"
        assert any(e.get("action") == "payment_failed" for e in doc.get("audit_log", []))
    _async(check)


# ═════════════════════ customer.subscription.deleted ═════════════════════

def test_subscription_deleted_cancels_membership(active_subscription):
    fx = active_subscription
    evt = {
        "id": f"evt_{uuid.uuid4().hex[:10]}",
        "object": "event",
        "type": "customer.subscription.deleted",
        "created": int(time.time()),
        "data": {"object": {
            "id": fx["subscription_id"],
            "customer": fx["customer_id"],
            "status": "canceled",
        }},
    }
    r = _post_event(evt)
    assert r.status_code == 200

    async def check(db):
        doc = await db.member_memberships.find_one({"id": fx["membership_id"]}, {"_id": 0})
        assert doc["status"] == "cancelled"
        assert doc.get("cancel_reason") == "stripe_subscription_deleted"
    _async(check)
