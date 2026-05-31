"""Iter 220al — CRM Contact → Enrol in journey tests.

Pins the new endpoints under ``/api/crm/contacts/{id}``:

  * ``GET ./journey-options`` — lists org's non-archived
    ``marketing_journeys`` + per-journey ``already_enrolled`` flag.
  * ``POST ./enrol`` — inserts a ``marketing_journey_enrolments``
    row, stamps a ``crm_activities`` "journey_enrolled" event, and
    increments ``metrics.entered`` on the journey row. Idempotent —
    409 on duplicate active enrolment.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, items): self._items = list(items)
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    return _Cur(items)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "crm_contacts", "crm_activities", "crm2_contacts", "crm2_activities",
        "marketing_journeys", "marketing_journey_enrolments",
    ):
        c = getattr(fdb, coll)
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()
        c.find_one = AsyncMock(return_value=None)
        c.find = MagicMock(return_value=_async_iter([]))
    return fdb


_USER = {"id": "u-1", "organization_id": "org-A", "full_name": "Rep Smith"}


def _stub_contact(**o):
    base = {
        "id": "c-1", "organization_id": "org-A",
        "first_name": "Alex", "last_name": "Carter",
        "email": "alex@anytime.example.com",
        "company_id": "co-1",
    }
    base.update(o)
    return base


# ── journey-options ───────────────────────────────────────────────

def test_journey_options_soft_returns_empty_for_non_crm_contact():
    """Non-CRM contacts (e.g. members rendered by the same list)
    should NOT 404 — we return empty journeys + a flag so the UI can
    silently hide the Enrol button."""
    from routes import crm_journey_enrol as m
    fdb = _fake_db()  # crm_contacts.find_one returns None by default

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_journey_options("c-1", _USER)
    out = _run(go())
    assert out["journeys"] == []
    assert out["non_crm_contact"] is True


def test_journey_options_returns_org_journeys_with_enrolled_flag():
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    fdb.crm2_contacts.find_one = AsyncMock(return_value=_stub_contact())

    journey_rows = [
        {"id": "j-1", "name": "Cold → demo",
         "description": "5 emails",
         "template_id": "cold-to-demo", "status": "draft",
         "metrics": {"entered": 2}, "nodes": [{}, {}, {}, {}, {}]},
        {"id": "j-2", "name": "Demo booked",
         "description": "3 emails",
         "template_id": "demo-booked", "status": "draft",
         "metrics": {"entered": 0}, "nodes": [{}, {}, {}]},
    ]
    j_cur = MagicMock()
    j_cur.sort = MagicMock(return_value=j_cur)
    j_cur.to_list = AsyncMock(return_value=journey_rows)
    fdb.marketing_journeys.find = MagicMock(return_value=j_cur)

    # Contact is already enrolled in j-1, not j-2.
    fdb.marketing_journey_enrolments.find = MagicMock(return_value=_async_iter([
        {"journey_id": "j-1"},
    ]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_journey_options("c-1", _USER)
    out = _run(go())
    assert out["contact"]["id"] == "c-1"
    by_id = {j["id"]: j for j in out["journeys"]}
    assert by_id["j-1"]["already_enrolled"] is True
    assert by_id["j-2"]["already_enrolled"] is False
    assert by_id["j-1"]["node_count"] == 5
    assert by_id["j-2"]["node_count"] == 3


# ── enrol happy path ──────────────────────────────────────────────

def test_enrol_writes_enrolment_activity_and_bumps_journey_metric():
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    fdb.crm2_contacts.find_one = AsyncMock(return_value=_stub_contact())
    fdb.marketing_journeys.find_one = AsyncMock(return_value={
        "id": "j-1", "name": "Cold → demo", "template_id": "cold-to-demo",
    })
    # No existing enrolment.
    fdb.marketing_journey_enrolments.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.enrol_contact(
                "c-1", m.EnrolPayload(journey_id="j-1"), _USER,
            )
    out = _run(go())
    assert out["ok"] is True
    assert out["journey_id"] == "j-1"
    assert out["contact_id"] == "c-1"

    # Enrolment row.
    fdb.marketing_journey_enrolments.insert_one.assert_awaited_once()
    enrol = fdb.marketing_journey_enrolments.insert_one.await_args.args[0]
    assert enrol["journey_id"] == "j-1"
    assert enrol["organization_id"] == "org-A"
    assert enrol["status"] == "active"
    assert enrol["source"] == "crm-contact-enrol"
    assert enrol["enrolled_by"] == "u-1"

    # Activity stamp went to crm2_activities (contact was v2).
    fdb.crm2_activities.insert_one.assert_awaited_once()
    activity = fdb.crm2_activities.insert_one.await_args.args[0]
    assert activity["type"] == "journey_enrolled"
    assert activity["contact_id"] == "c-1"
    assert "Cold → demo" in activity["description"]
    assert activity["organization_id"] == "org-A"
    fdb.crm_activities.insert_one.assert_not_called()

    # Journey metric bump.
    fdb.marketing_journeys.update_one.assert_awaited_once()
    call = fdb.marketing_journeys.update_one.await_args
    assert call.args[0] == {"id": "j-1"}
    assert call.args[1]["$inc"] == {"metrics.entered": 1}


def test_enrol_legacy_contact_writes_to_crm_activities():
    """Contacts created by the public demo-request endpoint live in
    the legacy ``crm_contacts`` collection. The activity stamp should
    follow them there so the legacy timeline view also picks it up."""
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    # v2 lookup misses, legacy hits.
    fdb.crm2_contacts.find_one = AsyncMock(return_value=None)
    fdb.crm_contacts.find_one = AsyncMock(return_value=_stub_contact())
    fdb.marketing_journeys.find_one = AsyncMock(return_value={
        "id": "j-2", "name": "Demo booked", "template_id": "demo-booked",
    })
    fdb.marketing_journey_enrolments.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.enrol_contact(
                "c-1", m.EnrolPayload(journey_id="j-2"), _USER,
            )
    _run(go())
    fdb.crm_activities.insert_one.assert_awaited_once()
    fdb.crm2_activities.insert_one.assert_not_called()


# ── Idempotency ──────────────────────────────────────────────────

def test_enrol_409_when_already_active():
    from fastapi import HTTPException
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    fdb.crm2_contacts.find_one = AsyncMock(return_value=_stub_contact())
    fdb.marketing_journeys.find_one = AsyncMock(return_value={
        "id": "j-1", "name": "Cold → demo", "template_id": "cold-to-demo",
    })
    fdb.marketing_journey_enrolments.find_one = AsyncMock(return_value={
        "id": "e-existing", "status": "active",
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.enrol_contact(
                    "c-1", m.EnrolPayload(journey_id="j-1"), _USER,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 409
    assert _run(go())
    # Crucially — no metric bump and no enrolment row.
    fdb.marketing_journey_enrolments.insert_one.assert_not_called()
    fdb.marketing_journeys.update_one.assert_not_called()
    fdb.crm_activities.insert_one.assert_not_called()


# ── Cross-tenant safety ──────────────────────────────────────────

def test_enrol_404_when_journey_belongs_to_other_org():
    from fastapi import HTTPException
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    fdb.crm2_contacts.find_one = AsyncMock(return_value=_stub_contact())
    # Journey lookup returns None because the org filter excludes it.
    fdb.marketing_journeys.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.enrol_contact(
                    "c-1", m.EnrolPayload(journey_id="j-foreign"), _USER,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_enrol_404_when_contact_belongs_to_other_org():
    from fastapi import HTTPException
    from routes import crm_journey_enrol as m

    fdb = _fake_db()
    # crm_contacts.find_one returns None → contact not in our org.

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.enrol_contact(
                    "c-foreign", m.EnrolPayload(journey_id="j-1"), _USER,
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


# ── Router surface ──────────────────────────────────────────────

def test_journey_enrol_router_exposes_both_paths():
    from routes.crm_journey_enrol import router
    paths = {r.path for r in router.routes}
    assert "/crm/contacts/{contact_id}/journey-options" in paths
    assert "/crm/contacts/{contact_id}/enrol" in paths
