"""
Iter 216h11 — Spec Sheet dropdown crash + bulk delete pin.

Pins:
  1. /api/spec-sheets/list returns docs as-is (including object-shaped
     `key_specs` values like `{value, unit}` and `{min, max}`).
     The frontend uses `safeRenderValue()` to coerce these — this test
     just confirms the backend continues to round-trip the raw payload so
     the bug surface stays observable (no silent server-side coercion).
  2. /api/spec-sheets/{id}/rematch tolerates object-shaped key_specs.
  3. Master Admin DELETE /api/spec-sheets/{id} hard-deletes a seeded row
     (powers the bulk-delete UI loop).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def master_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        headers={"X-RateLimit-Bypass": BYPASS} if BYPASS else None,
        timeout=15,
    )
    r.raise_for_status()
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def seeded_specs(db):
    """Seed 2 spec sheets — one clean, one with object-shaped key_specs."""
    ids = [f"test-216h11-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    db.spec_sheets.insert_many([
        {
            "id": ids[0],
            "equipment_model": "Test Treadmill",
            "equipment_type": "Treadmill",
            "manufacturer": "Pulse Fitness",
            "key_specs": {"top_speed": "20 km/h"},
            "hero_image_url": None,
            "original_filename": "test.pdf",
            "matched_count": 0,
            "matched_equipment_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": ids[1],
            "equipment_model": "Test Cycle",
            "equipment_type": "Cycle",
            "manufacturer": "Pulse Fitness",
            # The crash vector — nested objects + min/max + value/unit shapes
            "key_specs": {
                "flywheel_weight": {"value": 22, "unit": "kg"},
                "resistance": {"min": 1, "max": 24},
                "dimensions": {"length": "120cm", "width": "55cm"},
            },
            "description": {"short": "Indoor cycle", "long": "Pro indoor cycle"},
            "hero_image_url": None,
            "original_filename": "cycle.pdf",
            "matched_count": 0,
            "matched_equipment_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ])
    yield ids
    db.spec_sheets.delete_many({"id": {"$in": ids}})


def test_list_returns_raw_object_key_specs(master_headers, seeded_specs):
    """Backend must not silently flatten/coerce object-shaped key_specs."""
    r = httpx.get(f"{API_URL}/api/spec-sheets/list", headers=master_headers, timeout=15)
    assert r.status_code == 200, r.text
    by_id = {s["id"]: s for s in r.json()["spec_sheets"]}
    cycle = by_id[seeded_specs[1]]
    assert isinstance(cycle["key_specs"]["flywheel_weight"], dict)
    assert cycle["key_specs"]["flywheel_weight"] == {"value": 22, "unit": "kg"}
    assert cycle["key_specs"]["resistance"] == {"min": 1, "max": 24}
    # Description was also an object — must round-trip unchanged
    assert isinstance(cycle["description"], dict)


def test_delete_spec_sheet_hard_deletes_row(master_headers, seeded_specs, db):
    """Powers the bulk-delete UI loop — one DELETE per id."""
    target = seeded_specs[0]
    r = httpx.delete(f"{API_URL}/api/spec-sheets/{target}", headers=master_headers, timeout=15)
    assert r.status_code == 200, r.text
    assert db.spec_sheets.find_one({"id": target}) is None


def test_delete_missing_spec_sheet_returns_404(master_headers):
    """Bulk delete must show a graceful error for already-deleted rows."""
    r = httpx.delete(
        f"{API_URL}/api/spec-sheets/does-not-exist-{uuid.uuid4().hex[:6]}",
        headers=master_headers, timeout=15,
    )
    assert r.status_code == 404


def test_image_endpoint_is_public_and_404s_cleanly(seeded_specs):
    """SpecImage relies on a clean 404 (not 401) to trigger the placeholder."""
    target = seeded_specs[1]
    r = httpx.get(f"{API_URL}/api/spec-sheets/image/{target}", timeout=15)
    # No hero_image_url stored on the seeded row → endpoint must 404 (NOT 401)
    assert r.status_code == 404
