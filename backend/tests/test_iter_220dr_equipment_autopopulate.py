"""Iter 220dr — Equipment tab auto-population + Summary capture-media removal.

Operator feedback on the Treadmill-belt-slip screenshot (Feb 2026):

  1. **Capture Media still showing on Summary** — the engineer
     doesn't want photo capture on Summary; that surface is for
     customer/site context only. Photos belong to a machine, on
     the Equipment tab.
  2. **Equipment tab is empty** — when a customer logs a fault via
     the portal / inbound email / service desk the operator picks
     the affected machine (``asset_id`` / ``equipment_ids``). That
     selection used to NOT fan out into ``svc_work_visit_machines``
     until the engineer tapped "From site". The engineer should
     instead see the customer-logged machines pre-populated the
     moment they open the case.
  3. Customer-logged context (asset name, fault description,
     attached photos) must be visible on the Equipment tab so the
     engineer knows *which* machine they're walking to and what
     evidence the customer provided.

Backend:
  * ``_ensure_customer_machines_attached`` mirrors the case's
    ``asset_id`` + ``equipment_ids`` into ``svc_work_visit_machines``
    on every engineer GET. Idempotent — already-attached IDs are
    skipped. Pulls full serial/manufacturer/model from the
    ``equipment`` collection.

Frontend:
  * ``Capture Media`` block (``PhotosTab``) removed from Summary.
  * ``EquipmentTab`` renders a "What the customer logged" card
    with asset name, fault summary, customer photos + files.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _of():
    return {"organization_id": "org-1"}


# ── 1 · Summary tab no longer mounts PhotosTab ─────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_summary_tab_does_not_render_photos_block():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Pin the Summary conditional renders ONLY JobAtAGlance, not
    # PhotosTab. (The older two-child fragment is gone.)
    assert (
        "{activeTab === 'summary' && (\n"
        "          <JobAtAGlance"
    ) in src, "Summary tab must render JobAtAGlance directly, no fragment"
    # Sanity — the legacy "<>...PhotosTab...</>" wrapper is gone.
    assert (
        "{activeTab === 'summary' && (\n"
        "          <>\n"
        "            <JobAtAGlance"
    ) not in src


# ── 2 · Auto-attach customer-logged machines ───────────────────────


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def test_auto_attach_skips_when_no_customer_machines_on_case():
    """Cases without an ``asset_id`` or ``equipment_ids`` are a no-op
    — the engineer's existing manual ``From site`` flow still works."""
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {"id": "c-1", "organization_id": "org-1"}

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    fdb.svc_work_visit_machines.find.assert_not_called()
    fdb.svc_work_visit_machines.insert_many.assert_not_called()


def test_auto_attach_creates_row_for_primary_asset_id():
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "asset-treadmill-14",
        "asset_name": "Life Fitness Integrity",
    }
    # Nothing already attached.
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=0)
    fdb.equipment.find = MagicMock(return_value=_chain([{
        "id": "asset-treadmill-14",
        "name": "Treadmill #14",
        "equipment_type": "Treadmill",
        "manufacturer": "Life Fitness",
        "model": "Integrity DX",
        "serial_number": "LF-12345",
    }]))
    fdb.svc_work_visit_machines.insert_many = AsyncMock()

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    inserted = fdb.svc_work_visit_machines.insert_many.await_args.args[0]
    assert len(inserted) == 1
    row = inserted[0]
    assert row["asset_id"] == "asset-treadmill-14"
    assert row["asset_serial"] == "LF-12345"
    assert row["manufacturer"] == "Life Fitness"
    assert row["model"] == "Integrity DX"
    assert row["case_id"] == "c-1"
    assert row["source"] == "customer_logged"


def test_auto_attach_fans_equipment_ids_multi_asset():
    """Multi-asset intakes (site-wide outage) attach every requested
    equipment id, deduped against ``asset_id``."""
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "eq-a",
        "equipment_ids": ["eq-a", "eq-b", "eq-c"],  # eq-a dupe ignored
    }
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=0)
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "eq-a", "name": "Bike A", "serial_number": "SN-A"},
        {"id": "eq-b", "name": "Bike B", "serial_number": "SN-B"},
        {"id": "eq-c", "name": "Bike C", "serial_number": "SN-C"},
    ]))
    fdb.svc_work_visit_machines.insert_many = AsyncMock()

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    inserted = fdb.svc_work_visit_machines.insert_many.await_args.args[0]
    assert {r["asset_id"] for r in inserted} == {"eq-a", "eq-b", "eq-c"}


def test_auto_attach_skips_machines_already_present():
    """Idempotency — re-loading the case never duplicates rows that
    the engineer (or a previous call) already attached."""
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "eq-a",
        "equipment_ids": ["eq-a", "eq-b"],
    }
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {"asset_id": "eq-a"},  # already attached
    ]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=1)
    fdb.equipment.find = MagicMock(return_value=_chain([
        {"id": "eq-b", "name": "Bike B", "serial_number": "SN-B"},
    ]))
    fdb.svc_work_visit_machines.insert_many = AsyncMock()

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    inserted = fdb.svc_work_visit_machines.insert_many.await_args.args[0]
    assert [r["asset_id"] for r in inserted] == ["eq-b"]


def test_auto_attach_no_insert_when_all_present():
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "eq-a",
    }
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([
        {"asset_id": "eq-a"},
    ]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=1)
    fdb.svc_work_visit_machines.insert_many = AsyncMock()

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    fdb.svc_work_visit_machines.insert_many.assert_not_called()


def test_auto_attach_falls_back_to_asset_name_when_equipment_row_missing():
    """A case's `asset_id` may not match any current `equipment` row
    (e.g. customer typed a free-text asset). The helper must still
    create the work-visit machine using the case's asset_name so the
    engineer sees *something* rather than a blank tab."""
    from routes.svc.engineer import _ensure_customer_machines_attached

    fdb = MagicMock()
    case = {
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "orphan-id",
        "asset_name": "Treadmill (customer-described)",
    }
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain([]))
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=0)
    fdb.equipment.find = MagicMock(return_value=_chain([]))  # no match
    fdb.svc_work_visit_machines.insert_many = AsyncMock()

    async def go():
        with patch("routes.svc.engineer.db", fdb):
            await _ensure_customer_machines_attached(case, _of())

    _run(go())
    inserted = fdb.svc_work_visit_machines.insert_many.await_args.args[0]
    assert len(inserted) == 1
    assert inserted[0]["asset_id"] == "orphan-id"
    assert inserted[0]["asset_name"] == "Treadmill (customer-described)"


# ── 3 · Frontend Equipment tab renders the customer-logged card ───


def test_equipment_tab_renders_customer_context_card():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="equipment-customer-context"' in src
    assert 'data-testid="equipment-customer-asset"' in src
    assert 'data-testid="equipment-customer-summary"' in src
    assert 'data-testid="equipment-customer-photos"' in src
    assert 'data-testid="equipment-customer-files"' in src
    # Renders the customer's asset name, fault summary, photos +
    # non-image attachments.
    assert "job?.attachments" in src
