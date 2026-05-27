"""Iter 220ak — Public Demo Request + Growth Alerts.

Pins the new public ``POST /api/public/demo-request`` endpoint that
feeds the GymAxis self-promo funnel (SEO Autopilot → blog → demo
request → CRM lead → cold-to-demo journey).

  * Public (no auth). Validates name / email / company / site_count.
  * Inserts crm_contacts + crm_deals (stage=lead) + crm_activities
    + growth_alerts — scoped to the master-admin org.
  * Auto-enrols the contact into the cold-to-demo journey if it has
    been launched (Iter 220ah). Enrolment failure is non-fatal.
  * Honeypot — if ``website`` is non-empty, returns ``queued: true``
    with a fake receipt id (so bots can't detect the rejection) and
    writes nothing to Mongo.
  * Rate-limit raises 429 with a dedicated key so it never collides
    with the global per-IP buckets.
  * Master-admin gated growth-alerts endpoints (list + mark-read).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "users", "organizations", "crm_contacts", "crm_deals",
        "crm_activities", "crm_pipelines", "growth_alerts",
        "marketing_journeys", "marketing_journey_enrolments",
    ):
        c = getattr(fdb, coll)
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()
        c.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
        c.find_one = AsyncMock(return_value=None)
        c.count_documents = AsyncMock(return_value=0)
        find_cursor = MagicMock()
        find_cursor.sort = MagicMock(return_value=find_cursor)
        find_cursor.limit = MagicMock(return_value=find_cursor)
        find_cursor.to_list = AsyncMock(return_value=[])
        c.find = MagicMock(return_value=find_cursor)
    # master-admin org resolution
    fdb.users.find_one = AsyncMock(return_value={"organization_id": "org-master"})
    return fdb


async def _fake_org_id():
    return "org-master"


def _payload(**overrides):
    base = {
        "name": "Alex Carter", "email": "alex@example.com",
        "company": "Anytime Fitness UK", "site_count": 8,
        "message": "Cut downtime", "website": None,
    }
    base.update(overrides)
    from routes.public_demo_request import DemoRequestPayload
    return DemoRequestPayload(**base)


def _fake_request(ip: str = "1.2.3.4"):
    req = MagicMock()
    req.client = MagicMock(host=ip)
    req.headers = {}
    return req


# ── Honeypot ──────────────────────────────────────────────────────

def test_demo_request_honeypot_returns_fake_receipt_without_writes():
    from routes import public_demo_request as m

    fdb = _fake_db()
    request = _fake_request()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.submit_demo_request(
                _payload(website="http://spam.example"),
                request,
            )
    out = _run(go())
    # 200 with `queued: true` — bot can't tell it failed.
    assert out["ok"] is True
    assert out["queued"] is True
    assert "receipt_id" in out
    # Crucially — zero Mongo writes.
    fdb.crm_contacts.insert_one.assert_not_called()
    fdb.crm_deals.insert_one.assert_not_called()
    fdb.growth_alerts.insert_one.assert_not_called()


# ── Happy path: writes all 4 collections + enrols journey ────────

def test_demo_request_writes_contact_deal_activity_alert_and_enrols():
    from routes import public_demo_request as m

    fdb = _fake_db()
    # Cold-to-demo journey IS launched — should enrol.
    fdb.marketing_journeys.find_one = AsyncMock(return_value={"id": "j-cold-1"})
    request = _fake_request("9.9.9.9")  # fresh IP, won't trip rate limit

    async def fake_send(**_kw):
        return True

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "send_email", fake_send), \
             patch.object(m, "_master_admin_org_id", _fake_org_id):
            return await m.submit_demo_request(_payload(), request)
    out = _run(go())
    assert out["ok"] is True
    assert out["queued"] is False
    fdb.crm_contacts.insert_one.assert_awaited_once()
    fdb.crm_deals.insert_one.assert_awaited_once()
    fdb.crm_activities.insert_one.assert_awaited_once()
    fdb.growth_alerts.insert_one.assert_awaited_once()
    fdb.marketing_journey_enrolments.insert_one.assert_awaited_once()

    # Deal is in stage=lead, has the right source and contact-name.
    deal = fdb.crm_deals.insert_one.await_args.args[0]
    assert deal["stage"] == "lead"
    assert deal["source"] == "demo-request-form"
    assert deal["organization_id"] == "org-master"
    assert deal["site_count"] == 8
    assert deal["contact_name"] == "Alex Carter"

    # Contact tagged + scored.
    contact = fdb.crm_contacts.insert_one.await_args.args[0]
    assert "inbound-demo-request" in contact["tags"]
    assert contact["source"] == "demo-request-form"
    assert contact["first_name"] == "Alex"
    assert contact["last_name"] == "Carter"

    # Growth alert title surfaces company.
    alert = fdb.growth_alerts.insert_one.await_args.args[0]
    assert "Anytime Fitness UK" in alert["title"]
    assert alert["read"] is False


def test_demo_request_skips_enrolment_when_journey_not_launched():
    """Cold-to-demo journey hasn't been launched yet → enrolment is
    a silent no-op (we don't want the lead-capture to fail)."""
    from routes import public_demo_request as m

    fdb = _fake_db()
    fdb.marketing_journeys.find_one = AsyncMock(return_value=None)
    request = _fake_request("9.9.9.10")

    async def fake_send(**_kw):
        return True

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "send_email", fake_send), \
             patch.object(m, "_master_admin_org_id", _fake_org_id):
            return await m.submit_demo_request(_payload(), request)
    out = _run(go())
    assert out["ok"] is True
    fdb.marketing_journey_enrolments.insert_one.assert_not_called()
    # CRM writes still happened.
    fdb.crm_deals.insert_one.assert_awaited_once()


