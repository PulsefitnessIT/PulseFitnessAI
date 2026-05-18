"""Iter 216h199 — Phase 3: Service Desk auto-warranty-check at intake.

When an Operations fault is logged with `resolution_type='engineer'`,
the issue + bridged svc_case must be auto-stamped with:

  • `coverage_meta` on the issue row (cover_type, contract_id, etc.)
  • `cover_type` on the svc_case ("contract" / "warranty" / "chargeable")
  • `contract_id` on the svc_case
  • `source_meta.coverage_status` + contract refs on the svc_case

…all derived from the equipment's CRM aftersales contract + manufacturer
warranty state at the moment the fault is logged.

Run: pytest backend/tests/test_iter_216h199_auto_warranty_check.py -q
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


# ── Coverage utility (unit-level) ─────────────────────────────────────

def test_coverage_to_case_meta_uncovered() -> None:
    from utils.coverage import coverage_to_case_meta

    meta = coverage_to_case_meta({})
    assert meta["coverage_status"] == "uncovered"
    assert meta["cover_type"] == "chargeable"
    assert meta["contract_id"] == ""
    assert meta["warranty_active"] is False


def test_coverage_to_case_meta_under_contract() -> None:
    from utils.coverage import coverage_to_case_meta

    cov = {
        "has_crm_contract": True,
        "warranty_active": False,
        "warranty_expiry": None,
        "warranty_days_remaining": None,
        "cover_type": "contract",
        "best": {
            "contract_id": "c-1",
            "contract_number": "G-001",
            "contract_title": "Gold",
            "tier": "gold",
            "coverage_type": "full",
            "end_date": "2030-01-01",
            "expiring_soon": False,
        },
        "all_contracts": [],
    }
    meta = coverage_to_case_meta(cov)
    assert meta["coverage_status"] == "covered_contract"
    assert meta["cover_type"] == "contract"
    assert meta["contract_id"] == "c-1"
    assert meta["contract_number"] == "G-001"
    assert meta["contract_tier"] == "gold"
    assert meta["contract_coverage_type"] == "full"


def test_coverage_to_case_meta_warranty_only() -> None:
    from utils.coverage import coverage_to_case_meta

    cov = {
        "has_crm_contract": False,
        "warranty_active": True,
        "warranty_expiry": "2030-01-01",
        "warranty_days_remaining": 500,
        "cover_type": "warranty",
        "best": None,
        "all_contracts": [],
    }
    meta = coverage_to_case_meta(cov)
    assert meta["coverage_status"] == "covered_warranty"
    assert meta["cover_type"] == "warranty"
    assert meta["contract_id"] == ""
    assert meta["warranty_active"] is True


# ── Resolver against a fake db ────────────────────────────────────────

def _build_fake_db(*, equipment=None, contract_assets=None, contracts=None):
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


def test_resolve_equipment_coverage_picks_contract_over_warranty() -> None:
    from utils.coverage import resolve_equipment_coverage

    equipment = {
        "id": "eq-1", "warranty_expiry": _today(180),  # warranty active
    }
    contract_assets = [{"asset_id": "eq-1", "contract_id": "c-1", "coverage_type": "full"}]
    contracts = [{"id": "c-1", "tier": "gold", "status": "active",
                  "title": "Gold", "contract_number": "G-001",
                  "end_date": _today(730)}]
    fake_db = _build_fake_db(equipment=equipment,
                              contract_assets=contract_assets,
                              contracts=contracts)
    cov = _run(resolve_equipment_coverage(equipment, fake_db))
    # Both active, but contract beats warranty for case routing.
    assert cov["cover_type"] == "contract"
    assert cov["has_crm_contract"] is True
    assert cov["warranty_active"] is True


def test_resolve_equipment_coverage_returns_chargeable_when_uncovered() -> None:
    from utils.coverage import resolve_equipment_coverage

    equipment = {"id": "eq-1"}  # no warranty, no contract
    fake_db = _build_fake_db(equipment=equipment)
    cov = _run(resolve_equipment_coverage(equipment, fake_db))
    assert cov["cover_type"] == "chargeable"
    assert cov["has_crm_contract"] is False
    assert cov["warranty_active"] is False


def test_resolve_equipment_coverage_handles_empty_input() -> None:
    from utils.coverage import resolve_equipment_coverage

    fake_db = _build_fake_db()
    cov = _run(resolve_equipment_coverage({}, fake_db))
    assert cov["cover_type"] == "chargeable"
    assert cov["best"] is None


# ── Integration: _resolve_coverage_for_issue (called by /issues) ──────

def _make_fake_db_for_issue(*, equipment=None, contract_assets=None, contracts=None):
    """Same as _build_fake_db but mounted on `routes.issues.db`."""
    return _build_fake_db(
        equipment=equipment,
        contract_assets=contract_assets,
        contracts=contracts,
    )


def test_resolve_coverage_for_issue_with_no_serial_returns_uncovered() -> None:
    from routes import issues as iss

    meta = _run(iss._resolve_coverage_for_issue(
        serial_number="", organization_id="org-1",
    ))
    assert meta["coverage_status"] == "uncovered"
    assert meta["cover_type"] == "chargeable"


def test_resolve_coverage_for_issue_with_no_org_returns_uncovered() -> None:
    from routes import issues as iss

    meta = _run(iss._resolve_coverage_for_issue(
        serial_number="ABC123", organization_id=None,
    ))
    assert meta["coverage_status"] == "uncovered"


def test_resolve_coverage_for_issue_finds_contract_via_serial() -> None:
    from routes import issues as iss

    equipment = {"id": "eq-1", "serial_number": "ABC123"}
    contract_assets = [{"asset_id": "eq-1", "contract_id": "c-1", "coverage_type": "full"}]
    contracts = [{"id": "c-1", "tier": "platinum", "status": "active",
                  "title": "Platinum", "contract_number": "P-001",
                  "end_date": _today(365)}]
    fake_db = _make_fake_db_for_issue(
        equipment=equipment, contract_assets=contract_assets, contracts=contracts,
    )

    with patch.object(iss, "db", fake_db):
        meta = _run(iss._resolve_coverage_for_issue(
            serial_number="ABC123", organization_id="org-1",
        ))

    assert meta["coverage_status"] == "covered_contract"
    assert meta["cover_type"] == "contract"
    assert meta["contract_number"] == "P-001"
    assert meta["contract_tier"] == "platinum"
    assert meta["equipment_id"] == "eq-1"


def test_resolve_coverage_for_issue_missing_equipment_returns_uncovered() -> None:
    from routes import issues as iss

    fake_db = _make_fake_db_for_issue(equipment=None)
    with patch.object(iss, "db", fake_db):
        meta = _run(iss._resolve_coverage_for_issue(
            serial_number="GHOST-SERIAL", organization_id="org-1",
        ))
    assert meta["coverage_status"] == "uncovered"
    assert meta["cover_type"] == "chargeable"


# ── End-to-end: svc_case mirror picks correct cover_type ──────────────

class _CapturedCase:
    """Capture-stub for `_svc_create_case` so we can assert payload."""
    def __init__(self):
        self.payload = None

    async def __call__(self, *, payload, source, user):
        self.payload = payload
        return {"id": "case-1", **payload}


def test_mirror_issue_routes_contract_case_when_under_gold() -> None:
    """When the auto-resolved coverage says contract, the bridged
    svc_case must be created with cover_type='contract' and the
    contract_id populated — NOT the legacy hardcoded 'contract' string
    that lost the contract reference."""
    from routes import issues as iss

    issue_doc = {
        "id": "iss-1",
        "organization_id": "org-1",
        "serial_number": "ABC123",
        "machine_type": "Treadmill",
        "issue_description": "Belt slipping",
        "severity": "operational_major",
        "resolution_type": "engineer",
        "fault_code": "BELT-01",
        "coverage_meta": {
            "cover_type": "contract",
            "coverage_status": "covered_contract",
            "contract_id": "c-1",
            "contract_number": "G-001",
            "contract_title": "Gold Aftersales",
            "contract_tier": "gold",
            "contract_end_date": "2030-01-01",
            "contract_coverage_type": "full",
            "contract_expiring_soon": False,
            "warranty_active": False,
            "warranty_expiry": None,
            "warranty_days_remaining": None,
            "equipment_id": "eq-1",
        },
    }
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Lee", "email": "lee@x"}

    # Patch the svc_create_case and the db lookups inside the mirror.
    fake_db = _make_fake_db_for_issue(equipment={"id": "eq-1", "site_id": "s-1"})
    # sites lookup
    fake_db.sites = MagicMock()
    fake_db.sites.find_one = AsyncMock(return_value={"name": "Site A", "postcode": "SW1"})
    fake_db.svc_cases = MagicMock()
    fake_db.svc_cases.find_one = AsyncMock(return_value=None)  # no existing case

    captured = _CapturedCase()

    with patch.object(iss, "db", fake_db), \
         patch("routes.svc.intake._create_case", new=captured):
        _run(iss._mirror_issue_to_svc_case(issue_doc, user))

    assert captured.payload is not None, "mirror should have created a case"
    assert captured.payload["cover_type"] == "contract"
    assert captured.payload["contract_id"] == "c-1"
    meta = captured.payload["source_meta"]
    assert meta["coverage_status"] == "covered_contract"
    assert meta["contract_tier"] == "gold"
    assert meta["contract_number"] == "G-001"
    assert meta["contract_end_date"] == "2030-01-01"


def test_mirror_issue_routes_chargeable_when_uncovered() -> None:
    """No contract and no warranty → svc_case must be cover_type='chargeable'
    (not the legacy hardcoded 'contract')."""
    from routes import issues as iss

    issue_doc = {
        "id": "iss-2", "organization_id": "org-1", "serial_number": "XYZ",
        "machine_type": "Bike", "issue_description": "Wobble",
        "severity": "operational_minor", "resolution_type": "engineer",
        "coverage_meta": {
            "cover_type": "chargeable", "coverage_status": "uncovered",
            "contract_id": "", "contract_number": "", "contract_title": "",
            "contract_tier": "", "contract_end_date": "",
            "contract_coverage_type": "", "contract_expiring_soon": False,
            "warranty_active": False, "warranty_expiry": None,
            "warranty_days_remaining": None, "equipment_id": "",
        },
    }
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Lee", "email": "lee@x"}

    fake_db = _make_fake_db_for_issue(equipment=None)
    fake_db.svc_cases = MagicMock()
    fake_db.svc_cases.find_one = AsyncMock(return_value=None)

    captured = _CapturedCase()

    with patch.object(iss, "db", fake_db), \
         patch("routes.svc.intake._create_case", new=captured):
        _run(iss._mirror_issue_to_svc_case(issue_doc, user))

    assert captured.payload is not None
    assert captured.payload["cover_type"] == "chargeable"
    assert captured.payload["contract_id"] == ""
    assert captured.payload["source_meta"]["coverage_status"] == "uncovered"


def test_mirror_issue_routes_warranty_only_case() -> None:
    """Warranty active, no CRM contract → cover_type='warranty'."""
    from routes import issues as iss

    issue_doc = {
        "id": "iss-3", "organization_id": "org-1", "serial_number": "WAR-1",
        "machine_type": "Rower", "issue_description": "Display flickers",
        "severity": "operational_major", "resolution_type": "engineer",
        "coverage_meta": {
            "cover_type": "warranty", "coverage_status": "covered_warranty",
            "contract_id": "", "contract_number": "", "contract_title": "",
            "contract_tier": "", "contract_end_date": "",
            "contract_coverage_type": "", "contract_expiring_soon": False,
            "warranty_active": True, "warranty_expiry": "2030-01-01",
            "warranty_days_remaining": 500, "equipment_id": "eq-3",
        },
    }
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Lee", "email": "lee@x"}

    fake_db = _make_fake_db_for_issue(equipment={"id": "eq-3"})
    fake_db.svc_cases = MagicMock()
    fake_db.svc_cases.find_one = AsyncMock(return_value=None)

    captured = _CapturedCase()

    with patch.object(iss, "db", fake_db), \
         patch("routes.svc.intake._create_case", new=captured):
        _run(iss._mirror_issue_to_svc_case(issue_doc, user))

    assert captured.payload["cover_type"] == "warranty"
    assert captured.payload["source_meta"]["coverage_status"] == "covered_warranty"
    assert captured.payload["source_meta"]["warranty_active"] is True


def test_mirror_issue_only_runs_when_escalated_to_engineer() -> None:
    """resolution_type='self_fix' → no case mirrored (legacy behaviour)."""
    from routes import issues as iss

    issue_doc = {
        "id": "iss-4", "organization_id": "org-1", "serial_number": "x",
        "resolution_type": "self_fix", "coverage_meta": {},
    }
    user = {"id": "u1", "organization_id": "org-1"}

    captured = _CapturedCase()

    with patch("routes.svc.intake._create_case", new=captured):
        _run(iss._mirror_issue_to_svc_case(issue_doc, user))

    assert captured.payload is None, "self-fix must NOT mirror to svc_case"


def test_batch_mirror_picks_strongest_coverage_across_siblings() -> None:
    """3 machines: one under contract, one in warranty, one uncovered.
    The bundled svc_case must elect 'contract' as the cover_type and
    inherit the contract_id from the contract-covered sibling."""
    from routes import issues as iss

    docs = [
        {"id": "i-1", "organization_id": "org-1", "serial_number": "X1",
         "machine_type": "T", "resolution_type": "engineer",
         "severity": "operational_minor",
         "coverage_meta": {"cover_type": "chargeable",
                           "coverage_status": "uncovered",
                           "contract_id": "", "contract_number": "",
                           "contract_title": "", "contract_tier": "",
                           "contract_end_date": "", "contract_coverage_type": "",
                           "contract_expiring_soon": False,
                           "warranty_active": False,
                           "warranty_expiry": None,
                           "warranty_days_remaining": None}},
        {"id": "i-2", "organization_id": "org-1", "serial_number": "X2",
         "machine_type": "B", "resolution_type": "engineer",
         "severity": "operational_major",
         "coverage_meta": {"cover_type": "contract",
                           "coverage_status": "covered_contract",
                           "contract_id": "c-7", "contract_number": "G-007",
                           "contract_title": "Gold", "contract_tier": "gold",
                           "contract_end_date": "2030-01-01",
                           "contract_coverage_type": "full",
                           "contract_expiring_soon": False,
                           "warranty_active": False,
                           "warranty_expiry": None,
                           "warranty_days_remaining": None}},
        {"id": "i-3", "organization_id": "org-1", "serial_number": "X3",
         "machine_type": "R", "resolution_type": "engineer",
         "severity": "safety_critical",
         "coverage_meta": {"cover_type": "warranty",
                           "coverage_status": "covered_warranty",
                           "contract_id": "", "contract_number": "",
                           "contract_title": "", "contract_tier": "",
                           "contract_end_date": "", "contract_coverage_type": "",
                           "contract_expiring_soon": False,
                           "warranty_active": True,
                           "warranty_expiry": "2030-01-01",
                           "warranty_days_remaining": 500}},
    ]
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Lee", "email": "lee@x"}

    fake_db = _make_fake_db_for_issue(equipment={"id": "eq-1"})
    fake_db.sites = MagicMock()
    fake_db.sites.find_one = AsyncMock(return_value=None)
    fake_db.svc_cases = MagicMock()
    fake_db.svc_cases.find_one = AsyncMock(return_value=None)

    captured = _CapturedCase()

    with patch.object(iss, "db", fake_db), \
         patch("routes.svc.intake._create_case", new=captured):
        _run(iss._mirror_job_to_svc_case(docs, job_id="job-99", user=user))

    assert captured.payload is not None
    # Contract beats warranty beats uncovered.
    assert captured.payload["cover_type"] == "contract"
    assert captured.payload["contract_id"] == "c-7"
    meta = captured.payload["source_meta"]
    assert meta["coverage_status"] == "covered_contract"
    assert meta["contract_tier"] == "gold"
    assert meta["contract_number"] == "G-007"
    # Most-severe priority across siblings (p1 from safety_critical).
    assert captured.payload["priority"] == "p1"
