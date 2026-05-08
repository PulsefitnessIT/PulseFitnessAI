"""Collections dashboard — iteration 214.

Verifies GET /api/master-admin/collections/dashboard:
  • Returns required shape (buckets, top_overdue, reminders_mtd).
  • Aging logic: invoice 10d past due lands in the 1_30 bucket and
    appears in top_overdue with the right balance.
  • MTD reminders count picks up our seeded dunning share-link rows.
  • Master-admin gating returns 403 for non-master.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
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


@pytest.fixture
def overdue_invoice_with_reminder(master_admin_token_session):
    """Seed: one back-dated overdue invoice + one dunning share link
    timestamped this month (so it counts towards reminders_mtd)."""
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
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
    r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice",
        headers=headers,
        json={},
        timeout=15,
    )
    inv = r.json()["invoice"]

    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    past_due = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    async def _setup():
        await db.org_billing_invoices.update_one(
            {"id": inv["id"]},
            {"$set": {
                "due_at": past_due,
                "status": "issued",
                "reminders": [{
                    "stage": 7,
                    "days_overdue": 10,
                    "sent_at": now_iso,
                    "share_id": str(uuid.uuid4()),
                    "recipient": "iter214+pytest@example.com",
                    "delivered": True,
                    "sent_by": "pytest",
                }],
            }},
        )
        # Insert a matching dunning share-link row so reminders_mtd
        # picks it up.
        await db.invoice_share_links.insert_one({
            "id": str(uuid.uuid4()),
            "token": uuid.uuid4().hex,
            "organization_id": org_id,
            "invoice_id": inv["id"],
            "recipient_email": "iter214+pytest@example.com",
            "subject": "iter214 reminder",
            "message": "",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "used_count": 0,
            "last_used_at": None,
            "created_by": "pytest",
            "created_at": now_iso,
            "revoked": False,
            "kind": "dunning",
            "stage": 7,
        })
        await db.organizations.update_one(
            {"id": org_id},
            {"$set": {"primary_contact_email": "iter214+pytest@example.com"}},
        )

    asyncio.get_event_loop().run_until_complete(_setup())

    yield {"org_id": org_id, "invoice_id": inv["id"], "number": inv["number"], "total": inv["total"]}

    async def _cleanup():
        await db.org_billing_invoices.update_one(
            {"id": inv["id"]},
            {"$set": {"status": "void"}, "$unset": {"reminders": ""}},
        )
        await db.invoice_share_links.delete_many({"invoice_id": inv["id"]})

    asyncio.get_event_loop().run_until_complete(_cleanup())


def test_collections_dashboard_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/collections/dashboard",
        headers=_h(pulse_pro_token),
        timeout=10,
    )
    assert r.status_code == 403


def test_collections_dashboard_shape(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/collections/dashboard",
        headers=_h(master_admin_token_session),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("as_of", "currency", "total_outstanding", "buckets", "top_overdue", "reminders_mtd"):
        assert key in body
    assert body["currency"] == "GBP"
    assert isinstance(body["buckets"], list) and len(body["buckets"]) == 4
    bucket_keys = {b["key"] for b in body["buckets"]}
    assert bucket_keys == {"current", "1_30", "31_60", "61_plus"}
    for b in body["buckets"]:
        for k in ("label", "min_days", "max_days", "count", "amount"):
            assert k in b
    rm = body["reminders_mtd"]
    for k in ("total", "by_stage", "delivered", "skipped"):
        assert k in rm
    assert set(rm["by_stage"].keys()) == {"7", "14", "28"}


def test_collections_dashboard_buckets_overdue(overdue_invoice_with_reminder, master_admin_token_session):
    """A 10-day overdue invoice with balance must move the 1_30 bucket
    and surface in top_overdue."""
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/collections/dashboard",
        headers=_h(master_admin_token_session),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    bucket_1_30 = next(b for b in body["buckets"] if b["key"] == "1_30")
    assert bucket_1_30["count"] >= 1
    assert bucket_1_30["amount"] >= overdue_invoice_with_reminder["total"]

    # top_overdue must include Tottenham with the right balance.
    tott = next(
        (t for t in body["top_overdue"] if t["organization_id"] == overdue_invoice_with_reminder["org_id"]),
        None,
    )
    assert tott is not None, body["top_overdue"]
    assert tott["balance"] >= overdue_invoice_with_reminder["total"]
    assert tott["max_days_overdue"] >= 10
    assert tott["reminder_count"] >= 1
    assert tott["last_reminded_at"] is not None
    assert tott["organization_name"]


def test_collections_dashboard_reminders_mtd(overdue_invoice_with_reminder, master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/collections/dashboard",
        headers=_h(master_admin_token_session),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    rm = body["reminders_mtd"]
    # We seeded a stage-7 dunning share-link this month + a delivered
    # reminders[] audit row, so both counters must move.
    assert rm["by_stage"]["7"] >= 1
    assert rm["delivered"] >= 1


def test_collections_dashboard_unknown_currency_returns_zeros(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/collections/dashboard?currency=ZZZ",
        headers=_h(master_admin_token_session),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "ZZZ"
    assert body["total_outstanding"] == 0
    assert all(b["count"] == 0 and b["amount"] == 0 for b in body["buckets"])
    assert body["top_overdue"] == []
