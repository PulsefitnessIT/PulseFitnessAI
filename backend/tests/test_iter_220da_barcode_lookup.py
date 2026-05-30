"""Iter 220da — Engineer barcode / QR / asset-tag lookup.

Pins ``GET /api/svc/engineer/equipment/by-code/{code}``:

  * Exact serial / asset-tag / id match → ``match=exact``.
  * Case-insensitive contains, single hit → ``match=fuzzy``.
  * Multiple fuzzy hits → ``match=multiple`` with up to 5 options.
  * No hit → 404.
  * Empty / oversized code → 400.

Plus a frontend wiring smoke check for ``BarcodeScanModal`` + the
``QrCode`` scan button mounted in ``EngineerEquipment``.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user():
    return {"id": "eng-1", "organization_id": "org-1"}


def _chain(items):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _fake_equipment_db(*, exact=None, fuzzy=None):
    fdb = MagicMock()
    fdb.equipment.find_one = AsyncMock(return_value=exact)
    fdb.equipment.find = MagicMock(return_value=_chain(fuzzy or []))
    return fdb


# ── 1 · Exact match ──────────────────────────────────────────────


def test_lookup_returns_exact_match_on_serial():
    eq = {
        "id": "eq-1", "name": "Treadmill #4",
        "serial_number": "GA-12345", "manufacturer": "Life Fitness",
    }
    fdb = _fake_equipment_db(exact=eq)

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import engineer_equipment_by_code
            return await engineer_equipment_by_code(code="GA-12345", user=_user())

    out = _run(run())
    assert out["match"] == "exact"
    assert out["equipment"]["id"] == "eq-1"


def test_lookup_query_or_includes_serial_asset_tag_and_id():
    """Defensive: pin the lookup fields so a regression doesn't drop
    asset_tag matching."""
    fdb = _fake_equipment_db(exact=None, fuzzy=[])

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import engineer_equipment_by_code
            try:
                await engineer_equipment_by_code(code="X", user=_user())
            except Exception:  # 404 is expected, we just want the call args
                pass

    _run(run())
    args, _ = fdb.equipment.find_one.call_args
    or_clause = args[0]["$or"]
    keys = {next(iter(c.keys())) for c in or_clause}
    assert keys == {"serial_number", "asset_tag", "id"}


# ── 2 · Fuzzy single ─────────────────────────────────────────────


def test_lookup_falls_back_to_single_fuzzy_match():
    fdb = _fake_equipment_db(
        exact=None,
        fuzzy=[{
            "id": "eq-2", "name": "Treadmill GA-99",
            "serial_number": "GA-99-X", "manufacturer": "LF",
        }],
    )

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import engineer_equipment_by_code
            return await engineer_equipment_by_code(code="GA-99", user=_user())

    out = _run(run())
    assert out["match"] == "fuzzy"
    assert out["equipment"]["id"] == "eq-2"


# ── 3 · Multiple fuzzy ───────────────────────────────────────────


def test_lookup_returns_multiple_options_when_more_than_one_fuzzy():
    fdb = _fake_equipment_db(
        exact=None,
        fuzzy=[
            {"id": "eq-2", "name": "Belt A", "serial_number": "GA-99-A"},
            {"id": "eq-3", "name": "Belt B", "serial_number": "GA-99-B"},
            {"id": "eq-4", "name": "Belt C", "serial_number": "GA-99-C"},
        ],
    )

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import engineer_equipment_by_code
            return await engineer_equipment_by_code(code="GA-99", user=_user())

    out = _run(run())
    assert out["match"] == "multiple"
    assert len(out["options"]) == 3
    assert {o["id"] for o in out["options"]} == {"eq-2", "eq-3", "eq-4"}


# ── 4 · 404 ──────────────────────────────────────────────────────


def test_lookup_404s_on_no_match():
    import pytest
    from fastapi import HTTPException

    fdb = _fake_equipment_db(exact=None, fuzzy=[])

    async def run():
        with patch("routes.svc.engineer_equipment.db", fdb):
            from routes.svc.engineer_equipment import engineer_equipment_by_code
            return await engineer_equipment_by_code(code="ZZZ-NOPE", user=_user())

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 404


# ── 5 · Input validation ─────────────────────────────────────────


def test_lookup_400s_on_empty_code():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.engineer_equipment import engineer_equipment_by_code
        return await engineer_equipment_by_code(code="   ", user=_user())

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


def test_lookup_400s_on_oversize_code():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.engineer_equipment import engineer_equipment_by_code
        return await engineer_equipment_by_code(code="x" * 201, user=_user())

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


# ── 6 · Frontend wiring smoke ────────────────────────────────────


def test_frontend_barcode_scan_modal_mounted():
    eq = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerEquipment.js").read_text()
    modal = Path("/app/frontend/src/pages/ServiceOps/Engineer/BarcodeScanModal.js").read_text()

    assert "BarcodeScanModal" in eq, "modal not imported into EngineerEquipment"
    assert 'data-testid="equipment-scan-btn"' in eq
    # Modal contents pinned.
    for tid in (
        "barcode-scan-modal", "barcode-scan-close", "barcode-scan-manual",
        "barcode-scan-manual-input", "barcode-scan-manual-submit",
    ):
        assert f'data-testid="{tid}"' in modal, f"missing test-id: {tid}"
    # Hits the right endpoint.
    assert "/svc/engineer/equipment/by-code/" in modal