# ── Name validation ─────────────────────────────────────────────

def test_demo_request_rejects_all_numeric_name():
    from fastapi import HTTPException
    from routes import public_demo_request as m

    fdb = _fake_db()
    request = _fake_request("9.9.9.11")

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.submit_demo_request(_payload(name="12345"), request)
                return False
            except HTTPException as exc:
                return exc.status_code == 422
    assert _run(go())
    # No CRM writes because the name was rejected before we touched Mongo.
    fdb.crm_deals.insert_one.assert_not_called()


# ── Rate limit ──────────────────────────────────────────────────

def test_demo_request_rate_limit_429_after_too_many_submits(monkeypatch):
    """After 5 successful submits from the same IP we should hit a
    429 on the 6th."""
    from fastapi import HTTPException
    from routes import public_demo_request as m
    # Lower the window so the test doesn't have to clear state — and
    # crank max so 5 attempts are valid.
    monkeypatch.setattr(m, "_DEMO_RATE_MAX", 5)
    monkeypatch.setattr(m, "_DEMO_RATE_WINDOW_S", 3600)

    fdb = _fake_db()
    fdb.marketing_journeys.find_one = AsyncMock(return_value=None)
    request = _fake_request("9.9.9.50")  # never used elsewhere

    async def fake_send(**_kw):
        return True

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "send_email", fake_send), \
             patch.object(m, "_master_admin_org_id", _fake_org_id):
            for _ in range(5):
                await m.submit_demo_request(
                    _payload(email="x@a.com"),
                    request,
                )
            # 6th must 429.
            try:
                await m.submit_demo_request(
                    _payload(email="x@a.com"),
                    request,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 429
    assert _run(go())


# ── Growth Alerts endpoints ─────────────────────────────────────

def test_list_growth_alerts_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.list_growth_alerts({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


def test_list_growth_alerts_returns_rows_and_unread_count():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    fdb.users.find_one = AsyncMock(return_value={"organization_id": "org-master"})
    alerts = [
        {"id": "a1", "title": "A", "read": False, "created_at": "z"},
        {"id": "a2", "title": "B", "read": True, "created_at": "y"},
    ]
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=alerts)
    fdb.growth_alerts.find = MagicMock(return_value=cur)
    fdb.growth_alerts.count_documents = AsyncMock(return_value=1)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_growth_alerts({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["unread"] == 1
    assert len(out["alerts"]) == 2


def test_mark_growth_alerts_read_writes_update_many():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    fdb.users.find_one = AsyncMock(return_value={"organization_id": "org-master"})
    fdb.growth_alerts.update_many = AsyncMock(return_value=MagicMock(modified_count=3))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.mark_growth_alerts_read({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["ok"] is True
    assert out["marked"] == 3
    fdb.growth_alerts.update_many.assert_awaited_once()
    call = fdb.growth_alerts.update_many.await_args
    assert call.args[0]["organization_id"] == "org-master"
    assert call.args[0]["read"] is False
    assert call.args[1]["$set"]["read"] is True


def test_mark_growth_alerts_read_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.mark_growth_alerts_read({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


# ── Name splitting ──────────────────────────────────────────────

def test_safe_name_splits_first_and_last_correctly():
    from routes import public_demo_request as m
    assert m._safe_name("Alex Carter") == ("Alex", "Carter")
    assert m._safe_name("Madonna") == ("Madonna", "")
    assert m._safe_name("Mary Jo Smith Jones") == ("Mary", "Jo Smith Jones")
    assert m._safe_name("  Trimmed  ") == ("Trimmed", "")


# ── Module surface ──────────────────────────────────────────────

def test_demo_request_router_prefix_and_paths():
    from routes.public_demo_request import router
    paths = {r.path for r in router.routes}
    assert "/public/demo-request" in paths
