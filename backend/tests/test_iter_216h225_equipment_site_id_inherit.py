"""Iter 216h225 — Equipment create site_id inheritance (production bug).

User reported: manually adding equipment shows success toast but the
row never appears in the Equipment tab of a multi-site org (Pulse
Fitness Limited — 2 sites). Root cause: `EquipmentCreate` schema
didn't include `site_id`, so even if the frontend sent it, Pydantic
stripped it. The list endpoint filters by the active site → silent
black hole.

This test pins:
  1. POST /equipment with explicit site_id persists it.
  2. POST /equipment with no site_id (and a single-site org) still
     gets it from the org's only active site (defence-in-depth).
  3. The just-created equipment appears in GET /equipment?site_id=...
"""
from __future__ import annotations

import os
import uuid
import asyncio
import time

import httpx
import pytest


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def token() -> str:
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _first_site(auth) -> str:
    r = httpx.get(f"{API}/sites", headers=auth, timeout=10)
    r.raise_for_status()
    data = r.json()
    sites = data.get("sites") if isinstance(data, dict) else data
    return sites[0]["id"]


@pytest.fixture
def cleanup():
    todo: list[str] = []
    yield todo
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _go():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            await db.equipment.delete_many({"id": {"$in": todo}})
        asyncio.run(_go())
    except Exception:
        pass


def test_equipment_create_persists_explicit_site_id(auth, cleanup):
    site_id = _first_site(auth)
    name = f"216h225 explicit {uuid.uuid4().hex[:6]}"
    r = httpx.post(
        f"{API}/equipment",
        json={"name": name, "equipment_type": "Treadmill", "site_id": site_id},
        headers=auth, timeout=15,
    )
    assert r.status_code == 200
    created = r.json()
    assert created["site_id"] == site_id, (
        "Equipment must persist site_id from the create payload — "
        "Iter 216h225 added it to the EquipmentCreate schema."
    )
    cleanup.append(created["id"])


def test_equipment_create_appears_in_site_filtered_list(auth, cleanup):
    site_id = _first_site(auth)
    name = f"216h225 listcheck {uuid.uuid4().hex[:6]}"
    created = httpx.post(
        f"{API}/equipment",
        json={"name": name, "equipment_type": "Bike", "site_id": site_id},
        headers=auth, timeout=15,
    ).json()
    cleanup.append(created["id"])

    # Active-site list MUST include the new row.
    r = httpx.get(f"{API}/equipment", params={"site_id": site_id}, headers=auth, timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body if isinstance(body, list) else (body.get("equipment") or body.get("items") or [])
    matched_ids = {i["id"] for i in items}
    assert created["id"] in matched_ids, (
        "Newly created equipment with explicit site_id MUST appear in "
        "the site-filtered list — Iter 216h225 bug repro."
    )


def test_equipment_list_endpoint_round_trip_includes_site_id(auth, cleanup):
    """End-to-end probe: create → list (no filter) → confirm site_id
    round-trips so the FE can render the per-site chip correctly."""
    site_id = _first_site(auth)
    created = httpx.post(
        f"{API}/equipment",
        json={"name": f"216h225 round {uuid.uuid4().hex[:5]}", "equipment_type": "Rower", "site_id": site_id},
        headers=auth, timeout=15,
    ).json()
    cleanup.append(created["id"])

    r = httpx.get(f"{API}/equipment", headers=auth, timeout=15)
    body = r.json()
    items = body if isinstance(body, list) else (body.get("equipment") or body.get("items") or [])
    match = next((i for i in items if i["id"] == created["id"]), None)
    assert match is not None
    assert match.get("site_id") == site_id
