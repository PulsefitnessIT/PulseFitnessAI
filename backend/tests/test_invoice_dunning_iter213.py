"""Auto-dunning — iteration 213.

Verifies the new dunning endpoints:

* POST /api/master-admin/billing/dunning/run  (and dry_run preview)
* GET  /api/master-admin/billing/dunning/preview
* POST /api/master-admin/orgs/{org}/billing/invoice/{id}/remind

Plus invoice-row state mutations (`reminders` audit trail) and stage
selection logic.
"""
from __future__ import annotations

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
def overdue_invoice(master_admin_token_session):
    """Generate a fresh invoice for Tottenham, then back-date its
    `due_at` to 10 days ago so it qualifies for the 7-day dunning stage.

    The fixture writes directly to MongoDB to back-date — we need a
    deterministic past date for the stage logic, and the production
    invoice endpoint always sets `due_at` 30 days in the future.
    """
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    org_id = TOTTENHAM_GREEN_ORG_ID

    # Ensure a subscription is active.
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
    assert r.status_code == 200, r.text
    inv = r.json()["invoice"]

    # Back-date due_at via direct DB write.
    import asyncio
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    past_due = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    async def _backdate():
        await db.org_billing_invoices.update_one(
            {"id": inv["id"]},
            {"$set": {"due_at": past_due, "status": "issued"}, "$unset": {"reminders": ""}},
        )
        # Make sure the org has a billing contact so reminders can fire.
        await db.organizations.update_one(
            {"id": org_id},
            {"$set": {"primary_contact_email": "iter213+pytest@example.com"}},
        )

    asyncio.get_event_loop().run_until_complete(_backdate())

    yield {"org_id": org_id, "invoice_id": inv["id"], "number": inv["number"]}

    # Cleanup — remove our reminders so other tests start clean.
    async def _cleanup():
        await db.org_billing_invoices.update_one(
            {"id": inv["id"]},
            {"$unset": {"reminders": ""}, "$set": {"status": "void"}},
        )
    asyncio.get_event_loop().run_until_complete(_cleanup())


def test_dunning_run_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/billing/dunning/run",
        headers=_h(pulse_pro_token),
        json={},
        timeout=10,
    )
    assert r.status_code == 403


def test_dunning_preview_dry_run(overdue_invoice, master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.get(f"{base}/api/master-admin/billing/dunning/preview", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    # Our seeded overdue invoice must be amongst the would_fire entries.
    ids = [w["invoice_id"] for w in body["would_fire"]]
    assert overdue_invoice["invoice_id"] in ids
    # Stage at 10 days overdue: highest eligible is 7.
    target = next(w for w in body["would_fire"] if w["invoice_id"] == overdue_invoice["invoice_id"])
    assert target["stage"] == 7
    assert target["days_overdue"] == 10


def test_dunning_run_fires_and_audits(overdue_invoice, master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.post(
        f"{base}/api/master-admin/billing/dunning/run",
        headers=headers,
        json={},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is False
    fired_ids = [f["invoice_id"] for f in body["fired"]]
    assert overdue_invoice["invoice_id"] in fired_ids

    # Ledger reflects the reminders audit row.
    r2 = requests.get(
        f"{base}/api/master-admin/orgs/{overdue_invoice['org_id']}/billing",
        headers=headers,
        timeout=10,
    )
    assert r2.status_code == 200
    inv = next(i for i in r2.json()["invoices"] if i["id"] == overdue_invoice["invoice_id"])
    reminders = inv.get("reminders") or []
    assert len(reminders) == 1
    assert reminders[0]["stage"] == 7
    assert reminders[0]["recipient"] == "iter213+pytest@example.com"

    # Re-running must not double-fire stage 7.
    r3 = requests.post(
        f"{base}/api/master-admin/billing/dunning/run",
        headers=headers,
        json={},
        timeout=20,
    )
    assert r3.status_code == 200
    fired_ids2 = [f["invoice_id"] for f in r3.json()["fired"]]
    assert overdue_invoice["invoice_id"] not in fired_ids2


def test_remind_one_invoice_endpoint(overdue_invoice, master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.post(
        f"{base}/api/master-admin/orgs/{overdue_invoice['org_id']}/billing/invoice/{overdue_invoice['invoice_id']}/remind",
        headers=headers,
        json={},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["stage"] == 7
    assert body["days_overdue"] == 10
    assert "/api/public/invoice-share/" in body["share_url"]


def test_remind_rejects_paid_invoice(master_admin_token_session):
    """Create + immediately mark an invoice paid, then assert remind 400s."""
    import asyncio
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    org_id = TOTTENHAM_GREEN_ORG_ID
    r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice",
        headers=headers,
        json={},
        timeout=15,
    )
    assert r.status_code == 200
    inv_id = r.json()["invoice"]["id"]

    async def _mark_paid():
        await db.org_billing_invoices.update_one({"id": inv_id}, {"$set": {"status": "paid"}})
    asyncio.get_event_loop().run_until_complete(_mark_paid())

    r2 = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice/{inv_id}/remind",
        headers=headers,
        json={},
        timeout=10,
    )
    assert r2.status_code == 400
    assert "paid" in r2.text.lower()


def test_remind_not_yet_overdue_returns_400_unless_forced(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    org_id = TOTTENHAM_GREEN_ORG_ID
    # Fresh invoice — due_at is in the future.
    r = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice",
        headers=headers,
        json={},
        timeout=15,
    )
    inv_id = r.json()["invoice"]["id"]

    r2 = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice/{inv_id}/remind",
        headers=headers,
        json={},
        timeout=10,
    )
    assert r2.status_code == 400
    assert "not overdue" in r2.text.lower()

    # Force override — should fire stage 7 with days_overdue=0.
    r3 = requests.post(
        f"{base}/api/master-admin/orgs/{org_id}/billing/invoice/{inv_id}/remind",
        headers=headers,
        json={"force": True},
        timeout=15,
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["ok"] is True
    # Cleanup
    import asyncio
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    async def _cleanup():
        await db.org_billing_invoices.update_one({"id": inv_id}, {"$set": {"status": "void"}})
    asyncio.get_event_loop().run_until_complete(_cleanup())
