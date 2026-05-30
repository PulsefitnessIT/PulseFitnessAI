"""Iter 220ci — Engineer Equipment Tab tests.

Pins the strict-validation contract for the field-side create flow:

  * Mandatory fields enforced at the schema layer (422 on missing).
  * Picklist values rejected when off-list (422).
  * ``site_id`` required when org has multiple sites (400 at handler).
  * ``site_id`` auto-inherited when org has exactly one active site.
  * ``case_id`` query parameter inserts a matching machine row on the
    case AND tags the response so the UI can show "Added to job".
  * Cross-tenant safety — engineer A can't list/create equipment for
    engineer B's organization.
  * Picklist endpoint returns the canonical dropdown values + the
    engineer's org sites.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_db():
    fdb = MagicMock()
    for coll in (
        "equipment", "sites", "svc_cases", "svc_work_visit_machines",
    ):
        for op in ("insert_one", "update_one", "delete_one", "delete_many"):
            setattr(getattr(fdb, coll), op, AsyncMock())
        getattr(fdb, coll).find_one = AsyncMock(return_value=None)
        getattr(fdb, coll).count_documents = AsyncMock(return_value=0)
        getattr(fdb, coll).create_index = AsyncMock()

        # find().sort().to_list() chain.
        def _chain(_default=None):
            cur = MagicMock()
            cur.sort.return_value = cur
            cur.to_list = AsyncMock(return_value=_default or [])
            return cur
        getattr(fdb, coll).find = MagicMock(return_value=_chain([]))
    return fdb


def _user(org="org-1", uid="eng-1"):
    return {"id": uid, "organization_id": org}


def _valid_payload(**overrides):
    base = {
        "name": "Treadmill #14",
        "equipment_type": "Treadmill",
        "manufacturer": "Life Fitness",
        "model": "Integrity DX",
        "location": "Cardio Zone",
    }
    base.update(overrides)
    return base


# ── 1 · Picklists endpoint ────────────────────────────────────────────


def test_picklists_requires_org():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import get_picklists

    async def go():
        try:
            await get_picklists({"id": "u"})
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


def test_picklists_returns_curated_lists():
    from routes.svc.engineer_equipment import (
        get_picklists, EQUIPMENT_TYPE_OPTIONS, EQUIPMENT_LOCATION_OPTIONS,
        EQUIPMENT_STATUS_OPTIONS,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main Gym"},
        {"id": "site-2", "name": "Studio 2"},
    ]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await get_picklists(_user())
    out = _run(go())
    assert out["equipment_type_options"] == EQUIPMENT_TYPE_OPTIONS
    assert out["location_options"] == EQUIPMENT_LOCATION_OPTIONS
    assert out["status_options"] == EQUIPMENT_STATUS_OPTIONS
    assert {s["id"] for s in out["sites"]} == {"site-1", "site-2"}


def _chain(default):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.to_list = AsyncMock(return_value=default)
    return cur


# ── 2 · Schema-level validation ───────────────────────────────────────


def test_schema_rejects_missing_mandatory_fields():
    from pydantic import ValidationError
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    for missing in ("name", "equipment_type", "manufacturer", "model", "location"):
        payload = _valid_payload()
        del payload[missing]
        with pytest.raises(ValidationError) as exc_info:
            EngineerEquipmentCreate(**payload)
        assert missing in str(exc_info.value).lower(), missing


def test_schema_rejects_off_picklist_equipment_type():
    from pydantic import ValidationError
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    with pytest.raises(ValidationError):
        EngineerEquipmentCreate(**_valid_payload(equipment_type="Tradmill Bike"))


def test_schema_rejects_off_picklist_location():
    from pydantic import ValidationError
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    with pytest.raises(ValidationError):
        EngineerEquipmentCreate(**_valid_payload(location="random-zone"))


def test_schema_rejects_off_picklist_status():
    from pydantic import ValidationError
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    with pytest.raises(ValidationError):
        EngineerEquipmentCreate(**_valid_payload(status="broken"))


def test_schema_accepts_valid_payload_with_optionals():
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    obj = EngineerEquipmentCreate(**_valid_payload(
        serial_number="LF-12345",
        status="in_service",
        site_id="site-1",
        notes="Captured during PM visit",
    ))
    assert obj.name == "Treadmill #14"
    assert obj.equipment_type == "Treadmill"
    assert obj.status == "in_service"


def test_schema_strips_whitespace_on_freetext():
    from routes.svc.engineer_equipment import EngineerEquipmentCreate
    obj = EngineerEquipmentCreate(**_valid_payload(
        name="  Treadmill 14  ",
        manufacturer="  Life Fitness ",
        model=" Integrity DX  ",
    ))
    assert obj.name == "Treadmill 14"
    assert obj.manufacturer == "Life Fitness"
    assert obj.model == "Integrity DX"


# ── 3 · Create endpoint — site rules ──────────────────────────────────


def test_create_400s_when_multi_site_org_omits_site_id():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main"},
        {"id": "site-2", "name": "Annex"},
    ]))

    payload = EngineerEquipmentCreate(**_valid_payload())

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await create_engineer_equipment(payload, _user(), case_id=None)
                return False
            except HTTPException as exc:
                return exc.status_code == 400 and "multiple sites" in exc.detail
    assert _run(go())


def test_create_400s_when_site_id_does_not_belong_to_org():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main"},
    ]))

    payload = EngineerEquipmentCreate(**_valid_payload(site_id="site-OTHER"))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await create_engineer_equipment(payload, _user(), case_id=None)
                return False
            except HTTPException as exc:
                return exc.status_code == 400 and "not a valid site" in exc.detail
    assert _run(go())


def test_create_auto_inherits_site_when_only_one():
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-only", "name": "Main Gym"},
    ]))
    payload = EngineerEquipmentCreate(**_valid_payload())

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await create_engineer_equipment(payload, _user(), case_id=None)
    out = _run(go())
    assert out["site_id"] == "site-only"
    fdb.equipment.insert_one.assert_awaited_once()


def test_create_persists_to_equipment_collection_with_org_tag():
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main Gym"},
    ]))
    payload = EngineerEquipmentCreate(**_valid_payload(site_id="site-1"))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await create_engineer_equipment(payload, _user(), case_id=None)
    out = _run(go())
    inserted = fdb.equipment.insert_one.await_args.args[0]
    assert inserted["organization_id"] == "org-1"
    assert inserted["created_by_id"] == "eng-1"
    assert inserted["created_via"] == "engineer_app"
    assert inserted["equipment_type"] == "Treadmill"
    assert inserted["site_id"] == "site-1"
    assert out["attached_to_case"] is False


# ── 4 · Create endpoint — case auto-attach ────────────────────────────


def test_create_with_case_id_attaches_machine_row():
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main"},
    ]))
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-99"})
    fdb.svc_work_visit_machines.count_documents = AsyncMock(return_value=2)

    payload = EngineerEquipmentCreate(**_valid_payload(site_id="site-1"))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await create_engineer_equipment(payload, _user(), case_id="case-99")
    out = _run(go())
    fdb.svc_work_visit_machines.insert_one.assert_awaited_once()
    machine_row = fdb.svc_work_visit_machines.insert_one.await_args.args[0]
    assert machine_row["case_id"] == "case-99"
    assert machine_row["organization_id"] == "org-1"
    assert machine_row["asset_id"] == out["id"]
    assert "Life Fitness Integrity DX" in machine_row["asset_name"]
    assert machine_row["order_index"] == 2  # appended after existing rows
    assert machine_row["asset_type"] == "Treadmill"
    assert out["attached_to_case"] is True


def test_create_with_unknown_case_returns_skip_reason():
    """When case_id doesn't belong to this org we DO persist the
    equipment (the side-effect failed, the primary action succeeded)
    and return a skip reason so the UI can prompt."""
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    fdb = _fake_db()
    fdb.sites.find = MagicMock(return_value=_chain([
        {"id": "site-1", "name": "Main"},
    ]))
    # svc_cases.find_one returns None (not found) by default.
    payload = EngineerEquipmentCreate(**_valid_payload(site_id="site-1"))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await create_engineer_equipment(payload, _user(), case_id="case-X")
    out = _run(go())
    fdb.equipment.insert_one.assert_awaited_once()
    fdb.svc_work_visit_machines.insert_one.assert_not_awaited()
    assert out["attached_to_case"] is False
    assert out["case_skip_reason"] == "case_not_found"


# ── 5 · List endpoint ─────────────────────────────────────────────────


def test_list_filters_by_organization():
    from routes.svc.engineer_equipment import list_engineer_equipment
    fdb = _fake_db()
    rows = [
        {"id": "e-1", "name": "Treadmill", "organization_id": "org-1"},
    ]
    fdb.equipment.find = MagicMock(return_value=_chain(rows))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_engineer_equipment(
                _user(), site_id=None, customer_id=None,
                q=None, limit=200, include_unassigned=True,
            )
    out = _run(go())
    assert out["count"] == 1
    flt = fdb.equipment.find.call_args.args[0]
    # Iter 220cl — default list path filters to customer-owned rows;
    # this test opts back into the full org catalogue.
    assert flt == {"organization_id": "org-1"}


def test_list_applies_site_and_q_filters():
    from routes.svc.engineer_equipment import list_engineer_equipment
    fdb = _fake_db()
    fdb.equipment.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_engineer_equipment(
                _user(), site_id="site-1", customer_id=None,
                q="bike", limit=200, include_unassigned=True,
            )
    _run(go())
    flt = fdb.equipment.find.call_args.args[0]
    assert flt["organization_id"] == "org-1"
    assert flt["site_id"] == "site-1"
    assert "$or" in flt
    or_clauses = flt["$or"]
    assert any("name" in c for c in or_clauses)
    assert any("serial_number" in c for c in or_clauses)


# ── 6 · Cross-tenant safety ───────────────────────────────────────────


def test_create_requires_org_context():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import (
        create_engineer_equipment, EngineerEquipmentCreate,
    )
    payload = EngineerEquipmentCreate(**_valid_payload())

    async def go():
        try:
            await create_engineer_equipment(payload, {"id": "u"}, case_id=None)
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


def test_list_requires_org_context():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import list_engineer_equipment

    async def go():
        try:
            await list_engineer_equipment(
                {"id": "u"}, site_id=None, customer_id=None,
                q=None, limit=200, include_unassigned=True,
            )
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


# ── 7 · Module exports + router registration ─────────────────────────


def test_module_exports():
    from routes.svc import engineer_equipment as m
    for name in (
        "router",
        "EngineerEquipmentCreate",
        "EQUIPMENT_TYPE_OPTIONS",
        "EQUIPMENT_LOCATION_OPTIONS",
        "EQUIPMENT_STATUS_OPTIONS",
        "ensure_indexes",
        "list_engineer_equipment",
        "create_engineer_equipment",
        "get_picklists",
    ):
        assert hasattr(m, name), name


def test_router_registered_in_features():
    from route_registry import features as f
    assert "svc_engineer_equipment_router" in dir(f), (
        "Router not registered in route_registry.features"
    )


def test_router_prefix_and_paths():
    from routes.svc.engineer_equipment import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/equipment" in paths
    assert "/svc/engineer/equipment/picklists" in paths
