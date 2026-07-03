"""Iter 220d — Per-machine work reports + quick-add note presets.

Engineers on a PPM site visit can now log one row per machine they
serviced (rather than re-typing the same notes in a single summary
blob). The new `svc_work_visit_machines` collection captures the
spreadsheet-style data their real-world workflow uses, and the
`svc_note_presets` collection turns recurring sentences into 1-tap
chips.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://ops-parts-request.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": secret} if secret else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass(),
        )
        r.raise_for_status()
    _CACHE[email] = r.json()["token"]
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def admin(db):
    return db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0})


@pytest.fixture
def case(db, admin):
    cid = f"pm-220d-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "reference": "PM-T",
        "title": "Per-machine test",
        "status": "on_site",
        "assigned_engineer_id": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield cid
    db.svc_cases.delete_one({"id": cid})
    db.svc_work_visit_machines.delete_many({"case_id": cid})


@pytest.fixture
def preset_cleanup(db, admin):
    created = []
    yield created
    if created:
        db.svc_note_presets.delete_many({
            "organization_id": admin["organization_id"],
            "id": {"$in": created},
        })


# ─────────────────── Machines: CRUD + copy-down ───────────────────


def test_create_then_list_returns_rows_in_order(case):
    with httpx.Client(timeout=15.0) as c:
        for name in ("BikeErg #1", "BikeErg #2", "RowErg #1"):
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case}/machines",
                json={"asset_name": name},
                headers=_hdr(),
            )
            assert r.status_code == 200, r.text
        r = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    body = r.json()
    assert body["count"] == 3
    names = [m["asset_name"] for m in body["machines"]]
    assert names == ["BikeErg #1", "BikeErg #2", "RowErg #1"]
    indexes = [m["order_index"] for m in body["machines"]]
    assert indexes == [0, 1, 2]


def test_patch_updates_serviced_cleaned_notes(case):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines",
            json={"asset_name": "Treadmill A"},
            headers=_hdr(),
        )
        row_id = r.json()["id"]
        r2 = c.patch(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{row_id}",
            json={"serviced": True, "cleaned": True, "notes": "Belt replaced"},
            headers=_hdr(),
        )
    assert r2.status_code == 200
    body = r2.json()
    assert body["serviced"] is True
    assert body["cleaned"] is True
    assert body["notes"] == "Belt replaced"


def test_delete_removes_row(case):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines",
            json={"asset_name": "Treadmill Z"},
            headers=_hdr(),
        )
        row_id = r.json()["id"]
        rd = c.delete(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{row_id}",
            headers=_hdr(),
        )
        lst = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    assert rd.status_code == 200
    assert lst.json()["count"] == 0


def test_copy_down_propagates_to_subsequent_rows_only(case):
    """Ticking 'Serviced' on row 1 and tapping copy-down must apply to
    rows 2 + 3, NOT back-fill anything earlier."""
    with httpx.Client(timeout=15.0) as c:
        ids = []
        for name in ("Erg A", "Erg B", "Erg C"):
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case}/machines",
                json={"asset_name": name},
                headers=_hdr(),
            )
            ids.append(r.json()["id"])
        # Mark Erg A serviced + notes set.
        c.patch(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{ids[0]}",
            json={"serviced": True, "notes": "Calibration check passed"},
            headers=_hdr(),
        )
        # Copy down from Erg A.
        cd = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{ids[0]}/copy-down",
            json={"fields": ["serviced", "notes"]},
            headers=_hdr(),
        )
        lst = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    assert cd.json()["updated"] == 2
    rows = lst.json()["machines"]
    by_name = {r["asset_name"]: r for r in rows}
    assert by_name["Erg A"]["serviced"] is True
    assert by_name["Erg B"]["serviced"] is True
    assert by_name["Erg B"]["notes"] == "Calibration check passed"
    assert by_name["Erg C"]["serviced"] is True
    assert by_name["Erg C"]["notes"] == "Calibration check passed"


def test_copy_down_from_last_row_updates_zero(case):
    with httpx.Client(timeout=15.0) as c:
        ids = []
        for name in ("A", "B"):
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case}/machines",
                json={"asset_name": name},
                headers=_hdr(),
            )
            ids.append(r.json()["id"])
        cd = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{ids[-1]}/copy-down",
            json={"fields": ["serviced"]},
            headers=_hdr(),
        )
    assert cd.json()["updated"] == 0


# ─────────────────── Asset link snapshots the name/serial/type ───────────────────


def test_create_with_asset_id_snapshots_equipment(db, admin, case):
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id, "organization_id": admin["organization_id"],
        "name": "Indoor Rower", "manufacturer": "Concept 2",
        "model": "Model D", "equipment_type": "Rower",
        "serial_number": "C2-1234",
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case}/machines",
                json={"asset_id": asset_id},
                headers=_hdr(),
            )
        body = r.json()
        assert body["asset_id"] == asset_id
        assert body["asset_serial"] == "C2-1234"
        assert body["asset_type"] == "Rower"
        # Manufacturer prefix in the label.
        assert "Concept 2" in (body["asset_name"] or "")
    finally:
        db.equipment.delete_one({"id": asset_id})


# ─────────────────── Note presets ───────────────────


def test_preset_create_lists_pinned_first(preset_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r1 = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Shock cord worn — recommend replacement", "scope": "shared"},
            headers=_hdr(),
        )
        preset_cleanup.append(r1.json()["id"])
        r2 = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Million-Meter calibration check needed", "scope": "shared", "pinned": True},
            headers=_hdr(),
        )
        preset_cleanup.append(r2.json()["id"])
        lst = c.get(f"{BASE}/api/svc/engineer/note-presets", headers=_hdr())
    presets = lst.json()["presets"]
    # The pinned one should sort above the unpinned one regardless of
    # creation order.
    seen = [p["text"] for p in presets if p["id"] in {r1.json()["id"], r2.json()["id"]}]
    assert seen[0] == "Million-Meter calibration check needed"


def test_preset_dedupes_same_text_bumps_use_count(preset_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r1 = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Belt fatigue — order replacement", "scope": "personal"},
            headers=_hdr(),
        )
        preset_cleanup.append(r1.json()["id"])
        # Same text again — should dedupe (return same id, bump count).
        r2 = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Belt fatigue — order replacement", "scope": "personal"},
            headers=_hdr(),
        )
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["use_count"] == 2


def test_preset_used_endpoint_increments_count(preset_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Drag-factor reset to 130", "scope": "personal"},
            headers=_hdr(),
        )
        pid = r.json()["id"]
        preset_cleanup.append(pid)
        c.post(f"{BASE}/api/svc/engineer/note-presets/{pid}/used", headers=_hdr())
        c.post(f"{BASE}/api/svc/engineer/note-presets/{pid}/used", headers=_hdr())
        lst = c.get(f"{BASE}/api/svc/engineer/note-presets", headers=_hdr())
    me = next(p for p in lst.json()["presets"] if p["id"] == pid)
    assert me["use_count"] == 3  # 1 from create + 2 from used


def test_preset_archive_via_delete_hides_from_list(preset_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/note-presets",
            json={"text": "Squeaky chain — lubricate", "scope": "personal"},
            headers=_hdr(),
        )
        pid = r.json()["id"]
        preset_cleanup.append(pid)
        c.delete(f"{BASE}/api/svc/engineer/note-presets/{pid}", headers=_hdr())
        lst = c.get(f"{BASE}/api/svc/engineer/note-presets", headers=_hdr())
    visible_ids = {p["id"] for p in lst.json()["presets"]}
    assert pid not in visible_ids


def test_max_machines_per_case_enforced(db, admin, case):
    """Insert MAX directly so we can confirm the create endpoint refuses
    the 81st row without us having to hammer it ourselves."""
    bulk = [
        {
            "id": str(uuid.uuid4()),
            "organization_id": admin["organization_id"],
            "case_id": case,
            "asset_name": f"X{i}",
            "order_index": i,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(80)
    ]
    db.svc_work_visit_machines.insert_many(bulk)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines",
            json={"asset_name": "Overflow"},
            headers=_hdr(),
        )
    assert r.status_code == 400
    assert "Max" in r.text
