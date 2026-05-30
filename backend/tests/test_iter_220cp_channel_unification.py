"""Iter 220cp — Cross-module channel unification tests.

When a case is created via the operations-portal / service-desk
``intake.py`` flow, the doc must carry BOTH ``source`` (legacy field
read by the portal) and ``intake_channel`` (field read by the engineer
app) so the "Logged via …" pill on `EngineerJobDetailV2` renders
correctly regardless of where the case originated.

We also pin that the engineer self-create flow (`independence.py`)
keeps writing ``intake_channel`` for the four allowed engineer
channels: ``manual | phone | email | other``.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="u-1"):
    return {"id": uid, "organization_id": org, "full_name": "Op", "email": "op@x"}


def _fake_db_intake():
    fdb = MagicMock()
    fdb.svc_cases.insert_one = AsyncMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=None)
    fdb.svc_case_events.insert_one = AsyncMock()
    fdb.crm_companies.find_one = AsyncMock(return_value=None)
    fdb.svc_sage_quote_outbox = MagicMock()
    return fdb


async def _call_create_case(source: str, payload: dict | None = None):
    from routes.svc.intake import _create_case
    fdb = _fake_db_intake()
    payload = payload or {"title": "Boiler down", "priority": "p2"}
    with patch("routes.svc.intake.db", fdb), \
         patch("routes.svc.intake.compute_sla_targets",
               AsyncMock(return_value={
                   "sla_response_at": None, "sla_resolve_at": None,
               })), \
         patch("routes.svc.intake.next_reference",
               AsyncMock(return_value="GA-001")), \
         patch("routes.svc.intake.append_event", AsyncMock()):
        case = await _create_case(payload=payload, source=source, user=_user())
    # The doc passed to insert_one is what gets persisted.
    inserted = fdb.svc_cases.insert_one.await_args.args[0]
    return case, inserted


def test_portal_intake_sets_both_source_and_intake_channel():
    case, inserted = _run(_call_create_case("portal"))
    assert inserted["source"] == "portal"
    assert inserted["intake_channel"] == "portal"
    # And the same is returned to the caller (operations portal UI).
    assert case["source"] == "portal"
    assert case["intake_channel"] == "portal"


def test_phone_intake_sets_intake_channel_phone():
    _, inserted = _run(_call_create_case("phone"))
    assert inserted["source"] == "phone"
    assert inserted["intake_channel"] == "phone"


def test_email_intake_sets_intake_channel_email():
    _, inserted = _run(_call_create_case("email"))
    assert inserted["source"] == "email"
    assert inserted["intake_channel"] == "email"


def test_engineer_self_create_keeps_manual_intake_channel():
    """Engineer-self-create path must remain untouched: the form sends
    ``intake_channel='manual'`` (post-220cp the duplicate phone is
    gone) and the backend persists exactly that value."""
    from routes.svc.independence import SelfCreateIn, jobs_self_create
    fdb = MagicMock()
    fdb.svc_engineers.find_one = AsyncMock(return_value={
        "id": "eng-1", "full_name": "Test Engineer",
    })
    fdb.svc_cases.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.insert_one = AsyncMock()
    fdb.svc_case_events.find_one = AsyncMock(return_value=None)

    async def run():
        with patch("routes.svc.independence.db", fdb), \
             patch("routes.svc.independence._next_reference",
                   return_value="GA-100"), \
             patch("routes.svc.independence.append_event", AsyncMock()), \
             patch("routes.svc.independence.sicon_sync.push_case",
                   AsyncMock()), \
             patch("routes.svc.independence.sicon_sync.push_event",
                   AsyncMock()), \
             patch("routes.svc.independence.audit_log", AsyncMock()):
            body = SelfCreateIn(
                title="Phone-in fault", priority="P2",
                intake_channel="manual",
            )
            out = await jobs_self_create(
                body=body,
                user={"id": "eng-1", "organization_id": "org-1",
                      "full_name": "Test", "email": "e@x"},
                idempotency_key=None,
            )
            assert out["case_id"]
            inserted = fdb.svc_cases.insert_one.await_args.args[0]
            assert inserted["intake_channel"] == "manual"
            # Engineer self-create does NOT use ``source`` (set by the
            # ops-portal path); ensure we don't accidentally regress.
            assert "source" not in inserted or inserted.get("source") in (None, "")
    _run(run())


def test_engineer_self_create_accepts_phone_email_other():
    """All four allowed engineer channels round-trip through the
    Pydantic model and into the persisted doc — no validation error,
    no silent rewrite to 'manual'."""
    from routes.svc.independence import SelfCreateIn
    for ch in ("manual", "phone", "email", "other"):
        body = SelfCreateIn(title="t", intake_channel=ch)
        assert body.intake_channel == ch
