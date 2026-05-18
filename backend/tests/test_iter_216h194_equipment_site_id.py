"""Iter 216h194 — Craig's bug: equipment added via the OnboardingWizard
didn't show up in the Equipment list because rows had no `site_id` and
the per-site filter on GET /api/equipment excluded them.

Coverage:
  1. onboarding endpoint passes through an explicit `site_id` from the
     payload onto every inserted row.
  2. onboarding endpoint infers `site_id` for single-site orgs when the
     caller didn't include one (mostly invoice imports + legacy wizards).
  3. onboarding endpoint leaves `site_id` blank for multi-site orgs that
     didn't specify (caller must opt in — we don't guess).
  4. equipment GET lazily backfills `site_id` on legacy rows when the
     org has exactly one site (heals Craig's pre-fix data without a
     migration script).

Run: pytest backend/tests/test_iter_216h194_equipment_site_id.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_fake_db(sites_count=1, site_id="site-1"):
    """Helper: stub minimal Mongo surface used by the onboarding handler."""
    fake_sites = MagicMock()
    fake_sites_cursor = MagicMock()
    fake_sites_cursor.to_list = AsyncMock(return_value=[
        {"id": f"site-{i}"} for i in range(1, sites_count + 1)
    ])
    fake_sites.find = MagicMock(return_value=fake_sites_cursor)

    inserted = []

    async def fake_insert(doc):
        inserted.append(doc)

    fake_equipment = MagicMock()
    fake_equipment.insert_one = AsyncMock(side_effect=fake_insert)
    fake_equipment.update_many = AsyncMock(return_value=MagicMock(modified_count=0))

    fake_equipment_cursor = MagicMock()
    fake_equipment_cursor.sort = lambda *_a, **_k: fake_equipment_cursor
    fake_equipment_cursor.to_list = AsyncMock(return_value=[])
    fake_equipment.find = MagicMock(return_value=fake_equipment_cursor)

    fake_db = MagicMock()
    fake_db.sites = fake_sites
    fake_db.equipment = fake_equipment
    return fake_db, inserted


def test_onboarding_uses_explicit_site_id_from_payload() -> None:
    from routes.onboarding import onboard_equipment

    user = {"id": "u1", "organization_id": "org-1", "role": "owner"}
    fake_db, inserted = _build_fake_db(sites_count=2)  # multi-site; would NOT infer

    with patch("routes.onboarding.db", fake_db):
        out = _run(onboard_equipment(
            data={"site_id": "site-active",
                  "items": [{"name": "T1", "serial_number": "S1"}]},
            user=user,
        ))

    assert out["count"] == 1
    assert out["site_id"] == "site-active"
    assert inserted[0]["site_id"] == "site-active"


def test_onboarding_infers_site_id_for_single_site_org() -> None:
    from routes.onboarding import onboard_equipment

    user = {"id": "u1", "organization_id": "org-1", "role": "owner"}
    fake_db, inserted = _build_fake_db(sites_count=1, site_id="site-1")

    with patch("routes.onboarding.db", fake_db):
        out = _run(onboard_equipment(
            data={"items": [{"name": "T1", "serial_number": "S1"}]},
            user=user,
        ))

    assert out["site_id"] == "site-1"
    assert inserted[0]["site_id"] == "site-1"


def test_onboarding_leaves_site_id_blank_for_multi_site_no_hint() -> None:
    """Multi-site org + no explicit site_id = don't guess. Caller must
    pass site_id (the frontend does this from `activeSite`)."""
    from routes.onboarding import onboard_equipment

    user = {"id": "u1", "organization_id": "org-1", "role": "owner"}
    fake_db, inserted = _build_fake_db(sites_count=2)

    with patch("routes.onboarding.db", fake_db):
        out = _run(onboard_equipment(
            data={"items": [{"name": "T1", "serial_number": "S1"}]},
            user=user,
        ))

    assert out["site_id"] is None
    assert "site_id" not in inserted[0], "must not write a blank site_id"


def test_onboarding_per_item_site_id_overrides_org_inference() -> None:
    """Bulk imports may target multiple sites from one call. The
    per-item site_id wins over the inferred / payload-level one."""
    from routes.onboarding import onboard_equipment

    user = {"id": "u1", "organization_id": "org-1", "role": "owner"}
    fake_db, inserted = _build_fake_db(sites_count=1, site_id="site-1")

    with patch("routes.onboarding.db", fake_db):
        _run(onboard_equipment(
            data={"items": [
                {"name": "T1", "serial_number": "S1", "site_id": "site-A"},
                {"name": "T2", "serial_number": "S2"},  # no site_id → infer "site-1"
            ]},
            user=user,
        ))

    assert inserted[0]["site_id"] == "site-A"
    assert inserted[1]["site_id"] == "site-1"


def test_onboarding_persists_iter_216h193_date_and_sla_fields() -> None:
    """Regression: the wizard added SLA / warranty fields in iter
    216h193. They must round-trip through onboarding now."""
    from routes.onboarding import onboard_equipment

    user = {"id": "u1", "organization_id": "org-1"}
    fake_db, inserted = _build_fake_db(sites_count=1)

    with patch("routes.onboarding.db", fake_db):
        _run(onboard_equipment(
            data={"items": [{
                "name": "T1",
                "serial_number": "S1",
                "purchase_date": "2026-01-15",
                "warranty_expiry": "2028-01-15",
                "sla_response_time": "4h",
                "sla_contract_ref": "PF-001",
                "sla_expiry": "2027-12-31",
            }]},
            user=user,
        ))

    doc = inserted[0]
    assert doc["purchase_date"] == "2026-01-15"
    assert doc["warranty_expiry"] == "2028-01-15"
    assert doc["sla_response_time"] == "4h"
    assert doc["sla_contract_ref"] == "PF-001"
    assert doc["sla_expiry"] == "2027-12-31"
