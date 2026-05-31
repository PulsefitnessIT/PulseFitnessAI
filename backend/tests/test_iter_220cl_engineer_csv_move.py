"""Iter 220cl — Engineer CSV move + customer-only equipment scope.

User feedback (Feb 2026):
  1. Remove "Template" + "Import CSV" buttons from
     /svc/engineer/equipment list page.
  2. The equipment tab should only show equipment imported into a
     customer's account via the onboarding process.
  3. Drop "Orbit 4 Asset ID" and "Sicon Equipment ID" columns from
     the engineer's CSV template — those are Pulse Fitness only.

Backend pins:
  * ``GET /svc/engineer/equipment/template-csv`` exists, returns CSV
    headers that do NOT contain "Orbit 4" or "Sicon".
  * ``GET /svc/engineer/equipment`` only returns rows that have a
    ``customer_id`` set (the default). ``include_unassigned=true``
    opt-in returns the full org catalogue.
  * ``POST /svc/engineer/customers/{customer_id}/equipment/import-csv``
    bulk-creates equipment rows, all tagged with the customer_id.
    404s for cross-tenant customer ids.

Frontend pins:
  * EngineerEquipment.js no longer renders ``CsvActions`` (the
    component is deleted and the testids are gone).
  * EngineerCustomers.js exposes the per-customer CSV buttons
    inside the active customer drawer.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="u-1"):
    return {"id": uid, "organization_id": org}


# ── 1 · Slim CSV template — no Pulse-only columns ────────────────────


def test_engineer_csv_template_headers_exclude_pulse_only_columns():
    from routes.svc.engineer_equipment import _ENGINEER_CSV_HEADERS
    blob = ",".join(_ENGINEER_CSV_HEADERS).lower()
    assert "orbit" not in blob, _ENGINEER_CSV_HEADERS
    assert "sicon" not in blob, _ENGINEER_CSV_HEADERS
    # Required field set kept.
    for col in ("Name", "Type", "Manufacturer", "Model", "Serial Number"):
        assert col in _ENGINEER_CSV_HEADERS


def test_template_endpoint_403s_without_org():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import get_engineer_csv_template

    async def go():
        try:
            await get_engineer_csv_template({"id": "u"})
            return False
        except HTTPException as exc:
            return exc.status_code == 403
    assert _run(go())


def test_template_endpoint_returns_csv():
    from routes.svc.engineer_equipment import get_engineer_csv_template

    async def go():
        return await get_engineer_csv_template(_user())
    resp = _run(go())
    body = resp.body.decode("utf-8") if hasattr(resp, "body") else str(resp)
    # No Orbit 4 / Sicon header.
    assert "Orbit" not in body
    assert "Sicon" not in body
    # Engineer-friendly columns present.
    assert "Name" in body and "Type" in body


# ── 2 · List filter — customer-owned by default ──────────────────────


def _chain(default):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.to_list = AsyncMock(return_value=default)
    return cur


def test_list_engineer_equipment_filters_to_customer_owned_by_default():
    from routes.svc.engineer_equipment import list_engineer_equipment
    fdb = MagicMock()
    fdb.equipment.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_engineer_equipment(
                _user(), site_id=None, customer_id=None,
                q=None, limit=200, include_unassigned=False,
            )
    _run(go())
    flt = fdb.equipment.find.call_args.args[0]
    assert flt["organization_id"] == "org-1"
    assert flt["customer_id"] == {"$exists": True, "$ne": None}


def test_list_include_unassigned_opts_back_in():
    from routes.svc.engineer_equipment import list_engineer_equipment
    fdb = MagicMock()
    fdb.equipment.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_engineer_equipment(
                _user(), site_id=None, customer_id=None,
                q=None, limit=200, include_unassigned=True,
            )
    _run(go())
    flt = fdb.equipment.find.call_args.args[0]
    assert "customer_id" not in flt


def test_list_specific_customer_overrides_existence_check():
    from routes.svc.engineer_equipment import list_engineer_equipment
    fdb = MagicMock()
    fdb.equipment.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await list_engineer_equipment(
                _user(), site_id=None, customer_id="cust-99",
                q=None, limit=200, include_unassigned=False,
            )
    _run(go())
    flt = fdb.equipment.find.call_args.args[0]
    assert flt["customer_id"] == "cust-99"


# ── 3 · Per-customer CSV import ──────────────────────────────────────


def _parse_row_uses_correct_schema():
    """Sanity: the row parser consumes the slim template headers and
    tags the row with customer_id + customer_name."""
    from routes.svc.engineer_equipment import _parse_engineer_csv_row
    customer = {"id": "c-1", "name": "Acme", "site_id": "site-A"}
    row = {
        "Name": "Treadmill #14",
        "Type": "Treadmill",
        "Manufacturer": "Life Fitness",
        "Model": "Integrity DX",
        "Serial Number": "LF-12345",
        "Location": "Cardio Zone",
        "Length (m)": "2.1",
        "Notes": "Test",
    }
    doc = _parse_engineer_csv_row(
        row, _user(), customer=customer, now="2026-01-01T00:00:00Z",
    )
    assert doc["customer_id"] == "c-1"
    assert doc["customer_name"] == "Acme"
    assert doc["site_id"] == "site-A"
    assert doc["name"] == "Treadmill #14"
    assert doc["equipment_type"] == "Treadmill"
    assert doc["serial_number"] == "LF-12345"
    assert doc["location"] == "Cardio Zone"
    assert doc["length"] == 2.1
    assert doc["created_via"] == "engineer_customer_csv"


def test_parse_row():
    _parse_row_uses_correct_schema()


def test_parse_row_skips_blank_name():
    from routes.svc.engineer_equipment import _parse_engineer_csv_row
    customer = {"id": "c-1", "name": "Acme"}
    doc = _parse_engineer_csv_row(
        {"Name": "   ", "Type": "Treadmill"},
        _user(), customer=customer, now="now",
    )
    assert doc is None


def test_parse_row_handles_bad_numerics():
    """Garbage in the length/width columns must not crash — silently
    coerced to None."""
    from routes.svc.engineer_equipment import _parse_engineer_csv_row
    customer = {"id": "c-1", "name": "Acme"}
    doc = _parse_engineer_csv_row(
        {"Name": "X", "Length (m)": "nope"},
        _user(), customer=customer, now="now",
    )
    assert doc is not None
    assert doc["length"] is None


def test_csv_import_endpoint_404s_for_unknown_customer():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import import_customer_equipment_csv
    fdb = MagicMock()
    fdb.svc_engineer_customers.find_one = AsyncMock(return_value=None)
    file = MagicMock()
    file.read = AsyncMock(return_value=b"")

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await import_customer_equipment_csv(
                    "c-X", file=file, user=_user(),
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 404
    assert _run(go())


def test_csv_import_endpoint_persists_rows_tagged_with_customer_id():
    from routes.svc.engineer_equipment import import_customer_equipment_csv
    fdb = MagicMock()
    fdb.svc_engineer_customers.find_one = AsyncMock(return_value={
        "id": "c-1", "name": "Acme", "site_id": "site-A",
    })
    fdb.equipment.insert_many = AsyncMock()
    csv_body = (
        b"Name,Type,Manufacturer,Model,Serial Number,"
        b"Purchase Date (YYYY-MM-DD),Warranty Expiry (YYYY-MM-DD),"
        b"Length (m),Width (m),Height (m),Location,Notes\r\n"
        b"Treadmill 1,Treadmill,Life Fitness,Integrity DX,LF-1,"
        b",,2.1,0.9,1.6,Cardio Zone,\r\n"
        b"Bike 1,Spin Bike,Wattbike,Atom,WB-2,"
        b",,1.2,0.6,1.3,Cardio Zone,\r\n"
        # Blank row should be skipped silently.
        b",,,,,,,,,,,\r\n"
    )
    file = MagicMock()
    file.read = AsyncMock(return_value=csv_body)

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            return await import_customer_equipment_csv(
                "c-1", file=file, user=_user(),
            )
    out = _run(go())
    assert out["inserted"] == 2
    assert out["skipped"] == 1
    fdb.equipment.insert_many.assert_awaited_once()
    inserted_rows = fdb.equipment.insert_many.await_args.args[0]
    for row in inserted_rows:
        assert row["customer_id"] == "c-1"
        assert row["customer_name"] == "Acme"
        assert row["site_id"] == "site-A"
        assert row["organization_id"] == "org-1"
        assert row["created_via"] == "engineer_customer_csv"


def test_csv_import_endpoint_rejects_empty_file():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import import_customer_equipment_csv
    fdb = MagicMock()
    fdb.svc_engineer_customers.find_one = AsyncMock(return_value={"id": "c-1"})
    file = MagicMock()
    file.read = AsyncMock(return_value=b"")

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await import_customer_equipment_csv(
                    "c-1", file=file, user=_user(),
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 400
    assert _run(go())


def test_csv_import_endpoint_rejects_huge_file():
    from fastapi import HTTPException
    from routes.svc.engineer_equipment import import_customer_equipment_csv
    fdb = MagicMock()
    fdb.svc_engineer_customers.find_one = AsyncMock(return_value={"id": "c-1"})
    file = MagicMock()
    # 3 MB of bytes — exceeds the 2 MB cap.
    file.read = AsyncMock(return_value=b"x" * (3 * 1024 * 1024))

    async def go():
        with patch("routes.svc.engineer_equipment.db", fdb):
            try:
                await import_customer_equipment_csv(
                    "c-1", file=file, user=_user(),
                )
                return False
            except HTTPException as exc:
                return exc.status_code == 400 and "too large" in exc.detail.lower()
    assert _run(go())


# ── 4 · Router registrations + module exports ────────────────────────


def test_router_paths_include_220cl_endpoints():
    from routes.svc.engineer_equipment import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/equipment/template-csv" in paths
    assert "/svc/engineer/customers/{customer_id}/equipment/import-csv" in paths


def test_module_exports():
    from routes.svc import engineer_equipment as m
    for name in (
        "_ENGINEER_CSV_HEADERS",
        "_parse_engineer_csv_row",
        "get_engineer_csv_template",
        "import_customer_equipment_csv",
    ):
        assert hasattr(m, name), name


# ── 5 · Frontend pins ─────────────────────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_engineer_equipment_page_drops_csv_buttons():
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    # Old testids must be gone.
    for tid in (
        'equipment-csv-actions',
        'equipment-csv-download',
        'equipment-csv-import',
        'equipment-csv-file-input',
    ):
        assert tid not in src, f"{tid} should have been removed"
    # The CsvActions component itself is deleted.
    assert "function CsvActions" not in src
    assert "<CsvActions" not in src


def test_customer_drawer_has_per_customer_csv_buttons():
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    # Per-customer testids are dynamic (interpolated with `customer.id`).
    assert "customer-csv-template-${customer.id}" in src
    assert "customer-csv-import-${customer.id}" in src
    # Calls the engineer-scoped customer-bound import endpoint.
    assert "/svc/engineer/customers/${customer.id}/equipment/import-csv" in src
    assert "/svc/engineer/equipment/template-csv" in src
    # Component definition.
    assert "function CustomerEquipmentCsv" in src


def test_customer_wizard_equipment_step_hints_point_to_drawer():
    """The wizard's Equipment step text should mention the customer
    drawer now, not the Equipment tab."""
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    assert "customer's drawer" in src
