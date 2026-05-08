"""
Proactive-nudge scanner + API tests (P2, Feb 2026).

Unit-tests each scanner with an in-memory org fixture, then hits the live
``/api/nudges`` endpoint to confirm the full read/dismiss flow.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from tests.conftest import _test_backend_url, run_async as run

BASE = _test_backend_url()


# ─── Scanner unit tests ────────────────────────────────────────────

def test_warranty_scanner_emits_event(tmp_path):
    from utils.database import db
    from utils import proactive_nudges as pn

    org_id = f"test-org-{uuid.uuid4()}"
    soon = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()

    async def _go():
        await db.organizations.insert_one({"id": org_id, "name": "Warranty Test Gym"})
        await db.equipment.insert_one({
            "id": f"eq-{uuid.uuid4()}", "organization_id": org_id,
            "name": "Treadmill", "warranty_expiry": soon,
        })
        await pn.scan_warranty_expiring({"id": org_id})
        evt = await db.trust_events.find_one({"org_id": org_id, "type": "nudge.warranty_expiring"}, {"_id": 0})
        assert evt is not None
        assert evt["state"] == "open"
        assert evt["payload"]["count"] == 1
        # Cleanup
        await db.equipment.delete_many({"organization_id": org_id})
        await db.organizations.delete_one({"id": org_id})
        await db.trust_events.delete_many({"org_id": org_id})

    run(_go())


def test_warranty_scanner_auto_resolves_when_empty():
    from utils.database import db
    from utils import proactive_nudges as pn

    org_id = f"test-org-{uuid.uuid4()}"

    async def _go():
        await db.organizations.insert_one({"id": org_id, "name": "Empty Gym"})
        # Seed an existing nudge to confirm auto-resolve path
        await db.trust_events.insert_one({
            "id": str(uuid.uuid4()), "org_id": org_id,
            "type": "nudge.warranty_expiring",
            "state": "open", "severity": "low",
            "dedupe_key": f"nudge.warranty_expiring:{org_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "occurrences": 1, "visible_to": ["org_owner"],
        })
        await pn.scan_warranty_expiring({"id": org_id})
        evt = await db.trust_events.find_one({"org_id": org_id, "type": "nudge.warranty_expiring"}, {"_id": 0})
        assert evt is not None
        assert evt["state"] == "auto_resolved"
        await db.organizations.delete_one({"id": org_id})
        await db.trust_events.delete_many({"org_id": org_id})

    run(_go())


def test_ppm_overdue_scanner():
    from utils.database import db
    from utils import proactive_nudges as pn

    org_id = f"test-org-{uuid.uuid4()}"
    past = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()

    async def _go():
        await db.organizations.insert_one({"id": org_id, "name": "PPM Test Gym"})
        await db.ppm_tasks.insert_one({
            "id": f"task-{uuid.uuid4()}", "organization_id": org_id,
            "title": "Quarterly inspection", "status": "scheduled",
            "scheduled_date": past,
        })
        await pn.scan_ppm_overdue({"id": org_id})
        evt = await db.trust_events.find_one({"org_id": org_id, "type": "nudge.ppm_overdue"}, {"_id": 0})
        assert evt is not None
        assert evt["payload"]["count"] == 1
        await db.ppm_tasks.delete_many({"organization_id": org_id})
        await db.organizations.delete_one({"id": org_id})
        await db.trust_events.delete_many({"org_id": org_id})

    run(_go())


def test_supplier_drift_scanner():
    from utils.database import db
    from utils import proactive_nudges as pn

    org_id = f"test-org-{uuid.uuid4()}"

    async def _go():
        await db.organizations.insert_one({"id": org_id, "name": "Drift Test Gym"})
        now = datetime.now(timezone.utc).isoformat()
        # Three low ratings for "BadCo" to exceed minimum samples
        for rating in (1, 2, 2):
            await db.supplier_cases.insert_one({
                "id": str(uuid.uuid4()), "organization_id": org_id,
                "supplier_name": "BadCo", "current_status": "closed",
                "rating": rating, "updated_at": now,
            })
        await pn.scan_supplier_sla_drift({"id": org_id})
        evt = await db.trust_events.find_one({"org_id": org_id, "type": "nudge.supplier_sla_drift"}, {"_id": 0})
        assert evt is not None
        assert any(s["name"] == "BadCo" for s in evt["payload"]["suppliers"])
        await db.supplier_cases.delete_many({"organization_id": org_id})
        await db.organizations.delete_one({"id": org_id})
        await db.trust_events.delete_many({"org_id": org_id})

    run(_go())


# ─── API regression tests ─────────────────────────────────────────

def test_nudges_list_api():
    """GET /api/nudges returns nudges list for authenticated user."""
    # Login fresh to avoid session revocation issues
    login_resp = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"},
        timeout=10
    )
    if login_resp.status_code != 200:
        pytest.skip("Could not login as Pulse Pro user")
    token = login_resp.json().get("token")

    r = requests.get(f"{BASE}/api/nudges",
                     headers={"Authorization": f"Bearer {token}"},
                     timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "nudges" in body and isinstance(body["nudges"], list)
    assert "count" in body


def test_nudges_dismiss_requires_manager():
    """A user without owner/manager role should not be able to dismiss."""
    from utils.database import db

    # Create a throw-away staff user
    email = f"staff-nudge-{uuid.uuid4().hex[:8]}@example.com"
    requests.post(f"{BASE}/api/auth/register",
                  json={"email": email, "password": "Staff123!Good",
                        "full_name": "Staff Nudge", "company_name": "Staff Gym"},
                  timeout=10)
    login_resp = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": "Staff123!Good"},
                          timeout=10)
    if login_resp.status_code != 200:
        pytest.skip("Could not login as staff user")
    token = login_resp.json().get("token")

    # First downgrade their role via direct DB poke (they default to owner on register)
    async def _downgrade():
        await db.users.update_one({"email": email}, {"$set": {"role": "staff"}})

    run(_downgrade())

    r = requests.post(f"{BASE}/api/nudges/{uuid.uuid4()}/dismiss",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 403

    async def _cleanup():
        await db.users.delete_many({"email": email})

    run(_cleanup())


def test_nudges_run_requires_master_admin():
    """POST /api/nudges/run requires master admin role."""
    # Login fresh as Pulse Pro user
    login_resp = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": "lee.somers@pulsefitness.com", "password": "TempPass123!"},
        timeout=10
    )
    if login_resp.status_code != 200:
        pytest.skip("Could not login as Pulse Pro user")
    token = login_resp.json().get("token")

    r = requests.post(f"{BASE}/api/nudges/run",
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=10)
    assert r.status_code == 403
