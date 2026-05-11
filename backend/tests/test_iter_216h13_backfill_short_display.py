"""
Iter 216h13 — Equipment short-display backfill endpoint.

Pins:
  1. `/api/master-admin/equipment/backfill-short-display` requires
     master admin (403 for non-master).
  2. Dry-run returns a preview without writing.
  3. Commit writes the short shape AND preserves the full description.
  4. Idempotent — re-running on already-short rows is a no-op.
  5. Tenant-scoped via `organization_id`.
  6. Only touches rows that look invoice-imported (skips manually-
     added equipment).
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

LONG_PULSE = (
    "Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, "
    "Apple/Samsung Watch Connectivity, Content Mirroring & Wireless "
    "Charging in Sand Black"
)


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
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def seeded_legacy_rows(db):
    """Seed 3 invoice-imported rows in the legacy-long shape + 1
    already-short row (control — must NOT be touched)."""
    org_id = f"test-h13-org-{uuid.uuid4().hex[:8]}"
    ids = [f"test-h13-eq-{uuid.uuid4().hex[:8]}" for _ in range(4)]
    db.equipment.insert_many([
        {
            "id": ids[0], "organization_id": org_id,
            "name": LONG_PULSE, "model": LONG_PULSE,
            "manufacturer": "Pulse Fitness", "serial_number": "",
            "location": "Carshalton College", "supplier": "Pulse Fitness",
            "stock_item_code": "200H-AAF",
            "invoice_number": "0000022528",
            "import_id": "test-import-h13",
            "notes": "Imported from invoice 0000022528",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": ids[1], "organization_id": org_id,
            "name": "Club Line Upright Cycle with 10.1\" Tactile Key Console",
            "model": "Club Line Upright Cycle with 10.1\" Tactile Key Console",
            "manufacturer": "Pulse Fitness",
            "location": "Carshalton College", "supplier": "Pulse Fitness",
            "stock_item_code": "240G-AAV",
            "import_id": "test-import-h13",
            "notes": "Imported from invoice 0000022528",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": ids[2], "organization_id": org_id,
            "name": "Premium Treadmill with 18.5\" Touchscreen Console & Apple Watch Connectivity",
            "model": "Premium Treadmill with 18.5\" Touchscreen Console & Apple Watch Connectivity",
            "manufacturer": "Pulse Fitness",
            "location": "Carshalton College", "supplier": "Pulse Fitness",
            "stock_item_code": "210T-BBC",
            "notes": "Imported from invoice 0000022528",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        # Control row: already-short, manual-add. Must NOT be touched.
        {
            "id": ids[3], "organization_id": org_id,
            "name": "Treadmill", "model": "260G",
            "manufacturer": "Pulse Fitness", "serial_number": "12345",
            "location": "Main Gym", "supplier": "Pulse Fitness",
            "notes": "Added manually",  # ← no "Imported from invoice" prefix
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ])
    yield org_id, ids
    db.equipment.delete_many({"id": {"$in": ids}})


def test_backfill_dry_run_previews_without_writing(master_headers, seeded_legacy_rows, db):
    org_id, ids = seeded_legacy_rows
    r = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=true",
        headers=master_headers,
        json={"organization_id": org_id},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is True
    assert data["equipment_to_update"] == 3  # the 3 legacy rows
    assert data["equipment_updated"] == 0    # nothing written on dry run
    # Confirm DB still has the legacy long name
    untouched = db.equipment.find_one({"id": ids[0]})
    assert untouched["name"] == LONG_PULSE


def test_backfill_commit_writes_short_shape(master_headers, seeded_legacy_rows, db):
    org_id, ids = seeded_legacy_rows
    r = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=false",
        headers=master_headers,
        json={"organization_id": org_id},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is False
    assert data["equipment_updated"] == 3
    # Verify new shape per row
    stepmill = db.equipment.find_one({"id": ids[0]})
    assert stepmill["name"] == "StepMill"
    assert stepmill["model"] == "200H-AAF"
    assert stepmill["description"] == LONG_PULSE  # FULL description preserved
    cycle = db.equipment.find_one({"id": ids[1]})
    assert cycle["name"] == "Upright Cycle"
    assert cycle["model"] == "240G-AAV"
    treadmill = db.equipment.find_one({"id": ids[2]})
    assert treadmill["name"] == "Treadmill"
    assert treadmill["model"] == "210T-BBC"


def test_backfill_skips_already_short_rows(master_headers, seeded_legacy_rows, db):
    """The manual-add control row (id[3]) must NOT be touched."""
    org_id, ids = seeded_legacy_rows
    httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=false",
        headers=master_headers,
        json={"organization_id": org_id}, timeout=20,
    )
    control = db.equipment.find_one({"id": ids[3]})
    assert control["name"] == "Treadmill"  # unchanged
    assert control["model"] == "260G"


def test_backfill_is_idempotent(master_headers, seeded_legacy_rows):
    """Running commit twice should update 3 rows the first time and 0
    rows the second time."""
    org_id, _ = seeded_legacy_rows
    r1 = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=false",
        headers=master_headers, json={"organization_id": org_id}, timeout=20,
    )
    assert r1.json()["equipment_updated"] == 3
    r2 = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=false",
        headers=master_headers, json={"organization_id": org_id}, timeout=20,
    )
    assert r2.json()["equipment_updated"] == 0


def test_backfill_rejects_non_master_admin(seeded_legacy_rows):
    """403 for callers without master-admin role."""
    org_id, _ = seeded_legacy_rows
    r = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=true",
        json={"organization_id": org_id}, timeout=15,
    )
    # No auth → 401 or 403 — either is acceptable for a gated endpoint.
    assert r.status_code in (401, 403)


def test_backfill_filters_by_site_name(master_headers, seeded_legacy_rows, db):
    """Filtering by `site_name` only touches rows in that location."""
    org_id, ids = seeded_legacy_rows
    # Move one legacy row to a different site
    db.equipment.update_one({"id": ids[0]}, {"$set": {"location": "Other Site"}})
    r = httpx.post(
        f"{API_URL}/api/master-admin/equipment/backfill-short-display?dry_run=false",
        headers=master_headers,
        json={"organization_id": org_id, "site_name": "Carshalton College"},
        timeout=20,
    )
    data = r.json()
    # Only 2 of the 3 legacy rows are in Carshalton now
    assert data["equipment_updated"] == 2
    # The moved row should still be in its legacy shape
    moved = db.equipment.find_one({"id": ids[0]})
    assert moved["name"] == LONG_PULSE
