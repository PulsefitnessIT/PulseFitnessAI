"""Iter 216h196 — Phase 1: CRM Sites & Equipment tab.

Coverage for the new endpoints that join CRM contract data with
Operations sites + equipment:

  GET  /api/crm/v2/companies/{id}/sites-and-equipment
  POST /api/crm/v2/companies/{id}/link-organization
  POST /api/crm/v2/companies/{id}/equipment-coverage

Tests use a fake Mongo so they're hermetic — no db state required.

Run: pytest backend/tests/test_iter_216h196_sites_and_equipment.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_fake_db(*, company, user_org=None, sites=None, equipment=None,
                   contracts=None, contract_assets=None):
    """Configures a fake db with the collections used by the endpoint."""
    def _async_find(rows):
        cur = MagicMock()
        cur.sort = lambda *_a, **_k: cur
        cur.to_list = AsyncMock(return_value=rows or [])
        return cur

    fake_db = MagicMock()

    # crm2_companies
    fake_db.crm2_companies = MagicMock()
    fake_db.crm2_companies.find_one = AsyncMock(return_value=company)
    fake_db.crm2_companies.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    # organizations
    fake_db.organizations = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value=user_org)

    # sites
    fake_db.sites = MagicMock()
    fake_db.sites.find = MagicMock(return_value=_async_find(sites))

    # equipment
    fake_db.equipment = MagicMock()
    fake_db.equipment.find = MagicMock(return_value=_async_find(equipment))
    fake_db.equipment.find_one = AsyncMock(return_value=(equipment or [{}])[0] if equipment else None)

    # crm2_contract_assets + crm2_contracts
    fake_db.crm2_contract_assets = MagicMock()
    fake_db.crm2_contract_assets.find = MagicMock(return_value=_async_find(contract_assets))
    fake_db.crm2_contract_assets.insert_one = AsyncMock()

    fake_db.crm2_contracts = MagicMock()
    fake_db.crm2_contracts.find = MagicMock(return_value=_async_find(contracts))
    fake_db.crm2_contracts.insert_one = AsyncMock()

    return fake_db


def test_unlinked_when_no_match() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "Some Other Company"}
    user_org = {"id": "org-1", "name": "Pulse Fitness Limited"}

    fake_db = _build_fake_db(company=company, user_org=user_org)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    assert result["linked_via"] == "unlinked"
    assert result["linked_organization_id"] is None
    assert result["sites"] == []


def test_linked_via_explicit_link() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {
        "id": "co-1", "organization_id": "org-1", "name": "Customer X",
        "linked_organization_id": "org-1",
    }
    sites = [{"id": "site-A", "name": "Site A", "status": "active"}]
    equipment = [{"id": "eq-1", "name": "Treadmill 1", "site_id": "site-A",
                  "organization_id": "org-1"}]

    fake_db = _build_fake_db(company=company, sites=sites, equipment=equipment)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    assert result["linked_via"] == "explicit_link"
    assert result["linked_organization_id"] == "org-1"
    assert len(result["sites"]) == 1
    assert result["sites"][0]["equipment"][0]["id"] == "eq-1"
    assert result["sites"][0]["equipment"][0]["coverage"]["has_coverage"] is False


def test_linked_via_name_match_case_insensitive() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1",
               "name": "pulse fitness limited"}  # lowercase
    user_org = {"id": "org-1", "name": "Pulse Fitness Limited"}  # mixed case
    sites = [{"id": "site-A", "name": "iGym Carshalton", "status": "active"}]
    equipment = [{"id": "eq-1", "name": "Treadmill", "site_id": "site-A",
                  "organization_id": "org-1"}]

    fake_db = _build_fake_db(company=company, user_org=user_org,
                              sites=sites, equipment=equipment)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    assert result["linked_via"] == "name_match"
    assert result["linked_organization_id"] == "org-1"
    assert len(result["sites"]) == 1


def test_coverage_resolution_picks_highest_tier_active_contract() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "X",
               "linked_organization_id": "org-1"}
    sites = [{"id": "site-A", "name": "Site A", "status": "active"}]
    equipment = [{"id": "eq-1", "name": "Treadmill", "site_id": "site-A",
                  "organization_id": "org-1"}]
    contract_assets = [
        {"asset_id": "eq-1", "contract_id": "c-bronze", "coverage_type": "parts_only"},
        {"asset_id": "eq-1", "contract_id": "c-gold", "coverage_type": "full"},
    ]
    contracts = [
        {"id": "c-bronze", "tier": "bronze", "status": "active",
         "end_date": "2030-01-01", "title": "Bronze", "contract_number": "B-001"},
        {"id": "c-gold", "tier": "gold", "status": "active",
         "end_date": "2030-01-01", "title": "Gold", "contract_number": "G-001"},
    ]

    fake_db = _build_fake_db(company=company, sites=sites, equipment=equipment,
                              contract_assets=contract_assets, contracts=contracts)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    eq = result["sites"][0]["equipment"][0]
    assert eq["coverage"]["has_coverage"] is True
    # Gold beats bronze.
    assert eq["coverage"]["tier"] == "gold"
    assert eq["coverage"]["contract_number"] == "G-001"
    assert result["totals"]["covered"] == 1
    assert result["totals"]["uncovered"] == 0


def test_coverage_resolution_ignores_expired_contracts() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "X",
               "linked_organization_id": "org-1"}
    equipment = [{"id": "eq-1", "name": "Treadmill", "site_id": "site-A",
                  "organization_id": "org-1"}]
    sites = [{"id": "site-A", "name": "Site A", "status": "active"}]
    contract_assets = [{"asset_id": "eq-1", "contract_id": "c-old", "coverage_type": "full"}]
    contracts = [{"id": "c-old", "tier": "gold", "status": "active",
                  "end_date": "2020-01-01", "title": "Old", "contract_number": "O-001"}]

    fake_db = _build_fake_db(company=company, sites=sites, equipment=equipment,
                              contract_assets=contract_assets, contracts=contracts)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    eq = result["sites"][0]["equipment"][0]
    assert eq["coverage"]["has_coverage"] is False, "expired contract must not count as covered"


def test_unassigned_equipment_surfaces_under_unassigned_bucket() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "X",
               "linked_organization_id": "org-1"}
    sites = [{"id": "site-A", "name": "Site A", "status": "active"}]
    # An orphan equipment row with no site_id (pre-216h194 legacy).
    equipment = [
        {"id": "eq-1", "name": "Onsite", "site_id": "site-A", "organization_id": "org-1"},
        {"id": "eq-2", "name": "Orphan", "organization_id": "org-1"},
    ]
    fake_db = _build_fake_db(company=company, sites=sites, equipment=equipment)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.company_sites_and_equipment(company_id="co-1", user=user))

    site_ids = [s["id"] for s in result["sites"]]
    assert "__unassigned__" in site_ids
    unassigned = next(s for s in result["sites"] if s["id"] == "__unassigned__")
    assert len(unassigned["equipment"]) == 1
    assert unassigned["equipment"][0]["id"] == "eq-2"


def test_link_organization_rejects_other_org() -> None:
    from routes import crm_contracts as cc
    from fastapi import HTTPException

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "X"}
    fake_db = _build_fake_db(company=company)

    with patch.object(cc, "db", fake_db):
        with pytest.raises(HTTPException) as excinfo:
            _run(cc.link_company_to_organization(
                company_id="co-1",
                data={"organization_id": "org-OTHER"},
                user=user,
            ))
        assert excinfo.value.status_code == 403


def test_link_organization_happy_path() -> None:
    from routes import crm_contracts as cc

    user = {"id": "u1", "organization_id": "org-1"}
    company = {"id": "co-1", "organization_id": "org-1", "name": "X"}
    fake_db = _build_fake_db(company=company)

    with patch.object(cc, "db", fake_db):
        result = _run(cc.link_company_to_organization(
            company_id="co-1",
            data={"organization_id": "org-1"},
            user=user,
        ))

    assert result["success"] is True
    assert result["linked_organization_id"] == "org-1"
    fake_db.crm2_companies.update_one.assert_called_once()
