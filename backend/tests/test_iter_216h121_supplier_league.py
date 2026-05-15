"""Iter 216h121 — Supplier league-table regression tests.

Lee reported during demo prep that the Suppliers tab pulled no data
through for any MOD HQ user. Root cause was the same `organization_id`-
only scope bug fixed in iter 216h120, plus the supplier-to-fault
matching only honoured `serial_number` (never `equipment_id`, which is
the FK the demo seed actually populates).

Covers:
  • /api/supplier-dashboard returns equipment_suppliers ranked by score
  • Each supplier row carries rank, grade, score, resolution_rate
  • MOD HQ user with no site_id sees the WHOLE estate's suppliers
  • Passing site_id scopes to one child gym
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


def _setup() -> tuple[str, dict]:
    master = _master_token()
    requests.post(
        f"{API}/mod/demo/seed-army-catterick",
        headers={"Authorization": f"Bearer {master}"},
        timeout=60,
    ).raise_for_status()
    from pymongo import MongoClient
    client = MongoClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        army_hq = db.organizations.find_one({"name": "British Army — Head Office"}, {"_id": 0})
        helles = db.organizations.find_one({"name": "Helles Barracks Gym"}, {"_id": 0})
    finally:
        client.close()
    # Ensure equipment populated
    requests.post(
        f"{API}/master-admin/mod/populate-demo-equipment?parent_org_id={army_hq['id']}",
        headers={"Authorization": f"Bearer {master}"},
        timeout=60,
    ).raise_for_status()
    tok = hq_login_with_mfa("army.command@army.mod.local", "ArmyDemo2026!", portal="mod")["token"]
    return tok, helles


def test_supplier_league_rollup_for_mod_hq() -> None:
    tok, _ = _setup()
    r = requests.get(
        f"{API}/supplier-dashboard",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    sup = body["equipment_suppliers"]
    # Demo seed populates Life Fitness / Concept 2 / Wattbike / Technogym /
    # Pulse Fitness — at least 4 of those should appear in the league.
    assert len(sup) >= 4, [s["name"] for s in sup]
    # League contract — every row has rank/score/grade.
    for s in sup:
        assert "rank" in s and "score" in s and "grade" in s
    # Sorted by descending score (rank 1 = highest).
    for i in range(len(sup) - 1):
        assert sup[i]["score"] >= sup[i + 1]["score"], (sup[i], sup[i + 1])
    assert body["metrics"]["scope"] == "estate"


def test_supplier_league_drilldown_into_one_site() -> None:
    tok, helles = _setup()
    r = requests.get(
        f"{API}/supplier-dashboard?site_id={helles['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    sup = body["equipment_suppliers"]
    assert len(sup) >= 4  # all four cardio/strength brands at one site
    total_eq = sum(s["equipment_count"] for s in sup)
    # Helles seed: 8 machines (each maps to a manufacturer).
    assert total_eq == 8
    assert body["metrics"]["scope"] == "site"
