"""Iter 216h120 — MOD HQ rollup / drilldown scope tests.

The regression Lee reported during the demo: regional.command@mod.gov.uk
sees `0 eq` on every child site in the All Operations Sites switcher,
even after we seeded 8 machines per site. Root cause was that the
sites endpoint counted equipment by `site_id` instead of
`organization_id` for MOD child orgs, and `/equipment`,
`/issues`, and `/capex/analysis` only read the HQ's own org filter
(which is always empty — equipment lives under each child org).

These tests cover:
  • /api/sites returns the correct eq_count + issue_count per MOD child
  • /api/equipment (no site param) returns the COLLECTIVE estate
  • /api/equipment?site_id=<child> returns only that child's equipment
  • /api/issues mirrors the same scoping rules
  • /api/capex/analysis returns aggregate counts for the whole estate
  • A MOD HQ user cannot pass an unrelated site_id (cross-tenant block)
"""
from __future__ import annotations

import os

import requests

from tests._mod_test_utils import hq_login_with_mfa
from tests.conftest import _test_backend_url

API = _test_backend_url() + "/api"


def _master_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


def _seed_demo(tok: str) -> None:
    r = requests.post(
        f"{API}/mod/demo/seed-army-catterick",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=60,
    )
    r.raise_for_status()


def _hq_token() -> str:
    res = hq_login_with_mfa("army.command@army.mod.local", "ArmyDemo2026!", portal="mod")
    return res["token"]


def _find_org(account_type: str, name_contains: str) -> dict:
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        return db.organizations.find_one(
            {"account_type": account_type, "name": {"$regex": name_contains, "$options": "i"}},
            {"_id": 0},
        )
    finally:
        client.close()


def _setup() -> tuple[str, dict, dict]:
    """Ensure demo seed + Helles equipment, return (hq_token, hq_org, helles_org)."""
    master = _master_token()
    _seed_demo(master)
    # Idempotent equipment populate.
    army_hq = _find_org("mod_org", "British Army")
    assert army_hq
    requests.post(
        f"{API}/master-admin/mod/populate-demo-equipment"
        f"?parent_org_id={army_hq['id']}&machines_per_site=8&include_faults=true",
        headers={"Authorization": f"Bearer {master}"},
        timeout=60,
    ).raise_for_status()
    helles = _find_org("mod_site", "Helles Barracks Gym")
    assert helles
    return _hq_token(), army_hq, helles


def test_sites_returns_real_equipment_counts_for_mod_children() -> None:
    tok, hq, helles = _setup()
    r = requests.get(
        f"{API}/sites",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    sites = r.json()["sites"]
    helles_row = next((s for s in sites if s["id"] == helles["id"]), None)
    assert helles_row, "Helles missing from HQ /sites list"
    # Demo seed plants 8 machines + ~20 historic faults.
    assert helles_row["equipment_count"] == 8, helles_row
    assert helles_row["issue_count"] >= 1, helles_row


def test_equipment_collective_rollup_for_mod_hq() -> None:
    tok, hq, _ = _setup()
    r = requests.get(
        f"{API}/equipment",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    # 7 Catterick sites × 8 machines = 56, Vimy gets 10 (8 demo seed + 2
    # extras from a prior add-equipment test). Allow >= 50 to be robust.
    assert len(body["equipment"]) >= 50, len(body["equipment"])


def test_equipment_drilldown_returns_only_that_site() -> None:
    tok, _, helles = _setup()
    r = requests.get(
        f"{API}/equipment?site_id={helles['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    eq = r.json()["equipment"]
    assert len(eq) == 8, len(eq)
    for e in eq:
        assert e["organization_id"] == helles["id"]


def test_issues_collective_rollup_for_mod_hq() -> None:
    tok, _, _ = _setup()
    r = requests.get(
        f"{API}/issues",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200
    assert len(r.json()["issues"]) > 0


def test_capex_analysis_aggregates_whole_estate_for_mod_hq() -> None:
    tok, _, _ = _setup()
    r = requests.get(
        f"{API}/capex/analysis",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body.get("equipment", [])) >= 50, len(body.get("equipment", []))


def test_capex_drilldown_returns_only_that_site() -> None:
    tok, _, helles = _setup()
    r = requests.get(
        f"{API}/capex/analysis?site_id={helles['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body.get("equipment", [])) == 8


def test_gym_health_score_drilldown_for_mod_hq() -> None:
    """The Gym Health Score for a MOD HQ user drilling into Vimy Lines
    must not return `not_ready=true` — Lee's screenshot showed that
    despite having 10 machines + 48 open faults the empty-state copy
    kept rendering."""
    tok, _, helles = _setup()
    r = requests.get(
        f"{API}/gym-health-score?site_id={helles['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body.get("not_ready"), body
    assert "score" in body and isinstance(body["score"], int), body
    assert body["stats"]["total_equipment"] >= 8


def test_gym_health_score_collective_rollup_for_mod_hq() -> None:
    """No site_id → aggregate the whole estate. Must NOT be `not_ready`."""
    tok, _, _ = _setup()
    r = requests.get(
        f"{API}/gym-health-score",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert not body.get("not_ready"), body
    assert body["stats"]["total_equipment"] >= 50


def test_drilldown_into_unrelated_site_is_403() -> None:
    tok, _, _ = _setup()
    # Pick a non-MOD pulse pro org from the seed (the Third Space demo
    # ships with one); any random uuid would also work for negative path.
    r = requests.get(
        f"{API}/equipment?site_id=00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r.status_code == 403, r.status_code
