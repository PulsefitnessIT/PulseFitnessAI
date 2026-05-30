"""Iter 220dd — Parts request backorder / ETA visibility.

Backend changes pinned:

  * ``ApproveIn`` now carries optional ``eta_date`` + ``backordered``
    fields, and the approved request persists them.
  * New ``POST /admin/parts-requests/{id}/eta`` endpoint lets admin
    update ETA after approval (without re-approving) when supplier
    confirms.
  * 409 on non-pending/approved status, 404 on missing.

Frontend wiring pinned:

  * ``EngineerJobDetailV2`` Parts tab renders a new "On the way"
    panel with ``Backordered`` / ``ETA {date}`` chips.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _admin():
    return {
        "id": "admin-1",
        "organization_id": "org-1",
        "is_master_admin": True,
        "email": "admin@x.test",
        "full_name": "Admin",
    }


def _approve_db(req=None):
    fdb = MagicMock()
    fdb.svc_parts_requests.find_one = AsyncMock(return_value=req)
    fdb.svc_parts_requests.update_one = AsyncMock()
    fdb.svc_parts_requests.insert_one = AsyncMock()
    fdb.svc_part_movements.insert_one = AsyncMock()
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": req.get("case_id") if req else None, "reference": "GA-100"})
    return fdb


# ── 1 · ApproveIn carries ETA + backorder ─────────────────────────


def test_approve_in_accepts_eta_and_backorder():
    from routes.svc.engineer_parts_requests import ApproveIn

    a = ApproveIn(eta_date="2026-06-10", backordered=True)
    assert a.eta_date == "2026-06-10"
    assert a.backordered is True


def test_approve_persists_eta_and_backorder():
    """When approve is called with ETA + backorder, both land on the
    parts-request row."""
    req = {
        "id": "req-1", "organization_id": "org-1", "case_id": "case-1",
        "case_reference": "GA-100", "part_sku": "BELT-1",
        "part_name": "Belt", "qty": 2, "list_price_gbp": 25.0,
        "engineer_id": "eng-1", "urgency": "normal",
        "status": "pending",
    }
    fdb = _approve_db(req)

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb), \
             patch("routes.svc.engineer_parts_requests.append_event", AsyncMock()), \
             patch("routes.svc.engineer_parts_requests.sicon_sync.push_part_movement", AsyncMock()), \
             patch("routes.svc.engineer_parts_requests.audit_log", AsyncMock()):
            from routes.svc.engineer_parts_requests import (
                admin_approve, ApproveIn,
            )
            return await admin_approve(
                request_id="req-1",
                body=ApproveIn(eta_date="2026-06-15", backordered=True),
                user=_admin(),
            )

    _run(run())
    # Find the request-row update (the one with `status: approved`).
    updates = [
        c for c in fdb.svc_parts_requests.update_one.await_args_list
        if "$set" in c.args[1] and c.args[1]["$set"].get("status") == "approved"
    ]
    assert len(updates) == 1
    set_doc = updates[0].args[1]["$set"]
    assert set_doc["eta_date"] == "2026-06-15"
    assert set_doc["backordered"] is True


# ── 2 · /eta endpoint ─────────────────────────────────────────────


def test_eta_endpoint_updates_an_approved_request():
    req = {
        "id": "req-1", "organization_id": "org-1", "case_id": "case-1",
        "part_sku": "BELT-1", "status": "approved",
    }
    # find_one returns req twice (lookup + fresh fetch).
    fdb = MagicMock()
    fdb.svc_parts_requests.find_one = AsyncMock(side_effect=[req, req])
    fdb.svc_parts_requests.update_one = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb), \
             patch("routes.svc.engineer_parts_requests.append_event", AsyncMock()):
            from routes.svc.engineer_parts_requests import (
                admin_update_eta, EtaUpdateIn,
            )
            return await admin_update_eta(
                request_id="req-1",
                body=EtaUpdateIn(
                    eta_date="2026-06-20", backordered=True,
                    eta_notes="Supplier confirmed 5-day delay",
                ),
                user=_admin(),
            )

    _run(run())
    fdb.svc_parts_requests.update_one.assert_awaited_once()
    set_doc = fdb.svc_parts_requests.update_one.await_args.args[1]["$set"]
    assert set_doc["eta_date"] == "2026-06-20"
    assert set_doc["backordered"] is True
    assert set_doc["eta_notes"] == "Supplier confirmed 5-day delay"


def test_eta_endpoint_404s_on_missing():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_parts_requests.find_one = AsyncMock(return_value=None)

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb):
            from routes.svc.engineer_parts_requests import (
                admin_update_eta, EtaUpdateIn,
            )
            return await admin_update_eta(
                request_id="nope", body=EtaUpdateIn(),
                user=_admin(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 404


def test_eta_endpoint_409s_when_request_was_rejected_or_cancelled():
    import pytest
    from fastapi import HTTPException

    req = {"id": "req-1", "organization_id": "org-1",
           "case_id": "case-1", "part_sku": "X", "status": "rejected"}
    fdb = MagicMock()
    fdb.svc_parts_requests.find_one = AsyncMock(return_value=req)

    async def run():
        with patch("routes.svc.engineer_parts_requests.db", fdb):
            from routes.svc.engineer_parts_requests import (
                admin_update_eta, EtaUpdateIn,
            )
            return await admin_update_eta(
                request_id="req-1", body=EtaUpdateIn(),
                user=_admin(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 409


# ── 3 · Frontend wiring ───────────────────────────────────────────


def test_frontend_engineer_parts_tab_renders_eta_chips():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
    ).read_text()
    assert "incomingRequests" in src
    assert 'data-testid="parts-incoming-requests"' in src
    # ETA + backorder chips have stable test IDs.
    assert 'data-testid={`parts-backordered-${r.id}`}' in src
    assert 'data-testid={`parts-eta-${r.id}`}' in src
    # Filter only approved with ETA or backorder.
    assert "r.eta_date || r.backordered" in src
