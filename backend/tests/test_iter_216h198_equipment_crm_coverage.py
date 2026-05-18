"""Iter 216h198 — Phase 2: Operations Equipment Detail Coverage Panel.

Coverage for the enriched `crm_coverage` payload on the
`GET /api/equipment/{equipment_id}/coverage` endpoint. The panel in the
Operations equipment-detail dialog renders this data so engineers can
tell at a glance whether a fix is in-warranty / under an aftersales
contract before they pick up tools.

Run: pytest backend/tests/test_iter_216h198_equipment_crm_coverage.py -q
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _today(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def _build_fake_db(*, equipment, contract_assets=None, contracts=None):
    """Build a fake mongo db with just the collections the endpoint reads."""
    def _async_find(rows):
        cur = MagicMock()
        cur.sort = lambda *_a, **_k: cur
        cur.to_list = AsyncMock(return_value=rows or [])
        return cur

    fake_db = MagicMock()
    fake_db.equipment = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value=equipment)

    fake_db.crm2_contract_assets = MagicMock()
    fake_db.crm2_contract_assets.find = MagicMock(return_value=_async_find(contract_assets))

    fake_db.crm2_contracts = MagicMock()
    fake_db.crm2_contracts.find = MagicMock(return_value=_async_find(contracts))

    return fake_db


def test_no_warranty_no_contract_returns_no_coverage() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Treadmill", "organization_id": "org-1"}
    fake_db = _build_fake_db(equipment=equipment)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    assert result["covered"] is False
    assert result["crm_coverage"]["has_coverage"] is False
    assert result["crm_coverage"]["best"] is None
    assert result["crm_coverage"]["all_contracts"] == []
    assert result["warranty_active"] is False


def test_active_gold_contract_returned_as_best() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Treadmill", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-gold", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-gold", "tier": "gold", "status": "active",
         "title": "Gold Aftersales", "contract_number": "G-001",
         "start_date": _today(-30), "end_date": _today(730)},
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    cov = result["crm_coverage"]
    assert cov["has_coverage"] is True
    assert cov["best"]["tier"] == "gold"
    assert cov["best"]["contract_number"] == "G-001"
    assert cov["best"]["coverage_type"] == "full"
    assert cov["best"]["expiring_soon"] is False
    assert result["covered"] is True


def test_higher_tier_wins_over_lower_tier_when_both_active() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Bike", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-bronze", "coverage_type": "parts_only"},
        {"asset_id": "eq-1", "contract_id": "c-gold", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-bronze", "tier": "bronze", "status": "active",
         "title": "Bronze", "contract_number": "B-001", "end_date": _today(365)},
        {"id": "c-gold", "tier": "gold", "status": "active",
         "title": "Gold", "contract_number": "G-001", "end_date": _today(365)},
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    assert result["crm_coverage"]["best"]["tier"] == "gold"
    # Both contracts surfaced under all_contracts.
    assert len(result["crm_coverage"]["all_contracts"]) == 2


def test_expired_contract_is_excluded_from_coverage() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Cross-trainer", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-old", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-old", "tier": "gold", "status": "active",
         "title": "Old", "contract_number": "O-001",
         "end_date": _today(-1)},  # expired yesterday
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    assert result["crm_coverage"]["has_coverage"] is False, \
        "expired contracts must NOT count as active coverage"


def test_cancelled_status_contract_is_excluded() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Rower", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-can", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-can", "tier": "platinum", "status": "cancelled",
         "title": "Cancelled", "contract_number": "X-001",
         "end_date": _today(365)},
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    assert result["crm_coverage"]["has_coverage"] is False, \
        "cancelled/draft contracts must be excluded"


def test_contract_expiring_within_90d_flagged_as_expiring_soon() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Treadmill", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-soon", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-soon", "tier": "silver", "status": "active",
         "title": "Silver", "contract_number": "S-001",
         "end_date": _today(30)},  # expires in 30 days
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    best = result["crm_coverage"]["best"]
    assert best is not None
    assert best["expiring_soon"] is True
    assert 25 <= best["days_until_expiry"] <= 31


def test_manufacturer_warranty_still_surfaces_independently_of_crm() -> None:
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {
        "id": "eq-1", "name": "Bike", "organization_id": "org-1",
        "warranty_expiry": _today(180),
    }
    fake_db = _build_fake_db(equipment=equipment)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    # CRM coverage is empty…
    assert result["crm_coverage"]["has_coverage"] is False
    # …but manufacturer warranty is still active and surfaced.
    assert result["warranty_active"] is True
    assert result["warranty_days_remaining"] is not None
    assert result["covered"] is True  # warranty alone counts as covered


def test_returns_404_when_equipment_not_found() -> None:
    from routes import equipment as eq
    from fastapi import HTTPException

    user = {"id": "u1", "organization_id": "org-1"}
    fake_db = _build_fake_db(equipment=None)

    with patch.object(eq, "db", fake_db):
        with pytest.raises(HTTPException) as excinfo:
            _run(eq.get_equipment_coverage(equipment_id="missing", user=user))
        assert excinfo.value.status_code == 404


def test_orphan_contract_asset_without_matching_contract_is_skipped() -> None:
    """If `crm2_contract_assets` references a contract that no longer
    exists, the endpoint must not throw — it just skips that row."""
    from routes import equipment as eq

    user = {"id": "u1", "organization_id": "org-1"}
    equipment = {"id": "eq-1", "name": "Treadmill", "organization_id": "org-1"}
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-ghost", "coverage_type": "full"},
        {"asset_id": "eq-1", "contract_id": "c-real", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-real", "tier": "gold", "status": "active",
         "title": "Real", "contract_number": "R-001",
         "end_date": _today(365)},
        # c-ghost intentionally missing from contracts collection.
    ]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)

    with patch.object(eq, "db", fake_db):
        result = _run(eq.get_equipment_coverage(equipment_id="eq-1", user=user))

    assert result["crm_coverage"]["has_coverage"] is True
    assert len(result["crm_coverage"]["all_contracts"]) == 1
    assert result["crm_coverage"]["best"]["contract_number"] == "R-001"
