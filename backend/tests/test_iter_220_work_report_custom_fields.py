"""Iter 220 — Work Report custom fields.

Engineers + master admins can define machine-specific custom fields that
the Engineer App renders on the Complete tab and persists onto the case +
the customer Service Report PDF. Tests pin:

  • CRUD via /api/svc/work-report-fields (admin auth)
  • Scope resolution (`for-case/{id}` returns only matching defs)
  • Required-field validation on /complete
  • Value persistence onto svc_cases.work_report_custom_fields
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
    "https://maintenance-hub-357.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": secret} if secret else {}


def _login(email: str, password: str) -> str:
    key = f"login::{email}"
    if _CACHE.get(key):
        return _CACHE[key]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass_headers(),
        )
        r.raise_for_status()
    _CACHE[key] = r.json()["token"]
    return _CACHE[key]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin_user(db):
    user = db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0})
    assert user, "Master admin seed missing"
    return user


@pytest.fixture
def field_cleanup(db, admin_user):
    """Track created field ids so we can hard-delete them after each test."""
    created: list[str] = []
    yield created
    if created:
        db.svc_work_report_field_defs.delete_many(
            {"organization_id": admin_user["organization_id"], "id": {"$in": created}},
        )


def _create_field(payload: dict) -> dict:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/work-report-fields",
            json=payload,
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    return r.json()


# ─────────────────── CRUD basics ───────────────────


def test_create_text_field_persists_with_slug_key(field_cleanup):
    body = _create_field({
        "name": "Current Software",
        "field_type": "text",
        "scope_kind": "equipment_type",
        "scope_value": "Treadmill",
    })
    field_cleanup.append(body["id"])
    assert body["key"] == "current_software"
    assert body["scope_kind"] == "equipment_type"
    assert body["scope_value"] == "Treadmill"
    assert body["archived"] is False


def test_create_dropdown_requires_at_least_two_options(field_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/work-report-fields",
            json={
                "name": "Belt Wear",
                "field_type": "dropdown",
                "scope_kind": "global",
                "options": ["Light"],
            },
            headers=_admin_headers(),
        )
    assert r.status_code == 400
    assert "at least 2 options" in r.text


def test_patch_archive_unarchive_round_trip(field_cleanup):
    body = _create_field({
        "name": "Drag Factor",
        "field_type": "number",
        "scope_kind": "manufacturer",
        "scope_value": "Concept 2",
        "required": True,
    })
    field_cleanup.append(body["id"])
    field_id = body["id"]

    # Soft-archive via DELETE
    with httpx.Client(timeout=15.0) as c:
        r = c.delete(
            f"{BASE}/api/svc/work-report-fields/{field_id}",
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    assert r.json()["archived"] is True

    # PATCH to unarchive
    with httpx.Client(timeout=15.0) as c:
        r = c.patch(
            f"{BASE}/api/svc/work-report-fields/{field_id}",
            json={"archived": False, "required": False},
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    assert r.json()["archived"] is False
    assert r.json()["required"] is False


def test_scope_value_required_when_not_global(field_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/work-report-fields",
            json={
                "name": "Bad Scope",
                "field_type": "text",
                "scope_kind": "manufacturer",
                "scope_value": "",
            },
            headers=_admin_headers(),
        )
    assert r.status_code == 400
    assert "scope_value" in r.text


# ─────────────────── Scope resolution via /for-case/{id} ───────────────────


def test_for_case_returns_only_matching_scope(db, admin_user, field_cleanup):
    org_id = admin_user["organization_id"]
    asset_id = f"test-asset-{uuid.uuid4().hex[:8]}"
    case_id = f"test-case-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id,
        "organization_id": org_id,
        "name": "Test Bike",
        "equipment_type": "Indoor Bike",
        "manufacturer": "Concept 2",
        "model": "BikeErg",
    })
    db.svc_cases.insert_one({
        "id": case_id,
        "organization_id": org_id,
        "reference": "TST-0001",
        "title": "Test",
        "asset_id": asset_id,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        # 3 fields — only the manufacturer-scoped one matches.
        f_global = _create_field({
            "name": "Global Note",
            "field_type": "text",
            "scope_kind": "global",
        })
        field_cleanup.append(f_global["id"])
        f_match = _create_field({
            "name": "Drag Factor C2",
            "field_type": "number",
            "scope_kind": "manufacturer",
            "scope_value": "Concept 2",
        })
        field_cleanup.append(f_match["id"])
        f_miss = _create_field({
            "name": "Belt Wear",
            "field_type": "text",
            "scope_kind": "manufacturer",
            "scope_value": "Life Fitness",
        })
        field_cleanup.append(f_miss["id"])

        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/work-report-fields/for-case/{case_id}",
                headers=_admin_headers(),
            )
        assert r.status_code == 200, r.text
        keys = {f["key"] for f in r.json()["fields"]}
        assert "global_note" in keys
        assert "drag_factor_c2" in keys
        assert "belt_wear" not in keys
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.equipment.delete_one({"id": asset_id})


def test_for_case_404_when_missing(field_cleanup):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/work-report-fields/for-case/does-not-exist-{uuid.uuid4().hex[:8]}",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


# ─────────────────── /complete value persistence + required-field guard ───────────────────


def test_complete_persists_clean_custom_fields(db, admin_user, field_cleanup):
    org_id = admin_user["organization_id"]
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id, "organization_id": org_id,
        "name": "Treadmill A", "equipment_type": "Treadmill",
        "manufacturer": "Pulse", "model": "Run X",
    })
    db.svc_cases.insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": "PERSIST-0001", "title": "Cf test",
        "asset_id": asset_id, "status": "on_site",
        "assigned_engineer_id": admin_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        f1 = _create_field({
            "name": "Current Software",
            "field_type": "text",
            "scope_kind": "equipment_type",
            "scope_value": "Treadmill",
        })
        field_cleanup.append(f1["id"])
        f2 = _create_field({
            "name": "Wheel Check",
            "field_type": "checkbox",
            "scope_kind": "global",
        })
        field_cleanup.append(f2["id"])

        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={
                    "summary": "Replaced belt",
                    "target": "repaired",
                    "custom_fields": {
                        "current_software": "v2.3.1",
                        "wheel_check": True,
                        "ignored_unknown_key": "x",  # silently dropped
                    },
                },
                headers=_admin_headers(),
            )
        assert r.status_code == 200, r.text
        saved = db.svc_cases.find_one({"id": case_id}, {"_id": 0, "work_report_custom_fields": 1})
        assert saved["work_report_custom_fields"] == {
            "current_software": "v2.3.1",
            "wheel_check": True,
        }
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.equipment.delete_one({"id": asset_id})


def test_complete_rejects_missing_required_field(db, admin_user, field_cleanup):
    org_id = admin_user["organization_id"]
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id, "organization_id": org_id,
        "name": "Treadmill B", "equipment_type": "Treadmill",
        "manufacturer": "Pulse", "model": "Run X",
    })
    db.svc_cases.insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": "REQ-0001", "title": "Req test",
        "asset_id": asset_id, "status": "on_site",
        "assigned_engineer_id": admin_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        f_req = _create_field({
            "name": "Belt Tension",
            "field_type": "number",
            "scope_kind": "equipment_type",
            "scope_value": "Treadmill",
            "required": True,
        })
        field_cleanup.append(f_req["id"])

        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={
                    "summary": "Will fail",
                    "target": "repaired",
                    "custom_fields": {},
                },
                headers=_admin_headers(),
            )
        assert r.status_code == 400, r.text
        assert "Belt Tension" in r.text
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.equipment.delete_one({"id": asset_id})


def test_complete_rejects_non_numeric_for_number_field(db, admin_user, field_cleanup):
    org_id = admin_user["organization_id"]
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id, "organization_id": org_id,
        "name": "Rower X", "equipment_type": "Rower",
        "manufacturer": "Concept 2", "model": "Model D",
    })
    db.svc_cases.insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": "NUM-0001", "title": "Num test",
        "asset_id": asset_id, "status": "on_site",
        "assigned_engineer_id": admin_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        f = _create_field({
            "name": "Drag Factor",
            "field_type": "number",
            "scope_kind": "manufacturer",
            "scope_value": "Concept 2",
        })
        field_cleanup.append(f["id"])

        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={
                    "summary": "Bad data",
                    "target": "repaired",
                    "custom_fields": {"drag_factor": "not-a-number"},
                },
                headers=_admin_headers(),
            )
        assert r.status_code == 400
        assert "Drag Factor" in r.text
        assert "number" in r.text
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.equipment.delete_one({"id": asset_id})


def test_complete_accepts_dropdown_value_only_when_in_options(db, admin_user, field_cleanup):
    org_id = admin_user["organization_id"]
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    db.equipment.insert_one({
        "id": asset_id, "organization_id": org_id,
        "name": "Treadmill C", "equipment_type": "Treadmill",
        "manufacturer": "Pulse", "model": "Run X",
    })
    db.svc_cases.insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": "DD-0001", "title": "Dropdown test",
        "asset_id": asset_id, "status": "on_site",
        "assigned_engineer_id": admin_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        f = _create_field({
            "name": "Belt Wear",
            "field_type": "dropdown",
            "scope_kind": "global",
            "options": ["Light", "Medium", "Heavy"],
        })
        field_cleanup.append(f["id"])

        # Bad option → 400
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={
                    "summary": "Bad dropdown",
                    "target": "repaired",
                    "custom_fields": {"belt_wear": "Unknown"},
                },
                headers=_admin_headers(),
            )
        assert r.status_code == 400

        # Good option → 200 and persisted
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={
                    "summary": "Good dropdown",
                    "target": "repaired",
                    "custom_fields": {"belt_wear": "Medium"},
                },
                headers=_admin_headers(),
            )
        assert r.status_code == 200, r.text
        doc = db.svc_cases.find_one({"id": case_id}, {"_id": 0, "work_report_custom_fields": 1})
        assert doc["work_report_custom_fields"]["belt_wear"] == "Medium"
    finally:
        db.svc_cases.delete_one({"id": case_id})
        db.equipment.delete_one({"id": asset_id})
