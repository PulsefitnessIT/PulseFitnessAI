"""Iter 220cn — parts-request machine attribution tests.

The engineer can now tag a parts request to a specific machine row
on the case (``svc_work_visit_machines``). The backend must:

* Accept ``machine_id`` / ``machine_name`` on the create payload.
* Resolve ``machine_name`` from the work-visit row when only id was sent.
* Persist ``machine_id`` / ``machine_name`` on ``svc_parts_requests``.
* Append a case event whose ``extra.machine_id`` matches.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="eng-1"):
    return {"id": uid, "organization_id": org, "full_name": "Test Engineer"}


def _fake_db(machine_row=None, catalogue=None):
    fdb = MagicMock()
    for coll in (
        "svc_cases", "svc_parts", "svc_work_visit_machines",
        "svc_parts_requests", "svc_case_events",
    ):
        for op in ("insert_one", "insert_many", "update_one", "delete_one"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).count_documents = AsyncMock(return_value=0)
        getattr(fdb, coll).create_index = AsyncMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1", "reference": "GA-001",
    })
    fdb.svc_parts.find_one = AsyncMock(return_value=catalogue)
    fdb.svc_work_visit_machines.find_one = AsyncMock(return_value=machine_row)
    return fdb


def _payload(**extra):
    body = {
        "case_id": "case-1",
        "part_sku": "abc-123",
        "part_name": "Belt",
        "qty": 2,
        "urgency": "urgent",
        "notes": "left side worn",
    }
    body.update(extra)
    return body


def test_create_parts_request_with_machine_id_resolves_name():
    """Engineer sends only ``machine_id`` → server backfills
    ``machine_name`` from the work-visit machine row."""
    fdb = _fake_db(machine_row={
        "id": "mr-1", "asset_name": "Treadmill A",
        "organization_id": "org-1", "case_id": "case-1",
    })

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb), \
             patch(
                 "routes.svc.engineer_parts_requests.append_event",
                 AsyncMock(),
             ) as fake_evt:
            from routes.svc.engineer_parts_requests import (
                PartsRequestIn, create_request,
            )
            body = PartsRequestIn(**_payload(machine_id="mr-1"))
            doc = await create_request(body, user=_user())
            assert doc["machine_id"] == "mr-1"
            assert doc["machine_name"] == "Treadmill A"
            assert doc["part_sku"] == "ABC-123"  # upper-cased
            assert doc["urgency"] == "urgent"
            # The case-event must carry the machine id in extra.
            fake_evt.assert_awaited_once()
            kwargs = fake_evt.await_args.kwargs
            assert kwargs["extra"]["machine_id"] == "mr-1"
            assert "Treadmill A" in kwargs["body"]
            fdb.svc_parts_requests.insert_one.assert_awaited_once()
            inserted = fdb.svc_parts_requests.insert_one.await_args.args[0]
            assert inserted["machine_id"] == "mr-1"
            assert inserted["machine_name"] == "Treadmill A"
    _run(run())


def test_create_parts_request_without_machine_is_case_level():
    """No machine_id supplied → machine_id/name stay None and event
    fires without a machine reference in the body text."""
    fdb = _fake_db()

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb), \
             patch(
                 "routes.svc.engineer_parts_requests.append_event",
                 AsyncMock(),
             ) as fake_evt:
            from routes.svc.engineer_parts_requests import (
                PartsRequestIn, create_request,
            )
            body = PartsRequestIn(**_payload())
            doc = await create_request(body, user=_user())
            assert doc["machine_id"] is None
            assert doc["machine_name"] is None
            fake_evt.assert_awaited_once()
            kwargs = fake_evt.await_args.kwargs
            assert "for " not in kwargs["body"]  # no "— for {machine}" suffix
            assert kwargs["extra"]["machine_id"] is None
    _run(run())


def test_create_parts_request_with_explicit_machine_name_wins():
    """When the UI sends both ``machine_id`` and ``machine_name`` we
    must NOT overwrite the engineer-supplied name with the lookup."""
    fdb = _fake_db(machine_row={
        "id": "mr-9", "asset_name": "DB store value",
        "organization_id": "org-1", "case_id": "case-1",
    })

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb), \
             patch(
                 "routes.svc.engineer_parts_requests.append_event",
                 AsyncMock(),
             ):
            from routes.svc.engineer_parts_requests import (
                PartsRequestIn, create_request,
            )
            body = PartsRequestIn(**_payload(
                machine_id="mr-9", machine_name="Custom UI Label",
            ))
            doc = await create_request(body, user=_user())
            assert doc["machine_id"] == "mr-9"
            assert doc["machine_name"] == "Custom UI Label"
            # The lookup should NOT have been used (or used but ignored).
            # find_one may or may not be called depending on short-circuit.
    _run(run())
